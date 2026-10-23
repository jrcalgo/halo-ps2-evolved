# M2 Step 8 stock-MP vehicle-seat actor oracle

## Status

**PASS.** All 13 stock multiplayer maps were walked with
compiler-derived CE offsets. Each map has zero `actr` tags, zero encounters,
three hollow `actv` stubs, and zero vehicle seats whose
`built_in_actor_reference.index` is not `NONE`. Sidewinder's single actor
palette slot is also unresolved. The freestanding ILP32 fixture relocates the
three Sidewinder vehicle definitions and runs the real CE `unit_new` seat scan
plus `ai_place_pending_mounted_weapons`. Both paths leave the actor datum array
empty and never enter `actor_place`.

This is not bot coverage. Stock MP maps do not contain a resolved actor/unit
pair that CE can place. Do not fill those references synthetically and call
that the retail spawn path.

## Census

| map | actr | actv | encounters | palette | wired seats | map SHA |
|---|---:|---:|---:|---:|---:|---|
| `beavercreek` | 0 | 3 | 0 | 0 | 0 | eaf90b2abc4f |
| `bloodgulch` | 0 | 3 | 0 | 0 | 0 | 9eb0374cbe45 |
| `boardingaction` | 0 | 3 | 0 | 0 | 0 | 34ddf961973b |
| `carousel` | 0 | 3 | 0 | 0 | 0 | 3e4be29a7952 |
| `chillout` | 0 | 3 | 0 | 0 | 0 | 52bc3e23b914 |
| `damnation` | 0 | 3 | 0 | 0 | 0 | 87bd92c1821f |
| `hangemhigh` | 0 | 3 | 0 | 0 | 0 | e3e4b25ed361 |
| `longest` | 0 | 3 | 0 | 0 | 0 | e045b0843f4a |
| `prisoner` | 0 | 3 | 0 | 0 | 0 | 85ff2fdc117b |
| `putput` | 0 | 3 | 0 | 0 | 0 | efbe723188f3 |
| `ratrace` | 0 | 3 | 0 | 0 | 0 | 577886f949f2 |
| `sidewinder` | 0 | 3 | 0 | 1 | 0 | 995561a68c8c |
| `wizard` | 0 | 3 | 0 | 0 | 0 | 978539ff7008 |

The three `actv` paths on every map are `vehicles\warthog\warthog gunner`,
`vehicles\ghost\ghost pilot`, and `vehicles\scorpion\scorpion pilot`. Their actor, unit, and ranged
weapon references have `index == NONE` and a null name pointer. Vehicle seats
keep labels (`W-gunner`, `G-driver`, `scorpion-driver`, ...) but the built-in
actor index is `NONE`, so `unit_new` never calls
`ai_create_mounted_weapons_for_unit`.

## ILP32 fixture

Command: `python3 tools/audit_mp_vehicle_seat_actors.py`

- actual CE functions: ai_create_mounted_weapons_for_unit, ai_place_pending_mounted_weapons, actors_initialize, actors_dispose_from_old_map
- `actor_place`: call-count-probe-not-entered
- actor record: 1828 B
- game-state high-water: 489384 B of the 3,162,112-B CPU arena
- executable SHA-256: `bf6fbeca5a46c1f0861fd7c5a08b151b9ecca980a36aea9409637fdf75e47523`
- retained: `build/step8-vehicle-seat-actors`

The fixture force-queues all three Sidewinder vehicles after the seat scan
reports zero, then runs `ai_place_pending_mounted_weapons` so the NONE seat
guard is executed against relocated Xbox seat bytes. `actor_place` is a
call-count probe because the retail seats never reach it; calling the real
body with a hollow `actv` would dereference `actor_definition_get(NONE)`.

## Limits

No infantry encounters, no resolved vehicle-seat gunners, no actor-owned
objects/weapons, no AI tick, and no PCSX2/EE measurement. Bots remain in
product scope and still need a sourced spawn path that is not present in these
13 cache files. Step 7/8 stay open. Arenas and the reserve are unchanged.
