# CE rooted externals in pending slice [64:96]

Status: every pending symbol in the sorted ledger slice `[64:96]` is dispositioned from its live caller sections and `caller_sources`. Generated typed zeros are not approved where they skip stock vehicles, halt a failed cache, pause after a pad unplug, encode a CTF owner, show campaign help, or size the halt viewport. Those six functions plus the stock `custom_edition_vehicles_by_placement` predicate are implemented in `port/ps2/src/ps2_m0_batch_2.c`. The remaining rows are explicit local-profile state adapters or reachability exclusions.

## Evidence and boundary

The slice was taken from `docs/hcu-source-backed-review/hcu-ps2-external-review.json` by selecting `disposition == "pending"`, sorting by symbol name, and keeping `[64:96]`. Each row's caller sections were read in CE, then matched to the generated or real body in `build/hcu-ps2-closure/all/ps2_platform.c` or `port/ps2/src/ps2_edge.c`. Data-section storage (`dsound_globals`, `global_rasterizer_model_ambient_reflection_tint`) was traced to the defining object, not inferred from the name.

`source/interface/ui_widget.c`, `source/networking/`, `source/editor/`, and `source/render/` are excluded by `port/ps2/port.json`. Linux-port owners (`custom_edition_*.c`, `first_person_legs.c`, `hud_hires_tags.c`, `network_distributed.c`) are not in the PS2 manifest. A missing owner is not a license to keep a generated false that already changes stock placement or first-person identity.

## Disposition table

