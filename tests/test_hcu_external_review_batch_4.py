import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LEDGER = ROOT / "docs/hcu-source-backed-review/hcu-ps2-external-review.json"
BATCH = ROOT / "docs/hcu-source-backed-review/batches/batch-4.json"
REVIEW = ROOT / "docs/hcu-source-backed-review/hcu-ps2-batch-4-review.md"
SKIP = ROOT / "docs/hcu-source-backed-review/batches/batch-4-skip.txt"
class _PortC:
    def read_text(self):
        root = ROOT / "submodules/halo-ce-universal/port/ps2/src"
        return "\n".join(path.read_text() for path in sorted(root.glob("ps2_*.c")))

OWNER_C = _PortC()
TEST_ID = "tests/test_hcu_external_review_batch_4.py::test_batch_4_rooted_symbols_are_dispositioned"
ALLOWED = {"implemented", "state-adapter", "excluded-proven"}

CE_SNIPPETS = {
    "network_votekick_player_named": (
        "submodules/halo-ce-universal/source/hs/hs.c",
        "return network_votekick_player_named(name);",
    ),
    "pal_tags_first_person_advance": (
        "submodules/halo-ce-universal/source/interface/first_person_weapons.c",
        "if (!pal_tags_first_person_advance(local_player_index,",
    ),
    "pal_tags_first_person_frames": (
        "submodules/halo-ce-universal/source/items/weapons.c",
        "time = pal_tags_first_person_frames(weapon_definition->weapon.interface_definition.first_person_animations.index,",
    ),
    "pal_tags_loaded": (
        "submodules/halo-ce-universal/source/cache/cache_files.c",
        "pal_tags_loaded(cache_file_globals.header.build);",
    ),
    "pc_menus_screen": (
        "submodules/halo-ce-universal/source/interface/player_ui.c",
        "ui_widgets_close_all();",
    ),
    "powerup_render_bounds_tags_loaded": (
        "submodules/halo-ce-universal/port/linux/game/powerup_render_bounds.c",
        "equipment->object.render_bounding_radius = radius;",
    ),
    "process_ui_widgets": (
        "submodules/halo-ce-universal/source/main/main.c",
        "process_ui_widgets();",
    ),
    "progress_bar_dispose": (
        "submodules/halo-ce-universal/source/interface/progress_bar.c",
        "void progress_bar_dispose(",
    ),
    "progress_bar_initialize": (
        "submodules/halo-ce-universal/source/interface/progress_bar.c",
        "CopyFileA(source_path, destination_path, TRUE);",
    ),
    "qsort": (
        "submodules/halo-ce-universal/source/game/aim_assist.c",
        "qsort(targets, target_count, sizeof(struct aim_assist_target), compare_targets);",
    ),
    "rand": (
        "submodules/halo-ce-universal/source/math/random_math.c",
        "system_seconds()^system_milliseconds()^rand()",
    ),
    "rasterizer_bitmap_delete": (
        "submodules/halo-ce-universal/source/bitmaps/bitmaps.c",
        "rasterizer_bitmap_delete(bitmap);",
    ),
    "rasterizer_debug_options": (
        "submodules/halo-ce-universal/source/rasterizer/rasterizer.c",
        "TRUE, /* draw_models */",
    ),
    "rasterizer_decal_vertices_delete": (
        "submodules/halo-ce-universal/source/effects/decals.c",
        "rasterizer_decal_vertices_delete(cache_index);",
    ),
    "rasterizer_decal_vertices_lock": (
        "submodules/halo-ce-universal/source/effects/decals.c",
        "struct decal_quad *quads = rasterizer_decal_vertices_lock(",
    ),
    "rasterizer_decal_vertices_new": (
        "submodules/halo-ce-universal/source/effects/decals.c",
        "cache_index = rasterizer_decal_vertices_new(cache_size);",
    ),
    "rasterizer_decal_vertices_unlock": (
        "submodules/halo-ce-universal/source/effects/decals.c",
        "rasterizer_decal_vertices_unlock();",
    ),
    "rasterizer_decals_dispose": (
        "submodules/halo-ce-universal/source/effects/decals.c",
        "rasterizer_decals_dispose();",
    ),
    "rasterizer_decals_dispose_from_old_map": (
        "submodules/halo-ce-universal/source/effects/decals.c",
        "rasterizer_decals_dispose_from_old_map();",
    ),
    "rasterizer_decals_flush": (
        "submodules/halo-ce-universal/source/hs/hs.c",
        "HS_EVALUATE_NO_ARGUMENTS(rasterizer_decals_flush_evaluate, rasterizer_decals_flush)",
    ),
    "rasterizer_decals_initialize": (
        "submodules/halo-ce-universal/source/effects/decals.c",
        "rasterizer_decals_initialize();",
    ),
    "rasterizer_decals_initialize_for_new_map": (
        "submodules/halo-ce-universal/source/rasterizer/xbox/rasterizer_xbox_decals.c",
        "void _rasterizer_decals_initialize_for_new_map(",
    ),
    "rasterizer_decals_update_function_pointers": (
        "submodules/halo-ce-universal/source/saved games/game_state.c",
        "rasterizer_decals_update_function_pointers,",
    ),
    "rasterizer_dispose": (
        "submodules/halo-ce-universal/source/shell/shell.c",
        "rasterizer_dispose();",
    ),
    "rasterizer_dispose_from_old_map": (
        "submodules/halo-ce-universal/source/game/game.c",
        "rasterizer_dispose_from_old_map();",
    ),
    "rasterizer_dynamic_triangles_delete": (
        "submodules/halo-ce-universal/source/objects/widgets/flags.c",
        "rasterizer_dynamic_triangles_delete(triangle_buffer_index);",
    ),
    "rasterizer_dynamic_triangles_lock": (
        "submodules/halo-ce-universal/source/objects/widgets/flags.c",
        "triangles = rasterizer_dynamic_triangles_lock(triangle_buffer_index);",
    ),
    "rasterizer_dynamic_triangles_new": (
        "submodules/halo-ce-universal/source/objects/widgets/flags.c",
        "triangle_buffer_index = rasterizer_dynamic_triangles_new(maximum_triangles);",
    ),
    "rasterizer_dynamic_triangles_unlock": (
        "submodules/halo-ce-universal/source/game/game_engine_king.c",
        "rasterizer_dynamic_triangles_unlock(triangle_buffer_index);",
    ),
    "rasterizer_dynamic_unlit_geometry_draw": (
        "submodules/halo-ce-universal/source/objects/widgets/lightning.c",
        "rasterizer_dynamic_unlit_geometry_draw(",
    ),
    "rasterizer_dynamic_vertices_delete": (
        "submodules/halo-ce-universal/source/rasterizer/xbox/rasterizer_xbox_draw_primitives.c",
        "void _rasterizer_dynamic_vertices_delete(",
    ),
    "rasterizer_dynamic_vertices_lock": (
        "submodules/halo-ce-universal/source/objects/widgets/lightning.c",
        "struct lightning_vertex *vertices = rasterizer_dynamic_vertices_lock(vertex_buffer_index);",
    ),
}

