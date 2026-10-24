# m3_collision_owner_auditor

## Mission

Name the **single production collision authority** for the PS2 hybrid port (HCU `submodules/halo-ce-universal/source/physics/`), enumerate every **competing parent path** (`src/game/collide.c`, `collpack.c`, `pill.c`, and their consumers), and define the **M3 retirement contract**: route player sweeps, BSP tests, object/actor collision, and projectile traces through CE physics; keep parent code and HP2 `collision.hp2` packs as **parity fixtures** until traces match; unlink parent collision from `tools/ee-world.mk` only after M3 exit gates and M6 duplicate-path retirement (`plans/5.hcu-remake.md:146–150`, `177`).

Report-only; does not close M0–M3 gates.

## Inputs examined

| Document / tree | Role |
|---|---|
| `docs/investigations/_prompt_contract.md` | Report contract, evidence baseline commits |
| `plans/5.hcu-remake.md` | M0 step 5, M3 steps 3–4, M4 collision coupling, M6 unlink |
| `docs/source-audit.md` | Single-owner collision statement (`:51`) |
| `docs/hcu-tag-loader-contract.md` | BSP/collision pointer residency vs HP2 sections |
| `docs/player-movement.md` | Parent M12 scope (structure-only pill, scratch/tables sizes) |
| `docs/hcu-ps2-closure.md` | Closure hot symbols (`collision_test_vector`, etc.) |
| `config/memory-budget.json` | `current_bsp`, `frame_scratch` |
| `tools/ee-world.mk` | `WORLD_PLAY=1` object list |
| `tools/convert_collision.py` | `collision.hp2` section layout |
| `tools/hcu_ps2_closure.py` | `selected_sources()`, `collision_debug` exclusion |
| `src/game/collide.{h,c}`, `pill.c`, `collpack.{h,c}` | Parent BSP/pill/pack |
| `src/game/move.c`, `shot.c`, `grenade.c`, `grenade_blast.c`, `combat_targets.c`, `play_ee.c` | Parent collision consumers |
| `submodules/halo-ce-universal/source/physics/*` (36 files) | Intended CE authority |
| `submodules/halo-ce-universal/source/physics/collisions.h` | Unified query API and flag sets |
| `submodules/halo-ce-universal/source/units/bipeds.c` | `collision_move_pill` / `collision_test_pill` call sites |
| `submodules/halo-ce-universal/port/ps2/game/ps2_coop.c` | Local player-collision policy hook |
| `submodules/halo-ps2/engine/src/sim/objects.h` | Render table (non-collision; identity bridge risk) |
| Host fixtures | `tests/test_collide.py`, `test_player.py`, `test_move.py`, `test_location.py`, `test_actor_collision.py`, `test_shot.py`, `test_grenade.py`, `test_combat_targets.py`, `test_play_weapons.py`, `test_vital.py`, `test_gameplay_render.py`, `test_pad.py`, `tests/*_main.c` |
| HCU harness reference | `submodules/halo-ce-universal/tools/harness/tests/test_object_bounds_cache.py` |
| Cross-audit | `docs/investigations/m0_runtime_ownership_auditor.md` (collision §4), `m3_player_movement_auditor.md`, `m3_object_lifecycle_auditor.md`, `m2_loader_failure_auditor.md` |

**Evidence baseline (contract):** parent `a2575e957feefbdff27febedabf60590401e6bcc`; HCU `c406a4149ddebae4f45462ce4c1e8d9cce0567c2`. `build/hcu-ps2-closure/all/halo-local.elf` was present at audit time; contract SHA-256 not re-verified here.

---

## Findings

### 1. Locked target ownership (authoritative after integration)

Aligned with `docs/source-audit.md:51` and `plans/5.hcu-remake.md:55`.

