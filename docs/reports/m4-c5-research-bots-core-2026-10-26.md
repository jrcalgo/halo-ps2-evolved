# M4 C5 steps 1-2 research: Spartan bots as player-backed participants

Date: 2026-10-26. Read-only research. No source, plan or git state was changed.

## 1. Sources read

- `plans/7.hcu-remake-m2-m4.md` section C5 (steps 1-8 and exit).
- `submodules/halo-ce-universal/AGENTS.md`, `docs/mods.md`, `docs/custom_edition_caches.md` (headings and project rules).
- `submodules/halo-ps2/docs/*.md` (01-14). Relevant: `03-engine-architecture.md` (30 Hz tick, object system, AI/pathing intent), `05-halo-ce-data.md` (tag groups, gameplay semantics), `06-decisions.md` (ADR-010 "campaign only" is superseded by the 2026-10-21 multiplayer scope amendment in plan 7).
- `submodules/halo-64` bot code (`port/n64/game/n64_bots.c`, `n64_bot_ghosts.h`, hook in `source/game/players.c:3932`, `source/game/player_queues_new.c:743`).
- Retail disc: not extracted. Nothing in steps 1-2 needs disc data (the bot code path is CE logic and tags; retail actor recipes belong to C1/C3).

Note on docs: halo-ps2 docs describe the PS2 engine as a clean-room reimplementation. The HCU fork instead compiles CE's own `source/` (plan 5: "Object identity, datums, units, and movement", "Physics and collision", "Weapons, projectiles, damage" are all `halo-ce-universal` rows). So CE code paths below are the ones that run; the halo-ps2 engine docs are context only.

## 2. CE player API (`submodules/halo-ce-universal/source`)

| Need | Function / location | Facts |
| --- | --- | --- |
| Create a player | `player_new(machine_index, player_index, local_player_index, network_player*)`, `game/players.c:1232` | `player_index == NONE` uses `datum_new`; otherwise `datum_new_at_index` (explicit slot). Sets `local_player_index`, `unit_index=NONE`, `team_index=1` (players.c:1265), copies `network_player` (name, colour, `team_index`, `machine_index`) when given. Calls `machine_add_player`. |
| Machine table | `machine_add_player`, `game/players.c:1168`; `machine_to_player_table[MAXIMUM_NETWORK_MACHINE_COUNT][MAXIMUM_LOCAL_PLAYERS]` (players.c:508) | Each machine holds `MAXIMUM_LOCAL_PLAYERS` = 4 entries. Overflow is `display_assert` plus `system_exit(-1)` (players.c:1190-1200). Bots must not share machine 0 with local humans once it has 4. |
| Machine count | `MAXIMUM_NETWORK_MACHINE_COUNT = HALO_PORT_MAXIMUM_NETWORK_MACHINES` (players.c:321) | PS2: 4 (`submodules/halo-ce-universal/port/ps2/include/halo_ps2_limits.h:15`). Linux port: 128 (`port/linux/include/halo_port_limits.h:21`). |
| Player capacity | `NETWORK_GAME_MAXIMUM_PLAYER_COUNT = HALO_PORT_MAXIMUM_NETWORK_PLAYERS` (players.c:320); `player_data = game_state_data_new("players", NETWORK_GAME_MAXIMUM_PLAYER_COUNT, sizeof(player_datum))` (players.c:553) | PS2: 16 (`halo_ps2_limits.h:14`). A datum index is also the action slot and the queue slot. |
| Spawn | `player_spawn(player_index)`, `game/players.c:1415` | Unit from `game_globals` (multiplayer unit when `game_engine_running()`). `object_new`, then `unit->object.owner_player_index`, `owner_team_index = player->team_index`, `unit->unit.player_index`, `player->unit_index`, `unit_set_actively_controlled`. `player_control_new_unit` only for players with `local_player_index != NONE`. Spawn point: `find_best_starting_location_index` (players.c:1307). |
| Per-tick spawn decision | `players_update_before_game`, `game/players.c:4795`, branch `unit_index == NONE` (players.c ~4870-4900) | `game_engine_should_spawn_player` (game_engine.c:9299), then `game_engine_prespawn_player_update` / `player_spawn` / `game_engine_postspawn_player_update`. Respawn countdown is `player->respawn_timer`; countdown sounds only for locals (game_engine.c:9333-9350). |
| Respawn timer set | `game_engine.c:5030`, `5102` (`MAX(respawn_timer, 90)`) | Set in the kill path. Applies to any player, local or not. |
| Death | `units/units.c:2789` calls `player_died(unit->unit.player_index)`; `players_handle_deleted_object` (players.c:4531) | `player_died` (players.c:814): `dead_unit_index = unit_index`, `unit_index = NONE`, local-only `player_control_new_unit(…, NONE)`, recomputes `players_globals->all_dead` over all datums. |
| Kill credit | `objects/damage.c:1135` and `game/game_statistics.c:224` call `game_engine_player_killed(killer_player, killer_object, dead_player, friendly_fire)` (game_engine.c:4979) | Scores and statistics (`player_datum.statistics`, offset 0x8C). The distributed netcode already replays this on clients (game_engine.c:4990). |
| Team | `player_datum.team_index` (players.h, offset 0x20). `team_index=1` default in `player_new`. Copied to unit at spawn (players.c:1538). `network_player_data.team_index` written at game_engine.c:7432-7436. | Two team fields. Set both for bots. |
| Stock game rules | `game_engine_should_end_game` (game_engine.h:613), `game_engine_did_player_win` (game_engine.h:530), variant builders in game_engine.c (`_build_game_variant_*`) | Victory rules stay in CE. `game/game_engine_slayer.c` has `slayer_engine_player_killed_player` (line 468) and `slayer_player_update` (594). |

