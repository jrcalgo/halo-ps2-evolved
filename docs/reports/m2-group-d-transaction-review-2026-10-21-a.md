# M2 Group D transaction integration review (2026-10-21)

**Purpose:** independent, report-only review of Group D in [`plans/7.hcu-remake-m2-m4.md`](../../plans/7.hcu-remake-m2-m4.md#L251). No production code, tests, or shared plan were edited. The goal was to identify whether a small integrated fixture is still missing and, if so, the smallest next seam to compose.

## Executive finding

The core integration Group D previously called for is now present in `tests/test_hcu_scenario_bsp_switch.py::test_retail_ctag_and_cbsp_flow_through_ce_transaction_and_ps2_cache`: one host ILP32 executable compiles the real CE `scenario_switch_structure_bsp()` and cache load/unload logic, actual HCU PS2 cache/CTAG/CBSP adapters, the parent CTAG mount/backend/catalog/resource-index, and halo-ps2 HP2 decoding/arena code. It mounts a real audited `a30.hp2`, materializes its CTAG into the HCU tag-cache fixture, validates it with CE's real tag/schema validators, and switches among real package CBSP extents while asserting CE global/tag-instance and parent arena/lease state. Its failure/rollback/retry coverage is substantially stronger than the older standalone cache-model and UI service fixtures. The plan already records this in Group D and Step 7 evidence ([plan lines 255–259](../../plans/7.hcu-remake-m2-m4.md#L255), [lines 518–526](../../plans/7.hcu-remake-m2-m4.md#L518)).

Therefore the smallest useful next increment is **not** another package-backed CE switch harness. It is to close the single significant integration seam left by the current fixture: change its package and map-source ingress from a whole package read into libc memory plus a test-local `hp2_load()` callback and `no_retail_read()` to the production parent bounded file-reader path (`world_load_section_with_scratch()` plus `ctag_map_source`), with a deterministic FileXio host shim. This should retain CE switch/failure assertions unchanged. `tests/ctag_mount_main.c` already demonstrates the production FileXio-backed map source and map-service package loading separately; `tests/hcu_scenario_bsp_switch_main.c` already demonstrates the CE/package/CBSP transaction. The integration should compose those exact pieces, not reimplement the CE transaction or weaken the production admission guard.

This would be **host integration evidence only**. It cannot satisfy PS2 memory/capacity or PCSX2 guest acceptance: the retail CE fixture uses 16 MiB tag cache, 8 MiB BSP cache, 16 MiB owner and 16 MiB BSP scratch, and an external 4 MiB claims bitmap, not production arena limits. Gameplay map admission remains correctly blocked until M2 capacity is solved ([`hcu_map_service.c:164-168`](../../src/stream/hcu_map_service.c#L164), [`:214-238`](../../src/stream/hcu_map_service.c#L214)).

## Exact current fixture and observed coverage

### One executable already composes the main transaction owners

The Python fixture verifies the two package hashes against the audit manifest, checks HMAP source identity, decodes the CTAG and CBIX, verifies all CBSP envelopes and extents, then builds one `HCU_BSP_RETAIL_INTEGRATION` executable from the real CE scenario/cache source, real PS2 adapter sources, parent mount/catalog/resource-index/backend sources, HP2, and arena implementation ([`test_hcu_scenario_bsp_switch.py:75-114`](../../tests/test_hcu_scenario_bsp_switch.py#L75), [`:138-183`](../../tests/test_hcu_scenario_bsp_switch.py#L138)). The C harness mounts `a30.hp2` into a parent owner and separate scratch arena, invokes real cache-open and CTAG materialization, installs the actual CTAG tag table as CE globals, binds CE's claims bitmap, and calls `tag_validate_tags()` before selecting the scenario ([`hcu_scenario_bsp_switch_main.c:610-713`](../../tests/hcu_scenario_bsp_switch_main.c#L610)).

The package-backed transaction traverses actual scenario references in order, exercises every BSP in `a50` as well as both in `a30`, and switches back to the original BSP. It asserts the selected CE indices, global pointers, tag-instance bases, rematerialized bytes, cluster PVS/sound accessor pointer/value bounds, and that transient parent BSP scratch is released after each call ([`hcu_scenario_bsp_switch_main.c:730-770`](../../tests/hcu_scenario_bsp_switch_main.c#L730), [`:523-590`](../../tests/hcu_scenario_bsp_switch_main.c#L523)). Its snapshot captures both indices, all three CE BSP pointers, cache-header ownership, every scenario BSP tag-instance base, parent owner and scratch cursors, mount BSP-lease state, and a BSP destination byte sample ([`hcu_scenario_bsp_switch_main.c:123-160`](../../tests/hcu_scenario_bsp_switch_main.c#L123)).

Failure paths currently include:

| Injected condition | Executed result |
|---|---|
| Initial CBIX section callback fails once | Parent mount rolls back owner/scratch and leaves cache unavailable; same package mount retries successfully ([`hcu_scenario_bsp_switch_main.c:644-670`](../../tests/hcu_scenario_bsp_switch_main.c#L644)). |
| Candidate BSP owner load fails | Real CE switch reloads the old BSP through the same destination; snapshot and bytes match, then retry/switch-back succeeds ([`hcu_scenario_bsp_switch_main.c:772-787`](../../tests/hcu_scenario_bsp_switch_main.c#L772)). |
| Candidate port verifier rejects | Real CE rollback rematerializes and republishes old BSP; candidate tag base is cleared; then retry succeeds ([`hcu_scenario_bsp_switch_main.c:789-804`](../../tests/hcu_scenario_bsp_switch_main.c#L789)). |
| Candidate real BSP schema validator rejects | The actual CE BSP schema validator runs, with a separately controlled post-validation rejection; old BSP is reloaded; then retry succeeds ([`hcu_scenario_bsp_switch_main.c:806-820`](../../tests/hcu_scenario_bsp_switch_main.c#L806)). |
| Candidate and old BSP package section loads both fail | CE publishes null BSP pointers/indices, clears the cache header and tag-instance bases, enters menu fallback; parent leaves mounted map owner intact and releases BSP scratch/lease; a later retry restores the old BSP ([`hcu_scenario_bsp_switch_main.c:822-839`](../../tests/hcu_scenario_bsp_switch_main.c#L822)). |

The CE structure verifier is real `structure_bsp_port_verify_ce()` with a failure bitmask after its normal result; the schema wrapper calls actual `tag_validate_structure_bsp_actual()` and only then applies an explicit test rejection bitmask ([`hcu_scenario_bsp_switch_main.c:250-280`](../../tests/hcu_scenario_bsp_switch_main.c#L250), [`:386-404`](../../tests/hcu_scenario_bsp_switch_main.c#L386)). The actual PS2 cache `cache_file_read()` requests the parent loader for the exact BSP extent, validates/materializes CBSP into the fixed test destination and clears Xbox-only vertex/index handles before CE validation ([`ps2_cache.c:375-445`](../../submodules/halo-ce-universal/port/ps2/src/ps2_cache.c#L375)). The parent callback maps the exact `(file_offset,file_size)` through CBIX, leases the encoded section from BSP scratch, and routes successful/failed BSP mounting through the production backend ([`ctag_mount.c:67-104`](../../src/stream/ctag_mount.c#L67)).

### Reusable but separate fixtures

- `tests/test_cbsp.py` compiles the real PS2 cache/CTAG/CBSP code with synthetic images and separately verifies real retail `a30` extents/materialization; it is adapter coverage, not CE switch coverage ([`test_cbsp.py:208-258`](../../tests/test_cbsp.py#L208), [`:260-324`](../../tests/test_cbsp.py#L260)).
- `tests/test_ctag_mount.py` compiles the parent mount/source/service plus production PS2 adapters and halo-ps2 reader, and checks parent transactional mount, FileXio source behavior, corrupt/missing section failures, source identity, and rollback ([`test_ctag_mount.py:126-159`](../../tests/test_ctag_mount.py#L126)).
- `tests/test_retail_ui_ctag_mount.py` uses real UI package inputs, compiles the full parent `hcu_map_service` and FileXio reader shim, and exercises same-map owner unload/reload, source handle accounting, transport EOF and corrupt package failures. It is restricted to the admitted UI map and does not call CE's BSP switch ([`test_retail_ui_ctag_mount.py:16-76`](../../tests/test_retail_ui_ctag_mount.py#L16)).

These tests should remain distinct as diagnostics; the next composition should reuse their host FileXio mechanisms and keep the current large-memory CE fixture available as a rapid transaction regression.

## Remaining unmocked seams and limits

The current test is package-backed, but not end-to-end file-backed:

1. The Python runner reads the entire `.hp2` into memory, then the C harness reads it again with `fopen/fread` and calls `hp2_open()` on the whole buffer ([`test_hcu_scenario_bsp_switch.py:98-114`](../../tests/test_hcu_scenario_bsp_switch.py#L98), [`hcu_scenario_bsp_switch_main.c:592-607`](../../tests/hcu_scenario_bsp_switch_main.c#L592), [`:625-627`](../../tests/hcu_scenario_bsp_switch_main.c#L625)). Its local `load_package_section()` calls `hp2_find()`/`hp2_load()` directly and ignores `pack_path`; the `no_retail_read()` callback always returns failure ([`hcu_scenario_bsp_switch_main.c:311-364`](../../tests/hcu_scenario_bsp_switch_main.c#L311)). Thus it exercises package bytes and HP2 CRC/decompression in memory, but not the production parent retained-descriptor path, FileXio open/read/seek/EOF/close, mounted retail source-resource reads, or source-handle ownership across BSP switching.
2. The mount entry point is direct `ctag_mount_hp2_with_bsp_catalog()`, not `hcu_map_service` or its preflight/deferred-reload/map-unload transaction ([`hcu_scenario_bsp_switch_main.c:639-670`](../../tests/hcu_scenario_bsp_switch_main.c#L639)). This is appropriate for BSP switching while non-UI map admission is closed, but means the fixture must not be described as an L0–L6 map-service transaction.
3. `retail_owner`, `retail_bsp_scratch`, the physical CE cache arrays, and claims bitmap are 16/16/16/8/4 MiB-class host fixtures ([`hcu_scenario_bsp_switch_main.c:27-30`](../../tests/hcu_scenario_bsp_switch_main.c#L27), [`:112-121`](../../tests/hcu_scenario_bsp_switch_main.c#L112)). They test ownership mechanics, not production high-water, 32 MiB non-overlap, the fixed 6 MiB `current_bsp` cap, or ability to load a supported gameplay map. The fixture checks current cursors and a sample of the BSP bytes, not an allocation ledger tied to target addresses.
4. The test injects whole-section read failure before `hp2_load()` allocation/decode; it does not inject partial package-file reads, late streamed decoder writes/CRC failure, CBSP parse/materialization corruption after the parent lease is acquired, or failure after `scenario_unload()` releases the whole mount owner. The separate world-section and UI service suites cover some of these other boundaries, but not in this CE switch executable.
5. HCU CE lifecycle is bounded to the real BSP switch/load/unload path. End-of-test cleanup manually clears cache state and calls `ctag_mount_unload()` rather than invoking the whole actual `scenario_unload()` path, so map-level teardown with CE globals and retained package reader still needs composition.
6. Several machine-side leaves remain explicit host shims: physical-memory base/size accessors return arrays; vertex-buffer register/deregister hooks count calls; time, collision logging, sound, BSP reconnect/disconnect, error, and menu functions are stubs/counters ([`hcu_scenario_bsp_switch_main.c:225-235`](../../tests/hcu_scenario_bsp_switch_main.c#L225), [`:367-445`](../../tests/hcu_scenario_bsp_switch_main.c#L367)). Those are suitable seams for semantic transaction testing, not evidence that target GS/EE scheduling or renderer registration works.

## Smallest next fixture composition

Implement only the ingress upgrade inside `test_retail_ctag_and_cbsp_flow_through_ce_transaction_and_ps2_cache`; do not replace the transaction body or enlarge production budgets:

1. Keep Python's hash/manifest prechecks for `a30` and `a50` as a cheap provenance guard. Continue passing package/source paths and expected HMAP/catalog extents to the executable.
2. In the C fixture, replace the whole-file `read_package_file()` + `hp2_open()` with a retained `file_reader_t`/HP2 bounded section callback matching production `world_load_section_with_scratch()`; compile the real halo-ps2 `world/section.c`, `stream/file.c`, streaming HP2 code and `core/mem.c`. If production FileXio cannot be linked directly into this ILP32 fixture, use the already exercised FileXio shim contract from `tests/ctag_mount_main.c`, with deterministic per-call failure injection and open/close counters—not a new read implementation that sidesteps the production reader.
3. Replace `no_retail_read()` with an initialized production `ctag_map_source` over the matching decompressed retail map. Prefer the existing `ctag_mount_hp2_file_verified_discover_with_bsp_catalog()` path so HMAP identity, source SHA, discovered CRNG tag extent, source resource reads, lifetime retention, and close-after-unmount behavior are exercised. Assert a resource interval read reaches exact source bytes and the source remains open through candidate switch/fallback/retry, then closes exactly once on complete teardown.
4. Preserve CE scenario and cache globals, `cache_file_read()`/`scenario_structure_bsp_load()`/`scenario_switch_structure_bsp()`, all current fault injection and snapshot assertions. Add narrowly targeted failpoints for package header/table read, CBSP section read after a switch begins, streamed section decode/CRC failure after destination allocation, and resource source short read; assert either rollback to same old BSP or deterministic safe-null/menu state and then a same-process retry.
5. Add a final actual CE scenario teardown call if the `scenario_unload()` compile closure can be linked without broad, unrelated behavior; otherwise explicitly test that the production public cache owner-release callback orders CE cache unmount/source close/arena rewind, and keep the actual full scenario unload as a named remaining boundary. Never manually free the parent owner before HCU's mounted cache callbacks are unpublished.
6. Bind output to both package hashes, source-map hashes, exact source pins, linker map, and executable hash. Test `a30` and `a50`; keep all owner sizes intentionally overprovisioned but print them to prevent accidental capacity claims. Run host with ASan/UBSan if practical, then retain the existing target M2/PCSX2 gates separately.

### Expected acceptance statement for this next slice

“The current host ILP32 CE BSP transaction now reads the package and source map through the production parent bounded-reader/source abstractions, maintains one retained source handle while CE may reselect BSP data, rolls back and retries after injected file/decode/resource failures, and releases source/package/owner state only after cache unmount.”

It still must **not** say that a retail gameplay map fits the PS2, is admitted by the service, is successfully loaded in PCSX2, or renders.

## Test entry points, prerequisites, current verification

Exact current-package command (package root is external to the repository):

```sh
PYTHONPATH=. \
HALO_HCU_M2_PACKAGE_ROOT=/tmp/hcu-m2-capacity-repro.P5qdmI/packages \
HALO_HCU_M2_PACKAGE_MANIFEST=docs/reports/retail-cbsp-catalog-package-audit-e4a97218.json \
python3 -m pytest -q tests/test_hcu_scenario_bsp_switch.py -k retail
```

Run after native host ILP32 execution is allowed; the test explicitly skips the executable when the sandbox returns SIGSYS. Related separate suites are `tests/test_cbsp.py`, `tests/test_ctag_mount.py`, `tests/test_retail_ui_ctag_mount.py`, and `tests/test_world_section_visitor.py`. At review time, package and manifest identity hashes were `a30.hp2=ce38764fbba687bb26d4f2eb8a6cf066e19e4b8b81521d6f70f23ce8d00f183d`, `a50.hp2=9359e0eb09427b098d9773708352c77dbf426ebcec9d7b27400268d84221941a`, and package audit JSON `e4a9721846db228b88e6a563c34c0dccc7c6dc7694cf5a393d66c67ca004503b`.

This review ran:

```sh
PYTHONPATH=. HALO_HCU_M2_PACKAGE_ROOT=/tmp/hcu-m2-capacity-repro.P5qdmI/packages \
HALO_HCU_M2_PACKAGE_MANIFEST=docs/reports/retail-cbsp-catalog-package-audit-e4a97218.json \
python3 -m pytest -q tests/test_hcu_scenario_bsp_switch.py -k retail \
  tests/test_cbsp.py tests/test_ctag_mount.py
```

Result: **2 passed, 2 skipped, 12 deselected**. The `-k retail` filter means this was not the whole selected test set. A second run without the filter:

```sh
PYTHONPATH=. HALO_HCU_M2_PACKAGE_ROOT=/tmp/hcu-m2-capacity-repro.P5qdmI/packages \
HALO_HCU_M2_PACKAGE_MANIFEST=docs/reports/retail-cbsp-catalog-package-audit-e4a97218.json \
python3 -m pytest -q tests/test_hcu_scenario_bsp_switch.py \
  tests/test_cbsp.py tests/test_ctag_mount.py
```

Result: **13 passed, 3 skipped**. These are host tests; no PCSX2 guest execution or target RAM validation was performed for this review. Current repository/HCU/halo-ps2 pins were parent `70e2ed0cf2145a45d23aa07414a3a88c05155d4c`, HCU `6933490b2d16bb1c637295b6a0f3880ba23a7d56`, halo-ps2 `71183bb0a9adc586cd267b2780c82bbc12cfd95b`; working-tree changes in relevant files make those commit IDs insufficient alone, so bind any follow-up run to source-file hashes or a clean source snapshot as well.
