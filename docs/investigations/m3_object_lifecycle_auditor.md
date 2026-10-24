# m3_object_lifecycle_auditor

## Mission

Trace **create → identity → update → delete → snapshot ownership** for gameplay objects, contrasting HCU CE datum/object state with the parent `halo-ps2` `object_table_t` prototype and the parent `src/game` bridge code. Establish what is authoritative today, what M3 requires, and which seams the main agent must implement without inventing pool sizes or closing M0–M3 gates.

## Inputs examined

| Area | Paths / symbols |
|------|-----------------|
| Contract and plan | `docs/investigations/_prompt_contract.md`, `plans/5.hcu-remake.md` (M3 §142–150), `docs/source-audit.md` |
| HCU datum core | `submodules/halo-ce-universal/source/memory/data.c`, `data.h`, `cseries/cseries.h` (`DATUM_INDEX_*`) |
| HCU object lifecycle | `submodules/halo-ce-universal/source/objects/objects.c`, `objects.h`, `object_types.c`, `damage.c` |
| HCU tick / map init | `submodules/halo-ce-universal/source/game/game.c` (`game_initialize`, `game_tick`, `game_initialize_for_new_map`, `objects_place`) |
| HCU typed datums | `submodules/halo-ce-universal/source/items/weapons.h` (`weapon_datum`), unit/vehicle getters in `units/` |
| HCU render coupling | `submodules/halo-ce-universal/source/render/render_objects.c` (`cached_object_render_states`, `render_objects`) |
| PS2 port local hooks | `submodules/halo-ce-universal/port/ps2/game/ps2_local.c`, `port/ps2/include/halo_ps2_limits.h`, `port/ps2/src/ps2_abi.c` |
| Parent sim table | `submodules/halo-ps2/engine/src/sim/objects.h`, `sim/objects.c`, `engine/src/main.c` |
| Parent render consumer | `submodules/halo-ps2/engine/src/render/obj_render.h` |
| Parent duplicate gameplay | `src/game/play_ee.c`, `src/game/combat_targets.c`, `src/game/combat_targets.h`, `src/game/vital.h` |
| Parent link set | `tools/ee-world.mk` (`WORLD_PLAY=1`) |
| Hybrid proof (datum + snapshot shape only) | `src/hybrid/core.c`, `src/hybrid/replay.c` |
| ABI | `submodules/halo-ce-universal/port/ps2/src/ps2_abi.c` (`object_datum` 0x1A4) |

Evidence baseline: parent HEAD `a2575e957feefbdff27febedabf60590401e6bcc`, HCU HEAD `c406a4149ddebae4f45462ce4c1e8d9cce0567c2` (`_prompt_contract.md`).

## Findings

### 1. Two object databases exist today (competing models)

**HCU (intended production authority)** stores gameplay objects as:

1. **`object_header_data`** — a `data_array` of `object_header_datum` rows (`objects.c:1035–1065`, `objects.h:218–226`). Each row holds `identifier`, header `flags`, `type`, `cluster_index`, `data_size`, and a pointer `datum` into the object memory pool.
2. **`object_memory_pool`** — variable-size `object_datum` (and larger typed records) allocated via `object_header_new` / `object_header_block_allocate` (`objects.c:681–761`). Pool size is `OBJECT_MEMORY_POOL_SIZE` (PS2: `0x100000` via `halo_ps2_limits.h:35`).

**Parent `halo-ps2` (render prototype, not CE)** uses a fixed dense table:

- `object_table_t` with up to `OBJ_MAX` (1024) `object_t` records, `count` append index, no delete/generation API (`sim/objects.h:13–35`, `sim/objects.c:5–173`).
- Populated once from scenario HP2 data via `objects_spawn_bsp` / `objects_spawn_def`; `objects_tick` only advances idle animation (`sim/objects.c:55–67`).
- Wired in `engine/src/main.c:39,168,250` as static `s_objects`.

**Parent `src/game` (temporary parity oracle)** treats the engine table as a live simulation adjunct:

- `play_ee.c` wraps `objects_tick`, caches `object_table_t *`, and **mutates** `object_t` placement for a diagnostic actor (`play_ee.c:84–89,157–163,199+`).
- `combat_targets` registers bipeds keyed by **dense table index** `uint16_t object_index`, explicitly documenting no deletion/generation (`combat_targets.h:38–39,77–79`; `combat_targets.c:207–271`).

M3 plan text requires CE datums as sole identity and converting `sim/objects` to consume-only readers (`plans/5.hcu-remake.md:146`, `sim/objects.h:1–3`).

