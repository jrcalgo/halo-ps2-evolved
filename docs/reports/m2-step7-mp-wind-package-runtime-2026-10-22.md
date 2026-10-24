# Step 7 MP weather/wind package runtime fixture

Status: package generation, native ILP32 compile/link, and native fixture execution pass when run outside the default sandbox seccomp policy. This closes the Damnation package-backed host-runtime slice only; it is not target EE or all-map evidence.

## Fixture and evidence

`tests/test_hcu_mp_wind_package.py` builds a complete HP2 package from retail Damnation, then compiles a dedicated host-ILP32 fixture in `tests/hcu_mp_wind_package_host32.c`. It loads the package through the production map-service/CTAG/CBSP path, relocates the BSP, inspects the actual relocated weather palette and cluster references, and links the real CE `scenario/wind.c`, `math/random_math.c`, and scenario/map lifecycle code. It then calls `wind_initialize_for_new_map`, `wind_update`, `scenario_get_current_from_weather_palette`, and `scenario_get_wind`; expected vectors are computed independently from raw retail tag/BSP data.

The runner makes only temporary copies of the map service and fixture glue to admit Damnation in the existing host-only diagnostic path. No production gameplay/source file or shared collision/lifecycle fixture was changed. The isolated host TU delegates the external spline call to the exact CE header inline body, as the existing wind-consumer fixture does. It also links the pinned CE `real_math.c`/geosphere implementations and existing real-math host adapter; this matters because an earlier minimal normalization shim generated NaNs in the geosphere direction table and was not valid runtime evidence. The wind algorithm, random math, spline body, and direction-table source path are CE code; host linkage adapters remain test-only.

Command:

```sh
python3 -m pytest -q tests/test_hcu_mp_wind_package.py -s
```

The default sandbox run returns SIGSYS (`-31`/`159`) at native ILP32 execution, so the runner reports a skip there. The exact same fixture was then run outside seccomp:

```text
python3 -m pytest -q tests/test_hcu_mp_wind_package.py -s
.                                                                        [100%]
1 passed in 8.26s
```

The guest-equivalent fixture result was `ce-mp-wind map=damnation bsp=0 palette_count=2 cluster_count=12 wind_tag=e84f06d9 none_entry=zero current=-0.29173657,-0.21807766,0.096514143 repeat=stable relocated=passed status=passed`. The link map has a defined local `wind_uniform_cubic_spline_vector3d_inline` and no weak undefined external spline symbol. Retained artifacts are `build/m2-mp-wind-package/manifest.json`, `damnation-all-bsps.hp2`, `mp-wind`, `mp-wind.map`, and `run.log`.

Runtime artifact hashes from the passing run:

- ILP32 executable SHA-256: `d1aab1b62d0795f771ad7b16e69a4502c3739c6ffe69ce20b5cd9337916b5463`
- Link map SHA-256: `c91fc222f2ad2badd5f16949f7e2961ba7a4d16814e4404a27c607b6b06b6780`
- Run log SHA-256: `de74b793b2911e0593bf525980c23af6ec861f3e888d8f0fe1b2b2a5483212b7`
- Package SHA-256: `ca41445cc9560035910fbc8c2fc7130175b707b1df2e8e51734d208c4ee2076d`

After the final manifest fix and verification rerun (`1 passed in 8.03s`), the comprehensive retained manifest binds `run_returncode: 0`, `execution_status: 0`, exact `run_stdout` and `run_stderr`, plus the executable/map/log hashes listed above.

The original failure was a weak unresolved `uniform_cubic_spline_vector3d` call: CE's `wind.c` preamble imports the inline body under `wind_uniform_cubic_spline_vector3d_inline`, but the reconstructed body calls the ordinary spelling. The temporary wind TU now redirects just that call to the included CE inline. A follow-on NaN exposed an incomplete host geometry shim (NaN CE geosphere points); replacing it with the same real CE math/geosphere source closure used by `tests/test_hcu_wind_consumer.py` made the lookup table finite and restored oracle agreement. No expected values or CE production semantics were changed.

## Pinned inputs and raw Damnation facts

- Parent commit: `70e2ed0cf2145a45d23aa07414a3a88c05155d4c`
- halo-ce-universal commit: `6933490b2d16bb1c637295b6a0f3880ba23a7d56`
- halo-ps2 commit: `71183bb0a9adc586cd267b2780c82bbc12cfd95b`
- Decompressed retail map SHA-256: `87bd92c1821ff20bed03c559d7be5ac43baeb44aa68342ffdbb5a8cd978f711c`
- Schema ELF SHA-256: `2fba411b7244b20fdf31f0b1e540fc2b6f5598891f53a64f8b12f850a0cda0aa`
- Generated complete-BSP package: 2,672,640 bytes; SHA-256 `ca41445cc9560035910fbc8c2fc7130175b707b1df2e8e51734d208c4ee2076d`
- BSP path: `levels\\test\\damnation\\damnation`; raw BSP image SHA-256 and size are in the retained manifest.
- Raw palette count: 2. Entry 0 references wind datum `0xE84F06D9` (tag path `levels\\b30\\outside`); entry 1 is `NONE` (`0xFFFFFFFF`). The fixture validates the relocated datum/group/direction/magnitude against the raw BSP and confirms the no-wind entry is expected to yield zero current.
- Raw BSP cluster count: 12; each cluster references weather-palette index 0. This exercises a real multi-entry palette, but not mixed cluster references to the NONE entry.
- The existing raw all-map audit remains `docs/reports/m2-step7-mp-weather-palette-inventory-2026-10-22.md`; this package fixture covers one representative map, not all 13 runtime packages.

## Limits and closure path

This evidence does not show target EE execution, PS2 cycle cost, production-sized arena high-water, sound playback, actual particle/weather drawing, all-map runtime coverage, or native wind behavior beyond the sandbox boundary. It also does not by itself establish that every weather palette/tag field across the 13 maps is preserved; consult the raw inventory report for that separate field/count subcheck. No campaign map is included in this MP-only workload.

The Damnation package-backed host-runtime slice is now closed: relocated CE wind outputs match the independent raw-data vectors, NONE returns zero, and dispose/reinitialize reproduces the same result. For target-sized Step 7 acceptance, Step 8 arena/capacity evidence is still required; this test's diagnostic host arenas are intentionally not presented as EE memory evidence.
