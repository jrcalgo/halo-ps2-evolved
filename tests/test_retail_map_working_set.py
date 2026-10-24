from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from audit_retail_map_working_set import audit  # noqa: E402


def _inputs(tag_bytes=100, projected=50, raw=75):
    ctag = {
        "format": "retail-ctag-compaction-audit-v1",
        "schema_elf_sha256": "same-elf",
        "maps": [{"map": "test", "source_sha256": "same-map",
                  "image_size": tag_bytes}],
    }
    bsp = {
        "format": "retail-ce-bsp-schema-audit-v4",
        "schema_elf_sha256": "same-elf",
        "maps": [{"map": "test", "source_sha256": "same-map",
                  "structure_bsps": [
            {"raw_bytes": raw,
             "bytes_if_compressed_vertices_externalized": projected},
            {"raw_bytes": raw - 1,
             "bytes_if_compressed_vertices_externalized": projected - 1},
        ]}],
    }
    schema = {
        "format": "retail-ctag-coverage-audit-v3",
        "schema_elf_sha256": "same-elf",
        "maps": [{"map": "test.map", "source_sha256": "same-map",
                  "schema_visited_bytes_lower_bound": tag_bytes - 1,
                  "in_image_data_bytes_by_owner": {"animation.data": 25},
                  "in_image_data_maximum_record_bytes_by_owner": {"animation.data": 5}}],
    }
    budget = {"regions": [
        {"name": "resident_gameplay", "bytes": 100},
        {"name": "current_bsp", "bytes": 100},
    ]}
    return ctag, schema, bsp, budget


def test_working_set_uses_largest_bsp_and_distinguishes_sum_from_placement():
    result = audit(*_inputs(tag_bytes=100, projected=150, raw=175))
    row = result["maps"][0]
    assert row["largest_raw_active_bsp_bytes"] == 175
    assert row["largest_projected_active_bsp_bytes"] == 150
    assert row["tag_plus_projected_bsp_bytes"] == 250
    assert not row["tag_plus_projected_bsp_fits_combined_regions"]
    assert result["lower_bound_over_combined_regions"] == 1
    assert row["schema_visited_tag_bytes_lower_bound"] == 99
    assert row["animation_data_bytes_candidate_externalization"] == 25
    assert row["largest_animation_data_record_bytes"] == 5
    assert row["tag_image_bytes_after_animation_data_externalization"] == 75
    assert row["tag_after_animation_plus_projected_bsp_bytes"] == 225
    assert not row["animation_candidate_fits_combined_regions"]
    assert row["schema_lower_bound_after_animation_externalization_bytes"] == 74
    assert row["schema_after_animation_plus_projected_bsp_bytes"] == 224
    assert not row["schema_animation_candidate_fits_combined_regions"]
    assert result["schema_animation_candidate_over_combined_regions"] == 1


def test_working_set_rejects_reports_from_different_schema_builds():
    ctag, schema, bsp, budget = _inputs()
    bsp["schema_elf_sha256"] = "different-elf"
    try:
        audit(ctag, schema, bsp, budget)
    except ValueError as error:
        assert "different schema ELFs" in str(error)
    else:
        raise AssertionError("mixed-schema reports were accepted")


def test_working_set_rejects_different_map_corpora():
    ctag, schema, bsp, budget = _inputs()
    bsp["maps"][0]["map"] = "other"
    try:
        audit(ctag, schema, bsp, budget)
    except ValueError as error:
        assert "same nonempty map set" in str(error)
    else:
        raise AssertionError("different map corpora were accepted")


def test_working_set_rejects_different_source_map_hashes():
    ctag, schema, bsp, budget = _inputs()
    schema["maps"][0]["source_sha256"] = "different-map"
    try:
        audit(ctag, schema, bsp, budget)
    except ValueError as error:
        assert "different source maps" in str(error)
    else:
        raise AssertionError("reports from different source maps were accepted")