| Symbol | Caller file:line | Effect | Disposition | Sources |
|---|---|---|---|---|
| `custom_edition_structure_bsp_reference_valid` | `source/cache/cache_files.c:1390-1393` | CE BSP file/destination check. Only entered when `custom_edition_cache_tags_loaded()` is true. | `excluded-proven` | generated `custom_edition_cache_tags_loaded` is false (`ps2_platform.c:166`); stock BSP uses `cache_file_structure_bsp_reference_verify` |
| `custom_edition_structure_bsp_unload` | `source/cache/cache_files.c:1520-1521` | Releases CE-converted BSP geometry. Same `tags_loaded` gate. | `excluded-proven` | no CE load owner exists; paired unload is not reached |
| `custom_edition_vehicle_placement_allowed` | `source/objects/object_types.c:1230-1234` | `object_types_place_all` `continue`s a vehicle when this is false. Generated false skips stock vehicles. | `implemented` | CE `return !custom_edition_vehicles_by_placement() \|\| TEST_FLAG(...)` (`custom_edition_objects.c:118-119`); batch owner returns TRUE on the false predicate |
| `custom_edition_vehicles_by_placement` | `source/game/game_engine.c:7729-7730` | True keeps a CE map's vehicle set; false uses Xbox remapping. | `implemented` | CE requires `custom_edition_cache_tags_loaded()` (`custom_edition_objects.c:107`); this image has no CE cache, so FALSE |
| `display_error_damaged_media` | `source/cache/cache_files.c:1198-1207`; `source/game/game.c:760-761,894-895` | Cache/map status 2. CE ends the input frame and enters `main_loop_of_death`. An empty body lets load/unload continue. | `implemented` | `ui_widget.c:4641-4648`; batch owner calls `input_frame_end` then `main_loop_of_death` |
| `display_error_deferred` | `source/input/input_abstraction.c:825` | Pad-unplug stores error/modal/pause. In-game local sets both pause arguments TRUE. `process_ui_widgets` is empty, so the generated no-op drops the pause. | `implemented` | `ui_widget.c:4284-4310,3811-3813`; batch owner stores the record and calls `game_time_set_paused(TRUE)` |
| `display_error_when_main_menu_loaded` | `source/main/main.c:3588,3597,3603,3649` | Queues a main-menu error. Every rooted call is inside a network-client or network-server branch. | `excluded-proven` | `main_setup_connection` sets `_game_connection_local` (`main.c:2861`); `create_global_network_game_*` are generated false; `player_ui_fast_setup_network_server` never promotes the connection |
| `display_errors_deferred_until_cinematic_stop` | `source/cutscene/cinematics.c:258` | Drains `widget_globals.deferred_cinematic_errors` and writes NONE. | `excluded-proven` | the only writer is `display_error` while a cinematic is active (`ui_widget.c:4405-4417`); `ui_widget.c` is excluded, so the queue is not in the image |
| `display_scenario_help` | `source/hs/hs.c:15101` | HaloScript maps the active scenario to a campaign help widget. An empty body drops authored help. | `implemented` | `ui_widget.c:4703-4746`; batch owner keeps the scenario-name map and records the request. Widget load remains excluded |
| `dispose_global_network_game_client` | `source/interface/player_ui.c:656,681`; `source/main/main.c:2435,2439` | CE disposes only when a client pointer exists, then clears `client_started`. | `state-adapter` | `network_game_globals.c:471-481`; `ps2_local.c:36-38` returns NULL; create is generated false; empty dispose matches CE's null-session path |
| `dispose_global_network_game_server` | `source/interface/player_ui.c:655,680`; `source/main/main.c:2436` | CE disposes only when a server pointer exists. | `state-adapter` | `network_game_globals.c:421-429`; `ps2_local.c:31-34` returns NULL |
| `distributed_player_to_byte` | `source/game/game_engine_ctf.c:703,771,795,1224` | Encodes flag returner/grabber/capturer. Generated 0 maps `NONE` to player 0. | `implemented` | CE `player_index != NONE ? (byte)DATUM_INDEX_TO_ABSOLUTE_INDEX(player_index) : NO_PLAYER` with `NO_PLAYER = 0xFF` |
| `dsound_globals` | defining object `ps2_platform.c:220`; readers in `source/sound/sound_dsound_xbox.c` | Generated `unsigned char[30924]` is not an initialized device. | `excluded-proven` | `sound_preferences.c:33-34` sets platform `-1`; `sound_initialize` returns before `platform_definitions[0]` (`sound_manager.c:924-928`) |
| `fclose` | `source/game/cheats.c:261`; `source/main/main.c:1897` | Closes a `FILE*` the caller opened. | `implemented` | linked `libc_a-fclose.o`; callers only close a non-NULL handle |
| `fflush` | `source/cseries/errors.c`; `source/main/main.c`; `source/saved games/game_state.c`; `source/structures/structure_lens_flares.c` | Flushes a file-backed stream. Newlib reports the flush result, not a generated success. | `implemented` | linked `libc_a-fflush.o` |
| `fgets` | `source/game/cheats.c:248`; `source/main/console.c:414` | Reads cheat/init lines. NULL/EOF stops the loop. | `implemented` | linked `libc_a-fgets.o` |
| `first_person_legs_reset` | `source/objects/objects.c:1076` | CE clears Linux-port waist/mesh caches. | `excluded-proven` | `first_person_legs.c` and `object_mesh.c` are not in `port.json`; `source/render/` is excluded, so no consumer of that cache is compiled |
| `fopen` | `source/game/cheats.c:240`; `source/main/main.c:1890`; `source/camera/director.c:432` | Opens Xbox `d:`/`z:` paths. Newlib returns NULL; callers branch on the handle. | `implemented` | linked `libc_a-fopen.o`; `main_load_last_solo_map` falls back to `scenario_paths[0]` when the file is missing |
| `fprintf` | object/error/camera/game-state dump paths | Formats to a `FILE*`. Distinct from reviewed stdout `printf`. | `implemented` | linked `libc_a-fprintf.o`; write failure is the Newlib return, not a generated success |
| `fputc` | `source/objects/objects.c` | One-byte dump writer. | `implemented` | linked `libc_a-fputc.o` |
| `fputs` | `source/objects/objects.c`; `source/structures/structure_lens_flares.c` | String dump writer. | `implemented` | linked `libc_a-fputs.o` |
| `fread` | `source/main/main.c:1896` | Reads `z:\\last_solo.txt` only after a successful `fopen`. | `implemented` | linked `libc_a-fread.o` |
| `fscanf` | `source/camera/director.c:446-449` | Parses `d:\\camera.txt` only after a successful `fopen`. | `implemented` | linked `libc_a-fscanf.o` |
| `game_in_editor` | `source/game/game.c:712`; `source/objects/object_types.c:1049,1183`; `source/main/main.c:3438-3473` | False selects normal AI/object/player/map branches. | `state-adapter` | CE non-editor stub returns FALSE (`editor_stubs.c:18-22`); generated zero matches that stub |
| `global_rasterizer_model_ambient_reflection_tint` | `source/cutscene/cinematics.c:250-256` | `cinematic_stop` clears the ARGB only when the pointer is non-NULL. | `state-adapter` | generated BSS pointer is NULL; Xbox/script writers live in excluded `source/rasterizer/` |
| `gmtime_r` | `port/ps2/src/ps2_time.c:50` | `GetSystemTime` converts `time(NULL)` to UTC fields and zeros the SYSTEMTIME when `gmtime_r` fails. | `implemented` | linked `libc_a-gmtime_r.o` |
| `halo_custom_edition_tag_cache` | `source/cache/cache_files.c:375-377` | CE tag-cache base used only after `custom_edition_cache_tags_loaded()`. Generated NULL is "no CE backing". | `state-adapter` | Linux owner returns a reserved window (`xbox_memory.c:128-131`); this image has no reservation |
| `halo_interpolation_enabled` | `source/main/main.c:2524,2772,3661` | True selects the unthrottled interpolation time path. False keeps the Xbox throttled loop. | `state-adapter` | generated int zero; Linux owner reads `display.interpolation` (`sdl_platform.c:364`) |
| `halo_screen_width` | `source/main/main.c:3216` | Halt viewport `x1`. Generated 0 overrode the weak 512 default. | `implemented` | `ps2_edge.c:37-39` weakly returns 512; `src/stream/hcu_main.c:25` may still override with `VIDEO_WIDTH` |
| `hud_hires_tags_loaded` | `source/cache/cache_files.c:1351-1353` | Rebuilds Linux-port HUD bitmap tables. | `excluded-proven` | `hud_hires_tags.c` is not compiled; `hud_hires_button_draw` / `hud_hires_sprite_bitmap` are generated false/NULL and `hud_messaging.c:552-554` falls through to stock HUD |
| `hud_hires_tags_unloaded` | `source/cache/cache_files.c:622-624` | Clears those tables before cache teardown. | `excluded-proven` | paired with the omitted load; empty unload of absent tables does not retain map pointers |
| `initialize_network_game_packets` | `source/game/game.c:319` | Initializes the network message `data_packet_group`. | `excluded-proven` | `source/networking/` is excluded; encode/decode of that group live only in `network_messages.c:669,871` |

