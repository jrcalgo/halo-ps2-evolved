# M2 C2 r7, lane objects-pool (C2.5 object-pool verdicts, C2.6 object-pool telemetry)

Date: 2026-10-24. Host and EE compile evidence only. Nothing ran on PCSX2 or hardware.
Build outputs: `build/m2-c2-r7-objects-pool/` (`ce-counters/`, `ee/`).

## Changes

- `submodules/halo-ce-universal/port/ps2/src/ps2_owner_counters.c`: new
  `halo_ps2_owner_counters_note_pool()`, which copies a memory pool's own counters into
  `HALO_PS2_OWNER_OBJECT_POOL` (capacity, used, high water, failures, resets; values saturate at
  UINT32_MAX). `halo_ps2_owner_counters_bind_datum()` now accepts the actor pool only, so the object
  pool's datum-array estimate is gone.
- `submodules/halo-ce-universal/source/objects/objects.c` (allocation paths and counters only):
  - `object_pool_counters_note()` reads `memory_pool_get_counters(object_memory_pool)` and calls
    `halo_ps2_owner_counters_note_pool()`.
  - It runs after `object_header_new`, `object_header_delete`, `object_header_block_allocate`,
    the object-pool init in `objects_initialize`, and the dispose loop in `objects_dispose_from_old_map`.
  - The old `bind_datum` call for the object header array in `objects_initialize` is replaced.
- `tests/hcu_ce_owner_counters_main.c`: object-pool checks (pool values copied as they are, bad owners
  refused without touching game state, saturation, datum binding limited to the actor pool).
- `tests/test_hcu_ce_owner_counters.py`: output moved to `build/m2-c2-r7-objects-pool/ce-counters`
  (it wrote to another lane's build directory).
- `docs/reports/m2-c2-r7-objects-pool-verdicts.json`: verdicts for `objects.c` 4757 (the former 4734,
  `object_name_list_allocate`), `object_header_new`, `object_header_delete` and
  `object_header_block_allocate`, plus the telemetry mapping.

## Verdicts (summary; full evidence in the JSON)

- `object_name_list_allocate` (objects.c 4754): **load-only**. The only caller chain is
  `main()` (`source/main/main.c:3501`) -> `game_initialize` (`game.c:299`) -> `objects_initialize`
  (`objects.c:1169`) -> `game_state_malloc`, a bump carve of the fixed game-state block. It runs once at
  boot and never per map or per tick.
- `object_header_new`, `object_header_delete`, `object_header_block_allocate`: **bounded-in-pool**.
  All three use only `object_memory_pool`, created once at `objects.c:1150` with
  `OBJECT_MEMORY_POOL_SIZE` (0x100000 on PS2, `port/ps2/include/halo_ps2_limits.h:34`). A refused
  allocation returns NONE or FALSE with no fallback. Freed blocks are reused inside the pool.

## Verification

- `python3 -I tests/test_hcu_ce_owner_counters.py`: 2 tests, OK. The harness prints
  `hcu_ce_owner_counters: pass`. The ILP32 (`-m32`) compile of the producer also passed.
- EE compile, closure flags (`tools/hcu_ps2_closure.py` FLAGS, manifest include order and `-include`
  headers, the same per-unit command): `source/objects/objects.c` rc 0, `port/ps2/src/ps2_owner_counters.c`
  rc 0, both with 0 warnings and 0 errors printed (the closure flags include `-w`).
  Objects are in `build/m2-c2-r7-objects-pool/ee/`.
- `git diff --check` clean for `submodules/halo-ce-universal` `source/objects/objects.c` and
  `port/ps2/src/ps2_owner_counters.c`, and for the repository files touched in this lane.
- JSON verdicts parse (`python3 -m json.tool`).

## Not met (honest)

- **The full closure was not rerun.** `tools/hcu_ps2_closure.py --layer all --no-bootstrap-memory`
  writes the shared `build/hcu-ps2-closure/all-no-bootstrap-memory` directory, which other lanes use,
  so `failed_count 0` is not re-established by this lane. The two touched objects compile with the
  closure's flags.
- No PS2 run. The counters are host-tested and EE-compiled only. No Sidewinder or Blood Gulch
  workload trace of the object pool exists in this lane, so the bounded-in-pool verdicts rest on
  call-site reading plus the pool-level host result of the r6 driver
  (`docs/reports/m2-c2-r6-alloc-a-2026-10-24.md`: 100,000 cycles, used_after_drain 0, corruptions 0,
  escapes 0). The objects.c path itself is not host-compiled.
- C2.5 and C2.6 remain open for the whole C2 exit (other owners, workload attribution). This lane
  does not change `docs/reports/m2-c2-status-2026-10-23.json` or the plan.
