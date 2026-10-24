# M2 Step 7 — Independent collision hit/miss golden: next slice review

## Finding

The next highest-value Step 7 slice is a source-map-derived, frozen collision
golden over the existing `a30`/`a50` package transaction. Current tests already
execute CE collision code against the relocated retail BSP, and the recent
location/weather consumer slice adds useful environment coverage. The material
gap is independence: the current collision probe uses CE to find and describe
the candidate polygon, then compares the public CE wrapper with CE's own lower
level traversal. A shared traversal defect could therefore satisfy both sides.
This review is report-only; no source or plan files were changed and no new test
was run.

## What the data and current fixture actually establish

CE's collision schema is explicit. `global_collision_bsp_fields` orders blocks
as BSP3D nodes, planes, leaves, BSP2D references/nodes, surfaces, edges, and
vertices ([`collision_bsp_definitions.c:145-210`](../../submodules/halo-ce-universal/source/physics/collision_bsp_definitions.c#L145)).
The schema defines a collision surface as a signed plane designator, first-edge
index, flags, breakable index, and material index; an edge has two vertex,
edge, and surface indices; a vertex is a point plus first edge
([`collision_bsp_definitions.h:35-55`](../../submodules/halo-ce-universal/source/physics/collision_bsp_definitions.h#L35)).
The CE structure-BSP definition separately owns collision materials, collision
BSP, structure leaves, and world bounds ([`structure_bsp_definitions.h:178-220`](../../submodules/halo-ce-universal/source/structures/structure_bsp_definitions.h#L178)).
The 8-byte collision leaf stores BSP2D reference count/first-reference plus a
double-sided-surfaces flag; the BSP3D node stores a plane and signed front/back
children ([`collision_bsp_definitions.c:140-185`](../../submodules/halo-ce-universal/source/physics/collision_bsp_definitions.c#L140),
[`bsp3d.h:32-45`](../../submodules/halo-ce-universal/source/physics/bsp3d.h#L32)).

The current candidate generation is visibly CE-derived: it samples up to 2,048
surface indices, calls `collision_surface_polygon()`, averages those returned
vertices, reads the CE plane block/designator, and builds a segment across that
plane ([`hcu_scenario_bsp_switch_main.c:1013-1088`](../../tests/hcu_scenario_bsp_switch_main.c#L1013)).
It then asks `collision_bsp_test_vector()` for a hit and uses that returned
record as the expected basis before invoking `collision_test_vector()` on the
same endpoints ([`hcu_scenario_bsp_switch_main.c:1089-1165`](../../tests/hcu_scenario_bsp_switch_main.c#L1089)).
The wrapper compares hit fraction, surface/material, material type, plane,
leaf/cluster, hit point, and verifies the BSP image and breakable bitset remain
unchanged ([`hcu_scenario_bsp_switch_main.c:1165-1194`](../../tests/hcu_scenario_bsp_switch_main.c#L1165)).
That is solid CE composition/immutability evidence, but not an independent
expected hit tuple. The prior implementation review reaches the same boundary
([`m2-step7-full-ce-collision-wrapper-implementation-review-2026-10-21.md:46-57`](m2-step7-full-ce-collision-wrapper-implementation-review-2026-10-21.md#L46)).

The existing Python oracle is a useful design precedent, not yet a collision
oracle: it resolves raw retail BSP extents from the Xbox map and reads original
bytes, with CE-layout offsets checked against declarations
([`test_hcu_scenario_bsp_switch.py:27-55`](../../tests/test_hcu_scenario_bsp_switch.py#L27));
it currently extracts PVS, sound-distance, and cluster/weather data only
([`test_hcu_scenario_bsp_switch.py:56-158`](../../tests/test_hcu_scenario_bsp_switch.py#L56)).
The package test already binds exact source-map/package identities and runs the
real CE BSP switch, rollback, and consumers; do not weaken or replace that
transaction when adding the oracle. Its artifact identities and known host-only
limitations are recorded in
[`m2-step7-retail-consumer-query-qualification-2026-10-21.md:1-71`](m2-step7-retail-consumer-query-qualification-2026-10-21.md#L1).

## Recommended independent golden construction

Add a Python-side raw-map parser beside `retail_source_pvs_pair_oracle()` and
bind each golden to the source map SHA, raw BSP path/extent, HP2 package SHA,
CBSP image SHA, and fixture executable/map SHA. Use the existing compiler-derived
tag schemas and the `halo-ps2` map/BSP locator to resolve the original Xbox
structure-BSP root, its nested `collision_bsp` block, and every child block;
validate count × element-size bounds before decoding. Keep the oracle parser
small and independently check its offsets/strides against CE compiler layouts
at build time. Relevant source record layouts are `collision_surface` 12 bytes,
`collision_edge` 24 bytes, `collision_vertex` 16 bytes, and `structure_leaf`
with cluster index at `+0x0A` (assert these rather than copying guessed offsets).

Select one stable hit candidate by brute-force geometry over the **raw source
records**, not CE helpers: walk the serialized surface edge ring using each
edge's owner-side indices; collect source vertex coordinates; decode the
surface's plane index and sign; compute a point strictly inside the polygon
(centroid is acceptable only after confirming it is not on a boundary); and
form a short segment normal to the plane. Independently intersect that segment
against every raw collision polygon and reject candidates where another
surface intersects first, the point is outside the candidate polygon, the
candidate is invisible/breakable or has `NONE` material, the material/leaf is
invalid, or an endpoint lies too close to a BSP split. For a surviving query,
freeze the literal expected record in a reviewed golden: `(surface_index,
material_index, runtime_physics_material_type, raw_plane_designator, oriented
plane [i,j,k,d], t, hit point, start_leaf, end_leaf, start_cluster,
end_cluster)`. Compute `t` analytically from the raw plane and endpoints; resolve
the expected surface/material/leaf mapping from raw blocks. Require the CE
wrapper and CE low-level traversal to match this raw-derived tuple, but do not
use either CE result to choose the golden. If source geometry cannot prove a
unique first hit without reproducing too much BSP logic, retain the test as a
geometry-derived candidate test and explicitly do not call it an independent
traversal golden.

Expected tuple design details:

- Keep the query endpoints symmetric around the chosen point along its source
  plane normal (e.g. ±1.0 map units, subject to source-scale/float checks),
  giving analytically expected `t=0.5`. Use the signed plane designator to
  orient the expected plane exactly as CE does; the high/sign bit is material
  because `collision_test_vector()` negates the returned plane when set
  ([`collisions.c:528-560`](../../submodules/halo-ce-universal/source/physics/collisions.c#L528)).
- Resolve both leaf endpoints independently with raw CE BSP3D tree traversal
  only if that traversal is itself part of the desired oracle; otherwise choose
  a segment whose start/end points lie in structure leaves whose classification
  is independently decoded and asserted, and keep the expected surface tuple
  separate from CE's leaf traversal. Document this distinction: a raw geometry
  oracle validates collision plane/polygon selection; it does not, by itself,
  validate CE BSP3D leaf arbitration.
- The current CE wrapper is structure-only and passes
  `MAXIMUM_BREAKABLE_SURFACES_PER_MAP` plus the all-intact test fixture bitmap
  through to the low-level query ([`collisions.c:519-536`](../../submodules/halo-ce-universal/source/physics/collisions.c#L519),
  fixture initialization [`hcu_scenario_bsp_switch_main.c:1240-1250`](../../tests/hcu_scenario_bsp_switch_main.c#L1240)).
  Preserve these narrowly stated assumptions; this does not qualify damage or
  breakable-state ownership.

## Miss, backface, and arbitration cases

1. **Deterministic miss:** choose a finite segment wholly outside raw
   `structure_bsp.world_bounds`, with a conservative margin larger than any
   float epsilon, and prove by raw bounds that it cannot enter the collision
   world. Call the public structure-only wrapper with a sentinel-filled result;
   assert false, type `NONE`, `t == 1`, start/end leaf and cluster `NONE`, and
   unchanged BSP/breakable/publication state. Do not infer these defaults from
   the wrapper's return alone: CE initializes them explicitly at
   [`collisions.c:495-500`](../../submodules/halo-ce-universal/source/physics/collisions.c#L495).
   Also test a segment ending just before the independent hit point as a
   near-miss only if the raw geometry proves it remains on one side of the
   plane and no adjacent polygon intersects.
2. **Front/back arbitration:** use a raw-source surface whose `two-sided`
   surface flag is clear and whose segment is uniquely isolated as above. The
   front-facing flag should hit with the frozen tuple; reverse the segment and
   repeat with only front-facing enabled, expecting no hit. Repeat the reverse
   query with only back-facing enabled and expect the matching surface/plane
   hit, if the raw BSP marks permit it. Do not assume simple reversal always
   misses: test the exact CE facing predicates and surface flag behavior in
   [`collision_bsp.c:96-101, 2126-2300`](../../submodules/halo-ce-universal/source/physics/collision_bsp.c#L96).
   A two-sided candidate is a separate test; CE's ignore-two-sided bit and
   collision-leaf double-sided flag must not be conflated.
3. **Nearest-hit arbitration:** if a segment crosses two source polygons, make
   that an explicit golden only after independent analytic intersections
   identify the nearest `t`. Otherwise reject such a candidate and keep the
   first milestone narrowly scoped. This avoids accidentally treating surface
   array order or the CE traversal's first returned face as the oracle.

## Bounded closure and execution

The narrow test already links the real CE `scenario.c`, `collision_bsp.c`,
`bsp2d.c`, and `collisions.c` in a function/data-section ILP32 fixture; the
full public wrapper performs the result/material/leaf mapping shown at
[`collisions.c:478-575`](../../submodules/halo-ce-universal/source/physics/collisions.c#L478).
Keep raw parsing on the Python side. Avoid adding AI, physics tick, objects,
media/fog, effects, sound playback, or renderer sources. Retain fail-closed
object adapters and assert they remain at zero calls for structure-only flags.
Before accepting the added cases, inspect the retained ELF and linker map for
new rooted CE functions/data and demonstrate that the fixture remains limited
to collision traversal, material/leaf mapping, and existing transaction code.

Verification should be the same package-backed native ILP32 run for both
`a30` and `a50`, after switch/rollback/retry, with source map/package/CBSP
hashes, oracle tuple, executable/map hashes, and exact test-source hashes
recorded. Run the focused host regressions (schema walker, CBSP/CTAG, collision
synthetic, package BSP switch) and `git diff --check`. The sandbox SIGSYS skip
does not count as native fixture execution; retain the approved native result.
This remains host-only: a50's BSP exceeds the production `current_bsp` region,
so no EE-capacity or PCSX2 gameplay-map claim follows. Step 8's physical
capacity/residency gate remains blocking.

## Comparative context and REA

Halo-64 is useful only for the ownership boundary: its notes preserve
simulation-side state even where renderer calls are absent
([`port/n64/NOTES.md:33-55`](../../submodules/halo-64/port/n64/NOTES.md#L33)).
That supports keeping CE collision semantics in the game/simulation closure;
it is not a PS2 budget, collision oracle, or reason to remove collision cases.
REA is not applicable to this slice: the question is the behavior of known CE
source on hash-pinned raw retail BSP data and its converted package, not an
opaque executable or unexplained binary artifact.

## Disposition

Proceed with the raw-source geometry oracle as the next Step 7 implementation
slice. Freeze one uniquely intersected hit tuple first; add miss and reversed
facing cases only after their raw geometry preconditions are mechanically
checked. Step 7 remains **active/partial** until these independent expectations,
the other required BSP consumers/failure atomicity, and Step 8-qualified target
execution are addressed.
