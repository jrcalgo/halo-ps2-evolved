# M2 Step 7 — source-backed multiplayer shared-edge CE queries

## Result

The earlier `m2-step7-mp-edge-vertex-candidate-blocker-2026-10-22.md` is
superseded for shared-edge adjacency: a stricter source-derived search followed
by the real CE query has now passed on all 13 stock multiplayer maps. For each
map the fixture uses one pair of adjacent, unflagged, same-material surfaces;
it derives one ray per face, slightly inset from the common edge, and proves
from the original Xbox BSP that each ray intersects only that expected face.
It independently follows the serialized BSP3D to an empty-to-solid boundary
and the start leaf's BSP2D reference to that face. The CE result must select
that exact source-derived face, material/type, plane designator, leaf, and
approximately the expected `t`; either target also has to belong to the
source-adjacent pair. The expected face is not copied from CE output.

Native ILP32 execution of the generated fixture passed the complete
all-13-map lifecycle test, including two load/query/unload cycles. This yields
52 actual `collision_test_vector()` shared-edge-adjacency assertions (26
distinct map/face rays, repeated once). This is package-backed **host semantic
evidence only**, not an EE/PCSX2 query, PS2-sized memory proof, renderer test,
or map-admission approval. The rays are inset by 0.01 world units; exact
zero-offset edge ties and vertex/grazing cases remain separate open coverage.

## Why this corrects the previous blocker

The earlier report correctly rejected Beaver Creek surfaces 1/46: the selected
face had `material_index == NONE`, and correctly refused to promote 39/75
without tracing both raw BSP paths. It did not finish the all-map source
search. This run instead finds the valid Beaver Creek pair 39/94 and proves
both sides; it found a qualifying pair in each of the remaining 12 maps too.
The earlier table's large 1,154–8,722 values were broad geometric candidate
counts, not CE-qualified pairs. The new scanner's small `candidate_pairs`
counter is after strict same-material, valid-material-type, unflagged, two
shared-vertex filtering; the runtime further insists on two separately routed
faces. Therefore those counts are different filters and do not conflict.

## Source oracle and runtime path

The scanner [`audit_mp_collision_edge_pairs.py`](../../tools/audit_mp_collision_edge_pairs.py)
reads raw map BSP extents using the Halo-PS2 map/BSP readers, then decodes
collision surfaces, edge rings, vertices, planes, leaves, BSP3D nodes, leaf
BSP2D references, and BSP2D nodes directly from the serialized Xbox BSP. Its
candidate checks require a valid material type, no surface flags, exactly two
common polygon vertices, float32-rounded offset rays, one and only one
polygon intersection, empty-to-solid BSP3D traversal, and BSP2D selection of
the same face (lines 43–204). The generated CE fixture is orchestrated by
[`test_hcu_mp_collision_edge.py`](../../tools/test_hcu_mp_collision_edge.py).
It injects source-generated cases into a temporary copy of the existing
all-13 lifecycle fixture; the repo's production collision semantics, memory
limits, and map admission are untouched. The added assertion calls the actual
CE public `collision_test_vector()` and compares the complete relevant result
fields (generated harness logic at lines 82–127).

