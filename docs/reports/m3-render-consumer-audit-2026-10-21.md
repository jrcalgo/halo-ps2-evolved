# M3 Step 13: CE snapshot-to-PS2 renderer consumer audit

**Disposition:** the current direct-ELF UI-map run reaches CE rendering and commits a non-empty immutable snapshot, then stops at CPU-side matrix packet construction. The HCU machine profile has no production consumer that turns that snapshot into a world view, no call to the parent renderer's GS/VU initialization or frame APIs, and no renderer frame/present loop. That missing integration is the source-backed explanation for the black window. The screenshot proves the visible result for the exact run; the source graph explains why it happens. This is not a PCSX2 boot-media problem and not evidence that the PS2 renderer itself is broken.

Report-only audit. No production code, milestone plan, or shared ledger was changed. Focused tests were run read-only with respect to tracked sources.

## Evidence identity and provenance limits

The latest exact direct-ELF image with a captured black PCSX2 viewport is the host-profile combined image:

| Evidence | Identity |
|---|---|
| Machine ELF | SHA-256 `c1e83f7515a7a6a97b68bad75a9811aaf7fddd0564cb3bdd8722d16bab8d6386` |
| Parent / HCU / halo-ps2 pins in guest record | `70e2ed0cf2145a45d23aa07414a3a88c05155d4c` / `6933490b2d16bb1c637295b6a0f3880ba23a7d56` / `71183bb0a9adc586cd267b2780c82bbc12cfd95b` |
| Data ISO | SHA-256 `79f2855a5953483637ca060e778589a9f8c54e5fc4cda4a69347f22484457d79`; mounted by the test, not booted |
| UI inputs | `ui.map` SHA-256 `8556b647b82742d07282fe4e6db0cf847b542c046484e91e71ec31fea5f5fd7e`; `ui.hp2` SHA-256 `a83ded5049128dc0287b975af9c17f4224e467ad5e10ffa079468934e6241e90` |
| Interpreter run | `emulator-m1-interpreter-b39c9fbad98a44319623b72b29c1a0bf`; result SHA-256 `4aa33475018622916aaa7ebe96e9b4982b8d86f36e69c1a4059d840a14283b10`; log SHA-256 `75fccc1088b5bfc57ae6cf45decedb63e6bd0aaa604deaa26598e7f2a661c61b`; 5.0155 s stable after `m2-ui-map-loaded` |
| Recompiler run | `emulator-m1-recompiler-77cad19e92c444019698c31d3955f4da`; result SHA-256 `66e3920238b878ba48b74a9e481bf4a7b1bcb34bf86e75285057c06b439f8ed4`; log SHA-256 `ca9258b2f906eaeeff43f63635a0e95a4d1b44226b5ca893df7884df96bfc78f`; 10.0320 s stable after `m2-ui-map-loaded` |
| PCSX2 window capture | [`pcsx2-viewport.png`](../../build/hcu-ps2-closure/emulator-m1-recompiler-77cad19e92c444019698c31d3955f4da/pcsx2-viewport.png), SHA-256 `e9b2fbea1b63c6e1df84d01a759eb66cebf172dff1650719e99b4c3bccd0405b`; viewport black, PCSX2 status “No Image”, GPU 0% |
| Settings hashes | Interpreter `97c6c005dc6a1c08020fb2a1dcdbee36fb5d12251004b1127c73815837a04821`; recompiler `a251dc1eb21da37968be97e84d310050cc7f52f1f097e1607835d179746162dc` |

These pins are commit identities, not complete source-byte provenance: the parent and submodule working trees contain unrelated dirty changes. The currently inspected source bytes are independently fingerprinted below. The exact ELF's retained result binds commits and ELF hash; it does not embed a per-source-object manifest. Do not claim that the present source hashes cryptographically identify every input used for that ELF.

Current inspected pins and source fingerprints:

- Parent checkout pin: `70e2ed0cf2145a45d23aa07414a3a88c05155d4c`.
- HCU submodule pin: `6933490b2d16bb1c637295b6a0f3880ba23a7d56`; PS2 render adapter source SHA-256 `c5f244aa67c01cdc7eca93a20dc83ddabbf530859ee5cda0794e70cbe8c26943`.
- halo-ps2 submodule pin: `71183bb0a9adc586cd267b2780c82bbc12cfd95b`; machine loop `engine/src/main.c` SHA-256 `856122bbedc70418ec1350b3a4011c33efc71e1c1d727ca314aa6f3e5cbb6b08`, BSP renderer `engine/src/render/bsp_render.c` SHA-256 `def69c8d881067f9270182fbe7c2ffb066ca4fbbbed8beafabc0b96dd91f5780`, video `engine/src/platform/video.c` SHA-256 `cd1400ed3001486afebd1433d1c2302d66607ea059275d64c9ef31795d2b0525`.
- Parent HCU entry SHA-256 `55be5d93372e6833d8a7c063facdf18b1b3054dca1a6ae5495aa4bf07cff724a`; snapshot implementation SHA-256 `ec56be9a8b7ca2806bbc665e7dc2e72e36c5ca790fd5de0e4f83a8b9fa6bf03b`.

