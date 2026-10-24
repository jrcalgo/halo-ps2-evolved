# M2 Step 7 — Retail BSP consumer-query qualification

**Disposition: partial; Step 7 remains open.** This report supplements the CBSP materialization and transaction evidence with actual CE collision-BSP, PVS, and encoded sound-distance accessor calls against relocated retail BSPs. It does not establish complete CE collision/game-sound behavior, production-sized EE placement, or a PCSX2 gameplay-map pass.

## Bound inputs and implementation

- Parent / HCU / halo-ps2 HEADs: `70e2ed0cf2145a45d23aa07414a3a88c05155d4c` / `6933490b2d16bb1c637295b6a0f3880ba23a7d56` / `71183bb0a9adc586cd267b2780c82bbc12cfd95b` (the relevant worktrees are dirty; fixture and source hashes below bind the actual run).
- Package audit manifest: `docs/reports/retail-cbsp-catalog-package-audit-e4a97218.json`, SHA-256 `e4a9721846db228b88e6a563c34c0dccc7c6dc7694cf5a393d66c67ca004503b`.
- `a30`: source-map SHA-256 `287959f34a7379a1dbec5fec15b4d94d17fe97ccd861f5c0c8fc80148b7ed293`; HP2 SHA-256 `ce38764fbba687bb26d4f2eb8a6cf066e19e4b8b81521d6f70f23ce8d00f183d`; two catalogued BSP references.
- `a50`: source-map SHA-256 `d7a3e80a86f2b0f23d855ce353aed3c0eb252145697797d87f25623dc470f38d`; HP2 SHA-256 `9359e0eb09427b098d9773708352c77dbf426ebcec9d7b27400268d84221941a`; four catalogued BSP references.
- Native ILP32 executable: `build/m2-group-d-file-backed-transaction/retail-ce-transaction`, SHA-256 `986f295e691a37f0e3e93266462647185d482db5f6529b5c599f40c7f1934932`; link map SHA-256 `3c6efe6e22c1bab4bf5dbaae2b8f1c72b62ce480b51be7e12c908d2252cd6dff`.
- Modified fixture sources: [`hcu_scenario_bsp_switch_main.c`](../../tests/hcu_scenario_bsp_switch_main.c), SHA-256 `1a4729f92d99718e1dc0a1653305219d92418af13fe4269e8d8aecfd42f1836b`; [`test_hcu_scenario_bsp_switch.py`](../../tests/test_hcu_scenario_bsp_switch.py), SHA-256 `d6399485e3e89abec7ab9b4ac68ca5e2fa324f25290cbfad9365d0de66821bfc`; host XTL shim SHA-256 `169b3c99bb47a8825164e2e3ee72309ba39bd34844940d4d2d973da88c86fd3d`.
- CE collision sources exercised: `source/physics/collision_bsp.c` SHA-256 `096debda0f9cdd62fa8b9981f040770e5e0dfbb8f6baa2f4a241ff0db00dde86`; `source/physics/bsp2d.c` SHA-256 `e1e7f9378e8adefd23dababc794df515d6b8eedb697c541c4cc17ec6a00b302d`; `source/structures/structure_bsp_definitions.c` SHA-256 `00bbb359e4cf9129f8cf0076e7754584a31060836be0460a17cbaef24f8e51eb`; `source/scenario/scenario.c` SHA-256 `22aef8353c6f4a1067d0e51e78565783d5f7c911e3b4d73f40ad49269a2546c0`.

## What the new fixture proves

The existing `HCU_BSP_RETAIL_INTEGRATION` fixture continues to load actual CTAG/CBSP content through CE `scenario_switch_structure_bsp()`, HCU PS2 cache/CBSP materialization, parent package ownership, and halo-ps2 HP2 readers. For each published BSP it now:

1. Calls real CE `collision_surface_polygon()` on bounded samples from the relocated collision-surface array. From each polygon centroid and the source plane normal it constructs a deterministic crossing segment; this only selects test inputs and does not replace CE's query implementation.
2. Calls real CE `collision_bsp_test_vector()` against the currently published, CBSP-materialized `global_collision_bsp`. It requires a hit with an in-range surface, a plane pointer inside the relocated plane array, and a non-`NONE` material index within CE's collision-material table whose `runtime_physics_material_type` is nonnegative. Expected `NONE` materials are skipped while searching for a material-bearing hit.
3. Validates every returned collision leaf index against both collision and structure-BSP leaf counts and resolves its structure leaf to either `NONE` or an in-range cluster. At least one sampled hit per BSP must resolve a real cluster.
4. Checks every cluster PVS row points inside the relocated PVS payload and includes its own cluster bit. Checks same-cluster sound distance is zero; for every distinct pair, the returned pair-byte pointer stays inside relocated sound data and CE returns the same stored value in both index orders. Payload bytes remain unchanged across the accessors.
5. Runs those probes after successful BSP publication, across every catalogued reference and after returning to B000, while preserving the existing rollback/failure/retry assertions.

The probes therefore exercise CE code over actual relocated package bytes, not a synthetic collision BSP. The production callsites these narrow routines support are documented in [`m2-step7-bsp-consumer-disposition.md`](m2-step7-bsp-consumer-disposition.md): `collision_test_vector()` maps collision results to materials and locations (`source/physics/collisions.c:478-575`); CE cluster PVS is consumed by player and visibility paths (`source/game/players.c:1814-1871`, `source/structures/structure_visibility.c:1072-1115,1887-1907`); sound-distance/PVS are used by CE `game_sound.c:985-1015`.

## Verification

- Native package integration, outside the sandbox because its 32-bit executable is SIGSYS-blocked inside it:

  ```sh
  HALO_HCU_M2_PACKAGE_ROOT=/tmp/hcu-m2-capacity-repro.P5qdmI/packages \
  HALO_HCU_M2_PACKAGE_MANIFEST=docs/reports/retail-cbsp-catalog-package-audit-e4a97218.json \
  HALO_HCU_M2_RETAIN_LINK_ARTIFACTS=1 PYTHONPATH=. \
  python3 -m pytest -q -rs tests/test_hcu_scenario_bsp_switch.py -k retail
  ```

  Result: **1 passed, 1 deselected, 2 package subtests passed in 131.65 s**. The test's expected output and assertions require three collision-query BSP publications for `a30` and five for `a50` (each includes a return to B000); every probe found a valid hit/material/leaf-to-cluster result.
- Host parser/schema and CE synthetic-collision regression: `PYTHONPATH=.:submodules/halo-ps2/tools python3 -m pytest -q -rs tests/test_cbsp.py tests/test_ctag_schema_walk.py tests/test_m3_ce_collision_synthetic.py` → **32 passed, 2 skipped, 2 subtests passed**. One skip is the optional package integration without package arguments; the other is sandbox SIGSYS. The standalone synthetic CE collision test was separately run outside the sandbox → **1 passed**.
- R5900 compile closure, same pinned HCU tree: `python3 tools/hcu_ps2_closure.py --layer all --no-bootstrap-memory` → GCC 15.2.0, 342 selected sources, 371 compiled translation units, zero compile failures. Manifest SHA-256 `a64018b2b0de1edf0660ad4e9019d2738216db2ae5352c8a8503899ff9d6f93d`; result SHA-256 `9209c7ff4fc0570ecbbddd31eb8a6f9771e677610820c334eca9e35b9fc5ef89`; rooted object SHA-256 `cfaa082cfdbf7ea2f8dd2b359fcb350c23c7529d69fc85a0c688b67ea0d1ffa5`. This is compile/closure evidence; the M0 live-external gate remains open.
- `git diff --check` and `git -C submodules/halo-ce-universal diff --check` pass.

## Deterministic PVS-pair parity supplement (2026-10-21)

The package-backed fixture now checks specific PVS observations against an independent oracle read from each raw Xbox BSP extent in the exact source map. The oracle does not inspect the HCU-relocated image: it resolves each BSP from the retail map's scenario/tag index, reads its original `cluster_data` payload, and selects the first row-major non-self set bit and first clear bit. Compile-time assertions bind its structure offsets to CE's 648-byte `structure_bsp` and `tag_data.address` layouts in [`structure_bsp_definitions.h`](../../submodules/halo-ce-universal/source/structures/structure_bsp_definitions.h) and [`tag_groups.h`](../../submodules/halo-ce-universal/source/tag_files/tag_groups.h). CE's actual row accessor and bit-vector convention are exercised against the materialized BSP in [`hcu_scenario_bsp_switch_main.c:653-740`](../../tests/hcu_scenario_bsp_switch_main.c#L653); the independent raw-map oracle and output-vs-oracle assertions are in [`test_hcu_scenario_bsp_switch.py:21-83, 310-325`](../../tests/test_hcu_scenario_bsp_switch.py#L21).

