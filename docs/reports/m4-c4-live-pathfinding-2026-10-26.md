# M4 C4 item 3: live-unit pathfinding host evidence (revision 3, 2026-10-26)

## Verdict

Every live-unit behaviour in C4 item 3 is now driven by the real CE translation units. Smoothing, obstacle avoidance (including the blocked branch), the actor path refresh and step advance, the mid-path breakable destruction, and the point-to-surface selector including its ground search all run from `submodules/halo-ce-universal/source`. Four pieces of source are copied byte-for-byte by name into generated files because the HCU tree cannot compile them whole on this host (see Build). Every other gap is a data-only stub or an abort-on-call stub. The one row that stays BLOCKED is native 64-bit parity: the CE headers carry ILP32 size asserts. The ILP32 build repeats byte-identically at -O0 and -O1.

Item 4 is still a recorded finding: no stock Prisoner breakable carries a walkable bit, so destroying a stock breakable cannot change stock link availability.

## Resolved open items

### 1. Ring orientation for the 12 retail surfaces (`collision_bsp.c:823`)

Finding, stated precisely.

- CE's 2D point test accepts a point only if, for every ring edge, `cross(p0 - q, p1 - q) <= 0` (`collision_bsp.c:823-881`, `sign` TRUE as the selector calls it at `units/bipeds.c:1585`).
- For surfaces 0, 1, 5, 9, 11, 94, 100, 500, 2838, 2839, 401 and 2834 every edge gives a positive cross product (see the table below). Their xy signed areas are positive, so their stored rings run counter-clockwise in xy.
- Surfaces 457, 902, 960 and 2835 are accepted. 902 is clockwise (xy area -0.11). 457 and 2835 are vertical (zero xy area, zero cross products).
- The payload is a byte-for-byte copy of the decompressed BSP's surface, edge, vertex and tree records (`tests/test_c4_live_pathfinding_real.py: raw_full_payload`), and the ring walk uses CE's own `reverse = surface_indices[1] == s` rule. So the orientation is a property of the stock data as stored, not a payload conversion or a harness sign error.
- The plane designator sign bit does not explain it: 0, 1, 5 and 9 are not negated and fail, while 2838 and 2839 are negated and fail.
- Consequence: the 2D test cannot accept these 12 probes, so the selector falls back to the ground search (`bipeds.c:1499`, `collision_bsp_test_vector`, verbatim from `collision_bsp.c:1220`). That search returns the same surface for each of them, so the selector still returns the probed surface.

Per-edge evidence (cross-product sign of the probe against each ring edge; `+` means CE rejects):

| Surface | Edges | Ring area (xy) | Cross signs | CE 2D test | Ground branch | Selected |
|---|---|---|---|---|---|---|
| 0 | 4 | +34.56 | ++++ | reject | 0 | 0 |
| 1 | 4 | +29.52 | ++++ | reject | 1 | 1 |
| 5 | 4 | +25.99 | ++++ | reject | 5 | 5 |
| 9 | 4 | +16.96 | ++++ | reject | 9 | 9 |
| 11 | 5 | +17.58 | +++++ | reject | 11 | 11 |
| 94 | 4 | +4.76 | ++++ | reject | 94 | 94 |
| 100 | 4 | +3.16 | ++++ | reject | 100 | 100 |
| 500 | 3 | +1.20 | +++ | reject | 500 | 500 |
| 2838 | 3 | +0.11 | +++ | reject | 2838 | 2838 |
| 2839 | 3 | +0.10 | +++ | reject | 2839 | 2839 |
| 902 | 3 | -0.11 | --- | accept | 2838 | 902 (last-surface branch) |
| 457 | 6 | 0 | all zero | accept (trivial) | 1428 | 457 (last-surface branch) |

Whether this is a defect in CE's 2D test for upward rings, or whether the selector is meant to reach the ground search for them, is not decided here. Both readings give the same selection result on stock data. The finding for the HCU lane: the ground search is the path that actually selects these surfaces on stock Prisoner.

Walls: surfaces 401 and 2834 are vertical (`normal_z = 0`). A downward ground ray cannot hit a vertical surface, so the search returns the floor below (surface 1373). That is correct CE behaviour, and the test asserts it.

Full retail sweep (28 surfaces, `tests/test_c4_live_pathfinding_real.py`): 26 select themselves; 2 walls return the floor below.