| Concern | Production owner | Primary evidence |
|---|---|---|
| Structure BSP segment/pill queries | HCU `source/physics/collision_bsp.c` | `collision_bsp_test_vector` (`collision_bsp.c:1220`), `collision_bsp_test_pill` (`collision_bsp.c:1160`) |
| Unified gameplay queries (structure + media + objects) | HCU `collisions.c` / `collisions.h` | `collision_test_vector` (`collisions.h:141`), `collision_test_pill` (`collisions.h:127`), `collision_move_pill` (`collisions.c:1553`, `collisions.h:155`) |
| Collision features / object models | HCU `collision_features.c`, `collision_models.c`, `collision_model_definitions.c` | Feature caps `MAXIMUM_COLLISION_FEATURES_PER_TEST`; models use `object_get_node_matrices` (per prior audits) |
| Active structure/collision BSP instance | HCU scenario/globals | `global_collision_bsp_get` / `scenario_switch_structure_bsp` family (`scenario.c` symbols) |
| Player biped sweeps | HCU `bipeds.c` + physics | `collision_move_pill` (`bipeds.c:2633`), `collision_test_pill` (`bipeds.c:1279`) |
| Projectiles / vehicles / AI physics traces | HCU `items/projectiles.c`, `vehicles.c`, `physics.c` | `collision_test_vector` with `_collision_test_for_projectiles_flags` (`collisions.h:73`) |
| Co-op player-vs-player collision policy | HCU port + CE flags | `network_coop_player_collisions` (`ps2_coop.c:29–33`); `_collision_test_skip_player_bipeds_bit` (`collisions.h:54–56`) |
| HP2 render BSP (`halo-ps2` `world/bsp.c`) | Presentation / cluster lookup only | `docs/player-movement.md:9` — not gameplay collision authority |

**M3 step 4 (frozen):** “Route player sweeps, BSP tests, object collision, actor collision, and projectile tests through CE physics/collision. Retire parent `collide.c`/`collpack.c` only after parity fixtures pass; no duplicate collision authority.” (`plans/5.hcu-remake.md:147`)

### 2. Current runtime: two ELFs, one product direction

```text
TODAY (WORLD_PLAY=1)                         TARGET (M3 steady state)
┌──────────────────────────────┐            ┌──────────────────────────────┐
│ world.elf (ee-world.mk)      │            │ Integrated EE game image   │
│  play_ee → collision.hp2     │            │  game_tick @ 30 Hz         │
│  collpack → collide_bsp      │   ───►     │  global_collision_bsp_*    │
│  pill / move / shot / grenade│            │  collision_test_* only     │
└──────────────────────────────┘            └──────────────┬───────────────┘
┌──────────────────────────────┐                            │ snapshot (read-only)
│ halo-local.elf (HCU closure) │                            ▼
│  full source/physics/        │            ┌──────────────────────────────┐
│  not on play critical path   │            │ halo-ps2 render sim/*      │
└──────────────────────────────┘            └──────────────────────────────┘
```

| Artifact | Collision stack | Production today? |
|---|---|---|
| `build/.../world.elf` with `WORLD_PLAY=1` | `collpack.c` → `collide_bsp`; `pill.c`/`collide.c`; combat in `shot.c`/`grenade*.c` | **Yes** (`tools/ee-world.mk:43–50`) |
| `build/hcu-ps2-closure/all/halo-local.elf` | All non-excluded `source/**/*.c` including 36 `source/physics/` files (`hcu_ps2_closure.py:144–156`) | **Yes** for closure measurement; **not** wired to `play_ee` |
| Host `cc` tests | Same parent modules as play ELF | **Fixture oracles** only |

`tools/hcu_ps2_link.py` contains **no** references to `collide`, `collpack`, or `pill` — parent collision is intentionally absent from the HCU link script.

**Risk if integrated carelessly:** A single tick that calls both `collide_test_vector` on flat `collide_bsp` views and `collision_test_vector` on CE tag-backed BSP would duplicate traversal, disagree on media/objects, and split material/hit identity. Makefile separation is a **temporary** guard, not the architecture.

### 3. Parent collision stack — responsibilities and retirement

#### 3.1 Module map

