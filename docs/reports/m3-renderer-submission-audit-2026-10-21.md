# M3 renderer and submission audit — 2026-10-21

## Scope and provenance

This is a report-only source audit of the M3 Group F / Steps 13–14 renderer boundary. It answers what is currently connected, what can draw actual scene geometry, which buffers own the work, and the smallest route from the CE render callback to PS2 scene pixels. No source, plan, or shared report was changed. REA was not used: the question is answered directly by the pinned source and the existing PCSX2/host evidence; there is no opaque binary behavior that requires decompilation for this audit.

Inspected pins: parent `70e2ed0cf2145a45d23aa07414a3a88c05155d4c`, `halo-ce-universal` `6933490b2d16bb1c637295b6a0f3880ba23a7d56`, `halo-ps2` `71183bb0a9adc586cd267b2780c82bbc12cfd95b`, and Halo-64 `17541f4444baabb47d1a0deb917f26ccb7b6bc5c`. Worktrees are dirty, so these are HEAD pins, not assertions that all currently inspected files equal their committed versions. Relevant render sources were read in the shared worktree.

## Findings at a glance

1. The HCU side now advances CE presentation state and publishes a pointer-free, double-buffered camera/object/first-person snapshot. It does not call `bsp_render_build`, submit that snapshot's matrices to VU1, submit a real scene chain, or present a scene frame. The snapshot-to-DMA function is only a CPU packet packer, with a hard 64-total-matrix cap, and currently has no production DMA consumer ([PS2 adapter](../../submodules/halo-ce-universal/port/ps2/src/ps2_render.c#L120), [snapshot packer](../../src/stream/hcu_render_snapshot.c#L213)).
2. The separate PS2 BSP renderer is not a stub: it already performs BSP visibility/material/lightmap passes, VU1 vertex work, upload DMA, GIF/VIF submission, GS finish polling, and double buffering ([BSP build](../../submodules/halo-ps2/engine/src/render/bsp_render.c#L562), [kick](../../submodules/halo-ps2/engine/src/render/bsp_render.c#L747)). But the HCU machine target currently links it without initializing it or supplying a loaded HP2 `bsp_section` and texture callbacks. `hcu_main` enters the CE shell after binding the snapshot and map service; only an optional clear diagnostic calls `video_init()`/`video_present()` ([HCU boot path](../../src/stream/hcu_main.c#L331)).
3. The smallest real-pixels implementation is not to submit the existing matrix-only VIF slab. It is to add one parent render-frame consumer that reads the latest committed CE snapshot, converts its camera to `camera_t`, invokes the already-built BSP renderer on the *same admitted map’s* PS2 render pack, kicks the real BSP/texture chains, waits/polls the correct fences, then flips/presents. The initial diagnostic should draw only the BSP (the renderer's existing object pass can stay disabled); that is the smallest game-scene pixel gate. Later object/first-person/HUD parity is a separate increment.
4. This cannot be qualified against UI-only assets. The current guest can load the UI map, which has no admitted gameplay BSP scene; it presents a black viewport. M2 has to produce a gameplay-map layout and render pack that fit the actual PS2 budget before Step 13 can prove the normal game scene. The working-set audit explicitly excludes HP2/render pack, texture-cache, streaming and load/unload peaks from its lower-bound result, and nine candidate maps exceed the combined tag+BSP lower-bound budget even before those items ([working-set result](./retail-map-working-set-2fba411b.json#L1)).

## Existing source paths and what they prove

### CE/HCU producer

`ps2_render.c:120–210` is the real CE `render_frame` implementation for this port. It advances `render.frame_index`, selects the first non-console player window, copies CE camera and viewport/window bounds, calls `first_person_weapon_render_update()`, copies first-person node transforms and enumerates live CE objects, then commits the snapshot. A complete snapshot can hold 2,048 objects and 64 first-person nodes ([snapshot schema](../../submodules/halo-ce-universal/port/ps2/include/halo_ps2_render_snapshot.h#L8)). This is the right ownership direction: CE object datums remain authoritative; the parent receives stable IDs and transforms, not pointers into CE object pools.

Snapshot storage is bound by `hcu_main` to two banks in `frame_scratch`; it gives the remaining scratch tail to the map service. It also passes the beginning of `dma_commands` to the snapshot helper as a second staging allocation ([binding](../../src/stream/hcu_main.c#L331)). The snapshot code validates finite matrices/camera and keeps the previous committed bank readable while the next is written ([commit](../../src/stream/hcu_render_snapshot.c#L112)).

The machine loop contains no normal renderer initialization or submission: after storage/map-service setup, it calls `halo_shell_main()` ([`hcu_main.c:353–398`](../../src/stream/hcu_main.c#L353)). The optional `HALO_PS2_M3_RENDER_CLEAR_TEST` submits a GS clear using a small packet carved from `dma_commands`; this proves framebuffer setup and one GIF transfer, not BSP/model drawing ([diagnostic](../../src/stream/hcu_main.c#L58)). `ps2_render.c`'s weak `hcu_render_snapshot_publish_dma()` hook is overridden by the parent packer, but that packer only writes a VIF UNPACK header plus up to 64 transformed matrices into memory; `ps2_render.c:208–209` calls it and nothing submits the result to VIF1 ([packer](../../src/stream/hcu_render_snapshot.c#L213)).

### Parent/halo-ps2 renderer and presentation

The parent target compiles `bsp_render`, `camera`, `chain`, `obj_render`, texture cache, uploads, visibility, and VU1 world code ([`ee-world.mk:5–44`](../../tools/ee-world.mk#L5)). The HCU target adds the machine entry, snapshot, and map service ([`ee-world.mk:45–63`](../../tools/ee-world.mk#L45)), but linking an object is not a call path.

The BSP renderer has nearly all the required scene draw stages:

- `bsp_render_init()` initializes VIF1, uploads the BSP/model VU programs and double-buffer layout, allocates two geometry and two texture/lightmap upload chain buffers, sets the GS texture/Z extents, creates its environment packet, and uploads a font ([`bsp_render.c:85–101`](../../submodules/halo-ps2/engine/src/render/bsp_render.c#L85), [`:152–171`](../../submodules/halo-ps2/engine/src/render/bsp_render.c#L152)).
- `bsp_render_set_world()` binds an HP2-decoded `bsp_section`, resolves materials, and allocates map-lifetime visibility, sorting, clipping, and bound data through the provided arena ([`bsp_render.c:174–234`](../../submodules/halo-ps2/engine/src/render/bsp_render.c#L174)).
- `bsp_render_build()` computes camera frustum/clip transforms, runs portal/PVS visibility, groups by material, queues base and lightmap passes, optional object pass/overlay, a GS FINISH marker, and records chain high-water/overflow ([`bsp_render.c:562–588`](../../submodules/halo-ps2/engine/src/render/bsp_render.c#L562), [`:702–744`](../../submodules/halo-ps2/engine/src/render/bsp_render.c#L702)).
- `bsp_render_kick()` submits environment and upload data, then starts VIF1 geometry submission. `bsp_render_poll()` observes VIF1 completion and GS FINISH; `bsp_render_wait_gpu()` is the bounded drain used before teardown ([`bsp_render.c:747–780`](../../submodules/halo-ps2/engine/src/render/bsp_render.c#L747)).
- `video_init()` allocates two GS framebuffers, Z buffer, and texture window from 4 MiB GS eDRAM. `video_present()` flips the display buffer separately; those extents must not be charged as EE RAM ([video allocation](../../submodules/halo-ps2/engine/src/platform/video.c#L9)).

The existing host/diagnostic viewer demonstrates the expected world lifecycle: set the BSP from a `world_load()` result, render frames, then `bsp_render_clear_world()` (which drains GPU use) before resetting/reloading the arena ([viewer reload sequence](../../src/stream/viewer_diagnostic.c#L295)). It is valuable as renderer evidence but is a separate free-camera application, not HCU gameplay.

## Required camera and scene-data bridge

The CE snapshot camera stores position, forward/up vectors, vertical FOV, near/far planes, viewport, and window bounds. The PS2 BSP renderer's `camera_t` instead stores position, yaw, pitch, *horizontal* FOV, display aspect, near/far. The current snapshot has no dedicated conversion API for this type. A correct adapter must derive orientation robustly from normalized CE forward/up (not assume yaw/pitch convention), set horizontal FOV from vertical FOV and selected view aspect, preserve the CE viewport for split-screen/scissor policy, and reject degenerate/non-finite bases. It must verify PS2 BSP world axes and CE axis/handedness with fixed known vectors plus a gameplay in-world camera. Existing `hcu_render_snapshot_matrix_from_ce()` converts object transforms but its 64-matrix staging output is not a substitute for a camera and scene draw adapter ([matrix conversion](../../src/stream/hcu_render_snapshot.c#L165)).

The first-pixels bridge has two map owners that must not be confused:

- CE tag/scenario/BSP globals are gameplay authority and used by HCU collision, AI, game logic, and scenario lifetime.
- The halo-ps2 rasterizer consumes the converted `.hp2`/world `bsp_section` plus the corresponding PS2 texture/lightmap source callbacks. It does not draw directly from CE `structure_bsp` tags.

The HCU snapshot omits rendered-cluster selection, per-object model/region/permutation/animation data, material/shader-to-bitmap bindings, sky/particle/effect/HUD primitives, and texture handles. Some are not needed for the earliest BSP-only pixel proof, but the renderer’s callbacks still need to serve BSP materials and lightmaps. Object pixels then require a deliberate CE datum/definition/model/animation-node bridge into halo-ps2's object rendering structures; do not treat `definition_index` as a model index absent a verified mapping. Full Halo CE presentation parity also has stateful obligations: Halo-64's notes specifically retain per-view camera/frustum/local-player and first-person animation updates, HUD timer/sound state, and frame counters even when the platform draw path changes ([Halo-64 notes](../../submodules/halo-64/port/n64/NOTES.md#L33)).

## DMA, storage, and fences

### Existing bounded budgets

The `dma_commands` region is exactly 1,179,648 bytes. `bsp_render.c`'s current renderer reserves two geometry chains of 32,768 qwords (512 KiB each) and two upload chains of 4,096 qwords (64 KiB each): the four maximum capacities exactly equal the region, leaving no nominal room for a second 4,128-byte matrix staging buffer, per-frame extra packet, or unbudgeted padding. `bsp_render_init()` currently allocates those chains with `memalign(64)` and switches them to uncached aliases; the fixed arena itself must therefore be explicitly 64-byte aligned and the cache/alias contract preserved. Merely passing the arena's current 16-byte-aligned base is incorrect. The v2 allocator already requests 64-byte alignment for the DMA region in the inspected pin, but padding, guards and final base must remain proven in the physical layout ([region layout](../../submodules/halo-ps2/engine/src/core/mem.c#L68)).

The snapshot's `publish_dma()` separately owns bytes at the base of that same `dma_commands` arena. Its memory is not DMAed now, so this is a latent overlap with any renderer that starts its first chain there. Production integration must remove that duplicate staging reservation/use or allocate a single non-overlapping subregion explicitly; the recommendation is to stop treating the packet as a persistent arena owner and pack directly into the selected renderer chain. Do not reduce the 2,048-object snapshot capacity to satisfy the current 64-matrix helper cap.

PS2 safety constraints for the first scene consumer:

1. Geometry chain N is writable only when its previous VIF1 transfer and resulting GS FINISH are complete. The current renderer's two-chain toggle and `bsp_render_poll()`/`bsp_render_wait_gpu()` are the baseline; never read a double-buffer flip as a fence by itself.
2. Upload-source buffers and texture/lightmap pixels remain immutable until GIF path 3 transfer completion; renderer kick currently synchronously waits after upload chain before launching VIF1 geometry.
3. Before presenting/flipping, ensure the frame's GS FINISH marker has been observed. `bsp_render_kick()` returns with VIF1 active; presentation must not race it. `video_present()` alone is not a completion fence.
4. On map unload/retry, stop snapshot producers, drain VIF1/GIF/GS, call renderer world clear, and only then release the PS2 world/BSP/textures and CE map owner. `bsp_render_clear_world()` documents this ordering and consumes/re-primes a FINISH marker.
5. Every packet2 payload, descriptors, matrices, upload staging buffer and chain must be attributed to a measured EE owner. `packet2_create()`/`memalign()` can allocate payloads outside the arena even when `malloc` wrappers exist; source existence is not an ownership ledger.
6. Retain and assert the full 1,179,648-byte chain limits initially. Fail closed on `chain_overflow`; report geometry/upload qwords, peak bytes, render time, texture cache evictions, VIF complete, GS FINISH, and presented frame. No partial chain submission.

### Minimal implementation slice for first actual game-scene pixels

**Slice F1: one CE-controlled camera, one admitted gameplay BSP, BSP-only geometry, full hardware submission.** This is the smallest coherent production path; it is not full object/HUD/effect parity.

1. **Wait for M2's gameplay map admission.** Select a scenario whose CE tag image, selected BSP, HP2 BSP/render pack, texture/lightmap inputs, validation scratch, and peak transition working set have passed M2 and exact physical ownership. UI-only is not valid. The current retail lower-bound JSON says nine candidates exceed combined resident tag+BSP budget; its “fits” cases are not proof because PS2 render packs and cache/streaming are expressly excluded.
2. **Connect the existing PS2 world package to the same map selection.** At CE scenario/map commit, resolve the matching preconverted HP2 BSP and texture/lightmap catalog entry; load into `current_bsp`/`texture_cache` owners; create the `bsp_section` and `tex_source_t`; on abort/unload, use the map transaction and renderer fence ordering above. Keep CE scenario globals authoritative; do not duplicate collision. A temporary BSP-only render may begin with no object pass, but it must be the same map and selected CE BSP index.
3. **Make DMA ownership single-source before enabling render.** Partition the actual `dma_commands` arena into the four existing 64-byte-aligned renderer buffers, and route persistent/temporary command payload ownership explicitly. Remove/disable the overlapping snapshot matrix staging output in production; snapshot data remains as the render input. Add bounds/canaries and slot generation/fence state.
4. **Initialize GS/VU/render exactly once in the combined machine.** Call `video_init()`, initialize GIF/VIF channels, and `bsp_render_init()` after the normal machine setup, not only under `HALO_PS2_M3_RENDER_CLEAR_TEST`. Ensure the HCU build packages `vu1/world` and renderer assets already present in the parent link. Avoid repeated `video_init()` or reinitializing DMA channels behind CE services.
5. **Consume each CE render snapshot at the frame boundary.** Use `hcu_render_snapshot_latest()` after commit; validate a new monotonically increasing sequence and a player camera. Convert that camera into parent `camera_t`; render one world view at the matching viewport. Call `bsp_render_build(frame_index, &camera, overlay=NULL)`, reject overflow/invalid visibility, then `bsp_render_kick(&video)`.
6. **Complete and present safely.** Poll/wait VIF1 and GS FINISH before reusing that chain or flipping; call `video_present()` for actual scanout. Keep CE's next simulation tick independent of rendering where possible, but the first implementation may use a blocking fence until two-chain ownership is proven. Add frame-sequence assertions to ensure a render neither skips nor modifies CE state.
7. **Test first with deterministic static BSP camera.** A developer diagnostic may use a fixed, CE-approved camera corresponding to a known safe starting location to prove the parent loader/renderer chain; it is only an intermediate check. Final F1 evidence must use the camera from a real CE gameplay tick and visual screenshot pixels from the exact same map package and exact ELF. Compare interpreter and recompiler. Record BSP clusters/batches/triangles, chain occupancy/overflow, texture stats, GPU completion, screenshot hash and input source pins.
8. **Then add object rendering.** Map each CE snapshot datum/definition to verified PS2 model data; provide node palette and animation transforms; preserve per-view order for world objects, first-person arms/weapon, particles/effects, HUD. Add immutable snapshot invariance tests across different render frequencies, and no missing-object truncation. This is required for broader Step 13/14/CE parity but not required to prove first BSP pixels.

## Tests and acceptance evidence

### Host/target tests to add before integration

- Camera conversion fixture from CE forward/up vectors to PS2 yaw/pitch/hFOV/aspect, including cardinal axes, pitched camera, roll/degenerate vectors, split-view bounds and invalid near/far; compare the produced clip/frustum with expected projection points.
- DMA partition test with deliberately misaligned source base; prove 64-byte-aligned non-overlapping slots, exact fixed capacities, guard protection, exhaustion behavior, and that snapshot banks/scratch cannot alias any live DMA region.
- DMA slot-state test: alternate chain generations; prohibit writing/submitting a slot until VIF and GS fences have both completed; inject missed finish/timeouts; prove map teardown waits.
- Renderer bridge fixture: feed a committed synthetic snapshot plus a real small known HP2 BSP, assert visible cluster/material/triangle counts, nonzero generated chain, zero overflow and no CE-state mutation. Host tests can validate build/packet structure but not GS pixels.
- Build/link audit: exact combined target contains `bsp_render_init/build/kick`, video init/present and both required VU entries, with one owner per symbol and no diagnostic-only stub winning weak-symbol resolution.

### PCSX2 and PS2 evidence required

For the exact image/hash, run both interpreter and recompiler and require ordered markers: `renderer-ready`, `gameplay-bsp-ready`, `render-snapshot-seq`, `render-build batches>0 triangles>0`, `chain-overflow=0`, `vif1-complete`, `gs-finish`, `frame-presented`. Capture a PCSX2 window screenshot after stable completed frames and verify visible map geometry rather than black, a flat clear, menu-only UI, or a free camera without the CE scenario. Preserve ELF/ISO/pack hashes, HCU/halo-ps2 pins, PCSX2 settings and logs. Later qualify on physical PS2 because PCSX2 success is necessary but not sufficient for DMA/cache and performance behavior.

Acceptance for this narrow F1 slice proves “the CE-controlled gameplay BSP draws pixels.” It does **not** prove all HCU world objects, weapon models, HUD, particles, effects, split-screen, scene parity, final CPU performance, or M3 Group F completion. Those remain explicit follow-on acceptance items.

## Halo-64 comparison (method only)

Halo-64 keeps CE's stateful render-facing frame/camera/first-person/HUD/timer obligations in `n64_render_game.c`, then its separate N64 renderer draws the per-window scene; render frame and presentation are separate entry points ([view loop](../../submodules/halo-64/port/n64/game/n64_render_game.c#L517), [present](../../submodules/halo-64/port/n64/game/n64_render_game.c#L725)). Its notes explain that frame index and first-person updates matter to non-render systems ([`NOTES.md:33–62`](../../submodules/halo-64/port/n64/NOTES.md#L33)). The applicable lesson is the adapter contract and explicit presentation boundary—not its different renderer, asset conversion, memory limits, object/effect cuts, reduced map distance, or any N64-only cadence.

## M3 Step 13–14 status recommendation

**Do not mark Steps 13–14 or Group F complete.** Current evidence supports: snapshot producer and validation exist; PS2 GS/VU1 BSP renderer exists independently; diagnostic clear can initialize/present a solid color; PCSX2 UI-load boundary is real. Missing are one production frame call path between the committed CE snapshot and BSP renderer, an M2-admitted gameplay PS2 render package, exact DMA-chain ownership without the latent overlap, CE-to-PS2 camera transform validation, real VIF/GIF/GS submission under HCU, and screenshot proof of game-scene geometry. The highest-priority route is F1 above, with M2 map admission and DMA ownership as hard dependencies, then CE object/model/animation/effect/HUD rendering expansion.

## Source index

- HCU snapshot producer: [`ps2_render.c:120–210`](../../submodules/halo-ce-universal/port/ps2/src/ps2_render.c#L120)
- Snapshot type and bounds: [`halo_ps2_render_snapshot.h:8–57`](../../submodules/halo-ce-universal/port/ps2/include/halo_ps2_render_snapshot.h#L8)
- Parent allocation/bind and render diagnostic: [`hcu_main.c:58–135`](../../src/stream/hcu_main.c#L58), [`:331–398`](../../src/stream/hcu_main.c#L331)
- Snapshot packer and current 64-matrix restriction: [`hcu_render_snapshot.c:197–275`](../../src/stream/hcu_render_snapshot.c#L197)
- PS2 renderer build/world/buffers/submission: [`bsp_render.c:25–41`](../../submodules/halo-ps2/engine/src/render/bsp_render.c#L25), [`:85–110`](../../submodules/halo-ps2/engine/src/render/bsp_render.c#L85), [`:152–235`](../../submodules/halo-ps2/engine/src/render/bsp_render.c#L152), [`:562–780`](../../submodules/halo-ps2/engine/src/render/bsp_render.c#L562)
- PS2 render chain writer: [`chain.c:4–45`](../../submodules/halo-ps2/engine/src/render/chain.c#L4)
- GS display/storage: [`video.c:9–87`](../../submodules/halo-ps2/engine/src/platform/video.c#L9)
- Existing separate viewer integration: [`viewer_diagnostic.c:295–339`](../../src/stream/viewer_diagnostic.c#L295)
- Comparative Halo-64 render adapter: [`n64_render_game.c:517–625`](../../submodules/halo-64/port/n64/game/n64_render_game.c#L517), [`:725–742`](../../submodules/halo-64/port/n64/game/n64_render_game.c#L725), [`NOTES.md:33–62`](../../submodules/halo-64/port/n64/NOTES.md#L33)
- M2 gameplay working-set gate: [retail-map-working-set-2fba411b.json](./retail-map-working-set-2fba411b.json)
- Separate DMA-budget deep dive: [m3-dma-allocator-next-slice-2026-10-21.md](./m3-dma-allocator-next-slice-2026-10-21.md)
