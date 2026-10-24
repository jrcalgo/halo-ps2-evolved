# m0_runtime_ownership_auditor

## Mission

Settle production ownership for **object identity/lifecycle**, **collision**, and **render snapshots** in the HCU migration, per `plans/5.hcu-remake.md` M0 step 5: one identity owner (HCU datum/object state), one collision owner (HCU `source/physics/`), and a parent `sim/*` layer that is a **read-only snapshot consumer**—not a second simulation database. Name every **competing authority** that must be retired (or downgraded to parity fixtures) and the milestone that retires it.

Report-only; does not close M0–M3 gates.

## Inputs examined

| Document / tree | Role |
|---|---|
| `docs/investigations/_prompt_contract.md` | Report contract, evidence baseline commits |
| `docs/source-audit.md` | M0 source/owner matrix, single-owner collision/identity statements |
| `plans/5.hcu-remake.md` | Component-source table (lines 23–45), M0 step 5, M3 snapshot/collision steps, M6 duplicate-path retirement |
| `submodules/halo-ce-universal/source/memory/data.c`, `data.h` | Datum handle validation and allocation |
| `submodules/halo-ce-universal/source/objects/objects.c`, `objects.h` | `object_datum`, `object_get`, `objects_update`, node matrices |
| `submodules/halo-ce-universal/source/game/game.c` | `game_initialize` / `game_tick` ordering |
| `submodules/halo-ce-universal/source/physics/` (e.g. `collision_bsp.c`, headers) | CE BSP pill/sphere/vector tests |
| `submodules/halo-ce-universal/port/ps2/src/ps2_abi.c` | Layout locks for datum/object/weapon/projectile |
| `submodules/halo-64/port/n64/NOTES.md` | Render seam: simulation does not read pixels; tick-side matrix/HUD obligations |
| `docs/hcu-ps2-platform-placeholder-audit.md` | 187 render placeholders; state-advancing callbacks |
| `tools/ee-world.mk` | What the **current** play ELF links |
| `src/game/play_ee.c` and sibling `src/game/*` | Parent runtime simulation orchestration today |
| `submodules/halo-ps2/engine/src/sim/objects.h`, `objects.c`, `fpview.h`, `main.c` | Render-oriented object table and tick |
| `src/game/combat_targets.h` | Bridge from engine object slots to combat collision |

**Evidence baseline (contract):** parent `a2575e957feefbdff27febedabf60590401e6bcc`; HCU `c406a4149ddebae4f45462ce4c1e8d9cce0567c2`. `halo-local.elf` was **not** present in the workspace at audit time (contract SHA-256 not re-verified).

---

## Findings

### 1. Locked target ownership (authoritative after integration)

These rows are already decided in `docs/source-audit.md` and `plans/5.hcu-remake.md`; this audit treats them as the **settled contract**, with integration still open.

| Concern | Production owner | Primary evidence |
|---|---|---|
| Object identity, lifecycle, handles, per-tick simulation state | HCU `source/objects/`, `source/units/`, `source/memory/data.c` | `datum_get` / generation checks (`submodules/halo-ce-universal/source/memory/data.c:145–167`); `object_get` → `object_datum` (`objects.h:196`); `objects_update()` in `game_tick` (`game.c:391`) |
| Player/unit movement and physics integration | HCU `source/units/`, `source/physics/` | Units drive bipeds/vehicles; collision models read `object_get_node_matrices` (`collision_models.c:58` cited in prior audits) |
| Structure BSP and object collision queries | HCU `source/physics/` | `collision_bsp_test_pill` family (`collision_bsp.c`); no N64 collision replacement (`source-audit.md:30–31`) |
| Gameplay decisions (weapons, damage, AI, scripts) | HCU respective trees | `game_tick` section order (`game.c:358–394`) |
| Post-tick **render/HUD/effect presentation inputs** | **Hybrid:** HCU publishes; parent `halo-ps2` consumes | Plan rows: `sim/objects`, `sim/skeleton`, `sim/fpview` → modified halo-ps2 **consumers**; post-tick snapshot → HCU publish + halo-ps2 read (`plans/5.hcu-remake.md:41–42`, `docs/source-audit.md:45–46`) |
| GS/VU1/DMA, packs, arenas | Parent / `halo-ps2` | `source-audit.md:13–14`, `ee-world.mk` engine objects |

