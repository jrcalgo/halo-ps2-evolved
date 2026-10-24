# M2 D20 host-oracle experiment path

**Purpose:** report-only implementation-path investigation for M2 Step 8/10. Identify the shortest defensible way to run actual CE D20 map/scenario and animation consumers in an overprovisioned host oracle, while measuring byte touches and owner lifetimes. This report does not alter map admission, memory budgets, or data placement. No eviction/externalization is recommended or implied.

## Finding

There is a useful starting seam, but no existing D20 gameplay oracle. The best path is to extend the current ILP32 CE lifecycle fixture rather than mistake the target ELF or a parser-only audit for workload evidence:

1. Produce a reproducible D20 HP2 package from the checked-in decompressed source map using the current schema/CTAG/CBSP conversion tools; keep the package host-only and explicitly oversize its test arenas.
2. Adapt the existing test executable, which already links actual CE `scenario.c`, PS2 cache/CTAG/CBSP providers, parent map service, and halo-ps2 HP2 reader, from the UI package to D20. Keep a test-only catalog admission path; never change the production UI-only map gate.
3. Add the smallest possible bridge from successful `scenario_load()` into real CE game/object/actor setup and `game_tick()` plus pose calls. Use actual D20 scenario actor placements/tags and deterministic scripted inputs. First prove one actor is created and its `object_compute_node_matrices`/`unit_preprocess_node_orientations` path is reached; then widen scenario coverage.
4. In the same host process, use preallocated trace/event and owner ledgers to record accesses, lifetime scopes and high-water. Extend the trace beyond animation access ranges to every candidate owner; do not call distinct touched bytes or observed active intervals “evictable”.
5. Bind every output to a single frozen source/build/package tuple, and compare instrumentation-on/off against the same deterministic replay and CE state/pose hashes.

This is a practical two-stage experiment. The existing host lifecycle fixture supplies genuine CE map/scenario load and rollback; it stops before game initialization, AI, object pose, or tick. A source-extracted `game_tick()` harness exists, but its phase implementations are stubs, so it cannot establish a D20 workload. The existing PS2 trace hooks can record real byte range requests in an opt-in PS2 build, but the currently retained target trace is not a representative guest capture and cannot stand in for the overprovisioned host scenario.

## Repository evidence and available seams

### Real scenario lifecycle is already host-linked, but is UI-only

