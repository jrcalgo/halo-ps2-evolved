import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HCU = ROOT / "submodules/halo-ce-universal"
BATCH = ROOT / "docs/hcu-source-backed-review/batches/batch-1.json"
REVIEW = ROOT / "docs/hcu-source-backed-review/hcu-ps2-batch-1-review.md"
SKIP = ROOT / "docs/hcu-source-backed-review/batches/batch-1-skip.txt"
class _PortC:
    def read_text(self):
        return "\n".join(path.read_text() for path in sorted((HCU / "port/ps2/src").glob("ps2_*.c")))

OWNER_C = _PortC()
CRT = HCU / "port/ps2/src/ps2_crt.c"
LEDGER = ROOT / "docs/hcu-source-backed-review/hcu-ps2-external-review.json"

ASSIGNED = [
    "XFindClose",
    "XFindFirstSaveGame",
    "XFindNextSaveGame",
    "__sync_val_compare_and_swap_4",
    "_control87",
    "_snprintf",
    "_sound_cache_sound_request",
    "_texture_cache_bitmap_get_hardware_format",
    "_vsnprintf",
    "_vsnwprintf",
    "attract_mode_start",
    "build_sprite",
    "build_sprites_begin",
    "build_sprites_end",
    "config_boolean",
    "config_changes",
    "config_real",
    "config_string",
    "connected_geometry_add_triangle",
    "connected_geometry_delete",
    "connected_geometry_group_coplanar",
    "connected_geometry_new",
    "create_global_network_game_client",
    "create_global_network_game_server",
    "custom_edition_cache_refuse",
    "custom_edition_cache_tags_load",
    "custom_edition_cache_tags_loaded",
    "custom_edition_cache_tags_unload",
    "custom_edition_level_name",
    "custom_edition_maps_description",
    "custom_edition_maps_name",
    "custom_edition_structure_bsp_load",
]

DISPOSITIONS = {"implemented", "state-adapter", "excluded-proven"}
TEST_NAME = (
    "tests/test_hcu_external_review_batch_1.py::"
    "test_batch_1_rooted_symbols_are_dispositioned"
)

CONTRACT_SNIPPETS = {
    "XFindClose": (OWNER_C, "int __stdcall XFindClose(void *find_handle)"),
    "XFindFirstSaveGame": (OWNER_C, "return INVALID_HANDLE_VALUE;"),
    "XFindNextSaveGame": (OWNER_C, "int __stdcall XFindNextSaveGame(void *find_handle,"),
    "__sync_val_compare_and_swap_4": (CRT, "if (current == old_value)"),
    "_control87": (OWNER_C, "ps2_control87_word = (previous & ~mask) | (new_value & mask);"),
    "_snprintf": (CRT, "result = vsnprintf(buffer, count, format, args);"),
    "_sound_cache_sound_request": (OWNER_C, "return sound != NULL;"),
    "_texture_cache_bitmap_get_hardware_format": (OWNER_C, "return bitmap;"),
    "_vsnprintf": (CRT, "return vsnprintf(buffer, count, format, args);"),
    "_vsnwprintf": (OWNER_C, "return truncated ? -1 : (int)used;"),
    "attract_mode_start": (OWNER_C, "ps2_attract_countdown_timer = system_milliseconds();"),
    "build_sprite": (OWNER_C, "data->sprite_count = (short)(data->sprite_count + 1);"),
    "build_sprites_begin": (OWNER_C, "SET_FLAG(data->flags, _build_sprites_valid_bit, TRUE);"),
    "build_sprites_end": (OWNER_C, "SET_FLAG(data->flags, _build_sprites_valid_bit, FALSE);"),
    "config_boolean": (OWNER_C, "game.enhanced_animations"),
    "config_changes": (OWNER_C, "return ps2_config_generation;"),
    "config_real": (OWNER_C, "audio.music_volume"),
    "config_string": (OWNER_C, 'return "important";'),
    "connected_geometry_add_triangle": (OWNER_C, "long connected_geometry_add_triangle("),
    "connected_geometry_delete": (OWNER_C, "void connected_geometry_delete("),
    "connected_geometry_group_coplanar": (OWNER_C, "long connected_geometry_group_coplanar("),
    "connected_geometry_new": (OWNER_C, "void connected_geometry_new("),
    "create_global_network_game_client": (OWNER_C, "boolean create_global_network_game_client(void)"),
    "create_global_network_game_server": (OWNER_C, "boolean create_global_network_game_server(void)"),
    "custom_edition_cache_refuse": (OWNER_C, "CACHE_FILE_VERSION_CUSTOM_EDITION"),
    "custom_edition_cache_tags_load": (OWNER_C, "struct cache_file_tag_header *custom_edition_cache_tags_load("),
    "custom_edition_cache_tags_loaded": (OWNER_C, "boolean custom_edition_cache_tags_loaded(void)"),
    "custom_edition_cache_tags_unload": (OWNER_C, "void custom_edition_cache_tags_unload(void)"),
    "custom_edition_level_name": (OWNER_C, "CUSTOM_EDITION_LEVEL_NAME_PREFIX"),
    "custom_edition_maps_description": (OWNER_C, "wchar_t *custom_edition_maps_description("),
    "custom_edition_maps_name": (OWNER_C, "wchar_t *custom_edition_maps_name("),
    "custom_edition_structure_bsp_load": (OWNER_C, "boolean custom_edition_structure_bsp_load("),
}


