# M4 C5 research: bot and cooperative team modes (2026-10-26)

Read-only research for C5 step 5 of [plans/7.hcu-remake-m2-m4.md](../../plans/7.hcu-remake-m2-m4.md): qualifying
Slayer, CTF, Oddball, King and Race (team variants as applicable) with Spartan bots, preserving CE victory and
respawn rules, with humans sharing a team against bots in cooperative team modes. Nothing outside this file was
modified. Sources: `submodules/halo-ce-universal/source/game/`, `submodules/halo-64/source/game/` and
`port/n64/game/n64_bots.c` (reference only), `src/stream/hcu_local_setup.h`, and the docs listed in section 8.

## 1. Headline findings

1. **Stock CE has no bots.** No file in `halo-ce-universal/source` or `port/linux` implements a bot or a
   computer-controlled player. The grep hits for "bot" are false positives (`items/weapons.c:500`, a port
   comment that says "stock CE has no bots"; `main.c`; `port_config.c`; `network_test.c`). The `source/ai/` tree is
   scripted AI actors (encounters, squads), which is a different system from player-backed bots. C5 bots are new
   work in the HCU fork, not a switch on existing CE code.
2. **The only bot reference is halo-64's N64 bots**, `submodules/halo-64/port/n64/game/n64_bots.c` (with
   `n64_firefight.c`, `n64_bot_names.h`, `n64_bot_ghosts.h`). Its design is the one to study: bots are
   `player_new` players that the game engine spawns, scores, respawns and colours by its own rules; their actions
   come from a hook (`n64_bots_actions`) in `update_client_dequeue` (`player_queues_new.c:741`), and
   `players_update_before_game` applies them like a controller's. Do not import its `MAXIMUM_BOTS 12`, its
   throttles, its ghost and name tables, or the firefight tuning. Only the shape of the hook is reusable.
3. **The victory and respawn rules are generic** and live in `game_engine.c` and the per-gametype engines. The
   team logic is driven by `global_variant.universal_variant.teams`, not by the gametype. Bots therefore need
   nothing new in victory code if they are assigned team indices like humans.
4. **Team capability is set per variant builder**, not per engine. Five engines exist; team variants are
   separate builders that set `teams = TRUE` (section 3).
