# M2 Step 9 — Failure-state snapshot and retry audit

**Scope:** report-only adversarial review of the current HCU map service, parent CTAG mount, PS2 cache adapter, CE scenario/BSP lifecycle, and the tests that compose them. No runtime, test, or plan source was edited for this audit. The worktree contains extensive unrelated user changes; this report is a new standalone artifact.

## Summary

The existing code has a strong transactional foundation, and substantial host failure coverage already exists. The independent test layers currently establish three useful facts:

1. A parent mount failure rolls its arena cursor back and leaves the singleton cache unpublished (`tests/ctag_mount_main.c:681-718`, `:726-781`).
2. A retail CE BSP switch that fails to load, pass the port-capacity verifier, or pass the schema boundary rematerializes the previous BSP; if both candidate and old BSP fail, CE publishes a null BSP and goes to the menu (`tests/hcu_scenario_bsp_switch_main.c:621-676`).
3. A same-map reload can retain only a pending identity across preflight/unload, revalidate the source after release, fail closed on a changed source, then retry successfully; it also rejects a loader call while the old owner is still live (`tests/ctag_mount_main.c:523-607`).

These are not yet one adversarial failure-state proof. The successful retail transaction runs real CE scenario switching and real CE tag/BSP validation over retail `a30`/`a50` packages, but its failure injection is limited to the BSP section-loader callback, a wrapper-level schema rejection, and the wrapper-level port verifier. In particular, it does not inject failures at every parent mount stage or through the actual `cache_file_read()` CBSP handoff while asserting the full cross-layer state tuple after each failure. The service fixture tests most source/preflight rejection paths separately, but its checks are hand-written subsets of that tuple.

The smallest useful next target is a **single host state-snapshot assertion helper and table-driven failure matrix in the existing retail CE transaction executable**, without changing the production code or `plans/7.hcu-remake-m2-m4.md`. It should snapshot the CE publication, cache, parent owner, BSP scratch, source-reader, and pending-request state at the appropriate transition boundary, then assert either (a) the old logical BSP has been rematerialized, (b) the initial map-load failure is safe-null, or (c) the preflight-before-unload rejection preserved the entire old state. Current sources expose the required observables; no new runtime test hook is required for existing load/schema/verifier failures. Parent-stage failures (CBIX parse/registration, CBSP package read/materialization, target cache read) may need narrowly scoped callbacks already present in `ctag_mount_backend` or a new host-only wrapper.

## Current lifecycle and ownership

### Map-service staging and map mount

- `hcu_map_service_preflight()` rejects non-UI entries before opening assets while their memory peaks remain unqualified, and refuses to overwrite a live map owner. For the exact same active map it records `staged_entry`, `staged_map`, and `reload_pending`, without allocation or another source open (`src/stream/hcu_map_service.c:230-266`). For a new map, it stages the identity, opens the resource source, decodes HMAP/CTAG/CRNG/CBIX under a map-arena mark, validates identity/extents/cache size/source hash, releases all preflight allocations, and then sets `identity` and `preflight_ready` (`:268-322`).
- `map_loader()` requires the released owner for deferred reload, reruns preflight when the source must be checked again, verifies staged identity/catalog membership, then calls `ctag_mount_hp2_verified_source_discover()` (`src/stream/hcu_map_service.c:95-151`). A successful mount binds decoded CTAG/CRNG/CBIX plus the backing reader to the parent owner; the source stays open because cache callbacks depend on it.
- `map_unloader()` calls `ctag_mount_unload()` for an active mount, or closes a staged source otherwise, clears `preflight_ready`, and preserves the staged identity only when `reload_pending` was true (`src/stream/hcu_map_service.c:158-173`). `hcu_map_service_shutdown()` always clears pending state and unregisters cache callbacks (`:325-336`).
- One noteworthy control-flow oddity: on parent mount failure, `map_loader()` clears pending state and returns `1` (`src/stream/hcu_map_service.c:138-143`), while the PS2 cache subsequently checks `cache_files_precache_map_loaded()` and thus returns false if no payload was mounted (`submodules/halo-ce-universal/port/ps2/src/ps2_cache.c:331-347`). This is fail-closed in the current adapter, but the loader callback’s return value is success-shaped and easy to misread. The test should assert both callback outcome and final mounted state; later code cleanup should make the callback contract explicit rather than infer it from a second check.

