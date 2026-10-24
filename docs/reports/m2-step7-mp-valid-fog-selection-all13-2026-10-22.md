# Step 7 — Raw-oracle fog-region selection across stock MP BSPs

Status: **all source-present cluster fog-reference cases pass on the native
host ILP32 fixture**. This closes only the position-independent BSP fog-region
selector subcheck; it is not PS2-target evidence and does not close Step 7.

## Fixture and result

The new runner `tools/test_hcu_mp_fog_selection_all.py` derives an independent
oracle from every cluster record in each of the 13 pinned raw Xbox multiplayer
maps. It classifies each signed `fog_reference` from raw bytes and derives the
expected `scenario_get_fog_region_index(location, NULL)` result from the
bounded cluster, fog-plane, and fog-region blocks. It generates a test-only
golden header and C probe, then extends the existing package-backed
all-multiplayer-map lifecycle fixture. The linked executable contains HCU's
actual `scenario_get_fog_region_index()`; the generated test requires that
symbol in its link map.

For each raw-derived row, the C probe checks that the relocated cluster still
has the raw reference, calls CE's resolver, compares its returned index to the
raw oracle, and immediately checks that structure-BSP, collision-BSP, and
BSP3D publication pointers, both BSP indices, collision-user stack depth, and
all collision-user stack slots are unchanged. The matrix executes two
load/query cycles per map.

Native command result: **1 unittest passed in 86.377 s**. The test compared
**478 query rows** with the independent expected rows (239 raw clusters × 2
cycles) across all 13 source maps. The source census contains **188 `NONE`
references** and **51 valid high-bit plane→region references**; it contains no
valid direct-region references and no naturally out-of-range references.
Valid plane rows occur in Beaver Creek (29 clusters), Chill Out (10), and
Damnation (12). The other ten maps' every cluster is `NONE`. Every map's raw
source and converted HP2 package hashes are pinned in the retained manifest.

| Map | CE clusters queried per cycle | `NONE` | Valid plane chain | Direct / out-of-range |
| --- | ---: | ---: | ---: | ---: |
| Longest | 1 | 1 | 0 | 0 / 0 |
| Blood Gulch | 30 | 30 | 0 | 0 / 0 |
| Beaver Creek | 29 | 0 | 29 | 0 / 0 |
| Prisoner | 1 | 1 | 0 | 0 / 0 |
| Boarding Action | 41 | 41 | 0 | 0 / 0 |
| Carousel | 36 | 36 | 0 | 0 / 0 |
| Chill Out | 10 | 0 | 10 | 0 / 0 |
| Damnation | 12 | 0 | 12 | 0 / 0 |
| Hang ’Em High | 1 | 1 | 0 | 0 / 0 |
| Putput | 9 | 9 | 0 | 0 / 0 |
| Rat Race | 16 | 16 | 0 | 0 / 0 |
| Sidewinder | 35 | 35 | 0 | 0 / 0 |
| Wizard | 18 | 18 | 0 | 0 / 0 |

The test also runs the existing lifecycle, collision/PVS, wind, weather
selection, sound-environment, map-retry, and capacity-diagnostic assertions
from the base fixture. Their pass is not reinterpreted as target capacity or
rendering evidence.

## Source interpretation and limits

