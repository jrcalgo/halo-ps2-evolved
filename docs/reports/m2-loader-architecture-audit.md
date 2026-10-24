# M2 loader architecture and bounded-memory audit

**Scope:** report-only review of the parent HP2 reader, HCU map service, CTAG/CBSP adapter, CE map lifecycle, and current arena use. This is an architecture recommendation, not an implementation or map-fit qualification. The review is tied to the worktree state inspected on 2026-10-20; the M2 plan and runtime gates remain authoritative.

## Executive finding

The present UI path works because the UI package is exceptionally small, not because the loader is sized for stock maps. The current transaction stages every selected decoded section in the 1.5 MiB `streaming` arena during preflight and mount, retains CTAG/CRNG/CBIX bytes there for the whole map lifetime, and loads an entire CBSP encoded section into `frame_scratch` before materializing it in `current_bsp`. The persistent CTAG wire payload is not the same as its destination image: `ps2_ctag_open` exposes the image inside the payload, and CE later materializes that image into the separately bound tag cache.

This layering has several consequences:

1. A stock-map package is rejected before loading by `hcu_map_service_preflight` (`src/stream/hcu_map_service.c:179-185`), so no current runtime code proves its capacity.
2. Simply deleting the UI-only guard is unsafe. `world_load_section_with_scratch` needs a contiguous owner allocation equal to the raw section size plus a contiguous scratch allocation equal to the stored section size (`submodules/halo-ps2/engine/src/world/section.c:58-78`). A typical retail CTAG section alone is about 4.2–4.6 MB raw, far above the 1,572,864-byte streaming arena (`docs/reports/retail-ctag-compaction-2fba411b-v2.json`, map image/payload rows; `config/memory-budget.json:16`).
3. The 2 MiB tag cache configured for the current UI diagnostic is not a retail capacity claim. `src/stream/hcu_memory_bind.c:30-49` places that cache in `current_bsp` before binding the remainder as the CE BSP cache; the default and diagnostic rationale are recorded in `src/stream/hcu_main.c` and `tools/hcu_parent_link_probe.py:336-343`.
4. At least some standard maps may be representable with a revised, measured partition: the current lower-bound report puts Blood Gulch at a 4,477,116-byte compact CTAG image and a 1,066,832-byte projected active BSP, totaling 5,543,948 bytes before excluded data/peak overhead, within the *sum* of `resident_gameplay` + `current_bsp` (13,107,200 bytes), but not in today’s 2 MiB tag span and 4 MiB BSP remainder. This is only a lower-bound feasibility screen; it expressly excludes staging, validation scratch, packs, alignment, and transition peaks (`docs/reports/retail-map-working-set-a4-current.json:139-168`). A10 and other maps exceed the combined-region lower bound and cannot be repaired by repartitioning only those two regions.

## Current path and ownership

### Section reading and decompression

`world_load_section_with_scratch(owner, scratch, ...)` rejects overlapping arenas, reads the HP2 header into a static bounded header buffer, allocates `raw_size` from the owner and `stored_size` from scratch, reads the stored bytes, expands via `hp2_load_stored`, releases scratch, and leaves decoded bytes owned by the caller until rollback/release (`submodules/halo-ps2/engine/src/world/section.c:23-91`). This gives sound per-section rollback, but requires the full raw section as one contiguous allocation and has no chunked decoder/destination interface.

The map service selects `streaming` as `map_arena` and `frame_scratch` as `section_scratch` (`src/stream/hcu_map_service.c:131-139`). Preflight marks the streaming arena, loads HMAP, CTAG, CRNG, and CBIX sequentially into it, validates each, hashes the source, and then releases the whole temporary transaction (`src/stream/hcu_map_service.c:214-236`). The whole map transaction repeats those reads; CTAG and CRNG are retained, then CBIX is appended (`src/stream/ctag_mount.c:112-156`, `:218-252`).

Current UI-specific host tests pin section sizes and peak use: raw CTAG is 1,547,396 bytes, CRNG 2,900 bytes, stored CTAG 275,491 bytes; the isolated section fixture reports streaming peak 1,550,356/1,572,864 (`tests/test_world_section_capacity.py:14-18`, `:47-48`). The full service fixture reports 1,550,572/1,572,864 at preflight and 1,550,444/1,572,864 at mount (`tests/test_retail_ui_ctag_mount.py:54-57`). This leaves only about 22 KiB and is not scalable to retail campaign/multiplayer packages.

