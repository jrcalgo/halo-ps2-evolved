# M2 CBSP direct-destination cache-read interface audit

Date: 2026-10-21  
Scope: report-only source audit of the parent HP2 section visitor, map/mount owner, HCU PS2 cache callback, and CBSP parser. This is an implementation design, not evidence that production streaming is integrated or that a gameplay map loads.

## Executive finding

The correct production insertion point is the synchronous `cache_file_read(NONE, reference->file_offset, reference->file_size, reference->base_address, &read_complete, TRUE)` call made by CE's `scenario_structure_bsp_load()` ([`cache_files.c:1430-1435`](../../submodules/halo-ce-universal/source/cache/cache_files.c#L1430)). The PS2 adapter already recognizes that exact destination and has an exact-extent callback path ([`ps2_cache.c:375-407`](../../submodules/halo-ce-universal/port/ps2/src/ps2_cache.c#L375)); the missing part is that the current callback decodes the entire CBSP section into `frame_scratch`, mounts a payload pointer, and later copies/rebases it into the destination. `ctag_mount.c` lines 67-104 make this full-payload allocation explicit.

Replace that callback's *payload-returning* contract with a synchronous *section visitor into a consumer sink*. The cache adapter should own the CBSP parse/rebase transaction because it owns the fixed `current_bsp` destination, CTAG view, and `cache_file_read` completion flag. The parent should retain ownership of pack/source identity, catalog selection, HP2 decompression, and bounded scratch. Parent calls the sink only with transient decoder bytes; HCU copies the CBSP image directly to the exact final BSP address, keeps the fixed header and relocation rows in bounded scratch, validates all envelopes and cross-image fixups, then rebases in place. Only after every validation succeeds may the adapter set `read_complete = TRUE`.

