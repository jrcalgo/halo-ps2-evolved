# C3 first-person models: retained-palette check and depth contract (R2) — 2026-10-26

## Summary

An independent parse of retained runtime snapshots contradicts R1's key inference that the exported weapon/hands matrices are world-space. In all eight retained canonical snapshots (1, 2, 3, and 4 view runs, baseline and optimized), each published weapon root is approximately identity-oriented with camera-local translation around `(0.176, -0.047, -0.036)` and scale 1; hands use a distinct local root near the origin. The camera in the same view is at `(105.026, -162.209, 0.641)` with a changing, non-identity forward vector. Therefore the actual CE-to-parent snapshot palettes are camera-local for these captures, and `hcu_render_first_person_world` is the expected one-time camera-to-world composition. Do not implement R1's suggested “skip parent transform” based on the raw animation graph call alone.

The stronger implementation candidate is the missing first-person render policy: the current parent submits both models after world objects, but with ordinary world camera near/far, world frustum/culling rules and model material Z test/write. This makes the models subject to near-plane clipping and wall depth. Halo 64 instead starts an explicit viewmodel phase with a 0.01171875 near plane, 16-unit far plane, the view rectangle, and a depth clear before its viewmodel draw. Adopt an isolated, per-view FP policy while keeping the world color and each next viewport/HUD state intact.

## Runtime palette evidence

The parser in ignored `build/c3/first-person-fix/r2/parse.c` includes the current snapshot header and reads the canonical snapshot as the fixed-size host structure. It asserts through output that `sizeof(halo_ps2_frame_snapshot) == 82912`, matching the file. The parser output is derived from values, not included model asset bytes.

`runs/01-baseline-v1/snapshot-canonical.bin`:

- Header: version 5; one active view; camera position `(105.0261, -162.2092, 0.6408)`, forward `(-0.8977, 0.4407, 0)`, up `(0, 0, 1)`, vertical FOV `0.5779`, near `0.0625`, far `1024`.
- Weapon range `[126, 130)`, resource slot 28; four nodes. Root: scale `1.0`, forward `(1.0000, 0.0028, 0.0004)`, left `(-0.0028, 1.0000, 0.0044)`, up `(-0.0004, -0.0044, 1.0000)`, position `(0.1761, -0.0469, -0.0359)`.
- Hands range `[130, 167)`, resource slot 29; 37 nodes. Root scale `1.0`, position `(-0.0187, 0.0146, -0.0815)`.
- Weapon root forward differs from camera forward by roughly 90 degrees and the translation is sub-meter relative to the view origin, not the camera's world location. This is consistent with a local pose awaiting the parent camera transform.

Across runs 01–08, the view 0 weapon root stayed scale 1, identity-like, and around `(0.176, -0.047, -0.036)` as camera heading varied. Ranges and hands count stayed distinct. Runs 02–04 and 06–08 contain additional views and all have separate per-view FP palette ranges. This is direct runtime snapshot evidence, stronger than reasoning from `animation_graph_node_matrices_from_orientations` alone. Scope is limited to these retained Blood Gulch run snapshots; it does not prove all CE modes/weapons.

The active JSON identifies the baseline artifact and hashes it; snapshot-canonical is normalized only in sequence/frame fields (the raw file begins with sequence/frame `0x24f`, canonical has zero there). No assets were read into this report.

## Why the apparent source mismatch

`first_person_weapon_build_node_matrices` calls `animation_graph_node_matrices_from_orientations` with `render.camera.position/forward/up`. That helper composes a camera-rooted graph. However, `first_person_weapon_copy_render_models` then copies graph node matrices by remap-table lookup (`model_remap_node_matrices_to_match_animation_graph`, assignment only) into the snapshot palette. The runtime values say that the palette reaching the parent is local even though the earlier function call looks world-rooted. This deserves a narrower source trace of camera/render interpolation and the actual remap table path before changing transforms. The no-op PS2 `render_interpolation_first_person` does not explain the snapshot values by itself.

Parent selection keeps independent weapon and hands ranges. In `hcu_render_objects.c`, `pose_fn` applies `hcu_render_first_person_world` per palette node under `CAMERA_LOCAL`; root preparation also computes that transform once for culling/model metadata. This is internally consistent with the captured camera-local values. The active code should retain this transform until a contrasting runtime capture proves otherwise.

## Reference contract from Halo 64

In `submodules/halo-64/port/n64/src/n64_render.c`, `n64_render_first_person_begin` flushes world draws, finishes world particles, sets a first-person perspective using the current FOV/aspect with near `0.01171875 * WORLD_SCALE` and far `16 * WORLD_SCALE`, attaches the same viewport, and clears depth before the viewmodel phase. `draw_particles(first_person)` similarly uses those near/far values and suppresses world fog. `n64_first_person_model_draw` lazily opens this phase and then submits the CE-selected node matrices. The renderer also skips its ordinary object distance/LOD cull while `renderer.first_person` is set.

