import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HCU = ROOT / "submodules/halo-ce-universal"
BATCH_JSON = ROOT / "docs/hcu-source-backed-review/batches/batch-5.json"
SKIP = ROOT / "docs/hcu-source-backed-review/batches/batch-5-skip.txt"
REVIEW = ROOT / "docs/hcu-source-backed-review/hcu-ps2-batch-5-review.md"
LEDGER = ROOT / "docs/hcu-source-backed-review/hcu-ps2-external-review.json"
class _PortC:
    def read_text(self):
        return "\n".join(path.read_text() for path in sorted((HCU / "port/ps2/src").glob("ps2_*.c")))

BATCH_C = _PortC()
EDGE = HCU / "port/ps2/src/ps2_edge.c"
GENERATED = ROOT / "build/hcu-ps2-closure/all/ps2_platform.c"
TEST_ID = (
    "tests/test_hcu_external_review_batch_5.py::"
    "test_batch_5_rooted_symbols_are_dispositioned"
)
DISPOSITIONS = {"implemented", "state-adapter", "excluded-proven"}

# One CE or port snippet that proves the reviewed contract for each symbol.
CONTRACT_SNIPPETS = {
    "rasterizer_dynamic_vertices_new": [
        (HCU / "source/objects/widgets/flags.c",
         "if (triangle_buffer_index != NONE && vertex_buffer_index != NONE)"),
        (HCU / "source/rasterizer/xbox/rasterizer_xbox_draw_primitives.c",
         "long dynamic_vertex_buffer_index = NONE;"),
        (BATCH_C, "return NONE;"),
    ],
    "rasterizer_dynamic_vertices_unlock": [
        (HCU / "source/objects/widgets/lightning.c",
         "rasterizer_dynamic_vertices_unlock(vertex_buffer_index);"),
        (BATCH_C, "void rasterizer_dynamic_vertices_unlock("),
    ],
    "rasterizer_fps_accumulate": [
        (HCU / "source/hs/hs.c",
         "FALSE, /* rasterizer_fps_accumulate: the frame rate display */"),
        (HCU / "source/rasterizer/rasterizer_frame_statistics.c",
         "rasterizer_debug_options.fps_accumulation = TRUE;"),
    ],
    "rasterizer_frame_begin": [
        (HCU / "source/rasterizer/rasterizer.c",
         "if (rasterizer_globals.near_clip_distance == 0.f)"),
        (HCU / "source/main/main.c",
         "window_parameters.camera.z_near = rasterizer_globals.near_clip_distance;"),
        (BATCH_C, "ps2_rasterizer_restore_clip_defaults();"),
    ],
    "rasterizer_frame_end": [
        (HCU / "source/main/main.c", "rasterizer_frame_end();"),
        (HCU / "source/rasterizer/rasterizer.c", "_rasterizer_frame_end();"),
    ],
    "rasterizer_frame_update": [
        (HCU / "source/game/game.c", "rasterizer_frame_update(frame_dt);"),
        (HCU / "source/rasterizer/common/rasterizer_common.c",
         "global_frame_parameters.dt = dt;"),
    ],
    "rasterizer_globals": [
        (HCU / "source/hs/hs_globals_external.c",
         "&rasterizer_globals.near_clip_distance"),
        (HCU / "source/rasterizer/rasterizer.c", "0.0625f,"),
        (BATCH_C, "PS2_NEAR_CLIP_DISTANCE,"),
    ],
    "rasterizer_initialize": [
        (HCU / "source/shell/shell.c",
         "rasterizer_initialized = rasterizer_initialize();"),
        (EDGE, "rasterizer_globals.near_clip_distance = 0.0625f;"),
        (HCU / "source/rasterizer/rasterizer.c",
         "global_rasterizer_model_ambient_reflection_tint = game_state_malloc("),
    ],
    "rasterizer_initialize_for_new_map": [
        (HCU / "source/game/game.c", "rasterizer_initialize_for_new_map();"),
        (HCU / "source/rasterizer/common/rasterizer_common.c",
         "rasterizer_set_near_clip_distance(0.f);"),
        (BATCH_C, "rasterizer_screen_effects_initialize_for_new_map();"),
    ],
    "rasterizer_lights_reset_for_new_map": [
        (HCU / "source/rasterizer/rasterizer_lights.c",
         "memset(local_lens_flare_occlusion_test_results2"),
        (BATCH_C, "void rasterizer_lights_reset_for_new_map("),
    ],
    "rasterizer_model_ambient_reflection_tint": [
        (HCU / "source/rasterizer/xbox/rasterizer_xbox_models.c",
         "if (global_rasterizer_model_ambient_reflection_tint)"),
        (HCU / "source/hs/hs.c",
         "rasterizer_model_ambient_reflection_tint(arguments->value0, value1, value2, value3);"),
    ],
    "rasterizer_model_begin": [
        (HCU / "source/objects/widgets/flags.c",
         "rasterizer_model_begin(&parameters, FALSE);"),
        (HCU / "source/rasterizer/rasterizer.c", "_rasterizer_model_begin(parameters, is_dynamic);"),
    ],
    "rasterizer_model_draw": [
        (HCU / "source/objects/widgets/flags.c", "rasterizer_model_draw("),
        (HCU / "source/rasterizer/rasterizer.c", "_rasterizer_model_draw("),
    ],
    "rasterizer_model_end": [
        (HCU / "source/objects/widgets/flags.c", "rasterizer_model_end();"),
        (HCU / "source/rasterizer/rasterizer.c", "_rasterizer_model_end();"),
    ],
    "rasterizer_model_transparent_geometry_submit": [
        (HCU / "source/objects/widgets/flags.c",
         "rasterizer_model_transparent_geometry_submit("),
        (HCU / "source/rasterizer/rasterizer.c",
         "_rasterizer_model_transparent_geometry_submit("),
    ],
    "rasterizer_models_begin": [
        (HCU / "source/objects/widgets/flags.c", "rasterizer_models_begin(FALSE);"),
        (HCU / "source/rasterizer/rasterizer.c",
         "if (collision_test_vector("),
    ],
    "rasterizer_models_end": [
        (HCU / "source/objects/widgets/flags.c", "rasterizer_models_end();"),
        (HCU / "source/rasterizer/rasterizer.c", "_rasterizer_models_end();"),
    ],
    "rasterizer_preinitialize__fill_you_up_with_the_devils_cock": [
        (HCU / "source/shell/shell_xbox.c",
         "rasterizer_preinitialize__fill_you_up_with_the_devils_cock();"),
        (HCU / "source/rasterizer/xbox/rasterizer_xbox.c",
         "d3d = Direct3DCreate8(D3D_SDK_VERSION);"),
        (GENERATED,
         "boolean rasterizer_preinitialize__fill_you_up_with_the_devils_cock(void) { boolean result; memset(&result, 0, sizeof(result)); return result; }"),
    ],
    "rasterizer_present": [
        (HCU / "source/main/main.c", "rasterizer_present(NULL, NULL);"),
        (HCU / "source/rasterizer/rasterizer.c",
         "_rasterizer_present(screenshot_bitmap, screenshot_index);"),
    ],
    "rasterizer_profile_enable": [
        (HCU / "source/objects/widgets/flags.c", "rasterizer_profile_enable(FALSE);"),
        (HCU / "source/rasterizer/rasterizer.c", "_rasterizer_profile_enable(enable);"),
    ],
    "rasterizer_screen_effect_set_convolution": [
        (HCU / "source/rasterizer/rasterizer_cinematics.c",
         "if (cinematic_screen_effect_globals)"),
        (HCU / "source/hs/hs.c",
         "rasterizer_screen_effect_set_convolution(arguments->value0, arguments->value1, value2, value3, value4);"),
    ],
    "rasterizer_screen_effect_set_filter": [
        (HCU / "source/rasterizer/rasterizer_cinematics.c",
         "cinematic_screen_effect_globals->filter_light_enhancement_intensity[0] ="),
        (HCU / "source/hs/hs.c",
         "rasterizer_screen_effect_set_filter(arguments->value0, value1, value2, value3, arguments->value4, value5);"),
    ],
    "rasterizer_screen_effect_set_filter_desaturation_tint": [
        (HCU / "source/rasterizer/rasterizer_cinematics.c",
         "globals->parameters.filter_desaturation_tint.red = red;"),
        (HCU / "source/hs/hs.c",
         "rasterizer_screen_effect_set_filter_desaturation_tint(arguments->value0, value1, value2);"),
    ],
    "rasterizer_screen_effect_set_video": [
        (HCU / "source/rasterizer/rasterizer_cinematics.c",
         "cinematic_screen_effect_globals->parameters.video_on = TRUE;"),
        (HCU / "source/hs/hs.c",
         "rasterizer_screen_effect_set_video(arguments[0].unsigned_short_value, real_argument)"),
    ],
    "rasterizer_screen_effect_start": [
        (HCU / "source/rasterizer/rasterizer_cinematics.c",
         "globals->has_control = TRUE;"),
        (HCU / "source/hs/hs.c",
         "HS_EVALUATE_VOID_FROM_ARGUMENTS(rasterizer_screen_effect_start_evaluate, struct hs_arguments_boolean, (rasterizer_screen_effect_start(arguments->value)))"),
    ],
    "rasterizer_screen_effect_stop": [
        (HCU / "source/rasterizer/rasterizer_cinematics.c",
         "cinematic_screen_effect_globals->has_control = FALSE;"),
        (HCU / "source/hs/hs.c",
         "HS_EVALUATE_NO_ARGUMENTS(rasterizer_screen_effect_stop_evaluate, rasterizer_screen_effect_stop)"),
    ],
    "rasterizer_screen_effects_initialize_for_new_map": [
        (HCU / "source/cutscene/cinematics.c",
         "rasterizer_screen_effects_initialize_for_new_map();"),
        (BATCH_C, "rasterizer_set_near_clip_distance(0.f);"),
    ],
    "rasterizer_script_screen_effect_set_value": [
        (HCU / "source/rasterizer/rasterizer_cinematics.c",
         "cinematic_screen_effect_globals->script_values[signed_effect_index] = value;"),
        (HCU / "source/hs/hs.c",
         "rasterizer_script_screen_effect_set_value(arguments[0].unsigned_short_value, real_argument)"),
    ],
    "rasterizer_set_near_clip_distance": [
        (HCU / "source/cutscene/cinematics.c",
         "rasterizer_set_near_clip_distance(0.0f);"),
        (HCU / "source/rasterizer/rasterizer_cinematics.c",
         "cinematic_screen_effect_globals->near_clip_distance = near_clip_distance;"),
        (BATCH_C, "if (near_clip_distance > 0.f)"),
    ],
    "rasterizer_set_vblank_callback": [
        (HCU / "source/main/main.c",
         "rasterizer_set_vblank_callback(main_vertical_blank_interrupt_handler);"),
        (HCU / "source/input/input_xbox.c", "#ifndef HALO_PS2"),
        (HCU / "source/main/main.c",
         "if (rasterizer_globals.framerate_throttle && !halo_interpolation_enabled())"),
    ],
    "rasterizer_widget_batch_sprites": [
        (HCU / "source/objects/widgets/light_volumes.c",
         "rasterizer_widget_batch_sprites(TRUE); /* port: one draw */"),
        (HCU / "source/rasterizer/rasterizer_widgets.h",
         "void rasterizer_widget_batch_sprites("),
    ],
    "rasterizer_widget_begin": [
        (HCU / "source/objects/widgets/light_volumes.c",
         "rasterizer_widget_begin("),
        (HCU / "source/rasterizer/rasterizer.c", "_rasterizer_widget_begin("),
    ],
}


