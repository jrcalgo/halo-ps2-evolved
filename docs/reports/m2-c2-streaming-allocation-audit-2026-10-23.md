# C2 bounded streaming and allocation audit (2026-10-23)

## Scope and disposition

Source-backed review of C2 requirements 4–5 in `plans/7.hcu-remake-m2-m4.md`. This report does not claim either requirement complete. It reviewed the HCP profile chunk reader, HP2 section visitor/loader, CTAG/BSP mount lifetimes, bitmap reader leases, CE PS2 allocator, and focused allocator diagnostic. The allocator implementation has since gained a size-aware arena header, free-block reuse/coalescing, and realloc preservation; this report reflects that current shared-worktree state.

## C2.4: chunk bounds and ownership

There are two different chunk concepts in the current tree:

* HCP profile files have a sorted directory of `(type, chunk_id, offset, size, sha256)` entries. Preflight hashes chunks incrementally using a fixed 16 KiB local buffer; `hcu_asset_profile_read_chunk()` verifies a chunk and copies it to caller storage. That path is bounded by the profile's declared chunk size and the caller's destination capacity ([`hcu_asset_profile.h`](../../src/stream/hcu_asset_profile.h), [`hcu_asset_profile.c`](../../src/stream/hcu_asset_profile.c)). C1's asset builder emits resources as package chunks, but profile chunk size is not itself enforced at 64 KiB by the generic reader.
* HP2 `world_visit_section_reader_with_scratch()` decodes section output incrementally using 64 KiB history and fixed input/output buffers. A visitor can therefore process output in bounded callbacks, while the compatibility `world_load_section_with_scratch()` still reserves the entire decoded logical section in its destination arena ([`section.c`](../../submodules/halo-ps2/engine/src/world/section.c)). The visitor's transient callback granularity is bounded; this does not mean persistent map/resource residency is chunked.

The current mount still retains the complete CTAG image in CE's fixed tag-cache span and an active CBSP payload for the map lifetime; CRNG/CBIX and relocation metadata also have map-owner lifetimes ([`ctag_mount.c`](../../src/stream/ctag_mount.c), [`ps2_cache.c`](../../submodules/halo-ce-universal/port/ps2/src/ps2_cache.c)). This is a whole-map image ownership model, not independently evictable <=64 KiB runtime pieces. The 64 KiB HP2 history ring is a decoder back-reference window, not a decoded resource chunk limit.

There is explicit reader accounting for HCP bitmap resources and GPU leases: profile reload checks drained readers; the renderer releases dispatcher leases only at frame completion after the kick fence ([`hcu_bitmap_frame.h`](../../src/stream/hcu_bitmap_frame.h), [`hcu_bitmap_renderer.h`](../../src/stream/hcu_bitmap_renderer.h), [`hcu_map_service.c`](../../src/stream/hcu_map_service.c)). That accounting is specialized to the bitmap/frame path. The CTAG/BSP owners instead rely on synchronous CE cache lifecycle and BSP release callbacks; there is no general resource pin count covering all CE pointers plus DMA/GS readers, nor a generic eviction API that proves a resource has no gameplay pointer. Thus the required lifetime rule is only partially implemented.

**Finding:** bounded decode exists and package resources are directory-addressable, but the <=64 KiB independently decoded residency/eviction contract and general CE+DMA reader pin contract are not established. No safe general eviction policy can be claimed from current source.

## C2.5: allocation and free semantics