| Module | ~Lines | Owns today | CE analogue | Milestone |
|---|---:|---|---|---|
| `collide.c` | 307 | Structure segment test, material type, underwater via `LOC1`, point empty | `collision_bsp_test_vector`, location/media in CE | Retire from **production link** M3 after parity; keep host fixtures |
| `pill.c` | 877 | Structure-only `collision_move_pill` (256 features, 128 BSP depth per header `pill.c:4–5`) | `collision_move_pill` + feature gather in `collision_features.c` | M3 (with movement auditor) |
| `collpack.c` | 420 | HP2 section parser: `COLL`, `LOC1`, `TAGS`, `VITA`, `ACOL`; `collpack_actor_ray` | M2 CE tag/BSP load + `collision_models` / damage pipeline | **Data:** M2; **runtime authority:** M3 |
| `move.c` | — | `mover_tick_map` → `collide_move_pill` (`move.c:259`) | `biped_update_physics` | M3 (`m3_player_movement_auditor`) |
| `shot.c` | — | `collide_test_vector` + `collpack_actor_ray` + `combat_targets` (`shot.c:428–511`) | `projectile_update` + CE collision results | M4 (depends on M3 owner) |
| `grenade.c`, `grenade_blast.c` | — | BSP traces via `collide_test_vector` | CE grenade/projectile collision | M4 |
| `combat_targets.c` | — | Engine-slot registry + ACOL rays | CE actors/damage + datum handles | M4 |
| `play_ee.c` | — | Loads pack, `malloc` pill scratch (`play_ee.c:468–469`), orchestrates all above | CE shell + `port/ps2` session | M1 boot + M6 unlink play loop |

#### 3.2 Parent API surface (fixture producer)

- **Structure:** `collide_test_vector`, `collide_move_pill`, `collide_material_type`, `collide_location_underwater`, `collide_point_empty` (`collide.h:50–106`). Header documents provenance from CE `collision_bsp_test_vector` (`collide.h:2–4`).
- **Pack:** `collpack_collision`, `collpack_location`, `collpack_actor_collision`, `collpack_actor_ray` (`collpack.h:12–59`).
- **Flags:** Parent `COLLIDE_FRONT` etc. (`collide.h:11–15`) — **not** interchangeable with CE `_collision_test_*` bit enums (`collisions.h:26–79`).

#### 3.3 Documented intentional deltas (must not become “second truth”)

| Topic | Parent behavior | CE / M3 target | Evidence |
|---|---|---|---|
| Player pill scope | Structure BSP only | Biped pill includes object collision per CE flags | `pill.c:1–5`, `docs/player-movement.md:3` |
| Actor hits | Pre-triangulated `ACOL` ray vs posed nodes | Datum-backed `collision_model` + damage regions | `play_ee.c:484–487`, `convert_collision.py` ACOL export |
| Hit identity | `object_table_t` slot + `combat_targets` | `object_datum` / `collision_result.object_index` | `combat_targets.h:38–45`, `collisions.h:86–105` |
| Underwater / fog | `LOC1` leaf/cluster tables in pack | CE media + location validity flags | `collpack_location`, `collide_location_underwater` |
| Scratch allocation | Host tests: caller buffer 47,644 B (`docs/player-movement.md:25`); **play_ee uses `malloc`** (`play_ee.c:469`) | Plan: no heap on simulation path (`plans/5.hcu-remake.md:186`) | Violation is migration debt, not target |

#### 3.4 `collpack` / `collision.hp2` — stopgap data path

`tools/convert_collision.py` builds sections consumed at play boot (`play_ee.c:454–463`):

| Section | Role | Parent consumer | Long-term owner |
|---|---|---|---|
| `COLL` | Flat Xbox collision BSP tables (~666,372 B Blood Gulch, `docs/player-movement.md:25`) | `collpack_collision` → `collide_bsp` | CE structure/collision BSP in `current_bsp` (`config/memory-budget.json`) |
| `LOC1` | Leaf/cluster/fog for media tests | `collide_location_underwater` | CE scenario/media |
| `TAGS` | 24 floats cyborg movement constants | `move.c` / play | CE tags via M2 image |
| `VITA` | Damage resistance profile | `vital.c` | CE damage (M4) |
| `ACOL` | Cyborg mesh v2 for rays | `collpack_actor_ray`, combat | CE collision models or retained **export-only** tool output |