Halo 64's depth clear is the relevant wall policy: first-person geometry is layered over the already-rendered world in its viewport. It preserves the world color; the first-person models are not depth-occluded by a wall in the same view. That matches the current task interpretation that the viewmodel should remain visible in front of world geometry. Its per-view viewport rectangle keeps split views spatially isolated.

## Parent PS2 behavior and proposed contract

The PS2 parent currently draws world objects, then the two FP models, using the ordinary `render_ctx_t` from the world view. `obj_render` uses `rc->cam` and `rc->frustum` for distance, frustum and projected-size checks; `draw_model` installs the ordinary model state with `GS_TEST(... Z test GEQUAL ...)` and `GS_ZBUF(..., ZMSK=0)` (depth writes enabled). `hcu_render_objects.c` sets FP model radius from the model metadata and uses the shared `obj_render_pass` path. Thus:

1. A viewmodel close to the eye can hit the world's `near_z` during model triangle clipping (`clip_polygon` uses `rc->cam->near_z`). The retained capture uses world near `0.0625`; Halo 64's FP reference is `0.01171875` in Halo world units. The C3 view FOV remains the view's FOV; do not substitute a gameplay or arbitrary weapon FOV without evidence.
2. A wall whose reverse-Z depth is nearer than the weapon can reject weapon fragments under the ordinary GEQUAL world Z test. If the intended policy is a visible foreground viewmodel, the FP phase needs depth isolation: clear depth within the active view rectangle before FP, or draw with depth test disabled and Z writes disabled. A clear is closer to Halo 64. Merely changing near/far without isolating depth changes the meaning of the existing Z values and can produce inconsistent comparisons.
3. World frustum, distance, and tiny projected-size tests are inappropriate rejection criteria for a camera-attached viewmodel. Keep resource/model validity and triangle clipping to the FP projection, but bypass world object culling/LOD for the FP submission. Do not use a fixed root offset to compensate.
4. Keep the submitted node matrices and correct model bounds as CE authored. The camera-local pose and independent hand/gun palettes are the source of truth; the FP pass changes projection/depth/culling state, not asset transforms.

A minimal implementation seam is around the existing FP loop in `hcu_render_objects.c`/render context, leaving the CE producer and ordinary world pass intact: create a temporary first-person camera/context with the same camera pose, view FOV, aspect, viewport/scissor and world axes, and FP near/far; bypass world object culling for the two FP models; emit a depth clear scoped to that view before the loop (using the view's scissor); then draw FP geometry with world-compatible Z semantics and Z writes disabled, or with an explicitly verified always-pass Z test and writes disabled. Restore the prior GS depth/projection state before HUD/next view. If a scoped clear cannot be made reliable on this GS path, use test-disabled/Z-write-disabled state for the FP packet; world color has already been drawn and is not altered. Keep GIF/DMA chain allocation through existing fixed-capacity APIs and fail closed on capacity exhaustion; add no heap allocation or new framebuffer.

Be careful that `bsp_render.c` owns the active per-view viewport/scissor setup. The FP change must preserve that scissor, honor 1–4 active view rectangles, and must not clear neighboring rectangles. State changes are emitted into the same chain in order; explicitly re-establish normal depth state before the next view/HUD path because GS state is global.

## Validation/capture plan for implementation owner

Use screenshot plus structured pose/depth diagnostics; test all modes with no asset-coordinate tuning:

- One view: stock sidearm and a second stock weapon with CE first-person model/graph, arms visible; yaw through ±90°, pitch up/down, idle/fire/reload/sway. Capture the CE-selected resource IDs, palette ranges, scales, root and distal node values, camera pose/FOV/near/far, per-model projected bounds, and screenshot. Root/palette should not change contract or double-transform when camera moves.
- Wall set: stand at increasing closeness to a flat wall, corner, and narrow doorway; face parallel to and into the surface; fire and turn. The weapon/arms should stay fully rendered in their projected silhouette while the world wall geometry remains visually unchanged. Ensure no geometry disappears solely at world near plane.
- Two, three, and four views: use different headings/pitches per view. Check each view's hands/gun only draw in its own rectangle, that clearing FP depth leaves its world pixels intact, that adjacent views remain untouched, and that the next view/HUD has ordinary depth state.
- Stress state: long arm/weapon poses, model vertices nearest the camera, weapon switch/death/respawn, zoom/scope path (CE visibility selection), and missing model fail-closed behavior. Compare captured FP palette node counts with model counts and ensure each palette range remains disjoint.

Acceptance: transform/scale/bounds follow CE across heading and animation with no hardcoded pose changes; the frontmost FP silhouette is not truncated by world wall depth or the ordinary near plane; the world pass and other view rectangles keep their color/depth; no state leakage across view/HUD boundaries.

## Evidence boundary

This report independently validates actual published palette values from retained runtime snapshots and establishes Halo 64's explicit FP pass settings from source. It does not prove a live wall-clipping screenshot, the exact root of every visual size issue, or the correct PS2 depth-state patch. The near-plane/depth/culling handoff above is implementer guidance to capture and verify in the runtime. No emulator, EE build, or UI interaction was run here.
