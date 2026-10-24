# Step 7 runtime decal consumer fixture

**Result: one stock multiplayer BSP now drives the actual CE runtime decal update and BSP disconnect/reconnect bodies in an isolated host fixture. Step 7 remains open.** The fixture exercises Blood Gulch PVS entry, exit, stable visibility, BSP disconnect cleanup, and reconnect creation. It checks all eight source decal records' palette selector, position, and orientation at the controlled decal API boundary.

## Executed behavior

`tests/test_hcu_runtime_decals_consumer.py` parses the decompressed retail Xbox map with the existing map/tag index readers, locates its sole BSP, and extracts its runtime decal records and cluster ownership ranges. It also reads the four-entry Blood Gulch scenario decal palette and resolves each referenced `deca` datum against that map's tag index. It then compiles the bodies of `structure_decals_update`, `structure_decals_disconnect_from_structure_bsp`, and `structure_decals_reconnect_to_structure_bsp` directly from the CE source into a temporary C executable. The fixture supplies bounded tag blocks and spies only for `decal_definition_get`, `decal_new`, `decals_delete_permanent_from_cluster`, and the malformed-data warning.

The raw Blood Gulch BSP has 30 clusters and eight runtime decals. Clusters 6 and 19 own records 0–3 and 4–7. With both clusters entering the PVS, CE creates eight decals. Leaving cluster 6 deletes that cluster once; a stable PVS causes no additional calls. BSP disconnect deletes both decal-bearing clusters, and reconnect recreates the still-visible cluster 19's four decals. For each created record, the fixture compares the source palette selector and raw position against the captured `decal_new` arguments and checks the produced normal against an independent trigonometric calculation using the source yaw/pitch bytes and CE angle scales.

The actual scenario palette resolves selectors 0–3 to CE tag indices 1370, 1372, 1374, and 1376, respectively. These tags are `levels\\b30\\decals-environment\\decal fore symb blue`, `...blue b`, `...red b`, and `...red`. The eight BSP records select indices 3 and 0, and CE forwards the corresponding map-derived indices 1376 and 1370 to `decal_new`. Creation, drawing, and rendering are downstream spies, not effect or rasterizer execution.

The broader raw stock MP inventory confirms runtime decal coverage in the available 13-map set: Beaver Creek 8, Blood Gulch 8, Boarding Action 55, Hang 'Em High 2, Longest 2, Putput 7, and Sidewinder 24; Carousel, Chillout, Damnation, Prisoner, Rat Race, and Wizard contain zero. Each nonempty map's raw cluster ranges sum exactly to the BSP runtime decal count. Only Blood Gulch is executed through CE in this fixture.

## Source references and artifacts

- CE PVS transition predicates and create/delete branches: [`structure_runtime_decals.c`](../../submodules/halo-ce-universal/source/structures/structure_runtime_decals.c#L141), especially lines 153–178.
- CE palette lookup, malformed palette handling, angle conversion, and `decal_new`: same source, lines 185–230.
- CE BSP disconnect cleanup: same source, lines 94–123.
- Raw stock fixture parsing, layout bounds, ownership assertions, actual scenario palette datum resolution, and source-map hash pin: [`test_hcu_runtime_decals_consumer.py`](../../tests/test_hcu_runtime_decals_consumer.py#L47).
- Palette data binding and controlled downstream spies: same fixture, lines 125–176.
- Transition/lifecycle and field assertions: same fixture, lines 171–220.

Exact command:

```sh
python3 tests/test_hcu_runtime_decals_consumer.py -v
```

Observed result:

```text
Ran 1 test ... OK
fixture map=bloodgulch map_sha256=9eb0374cbe4571af640ae0d2e0ebf6119543cdbbece44d49543b4748c4cf0dc1 bsp=levels\test\bloodgulch\bloodgulch bsp_sha256=8b3fa60e1f01fcec21c97c1916e7ca3ac8ed51a24f00eef18e4c8361d48e18bf
actual-ce-runtime-decals source=bloodgulch created=12 deleted_clusters=3 status=passed
```

SHA-256 pins:

| Artifact | SHA-256 |
|---|---|
| Decompressed Blood Gulch source map | `9eb0374cbe4571af640ae0d2e0ebf6119543cdbbece44d49543b4748c4cf0dc1` |
| Located raw Blood Gulch BSP image | `8b3fa60e1f01fcec21c97c1916e7ca3ac8ed51a24f00eef18e4c8361d48e18bf` |
| CE runtime decal source unit | `b8414f1c1d1305fcc23beafd6e74486485ce79078cc61868dfba35bde4023f58` |
| Isolated fixture runner | `44f12dcaa9a9983790cf6a71ad964d12dee0877b20a2bae8fda6706b9a829fea` |

This is host evidence for CE consumer semantics with raw retail BSP records and the map-derived scenario palette indices. It is not guest/EE execution, does not run decal/effect/render services, and covers one of the seven nonempty stock MP maps. Do not mark Step 7 complete from this fixture.
