# M2 C2 r8, lane alloc-final (C2.5 remaining open sites)

Date: 2026-10-24. Host and EE-compile evidence only. Nothing here ran on PCSX2 or hardware, and no workload trace was taken.

## Result

- Open callsites: **20 at the start of the lane, 0 now.** Three more appeared during the lane, from another lane's new code in `src/stream/hcu_main.c` (`hcu_register_selected_runtime`, lines 356-358). All 23 are now closed by a verdict with a cited basis.
- Inventory: `docs/reports/m2-c2-5-postload-allocation-source-inventory-2026-10-23.json` regenerated. 216 allocator callsites in 67 files. 63 sit outside the load-or-init phase and carry a verdict (30 unreachable-selected-build, 20 load-only, 7 bounded-after-binding, 6 bounded-in-pool). 153 are load-or-init by name and carry no verdict.
- Verdict closure: 13 bounded verdicts close on a counter-backed basis, and every bounded basis in the table cites a counter.
- `tests/test_hcu_c2_alloc_b.py`: 17 tests pass.
- Full closure (`tools/hcu_ps2_closure.py --layer all --no-bootstrap-memory`): **`failed_count` 0**, 373 units compiled. The gate stays `open`, as it does for every layer-measured run.

**C2.5 exit is still not claimed.** The inventory is source-only. Its own limitations say that phase, owner instance and allocation size need runtime observation, and no recurrent path, bot, wave or mode trace exists. Zero open sites means every site has a verdict and a basis, not that the workload has been measured.

## Touched files

Repository:
- `tools/audit_hcu_postload_allocations.py`: verdict rows for the 23 sites, a final-verdict layer applied after the alloc-a file, and the `alloc-final verdict rows applied` summary line.
- `tests/test_hcu_c2_alloc_b.py`: stale expectation fixed (`file_read_into_memory` match_malloc is `unreachable-selected-build`); new tests for the final layer, the counter-backed bounded rows, the cseries rows staying in the PS2 source set, the hs accessors, the revert refusal ordering, and the single owner-counter prototype; inventory open-site test.
- `docs/reports/m2-c2-5-postload-allocation-source-inventory-2026-10-23.json`: regenerated.

Submodule `submodules/halo-ce-universal`:
- `port/ps2/include/halo_ps2_owner_counters.h`: prototype for `halo_ps2_owner_counters_note_pool`, with a comment that the call is valid only for `HALO_PS2_OWNER_OBJECT_POOL`.
- `source/objects/objects.c`: the local prototype of `halo_ps2_owner_counters_note_pool` is removed. Nothing else changed.
- `source/hs/hs.c`, `source/hs/hs.h`: accessors `hs_port_recompile_refusal_count()` and `hs_port_core_load_refusal_count()`, under `#if defined(HALO_PS2)`.
- `source/saved games/game_state_xbox.c`: `game_state_read_from_file` refuses the read on PS2 whenever `game_engine_running()`, before the whole-image `malloc`, and increments `game_state_port_revert_refusals`. The accessor `game_state_port_revert_refusal_count()` reads it. The file includes `game/game_engine.h` for `game_engine_running`.