**M0 step 5 wording (frozen):** “Freeze one collision owner (HCU) and one identity owner (HCU datum/object state). The parent object table must not remain a competing simulation database.” (`plans/5.hcu-remake.md:107–108`)

### 2. Current runtime reality (pre-integration)

Two bodies of code **both** implement overlapping concerns today; only one may remain in the production link after M6.

```text
                    TODAY (WORLD_PLAY=1)                    TARGET (M3+ / M6)
┌─────────────────────────────┐              ┌─────────────────────────────┐
│ HCU closure ELF (standalone)│              │ HCU game_tick @ 30 Hz       │
│ 345 units, not in play link │              │  datum/object state         │
└─────────────────────────────┘              │  physics/collision        │
                                             └──────────────┬──────────────┘
┌─────────────────────────────┐                             │ post-tick snapshot
│ play_ee + src/game/*        │                             ▼
│  mover/pill/collide/collpack│              ┌─────────────────────────────┐
│  gun/shot/grenade/vital     │              │ halo-ps2 render + sim/*     │
│  wraps engine objects_tick  │              │  read-only poses/HUD quads  │
└─────────────────────────────┘              └─────────────────────────────┘
```

**Play link set** (`tools/ee-world.mk:43–52`): `play_ee.c`, `collpack.c`, `collide.c`, `gun.c`, `shot.c`, `vital.c`, `grenade*.c`, `move.c`, `pill.c`, `play_fp.c`, plus linker wraps on `flycam_update`, `fpview_*`, `objects_pose_model`, `objects_tick`.

**Engine main loop** (`submodules/halo-ps2/engine/src/main.c:246–254`): pad → `flycam_update` (or play override) → **30 Hz** `objects_tick` + `fpview_tick` → `fpview_place` → render. That tick advances **placement animation** only (`objects.c:55–67`), not CE object semantics.

**HCU** is not yet the tick driving the visible play ELF; it is a measured compile closure (`plans/5.hcu-remake.md:11–12`, `docs/source-audit.md:55`).

### 3. Object identity — settled owner vs competing authorities

#### 3.1 Authoritative model (HCU)

- **Handles:** `struct datum_header` + `identifier` in the high 16 bits of indices; stale handles fail in `datum_get` (`data.c:153–167`, `data.h:36–38`).
- **Records:** `struct object_datum` (ABI-locked 0x1A4 bytes on PS2: `port/ps2/src/ps2_abi.c:41`).
- **Tick owner:** `objects_update()` runs late in `game_tick`, after effects, game engine, editor, HaloScript (when allowed), and recorded animations (`game.c:371–391`).
- **Node poses for collision/render:** `object_compute_node_matrices` / `object_get_node_matrices` (`objects.c:1298`, `2457`; used from units and collision models).

#### 3.2 Competing authorities (retire or fixture-only)

| Authority | Location | What it owns today | Why it conflicts | Retirement / disposition |
|---|---|---|---|---|
| **Engine object table** | `submodules/halo-ps2/engine/src/sim/objects.h:1–35`, `objects.c` | Up to 1024 `object_t` placements; spawn from scenario; **local** anim tick | Header still describes future sim writers (`objects.h:2–3`); indices are **table slots**, not datum handles; no generation, no damage/lifecycle | **M3:** stop treating as simulation DB; **consume** CE snapshot fields (transform, anim phase, visibility flags). Retire `objects_tick` as authority (`M3` plan step 3, `5.hcu-remake.md:146`) |
| **Play loop object mutation** | `src/game/play_ee.c:157–163`, `199–204` | Captures `object_table_t*` after `objects_tick`; **rewrites** appended biped pose for actor-ray diagnostics | Mutates presentation table during “simulation” callback; not driven by CE datums | **M3/M4:** remove or confine to non-production fixtures; never dual-write with CE |
| **Combat target registry** | `src/game/combat_targets.h:38–39`, `combat_targets.c` | Maps `object_index` (engine slot) → ACOL mesh + `vital` | Parallel health/identity keyed to render table, not `object_datum` / unit indices | **M4:** actor damage routes through CE; registry becomes snapshot-driven or deleted |
| **Parent combat/movement state** | `play_ee.c:35–58`, `move.c`, `gun.c`, `shot.c`, … | `mover`, `gun`, `shot`, `grenade`, probe `vital` | Full parallel player/world state machine | **M6** production unlink (`5.hcu-remake.md:177`); until then **parity oracle** (`source-audit.md:16`) |
| **OpenCE / N64 pool macros** | `objects.h:33–50` (`HALO_PORT_*`) | Capacity semantics in headers | Foreign to PS2 budget v2 (`5.hcu-remake.md:87–88`) | **M2:** PS2 limits in `port/ps2` replace for runtime sizing; not a second identity system |

