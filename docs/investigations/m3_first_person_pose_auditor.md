# m3_first_person_pose_auditor

## Mission

Audit how **Halo CE Universal (HCU)** first-person weapon **simulation and animation state** relates to the **parent PS2 first-person pose adapter** (`hold_pose` / `play_fp` linker wraps), in light of the **hybrid component-table rows** in `plans/5.hcu-remake.md` (energy sword and gravity rifle view orientation; effect/HUD/FP simulation vs FP draw). Produce a report-only boundary map for M3 snapshot work and M4/M6 retirement of duplicate paths. Do not close M0–M3 gates.

Evidence baseline (Round 1): parent `a2575e957feefbdff27febedabf60590401e6bcc`, HCU `c406a4149ddebae4f45462ce4c1e8d9cce0567c2`, `halo-local.elf` SHA-256 `e45b4719d35450a77f2a541a7ed8abb877e5fbef495fc918539f8da91de597a2` (if present).

## Inputs examined

| Area | Paths |
|---|---|
| Migration plan / component table | `plans/5.hcu-remake.md` (rows 29–32, 41–47, M3 step 5, M4 step 4, M6 step 4) |
| Pose investigation history | `plans/3.sword-fuel-rod-orientation.md` |
| Source ownership | `docs/source-audit.md` |
| M13 tag crosswalk (FP graphs) | `docs/m13-step10-fuel-rod-flight-investigation.md` (ammo/FP table §) |
| HCU tick + FP simulation | `submodules/halo-ce-universal/source/game/game.c`, `source/interface/first_person_weapons.c`, `source/interface/first_person_weapons.h`, `source/render/render.c`, `source/render/render_objects.c` |
| HCU weapon-set / cut-weapon notes | `submodules/halo-ce-universal/source/game/game_engine.c` |
| Parent pose data + adapter | `src/game/hold_pose.h`, `src/game/sword_idle.h`, `src/game/carbine_idle.h`, `src/game/flak_idle.h`, `src/game/play_fp.c`, `src/game/play_fp.h` |
| Parent link / wraps | `tools/ee-world.mk` |
| Stock PS2 FP consumer | `submodules/halo-ps2/engine/src/sim/fpview.c`, `sim/fpview.h`, `render/obj_render.c`, `engine/src/main.c` |
| Fixtures | `tests/test_hold_pose.py`, `tests/hold_pose_main.c`, `tools/play_weapons.py` |
| PS2 HCU port (snapshot) | `submodules/halo-ce-universal/port/ps2/` — **no** `fpview` / first-person snapshot symbols found (grep) |

## Findings

### 1. Component table: three related rows, one presentation exception

`plans/5.hcu-remake.md` fixes ownership as follows:

| Component | Source | Hybrid sides |
|---|---|---|
| Energy sword and gravity rifle **view orientation** | **hybrid** | Modified HCU weapon state; **halo-ps2 draw**; **accepted orientations stay the parent pose adapter** (`plans/5.hcu-remake.md:29`) |
| Effect simulation, HUD decisions, and **first-person weapon simulation** | **halo-ce-universal** | — (`plans/5.hcu-remake.md:31`) |
| Effect sprites, HUD quads, and **first-person draw** | **hybrid** | HCU decisions; **halo-ps2 GS/VU1** (`plans/5.hcu-remake.md:32`) |

Locked decisions in the same plan:

- Parent `src/game` is **not** a production source; it remains a **comparison fixture** until M6 (`plans/5.hcu-remake.md:47`).
- The **sword and gravity-rifle pose adapter** is the **only presentation exception** that survives M6; the **fuel-rod pose adapter is removed** (`plans/5.hcu-remake.md:47`, `plans/5.hcu-remake.md:60`, `plans/5.hcu-remake.md:177`).
- `sim/objects`, `sim/skeleton`, and `sim/fpview` become **read-only snapshot consumers** of CE state (`plans/5.hcu-remake.md:55`, M3 step 3 `plans/5.hcu-remake.md:146`).

**Current repository reality:** production play/world EE images still link parent `play_fp.o` and **wrap** `fpview_place`, `fpview_tick`, and `objects_pose_model` (`tools/ee-world.mk:50-52`). HCU `first_person_weapons_*` is in the **345-unit closure** but is **not** wired through a post-tick snapshot into `fpview_t` on the parent play path. The authoritative-vs-adapter split described in the plan is **architectural target**, not **integrated runtime** at M3.

