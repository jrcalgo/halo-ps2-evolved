# CE render-clock, interpolation, and leftover roots under the PS2 M0 slice

Status: slice `[192:224]` of the pending ledger is closed. Widget draw/submit and the halt-screen window brackets stay excluded as parent-owned presentation. Effect switches, the `render` frame clock, render lifecycle, disabled interpolation, the last player-1 profile index, and Newlib `rint` are approved against the CE call sites below. Re-open the widget and present rows before a PS2 GS widget/present owner is linked.

## Evidence and boundary

`source/render/` and `source/rasterizer/` are excluded from the PS2 manifest except `render_cameras.c`, `rasterizer_geometry.c`, and `rasterizer_swizzle.c` (`port/ps2/port.json:35-42,78-83`). The generated bodies in `build/hcu-ps2-closure/all/ps2_platform.c` therefore stand in for CE `render.c`, `render_objects.c`, Linux interpolation, and the Xbox widget wrappers. A typed zero-return or BSS-zero global is not the CE contract for this slice: `particles_update` and `particle_new` read `render.frame_index` (`source/effects/particles.c:902,1023-1038`), `glow_submit` advances trailing particles with `render.time_delta_since_tick_sec` (`source/objects/widgets/glow.c:1433,1449`), and `main_game_render` overwrites a valid observer with `render_interpolation_camera` before `set_window_camera_values` (`source/main/main.c:3359-3367`).

Data-section callers were traced to their defining objects. `.data.editor_custom_render` is `editor_custom_render = &render` (`source/camera/editor_flying_camera.c:216`). `.data.render_contrails_definition`, `.data.render_particles_definition`, `.data.render_psystems_definition`, `.data.render_wsystems_definition`, and `.data.render_shadows_definition` are the HaloScript external globals that point at the four effect switches and `render_shadows` (`source/hs/hs_globals_external.c:1416-1422,1464`).

`ps2_m0_batch_6.c` owns the CPU contracts. It does not submit GS/VU1 geometry.

## Per-symbol dispositions

### `rasterizer_widget_draw_sprite3d` — excluded-proven

- Caller: `source/objects/widgets/light_volumes.c:312` (`light_volume_render`)
- Effect: CE draws one 3D sprite inside an Xbox widget batch. The function is void. The generated empty body drops only that sprite.
- Disposition: parent GS owns presentation. The call does not allocate, report success, or change campaign/UI cache state.
- Sources: `light_volumes.c:276-320`; `source/rasterizer/rasterizer.c:1703-1710`; generated empty `void` in `ps2_platform.c`.

### `rasterizer_widget_end` — excluded-proven

- Caller: `source/objects/widgets/light_volumes.c:320`
- Effect: CE closes the Xbox widget batch begun at `:276`. Empty end drops device scope only.
- Disposition: no compiled consumer reads a widget-begin flag. Pairing is presentation-only.
- Sources: `light_volumes.c:276-320`; `rasterizer.c:911-914`.

### `rasterizer_widget_set_texture` — state-adapter

- Caller: `source/objects/widgets/light_volumes.c:279`
- Effect: CE returns the Xbox bind result. `light_volume_render` does not test it, but a generated true-shaped success would be a failed service reporting success. The adapter returns `FALSE`.
- Disposition: fail-closed texture bind. Owned by `ps2_m0_batch_6.c`.
- Sources: `light_volumes.c:279-282`; `source/rasterizer/rasterizer_widgets.h:37-40`; `port/ps2/src/ps2_m0_batch_6.c`.

### `rasterizer_widget_submit` — excluded-proven

- Caller: `source/objects/widgets/light_volumes.c:367` (`light_volume_submit`)
- Effect: CE queues `light_volume_render` as the widget proc. The function is void.
- Disposition: dropping the Xbox queue does not change the preceding camera-distance test (`:358-366`).
- Sources: `light_volumes.c:328-372`; `rasterizer.c:1636-1642`.

### `rasterizer_window_begin` — excluded-proven

- Caller: `source/main/main.c:3231` (`.text.halt_and_catch_fire`)
- Effect: the fatal loop already writes `render.camera` from its window parameters (`:3230`) and then begins a window. Empty begin does not change that CPU camera copy.
- Disposition: halt-screen presentation only. Main-loop windows go through `render_frame`, which this slice owns separately.
- Sources: `main.c:3197-3275`; `source/rasterizer/rasterizer.h:411-412`.

