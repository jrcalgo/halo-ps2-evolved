# Longest B000 through the direct cache visitor (2026-10-21)

**Disposition:** the frozen Longest package now passes a host integration test through the real parent CTAG mount, registered HP2 section visitor, HCU `cache_file_read()` callback, and HCU CBSP split validation/rebase path. The final 374,784-byte CE BSP image matches an independent Python materialization byte-for-byte. This closes a useful direct-callback loader-mechanics slice, not map-service admission, CE scenario/BSP publication, campaign support, PS2 capacity, or visible rendering.

## Artifact and source identity

| Item | SHA-256 | Use |
|---|---|---|
| Longest HP2 package `build/m2-artifacts/longest-2fba411b-hcu6933490-all-bsps.hp2` | `6f9c19feb4df9e7ec49e797ce3eb6f7cfbdef3c89c6363b12aab2f05359f5a5b` | Frozen input package |
| Decompressed `longest.map` | `e045b0843f4a167a516f050161a651610fafc94ccc8c5f2c5d5725d108d5d1b9` | HMAP/source identity input |
| `tests/ps2_cache_cbsp_longest_main.c` | `50627f646b597fb24768c397469f6aba6697ba9ec1d82e91a6c0fbebd8d2723c` | C composition fixture |
| `tests/test_cbsp.py` | `f9447ef828b7661c1028d63728087a064c9f38dc1aae4fa3f861db468833136e` | Python builder/oracle/runner |
| Parent `src/stream/ctag_mount.c` | `b90f5df170711f40e550cf6b913d6d58824700eb3c80980456c84a37b8c54ef5` | Verified mount and visitor registration |
| HCU `port/ps2/src/ps2_cache.c` | `d2314926bf16064cdc898fc14d9e4c59eb6218d167d345ee33f0f704914063aa` | Exact cache read/CBSP materialization seam |
| HCU `port/ps2/src/ps2_cbsp.c` | `4f317c775928b827412efc47611389f120629260e887897fc4e369660f40e10d` | Split envelope validation and in-place relocation |
| halo-ps2 `engine/src/world/section.c` | `3626bd968af5e89bfe0876dcbaec49334e39f004a48d920fb4bc3478f1521e7c` | Bounded HP2 section visitor |
| halo-ps2 `engine/src/stream/hp2.c` | `f5222e7e2ccfe7fba897cb1d7f0fe46d4fb4a9e1c2018973d7c3b5e9c26140cd` | Streaming decoder and CRC completion |

Git pins at test time: parent `70e2ed0cf2145a45d23aa07414a3a88c05155d4c`, HCU `6933490b2d16bb1c637295b6a0f3880ba23a7d56`, and halo-ps2 `71183bb0a9adc586cd267b2780c82bbc12cfd95b`. The source worktrees are dirty, so the file hashes above are required to identify the exact implementation.

## What is exercised

The fixture allocates separate host arrays at the diagnostic candidate capacities: 4,477,120 B tag cache and 1,814,336 B BSP destination (their sum is the existing 6,291,456 B `current_bsp` budget). It mounts the verified Longest package, opens CE's synthetic cache header, materializes/rebases the 4,263,624 B compact CTAG into the fixed test tag address, installs `ctag_mount_set_bsp_section_visitor()`, and issues the exact cache read for source extent `(2048, 374784)`.

The callback streams B000 through `world_visit_section_with_scratch()` using a 124,224 B host scratch arena. The C fixture checks successful completion, normalized Xbox vertex/index-buffer fields, an unchanged guard immediately beyond the BSP destination, scratch rewind, and mount/source lifetime. The Python test independently decodes the same package and materializes CTAG and CBSP at the C fixture's actual 32-bit host addresses, then compares every final BSP byte. The envelope contains 214 relocation rows; image plus relocation table occupies 377,352 B in the temporary fixed destination. The test is implemented in [`ps2_cache_cbsp_longest_main.c:17-22,45-65,88-98,140-205`](../../tests/ps2_cache_cbsp_longest_main.c) and driven by [`test_cbsp.py:267-361`](../../tests/test_cbsp.py).

Command:

```sh
PYTHONPATH=.:submodules/halo-ps2/tools \
  HALO_HCU_M2_PACKAGE_ROOT=/tmp/hcu-m2-capacity-repro.P5qdmI/packages \
  HALO_HCU_M2_PACKAGE_MANIFEST=docs/reports/retail-cbsp-catalog-package-audit-e4a97218.json \
  python3 -m pytest -q tests/test_cbsp.py::CbspEnvelopeTest::test_longest_b000_uses_production_ctag_mount_visitor_and_ps2_cache -x
```

Result: **1 passed**. The focused related suite (`test_cbsp.py`, `test_ctag_mount.py`, `test_retail_ui_ctag_mount.py`, `test_hcu_scenario_bsp_switch.py`, `test_world_section_visitor.py`) passed **17 tests, 3 skipped in 30.49 s**.

## Explicit limitations and next work

- The fixture calls `ctag_mount_hp2_file_verified_discover_with_bsp_catalog()` directly; it does not use `hcu_map_service_preflight()` or remove the production UI-only admission guard.
- The package owner is an 8 MiB host-only arena, so this does not prove Longest's CTAG/CRNG/CBIX/HMAP or complete map live set fits the PS2 streaming owner. The diagnostic tag/BSP capacities are candidate spans, not a changed/default bound memory profile.
- It calls HCU `cache_file_read()` but does not compile CE's `scenario_structure_bsp_load()` / `scenario_switch_structure_bsp()` transaction. CE schema validation, BSP port verification, scenario/global publication, rollback, and CE-level retry remain untested for this direct visitor path.
- It is host-only. No R5900 runtime high-water, real FileXio/optical/OPL behavior, PCSX2 Longest load, collision/material/PVS/sound parity, or rendered pixels are demonstrated.
- Longest is a multiplayer candidate, not evidence that the campaign capacity problem is solved. The independent campaign topology review finds the d20 tag+BSP plus only fixed known owners already exceeds the committed v2 ceiling; keep campaign admission closed while the full owner/lease feasibility experiment proceeds.

Accordingly, this test should sharpen Remake M2 Step 9's CBSP callback evidence and reduce uncertainty in its loader mechanics. It does not satisfy Step 8's all-campaign memory topology, Step 9's full transactional/fault gate, or Step 10's guest gameplay acceptance. The independent reports [`m2-gameplay-map-bsp-candidate-audit-2026-10-21.md`](m2-gameplay-map-bsp-candidate-audit-2026-10-21.md), [`m2-cbsp-direct-stream-current-audit-2026-10-21.md`](m2-cbsp-direct-stream-current-audit-2026-10-21.md), and [`m2-campaign-capacity-topology-review-2026-10-21.md`](m2-campaign-capacity-topology-review-2026-10-21.md) remain useful prioritization evidence; `plans/5.hcu-remake.md` remains the acceptance authority.
