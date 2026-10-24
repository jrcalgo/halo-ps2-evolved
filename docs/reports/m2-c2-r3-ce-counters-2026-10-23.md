# M2 C2 r3 lane ce-counters: always-on CE owner counters (C2.6)

Lane: C2.6 CE producers. Scope: game state, object and actor datum pools, tags and BSP publication, audio requests.

## What changed

- `submodules/halo-ce-universal/port/ps2/include/halo_ps2_owner_counters.h`: the typedef, owner enum and `halo_ps2_owner_counters_get`, as specified.
- `submodules/halo-ce-universal/port/ps2/src/ps2_owner_counters.c` (new): counter state and the get function. Nothing allocates. Counters saturate at `UINT32_MAX`.
  - Game state, object pool and actor pool are pushed in by their producers.
  - Tags and BSP are read from the existing `ps2_cache` publication telemetry (`tag_*`, `bsp_*` fields). `ps2_cache.c` is not changed, so nothing is counted twice.
  - Audio requests are reported as unbound (`get` returns -1). See the limits below.
- `submodules/halo-ce-universal/source/saved games/game_state.c`: always-on (`#if defined(HALO_PS2)`, not the opt-in diagnostic macro) cursor update in `game_state_malloc`, failure count for a request that exceeds the fixed CPU bound, and a reset on `game_state_initialize_for_new_map`. The existing opt-in diagnostics are unchanged.
- `submodules/halo-ce-universal/source/memory/data.c`: always-on hooks in `datum_new` (a full array counts as a failure), `datum_delete` (used update), `data_make_invalid` and `data_delete_all` (resets). Datum layouts are unchanged.
- `submodules/halo-ce-universal/source/objects/objects.c` and `source/ai/actors.c`: bind the object header array (`object_header_data`) and the actor array (`actor_data`) as the object and actor pools after creation.
- `submodules/halo-ce-universal/port/ps2/port.json`: `port/ps2/src/ps2_owner_counters.c` added after `ps2_cache.c`.
- `tests/hcu_ce_owner_counters_main.c` and `tests/test_hcu_ce_owner_counters.py` (new).

## Accounting rules

- Game state: `used` is the CPU game-state cursor, which already includes fixed-pool backing. Object and actor pools are allocated from game state, so their bytes are reported for the pool alone and are never added to the game-state total.
- Object and actor pools: `capacity = maximum_count * datum_size`, `used = actual_count * datum_size`.
- Failures for a pool are `datum_new` calls that found no free slot on a usable array. An unusable array returns before the hook and is not counted.
- Resets for a pool are `data_make_invalid` and `data_delete_all`.
- Tags and BSP: `capacity` is the physical tag and BSP cache size. `used` and `high_water` come from the current and peak publication bytes, failures from refused publications, resets from unloads.

## Evidence

Run from the repo root.

- `gcc -std=gnu99 -Wall -Wextra -Werror -Wno-unused-parameter -DHALO_PS2=1 -Isubmodules/halo-ce-universal/port/ps2/include -Isubmodules/halo-ce-universal/source tests/hcu_ce_owner_counters_main.c` then run: output `hcu_ce_owner_counters: pass`. Covers unbound and bad-argument rejection, game-state used/high/failure/reset, pool capacity/used/high/failure/reset, rejection of unbound arrays and of a game-state binding attempt, tag and BSP pull, audio unavailable, and saturation at `UINT32_MAX` (including a product that does not fit).
- `python3 -I tests/test_hcu_ce_owner_counters.py`: 2 tests, OK.
- ILP32: `gcc -m32 -std=gnu89 -Wall -Werror ... -c ps2_owner_counters.c` compiles cleanly. Linking a 32-bit host binary is not possible here (no 32-bit libgcc), so only the compile is claimed.
- EE cross-compile with `build/toolchain/install/ee/bin/mips64r5900el-ps2-elf-gcc` using the same flag set as `tools/hcu_ps2_link.py` (`-std=gnu89 -Os -mabi=n32 -G0 ...`, with `halo_ps2_prefix.h` and the generated `halo_ps2_msvc_semantics.h`). Exit 0 for each object, outputs in `build/m2-c2-r3-ce-counters/ee/`: `ps2_owner_counters.o`, `data.o`, `objects.o`, `actors.o`, `game_state.o`.
- `git diff --check` on the modified submodule and repo files: clean. The new files were checked for trailing whitespace by hand.

## Limits (C2.6 stays open)

- **Audio requests: not counted.** The PS2 sound adapter (`port/ps2/src/ps2_sound_cache.c`) implements `_sound_cache_sound_request` as a stub that returns `sound != NULL`. There is no request queue to measure slots, high water or drops against. The owner is left unbound rather than invented. This needs a real CE sound-request queue, which belongs to C3.8.
- Tags and BSP capacities come from the physical memory getters. The published image bytes are the cache's own measurement. Neither has been measured on a live PS2 run.
- The object and actor pools are counted through the datum allocator only. Production workload attribution, and the EE runtime sample, are not measured. The actor pool keeps its pre-existing `actors_get_pool_telemetry` counters, unchanged.
- Nothing here runs in PCSX2 or on hardware, and the full CE image is not linked. The host test uses stubs for the cache and memory getters, so it proves the accounting logic and not the integration.
- `ee-world.mk` was not changed. The PS2 CE build reads sources from `port.json`, which now lists the new file.
