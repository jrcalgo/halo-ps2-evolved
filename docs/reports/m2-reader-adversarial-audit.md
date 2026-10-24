# M2 Step 5 — reader and catalog adversarial-coverage audit

Audit date: 2026-10-21  
Scope: report-only inspection of the current Step 5 all-map host C matrix, production parsers/validators, and adjacent failure tests. This report does not modify parser behavior or close Step 5. The primary positive-corpus evidence and its limits are also recorded in [`m2-step5-c-reader-matrix-audit.md`](m2-step5-c-reader-matrix-audit.md#implementation-follow-up-2026-10-21).

## Finding

The present test set has unusually good breadth for *valid package coverage*: it sends all 24 audited map packages through production HP2/HMAP/CRNG/CBIX readers and all 82 CBSP envelopes through the PS2 C reader under ASan/UBSan. It also has a compact set of parser-negative cases spread among unit and service tests. It is not yet an adversarial matrix for the composition of these readers. Several important negative assertions exist only against Python encoders/decoders, while the C runtime parser is exercised on valid retail data; a few direct C negatives exist, but do not cover the generic CBIX/CRNG invariants or transactional service state.

The highest-risk missing seam is a C-level, single-package mutation harness which recomputes the enclosing HP2 section CRC after mutating inner metadata. That makes the test reach the intended HMAP/CRNG/CBIX/CBSP semantic validator instead of being rejected by the outer HP2 CRC first. The second highest-risk gap is cross-validation between the actual `scnr` structure-BSP reference block and the static catalog/CBIX order: current all-map verification checks scenario tag class/index/name, then separately checks catalog BSP extents and payload source extents, but never reads and compares the scenario’s BSP references.

## Current positive path and proven scope

`tests/test_hcu_map_catalog.py:54-105` requires an explicit package root and manifest, requires 24 maps and 82 BSPs, checks the exact `.hp2` stem set, and compares each file size and SHA-256 with that manifest. It compiles the matrix against production parent readers plus the halo-ps2 HP2 parser and HCU PS2 CTAG/CBSP decoders, with `-Wall -Wextra -Werror -fsanitize=address,undefined` (`tests/test_hcu_map_catalog.py:82-103`).

`tests/hcu_map_catalog_package_matrix_main.c:101-159` opens each package, checks package name, checks its scenario datum is an `scnr` and that the resolved name equals the catalog’s scenario path, validates actual HMAP, CRNG, and CBIX records, and opens every catalog BSP payload via `ps2_cbsp_open`, comparing embedded source offset/size with the expected static record. The loop and aggregate assertions require 24 maps and 82 BSPs (`tests/hcu_map_catalog_package_matrix_main.c:161-188`). Case-insensitive uniqueness is checked for catalog map/map-path/package-path/scenario-path strings at lines 169-182.

This is strong valid-input evidence and provides sanitizer coverage on those paths. It does not establish behavior on malformed package inputs, EE memory fit, target storage semantics, CE global rollback, or rendered output. Assertions are appropriate for this developer fixture, but the harness needs to make the intentional mutation/rejection cases explicit rather than treating the positive loop as a fault matrix.

## Coverage already present

### Outer HP2 envelope and decompression

- `tests/test_hp2_header_fault_matrix.py:50-74` compiles the production halo-ps2 `hp2_open_header()` and tests truncated section table, nonzero reserved table word, duplicate section tags, overlapping payload extents, unknown codec, and extent beyond file.
- `tests/test_ctag.py:98-154` exercises a valid packed package through Python and production HP2 C readers, and corrupts a section body to ensure the enclosing HP2 CRC rejects it.
- `tests/test_hp2_stream_retail.py:13-48` compares the bounded C stream decoder’s output byte-for-byte with Python’s full decode for a large retail CTAG section under sanitizers.
- The HCU source-backed plan notes additional composed service checks for stale HP2 section CRC and a reserved-word fault; see [`plans/7.hcu-remake-m2-m4.md:325`](../../plans/7.hcu-remake-m2-m4.md#L325).

The direct header cases are valuable, but current explicit coverage does not demonstrate exact status and no-output-mutation behavior for every HP2 codec/body truncation boundary, extended LZ4 length boundary, bad section CRC, or zero-length stored/raw combination. Only malformed *header* cases are in the dedicated fault matrix.

### HMAP identity

- `tests/hcu_map_catalog_main.c:84-90` mutates the expected source hash, file length, and payload length, and confirms the catalog validator rejects those cases.
- `tests/test_hmap.py:24-40` checks malformed magic/version/header size/name-tail and invalid path/range at the Python format layer.
- `tests/hcu_map_catalog_package_matrix_main.c:121-124` validates the actual HMAP against each static retail identity in all 24 packages.

Missing direct parent-C cases include wrong expected map name/cross-map identity, each bounds edge (`tag_offset == file_length`, size zero, `offset + size` wrap-shaped values), noncanonical name bytes/padding, version/header-size mutation, and null/invalid arguments. `hmap_open()` has explicit branches for these at `src/stream/hmap.c:13-54`; `hcu_map_catalog_validate_hmap()` adds catalog equality at `src/stream/hcu_map_catalog.c:304-317`. Python parity is useful but is not evidence that all those C branches reject.

### CRNG resource-range index

- `tests/test_ctag_resources.py:16-49` checks Python reader authorization boundaries, wrong expected file/tag identity, bad body CRC, touching/overlapping ranges, tag-region overlap, and out-of-file ranges.
- `tests/test_ctag_resources.py:51-70` compiles the production parent C parser against a valid Python-encoded record.
- `tests/test_ctag_resources.py:72-92` checks one real Blood Gulch audit-derived index and a valid/invalid `allows` query.
- The full-map matrix opens all 24 actual CRNGs with production C and the HMAP bounds (`tests/hcu_map_catalog_package_matrix_main.c:125-127`).

No current direct C negative matrix is apparent for CRNG. `ctag_resource_index_open()` performs careful checks for header/version/size, count/record arithmetic, file/tag identity, CRC, sorted non-overlapping records, tag overlap, and file bounds (`src/stream/ctag_resource_index.c:18-61`). `open_discover()` reparses header identity (`:64-75`), and query functions perform their own read-bound checks (`:78-144`). All those rejection paths should be tested through C, not inferred from equivalent Python checks. Especially high risk: a count that is arithmetically plausible but makes `size != header + count*record`, equal/touching interval boundaries, interval endpoint overflow, zero count, malformed reserved word, and a validly resealed CRNG with one changed interval.

### CBIX/BSP catalog

- `tests/hcu_map_catalog_main.c:92-97` mutates one expected row’s section tag, recomputes the CBIX body CRC, and confirms `hcu_map_catalog_validate_bsp_catalog()` rejects it.
- `tests/test_cbsp.py:35-64` checks Python catalog encode/decode and that the production C catalog reader accepts one valid fixture.
- `tests/test_cbsp.py:76-116` tests Python CBSP corruption/checksum, invalid domain, bad target, address/alignment/overlap/string bounds, and source extent.
- `tests/test_cbsp.py:118-146` compares valid Python materialization with the PS2 C decoder and checks one corrupted-image checksum rejection.
- `tests/test_cbsp.py:205-249` tests cache lookup constrained to expected CBSP extents and checks a source/tag overlap case.
- The all-map matrix validates all actual CBIX records and payload source extents (`tests/hcu_map_catalog_package_matrix_main.c:129-152`).

`cbsp_catalog_open()` validates CBIX header/version, exact count and byte size, expected source file length, header size/reserved word, body CRC, sorted/non-overlapping in-file extents, printable unique tags, and reserved tags (`src/stream/cbsp_catalog.c:23-63`). However the direct C negative surface is essentially one *catalog-specific tag mismatch*. Python tests rejecting overlapping catalog rows do not exercise the C reader. Missing C negatives include wrong file length; zero/too-large count; truncated/extra row; offset+length overflow/past file; unsorted, overlapping, or zero-length extents; duplicate/reserved/nonprintable tags; nonzero reserved/header bytes; and a body mutation with recomputed CRC to reach each semantic branch. `cbsp_catalog_find()` should also be tested for non-exact offset, wrong size, and empty request (`src/stream/cbsp_catalog.c:66-89`).

For `ps2_cbsp_open()`, direct runtime negatives include checksum corruption, with more extensive materialization negative checks in Python. The production PS2 decoder’s C-specific format/bounds branches are not all represented by direct C mutations (`submodules/halo-ce-universal/port/ps2/src/ps2_cbsp.c:62-119`). In particular, mutate relocation row padding/domain/order/field alignment/field bounds/target equality and source extent metadata while recomputing the inner image CRC as required. Confirm rejection does not publish a partially valid `ps2_cbsp_view` (the function zeroes the view on entry).

### CTAG and package ownership/service

- `tests/test_ctag.py:43-96` covers Python CTAG header/checksum/size/relocation/scenario/target/trailing-byte cases.
- `tests/test_ctag.py:156-194` exercises production PS2 C materialization parity and two C malformed records (bad relocation target and missing relocation), including a recomputed image checksum.
- `tests/test_retail_ui_ctag_mount.py:89-117` mutates actual UI CBIX metadata, reseals outer HP2 section CRC, and checks service rejects before publication; a subsequent service branch tests a reserved HP2 field.
- `tests/test_retail_ui_ctag_mount.py:53-87` and `tests/test_ctag_mount.py` test UI ownership lifecycle, release/reload, and same-process retry under host shims; plan details identify their limited owner snapshots and untested fault boundaries (`plans/7.hcu-remake-m2-m4.md:321-327`).

Positive CTAG decode happens for every package in the matrix through `verify_scenario_tag()` (`tests/hcu_map_catalog_package_matrix_main.c:66-99`), but that helper intentionally checks only scenario datum/index/type/name. Negative CTAG decoder coverage is broad in Python, narrower in C, and some service failures concern lifecycle rather than raw parser faults. Current tests should not be described as a complete adversarial composed-reader matrix.

## Highest-risk gaps and why they matter

1. **Scenario-to-catalog identity/order is not proven.** The C positive matrix reads scenario type/index/name but does not inspect `scenario_structure_bsp_references` or compare each selected path/index with `hcu_map_catalog_entry.bsp_catalog`. The catalog validator separately proves that CBIX matches the static table, and the BSP payload separately proves its own source extent, but those relationships do not prove that CE’s scenario will request the intended `Bxxx` for a given BSP reference. A valid-but-swapped reference or duplicate reference can survive every current Step 5 positive assertion. The original reader audit already calls this out at [`m2-step5-c-reader-matrix-audit.md:106`](m2-step5-c-reader-matrix-audit.md#L106).
2. **C parser negatives are thin for CRNG and CBIX.** Current Python decoder tests do not execute the R5900-bound C parser. A discrepancy in C arithmetic, integer width, order checks, or reserved-field handling could pass the Python suite and the positive real package matrix.
3. **Inner semantic faults need resealed outer envelopes.** A random byte flip often stops at HP2 section CRC, which proves envelope integrity only. Tests must recompute HP2 CRC after changing HMAP/CRNG/CBIX, and recompute the CBSP image CRC after changing CBSP metadata when testing deeper branches. Otherwise the target reader’s intended validation path is not being tested.
4. **Cross-map catalog confusion is insufficiently exercised.** The matrix checks actual pack name and HMAP identity per entry, but the synthetic catalog test does not pass map A’s valid HMAP/CBIX under map B’s entry. Cross-map confusion matters because a stale or wrong package at a valid path must fail before a cache/source owner is published.
5. **Negative tests do not consistently assert state invariants.** A parser’s rejection is necessary but composed service acceptance also requires no file source/mount/cache/BSP owner, no arena cursor/high-water change where applicable, closed descriptors, and a successful subsequent valid retry. Those service-level invariants exist for selected L0-L3 failures; they are not universal across the parser fault classes, and the guest `scenario_unload` / global rollback path remains a separate M2 lifecycle gap.

## Recommended compact next implementation slice

Keep the all-map positive corpus unchanged. Add one dedicated **production-C reader fault corpus** using a tiny synthetic package builder and the existing file-level reader APIs; do not multiply mutations across 24 huge retail packages. Every case should be named and should target exactly one layer:

| Layer | Minimum mutations (reseal outer/inner CRC as noted) | Expected proof |
|---|---|---|
| HMAP | cross-map HMAP; wrong length/range; invalid canonical name/padding; truncation | `hmap_open`/catalog validator rejects; output identity not consumed |
| CRNG | wrong expected identity; count/size mismatch; unsorted/touching/overlap; tag overlap; out-of-file/overflow interval; bad reserved/CRC | production `ctag_resource_index_open` rejects; query still denies zero/out-of-range/partial interval reads |
| CBIX | wrong expected file length; count/size mismatch; zero/duplicate/reserved/nonprintable tag; unsorted/overlap/out-of-file extent; reserved word; bad CRC | production `cbsp_catalog_open` rejects; `find` rejects wrong offset/size |
| CBSP | bad source extent; nonzero row padding; invalid domain; unsorted/duplicate/misaligned/out-of-range field; image/target mismatch | `ps2_cbsp_open` rejects with view zeroed; valid control still opens |
| HP2 composition | inner HMAP/CRNG/CBIX semantic mutation with the containing HP2 section CRC recomputed; actual section CRC mismatch; truncated LZ4 body/length extension | prove inner layer reached (semantic rejection) versus outer layer rejection (CRC/codec) using status/asserted validation call |
| Service transaction | inject one representative preflight failure before owner publication and one late resource read failure; snapshot arena, descriptor, source/mount/cache/staged-owner state; then valid retry | fail-closed state equals baseline, no leak, same-process valid retry succeeds |

The harness should avoid hidden dependencies on assert-only evaluation: compile without `NDEBUG`, make every case print/return a named failure, and use explicit bounds checks in the fixture builder before writing mutation offsets. Use ASan/UBSan and run the existing Python-format parity tests in the same pytest invocation. Keep exact status expectations per parser where stable; where the service deliberately folds parser details, assert the service error class and the complete pre/post owner snapshot rather than raw enum numbers.

### Test seams / source locations

- A shared mutation helper can operate on tiny in-memory wire records. It should use production `hp2_crc32()` from `submodules/halo-ps2/engine/src/stream/hp2.c:8-15` to reseal CBIX/CRNG bodies, and a local/reference CRC implementation matching `ps2_cbsp.c:34-46` for the CBSP image CRC.
- HMAP test seam: `hmap_open()` and `hcu_map_catalog_validate_hmap()` at `src/stream/hmap.c:26-55` and `src/stream/hcu_map_catalog.c:304-317`.
- CRNG seam: `ctag_resource_index_open()`/`open_discover()` and authorization calls at `src/stream/ctag_resource_index.c:18-144`.
- CBIX seam: `cbsp_catalog_open()`/`find()` at `src/stream/cbsp_catalog.c:23-89`; catalog binding at `src/stream/hcu_map_catalog.c:319-333`.
- CBSP seam: `ps2_cbsp_open()` at `submodules/halo-ce-universal/port/ps2/src/ps2_cbsp.c:62-119`, with existing parity harness `tests/ps2_cbsp_main.c` and Python builder in `tests/test_cbsp.py:118-146`.
- Package/service seam: use the existing composed fixture in `tests/test_retail_ui_ctag_mount.py:89-117` as the model for mutating an actual package while preserving outer section CRC. Avoid expanding that large test with every low-level parser case; keep one service-level state invariant case here and put per-parser checks in a standalone C executable/test wrapper.
- Scenario cross-reference seam: extend the schema/retail audit path rather than hard-coding offsets. `tools/ctag_schema_walk.py` and `tools/audit_ctag_retail_maps.py` already know schema-defined structures and source tag identity; produce an audited mapping from each scenario’s ordered structure-BSP reference path to its source file extent/catalog tag, then make the package matrix compare that mapping. The current package helper’s explicit limited scope is `tests/hcu_map_catalog_package_matrix_main.c:66-99`.

## Acceptance recommendation

Call the current result **all-map positive C reader/catalog validation with selected negative coverage**, not “full adversarial matrix” and not complete Step 5. The next compact gate should require: (a) exact positive corpus stays 24/24 and 82/82; (b) at least one direct C negative for every HMAP/CRNG/CBIX/CBSP parser invariant class listed above, with resealed checksums where relevant; (c) all-map scenario-reference order/path mapping is corroborated against the source stock tags; and (d) representative composed-service rejection returns to the full owner baseline and permits a valid same-process retry. This still does not close Step 5’s separate capacity, guest gameplay-map, target-device, or rendering criteria.

No tests were executed for this report-only audit. Findings come from source and test inspection; implementation and verification are intentionally left to the main agent.