### Parent mount transaction and lazy BSP owner

- `ctag_mount_hp2_internal()` captures the owner mark, decodes CTAG and CRNG into transaction-owned memory, validates the resource index and calls the backend mount. It restores the owner mark if any of those stages fails; backend mount failure also clears the mount object (`src/stream/ctag_mount.c:112-173`).
- The catalog variants mount the base cache first, then decode/validate CBIX and register the BSP loader; failures in either later stage call `ctag_mount_unload()` so cache unpublication precedes owner rollback (`src/stream/ctag_mount.c:199-275`). `ctag_mount_unload()` releases any BSP first, unmounts the CE cache, closes its owned reader only after unmount, restores the owner mark, and zeroes the handle (`:277-290`).
- Lazy BSP loading checks exact CBIX offset/size, avoids overlap with the tag extent/resource index, releases the previous encoded CBSP, decodes the selected section into scratch, asks the PS2 backend to materialize it, and records a scratch mark only on success (`src/stream/ctag_mount.c:67-105`). Failure restores the scratch mark. This behavior is tested indirectly by normal switching and failed reads, but no one test currently snapshots both encoded payload/scratch and CE/cache globals for every failure point.

### CE scenario/BSP behavior

- `scenario_switch_structure_bsp()` validates the requested BSP index before side effects. For a real switch, it stops time/disables collision logging, disconnects BSP-dependent procedures, unloads the old BSP, and clears the CE logical indices (`submodules/halo-ce-universal/source/scenario/scenario.c:1101-1127`).
- A candidate is loaded, then subjected to `structure_bsp_port_verify()` (`:1130-1140`). On failure, CE nulls the global structure/collision/BSP3D pointers and attempts to reload the old BSP by *identity*, not by retaining its invalidated pointer. If that retry also fails, it requests main menu (`:1141-1169`). If a BSP loads, CE republishes its structure/collision pointers and both indices and reconnects dependent procedures; when it was the old BSP reloaded, the function correctly returns false (`:1172-1195`).
- The initial scenario path calls `scenario_switch_structure_bsp(0)` and only reports scenario load success if its first BSP succeeds (`scenario.c:1230-1247`). This initial failure branch is not part of the retail fixture’s current positive transaction path.

## What the current tests do and do not establish

### Covered, with evidence

| Failure/switch case | Existing coverage | State asserted |
|---|---|---|
| Invalid BSP indices and same-index request | `tests/hcu_scenario_bsp_switch_main.c:703-718` | No unload/load/verification side effects; current fake CE BSP remains published. |
| Candidate BSP section-load failure with old BSP active | Synthetic CE fixture `:621-635`; retail CE fixture `:621-635` uses `fail_load_index` at `:261-267` | Old index/global/tag instance restored; candidate tag pointer null; selected order candidate then old; original B000 bytes match snapshot. Retail also checks BSP scratch released. |
| Candidate port verifier rejection | Synthetic `:636-647`; retail `:636-648` | Old BSP rematerialized; candidate pointer null; first BSP bytes restored. Retail’s real CE port verifier executes before injected extra rejection. |
| Candidate schema rejection | Synthetic `:650-661`; retail `:650-661` | Old BSP rematerialized; candidate pointer null; original BSP cache bytes restored. Retail invokes the actual CE `tag_validate_structure_bsp_actual()` before the injected rejection wrapper (`:183-213`). |
| Candidate and old BSP both unreadable | Synthetic `:663-676`; retail `:663-681` | Global and scenario indices become `NONE`; global BSP/collision/BSP3D and both candidate/old tag datum pointers are null; menu called; parent BSP scratch released. |
| Pre-unload unsupported-map rejection | `tests/ctag_mount_main.c:501-519` | Existing UI mount and owner usage survive; no extra source open/close. It does not compare every CE global/cache field. |
| Same-map preflight → owner release → source changed before deferred reload | `ctag_mount_main.c:523-582` | Owner/source released; changed source fails without mount/arena/scratch leak; source restored, fresh preflight and remount succeeds. |
| Deferred load attempted before owner released | `ctag_mount_main.c:589-607` | Cache unmounted but parent mount/source/arena preserved; service shutdown then performs release. |
| Preflight/mount rejection, malformed package, capacity failure, backend mount failure | `ctag_mount_main.c:681-718`, `:726-781`, and `tests/test_retail_ui_ctag_mount.py:142-215` | Owner mark returns to baseline; source closes; mount inactive/cache unpublished; a later successful load is possible in the same process. |
| CBSP requested range not available / resource read failure | `ctag_mount_main.c:805-823`, `:835-844` | Failed completion and scratch release or untouched destination buffer. This is cache-read/mount-level, not full CE rollback publication proof. |

