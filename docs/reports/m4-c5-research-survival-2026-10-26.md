# M4 C5 research: survival state machine and population bounds (2026-10-26)

Read-only research for C5 steps 6 and 7 of `plans/7.hcu-remake-m2-m4.md`. No source,
plan, or other documents were modified. Sources read: every file under
`submodules/*/docs`, `submodules/halo-ce-universal/AGENTS.md`, and the C5 section of
the plan. The halo-64 survival code was read in full
(`submodules/halo-64/port/n64/game/n64_firefight.c`). The CE capacity and AI code was
checked by constant and function name, not read end to end.

## 1. Sources and what they say about survival

| Source | Survival / wave content | Relevance |
| --- | --- | --- |
| `submodules/halo-64/port/n64/game/n64_firefight.c` | Full wave system: `n64_firefight_begin`, `n64_firefight_tick`, `start_wave`, `wave_size`, `wave_kind`, `spawn_covenant`, `count_lives`, `body_fell`, `n64_firefight_results`. Waves of five per set, lives, bodies, spawn timer. | Behavioural precedent only. Its caps are N64 cuts and must not be imported. |
| `submodules/halo-ce-universal` | No survival mode, no wave code, no intermission. `grep -i survival/wave/intermission` hits only `port/linux/NETCODE.md` and unrelated strings. | CE has no survival rules to copy; the state machine is new HCU work. |
| `submodules/halo-ce-universal/port/linux/game/coop_enemies.c` | Co-op enemy growth: `coop_enemies_extra_count` reserves room as `MAXIMUM_ACTORS - COOP_ENEMIES_LEVEL_ACTORS - actor_data->actual_count`. | The one place CE already does "reserve before admission" for actors. Survival should use the same shape but without the level-actor term. |
| `submodules/halo-ce-universal/port/linux/game/coop_enemies.c` (`COOP_ENEMIES_MAXIMUM_GROWTH`, `MAXIMUM_RIDING_VEHICLES`, `MAXIMUM_SEATED_RIDERS`, `MAXIMUM_KEPT_RIDERS`) | Growth and rider caps for co-op enemies. | Shows CE-side caps already bound riders and vehicles separately from the actor pool. |
| `submodules/halo-ps2/docs/04-roadmap.md` | Phase 7 `c20` stress and Phase 6 hardening; no survival, no bot or wave content. | Context only. |
| `plans/7.hcu-remake-m2-m4.md` C5 items 6 and 7 | The normative rules this report addresses. | Governing text. |
| `submodules/halo-ce-universal/AGENTS.md` | Port conventions: `port:` comments, netcode version bump on changes to anything machines must agree on, no `HALO_LINUX` define. | Survival states that machines must agree on (wave index, roster, seed) need the netcode rules. |
| `submodules/halo-ce-universal/docs/custom_edition_caches.md`, `docs/mods.md` | Map and mod loading; no population or spawn content. | Not relevant to C5 steps 6-7. |
| `submodules/halo-ps2/CLAUDE.md` (and the other submodule docs) | PS2 budget notes: no heap after level load, 30 Hz tick. | Constrains the design: all survival storage is fixed-size. |

## 2. Capacity constants (CE source, Xbox figures with PS2 figures)

Names are from `port/linux/include/halo_port_capacity.h` (desktop values, Xbox figure in
parentheses in that header) and `port/ps2/include/halo_ps2_limits.h` (PS2 port values).
`source/ai/actors.h` maps them to `MAXIMUM_ACTORS`, `MAXIMUM_SWARMS`,
`MAXIMUM_SWARM_COMPONENTS`.

