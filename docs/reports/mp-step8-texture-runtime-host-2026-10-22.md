# Step 8 candidate texture-owner runtime exercise (host)

## Result

I exercised the actual halo-ps2 HP2 section loader and TEXS/LMAP parsers against production-converter section data for each of the 13 stock MP maps. For each map, one 4,014,936-byte owner simultaneously retained decoded TEXS, every emitted LM section, and scenario-selected OTEX; the actual `world_load_section_with_scratch` path streamed and CRC-checked the HP2 sections using a distinct 524,288-byte scratch arena. All 13 fit. The largest normal retained/high-water use was Blood Gulch at 2,144,672 bytes; the largest deliberate transient CRC-failure retry high-water was 2,550,720 bytes. Both remain below the candidate owner ceiling.

The run also verified 64-byte section output alignment, texture/mip/CLUT and lightmap-page ranges, 13 expected CRC rejections with owner cursor rollback, retained-section validity after rollback, scratch rewind, and before/after canaries on both arenas. Scratch high-water was 98,304 of 524,288 bytes on every map. This is a host x86-64 run of the real C loader/parsers, not target ABI or PS2/EE placement evidence.

This extends—but does not replace—the prior candidate map/BSP topology report [mp-step8-tail-inclusive-candidate-2026-10-22.md](mp-step8-tail-inclusive-candidate-2026-10-22.md), SHA-256 `f8b8d25a8bc4c8b7accb95d73f09a7b886fca2eb996dcd370e5af4764e45a649`. Both remain candidate diagnostics; neither closes Step 8 nor changes production capacity/admission.

## Per-map runtime measurements

`raw sections` is the sum of the decoded TEXS + all LMn + selected OTEX section lengths, matching the static converter inventory. `retained/normal high` is actual `arena_t` usage after the loader's 64-byte aligned allocations. `CRC retry peak` includes an intentionally failed second TEXS load after the successful sections are retained; the loader rolls the owner cursor back, but high-water correctly records that temporary allocation.

| Map | TEXS | All LM sections | Scenario OTEX | Raw section sum | Retained / normal high | CRC retry peak | Alignment overhead |
|---|---:|---:|---:|---:|---:|---:|---:|
| Beaver Creek | 389,728 | 16,288 | 875,808 | 1,281,824 | 1,281,888 | 1,671,648 | 64 |
| Blood Gulch | 406,016 | 33,120 | 1,705,504 | 2,144,640 | 2,144,672 | 2,550,720 | 32 |
| Boarding Action | 285,024 | 113,440 | 647,328 | 1,045,792 | 1,045,856 | 1,330,912 | 64 |
| Carousel | 167,904 | 43,328 | 679,040 | 890,272 | 890,304 | 1,058,208 | 32 |
| Chill Out | 315,456 | 31,904 | 425,664 | 773,024 | 773,056 | 1,088,512 | 32 |
| Damnation | 228,960 | 44,992 | 816,832 | 1,090,784 | 1,090,816 | 1,319,776 | 32 |
| Hang 'Em High | 352,384 | 83,072 | 745,728 | 1,181,184 | 1,181,184 | 1,533,568 | 0 |
| Longest | 354,528 | 17,504 | 638,784 | 1,010,816 | 1,010,880 | 1,365,408 | 64 |
| Prisoner | 380,288 | 33,920 | 745,568 | 1,159,776 | 1,159,776 | 1,540,096 | 0 |
| Putput | 174,112 | 34,144 | 389,376 | 597,632 | 597,696 | 771,808 | 64 |
| Rat Race | 382,400 | 30,880 | 509,088 | 922,368 | 922,400 | 1,304,832 | 32 |
| Sidewinder | 475,584 | 61,536 | 1,301,536 | 1,838,656 | 1,838,688 | 2,314,304 | 32 |
| Wizard | 171,136 | 18,208 | 754,176 | 943,520 | 943,552 | 1,114,688 | 32 |

The run reinitializes the candidate owner per map; the 13 per-map figures must not be summed as simultaneous map residency. The `.hp2` transport-file sizes also are not the resident section totals: the test checks runtime decompression into the owner, rather than counting compressed bytes as resident memory.

## Implementation and source grounding