Not touched: `source/memory/**` (no change was needed; the stack-pool rows close on the pool's existing counters), `source/game/game_state.c` and `port/ps2/src/ps2_owner_counters.c` (both read only).

## Verdicts for the 20 starting sites, and the new site

| Sites | Callsite | Verdict | Basis (abbreviated) |
|---|---|---|---|
| 7 (hcu_main.c:657, 660, 751, 752, 754, 756, 758) | `main` `arena_alloc` | load-only | `main()` runs once. These run before `halo_shell_main()` (:881), and no loop in `main()` repeats them. |
| 1 (hcu_map_service.c:195) | `feed_ctag_first_pass` `arena_alloc` | load-only | Map-load preflight, rewound. `preflight_ctag_stream` rewinds at :266 and `hcu_map_service_preflight` rewinds `map_arena` at :1062. Reached from the CE map preflight hook (:772) and the map loader (:600, :716). |
| 3 new (hcu_main.c:356-358) | `hcu_register_selected_runtime` `arena_alloc` | load-only | Called once from `main()` (:1012), before `halo_shell_main()` (:1073). |
| 4 (cseries_windows.c:176, 182, 209, 214) | `system_calloc`, `system_malloc`, `system_realloc` (`GlobalAlloc`, `GlobalReAlloc`) | bounded-after-binding | **Not excluded.** `port.json` does not exclude `cseries_windows.c`, and the closure compiles it. Its `GlobalAlloc` and `GlobalReAlloc` are the PS2 ones (`ps2_memory.c:479`, `:696`), which allocate from the fixed compat arena, refuse on exhaustion, and never use the SDK heap. Counters: `physical_memory_get_malloc_fallback_counters` (`refused_unbound`, `sdk_malloc_preactivation`, `sdk_realloc`) and `malloc_high_water`. |
| 2 (stack_memory_pool.c:1167, 1182) | `stack_memory_pool_resize_block` → `stack_memory_pool_allocate` | bounded-in-pool | UI widget pool only. Callers: `ui_widget.c:1924`, `:5120`, `:5244`. The pool is a fixed `WIDGET_MEMORY_POOL_SIZE` (0x40000) block, allocated once at `ui_widgets_initialize` (:2170). High-water fields `maximum_bytes_used` and `maximum_block_count_used` are kept in the pool. |
| 2 (objects.c:810, 835) | `object_header_delete` → `memory_pool_block_free`; `object_header_block_allocate` → `memory_pool_block_reallocate` | bounded-in-pool | `object_memory_pool` is a fixed memory pool. Every change calls `object_pool_counters_note()`, which pushes used, high-water, allocation-failure and reset counters to `HALO_PS2_OWNER_OBJECT_POOL`. |
| 1 (objects.c:4757) | `object_name_list_allocate` → `game_state_malloc` | load-only | `objects_initialize` (:1169) ← `game_initialize` (game.c:299) ← `main_loop` (main.c:3501), which calls `game_initialize` once before its frame loop. `shell_xbox.c:122` calls `main_loop` once. The alloc-a file's `unverified-open` row for this function is overridden (see below). |
| 2 (game_state_xbox.c:343 `malloc`, :362 `free`) | `game_state_read_from_file` | unreachable-selected-build | Refused on PS2 whenever `game_engine_running()`. Only `game_state_revert` calls it. Its callers are checkpoint revert (main.c:2070, :2090), cinematic skip (:2113), the lost-map respawn (:2266, armed only without a game engine, players.c:5136), and save-and-quit (game_state.c:421). `game_engine_running()` is `game_engine != NULL`, and `game_engine_initialize` sets `game_engine` only for a variant with a nonzero engine index. The campaign has none (`game_engine.c:2058`, `campaign = !game_engine`). |
| 1 (mem.c:65) | `arena_sub_aligned` → `arena_alloc` | unreachable-selected-build | `arena_sub` is its only caller, and `arena_sub` has no caller in `src/`, the halo-ps2 engine, or the CE source and port trees. |

### Multiplayer reachability of the checkpoint revert

- Lost-map: armed only with no game engine (`players.c:5136`), so it cannot arm in a game with an engine.
- Solo pause restart (`pause_game_restart_at_checkpoint`): the handler in the solo pause menu. This lane did not trace whether the multiplayer pause ever uses this handler; that is a tag-data question.
- Cinematic skip and the `game_revert` script built-in: reachable in a multiplayer game if its cinematic or script calls them. The multiplayer map scripts are not in the tag inventory, so this is not proven either way.
- **Decision:** the PS2 build refuses the read whenever a game engine runs. That makes the checkpoint read a campaign-only path, which is the option the lane brief named, and the refusal is counted.

**Behaviour change, stated plainly.** A refused read takes `game_state_revert`'s existing failure branch: `saved_game_valid` is cleared and `main_reset_map()` runs. So a refused revert in a multiplayer game restarts the map. Save-and-quit in a multiplayer game with one spawned player writes the current state, not a checkpoint.

## Code change verification

- Closure (`HALO_BUILD_ROOT=build/m2-c2-r8-alloc-final/root`, toolchain symlinked from `build/toolchain`, `--layer all --no-bootstrap-memory`): `failed_count` 0, `compiled_count` 373. Touched objects compiled with the closure flags (`-std=gnu89 -Os -mabi=n32 -fms-extensions -fshort-wchar -fcommon -fno-strict-aliasing -ffp-contract=off -fsigned-char -fwrapv -G0 -D_EE`, plus the manifest include set):
  - `source/hs/hs.c` (object sha `e5f8b7d3bc04`)
  - `source/saved games/game_state_xbox.c` (`1151989dbd89`)
  - `source/objects/objects.c` (`a3cc9587ae9e`)
  - `source/cseries/cseries_windows.c` (`30c68559f4d1`), `source/memory/stack_memory_pool.c`, `port/ps2/src/ps2_owner_counters.c`
- Closure output: `build/m2-c2-r8-alloc-final/root/hcu-ps2-closure/all-no-bootstrap-memory/result.json` (log: `build/m2-c2-r8-alloc-final/closure.log`). The shared baseline `build/hcu-ps2-closure/all-no-bootstrap-memory` was not written.
- `python3 -I tools/audit_hcu_postload_allocations.py --output docs/reports/m2-c2-5-postload-allocation-source-inventory-2026-10-23.json`: `open callsites remaining: 0`.
- `python3 tests/test_hcu_c2_alloc_b.py`: `Ran 17 tests ... OK`.
- `git diff --check`: clean for the three repository files and the submodule files touched (`port/ps2/include/halo_ps2_owner_counters.h`, `source/objects/objects.c`, `source/hs/hs.c`, `source/hs/hs.h`, `source/saved games/game_state_xbox.c`).

## Final-verdict layer

The alloc-a file (`docs/reports/m2-c2-r6-alloc-a-verdicts.json`, untracked, another lane's) overrides built-in rows by function. Three of its rows carry no counter or caller evidence and would keep the object-pool and name-list sites open, so the audit tool now applies `FINAL_VERDICTS` after that file. A final row replaces every row of its file and function. Three rows are final: the two object-pool rows (bounded-in-pool, counter-backed basis) and `object_name_list_allocate` (load-only). Source tag: `alloc-final`.

## Residual risks and cross-lane changes

1. **Survival variant engine index not traced.** The revert refusal assumes survival profiles run a game variant with a nonzero engine index. If a survival variant has index 0, its revert reaches the read, and the two `game_state_read_from_file` verdicts would be wrong. Owner: the survival profile generator (`tools/hcu_multiplayer_profiles.py`) or the survival variant definition.
2. **Object-pool telemetry omits reallocation failures.** `object_pool_counters_note` (`source/objects/objects.c`) forwards the pool's `allocation_failures` but not `reallocation_failures` (`source/memory/memory_pool.c:310`), so a refused in-place object reallocate is not in owner telemetry. The bound holds (the call returns FALSE and never uses the SDK heap), but the telemetry is incomplete. Needed change, outside this lane's ownership: forward `reallocation_failures` as part of `failures` in `objects.c`. The basis text cites this gap.
3. **Misleading comment in `port/ps2/src/ps2_owner_counters.c`.** It says a refused reallocate "is counted once, as the allocation it made inside the pool". The code counts it under `reallocation_failures` only. Needed change: correct that comment (outside this lane).
4. **Widget pool exhaustion is an assert, not a counter.** The stack-pool rows close on high-water counters. Exhaustion goes through `display_assert` and returns NULL, and no owner telemetry reports it. This is a C2.6 gap, not a heap fallback.
5. **Campaign revert is still compiled and reachable in a campaign run.** The verdict is scoped to the C2 selected profiles (UI, multiplayer bot, survival). A campaign build would need the same review.
6. **The alloc-a file is untracked and overridden.** Its three object rows were replaced by the final layer. Owner: the alloc-a lane should reconcile the file with this report before it is committed.

Nothing in this lane was run on PCSX2 or hardware. No EE memory fit, workload trace or console result is claimed.

## C2.6 counter correction follow-up (2026-10-24)

The object-pool producer now passes `allocation_failures` and `reallocation_failures` separately to the PS2 owner counter. The published `failures` value is their saturating sum. These source counters overlap for a refused moving reallocate: the replacement block allocation fails and then the reallocate operation returns false, so the aggregate intentionally reflects both recorded failure events. This replaces the earlier comment that claimed a refused reallocation was counted once as an allocation.

The UI widget pool now routes each of its three allocation and three resize callsites through small reporting wrappers. A failed positive-size request increments `HALO_PS2_OWNER_WIDGET_POOL`; pool capacity, current use, and the stack pool's existing high-water value are sampled without enlarging the pool or its data structure. Pool reset increments its reset count and starts a new high-water window. The PS2 owner-counter ID/API is ready for the parent HCU owner-row binding; no guest trace from the changed source is claimed here.

Focused verification: `python3 -m pytest -q tests/test_hcu_ce_owner_counters.py tests/test_hcu_c2_alloc_b.py` — **21 passed**. This includes host execution of the counter producer, ILP32 compilation of the PS2 port counter, saturated failure aggregation, widget owner update/failure/reset behavior, and source checks that all current widget stack-pool callsites use the reporting wrappers. `git diff --check` is clean for the touched CE source, port counter, and focused test files.
