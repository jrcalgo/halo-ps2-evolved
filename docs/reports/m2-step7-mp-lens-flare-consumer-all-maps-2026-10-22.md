# Step 7 — Multiplayer BSP lens-flare marker consumer audit

## Result

The CE cluster lens-flare selector was compiled from the pinned source and exercised against the raw BSP images for all 13 stock Halo CE multiplayer maps. The independent host oracle agrees with CE's emitted marker-index sequence for every cluster. Only Boarding Action, Damnation, and Putput contain a non-empty lens-flare marker palette in these BSP images; they account for 1,121 valid marker submissions (207 + 22 + 892). The other ten maps have empty marker arrays and correctly submit none.

This closes a source-backed selector/data-range subcheck for the lens-flare marker consumer. It does not establish that flares are visibly rendered, that definitions resolve to the intended bitmap/effect, that occlusion queries work, or that the production PS2 renderer submits the data. It is not Step 7 or Step 8 closure evidence by itself.

## Scope and source ownership

The exercised CE function is `rasterizer_lens_flare_submit_for_cluster()` in `submodules/halo-ce-universal/source/rasterizer/rasterizer_lights.c:771-840`. It obtains the selected cluster, bounds its marker scan to the BSP marker count and the signed-short index capacity (`:779-798`), validates each marker's lens-flare palette index (`:799-806`), decodes the marker direction into the submit parameters, and forwards the selected record (`:808-835`). The record layout is defined in the same file: a 12-byte position, three signed direction bytes, and one palette-index byte (`:288-295`); compile-time assertions in that source pin the cluster and marker ABI sizes.

The port owns the visible output path. Halo-PS2's architecture document says its VU1 `sprite` program expands camera-facing quads for particles, lens flares, and contrails ([`03-engine-architecture.md:130-137`](../../submodules/halo-ps2/docs/03-engine-architecture.md#L130)). Therefore CE marker selection is upstream state/data preparation; this host test does not exercise the PS2 sprite program, GS state, occlusion readback, or frame submission.