### `rasterizer_window_end` — excluded-proven

- Caller: `source/main/main.c:3272`
- Effect: closes the halt-screen window. Void.
- Disposition: pairs the begin above. No split-screen CPU scope lives in this caller.
- Sources: `main.c:3231-3273`.

### `rasterizer_windows_begin` — excluded-proven

- Caller: `source/main/main.c:3202`
- Effect: opens the halt-screen multi-window scope. Void.
- Disposition: same halt-only rooted section as the per-window pair.
- Sources: `main.c:3197-3202`.

### `rasterizer_windows_end` — excluded-proven

- Caller: `source/main/main.c:3273`
- Effect: closes that halt-screen scope. Void.
- Disposition: same as begin.
- Sources: `main.c:3272-3274`.

### `render` — implemented

- Callers: `.data.editor_custom_render` (`editor_flying_camera.c:216`); `glow_submit` (`glow.c:1433,1449`); `halt_and_catch_fire` (`main.c:3230`); `light_volume_render` / `light_volume_submit` (`light_volumes.c:246-254,358-364`); `lightning_submit` (`lightning.c:400,517`); `particle_new` / `particles_update` (`particles.c:902,1023-1038`); `unit_render_debug` (`units.c:5060`).
- Effect: CE's `struct render_globals` is the camera, frame index, and time delta those units read. Generated BSS storage exists but `render_frame` never advanced `frame_index` or wrote `time_delta_since_tick_sec`.
- Disposition: `ps2_m0_batch_6.c` defines the CE object and `render_frame` / `render_frame_pregame` write the clock and the first player camera.
- Sources: `source/render/render.h:77-109`; `source/render/render.c:144,245,607-608`; `port/ps2/src/ps2_m0_batch_6.c`.

### `render_contrails_enabled` — state-adapter

- Caller: `.data.render_contrails_definition` → `&render_contrails_enabled` (`hs_globals_external.c:1416`)
- Effect: CE default is `TRUE` (`render.c:150`). Generated BSS is `FALSE` and would hide contrail submission if that render path is later linked.
- Disposition: retail `TRUE`, writable by `render_effects`.
- Sources: `render.c:150,163`; `hs_globals_external.c:1416`.

### `render_dispose` — implemented

- Caller: `source/game/game.c` `game_dispose`
- Effect: CE clears `cached_object_render_states` (`render_objects.c:312-316`).
- Disposition: pointer clear after game teardown.
- Sources: `render.c:186-190`; `render_objects.c:312-316`.

### `render_dispose_from_old_map` — implemented

- Caller: `source/game/game.c` `game_dispose_from_old_map`
- Effect: CE invalidates the cache when it is valid (`render_objects.c:301-308`).
- Disposition: map-transition invalidation, not a no-op.
- Sources: `render.c:180-184`; `render_objects.c:301-308`.

### `render_effects` — implemented

- Caller: `source/hs/hs.c` `render_effects_evaluate`
- Effect: writes the four effect switches (`render.c:157-164`).
- Disposition: script-visible state, not a no-op.
- Sources: `hs.c` `HS_EVALUATE_VOID_BOOLEAN(render_effects_evaluate, render_effects)`; `render.c:157-164`.

### `render_fov_vertical` — state-adapter

- Caller: `source/main/main.c:1169` (`set_window_camera_values`)
- Effect: writes the window's vertical FOV. Generated zero collapses the projection. Linux `view_fov.c:125-148` returns the native angle when `display.fov` is unset.
- Disposition: identity native FOV. No desktop config on this profile.
- Sources: `main.c:1158-1172`; `port/linux/game/view_fov.c:125-148`.

### `render_frame` — implemented

- Callers: `source/main/main.c:3383` (`main_game_render`); screenshot path `:2969,:2980`
- Effect: CE increments `render.frame_index`, stores `time_delta_since_tick_sec`, then submits windows (`render.c:594-654`). An empty body leaves particle cull and glow motion on a zero clock.
- Disposition: CPU clock and first-player camera snapshot. GS submission remains parent-owned.
- Sources: `render.c:607-608`; `particles.c:902,1035-1040`; `glow.c:1433,1449`.

