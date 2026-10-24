import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LEDGER = ROOT / "docs/hcu-source-backed-review/hcu-ps2-external-review.json"
BATCH = ROOT / "docs/hcu-source-backed-review/batches/batch-2.json"
REVIEW = ROOT / "docs/hcu-source-backed-review/hcu-ps2-batch-2-review.md"
SKIP = ROOT / "docs/hcu-source-backed-review/batches/batch-2-skip.txt"
class _PortC:
    def read_text(self):
        root = ROOT / "submodules/halo-ce-universal/port/ps2/src"
        return "\n".join(path.read_text() for path in sorted(root.glob("ps2_*.c")))

OWNER_C = _PortC()
TEST_ID = (
    "tests/test_hcu_external_review_batch_2.py::"
    "test_batch_2_rooted_symbols_are_dispositioned"
)
ALLOWED = {"implemented", "state-adapter", "excluded-proven"}
HCU = ROOT / "submodules/halo-ce-universal"

SNIPPETS = {
    "custom_edition_structure_bsp_reference_valid": [
        (HCU / "source/cache/cache_files.c",
         "if (!custom_edition_structure_bsp_reference_valid(reference))"),
        (ROOT / "build/hcu-ps2-closure/all/ps2_platform.c",
         "boolean custom_edition_cache_tags_loaded(void)"),
    ],
    "custom_edition_structure_bsp_unload": [
        (HCU / "source/cache/cache_files.c",
         "custom_edition_structure_bsp_unload();"),
    ],
    "custom_edition_vehicle_placement_allowed": [
        (HCU / "source/objects/object_types.c",
         "(!custom_edition_vehicle_placement_allowed(scenario_object) ||"),
        (HCU / "port/linux/game/custom_edition_objects.c",
         "return !custom_edition_vehicles_by_placement() ||"),
        (OWNER_C, "if (!custom_edition_vehicles_by_placement())"),
    ],
    "custom_edition_vehicles_by_placement": [
        (HCU / "source/game/game_engine.c",
         "if (custom_edition_vehicles_by_placement())"),
        (HCU / "port/linux/game/custom_edition_objects.c",
         "return custom_edition_cache_tags_loaded() &&"),
        (OWNER_C, "boolean custom_edition_vehicles_by_placement("),
    ],
    "display_error_damaged_media": [
        (HCU / "source/cache/cache_files.c",
         "display_error_damaged_media();"),
        (HCU / "source/interface/ui_widget.c", "main_loop_of_death();"),
        (OWNER_C, "main_loop_of_death();"),
    ],
    "display_error_deferred": [
        (HCU / "source/input/input_abstraction.c",
         "display_error_deferred(error_code, error_controller, pause_game, pause_game);"),
        (HCU / "source/interface/ui_widget.c",
         "widget_globals.deferred_errors[index].pause_game_time = pause_game_time;"),
        (OWNER_C, "game_time_set_paused(TRUE);"),
    ],
    "display_error_when_main_menu_loaded": [
        (HCU / "source/main/main.c",
         "if (connection==_game_connection_network_client)"),
        (HCU / "source/main/main.c",
         "main_globals.connection = _game_connection_local;"),
        (ROOT / "build/hcu-ps2-closure/all/ps2_platform.c",
         "boolean create_global_network_game_server(void)"),
    ],
    "display_errors_deferred_until_cinematic_stop": [
        (HCU / "source/cutscene/cinematics.c",
         "display_errors_deferred_until_cinematic_stop();"),
        (HCU / "source/interface/ui_widget.c",
         "widget_globals.deferred_cinematic_errors[local_player_index].error_code = error_code;"),
        (HCU / "port/ps2/port.json", "source/interface/ui_widget.c"),
    ],
    "display_scenario_help": [
        (HCU / "source/hs/hs.c",
         "HS_EVALUATE_VOID_UNSIGNED_SHORT(display_scenario_help_evaluate, display_scenario_help)"),
        (HCU / "source/interface/ui_widget.c",
         'widget_name = "ui\\\\shell\\\\solo_game\\\\player_help\\\\player_help_screen_a10";'),
        (OWNER_C,
         'widget_name = "ui\\\\shell\\\\solo_game\\\\player_help\\\\player_help_screen_a10";'),
    ],
    "dispose_global_network_game_client": [
        (HCU / "source/networking/network_game_globals.c",
         "if (bss_004566dc.client)"),
        (HCU / "port/ps2/game/ps2_local.c",
         "struct network_game_client *global_network_game_client_get(void)"),
        (HCU / "source/interface/player_ui.c",
         "dispose_global_network_game_client();"),
    ],
    "dispose_global_network_game_server": [
        (HCU / "source/networking/network_game_globals.c",
         "if (bss_004566dc.server)"),
        (HCU / "port/ps2/game/ps2_local.c",
         "struct network_game_server *global_network_game_server_get(void)"),
        (HCU / "source/interface/player_ui.c",
         "dispose_global_network_game_server();"),
    ],
    "distributed_player_to_byte": [
        (HCU / "source/game/game_engine_ctf.c",
         "ctf_events.capturers[team_index] = distributed_player_to_byte(player_index);"),
        (HCU / "port/linux/game/network_distributed.c",
         "return player_index != NONE ? (byte)DATUM_INDEX_TO_ABSOLUTE_INDEX(player_index) : NO_PLAYER;"),
        (OWNER_C, "DATUM_INDEX_TO_ABSOLUTE_INDEX(player_index)"),
    ],
    "dsound_globals": [
        (HCU / "source/sound/sound_preferences.c", "#ifdef HALO_PS2"),
        (HCU / "source/sound/sound_manager.c",
         "if (platform_code < 0 || platform_code >= 2)"),
        (ROOT / "build/hcu-ps2-closure/all/ps2_platform.c",
         "unsigned char dsound_globals[30924];"),
    ],
    "fclose": [
        (HCU / "source/game/cheats.c", "fclose(file);"),
        (ROOT / "build/hcu-ps2-closure/all/halo-local.map", "libc_a-fclose.o"),
    ],
    "fflush": [
        (HCU / "source/cseries/errors.c", "fflush(file);"),
        (ROOT / "build/hcu-ps2-closure/all/halo-local.map", "libc_a-fflush.o"),
    ],
    "fgets": [
        (HCU / "source/game/cheats.c",
         "if (!fgets(cheat_strings[cheat_index], MAXIMUM_CHEAT_LENGTH-1, file))"),
        (ROOT / "build/hcu-ps2-closure/all/halo-local.map", "libc_a-fgets.o"),
    ],
    "first_person_legs_reset": [
        (HCU / "source/objects/objects.c", "first_person_legs_reset();"),
        (HCU / "port/linux/game/first_person_legs.c",
         "first_person_legs_waist_key = NONE;"),
        (HCU / "port/ps2/port.json", '"source/render/"'),
    ],
    "fopen": [
        (HCU / "source/main/main.c", 'file = fopen("z:\\\\last_solo.txt", "r");'),
        (HCU / "source/game/cheats.c", 'FILE *file = fopen(CHEATS_FILENAME, "r");'),
        (ROOT / "build/hcu-ps2-closure/all/halo-local.map", "libc_a-fopen.o"),
    ],
    "fprintf": [
        (HCU / "source/objects/objects.c", 'fprintf(file, "OBJECTS BY TYPE\\n");'),
        (ROOT / "build/hcu-ps2-closure/all/halo-local.map", "libc_a-fprintf.o"),
    ],
    "fputc": [
        (HCU / "source/objects/objects.c",
         'file = fopen("d:\\\\object_memory.txt", "a+b");'),
        (ROOT / "build/hcu-ps2-closure/all/halo-local.map", "libc_a-fputc.o"),
    ],
    "fputs": [
        (HCU / "source/structures/structure_lens_flares.c",
         'fprintf(stdout, "building structure lens flares...");'),
        (ROOT / "build/hcu-ps2-closure/all/halo-local.map", "libc_a-fputs.o"),
    ],
    "fread": [
        (HCU / "source/main/main.c",
         "character_count = fread(map_name, 1, 255, file);"),
        (ROOT / "build/hcu-ps2-closure/all/halo-local.map", "libc_a-fread.o"),
    ],
    "fscanf": [
        (HCU / "source/camera/director.c",
         'fscanf(file, "%f %f %f\\n", &position.x, &position.y, &position.z);'),
        (ROOT / "build/hcu-ps2-closure/all/halo-local.map", "libc_a-fscanf.o"),
    ],
    "game_in_editor": [
        (HCU / "source/editor/editor_stubs.c", "return FALSE;"),
        (HCU / "source/game/game.c", "if (!game_in_editor())"),
        (HCU / "source/objects/object_types.c",
         "if (!game_in_editor() && global_structure_bsp_index!=NONE)"),
    ],
    "global_rasterizer_model_ambient_reflection_tint": [
        (HCU / "source/cutscene/cinematics.c",
         "if (global_rasterizer_model_ambient_reflection_tint)"),
        (ROOT / "build/hcu-ps2-closure/all/ps2_platform.c",
         "real_argb_color * global_rasterizer_model_ambient_reflection_tint;"),
    ],
    "gmtime_r": [
        (HCU / "port/ps2/src/ps2_time.c", "if (!gmtime_r(&now, &utc))"),
        (ROOT / "build/hcu-ps2-closure/all/halo-local.map", "libc_a-gmtime_r.o"),
    ],
    "halo_custom_edition_tag_cache": [
        (HCU / "source/cache/cache_files.c",
         "tag_cache = halo_custom_edition_tag_cache();"),
        (HCU / "source/cache/cache_files.c",
         "if (custom_edition_cache_tags_loaded())"),
    ],
    "halo_interpolation_enabled": [
        (HCU / "source/main/main.c", "if (halo_interpolation_enabled())"),
        (ROOT / "build/hcu-ps2-closure/all/ps2_platform.c",
         "int halo_interpolation_enabled(void)"),
    ],
    "halo_screen_width": [
        (HCU / "source/main/main.c",
         "window_parameters.camera.viewport_bounds.x1 = (short)halo_screen_width();"),
        (HCU / "port/ps2/src/ps2_edge.c", "return 512;"),
    ],
    "hud_hires_tags_loaded": [
        (HCU / "source/cache/cache_files.c", "hud_hires_tags_loaded();"),
        (HCU / "source/interface/hud_messaging.c",
         "if (hud_hires_button_draw(icon, cursor_bounds, color))"),
    ],
    "hud_hires_tags_unloaded": [
        (HCU / "source/cache/cache_files.c", "hud_hires_tags_unloaded();"),
        (HCU / "port/linux/game/hud_hires_tags.c",
         "void hud_hires_tags_unloaded("),
    ],
    "initialize_network_game_packets": [
        (HCU / "source/game/game.c", "initialize_network_game_packets();"),
        (HCU / "source/networking/network_messages.c",
         "data_packet_group_initialize(&data_0030aa68.group);"),
        (HCU / "port/ps2/port.json", '"source/networking/"'),
    ],
}