## Confirmed call graph: HCU render state reaches packet formation, not presentation

The production `WORLD_HCU_GAMEPLAY=1` target selects `src/stream/hcu_main.o` and snapshot/map glue, while the `else` branch that adds the viewer's `main.o` is not selected ([`tools/ee-world.mk:45-65`](../../tools/ee-world.mk#L45)). It still links the shared video and BSP renderer objects in the common object list ([`tools/ee-world.mk:5-44`](../../tools/ee-world.mk#L5)). Those objects being linked does not call them.

The actual runtime sequence is:

1. Parent machine `main()` initializes the PS2 memory/services and invokes `halo_shell_main()`; HCU's `port.json` renames `source/shell/shell_xbox.c`'s `main` to that symbol ([`port.json:108-115`](../../submodules/halo-ce-universal/port/ps2/port.json#L108), [`hcu_main.c:225-296`](../../src/stream/hcu_main.c#L225)).
2. CE's local-game loop conditionally calls `main_game_render()` after game update; `main_game_render()` constructs CE player windows/cameras, then calls `render_frame()` ([`source/main/main.c:3688-3739`](../../submodules/halo-ce-universal/source/main/main.c#L3688), [`source/main/main.c:3311-3405`](../../submodules/halo-ce-universal/source/main/main.c#L3311)). This is the gameplay frame path, distinct from shell's pregame/UI path.
3. The PS2 HCU render adapter advances CE render frame state and first-person pose, copies camera/object/node transforms into the bound snapshot, commits it, and invokes the packet packer ([`ps2_render.c:120-210`](../../submodules/halo-ce-universal/port/ps2/src/ps2_render.c#L120)). The parent entry binds two snapshot banks and a bounded VIF-word area before entering CE ([`hcu_main.c:245-266`](../../src/stream/hcu_main.c#L245)); snapshot begin/commit validates storage, dimensions/camera scalars, matrix finiteness, and generation publication ([`hcu_render_snapshot.c:38-65`](../../src/stream/hcu_render_snapshot.c#L38), [`hcu_render_snapshot.c:83-160`](../../src/stream/hcu_render_snapshot.c#L83)).
4. `hcu_render_snapshot_publish_dma()` converts at most 64 first-person/object matrices to `mat4`, writes a VIF `UNPACK V4-32` command and data words, and reports qword count ([`hcu_render_snapshot.c:213-275`](../../src/stream/hcu_render_snapshot.c#L213)). This is CPU buffer construction only. Source search finds no production call to `hcu_render_snapshot_latest()`, `hcu_render_snapshot_dma_words()`, or `hcu_render_snapshot_dma_qwords()` outside the helper itself/tests; the only production caller of `publish_dma()` is the HCU render adapter. No consumer takes those words and creates a parent `chain_t` or submits a VIF1 transfer.
5. There is no call from the HCU entry to `dma_channel_initialize(DMA_CHANNEL_GIF, ...)`, `video_init()`, or `bsp_render_init()`. There is likewise no production `bsp_render_build()`, `bsp_render_kick()`, `video_wait_gpu()`, `video_present()`, or `graph_set_framebuffer_filtered()` call in the HCU entry/adapter. The only complete loop found is the standalone viewer in `engine/src/main.c`: it initializes GIF/video/VU1, loads a PS2 BSP, repeatedly builds, waits, presents, and kicks frames ([`main.c:142-147`](../../submodules/halo-ps2/engine/src/main.c#L142), [`main.c:256-273`](../../submodules/halo-ps2/engine/src/main.c#L256), [`main.c:307-311`](../../submodules/halo-ps2/engine/src/main.c#L307)).

The renderer's existing GS/VU contract has real side effects: `video_init()` allocates two framebuffers and a Z buffer from 4 MiB GS VRAM, configures NTSC/interlaced display, sets the framebuffer and enables output ([`video.c:9-40`](../../submodules/halo-ps2/engine/src/platform/video.c#L9)); `bsp_render_init()` initializes VIF1, uploads VU1 programs, allocates chains, sets texture-window state and uploads a font ([`bsp_render.c:152-171`](../../submodules/halo-ps2/engine/src/render/bsp_render.c#L152)); `bsp_render_kick()` constructs/sends GIF setup and an uncached VIF1 chain ([`bsp_render.c:747-769`](../../submodules/halo-ps2/engine/src/render/bsp_render.c#L747)); `video_present()` waits for vsync and selects the rendered framebuffer ([`video.c:94-109`](../../submodules/halo-ps2/engine/src/platform/video.c#L94)). None is equivalent to building a VIF unpack array on the EE.

### What the current guest marker proves

For the `72fe0034df7a70a13e26d95ef470006054e6e5ff5425170c89a80e98b2319ff2` UI-only image, both retained guest logs show `m2-ui-map-loaded` followed by `snapshot-dma qwords=5` ([interpreter log](../../build/hcu-ps2-closure/emulator-m1-interpreter-c6c9ff0fc197473388843699c29dd965/emulog.txt), [recompiler log](../../build/hcu-ps2-closure/emulator-m1-recompiler-26857112060e4cd6b2ef735c53274a0d/emulog.txt)). The packer's formula `1 + packed * 4` means five qwords represents one matrix packed into a CPU-side VIF payload. It proves that `render_frame()` ran, one snapshot passed commit, and one matrix was accepted by the packer. The log does not reveal whether that matrix was an object or first-person node, and says nothing about actual VIF1 DMA.

For the later exact black-capture ELF `c1e83f…`, the PCSX2 result records `m2-ui` and the screenshot is retained, but its screenshot is not embedded in `result.json` (`screenshot_sha256` is null because the window was captured separately). The independent recompiler screenshot is a literal black guest viewport with PCSX2 “No Image” and GPU 0%. This supports “the guest produced no displayed frame in this run”; it does not, by itself, distinguish GS never initialized from a cleared/unpresented framebuffer. Source inspection resolves the structural question: the HCU path lacks both initialization and submission/present wiring.

## Why UI load and snapshot success coexist with black pixels

`m2-ui-map-loaded` is emitted after the UI scenario/tag load, not after a renderer draw. The tested `ui.map`/`ui.hp2` package is explicitly UI/bootstrap data and contains no accepted gameplay BSP render set. Therefore it is not a valid scene fixture even if it loads cleanly. The packet helper only packs transforms; it contains no BSP vertices, material bindings, textures/lightmaps, object geometry batches, or framebuffer lifecycle.

The dominant structural cause is missing display initialization plus missing frame submission/presentation. The profile swaps the viewer `main()` out for HCU's shell entry, but does not provide the counterpart GS/VU loop. This is why the application can reach its HCU log markers while the PCSX2 viewport remains black. It is not fixed by changing the ISO boot method, adding a matrix to the snapshot, or toggling PCSX2 renderer settings.

### Similar-looking but false paths

- `hcu_render_snapshot_publish_dma()` is named “DMA” but never launches DMA: it only writes VIF words to `dma_commands` and returns a qword count.
- `snapshot-dma qwords=5` does not mean “five DMA qwords submitted.” It means one matrix is present in a CPU staging payload according to the helper's encoding.
- The common HCU build object list containing `video.o`, `bsp_render.o`, and `vu1/world.o` is not a call graph; the HCU entry never invokes these functions.
- A successful scenario marker is not a successful BSP setup; no game BSP is loaded/converted/bound to `bsp_render_set_world()`.
- A PCSX2 black capture is not a guest crash: the exact recompiler result reached its requested marker and stayed stable for 10 seconds. Earlier reports of post-marker script faults are separate runs and not the stable black-capture root cause.
- Booting the data ISO itself leads to BIOS insert-disc fallback because it is not bootable. The black capture here is from direct `-elf` execution with the same ISO mounted as data, so media selection does not explain the captured black display.

## Smallest safe next implementation slice for Step 13

Do not wire the current matrix-only VIF packet directly into the renderer as if it were a world. Step 13 needs an explicit **parent render consumer and presentation loop**. Keep CE object identity and simulation authoritative in HCU; the parent reads only immutable presentation snapshots and runs the GS/VU1 pipeline.

1. **Create the parent machine-render owner without reviving the standalone viewer entry.** Add a bounded `hcu_ps2_renderer`/render-bridge lifecycle called by the production HCU entry: initialize GIF and VIF1 once, call `video_init()` and `bsp_render_init()`, provide shutdown/unwind on partial initialization, and keep parent machine setup separate from CE shell entry. Do not add `main.o` to the HCU target; it owns a second simulation/viewer loop. Use its call ordering and fences as reference only.
2. **First prove display bring-up independently of CE scene assets.** A temporary diagnostic-only path should submit a known GS clear or existing renderer selftest color, wait for GS FINISH, call `video_present()`, and expose monotonically increasing `renderer-init`, `clear-submit`, `gs-finish`, `frame-present` counters. Capture it in PCSX2. This validates display mode/framebuffer ownership before coupling scene mapping. Do not count a colored clear as a Halo scene/render pass.
3. **Make frame consumption explicit and safe.** On each accepted CE presentation callback, acquire a stable snapshot/generation once, reject missing/stale/non-finite camera or bounds, and build one parent-owned view. Keep it immutable until VIF/GIF readers finish; two-bank reuse must be fenced against in-flight DMA, not merely against CPU publication. Use the snapshot's camera/frame data as input, not a pointer into CE globals. If rendering can run at a different cadence than simulation, prove it cannot mutate CE state or advance RNG.
4. **Connect one real, capacity-qualified BSP and source adapters.** Before scene drawing, M2 must admit a non-UI map and prove its CE tag/BSP state, validated BSP, PS2 vertex/cluster packs, material bindings, textures, and lightmap data have bounded non-overlapping owners. The CE `scenario`/CBSP memory representation is not automatically the PS2 `bsp_section`; implement and test the explicit mapping/material/texture callbacks before calling `bsp_render_set_world()`. Use camera conversion into parent `camera_t` with correct position/basis/FOV/aspect/near-far; test viewport mapping. Start with static BSP only; do not infer object rendering from snapshot matrices.
5. **Feed geometry through the established renderer.** For each frame, call `bsp_render_build(frame, camera, overlay)`; account/limit chain and upload memory; call `bsp_render_kick()` to launch GIF/VIF1; observe VIF1 completion and GS FINISH using the existing parent synchronization; then `video_present()` at a measured cadence. Use the PS2 render path's visibility/clip/LOD/material and VU1 programs, rather than synthesizing a second draw engine in `src/game/`.
6. **Separate scene proof from later visual features.** First acceptance is a real BSP frame with a nonzero visible batch/triangle count and non-black pixels, not a UI/menu, clear-only, or test pattern. Object models, player model/first-person weapon, HUD, particles, and effects follow only after the BSP bridge is stable; presentation still must preserve CE frame timers/camera/first-person state.

## PS2 capacity and performance implications

- EE RAM is 32 MiB; the current v2 plan commits 27,787,264 bytes and leaves its 5,767,168-byte reserve untouched. `dma_commands` is budgeted at 1,179,648 bytes, `current_bsp` at 6,291,456 bytes, `texture_cache` at 4,194,304 bytes, `dynamic_simulation` at 2,621,440 bytes, and `frame_scratch` at 393,216 bytes ([`memory-budget.json:4-20`](../../config/memory-budget.json#L4)). The snapshot banks consume 268,992 bytes in frame scratch and the CPU VIF buffer 4,128 bytes in DMA commands for the current schema. A full renderer's chain, upload packets, textures/staging, camera data, and BSP runtime arrays must be charged once to these named owners; do not layer in uncharged `alloc_uncached()` buffers or silently keep the viewer's former megabyte heap.
- The 4 MiB GS eDRAM is a separate store, not part of the 32 MiB EE ledger. Existing `video_init()` spends it on two 640×448 CT16S framebuffers, Z24, and a texture window; `bsp_render_init()` consumes GS pages for CLUT/font/cache. Calculate the real scene's texture/lightmap residency against that remaining GS window, with a bounded upload/cache policy. VU1 micro memory/data and IOP/SPU2 are separate again.
- `bsp_render_set_world()` allocates visibility, clipping, material, sort, and bounding-box arrays from an `arena_t` based on BSP/material/batch counts ([`bsp_render.c:174-234`](../../submodules/halo-ps2/engine/src/render/bsp_render.c#L174)). Include those plus the decoded BSP in `current_bsp`; include transient decoder/asset streaming peaks without overlapping those persistent allocations.
- The EE runs a 30 Hz game cadence in the current viewer by default and the GS/VU1 chain is asynchronous. Measure EE build time, VIF chain length/time, GS FINISH, cache misses/evictions, and frame deadline on PCSX2 and real hardware when available. Do not copy Halo-64's 8 MiB/94 MHz cuts or lower update cadence; do not mistake its render bridge for a PS2 backend.

## Tests and emulator evidence needed to close the renderer-consumer portion

1. **Host contract tests:** renderer lifecycle init/failure unwind; invalid and stale snapshots; view/camera basis and viewport conversion; map unload invalidates publication; two-bank immutability while one prior frame is in flight; bounded chain/scratch exhaustion; object/node maximum handling; presentation-rate variation leaves CE state/RNG hashes identical.
2. **Renderer adapter tests:** feed a small known real PS2 BSP pack through `bsp_render_set_world()` with deterministic untextured/material callbacks; assert selected BSP identity, camera, visible batches/triangles, built chain qwords, texture-cache bounds, and no out-of-range material/cluster indices. Add an integration test that proves one generation's snapshot was consumed exactly once and the returned chain references only parent-owned buffers.
3. **Target build/source gate:** HCU production image includes the bridge lifecycle and real consumer symbols; map/source manifest records the selected BSP/texture pack hashes; zero undefined imports; linker map and arena high-water prove `current_bsp`, `dma_commands`, `frame_scratch`, resident data, and all renderer allocations remain in their assignments, with reserve preserved.
4. **PCSX2 interpreter + recompiler:** exact same artifact reaches markers for `renderer-ready`, `snapshot-consumed generation=N`, selected BSP, `visible-batches>0`, `vif1-submitted`, `vif1-complete`, `gs-finish`, and `frame-present`; retain result/log/settings hashes and a viewport screenshot. Validate image pixels in the actual guest output region and require non-black scene pixels across multiple frames. Logs alone are not visual acceptance.
5. **Target performance check:** record EE/VIF1/GS frame-time distributions and high-water under repeatable camera paths, verify no chain overflow/cache thrash/missed 30 Hz budget, canary corruption, or arena growth; repeat on physical PS2 when available. Emulator pass does not substitute for physical EE/GS throughput qualification.

### Focused check performed in this audit

```text
PYTHONPATH=. python3 -m pytest -q tests/test_hcu_render_snapshot.py tests/test_hcu_render_frame_invariance.py
4 passed in 0.27s
```

These host fixtures validate snapshot packing and render-source immutability. They do not execute the PS2 VIF1/GS path and therefore do not alter the black-frame finding.

## Source citation index

- HCU boot/bind and CE shell handoff: [`src/stream/hcu_main.c:225-306`](../../src/stream/hcu_main.c#L225).
- Target selection: [`tools/ee-world.mk:45-65`](../../tools/ee-world.mk#L45).
- CE game-loop render gate and window/camera population: [`source/main/main.c:3688-3739`](../../submodules/halo-ce-universal/source/main/main.c#L3688), [`source/main/main.c:3311-3405`](../../submodules/halo-ce-universal/source/main/main.c#L3311).
- Snapshot producer: [`port/ps2/src/ps2_render.c:120-210`](../../submodules/halo-ce-universal/port/ps2/src/ps2_render.c#L120).
- Snapshot storage and CPU packet: [`src/stream/hcu_render_snapshot.c:38-160`](../../src/stream/hcu_render_snapshot.c#L38), [`src/stream/hcu_render_snapshot.c:213-275`](../../src/stream/hcu_render_snapshot.c#L213).
- Existing parent renderer lifecycle: [`engine/src/main.c:142-147`](../../submodules/halo-ps2/engine/src/main.c#L142), [`engine/src/main.c:256-273`](../../submodules/halo-ps2/engine/src/main.c#L256), [`engine/src/main.c:307-311`](../../submodules/halo-ps2/engine/src/main.c#L307).
- Renderer init/world/frame/kick APIs: [`bsp_render.h:71-99`](../../submodules/halo-ps2/engine/src/render/bsp_render.h#L71), [`bsp_render.c:152-234`](../../submodules/halo-ps2/engine/src/render/bsp_render.c#L152), [`bsp_render.c:747-769`](../../submodules/halo-ps2/engine/src/render/bsp_render.c#L747).
- GS initialization/presentation: [`video.c:9-40`](../../submodules/halo-ps2/engine/src/platform/video.c#L9), [`video.c:94-109`](../../submodules/halo-ps2/engine/src/platform/video.c#L94).
- Separate EE memory ledger: [`config/memory-budget.json:4-20`](../../config/memory-budget.json#L4).
- Related earlier viewport audit and exact evidence reconciliation: [`m2-black-viewport-render-audit.md`](m2-black-viewport-render-audit.md); this report updates its older statements about snapshot binding/commit by using the later exact guest evidence above.
