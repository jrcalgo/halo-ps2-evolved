# M2 CE scenario ingress + parent map-service audit

**Scope:** report-only review of the smallest next M2 Step 9 test that composes the real CE scenario lifecycle/global state with the parent HCU map service and FileXio/HP2 failure injection. No source or plan files were changed for this audit.

## Conclusion and priority

The strongest existing pieces are separate, not yet one end-to-end host test:

1. `tests/test_hcu_scenario_bsp_switch.py::test_retail_ctag_and_cbsp_flow_through_ce_transaction_and_ps2_cache` runs actual CE `scenario_switch_structure_bsp()` over retail `a30`/`a50` CTAG+CBSP data, including BSP rollback and retry, but starts from manually prepared cache/scenario globals and mounts through direct `ctag_mount_hp2_file_verified_discover_with_bsp_catalog()` calls. It does not link `hcu_map_service.c` or exercise CE `scenario_load()` / `scenario_unload()` ([test setup and source list](../../tests/test_hcu_scenario_bsp_switch.py#L75-L200), [fixture transaction](../../tests/hcu_scenario_bsp_switch_main.c#L609-L650), [manual scenario/BSP state](../../tests/hcu_scenario_bsp_switch_main.c#L720-L750)).
2. `tests/test_retail_ui_ctag_mount.py` runs the real HCU map service and PS2 cache against the retail UI HP2/MAP, injects deferred FileXio/HP2 and late CTAG-backend failures, verifies owner/source/cache rollback, and retries in the same process. It does not link CE scenario code or prove CE globals are unpublished/published around parent release/remount ([fixture invocation](../../tests/test_retail_ui_ctag_mount.py#L14-L80), [late mount failure and retry](../../tests/ctag_mount_main.c#L870-L920)).
3. The opt-in PCSX2 lifecycle profile composes actual CE UI scenario unload/reload with the parent owner and proves successful release/reload only. The plan records no guest failure injection or failed-scenario global-state check yet ([scenario unload ordering](../../submodules/halo-ce-universal/source/scenario/scenario.c#L370-L412), [M2 lifecycle status](../../plans/7.hcu-remake-m2-m4.md#L201-L205)).

**Recommended next test:** extend the existing ILP32 `hcu_scenario_bsp_switch` retail integration fixture (or add a sibling fixture with its CE/cache stubs) to initialize `hcu_map_service` for the retail UI package, then drive the real CE `scenario_load()` → `scenario_unload()` → failed deferred reload → corrected retry sequence. This is narrower than adding the whole `game_new_map` path, but closes the current evidence seam: actual CE `global_scenario`, `global_structure_bsp`, collision/BSP globals, and tag-instance pointers must transition atomically with the parent HP2 source and arena owner. Keep the product-side UI-only capacity gate unchanged; do not use this test to admit an unqualified gameplay map.

## Evidence and gaps

### CE owns scenario publication; the parent owns its backing bytes

`scenario_load()` calls `scenario_tags_load()`, publishes `global_scenario` only after it receives a datum, obtains game globals, and reports success only if BSP 0 switches successfully ([`scenario.c`](../../submodules/halo-ce-universal/source/scenario/scenario.c#L1230-L1252)). `scenario_unload()` first unloads tags and clears scenario/BSP/game-global pointers, then under `HALO_PS2` calls `ps2_cache_release_map_owner()` ([`scenario.c`](../../submodules/halo-ce-universal/source/scenario/scenario.c#L370-L412)). That ordering is the critical lifetime invariant for CTAG/CBSP-backed CE pointers.

The parent service registers map preflight/loader/unloader callbacks with the PS2 cache adapter. It preserves a same-map staged request during CE's preflight-before-unload transition; after owner release, `map_loader()` performs deferred validation and mounts the package, cleaning staged/source state if mount fails ([`hcu_map_service.c`](../../src/stream/hcu_map_service.c#L95-L172)). Preflight streams HMAP, CTAG, CRNG, and CBIX, validates map identity/catalog/resource extent/CTAG capacity/source hash, then releases temporary arena use; only `ui` is currently allowed because gameplay capacity is not qualified ([`hcu_map_service.c`](../../src/stream/hcu_map_service.c#L230-L323)).

### Existing CE BSP fixture is not scenario ingress

The ILP32 fixture links the real `scenario.c` and PS2 cache/CTAG/CBSP backend plus parent HP2/file/section code ([`test_hcu_scenario_bsp_switch.py`](../../tests/test_hcu_scenario_bsp_switch.py#L145-L181)). It verifies actual CE BSP switch behavior against retail map references and verifies caller-visible rollback when a candidate BSP read, port verifier, or schema validation fails ([`hcu_scenario_bsp_switch_main.c`](../../tests/hcu_scenario_bsp_switch_main.c#L750-L923)).

However, its package setup mounts CTAG directly with `ctag_mount_hp2_file_verified_discover_with_bsp_catalog()` and then manually seeds `global_tag_instances`, `global_scenario`, and scenario BSP references before invoking the switch. Its CRC and section faults therefore validate mount rollback and BSP transaction semantics, not CE `scenario_tags_load()` / `scenario_load()` ingress or `hcu_map_service` staging ([direct mount/fault/retry](../../tests/hcu_scenario_bsp_switch_main.c#L616-L650); [fixture entrypoint](../../tests/test_hcu_scenario_bsp_switch.py#L201-L227)).

### Existing map-service fixture is not CE global-state integration

The UI service host test links `hcu_map_service.c`, `ps2_cache.c`, actual FileXio-facing file/HP2/section readers and actual CTAG/CBSP code ([`test_retail_ui_ctag_mount.py`](../../tests/test_retail_ui_ctag_mount.py#L14-L48)). It tests a successful UI mount, source/section read faults, post-unload file corruption, each metadata/tag section corruption, and late PS2 CTAG backend capacity rejection followed by same-process recovery ([`ctag_mount_main.c`](../../tests/ctag_mount_main.c#L760-L920)). This currently invokes cache preflight/release/load directly; it does not call `scenario_load()` or observe CE global pointers. Thus it cannot yet prove there is no stale CE pointer when the parent unmounts or when a remount fails.

## Proposed smallest composed regression

Use the actual retail UI MAP/HP2 pair already required by the service fixture. It is the one catalog entry the production service currently accepts, so this avoids weakening product policy or selecting a gameplay map whose M2 capacity is explicitly unqualified ([`hcu_map_service_preflight`](../../src/stream/hcu_map_service.c#L242-L253)).

1. **Compose, do not reimplement, the owners.** Reuse the service fixture's FileXio counters/fault hooks, HCU service and PS2 cache adapter, plus the scenario-switch fixture's ILP32 prefix/shims and actual CE `scenario.c`/`cache_files.c`. Prefer a dedicated sibling test executable over broad edits to the already-large `ctag_mount_main.c` and `hcu_scenario_bsp_switch_main.c`.
2. **Bring up one real CE scenario.** Initialize CE cache/global state and `hcu_map_service`; invoke CE's normal scenario/map-entry path for `levels\\ui\\ui`. Assert successful `scenario_load()`, non-null `global_scenario` and `global_structure_bsp`, matching scenario/global BSP indices, a published validated tag table, active parent CTAG mount/source, and expected map-arena use. Use the UI fixture's actual package and source hashes, not a fabricated in-memory tag image.
3. **Begin a same-map reload through CE ordering.** Call the PS2 cache preflight for the same UI scenario while it is mounted; assert this only stages reload and leaves the current CE globals, owner bytes, descriptor, and cache publication intact. Call CE `scenario_unload()`; assert all CE scenario/BSP/collision/game-global pointers are cleared before/when `ps2_cache_release_map_owner()` returns, and parent mount/source/descriptor are released while reload intent remains staged.
4. **Inject one real parent read failure after old-owner release.** Arm the FileXio fake for a one-shot short read/EOF on the first deferred post-release HP2 section read (or source revalidation read). Invoke the actual CE map-load/scenario-load path again. Assert the scenario does not become published, all CE scenario/BSP/collision/game-global pointers remain null, cache map publication is false, `hcu_map_service` has no mount/source/open descriptor or staged/reload/preflight state, map and section-scratch arenas roll back to their pre-attempt marks, and FileXio opens equal closes. Check that the injected-fault witness proves the intended FileXio read boundary was reached rather than an earlier path rejection.
5. **Retry without process reset.** Disable the one-shot fault, run the same CE load path again, and assert successful `scenario_load()`, valid/non-stale globals and datum indices, live mount/source ownership, and FileXio descriptor accounting (one retained descriptor while mounted, balanced after final unload). Finally call CE `scenario_unload()` and verify globals are null, owner/scratch are empty, and descriptor counts balance.
6. **Keep assertions state-based.** Capture object identities and arena marks; compare before/after globals and cache bytes where applicable. Do not rely only on success log strings or callback return values. Record source/package SHA-256 and the exact test command in the report output.

### Acceptance for this focused increment

- The real CE `scenario_load()`/`scenario_unload()` code and HCU parent map-service callback path are present in the executable's link map (not merely textually referenced).
- The test witnesses the injected storage read fault after CE has unpublished the prior scenario and the parent has released its old owner.
- Failure leaves no published CE pointers, mounted cache, active source/descriptor, staged transaction, leaked arena bytes, or unbalanced FileXio handle.
- A valid retry in the same process publishes the scenario again and a final CE unload clears all pointers and parent ownership.
- Existing direct retail BSP switch tests remain unchanged and passing; this new case supplements, rather than replaces, their BSP rollback coverage.

This is host integration evidence, not PCSX2 or retail-PS2 device qualification. After it passes, mirror only the one-shot failed-remount/retry sequence in the existing opt-in PCSX2 lifecycle profile and run both interpreter and recompiler on the exact rebuilt ELF. Keep UI scenario-load status distinct from gameplay-map capacity and rendering gates.

## Comparative note

Halo-64's port notes explicitly call `scenario_switch_structure_bsp` a trap because it is reached on every map load and changes persistent/global invariants ([`NOTES.md`](../../submodules/halo-64/port/n64/NOTES.md#L16-L28)). That is useful as a reminder to test lifecycle side effects and pointer lifetime, not as a reason to copy N64's reduced game scope or scheduling cuts. This port must retain CE scenario/BSP semantics and its PS2-constrained owner/reader transaction; the parent/HCU split in this test is the behavior being validated.

## Open question to resolve while implementing

`hcu_map_service` currently insists on one process-global service pointer (`s_service`) and production callback registration; the test should exercise the real registration route rather than bypassing it. Also confirm the actual CE call sequence used by the test around `cache_files_precache_map_begin()` so the injected error happens inside deferred validation/mount and `scenario_load()` observes it as failure. If CE's first UI load uses a menu-specific wrapper rather than a direct scenario call, preserve that wrapper in the fixture or clearly identify the test seam; do not silently substitute a direct cache callback and label it an end-to-end CE scenario test.
