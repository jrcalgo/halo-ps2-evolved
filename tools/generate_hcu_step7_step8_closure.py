#!/usr/bin/env python3
"""Generate the current M2 Step 7/8 evidence ledger and BSP field inventory.

This records existing evidence without upgrading the scope of any fixture. The
compiler-derived schema supplies serialized field extents; uncovered bytes are
reported explicitly and remain open for source/layout classification.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from hcu_schema_manifest import Elf32, SchemaManifest  # noqa: E402
from build_toolchain import environment as toolchain_environment  # noqa: E402

SCHEMA_DEFAULT = ROOT / "build/hcu-ps2-closure/all-no-bootstrap-memory/halo-local.elf"
LEDGER_DEFAULT = ROOT / "docs/reports/m2-step7-step8-closure-ledger-2026-10-22.json"
INVENTORY_DEFAULT = ROOT / "docs/reports/m2-step7-bsp-member-inventory-2026-10-22.json"
COVERAGE_AUDIT_DEFAULT = ROOT / "docs/reports/m2-step7-step8-ledger-coverage-audit-2026-10-22.json"
PACKAGE_PROVENANCE_DEFAULT = ROOT / "docs/reports/m2-step7-step8-package-provenance-2026-10-22.json"
RECOVERED_BINDINGS_DEFAULT = ROOT / "docs/reports/m2-step7-step8-supplemental-bindings-2026-10-23.json"
ROOT_GAP_LAYOUT = [
    (16, 4, "vehicle_floor"), (20, 4, "vehicle_ceiling"),
    (24, 20, "sad_unused[5]"), (160, 4, "lonely_unused"),
    (200, 24, "world_bounds"), (272, 12, "render_unused[3]"),
    (352, 12, "cluster_unused[3]"), (412, 24, "fog_unused[6]"),
    (460, 24, "weather_unused[6]"), (552, 24, "sound_unused[6]"),
    (576, 12, "markers"), (612, 8, "diminishing_misc_unused[2]"),
]

_REPORT_PIN_SOURCE_INDEX: dict[str, list[str]] | None = None

def _report_pin_source_index() -> dict[str, list[str]]:
    """Index current source/fixture bytes so prose pins can bind to exact files.

    Many historic reports record a runner or fixture digest but omit the path
    beside it. Exact content matching against the bounded source roots repairs
    that identity without treating a label or a nearby hash as evidence.
    """
    global _REPORT_PIN_SOURCE_INDEX
    if _REPORT_PIN_SOURCE_INDEX is not None:
        return _REPORT_PIN_SOURCE_INDEX
    roots = [ROOT / name for name in ("tools", "tests", "src", "config")]
    roots += [ROOT / "submodules" / repo / subtree
              for repo, subtree in (("halo-ce-universal", "source"),
                                    ("halo-ce-universal", "port"),
                                    ("halo-ps2", "engine"),
                                    ("halo-ps2", "port"),
                                    ("halo-64", "port"))]
    index: dict[str, list[str]] = {}
    for root in roots:
        if not root.is_dir():
            continue
        for path in root.rglob("*"):
            if not path.is_file() or ".git" in path.parts:
                continue
            try:
                digest = sha256(path)
            except OSError:
                continue
            index.setdefault(digest, []).append(str(path.relative_to(ROOT)))
    _REPORT_PIN_SOURCE_INDEX = {digest: sorted(paths) for digest, paths in index.items()}
    return _REPORT_PIN_SOURCE_INDEX


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def package_provenance_identity(path: Path = PACKAGE_PROVENANCE_DEFAULT) -> dict:
    """Pin the package provenance sidecar without elevating its evidence.

    Recipes remain unresolved unless the sidecar explicitly says otherwise;
    an exact package hash, HMAP source binding, or current command arguments
    alone do not establish every historical producer input.
    """
    relative = str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else str(path)
    if not path.is_file():
        return {"path": relative, "sha256": None, "bytes": None,
                "summary": {"status": "missing", "package_count": 0,
                            "source_map_input_bound_count": 0,
                            "historical_command_output_bound_count": 0,
                            "complete_recipe_count": 0,
                            "unresolved_recipe_count": None,
                            "limitation": "Provenance sidecar is absent; recipe completeness is unknown."}}
    obj = json.loads(path.read_text())
    if (obj.get("format") != "hcu-step7-step8-package-provenance-v1" or
            not isinstance(obj.get("packages"), list) or
            obj.get("package_count") != len(obj["packages"])):
        raise ValueError(f"invalid package provenance sidecar: {path}")
    packages = obj["packages"]
    source_bound = sum(bool((item.get("hmap_input") or {}).get("source_map_paths"))
                       for item in packages)
    command_bound = sum(bool(item.get("historical_invocation_bindings"))
                        for item in packages)
    # No current row establishes every historical generator input. Keep all
    # recipes open even where an output hash and command are jointly pinned.
    complete = sum(item.get("producer_binding") == "complete-historical-recipe"
                   for item in packages)
    unresolved = len(packages) - complete
    return {"path": relative, "sha256": sha256(path), "bytes": path.stat().st_size,
            "summary": {"status": "identity-pinned",
                        "package_count": len(packages),
                        "source_map_input_bound_count": source_bound,
                        "historical_command_output_bound_count": command_bound,
                        "complete_recipe_count": complete,
                        "unresolved_recipe_count": unresolved,
                        "limitation": obj.get("limitation")}}


def _bound_measurement(name: str, value, unit: str, artifact: Path,
                       pointer: str, derivation: str | None = None) -> dict:
    """Attach a verifiable artifact and exact JSON source location to a metric."""
    item = {"name": name, "value": value, "unit": unit,
            "source_artifact": str(artifact.relative_to(ROOT)),
            "source_artifact_sha256": sha256(artifact),
            "source_pointer": pointer}
    if derivation:
        item["derivation"] = derivation
    return item


def _json_pointer_value(document, pointer: str):
    """Read an RFC 6901-style pointer used by the exact-artifact metrics."""
    value = document
    for raw in pointer.strip("/").split("/"):
        if not raw:
            continue
        token = raw.replace("~1", "/").replace("~0", "~")
        value = value[int(token)] if isinstance(value, list) else value[token]
    return value


def git(path: Path, *args: str) -> str:
    return subprocess.check_output(["git", "-C", str(path), *args], text=True).strip()


def repository_identity(path: Path, name: str) -> dict:
    status = git(path, "status", "--porcelain=v1", "--untracked-files=all")
    tracked_diff = subprocess.check_output(
        ["git", "-C", str(path), "diff", "--binary", "HEAD"], stderr=subprocess.STDOUT)
    files = []
    prefixes = {
        "parent": ("src/", "tools/", "config/"),
        "halo-ce-universal": ("source/", "port/ps2/", "port/linux/game/"),
        "halo-ps2": ("engine/src/", "engine/include/", "tools/halo2ps2/"),
    }.get(name, ("**",))
    for line in status.splitlines():
        item = line[3:]
        if " -> " in item:
            item = item.split(" -> ", 1)[1]
        if (not item.startswith(prefixes) or
                Path(item).suffix not in {".c", ".h", ".py", ".mk", ".json", ".inc", ".vsm"}):
            continue
        candidate = path / item
        if candidate.is_file():
            files.append({"path": item, "sha256": sha256(candidate), "bytes": candidate.stat().st_size})
    return {
        "name": name,
        "path": str(path.relative_to(ROOT)),
        "head": git(path, "rev-parse", "HEAD"),
        "dirty": bool(status),
        "status_count": len(status.splitlines()),
        "status_porcelain_sha256": hashlib.sha256(status.encode()).hexdigest(),
        "tracked_diff_sha256": hashlib.sha256(tracked_diff).hexdigest(),
        "changed_file_sha256": files,
    }


def schema_source_identity(units: dict, source_root: Path) -> dict:
    """Reconcile every source compiled into the pinned schema ELF.

    A missing input is as stale as a changed one. Keep this separate from the
    repository dirty-file list: the latter describes the worktree, while this
    table describes the exact build's translation-unit inputs.
    """
    records = []
    for name, unit in sorted(units.items()):
        source = source_root / name
        current = sha256(source) if source.is_file() else None
        built = unit.get("source_sha256")
        status = "missing" if current is None else (
            "match" if current == built else "changed")
        records.append({
            "path": name,
            "built_source_sha256": built,
            "current_source_sha256": current,
            "object_sha256": unit.get("object_sha256"),
            "status": status,
        })
    counts = {key: sum(row["status"] == key for row in records)
              for key in ("match", "changed", "missing")}
    return {
        "status": "current" if counts["changed"] == 0 and counts["missing"] == 0
                  else "stale-or-incomplete",
        "unit_count": len(records),
        "counts": counts,
        "units": records,
    }


def flatten_definition(manifest: dict, definition_key: str, prefix: str,
                       base: int, extents: list[dict], stack: tuple[str, ...] = ()) -> None:
    definition = manifest["definitions"][str(definition_key)]
    if definition["name"] in stack:
        raise ValueError(f"recursive serialized structure schema: {definition['name']}")
    for field in definition["fields"]:
        name = field.get("name") or f"<unnamed@{field['offset']}>"
        path = f"{prefix}.{name}"
        start = base + field["offset"]
        if field["kind"] == "check":
            extents.append({"path": path, "offset": start, "size": 0,
                            "kind": "check", "classification": "validation-rule",
                            "maximum": field["maximum"]})
            continue
        if field["kind"] == "struct":
            child = manifest["definitions"][str(field["definition"])]
            child_size = child["size"]
            count = field["count"]
            for index in range(count):
                child_base = start + index * field["size"]
                flatten_definition(manifest, str(field["definition"]),
                                   f"{path}[{index}]" if count > 1 else path,
                                   child_base, extents, stack + (definition["name"],))
            extents.append({"path": path, "offset": start,
                            "size": field["size"] * max(0, count - 1) + child_size,
                            "kind": "struct", "classification": "schema-structure"})
        else:
            extents.append({
                "path": path, "offset": start,
                "size": field["size"] * field["count"],
                "kind": field["kind"], "classification": "schema-declared",
                "element_size": field["size"], "count": field["count"],
                "maximum": field["maximum"], "flags": field["flags"],
                "target_level": field["target_level"],
                "target_offset": field["target_offset"],
                **({"groups": field["groups"]} if "groups" in field else {}),
            })


def inventory(schema_elf: Path) -> dict:
    manifest = SchemaManifest(Elf32(schema_elf)).build()
    groups = [item for item in manifest["groups"]
              if item["group"] == "sbsp" and item["definition"] is not None]
    if len(groups) != 1:
        raise ValueError(f"expected one concrete sbsp schema, got {len(groups)}")
    root = manifest["definitions"][str(groups[0]["definition"])]
    definitions = manifest["definitions"]
    pending = [str(groups[0]["definition"])]
    seen = set()
    nodes = []
    rows = []
    schema_gaps = []
    overlaps = []
    while pending:
        key = pending.pop(0)
        if key in seen:
            continue
        seen.add(key)
        definition = definitions[key]
        members = []
        spans = []
        for field in definition["fields"]:
            name = field.get("name") or f"<unnamed@{field['offset']}>"
            size = field["size"] * field["count"]
            if field["kind"] == "check":
                size = 0
            elif field["kind"] == "struct" and field.get("definition") is not None:
                child = definitions[str(field["definition"])]
                size = field["size"] * max(0, field["count"] - 1) + child["size"]
            member = {
                "name": name, "offset": field["offset"], "size": size,
                "kind": field["kind"], "element_size": field["size"],
                "count": field["count"], "maximum": field["maximum"],
                "flags": field["flags"], "target_level": field["target_level"],
                "target_offset": field["target_offset"],
            }
            if "groups" in field:
                member["groups"] = field["groups"]
            if field.get("definition") is not None:
                member["child_definition_id"] = str(field["definition"])
                member["child_definition_name"] = definitions[str(field["definition"])]["name"]
                if field["kind"] in ("struct", "block"):
                    pending.append(str(field["definition"]))
            members.append(member)
            rows.append({"definition": definition["name"],
                         "definition_id": key,
                         "path": f"{definition['name']}.{name}",
                         "offset_within_definition": field["offset"], "size": size,
                         "kind": field["kind"], "classification": "schema-declared",
                         **{k: v for k, v in member.items()
                            if k not in {"name", "offset", "size", "kind"}}})
            if size:
                spans.append((field["offset"], field["offset"] + size, name))
        spans.sort()
        cursor = 0
        local_gaps = []
        for start, end, name in spans:
            if start < cursor:
                overlaps.append({"definition": definition["name"], "member": name,
                                 "offset": start, "end": end,
                                 "overlaps_previous_end": cursor})
            elif start > cursor:
                local_gaps.append({"offset": cursor, "size": start - cursor,
                                   "next_member": name})
            cursor = max(cursor, end)
        if cursor < definition["size"]:
            local_gaps.append({"offset": cursor, "size": definition["size"] - cursor,
                               "next_member": None})
        nodes.append({"definition_id": key, "name": definition["name"],
                      "serialized_size": definition["size"], "members": members,
                      "unrepresented_ranges": local_gaps})
        for gap in local_gaps:
            if key == str(groups[0]["definition"]):
                start, end = gap["offset"], gap["offset"] + gap["size"]
                named = sorted((offset, offset + size) for offset, size, _name
                               in ROOT_GAP_LAYOUT if offset >= start and offset + size <= end)
                covered = start
                for field_start, field_end in named:
                    if field_start != covered:
                        break
                    covered = field_end
                if covered == end:
                    continue
            schema_gaps.append({"definition": definition["name"],
                                "definition_id": key,
                                "path": f"{definition['name']}.<unclassified@0x{gap['offset']:x}>",
                                "offset_within_definition": gap["offset"],
                                "size": gap["size"], "kind": "schema-unrepresented-range",
                                "classification": "unclassified",
                                "next_member": gap["next_member"]})

    named_gap_rows = [{"definition": root["name"], "definition_id": str(groups[0]["definition"]),
                       "path": f"structure_bsp.{name}", "offset_within_definition": offset,
                       "size": size, "kind": "C-layout-member-omitted-from-validation-schema",
                       "classification": "consumer-disposition-open",
                       "layout_source": "source/structures/structure_bsp_definitions.h"}
                      for offset, size, name in ROOT_GAP_LAYOUT]
    root_unclassified = [gap for gap in schema_gaps
                         if gap["definition_id"] == str(groups[0]["definition"])]
    if root_unclassified:
        raise ValueError("named root layout did not close every schema gap")
    rows = sorted(rows + named_gap_rows + schema_gaps,
                  key=lambda row: (row.get("definition_id", ""),
                                   row.get("offset_within_definition", 0), row["path"]))
    return {
        "format": "hcu-step7-bsp-member-inventory-v1",
        "schema_elf": str(schema_elf.relative_to(ROOT)),
        "schema_elf_sha256": sha256(schema_elf),
        "schema_manifest_sha256": hashlib.sha256(
            json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()).hexdigest(),
        "schema_format": manifest["format"],
        "group": "sbsp",
        "definition": root["name"],
        "serialized_definition_bytes": root["size"],
        "definition_count": len(nodes),
        "member_rows": len(rows),
        "schema_declared_rows": sum(row["classification"] == "schema-declared" for row in rows),
        "schema_omitted_named_rows": len(named_gap_rows),
        "unclassified_ranges": len(schema_gaps),
        "schema_extent_overlaps": overlaps,
        "definitions": sorted(nodes, key=lambda item: (item["name"], item["definition_id"])),
        "compiler_layout": {
            "status": "source-named-pending-compiler-assertion",
            "assertions": [{"member": name, "offset": offset, "size": size}
                           for offset, size, name in ROOT_GAP_LAYOUT],
        },
        "members": rows,
        "status": "open" if schema_gaps or overlaps else "inventory-complete-pending-consumer-classification",
        "interpretation": (
            "Compiler-derived CE schema fields and byte extents are recorded. "
            "Ranges absent from the validation schema remain unclassified until "
            "compiler-derived C member layout and CE consumers name them. No field "
            "may be removed from this inventory based on retail corpus emptiness."
        ),
    }


def compile_member_layout(schema_elf: Path) -> dict:
    """Compile the root sbsp C layout against every linked schema member."""
    manifest = SchemaManifest(Elf32(schema_elf)).build()
    sbsp = [item for item in manifest["groups"]
            if item["group"] == "sbsp" and item["definition"] is not None]
    if len(sbsp) != 1:
        raise ValueError("expected one concrete sbsp definition")
    root = manifest["definitions"][str(sbsp[0]["definition"])]
    assertions = []
    assertions.append(
        f"HCU_LAYOUT_ASSERT(hcu_sizeof_structure_bsp, sizeof(struct structure_bsp) == {root['size']});")
    for field in root["fields"]:
        if field["kind"] == "check" or not field.get("name"):
            continue
        member = field["name"]
        assertions.append(
            f"HCU_LAYOUT_ASSERT(hcu_offset_{len(assertions)}, "
            f"offsetof(struct structure_bsp, {member}) == {field['offset']});")
        expected_size = field["size"] * field["count"]
        if field["kind"] == "struct":
            expected_size = manifest["definitions"][str(field["definition"])]["size"]
        assertions.append(
            f"HCU_LAYOUT_ASSERT(hcu_size_{len(assertions)}, "
            f"sizeof(((struct structure_bsp *)0)->{member}) == {expected_size});")
    for offset, size, field_name in ROOT_GAP_LAYOUT:
        member = field_name.split("[", 1)[0]
        assertions.append(
            f"HCU_LAYOUT_ASSERT(hcu_gap_offset_{len(assertions)}, "
            f"offsetof(struct structure_bsp, {member}) == {offset});")
        assertions.append(
            f"HCU_LAYOUT_ASSERT(hcu_gap_size_{len(assertions)}, "
            f"sizeof(((struct structure_bsp *)0)->{member}) == {size});")
    probe_dir = ROOT / "build/hcu-step7-step8-c0"
    probe_dir.mkdir(parents=True, exist_ok=True)
    source = probe_dir / "structure_bsp_member_layout.c"
    obj = probe_dir / "structure_bsp_member_layout.o"
    source.write_text(
        '#include "cseries.h"\n'
        '#include "structures/structure_bsp_definitions.h"\n'
        "#define HCU_LAYOUT_ASSERT(name, expression) typedef char name[(expression) ? 1 : -1]\n"
        + "\n".join(assertions) + "\n")

    build, prefix, env, _jobs = toolchain_environment()
    hcu_manifest = json.loads((ROOT / "submodules/halo-ce-universal/port/ps2/port.json").read_text())
    closure_result = json.loads((build / "hcu-ps2-closure/all-no-bootstrap-memory/result.json").read_text())
    includes = ["-I" + str(ROOT / "submodules/halo-ce-universal" / item)
                for item in hcu_manifest["include_dirs"]]
    includes.extend(("-I" + str(prefix / "ps2sdk/common/include"),
                     "-I" + str(prefix / "ps2sdk/ee/include")))
    flags = list(closure_result["flags"])
    semantics = build / "hcu-ps2-closure/all-no-bootstrap-memory/halo_ps2_msvc_semantics.h"
    header = ROOT / "submodules/halo-ce-universal" / hcu_manifest["prefix"]
    compiler = prefix / "ee/bin/mips64r5900el-ps2-elf-gcc"
    command = [str(compiler), *flags, *includes, "-include", str(header),
               "-include", str(semantics), "-c", str(source), "-o", str(obj)]
    result = subprocess.run(command, cwd=ROOT, env=env, text=True,
                            capture_output=True)
    return {
        "status": "passed" if result.returncode == 0 else "failed",
        "schema_elf_sha256": sha256(schema_elf),
        "source_path": str(source.relative_to(ROOT)),
        "source_sha256": sha256(source),
        "object_path": str(obj.relative_to(ROOT)) if obj.exists() else None,
        "object_sha256": sha256(obj) if obj.exists() else None,
        "assertion_count": len(assertions),
        "compiler": subprocess.check_output([str(compiler), "--version"], text=True).splitlines()[0],
        "command": command,
        "diagnostics": result.stdout + result.stderr,
    }


def evidence_rows() -> list[dict]:
    def row(step, key, behavior, level, result, source, limitation, requirement):
        paths = []
        for token in source.split("; "):
            if token == "hcu_render_snapshot.h":
                candidate = ROOT / "src/stream/hcu_render_snapshot.h"
            elif token.startswith("config/"):
                candidate = ROOT / token
            elif (ROOT / token).is_file():
                candidate = ROOT / token
            else:
                candidate = ROOT / "docs/reports" / token
            paths.append({"path": str(candidate.relative_to(ROOT)),
                          "exists": candidate.is_file(),
                          "sha256": sha256(candidate) if candidate.is_file() else None})
        report_paths = [ROOT / item["path"] for item in paths
                        if item["exists"] and (ROOT / item["path"]).suffix.lower() == ".md"]
        core_maps = ("beavercreek", "bloodgulch", "boardingaction", "carousel", "chillout",
                     "damnation", "hangemhigh", "longest", "prisoner", "putput", "ratrace",
                     "sidewinder", "wizard")
        fixture_data, measurement_data = _normalized_report_data(report_paths, core_maps)
        # Test/harness source files cited directly by a core row are useful
        # build inputs even when there is no prose report to parse.
        for item in paths:
            candidate = ROOT / item["path"]
            if item["exists"] and candidate.suffix.lower() in {".py", ".c", ".h", ".json", ".inc"}:
                entry = {"reported_label": item["path"],
                         "role": "harness" if "test" in candidate.name.lower() or "fixture" in candidate.name.lower() else "source",
                         "sha256": item["sha256"], "local_path": item["path"],
                         "local_sha256": item["sha256"], "matches_current_file": True}
                fixture_data["input_hashes"].append(entry)
                target = "harness_hashes" if entry["role"] == "harness" else "source_hashes"
                fixture_data[target].append(entry)
        return {"step": step, "subcheck": key, "behavior_or_member": behavior,
                "owner": source, "evidence_level": level, "result": result,
                "evidence": source, "evidence_files": paths,
                # Evidence reports are hashed above, but are not themselves
                # fixture/input identities. Keep this distinction explicit:
                # the source-map corpus is pinned at ledger scope, while the
                # exact per-fixture hashes must be imported from each original
                # test manifest before this row can be qualified.
                "fixture_input_hashes": fixture_data,
                "measurements": measurement_data,
                "remaining_limitation": limitation,
                "acceptance_requirement": requirement}
    rows = [
        row(7, "bsp-inventory", "All serialized sbsp members and byte ranges", "source inspection",
            "partial", "m2-step7-bsp-member-inventory-2026-10-22.json; m2-step7-schema-gap-source-discovery-2026-10-22.json; m2-step7-schema-gap-layout-2026-10-22.json; m2-step7-schema-gap-dwarf-members-2026-10-22.json; m2-step7-bsp-range-member-layout-2026-10-22.json; m2-step7-eight-unmapped-exact-layout-2026-10-22.json; m2-step7-unclassified-range-dispositions-2026-10-22.json; m2-step7-bsp-consumer-crosswalk-2026-10-22.json; m2-step7-open-root-bsp-dispositions-2026-10-22.json; m2-step7-empty-bsp-fields-2026-10-22.json; m2-step7-bsp-collision-pvs-current-target-probe-2026-10-22.json; retail-bsp-cbsp-audit-c0-2026-10-22.json; tools/test_step7_bsp_zero_size_sentinels.py; tests/test_step7_unmapped_bsp_range_retention.py; tools/audit_step7_empty_bsp_fields.py; tools/audit_step7_unclassified_range_dispositions.py; tools/probe_step7_eight_unmapped_exact_layout.py",
            "All 82 BSPs across 24 audited maps round-trip with bytes preserved except declared normalizations; this proves serialized retention, not semantic disposition. Four of 12 omitted root members have source-backed dispositions, three CE behavior associations remain target-unverified, and eight *_unused ranges remain semantically open. Compiler-selected member extents cover all 54 nested schema-unrepresented ranges with zero uncovered byte intervals; all 54 semantic dispositions remain open. All 41 serialized block/data fields empty in at least one audited retail BSP have synthetic structural fixtures; consumer semantics remain unproven. Member-specific artifacts cover all 164 rows including three zero-size nonserialized check sentinels; behavioral fixtures name 58 rows. The paired PCSX2 target probe qualifies its named collision/PVS/path rows on 13 MP maps. None of these counts closes opaque byte semantics.",
            "Name every C member/range and classify every consumer or retained byte."),
        row(7, "synthetic-empty-retail-bsp-fields", "Synthetic structure for every serialized block/data field empty in any audited retail BSP", "host execution",
            "qualified", "m2-step7-empty-bsp-fields-2026-10-22.json; tools/audit_step7_empty_bsp_fields.py; tests/test_step7_synthetic_empty_bsp_fields.py",
            "Structural walker coverage only; the occupancy report explicitly does not prove field consumer semantics.",
            "Cover every empty-in-retail serialized field structurally and qualify each actual CE consumer separately."),
        row(7, "relocation-materialization", "CBSP relocation and byte parity", "host execution",
            "partial", "m2-step7-retail-cbsp-validation.md",
            "Exact materializer parity does not prove all CE consumers or production target ownership.",
            "Retain exact materialization plus CE consumer and failure qualification."),
        row(7, "late-failure", "Late BSP visitor failure, rollback, and retry", "host execution",
            "partial", "m2-step7-mp-cbsp-late-failure-atomicity-2026-10-22.md",
            "Covers the injected late visitor boundary; it is not every publication/relocation boundary.",
            "Exercise each distinct new failure boundary and prove owner/publication recovery."),
        row(7, "collision-pvs-query", "Collision and PVS on all 13 MP maps", "PCSX2 recompiler",
            "partial", "m2-step8-mp-13-map-pcsx2-query-2026-10-22.md",
            "Candidate diagnostic, selected query cases, no renderer submission or production profile.",
            "Qualify complete consumers under the production memory profile."),
        row(7, "collision-pvs-query-interpreter", "Collision and PVS on all 13 MP maps", "PCSX2 interpreter",
            "partial", "step8-mp-all-map-candidate-pcsx2-2026-10-22.md",
            "Candidate query/load/unload only; no rendered match.",
            "Rerun integrated renderer and workload on exact final build."),
        row(7, "fog-reference", "Valid and malformed fog references", "host execution",
            "partial", "m2-step7-mp-valid-fog-selection-all13-2026-10-22.md; m2-step7-mp-invalid-fog-reference-all13-2026-10-22.md",
            "scenario_fog_at_point attenuation is intentionally unresolved and not a closure gate.",
            "Preserve pinned HCU results; no Xbox attenuation equivalence claim."),
        row(7, "environment-consumers", "Weather, wind, sound environment, and sound scenery", "host execution",
            "partial", "m2-step7-mp-weather-particle-consumer-2026-10-22.md; m2-step7-mp-fogged-sound-environment-2026-10-22.md; m2-step7-mp-sound-scenery-runtime-2026-10-22.md",
            "Selection/runtime slices do not prove rendered weather or audible SPU2 playback.",
            "Qualify each consumer in the integrated path within its owning milestone."),
        row(7, "pathfinding-host", "CE A* and edge traversal on all 13 raw BSPs", "host execution",
            "partial", "m2-step7-mp-bot-pathfinding-2026-10-22.md",
            "Host adapter uses centroid projection and no live actor steering.",
            "Qualify object-backed paths, build/smooth, avoidance, progress, and recovery."),
        row(7, "pathfinding-guest", "CE A* on relocated BSPs across 13 maps", "PCSX2 recompiler",
            "partial", "m2-step7-mp-target-astar-2026-10-22.md",
            "Stops before live actor path build/steering; diagnostic candidate owner.",
            "Integrate with real actors and production-profile capacity."),
        row(7, "rendered-bsp", "BSP geometry, materials, lightmaps, and visible pixels", "not run",
            "not_run", "mp-step8-live-render-cache-stress-2026-10-22.md",
            "Host resource scans and CPU snapshots are not a framebuffer render.",
            "Capture actual integrated rendering in PCSX2 for all supported views."),
        row(7, "render-consumers", "Lens flare, detail objects, decals, surfaces and nested blocks", "host execution",
            "partial", "m2-step7-mp-lens-flare-consumer-all-maps-2026-10-22.md; m2-step7-mp-detail-object-consumer-2026-10-22.md; m2-step7-mp-sound-scenery-runtime-2026-10-22.md",
            "Per-consumer tests do not yet close every field or integrated presentation result.",
            "Tie every inventory member to consumer and parity/failure evidence."),
        row(8, "map-query-13", "Map preflight/load/query/unload on all 13 maps", "PCSX2 interpreter and recompiler",
            "partial", "step8-mp-all-map-candidate-pcsx2-2026-10-22.md",
            "Diagnostic capacity profile and query-only workload.",
            "Use a production profile with all required runtime owners and workloads."),
        row(8, "map-render-owner", "TEXS/LM/OTEX owner and texture-cache stress", "host execution",
            "partial", "mp-step8-live-render-cache-stress-2026-10-22.md",
            "Blood Gulch leaves 60,208 bytes; no GS submission, pins, transition overlap, weapon/HUD/effect closure, or EE measurement.",
            "Measure complete integrated source, upload, GS, and transition lifetimes."),
        row(8, "binder", "Production map/BSP/render partition", "host execution",
            "partial", "mp-step8-production-binder-ownership-2026-10-22.md",
            "Candidate binder arithmetic passes only in opt-in diagnostic; production default remains insufficient.",
            "Promote only a measured production carve with guarded owner assertions."),
        row(8, "local-players-4", "Four distinct local CE players and teardown", "PCSX2 interpreter and recompiler",
            "partial", "m2-step8-ce-four-local-player-workload-2026-10-22.md",
            "Sidewinder local-player-only sample; no AI actor records, bots, combat churn, or production-capacity proof.",
            "Add four Spartan bots and separately measured retail actor workloads."),
        row(8, "spartan-bots-4", "Four deterministic player-backed Spartan bots", "not run",
            "not_run", "m2-step8-ce-actor-workload-boundary.md; m2-step8-mp-vehicle-seat-actors-2026-10-22.md",
            "No in-scope Spartan bot controller or valid stock-MP retail actor placement is currently qualified.",
            "Implement and run four bots with CE actions, navigation, combat, scoring, and cleanup."),
        row(8, "retail-actor-workload", "Resolved retail combat variants in survival", "host ILP32 allocation fixture",
            "partial", "m2-step8-ce-actor-ilp32-attempt.md",
            "Synthetic variant/biped proves datum slots only; stock MP cache census has no usable actr roster.",
            "Import source-backed variants and execute real placement/AI/death/respawn."),
        row(8, "mixed-survival", "Retail actors and Spartan bots in endless waves", "not run",
            "not_run", "m2-step8-gameplay-workload-fixture-feasibility-2026-10-22.md",
            "No integrated survival mode, wave reuse, respawn/elimination, or mixed workload exists.",
            "Run repeated mixed waves under bounded storage and gameplay-hash invariance."),
        row(8, "production-owner-telemetry", "All EE owners, peaks, failure counts and reset", "partial host/PCSX2 diagnostics",
            "partial", "m2-step8-malloc-arena-telemetry-2026-10-22.md; m2-step8-game-state-object-pool-telemetry-2026-10-22.md",
            "Owners are measured separately in selected probes; combined renderer/gameplay production peak absent.",
            "Observe each owner concurrently over full map/mode transitions."),
        row(8, "dma-budget", "Renderer chains and snapshot DMA ownership", "source inspection",
            "blocked", "mp-step8-live-render-cache-stress-2026-10-22.md; hcu_render_snapshot.h",
            "Four renderer chains use all DMA bytes; separate snapshot DMA reservation remains.",
            "Remove snapshot DMA payload and emit directly into renderer-owned chains."),
        row(8, "timing", "Four-player/four-bot 30 Hz and render timing", "not run",
            "not_run", "m2-step8-gameplay-workload-fixture-feasibility-2026-10-22.md",
            "No bot/mixed workload EE tick and end-to-end timing evidence.",
            "Measure complete required workload; preserve 30 Hz and reserve."),
        row(8, "reserve", "5,767,168-byte reserve untouched", "source inspection",
            "partial", "config/memory-budget.json",
            "Budget specifies the reserve; each exact candidate ELF/profile still needs placement verification.",
            "Require non-overlap with reserve in every final guest run."),
    ]
    # Import metrics only from exact machine-readable artifacts with stable
    # JSON pointers. These document the measured slice; they do not promote
    # any row's acceptance result or imply workload-wide capacity.
    def add_json_metrics(subcheck: str, artifact: Path,
                         metrics: list[tuple[str, str, str, str]]) -> None:
        target = next(item for item in rows if item["subcheck"] == subcheck)
        values = target.setdefault("measurements", {}).setdefault("values", [])
        target["measurements"]["status"] = "normalized"
        target["measurements"]["limitation"] = (
            "Exact values are bound to a machine-readable artifact and JSON pointer; "
            "they describe only the named fixture/profile and do not establish broader acceptance.")
        for name, pointer, unit, derivation in metrics:
            value = json.loads(artifact.read_text())
            value = _json_pointer_value(value, pointer)
            values.append(_bound_measurement(name, value, unit, artifact, pointer, derivation))
        rel = str(artifact.relative_to(ROOT))
        if not any(item.get("path") == rel for item in target["evidence_files"]):
            target["evidence_files"].append({"path": rel, "exists": True, "sha256": sha256(artifact)})

    cbsp_metric_artifact = ROOT / "docs/reports/retail-bsp-cbsp-bloodgulch.json"
    if cbsp_metric_artifact.is_file():
        add_json_metrics("relocation-materialization", cbsp_metric_artifact, [
            ("materialized_bsp_bytes", "/structure_bsp/raw_and_cbsp_image_bytes", "bytes", "exact packaged source extent"),
            ("internal_relocation_fields", "/structure_bsp/bsp_internal_relocation_fields", "fields", "reported relocation field count"),
            ("typed_ctag_name_relocations", "/structure_bsp/typed_ctag_name_relocation_fields", "fields", "reported typed cross-image relocation count"),
            ("python_ps2_materializer_parity", "/round_trip/ps2_c_decoder_materializer_matches_python_fixture", "boolean", "direct artifact assertion"),
        ])
    binder_metric_artifact = ROOT / "build/mp-production-binder-capacity-1792695756835008376/manifest.json"
    if binder_metric_artifact.is_file():
        add_json_metrics("binder", binder_metric_artifact, [
            ("candidate_bsp_bytes", "/profile/candidate_bsp_bytes", "bytes", "candidate profile field"),
            ("candidate_tag_bytes", "/profile/candidate_tag_bytes", "bytes", "candidate profile field"),
            ("candidate_texture_bytes", "/profile/candidate_texture_bytes", "bytes", "candidate profile field"),
            ("candidate_total_bytes", "/profile/candidate_total_bytes", "bytes", "candidate profile field"),
        ])
    player_metric_artifact = ROOT / "build/hcu-step8-mp-workload/interpreter-result.json"
    if player_metric_artifact.is_file():
        add_json_metrics("local-players-4", player_metric_artifact, [
            ("local_player_count", "/assertions/local_players", "players", "exact guest assertion"),
            ("spawned_unit_count", "/assertions/spawned_units", "units", "exact guest assertion"),
            ("game_ticks", "/assertions/game_ticks", "ticks", "exact guest assertion"),
            ("game_state_high_water", "/assertions/game_state/high_water_bytes", "bytes", "exact guest owner snapshot"),
            ("game_state_failed_allocations", "/assertions/game_state/failed_allocations", "allocations", "exact guest owner snapshot"),
            ("object_pool_high_water", "/assertions/object_pool/high_water_bytes", "bytes", "exact guest owner snapshot"),
        ])
    add_json_metrics("reserve", ROOT / "config/memory-budget.json", [
        ("reserve_bytes", "/reserve_bytes", "bytes", "configured memory budget; not a physical placement measurement"),
    ])
    bsp_inventory_row = next(item for item in rows if item["subcheck"] == "bsp-inventory")
    bsp_inventory_row["fixture_input_hashes"]["status"] = "not_applicable"
    bsp_inventory_row["fixture_input_hashes"]["fixture_hashes"] = []
    bsp_inventory_row["fixture_input_hashes"]["limitation"] = (
        "This row is compiler/schema source inspection, not runtime execution; fixture applicability is explicitly not applicable. "
        "Every source, schema, audit, and test input is separately hash-pinned.")
    crosswalk_path = ROOT / "docs/reports/m2-step7-bsp-consumer-crosswalk-2026-10-22.json"
    crosswalk_data = json.loads(crosswalk_path.read_text()) if crosswalk_path.is_file() else {}
    inventory_data = json.loads((ROOT / "docs/reports/m2-step7-bsp-member-inventory-2026-10-22.json").read_text())
    # Keep exact source ownership/domain evidence for the eight ranges that have
    # no compiler-derived C member mapping. This supplements retention fixtures
    # without changing their still-open semantic disposition.
    range_map_path = ROOT / "docs/reports/m2-step7-eight-unmapped-range-source-map-2026-10-22.json"
    if range_map_path.is_file():
        range_map = json.loads(range_map_path.read_text())
        range_map_tool = ROOT / "tools/audit_step7_eight_unmapped_ranges.py"
        range_map_test = ROOT / "tests/test_step7_eight_unmapped_range_source_map.py"
        range_paths = {range_map_path, range_map_tool, range_map_test}
        range_paths.update(ROOT / item["source_path"] for item in range_map.get("ranges", []))
        existing_evidence = {item["path"]: item for item in bsp_inventory_row.get("evidence_files", [])}
        identity = bsp_inventory_row["fixture_input_hashes"]
        identity.setdefault("input_hashes", [])
        identity.setdefault("source_hashes", [])
        identity.setdefault("harness_hashes", [])
        for path in sorted(range_paths):
            if not path.is_file():
                continue
            rel = str(path.relative_to(ROOT))
            digest = sha256(path)
            if rel not in existing_evidence:
                bsp_inventory_row["evidence_files"].append({"path": rel, "exists": True, "sha256": digest})
                existing_evidence[rel] = bsp_inventory_row["evidence_files"][-1]
            else:
                existing_evidence[rel].update({"exists": True, "sha256": digest})
            role = "harness" if path == range_map_test or path == range_map_tool else "source"
            pin = {"reported_label": rel, "role": role, "sha256": digest,
                   "local_path": rel, "local_sha256": digest,
                   "matches_current_file": True, "purpose": "exact source member/serialized offset/pointer-domain map for eight unmapped ranges"}
            for category in ("input_hashes", "harness_hashes" if role == "harness" else "source_hashes"):
                category_pins = identity[category]
                prior = next((item for item in category_pins if item.get("local_path") == rel), None)
                if prior is None:
                    category_pins.append(pin.copy())
                else:
                    prior.update(pin)
        bsp_inventory_row["unmapped_range_source_map"] = {
            "path": str(range_map_path.relative_to(ROOT)), "sha256": sha256(range_map_path),
            "range_count": len(range_map.get("ranges", [])),
            "semantic_status": "open",
            "limitation": "Source declaration ownership and sibling index domains are documented; byte-preservation, pointer-domain validity, and target consumer semantics remain independent requirements."}
    bsp_inventory_row["measurements"] = {
        "status": "normalized",
        "values": [
            _bound_measurement("schema_inventory_rows", inventory_data["member_rows"], "rows",
                               ROOT / "docs/reports/m2-step7-bsp-member-inventory-2026-10-22.json", "/member_rows"),
            _bound_measurement("schema_definitions", len(inventory_data["definitions"]), "definitions",
                               ROOT / "docs/reports/m2-step7-bsp-member-inventory-2026-10-22.json", "/definitions", "count(keys)"),
            _bound_measurement("unclassified_byte_ranges", inventory_data["unclassified_ranges"], "ranges",
                               ROOT / "docs/reports/m2-step7-bsp-member-inventory-2026-10-22.json", "/unclassified_ranges"),
            _bound_measurement("ranges_with_compiled_member_overlap", crosswalk_data["coverage_summary"]["unclassified_rows_with_compiled_source_member_overlap"], "ranges",
                               crosswalk_path, "/coverage_summary/unclassified_rows_with_compiled_source_member_overlap"),
            _bound_measurement("rows_with_exact_member_artifact", crosswalk_data["coverage_summary"]["rows_with_any_exact_member_artifact"], "rows",
                               crosswalk_path, "/coverage_summary/rows_with_any_exact_member_artifact"),
            _bound_measurement("rows_with_behavior_fixture", crosswalk_data["coverage_summary"]["rows_with_exact_member_behavior_fixture"], "rows",
                               crosswalk_path, "/coverage_summary/rows_with_exact_member_behavior_fixture"),
            _bound_measurement("target_consumer_execution_rows", crosswalk_data["coverage_summary"]["current_target_execution_rows"], "rows",
                               crosswalk_path, "/coverage_summary/current_target_execution_rows"),
            *([_bound_measurement("unmapped_ranges_with_exact_source_map", len(range_map.get("ranges", [])), "ranges",
                                  range_map_path, "/ranges", "count(exact source ownership records)")] if range_map_path.is_file() else []),
        ],
        "limitation": "Counts are from compiler inventory and generated crosswalk; they do not imply semantic closure of unclassified ranges."}
    cbsp_audit_path = ROOT / "docs/reports/retail-bsp-cbsp-audit-c0-2026-10-22.json"
    cbsp_audit = json.loads(cbsp_audit_path.read_text()) if cbsp_audit_path.is_file() else {}
    schema_elf = ROOT / "build/hcu-ps2-closure/all-no-bootstrap-memory/halo-local.elf"
    audit_script = ROOT / "tools/audit_retail_bsp_schema.py"
    if cbsp_audit and schema_elf.is_file() and audit_script.is_file():
        map_inputs = [{"map": item["map"], "sha256": item["source_sha256"],
                       "bytes": item.get("source_bytes"), "role": "retail source-map fixture"}
                      for item in cbsp_audit.get("maps", []) if item.get("source_sha256")]
        cbsp_row = {
            "step": 7, "subcheck": "bsp-byte-preservation-24map-cbsp-roundtrip",
            "behavior_or_member": "Schema-owned BSP bytes and CBSP round-trip across audited stock/campaign/UI maps",
            "owner": "tools/audit_retail_bsp_schema.py",
            "evidence_level": "host execution", "result": "partial",
            "evidence": "retail-bsp-cbsp-audit-c0-2026-10-22.json",
            "evidence_files": [{"path": str(p.relative_to(ROOT)), "exists": p.is_file(),
                                 "sha256": sha256(p) if p.is_file() else None}
                                for p in (cbsp_audit_path, audit_script)],
            "fixture_input_hashes": {
                "status": "complete" if len(map_inputs) == cbsp_audit.get("map_count") else "partial",
                "fixture_hashes": map_inputs,
                "input_hashes": [
                    {"path": str(schema_elf.relative_to(ROOT)), "sha256": sha256(schema_elf),
                     "role": "compiler-derived schema ELF"},
                    {"path": str(audit_script.relative_to(ROOT)), "sha256": sha256(audit_script),
                     "role": "audit harness"}],
                "limitation": "Source-map identities bind the audited corpus; audit confirms byte retention except named schema normalizations, not consumer semantics."},
            "measurements": {"status": "normalized", "values": [
                _bound_measurement("maps_audited", cbsp_audit.get("map_count"), "maps",
                                   cbsp_audit_path, "/map_count"),
                _bound_measurement("BSPs_audited", cbsp_audit.get("structure_bsp_count"), "BSPs",
                                   cbsp_audit_path, "/structure_bsp_count"),
                _bound_measurement("CBSP_round_trip_failures", cbsp_audit.get("cbsp_round_trip_failure_count"), "failures",
                                   cbsp_audit_path, "/cbsp_round_trip_failure_count"),
                _bound_measurement("BSPs_over_current_capacity",
                                   cbsp_audit.get("raw_current_bsp_capacity_failures", 0), "BSPs",
                                   cbsp_audit_path, "/raw_current_bsp_capacity_failures")],
                "limitation": "Zero CBSP round-trip failures and byte-preservation checks do not establish member semantics or runtime consumer completeness."},
            "remaining_limitation": "Retention is qualified for this audit corpus only; 54 opaque nested ranges remain semantically unresolved.",
            "acceptance_requirement": "Preserve all bytes except documented schema normalizations and qualify every BSP consumer/failure path."}
        rows.append(cbsp_row)
    target_probe_path = ROOT / "docs/reports/m2-step7-bsp-collision-pvs-current-target-probe-2026-10-22.json"
    if target_probe_path.is_file():
        target_probe = json.loads(target_probe_path.read_text())
        target_runs = target_probe.get("runs", [])
        if len(target_runs) == 2 and all(r.get("status") == "passed" for r in target_runs):
            source_fixtures = {}
            package_fixtures = {}
            for run in target_runs:
                for item in run.get("map_inputs", []):
                    source_fixtures[item["source_map_path"]] = {
                        "path": item["source_map_path"], "map": item["map"],
                        "sha256": item["source_map_sha256"], "role": "retail map fixture"}
                    package_fixtures[item["package_path"]] = {
                        "path": item["package_path"], "map": item["map"],
                        "sha256": item["package_sha256"], "role": "mounted HP2 package"}
            source_inputs = [{"path": item["path"], "sha256": item["sha256"],
                              "role": "CE consumer source"}
                             for item in target_probe.get("code_inputs", [])]
            source_inputs += [
                {"path": target_probe["build_report_path"],
                 "sha256": target_probe["build_report_sha256"], "role": "parent/HCU build report"},
                {"path": target_probe["probe_source_path"],
                 "sha256": target_probe["probe_source_sha256"], "role": "guest probe source"},
                {"path": target_probe["recorder_path"],
                 "sha256": target_probe["recorder_sha256"], "role": "evidence verifier"},
                {"path": target_runs[0]["collision_oracle_path"],
                 "sha256": target_runs[0]["collision_oracle_sha256"], "role": "independent collision oracle"}]
            log_inputs = []
            executable_inputs = [{"path": run["elf_path"], "sha256": run["elf_sha256"],
                                  "role": f"{run['mode']} guest ELF"} for run in target_runs]
            for run in target_runs:
                executable_inputs.append({"path": run.get("emulator_path", "PCSX2"),
                                          "sha256": run["emulator_sha256"],
                                          "role": f"{run['mode']} PCSX2 executable"})
                log_inputs.append({"path": str(Path(run["run_directory"]) / "result.json"),
                                   "sha256": run["result_sha256"],
                                   "role": f"{run['mode']} runner result"})
                for key, role in (("guest_log_path", "guest log"),
                                  ("path_validation_path", "path validator result")):
                    if run.get(key) and run.get(key.replace("_path", "_sha256")):
                        log_inputs.append({"path": run[key],
                                           "sha256": run[key.replace("_path", "_sha256")],
                                           "role": f"{run['mode']} {role}"})
                log_inputs.extend([
                    {"path": run.get("bios_path", "PCSX2 BIOS"), "sha256": run["bios_sha256"],
                     "role": f"{run['mode']} BIOS"},
                    {"path": run.get("settings_path", "PCSX2 settings"),
                     "sha256": run["settings_sha256"], "role": f"{run['mode']} settings"}])
            total_pvs = {run["mode"]: sum(item["pvs_rows_queried"] for item in run["query_rows"])
                         for run in target_runs}
            rows.append({
                "step": 7, "subcheck": "current-target-bsp-collision-pvs-path-13map",
                "behavior_or_member": "CE collision hit/material, full per-map cluster PVS, CE A* route and unload guard on all stock MP maps",
                "owner": "tools/test_hcu_step7_path_guest.py + tools/record_step7_bsp_target_probe.py",
                "evidence_level": "PCSX2 interpreter and recompiler",
                "result": "partial",
                "evidence": "m2-step7-bsp-collision-pvs-current-target-probe-2026-10-22.json",
                "execution_results": [{"mode": run["mode"], "result": "partial",
                                       "reported_result": run["status"],
                                       "elf_path": run["elf_path"], "elf_sha256": run["elf_sha256"],
                                       "settings_sha256": run["settings_sha256"],
                                       "limitation": "Historical settings bytes unavailable; reported query success is retained without exact-run qualification."}
                                      for run in target_runs],
                "evidence_files": [{"path": str(path.relative_to(ROOT)), "exists": path.is_file(),
                                    "sha256": sha256(path) if path.is_file() else None}
                                   for path in (target_probe_path,
                                                ROOT / "docs/reports/m2-step7-bsp-collision-pvs-current-target-probe-2026-10-22.md")],
                "fixture_input_hashes": {
                    "status": "complete" if all(len(run.get("map_inputs", [])) == 13 for run in target_runs) else "partial",
                    "fixture_hashes": list(source_fixtures.values()) + list(package_fixtures.values()),
                    "input_hashes": source_inputs,
                    "executable_hashes": executable_inputs,
                    "log_hashes": log_inputs,
                    "limitation": "Exact diagnostic ELF/profile, emulator, BIOS, settings, source maps, packages, source and logs are pinned; this profile does not qualify renderer, bots, production memory admission, or hardware."},
                "measurements": {
                    "status": "normalized",
                    "values": [
                        _bound_measurement(f"{run['mode']}_maps", len(run["query_rows"]), "maps",
                                           target_probe_path, f"/runs/{index}/query_rows", "count")
                        for index, run in enumerate(target_runs)] +
                              [_bound_measurement(f"{run['mode']}_cluster_pvs_rows", total_pvs[run["mode"]], "rows",
                                                  target_probe_path, f"/runs/{index}/query_rows/*/pvs_rows_queried", "sum")
                               for index, run in enumerate(target_runs)] +
                              [_bound_measurement(f"{run['mode']}_collision_hits", sum(q["collision_hit"] for q in run["query_rows"]), "hits",
                                                  target_probe_path, f"/runs/{index}/query_rows/*/collision_hit", "sum")
                               for index, run in enumerate(target_runs)] +
                              [_bound_measurement(f"{run['mode']}_A_star_routes", run["path_rows"], "routes",
                                                  target_probe_path, f"/runs/{index}/path_rows")
                               for index, run in enumerate(target_runs)] +
                              [_bound_measurement(f"{run['mode']}_unload_guard_passes", run["unload_guard_rows"], "maps",
                                                  target_probe_path, f"/runs/{index}/unload_guard_rows")
                               for index, run in enumerate(target_runs)],
                    "limitation": "Measured diagnostic query behavior only; no visual rendering, bot workload, or physical-console qualification."},
                "remaining_limitation": "Reported query runs passed, but both historical emulator settings files are unavailable, so exact-run qualification remains partial. Only the listed diagnostic consumers were exercised; other inventory consumers remain open.",
                "acceptance_requirement": "Run exact target consumers on all stock maps in interpreter/recompiler and verify oracle, PVS bounds, paths, cleanup and guards."})
    schema_hash = sha256(SCHEMA_DEFAULT) if SCHEMA_DEFAULT.is_file() else None
    synthetic_test = ROOT / "tests/test_step7_synthetic_empty_bsp_fields.py"
    synthetic_row = next(item for item in rows
                         if item["subcheck"] == "synthetic-empty-retail-bsp-fields")
    empty_field_report_path = ROOT / "docs/reports/m2-step7-empty-bsp-fields-2026-10-22.json"
    empty_field_report = json.loads(empty_field_report_path.read_text())
    synthetic_row["fixture_input_hashes"] = {
        "status": "complete",
        "fixture_hashes": [{"field": field["path"],
                            "sha256": field["synthetic_fixture"]["sha256"],
                            "bytes": field["synthetic_fixture"]["image_bytes"],
                            "recipe": field["synthetic_fixture"]["construction_recipe"],
                            "role": "synthetic nonempty structural fixture"}
                           for field in empty_field_report["fields"]
                           if field["retail_empty_bsp_count"] > 0],
        "input_hashes": [{"path": str(synthetic_test.relative_to(ROOT)),
                           "sha256": sha256(synthetic_test)},
                          {"path": str(empty_field_report_path.relative_to(ROOT)),
                           "sha256": sha256(empty_field_report_path)},
                          {"path": str((ROOT / "tools/audit_step7_empty_bsp_fields.py").relative_to(ROOT)),
                           "sha256": sha256(ROOT / "tools/audit_step7_empty_bsp_fields.py")},
                          {"path": str(SCHEMA_DEFAULT.relative_to(ROOT)),
                           "sha256": schema_hash}],
        "limitation": "These fixtures establish structural walking, extent, payload retention, normalization, and truncation handling; they do not establish CE consumer semantics."}
    synthetic_row["measurements"] = {
        "status": "normalized",
        "values": [_bound_measurement("serialized_block_data_fields", empty_field_report["serialized_block_and_data_field_count"], "fields",
                                       empty_field_report_path, "/serialized_block_and_data_field_count"),
                   _bound_measurement("fields_empty_in_any_retail", len(empty_field_report["empty_in_any_retail"]), "fields",
                                      empty_field_report_path, "/empty_in_any_retail", "count") ,
                   _bound_measurement("fields_empty_in_all_audited_BSPs", len(empty_field_report["empty_across_retail"]), "fields",
                                      empty_field_report_path, "/empty_across_retail", "count")],
        "limitation": "Host structural tests only; no guest/runtime consumer qualification."}
    return rows


def _swarm_hash_role(label: str) -> str:
    lower = label.lower()
    if ".hp2" in lower or "package" in lower:
        return "package"
    if any(token in lower for token in ("test", "harness", "bridge", "_main.c", "host_stubs")):
        return "harness"
    if any(token in lower for token in ("fixture", "synthetic", "raw map", "raw bsp")):
        return "fixture"
    if ".map" in lower or "inventory" in lower:
        return "input"
    if any(token in lower for token in ("source", ".c", ".h", ".py", ".json", ".vsm", ".inc")):
        return "source"
    if any(token in lower for token in ("bin/", " executable", "elf", "host", "drive", "ps2")):
        return "executable"
    if any(token in lower for token in ("log", "stdout", "stderr")):
        return "log"
    return "unclassified"


def _report_maps(content: str, maps: tuple[str, ...]) -> tuple[list[str], bool]:
    display = {"beavercreek": r"beaver\s*creek", "boardingaction": r"boarding\s*action",
               "chillout": r"chill\s*out", "hangemhigh": r"hang(?:\s*|'|’)em\s*high",
               "ratrace": r"rat\s*race"}
    patterns = {name: display.get(name, re.escape(name)) for name in maps}
    found = [name for name in maps if re.search(rf"(?i)\b(?:{patterns[name]})\b", content)]
    excluded = {name for name in found if any(
        re.search(rf"(?i)\b(?:{patterns[name]})\b", line) and re.search(r"(?i)not this slice|not run", line)
        for line in content.splitlines())}
    found = [name for name in found if name not in excluded]
    all13 = len(found) == 13 or (bool(re.search(r"(?i)all[ -]+13\b", content)) and not excluded)
    if all13:
        found = list(maps)
    return found, all13


def _normalized_report_data(report_paths: list[Path], maps: tuple[str, ...]) -> tuple[dict, dict]:
    map_fixtures_by_name = {p.stem.lower(): p for p in
                            (ROOT / "build/retail-maps/decompressed").glob("*.map")
                            if p.stem.lower() in maps}
    fixture_hashes, input_hashes = [], []
    source_hashes, harness_hashes, executable_hashes, log_hashes, reported_pins = [], [], [], [], []
    metric_values = []
    verbatim_values = []
    complete_scopes = 0
    for report in report_paths:
        if not report.is_file():
            continue
        content = report.read_text(errors="replace")
        report_maps, _all13 = _report_maps(content, maps)
        report_map_fixtures = [{"map": name, "path": str(map_fixtures_by_name[name].relative_to(ROOT)),
                                "sha256": sha256(map_fixtures_by_name[name]),
                                "bytes": map_fixtures_by_name[name].stat().st_size,
                                "role": "fixture"} for name in report_maps if name in map_fixtures_by_name]
        raw_source_claim = bool(re.search(r"(?i)raw|decompressed|source map|source BSP|Xbox BSP", content))
        # Prefer a retained run manifest's per-map source hash when the report
        # names a run directory. This provides exact identity even when the
        # prose says only "all pinned stock maps".
        dirs = re.findall(r"(?im)^\s*-?\s*Directory\s*:\s*(build/[^\s`]+)", content)
        manifests = []
        for text_path in re.findall(r"(?<![\w.])((?:\.\.?/)*build/[\w./-]+\.json)", content):
            parts = Path(text_path).parts
            if "build" in parts:
                manifests.append(ROOT.joinpath(*parts[parts.index("build"):]))
        for dirname in dirs:
            run_dir = ROOT / dirname.rstrip("/")
            manifests.extend([run_dir / "manifest.json", run_dir / "result.json"])
        manifest_pins = {}
        for manifest_path in manifests:
            if not manifest_path.is_file():
                continue
            try:
                manifest_data = json.loads(manifest_path.read_text())
            except (OSError, json.JSONDecodeError):
                continue
            def visit(value):
                if isinstance(value, dict):
                    name = value.get("map") or value.get("name")
                    digest = value.get("source_sha256") or value.get("source_map_sha256")
                    if name and digest and str(name).lower() in report_maps:
                        manifest_pins[str(name).lower()] = {"sha256": str(digest).lower(),
                                                             "manifest_path": str(manifest_path.relative_to(ROOT)),
                                                             "manifest_sha256": sha256(manifest_path)}
                    for child in value.values(): visit(child)
                elif isinstance(value, list):
                    for child in value: visit(child)
            visit(manifest_data)
        for fixture in report_map_fixtures:
            pin = manifest_pins.get(fixture["map"])
            if pin:
                fixture["manifest_path"] = pin["manifest_path"]
                fixture["manifest_sha256"] = pin["manifest_sha256"]
                fixture["report_manifest_source_sha256"] = pin["sha256"]
                fixture["matches_report_manifest"] = fixture["sha256"] == pin["sha256"]
        manifest_scope_complete = (bool(report_maps) and len(manifest_pins) == len(report_maps)
                                   and all(manifest_pins[name]["sha256"] == sha256(map_fixtures_by_name[name])
                                           for name in report_maps if name in map_fixtures_by_name))
        if report_maps and len(report_map_fixtures) == len(report_maps) and (raw_source_claim or manifest_scope_complete):
            complete_scopes += 1
            fixture_hashes.extend(report_map_fixtures)
        # Only normalize cells from Markdown tables whose column header names
        # an unambiguous count/quantity or unit. Free-form prose and cells
        # without a declared unit remain verbatim; numeric tokens are never
        # assigned semantics based on their magnitude or neighboring text.
        normalized = _markdown_table_measurements(report, content)
        metric_values.extend(normalized)
        for line_number, line in enumerate(content.splitlines(), 1):
            # Markdown table rows place labels and digests in separate cells.
            # Keep label extraction inside the digest cell and skip separator
            # rows so table formatting cannot create phantom hash pins.
            table_cells = line.split("|") if "|" in line else None
            table_separator = bool(table_cells) and all(
                not cell.strip() or re.fullmatch(r":?-{3,}:?", cell.strip())
                for cell in table_cells
            )
            if table_separator:
                continue
            digest_matches = list(re.finditer(r"(?i)([0-9a-f]{64})", line))
            path_matches = list(re.finditer(
                r"(?<![A-Za-z0-9])((?:(?:\.\./)+)?(?:build|docs|tools|tests|src|submodules|config)/[A-Za-z0-9_./:@+-]+)",
                line))
            for match in digest_matches:
                digest = match.group(1).lower()
                nearest_path = min(path_matches, key=lambda item: abs(item.start() - match.start())) if path_matches else None
                token = nearest_path.group(1).rstrip(")],;:") if nearest_path else ""
                token = token.split("#", 1)[0]
                if table_cells:
                    cell_start = line.rfind("|", 0, match.start()) + 1
                    cell_end = line.find("|", match.end())
                    if cell_end < 0:
                        cell_end = len(line)
                    cell_index = line.count("|", 0, cell_start)
                    current_cell = line[cell_start:cell_end]
                    label = current_cell[:match.start() - cell_start].strip(" `*:_-")
                    if not label:
                        previous = [cell.strip(" `*:_-") for cell in table_cells[:cell_index]
                                    if cell.strip(" `*:_-")]
                        label = previous[-1] if previous else ""
                    label = label or (token or None)
                else:
                    label = line[max(0, match.start() - 160):match.start()].strip(" -|:*`\t") or (token or None)
                    label = re.split(r"[;\n]", label or "")[-1].strip(" -|:*`\t") or (token or None)
                # When one prose/table cell lists several labeled digests,
                # bound each digest to the immediately preceding label segment
                # rather than copying the entire tail of the line.
                if not (table_cells and len(digest_matches) == 1):
                    prior_digest = max((item.end() for item in digest_matches if item.end() <= match.start()), default=-1)
                    segment_start = prior_digest if prior_digest >= 0 else max(0, match.start() - 160)
                    segment = line[segment_start:match.start()].strip(" -|:*`\t")
                    if segment:
                        label = segment[-120:]
                if not table_cells:
                    label = re.split(r"[;.]", label or "")[-1].strip(" -|:*`\t") or (token or None)
                    role_match = re.search(
                        r"(?i)((?:recompiler|interpreter)\s+(?:result(?:/guest-log)?|guest-log)|(?:runner JSON|guest log|BIOS|PCSX2 executable|diagnostic ELF|build report))\s+SHA-256\s*$",
                        line[:match.start()])
                    if role_match:
                        label = role_match.group(1)
                candidates = []
                if token:
                    token_path = Path(token)
                    candidates.append(token_path if token_path.is_absolute() else report.parent / token_path)
                    if not token.startswith("../"):
                        candidates.append(ROOT / token)
                local = next((p.resolve() for p in candidates if p.is_file()), None)
                # If the report names only a role (for example "C fixture
                # SHA-256"), bind the digest to a current harness/source file
                # only when its exact bytes identify one file, or when the
                # printed label supplies a matching basename.
                if not local:
                    indexed = _report_pin_source_index().get(digest, [])
                    label_names = re.findall(r"[A-Za-z0-9_.-]+\.(?:c|h|py|mk|json|inc)", label or "")
                    narrowed = [name for name in indexed if any(Path(name).name == wanted for wanted in label_names)]
                    selected = narrowed if narrowed else indexed if len(indexed) == 1 else []
                    if len(selected) == 1:
                        local = (ROOT / selected[0]).resolve()
                local_in_root = bool(local and local.is_relative_to(ROOT))
                entry = {"reported_label": label, "role": _swarm_hash_role(label or token),
                         "sha256": digest,
                         "local_path": str(local.relative_to(ROOT)) if local_in_root else None,
                         "local_sha256": sha256(local) if local else None,
                         "identity_resolution": "exact-current-source-file" if local_in_root else "unresolved",
                         "matches_current_file": bool(local and sha256(local) == digest)}
                reported_pins.append(entry)
                role = entry["role"]
                if role == "fixture": fixture_hashes.append(entry)
                elif role in ("input", "package", "source", "harness"): input_hashes.append(entry)
                if role == "source": source_hashes.append(entry)
                elif role == "harness": harness_hashes.append(entry)
                elif role == "executable": executable_hashes.append(entry)
                elif role == "log": log_hashes.append(entry)
            if ("|" in line and re.search(r"\d", line)) or re.search(
                r"(?i)\b(count|counts|tests|subtests|maps|queries|samples|calls|bytes|result|digest|peak|limit|maximum|total|size|high-water|elapsed|seconds)\b.*\d|\d.*\b(count|tests|subtests|maps|queries|samples|calls|bytes|result|peak|limit|maximum|total|size|high-water|elapsed|seconds)\b", line):
                nums = re.findall(r"(?<![A-Za-z])[-+]?\d+(?:\.\d+)?", line)
                verbatim_values.append({"source_report": str(report.relative_to(ROOT)),
                                        "source_line": line_number,
                                        "raw": line.strip(),
                                        "numeric_tokens": nums,
                                        "unit_status": "verbatim_only"})
    fixture_status = "complete" if complete_scopes == len(report_paths) and report_paths else "partial"
    fixture = {"status": fixture_status, "fixture_hashes": fixture_hashes,
               "input_hashes": input_hashes, "source_hashes": source_hashes,
               "harness_hashes": harness_hashes, "executable_hashes": executable_hashes,
               "log_hashes": log_hashes, "reported_hash_pins": reported_pins,
               "limitation": "Exact map fixture hashes bind only report-declared raw/decompressed stock-map scope; all printed input pins are kept by role."}
    measurement = {"status": "normalized" if metric_values else "verbatim_only" if verbatim_values else "incomplete",
                   "values": metric_values,
                   "verbatim_lines": verbatim_values,
                   "limitation": "Normalized values come only from table cells with an explicit unit/count in the header. Other numeric lines remain verbatim and are not promoted."}
    return fixture, measurement


_TABLE_UNITS = (
    (re.compile(r"\bbytes?\b", re.I), "bytes"),
    (re.compile(r"\bpages?\b", re.I), "pages"),
    (re.compile(r"\b(?:pvs\s+)?rows?\b", re.I), "rows"),
    (re.compile(r"\bclusters\b", re.I), "clusters"),
    (re.compile(r"\bentries\b", re.I), "entries"),
    (re.compile(r"\brefs?\b", re.I), "references"),
    (re.compile(r"\bguards?\b", re.I), "guards"),
    (re.compile(r"\bnodes?\b", re.I), "nodes"),
    (re.compile(r"\ballocations?\b", re.I), "allocations"),
    (re.compile(r"\bresources?\b", re.I), "resources"),
    (re.compile(r"\buploads?\b", re.I), "uploads"),
    (re.compile(r"\bhits?\b", re.I), "hits"),
    (re.compile(r"\bdeferred\b", re.I), "deferred"),
    (re.compile(r"\bfull\b", re.I), "full"),
    (re.compile(r"\bqueries\b", re.I), "queries"),
    (re.compile(r"\bsamples?\b", re.I), "samples"),
    (re.compile(r"\bcalls?\b", re.I), "calls"),
    (re.compile(r"\btests?\b", re.I), "tests"),
    (re.compile(r"\bmaps?\b", re.I), "maps"),
    (re.compile(r"\brecords?\b", re.I), "records"),
    (re.compile(r"\bsurfaces\b", re.I), "surfaces"),
    (re.compile(r"\bparts?\b", re.I), "parts"),
)


def _markdown_table_measurements(report: Path, content: str) -> list[dict]:
    """Extract conservative name/value/unit tuples from explicitly-unitized tables."""
    lines = content.splitlines()
    values = []
    for index in range(len(lines) - 2):
        header = lines[index].strip()
        separator = lines[index + 1].strip()
        if not (header.startswith("|") and separator.startswith("|") and
                re.fullmatch(r"\|?\s*:?-{3,}:?\s*(?:\|\s*:?-{3,}:?\s*)+\|?", separator)):
            continue
        columns = [cell.strip().strip(" `") for cell in header.strip("|").split("|")]
        if len(columns) < 2:
            continue
        column_units = []
        for column_index, title in enumerate(columns):
            unit = next((unit for pattern, unit in _TABLE_UNITS if pattern.search(title)), None)
            # Hashes, labels, datums, coordinates, and arbitrary numeric
            # columns intentionally have no inferred unit.
            if re.search(r"(?i)sha-?256|datum|\(x|\(y|\(z|priority|type", title):
                unit = None
            column_units.append(unit)
        for row_index in range(index + 2, len(lines)):
            line = lines[row_index].strip()
            if not line.startswith("|"):
                break
            cells = [cell.strip().strip(" `") for cell in line.strip("|").split("|")]
            if len(cells) != len(columns):
                continue
            entity = cells[0]
            for column_index, (title, cell, unit) in enumerate(zip(columns, cells, column_units)):
                if unit is None or not cell or cell in {"-", "—", "n/a", "none"}:
                    continue
                # Scalar values and explicit high-water/capacity or x/y
                # pairs are normalized. Composite prose (e.g. "29 / 29")
                # is retained rather than guessed at.
                scalar = re.fullmatch(r"\d+(?:\.\d+)?", cell.replace(",", ""))
                pair = re.fullmatch(r"([\d,]+)\s*/\s*([\d,]+)", cell)
                if scalar:
                    values.append({"name": re.sub(r"[^a-z0-9]+", "_", title.lower()).strip("_"),
                                   "value": float(scalar.group()) if "." in scalar.group() else int(scalar.group()),
                                   "unit": unit, "entity": entity,
                                   "source_report": str(report.relative_to(ROOT)),
                                   "source_report_sha256": sha256(report),
                                   "source_line": row_index + 1, "source_column": title})
                elif pair and re.search(r"(?i)high.?water.*cap|/\s*cap", title):
                    for name, raw_value in (("high_water", pair.group(1)), ("capacity", pair.group(2))):
                        values.append({"name": f"{re.sub(r'[^a-z0-9]+', '_', title.lower()).strip('_')}_{name}",
                                       "value": int(raw_value.replace(",", "")), "unit": unit,
                                       "entity": entity, "source_report": str(report.relative_to(ROOT)),
                                       "source_report_sha256": sha256(report),
                                       "source_line": row_index + 1, "source_column": title})
                elif pair:
                    base_name = re.sub(r"[^a-z0-9]+", "_", title.lower()).strip("_")
                    for suffix, raw_value in (("value", pair.group(1)), ("total", pair.group(2))):
                        values.append({"name": f"{base_name}_{suffix}",
                                       "value": int(raw_value.replace(",", "")), "unit": unit,
                                       "entity": entity, "source_report": str(report.relative_to(ROOT)),
                                       "source_report_sha256": sha256(report),
                                       "source_line": row_index + 1, "source_column": title})
    return values


def swarm_evidence_rows() -> list[dict]:
    """Import existing swarm reports at their original, narrow evidence scope."""
    maps = ("beavercreek", "bloodgulch", "boardingaction", "carousel", "chillout",
            "damnation", "hangemhigh", "longest", "prisoner", "putput", "ratrace",
            "sidewinder", "wizard")
    source_map_root = ROOT / "build/retail-maps/decompressed"
    stock_map_files = {path.stem.lower(): path for path in source_map_root.glob("*.map")
                       if path.stem.lower() in maps} if source_map_root.is_dir() else {}
    rows = []
    for report in sorted((ROOT / "build/step7-swarm").glob("*/report.md")):
        content = report.read_text(errors="replace")
        slug = report.parent.name
        status_match = re.search(r"(?im)^\s*(?:disposition|status)\s*:\s*([^\n]+)", content)
        if status_match:
            original_status = status_match.group(1).strip(" *.:`")
        elif re.search(r"(?i)\bpass\b", "\n".join(content.splitlines()[:8])):
            original_status = "PASS (report text)"
        else:
            original_status = "unspecified"
        # Every report documents executed or source-inspected work; a limit
        # saying one sub-path was not run must not erase the report's result.
        result = "not_run" if original_status.lower().startswith(("not run", "not_run")) else "partial"
        report_level = "host execution" if re.search(r"(?i)host|ilp32|32-bit|executed|compiled|reproduction", content) else "source inspection"
        if re.search(r"(?i)(?:PCSX2.{0,80}\b(?:passed|pass|ran|run|result)\b|\b(?:passed|pass|ran|run)\b.{0,80}PCSX2)", content):
            report_level = "PCSX2 (diagnostic claim only; see report)"
        scoped_maps, declares_all_13 = _report_maps(content, maps)
        map_fixtures = [{"map": name, "path": str(stock_map_files[name].relative_to(ROOT)),
                         "sha256": sha256(stock_map_files[name]),
                         "bytes": stock_map_files[name].stat().st_size,
                         "role": "fixture"} for name in scoped_maps if name in stock_map_files]
        source_map_fixture_complete = (bool(scoped_maps) and len(map_fixtures) == len(scoped_maps)
                                       and bool(re.search(r"(?i)raw|decompressed|source map|source BSP|Xbox BSP", content)))
        pins = []
        for line in content.splitlines():
            match = re.search(r"(?i)([0-9a-f]{64})", line)
            if not match:
                continue
            digest = match.group(1).lower()
            label = line[:match.start()].strip(" -`|:*\t")
            token = label.strip(" `'")
            if token and not token.startswith(("build/", "tests/", "source/", "port/")):
                token = token.split()[-1].strip(" `'")
            candidates = [ROOT / token, report.parent / token] if token else []
            local = next((p for p in candidates if p.is_file()), None)
            role = _swarm_hash_role(label)
            pins.append({"reported_label": label or None, "role": role, "sha256": digest,
                         "local_path": str(local.relative_to(ROOT)) if local and local.is_relative_to(ROOT) else None,
                         "local_sha256": sha256(local) if local else None,
                         "matches_current_file": bool(local and sha256(local) == digest)})
        metrics = _markdown_table_measurements(report, content)
        verbatim_metrics = []
        for line_number, line in enumerate(content.splitlines(), 1):
            if ("|" in line and re.search(r"\d", line)) or re.search(
                r"(?i)\b(count|counts|tests|subtests|maps|queries|samples|calls|bytes|result|digest|peak|limit|maximum|total)\b.*\d|\d.*\b(count|tests|subtests|maps|queries|samples|calls|bytes|result|peak|limit|maximum|total)\b", line):
                nums = re.findall(r"(?<![A-Za-z])[-+]?\d+(?:\.\d+)?", line)
                verbatim_metrics.append({"source_report": str(report.relative_to(ROOT)),
                                         "source_line": line_number, "raw": line.strip(),
                                         "numeric_tokens": nums,
                                         "unit_status": "verbatim_only"})
        rows.append({"step": 7, "subcheck": f"swarm-{slug}",
                     "behavior_or_member": f"Existing Step 7 consumer slice ({slug})",
                     "owner": str(report.relative_to(ROOT)), "evidence_level": report_level,
                     "result": result, "evidence": str(report.relative_to(ROOT)),
                     "evidence_files": [{"path": str(report.relative_to(ROOT)), "exists": True,
                                         "sha256": sha256(report)}],
                     "fixture_scope": {"maps_named_in_report": scoped_maps,
                                       "all_13_maps_explicit": declares_all_13,
                                       "map_names_enumerated": len(scoped_maps) == 13,
                                       "scope_excerpt": " ".join(x.strip() for x in content.splitlines()[:18] if x.strip())[:1200]},
                     "fixture_input_hashes": {"status": "complete" if source_map_fixture_complete else "partial",
                                              "reported_hash_pins": pins,
                                              "fixture_hashes": map_fixtures + [p for p in pins if p["role"] == "fixture"],
                                              "input_hashes": [p for p in pins if p["role"] in ("input", "package", "harness", "source")],
                                              "source_hashes": [p for p in pins if p["role"] == "source"],
                                              "harness_hashes": [p for p in pins if p["role"] == "harness"],
                                              "executable_hashes": [p for p in pins if p["role"] == "executable"],
                                              "log_hashes": [p for p in pins if p["role"] == "log"],
                                              "limitation": "Map fixtures are bound to the exact decompressed source-map files for the report's declared scope. Other fixture identities remain incomplete unless printed by the report."},
                     "measurements": {"status": "normalized" if metrics else "verbatim_only" if verbatim_metrics else "incomplete",
                                      "values": metrics, "verbatim_lines": verbatim_metrics,
                                      "limitation": "Only unit-explicit table cells are normalized. Other numeric lines remain verbatim and are not promoted."},
                     "original_status": original_status,
                     "remaining_limitation": "Supporting evidence only; no broader BSP-consumer, rendering, target-capacity, or Step 7 acceptance is inferred.",
                     "acceptance_requirement": "Retain this consumer slice at its original report scope."})
    return rows


def step8_report_rows() -> list[dict]:
    """Import existing Step 8 diagnostics without broadening their claims."""
    stock_maps = ("beavercreek", "bloodgulch", "boardingaction", "carousel", "chillout",
                  "damnation", "hangemhigh", "longest", "prisoner", "putput", "ratrace",
                  "sidewinder", "wizard")
    candidates = set((ROOT / "docs/reports").glob("m2-step8-*.md"))
    candidates.update((ROOT / "docs/reports").glob("mp-step8-*.md"))
    candidates.update((ROOT / "docs/reports").glob("step8-mp-*.md"))
    excluded = ("review", "next-action", "capacity-next-action", "step10-capacity")
    rows = []
    for report in sorted(path for path in candidates if not any(token in path.name for token in excluded)):
        content = report.read_text(errors="replace")
        slug = re.sub(r"[^a-z0-9]+", "-", report.stem.lower()).strip("-")
        scope_maps, all13 = _report_maps(content, stock_maps)
        fixture_data, measurement_data = _normalized_report_data([report], stock_maps)
        status_match = re.search(r"(?im)^\s*(?:disposition|status)\s*:\s*([^\n]+)", content)
        original_status = status_match.group(1).strip(" *.:`") if status_match else "unspecified"
        has_guest_run = bool(re.search(r"(?i)PCSX2", content) and re.search(r"(?i)\b(passed|pass|ran|run|rerun|attempt)\b", content))
        if has_guest_run and re.search(r"(?i)\binterpreter\b", content) and re.search(r"(?i)\brecompiler\b", content):
            level = "PCSX2 interpreter and recompiler"
        elif has_guest_run and re.search(r"(?i)\binterpreter\b", content):
            level = "PCSX2 interpreter"
        elif has_guest_run and re.search(r"(?i)\brecompiler\b", content):
            level = "PCSX2 recompiler"
        elif re.search(r"(?i)host|ILP32|32-bit|executed|compiled|reproduction", content):
            level = "host execution"
        else:
            level = "source inspection"
        rows.append({"step": 8, "subcheck": f"report-{slug}",
                     "behavior_or_member": f"Existing Step 8 report at source scope: {report.stem}",
                     "owner": str(report.relative_to(ROOT)), "evidence": str(report.relative_to(ROOT)),
                     "evidence_files": [{"path": str(report.relative_to(ROOT)),
                                         "exists": True, "sha256": sha256(report)}],
                     "evidence_level": level, "result": "partial",
                     "fixture_scope": {"maps_named_in_report": scope_maps,
                                       "all_13_maps_explicit": all13,
                                       "map_names_enumerated": len(scope_maps) == 13,
                                       "scope_excerpt": " ".join(x.strip() for x in content.splitlines()[:18] if x.strip())[:1200]},
                     "fixture_input_hashes": fixture_data,
                     "measurements": measurement_data,
                     "original_status": original_status,
                     "remaining_limitation": "Imported only at the report's stated workload, artifact, and evidence level; no Step 8 acceptance is inferred.",
                     "acceptance_requirement": "Preserve this Step 8 diagnostic at its original scope; qualify the full production multiplayer workload separately."})
    return rows


def step7_mp_consumer_rows() -> list[dict]:
    """Import successful MP consumer reports omitted from the original corpus.

    Each group keeps the exact source reports and their individual scope excerpts.
    Grouping related cases does not broaden them into all-map or target evidence.
    """
    stock_maps = ("beavercreek", "bloodgulch", "boardingaction", "carousel", "chillout",
                  "damnation", "hangemhigh", "longest", "prisoner", "putput", "ratrace",
                  "sidewinder", "wizard")
    groups = [
        ("mp-collision-13map-host", "CE collision hit matrix and Prisoner branch", [
            "m2-step7-mp-collision-next-slice-audit-2026-10-22.md"],
            ["tests/test_hcu_mp_capacity.py", "tests/hcu_mp_capacity_main.c"],
            "13 stock maps ×2 plus the Prisoner collision branch.",
            "Host ILP32 semantic coverage with 16 MiB tag and 8 MiB BSP buffers; no target-capacity claim."),
        ("mp-shared-edge-host", "Shared-edge collision behavior across stock maps", [
            "m2-step7-mp-shared-edge-ce-runtime-2026-10-22.md"],
            ["tools/test_hcu_mp_collision_edge.py"],
            "13 package-backed stock maps, 52 CE assertions over two lifecycle cycles.",
            "Inset-face behavior only; does not prove exact-boundary ties, target performance, or full collision parity."),
        ("mp-edge-vertex-boundary-host", "Exact-edge, exact-vertex, grazing, and near-zero collision cases", [
            "m2-step7-mp-exact-edge-tie-ce-2026-10-22.md",
            "m2-step7-mp-exact-vertex-ce-2026-10-22.md",
            "m2-step7-mp-grazing-ce-2026-10-22.md",
            "m2-step7-mp-collision-near-zero-boundary-2026-10-22.md"],
            ["tools/test_hcu_mp_collision_edge.py", "tools/audit_mp_collision_edge_pairs.py"],
            "Four separate Beaver Creek cases: exact-edge tie, exact vertex, grazing incidence, and near-zero t (not exact t=0).",
            "One-map host cases only; do not infer other-map topology or R5900 qualification."),
        ("mp-nested-bsp-owner-extents", "Nested BSP block ownership and extents", [
            "m2-step7-mp-nested-bsp-extent-census-2026-10-22.md"],
            ["tests/hcu_mp_nested_bsp_census.h", "tests/hcu_mp_capacity_main.c"],
            "Stock map IDs 101–113, 26 load/query/unload rows.",
            "CE owner-span extent proof only; no CE semantic parity or target capacity claim."),
        ("mp-breakable-surface-and-state", "Breakable-surface inventory and CE state transition", [
            "m2-step7-mp-breakable-surface-coverage-2026-10-22.md",
            "m2-step7-prisoner-ce-breakable-damage-runtime-2026-10-22.md"],
            ["tests/test_hcu_mp_breakable_inventory.py",
             "tests/test_hcu_mp_breakable_runtime.py",
             "tests/hcu_mp_breakable_runtime_host32.c"],
            "All-13 source inventory plus one Prisoner/map-104 runtime transition at surface 457.",
            "Host state/bitmap transition only; effect path is disabled and other map/runtime behaviors remain unqualified."),
        ("mp-fog-plane-position-host", "Position-sensitive CE fog-region and underwater selection", [
            "m2-step7-mp-fog-plane-sides-2026-10-22.md"],
            ["tools/test_hcu_mp_fog_plane_sides.py"],
            "102 plane-side rows on Beaver Creek, Chill Out, and Damnation; lifecycle coverage on all 13 maps.",
            "Host selection only; no fog rendering or bot attenuation. Exact retail attenuation remains outside this gate."),
        ("mp-location-leaf-cluster-host", "CE point-to-location and leaf-to-cluster mapping", [
            "m2-step7-mp-location-leaf-map-13-map-host-2026-10-22.md"],
            ["tests/test_hcu_mp_capacity.py", "tests/hcu_mp_capacity_main.c"],
            "Stock map IDs 101–113 ×2 with a raw point-to-leaf oracle.",
            "Host-size arenas; no target-capacity claim."),
        ("mp-sound-obstruction-host", "CE sound obstruction accessor and lookup", [
            "m2-step7-mp-sound-obstruction-host-2026-10-22.md"],
            ["tests/hcu_game_sound_host32.c", "tests/hcu_mp_capacity_main.c",
             "tests/test_hcu_mp_capacity.py"],
            "Blood Gulch/map 102 only, using the exact raw map and HP2 package pins in the report.",
            "No SPU2 playback, target execution, or all-map sound qualification."),
        ("mp-visible-pvs-sound-branch-host", "Visible-PVS sound branch selection", [
            "m2-step7-mp-visible-pvs-sound-host-2026-10-22.md"],
            ["tools/test_hcu_mp_visible_pvs_sound.py"],
            "Blood Gulch clusters 0→1, two CE branch rows plus 26 lifecycle rows with a test-only collision-miss spy.",
            "No geometry collision, PAS, playback, target, or all-map branch qualification."),
        ("mp-weather-wind-host", "Relocated CE wind queries on stock MP maps", [
            "m2-step7-mp-weather-wind-13-map-host-2026-10-22.md"],
            ["tests/test_hcu_mp_capacity.py", "tests/hcu_mp_weather_wind_host32.c"],
            "Stock map IDs 101–113 ×2 with relocated CE wind queries.",
            "Host semantic coverage only; no target-sized memory, wind rendering, or Step 7 closure."),
        ("mp-bsp-failure-atomicity-host", "BSP failure rollback and retry at a late-write boundary", [
            "m2-step7-mp-bsp-failure-atomicity-2026-10-22.md"],
            ["tests/test_hcu_mp_wind_package.py",
             "tests/hcu_mp_bsp_failure_atomicity_check.h",
             "tests/hcu_mp_wind_package_host32.c"],
            "Damnation/map 108, one native host ILP32 late-write rollback/retry boundary.",
            "This injected boundary only; other publication, relocation, and upload failures remain separate."),
    ]
    # Keep query maps distinct from lifecycle-map coverage. In particular,
    # three reports contain all-map lifecycle rows while their fog/query
    # assertions exercise only a subset; four boundary reports are
    # Beaver-Creek-only even though shared test prose mentions the 13-map
    # corpus.
    all_maps = list(stock_maps)
    report_map_scopes = {
        "m2-step7-mp-collision-next-slice-audit-2026-10-22.md": {"fixture_maps": all_maps, "behavior_maps": all_maps},
        "m2-step7-mp-shared-edge-ce-runtime-2026-10-22.md": {"fixture_maps": all_maps, "behavior_maps": all_maps},
        "m2-step7-mp-exact-edge-tie-ce-2026-10-22.md": {"fixture_maps": ["beavercreek"], "behavior_maps": ["beavercreek"]},
        "m2-step7-mp-exact-vertex-ce-2026-10-22.md": {"fixture_maps": ["beavercreek"], "behavior_maps": ["beavercreek"]},
        "m2-step7-mp-grazing-ce-2026-10-22.md": {"fixture_maps": ["beavercreek"], "behavior_maps": ["beavercreek"]},
        "m2-step7-mp-collision-near-zero-boundary-2026-10-22.md": {"fixture_maps": ["beavercreek"], "behavior_maps": ["beavercreek"]},
        "m2-step7-mp-nested-bsp-extent-census-2026-10-22.md": {"fixture_maps": all_maps, "behavior_maps": all_maps},
        "m2-step7-mp-breakable-surface-coverage-2026-10-22.md": {"fixture_maps": all_maps, "behavior_maps": all_maps},
        "m2-step7-prisoner-ce-breakable-damage-runtime-2026-10-22.md": {"fixture_maps": ["prisoner"], "behavior_maps": ["prisoner"]},
        "m2-step7-mp-fog-plane-sides-2026-10-22.md": {"fixture_maps": all_maps, "behavior_maps": ["beavercreek", "chillout", "damnation"]},
        "m2-step7-mp-location-leaf-map-13-map-host-2026-10-22.md": {"fixture_maps": all_maps, "behavior_maps": all_maps},
        "m2-step7-mp-sound-obstruction-host-2026-10-22.md": {"fixture_maps": ["bloodgulch"], "behavior_maps": ["bloodgulch"]},
        "m2-step7-mp-visible-pvs-sound-host-2026-10-22.md": {"fixture_maps": ["bloodgulch"], "behavior_maps": ["bloodgulch"]},
        "m2-step7-mp-weather-wind-13-map-host-2026-10-22.md": {"fixture_maps": all_maps, "behavior_maps": all_maps},
        "m2-step7-mp-bsp-failure-atomicity-2026-10-22.md": {"fixture_maps": ["damnation"], "behavior_maps": ["damnation"]},
    }
    map_fixture_files = {path.stem.lower(): path for path in
                         (ROOT / "build/retail-maps/decompressed").glob("*.map")
                         if path.stem.lower() in stock_maps}
    map_fixture_snapshots = {name: {"map": name, "path": str(path.relative_to(ROOT)),
                                    "sha256": sha256(path), "bytes": path.stat().st_size,
                                    "role": "fixture"}
                             for name, path in map_fixture_files.items()}
    rows = []
    for slug, behavior, report_names, input_names, scope_note, limitation in groups:
        reports = [ROOT / "docs/reports" / name for name in report_names]
        missing_reports = [str(p.relative_to(ROOT)) for p in reports if not p.is_file()]
        if missing_reports:
            raise FileNotFoundError(f"missing imported Step 7 MP report(s): {missing_reports}")
        inputs = [ROOT / name for name in input_names]
        missing_inputs = [str(p.relative_to(ROOT)) for p in inputs if not p.is_file()]
        if missing_inputs:
            raise FileNotFoundError(f"missing imported Step 7 MP input(s): {missing_inputs}")
        fixture_data, measurement_data = _normalized_report_data(reports, stock_maps)
        # Use the audited report-to-harness scope mapping above rather than
        # guessing from incidental map names mentioned in report prose.
        map_fixtures = []
        for report in reports:
            scoped = report_map_scopes[report.name]
            for name in scoped["fixture_maps"]:
                path = map_fixture_files.get(name)
                if not path:
                    raise FileNotFoundError(f"missing exact source-map fixture for {name}")
                map_fixtures.append({**map_fixture_snapshots[name],
                                     "scope_report": str(report.relative_to(ROOT))})
        fixture_data["fixture_hashes"] = map_fixtures
        fixture_data["status"] = "complete" if map_fixtures else "partial"
        fixture_data["limitation"] = ("Map fixture identities follow the per-report harness/query map scope; "
                                       "broader all-map lifecycle scope is recorded separately.")
        for path in inputs:
            rel = str(path.relative_to(ROOT))
            digest = sha256(path)
            role = "harness" if "test" in path.name.lower() or path.suffix in {".c", ".h"} else "source"
            entry = {"reported_label": rel, "role": role, "sha256": digest,
                     "local_path": rel, "local_sha256": digest,
                     "matches_current_file": True,
                     "identity_resolution": "exact current source bytes"}
            fixture_data["input_hashes"].append(entry)
            fixture_data["harness_hashes" if role == "harness" else "source_hashes"].append(entry)
        imported_scopes = []
        for report in reports:
            content = report.read_text(errors="replace")
            scoped = report_map_scopes[report.name]
            report_maps = scoped["behavior_maps"]
            fixture_maps = scoped["fixture_maps"]
            all13 = len(fixture_maps) == 13
            status_match = re.search(r"(?im)^\s*(?:status|disposition|result)\s*:\s*([^\n]+)", content)
            imported_scopes.append({
                "report_path": str(report.relative_to(ROOT)),
                "report_sha256": sha256(report),
                "original_status": status_match.group(1).strip(" *.:`") if status_match else "see report; not normalized",
                "maps_named_in_report": report_maps,
                "fixture_maps": fixture_maps,
                "all_13_maps_explicit": all13,
                "scope_excerpt": " ".join(line.strip() for line in content.splitlines()[:20] if line.strip())[:1200],
            })
        evidence_paths = reports + inputs
        rows.append({
            "step": 7, "subcheck": f"mp-{slug.removeprefix('mp-')}", "behavior_or_member": behavior,
            "owner": "; ".join(str(path.relative_to(ROOT)) for path in evidence_paths),
            "evidence_level": "host execution", "result": "partial",
            "evidence": "; ".join(str(path.relative_to(ROOT)) for path in reports),
            "evidence_files": [{"path": str(path.relative_to(ROOT)), "exists": True,
                                "sha256": sha256(path)} for path in evidence_paths],
            "fixture_scope": {"summary": scope_note,
                              "maps_named_in_report": sorted({name for item in imported_scopes
                                                               for name in item["fixture_maps"]}),
                              "behavior_maps": sorted({name for item in imported_scopes
                                                       for name in item["maps_named_in_report"]}),
                              "imported_reports": imported_scopes},
            "fixture_input_hashes": fixture_data,
            "measurements": measurement_data,
            "remaining_limitation": limitation,
            "acceptance_requirement": "Preserve each linked consumer result at its original report scope; qualify broader production, target, and gameplay acceptance separately.",
        })
    return rows


def ledger(schema_elf: Path, inventory_path: Path) -> dict:
    parent = repository_identity(ROOT, "parent")
    hcu = repository_identity(ROOT / "submodules/halo-ce-universal", "halo-ce-universal")
    ps2 = repository_identity(ROOT / "submodules/halo-ps2", "halo-ps2")
    schema_result = ROOT / "build/hcu-ps2-closure/all-no-bootstrap-memory/result.json"
    schema_build = json.loads(schema_result.read_text())
    build_root, toolchain_prefix, _toolchain_env, _jobs = toolchain_environment()
    compiler = toolchain_prefix / "ee/bin/mips64r5900el-ps2-elf-gcc"
    hcu_root = ROOT / "submodules/halo-ce-universal"
    source_identity = schema_source_identity(schema_build.get("units", {}), hcu_root)
    source_mismatches = [row for row in source_identity["units"]
                         if row["status"] != "match"]
    budget = ROOT / "config/memory-budget.json"
    map_roots = [ROOT / "build/retail-maps/decompressed",
                 ROOT / "data/retail/weapon-audit-maps"]
    source_maps = []
    for map_root in map_roots:
        if map_root.is_dir():
            source_maps.extend({"path": str(path.relative_to(ROOT)), "sha256": sha256(path),
                                "bytes": path.stat().st_size}
                               for path in sorted(map_root.glob("*.map")))
    generated = []
    for path in (schema_elf, schema_result, budget,
                 ROOT / "submodules/halo-ce-universal/port/ps2/port.json",
                 ROOT / "submodules/halo-ce-universal/port/ps2/include/halo_ps2_prefix.h",
                 ROOT / "submodules/halo-ps2/tools/halo2ps2/bsp.py",
                 ROOT / "tools/hcu_schema_manifest.py", ROOT / "tools/ctag_schema_walk.py",
                 ROOT / "config/dependencies.json"):
        if path.is_file():
            generated.append({"path": str(path.relative_to(ROOT)), "sha256": sha256(path),
                              "bytes": path.stat().st_size})
    for path in (ROOT / "tools/extract_hcu_step7_gap_dwarf_members.py",
                 ROOT / "docs/reports/m2-step7-schema-gap-dwarf-members-2026-10-22.json",
                 ROOT / "tools/generate_step7_bsp_consumer_crosswalk.py",
                 ROOT / "docs/reports/m2-step7-bsp-consumer-crosswalk-2026-10-22.json",
                 ROOT / "tools/generate_m2_step7_open_root_dispositions.py",
                 ROOT / "docs/reports/m2-step7-open-root-bsp-dispositions-2026-10-22.json",
                 ROOT / "tools/probe_step7_bsp_range_members.py",
                 ROOT / "docs/reports/m2-step7-bsp-range-member-layout-2026-10-22.json",
                 ROOT / "tools/probe_step7_eight_unmapped_exact_layout.py",
                 ROOT / "docs/reports/m2-step7-eight-unmapped-exact-layout-2026-10-22.json",
                 ROOT / "tools/audit_step7_unclassified_range_dispositions.py",
                 ROOT / "docs/reports/m2-step7-unclassified-range-dispositions-2026-10-22.json",
                 ROOT / "docs/reports/m2-step7-mp-target-astar-2026-10-22.md",
                 ROOT / "tools/test_step7_bsp_zero_size_sentinels.py",
                 ROOT / "tests/test_step7_unmapped_bsp_range_retention.py",
                 ROOT / "docs/reports/m2-step7-unmapped-bsp-range-retention-2026-10-22.md",
                 ROOT / "tools/audit_step7_empty_bsp_fields.py",
                 ROOT / "docs/reports/m2-step7-empty-bsp-fields-2026-10-22.json",
                 ROOT / "tests/test_step7_synthetic_empty_bsp_fields.py",
                 ROOT / "tools/record_step7_bsp_target_probe.py",
                 ROOT / "docs/reports/m2-step7-bsp-collision-pvs-current-target-probe-2026-10-22.json",
                 ROOT / "docs/reports/m2-step7-bsp-collision-pvs-current-target-probe-2026-10-22.md",
                 ROOT / "docs/reports/retail-bsp-cbsp-audit-c0-2026-10-22.json"):
        if path.is_file():
            generated.append({"path": str(path.relative_to(ROOT)), "sha256": sha256(path),
                              "bytes": path.stat().st_size})
    for path in (ROOT / "build/m2-mp-render-assets/match-content-closure-v1.json",
                 ROOT / "build/custom-weapon-capacity/closure-verified-2026-10-22.json"):
        if path.is_file():
            generated.append({"path": str(path.relative_to(ROOT)), "sha256": sha256(path),
                              "bytes": path.stat().st_size,
                              "scope": "offline source closure; not runtime residency"})
    gap_discovery = ROOT / "docs/reports/m2-step7-schema-gap-source-discovery-2026-10-22.json"
    if gap_discovery.is_file():
        generated.append({"path": str(gap_discovery.relative_to(ROOT)),
                          "sha256": sha256(gap_discovery),
                          "bytes": gap_discovery.stat().st_size,
                          "scope": "source declaration discovery only; no layout/retention claim"})
    gap_layout = ROOT / "docs/reports/m2-step7-schema-gap-layout-2026-10-22.json"
    gap_layout_tool = ROOT / "tools/verify_hcu_step7_schema_gap_layout.py"
    for path in (gap_layout, gap_layout_tool):
        if path.is_file():
            generated.append({"path": str(path.relative_to(ROOT)),
                              "sha256": sha256(path), "bytes": path.stat().st_size,
                              "scope": "whole-type compiler ABI check; no byte-level classification"})
    generated.append({"path": "tools/generate_hcu_step7_step8_closure.py",
                      "sha256": sha256(ROOT / "tools/generate_hcu_step7_step8_closure.py"),
                      "bytes": (ROOT / "tools/generate_hcu_step7_step8_closure.py").stat().st_size})
    for recovery_tool in ("tools/integrate_step7_step8_recovered_bindings.py",
                          "tools/audit_hcu_c0_row_accounting.py"):
        path = ROOT / recovery_tool
        generated.append({"path": recovery_tool, "sha256": sha256(path),
                          "bytes": path.stat().st_size,
                          "scope": "Row-scoped exact identity recovery and explicit evidence availability accounting"})
    rows = evidence_rows()
    # Keep the explicit core acceptance rows and the synthetic structural
    # empty-field row intact; append historical consumer evidence separately.
    rows.extend(swarm_evidence_rows())
    rows.extend(step8_report_rows())
    rows.extend(step7_mp_consumer_rows())
    step7 = [item for item in rows if item["step"] == 7]
    step8 = [item for item in rows if item["step"] == 8]
    dependency_config = json.loads((ROOT / "config/dependencies.json").read_text())
    dependency_names = {"halo-64", "halo-ps2", "halo-ce-universal", "ps2dev",
                        "ps2toolchain", "ps2sdk", "ps2toolchain-ee",
                        "ps2toolchain-iop", "ps2toolchain-dvp"}
    dependencies = []
    for item in dependency_config["dependencies"]:
        if item["name"] not in dependency_names:
            continue
        path = ROOT / item["path"]
        if path.is_dir() and (path / ".git").exists():
            dependencies.append(repository_identity(path, item["name"]))
    package_roots = [ROOT / "build/retail-maps",
                     ROOT / "build/m2-mp-all-map-packages",
                     ROOT / "build/hcu-parent-link-probe/maps"]
    package_files = []
    package_suffixes = {".hp2", ".ctag", ".cbsp", ".hmap"}
    for package_root in package_roots:
        if package_root.is_dir():
            for path in sorted(package_root.rglob("*")):
                if path.is_file() and path.suffix.lower() in package_suffixes and "fault" not in path.name.lower():
                    package_files.append({"path": str(path.relative_to(ROOT)),
                                          "sha256": sha256(path),
                                          "bytes": path.stat().st_size})
    for path in (ROOT / "build/retail-ui-hmap.hp2", ROOT / "build/retail-ui-component.hp2"):
        if path.is_file():
            package_files.append({"path": str(path.relative_to(ROOT)), "sha256": sha256(path),
                                  "bytes": path.stat().st_size})
    return {
        "format": "hcu-m2-step7-step8-closure-ledger-v1",
        "generated_utc_date": "2026-10-22",
        "scope": {"maps": 13, "ui_bootstrap": True, "campaign": False,
                  "local_players": [1, 2, 3, 4], "minimum_spartan_bots": 4,
                  "retail_actor_variants": "all resolved combat variants from retained source corpus",
                  "reserve_bytes": 5767168},
        "repository_identities": [parent, hcu, ps2],
        "dependency_identities": dependencies,
        "additional_pins": {
            "halo64": "17541f4444baabb47d1a0deb917f26ccb7b6bc5c",
            "schema_elf": str(schema_elf.relative_to(ROOT)),
            "schema_elf_sha256": sha256(schema_elf),
            "schema_result_sha256": sha256(schema_result),
            "toolchain": {
                "compiler_path": str(compiler.relative_to(ROOT)),
                "compiler_sha256": sha256(compiler) if compiler.is_file() else None,
                "compiler_version": subprocess.check_output(
                    [str(compiler), "--version"], text=True).splitlines()[0]
                    if compiler.is_file() else None,
                "profile_path": "config/toolchain-profile.json",
                "profile_sha256": sha256(ROOT / "config/toolchain-profile.json"),
                "build_report_path": str((build_root / "toolchain/compiler-sdk.json").relative_to(ROOT)),
                "build_report_sha256": sha256(build_root / "toolchain/compiler-sdk.json")
                    if (build_root / "toolchain/compiler-sdk.json").is_file() else None,
            },
            "schema_build_prefix": schema_build.get("prefix"),
            "schema_build_prefix_sha256": schema_build.get("prefix_sha256"),
            "schema_build_manifest_sha256": schema_build.get("manifest_sha256"),
            "budget_path": str(budget.relative_to(ROOT)),
            "budget_sha256": sha256(budget),
            "schema_manifest_generator_sha256": sha256(ROOT / "tools/hcu_schema_manifest.py"),
            "bsp_inventory_path": str(inventory_path.relative_to(ROOT)),
            "bsp_inventory_sha256": sha256(inventory_path),
        },
        "source_maps": source_maps,
        "generated_packages": package_files,
        "package_provenance": package_provenance_identity(),
        "generated_inputs": generated,
        "schema_build_units": {
            "count": len(schema_build.get("units", {})),
            "compiled_count": schema_build.get("compiled_count"),
            "failed_count": schema_build.get("failed_count"),
            "status": "stale-source-inputs" if source_identity["status"] != "current"
                      else "source-hashes-match",
            "source_hash_mismatches": [row for row in source_mismatches
                                       if row["status"] == "changed"],
            "source_files_missing": [row["path"] for row in source_mismatches
                                     if row["status"] == "missing"],
            "source_identity": source_identity,
            "source_and_object_hashes": schema_build.get("units", {}),
            "source_manifest_sha256": hashlib.sha256(json.dumps(
                {name: item.get("source_sha256") for name, item in
                 sorted(schema_build.get("units", {}).items())}, sort_keys=True,
                separators=(",", ":")).encode()).hexdigest(),
        },
        "step_status": {
            "step7": {"status": "open", "qualified_rows": sum(x["result"] == "qualified" for x in step7),
                      "partial_rows": sum(x["result"] == "partial" for x in step7),
                      "unrun_rows": sum(x["result"] in ("not_run", "blocked") for x in step7)},
            "step8": {"status": "open", "qualified_rows": sum(x["result"] == "qualified" for x in step8),
                      "partial_rows": sum(x["result"] == "partial" for x in step8),
                      "unrun_rows": sum(x["result"] in ("not_run", "blocked") for x in step8)},
        },
        "evidence": rows,
        "ledger_rules": [
            "A result only satisfies the row's stated acceptance_requirement.",
            "Partial, blocked, not_run, skipped, stale, and failed evidence never counts as qualified.",
            "Commit IDs do not identify dirty build inputs; retain tracked diff and changed-file hashes.",
            "Every generated guest claim must identify ELF, source pins, emulator mode, settings, and log hashes.",
            "Step 7 and Step 8 remain open until their complete acceptance rows are qualified.",
        ],
    }


def write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True, indent=2) + "\n")


def coverage_audit(ledger_obj: dict, ledger_path: Path) -> dict:
    def pinned_local(record: dict) -> bool:
        if record.get("matches_current_file") is True:
            return True
        path = record.get("path") or record.get("local_path")
        digest = record.get("sha256") or record.get("local_sha256")
        if not path or not digest:
            return False
        candidate = Path(path)
        if not candidate.is_absolute():
            candidate = ROOT / candidate
        return candidate.is_file() and sha256(candidate) == digest

    rows = ledger_obj["evidence"]
    row_summaries = []
    for row in rows:
        fixture = row.get("fixture_input_hashes", {})
        measurements = row.get("measurements", {})
        input_records = fixture.get("input_hashes", [])
        fixture_records = fixture.get("fixture_hashes", [])
        fixture_status = fixture.get("status", "missing")
        if fixture_records and all(pinned_local(item) or
                                   (item.get("sha256") and item.get("recipe"))
                                   for item in fixture_records):
            fixture_status = "complete"
        input_status = ("complete" if input_records and all(pinned_local(item) for item in input_records)
                        else "partial" if input_records else "missing")
        row_summaries.append({
            "step": row["step"], "subcheck": row["subcheck"],
            "result": row["result"], "evidence_level": row["evidence_level"],
            "evidence_artifact_hashes": row.get("evidence_files", []),
            "fixture_hash_status": fixture_status,
            "fixture_hash_count": len(fixture_records),
            "input_hash_status": input_status,
            "input_hash_count": len(input_records),
            "measurement_status": measurements.get("status", "missing"),
            "limitation": row.get("remaining_limitation", "")})
    swarm = [row for row in rows if row["subcheck"].startswith("swarm-")]
    step8_imports = [row for row in rows if row["subcheck"].startswith("report-")]
    step7_mp_imports = [row for row in rows if row["subcheck"].startswith("mp-")]
    imported_reports = swarm + step8_imports + step7_mp_imports
    step7_mp_report_count = sum(len(row.get("fixture_scope", {}).get("imported_reports", []))
                                 for row in step7_mp_imports)
    complete_fixtures = sum(row.get("fixture_input_hashes", {}).get("status") == "complete" for row in imported_reports)
    structured_metric_values = sum(
        1 for row in rows for value in row.get("measurements", {}).get("values", [])
        if isinstance(value, dict) and {"name", "value", "unit"} <= set(value))
    verbatim_metric_rows = sum(row.get("measurements", {}).get("status") == "verbatim_only" for row in rows)
    verbatim_metric_lines = sum(
        len(row.get("measurements", {}).get("verbatim_lines", [])) +
        sum(1 for value in row.get("measurements", {}).get("values", [])
            if isinstance(value, dict) and value.get("unit_status") == "verbatim_only")
        for row in rows)
    core_rows = [row for row in rows
                 if not row["subcheck"].startswith(("swarm-", "report-", "mp-"))]
    core_normalized_values = sum(
        1 for row in core_rows for value in row.get("measurements", {}).get("values", [])
        if isinstance(value, dict) and {"name", "value", "unit"} <= set(value))
    metric_binding_issues = []
    for row in rows:
        for value in row.get("measurements", {}).get("values", []):
            if not isinstance(value, dict) or not {"name", "value", "unit"} <= set(value):
                continue
            source_path = value.get("source_artifact") or value.get("source_report")
            source_hash = value.get("source_artifact_sha256") or value.get("source_report_sha256")
            has_location = bool(value.get("source_pointer") or
                                (value.get("source_line") and value.get("source_column")))
            source_file = ROOT / source_path if source_path else None
            valid = bool(source_file and source_file.is_file() and source_hash and
                         sha256(source_file) == source_hash and has_location)
            if not valid:
                metric_binding_issues.append({"step": row["step"], "subcheck": row["subcheck"],
                                              "name": value.get("name"), "source_path": source_path,
                                              "source_hash": source_hash,
                                              "source_exists": bool(source_file and source_file.is_file()),
                                              "location_bound": has_location})
    report_metric_rows = sum(bool(row.get("measurements", {}).get("values")) for row in imported_reports)
    complete_fixture_rows = sum(item["fixture_hash_status"] == "complete" for item in row_summaries)
    not_applicable_fixture_rows = sum(item["fixture_hash_status"] == "not_applicable" for item in row_summaries)
    complete_input_rows = sum(item["input_hash_status"] == "complete" for item in row_summaries)
    return {
        "format": "hcu-m2-step7-step8-ledger-coverage-audit-v1",
        "ledger_path": str(ledger_path.relative_to(ROOT)),
        "ledger_sha256": sha256(ledger_path),
        "row_count": len(rows), "swarm_import_count": len(swarm),
        "step8_report_import_count": len(step8_imports),
        "generated_package_count": len(ledger_obj.get("generated_packages", [])),
        "profile_package_counts": {
            "stock_mp": sum(x["path"].startswith(("build/m2-mp-all-map-packages/", "build/retail-maps/")) and x["path"].endswith(".hp2") for x in ledger_obj.get("generated_packages", [])),
            "parent_link_probe": sum(x["path"].startswith("build/hcu-parent-link-probe/maps/") and x["path"].endswith(".hp2") for x in ledger_obj.get("generated_packages", [])),
            "ui": sum(x["path"].startswith("build/retail-ui-") and x["path"].endswith(".hp2") for x in ledger_obj.get("generated_packages", []))},
        "rows": row_summaries,
        "coverage_findings": [
            {"requirement": "Every row has fixture and input hashes", "status": "partial",
             "finding": f"{complete_fixture_rows}/{len(rows)} rows have verifiable fixture identities; {not_applicable_fixture_rows} source-inspection rows explicitly require no runtime fixture. {complete_input_rows}/{len(rows)} rows have fully path-bound input hashes. Among imported reports, {complete_fixtures}/{len(imported_reports)} bind exact decompressed map fixtures for declared map scopes."},
            {"requirement": "Every row has measured values", "status": "partial",
             "finding": f"{structured_metric_values} values have explicit name/value/unit fields, including {core_normalized_values} normalized values across the {len(core_rows)} core rows; {verbatim_metric_rows} rows retain only verbatim numeric lines and {verbatim_metric_lines} such lines remain explicitly unnormalized. {report_metric_rows}/{len(imported_reports)} imported reports have parsed numeric content. Only unit-explicit table cells are normalized; raw token lists are not promoted."},
            {"requirement": "Every normalized metric has an exact source binding", "status": "satisfied" if not metric_binding_issues else "partial",
             "finding": f"{structured_metric_values - len(metric_binding_issues)}/{structured_metric_values} normalized values bind to an existing, hash-matching source artifact and an exact JSON pointer or report line/column.",
             "unresolved": metric_binding_issues},
            {"requirement": "Evidence level and result separate host/interpreter/recompiler", "status": "partial",
             "finding": f"All {len(swarm)} swarm reports and {len(step8_imports)} Step 8 reports retain their own rows; {step7_mp_report_count} previously omitted Step 7 MP consumer reports are grouped into {len(step7_mp_imports)} rows with per-report status, scope, and hash pins. Mixed, blocked, and unavailable execution modes are not promoted."},
            {"requirement": "Import prior evidence at original scope", "status": "partial",
             "finding": f"Imported all {len(swarm)} build/step7-swarm/*/report.md files, {len(step8_imports)} existing Step 8 consumer/runtime reports, and {step7_mp_report_count} distinct Step 7 MP consumer reports in {len(step7_mp_imports)} grouped rows. Each imported MP source report retains its own map-scope excerpt and hash; blockers and campaign-only reports remain excluded."},
            {"requirement": "Keep Steps 7 and 8 open", "status": "satisfied",
             "finding": "Both generated step_status entries are open."}],
        "next_actions": [
            "Complete exact fixture/input identities for core rows whose map scope or raw-source binding is not proven.",
            "Normalize report metrics with units and exact run identities where raw summary lines are insufficient.",
            "Import remaining non-report-linked Step 8 evidence only when it adds distinct source-backed coverage.",
            "Reconcile all consumer rows against the compiler-derived BSP member inventory and failure cases."],
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--schema-elf", type=Path, default=SCHEMA_DEFAULT)
    parser.add_argument("--ledger", type=Path, default=LEDGER_DEFAULT)
    parser.add_argument("--inventory", type=Path, default=INVENTORY_DEFAULT)
    parser.add_argument("--audit", type=Path, default=COVERAGE_AUDIT_DEFAULT)
    parser.add_argument("--bindings", type=Path, default=RECOVERED_BINDINGS_DEFAULT,
                        help="row-scoped exact identity recovery manifest")
    parser.add_argument("--force", action="store_true", help="replace outputs generated by this tool")
    args = parser.parse_args(argv)
    for output in (args.ledger, args.inventory, args.audit, args.bindings):
        if output.exists() and not args.force:
            parser.error(f"refusing to overwrite {output}; pass --force to refresh the C0 baseline")
    try:
        inv = inventory(args.schema_elf)
        inv["compiler_layout"] = compile_member_layout(args.schema_elf)
        if inv["compiler_layout"]["status"] != "passed":
            raise ValueError("compiler-derived C layout assertions failed; see build/hcu-step7-step8-c0/structure_bsp_member_layout.c")
        inv["compiler_layout"]["assertions"] = "structure_bsp sizeof/offsetof/field-size against linked schema and all omitted root members"
        write_json(args.inventory, inv)
        led = ledger(args.schema_elf, args.inventory)
        # Generate the diagnostic from the just-built baseline ledger, then
        # resolve only hashes already pinned on the same row. The canonical
        # ledger embeds paths/hashes, never a hash of the diagnostic, so the
        # dependency is one-way and cannot form a circular digest reference.
        write_json(args.ledger, led)
        subprocess.run([sys.executable,
                        str(ROOT / "tools/audit_step7_step8_recoverable_bindings.py"),
                        "--ledger", str(args.ledger), "--output", str(args.bindings)],
                       cwd=ROOT, check=True)
        with args.bindings.open() as stream:
            recovered = json.load(stream)
        from integrate_step7_step8_recovered_bindings import integrate
        integration = integrate(led, recovered, ROOT)
        from audit_hcu_c0_row_accounting import attach_accounting
        attach_accounting(led, ROOT)
        write_json(args.ledger, led)
        # This is a non-circular, one-way snapshot pointer from the diagnostic
        # manifest to the enriched canonical ledger.
        recovered["ledger_sha256"] = sha256(args.ledger)
        write_json(args.bindings, recovered)
        write_json(args.audit, coverage_audit(led, args.ledger))
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        parser.exit(2, f"Step 7/8 C0 generation failed: {error}\n")
    print(f"inventory={args.inventory} rows={inv['member_rows']} unclassified={inv['unclassified_ranges']}")
    print(f"ledger={args.ledger} step7={led['step_status']['step7']['status']} step8={led['step_status']['step8']['status']}")
    print(f"recovered_bindings={integration['rows_with_added_bindings']} rows; "
          f"{integration['map_identity_resolutions']} map and "
          f"{integration['report_artifact_resolutions']} report-artifact identities")
    print(f"coverage_audit={args.audit} rows={len(led['evidence'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
