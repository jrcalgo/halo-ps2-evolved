# C3 HUD resident bitmap optimization — 2026-10-25

## Scope

This change adds a per-map-generation descriptor cache for CE HUD bitmap dispatch. The strict public `hcu_bitmap_dispatch_request()` API remains available and continues through the fully verified cold path. The C3 queue reader opts into resident mode through `hcu_bitmap_dispatch_resident_bind()` after its profile and expected generation are set.

The implementation was first checked with source and host tests, then compared in a controlled one-view PCSX2 recompiler A/B run documented below. The run demonstrates this workload's improvement; it does not establish real-console timing or general C3 qualification.

## Resident-generation contract

The resident table stores pointer-free facts about a successfully decoded image: profile ID, map generation, chunk ID and SHA-256, expected source datum, image index, cache key, dimensions, pixel format, mip size and CLUT size. It does not retain decoded pixels or CLUT bytes. Those upload sources remain in the existing per-kick upload pool until the paired upload and draw work is fenced.

On dispatch, a descriptor is usable only when its profile and generation match the bound context and its chunk, source datum, image index, cache key and expected SHA-256 match the current binding. A hot path additionally requires the texcache map entry to refer to a valid entry with the same key and `pending_upload == 0`. It then reconstructs the validated image metadata without looking up or reading the package, hashing bytes, or parsing TEXS data. It still calls the normal texcache acquisition path and takes a GPU lease for each draw.

Resident mode treats the already verified texture in VRAM as the resource for that generation. Changing backing-file bytes does not change or invalidate an existing resident draw. A cold reload after eviction verifies the current backing and rejects corrupted bytes; a new profile or map generation requires rebinding. The strict public API retains its per-call backing verification. Host tests explicitly distinguish these contracts: corrupted backing is rejected by strict dispatch, remains irrelevant to a resident hit, and is rejected again when resident dispatch must reload it.

A cold request looks up the chunk and checks its SHA-256 identity, stages and verifies the chunk, parses TEXS, validates the selected image and then builds the upload and geometry work. The descriptor is published only after geometry emission succeeds and the texcache journal is committed. Failures in the transactional upload/geometry path restore both chains and roll back texcache mutations; descriptor contents are not published from a failed request.

`hcu_asset_profile_read_chunk_staged_profiled()` performs the cold payload read into the final staging buffer while computing segment and logical hashes in that pass. Once lookup and capacity checks have succeeded, a read, metadata or hash failure clears the chunk-sized destination before returning. Argument, lookup and capacity failures occur before payload publication and leave the destination untouched. The existing non-staged `hcu_asset_profile_read_chunk()` path remains used by the strict compatibility API.

Descriptors are bound only after map profile and generation are initialized. At map release, the frame owner must first prove there are no live leases and unbind; only then does the caller reset resident descriptors and clear the dispatch context. A bind/reset attempt while dispatch leases are outstanding is refused or ignored, respectively.

## Bounded memory

The live C3 owner allocates a fixed table of 64 descriptors inside the existing 400 KiB bitmap-owner tail. The descriptor structure is 80 bytes on the target ABI, so the table uses 5,120 bytes. The bytes are included in the owner's preflight budget before allocation; they do not enlarge the reserved owner region. `HCU_C3_BITMAP_RESIDENT=0` disables the allocation and binds a zero-capacity table. The default is enabled.

The descriptor table is deliberately bounded. It retains metadata for up to 64 unique cache keys in one map generation; a cache miss for a key without a descriptor uses the verified cold path. Pixel and CLUT lifetime remains governed by the existing source-slot and GPU-fence lease mechanism, not by descriptor lifetime.

## Verification recorded

The resident-dispatch host fixture exercises a cold request followed by a hot request, verifies that the hot request does not add backing reads, hash checks or parses, compares emitted command bytes with the strict API, and exercises generation/profile mismatch and lease-protected reset behavior. It also checks that resident requests in distinct view rectangles emit their own scissor state. The source publishes a descriptor only after successful geometry emission and journal commit. The existing rollback assertions cover cache and chain state on rejected upload/geometry work.

