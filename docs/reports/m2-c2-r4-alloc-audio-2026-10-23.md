# M2 C2 r4, lane alloc-audio (C2.5 open sites, C2.6 audio requests)

Date: 2026-10-23. Build outputs: `build/m2-c2-r4-alloc-audio/`. Status is host and EE compile evidence only; nothing here ran on PCSX2 or hardware.

## Changes

- `submodules/halo-ce-universal/source/hs/hs_compile.c`: the console/cheat expression path no longer calls `match_malloc` per command. Its text (bounded by `HS_MAXIMUM_DYNAMIC_SOURCE_DATA_BYTES`, 0x400) is compiled in the static `hs_compile_expression_scratch`. `hs_compile_dispose` skips `match_free` for that buffer. The whole-source realloc of `hs_compile` (`hs_compile_add_source`, line 1006) is still on the heap and stays open.
- `submodules/halo-ce-universal/port/ps2/src/ps2_sound_cache.c`, `port/ps2/src/ps2_owner_counters.c`, `port/ps2/include/halo_ps2_owner_counters.h`: the PS2 audio request path counts each request. Playback is out of scope, so a request is accepted or refused on the spot and never held. The owner is bound at `sound_cache_new` with capacity 0 (no request storage), `submitted` and `failures` count requests, high water stays 0, and `sound_cache_close` (map change) counts a reset. `HALO_PS2_OWNER_AUDIO_REQUESTS` is no longer a special -1 case; it reads as bound once bound.
- `tests/hcu_ce_owner_counters_main.c`: `check_audio_requests` replaces the old "unavailable" check. It covers unbound, bound, submitted/failed counts and reset.
- `tools/audit_hcu_postload_allocations.py`: verdict table updated (line keys follow the new `hs_compile.c` layout; traced callers recorded). Inventory regenerated through the tool: `docs/reports/m2-c2-5-postload-allocation-source-inventory-2026-10-23.json`.

Path note: the lane brief names `source/memory/debug_memory.c`. The file is `source/cseries/debug_memory.c`. It was not edited (see below).

## Verdict movement (210 callsites)

| verdict | before | after |
| --- | ---: | ---: |
| recurrent-open | 9 | 8 |
| unknown-open | 17 | 15 |
| unreachable-selected-build | 20 | 22 |
| unverified | 8 | 7 |
| load-only | 6 | 6 |
| cross-lane-open | 1 | 1 |

Traced to a verdict: `array.c:225` and `lruv_cache.c:216` are now `unreachable-selected-build` (no caller in the selected tree). The `hs_compile.c` expression malloc is gone. Reasons were refreshed with cited callers for `debug_memory.c` (system_* routes to the compat arena), `memory_pool.c`/`objects.c` (bounded in the pool, FALSE on exhaustion), `files.c` (hs.c:13518/13538), and the save-game reads (`game_state.c:405`, `:1075`, `:1096`).

Still open: 8 recurrent-open sites (debug heap x3, `hs_compile` realloc, memory_pool x2, objects.c x2) and 15 unknown-open (Windows-only `cseries_windows.c` x4, `game_state_xbox.c` x6, `files.c` x2, `stack_memory_pool` x2, `mem.c` x1). The remaining 15 are not traced to a verdict.

## Verification

- `python3 -I tools/test_hcu_ps2_malloc_endless.py`: `ps2-malloc-endless ops=2000000 allocs=785655 frees=785426 reallocs=336483 failures=0 fragmentation_failures=0 realloc_failures_preserved=0 largest_after_drain=1048560 sdk_fallbacks=0`
- `python3 -I tools/test_hcu_ps2_malloc_diagnostic.py`: `ps2-malloc-diagnostic preboot-realloc=preserved align=16 high_water=224 failures=3 free=coalesced-reuse rebind_reset=passed`
- `python3 -I tests/test_hcu_ce_owner_counters.py`: 2 tests, OK (`check_audio_requests` included)
- EE compile with the closure flags (`build/toolchain/install/ee/bin/mips64r5900el-ps2-elf-gcc`, `-mabi=n32 -G0 ...`): `hs_compile.c`, `ps2_sound_cache.c` (needed extra `-I source/interface` and `-I port/linux/game`, `-I source/bungie_net`) and `ps2_owner_counters.c` all compile, rc 0.
- `python3 -I tools/hcu_ps2_closure.py --layer all --no-bootstrap-memory`: rc 0, `failed_count` 0, `compiled_count` 373, `selected_source_count` 342 (`build/hcu-ps2-closure/all-no-bootstrap-memory/result.json`).
- `git diff --check` clean in the repo and in `submodules/halo-ce-universal` (for the touched files).

## Not met (honest)

- C2.5 exit is not met. Eight recurrent-open sites remain, and their steady-state reuse is not proven: there is no host fixture for the expression path, since `hs_compile.c` needs the whole engine. The endless-churn test covers only the PS2 compat arena.
- `debug_memory.c` (cseries) was classified but not edited. On PS2 once the arena is bound, system_* refuses rather than using the SDK heap (`ps2_memory.c:373`). The pre-binding SDK fallback is counted, not removed.
- `memory_pool.c` and `objects.c` allocation paths are bounded in the object pool and were not changed. No counter for pool-level block reallocate exists.
- C2.6 audio: the request counters are host-tested and the owner is bound, but there is no runtime playback or live workload snapshot. Capacity is 0 bytes by design, not a ring.
- The `hs_compile_add_source` realloc remains a heap allocation on the console and scenario compile path.
