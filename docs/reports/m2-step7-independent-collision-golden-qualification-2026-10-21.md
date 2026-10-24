# M2 Step 7 — independent retail collision-golden qualification

## Result and limit

The Step 7 retail fixture now compares the real CE public structure-collision
query against collision expectations independently derived from the original
decompressed Xbox map bytes. The earlier fixture found a CE hit and used CE's
own polygon/traversal result as its expected tuple; that was useful wrapper
composition coverage but not an independent golden. The new raw-map oracle
decodes collision material, surface, plane, edge, vertex, structure-leaf, and
BSP3D records, then analytically computes the unique polygon intersection and
the raw-tree leaf locations. CE is the system under test only after those
expected values have been fixed by the source-map parser.

Approved native ILP32 command:

```sh
PYTHONPATH=.:submodules/halo-ps2/tools \
HALO_HCU_M2_PACKAGE_ROOT=/tmp/hcu-m2-capacity-repro.P5qdmI/packages \
HALO_HCU_M2_PACKAGE_MANIFEST=docs/reports/retail-cbsp-catalog-package-audit-e4a97218.json \
HALO_HCU_M2_RETAIN_LINK_ARTIFACTS=1 \
python3 -m pytest -q -rs tests/test_hcu_scenario_bsp_switch.py -k retail -x
```

Final run after independent review and raw-leaf bounds hardening: **1 passed,
1 deselected, 2 package subtests passed** in 132.46 seconds.
The ordinary sandbox run compiles but skips execution because the sandbox traps
the native ILP32 process with SIGSYS; the accepted run used the approved native
execution path. The run exercised both audited packages and every catalog BSP:
two BSPs in `a30`, four in `a50`.

## Independent oracle and CE assertion