def pending_slice():
    return sorted(json.loads(BATCH_JSON.read_text()))


def defined_symbols(text):
    names = set()
    names.update(re.findall(
        r"^(?:long|void|boolean|real|short|int)\s+\**([A-Za-z_][A-Za-z0-9_]*)\s*\(",
        text, re.M))
    names.update(re.findall(
        r"^struct\s+\w+\s+([A-Za-z_][A-Za-z0-9_]*)\s*=",
        text, re.M))
    return names


def test_batch_5_rooted_symbols_are_dispositioned():
    assigned = json.loads(BATCH_JSON.read_text())
    slice_names = pending_slice()
    assert slice_names, "pending slice [160:192] must not be empty"
    assert list(assigned) == slice_names or set(assigned) == set(slice_names)
    assert set(assigned) == set(slice_names)
    assert set(CONTRACT_SNIPPETS) == set(slice_names)

    review = REVIEW.read_text()
    batch_c = BATCH_C.read_text()
    skip = [line for line in SKIP.read_text().splitlines() if line.strip()]
    assert set(skip) <= defined_symbols(batch_c)
    assert "return NONE;" in batch_c
    assert "framerate_throttle" not in batch_c or "FALSE" in batch_c
    assert "PS2_NEAR_CLIP_DISTANCE" in batch_c
    generated = GENERATED.read_text()
    generated_new = generated[generated.index(
        "long rasterizer_dynamic_vertices_new("):]
    assert "memset(&result, 0, sizeof(result)); return result;" in generated_new[:220]

    for name, row in assigned.items():
        assert row["disposition"] in DISPOSITIONS, name
        assert row["owner"], name
        assert row["reason"], name
        assert row["evidence"], name
        assert row["test"] == TEST_ID, name
        assert "hcu-ps2-batch-5-review.md" in row["evidence"], name
        assert name in review, name
        snippets = CONTRACT_SNIPPETS[name]
        assert snippets, name
        found = 0
        for path, snippet in snippets:
            text = path.read_text(encoding="latin-1", errors="replace")
            assert snippet in text, f"{name}: missing {snippet!r} in {path}"
            found += 1
        assert found >= 1, name

    assert assigned["rasterizer_dynamic_vertices_new"]["disposition"] == "implemented"
    assert assigned["rasterizer_globals"]["disposition"] == "implemented"
    assert assigned["rasterizer_initialize"]["disposition"] == "implemented"
    assert assigned["rasterizer_preinitialize__fill_you_up_with_the_devils_cock"][
        "disposition"] == "state-adapter"
    assert "cinematic_stop" in review
    assert "NONE" in review