[`tests/test_hcu_ce_map_lifecycle.py`](../../tests/test_hcu_ce_map_lifecycle.py#L18) builds a 32-bit/short-wchar executable with actual CE `scenario.c`, `tag_files.c`, all relevant schema units, PS2 `ps2_cache.c`/`ps2_ctag.c`/`ps2_cbsp.c`, the parent map service, and halo-ps2 HP2 section/file readers ([lines 51–90](../../tests/test_hcu_ce_map_lifecycle.py#L51)). It verifies the linked CE and production-service symbols ([lines 94–99](../../tests/test_hcu_ce_map_lifecycle.py#L94)). Today it hardcodes `ui-with-bsp.hp2`, `ui.map`, `levels\\ui\\ui`, and its same-process failure/retry behavior ([lines 19–23](../../tests/test_hcu_ce_map_lifecycle.py#L19), [map-load calls in the fixture](../../tests/hcu_ce_map_lifecycle_main.c#L457)). Its host owner/scratch arenas are deliberately fixed and explicitly described as lifecycle semantics rather than PS2 capacity ([`hcu_ce_map_lifecycle_main.c:439-449`](../../tests/hcu_ce_map_lifecycle_main.c#L439)). This makes it a good composition point for a separately named D20 host profile, not evidence of D20 execution today.

The lifecycle fixture calls `scenario_load()` and validates published CE globals/tags/BSP ([`hcu_ce_map_lifecycle_main.c:493-530`](../../tests/hcu_ce_map_lifecycle_main.c#L493)). It does not call `game_initialize()`, create campaign actors, call `ai_update()`/`game_tick()`, or drive object/unit/first-person pose. The ordinary tick fixture extracts the production CE `game_tick()` body, but replaces major phases—including AI, effects, and first-person update—with event stubs ([`test_hcu_game_tick_fixture.py`](../../tests/test_hcu_game_tick_fixture.py#L71)); it is sequencing evidence only, not a real actor workload.

### Data preparation exists; exact D20 outputs do not

The decompressed D20 source map is available at `build/retail-maps/decompressed/d20.map`, 205,501,952 bytes, SHA-256 `30d8fc02bcd209a7ce03174d8cf6cf771dd3621837d9a2d02111718dcc5e792c`. The current build tree contains UI and Longest HP2 packages, but no D20 HP2 package. `tools/pack_retail_ctag_hp2.py` is the package composition entry point; `tools/convert_retail_ctag.py`, `tools/convert_retail_bsp.py`, and `tools/audit_retail_scenario_bsp_references.py` are the existing schema/tag/BSP inputs to evaluate for D20 packaging.

The current frozen 2fba schema audit found a D20 CTAG image of 10,046,996 B (16-byte span 10,047,008 B), largest referenced raw BSP `d20_hangar` 8,517,632 B, and 24 total D20 BSP references. These are static whole-image extents, not a runtime working set. The existing D20 data lacks a current exact-schema D20 HP2 package/manifest to feed the host lifecycle fixture, and the previous schema artifact is historical against dirty HCU files. Before treating any package/report as current, rebuild the schema manifest from a single coherent source tuple and regenerate D20 outputs. The input/source audit path is intentionally offline and measures source ranges, not runtime cache behavior ([`audit_animation_data_ranges.py:27-74`](../../tools/audit_animation_data_ranges.py#L27)).

### Animation observer exists, but it is not a lifetime ledger

The opt-in `HALO_PS2_M2_ANIMATION_TRACE` trace hooks are present in the CE PS2 code. `animation_get_frame_data()` records an accessor request extent, explicitly described in source as *not* a pin/lifetime claim ([`model_animation_definitions.c:504-539`](../../submodules/halo-ce-universal/source/models/model_animation_definitions.c#L504)). The recorder uses fixed prebound event and context arrays and increments a dropped counter on overflow ([`ps2_animation_trace.c:216-265`](../../submodules/halo-ce-universal/port/ps2/src/ps2_animation_trace.c#L216)); its `H2ANIMT1` exporter streams a bounded header and event/context rows through a sink ([`ps2_animation_trace.c:286-390`](../../submodules/halo-ce-universal/port/ps2/src/ps2_animation_trace.c#L286)). The decoder requires a complete, CRC-valid stream and binds the capture to an ELF hash plus source-manifest hash and commit/profile strings ([`decode_ps2_animation_trace.py:29-65`](../../tools/decode_ps2_animation_trace.py#L29)).

Current test coverage verifies trace serialization/decoder rejection, trace clocks, object/unit/first-person phase-scope insertion and accessor bounds ([`test_ps2_animation_trace.py:135-186`](../../tests/test_ps2_animation_trace.py#L135)). Existing lifecycle coverage binds a 64-row recorder and samples map epoch around load/unload/preflight ([`hcu_ce_map_lifecycle_main.c:428-449`](../../tests/hcu_ce_map_lifecycle_main.c#L428)), but does not capture a real animation event. More importantly, an accessor trace alone cannot infer pointer lifetime: four yaw/pitch interpolation frames may be held at once ([`model_animations.c:1881-1886`](../../submodules/halo-ce-universal/source/models/model_animations.c#L1881)); compressed readers and `frame_info`/`default_data` paths have bypasses. Add explicit scope/pin events only in a separate diagnostic patch, with no runtime-provider behavior changes.

### M2 host assets and source code are modified/dirty

At this investigation snapshot, gitlinks are parent `70e2ed0cf2145a45d23aa07414a3a88c05155d4c`, HCU `6933490b2d16bb1c637295b6a0f3880ba23a7d56`, halo-ps2 `71183bb0a9adc586cd267b2780c82bbc12cfd95b`, and Halo-64 `17541f4444baabb47d1a0deb917f26ccb7b6bc5c`. The HCU and halo-ps2 worktrees are dirty. These commit IDs alone are not a reproducibility identity.

Current high-impact dirty-source hashes (SHA-256):

| Source | SHA-256 |
|---|---|
| `submodules/halo-ce-universal/source/models/model_animation_definitions.c` | `1d9df3bcc9aa0fb8f3db101a2185c4e95becacd9273717a01e1343d59b281ee8` |
| `submodules/halo-ce-universal/source/models/model_animations.c` | `e4ee659ab348529cc51cb3aea0177cfdb903a6a84e1bb58f3e43d9ae5592851f` |
| `submodules/halo-ce-universal/source/game/game.c` | `941e187aa0bfb1278cab7c5a94ae688808f702742d68e92802e7489a491a2dad` |
| `submodules/halo-ce-universal/source/scenario/scenario.c` | `ddef9ab76c88b09db055713c84ec680128d22b05323cd3599f4477116384cd5c` |
| `submodules/halo-ce-universal/port/ps2/src/ps2_animation_trace.c` | `118810f7a7d37d86bbe1f952b80ed82441c8bdb73687ebbff24dc1b0e49d2943` |
| `submodules/halo-ce-universal/port/ps2/src/ps2_cache.c` | `d2314926bf16064cdc898fc14d9e4c59eb6218d167d345ee33f0f704914063aa` |
| `tests/hcu_ce_map_lifecycle_main.c` | `6441be67076f5e9891a6c6f44d725ba5a69eaa36b028aa313c70cf0523f23f5f` |
| `tests/test_hcu_ce_map_lifecycle.py` | `d9cd45a8fea8db5e7c919b3a5c6cc23cfe3496c4bd1a99ab3ac78db285cfd449` |
| `tools/hcu_ps2_closure.py` | `57f263e40fc4c75d1d3867adc91e13467d8ed11c67c0fd1c82ca30f0d1133fea` |
| `tools/hcu_parent_link_probe.py` | `8f1b3a4e367f2b83814b35fdea210265c241251ab3d482e81adb89fd9d408289` |

Recompute these at experiment start. Also hash each tracked dirty diff, every untracked source/fixture input, generated semantics header, source manifest, exact compiler executable/version/flags, and package outputs. The H2ANIMT1 provenance validator only enforces commit IDs, `source_manifest_sha256`, toolchain/profile labels and exact ELF SHA; make a separate experiment manifest bind the map, package, schema artifacts, dirty-file manifest, instrumentation diff and replay inputs as well ([`decode_ps2_animation_trace.py:42-65`](../../tools/decode_ps2_animation_trace.py#L42)).

## Concrete experiment steps

### A. Freeze inputs before running

1. Preserve the exact current state without rewriting the shared dirty worktrees: record `git rev-parse HEAD` for parent/HCU/halo-ps2/Halo-64; produce `git status --porcelain=v2` for each; hash `git diff --binary` for each; list and hash all untracked files relevant to source, manifests, tests and generated schemas. Never include unrelated untracked build outputs as code.
2. Hash the decompressed `d20.map`, original source ISO/XISO if available, schema ELF and its compiler-derived schema manifest, schema generator, CTAG/BSP converter sources and commands, D20 CTAG/CBIX/CBSP package and catalog, and all package validation logs.
3. Record host compiler/sysroot, exact ILP32/short-wchar flags, generated MSVC semantics header hash, executable/link-map hashes, environment variables, and deterministic scenario/replay seed/input. Keep package and all owner arenas host-only. Label all sizes as host-oracle capacities.
4. Produce a machine-readable run manifest that includes exact SHA-256 for every artifact plus the source hashes above. Reject any mismatch between manifest and bytes before running.

### B. Build D20 package and extend only the host test fixture

1. Rebuild the schema closure from current HCU source rather than pairing with `schema-2fba411b-prior`. Regenerate D20 tag schema, referenced BSP catalog and package using the present converters; assert every D20 scenario BSP reference resolves to one package catalog entry with exact source offsets/sizes and decoded hash.
2. Create a separate `d20-host-oracle` test profile, reusing `test_hcu_ce_map_lifecycle.py` build flags/source list and the real CE/PS2-cache/parent-Hp2 composition. Generalize the C fixture’s map name, source/package inputs, owner arenas and claims storage through explicit arguments or generated constants. Do not loosen `hcu_map_service.c` production admission; a fixture-only catalog/service override must be visibly test-only and compile out of the PS2 profile.
3. Increase host owner and scratch buffers only enough to hold the full aligned D20 tag image, one selected active BSP, CE validator claims and decode temporaries. Print all extents and high-water independently; add guard regions/canaries. Do not use those buffers as a proposed EE topology.
4. First execute actual CE `scenario_load()` against D20 and validate published scenario/tag/BSP structures. Cover D20's initial BSP and then every referenced BSP one at a time. Include unload/remount and failed read/CRC/validation retry. This is a map/scenario lifecycle gate only.
5. In a second slice, invoke actual HCU game initialization and CE object/actor setup using the loaded D20 scenario. The minimally complete workload must reach a real authored actor/unit pose and real `game_tick()`, not just synthetic `animation_get_frame_data()` calls. Use deterministic, explicit shims only at machine/UI/audio/display boundaries; do not stub objects, units, AI, animation decoders or scenario data access. If compiling the full game path host-side is too broad, link/test actual units incrementally and report exactly which production function bodies are real versus shims; do not label that partial fixture a complete D20 actor workload.
6. Run distinct replay phases: boot/initial load; player spawn; one idle/moving/turning actor; AI alert/combat/damage/death; player locomotion and weapon first-person pose; vehicle/seat enter/exit if present; animated device; script/effect-triggered actor creation; one D20 BSP switch; unload and reload. Inventory the scenario to ensure each authored feature actually exists before claiming coverage. Test local player counts permitted by current product scope separately; do not synthesize actors in place of the D20 encounter.

### C. Instrument access, lifetimes and owners

1. Keep the existing fixed-capacity H2ANIMT1 recorder opt-in. Size host recording tables from an explicit pre-run bound; fail if dropped events are nonzero. Export/CRC/decode the trace after the run and match exact provenance. Trace access ranges for `animation.data`, compressed rotation/translation/scale, `default_data`, indexed and bulk `frame_info`, and schema validation/correction. Audit all direct address paths and accessor callers before interpreting misses.
2. Add a separate owner-phase ledger for tag image, each active BSP, claims, decoded/staging scratch, collision data, retained render data, textures/lightmaps, animation records, CE game state, actors/AI/scripts/effects, DMA/sound queues, audio and load-transition overlap. Record allocation/release/retain events with owner identity and phase; current bytes, peak bytes, and high-water by owner/phase; simultaneous pinned intervals; and failed/invalid accesses. A host heap/RSS graph is not an owner ledger.
3. For animation, maintain distinct metrics: (a) static complete payload size; (b) bytes ever requested/touched; (c) union over explicit tick/frame windows; (d) maximum simultaneous pointer/pin lifetime; (e) any hypothetical resident-cache occupancy after charging metadata, read-ahead and staging. Without acquire/release scopes there is no measured pinned-live-set; mark it unknown rather than infer it from sequential trace rows.
4. For every retained pointer, identify the function/frame scope where it becomes live and dies, including overlapping interpolation frames. Explicitly test the four-frame aiming interpolation and simultaneous actor/player/first-person calls. Current trace row order alone does not establish pointer overlap.
5. Record CE validation acceptance/correction result and resulting tag bytes. Compare pose matrices/node outputs, actor/object state, damage/RNG/script state and deterministic tick hashes with trace disabled vs enabled. Vary render calls 0/1/3 per tick while keeping tick/replay constant. Observer-on/off differences beyond telemetry invalidate the run.
6. Do not measure target cycle cost from native x86 wall time or PCSX2 time. Host data determines source semantics/locality only. EE CPU and real I/O deadlines require a later exact R5900/PCSX2 regression and, for hardware-limit qualification, actual EE measurements.

## Static sizes versus runtime measurements

Keep these result categories separate in every run report:

| Category | What is currently available | What it does not establish |
|---|---|---|
| Static whole-image sizing | D20 CTAG/BSP source/schema extent reports and fixed configured EE region sizes. | Peak campaign residency, allocations actually made, or safe partitioning. |
| Bytes touched | Offline schema/range extraction; opt-in trace can count requests/ranges when a real pose workload exists. | Whether requested pointers overlap in lifetime, whether bytes can be evicted, or replacement cache fits. |
| Window working set | Not measured for any real D20 scenario/actor replay. | Maximum simultaneous pins or all-owner peak. |
| Pinned/live high-water | Not measured; current accessor tracing is expressly not lifetime instrumentation. | Safe eviction/provider boundary. |
| Host arena/owner high-water | UI lifecycle fixtures observe their own deliberately fixed arenas only. | PS2 memory placement or D20 full gameplay ownership. |
| Target physical RAM / performance | Separate PCSX2 UI/boot evidence and exact ELF memory audit exist. | D20 target load, campaign simulation, or EE timing. |

No savings may be subtracted from the static lower bound until the same D20 workload demonstrates parity and the complete replacement bytes, metadata, staging, transitions and simultaneous pinning are charged. The existing campaign capacity audit’s fixed-owner lower-bound failure remains separate from this experiment ([`m2-d20-live-set-next-experiment-audit.md`](m2-d20-live-set-next-experiment-audit-2026-10-21.md#L53-L80)).

## Commands and present verification

The focused tests run during this report:

```sh
python3 -m pytest -q -rs \
  tests/test_ps2_animation_trace.py \
  tests/test_hcu_ce_map_lifecycle.py \
  tests/test_hcu_scenario_bsp_switch.py \
  tests/test_animation_data_ranges.py
```

Result: **11 passed, 3 skipped**. Trace encoder/decoder/source checks and static range tests pass. Both native ILP32 CE execution fixtures were skipped because this environment’s sandbox blocks native ILP32 execution with SIGSYS; the a30 integration fixture was also skipped because `HALO_HCU_M2_PACKAGE_ROOT` and `HALO_HCU_M2_PACKAGE_MANIFEST` were not set. This is not evidence of a runtime pass.

Candidate commands for the next operator once a package profile and unsandboxed host execution are available:

```sh
# Rebuild current schema/profile first; preserve its ELF/manifest and hashes.
python3 tools/hcu_ps2_closure.py --layer all --no-bootstrap-memory

# Recompute static animation ranges against that exact current schema ELF.
python3 tools/audit_animation_data_ranges.py \
  build/retail-maps/decompressed build/hcu-ps2-closure/all/halo-local.elf \
  --output build/m2-artifacts/d20-host-oracle/animation-ranges-current.json

# Build and validate exact D20 package using the converter's documented CLI;
# retain output hashes rather than overwriting historical package fixtures.
python3 tools/pack_retail_ctag_hp2.py --help

# Run after extending the existing lifecycle fixture to select D20 and expose
# a fixture-only catalog; retain executable, link map, trace and owner ledger.
HALO_HCU_M2_PACKAGE_ROOT=build/m2-artifacts/d20-host-oracle/packages \
HALO_HCU_M2_PACKAGE_MANIFEST=build/m2-artifacts/d20-host-oracle/manifest.json \
python3 -m pytest -q -rs tests/test_hcu_ce_map_lifecycle.py
```

The exact package CLI/manifest schema should be read from `--help` and the current converter before use; this report intentionally does not guess unverified flags. Do not run the first two build commands over existing frozen `build/hcu-ps2-closure/all` or historical outputs without copying/retaining their hashes first.

## Go/no-go criteria

The first go/no-go is only whether the extended fixture can load/tear down the real D20 scenario and invoke the desired CE actor/pose workload reproducibly. It is not a capacity or eviction decision. Reject an experiment result if the source tuple is mixed, a source/package hash is missing, the D20 BSP reference set is incomplete, only synthetic animation calls occurred, any trace row dropped, traces-on/off alter gameplay/pose hashes, a lifecycle callback is stubbed without disclosure, or the host-only owner buffers are described as a PS2 budget.

After a complete D20 capture, independently decide whether further owner instrumentation is justified. Even a promising animation locality result does not close M2 Step 8: the full lossless all-map topology, collision/render data ownership, resident CE pointer contract, all-owner transition high-water, unchanged reserve, target placement, and EE performance gates remain open. Keep gameplay-map admission closed until those gates are satisfied.
