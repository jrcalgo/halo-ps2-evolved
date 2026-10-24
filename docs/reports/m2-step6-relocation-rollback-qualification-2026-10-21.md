# M2 Step 6 — current CE/PS2 transaction and relocation-failure qualification

## Disposition

**Step 6's host transaction gate is complete for the tested package inputs; M2's target gameplay-map gate remains open.** The current fixture executes CE's actual `scenario_switch_structure_bsp()` and `scenario_structure_bsp_load()`/`_unload()` paths, the HCU PS2 cache/CTAG/CBSP implementation, the parent package owner/catalog/source reader, and halo-ps2's bounded HP2 section visitor in one process. It uses audited `a30` and `a50` packages and executes package-backed switching, candidate rejection, rollback, same-process retry, and unload. This is host ILP32 semantic evidence with deliberately overprovisioned stores; it is not EE capacity, PCSX2 gameplay-map, optical/OPL, or rendering evidence.

This closes the previously missing *composed relocation-failure edge* as well: the `a50` B001 test now retains valid outer HP2 and inner CBSP image CRCs while changing one domain-1 CTAG-name relocation target to `tag_data_size` (one-past the mapped CTAG). The production `ps2_cbsp_open_parts()` accepts the envelope/row/image agreement; `ps2_cbsp_rebase_in_place()` rejects the typed target before publishing; CE then reloads B000 and verifies the old image and owner state. This is distinct from the existing HP2-CRC, CBSP-image-CRC, schema, and port-verification failures.

## Exact implementation and test evidence

The test adds the `--direct-cbsp-rebase` path in [`hcu_scenario_bsp_switch_main.c`](../../tests/hcu_scenario_bsp_switch_main.c) and constructs the valid-CRC malformed relocation package in [`test_hcu_scenario_bsp_switch.py`](../../tests/test_hcu_scenario_bsp_switch.py). Assertions require the production `cbsp-stream reject=rebase` marker, a failed switch, candidate B001 followed by old B000 selection, byte-identical B000 restoration, restored CE globals/tag-instance/cache header, cleared parent BSP lease/scratch, and a successful same-process retry. Existing cases continue to cover:

- exact B000/B001 replacement and B000 rematerialization from package-derived extents;
- candidate HP2 read/CRC failure after streamed bytes reach the fixed destination;
- candidate CBSP inner-image CRC failure after the full valid-HP2 section is streamed;
- candidate relocation/rebase failure with valid package and CBSP image checksums;
- real CE schema/structure validation and explicit injected schema/port-verification rejection;
- candidate load failure with successful old-BSP rollback, and candidate plus old-load failure to CE's safe-null/menu state;
- same-index/invalid-index and first-load boundaries in the companion real-CE control-flow case;
- source descriptor lifetime, resource range reads, parent owner/scratch release, and in-process retry/unload.

