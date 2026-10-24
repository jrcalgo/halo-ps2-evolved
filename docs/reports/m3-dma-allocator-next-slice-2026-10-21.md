# M3 Step 13: DMA allocator blocker and measured next slice

Date: 2026-10-21  
Disposition: report-only audit; no code or plan changes.  
Scope: reconcile the current PS2 BSP renderer's EE DMA storage with HCU snapshot staging and the fixed v2 arena, distinguish EE RAM from GS/IOP/SPU2 stores, and propose one measured integration slice. This is not an M3 acceptance report and does not claim a gameplay scene is rendered.

## Executive finding

`dma_commands` is a fixed 1,179,648-byte EE arena. The pinned `halo-ps2` BSP renderer configures two 512 KiB VIF1 geometry chains and two 64 KiB GIF upload chains, whose payload capacities sum to exactly 1,179,648 bytes. The current HCU snapshot publisher separately binds and writes a 4,128-byte VIF matrix staging buffer at the start of that same arena. The current HCU machine does not yet initialize or consume the BSP renderer, so this is a latent ownership collision, not evidence of an observed overwrite. The current snapshot's `publish_dma()` is CPU packing only; it has no production DMA submitter.

There are also two allocator-contract gaps that the simple total misses:

1. `arena_alloc()` supports arbitrary power-of-two alignment, but the v2 layout creates regions at 16-byte alignment. Saved PCSX2 logs include a `dma_commands` base ending in `...bf0` (48 mod 64), so the current arena base cannot universally satisfy the BSP renderer's `memalign(64, ...)` alignment contract without an explicit aligned carve.
2. Raw renderer chains use `memalign()` and packet2 payloads use `memalign()` inside PS2SDK `packet2_create()`. The HCU link wraps `malloc`, `free`, `calloc`, and `realloc`, but not `memalign`; the current source therefore does not prove those DMA payloads are owned by `dma_commands` or any other named bounded arena. `packet2_create()` also separately `calloc()`s its descriptor. Do not count wrapper-routed descriptors and assume their packet data was wrapper-routed too.

The safest next slice is not to shrink renderer chains or borrow the 5.5 MiB reserve. Make the renderer's EE DMA ownership explicit, remove the unused duplicate snapshot staging slab from the production DMA allocation, align the `dma_commands` region at 64 bytes using existing layout-alignment slack, and feed the existing four full-capacity chain buffers from it. Keep all four chain capacities unchanged initially. Before adding packet/object matrices to the chains, measure actual per-buffer high-water on the first M2-qualified real BSP and fail on overflow; place any concurrently live packet2 command payload only in a separately named, measured owner or in demonstrated unused chain capacity. If measurements show the matrices/control packet do not fit, use a measured streaming/chain construction change—not object/view/product cuts or reserve consumption.

## Provenance and limits

| Input | Identity / note |
|---|---|
| Parent HEAD | `70e2ed0cf2145a45d23aa07414a3a88c05155d4c` |
| `halo-ps2` pin | `71183bb0a9adc586cd267b2780c82bbc12cfd95b` |
| HCU pin | `6933490b2d16bb1c637295b6a0f3880ba23a7d56` |
| Halo-64 pin | `17541f4444baabb47d1a0deb917f26ccb7b6bc5c` |
| Current inspected source hashes | `hcu_main.c` `22fbaaa2bab4b73317e042cb3206cb873f47072dab98746bf0d153c33c443ad7`; snapshot implementation `ec56be9a8b7ca2806bbc665e7dc2e72e36c5ca790fd5de0e4f83a8b9fa6bf03b`; BSP renderer `def69c8d881067f9270182fbe7c2ffb066ca4fbbbed8beafabc0b96dd91f5780`; PS2SDK packet2 implementation `a0054ac18f2d6fd02cb51ff1071aeb2ea24ffc9ee94dd30d9722da99162b55b7`; memory budget `67ef6d6085de71c22e3998a355cb2f79a8123837b7b14e89593a0d497de21b74`. |
| Alignment corroboration | Saved guest log [`emulog.txt`](../../build/hcu-ps2-closure/emulator-m1-recompiler-33230a6978924fcca86118febd8b2329/emulog.txt) for result [`result.json`](../../build/hcu-ps2-closure/emulator-m1-recompiler-33230a6978924fcca86118febd8b2329/result.json), ELF SHA-256 `8d3c9aa1dba93b2ad77ef0b37b32ed39d4ad7ad3a33b634ab8521b19bb3ec222`, records `dma_commands base=0x15fdbf0`; this is 16-byte aligned but 48 mod 64. This is memory-layout evidence only, not a render run. |
| Dirty submodule caveat | halo-ps2's unrelated simulation/stream/world files are dirty; the renderer and packet2 sources inspected here match their cited content hashes, but the submodule working tree as a whole is not pristine. |

