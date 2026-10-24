# C2.4 segmented MEDIA format design (2026-10-23)

## Finding

The new HCP1 MEDIA cap is deliberately only a fail-closed size-bound increment. It makes every checked-in primary C1 package invalid: all 27 packages contain at least one MEDIA entry above 65,536 bytes. The checked set includes UI (six over-cap entries; largest 177,536 bytes), 13 bots profiles (66–78 over-cap entries each), and 13 survival profiles (556–568 each; largest observed profile entry 1,993,740 bytes). The C1 qualification JSON still records six passing requirements, but that result predates the cap and does not validate the current writer/strict parser contract.

## Why splitting payloads alone is unsafe

HCP1 currently has one directory row and one SHA-256 for each `(type, chunk_id)` logical resource. The builder assigns consecutive IDs to `media['chunks']`; manifests and runtime bindings refer to that ID and the whole resource's SHA. HCP lookup returns one `hcu_asset_chunk_view`, and read copies that full resource into caller storage. The bitmap dispatcher verifies the bound hash, reads the complete resource, then passes one contiguous TEXS image to `tex_open`. CBSP mount bindings likewise name one MEDIA id and expected whole-payload hash; its visitor reads byte ranges against that one chunk. (See `tools/hcu_profile_chunks.py`, `tools/hcu_profile_media.py`, `src/stream/hcu_asset_profile.[ch]`, `src/stream/hcu_profile_mount.[ch]`, and `src/stream/hcu_bitmap_dispatch.c`.)

If a writer merely emits 64 KiB payload records under new IDs, existing consumers cannot discover or reconstruct their original logical resource. If it reuses a logical ID for multiple HCP1 rows, the strict sorted-unique directory and binary-search lookup reject or ambiguously resolve them. Changing only writer-side chunking would also invalidate manifest counts, binding IDs, expected hashes, and deterministic package pins.

## Minimum viable format and API

Keep HCP1 version 1 semantics unchanged for old packages and add an explicit version 2 directory. A v2 row should carry at least `(type, logical_id, segment_index, segment_count, logical_offset, decoded_segment_size, logical_size, segment_sha256, logical_sha256)`. Require rows sorted by `(type, logical_id, segment_index)`; segment indices must be exactly `0..count-1`; offsets must form a gap-free, non-overlapping cover of `[0, logical_size)`; every segment must be nonempty and at most 65,536 bytes; all rows for a logical resource must agree on count, size, and whole-resource digest. Hash each segment during package preflight and hash the assembled logical byte stream incrementally before publishing its validated logical descriptor. Preserve 16-byte payload alignment and reject unclaimed/trailing bytes as v1 does.

Bindings continue to name `(type, logical_id)` and the whole-resource SHA, so consumer identity remains stable across segmentation. Replace the current single-row lookup assumption with a logical-resource view plus two bounded access operations:

* `read_range(view, logical_offset, size, destination)` resolves and copies only intersecting segments, validating segment digests and the logical digest according to an explicit preflight/lazy-integrity policy.
* `visit(view, sink, context, scratch)` emits ordered decoded bytes in bounded spans, supports offset-based resources such as CBSP, and reports failure without publishing a completed resource when a late segment/hash fails.

Retain an explicitly named compatibility helper for callers that need a contiguous reconstructed resource; it must require caller capacity for `logical_size`, and must not claim that the logical resource itself is <=64 KiB. Adapt the CBSP mount path to the visitor/range interface. The bitmap path currently requires the complete TEXS payload at once; either keep bounded contiguous destination reconstruction as an explicit consumer-owned allocation, or make TEXS validation/accessors range-based before claiming that bitmap use is fully streamed. The decoder segment limit alone does not prove that the reconstructed TEXS owner, CE cache, GS upload, or DMA live set fits.

For representation without changing HCP1's fixed 48-byte records, an alternative is a new HCP2 envelope/magic and 64-byte-or-larger rows. Do not overload HCP1's existing `chunk_id` to encode segment numbers: that leaks physical layout into stable logical identities and still leaves whole-resource binding hashes ambiguous. Exact integer widths/maximum logical size and all-hashes-before-publication behavior need to be pinned before implementation.

## Migration and qualification

1. Implement a v1/v2 strict parser and reader while keeping v1 behavior unchanged for entries at or below the segment cap. Add exact-boundary, malformed sequence/gap/overlap, hash corruption, short-read, and cross-segment range tests.
2. Update profile writers and manifests to record logical resource identity and segment roster, with deterministic segment IDs/order; preserve binding IDs and whole-resource hashes.
3. Validate a UI package and a large map package through strict host parser, C preflight, bitmap/TEXS consumer, and CBSP visitor. Compare logical bytes, bindings, and semantic validation with the existing v1 source artifacts. Do not regenerate accepted outputs until these tests pass.
4. Requalify every C1 profile and both deterministic producer passes against the new format/parser; refresh qualification pins. The current C1 pass report is stale under the v1 MEDIA cap.

This design closes only the representational gap. It does not define resource eviction, CE-pointer pinning, DMA/GS fences, resident-owner capacities, or a general lifetime protocol; those remain separate C2.4 evidence requirements.
