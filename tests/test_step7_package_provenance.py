import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

from tools import audit_step7_package_provenance as provenance  # noqa: E402
from tools import generate_hcu_step7_step8_closure as closure  # noqa: E402
import hmap  # noqa: E402
from ctag import _hp2_module  # noqa: E402


def test_hp2_hmap_binds_exact_available_map_and_labels_recipe_limits(tmp_path, monkeypatch):
    monkeypatch.setattr(provenance, "ROOT", tmp_path)
    map_root = tmp_path / "maps"
    package_root = tmp_path / "packages"
    report_root = tmp_path / "reports"
    for folder in (map_root, package_root, report_root):
        folder.mkdir()
    (tmp_path / "tools").mkdir()
    (tmp_path / "tools/pack_retail_ctag_hp2.py").write_text("# fixture producer\n")
    (tmp_path / "schema.elf").write_bytes(b"fixture schema")
    source = map_root / "fixture.map"
    source_bytes = b"fixture source cache bytes"
    source.write_bytes(source_bytes)
    source_hash = hashlib.sha256(source_bytes).digest()
    identity = hmap.encode("fixture", len(source_bytes), 1, len(source_bytes) - 1,
                           source_hash)
    hp2 = _hp2_module()
    package = package_root / "fixture.hp2"
    package_bytes = hp2.build("fixture", [("HMAP", identity), ("DATA", b"payload")])
    package.write_bytes(package_bytes)
    package_sha = hashlib.sha256(package_bytes).hexdigest()
    (report_root / "recipe.md").write_text(
        "```sh\npython3 tools/pack_retail_ctag_hp2.py maps/fixture.map "
        "schema.elf packages/fixture.hp2\n```\n\n"
        f"Output SHA256: {package_sha}\n")

    result = provenance.build_manifest([package_root], [map_root], [report_root])
    assert result["package_count"] == 1
    item = result["packages"][0]
    assert item["sha256"] == package_sha
    assert item["hmap_input"]["source_map_sha256"] == source_hash.hex()
    assert item["hmap_input"]["source_map_paths"] == ["maps/fixture.map"]
    assert item["hmap_input"]["source_map_binding"] == "unique-exact-content-match"
    assert item["producer_binding"].startswith(
        "historical-command-output-and-argument-files-bound")
    assert item["producer_capability"]["historical_producer_claim"] is False
    pin = item["historical_output_hash_pins"][0]
    assert pin["path"] == "reports/recipe.md"
    assert pin["exact_output_hash_pin"] is True
    assert pin["nearby_command_text"]
    assert item["historical_invocation_bindings"][0]["command_file_bindings"]
    assert item["producer_binding"].startswith("historical-command-output-and-argument-files-bound")


def test_manifest_does_not_guess_missing_or_ambiguous_source_maps(tmp_path, monkeypatch):
    monkeypatch.setattr(provenance, "ROOT", tmp_path)
    maps = tmp_path / "maps"
    packages = tmp_path / "packages"
    maps.mkdir()
    packages.mkdir()
    source = b"not-installed-map-bytes"
    hmap_payload = hmap.encode("missing", len(source), 0, len(source),
                               hashlib.sha256(source).digest())
    hp2 = _hp2_module()
    package = packages / "missing.hp2"
    package.write_bytes(hp2.build("missing", [("HMAP", hmap_payload)]))

    result = provenance.build_manifest([packages], [maps], [])
    item = result["packages"][0]
    assert item["hmap_input"]["source_map_binding"] == "source-map-bytes-not-present"
    assert item["producer_binding"] == "embedded-source-digest-only; source-bytes-unavailable"
    assert item["historical_output_hash_pins"] == []


def test_manifest_json_output_is_machine_readable(tmp_path, monkeypatch):
    monkeypatch.setattr(provenance, "ROOT", tmp_path)
    output = tmp_path / "provenance.json"
    empty = provenance.build_manifest([], [], [])
    output.write_text(json.dumps(empty))
    assert json.loads(output.read_text())["package_count"] == 0


