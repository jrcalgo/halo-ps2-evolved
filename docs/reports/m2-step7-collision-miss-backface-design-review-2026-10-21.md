# M2 Step 7 — collision miss and reverse-face fixture design review

## Recommendation

Add two narrowly-scoped cases to the existing raw-source collision fixture,
using `a50_muster` (the `a50` source map, BSP index 1). Keep the raw map parser
as the expected-value authority and invoke CE's public
`collision_test_vector()` only as the system under test. First add an isolated
front-facing **miss**; then add a reverse traversal in two flag modes: front-only
must miss, back-only should hit the same single-sided source face. Keep these
as separate expected records and assertions. Do not describe the reverse case
as a normal-vector/backface heuristic: CE decides this from solid/empty BSP
leaf transitions, surface references and the selected front/back flags.

The exact source map is present at
`build/retail-maps/decompressed/a50.map` and has SHA-256
`d7a3e80a86f2b0f23d855ce353aed3c0eb252145697797d87f25623dc470f38d`, matching
the existing collision-golden qualification. The current oracle already
selects `levels\\a50\\a50_muster`, surface 0, material 1, runtime material
type 7, plane designator 1, and oriented plane `(0, 0, 1, -23.296905517578125)`.
Its front-facing source query is:

```text
start  = (10.505987882614136, -10.928828239440918, -22.796904802322388)
vector = (0, 0, -1)
t      = 0.5000007152557373
point  = (10.505987882614136, -10.928828239440918, -23.296905517578125)
```

I independently replayed the decoded source BSP3D leaf lookup for the
candidate endpoints. The existing query begins in leaf 8142 and ends in the
solid terminal (`NONE`). A short segment in the reverse-of-hit direction,
starting at the same empty point, ends in the same leaf 8142:

```text
miss start  = (10.505987882614136, -10.928828239440918, -22.796904802322388)
miss vector = (0, 0, +0.25)
raw leaves  = 8142 -> 8142; both structure-leaf cluster indices = 9
```

The raw surface scan should explicitly assert that this short segment has no
intersection with any decoded collision polygon before accepting the case.
For `collision_test_vector(STRUCTURE | FRONT_FACING, ...)`, expect return
`FALSE`, `type == NONE`, and `t == 1.0f`. Since the wrapper still copies BSP
traversal leaves even if no collision is found, this chosen same-leaf miss is
expected to report `start_location` and `location` as leaf 8142 / cluster 9,
not leave them as `NONE`. The result struct's other fields are not initialized
by this wrapper on a miss and must not be asserted. The fixture's `0xCD` fill
is appropriate for detecting accidental reads, but do not interpret untouched
surface/material/plane bytes as CE defaults.

## Reverse traversal: distinguish CE's two flag rules

Reverse the existing source query exactly, rather than choosing a visually
opposite normal independently:

```text
reverse start  = (10.505987882614136, -10.928828239440918, -23.796904802322388)
reverse vector = (0, 0, +1)
raw leaves     = solid terminal (NONE) -> leaf 8142 / cluster 9
surface        = 0; material = 1; runtime type = 7
reverse t      = 1 - 0.5000007152557373 = 0.4999992847442627
hit point      = (10.505987882614136, -10.928828239440918, -23.296905517578125)
```

These values are source-derived from the already hash-bound forward golden.
Before adding expected rows, extend the Python oracle to prove the reversed
segment still has exactly one intersection with the raw polygon set and that
its BSP endpoints classify as stated. Its direction change must not be used as
a proxy for those checks.

Run the reversed segment twice, with flags deliberately explicit:

1. `STRUCTURE | FRONT_FACING`: expect `FALSE`, `type == NONE`, `t == 1.0f`.
   The traversal reaches the empty leaf but the CE front rule does not accept a
   solid-to-empty transition. For this segment, CE's miss traversal should
   retain leaf 8142 as its first and last recorded leaf (cluster 9); assert
   this separately from the hit flags.
2. `STRUCTURE | BACK_FACING`: expect `TRUE`, structure result, surface 0,
   material 1, material type 7, plane designator 1, `t` near
   `0.499999285`, and hit point as above. In this direction the transition is
   solid-to-empty, which is exactly the branch gated by
   `_collision_test_back_facing_surfaces_bit` in CE. Because CE checks a back
   face on entry to the empty leaf before appending that leaf to the traversal
   list, the selected reverse-hit row should leave public `start_location` and
   `location` at their wrapper-initialized `NONE` values. Confirm this against
   the actual run; do not make it a golden assertion unless the fixture confirms
   the target source/tag's leaf transitions and CE output.

