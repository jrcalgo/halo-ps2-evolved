# M2 Step 7 — exact shared-edge tie through CE collision

## Outcome

An exact-zero shared-edge tie is source-derived and now passes through CE's
actual `collision_test_vector()`. The case is Beaver Creek surfaces 39 and 94.
The raw Xbox collision BSP says the first-contact point is their exact common
edge midpoint; both polygons contain the contact inclusively, both have valid
same material/type and no flags, and the leaf's serialized BSP2D selectors
allow either face. The test therefore asserts a CE-valid adjacent-face set
`{39, 94}`, not a fabricated unique-face oracle. At runtime CE selected surface
39 on both lifecycle iterations, and the result passed material, material
type, start leaf, and `t` checks.

This is native ILP32 package-backed host evidence, not target/PCSX2 evidence or
Step 8 capacity proof. It validates one exact edge tie; vertex hits and grazing
segments remain open.

## Independent source criteria

The raw-source scanner reads the original decompressed Xbox map and reconstructs
the collision surface loops from their edge/vertex tables. It qualifies only
an unflagged pair with identical valid material indices/types and exactly two
shared vertices. At the shared-edge midpoint it constructs a float32 start and
segment along the first surface's normalized serialized plane. The simultaneous
first-contact set must contain both adjacent faces; all first-contact faces
must be unflagged and retain that valid material. The raw BSP3D start/end must
traverse empty-to-solid, and the exact contact must be selected by a serialized
leaf BSP2D reference for at least one member of that adjacent set. The point is
not picked from CE's result. The adjacent-set expansion and inclusive polygon
test are in [`audit_mp_collision_edge_pairs.py`](../../tools/audit_mp_collision_edge_pairs.py#L41)
(especially lines 128–176); offset edge pairs and their BSP route checks are
lines 177–243.

The test generator adds one exact-tie row to a temporary copy of the existing
13-map CE fixture and calls the real CE vector collision query; its assertion
checks the returned face belongs to the source-proven adjacent set and verifies
source material/type, start leaf, and hit fraction. See
[`test_hcu_mp_collision_edge.py`](../../tools/test_hcu_mp_collision_edge.py#L35)
(case generation) and lines 85–148 (runtime query insertion and evidence
capture). No production collision source, map-admission rule, or memory budget
was modified.

CE's public vector path publishes the surface/material/plane/leaf output from
the collision-BSP test at
[`collisions.c:478-577`](../../submodules/halo-ce-universal/source/physics/collisions.c#L478).
For the relevant per-leaf route, CE matches the plane designator in the leaf's
BSP2D references, projects the point, and runs the referenced BSP2D node tree
at [`collision_bsp.c:1821-1885`](../../submodules/halo-ce-universal/source/physics/collision_bsp.c#L1821).
Halo-PS2's independent retail structure notes document the source BSP3D
children, leaves, and leaf-to-cluster layout at
[`08-bsp-section.md:18-36`](../../submodules/halo-ps2/docs/08-bsp-section.md#L18).

## Case and coverage boundary

| Map | Shared edge | Raw exact-contact face set | BSP2D-valid selected set | CE result |
|---|---:|---:|---:|---:|
| Beaver Creek | 39 / 94 | {39, 94} | {39, 94} | 39 |

The raw screen examined all collision surface/edge/vertex data in the single
structure BSP of each of the 13 stock MP maps. With this filter and a ray
normal to the lower-index face, candidates were found in 11 maps; Boarding
Action and Damnation did not yield a candidate under those criteria. This is
not a claim that those maps lack every possible exact tie: the bounded search
does not vary the ray direction or admit differing-material/flagged edges.
One valid case is sufficient for this follow-up; the all-13 offset-adjacency
matrix remains documented separately in
[`m2-step7-mp-shared-edge-ce-runtime-2026-10-22.md`](m2-step7-mp-shared-edge-ce-runtime-2026-10-22.md).

## Reproduction and exact run

```sh
python3 tools/test_hcu_mp_collision_edge.py
```

Native host ILP32 rerun: **1 passed in 70.498 s**. The existing fixture ran
all 13 package-backed map lifecycles twice; the added Beaver Creek exact tie
therefore produced two successful CE queries. Source pins: parent
`70e2ed0cf2145a45d23aa07414a3a88c05155d4c`, HCU
`6933490b2d16bb1c637295b6a0f3880ba23a7d56`, halo-ps2
`71183bb0a9adc586cd267b2780c82bbc12cfd95b`; Beaver Creek source map SHA-256
`eaf90b2abc4fd295469eb2d640063618b0d14396f28e7d7f1758e834c061c50a`.

Retained evidence is under
`build/m2-mp-edge-runtime-1792685151343546537/`:

* manifest SHA-256 `df6707d9700e451454d4ce06f02e43cec2d8ce0237ff04d1ef49fd33022928f0`;
* generated edge golden SHA-256 `d447ea5f8ec891c9d8deed5361101f3b24c7bbd867c2d709d1aaae53ff7a333d`;
* native executable SHA-256 `4eabf55a6b2d0a1fbb0676557b2437309c96d52f9653bcbff4dcd2d38663764a`;
* linker map SHA-256 `16b24885b93045ca47b1c8fb61baec4d212b3f7df9645aad8ed5e19773b049f9`;
* CE output log SHA-256 `0af35b0ce5f3224512118a527190b2d207e93a4c1755111644b07d191fe42739`.

The run manifest carries the exact float32 start/vector/contact and allowed
surface set. The host fixture still uses 16 MiB tag and 8 MiB BSP buffers, so
it provides no target RAM/capacity evidence.
