# Step 8 candidate topology: relocation-tail-inclusive MP diagnostic

## Result

The diagnostic-only candidate completed two map load/query/unload cycles for all 13 stock multiplayer packages (26 successful map-cycle rows), including Sidewinder and Wizard. This resolves the earlier candidate failure: the image-only BSP capacity was 9,192 bytes too small for Sidewinder's decoded CBSP image plus its relocation tail. The revised profile adds exactly those 9,192 bytes to BSP cache and removes exactly the same number from the adjacent texture remainder. The total contiguous map-plus-texture span remains exactly 10,485,760 bytes (10 MiB), and the fixture's adjacency and boundary/content canaries passed.

This is native x86-64 execution of the host-built ILP32 semantic fixture, not execution on R5900/PCSX2 hardware. It is a candidate topology feasibility result only. It does not establish production EE placement, PS2 performance, actual texture residency/safety, or Step 8 closure. In particular, the fixture reserves and protects the texture remainder but does not load/render all texture consumers into it. Campaign is excluded.

## Exact candidate profile

| Store | Bytes |
|---|---:|
| CTAG/tag cache | 4,477,120 |
| CBSP/BSP cache, including the Sidewinder relocation tail | 1,993,704 |
| Combined map cache | 6,470,824 |
| Texture remainder, contiguous after the BSP cache | 4,014,936 |
| Combined map + texture span | 10,485,760 |
| Map owner | 1,048,576 |
| Section scratch | 524,288 |
| Tag validation claims | 808,856 |

Arithmetic is asserted by the isolated runner. Claims are sized to the fixture's production-path query, not treated as part of the contiguous 10 MiB map/texture span.

## Evidence and reproduction

The runner reuses the pinned package matrix and the actual CE map-service, tag relocation, collision, PVS, sound-environment, and weather-query fixture in `tests/test_hcu_mp_capacity.py` and `tests/hcu_mp_capacity_main.c`. Its temporary generated variant changes only test storage ceilings and performs the exact adjacent-slice/canary checks; no production capacity, map admission, binder, or gameplay code was changed. The source fixture iterates the 13 map names and two cycles at `tests/hcu_mp_capacity_main.c:298-303,344-419`; collision/PVS expectations are exercised by `mp_query` at `tests/hcu_mp_capacity_main.c:264-295` and the per-map call at `:399`. Its final result line is `13-map CE hit/PVS/reload matrix passed`.

Build/prepare the diagnostic (the local sandbox may report a skipped test because it kills native ILP32 execution with SIGSYS):

```sh
python3 tools/test_hcu_mp_candidate_topology.py --include-relocation-tail
```

For the retained run below, the actual native command was:

```sh
build/hcu-mpct-tail-1792683984346895497/retained/mp-weather-wind \
  build/hcu-mpct-tail-1792683984346895497/retained/assets/ \
  > build/hcu-mpct-tail-1792683984346895497/retained/candidate-run.log 2>&1
```

The command exited 0. The retained log contains exactly 26 `mp-host-map` rows (each stock map appears at cycles 0 and 1) and ends with the pass marker. Across accepted rows, owner high-water was 89,164 bytes of 1,048,576 and section-scratch high-water was 262,144 bytes of 524,288. The fixture also injected a late B000 failure on Longest and checked globals, published tags, mount, owner/scratch cursors, then retried; this is rollback/retry coverage, not a general fault-injection proof for every loader failure.

The initial image-only candidate and its Sidewinder miss are retained at `build/hcu-mpct-1792683873390176105/`: BSP was 1,984,512 bytes, so the Sidewinder B000 CBSP required 1,993,704 bytes (9,192 over). `tools/audit_mp_tag_bsp_capacity_floor.py:57-75` computes image-plus-relocation storage from each package; the Sidewinder package is pinned by `tests/test_hcu_mp_capacity.py:36-50,180-225`. This diagnostic variant specifically tests whether assigning that tail from the adjacent texture remainder is feasible without increasing the total contiguous span.

## Provenance hashes

Parent/HCU/PS2 source pins used by the retained run:

- Parent: `70e2ed0cf2145a45d23aa07414a3a88c05155d4c`
- halo-ce-universal: `6933490b2d16bb1c637295b6a0f3880ba23a7d56`
- halo-ps2: `71183bb0a9adc586cd267b2780c82bbc12cfd95b`
- Original 13-map source test, SHA-256: `c45575259c0e47f34328df8d54f744da4c9e5289d73f793121957100f2719a9e`
- Candidate runner `tools/test_hcu_mp_candidate_topology.py`, SHA-256: `13e568f9813836b3dbcc297c23d9501c5d01cddfa5e06027163d0f63a63361f7`
- Native ILP32 executable, SHA-256: `09db4dfda456f3de333f6e3bfa6bc4caba8fc0919ca19d8af939b3fb5e82e5cd`
- Link map, SHA-256: `6057cab9a4813bdebe4d39b467a0de0f1a9a446c413c923fcfe4c2486e51c764`
- Successful 26-cycle log, SHA-256: `d4a26e123d89ed45ad84296c8fd9c8708163006086f176b67efb60ca4f8e3099`
- Successful-run provenance manifest `docs/reports/mp-step8-tail-inclusive-candidate-2026-10-22.manifest.json`, SHA-256: `7953d9b4ba955b3eca49b9a792f851f3bb55c526f272223f4da3eb880d4c3d00`
- Candidate-preparation manifest (records the SIGSYS sandbox skip and build provenance), SHA-256: `55d364f0875a5fb8c6eccc4d970ae3b50ec7e50ff52a68b8de087df23c56ec4e`

Artifact directory: `build/hcu-mpct-tail-1792683984346895497/`. The generated temporary test source was removed by the runner after the retained binary was built; the original source fixture and generated artifacts remain available for review.

## Limits and next test

The candidate run deliberately replaces the exact weather-vector comparison with a finite-value smoke assertion, so this run itself makes no numeric wind-parity claim. A separate exact wind fixture is reported as passing; use that fixture for wind numeric parity evidence. This candidate run does not load converted render textures, object/biped/weapon assets, or establish their simultaneous residency; the guarded texture slice proves only that this fixture did not overwrite it. In particular it does not exercise the 2.5 MiB dynamic-simulation pool with a live match's simultaneous players/bots, weapons, effects, and animation. It also does not measure R5900 DMA/alignment, physical EE arena placement, rendering, sound playback, EE timing, or actual OPL/PCSX2 target behavior. CE tag-validation corrections for render geometry in the host packages are expected from this non-rendering test setup and do not prove a valid rendered scene. No production budget, binder, or map-admission setting was changed.

Next useful evidence is a target-shaped EE/PCSX2 run of the same profile with actual map-plus-texture owners, texture uploads/evictions, alignment and DMA constraints, physical arena placement, and peak overlap measured. Until then, keep this topology diagnostic-only and Step 8 open; do not substitute host high-water figures for EE evidence or silently adopt the candidate as production budget.