**Not competing on PS2 (reference only):** `halo-64/port/n64/src/n64_render.c` — N64 machine renderer; method is seam notes, not a second CE object store (`source-audit.md:67`, `5.hcu-remake.md:75`).

#### 3.3 Identity seam rule

- **Production:** Any stable reference to a world entity must be a **HCU datum index** (with generation) or a CE-defined field derivable from it (e.g. unit object index).
- **Render snapshot:** May carry a **display handle** (slot in fixed snapshot arrays) but must be **derived from** CE state each tick; renderer must not allocate new gameplay identity.
- **Forbidden:** Growing new gameplay semantics in `src/game/*` or inferring gameplay from `object_t.def` alone without CE backing (`5.hcu-remake.md:177`).

### 4. Collision — settled owner vs competing authorities

#### 4.1 Authoritative model (HCU)

- **Owner:** `submodules/halo-ce-universal/source/physics/` (`source-audit.md:51`, plan table line 26).
- **BSP queries:** `collision_bsp.c` pill/sphere/vector tests (symbols at file head, e.g. `collision_bsp_test_pill` at `collision_bsp.c:64`).
- **Object features:** `collision_features.h`, `collisions.c`, `collision_models.c` (object collision instances use node matrices from CE objects).
- **Activation gate (plan):** CE collision is production-authoritative only when converted map/BSP data is loadable and R5900 closure is accepted (`source-audit.md:19`).

#### 4.2 Competing authorities (retire or fixture-only)

| Authority | Location | Role today | Conflict | Retirement |
|---|---|---|---|---|
| **`collide.c` + `pill.c`** | `src/game/collide.c`, `pill.c` | BSP pill move ported from CE algorithms; comment traces to `collision_bsp_test_sphere` / `collision_move_pill` (`pill.c:1–5`) | Second BSP collision implementation on parent `collide_bsp` views | **M3** after parity fixtures (`5.hcu-remake.md:147`); keep as **comparison** until then (`source-audit.md:51`) |
| **`collpack.c`** | `src/game/collpack.h:1–2` | Offline `COLL`/`ACOL`/`VIT1` packs; pointers alias pack bytes | Collision **data** path parallel to CE tag BSP + collision model tags; not the same loader as M2 tag image | **M2/M3:** CE BSP/collision from runtime tag image replaces pack-as-authority; collpack remains **test/fixture** producer (`convert_collision.py` pipeline) |
| **`play_ee` mover** | `play_ee.c:554` `mover_tick_map` | Player locomotion against `collide_bsp` | Competing player physics vs CE biped/unit physics | **M3** |
| **Actor ray on engine pose** | `play_ee.c:168–227`, `collpack_actor_ray` | Hit detection on posed engine biped + separate `vital` | Actor collision without CE damage pipeline | **M4** |
| **Parent shot/grenade collision** | `shot.c`, `grenade*.c` | Projectile traces vs parent BSP/actors | Duplicate combat collision | **M4** |

**Single-owner rule (restated):** At steady state, **one** code path answers “can the player move here?” and “what did the projectile hit?” — HCU physics/collision. Parent BSP **render** geometry from HP2 is not a gameplay collision authority unless explicitly passed into CE as the loaded structure BSP (M2 loader contract).

### 5. Render snapshots — settled split vs competing behavior

#### 5.1 Contract (hybrid)

| Side | Owner | Responsibility |
|---|---|---|
| **Publisher (simulation tick boundary)** | Modified HCU / port layer | After `game_tick` completes, copy **immutable** transforms, node palettes, cameras, per-player FP state, HUD/effect **requests** into caller-provided buffers (`5.hcu-remake.md:148`, `docs/source-audit.md:15`) |
| **Consumer** | Modified `halo-ps2` `sim/objects`, `sim/skeleton`, `sim/fpview` + `render/*` | Read snapshot only; GS/VU1/DMA never write back into gameplay (`source-audit.md:15`, `5.hcu-remake.md:188`) |
| **Presentation exceptions** | Parent `hold_pose` / `play_fp` wraps | Sword/gravity-rifle **view** orientation only (`5.hcu-remake.md:29–30`, `source-audit.md:21`) — not gameplay duplication |

