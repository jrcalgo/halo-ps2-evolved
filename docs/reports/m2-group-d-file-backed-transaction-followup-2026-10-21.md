# M2 Group D file-backed transaction follow-up (2026-10-21)

## Result

Group D now composes the real CE BSP-switch transaction with the parent bounded HP2 section reader and retained retail-map source in one host ILP32 fixture. This closes the previous whole-package-in-memory / always-failing-resource-read seam for the tested host POSIX backend. It is still a host semantic/integration result: it does not prove FileXio/OPL or optical behavior, production memory fit, gameplay-map admission, PCSX2 loading, or rendering.

The integration enters through [`ctag_mount_hp2_file_verified_discover_with_bsp_catalog()`](../../src/stream/ctag_map_source.c#L217), which verifies HMAP identity and full source-map SHA, discovers the CRNG tag extent, loads CTAG/CRNG/CBIX, and ties the open map reader to mount teardown. HP2 package sections now flow through [`world_load_section_with_scratch()`](../../submodules/halo-ps2/engine/src/world/section.c#L141), which bounds its decode workspace, uses the production `file_reader_*` API, and rewinds output/scratch on failure. The callback and fixture wiring are in [`hcu_scenario_bsp_switch_main.c`](../../tests/hcu_scenario_bsp_switch_main.c#L315) and [`test_hcu_scenario_bsp_switch.py`](../../tests/test_hcu_scenario_bsp_switch.py#L78).

Before that one-shot callback failure, the C fixture now tries a temporary package whose CBIX table entry has a deliberately wrong expected CRC. The package structure and compressed bytes are unchanged, so `world_load_section_with_scratch()` opens the package, reserves output, streams the entire CBIX decode, and only then reports `HP2_ERR_CRC` (8). The mount must rewind all owner/scratch spans, leave the cache unavailable, close the source descriptor, and allow the same-process retry from the untouched package. It then injects the earlier one-shot callback failure as a separate rollback check. After successful retry, the fixture materializes the real CTAG and invokes the actual cache read path for a non-`NONE` scenario datum. That read is CRNG-authorized and compared byte-for-byte with the corresponding range in the pinned decompressed retail map. The source descriptor remains active across all BSP switches, rollback, and retry, then becomes inactive with descriptor `-1` after `ctag_mount_unload()`. Existing candidate-read, schema, port-verification, dual-failure, fallback, snapshot, and retry assertions remain active. See [`package_transaction()`](../../tests/hcu_scenario_bsp_switch_main.c#L579) and the cleanup assertions near its end.

## Verification

The exact native ILP32 test command was run outside the sandbox because the sandbox terminates that executable with SIGSYS:

```sh
HALO_HCU_M2_RETAIN_LINK_ARTIFACTS=1 PYTHONPATH=. \
HALO_HCU_M2_PACKAGE_ROOT=/tmp/hcu-m2-capacity-repro.P5qdmI/packages \
HALO_HCU_M2_PACKAGE_MANIFEST=docs/reports/retail-cbsp-catalog-package-audit-e4a97218.json \
python3 -m pytest -q -rs tests/test_hcu_scenario_bsp_switch.py -k retail
```

Result: **1 passed, 1 deselected, 2 subtests passed** (the `a30` and `a50` retail package cases); both subtests emitted the expected CBIX checksum diagnostic and passed the failed-mount cleanup plus retry. The package fixture validates both package and decompressed-map hashes against the audit manifest before compiling/running the transaction. Combined sandbox-safe regression command:

```sh
PYTHONPATH=. python3 -m pytest -q \
  tests/test_hcu_scenario_bsp_switch.py \
  tests/test_world_section_capacity.py \
  tests/test_retail_ui_ctag_mount.py
```

Result: **3 passed, 2 skipped**; skips are expected where package inputs are not supplied or sandbox ILP32 execution is blocked. `git diff --check` passed.

Retained exact fixture artifacts:

| Artifact | SHA-256 |
|---|---|
| Host ILP32 executable, `build/m2-group-d-file-backed-transaction/retail-ce-transaction` | `623f6b2d3731cdbad7390c7ef24f4445d4e3502aa14fe9565de1cfca1364a534` |
| Link map, `build/m2-group-d-file-backed-transaction/retail-ce-transaction.map` | `5eff4d3b59bf832d659fa0943abeb33a1423d30fe565a25f1fc90d5fee039b98` |
| `a30.hp2` | `ce38764fbba687bb26d4f2eb8a6cf066e19e4b8b81521d6f70f23ce8d00f183d` |
| `a30.map` | `287959f34a7379a1dbec5fec15b4d94d17fe97ccd861f5c0c8fc80148b7ed293` |
| `a50.hp2` | `9359e0eb09427b098d9773708352c77dbf426ebcec9d7b27400268d84221941a` |
| `a50.map` | `d7a3e80a86f2b0f23d855ce353aed3c0eb252145697797d87f25623dc470f38d` |
| Package audit manifest | `e4a9721846db228b88e6a563c34c0dccc7c6dc7694cf5a393d66c67ca004503b` |

Source pins at run: parent `70e2ed0cf2145a45d23aa07414a3a88c05155d4c`; HCU `6933490b2d16bb1c637295b6a0f3880ba23a7d56`; halo-ps2 `71183bb0a9adc586cd267b2780c82bbc12cfd95b`. The relevant source trees were dirty, so the run is bound additionally to these content hashes:

| Source | SHA-256 |
|---|---|
| `tests/hcu_scenario_bsp_switch_main.c` | `adb283cb8d37d66b4a8b4b9a7b8badb8d8ed41c186b181cdcf357edc4fa45006` |
| `tests/test_hcu_scenario_bsp_switch.py` | `98d3a342f830c3d07777d5b56bfc75bbc67626cc598325659343005124d3bbfd` |
| HCU `source/scenario/scenario.c` | `ca2da9a1332a259c66046a444c9456572f21d1586bdef72b715ef9013fc61b91` |
| HCU `source/cache/cache_files.c` | `037319cf155152b25a018028401bf709097607a1728cd7821727795a8e81be5c` |
| HCU `port/ps2/src/ps2_cache.c` | `0d16f16c4d5fca09871a2c1d0bdbc4b952c14f7f922f09d541bc67ba43521aef` |
| halo-ps2 `engine/src/world/section.c` | `74908f5122752a88545447fd2ea246080a510fabce5bd7254e09e6e015143c7e` |
| halo-ps2 `engine/src/stream/file.c` | `084b1427d1bf07091efd911b60fb6a7eace153ee5c9baf5b99a870a86f0a648e` |
| parent `src/stream/ctag_map_source.c` | `3f457ea3194edb2a2807ff414b084a593c5e9ff2b93e105ca3c7212fb571f241` |
| parent `src/stream/ctag_mount.c` | `e2cc52e628a5c163be7038570c0502dc19db61ec2007d4ab9d6a76344eff9219` |
| parent `src/stream/ctag_resource_index.c` | `0ce6bc433fc76699eda7e15af1a26aca4ff1f9a02eca9f9be7163e2353bfd18f` |

## Scope and remaining Group D work

The host fixture links `file.c` without `HALO_FILE_USE_FILEXIO`, so it exercises production bounded POSIX host reads, not FileXio calls or OPL-mounted devices. The independent FileXio fake tests remain in [`ctag_mount_main.c`](../../tests/ctag_mount_main.c), and real OPL/optical device tests remain M1 acceptance work. The retail transaction still uses 16 MiB owner and BSP scratch arenas, 8 MiB BSP storage, and a 4 MiB claims bitmap. The exact host success must not be interpreted as target-capacity evidence; the d20 lower-bound failure and closed campaign admission still govern M2.

Uncovered transaction additions from the earlier Group D proposal remain open: deterministic short-read/EOF injection in the package section reader, resource-read short-read rollback/retry, actual full CE scenario teardown rather than fixture cleanup, and target guest switch/rollback traces after a lawful map fits. The stored-CRC mismatch path now proves rollback after full streamed CBIX output, but it does not yet inject a decoder transport EOF or a CRC failure while materializing a candidate CBSP. This follow-up is a meaningful ingress integration, not Group D or Step 9 completion.