5. **Two traps for C5:** (a) the port's auto team balance (`game_engine_player_killed`, `game_variant_options`
   `auto_team_balance`) can move a dead player to the other team, which would move a bot or a human out of the
   human-team/bot-team split; it must be off in cooperative modes. (b) The HCU survival end rule ("zero living
   humans ends the match") is not a CE rule. CE's `game_engine_should_end_game` ends on `!multiple_teams_alive()`
   or the time limit. Survival needs its own end condition, separate from the CE path, and must not be implemented
   by changing CE's.

## 2. Entry points (function names)

| Concern | Function (file:line) | Notes |
| --- | --- | --- |
| Engine selection | `enum game_engine_type` (`game_engine.h:35`): `game_engine_ctf`, `_slayer`, `_oddball`, `_king`, `_race`, `_terminator`, `_stub`; usable range `ctf..race` | Terminator and stub are not usable. |
| Variant builders | `build_game_variant_<name>` (`game_engine.c`): slayer 6047, team_slayer 6080, elimination 6113, phantoms 6146, endurance 6179, rockets 6212, snipers 6245, oddball 6278, team_oddball 6315, reverse_tag 6352, accumulation 6389, juggernaut 6425, stalker 6461, king_pro 6498, team_king 6529, slayer_pro 6560, ctf 6593, ctf_pro 6628, invasion 6663, iron_ctf 6698, race 6733, rally 6765, team_race 6797, team_rally 6829 | The HCU variant names in `hcu_local_setup.h` are slayer, ctf, oddball, king, race. |
| Variant struct | `struct game_variant` (`game_engine.h`), size asserted 0x68 | Fields in section 3. |
| Victory gate | `game_engine_should_end_game` (`game_engine.c:5571`) | Ends on `!multiple_teams_alive()` or the time limit. |
| Teams alive | `multiple_teams_alive` (`game_engine.c:6904`), `team_has_players` (`:6951`) | Counts players with a unit or still in lives, skipping quit and odd-man-out players. |
| Team win (scoreboard, post-game) | `game_engine_did_team_win` (`:1056`), `game_engine_did_player_win_default` (`:6996`), `game_engine_did_player_win` (`:6888`, per-engine override first) | Team variants compare `game_engine_get_team_score`; non-team variants use place. |
| Lives | `game_engine_player_is_out_of_lives` (`:5745`) | Only when `lives > 0`. |
| Death and respawn timer | `game_engine_player_killed` (`:4979`, respawn block about 5024-5050) | See section 4. |
| Per-tick update | `game_engine_update` (`:4815`) | Runs `game_engine->player_update_each_tick`, `game_engine->update`, then `should_end_game` (only when `!network_game_distributed_client()`). |
| Slayer | `game_engine_slayer.c`: `slayer_engine_update` (:223), `slayer_player_update` (:594), `slayer_engine_player_killed_player` (:468) | `score_to_win` checked at :669. |
| CTF | `game_engine_ctf.c`: `ctf_engine_update` (:817), `ctf_engine_player_update` (:570), `ctf_engine_player_killed_player` (:363), `ctf_engine_game_starting` (:392) | Teams are always on. Flag return and capture rules are here. |
| Oddball | `game_engine_oddball.c`: score checks at :448, :464, :480, :818, :1451; `oddball_globals.score_to_win` set at :699-701 | Score is in ticks per unit (`ODDBALL_SCORE_TICKS_PER_UNIT`). |
| King | `game_engine_king.c`: `king_engine_update` (:780), `king_engine_player_update` (:455), score check around :477-482 | Hill state `king_calculate_hill_state` (:959). |
| Race | `game_engine_race.c`: `race_engine_update` (:311), `race_engine_player_update` (:273), `race_team_can_win_game` (:239, body near :793), `race_engine_did_player_win` (:309), `race_complete_lap` (:229) | Laps counted per team in team mode (`race_globals.team_laps`). |
| Team assignment | `players.c:1265` (`player->team_index = 1`), `players.c:1603-1605` (team from `unit->object.owner_team_index`) | The lobby or network path that first sets `team_index` was not traced; see section 7. |
| Auto team balance | `game_engine.c` in `game_engine_player_killed` (about :74-97) | Port addition, host-only, gated on `teams` and `game_variant_options_get()->auto_team_balance`. |
| HCU setup admission | `src/stream/hcu_local_setup.h`: `hcu_local_setup_validate`, `hcu_local_setup_admit`; `HCU_LOCAL_BOT_SLOTS 4u` | Already rejects a survival profile with a team variant and a coop profile without one (`VARIANT_NOT_APPLICABLE`). |

## 3. Variant fields and team capability

`struct universal_variant` (in `game_engine.h`): `teams`, `flags` (bits `_game_variant_*_bit`), `goal_radar`,
`odd_man_out`, `respawn_time_growth`, `respawn_time`, `suicide_penalty`, `lives`, `health`, `score_to_win`,
`weapon_set`, `vehicle_set`. Engine-specific data sits in the union `game_engine_variant`: `ctf`
(`assault`, `reset_on_capture`, `flag_must_reset`, `flag_at_home_to_score`, `single_flag_time`), `slayer`
(`no_death_bonus`, `no_kill_penalty`, `kill_in_order`), `king` (`moving_hill`), `oddball` (`random_start`,
`ball_spawn_delay`, `speed_with_ball`, `trait_with_ball`, `trait_without_ball`, `oddball_ball_type`,
`ball_spawn_count`), `race` (`race_type`, `team_scoring`).

Values as set by the builders (`game_engine.c`). `teams` is the team switch; `vehicle_set` is shown only where it
is not the default.

| Variant | engine | teams | respawn_time | suicide_penalty | score_to_win | lives | other |
| --- | --- | --- | --- | --- | --- | --- | --- |
| slayer | slayer | FALSE | 0 | 300 | 15 | 0 | warthog |
| team_slayer | slayer | TRUE | 300 | 300 | 50 | 0 | warthog |
| ctf | ctf | TRUE | 300 | 150 | 3 | 0 | warthog, nav-point radar |
| oddball | oddball | FALSE | 150 | 150 | 2 | 0 | vehicles none, ball_spawn_count 1, spawn delay on |
| team_oddball | oddball | TRUE | 300 | 150 | 2 | 0 | vehicles none, generic starting equipment on |
| king | king | FALSE | 150 | 150 | 2 | 0 | warthog |
| team_king | king | TRUE | 300 | 150 | 2 | 0 | warthog, moving_hill TRUE |
| race | race | FALSE | 0 | 300 | 3 | 0 | race_type 0, team_scoring 0 |
| team_race | race | TRUE | 0 | 300 | 3 | 0 | race_type 0, team_scoring 0 |
| rally | race | FALSE | 0 | 300 | 15 | 0 | race_type 2 |

Team capability summary:

- **Team-capable (teams TRUE):** team_slayer, ctf (always), team_oddball, team_king, team_race. Only the first
  four are named in the plan's list; team_race is the race team variant.
- **Individual only (teams FALSE):** slayer, oddball, king, race, rally.
- The HCU `hcu_local_variant` enum (`SLAYER, CTF, ODDBALL, KING, RACE`) selects the engine. The team switch is a
  second input and must come from the variant name (team_slayer, team_oddball, team_king, team_race) or from a
  profile flag. The current header does not carry that flag; C5 needs to add it or add the team variants to the
  enum. Note CTF has no non-team variant in CE, so it is always a team mode.
- Rally is a race engine variant without teams. It is not in the plan list and can be deferred.

## 4. Victory and respawn rules that must survive

Respawn (`game_engine_player_killed`):

- `respawn_timer = respawn_penalty + respawn_time`.
- If `respawn_time_growth > 0`: penalty grows by growth per death, capped at `growth * 5`; a player kill reduces
  the killer's penalty by growth (floored at 0).
- Not a player kill (suicide, team kill, environment): `respawn_timer += suicide_penalty`.
- In team variants, the host's auto team balance may move the dead player (see section 1 trap a).

Victory:

- Team modes: the game ends when `multiple_teams_alive()` is false (one team has all the remaining players), or
  at the time limit. Ties on score go to `game_engine_did_team_win` (team score compare, or `NONE` on a tie).
- Individual modes: `score_to_win` per engine, plus `multiple_teams_alive()` (which is trivially true with
  individual players, since each player is its own team index in practice). Verify this before relying on it; see
  section 7.
- Lives: `lives > 0` makes `game_engine_player_is_out_of_lives` true for a unitless player with deaths at or above
  the limit. Every builder above sets lives 0, so C5 modes never use it.

Human-team versus bot-team wiring (proposal, consistent with CE):

1. Team 0 is all human controller slots (`human_mask` bits), team 1 is all bot slots. Bots are `player_new` players
   with `team_index = 1`; humans keep `team_index = 0`. This relies on the existing team index path (section 7).
2. Set `universal_variant.teams = TRUE` for the cooperative team variants. Victory then is CE's: one team left
   standing ends the game, so humans-alive-only ends the match once bots are gone, and bots-alive-only ends it
   when humans are gone.
3. Turn off auto team balance for cooperative profiles (the setting is in `game_variant_options`; set it to FALSE
   in the admitted profile, not in CE's defaults).
4. Survival (no variant, `HCU_LOCAL_MODE_SURVIVAL`) does not use CE's victory. Its states (`setup`, `active_wave`,
   `intermission`, `game_over`) and the "zero living humans ends the match" rule are HCU additions. Keep them in
   the HCU layer; do not change `game_engine_should_end_game`.

## 5. Bot architecture guidance (from n64_bots.c, not to import)

- Bots are created as players: CE `player_new`, spawned in the player biped, scored, respawned and coloured by the
  engine. They appear in the same `player_data` iterator as humans, so every CE rule above applies to them with no
  special case.
- Actions are produced by a per-tick hook in `update_client_dequeue`, equivalent to `n64_bots_actions`, which
  writes the bot's `player_action` slots. Human actions come from controllers. The apply step
  (`players_update_before_game`) is shared.
- Perception and combat in the N64 code: nearest enemy (other team in team games, anyone otherwise), path along
  Halo's own paths when out of sight, keep weapon range, burst fire, grenades, melee, reload and vehicle exit, and
  no fire through teammates (a clear line is required). This is a reasonable reference, but the plan requires CE
  collision, pathfinding and damage paths and deterministic seeded streams, so its simplified logic is not a
  drop-in.
- Bot state and seeded random streams must be part of simulation and replay hashes (plan C5.2).
- Counts: plan C5.4 requires Spartan bots counted separately from retail actors. `HCU_LOCAL_BOT_SLOTS` is 4, which
  matches the plan's "four local plus four bots" row (C6.1) only if the bot cap in the HCU profile is raised to 4
  for qualification. Confirm the intended cap with the plan owner; the header's comment says 4.

## 6. Qualification test matrix

Per map (the 13 stock multiplayer maps: beavercreek, bloodgulch, boardingaction, carousel, chillout, damnation,
hangemhigh, longest, prisoner, putput, ratrace, sidewinder, wizard). Start with Longest and Blood Gulch as the plan
says. Survival rows are not CE rules and are listed for completeness.

| # | Mode / variant | Teams | Humans | Bots | Checks |
| --- | --- | --- | --- | --- | --- |
| 1 | slayer (individual) | no | 1-4 | 0 | Score to 15, respawn timer 0 + suicide 300, no bot involvement. Baseline. |
| 2 | slayer, with bots | no | 1 | 1-4 | Bots score, die, respawn; individual victory when score reaches 15. |
| 3 | team_slayer | yes | 4 | 0 | Team victory at 50; respawn 300. |
| 4 | team_slayer, cooperative | yes | 1-4 | 1-4 | Humans team 0, bots team 1; victory when one team is eliminated; no auto-balance; respawn 300. |
| 5 | ctf | yes | 4 | 4 | Flag capture to 3; flag return and touch-return rules; respawn 300; suicide 150. |
| 6 | oddball (individual) | no | 1-4 | 1-4 | Ball pick-up by bots; score to 2 units; respawn 150. |
| 7 | team_oddball, cooperative | yes | 1-4 | 1-4 | Ball on either team; score to 2; team victory; respawn 300. |
| 8 | king (individual) | no | 1-4 | 1-4 | Hill occupancy by bots; score to 2 minutes; respawn 150. |
| 9 | team_king, cooperative | yes | 1-4 | 1-4 | Moving hill; team victory; respawn 300. |
| 10 | race (individual) | no | 1-4 | 1-4 | Laps; bots drive warthogs; race_type 0. |
| 11 | team_race, cooperative | yes | 1-4 | 1-4 | Team laps; `race_team_can_win_game`; team victory. |
| 12 | Human elimination | any team mode | 0 left | some alive | Match ends on the tick when humans reach zero; if the last enemy also dies that tick, humans still lose (plan C5.6). Survival only. |
| 13 | Time limit | any | any | any | `game_variant_options_get()->time_limit` ends the match with `should_end_game`. |
| 14 | Teams disabled for bots | yes | 4 | 4 | Auto team balance off, no bot changes team index. |
| 15 | Profile rejection | any | any | >4 | `hcu_local_setup_admit` refuses before teardown (`TOO_MANY_BOTS`, `VARIANT_NOT_APPLICABLE`, `MAP_NOT_QUALIFIED`). |
| 16 | Determinism | any | any | any | Normalised simulation hash equal across render-pass schedules (C6.6). |
| 17 | Retail actor coverage | any | any | any | Retail actors execute lifecycle; Spartan bot count reported separately (C5.4). |

Each row should record: respawn timer per death, score path, victory tick, team index of every participant, and
the qualified population row used. Use the fixed qualification seeds from the plan.

## 7. Open questions and unverified points

- **Team assignment path:** the code that first sets `team_index` for a new human in a lobby or network game was
  not traced. `players.c:1265` sets team 1 in some path; that context must be read before bots are added.
- **Individual-mode victory:** `multiple_teams_alive()` returns TRUE when `players_in_game() <= 1` and otherwise
  looks for two distinct team indices. In an individual mode each player's team index should be unique, which would
  make it true with two or more players. Check `team_index` values in individual modes before relying on it.
  Individual modes end by `score_to_win` in each engine's update, which is a separate path.
- **Score-to-win checks** are per engine (slayer 669, race 595/644/1065/1099, oddball 480/818, king 477-482). The
  CTF path was not checked for `score_to_win`; its victory is via `game_engine_ctf.c` captures.
- **Respawn tick accounting:** `respawn_timer` is set in ticks (the respawn values are in seconds in the builders;
  whether they are converted is not traced).
- **Odd-man-out** (`odd_man_out`) is FALSE in every builder; `game_engine_player_is_odd_man_out` is not analysed.
- **Custom Edition vehicle placement** (`custom_edition_caches.md`, "Multiplayer vehicle placement"): vehicles are
  placed by the spawn flags of the game type. Bots spawn in vehicles through the same path, so a custom map's
  vehicles depend on the variant's `vehicle_set`. Not needed for stock maps.
- **HCU header mismatch:** `hcu_local_variant` has no team switch. Add one before C5 qualification.
- **Bot cap:** `HCU_LOCAL_BOT_SLOTS 4u` against the plan's "four local plus four bots" is consistent only if the
  profile allows four bots; confirm.
- **halo-ps2 is a different project.** Its ADR-010 ("campaign only, no multiplayer") does not apply to the HCU
  fork. The HCU plan's scope amendment (2026-10-21) governs.

## 8. Documents read

- `submodules/halo-ce-universal/AGENTS.md`, `docs/custom_edition_caches.md`, `docs/mods.md`.
- `submodules/halo-ps2/docs/01` to `14` (architecture, specs, decisions, roadmap, data, engine, hardware check,
  xbox reference, format sections, and `reports/*`). These describe the PS2 port and contain no bot or team
  design; ADR-010 excludes multiplayer for that port.
- `submodules/ps2sdk/docs/code.css` (styling only).
- `plans/7.hcu-remake-m2-m4.md` C5 and C6 steps; `src/stream/hcu_local_setup.h`.
- `submodules/halo-64/port/n64/game/n64_bots.c` header and `source/game/player_queues_new.c` hook (reference only).

Not read in full: the `source/ai/` tree (scripted AI, not used for player bots), `network_coop.c` and
`coop_enemies.c` (cooperative enemy handling for the network game, likely relevant to C5 cooperative modes but
outside this step's scope), and the CE menu and lobby team-selection code.