### 2.1 Actions and unit control

- Per-tick input record: `struct player_action` (players.h), size asserted 0x20: `control_flags` (0x00), `desired_facing.yaw` (0x04, asserted), `desired_facing.pitch` (0x08, asserted), `throttle` (vec2, computed 0x0C), `primary_trigger` (real, computed 0x14), `desired_weapon_index` (short, computed 0x18), `desired_grenade_index` (0x1A), `desired_zoom_level` (0x1C), pad (0x1E). Computed offsets follow the layout; the header asserts only cover 0x04 and 0x08.
- Consumer: `players_update_before_game` (players.c:4795). It calls `update_client_dequeue(actions)` (player_queues_new.c:737). The body runs only when that returns TRUE. Actions are indexed by absolute player datum index, array size `NETWORK_GAME_MAXIMUM_PLAYER_COUNT`. For each live unit it:
  - runs `player_handle_action` when `_unit_control_action_bit` is set (players.c ~4917; pickup, vehicle, device),
  - handles swap (`_unit_control_swap_weapons_bit`), equipment (`_unit_control_use_equipment_bit`), weapon ready (`weapon_must_be_readied`),
  - builds `struct unit_control_data control_data` (players.c ~4960-5000): `control_flags`, `aiming_vector` via `player_aiming_vector_from_facing(player, &vec, &action->desired_facing)` (players.c:4735), `throttle`, `primary_trigger`, `weapon_index`, `grenade_index`, `zoom_level`, `animation_state = _unit_animation_state_in_combat`, and calls `unit_control(unit_index, &control_data)` (players.c:4994, 5012).