**Retirement rule:** `collpack` as **live gameplay loader** retires when M2 supplies CE-valid BSP memory and M3 routes queries through `global_collision_bsp_get()`. The converter remains valuable as a **byte oracle** for parity (`plans/5.hcu-remake.md:147`).

### 4. HCU collision stack — intended authority (detail)

#### 4.1 File inventory (`source/physics/`, 36 files)

Core query path: `collision_bsp.c`, `collision_bsp_definitions.c`, `collisions.c`, `collision_features.c`, `collision_models.c`, `collision_model_definitions.c`, `collision_usage.c`, `bsp2d.c`, `bsp3d.c`, `breakable_surfaces.c`, `terrain_definitions.c`, `physics.c`, `point_physics.c`, plus headers/definitions.

**PS2 closure:** `port/ps2/port.json` includes `source/physics` on the include path (cited in prior closure docs); `hcu_ps2_closure.py` compiles all manifest-selected sources. Prefix `collision_debug` is in the excluded-feature list (`hcu_ps2_closure.py:80`) — debug collision must not silently become gameplay stubs.

#### 4.2 Query taxonomy (production entry points)

| Query class | CE API | Typical callers | Parent fixture analogue |
|---|---|---|---|
| Structure segment | `collision_bsp_test_vector` | Internal; via `collision_test_vector` | `collide_test_vector` |
| Structure pill | `collision_bsp_test_pill` / `_new` | Internal | Partial overlap with parent `pill.c` |
| Unified segment | `collision_test_vector(flags, …)` | Projectiles, AI, vehicles | `collide_test_vector` (structure only) |
| Unified pill | `collision_test_pill` / `_new` | Bipeds, probes | Parent pill (structure only) |
| Move pill | `collision_move_pill` | `bipeds.c:2633` | `collide_move_pill` via `mover_tick_map` |
| Point / fix pill | `collision_test_point`, `collision_fix_pill` | Physics edge cases | `collide_point_empty` (partial) |
| Object features in volume | `object_get_features_in_sphere` (harness) | OpenCE harness | Not implemented on parent |

**Result record:** `struct collision_result` (`collisions.h:86–105`, size assert `0x50`) carries `type`, `material_type`, `object_index`, `region_index`, `node_index`, `surface_index`, etc. Parent `collide_hit` is a reduced view — parity tests must map fields explicitly.

#### 4.3 Flag sets (use CE names in production)

Preset composites in `collisions.h:73–79`:

- `_collision_test_for_projectiles_flags` = `0x1000E9`
- `_collision_test_for_bipeds_living_flags` = `0x20C3A0`
- `_collision_test_for_bipeds_dead_flags` = `0xC0A0`
- `_collision_test_for_vehicles_flags` = `0xC0A0`

Co-op skip: `_collision_test_skip_player_bipeds_bit` tied to `network_coop_player_collisions` comment (`collisions.h:54–56`). PS2 adapter returns `TRUE` for local retail semantics (`ps2_coop.c:29–33`).

#### 4.4 What HCU closure has vs what play lacks

| Capability | In `halo-local.elf` closure | On `world.elf` play path |
|---|---|---|
| Compile/link full physics tree | Yes | N/A (parent modules instead) |
| Load retail map BSP into CE globals | **No** (M2 loader open) | Loads `collision.hp2` `COLL` only |
| Run `game_tick` with collision | Standalone closure only | `play_ee` + engine `main.c` loop |
| Object-type collision in player pill | Code present | Parent explicitly omits |

### 5. Competing authorities — retirement ledger

Consolidated from `m0_runtime_ownership_auditor.md` §6, specialized for collision.

