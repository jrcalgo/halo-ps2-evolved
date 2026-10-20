# M0 source review: saved obstacle-path debug globals

## Disposition

Seven rooted globals are `excluded-proven`: `debug_ignore_broken_surfaces`, `debug_obstacle_path_finishing`, `debug_obstacle_path_goal_point`, `debug_obstacle_path_goal_surface_index`, `debug_obstacle_path_radius`, `debug_obstacle_path_start_point`, and `debug_obstacle_path_start_surface_index`. All are diagnostic snapshots, not live AI settings.

## Source trace

In `source/ai/path_obstacle_avoidance.c:1042-1054`, the only write path is inside the branch after the active `path_avoid_obstacles` search has failed. It copies the failed request's start/goal points, surface indices, radius, finishing flag, `ignore_broken_surfaces` input and obstacle/path work state into globals for later inspection. The current search result is then set to false and exits; these snapshots do not change that decision.

`render_debug_obstacle_path` at `path_obstacle_avoidance.c:1067-1108` consumes the stored values only while the separate debug mode is enabled. Pressing the developer replay key calls `path_new` against the saved request, and the renderer draws the saved obstacles/path. This is a second, explicit diagnostic execution; it does not write back to the actor's pathfinding state. `hs_globals_external.c:1548-1562` exposes the point/surface values for script/debug inspection, not for the live path algorithm.

## Regression guard

The test verifies the seven ledger entries are individually attributed to the diagnostic owner, references stay bounded to the failure-capture and debug-replay blocks, and the report records the distinction between the original AI decision and the saved replay. It is a source-contract regression test, not a visual test of obstacle debug rendering. If a future source revision reads these values in the normal path search, the test and this disposition must be revisited.