- Control bits: `units/units.h` lines 105-119 (`_unit_control_*_bit`), `UNIT_CONTROL_PORT_ACTION_ONLY_BIT` = 15 (units.h:142, port-defined).
- `struct unit_control_data` (`units/unit_control_data.h:20`): `animation_state` char (0x00), `aiming_speed` char (0x01), `control_flags` word (0x02), `weapon_index` short (0x04), `grenade_index` (0x06), `zoom_level` (0x08), `pad` (0x0A), `throttle` vec3 (0x0C), `primary_trigger` real (0x18), `facing_vector` (0x1C), `aiming_vector` (0x28), `looking_vector` (0x34), size 0x40. Offsets computed, not asserted.
- Player control (human side): `struct player_control` (players.h), size asserted 0x40, `unit_index` at 0x00, `desired_angles.yaw` 0x0C, `.pitch` 0x10, `desired_weapon_index` 0x20, `desired_grenade_index` 0x22, `zoom_level` 0x24. Bots do NOT need this struct: they have no local player control, so they never touch `player_control_get` or the four local control records.
- AI actors also drive units through `unit_control` (ai/actors.c:1333, 3793, 4225 via `actor_unit_control` at 4180; ai/actor_type_infection.c:887). This is the non-player path. Bots should use the player path, as the plan requires.

### 2.2 Where local humans enter the action stream (the path bots must join)

1. `player_control_update` → `update_client_queue(&action)` per local player (`game/player_control.c:892`; `update_client_queue` at `game/player_queues_new.c:609`), then `update_client_queue_push()` (player_control.c:905, player_queues_new.c:642).
2. `game_time.c:455`: when `game_connection() == _game_connection_local`, `update_client_local_ticks(ticks_elapsed)` (player_queues_new.c:838). It calls `update_client_build_client_update` (copies `saved_action_collection`), then `update_server_handle_client_update(machine_index=0, actions)` (player_queues_new.c:861), then loops `update_server_next_update()` once per tick.
3. `update_server_handle_client_update` only copies into queues of the machine 0 player list, keyed by `player->local_player_index` (player_queues_new.c:861-911). Bots have `local_player_index = NONE` and are on another machine, so this path never reaches them.
4. `update_server_next_update` (player_queues_new.c:398) builds one `struct update` per tick. For every queue with `identifier != 0` it copies `queue->current_action` and ORs `update_server_pending_control_flags` (player_queues_new.c:420-470). Dead or empty slots get an idle action.
5. `update_client_dequeue` (player_queues_new.c:737) hands that update to `players_update_before_game`.

So the single hook point that keeps bots in the same deterministic stream as humans is step 3/4: write the bot's `current_action` (and pending button flags) into its own queue (`update_server_globals.queues`, datum at the bot's player index) once per tick inside the `update_server_next_update` loop of `update_client_local_ticks`, before that call. That makes bot actions part of each `struct update`, so they are recorded and replayable with the rest of the update stream.

Network-server analogue: `update_server_take_local_actions` (player_queues_new.c:1056) copies only local-player queues. Bots in a network game must be handled there too, or on the host only. Not designed in this report.

Halo-64's hook is different: it writes bot actions inside `update_client_dequeue` (player_queues_new.c:740-746, `n64_bots_actions(actions)`), after the update is dequeued. That skips the update stream. Do not copy that placement (see section 5).

### 2.3 Lifecycle hooks a bot needs

- Create: `player_new(machine, 4 + i, NONE, &network_player)` with an explicit index (players.c:1243-1245 `datum_new_at_index`). Then add a queue: `update_server_add_player(idx)` and `update_client_add_player(idx)` (player_queues_new.c:382, 581; the join path does both at `networking/network_client_manager.c:2008-2011`). Also `game_engine_player_added(idx)` (game_engine.h:486) as the join path does (network_client_manager.c:~2000).
- Team: set `player->team_index` and `player->network_player_data.team_index` explicitly. Both default to 1 in CE.
- Spawn/respawn: nothing new. The stock per-tick loop in `players_update_before_game` spawns any non-local player whose `game_engine_should_spawn_player` is TRUE. Survival (plan C5.6) needs its own spawn gate, since it has no stock respawn rule.
- Death: `player_died` is already called through `units.c:2789`. Kill score through `game_engine_player_killed`. Bots need `hcu_bot_note_death(state, bot, killer)` from the same two places. These are not hooked yet.

