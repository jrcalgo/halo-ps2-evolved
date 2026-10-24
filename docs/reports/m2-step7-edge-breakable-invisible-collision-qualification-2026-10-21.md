# Step 7 edge, invisible, and breakable collision qualification

## Result

The package-backed native ILP32 transaction now checks four collision queries against Halo CE's real `collision_test_vector()` implementation: rays offset to both sides of a shared BSP edge, an exact shared-edge tie, an invisible/two-sided face and its ignore flag, and a breakable face before and after its breakable-state bit is cleared. The independent expectation builder reads the retail Xbox map's raw collision records, derives segment intersections, walks the serialized BSP3D tree for leaf state, and follows each leaf's BSP2D references/tree to determine which coincident face CE selects. This last part matters: raw geometry alone found coincident surfaces at both initial flagged candidates and cannot establish CE's chosen face by nearest-hit ordering.

This is a host semantic integration result only. It does not prove target-sized collision-query memory/capacity, guest EE performance, visible rendering, campaign-map admission, or the remaining Step 7 consumers.

## Implemented fixture behavior

- The source oracle in [`tests/test_hcu_scenario_bsp_switch.py`](../../tests/test_hcu_scenario_bsp_switch.py#L270) validates all collision arrays, decodes polygon edge rings, derives unique shared-edge offset rays for `a30` B000 surfaces 27 and 94, and calculates candidate hits without calling CE traversal code.
- The same oracle mirrors only the serialized leaf-reference/BSP2D selection contract in CE's source: `collision_leaf_test_vector()` scans a leaf's `bsp2d_references`, matches the plane designator, projects the hit point, and calls `bsp2d_test_point()` ([`collision_bsp.c`](../../submodules/halo-ce-universal/source/physics/collision_bsp.c#L1821), [`bsp2d.c`](../../submodules/halo-ce-universal/source/physics/bsp2d.c#L30)). The traversal is separately bounded by the raw node counts. It is an expectation-side parser, not the system under test.
- [`assert_a30_shared_edge_grazing()`](../../tests/hcu_scenario_bsp_switch_main.c#L789) calls the integrated CE/parent collision wrapper for both offset rays and an exact tie at the source-derived shared-edge midpoint. The offset rays assert exact surface/material/plane/flags, start and pre-contact leaves, endpoint sentinel, hit parameter and point; the exact tie requires CE to select one of the two adjacent retail surfaces, with the expected material, nearby point, and valid adjacent pre-contact leaf. It also checks that the materialized BSP bytes, breakable state, and active BSP globals are unchanged.
- [`assert_a30_flagged_surface_queries()`](../../tests/hcu_scenario_bsp_switch_main.c#L871) queries surface 12034 (`flags=3`, two-sided + invisible) with and without `_collision_test_ignore_invisible_surfaces_bit`; it then queries surface 7795 (`flags=9`, breakable index 1), clears that bit in the CE breakable bitmap, and requires the hit to disappear. The bit is restored after the test. CE performs the selected-surface check in [`collision_surface_test_point()`](../../submodules/halo-ce-universal/source/physics/collision_bsp.c#L1544), with wrapper filtering in [`collision_bsp_test_vector_recursive()`](../../submodules/halo-ce-universal/source/physics/collision_bsp.c#L2255) and flag forwarding in [`collisions.c`](../../submodules/halo-ce-universal/source/physics/collisions.c#L478).
- Existing source-backed hit/miss/reverse-face, PVS aggregation/root refresh, sound-distance, and weather checks continue to run in the same package transaction. This addition does not replace or weaken those checks.

## Raw-derived cases

Source map `build/retail-maps/decompressed/a30.map` SHA-256 is `287959f34a7379a1dbec5fec15b4d94d17fe97ccd861f5c0c8fc80148b7ed293`.

| Case | Surface / material | Flags / breakable index | Start | Vector | Expected CE result |
|---|---|---|---|---|---|
| Shared edge, side A | 27 / 3 | 0 / 0 | `(35.58037965, -112.22320952, -23.79589021)` | `(0.58976912, 0.80371350, -0.07884793)` | hit at `t=0.4999960102`; start/precontact leaves `10114/10114`; end is solid sentinel |
| Shared edge, side B | 94 / 3 | 0 / 0 | `(35.57309158, -112.21616987, -23.77864702)` | `(0.58976912, 0.80371350, -0.07884793)` | hit at `t=0.5002250931`; start/precontact leaves `10114/10113`; end is solid sentinel |
| Invisible/two-sided | 12034 / 17 | 3 / 0 | `(7.38351488, 45.86596870, 65.55365753)` | `(0, 0, -1)` | hit with ordinary front-facing flags; no hit when invisible surfaces are ignored |
| Breakable | 7795 / 12 | 9 / 1 | `(-151.89996338, -23.00001240, 31.00000381)` | `(0, 0, -1)` | hit while state bit 1 is set; no hit after clearing that bit |

The exact-edge tie is deliberately checked against the adjacent-surface set rather than requiring one arbitrarily ordered face. This qualifies the observed CE traversal for this retail edge only; other edge/vertex topologies and broader cross-target tie stability remain open.

## Reproduction and immutable identities

Approved native command (native ILP32 execution is blocked by the ordinary sandbox's SIGSYS policy):

```sh
PYTHONPATH=.:submodules/halo-ps2/tools \
HALO_HCU_M2_PACKAGE_ROOT=/tmp/hcu-m2-capacity-repro.P5qdmI/packages \
HALO_HCU_M2_PACKAGE_MANIFEST=docs/reports/retail-cbsp-catalog-package-audit-e4a97218.json \
HALO_HCU_M2_RETAIN_LINK_ARTIFACTS=1 \
python3 -m pytest -s -q -rs tests/test_hcu_scenario_bsp_switch.py -k retail -x
```

Final result after adding the exact edge tie: **1 passed, 1 deselected, 2 package subtests passed in 132.87 seconds**. The unapproved sandbox run compiled but skipped native execution; it is not counted as acceptance. An earlier passing run before the tie assertion took 134.11 seconds and is superseded below.

- Parent repository HEAD: `70e2ed0cf2145a45d23aa07414a3a88c05155d4c` (the worktree was dirty; the exact test-source hashes below identify the working inputs).
- HCU submodule HEAD: `6933490b2d16bb1c637295b6a0f3880ba23a7d56`.
- halo-ps2 submodule HEAD: `71183bb0a9adc586cd267b2780c82bbc12cfd95b`.
- Native fixture ELF SHA-256: `952d3f6e2e75d9245311bbd94809a65f78236af79c4cf3d253af49a93005ce19` (392,836 bytes).
- Native link map SHA-256: `e95632028d3caaad8c3128fa33e6863cbd9a7a1c250382fb6682438f56b7974e`.
- Generated collision-golden header SHA-256: `baf06f15ab8c0f39ef778b717a4705a7d9fc7a014ef36628d6d013bdb9a5a414`.
- C fixture / Python oracle SHA-256: `34f768337a7c7828e7f1cefd44b9b63b7c57432829902900b1b8bc29547a5034` / `c6bbb80e3de73e75ae416192f852589479634b6ee1af30ba95044ad837db2e6f`.
- `a30` package SHA-256: `ce38764fbba687bb26d4f2eb8a6cf066e19e4b8b81521d6f70f23ce8d00f183d`.
- `a50` package SHA-256: `9359e0eb09427b098d9773708352c77dbf426ebcec9d7b27400268d84221941a`; `a50` map SHA-256: `d7a3e80a86f2b0f23d855ce353aed3c0eb252145697797d87f25623dc470f38d`.
- Package audit manifest SHA-256: `e4a9721846db228b88e6a563c34c0dccc7c6dc7694cf5a393d66c67ca004503b`.

## Remaining acceptance work

This closes only the raw-source shared-edge-offset/exact-tie, invisible-ignore, and breakable-state host subchecks for these selected retail surfaces. Step 7 still needs additional grazing/vertex and tie behavior across more topologies, further relevant collision edge/breakable/invisible integration cases, remaining real CE BSP consumers (including sound environment/background palette and the identified fog/weather/wind/geometry paths), and full failure-atomicity/player movement-to-collision ownership tests. The transaction's large host arenas do not meet the target-sized query gate.

Step 8 remains open and blocks target-sized Step 7 evidence: there is still no accepted lossless capacity topology satisfying all campaign maps, CE pointer/lifetime constraints, current named owners, and the untouched reserve. Do not count these host tests as EE placement/high-water or PCSX2 guest proof; do not reduce map scope, truncate fields, or spend reserve to make a query fit.