CONTRACT_SNIPPETS = {
    "network_votekick_player_named": "return FALSE;",
    "pal_tags_first_person_advance": "return TRUE;",
    "pal_tags_first_person_frames": "return frames;",
    "pal_tags_loaded": "(void)build;",
    "pc_menus_screen": "return name;",
    "powerup_render_bounds_tags_loaded": "void powerup_render_bounds_tags_loaded(void)",
    "process_ui_widgets": "if (virtual_keyboard_active())",
    "progress_bar_dispose": "void progress_bar_dispose(void)",
    "progress_bar_initialize": "void progress_bar_initialize(void)",
    "rasterizer_bitmap_delete": "bitmap->hardware_format = NULL;",
    "rasterizer_debug_options": "TRUE, /* draw_models */",
    "rasterizer_decal_vertices_delete": "s_decal_slots[decal_vertex_buffer_index].used = FALSE;",
    "rasterizer_decal_vertices_lock": "return s_decal_bytes + slot->byte_start;",
    "rasterizer_decal_vertices_new": "return NONE;",
    "rasterizer_decal_vertices_unlock": "s_decal_locked = FALSE;",
    "rasterizer_decals_dispose": "s_decals_initialized = FALSE;",
    "rasterizer_decals_dispose_from_old_map": "ps2_m0_decal_reset();",
    "rasterizer_decals_flush": "ps2_m0_decal_reset();",
    "rasterizer_decals_initialize": "s_decals_initialized = TRUE;",
    "rasterizer_decals_initialize_for_new_map": "void rasterizer_decals_initialize_for_new_map(void)",
    "rasterizer_decals_update_function_pointers": "void rasterizer_decals_update_function_pointers(void)",
    "rasterizer_dispose": "rasterizer_globals.initialized = FALSE;",
    "rasterizer_dispose_from_old_map": "rasterizer_globals.default_2d_hardware_format = NULL;",
    "rasterizer_dynamic_triangles_delete": "s_dynamic_triangles[triangle_buffer_index].used = FALSE;",
    "rasterizer_dynamic_triangles_lock": "return s_dynamic_triangle_shorts + buffer->short_start;",
    "rasterizer_dynamic_triangles_new": "return NONE;",
    "rasterizer_dynamic_triangles_unlock": "s_dynamic_triangle_locks--;",
    "rasterizer_dynamic_unlit_geometry_draw": "(void)geometry_flags;",
    "rasterizer_dynamic_vertices_delete": "(void)dynamic_vertex_buffer_index;",
    "rasterizer_dynamic_vertices_lock": "return s_dynamic_vertex_bytes;",
}