CE's live vector routine delegates to `collision_bsp_test_vector()` and
publishes the CE-selected surface, material, plane designator, and visited
leaf state at [`collisions.c:478-577`](../../submodules/halo-ce-universal/source/physics/collisions.c#L478).
The per-leaf selector scans serialized BSP2D references and projects the
intersection point before traversing the BSP2D node root at
[`collision_bsp.c:1821-1885`](../../submodules/halo-ce-universal/source/physics/collision_bsp.c#L1821);
the traversal only accepts valid source leaves and handles empty/solid
transitions at [`collision_bsp.c:2220-2276`](../../submodules/halo-ce-universal/source/physics/collision_bsp.c#L2220).
The raw layout is independently described in Halo-PS2's
[`08-bsp-section.md:18-36`](../../submodules/halo-ps2/docs/08-bsp-section.md#L18),
including BSP3D child encoding, matching collision/render leaves, and the
source leaf-to-cluster relationship. The retained Halo-PS2 cache path
materializes CE's Xbox tag image and visits one bounded CBSP section at a time;
see [`ctag_mount.c:108-145`](../../src/stream/ctag_mount.c#L108) and the
Halo-PS2 `bsp.c` reader. This test uses the current HP2/CBSP package lifecycle,
not a duplicate custom collision implementation.

## Cases and source map identities

Each row gives the selected surface for each ray, in adjacent-pair order;
both rows share that map's listed adjacent pair. `type` is CE's collision
material type. The case file contains exact float32 start/vector/t/plane/leaf
tuples.

| Stock MP map | Adjacent surfaces | Expected face results | Material type |
|---|---:|---:|---:|
| Longest | 2 / 35 | 2, 35 | 7 |
| Blood Gulch | 84 / 164 | 84, 164 | 2 |
| Beaver Creek | 39 / 94 | 39, 94 | 2 |
| Prisoner | 0 / 1487 | 0, 1487 | 7 |
| Boarding Action | 16 / 56 | 16, 56 | 7 |
| Carousel | 21 / 189 | 21, 189 | 7 |
| Chill Out | 1 / 129 | 1, 129 | 7 |
| Damnation | 7 / 62 | 7, 62 | 7 |
| Hang 'em High | 0 / 10 | 0, 10 | 7 |
| Putput | 4 / 926 | 4, 926 | 7 |
| Rat Race | 2 / 190 | 2, 190 | 7 |
| Sidewinder | 85 / 111 | 85, 111 | 2 |
| Wizard | 2 / 3 | 2, 3 | 7 |

All 13 source-map hashes and all exact query tuples are retained in
`build/m2-mp-edge-runtime-1792684627811086422/manifest.json`.

## Reproduction and artifacts

Run from the repository root; native execution may require running outside a
SIGSYS-restricted sandbox:

```sh
python3 tools/test_hcu_mp_collision_edge.py
```

The harness uses the pinned package/source/schema assertions already in
`tests/test_hcu_mp_capacity.py`; it also requires the current CE and Halo-PS2
source pins recorded in the run manifest. Run evidence:

* Test: **1 passed, 69.649 s**, native host ILP32.
* Parent HEAD: `70e2ed0cf2145a45d23aa07414a3a88c05155d4c`.
* HCU HEAD: `6933490b2d16bb1c637295b6a0f3880ba23a7d56`.
* Halo-PS2 HEAD: `71183bb0a9adc586cd267b2780c82bbc12cfd95b`.
* Schema ELF: `2fba411b7244b20fdf31f0b1e540fc2b6f5598891f53a64f8b12f850a0cda0aa`.
* Test manifest SHA-256: `0c1ef2fccaf948e4ce1bee7abadce021087143d06d0d664ad6d54a84fd012da6`.
* Generated golden header SHA-256: `8b2059284acd79aa1c4d33ac2b2541103392d67fa9f2558a919f1929b71c00c8`.
* Executable SHA-256: `b2bd89da859bf67b097c71725aa73db1f1a3500d4d821139389b61b5936cba1b`.
* Link map SHA-256: `bb2f11275cd6df2a5b1d91dd5b6d0f44b85536dfa13e4e6bb225cbd02935b6b0`.
* Guest/native output log SHA-256: `f6a8efcefea006ade3b2cb40039dddaf04d29cea867aec3eabaafffbcbf523f1`.
* Source-screen JSON (temporary `/tmp/mp-edge-screen.json`) SHA-256:
  `81402b07e4e61ecae906a953b00bb53830fad7bc493100fb35ac545f2c1d99d7`; the
  reproducible source tuples and all map hashes are also embedded in the
  retained run manifest above.

The exact pinned source map table, generated fixture, executable, link map,
and full CE output are under `build/m2-mp-edge-runtime-1792684627811086422/`.
The host fixture retains the existing 16 MiB tag / 8 MiB BSP work buffers and
therefore does not support any Step 8 capacity conclusion.

## Remaining boundary

This closes the stock-MP **adjacent shared-edge two-face routing** subcheck,
not all Step 7 collision topology. Still required: exact edge contact / tie
stability, at least one raw-source-proven vertex or grazing case if stock MP
geometry admits one, more edge/vertex topologies beyond one pair per map,
and target-sized query evidence after Step 8. Do not generalize this two-face
test into an exact-boundary tolerance guarantee; CE's float32 BSP2D routing
and serialized leaf reference order remain the source of truth.