### 2. Blocked avoidance branch (`path_obstacle_avoidance.c:1082`)

Reached. The fixture places eight scenery discs of radius 3 on a ring of radius 3 around the start (5,15). The real A* still finds the route (`path_state_find` returns TRUE). The real `path_avoid_obstacles` (`path_obstacle_avoidance.c:907`) then returns FALSE. The only assignment of FALSE in that function is `:1082`, and the function returns `result` at `:1087`, so this is the branch. The full build (`path_state_build_path`) reports no path. Scenario: `avoidance.blocked`.

### 3. Mid-path breakable destruction with the real actor

Reached and passing. The actor follows the real `actor_destination_update` (`actor_moving.c:2109`), which calls the real `actor_path_refresh` on every tick unless the actor is at its destination (`actor_moving.c:2003-2012`: `build_path` stays TRUE while not at destination). At tick 20 the unit is in cell 6 at x=15, mid-path. The gate's breakable bit is cleared (`physics/breakable_surfaces.c:330` analogue). On the very next real refresh, with no driver replan, the new path does not cross the gate, the unit never enters it, and it arrives at tick 88. Scenario: `midpath.breakable`.

This also corrects the revision-2 recovery row: the real code already replans every tick, so the driver's explicit stall replan in `actor.recovery` is a driver detector around the real refresh, not the mechanism the real code needs.

## Table: behaviour -> test -> PASS/PARTIAL/BLOCKED -> evidence

| Behaviour | Test (`tests/test_c4_live_pathfinding_real.py` unless noted) | Result | Evidence |
|---|---|---|---|
| (a) Selection, support-surface branch | `selection.support_surface` (driver) | PASS | `units/bipeds.c:1537` run unchanged; selects 7, projects to (25,15). |
| (a) Selection, throttle and flying | `selection.attempt_throttled`, `selection.flying` | PASS | `bipeds.c:1544-1549` (flying), `:1554` (throttle). |
| (a) Selection, last-surface branch, synthetic grid | not asserted | PARTIAL | The synthetic rings are counter-clockwise in xy, so the 2D test rejects them as for the 12 retail surfaces, and the synthetic grid has no BSP3D trees for the ground search. Retail covers the branch. |
| (a) Selection, ground search, retail Prisoner | `test_retail_prisoner_selection_through_real_ground_search` (8 probes), `test_retail_wall_surfaces_are_not_ground` (2 walls) | PASS | Real `biped_find_ground_surface` (`bipeds.c:1475`) and `collision_bsp_test_vector` (`collision_bsp.c:1220`) on the real BSP3D/BSP2D trees. Walls 401, 2834 return floor 1373 by design. |
| (a) Selection, last-surface branch, retail | same as above | PASS | 457, 902, 960, 2835 and others accepted by `collision_bsp.c:823`. |
| (b) Path construction (A*) | `smoothing.intact` | PASS | `ai/path.c:1479` traverse, `:837` build. |
| (b) Smoothing: invariants, no crossing a blocked edge, goal preserved, deterministic | `smoothing.intact`, `smoothing.gate_blocked`, `smoothing.gate_destroyed`, `smoothing.deterministic` | PASS | `ai/path_smoothing.c:527` and `structure_test_pill2d` (`ai/path_structure_bsp.c:596`) unchanged. 41 samples per segment on walkable unbroken ground. |
| (c) Obstacle avoidance, disc steers around dynamic obstacle | `disc.steer` | PASS | `ai/path_obstacle_avoidance.c:907`, collection `:975`. Disc (8,15) r=2: min distance 2.504. |
| (c) Avoidance reports blocked when no path | `avoidance.blocked` | PASS | Branch `path_obstacle_avoidance.c:1082` (sole FALSE assignment; returned at `:1087`), reached with eight discs. |
| (d) Movement progress over the path | `actor.progress` | PASS | Real `actor_destination_update` (`actor_moving.c:2109`, step advance `:2122-2190`) and real `actor_path_refresh` (`:1849`). 81 ticks, valid ground every tick. The integrator (movement model) is a stated driver stub. |
| (e) Recovery: stall, replan, arrive | `actor.recovery` | PASS (driver detector) | The driver detects 30 unmoved ticks and calls the real refresh; arrives at tick 118 without crossing the gate. The real code already replans every tick (see item 3). |
| (f) Breakable destroyed mid-path, real actor replan | `midpath.breakable` | PASS | Destruction at tick 20 (x=15). Path crosses the gate before, does not after; the first real refresh after the break already avoids it; unit never enters the gate cell; arrives tick 88. |
| (f) Breakable destroyed before the unit moves | `breakable.smoothing_avoids_destroyed` | PASS | Real smoothing and `surface_is_broken` (`ai/path.c:632`, neighbour check `:1568-1570`). |
| (f) Retail Prisoner: all 8 stock breakables destroyed | `test_retail_prisoner_breakables_destroyed_route_invariant` (seam file) | PASS (finding) | Route unchanged: stock breakables have no walkable bit (item 4). |
| Native 64-bit vs ILP32 parity | `test_repeat_builds_at_two_optimisation_levels_agree` | BLOCKED (native); PASS (repeat) | Native compile fails at `ai/path.h:131` and `:217` (ILP32 size asserts). ILP32 at -O0 and -O1 is byte-identical. |

