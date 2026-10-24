# Step 8 multiplayer dynamic pool pressure: CE ownership bound

## Finding

The current sources do not expose a per-map dynamic simulation high-water, so no honest byte estimate for bots, co-op, projectiles, effects, and moving objects can be derived from the 13 scenario files alone. The actionable source-backed bound is the allocator and fixed-pool ownership:

| Owner | Capacity / route | Accounting result |
|---|---:|---|
| PS2 dynamic simulation | 2,621,440 B (`dynamic_pool`) | `hcu_memory_bind_parent_v2()` binds the entire region to CE's compatibility `malloc` arena. Allocation is 16-byte aligned and monotonic; frees inside that arena are no-ops. |
| CE object payload pool | 1,048,576 B | `objects_initialize()` allocates it via `game_state_memory_pool_new()`, hence inside `HALO_PORT_GAME_STATE_SIZE` in `resident_gameplay`. Do not add it to dynamic simulation while this route remains. |
| Actor / prop / swarm arrays | actors 256, props 768, swarms 32, components 256 | Each is created by `game_state_data_new()` and belongs to game state, not the dynamic malloc arena. These are datum-count caps, not byte high-water. |
| PS2 object slots | 2,048 per map | Header/data-array capacity; not a byte count and not evidence all slots are simultaneously active. |
| PS2 effect family caps | 256 effects, 1,024 particles, 64 particle systems, 256 contrails | Fixed count limits only; storage ownership and live bytes are not surfaced as a combined pool ledger. |

The isolated 1 MiB object memory pool is 40% of the 2.5 MiB dynamic arena by byte capacity, but that is only a hypothetical subtraction if the pool is rehomed. Under the present CE call route it is already charged to the game-state block in `resident_gameplay`; charging it again would double count. The rest of the 2.5 MiB arena has no published consumer ledger or high-water, and no source or test currently proves that the remaining 2,621,440 B accommodates simultaneous match allocations.

This is scoped to exactly the 13 stock multiplayer maps and their multiplayer bot/co-op workload. Campaign content is excluded. The Step 8 map package/query fixture covers map ownership and selected BSP consumers; it explicitly does not instantiate the dynamic live-match owners, so its map-cycle high-water must not be reused as a simulation measurement.

## Source evidence

- Budget v2 fixes `dynamic_simulation` at 2,621,440 B: [`config/memory-budget.json`](../../config/memory-budget.json#L4-L20).
- The memory map says the CE object pool is nested in the game-state provider and must not be charged twice; it records dynamic high-water as unknown: [`config/hcu-ps2-memory-map.json`](../../config/hcu-ps2-memory-map.json#L1-L8) and [line 80](../../config/hcu-ps2-memory-map.json#L80).
- The binder allocates `HALO_PORT_GAME_STATE_SIZE` from `resident_gameplay`, binds dynamic-region base/capacity to `physical_memory_bind_malloc_arena()`, then allocates validator claims in resident gameplay: [`src/stream/hcu_memory_bind.c`](../../src/stream/hcu_memory_bind.c#L19-L67).
- The PS2 compatibility allocator aligns each request to 16 bytes, advances `malloc_used`, rejects overflow, and does not reclaim arena pointers on free: [`ps2_memory.c`](../../submodules/halo-ce-universal/port/ps2/src/ps2_memory.c#L288-L331).
- PS2 pool constants are explicit in [`halo_ps2_limits.h`](../../submodules/halo-ce-universal/port/ps2/include/halo_ps2_limits.h#L18-L50).
- CE declares `OBJECT_MEMORY_POOL_SIZE` from the port constant and sets garbage thresholds as 5%, 10%, and 20% of that size: [`objects.h`](../../submodules/halo-ce-universal/source/objects/objects.h#L25-L37).
- Runtime initialization calls `game_state_memory_pool_new("objects", OBJECT_MEMORY_POOL_SIZE)` outside editor mode: [`objects.c`](../../submodules/halo-ce-universal/source/objects/objects.c#L1040-L1063). That helper obtains the pool bytes with `game_state_malloc()`: [`game_state.c`](../../submodules/halo-ce-universal/source/saved%20games/game_state.c#L549-L566) and [pool constructor](../../submodules/halo-ce-universal/source/saved%20games/game_state.c#L943-L955).
- Actor, swarm, and swarm-component arrays use `game_state_data_new()` in `actors_initialize()`: [`actors.c`](../../submodules/halo-ce-universal/source/ai/actors.c#L560-L577). Props do the same: [`props.c`](../../submodules/halo-ce-universal/source/ai/props.c#L89-L104).
- The 13-map candidate only ran load/query/unload cycles and says it did not exercise simultaneous players/bots/weapons/effects/animation in the 2.5 MiB pool: [`mp-step8-tail-inclusive-candidate-2026-10-22.md`](mp-step8-tail-inclusive-candidate-2026-10-22.md#L1-L10) and [limits](mp-step8-tail-inclusive-candidate-2026-10-22.md#L55-L67).

## Smallest useful runtime fixture

Instrument the real CE allocation boundaries in the combined no-bootstrap PS2 image with per-owner current/peak bytes and allocation-failure counts. Keep object-pool bytes separate from the dynamic allocator unless its allocation route is deliberately changed. Use one source-pinned MP map per row, then exercise a shared workload on all 13: four local players, configured maximum bots, co-op encounter spawn/cleanup, vehicle enter/exit, repeated projectile and grenade/effect lifecycles, and map unload/reload. Record source map SHA, ELF SHA, memory-budget hash, player/bot count, owner peaks, and whether frees/reloads restore allocator headroom. Run on PCSX2 interpreter and recompiler first, then target-sized EE if available.

The fixture must fail if an allocation returns null, if a count pool fills, if the dynamic arena cursor exceeds 2,621,440 B, or if reset/transition leaves the cursor elevated. A passing diagnostic would establish only that exact workload's peak; it would not prove arbitrary custom-game settings or Step 8 closure.

## Reproduction and status

This report is a source-backed arithmetic/ownership audit. No executable per-map high-water artifact exists: the current PS2 allocator exposes no peak counter, and the retained 13-map candidate run omits live dynamic simulation. Scenario placement counts would not substitute for heap bytes or simultaneous lifetime evidence. Step 8 remains open until the live fixture supplies those measurements alongside the other map/render/audio owners.
