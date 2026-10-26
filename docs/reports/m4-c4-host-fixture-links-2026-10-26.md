# M4 C4 host fixture link repair (2026-10-26)

Scope: the ILP32 host fixtures that give C4 their runtime parity evidence failed to LINK
(undefined `unit_get_camera_position`, `unit_get_aiming_vector`, `observer_up_from_forward`,
`render_interpolation_object_node_matrices`, `matrix4x3_from_point_and_vectors`,
`matrix4x3_multiply`). Production CE/HCU sources, expected values, goldens and pins were not edited.

## Root cause

Recipe: `tests/test_hcu_mp_capacity.py` (`MultiplayerHostCollisionMatrix`, gcc command near the
`sources` list). It compiles `tests/hcu_objects_host32.c` (copied to a temp file named
`matrix_hcu_objects_host32.c`, which includes CE `source/objects/objects.c`) and
`tests/hcu_game_sound_host32.c` (includes CE `source/sound/game_sound.c`). Those TUs reference six
definitions that live in CE files the recipe never compiles: `source/camera/observer.c`,
`source/units/units.c`, `source/math/matrix_math.c`, and `port/ps2/src/ps2_render.c`.

Every fixture that builds through this recipe inherits the break: the capacity test, the sound
scenery runtime fixture, and the `tools/test_hcu_mp_fog_*.py` fixtures (they copy the capacity test's
source list through `tools/test_hcu_mp_fog_selection_all.py`).

## Fix (shared recipe, not per-fixture)

1. New `tests/c4_host_shims/ce_host_link_closure.py`. It extracts four production function bodies
   verbatim from the submodule at build time (brace-matched, each must occur exactly once):
   - `source/math/matrix_math.c`: `matrix4x3_rotation_from_vectors`, `matrix4x3_from_point_and_vectors`,
     `matrix4x3_multiply`;
   - `source/camera/observer.c`: `observer_up_from_forward`;
   - `port/ps2/src/ps2_render.c`: `render_interpolation_object_node_matrices` (the PS2 target body,
     `return NULL`, which means "use the CE object datum matrices". The host fixtures never enter
     interpolation rendering, so the linux `render_interpolation.c` body would take the same path).
   It writes them into one generated TU `c4_ce_host_link_closure.c` in the fixture temp dir.
2. New `tests/c4_host_shims/c4_unit_camera_unreachable_shim.c`: fail-loud `abort()` stubs for
   `unit_get_camera_position` and `unit_get_aiming_vector`. Extracting the real bodies was tried and
   failed: they pull the biped and model graph (`biped_get_sight_position`, `model_get_marker_by_name`,
   `matrix4x3_identity`), a cascade with no bound. CE `sound_listener_camera()` only calls them when
   the observer camera has no cluster and a zero position and the player owns a unit. The MP fixtures set
   explicit listener cameras, so the branch is not reached. Evidence it is not reached: every fixture
   below passes, and any call would abort. The stub is therefore not on the executed path.
3. `tests/test_hcu_mp_capacity.py`: imports `write_closure_tu` and appends its two outputs to `sources`
   next to `hcu_map_service_host.c`. Nothing else changed in that file. Fixtures that copy that source list
   (fog tools) inherit the fix. The sound-scenery fixture's own `generated_matrix` only defines
   `matrix4x3_rotation_from_angles` and `matrix4x3_to_point_and_vectors`, which the closure does not define,
   so there is no duplicate symbol.

## Commands and results

Before = the reproduced failure on this tree before the change (the four originals). After = this change.

