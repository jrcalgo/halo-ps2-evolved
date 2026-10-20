# CE roots under the PS2 M0 batch-4 slice

Status: pending slice `[128:160]` is closed. `qsort` and `rand` stay on pinned Newlib. The other thirty names are owned by `port/ps2/src/ps2_m0_batch_4.c`. Generated memset-zero or empty bodies are not approved where they stop first-person animation, invent a network session, leave a zero `rasterizer_debug_options` object, or hand a live decal/triangle index that locks to NULL.

`create_global_network_game_client`, `create_global_network_game_server`, `dispose_global_network_game_client`, `dispose_global_network_game_server`, and `network_game_accept_remote_connections` are not in this slice. They remain on the HaloScript `player_ui_fast_setup_network_server` path. This batch only owns `pc_menus_screen` and `network_votekick_player_named` from that neighborhood.

## Evidence and boundary

The PS2 manifest excludes `source/interface/ui_widget.c`, `source/interface/progress_bar.c`, and `source/rasterizer/` (`port/ps2/port.json:35-65`). The Linux PAL, votekick, menu-path, and powerup-bounds files are not in `port_sources`. Live callers still come from compiled CE: HaloScript, `scenario_tags_load`, `first_person_weapons_update`, `weapon_get_first_person_animation_time`, `main_loop`, `game_initialize` / `game_dispose`, `bitmap_delete`, decal lifetime, `shell_dispose`, and the saved-game `.data.after_load_procs` table.

`.data.after_load_procs` is the after-load array in `source/saved games/game_state.c:196-211`. `rasterizer_decals_update_function_pointers` is one entry. `game_state_call_after_load_procs` runs it after a core load (`249-255,370`).

## Disposition rationale

