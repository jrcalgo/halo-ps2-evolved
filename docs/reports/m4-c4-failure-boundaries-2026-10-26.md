# M4 C4 item 5: failure boundaries and fault injection (2026-10-26)

Scope: PS2 CBSP load/publication path (parse, section directory, decode+CRC, relocation rows, materialize/rebase, owner capacity, streamed upload, CE publication, late publication). Host-only; no PCSX2 or guest runs; no production behaviour changed.

## Result

Every boundary x fault-class cell is classified. No cell remains MISSING. New injected cases (tests/c4_bsp_fault_harness_main.c, tests/test_c4_bsp_fault_injection.py) cover the decoder rows that previously had no C-level injection: counts, truncation, table/image overlap, capacity, row-level references and domains, and partial relocation at a late row. Every injected case asserts: classified status, previously published image byte-identical, candidate/neighbour guards intact, and a clean retry reproducing the Python oracle bytes.

Cell counts: covered-by-new-injection (I) 24, covered-by-existing (C) 11, equivalence (E) 6, historical not re-run (H) 0, blocked (B) 1, not applicable (N) 48.

Legend: I = new C4 injected case (passing); C = existing test or fixture, passing this session (file:line); E = equivalence (reason given); B = blocked (reason given); N = not applicable (reason given); H = historical only.

## Matrix (code only; evidence in the per-boundary list below)

| Boundary | FC1 | FC2 | FC3 | FC4 | FC5 | FC6 | FC7 | FC8 | FC9 | FC10 |
|---|---|---|---|---|---|---|---|---|---|---|
| B1 header parse/validate | N | N | I | I | E | N | I | N | N | N |
| B2 section directory (count, table offset/size, source extent) | I | N | N | I | I | I | N | N | N | N |
| B3 per-section decode + CRC (image size, psbs magic, CRC) | N | N | N | I | N | I | I | N | N | N |
| B4 relocation rows (field alignment/order, domain, padding, target match) | N | I | I | N | E | N | E | I | N | N |
| B5 relocation writes: materialize/rebase (CTAG strings, address range, destination size) | N | C | C | N | I | I | N | I | N | N |
| B6 owner allocation / capacity (BSP cache, max image, max relocs) | N | N | N | N | N | I | N | N | N | N |
| B7 streamed upload / cache read (sink, visitor, rebase, normalization) | E | E | I | I | E | I | I | I | I | N |
| B8 CE publication (scenario_switch_structure_bsp: schema, verifier, global publish, rollback) | N | C | C | C | N | C | C | C | C | C |
| B9 late publication/commit (candidate write after publish, owner unload, renderer bind) | N | N | N | N | N | I | N | N | C | B |

Fault classes: FC1 malformed counts; FC2 malformed references; FC3 malformed domains; FC4 truncated sections; FC5 overlapping ranges; FC6 insufficient capacity; FC7 decode/CRC errors; FC8 partial relocation; FC9 upload failure; FC10 late publication failure.

## Boundary evidence

### B1: header parse/validate

Source: ps2_cbsp.c:76-150 (open_parts header), ps2_cbsp.c:153 (open), ps2_cache.c:458 (mount)

- FC1 malformed counts: **N** header has no count fields; counts are checked at B2
- FC2 malformed references: **N** no references in the header
- FC3 malformed domains: **I** reserved_header_nonzero W -> FORMAT (ps2_cbsp.c:115); in tests/test_c4_bsp_fault_injection.py
- FC4 truncated sections: **I** truncated_header (W) and truncated_header_stream (S) -> TRUNCATED; tests/test_c4_bsp_fault_injection.py. Also tests/ps2_cache_cbsp_main.c:171-176 rejects bad payloads via ps2_cache_mount_cbsp (passed)
- FC5 overlapping ranges: **E** header/image overlap uses the same range_overlaps check as table overlap (ps2_cbsp.c:112-114); header is a separate span in every caller, so no injected case
- FC6 insufficient capacity: **N** header size is fixed at 36 bytes
- FC7 decode/CRC errors: **I** bad_magic and bad_version (W) -> FORMAT; tests/test_c4_bsp_fault_injection.py
- FC8 partial relocation: **N** no relocation in header
- FC9 upload failure: **N** upload is a B7 concern
- FC10 late publication failure: **N** publication is B8/B9