This audit uses source-level allocation and call-site evidence. REA is not appropriate for the specific question: there is no renderer ELF whose machine code or runtime-only behavior must be reverse engineered to derive these constants. The cited guest log corroborates runtime addresses/alignment, not a rendered scene.

## Byte-level ledger

### `dma_commands`

The budget is fixed in [`config/memory-budget.json:14-20`](../../config/memory-budget.json#L14), and duplicated as the `mem_layout_v2` region capacity in [`engine/src/core/mem.c:62-70`](../../submodules/halo-ps2/engine/src/core/mem.c#L62). Renderer constants and four allocations are in [`bsp_render.c:25-28,104-111,152-171`](../../submodules/halo-ps2/engine/src/render/bsp_render.c#L25):

| Renderer object | Count × capacity | Bytes |
|---|---:|---:|
| Geometry VIF1 chain | 2 × 32,768 qwords × 16 | 1,048,576 |
| GIF texture/lightmap upload chain | 2 × 4,096 qwords × 16 | 131,072 |
| Four chain capacities | 1,179,648 | 1,179,648 |
| Configured `dma_commands` | — | 1,179,648 |
| Free nominal bytes if all four are reserved at full capacity | — | 0 |

The arithmetic is exact. These capacities are maximum buffer sizes, not evidence that any map fills them. `bsp_render_build()` exposes `chain_qw`, overflow state and other render stats after a build ([`bsp_render.c:738-744`](../../submodules/halo-ps2/engine/src/render/bsp_render.c#L738)); no HCU gameplay BSP render has yet produced high-water evidence, so shrinking either constant now would be speculative.

### Snapshot storage and its current overlap

The snapshot is pointer-free and double-buffered: each bank is 134,488 bytes, rounded to 134,496, and both occupy 268,992 bytes of `frame_scratch` (the maximum arrays are declared in [`halo_ps2_render_snapshot.h:8-51`](../../submodules/halo-ce-universal/port/ps2/include/halo_ps2_render_snapshot.h#L8)). `hcu_main.c` binds those banks, then gives map loading only the nonoverlapping remaining `frame_scratch` tail ([`hcu_main.c:331-354`](../../src/stream/hcu_main.c#L331)); with a 393,216-byte region, that tail is 124,224 bytes.

Separately, [`hcu_render_snapshot.c:20-35,38-65`](../../src/stream/hcu_render_snapshot.c#L20) defines a max 64-matrix packet reservation of `(1 + 64*4 + 1)*4` 32-bit words = 4,128 bytes and binds `s_dma_words` directly to `dma_commands` base ([`hcu_render_snapshot.c:38-65`](../../src/stream/hcu_render_snapshot.c#L38)). `publish_dma()` writes a UNPACK header and at most 64 matrices there, with qwords `1 + 4*packed`, and fails rather than truncating when object plus first-person matrix count exceeds 64 ([`hcu_render_snapshot.c:213-265`](../../src/stream/hcu_render_snapshot.c#L213)). It is not a complete DMA chain and no production caller submits `hcu_render_snapshot_dma_words()`; the HCU adapter only calls the packer after snapshot commit ([`ps2_render.c:185-210`](../../submodules/halo-ce-universal/port/ps2/src/ps2_render.c#L185)).

That 4,128-byte staging slab is not a required independent product buffer if the eventual parent renderer consumes the immutable snapshot directly and emits its needed VIF data into an owned chain. The host conversion/encoding tests can still test the encoding helper with test-local storage. The current staging output must not be made an uncharged prefix of the four renderer chains. Nor should the 64-matrix hard limit be adopted as the runtime object capacity: the public snapshot supports up to 2,048 objects plus 64 first-person nodes, so a real renderer must define its full matrix/palette demand and reject incomplete snapshots as current commit code intends.

### Alignment and allocator APIs

The v2 `arena_alloc()` already accepts any power-of-two alignment and computes alignment from the actual address, rather than assuming an aligned offset ([`mem.c:12-32`](../../submodules/halo-ps2/engine/src/core/mem.c#L12)). But guarded layout creation currently requests only 16-byte alignment for each region ([`mem.c:103-135`](../../submodules/halo-ps2/engine/src/core/mem.c#L103)). The renderer's `alloc_uncached()` requests `memalign(64, bytes)`, zeroes and cache-syncs it, and passes the KSEG1 uncached accelerated alias to the DMA path ([`bsp_render.c:104-111`](../../submodules/halo-ps2/engine/src/render/bsp_render.c#L104)). Thus switching from `memalign()` to `arena_alloc()` must explicitly preserve the intended 64-byte alignment and uncached-alias/cache behavior.

Saved guest memory reports corroborate why an explicit alignment assertion matters: the linked [`result.json`](../../build/hcu-ps2-closure/emulator-m1-recompiler-33230a6978924fcca86118febd8b2329/result.json) and its [`emulog.txt`](../../build/hcu-ps2-closure/emulator-m1-recompiler-33230a6978924fcca86118febd8b2329/emulog.txt) show `dma_commands base=0x15fdbf0`, 16-byte aligned but 48 modulo 64. The suballocator cannot assume the parent region's start meets the renderer's existing 64-byte request. Because all four chain byte sizes are multiples of 64, a 64-aligned base permits the four slots to exactly tile the arena without inter-slot padding. The layout has a bounded alignment-slack field (`MEM_LAYOUT_V2_GUARDED_SLACK`, 310 bytes) already added to the single boot allocation ([`mem.h:37-41`](../../submodules/halo-ps2/engine/src/core/mem.h#L37), [`hcu_main.c:236-270`](../../src/stream/hcu_main.c#L236)). Given the actual region extents, one needs to prove the adjusted carve's worst-case padding against this slack in a unit test and on target; do not silently grow the v2 region or eat reserve.

There are two different PS2SDK packet allocation paths. `packet2_create()` calls `calloc(sizeof(packet2_t))` for metadata and `memalign(64, qwords*16)` for payload ([`packet2.c:25-57`](../../submodules/ps2sdk/ee/packet2/src/packet2.c#L25)); `packet2_create_from()` still calloc-allocates metadata while borrowing payload, and `packet2_free()` unconditionally frees both base and descriptor ([`packet2.c:60-86`](../../submodules/ps2sdk/ee/packet2/src/packet2.c#L60)). HCU links wrappers for `malloc/free/calloc/realloc` ([`hcu_parent_link_probe.py:244-254,276-285`](../../tools/hcu_parent_link_probe.py#L244)), so the metadata may be routed to the bounded compatibility arena, but `memalign` is not among those wrapped symbols. The existing renderer uses `memalign()` for all four large chains and `packet2_create()` for its VU program upload packets and the persistent 64-qword environment packet ([`bsp_render.c:85-99,152-171`](../../submodules/halo-ps2/engine/src/render/bsp_render.c#L85)). Current memory evidence therefore does not show a single bounded owner for these payloads. A borrowed packet must not be passed to `packet2_free()` unless its base really is independently freeable; a packet2 control descriptor is not the same thing as its command storage.

## Hardware stores — do not mix ledgers

| Store | What belongs there for this path | Evidence / rule |
|---|---|---|
| EE main RAM (32 MiB) | HCU snapshot banks, CPU-built VIF/GIF DMA chains, upload-source staging, BSP/material/visibility scratch and CE-owned data | `dma_commands`, `frame_scratch`, `current_bsp`, `texture_cache`, and the fixed reserve are EE-budget regions; every pointer CPU or DMA reads must be charged once. |
| GS eDRAM (4 MiB) | Two color framebuffers, Z buffer, texture/lightmap residency | `video_init()` calls `graph_vram_allocate()` for color/Z and texture base; it configures display and scanout ([`video.c:9-45`](../../submodules/halo-ps2/engine/src/platform/video.c#L9)). GS allocations are not EE `dma_commands` bytes. The actual rasterizer/framebuffer output is not a place to put EE chain data. |
| VU1 local memory | VU microprogram and its small local double-buffer data | VU1 program is uploaded separately in `send_vif_program()`; it is not an EE arena or general-purpose chain-storage extension ([`bsp_render.c:85-101`](../../submodules/halo-ps2/engine/src/render/bsp_render.c#L85)). |
| IOP RAM | IOP modules, storage/device services and RPC communication | Not the destination for EE DMA sources or map-resident CE pointers. |
| SPU2 RAM | Later audio playback/sample residency | Separate from M3 renderer capacity; do not charge EE staging and SPU2 storage twice. |

`bsp_render_set_world()` allocates per-map visibility, material bindings, sort indexes, clipping buffers and batch bounding boxes from an `arena_t` ([`bsp_render.c:174-234`](../../submodules/halo-ps2/engine/src/render/bsp_render.c#L174)). Those are not the persistent DMA chains and do not belong in `dma_commands`; source texture/lightmap images nevertheless must stay in EE-accessible memory until any upload DMA that references them completes. `bsp_render_kick()` sends the environment packet, waits, sends upload data and waits, then submits the geometry VIF1 chain asynchronously ([`bsp_render.c:747-769`](../../submodules/halo-ps2/engine/src/render/bsp_render.c#L747)). Those lifetimes make a single allocation total insufficient: each range needs owner, alignment, cache mode, submit/fence, and reuse point.

## Halo-64 comparison: useful separation, wrong capacity model

Halo-64's N64 port notes explicitly list the state CE still requires when its original renderer is excluded: advancing `render.frame_index`, per-window camera/frustum/local-player state, first-person node matrix updates, `interface_draw_screen()` timer/sound state, rasterizer bounds, and vblank/frame counters ([`port/n64/NOTES.md:33-57`](../../submodules/halo-64/port/n64/NOTES.md#L33)). Its render adapter increments frame state, copies a per-window camera, calls `first_person_weapon_render_update()`, and updates HUD state in the view loop ([`n64_render_game.c:517-547,669-708`](../../submodules/halo-64/port/n64/game/n64_render_game.c#L517)). HCU's current PS2 adapter similarly advances CE presentation state and copies first-person/object transforms before the parent can render ([`ps2_render.c:134-210`](../../submodules/halo-ce-universal/port/ps2/src/ps2_render.c#L134)).

The reusable principle is the boundary: CE must still receive stateful per-frame presentation services, while the machine-specific renderer owns actual graphics submission. The N64's 8 MiB/94 MHz constraints and any N64 renderer buffers/cadence compromises are **not** evidence to reduce PS2 object/actor/effect/view capacity. Keep the PS2 32 MiB accounting, measured R5900/GS performance, all product features and untouched reserve; use Halo-64 as a call-order/ownership comparison only.

## Recommended single implementation/test slice

**Name:** `renderer_dma_owner_v1`: exact arena ownership and high-water gate for the existing BSP renderer, without changing the four chain capacities.

1. **Make partition math executable.** Add a small allocator interface taking the v2 DMA arena. Carve the region on a 64-byte boundary and create four disjoint fixed-capacity slots: geometry 0/1, upload 0/1, with start/end, bytes, alignment, cache alias and owner reported. Preserve the four existing capacities. Modify guarded v2 layout only as needed to make the DMA region base 64-byte aligned; prove maximum alignment padding remains inside the pre-budgeted guarded-allocation slack and the 5.5 MiB reserve remains unchanged. Add host tests for deliberately 16-but-not-64-aligned backing, all four intervals, canaries, allocator exhaustion, overflow-safe arithmetic, and no overlap with snapshot/frame-scratch.
2. **Remove duplicate command storage, not matrix information.** Do not bind the 4,128-byte snapshot VIF slab into the production `dma_commands` arena. Keep HCU snapshots as the complete immutable presentation input. Until a real consumer exists, retain matrix packing as a host/local test helper rather than reserving runtime EE storage. When connected, convert snapshot data as part of renderer chain construction; never silently impose the current 64-combined-matrix pack cap on all CE render objects or first-person nodes. Add a test that a failed/over-cap snapshot is rejected whole and that no `publish_dma()` write aliases a live chain slot.
3. **Make packet2 payload ownership explicit.** In the same allocator slice, enumerate every packet2 use at renderer startup and frame submission. Use a documented borrowed-buffer/control-descriptor API or an explicit bounded owner for command payloads; do not assume `--wrap,calloc` accounts for `memalign` payloads. Keep the VU upload packet synchronous and recyclable after its VIF fence. Reserve the persistent environment packet only from measured unused capacity or a separately named, physically proven EE owner. Its descriptor and backing payload must have distinct lifetimes; do not call `packet2_free()` on a borrowed chain base.
4. **Measure before changing capacity.** Preserve current `32768/4096` qword caps at first. Add per-slot attempted/high-water qwords and overflow counters plus chain generation/fence state; report after each frame and fail the frame rather than submit a partial chain. Test synthetic boundary sizes immediately below, exactly at, and above the cap. Exercise the standalone viewer first to validate allocator mechanics, then the first M2-qualified real gameplay BSP under HCU in PCSX2 interpreter and recompiler. The data-only UI map and blue-clear diagnostic do not exercise BSP chain occupancy.
5. **Use measured results for the next decision.** If the measured worst-case camera path plus snapshot-derived required VIF records and environment packet fit within the existing slots with safety margin, retain the current fixed capacities and demonstrate no overflow/canary damage across map load, frame variation, texture misses and unload/reload. If not, identify the exact required bytes and select a non-scope-reducing mechanism (e.g. stream multiple ordered chain batches with existing synchronization, or rework upload/environment sequencing), then repeat high-water and visual/parity checks. Do not shrink visible-object capacity, omit geometry/features, decrease player views, change simulation cadence, or touch `uncommitted_reserve` to make the arithmetic green.

### Required test evidence for this slice

- Allocator unit test: the intentionally misaligned 16-byte base is aligned to 64; the four current slots occupy exactly 1,179,648 bytes; all extents lie within `dma_commands`; guards remain intact; one-byte/qword-over allocation fails without state mutation.
- Packet ownership test: instrument the target allocation seam so no renderer DMA payload escapes into unreported `memalign`/libc storage; borrowed packet descriptors do not free arena-owned payload; every reuse follows a completed channel/GS fence.
- Renderer host tests: existing chain overflow tests plus four-slot and sequence/fence tests; full relevant tests under ASan/UBSan where supported.
- Guest test on a current, exact-hash gameplay image: same map/camera trace in interpreter and recompiler; markers for renderer-ready, nonzero BSP batch/triangle count, per-slot high-water, no overflow, VIF1 complete, GS FINISH, and frame-present; screenshot must show BSP pixels. Record exact ELF/source/package pins. A blue clear alone is not this test.
- Memory gate: 32 MiB physical interval ledger still disjoint; all regions/canaries pass; 5,767,168-byte reserve is byte-for-byte unchanged; GS extents remain in eDRAM and do not appear as EE arena allocations.

This slice resolves the allocator ownership and creates the first trustworthy usage data. It does not, by itself, close M3 Step 13: the HCU consumer, admitted gameplay BSP, correct camera conversion, real VIF/GIF submission, and visible scene proof remain required.

## Verification performed for this report

- `python3 -m pytest -q tests/test_hcu_render_snapshot.py tests/test_hcu_m3_render_clear.py tests/test_hcu_v2_guard.py` passed: **6 passed**.
- A combined invocation that also included `tests/test_hcu_allocation_ownership.py` reported 8 passed and 1 failed (560 subtests). The failure is outside this audit's renderer path: `test_current_machine_map_has_exact_bss_owners` invokes the current M0 gate, which exits nonzero because source-backed review entries remain unresolved. It is not counted as a DMA allocator pass/failure.
- No code was changed and no PCSX2 render was run for this report. The existing saved guest record cited above is only used for its address/alignment observation.