The current PS2 compatibility allocator stores a 16-byte-aligned header per block, scans the arena for a first-fit free block, splits sufficiently large remainders, and coalesces adjacent free blocks. A freed tail can rewind the arena cursor. `__wrap_realloc()` reads the recorded old requested size, allocates a replacement, copies `min(old_size,new_size)`, and frees the old block only after successful allocation. On allocation failure, the old allocation remains live. Size zero frees and returns null. These semantics are implemented in [`ps2_memory.c:333-469`](../../submodules/halo-ce-universal/port/ps2/src/ps2_memory.c#L333) and [`ps2_memory.c:518-590`](../../submodules/halo-ce-universal/port/ps2/src/ps2_memory.c#L518).

`GlobalReAlloc()` remains a separate CE debug-heap adapter. It handles null and zero-size cases, derives the old user extent from the CE debug header at offset 12, copies `min(old-header+trailer, requested-size)` bytes, and releases the old block only after successful allocation ([`ps2_memory.c:649-682`](../../submodules/halo-ce-universal/port/ps2/src/ps2_memory.c#L649)). Its correctness still depends on the documented live caller being `system_realloc` with that debug-header layout.

The focused diagnostic `python3 tools/test_hcu_ps2_malloc_diagnostic.py` passes. Its host fixture checks preboot realloc preservation, 16-byte alignment, successful realloc copy, failed realloc preserving the old block, freed-block reuse, coalescing, failure counts, and reset on rebind. It reports an allocator high-water of 224 bytes for that small synthetic sequence. This is allocator behavior evidence only, not a workload allocation trace.

First-fit allocation scans block headers linearly from the arena start; free validates a candidate pointer by scanning headers, then scans/coalesces spans. Worst-case allocation/free work is therefore O(number of blocks), with no EE cycle/timing bound measured. Header corruption is treated as allocation/free failure, but there is no external integrity table. The opt-in `HALO_PS2_STEP8_MEMORY_DIAGNOSTIC` reports compatibility-arena capacity, current used/high-water bytes, and failures. It does not cover game-state allocation, object pool, actor/prop/swarm pools, graphics or GS/IOP/SPU2 ([`m2-step8-malloc-arena-telemetry-2026-10-22.md`](m2-step8-malloc-arena-telemetry-2026-10-22.md)). No broad post-load allocation-site trace has classified recurrent path/bot/renderer/wave/mode operations under sustained gameplay workloads.

**Finding:** the allocator's former no-op-free and realloc-copy defects are corrected and focused host behavior passes. C2.5 remains open pending broad post-load allocation-site evidence, target timing/fragmentation behavior under repeated churn, and owner-level peaks/failure/reset telemetry. No steady-state SDK heap fallback after arena activation is enforced at the wrapper path, but source/runtime evidence does not establish that every subsystem routes all steady-state allocations through it.

## Focused next work

1. Add allocation-site tracing at actual post-load boundaries, with owner, size, call phase, and free/realloc outcome; classify recurrent AI/path, bot, renderer, wave, and mode operations under the required workloads.
2. Measure first-fit scan duration and fragmentation/reuse under representative repeated churn on EE or exact guest workload; host unit behavior does not bound target costs.
3. Define profile resource chunks with a <=65,536 decoded-byte limit (or a segmented-resource schema), then prove per-chunk decode/release and stable references. Add a shared pin/fence ownership protocol for CE pointers and DMA/GS readers before eviction.
4. Measure per-owner high-water and failure/reset values in target or exact guest workloads; existing malloc-only telemetry is insufficient for C2 exit.

## Source pins

The findings are based on the checked-in sources cited above as of 2026-10-23. The earlier CTAG and HP2 audit reports describe historical whole-section blockers and remain useful for transaction details. The allocator conclusion also uses the focused host diagnostic above; no guest or performance result is inferred from it. No broad workload allocation-site trace is available.

Current allocator evidence SHA-256: `ps2_memory.c` `4dbda430de9fbc7d3f51cbf5dfc01e51ffd303f6c1cd8d4b4a2d6d20caa120f9`; diagnostic fixture `tests/hcu_ps2_malloc_diagnostic_main.c` `9c48a8e96edb16020699e539de81c3d0d7105191491eb8bdb8edd5baac635a09`; runner `tools/test_hcu_ps2_malloc_diagnostic.py` `bdf0bfd7cdccc8a4c46a51ff4615c9ac32cfe02cef3f946122141611e072fcd0`. The run emitted `preboot-realloc=preserved align=16 high_water=224 failures=3 free=coalesced-reuse rebind_reset=passed`.
