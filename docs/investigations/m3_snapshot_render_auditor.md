# m3_snapshot_render_auditor

## Mission

Audit M3 requirements for **immutable post-tick snapshot contents**, **simulation invariance across render schedules** (zero / one / multiple presentation passes per tick), and the **Halo-64 render NOTES seam** (`render.frame_index`, per-window camera, `interface_draw_screen`, and related presentation-side state). Report-only: no implementation changes, no gate closure.

Evidence baseline per `_prompt_contract.md`: parent HEAD `a2575e957feefbdff27febedabf60590401e6bcc`, HCU HEAD `c406a4149ddebae4f45462ce4c1e8d9cce0567c2`.

## Inputs examined

| Area | Paths |
|------|--------|
| M3 / interface contracts | `plans/5.hcu-remake.md` (M3 step 5, M6 §3, §4 snapshot bullets), `docs/source-audit.md`, `docs/hcu-ps2-platform-placeholder-audit.md`, `docs/hcu-ps2-closure.md` |
| Halo-64 render seam (reference) | `submodules/halo-64/port/n64/NOTES.md`, `submodules/halo-64/port/n64/game/n64_render_game.c` |
| CE tick vs render ordering | `submodules/halo-ce-universal/source/game/game.c`, `submodules/halo-ce-universal/source/game/game_time.c`, `submodules/halo-ce-universal/source/main/main.c` |
| CE render / HUD / particles | `submodules/halo-ce-universal/source/render/render.c`, `render_particles.c`, `submodules/halo-ce-universal/source/interface/interface.c`, `hud.c`, `submodules/halo-ce-universal/source/effects/particles.c` |
| HCU PS2 closure (no real renderer) | `submodules/halo-ce-universal/port/ps2/port.json`, `port/ps2/src/ps2_edge.c`, `port/ps2/src/ps2_abi.c`, `port/ps2/src/ps2_main.c` |
| Parent snapshot prototypes & render-schedule fixtures | `src/hybrid/protocol.h`, `src/hybrid/replay.c`, `src/game/move.c`, `tests/player_main.c`, `tests/weapon_replay_main.c`, `tests/test_shot.py`, `docs/player-movement.md` |
| Target consumer (halo-ps2) | `submodules/halo-ps2/engine/src/sim/objects.h`, `submodules/halo-ps2/docs/03-engine-architecture.md` |
| Budget slot for snapshots | `config/memory-budget.json` (`frame_scratch`, 393216 bytes) |

## Findings

### 1. M3 snapshot builder: specified, not present

`plans/5.hcu-remake.md` M3 step 5 requires a **PS2 snapshot builder after each completed CE tick** that publishes, into caller-provided storage (prefer `frame_scratch` or another named region):

- Immutable object transforms and node palettes  
- Cameras / first-person pose  
- HUD **work** (draw requests / display state derived from CE decisions)  
- Render-only effect requests  

Constraints from the same plan: **1–4 local players** reuse fixed storage; the parent renderer may **skip or delay** rendering without mutating the snapshot or simulation and **without allocating** (`plans/5.hcu-remake.md:148`). Section 4 adds: snapshot production is **read-only and bounded**; render must not call back into gameplay mutation (`plans/5.hcu-remake.md:188`).

**Repository state:** No `snapshot` type, builder, or HCU→parent adapter exists outside documentation and architectural sketches. The only concrete snapshot structs in-tree are:

- **M08 hybrid proof** — `struct hybrid_snapshot` in `src/hybrid/protocol.h:14-17` (synthetic handles/positions; not CE-shaped).  
- **halo-ps2 design doc** — double-buffered POD render snapshot described in `submodules/halo-ps2/docs/03-engine-architecture.md:82-84` (design intent, not wired to HCU).

`docs/hcu-ps2-closure.md` and `docs/source-audit.md` both state that the 201,364-byte generated `render` global (`struct render_globals`, asserted in `port/ps2/src/ps2_abi.c:53`) needs a **real snapshot/simulation seam**, not a placeholder BSS definition.

**M3 gate status:** `plans/5.hcu-remake.md:14` marks M3 incomplete; render-schedule invariance on the **CE path** is explicitly **not implemented/verified**.

### 2. Intended immutable snapshot contents (contract decomposition)

