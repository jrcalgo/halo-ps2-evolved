# M2 HP2 bounded visitor correctness audit

**Disposition: host-verified decoder primitive; production map integration and target acceptance remain open.** This independent review covers `world_visit_section_with_scratch()` and `hp2_load_stream()` as present in the dirty halo-ps2 worktree on 2026-10-21. It does not change code or plans and does not claim a CE gameplay-map load, fit, or rendered scene.

## Executive assessment

The visitor is a sound bounded-memory *decode-and-callback* seam for the tested HP2 inputs. It parses the pack header/table before selecting a section, checks section file extents at the reader boundary, uses a 65,536-byte LZ4 history ring plus 16-KiB input and output buffers (98,304 bytes total), validates exact decoded length and raw CRC, and closes/releases its file and scratch lease after the synchronous call. Host ASan/UBSan comparisons passed byte-for-byte for UI, Longest, and Blood Gulch CTAG and B000 sections. The fixtures explicitly hash their packages and include the large raw/stored sizes, so the result is stronger than a synthetic-only codec test.

The central safety caveat is part of the API contract, not a latent failure: output callbacks can run repeatedly before the final raw CRC is known. A late CRC, I/O, or decode error leaves already-written sink bytes in place. Callers must keep those bytes unpublished and make retry/revalidation safe. The new visitor is not yet called by `hcu_map_service_preflight()` or `ctag_mount`; current runtime still owns whole raw section outputs. It therefore does not yet resolve production arena capacity or validate any CE cache/BSP owner transition.

## Exact reviewed inputs and verification

The checkout is dirty; the halo-ps2 commit alone is not a full source identity. At review time:

| Input | Identity |
|---|---|
| halo-ps2 `HEAD` | `71183bb0a9adc586cd267b2780c82bbc12cfd95b` (dirty) |
| `engine/src/world/section.c` | SHA-256 `61cbdcf88bcbf4b46cadd929882b374e2c627f12a827e7369a6100d487ac1e74` |
| `engine/src/world/section.h` | SHA-256 `5ca46c64c26515f1ea24a37edcdd94633f46730eba58067ca8c79254622722e4` |
| `engine/src/stream/hp2.c` | SHA-256 `f5222e7e2ccfe7fba897cb1d7f0fe46d4fb4a9e1c2018973d7c3b5e9c26140cd` |
| Longest HP2 fixture | SHA-256 `6f9c19feb4df9e7ec49e797ce3eb6f7cfbdef3c89c6363b12aab2f05359f5a5b` |
| Blood Gulch HP2 fixture | SHA-256 `ded2bca19058f51d7feed6b40149f421f7b1c2c7704f0918a42bacc5601dd011` |
| UI HP2 fixture | SHA-256 `a83ded5049128dc0287b975af9c17f4224e467ad5e10ffa079468934e6241e90` |

Independent checks run in this review:

```text
python3 -m pytest -q tests/test_world_section_visitor.py tests/test_hp2_stream_retail.py tests/test_world_section_capacity.py tests/test_pack_retail_ctag_hp2.py
7 passed, 6 subtests passed

ASAN_OPTIONS=detect_leaks=0 make -C submodules/halo-ps2/engine/tests test
passed (HP2, world-loader, BSP, texture, rendering, config, skeleton/animation and related engine tests)

R5900 compile of engine/src/world/section.c: passed
readelf: ELF32, little-endian, MIPS R3000, flags include 5900/mips3
```

The first engine `make test` attempt without `ASAN_OPTIONS=detect_leaks=0` stopped in LeakSanitizer with its “does not work under ptrace” fatal diagnostic; rerunning with leak detection disabled passed the suite. AddressSanitizer and UndefinedBehaviorSanitizer remained enabled. The R5900 check was a compile-only translation-unit check, not a linked guest or hardware run. The compile command used the installed PS2SDK headers and `_EE` target define and wrote its object under `/tmp`; no repository source/test was edited for this audit.

## Verified invariants

### Pack selection and read bounds

