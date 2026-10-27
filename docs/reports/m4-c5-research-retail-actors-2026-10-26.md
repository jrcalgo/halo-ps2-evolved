# M4 C5 research: retail actor lifecycle and bot-count metrics (2026-10-26)

Read-only research lane for plans/7 C5 steps 3-4. No source, test, or plan files were changed. Only this report was written.

## Scope and reading completed

- Read every file under `submodules/*/docs` (halo-ce-universal: `custom_edition_caches.md`, `mods.md`; halo-ps2: `01`-`14` docs, `reports/*`; ps2sdk: `code.css`), plus `submodules/halo-ce-universal/AGENTS.md`.
- Read `plans/7.hcu-remake-m2-m4.md` (C1 at line 373, C2 at 386, C5 at 456-467), `plans/6.hcu-remake-cowork.md` (C1 result, lines 79-141), memory `hcu-c1-handoff.md`.
- Reviewed `docs/reports/m2-c1-actor-roster-2026-10-23.json`, `m2-c2-actor-pool-telemetry-2026-10-23.md`, `m2-c2-gaps-bots-2026-10-24.md`.

## Key findings

1. **The C1 recipes are retail placement records, not bot spawns.** `m2-c1-actor-roster-2026-10-23.json` has 336 actor-variant occurrences (`variants`) and 75 logical placement recipes (`unique_recipes`). Each entry carries `actor`, `actor_type`, `datum`, `dependencies`, `disposition`, `equipment`, `mounted_recipes`, `placements`, `ranged_weapon`, `recipe`, `unit`, `unresolved`. Recipes are per-map and keyed by `source_map_sha256` (sources: `build/retail-maps/decompressed/*.map`). These are the inputs for C5.3 placement.
2. **Stock-MP bot profiles carry no retail actor bindings by design.** `plans/6` C1 disclosure (C1.2): bots are Spartan MP bipeds (`cyborg_mp`, three Spartan weapons, three special weapons, profile 13 `bots-sidewinder`, 1,830 tags, no retail actor variant). The plan forbids synthesizing stock-MP actor references. So a bot profile's retail-actor count is 0 by construction. That is not a bot count of 0.
3. **Survival profiles bind all 255 combat/mounted occurrences** (C1 acceptance). These are the only C1 profiles with retail actor records.
4. **Bot slots are separate from actor datums.** CE bots must be player-backed (C5.1). The actor datum pool (`actor_new` in `source/ai/actors.c:2251`) is an AI record pool, while bot players live in the player/unit pool. A retail actor record and a Spartan bot are different objects.
5. **Telemetry already exists for actors, but only for actor datums.** `m2-c2-actor-pool-telemetry-2026-10-23.md` adds retained counters in CE `actors.c`: configured capacity, peak `actual_count`, `datum_new` failures in `actor_new`, and map-reset count. Its own scope limits say it does NOT count unit/object allocations, props, swarms, effects, or bot players. It cannot be read as bot coverage.
6. **Bot gap evidence (C2) is a single load/release cycle.** `m2-c2-gaps-bots-2026-10-24.md` shows `bots_sidewinder` loads once with no gameplay ticks. That is load evidence, not bot behavior evidence.

## Source map for the C5 lifecycle (halo-ce-universal)

| Stage | Function | File:line |
| --- | --- | --- |
| Placement from encounter | `encounter` placement calls `actor_place` | `source/ai/encounters.c:3230` |
| Placement, scripted/AI | `actor_place` (definition) | `source/ai/actors.c:2720`; decl `source/ai/actor_placement.h:9` |
| Datum allocation | `actor_new` | `source/ai/actors.c:2251`; decl `source/ai/actors.h:1031` |
| Spawn from AI | `ai.c` calls `actor_place` | `source/ai/ai.c:3065` |
| Spawn of coop riders | `coop_enemies.c` | `port/linux/game/coop_enemies.c:678` |
| Update per tick | `static actor_update` (iterates, erases `erase_next_tick`) | `source/ai/actors.c:4247`, driver loop `:4309` |
| Death/kill | `actor_kill(index, silent, delayed)` | `source/ai/actors.c:3265`; callers `ai.c:2834,2868`, `actor_stimulus.c:911`, `ai_script.c:4615` |
| Cleanup | `actor_delete(index, died)` | `source/ai/actors.c:3129`; callers `ai.c:1385`, `ai_script.c:1941`, `actors.c:2687,2702,3319,3458,3481,3693,3846,3926` |
| Unit-linked delete | `unit->unit.actor_index` delete path | `actors.c:3693,3846`; `ai.c:1385` |

Note: `actor_new` requires a valid actor variant definition; `actor_place` takes encounter/squad/starting location. Before C5 can use retail placement, the CE encounter path must actually receive the C1 recipe data. Verify the CE port's map loader feeds `actor_place`; this research did not trace that.

## Existing tests and fixtures