| Constant | Desktop (Xbox) | PS2 (`halo_ps2_limits.h`) | Use |
| --- | --- | --- | --- |
| `MAXIMUM_ACTORS` (`HALO_PORT_MAXIMUM_ACTORS`) | 1024 (256) | 256 | Actor datum pool, `actor_new`, `actor_data` |
| `MAXIMUM_PROPS` (`HALO_PORT_MAXIMUM_PROPS`) | 8192 (768) | 768 | Knowledge of units around actors |
| `MAXIMUM_SWARMS` (`HALO_PORT_MAXIMUM_SWARMS`) | 128 (32) | 32 | `actor_swarm_cache_new`, error "exceeded MAXIMUM_NUMBER_OF_ACTIVE_SWARMS" |
| `MAXIMUM_SWARM_COMPONENTS` | 1024 (256) | 256 | `actor_swarm_cache_new`, `actor_swarm_attach_unit` |
| `MAXIMUM_UNIT_INDICES_PER_SWARM` | 16 (fixed, `actors.h:266`) | 16 | Units per swarm; `actor_new` and `actor_swarm_attach_unit` check it |
| `MAXIMUM_COMPONENT_INDICES_PER_SWARM` | 16 (fixed, `actors.h:267`) | 16 | Components per swarm |
| `MAXIMUM_SEATS_PER_UNIT` (`tag_schema_objects.c`) | 16 | 16 | Seats per vehicle (mounted occupant bound) |
| `MAXIMUM_OBJECTS_PER_MAP` (`HALO_PORT_MAXIMUM_OBJECTS_PER_MAP`) | 8192 (2048) | 2048 | Object datum pool; units, weapons, projectiles, drops, corpses all draw from it |
| `GARBAGE_LIMIT_FREE_OBJECTS_CRITICAL/TRIGGER/TARGET` (`objects.h`) | pool / 40, / 20, / 10 | same formula | Object garbage thresholds |
| `HALO_PORT_MAXIMUM_EFFECTS` | 2048 (256) | 256 | Effect datum pool |
| `HALO_PORT_MAXIMUM_EFFECT_LOCATIONS` | 4096 (512) | 512 | Effect locations |
| `HALO_PORT_MAXIMUM_PARTICLES`, `..._PARTICLE_SYSTEMS`, `..._SYSTEM_PARTICLES` | 8192 / 256 / 4096 (1024 / 64 / 512) | 1024 / 64 / 512 | Particle pools |
| `HALO_PORT_MAXIMUM_LIGHTS_PER_MAP`, `..._GAME_LOOPING_SOUNDS` | 4096 / 4096 (896 / 1024) | 896 / 1024 | Light and looping sound pools |
| `HALO_PORT_MAXIMUM_NETWORK_PLAYERS` | 128 (desktop) | 16 | Player datum bound; not a survival cap |
| `MAXIMUM_DROPPED_VEHICLES` (`network_coop.c`) | 5 | n/a | Co-op drop bound, not survival |
| `MAXIMUM_DECALS_PER_MAP` | 2048 | n/a | Decal cap, bounded separately (decals are not in the C5 list but are a population term) |

No dedicated CE cap for projectiles or corpses was found. Both are objects and draw from
`MAXIMUM_OBJECTS_PER_MAP`. Survival therefore needs its own budgets for them (section 6).

Notable points:

- `MAXIMUM_UNIT_INDICES_PER_SWARM` and `MAXIMUM_COMPONENT_INDICES_PER_SWARM` are 16 each
  and fixed. A single swarm therefore expands by up to 16 units or components, regardless
  of pool size.
- The PS2 actor pool is 256. Its swarm pool is 32, its component pool 256.
- CE's own `coop_enemies_extra_count` reserves against `MAXIMUM_ACTORS` minus a 256-actor
  level term. Survival must not use that term: it should remove map encounters, or it
  will consume the pool.

## 3. Functions relevant to population