## 3. Bot-state and seed wiring (what exists in the fork)

- `src/stream/hcu_bot.h` / `hcu_bot.c` (fork, 183 + 639 lines): pure host-testable core. `HCU_BOT_LOCAL_SLOTS 4`, `HCU_BOT_PLAYER_SLOT_BASE 4`, `HCU_BOT_MAX 8` (`hcu_bot.h`). Per-bot xorshift32 streams via `hcu_bot_rng_seed(rng, seed, stream)` (`hcu_bot.c:168`). `hcu_bot_think` (`hcu_bot.c:572`) writes `hcu_bot_action` per bot. `hcu_bot_hash` (`hcu_bot.c:587`) is FNV-1a over roster, tick, streams, counters, float bit patterns.
- Not wired anywhere yet. `grep` finds `hcu_bot_*` only in `src/stream/hcu_bot.[ch]`. No CE file calls `hcu_bot_think`, `hcu_bot_hash`, `hcu_bot_init`, or the death/spawn notes. Replay hash folding is not connected.
- `src/stream/hcu_coop_modes.h`: `HCU_COOP_MAX_BOTS 12`, `HCU_COOP_HUMAN_TEAM 0`, `HCU_COOP_BOT_TEAM 1`. CE's default team is 1 (players.c:1265), so the human team 0 must be set explicitly.
- `src/stream/hcu_local_setup.h`: `HCU_LOCAL_BOT_SLOTS 4`.
- `src/stream/hcu_survival.h` (C5.6-7): intermission 150 ticks, `HCU_SURVIVAL_ACTIVE_LIMIT_MAX 32`, humans max 4.
- Survival state for bots is not yet connected to CE respawn (section 2.3).

### 3.1 Seeded RNG streams

- CE has two streams (`math/random_math.c`):
  - `global_random_seed` (random_math.c:82). Simulation. Seeded at map load from `game_globals->options.random_seed` (`game/game.c:681`). `get_global_random_seed_address()` (random_math.c:132) asserts `!game_engine_running() || !lock_count`. The first-person update is locked (`game/game.c:392-395`). AI uses it (actors.c, actor_stimulus.c, items.c:469).
  - `global_local_random_seed` (random_math.c:83). Time-seeded in `random_math_initialize` (random_math.c:163-170, `system_seconds ^ system_milliseconds ^ rand()`). Not deterministic. Must not feed simulation or bots.
- Bots must draw only from their own `hcu_bot_rng` streams, never from `global_random_seed`. Drawing from it would shift AI order for every actor, which changes both AI and the hash.
- `hcu_bot_init` seeds each stream from the roster seed (`hcu_bot.c:191-216`). The roster seed must be the qualification seed, not `system_*` or `rand()`. The local-game seed for CE's global stream comes from `options.random_seed` (game.c:681), which is also a setup input and must be fixed for qualification runs.

## 4. Struct offsets for the adapter

Asserted by CE (`players.h`):
- `player_datum` size 0xD4. `team_index` 0x20. `player_display_count` 0x80. `statistics` 0x8C. `telefrag_timeout` 0xC8. `quit_out_of_game_time` 0xCC. `is_blocking_teleporter` 0xD0. `quit_out_of_game` 0xD1.
- `players_globals` size 0xB0. `local_player_count` 0x24, `all_dead` 0x28, `input_disabled` 0x29, `respawn_failure` 0x2C, `combined_pvs` 0x30, `combined_pvs_local` 0x70.
- `player_control` size 0x40 (fields in section 2.1).
- `player_action` size 0x20 (desired_facing yaw 0x04, pitch 0x08).