The M2 Step 7 report records a real retail Blood Gulch `B000` CBSP section of 1,303,092 bytes, normalized BSP image 1,296,384 bytes, and 463 BSP plus 93 CTAG-name relocations (`docs/reports/m2-step7-retail-cbsp-validation.md`, “Reproducible fixture identity”). The encoded section is larger than `frame_scratch` (393,216 bytes); thus the existing whole-section CBSP loader cannot be used for Blood Gulch as-is even if the final BSP destination span is sufficient. `ctag_mount.c:57-102` currently loads the whole selected section into that scratch arena, retains it until CE consumes the BSP request, then releases it.

### Tag-cache destination and pointer lifetime

`ps2_cache_mount_ctag_with_file_source` validates the CTAG envelope against the physically bound tag-cache capacity, then retains pointers to the source payload and read callback (`submodules/halo-ce-universal/port/ps2/src/ps2_cache.c:79-110`). CE requests the tag image as one exact cache-file extent; `cache_file_read` calls `ps2_ctag_materialize` into the physical tag-cache base (`ps2_cache.c:343-359`). The materializer copies the complete compact image and rebases its relocation table in place (`submodules/halo-ce-universal/port/ps2/src/ps2_ctag.c:159-180`). Therefore CTAG payload storage must remain valid through `scenario_tags_load` and any subsequent reads needed by the mounted cache; the final materialized tag image must remain resident for the entire scenario lifetime because tags/scenario/object data contain pointers into it.

The parent owner encodes this lifetime today: `ctag_mount_unload()` unregisters BSP loading, unmounts the PS2 cache, closes the virtual-file source, and releases the owner arena to its transaction mark (`src/stream/ctag_mount.c`, unload implementation). CE calls that only after clearing scenario, BSP, collision, and game-global pointers (`submodules/halo-ce-universal/source/scenario/scenario.c:371-389`). Do not move release earlier or treat a successful preflight as authorization to overwrite the current tag cache.

### BSP ownership and cache lifetime

The selected CBSP is mapped by exact retail file extent through CBIX; only one BSP is active at a time (`halo_ps2_cache.h:43-58`, `ps2_cache.c:169-197`). CE asks for the original BSP file extent, the parent loads the matching CBSP, the adapter materializes it to the structure BSP cache, then releases encoded CBSP scratch (`ps2_cache.c:304-339`). The final materialized BSP occupies `current_bsp` and has its own lifetime until CE unloads/replaces the active BSP. CBSP pointer domains can target either the BSP image or CTAG tag image, so the materialized tag image must already be live and stable when the BSP is materialized. The real Blood Gulch parity test proves Python/PS2-C materialization bytes match, but not CE BSP verifier/consumer acceptance or target arena fit (`docs/reports/m2-step7-retail-cbsp-validation.md`, “Still required for Step 7”).

## Retail sizes and limits of current evidence

The current A4 working-set report is a lower-bound screen, not a buffer-size prescription. Selected rows:

| Map | Compact CTAG image | Projected largest active BSP | Sum | Interpretation |
|---|---:|---:|---:|---|
| UI | 1,510,628 B | 2,048 B | 1,512,676 B | Current UI package fits streaming staging only because CTAG’s *compressed stored extent* is small; current tests measure this path. |
| Hang ’em High | 4,246,076 B | 380,392 B | 4,626,468 B | Candidate map remains unqualified; tag destination and transaction design need changes. |
| Blood Gulch | 4,477,116 B | 1,066,832 B | 5,543,948 B | BSP fits the current BSP remainder only if tag-cache reservation is reduced, but compact CTAG cannot fit current 2 MiB tag cache. |
| A10 | 9,622,260 B | 4,736,728 B | 14,358,988 B | Exceeds the combined 13,107,200 B resident+BSP regions even before excluded working set; cannot fit by repartitioning those two regions alone. |