### `render_frame_pregame` — implemented

- Caller: `source/main/main.c:2004` (`main_pregame_render`)
- Effect: CE increments `render.frame_index` and copies the pregame camera (`render.c:245,253`).
- Disposition: same frame clock. UI/Bink/progress-bar draw stay excluded with their own owners.
- Sources: `render.c:238-280`; `main.c:2004-2006`.

### `render_frame_present` — excluded-proven

- Callers: `source/main/main.c:1226` (`main_present_frame`); screenshot `:2976,:2981`
- Effect: CE calls `rasterizer_present` (`render.c:283-288`). Void.
- Disposition: present/screenshot capture is parent GS work. The empty body does not report success or change simulation/cache.
- Sources: `render.c:283-288`; `main.c:1226,2976`.

### `render_initialize` — implemented

- Caller: `source/game/game.c` `game_initialize`
- Effect: CE allocates `cached object render states` with `game_state_data_new` (`render_objects.c:281-288`). Size is `0x100` (`:198`).
- Disposition: game-state cache lifetime. Empty allocate would skip the arena entry.
- Sources: `render.c:166-170`; `render_objects.c:281-288,198`; `port/ps2/include/halo_ps2_limits.h:37`.

### `render_initialize_for_new_map` — implemented

- Caller: `source/game/game.c` `game_initialize_for_new_map`
- Effect: CE repairs transparent-part links and marks the cache valid (`render.c:172-178`).
- Disposition: `models_fix_transparent_part_links` plus `data_make_valid`.
- Sources: `render.c:172-178`; `source/models/models.c:532`; `render_objects.c:293-298`.

### `render_interpolation_camera` — state-adapter

- Caller: `source/main/main.c:3360`
- Effect: generated `memset` of a pointer returns `NULL`, so `set_window_camera_values` sees no observer. Linux disabled interpolation returns the input observer (`port/linux/game/render_interpolation.c:720-728`).
- Disposition: identity observer. Interpolation snapshots are not allocated.
- Sources: `main.c:3359-3367`; `render_interpolation.c:720-728`.

### `render_interpolation_fraction` — state-adapter

- Caller: `source/objects/widgets/antenna.c:434` (`antenna_render_proper`)
- Effect: native inactive path returns `1.0f` (`render_interpolation.c:514-517`). Generated zero is not that fallback.
- Disposition: inactive fraction `1.0f`.
- Sources: `antenna.c:434`; `render_interpolation.c:514-517`.

### `render_interpolation_frame_begin` — state-adapter

- Callers: `source/game/game_time.c`; `source/main/main.c`
- Effect: native sets the interpolation-active flag. With no snapshot store, an empty body matches disabled interpolation.
- Disposition: no-op while camera/fraction/node queries implement the disabled path.
- Sources: `render_interpolation.c:502-507`.

### `render_interpolation_frame_end` — state-adapter

- Callers: `source/game/game_time.c`; `source/main/main.c`
- Effect: native clears the active flag. Empty is the disabled end.
- Disposition: same as begin.
- Sources: `render_interpolation.c:509-512`.

### `render_interpolation_object_node_matrices` — state-adapter

- Callers: `source/objects/objects.c:1303,1944`
- Effect: `NULL` selects the object datum matrices (`objects.c:1305-1307`). Generated zero pointer is already `NULL`; the adapter keeps that CE fallback explicit.
- Disposition: `NULL`, no interpolated snapshot.
- Sources: `objects.c:1298-1307,1944-1949`; `render_interpolation.c:519-525`.

### `render_interpolation_reset` — state-adapter

- Caller: `source/game/game.c` `game_initialize_for_new_map`
- Effect: native invalidates interpolation records because object indices are reused. No records exist here.
- Disposition: no-op reset of an empty store.
- Sources: `render_interpolation.c:483-498`.

### `render_interpolation_tick` — state-adapter

- Caller: `source/game/game_time.c` `game_time_update`
- Effect: native `calloc`/`realloc` snapshots are not portable to the PS2 no-post-map-malloc budget. Tick does not advance authoritative CE simulation.
- Disposition: no-op. Queries stay on the disabled path.
- Sources: `render_interpolation.c:387-394`.