def test_ledger_package_provenance_pins_sidecar_and_keeps_recipes_open(tmp_path):
    sidecar = tmp_path / "packages.json"
    manifest = {
        "format": "hcu-step7-step8-package-provenance-v1",
        "package_count": 2,
        "limitation": "Schema and historical optional inputs remain unresolved.",
        "packages": [
            {"hmap_input": {"source_map_paths": ["maps/a.map"]},
             "historical_invocation_bindings": [{"command": "pinned command"}],
             "producer_binding": "historical-command-output-and-argument-files-bound; other historical inputs unresolved"},
            {"hmap_input": None, "historical_invocation_bindings": [],
             "producer_binding": "unresolved-historical-invocation"},
        ],
    }
    sidecar.write_text(json.dumps(manifest))
    identity = closure.package_provenance_identity(sidecar)
    assert identity["path"] == str(sidecar)
    assert identity["sha256"] == hashlib.sha256(sidecar.read_bytes()).hexdigest()
    assert identity["bytes"] == sidecar.stat().st_size
    assert identity["summary"] == {
        "status": "identity-pinned",
        "package_count": 2,
        "source_map_input_bound_count": 1,
        "historical_command_output_bound_count": 1,
        "complete_recipe_count": 0,
        "unresolved_recipe_count": 2,
        "limitation": "Schema and historical optional inputs remain unresolved.",
    }
    # Verify the actual ledger builder emits this dedicated field without
    # regenerating or altering the canonical ledger during the test.
    assert "package_provenance_identity" in closure.ledger.__code__.co_names
    assert any(isinstance(keys, tuple) and "package_provenance" in keys
               for keys in closure.ledger.__code__.co_consts)


def test_retained_ui_hmap_package_reproduces_with_no_bsp_flag():
    package = ROOT / "build/retail-ui-hmap.hp2"
    map_root = ROOT / "build/retail-maps/decompressed"
    schema = ROOT / "build/hcu-ps2-closure/all/halo-local.elf"
    if not package.is_file() or not map_root.is_dir() or not schema.is_file():
        import pytest
        pytest.skip("retained UI HP2, source map, or schema ELF is unavailable")
    map_by_hash = provenance.hash_index([map_root])
    record = provenance.package_record(package, map_by_hash, [])
    result = provenance._reproduce_hp2(record, map_by_hash, [schema], {})
    assert result["result"] == "byte_identical_reproduction"
    assert result["recipe"]["include_all_bsps"] is False
    assert result["recipe"]["output_sha256"] == record["sha256"]


def test_retained_package_manifest_binds_each_current_recipe_input():
    """Current reproducibility is verified without upgrading it to history."""
    report = ROOT / "docs/reports/m2-step7-step8-package-provenance-2026-10-22.json"
    manifest = json.loads(report.read_text())
    assert manifest["package_count"] == 36
    assert manifest["reproduction_verification"]["counts"] == {
        "byte_identical_reproduction": 36
    }
    assert manifest["reproduction_verification"]["historical_execution_claims"] == 0
    assert manifest["historical_invocation_coverage"] == {
        "package_path_count": 36,
        "path_specific_invocation_count": 12,
        "profile_manifest_path_specific_invocation_count": 12,
        "unresolved_path_specific_invocation_count": 24,
        "limitation": "A byte-identical sibling's command is not transferred to another path. Package recipe reproduction remains current-input evidence, not proof of historical execution.",
    }
    assert manifest["producer_binding_counts"] == {
        "historical-command-output-and-argument-files-bound; other historical inputs unresolved": 12,
        "source-map-input-bound; schema-and-invocation-unresolved": 23,
        "unresolved-historical-invocation": 1,
    }
    bound_paths = set()

    for item in manifest["packages"]:
        package = ROOT / item["path"]
        assert package.is_file(), item["path"]
        assert package.stat().st_size == item["bytes"]
        assert provenance.digest(package) == item["sha256"]
        reproduction = item["reproduction"]
        assert reproduction["result"] == "byte_identical_reproduction", item["path"]
        assert reproduction["historical_execution_claim"] is False
        recipe = reproduction["recipe"]

        for binding in item.get("historical_invocation_bindings", []):
            evidence_path = ROOT / binding["report_path"]
            assert evidence_path.is_file()
            assert provenance.digest(evidence_path) == binding["report_sha256"]
            assert binding["exact_output_sha256_pin"] is True
            assert any(source["path"] == item["path"]
                       and source["sha256"] == item["sha256"]
                       for source in binding["command_file_bindings"])
            if binding.get("json_pointer"):
                evidence = json.loads(evidence_path.read_text())
                value = evidence
                for component in binding["json_pointer"].strip("/").split("/"):
                    value = value[component]
                assert value["package_sha256"] == item["sha256"]
                assert value["source_map_sha256"] == item["hmap_input"]["source_map_sha256"]
                assert value["schema_elf_sha256"] == recipe["schema_elf_sha256"]
                bound_paths.add(item["path"])

        if item["extension"] != ".hp2" or item["path"] == "build/retail-ui-component.hp2":
            # The UI component is a projection of the retained UI HP2, not a
            # map/schema invocation. Its source package and implementation are
            # still exact, independently checked recipe inputs.
            source = ROOT / recipe["source_package_path"]
            producer = ROOT / recipe["producer_path"]
            assert source.is_file()
            assert provenance.digest(source) == recipe["source_package_sha256"]
            assert producer.is_file()
            assert provenance.digest(producer) == recipe["producer_sha256"]
            assert recipe["output_sha256"] == item["sha256"]
            continue

        source_map = ROOT / recipe["map_path"]
        schema = ROOT / recipe["schema_elf_path"]
        producer = ROOT / recipe["producer_path"]
        assert source_map.is_file()
        assert schema.is_file()
        assert producer.is_file()
        assert provenance.digest(source_map) == recipe["map_sha256"]
        assert recipe["map_sha256"] == item["hmap_input"]["source_map_sha256"]
        assert recipe["map_path"] in item["hmap_input"]["source_map_paths"]
        assert provenance.digest(schema) == recipe["schema_elf_sha256"]
        assert provenance.digest(producer) == recipe["producer_sha256"]
        assert recipe["output_sha256"] == item["sha256"]

        # Duplicate source paths are allowed only as byte-identical mirrors;
        # each reported candidate must match the package's embedded HMAP.
        for alias in item["hmap_input"]["source_map_paths"]:
            assert provenance.digest(ROOT / alias) == item["hmap_input"]["source_map_sha256"]

        section_tags = {section["tag"] for section in item["sections"]}
        assert recipe["include_all_bsps"] == (
            "CBIX" in section_tags or any(tag.startswith("B") and len(tag) == 4
                                            for tag in section_tags)
        )

    assert len(bound_paths) == 12