Source: `docs/reports/retail-map-working-set-a4-current.json` (the map rows and top-level exclusions). “Projected active BSP” is a projection after hypothetical externalization of compressed BSP vertex data; that transformation and its consumers require separate validation. The report excludes `streaming`, frame scratch, tag-validator claims, PS2 renderer packs/texture cache/audio, alignment, and load/unload overlap. It therefore cannot establish retail map fit.

Animation data is a particularly important non-solution: the current proposal intentionally retains `animation.data` in its CE-compatible in-image layout and refuses to authorize externalization or budget transfer until pointer consumers and simultaneous leases are measured (`docs/reports/m2-budget-proposal-animation-data-v1.md`, “Decision” and “Reconsideration gates”). Do not rely on its hypothetical externalization column to make a loader fit.

## Recommended bounded-memory architecture

The following is a design for implementation, with a clean separation between persistent residents, transient decode work, and one active BSP. It does not change the 32 MiB budget or consume the reserved interval.

### 1. Treat map opening as a section-indexed transaction, not “load sections into streaming”

Add a bounded HP2 section descriptor/index operation that reads and validates the fixed-size pack header/table once, stores at most the fixed maximum section metadata in a small caller-owned descriptor (or the existing static header-sized representation), and records each section’s raw size, stored size, offset, codec, and CRC. Do not materialize every decoded section merely to preflight. Reject duplicate tags, overflowed extents, unsupported codecs, and pack/source identity mismatch before any persistent store is modified. HP2 already bounds section count/header parsing; build on that instead of introducing dynamic allocation.

Make source SHA validation a bounded streaming pass over the original map file using the existing scratch buffer, as `verify_source_hash` already does in chunks (`src/stream/hcu_map_service.c:26-52` and the source hashing callback). Preserve the exact source identity linkage from HMAP; do not read all source bytes into an arena.

### 2. Decode CTAG directly into its final physical tag-cache span

Add an HP2 decode-to-sink/stream API that feeds the decompressor in bounded blocks (proposed initial buffer: one measured 16–64 KiB aligned scratch window, to be confirmed against codec behavior and EE tick/I/O constraints) and computes stored/raw CRC incrementally. For the CTAG wire format, place the small CTAG envelope/relocation list in bounded transient metadata, but write the final tag image directly into the physical `tag_cache` destination after validating the image-size capacity and the CE tag-header invariants. Avoid a second full compact-image buffer in `streaming`.

Because the current CTAG CRC covers the entire image and `ps2_ctag_open` validates relocations by scanning the entire payload before materialization (`ps2_ctag.c:72-156`), implement a two-pass-safe strategy: first pass validates pack section, envelope, image CRC, CE tag header, relocation ordering/ranges, and destination capacity without mutating the published destination; second pass decodes/copies into a *staged* tag-cache span and applies rebasing. If memory cannot hold old and staged maps concurrently, then map replacement must be explicitly destructive after the current CE scenario is unloaded, with a rollback contract that leaves a diagnosed unloaded/menu state rather than pretending to restore the prior map. Do not mutate the active cache during the non-mutating `ps2_cache_preflight_map` callback.

Do not change source pointer semantics: after publication, every CE pointer targets the final fixed tag-cache address; the staging envelope/relocation table can be released once the tag image and required source-read metadata are committed. The resource-index/virtual-file reader must remain valid for out-of-image cache reads (sound/bitmap resources) throughout the map, and those bytes must be served from original map extents or another separately measured destination cache.

### 3. Keep only bounded metadata and one active BSP resident

The current resident map needs: one final CTAG image in the tag-cache span; the CE/BSP cache remains a separate destination; a compact CRNG interval index and CBIX catalog (both bounded by map contents and validated against pack extents); HMAP identity; and file-source handle/context. CRNG/CBIX can be retained as compact parsed records rather than the original full section buffers, but record counts and bytes must be explicitly bounded per map and included in the resident ledger. The whole HP2 CTAG envelope, CRNG wire payload, and CBIX wire payload should not occupy streaming for the full map lifetime.

