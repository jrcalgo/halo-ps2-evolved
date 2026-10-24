import json
import struct
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import ctag
from hcu_profile_chunks import encode
from hcu_profile_validate import validate
from qualify_hcu_c1 import (EXPECTED, _producer_and_source_pins, _validate_pair,
                            _requirement, _check_specs, compare_profile_builds,
                            _source_bsp_inventory, _verify_bitmap_profile_binding,
                            _audit_delta_spans, _check_root_and_special_identity,
                            _native_package_identity_errors, _audit_actor_bindings,
                            _expected_actor_occurrences, _audit_import_identities,
                            _audit_stock_mp_actor_origins, _audit_actor_source_closures,
                            _audit_special_weapon_metadata, _check_preflight_report,
                            _check_bitmap_live_dispatch, DEFAULT_SCHEMA_ELF,
                            _check_consumer_roles, sha_file)


def valid_profile_files(directory: Path, name="ui", profile_id=1):
    directory.mkdir(parents=True, exist_ok=True)
    scenario = "levels\\test\\scenario"
    name_at = 68
    root_at = (name_at + len(scenario.encode()) + 1 + 3) & ~3
    image = bytearray(root_at + 4)
    struct.pack_into("<9I", image, 0, 36, 0, 0, 1, 0, 0, 0, 0, 0x74616773)
    image[36:40] = b"rncs"
    struct.pack_into("<I", image, 48, 0)
    struct.pack_into("<II", image, 52, name_at, root_at)
    image[name_at:name_at + len(scenario) + 1] = scenario.encode() + b"\0"
    image[root_at:root_at + 4] = b"root"
    ctag_payload = ctag.encode(bytes(image), (0, 20, 28, 52, 56), scenario_tag_index=0)
    sound = json.dumps({"format": "hcu-profile-sound-metadata-v1", "sources": {}}).encode()
    package = encode(profile_id, {"ce": ctag_payload, "media": {}, "sound_meta": sound})
    schema = {"format": "hcu-schema-manifest-v1", "elf_sha256": "schema-test",
              "groups": [{"group": "scnr", "definition": 1}],
              "definitions": {"1": {"name": "scenario", "size": 4, "fields": []}}}
    package_sha = __import__("hashlib").sha256(package).hexdigest()
    manifest = {"format": "hcu-built-profile-v1", "profile": {"id": profile_id,
        "name": name, "kind": "ui", "map": "ui", "scenario": {"source": "ui",
        "group": "scnr", "path": scenario}}, "schema_elf_sha256": "schema-test",
        "package_sha256": package_sha, "dependencies": [{"output_datum": 0,
        "group": "scnr", "path": scenario, "source_key": "ui", "source_datum": 1}],
        "tag_relocations": [], "tag_index_remaps": [], "resources": [],
        "roots": [{"source": "ui", "group": "scnr", "path": scenario, "role": "scenario"}],
        "source_maps": {}, "producers": {}, "actor_bindings": [],
        "source_occurrence_remaps": [], "memory": {"resident_recipe_bytes": len(image)},
        "resource_policy": {"sound_samples": "metadata_only_spu2_unqualified"},
        "media": {"chunks": [], "bindings": [], "bitmap_catalog": [],
                  "bsp_catalog": [], "sound_metadata": {"sources": {}}}}
    manifest["validation"] = validate(package, manifest, schema,
        expected_package_sha256=package_sha, expected_profile_id=profile_id,
        expected_scenario=scenario)
    (directory / f"{name}.hcp").write_bytes(package)
    (directory / f"{name}.json").write_text(json.dumps(manifest, sort_keys=True) + "\n")
    return schema, package, manifest


def test_small_real_hcp_fixture_uses_schema_validator(tmp_path):
    schema, _package, _manifest = valid_profile_files(tmp_path)
    result, errors = _validate_pair(tmp_path, "ui", schema)
    assert not errors
    assert result["validation"]["tag_count"] == 1
    assert result["validation"]["scenario"] == "levels\\test\\scenario"


def test_package_blob_mutation_fails_validation(tmp_path):
    schema, package, _manifest = valid_profile_files(tmp_path)
    target = tmp_path / "ui.hcp"
    target.write_bytes(package + b"tamper")
    result, errors = _validate_pair(tmp_path, "ui", schema)
    assert result is None
    assert errors and ("package_sha256" in errors[0] or "HCP" in errors[0])


