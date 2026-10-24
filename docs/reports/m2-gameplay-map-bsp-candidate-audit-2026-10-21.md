# M2 gameplay-map/BSP candidate and direct-visitor composition audit

**Scope:** report-only audit requested for the current M2 catalog/package and production CBSP visitor. No code, plan, catalog, capacity, or acceptance-gate edits were made. The purpose is to select a defensible first non-UI gameplay BSP candidate and give the implementation agent exact artifact identity, spans, prerequisites, and a test composition. This does not qualify a map for runtime admission.

## Finding

Use the frozen retail `longest` package and its sole `B000` BSP as the first *candidate* for composing the direct CBSP visitor through the production map service and CE cache callback. It is the smallest legitimate non-UI map in the current package audit by the recorded compact-tag-plus-projected-BSP lower bound (4,488,144 bytes), and its raw B000 image is only 374,784 bytes. That makes it the highest-value early integration case: it exercises a real scenario tag image, CE BSP extent/catalog lookup, tag-string relocation, and the production final-destination visitor with minimal BSP size. It is not the final capacity stress case, a campaign-map qualification, nor permission to open the map catalog.

The main blocker is no longer the CBSP callback design: the current dirty tree has the visitor registered from `hcu_map_service` through `ctag_mount` to `ps2_cache`, and `cache_file_read()` writes candidate BSP bytes to the bound final BSP span before it knows the outer HP2 CRC. It keeps CE's completion flag false until the visitor and CBSP validation/rebase succeed. However, existing production-composed retail coverage exercises the UI path, while the available frozen Longest test exercises the split parser/rebase API separately. There is no test yet that drives this exact Longest B000 package through `ctag_mount` + `hcu_map_service.visit_section()` + HCU `ps2_cache.c` + real CE scenario load/verification/publication. Longest CTAG is a separate, larger blocker: the path still materializes the whole 4,339,096-byte encoded CTAG and cannot fit the 1,572,864-byte `streaming` owner.

## Exact candidate identity and extents

The checked-in worktree revision pins are parent `70e2ed0cf2145a45d23aa07414a3a88c05155d4c`, HCU submodule `6933490b2d16bb1c637295b6a0f3880ba23a7d56`, and halo-ps2 submodule `71183bb0a9adc586cd267b2780c82bbc12cfd95b`. The parent, HCU, and halo-ps2 worktrees are dirty; for exact reproduction bind the following per-file and input hashes too, rather than treating the commit IDs as the complete source identity.

| Artifact / source | Identity |
|---|---|
| Decompressed retail `longest.map` | 42,141,696 bytes; SHA-256 `e045b0843f4a167a516f050161a651610fafc94ccc8c5f2c5d5725d108d5d1b9` |
| Frozen Longest HP2 package `build/m2-artifacts/longest-2fba411b-all-bsps.hp2` | 2,041,856 bytes; SHA-256 `6f9c19feb4df9e7ec49e797ce3eb6f7cfbdef3c89c6363b12aab2f05359f5a5b` |
| Schema ELF used to produce the frozen package | SHA-256 `2fba411b7244b20fdf31f0b1e540fc2b6f5598891f53a64f8b12f850a0cda0aa` |
| Parent `src/stream/hcu_map_service.c` | SHA-256 `66c7a3c904fbab41c8473f44f5d18ddd7a3b34d09d1f9579caa076b02d5c3880` |
| Parent `src/stream/ctag_mount.c` | SHA-256 `b90f5df170711f40e550cf6b913d6d58824700eb3c80980456c84a37b8c54ef5` |
| HCU `port/ps2/src/ps2_cache.c` | SHA-256 `d2314926bf16064cdc898fc14d9e4c59eb6218d167d345ee33f0f704914063aa` |
| halo-ps2 `engine/src/world/section.c` | SHA-256 `3626bd968af5e89bfe0876dcbaec49334e39f004a48d920fb4bc3478f1521e7c` |
| Frozen package provenance / source and output measurements | [`m2-longest-artifact-freeze.md`](m2-longest-artifact-freeze.md), including its qualification limits and pack command |

There are two distinct notions of extent; fixtures and logs must print both:

| Kind | Longest value | Meaning |
|---|---:|---|
| CE source-map tag-data extent | offset `35,062,272` (`0x0216F000`), size `7,079,296` (`0x006C1000`) | HMAP/cache-header identity fields from the retail map; not the compact image size |
| Compact CTAG image / wire extent | image `4,263,624` bytes; encoded HP2 raw CTAG section `4,339,096` bytes | Image is rebased into CE's tag-cache address; wire section also includes the CTAG header and 18,855 relocation rows |
| Retail CE B000 source extent (CBIX and CBSP agree) | offset `2,048` (`0x800`), size `374,784` (`0x5B800`) | Requested original cache range passed by CE; CBSP header validates its source offset and size against this exact request |
| Decoded CBSP section shape | section raw `377,388` bytes = 36-byte CBSP header + 374,784-byte BSP image + 2,568-byte relocation table | 214 relocation rows total (138 BSP-internal + 76 CTAG-name relocations); final BSP image is not the entire envelope |
| HP2 package file extents | `CTAG @ 0x800`, stored 1,787,814/raw 4,339,096; `B000 @ 0x1B7800`, stored 238,144/raw 377,388; `CBIX @ 0x1F2000`, stored/raw 44 | Package transport extents, distinct from CE's retail-map source offset/size |

These exact section extents were read from the frozen package with `halo2ps2.hp2 info`; HMAP/CBIX/CBSP were decoded using the repository pack tools and cross-checked. HMAP gives map name `longest`, decompressed file length `42,141,696`, tag offset/size above, and the same source-map hash. CBIX has one `B000` row `(2048, 374784)`, exactly matching the CBSP embedded source extent. This satisfies package correspondence, not a physical file-read or runtime-load claim.

## Why Longest is the initial candidate—and what it does not establish

The current working-set audit ranks Longest lowest among all non-UI candidates on its schema lower bound plus projected active-BSP measure: 4,403,387 bytes. Its compact tag image plus projected active BSP is 4,488,144 bytes. Its source-map BSP image is 374,784 bytes. Nearby alternatives are larger: Chillout 4,609,360 bytes compact-tag + projected BSP, Wizard 4,609,860, Carousel 4,611,272, Hang 'Em High 4,626,468, and Rat Race 4,632,116. Thus Longest is a sensible first candidate for integration/debugging because it minimizes the number of simultaneous large owners while still traversing a real stock gameplay BSP. Data are from [`retail-map-working-set-a4-current.json`](retail-map-working-set-a4-current.json), which labels these as lower bounds/projections, not fit evidence.

The raw selected BSP's 374,784 bytes is not the budget's 1,814,336-byte candidate BSP span requirement by itself. The candidate long-map split in [`m2-longest-streamed-live-set-reconciliation-2026-10-21.md`](m2-longest-streamed-live-set-reconciliation-2026-10-21.md) assigns 4,477,120 bytes to tag cache and 1,814,336 to BSP cache within the unchanged 6,291,456-byte `current_bsp` region, preserving the claims-bitmap formula. This is only arithmetic/diagnostic-link evidence; the diagnostic layout had `acceptance=false`, and an older UI memory-ready run is not Longest physical-placement proof. Further, the whole-map ledger must include the resident CE game-state/claims/static owners, persistent CRNG/CBIX/CTAG relocation metadata, dynamic actors/objects/effects, animation pins, texture/lightmap data, audio, frame snapshots/scratch, and renderer DMA/upload queues. In particular, `dma_commands` is already at risk of aliasing snapshot packing with renderer chain allocation. A small BSP does not make those other resident owners disappear.

`longest` is a stock multiplayer map, not a campaign mission. Passing this first vertical-slice test would show a real gameplay BSP can traverse the stream/cache/CE validation path; it would not satisfy the overarching plan's all-supported campaign-map capacity requirement or establish AI, scripts, collision parity, rendering, or gameplay startup. Keep all non-UI catalog requests rejected until the full Step 8/10 decision and acceptance conditions pass.

## Current production path and composition seam

The relevant control/data sequence is:

1. `hcu_map_service` validates a catalog candidate and mounts the verified HP2 source. On successful map mount it registers `visit_section()` through `ctag_mount_set_bsp_section_visitor()` (`src/stream/hcu_map_service.c:154-181`). The HCU source code is included in the composition test even though current `capacity-not-qualified` logic denies the Longest runtime request (`src/stream/hcu_map_service.c:230-253, 283-310`).
2. `ctag_mount` retains CTAG/CRNG/CBIX and the source reader; `visit_bsp_extent()` requires an exact CBIX match and rejects ranges overlapping tag data or CRNG resources, then delegates the named `Bnnn` section to the registered visitor (`src/stream/ctag_mount.c:235-276, 332-350`).
3. The service visitor adapts the halo-ps2 visitor convention and calls `world_visit_section_with_scratch()`, which retains a bounded HP2 decode workspace, feeds transient decoded chunks, and reports success only after the outer section CRC passes (`src/stream/hcu_map_service.c:80-112`; `submodules/halo-ps2/engine/src/world/section.c:67-138`).
4. `ps2_cache.c` recognizes only CE's BSP request shape (`tag_index == NONE` and destination exactly the fixed physical BSP-cache base). Its sink stores the 36-byte header locally, copies image bytes to that exact fixed destination, and places relocation rows in the destination's unused tail. It checks the stream length, `ps2_cbsp_open_parts`, the exact CBIX request extent, and CTAG-name relocations before `ps2_cbsp_rebase_in_place`; it clears only Xbox vertex/index buffer fields after successful validation and sets CE completion true only once the visitor path returns success (`port/ps2/src/ps2_cache.c:390-506, 552-576`). For a recognized visitor request it returns failure rather than silently falling through to the generic raw-file path.
5. CE's `cache_file_read` result is followed by CE structure-BSP header checks and `structure_bsp_port_verify()`/schema validation before CE publishes the BSP datum/global pointers (`source/cache/cache_files.c:1412-1513`; `source/scenario/scenario.c:1101-1198`). On failed BSP switching, CE's real scenario path attempts to restore the old reference. Current first-load/post-unload and successful B000 transaction semantics should be asserted at this boundary, not inferred from a callback unit alone.