**N64 method (non-transferable implementation, transferable seam):** Simulation does not read render results; several “draw” calls still advance timers, `render.frame_index`, cameras, and FP matrices (`submodules/halo-64/port/n64/NOTES.md:33–44`). PS2 must implement **state advancement** either in real HCU render stubs or in the snapshot publisher—empty placeholders are not equivalent (`docs/hcu-ps2-platform-placeholder-audit.md:17`).

#### 5.2 What exists today (competing / immature)

| Piece | Behavior | Issue |
|---|---|---|
| **`objects_tick` / `fpview_tick`** | Engine animates scenario objects and FP arms (`main.c:248–252`, `fpview.h:1–2`) | **Simulation-like** animation on the render table while play mode also runs parent movement/combat |
| **`objects_pose` / `objects_pose_model`** | Skinning math for draw (`objects.h:53–63`) | Correct as **consumer** math if inputs are snapshot fields; wrong if driven only by engine table state |
| **Linker wraps** | `play_fp.c` `__wrap_objects_pose_model`; `play_ee.c` `__wrap_objects_tick` (`ee-world.mk:51–52`) | Parent injects pose policy and diagnostic capture **around** engine sim hooks |
| **HCU `render.frame_index++`** | Real CE side effect (`render.c:245`) | PS2 closure has **187** generated render symbols; particle/HUD lifetime may not advance until implemented (`hcu-ps2-platform-placeholder-audit.md:7`, `17`) |
| **No `ps2_snapshot_*` API** | Grep finds no snapshot builder in tree | M3 deliverable not started (`5.hcu-remake.md:148`) |

#### 5.3 Render snapshot data flow (target)

```text
game_tick()  [HCU, EE]
    │
    ├─ objects_update, units, weapons, collision, …
    │
    ▼
ps2_snapshot_publish()  [port/ps2 or parent adapter — TO BE ADDED M3]
    │  (writes into frame_scratch / fixed arrays; no heap)
    ▼
objects_draw_read(), fpview_read(), HUD quad list, effect sprites  [halo-ps2]
    │
    ▼
GS/VU1/DMA  [halo-ps2 only]
```

**Invariants (from plan §4):** snapshot is read-only and bounded; renderer may skip frames without mutating simulation (`5.hcu-remake.md:187–188`); render schedule invariance is an M3/M4 test gate.

### 6. Competing authorities — consolidated retirement ledger

Aligned with `plans/5.hcu-remake.md` M0 step 5 and M6 step 4.

| Competing authority | Path / symbol class | Replace with | Milestone to remove from production link |
|---|---|---|---|
| Parent player movement + BSP pill | `src/game/move.c`, `pill.c`, `play_ee.c` mover | CE units/bipeds + `collision_bsp_*` | M3 |
| Parent BSP collision core | `src/game/collide.c` | HCU `source/physics/collision_bsp.c` + features | M3 (fixtures until parity) |
| Offline collision pack as live BSP | `src/game/collpack.c` (runtime authority) | M2 CE tag/BSP load + HCU collision | M2 data path; M3 gameplay |
| Parent weapons/projectiles/damage | `gun.c`, `shot.c`, `grenade*.c`, `vital.c`, `arsenal.c` | HCU `source/items/`, `damage.c` | M4 |
| Engine object table as sim DB | `sim/objects.c` `objects_tick`, spawn semantics as state | Snapshot-fed draw records | M3 |
| Engine FP weapon sim tick | `sim/fpview.c` `fpview_tick` | CE `first_person_weapons_update` + snapshot | M3/M5 |
| Combat target vitals on table indices | `combat_targets.c` | CE damage/actor model | M4 |
| Play orchestration | `src/game/play_ee.c` (whole diagnostic loop) | CE shell + `port/ps2` session (`ps2_local.c` / game entry) | M1 boot + M6 unlink |
| Fuel rod pose/gameplay fallback | `play_fp.c` fuel-rod paths (per plan) | Generic HCU weapon + arms-only FP | M4 |
| HCU render placeholders as “no-op forever” | Generated render/rasterizer stubs | State-advancing adapters per N64 NOTES | M1/M5 service review |