### 2. HCU identity: generation-safe handles

Handles are `(identifier << 16) | absolute_index`:

- Macros: `DATUM_INDEX_NEW`, `DATUM_INDEX_TO_ABSOLUTE_INDEX`, `DATUM_INDEX_TO_IDENTIFIER` (`cseries.h:170–172`).
- On allocate, `datum_initialize` assigns `header->identifier = data->next_identifier` and increments `next_identifier`, wrapping to `0x8000` if zero (`data.c:599–611`).
- `datum_get` / `datum_try_and_get` reject stale handles when the stored `identifier` does not match the index argument (`data.c:113–200`).
- `datum_delete` clears `identifier` and may shrink `data->count` (`data.c:351–374`).

Object indices used across the game are these full handles (e.g. `objects_update` builds `DATUM_INDEX_NEW(i, object_header->identifier)` at `objects.c:4513,4541`).

**PS2 ABI:** base `struct object_datum` is compile-asserted at **420 bytes (0x1A4)** (`ps2_abi.c:41`). Typed datums extend this in-place (example: `weapon_datum` embeds `struct _object_datum object` after `definition_index` — `weapons.h:213–218`).

### 3. HCU create path

| Stage | Mechanism | Evidence |
|-------|-----------|----------|
| Global init | `objects_initialize()` allocates header array + pool in `game_state` (`objects.c:1035–1065`) | `game_initialize` calls `objects_initialize()` (`game.c:296`) |
| Per-map reset | `objects_initialize_for_new_map()` → `data_make_valid(object_header_data)`, clears globals, cluster partitions (`objects.c:1067–1092`) | Called from `game_initialize_for_new_map` before placement (`game.c:667`) |
| Scenario placement | `objects_place()` sets `initial_placement`, runs `object_types_place_all` (`objects.c:831–838`) | After map init, `game_initialize_for_new_map` calls `objects_place()` (`game.c:705`) |
| Per-object create | `object_placement_data_new` → `object_new` → `object_header_new` + type setup + node block alloc (`objects.c:1204–1244,3435–3588`) | Scripts/game use `object_new` / `object_new_from_scenario` (`objects.h:419,462,466`) |
| Scenario row | `object_new_from_scenario` copies scenario transform, calls `object_new`, `object_type_place`, optional name list (`objects.c:3918–3961`) | Bulk placement loops in `object_types.c:1214–1237` |
| Network index override | `network_objects_new_object_index()` may force `datum_new_at_index` (`objects.c:686`) | PS2 local returns `NONE` → first-free slot (`ps2_local.c:129–132`) |

Create failure paths: invalid definition/type mismatch aborts before header alloc (`objects.c:3457–3468`); pool exhaustion frees the new header datum (`objects.c:697–700`).

### 4. HCU update path (simulation ownership)

Per tick, after units/AI/players/effects/game_engine/scripts:

- `objects_update()` (`game.c:391`) performs PVS-driven activate/deactivate, per-object `object_update`, completes `_object_header_being_created_bit` / `_object_header_being_deleted_bit` phases, then `objects_garbage_collection()` (`objects.c:4438–4552`).
- Node matrices: `object_compute_node_matrices_recursive` / `object_postprocess_node_matrices` (called from `object_update` path — see `objects.c:3897–3915,3880–3892`).
- Double-speed games skip some object updates except player units (`objects.c:4449–4521`).

**Render-side cache (still HCU memory, not parent table):** `cached_object_render_states` is its own `game_state_data_new` datum array keyed by render-state index, holding `object_index` and lighting LOD state (`render_objects.c:174–184,271–296,1069+`). This is simulation-adjacent presentation cache, not a second gameplay object table, but it **does** reference `long object_index` handles.

**PS2-only:** `object_bounds_cache_*` in `ps2_local.c:229–260` mirrors bounding spheres per absolute index for reach tests; invalidated by epoch bump — auxiliary to CE objects, not a second identity store.

### 5. HCU delete / destroy path

| API | Behavior |
|-----|----------|
| `object_delete` | Marks deletion (`object_delete_initial_recursive`), deferred finalize in `objects_update` (`objects.c:1823–1830,4544–4547`) |
| `object_delete_immediately` | Initial + `object_delete_recursive` in one call (`objects.c:4068–4076`) |
| `object_destroy` | Gameplay death: effects, child notify, then `object_delete` (`damage.c:623–649`) |
| `object_delete_recursive` | Widgets/attachments, disconnect from map, `object_type_delete`, `object_header_delete` → `datum_delete` + pool free (`objects.c:5117–5150,706–721`) |

