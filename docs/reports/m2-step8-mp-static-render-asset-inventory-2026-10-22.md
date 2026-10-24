# M2 Step 8: static render-asset inventory for 13 stock multiplayer maps

## Finding

I generated a reproducible, per-map inventory of converted BSP textures (`TEXS`), all converted lightmap sections (`LMn`), and scenario-selected object textures (`OTEX`) for the complete 13-map stock multiplayer set. This addresses the *offline static converted-section size* subquestion in Step 8; it is not a runtime cache high-water measurement, map-admission proof, or all-render-state bound.

| Stock MP map | BSP `TEXS` section | selected-object `OTEX` | all `LMn` sections | summed static texture sections | decoded lightmap pixels |
|---|---:|---:|---:|---:|---:|
| Beaver Creek | 389,728 | 875,808 | 16,288 | 1,281,824 | 14,784 |
| Blood Gulch | 406,016 | 1,705,504 | 33,120 | 2,144,640 | 31,552 |
| Boarding Action | 285,024 | 647,328 | 113,440 | 1,045,792 | 111,552 |
| Carousel | 167,904 | 679,040 | 43,328 | 890,272 | 41,344 |
| Chill Out | 315,456 | 425,664 | 31,904 | 773,024 | 30,528 |
| Damnation | 228,960 | 816,832 | 44,992 | 1,090,784 | 43,584 |
| Hang 'Em High | 352,384 | 745,728 | 83,072 | 1,181,184 | 81,920 |
| Longest | 354,528 | 638,784 | 17,504 | 1,010,816 | 16,384 |
| Prisoner | 380,288 | 745,568 | 33,920 | 1,159,776 | 32,768 |
| Putput | 174,112 | 389,376 | 34,144 | 597,632 | 32,768 |
| Rat Race | 382,400 | 509,088 | 30,880 | 922,368 | 29,440 |
| Sidewinder | 475,584 | 1,301,536 | 61,536 | 1,838,656 | 59,712 |
| Wizard | 171,136 | 754,176 | 18,208 | 943,520 | 16,768 |

The largest converted static texture-section sum is Blood Gulch at **2,144,640 bytes** (2.045 MiB); Sidewinder is next at 1,838,656 bytes. All 13 maps together sum to 14,880,288 bytes, but that is an *across-alternatives catalog total* and must not be charged as simultaneous live memory. Each row is the sum of one map's `TEXS` + scenario-selected `OTEX` + all its converted `LMn` sections. These rows do not include BSP geometry, object MODL/SCEN/ANIM/SKY sections, runtime-created effects, weapons, UI, DMA staging, decoded Xbox source buffers, cache fragmentation, or transition overlap.

