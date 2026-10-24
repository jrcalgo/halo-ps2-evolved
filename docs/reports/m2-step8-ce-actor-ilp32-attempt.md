# M2 Step 8 CE actor ILP32 fixture

## Status

The initial harness attempt failed compilation because its extractor selected
CE prototypes instead of definitions and duplicated `data_allocation_size`.
That bug is fixed: the current freestanding i386 executable runs the real CE
actor data-array initialization, actor creation/attachment, activation,
deletion, and map-data invalidation bodies. It first validates one bounded
synthetic actor/biped pair, then allocates all **256** configured actor datum
slots, confirms the 257th request is rejected, deletes all 256, and verifies
the live count returns to zero. The actor record is **1,828 B** and the three
actor-related arrays reserve **489,384 B** at initialization. The fixture is
ILP32 host execution, not an R5900/PCSX2 or retail-PS2 run.

The runner retains generated inputs and executable under
`build/hcu-step8-actor-ilp32/`. Its success contract uses a deliberate `int3`
trap after all assertions pass; a different signal/exit status is failure.

## Scope and limitations

The fixture extracts actual CE
`actors_initialize`, `actors_initialize_for_new_map`,
`actor_create_for_unit`, `actor_new`, `actor_attach_unit`, `actor_verify_activation`,
`actor_delete`, `data_initialize`/datum operations, and
`actors_dispose_from_old_map`. It supplies the `actor_variant`/`actor`
definitions and unit as synthetic layout-matched data, uses the production
datum arrays and actor record size under PS2 ILP32 capacity constants, and
attaches one actor then verifies the reverse unit link, actor link, counts,
deletion, and invalidation. A second allocation-only phase fills and drains the
actor datum array using CE's actual `actor_new()` and `datum_new()` functions;
the pool-full check reads CE's `data_array.actual_count`, not fixture counters.
Peripheral type/debug/tag/world services remain
bounded stubs. The object-pool delta is zero because this fixture attaches to
an already-present synthetic biped; it does not create a world object or run
AI perception, path choice, steering, weapon logic, or a full bot tick.
Therefore this is a real actor-record allocation/ownership slice, but still
not integrated multiplayer bot behavior or total bot-workload capacity.

The supported PS2 bounds are game-state CPU arena `0x305000` (3,162,112 B),
game-state GPU arena `0x40000` (262,144 B), object pool `0x100000`
(1,048,576 B), and actor datum capacity 256. The fixture reserves all three
actual actor-related CE datum arrays (`actor`, `swarm`, `swarm component`) at
their compiled CE datum sizes: their combined backing high-water is 489,384 B
of the 3,162,112-B CPU limit. Creating one actor consumes a preallocated
1,828-B datum slot and does not grow the monotonic game-state cursor. Do not
sum the nested actor arrays and actor record, nor count the object pool twice.
The existing four-player PCSX2 run remains local-player-only evidence; this
fixture separately measures actor record initialization/attach/delete, not
an AI tick under the four-player workload.

## Reproduction

```text
python3 tools/test_hcu_step8_ce_actor_ilp32.py
step8-ce-actor-ilp32 actual_ce_functions=actor_new,actor_create_for_unit,actor_attach_unit,actor_delete synthetic_tag_and_biped=1 actor_capacity=256 actor_peak=256 actor_record_bytes=1828 game_state_cpu_capacity=3162112 game_state_high_water=489384 object_pool_capacity=1048576 object_pool_delta=0 actor_cleanup=passed map_data_invalidated=passed
```

Retained executable SHA-256: `2dc6d25a97a50d824600dc4939fc7c014b6eca9459bac06dceb6023874a261fb`;
generated C SHA-256: `b2558572bad01366b4f90ac8be24db41216ca7cf6efc263d73bc448bd338c515`;
prefix SHA-256: `64ab92b861e64fb0f0e01790c1346824c66e484383113197a0bbf82fc2d62a14`.

Passing checks:

```text
python tests/test_hcu_step8_ce_actor_boundary.py
step8-ce-actor-boundary local_players=real-ce-player-spawn units=object_new ai_actor_records=not-spawned actor_pool=game_state_data_new max_actors=256 actor_objects=not-measured

python tests/test_hcu_step8_mp_workload_runner.py
step8-workload-runner synthetic_profiles=2,4 distinct-unit-gate=pass duplicate-unit-rejection=pass

python tools/test_hcu_step8_memory_owners.py
step8-owner-diagnostics game_state=64/64 game_state_fail=1 object_pool=64/64 object_pool_fail=1 nested_owner=separate dynamic_simulation=unchanged reset=passed
```

## Source pins

CE submodule HEAD: `6933490b2d16bb1c637295b6a0f3880ba23a7d56` (working tree dirty).
Inspected source pins from the boundary report:

| Source | SHA-256 |
|---|---|
| `source/ai/actors.c` | `e5268ce59d8e67dcc573ead661a24c0f0dd4fcf334451f465701217da3cc5829` |
| `source/memory/data.c` | `db97ad491207a513f6d6015f9c2fbd2c2bd7a83e2d5698be4ab8a8bf3ea773e9` |
| `port/ps2/include/halo_ps2_limits.h` | `b8d28b87f33401c9de05762e1ce988b1777ea24d3e1f9f8cc7340837a6cd2529` |

Fixture SHA-256 values are recorded in the handoff with the final tree state.

Runner SHA-256: `987af62554e1cc95b299ce361d743300c617f96a7cac24028c1a338c4da97d88`.
For comparison, Halo-64's [`n64_game.c:202-204`](../../submodules/halo-64/port/n64/game/n64_game.c#L202)
explicitly leaves AI out of its game initialization; that is an N64 resource
cut, not parity evidence or a design to copy for the PS2 port. This fixture
therefore measures retained CE actor allocation instead of using Halo-64's
omitted-AI behavior as the expected result.