`world_visit_section_with_scratch()` clears `*raw_size` first, rejects missing arguments, opens one `file_reader_t`, reads at most the fixed header/table capacity, passes that buffer plus the measured file length to `hp2_open_header()`, selects one exact tag with `hp2_find()`, leases work scratch, calls `hp2_load_stream()`, releases the scratch mark and closes the reader on the common completion path (`submodules/halo-ps2/engine/src/world/section.c:63-130`). Header-read, malformed-header, missing-section, overflow, and scratch-allocation exits close the reader before return (`section.c:81-112`).

`hp2_open_header()` shares `open_common()` with whole-buffer parsing. It checks HP2 magic/version, count ceiling, declared file length, reserved bytes, complete table extent, canonical 4-byte tags, allowed alignment values, sector alignment and payload floor, supported codec, stored/raw equality for stored sections, file-range bounds, duplicate tags, and overlapping payload extents (`submodules/halo-ps2/engine/src/stream/hp2.c:18-69`). The visitor’s read callback independently checks `offset <= reader.size` and `bytes <= reader.size - offset` before every file operation (`section.c:36-46`). This subtraction form avoids an offset-plus-length overflow at that boundary.

The format header is static, 16-byte-aligned storage of `64 + 32 * HP2_MAX_SECTIONS` bytes (2,112 bytes) at `section.c:67`. The selected `hp2_section` pointer refers into the local `hp2_pack` table, which remains live for the synchronous decode. No pointer to the header/table is returned to the caller.

### Bounded decoder and parity

The work arena allocation is the sum of `HP2_STREAM_HISTORY_BYTES` (65,536), 16,384 input bytes, and 16,384 output bytes, aligned to 64 bytes (`section.c:74-78,101-118`). `hp2_load_stream()` does no payload-sized allocation; input is refilled in caller-sized chunks, decoded output is flushed in caller-sized chunks, and the circular history indexes by the power-of-two 64-KiB mask (`hp2.c:183-229,251-354`). LZ4 match distances are read as 16-bit values and rejected if zero or larger than bytes already produced; length and output-room checks precede match emission (`hp2.c:298-345`). The complete stored extent is consumed, produced length must equal `raw_size`, output is flushed, and only then is the inverted incremental CRC compared to the declared CRC (`hp2.c:347-354`). Stored payloads use the same bounded refill/output path and are subject to the same produced-length and CRC checks (`hp2.c:283-297,350-354`).

The retail parity test compiles the production visitor and legacy whole-output loader under host ASan/UBSan, checks each package SHA, and compares the complete decoded output byte-for-byte. Current cases include:

| Package | Sections checked by visitor | Raw section sizes (CTAG / B000) |
|---|---|---:|
| UI | CTAG, CRNG, HMAP, B000, CBIX | 1,547,396 / 2,288 bytes |
| Longest | CTAG, CRNG, HMAP, B000, CBIX | 4,339,096 / 377,388 bytes |
| Blood Gulch | CTAG, CRNG, HMAP, B000, CBIX | 4,556,496 / 1,303,092 bytes |