## Build and seams

Real CE units, `clang -m32 -fms-extensions -fshort-wchar -fwrapv -fno-strict-aliasing` with `tests/soundreq_host_prefix.h`, include order shim, port, engine, src, tests, source:

- Real files: `ai/path.c`, `ai/path_smoothing.c`, `ai/path_structure_bsp.c`, `ai/path_obstacle_avoidance.c`, `ai/path_obstacles.c`, `ai/actor_moving.c`, `ai/ai_profile.c`, `math/real_math.c`, `math/matrix_math.c`, `physics/bsp2d.c`.
- Generated from source by exact text:
  - `physics/collision_bsp.c` (whole file) minus its `#include "collision_bsp.h"` line, with that header's result structs inserted after the last include (Xbox header conflicts on this host). Unresolved: `collision_log_*` (profiling, no-op stubs), `render_debug_*` (abort, reached only from debug renderers).
  - `ai/actors.c:actor_find_pathfinding_location`, `units/bipeds.c:biped_find_pathfinding_surface_index`, `units/bipeds.c:biped_find_ground_surface`.
  - `tag_files/tag_groups.c:tag_block_get_element_with_size` and `tag_empty_data`.
- Shim: `tests/c4_shim/xtl.h` (empty; `collision_usage.h` includes it for the hcex build only).
- Data-only stubs: `tests/c4_live_pathfinding_stubs.c` (scenario BSP pointers, `global_collision_bsp`, up to 16 scenery objects with per-object definitions and pathfinding spheres, unit 0 biped datum, the breakable bit vector, debug switches, tag accessors, cseries byte helpers, profiling no-ops).
- Abort-on-call stubs: `tests/c4_live_pathfinding_abort.c`.
- Stated driver seams: integrator (`actor_integrate`), per-tick `pathfinding_surface_index` (the biped selector's job), `actor_destination_tolerance` = 0.5 (vehicle definition absent from the tree), `ai_debug_get_path_storage` = NULL, `object_get_origin` = datum centre.
- Retail payload: full-record payload from the decompressed Prisoner BSP (surface, edge, vertex, flag and BSP3D/BSP2D tree records copied byte-for-byte).

## Old seam tests (kept, superseded)

`tests/test_c4_live_pathfinding.py` and `tests/c4_live_pathfinding_host.c` (revision 1) drive a transcription of `actor_moving.c:2143-2170`. They are superseded for (d), (e) and (f) by the real-source tests. They remain as a graph-level check, and the Prisoner stock-breakable invariance test (item 4) lives there.

## Reproduction

```sh
python3 -I -m pytest -q tests/test_c4_live_pathfinding_real.py tests/test_c4_live_pathfinding.py tests/test_hcu_mp_bot_pathfinding.py
```

Result: 8 passed, 26 subtests passed.

## Open items

1. The synthetic last-surface selection is not asserted. It would need BSP3D trees for the synthetic grid; retail covers the branch.
2. Native 64-bit parity is impossible while the HCU headers carry ILP32 size asserts. Not in this lane's scope to change them.
3. Whether CE's 2D point test is meant to reject upward counter-clockwise rings (item 1) is a question for the HCU collision lane. The selection outcome on stock data does not depend on the answer.
