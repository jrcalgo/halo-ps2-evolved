import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BATCH = ROOT / "docs/hcu-source-backed-review/batches/batch-7.json"
REVIEW = ROOT / "docs/hcu-source-backed-review/hcu-ps2-batch-7-review.md"
SKIP = ROOT / "docs/hcu-source-backed-review/batches/batch-7-skip.txt"
class _PortC:
    def read_text(self):
        root = ROOT / "submodules/halo-ce-universal/port/ps2/src"
        return "\n".join(path.read_text() for path in sorted(root.glob("ps2_*.c")))

IMPL = _PortC()
ASSIGNED = [
    "sound_cache_close",
    "sound_cache_delete",
    "sound_cache_flush",
    "sound_cache_idle",
    "sound_cache_new",
    "sound_cache_open",
    "sound_cache_sound_finished",
    "strtok",
    "structure_bsp_header_deregister_vertex_buffers",
    "structure_bsp_header_register_vertex_buffers",
    "tags_header_deregister_vertex_and_index_buffers",
    "tags_header_register_vertex_and_index_buffers",
    "texture_cache_close",
    "texture_cache_debug_options",
    "texture_cache_flush",
    "texture_cache_open",
    "time",
    "towlower",
    "transport_dispose",
    "transport_initialize",
    "ui_set_next_level",
    "ui_widget_load_by_name_or_tag",
    "ui_widget_load_progress_widget",
    "ui_widgets_active_for_local_player",
    "ui_widgets_close_all",
    "ui_widgets_disable_pause_game",
    "ui_widgets_dispose",
    "ui_widgets_inhibit_processing",
    "ui_widgets_initialize",
    "ui_widgets_set_fade_value",
    "vswprintf",
    "xbox_set_machine_name",
]

ALLOWED = {"implemented", "state-adapter", "excluded-proven"}
TEST_NAME = (
    "tests/test_hcu_external_review_batch_7.py::"
    "test_batch_7_rooted_symbols_are_dispositioned"
)

