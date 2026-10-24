# Step 7 multiplayer collision validation — MP hit and Prisoner slices implemented

## Handoff

Two implementation slices are complete: package-backed ordinary CE hits now
run for every stock multiplayer map, and Prisoner adds a source-derived
directional miss/reverse pair plus breakable set/clear/restore. The remaining
collision-specific gap in this slice is multiplayer edge/vertex topology (and
the other broader Step 7 consumer/failure gates). Do not spend another slice
extending the a30-only edge test: `a30` is not in the product's multiplayer
catalog. Keep the collision engine and public query under test in HCU; the
parent contributes only the real map/package loading path.

Prisoner was the focused validation case: its raw BSP contains 16 surfaces with
nonzero flags or breakable metadata. The native fixture proves the coplanar
surface group `[457, 2835]` (both `flags=9`, breakable index 1, material 9),
CE's selected surface 457, set->hit, clear->miss, and full-bitmap restore. The
source map SHA-256 is
`85ff2fdc117b7640bda85a490b30c662f2626bd6d0685e41832935422891c307`.

## Current evidence and precise gap

`tests/test_hcu_mp_capacity.py` now mounts all 13 stock multiplayer packages
and generates one independent raw-source collision golden for each source
BSP. The CE query checks hit type, surface, material index/type, plane
designator, start/contact leaf, and `t` (`tests/test_hcu_mp_capacity.py:64-143`,
`tests/hcu_mp_capacity_main.c:204-248`). All 13 map queries run in two
load/unload cycles, with explicit names/IDs and a hard assertion on 26 ordinary
CE hit queries (13 maps × 2 cycles; `tests/hcu_mp_capacity_main.c:251-378`).
Prisoner's directional and breakable checks are additional queries. The all-map hit coverage does
not itself exercise an edge/vertex tie, invisible-surface filtering on an MP
map, or a breakable transition on every flagged MP topology; Prisoner is the
separate breakable exception below.

The stronger current miss/backface/edge/flagged fixtures live in
`tests/test_hcu_scenario_bsp_switch.py` and
`tests/hcu_scenario_bsp_switch_main.c`, but the extended miss/backface golden
is special-cased to `a50_muster`; shared-edge and invisible/breakable query
generation/assertions are special-cased to `a30_a` (Python oracle at
`tests/test_hcu_scenario_bsp_switch.py:1010-1172`, CE checks at
`tests/hcu_scenario_bsp_switch_main.c:789-1010`). Those prove useful CE behavior
on those source maps, but not the multiplayer-only map set.

The existing all-map raw hit oracle already succeeds on every multiplayer map.
The command below reported exactly one BSP and a source-derived hit candidate
for each of the 13 maps:

| Map | Surface / material / starting leaf |
|---|---:|
| Beaver Creek | 39 / 0 / 178 |
| Blood Gulch | 84 / 0 / 5307 |
| Boarding Action | 14 / 1 / 105 |
| Carousel | 16 / 0 / 692 |
| Chill Out | 1 / 2 / 745 |
| Damnation | 7 / 1 / 311 |
| Hang 'em High | 0 / 4 / 1040 |
| Longest | 0 / 0 / 163 |
| Prisoner | 0 / 4 / 745 |
| Putput | 0 / 2 / 1334 |
| Rat Race | 0 / 0 / 235 |
| Sidewinder | 69 / 10 / 4853 |
| Wizard | 0 / 4 / 251 |

All 13 rows now have CE host-fixture execution. This remains host ILP32
semantic evidence, not target memory evidence, and it does not prove every
collision topology is covered. The hit selection is intentionally a single
ordinary `flags==0` source-derived case; selected surface IDs often being
small is not evidence of a geometry defect, but it emphasizes why the oracle
must report its selection rule and prove uniqueness.

## Prisoner implementation and evidence

The raw-source oracle in `tests/test_hcu_scenario_bsp_switch.py` now requires
the ordinary hit candidate to be selected by the source-serialized leaf
BSP2D reference/tree (`ce_leaf_surface`) in addition to unique full-polygon
intersection and BSP3D traversal. This was necessary because a mathematically
valid raw polygon contact alone is not sufficient evidence that CE's leaf
reference path can reach that surface. The oracle also opts into Prisoner's
same-leaf directional miss/reverse pair and derives a flagged case only after
fully decoding all surfaces, finding a coplanar, same-material, same-breakable
group, independently walking BSP3D and BSP2D, and requiring CE's source-side
selection algorithm to choose a member of that group.

