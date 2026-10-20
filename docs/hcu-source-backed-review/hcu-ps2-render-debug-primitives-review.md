# M0 source review: CE debug drawing primitives

## Disposition

Nine rooted drawing helpers are `excluded-proven` as debug-only visual/output services: `render_debug_line`, `render_debug_matrix`, `render_debug_pill`, `render_debug_point`, `render_debug_sphere`, `render_debug_string`, `render_debug_string_at_point`, `render_debug_vector`, and `render_debug_vectors`. The HCU platform placeholders for these do not own gameplay state. The PS2 renderer may later implement equivalent overlays, but M0 local simulation does not depend on them.

## Call-site review

- `render_debug_line`: object diagnostics in `source/objects/objects.c:3236-3254` and collision-BSP edge rendering in `source/physics/collision_bsp.c:540-563`. The collision test results and object state are computed before the draw call; it only displays segment endpoints.
- `render_debug_matrix` and `render_debug_vector`: object debug rendering in `objects.c:3059-3090`; matrix, position, and velocity are read to draw labels/axes, not written back.
- `render_debug_pill`: biped physics/autoaim overlays in `source/units/bipeds.c:1410-1431`; pill geometry is queried and submitted for rendering, not used as the collision authority.
- `render_debug_point`: point-physics debug helper in `source/physics/point_physics.c:280-292` (called only under `debug_point_physics` after the physics result is already determined), plus unit debug overlays in `source/units/units.c:5080-5090`.
- `render_debug_sphere`: optional material-effect failure visualization (`source/effects/material_effects.c:143,196`), physics/object debug overlays (`source/physics/physics.c:502-539`, `source/objects/objects.c:3114,3193`), biped overlays, collision-debug visuals, and sound-manager diagnostics (`source/sound/sound_manager.c:1680-1768`). These are submitted shapes only; effect creation, collision responses, and sound selection are decided independently.
- `render_debug_string` and `render_debug_string_at_point`: sound/environment, cache/device/object/unit diagnostics (`scenario.c:1361`, `sound_dsound_xbox.c:1559`, `devices.c:682`, `objects.c:3073-3088`, `sound_manager.c:1696,1758`, `units.c:5114`). Their inputs are formatted for display; the helper does not write state back.
- `render_debug_vectors`: only `render_debug_physics` (`physics.c:487-539`) emits mass-point axes and center-of-mass orientation, reading existing physics transforms.

All identified paths are observational after or alongside the normal simulation calculations. They may cost rendering time or show diagnostics in a debug build, but they do not advance camera, object, damage, collision, audio selection, or effects state. This review does not approve omission of the separate render lifecycle, interpolation, viewport/frustum, particle/HUD, or first-person state interfaces.

## Regression guard

The test checks exact rooted-caller source attribution, the debug-mode guards around representative calls, and the point-physics ordering (collision result and position update precede its optional drawing). If a future source revision makes one of these helpers mutate game state, the test and its exclusion must be revisited.
