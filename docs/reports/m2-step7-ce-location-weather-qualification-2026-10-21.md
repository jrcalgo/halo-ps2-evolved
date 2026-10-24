# M2 Step 7 — CE location/weather consumer qualification

## Result

The package-backed native ILP32 fixture now calls CE's real
`scenario_location_underwater()` after each published retail BSP load. The
source oracle chooses the first cluster whose raw Xbox `fog_reference` is
`NONE`, then independently checks CE's return value and weather-palette
selection against the original BSP bytes and the BSP's raw weather-palette
count. The test passed for the hash-verified `a30` and `a50` packages:

```text
1 passed, 1 deselected, 2 package subtests passed in 131.26s
```

The query is repeated during rollback/retry publications. The test requires the
repeated observations for a BSP to agree and requires every BSP index in each
package to be covered.

## Source contract and oracle

CE declares the API in
[`scenario.h:131-133`](../../submodules/halo-ce-universal/source/scenario/scenario.h#L131)
and implements it in
[`scenario.c:694-741`](../../submodules/halo-ce-universal/source/scenario/scenario.c#L694).
For an unfogged cluster, CE's
[`scenario_get_fog_region_index()`](../../submodules/halo-ce-universal/source/scenario/scenario.c#L632)
returns `NONE`; the underwater path therefore skips fog-region/tag lookups,
returns false, and takes `weather_palette_index` from the cluster, normalizing
it to `NONE` if it is outside the active BSP weather-palette count.

The raw-byte oracle is in
[`test_hcu_scenario_bsp_switch.py`](../../tests/test_hcu_scenario_bsp_switch.py).
It follows the source map's scenario/BSP records and selected BSP extent,
checks the complete cluster and weather-palette block bounds, reads
`fog_reference` at cluster `+0x02` and weather index at `+0x08`, and chooses
only an actual source cluster with `fog_reference == -1`. The C fixture ties
the serialized assumptions to CE's declarations with compile-time checks for
`structure_cluster` size `0x68`, fog offset `+0x02`, weather offset `+0x08`,
`structure_bsp` size `648`, and weather-palette block offset `436` in
[`hcu_scenario_bsp_switch_main.c:70-86`](../../tests/hcu_scenario_bsp_switch_main.c#L70).
It calls the real API on the already-published BSP, checks false return and
unchanged BSP pointer/index and collision-user depth, and emits the selected
cluster/result. The fixture does not synthesize map records or fog tags.

Raw-source expected selections (cluster index, raw weather index, CE-normalized
expected weather index):

| Map BSP | Expected selection |
|---|---:|
| `a30_a` | `(9, -1, -1)` |
| `a30_b` | `(0, -1, -1)` |
| `a50_exterior` | `(0, 0, 0)` |
| `a50_muster` | `(0, -1, -1)` |
| `a50_hangar` | `(0, -1, -1)` |
| `a50_control` | `(0, -1, -1)` |

The `a30` / `a50` `-1` weather values exercise CE's invalid/missing-palette
normalization; `a50_exterior` exercises a valid palette index. All selected
clusters have raw `fog_reference == NONE`, so this is not evidence for fog
plane/region resolution or underwater-water behavior.

## Reproducibility identities

- Parent / HCU / halo-ps2 / Halo-64 pins: `70e2ed0cf2145a45d23aa07414a3a88c05155d4c` /
  `6933490b2d16bb1c637295b6a0f3880ba23a7d56` /
  `71183bb0a9adc586cd267b2780c82bbc12cfd95b` /
  `17541f4444baabb47d1a0deb917f26ccb7b6bc5c`.
- CE scenario implementation SHA-256:
  `22aef8353c6f4a1067d0e51e78565783d5f7c911e3b4d73f40ad49269a2546c0`.
- CE BSP definition SHA-256:
  `dde75cddffc975c95395f525b60e5d125b5904beb106a3916dccbc295c26afe2`.
- Fixture C / Python SHA-256:
  `505ebc1168227fac5a3fc211dec4b4c2061ede847f6fc3d2366c14dbc9c03ae5` /
  `75f986e59b490ffc225d1c6f66cb54dd14daeefbb3ce487ee76b55c8336b9c0a`.
- Retained native ILP32 executable / linker-map SHA-256:
  `a586b9982a17e583d6566eb4e432059c40c28aa918389bed5ea0795fb54073df` /
  `751e1157fbd20b7c6efc02f66e343dfcd5e67d3d58bbd135bd75a6b561105a39`.
- Retail package audit manifest SHA-256:
  `e4a9721846db228b88e6a563c34c0dccc7c6dc7694cf5a393d66c67ca004503b`.
- `a30` source map / package SHA-256:
  `287959f34a7379a1dbec5fec15b4d94d17fe97ccd861f5c0c8fc80148b7ed293` /
  `ce38764fbba687bb26d4f2eb8a6cf066e19e4b8b81521d6f70f23ce8d00f183d`.
- `a50` source map / package SHA-256:
  `d7a3e80a86f2b0f23d855ce353aed3c0eb252145697797d87f25623dc470f38d` /
  `9359e0eb09427b098d9773708352c77dbf426ebcec9d7b27400268d84221941a`.
- Exact verified command:

```sh
PYTHONPATH=.:submodules/halo-ps2/tools \
HALO_HCU_M2_PACKAGE_ROOT=/tmp/hcu-m2-capacity-repro.P5qdmI/packages \
HALO_HCU_M2_PACKAGE_MANIFEST=docs/reports/retail-cbsp-catalog-package-audit-e4a97218.json \
HALO_HCU_M2_RETAIN_LINK_ARTIFACTS=1 \
python3 -m pytest -q -rs tests/test_hcu_scenario_bsp_switch.py -k retail -x
```

The ordinary sandbox run builds the same fixture but its native ILP32 execution
is blocked by SIGSYS; the recorded pass used the approved native execution
path. `git diff --check` passed for the parent and HCU submodule worktrees.

## Scope and remaining gaps

This closes only the host-side CE location/weather consumer branch for these
materialized `a30`/`a50` BSPs. It does not establish underwater rendering,
weather simulation, valid fog-region/plane selection, water depth, sound
environment selection/playback, independent collision goldens, PS2 capacity,
PCSX2 gameplay-map execution, or visible rendering. Step 7 remains partial and
Step 8 remains the capacity/target-residency gate.

The attempted `structure_get_planar_fog_definition_index()` draft was removed:
linking the broad CE `structures.c` translation unit conflicts with the
fixture's intentional fail-closed `structure_cluster_marker_begin/end`
adapters. This was confirmed by the report-only review
[`m2-step7-next-environment-consumer-slice-2026-10-21.md`](m2-step7-next-environment-consumer-slice-2026-10-21.md)
and the independent implementation review. Halo-64's
[`port/n64/NOTES.md:33-55`](../../submodules/halo-64/port/n64/NOTES.md#L33)
is relevant only as a boundary comparison: game-owned CPU state remains
distinct from platform drawing. It provides no CE fog/weather oracle or PS2
memory authority. REA was not applicable because this qualification executes
known CE source against hash-bound retail map/package data rather than
investigating an opaque binary or unexplained runtime artifact.