### Missing or too weak for the Step 9 acceptance question

1. **No uniform cross-layer snapshot assertion.** Existing tests assert different subsets. The retail CE transaction does not snapshot/compare `service` fields, arena marks/high-water, source descriptor/reader position, `ps2_cache` mounted map and callback state, `cache_file_globals`, and all CE BSP pointers/indices at every failure boundary. The independent tests can all pass while a field outside their local assertions leaks stale state.
2. **No full real scenario-load initial-BSP failure transaction.** The current retail fixture first mounts and manually activates the CE tag image, then explicitly calls BSP switching; it does not run real `scenario_load()` with BSP 0 failing and verify scenario/tag teardown and retry (`tests/hcu_scenario_bsp_switch_main.c:480-584`, `:695-752`; CE startup is at `scenario.c:1230-1247`).
3. **No preflight failure snapshot with an already active CE old scenario.** Service-level unsupported map and changed-source cases check the parent mounted UI and streaming usage, but not the scenario’s tag globals, old CE indices/pointers, BSP registration, cache header, or old BSP bytes together (`ctag_mount_main.c:501-519`, `:545-573`). This matters because `scenario_tags_load()` preflights before unload; a rejected preflight must leave the previous game in a fully usable state.
4. **Post-unload revalidation failure matrix is only one fault.** The current guest/host lifecycle injects same-length source corruption between preflight and remount (`ctag_mount_main.c:545-582`). It does not inject post-unload source-open failure, HP2 header/table/CRC/read failure, HMAP identity/hash failure, CTAG parse/capacity failure, CRNG/index failure, CBIX catalog failure, backend CTAG mount failure, or BSP callback-registration failure through the *same deferred-reload path*. Lower-layer non-reload tests cover many, but not the reload state transition.
5. **Lazy CBSP failure not comprehensively composed with CE recovery.** The retail transaction injects B-section load failure (`hcu_scenario_bsp_switch_main.c:261-283`, `:621-635`) and schema/port rejection, but not a failure at each seam after successful section decode: malformed CBSP materialization, destination collision/tag-image overlap, `cache_file_read()` short/EOF behavior with the existing BSP evicted, backend BSP mount refusal, CE range/schema rejection after real PS2 materialization, old-BSP rematerialization failing specifically after candidate failure, and retry after each. CBSP parser standalone fault tests do not prove CE/parent publication rollback.
6. **Assertions of arena high-water allow no untracked lifetime distinction.** The tests often assert `used` returns to baseline and `high <= cap`; this proves no live allocation leak, but high-water is intentionally historical and need not roll back. Snapshot the prior `high` separately and assert the expected monotonic behavior, rather than treating `high == baseline` as required or ignoring unexplained growth.
7. **No invariant assertion for callback/resource-owner coherence.** On all terminal states, verify the singleton cache is either fully mounted with reader alive and the correct BSP loader/release callbacks, or fully unmounted with no cache payload, no registered callback that points into a dead `ctag_mount`, no active reader, no owner bytes, and no BSP scratch. `ps2_cache_unmount_ctag()` clears `mounted_payload` and its reader fields, but callback registration details and owner lifetime need explicit checks (`ps2_cache.c:76-85`, `:131-159`, `:204-210`; parent callback register/unregister is in `ctag_mount.c:230-234`, unload `:277-290`).