def test_retained_mp_profile_manifest_binds_all_stock_map_package_inputs():
    """The retained 13-map host profile pins its package/source/schema tuple."""
    import pytest

    profile_path = ROOT / "build/m2-mp-nested-census-13/manifest.json"
    provenance_path = ROOT / "docs/reports/m2-step7-step8-package-provenance-2026-10-22.json"
    if not profile_path.is_file() or not provenance_path.is_file():
        pytest.skip("retained package/profile artifacts are unavailable")
    profile = json.loads(profile_path.read_text())
    provenance_manifest = json.loads(provenance_path.read_text())
    records = {item["path"]: item for item in provenance_manifest["packages"]}

    assert profile["status"] == "passed"
    assert profile["capacity_scope"] == (
        "host semantic fixture only; not PS2/EE target memory evidence"
    )
    assert len(profile["packages"]) == 13
    assert set(profile["packages"]) == set(profile["source_maps"])
    assert set(profile["packages"]) == set(profile["package_generation"])

    command_bound = 0
    for map_name, output_hash in profile["packages"].items():
        generation = profile["package_generation"][map_name]
        assert generation["package_sha256"] == output_hash
        assert generation["source_map_sha256"] == profile["source_maps"][map_name]
        matches = [item for item in records.values()
                   if item["sha256"] == output_hash
                   and item.get("hmap_input", {}).get("map_name") == map_name]
        assert matches, map_name
        assert all(item["hmap_input"]["source_map_sha256"] == profile["source_maps"][map_name]
                   for item in matches)
        assert all(item["reproduction"]["result"] == "byte_identical_reproduction"
                   for item in matches)
        assert all(item["reproduction"]["historical_execution_claim"] is False
                   for item in matches)

        command = generation.get("command") or generation.get("generation_record", "")
        if "pack_retail_ctag_hp2.py" not in command:
            # Damnation's profile record points to its independently retained
            # wind-package manifest, which pins map/schema/output hashes but
            # does not retain the packer invocation.
            assert "damnation" == map_name
            assert command == "build/m2-mp-wind-package/manifest.json; validated MP wind package"
            continue

        import shlex
        tokens = shlex.split(command)
        assert tokens[0] == "tools/pack_retail_ctag_hp2.py"
        assert len(tokens) == 5 and tokens[4] == "--include-all-bsps"
        source_map = ROOT / tokens[1]
        schema = ROOT / tokens[2]
        output = ROOT / tokens[3]
        producer = ROOT / tokens[0]
        assert source_map.is_file() and schema.is_file() and output.is_file()
        assert provenance.digest(source_map) == profile["source_maps"][map_name]
        assert provenance.digest(schema) == generation["schema_elf_sha256"]
        assert generation["schema_elf_sha256"] == matches[0]["reproduction"]["recipe"]["schema_elf_sha256"]
        assert provenance.digest(output) == output_hash
        assert provenance.digest(producer) == matches[0]["reproduction"]["recipe"]["producer_sha256"]
        command_bound += 1

    # Twelve exact command rows and one validated-package reference: the
    # latter is not inflated into an invocation claim.
    assert command_bound == 12
