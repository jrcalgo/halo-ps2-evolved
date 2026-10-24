# M2 Step 7 — Multiplayer detail-object consumer evidence

## Result

The CE structure-BSP detail-object path has now been exercised in a bounded source-derived host fixture. The 13 stock multiplayer BSPs all contain one `structure_detail_object_data` root record, but each root has `valid == 0` and all four child blocks (`cells`, `detail_objects`, `counts`, `z_reference_vectors`) are empty. The actual CE consumer therefore issues no detail-object rasterizer calls for any stock MP map. This identifies the currently shipped MP behavior precisely; it is not a finding that these BSP fields are disposable.

The same fixture injects the verbatim HCU camera-cell selector and its binary-search/count helpers and reaches a synthetic valid-data case. That case checks the 3×3 horizontal neighborhood, ±1 vertical cell selection, per-layer count/object offsets, scenario palette truncation, same-cell selection caching, an empty-but-valid data block, and the `local_player_count() == 1` gate. The test covers CPU-side view selection only; it does not draw the detail sprites, implement the PS2 rasterizer path, or demonstrate target-sized/EE execution.

## Source and parity comparison

- HCU `structure_render_detail_objects` is called in the world render flow at [`render.c:410`](../../submodules/halo-ce-universal/source/render/render.c#L410). The consumer is restricted to one local player and derives the camera cell from camera position at [`structure_detail_objects.c:420-437`](../../submodules/halo-ce-universal/source/structures/structure_detail_objects.c#L420). For valid data it rebuilds when the camera cell changes or the dirty bit is set; the queried x/y coordinates cover a 3×3 neighborhood and z is limited to ±1 at [`structure_detail_objects.c:441-499`](../../submodules/halo-ce-universal/source/structures/structure_detail_objects.c#L441). It caps cells per layer, validates count/object extents, uses the default z-reference when needed, and omits layers absent from the scenario palette at [`structure_detail_objects.c:501-543`](../../submodules/halo-ce-universal/source/structures/structure_detail_objects.c#L501) and [`structure_detail_objects.c:556-587`](../../submodules/halo-ce-universal/source/structures/structure_detail_objects.c#L556).
- Halo-64's comparison implementation follows the same one-player camera-cell and layer-selection shape at [`structure_detail_objects.c:376-399`](../../submodules/halo-64/source/structures/structure_detail_objects.c#L376), then searches and builds cells at [`structure_detail_objects.c:410-479`](../../submodules/halo-64/source/structures/structure_detail_objects.c#L410). Its shown implementation directly dereferences the detail root, uses `cells.count - 1`, trusts count indices and counts, and increments layer cell arrays without the HCU guards. This is a useful comparison, not a reason to remove HCU bounds checks.
- The PS2 reference renderer specifies model, BSP, sprite, and decal VU1 programs; its sprite program is documented for particles, lens flares, and contrails ([`03-engine-architecture.md:126-139`](../../submodules/halo-ps2/docs/03-engine-architecture.md#L126)). That documentation does not establish an equivalent to CE detail-object collection rendering. No GS/VU output is claimed by this report.

## Fixture and evidence

`tests/test_hcu_mp_detail_object_consumer.py` extracts the HCU comparator, lower/upper-bound, player-data, count-safety, and `structure_render_detail_objects` function bodies directly from the pinned source, compiles them into `tests/hcu_mp_detail_object_consumer_main.c`, then runs the CPU-only checks. For the retail inventory it decodes original decompressed Xbox map bytes using the Halo PS2 map/tag index tools, follows the retail structure-BSP pointer at the source-defined `detail_object_data` field, validates the root/child extents, and supplies the observed validity state to the verbatim CE consumer. Each map source SHA-256 is pinned in the test.

Reproduction:

```sh
python3 -m pytest -q tests/test_hcu_mp_detail_object_consumer.py -x
```

Result on 2026-10-22: `1 passed, 13 subtests passed`. The synthetic fixture reported successful camera-cell selection, layer/palette filtering, cache reuse, and the split-screen gate. Each of the 13 retail map subtests reported `detail_valid=0`, zero child blocks, and `draw_calls=0`.

Source identities used:

- Parent working tree: captured from current working tree; this is not a committed change.
- `halo-ce-universal`: `6933490b2d16bb1c637295b6a0f3880ba23a7d56`; `source/structures/structure_detail_objects.c` SHA-256 `471e7a77c5f92bcd8587ffccd9f3cffe7cf7cabec94189f02e0a0231b2314a5a`.
- `halo-64`: `17541f4444baabb47d1a0deb917f26ccb7b6bc5c`; comparison file SHA-256 `5dff12997c522bdcd3c62509fede2e2e29ed170a097d45eb50f258486e045126`.
- `halo-ps2`: `71183bb0a9adc586cd267b2780c82bbc12cfd95b`; architecture comparison is the checked-in renderer documentation cited above.
- Test files: `tests/test_hcu_mp_detail_object_consumer.py` SHA-256 `1beab7cc411b30ba14c0e2801967c335504f306288b28a7f8b1241719e171559`; `tests/hcu_mp_detail_object_consumer_main.c` SHA-256 `54ded964943614556c9f8704f5340c4f22f77cb635c0f9ba99f8039aaa143a8a`.

## Scope and limits

The retail-map results mean detail-object camera-cell selection has no populated stock MP input to exercise: it is dormant for these 13 retail BSPs, not proven unnecessary for arbitrary/custom maps. Keep the BSP root and child blocks through conversion unless a separate compatibility decision covers modded content. The synthetic fixture is a controlled branch test, not a retail oracle. It does not qualify Xbox detail-object sprite/bitmap/material behavior, the HCU platform rasterizer implementation, GS memory or DMA, 2–4-player rendering beyond confirming CE's early return, target RAM high-water, frame cost, or PCSX2/EE behavior. Accordingly this closes only the source inventory and bounded CPU selection subcheck; it does not close Step 7's broader BSP-consumer or Step 8 target acceptance gates.