### `render_particle_systems_enabled` — state-adapter

- Caller: `.data.render_psystems_definition` (`hs_globals_external.c:1420`)
- Effect: CE default `TRUE` (`render.c:152`). The weather renderer also tests this flag and can create/delete the active weather system (`source/effects/weather_particle_systems.c:756-786`). Generated `FALSE` would suppress that lifecycle if the render path is linked.
- Disposition: retail `TRUE`.
- Sources: `render.c:152,161`; `weather_particle_systems.c:756-786`.

### `render_particles_enabled` — state-adapter

- Caller: `.data.render_particles_definition` (`hs_globals_external.c:1418`)
- Effect: CE default `TRUE` (`render.c:151`).
- Disposition: retail `TRUE`.
- Sources: `render.c:151,162`.

### `render_shadows` — state-adapter

- Caller: `.data.render_shadows_definition` (`hs_globals_external.c:1464`)
- Effect: CE default `TRUE` (`render_objects.c:264`).
- Disposition: retail `TRUE`. Shadow GS submission stays parent-owned.
- Sources: `render_objects.c:264`; `hs_globals_external.c:1464`.

### `render_weather_particle_systems_enabled` — state-adapter

- Caller: `.data.render_wsystems_definition` (`hs_globals_external.c:1422`)
- Effect: CE default `TRUE` and `render_effects` writes it (`render.c:153,160`). The weather renderer tests `render_particle_systems_enabled` instead (`weather_particle_systems.c:756`). The global remains script-visible.
- Disposition: retail `TRUE`, kept distinct from the shared gate.
- Sources: `render.c:153,160`; `hs_globals_external.c:1422`; `weather_particle_systems.c:756`.

### `reset_last_player1_profile_index` — implemented

- Caller: `source/saved games/saved_game_files.c:1578` (`delete_enumerated_saved_game_file`)
- Effect: CE stores `NONE` into `event_handler_functions.last_player1_profile_index` (`source/interface/ui_widget_event_handler_functions.c:1771-1775`). The UI owner is excluded; an empty stub leaves a stale index after delete.
- Disposition: store `NONE` in the adapter's last player-1 profile index.
- Sources: `saved_game_files.c:1578`; `ui_widget_event_handler_functions.c:1771-1775`.

### `rint` — implemented

- Callers: `fast_ftol` (`source/cseries/cseries.h:341`); `real_argb_color_to_pixel32` / `real_a_rgb_color_to_pixel32` (`source/bitmaps/bitmaps_inlines.h`)
- Effect: `__builtin_rint` lowers to Newlib `libm_a-s_rint.o` (`halo-local.map`). Not a generated stub. Result follows the EE rounding mode; `_control87` remains a separate pending row.
- Disposition: pinned Newlib libm owner. This file does not wrap `rint`.
- Sources: `cseries.h:335-343`; `build/hcu-ps2-closure/all/halo-local.map` (`libm_a-s_rint.o`).

## Regression

`tests/test_hcu_external_review_batch_6.py::test_batch_6_rooted_symbols_are_dispositioned` loads `docs/hcu-source-backed-review/batches/batch-6.json`, checks every assigned symbol, and requires a real CE or `ps2_m0_batch_6.c` snippet for each approved contract.

## Sources

- `docs/hcu-source-backed-review/hcu-ps2-external-review.json` (pending slice `[192:224]`)
- `submodules/halo-ce-universal/port/ps2/src/ps2_m0_batch_6.c`
- `submodules/halo-ce-universal/source/render/render.c:144-190,238-288,594-654`
- `submodules/halo-ce-universal/source/render/render_objects.c:264,271,281-316`
- `submodules/halo-ce-universal/port/linux/game/render_interpolation.c:387-517,720-728`
- `submodules/halo-ce-universal/port/linux/game/view_fov.c:125-148`
- `submodules/halo-ce-universal/source/main/main.c:1168-1172,2004,3230-3273,3359-3389`
- `submodules/halo-ce-universal/source/effects/particles.c:902,1023-1040`
- `submodules/halo-ce-universal/source/hs/hs_globals_external.c:1416-1422,1464`
- `build/hcu-ps2-closure/all/ps2_platform.c`