## Failure-state fields to snapshot

Use two logical snapshots: **old-state preservation** before a failure that must happen pre-unload, and **terminal/recovered-state** after a failure that happens after CE has released/replaced the old BSP. Do not demand restoration of invalid pointers or of bytes overwritten in the fixed BSP cache; CE’s intended recovery is rematerialization by old BSP index.

### CE publication and cache datum state

- `global_scenario`, `global_scenario_index`, `scenario_globals` pointer and `scenario_globals->structure_bsp_index`.
- `global_structure_bsp_index`, `global_structure_bsp`, `global_collision_bsp`, `global_bsp3d`.
- For the old and candidate tag datums: `global_tag_instances[datum].base_address`, `global_tag_count`, and `cache_file_globals.tags_loaded`, `.tag_header`, `.structure_bsp_header`, and `.header` identity fields (map name, tag extent, file length).
- For successful old-BSP recovery, compare the restored logical index/datum and re-derived pointers into the current BSP cache, plus a deterministic digest of the rematerialized old BSP bytes; pointer equality to the pre-switch BSP cache payload is not the right invariant if the cache is reused.
- When both BSP loads fail: both indices must be `NONE`, all three global BSP pointers and old/candidate datum bases null, and the main-menu path requested. Also ensure no reconnect callbacks run against null BSP state.

### Parent map-service, cache-adapter, and source state

- `hcu_map_service`: initialized; active `mount.active`; `mount.owner`, `mount.arena_mark`, `mount.bsp_active`, catalog count and selected extent; `source.active`, reader descriptor/size/cursor; `identity`; `staged_entry`, `staged_map`, `preflight_ready`, `reload_pending` (`src/stream/hcu_map_service.h:8-20`). On active-map preservation, these should remain the same values; on safe-null failure they should reach the documented clean inactive values.
- PS2 cache singleton: mounted payload/map/CTAG metadata, backing `read_at` and context, BSP payload/view/extent, `cache_file_is_open`, BSP load/release callback/context, and map load/preflight/unload callbacks. Most are private statics, so expose them through test-only inspectors or use public `cache_file_open`, `cache_files_precache_map_loaded`, read-completion flags, and mount state. Do not add production debug exports solely to satisfy a host test.
- Source reader/file bridge: active flag, descriptor, size, file identity, cursor/seek position if observable, and open/close counters. The active mounted map needs its source reader retained; all unmounted terminal states must have it closed exactly once.

### Memory and callbacks

- Both arena objects’ identity (`base`, `cap`), pre-transaction `used`, post-transaction `used`, and pre/post `high`; record the BSP scratch mark plus whether the backend materialized BSP is active.
- `s_active_mount` relationship and whether the backend register/unregister counts balance. After release, no callback context may point at a zeroed/dead mount. During active state, the read callback context must be the active mount and the file reader must remain valid.
- Keep fixed cache destination bytes/digest only for assertions where no overwrite is expected. After candidate BSP overwrites the single CE BSP cache and both old/new loads fail, the bytes may contain a failed-read pattern; the safety requirement is null publication, never stale pointers.

## Required failure matrix and safe semantics

Each row needs a named injection point and a reusable snapshot/assert helper. “Before unload” means CE never called old-map teardown; “after unload” means the old scenario is already gone and cannot be resurrected through stale pointers.