| Competing authority | Path / symbol class | Replace with | Remove from production link |
|---|---|---|---|
| Parent BSP collision core | `src/game/collide.c` | HCU `collision_bsp.c` + `collision_test_vector` | M3 (fixtures until parity) |
| Parent structure pill | `src/game/pill.c` | HCU `collision_move_pill` | M3 |
| HP2 pack as live BSP authority | `src/game/collpack.c` runtime load in `play_ee` | M2 CE BSP residency + scenario load | M2 data; M3 gameplay |
| Parent player locomotion vs BSP | `move.c`, `play_ee.c` `mover_tick_map` | CE biped/unit physics | M3 |
| Parent projectile BSP + ACOL | `shot.c`, `grenade.c`, `grenade_blast.c` | CE projectiles + `collision_test_vector` | M4 |
| Actor ray on engine pose + ACOL | `play_ee.c:168–227`, `collpack_actor_ray` | CE damage + collision models | M4 |
| Combat target vitals on table indices | `combat_targets.c` | CE damage/actor model | M4 |
| Dual link of parent physics | Any `collide.o` in HCU ELF | Forbidden | Immediate anti-pattern |
| Render BSP as collider | Implicit if gameplay used `bsp_find_cluster` alone | CE structure BSP | Policy: presentation only |

**M6 explicit unlink list** (collision-related subset of `ee-world.mk:44–49`): `game/collpack.o`, `game/collide.o`, `game/pill.o`, plus movement/combat consumers `move.o`, `shot.o`, `grenade.o`, `grenade_blast.o`, `combat_targets.o`, orchestrator `play_ee.o` (`plans/5.hcu-remake.md:177`).

**Explicitly retained:** Host tests compiling parent modules; `convert_collision.py`; emulator smokes that pin behavior until HCU traces exist.

### 6. Parity checklist (parent fixture → HCU acceptance)

Use this as the M3 collision gate workbook. “Oracle” column is the **minimum** evidence source today; final acceptance must include CE/tag expectations per plan (`plans/5.hcu-remake.md:147`, `154`).

| # | Behavior | Parent fixture | Key assertion | HCU API / notes | Oracle |
|---:|---|---|---|---|---|
| 1 | Downward segment from spawns hits surface | `test_collide.py` (71 spawns, `test_collide.py:38`) | `abs(ground - spawn) < 0.002` when hit | `collision_bsp_test_vector` or `collision_test_vector` with structure flags | Parent + tag |
| 2 | Pill settle on first spawn | `test_player.py` `settle` | Grounded, eye ≈ 0.62 | `collision_move_pill` / biped tick | Parent (`docs/player-movement.md:23`) |
| 3 | Jump peak / landing | `test_player.py` `jump` | Documented tolerances (`player-movement.md:31`) | CE biped physics | Parent |
| 4 | Crouch height transition | `test_player.py` | Eye → 0.35, height 0.50 | CE biped | Parent |
| 5 | Wall stop distance | `test_player.py` | ≤ radius 0.2 + tolerance | CE pill with **objects** enabled | Parent (structure-only) ≠ CE — **document delta** |
| 6 | Out-of-BSP recovery | `test_player.py` | Restores last safe feet | CE location validity | Parent |
| 7 | Scratch / tables budget | `test_player.py:56–59` | scratch < 393216; tables < BSP spare | Measure CE `collision_move_pill` stack + working set (**unknown size**) | Parent only until measured |
| 8 | No malloc in game tick | `test_player.py` (host modules) | Host `src/game` path | Integrated port must use `frame_scratch` | Plan policy |
| 9 | Underwater at point | `test_location.py` | Dry/wet boundaries | CE media flags | Parent LOC1 |
| 10 | ACOL mesh extraction | `test_actor_collision.py` | Triangle/node counts | Export regression only until datum spawn | Parent export |
| 11 | Projectile BSP hit + material | `test_shot.py` | Material index resolution | `collision_test_vector` + CE material | Parent `collide_material_type` |
| 12 | Actor ray damage part | `test_shot.py` / actor mains | node, damage_part, resistance | CE regions | Parent ACOL |
| 13 | Grenade BSP bounce/block | `test_grenade.py` | Segment tests | CE projectile | Parent |
| 14 | Combat target registry ray | `test_combat_targets.py` | AABB + ray | CE object collision | Parent bridge |
| 15 | Render-schedule invariance | `test_gameplay_render.py` | Positions unchanged across render passes | HCU tick + snapshot (`m3_snapshot_render_auditor`) | Parent movement path |
| 16 | Co-op skip player bipeds | *(no PS2-repo test yet)* | Skip when policy false | `_collision_test_skip_player_bipeds_bit` | CE semantics |

