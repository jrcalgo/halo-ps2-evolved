# C2 actor datum pool telemetry slice (2026-10-23)

## Result

Added retained actor-owner counters in CE `actors.c` and a read-only snapshot API. The snapshot reports configured actor datum capacity, maximum simultaneous `actual_count`, failed actor datum allocations, and calls to `actors_initialize_for_new_map`. Counter storage is static and does not change `struct actor_datum`, `struct data_array`, game-state allocation size, or game-state cursor usage.

The allocation failure counter increments only when `actor_new` reaches `datum_new(actor_data)` and the datum allocator returns `NONE`. It does not include distributed-client rejection, invalid/missing actor definitions, or actor-type validation failures. High-water is retained across map resets until `actors_initialize`; reset count records actor-array revalidation for a new map. Dispose/invalidation is not counted as a reset.

## Focused evidence

`python3 tools/test_hcu_step8_ce_actor_ilp32.py` passed. The existing freestanding ILP32 fixture now queries the retained producer at initialization, after one map reset, at full 256-slot occupancy, after a rejected 257th allocation, and after a second map reset. It observed capacity 256, peak occupancy 256, one datum-allocation failure, and two reset calls. It also continued to assert clean actor deletion and invalidation. The fixture is synthetic and proves the selected CE actor datum operations only; it is not a game workload, bot-spawn parity, EE runtime sample, or C2.6 completion.

The pre-existing fixture reported unchanged actor record size (1,828 B) and fixed game-state high-water (489,384 B of 3,162,112 B). Actor datum slots are already included in that game-state backing; do not add a separate actor-array byte total to the game-state figure. Actor high-water is a count, not an additional memory owner.

## Scope limits

- The exported getter provides a retained source value but is not yet wired into a production owner telemetry log or guest snapshot.
- Counts are cumulative from `actors_initialize`, with reset count cumulative across map initializations; no per-map peak history is retained.
- This does not measure actor-owned unit/object allocations, props, swarms, effects, AI update/perception/pathfinding cost, failures in other datum arrays, or target EE CPU/RAM high-water.
- It does not make C2.6 complete; other owner telemetry gaps remain as listed in `m2-c2-owner-telemetry-audit-2026-10-23.md`.

## Documentation reviewed

Reviewed the Halo PS2 architecture/engine/BSP documentation, Halo CE cache documentation, N64 port expansion notes, PS2SDK docs index and peripheral references, and PS2 client protocol docs. The PS2SDK references cover USB mass storage, IEEE1394 disk/manager behavior, and a camera device; the client docs cover ps2link transport. They describe separate I/O/runtime domains and provide no producer for CE actor datum pool metrics. The N64 notes are comparative and are not used as PS2 capacity evidence.

## Hashes

After the focused test, the fixture ELF was retained at `build/hcu-step8-actor-ilp32/actor_fixture`; its SHA-256 is recorded by the test output. Source, test, and report SHA-256 values are recorded with the task handoff.
