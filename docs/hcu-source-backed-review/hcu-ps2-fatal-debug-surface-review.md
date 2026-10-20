# Fatal-screen, debug-console, and screenshot roots

Status: four halt-only draw calls, the widget path script, the telnet console, TIFF export, and the D3D flip counter are source-proven omissions. `halo_screen_width` and `rasterizer_debug_options` stay pending.

## Halt screen

`halt_and_catch_fire` is the only rooted caller for these symbols (`source/main/main.c:3199-3271`). The generated bodies are empty, or zero for `halo_screen_width` (`build/hcu-ps2-closure/all/ps2_platform.c`).

| Root | What the halt screen does with it | Disposition |
|---|---|---|
| `rasterizer_reset_state` | Clears device state before the error frame (`main.c:3199`). | `excluded-proven`. No simulation reader. |
| `rasterizer_draw_string` | Draws the halt banner (`main.c:3246,3257`). | `excluded-proven`. The on-screen string is diagnostic. |
| `rasterizer_transparent_geometry_draw` | Submits the error-screen transparent pass (`main.c:3269-3270`). | `excluded-proven`. |
| `rasterizer_debug_draw` | Draws debug geometry after that pass (`main.c:3271`). | `excluded-proven`. |
| `halo_screen_width` | Sets the halt viewport `x1` (`main.c:3216`). | Pending. The generated body returns 0. `port/ps2/src/ps2_edge.c:37-39` weakly returns 512, and `src/stream/hcu_main.c` returns the machine width. A zero viewport is not that width. |

Other source files also call `halo_screen_width` and `rasterizer_draw_string`. Those calls are not in the rooted caller sections, so they are not this approval. Re-open the four draw roots if a non-halt caller becomes live.

## Script and console

`ui_widget_debug_show_path` writes `widget_globals.debug_show_path` (`source/interface/ui_widget.c:1860-1865`). The only rooted caller is the HaloScript evaluator (`source/hs/hs.c:15100`). `ui_widget.c` is excluded by `port/ps2/port.json`, so the flag has no linked reader. The empty stub does not change local simulation.

`telnet_console_initialize` opens a listening endpoint only when transport creation succeeds (`source/networking/telnet_console.c:105-131`). `telnet_console_process` returns immediately unless `initialized` is set (`191-194`). `telnet_console_print` sends a line only to a connected client (`170-178`). `telnet_console_dispose` releases that endpoint (`155-165`). The rooted callers are `game_initialize`, `game_dispose`, `terminal_printf` (`source/interface/terminal.c:377`), and `main_loop` (`source/main/main.c:3293,3569`). `terminal_printf` already stored the on-screen line before the telnet call. An uninitialized console therefore adds no game-state write. This is the remote debug console, not the local terminal.

`tiff_export` writes a screenshot file (`source/bitmaps/tiff_file.c:106`). `screenshot_record` reports an error only when the return is non-NULL (`source/main/main.c:1147-1154`). The generated NULL skips that error and writes no file. `source/bitmaps/tiff_file.c` is in the PS2 exclude list. The rooted callers are the screenshot and movie-frame recorders, not the simulation tick.

`d3d_find_flipcount` is stored in `main_globals.d3d_flip_count` (`main.c:2897`). The vblank handler's null branch does not sample flip deltas (`1837-1840`). The only reader of those deltas is the frame-rate debug overlay (`3078-3095`). A null pointer is the handler's existing no-counter path.

## `rasterizer_debug_options`

The `.data.f0_definition` through `.data.f5_definition` sections, and the other `.data.*_definition` sections on this symbol, are HaloScript globals in `source/hs/hs_globals_external.c`. Each stores a pointer to one field, for example `f0_definition` points at `rasterizer_debug_options.f[0]` (`hs_globals_external.c:1260`).

The CE object is not zero. `source/rasterizer/rasterizer.c:602` starts it with `draw_models`, `draw_environment == 2`, and the other retail TRUE flags. The generated object is an uninitialized BSS global. Rooted text readers do not treat that as cosmetic:

- `main_loop` reads `force_all_player_views_to_default_player` while assigning local windows (`main.c:3345`).
- `cheats_network_client_enforce` rewrites water, lens-flare, fog, and environment flags when they differ from the retail defaults (`source/game/cheats.c:138-164`).
- `decal_new_from_collision` scales decal offsets by `zoffset` (`source/effects/decals.c:1335,2095`).
- `flying_camera_update` decrements `freeze_flying_camera` when it is positive (`source/camera/flying_camera.c:76-81`).

A zero object is not the retail initializer. Keep the row pending until the PS2 image provides that initializer.

## Regression

`tests/test_hcu_external_review.py::test_fatal_debug_surface_separates_halt_draws_from_debug_options` locks the halt-only approvals, the telnet initialized guard, the screenshot null check, and the pending width and options rows.
