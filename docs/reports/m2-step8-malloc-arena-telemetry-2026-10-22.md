# Step 8 PS2 dynamic allocator telemetry

## Result

Added opt-in allocator statistics behind `HALO_PS2_STEP8_MEMORY_DIAGNOSTIC`: capacity, current monotonic bytes used, high-water bytes, and failed arena allocations. In ordinary builds the diagnostic fields, API, and static counters are absent. The counters reset when a new physical-memory allocation interval begins and on teardown. The PS2 preboot SDK-heap path remains separate; overflow is rejected before it can reach that fallback.

`python3 tools/test_hcu_ps2_malloc_diagnostic.py` passed. The host fixture verifies preboot allocations remain untracked, 16-byte alignment, 48-byte high-water after requests of 17 and 1 bytes, monotonic behavior after free, arena-exhaustion and overflow failures, and reset after free/rebind. `git diff --check` passed. An R5900 compile check was unavailable because neither `mips64r5900el-ps2-elf-gcc` nor `ee-gcc` is installed in this environment.

The telemetry measures only the CE compatibility malloc arena mapped to `dynamic_simulation`. It does not include CE `game_state` allocations, the object memory pool, actor/prop/swarm arrays, graphics allocations, or GS/IOP stores. Thus it is instrumentation for a later live-match fixture, not evidence that the 2,621,440-byte pool fits bots, co-op, weapons, effects, or all 13 multiplayer maps.

## Source references and hashes

- PS2 allocation, alignment, and overflow route: [`ps2_memory.c:304-367`](../../submodules/halo-ce-universal/port/ps2/src/ps2_memory.c#L304)
- The diagnostic-only API and result fields: [`physical_memory_map.h:48-64`](../../submodules/halo-ce-universal/source/cache/physical_memory_map.h#L48)
- Separate game-state object-pool ownership: [`objects.c:1040-1063`](../../submodules/halo-ce-universal/source/objects/objects.c#L1040), [`game_state.c:549-566`](../../submodules/halo-ce-universal/source/saved%20games/game_state.c#L549)
- Host fixture: [`hcu_ps2_malloc_diagnostic_main.c`](../../tests/hcu_ps2_malloc_diagnostic_main.c)
- Reproduction: `python3 tools/test_hcu_ps2_malloc_diagnostic.py`

| File | SHA-256 |
|---|---|
| `port/ps2/src/ps2_memory.c` | `2d4260a575770607273c5f0d4b8bda172e60558009eee163e7bd004149fc3d7f` |
| `source/cache/physical_memory_map.h` | `b57f014f273e2344a79b3bf4c83fb6701988049a932bc7361ea9d1fa3bef7e68` |
| `tests/hcu_ps2_malloc_diagnostic_main.c` | `4a9e56ed4b5c5b5df8a4921363a941e3e7402bbb0479181ebbaa76a3bc00359b` |
| `tools/test_hcu_ps2_malloc_diagnostic.py` | `ccdb8fa8f378b10f2e6409cbc1d432bd5d49d8b92dee779a60922d103e9b1ee7` |

The added compatibility-alignment and overflow-order guard preserves prior behavior and is test-covered. This subcheck does not close Step 8: target/runtime high-water, non-malloc owner peaks, maximum supported players/bots/co-op, rendering/DMA overlap, and target performance remain outstanding.
