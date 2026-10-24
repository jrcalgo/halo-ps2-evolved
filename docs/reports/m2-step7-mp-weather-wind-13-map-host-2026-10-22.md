# Step 7: 13-map multiplayer weather/wind CE consumer fixture

Status: **host semantic fixture passed** for the thirteen stock multiplayer maps, with two lifecycle loads per map (26 successful wind-query rows). This is one Step 7 consumer subcheck only. It is not EE/PCSX2 execution, target-sized capacity evidence, particle rendering, or Step 7 closure.

## What was implemented and verified

`tests/test_hcu_mp_capacity.py` now reads each decompressed stock map's sole BSP, checks the source-layout extents, and independently extracts weather-palette entries, referenced wind-tag definitions, direction/magnitude fields, and every cluster's weather-palette selector (lines 69–127). Inputs are hash-pinned by map and package, and package conversion is tied to the audited schema ELF SHA-256 `2fba411b7244b20fdf31f0b1e540fc2b6f5598891f53a64f8b12f850a0cda0aa` (`tests/test_hcu_mp_capacity.py:15-48,202-225`). The generated source inventory is retained at `build/m2-mp-weather-wind-13/mp_weather_wind_source_inventory.json` (SHA-256 `549e10e47b5a59a0056f15924f094efbb7bf0d75c76a963bdb00548102dcbac5`); the source-derived C goldens contain 14 palette rows and 239 cluster rows (SHA-256 `fa333f74b40bcde3359ab51f169c49ef26056e1496e0a293d0c86d5a4fbf0404`).

The fixture loads each verified HP2 package through the existing map lifecycle. For the actual relocated CE BSP/tag data, `tests/hcu_mp_weather_wind_host32.c:76-140` verifies palette count, wind group/datum, direction and magnitude, plus every cluster selector against the separately read retail source. It fixes random seeds per map/reload, calls `random_math_initialize`, real CE `wind_initialize_for_new_map()` and `wind_update()`, then queries normal, simple, damped, and cluster-selected currents and checks NONE references return zero (`tests/hcu_mp_weather_wind_host32.c:142-206`). It disposes wind/random state before lifecycle unload/reload.

The production CE behavior under test is in `submodules/halo-ce-universal/source/scenario/wind.c:184-272` (state initialization/update and wind construction) and `:274-330` (palette query, damping, and invalid/NONE zero result). The source defines the embedded Euler fields as `{ yaw, pitch }` in `submodules/halo-ce-universal/source/math/real_math.h:396-401`.

Native ILP32 run command, from the repository root, with the retained package assets:

```sh
build/m2-mp-weather-wind-13/mp-weather-wind build/m2-mp-weather-wind-13/assets/
```

The default sandbox denies native ILP32 execution with SIGSYS. The elevated run of the exact current retained binary completed with exit code 0; complete output is `build/m2-mp-weather-wind-13/native-run-final.log` (SHA-256 `7992858a40f0d65ae455b0bb083e5715df4769e261cc24c5ebb7f3369b3f3ccc`). It contains 26 `mp-weather-wind ... status=passed` rows: map IDs 101–113, each appearing twice. All rows report `wind_update=passed`, `query=passed`, and `reload_cycle=stable`; the parent-confirmed output has 26/26 matching host-map lifecycle rows and no assertion, mismatch, or failure. Carousel exercises four cluster `NONE` references; Damnation exercises a `NONE` palette entry. The overall combined fixture concludes `mp-host-collision 13-map CE hit/PVS/reload matrix passed; target capacity not tested`.

Retained executable SHA-256: `ecc096846afaa6e22328f4b7c5e49c326add527e8fcd1318a08321b3c095fc55`. Link-map SHA-256: `9490fc66f329fe27f3ae726168121b2bf21c9c62326d284da655640fb95d7192`.

## Oracle correction discovered during validation

The first elevated execution stopped on Longest because the independent vector oracle had interpreted the two variation-area floats in reverse order. The CE `wind_definition` embeds `real_euler_angles2d`, whose source layout is `{yaw, pitch}`; consequently the third float is yaw variation and the fourth is pitch variation. The source-derived oracle was corrected in `tests/test_hcu_wind_consumer.py:176-189` to model that declared order. This changed only expected-value construction, not CE implementation. The corrected current executable then passed the complete 26-row run above. This is specifically why the earlier failing log `build/m2-mp-weather-wind-13/native-run.log` (old executable; SHA-256 `c179999b389d458a780f4eb99b47e32e2db80028c635125bbc101795defaa0a9`) is not acceptance evidence.

## Pins and limits

- Parent commit: `70e2ed0cf2145a45d23aa07414a3a88c05155d4c`
- halo-ce-universal commit: `6933490b2d16bb1c637295b6a0f3880ba23a7d56`
- halo-ps2 commit: `71183bb0a9adc586cd267b2780c82bbc12cfd95b`
- Map source SHA-256s and converted package SHA-256s: pinned in `tests/test_hcu_mp_capacity.py:21-55`; the fixture fails on missing packages or mismatched pins rather than silently skipping a map.
- Schema ELF SHA-256: `2fba411b7244b20fdf31f0b1e540fc2b6f5598891f53a64f8b12f850a0cda0aa`.

The host harness intentionally uses diagnostic host-sized tag/BSP/claims storage, as documented in `tests/test_hcu_mp_capacity.py:228-230`. It therefore establishes source-backed CE wind behavior against relocated retail map data and repeated host lifecycle stability, not fit in PS2 EE memory, runtime performance, physical arena high-water, optical/OPL reads, sound playback, weather-particle drawing, or in-game visuals. Step 8 capacity and target evidence remains separate. This report does not mark Step 7 complete.
