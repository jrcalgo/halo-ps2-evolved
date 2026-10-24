# C2 repeated-use storage reuse (2026-10-24)

Exit clause: "repeated use reuses storage". Evidence level: host execution (PCSX2 interpreter, production headless runtime guest per row).

## Mechanism

- `submodules/halo-ce-universal/source/main/main.c` (`HALO_PS2_C2_PRODUCTION_RUNTIME_GUEST` block): the guest loops `load -> map-loaded -> [ticks] -> release` `HALO_PS2_C2_PRODUCTION_RUNTIME_CYCLES` times (default 1). Cycle 1 is the load `main_setup_connection()` already did; later cycles call `main_setup_connection()` again, the same preflight/dispose/unload/precache/`main_new_map` path CE uses. Markers carry `cycle=K cycles=N`; the map service's boundary hook prints owner telemetry with its own cycle counter. Cycles before the last print `production-ce-map-released-cycle` because `tools/c2_guest_run.py` stops PCSX2 at the first line containing `production-ce-map-released result=`.
- Optional `HALO_PS2_C2_PRODUCTION_RUNTIME_TICKS` (default 0): per cycle, N x (`player_control_update` + `game_time_update`, the step 8 workload's local-match frame order), then one `game_frame`.
- Defines reach the compile without touching the unowned closure/link scripts: the tool writes `<out>/cycles-inc/hcu_c2_cycles.h` and sets `C_INCLUDE_PATH`; main.c includes it via `__has_include`. Guest markers echo `cycles=N` and the parser rejects a stale count.
- `tools/c2_profile_boot_matrix.py --cycles N [--ticks T]`: output goes to `build/m2-c2-gaps-reuse/<row>` (the matrix results are untouched). `--ticks` is an addition beyond the requested `--cycles`. Per cycle it requires loaded and released markers (result=1, mounted=0, zero bytes), boundary telemetry, ticks result=1 (when requested), and per-cycle `resets` increase for game_state/tags/bsp owners and the tags/bsp cache owners. Across cycles 2..N the release snapshot (every owner used/high/failures, cache current/peak, backing used/high) must be identical. Cycle 1 vs 2 differences are reported, not failed. Existing failure-counter, fault and marker checks run over the whole log. Tests: `tests/test_c2_profile_boot_matrix.py` 24 passed (7 new).

## Results (all pass; zero failures, no faults)

| Row | Cycles x ticks | Elapsed | Result |
|---|---|---:|---|
| longest_mounted_gunner_4p4bot (smallest BSP margin, 2,608 B) | 3 x 0, then 3 x 300 | 476 s / 471 s | pass, pass |
| bloodgulch_mounted_gunner_4p4bot | 3 x 300 | 543 s | pass |
| sidewinder_marine_shotgun_4p4bot | 2 x 300 | 515 s | pass |

Sidewinder could not run 3 cycles inside the 600 s guest limit: each sidewinder load takes about 177 s under the interpreter (cycle 1 ended 254 s, cycle 2 at 437 s; a third would end near 614 s). The 3-cycle attempts (with and without ticks) stopped at the 600 s bound after cycle 2 with no fault and are kept as `sidewinder_cycles3_*_timeout_result.json` (fail). Sidewinder is therefore verified for 2 cycles only (one reload); cycles 2..N identity is then trivially a single sample, so the sidewinder claim is cycle 1 == cycle 2.

Per-cycle values at release (same in every cycle unless noted; resets are cumulative):

| Row | Cycle | tag bytes | bsp bytes | tags high/used | bsp high/used | game_state high/used | object_pool high | backing used/high | owner resets (gs/tags/bsp) | cache publications/unmounts |
|---|---|---:|---:|---|---|---|---:|---|---|---|
| longest 3x300 | 1 | 4,578,030 | 374,784 | 4,578,030 / 0 | 374,784 / 0 | 3,107,696 / 3,107,696 | 7,860 | 3,382,400 / 8,335,214 | 1/1/1 | 1/1 |
| longest 3x300 | 2 | same | same | same | same | same | 7,860 | same | 2/2/2 | 2/2 |
| longest 3x300 | 3 | same | same | same | same | same | 7,860 | same | 3/3/3 | 3/3 |
| bloodgulch 3x300 | 1 | 4,795,978 | 1,296,384 | 4,795,978 / 0 | 1,296,384 / 0 | 3,107,696 / 3,107,696 | 54,804 | 3,382,400 / 9,474,762 | 1/1/1 | 1/1 |
| bloodgulch 3x300 | 2, 3 | same | same | same | same | same | same | same | 2/2/2, 3/3/3 | 2/2, 3/3 |
| sidewinder 2x300 | 1 | 6,913,928 | 1,984,512 | 6,913,928 / 0 | 1,984,512 / 0 | 3,107,696 / 3,107,696 | 48,460 | 3,382,400 / 12,280,840 | 1/1/1 | 1/1 |
| sidewinder 2x300 | 2 | same | same | same | same | same | 48,460 | same | 2/2/2 | 2/2 |

Result files: `build/m2-c2-gaps-reuse/*_result.json` (`cycle_checks.per_cycle[].at_release`).

Arena `used` after release: the `streaming_map_owner` arena is printed only once, in the after-shell dump, after all cycles. Its `used` matches the single-cycle matrix value exactly (longest 122,360; bloodgulch 129,020; sidewinder 182,868), so three (two for sidewinder) load/release cycles added no residency storage. Per-cycle arena lines were not available without editing `src/stream/hcu_main.c` (not in this lane's ownership); per-cycle evidence for storage is the owner `used`/`high` and backing used/high above.

## Ticks

300 ticks per cycle ran for all three rows (`production-ce-ticks result=1 ticks=300`), the object_pool high rising (longest 2,000 -> 7,860; sidewinder 48,460), game_state unchanged, zero failures. Scope: one local player (`local-players=1`), single-player-style CE spawn from the scenario; no 4-player split-screen and no bots, despite the 4p4bot row names. It is not the step 8 workload (that needs `hcu_step8_test_start_local_map` from the diagnostic build).

## Limits

- Interpreter PCSX2, no renderer loop, no integrated readers.
- Peaks are cumulative `high` counters, so identical high across cycles shows no growth beyond cycle 1's peak, not that cycle 1 peaked at the minimum.
- Sidewinder 2 cycles only (guest time limit); not 3.
- The fourth selected map extreme (the matrix-wide smallest tag margin, ratrace 0 B) was not run in this lane.