Halo-64 is useful only as a contrast: its generated platform stubs make `rasterizer_widget_draw_sprite3d()` a no-op ([`n64_stubs_generated.c:224`](../../submodules/halo-64/port/n64/game/n64_stubs_generated.c#L224)). That demonstrates a deliberately reduced N64 output path, not a suitable PS2 implementation or evidence that this port can drop the renderer-facing consumer.

## Fixture and method

`tests/test_hcu_mp_lens_flare_all_maps.py` reuses the existing source extractor, raw BSP decoder, and ABI shim in `tests/test_hcu_mp_lens_flare_consumer.py`, while supplying the full 13-map source-digest allowlist. The test extracts the function body from the current HCU source, substitutes only the debug-option global with a host stub, then compiles it with the retail BSP blocks and CE-sized structure shims. A recording submit function captures the indices CE forwards. The Python oracle independently reads each cluster's first-marker/count words at `0x40/0x42`, walks the decoded marker block, and filters marker palette references against the BSP lens-flare palette count. It compares the full ordered index sequence, not only totals.

A synthetic subcase exercises boundary behavior that the valid retail maps do not provide: a marker whose palette index is invalid is skipped; a later valid marker is still submitted; the scan stops at the marker-block boundary even when the cluster declares a longer range; and disabled/screenshot modes submit nothing. This is selector-level behavior with the real CE function body but test-owned records and submit/definition stubs.

## Retail BSP inventory

All files are decompressed retail `.map` artifacts at `build/retail-maps/decompressed/<name>.map`. Their SHA-256 digests are checked before parsing and are embedded in the test.

| Map | BSP clusters | Lens-flare palette entries | Marker records | Valid CE marker submissions | Raw map SHA-256 |
|---|---:|---:|---:|---:|---|
| Beaver Creek | 29 | 0 | 0 | 0 | `eaf90b2abc4fd295469eb2d640063618b0d14396f28e7d7f1758e834c061c50a` |
| Blood Gulch | 30 | 0 | 0 | 0 | `9eb0374cbe4571af640ae0d2e0ebf6119543cdbbece44d49543b4748c4cf0dc1` |
| Boarding Action | 41 | 1 | 207 | 207 | `34ddf961973b6aaf05f40f26bd9ad536ca97f8af503995611535ccf6ce911522` |
| Carousel | 36 | 0 | 0 | 0 | `3e4be29a7952af0b3f19a7540e454fd0deece6d6078c256cde70a734beba55e1` |
| Chill Out | 10 | 0 | 0 | 0 | `52bc3e23b9142cf479770d1d601fe08b13d78fe3eb05eca72d313b7ebbd21ffb` |
| Damnation | 12 | 1 | 22 | 22 | `87bd92c1821ff20bed03c559d7be5ac43baeb44aa68342ffdbb5a8cd978f711c` |
| Hang 'Em High | 1 | 0 | 0 | 0 | `e3e4b25ed36178926f0df11f3cd82b07e2071f6aa0efaa77f0cfde8f8480981f` |
| Longest | 1 | 0 | 0 | 0 | `e045b0843f4a167a516f050161a651610fafc94ccc8c5f2c5d5725d108d5d1b9` |
| Prisoner | 1 | 0 | 0 | 0 | `85ff2fdc117b7640bda85a490b30c662f2626bd6d0685e41832935422891c307` |
| Putput | 9 | 1 | 892 | 892 | `efbe723188f34053d318105f20c7046f263171fbb937fbad45e3d00f8437f243` |
| Rat Race | 16 | 0 | 0 | 0 | `577886f949f2648f04cf99e354fb04ca08d7b9199636c2f9fe1a161ccdaa4b1e` |
| Sidewinder | 35 | 0 | 0 | 0 | `995561a68c8c5b142f13f1967730ce8c08d4f0db9574db8e987d915f2b118dcc` |
| Wizard | 18 | 0 | 0 | 0 | `978539ff70085998485870a15d4ec81d3811442ac48f9265db668a396f6ff1eb` |

## Verification and provenance

Command:

```sh
python3 -m pytest -q tests/test_hcu_mp_lens_flare_all_maps.py tests/test_hcu_mp_lens_flare_consumer.py
```

Result: **3 passed in 1.97s**. `git diff --check -- tests/test_hcu_mp_lens_flare_all_maps.py` passed. The all-map test alone had also passed before the synthetic subcase was added.

Source pins and hashes at verification:

- Parent repository `HEAD`: `70e2ed0cf2145a45d23aa07414a3a88c05155d4c`.
- `halo-ce-universal`: `6933490b2d16bb1c637295b6a0f3880ba23a7d56`.
- `halo-ps2`: `71183bb0a9adc586cd267b2780c82bbc12cfd95b`.
- CE source `rasterizer_lights.c`: SHA-256 `2a4db1e1f5e125436fddc05a46b1eb68102e2be978d8294919f85275d742b233`.
- Baseline focused fixture `test_hcu_mp_lens_flare_consumer.py`: SHA-256 `005ea3db352e56fc06d5fa0c0d07e3620a720534f470163da78d6b447aef3cdc`.
- New all-map fixture `test_hcu_mp_lens_flare_all_maps.py`: SHA-256 `249fc32c592e94eb7a12b8ed8fdcb935a4358cd99ffea9f91d0e21c5cd325ea9`.

## Remaining lens-flare evidence gaps

- The input is a raw-Xbox-format BSP embedded in each decompressed map, not the post-CTAG relocation output consumed by the PS2 game. This verifies CE consumer indexing against source data, not relocated-pointer correctness.
- The host shim stubs tag-definition lookup, submit, vector math/compression, window state, and renderer state. It observes marker selection/forwarding, not actual definition contents or visual behavior.
- The test covers only the one active BSP selected by the retail map extraction helper. It is not evidence about every sub-BSP in maps that have multiple BSP tags.
- No PCSX2 or hardware screenshot, GS/VU packet, sprite texture residency, occlusion-query result, or frame-time measurement was captured.
- The result is narrow Step 7 coverage; it neither makes the retail map load/render nor closes Step 7/8 acceptance.