The most important semantic is CE's tri-state completion flag: `_cache_file_read_failed` is `2`, `FALSE` is pending, and `TRUE` is success ([`cache_files.h:25-31`](../../submodules/halo-ce-universal/source/cache/cache_files.h#L25)). CE's waiting loop exits for either nonzero value and then tests for exactly `TRUE` ([`cache_files.c:1437-1450`](../../submodules/halo-ce-universal/source/cache/cache_files.c#L1437)). Preserve this contract on all exits. A visitor or validator failure must leave the flag at `2`; a partial write into `current_bsp` is permitted only while unpublished and must never be reported as successful.

## Current call graph and ownership

1. `hcu_map_service_preflight()` opens the selected retail resource map, validates HMAP/CTAG/CRNG/CBIX, confirms source length/hash, and retains the source reader ([`hcu_map_service.c:230-305`](../../src/stream/hcu_map_service.c#L230)). It currently rejects every gameplay map except `ui` because capacity is not qualified.
2. `map_loader()` calls `ctag_mount_hp2_verified_source_discover()` with the retained source and the stable map/section-scratch arenas ([`hcu_map_service.c:95-143`](../../src/stream/hcu_map_service.c#L95)). `ctag_mount` owns the decoded CTAG/CRNG/CBIX bytes in `map_arena`, keeps the source reader alive through unmount, and registers a BSP loader with the backend.
3. At BSP request time, `load_bsp_extent()` requires an active mount, exact `cbsp_catalog_find(offset,size)`, rejects CTAG and CRNG-resource overlaps, then releases any prior BSP and decodes one whole HP2 CBSP payload into `bsp_scratch` ([`ctag_mount.c:67-104`](../../src/stream/ctag_mount.c#L67)). The active mount retains that payload until CE unloads the BSP and invokes the release callback ([`ctag_mount.c:54-65`](../../src/stream/ctag_mount.c#L54)).
4. The PS2 backend maps parent mount calls to HCU functions `ps2_cache_mount_ctag_with_file_source`, `ps2_cache_mount_cbsp_for_extent`, and `ps2_cache_set_bsp_loader` ([`ctag_ps2_backend.c`](../../src/stream/ctag_ps2_backend.c)). HCU's static cache state owns the CTAG view and one optional whole CBSP payload pointer ([`ps2_cache.c:61-86`](../../submodules/halo-ce-universal/port/ps2/src/ps2_cache.c#L61)).
5. `cache_file_read()` initializes completion to failure, detects the BSP request only when `tag_index == NONE` and `buffer` is exactly the physical BSP-cache base, invokes the loader if necessary, and then materializes the mounted CBSP into `buffer` ([`ps2_cache.c:375-452`](../../submodules/halo-ce-universal/port/ps2/src/ps2_cache.c#L375)). The current `ps2_cbsp_materialize()` copies the image and fixes pointers from the complete payload; the PS2 adapter then zeros Xbox-only vertex/index buffer fields and sets completion to `TRUE` ([`ps2_cache.c:418-442`](../../submodules/halo-ce-universal/port/ps2/src/ps2_cache.c#L418)).
6. CE next checks `read_complete == TRUE`, the `psbs` signature, and that `base_address`, vertex-buffer array, and index-buffer array lie inside the requested BSP extent ([`cache_files.c:1446-1477`](../../submodules/halo-ce-universal/source/cache/cache_files.c#L1446)). This explains why the HCU adapter must retain the established post-materialization header normalization.

Current `world_visit_section_reader_with_scratch()` is already a bounded synchronous decoder: it emits ordered contiguous decoded spans, its sink bytes are valid only during the call, and its 98,304-byte decoder lease is released before return ([`section.h:12-31`](../../submodules/halo-ps2/engine/src/world/section.h#L12), [`section.c:79-138`](../../submodules/halo-ps2/engine/src/world/section.c#L79)). It can emit a prefix before late decompression/I/O/CRC failure, so the destination must remain private/unpublished until it returns `HP2_OK` and all CBSP checks pass.

## Recommended boundary and minimum API change

### Preferred responsibility split

- **Parent (`src/stream`)**: own the HP2 pack path and validated CBIX entry; confirm the request exactly matches one catalog extent; recheck the source extent is outside tag data and all CRNG resource intervals; invoke the visitor for that selected `entry.section_tag`; provide the sink with transient decoded bytes; retain map/source ownership until CE unpublishes and parent unmounts.
- **HCU PS2 cache adapter**: own exact-destination checks, destination bounds, fixed-size CBSP header staging, relocation scratch lease, `ps2_cbsp_open_parts()`, source extent equality against the request, CTAG string target checks, `ps2_cbsp_rebase_in_place()`, Xbox-only header normalization, and completion-state transition.
- **CE**: remains unchanged. The scenario loader continues using normal cache reads and its existing post-read validation and BSP publication/unload behavior.

Do not add a new CE-only alternate BSP loader and do not set completion from the parent callback. Completion is part of the cache adapter's responsibility and should remain true only after its last normalization write.

### Minimum API delta

Keep `ctag_bsp_load_fn`/`ps2_cache_bsp_loader_fn` only if it is widened to pass the transaction inputs and receive a sink; do not pass the final destination into parent code as an untyped direct writer. A small API that keeps the owner boundaries explicit is:

```c
typedef int (*ctag_bsp_sink_fn)(void *sink_context, uint32_t section_offset,
	const uint8_t *bytes, size_t byte_count);
typedef int (*ctag_bsp_visit_fn)(void *context, uint32_t retail_file_offset,
	uint32_t retail_file_size, ctag_bsp_sink_fn sink, void *sink_context,
	size_t *decoded_section_size);
```

The backend registration becomes `register_bsp_visitor(visit, context)`; the parent implementation performs the current `cbsp_catalog_find()` and CRNG/tag exclusion before calling `world_visit_section_with_scratch(section_scratch, pack_path, entry.section_tag, &raw_size, 0, sink, sink_context)`. Return success only for `HP2_OK` and the reported exact decoded size. This removes parent-side persistent BSP scratch and the release callback for CBSP payload; the `current_bsp` bytes themselves are owned by CE after a successful read and are cleared/reused only after `scenario_structure_bsp_unload()`.

On the HCU side, expose a transaction function rather than exposing internal staging state:

```c
int ps2_cache_stream_cbsp_for_read(uint32_t offset, uint32_t size,
	void *destination, size_t destination_capacity);
```

It calls the registered parent visitor with a private sink context containing the destination, staged 36-byte envelope header, a relocation-table lease in the scratch arena, expected request extent, and checked running byte counters. The function returns success only after all final checks and normalization; `cache_file_read()` alone maps that result to `TRUE`. An alternate acceptable shape is for `cache_file_read()` to own the sink context and invoke the visitor directly. Either way, there must be only one owner of completion semantics and no public “mounted CBSP payload” state in streaming mode.

The current `ps2_cbsp_open_parts()` and `ps2_cbsp_rebase_in_place()` are sufficient for the final parser/rebase layer ([`ps2_cbsp.h:36-60`](../../submodules/halo-ce-universal/port/ps2/include/ps2_cbsp.h#L36)). The parent needs one visitor callback contract; the HCU cache needs one transaction entry point; the backend needs to register/unregister that visitor with mount lifetime. This is the minimum functional interface change. Retain the whole-payload APIs as test oracle/compatibility until integration parity passes.

## Required synchronous stream transaction

The proposed operation runs *inside* the exact BSP `cache_file_read()` request, after CE has poisoned `current_bsp` with `0xCD` and before CE tests completion. It must not run at preflight or map mount: CE poisons the destination immediately before the BSP read, so any eager bytes would be erased. The preflight remains non-destructive while the previous map may still be active ([`cache_files.c:1414-1424`](../../submodules/halo-ce-universal/source/cache/cache_files.c#L1414), [`cache_files.c:1430-1445`](../../submodules/halo-ce-universal/source/cache/cache_files.c#L1430)).

1. **Initialize CE result and classify the request.** Set a non-null completion pointer to `_cache_file_read_failed` before validation, exactly as today. Require the mounted map/open state, `tag_index == NONE`, `offset`/`size` nonnegative and within mounted file length, destination exactly equal to `physical_memory_get_structure_bsp_cache_base_address()`, and requested size equal to the registered catalog extent. A malformed/mismatched BSP request stays at failure; do not let it fall through to generic map reads.
2. **Acquire one bounded scratch lease.** Mark the parent-provided `section_scratch` (currently it defaults to `frame_scratch` in [`hcu_map_service.c:154-181`](../../src/stream/hcu_map_service.c#L154)). Allocate only relocation bytes, computed with checked multiplication `relocation_count * 12`, after validating the envelope header. Keep this lease while the section visitor takes its own 98,304-byte history/input/output lease; release to the exact mark on every exit. Check that this existing arena is exclusive for the synchronous transaction (no reentrant visitor and no simultaneous unrelated use). The header can be a local fixed 36-byte aligned object, not an arena allocation.
3. **Route streamed section bytes monotonically.** The visitor sink must check each callback's `section_offset` equals the transaction's `bytes_received`, reject overflow and out-of-order/duplicate/gapped spans, and split callback spans at CBSP boundaries. Copy bytes `[0,36)` into the local envelope header. After all 36 bytes are accumulated, validate magic/version/reserved fields and decode `image_size`, relocation count, table offset, source offset, and source size using checked arithmetic. Reject image sizes exceeding final BSP capacity; reject relocation counts above an explicit cap whose product plus visitor scratch fits the arena. Direct `[36,36+image_size)` spans into the exact final BSP destination. Route the trailing table to the separate relocation scratch. Reject any trailing or missing byte.
4. **Verify exact decoded envelope length and outer HP2 completion.** Require `raw_size == 36 + image_size + relocation_count*12`, checked for overflow, and require the visitor return `HP2_OK`. Because the visitor reports `raw_size` only after successful decode/CRC, no CBSP validation/rebase or completion success can occur after only a prefix. Add a size cap in the parent catalog before the call if HP2 section metadata exposes it; the HCU sink still independently enforces its cap.
5. **Validate CBSP v1 without modifying final pointers.** Call `ps2_cbsp_open_parts()` with the local header, direct destination image, and relocation scratch. It verifies exact header/layout, table length/order/domains/padding, `psbs`, image CRC, relocation row fields, and stored image targets ([`ps2_cbsp.c:76-150`](../../submodules/halo-ce-universal/port/ps2/src/ps2_cbsp.c#L76)). Separately require `view.source_file_offset == requested_offset`, `view.source_file_size == requested_size`, `view.source_file_size == view.image_size`, non-sentinel extent, no integer overflow, extent within the mounted original file, and no overlap with CTAG or CRNG-listed intervals. The parent catalog check and this HCU/header check are intentionally redundant: they bind the selected pack section and its claims to the exact CE request.
6. **Prevalidate every cross-image target, then rebase.** Call `ps2_cbsp_rebase_in_place()` with physical `current_bsp` and CTAG bases plus the successfully materialized tag image. It performs a no-write pass over all rows, validates domain-1 target bounds/NUL terminators and all effective addresses, then a second pass applies rebases ([`ps2_cbsp.c:240-315`](../../submodules/halo-ce-universal/port/ps2/src/ps2_cbsp.c#L240)). The relocation scratch must remain live throughout both passes and must not alias the final image. Do not copy or relocate pointers incrementally as callbacks arrive.
7. **Normalize the CE-facing header last.** After rebase succeeds, set `vertex_buffer_count`, `vertex_buffers`, `index_buffer_count`, and `index_buffers` to zero as the current callback does ([`ps2_cache.c:418-438`](../../submodules/halo-ce-universal/port/ps2/src/ps2_cache.c#L418)); validate that the first 24 bytes are present, signature is `psbs`, base address is in the destination extent, and header/base offsets satisfy CE's `cache_file_region_contains()` test. Then set completion to `TRUE`. No relocation scratch or parent section-reader pointer may escape the function.
8. **Release transient resources, retain loaded BSP.** Release scratch immediately after a success/failure return. On failure, clear only private visitor transaction bookkeeping and leave the active map/source/catalog owner mounted so CE may retry the exact BSP read in the same scenario, matching the established UI retry fixture. Do not invoke BSP-unmount/release on a failed first attempt unless there was an older successfully loaded BSP to release; do not close the shared source reader. On successful subsequent different-BSP request, CE is expected to unload the prior BSP first; assert/trace that lifecycle before reusing the single physical BSP destination.

## Cache normalization and exact extent constraints

There are three independent sizes and they must not be conflated:

| Quantity | Meaning | Must match |
|---|---|---|
| CE `reference->file_size` | Retail serialized extent requested by CE | CBIX entry's `file_size`; CBSP header source size; CBSP image size |
| CBIX `section_tag` decoded `raw_size` | Encoded converter section containing header + image + relocation rows | `36 + image_size + 12 * relocation_count` |
| CE `current_bsp` capacity | Fixed physical destination for relocated BSP image only | At least `image_size`; it does not need room for header/table envelope |

Do not compare `raw_size` to CE `reference->file_size`: they are different representations. Do not pass the converter envelope length as `cache_file_read` completion length. CE will continue to validate the final *image* using its original requested extent. Its vertex/index metadata is normalized to empty because GS/VU packs own geometry, but `base_address` and the `psbs` header remain real and range-valid.

The parent already checks that request `(offset,size)` is an exact CBIX entry, lies within source file length, does not overlap tag data, and does not overlap any CRNG resource interval ([`ctag_mount.c:75-85`](../../src/stream/ctag_mount.c#L75), [`ctag_resource_index.c`](../../src/stream/ctag_resource_index.c)). Preserve those checks before invoking the visitor. HCU must additionally require the CBSP envelope source extent to equal the same request; otherwise a valid HP2 section could be mislabeled for another BSP.

## Rollback and retry semantics

The target BSP destination is allowed to contain a partial or fully relative image after a streamed failure because CE marks it `0xCD` before the read and does not publish the BSP unless completion is exactly `TRUE` and subsequent header checks pass. It is not safe to call this a byte-for-byte rollback. The correct guarantee is **publication rollback**:

- completion remains `_cache_file_read_failed` (`2`), so CE exits its wait and returns false;
- no global structure-BSP pointer/tag-instance base address is set by CE;
- no success-state (`mounted`, `bsp_active`, completed destination generation) is recorded by HCU/parent;
- the scratch arena returns to its original mark and the map source/CTAG/CBIX owner remains live;
- same-request retry starts its sink offset at zero, overwrites the entire destination image from relative source bytes, rereads all relocation rows, reruns CRC/validation, and only then rebases;
- a late visitor failure must never reuse partially collected header/count state from the previous attempt;
- if there is a required `scenario_unload()` after failure, CE must first clear any partially assigned fields (normally none, since its publication occurs after read validation); tests must prove no stale `tag_instance->base_address` or global BSP pointer survives.

The current UI lifecycle already shows the right owner ordering: CE unpublishes scenario/tag pointers before `ps2_cache_release_map_owner()` invokes parent unmount, then parent closes the source and rewinds map-arena ownership. Preserve this direction; the stream callback must not release the mounted map owner or source. `ctag_mount_unload()` explicitly unmounts the backend before closing the retained source and rewinding the arena ([`ctag_mount.c:278-290`](../../src/stream/ctag_mount.c#L278)).

## Error/failure ordering

Fail in the earliest layer that has sufficient evidence, always keeping completion `2`:

1. Invalid completion pointer, destination, request integer/range, map-open state, or exact callback registration: reject before scratch or writes.
2. Parent catalog miss, extent overflow, tag overlap, CRNG overlap, inactive mount, or unavailable pack/source: reject before visitor invocation.
3. Scratch capacity/lease failure or initial section open/header failure: reject before destination write.
4. Invalid/oversized CBSP header, row count, arithmetic, destination cap, or expected full raw length: reject; if already partially streamed, destination remains unpublished and retry restarts at offset zero.
5. HP2 I/O/decode/CRC failure: no parser/rebase success, retain failure sentinel, release scratch.
6. CBSP internal CRC/format/relocation/source-extent failure: no rebase; release scratch.
7. CTAG cross-string/bounds/alignment/address failure during preflight pass: no pointer writes because `rebase_in_place()` validates all rows before its write pass; release scratch.
8. CE header postcondition failure after normalization: leave failure sentinel and do not mark loaded. Prefer prevalidate `base_address`/signature/size before normalization so the normalization is the final non-failing mutation.
9. Success: normalize CE-only arrays, record a monotonically increasing debug generation (optional but useful), set completion exactly `TRUE`, release scratch before returning.

Never fall back from a recognized BSP request to `mounted_read_at()` if the visitor rejects it. The current code already prevents the ordinary source-read branch for `bsp_request`; preserve this so failure cannot silently load raw retail bytes instead of the converted CBSP ([`ps2_cache.c:445-466`](../../submodules/halo-ce-universal/port/ps2/src/ps2_cache.c#L445)).

## Bounded-memory implications

The visitor reserves 98,304 bytes per call (65,536 history + 16,384 input + 16,384 output) in `section.c:90-127`. The decoded CBSP image goes directly to fixed `current_bsp`; only header bytes and relocation rows are staged. Existing retail-backed Longest B000 uses a 374,784-byte final BSP image, a 377,388-byte CBSP envelope, and 214 rows (2,568 relocation bytes); this means the streaming transaction's live scratch is approximately 100,908 bytes plus alignment, instead of the current whole envelope plus visitor scratch (475,692 bytes). These values are specific to that frozen artifact; production max-row policy must be explicit and measured across the admitted BSP catalog rather than inferred from this one BSP.

There is a subtle arena ownership issue: `hcu_map_service` defaults `section_scratch` to the 393,216-byte `frame_scratch`, while BSP final bytes belong in `current_bsp`; do not use `bsp_scratch` for the destination and do not retain relocation rows in the final image. The BSP sink must allocate its relocation scratch before calling the visitor so both coexist. It must restore the saved mark on every result, including sink callback abort. The existing visitor itself restores its own nested 98,304-byte lease before returning. Verify both marks in target/high-water tests; the arithmetic estimate alone does not establish safe simultaneous use under the actual build.

## Tests required before replacing the current callback

### Host/C unit tests

1. Visitor sink routing across all boundary splits: header delivered as multiple fragments; image/table split at every byte boundary around 36 and `36+image_size`; zero/maximum callback chunk; increasing contiguous offsets; duplicate, gap, out-of-order, overflow, trailing, and truncated spans.
2. Frozen retail B000 path: run actual `world_visit_section_reader_with_scratch()` through the new HCU sink, compare the final rebased destination byte-for-byte with existing full-buffer oracle/Python output, verify image CRC and all pointer domains, assert destination pointer is exactly fixed BSP buffer, and record scratch high-water including nested visitor lease.
3. Header adversarial matrix: bad magic/version/reserved; minimum/maximum image; image exceeds BSP cap; relocation multiplication/addition overflow; relocation count cap; table offset mismatch; source sentinel; source offset/size mismatch; file-length overflow; tag interval overlap; CRNG interval overlap; raw-size mismatch; zero/missing table pointer handling.
4. Relocation adversarial matrix: bad row field alignment/order/range; nonzero padding; invalid domain; stale target word; late invalid row; domain-1 target outside CTAG; missing NUL within 256 bytes; effective address overflow; relocation scratch alias; verify late failures leave destination still relative (no partial rebase).
5. Outer/inner checksum and I/O matrix: invalid pack header/section table, open failure, short read after image prefix, HP2 outer CRC failure, CBSP image CRC failure under valid outer HP2, sink abort. Each checks completion value `2`, scratch mark restored, no BSP publication, owner/source retained, next retry starts offset zero and succeeds.
6. Exact callback behavior through `cache_file_read()`: wrong `tag_index`, wrong destination, wrong offset/size, generic cache request, absent visitor, visitor failure, success; assert tri-state `2/0/1` contract, and ensure no raw source fallback for a recognized BSP request.
7. CE-composed lifecycle fixture: call real `scenario_structure_bsp_load()` and `scenario_structure_bsp_unload()` around the existing tag-load fixture, inspect global/tag-instance publication before/after, inject all failure cuts, then retry same BSP and load a second BSP. Preserve UI map retry and owner-unload/reload tests.

### Target / PCSX2 evidence

- Build the exact combined R5900 production entry with the streaming callback, record parent/HCU/halo-ps2 commits and artifact hashes, and prove no unresolved imports.
- Run the exact artifact in PCSX2 interpreter and recompiler with debug traces for request offset/size, CBIX entry, visitor raw size, destination base/capacity, relocation count, scratch high-water, CRCs, completion enum, BSP publication/unload, and source-reader lifetime.
- First qualify existing UI and same-map/reload paths, then a single candidate BSP only after the candidate map's CTAG+BSP live set fits its chosen immutable split. Require injected corrupt late relocation and late HP2 read failures to return CE failure, no published BSP, same-source retry success, followed by unload and successful next-BSP selection.
- The acceptance claim is “one CBSP streamed and validated into the real fixed BSP destination through CE's cache callback.” It is not a rendered-scene claim. Rendering requires the independent snapshot/GS/VU path.

## Comparison with Halo-64

Halo-64 is useful as a contrast, not a template for this transaction. Its N64 `cache_file_read()` simply ignores request inputs and sets completion to `TRUE` ([`n64_game.c:1271-1286`](../../submodules/halo-64/port/n64/game/n64_game.c#L1271)); its converted map embeds BSPs in the loaded map image and bypasses ordinary BSP reads ([`cache_files.c:684-698,752-763`](../../submodules/halo-64/source/cache/cache_files.c#L684)). That avoids precisely the separate fixed-destination/streamed-source problem here, but it also provides no failure, exact-extent, relocation, or publication proof. Keep CE's real scenario BSP lifecycle and PS2's split fixed memory model; borrow only Halo-64's practice of isolating machine-specific cache seams and documenting which state is simulated versus rendered.

## Acceptance status / handoff

Current source evidence supports the design, not its implementation. The split CBSP parser/rebase exists and its complete-buffer test oracle passes, but `ctag_mount.c` still decodes the entire section into `bsp_scratch` and `ps2_cache.c` still requires a mounted whole-payload pointer. `world_visit_section_with_scratch()` currently has no production CBSP caller. No direct-destination CE `scenario_structure_bsp_load()` test, target scratch high-water, gameplay BSP guest load, or rendered scene is established by this audit. Keep map admission closed until the transaction and failure/retry tests above pass.
