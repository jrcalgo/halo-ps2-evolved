# Third-person vehicle cameras and the death camera (2026-11-07)

## Summary

Before this change the PS2 port stayed in the first-person camera in every vehicle, and the death view froze or showed
"RESPAWNING". The retail camera data was always present in the map. What was missing was the code that runs it.

* Entering a vehicle now switches to the seat's third-person chase camera, as on retail Xbox (driver and gunner seats set
  `third_person_camera`; passengers set `third_person_on_enter`).
* Dying switches to the dead camera, which orbits the body for about 3 s and then respawns into first person.
* On foot, first person is unchanged.

## Root cause

The PS2 production loop (`source/main/main.c`, realtime scheduler and fixed-tick path) never called `director_update` or
`observer_update`. Those run once per frame in retail `main_loop`. Without them the director never leaves its default
first-person camera, so the following camera (vehicle chase) and the dead camera never ran. Two PS2 publication details
also hid the result:

1. `port/ps2/src/ps2_render.c` forced the player's view inactive when the unit was gone (`unit_index == NONE`). The
   parent then replayed the last good camera and drew "RESPAWNING". A dead player in the dead camera now keeps an active
   view with the HUD flags cleared.
2. The camera fallback (`ps2_c3_unit_camera`) was used whenever the observer was unset. It is now also used when the
   director perspective is first person, so on-foot play is unchanged and any other perspective reads the observer.

The parent already hides the player's own unit only when `HALO_PS2_FRAME_VIEW_FIRST_PERSON_CAMERA` is set
(`src/stream/hcu_render_objects.c:283`). The chase camera therefore shows the player sitting in the vehicle.

`source/camera/director.c` also gained one port guard. `director_choose_camera_game` rotates the camera mode when a
button is pressed (the "black button"). On PS2 that button is the flashlight, so the rotation is compiled out under
`HALO_PS2`.

## Changes

| File (submodule `halo-ce-universal`) | Change |
|---|---|
| `source/main/main.c` | `director_update` and `observer_update` before `main_game_render` in both publish paths |
| `source/camera/director.c` | `#ifndef HALO_PS2` around the camera-mode rotation |
| `port/ps2/src/ps2_render.c` | dead view stays active; fallback camera only for first person |
| `tools/dump_vehicle_cameras.py` (parent) | dumps the retail camera data cited below |

## Sources and comparison

### 1. Retail Halo: Combat Evolved (Xbox ISO, `~/Documents/Halo/Halo - Combat Evolved.xiso.iso`)

Dumped with `python3 -I tools/dump_vehicle_cameras.py bloodgulch` from the decompressed map. Vehicle cameras are data
(`unit_seat` flags plus `trak` camera tracks), not code.

| Vehicle | Seat | Flags | Camera tracks |
|---|---|---|---|
| Warthog | driver | `driver`, `third_person_camera` | `warthog_driver_loose`, `warthog_driver_tight` |
| Warthog | passenger | `allows_weapons`, `third_person_on_enter` (marker `camera rider`) | `warthog_driver_loose` |
| Warthog | gunner | `gunner`, `third_person_camera`, `first_person_camera_slaved` (marker `camera gunner`) | `warthog_driver_loose` |
| Scorpion | driver | `driver`, `gunner`, `third_person_camera` | `scorpion_driver_loose`, `warthog_driver_tight` |
| Ghost | driver | `driver`, `gunner`, `third_person_camera` (marker `driver camera`) | `warthog_driver_loose` |

All vehicles use a 70 degree camera FOV. The biped's own camera uses the `biped_small_tight` track.

### 2. halo-ce-universal (CE source reconstruction)

* `source/camera/director.c`: `director_get_perspective` (l.300), `director_desired_perspective` (l.328),
  `director_choose_game_perspective` (l.614), `director_choose_camera_game` (l.683).
* `source/camera/following_camera.c`: `following_camera_update` (l.191) follows the seat's tracks;
  `camera_track_splut` (l.365) interpolates the control points.
* `source/camera/dead_camera.c`: `dead_camera_new` (l.95), `dead_camera_update` (l.132) orbits the dead unit.
  `director_get_perspective` reports it as `_director_perspective_neutral`.

### 3. Halo 64 (`submodules/halo-64`, v0.6.6, commit `b629d0a`)

* `source/main/main.c:3443` calls `director_update(halt_time_scale * seconds_elapsed)` every frame, the same call this
  port was missing.
* `port/n64/game/n64_render_game.c:426-446`: the viewer's own unit is hidden only when not third person, matching the PS2
  `FIRST_PERSON_CAMERA` flag.
* `port/n64/HISTORY.md:898-899`: the vehicle and death cameras cast 4 bisection rays instead of 10.
* `source/camera/director.c:504`: Halo 64 documents a `BUG (original)` in the director. This port does not depend on that
  path.

Comparison: Halo 64 and this port both drive the stock CE director and following/dead cameras from the main loop. Halo 64
runs them every frame. The PS2 port now does the same. The retail Xbox data is read unchanged. Halo 64 cheapens the
camera collision rays, and this port has not done that yet.

## Verification (headless PCSX2, Blood Gulch, 1 player)

| Case | Result |
|---|---|
| Ghost driver | chase camera behind and above, FPS about 30 |
| Warthog driver | chase camera behind and above, camera follows and yaws while driving, dust trail visible, FPS about 30 |
| Death | after `unit_kill` at a fixed tick (temporary test hook, since removed): elevated dead camera on the body, no "RESPAWNING"; after about 3 s respawn in first person with the HUD back |
| On foot | unchanged first person |
| Scorpion | not driven in a test. The seat has the same `third_person_camera` flag and its own track, so it takes the same path |
| Warthog passenger and gunner | not driven in a test. They take the same path, with the `camera rider` and `camera gunner` markers |

Host tests: the views, snapshot and camera fallback tests pass. `test_c3_snapshot_publish.py::test_publisher_fills_bounded_fx_requests_with_counted_drops`
fails because `ps2_c3_fx_run_streams` is not in `ps2_render.c` at HEAD. That is unrelated to this change.