Expected/observed first non-self pairs (source BSP reference order):

| Map/BSP | Clusters | Visible pair | Hidden pair |
|---|---:|---:|---:|
| a30 / `a30_a` (B000) | 38 | 0→2 | 0→1 |
| a30 / `a30_b` (B001) | 39 | 0→1 | 0→3 |
| a50 / `a50_exterior` (B000) | 12 | 0→1 | 0→5 |
| a50 / `a50_muster` (B001) | 72 | 0→1 | 0→2 |
| a50 / `a50_hangar` (B002) | 82 | 0→2 | 0→1 |
| a50 / `a50_control` (B003) | 64 | 0→1 | 0→2 |

The full a30/a50 transaction and fault/retry suite passed again using the package/source identities above: **1 passed, 1 deselected, 2 package subtests passed in 132.28 s**. The exact follow-up executable SHA-256 is `600c78a9b8221568ea1b9f156c40291b5fd4acdbefcf2b6a852e38c383d86593`, link-map SHA-256 `1849ecd3cf1fe49bfd876966b5bed503886e89414169f17e0d908411ee6927e9`, C fixture SHA-256 `2412141bf1da24298604b51d5c518327461cfbf0742edb955b840c28e0eaadec`, and Python runner SHA-256 `dc59d9ed7ea9c27016c8b1016ff089aa3cd86df2b9d9072566e49431d5910843`. `PYTHONPATH=.:submodules/halo-ps2/tools python3 -m pytest -q -rs tests/test_cbsp.py tests/test_ctag_schema_walk.py tests/test_m3_ce_collision_synthetic.py tests/test_hcu_scenario_bsp_switch.py -k 'not retail'` passed **30**, skipped 2 sandbox-only native ILP32 tests, and ran 2 subtests. Both parent and HCU `git diff --check` pass.

This closes only the specific relocated visible/hidden PVS bit-pair subcheck for these source-hash-bound BSPs. It does not run CE portal/frustum traversal or player PVS aggregation, and it gives no target memory/capacity or rendered-visibility evidence. The earlier source/PVS summary remains historical; this section supersedes its statement that visible/hidden pairs were untested.

## Remaining Step 7 gaps and limits

- This calls CE's low-level `collision_bsp_test_vector()` primitive, not the full `collision_test_vector()` wrapper in `collisions.c`; dynamic-object arbitration, CE `collision_result` population, and downstream damage/material response are untested.
- The collision inputs are deterministic, package-derived geometry probes, but this run does not bind literal expected hit tuples to an independent retail/CE golden oracle. The tests establish valid in-image hits and map references, not full Halo CE parity of hit fraction/plane/material selection.
- PVS checks now establish self-visibility and source-map-matched visible/hidden pair bits for these six BSPs, but do not test player PVS aggregation/fallback or CE's portal/frustum visibility-set output. Sound accessors are exercised, but `game_sound.c` PVS/occlusion selection, palette/tag selection, and parent SPU2 request behavior are not.
- No environment/fog/underwater/weather/wind query has been executed against the loaded BSP.
- These are overprovisioned native-host fixtures, not production EE RAM/claims/DMA placement. The a30/a50 transaction fixture uses host arrays larger than PS2 spans; the package still exercises transaction semantics only. Step 8's unresolved lossless capacity topology blocks target/PCSX2 gameplay-map acceptance. Do not open campaign-map admission, consume the protected reserve, or remove BSP field families based on these host results.
- Halo-64's N64 port is a comparison for retaining CPU-side CE state while replacing drawing, not a PS2 field-removal/capacity authority ([`port/n64/NOTES.md:33-55`](../../submodules/halo-64/port/n64/NOTES.md#L33)). REA is not applicable to this source/data-path fixture; there is no failing shipped binary here to decompile.

**Next Step 7 slice:** add a full CE `collision_test_vector()` wrapper case with source-derived expected hit/material/plane/leaf tuples if its bounded link closure is practical; execute the actual `game_sound.c` obstruction selection over the materialized PVS/sound data; and cover relevant fog/weather/location consumers. Final target/PCSX2 tests remain blocked until Step 8 supplies a physically measured, behavior-preserving production memory topology.