- `submodules/halo-ps2/engine/src/world/section.c:153-247` is the real loader under test. It allocates the decoded section at 64-byte alignment, allocates the 65,536-byte history plus 16 KiB input/output streaming workspace from the separate scratch arena, rewinds scratch, and rolls the owner back if streamed decode/CRC fails.
- `submodules/halo-ps2/engine/src/world/world.c:76-99,121-126` shows production callers parsing BSP TEXS/LMn and object OTEX. The fixture calls the same section-loader API and parser APIs directly so each section family can be charged to the candidate texture owner independently of BSP geometry and object MODL/SCEN/ANIM storage.
- `submodules/halo-ps2/engine/src/world/tex.c:28-71,121-167` validates the TEXS tables and each mip/CLUT extent, and LMAP page tables, extents, and lightmap pixels.
- `tools/test_halo_ps2_mp_texture_runtime.py:50-100` runs pinned `texconv.convert_map(..., lightmaps=True, lm_gain=1.5)`, `scenconv.collect`, `skyconv.read_sky`, and `modelconv.convert_map` with the resulting scenario model tags. The texture HP2 wrapper carries the exact converted TEXS and all emitted LM raw bytes; OTEX wrapper carries the exact production model-converter OTEX bytes. Only the enclosing wrapper is narrowed (the BSP payload is omitted); it is not a hand-reencoded texture section.
- `tests/mp_texture_runtime_main.c:118-204` runs every map, validates the buffers, captures normal and CRC-failure peaks, and checks retained state and canaries. The generated corruption changes only TEXS's HP2 CRC field; the output log records the expected `HP2_ERR_CRC` (status 8) for each map.

Reproduce conversion, compile, and run with:

```sh
python3 tools/test_halo_ps2_mp_texture_runtime.py
```

The successful run's retained artifacts are under `build/mp-texture-runtime/1792684440364070518/`. The generated binary was x86-64 Linux; the test is a byte-capacity/runtime-loader check, not ILP32 ABI evidence.

## Provenance

- Parent commit: `70e2ed0cf2145a45d23aa07414a3a88c05155d4c`
- halo-ce-universal: `6933490b2d16bb1c637295b6a0f3880ba23a7d56`
- halo-ps2: `71183bb0a9adc586cd267b2780c82bbc12cfd95b`
- Source map inputs: the exact 13 SHA-256 pins from `tests/test_hcu_mp_capacity.py`; the generated run manifest records each map's source hash and every converted section/hash.
- Test-run manifest: `build/mp-texture-runtime/1792684440364070518/manifest.json`, SHA-256 `55d286a729b5c6073e35dc7cade2ac5967ecc0bdb8514ee209c13406fec17388`.
- C fixture SHA-256: `e97cbf1746436b6363359f6b533ff35044406d63ac8fd995377a64390bef1861`.
- Python runner SHA-256: `039e31d0e705fe89112a83e68c096d1075f67204838b2695898227d3a720ebb6`.
- Host executable SHA-256: `f3adf5bc07f730d2bf926aebecd14715bb5f78de00a3c5080dae847ce7be16dc`.
- Link map SHA-256: `209f159cab8b3a51953d09a4fa96cdbc5c84a0f0311e9b9c48e8048ca0a502d3`.
- Runtime log SHA-256: `182179603dea4ec4f3b4d08bfa4049da4b96dc2b527f59d44a2c19c84ced1456`.

## What this does not prove

The fixture does not call `world_load()`/`world_load_objects()` as a whole: those functions mix BSP, MODL, SCEN, ANIM, and other persistent sections into the caller-provided owner. Here the actual `world_load_section_with_scratch` API retains only the texture section subset in the candidate texture owner, and calls the actual `tex_open`/`lm_open` readers. The selected model set and OTEX section are production-converter-derived, but the object HP2 wrapper is OTEX-only; this is not evidence for simultaneous object-pack plus texture residency or `world_load_objects` map-owner usage.

It also does not upload pixels/CLUTs to GS, exercise cache eviction or per-frame visibility, measure render-time overlap with streaming/staging/DMA buffers, include extra match-time weapon/equipment/effect/HUD assets, use the dynamic-simulation pool, test PS2 DMA alignment against hardware, establish physical EE placement, or measure R5900 timing. The 4,014,936-byte profile remains an explicitly diagnostic candidate and texture-runtime safety still requires an EE/PCSX2 render/streaming workload.