| Function | File | What it does | Population effect |
| --- | --- | --- | --- |
| `actor_new` | `source/ai/actors.c` (~2251) | Allocates an actor datum; refused on a network-distributed client | One actor per actor-carrying unit |
| `actor_place` | `source/ai/actors.c` (~2720) | Places an actor on a unit | Same as above |
| `actors_spawn_from_unit` | `source/ai/actors.c` (~2899) | Secondary spawn from a dying or triggering unit, `actor_count` new actors | Secondary-spawn expansion; count comes from the tag |
| `actor_swarm_cache_new` | `source/ai/actors.c` (~3189) | Creates a swarm; errors past `MAXIMUM_NUMBER_OF_ACTIVE_SWARMS` | Swarm slot |
| `actor_swarm_attach_unit` | `source/ai/actors.c` (~3656) | Adds a unit to a swarm; bounded by `MAXIMUM_UNIT_INDICES_PER_SWARM` and components | Swarm member expansion |
| `actor_swarm_unit_died` | `source/ai/actors.c` (~3467) | Removes a dead swarm member | Shrinks a swarm |
| `actor_swarm_cache_delete`, `actor_swarm_detach_from_unit` | `source/ai/actors.c` (~888, ~821) | Frees swarms | Release |
| `actor_delete`, `actor_delete_props` | `source/ai/actors.c` (~3129, ~3115) | Actor cleanup | Release |
| `encounter_spawn_actor` | `source/ai/encounters.c` (~1846) | Squad spawn; increments encounter and squad counts | Map encounters only, not survival |
| `ai_scripting_spawn_actor` | `source/ai/ai_script.c` (~3013) | Script spawn | Scripted spawns |
| `ai_scripting_swarm_count`, `ai_scripting_nonswarm_count` | `source/ai/ai_script.c` (~2008, ~2014) | Counts of swarm and non-swarm actors | Useful for the active-enemy count |
| `unit_enter_seat`, `unit_set_seat`, `unit_find_nearby_seat` | `source/units/units.h` (~895, ~856, ~876) | Seat occupancy | Mounted occupants become actors |
| `unit_seat_filled` | `source/units/units.h` (~933) | Seat occupancy test | Mounted occupant count |
| `coop_enemies_extra_count` | `port/linux/game/coop_enemies.c` | Co-op growth; reserves against `MAXIMUM_ACTORS` | Precedent for reserve-before-admission |
| `game_engine_end_game` | `source/game` | Ends the game | Survival match end |
| `actor_swarm_unit_died` / `actors_spawn_from_unit` path | `source/ai/actors.c` | Death-side expansion | Must be counted in the same tick as the death |

## 4. N64 Firefight: what to borrow and what not to import

| N64 item (`n64_firefight.c`) | Value | Use in HCU | Reason |
| --- | --- | --- | --- |
| `MAXIMUM_ENEMIES` | 12 | Do not import | N64 cap |
| `alive_limit()` | 5 or 6 by player count | Do not import the number. Use the qualified active limit | The spec requires one active-limit-sized batch per wave, qualified on PS2 |
| `MAXIMUM_BODIES` | 16 | Do not import the number. Keep a bounded corpse budget | Corpse budget is a PS2 measurement |
| `BODY_TICKS` | 5 s | Compare against the plan's own corpse policy | Not a survival rule in the spec |
| `TICKS_BETWEEN_WAVES` | 6 s | Do not import. The spec's intermission is 5 s | Spec value wins |
| Break at start | 3 s | Do not import unless the spec requires it | Spec says `setup` then waves |
| `starting_lives` | 10, 7, 5, 3 by difficulty | Do not import. Spec says respawn between waves only, no team lives | Spec model differs |
| `wave_size` | `(4 + 2*in_set + 3*set) * scale * (1 + 0.2*(players-1))` | Replace with the spec's "one active-limit-sized batch per wave" and fixed templates | Spec specifies the batch |
| `wave_kind` | Roll by set and wave index | Replace with cycled wave templates | Spec says templates cycle indefinitely without retained arrays |
| `TICKS_BETWEEN_SPAWNS` | 20 ticks | Batch semantics differ, so not needed for batch admission. Keep only if spawn staggering is needed for PS2 frame time | Qualification decides |
| `count_lives` | Team lives; respawn timer forced to 2 s for out players | Not compatible with spec. Spec: respawn dead players between waves only, and zero living humans ends the match | Reject this model |
| `unit_alive` / `covenant_celebrate` | Death handling | Keep the idea of resolving deaths before admission | Needed for same-tick ordering |
| Path state (47 KB, `firefight_path_state`) | Malloc'd only while playing | Do not import the malloc. PS2 forbids heap after level load | Preallocate or drop |
| `ai_debug.path_disable_obstacle_avoidance` | Set on begin | Keep as a reference for the PS2 AI budget | Decision belongs to C5 AI work |

