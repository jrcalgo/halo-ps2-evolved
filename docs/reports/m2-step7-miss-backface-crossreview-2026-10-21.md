# M2 Step 7 — miss and reverse-facing collision fixture cross-review

## Scope and conclusion

I reviewed the new a50-muster directional cases in
[`test_hcu_scenario_bsp_switch.py`](../../tests/test_hcu_scenario_bsp_switch.py#L419),
the CE-call assertions in
[`hcu_scenario_bsp_switch_main.c`](../../tests/hcu_scenario_bsp_switch_main.c#L1244),
the CE public wrapper and BSP traversal, and the earlier raw-source golden report.
I did not edit shared code and did not run/claim target or native fixture tests.
The prior qualification report records that its ordinary sandbox run skips the
native ILP32 execution under SIGSYS; any claim for the newly added cases still
requires the approved native run.

The CE-facing assertions are well matched to the implementation for these two
carefully selected cases. In particular, the reverse test correctly expects a
solid-to-empty crossing to be ignored with front-only flags and accepted with
back-only flags, and it avoids inspecting hit-only fields on a miss. The raw
oracle is meaningfully independent of CE's traversal. One residual oracle
completeness issue should be fixed or explicitly constrained before claiming
that the miss is mathematically proven against every raw polygon: the raw
segment/polygon checker drops parallel planes without checking whether the
segment is coplanar with and overlaps a polygon. This is likely irrelevant to
the chosen normal-offset miss, but the current code does not establish that.

## Source-backed validation

1. **Miss defaults and leaf locations:** `collision_test_vector()` initializes
   `type`, both leaf/cluster pairs to `NONE`, and `t=1.0f` before querying the
   BSP ([`collisions.c`](../../submodules/halo-ce-universal/source/physics/collisions.c#L491)).
   The BSP query initializes `leaf_count=0` and records each valid traversed
   leaf unless it returns early on a hit
   ([`collision_bsp.c`](../../submodules/halo-ce-universal/source/physics/collision_bsp.c#L1220),
   [`collision_bsp.c`](../../submodules/halo-ce-universal/source/physics/collision_bsp.c#L2295)).
   For the source-derived short miss, the raw oracle proves both endpoints
   traverse to the same non-solid leaf and the segment has no detected polygon
   intersection ([test oracle](../../tests/test_hcu_scenario_bsp_switch.py#L451)).
   Therefore CE should return false with `type=NONE`, `t=1`, and both wrapper
   locations equal to that leaf and its structure cluster, as asserted in the C
   fixture ([C assertions](../../tests/hcu_scenario_bsp_switch_main.c#L1265)).
   These are initialized or explicitly traversal-written fields; the fixture
   correctly leaves all other poisoned fields unread.

2. **Directional transition semantics:** the recursive BSP code treats a
   transition from empty/semi-empty to solid as front-facing, choosing the
   prior empty leaf for surface lookup; a solid-to-empty transition is tested
   only with the back-facing bit and selects the entering empty leaf
   ([`collision_bsp.c`](../../submodules/halo-ce-universal/source/physics/collision_bsp.c#L2226)).
   The return from the successful surface test occurs before the current leaf
   is appended to `leaf_indices` ([`collision_bsp.c`](../../submodules/halo-ce-universal/source/physics/collision_bsp.c#L2253)).
   Consequently, the reverse backface hit has `leaf_count==0`; the public
   wrapper's location members remain at their initialized `NONE` values. The
   fixture's front-only reverse miss should append the empty endpoint leaf and
   consequently report that leaf/cluster for both start and final locations.
   Those expectations match the code path.

3. **Independent geometric construction:** the candidate reverse begins at
   the original hit segment's endpoint and negates its vector. The raw tree
   must classify its start as the solid sentinel (`-1`) and its endpoint as
   the original empty leaf; the raw polygon check requires exactly one hit on
   the originally selected surface
   ([oracle](../../tests/test_hcu_scenario_bsp_switch.py#L470)). The raw hit
   parameter/point are then compared with CE's back-only result, while
   surface/material identity and plane designator are cross-checked against
   the original forward golden
   ([fixture](../../tests/hcu_scenario_bsp_switch_main.c#L1292)). This is a
   suitable reverse-direction golden, not an expected value derived from CE.

4. **State preservation/ownership:** the directional tests reassert no object
   adapter calls, unchanged BSP selection, unchanged full BSP bytes, and
   unchanged breakable flags. This keeps HCU as collision authority while the
   parent/PS2 side only materializes the package under test. The previous
   qualification explicitly leaves dynamic-object collision, broader map
   parity, EE execution/capacity, and player movement outside this fixture
   ([qualification limits](m2-step7-independent-collision-golden-qualification-2026-10-21.md#L108)).

## Required oracle hardening

At [`source_segment_hits()`](../../tests/test_hcu_scenario_bsp_switch.py#L430),
`abs(denominator) < 1e-9` is unconditionally treated as no intersection. That
is correct for a non-coplanar parallel segment, but not enough to prove no
intersection for a segment lying in a polygon's plane: such a segment may
overlap the polygon without a unique plane-crossing parameter. The current
candidate miss is short, stays in one raw empty leaf, and moves away from the
selected surface, so this is probably not a practical failure for a50 muster;
however, the comment that *all* raw polygons were ruled out overstates what the
checker proves.

Before treating this as a complete raw-geometry miss oracle, either:

- detect the near-parallel/coplanar case using a scale-aware plane-distance
  tolerance and test segment/polygon overlap in the polygon's dominant-axis
  projection; reject the candidate if overlap is found, or
- prove from the exact generated miss inputs that every near-parallel raw
  polygon is non-coplanar by a documented distance margin, and encode that
  check so future source-map or input changes cannot bypass it.

Keep this separate from CE's expected no-hit behavior. The CE wrapper initializes
the public result, whereas the raw oracle's job is to establish that the query
really has no source-geometry contact. Also retain the current full decode
requirement: rejecting a `None` surface row prevents a partial polygon inventory
from being mistaken for a proof of no hit.

## Test/evidence status and plan impact

No tests were run in this review. The prior report says the sandbox/native
boundary skips ILP32 execution unless using the approved native path; it reports
the earlier forward-hit test passed, not these new miss/backface additions.
After addressing the coplanar-oracle gap, run the exact approved native command
against both a30 and a50 packages and preserve the executable/map/source hashes
and per-BSP directional output. Do not upgrade Step 7 or M2 to complete from
source inspection alone.

Halo-64 is only a comparative architecture reference here. Its N64 collision
cuts or budgets do not establish the PS2/CE result. REA is not indicated: the
relevant CE semantics and raw BSP records are visible in source and decompressed
map data, so no unresolved opaque binary behavior motivated this review.
