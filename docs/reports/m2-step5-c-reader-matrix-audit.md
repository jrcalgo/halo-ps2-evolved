# M2 Step 5: package-derived C reader matrix audit

**Scope:** report-only review of the current M2 Step 5 catalog and package readers. This proposes the smallest test-only addition that exercises the actual production C readers against every real HP2 package and every CBIX/CBSP row. No source or plan files were changed for this audit.

**Snapshot identity:** parent `70e2ed0cf2145a45d23aa07414a3a88c05155d4c`, HCU `6933490b2d16bb1c637295b6a0f3880ba23a7d56`, halo-ps2 `71183bb0a9adc586cd267b2780c82bbc12cfd95b`; working tree is dirty. The catalog and tests must additionally be identified by content hashes at implementation time; these commit pins alone do not identify dirty files.

## Finding

The production catalog has 24 retail map identities and 82 source BSP records, and its validators are real, useful C gates. The current C test suite does **not** establish that all 24 independently generated packages pass those gates. `tests/hcu_map_catalog_main.c` synthesizes HMAP and CBIX bytes directly from each catalog row, then feeds those bytes back into the matching validators. `tests/hcu_map_catalog_package_main.c` exercises actual HP2 package bytes, but only for UI and Blood Gulch. The all-map package audit is a Python reader/auditor; it cannot substitute for C parser execution. This is the exact missing test boundary called out in Step 5: [`plans/7.hcu-remake-m2-m4.md:494-498`](../../plans/7.hcu-remake-m2-m4.md#L494).

Recommended next slice: add a distinct host-only package-matrix test that reads actual package sections through the bounded HP2 C visitor, then invokes HMAP, CRNG, CBIX, and CBSP production C parsers against all 24 catalog entries and all 82 BSP records. Keep `src/stream/hcu_map_service.c` and production catalog data unchanged. The test should consume an explicit package directory and freshly generated package-audit manifest; it should fail closed on any missing map, duplicate identity, hash mismatch, or row-count mismatch.

This closes a *reader/catalog evidence gap only*. It does not prove scenario-tag references, transactional map/BSP publication, PS2 target file I/O, M2 arena fit, CE map load, or visible rendering.

## Current code and tests

### Catalog and C validation entry points

- [`src/stream/hcu_map_catalog.h:9-39`](../../src/stream/hcu_map_catalog.h#L9) defines the fixed metadata record and public enumeration, name lookup, HMAP validator, and CBIX validator.
- [`src/stream/hcu_map_catalog.c:7-12`](../../src/stream/hcu_map_catalog.c#L7) says the table was generated from the pinned retail audits. `s_bsps[]` contains the 82 rows at lines 13-96; `s_maps[]` contains the 24 map entries beginning at line 98. `hcu_map_catalog_count/at/find` are at lines 281-302. Map aliases accept exact leaf or canonical scenario path and normalize slash direction only; they do not synthesize arbitrary paths.
- [`hcu_map_catalog_validate_hmap`](../../src/stream/hcu_map_catalog.c#L304) compares parsed HMAP map leaf, decompressed source length, tag extent, and source SHA-256 to the catalog identity.
- [`hcu_map_catalog_validate_bsp_catalog`](../../src/stream/hcu_map_catalog.c#L319) validates a parsed CBIX count and requires each expected offset/length/tag; the count equality prevents extra records.
- [`src/stream/cbsp_catalog.c:23-63`](../../src/stream/cbsp_catalog.c#L23) parses CBIX v1 and checks header/version, count, expected original file length, exact record byte length, CRC, reserved bits, in-file sorted extents, unique printable section tags, and reserved-tag exclusion. `cbsp_catalog_find` does exact offset/size lookup at lines 66-89.
- [`src/stream/ctag_resource_index.c:18-61`](../../src/stream/ctag_resource_index.c#L18) parses CRNG v1 against expected source length and HMAP tag extent, exact record count/length, checksum, ordered nonempty file intervals, source bounds, and no overlap with the tag-data extent. The `allows`, `overlaps`, and read-gate functions are at lines 78-139.
- [`src/stream/hmap.c:26-60`](../../src/stream/hmap.c#L26) parses HMAP v1, exact 72-byte shape, canonical map leaf, source length, tag range, and SHA bytes. The catalog wrapper adds the pinned-identity comparison.
- [`submodules/halo-ce-universal/port/ps2/include/ps2_cbsp.h:19-41`](../../submodules/halo-ce-universal/port/ps2/include/ps2_cbsp.h#L19) defines a view-based, allocation-free CBSP reader API. [`ps2_cbsp_open`](../../submodules/halo-ce-universal/port/ps2/src/ps2_cbsp.c#L62) validates each complete CBSP envelope, image signature/checksum, source extent metadata, relocation-table shape/order/domains, and target bounds. A matrix can call it on each actual BSP section and compare the embedded source extent against its CBIX row without materializing a BSP or allocating EE memory.

### Existing package fixtures and the present gap

- [`tests/hcu_map_catalog_main.c:18-52`](../../tests/hcu_map_catalog_main.c#L18) makes HMAP and CBIX records using the very catalog values under test; `main` loops across 24 records at lines 54-82. These are good self-consistency and malformed-input tests, but not independent package evidence.
- [`tests/hcu_map_catalog_package_main.c:29-70`](../../tests/hcu_map_catalog_package_main.c#L29) opens actual packages, extracts HMAP and CBIX with full-buffer `hp2_open/hp2_load`, validates catalog matches, and enumerates BSP extents. Its `main` hard-codes only UI and Blood Gulch at lines 73-78.
- [`tests/test_hcu_map_catalog.py:22-49`](../../tests/test_hcu_map_catalog.py#L22) compiles the production catalog/HMAP/CBIX C code and runs the synthetic test. Its second test conditionally uses just two package files (UI and Blood Gulch), then skips if either is absent.
- The existing bounded-reader fixture compiles the actual halo-ps2 section visitor with ASan/UBSan: [`tests/test_world_section_visitor.py:31-54`](../../tests/test_world_section_visitor.py#L31). It currently checks UI, Longest, and Blood Gulch packages where available, and hashes those fixed artifacts; it does not connect the visitor to HCU catalog, CRNG, or CBSP validation for the full map corpus.
- [`tools/audit_retail_cbsp_catalogs.py:23-74`](../../tools/audit_retail_cbsp_catalogs.py#L23) audits every same-stem package in Python, opens each CBIX/CBSP, checks CBSP-embedded source extents against audited stock BSP references, and reports 24 maps / 82 BSP entries. The script itself expressly disclaims memory-fit/runtime claims. It is the correct independent package-generation audit to pair with the C matrix, not a replacement for it.

## Exact corpus and provenance that can be used now

The current worktree contains 24 decompressed retail map sources under `build/retail-maps/decompressed/*.map` and 24 freshly rebuilt HP2 packages under `/tmp/hcu-m2-capacity-repro.P5qdmI/packages/`. The latter are real usable package inputs *now*, but `/tmp` is temporary and must not become an implicit long-term fixture contract.

The fresh package audit is `/tmp/hcu-m2-capacity-repro.P5qdmI/retail-cbsp-catalog-package-audit.json`, SHA-256 `e4a9721846db228b88e6a563c34c0dccc7c6dc7694cf5a393d66c67ca004503b`. It reports `map_count=24`, `bsp_count=82`, total package bytes `299,022,336`, and total CBSP payload bytes `349,869,456`. [`docs/reports/m2-next-capacity-design-review.md`](m2-next-capacity-design-review.md) lines 170-184 records the same package rebuild, exact audit SHA, source pins, retail-map provenance, and the critical stale-report warning.

Do **not** pair those fresh packages with [`docs/reports/retail-cbsp-catalog-package-audit-current.json`](retail-cbsp-catalog-package-audit-current.json) as their package-hash manifest. The retained JSON SHA is `f4fa3b7fbe8e9f0d80379a72653522a6e8162da1ad21f7d2546cbc66009588fb`, while the fresh `/tmp` audit hash is `e4a972…`; according to the design-review addendum, the old and fresh reports agree on all 24 source hashes and BSP counts, but none of the 24 package hashes match. It cites Blood Gulch as one example: fresh package SHA `ded2bca19058f51d7feed6b40149f421f7b1c2c7704f0918a42bacc5601dd011`, versus historical `a4c878…`. Preserve both historical evidence and regenerate a hash-specific manifest for whichever package set is actually tested. Do not overwrite current reports in place.

Additional stable package evidence useful for smoke/visitor parity:

- UI package hash and section sizes are pinned in [`tests/test_world_section_visitor.py:12-16`](../../tests/test_world_section_visitor.py#L12).
- Longest's all-BSP package is pinned there at lines 17-20; the freeze report [`docs/reports/m2-longest-artifact-freeze.md`](m2-longest-artifact-freeze.md) binds its schema ELF, map, package and section extents.
- Blood Gulch's current all-BSP package is pinned in the same test at lines 21-24 and its fresh package hash is also recorded in the capacity report.

For a durable test, regenerate the package set into a unique temporary directory (or a new explicitly named, hash-addressed artifact directory), invoke `tools/audit_retail_cbsp_catalogs.py` with a new output path, then run the C matrix on precisely that output directory. The wrapper must pass package root and audit-manifest paths explicitly; never silently pick up a stale `build/` or `/tmp/` directory.

## Proposed test-only implementation (no production changes)

Add two uniquely named files, keeping the existing tests intact:

1. `tests/hcu_map_catalog_package_matrix_main.c`: host-only C test executable. It links the production readers and takes `--package-root` plus an expected-manifest/map-set input (or receives an already verified exact list from the Python wrapper). It enumerates `hcu_map_catalog_at(0..23)` and accesses each canonical basename from `entry->hp2_path`; it must not concatenate untrusted paths or modify production roots.
2. `tests/test_hcu_map_catalog_package_matrix.py`: orchestration fixture. It creates an isolated temporary output directory, runs the existing/standard retail pack-generation commands against all 24 source maps, generates a *fresh* package audit JSON via `tools/audit_retail_cbsp_catalogs.py`, verifies manifest map names/counts/source hashes/package hashes, compiles the C matrix with strict warnings and sanitizers, then runs it on that exact package directory. This file should identify its inputs/source pins and never rewrite retained audit JSON or packages.

### C reader sequence for each map

1. Enumerate the 24 production entries. Before opening packages, assert unique canonical leaves, unique normalized `maps/<leaf>.hp2` paths, and a total `sum(entry->bsp_count) == 82`. Compare exact leaf set and per-map BSP counts against the fresh manifest. Require exactly 24 entries on both sides—no missing, extra, or duplicate maps.
2. For each map, read the package through the bounded section-reader API, preferably one open reader across serialized passes: [`world_visit_section_reader_with_scratch`](../../submodules/halo-ps2/engine/src/world/section.h#L24) avoids reopening and documents caller ownership; [`world_visit_section_with_scratch`](../../submodules/halo-ps2/engine/src/world/section.c#L63) is simpler but opens/closes per section. A sink should append each callback span at its supplied offset into host-only dynamic buffers, reject offset discontinuity/overflow, and publish the buffer only after `HP2_OK`. The API uses reusable decoder memory and a shared static header and is explicitly synchronous/non-reentrant at [`section.h:12-19`](../../submodules/halo-ps2/engine/src/world/section.h#L12); keep the entire matrix single-threaded and never retain callback pointers.
3. Visit actual `HMAP`, `CRNG`, and `CBIX` package sections; assert their sizes and validate them with `hcu_map_catalog_validate_hmap`, `ctag_resource_index_open`, `cbsp_catalog_open`, and `hcu_map_catalog_validate_bsp_catalog`. Use catalog HMAP identity fields as CRNG expected length/tag bounds. Assert 24 successful HMAPs, 24 CRNGs, 24 CBIXs.
4. For each CBIX row, resolve the exact expected catalog record with `cbsp_catalog_find`; check offset, size, and four-byte tag. Visit that actual tag section from HP2, call `ps2_cbsp_open` with a reviewed host safety cap (not a guessed production arena size), then require its `source_file_offset/source_file_size` exactly equal the CBIX row. This makes the C path execute all **82** actual CBSP payload readers, not just count catalog records.
5. For each CRNG row, exercise positive and negative authorization at boundary points derived from the wire record: full interval, last byte, one-byte crossing past end, first byte before/after an interval where in-file, tag-data overlap, zero-size, and out-of-file/overflow request. Add a fake source callback counter to prove rejected reads never reach the source. Existing interval parser checks are useful but do not prove each of 24 independently packaged CRNGs passed C parsing.
6. Track callback raw byte counts and package-level results. Final machine-readable summary must state `maps=24`, `hmap=24/24`, `crng=24/24`, `cbix=24/24`, `cbsp=82/82`, plus per-map package SHA, HMAP source SHA, BSP count and section tag list. Compare these to the just-generated Python audit before passing.

The visitor implementation and key lifetime/cleanup contract are explicit in [`submodules/halo-ps2/engine/src/world/section.h:12-32`](../../submodules/halo-ps2/engine/src/world/section.h#L12) and [`section.c:63-139`](../../submodules/halo-ps2/engine/src/world/section.c#L63): scratch is leased/released per section, and partial sink output may arrive before later decode/CRC failure. The proposed C collector is therefore test-only and must discard its output on every non-`HP2_OK` return. Host `malloc` is allowed only in the test harness, not in the EE loader or in any memory-fit argument.

### Compile/test target composition

The existing package test wrapper provides a useful starting compile recipe at [`tests/test_hcu_map_catalog.py:9-19`](../../tests/test_hcu_map_catalog.py#L9). The new matrix will need:

- `tests/hcu_map_catalog_package_matrix_main.c`
- `src/stream/hcu_map_catalog.c`, `src/stream/hmap.c`, `src/stream/cbsp_catalog.c`, and `src/stream/ctag_resource_index.c`
- `submodules/halo-ps2/engine/src/world/section.c`, `core/mem.c`, `stream/hp2.c`, and `stream/file.c`
- `submodules/halo-ce-universal/port/ps2/src/ps2_cbsp.c`

Include paths should match existing engine/HCU test conventions; `world/section.c` currently uses the PS2 engine source and HP2 test shim in [`tests/test_world_section_visitor.py:31-43`](../../tests/test_world_section_visitor.py#L31). Compile with `-std=c11 -Wall -Wextra -Werror`; use ASan/UBSan on hosts where available. Keep output binary in a temporary/build test location, not a tracked fixture.

### Negative and adversarial cases

The baseline success matrix should be followed by isolated-copy mutations (never mutate the hash-pinned baseline package set):

- missing package, extra package, duplicate manifest map, duplicate normalized path, mismatch in source hash, mismatch in package hash, wrong basename/package internal name;
- truncated HP2 header/directory and section payload; malformed compression output; callback failure after a valid prefix; bad HP2 section CRC;
- HMAP name/source hash/file length/tag offset/tag size changed independently;
- CRNG bad version/header size/count/body length/CRC/reserved field, unsorted/overlapping/zero/out-of-file range, and range overlapping tag data;
- CBIX bad version/count/record length/CRC, duplicate/reserved/nonprintable tag, duplicate/out-of-order/overlapping/overflow/out-of-file extent, unknown/missing/extraneous expected row;
- CBSP truncation, wrong signature, image CRC, wrong embedded source extent, relocation bounds/order/padding/domain/target mismatch;
- visitor early sink rejection and late decode failure must discard all collected section bytes and close the file lease; the next package must still pass.

The matrix should not multiply every mutation across 24 maps if expensive; one adversarial corpus per parser plus positive package-derived coverage across all maps is acceptable. Ensure at least each map's actual package, each CRNG, every CBIX record, and all 82 CBSP sections are traversed in the positive path.

## Acceptance and remaining dependencies

### Acceptance for this test slice

- Fresh package audit identifies exactly the 24 catalog leaves and `82` total BSP rows; its source hashes agree with HMAP identities and its package hashes match the bytes opened by C.
- Every real package passes `HP2` bounded reads, HMAP catalog identity validation, CRNG parser validation, CBIX parser/catalog validation, and all associated CBSP C payload validation.
- Mutated inputs fail closed, sink outputs from failed visits are not treated as valid, and no test rewrites retained package/report evidence.
- Strict warning/sanitizer build and focused test pass. The report records exact generated manifest SHA, all package SHA-256s or an immutable manifest of them, and the exact parent/HCU/halo-ps2 working-tree/source hashes.

### What remains outside this matrix

- **Scenario tag/BSP reference agreement:** the static `scenario_bsp_path` strings are catalog metadata, and CBIX extent parity alone cannot prove the actual stock `scnr` tag names/ordering agree with them. Add/retain a separate source-tag audit that extracts every map's scenario references and compares canonical paths plus selected index/order with the 82 package rows. Step 5's desired “scenario tag validation” is not satisfied by this proposed test by itself.
- **C production mount/rollback:** this matrix validates formats and reader outputs, not publication into cache/tag globals, failure rollback, lifecycle transition, or arena cursors. Those remain Steps 6-8 and existing host/guest lifecycle evidence.
- **Capacity:** counts and hashes do not show CTAG+BSP+renderer+animation+staging peak fits within fixed PS2 regions. No arena-size change is proposed here.
- **Guest and display:** host C tests are not R5900 execution, PCSX2 scenario load, or rendering proof.

## Recommended work order

1. Rebuild or re-verify the full 24-package corpus from the current 24 source maps in an isolated directory; run the Python all-package audit to a new output path.
2. Implement only the two new test files and test helper glue. Do not modify the catalog table, production `map_leaf` gate, package format, arena sizes, plan, or current reports as a side effect.
3. First make positive package-derived validation pass for 24/24 maps and 82/82 CBSP sections; then add a compact adversarial matrix for parser failure boundaries.
4. Run the preexisting `tests/test_hcu_map_catalog.py`, `tests/test_world_section_visitor.py`, and the new matrix. Confirm one test is not accidentally skipping due to absent artifacts.
5. Preserve this matrix as Step 5 acceptance evidence while continuing to label map fit, CE load, and visible output as unproven until their separate gates pass.

## Implementation follow-up (2026-10-21)

The proposed positive all-map host C-reader slice has now been implemented in [`tests/hcu_map_catalog_package_matrix_main.c`](../../tests/hcu_map_catalog_package_matrix_main.c) and wired into [`tests/test_hcu_map_catalog.py`](../../tests/test_hcu_map_catalog.py). The test compiles the production HP2 section reader, HMAP, CRNG, CBIX, CBSP, and HCU catalog readers with host sanitizers, opens the exact actual package files listed by the catalog, and verifies scenario datum/name identity plus the 24 HMAP, 24 CRNG, 24 CBIX and 82 CBSP records. It also checks catalog map/path/scenario-name uniqueness case-insensitively and validates the package audit manifest against the bytes it opens.

The fresh package audit is retained as [`retail-cbsp-catalog-package-audit-e4a97218.json`](retail-cbsp-catalog-package-audit-e4a97218.json), SHA-256 `e4a9721846db228b88e6a563c34c0dccc7c6dc7694cf5a393d66c67ca004503b`; it binds 24 packages, 82 BSP rows, 299,022,336 package bytes and 349,869,456 aggregate CBSP payload bytes. The exact package directory used for this run was `/tmp/hcu-m2-capacity-repro.P5qdmI/packages`; it is intentionally supplied explicitly rather than discovered implicitly. Verification command:

```sh
HALO_HCU_M2_PACKAGE_ROOT=/tmp/hcu-m2-capacity-repro.P5qdmI/packages \\
HALO_HCU_M2_PACKAGE_MANIFEST=docs/reports/retail-cbsp-catalog-package-audit-e4a97218.json \\
python3 -m pytest -q tests/test_hcu_map_catalog.py
```

Result: **3 passed in 23.92 s**. The focused adjacent parser/service regression also passed: **14 passed, 6 subtests passed in 7.40 s** across `test_retail_ui_ctag_mount.py`, `test_cbsp.py`, `test_ctag_mount.py`, `test_world_section_visitor.py`, and `test_hp2_header_fault_matrix.py`.

This closes the report's previously proposed positive all-map parser-coverage gap, with a scope refinement: the current matrix proves package-derived parser/catalog identity and all 82 CBSP payload readers, not every mutation listed in the proposed adversarial matrix. Scenario BSP reference ordering/path agreement against stock retail scenario tag contents is also still open; comparing HMAP scenario name and CBIX extents does not establish that relationship. These tests are host-only and do not prove physical EE memory placement, capacity, production mount rollback, CE gameplay-map load, or GS-visible rendering. The original report above remains as the audit's design history; this dated addendum records what is now implemented and what remains.