In both calls, also retain current invariants: forbidden object adapters are
not called, published BSP identity/index do not change, the materialized BSP
image is byte-identical before/after, and breakable flags remain unchanged.
The expected no-hit fields should be limited to values the public wrapper
actually initializes or derives; do not compare the full 0x50-byte struct.

## Source basis and semantic cautions

The current independent oracle derives hit queries from raw collision records
and raw BSP3D traversal in
[`tests/test_hcu_scenario_bsp_switch.py:163-405`](../../tests/test_hcu_scenario_bsp_switch.py#L163).
It currently emits only the front-facing hit row, so the miss and reversed
query should be added there as distinct source-derived records, not inferred
inside the C test from the CE result.

CE's public wrapper initializes only `type`, both location leaf/cluster pairs,
and `t` before dispatch ([`collisions.c:478-524`](../../submodules/halo-ce-universal/source/physics/collisions.c#L478)). It initializes `type` to `NONE`, locations to
`NONE`, and `t` to `1.0`; after BSP traversal it fills location pairs whenever
`leaf_count > 0`, even when the boolean result is false
([`collisions.c:563-576`](../../submodules/halo-ce-universal/source/physics/collisions.c#L563)). Thus “miss defaults” are conditional: type and t remain
defaults, while locations can become real leaf/cluster indices. A miss golden
must model the traversal's first and last recorded non-solid leaves.

The BSP walker sets `leaf_count` to zero and `result->t` to its maximum at
entry ([`collision_bsp.c:1220-1254`](../../submodules/halo-ce-universal/source/physics/collision_bsp.c#L1220)). During traversal it recognizes an
empty-to-solid transition only when the front-facing flag is present, and a
solid-to-empty transition only when the back-facing flag is present; two-sided
semi-empty handling is a separate third branch
([`collision_bsp.c:2211-2251`](../../submodules/halo-ce-universal/source/physics/collision_bsp.c#L2211)). It tests the chosen leaf for a surface and returns on
success before appending the current valid leaf to `leaf_indices`
([`collision_bsp.c:2253-2305`](../../submodules/halo-ce-universal/source/physics/collision_bsp.c#L2253)). This is why a reverse backface hit may have
`NONE` public locations while the corresponding front-only reverse miss has
leaf 8142; confirm the precise result on the retained fixture rather than
assuming all collision misses share location defaults.

There is a flag-default trap: if neither front nor back face is requested, the
public wrapper enables **both** ([`collisions.c:514-524`](../../submodules/halo-ce-universal/source/physics/collisions.c#L514)). Therefore every new
directional case must set exactly one of the two face bits, alongside the
structure bit. The current production fixture explicitly sets front-facing
([`hcu_scenario_bsp_switch_main.c:1219-1223`](../../tests/hcu_scenario_bsp_switch_main.c#L1219)); reusing that mask for the reversed query should
exercise the front-only rejection. The back-only query needs its own call and
must not accidentally include the front bit.

## Ownership and platform implication

This test must remain an HCU collision-API qualification: CE owns BSP
collision traversal, result initialization/selection, and collision leaf to
cluster mapping. The test-side raw Xbox map decoder is only an independent
oracle. The parent/halo-ps2 path owns package loading/materialization and
hardware services; it must not introduce a second gameplay collision answer.
These fixture increments therefore require no PS2 production collision code
change. Later PS2 evidence still needs to prove package storage, arena bounds,
and on-device query performance independently; this host ILP32 result cannot
prove those.

Halo-64 is a boundary comparator only: its port notes explicitly say
simulation must not read render results ([`NOTES.md:35`](../../submodules/halo-64/port/n64/NOTES.md#L35)). That supports keeping this fixture's authoritative query
in CE and treating PS2-side rendering as a consumer, but it provides no
collision parity, capacity, or timing evidence for this PS2 port. Do not copy
Halo-64's cuts or budgets. REA is not applicable: this review compares
available CE source against hash-bound, decoded retail map records; it is not
recovering undocumented behavior from an opaque executable.

## Exit checks for this increment

- Source map and package identities still match the pinned audit manifest.
- The Python oracle independently proves zero polygon hits for the short miss,
  exactly one same-surface hit for the reversed segment, and raw BSP leaf
  classification for each endpoint.
- The native fixture tests front-only miss defaults/leaf reporting and the
  back-only reverse hit tuple, while testing the reverse front-only rejection.
- No result fields that CE leaves unwritten on a miss are read or compared.
- Existing six front-hit goldens and BSP immutability checks still pass.
- Report the exact executable/map hashes and native ILP32 result. Until this
  runs, treat the expected backface location behavior as source-based
  prediction, not verified fact.
