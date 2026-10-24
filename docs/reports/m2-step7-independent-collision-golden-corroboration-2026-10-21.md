# M2 Step 7 — independent collision-golden implementation review

## Verdict

The new raw-source oracle is meaningfully independent of CE collision
traversal, and the qualification evidence supports a **host-side structure-hit
golden subcheck** for all six package-backed BSPs in `a30` and `a50`. The
implementation closes the prior circular-oracle issue for hit selection and
result tuple checking. It does **not** provide a miss golden or front/back
arbitration coverage; therefore it must not be described as hit/miss or full
collision acceptance. Step 7 remains partial, and no target/capacity claim
follows.

This is a report-only review. I inspected current code and retained artifacts,
did not change implementation or plan files, and did not rerun the ~133-second
native ILP32 test.

## Oracle independence and raw record interpretation

`retail_source_collision_goldens()` reads source-map BSP extents via the
`halo2ps2.bsp.locate()` map locator, then parses the original Xbox BSP bytes
directly ([`test_hcu_scenario_bsp_switch.py:163-240`](../../tests/test_hcu_scenario_bsp_switch.py#L163)).
It does not call CE's `collision_surface_polygon()`,
`collision_bsp_test_vector()`, or `collision_test_vector()` when deriving the
expected query and tuple. It decodes edge rings and vertices directly,
resolves the signed plane designator and material, analytically intersects the
query segment with all decoded raw polygons, requires exactly one interior
intersection, and independently walks the raw BSP3D tree for start/contact
leaf and structure-cluster indices ([same file:241-405](../../tests/test_hcu_scenario_bsp_switch.py#L241)).
The temporary C golden header is generated only after this parser finishes
([same file:416-454, 565-579](../../tests/test_hcu_scenario_bsp_switch.py#L416)).
This is a sound independent geometry oracle for the selected source records;
the test still uses CE, as it should, to validate the relocated package result.

The raw field widths and offsets agree with the separately audited source
layout in [`halo2ps2/bsp.py:16-25, 36-51`](../../submodules/halo-ps2/tools/halo2ps2/bsp.py#L16):
structure BSP collision materials at `+0xA4` with stride 20, collision BSP at
`+0xB0` with eight reflexives, collision nodes/planes/leaves at child offsets
`+0/+0x0C/+0x18`, structure leaves at `+0xE0`, and world bounds at `+0xC8`.
CE's declarations independently corroborate the collision records:
`collision_surface` is 12 bytes, `collision_edge` 24, `collision_vertex` 16,
and `collision_bsp` has the same eight-block order
([`collision_bsp_definitions.h:35-82`](../../submodules/halo-ce-universal/source/physics/collision_bsp_definitions.h#L35),
[`collision_bsp_definitions.c:145-210`](../../submodules/halo-ce-universal/source/physics/collision_bsp_definitions.c#L145)).
The collision BSP3D node stores plane/back/front; the source tool documents
this ordering and `n·p-d >= 0` front classification
([`bsp3d.h:32-45`](../../submodules/halo-ce-universal/source/physics/bsp3d.h#L32),
[`bsp.py:36-46`](../../submodules/halo-ps2/tools/halo2ps2/bsp.py#L36)).
The raw runtime collision material type is decoded at material record `+18`,
consistent with CE's tag-backed structure material layout
([`structure_bsp_definitions.h:212-216`](../../submodules/halo-ce-universal/source/structures/structure_bsp_definitions.h#L212)).

There is one small oracle-hardening opportunity: `tree_leaf()` returns the
low 31-bit leaf index without separately asserting it is less than the
collision-leaf count before that index is used to read the structure-leaf
array ([`test_hcu_scenario_bsp_switch.py:286-306, 377-388`](../../tests/test_hcu_scenario_bsp_switch.py#L286)).
All tested retail bytes are hash-bound and the test confirms collision- and
structure-leaf counts match, so this does not undermine the present six
goldens; add an explicit `leaf_index < structure_leaves[0]` check before any
indexed read to make malformed-source failure deterministic.

## CE path and asserted result fields

After the earlier CE-derived probe, the fixture looks up the raw-source row for
the currently published map/BSP and invokes the actual public CE
`collision_test_vector()` with only structure and front-facing flags
([`hcu_scenario_bsp_switch_main.c:1193-1223`](../../tests/hcu_scenario_bsp_switch_main.c#L1193)).
CE's wrapper initializes the result and calls the real
`collision_bsp_test_vector()` ([`collisions.c:478-560`](../../submodules/halo-ce-universal/source/physics/collisions.c#L478));
the raw golden is not copied from this CE answer.

The C assertions compare result type, surface/material index, runtime material
type, signed plane designator, hit `t`, all four oriented plane floats, hit
point, start and contact leaf, and both cluster indices
([`hcu_scenario_bsp_switch_main.c:1219-1243`](../../tests/hcu_scenario_bsp_switch_main.c#L1219)).
The preceding CE-composition query separately checks its fields and full
materialized BSP/breakable-state immutability. The raw-golden query then checks
the returned CE structure globals and leaves object adapters at zero calls;
the full BSP snapshot and breakable-bitset snapshots are checked after both
queries ([same file:1140-1153, 1252-1255](../../tests/hcu_scenario_bsp_switch_main.c#L1140)).
That combination is stronger than a return-code smoke test and correctly
distinguishes the CE result under test from Python's raw-source expectation.

## Verified golden rows and exact run evidence

The qualification report records independently derived rows for:

| Map/BSP | Surface | Material/type | Plane designator | Start → contact leaf (cluster) | `t` |
|---|---:|---:|---:|---|---:|
| a30 / a30_a | 27 | 3 / 2 | 30 | 10733 → 10731 (33 → 33) | 0.4999957 |
| a30 / a30_b | 21 | 18 / 2 | 19 | 7658 → 7658 (0 → 0) | 0.5000070 |
| a50 / a50_exterior | 12 | 0 / 2 | 14 | 13028 → 13028 (3 → 3) | 0.4999997 |
| a50 / a50_muster | 0 | 1 / 7 | 1 | 8142 → 8142 (9 → 9) | 0.5000007 |
| a50 / a50_hangar | 43 | 1 / 6 | 28 | 8783 → 8783 (1 → 1) | 0.5000004 |
| a50 / a50_control | 0 | 3 / 7 | 0 | 10095 → 10095 (39 → 39) | 0.4999864 |

The exact native ILP32 command and result are in
[`m2-step7-independent-collision-golden-qualification-2026-10-21.md:15-27`](m2-step7-independent-collision-golden-qualification-2026-10-21.md#L15):
`1 passed, 1 deselected, 2 package subtests` in 133.35 seconds using the
approved native route; sandbox execution was skipped on SIGSYS. The report
binds decompressed maps (`a30` SHA-256
`287959f34a7379a1dbec5fec15b4d94d17fe97ccd861f5c0c8fc80148b7ed293`, `a50`
`d7a3e80a86f2b0f23d855ce353aed3c0eb252145697797d87f25623dc470f38d`), HP2
packages (`ce38764fbba687bb26d4f2eb8a6cf066e19e4b8b81521d6f70f23ce8d00f183d`,
`9359e0eb09427b098d9773708352c77dbf426ebcec9d7b27400268d84221941a`), and
package manifest (`e4a9721846db228b88e6a563c34c0dccc7c6dc7694cf5a393d66c67ca004503b`)
([same report:80-101](m2-step7-independent-collision-golden-qualification-2026-10-21.md#L80)).
Current fixture hashes match the recorded identities: Python oracle/runner
`5e9f157d46f53adfa5ea8d1cff9300e73ffaf3873b02c4bf17f14e8ca02a40bb`, C fixture
`363adfd00e70f142102cef3ae5a9511ebd59385cd19100f08b9aa4c866c94adc`, retained
executable `9d5a068a7d9f6a80ca94926bfb37988d395aea88bd9288ccbf7b13f57fb2109f`,
and link map `bcc5ab6478db64b06a0f0b8373168be17f04928d12b221bb6956dd95a846ef79`.
The inspected CE collision source hashes also match the report.

The runner checks the source-map SHA against the audit manifest and the
package SHA against its row before parsing the package, derives oracle records
from the original map, then invokes the native fixture and requires a golden
line for each catalog BSP ([`test_hcu_scenario_bsp_switch.py:535-571, 785-820`](../../tests/test_hcu_scenario_bsp_switch.py#L535)).
This is good provenance and covers both map/package pairs. The report does not
retain a separate stdout/result JSON hash or host compiler version; those
would improve run-log reproducibility, but the linked binary/map, source hashes,
exact command, and fixed source/package identities provide a credible
qualification record.

## Exact scope, open cases, and recommendations

The new oracle selects only surfaces with `flags == 0`, valid material types,
an interior plane centroid, one raw polygon intersection, and a segment whose
far endpoint reaches the BSP's `NONE` solid boundary
([`test_hcu_scenario_bsp_switch.py:308-367`](../../tests/test_hcu_scenario_bsp_switch.py#L308)).
The CE call enables **front-facing only** ([`hcu_scenario_bsp_switch_main.c:1220-1223`](../../tests/hcu_scenario_bsp_switch_main.c#L1220)).
Therefore this demonstrates one isolated front-facing structure hit per BSP;
it does not test wrapper miss defaults, back-facing rejection/acceptance,
two-sided surfaces, edge/vertex/grazing or parallel cases, breakable/invisible
surface rules, object/media arbitration, all-map collision parity, runtime EE
capacity, PCSX2 gameplay, or rendering. The report accurately retains most of
these non-claims ([qualification report:105-117](m2-step7-independent-collision-golden-qualification-2026-10-21.md#L105)).

Recommended next acceptance increment: add an independently derived
world-bounds miss with expected public-wrapper defaults (`type NONE`, `t=1`,
locations NONE), then a reversed query over one of these same raw single-sided
faces with front-only flags, only after the source oracle verifies no other
polygon intersects either segment. Keep those as separate cases; do not infer
backface behavior from the current outward-boundary hit. Retain the existing
source-map/package identities and require unchanged BSP/publication snapshots.
Step 8 remains a prerequisite for target-side gameplay-map collision; this
host fixture's overprovisioned BSP storage is not PS2 memory evidence.

Halo-64 is not an oracle here. It is only useful as an architecture boundary
comparison; do not transfer its N64 collision cuts or capacity assumptions.
REA is not applicable because the implementation directly tests known CE
source with hash-bound retail BSP records rather than recovering unexplained
shipped-binary behavior.
