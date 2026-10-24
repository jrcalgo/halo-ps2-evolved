# m3_player_movement_auditor

## Mission

Audit Halo CE player control and biped movement against the parent port’s locked behavioral contract (`docs/player-movement.md`) and the intended M3 HCU integration path (`plans/5.hcu-remake.md` §M3). Identify gaps between (a) retail CE semantics in `submodules/halo-ce-universal`, (b) the parent reference implementation in `src/game/`, and (c) PS2 platform input (`submodules/halo-ps2/engine/src/platform/pad.c`, HCU `port/ps2/src/ps2_input.c`). Propose parity fixtures for the main agent; report-only, no gate closure.

## Inputs examined

| Area | Paths / symbols |
|------|------------------|
| Parent contract | `docs/player-movement.md` |
| M3 plan | `plans/5.hcu-remake.md` (M3 steps 1–5, exit gate) |
| Parent movement | `src/game/move.c`, `src/game/move.h`, `src/game/pad.c`, `src/game/pad.h` |
| Parent collision sweep | `src/game/pill.c`, `src/game/collide.c`, `src/game/collide.h`, `src/game/collpack.c` |
| Parent EE play loop | `src/game/play_ee.c` (`mover_tick_map`, `pad_to_command`, `flycam_update` wrap) |
| Parent tests | `tests/test_move.py`, `tests/test_pad.py`, `tests/test_player.py`, `tests/test_collide.py`, `tests/test_gameplay_render.py`, `tests/move.c`, `tests/pad_main.c`, `tests/player_main.c`, `tests/gameplay_path.c` |
| CE tick shell | `submodules/halo-ce-universal/source/game/game.c` (`game_tick`, `units_update` ordering) |
| CE player control surface | `submodules/halo-ce-universal/source/game/player_control.c`, `source/game/players.c` (cited in `docs/player-movement.md`, not fully walked) |
| CE biped physics blend | `submodules/halo-ce-universal/source/units/bipeds.c` (~3777–3863 player-information blend, ~2583–2585 floor bias, ~1864–1938 `biped_jump`) |
| CE input | `submodules/halo-ce-universal/source/input/input_xbox.c` (`fix_dead_zone`, `GAMEPAD_STICK_DEAD_RANGE`, analog/binary button ingest) |
| CE gravity | `submodules/halo-ce-universal/source/physics/physics.c` (`global_gravity`) |
| HCU PS2 input adapter | `submodules/halo-ce-universal/port/ps2/src/ps2_input.c`, `port/ps2/include/halo_ps2_input.h`, `tests/test_hcu_ps2_input.py`, `tests/hcu_ps2_input_main.c` |
| PS2 pad service | `submodules/halo-ps2/engine/src/platform/pad.h`, `pad.c` (`pad_poll`, `pad_poll_players`, `pad_read_sample`) |
| Closure / bridge status | `docs/hcu-ps2-closure.md`, `plans/5.hcu-remake.md` (XInput adapter uncalled) |
| Memory budget | `config/memory-budget.json` (`frame_scratch` 393216 bytes) |
| Evidence baseline | `docs/investigations/_prompt_contract.md` (parent HEAD `a2575e9…`, HCU HEAD `c406a41…`) |

## Findings

### 1. Two authorities today: parent `mover` vs CE `game_tick`

M12 closed on the **parent** stack: `move_cmd` → `mover_tick_map` → `collide_move_pill` over a converted structure BSP (`docs/player-movement.md`). The EE play build links that stack via `tools/ee-world.mk` (`move.o`, `pad.o`, `pill.o`, `collide.o`) and steps it inside `play_ee.c`’s `__wrap_flycam_update` (`mover_tick_map` at `src/game/play_ee.c:554`), not inside CE `game_tick`.

M3 requires the opposite: `game_initialize` / `game_tick` at 30 Hz with CE object datums and CE collision (`plans/5.hcu-remake.md` §M3.1–3.4). HCU PS2 `port.json` still lists only a thin port layer (`ps2_input.c`, `ps2_local.c`, …) and does **not** yet subsume the parent `src/game` movement modules. Until CE units/bipeds and `collision_move_pill` own the player, the parent implementation remains the **behavioral reference** and the **production authority** on the play ELF.