The measured largest row is below the configured 4,194,304-byte `texture_cache` reservation in [`config/memory-budget.json`](../../config/memory-budget.json#L13), but this is not proof that those bytes are allocated from that reservation today. The parent/halo-ps2 section loader takes a caller-supplied arena and copies section payloads there; `world_load()` retains BSP, TEXS, and the selected LM section in its `arena` argument, and `world_load_objects()` retains MODL/SCEN and optional OTEX in its supplied arena ([`world.c`](../../submodules/halo-ps2/engine/src/world/world.c#L58), [`world.c`](../../submodules/halo-ps2/engine/src/world/world.c#L103), [`section.c`](../../submodules/halo-ps2/engine/src/world/section.c#L153)). Therefore the sums are asset sizes that an ownership design must place, not evidence that the current 4 MiB reservation is the allocator backing them or that concurrent live working set fits. The renderer consumes TEXS/LM payloads as source views ([`world.c`](../../submodules/halo-ps2/engine/src/world/world.c#L5), [`tex.c`](../../submodules/halo-ps2/engine/src/world/tex.c#L24)); these data are not evidence of a measured residency/eviction policy.

## How to reproduce and what was measured

The isolated audit is [`tools/audit_mp_render_asset_bound.py`](../../tools/audit_mp_render_asset_bound.py#L1). It hard-requires the 13 stock MP map filenames (campaign files are not included), runs pinned halo-ps2 `texconv.convert_map(..., lightmaps=True, lm_gain=1.5)`, parses the emitted `TEXS` and every `LMn`, and runs `scenconv.collect()` plus `modelconv.convert_map()` on the scenario-selected model tags and sky model. Its method corresponds to [`texconv.py`](../../submodules/halo-ps2/tools/halo2ps2/texconv.py#L973), which filters shader textures to BSP material references and lightmap pages referenced by rendered materials, and [`modelconv.py`](../../submodules/halo-ps2/tools/halo2ps2/modelconv.py#L829), which converts the supplied set of model tags and builds their OTEX. This is a deterministic conversion inventory, not a count of all bitmap tags in an Xbox map and not an all-gameplay-object closure.

Commands (from the repository root):

```sh
python3 tools/audit_mp_render_asset_bound.py \
  build/retail-maps/decompressed \
  --output build/m2-mp-render-assets/static-render-assets.json
```

The audit JSON stores every raw decompressed map SHA-256, each per-map `TEXS`/`OTEX`/`LMn` section SHA-256, count/byte subtotals, converter identity, and source pin. Two full conversions completed with byte-identical JSON (`static-render-assets-v2.json` and `static-render-assets-v3.json`, each 29,098 bytes). Both JSON files report the source directory `build/retail-maps/decompressed`, halo-ps2 pin `71183bb0a9adc586cd267b2780c82bbc12cfd95b`, HCU pin `6933490b2d16bb1c637295b6a0f3880ba23a7d56`, and audit-script SHA-256 `466210ce16d208803020c144750c5b0cfb4a81dd8ff0f694da5f103e716b751a`. The v2/v3 JSON SHA-256 is `fae6288e6335ab6f0afa41bb61074e49046aa823ff8d0cc740f9f815c6e1904f` (identical outputs). Per-source map hashes and output-section hashes are inside that JSON.

The full per-map report also records source-resolution decoded lightmap pixel estimates, converted luminance pixels, dense and used lightmap page counts, TEXS pixel/CLUT bytes, object model and texture counts, and untextured bindings. `TEXS` and `OTEX` section sizes include their headers and binding/texture tables; lightmap section sizes include dense tables and CLUT, while the separately shown “decoded lightmap pixels” counts only converted page pixels. Do not add the decoded source-resolution estimate on top of the section size: it is an intermediate input, not a retained output allocation.

## Interpretation for Step 8 and unresolved evidence

- This gives an actual converted-section bound for the baseline scenario-selected render assets of each stock multiplayer map. It is materially stronger than the single Blood Gulch viewer observation, and it identifies Blood Gulch as the largest baseline section sum under this exact conversion configuration.
- It does **not** establish that the whole render workload fits the 4 MiB reservation. The current section reader retains output sections in the arena passed by its caller, while this script measures offline pack-section sizes. Ownership routing, transition peaks, alignment, reader scratch, and live renderer/cache state still require implementation/runtime instrumentation.
- Match-time scenario object selection is not the maximum co-op/bot/multiplayer state. Dynamic bots, weapons/equipment, vehicles, effects, other model references, damage, first-person arms, HUD, and animation residency are not bounded by the `OTEX` rows. A bot/object asset closure must be enumerated separately and then measured at runtime.
- `LMn` conversion honors the converter's 512 KiB per-BSP pixel guard and configured extra shrink behavior ([`texconv.py`](../../submodules/halo-ps2/tools/halo2ps2/texconv.py#L63), [`texconv.py`](../../submodules/halo-ps2/tools/halo2ps2/texconv.py#L973)). The observed *sum of each map's selected LMAP sections* is only 16,288–113,440 bytes; this does not include temporary full-resolution decode buffers or demonstrate PS2 EE placement.
- The 14,880,288-byte all-map total is not a simultaneously resident demand and cannot be compared as a single-map allocation. Do not use it to justify taking 170,176 bytes from texture cache, and do not use the per-map max alone to accept such a transfer.
- Halo-64 is useful only as an architectural comparison for explicit asset/resource ownership and measured target-specific limits. Its N64 renderer, budgets, and cuts do not validate R5900/GS/EE sizes. This inventory is computed from this repo's pinned PS2 converter and Halo CE source-map inputs, not inferred from Halo-64.
- REA was not used: this task is an offline inventory using available raw retail map files and the repository's converter source; no opaque executable behavior or binary disagreement needed reverse engineering. It would become relevant if the runtime disagrees with these converter outputs or if an undocumented retail cache/lifetime behavior must be recovered from a shipped binary.

This closes only the reproducible offline static asset-size inventory subcheck. Step 8 remains open for physical arena ownership/high-water, map transition overlap, scenario and match-time object closure, bot/co-op runtime load, EE/PCSX2 rendering, and acceptance across all 13 maps.