[`test_hcu_scenario_bsp_switch.py`](../../tests/test_hcu_scenario_bsp_switch.py#L163)
reads each source BSP extent located through `halo2ps2.bsp.locate`, then bounds
every raw array against that extent. For each candidate surface it follows the
edge ring from serialized edge/vertex records, applies the surface's plane
designator orientation, and rejects malformed or non-convex rings. It
calculates the segment-plane parameter and point in Python double precision,
tests the point against every decoded polygon, and accepts only a unique
interior intersection with the candidate surface. The raw BSP3D tree is walked
separately to determine the starting leaf and the final non-solid leaf just
before contact; the structure-leaf records independently provide each cluster
index. The generated expectations are passed to the C fixture through a
temporary header, not checked into the repository as opaque constants.
The parser explicitly rejects a raw BSP3D leaf index outside the decoded
collision-leaf count before indexing the structure-leaf block. Independent
corroboration confirmed the oracle is separate from CE traversal, validated
the record layout and asserted result fields, and recommended this bounds
check; the final native rerun includes it
([`m2-step7-independent-collision-golden-corroboration-2026-10-21.md`](m2-step7-independent-collision-golden-corroboration-2026-10-21.md)).

[`hcu_scenario_bsp_switch_main.c`](../../tests/hcu_scenario_bsp_switch_main.c#L1015)
still retains the previous CE-derived probe as a separate smoke/composition
check. It additionally invokes the public CE
[`collision_test_vector()`](../../submodules/halo-ce-universal/source/physics/collisions.c#L478)
on each raw-source query with structure and front-facing tests enabled, then
asserts result type, surface/material indices, runtime material type, plane
designator/oriented plane, hit fraction, hit point, start and last-contact leaf
and cluster, unchanged full BSP bytes, unchanged breakable-surface flags, and
no call into any fail-closed object adapter. CE's wrapper feeds the production
[`collision_bsp_test_vector()`](../../submodules/halo-ce-universal/source/physics/collision_bsp.c#L1220);
it does not supply the expected values. This adds the complete public wrapper
path that the prior query audit lacked.

The independently generated raw geometry values are:

| Map / BSP | Surface | Material / runtime type | Plane designator | Start leaf → contact leaf (clusters) | t | Hit point (x, y, z) |
|---|---:|---:|---:|---|---:|---|
| a30 / 0 `a30_a` | 27 | 3 / 2 | 30 | 10733 → 10731 (33 → 33) | 0.4999957 | (42.865618, -118.573449, -40.374136) |
| a30 / 1 `a30_b` | 21 | 18 / 2 | 19 | 7658 → 7658 (0 → 0) | 0.5000070 | (-457.555536, 9.553990, -37.994494) |
| a50 / 0 `a50_exterior` | 12 | 0 / 2 | 14 | 13028 → 13028 (3 → 3) | 0.4999997 | (7.089246, 57.697401, 20.356023) |
| a50 / 1 `a50_muster` | 0 | 1 / 7 | 1 | 8142 → 8142 (9 → 9) | 0.5000007 | (10.505988, -10.928828, -23.296906) |
| a50 / 2 `a50_hangar` | 43 | 1 / 6 | 28 | 8783 → 8783 (1 → 1) | 0.5000004 | (27.402204, -35.605137, -34.310772) |
| a50 / 3 `a50_control` | 0 | 3 / 7 | 0 | 10095 → 10095 (39 → 39) | 0.4999864 | (2.730970, -62.778832, -14.204400) |

The C fixture asserts the oriented plane's four float components exactly
against the temporary raw-source golden; it checks `t` and the point within
`1e-4`. Start/contact leaves and their cluster indices are checked exactly.
Only the summary fields above are printed to pytest output; the full start,
vector, plane, raw source leaf, and point inputs are deterministically derived
on every run from the hash-checked source maps rather than maintained as a
second copied table.

## Artifact and source identities

| Input/artifact | SHA-256 |
|---|---|
| Parent source pin | `70e2ed0cf2145a45d23aa07414a3a88c05155d4c` |
| HCU source pin | `6933490b2d16bb1c637295b6a0f3880ba23a7d56` |
| halo-ps2 source pin | `71183bb0a9adc586cd267b2780c82bbc12cfd95b` |
| Package manifest `retail-cbsp-catalog-package-audit-e4a97218.json` | `e4a9721846db228b88e6a563c34c0dccc7c6dc7694cf5a393d66c67ca004503b` |
| a30 decompressed source map | `287959f34a7379a1dbec5fec15b4d94d17fe97ccd861f5c0c8fc80148b7ed293` |
| a30 HP2 package | `ce38764fbba687bb26d4f2eb8a6cf066e19e4b8b81521d6f70f23ce8d00f183d` |
| a50 decompressed source map | `d7a3e80a86f2b0f23d855ce353aed3c0eb252145697797d87f25623dc470f38d` |
| a50 HP2 package | `9359e0eb09427b098d9773708352c77dbf426ebcec9d7b27400268d84221941a` |
| Native ILP32 fixture executable | `9d5a068a7d9f6a80ca94926bfb37988d395aea88bd9288ccbf7b13f57fb2109f` |
| Native ILP32 fixture link map | `bb09fbb7a0a91296215ffb4e48c51e3c18c2e56b53afba1ca75ca9e5b94c3a87` |
| C fixture source | `363adfd00e70f142102cef3ae5a9511ebd59385cd19100f08b9aa4c866c94adc` |
| Python oracle/runner source | `f0311b56a5209cbe3f49e4d9685869f40e9b64350b9e0f13ee40adf019dfe9df` |
| CE `collisions.c` | `16581f812393db63428fcf426acaad33bebe0687393db4a7fc4febccc7ca45c3` |
| CE `collision_bsp.c` | `096debda0f9cdd62fa8b9981f040770e5e0dfbb8f6baa2f4a241ff0db00dde86` |

The executable and map are retained under
`build/m2-group-d-file-backed-transaction/`. The source maps and HP2 packages
are local, read-only test inputs; no retail data was staged or committed.

## What this closes and what remains

This closes the Step 7 source-backed **collision hit tuple** subcheck for these
six BSPs on the host ILP32 fixture: the public CE wrapper now agrees with
independently parsed retail geometry/material/tree data, while the loaded
materialized BSP image and breakable-surface state remain unchanged. It is
stronger evidence than the prior CE self-derived expected tuple.

It does not establish collision parity for every BSP/map or all segment
orientations, back-facing rejection, parallel/grazing/edge/vertex hits,
breakable or invisible-surface behavior, dynamic-object collision, EE
placement/capacity, PS2 device I/O, target timing, PCSX2 gameplay, or visible
rendering. In particular, the fixture intentionally installs aborting object
adapters and does not exercise player movement or game tick. Step 7 and overall
M2 remain partial; no campaign map is admitted by this host test.

## Relevant source ownership

HCU owns the authoritative collision query and result; the test's raw map
parser is an independent oracle, not a competing runtime collision system.
The PS2 side contributes only the package/cache materialization path under
test. Halo-64 is not used as a collision algorithm or memory-budget authority
for this result; its N64 collision cuts and capacities would not establish PS2
parity. REA was not used because this qualification examines source and
decompressed retail map records, not an opaque executable behavior.
