#!/usr/bin/env python3
"""Bind generated M2 package identities to their embedded source-map inputs.

The audit does not infer a historical invocation from a filename. HP2's HMAP
section carries the source map digest, which is matched against available map
files by content. Producer recipes are reported as historical only when a
report pins the exact output digest and includes a command; otherwise the
current packer is identified as a capable producer, not claimed as the one
that made the artifact.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import shlex
import sys
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
PACKER_PATH = ROOT / "tools/pack_retail_ctag_hp2.py"
sys.path.insert(0, str(ROOT / "tools"))
from ctag import _hp2_module  # noqa: E402
import hmap  # noqa: E402

DEFAULT_PACKAGE_ROOTS = (
    "build/retail-maps", "build/m2-mp-all-map-packages",
    "build/hcu-parent-link-probe/maps", "build/m2-mp-extra",
    "build/m2-artifacts", "build/m2-mp-wind-package",
)
DEFAULT_MAP_ROOTS = ("build/retail-maps", "build/hcu-parent-link-probe/maps")
DEFAULT_SCHEMA_PATHS = (
    "build/hcu-ps2-closure/all/halo-local.elf",
    "build/m2-artifacts/schema-2fba411b-prior/halo-local.elf",
    "build/hcu-ps2-closure/all-no-bootstrap-memory/halo-local.elf",
    "build/hcu-ps2-closure/all-no-bootstrap-memory-step8-mp-workload-4p/halo-local.elf",
)
MP_PROFILE_MANIFEST = "build/m2-mp-nested-census-13/manifest.json"
PACKAGE_SUFFIXES = {".hp2", ".ctag", ".cbsp", ".hmap"}


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def hash_index(roots: list[Path]) -> dict[str, list[Path]]:
    result: dict[str, list[Path]] = {}
    for root in roots:
        if not root.is_dir():
            continue
        for path in sorted(root.rglob("*")):
            if path.is_file() and path.suffix.lower() == ".map":
                result.setdefault(digest(path), []).append(path)
    return result


def report_refs(package_hash: str, report_roots: list[Path]) -> list[dict]:
    """Find exact output-hash pins; nearby commands are useful but not proof."""
    refs = []
    for root in report_roots:
        if not root.is_dir():
            continue
        for path in sorted(root.rglob("*")):
            if not path.is_file() or path.suffix.lower() not in {".md", ".json", ".txt"}:
                continue
            if path.relative_to(ROOT).as_posix() == "docs/reports/m2-step7-step8-package-provenance-2026-10-22.json":
                continue
            try:
                content = path.read_text(errors="replace")
            except OSError:
                continue
            if package_hash not in content.lower():
                continue
            rel = path.relative_to(ROOT).as_posix()
            lines = content.splitlines()
            for number, line in enumerate(lines, 1):
                if package_hash not in line.lower():
                    continue
                context = "\n".join(lines[max(0, number - 16):min(len(lines), number + 3)])
                commands = [x.strip() for x in context.splitlines()
                            if re.search(r"(?:python\d?\s+|tools/)[^\n]*(?:pack_retail_ctag_hp2|convert_retail|\.hp2)", x)]
                if commands:
                    # Preserve the exact nearby shell lines, including wrapped
                    # arguments, so a reviewer can distinguish a printed hash
                    # from a command tied to that output in the same report.
                    start = max(0, number - 16)
                    command_start = next((i for i in range(number - 1, start - 1, -1)
                                          if re.match(r"\s*(?:python\d?\s+|(?:[^\s]+/)?[\w.-]+\.py\s+)", lines[i])), None)
                    if command_start is not None:
                        wrapped = []
                        for candidate in lines[command_start:number]:
                            if not candidate.strip():
                                if wrapped:
                                    break
                                continue
                            if candidate.strip().startswith("```"):
                                if wrapped:
                                    break
                                continue
                            wrapped.append(candidate.strip().removesuffix("\\").strip())
                        commands = [" ".join(part for part in wrapped if part)]
                bound_files = []
                for command in commands:
                    for token in shlex.split(command):
                        candidate = (ROOT / token).resolve()
                        try:
                            candidate.relative_to(ROOT.resolve())
                        except ValueError:
                            continue
                        if candidate.is_file():
                            bound_files.append({"path": candidate.relative_to(ROOT).as_posix(),
                                                "sha256": digest(candidate),
                                                "bytes": candidate.stat().st_size})
                refs.append({"path": rel, "sha256": digest(path), "line": number,
                             "exact_output_hash_pin": True,
                             "nearby_command_text": commands,
                             "command_file_bindings": bound_files})
    # A report may repeat a package digest in prose, tables, and embedded JSON.
    # Keep its strongest single binding (a command-bearing occurrence wins)
    # rather than multiplying identical citations in the machine manifest.
    best: dict[str, dict] = {}
    for ref in refs:
        prior = best.get(ref["path"])
        rank = (bool(ref["nearby_command_text"]), -ref["line"])
        prior_rank = ((bool(prior["nearby_command_text"]), -prior["line"])
                      if prior else None)
        if prior is None or rank > prior_rank:
            best[ref["path"]] = ref
    return [best[path] for path in sorted(best)]


def package_record(path: Path, map_by_hash: dict[str, list[Path]], report_roots: list[Path]) -> dict:
    record = {"path": path.relative_to(ROOT).as_posix(), "sha256": digest(path),
              "bytes": path.stat().st_size, "extension": path.suffix.lower(),
              "producer_binding": "unresolved-historical-invocation"}
    if path.suffix.lower() != ".hp2":
        record["format_provenance"] = "standalone-component; no container metadata to bind producer inputs"
        record["report_pins"] = report_refs(record["sha256"], report_roots)
        return record
    hp2 = _hp2_module()
    pack = hp2.parse(path.read_bytes())
    sections = []
    hmap_identity = None
    for section in pack.sections:
        payload = pack.read(section.tag)
        item = {"tag": section.tag, "bytes": len(payload),
                "sha256": hashlib.sha256(payload).hexdigest()}
        if section.tag == "HMAP":
            identity = hmap.decode(payload, expected_map_name=pack.name)
            source_hash = identity.source_sha256.hex()
            candidates = map_by_hash.get(source_hash, [])
            hmap_identity = {
                "map_name": identity.map_name,
                "source_file_bytes": identity.file_length,
                "source_tag_data_offset": identity.tag_data_offset,
                "source_tag_data_bytes": identity.tag_data_size,
                "source_map_sha256": source_hash,
                "source_map_paths": [p.relative_to(ROOT).as_posix() for p in candidates],
                "source_map_binding": "unique-exact-content-match" if len(candidates) == 1
                    else "multiple-exact-content-matches" if candidates else "source-map-bytes-not-present",
            }
        sections.append(item)
    output_path = path.relative_to(ROOT).as_posix()
    output_pins = report_refs(record["sha256"], report_roots)
    invocation_bindings = []
    for pin in output_pins:
        for command in pin["nearby_command_text"]:
            files = pin["command_file_bindings"]
            file_paths = {item["path"] for item in files}
            if output_path in file_paths and any(p.startswith("tools/") and p.endswith(".py")
                                                 for p in file_paths):
                invocation_bindings.append({"report_path": pin["path"],
                                            "report_sha256": pin["sha256"],
                                            "report_line": pin["line"],
                                            "exact_output_sha256_pin": True,
                                            "command": command,
                                            "command_file_bindings": files})
    record.update({"container_name": pack.name, "sections": sections,
                   "hmap_input": hmap_identity,
                   "historical_invocation_bindings": invocation_bindings,
                   "producer_capability": {
                       "path": "tools/pack_retail_ctag_hp2.py",
                       "sha256": digest(PACKER_PATH),
                       "scope": "current implementation can produce CTAG/CRNG/HMAP and Bxxx/CBIX packages",
                       "historical_producer_claim": False,
                   },
                   "historical_output_hash_pins": output_pins})
    if hmap_identity:
        record["producer_binding"] = (("historical-command-output-and-argument-files-bound; other historical inputs unresolved"
                                        if invocation_bindings else
                                        "source-map-input-bound; schema-and-invocation-unresolved")
                                       if hmap_identity["source_map_paths"] else
                                       "embedded-source-digest-only; source-bytes-unavailable")
    return record


def _run_cli_recipe(map_path: Path, schema_path: Path,
                    include_all_bsps: bool) -> tuple[str, int]:
    """Run the retained packer into a temporary path using the observed scope."""
    with tempfile.TemporaryDirectory(prefix="hcu-package-provenance-") as temp:
        output = Path(temp) / f"{map_path.stem}.hp2"
        command = [sys.executable, "tools/pack_retail_ctag_hp2.py", str(map_path),
                   str(schema_path), str(output)]
        if include_all_bsps:
            command.append("--include-all-bsps")
        completed = subprocess.run(command, cwd=ROOT, check=True,
                                   stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                   text=True)
        return digest(output), output.stat().st_size


def _reproduce_hp2(record: dict, map_by_hash: dict[str, list[Path]],
                   schema_paths: list[Path], reproduction_cache: dict) -> dict:
    identity = record.get("hmap_input")
    if not identity or not identity.get("source_map_paths"):
        return {"result": "not_reproduced", "reason": "no exact local HMAP source-map bytes"}
    map_candidates = [p for p in map_by_hash.get(identity["source_map_sha256"], [])
                      if p.stem.lower() == identity["map_name"].lower()]
    if not map_candidates:
        return {"result": "not_reproduced", "reason": "no source file with matching HMAP name and bytes"}
    map_path = sorted(map_candidates, key=lambda p: ("/decompressed/" not in p.as_posix(), p.as_posix()))[0]
    section_tags = {section["tag"] for section in record.get("sections", [])}
    include_all_bsps = "CBIX" in section_tags or any(
        re.fullmatch(r"B\d{3}", tag) for tag in section_tags)
    attempts = []
    for schema_path in schema_paths:
        if not schema_path.is_file():
            continue
        key = (identity["source_map_sha256"], digest(schema_path), include_all_bsps)
        if key not in reproduction_cache:
            try:
                output_hash, output_bytes = _run_cli_recipe(map_path, schema_path,
                                                            include_all_bsps)
                reproduction_cache[key] = {"output_sha256": output_hash,
                                           "output_bytes": output_bytes,
                                           "map_path": map_path,
                                           "schema_path": schema_path,
                                           "error": None}
            except (OSError, subprocess.CalledProcessError) as error:
                reproduction_cache[key] = {"error": str(error),
                                           "map_path": map_path,
                                           "schema_path": schema_path}
        result = reproduction_cache[key]
        if result.get("error"):
            attempts.append({"schema_path": schema_path.relative_to(ROOT).as_posix(),
                             "result": "failed", "detail": result["error"]})
            continue
        if result["output_sha256"] == record["sha256"]:
            return {
                "result": "byte_identical_reproduction",
                "historical_execution_claim": False,
                "recipe": {"command_template": "python3 tools/pack_retail_ctag_hp2.py <map> <schema-elf> <output-hp2>" +
                                              (" --include-all-bsps" if include_all_bsps else ""),
                           "map_path": map_path.relative_to(ROOT).as_posix(),
                           "map_sha256": digest(map_path),
                           "schema_elf_path": schema_path.relative_to(ROOT).as_posix(),
                           "schema_elf_sha256": digest(schema_path),
                           "producer_path": "tools/pack_retail_ctag_hp2.py",
                           "producer_sha256": digest(ROOT / "tools/pack_retail_ctag_hp2.py"),
                           "output_sha256": result["output_sha256"],
                           "output_bytes": result["output_bytes"],
                           "include_all_bsps": include_all_bsps},
                "limitation": "The recipe reproduces the exact bytes from retained inputs; it does not prove that this was the historical invocation."}
        attempts.append({"schema_path": schema_path.relative_to(ROOT).as_posix(),
                         "schema_elf_sha256": digest(schema_path),
                         "rebuilt_output_sha256": result["output_sha256"],
                         "result": "hash_mismatch"})
    return {"result": "not_reproduced", "historical_execution_claim": False,
            "attempts": attempts,
            "reason": "retained candidate schemas did not reproduce the package bytes"}


def _reproduce_ui_component(record: dict, hmap_pack_path: Path) -> dict:
    """Recreate the CTAG+CRNG-only UI package from the retained HMAP package."""
    hp2 = _hp2_module()
    source = hp2.parse(hmap_pack_path.read_bytes())
    output = hp2.build(source.name, [(tag, source.read(tag)) for tag in ("CTAG", "CRNG")])
    output_hash = hashlib.sha256(output).hexdigest()
    if output_hash != record["sha256"]:
        return {"result": "not_reproduced", "rebuilt_output_sha256": output_hash,
                "reason": "repacked CTAG/CRNG sections do not match component package"}
    return {"result": "byte_identical_reproduction", "historical_execution_claim": False,
            "recipe": {"operation": "parse source HP2; retain CTAG and CRNG; rebuild HP2 under same package name",
                       "source_package_path": hmap_pack_path.relative_to(ROOT).as_posix(),
                       "source_package_sha256": digest(hmap_pack_path),
                       "source_section_tags": ["CTAG", "CRNG"],
                       "producer_path": "submodules/halo-ps2/tools/halo2ps2/hp2.py",
                       "producer_sha256": digest(ROOT / "submodules/halo-ps2/tools/halo2ps2/hp2.py"),
                       "output_sha256": output_hash,
                       "output_bytes": len(output)},
            "limitation": "The reconstructed recipe proves byte identity from the retained HMAP package; it does not prove historical execution."}


def profile_package_bindings(record: dict, profile_path: Path) -> list[dict]:
    """Bind package content and exact-path commands from a retained MP manifest.

    The manifest's `package_generation` entries are treated as command evidence
    only when the command names this exact package path and all map, schema,
    producer, and output hashes agree. Hash-equal copies receive content/profile
    bindings, never another file's invocation claim.
    """
    if not profile_path.is_file() or not record.get("hmap_input"):
        return []
    profile = json.loads(profile_path.read_text())
    if profile.get("status") != "passed":
        return []
    manifest_rel = profile_path.relative_to(ROOT).as_posix()
    manifest_sha = digest(profile_path)
    identity = record["hmap_input"]
    bindings = []
    for map_name, output_sha in profile.get("packages", {}).items():
        generation = profile.get("package_generation", {}).get(map_name, {})
        map_sha = profile.get("source_maps", {}).get(map_name)
        schema_sha = generation.get("schema_elf_sha256")
        if (map_name != identity.get("map_name") or output_sha != record["sha256"]
                or map_sha != identity.get("source_map_sha256")
                or generation.get("package_sha256", output_sha) != record["sha256"]
                or not schema_sha):
            continue
        recipe = record.get("reproduction", {}).get("recipe", {})
        if recipe.get("schema_elf_sha256") and recipe["schema_elf_sha256"] != schema_sha:
            continue

        command = generation.get("command") or generation.get("generation_record", "")
        binding = {
            "profile_manifest_path": manifest_rel,
            "profile_manifest_sha256": manifest_sha,
            "profile_status": profile["status"],
            "profile_capacity_scope": profile.get("capacity_scope"),
            "map_name": map_name,
            "manifest_json_pointers": [f"/packages/{map_name}",
                                        f"/source_maps/{map_name}",
                                        f"/package_generation/{map_name}"],
            "package_sha256": record["sha256"],
            "source_map_sha256": map_sha,
            "schema_elf_sha256": schema_sha,
            "path_specific_invocation": False,
            "limitation": "Profile manifest binds package content and source/schema identities; it does not name this package path's invocation.",
        }
        if "pack_retail_ctag_hp2.py" in command:
            try:
                tokens = shlex.split(command)
            except ValueError:
                continue
            if len(tokens) != 5 or tokens[0] != "tools/pack_retail_ctag_hp2.py":
                continue
            command_files = []
            for token in tokens[:4]:
                path = (ROOT / token).resolve()
                try:
                    path.relative_to(ROOT.resolve())
                except ValueError:
                    command_files = []
                    break
                if not path.is_file():
                    command_files = []
                    break
                command_files.append({"path": path.relative_to(ROOT).as_posix(),
                                      "sha256": digest(path),
                                      "bytes": path.stat().st_size})
            if not command_files:
                continue
            command_output = command_files[3]["path"]
            # A command record for a byte-identical sibling is not evidence
            # that this particular package path was generated by that command.
            if command_output != record["path"]:
                bindings.append(binding)
                continue
            if (command_files[1]["sha256"] != map_sha
                    or command_files[2]["sha256"] != schema_sha
                    or command_files[3]["sha256"] != record["sha256"]
                    or tokens[4] != "--include-all-bsps"):
                continue
            binding.update({
                "path_specific_invocation": True,
                "command": command,
                "command_file_bindings": command_files,
                "limitation": "Retained profile-generation record pins the exact package path, output hash, map, schema ELF, and packer bytes; toolchain identity and broader build context remain outside this package recipe.",
            })
        elif map_name == "damnation" and "m2-mp-wind-package/manifest.json" in command:
            binding["limitation"] = "Damnation content is linked to the retained wind-package manifest, which pins output/map/schema hashes but contains no packer invocation or package output path."
        else:
            continue
        bindings.append(binding)
    return bindings


def build_manifest(package_roots: list[Path], map_roots: list[Path], report_roots: list[Path],
                   *, verify_reproduction: bool = False,
                   schema_paths: list[Path] | None = None) -> dict:
    maps = hash_index(map_roots)
    paths = []
    for root in package_roots:
        if root.is_dir():
            paths.extend(p for p in root.rglob("*") if p.is_file()
                         and p.suffix.lower() in PACKAGE_SUFFIXES
                         and "fault" not in p.name.lower())
    # Also include the named retail UI packages kept outside the package roots.
    for p in (ROOT / "build/retail-ui-hmap.hp2", ROOT / "build/retail-ui-component.hp2"):
        if p.is_file():
            paths.append(p)
    unique = sorted(set(paths))
    packages = [package_record(p, maps, report_roots) for p in unique]
    reproduction_cache = {}
    if verify_reproduction:
        schemas = schema_paths if schema_paths is not None else [ROOT / p for p in DEFAULT_SCHEMA_PATHS]
        ui_source = ROOT / "build/retail-ui-hmap.hp2"
        ui_component_hash = None
        if ui_source.is_file():
            ui_component_hash = digest(ui_source)
        for package in packages:
            artifact = ROOT / package["path"]
            if package["extension"] == ".hp2" and package.get("hmap_input"):
                package["reproduction"] = _reproduce_hp2(package, maps, schemas,
                                                         reproduction_cache)
            elif (artifact.name == "retail-ui-component.hp2" and ui_component_hash
                  and ui_source.is_file()):
                package["reproduction"] = _reproduce_ui_component(package, ui_source)
            else:
                package["reproduction"] = {"result": "not_attempted",
                                           "reason": "no supported reconstruction recipe"}
    profile_path = ROOT / MP_PROFILE_MANIFEST
    for package in packages:
        bindings = profile_package_bindings(package, profile_path)
        package["profile_manifest_bindings"] = bindings
        path_specific = [binding for binding in bindings
                         if binding["path_specific_invocation"]]
        if path_specific:
            # Keep the existing stronger docs/reports command evidence and
            # append profile-manifest command evidence, deduplicated by the
            # source artifact + pointer. Byte-identical sibling outputs never
            # inherit these path-specific commands.
            invocations = package.setdefault("historical_invocation_bindings", [])
            for binding in path_specific:
                invocation = {
                    "report_path": binding["profile_manifest_path"],
                    "report_sha256": binding["profile_manifest_sha256"],
                    "json_pointer": binding["manifest_json_pointers"][2],
                    "exact_output_sha256_pin": True,
                    "command": binding["command"],
                    "command_file_bindings": binding["command_file_bindings"],
                    "evidence_kind": "retained-profile-manifest-generation-record",
                }
                if not any(existing.get("report_path") == invocation["report_path"]
                           and existing.get("json_pointer") == invocation["json_pointer"]
                           for existing in invocations):
                    invocations.append(invocation)
            package["producer_binding"] = (
                "historical-command-output-and-argument-files-bound; other historical inputs unresolved")

    invocation_path_count = sum(bool(item.get("historical_invocation_bindings"))
                                for item in packages)
    unresolved_invocation_path_count = len(packages) - invocation_path_count
    profile_command_path_count = sum(any(binding.get("path_specific_invocation")
                                         for binding in item.get("profile_manifest_bindings", []))
                                     for item in packages)
    counts: dict[str, int] = {}
    for item in packages:
        status = item["producer_binding"]
        counts[status] = counts.get(status, 0) + 1
    reproduction_counts: dict[str, int] = {}
    for item in packages:
        status = item.get("reproduction", {}).get("result", "not_attempted")
        reproduction_counts[status] = reproduction_counts.get(status, 0) + 1
    return {"format": "hcu-step7-step8-package-provenance-v1",
            "scope": "generated package identity and embedded HMAP source binding",
            "package_count": len(packages), "producer_binding_counts": counts,
            "reproduction_verification": {"enabled": verify_reproduction,
                                          "counts": reproduction_counts,
                                          "historical_execution_claims": 0},
            "historical_invocation_coverage": {
                "package_path_count": len(packages),
                "path_specific_invocation_count": invocation_path_count,
                "profile_manifest_path_specific_invocation_count": profile_command_path_count,
                "unresolved_path_specific_invocation_count": unresolved_invocation_path_count,
                "limitation": "A byte-identical sibling's command is not transferred to another path. Package recipe reproduction remains current-input evidence, not proof of historical execution.",
            },
            "packages": packages,
            "limitation": "Matching HMAP to source bytes binds the map input only. Historical schema ELF, optional section inputs, exact CLI, and toolchain remain unresolved unless independently pinned in the cited report; current producer capability is not historical provenance."}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--package-root", action="append", default=[])
    ap.add_argument("--map-root", action="append", default=[])
    ap.add_argument("--report-root", action="append", default=["docs/reports"])
    ap.add_argument("--verify-reproduction", action="store_true",
                    help="rebuild candidate HP2 packages from retained maps and schema ELFs, then compare exact bytes")
    ap.add_argument("--schema-elf", action="append", default=[],
                    help="schema ELF candidate used with --verify-reproduction; may be repeated")
    ap.add_argument("--output", type=Path, default=ROOT / "docs/reports/m2-step7-step8-package-provenance-2026-10-22.json")
    args = ap.parse_args(argv)
    package_roots = [ROOT / x for x in (args.package_root or DEFAULT_PACKAGE_ROOTS)]
    map_roots = [ROOT / x for x in (args.map_root or DEFAULT_MAP_ROOTS)]
    report_roots = [ROOT / x for x in args.report_root]
    schemas = [ROOT / path for path in args.schema_elf] if args.schema_elf else None
    result = build_manifest(package_roots, map_roots, report_roots,
                            verify_reproduction=args.verify_reproduction,
                            schema_paths=schemas)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(f"packages={result['package_count']} output={args.output.relative_to(ROOT)}")
    print(json.dumps(result["producer_binding_counts"], sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