From plan + halo-ps2 consumer expectations, the main agent should treat the post-tick snapshot as **POD, self-contained, pointer-free into tick scratch**, with generation-safe handles where the parent indexes CE datums (`plans/5.hcu-remake.md:146`, `submodules/halo-ps2/engine/src/sim/objects.h:1-3`, `plans/0.native-ps2-halo-hybrid-port.md:640`).

| Category | CE source of truth (today) | Snapshot should carry (per plan) | Notes |
|----------|---------------------------|--------------------------------|-------|
| Object pose | `object_compute_node_matrices` / datum transforms (`NOTES.md:60-62`) | Root transforms, skinning/node palette indices or matrices, flags | Parent `object_t` today simulates animation (`sim/objects.h:50-51`); must become read-only. |
| Camera / windows | `main_game_render` builds `render_window` + cameras (`main.c:3256+`) | Per-local-player camera, viewport, frustum inputs | Interpolation between ticks is a separate `render_interpolation_*` path (`game_time.c:496-503`). |
| First-person weapon | `first_person_weapons_update` in `game_tick`; `first_person_weapon_render_update` in render (`render.c:340`) | Matrices/effect attachment points for GS/VU1 | N64 calls both update and draw (`n64_render_game.c:677-678`). |
| HUD | `hud_draw_screen` chain from `interface_draw_screen` (`interface.c:720`) | Quads/glyphs/**or** pre-resolved HUD element list | CE decides shields/ammo/motion sensor in HUD code; PS2 draws (`plans/5.hcu-remake.md:165`). |
| Effects (render leg) | Particles/contrails/widgets in `game_frame` + draw in `render_window` | Sprite/effect requests, not live particle pool pointers | Effect **simulation** stays in CE (`effects_update` in `game_tick`). |
| Visibility / PVS | `structure_visibility_compute` during render (`render.c:332`) | Optional: visible cluster/surface bitsets for culling | `render_globals` bitsets are simulation-adjacent (`render.h:94-108`, `plans/remake-cowork.md:110`). |

**Immutability test pattern already in-repo:** `src/hybrid/replay.c:66-71` captures a snapshot, mutates a field, recaptures, and asserts `memcmp` equality — this is the intended **consumer cannot corrupt publisher storage** check, applied to the hybrid toy model.

**Budget:** `config/memory-budget.json:19` reserves **393,216 bytes** for `frame_scratch`; `tests/test_player.py:12-13` uses the same constant as a movement scratch ceiling. Snapshot high-water for 4-player split screen is **unmeasured** (unknown).

### 3. Simulation invariance across render schedules

#### 3.1 Target behavior (M3 / M6)

- M3 exit: movement/collision traces match with **zero, one, or multiple render passes between ticks** (`plans/5.hcu-remake.md:150`).  
- M6: hash **CE gameplay state** across render schedules; **exclude** render/audio-only work (`plans/5.hcu-remake.md:176`).  
- M1 platform audit: verify traces across **zero/one/multiple** render passes (`docs/hcu-ps2-platform-placeholder-audit.md:17`).

#### 3.2 Parent duplicate path (reference fixtures only)

The **parent** `src/game` stack intentionally decouples simulation from a `render_schedule` integer:

- `src/game/move.h:79-88` documents that `render_schedule` is **ignored**.  
- `tests/player_main.c:259-266` runs three parallel movers with schedules `0`, `1`, `2` for 20 ticks and prints `schedule 1` when positions match.  
- `docs/player-movement.md:21-23` states three render schedules produce the same positions.  
- `tests/weapon_replay_main.c:83-86` inserts `presentations` loops **after** each tick’s state hash; `tests/test_shot.py:60-76` asserts identical `state=` hashes for presentations `0`, `1`, `4` and **distinct** `presentation=` hashes.  
- M08 hybrid: `src/hybrid/ee_main.c` and `tests/gameplay_host32/hybrid.c` run three presentation cadences with the same `event_hash`.

These prove **the parent oracle and hybrid toy** respect presentation isolation. They do **not** prove CE `game_tick` + `main_loop` render scheduling invariance on R5900 or PCSX2.

#### 3.3 CE retail coupling (why render schedule matters on the HCU path)

Retail CE **does not** treat rendering as a pure side effect. Important couplings:

**A. `render.frame_index` (global, presentation cadence)**

- Incremented at start of `render_frame` and `render_frame_pregame` (`render.c:245`, `607`).  
- Halo-64 documents: particles die when `frame_index - last_rendered_frame_index > 15`; particle renderer must refresh `last_rendered_frame_index` (`submodules/halo-64/port/n64/NOTES.md:36-38`).  
- CE `particles_update` (called from `game_frame`, not `game_tick`) culls datums when unrendered for `MAXIMUM_PARTICLE_UNRENDERED_FRAME_COUNT` (15) frames (`particles.c:102`, `1035-1041`).  
- `render_particles` sets `last_rendered_frame_index` when a particle is actually processed for draw (`render_particles.c:385-386`).  
- `particles_update` also records `render.frame_index` into `particles_tick_frame_indices` per sub-tick step (`particles.c:1021-1023`).

**B. `game_frame` runs on wall-clock frames, not only on sim ticks**

`game_time_update` calls `game_frame` once per loop iteration with frame delta (`game_time.c:496-503`), including `particles_update`, `contrails_update`, `widgets_update`, `game_sound_update`, `rasterizer_frame_update`. Comment at `game_time.c:496-500` ties this to **interpolation between ticks**. Skipping or multiplying `render_frame` without an equivalent **presentation seam** changes how often `particles_update` runs relative to `render.frame_index` advances.

**C. `interface_draw_screen` / HUD (per window, in render)**

- Invoked from `render_window` after 3D scene work (`render.c:425`).  
- Calls `hud_draw_screen` (`interface.c:720`).  
- `hud_draw_screen` advances **motion sensor** (`motion_sensor_tick` at `hud.c:1430`) and **HUD messaging** (`hud_messaging_update` at `hud.c:1457`), plays unit sounds, draws weapon/unit UI.  
- Halo-64 NOTES list motion sensor, HUD sounds, pickup prompts, message timers, target-name hold as advancing inside `interface_draw_screen` (`NOTES.md:43-44`).  
- N64 port calls `interface_draw_screen` once per player view inside its `render_frame` replacement (`n64_render_game.c:702`).

**D. `first_person_weapon_render_update` (render path)**

Called inside `render_window` before object draw (`render.c:340`). N64 invokes it per view (`n64_render_game.c:677`). This is distinct from `first_person_weapons_update` in `game_tick` (`game.c:378-382`).

**E. Main loop gating**

`main_loop` may skip `main_game_render` when `!render_frame || debug_no_drawing` (`main.c:3631-3637`, `3649-3651`). `render_frame` is also tied to menu/time-scale and `game_time_get()>=3` when an engine runs (`main.c:3609-3615`, NOTES `main.c:3297`).

**Conclusion:** For **full CE parity**, “render schedule invariance” cannot mean “never call render”; it requires either (1) **retail-identical** coupling of presentation hooks to frame cadence, or (2) a **documented port seam** that moves presentation-frequency state updates into the tick or into explicit snapshot fields so skipping GS work does not change gameplay. The Halo-64 NOTES + `n64_render_game.c` are the project’s chosen reference for (1) on constrained hardware.

#### 3.4 HCU PS2 closure today (breaks retail seam)

- `port/ps2/port.json` **excludes** entire `source/render/` and `source/rasterizer/` trees (`port.json:28-29`); only `render_cameras.c`, `rasterizer_geometry.c`, `rasterizer_swizzle.c` are pulled in (`port.json:65-68`).  
- **187** generated `render` placeholders (`docs/hcu-ps2-platform-placeholder-audit.md:7`, `17`).  
- `ps2_edge.c` implements `render_location_visible` as **always FALSE** (`ps2_edge.c:19-23`), overriding CE logic in `render.c:292-297`. That changes which particles are considered visible in `render_particles.c:164` (if `render_particles` were linked).  
- `rasterizer_initialize` returns success without a device (`ps2_edge.c:56-61`).  
- No `render_frame` / `interface_draw_screen` implementation is linked from CE sources on PS2; generated stubs stand in.

Therefore **render-schedule invariance for CE gameplay is undefined** on the current PS2 link: presentation hooks are mostly no-ops, and one seam (`render_location_visible`) is actively non-retail.

### 4. Halo-64 render NOTES seam (frame_index, interface_draw_screen)

#### 4.1 NOTES requirements (excerpt)

`submodules/halo-64/port/n64/NOTES.md:33-57` states simulation does not read render **pixels**, but still requires:

| Requirement | CE / N64 evidence |
|-------------|-------------------|
| `render.frame_index` per frame | CE: `render.c:607`; N64: `n64_render_game.c:535`, pregame `720` |
| Particle lifetime vs `last_rendered_frame_index` | CE: `particles.c:1035-1037`, `render_particles.c:385-386`; NOTES:36-38 |
| `render.camera` / frustum per window | CE: `render_window` sets `render.camera`, `render.local_player_index` (`render.c:322-324`); N64 sets per view (`n64_render_game.c:669-672`) |
| `first_person_weapon_render_update` per window | CE: `render.c:340`; N64: `n64_render_game.c:677` |
| `interface_draw_screen` per window | CE: `render.c:425`; N64: `n64_render_game.c:702` (after HUD inset) |
| Rasterizer globals / vblank throttle | NOTES:45-49; N64 has separate `n64_render_*` implementation (non-transferable per `docs/source-audit.md:37`) |

N64 **does not** use Xbox `structure_render.c`; it replaces `render_frame` entirely in `n64_render_game.c` while preserving the **state-advancing** calls the NOTES list.

#### 4.2 PS2 should copy the method, not the N64 renderer

`docs/source-audit.md:46` points PS2 post-tick snapshot work at the **NOTES seam**, not `n64_render.c`. PS2 parent keeps GS/VU1/DMA (`source-audit.md:13`). Expected PS2 factoring:

1. **After `game_tick`:** build immutable snapshot from CE state (M3 step 5).  
2. **On each presentation opportunity (0..N per tick):** parent renderer reads snapshot only; any retail-required `frame_index` / HUD / FP-weapon **presentation updates** must either run in a **bounded CE adapter** invoked at a defined rate or be **reflected in snapshot fields** so skipped draws do not desync simulation.  
3. **Do not** let VU1/GS callbacks write CE globals (`source-audit.md:15`).

#### 4.3 `render_globals` and visibility

`struct render_globals` (`render.h:77-109`) holds `frame_index`, cameras, cluster/surface bitsets. `structure_visibility_compute` runs inside CE `render_window` (`render.c:332`). `plans/remake-cowork.md:110` notes live consumers of `render.camera`, `render.frame_index`, and structure visibility bitsets. M3 snapshot design must decide whether visibility for a frame is **snapshot-published** (from last tick or last presentation pass) or recomputed on EE during parent prep — **unknown** without call-graph audit on AI/perception consumers.

### 5. Tick / render ordering (integration risk)

Canonical retail order in `main_loop` (simplified):

1. Input / `game_time_update` → may run **multiple `game_tick()`** per loop (`game_time.c:481-487`).  
2. `game_frame` (effects, particles, sound, widgets) with interpolation (`game_time.c:501-503`).  
3. Optional `main_game_render` → `render_frame` → per-window `interface_draw_screen` (`main.c:3635`, `render.c:594+`).  
4. Present / throttle (`main.c:3647-3651`).

M3 says parent diagnostic `play_ee` / `src/game` stay **out** of the CE tick path (`plans/5.hcu-remake.md:144`). Snapshot builder attach point should be **after** `game_tick` completes for a logical sim step, not after parent `mover_tick_map`.

**Unknown:** Exact hook when PS2 runs 30 Hz EE tick vs 30 fps presentation (halo-ps2 `03-engine-architecture.md:60-68` assumes tick and frame coincide at 30 fps with snapshot between them). Whether `game_frame` runs once per EE frame or per vblank on PS2 is **not implemented** in `port/ps2/src/ps2_main.c` (shell entry only).

### 6. Consumer side (halo-ps2)

`submodules/halo-ps2/engine/src/sim/objects.h` documents the object table as something **rendering reads** and later simulation would write — opposite of the target (`objects.h:2-3`). Node matrices are computed via `objects_pose` from parent world data, not CE datums.

No CE handle/generation field appears in `object_t`. M3 requires generation-safe handles in parent render records (`plans/5.hcu-remake.md:146`).

### 7. Tests and evidence map

| Test / fixture | What it validates | CE / M3 relevance |
|----------------|-------------------|-------------------|
| `tests/player_main.c` + `test_player.py` | Movement + scratch budget; 3× `render_schedule` | Parent movement only |
| `tests/weapon_replay_main.c` + `test_shot.py::test_weapon_replay_independent_of_presentation_work` | Combat state vs presentation passes | Parent gun/shot/grenade only |
| `src/hybrid/replay.c` + `tools/test_hybrid_emulator.py` | Snapshot immutability + 3 cadences | Protocol prototype |
| `tests/combat_main.c` `melee_and_replay` | Synthetic combat world replay with render_work between ticks | Not CE |
| M06 platform emulator | Presentation **RGB** snapshots match (`plans/0.native-ps2-halo-hybrid-port.md:19`) | Parent platform ELF, not CE gameplay |
| HCU PS2 closure tests | ABI, placeholders, input semantics | No render-schedule CE replay |

**No test** currently hashes CE datum state across 0/1/N render passes on R5900.

## Interface contracts for the main agent

1. **Snapshot ABI (publisher: HCU PS2 port; consumer: parent/halo-ps2)**  
   - **When:** once per completed `game_tick` (or per server tick in time-advance loops), before any optional presentation pass.  
   - **Where:** caller-provided buffer in `frame_scratch` (393216 B budget) or alternate named region with measured high-water.  
   - **Shape:** POD, no pointers into CE heaps; include tick id, player/window count, object records (datum index + generation + transform/node palette), per-player camera, FP weapon pose, HUD draw list / effect requests. Version field + size cap required (not yet defined).  
   - **Immutability:** second capture without intervening tick must be bitwise identical; consumer reads are read-only (`hybrid/replay.c:66-71` pattern).

2. **Presentation seam (retail parity)**  
   - Treat Halo-64 `NOTES.md:33-57` as the checklist of CE functions that **must run** at presentation frequency **or** have tick-side equivalents proven equivalent by fixtures. Minimum named symbols: `render.frame_index` advance, `first_person_weapon_render_update`, `interface_draw_screen` (hence `motion_sensor_tick`, `hud_messaging_update` inside `hud_draw_screen`).  
   - PS2 parent owns drawing; CE or a thin `port/ps2` game-side shim owns **whether** presentation hooks run and **what** they mutate. Generated 187 render no-ops are **not** sufficient (`hcu-ps2-platform-placeholder-audit.md:17`).

3. **Render schedule semantics**  
   - **Simulation hash** must exclude fields only mutated during presentation (`plans/5.hcu-remake.md:176`).  
   - **Include** in hash: datums, transforms, weapons, projectiles, health, RNG, tick counter.  
   - **Define** whether `game_frame` subsystems (`particles_update`, etc.) belong to sim or presentation for hashing — retail ties them to frame delta (`game_time.c:501-503`); port must document choice.

4. **Decouple parent oracle**  
   - Keep `render_schedule` unused in `mover_tick_map` for parent fixtures (`move.h:80`).  
   - CE path must not use the parent integer; use explicit **presentation pass count** injected at test harness boundary.

5. **Forbidden**  
   - GS/VU1/DMA paths writing CE globals.  
   - Snapshot containing raw CE pointers.  
   - Growing `src/game` production semantics (`plans/5.hcu-remake.md:177`).

## Recommended tests / fixtures

1. **CE host or R5900 replay (priority)**  
   - Fixed script: N ticks, pad input sequence; run with `presentations_per_tick ∈ {0,1,4}`.  
   - Hash per tick: object datum generations, unit/player transforms, weapon/ammo, projectiles, shields/body, `random_get_status`, `game_time_get()`.  
   - Assert hashes identical across presentation counts; separate optional hash of presentation-only counters (`render.frame_index`, HUD message timers if exposed).

2. **Particle seam fixture**  
   - Spawn particles; run with presentations 0 vs 1 for 20+ frames; assert datum count / ages match **or** document intentional retail coupling and move refresh into tick/snapshot adapter.

3. **HUD seam fixture**  
   - Trigger pickup prompt / message; advance with and without `interface_draw_screen`; compare `hud_messaging` state.

4. **Snapshot immutability**  
   - Extend hybrid pattern: CE builder fills buffer; consumer corrupt attempt; rebuild and compare.

5. **Snapshot size / `frame_scratch`**  
   - Worst-case Blood Gulch scenario: max visible objects + 4 split views; measure bytes; fail if > 393216 without budget revision.

6. **Migration of existing tests**  
   - Port `weapon_replay_main.c` pattern to CE-backed executable when M3 movement/combat links; keep parent tests as regression until parity.

## Dependencies on other investigators

| Investigator | Dependency |
|--------------|------------|
| `m3_player_movement_auditor` | Movement parity defines tick input boundary for snapshot capture. |
| `m3_object_lifecycle_auditor` | Datum handles/generations in snapshot records. |
| `m3_collision_owner_auditor` | Collision state in sim hash; no duplicate parent collision in snapshot. |
| `m3_first_person_pose_auditor` | FP matrices in snapshot vs `first_person_weapon_render_update`. |
| `m1_platform_callsite_auditor` / M0 runtime ownership | Which generated render stubs are reachable from `game_tick` / `main_loop`; call-graph proof for empty callbacks. |
| M2 tag/image | Map load required before integrated CE tick snapshots in real maps. |

## Open questions

1. **Exact snapshot schema:** field list, versioning, and 4-player split-screen high-water in `frame_scratch` — **unknown** (no prototype struct).  
2. **`game_frame` on PS2:** same cadence as retail `game_time_update` or tied 1:1 to 30 Hz EE frame — **unknown** (`ps2_main.c` only enters shell).  
3. **Visibility / `structure_visibility_compute`:** snapshot copy vs recompute on parent; impact on AI if bitsets stale — **unknown** (needs xref audit).  
4. **`render_location_visible` PS2 stub (always false):** intentional for closure or bug relative to particle culling — **unresolved** (`ps2_edge.c:19-23`).  
5. **Interpolation:** halo-ps2 60 fps stretch reads interpolated snapshots (`03-engine-architecture.md:71-79`); M3 gate text focuses on 30 Hz — clarify whether M3 acceptance includes interpolation factor or only tick-aligned snapshots.  
6. **Sound:** `sound_render` in `main_game_render` (`main.c:3269`) — classify as presentation-only for hashing vs sim-affecting — **needs call-site audit**.  
7. **Pool sizes / effect caps in snapshot** — do not invent; use CE tag-derived limits when M5 effects integrate.

## Handoff summary

M3’s **post-tick immutable snapshot** is specified in `plans/5.hcu-remake.md` but **not implemented**; only hybrid and halo-ps2 **design** artifacts exist. **Render-schedule invariance** is demonstrated for **parent** `move`/`weapon_replay` and hybrid fixtures, **not** for linked HCU gameplay: retail CE couples `render.frame_index`, `game_frame`/`particles_update`, and `interface_draw_screen`/`hud_draw_screen` to presentation frequency, documented in **Halo-64 `NOTES.md`** and implemented in **`n64_render_game.c`**, while HCU PS2 currently **excludes** real `render.c` and fills **187 render placeholders**. PS2 integration should follow the NOTES **seam** (state-advancing presentation hooks + snapshot read path), not the N64 GPU code. **M3 gate remains open:** build snapshot builder after `game_tick`, wire halo-ps2 consumers to read-only POD, replace render stubs with a bounded presentation adapter, and add CE state hashing across 0/1/N presentation passes before claiming render-schedule invariance on the production path.

## Corroboration

### Agreements

- **m1_platform_callsite:** **187** render stubs + zeroed **`render`** global — root cause of presentation/sim decoupling on PS2 link.
- **m1_dma_layout_auditor:** Snapshot rows in `frame_scratch`, 16-byte aligned, pointer-free — design target for builder.
- **m3_object_lifecycle / m3_first_person_pose:** Consumers (`obj_render`, `fpview`) read snapshot only; CE owns tick outputs.
- **m0_runtime_ownership:** HCU publish → halo-ps2 consume is the locked seam.
- **m3_player_movement:** Sim hash tests must ignore presentation-only stubs until adapter advances required globals.

### Conflicts

- **C4:** Corroborated **open** — need bounded adapter (frame_index / HUD hooks) without duplicating sim in render stubs.

### Updated handoff

1. Implement snapshot builder immediately after `game_tick` in integration branch.
2. Replace highest **R4** render globals used by CE timer paths before claiming menu/map stability (**m1_platform** §5).
3. Add 0/1/N presentation pass CE state hash test before M3 gate close.
