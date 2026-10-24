# M2 Step 8 CE actor workload boundary

## Result

The available Step 8 Sidewinder workload is a real CE local split-screen run, but it does not create AI actors or bots. The test fixture starts local player records, and CE's `player_spawn` creates each player's unit through `object_new`. The distinct AI path is `actor_create_for_unit` → `actor_new` → `datum_new(actor_data)`. Treating the current unit count or object-pool use as bot evidence would be incorrect.

The focused source test `python tests/test_hcu_step8_ce_actor_boundary.py` now pins this distinction and fails if the workload silently begins claiming actor coverage without adding the actor creation path. Existing workload-runner and owner-diagnostic tests also pass.

## Existing 4-player workload evidence

An existing Step 8 guest log reports four distinct live local-player units after three CE update ticks on Sidewinder:

| Owner | Capacity | Used / high water | Failed allocations |
|---|---:|---:|---:|
| CE game-state CPU arena | 3,162,112 B (`0x305000`) | 3,107,656 B / 3,107,656 B | 0 |
| CE object memory pool | 1,048,576 B (`0x100000`) | 92,768 B / 92,768 B | 0 |

The CPU game-state arena had 54,456 bytes remaining at the sample. The separately allocated GPU portion is 262,144 bytes (`0x40000`) and is not part of the CPU allocator capacity. The object memory pool is allocated with `game_state_memory_pool_new`, inside the game-state owner; these two owner figures are nested and must not be added. The log records 94 objects (88 active), four distinct unit handles, and clean CE map teardown. A CE work profile says `bots=not-exercised`.

These values describe the local-player scenario workload only. They are not actor or bot high-water values and do not establish the incremental cost of AI actor records, AI units, or bot simulation.

## Why the actor workload is not exercised

- `create_local_players` creates `player_new` records for local controllers.
- `player_spawn` creates a configured player unit with `object_new`; it does not call `actor_create_for_unit`.
- `ai_initialize` calls `actors_initialize`, which reserves the actor datum array through `game_state_data_new("actor", MAXIMUM_ACTORS, sizeof(struct actor_datum))`. That reserves capacity but does not create any actor records.
- `actor_create_for_unit` creates an actor record via `actor_new`, which allocates from `actor_data`. It also attaches the record to an already existing unit. The current fixture has no actor-spawn scenario/script request or actor-count assertion.

Therefore safely extending this workload requires a Sidewinder scenario path that resolves a valid actor variant and attaches/spawns AI actors, followed by explicit live actor/unit count checks. The current source-only inventory is the smallest safe harness improvement in this slice; it does not fabricate an actor count or infer a bot cost from the local-player objects.

## Reproduction and source pins

Focused checks run successfully:

```text
python tests/test_hcu_step8_ce_actor_boundary.py
step8-ce-actor-boundary local_players=real-ce-player-spawn units=object_new ai_actor_records=not-spawned actor_pool=game_state_data_new max_actors=256 actor_objects=not-measured

python tests/test_hcu_step8_mp_workload_runner.py
step8-workload-runner synthetic_profiles=2,4 distinct-unit-gate=pass duplicate-unit-rejection=pass

python tools/test_hcu_step8_memory_owners.py
step8-owner-diagnostics game_state=64/64 game_state_fail=1 object_pool=64/64 object_pool_fail=1 nested_owner=separate dynamic_simulation=unchanged reset=passed
```

CE submodule HEAD: `6933490b2d16bb1c637295b6a0f3880ba23a7d56`. The checkout is dirty; these SHA-256 values pin the inspected file contents:

| Source | SHA-256 |
|---|---|
| `source/main/ps2_m2_ui_lifecycle_test.c` | `d3f36c62a3915c4565b0ab8b21de05f540a650a6cb1d727636a4fc5ec12a21df` |
| `source/game/players.c` | `837b39a3b24997ea7619356cf080d004dfa4b3810950ddce0f298244c1a6eb09` |
| `source/ai/actors.c` | `e5268ce59d8e67dcc573ead661a24c0f0dd4fcf334451f465701217da3cc5829` |
| `source/ai/ai.c` | `9049813558d719d56017a7db70f7a4bf7561fabba89674ecdc42d7b3ad5d0e3c` |
| `source/saved games/game_state.c` | `1cb6f23f0748faf9f1eb0d1d9d33e861e0f629da2a5e5d665194f2e3bc607d7f` |
| `source/objects/objects.c` | `c1a4a9bbea96d8662c9d1dc6454abe248e1f560009a45ff755287b8f0659fd05` |
| `port/ps2/include/halo_ps2_limits.h` | `b8d28b87f33401c9de05762e1ce988b1777ea24d3e1f9f8cc7340837a6cd2529` |
| `tests/test_hcu_step8_ce_actor_boundary.py` | `c3793696fec77e8f193d36feeec7bb3abf407812aaa92ff7376aeb6a071db51b` |

Limits in the pinned PS2 header are `HALO_PORT_GAME_STATE_CPU_SIZE=0x305000`, `HALO_PORT_GAME_STATE_GPU_SIZE=0x40000`, `HALO_PORT_OBJECT_MEMORY_POOL_SIZE=0x100000`, and `HALO_PORT_MAXIMUM_ACTORS=256`. The maximum actor count is a datum-array bound, not a measured actor-object footprint. Workload figures above were read from the existing Step 8 4-player guest log; this focused run did not rebuild or rerun the emulator ELF.