- `tests/test_hcu_actor_roster.py`: C1 roster checks.
- `tests/test_hcu_step8_ce_actor_boundary.py`, `tests/test_hcu_step8_ce_vehicle_seat_actors.py`: actor-boundary and mounted-seat fixtures (step 8).
- `tests/test_hcu_step8_ce_actor_ilp32.py` (fixture `actor_fixture` in `build/hcu-step8-actor-ilp32/`): freestanding ILP32 test of the actor datum pool telemetry.
- `tests/hcu_mp_bot_pathfinding_host.c` and `tests/test_hcu_mp_bot_pathfinding.py`: host pathfinding for bots (prints `ce-bot-path` lines; synthetic walkable/blocked plus retail BSP case). This is pathfinding only, not a bot actor lifecycle.
- `tests/test_hcu_bots_partition_candidate.py`: bots partition package (2 tests). Package-level, not runtime.
- `tests/test_hcu_mp_detail_present_bound.py`: known to depend on a deleted `/tmp` directory (C1 residual).
- `submodules/halo-ce-universal/tools/system_link_bots.py`: launches CE copies as network bots (`bot%d` names, `source` line 125). It is a network bot harness that does not simulate AI in this sense: its own header says "bots do not simulate the game, nor send the distributed netcode's input". It must not be cited as C5 bot coverage.
- `submodules/halo-64/port/n64/game/n64_bots.c` and `n64_bot_ghosts.h`, `n64_bot_names.h`: N64 bots. Per C5.2, do not import N64 capacities, throttles, or cuts. They are reference only (player-slot bot-turn loop at `n64_game.c` / `players.c` near line 3930, "8 bots").
- `submodules/halo-ce-universal/port/linux/game/network_actors.c`, `coop_enemies.c`, `coop_scripts.c`: co-op actor path, the closest existing CE code to C5 cooperative modes.

## Proposed metrics schema (separate counters)

Keep the two populations separate in every record. Never derive one from the other.

```json
{
  "schema": "m4-c5-actor-bot-metrics/v1",
  "profile": "<profile name>",
  "mode": "stock_mp_bots | coop | survival",
  "tick": 0,
  "bots": {
    "spartan_player_slots_configured": 0,
    "spartan_player_slots_active": 0,
    "spartan_player_peak": 0,
    "spartan_spawned": 0,
    "spartan_died": 0,
    "spartan_respawned": 0,
    "spartan_navigating_ticks": 0,
    "spartan_firing_ticks": 0,
    "spartan_score_events": 0,
    "player_alloc_failures": 0
  },
  "retail_actors": {
    "recipe_count_bound": 0,
    "occurrences_bound": 0,
    "placed_count": 0,
    "alive_count": 0,
    "peak_alive": 0,
    "placement_failures": 0,
    "kill_count": 0,
    "delete_count": 0,
    "actor_datum_capacity": 0,
    "actor_datum_peak": 0,
    "actor_datum_alloc_failures": 0
  },
  "coverage_flags": {
    "bots_have_actor_recipes": false,
    "bots_covered_by_player_tests": false,
    "zero_retail_actors_implies_zero_bots": false
  }
}
```

Field rules:
- `bots.*` counts player-backed Spartans (CE player/unit pool). Source of truth: CE player creation/death/respawn.
- `retail_actors.*` counts AI actor records from C1 recipes (`actor_place`/`actor_new`/`actor_delete`). Source of truth: the actor datum pool telemetry from C2.
- Stock-MP bot profiles will read `retail_actors.placed_count = 0` by design. Report that, do not use it as bot coverage.
- Player-only tests (`hcu_mp_bot_pathfinding`, `test_hcu_bots_partition_candidate`) set `coverage_flags.bots_covered_by_player_tests` only after a real bot tick loop runs, not from host or package checks.
- Add a per-profile assertion: `spartan_player_peak` must equal the configured bot count in each qualified run. Zero is a failure, not a pass.

## Risks

1. **Conflation.** The biggest risk is treating `retail_actors.placed_count == 0` as "no bots", or passing player-only tests as bot coverage. The schema's coverage flags exist for this.
2. **Missing lifecycle evidence.** Current C2 bot evidence is one load/release cycle with no ticks. Nothing yet exercises bot death, respawn, or `actor_kill`/`actor_delete` on a bot.
3. **Telemetry gap.** The actor pool telemetry does not measure unit/object, prop, swarm, or effect allocations, so the 7/C5 bounded-storage rule (corpses, drops, projectiles, effects) has no counter yet.
4. **Stale bot package.** `bots_sidewinder` package was rebuilt with a diagnostic wrapper that overrides the non-2D pin check. `tools/c2_profile_boot_matrix.py` `EXTRA_PACKAGE_ROOTS` still points at the defective v2 tree (C2 follow-up). Any C5 bot run must use the fixed package.
5. **Plan hash pin.** Any edit to `plans/7.hcu-remake-m2-m4.md` invalidates the non-2D consumer reports (C1 disclosure). Regenerate with `tools/audit_hcu_profile_non2d.py` after touching the plan.
6. **Unverified seam.** CE `actor_place` callers do not yet consume the C1 recipe data in the HCU build (no trace in this lane). Verify the producer before counting `recipe_count_bound` as live.
7. **Licensing.** CE source is GPL-3.0 per halo-ps2 ADR-014 scope and submodule rules; do not copy N64 bot code without checking, and do not copy the Xbox SDK headers (AGENTS.md).
8. **Scope.** This research did not run the game, did not confirm the CE `actors.c` update path under the HCU build, and did not measure any bot count. All statements above are from source reading and existing reports.

## Next steps (for the implementer, not done here)

- Add the schema above as a retained-counter snapshot (mirror the C2 `actors.c` telemetry API) for both populations.
- Add a bot qualification test that runs N ticks with bots and asserts `bots.spartan_player_peak == configured` and `retail_actors.alive_count` stays within the active-limit, separately.
- Trace the encounter/`actor_place` feed from C1 recipes before claiming retail placement.