Garbage collection compacts the object memory pool and can force-delete deactivated objects (`objects.c:4104+`, port co-op garbage distance tweaks `objects.c:68–79`).

**Local PS2:** `network_objects_may_delete` always `TRUE` (`ps2_local.c:139–144`); no distributed host veto.

### 6. Map transition / ownership of arrays

On old map unload, `objects_dispose_from_old_map` walks all header indices, frees pool blocks, `datum_delete` each, then `data_make_invalid` (`objects.c:1095–1128`). New map: `data_make_valid` + empty via `data_delete_all` inside `data_make_valid` (`data.c:341–348`, `objects.c:1078`).

`object_header_data` and `object_memory_pool` are allocated from **`game_state_malloc` / `game_state_data_new`**, not the parent EE arena (`objects.c:1045–1046`, `game_state.c:859–877`). Map-transition correctness depends on `game_state` allocation discipline (M0/M2 arena routing is a separate gate).

### 7. Parent `object_table_t` lifecycle (snapshot-oriented prototype)

| Operation | Parent behavior | CE equivalent |
|-----------|-----------------|---------------|
| Create | Append at `t->count`, memset `object_t` (`sim/objects.c:27–28,152–172`) | `object_new` + typed datum |
| Identity | Dense `0..count-1` | `(salt, absolute_index)` handle |
| Update | Animation frame only (`sim/objects.c:55–67`) | Full physics, damage, attachments, AI hooks |
| Delete | **None** | `object_delete` / `object_destroy` + GC |
| Pose for render | `objects_pose` / `objects_pose_model` from table + world sections (`sim/objects.h:57–63`) | `object_get_node_matrices`, model animation state on datum |

`obj_render_t` holds `const object_table_t *table` and reads it during the GS pass (`obj_render.h:11–12`) — today that table is the same structure `main.c` animates.

### 8. Parent bridge: where authority leaks

1. **`play_ee.c`** — After real `objects_tick`, stores pointers to the engine table and overwrites a spawned biped’s `pos`/`root` to follow the parent `mover` collision body (`play_ee.c:157–163,168–200`). That is **parent simulation writing the render table**, not consuming an immutable post-tick snapshot.
2. **`combat_targets_update`** — Rebuilds targets each tick from the parent table; retains `vital` only when `(object_index, definition, model tags)` match (`combat_targets.c:207–271`). Identity is **table slot**, not CE handle; no generation.
3. **`vital.h`** — Documents parent vitality as normalized like CE object datum fields, but storage is separate from any HCU `object_datum` (`vital.h:1–11`).

### 9. Planned snapshot ownership (not implemented in tree)

M3 step 5: after each **completed CE tick**, a PS2 snapshot builder publishes immutable transforms, node palettes, cameras, HUD work, and render-only effect requests into fixed storage (`plans/5.hcu-remake.md:148`). `docs/source-audit.md:15` assigns **HCU publishes / parent consumes**; renderer may skip passes without mutating simulation.

Existing **hybrid proof** (`src/hybrid/core.c`, `replay.c`) only demonstrates datum create/move/delete and a value-type `hybrid_snapshot` for schedule invariance — not CE object fields or GPU records.

There is **no** production `snapshot_builder` linking HCU `object_get` / node matrices to `object_t` or a new DMA-facing struct in this repository state.

### 10. Tick ordering vs render (HCU)

`game_tick` runs `objects_update` **before** `players_update_after_game` and HUD (`game.c:358–394`). Rendering on CE historically occurs outside this function via `interface_draw_screen` / rasterizer (see `docs/hcu-ps2-platform-placeholder-audit.md`). For PS2, any snapshot must be taken at a defined boundary **after** the tick slice that owns object/node matrix updates, and parent draw must not call back into `object_translate` or parent `move.c`.

### 11. Capacity notes (evidence only, not budget sign-off)

| Constant | PS2 header value | Role |
|----------|------------------|------|
| `HALO_PORT_MAXIMUM_OBJECTS_PER_MAP` | 2048 (`halo_ps2_limits.h:34`) | Header datum cap |
| `HALO_PORT_OBJECT_MEMORY_POOL_SIZE` | 0x100000 (`halo_ps2_limits.h:35`) | Variable object bodies |
| `HALO_PORT_MAXIMUM_RENDERED_OBJECTS` | 256 (`halo_ps2_limits.h:37`) | CE render list cap |
| `OBJ_MAX` | 1024 (`sim/objects.h:13`) | Parent table cap |

`halo_ps2_limits.h:4–8` explicitly states object counts are **not** evidence pools fit the EE budget. Do not use these to close M0 gates.