## New C definitions

`port/ps2/src/ps2_m0_batch_2.c` defines the seven names listed in `docs/hcu-source-backed-review/batches/batch-2-skip.txt`. `halo_screen_width` is weak so a later parent `VIDEO_WIDTH` still wins.

## Regression

`tests/test_hcu_external_review_batch_2.py::test_batch_2_rooted_symbols_are_dispositioned` reloads this slice, checks every batch row, and requires a real CE/port/generated snippet for each approved contract.

## Sources

- `docs/hcu-source-backed-review/hcu-ps2-external-review.json`
- `build/hcu-ps2-closure/all/ps2_platform.c`
- `build/hcu-ps2-closure/all/halo-local.map`
- `submodules/halo-ce-universal/port/ps2/src/ps2_m0_batch_2.c`
- `submodules/halo-ce-universal/port/ps2/src/ps2_edge.c:37-39`
- `submodules/halo-ce-universal/port/ps2/src/ps2_time.c:42-70`
- `submodules/halo-ce-universal/port/ps2/game/ps2_local.c:31-38`
- `submodules/halo-ce-universal/port/linux/game/custom_edition_objects.c:104-119`
- `submodules/halo-ce-universal/port/linux/game/network_distributed.c:1157-1161`
- `submodules/halo-ce-universal/source/objects/object_types.c:1230-1234`
- `submodules/halo-ce-universal/source/cache/cache_files.c:375-377,622-624,1198-1207,1351-1353,1390-1393,1520-1521`
- `submodules/halo-ce-universal/source/interface/ui_widget.c:1970-1976,4284-4310,4338-4364,4405-4417,4641-4648,4703-4746`
- `submodules/halo-ce-universal/source/input/input_abstraction.c:768-825`
- `submodules/halo-ce-universal/source/main/main.c:1880-1908,2432-2440,2524-2528,2861,3216,3583-3649`
- `submodules/halo-ce-universal/source/editor/editor_stubs.c:18-22`
- `submodules/halo-ce-universal/source/sound/sound_preferences.c:28-37`
- `submodules/halo-ce-universal/source/sound/sound_manager.c:908-928`