The fixed destination sink intentionally changes failure semantics versus whole-buffer materialization: late HP2 I/O/CRC errors can leave a partial or full relative-image candidate inside the final BSP span. It must remain unpublished (completion false, no CE header/datum/global pointers, no snapshot referencing the replaced map), and a retry must overwrite from offset zero before it may publish. The current synthetic callback fixture in [`tests/ps2_cache_cbsp_main.c:219-270`](../../tests/ps2_cache_cbsp_main.c#L219) demonstrates late-write failure and retry; that is not retail Longest composition.

## Exact integration fixture recommended next

Extend the actual CE retail BSP-switch fixture, but make a one-map Longest case rather than adding Longest into the current a30/a50 two-map assumptions. The present fixture is a good base: [`tests/test_hcu_scenario_bsp_switch.py:75-230`](../../tests/test_hcu_scenario_bsp_switch.py#L75) compiles the real CE `scenario.c`, HCU cache/CTAG/CBSP, parent mount/catalog/source/index, halo-ps2 HP2 reader, and real schema validator; [`tests/hcu_scenario_bsp_switch_main.c:620-740`](../../tests/hcu_scenario_bsp_switch_main.c#L620) owns test arenas and CE globals. It currently uses an 8 MiB BSP array, 16 MiB owner arena, 131,072-byte decoder scratch, and 4 MiB claims array, and calls the whole-payload BSP mount API; those host capacities and the legacy path must not be described as PS2-fit evidence.

Recommended exact sequence:

1. Gate on the frozen Longest package SHA, decompressed map SHA, schema/source pins, and matching HMAP source hash. Decode CBIX and assert exactly one row (`B000`, source `(2048,374784)`); decode B000 through the full-output oracle and produce a full expected post-rebase image from the same CTAG image. Keep expected output in host-only memory, never in the simulated production arena.
2. Mount using the same verified-source and CTAG/CRNG/CBIX production ownership path as the retail fixture. Before scenario tag cache load, exercise the *currently missing CTAG direct-destination strategy* separately; the whole CTAG staging path will fail the actual 1,572,864-byte production map owner, so do not let a large test arena mask it. To isolate the CBSP integration temporarily, the test may initialize the HCU cache with a prevalidated candidate CTAG image while retaining the real package-backed source/catalog/visitor path, but mark that an explicit CBSP-isolation test, not a Longest map-load test.
3. Register the `ctag_mount` section visitor, configure the service path to `longest.hp2`, bind real fixed addresses/capacities from an opt-in candidate layout (4,477,120 tag + 1,814,336 BSP if testing that diagnostic split), initialize canaries outside both spans, and link `world_visit_section_with_scratch()` plus the actual PS2 cache adapter. Assert actual `section_scratch` is the production child lease of 124,224 bytes after the two 134,496-byte snapshot banks are bound; assert peak includes nested 98,304-byte HP2 work area, all alignment, and any simultaneous allocations. Do not use a 131,072-byte test area or whole 393,216 bytes without explaining snapshot ownership.
4. Call CE's actual `scenario_structure_bsp_load()` with the scenario's real B000 reference. Verify the request matches CBIX and the CBSP embedded source extent exactly; capture visitor open/read/close and scratch acquire/release counts; compare exactly 374,784 final bytes against the whole-buffer oracle after documented PS2 normalization; verify relocations (138 internal, 76 CTAG-name), bounds and header schema; confirm `cache_file_read` completion is true only after HP2 CRC and CBSP rebase; confirm CE validates before datum/global publication.
5. Inject failure before first output, mid-image, near final image/table, late HP2 outer CRC, bad CBSP internal CRC, malformed last relocation, invalid CTAG name target, scratch exhaustion, and post-rebase/pre-publication. For late write faults, allow changed candidate bytes but require both canaries, failure sentinel, no datum/header/global/index publication, no retained visitor descriptor/scratch, and corrected same-process retry that rewrites the entire span and matches the oracle. Include BSP-switch rollback with a second fixture BSP only if available; a one-BSP first-load failure must leave explicit null/no-map state.
6. In the same harness, assert no CE consumer or render snapshot may retain a pointer/handle to the previous map during candidate replacement. Keep the cache map owner/source open until CE unloads callback state; close source and rewind only after backend unmount. Verify owner marks and descriptor counts on success, all injected failures, unload, and retry.

Use two tiers to avoid overstating results:

- **CBSP isolation/composition pass:** actual retail Longest B000 visitor through parent catalog/service, HP2, HCU cache, CBSP validator/rebase, and exact physical destination, with a fixture-provided validated tag image. This closes only the CBSP seam.
- **Full Longest load pass:** add lossless CTAG streaming/private-stage/validation/rebase; real CE tag load and claims; production-sized arena/metadata; scenario BSP validation and publication; resident owner/high-water reconciliation; then the exact same pinned production ELF/package in PCSX2 interpreter and recompiler. Until this tier succeeds, Longest remains rejected and M2 open.

## Existing relevant tests and current evidence gaps

| Existing artifact | What it proves | What remains unproven |
|---|---|---|
| [`tests/test_cbsp.py:208-257`](../../tests/test_cbsp.py#L208) + [`ps2_cbsp_main.c`](../../tests/ps2_cbsp_main.c) | Frozen Longest package's split CBSP parser/rebase equals Python materialization, with 374,784-byte image and 214 rows | No mount/service visitor, cache completion, CE validation, globals, or failure retry in Longest composition |
| [`tests/ps2_cache_cbsp_main.c:219-270`](../../tests/ps2_cache_cbsp_main.c#L219) | Synthetic visitor validates callback failure sentinel, partial write then same-request retry, malformed relocation retry | Synthetic small envelope; visitor is injected, not production HP2 decoder nor retail bytes |
| [`tests/test_retail_ui_ctag_mount.py`](../../tests/test_retail_ui_ctag_mount.py) | Actual UI `hcu_map_service` path can register/visit a real retail UI B000 section; useful bridge proof | UI's 2,048-byte BSP and package are not gameplay map capacity or a real CE BSP world; no Longest CBSP limit |
| [`tests/test_hcu_scenario_bsp_switch.py:75-230`](../../tests/test_hcu_scenario_bsp_switch.py#L75) | Real CE scenario load/switch/rollback with real schemas/package data over a30/a50, through current cache adapter | Existing retail transaction uses full payload loader, a30/a50 only, and oversized host arenas; not Longest visitor or production spans |
| [`tests/test_world_section_visitor.py`](../../tests/test_world_section_visitor.py) | HP2 visitor byte parity and sink failure semantics across UI/Longest/Blood Gulch packages | Does not call HCU cache sink or CE scenario code |
| [`tests/test_retail_map_working_set.py`](../../tests/test_retail_map_working_set.py), [`retail-map-working-set-a4-current.json`](retail-map-working-set-a4-current.json) | Candidate ordering and schema lower bounds/projections | No runtime fit, no complete live-set, and the projection is explicitly not permission to strip consumers' data |

Focused current test execution for the missing integrated path should be reproducible as a named new test case in `test_hcu_scenario_bsp_switch.py` with package-env inputs and output logs retaining all hashes. The previous focused pass of UI/synthetic tests is useful but does not satisfy Longest. The M2 plan's Step 5 (catalog), Step 8 (stable backing/capacity), Step 9 (transaction), and Step 10 (current-image gameplay acceptance) remain sequential dependencies; implementing just this CBSP test cannot close Steps 8–10.

## Halo-64 comparison (lifetime only)

Halo-64 is useful only for renderer/cache lifetime discipline here. Its level unload waits for in-flight RSP work before freeing level data and its model-room path tracks frame references before recycling storage (`submodules/halo-64/port/n64/src/n64_render.c:1239-1280,1716-1755`, as analyzed in `m2-longest-streamed-live-set-reconciliation-2026-10-21.md`). The analogous PS2 requirement is to keep HCU tag/BSP destinations alive until all GS/VU/DMA readers have crossed an explicit completion fence. Do not import Halo-64's 8-MiB budget, N64 pool sizes, dropped AI/scripts/effects, or its embedded-BSP/no-op cache-read behavior (`submodules/halo-64/port/n64/game/n64_game.c:1271-1286`) as evidence for CE/PS2. This source path does not need REA: it is a source/package-layout audit, not decompilation of an opaque executable.

## Handoff: concrete next actions

1. First refresh the above file hashes against the exact current dirty worktree when preparing a test run; the parent/HCU/halo-ps2 submodules are dirty and commit IDs alone do not pin the CBSP patch.
2. Add a **single-map Longest B000 direct visitor composition** test over the real production `ctag_mount` and `hcu_map_service.visit_section` registration, actual HP2 visitor, HCU cache adapter, and CE BSP load/verify path. Reuse existing CE fixture, but add a direct visitor registration hook and do not reuse oversized capacities as acceptance.
3. Keep a separate explicit CTAG fixture until CTAG direct stream publication is implemented; never call a CBSP-only pass a gameplay map load.
4. Independently solve/adjudicate Longest CTAG relocation metadata: 75,420 relocation bytes + 9,380 CRNG + 44 CBIX = 84,844 persistent bytes (84,916 if HMAP retained). Candidate tag tail after CTAG image is 213,496 bytes, but that tail cannot be assumed free unless CE cache/schema boundary and claims ownership explicitly exclude the metadata and it remains retained until last use. HP2 visitor scratch itself is 98,304 bytes and fits the 124,224-byte child scratch lease with at least 25,857 bytes after 64-byte alignment; the old fixture's 173,760-byte high-water is due to also retaining relocation rows in that scratch and is not the only possible allocation topology.
5. Only then proceed to full map live-set budget and the pinned PCSX2 interpreter/recompiler run. Keep `capacity-not-qualified` denial in `hcu_map_service.c` until that full evidence exists.

## Current source pin and artifact recheck commands

```sh
git rev-parse HEAD
git -C submodules/halo-ce-universal rev-parse HEAD
git -C submodules/halo-ps2 rev-parse HEAD
sha256sum build/retail-maps/decompressed/longest.map \
  build/m2-artifacts/longest-2fba411b-all-bsps.hp2 \
  src/stream/hcu_map_service.c src/stream/ctag_mount.c \
  submodules/halo-ce-universal/port/ps2/src/ps2_cache.c \
  submodules/halo-ps2/engine/src/world/section.c
PYTHONPATH=submodules/halo-ps2/tools python3 -m halo2ps2.hp2 info \
  build/m2-artifacts/longest-2fba411b-all-bsps.hp2
```