def test_batch_1_rooted_symbols_are_dispositioned():
    rows = json.loads(BATCH.read_text())
    review = REVIEW.read_text()
    owner_c = OWNER_C.read_text()
    skip = [line for line in SKIP.read_text().splitlines() if line.strip()]
    ledger = json.loads(LEDGER.read_text())
    assert set(rows) == set(ASSIGNED)
    for name in ASSIGNED:
        assert ledger["symbols"][name]["disposition"] == rows[name]["disposition"]
    assert len(ASSIGNED) == 32

    for name in ASSIGNED:
        row = rows[name]
        assert row["disposition"] in DISPOSITIONS, name
        assert row["owner"], name
        assert row["reason"], name
        assert row["evidence"], name
        assert "hcu-ps2-batch-1-review.md" in row["evidence"], name
        assert row["test"] == TEST_NAME, name
        assert f"`{name}`" in review, name

    for name, row in rows.items():
        if row["disposition"] in {"implemented", "state-adapter"}:
            path, snippet = CONTRACT_SNIPPETS[name]
            text = path.read_text()
            assert snippet in text, f"{name}: {snippet} not in {path}"

    for symbol in skip:
        assert symbol in owner_c, symbol
        assert symbol in ASSIGNED, symbol

    saved = (HCU / "source/saved games/saved_game_files.c").read_text()
    assert "if (find_handle != INVALID_HANDLE_VALUE)" in saved
    assert "if (!XFindClose(find_handle))" in saved

    errors = (HCU / "source/cseries/errors.c").read_text()
    assert "file = __sync_val_compare_and_swap(&debug_file, (FILE *)NULL, opened);" in errors

    real_math = (HCU / "source/math/real_math.c").read_text()
    assert "_control87(CW_DEFAULT, 0xFFFFF)" in real_math

    manager = (HCU / "source/sound/sound_manager.c").read_text()
    assert "if (!_sound_cache_sound_request(" in manager
    assert 'config_real("audio.music_volume")' in manager

    lights = (HCU / "source/objects/object_lights.c").read_text()
    assert "_texture_cache_bitmap_get_hardware_format(lightmap_bitmap, FALSE, FALSE)" in lights

    units = (HCU / "source/units/units.c").read_text()
    assert 'config_boolean("game.enhanced_animations") != 0' in units
    assert "static boolean enhanced = TRUE" in units

    cache = (HCU / "source/cache/cache_files.c").read_text()
    assert "custom_edition_cache_refuse(header, header->build, scenario_name)" in cache
    assert "if (custom_edition_level_name(scenario_name))" in cache

    main = (HCU / "source/main/main.c").read_text()
    assert "if (custom_edition_level_name(name))" in main

    unicode = (HCU / "source/text/unicode.c").read_text()
    assert "result = _vsnwprintf(string, size, format, arglist);" in unicode

    player_ui = (HCU / "source/interface/player_ui.c").read_text()
    assert "if (create_global_network_game_server() && create_global_network_game_client())" in player_ui

    assert "return INVALID_HANDLE_VALUE;" in owner_c
    assert "return sound != NULL;" in owner_c
    assert "return bitmap;" in owner_c
    assert 'game.enhanced_animations' in owner_c
    assert "CACHE_FILE_VERSION_CUSTOM_EDITION" in owner_c
    assert "CUSTOM_EDITION_LEVEL_NAME_PREFIX" in owner_c
    assert "memset(&result, 0, sizeof(result)); return result;" not in owner_c
