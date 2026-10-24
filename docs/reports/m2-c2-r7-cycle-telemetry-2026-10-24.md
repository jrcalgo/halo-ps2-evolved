# M2 C2 round 7, lane cycle-telemetry (C2.6 per-cycle guest counters), 2026-10-24

Status: **partial.** The boundary hook is implemented and host-tested, and the EE objects compile. The lifecycle ELF
could not be rebuilt, so no guest per-cycle owner rows were produced. C2.6 stays open.

## Changes

- `src/stream/hcu_map_service.h`: `hcu_map_service_boundary_fn` (phase, cycle), three fields on `hcu_map_service`
  (`boundary_hook`, `boundary_context`, `boundary_cycle`), and `hcu_map_service_set_boundary_hook()`. A NULL hook is a
  no-op, and setting one resets the cycle to zero.
- `src/stream/hcu_map_service.c`: `notify_boundary()`. It fires:
  - `map-loaded` after a successful load (runtime path `profile_load` and legacy `map_loader`). The cycle counts
    successful loads and increments before the notification.
  - `map-released` after the owner's storage is released (`profile_unload` when an owner was live, and legacy
    `map_unloader` after `ctag_mount_unload`).
  - `map-empty` after a failed load (the safe-empty state in `profile_load`, and the legacy mount failure).
- `src/stream/hcu_main.c`: `hcu_map_boundary_report()` prints `HALO_PS2_LOCAL m2-cycle-boundary phase=... cycle=...`,
  then calls `hcu_report_owner_telemetry(phase)` and `hcu_report_cache_owners(phase)`. It is registered right after the
  map service init, before the legacy renderer-drain gate.
- `tests/hcu_map_service_profile_main.c`: a recorder and a new case. The hook is set before step 7 and checked after
  step 8: released (cycle 0), empty (cycle 0), loaded (cycle 1), released (cycle 1). It then clears the hook.
- `tests/test_hcu_map_service_profile.py`: the expected PASS count goes from 24 to 25.

## Evidence

- `cd tests && python3 -I test_hcu_map_service_profile.py`: `Ran 1 test ... OK` (25 PASS lines, including the new
  boundary-order case).
- `python3 -I tests/test_hcu_main_wiring.py`: `Ran 9 tests ... OK`.
- EE compile, with `PS2DEV=build/toolchain/install`, `PS2SDK=$PS2DEV/ps2sdk` and `ee/bin` on `PATH`:
  `make -f tools/ee-world.mk WORLD_HCU_GAMEPLAY=1 WORLD_OUTPUT=build/m2-c2-r7-cycle-telemetry/ee` built
  `stream/hcu_main.o` and `stream/hcu_map_service.o` with no errors.
- `git diff --check` is clean on the touched files, `submodules/halo-ps2` and `submodules/halo-ce-universal`.

## Lifecycle ELF and guest run: not produced

`timeout 2400 python3 tools/hcu_parent_link_probe.py --asset-profile host --m2-ui-lifecycle-test` failed twice with
`EXIT=1`. The failing step was `tools/hcu_ps2_closure.py --layer all --no-bootstrap-memory --m2-ui-lifecycle-test`.
Exact errors (from `build/hcu-ps2-closure/all-no-bootstrap-memory-m2-ui-lifecycle/`):

```
source/ai/ai.c:427:14: error: size of array 'ai_profile_collision_test_count_offset_assert' is negative
source/main/main.c:3477:17: error: expected declaration or statement at end of input
source/scenario/scenario.c:388: error: unterminated #ifdef
source/main/ps2_m2_ui_lifecycle_test.c:23:52: error: 'global_structure_bsp' undeclared
collect2: error: ld returned 1 exit status
```

These files are in `submodules/halo-ce-universal`, which has uncommitted edits from other lanes (`port/ps2/...` and more).
They are outside this lane's ownership and look mid-edit. The ELF was not rebuilt: the file on disk is still the 00:26
build from before this change, so it has no `m2-cycle-boundary` lines. `tools/c2_guest_run.py` was not run, because
running that stale ELF would not show the new hook. The per-cycle owner rows are therefore **not produced**.

## Side effect to note

`tests/test_hcu_map_service_profile.py` writes its artifacts to `build/m2-c2-map-service-profile` by default. This run
overwrote that directory's `result.json` and copies of the inputs, which belong to the earlier map-service evidence
(its `result.json` now reflects 25 PASS lines). The env var `HCU_MAP_SERVICE_PROFILE_ARTIFACTS` can redirect future runs.

## Limitations

- The host test covers only the runtime (`profile_load`/`profile_unload`) path. The legacy `map_loader`/`map_unloader`
  boundaries are wired but not host-tested. The test fixture has no legacy path for them.
- `map-released` fires only when an owner was live, so a no-op unload emits nothing.
- The cycle counter counts successful loads, and the hook is cleared with `NULL` in the host test only. The EE boot
  sets it once after init.

## Needed cross-lane changes

1. Make `submodules/halo-ce-universal` build the lifecycle profile (`source/ai/ai.c`, `source/main/main.c`,
   `source/scenario/scenario.c`, `source/main/ps2_m2_ui_lifecycle_test.c`). Owner: the lane editing those files.
2. Once the ELF builds, rerun `timeout 900 python3 -I tools/c2_guest_run.py --only lifecycle --source-elf <copied ELF> --timeout 600`
   and read the `m2-cycle-boundary` blocks for the per-cycle rows.