Ordering point to take from the N64 code: `count_lives` runs at the start of the tick,
before enemy deaths are processed. The spec requires the end-of-match check after all
deaths resolve, with a human count of zero ending the match even if an enemy also died
that tick. The N64 order would end the match one tick late, or not at all if an enemy
death in the same tick is processed first. Do not copy that order.

## 5. Cross-analysis: CE vs N64 vs spec

| Topic | CE (`halo-ce-universal`) | N64 (`halo-64`) | Spec (C5 6-7) | Design decision |
| --- | --- | --- | --- | --- |
| Difficulty | CE Normal (no survival-specific table in CE) | Four levels with scales | CE Normal | Use CE Normal; N64 scales are not imported |
| Seed | Fixed qualification seeds (plan) | `n64_ticks()` seed | Fixed qualification seeds | Use fixed seeds; the seed is part of simulation state |
| States | None | Implicit (`break_timer`, `over`) | `setup`, `active_wave`, `intermission`, `game_over` | Explicit enum, one transition function |
| Batch | No batch concept | Incremental spawn up to a limit | One active-limit-sized batch per wave | Admit the batch in one step after reservation |
| Intermission | None | 6 s, plus 3 s start | 5 s | 5 s |
| Templates | None | Computed per wave | Cycle wave templates indefinitely | Fixed template table, index modulo count, no completed-wave arrays |
| Respawn | Normal CE rules | Respawn timer forced to 2 s for out players | Respawn dead players between waves only | Respawn at wave boundary only |
| End | `game_engine_end_game` | Team lives run out, then end | Zero living humans after deaths resolve | Post-death check, same tick |
| Actor cap | `MAXIMUM_ACTORS` 256 (PS2) | Its own cut (12) | Reserve before admission | Reserve against `MAXIMUM_ACTORS` |
| Corpses | None in survival | Bodies capped at 16 for 5 s | Bounded separately | Own corpse budget |

## 6. Population bounding: worst-case expansion

Terms that count against the active-enemy limit `L` (survival rule 7): mounted occupants,
swarm members, and secondary spawns. Terms bounded separately: corpses, drops,
projectiles, effects, deferred requests.

Per admitted enemy `e`, the worst-case expansion `X(e)` is:

- Base biped: 1 actor, 1 unit, plus weapon objects (1 primary, up to 2 grenade types).
- Mounted occupant: the occupant is an enemy and is already counted. The vehicle is an
  object and is not counted against `L`, but it draws from the object pool. Up to 16 seats
  per vehicle (`MAXIMUM_SEATS_PER_UNIT`).
- Swarm member: a swarm admitted as one enemy expands to up to 16 units
  (`MAXIMUM_UNIT_INDICES_PER_SWARM`) and up to 16 components
  (`MAXIMUM_COMPONENT_INDICES_PER_SWARM`). Worst case: 16 counted enemies from one swarm.
- Secondary spawn: `actors_spawn_from_unit(actor_count)` on death. Worst case per death is
  the tag's `actor_count`. That count is not extracted in this research; it must be read
  from the variant tags during C5 implementation.

Worst-case table. Assumed admitted-enemy count `L`. Columns: actors counted against the
pool, units, swarm slots and components, and object pool draw. Values use
`X(e) = 16` for swarm members, the worst case; secondary spawns are shown separately.

