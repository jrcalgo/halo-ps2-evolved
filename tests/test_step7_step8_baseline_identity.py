"""Guard the baseline identity contract recorded by the C0 closure ledger."""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LEDGER_PATH = ROOT / "docs/reports/m2-step7-step8-closure-ledger-2026-10-22.json"
SHA256 = re.compile(r"^[0-9a-f]{64}$")
GIT_COMMIT = re.compile(r"^[0-9a-f]{40}$")


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_c0_baseline_records_required_identities_and_dirty_build_inputs():
    ledger = json.loads(LEDGER_PATH.read_text())

    repositories = {row["name"]: row for row in ledger["repository_identities"]}
    assert {"parent", "halo-ce-universal", "halo-ps2"} <= repositories.keys()
    dependencies = {row["name"]: row for row in ledger["dependency_identities"]}
    assert "halo-64" in dependencies
    assert all(GIT_COMMIT.fullmatch(row["head"]) for row in repositories.values())
    assert GIT_COMMIT.fullmatch(dependencies["halo-64"]["head"])

    # Every dirty checkout records exact hashes for the source files in scope;
    # a dirty flag with no file-level identity would not identify the build tree.
    for row in [*repositories.values(), *dependencies.values()]:
        assert isinstance(row["dirty"], bool)
        assert SHA256.fullmatch(row["status_porcelain_sha256"])
        assert SHA256.fullmatch(row["tracked_diff_sha256"])
        changed = row["changed_file_sha256"]
        assert changed or not row["dirty"]
        assert len({item["path"] for item in changed}) == len(changed)
        for item in changed:
            assert item["path"] and item["bytes"] > 0
            assert SHA256.fullmatch(item["sha256"])

    pins = ledger["additional_pins"]
    toolchain = pins["toolchain"]
    for path_key, hash_key in (("profile_path", "profile_sha256"),
                               ("build_report_path", "build_report_sha256"),
                               ("compiler_path", "compiler_sha256")):
        assert _sha(ROOT / toolchain[path_key]) == toolchain[hash_key]
        assert SHA256.fullmatch(toolchain[hash_key])
    assert toolchain["compiler_version"]
    for path_key, hash_key in (("schema_elf", "schema_elf_sha256"),
                               ("budget_path", "budget_sha256"),
                               ("bsp_inventory_path", "bsp_inventory_sha256")):
        assert _sha(ROOT / pins[path_key]) == pins[hash_key]
        assert SHA256.fullmatch(pins[hash_key])
    prefix_path = ROOT / "submodules/halo-ce-universal" / pins["schema_build_prefix"]
    assert _sha(prefix_path) == pins["schema_build_prefix_sha256"]
    assert SHA256.fullmatch(pins["schema_build_prefix_sha256"])
    assert SHA256.fullmatch(pins["schema_result_sha256"])
    assert SHA256.fullmatch(pins["schema_build_manifest_sha256"])

    # The linked schema build's translation-unit table is the build-input
    # identity: every dirty or clean source that entered this ELF must retain
    # its original hash and still match the recorded current source.
    build = ledger["schema_build_units"]
    source_identity = build["source_identity"]
    assert build["status"] == "source-hashes-match"
    assert source_identity["status"] == "current"
    assert source_identity["counts"] == {"match": build["compiled_count"],
                                          "changed": 0, "missing": 0}
    assert source_identity["unit_count"] == build["compiled_count"] == build["count"]
    assert build["failed_count"] == 0
    assert not build["source_hash_mismatches"]
    assert not build["source_files_missing"]
    for unit in source_identity["units"]:
        assert SHA256.fullmatch(unit["built_source_sha256"])
        assert unit["current_source_sha256"] == unit["built_source_sha256"]
        assert SHA256.fullmatch(unit["object_sha256"])
        source = ROOT / "submodules/halo-ce-universal" / unit["path"]
        assert _sha(source) == unit["built_source_sha256"]

    # Retail map fixtures and generated packages are represented as path/hash
    # identities; check that the scope includes all stock MP maps.
    map_paths = {item["path"] for item in ledger["source_maps"]}
    stock_maps = {"beavercreek", "bloodgulch", "boardingaction", "carousel",
                  "chillout", "damnation", "hangemhigh", "longest", "prisoner",
                  "putput", "ratrace", "sidewinder", "wizard"}
    assert all(any(Path(path).stem == name and "decompressed" in Path(path).parts
                   for path in map_paths) for name in stock_maps)
    assert ledger["generated_packages"]
    for item in [*ledger["source_maps"], *ledger["generated_packages"]]:
        assert item["bytes"] > 0
        assert SHA256.fullmatch(item["sha256"])
    provenance = ledger["package_provenance"]
    assert _sha(ROOT / provenance["path"]) == provenance["sha256"]
    assert provenance["summary"]["package_count"] >= len(ledger["generated_packages"])