| Stage / injected fault | Safe expected outcome | Current evidence / gap |
|---|---|---|
| Preflight: missing asset, short read, bad package CRC/HMAP/hash, invalid CTAG/CRNG/CBIX, capacity refusal | Return failure before old scenario unload. Preserve old map, BSP/cache globals, owner bytes, reader, callbacks, and arena mark exactly. | Many are parent fixture covered; no composed CE old-state snapshot. |
| After CE unpublishes old scenario and parent owner releases: reopen/re-read fails | No old CE scenario pointers remain; no mount/source/arena/BSP callback owner remains; fail to menu/known no-map state. Retry begins from clean state and can load the exact asset once restored. | Same-length hash mismatch is covered; other reload failure stages absent. |
| Parent base mount: CTAG/CRNG decode, source/resource extent, cache-size check, backend CTAG mount fails | Restore owner mark; close owned source once; cache singleton unmounted; no dangling callbacks; CE load fails safely. If an old scenario had already been torn down, enter menu rather than claim playability. | Lower-level rollback is tested independently; deferred reload composition and full callback snapshot missing. |
| Parent catalog mount: CBIX section/parse or BSP-loader registration fails after CTAG mount succeeded | `ctag_mount_unload()` first unpublishes cache and callbacks, then closes reader and restores owner mark; no partially mounted map. Retry succeeds in same process. | Catalog corruption and main mount failure are tested, but failure after base-mount commit at callback registration should be directly injected and asserted. |
| BSP candidate: payload decode/read fails or CBSP materializer rejects | `scenario_switch_structure_bsp()` rematerializes old BSP from its exact extent, republishes old logical index/pointers, reconnects dependents, and returns failure for candidate. | B-section read fault exists; materializer failure and state tuple coverage should be added. |
| BSP candidate: CE schema or PS2 capacity validator rejects | Unload rejected candidate; reload old BSP and verify it again; preserve/recover CE tag datum and collision globals; return failure without menu if recovery succeeds. | Both paths are represented; actual real schema validator is called in retail fixture, but rejection uses wrapper injection after actual pass. |
| Candidate and old BSP both fail | Publish safe-null indices/pointers and clear both BSP tag bases; request main menu; release parent BSP scratch and any encoded CBSP. Never leave pointer into overwritten single BSP cache. | Already substantially asserted in retail fixture; extend to cache globals, callbacks, scratch, and retry. |
| Retry after recoverable candidate failure | A later request for the candidate after removing injection should mount it successfully; failed attempt must not poison `s_active_mount`, map service staging, cache callback table, or arena cursors. | Current CE tests end after failure branch; there is no immediately-following same-process recovery switch for each CE-stage failure. |

## Minimal implementation/test target (no runtime changes required initially)

Add a `struct failure_state_snapshot` plus `capture_failure_state()` / `assert_state_*()` helpers to **`tests/hcu_scenario_bsp_switch_main.c`** only. This is the narrowest fixture that already links `scenario.c`, actual CE `tag_validate.c`/schema units, PS2 `ps2_cache.c`/CTAG/CBSP materializers, parent `ctag_mount.c`, and real audited `a30`/`a50` HP2 packages. Keep edits in that test file (and its Python launcher only if an injection argument is needed); do not alter `hcu_map_service.c`, cache runtime, or the plan as part of the first slice.

1. Capture the known-good B000 state after initial `scenario_switch_structure_bsp(0)`: current CE index/pointers/tag datum, `cache_file_globals` identity, parent mount + source state, owner/scratch arena base/cap/used/high, cache-loaded result, and a hash of B000’s materialized bytes.
2. Convert the current `fail_load_index`, `fail_verify_mask`, and `fail_schema_mask` blocks into a table-driven sequence. For each, assert candidate attempt followed by old extent selection, restored old-state invariants, no leaked BSP scratch, balanced CE register/unload and disconnect/reconnect lifecycle counts, then disable the fault and immediately switch successfully to the candidate and back. This catches stale state that a one-shot recover branch misses.
3. Add host-only injection for CBSP load-section decode/CRC failure and PS2 materialization refusal. Existing seam: `load_package_section()` at `:244-283`; a wrapper around `ps2_cache_mount_cbsp_for_extent()` or test backend callbacks can force failure without modifying production code. Assert CE fallback and same-process retry.
4. Add a real initial BSP-0 failure case from `NONE` and exercise `scenario_load()` if feasible in the existing link; otherwise explicitly test the same switch entry from `NONE` and mark full `scenario_load()` teardown as remaining. Require null CE BSP publication, no menu spam if this matches current CE semantics, owner/source lifecycle consistent with the scenario-tags owner, and successful retry after clearing injection.
5. Separately extend the existing service fixture only after the CE snapshot helper lands: take an old-state snapshot before preflight; run preflight corruption/unsupported-map cases; compare the complete old tuple; after intentional owner release, inject each deferred reload failure stage and require a clean terminal tuple plus exact retry. This avoids merging direct map-service/service-test changes into the CE transaction fixture prematurely.