For BSP requests, use the existing one-BSP-at-a-time contract. Decode the CBSP section with bounded scratch into the final `current_bsp` destination while validating and rebasing its relocation records. Preserve target-atomicity: do not expose CE BSP globals or mark the read complete until the complete section passes envelope, checksum, extent, relocation-domain, CTAG-name, and materialization checks. Since destination may be partially written on error, CE must not publish it until success; on failure zero/poison only the unpublished span or reload the prior BSP if the map remains active. Current `ps2_cbsp_materialize` accepts a whole payload pointer; it needs either a streaming two-pass decoder or a bounded CBSP iterator API before full Blood Gulch sections can fit scratch.

Keep BSP package bytes out of `frame_scratch` after the destination copy is validated. `frame_scratch` must be available to per-frame/render work; it should not become a hidden persistent map store.

### 4. Define old/new map transition semantics before enabling non-UI map names

The current flow preflights before CE teardown and deliberately preserves the old mounted owner on invalid target package (`tests/ctag_mount_main.c:305-341`). Once preflight succeeds, CE’s actual map-load transition must be verified to call `scenario_unload()` before any write to the single physical tag/BSP spans; the release callback ordering is visible in `scenario.c:371-389`. Tests need to establish that:

- invalid/missing/corrupt new package: old map remains active and readable, no arena/cache state changed;
- valid new package before teardown: old map remains active, staged state is metadata/source-only and bounded;
- after old scenario unload: old owner closes, tag/BSP stores become available, new image loads and validates;
- failure after teardown: no dangling old/new pointers; CE remains in a deterministic menu/error state and can retry another map;
- successful load: only then `cache_files_precache_map_loaded(new_name)` becomes true and CE proceeds to `scenario_tags_load`;
- unload/reload same map and repeated map switching leave arenas/file descriptors at stable marks and do not leak.

If old+new CTAG is required for a true rollback and cannot fit simultaneously, state this as a deliberate no-rollback-after-unload boundary. Preflight can still guarantee the packaged candidate is structurally sound and fits its planned regions before unload; actual I/O failure after destructive switch must be explicit. Never claim fully transactional rollback if destination stores are overwritten in place.

### 5. Capacity qualification must be map-specific and include simultaneous peaks

For every proposed supported map, generate a source-hash-pinned ledger of:

- final compact CTAG image and relocation bytes;
- CE validator bitmap/scratch and all CE allocations that coexist with tag bytes;
- active BSP destination bytes (with exact evidence for any omitted/externalized vertex/index data);
- retained CRNG/CBIX metadata, HP2 descriptor/source state, virtual-file read scratch;
- texture/model/animation and HP2/renderer-pack residency that overlaps map load;
- peak scratch buffers for decompression, SHA, CBSP parse/materialization, and error cleanup;
- old/new overlap or explicit post-unload destructive-switch peak;
- arena high-water, alignment/padding, and physical EE addresses/canaries.

Use the diagnostic UI, Blood Gulch, a small multiplayer map, and an over-budget campaign map (e.g. A10) to verify both admission and intentional rejection. For “all stock maps,” run the ledger against all 24 stock maps; do not extrapolate from Blood Gulch. Leave `5,767,168` bytes reserved in the EE map (`docs/memory.md`, `config/memory-budget.json`).

## Concrete implementation sequence and tests

