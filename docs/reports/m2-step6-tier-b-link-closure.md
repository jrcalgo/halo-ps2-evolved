# M2 Step 6 Tier B — Minimum real CE cache / PS2 adapter closure

**Scope:** report-only feasibility assessment using the current Tier A files. No tests, production sources, plans, or build files were edited. Tier A is a real execution of `scenario_switch_structure_bsp()` but deliberately replaces its BSP load/unload, tag lookup, and verification leaves with fixture functions. This report identifies the minimum next closure needed to execute the real CE `scenario_structure_bsp_load()` / `_unload()` with the HCU PS2 cache/CBSP adapter against a package-derived scenario containing at least two BSP references.

## Recommendation: one package-backed fixture, with a narrow cache-state initializer

Tier B is feasible in the existing ILP32 harness. Keep the real `scenario.c` switch body and add the real `cache_files.c` load/unload/tag lookup functions, `port/ps2/src/ps2_cache.c`, CTAG/CBSP materializers, and the existing parent `ctag_mount` callback path. Do not clone or rewrite the transaction.

The smallest blocker is not BSP-read wiring; it is CE cache-tag lifecycle state. `cache_file_open()` fills the CE cache header from the PS2 mounted image, but the `cache_file_globals.tags_loaded` bit, `tag_header`, `global_tag_instances`, and tag count are normally published by the much larger `scenario_tags_load()` path. `cache_files_set_tag_instances()` publishes only the external table pointer/count; it does not set the private `tags_loaded` state ([`cache_files.c:659-672`](../../submodules/halo-ce-universal/source/cache/cache_files.c#L659)). The switch/load/unload tests need a narrow, explicit fixture initializer for that private state. Best choices, in order:

1. For this host-only test, compile the exact `cache_files.c` source into a test wrapper translation unit that exposes a fixture-only function after the included source. The helper sets `cache_file_globals.tag_header`, `.tags_loaded`, `global_tag_instances`, and the private count from the already materialized CTAG tag header. This keeps the source body unmodified and lets the test access the real `static` state; it is a test harness technique, not a runtime API.
2. If source inclusion is rejected by local coding conventions, add a narrowly scoped `#if defined(HALO_PS2_M2_BSP_TRANSACTION_TEST)` helper in `cache_files.c` and compile only this host test with that define. Make the helper accept a validated in-image tag-header pointer and use the real layout. It must not be present/callable in the production image.
3. Avoid calling full `scenario_tags_load()` initially. It correctly publishes this state, but also enters schema validation, registration, menu/pal tags, sound/texture callbacks, and more startup flow than the BSP transaction fixture needs. Add it later only if Step 6 specifically expands to map-load integration.

The initializer must derive the table from the package CTAG materialized at the actual tag-cache base, not point at a separately synthesized array. The map/package reader has already validated CTAG bounds and relocations before CE is permitted to use this path. This provides real scenario references and tag instances while keeping the test focused on BSP switching.

## Current Tier A baseline and delta

[`tests/test_hcu_scenario_bsp_switch.py:15-68`](../../tests/test_hcu_scenario_bsp_switch.py#L15) compiles real `source/scenario/scenario.c` with host `-m32`, `-fshort-wchar`, HCU's prefix and generated MSVC semantics, then roots `scenario_switch_structure_bsp` with `--gc-sections`. The real source switch body is reached. [`tests/hcu_scenario_bsp_switch_main.c:55-78`](../../tests/hcu_scenario_bsp_switch_main.c#L55) currently supplies fake `scenario_structure_bsp_load`, `_unload`, and `structure_bsp_port_verify`; its `tag_get` returns one of two local records rather than CE cache tag data ([`main.c:48-53`](../../tests/hcu_scenario_bsp_switch_main.c#L48)). Its fixture scenario/references, globals, and branch assertions are useful and can be retained ([`main.c:123-163,165-223`](../../tests/hcu_scenario_bsp_switch_main.c#L123)).

For Tier B:

- Remove the fake load/unload/tag lookup. Allow `source/cache/cache_files.c` to provide `scenario_structure_bsp_load()`, `_unload()`, `tag_get()`, `cache_get_tag_instance()`, and the reference/header range helpers.
- Replace fake scenario/reference/BSP structs with pointers into an actual host-materialized CTAG image. Keep test-controlled counters only for platform edges and bounded validators.
- Keep `structure_bsp_port_verify()` real. Its implementation is compact and purely bounds/count based: it checks collision/cluster presence and count limits plus cluster-PVS and sound-cluster data sizes ([`structure_bsp_definitions.c:26-43`](../../submodules/halo-ce-universal/source/structures/structure_bsp_definitions.c#L26)).
- Add the actual parent section-selection callback so a requested retail `(file_offset,file_size)` resolves through the package CBIX to its CBSP HP2 section, then through `ps2_cache` to the fixed BSP destination. It does not need to involve FileXio or the HCU map-service singleton: a host fixture can read the exact audited `.hp2` file into its test context, open it with production `hp2_open()`, and implement `ctag_section_load_fn` by `hp2_find()` + `hp2_load()` into the callback's arena. Supply a non-null bounded `ctag_read_at_fn` that fails resource reads (none should be needed for the BSP transaction). This keeps the real parent CTAG/CRNG/CBIX/CBSP owner path while avoiding unrelated DVD/IOP services.

## Exact production path to retain

The real CE transaction consists of these stages:

1. `scenario_switch_structure_bsp()` validates the target index, disconnects old BSP procedures, calls real `scenario_structure_bsp_unload()` if one is active, calls real `scenario_structure_bsp_load()`, verifies through `structure_bsp_port_verify()`, and only then publishes new global pointers/index. On failure it clears pointers and reloads/re-verifies the old reference before publishing it again ([`scenario.c:1101-1191`](../../submodules/halo-ce-universal/source/scenario/scenario.c#L1101)).
2. Real `scenario_structure_bsp_load()` checks the map header and scenario reference bounds, rounds and checks the read extent against the bound structure-BSP region, and replaces the Xbox virtual `base_address` with the fixed PS2 BSP-cache base ([`cache_files.c:1401-1405,483-532`](../../submodules/halo-ce-universal/source/cache/cache_files.c#L1401)).
3. It fills the destination, calls `cache_file_read(NONE, file_offset, file_size, base_address, &complete, TRUE)`, and validates the loaded BSP cache header signature, its base pointer, and vertex/index ranges before calling `tag_validate_structure_bsp()` ([`cache_files.c:1408-1485`](../../submodules/halo-ce-universal/source/cache/cache_files.c#L1408)).
4. On success CE stores the header pointer, registers BSP vertex buffers, checks the actual tag instance's group/unloaded state, and publishes the BSP header base through that tag instance ([`cache_files.c:1492-1509`](../../submodules/halo-ce-universal/source/cache/cache_files.c#L1492)). On unload, it deregisters, verifies the cache tag instance, clears its `base_address`, and clears the cached BSP header ([`cache_files.c:1512-1534`](../../submodules/halo-ce-universal/source/cache/cache_files.c#L1512)).
5. The PS2 `cache_file_read()` recognizes a BSP request only when it is directed at the physical BSP-cache base, obtains the exact extent's CBSP view through the registered loader, materializes into that same base while resolving pointers against the mounted CTAG base, and sets completion only on success ([`ps2_cache.c:358-418`](../../submodules/halo-ce-universal/port/ps2/src/ps2_cache.c#L358)). `ctag_mount` resolves the exact CBIX extent, prevents overlap with tag/resource extents, loads the package section into its bounded BSP scratch owner, and registers/unregisters the adapter lease ([`ctag_mount.c:67-104`](../../src/stream/ctag_mount.c#L67)).

This is the right minimum to validate: real CE transaction and cache publication, actual PS2 materialization, and the actual package catalog/section selection. Drawing/GS, game load, and the full cache tag-load path remain outside this test's boundary.

## Exact state needed before calling the real BSP loader

### 1. Mounted cache header

Call real PS2 `cache_file_open(scenario_name, &header)` after mounting the selected package through `ctag_mount` + `ctag_ps2_backend`. It initializes the CE header fields (signature/footer/version/tag data offset/size/file length/name/build) and marks the PS2 cache source open ([`ps2_cache.c:338-355`](../../submodules/halo-ce-universal/port/ps2/src/ps2_cache.c#L338)). `cache_files.c` copies that header into its private `cache_file_globals.header` through this output parameter in normal CE startup. No test setter should synthesize file length/offsets; those must come from this real opened package/header.

### 2. Relocated package CTAG and CE tag table

Call real `cache_file_read(NONE, tag_data_offset, tag_data_size, tag_cache_base, ...)` so `ps2_ctag_materialize()` writes the map's real relocated image into the fixed tag cache. The `scenario_structure_bsp_reference` records use a 32-byte 32-bit ABI layout (`file_offset`, `file_size`, transient `base_address`, pad, tag reference) ([`scenario_definitions.h:147-157`](../../submodules/halo-ce-universal/source/scenario/scenario_definitions.h#L147)).

Then use the CTAG image's `cache_file_tag_header` and `tag_instances` pointer, not a test array. CE's private cache state must indicate tags loaded, and the instance table/count must match the actual tag header. The production path sets those fields in `scenario_tags_load()` after header/schema checks and assigns `global_tag_instances`, `global_tag_count`, and `tags_loaded = TRUE` ([`cache_files.c:1286-1329`](../../submodules/halo-ce-universal/source/cache/cache_files.c#L1286)). The public setter is intentionally insufficient because it only sets pointer/count ([`cache_files.c:666-672`](../../submodules/halo-ce-universal/source/cache/cache_files.c#L666)).

The initial active BSP must be loaded using the real `scenario_structure_bsp_load()` before seeding `global_structure_bsp_index=0` and `scenario_globals->structure_bsp_index=0`. The actual `tag_instance.base_address` and `cache_file_globals.structure_bsp_header` then represent the loaded initial BSP, as would be true immediately after CE `scenario_load()`. Do not seed only the CE indices or call `scenario_switch_structure_bsp(0)`—that guard is a no-op and does not prepare cache ownership.

### 3. BSP cache header offsets and bounds

The 32-bit CE `cache_file_structure_bsp_header` layout is 24 bytes: `base_address` at `+0`, vertex-buffer count/pointer at `+4/+8`, index-buffer count/pointer at `+12/+16`, and signature at `+20` ([`cache_files.c:187-195`](../../submodules/halo-ce-universal/source/cache/cache_files.c#L187)). A minimal fixture CBSP must materialize an image at least this large. For a low-complexity header fixture, counts may be zero (then range checks permit null arrays); `base_address` must resolve wholly inside the BSP output extent and signature must match the PS2 CE header constant. If using real retail CBSPs, verify these pointers and counts against the decoded image and preserve the relocated values. The cache loader also checks the reference is sector-roundable within capacity; `CACHE_FILE_SECTOR_SIZE` is 512, and the parent sets the reference destination only after checking the rounded read fits ([`cache_files.c:148-151,517-532`](../../submodules/halo-ce-universal/source/cache/cache_files.c#L148)).

The actual PS2 adapter requires exact CBIX source extent matching, and CBSP v1 currently requires `source_file_size == image_size` ([`ps2_cache.c:219-247`](../../submodules/halo-ce-universal/port/ps2/src/ps2_cache.c#L219)). The fixture must use source metadata from the package's CBIX record, not a rounded sector size. CE's validation uses the record's byte extent; sector rounding is only a containment check.

### 4. BSP tag datum, actual tag-instance lookup, and publication

`scenario_switch_structure_bsp()` obtains each real scenario reference from `global_scenario->structure_bsp_references`; `structure_bsp_definition_get()` uses `tag_get(STRUCTURE_BSP_TAG, datum)`. In cache source, `tag_get()` uses the real `cache_get_tag_instance()`, which requires `tags_loaded`, a non-null actual table, datum/index match, and a `STRUCTURE_BSP_TAG` group. Successful load changes the tag instance's `base_address` from null to `cache_file_globals.structure_bsp_header->base_address`, making `tag_get()` return the actual materialized `struct structure_bsp`. Unload clears it before the same destination may be overwritten ([`cache_files.c:275-315,1492-1534`](../../submodules/halo-ce-universal/source/cache/cache_files.c#L275)).

For a switch fixture, use two distinct, actual scenario references and two different BSP datums. Setup can call real `scenario_switch_structure_bsp(0)` with both CE indexes at `NONE` to reproduce CE's first-BSP path, then switch to BSP 1. On success assert tag 0's base is null and tag 1's base points into the fixed BSP span; on candidate failure with rollback assert tag 0 points to the *re-materialized* old BSP base and tag 1 is null. Pointer equality alone cannot distinguish old bytes from overwritten candidate bytes because the destination is intentionally stable; also compare bytes or a validated identifying field of the rematerialized old BSP and verify the source callback selected the old CBIX section on rollback.

### 5. Validator and vertex-buffer registration leaves

- `tag_validate_structure_bsp()` is called by real CE load after cache-header bounds checks ([`cache_files.c:1477-1485`](../../submodules/halo-ce-universal/source/cache/cache_files.c#L1477)). For the first Tier B increment, use an explicit controllable validator shim so fault injection can distinguish “schema accepted” from “schema rejected” without dragging all schema registries and claims-scratch code into this transaction closure. A true production-validator integration can be a follow-on; do not describe shimmed Tier B as schema-validation proof.
- `structure_bsp_port_verify()` is easy to keep real: it is a small function in `source/structures/structure_bsp_definitions.c` and reads the loaded tag's cluster, surface, collision, PVS, and sound-data metadata ([`structure_bsp_definitions.c:26-43`](../../submodules/halo-ce-universal/source/structures/structure_bsp_definitions.c#L26)). It must receive `tag_get()`'s real structure pointer, not a side fixture.
- `structure_bsp_header_register_vertex_buffers()` and `_deregister_vertex_buffers()` are intentionally empty in the PS2 sound/cache backend ([`ps2_sound_cache.c:238-248`](../../submodules/halo-ce-universal/port/ps2/src/ps2_sound_cache.c#L238)). To verify lifecycle calls, supply instrumented test shims recording the exact header pointer and balancing registration/deregistration rather than treating the production no-op as an observable registry. Do not invent GS buffer registration as part of this CE test.
- `cache_get_tag_instance()` uses CE `match_assert`/`match_vassert` paths. Supply assertion shims that fail the test immediately, plus any diagnostic formatter dependency reached on failed assertions. For valid fixtures those failure-only paths should not run.

## Package-backed two-BSP candidate

The durable current Step 5 package audit identifies `a30` as the smallest early campaign candidate with two BSPs: 2 BSPs, package SHA-256 `ce38764fbba687bb26d4f2eb8a6cf066e19e4b8b81521d6f70f23ce8d00f183d`, source map SHA-256 `287959f34a7379a1dbec5fec15b4d94d17fe97ccd861f5c0c8fc80148b7ed293` ([`retail-cbsp-catalog-package-audit-e4a97218.json:15-21`](retail-cbsp-catalog-package-audit-e4a97218.json#L15)). It is a good *host transaction input* because the real tag scenario should expose two references; this does not mean a30 fits any EE region or is a guest-approved map. The package audit overall reports 24 maps / 82 CBSP entries and explicitly disclaims memory fit or runtime-load acceptance ([same report, lines 1-9](retail-cbsp-catalog-package-audit-e4a97218.json#L1)).

Use the same audit manifest/package root already accepted by `tests/test_hcu_map_catalog.py` rather than checking in a duplicate payload or hard-coded new extents. The fixture should extract from the package at runtime:

- package SHA and map source SHA;
- CTAG and CRNG extents/identities;
- `scenario_tag_index`, actual scenario name/path, and the ordered `structure_bsp_references` block;
- each datum/tag group and each reference's exact `file_offset`/`file_size`;
- matching CBIX row, B000/B001 section identity, and CBSP payload hash.

For host-only test buffers, provision generous but explicit tag-cache, BSP-cache, map-section, section-scratch and validator-scratch spans; report actual high-water, but make no production-capacity inference. Respect disjointness and stable addresses because CE saves materialized pointers in tag instances.

## Smallest implementable next slice and files

Extend the current Tier A test instead of creating another parallel state-machine test:

1. **New `tests/hcu_scenario_bsp_switch_tier_b_fixture.c` (or wrapper TU):** include/compile the actual `cache_files.c` and expose only a fixture helper for the private `cache_file_globals` state. Prefer the wrapper technique to changing HCU production sources. It should initialize `tag_header`, `tags_loaded`, global table pointer/count from the real materialized CTAG image and expose read-only snapshots of `structure_bsp_header`/tag state for assertions if needed.
2. **Extend `tests/hcu_scenario_bsp_switch_main.c`:** replace synthetic scenario/references/structures with actual CTAG-backed pointers; call real `cache_file_open`, actual CTAG read/materialization, the fixture state initializer, and real first-BSP load before setting initial CE globals. Invoke actual scenario switch and validate cache/tag pointer transitions and identity-specific materialized bytes.
3. **Extend `tests/test_hcu_scenario_bsp_switch.py`:** add `cache_files.c`, `ps2_cache.c`, `ps2_ctag.c`, `ps2_cbsp.c`, parent `ctag_mount.c`, `ctag_ps2_backend.c`, `cbsp_catalog.c`, and halo-ps2 `hp2.c` plus any arena implementation required by the harness; add actual `structure_bsp_definitions.c`. Read the audited a30 package into test context and make the `ctag_section_load_fn` use production `hp2_open()`/`hp2_find()`/`hp2_load()` against it. Keep host ILP32 and `--gc-sections`; write a link map and assert the exact production symbols are retained (switch, CE BSP load/unload/tag_get, adapter read/mount, CBSP open/materialize, parent extent loader, HP2 decode, real port verifier). Use the Step 5 manifest/environment and skip with an explicit reason only if the licensed package corpus is absent.
4. **Validator shims:** `tag_validate_structure_bsp` should be a fail-mask shim for this first Tier B test, while the separate current validator host test remains authoritative for validator contracts. Add a later optional tier using real tag schema/claims sources; do not make a mocked validator appear production-integrated.
5. **Instrumented PS2 render-resource leaves:** register/deregister shims record pointer/call order and must balance across success, candidate verification failure, rollback, rollback failure, and map unload. Timer/collision/error/menu/BSP procedure calls can reuse Tier A counters. Ensure the actual procedure callbacks remain connected/disconnected in proper order.

This is the smallest slice that executes the real CE scenario transaction, cache loader/unloader and tag publication, actual adapter materialization, actual parent section selection, and actual structure capacity verifier while isolating schema validation and PS2 hardware-only registration as explicit leaves.

## Remaining limits after Tier B host pass

- It still does not run full `scenario_tags_load()` and therefore does not prove the end-to-end map-open/tag-header/schema publication transaction; that belongs to M2 Step 9.
- If `tag_validate_structure_bsp()` is shimmed, the CBSP's nested schema pointers/regions are not semantically validated by this test. Keep the report output precise.
- An overprovisioned host package fixture says nothing about PS2 6 MiB current-BSP or overall budget fit.
- It does not prove game ticks/player transition triggers, renderer consumer quiescence, or visible GS output.
- It does not prove guest fault behavior. After M2 map capacity/guest load, PCSX2 still needs a test-only diagnostic route through the real scenario function with targeted failure flags at candidate read, tag validation, CE port verification, and old BSP retry; run interpreter and recompiler on the same pinned image/package.

## Gate statement

Tier B is a contained next implementation slice: the current Tier A harness and host compatibility layer are in place, `cache_files.c` is reported to compile under those shims, the required CE ABI/layout assertions already exist, and the PS2 adapter/package components are host-tested. The private tag-loaded state is the one setup seam that must not be confused with normal CE map loading. A package-derived two-BSP a30 fixture can close it without asserting EE fit. Keep M2 Step 6 partial until this Tier B executable passes and later target guest evidence verifies actual BSP replacement/rollback on a capacity-qualified scenario.

**Current non-mutating check:** `python3 -m pytest -q -rs tests/test_hcu_scenario_bsp_switch.py` compiled the current Tier A fixture but skipped executing its native ILP32 binary because sandbox policy blocks native ILP32 execution with SIGSYS. Thus this report has inspected current fixture/build sources and current production R5900 object relocations, but does not claim a host runtime pass. `qemu-i386`/`qemu-i386-static` are not installed; `pcsx2` is installed, but PCSX2 execution is a later guest path with the currently documented display/map-capacity prerequisites. `git diff --check` passes for this report.