### 12. Integration status

- HCU closure compiles object sources under `port/ps2/port.json` (`source/objects`), but the **parent world/play ELF** (`tools/ee-world.mk`) still links `sim/objects.o` and optional `src/game/*` — **not** `game_tick` + CE `objects_update` on the same image path as production M3.
- M3 exit gate: real player movement/collision on CE records; render-schedule invariance; parent table as reader only (`plans/5.hcu-remake.md:150`) — **open**.

## Interface contracts for the main agent

### Authority

| Concern | Owner | Consumer must not |
|---------|--------|-------------------|
| Object identity / handles | HCU `object_header_data` + `datum` handles | Reuse parent dense indices as CE identity |
| Transform, velocity, animation, damage, attachment graph | HCU `object_datum` / typed datums | Write `object_t` in `sim/objects.c` for gameplay |
| Collision queries | HCU physics (M3 collision auditor) | Keep `collide.c` / `collpack.c` as second authority after parity |
| Renderable pose | **Post-tick snapshot** (to be defined) | Call `objects_pose` on parent table for entities backed by CE sim |
| Idle scenario props (until CE drives them) | Either CE scenario objects or explicit static snapshot rows | Silently dual-sim the same entity in both tables |

### Snapshot record (minimum fields to plan)

For each visible/simulated entity the renderer needs:

1. **Stable CE handle** — full `long object_index` (generation + absolute index), not parent slot alone.
2. **Definition / model identity** — tag indices or stable scenario def keys needed to resolve HP2 `model` / `graph` / permutations (parent world uses `scen_def` + `model_info` — `sim/objects.c:24–47`).
3. **Root transform** — position, orientation (parent `object_t.root` / `pos` + `objects_pose` inputs).
4. **Animation state** — graph index, anim index, frame (maps to `object_t.anim`, `frame`, `flags` OR bypass parent anim tick entirely and pass baked node palettes).
5. **Visibility / region permutations** — `region_count`, `perm[]` (`sim/objects.h:24–28`).
6. **Optional**: first-person / weapon nodes (coordination with `m3_first_person_pose_auditor`).

Storage: caller-provided buffers in `frame_scratch` or named budget region (`plans/5.hcu-remake.md:148`); **no heap** on publish path.

### Lifecycle hooks the adapter must observe

| Event | HCU signal | Parent action |
|-------|------------|---------------|
| Map load | After `objects_place()` completes (`game.c:705–707`) | `combat_targets_reset`; rebuild snapshot catalog; do **not** `objects_spawn_bsp` the same entities unless explicitly static-decor only |
| Tick end | After `objects_update` (and any required `players_update_after` if pose depends on it) | Copy/transform into snapshot; parent `objects_tick` must not advance CE-owned animation |
| Object delete | Handle invalid after `datum_delete` | Drop snapshot row by CE handle; parent slot reuse must not preserve vitals keyed only by slot |
| BSP switch | `object_types_reconnect_to_structure_bsp` / placement flags (`object_types.c:1169–1177`) | Invalidate snapshot clusters; resync from CE |

### Deprecation targets (after parity)

- `play_ee.c` table mutation and `__wrap_objects_tick` pose path (`play_ee.c:157–200`).
- `combat_targets` identity keyed by `uint16_t object_index` without CE handle (`combat_targets.h:38–39`).
- Parent `objects_tick` animation for CE-backed entities (`sim/objects.c:55–67`).

Keep modules as fixtures until HCU paths pass (`plans/5.hcu-remake.md:177`).

## Recommended tests / fixtures

1. **Datum generation** — Extend `src/hybrid/core.c` pattern: create/delete/reuse index; assert `datum_try_and_get` fails on stale handle after delete (mirrors `data.c:351–374`).
2. **Handle export** — Host test: given mocked `object_header_datum.identifier` and absolute index, snapshot encoder round-trips `DATUM_INDEX_NEW` (`cseries.h:170`).
3. **Map transition** — Call sequence `objects_initialize_for_new_map` → place N objects → `objects_dispose_from_old_map`; assert `object_header_data->actual_count == 0` and pool compact (`objects.c:1095–1128`).
4. **Delete deferral** — `object_delete` then single `objects_update`; assert header row cleared only after delete phase (`objects.c:1823–1830,4544–4547`).
5. **Render-schedule invariance** — Reuse `hybrid_replay` cadence harness (`src/hybrid/replay.c`) against a future CE state hash API (`plans/5.hcu-remake.md:176`) once snapshot exists.
6. **Parent regression conversion** — Port `combat_targets_update` vitals retention tests to key on CE handle + definition/model tags, not dense index alone (`combat_targets.c:265–270`).
7. **ABI** — Keep `ps2_abi.c` `object_datum` size gate in CI (`ps2_abi.c:41`).