The production path under test is visible in [`scenario.c`](../../submodules/halo-ce-universal/source/scenario/scenario.c#L1088-L1191), [`cache_files.c`](../../submodules/halo-ce-universal/source/cache/cache_files.c#L1376-L1534), [`ps2_cache.c`](../../submodules/halo-ce-universal/port/ps2/src/ps2_cache.c#L500-L626), [`ps2_cbsp.c`](../../submodules/halo-ce-universal/port/ps2/src/ps2_cbsp.c#L118-L250), and parent [`ctag_mount.c`](../../src/stream/ctag_mount.c#L54-L139). The rebase performs target/alignment/range/NUL checks before patching pointer fields, so the induced one-past target is rejected without publishing a partial pointer graph.

Reproducible current-source command (the native ILP32 process is SIGSYS-blocked in the ordinary sandbox, so the accepted run used the approved outside-sandbox path):

```sh
HALO_HCU_M2_PACKAGE_ROOT=/tmp/hcu-m2-capacity-repro.P5qdmI/packages \
HALO_HCU_M2_PACKAGE_MANIFEST=docs/reports/retail-cbsp-catalog-package-audit-e4a97218.json \
HALO_HCU_M2_RETAIN_LINK_ARTIFACTS=1 PYTHONPATH=. \
python3 -m pytest -q -rs tests/test_hcu_scenario_bsp_switch.py -k retail
```

Result: **1 passed, 1 deselected, 2 package subtests passed** (a30 and a50) in 137.06 seconds. The sandbox invocation compiled the same current sources but skipped native execution with SIGSYS; it is not the run being credited.

Exact artifact/source identity for the passed run:

| Item | SHA-256 |
|---|---|
| Host ILP32 executable | `f1e20f7ddcfd5b6f6ba1779efa6ccc9ef8524554346a2f8d781f8f3d3cf7a156` |
| Link map | `c47315d6d0536b9d5b4ae6d33e09f85f32385901d09c1d325e50995b113009b3` |
| C transaction fixture | `041620fd4ba1931af6187e2fe23fcdc6f0331965acae6ec84b5139379d3bce55` |
| Python test/runner | `17852aa9821b4f615808034c8099f9b6c0a9d9d446a7867d74da4544d0313c90` |
| Retail package audit manifest | `e4a9721846db228b88e6a563c34c0dccc7c6dc7694cf5a393d66c67ca004503b` |
| a30 HP2 / source map | `ce38764fbba687bb26d4f2eb8a6cf066e19e4b8b81521d6f70f23ce8d00f183d` / `287959f34a7379a1dbec5fec15b4d94d17fe97ccd861f5c0c8fc80148b7ed293` |
| a50 HP2 / source map | `9359e0eb09427b098d9773708352c77dbf426ebcec9d7b27400268d84221941a` / `d7a3e80a86f2b0f23d855ce353aed3c0eb252145697797d87f25623dc470f38d` |
| Dirty CE scenario / cache source | `22aef8353c6f4a1067d0e51e78565783d5f7c911e3b4d73f40ad49269a2546c0` / `0ac4f54729de1506d8ba67480f3d14aa5ed1f1f216d107c0547479501943d866` |
| Dirty HCU PS2 cache / CBSP source | `67125925fa335ee57171088979b65775cb4e70d336218da400ec5f8e3d4cfa5c` / `4f317c775928b827412efc47611389f120629260e887897fc4e369660f40e10d` |
| Dirty parent mount / halo-ps2 section / file source | `1cc188a42f8ea2873fb433e8360ad7e08cc2800f46c1c9c3e4881655c2645f0a` / `3626bd968af5e89bfe0876dcbaec49334e39f004a48d920fb4bc3478f1521e7c` / `084b1427d1bf07091efd911b60fb6a7eace153ee5c9baf5b99a870a86f0a648e` |

Repository/submodule heads at qualification: parent `70e2ed0cf2145a45d23aa07414a3a88c05155d4c`, HCU `6933490b2d16bb1c637295b6a0f3880ba23a7d56`, halo-ps2 `71183bb0a9adc586cd267b2780c82bbc12cfd95b`. Dirty source hashes above are required because the heads alone do not identify the code compiled into the test.

## Scope boundary and next dependency

The fixture uses host arrays (16 MiB owner, 16 MiB BSP scratch, 8 MiB active BSP, and 4 MiB validator claims) and a POSIX host file reader. It proves behavior and ownership ordering for the tested cases, not PS2-sized arena capacity or device mounting. The current capacity audit reports the best campaign CTAG plus one referenced BSP lower bound at **10,310,880 bytes** against the entire **6,291,456-byte** `current_bsp` region, before other live owners; therefore no lawful gameplay-map PCSX2 BSP-switch transaction can yet be claimed ([`m2-2026-10-21-capacity-candidate-audit.md`](m2-2026-10-21-capacity-candidate-audit.md)).

Step 6 may be marked complete for its host transaction specification because its actual CE/parent/PS2 package path and required host failure/recovery edges now pass. Keep M2 overall open. Step 8 must first establish a lossless production-sized map/live-set design; the later guest acceptance step must then run the exact qualified package/ELF in PCSX2 interpreter and recompiler and measure EE high-water. Neither Halo-64's N64-specific cuts nor REA binary analysis is needed to justify this source-level transaction behavior; CE source and the PS2 adapter are authoritative, while Halo-64 remains only a comparative platform reference.