### B2: section directory (count, table offset/size, source extent)

Source: ps2_cbsp.c:153-179 (open), ps2_cbsp.c:97-111 (table sizing)

- FC1 malformed counts: **I** count_plus_one: W -> TRUNCATED, S -> FORMAT (tests/test_c4_bsp_fault_injection.py)
- FC2 malformed references: **N** directory does not hold references
- FC3 malformed domains: **N** directory does not hold domains
- FC4 truncated sections: **I** truncated_table_tail (W TRUNCATED / S FORMAT), trailing_bytes (FORMAT), image_size_inflated (W TRUNCATED / S BOUNDS)
- FC5 overlapping ranges: **I** table_aliases_image: open_parts with table inside image -> OVERLAP (ps2_cbsp.c:113-114)
- FC6 insufficient capacity: **I** count_over_maximum (W,S) -> BOUNDS against maximum relocations (ps2_cbsp.c:99)
- FC7 decode/CRC errors: **N** CRC covers the image only; see B3
- FC8 partial relocation: **N** no relocation writes at this boundary
- FC9 upload failure: **N** upload failure is B7
- FC10 late publication failure: **N** publication is B8/B9

### B3: per-section decode + CRC (image size, psbs magic, CRC)

Source: ps2_cbsp.c:113-125

- FC1 malformed counts: **N** no counts consumed by the section decoder
- FC2 malformed references: **N** no references consumed by the section decoder
- FC3 malformed domains: **N** no domains consumed by the section decoder
- FC4 truncated sections: **I** truncated_image_tail (W TRUNCATED), truncated_image_stream (S TRUNCATED)
- FC5 overlapping ranges: **N** single contiguous section
- FC6 insufficient capacity: **I** image_over_capacity (W,S) -> BOUNDS against bsp cache size; also tests/ps2_cache_cbsp_main.c:171-176 (passed)
- FC7 decode/CRC errors: **I** image_bitflip_crc (W,S) and header_crc_mismatch -> CHECKSUM; image_magic_not_psbs -> FORMAT; source_extent_mismatch (W,S) -> BOUNDS; source_extent_unknown_with_size -> FORMAT. Python oracle equivalence: tests/test_cbsp.py:81-93 (passed)
- FC8 partial relocation: **N** no relocation at this boundary
- FC9 upload failure: **N** upload is B7
- FC10 late publication failure: **N** publication is B8/B9

### B4: relocation rows (field alignment/order, domain, padding, target match)

Source: ps2_cbsp.c:127-149

- FC1 malformed counts: **N** row count is validated at B2
- FC2 malformed references: **I** field_unaligned, field_past_image, rows_unsorted (BOUNDS); reference_target_mismatch (FORMAT); dom0_target_outside_image (BOUNDS)
- FC3 malformed domains: **I** domain_out_of_range (W,S) -> BOUNDS; row_padding_nonzero (W) -> BOUNDS. Python oracle does NOT reject padding (tools/cbsp.py '<IB3xI'); pinned as KNOWN_PYTHON_GAPS in tests/test_c4_bsp_fault_injection.py
- FC4 truncated sections: **N** table truncation is B2
- FC5 overlapping ranges: **E** duplicate field fails the same 'field <= previous' test as rows_unsorted (ps2_cbsp.c:135)
- FC6 insufficient capacity: **N** no capacity at row validation
- FC7 decode/CRC errors: **E** row/image mismatch is a FORMAT check, reached only after CRC passes (see B3 FC7)
- FC8 partial relocation: **I** last_row_target_mismatch_stream: FORMAT on row 4 after rows 0-3 validated; candidate not published
- FC9 upload failure: **N** upload is B7
- FC10 late publication failure: **N** publication is B8/B9

### B5: relocation writes: materialize/rebase (CTAG strings, address range, destination size)

Source: ps2_cbsp.c:181-237 (materialize), 240-315 (rebase)