## Dependencies on other investigators

| Investigator | Dependency |
|--------------|------------|
| `m3_snapshot_render_auditor` | Defines snapshot memory layout, publish point, and parent `obj_render` / `fpview` consumption; this report’s handle + pose fields must align with that schema. |
| `m3_collision_owner_auditor` | When collision moves to CE, snapshot must expose posed collision meshes or CE queries must replace `combat_targets_ray` on parent table. |
| `m3_player_movement_auditor` | Player unit object index and camera/first-person timing relative to `objects_update` vs `players_update_*`. |
| `m2_*` / loader | Scenario placement and BSP reconnect drive create/delete storms (`object_types.c:1134–1157`); tag image must supply scenario palettes before `objects_place`. |
| `m0_runtime_ownership_auditor` | `game_state` vs parent arena placement for `object_header_data` and pool bytes. |

## Open questions

1. **Snapshot tick boundary** — Is `objects_update` alone sufficient for node matrices, or must the snapshot run after `players_update_after_game` / `first_person_weapons_update` (`game.c:378–392`)? Needs trace on player/biped nodes.
2. **Static scenario decor** — Until CE drives all placed scenery, will parent `objects_spawn_bsp` remain for HP2-only props while CE simulates units/weapons/projectiles? Dual representation risks duplicate draws unless partitioned by object class.
3. **`cached_object_render_states`** — On PS2, is this array retired with software rasterizer removal, or does the snapshot need to subsume its lighting LOD fields (`render_objects.c:174–184`)?
4. **Maximum simultaneous snapshot entities** — CE `MAXIMUM_RENDERED_OBJECTS` (256) vs parent `OBJ_MAX` (1024) vs `COMBAT_TARGET_MAX` (64): which cap governs the unified snapshot for combat + render?
5. **Editor / `game_in_editor`** — Editor uses heap-backed larger pools (`objects.c:1048–1054`); PS2 production path assumes `!game_in_editor()` — confirm editor is excluded from EE closure.
6. **Distributed / co-op** — `network_objects_new_object_index` and co-op attach notes (`objects.c:143–153`, `ps2_coop.c`) — confirm no hidden second object namespace on local PS2 beyond `ps2_local.c` stubs.

## Handoff summary

- **HCU** already implements full CE object lifecycle: generation-safe handles (`data.c` + `object_header_data`), create (`object_new` / scenario placement), tick update (`objects_update`), deferred delete and `object_destroy`, map-scoped reset/dispose, and a separate render-state datum cache (`render_objects.c`).
- **Parent `object_table_t`** is a fixed-size, dense, animation-only HP2 scenario mirror with no delete/generation; it is explicitly documented as future shared state for render (`sim/objects.h:1–3`) but **today** is written by `play_ee.c` for diagnostics.
- **M3 work** is to insert a **one-way, post-tick snapshot** from HCU handles/poses into parent-fixed memory, teach `obj_render` / `fpview` to read that snapshot only, and stop using parent table indices as gameplay identity (`combat_targets`, `vital`).
- **Do not** treat parent `OBJ_MAX` or HCU pool constants as proof of fitting memory; **do** preserve CE handle semantics in any parent-side record that outlives a single map or survives slot reuse.

## Corroboration

### Agreements

- **m3_snapshot_render:** Post-tick immutable snapshot is the integration seam; parent table becomes consume-only animation mirror.
- **m0_runtime_ownership:** CE identity authority; retire parent spawn/tick simulation paths.
- **m3_collision_owner:** Hit queries and combat targets must not use parent slot indices after integration.
- **m0_memory_ledger:** Object pool under `game_state` / `resident_gameplay` — snapshot rows must not duplicate full datums (**m1_dma**).
- **m3_first_person_pose:** FP entities are CE-driven; snapshot carries posed state for `obj_render`/`fpview`.

### Conflicts

- **Cap tension (open):** `OBJ_MAX` 1024 vs CE render caps — Round 3 integrator picks governing cap for snapshot schema; not a lifecycle ownership dispute.

### Updated handoff

1. Define snapshot record: generation + handle + pose (+ render subset) — coordinate with **m3_snapshot_render** and **m1_dma**.
2. Deprecate `play_ee.c` writes to `object_table_t` for gameplay identity once snapshot publishes.
3. Map transition: CE `objects_dispose` ordering is authoritative; parent table reset follows snapshot clear.
