# Step 8: multiplayer render-owner and GS texture-cache stress

## Result

Added and ran a separate host diagnostic over all 13 pinned stock multiplayer maps. It combines two previously separate proofs:

1. The real halo-ps2 HP2 section loader retains each map's converted TEXS, all emitted LMn, selected MODL, and scenario-selected OTEX in a guarded 4,014,928-byte candidate render owner. model_open, tex_open, and lm_open validate the retained sections.
2. The actual render/texcache.c implementation allocates the resources in BSP-texture, lightmap-slot, then object-texture key order. The fixture feeds the same top-level mip data and CLUT sizes as the production callbacks, the renderer's 270-page NTSC cache capacity, 127 CLUT slots, and the 1.5 MiB per-frame upload budget. It scans all resources for two consecutive frame numbers and records uploads, hits, deferrals, and occupied-page high-water.

All maps completed both scans with zero TC_FULL failures, owner and scratch bounds intact, outer canaries intact, and cache flush/owner rewind verified. Blood Gulch is the closest RAM owner at 3,954,720 / 4,014,928 bytes (60,208 bytes free). Sidewinder is 3,697,632 bytes. Blood Gulch's conservative all-resource pass deferred two uploads in frame 0; frame 1 accepted those two, with the other 76 resources as cache hits. Thus the candidate is tight but this resource set did not reveal an intrinsically uncacheable texture or permanent upload-budget starvation.

This is useful candidate evidence, not proof of a production-capacity fit or a rendered frame. The fixture intentionally requests every texture and every nonempty lightmap page, rather than deriving the visible per-frame subset from BSP/PVS and a camera. It does not issue PATH3 uploads, simulate in-flight GS references/DMA chains, include BSP geometry, SCEN, ANIM, sky/effect/HUD/weapon resources, or execute on PCSX2/EE.

## Per-map results

owner is the high-water of co-resident converted section data in the candidate render owner. cache high-water is occupied texture pages under the actual renderer cache API; the 270-page limit reflects the current 512x448 NTSC mode and renderer's reserved pages, as derived below. uploads / hits / deferred list frame 0 then frame 1.

| Map | Owner high-water / cap (bytes) | Resources scanned | Cache high-water / cap (pages) | Uploads | Hits | Deferred | Full |
|---|---:|---:|---:|---:|---:|---:|---:|
| Beaver Creek | 1,928,544 / 4,014,928 | 49 | 135 / 270 | 49, 0 | 0, 49 | 0, 0 | 0, 0 |
| Blood Gulch | 3,954,720 / 4,014,928 | 78 | 221 / 270 | 76, 2 | 0, 76 | 2, 0 | 0, 0 |
| Boarding Action | 1,648,992 / 4,014,928 | 54 | 118 / 270 | 54, 0 | 0, 54 | 0, 0 | 0, 0 |
| Carousel | 1,406,784 / 4,014,928 | 55 | 110 / 270 | 55, 0 | 0, 55 | 0, 0 | 0, 0 |
| Chill Out | 1,267,200 / 4,014,928 | 35 | 80 / 270 | 35, 0 | 0, 35 | 0, 0 | 0, 0 |
| Damnation | 1,722,624 / 4,014,928 | 45 | 114 / 270 | 45, 0 | 0, 45 | 0, 0 | 0, 0 |
| Hang 'Em High | 1,675,456 / 4,014,928 | 24 | 113 / 270 | 24, 0 | 0, 24 | 0, 0 | 0, 0 |
| Longest | 1,525,568 / 4,014,928 | 25 | 95 / 270 | 25, 0 | 0, 25 | 0, 0 | 0, 0 |
| Prisoner | 1,652,576 / 4,014,928 | 26 | 109 / 270 | 26, 0 | 0, 26 | 0, 0 | 0, 0 |
| Putput | 1,078,720 / 4,014,928 | 27 | 65 / 270 | 27, 0 | 0, 27 | 0, 0 | 0, 0 |
| Rat Race | 1,472,864 / 4,014,928 | 39 | 99 / 270 | 39, 0 | 0, 39 | 0, 0 | 0, 0 |
| Sidewinder | 3,697,632 / 4,014,928 | 71 | 195 / 270 | 71, 0 | 0, 71 | 0, 0 | 0, 0 |
| Wizard | 1,449,600 / 4,014,928 | 35 | 99 / 270 | 35, 0 | 0, 35 | 0, 0 | 0, 0 |

