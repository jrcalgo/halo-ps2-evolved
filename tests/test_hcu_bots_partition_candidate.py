"""Static-only accounting for the migrated bots_sidewinder partition candidate."""
import json
import hashlib
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests/fixtures/hcu_bots_sidewinder_partition_candidate.json"
PROFILE_C = ROOT / "src/stream/hcu_memory_profile.c"


def test_bots_sidewinder_candidate_provenance_and_static_accounting():
    data = json.loads(FIXTURE.read_text())
    assert data["status"] == "static-candidate-not-measured-fit"
    provenance = data["provenance"]
    assert provenance["package_sha256"] == "bdf9559fec754b9007825e133d38d1e619a730f4b8ceaa87273d1c492ef5dea3"
    assert provenance["package_manifest_file_sha256"] == "38eb0c4633bcf5b6b43a0f9b04c0bf8a95d3eefee9350d11ae808a0e8eafde02"

    inputs = data["static_inputs"]
    row = data["partition"]
    assert row["tag_cache_bytes"] == (inputs["resident_recipe_bytes"] + 15) // 16 * 16
    assert row["structure_bsp_bytes"] == (inputs["bsp_payload_bytes"] + 15) // 16 * 16
    assert row["residency_segment_bytes"] == 65536
    assert row["residency_slots"] == 16
    assert row["residency_bytes"] == row["residency_segment_bytes"] * row["residency_slots"]
    assert row["tag_cache_bytes"] + row["tag_bsp_guard_bytes"] + \
        row["structure_bsp_bytes"] + row["render_texture_bytes"] + \
        row["residency_guard_bytes"] + \
        row["residency_bytes"] == row["map_render_total_bytes"] == 10 * 1024 * 1024
    assert row["map_render_contiguous_span_bytes"] == \
        row["map_render_total_bytes"] + row["map_render_guard_bytes"] == 10 * 1024 * 1024 + 16
    assert "outside the 10 MiB combined payload capacity" in row["map_render_guard_location"]
    assert "standard guarded slack" in row["terminal_layout_guard_location"]
    assert row["claims_scratch_bytes"] == ((row["tag_cache_bytes"] + row["structure_bsp_bytes"] + 31) // 32) * 4
    assert row["resident_gameplay_static_need_bytes"] == row["game_state_bytes"] + row["claims_scratch_bytes"]
    assert row["resident_gameplay_nominal_static_margin_bytes"] == \
        row["resident_gameplay_nominal_capacity_bytes"] - row["resident_gameplay_static_need_bytes"]
    assert row["resident_gameplay_nominal_capacity_basis"] == \
        "configured region before subtracting PT_LOAD NOBITS"
    assert row["ctag_relocation_staging_bytes"] == inputs["ctag_relocation_table_bytes"]
    assert row["ctag_relocation_staging_owner"] == "streaming/map-load staging"
    assert row["relocation_table_resident"] is False
    assert row["fit_measured"] is False

    # The effective margin is analytical accounting from one exact retained ELF,
    # not a claim about the currently changing guest image.
    elf_accounting = data["last_retained_elf_accounting"]
    manifest_path = ROOT / elf_accounting["artifact_manifest"]
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text())
        assert manifest["elf_sha256"] == elf_accounting["elf_sha256"]
        assert manifest["elf_sha256"] == "ae69bb05de0068f0b2e50f136e2e7f48eb6cc1fa84b219244e98876a312da8e0"
        retained_elf = ROOT / manifest["elf"]
        assert hashlib.sha256(retained_elf.read_bytes()).hexdigest() == manifest["elf_sha256"]
        assert manifest["nobits_bytes"] == elf_accounting["nobits_bytes"] == 1811648
        effective_capacity = manifest["resident_gameplay_capacity_bytes"] - manifest["nobits_bytes"]
        assert effective_capacity == manifest["resident_after_nobits_bytes"] == 5004096
        effective_margin = effective_capacity - row["resident_gameplay_static_need_bytes"]
        assert effective_margin == elf_accounting["effective_static_margin_bytes"]
        assert effective_margin == row["resident_gameplay_last_retained_elf_effective_static_margin_bytes"] == 753416
        assert elf_accounting["current_guest_elf_must_recompute"] is True

    source = PROFILE_C.read_text()
    match = re.search(r'\{ "bots_sidewinder", \{ HCU_MEMORY_PROFILE_VERSION_1, (\d+), (\d+), (\d+), (\d+) \} \}', source)
    assert match
    assert tuple(map(int, match.groups())) == (
        row["tag_cache_bytes"], row["structure_bsp_bytes"],
        row["render_texture_bytes"], row["residency_bytes"],
    )
