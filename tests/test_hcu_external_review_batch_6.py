import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HCU = ROOT / "submodules/halo-ce-universal"
BATCH = ROOT / "docs/hcu-source-backed-review/batches/batch-6.json"
REVIEW = ROOT / "docs/hcu-source-backed-review/hcu-ps2-batch-6-review.md"
SKIP = ROOT / "docs/hcu-source-backed-review/batches/batch-6-skip.txt"
class _PortC:
    def read_text(self):
        return "\n".join(path.read_text() for path in sorted((HCU / "port/ps2/src").glob("ps2_*.c")))

OWNER_C = _PortC()
LEDGER = ROOT / "docs/hcu-source-backed-review/hcu-ps2-external-review.json"

ASSIGNED = [
    "rasterizer_widget_draw_sprite3d",
    "rasterizer_widget_end",
    "rasterizer_widget_set_texture",
    "rasterizer_widget_submit",
    "rasterizer_window_begin",
    "rasterizer_window_end",
    "rasterizer_windows_begin",
    "rasterizer_windows_end",
    "render",
    "render_contrails_enabled",
    "render_dispose",
    "render_dispose_from_old_map",
    "render_effects",
    "render_fov_vertical",
    "render_frame",
    "render_frame_pregame",
    "render_frame_present",
    "render_initialize",
    "render_initialize_for_new_map",
    "render_interpolation_camera",
    "render_interpolation_fraction",
    "render_interpolation_frame_begin",
    "render_interpolation_frame_end",
    "render_interpolation_object_node_matrices",
    "render_interpolation_reset",
    "render_interpolation_tick",
    "render_particle_systems_enabled",
    "render_particles_enabled",
    "render_shadows",
    "render_weather_particle_systems_enabled",
    "reset_last_player1_profile_index",
    "rint",
]

DISPOSITIONS = {"implemented", "state-adapter", "excluded-proven"}
TEST_NAME = (
    "tests/test_hcu_external_review_batch_6.py::"
    "test_batch_6_rooted_symbols_are_dispositioned"
)

# Approved contracts (implemented / state-adapter) must appear in live source.
CONTRACT_SNIPPETS = {
    "rasterizer_widget_set_texture": (
        OWNER_C, "return FALSE;"),
    "render": (
        OWNER_C, "struct render_globals render;"),
    "render_contrails_enabled": (
        OWNER_C, "boolean render_contrails_enabled = TRUE;"),
    "render_dispose": (
        OWNER_C, "cached_object_render_states = NULL;"),
    "render_dispose_from_old_map": (
        OWNER_C, "data_make_invalid(cached_object_render_states);"),
    "render_effects": (
        OWNER_C, "render_contrails_enabled = enable;"),
    "render_fov_vertical": (
        OWNER_C, "return native_vertical_field_of_view;"),
    "render_frame": (
        OWNER_C, "render.frame_index++;"),
    "render_frame_pregame": (
        OWNER_C, "void render_frame_pregame("),
    "render_initialize": (
        OWNER_C, '"cached object render states"'),
    "render_initialize_for_new_map": (
        OWNER_C, "models_fix_transparent_part_links();"),
    "render_interpolation_camera": (
        OWNER_C, "return observer;"),
    "render_interpolation_fraction": (
        OWNER_C, "return 1.0f;"),
    "render_interpolation_frame_begin": (
        OWNER_C, "void render_interpolation_frame_begin("),
    "render_interpolation_frame_end": (
        OWNER_C, "void render_interpolation_frame_end("),
    "render_interpolation_object_node_matrices": (
        OWNER_C, "return NULL;"),
    "render_interpolation_reset": (
        OWNER_C, "void render_interpolation_reset("),
    "render_interpolation_tick": (
        OWNER_C, "void render_interpolation_tick("),
    "render_particle_systems_enabled": (
        OWNER_C, "boolean render_particle_systems_enabled = TRUE;"),
    "render_particles_enabled": (
        OWNER_C, "boolean render_particles_enabled = TRUE;"),
    "render_shadows": (
        OWNER_C, "boolean render_shadows = TRUE;"),
    "render_weather_particle_systems_enabled": (
        OWNER_C, "boolean render_weather_particle_systems_enabled = TRUE;"),
    "reset_last_player1_profile_index": (
        OWNER_C, "last_player1_profile_index = NONE;"),
    "rint": (
        HCU / "source/cseries/cseries.h",
        "result = (long)__builtin_rint((double)value);"),
}


def test_batch_6_rooted_symbols_are_dispositioned():
    rows = json.loads(BATCH.read_text())
    review = REVIEW.read_text()
    owner_c = OWNER_C.read_text()
    skip = [line for line in SKIP.read_text().splitlines() if line.strip()]
    ledger = json.loads(LEDGER.read_text())
    assert set(rows) == set(ASSIGNED)
    assert len(ASSIGNED) == 32

    for name in ASSIGNED:
        assert ledger["symbols"][name]["disposition"] == rows[name]["disposition"]
        assert ledger["symbols"][name]["evidence"] == rows[name]["evidence"]
        row = rows[name]
        assert row["disposition"] in DISPOSITIONS, name
        assert row["owner"], name
        assert row["reason"], name
        assert row["evidence"], name
        assert "hcu-ps2-batch-6-review.md" in row["evidence"], name
        assert row["test"] == TEST_NAME, name
        assert f"`{name}`" in review, name

    for name, row in rows.items():
        if row["disposition"] in {"implemented", "state-adapter"}:
            path, snippet = CONTRACT_SNIPPETS[name]
            text = path.read_text()
            assert snippet in text, f"{name}: {snippet} not in {path}"

    for symbol in skip:
        assert symbol in owner_c, symbol
    assert "return FALSE;" in owner_c[owner_c.index("rasterizer_widget_set_texture"):]
    assert "boolean render_contrails_enabled = TRUE;" in owner_c
    assert "return observer;" in owner_c
    assert "return native_vertical_field_of_view;" in owner_c
    assert "last_player1_profile_index = NONE;" in owner_c

    link_map = (ROOT / "build/hcu-ps2-closure/all/halo-local.map").read_text()
    assert "libm_a-s_rint.o" in link_map
    assert "                rint" in link_map

    particles = (HCU / "source/effects/particles.c").read_text()
    assert "particle->last_rendered_frame_index = render.frame_index;" in particles
    main = (HCU / "source/main/main.c").read_text()
    assert "observer = render_interpolation_camera(window->local_player_index, observer);" in main
    assert "render.camera = window_parameters.camera;" in main
    hs = (HCU / "source/hs/hs_globals_external.c").read_text()
    assert "&render_contrails_enabled" in hs
    assert "&render_shadows" in hs
    editor = (HCU / "source/camera/editor_flying_camera.c").read_text()
    assert "struct render_globals *editor_custom_render = &render;" in editor
