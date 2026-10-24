# M2 Step 7: stock-MP collision boundary query

## Result

Added a stock-map-backed near-zero boundary ray to the CE collision integration matrix. The new ray uses Beaver Creek structure-BSP surface 44 (material index 0, material type 2, plane designator 52). Its start is generated from the serialized plane and then rounded to float32; the independent raw-CBSP oracle finds one strict-interior polygon contact at `t=7.2109438e-8`, with plane residual `7.2109440e-8`, in leaf 2665. Because float32 rounding leaves a small nonzero residual, this is explicitly a near-zero boundary case, **not** claimed as mathematically exact `t == 0`.

The host fixture calls CE `collision_test_vector()` and observed the same surface, leaf, and `t` (`7.21094437e-8`). The source oracle independently decodes the retail Xbox collision surface/edge/vertex/plane records, calculates all polygon intersections, walks the serialized BSP3D leaf routing, and validates the BSP2D-selected face. The expectation does not come from CE's result.

## Coverage and limits

The native fixture exercises 26 strict-interior shared-edge rays (two opposite-face rays on each of the 13 stock multiplayer maps), plus Beaver Creek exact shared-edge and six-face vertex tie cases, a grazing ray, and this near-zero boundary ray. The tie/vertex/grazing/boundary probes are selected from Beaver Creek; this does not establish those topologies on every MP map. Campaign maps are excluded. This is host ILP32 semantic evidence only—not PS2 memory, EE performance, target runtime, movement coverage, or multiplayer capacity evidence.

Existing collision coverage and the new case remain under [`tools/test_hcu_mp_collision_edge.py`](../../tools/test_hcu_mp_collision_edge.py) and its independent raw parser [`tools/audit_mp_collision_edge_pairs.py`](../../tools/audit_mp_collision_edge_pairs.py). No production source, plan, or pool budget was changed.

## Verification and artifacts

The native ILP32 command `python3 tools/test_hcu_mp_collision_edge.py` completed once with exit 0: **1 test passed in 79.551 s** (the ordinary sandbox invocation skips execution due SIGSYS). A follow-up run after adding unique artifact retention also reported the native unittest **OK, 1 test passed in 80.926 s** and retained its executable/log. The outer runner then raised `NameError: shutil` while copying the generated golden after the successful unittest; the missing import has since been added and `py_compile` passes, but that final wrapper-only repair was not rerun. The CE result itself is independently present in the retained log at line 225.

First clean-run manifest: [`manifest.json`](../../build/m2-mp-edge-runtime-1792693410757655589/manifest.json), SHA-256 `ae9be1d7b08621ff0aa058610182995444b750ee06d678086b9476072791dadf`. It binds the 13 decompressed stock map hashes, selected raw ray, golden, and successful runner status. The exact-zero-named field in that early manifest is the near-zero case described above; later runner source/report uses the more precise terminology.

The retained follow-up run is under `build/m2-mp-edge-runtime-1792693532914764252/retained/`:

- Native stdout/log SHA-256: `28eb527518a8c99f53b489bfc428bebae68462dbc2f03ef60d682997b2eade0d`
- ELF SHA-256: `2e0b94d409f9878965de188589e24fe79271d88c9d06ff5c59a667941e6f8454`
- Link map SHA-256: `d0a3e9e51617a8691c613875a33ede6d687894863502adbda19f0e7794fc42b4`
- Retained test golden SHA-256: `3c68fd017cc9425ec2e009c30311c259c019d039b67a43c55226d92c53ef2805`

The retained log records the CE near-zero result as `surface=44 leaf=2665 raw_t=7.21094366e-08 residual=7.21094437e-08 ce_t=7.21094437e-08`.

Current source SHA-256 after the artifact-retention/import and terminology cleanup:

- `tools/audit_mp_collision_edge_pairs.py`: `fa56ab6d7bc53f746155313a83c02f925249c4d2e2445d020771f045a665016b`
- `tools/test_hcu_mp_collision_edge.py`: `7d73e2a613f73683baa059af7615ec535e67e3200804c938d5c05a9fd9b5a746`
- This report: recorded after writing; hash is supplied in the handoff.

Remaining useful collision work: add source-qualified topology probes for other stock MP BSPs, especially exact vertex/edge starts, and retain a full successful run after the reporting-only artifact-copy fix. Do not treat the current Beaver Creek tie/vertex evidence as cross-map or cross-target tie stability.