# CE snippet that must exist in the named source and in the batch contract
# (implementation, review, or skip-owned C file).
APPROVED_SNIPPETS = {
    "sound_cache_close": (
        "submodules/halo-ce-universal/source/cache/xbox_sound_cache.c",
        "data_make_invalid(xbox_sound_cache_globals.cache_sounds);",
    ),
    "sound_cache_delete": (
        "submodules/halo-ce-universal/source/cache/xbox_sound_cache.c",
        "data_dispose(xbox_sound_cache_globals.cache_sounds);",
    ),
    "sound_cache_flush": (
        "submodules/halo-ce-universal/source/cache/xbox_sound_cache.c",
        "cache_sound->software_reference_count == 0 &&",
    ),
    "sound_cache_idle": (
        "submodules/halo-ce-universal/source/sound/sound_manager.c",
        "sound_cache_idle();",
    ),
    "sound_cache_new": (
        "submodules/halo-ce-universal/source/cache/xbox_sound_cache.c",
        "physical_memory_get_sound_cache_base_address();",
    ),
    "sound_cache_open": (
        "submodules/halo-ce-universal/source/cache/xbox_sound_cache.c",
        "data_make_valid(xbox_sound_cache_globals.cache_sounds);",
    ),
    "sound_cache_sound_finished": (
        "submodules/halo-ce-universal/source/cache/xbox_sound_cache.c",
        "cache_sound->software_reference_count--;",
    ),
    "strtok": (
        "submodules/halo-ce-universal/source/cseries/cseries.c",
        "return strtok(s1, s2);",
    ),
    "structure_bsp_header_deregister_vertex_buffers": (
        "submodules/halo-ce-universal/source/cache/cache_files_windows.c",
        "IDirect3DVertexBuffer8_BlockUntilNotBusy(vertex_buffer);",
    ),
    "structure_bsp_header_register_vertex_buffers": (
        "submodules/halo-ce-universal/source/cache/cache_files_windows.c",
        "IDirect3DVertexBuffer8_Register(vertex_buffer, NULL);",
    ),
    "tags_header_deregister_vertex_and_index_buffers": (
        "submodules/halo-ce-universal/source/cache/cache_files.c",
        "tags_header_deregister_vertex_and_index_buffers(cache_file_globals.tag_header);",
    ),
    "tags_header_register_vertex_and_index_buffers": (
        "submodules/halo-ce-universal/source/cache/cache_files.c",
        "tags_header_register_vertex_and_index_buffers(cache_file_globals.tag_header);",
    ),
    "texture_cache_close": (
        "submodules/halo-ce-universal/source/cache/xbox_texture_cache.c",
        "data_make_invalid(xbox_texture_cache_globals.textures);",
    ),
    "texture_cache_debug_options": (
        "submodules/halo-ce-universal/source/hs/hs_globals_external.c",
        "texture_cache_debug_options + 0x1",
    ),
    "texture_cache_flush": (
        "submodules/halo-ce-universal/source/cache/xbox_texture_cache.c",
        "lruv_flush(xbox_texture_cache_globals.cache);",
    ),
    "texture_cache_open": (
        "submodules/halo-ce-universal/source/cache/xbox_texture_cache.c",
        "data_make_valid(xbox_texture_cache_globals.textures);",
    ),
    "time": (
        "submodules/halo-ce-universal/source/cseries/cseries_windows.c",
        "return time(NULL);",
    ),
    "towlower": (
        "submodules/halo-ce-universal/source/cseries/cseries.c",
        "c1 = towlower(*s1);",
    ),
    "transport_dispose": (
        "submodules/halo-ce-universal/source/bungie_net/network/transport_endpoint_set_winsock.c",
        "result = _transport_error_not_initialized;",
    ),
    "transport_initialize": (
        "submodules/halo-ce-universal/source/bungie_net/network/transport_endpoint_set_winsock.c",
        "return _transport_error_not_initialized;",
    ),
    "ui_set_next_level": (
        "submodules/halo-ce-universal/source/interface/ui_widget.c",
        "main_set_map_name(main_get_solo_level_name(level));",
    ),
    "ui_widget_load_by_name_or_tag": (
        "submodules/halo-ce-universal/source/interface/player_ui.c",
        "if (ui_widget_load_by_name_or_tag(",
    ),
    "ui_widget_load_progress_widget": (
        "submodules/halo-ce-universal/source/interface/ui_widget.c",
        "the old loading progress screen has been replaced with glowy halo gravy",
    ),
    "ui_widgets_active_for_local_player": (
        "submodules/halo-ce-universal/source/game/player_control.c",
        "ui_widgets_active_for_local_player(gamepad_index);",
    ),
    "ui_widgets_close_all": (
        "submodules/halo-ce-universal/source/interface/ui_widget.c",
        "if (virtual_keyboard_active())",
    ),
    "ui_widgets_disable_pause_game": (
        "submodules/halo-ce-universal/source/interface/ui_widget.c",
        "widget_globals.pause_disabled_ticks = duration_ticks;",
    ),
    "ui_widgets_dispose": (
        "submodules/halo-ce-universal/source/interface/ui_widget.c",
        "ui_widgets_close_all();",
    ),
    "ui_widgets_inhibit_processing": (
        "submodules/halo-ce-universal/source/interface/ui_widget.c",
        "widget_globals.processing_inhibited = inhibit;",
    ),
    "ui_widgets_initialize": (
        "submodules/halo-ce-universal/source/interface/ui_widget.c",
        "widget_globals.fade_to_black = -1.0f;",
    ),
    "ui_widgets_set_fade_value": (
        "submodules/halo-ce-universal/source/interface/ui_widget.c",
        "widget_globals.fade_to_black = value;",
    ),
    "vswprintf": (
        "submodules/halo-ce-universal/source/text/unicode.c",
        "result = vswprintf(string, format, arglist);",
    ),
    "xbox_set_machine_name": (
        "submodules/halo-ce-universal/source/networking/network_game_manager.c",
        "if (!XSetNicknameW(wide_machine_name, TRUE))",
    ),
}


def test_batch_7_rooted_symbols_are_dispositioned():
    batch = json.loads(BATCH.read_text())
    review = REVIEW.read_text()
    impl = IMPL.read_text()
    skip = [line for line in SKIP.read_text().splitlines() if line.strip()]
    assert set(batch) == set(ASSIGNED)
    assert set(skip) == set(ASSIGNED) - {"strtok", "time"}
    contract = review + "\n" + impl

    for name in ASSIGNED:
        row = batch[name]
        assert row["disposition"] in ALLOWED, name
        assert row["owner"].strip(), name
        assert row["reason"].strip(), name
        assert row["evidence"].strip(), name
        assert "hcu-ps2-batch-7-review.md" in row["evidence"], name
        assert row["test"] == TEST_NAME, name
        assert name in review, name
        if name in skip:
            assert name in impl, name

        source_rel, snippet = APPROVED_SNIPPETS[name]
        source = (ROOT / source_rel).read_text()
        assert snippet in source, (name, source_rel, snippet)
        assert snippet in contract, (name, snippet)
