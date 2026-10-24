# M2 Step 7 — a30 BSP B000 edge-grazing candidate revalidation

## Finding

The a30 B000 surface-27 shared-edge neighborhood is a useful and implementable
Step 7 fixture increment, provided it is treated as a *paired adjacent-face*
test rather than as “surface 27 hit vs miss.” I independently decoded every
collision surface in the exact decompressed raw map, followed each edge ring,
computed segment/plane intersections, checked polygon containment, and walked
the raw BSP3D/BSP2D structures for the candidate paths. All **19,138/19,138**
surface rings decoded for B000. At 0.01 map-unit offsets on opposite sides of
the shared edge, each query has exactly one raw polygon intersection: the
inside query hits surface 27; the outside query hits adjacent surface 94. Both
share the same raw collision edge (surface 27 vertices 0–1 and surface 94
vertices 0–1). The raw BSP path changes from leaf 10114 to 10113 on the outside
query and then reaches the solid sentinel; the inside query reaches the
surface-27 plane from leaf 10114. Raw BSP2D lookup of the relevant leaf
references resolves the expected surface IDs 27 and 94 respectively.

Do **not** use an exact edge midpoint as the primary acceptance case. The
current independent strict polygon helper intentionally rejects boundary
points (`abs(cross) < 1e-5`), and CE routes exact BSP2D plane equality through
the `distance >= 0` child. Exact-boundary acceptance is therefore a valuable
separate diagnostic for CE’s float/edge convention, but its expected result
needs target/compiler-confirmed rounding before becoming a golden.

## Raw source and exact candidate inputs