1. **Instrument current sizes/lifetimes (no policy relaxation):** add test assertions/trace fields for each HP2 section’s stored/raw sizes, arena mark before/after, peak scratch, and payload owner. Extend `tests/test_world_section_capacity.py` to run several real packages and prove precise expected failures for current retail CTAG/CBSP overflow; retain UI as positive control. This is diagnostic only.
2. **HP2 bounded decode API:** host-test malformed headers, arithmetic overflow, truncated stored payload, bad raw CRC, unsupported codec, exact-fit buffers, one-byte-short buffers, and rollback. Run a target compile. Compare streamed decode output byte-for-byte with existing `world_load_section_with_scratch` on UI, Blood Gulch CTAG, and Blood Gulch B000. Capture EE cycles/I/O/block duration; verify scratch remains bounded independently of raw section size.
3. **CTAG staged destination materializer:** validate on a candidate destination not yet published; verify whole-image and relocation checks, exact address fixups, no destination changes on rejected inputs, and high-water at the expected fixed tag span. Exercise retail UI then Blood Gulch. Ensure final CE pointers are based at physical tag-cache address; do not use host pointers as simulated target values in the production fixture.
4. **Compact mounted metadata and virtual-file lifetime:** parse CRNG/CBIX into bounded records and discard their encoded bytes; verify all CRNG interval reads and CBSP catalog lookups match old parser behavior. Stress synchronous random file extents and source close only on owner unload. Include source-hash mismatch and corrupt late-read cases.
5. **Streaming CBSP materialization into current_bsp:** read/validate CBSP first pass; decode a second pass directly into the unpublished BSP span; resolve domain-1 strings against the already-published tag image; byte-compare against `tools/cbsp.py` materialized output for real Blood Gulch and one structurally different BSP. Ensure no scratch allocation exceeds the selected bounded window.
6. **Map-transition test harness:** use callbacks that instrument CE unpublish/unload, parent owner release, preflight, staging, cache publication, and `scenario_tags_load`. Assert exact order and outcomes for success, invalid target, I/O fault at each read boundary, decoder fault, capacity refusal, retry, and same-map reload. Add a full CE integration test once the new map path can reach CE `structure_bsp_port_verify` and queries.
7. **Map admission and target acceptance:** keep non-UI catalog entries denied until each map's complete ledger passes, run R5900 closure, then PCSX2 interpreter/recompiler with the exact ELF+package hashes and physical arena diagnostics. At least one real BSP must pass CE verification and collision/surface/PVS/sound queries before calling the path a loaded gameplay map. A rendered scene is a later presentation gate, not implied by `m2-ui-map-loaded`.

## Open decisions / blockers

- Whether production map switching promises restoration of the old campaign after a post-unload storage failure, or only guarantees preflight survival and leaves the game safely at menu on later I/O failure. The current single tag-cache/BSP spans cannot hold arbitrary old+new images.
- Exact compression codecs and ability to incrementally decode HP2 sections. This determines whether a bounded scratch window is feasible without temporarily storing large raw CTAG/CBSP data elsewhere.
- Exact resident ownership of CRNG/CBIX parsed forms, source file descriptors, and out-of-tag-file cache reads across USB, SMB, HDD, ISO/disc. Their byte counts and latency must be measured.
- Map-specific placement after preserving all source data: the A4 report rules out several maps by a lower-bound sum, while M2 product requirements retain all retail maps. Any actual redesign needs a complete allocation ledger before region sizes or features are changed.
- Target EE latency: synchronous FileXio reads and repeated two-pass decode/hash may stall ticks. Correctness comes first, but measure blocking time and decide whether bounded asynchronous streaming is required without changing CE simulation cadence.

## Source index

- Parent map lifecycle and staging: `src/stream/hcu_map_service.c:55-88`, `:131-160`, `:168-236`.
- Parent HP2 section transaction / lifetime: `src/stream/ctag_mount.c:57-102`, `:112-156`, `:218-252`; unload path in same file.
- PS2 arena split and current tag reservation: `src/stream/hcu_memory_bind.c:18-78`; `config/memory-budget.json:11-19`.
- HP2 full-section allocation and scratch behavior: `submodules/halo-ps2/engine/src/world/section.c:23-91`.
- CTAG validation/materialization: `submodules/halo-ce-universal/port/ps2/src/ps2_ctag.c:72-180`.
- PS2 map/BSP cache pointer lifetime and exact-extent reads: `submodules/halo-ce-universal/port/ps2/src/ps2_cache.c:79-110`, `:169-197`, `:304-380`.
- CE map preflight/load/unload transition: `submodules/halo-ce-universal/source/game/game.c:805-940`; `submodules/halo-ce-universal/source/scenario/scenario.c:371-389`; `submodules/halo-ce-universal/source/cache/cache_files.c:1180-1210`.
- UI capacity fixtures: `tests/test_world_section_capacity.py:14-48`; `tests/test_retail_ui_ctag_mount.py:17-90`.
- Real BSP byte parity and remaining consumer gaps: `docs/reports/m2-step7-retail-cbsp-validation.md`.
- Retail lower-bound map screen and explicit exclusions: `docs/reports/retail-map-working-set-a4-current.json`.
- No animation externalization accepted: `docs/reports/m2-budget-proposal-animation-data-v1.md`.