- FC1 malformed counts: **N** no counts
- FC2 malformed references: **C** bad pointer targets / materialization bounds: tests/test_cbsp.py:95-112 (leaves CTAG, wraps, alignment, NUL) passed; C side tests/ps2_cbsp_main.c:117-137 bad table rows, run by test_ps2_c_decoder_matches_python_materialization (passed)
- FC3 malformed domains: **C** unterminated CTAG string: tests/ps2_cbsp_main.c:144-157 (passed via test_ps2_c_decoder); tests/test_c4_bsp_fault_injection.py late_row_unterminated_tag_* also reject
- FC4 truncated sections: **N** tag image truncation is checked by the CTAG loader, not this boundary
- FC5 overlapping ranges: **I** bsp_tag_address_overlap -> ADDRESS (ps2_cbsp.c:197-198); Python tests/test_cbsp.py:107 passed
- FC6 insufficient capacity: **I** destination_one_short (W) and destination_short_stream (S) -> SPACE
- FC7 decode/CRC errors: **N** CRC is checked before any write (B3)
- FC8 partial relocation: **I** late_row_unterminated_tag_stream and _whole: row 3 of 5 rejected after rows 0-2 valid; S-mode candidate verified unrelocated (raw=1); retry OK
- FC9 upload failure: **N** upload is B7
- FC10 late publication failure: **N** publication is B8/B9

### B6: owner allocation / capacity (BSP cache, max image, max relocs)

Source: ps2_cache.c:458-493 (mount), ps2_cache.c:745-768 (stream)

- FC1 malformed counts: **N** no counts
- FC2 malformed references: **N** no references
- FC3 malformed domains: **N** no domains
- FC4 truncated sections: **N** no truncation at owner
- FC5 overlapping ranges: **N** owner ranges are fixed by the arena; no pointer overlap possible
- FC6 insufficient capacity: **I** owner exhaustion through the production legacy preflight: CTAG relocation owner allocation (site 1, src/stream/hcu_map_service.c:232) and preflight sha256 scratch (site 2, :73), via HCU_C4_FAULT_SEAM (default off). Each fault is rejected with an empty safe state (preflight_ready 0, arenas at their marks, no source/mount open, guard intact), and a clean retry reproduces the clean-load state exactly. tests/test_c4_bsp_fault_legacy.py (3 passed). Reachability: default build leaves WORLD_HCU_PARTITION_PROFILE empty (tools/ee-world.mk:56), so no profile runtime is registered and hcu_map_service_preflight takes the legacy branch (hcu_map_service.c:1459-1461), with the CE hook installed at :1176
- FC7 decode/CRC errors: **N** no decode at owner
- FC8 partial relocation: **N** no relocation at owner
- FC9 upload failure: **N** upload is B7
- FC10 late publication failure: **N** publication is B8/B9

### B7: streamed upload / cache read (sink, visitor, rebase, normalization)

Source: ps2_cache.c:713-779 (stream_cbsp_for_read; open_parts at 745, rebase at 762)

- FC1 malformed counts: **E** S mode runs the same open_parts code as ps2_cache.c:745; count_plus_one_stream -> FORMAT (tests/test_c4_bsp_fault_injection.py)
- FC2 malformed references: **E** S mode runs the same reference checks as B4; last_row_target_mismatch_stream covers the stream path
- FC3 malformed domains: **I** domain_out_of_range_stream -> BOUNDS
- FC4 truncated sections: **I** truncated_image_stream, truncated_table_stream, upload_half_stream, upload_short_one_byte_stream. Also tests/ps2_cache_cbsp_main.c:259-263 bsp_stream_fail_after=80 leaves sentinel, retry restores bytes (passed)
- FC5 overlapping ranges: **E** sink writes table after image with size checks (ps2_cache.c:620-707, cbsp_stream_sink); overlap is impossible by construction and covered by table_aliases_image at B2
- FC6 insufficient capacity: **I** destination_short_stream -> SPACE; image_over_capacity_stream and count_over_maximum_stream -> BOUNDS
- FC7 decode/CRC errors: **I** image_bitflip_crc_stream -> CHECKSUM; source_extent_mismatch_stream -> BOUNDS
- FC8 partial relocation: **I** late_row_unterminated_tag_stream -> BOUNDS, candidate unrelocated; last_row_target_mismatch_stream -> FORMAT. Also tests/ps2_cache_cbsp_main.c:278-283 full stream with malformed final relocation rejected, restored source retried (passed)
- FC9 upload failure: **I** upload_half_stream and upload_short_one_byte_stream; tests/ps2_cache_cbsp_main.c:259-270 (passed)
- FC10 late publication failure: **N** publication is B8

