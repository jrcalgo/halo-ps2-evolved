# C3 sniper zoom render-path audit — 2026-10-26

## Finding

The quiet desktop runtime log contains `HALO_PS2_FAIL c3-render frame-end frame=1455` at emulation time 157.4081s. The corresponding code path permanently sets the parent C3 renderer inactive. This is a strong match for the reported frozen picture while PCSX2 remains open.

The leading source-backed cause is an HCU minimum-FOV check that rejects a valid narrow CE zoom camera. `hcu_views_camera_from_snapshot()` accepts vertical FOV only in `[0.1, 2.8]` radians (`src/stream/hcu_render_views.c:9-10, 42`). CE applies weapon magnification before constructing the window camera, then converts it to vertical FOV with `2*atan(0.75*0.85*tan(native_fov/2))` (`source/main/main.c:1189-1193`; the fallback uses the same formula in `port/ps2/src/ps2_render.c:689-692`). `weapon_get_field_of_view()` accepts zoomed native FOV down to `pi/100` and returns `base_fov / magnification` (`source/items/weapons.c:1261-1275`); the player camera obtains that value through `player_control_get_field_of_view()` (`source/game/player_control.c:491-517`).

For the stock sniper's 10x level and a 70-degree unit camera, the expected CE vertical FOV is about 0.078 radians, below HCU's 0.1-radian lower bound. This numeric value should be confirmed against the exact active weapon definition and the implementor's equip repro. It is sufficient to demonstrate that CE's permitted zoom range extends below the HCU camera validator's range.

When a previously active snapshot view fails this check, `hcu_c3_views_camera()` marks it refused and returns no overlay (`src/stream/hcu_main.c:1958-1965, 2013-2017`). The render loop skips that view (`src/stream/hcu_main.c:2681-2682`). If all views are rejected, BSP frame closure fails because `bsp_render_frame_end()` requires at least one submitted view (`engine/src/render/bsp_render.c:1437-1442`). HCU logs `c3-render frame-end`, sets `s_c3r.active = 0`, and returns (`src/stream/hcu_main.c:2741-2744`). Subsequent ticks stop building frames, leaving the displayed picture frozen.

The observed frame-end marker is not by itself proof that zero views caused the failure: `hcu_render_frame_end()` is the second possible failing call in the same expression. However, after a successful frame-begin, an all-view skip is a direct way to make the BSP's `s_frame_views == 0` guard fail. A targeted repro should log the snapshot FOV, camera conversion result, `views_last`, and frame-end return values at the second zoom transition.

## Downstream paths checked

- Parent depth begin/end reserve 19 QW and fail closed if the per-view viewport is invalid or capacity is insufficient. The sniper FOV changes projection; it does not change the viewport rectangle passed to the clear helper (`engine/src/render/bsp_render.c:902-933`).
- Parent near/far values are replaced only for the FP model camera; world camera near/far come from the snapshot after finite/order checks. `camera_clip_matrix()` and frustum construction consume the accepted camera; they have no FOV-specific assertion after HCU conversion.
- Native CE HUD production still runs through `interface_draw_screen()` at the bitmap frame seam. HUD geometry is viewport-relative and the dispatcher validates target bounds, image dimensions, texture metadata, vertex finiteness/range, and chain capacity. The request owner drops malformed/full batches and keeps valid texture leases until the real renderer fence. These paths can explain missing scope overlays or a dropped bitmap batch, but source inspection found no direct route from a cold scope bitmap miss to the observed `c3-render frame-end` deactivation.
- Zoom-dependent sniper scope assets are present in the Blood Gulch profile metadata, including `sniper_scope_mask2`, `sniper_scope_mask_sm`, `hud_reticles_scope`, `sniper_scope_crosshairs2`, and the small crosshair variant. The native bitmap path has a 256-pixel per-image dimension limit and can reject larger images; such a request failure is handled as a batch refusal, not a wait. A separate texture/lease issue remains possible, but should be investigated only if the FOV acceptance test passes.

## Bounded verification

At the implementor's private equip repro, capture native weapon FOV, CE vertical FOV, `hcu_views_camera_from_snapshot()` result, number of submitted BSP views, and both return values from the frame-end expression across unzoomed, first zoom, and second zoom states. A host fixture should feed the converted 70-degree/10x value (~0.078 radians) into `hcu_views_camera_from_snapshot()` and assert it remains usable; the runtime check should verify one view is submitted and no `c3-render frame-end` failure occurs. Keep the scope bitmap request and texture-lease counters in the same run to rule out a separate cold asset failure.

## Runtime constraints

The live user desktop guest PID 2193789 and its window were not touched. No build, guest launch, input, or production source edit was performed for this audit.
