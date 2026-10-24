# M2 streamed CTAG production integration (2026-10-21)

## Result

The production HCU cache read now has a bounded HP2 visitor route for CTAG. After CE's cache layer requests its fixed tag-cache base, HCU streams the raw CTAG header and image directly into that unpublished destination, retains relocation rows in the map owner's arena, validates HP2 completion plus CTAG structure/image CRC/relocations, rebases pointers in place, and reports success only after all checks. The existing whole-buffer CTAG route remains for non-stream mounts and diagnostic callers.

This is a concrete Step 9 capacity/lifecycle improvement, not M2 acceptance. Preflight still materializes CTAG temporarily to validate the envelope before unload, so large-map preflight pressure is not solved. The current catalog remains UI-only. No gameplay map was admitted, no retail scene was rendered, and no physical optical/OPL medium was tested.

## Source path and ownership

- Parent `ctag_mount` owns map identity, `CRNG`/`CBIX`, the retained source reader, and an arena-owned relocation table; it does not include HCU headers for the generic parent compile (`src/stream/ctag_mount.h`, `src/stream/ctag_mount.c`). The bridge metadata is a parent-local `ctag_stream_info`; [`ctag_ps2_backend.c`](../../src/stream/ctag_ps2_backend.c) converts it at the HCU adapter boundary.
- The HP2 visitor is registered by the mounted owner and decodes synchronously through the retained reader (`src/stream/hcu_map_service.c::visit_section`; `submodules/halo-ps2/engine/src/world/section.c::world_visit_section_reader_with_scratch`). Its callback convention is translated at that boundary: HP2 uses zero for sink success; the cache adapter uses nonzero.
- HCU's exact `cache_file_read()` destination check remains authoritative (`submodules/halo-ce-universal/port/ps2/src/ps2_cache.c::stream_ctag_for_read`). It only accepts the fixed tag-cache base. The sink requires contiguous offsets and exact envelope extents, stages the 52-byte CTAG header, copies image bytes to the destination, and places relocation records in the retained owner table.
- HP2's visitor must return success and the exact decoded raw size before the cache adapter calls `ps2_ctag_open_parts()` and `ps2_ctag_rebase_in_place()`. The former validates the inner image CRC, CE tag header/table, relocation list and every target; the latter validates all fixups and rebases in place before CE can publish `tags_loaded` (`ps2_ctag.c::ps2_ctag_open_parts`, `ps2_ctag_rebase_in_place`; CE publication is later in `source/cache/cache_files.c:1262-1314`). On every path `cache_file_read()` initializes CE's completion reference to failure; a late HP2/CTAG failure therefore cannot publish a partial destination.
- The parent closure originally garbage-collected the new HCU APIs because they were not reachable from HCU's own internal roots. Added `ps2_cache_mount_ctag_stream` and `ps2_cache_set_ctag_visitor` as explicit cross-owner roots in `tools/hcu_ps2_closure.py`; a regression asserts both names exist in the exact no-bootstrap root list and map (`tests/test_hcu_ps2_closure.py::test_streamed_ctag_adapter_boundaries_are_rooted_for_parent_link`). This is required link plumbing, not generated stubs.

## Failure/retry coverage and correction

`tests/hcu_ce_map_lifecycle_main.c` injects a visitor failure after a real CTAG prefix has reached the final cache destination. It verifies the destination witness, false completion/unpublished CE tag globals, parent owner and descriptor cleanup, then successful same-process remount/retry. The same composed real-CE fixture then checks post-copy schema rejection and the initial B000 write-failure rollback/retry. The first run exposed a fixture-only failure: the CTAG injector intentionally clears its selected-tag pointer, and the later B000 injection did not restore it. The B000 case now explicitly selects `"B000"` before arming. This is a test setup fix; no production rollback semantics were relaxed.

The real UI HP2 package is `a83ded5049128dc0287b975af9c17f4224e467ad5e10ffa079468934e6241e90`; the decompressed UI map is `8556b647b82742d07282fe4e6db0cf847b542c046484e91e71ec31fea5f5fd7e`. The fixture reports a mounted owner of 39,704 bytes after CTAG streaming, versus the prior whole-payload retained owner of 1,550,444 bytes; the transient preflight still peaks at 1,550,572 bytes. Treat the reduction only as *post-mount retained ownership* evidence, not as a complete preflight peak reduction.

## Verification