def test_changed_source_map_fails_pinned_provenance(tmp_path):
    source = tmp_path / "retail.map"
    source.write_bytes(b"retail-source-original")
    expected = __import__("hashlib").sha256(source.read_bytes()).hexdigest()
    manifest = {"producers": {"producer.py": "a" * 64},
                "source_maps": {"ui": {"path": "retail.map", "sha256": expected}}}
    (tmp_path / "producer.py").write_text("producer")
    source.write_bytes(b"mutated retail source")
    errors = _producer_and_source_pins(manifest, root=tmp_path)
    assert any("source map hash is stale" in error for error in errors)


def test_unmatched_profile_input_set_is_nonpass(tmp_path):
    row = _requirement(1, "test")
    specs = {"profiles": [{"name": name, "kind": kind, "map": map_name}
                           for name, kind, map_name in EXPECTED[:-1]]}
    (tmp_path / "specs.json").write_text(json.dumps(specs))
    _check_specs(tmp_path, row, None, None)
    assert row["findings"]
    assert "exact ordered" in row["findings"][0]["message"]


def test_rebuild_manifest_mutation_breaks_exact_reproducibility(tmp_path):
    first, second = tmp_path / "first", tmp_path / "second"
    valid_profile_files(first)
    valid_profile_files(second)
    manifest_path = second / "ui.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["provenance_note"] = "altered"
    manifest_path.write_text(json.dumps(manifest, sort_keys=True) + "\n")
    errors = compare_profile_builds(first, second, "ui")
    assert errors == ["independent manifest bytes differ for ui"]


def test_real_ui_and_bloodgulch_bsp_owners_have_source_extents():
    maps = ROOT / "build/retail-maps/decompressed"
    ui, bloodgulch = maps / "ui.map", maps / "bloodgulch.map"
    if not ui.is_file() or not bloodgulch.is_file():
        pytest.skip("retail UI and Blood Gulch maps are unavailable")
    ui_rows = _source_bsp_inventory(ui, "ui")
    bloodgulch_rows = _source_bsp_inventory(bloodgulch, "bloodgulch")
    assert len(ui_rows) == len(bloodgulch_rows) == 1
    assert next(iter(ui_rows))[1:3] == ("sbsp", "levels\\ui\\ui")
    assert all(row["source_file_size"] > 24 and row["source_xbox_base"] > 0
               for row in (*ui_rows.values(), *bloodgulch_rows.values()))


