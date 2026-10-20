# M0 source review: render/cache diagnostic globals

## Disposition

Sixteen rooted globals are `excluded-proven` as optional diagnostic controls, not simulation or resource-ownership state: `debug_bink`, `debug_bsp`, `debug_camera`, `debug_inactive_objects`, `debug_input`, `debug_leaf_index`, `debug_leaf_portal_index`, `debug_leaf_portals`, `debug_objects`, `debug_permanent_decals`, `debug_player`, `debug_sound_cache`, `debug_sound_environment`, `debug_sprites`, `debug_structure`, and `debug_texture_cache`.

## Source findings

- `debug_bink` only gates Bink realtime/frame/audio/read-time diagnostics in `source/bink/bink_playback.c:714-760`. It does not select or advance a frame; Bink itself remains outside the current PS2 M1 profile.
- `debug_bsp` gates a diagnostic BSP traversal/text dump in `source/render/render_debug.c:1401-1485`, including an optional `d:\debug_bsp.txt` output. BSP/camera values are read for the dump; collision, rendering visibility, and map ownership are not assigned there.
- `debug_camera` gates a read-only camera position/location and collision diagnostic in `render_debug.c:1221-1320`. It formats and emits the query values without feeding them back into observer state.
- `debug_player` reads local player/biped/vehicle state and emits diagnostic strings (`render_debug.c:1323-1360`).
- `debug_structure` iterates collision-BSP edges and submits diagnostic lines (`render_debug.c:1367-1400`). `debug_permanent_decals` iterates runtime decals for diagnostic drawing (`render_debug.c:1523-1578`); neither branch creates, deletes, or updates the source data.
- `debug_input` formats raw pad state for on-screen output (`render_debug.c:1488-1520`). The normal input poll and abstraction paths are separate.
- `debug_leaf_index`, `debug_leaf_portal_index`, and `debug_leaf_portals` add portal visualization in `source/structures/structure_render.c:665-710`; the branches do not write the leaf/portal map or alter the renderer's visibility decision.
- `debug_objects` invokes `object_type_render_debug` after the normal object-model submission (`source/render/render_objects.c:635-637`). Object update, transform, activation, and collision run in their separate simulation routines. `debug_inactive_objects` only adds a label/point for an object already marked inactive (`render_objects.c:589-618`).
- `debug_sound_cache` reads the cache's page-usage bitmap and draws a diagnostic grid (`source/cache/xbox_sound_cache.c:789-850`); it does not cause cache allocation/eviction or choose sound.
- `debug_sound_environment` prints the already selected environment's name before the ordinary environment definition is assigned (`source/scenario/scenario.c:1354-1373`). It is not part of environment selection.
- `debug_sprites` prints coverage/count statistics (`source/render/render_sprite.c:300-315`). The separate sprite size/count limit and count updates occur independently of the diagnostic branch (`render_sprite.c:543-565`).
- `debug_texture_cache` gates only the console warning in the bitmap lookup path (`source/cache/xbox_texture_cache.c:1048-1064`); the cache read-promotion call is outside that conditional, so turning off the message does not alter loading schedule.

These controls may enable developer overlays or log files on CE, but the PS2 product path does not include those diagnostics. The semantic exclusion is narrow: do not use these results as justification to omit camera, collision, sound-selection, cache scheduling, or normal sprite/object rendering state.

## Regression guard

The focused test binds every ledger row to its exact source and asserts that the critical cache-promotion and sound-environment assignments remain outside their debug-only branches. It also checks that the toggles stay classified as optional debug exclusions; if a future source revision moves a state mutation into one of these branches, the test and disposition must change.
