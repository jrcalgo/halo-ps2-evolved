# M2 black-viewport render audit

**Disposition:** the black output is explained by a missing end-to-end presentation path in the `WORLD_HCU_GAMEPLAY=1` image, not by PCSX2 boot-media selection. The HCU port advances CPU-side render state and has code to form a pointer-free snapshot, but the combined entry neither binds that snapshot storage nor initializes/submits the parent GS/VU renderer. The parent’s renderer sources are present in the build's common object list, but in the HCU profile the normal viewer `main.o`—which initializes video/VU1 and drives `bsp_render_build()` / `bsp_render_kick()`—is omitted. Even after wiring that path, the observed UI package is explicitly not a gameplay BSP map and cannot serve as the scene-render acceptance case.

This is a report-only source/runtime diagnosis. No runtime or plan code was changed, and no new PCSX2 run was launched. I inspected the retained guest captures and logs directly. The old stable screenshot is demonstrably black; that visual observation is tied to its exact old ELF, not silently transferred to the latest build. Current-source inspection independently confirms the same structural render integration gaps.

## Evidence set and what the markers mean

### Stable black viewport capture

The strongest screenshot evidence is the recompiler run recorded in [`plans/7.hcu-remake-m2-m4.md`](../../plans/7.hcu-remake-m2-m4.md#L205):

| Artifact | Identity |
|---|---|
| ELF | SHA-256 `4a9bcce6fcc15b5f41298073ad0d8c37304528ec1148aac33bf2caf7757ba41e` |
| Screenshot | [`pcsx2-viewport.png`](../../build/hcu-ps2-closure/emulator-m1-recompiler-2ece2e90b9854867bdaa6743fd117dfb/pcsx2-viewport.png), SHA-256 `82e7b3dab039d12eb5ce065ee0cb5473e3907a1716f7cdf4a7c7f873fd248e42` |
| Guest log / result | [`emulog.txt`](../../build/hcu-ps2-closure/emulator-m1-recompiler-2ece2e90b9854867bdaa6743fd117dfb/emulog.txt), SHA-256 `d5600b64e270675fa81438d4aca80f8d8619333ba32681199ef9550873f005df`; [`result.json`](../../build/hcu-ps2-closure/emulator-m1-recompiler-2ece2e90b9854867bdaa6743fd117dfb/result.json), SHA-256 `e14f5dad37269fb520bff6cdead785b53fb6d41057bec79fb12af706999410a9` |
| Inputs / pins | `ui.map` `8556b647b82742d07282fe4e6db0cf847b542c046484e91e71ec31fea5f5fd7e`; `ui.hp2` `a83ded5049128dc0287b975af9c17f4224e467ad5e10ffa079468934e6241e90`; data ISO `79f2855a5953483637ca060e778589a9f8c54e5fc4cda4a69347f22484457d79`; parent `70e2ed0cf2145a45d23aa07414a3a88c05155d4c`; HCU `6933490b2d16bb1c637295b6a0f3880ba23a7d56`; halo-ps2 `71183bb0a9adc586cd267b2780c82bbc12cfd95b` |

I opened this exact `pcsx2-viewport.png`: the guest output rectangle is entirely black. Its result reaches the requested `m2-ui-map-loaded` marker and was stable for about 25 seconds. The interpreter image with the same ELF and pins reached the same marker and was stable for about 30 seconds. This proves that the black frame was not merely the BIOS “insert disc” prompt and was not caused by a guest exception in the stable recompiler run. It still does not prove any GS draw call was attempted.

### Current post-marker run and later stable run

The retained current-source-era interpreter capture at [`screen.png`](../../build/hcu-ps2-closure/emulator-m1-interpreter-149b19b0c26e44bb8ca81e952ac5f2a4/screen.png), SHA-256 `9b48bb1ebe169f14898db5340baa4c8e35c6aa5aaa99d3c2911ac6801d28989d`, shows the PCSX2 output window black. Its exact guest record is [`result.json`](../../build/hcu-ps2-closure/emulator-m1-interpreter-149b19b0c26e44bb8ca81e952ac5f2a4/result.json), bound to ELF SHA-256 `62763185b8dc0da6aeaf1437a6445f3dff154cd232dc36de527b44a5714d5d33` and pins parent/HCU/halo-ps2 `70e2ed0cf2145a45d23aa07414a3a88c05155d4c` / `6933490b2d16bb1c637295b6a0f3880ba23a7d56` / `71183bb0a9adc586cd267b2780c82bbc12cfd95b`. It reached `m2-ui-map-loaded`, then the guest faulted:

1. UI HMAP (72 B), CTAG (1,547,396 B), CRNG (2,900 B), CBIX (44 B), and B000 (2,288 B) preflight/mount operations complete.
2. `HALO_PS2_LOCAL m2-ui-map-loaded` is logged at 31.2733 s.
3. At 31.5481 s PCSX2 logs unaligned accesses at `0x7d2cc6`/`0x7d2cca`; CE then asserts that script node `#58608` is unused/changed and halts `ring_loop` for corrupt syntax. The harness correctly marks this run failed after its requested stage marker.

Thus this exact capture is black but is **not** a fault-free persistent render test. The independent stable black screenshot above is better evidence that the viewport stayed black even when the guest survived the post-marker interval.

The latest pair at the time of the first audit was ELF `fbedd1aeab4319bd68b5515cc734206538fda4d896a70f30398e5668fd4fb768`, passing `m2-ui-map-loaded` in both modes with no viewport capture. It has since been superseded by the snapshot-bound current ELF and guest runs in the dated follow-up below. This historical run did not visually qualify its image.

## Source trace: why the machine path cannot currently draw a scene

### 1. The combined HCU entry never starts the parent renderer

`tools/ee-world.mk` puts `platform/video.o` and the PS2 `render/bsp_render.o`, VU1 world program, DMA-chain, texture-cache, and related objects in the common `EE_OBJS` set ([`ee-world.mk:5-44`](../../tools/ee-world.mk#L5)). But when `WORLD_HCU_GAMEPLAY=1`, it selects `hcu_main.o` and HCU service objects; only the `else` branch includes the ordinary viewer [`main.o`](../../tools/ee-world.mk#L45-L65).

That omission matters: the viewer startup calls `video_init()` and `bsp_render_init()` before map loading ([`engine/src/main.c:142-147`](../../submodules/halo-ps2/engine/src/main.c#L142)); its frame loop constructs the BSP draw chain with `bsp_render_build()`, waits and presents buffers, then submits the chain with `bsp_render_kick()` ([`engine/src/main.c:248-274`](../../submodules/halo-ps2/engine/src/main.c#L248), [`engine/src/main.c:286-311`](../../submodules/halo-ps2/engine/src/main.c#L286)). Those are live calls, not static link requirements.

The combined machine entry [`hcu_main.c`](../../src/stream/hcu_main.c#L1) allocates/binds EE arenas, initializes pads and storage, starts HCU's shell, and tears resources down ([`hcu_main.c:176-240`](../../src/stream/hcu_main.c#L176), [`hcu_main.c:249-265`](../../src/stream/hcu_main.c#L249)). It declares display dimensions for CE's CPU camera only and explicitly says it does not own GS setup/drawing ([`hcu_main.c:35-38`](../../src/stream/hcu_main.c#L35)). It contains no call to `video_init`, `bsp_render_init`, `bsp_render_set_world`, `bsp_render_build`, `bsp_render_kick`, or `video_present`. Linking renderer object files does not invoke their initialization or draw loop. This is a direct production-path integration gap.

### 2. HCU's render adapter writes a snapshot only if a buffer was bound

HCU's `render_frame()` adapter advances `render.frame_index`, selects a non-console camera, updates first-person pose, and conditionally copies camera/object matrices into a parent-owned snapshot ([`ps2_render.c:91-140`](../../submodules/halo-ce-universal/port/ps2/src/ps2_render.c#L91), [`ps2_render.c:142-210`](../../submodules/halo-ce-universal/port/ps2/src/ps2_render.c#L142)). This is CPU presentation-state work; it is not drawing.

The parent snapshot implementation returns `NULL` from `halo_ps2_render_snapshot_begin()` until `hcu_render_snapshot_bind()` has supplied its two banks ([`hcu_render_snapshot.c:38-66`](../../src/stream/hcu_render_snapshot.c#L38), [`hcu_render_snapshot.c:83-95`](../../src/stream/hcu_render_snapshot.c#L83)). At the time of the original audit there was no production binding call. The current M3 interface slice binds both banks from `frame_scratch` and packet memory from `dma_commands` before the HCU shell starts ([`hcu_main.c`](../../src/stream/hcu_main.c#L246)); it gives the decoder a disjoint 124,224-byte tail arena after reserving the 268,992-byte snapshot banks. The exact ELF `72fe0034df7a70a13e26d95ef470006054e6e5ff5425170c89a80e98b2319ff2` passed `m2-ui` in interpreter and recompiler. Both guest logs contain `m2-ui-map-loaded` followed by `snapshot-dma qwords=5`; in [`ps2_render.c`](../../submodules/halo-ce-universal/port/ps2/src/ps2_render.c#L142), the DMA packer is called only after a successful snapshot commit, so this is evidence of one committed nonempty snapshot and CPU-side packet packing. It still does not prove a GS renderer consumer or a scene can be presented.

The adapter's DMA routine only packs matrices into a VIF payload; it does not send a DMA chain to VIF1, draw the BSP, or flip the framebuffer ([`hcu_render_snapshot.c:213-265`](../../src/stream/hcu_render_snapshot.c#L213)). The current parent still has no production consumer connecting `hcu_render_snapshot_latest()` or `hcu_render_snapshot_dma_words()` to `bsp_render_set_world()` / object pass / GS submission. The state snapshot's presence in the ELF is not evidence of a renderer consumer.

The current plan records the remaining consumer seam as open: snapshot banks, commit, and CPU packet packing exist, but no consumer dispatches the packet or uses the snapshot to build/submit BSP and object passes ([`plans/7.hcu-remake-m2-m4.md:370`](../../plans/7.hcu-remake-m2-m4.md#L370)). The absent renderer initialization/consumer remains the direct structural explanation for an all-black Halo world viewport. The latest `72fe…` test harness did not retain a viewport screenshot, so do not attribute an old black screenshot to that exact ELF.

### 3. The UI map is only a loader/bootstrap test, not scene content

The source plan labels this package UI-only and says it has no gameplay BSP set ([`plans/7.hcu-remake-m2-m4.md:181`](../../plans/7.hcu-remake-m2-m4.md#L181)). Its test proves HMAP/CTAG/CRNG/CBIX/B000 reads and the UI load marker; it does not await or assert `main_game_render()`, a parent renderer call, a presented frame, any draw count, or a non-black framebuffer. `main_game_render()` ultimately calls CE `render_frame()` for a computed window list ([`main.c:3311-3397`](../../submodules/halo-ce-universal/source/main/main.c#L3311)). Snapshot storage is now bound, but the current guest test does not instrument whether this callback commits a snapshot, and no GS/VU renderer consumes one.

Even if the parent's `bsp_render_*` path were initialized, this UI load would not prove that a gameplay BSP, expected map geometry, texture inputs, or object pass had been loaded and bound. The package is a valid test for UI scenario/tag load, not a valid “first visible world” fixture. Do not add placeholder geometry or mark an empty clear-color frame as visible-world acceptance.

## Finding classification

### Proven structural causes

1. The combined HCU target excludes the parent viewer entry that performs GS/video/VU1 initialization and advances/submits the parent renderer loop; HCU `hcu_main` has no replacement calls.
2. The prior production snapshot-bind omission has been fixed in the current tree; however, no runtime counter confirms a committed snapshot, and there is still no parent GS/VU scene consumer or frame submission.
3. The snapshot/DMA packet helper is not a GS renderer, and source search finds no production consumer dispatching its packet or using latest snapshot data to drive BSP/object rendering.
4. `m2-ui-map-loaded` means `scenario_load()` returned success; it is intentionally only a loader boundary. The UI package is not a gameplay BSP scene test.

Any one of the first three is sufficient to explain why loaded-tag state can coexist with an all-black display. Together they make the absence of a draw path the overwhelmingly likely direct explanation.

### Correlated guest faults, not the black-frame root cause

The `627631...` interpreter run's unaligned accesses and HaloScript invalid-node assertion after the marker are real guest failures and require a separate source/ABI/data investigation. They may stop or destabilize later frame processing in that run, but they cannot explain the independent stable black capture on ELF `4a9bcce...`, which remained fault-free through its observation window. Do not “fix” the black viewport by changing script syntax, disabling the ring script, or changing the startup media.

### Hypotheses / not established

- Whether a nonblack flat color is ever submitted in the stable image is unobserved; there is no parent video initialization and no guest render counters, so the screenshot alone cannot distinguish a never-initialized display from an initialized-but-untouched black buffer.
- Whether a future UI/menu rendering path should draw before any gameplay scenario is loaded depends on the product/UI scope. The present target only proves scenario load, and no PS2 HUD quad/glyph consumer is connected.
- Whether the current `72fe0034...` image paints any non-black pixel is not visually established: its run directories contain logs/results but no screenshot. The renderer initialization/submission gap is established, while exact current-image pixel output remains unmeasured.
- PCSX2 graphics configuration is not implicated by current evidence: the emulator opens a Vulkan render window and the black screenshot is from a guest-run capture. There is no comparison showing that changing the PCSX2 host renderer creates the missing PS2 DMA submission.

## Smallest end-to-end implementation slice that moves toward a real visible scene

Do not try to draw the Halo CE scene directly from the existing matrix-only DMA packet; it has no geometry, materials, texture ownership, or GS frame lifecycle. The smallest honest end-to-end slice is a **single BSP clear/background path** that uses a real, capacity-qualified map BSP and the existing parent GS/VU renderer, followed immediately by the first actual BSP batches:

1. **Choose a real non-UI test map/BSP only after its M2 capacity gate is satisfied.** Keep catalog denial until CTAG and selected CBSP can be materialized into their fixed CE/tag and `current_bsp` owners with validator scratch, graphics packs, and load/decode overlap all counted. Current 2 MiB tag-cache and 393,216-byte `frame_scratch` are UI/bootstrap values, not authority to admit Longest or Blood Gulch. The fixed region binder/boot allocation in [`hcu_main.c:150-220`](../../src/stream/hcu_main.c#L150) already protects the 26 MiB reserve boundary; do not steal that reserve or merge dynamic, BSP, and renderer/DMA ownership to force a fit.
2. **Initialize the existing parent machine renderer once from the HCU entry.** Bring up GIF/VIF1 DMA and GS video, call `video_init()`/`bsp_render_init()` on the stable PS2 side, and preserve its VU1 microprogram and uncached chain allocations. Ensure all chain/packet data remains in named `dma_commands` or other measured aligned EE storage; keep GS VRAM usage inside 4 MiB and account framebuffers, Z buffer, texture window, CLUT/font/cache pages. Treat VU1 microprogram/data memory, GS VRAM, and EE RAM as separate finite stores, not interchangeable capacity.
3. **Status: partial — storage bind is implemented and guest-startup-tested; publication and renderer consumption remain open.** Production `hcu_main()` now binds the two snapshot banks in `frame_scratch` and VIF packet storage in `dma_commands` before CE startup, then passes map loading a non-overlapping 124,224-byte `frame_scratch` tail. The exact guest log reports `banks=268992`, `scratch-cap=124224`, and `dma=4128`; UI load passes in interpreter and recompiler. Keep tests for generation/sequence, viewport/camera, object count, first-person node bounds, maximum view count, and actual snapshot publication. This tail is sufficient for the current 98,304-byte decoder workspace plus the UI BSP payload, not the Longest/Blood Gulch BSP envelope; the complete owner/capacity ledger must still prove any larger payload strategy before map admission.
4. **Build a minimal BSP-to-renderer adapter for one view.** Convert the accepted CE camera record into the existing `camera_t`; use the CE world/BSP that was loaded and validated, not the unrelated UI fixture. Provide material IDs and texture/lightmap callbacks backed by bounded PS2 texture assets; bind a first pass that produces visible BSP batches. Do not interpret `hcu_render_snapshot_publish_dma()`'s matrix unpack as a mesh draw. Initially omit optional HUD/effect/audio visuals, but do not skip CE frame timers or camera selection.
5. **Drive and present frames.** For each accepted CE presentation frame: acquire a stable immutable snapshot; build the GS/VIF chain using existing `bsp_render_build()`; start it with `bsp_render_kick()`; wait/observe VIF1 and GS FINISH correctly; flip/present at PS2 cadence. The PS2's 4 MiB GS VRAM and finite EE/VU1 throughput and memory require measuring chain qwords, VU1 work, texture residency/cache evictions, DMA completion, and frame time against the 30 Hz gameplay cadence. Do not copy the N64's lower hardware constraints or its reduced update frequency; do not assume the faster EE means an unbounded BSP/object/texture workload.
6. **Instrument every layer and verify a real image.** Add counters/markers for `snapshot-generation`, `camera-valid`, selected BSP id, renderer initialized, visible cluster/batch/triangle counts, texture/material misses, VIF1 submitted/completed, GS FINISH, frame flip, and presented-frame number. A host fixture should drive a synthetic camera and finite matrices through the adapter; an EE/PCSX2 run should then use the exact rebuilt ELF/package hashes and retain both guest logs and a PCSX2 viewport screenshot. Require at least one visible real BSP batch and nonblack pixels in the game viewport over multiple frames, with no exception, lost canary, arena overflow, bad texture read, or memory/reserve violation. This would qualify one visible map slice—not full HUD/particles, all maps, or M2 completion.

### Tests and acceptance for this first visual slice

- Host tests: snapshot binding is mandatory; begin-before-bind fails cleanly; frame snapshot contains valid view/BSP identity; camera/matrix conversion parity; no stale snapshot after unload; failure/retry leaves renderer and arena state consistent.
- Target compile/link: exact HCU/parent/submodule pins and zero unresolved symbols; confirm machine entry includes renderer initialization/consumer and not the default viewer's independent main loop.
- PCSX2 interpreter and recompiler: exact artifact hash reaches map/BSP committed marker, visible-batch marker, VIF submit/finish and frame-present markers without post-load errors; preserve viewport captures and verify pixels are not all black. Logs alone are insufficient for pixel acceptance.
- PS2 hardware qualification when available: repeat same BSP path with EE timing and EE/GS/VU1/texture high-water; keep the 5.5 MiB v2 reserve intact and avoid unmeasured allocation in the 2.5 MiB `dynamic_simulation`, 6 MiB `current_bsp`, 4 MiB texture cache, 1.125 MiB DMA chain pool, and 384 KiB `frame_scratch` budgets.

## Useful code and comparison references

- HCU frame adapter and snapshot producer: [`ps2_render.c:120-210`](../../submodules/halo-ce-universal/port/ps2/src/ps2_render.c#L120).
- Snapshot storage binding/producer guard and matrix packet: [`hcu_render_snapshot.c:38-95`](../../src/stream/hcu_render_snapshot.c#L38), [`hcu_render_snapshot.c:213-265`](../../src/stream/hcu_render_snapshot.c#L213).
- Combined-vs-viewer target selection: [`ee-world.mk:45-65`](../../tools/ee-world.mk#L45).
- Parent GS/VU initialization and submission contract: [`main.c:142-147`](../../submodules/halo-ps2/engine/src/main.c#L142), [`main.c:248-274`](../../submodules/halo-ps2/engine/src/main.c#L248), [`main.c:307-311`](../../submodules/halo-ps2/engine/src/main.c#L307); renderer API documents build/kick at [`bsp_render.h:71-82`](../../submodules/halo-ps2/engine/src/render/bsp_render.h#L71).
- Halo-64's actual equivalent of a renderer bridge is instructive, not drop-in: `n64_render_game.c` increments frame state, maps each CE camera/window to an N64 view, invokes `n64_render_view`, draws objects, first-person weapon, particles and HUD ([`n64_render_game.c:517-685`](../../submodules/halo-64/port/n64/game/n64_render_game.c#L517)). Its notes stress that even a no-draw backend must advance render frame/camera/local-player state, first-person pose, HUD timers, and rasterizer bounds ([`NOTES.md:33-59`](../../submodules/halo-64/port/n64/NOTES.md#L33)). The PS2 port likewise must preserve stateful CE behavior, but replace the N64 draw calls with the existing GS/VU1 path.

## Current-image rerun and REA boundary (2026-10-21)

The ordinary combined machine was rebuilt after refreshing the production `all-no-bootstrap-memory` closure. HCU compiled 369 units with zero failures; the rooted object hash is `0645f18c1bc7332b8f4ec161b85b947653e4673fdab1a7fa57fac4e7de64a3e1`, and its closure report is `6d035c6a39f20a82de729cb2be4f779bb67d05a88736ff152b5f5c8fd2ff6e47`. The machine ELF is SHA-256 `03670da6e3d66ee4f8531e9b7874d535698382ba7cb9ed3b90f13473dab2ee3a`, with zero unresolved imports and 2,085,636 LOAD file bytes. Pins recorded by the guest harness: parent `70e2ed0cf2145a45d23aa07414a3a88c05155d4c`, HCU `6933490b2d16bb1c637295b6a0f3880ba23a7d56`, halo-ps2 `71183bb0a9adc586cd267b2780c82bbc12cfd95b`. The working trees also contain uncommitted changes; the ELF/source-object hashes, not commit IDs alone, identify this build.

Fresh run command:

```sh
APPIMAGE_EXTRACT_AND_RUN=1 python3 tools/test_hcu_boot.py --mode both --stage m2-ui --stable-seconds 5 --elf build/hcu-parent-link-probe/hcu-gameplay-machine.elf --disc build/hcu-m1-disc-data.iso
```

Interpreter passed in 37.851 seconds total with the requested five-second post-marker interval. Its result/log are [`result.json`](../../build/hcu-ps2-closure/emulator-m1-interpreter-5f5c7b57714e46d4a217851924f3202d/result.json), SHA-256 `5f136a4f4b7bdcf1c0946354b500dfd7d708db7bbc603ba3838a4228279dd94d`, and [`emulog.txt`](../../build/hcu-ps2-closure/emulator-m1-interpreter-5f5c7b57714e46d4a217851924f3202d/emulog.txt), SHA-256 `f97edb01e49546f3e33844e7d050d5ff6f0883e28b45f8858222e6a25fba9c34`. Recompiler passed in 24.323 seconds total, with [`result.json`](../../build/hcu-ps2-closure/emulator-m1-recompiler-2549336e0de14c5ebff3963adb2c4771/result.json), SHA-256 `3410e4f4769cc708a5f6f0eb301ec598bf2c7e0058802a6c5087f879500859ea`, and [`emulog.txt`](../../build/hcu-ps2-closure/emulator-m1-recompiler-2549336e0de14c5ebff3963adb2c4771/emulog.txt), SHA-256 `2a12b9f848e95534fd2768eb5cec41c6c2d3af11bed555d6746217d27550e35a`. Both reached `HALO_PS2_LOCAL m2-ui-map-loaded`, had no failure after the requested boundary, and observed unchanged host assets. They used the mounted data ISO SHA-256 `79f2855a5953483637ca060e778589a9f8c54e5fc4cda4a69347f22484457d79` (not booted), UI map SHA-256 `8556b647b82742d07282fe4e6db0cf847b542c046484e91e71ec31fea5f5fd7e`, UI HP2 SHA-256 `a83ded5049128dc0287b975af9c17f4224e467ad5e10ffa079468934e6241e90`; settings hashes differ by mode and are retained in each result.

This `03670da6...` image run did not include a PCSX2 screenshot. It has since been superseded by the `72fe0034...` snapshot-bound image below, which also has no screenshot. The current HCU entry still does not initialize or drive the parent renderer, and no consumer submits a CE-derived scene through the parent GS/VU path. Thus a Halo world scene is not expected yet, despite the successful UI-load marker.

I also attempted to open the rebuilt ELF in REA 6.5.0 with its available Ghidra provider. REA rejected it before analysis: its MIPS/R5900 target is outside the configured Ghidra and Hopper processor lanes (`architecture_unsupported`); the preserved failing ELF `b347420832736d5370c3dfa338522b9849d1cc1e726d554d0590ead49fb9c970` has the same target limitation. This is not disassembly evidence and no pseudocode claim is made. The unchanged data-only ISO's REA/xorriso inventory remains recorded in [`m2-iso-and-pcsx2-boot-audit.md`](m2-iso-and-pcsx2-boot-audit.md): it is mounted input, not an executable boot image. Standard `file`/`readelf` independently identify the ELF32 little-endian MIPS executable and ISO 9660 container, but do not replace the unavailable REA R5900 analysis lane.

## Snapshot-bind slice guest qualification (2026-10-21)

The production entry now calls `hcu_render_snapshot_bind()` after the parent v2 arenas are ready and before map-service/shell startup. It reserves `268,992` bytes for two pointer-free snapshot banks and `4,128` bytes for VIF payloads. The map service receives only the non-overlapping `frame_scratch` tail: `124,224` bytes. At runtime, both logs print `render-snapshot-bound banks=268992 scratch-cap=124224 dma=4128`; the UI package's B000 section then decodes to 2,288 bytes, and both modes reach the UI marker fault-free. This validates the bind order and that the UI loader still operates with the partition. It does not show that a CE render callback commits a snapshot, that DMA is submitted, or that any pixels change.

The rebuilt exact machine ELF is SHA-256 `72fe0034df7a70a13e26d95ef470006054e6e5ff5425170c89a80e98b2319ff2`. The refreshed HCU closure compiled 369 units, zero failures; parent-link metadata reports zero undefined symbols and 2,086,532 LOAD file bytes (10,620 bytes below `elf_static`). The host inputs/pins are the ones listed in the previous subsection; asset hashes did not change. PCSX2 command remained:

```sh
APPIMAGE_EXTRACT_AND_RUN=1 python3 tools/test_hcu_boot.py --mode both --stage m2-ui --stable-seconds 5 --elf build/hcu-parent-link-probe/hcu-gameplay-machine.elf --disc build/hcu-m1-disc-data.iso
```

Interpreter passed in 37.597 seconds total with 5.016 seconds after the marker. Run directory: [`emulator-m1-interpreter-c6c9ff0fc197473388843699c29dd965`](../../build/hcu-ps2-closure/emulator-m1-interpreter-c6c9ff0fc197473388843699c29dd965); result SHA `40ce208efe4bdc1e82b0a5a00e687d7301be1fecf250329143ce4d5a5454e320`, log SHA `4e62fa8cc03a03c1152e6b8a633e111c005effb2cd0a7a5bae60efb21e55022e`. Recompiler passed in 24.314 seconds total with 5.016 seconds after the marker. Run directory: [`emulator-m1-recompiler-26857112060e4cd6b2ef735c53274a0d`](../../build/hcu-ps2-closure/emulator-m1-recompiler-26857112060e4cd6b2ef735c53274a0d); result SHA `69ea29329dd91c7b1b01d024f6bd5f35cce3264c4807144eee76f4ecb52986fe`, log SHA `e4f198243fb9b86d82dd686491d4d99642014b0a360424371746f3e8574ba030`. Neither run directory includes a viewport screenshot because the harness closes PCSX2 after the marker's stable window. The historical MIPS provider rejection still applies as a capability limitation; it does not analyze this current ELF's code.

