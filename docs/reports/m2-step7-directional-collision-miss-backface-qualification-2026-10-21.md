# M2 Step 7 — source-derived collision miss and reverse-face qualification

## Result

The Step 7 raw-retail collision oracle now covers more than front-facing hits.
The `a50_muster` (`a50`, B001) case derives a short miss that remains in an
empty BSP leaf and the exact reversal of its independently derived front hit.
The real CE public `collision_test_vector()` wrapper was run against the
materialized retail BSP: the short query missed with CE's initialized
`type=NONE`, `t=1`, and traversal-derived leaf/cluster 8142/9; the reversed
front-only query missed; and the reversed back-only query hit surface 0 at
`t=0.4999992847`. The accepted native ILP32 run passed **1 test, 2 package
subtests in 139.39 seconds**.

This closes only the raw-source-derived miss/front-vs-back subcheck for this
one BSP. It is not broad collision parity, player collision, target execution,
capacity evidence, or M2 completion.

## Independent raw-source construction

[`tests/test_hcu_scenario_bsp_switch.py`](../../tests/test_hcu_scenario_bsp_switch.py)
parses the hash-verified original Xbox map collision arrays and BSP3D tree.
For the miss, the segment starts at the already-selected raw hit start and
moves 0.25 units away from the surface: `(10.5059879, -10.9288282,
-22.7969048)` with vector `(0, 0, +0.25)`. Raw BSP3D traversal classifies both
endpoints as collision leaf 8142; its structure leaf names cluster 9. The
oracle rejects the case unless every collision surface can be decoded, no
decoded polygon is intersected, and no parallel/coplanar segment overlaps a
polygon. The coplanar test projects to the dominant-normal plane and performs
inclusive segment-edge and endpoint-in-polygon checks; thus a near-parallel
plane is not silently treated as a guaranteed miss.

The reverse query starts at the original segment end `(10.5059879,
-10.9288282, -23.7969048)` and uses vector `(0, 0, +1)`. The raw BSP tree
classifies its start as solid and its end as leaf 8142. The raw polygon scan
requires exactly one hit, on source surface 0, at `t=0.4999992847442627` and
point `(10.5059879, -10.9288282, -23.2969055)`. These expectations are
generated into a temporary C header from the raw map; they are not copied from
CE's result.

## CE assertions and ownership

[`tests/hcu_scenario_bsp_switch_main.c`](../../tests/hcu_scenario_bsp_switch_main.c)
runs three explicit masks against CE:

1. `STRUCTURE | FRONT_FACING` on the short miss: false, `type=NONE`, `t=1`,
   and start/final leaf and cluster 8142/9. It does not read poisoned hit-only
   result fields.
2. `STRUCTURE | FRONT_FACING` on the reverse query: false with the same
   traversal leaf/cluster. This covers CE's rejection of a solid-to-empty
   transition under front-only flags.
3. `STRUCTURE | BACK_FACING` on the reverse query: true, structure type,
   source surface/material/runtime-material/plane-designator identity, raw
   `t` and hit point. CE returns before appending the empty leaf, so both
   location pairs remain wrapper-initialized `NONE`; the fixture checks that
   observed path.

Each directional call also checks the no-object-adapter invariant, unchanged
published BSP identity/index, byte-identical full materialized BSP, and
unchanged breakable flags. This matches ownership: HCU owns collision
traversal/result arbitration; the parent and pinned halo-ps2 path only load and
materialize the package. Halo-64 is only an architecture-boundary comparator,
not a collision algorithm or PS2 budget source. REA is not applicable because
the exact CE source and decompressed retail collision records are inspectable.

## Reproduction and identities

Approved native ILP32 command (outside the sandbox, which blocks this
executable with SIGSYS):

```sh
PYTHONPATH=.:submodules/halo-ps2/tools \
HALO_HCU_M2_PACKAGE_ROOT=/tmp/hcu-m2-capacity-repro.P5qdmI/packages \
HALO_HCU_M2_PACKAGE_MANIFEST=docs/reports/retail-cbsp-catalog-package-audit-e4a97218.json \
HALO_HCU_M2_RETAIN_LINK_ARTIFACTS=1 \
python3 -m pytest -q -rs tests/test_hcu_scenario_bsp_switch.py -k retail -x
```

The final exact-source run passed **1 passed, 1 deselected, 2 package
subtests**. The focused sandbox regressions passed **30 tests, 2 expected
SIGSYS skips, 4 deselected, and 2 subtests**. `python3 -m py_compile
tests/test_hcu_scenario_bsp_switch.py` and `git diff --check` passed.

| Artifact/input | SHA-256 |
|---|---|
| Parent source pin | `70e2ed0cf2145a45d23aa07414a3a88c05155d4c` |
| HCU source pin | `6933490b2d16bb1c637295b6a0f3880ba23a7d56` |
| halo-ps2 source pin | `71183bb0a9adc586cd267b2780c82bbc12cfd95b` |
| Package manifest | `e4a9721846db228b88e6a563c34c0dccc7c6dc7694cf5a393d66c67ca004503b` |
| a30 decompressed source map | `287959f34a7379a1dbec5fec15b4d94d17fe97ccd861f5c0c8fc80148b7ed293` |
| a30 HP2 package | `ce38764fbba687bb26d4f2eb8a6cf066e19e4b8b81521d6f70f23ce8d00f183d` |
| a50 decompressed source map | `d7a3e80a86f2b0f23d855ce353aed3c0eb252145697797d87f25623dc470f38d` |
| a50 HP2 package | `9359e0eb09427b098d9773708352c77dbf426ebcec9d7b27400268d84221941a` |
| Final native fixture executable (rerun after shared 64-byte test-arena alignment) | `2bbc19577daf4d454625459051415aa294539c486db5bf7977a7a31a2cdcd532` |
| Final native fixture link map | `83cacfe018c3b6ab8ed2cd134ff831559e401eb6e18564fc273bb91030de5950` |
| Python raw oracle/runner | `4ef269f41f9457780ece8efae829616e49a7c24923400e7b267db4d80a68f730` |
| C CE integration fixture (current; 64-byte test-arena alignment) | `3fe6ee55a8dc682bf0bec7b87dd52b2dc09e274097276a12db5de246d9b9c84f` |
| Independent design review | `154c5cfcbd5991e7f3bbaea597d28632730d3955e54e4de0984fbdea27d4d247` |
| Independent code cross-review | `26b1325e9cf57620027ea42964edd58bff7189440db57e4df20f226abc352aeb` |

The code cross-review found a parallel/coplanar blind spot in the first oracle
draft. The final native run (1 test, 2 package subtests in 138.75 seconds) is
after that finding and after the shared test owner's alignment changed to 64
bytes; it includes the dominant-axis coplanar overlap check. Focused
regressions passed 30 tests, with two expected SIGSYS skips. The reviews and implementation agree that
Step 7 still needs broader boundaries, breakable/invisible response, dynamic
object interaction, player-collision integration, EE/PCSX2 capacity/performance
evidence, and rollback/failure coverage before its milestone exit can close.