The staged profile reader's tests cover segmented HCP2 reads and destination clearing on payload/hash failures. The change was reported with 23 source host tests plus one resident-dispatch fixture passing. These are host-side checks of parsing, cache/chain transactions and command construction; they do not execute the guest on EE, exercise the GS, or observe hardware DMA fences.

## A/B methodology

Build two clean C3 ELFs from the same source and generated profile/workload, in separate output directories so timing flags cannot reuse stale objects:

| Variant | `HCU_C3_BITMAP_RESIDENT` | `HCU_C3_TIMING` | `HCU_C3_TELEMETRY` |
|---|---:|---:|---:|
| Baseline | 0 | 1 | 0 |
| Resident | 1 | 1 | 0 |

Run the same map and deterministic C3 workload in the same PCSX2 mode and profile for both. Keep the startup/warmup policy and sample frame numbers identical. Compare the sparse `c3-timing` records by guest frame and host log timestamp, and compare `c3-hud-perf` counters for hits, misses, source loads, read calls/bytes, hash checks and parses. Use sustained samples after warmup to calculate host-observed frames per second as `(last_frame - first_frame) / (last_log_timestamp - first_log_timestamp)`. Report that value separately from the guest phase measurements. Preserve the ELF hashes, build flags, package/profile hashes, launch manifests and logs for both variants.

`docs/emulator.md` describes the isolated desktop launch and sparse timing-sample method used for C3. The completed pair below used the same workload in both variants; a source-level host test alone would not establish a runtime improvement.

## Runtime result

### Controlled pair result: pass

The strict and resident variants used the same pinned package, Blood Gulch map, one-view/one-player workload, 180 rendered frames, neutral input and PCSX2 recompiler mode. The manifests agree on the controlled inputs, with the resident build flag as the intended difference; the A/B report has no errors. The resident HUD dispatch substantially reduced the measured callback cost and preserved the final captured RGB image exactly.

Host-log timestamps for frames 30 and 150 give the sustained FPS interval (120 frames):

| Variant | Frame 30 host time | Frame 150 host time | Elapsed | FPS |
|---|---:|---:|---:|---:|
| Strict | 113.7865 s | 165.8382 s | 52.0517 s | 2.3054 |
| Resident | 103.5225 s | 111.5305 s | 8.0080 s | 14.985015 |

This wall-clock FPS uses PCSX2 log timestamps. It is separate from the guest COP0 timer measurements below. In the warm samples at frames 30, 60, 90, 120 and 150, strict dispatch averaged 16 misses/source loads and 1,580 reads (318,400 bytes) plus 16 parses and 16 hash checks per sample. Resident dispatch averaged 16 descriptor/cache hits and zero misses, source loads, read calls/bytes, hash checks or parses. At frame 30 resident totals were 13 source loads and 282 reads; no further reads occurred in the warm samples. The strict `hash-ms=0.000` field is uninstrumented for that legacy hash path and must not be read as zero hash cost.

The guest phase timings averaged across those same warm frames:

| Guest phase | Strict | Resident |
|---|---:|---:|
| HUD emit/dispatch | 366.901 ms | 0.985 ms |
| Frame-end kick | 366.924 ms | 1.008 ms |
| Close-frame remaining work | 0.012 ms | 0.012 ms |
| View build | 26.326 ms | 26.326 ms |
| Full render callback | 407.853 ms | 40.637 ms |

At printed precision, warm-frame setup and upload DMA wait fields are `0.000 ms`; this does **not** mean the waits or fences were removed. The resident first-frame record shows an upload of 433 qwords and a 0.133 ms upload DMA wait. The renderer retains its DMA wait and fence paths. The current guest callback is still about 40.6 ms, above the 33.33 ms budget for 30 FPS; view construction at about 26.3 ms is now the largest measured CPU phase. The pair establishes this one-view Blood Gulch result only, not 30 FPS or general C3 renderer qualification.