### B8: CE publication (scenario_switch_structure_bsp: schema, verifier, global publish, rollback)

Source: submodules/halo-ce-universal/source/scenario/scenario.c:1101-1204

- FC1 malformed counts: **N** no counts at CE
- FC2 malformed references: **C** CE schema rejects a candidate with bad references: tests/hcu_scenario_bsp_switch_main.c:2586,2608 (non-retail branch, passed via test_hcu_scenario_bsp_switch.py -k 'not retail')
- FC3 malformed domains: **C** CE schema domain rejection, same seam: tests/hcu_scenario_bsp_switch_main.c:2586,2608 (passed)
- FC4 truncated sections: **C** candidate read failure rolls back to previous BSP: tests/ps2_cache_cbsp_main.c:222-236 (passed). Retail counterpart tests/hcu_scenario_bsp_switch_main.c:2369 is skipped in this checkout (open items)
- FC5 overlapping ranges: **N** CE only sees published pointers
- FC6 insufficient capacity: **C** CE port-capacity verifier rejection: tests/hcu_scenario_bsp_switch_main.c:2593-2605 fail_verify_mask (passed). Injected verifier, not a measured capacity
- FC7 decode/CRC errors: **C** corrupted final payload byte is rejected before CE publication and the restored source retries: tests/ps2_cache_cbsp_main.c:278-283 (passed). Retail outer/inner CRC counterpart tests/hcu_scenario_bsp_switch_main.c:2442-2480 is skipped in this checkout (open items)
- FC8 partial relocation: **C** malformed final relocation before publication, retry OK: tests/ps2_cache_cbsp_main.c:278-283 (passed)
- FC9 upload failure: **C** partial/short stream at CE read: tests/ps2_cache_cbsp_main.c:259-270 (passed)
- FC10 late publication failure: **C** late failure after old BSP unloaded, both reads fail -> safe-null and menu: tests/ps2_cache_cbsp_main.c:239-244 (passed); verify/schema after load: tests/hcu_scenario_bsp_switch_main.c:2586-2617 (passed)

### B9: late publication/commit (candidate write after publish, owner unload, renderer bind)

Source: tests/hcu_mp_bsp_failure_atomicity_check.h; src/stream/hcu_map_service.c (not modified)

- FC1 malformed counts: **N** no counts at this boundary
- FC2 malformed references: **N** references validated earlier
- FC3 malformed domains: **N** domains validated earlier
- FC4 truncated sections: **N** truncation validated earlier
- FC5 overlapping ranges: **N** no ranges at this boundary
- FC6 insufficient capacity: **I** same two preflight owner-exhaustion sites as B6 FC6 (both run before CE publication); rollback, canaries and retry asserted by tests/test_c4_bsp_fault_legacy.py (3 passed)
- FC7 decode/CRC errors: **N** decode finished before this boundary
- FC8 partial relocation: **N** relocation finished before this boundary
- FC9 upload failure: **C** candidate B000 write failure with restore and same-process retry: tests/hcu_mp_bsp_failure_atomicity_check.h:26-60, run by tests/test_hcu_mp_wind_package.py (passed)
- FC10 late publication failure: **B** re-verified against the re-derived pin (docs/reports/m4-c4-pin-rederivation-2026-10-26.md): tests/test_hcu_ce_map_lifecycle.py:58 still FAILS. It compares the HCP2 UI manifest field schema_elf_sha256 (build/m2-ce-map-lifecycle-host-hcp2/producer-ui-verified/ui.json) = 1b7e191b... with the current ELF b1d3c7b0... (sha256 of build/hcu-ps2-closure/all-no-bootstrap-memory/halo-local.elf). 1b7e191b... matches no file on disk, and no tool in tools/ writes producer-ui-verified/. The manifest file hash a94a3f2f... and package hash 4ad8b57b... do match the test pins, so the embedded field must change, which changes the manifest hash and so also requires the test pin HCP2_UI_MANIFEST_SHA256 to change. Needed: a producer run (not present in the repo) that regenerates ui.hcp and ui.json against b1d3c7b0, then the producer-generated manifest hash replacing the test pin. No hash was hand-edited

## Commands and results