| Symbol | Caller | Effect | Disposition |
|---|---|---|---|
| `network_votekick_player_named` | `source/hs/hs.c:15456` inside `hs_compile_and_evaluate_command` | CE returns FALSE when `network_votekick_available()` is false (`port/linux/game/network_votekick.c:971-974`). A true result would start a kick. This profile has no session. | `implemented` FALSE. Does not pretend a server exists. |
| `pal_tags_first_person_advance` | `source/interface/first_person_weapons.c:1858-1863` | FALSE is `_animation_no_key_frame` and skips `animation_update_render_only`. CE returns TRUE when the graph is not PAL (`port/linux/game/pal_tags.c:430-431`). Generated FALSE stops every first-person weapon. | `implemented` TRUE. |
| `pal_tags_first_person_frames` | `source/items/weapons.c:1382,1419` | Replaces the animation frame count. CE returns the incoming NTSC count when the graph is not PAL (`pal_tags.c:397-399`). Generated zero is not that count. | `implemented` return `frames`. |
| `pal_tags_loaded` | `source/cache/cache_files.c:1332-1334` | CE zeros PAL state and returns unless the build region is `"PAL"` (`pal_tags.c:373-380`). This profile does not rewrite biped/weapon/projectile tags. | `state-adapter` NTSC-only no-rewrite. |
| `pc_menus_screen` | `source/interface/player_ui.c:654-669` | `player_ui_fast_setup_network_server` closes widgets, disposes any client/server, and sets the local connection **before** this call. CE returns `name` when `menu_tags.loaded` is false (`port/linux/game/menu_tags.c:2321`). Generated NULL fails the load and is not the CE pass-through. A remapped PC path would pretend the Linux menus exist. | `implemented` return `name`. Widget load still decides; this is not a successful menu. |
| `powerup_render_bounds_tags_loaded` | `source/cache/cache_files.c:1339-1341` | Linux enlarges overshield/camo radii (`port/linux/game/powerup_render_bounds.c:163-183`). Xbox CE keeps authored bounds. | `excluded-proven` omitted Linux enhancement. |
| `process_ui_widgets` | `source/main/main.c:3294,3617` | CE asserts `widget_globals.initialized`, then walks active widgets, pause, attract, and deferred errors (`source/interface/ui_widget.c:8434-8639`). `ui_widget.c` is excluded, so there is no pool. The only live CE gate this adapter can evaluate is `virtual_keyboard_active()`, already false on the pad profile. | `state-adapter` no widget pool. |
| `progress_bar_dispose` | `source/game/game.c:813` | CE body is already `return;` (`source/interface/progress_bar.c:1576-1579`). | `excluded-proven` exact CE empty. |
| `progress_bar_initialize` | `source/game/game.c:326` | CE copies `d:\\loading.tga` to `z:\\` through `CreateDirectoryA` / `CopyFileA` (`progress_bar.c:1565-1571`). Those Xbox paths are not a mounted PS2 filesystem, and `progress_bar.c` is excluded. A copy that did not happen must not be treated as success. The function is void. | `state-adapter` no writable TGA. |
| `qsort` | aim-assist, actor perception, vehicle script, objects, lens flares, HS tokens (`source/game/aim_assist.c:525` and the other rooted sections) | Newlib `libc_a-qsort.o` is already in `build/hcu-ps2-closure/all/halo-local.map`. This is a real sort, not a generated empty. Equal-key order follows Newlib, not the Xbox CRT. | `implemented` pinned Newlib. |
| `rand` | `source/math/random_math.c:156-159` | The only rooted caller mixes `rand()` into `system_seconds()^system_milliseconds()^rand()`. Newlib `libc_a-rand.o` is linked. A generated zero would collapse that mix. | `implemented` pinned Newlib. |
| `rasterizer_bitmap_delete` | `source/bitmaps/bitmaps.c:624-629` | CE also releases `hardware_format` (`source/rasterizer/xbox/rasterizer_xbox_hardware_bitmaps.c:689-698`). This adapter never creates a D3D texture; it still nulls a leftover pointer so bitmap teardown does not keep a hardware binding. | `implemented` clear `hardware_format`. |
| `rasterizer_debug_options` | `.data.f0_definition`… plus `source/main/main.c:3345`, `source/game/cheats.c:138-164`, `source/effects/decals.c:2095`, `source/camera/flying_camera.c:76-81` | HaloScript globals point at fields (`source/hs/hs_globals_external.c:1260`). CE starts `draw_models`, `draw_environment == 2`, `zoffset = 1/256`, and `force_all_player_views_to_default_player == FALSE` (`source/rasterizer/rasterizer.c:602-687`). Generated BSS is zero. | `implemented` retail initializer. |
| `rasterizer_decal_vertices_new` | `source/effects/decals.c:2108` | `cache_index != NONE` is the insert gate. Generated zero is a valid-looking index that then locks to NULL. | `implemented` bounded slots; `NONE` on exhaustion. |
| `rasterizer_decal_vertices_lock` | `source/effects/decals.c:2122` | CE writes quads only when the lock is non-NULL (`2126-2230`). | `implemented` writable span or NULL. |
| `rasterizer_decal_vertices_unlock` | `source/effects/decals.c:2226` | Closes the write window. | `implemented` clear lock. |
| `rasterizer_decal_vertices_delete` | `source/effects/decals.c:911,2234,2244,2394` | Permanent delete and failed insert/lock both call delete. | `implemented` free the slot. |
| `rasterizer_decals_initialize` | `source/effects/decals.c:513` | Xbox allocates the GPU lruv cache (`rasterizer_xbox_decals.c:497-536`). This adapter owns a BSS cache and marks it initialized. | `implemented` bounded CPU cache. |
| `rasterizer_decals_initialize_for_new_map` | `source/effects/decals.c:536` | Xbox `_rasterizer_decals_initialize_for_new_map` is already `return;` (`rasterizer_xbox_decals.c:455-458`). | `excluded-proven` exact Xbox empty. |
| `rasterizer_decals_dispose_from_old_map` | `source/effects/decals.c:549` | Xbox flushes the lruv cache (`461-470`). | `implemented` reset the BSS cache. |
| `rasterizer_decals_dispose` | `source/effects/decals.c:559` | Xbox releases the D3D buffer (`540-561`). | `implemented` reset and clear initialized. |
| `rasterizer_decals_flush` | HaloScript `rasterizer_decals_flush_evaluate` (`source/hs/hs.c:14222`) | Xbox unlocks and `lruv_flush` (`955-964`). | `implemented` reset the BSS cache. |
| `rasterizer_decals_update_function_pointers` | `.data.after_load_procs` (`game_state.c:203`) | Xbox rewrites lruv callbacks stored in game-state (`482-493`). This cache is BSS, so there are no stale callbacks. | `state-adapter` no game-state lruv. |
| `rasterizer_dispose` | `source/shell/shell.c:84` | Xbox releases the D3D device (`rasterizer_xbox.c:1910-1935`). `ps2_edge.c:106` set `rasterizer_globals.initialized`. Teardown clears that bit and the batch-4 arenas. | `implemented` `initialized = FALSE`. |
| `rasterizer_dispose_from_old_map` | `source/game/game.c:936` | CE nulls `global_rasterizer_data` (`rasterizer_common.c:57-63`). This adapter never stored that tag pointer; it drops map-owned default hardware-format leftovers and the arenas. | `implemented` clear map leftovers. |
| `rasterizer_dynamic_triangles_new` | `source/objects/widgets/flags.c:751`, `source/game/game_engine_king.c:648` | Xbox returns `NONE` on exhaustion (`rasterizer_xbox_draw_primitives.c:615-661`). Callers check `NONE` before lock. Generated zero is a live index. | `implemented` bounded shorts; `NONE` on exhaust. |
| `rasterizer_dynamic_triangles_lock` | `flags.c:775`, `game_engine_king.c:653` | Returns writable triangle storage for a live index; NULL for `NONE`. | `implemented` |
| `rasterizer_dynamic_triangles_unlock` | `flags.c` / `game_engine_king.c:671` | Closes the write window. | `implemented` |
| `rasterizer_dynamic_triangles_delete` | `flags.c:958`, `game_engine_king.c:741` | Marks the slot unused and resets the bump when idle. | `implemented` |
| `rasterizer_dynamic_unlit_geometry_draw` | `source/objects/widgets/lightning.c:453` | Submits CPU vertices. This file does not own GS/VU1. A void body is not a report that the bolt was presented. | `state-adapter` CPU-only; no GS submit. |
| `rasterizer_dynamic_vertices_delete` | `flags.c:959`, `lightning.c:462`, `game_engine_king.c:742` | Xbox `_rasterizer_dynamic_vertices_delete` is already `return;` (`draw_primitives.c:973-977`). `vertices_new` / `unlock` are the next slice. | `excluded-proven` exact Xbox empty. |
| `rasterizer_dynamic_vertices_lock` | `flags.c:774`, `lightning.c:351`, `game_engine_king.c:652` | Callers write through the pointer. Generated `vertices_new` (next slice) still returns 0, which is not `NONE`. A NULL lock would crash flag cloth and trip lightning's `vertices` assert. | `implemented` writable scratch for a non-`NONE` index. |

