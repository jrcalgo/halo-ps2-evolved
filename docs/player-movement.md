# M12 player movement

M12 is complete for one local player against the Blood Gulch structure. The pill does not collide with objects. A physical console has not run it.

## Source audit

`submodules/halo-64/source/game/player_control.c` is the original control surface: aiming, zoom, weapon desire, camera, and button inhibition. It calls into units, objects, and the player datum. `players.c` owns spawn and the player record. Neither file is in the frozen M07 compile closure. Porting them requires the object and tag graph those files include. That graph is not on the EE.

`halo-ps2` has no player collider. `bsp_find_cluster` reports the cluster containing a point and returns `-1` for solid space and for points outside the map. Converted BSP planes are the collision query that exists today. The rendered batches are not a separate collision mesh.

## What this step implements

`src/game/move.c` steps one biped from `move_cmd` and a solid predicate. There is no heap allocation and no render input. The numbers are Halo CE, read from the user's Blood Gulch map and from `halo-64`:

- `matg` player information: run forward 2.25, backward 2.0, sideways 2.0, acceleration 0.32; sneak forward 0.9, backward 0.65, sideways 0.6, acceleration 0.16; airborne acceleration 0.035. Units are per second, then divided by `TICKS_PER_SECOND` (30), matching `bipeds.c` around the player-physics blend.
- `characters\cyborg_mp`: jump velocity 0.07 per tick, standing camera 0.62, crouching camera 0.35, crouch transition 0.2, collision height 0.70 standing and 0.50 crouching, radius 0.2.
- `physics.c` `global_gravity` 0.0035651792 per tick. Grounded motion also subtracts the source floor bias of 1/128 along the ground normal. Crouch blends sneak speeds against run speeds the way that blend is written.

`src/game/collide.c` is the structure segment test (`collision_bsp_test_vector`). A downward segment from two units above each of the first twelve player-starts hits about one millimetre under the start.

`src/game/pill.c` is `collision_move_pill` for the structure BSP: the sphere gather, the expanded spheres, cylinders and prisms, and the clip loop. The pill is the one `biped_get_physics_pill` builds for a player cyborg. The base is the feet plus the 0.2 radius, and the standing height is 0.70 minus twice that radius. Objects are not in the query. `mover_tick_map` feeds that sweep. The render schedule argument is not read.

On the first Blood Gulch start the body settles 1.2 mm under the tag position, grounded. A jump leaves with vertical speed 0.07 minus gravity and lands on the same surface. Six ticks of crouch reach eye 0.35 and collision height 0.50. Walking along the start's facing stays grounded. A point taken outside the BSP restores the last safe feet position. Two fast steps toward vertical surfaces stop at or before those surfaces. Three render schedules produce the same positions.

The scratch block is 47,644 bytes, inside the 393,216-byte frame scratch. It is passed in by the caller. The tick does not call malloc. A walking tick visits at most 62 BSP nodes and 16 features and takes about 4 microseconds on this host. A step that fills a 256-feature list is halved until the lists fit; if the finer sweep would travel farther than the contact the coarse lists already found, that contact is kept. The collision tables are 666,372 bytes in the converted `COLL` pack from `tools/convert_collision.py`. They fit in the spare of the 6,291,456-byte current BSP region beside the 611,856-byte render BSP. The EE play build loads that pack once and reuses a 47,644-byte scratch buffer. The tick does not allocate.

The eye is the feet plus the standing camera height, aimed along the player-start yaw. After the settle on the first Blood Gulch start that pose is `98.4934 -157.6390 2.3235`, yaw `76.1049` degrees, pitch `0`. A still frame of that pose is run `world-portal-recompiler-8bf691f4cfac42809cad3e9951a4d02d`. The moving view is run `world-portal-recompiler-6b65eea7259b441ca0ce65ae8707e16c`: 15 eye keys over 7 seconds, 241 frames, 0 dropped. The eye walks into the structure, drops to the ground, and turns. The host geometry reference of the same pose is `build/reference/bloodgulch-player-eye.png`. The EE steps this pill in the play build. Run `world-recompiler-6faf9afd611e4bf8aaccc40727fa45fd` logged `[play] ready feet 98.49 -157.64 1.70 yaw 76.1` and drew a grounded walk at 30 fps, frame time 33.4 ms, no drops, heap break 16,222 KB of 27,136 KB committed and 32,768 KB total. First-person arms draw with the view. Weapon simulation is M13.

The pad uses `fix_dead_zone` with range 9000. Default look sensitivity is 3: yaw 120 degrees per second, pitch 60, invert off. On the keyboard, W S walk, A D strafe, the arrow keys look, G jumps, and Control crouches.

Tolerances, measured from the source before the host comparison: ground contact within 8 mm, from the 1/128 floor bias. Jump speed within `1e-5` of `0.07` minus gravity. Jump height within one jump-tick of `v^2 / (2g)`. A ceiling may be penetrated by at most 0.05. A fast step must stop at or before the wall plus the 0.2 radius. A slope must gain at least 0.02 over 30 ticks and stay grounded for 20 of them.

`python3 -m unittest discover -s tests -p test_move.py -v` checks the velocity formulas against a point probe. `test_collide.py` checks the segment test. `test_player.py` checks the pill on Blood Gulch, the scratch size, and that `src/game` does not allocate.

## Limits

Object collision, weapons, and a second player are not in this milestone. M13 has not started. M23 stays blocked: no physical console is available.