### 2. Parent movement matches documented CE constants (Blood Gulch / cyborg_mp)

`src/game/move.h` hard-codes the same matg and `cyborg_mp` scalars documented in `docs/player-movement.md` (run 2.25 / sneak blend, jump `0.07`, camera 0.62/0.35, pill 0.70/0.50 height, radius 0.2, gravity `0.0035651792`, ground bias `1/128`, crouch step `1/6`).

`mover_tick_map` (`src/game/move.c:174–291`) implements:

- Gradual crouch blend (`blend_crouch`, six ticks to full crouch).
- Player-information speed blend keyed off throttle sign and crouch (same structure as `bipeds.c:3817–3846`).
- Ground-aligned velocity with uphill/downhill scaling (`MOVE_*HILL_*` constants).
- Structure pill sweep via `collide_move_pill` with feet at `pos + radius` and height `pill_height(crouch)`.
- Out-of-world recovery using `collide_point_empty` and `last_safe`.

`mover_tick` (`src/game/move.c:57–150`) is a **simplified** probe callback path (instant crouch, axis-aligned blocking, no BSP pill). Host `tests/move.c` exercises physics tolerances without BSP geometry.

CE’s player blend at `bipeds.c:3777–3849` adds behaviors **not** in the parent `move_cmd` path:

- `body_stun` and `stun_movement_penalty` scaling (`3813–3816`).
- Per-player `speed_multiplier` (`3805–3809`).
- Alert-seat walking mode (`3833–3838`, `walking_speed` 0.512).
- Cinematic / `_biped_uses_old_player_physics_bit` override block (`3791–3803`).
- `game_players_are_double_speed()` scaling (`3857–3863`).
- Jump via `biped_jump` with actor aim arbitration, stun on jump magnitude, cheats (`bipeds.c:1864–1938`) — parent only sets `vel[2] = MOVE_JUMP_VELOCITY` when grounded (`move.c:208–211`).

These CE-only paths are **intentionally out of scope** for M12 (`docs/player-movement.md` §Limits) but **in scope** for full M3 CE ownership unless explicitly classified as port exceptions.

### 3. Collision: structure-only pill; CE `collision_move_pill` not wired

Parent `pill.c` documents structure-only `collision_move_pill` with caller scratch, 256 features / 128 BSP depth caps (`src/game/collide.h:65–66`, `pill.c:1–5`). `collide_pill_scratch_bytes()` returns `sizeof(pill_scratch)` (`pill.c:706–709`); `tests/test_player.py` asserts measured scratch **&lt; 393216** frame scratch and tables fit BSP spare — consistent with `docs/player-movement.md` (47,644 bytes cited; exact value is build-time `sizeof`, not re-derived here).

Gaps vs CE retail:

- No dynamic object, actor, or biped-biped collision in the player pill (`docs/player-movement.md` §Limits; M3.4 requires CE routes for object/actor/projectile tests).
- Parent `collide.c` is a port of structure segment tests, not the full CE `collision_bsp.c` / `collisions.c` graph (`plans/5.hcu-remake.md` §M3.4).
- `mover_tick_map` ignores `render_schedule` (`move.c:193`, `move.h:80`) — parent already proves render-schedule invariance for **simulation** (`tests/player_main.c:259–266`); M3 exit gate extends that to **CE** state after snapshot insertion.

### 4. Input: three parallel pipelines, none end-to-end on PS2

**A. Parent diagnostic path (what runs in `--play`):**

- `halo-ps2` `pad_poll` fills `fly_input` with **linear** sticks `(v - 127.5) / 127.5` (`pad.c:46–46`, `143–146`) — **no** `fix_dead_zone(9000)`.
- `play_ee.c` rescales `fly_input` to int16 and calls `pad_to_command` (`play_ee.c:536–542`), which **does** apply `PAD_DEAD_ZONE 9000` and sensitivity-3 look rates (`src/game/pad.h:11–16`, `pad.c:17–28`).
- Jump/crouch: Cross → `cmd.jump`, Circle → `cmd.crouch` (`pad.c:22–23`), matching the doc’s DualShock binding (`docs/player-movement.md:29`).