The exact cases and expected sizes/hashes are in [`tests/test_world_section_visitor.py:9-54`](../../tests/test_world_section_visitor.py#L9). The visitor test reports `scratch_high=98304` while comparing output to the legacy loader (`submodules/halo-ps2/engine/tests/test_world_section_visitor.c:31-73`). The independent Python-to-C Blood Gulch CTAG test additionally checks the 4,556,496-byte raw / 1,901,809-byte stored section against the Python HP2 decoder (`tests/test_hp2_stream_retail.py:12-48`; `submodules/halo-ps2/engine/tests/test_hp2_stream_retail.c`). These prove decoded bytes for those exact fixtures, not map-level capacity.

### Failure and cleanup behavior

The visitor sets `raw_size=0` before work and assigns the decoded raw size only on `HP2_OK` (`section.c:81-83,124-130`). Once scratch is allocated, all decode outcomes—success, source error, sink rejection, malformed stream, or final CRC mismatch—flow through arena release and file close (`section.c:124-130`). Failure to allocate the work area closes the file without advancing the cursor (`section.c:106-112`; arena allocation does not change `used` on failure in `submodules/halo-ps2/engine/src/core/mem.c:12-32`).

The synthetic engine suite verifies valid visitor output, scratch cursor restoration, a one-byte-short scratch cap, payload I/O failure, sink rejection, bad CRC, and zeroed `raw_size` (`submodules/halo-ps2/engine/tests/test_world_loader.c:135-197`). The visitor test’s error semantics are appropriate: sink rejection maps to `HP2_ERR_IO`; callers should log additional context if they need to distinguish sink failure from source I/O. Existing full-output loading remains a separate API and retains a full raw output allocation, with rollback on failure (`section.c:133-228`).

## Failure atomicity and ownership constraints

The API explicitly documents that a sink may receive a prefix before a later failure and requires callers not to publish output until success (`section.h:11-16`; `hp2.h:82-88`). In fact, a bad raw CRC is detected only after the final output flush, so a rejecting CRC leaves the *entire* decoded section potentially written to the sink. The host CRC test confirms the error code and arena release but does not assert/implement rollback of the sink (`test_world_loader.c:181-197`). This is not a decoder bug, but it makes caller publication/transaction rules a hard correctness dependency.

The visitor itself does not synchronize data cache after calling an arbitrary sink. The legacy full-output path calls `SyncDCache(raw, raw + size)` after successful decode (`section.c:225-226`), whereas visitor callers must perform any cache writeback/invalidation needed by their destination and next EE/ DMA/VU consumer. A sink that copies into CE’s tag cache or a BSP store cannot treat `HP2_OK` alone as cache coherency or CE publication approval.

Lifetime of the `bytes` pointer passed to the sink is not stated explicitly in the public header. It points at the reusable output window (`hp2.c:207-229`), so a callback must consume/copy those bytes synchronously and must not retain the pointer. Add this to the documented interface before a production consumer adopts it.

The visitor opens and closes the package reader inside one call (`section.c:84-90,124-130`). A multi-pass CTAG verify/materialize design will reopen the path per pass (or require a separate retained-reader API). On removable OPL media, that means the source can disappear/change between validation and materialization. Raw CRC detects ordinary content changes during each pass but does not bind two passes to the same immutable file identity; source/package hash or stable source lease/revalidation must be specified by the consumer. Resource-tag extent reads also need a reader lifetime distinct from this temporary visitor handle.

## Concurrency and stack/static-state constraints

The interface correctly warns it is synchronous and non-reentrant: its `hdr` buffer is static at `section.c:67`, while the legacy loader has a different static header array at `section.c:136`; simultaneous calls to the visitor itself race on its shared header. The current HCU map/cache service is one-active-map and synchronous, so serial use is a reasonable present contract, but future map-load/resource workers must serialize calls or make header storage caller-owned. The header should not be converted to a large automatic array without checking the small target thread stack.

The `hp2_pack` table is local stack state and carries 64 section records, roughly 2 KiB depending on target layout (`hp2.h:26-37`), in addition to decoder locals and caller frames. The R5900 compile establishes that this code compiles for the target ABI; it does not establish acceptable EE stack high-water, worst-case interrupt/task nesting, or reentrancy. Measure target stack use before moving the visitor into a different CE thread/context.

`file_reader_read_at()` seeks then loops until the requested bytes are read, treating short/zero reads as errors and bounding each syscall to `CHUNK=256 KiB` (`submodules/halo-ps2/engine/src/stream/file.c:15-16,129-164`). Visitor refill requests are only 16 KiB, so on a large stored section many seek/read operations occur; each refill is a positional operation implemented by seek+read, not a single atomic random-access call. Current R5900 work buffers are 64-byte aligned, but the static HP2 header is only 16-byte aligned (`section.c:67,107`): FileXio/DVD/OPL buffer-alignment requirements must be checked on the real target rather than inferred from host success.

## Missing adversarial coverage

Existing coverage is useful but leaves specific edge cases before treating this as a generic bounded reader:

1. **Partial sink mutation at late failure:** inject source failure after at least one successful output flush, callback failure after several chunks, and a CRC mismatch after a large real-size output. Assert `raw_size==0`, arena cursor/descriptor cleanup, and, at the eventual consumer boundary, no cache/BSP/global publication plus deterministic retry. Current test I/O failure occurs as soon as payload reads at nonzero offsets are attempted, and the current sink rejection is immediate (`test_world_loader.c:156-170`); neither demonstrates multi-chunk partial writes. CRC fixture changes metadata CRC and checks the status, but not sink contents/publication (`:181-197`).
2. **Streamed LZ4 truncation/corruption matrix:** run the visitor—not only `lz4_decode()`/header parser—against truncated token, extended literal/match length, missing offset byte, zero/too-large back-reference, raw overrun/underrun, trailing compressed bytes, and CRC error. Include exact 65,535-byte distance and 64-KiB ring wrap boundaries with tiny input/output windows. `test_hp2.c` has useful general header/LZ4 negatives and small-window stream checks (`engine/tests/test_hp2.c:80-190`), but the real retail streaming test is principally successful Blood Gulch CTAG output parity (`tests/test_hp2_stream_retail.py:12-48`).
3. **Callback contract:** verify strictly increasing contiguous output offsets, callback lengths never exceed sink limits, zero-size raw sections, null/invalid callback arguments, and no retaining of temporary output buffers. The full-output parity fixture makes final byte equality strong, but does not characterize each callback boundary/failure location.
4. **Bounds and malformed reader metadata:** test header/table truncation, invalid section count, offset+stored-size overflow at `UINT32_MAX`, short read in the middle of a refill, source file size changing/truncating after header parse, reader open failure, and close count exactly once for every exit. `hp2_open_header()`’s shared parser has table/layout tests, and the synthetic loader exercises selected failures, but no comprehensive world-visitor reader lifecycle matrix is present.
5. **Scratch aliasing contract:** `hp2_load_stream()` validates non-null/nonzero buffers and history capacity but does not verify that `history`, `input`, and `output` are disjoint (`hp2.c:259-280`). The world visitor supplies disjoint contiguous windows, as do tests; the lower-level public API should either document non-overlap or reject overlapping ranges, because aliasing can overwrite unread compressed input or LZ4 history.
6. **Target I/O/stack/performance:** measure actual FileXio/OPL/optical short-read behavior, 64-byte alignment constraints, seek/read count, throughput, stack high-water, and EE cycles for the 4.3–4.6 MiB CTAG sections and repeated passes. Host timing is not representative of EE or USB/HDD/SMB.

## Integration and M2 acceptance gaps

1. **No production caller yet.** Current HCU preflight still calls `world_load_section_with_scratch()` for HMAP/CTAG/CRNG/CBIX, and `ctag_mount` retains full CTAG/CRNG/CBIX section buffers in its map owner (`src/stream/hcu_map_service.c:55-67,202-295`; `src/stream/ctag_mount.c:112-173,199-235`). The visitor’s existence/parity does not currently reduce `streaming` high-water.
2. **CTAG sink must preserve HCU/CE authority.** The eventual sink needs a no-write validation strategy, then post-unpublish materialization into the already-bound CE tag-cache span; it must validate the complete envelope/image CRC, relocation table and targets, write back caches, and only report read completion after all checks. CE continues to validate/publish its tag state. A direct sink can partially overwrite destination on late failure, so the destination must remain unpublished and a retry must completely rewrite/revalidate it.
3. **CBSP is a separate path.** Longest’s B000 raw envelope is 377,388 bytes and its materialized BSP image is 374,784 bytes; Blood Gulch B000 is 1,303,092 bytes. Visitor parity says these can be emitted through bounded scratch, but current map loader still expects a full decoded payload for `ps2_cbsp_materialize()`. A streaming CBSP validator/sink must preserve internal and CTAG-name relocation domains, verify target-name bounds before publication, and keep exactly one active CE BSP. This visitor by itself does not materialize or mount the BSP.
4. **Tag/BSP placement and broader live-set remain gates.** The Longest CTAG image is 4,263,624 bytes, not its 4,339,096-byte raw CTAG wire payload; Blood Gulch image is 4,477,116 bytes. The current default CE tag-cache span remains 2 MiB and `current_bsp` remains 6 MiB. A candidate split must be fixed before CE physical allocation, disjoint, canaried, and charged with validation claims, CRNG/CBIX metadata, render geometry/lightmaps/textures, audio/animation, decode/verification overlap, and transition peaks. See [`m2-longest-artifact-freeze.md:30-46,55-69`](m2-longest-artifact-freeze.md#L30) and [`m2-next-capacity-design-review.md:101-123`](m2-next-capacity-design-review.md#L101).
5. **No end-to-end result.** No exact combined guest ELF has loaded Longest or Blood Gulch through CE scenario load, `structure_bsp_port_verify`, collision/surface/PVS/sound consumers, gameplay tick, and parent render snapshot. No visible scene is demonstrated. M2 Step 10 must keep the non-UI map admission guard closed until the complete destination/owner/renderer ledger and interpreter+recompiler run pass (`plans/7.hcu-remake-m2-m4.md:511-525`).

## Recommendations for the next small code-reviewable increment

1. Keep the existing whole-output API as the reference and keep non-UI admission fail-closed.
2. Clarify/document sink-byte lifetime, scratch-buffer disjointness, callback ordering, and the `raw_size==0` on failure contract; add a visitor test asserting the actual partial-output behavior.
3. Add deterministic HP2 visitor fault injection at several output windows and verify every cleanup branch (including close exactly once).
4. Define a caller-owned reader/header context if the consumer needs multi-pass/reentrant validation; otherwise enforce a single-thread serialization rule at the map-service boundary. Avoid a large target stack allocation as a superficial reentrancy fix.
5. Prototype CTAG and CBSP consumers against inactive destination spans with failure-injection and cache-coherency assertions, without publishing CE globals. Only after these transactions pass should the production map service call the visitor.
6. Measure target cycles and file I/O on the R5900/PCSX2 and intended physical OPL/storage paths before selecting decoder window sizes or repeated-pass validation. A host `scratch_high=98,304` is a bound on this visitor’s current work lease, not total map staging, memory fit, or acceptable latency.

**Bottom line:** current source and host evidence support the visitor as a useful, bounded HP2 primitive with correct bytes for the tested retail fixtures. Remaining correctness hinges on transactional consumers, explicit pointer/scratch contracts, stronger partial-failure tests, target I/O/stack/performance qualification, and the separate CTAG/CBSP/map-owner integration. No gameplay-map fit/load/render should be claimed on this evidence alone.

## Follow-up (2026-10-21)

The public callback lifetime contract is now explicit: `world_section_sink_fn` receives a pointer into a reused output window, must consume/copy it synchronously, and successful callback spans are increasing and contiguous (`submodules/halo-ps2/engine/src/world/section.h:8-20`). The lower-level `hp2_load_stream()` documentation likewise states that the writer consumes the reusable output window synchronously and that caller-provided history/input/output buffers must not overlap (`submodules/halo-ps2/engine/src/stream/hp2.h:72-89`). These are documented caller obligations; the lower-level API does not yet dynamically detect overlapping work buffers.

The visitor host harness now injects a sink rejection at decoded offset 32,768 for every tested section larger than two 16-KiB windows. It verifies two complete callback writes precede failure, the callback then rejects, `world_visit_section_with_scratch()` returns `HP2_ERR_IO`, caller `raw_size` remains zero, and the scratch cursor returns to baseline (`engine/tests/test_world_section_visitor.c:20-33,65-89`). The synthetic engine fixture also now places source-I/O failure at the first actual section payload offset derived from the HP2 table, rather than failing the earlier header/table read (`engine/tests/test_world_loader.c:15-17,40-72,120-140`). This corrects the earlier statement in “Missing adversarial coverage” that the world-loader injection failed only during header parsing.

Verification after these changes: `python3 -m pytest -q tests/test_world_section_visitor.py` — **1 passed**, covering all five sections (CTAG, CRNG, HMAP, B000, CBIX) in each available pinned UI, Longest, and Blood Gulch package and the multi-window partial-sink fault; `ASAN_OPTIONS=detect_leaks=0 make -C submodules/halo-ps2/engine/tests test` — **passed** with AddressSanitizer and UndefinedBehaviorSanitizer. Leak detection remains disabled for this environment because LeakSanitizer fails under its known ptrace restriction. This still does not solve final-destination transactionality, actual CTAG/CBSP integration, target stack/throughput, map capacity, or guest scene rendering.
