# M2 Step 7 — source-derived multiplayer exact-vertex collision

## Result

A raw-source exact-vertex contact was found in Beaver Creek and validated
through CE's real `collision_test_vector()`. The test ray is built from the
source vertex `(7.56110334, 21.50254440, 3.05857038)` and the serialized normal
of incident surface 39. The original BSP independently gives a simultaneous
first-contact set of six surfaces `{39, 75, 162, 315, 549, 684}` at `t` about
`0.4999988`; the start leaf's serialized BSP2D references permit the
CE-selected subset `{39, 162, 315, 549}`. CE selected surface **549**, which
belongs to both source-proven sets. Its material/type, start leaf 191, and hit
fraction passed. The same assertion passed twice, once in each map lifecycle
cycle. Expected output is an allowed source-derived surface set, never a
single face copied from CE.

This is package-backed native ILP32 host evidence, not EE/PCSX2 or Step 8
capacity evidence. It is one exact vertex case, not exhaustive collision
topology acceptance.

## Search bounds and oracle

The raw scan read the one structure BSP of each of the 13 stock multiplayer
maps from the pinned decompressed retail maps. It walked each decoded surface
edge ring to recover source vertices, grouped face incidences by identical
serialized vertex coordinates, and screened vertices shared by at least
three polygons. For each candidate it tried rays along a candidate face's
normalized serialized plane, requiring:

* the contact is the exact source vertex and is inclusively inside at least
  three raw source polygons;
* every simultaneous first-contact surface belongs to that vertex's incident
  face set, is unflagged, and has an in-range material index/type;
* the segment traverses empty-to-solid in the raw BSP3D; and
* the source leaf's serialized BSP2D reference/node traversal returns at least
  one of the simultaneous contact faces.

The raw polygon, incidence, float32 tuple, BSP3D, and BSP2D checks are in
[`audit_mp_collision_edge_pairs.py`](../../tools/audit_mp_collision_edge_pairs.py#L55)
(inclusive boundary query and serialized reader) and lines 129–150 and
261–301 (leaf selector and exact vertex search). This bounded screen found a
runtime candidate in Beaver Creek; it is not a negative result for any other
map because the tool intentionally stops at its first qualified vertex per
BSP and does not vary ray directions beyond the tested face normals.

The isolated generated host harness adds the raw source-derived contact set
and allowed face set to the existing all-13 CE lifecycle fixture, then invokes
`collision_test_vector()` and requires the CE surface to belong to both sets
and to retain the expected source material/type, leaf, and `t`. See
[`test_hcu_mp_collision_edge.py`](../../tools/test_hcu_mp_collision_edge.py#L35)
for raw tuple generation and lines 168–193 for the inserted vertex runtime check.
CE's public vector path publishes the selected surface and material from the
BSP query at
[`collisions.c:478-577`](../../submodules/halo-ce-universal/source/physics/collisions.c#L478);
leaf-local reference selection is implemented at
[`collision_bsp.c:1821-1885`](../../submodules/halo-ce-universal/source/physics/collision_bsp.c#L1821).
Halo-PS2's retail BSP layout notes describe the source BSP3D and leaf encoding
at [`08-bsp-section.md:18-36`](../../submodules/halo-ps2/docs/08-bsp-section.md#L18).

## Reproduction and artifacts

```sh
python3 tools/test_hcu_mp_collision_edge.py
```

Native host ILP32 rerun: **1 passed in 67.678 s**. This is the existing
13-map package-backed test (two map cycles) with source-derived offset-edge,
exact-edge, and Beaver Creek exact-vertex queries. Source pins: parent
`70e2ed0cf2145a45d23aa07414a3a88c05155d4c`, HCU
`6933490b2d16bb1c637295b6a0f3880ba23a7d56`, halo-ps2
`71183bb0a9adc586cd267b2780c82bbc12cfd95b`; Beaver Creek map SHA-256
`eaf90b2abc4fd295469eb2d640063618b0d14396f28e7d7f1758e834c061c50a`.

Retained artifacts are under
`build/m2-mp-edge-runtime-1792685388829095323/`:

* manifest SHA-256 `175ce7e15dfc5868cd3b7793b0987624284c5a937d388c99994db58dd76f1cd4`;
* generated source-golden header SHA-256 `d1ef84206e9371fb87339c8f802c7e330cf60e69ef5a5a9fbcbdbd0dfe5b0821`;
* native executable SHA-256 `1713a9bbc99c6655dbc36feff9fc9d0dfda70882908357e73694c23abcd9b1dd`;
* link map SHA-256 `fd193abf8a33642b977a06a44628c4ddc784944af80293a76a3dd8307dd49f9`;
* complete CE run log SHA-256 `a3b531e4714402b3d3c3a55b21499717ffeaa85d380d1611f7e66e60ac4f5a6a`.

The host fixture retains the existing 16 MiB tag and 8 MiB BSP arrays; no
PS2-sized placement or workload claim follows from this result.