| Fixture | Command | Before | After |
|---|---|---|---|
| tools/test_hcu_mp_fog_plane_sides.py | `python3 -I tools/test_hcu_mp_fog_plane_sides.py` | exit 1, ld undefined refs | exit 0, 1 test OK (98 s) |
| tools/test_hcu_mp_fog_selection_all.py | `python3 -I tools/test_hcu_mp_fog_selection_all.py` | exit 1, ld undefined refs | exit 0, 1 test OK (101 s) |
| tests/test_hcu_mp_capacity.py | `python3 -m pytest -q tests/test_hcu_mp_capacity.py` | 1 failed (ld) | 1 passed (105 s) |
| tests/test_hcu_mp_sound_scenery_runtime.py | `python3 -m pytest -q tests/test_hcu_mp_sound_scenery_runtime.py` | 1 failed (ld) | 1 passed (96 s, run alone) |
| tools/test_hcu_mp_fog_invalid_refs.py | `python3 -I ...` | not run before (same recipe family) | exit 0, 1 test OK |
| tools/test_hcu_mp_fog_invalid_refs_all.py | `python3 -I ...` | not run before | exit 0, 1 test OK |
| tools/test_hcu_mp_visible_pvs_sound.py | `python3 -I ...` | not run before | exit 0, 1 test OK |
| tools/test_hcu_mp_target_capacity.py | `python3 -I ...` | not run before | exit 0 (no test-summary line printed; JSON report written) |
| tools/test_hcu_mp_collision_edge.py | `python3 -I ...` | not run before | exit 0, "OK" |
| tests/test_hcu_mp_wind_package.py | `python3 -m pytest -q` | not run before | 1 passed |
| tests/test_hcu_scenario_bsp_switch.py | `python3 -m pytest -q` | not run before | 1 passed, 1 skipped |
| tests/test_hcu_sound_scenery.py | `python3 -m pytest -q` | not run before | 1 passed |
| tests/test_hcu_mp_breakable_runtime.py | `python3 -m pytest -q` | not run before | 1 passed (110 s) |
| tests/test_c4_fog_pin.py | `python3 -I -m pytest -q` | 7 passed | 7 passed |
| tests/test_c4_parity_fog.py | `python3 -m pytest -q` | not run before | 10 passed, 25 subtests |
| tests/test_hcu_mp_detail_present_bound.py | `python3 -m pytest -q` | not run before | FAILED, input missing (see below) |
| tests/test_hcu_mp_swept_collision.py | `python3 -m pytest -q` | not run before | FAILED, pinned Blood Gulch package missing (known, see below) |

"Not run before" rows use the same recipe or none of the changed code. Their before state was not separately
reproduced; no link error was observed for them after the change.

## Remaining failures (not link errors; not fixed)

- `tests/test_hcu_mp_detail_present_bound.py`: fails at 1 s on `missing HP2 package
  /tmp/hcu-m2-capacity-repro.P5qdmI/packages/beavercreek.hp2`. The fixture hardcodes a /tmp directory from a past
  run that no longer exists (`PACKAGES` at line 20). This is missing input, not a link or logic failure. The
  fixture needs its package staging restored, not a golden change. Not touched.
- `tests/test_hcu_mp_swept_collision.py::test_bloodgulch_pill_and_sphere_match_raw_floor_oracle`: "pinned
  Blood Gulch package is missing". Already reported as blocker B2 in m4-c4-oracles-2026-10-26.md.

## Logic divergence

None found. Every fixture that links runs its own assertions to completion and passes, including the 13-map
all-map fog selection and the sound-scenery placement/callback checks. No golden or expected value was changed.

## Notes

- Fixtures in the capacity family write retained executables to `build/m2-mp-weather-wind-13/`,
  and fog runs write to `build/mp-fog-selection-*` and `build/m2-mp-fog-selection-*`. These are normal fixture outputs.
  Do not run two of them concurrently: they race on the same retained executable path and fail with
  "Text file busy" (observed once, then re-run solo, pass). Nothing under `build/` was edited by hand.
- Files changed: `tests/test_hcu_mp_capacity.py` (import + two `sources` lines; see above). New:
  `tests/c4_host_shims/ce_host_link_closure.py`, `tests/c4_host_shims/c4_unit_camera_unreachable_shim.c`,
  this report. No production source, pin, golden, expected value or `build/` artifact was edited.
- Open: the unit camera accessors are fail-loud stubs. If a future fixture drives a unit-owned listener, it
  will abort and must be given a real unit closure (the biped/model graph) instead of an invented position.

## Follow-up: tests/test_hcu_mp_path_smoothing.py (compile failure)

Symptom: `compile failed pathsmooth_ce_extract.c`. Cause: the generated extract TU (built by `write_extract`)
referenced file-static CE state it did not carry. Diagnosis from `build/step7-swarm/pathsmooth/pathsmooth.log`:
- `s_actor_pool_high_water`, `s_actor_pool_failed_allocations`, `s_actor_pool_resets` (CE `ai/actors.c:561-563`)
  are used by the extracted `actors_initialize()` and actor pool paths. The declarations were not extracted.
- Second failure after the first fix: the link stub `object_pool_counters_note` (CE `objects/objects.c:750`, static)
  was reached by the extracted pool paths, so the generated fail-loud "unexpected CE call" stub aborted.

Fix (test-side extraction only; no production source, assertion, or golden changed):
1. The three counter declarations are copied verbatim from `actors.c`, each checked to occur exactly once
   (`AssertionError` if CE changes), and placed before the actor function extracts so they precede their uses.
2. `object_pool_counters_note` is extracted verbatim with `extract_last` from `objects.c`. Its body is compiled out
   under this host build (no `HALO_PS2` define), so this reproduces production behaviour, not a stub.

Result: `python3 -m pytest -q tests/test_hcu_mp_path_smoothing.py` -> **1 passed** (4 s). `git diff` for this file is
additions only (8 + 8 lines); no existing assertion, expected value or golden was touched.
