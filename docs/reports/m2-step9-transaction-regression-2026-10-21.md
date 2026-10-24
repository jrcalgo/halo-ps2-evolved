# M2 Step 9 transaction regression run

## Result

The focused map transaction, lifecycle, reader-fault, catalog, mount, CBSP, and HP2 regression set passed **27 tests, 1 skipped, and 2 retail subtests** in 155.66 seconds. This corroborates Step 9's host-side loader/rollback evidence across the currently available fixtures. It does not establish EE memory fit, normal campaign admission, successful gameplay map load in PCSX2, rendering, or the full L0–L6 fault matrix; M2 remains open.

## Exact command and inputs

```sh
PYTHONPATH=.:submodules/halo-ps2/tools \
HALO_HCU_M2_PACKAGE_ROOT=/tmp/hcu-m2-capacity-repro.P5qdmI/packages \
HALO_HCU_M2_PACKAGE_MANIFEST=docs/reports/retail-cbsp-catalog-package-audit-e4a97218.json \
python3 -m pytest -q -rs \
  tests/test_hcu_scenario_bsp_switch.py \
  tests/test_hcu_ce_map_lifecycle.py \
  tests/test_hcu_ce_initial_bsp_rollback_source.py \
  tests/test_hcu_reader_fault_matrix.py \
  tests/test_hcu_map_catalog.py \
  tests/test_retail_ui_ctag_mount.py \
  tests/test_cbsp.py \
  tests/test_hp2_stream_retail.py -x
```

Pytest result:

```text
27 passed, 1 skipped, 2 subtests passed in 155.66s
SKIPPED tests/test_hcu_map_catalog.py:107: requires retail map, package root, schema ELF and package audit manifest env vars
```

The separately rerun A30/A50 CE transaction test passed **1 test, 1 deselected, 2 map subtests** in 97.87 seconds. The exact executable, link map, runner, test, and package manifest hashes are recorded in the Step 9 entry of [`plans/7.hcu-remake-m2-m4.md`](../../plans/7.hcu-remake-m2-m4.md).

## Identity

Committed source pins used by this worktree:

- Parent: `70e2ed0cf2145a45d23aa07414a3a88c05155d4c`
- halo-ce-universal: `6933490b2d16bb1c637295b6a0f3880ba23a7d56`
- halo-ps2: `71183bb0a9adc586cd267b2780c82bbc12cfd95b`

The selected sources are dirty, so their content identities are included:

| File | SHA-256 |
|---|---|
| `src/stream/hcu_map_service.c` | `b9edaf7320bae962b5ca8a5bd0e9720475a3be7c37cc85cd78da8388f3755a67` |
| `src/stream/ctag_mount.c` | `b90f5df170711f40e550cf6b913d6d58824700eb3c80980456c84a37b8c54ef5` |
| `submodules/halo-ce-universal/port/ps2/src/ps2_cache.c` | `d2314926bf16064cdc898fc14d9e4c59eb6218d167d345ee33f0f704914063aa` |
| `submodules/halo-ce-universal/port/ps2/src/ps2_cbsp.c` | `4f317c775928b827412efc47611389f120629260e887897fc4e369660f40e10d` |
| `submodules/halo-ps2/engine/src/world/section.c` | `3626bd968af5e89bfe0876dcbaec49334e39f004a48d920fb4bc3478f1521e7c` |

Test source hashes:

| File | SHA-256 |
|---|---|
| `tests/test_hcu_scenario_bsp_switch.py` | `30c96bd998fb5132cdda79bcce993dc6599c0e5dff4b91af16f7d9e01cf46ddd` |
| `tests/test_hcu_ce_map_lifecycle.py` | `d9cd45a8fea8db5e7c919b3a5c6cc23cfe3496c4bd1a99ab3ac78db285cfd449` |
| `tests/test_hcu_ce_initial_bsp_rollback_source.py` | `463881d44762cadc7ef8aab0eee6e71371a77298d591831a877d5abb8ba35fed` |
| `tests/test_hcu_reader_fault_matrix.py` | `34d80c634b7b67a62b33eef65f4848f3ddda8cf3ff5d8ba8e3f2edcfd26ed42d` |
| `tests/test_hcu_map_catalog.py` | `8512659f8cf0113a35bb8896f2848959dfd05eb8674474b90610680d7f5376fa` |
| `tests/test_retail_ui_ctag_mount.py` | `5f47a23cfcd4032905fd1be04aeb7785f81f0c0dfe1e4ff8d5cc3b151a918d7e` |
| `tests/test_cbsp.py` | `f9447ef828b7661c1028d63728087a064c9f38dc1aae4fa3f861db468833136e` |
| `tests/test_hp2_stream_retail.py` | `1a894bb7db126c3fb0e033ecc58d8e1014f9397ea7e547d4fabe0c173ea0e9c5` |

## Interpretation and remaining work

The test set exercises the actual CE scenario/BSP switch and lifecycle harnesses, production HCU/PS2 section visitor and cache paths, parent CTAG mount, HP2 reader, and CBSP parser with their current host test allocations. The retail transaction test verifies A30 and A50 package identity and its encoded corrupt-CRC/retry cases. The skipped catalog test did not fail; it was not configured with all four required catalog-audit inputs.

### Superseding full retail catalog/reference run

The missing environment inputs were then supplied from the frozen local corpus and matching schema ELF:

```sh
PYTHONPATH=.:submodules/halo-ps2/tools \
HALO_HCU_M2_RETAIL_MAP_ROOT=build/retail-maps/decompressed \
HALO_HCU_M2_PACKAGE_ROOT=/tmp/hcu-m2-capacity-repro.P5qdmI/packages \
HALO_HCU_M2_SCHEMA_ELF=build/hcu-ps2-closure/all/halo-local.elf \
HALO_HCU_M2_PACKAGE_MANIFEST=docs/reports/retail-cbsp-catalog-package-audit-e4a97218.json \
python3 -m pytest -q -rs tests/test_hcu_map_catalog.py -x
```

Result: **4 passed in 27.98 seconds**. The schema ELF SHA-256 is `2fba411b7244b20fdf31f0b1e540fc2b6f5598891f53a64f8b12f850a0cda0aa`; the frozen 24-map/82-BSP package manifest SHA-256 is `e4a9721846db228b88e6a563c34c0dccc7c6dc7694cf5a393d66c67ca004503b`. This resolves the prior missing-input skip for the standalone catalog suite. The combined suite's original count remains as run; do not arithmetically merge test counts for overlapping test files.

Still required for Step 9/M2: complete the enumerated L0–L6 failure/rollback matrix at production ownership boundaries; use normal map-service admission rather than only the lower-level mounted fixture; demonstrate campaign-size resident/BSP/tag/scratch high-water in a physically reconciled 32 MiB EE map; exercise gameplay-map load and consumers in PCSX2 or hardware; and capture visible renderer output. Do not infer those from host correctness, use Halo-64's N64 streaming policy as a PS2 capacity substitute, or broaden map admission based on this run.