**Gap:** No repository test yet executes row 1 or 2 on HCU against Blood Gulch bytes (`m0_runtime_ownership_auditor.md` open parity). OpenCE `test_object_bounds_cache.py` covers feature gathering only.

### 7. Call graph — parent play loop (collision touchpoints)

```text
play_init (play_ee.c:443)
  load collision.hp2
  collpack_collision → s_bsp
  collpack_location → s_location
  malloc(collide_pill_scratch_bytes)  ← migration defect
  collpack_actor_collision → s_actor_collision

per-frame (flycam wrap → play mode)
  mover_tick_map → collide_move_pill (structure)
  gun/shot_tick → collide_test_vector + collpack_actor_ray + combat_targets
  grenade_tick → collide_test_vector
  collide_location_underwater (weapon fire gate)
  __wrap_objects_tick → mutates engine biped pose for actor-ray diagnostics (play_ee.c:157–227)
```

HCU target graph (single authority):

```text
game_tick
  scenario / global_collision_bsp_*  [after M2 load]
  units → biped_update_physics → collision_move_pill / collision_test_pill
  projectiles → collision_test_vector (_collision_test_for_projectiles_flags)
  damage ← collision_result fields (M4)
  ps2_snapshot_publish (no collide_* calls in render consumers)
```

### 8. `sim/objects` and collision (identity, not geometry)

`sim/objects.c` performs no collision queries (grep: no `collide`/`collision`). Collision **risk** is indirect: `combat_targets` and `play_ee` tie hits to **engine object indices** and posed nodes (`play_ee.c:199–204`), bypassing CE datums. M3 requires snapshots for draw only (`plans/5.hcu-remake.md:146`); M4 must not use render slots as hit authority.

### 9. Fixture catalog (host)

All compile parent `collide.c` / `collpack.c` (and allies) with host `cc`; they do not run `halo-local.elf`.

| Test | Pins |
|---|---|
| `test_collide.py` | 71 spawn downward segments |
| `test_move.py` | Velocity + pill callback contract |
| `test_player.py` | Full Blood Gulch pill, scratch/tables budget |
| `test_gameplay_render.py` | Render-schedule invariance for movement |
| `test_location.py` | Underwater/fog |
| `test_actor_collision.py` | ACOL v2 |
| `test_shot.py`, `*_shot_main.c` | Projectile + actor materials |
| `test_grenade.py` | Grenade BSP |
| `test_combat_targets.py` | Registry + rays |
| `test_play_weapons.py` | Integrated weapon link |
| `test_vital.py` | `VITA` section |
| `test_pad.py` | Pulls collision into link smoke |
| `tools/run_world_viewer.py`, `qualify_actor_*_smoke.py` | EE/emulator smokes |

`plans/remake-cowork.md:124` (cited in prior audits): parent gun/shot/grenade/actor tests are host evidence, not HCU parity proof.

### 10. Gaps blocking M3 “one owner” acceptance

| Gap | Evidence |
|---|---|
| Play ELF still authoritative for movement/combat collision | `ee-world.mk:43–50`, `play_ee.c:554+` |
| No CE BSP bytes on play path | `play_ee` loads HP2 pack only |
| No HCU-vs-parent normalized trace | Explicit unknown |
| CE pill scratch / working set size on EE | Unknown — do not invent (`_prompt_contract.md:10`) |
| M2 tag image + `global_collision_bsp` residency | `hcu-tag-loader-contract.md`, `m2_loader_failure_auditor` |
| Parent structure-only pill vs CE object-inclusive biped pill | `docs/player-movement.md:3` vs `collision_test_pill` flags |
| `play_ee` heap for pill scratch | `play_ee.c:469`, `plans/5.hcu-remake.md:192` |
| Soft-double helpers in hot `collision_test_vector` | `docs/hcu-ps2-closure.md:68` (M23 perf, not M3 owner) |

### 11. M3 collision owner verdict