**B. CE retail path (target for M3):**

- `input_xbox.c` applies `fix_dead_zone` to XInput stick shorts after `XInputGetState` (`input_xbox.c:964–975`, dead range `9000` at line 132).
- Analog face buttons map through `bAnalogButtons` with Xbox ordering A,B,X,Y,… (`input_xbox.c:271–280`; `XINPUT_GAMEPAD_A` is index `0` in `port/include/xdk/xdk_xbox.h`).
- Look rates come from profile `look_sensitivity` tables (`player_ui.c:1045–1053`; default index 3 → yaw 120°/s, pitch 60°/s — matches `src/game/pad.h`).

**C. HCU PS2 XInput adapter (host-tested, not bridged):**

- `ps2_input_publish_dualshock` maps PS2 **digital** button bits to a subset of `wButtons` (DPAD, START, BACK, thumbs only) (`ps2_input.c:67–74`). Face buttons are **not** mirrored to `wButtons`; CE expects them via `bAnalogButtons` when the publisher passes the 8-byte pressure array (`ps2_input.c:79`, `input_xbox.c:937–940`).
- Sticks: `(byte - 128) * 256` with LY inverted (`ps2_input.c:19–27`, `76–77`) — **no** `fix_dead_zone`; CE applies dead zone **after** read (`input_xbox.c:964–975`). That can be correct if publishing raw XInput-scale sticks, but it differs from the parent `pad_poll` → `pad_to_command` chain.
- `docs/hcu-ps2-closure.md` and `plans/5.hcu-remake.md` state explicitly: parent pad service does **not** call `ps2_input_publish_*`; no machine/game-loop bridge exists.

**D. Multitap / 1–4 players:**

- `pad_poll_players` defines stable four-player port/slot mapping (`pad.c:116–133`).
- Parent play and movement tests are **single-player** only.
- HCU adapter holds four ports (`ps2_input.c:5`, `PS2_INPUT_PORTS`); multitap join semantics are untested against CE `player_control` / `players.c`.

### 5. `player_control.c` scope vs parent `move_cmd`

`docs/player-movement.md` §Source audit: `player_control.c` covers aiming, zoom, weapon desire, camera, button inhibition — not duplicated in `move.c`/`pad.c`. CE `game_tick` runs `units_update` before AI and first-person weapon updates (`game.c:358–382`). Parent `play_ee.c` interleaves movement with M13 combat modules on the same tick (`play_ee.c:543–554`), which is a **different tick ordering** than CE.

For M3, movement parity is insufficient without fixtures for: facing/throttle from `player_control_update`, camera vs unit facing (`_unit_control_look_dont_turn_bit` in biped physics), and weapon/grenade actions that share the same input frame.

### 6. Memory and allocation posture

- Parent movement modules assert no `malloc` in `move.c`/`pill.c`/`collide.c` (`tests/test_player.py:113–116`); pill scratch is caller-owned (`collide.h:62–64`).
- `play_ee.c` still `malloc`s collision pack and scratch at init (`play_ee.c:423–470`) — called out in `plans/5.hcu-remake.md` §4 as a migration target, not M3-compliant steady state.
- M3 exit gate: movement fixtures must stay inside assigned **dynamic** and **frame_scratch** regions (`plans/5.hcu-remake.md` §M3 exit gate). Current parent scratch fits `frame_scratch` per `test_player.py`; CE `collision_move_pill` scratch size on HCU path is **unknown** until linked (do not invent).

### 7. PS2 “parent behavior” summary