The source input is `build/retail-maps/decompressed/a30.map`, SHA-256
`287959f34a7379a1dbec5fec15b4d94d17fe97ccd861f5c0c8fc80148b7ed293`, HCU
pin `6933490b2d16bb1c637295b6a0f3880ba23a7d56`. The existing raw parser
resolves the structure-BSP root and bounded arrays in
[`test_hcu_scenario_bsp_switch.py`](../../tests/test_hcu_scenario_bsp_switch.py#L250-L289),
then follows source `collision_edge` rings and reads source plane/surface
fields in [the polygon decoder](../../tests/test_hcu_scenario_bsp_switch.py#L291-L334).
The parsed surface-27 triangle is:

```text
v0 = ( 43.07497024536133, -112.23355102539062,   25.81563949584961)
v1 = ( 28.668270111083984, -111.40211486816406, -73.46902465820312)
v2 = ( 56.85362243652344, -132.08467102050781, -73.46902465820312)
surface 27: plane_designator 30, flags 0, material 3
raw plane 30: (-0.5897691249847412, -0.8037135004997253,
                0.07884792983531952, 66.83484649658203)
```

Surface 94 shares the same v0–v1 edge but is a different triangle and plane:

```text
v0 = (28.668270111083984, -111.40211486816406, -73.46902465820312)
v1 = (43.07497024536133, -112.23355102539062, 25.81563949584961)
v2 = (38.759647369384766, -106.47339630126953, 47.80506134033203)
surface 94: plane_designator 108, flags 0, material 3
raw plane 108: (-0.6186754703521729, -0.7812255024909973,
                 0.08323071151971817, 63.17893600463867)
```

Use the midpoint of shared edge v0–v1,
`m=(35.871620178222656,-111.81783294677734,-23.826692581176758)`. The
oriented unit normal of plane 30 is
`n=(-0.5897691227111505,-0.8037134974013678,0.07884792953135662)`. The
in-plane unit vector from the edge midpoint toward surface 27’s interior is
`q=(0.3644032226283358,-0.3519826870797768,-0.8621591960503487)`. For
`epsilon=+0.01` and `epsilon=-0.01`, construct:

```text
contact = m + epsilon*q
start   = contact + 0.5*n
vector  = -n                 # length 1; expected t near 0.5
```

Raw double-precision derivation (header values should be rounded to float32
before finalizing a checked-in golden):

| Offset | Start | Vector | Unique raw hit | `t` | BSP3D raw evidence |
|---|---|---|---|---:|---|
| `+0.01` interior to surface 27 | `(35.5803796491, -112.2232095223, -23.7958902084)` | `(0.5897691227, 0.8037134974, -0.0788479295)` | surface 27, material 3, designator 30 | `0.49999601` | start/pre-contact leaf 10114, cluster 33; segment end is invalid-child/solid sentinel |
| `-0.01` beyond surface 27 into surface 94 | `(35.5730915846, -112.2161698686, -23.7786470245)` | `(0.5897691227, 0.8037134974, -0.0788479295)` | surface 94, material 3, designator 108 | `0.500225093` | start leaf 10114, pre-contact leaf 10113, both cluster 33; segment end is invalid-child/solid sentinel |

For the second row, raw leaf 10114 references plane 30 and surface 27; raw
leaf 10113 references plane 108 and surface 94. Raw BSP2D traversal at each
respective plane intersection returns the listed surface. This is a
source-derived expected face change across the shared edge, not a CE-generated
golden. The current raw decoder is capable of generating the vectors and
surface tuples, but must be extended to retain an explicit shared-edge
candidate record instead of relying only on its interior-centroid query
selection.

### Required independent oracle checks before accepting the record

1. Hash-bind the exact decompressed `a30.map`, HP2 package, manifest, source
   pins, and generated header. Confirm B000 identifies `levels\\a30\\a30_a`.
2. Require every source surface to decode (already observed for this map) and
   perform a scale-aware line/plane calculation plus inclusive 2-D polygon
   containment for all 19,138 polygons. For the +/-0.01 records, require
   exactly one in-range polygon contact, expected surface identity, and a
   minimum signed interior margin. Record the runner-up minimum margin so
   future coordinate/float changes fail closed rather than silently turn the
   query into a vertex/edge ambiguity.
3. Re-run intersections using float32-rounded inputs and float32-equivalent
   intermediate arithmetic. The preliminary double derivation has ample
   geometric separation at 0.01, but the final expected `t` and point must
   correspond to the serialized C float inputs. Recommended C assertions:
   `abs(t - expected_t) <= 2e-4`, hit-point component error `<= 1e-3` world
   units, exact surface/material/designator/flags, and exact leaf/cluster
   identities. These tolerances are proposed, not yet validated on the native
   fixture.
4. Independently walk raw BSP3D along each query to record the start leaf,
   every crossed node/plane, leaf transition around contact, and the
   immediately pre-contact leaf. Independently walk the relevant source
   BSP2D references/nodes at each surface plane using CE’s *documented source
   rule* (`distance >= 0` selects child 1) and confirm the terminal surface.
   Keep source geometry calculations separate from CE execution so a shared
   CE traversal error cannot define the expected output.
5. Add both vectors to the existing package-backed native C fixture and call
   `collision_test_vector(STRUCTURE | FRONT_FACING, ...)`. Assert the
   source-derived result tuples, unchanged BSP/source bytes and breakable
   state, unchanged published BSP identity, and zero dynamic-object adapter
   calls. The fixture already exercises these invariants for its raw hit and
   a50 miss/backface queries
   ([C fixture](../../tests/hcu_scenario_bsp_switch_main.c#L1147-L1225),
   [directional assertions](../../tests/hcu_scenario_bsp_switch_main.c#L1265-L1354)).
6. Add a third exact-edge vector only as a separately labeled diagnostic. The
   source plane and polygon are known, but current Python oracle rejects exact
   edge points by design; CE’s polygon check permits zero cross products while
   its BSP2D tree routes equality to child 1. Do not gate milestone acceptance
   on a CE-exact edge result until float32 reproduction and both adjacent
   BSP2D outcomes are qualified.

## CE semantics and interpretation

The public CE `collision_test_vector()` initializes the result (`type=NONE`,
leaf/cluster indices `NONE`, `t=1`) and maps BSP surface/material/plane data
when the BSP routine reports a hit
([`collisions.c:478-575`](../../submodules/halo-ce-universal/source/physics/collisions.c#L478)).
The BSP recursion recognizes empty-to-solid transitions as front-facing and
chooses the prior empty leaf for surface lookup; solid-to-empty is tested only
when the back-facing bit is enabled
([`collision_bsp.c:2226-2247`](../../submodules/halo-ce-universal/source/physics/collision_bsp.c#L2226)).
For the selected surface point, CE follows that leaf’s BSP2D references for
the crossing plane, chooses the surface by the BSP2D tree, then validates its
edge ring and projected polygon
([`collision_bsp.c:1821-1894`](../../submodules/halo-ce-universal/source/physics/collision_bsp.c#L1821)).
The polygon edge test rejects a point only when a projected edge cross product
is positive ([`collision_bsp.c:1584-1610`](../../submodules/halo-ce-universal/source/physics/collision_bsp.c#L1584));
the BSP2D node traversal selects child 1 for zero distance
([`bsp2d.c:30-60`](../../submodules/halo-ce-universal/source/physics/bsp2d.c#L30)).
Thus exact edge inclusion is a real behavior worth testing, but it is more
rounding-sensitive than the two offset cases.

This is structure-only collision evidence. It does not qualify dynamic-object
arbitration, pill/player sweep, breakable transitions, map-wide collision
parity, target runtime, memory capacity, or frame-time. Halo-64 is only an
architecture comparator: its N64 collision cuts and budget are not evidence
for CE collision semantics or the PS2 acceptance bar. REA is not applicable;
the exact collision code and decompressed source arrays are inspectable.

## Current status

The two +/-0.01 queries are independently proven against every decoded source
surface and the corresponding raw BSP3D/BSP2D paths. They are ready for a
carefully scoped fixture implementation and exact native ILP32 execution.
No CE fixture was executed for these proposed vectors in this review, so they
are not yet accepted CE behavior or a Step 7/M2 completion gate. Exact-edge
behavior remains diagnostic-only until float32 rounding and the CE BSP2D tie
case are executed and recorded.
