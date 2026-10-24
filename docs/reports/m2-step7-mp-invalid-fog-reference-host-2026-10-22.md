# Step 7 — invalid fog-reference bounds on stock multiplayer BSPs

## Result

Added a test-only probe for the two bounds-checked malformed-reference paths in
CE's real `scenario_get_fog_region_index()` implementation. The probe runs only
on maps with a source-derived valid fog-plane chain (Beaver Creek, Chill Out,
and Damnation). For each map and each of the two all-map lifecycle cycles, it
temporarily changes the selected relocated cluster's `fog_reference` to:

1. a high-bit plane reference whose index equals `fog_planes.count`; and
2. a legacy region reference equal to `fog_regions.count`.

CE returns `NONE` for both. The test restores the original reference and then
asserts the valid source-derived fog lookup still returns its original region,
the cluster reference was restored, the published BSP and BSP index are
unchanged, and collision-user depth is unchanged. Native ILP32 execution
passed **6 invalid-reference assertions** (three maps × two lifecycle cycles),
alongside the fixture's **26/26** all-map lifecycle rows and its final
13-map collision/PVS/reload success marker.

This qualifies malformed plane/region reference handling at a package-backed
host seam. It does not prove target/PCSX2 memory safety, all malformed schema
inputs, bot fog perception, fog rendering, or map capacity. No production code,
source map, or HP2 package was edited. The injection and validation are in the
unique runner [`test_hcu_mp_fog_invalid_refs.py`](../../tools/test_hcu_mp_fog_invalid_refs.py).

## Source basis

The CE implementation decodes a high-bit plane index and rejects it when it is
outside `fog_planes.count` before accessing the block, then validates the
resulting region against `fog_regions.count`:
[`scenario.c:649-688`](../../submodules/halo-ce-universal/source/scenario/scenario.c#L649).
Existing valid-plane and `NONE` cases in the all-map fixture are in
[`hcu_scenario_bsp_switch_main.c:1297-1445`](../../tests/hcu_scenario_bsp_switch_main.c#L1297).
This added test targets the adjacent invalid-index branches without changing
their semantics.

## Reproduction

The fixture generator/build command is:

```sh
python3 tools/test_hcu_mp_fog_invalid_refs.py
```

In the restricted sandbox, the Python unittest builds the exact test binary
but skips its native ILP32 run because execution is denied with SIGSYS. Run the
retained binary outside that sandbox:

```sh
build/m2-mp-weather-wind-13/mp-weather-wind-location \
  build/m2-mp-weather-wind-13/assets/ \
  > build/m2-mp-invalid-fog-1792687843283891487/native-direct.log 2>&1
```

The command exited 0. The log has six
`mp-fog-invalid-reference ... status=passed` rows, 26 `mp-host-map` rows, and
ends with `mp-host-collision 13-map CE hit/PVS/reload matrix passed; target
capacity not tested`.

## Bound identities

Source pins: parent `70e2ed0cf2145a45d23aa07414a3a88c05155d4c`,
halo-ce-universal `6933490b2d16bb1c637295b6a0f3880ba23a7d56`, and halo-ps2
`71183bb0a9adc586cd267b2780c82bbc12cfd95b`.

| Artifact/input | SHA-256 |
|---|---|
| Runner `tools/test_hcu_mp_fog_invalid_refs.py` | `4434f7bd6642b37bf7db70da572974f4acdcea3c20b2d451c2c2ae0a499df47b` |
| Generated test `build/m2-mp-invalid-fog-1792687843283891487/test_hcu_mp_capacity_fog_invalid.py` | `d6b81be5202a0d6c8461cb36fc1f9bda10f338e5c40a539b66db19f68e067859` |
| Generated CE translation unit `.../generated_hcu_scenario_bsp_switch_main.c` | `1dec96b1a3d14cd3c9804c6c6c5ccfdc610a7518f0239b62ae0d5633867eb3c5` |
| Host ILP32 executable `build/m2-mp-weather-wind-13/mp-weather-wind-location` | `40397a1798ca95cd7396c77cbfdc989ddc36416ecae01d9435003a14cbde3667` |
| Link map `build/m2-mp-weather-wind-13/mp-weather-wind-location.map` | `f77edd160713fd1475fae5ccefe8736ecbabb172af1a426e22ac620dc31a5ddc` |
| Native run log `.../native-direct.log` | `64f4eb93d085f0e1a62ad158b53f9262d8f69f15b67356bbde382634d1040703` |
| Beaver Creek source map / HP2 | `eaf90b2abc4fd295469eb2d640063618b0d14396f28e7d7f1758e834c061c50a` / `4f95672c4233a63d30e94395010324076cb1454813facb54e48c065d7c776dfc` |
| Chill Out source map / HP2 | `52bc3e23b9142cf479770d1d601fe08b13d78fe3eb05eca72d313b7ebbd21ffb` / `727abc7401a530892f1136f082a6254544915e0d85f2a068f63d9530189b1bf0` |
| Damnation source map / HP2 | `87bd92c1821ff20bed03c559d7be5ac43baeb44aa68342ffdbb5a8cd978f711c` / `ca41445cc9560035910fbc8c2fc7130175b707b1df2e8e51734d208c4ee2076d` |

The fixture uses diagnostic host-sized memory. This is a narrow Step 7
consumer/bounds subcheck; it neither closes Step 7 nor changes Step 8's
target-capacity gates.