| Topic | Parent (M12 reference) | PS2 platform today | CE (M3 target) |
|-------|------------------------|--------------------|----------------|
| Sim authority | `mover_tick_map` | Same in play ELF | `units_update` / biped physics + CE collision |
| Tick rate | 30 Hz (`MOVE_TICKS_PER_SECOND`) | `play_ee` increments `s_play_sim_tick` per wrapped frame | `TICKS_PER_SECOND` in `game_tick` |
| Stick dead zone | Applied in `pad_to_command` only | Not in `pad_poll` | In `input_xbox.c` after XInput |
| Jump / crouch | Cross / Circle → `move_cmd` | Same in play path | Analog A/B (+ full action map) |
| Look sensitivity | Fixed “3” in `pad.h` | Same | Profile tables in `player_ui.c` |
| 4-player input | Not tested | `pad_poll_players` + HCU 4-port XInput | CE local player slots |
| BSP collision | Converted `COLL` pack | Same pack in play | CE cache BSP + `collision_move_pill` |
| Object collision | None | None | Required in M3.4 |

### 8. Documented tolerances (parent reference fixtures)

From `docs/player-movement.md:31` and `tests/test_player.py` / `tests/move.c`:

- Ground contact within ~8 mm of spawn after settle.
- Jump initial `vz` ≈ `0.07 - gravity` (`1e-5`).
- Jump apex height band (~0.65–0.72 m above settle).
- Walk distance band on first start facing (30 ticks).
- Crouch eye 0.35, height 0.50 after six ticks.
- Wall fast-step stop before surface + radius; ceiling penetration ≤ 0.05; slope rise ≥ 0.02 over 30 ticks with ≥ 20 grounded ticks.
- Render schedule argument 0/1/2 yields identical feet (`player_main.c:259–266`).

These are the **locked parent contract** for migration; CE parity fixtures should either match them or document CE-intentional deltas with source citations.

## Interface contracts for the main agent

1. **Simulation owner (M3):** After integration, player feet/velocity/ground contact come from CE biped object state updated inside `game_tick`, not from a parallel `mover` struct. Parent `mover` fields map conceptually to: object translation, `translational_velocity`, biped crouch, grounded/airborne flags, support plane — exact datum offsets are for `m3_object_lifecycle_auditor` / ABI work.

2. **Input boundary:** At each simulation tick, for each local player index `0..3`:
   - Read `pad_sample` via `pad_poll_players` (`pad.h:37`).
   - Publish with `ps2_input_publish_dualshock(port, …)` or `ps2_input_publish_state` (`halo_ps2_input.h:7–14`) **before** CE input abstraction runs.
   - Ensure `analog[0..7]` follows Xbox order populated in `pad.c:91–98` (Cross → A, Circle → B, …).
   - Do not apply `fix_dead_zone` twice; pick either pre-publish scaling or CE post-read (retail applies once in `input_xbox.c:964–975`).

3. **Collision boundary:** Player sweeps go through CE `collision_move_pill` (and related BSP queries) with scratch allocated from `frame_scratch` (or named sub-arena), size ≥ CE/port measured `collide_pill_scratch_bytes` equivalent. Parent `collide_move_pill` signature (`collide.h:88–95`) is the reference for structure-only phases; object/actor phases attach per M3.4.

4. **Render decoupling:** Snapshot builder reads CE state after tick; renderer may skip frames. `render_schedule` must not feed back into simulation (parent already ignores it in `mover_tick_map`; CE path must preserve the same invariant).

5. **Constants source:** Gameplay speeds, jump, pill dimensions, and gravity for **parity tests** should be read from map/tags (`convert_collision` TAGS section / matg / cyborg_mp) where possible (`tests/test_player.py:104–112`), not only from `move.h` macros — guards against map-specific drift when M2 loader lands.

## Recommended tests / fixtures

### Tier A — Retain and extend (parent reference, pre-CE)