### 2. HCU: first-person weapon simulation (tick-owned)

**Tick placement.** `game_tick` calls `first_person_weapons_update()` inside `game_tick.first_person`, after `antennas_update` and before `game_engine_update` (`submodules/halo-ce-universal/source/game/game.c:378-383`). Random seed is locked for that section (`game.c:379-382`).

**Per-player state.** `struct first_person_weapon` is **0x1EA0** bytes per local player (`first_person_weapons.c:241-288`, `verify_first_person_weapon_size`). Salient fields for migration:

- Identity: `unit_index`, `weapon_index`, `visible`, `state`, overlay/moving/overcharged animation states (`first_person_weapons.c:243-255`).
- Presentation-adjacent simulation: `firing_push_back`, 2D position/turning and velocities, `render_forward`, `render_facing`, `render_position`, interpolation indices (`first_person_weapons.c:256-270`).
- **Authoritative posed skeleton for draw:** `node_orientations`, `original_node_orientations`, **`node_matrices[MAXIMUM_NODES_PER_ANIMATION]`** at offset **0x108C** (`first_person_weapons.c:271-273`, `verify_first_person_weapon_node_matrices_offset`).
- Graph alignment: `weapon_node_remapping_table_valid`, `hands_node_remapping_table_valid`, remapping tables (`first_person_weapons.c:274-279`).

**Update pipeline (`first_person_weapons_update`).** For each local player with a valid player index: sync unit (`first_person_weapon_new_unit` if needed), switch weapons if `weapon_index == NONE`, then `first_person_weapon_update` (`first_person_weapons.c:830-853`).

**Weapon attach preconditions (`first_person_weapon_switch_weapons`).** HCU only commits `first_person_weapon->weapon_index` when **both**:

1. `weapon_definition->weapon.interface_definition.first_person_model.index != NONE`
2. `weapon_definition->weapon.interface_definition.first_person_animations.index != NONE`

…and the animation graph has `first_person_weapon_animations`, and **both** remapping tables build successfully (`first_person_weapons.c:1615-1673`). If any step fails, the FP weapon slot stays empty (`weapon_index` remains `NONE` after switch).