This host test is necessary but insufficient for M2 exit: it cannot demonstrate PS2 physical RAM fit, EE FileXio/OPL/optical behavior, PCSX2 guest fault-injection, or playable behavior. Preserve those gates in `plans/7.hcu-remake-m2-m4.md`; current status at Step 2 explicitly says failure-before-unload and failure-after-unload retry remain unproven for the guest (`plans/7.hcu-remake-m2-m4.md:195-199`).

## Targeted follow-up questions / risks

- Can the PS2 cache adapter expose a strictly test-only state query without enlarging production symbols? Prefer black-box observations or `#ifdef`-guarded fixture support over new public runtime API.
- Does the M2 transaction intend a failed post-unload map mount to call `main_goto_main_menu()` directly, or does its caller reliably do so after `scenario_load()` returns false? Confirm through `game_unload()`/menu path before asserting a particular UX, but always require safe-null/no dangling owner state.
- `ctag_mount_unload()` assumes the backend's `unmount()` synchronously clears all CE cache callbacks before owner bytes are released. This assumption is documented but not represented as a status-returning contract (`src/stream/ctag_mount.h:62-64`, implementation `ctag_mount.c:277-290`). Failure injection should verify the current backend actually clears those statics.
- Existing arena `high` is a historical maximum. A failure can legitimately raise it while returning `used` to baseline; report before/after rather than treating high-water rollback as a correctness condition.

## Source index

- Map service state shape: [`src/stream/hcu_map_service.h:8-20`](../../src/stream/hcu_map_service.h#L8)
- Service preflight/commit/rollback: [`src/stream/hcu_map_service.c:82-173`](../../src/stream/hcu_map_service.c#L82), [`:230-322`](../../src/stream/hcu_map_service.c#L230)
- Parent CTAG/CBIX transaction and BSP lazy load: [`src/stream/ctag_mount.c:67-105`](../../src/stream/ctag_mount.c#L67), [`:112-173`](../../src/stream/ctag_mount.c#L112), [`:199-290`](../../src/stream/ctag_mount.c#L199)
- Cache adapter preflight/map ownership and BSP callback seam: [`submodules/halo-ce-universal/port/ps2/src/ps2_cache.c:162-202`](../../submodules/halo-ce-universal/port/ps2/src/ps2_cache.c#L162), [`:331-405`](../../submodules/halo-ce-universal/port/ps2/src/ps2_cache.c#L331)
- CE BSP switch and initial scenario load: [`submodules/halo-ce-universal/source/scenario/scenario.c:1088-1198`](../../submodules/halo-ce-universal/source/scenario/scenario.c#L1088), [`:1230-1247`](../../submodules/halo-ce-universal/source/scenario/scenario.c#L1230)
- Retail transaction fixture injection/state checks: [`tests/hcu_scenario_bsp_switch_main.c:244-293`](../../tests/hcu_scenario_bsp_switch_main.c#L244), [`:487-681`](../../tests/hcu_scenario_bsp_switch_main.c#L487)
- Service preflight/reload fault fixture: [`tests/ctag_mount_main.c:501-607`](../../tests/ctag_mount_main.c#L501), [`:681-781`](../../tests/ctag_mount_main.c#L681)
- Python composed service tests: [`tests/test_retail_ui_ctag_mount.py:142-215`](../../tests/test_retail_ui_ctag_mount.py#L142)
- Current M2 Step 2 gate wording: [`plans/7.hcu-remake-m2-m4.md:195-199`](../../plans/7.hcu-remake-m2-m4.md#L195)
