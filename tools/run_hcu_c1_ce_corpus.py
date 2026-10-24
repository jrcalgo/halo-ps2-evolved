#!/usr/bin/env python3
"""Run the native ILP32 CE validator against an exact HCP profile corpus.

The 2 MiB run models the PS2 tag-cache admission bound. The separate 64 MiB
host run is a semantic validator diagnostic only and is never EE-capacity proof.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import ctag
from hcu_profile_validate import parse_package, validate as validate_profile
from hcu_schema_manifest import Elf32, SchemaManifest
from qualify_hcu_c1 import EXPECTED

TARGET_CAPACITY = 2 * 1024 * 1024
HOST_DIAGNOSTIC_CAPACITY = 64 * 1024 * 1024


def sha_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def file_pin(path: Path, *, root=ROOT) -> dict:
    path = Path(path).resolve()
    try:
        display = path.relative_to(Path(root).resolve()).as_posix()
    except ValueError:
        display = path.as_posix()
    return {"path": display, "sha256": sha_file(path), "bytes": path.stat().st_size}


def expected_profile_names() -> list[str]:
    return [row[0] for row in EXPECTED]


def expected_identity(name: str) -> tuple[int, str, str]:
    for index, (profile_name, kind, map_name) in enumerate(EXPECTED, 1):
        if profile_name == name:
            return index, kind, map_name
    raise ValueError(f"profile name is outside the canonical corpus: {name}")


def _load_fixture_module(artifacts: Path):
    os.environ["HCU_C1_CE_ARTIFACTS"] = str(artifacts.resolve())
    path = ROOT / "tests/test_hcu_profile_ce_validation.py"
    spec = importlib.util.spec_from_file_location("hcu_c1_ce_fixture", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load the maintained native CE fixture helpers")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _profile_input(directory: Path, name: str, schema: dict, *, root=ROOT) -> dict:
    package_path, manifest_path = directory / f"{name}.hcp", directory / f"{name}.json"
    if not package_path.is_file() or not manifest_path.is_file():
        raise FileNotFoundError(f"missing package/manifest pair for {name}")
    manifest = json.loads(manifest_path.read_text())
    package_bytes = package_path.read_bytes()
    package_sha = sha_bytes(package_bytes)
    if not isinstance(manifest, dict) or manifest.get("package_sha256") != package_sha:
        raise ValueError(f"{name}: manifest package hash differs from package bytes")
    profile = manifest.get("profile", {})
    expected_index, expected_kind, expected_map = expected_identity(name)
    if (profile.get("name"), profile.get("id"), profile.get("kind"), profile.get("map")) != (
            name, expected_index, expected_kind, expected_map):
        raise ValueError(f"{name}: manifest identity differs from canonical 27-profile roster")
    schema_sha = schema.get("elf_sha256") if isinstance(schema, dict) else None
    if manifest.get("schema_elf_sha256") != schema_sha:
        raise ValueError(f"{name}: manifest compiler-schema ELF pin is stale")
    validation = validate_profile(package_bytes, manifest, schema,
        expected_package_sha256=package_sha, expected_profile_id=expected_index,
        expected_scenario=profile.get("scenario", {}).get("path", ""))
    if manifest.get("validation") != validation:
        raise ValueError(f"{name}: retained validation summary is stale")
    source_rows = manifest.get("source_maps", {})
    source_lengths = []
    source_pins = {}
    for key, item in source_rows.items():
        source = Path(item.get("path", ""))
        if not source.is_absolute():
            source = Path(root) / source
        if not source.is_file() or sha_file(source) != item.get("sha256"):
            raise ValueError(f"{name}: source map pin missing/stale: {key}")
        source_lengths.append(source.stat().st_size)
        source_pins[key] = {"path": item["path"], "sha256": item["sha256"]}
    if not source_lengths:
        raise ValueError(f"{name}: no pinned source maps")
    for producer, digest in manifest.get("producers", {}).items():
        producer_path = Path(producer)
        if not producer_path.is_absolute():
            producer_path = Path(root) / producer_path
        if not producer_path.is_file() or sha_file(producer_path) != digest:
            raise ValueError(f"{name}: producer source pin is stale: {producer}")
    chunks = parse_package(package_bytes, expected_package_sha256=package_sha,
                           expected_profile_id=expected_index)
    ce_blob = chunks['chunks'].get((1, 0))
    if ce_blob is None:
        raise ValueError(f"{name}: HCP lacks CE chunk")
    decoded = ctag.decode(ce_blob, max_image_size=len(ce_blob))
    return {"name": name, "package_path": package_path, "manifest_path": manifest_path,
            "package_sha256": package_sha, "manifest_sha256": sha_file(manifest_path),
            "profile_id": expected_index, "kind": expected_kind, "map": expected_map,
            "source_map_pins": source_pins, "source_file_length": max(source_lengths),
            "ctag": ce_blob, "ctag_sha256": sha_bytes(ce_blob),
            "image_size": len(decoded.image), "tag_count": validation["tag_count"],
            "relocation_count": len(decoded.relocations), "validation": validation}


def _run(command: list[str], *, env=None, timeout=300) -> subprocess.CompletedProcess:
    return subprocess.run(command, capture_output=True, text=True, env=env, timeout=timeout)


def _assert_markers(name: str, text: str, *, target: bool) -> None:
    if "ctag=ok" not in text or "pointers_stable=1" not in text or "owner_unpublished=1" not in text:
        raise RuntimeError(f"{name}: native validator omitted CTAG or pointer-lifetime proof")
    if name == "ui" and target:
        required = ("validator=accepted", "mount=1", "corrupt_schema_rejected=1")
    elif target:
        required = ("validator=rejected", f"capacity={TARGET_CAPACITY}", "mount=0")
    else:
        required = ("validator=accepted", f"capacity={HOST_DIAGNOSTIC_CAPACITY}",
                    "corrupt_schema_rejected=1")
    if not all(item in text for item in required):
        raise RuntimeError(f"{name}: native result does not meet required markers {required}")


def run_corpus(profiles_dir: Path, output_dir: Path, *, only: list[str] | None = None,
               schema_elf=ROOT / "build/hcu-ps2-closure/all-no-bootstrap-memory/halo-local.elf",
               root=ROOT) -> dict:
    profiles_dir, output_dir = Path(profiles_dir), Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    expected = expected_profile_names()
    selected = expected if only is None else list(only)
    if not selected or len(set(selected)) != len(selected) or any(name not in expected for name in selected):
        raise ValueError("--only must be a nonempty unique subset of the canonical 27 profile names")
    schema_path = Path(schema_elf)
    if not schema_path.is_absolute():
        schema_path = Path(root) / schema_path
    schema = SchemaManifest(Elf32(schema_path)).build()
    profile_inputs = {}
    for name in selected:
        profile_inputs[name] = _profile_input(profiles_dir, name, schema, root=root)

    artifacts = output_dir / "ce-artifacts"
    fixture = _load_fixture_module(artifacts)
    _compiler, target_command = fixture._compile_fixture()
    _host_compiler, host_command = fixture._compile_fixture(host_capacity=True)
    target_exe = artifacts / "hcu-profile-ce-validation"
    host_exe = artifacts / "hcu-profile-ce-validation-host64m"
    run_rows = []
    for name in selected:
        item = profile_inputs[name]
        ctag_path = artifacts / "corpus" / f"{name}.ctag"
        ctag_path.parent.mkdir(parents=True, exist_ok=True)
        ctag_path.write_bytes(item["ctag"])
        target_command_row = [str(target_exe), str(ctag_path), name, str(item["source_file_length"])]
        process = _run(target_command_row)
        if process.returncode != 0:
            raise RuntimeError(f"{name}: target-capacity native run failed ({process.returncode}): {process.stderr}")
        target_text = process.stdout.strip()
        _assert_markers(name, target_text, target=True)
        target_log = artifacts / "corpus" / f"{name}.target.log"
        target_log.write_text(process.stdout + process.stderr)
        row = {"profile": name, "package_sha256": item["package_sha256"],
               "manifest_sha256": item["manifest_sha256"], "ctag_sha256": item["ctag_sha256"],
               "source_map_pins": item["source_map_pins"], "source_file_length": item["source_file_length"],
               "image_size": item["image_size"], "tag_count": item["tag_count"],
               "relocation_count": item["relocation_count"],
               "target": {"command": target_command_row, "returncode": process.returncode,
                          "result": target_text, "log": file_pin(target_log, root=root)}}
        callback_path = artifacts / "corpus" / f"{name}.callback-deltas.tsv"
        field_path = artifacts / "corpus" / f"{name}.field-deltas.tsv"
        sound_path = artifacts / "corpus" / f"{name}.sound-owner-fixups.tsv"
        delta_path = artifacts / "corpus" / f"{name}.validation-deltas.json"
        audit_path = artifacts / "corpus" / f"{name}.callback-audit.json"
        for path in (callback_path, field_path, sound_path):
            path.write_text("")
        host_env = os.environ.copy()
        host_env["HCU_VALIDATOR_CHECK_DELTA_PATH"] = str(callback_path)
        host_env["HCU_VALIDATOR_FIELD_DELTA_PATH"] = str(field_path)
        host_env["HCU_SOUND_FIXUP_PATH"] = str(sound_path)
        host_command_row = [str(host_exe), str(ctag_path), name, str(item["source_file_length"]),
                            str(HOST_DIAGNOSTIC_CAPACITY), str(delta_path)]
        host_process = _run(host_command_row, env=host_env)
        if host_process.returncode != 0:
            raise RuntimeError(f"{name}: host semantic native run failed ({host_process.returncode}): {host_process.stderr}")
        host_text = host_process.stdout.strip()
        _assert_markers(name, host_text, target=False)
        host_log = artifacts / "corpus" / f"{name}.host64m.log"
        host_log.write_text(host_process.stdout + host_process.stderr)
        callback_counts, delta, callback_audit = fixture._audit_host_validation(
            host_process, callback_path, field_path, sound_path, delta_path, audit_path)
        correction_match = __import__("re").search(r"corrections=(\d+)", host_text)
        if not correction_match or sum(callback_counts.values()) != int(correction_match.group(1)):
            raise RuntimeError(f"{name}: host correction callback count does not reconcile")
        if (not callback_audit.get("all_byte_deltas_attributed_to_validator_mutation_sites") or
                callback_audit.get("whole_image_delta_bytes_verified") != delta.get("changed_bytes")):
            raise RuntimeError(f"{name}: host mutation byte attribution is incomplete")
        row["host_semantic"] = {"command": host_command_row, "returncode": host_process.returncode,
            "result": host_text, "log": file_pin(host_log, root=root),
            "callbacks": dict(sorted(callback_counts.items())), "delta": delta,
            "callback_audit": callback_audit,
            "artifacts": {path.name: file_pin(path, root=root) for path in
                          (callback_path, field_path, sound_path, delta_path, audit_path)}}
        run_rows.append(row)

    completeness = len(selected) == len(expected) and set(selected) == set(expected)
    report = {"format": "hcu-c1-native-ce-corpus-v1",
        "status": "complete" if completeness else "partial",
        "complete_27_profile_corpus": completeness,
        "runtime_admitted": False,
        "scope": "Native host ILP32 CE validator evidence for C1 package inputs; no framebuffer, SPU2, console, or C2 EE-fit claim.",
        "limitations": ["64 MiB semantic run is host-only and is not evidence of PS2 EE capacity."],
        "profiles_directory": str(profiles_dir.resolve()),
        "schema_elf": file_pin(schema_path, root=root),
        "target_capacity_bytes": TARGET_CAPACITY,
        "host_semantic_capacity_bytes": HOST_DIAGNOSTIC_CAPACITY,
        "executables": {"target": file_pin(target_exe, root=root), "host": file_pin(host_exe, root=root)},
        "compile_commands": {"target": target_command, "host": host_command},
        "generated_sources": {path.name: file_pin(path, root=root) for path in (
            artifacts / "halo_ps2_msvc_semantics.h", artifacts / "tag_validate_host_instrumented.c",
            artifacts / "tag_schema_effects_host_instrumented.c", artifacts / "tag_schema_models_host_instrumented.c")},
        "implementation_source_pins": {
            str(path.relative_to(Path(root).resolve()).as_posix()): sha_file(path)
            for path in sorted({Path(token).resolve() for token in [*target_command, *host_command]
                                if isinstance(token, str) and Path(token).suffix in (".c", ".h") and
                                Path(token).is_file()} | {Path(__file__).resolve()})},
        "run_count": len(run_rows), "profiles": run_rows}
    return report


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profiles", type=Path,
        default=ROOT / os.environ.get("HCU_C1_PROFILES", "build/m2-c1-corpus-primary-v3"),
        help="HCP profile corpus directory (default: $HCU_C1_PROFILES or build/m2-c1-corpus-primary-v3)")
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--schema-elf", type=Path,
        default=ROOT / "build/hcu-ps2-closure/all-no-bootstrap-memory/halo-local.elf")
    parser.add_argument("--only", nargs="+", help="optional smoke subset; report remains partial")
    parser.add_argument("--report", type=Path,
        help="optional report path (default: OUTPUT_DIR/native-corpus.json)")
    args = parser.parse_args(argv)
    report = run_corpus(args.profiles, args.output_dir, only=args.only, schema_elf=args.schema_elf)
    report_path = args.report or args.output_dir / "native-corpus.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, sort_keys=True, indent=2) + "\n")
    print(json.dumps({"status": report["status"], "run_count": report["run_count"],
                      "report": str(report_path)}, sort_keys=True))
    return 0 if report["status"] == "complete" else 2


if __name__ == "__main__":
    raise SystemExit(main())