Prisoner's breakable candidates are duplicate/coplanar topology, not a unique
single-surface hit: the full raw segment intersects surfaces 457 and 2835 at
the same point/parameter. Both are flagged (`flags=9`), share material 9 and
breakable index 1, and their plane designators represent opposite orientations
of the same plane. The CE-selected surface for the generated ray is 457.
Accordingly, the C test asserts the complete group and validates CE's chosen
member, rather than falsely claiming that surface 457 is the only raw contact.

The independent directional case is based on the ordinary source hit on
surface 0/material 4. The generated short miss starts at source-derived
`(2.3499986, -1.9000012, 0.0924993)`, moves +Z by 0.25, stays inside empty leaf
745 / cluster 0, and intersects no decoded source surface. The reverse ray
traverses from outside/solid toward the empty leaf: CE front-only rejects and
back-only accepts the expected surface, preserving CE's empty-leaf recording
semantics.

The package-backed native ILP32 fixture loads Prisoner as map ID 104 in both
lifecycle cycles of the full 13-map matrix. For breakable index 1, its initially-zero state is
asserted; setting the bit yields CE hit surface 457 with expected material,
flags, index, and `t`; clearing it yields a miss; restoring the complete saved
bitmap restores the initial miss behavior. The full bit-vector and loaded BSP
image are byte-for-byte unchanged after restoration/query; published map/BSP
identity remains stable. The fixture also calls the Prisoner CE sound
environment selector when it has a source golden. Relevant implementation
points: oracle generation and candidate criteria at
`tests/test_hcu_scenario_bsp_switch.py:558-1015` and
`:1181-1295`; generated header group encoding at `:1410-1435`; CE fixture at
`tests/hcu_mp_capacity_main.c:40-203`; package and manifest setup at
`tests/test_hcu_mp_capacity.py:64-143` and `:290-420`. CE breakable filtering
is implemented at
`submodules/halo-ce-universal/source/physics/collision_bsp.c:1398-1416` and
`:2253-2288`; this validation does not modify gameplay code.

Reproduction command, executed outside the sandbox because native ILP32
execution is restricted there:

```sh
python3 -m unittest discover -s tests -p test_hcu_mp_capacity.py
```

Result: `Ran 1 test in 68.410s — OK` (native ILP32 execution). Retained output shows
`collision-directional-golden map=104 ... status=passed` and
`collision-breakable-group map=104 surfaces=457,2835 selected=457 index=1
status=passed` in both cycle 0 and cycle 1. All 13 maps print one successful
`mp-host-map` row in each of the two cycles. The fixture uses host-only
16 MiB tag, 8 MiB BSP, 4 MiB claims, 1 MiB map-owner, and 512 KiB scratch
arrays; the run manifest explicitly says this is not PS2/EE target capacity
evidence, so it does not close Step 8.

The full matrix identity and retained artifacts are in
`build/m2-mp-host-13-collision/`:

| Artifact/input | SHA-256 |
|---|---|
| Schema ELF used by the pinned offline conversions | `2fba411b7244b20fdf31f0b1e540fc2b6f5598891f53a64f8b12f850a0cda0aa` |
| Generated all-map CE collision golden header | `2b1b9f536114042023f0ab3c5f49c35faa22d8743595175953dfb706739a234a` |
| Generated all-map PVS header | `a83a8f3bad807aee766619e44f08e5fa8e3089fd4d8486f4cae3304036db6ffa` |
| Native ILP32 fixture executable | `1e0c7b0196ced223d2ff38b036d2a28e800f6a0a00df1ac518eb884f36f87f80` |
| Link map | `a7470f856f0acde0731506a1dbbcdf416e21e6bc4ec0a10c67756074c271f377` |
| Run manifest | `beaf128bf00e30fc64bb93a1dd556b95a0492acd5519faf20fa85fa4332461d2` |

Package command:

```sh
python3 tools/pack_retail_ctag_hp2.py \
  build/retail-maps/decompressed/prisoner.map \
  build/m2-artifacts/schema-2fba411b-prior/halo-local.elf \
  build/m2-mp-extra/prisoner-all-bsps.hp2 --include-all-bsps
```

The test hard-fails if any of the 13 source maps, package hashes, the schema
ELF, or the retained Damnation package record is missing or differs from its
audited value (`tests/test_hcu_mp_capacity.py:36-109`). The manifest binds all
13 source-map and package hashes, the shared schema hash, parent/HCU/halo-ps2
pins, relevant source/generated TU hashes, host-only capacities, ELF, and link
map. Damnation uses the separate validated wind-enabled package record at
`build/m2-mp-wind-package/manifest.json`; its source map and schema hashes are
also asserted. Package schema ELF is an offline converter input, not the CE
executable under test. Do not treat generated package presence as target
placement proof.

## Implementation sequence

1. **Generalize flagged-candidate derivation without weakening it.** Completed
   for the opt-in Prisoner breakable group (not yet generalized to other maps).
   The source oracle requires complete polygon coverage and exact source-side
   BSP3D/BSP2D candidate selection. The existing a30 path is preserved.
   Further generalization remains open. Refactor
   the `location.path == "levels\\a30\\a30_a"` branch in
   `retail_source_collision_goldens()` into explicit opt-in source-oracle
   helpers. Retain its existing raw-polygon uniqueness check, BSP3D traversal,
   CE-matched BSP2D reference selection, and bounds failures. Do not use CE's
   returned hit as the expected value. The current parser and helper functions
   are in `tests/test_hcu_scenario_bsp_switch.py:558-817`; the a30-only flagged
   derivation begins at `:1010`.
2. **Qualify one MP breakable on Prisoner.** Completed in native ILP32.
   Exact selected surface 457 and coplanar duplicate group [457,2835],
   material 9, flags 9, breakable index 1; CE set->hit, clear->miss, restore
   full original bitfield->original miss, plus BSP/global immutability passed.
   The original planned criteria were to search flagged polygons, accept
   a candidate only if every raw surface needed for the no-hit proof decoded,
   the source ray has exactly one in-range polygon contact, the source BSP3D
   reaches an empty-to-solid transition, and `ce_leaf_surface()` selects the
   same flagged surface. Prefer surface 457 only if those tests prove it; its
   flag/index tuple makes it a useful nonzero-index candidate. Emit the
   expected surface/material/plane/flags/index/leaf/cluster/t/point into the
   generated header. In C, query once with the bit set and again after clearing
   it; assert hit then miss, expected miss defaults/locations, unchanged map
   image and global BSP publication, unchanged cursor/ownership, and exact
   restoration of the full breakable bitmap. CE's filtering is at
   `submodules/halo-ce-universal/source/physics/collision_bsp.c:2253-2288`;
   the existing test pattern is `tests/hcu_scenario_bsp_switch_main.c:950-1004`.
3. **Add a source-proven directional miss for the MP case.** Completed for
   Prisoner: same-empty-leaf no-contact miss and reverse front-reject/back-hit
   passed. The original planned procedure was to generate a short
   same-empty-leaf segment that intersects no complete decoded source polygon,
   then assert public `collision_test_vector()` false-result defaults plus
   exact leaf/cluster results. Optionally reverse the proven Prisoner hit and
   assert front-only reject/back-only accept; preserve the distinction that CE
   returns before recording an empty leaf on the reverse backface path.
4. **Promote simple hit coverage to the full 13-map inventory.** Completed in
   the host semantic fixture. `tests/test_hcu_mp_capacity.py:36-109` hard-fails
   on missing/changed source, package, and schema hashes; it generates one
   source/CE-BSP2D-selected golden per map. The CE lifecycle loop at
   `tests/hcu_mp_capacity_main.c:251-378` ran all 13 packages in two cycles and
   asserted 26 successful map result records. Source/package/schema/pin hashes
   and generated file hashes are retained in
   `build/m2-mp-host-13-collision/manifest.json`. This is a semantic host run
   using 16/8 MiB tag/BSP arrays, not production-capacity or PS2 RAM evidence.