Re-open `pal_tags_loaded` before shipping a PAL map: the NTSC pass-through would leave PAL tag timing in place. Re-open `process_ui_widgets` before a widget pool, attract mode, or UI pause. Re-open `pc_menus_screen` before Linux PC menu remapping. Re-open the dynamic vertex `new`/`unlock` pair with the next slice so lock and new share one arena. Re-open unlit draw when the parent GS owner consumes the CPU buffers.

## Regression

`tests/test_hcu_external_review_batch_4.py::test_batch_4_rooted_symbols_are_dispositioned` reloads this slice from the shared ledger, checks `batches/batch-4.json`, and requires a real CE or batch-4 C snippet for every approved contract.

## Sources

- `submodules/halo-ce-universal/port/ps2/src/ps2_m0_batch_4.c`
- `submodules/halo-ce-universal/port/ps2/port.json:35-65`
- `submodules/halo-ce-universal/source/hs/hs.c:15440-15456`
- `submodules/halo-ce-universal/source/interface/player_ui.c:651-691`
- `submodules/halo-ce-universal/source/interface/first_person_weapons.c:1858-1868`
- `submodules/halo-ce-universal/source/items/weapons.c:1379-1422`
- `submodules/halo-ce-universal/source/cache/cache_files.c:1332-1341`
- `submodules/halo-ce-universal/source/main/main.c:3294,3345,3617`
- `submodules/halo-ce-universal/source/game/game.c:326,813,936`
- `submodules/halo-ce-universal/source/game/cheats.c:138-164`
- `submodules/halo-ce-universal/source/effects/decals.c:513-559,2108-2234`
- `submodules/halo-ce-universal/source/saved games/game_state.c:196-211`
- `submodules/halo-ce-universal/source/objects/widgets/flags.c:751-775,958-959`
- `submodules/halo-ce-universal/source/objects/widgets/lightning.c:346-462`
- `submodules/halo-ce-universal/source/game/game_engine_king.c:648-653`
- `submodules/halo-ce-universal/source/bitmaps/bitmaps.c:624-629`
- `submodules/halo-ce-universal/source/rasterizer/rasterizer.c:602-687`
- `submodules/halo-ce-universal/source/rasterizer/xbox/rasterizer_xbox_draw_primitives.c:615-753,973-977`
- `submodules/halo-ce-universal/source/rasterizer/xbox/rasterizer_xbox_decals.c:455-458,482-493`
- `submodules/halo-ce-universal/port/linux/game/pal_tags.c:367-431`
- `submodules/halo-ce-universal/port/linux/game/network_votekick.c:961-974`
- `submodules/halo-ce-universal/port/linux/game/menu_tags.c:2305-2328`
- `build/hcu-ps2-closure/all/halo-local.map` (`libc_a-qsort.o`, `libc_a-rand.o`)
- `docs/hcu-source-backed-review/hcu-ps2-external-review.json`
