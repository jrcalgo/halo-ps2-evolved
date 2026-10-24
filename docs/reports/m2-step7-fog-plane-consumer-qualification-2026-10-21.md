# Step 7 fog-plane consumer qualification

Status: one source-backed, package-backed host ILP32 subcheck passed. This is
not Step 7 completion, target-sized evidence, map admission, or a rendering
result.

## Scope and source contract

The fixture executes CE's production `scenario_get_fog_region_index()` and
`scenario_location_underwater()` against a BSP materialized through the real
CTAG/CBSP and PS2-cache transaction. CE interprets a cluster `fog_reference`
with bit 15 set as an index into `fog_planes`; the plane names a fog region,
whose fog palette reference resolves the fog tag. With a position, CE tests
the plane distance (and includes the fog tag's `plane_distance` when its
underwater flag is set). Weather comes from the fog region first and falls
back to the cluster when the region's value is `NONE`; invalid weather indices
are normalized to `NONE`. See
[`scenario.c:619-741`](../../submodules/halo-ce-universal/source/scenario/scenario.c#L619)
and the CE record definitions and layout assertions in
[`structure_bsp_definitions.h:145-166`](../../submodules/halo-ce-universal/source/structures/structure_bsp_definitions.h#L145).

The Python oracle decodes only raw Xbox map BSP bytes, bounds each block by its
source BSP extent, and selects only a cluster whose full reference chain is
valid. It does not infer a candidate from relocated pointers or generated
package values. Compile-time fixture assertions pin the CE record sizes and
the BSP field offsets before the native test is built. The fixture then checks
that the relocated cluster, plane coefficients, region, palette entry, fog
datum, and weather result match the raw-source oracle; it queries the
position-independent region result, a point safely on the negative side, and
the opposite side of the actual source plane. It also calls CE's water-depth
accessor on both sides, checking the signed depth (or `REAL_MIN` for a
non-water fog tag), and verifies the published BSP identity and collision-user
depth are unchanged.

## Audited candidate and result

The oracle selects the first valid chain in each BSP. In the audited map set,
that selection yields exactly one fixture candidate:

| Map/BSP | Cluster | Encoded reference | Plane | Region | Fog palette/datum | Region weather | Cluster fallback | CE weather |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| `a30` / `a30_a` (BSP 0) | 0 | `-32767` (`0x8001`) | 1 | 0 | 0 / `-304804769` | `NONE` | 1 | 1 |

The plane is `(0, 0, 1, 23.405229568)`. The `a50` exterior, muster, hangar,
and control BSPs have no valid high-bit fog-plane → region → nonempty fog-tag
chain in the audited source data. The test therefore does not fabricate
coverage for them. For `a30` BSP 0, the actual CE calls pass against the first
raw-source-derived chain; this does not count or exercise every chain in that
BSP. Water/underwater is checked against the resolved CE fog tag's flag at
runtime; this field's tag payload is not independently decoded by this BSP
oracle.

The approved native ILP32 test result was **1 passed, 1 deselected, 2 package
subtests passed in 135.27 s**. The deselected test is outside the `-k retail`
selection. The final accepted run was:

```sh
APPIMAGE_EXTRACT_AND_RUN=1 \
PYTHONPATH=.:submodules/halo-ps2/tools \
HALO_HCU_M2_PACKAGE_ROOT=/tmp/hcu-m2-capacity-repro.P5qdmI/packages \
HALO_HCU_M2_PACKAGE_MANIFEST=docs/reports/retail-cbsp-catalog-package-audit-e4a97218.json \
HALO_HCU_M2_RETAIN_LINK_ARTIFACTS=1 \
python3 -m pytest -s -q -rs tests/test_hcu_scenario_bsp_switch.py -k retail -x
```

The native process required approved execution because sandboxed ILP32
execution can terminate with SIGSYS. The run passes host ILP32 code, not the
R5900 or PCSX2 guest. It uses 16 MiB tag storage and 8 MiB BSP storage, so it
is not proof against the PS2 production arena budgets.

## Reproducibility identities

- Parent checkout: `70e2ed0cf2145a45d23aa07414a3a88c05155d4c` (worktree dirty).
- HCU submodule: `6933490b2d16bb1c637295b6a0f3880ba23a7d56` (worktree dirty).
- halo-ps2 submodule: `71183bb0a9adc586cd267b2780c82bbc12cfd95b`.
- `scenario.c` SHA-256: `22aef8353c6f4a1067d0e51e78565783d5f7c911e3b4d73f40ad49269a2546c0`.
- BSP definitions header SHA-256: `dde75cddffc975c95395f525b60e5d125b5904beb106a3916dccbc295c26afe2`.
- Python test/oracle SHA-256: `14af200645ea1f935a29123d10b45c2b7741bb0c7ac47b755d749ef1d9c7060d`.
- C fixture SHA-256: `ea81d7507a148a22fff56c77fcedc944b8a2faa507773862add9879d8e16a20f`.
- Retained native executable SHA-256: `7f5efb8aec56e7694406b14f0cba134f67b22eadbc0bdda80667ec29489eebcb`.
- Retained link map SHA-256: `fe1b96a4688c5a01dbadafd507867aa4a9da7d387d7a6a2560d67aab8d4f525f`.
- Generated raw-source golden header SHA-256: `ac05e8c5e874a07995a94c6c2629a3b89c450d73b478f032f61db9e5519eeee9`.
- Raw `a30.map` SHA-256: `287959f34a7379a1dbec5fec15b4d94d17fe97ccd861f5c0c8fc80148b7ed293`.
- Raw `a50.map` SHA-256: `d7a3e80a86f2b0f23d855ce353aed3c0eb252145697797d87f25623dc470f38d`.
- `a30.hp2` / `a50.hp2` SHA-256: `ce38764fbba687bb26d4f2eb8a6cf066e19e4b8b81521d6f70f23ce8d00f183d` / `9359e0eb09427b098d9773708352c77dbf426ebcec9d7b27400268d84221941a`.
- Package audit manifest SHA-256: `e4a9721846db228b88e6a563c34c0dccc7c6dc7694cf5a393d66c67ca004503b`.

## Limits and next work

This qualifies one selected fog-plane chain, its weather fallback, the
position-sensitive region boundary, and selected water-depth checks only. It
does not cover fog-region priority/arbitration, every fog chain, all
`scenario_location_water_depth` cases, weather simulation/particle consumers,
BSP fog rendering, malformed-reference failure atomicity, all retail maps,
audio playback, PS2 target arena capacity, or EE performance. It does not
demonstrate that fog or weather BSP payloads
can be stripped. Continue Step 7's remaining field/consumer inventory, collision
topology and rollback cases, and target-sized consumer checks after Step 8
capacity evidence is available. Step 7 and Step 8 remain open.