- HCU's real selector is in
  [`scenario.c:632-692`](../../submodules/halo-ce-universal/source/scenario/scenario.c#L632).
  For a high-bit reference it resolves the plane's region; without a position,
  it returns that region subject to the final region-count check. For `NONE`,
  it returns `NONE`. The raw oracle deliberately expects no region for source
  references that are naturally malformed, should such a pinned source ever
  contain them; none occur in this 13-map set.
- The function delegates region fog-tag selection to
  [`scenario_fog_region_get_fog_index()` at `scenario.c:1073-1096`](../../submodules/halo-ce-universal/source/scenario/scenario.c#L1073),
  whose bounds handling is not confused with the region index returned by the
  selector.
- **Fog attenuation is not tested here.** HCU's
  [`scenario_fog_at_point()` at `scenario.c:803-810`](../../submodules/halo-ce-universal/source/scenario/scenario.c#L803)
  is an explicit constant-zero stub, not a function with an available
  implementation oracle in this source. Halo-64's corresponding
  [`scenario_fog_at_point()` at `scenario.c:780-787`](../../submodules/halo-64/source/scenario/scenario.c#L780)
  is likewise constant-zero. This fixture therefore tests selector behavior
  only; it makes no claim about attenuation, visible fog, or parity of a
  missing implementation.
- The selector is called with `position == NULL`; fog-plane side tests,
  water-boundary behavior, fog-palette rendering, and weather-particle
  behavior remain separate checks. The 13 map queries execute in diagnostic
  host-sized arenas and do not prove EE memory or timing.

## Reproduction and pinned evidence

The ordinary runner compiles and generates the unittest. If the sandbox
rejects native ILP32 with SIGSYS, run the generated unittest in the approved
native execution context. The successful command for this evidence set was:

```sh
PYTHONPATH=build/m2-mp-fog-selection-1792693186821210956:.:tests:tools:submodules/halo-ps2/tools \
HCU_MP_CAPACITY_RETENTION_DIR=build/mp-fog-selection-1792693186821610382 \
python3 -m unittest -v \
  test_hcu_mp_fog_selection_generated.MultiplayerHostCollisionMatrix.test_host_sized_13_map_lifecycle_and_collision
```

Pinned commits (parent / HCU / halo-ps2 / Halo-64):
`70e2ed0cf2145a45d23aa07414a3a88c05155d4c` /
`6933490b2d16bb1c637295b6a0f3880ba23a7d56` /
`71183bb0a9adc586cd267b2780c82bbc12cfd95b` /
`17541f4444baabb47d1a0deb917f26ccb7b6bc5c`.

The manifest includes the exact 13 raw-map and 13 HP2-package hashes and the
compiled input-source hashes. Key SHA-256 values:

| Artifact | SHA-256 |
| --- | --- |
| Runner `tools/test_hcu_mp_fog_selection_all.py` | `44306eceb585a4f01212c2deac59939973f6f0c72ea4d98cdfa37e66c7514148` |
| Generated unittest | `1ea51d79b0a251e5e15b7a0da95b015f98d20d64259fb7a48becf74eb34a1e2b` |
| Generated C test | `156a6b31b7f7cceed9f1b8544bfaa13d9ec0c131078075e5f863aea6ac9518f4` |
| Generated raw-derived golden header | `3632f5956b122a189b0a517240fc32008c678a4cc03bf0d44d95198104caf472` |
| Raw fog-selection inventory | `640c048333b43a7ffba088f56edcad5ccb953d0a88da9a80864fdabe302860b5` |
| HCU `scenario.c` | `22aef8353c6f4a1067d0e51e78565783d5f7c911e3b4d73f40ad49269a2546c0` |
| Halo-64 `scenario.c` | `0368b3bb31f8008f1ff2120f58c3d0c91e4c003a1009974d3f1cbd67810e1684` |
| Host ILP32 executable | `bef640bd7c6bd8b89f69c3378adef6d9e547a581c1e4a18a75cd4bde9041f3ff` |
| Link map | `c18b0e1e7e59a57848f4cb10aac4043e594bdc08b44d5703968f246eaab11b2d` |
| Native unittest output | `df873cc743fa8befae470ec6a96b87b2c156de5bf2457aebdd5a7c130df15b99` |
| Source/pin/map/package manifest | `424cd09baa105cb60d70b6c4d452022a37f6224d6bda5ed761e432037b0c0771` |

No production code or the shared plan was edited. This is a test/report
addition only; other Step 7 BSP consumer, collision, and failure-boundary
gates and Step 8 target-capacity gates remain open.