| Case | `L` | Actors (`L x E_max`) | Units | Swarms | Components | Objects (approx.) | Fits PS2 actor pool (256)? |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Bipeds only | 6 | 6 | 6 | 0 | 0 | 6 x 3 = 18 | yes |
| Bipeds + 2 mounted vehicles (16 seats) | 6 | 6 | 6 | 0 | 0 | 6 x 3 + 2 = 20 | yes |
| All swarms (worst) | 6 | 6 x 16 = 96 | 96 | 6 | 6 x 16 = 96 | 6 x (1 + 16) = 102 | yes (96 of 256) |
| Swarms + secondary spawns (count c per death) | 6 | 96 + 6 x c | 96 | 6 | 96 | 102 + weapons | yes if 6c <= 160 |
| Max `L` for PS2 pool, swarms worst | 16 | 16 x 16 = 256 | 256 | 16 | 256 | 16 x 17 = 272 | no margin; `L <= 12` keeps 192 |

Reading the table: with swarms at the worst case, `L` must stay at or below about 12 on
PS2 (12 x 16 = 192, leaving 64 actors for the reserve margin). The object pool
(2048 PS2) is not the binding limit for bipeds or swarms at these `L` values. It becomes
binding only when corpses, drops and projectiles are unbounded (section 7).

Reserve rule (proposal): before admitting a batch of `L` enemies, compute
`R = L x E_max(template)`, where `E_max(template)` is the template's worst expansion
(16 if it has a swarm, plus the tag's secondary count, plus 0 for mounted occupants
because they are already counted). Admit only if
`actor_data->actual_count + R <= MAXIMUM_ACTORS - SURVIVAL_MARGIN`. Otherwise stay in
`intermission` and retry at the next tick. Do not truncate the batch.

## 7. Recommended design

### State machine

- `setup`: validate the profile (mode, roster, difficulty, seed, qualified population).
  Reject unsupported profiles before map teardown. Expose mode, roster, difficulty, seed
  and qualified population at local setup.
- `active_wave`: admit one batch of `L` enemies after the reserve check. Wave ends when
  all batch enemies are dead or removed.
- `intermission`: 5 s (150 ticks at 30 Hz). Respawn dead humans here only. Advance the
  wave index.
- `game_over`: entered after the post-death check (below).

Transitions are a single function evaluated once per tick, after all deaths for the tick
have resolved.

Post-death check (rule 6): after every death in the tick is processed, count living
humans. If zero, enter `game_over` even if enemies also died this tick. The check must not
run before the death pass.

### Template cycle

Fixed table of wave templates, indexed by `wave % template_count`. Each template gives a
composition of kinds and mounted and swarm options. No array of completed waves is kept.
Only the current wave index and the seed-derived random state are stored.

### Population budgets

| Budget | Bound | Policy |
| --- | --- | --- |
| Active enemies (actors counted against `L`) | `L` (qualified; <= 12 for PS2 with swarms) | Batch-admit with reserve |
| Corpses | Fixed budget (e.g., 16, to be qualified) | Oldest-out; a corpse that is removed is deleted without touching live state |
| Drops | Fixed budget per wave | Oldest-out |
| Projectiles | Object pool share, qualified | Deferred spawn if over budget |
| Effects | `HALO_PORT_MAXIMUM_EFFECTS` share | Drop cosmetic effects first |
| Deferred requests | Fixed queue | Refuse new requests when full, log |

Rule for all budgets: they bound what is added or retained by survival. They must not
discard live CE state (living actors, living units, live projectiles still in flight).

### Qualification

- Fixed seeds per map (plan's qualification seeds).
- Population increased one participant at a time from the required baseline, stop at the
  first failure (C6 item 4).
- Mixed survival run for at least 1,000 waves followed by restart and UI return (C6 item 5).

## 8. Open items for the implementer

1. Read `actor_count` for each variant's secondary spawn from its tag (not done here).
2. Confirm the PS2 frame cost of a 16-unit swarm within one tick.
3. Decide whether map encounters are removed in survival (recommended) or the reserve
   subtracts their actors.
4. Decide corpse, drop, projectile and effect budgets by measurement, not from the N64.
5. Decide whether `game_over` is networked (machines must agree; AGENTS.md requires a
   network-version bump for changes to what machines agree on).
