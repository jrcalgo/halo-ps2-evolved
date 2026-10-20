# CE roots under the PS2 M0 batch-7 slice

Status: the pending-ledger slice `[224:256]` is closed. Campaign next-level, the sound-cache datum, widget lifetime state, CE-shaped `vswprintf`, and the ASCII `towlower` fold are implemented. Texture-cache open/close/flush, D3D vertex-buffer register pairs, transport startup, widget load, and the Xbox nickname setter are explicit state adapters. `strtok` and `time` keep their pinned Newlib/PS2SDK owners. Generated typed zero-return bodies are not approved on this slice.

## Evidence and boundary

The live caller sections and `caller_sources` on each ledger row were traced to the CE call site, the declaration, and the generated or real body in `build/hcu-ps2-closure/all/ps2_platform.c` and `submodules/halo-ce-universal/port/ps2/src/ps2_edge.c`. Data-section callers were traced to their defining objects. `port/ps2/src/ps2_edge.c` does not own any symbol in this slice. The generated file supplies empty or `memset`-zero bodies for the game services; Newlib already supplies `strtok`, `time`, `towlower`, and a four-argument `vswprintf`.

The PS2 manifest excludes `source/interface/ui_widget.c`, `source/cache/xbox_sound_cache.c`, `source/cache/xbox_texture_cache.c`, `source/cache/cache_files_windows.c`, `source/bungie_net/` (except the extra thread unit), and `source/networking/` (`port/ps2/port.json:35-66`). Those CE files remain the comparison source for the contracts implemented in `port/ps2/src/ps2_m0_batch_7.c`.