Both frame-180 captures are 640×480 and have identical decoded RGB SHA-256 `89868a66d045afb0fd046b4d0d00d59b90b45389590591b17ffab141bf3f0a85`, with zero differing pixels. The known oversized/intersecting first-person geometry remains unchanged. The exact screenshot PNG file SHA-256 is `4a20b86cc4eb2f08922856666bc233fb293838d41a64fe673fab5df4c7be001e` for both captures.

### Reproducibility artifacts

The paired launch manifests identify the exact ELF, profile, flags, working directory, and complete source-pin list. Both variants used package SHA-256 `23d41d49c5e755da415f068e6420745eca8d51a71474d40c7335cca834273aac`.

| Item | Strict | Resident |
|---|---|---|
| ELF SHA-256 | `366da6db032083a668d54c0000f8c448ec0bc972a6b55e8b0b3c39147cbf67a2` | `2562480ba6ceb4c87febef3d6e98dfc7362b6874bd9fce4750cfd5096a81ac36` |
| Launch manifest | [`strict/desktop-launch.json`](../../build/c3/perf/hud-resident-ab-20261025-r1/strict/desktop-launch.json) | [`resident/desktop-launch.json`](../../build/c3/perf/hud-resident-ab-20261025-r1/resident/desktop-launch.json) |
| Emulator log | [`strict/play/ab-20261025T212521Z-emu.txt`](../../build/c3/perf/hud-resident-ab-20261025-r1/strict/play/ab-20261025T212521Z-emu.txt) | [`resident/play/ab-20261025T212823Z-emu.txt`](../../build/c3/perf/hud-resident-ab-20261025-r1/resident/play/ab-20261025T212823Z-emu.txt) |
| Frame-180 capture | [`strict/frame-180.png`](../../build/c3/perf/hud-resident-ab-20261025-r1/strict/frame-180.png) | [`resident/frame-180.png`](../../build/c3/perf/hud-resident-ab-20261025-r1/resident/frame-180.png) |

The matching build source pins cover `src/stream/hcu_asset_profile.[ch]`, `src/stream/hcu_bitmap_dispatch.[ch]`, `src/stream/hcu_bitmap_quad.[ch]`, `src/stream/hcu_main.c`, `submodules/halo-ps2/engine/src/render/bsp_render.[ch]`, `submodules/halo-ps2/engine/src/render/chain.[ch]`, `submodules/halo-ps2/engine/src/render/storage.h`, and `tools/ee-world.mk`; the per-file SHA-256 values are in both launch manifests. The aggregate result is [`report.json`](../../build/c3/perf/hud-resident-ab-20261025-r1/report.json), with the readable summary at [`report.md`](../../build/c3/perf/hud-resident-ab-20261025-r1/report.md).

The separate long-running quiet interactive build (108,000 rendered frames, resident enabled, timing and telemetry disabled, FPS OSD enabled) was built and launched on the desktop. Its ELF SHA-256 is `b181441df5e2639a0c4f83327a8bb70b5c3cbdc64ca957b7b14932f4cbec1aeb`. The per-frame timing, HUD and submission diagnostic strings are absent from the ELF and the live log. The retained capture visibly shows Blood Gulch, HUD and the unchanged first-person geometry defect. Scripted firing is disabled; the isolated profile restores arrow-key look, Control crouch, F fire, G jump and WASD movement.

The launch and active records are under [`build/c3/perf/hud-resident-quiet-20261025-r1/resident/`](../../build/c3/perf/hud-resident-quiet-20261025-r1/resident/), with [`gameplay-quiet.png`](../../build/c3/perf/hud-resident-quiet-20261025-r1/resident/gameplay-quiet.png) and `play/desktop-20261025T213229Z-emu.txt`. This visible quiet session is separate from the controlled timing measurements above; no log-based FPS result is claimed for the quiet ELF.

### Scope and remaining qualification

The A/B result qualifies the isolated optimization under one view, Blood Gulch and PCSX2 recompiler. It does not qualify all C3 maps, multi-view behavior, hardware DMA timing, or the renderer as a whole. The visible capture still has the known oversized/intersecting first-person geometry. The resident cache removes repeated backing I/O, hash verification and TEXS parsing for warm resident requests; the next measured CPU bottleneck is view construction, and the current result remains below the 30 FPS target.
