# M2: smallest host fixture for real CE scenario/map-service lifecycle

Date: 2026-10-21  
Scope: report only; no implementation edits.  
Question: how to compose the real HCU `scenario_load()` / `scenario_unload()` path with the production parent `hcu_map_service` against audited UI assets, and what is the smallest useful executable fixture?

## Finding

There are already two substantial but separate host fixtures:

1. [`tests/test_retail_ui_ctag_mount.py`](../../tests/test_retail_ui_ctag_mount.py) builds `tests/ctag_mount_main.c` with the real parent map service, HP2 reader/section decoder, CTAG mount, HCU PS2 cache adapter, CTAG and CBSP materializers, and the actual audited `ui.hp2` plus `ui.map`. It proves parent preflight/mount/read/rollback/retry and owns synthetic lifecycle snapshots. It does **not** compile CE `scenario.c` or `cache_files.c`.
2. [`tests/test_hcu_scenario_bsp_switch.py`](../../tests/test_hcu_scenario_bsp_switch.py) compiles real HCU `source/scenario/scenario.c`; its retail integration variant also compiles real PS2 cache/CTAG/CBSP and parent mount/HP2 components and exercises CE's real `scenario_switch_structure_bsp()` over audited a30/a50 packages. It starts with manually published CE scenario/tag state and stubs unrelated CE services. It does **not** call `scenario_load()`, `scenario_unload()`, or the real parent `hcu_map_service`.

The smallest high-value next fixture is a **new composition mode** based on the retail-UI host executable, adding HCU's real `cache_files.c` and `scenario.c` while reusing the production parent service/backend sources and audited UI package. It should exercise one successful `scenario_load("levels\\ui\\ui")`, assert CE pointers and cache bytes are valid while mounted, then `scenario_unload()`, assert CE globals are cleared before the parent owner is released, and retry the full load/unload cycle in the same process. Keep it as a host/ILP32 harness; it is strong lifecycle evidence but not a replacement for the plan's target guest run or gameplay-map qualification.

## Source and existing fixture seams

### Parent service and storage owner

