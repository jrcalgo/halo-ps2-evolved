# Step 7 MP edge/vertex topology candidate search — blocker and evidence

## Outcome

This bounded investigation did **not** add an MP topology assertion. It found
that suitable-looking geometry is abundant, but it did not establish the
required complete source oracle + CE-query pair with valid, unique expected
surface/material/plane/leaf tuples. The MP shared-edge and vertex/grazing gate
therefore remains open; no ambiguous candidate was promoted to a test golden.

The existing a30 fixtures remain their separate, non-MP comparator. Their
shared-edge offset case is hard-coded to a30 surfaces 27/94 and its known leaf
paths (`tests/test_hcu_scenario_bsp_switch.py:1032-1113`); it cannot be cited as
13-map multiplayer topology evidence. The all-13 ordinary-hit matrix and
Prisoner breakable/directional assertions from the prior report are unaffected.

## Bounded source inventory

The inventory read the raw Xbox collision-surface, edge, and vertex blocks for
the 13 decompressed stock MP maps. The decoder already used by the accepted
hit fixture follows source edge rings, retains flags/material/plane designator,
and decodes polygon vertices (`tests/test_hcu_scenario_bsp_switch.py:683-735`).
The candidate scan grouped polygons by identical geometric edge endpoints and
counted distinct adjacent, unflagged, same-material face pairs. This is only a
geometric adjacency count—not proof that the CE-selected leaf's BSP2D reference
routes a candidate ray to either face.

| Map | Candidate same-material, unflagged shared-edge pairs |
|---|---:|
| Beaver Creek | 3,342 |
| Blood Gulch | 6,731 |
| Boarding Action | 4,555 |
| Carousel | 1,154 |
| Chill Out | 2,197 |
| Damnation | 5,494 |
| Hang 'em High | 2,128 |
| Longest | 1,438 |
| Prisoner | 2,987 |
| Putput | 7,461 |
| Rat Race | 1,811 |
| Sidewinder | 8,722 |
| Wizard | 2,131 |

The count is useful for narrowing a future search, but must not be mistaken for
CE query candidates. In an exploratory Beaver Creek check, the first routed
shared-edge candidate was surfaces 1/46 and CE-source-equivalent BSP2D
selection chose surface 1; however that face has `material_index=-1` (`NONE`).
CE intentionally maps the `NONE` material index to `NONE` material type
(`submodules/halo-ce-universal/source/physics/collisions.c:290-306`), so this
candidate was rejected for the requested valid-material topology fixture.
Other geometry-only Beaver candidates such as 39/75 have material 0, but their
two offset rays were not both independently traced through the raw BSP3D
leaves and BSP2D face selector and therefore remain unqualified.

The raw source inventory also found **zero stock-MP collision surfaces with
the invisible flag set** (CE flag bit 1, mask `1 << 1`). Prisoner has eight
breakable surfaces, but none of the 13 maps has an invisible-only surface.
Consequently the prior a30 invisible-ignore test has no stock-MP input to
exercise; mark this subcheck unsupported by the current stock map set, not
passed for multiplayer. CE's filter condition is explicit at
`submodules/halo-ce-universal/source/physics/collision_bsp.c:2273-2276`, and
flag bit assignments are at `:96-102`.

The raw candidates and source/package identities are bounded by the exact
all-MP matrix tuple: source map and package hashes are pinned in
`tests/test_hcu_mp_capacity.py:21-49` and retained with per-package generation
records in `build/m2-mp-host-13-collision/manifest.json`. For Beaver Creek,
source map SHA-256 is
`eaf90b2abc4fd295469eb2d640063618b0d14396f28e7d7f1758e834c061c50a`, package
SHA-256 is `4f95672c4233a63d30e94395010324076cb1454813facb54e48c065d7c776dfc`,
and converter schema ELF SHA-256 is
`2fba411b7244b20fdf31f0b1e540fc2b6f5598891f53a64f8b12f850a0cda0aa`. The
recorded conversion command is:

```sh
tools/pack_retail_ctag_hp2.py \
  build/retail-maps/decompressed/beavercreek.map \
  build/m2-artifacts/schema-2fba411b-prior/halo-local.elf \
  build/m2-mp-extra/beavercreek-all-bsps.hp2 --include-all-bsps
```

## Why the candidate is not yet safe to assert

The independent oracle must validate the candidate across all decoded source
polygons, not just adjacency: calculate each float32 serialized-plane contact,
require exactly one polygon containment per offset ray, establish a useful
inside-edge margin, traverse BSP3D to the empty/contact leaves, then run the
source-mirrored leaf BSP2D reference and node selection for that exact face.
The current helper has those independent BSP3D/BSP2D checks for ordinary hits
and Prisoner flagged faces (`tests/test_hcu_scenario_bsp_switch.py:737-810,
:1181-1295`), while the a30 shared-edge candidate derives its two source rays
and checks both polygon uniqueness and leaf paths (`:1032-1113`). No tested MP
pair has yet completed all those gates for *both* sides of the edge.

Similarly, a vertex/grazing case must be a separate source-derived tuple, not
an exact geometric tie accepted merely because CE returns one adjacent
surface. The existing a30 report notes that exact boundary points are
rounding-sensitive and keeps its exact tie diagnostic-only
(`docs/reports/m2-step7-edge-grazing-candidate-revalidation-2026-10-21.md`).
No MP vertex/grazing point has had float32/source-BSP2D uniqueness established
in this bounded search.

## Next safe action

Resume by screening same-material, non-`NONE`, unflagged shared-edge pairs in
the already pinned MP maps. For each candidate, use the existing source edge
decoder and tree/BSP2D helpers; reject any pair if either offset ray lacks a
unique raw polygon hit, has a near-zero polygon-edge margin, traverses a solid
start leaf, or the source BSP2D selector does not choose the expected face.
Then run the pair in the native ILP32 package-backed CE fixture and assert the
full collision result plus unchanged BSP/global state. Only after that pair
passes should a second search derive a near-vertex grazing case. Keep exact
ties diagnostic-only until their source and float32 routing are reproducible.

This is a focused Step 7 blocker report, not Step 7 closure. It does not change
core collision behavior or Step 8 target-capacity requirements. The prior
13-map native run remains host semantic evidence only; its command and
artifacts are recorded in
`docs/reports/m2-step7-mp-collision-next-slice-audit-2026-10-22.md`.