**Explicitly retained (not retired):** `halo-ps2` renderer, stream/world, arenas, pad/timer; `hold_pose` presentation for sword/gravity rifle; host tests that **read** parent traces as fixtures after M6 conversion (`5.hcu-remake.md:177`).

### 7. Halo-64 method mapping (ownership only)

| N64 artifact | PS2 ownership lesson | Transfer? |
|---|---|---|
| `n64_game.c` memory map / cache | PS2 `port/ps2` + parent arenas own bases (`5.hcu-remake.md:40–44`) | Method yes, implementation no |
| `NOTES.md` render seam | One-way snapshot; tick-side HUD/FP/frame_index | Yes |
| `n64_render.c` | N64 draw | **No** — halo-ps2 GS/VU1 owns draw |
| Node matrices “on tick” (`NOTES.md:60–62`) | Matches CE `object_compute_node_matrices` → publish in snapshot | Yes (via HCU, not engine table) |

### 8. M0 step 5 verdict

| Question | Settlement |
|---|---|
| Who owns object identity? | **HCU** — `data.c` datums + `object_datum` in `objects.c` / `objects.h`. |
| Who owns collision? | **HCU** — `source/physics/`. |
| Who owns render snapshot contents? | **HCU decides** (post-tick publish); **halo-ps2 consumes** for draw. |
| What must not remain a competing DB? | Parent **`sim/object_table_t` lifecycle semantics**, **`src/game` movement/collision/combat**, and **collpack-as-live-BSP** for gameplay. |
| Is integration done? | **No.** Play ELF still links parent gameplay (`ee-world.mk:43–52`); snapshot API absent; HCU closure not wired to guest loop. |
| Does this close M0? | **No** — only names owners and retirement targets; memory ledger and grouped-owner acceptance remain open (`plans/5.hcu-remake.md:11`, `docs/source-audit.md:55`). |

---

## Interface contracts for the main agent

1. **Datum authority:** All gameplay code in the production EE image resolves entities via `datum_get` / `object_get` (or CE unit APIs). No production path may treat `object_table_t` slot indices as gameplay IDs.

2. **Snapshot publish (to implement):** Single call after each `game_tick` (or CE frame equivalent), writing into **pre-sized** parent buffers (plan: `frame_scratch` or named region — exact layout owned by `m3_snapshot_render_auditor`). Must include at minimum: per-visible-object root transform, animation phase, node palette or precomputed skin matrices, per-local-player camera + FP weapon nodes, HUD/effect draw requests. **No allocation** on publish path (`5.hcu-remake.md:148`).

3. **Snapshot consume:** `sim/objects`, `sim/skeleton`, `sim/fpview`, `render/obj_render.c` read only the published struct for the current tick generation; skipping render must not advance simulation.

4. **Collision feed:** CE `global_structure_bsp` (and collision models) loaded from M2 tag image; parent `collide_bsp` views may remain for **tests** comparing pill results until M3 parity passes.

5. **Render callback policy:** Classify each HCU render/rasterizer call site per N64 NOTES: either implement state advance in PS2 port code or prove via call-graph audit it is a pure no-op (`5.hcu-remake.md:118`, placeholder audit).

6. **Handle mapping:** Snapshot records should carry `datum` index (or opaque 32-bit CE handle) plus generation; consumers must not cache pointers across ticks.

---

## Recommended tests / fixtures

| Test | Purpose |
|---|---|
| Existing parent movement/collision/projectile host tests (`tests/test_gun.py`, `test_shot.py`, `test_actor_collision.py`, etc.) | Retain as **oracle** until HCU traces match; then freeze as regression inputs (`5.hcu-remake.md:147–158`) |
| Datum stale-handle rejection | Already on host/R5900 (`docs/source-audit.md:134`); extend to integrated tick |
| **Render-schedule invariance** | Zero vs one vs N render passes between ticks; hash CE simulation state (`5.hcu-remake.md:176`) |
| Pill/BSP parity | Parent `pill.c` vs HCU `collision_bsp_test_pill` on shared BSP bytes (synthetic COLL or converted BSP section) |
| Snapshot generation counter | Monotonic tick id; consumer detects stale reads |

---

## Dependencies on other investigators