| Fixture | Basis | M3 use |
|---------|--------|--------|
| `tests/move.c` via `test_move.py` | Point-probe physics | Regression while swapping `mover_tick` implementation; add CE-host equivalent later |
| `tests/pad_main.c` via `test_pad.py` | Dead zone 9000, sensitivity 3, invert | Golden values for **post-bridge** stick shorts into CE; add cases for partial deflection (e.g. 10000, -12000) |
| `tests/player_main.c` via `test_player.py` | Blood Gulch COLL pack, full movement matrix | **Primary migration oracle**: same stdout keys (`settle`, `jump`, `land`, `walk`, `crouch`, `recover`, `schedule`, `slope`, `ceiling`, `corner`, `bench`) hashed per tick |
| `tests/gameplay_path.c` via `test_gameplay_render.py` | Pad-driven eye path | Visual smoke; add normalized trace hash (positions only) for CE comparison |
| Render-schedule triple tick | `player_main.c:259–266` | Require identical CE biped origin after N ticks with 0/1/2 dummy render passes inserted |

Proposed new **parent-side** fixture (report-only sketch): `tests/movement_trace_main.c` emitting one line per tick: `tick feet_x feet_y feet_z vx vy vz grounded crouch eye flags` for a fixed script (settle 90, jump, land, walk 30, crouch 6, wall burst, OOW recover). Store SHA-256 of trace in repo when map asset present. Main agent implements when wiring CE.

### Tier B — Input bridge (PS2 → HCU → CE)

| Fixture | Description |
|---------|-------------|
| `pad_sample` → XInput round-trip | Extend `tests/hcu_ps2_input_main.c`: for each of 4 logical players, feed synthetic `pad_sample` bytes matching `pad.c:91–98` ordering; assert `XInputGetState` analog thresholds cross CE’s `input_update_analog_button_state` behavior (host compile `input_xbox.c` slice or harness). |
| Dead-zone equivalence | Table: raw stick short → after `fix_dead_zone` → compare parent `pad_apply_dead_zone` at same short (`pad.c:3–9` vs `input_xbox.c:353–367`). |
| `pad_poll_players` mapping | Host simulation of port0 multitap on/off matrices (`pad.c:118–131`); assert published to ports 0–3 expected. |
| Missing face analog | Digital-only press: `analog[0]=0xFF` when Cross down — CE must still see jump. |

### Tier C — CE authority (post `game_tick` integration)

| Fixture | Description |
|---------|-------------|
| Host `game_tick` movement script | Minimal map load + one local player + scripted input blob (pattern: `player_control_action_test_*` in `player_control.c` symbol list). Hash: player unit origin, velocity, crouch, airborne flag each tick. |
| CE vs parent trace diff | Run Tier A trace on parent `mover_tick_map` and CE biped for same `move_cmd`/facing script; diff with tolerance table from `docs/player-movement.md:31`. Flag known deltas: stun off, no actors, no alert seat. |
| Tag-derived constants | Reuse `convert_collision` TAGS extraction (`test_player.py:102–112`) against CE-loaded matg/cyborg_mp for the same map. |
| Four-player idle/walk | Four slots connected; 30 ticks walk forward; assert distinct player indices, no cross-talk on XInput ports. |
| Scratch high-water | One tick worst-case pill on Blood Gulch: record `collide_pill_stats` + bytes used ≤ budget owner for frame scratch (measure CE path; compare to parent 47644 aggregate report). |

### Tier D — M3 exit gate explicit

1. **Render-schedule invariance:** Insert 0, 1, or 3 no-op “render” calls between `game_tick` invocations; normalized simulation hash unchanged.
2. **No steady-state heap:** Movement/collision path does not call `malloc` after map load (contrast `play_ee.c:423–470`).
3. **Dual emulator:** Same trace hash PCSX2 interpreter vs recompiler when CE path runs on EE (deferred to main agent; not claimed here).

## Dependencies on other investigators

| Investigator | Dependency |
|--------------|------------|
| `m3_collision_owner_auditor` | CE `collision_move_pill` scratch size, object/actor collision ordering vs parent `pill.c`; when parent `collide.c` may retire. |
| `m3_object_lifecycle_auditor` | Player datum / biped handle mapping, spawn at `player_start`, generation-safe handles for snapshot. |
| `m3_snapshot_render_auditor` | Camera eye from CE `player_control_get_unit_camera_info` vs parent `pos + eye`. |
| `m3_first_person_pose_auditor` | Facing vs aim; interaction with `_unit_control_look_dont_turn_bit`. |
| `m1_pad_multitap_auditor` | Hardware multitap discovery vs `pad_poll_players` policy. |
| `m2_map_conversion_auditor` / loader | BSP + collision residency when CE owns cache BSP instead of `COLL` hp2 pack. |