def test_bitmap_native_sample_must_bind_final_package_image_and_payload(tmp_path):
    source = tmp_path / "ui.map"
    source.write_bytes(b"retail ui")
    import hashlib
    source_sha = hashlib.sha256(source.read_bytes()).hexdigest()
    consumers = {}
    for field, name in (("main", "quad.c"), ("parser", "tex.c"), ("capture", "fixture.py")):
        path = tmp_path / name
        path.write_text(name)
        consumers[field] = {"path": name, "source_sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
    tex_sha = "a" * 64
    owner = {"source_key": "ui", "group": "bitm", "path": "ui\\sample",
             "source_datum": 123, "source_image_index": 2}
    meta = {"source_map": "ui.map", "source_map_sha256": source_sha,
            "source_path": owner["path"], "source_datum": owner["source_datum"],
            "source_image_index": owner["source_image_index"], "source_pixel_sha256": "b" * 64,
            "serialized_texs_sha256": tex_sha}
    profile = {"package_sha256": "c" * 64, "manifest": {
        "source_maps": {"ui": {"path": "ui.map", "sha256": source_sha}},
        "dependencies": [{"source_key": "ui", "group": "bitm", "path": owner["path"],
                          "source_datum": 123}],
        "media": {"bitmap_catalog": [{"source_key": "ui", "path": owner["path"],
            "source_datum": 123, "dispositions": [{"source_image_index": 2,
                "source_pixel_sha256": "b" * 64}]}],
            "chunks": [{"kind": "BITM", "sha256": tex_sha, "key": f"BITM:{tex_sha}",
                        "owners": [owner], "runtime_admitted": False,
                        "engine_consumer": {**consumers["main"], "parser": consumers["parser"],
                                             "capture_fixture": consumers["capture"]}}],
            "bindings": [{"kind": "BITM", "chunk_key": f"BITM:{tex_sha}", "owner": owner}]}}}
    assert _verify_bitmap_profile_binding(meta, profile, root=tmp_path) is None
    altered = {**meta, "serialized_texs_sha256": "d" * 64}
    assert "final UI BITM chunk" in _verify_bitmap_profile_binding(altered, profile, root=tmp_path)
    altered = {**meta, "source_image_index": 1}
    assert "not bound to the sampled source image" in _verify_bitmap_profile_binding(altered, profile, root=tmp_path)
    (tmp_path / "quad.c").write_text("changed consumer")
    assert "source pin is missing or stale" in _verify_bitmap_profile_binding(meta, profile, root=tmp_path)


def test_correction_delta_bytes_are_recomputed_and_overlap_rejected():
    valid = {"format": "hcu-validator-byte-deltas-v1", "image_size": 16,
             "changed_bytes": 3, "span_count": 2,
             "spans": [{"offset": 1, "before_hex": "0001", "after_hex": "0201"},
                       {"offset": 8, "before_hex": "aa", "after_hex": "bb"}]}
    changed, errors = _audit_delta_spans(valid)
    assert changed == 2
    assert errors  # Declared total is inconsistent with the actual changed bytes.
    valid["changed_bytes"] = 2
    changed, errors = _audit_delta_spans(valid)
    assert changed == 2 and not errors
    valid["spans"].append({"offset": 8, "before_hex": "cc", "after_hex": "dd"})
    assert any("overlapping" in error for error in _audit_delta_spans(valid)[1])


def test_special_weapon_roots_require_full_separately_sourced_closures(tmp_path):
    weapon = {"weapon_roots": {
        "energy_sword": {"source_map": "a50.map", "source_map_sha256": "a" * 64,
            "root_tag": {"group": "weap", "path": "weapon\\sword"},
            "dependencies_by_group": {"weap": ["weapon\\sword"], "bitm": ["weapon\\sword\\bitmap"]}},
        "gravity_rifle": {"source_map": "bloodgulch.map", "source_map_sha256": "b" * 64,
            "root_tag": {"group": "weap", "path": "weapon\\gravity"},
            "dependencies_by_group": {"weap": ["weapon\\gravity"]}},
        "fuel_rod": {"source_map": "c40.map", "source_map_sha256": "c" * 64,
            "root_tag": {"group": "weap", "path": "weapon\\fuel"},
            "dependencies_by_group": {"weap": ["weapon\\fuel"]}}},
        "presentation_provenance": {"adapter_files": {}, "energy_sword": {},
                                    "gravity_rifle": {}, "fuel_rod": {}}}
    manifest = {"profile": {"map": "beavercreek", "scenario": {"path": "scenario"}},
        "roots": [{"source": "beavercreek", "group": "scnr", "path": "scenario"},
                  {"source": "a50", "group": "weap", "path": "weapon\\sword",
                   "role": "special_weapon:energy_sword"},
                  {"source": "bloodgulch", "group": "weap", "path": "weapon\\gravity",
                   "role": "special_weapon:gravity_rifle"},
                  {"source": "c40", "group": "weap", "path": "weapon\\fuel",
                   "role": "special_weapon:fuel_rod"}],
        "dependencies": [{"source_key": "a50", "group": "weap", "path": "weapon\\sword"}],
        "source_maps": {"a50": {"path": "a50.map", "sha256": "a" * 64},
                        "bloodgulch": {"path": "bloodgulch.map", "sha256": "b" * 64},
                        "c40": {"path": "c40.map", "sha256": "c" * 64}}}
    errors = _check_root_and_special_identity("survival-beavercreek", manifest, weapon, root=tmp_path)
    assert any("closure is incomplete" in error for error in errors)
    assert any("presentation adapter source pins" in error for error in errors)


@pytest.mark.parametrize("name", ["ui", "bots-chillout"])
def test_actual_profile_special_identity_uses_workspace_root_without_path_error(name):
    directory = ROOT / "build/m2-c1-corpus-primary-v1"
    manifest_path = directory / f"{name}.json"
    weapon_path = ROOT / "docs/reports/m2-c1-special-weapons-2026-10-23.json"
    if not manifest_path.is_file():
        pytest.skip(f"current C1 profile fixture is unavailable: {name}")
    errors = _check_root_and_special_identity(name, json.loads(manifest_path.read_text()),
        json.loads(weapon_path.read_text()), root=ROOT)
    assert isinstance(errors, list)
    assert not any("presentation adapter input is missing or stale" in error for error in errors)


def test_actor_recipes_must_match_full_retained_roster_and_required_fields():
    roster = json.loads((ROOT / "docs/reports/m2-c1-actor-roster-2026-10-23.json").read_text())
    expected = _expected_actor_occurrences(roster)
    recipes = {}
    for variant in roster["variants"]:
        identity = (variant["map"], variant["path"], variant["datum"])
        if variant.get("disposition") == "combat" and variant.get("recipe"):
            recipes[(*identity, "combat_variant")] = variant["recipe"]
        for recipe in variant.get("mounted_recipes", []):
            recipes[(*identity, "mounted_variant")] = recipe
    bindings, remaps, dependencies = [], [], []
    recipe_outputs = {}
    def bind_recipe(value):
        if isinstance(value, list):
            return [bind_recipe(item) for item in value]
        if isinstance(value, dict):
            result = {key: bind_recipe(item) for key, item in value.items()}
            if value.get("group") and value.get("path"):
                identity = (value["group"], value["path"])
                if identity not in recipe_outputs:
                    recipe_outputs[identity] = 10000 + len(recipe_outputs)
                    dependencies.append({"group": identity[0], "path": identity[1],
                                         "output_datum": recipe_outputs[identity]})
                result["output_datum"] = recipe_outputs[identity]
            return result
        return value
    for output_datum, (source, path, source_datum, role) in enumerate(sorted(expected), 1):
        raw = recipes[(source, path, source_datum, role)]
        bindings.append({"source_key": source, "path": path, "output_datum": output_datum,
                         "role": role, "recipe": bind_recipe(raw)})
        remaps.append({"source_key": source, "path": path, "group": "actv",
                       "source_datum": source_datum, "output_datum": output_datum})
        dependencies.append({"group": "actv", "path": path, "output_datum": output_datum})
    manifest = {"actor_bindings": bindings, "source_occurrence_remaps": remaps,
                "dependencies": dependencies}
    row = _requirement(2, "actor recipes")
    _audit_actor_bindings("fixture", manifest, expected, row, roster=roster)
    assert not row["findings"]
    assert row["measurements"]["actor_occurrence_bindings"]["fixture"] == 255

    # Removing a required retained recipe field cannot pass merely because the
    # binding remains present and otherwise references a valid output actor.
    broken = json.loads(json.dumps(manifest))
    next(item for item in broken["actor_bindings"] if item["role"] == "combat_variant")["recipe"]["actor"] = None
    failed = _requirement(2, "actor recipes")
    _audit_actor_bindings("fixture", broken, expected, failed, roster=roster)
    assert any("lacks required fields" in finding["message"] for finding in failed["findings"])


def test_c1_import_identity_audit_rejects_ambiguous_source_choices():
    dep = {"output_datum": 4, "group": "actv", "path": "actors\\marine",
           "source_key": "bloodgulch", "stable_key": "actv:actors\\marine#abc",
           "source_aliases": ["bloodgulch"], "conflicts": []}
    valid = {"dependencies": [dep], "decisions": [{"output_datum": 4,
                 "stable_key": dep["stable_key"], "canonical_source": dep["source_key"],
                 "source_aliases": dep["source_aliases"], "conflicts": [], "decision": "retained"}],
             "source_occurrence_remaps": [{"source_key": "bloodgulch", "group": "actv",
                 "path": "actors\\marine", "source_datum": 99, "output_datum": 4}]}
    assert _audit_import_identities("fixture", valid) == []
    duplicated = json.loads(json.dumps(valid))
    conflicting_dep = {**dep, "output_datum": 5}
    duplicated["dependencies"].append(conflicting_dep)
    duplicated["decisions"].append({"output_datum": 5,
        "stable_key": conflicting_dep["stable_key"], "canonical_source": conflicting_dep["source_key"],
        "source_aliases": conflicting_dep["source_aliases"], "conflicts": [], "decision": "retained"})
    assert any("duplicate stable dependency identity" in error
               for error in _audit_import_identities("fixture", duplicated))


def test_stock_mp_actor_origin_must_be_in_retained_roster():
    roster = {"variants": [{"map": "chillout", "group": "actv", "path": "actors\\marine",
                            "datum": 42, "disposition": "combat"}]}
    manifest = {"profile": {"kind": "bots", "map": "chillout"}, "dependencies": [
        {"source_key": "chillout", "group": "actv", "path": "actors\\marine", "source_datum": 42}]}
    assert _audit_stock_mp_actor_origins("bots-chillout", manifest, roster) == []
    manifest["dependencies"][0]["source_datum"] = 99
    assert "not a retained retail actor occurrence" in _audit_stock_mp_actor_origins(
        "bots-chillout", manifest, roster)[0]


def test_survival_actor_source_closures_require_all_retained_dependencies():
    roster = {"variants": [{"map": "a10", "path": "actors\\marine", "datum": 10,
        "disposition": "combat", "recipe": {"variant": {}, "unit": {}, "actor": {}},
        "dependencies": [{"group": "actr", "path": "actors\\marine", "datum": 11},
                        {"group": "weap", "path": "weapons\\pistol", "datum": 12}]}]}
    manifest = {"source_occurrence_remaps": [
        {"source_key": "a10", "group": "actr", "path": "actors\\marine", "source_datum": 11},
        {"source_key": "a10", "group": "weap", "path": "weapons\\pistol", "source_datum": 12}]}
    assert _audit_actor_source_closures("survival-test", manifest, roster) == []
    manifest["source_occurrence_remaps"].pop()
    assert "actor source closure dependency is absent" in _audit_actor_source_closures(
        "survival-test", manifest, roster)[0]


def test_fuel_rod_unreadable_cube_layouts_need_checked_optional_reflection_disposition():
    report = {"visual_admitted": True,
        "presentation_policy": "Base/diffuse admitted; optional cube-map environment reflections omitted. No full visual parity claim.",
        "presentation_provenance": {"fuel_rod": {"pose": "arms only",
            "policy": "CE FP model/animation refs null; no FP weapon graph"}},
        "undecodable_reached_records": [{"decodable": False, "path": "vehicle\\reflection",
            "presentation_policy": "omit optional environment reflection layer; preserve base/diffuse materials",
            "cube_storage": {"extent_valid": True, "actual_extent_bytes": 16896,
                             "expected_extent_bytes": 16896, "faces": 6,
                             "mip_levels_per_face": 7}},
            {"decodable": False, "path": "character\\reflection",
             "presentation_policy": "omit optional environment reflection layer; preserve base/diffuse materials",
             "cube_storage": {"extent_valid": True, "actual_extent_bytes": 66048,
                              "expected_extent_bytes": 66048, "faces": 6,
                              "mip_levels_per_face": 7}}]}
    assert _audit_special_weapon_metadata(report) == []
    report["undecodable_reached_records"][0]["cube_storage"]["extent_valid"] = False
    assert "extent-checked disposition" in _audit_special_weapon_metadata(report)[0]


def test_real_preflight_evidence_is_pinned_to_current_ui_profile_and_lifecycle_code():
    primary = ROOT / "build/m2-c1-corpus-primary-v3"
    rebuild = ROOT / "build/m2-c1-corpus-rebuild-v3"
    schema = __import__("hcu_schema_manifest").SchemaManifest(
        __import__("hcu_schema_manifest").Elf32(DEFAULT_SCHEMA_ELF)).build()
    first, first_errors = _validate_pair(primary, "ui", schema)
    second, second_errors = _validate_pair(rebuild, "ui", schema)
    if first is None or second is None or first_errors or second_errors:
        pytest.skip("current independent UI C1 packages are not available")
    result = _check_preflight_report(ROOT / "build/m2-c1-real-preflight/result.json",
        {"ui": first}, {"ui": second}, DEFAULT_SCHEMA_ELF, root=ROOT)
    assert result["errors"] == []
    assert result["metrics"]["preflight_ui_chunk_count"] > 0


def _dispatch_profiles():
    primary = ROOT / "build/m2-c1-corpus-primary-v3"
    rebuild = ROOT / "build/m2-c1-corpus-rebuild-v3"
    schema = __import__("hcu_schema_manifest").SchemaManifest(
        __import__("hcu_schema_manifest").Elf32(DEFAULT_SCHEMA_ELF)).build()
    first, first_errors = _validate_pair(primary, "ui", schema)
    second, second_errors = _validate_pair(rebuild, "ui", schema)
    if first is None or second is None or first_errors or second_errors:
        pytest.skip("current independent UI C1 packages are not available")
    return {"ui": first}, {"ui": second}


def _dispatch_report_variant(tmp_path, mutate):
    evidence = ROOT / "build/m2-c1-bitmap-live-dispatch/result.json"
    if not evidence.is_file():
        pytest.skip("native bitmap dispatch report is unavailable")
    report = json.loads(evidence.read_text())
    mutate(report)
    variant = tmp_path / "result.json"
    variant.write_text(json.dumps(report, indent=2) + "\n")
    return variant


def test_bitmap_dispatch_missing_frame_binding_is_c3_carry_over_not_open_finding():
    primary, rebuild = _dispatch_profiles()
    evidence = ROOT / "build/m2-c1-bitmap-live-dispatch/result.json"
    if not evidence.is_file():
        pytest.skip("native bitmap dispatch report is unavailable")
    result = _check_bitmap_live_dispatch(evidence, primary, rebuild, root=ROOT)
    assert result["errors"] == []
    assert result["open_findings"] == []
    assert len(result["deferred"]) == 1
    carry = result["deferred"][0]
    assert carry["gate"] == "C3" and carry["item"] == "C3.4/C3.6/C3.7"
    assert carry["decided_by"] == "user 2026-10-23"
    assert "no parent render" in carry["reason"]


def test_bitmap_dispatch_frame_binding_overclaim_is_still_an_error(tmp_path):
    primary, rebuild = _dispatch_profiles()

    def overclaim(report):
        report["actual_ce_frame_bound"] = True
        report["live_consumer_evidence"]["not_covered"] = [
            "production ps2_render.render_frame binding is not exercised"]

    variant = _dispatch_report_variant(tmp_path, overclaim)
    result = _check_bitmap_live_dispatch(variant, primary, rebuild, root=ROOT)
    assert any("claims a frame binding while listing the production frame as untested" in error
               for error in result["errors"])
    assert result["deferred"] == []


def test_bitmap_dispatch_incomplete_live_evidence_keeps_row_open(tmp_path):
    primary, rebuild = _dispatch_profiles()

    def incomplete(report):
        report["live_consumer_evidence"]["registration"] = None

    variant = _dispatch_report_variant(tmp_path, incomplete)
    result = _check_bitmap_live_dispatch(variant, primary, rebuild, root=ROOT)
    assert result["errors"] == []
    assert any("lacks complete registration" in message for message in result["open_findings"])


def test_native_ce_evidence_must_pin_final_package_manifest_and_ctag(tmp_path):
    _schema, package, manifest = valid_profile_files(tmp_path, "ui", 1)
    package_path, manifest_path = tmp_path / "ui.hcp", tmp_path / "ui.json"
    row = {"package_path": str(package_path), "manifest_path": str(manifest_path),
           "package_sha256": manifest["package_sha256"], "manifest": manifest}
    pins = {"ui_package_sha256": manifest["package_sha256"],
            "ui_manifest_sha256": __import__("hashlib").sha256(manifest_path.read_bytes()).hexdigest(),
            "ui_ctag_sha256": "0" * 64}
    errors = _native_package_identity_errors(pins, {"ui": row}, None)
    assert any("CTAG differs" in error for error in errors)
    # A mismatched package must still be rejected even if a stale report row has plausible other pins.
    pins["ui_package_sha256"] = "f" * 64
    assert any("package differs" in error for error in
               _native_package_identity_errors(pins, {"ui": row}, None))


def _consumer_fixture(tmp_path, *, bots_pin=True, bots_dropped=None, ui_pin_sha=None, blocking_rows=(),
                      elf_pin=None, counts=None):
    """Synthetic C1.4 consumer-role fixture using the builder's real manifest keys.

    One ui profile (no drops) and one bots profile that drops two distinct images of one bitmap.
    """
    elf = tmp_path / "halo-local.elf"
    elf.write_bytes(b"\x7fELF-consumer-fixture")
    exclusions = [{"class": "bitmap-no-reader", "reason": "no PS2 reader", "profile_kinds": ["bots"],
                   "match": {"definition": "bitm", "field": "bitmap", "owner_group": "bots", "role": "hud"},
                   "counts": {"bots-ratrace": 2 if counts is None else counts}}]
    exclusion_file = tmp_path / "exclusions.json"
    exclusion_file.write_text(json.dumps(exclusions))  # builder input: bare list of rows
    occurrences = [{"disposition": "live-consumer"}] * 3 + [{"disposition": "excluded-by-proven-profile-policy"}] + \
        [{"disposition": "drop-no-ps2-reader"}] + list(blocking_rows)
    report = {"rule": "a bitmap class is live only with a real non-stub PS2 reader",
              "elf_inputs": {str(elf): elf_pin or sha_file(elf)},
              "occurrences": occurrences, "required_profile_exclusions": exclusions,
              "deferred_to": ["C3"]}
    report_file = tmp_path / "roles.json"
    report_file.write_text(json.dumps(report))
    pin_sha = sha_file(exclusion_file)
    ui = {"profile": {"kind": "ui"}, "source_inputs": {"consumer_exclusions": {
              "path": str(exclusion_file), "sha256": ui_pin_sha or pin_sha}},
          "media": {"bitmap_catalog": [], "consumer_exclusions": [],
                    "consumer_exclusion_policy": {"path": str(exclusion_file), "sha256": pin_sha,
                                                  "profile_kind": "ui", "rows": exclusions}}}
    if bots_dropped is None:
        bots_dropped = [(0,), (1,)]  # two distinct images of one bitmap
    catalog, records = [], []
    for datum_source, indexes in ((("a50", 3870426430), bots_dropped),):
        if not indexes:
            continue
        source_key, source_datum = datum_source
        catalog.append({"source_key": source_key, "source_datum": source_datum, "dispositions": [
            {"source_key": source_key, "source_datum": source_datum, "source_image_index": index[0],
             "disposition": "excluded_by_consumer_exclusion", "exclusion_sha256": pin_sha}
            for index in indexes]})
        records.append({"source_key": source_key, "source_datum": source_datum, "output_datum": 57,
                        "image_count": len(indexes), "dropped_source_images": [index[0] for index in indexes]})
    bots = {"profile": {"kind": "bots"}, "media": {
        "bitmap_catalog": catalog, "consumer_exclusions": records,
        "consumer_exclusion_policy": {"path": str(exclusion_file), "sha256": pin_sha,
                                      "profile_kind": "bots", "rows": exclusions}}}
    if bots_pin:
        bots["source_inputs"] = {"consumer_exclusions": {"path": str(exclusion_file), "sha256": pin_sha}}
    return report_file, {"ui": {"manifest": ui}, "bots-ratrace": {"manifest": bots}}


def test_consumer_roles_pass_reconciles_pins_counts_and_metrics(tmp_path):
    report, profiles = _consumer_fixture(tmp_path)
    result = _check_consumer_roles(report, profiles, root=tmp_path)
    assert result["errors"] == []
    assert result["open_findings"] == []
    kinds = result["metrics"]["per_profile_kind"]
    assert kinds["bots"] == {"profiles": 1, "live": 3, "excluded": 2}
    assert kinds["ui"] == {"profiles": 1, "live": 3, "excluded": 0}
    assert result["metrics"]["report_occurrences"] == {"live": 3, "excluded": 1, "dropped": 1, "blocking": 0}


def test_consumer_roles_distinct_images_not_row_sums_reconcile(tmp_path):
    # Two rows cover the same two images; counts are distinct images per profile, so both rows state 2.
    report, profiles = _consumer_fixture(tmp_path, counts=2)
    result = _check_consumer_roles(report, profiles, root=tmp_path)
    assert result["errors"] == []


def test_consumer_roles_duplicate_dropped_image_is_error(tmp_path):
    report, profiles = _consumer_fixture(tmp_path, bots_dropped=[(0,), (0,)])
    result = _check_consumer_roles(report, profiles, root=tmp_path)
    assert any("dropped more than once" in error for error in result["errors"])


def test_consumer_roles_records_must_agree_with_dispositions(tmp_path):
    report, profiles = _consumer_fixture(tmp_path)
    profiles["bots-ratrace"]["manifest"]["media"]["consumer_exclusions"][0]["dropped_source_images"] = [0]
    result = _check_consumer_roles(report, profiles, root=tmp_path)
    assert any("consumer_exclusions records disagree" in error for error in result["errors"])


def test_consumer_roles_policy_sha_must_match_pin(tmp_path):
    report, profiles = _consumer_fixture(tmp_path)
    profiles["bots-ratrace"]["manifest"]["media"]["consumer_exclusion_policy"]["sha256"] = "f" * 64
    result = _check_consumer_roles(report, profiles, root=tmp_path)
    assert any("consumer_exclusion_policy does not match" in error for error in result["errors"])


def test_consumer_roles_inconsistent_counts_across_rows_fail(tmp_path):
    report, profiles = _consumer_fixture(tmp_path)
    report_data = json.loads(report.read_text())
    report_data["required_profile_exclusions"].append({
        "class": "other", "reason": "r", "profile_kinds": ["bots"], "match": {}, "counts": {"bots-ratrace": 1}})
    report.write_text(json.dumps(report_data))
    result = _check_consumer_roles(report, profiles, root=tmp_path)
    assert any("disagree across rows" in error for error in result["errors"])


def test_consumer_roles_stale_elf_pin_is_reported_as_stale_audit(tmp_path):
    report, profiles = _consumer_fixture(tmp_path, elf_pin="0" * 64)
    result = _check_consumer_roles(report, profiles, root=tmp_path)
    assert any(error.startswith("stale consumer audit") for error in result["errors"])


def test_consumer_roles_blocking_or_undecided_row_fails_closed(tmp_path):
    report, profiles = _consumer_fixture(tmp_path, blocking_rows=[{"disposition": "blocking"},
                                                                   {"note": "no disposition"}])
    result = _check_consumer_roles(report, profiles, root=tmp_path)
    assert any("blocking or undecided dispositions: 2" in error for error in result["errors"])


def test_consumer_roles_missing_manifest_pin_is_open_finding(tmp_path):
    report, profiles = _consumer_fixture(tmp_path, bots_pin=False)
    result = _check_consumer_roles(report, profiles, root=tmp_path)
    assert result["errors"] == []
    assert result["open_findings"] == ["profiles were built without the consumer exclusions"]


def test_consumer_roles_count_mismatch_between_manifest_and_report_fails(tmp_path):
    report, profiles = _consumer_fixture(tmp_path, bots_dropped=[(0,)])
    result = _check_consumer_roles(report, profiles, root=tmp_path)
    assert any("manifest removed 1 distinct dropped images but report counts 2" in error
               for error in result["errors"])


def test_consumer_roles_pin_must_match_across_profiles(tmp_path):
    report, profiles = _consumer_fixture(tmp_path, ui_pin_sha="f" * 64)
    result = _check_consumer_roles(report, profiles, root=tmp_path)
    assert any("different consumer exclusion inputs" in error for error in result["errors"])


_MISSING = object()
_FRAME_ITEM = "production ps2_render.render_frame binding is not exercised"


def _synthetic_ui_profiles(tmp_path):
    _schema, package, manifest = valid_profile_files(tmp_path, "ui", 1)
    return {"ui": {"manifest": manifest, "package_path": str(tmp_path / "ui.hcp"),
                   "manifest_path": str(tmp_path / "ui.json"),
                   "package_sha256": manifest["package_sha256"]}}


def _frame_scope_result(tmp_path, *, bound, not_covered):
    profiles = _synthetic_ui_profiles(tmp_path)
    report = {"schema": "hcu-c1-bitmap-live-dispatch-v1", "status": "host_qualified",
              "returncode": 0, "stderr": "", "runtime_admitted": False,
              "pre_fence_evidence": True,
              "live_consumer_evidence": {"not_covered": not_covered}}
    if bound is not _MISSING:
        report["actual_ce_frame_bound"] = bound
    path = tmp_path / "frame_scope_result.json"
    path.write_text(json.dumps(report, indent=2) + "\n")
    return _check_bitmap_live_dispatch(path, profiles, None, root=tmp_path)


FRAME_SCOPE_ERROR = "native bitmap dispatch report does not state its frame-binding scope"


def test_bitmap_dispatch_missing_frame_binding_field_is_error(tmp_path):
    result = _frame_scope_result(tmp_path, bound=_MISSING, not_covered=[_FRAME_ITEM])
    assert FRAME_SCOPE_ERROR in result["errors"]
    assert result["deferred"] == []


@pytest.mark.parametrize("value", [None, "false", 0])
def test_bitmap_dispatch_non_boolean_frame_binding_field_is_error(tmp_path, value):
    result = _frame_scope_result(tmp_path, bound=value, not_covered=[_FRAME_ITEM])
    assert FRAME_SCOPE_ERROR in result["errors"]
    assert result["deferred"] == []


def test_bitmap_dispatch_explicit_false_with_frame_item_is_deferred(tmp_path):
    result = _frame_scope_result(tmp_path, bound=False, not_covered=[_FRAME_ITEM])
    assert FRAME_SCOPE_ERROR not in result["errors"]
    assert len(result["deferred"]) == 1
    carry = result["deferred"][0]
    assert carry["gate"] == "C3" and carry["item"] == "C3.4/C3.6/C3.7"
    assert carry["decided_by"] == "user 2026-10-23"


def test_bitmap_dispatch_explicit_false_without_frame_item_is_error(tmp_path):
    result = _frame_scope_result(tmp_path, bound=False, not_covered=["unrelated gap"])
    assert FRAME_SCOPE_ERROR in result["errors"]
    assert result["deferred"] == []