| Investigator | Dependency |
|---|---|
| `m0_memory_ledger_auditor` | Where snapshot buffers and CE pools land in budget v2 regions |
| `m0_link_closure_auditor` | When HCU objects/physics symbols are in the same ELF as play vs standalone |
| `m1_platform_callsite_auditor` | Which render/HUD calls must advance state before M3 |
| `m2_loader_failure_auditor` / tag image work | Collision BSP **data** owner at load time |
| `m3_object_lifecycle_auditor` | CE `objects_initialize` / map transition vs engine `objects_spawn_bsp` |
| `m3_collision_owner_auditor` | Detailed pill/feature parity checklist |
| `m3_snapshot_render_auditor` | Field-level snapshot schema and `sim/*` read paths |
| `m3_first_person_pose_auditor` | FP pose: CE vs `hold_pose` adapter boundary |

---

## Open questions

1. **Exact snapshot schema:** No checked-in struct yet; must not duplicate full `object_datum` in `frame_scratch` without a measured size gate.

2. **Double-speed / half-rate object update:** `objects_update` skips some ticks when `game_players_are_double_speed()` (`objects.c:4449`); snapshot must reflect CE policy, not engine’s every-other-frame `objects_tick` (`main.c:249`).

3. **PVS / cluster bits:** CE `object_globals->active_cluster_bits` vs renderer visibility — confirm snapshot carries enough for draw culling without recomputing gameplay PVS in halo-ps2.

4. **When collpack stops being loaded in `play_ee`:** Depends on M2 BSP residency and CE `scenario_switch_structure_bsp` path on PS2.

5. **Integrated ELF naming:** `halo-local.elf` absent here; re-verify SHA and link set when artifact is regenerated.

6. **Co-op / network object hooks:** `port/ps2/game/ps2_local.c` stubs network object indices; local CE path still owns real object creation — confirm no second list in parent when co-op activates (`ps2_coop.c` audit).

---

## Handoff summary

**Settled:** Production **identity** = HCU datums/`object_datum`; **collision** = HCU `source/physics/`; **render** = post-tick **HCU publish → halo-ps2 consume**, with sword/gravity-rifle pose adapter as presentation-only exception.

**Retire from production (keep as fixtures until parity):** entire competing stack `src/game/{move,pill,collide,collpack,gun,shot,grenade*,vital,play_ee}` plus **simulation authority** of `sim/objects_tick` and `fpview_tick` and `combat_targets` vitals keyed on engine slots.

**Current blocker:** Play target still links and runs the parent stack (`tools/ee-world.mk`); HCU tick and snapshot publish are not on the guest critical path. M0 step 5 is satisfied at the **documentation/decision** level; **runtime** single-owner enforcement waits for M1 boot bridge + M3 snapshot + M6 unlink.

**Main agent next actions:** (1) Lock snapshot struct ownership with `m3_snapshot_render_auditor`; (2) wire `game_tick` → publish → existing render entry; (3) mark `object_table_t` header comment and spawn/tick APIs as deprecated simulation paths; (4) track collpack/BSP transition under M2 loader work.

## Corroboration

### Agreements

- **m3_collision_owner_auditor (retry):** Production collision = HCU `source/physics/`; parent `collide.c` / `collpack` / `pill.c` = fixtures until parity — matches §4 retirement table here.
- **m3_object_lifecycle:** CE owns handles/lifecycle; parent `object_table_t` is animation/diagnostic mirror pending one-way snapshot.
- **m3_player_movement:** Parent `move`/`pill` is oracle today; CE `game_tick` is target — no dual authority at steady state.
- **m3_first_person_pose:** CE sim + snapshot → halo-ps2 draw; parent `play_fp` wraps are comparison-only until M6.
- **m0_link_closure:** HCU physics symbols present in `halo-local.elf` closure; `world.elf` path is parallel build, not production direction.

### Conflicts

- **C2:** Policy **HCU-only** is unanimous; **tension** is operational (`WORLD_PLAY=1` still runs parent stack) — resolution = M3 wiring + M6 unlink, not a second physics owner.
- **C4:** Render stubs vs NOTES seam — **m1_platform** + **m3_snapshot** agree presentation must not own sim state; bounded adapter required.

### Updated handoff

1. Sequence: M1 boot bridge → M2 BSP residency → M3 `game_tick` + snapshot publish → retire `ee-world.mk` sim objects (**m3_collision** ledger rows 1–2 first).
2. Do not link parent collision into HCU ELF (**m3_collision** handoff “do not”).
3. Snapshot schema owner = **m3_snapshot_render** + **m1_dma** (pointer-free rows in `frame_scratch`).
