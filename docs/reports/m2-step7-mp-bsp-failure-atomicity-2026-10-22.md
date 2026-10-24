# Step 7 MP BSP replacement failure-atomicity evidence

Status: **host ILP32 check passed; this closes the package-backed rollback subcheck only.** Scope is stock multiplayer Damnation; campaign is excluded.

## What was exercised

The new fixture loads retail Damnation CTAG/B000 through the production parent map service and CE scenario loader, snapshots published CE globals plus the map-owner/scratch state and bytes, then injects a visitor failure only after decoded candidate `B000` bytes have reached the real BSP destination. It verifies CE restores the prior BSP index/pointers and the old relocated map remains queryable (12 clusters, two weather palette entries, cluster 0 references palette 0). It also compares CE cache globals, scenario globals, owner bytes/high-water/cursors, BSP destination bytes, and source descriptor against the pre-attempt snapshot. The exact retry then succeeds, switches back, unloads, and checks that globals, owner/scratch cursors, mount/source state, and descriptor are cleared before reloading Damnation for the existing wind query.

The test-only second scenario-BSP reference is a duplicate of Damnation's actual sole reference, installed temporarily in host memory. This drives CE's real `scenario_switch_structure_bsp` transaction and rollback path without fabricating BSP bytes or editing production data. The scope is intentionally explicit: it verifies failure atomicity over the actual MP package's BSP payload and CE code path, but not the topology of a retail multi-BSP stock MP map. The inventory currently shows one BSP in each stock MP package; campaign was not used.

## Implementation and source basis

- [`tests/hcu_mp_bsp_failure_atomicity_check.h`](../../tests/hcu_mp_bsp_failure_atomicity_check.h:6) performs the late-write injection, snapshot comparison, restored-BSP data query, retry, and unload assertions.
- [`tests/hcu_mp_wind_package_host32.c`](../../tests/hcu_mp_wind_package_host32.c:18) invokes that check on the package-backed fixture before the actual CE wind queries.
- [`tests/test_hcu_mp_wind_package.py`](../../tests/test_hcu_mp_wind_package.py:278) asserts the runtime evidence markers and records the helper and fixture source hashes.
- CE's rollback behavior is in [`scenario.c`](../../submodules/halo-ce-universal/source/scenario/scenario.c:1129): it unloads the current BSP, attempts the replacement, and reloads the old BSP when candidate loading fails (lines 1154–1182).
- The visitor wrapper records a real destination write before it aborts in [`hcu_ce_map_lifecycle_main.c`](../../tests/hcu_ce_map_lifecycle_main.c:145).
- Parent ownership is intentionally not replaced while an active source/mount exists: [`hcu_map_service.c`](../../src/stream/hcu_map_service.c:483) only accepts an active same-map preflight and refuses a different mounted map.

## Reproduction and retained evidence

Run outside seccomp because this host ILP32 binary receives SIGSYS in the sandbox:

```sh
python3 -m pytest -q tests/test_hcu_mp_wind_package.py -s
```

Result: `1 passed in 9.62s` (native ILP32 execution). The same command inside the restricted sandbox is expected to skip when the binary is blocked by SIGSYS; that is not runtime evidence.

Run/package identity from `build/m2-mp-wind-package/manifest.json`:

| Artifact/input | SHA-256 |
| --- | --- |
| Parent / HCU / halo-ps2 pins | `70e2ed0cf2145a45d23aa07414a3a88c05155d4c` / `6933490b2d16bb1c637295b6a0f3880ba23a7d56` / `71183bb0a9adc586cd267b2780c82bbc12cfd95b` |
| Damnation decompressed MP source map | `87bd92c1821ff20bed03c559d7be5ac43baeb44aa68342ffdbb5a8cd978f711c` |
| Damnation HP2 package | `ca41445cc9560035910fbc8c2fc7130175b707b1df2e8e51734d208c4ee2076d` |
| BSP image used (`B000`) | `d3118effad059fde0083f0fd6abc45b824048fd6fe22867047ae6973ac330087` |
| Host ILP32 executable | `90f10de86c93d69672fa95f3c06fa6207296f248c55084233e90b86b233f9291` |
| Runtime log | `101b585b63993f34ff87d9e57a1f16f2c40a3063340f31b64c2d88cc5a820ea0` |
| Failure-atomicity helper | `c0a8c4c22c7170168fd8aeb0b96818f1a12b0892315acc4255c0e18843ad0e3d` |

The retained manifest includes exact stdout/stderr, source hashes, generated package identity, and the new booleans `ce_mp_bsp_replacement_failure_atomicity`, `failed_candidate_written_before_rollback`, `old_bsp_globals_owner_bytes_cursors_and_source_handle_preserved`, `same_process_replacement_retry_passed`, and `owner_source_unload_after_retry_passed`.

## Limits / remaining Step 7 work

This is host ILP32 semantic evidence, not EE or PCSX2 evidence, and the fixture's tag/BSP storage is host-sized. The synthetic duplicate reference is only a means to execute the real CE transaction on an MP package that has one authored BSP. No production code or map admission was changed. This does not close the rest of Step 7: remaining BSP consumers, collision topology coverage, failure behavior for other relocation stages, target-sized query evidence, and target placement still need their own acceptance evidence. It makes no campaign claim.