## Open questions

1. **Locked control contract:** Is the parent’s Cross/Circle jump/crouch binding normative for PS2, or must CE’s full Xbox action map (triggers, grenade, zoom) be matched before M3 movement is “closed”?
2. **Dead-zone single owner:** Should PS2 sticks be normalized in `pad_poll`, in `ps2_input_publish_dualshock`, or only in CE `input_xbox.c`? Current play path double-shapes sticks (`pad_poll` linear → `pad_to_command` dead zone).
3. **HCU `ps2_input_publish_dualshock` face buttons:** Confirm retail CE reads jump/crouch only from analog bytes, never from `wButtons`, for PS2-published state — if not, adapter needs digital face mapping.
4. **CE scratch size:** What is `sizeof` CE collision workspace for `collision_move_pill` in the HCU PS2 link? Parent reports 47,644 bytes; do not assume equality.
5. **Alert / stun / double-speed:** Are campaign or Slayer variants required in M3 movement gate, or only stock Blood Gulch MP cyborg_mp?
6. **Tick ordering:** When CE owns simulation, do M13 modules in `play_ee.c` run inside `game_tick` sections or remain outside until M4/M6? Movement tests may show divergent combat+move coupling until ordering is unified.
7. **Square/Triangle/R1** in movement gate: Parent play uses Triangle weapon cycle, R1 fire, L2 grenade (`play_ee.c`) — outside `docs/player-movement.md` but coupled to same tick as movement.

## Handoff summary

- **Authoritative today:** Parent `src/game/move.c` + `pill.c` + `pad.c` on Blood Gulch structure collision; documented in `docs/player-movement.md` with strong automated fixtures (`test_move`, `test_pad`, `test_player`, gameplay path).
- **M3 gap:** CE `game_tick` + biped physics + CE `collision_move_pill` + input bridge (`pad_poll_players` → `ps2_input_publish_*` → `input_xbox.c`) are not integrated; HCU XInput adapter is host-tested only (`docs/hcu-ps2-closure.md`).
- **Largest behavioral deltas to plan for:** player_control/aim/zoom/weapon input, stun/double-speed/alert seat, actor-mediated jump, object collision, CE tick ordering vs `play_ee.c`, and stick dead-zone pipeline consistency across PS2/HCU/CE.
- **Parity strategy:** Treat `tests/player_main.c` stdout trace + per-tick hash as the migration oracle; add input-bridge and CE `game_tick` hashes; extend render-schedule invariance to CE state; measure scratch against `frame_scratch` after CE collision is linked.
- **Do not:** Close M3 gates from this report; invent CE pool/scratch sizes; or treat parent play `malloc` as acceptable steady state.

## Corroboration

### Agreements

- **m1_pad_multitap:** Input bridge gap is the primary M3 movement blocker on integrated path — unanimous.
- **m3_collision_owner:** CE `collision_move_pill` is production sweep API; parent `pill.c` remains oracle.
- **m3_snapshot_render:** Render-schedule invariance not yet proven for CE `game_tick` — movement hashes must use sim tick, not presentation pass count.
- **m0_runtime_ownership:** Parent `move.c` is fixture until CE path hashes match tier-A fixtures.
- **m1_startup / m1_platform:** Movement integration follows M1 boot + cache adapter — no movement parity on guest until precache path real.

### Conflicts

- None on authority direction; **tick ordering** vs `play_ee.c` modules remains open question §6 — defer to M4/M6 planning.

### Updated handoff

1. Tier-A: wire pad bridge → CE `game_tick` on host harness with Blood Gulch structure collision (CE BSP loaded).
2. Keep `tests/player_main.c` trace as migration oracle; add CE hash column when bridge lands.
3. Measure pill scratch against `frame_scratch` after CE collision linked (**m1_dma**).