5. **Add multiplayer topology breadth as a separate acceptance set.** Still
   open. Derive one shared-edge pair and one vertex/grazing case from a
   multiplayer BSP. Assert two offset rays with unique expected
   face/material/plane/leaf tuples; make an exact tie diagnostic-only unless
   float32 and BSP2D tie routing establish a stable source expectation. Also
   exercise multiplayer invisible-surface filtering; a30-only cases remain
   non-MP comparators. The current a30 derivation explains the tie constraint
   at `docs/reports/m2-step7-edge-grazing-candidate-revalidation-2026-10-21.md:17-30`.

## Reproduction and source audit performed

The report-only raw inventory was run from the repository root with:

```sh
PYTHONPATH=tests:tools:submodules/halo-ps2/tools python3 - <<'PY'
from pathlib import Path
from test_hcu_scenario_bsp_switch import retail_source_collision_goldens
from halo2ps2 import bsp, mapinfo, tagindex
from ctag_schema_walk import read_xbox_tag_region
root = Path('build/retail-maps/decompressed')
maps = ('beavercreek','bloodgulch','boardingaction','carousel','chillout',
        'damnation','hangemhigh','longest','prisoner','putput','ratrace',
        'sidewinder','wizard')
for name in maps:
    path = root / f'{name}.map'
    header = mapinfo.read_header(path)
    tag_region, _, _ = read_xbox_tag_region(path)
    bsps = bsp.locate(tagindex.TagIndex.read(path), tag_region,
                      header.decompressed_size)
    goldens = retail_source_collision_goldens(path, len(bsps))
    print(name, 'bsps', len(bsps), 'goldens',
          [(row['bsp_index'], row['surface_index'], row['material_index'],
            row['leaf_index']) for row in goldens])
PY
```

Result of this initial raw inventory: all 13 source maps parsed, one BSP each,
and one source hit golden each. A second bounded raw surface-header scan found
the Prisoner flagged records later proven by the native fixture above. The
subsequent execution was:

```sh
python3 -m unittest discover -s tests -p test_hcu_mp_capacity.py
```

It passed outside the sandbox as native ILP32 (`Ran 1 test in 68.410s — OK`).
The run compiled and executed the HCU CE collision query against all 13
package-backed maps in two load/unload cycles, yielding 26 successful ordinary
map hit queries, plus the Prisoner miss/breakable and applicable PVS/sound/fog
checks. Retained output is `build/m2-mp-host-13-collision/run.log`.
The source identities for all 13 decompressed maps are available in the local
audit output/worktree; additionally, `sidewinder.map` is SHA-256
`995561a68c8c5b142f13f1967730ce8c08d4f0db9574db8e987d915f2b118dcc` and is
the largest multiplayer BSP capacity case, while `prisoner.map` is SHA-256
`85ff2fdc117b7640bda85a490b30c662f2626bd6d0685e41832935422891c307`.

## Ownership and interpretation

HCU `collision_test_vector()` and its CE collision-BSP traversal remain the
gameplay authority. The parent/halo-ps2 side only mounts and materializes
source-backed map data. Do not add a second parent collision answer to make
the fixture pass. Step 8's unresolved production-sized capacity and all-map
high-water remain prerequisites for target-sized Step 7 collision evidence;
host ILP32 success cannot close that dependency.

Halo-64's `source/physics/collision_bsp.c` and
`source/physics/breakable_surfaces.c` are useful structural comparators for
how the same source families are wired. They are not collision or breakable
behavior authority for this port: compare expected behavior to CE source and
the retail Xbox map bytes, not N64 cuts, timing, or limits. REA is not
applicable to this concrete gap because the relevant CE source and decompressed
retail collision records are inspectable; use REA only if later evidence
requires explaining opaque retail executable behavior not specified by those
sources/tags.

## Priority decision

Prisoner breakable + directional miss and ordinary hit cases for all 13 maps
are complete in the host semantic fixture. Next, add a multiplayer shared-edge
/ vertex topology and MP invisible-surface case with independent source
expectations. Do not claim Step 7 complete from these host fixtures: all
relevant BSP consumers, failure atomicity, wider topologies, and Step 8 target
placement/capacity evidence remain separate gates.