| Question | Settlement |
|---|---|
| Who owns gameplay collision at steady state? | **HCU** `source/physics/` (+ units/projectiles callers). |
| Who owns collision **data** for maps? | **CE-loaded** BSP/collision tags in `current_bsp` (M2); until then parent `COLL` is a **fixture adapter**. |
| May parent `collide`/`collpack`/`pill` stay in production? | **No** after M3 parity + M6 unlink; **yes** as host/oracle fixtures until then. |
| May `collpack` remain a second runtime loader? | **No** as authority; **yes** for tests and converter regression. |
| Is integration done? | **No** — separate ELFs; no `collision_test_*` on play tick; no cross-stack parity tests. |
| Does this close M3? | **No** — report names owners, ledger, and checklist only. |

---

## Interface contracts for the main agent

1. **Single query family in production:** All gameplay collision resolves through HCU `collision_test_vector`, `collision_test_pill`, `collision_move_pill`, and `collision_bsp_*` internals — never through `collide_*` / `collpack_*` in the integrated EE image.

2. **Flags and results:** Use `_collision_test_*` presets from `collisions.h`; map outcomes to `struct collision_result`. Do not translate parent `COLLIDE_*` masks at the boundary except in **test harness** comparison shims.

3. **BSP residency:** One logical structure/collision BSP owner in `current_bsp`; load path must satisfy `hcu-tag-loader-contract.md` pointer rules. Parent `collide_bsp` flat views are **comparison layouts** only.

4. **Collpack retirement:** Stop calling `collpack_collision` from production boot once CE `scenario_switch_structure_bsp` (or PS2 equivalent) publishes the same logical tables. Keep `convert_collision.py` output for parity rows 1–11 in §6.

5. **Movement coupling:** Player motion must call CE `collision_move_pill` with biped flag sets (`m3_player_movement_auditor`); retire `mover_tick_map` → `collide_move_pill` from `ee-world.mk`.

6. **Combat coupling (M4):** Projectiles and grenades consume CE collision results for materials and hit objects; retire `collpack_actor_ray` as gameplay authority when datum-backed models are live (`m3_object_lifecycle_auditor`).

7. **Co-op policy:** Implement player-collision enablement only via `network_coop_player_collisions` + `_collision_test_skip_player_bipeds_bit`; no PS2-only parallel.

8. **Render boundary:** `sim/*` and `render/*` must not call `collide_*` or `collpack_*`; collision side effects occur only inside `game_tick`.

9. **Allocation:** Pill/collision scratch comes from caller-owned `frame_scratch` (or measured CE pools) — eliminate `play_ee.c:469` pattern in integrated build.

10. **Anti-pattern:** Linking `game/collide.o` into `halo-local.elf` or calling parent helpers from `port/ps2` (`plans/5.hcu-remake.md:177`).

---

## Recommended tests / fixtures

1. **BSP segment parity (new HCU host harness):** For 71 spawns in `test_collide.py`, compare `collide_test_vector` vs `collision_bsp_test_vector` on shared bytes (post-M2 shim or vetted COLL→CE mapper).

2. **Pill parity:** Replay `test_player.py` inputs on CE biped path; document tolerances for structure-only parent vs object-inclusive CE where they must differ (checklist row 5).

3. **Scratch measurement:** Once integrated, assert CE collision scratch + BSP working set ≤ `frame_scratch` (393,216 B) and `current_bsp` high-water — parent 47,644 B is a lower bound reference only (`docs/player-movement.md:25`).

4. **Projectile normalized trace:** Extend `test_shot.py` events to a shared JSON/binary trace replayed on `projectile_update`.

5. **Co-op flag fixture:** `network_coop_player_collisions(FALSE)` causes living biped pill tests to skip other player bipeds.

6. **Render-schedule invariance:** Port `test_gameplay_render.py` to HCU tick + snapshot publish (depends on `m3_snapshot_render_auditor`).

7. **Retain all §9 host tests** until HCU counterparts pass; then freeze as regression inputs (`plans/5.hcu-remake.md:154`).

---

## Dependencies on other investigators

