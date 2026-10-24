# Step 7 MP shared-edge collision parity — CE runtime evidence

## Result

The previous candidate-blocker report said no stock multiplayer pair had yet
completed both source-side routing checks and an actual CE query. This follow-up
closes that specific gap: one same-material adjacent pair is now independently
qualified on each of the 13 stock multiplayer BSPs, and CE's
`collision_test_vector()` returned each face on its own strictly interior ray.
Each map was loaded twice in the same ILP32 process, so the runtime log contains
52 successful per-face assertions (13 maps × 2 faces × 2 load cycles). Exact
edge-tie, vertex-tie, and grazing checks also passed twice on Beaver Creek.

This is host ILP32 semantic evidence for the CE collision path—not EE timing,
target-RAM, renderer, multiplayer-match, or PS2 acceptance. It closes only the
shared-edge-pair subcheck; Step 7 remains open for its other consumer, failure,
and target-sized requirements.

## Source oracle and pair selection

`tools/audit_mp_collision_edge_pairs.py` parses the raw decompressed Xbox BSP
blocks rather than converted HP2 collision output. Its surface decoder follows
the serialized edge ring, reads float32 vertices/planes and materials, and
rejects malformed or flagged faces. For each candidate pair it independently
requires both offset rays to have exactly one polygon hit across the decoded
surface set, checks the contact lies strictly within the target polygon,
traverses raw BSP3D from a non-solid start leaf to the empty endpoint, and
follows that leaf's BSP2D reference/tree to the expected face. See the edge
ring and source traversal in
[`audit_mp_collision_edge_pairs.py:85-160`](../../tools/audit_mp_collision_edge_pairs.py#L85),
candidate qualification at
[`audit_mp_collision_edge_pairs.py:175-293`](../../tools/audit_mp_collision_edge_pairs.py#L175),
and the test runner's all-map source case selection at
[`test_hcu_mp_collision_edge.py:30-60`](../../tools/test_hcu_mp_collision_edge.py#L30).

| Map ID | Multiplayer map | Adjacent surface pair | CE selected surfaces (both qualified sides) | Source start leaves |
|---:|---|---:|---:|---:|
| 101 | Longest | 2 / 35 | 2, 35 | 249, 249 |
| 102 | Blood Gulch | 84 / 164 | 84, 164 | 5307, 5102 |
| 103 | Beaver Creek | 39 / 94 | 39, 94 | 546, 178 |
| 104 | Prisoner | 0 / 1487 | 0, 1487 | 133, 133 |
| 105 | Boarding Action | 16 / 56 | 16, 56 | 1937, 1937 |
| 106 | Carousel | 21 / 189 | 21, 189 | 922, 922 |
| 107 | Chill Out | 1 / 129 | 1, 129 | 773, 773 |
| 108 | Damnation | 7 / 62 | 7, 62 | 311, 311 |
| 109 | Hang 'em High | 0 / 10 | 0, 10 | 981, 981 |
| 110 | Putput | 4 / 926 | 4, 926 | 124, 124 |
| 111 | Rat Race | 2 / 190 | 2, 190 | 141, 141 |
| 112 | Sidewinder | 85 / 111 | 85, 111 | 2154, 2154 |
| 113 | Wizard | 2 / 3 | 2, 3 | 294, 294 |

For every row, each side is a separate query with its own face's serialized
plane, float32 contact, expected `t`, material index/type, plane designator,
and source leaf. The source inventory JSON contains the complete tuples and
source map SHA-256 values:
[`build/mp-collision-shared-edge-source-oracle.json`](../../build/mp-collision-shared-edge-source-oracle.json)
(SHA-256 `ff26f43f8e474f59397c441d246b93e3a45f39fdaefca555d5eb7e3bfb54b95a`).
The generated CE golden is
[`hcu_mp_edge_golden.h`](../../build/m2-mp-edge-runtime-1792688142371578057/hcu_mp_edge_golden.h)
(SHA-256 `0ae099356b7a1bd63f89baa5a32aa13c95845f51a108f10ebf65e06297c09950`).

## CE fixture and exact runtime run

The generated fixture inserts `assert_mp_shared_edge()` into the existing
package-backed CE 13-map lifecycle test; it calls the retail CE entry
`collision_test_vector()` with structure and front-facing flags and asserts hit
kind, selected surface membership in the adjacent pair, material index/type,
plane designator, start leaf, and intersection parameter. The assertion and
placement are in
[`test_hcu_mp_collision_edge.py:121-148`](../../tools/test_hcu_mp_collision_edge.py#L121)
and [`test_hcu_mp_collision_edge.py:219-230`](../../tools/test_hcu_mp_collision_edge.py#L219).
The base fixture performs `scenario_load`, runs `mp_query`, rejects an
unsupported a30 preflight without disturbing the active-map snapshot, then
unloads and repeats for each MP map; see
[`hcu_mp_capacity_main.c:431-460`](../../tests/hcu_mp_capacity_main.c#L431).
CE initializes and returns collision results through
[`collisions.c:478-545`](../../submodules/halo-ce-universal/source/physics/collisions.c#L478),
while the BSP traversal records its face, plane, material, and path leaf in
[`collision_bsp.c:2126-2302`](../../submodules/halo-ce-universal/source/physics/collision_bsp.c#L2126).

Exact run command (native ILP32 execution must be outside a sandbox that
returns `SIGSYS`):

```sh
build/m2-mp-edge-runtime-1792688142371578057/retained/mp-weather-wind-location \
  build/m2-mp-edge-runtime-1792688142371578057/retained/assets/
```

The run exited 0 and ended with
`mp-host-collision 13-map CE hit/PVS/reload matrix passed; target capacity not
tested`. The retained complete log is
[`native-run-passed.log`](../../build/m2-mp-edge-runtime-1792688142371578057/retained/native-run-passed.log)
(SHA-256 `7d3380918f4621ae7047b78d0fdc9d3b808698027d2b10cab41f7beccced76f3`);
the executed binary SHA-256 is
`015c2905a430ab9881177f5e861110fb90b147603d3cbc1364f6fee64904981b`, and its
link-map SHA-256 is
`665d9bf9d978599dd8139ccaa13577c1f628e3facc5b8c4cfdd7f043937047e7`. It emits
four shared-edge pass rows per MP map (two faces, twice loaded); Beaver Creek
also emits edge/vertex/grazing pass rows on each load cycle.

The reproducible source generator is
[`tools/test_hcu_mp_collision_edge.py`](../../tools/test_hcu_mp_collision_edge.py)
(SHA-256 `11f715e0cf22a63dac00750194f7233967c318e8956faa890aa7a085756aaa85`);
the raw source audit is
[`tools/audit_mp_collision_edge_pairs.py`](../../tools/audit_mp_collision_edge_pairs.py)
(SHA-256 `f59b1ed39ebd764ad28a8868039359930415700ea135d195950b1d4cc83396e3`).
The all-map runner's ordinary sandbox invocation can report its native test as
skipped because the sandbox kills ILP32 with SIGSYS; that skip is not the
passing result cited here. The cited result is the successful direct execution
above, with its own retained log and binary hash.

## Provenance and interpretation

The generated runner manifest is
[`manifest.json`](../../build/m2-mp-edge-runtime-1792688142371578057/manifest.json)
(SHA-256 `ccb8dd1ab88a352f47baa4277deab2324ddf91ba0c708b62700984415c6d7a08`).
It records the per-map source hashes and pins: parent `70e2ed0cf2145a45d23aa07414a3a88c05155d4c`,
halo-ce-universal `6933490b2d16bb1c637295b6a0f3880ba23a7d56`, and halo-ps2
`71183bb0a9adc586cd267b2780c82bbc12cfd95b`. The separately executed binary,
link map, and log hashes above bind the runtime result to that generated
fixture; the manifest's `runner_exit_code` describes the wrapper's sandbox
run, not the successful native execution.

Halo-64's [`port/n64/NOTES.md:194`](../../submodules/halo-64/port/n64/NOTES.md#L194)
mentions counting `collision_test_vector()` calls for performance diagnostics.
That is only a useful instrumentation comparison: Halo-64 is not used as the
collision semantic oracle; the retail serialized BSP plus CE's own query
implementation are the authorities here.

## Limits and next Step 7 work

This result specifically resolves the prior report's missing fully qualified
MP pair. It does not prove geometry/material sound occlusion, invisible-face
filter behavior (the prior audit found no invisible-flagged surface in the
stock 13-map set), collision failure atomicity, query behavior at production
PS2 BSP capacities, or EE performance. It also does not validate player
capsule/vehicle collision at the shared edge. Keep those checks open and keep
M2 map admission closed pending the independent Step 8 capacity evidence.