- [`src/stream/hcu_map_service.c`](../../src/stream/hcu_map_service.c#L82) owns staged request cleanup; [`#L97`](../../src/stream/hcu_map_service.c#L97) implements the cache loader callback and invokes `ctag_mount_hp2_verified_source_discover()`; [`#L160`](../../src/stream/hcu_map_service.c#L160) implements the CE/cache preflight callback; [`#L175`](../../src/stream/hcu_map_service.c#L175) registers those callbacks and binds `streaming`/`frame_scratch`; [`#L230`](../../src/stream/hcu_map_service.c#L230) executes HMAP/CTAG/CRNG/CBIX preflight; [`#L325`](../../src/stream/hcu_map_service.c#L325) shuts the service down.
- [`submodules/halo-ce-universal/port/ps2/src/ps2_cache.c`](../../submodules/halo-ce-universal/port/ps2/src/ps2_cache.c#L114) provides the cache callback registration/preflight seam. `ps2_cache_preflight_map()` at `#L179` calls the parent preflight; `cache_file_open()` at `#L355` exposes the mounted CTAG header; `cache_file_read()` at `#L375` serves tag bytes and the selected CBSP; `ps2_cache_release_map_owner()` at `#L196` delegates unmount to the parent callback.
- The existing exact source list and audited UI asset setup are in [`tests/test_retail_ui_ctag_mount.py`](../../tests/test_retail_ui_ctag_mount.py#L20) and its service-mode invocation around `#L55-L105`. Extend by adding the two CE sources and lifecycle roots; do not reimplement mount behavior in the test.
- [`tests/ctag_mount_main.c`](../../tests/ctag_mount_main.c#L77) has a useful parent-state snapshot, including arenas, mount pointers, source descriptor, staged flags, cache loaded query, tag/BSP cache hashes, and fake FileXio counts. The new composed fixture needs an additional **CE publication snapshot** rather than treating this existing snapshot as complete.

### CE load/unload path

- [`source/game/game.c`](../../submodules/halo-ce-universal/source/game/game.c#L609) calls `scenario_load()` and only then publishes `game_globals->map_loaded = TRUE`.
- [`source/scenario/scenario.c`](../../submodules/halo-ce-universal/source/scenario/scenario.c#L1230) implements the real `scenario_load()`: `scenario_tags_load()`, `scenario_definition_get()`, `game_globals_definition_get()`, and `scenario_switch_structure_bsp(0)` are the critical success chain. It returns false if tags or the initial BSP fail.
- [`source/cache/cache_files.c`](../../submodules/halo-ce-universal/source/cache/cache_files.c#L1214) implements the actual `scenario_tags_load()`: it opens the mounted map cache, verifies its synthetic header, synchronously reads tag image into CE's bound tag-cache span, validates the tag header/tags, publishes `global_tag_instances`, tag count and `tags_loaded`, and returns scenario datum index.
- [`scenario.c`](../../submodules/halo-ce-universal/source/scenario/scenario.c#L370) implements `scenario_unload()`: it calls `scenario_tags_unload()`, clears global scenario/BSP/collision pointers and indices, then under `HALO_PS2` invokes `ps2_cache_release_map_owner()` **after** CE unpublishes CTAG-backed pointers. This ordering is a central test assertion.
- [`cache_files.c`](../../submodules/halo-ce-universal/source/cache/cache_files.c#L617) implements tag-side unload: close sound/texture cache consumers, close the cache, deregister tag vertex/index handles, clear CE tag-table pointers/count and loaded flag. The UI fixture must provide real or carefully bounded test stubs for unrelated cache consumers and tag-buffer hooks, without stubbing the CE load/unload sequence itself.
- [`source/scenario/scenario.c`](../../submodules/halo-ce-universal/source/scenario/scenario.c#L1075) is the already-tested BSP switch/load path. Existing retail integration verifies it against audited a30/a50 packages, but the new UI fixture can use the UI package's audited single-BSP catalog and reuse the same adapter callback registration contract.

### Audited UI assets and existing test contract

`tests/test_retail_ui_ctag_mount.py` requires:

- `build/hcu-parent-link-probe/maps/ui-with-bsp.hp2`;
- `build/retail-maps/decompressed/ui.map`;
- a temporary asset root with `maps/ui.hp2` and `maps/ui.map`.

The test independently asserts the parent service loaded CTAG `1,510,628` bytes and that streaming usage is `1,550,444 / 1,572,864` after mount, and drives failures/retry. The lifecycle fixture should use these same built inputs and fail/skip with the existing explicit missing-artifact reason. UI is the appropriate first composed asset because it is the already-qualified M2 package; do not silently substitute a hand-built dummy CTAG or claim this validates gameplay-map capacity.

## Recommended executable and call sequence

Create a focused `tests/test_hcu_ce_map_lifecycle.py` plus a C harness, preferably reusing helper code from `hcu_scenario_bsp_switch_main.c` without making that existing fixture's manual-state semantics ambiguous.

1. Build the package root exactly as the current retail-UI test does; verify source-map and package hashes against the audited manifest before entering C.
2. Initialize/bind the fixed CE tag-cache and BSP spans, a `mem_layout_v2` with the production region identities/capacities, and a service with the real `hcu_map_service_init[_with_scratch]()`; bind the same audited `ui` catalog entry and `asset_root`.
3. Install the production PS2 BSP loader/release callback on the cache adapter. Reuse the parent `ctag_mount` BSP-catalog path; do not bypass `hcu_map_service` by directly calling `ctag_mount_hp2()`.
4. Mirror production pre-load ordering: call `ps2_cache_preflight_map("ui")` (the equivalent parent readiness request used before CE `game_load`). This should stage and validate the package but not publish a mount or CE scenario pointer.
5. Call the real CE `scenario_load("levels\\ui\\ui")`. The first `scenario_tags_load()` calls real `cache_file_open()` against the registered adapter, reads the actual CTAG image, and publishes the CE tag table. `scenario_load()` then resolves a scenario fixture backed by the actual loaded CE tag data or a narrowly documented fixture accessor, and runs `scenario_switch_structure_bsp(0)` over the actual audited CBSP. Prefer `game_load()` only if its required `game_options`/`game_globals` setup is available without bringing in an oversized game initialization graph; the acceptance target is real `scenario_load`, not the broader `game_initialize_for_new_map()`.
6. On success, assert the return value; non-null `global_scenario`, `global_structure_bsp`, `global_collision_bsp`, and `global_bsp3d` where the selected UI BSP supplies them; consistent scenario/BSP indices; `cache_file_globals.tags_loaded`; tag header and datum pointers inside the bound tag cache; mounted CTAG/BSP adapter state; source descriptor still owned by the mount; and arena/canary validity.
7. Call real `scenario_unload()`. At the `ps2_cache_release_map_owner()` boundary, assert CE's globals/indexes and tag-table publication have already been cleared/deregistered. Then assert parent mount inactive, source closed / descriptor `-1`, map and BSP owner cursors back to their pre-load marks, adapter cache query false, no stale BSP callback/payload, and unchanged canaries.
8. Repeat steps 4–7 in the same process. This detects stale singleton cache callbacks, tag header, source descriptor, `scenario_globals` or active mount state. Also include at least one preflight failure and one load-time failure (prefer corrupt/short CBSP after successful tag publication) followed by a successful same-process retry. For the failure case, assert scenario load returns false, CE is not left published, parent retains no leaked mount/source/arena allocations, and `scenario_unload()` is safe if called according to the production failure path.
9. Keep parent snapshot assertions and add a CE snapshot covering `global_scenario_index`, `global_scenario`, `global_structure_bsp_index`, scenario BSP index, `global_structure_bsp`, collision/BSP3d pointers, `cache_file_globals.tag_header`, `tag_instances`, `tag_count`, `tags_loaded`, cache open state/header, the tag-cache/BSP-cache hashes, map-loaded state if `game_load()` is included, and the parent's service fields. Record exact package/map hashes and source pins in test output.

## Minimal symbols/source closure and fixture stubs

Compile real production sources:

- Parent: `src/stream/hcu_map_service.c`, `hcu_map_catalog.c`, `ctag_mount.c`, `ctag_ps2_backend.c`, `ctag_map_source.c`, `ctag_resource_index.c`, `cbsp_catalog.c`, `hmap.c`, `sha256.c`; halo-ps2 `engine/src/world/section.c`, `stream/hp2.c`, `stream/file.c`, `core/mem.c`.
- HCU port: `port/ps2/src/ps2_cache.c`, `ps2_ctag.c`, `ps2_cbsp.c`.
- CE: `source/cache/cache_files.c`, `source/scenario/scenario.c`; include real `tag_validate.c` and schema units if the fixture runs retail tag validation (preferred). `scenario.c` also contains many unrelated functions, so compile with function/data sections and link with `--gc-sections` rooted at `scenario_load` and `scenario_unload`, plus their transitive real helpers.
- Test harness: either extend `tests/ctag_mount_main.c` under a distinct `--retail-ui-ce-lifecycle` mode, or create a new `tests/hcu_ce_map_lifecycle_main.c`. A new harness is cleaner because the existing main contains lots of parent-only fault modes and hand-authored cache structures.

Likely narrow stubs (exact set must be generated from the rooted link map, not guessed):

- CE heap/debug/assert/reporting (`debug_malloc/free`, match/assert/error, `csprintf`, string/memory wrappers), only where live.
- Texture/sound cache lifetime hooks and HUD/mod/menu tag observer callbacks invoked by `scenario_tags_load()`/`scenario_tags_unload()`; their stubs should record call order, not invent tag data.
- Tag vertex/index registration and deregistration callbacks. For PS2 these are expected machine hooks/no-ops, but the fixture must count balanced register/unregister and ensure deregistration occurs before CTAG owner release.
- `tag_validate_tags` and structure-BSP validator: preferably link real CE port validators with a bound claims buffer. If host ILP32 execution cannot supply these, isolate and name the validation stub explicitly; pre-run the Python audited-asset parser and report that this fixture then proves loader/lifecycle, not schema validation.
- Scenario/tag access seam: the smallest uncertain portion is resolving the actual UI scenario tag and its BSP reference. Prefer actual `scenario_definition_get()` / `TAG_BLOCK_GET_ELEMENT` over fake success. If necessary, provide a read-only adapter over actual tag-instance records to return the UI scenario and selected BSP reference; assert that all resolved addresses/datum indices lie within the mounted tag image, and label precisely which CE accessors remain stubbed.
- `bink_playback_active()` must return false; any `wind_dispose_from_old_map()` and time/collision presentation calls pulled by real BSP switch must be bounded and counted.

Avoid broad zero-stub generation here: the point is an ownership contract test. Every return-valued stub in the rooted closure should have a reason and a test assertion proving the sequence does not depend on fabricated success. Emit the linker map and undefined-symbol list as artifacts.

## Main pitfalls / acceptance boundaries

- `scenario_load()` is not just a wrapper for the tested BSP-switch function: it calls `scenario_tags_load()`, scenario and globals lookup, and only returns success after the first BSP switch. A fixture that starts by setting `global_scenario` and `global_tag_instances` still misses this gap.
- Parent preflight is deliberately before CE load/unload. The fixture must call the same preflight interface first; invoking map loader only after CE calls `cache_file_open()` changes lifecycle semantics and misses the preflight-before-unload constraint.
- Real `scenario_tags_load()` runs CE header checks, a synchronous `cache_file_read()` loop, schema validation, buffer registration, and tag-loaded callbacks. A test that only calls `cache_file_open()` and reads one tag is not equivalent.
- Real `scenario_unload()` first lets `scenario_tags_unload()` close CE consumers and invalidate tag pointers, then clears scenario globals, then asks the parent to release the mount. Parent release before these steps risks use-after-unmount and is specifically what the test must reject.
- The UI package has a real CE CTAG/BSP path but is not a gameplay map. It proves loader mechanics, cleanup ordering, and retry—not gameplay memory capacity, complete campaign resources, object simulation, or rendering.
- The service singleton (`s_service`) and cache adapter globals survive between cycles. Reuse the same service object and process; do not fork a fresh process per cycle, or stale-owner bugs are hidden.
- Map service currently has a non-UI capacity gate in `hcu_map_service_preflight()` (`src/stream/hcu_map_service.c:252`); use `ui` until the M2 capacity decision changes based on measured evidence.
- `scenario_unload()` asserts Bink is not playing and calls CE consumers; assert-only shortcuts must not remove the ordering under test.
- Host ILP32 layout/syntax checks are not R5900 execution. This fixture does not replace the current exact-ELF PCSX2 guest run, current production pin/hash, optical/OPL read tests, or the M2 gameplay-map qualification gate.

## Halo-64 comparison (reminders only)

Halo-64's [`port/n64/NOTES.md`](../../submodules/halo-64/port/n64/NOTES.md#L16) records that `scenario_switch_structure_bsp()` participates in every map load and that its time stop/start behavior interacts with the main loop. Its notes at `#L71-L75` also call out CE cache/BSP header expectations. These are useful reminders to preserve lifecycle ordering and required CE state when designing a harness; they are **not** authority to remove CE scenario/script/AI systems, alter the PS2 memory budget, or copy N64-specific cuts. The present fixture should link the actual CE lifecycle and PS2 cache bridge and test their ownership handoff.

## Suggested landing/verification sequence

1. First add only the composed success cycle and map/CE snapshots in a new fixture; keep existing tests unchanged.
2. Prove real `scenario_load()` + `scenario_unload()` with `nm`/link-map checks confirming those bodies and all target production files are present; assert audited asset hashes.
3. Add same-process second cycle and precise CE-unpublished-before-owner-release callback assertion.
4. Add one load-stage failure and successful retry; only then expand section-selective faults. Keep the already broad parent failure matrix in `test_retail_ui_ctag_mount.py` as the parent-seam evidence rather than duplicating every fault immediately.
5. Run `python3 -m pytest -q tests/test_hcu_scenario_bsp_switch.py tests/test_retail_ui_ctag_mount.py` and the focused validator/cache tests; run `git diff --check`. Preserve skips when audited binaries or ILP32 runtime are unavailable.
6. Update M2 Step 9 wording to state exactly: whether the test called real `scenario_load()` / `scenario_unload()`, whether cache/tag validators were real, the real package/map hashes, which callbacks were stubbed, and which failures/retries were exercised. Do not infer map-capacity or scene-render completion.

## Code citations

- Parent M2 service: [`hcu_map_service.c`](../../src/stream/hcu_map_service.c#L97), [preflight and current UI-only admission](../../src/stream/hcu_map_service.c#L230), [service shutdown](../../src/stream/hcu_map_service.c#L325).
- CE real load path: [`scenario_load()`](../../submodules/halo-ce-universal/source/scenario/scenario.c#L1230), [`scenario_unload()`](../../submodules/halo-ce-universal/source/scenario/scenario.c#L370), [`scenario_tags_load()`](../../submodules/halo-ce-universal/source/cache/cache_files.c#L1214), [`scenario_tags_unload()`](../../submodules/halo-ce-universal/source/cache/cache_files.c#L617).
- Cache adapter and ownership: [`ps2_cache_preflight_map()`](../../submodules/halo-ce-universal/port/ps2/src/ps2_cache.c#L179), [`ps2_cache_release_map_owner()`](../../submodules/halo-ce-universal/port/ps2/src/ps2_cache.c#L196), [`cache_file_open()`](../../submodules/halo-ce-universal/port/ps2/src/ps2_cache.c#L355), [`cache_file_read()`](../../submodules/halo-ce-universal/port/ps2/src/ps2_cache.c#L375).
- Existing retail asset fixture: [`test_retail_ui_ctag_mount.py`](../../tests/test_retail_ui_ctag_mount.py#L20), [service invocation/assertions](../../tests/test_retail_ui_ctag_mount.py#L55), [CE BSP fixture build](../../tests/test_hcu_scenario_bsp_switch.py#L105).
- Comparative Halo-64 notes: [`port/n64/NOTES.md`](../../submodules/halo-64/port/n64/NOTES.md#L16), BSP/cache expectations at [#L71](../../submodules/halo-64/port/n64/NOTES.md#L71).