- `PYTHONPATH=. python3 -m pytest -q tests/test_hcu_ctag_stream_validate.py tests/test_ctag.py tests/test_ctag_mount.py tests/test_retail_ui_ctag_mount.py`: **21 passed, 6 subtests passed**.
- `PYTHONPATH=. python3 -m pytest -q tests/test_hcu_ce_map_lifecycle.py -x` outside the native ILP32 seccomp restriction: **1 passed**. Retained fixture ELF SHA-256 `5b387b3d74693b98d97f5f5f5cc8e58523fdaa62e631796c42084b3183540573`; link-map SHA-256 `c85f77376f0873e2a8e5f55ee9fc8cb66b8f38823fe72f45cd8db09d7a9bb50d`; runtime log SHA-256 `6f86ade86287d1a611fd397092b9bd74710ee0949ba8a26cdff29a308eec2200`.
- `python3 tools/hcu_ps2_closure.py --layer all --no-bootstrap-memory`: **370 selected units, 0 compile failures**; HCU rooted object SHA-256 `a63091dd6bc6c62410a81749fad9f9d8a889f1df58c427c33e93430a8fb835bd`. Its M0 gate remains open; this compile count is not external-disposition or memory-ledger closure.
- `python3 tools/hcu_parent_link_probe.py --asset-profile host`: combined machine ELF has zero undefined imports and SHA-256 `ceb5d53bb4ff0e20c78413db9470ee46abac515de390de5d9eb1b076bc1842b5`; link map SHA-256 `4593864dd782b8d6d1a6ba6fe057d11589993f14b358fb40ed8238fb08f50a48`; memory audit SHA-256 `b4326c00f86d738d0ede170ed29fd97d405223553cbc9de62808f9916f08b344`. Its file-backed load image is 2,095,108 bytes against the 2,097,152-byte static limit (2,044 bytes of margin); probe acceptance remains false, so this thin link margin is diagnostic, not a sign-off.
- Exact ELF passed `tools/test_hcu_boot.py --mode both --stage m2-ui --stable-seconds 3 --require-physical-placement --elf build/hcu-parent-link-probe/hcu-gameplay-machine.elf --disc build/hcu-m1-disc-data.iso`. Interpreter result/log SHA-256: `3644bfb5fedc6f5d0dc621d2a5401a353bf6370fa564b1671b7b77bd99764a31` / `6e8fd1828fbe725a18eb174ef00428273ad30c492e8b1ec430ef2c0deeb1152f`; recompiler: `3ec4f34370916ca0ed8731127502b2a3b18dd487e46b3877a74d3b9e7f52a41d` / `29c3f5694b2126c2802351d72320241c871f5ef79be71e7a69eb014deb79d942`. Both used parent/HCU/halo-ps2 pins `70e2ed0cf2145a45d23aa07414a3a88c05155d4c` / `6933490b2d16bb1c637295b6a0f3880ba23a7d56` / `71183bb0a9adc586cd267b2780c82bbc12cfd95b`, unchanged UI inputs and ISO SHA-256 `79f2855a5953483637ca060e778589a9f8c54e5fc4cda4a69347f22484457d79`. Both runs passed the runtime ELF/boot/reserve marker checks and reached `m2-ui-map-loaded`, stable for at least three seconds. The UI source assets remained unchanged.
- Both guest logs show `elf_end=0x504524`, boot allocation base `0x504740`, boot end `0x19ffbd2`, reserve start `0x1a00000`, allocator gap 540 bytes, and ten verified canaries. The reported boot-to-reserve gap is 10,286 bytes; the configured 5.5 MiB reserve itself remains unclaimed. These are PCSX2 observations for the exact image, not physical-console confirmation.

## Dirty-input identity

The source worktrees were dirty; commit pins alone do not identify the exact linked sources. Relevant source SHA-256 values at build/test time:

| File | SHA-256 |
|---|---|
| [`ctag_mount.c`](../../src/stream/ctag_mount.c) | `1cc188a42f8ea2873fb433e8360ad7e08cc2800f46c1c9c3e4881655c2645f0a` |
| [`ctag_mount.h`](../../src/stream/ctag_mount.h) | `ca620f1a66bdb7bf58c692f29816f7e61cf3ae4b37651c747b8cf4ea1a64833d` |
| [`ctag_ps2_backend.c`](../../src/stream/ctag_ps2_backend.c) | `e4c2efc58cc171fe5ea9982306eedfbde902c2731e676b968c46306e356d157a` |
| [`hcu_map_service.c`](../../src/stream/hcu_map_service.c) | `c5b94f0a5a280a876f5841899538d0433d22dd8ffd8ccd45f41c52596f683b4c` |
| HCU `ps2_cache.c` | `67125925fa335ee57171088979b65775cb4e70d336218da400ec5f8e3d4cfa5c` |
| HCU `halo_ps2_cache.h` | `48b2c9b3e913b6c40fad03fdf27ee8ea1ec89c35e2dfdd45a43a1f135e93f41b` |
| CE `cache_files.c` | `0ac4f54729de1506d8ba67480f3d14aa5ed1f1f216d107c0547479501943d866` |
| [`hcu_ps2_closure.py`](../../tools/hcu_ps2_closure.py) | `499b1d2b9049caf33d134bcda65c3ec325c7148ea91edeb5d78bd37e041a26e1` |
| lifecycle fixture C | `646dedca4b0169721646efd335c4ad3c8e87f54ffed3631467341b3938b2f30d` |

## Next implementation gates

1. Replace preflight's full `CTAG` `load_section()` with bounded validation while preserving current-map nonmutation, inner/outer CRC checks, schema/layout and relocation checks, source-hash identity, and the same post-unload failure/retry semantics. The stream validator in `port/ps2/src/ps2_ctag.c` is currently read-at based, while `world_visit_section_reader_with_scratch()` is push/visitor based; do not adapt this by repeatedly decompressing the section per tiny random read.
2. Keep `cache_file_globals.tags_loaded` and all CE tag pointers unpublished until the direct final-span stream, rebase, and CE schema validator all pass. Preserve the UI-only guard until an exact largest-map plan demonstrates the simultaneous tag/BSP/live owner fit.
3. Rebuild and rerun both PCSX2 modes for every production source change. A UI marker plus physical placement checks is only M2 service smoke; it is not Longest/gameplay acceptance or proof of visible pixels.

