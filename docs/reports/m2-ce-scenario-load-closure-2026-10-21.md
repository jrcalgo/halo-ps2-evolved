# M2 Step 9: composed CE scenario-load fixture closure

Date: 2026-10-21  
Scope: report-only investigation of the smallest credible host ILP32 fixture that composes the real CE scenario lifecycle with the production parent `hcu_map_service` and the audited UI package. No source or plan files were changed.

## Summary

The existing fixtures cover complementary halves, but no current test calls real `scenario_load()` and `scenario_unload()` while the real parent service owns the map. The least ambiguous next step is a new `tests/test_hcu_ce_map_lifecycle.py` plus `tests/hcu_ce_map_lifecycle_main.c`, reusing the audited UI asset contract and the parent's real service sources. Compile the CE `cache_files.c` into the harness translation unit (as the existing BSP test does), compile CE `scenario.c`, and add roots for `scenario_load` and `scenario_unload`. Do not root `game_load()` unless a separate need justifies the broader game-global startup closure.

Two important path corrections:

1. `ps2_cache_preflight_map("ui")` stages validation but does not mount a cache. `cache_files_give_time_to_precache("levels\\ui\\ui")` is the CE-owned API that eventually calls `cache_files_precache_map_begin()`, which calls the registered `hcu_map_service` loader. Only then can real `scenario_load()` reach `cache_file_open()` successfully.
2. On same-map reload, preflight while the old map is mounted sets `reload_pending`; real `scenario_unload()` clears CE publications and releases the owner; a subsequent `cache_files_give_time_to_precache()` invokes the deferred loader, which reruns full source/package validation after owner release. This preserves the production order and exercises the intended service state machine.

## Existing evidence and missing composition