# Frozen when this batch started: pending names sorted, then [128:160].
# Later batches close other pending rows, so recomputing that slice now
# is empty and is not this review's assignment.
ASSIGNED = [
    "network_votekick_player_named",
    "pal_tags_first_person_advance",
    "pal_tags_first_person_frames",
    "pal_tags_loaded",
    "pc_menus_screen",
    "powerup_render_bounds_tags_loaded",
    "process_ui_widgets",
    "progress_bar_dispose",
    "progress_bar_initialize",
    "qsort",
    "rand",
    "rasterizer_bitmap_delete",
    "rasterizer_debug_options",
    "rasterizer_decal_vertices_delete",
    "rasterizer_decal_vertices_lock",
    "rasterizer_decal_vertices_new",
    "rasterizer_decal_vertices_unlock",
    "rasterizer_decals_dispose",
    "rasterizer_decals_dispose_from_old_map",
    "rasterizer_decals_flush",
    "rasterizer_decals_initialize",
    "rasterizer_decals_initialize_for_new_map",
    "rasterizer_decals_update_function_pointers",
    "rasterizer_dispose",
    "rasterizer_dispose_from_old_map",
    "rasterizer_dynamic_triangles_delete",
    "rasterizer_dynamic_triangles_lock",
    "rasterizer_dynamic_triangles_new",
    "rasterizer_dynamic_triangles_unlock",
    "rasterizer_dynamic_unlit_geometry_draw",
    "rasterizer_dynamic_vertices_delete",
    "rasterizer_dynamic_vertices_lock",
]


def defined_symbols(source):
    names = set(re.findall(
        r"^(?:boolean|short|long|void|char const|struct rasterizer_debug_options)"
        r"\s+\*?\s*(\w+)\s*[=(]",
        source, re.M))
    return names


def test_batch_4_rooted_symbols_are_dispositioned():
    assigned = ASSIGNED
    assert assigned, "batch-4 slice [128:160] must not be empty"
    batch = json.loads(BATCH.read_text())
    ledger = json.loads(LEDGER.read_text())
    review = REVIEW.read_text()
    owner = OWNER_C.read_text()
    skip = [line.strip() for line in SKIP.read_text().splitlines() if line.strip()]
    generated = (ROOT / "build/hcu-ps2-closure/all/ps2_platform.c").read_text()
    link_map = (ROOT / "build/hcu-ps2-closure/all/halo-local.map").read_text()
    player_ui = (ROOT / "submodules/halo-ce-universal/source/interface/player_ui.c").read_text()

    assert set(batch) == set(assigned)
    assert set(skip) <= defined_symbols(owner)
    assert "qsort" not in skip and "rand" not in skip
    assert "memset(&result, 0, sizeof(result)); return result;" not in owner
    assert "TRUE, /* draw_models */" in owner
    assert "libc_a-qsort.o" in link_map
    assert "libc_a-rand.o" in link_map

    setup = player_ui[player_ui.index("void player_ui_fast_setup_network_server("):
                      player_ui.index("void player_ui_fast_setup_network_server(") + 1600]
    assert setup.index("ui_widgets_close_all();") < setup.index("pc_menus_screen(")
    assert setup.index("pc_menus_screen(") < setup.index("create_global_network_game_server()")
    assert "failed to initiate a multiplayer game server" in setup

    for name in assigned:
        assert name in ledger["symbols"], name
        row = batch[name]
        assert row["disposition"] in ALLOWED, name
        assert row["owner"], name
        assert row["reason"], name
        assert row["evidence"], name
        assert "hcu-ps2-batch-4-review.md" in row["evidence"], name
        assert row["test"] == TEST_ID, name
        assert name in review, name

        ce_path, ce_snippet = CE_SNIPPETS[name]
        ce_text = (ROOT / ce_path).read_text()
        assert ce_snippet in ce_text, name

        if name in skip:
            assert name in owner, name
            assert CONTRACT_SNIPPETS[name] in owner, name
            generated_zero = (
                f"{name}" in generated and
                "memset(&result, 0, sizeof(result));" in generated[
                    generated.find(name):generated.find(name) + 220]
            )
            if generated_zero:
                assert "memset(&result, 0, sizeof(result));" not in owner[
                    owner.find(CONTRACT_SNIPPETS[name]) - 80:
                    owner.find(CONTRACT_SNIPPETS[name]) + 80]
        elif name in ("qsort", "rand"):
            assert row["disposition"] == "implemented"
            assert "Newlib" in row["owner"]