def pending_slice():
    return list(json.loads(BATCH.read_text()))


def test_batch_2_rooted_symbols_are_dispositioned():
    assigned = pending_slice()
    assert assigned, "pending slice [64:96] must not be empty"
    batch = json.loads(BATCH.read_text())
    assert set(batch) == set(assigned)
    review = REVIEW.read_text()
    skip = [line for line in SKIP.read_text().splitlines() if line.strip()]
    owner_c = OWNER_C.read_text()
    assert skip
    for name in skip:
        assert name in owner_c
        assert batch[name]["disposition"] == "implemented"

    for name in assigned:
        row = batch[name]
        assert row["disposition"] in ALLOWED, name
        assert row["owner"].strip(), name
        assert row["reason"].strip(), name
        assert row["evidence"].strip(), name
        assert "hcu-ps2-batch-2-review.md" in row["evidence"], name
        assert row["test"] == TEST_ID, name
        assert name in review, name
        snippets = SNIPPETS[name]
        assert snippets, name
        found = False
        for path, snippet in snippets:
            text = path.read_text()
            assert snippet in text, f"{name}: missing {snippet!r} in {path}"
            found = True
        assert found, name

    assert "if (!custom_edition_vehicles_by_placement())" in owner_c
    assert "return TRUE;" in owner_c
    assert "main_loop_of_death();" in owner_c
    assert "game_time_set_paused(TRUE);" in owner_c
    assert "PS2_M0_NO_PLAYER" in owner_c
    assert "__attribute__((weak)) long halo_screen_width(" in (ROOT / "submodules/halo-ce-universal/port/ps2/src/ps2_edge.c").read_text()
