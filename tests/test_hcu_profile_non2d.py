import json
import shutil
from pathlib import Path

import pytest

from tools.audit_hcu_profile_non2d import ROOT, FIELD_RULES, audit_survival, classify, run


def test_known_ui_cube_and_volume_rows_are_gated_with_source_owners():
    out = run()
    assert out["status"] == "partial"
    assert out["runtime_admitted"] is False
    assert len(out["rows"]) == 9
    assert all(r["classification"] != "unknown_fail_closed" for r in out["rows"])
    assert all("feature_gate" in r for r in out["rows"])
    assert all(r["owners"] for r in out["rows"])
    cube = next(r for r in out["rows"] if r["path"].endswith("cubemap halo"))
    assert cube["owners"][0]["field"] == "reflection_cube_map"
    assert "sphere/environment-map render pass" in cube["replacement_if_enabled"]
    volume = next(r for r in out["rows"] if r["path"].endswith("distance attenuation"))
    assert volume["owners"][0]["group"] == "matg"
    assert "native volume/cube sampling" in volume["replacement_if_enabled"]


def test_classifier_fails_closed_on_unknown_or_changed_owner():
    assert classify("new\\bitmap", "cube", [{"group": "soso", "field": "reflection_cube_map"}])["classification"] == "unknown_fail_closed"
    assert classify("scenery\\halo\\bitmaps\\cubemap halo", "cube", [{"group": "soso", "field": "base_map"}])["classification"] == "unknown_fail_closed"
    assert classify("scenery\\halo\\bitmaps\\cubemap halo", "2d", [{"group": "soso", "field": "reflection_cube_map"}])["classification"] == "unknown_fail_closed"


def test_source_map_hash_change_invalidates_audit(tmp_path):
    original = ROOT / "build/m2-c1-profiles-ui/bitmap-stage-ui-2026-10-23/catalog.json"
    data = json.loads(original.read_text())
    # Point at a copied source map with altered bytes while keeping the pinned
    # source digest. The audit must reject it before classifying any asset.
    source = ROOT / data["source_maps"]["ui"]["path"]
    changed = tmp_path / "ui.map"
    changed.write_bytes(source.read_bytes() + b"changed")
    data["source_maps"]["ui"]["path"] = str(changed)
    catalog = tmp_path / "catalog.json"
    catalog.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="source map pin mismatch"):
        run(catalog, ROOT / "docs/reports/m2-c1-media-coverage-2026-10-23.json")


def test_report_includes_governing_source_and_output_pins():
    result = run()
    assert "plans/7.hcu-remake-m2-m4.md" in result["source_pins"]
    assert "submodules/halo-ps2/docs/11-model-section.md" in result["source_pins"]
    assert result["catalog"]["schema_elf_sha256"]


def test_survival_scan_covers_all_non2d_roles_from_exact_ctag():
    result = audit_survival(
        ROOT / "build/c3/c3-fplod/audit/survival-diag-2026-10-25-r2/survival-beavercreek.failure.json",
        ROOT / "build/c3/c3-fplod/audit/survival-diag-2026-10-25-r2/survival-beavercreek.unadmitted.ctag",
        ROOT / "build/hcu-ps2-closure/all-no-bootstrap-memory/halo-local.elf",
    )
    assert result["status"] == "partial"
    assert result["runtime_admitted"] is False
    assert result["non2d_image_occurrence_count"] == 186
    roles = {o["owner_group"] + "." + o["field"] for r in result["roles"] for o in r["owners"]}
    # The regenerated diagnostic includes the BSP-owned dependency roots (swat).
    assert roles == {f"{g}.{f}" for g, f in FIELD_RULES}
    assert all(r["owners"] and r["source_occurrences"] for r in result["roles"])
    assert all(r["classification"] == "role_gated_no_current_ps2_payload_consumer" for r in result["roles"])


def test_bsp_owned_water_reflection_has_source_backed_role():
    from tools.hcu_profile_package import classify_bitmap_role
    result = classify_bitmap_role(r"levels\a30\bitmaps\reflection noise1", 'cube',
                                 [{'group': 'swat', 'field': 'reflection_map'}])
    assert result['classification'] == 'role_gated_no_current_ps2_payload_consumer'
    assert result['feature_gate'] == ['ps2_water_reflection_consumer_absent']
    root = ROOT / 'submodules/halo-ce-universal/source/rasterizer/xbox/rasterizer_xbox_water.c'
    assert 'water->reflection_map.index' in root.read_text()
    texconv = ROOT / 'submodules/halo-ps2/tools/halo2ps2/texconv.py'
    text = texconv.read_text()
    branch = text.split('elif e.group == "swat":', 1)[1].split('else:', 1)[0]
    assert '_bitmap_ref(m, block, SWAT_MAP)' in branch
    assert 'reflection_map' not in branch


def test_survival_source_map_hash_change_invalidates_scan(tmp_path):
    diagnostic = json.loads((ROOT / "build/c3/c3-fplod/audit/survival-diag-2026-10-25-r2/survival-beavercreek.failure.json").read_text())
    first_key = sorted(diagnostic["source_maps"])[0]
    original = ROOT / diagnostic["source_maps"][first_key]["path"]
    changed = tmp_path / "changed.map"
    changed.write_bytes(original.read_bytes() + b"changed")
    diagnostic["source_maps"][first_key]["path"] = str(changed)
    diag_path = tmp_path / "diagnostic.json"
    diag_path.write_text(json.dumps(diagnostic))
    with pytest.raises(ValueError, match="source-map pin mismatch"):
        audit_survival(diag_path,
            ROOT / "build/c3/c3-fplod/audit/survival-diag-2026-10-25-r2/survival-beavercreek.unadmitted.ctag",
            ROOT / "build/hcu-ps2-closure/all-no-bootstrap-memory/halo-local.elf")