The runtime emits one row per map with scratch high-water 98,304 / 524,288 bytes. Selected MODL coverage ranged from 4 models / 23 parts on Putput to 25 models / 163 parts on Blood Gulch; these are converter model-section counts, not spawned-object counts.

## Source basis and limits of the model

- submodules/halo-ps2/engine/src/world/section.c:153-245 is the actual bounded section path: it reserves a 64-byte-aligned decoded section, uses distinct history/input/output scratch, rewinds scratch on success, and releases the owner mark if decode/CRC fails.
- submodules/halo-ps2/engine/src/world/tex.c:28-71,121-167 validates texture tables, mip extents, CLUTs, and lightmap-page extents; model.c:model_open validates the converted model section.
- The production world.c:21-37 callback supplies mip 0, its pixel bytes, and the CLUT; world.c:43-57 supplies lightmap page pixels and the shared 1,024-byte CLUT. This fixture uses those same parser views.
- submodules/halo-ps2/engine/src/render/bsp_render.c:29-33 reserves 16 texture-window pages for CLUTs and one for the font. Its pages_for and resident_tex0 at :344-382 compute page occupancy, charge pixel-plus-CLUT upload bytes, request a cache entry, and enqueue the real GS upload pair. :800-802 and :832-840 establish texture/lightmap/object key ordering and the 1.5 MiB budget.
- The page count used by the diagnostic follows platform/video.h (512x448, 4 MiB GS VRAM) and platform/video.c:14-29: the two CT16 framebuffers and Z24 buffer consume 1,835,008 bytes (224 GS pages), and bsp_render.c:164 starts the texture window after the extra allocated page. 512 total GS pages - 224 framebuffer/Z pages - 1 window-base page - 17 CLUT/font pages = 270 cache pages.
- Halo-64's `submodules/halo-64/port/n64/NOTES.md:115-155` is a useful comparison for why its texture policy cannot be copied: its first-person atlas had to be split into windows and represented as small CI4 textures, while it also describes tradeoffs around its level texture path. This measurement instead uses this repository's halo-ps2 GS/VRAM/cache implementation and its 270-page renderer window; no N64 texture or pool limit is imported.

The test's two complete resource scans are a deliberately conservative cache-pressure trace. A real frame obtains resources from PVS-visible batches and materials; no camera or CE-derived visible-material trace is present here. The frame-0 deferral on Blood Gulch is therefore a worst-case request-order observation, not evidence that a normal frame drops a visible material. Actual gs_upload_pair packet growth, 512 KiB upload chains, transfer overlap with VIF/GS, texture residency under movement, and R5900 timing remain unmeasured.

## Reproduction and provenance

Reproduce by running:

    python3 tools/test_halo_ps2_mp_render_cache_stress.py

Successful retained run:

- Directory: build/mp-render-cache-stress/1792694848520442898/
- Manifest SHA-256: 2437ba15487881814141f270b0ef6f73e640f913d8424ed1941ca974a1b50a73
- Runtime log SHA-256: cb5a3c21038133ad19c081af47a79d93491f6f983c48bef391ee3fd5f5f45c67
- Host executable SHA-256: 0cad89bffb8c2645abf814876c7639dae774d83759c80a980696eed8ab35b447
- Link map SHA-256: f8806ae24b837ad3dd1419a41fa05b06052690173f9b8a830dac99f293aa0cea
- Runner SHA-256: 14a1d05e95cc245fa2be901c2a29c25f232a67453c711316ebe0f640311b5cfe
- C fixture SHA-256: e2c48ceb50749b55b02f2935960fca8aef0ce09bbac536d8bca4a2d7d269a4d9
- Pins: parent 70e2ed0cf2145a45d23aa07414a3a88c05155d4c; halo-ce-universal 6933490b2d16bb1c637295b6a0f3880ba23a7d56; halo-ps2 71183bb0a9adc586cd267b2780c82bbc12cfd95b.

The manifest has each retail-map source hash, generated-section hashes, command, executable/link-map/log hashes, source pins, and all 13 output rows. The diagnostic changes neither production owner sizes nor admission.