| Root | Caller file:line | Effect |
|---|---|---|
| `sound_cache_new` | `source/sound/sound_manager.c:920` (`sound_initialize`) | Creates the 512-entry `"xbox sound"` datum and binds `physical_memory_get_sound_cache_base_address()` before the HALO_PS2 platform `-1` return. |
| `sound_cache_delete` | `source/sound/sound_manager.c:811` (`sound_dispose`) | Disposes that datum and clears the base after the uninitialized manager path. |
| `sound_cache_open` | `source/cache/cache_files.c:1225` (`scenario_tags_load`) | `data_make_valid` on the sound datum before tags are installed. |
| `sound_cache_close` | `source/cache/cache_files.c:626` (`scenario_tags_unload`) | Drains remaining entries, zeros leftover software/hardware counts, then `data_make_invalid` before tag teardown. |
| `sound_cache_idle` | `source/sound/sound_manager.c:3812,4002` (`sound_idle`, `sound_render`) | Advances LRU work. An empty datum has no pending pages. |
| `sound_cache_flush` | `source/hs/hs.c:14196` (`sound_cache_flush_evaluate`) | Deletes only entries whose software and hardware counts are both zero. |
| `sound_cache_sound_finished` | `source/sound/sound_manager.c:1287,1945,1966,1983,1989,2018` | `if (!cache_sound) return;` then `software_reference_count--`. |
| `strtok` | `source/cseries/cseries.c:560` (`csstrtok`) | `return strtok(s1, s2);`. `cseries.h:279` remaps the `strtok` name onto `csstrtok`. Linked member: `libc_a-strtok.o`. |
| `structure_bsp_header_register_vertex_buffers` | `source/cache/cache_files.c:1497` | CE writes `D3DCOMMON_TYPE_VERTEXBUFFER` and calls `IDirect3DVertexBuffer8_Register`. |
| `structure_bsp_header_deregister_vertex_buffers` | `source/cache/cache_files.c:1517` | CE waits on `IDirect3DVertexBuffer8_BlockUntilNotBusy`. |
| `tags_header_register_vertex_and_index_buffers` | `source/cache/cache_files.c:1328` | CE registers tag-header vertex buffers and marks index buffers. |
| `tags_header_deregister_vertex_and_index_buffers` | `source/cache/cache_files.c:649` | CE waits for those buffers to go idle on unload. |
| `texture_cache_open` | `source/cache/cache_files.c:1224` | CE `data_make_valid(xbox_texture_cache_globals.textures)`. `texture_cache_new` is not a live external in this closure. |
| `texture_cache_close` | `source/cache/cache_files.c:627` | CE `texture_cache_flush(); data_make_invalid(...)`. |
| `texture_cache_flush` | `source/hs/hs.c:14195` | CE kicks the D3D push buffer and `lruv_flush`. |
| `texture_cache_debug_options` | `.data.texture_cache_graph_definition`, `.data.texture_cache_list_definition` in `source/hs/hs_globals_external.c:1926-1928` | Defining objects alias `texture_cache_debug_options` and `texture_cache_debug_options + 0x1`. CE storage is `{0}`. The Xbox debug renderer that reads `.graph`/`.list` is excluded. |
| `time` | `port/ps2/src/ps2_time.c:49`, `source/cseries/cseries_windows.c:161`, `source/cseries/errors.c:161` | Wall-clock seconds for `GetSystemTime`, `system_seconds`, and dated error output. Linked member: `libc_a-time.o` via PS2SDK `ps2time`. Not frame timing. |
| `towlower` | `source/cseries/cseries.c:619-634` (`csstrcasecmp`) | Folds each `char` byte. Newlib `libc_a-towlower.o` is locale `wchar_t` conversion; the approved fold is the same ASCII `A`–`Z` map as `_stricmp`. |
| `transport_initialize` | `source/game/game.c:317` | CE starts XNet/WSA and returns `_transport_error_none` (0) on success or `_transport_error_not_initialized` on failure. The generated `memset` zero is success. `game.c` ignores the result; reporting success still names a live Winsock/XNet service that this image does not start. |
| `transport_dispose` | `source/game/game.c:811` | CE returns `_transport_error_none` only after cleanup of an initialized transport; otherwise `_transport_error_not_initialized`. |
| `ui_set_next_level` | `source/main/main.c:2409` (`main_won_map_private`, rooted through `.text.main_loop`) | After the network co-op branch returns: level `0..9` calls `main_set_map_name(main_get_solo_level_name(level)); main_disallow_persistent_storage();`, `NONE` calls `main_roll_credits();`, any other level calls `main_goto_main_menu();`. |
| `ui_widget_load_by_name_or_tag` | `source/interface/player_ui.c:662` (`player_ui_fast_setup_network_server`) | CE allocates a widget from the excluded pool. The generated NULL is an honest failure; a non-NULL stub would start the network-server success path. |
| `ui_widget_load_progress_widget` | `source/game/game.c:749` (`game_unload`) | CE `error(_error_silent, "the old loading progress screen has been replaced with glowy halo gravy");`. `_error_silent` writes diagnostics and does not queue `display_error` UI state (`source/cseries/errors.c:248-268`). |
| `ui_widgets_active_for_local_player` | `source/game/player_control.c:620` | `player_control_port_menu_has_controller` zeroes input when this is true (`player_control.c:655-658`). |
| `ui_widgets_close_all` | `source/game/game.c:759,893,969`, `source/game/game_engine.c:5689`, `source/interface/player_ui.c:654` | Closes the virtual keyboard and clears per-player active widgets across map/session teardown. |
| `ui_widgets_disable_pause_game` | `source/main/main.c:1507,2026,2045,2068,2913` | Stores `pause_disabled_ticks`. |
| `ui_widgets_dispose` | `source/game/game.c:782` | `ui_widgets_close_all()` then releases widget state. |
| `ui_widgets_inhibit_processing` | `source/main/main.c:1524,1548` | Writes `processing_inhibited` around map-name fade. |
| `ui_widgets_initialize` | `source/game/game.c:313` | Resets globals, records initialization, sets `fade_to_black = -1.0f`. |
| `ui_widgets_set_fade_value` | `source/main/main.c:1525,1533,1544` | Writes `fade_to_black`. |
| `vswprintf` | `source/text/unicode.c:1468,1514` | `usprintf`/`uvsprintf` call `vswprintf(string, format, arglist)`. Newlib `libc_a-vswprintf.o` takes a `size_t` count before the format. |
| `xbox_set_machine_name` | `source/hs/hs.c:15102` (`xbox_set_machine_name_evaluate`) | CE converts the script string and calls `XSetNicknameW`, or reports an error. There is no Xbox nickname store. |

## Disposition rationale