**Implication for M13 specials (tag audit):** supplied map audit records **no first-person graph** for fuel rod (#10), gravity rifle (#11), or energy sword (#12) (`docs/m13-step10-fuel-rod-flight-investigation.md:931-933`). Under stock CE switch rules, those weapons **do not** get a committed `first_person_weapon` animation state at all unless the HCU fork adds tags, synthetic graphs, or a `port:` bypass—planned as **modified halo-ce-universal** gameplay for sword/gravity (`plans/5.hcu-remake.md:28-29`, M4 step 4 `plans/5.hcu-remake.md:157`).

**Per-tick animation (`first_person_weapon_update`).** When `weapon_index` is valid, the update drives `animation_update_render_only` on the weapon FP graph (`state_animation`, optional `moving_animation`, overcharge jitter), reacts to overheat flags, PAL first-person cadence (`pal_tags_first_person_advance`), sound impulses on key frames, and state transitions (`first_person_weapons.c:1807-1938`). This is **simulation-side** animation state, not GS drawing.

### 3. HCU: first-person draw path (render-owned, schedule-sensitive)

**Render-phase matrix build.** `render_window` calls `first_person_weapon_render_update()` before `render_objects()` (`submodules/halo-ce-universal/source/render/render.c:336-342`). That path builds/refines matrices used for drawing (see `first_person_weapon_build_node_matrices`, `first_person_weapons.c:334+`, `first_person_weapon_render_update` at `first_person_weapons.c:647+`).

**Draw gate.** `first_person_weapon_draw` requires, among other checks, `weapon_definition->weapon.interface_definition.first_person_animations.index != NONE` (`first_person_weapons.c:498`). If the index is `NONE`, the entire draw block is skipped—even if a third-person weapon model exists.

When draw proceeds and **both** remapping tables are valid and **first_person_model** is present, CE remaps `first_person_weapon->node_matrices` into model space and calls `render_model` with `_render_model_first_person_bit` (`first_person_weapons.c:526-548`). Separately, **hands** draw uses scenario `game_globals.first_person_interface.hands` with hands remapping (`first_person_weapons.c:574+`).

**Arms-only vs weapon mesh.** Draw can include **hands** when `hands_node_remapping_table_valid` even if weapon model remap fails; weapon mesh draw requires **weapon** remap (`first_person_weapons.c:526-527`). Plan text for fuel rod (“arms-only when tag supplies no FP animation reference”) aligns with **no weapon FP graph** + CE hands path, **not** with parent synthesized third-person fuel rod on a borrowed pose (`plans/5.hcu-remake.md:60`).

**Render vs tick decoupling.** FP simulation advances on `game_tick`; matrix refresh for drawing happens on render passes. M3/M5 gates require **simulation hash invariance** across zero/one/multiple render passes (`plans/5.hcu-remake.md:148`, `plans/5.hcu-remake.md:188`). FP **node_matrices** are presentation inputs but are produced through CE code that runs in the render schedule as well as tick-driven animation state—snapshot design must record **which fields are tick-frozen** vs **render-refined**.

### 4. Parent halo-ps2: stock `fpview` (pre-adapter)

`fpview_t` holds arms/weapon model and graph indices, animation indices, `weapon_node_offset`, hand marker/node, camera-space `offset`, `arms_frame` / `weapon_frame`, and output `arms_root`, `weapon_root`, `arms_nodes` (`submodules/halo-ps2/engine/src/sim/fpview.h:8-18`).

**Init** resolves models/animations from `scen_player` tags (`fpview_init`, `fpview.c:5-34`).

**Tick** advances arms and weapon clip times at 30 Hz (`fpview_tick`, `fpview.c:50-55`).

**Place** builds camera-attached `arms_root`, samples arms skeleton into `arms_nodes`, sets `weapon_root` from hand node/marker when weapon graph is separate (`fpview_place`, `fpview.c:57-77`).

**Draw** (`obj_render.c:224-243`): if `draw_fp` and `fp->active`, draws arms from `f->arms_nodes`, then weapon with `objects_pose_model(..., &f->weapon_root, &wn)`.

World viewer loop: `objects_tick` + `fpview_tick` on 30 Hz cadence; `fpview_place` every frame (`submodules/halo-ps2/engine/src/main.c:248-253`).

This path is **scenario-driven** and **does not** read CE `first_person_weapon` or weapon datums.

### 5. Parent pose adapter: `play_fp.c` wraps (current port behavior)

Linker wraps (`tools/ee-world.mk:51-52`) intercept:

| Symbol | Parent implementation |
|---|---|
| `fpview_tick` | Delegates to `__real_fpview_tick`, then advances H2 idle frame clocks for hold weapons (`play_fp.c:855-863`) |
| `fpview_place` | Reconfigures `fpview_t` from `host:/weapons.fp` selection + hold rules, then `__real_fpview_place`, then `seat_world_model` (`play_fp.c:956-1018`) |
| `objects_pose_model` | Optional **pose remapping** and **H2 arm replacement** for assault-rifle arms mesh (`play_fp.c:758-837`) |

**Weapon list and hold table.** `HOLDS[]` binds three tag paths to Halo 2-derived tables (`play_fp.c:120-129`):

- Energy sword → `sword_idle.h` (89 frames), seat `play_fp_sword_on_hand`
- Fuel rod → `flak_idle.h` (73 frames), seat `play_fp_flak_on_hand` (see §6 for actual seat path)
- Gravity rifle → `carbine_idle.h` (89 frames), seat `play_fp_carbine_on_hand`

**Orientation constants.** `hold_pose.h` stores frame-0 camera-relative quaternions for carbine (gravity rifle), flak (fuel rod label), and sword (`hold_pose.h:21-39`), with documented H2 provenance (`hold_pose.h:1-12`). Helpers `play_fp_player_from_h2`, `play_fp_seat_hold`, and per-weapon `*_on_hand` apply CE camera basis conventions (`hold_pose.h:42-87`).

**Assault-rifle arms donor.** Sword and gravity rifle replace **arms** animation with H2 idle tables when `is_hold_arms` matches the **assault rifle arms model** (`play_fp.c:744-756`, `790-811`). Fuel rod **excludes** arm replacement (`play_fp.c:751`) and instead borrows **rocket launcher** first-person idle for arms timing (`play_fp.c:747-748`, `994-996`).

**Third-person mesh seating (`seat_world_model`).**

- **Sword:** weapon root from handle on right wrist (`play_fp.c:880-883`, `hold_pose.h:59-62`).
- **Fuel rod:** special branch: sample rocket launcher graph node **7** (`frame gun`), apply −5.2° pitch correction and forward offset along launcher axis (`play_fp.c:885-914`) — **not** `play_fp_flak_on_hand` despite `HOLDS` entry.
- **Gravity rifle:** sample AR graph node 7 at frame 0 for grip anchor, apply `play_fp_hold_quat` via `play_fp_seat_hold` (`play_fp.c:916-933`, `hold_pose.h:77-87`).

**Pose maps.** Retail weapons with CE FP graphs use `weapons.fp` RMP1 maps so graph node order matches model node order (`play_fp.c:729-741`, `813-826`).

**Coupling to parent combat diagnostic.** `play_ee.c` uses `play_fp_*` for gun/projectile profiles (`src/game/play_ee.c` imports per `plans/5.hcu-remake.md:177`); FP presentation is tied to the **same weapon slot** as parent M13 reference firing, not to CE inventory.

### 6. Tag reality vs adapter vs HCU plan

| Weapon | FP graph in supplied audit | Stock CE `first_person_weapon` attach | Parent adapter (today) | HCU-remake target |
|---|---|---|---|---|
| Energy sword | missing (`m13-step10` #12) | Unlikely without fork | H2 89-frame idle on AR arms + sword mesh on wrist | Gameplay in modified HCU; **keep** parent orientation tables for draw |
| Gravity rifle | missing (#11) | Unlikely without fork | H2 carbine idle on arms + `PLAY_FP_Q_CARBINE` seat | Gameplay in modified HCU; **keep** adapter |
| Fuel rod | missing (#10) | Unlikely; draw gate needs FP anim index for weapon mesh | RL-shoulder seat + 3P mesh; flak tables partially wired | **Remove** adapter; generic HCU + **arms-only** if no FP anim (`plans/5.hcu-remake.md:60`) |

**Fuel-rod inconsistency (document for M6 removal).** `HOLDS` still references `flak_idle` and `play_fp_flak_on_hand`, but `seat_world_model` for fuel rod takes the rocket-launcher shoulder branch (`play_fp.c:885-914`) and `is_hold_arms` skips flak arm channels (`play_fp.c:751`). `flak_idle.h` documents H2 flak pose (`flak_idle.h:4-5`). Historical plan notes describe alternate `play_fp_seat_fuel_rod` camera-space seats (`plans/3.sword-fuel-rod-orientation.md` execution log); current `play_fp.c` does not define `play_fp_seat_fuel_rod` (symbol only in plan text). **Do not** treat parent fuel-rod view as a long-term acceptance surface.

**HCU fork gameplay markers.** Pinned HCU only comments that gravity rifle is a cut weapon remapped like flamethrower in weapon-set selection (`game_engine.c:7799-7802`); no dedicated sword/lunge or gravity-rifle flame route was found in `port/ps2` or a quick `source/` grep for implementations. M4 explicitly requires retaining those behaviors in HCU with parent modules as **comparison inputs** (`plans/5.hcu-remake.md:157`).

### 7. M3 snapshot gap (no implementation yet)

M3 step 5 requires a **post-tick snapshot** publishing object transforms, node palettes, **cameras/first-person pose**, HUD work, and effect requests into fixed storage (`plans/5.hcu-remake.md:148`). Contract: snapshot is **read-only**, bounded, and must not allocate (`plans/5.hcu-remake.md:188`).

**Missing today:**

- No `port/ps2` types or builder for FP pose exported from CE.
- Parent renderer still mutates presentation through `__wrap_fpview_*` and reads `play_fp_slot()` from `weapons.fp`, not CE weapon datums.
- `sim/objects.h` still describes `objects_tick` as simulation writer for placed objects (`submodules/halo-ps2/engine/src/sim/objects.h:1-3`, `50-51`)—conflicts with “consume-only” until snapshot lands.

**Minimum FP payload (inferred, not sized):** per local player (1–4): visibility; weapon definition/tag id or datum handle; CE FP animation state indices + frame indices (state/moving/overlay); **`node_matrices` or equivalent posed palette** after tick; hands vs weapon model tag indices; remapping validity flags; camera / `render_position` / `render_facing` if effects depend on them; explicit **adapter key** for sword/gravity presentation override (enum or tag path), applied only on PS2 consumer side.

Pool sizes for snapshot FP records are **unknown** until measured; do not invent capacities in this report.

### 8. Acceptance artifacts already in repo

- `tests/test_hold_pose.py` + `tests/hold_pose_main.c`: oracle checks for carbine/gravity rotation, sword/flak/carbine idle chains (`tests/test_hold_pose.py:11-22`, `hold_pose_main.c:33-95`).
- `plans/3.sword-fuel-rod-orientation.md`: documents H2 extraction provenance and visual acceptance for sword/fuel rod/gravity (parent port scope).
- `tools/play_weapons.py`: lists fuel rod, gravity rifle, energy sword among weapons **without model tag** for FP pack purposes (`tools/play_weapons.py:69-71` comment block ~line 8).

These fixtures characterize **parent presentation**, not HCU tick state parity.

## Interface contracts for the main agent

1. **Simulation owner.** All FP animation state machines, weapon messages from units/weapons, and `node_matrices` progression tied to `game_tick` remain **HCU** (`plans/5.hcu-remake.md:31`, `first_person_weapons_update` in `game.c:378-381`).

2. **Draw owner.** GS/VU1 draws FP arms/weapon from **halo-ps2** `obj_render` reading **`fpview_t`** (or a thin view of snapshot fields), not from direct CE `render_model` on EE (`plans/5.hcu-remake.md:32`, `obj_render.c:224-243`).

3. **Snapshot seam.** After each completed CE tick, publish immutable FP fields needed to populate `fpview_t` **without** calling `play_fp_cycle` or reading `host:/weapons.fp`. Generation-safe handles for weapon/unit if render records cache identity (`plans/5.hcu-remake.md:146`).

4. **Presentation exception (sword + gravity only).** When snapshot weapon path matches energy sword or gravity rifle, PS2 consumer applies **parent** `hold_pose` / idle tables and seating rules **after** consuming CE tick outputs, without feeding back into simulation (`plans/5.hcu-remake.md:29`, `hold_pose.h:31-39`, `play_fp.c:956-1018` as reference algorithm). Constants remain in parent repo until explicitly forked into a **named, versioned** PS2 presentation module; plan says adapter **stays**, not that it must stay in `src/game` forever.

5. **Fuel rod.** Do **not** publish parent RL/flak shoulder pose into production snapshot. If CE tag has no `first_person_animations`, consumer draws **hands only** per CE draw preconditions (`first_person_weapons.c:498`, `plans/5.hcu-remake.md:60`). Remove `fuel rod` entries from `HOLDS` and fuel-specific seat branches when retiring duplicate path (`plans/5.hcu-remake.md:177`).

6. **Render schedule.** Snapshot taken at tick boundary must produce identical **gameplay** hashes when render skips frames or runs multiple `first_person_weapon_render_update` passes; document whether snapshot includes render-refined matrices or tick-end matrices (`plans/5.hcu-remake.md:148`, `render.c:340`).

7. **`objects_pose_model` hook.** Parent pose remapping (`play_fp.c:758-837`) is **presentation**. Equivalent logic belongs in modified `halo-ps2` consumer or post-snapshot adapter, **not** in HCU simulation. CE’s own remapping is `model_remap_node_matrices_to_match_animation_graph` inside `first_person_weapon_draw` (`first_person_weapons.c:529-534`).

## Recommended tests / fixtures

| Test | Purpose |
|---|---|
| Extend host snapshot fixture (new) | Given frozen CE `first_person_weapon` bytes for pistol + shotgun, PS2 stub consumer builds `fpview_t` matching CE node palette within epsilon—**no** `play_fp` |
| `tests/test_hold_pose.py` / `hold_pose_main.c` | Regression lock on **sword/gravity** H2 orientation math when adapter moves out of `src/game` |
| Render-schedule replay | Two traces: one tick with 0 renders, one with 3 `render_frame` equivalents; gameplay hash excludes FP render-only fields |
| Tag-negative weapons | Fuel rod / sword / gravity with audited missing FP graph: assert CE `weapon_index` NONE in stock path; assert fork path sets expected visibility for M4 |
| Parent comparison (until M6) | `WORLD_VARIANT=play` weapon cycle captures for sword/gravity against `plans/3` reference PNG paths—**comparison only** |

Reuse `docs/m13-step10-fuel-rod-flight-investigation.md` table for tag expectations; do not use MAG2 `reload_seconds` as FP timing oracle.

## Dependencies on other investigators

| Investigator | Dependency |
|---|---|
| `m3_snapshot_render_auditor` | Snapshot record layout, `frame_scratch` placement, split-screen per-player FP slots, render-pass invariance |
| `m3_object_lifecycle_auditor` | Unit/weapon datum handles in snapshot; equip/swap ordering vs `first_person_weapon_switch_weapons` |
| `m3_player_movement_auditor` | Camera basis fed to `fpview_place`; `fp_offset` from scenario vs CE camera |
| M4 combat investigators | Modified HCU sword/gravity gameplay without duplicating parent `gun.c` semantics; marker/matrix queries via `first_person_weapon_get_node_matrix` |
| M2 tag loader | When FP models/graphs for specials are synthesized or loaded from map image |

## Open questions

1. **Modified HCU FP for sword/gravity:** Will fork add synthetic `first_person_model` / `first_person_animations` tags, or extend `first_person_weapon_switch_weapons` with a `port:` path for missing graphs? Switch logic today is strict (`first_person_weapons.c:1615-1616`).

2. **Tick vs render matrices:** Should snapshot export `node_matrices` at end of `first_person_weapon_update` only, or after `first_person_weapon_render_update`? Effects/particles attach to FP weapon nodes in CE—need call-site audit.

3. **Multiplayer local players:** CE stores `first_person_weapons[MAXIMUM_NUMBER_OF_LOCAL_PLAYERS]`; `fpview_t` in world viewer is singular (`main.c:40`). Snapshot must define **per-window** FP records for split screen (plan: 1–4 players, `plans/5.hcu-remake.md:148`).

4. **Hands-only fuel rod:** Confirm CE still draws scenario hands when weapon FP anim index is `NONE` but unit holds fuel rod—depends on visibility and hands remap without weapon remap (draw code paths `first_person_weapons.c:498-576`).

5. **Adapter ownership location:** M6 retains adapter behavior but removes parent `src/game` from link (`plans/5.hcu-remake.md:177`). Where do `sword_idle.h` / `carbine_idle.h` live in production—`halo-ps2` engine vs small `hcu_ps2_fp_pose` object file?

6. **`PLAY_FP_FLAK_MESH_X`:** Still defined in `flak_idle.h` (`flak_idle.h:587`) but fuel-rod seat path in `play_fp.c` uses RL shoulder logic—confirm no production reliance before deleting flak hold assets.

## Handoff summary

HCU already owns a full first-person **simulation** stack (`first_person_weapons_update`, large per-player struct, tick-ordered before game rules). **Drawing** on Xbox is CE `render_model`; on PS2 target it is **hybrid**: CE decisions encoded in a **post-tick snapshot**, **halo-ps2** `fpview` + `obj_render` execution. Today’s integrated world/play path instead **wraps** stock `fpview` with parent `play_fp.c` and Halo 2 pose tables for sword/gravity (and a legacy fuel-rod shoulder hack), linked via `ee-world.mk`—contrary to M3/M6 direction but required as **comparison** until snapshot + HCU parity exist.

For M3, treat **CE tick outputs** as the only authoritative animation state; treat `hold_pose.h` / idle headers as **read-only presentation oracles** for two weapons; **delete** fuel-rod pose from the production story and align with CE arms-only rule when `first_person_animations.index == NONE`. Do not conflate parent `play_fp` weapon cycling with CE inventory. Gate closure remains with measured snapshot bytes and render-schedule tests—not this document.

## Corroboration

### Agreements

- **m3_snapshot_render:** FP draw consumes snapshot fields; parent `play_fp.c` wraps are comparison-only until M6.
- **m3_object_lifecycle:** Player/unit identity from CE handles — not parent weapon cycle in `play_ee.c`.
- **m0_runtime_ownership:** Sword/gravity pose tables are presentation adapter exception, not sim authority.
- **m1_dma_layout_auditor:** FP pose matrices repack at upload if included in snapshot — not raw CE struct DMA.

### Conflicts

- None on CE sim authority; **adapter file location** (halo-ps2 vs small port object) deferred to Round 3 / M6.

### Updated handoff

1. Snapshot must include per-player FP animation indices/matrices from `first_person_weapons_update` outputs.
2. Retire fuel-rod shoulder hack from production path when snapshot lands; keep headers as oracles for sword/gravity only.
3. Do not gate M3 FP on parent `play_fp` weapon cycling parity.