- `cc -std=c89 -Wall -Wextra -Werror -no-pie -Isubmodules/halo-ce-universal/port/ps2/include tests/c4_bsp_fault_harness_main.c submodules/halo-ce-universal/port/ps2/src/ps2_cbsp.c`: compiles clean
- `python3 -m pytest -q tests/test_c4_bsp_fault_injection.py`: 5 passed, 77 subtests passed
- `PYTHONPATH=submodules/halo-ps2/tools python3 -m pytest -v tests/test_cbsp.py`: 12 passed, 1 skipped (test_ps2_cache_rematerializes_two_exact_retail_cbix_extents: retail package absent)
- `PYTHONPATH=submodules/halo-ps2/tools python3 -m pytest -v tests/test_hcu_scenario_bsp_switch.py -k 'not retail'`: 1 passed
- `PYTHONPATH=submodules/halo-ps2/tools python3 -m pytest -q tests/test_hcu_mp_wind_package.py`: 1 passed
- `python3 -m pytest -q tests/test_c4_bsp_fault_legacy.py`: 3 passed: clean accept, site 1 and site 2 rollback to safe-empty with guard intact, clean retry equals clean state, seam-off build equals seam-on clean run (host-only: HCU_M2_MP_HOST_ORACLE, 16 MiB host tag cache)
- `python3 -m pytest -q tests/test_c4_parity_validators.py`: 3 passed, 13 subtests: pin, wiring, and verbatim validator cases (valid accepted, malformed refused or corrected with rewritten values)
- `python3 -m pytest -q tests/test_c4_bsp_fault_injection.py`: 5 passed, 77 subtests (see above)
- `PYTHONPATH=submodules/halo-ps2/tools python3 -m pytest -q tests/test_hcu_ce_map_lifecycle.py`: 1 failed: HCP2 UI manifest pins a schema ELF hash that does not match build/hcu-ps2-closure/all-no-bootstrap-memory/halo-local.elf (test_hcu_ce_map_lifecycle.py:58); not edited
- `PYTHONPATH=submodules/halo-ps2/tools python3 -m pytest -q tests/test_hcu_scenario_bsp_switch.py`: retail a30/a50 transaction skipped: HALO_HCU_M2_PACKAGE_ROOT/MANIFEST unset and a30.hp2/a50.hp2 not present in this checkout

Per-case harness output is in the JSON file (cases array).

## Open items

- retail a30/a50 CBSP transaction (tests/hcu_scenario_bsp_switch_main.c:2440-2530, 2369): packages not present; this session's runs of those cells are historical
- test_hcu_ce_map_lifecycle.py fails its pinned schema-ELF check (test_hcu_ce_map_lifecycle.py:58); cells B9 FC10 depend on it
- legacy-path fixture is host-only: HCU_M2_MP_HOST_ORACLE admits bloodgulch (hcu_map_service.c:1373) and the host tag cache is 16 MiB; at the production 2 MiB the clean bloodgulch preflight is rejected by the CTAG capacity check (status 8), a real production-capacity finding, not a seam result. The other admitted maps (beavercreek, longest) are likewise CTAG-capacity rejected; the ui map is HCP-profile only
- B9 FC10 pending the schema-ELF pin re-derivation (docs/reports/m4-c4-pin-rederivation-2026-10-26.md not yet present)
- validator descriptors: the three member-exact validator rows pass (docs/reports/m4-c4-parity-validators-2026-10-26.json) with verbatim CE callbacks; the material vertex-buffer and tag-lookup accessors are data stubs that report none, so that path is not driven
- tools/cbsp.py decode ignores relocation-row padding bytes that ps2_cbsp.c rejects (pinned in KNOWN_PYTHON_GAPS)
- owner-canary check is a neighbour region the decoder never writes; it proves no escape but is not a byte high-water measurement
- test_hcu_mp_capacity.py:886 renderer late publication recorded from prior runs, not re-run this session

Production change: src/stream/hcu_map_service.c only, three macro-gated hunks (HCU_C4_FAULT_SEAM, default off, approved by the coordinator). No pins, hashes, tools/cbsp.py, or hcu_main.c changes. New files: tests/c4_bsp_fault_harness_main.c, tests/test_c4_bsp_fault_injection.py, tests/test_c4_parity_validators.py, docs/reports/m4-c4-parity-validators-2026-10-26.json, this report.