- `sound_cache_new`, `sound_cache_open`, `sound_cache_close`, `sound_cache_delete`, `sound_cache_idle`, `sound_cache_flush`, `sound_cache_sound_finished`: `implemented`. `sound_initialize` calls `sound_cache_new()` before the platform `-1` return, so the datum exists on this profile. Map load/unload pair `data_make_valid` / drain / `data_make_invalid`. Finish is the CE NULL-safe decrement. `_sound_cache_sound_request` remains a later slice; this owner does not invent resident permutations.
- `strtok`: `implemented` by pinned Newlib `libc_a-strtok.o`. `csstrtok` returns that pointer; the `cseries.h` name remap stops recursion. Single-threaded EE reent state is the strtok save pointer.
- `structure_bsp_header_*`, `tags_header_*`: `state-adapter`. The CE bodies talk only to D3D vertex/index objects from excluded `cache_files_windows.c`. No compiled PS2 unit reads `D3DCOMMON_TYPE_*` or calls `IDirect3DVertexBuffer8_Register`. The load/unload pairing still runs; the adapter does not leave a D3D registration because none is created.
- `texture_cache_open`, `texture_cache_close`, `texture_cache_flush`: `state-adapter`. `texture_cache_new` is not a live external, so CE `data_make_valid(xbox_texture_cache_globals.textures)` would operate on a missing LRU. Close still calls flush. Parent GS packs are a different owner.
- `texture_cache_debug_options`: `implemented` as the CE `{0}` object. The defining HaloScript globals write bytes 0 and 1. The excluded Xbox debug renderer is the only CE reader.
- `time`: `implemented` by pinned Newlib `libc_a-time.o` / PS2SDK RTC glue. Callers are wall-clock diagnostics, not `GetTickCount` / EE bus-clock frame time.
- `towlower`: `implemented` as the ASCII identifier fold already used by `_stricmp`. `csstrcasecmp` passes `char` bytes, not locale `wchar_t` text.
- `transport_initialize`, `transport_dispose`: `state-adapter`. Return `_transport_error_not_initialized`. The generated zero is `_transport_error_none` and would report success for a service that did not start XNet/WSA.
- `ui_set_next_level`: `implemented` from `source/interface/ui_widget.c:2086-2107`. The four `main_*` callees are declared, not copied from the rest of `ui_widget.c`.
- `ui_widget_load_by_name_or_tag`: `state-adapter` NULL. `ui_widget.c` is excluded, so no definition/pool exists. `player_ui_fast_setup_network_server` treats NULL as failure and calls `main_goto_main_menu()`. Returning a fake instance would report success for a failed menu/server setup.
- `ui_widget_load_progress_widget`: `implemented` as the CE `_error_silent` diagnostic. That priority does not set widget error-dialog state.
- `ui_widgets_initialize`, `ui_widgets_dispose`, `ui_widgets_close_all`, `ui_widgets_active_for_local_player`, `ui_widgets_disable_pause_game`, `ui_widgets_inhibit_processing`, `ui_widgets_set_fade_value`: `implemented` as the CE write/query contract on a local widget record. Close also honors `if (virtual_keyboard_active()) virtual_keyboard_close();`. Load never inserts instances, so the player-control menu gate stays false until a later UI owner creates widgets.
- `vswprintf`: `implemented` with the CE three-argument shape used by `usprintf`/`uvsprintf`. The Newlib four-argument member reads the format pointer as a count.
- `xbox_set_machine_name`: `state-adapter`. The HaloScript evaluator is void (`HS_EVALUATE_VOID_STRING`). The name is stored locally; `XSetNicknameW` is not called.

Re-open before adding SPU2 sound request, a GS texture-pack handoff for the CE texture datum, D3D-equivalent buffer registration, XNet/Winsock, a widget definition pool, or an Xbox nickname service.

## Regression

`tests/test_hcu_external_review_batch_7.py::test_batch_7_rooted_symbols_are_dispositioned` loads `docs/hcu-source-backed-review/batches/batch-7.json`, checks every assigned symbol, and asserts at least one real CE source snippet for each approved contract.

## Approved contract snippets

These CE lines are the review path for each approved contract:

- `data_make_invalid(xbox_sound_cache_globals.cache_sounds);`
- `data_dispose(xbox_sound_cache_globals.cache_sounds);`
- `cache_sound->software_reference_count == 0 &&`
- `sound_cache_idle();`
- `physical_memory_get_sound_cache_base_address();`
- `data_make_valid(xbox_sound_cache_globals.cache_sounds);`
- `cache_sound->software_reference_count--;`
- `return strtok(s1, s2);`
- `IDirect3DVertexBuffer8_BlockUntilNotBusy(vertex_buffer);`
- `IDirect3DVertexBuffer8_Register(vertex_buffer, NULL);`
- `tags_header_deregister_vertex_and_index_buffers(cache_file_globals.tag_header);`
- `tags_header_register_vertex_and_index_buffers(cache_file_globals.tag_header);`
- `data_make_invalid(xbox_texture_cache_globals.textures);`
- `texture_cache_debug_options + 0x1`
- `lruv_flush(xbox_texture_cache_globals.cache);`
- `data_make_valid(xbox_texture_cache_globals.textures);`
- `return time(NULL);`
- `c1 = towlower(*s1);`
- `result = _transport_error_not_initialized;`
- `return _transport_error_not_initialized;`
- `main_set_map_name(main_get_solo_level_name(level));`
- `if (ui_widget_load_by_name_or_tag(`
- `the old loading progress screen has been replaced with glowy halo gravy`
- `ui_widgets_active_for_local_player(gamepad_index);`
- `if (virtual_keyboard_active())`
- `widget_globals.pause_disabled_ticks = duration_ticks;`
- `ui_widgets_close_all();`
- `widget_globals.processing_inhibited = inhibit;`
- `widget_globals.fade_to_black = -1.0f;`
- `widget_globals.fade_to_black = value;`
- `result = vswprintf(string, format, arglist);`
- `if (!XSetNicknameW(wide_machine_name, TRUE))`

## Sources

- `submodules/halo-ce-universal/port/ps2/port.json:35-66`
- `submodules/halo-ce-universal/source/cache/cache_files.c:626-627,649,1224-1225,1328,1497,1517`
- `submodules/halo-ce-universal/source/cache/xbox_sound_cache.c:211-456`
- `submodules/halo-ce-universal/source/cache/xbox_texture_cache.c:218-221,340,355-360,548-555,726-736,877,949`
- `submodules/halo-ce-universal/source/cache/cache_files_windows.c:428-536`
- `submodules/halo-ce-universal/source/sound/sound_manager.c:811,920-928,1287,3812,4002`
- `submodules/halo-ce-universal/source/interface/ui_widget.c:1660-1667,1852-1857,1954-1961,2031-2040,2086-2107,2163-2208,2912-2933,3897-3960,4369-4396`
- `submodules/halo-ce-universal/source/interface/player_ui.c:654-691`
- `submodules/halo-ce-universal/source/game/game.c:313,317,749,782,811,969`
- `submodules/halo-ce-universal/source/game/player_control.c:620,655-658`
- `submodules/halo-ce-universal/source/game/game_engine.c:5689`
- `submodules/halo-ce-universal/source/main/main.c:1507,1524-1548,2409-2420`
- `submodules/halo-ce-universal/source/cseries/cseries.c:554-560,608-634`
- `submodules/halo-ce-universal/source/cseries/cseries.h:279`
- `submodules/halo-ce-universal/source/cseries/cseries_windows.c:161`
- `submodules/halo-ce-universal/source/cseries/errors.c:161,248-268`
- `submodules/halo-ce-universal/source/text/unicode.c:1468,1514`
- `submodules/halo-ce-universal/source/hs/hs.c:14195-14196,15102`
- `submodules/halo-ce-universal/source/hs/hs_globals_external.c:1926-1928`
- `submodules/halo-ce-universal/source/networking/network_game_manager.c:232-243`
- `submodules/halo-ce-universal/source/bungie_net/network/transport.h:20-46`
- `submodules/halo-ce-universal/source/bungie_net/network/transport_endpoint_set_winsock.c:252-377`
- `submodules/halo-ce-universal/port/ps2/src/ps2_time.c:49`
- `submodules/halo-ce-universal/port/ps2/src/ps2_m0_batch_7.c`
- `build/hcu-ps2-closure/all/ps2_platform.c`
- `build/hcu-ps2-closure/all/halo-local.map`
- `docs/hcu-source-backed-review/hcu-ps2-external-review.json`
