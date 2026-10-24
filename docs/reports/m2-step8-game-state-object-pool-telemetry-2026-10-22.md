# Step 8 game-state and object-pool diagnostic counters

Date: 2026-10-22  
Disposition: opt-in measurement primitive and focused host fixture only. This is not a multiplayer capacity result.

## Result

The HCU PS2 CE sources now expose separate diagnostic snapshots for the fixed CPU game-state arena and the CE fixed object-memory pool under `HALO_PS2_STEP8_MEMORY_DIAGNOSTIC` ([game-state counters/getter](../../submodules/halo-ce-universal/source/saved%20games/game_state.c#L181), [object-pool counters/getter](../../submodules/halo-ce-universal/source/objects/objects.c#L205), [diagnostic-only API](../../submodules/halo-ce-universal/port/ps2/include/ps2_step8_memory_owners.h#L1)). Each snapshot has capacity, current used extent, high-water extent, and rejected-allocation count. The compatibility `malloc` arena remains a third, separate owner ([allocator telemetry](m2-step8-malloc-arena-telemetry-2026-10-22.md#L1)); this instrumentation does not charge or mutate it.

The game-state telemetry starts at `game_state_initialize()` and ends at `game_state_dispose()` ([lifecycle hooks](../../submodules/halo-ce-universal/source/saved%20games/game_state.c#L285), [initialization](../../submodules/halo-ce-universal/source/saved%20games/game_state.c#L1090)). Its monotonic cursor includes backing allocated to game-state data arrays and the CE object pool itself. The object-pool telemetry starts after `objects_initialize()` creates that pool and ends at `objects_dispose()` ([pool lifecycle](../../submodules/halo-ce-universal/source/objects/objects.c#L1110), [pool reset](../../submodules/halo-ce-universal/source/objects/objects.c#L1220)); its bytes are nested inside the game-state backing, so **do not add the two owners together**. Its `used_bytes` follows the memory pool's current cursor/highest-address extent (`memory_pool_get_used_size()`), including any holes below the last live block; it is a footprint/fragmentation measure, not a sum of live payload sizes. Map transitions keep the lifetime counters active and may lower current object-pool extent after frees; high-water remains for the subsystem lifetime.

`python3 tools/test_hcu_step8_memory_owners.py` passed:

```text
step8-owner-diagnostics game_state=64/64 game_state_fail=1 object_pool=64/64 object_pool_fail=1 nested_owner=separate dynamic_simulation=unchanged reset=passed
```

The test compiles extracted real CE accounting/allocation functions in a native host fixture with mock owner primitives. It checks game-state exhaustion counting and reset/restart, object allocation exhaustion counting and reset, separate/nested ownership, and that the fixture's `dynamic_simulation` accounting sentinel is unchanged. It is not a complete game-state or gameplay allocator simulation.

## R5900 compile and production-profile check

Both changed CE translation units compiled with the installed R5900 compiler, `mips64r5900el-ps2-elf-gcc (GCC) 15.2.0`, under the HCU PS2 closure flags, once with the normal profile and once with `HALO_PS2_STEP8_MEMORY_DIAGNOSTIC`:

| Translation unit | Normal `.text` / `.bss` | Diagnostic `.text` / `.bss` | Diagnostic-only delta |
|---|---:|---:|---:|
| `game_state.c` | 13,024 / 10,276 B | 13,276 / 10,288 B | +252 / +12 B |
| `objects.c` | 47,224 / 16 B | 47,592 / 28 B | +368 / +12 B |
| Total | 60,248 / 10,292 B | 60,868 / 10,316 B | **+620 / +24 B** |

The normal-profile objects contain no `ps2_step8_*` symbols or counter storage. The diagnostic profile's 24-byte `.bss` delta is the six 32-bit counters/active flags (three per owner); 620 bytes of additional `.text` are the guarded instrumentation and getters in these two objects. These are object-level deltas, not a linked-ELF or runtime memory report. The declarations/counters/instrumentation are all preprocessor-guarded; no structure layout or production ABI change was made. The whole PS2/gameplay ELF was not rebuilt with this new define, and no PCSX2 or retail EE workload was run.

## Ownership and limits

- Production capacities remain unchanged: PS2 game-state CPU backing is `HALO_PORT_GAME_STATE_CPU_SIZE` = `0x305000` (3,162,112 B) and the CE object pool is `HALO_PORT_OBJECT_MEMORY_POOL_SIZE` = `0x100000` (1,048,576 B) ([PS2 limits](../../submodules/halo-ce-universal/port/ps2/include/halo_ps2_limits.h#L18)); the separate `dynamic_simulation` region is 2,621,440 B ([memory budget](../../config/memory-budget.json#L4)).
- Game-state failures count requests rejected by the fixed CPU bound, including negative/overflowing requests before pointer arithmetic. Object-pool failures count failed object payload allocation and block-growth attempts at the instrumented CE call sites. They do not count datum-slot exhaustion, AI/prop/swarm array allocation failures, or unrelated `game_state_malloc` consumers separately.
- No API sums owners. The object-pool backing is already included in the game-state cursor; the compatibility malloc arena and its counters are independent. Avoid double counting.
- The host fixture proves only those focused branches. It does not instantiate a map, player, bot, co-op scenario, vehicle, weapon, projectile, particle workload, or renderer; it does not establish all allocation sites are instrumented or that the measured capacities are sufficient.
- The next capacity evidence is a real supported multiplayer fixture that snapshots these owners and the compatibility arena through initialization, map transition, player/bot/co-op creation, representative weapon/effect churn, cleanup/reload, and failure handling on the 13-map set. Record current/high-water/failures per owner and keep game-state/object-pool nesting explicit. Do not claim 1–4 player or bot/co-op support from this primitive alone.

## Exact changed artifacts

| File | SHA-256 |
|---|---|
| [`game_state.c`](../../submodules/halo-ce-universal/source/saved%20games/game_state.c) | `1cb6f23f0748faf9f1eb0d1d9d33e861e0f629da2a5e5d665194f2e3bc607d7f` |
| [`objects.c`](../../submodules/halo-ce-universal/source/objects/objects.c) | `c1a4a9bbea96d8662c9d1dc6454abe248e1f560009a45ff755287b8f0659fd05` |
| [`ps2_step8_memory_owners.h`](../../submodules/halo-ce-universal/port/ps2/include/ps2_step8_memory_owners.h) | `e60562865b86c69c23ff25838de228f8fef34fa404fb3b31e912d09e4e569b15` |
| [`test_hcu_step8_memory_owners.py`](../../tools/test_hcu_step8_memory_owners.py) | `3585980114bf92c57f5f769377a86daf2ad618ada0f57d3c9b26c838a727d670` |

The focused host test and R5900 compile checks establish the diagnostic plumbing only. Step 8 remains open for runtime owner high-water, combined map/render/gameplay load, target placement/timing, and supported multiplayer workload evidence.