- The CE/BSP harness already compiles real `scenario.c` and, in retail mode, includes real `cache_files.c`; it roots only `scenario_switch_structure_bsp`, manually seeds tag/scenario/BSP state, and links the real PS2 cache and CBSP path. See the compile command and roots in [`test_hcu_scenario_bsp_switch.py`](../../tests/test_hcu_scenario_bsp_switch.py#L145) and the harness's direct entry point in [`hcu_scenario_bsp_switch_main.c`](../../tests/hcu_scenario_bsp_switch_main.c#L923).
- The UI service harness already compiles the real parent `hcu_map_service`, HP2/file/section readers, CTAG/CBSP mount and cache bridge, and runs against `ui.hp2` plus decompressed `ui.map`; it does not compile CE `scenario.c` or `cache_files.c`. See [`test_retail_ui_ctag_mount.py`](../../tests/test_retail_ui_ctag_mount.py#L22) and its temporary asset-root setup at [#L53](../../tests/test_retail_ui_ctag_mount.py#L53).
- The M2 lifecycle design report independently identifies this composition gap and recommends real CE load/unload roots: [`m2-ce-lifecycle-fixture-design-2026-10-21.md`](m2-ce-lifecycle-fixture-design-2026-10-21.md).

## Real call path and lifecycle ordering

### First load

1. Initialize the FileXio host fake and `mem_layout_v2_t`; create streaming and frame-scratch arenas; call real `hcu_map_service_init()` with a temporary root containing the audited `maps/ui.hp2` and `maps/ui.map`. This is the setup pattern in [`ctag_mount_main.c`](../../tests/ctag_mount_main.c#L606) and the service integration test.
2. Call `ps2_cache_preflight_map("levels\\ui\\ui")`. The adapter forwards to the parent callback ([`ps2_cache.c`](../../submodules/halo-ce-universal/port/ps2/src/ps2_cache.c#L179)); the parent validates HMAP/CTAG/CRNG/CBIX and source hash, stages the entry, then releases temporary arena usage ([`hcu_map_service.c`](../../src/stream/hcu_map_service.c#L230)). This step must leave the mount unpublished.
3. Call real `cache_files_give_time_to_precache("levels\\ui\\ui")`. Since the map is not mounted, CE reaches `cache_files_precache_map_begin()` ([`cache_files.c`](../../submodules/halo-ce-universal/source/cache/cache_files.c#L1164)), and the PS2 cache adapter calls the service's registered loader ([`ps2_cache.c`](../../submodules/halo-ce-universal/port/ps2/src/ps2_cache.c#L331)). This mounts CTAG and registers the BSP callback through the real CTAG backend.
4. Call real `scenario_load("levels\\ui\\ui")`. It invokes `scenario_tags_load()`, resolves the scenario and globals from the just-loaded tag table, and commits BSP zero through CE's `scenario_switch_structure_bsp()` ([`scenario.c`](../../submodules/halo-ce-universal/source/scenario/scenario.c#L1230)). Do not replace those accessors with a fabricated scenario result: use the retail UI package's actual scenario tag, global tag and first BSP reference.
5. `scenario_tags_load()` calls the real PS2 `cache_file_open()`, verifies the cache header, materializes CTAG into the bound tag-cache span, runs cache-tag and schema validation, publishes the tag table and calls cache-observer hooks ([`cache_files.c`](../../submodules/halo-ce-universal/source/cache/cache_files.c#L1214)). Its `cache_file_read()` call is synchronous for this adapter; no test thread should simulate an asynchronous completion.

### Same-map unload and deferred reload

1. While the first UI mount and CE scenario are live, call `ps2_cache_preflight_map("levels\\ui\\ui")`. The service must take its same-map branch and set `reload_pending` without changing the live owner or reopening the source ([`hcu_map_service.c`](../../src/stream/hcu_map_service.c#L254)).
2. Call real `scenario_unload()`. CE closes its cache-side consumers and clears tag-table, scenario, BSP, collision, and game-global publications before calling `ps2_cache_release_map_owner()` ([`scenario.c`](../../submodules/halo-ce-universal/source/scenario/scenario.c#L370)); `scenario_tags_unload()`'s ordered cleanup is at [`cache_files.c`](../../submodules/halo-ce-universal/source/cache/cache_files.c#L617). The fixture should instrument the owner-release seam and assert CE globals are already null/`NONE`, `tags_loaded` is false, tag table/count are empty, and deregistration has happened before the parent arena is released.
3. The parent unloader releases `ctag_mount` and its source but preserves the staged same-map identity because `reload_pending` was set ([`hcu_map_service.c`](../../src/stream/hcu_map_service.c#L158)).
4. Call `cache_files_give_time_to_precache()` again. The CE cache is no longer mounted, so `cache_files_precache_map_begin()` invokes the parent loader. Since `reload_pending` is set but no longer owns an active source/mount, `map_loader()` repeats `hcu_map_service_preflight()` before remount ([`hcu_map_service.c`](../../src/stream/hcu_map_service.c#L95)).
5. Call real `scenario_load()` again, assert the same CE publications are valid, then `scenario_unload()` again. Run both cycles in one process with the same service object and adapter singleton so stale callback state, descriptors, or tag globals cannot be hidden by process reset.

## Minimal candidate build closure

Use the current ILP32 host flags, prefix, generated MSVC-semantics header, and function/data section GC already used by the retail BSP test. Keep the existing `-fshort-wchar`, `-fcommon`, `-fwrapv`, `-fno-strict-aliasing`, and null-pointer-check behavior. A tentative test-mode define such as `HALO_HCU_CE_MAP_LIFECYCLE=1` is useful for observation hooks, but avoid production-code conditional behavior if the harness can wrap callback boundaries instead.

### CE sources and roots

- Harness should include `source/cache/cache_files.c` directly, matching the existing fixture's inclusion at [`hcu_scenario_bsp_switch_main.c`](../../tests/hcu_scenario_bsp_switch_main.c#L1). It needs access to the real cache globals and avoids trying to link the retail console cache implementation separately.
- Compile `source/scenario/scenario.c`; root `scenario_load` and `scenario_unload` with `-Wl,-u,scenario_load -Wl,-u,scenario_unload`. Keep `-ffunction-sections -fdata-sections -Wl,--gc-sections` so unrelated scenario routines do not become the build boundary.
- Prefer the real `port/linux/game/tag_validate.c` under the existing PS2 host adaptation (the BSP fixture already demonstrates compiling it into the harness and supplying schema tables). Include all schema units required by `tag_validate_tags`, beginning with the same seven currently used in the BSP integration: `tag_schema_groups.c`, `tag_schema_collision.c`, `tag_schema_models.c`, `tag_schema_objects.c`, `tag_schema_render.c`, `tag_schema_effects.c`, and `tag_schema_scenario.c`.
- Use the real CE tag lookup/access macros over the mounted UI tag image. The scenario/game-globals helpers are macros around `tag_get`, not independent implementations; check [`scenario_definitions.h`](../../submodules/halo-ce-universal/source/scenario/scenario_definitions.h#L63) and [`game_globals.h`](../../submodules/halo-ce-universal/source/game/game_globals.h#L62). The real `tag_loaded()` implementation is in `cache_files.c`.

### Parent and PS2 sources

Reuse the exact real source list from [`test_retail_ui_ctag_mount.py`](../../tests/test_retail_ui_ctag_mount.py#L32):

```text
src/stream/hcu_map_service.c
src/stream/hcu_map_catalog.c
src/stream/ctag_mount.c
src/stream/ctag_ps2_backend.c
src/stream/cbsp_catalog.c
src/stream/ctag_resource_index.c
src/stream/ctag_map_source.c
src/stream/sha256.c
src/stream/hmap.c
submodules/halo-ps2/engine/src/world/section.c
submodules/halo-ps2/engine/src/stream/hp2.c
submodules/halo-ps2/engine/src/stream/file.c
submodules/halo-ps2/engine/src/core/mem.c
submodules/halo-ce-universal/port/ps2/src/ps2_cache.c
submodules/halo-ce-universal/port/ps2/src/ps2_ctag.c
submodules/halo-ce-universal/port/ps2/src/ps2_cbsp.c
```

The source list above is sufficient for real service, file source, HP2 section loads, CTAG/CBSP materialization, and cache ownership. The composed UI lifecycle adds CE scenario/cache code and real tag validation to the existing UI parent test. Register BSP loader through the actual CTAG mount backend, not a manually mounted CBSP fixture.

### Likely bounded test doubles

First attempt a real-source link and use the retained link map plus `nm -u` to derive the exact unresolved closure. Expected narrow test-only implementations are:

- host CE diagnostics/assertions/string support and fixed physical-memory tag/BSP-cache addresses;
- map-independent CE cache observers invoked by `scenario_tags_load()`/`scenario_tags_unload()` (`sound_cache_*`, `texture_cache_*`, HUD/menu/mod/pal/powerup hooks) and tag vertex/index registration hooks. Count and order these; do not fake tag/scenario/BSP data;
- scenario-switch reconnect/disconnect services that the existing BSP fixture already bounds and counts (e.g., object/AI/effect/player reconnection callbacks), plus `bink_playback_active() == FALSE` and bounded wind/time/collision hooks if rooted;
- `tag_validate_report()` and the tag-claims arena callback if the real validator requires them. Prefer real schema validation; if any validator is stubbed, state it explicitly and rely on a separately passing validator test for schema semantics.

Avoid linking full `game.c`, `game_initialize_for_new_map()`, renderer, AI or sound runtime just to test this boundary. The requested lifecycle is real `scenario_load()` / `scenario_unload()` and map service, not full playable gameplay. `scenario_load()`'s retained code should access the actual UI scenario/BSP record and return false if the real CE data path cannot establish the map.

## Fault after unload and retry

The existing service-only test corrupts the backing `.map` after owner release, observes deferred reload rejection with empty arenas/closed descriptors, restores exact bytes, and passes a fresh retry in [`ctag_mount_main.c`](../../tests/ctag_mount_main.c#L735). A stronger one-shot transport fault can use the FileXio fake's existing short-read injection instead of file mutation:

1. Successfully load and unload once. Before unloading, request same-map preflight so `reload_pending` survives the owner release.
2. Arm a one-shot EOF on the first post-release source read used by deferred `hcu_map_service_preflight()`/HP2 section or source-hash validation. It must return a genuine partial read followed by EOF, then disarm itself; reuse the existing fake FileXio state/counters from the UI test harness rather than altering the mounted CE tag bytes.
3. Call real `cache_files_give_time_to_precache()` for the requested UI map. It should fail to mount deterministically; assert `scenario_load()` is not called / remains false, `reload_pending` and staged fields are cleared by the failed deferred loader, source descriptor is closed, map and scratch arenas return to baseline, mount/cache query is false, and CE scenario/tag globals remain unpublished.
4. Call `ps2_cache_preflight_map()` again, then `cache_files_give_time_to_precache()`, then real `scenario_load()`. Assert the retry obtains the expected owner high-water and tag/BSP publications; finish with real `scenario_unload()` and verify a second clean release.

This is a post-unload *prepublication reload-read* fault. Separately, a fault inside `scenario_tags_load()`'s CTAG materialization/tag validation is a distinct load-failure branch: a failed `scenario_load()` may leave CE consumers opened or partial cache globals, so only add it after defining and testing the correct CE failure cleanup path. Do not label the service preflight fault as proof of a CE tag-cache short-read rollback.

## Assertions and artifacts

The CE snapshot should capture at minimum:

- return values of `scenario_load()`; `global_scenario_index`, `global_scenario`, `global_structure_bsp_index`, `scenario_globals->structure_bsp_index`, `global_structure_bsp`, `global_collision_bsp`, `global_bsp3d`, and `global_game_globals`;
- `cache_file_globals.tags_loaded`, `tag_header`, `header`, `global_tag_instances`, `global_tag_count`, cache-open state where observable, and tag-cache/BSP-cache hash and canaries;
- parent `service.mount.active`, `service.source.active`, descriptor, staged map/entry, `preflight_ready`, `reload_pending`, arena used/high-water and cache adapter `cache_files_precache_map_loaded("ui")`;
- event order for `scenario_tags_unload` observers, cache close, buffer deregistration, CE global unpublication, parent owner release, and next loader call;
- balanced source open/close descriptors and stable high-water across two successful cycles and the failed-reload/retry cycle.

Retain the linker map and unresolved-symbol output as build artifacts. Assert that `scenario_load`, `scenario_unload`, `scenario_tags_load`, `scenario_tags_unload`, `cache_files_give_time_to_precache`, `hcu_map_service_preflight`, `map_loader`, and the production parent file/mount path are live in the map. Record source pins and UI package/map SHA256 as the current test already does. The parent-only service test remains valuable; this composed fixture supplements rather than replaces it.

## Halo-64 as comparative context

Use Halo-64's [`port/n64/NOTES.md`](../../submodules/halo-64/port/n64/NOTES.md#L16) only as a warning to preserve CE scenario/BSP lifecycle and time-state effects. It is not a basis for removing CE scenario/tag logic or adopting N64 memory/performance cuts. The composed fixture should exercise the actual CE and PS2-parent owners described above.

## Exit boundary

Passing this fixture would close one important M2 Step 9 gap: host ILP32 proof that real CE scenario/tag load and unload compose with the real HCU/PS2 UI owner, including same-process deferred reload and transport-failure retry. It would not establish R5900 execution, gameplay map fit, OPL/optical mounted-volume qualification, or a rendered scene. M2/M3/M4 remain governed by their own plan gates.