| Investigator | Dependency |
|---|---|
| `m2_loader_failure_auditor` / `m2_map_conversion_auditor` | CE BSP pointer validation; COLL vs tag BSP ownership |
| `m2_arena_capacity_auditor` | `current_bsp` peak with collision + render BSP overlap |
| `m3_player_movement_auditor` | Tick order, `biped_update_physics` vs `move.c` |
| `m3_object_lifecycle_auditor` | Datum spawn for object-type collision; retire ACOL bridge |
| `m3_snapshot_render_auditor` | No collision in snapshot consumers; sim hash excludes parent collide |
| `m0_link_closure_auditor` | Duplicate physics symbols if parent objects linked into HCU ELF |
| `m0_runtime_ownership_auditor` | Identity/collision/render split consistency |
| M4 combat work | Materials, vitals, grenades after M3 query owner is live |

---

## Open questions

1. **COLL → CE BSP mapping:** In-place materialization vs native tag BSP load — not decided (`m2_tag_image_format_investigator` notes `TAGS` collpack ≠ CE tag image).

2. **ACOL longevity:** Offline export only vs runtime `collision_model` on EE for cyborg hits (`play_ee.c` still requires ACOL at boot).

3. **Per-test oracle:** When parent and CE disagree, which wins for M3 exit — plan says compare both; per-row authority not fully enumerated.

4. **Object collision in player pill:** Confirm M3 exit requires CE-complete biped pill (not structure-only parent subset).

5. **Integrated ELF strategy:** Single image vs dual entry — affects enforcement of “no competing path” at link time.

6. **Feature list halving:** Parent documents halving when 256 features fill (`pill.c:828`); confirm CE `collision_move_pill` uses equivalent policy for parity.

7. **PVS / cluster:** Whether underwater tests need CE media only or also parent `LOC1` tables during transition.

---

## Handoff summary

**Settled:** Production collision = HCU `source/physics/` with unified `collision_test_*` / `collision_move_pill`; map BSP bytes owned by CE load into `current_bsp` (M2); parent `collide.c`, `pill.c`, and runtime `collpack` are **competing authorities** to retire from `ee-world.mk` after §6 parity and M6 unlink.

**Today:** `world.elf` (`WORLD_PLAY=1`) runs the full parent stack against `collision.hp2`; `halo-local.elf` compiles CE physics but is not on the play critical path; no cross-stack traces exist.

**Main agent actions:** (1) Land M2 BSP residency so `global_collision_bsp_get` matches fixture bytes; (2) wire `game_tick` player/projectile collision only through CE APIs; (3) add HCU host parity harness for rows 1–2 in §6; (4) remove `malloc` pill scratch from integrated boot; (5) keep parent modules as oracles until traces pass, then drop `collpack.o`/`collide.o`/`pill.o` per `plans/5.hcu-remake.md:147`, `177`.

**Do not:** Link parent collision into HCU ELF, extend parent collision semantics, or treat `collpack`/`ACOL` as permanent production hit authority alongside CE physics.

## Corroboration

### Agreements

- **m0_runtime_ownership:** Single collision authority = HCU physics; parent stack is fixture — no peer dissent.
- **m3_player_movement:** Parent `pill.c` oracle vs CE `collision_move_pill` target; scratch/`frame_scratch` sizing follows CE path after link.
- **m2_loader_failure / m2_tag_format:** BSP bytes into CE `current_bsp` before collpack retirement; fail-closed load ordering.
- **m1_dma_layout_auditor:** CE collision records are sim-memory, not DMA snapshot payloads.
- **m3_object_lifecycle:** Combat rays must use CE handles after snapshot — no parent table indices as hit identity.

### Conflicts

- **C2:** Corroborated **open** operationally (`world.elf` still runs parent path); policy is settled (HCU-only).

### Updated handoff

1. Run §6 parity checklist rows 1–2 on HCU host harness before unlinking `collide.o` from any integrated image.
2. M2 BSP residency is prerequisite for rows involving structure BSP parity.
3. Keep `tools/ee-world.mk` collision objects as oracles until traces match — then M6 drop per ledger.