Computed, not asserted (verify with a new assert before use):
- `player_datum.unit_index` 0x34, `dead_unit_index` 0x38, `respawn_timer` 0x2C, `action_result` 0x28, `local_player_index` 0x02, `name` 0x04 (wchar_t[12]; 24 bytes only if wchar_t is 2 bytes, which the fork's ABI must confirm), `network_player_data` 0x48 (32 bytes), `death_time` 0x84.
- `unit_control_data` size 0x40 (section 2.1).

## 5. Halo-64 bots: what to take and what not to import

Take (concepts, reimplemented in `hcu_bot.c`):
- Players built with `player_new` on machines of their own, spawned, scored, respawned and coloured by CE's own rules (halo-64 `n64_bots.c:1-14`; machine per four players, `player_new(1 + i/4, …)` at line 717).
- Actions go through `players_update_before_game` like a controller's (action button pickup, vehicle exit, trigger, grenade, jump, reload).
- Enemy selection by team (another team in team games, anyone otherwise), paths on Halo's own path code, line of sight through objects, no fire through a teammate (`n64_bots.c:1-30`, `line_of_sight` at ~420).
- Burst fire (held for automatics, pressed otherwise), skill-based aim error, grenade chance per tick, melee up close, reload and weapon swap, "go for a better weapon nearby".

Do not import (N64 capacities, throttles, cuts, or non-determinism):
- `MAXIMUM_BOTS 12` as a cut (n64_bots.c:62). The PS2 seat count is 16 − 4 humans = 12 (section 6). Use the seat arithmetic, not the N64 number.
- `DIRECT_TESTS_PER_TICK 2`, `DIRECT_PATH_RETRY_TICKS 30`, `SEARCH_SURFACES_PER_TICK 40`, `TICKS_BETWEEN_PATHS 3`, `PATH_LIFETIME` (n64_bots.c:64-75): path throttles.
- `bot_detail`, `n64_bots_pose_interval`, `n64_bot_pose_interval`, `n64_bots_update_interval`, `n64_bot_move_interval`, `bot_think_interval` (n64_bots.c:368, 575-643): pose and think rate cuts by distance, skill and bot count.
- `n64_bots_examine_turn` gate in `players_update_before_game` (halo-64 `source/game/players.c:3932-3938`): bots skip object examination on some ticks.
- `ai_debug.path_disable_obstacle_avoidance = TRUE` (n64_bots.c:~544). The N64 lacks AI's obstacle records. CE has them (`ai/path_obstacle_avoidance.c`); keep them on.
- `bots.random = n64_ticks() | 1` (n64_bots.c:~537). Wall-clock seed. Replace with the qualification seed streams.
- Ghost profiles (`n64_bot_ghosts.h`, `n64_bot_names.h`): roster and camouflage rolls. Cosmetic and out of scope. Keep the name pool idea only.
- `SIGHT_RANGE 50`, `WEAPON_SEARCH_RANGE 14`, `WEAPON_GIVE_UP_TICKS`, `BOT_NEAR/BOT_FAR` (n64_bots.c:77-86): tuned to N64 timings. Re-tune against CE values, do not copy.
- Placement in `update_client_dequeue` (player_queues_new.c:740-746): skips the update stream, so bot actions are not recorded in updates and cannot be replayed from them. Use the `update_server_next_update` hook (section 2.2).

## 6. Seat and capacity arithmetic (PS2 build)

- Player datums: 16 (`HALO_PORT_MAXIMUM_NETWORK_PLAYERS`).
- Local humans: 4 (`MAXIMUM_LOCAL_PLAYERS`, all on machine 0).
- Bot seats: 12 at most (16 − 4). They need machines 1-3 (3 × 4 = 12), since machine 0 may hold 4 humans.
- Three different bot caps exist in the fork: `HCU_BOT_MAX 8` (`hcu_bot.h`), `HCU_COOP_MAX_BOTS 12` (`hcu_coop_modes.h`), `HCU_LOCAL_BOT_SLOTS 4` (`hcu_local_setup.h`). They must agree, and the roster bound should be derived from `HALO_PORT_MAXIMUM_NETWORK_PLAYERS − humans` and `HALO_PORT_MAXIMUM_NETWORK_MACHINES`. `HCU_BOT_MAX 8` looks like it came from the N64 "7 or 8 bots" comments (halo-64 n64_bots.c:572); it needs a stated reason or a change to 12.
- `hcu_bot_think` loops `i < HCU_BOT_MAX` (hcu_bot.c:577), not `count`. Dead or absent slots get `bot_action_idle`. Confirm that is intended.

Caution: `hcu_bot.h` says bot i is CE player `4 + i`. CE datum indices carry an identifier in the high 16 bits (`DATUM_INDEX_TO_ABSOLUTE_INDEX`). The adapter must compare absolute indices everywhere.

## 7. Adapter mapping: `hcu_bot_action` → CE `player_action` / `unit_control_data`

| `hcu_bot_action` field | CE target | Note |
| --- | --- | --- |
| `stick[2]` | `player_action.throttle` (vec2) | Same as a controller's stick. Range [-1, 1]. |
| `aim[3]` (vector) | `player_action.desired_facing` (yaw, pitch) | CE stores euler angles. The adapter must convert the aim vector to yaw/pitch (inverse of `player_aiming_vector_from_facing`, players.c:4735). Not written yet. |
| `trigger` | `primary_trigger` (real) and `_unit_control_weapon_primary_trigger_bit` | Auto weapons: held. Semi/explosive: pressed (matches `hcu_bot_fire` modes). |
| `grenade` | `_unit_control_throw_grenade_bit` | |
| `jump` | `_unit_control_jump_bit` | |
| `reload` | `_unit_control_weapon_reload_bit` | |
| `action` | `_unit_control_action_bit` | Pickup and vehicle; `UNIT_CONTROL_PORT_ACTION_ONLY_BIT` (15) is port-only and stripped before `unit_control`. |
| `swap` | `_unit_control_swap_weapons_bit` | Also needs `player->swapped_weapons` edge logic (players.c ~4905). |
| `melee` | Not mapped | No melee bit in `units.h`. CE melee is `_unit_state_melee_attack` (units.h:179). The input that triggers it is not identified here. Open item. |

Button flags in `update_server_pending_control_flags` are ORed between ticks for humans. Bots think each tick, so they can set `control_flags` directly. Be sure a pressed bit is set for exactly one tick (the `pressed` mask in halo-64 `n64_bots_actions` shows the idea, players.c-side).

## 8. Determinism and hashing

- No CE simulation or replay hash was found. Searched: `game/`, `networking/`, `saved films/`, `port/linux/game/`. The only checksums are map/cache CRCs (`port/linux/game/cache_file_formats.c`), tag-group checksums (`networking/network_server_manager.c:3367`), and map-share hashes. `src/hybrid/replay.c` has its own `hash_word` over the hybrid protocol, unrelated to CE.
- So "replay hash" must be defined by this work. Proposed fold order: CE per-tick update stream (`struct update`, 16 actions) + `hcu_bot_hash` + global seed value + `player_data` identity fields (unit_index, team, respawn_timer, statistics) per tick. Include `hcu_bot_hash` only after the adapter writes into the update stream, or the hash misses what the bots actually did.
- Bot inputs are drawn from per-bot streams. Scheduling does not change them as long as `hcu_bot_think` is called exactly once per simulated tick, in bot-index order, from the same point in the tick. Document that as a rule.
- Float use: `hcu_bot` hashes float bit patterns. CE's real math is the same across builds of one target, which is enough for the PS2 build. Cross-build hashing (for example the Linux build) needs the normalization that CE already does (`port/linux` uses musl maths for every native build).
- Do not read `get_number_suitable_for_initializing_random_seed()` or `system_*` inside bot code.

## 9. Integration plan (for steps 1-2; no edits made)

1. Pick a single bot seat rule: bot i uses CE player index `4 + i`, machine `1 + i/4`, `local_player_index = NONE`, `network_player` name from `hcu_bot_name_index`. Use `player_new` with explicit index.
2. After `player_new`, call `update_server_add_player(idx)`, `update_client_add_player(idx)`, `game_engine_player_added(idx)`. Set `team_index` and `network_player_data.team_index` explicitly for humans (0) and bots (1), so they match `hcu_coop_modes.h`.
3. In `update_client_local_ticks` (player_queues_new.c:838), inside the per-tick loop, before `update_server_next_update()`: build `hcu_bot_world` from CE (players' alive/team/weapon/pos from `unit_get`, `line_clear` via `collision_test_vector`, `path_step` via `path_input_new` / `path_state_new` / `path_state_find` / `path_state_build_path` with `structure_surface_index_from_point`, `objective` from the mode), call `hcu_bot_think`, convert each `hcu_bot_action` to a `player_action`, write `queue->current_action` for the bot's queue.
4. Death: from `player_died` (players.c:814) or `units.c:2789`, call `hcu_bot_note_death(state, bot, killer)`. Spawn: from `player_spawn` (players.c:1415), call `hcu_bot_note_spawn(state, bot, pos)`. Kill credit already in `game_engine_player_killed`.
5. Survival: override `game_engine_should_spawn_player` for the survival mode (the stock rule uses `respawn_timer`), following `hcu_survival.h`.
6. Hash: fold `hcu_bot_hash` plus the per-tick update stream into the replay hash after step 3.

Unit tests that exist or are needed: `hcu_bot` host tests (none run here). Needed: a mapping test (action → `player_action`, including aim-vector to yaw/pitch), an absolute-index test (datum identifier bits), and an update-stream test (bot action appears in `struct update` for its index).

## 10. Risks

- Machine overflow: putting bots on machine 0 with 4 humans calls `system_exit` (players.c:1190-1200). Bots must use machines 1-3 only.
- Empty update stream: `players_update_before_game` runs only if `update_client_dequeue` returns TRUE (player_queues_new.c:737). Local games with no update yet skip all players. Verify bot-only ticks still produce updates.
- Bot actions missing from replays if written after dequeue (halo-64 placement). Avoid.
- Global RNG leakage: any `real_seed_random(get_global_random_seed_address())` call from bot code changes AI for every actor. Enforce the stream rule with a test.
- Team defaults: `player_new` sets team 1 (players.c:1265), and `hcu_coop_modes` expects humans on 0. Missing explicit assignment flips teams.
- Two team fields (`player->team_index` and `network_player_data.team_index`) may diverge. Set both.
- Three different bot caps (section 6).
- Path state is large: `struct path_state` holds `node_list[0x400]` and `heap[1025]` (path.h:139-153). One shared state for all bots, not one per bot. Per-bot heap would blow the PS2 budget.
- Obstacle avoidance: do not disable it as halo-64 does.
- Melee input not identified (section 7).
- `hcu_bot_think` reads `players[4+i]` from a world array. A wrong mapping from datum to slot silently gives bots the wrong percepts. Assert it in the adapter.
- Local-only test paths (`debug.test_input` "bot:<seed>" in `port/linux/src/xinput_sdl.c`, `port/linux/game/network_test.c`) are controller scripts, not bots. Do not confuse them with C5 bots.

## 11. Open items for later steps

- Find CE's melee input bit and its edge handling.
- Confirm `wchar_t` width in the PS2 build (affects `player_datum` offsets).
- Confirm whether local games without network create `update_server` queues for local players at map load (the path that `player_new` + `update_server_add_player` must join).
- Decide the survival respawn override and the bot-count bound (one number).
- Decide whether to add a bot-specific replay hash or fold into the existing hybrid replay (`src/hybrid/replay.c`); the latter is a different protocol.
