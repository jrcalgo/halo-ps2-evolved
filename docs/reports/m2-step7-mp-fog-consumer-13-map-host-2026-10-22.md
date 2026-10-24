# M2 Step 7 — stock multiplayer fog consumers (host ILP32)

Date: 2026-10-22. This report records a package-backed semantic check of the
retail CE fog-region consumers across the 13 stock multiplayer maps. It is
host ILP32 evidence only: it does not prove PS2 arena capacity, target runtime,
weather-particle rendering, or a playable/rendered map. Step 7 remains open.

## Result

The fixture now derives candidate fog cases independently from the raw retail
map BSPs, then executes the real CE `scenario_get_fog_region_index()` path on
the relocated CE BSP/tag data as part of each map load. The supported input
contains valid tagged fog-plane chains in exactly three maps: Beaver Creek
(ID 103), Chill Out (107), and Damnation (108). For each, the test verifies
the source-derived cluster, encoded reference, plane, region, fog palette/tag,
and expected region result on both sides of the plane. The ten remaining maps
have a raw `fog_reference == NONE` case; for each, CE must return `NONE` for
both the null-position and concrete-position query. BSP publication must
remain unchanged. The main fixture performs two load/unload cycles, so the
retained native run contains 6 valid plane rows (3 maps × 2) and 20 NONE rows
(10 maps × 2).

The raw inventory is intentionally not a hand-authored set of arbitrary
expected fog values. `retail_source_fog_plane_oracle()` follows the selected
source BSP and tag chain; `retail_source_fog_none_oracle()` bounds-checks the
source cluster block and accepts only an actual cluster whose field is
`NONE`. The generated inventory binds map ID, source-map digest, BSP/cluster
indices, encoded reference, plane values, region/palette selection and datum.
The Python integration requires the exact supported map sets, generates the
golden header, and checks the native output against every derived row.

Relevant implementations and source contract:

- [`tests/test_hcu_mp_capacity.py:20-24`](../../tests/test_hcu_mp_capacity.py#L20) fixes the 13-map fixture population and the three/ten observed fog-case groups.
- [`tests/test_hcu_mp_capacity.py:273-310`](../../tests/test_hcu_mp_capacity.py#L273) builds the per-map fog-plane/NONE source inventory and generated CE golden.
- [`tests/test_hcu_mp_capacity.py:580-613`](../../tests/test_hcu_mp_capacity.py#L580) requires the exact 6/20 cycle coverage and output equality; missing cases cannot silently pass.
- [`tests/test_hcu_scenario_bsp_switch.py:341-374`](../../tests/test_hcu_scenario_bsp_switch.py#L341) derives a NONE oracle from raw source cluster bytes with range validation.
- [`tests/hcu_scenario_bsp_switch_main.c:1297-1445`](../../tests/hcu_scenario_bsp_switch_main.c#L1297) exercises actual relocated plane and NONE consumers and verifies the active BSP remains published.
- CE's [`scenario_get_fog_region_index()` at `scenario.c:632-692`](../../submodules/halo-ce-universal/source/scenario/scenario.c#L632) defines the high-bit plane-reference decoding, bounds checks, location result, and `NONE` behavior. CE's underwater/weather path continues at [`scenario.c:694-741`](../../submodules/halo-ce-universal/source/scenario/scenario.c#L694).

## Source-derived coverage inventory

| CE fog input case | Stock MP maps | Source-derived case count | Runtime rows |
|---|---|---:|---:|
| Valid fog-plane → region → palette/tag chain | Beaver Creek (103), Chill Out (107), Damnation (108) | 1 selected case per map | 6 (two cycles each) |
| Cluster `fog_reference == NONE` | Blood Gulch (102), Boarding Action (105), Carousel (106), Hang ’Em High (109), Longest (101), Prisoner (104), Putput (110), Rat Race (111), Sidewinder (112), Wizard (113) | 1 selected case per map | 20 (two cycles each) |

Other clusters and references are not promoted into additional fog goldens by
this report. This is a deterministic representative query per map, not an
exhaustive assertion over every cluster/point. In particular, it does not
exercise bot perception via `scenario_fog_at_point()`, every fog boundary or
invalid reference, weather-particle simulation, SPU2 playback, or visible
fog rendering.

## Reproduction and exact evidence

The fixture is built by:

```sh
PYTHONPATH=.:submodules/halo-ps2/tools python3 -m pytest -q tests/test_hcu_mp_capacity.py
```

The sandboxed invocation builds the host ILP32 binary but native execution is
blocked there by SIGSYS. The exact retained binary was therefore run through
the approved native execution path with the asset root relative to the
repository (the fixture expects one root argument):

```sh
build/m2-mp-weather-wind-13/mp-weather-wind build/m2-mp-weather-wind-13/assets/
```

That run exited 0. Retained output ends with:

```text
mp-host-collision 13-map CE hit/PVS/reload matrix passed; target capacity not tested
```

The relevant output includes the expected 6 `fog-plane` and 20 `fog-none`
success rows. The binary also runs the existing all-13 host CE collision,
PVS, wind/weather selection, lifecycle/reload, and sound-environment checks;
those existing checks are not newly reinterpreted here as target evidence.

Exact artifacts:

- Parent / HCU / halo-ps2 pins: `70e2ed0cf2145a45d23aa07414a3a88c05155d4c` / `6933490b2d16bb1c637295b6a0f3880ba23a7d56` / `71183bb0a9adc586cd267b2780c82bbc12cfd95b`.
- Schema ELF: `build/m2-artifacts/schema-2fba411b-prior/halo-local.elf`, SHA-256 `2fba411b7244b20fdf31f0b1e540fc2b6f5598891f53a64f8b12f850a0cda0aa`.
- Retained executable `build/m2-mp-weather-wind-13/mp-weather-wind`, SHA-256 `6dc609aabd69a7df3292cd562c7801b45061c4dcfcbdd9433bccc4d97cb48353`.
- Link map `build/m2-mp-weather-wind-13/mp-weather-wind.map`, SHA-256 `d9f1a7bd4537ae0cdfa21af68de4603c64c0e5ad53f83444f080c30f03d2de08`.
- Generated fog goldens `build/m2-mp-weather-wind-13/hcu_fog_plane_golden.h`, SHA-256 `5113d1e222846877f84193d8b0c144733a8c3d3b05be1e0b648e55b9ffd825f5`.
- Raw-derived case inventory `build/m2-mp-weather-wind-13/mp_fog_source_inventory.json`, SHA-256 `8e77e0aa2ab121c5e9dbfbf0195589deae4d65dfa8cd285eeb041667a52da58e`.
- Native run log `build/m2-mp-weather-wind-13/native-run-fog-expanded.log`, SHA-256 `8c93ff91045af3ab322d24e37c494b996f5b64cb9c9bf822265e95e8b86ac934`.
- The test pins the source-map and package hashes for all 13 maps in [`tests/test_hcu_mp_capacity.py:25-66`](../../tests/test_hcu_mp_capacity.py#L25). Package generation is tied to the schema ELF above; the Damnation package record is validated against `build/m2-mp-wind-package/manifest.json`.

## Scope boundary / remaining work

This closes the fog-region/plane-query subcheck for representative raw-derived
cases across all 13 stock MP maps on the oversized host semantic fixture. It
does **not** close Step 7: collision edge/vertex and breakable diversity,
complete BSP field/consumer disposition, bot fog perception, geometry and
visibility paths, sound playback, and failure-atomicity still need their own
acceptance evidence. It also does **not** close Step 8: the fixture allocates
host-sized tag/BSP/claim/scratch capacities and its terminal marker explicitly
says target capacity was not tested. No EE/PCSX2 map-admission or rendering
claim follows from this run.
