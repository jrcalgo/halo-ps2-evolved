# M2 Step 9: direct-CBSP CRC faults inside the CE BSP transaction

**Result:** the native ILP32 host transaction exercises the production HCU section-visitor adapter and PS2 CBSP streaming/rebase path from CE's real BSP-switch routine under two distinct late-integrity failures. The outer-HP2-CRC case proves image bytes reached the candidate destination before the visitor rejected it. The inner-CBSP-image-CRC case keeps HP2 valid, completes the visitor, then proves the cache parser rejects CBSP before CE publication. In both cases CE restores the previous B000, the *entire* B000 cache image matches its pre-failure snapshot, and a clean replacement at the same path can be retried in the same process. This closes host integration slices only; it is not production gameplay-map admission, an EE/PCSX2 load, a memory-fit result, or a render result.

## Reproducible input and implementation identity

- Parent HEAD: `70e2ed0cf2145a45d23aa07414a3a88c05155d4`.
- halo-ce-universal HEAD: `6933490b2d16bb1c637295b6a0f3880ba23a7d56`; dirty production sources used here: `port/ps2/src/ps2_cache.c` SHA-256 `d2314926bf16064cdc898fc14d9e4c59eb6218d167d345ee33f0f704914063aa`, `port/ps2/src/ps2_cbsp.c` `4f317c775928b827412efc47611389f120629260e887897fc4e369660f40e10d`.
- halo-ps2 HEAD: `71183bb0a9adc586cd267b2780c82bbc12cfd95b`; dirty `engine/src/world/section.c` SHA-256 `3626bd968af5e89bfe0876dcbaec49334e39f004a48d920fb4bc3478f1521e7c`.
- Parent production service/mount sources are dirty: `src/stream/hcu_map_service.c` SHA-256 `66c7a3c904fbab41c8473f44f5d18ddd7a3b34d09d1f9579caa076b02d5c3880`, `src/stream/ctag_mount.c` `b90f5df170711f40e550cf6b913d6d58824700eb3c80980456c84a37b8c54ef5`.
- Test inputs: audited a50 HP2 SHA-256 `9359e0eb09427b098d9773708352c77dbf426ebcec9d7b27400268d84221941a`; decompressed source map `d7a3e80a86f2b0f23d855ce353aed3c0eb252145697797d87f25623dc470f38d`; package manifest `e4a9721846db228b88e6a563c34c0dccc7c6dc7694cf5a393d66c67ca004503b`.
- The current ILP32 fixture C source is SHA-256 `d1dd3d73965330249dcab04fae46bb35070bd17a9138ec7a531a9311ea7467d5`; production-translation-unit bridge `tests/hcu_map_service_visit_test_bridge.c` is `2eab050b7b79e796f6a5d2138ce20d58b072af0d51f94a7a4179f33108505cd8`; Python runner is `30c96bd998fb5132cdda79bcce993dc6599c0e5dff4b91af16f7d9e01cf46ddd`.
- Retained artifacts from the final direct-only fixture run: `build/m2-group-d-file-backed-transaction/retail-ce-transaction` SHA-256 `842ced7d1be57598cbf12a98573450af23bd3b36b731ce23fba68f6cdf39b756`; link map `retail-ce-transaction.map` SHA-256 `b3f1c730afe9a42fdea9b869b43fa13f66148f91fa22e9b990eb407ab35a1c31`. The combined run used the same executable hash; its temporary-path-bearing link map was replaced by the direct-only run's map.

## What was exercised

The fixture links CE `scenario_switch_structure_bsp()` and `scenario_structure_bsp_load()` plus real `cache_files.c`, the real HCU `ps2_cache.c`/`ps2_cbsp.c`, parent `ctag_mount.c`, and halo-ps2 `world/section.c`. A test-only bridge includes the actual `src/stream/hcu_map_service.c` translation unit and invokes its private production `visit_section()`; it does not clone its HP2 success/error convention adapter. The service's section scratch and retained a50 source are supplied as callback context.

Each direct run starts from retail a50 B000 and saves a full `retail_size[0]` copy of its BSP cache image. In the first run, only B001's stored HP2 directory CRC is changed; Python confirms the section read fails its checksum. The direct sink counter requires **more than 36 bytes** accepted (the complete CBSP envelope header is buffered separately), proving image bytes reached the unpublished candidate destination before the late outer CRC rejection. In the second run, one B001 CBSP image byte is changed while `hp2.build()` recomputes the containing HP2 section CRC; Python confirms the HP2 section remains readable but the CBSP decoder rejects its inner image CRC. The production cache log contains `cbsp-stream reject=validate`, while the HP2 visitor itself succeeds, separating the two layers. In each case CE's B001 switch returns failure, restores B000, preserves all captured CE pointers/indices/arena cursors and every byte of the full B000 image, and permits the same-path clean package replacement followed by B001→B000 retry without restarting CE, mount, descriptor, or cache backend. Existing transaction/fault cases then run and end with mount/owner cleanup checks.

The successful remount must retain `&direct_visit_service` as `load_context`. An earlier fixture failure passed `NULL`; production `visit_section()` correctly rejected that context. This is fixed in the test setup and was a harness bug, not evidence of a production visitor failure. The fixture also preserves the one-entry B000 selection baseline for subsequent legacy transition assertions.

## Verification

Direct-only strengthened case:

```sh
PYTHONPATH=.:submodules/halo-ps2/tools \
HALO_HCU_M2_PACKAGE_ROOT=/tmp/hcu-m2-capacity-repro.P5qdmI/packages \
HALO_HCU_M2_PACKAGE_MANIFEST=docs/reports/retail-cbsp-catalog-package-audit-e4a97218.json \
HALO_HCU_M2_RETAIN_LINK_ARTIFACTS=1 HALO_HCU_M2_DIRECT_CBSP_ONLY=1 \
python3 -m pytest -q tests/test_hcu_scenario_bsp_switch.py -k retail -x
```

Result before adding the independent inner-CBSP case: **1 passed, 1 deselected in 26.77 s**. The sandboxed run skips native ILP32 binaries with SIGSYS, so this command was executed outside the sandbox.

Combined legacy a30/a50 transaction cases plus direct a50 visitor case, against the strengthened source:

```sh
PYTHONPATH=.:submodules/halo-ps2/tools \
HALO_HCU_M2_PACKAGE_ROOT=/tmp/hcu-m2-capacity-repro.P5qdmI/packages \
HALO_HCU_M2_PACKAGE_MANIFEST=docs/reports/retail-cbsp-catalog-package-audit-e4a97218.json \
HALO_HCU_M2_RETAIN_LINK_ARTIFACTS=1 \
python3 -m pytest -q tests/test_hcu_scenario_bsp_switch.py -k retail -x
```

Result with both independent CRC-failure/retry paths: **1 passed, 1 deselected, 2 subtests passed in 98.29 s**. The direct-only run of both a50 direct paths also passes: **1 passed, 1 deselected in 59.03 s**; the retained executable is byte-identical and the listed link map is from that direct-only run. The separate Longest production-mount/visitor/cache host control also passes: `tests/test_cbsp.py::CbspEnvelopeTest::test_longest_b000_uses_production_ctag_mount_visitor_and_ps2_cache` — **1 passed**. `git diff --check` passes.

## Exact scope and open gates

- This is a host ILP32 transaction with deliberately large host arenas, not a PS2 32 MiB arena placement/high-water measurement.
- It intentionally low-level mounts a50 to exercise the callback. It does **not** call or bypass-test `hcu_map_service_preflight()` as an assertion; the normal UI-only admission gate is unchanged and gameplay-map admission remains closed.
- It does not run the transaction on PCSX2/EE, load a campaign map in the guest, or show a rendered scene. The current data ISO SHA-256 is `79f2855a5953483637ca060e778589a9f8c54e5fc4cda4a69347f22484457d79`; it is a data disc, not a bootable game disc.
- M2 Step 8 capacity remains unsolved: the d20 source-backed lower-bound reports still exceed the committed EE budget before multiple owners. No arena increase, reserve use, asset dropping, or gameplay-map catalog admission is authorized by this host test.
- M2 Step 9 remains partial pending the remaining L0–L6 fault stages (including full cache/CE snapshots for parser and publication failures), normal service-preflight integration, actual target high-water, and guest qualification. These CRC tests add no capacity credit. Step 10 and M2 remain open.

## REA artifact comparison and Halo-64 boundary

REA GNU objdump Evidence for the pre-streaming failing ELF `build/m2-artifacts/failing-b347420832736d53.elf` (SHA-256 `b347420832736d5370c3dfa338522b9849d1cc1e726d554d0590ead49fb9c970`) is `ev_f8106eed99b5fbf323c330bac31033b0276efe71605a0d122db3d82ccd38c48d` for a complete, non-truncated symbol table; selected symbols include CE scenario switch/load and map-service preflight/init, but not `ctag_mount_set_bsp_section_visitor` or `world_visit_section_with_scratch`. The currently rebuilt combined PS2 diagnostic ELF `build/hcu-parent-link-probe/hcu-gameplay-machine.elf` (SHA-256 `8a00017cec6acebbf8d7b147f9c87ceeb6e1c2c99443adc5ec7d3bfa05258147`) has REA Evidence `ev_1fa73c923bd583c91c258ad86d10decf689bc6e2c1042db5570352b8a751f5c6` (complete symbol output) with `visit_section`, `world_visit_section_with_scratch`, `ctag_mount_set_bsp_section_visitor`, `hcu_map_service_preflight`, CE scenario load/switch, and `render_frame`. The separate REA file-header Evidence `ev_3bc4e397e242a4941c22b77676e6b8e09e41351942f436fff54adda5ff8542c7` identifies an `elf32-little` image with entry `0x001010b0`; GNU objdump reports architecture `UNKNOWN!`, so these are symbol/file-format observations, not MIPS decompilation or EE execution. In the complete selected symbol output no `video_present` or `bsp_render_*` symbol was found; this is consistent with the black UI viewport and does not prove why the guest display is black.

Halo-64 is a useful *boundary* comparison, not a source of PS2 memory policy: its N64 map path reopens and loads a converted map image into one contiguous map arena, then assigns that image as `n64_memory.tag_cache` ([`n64_game.c:1011-1055,1100-1110`](../../submodules/halo-64/port/n64/game/n64_game.c#L1011)); its release path tears down render/map state and nulls the tag-cache pointer ([`n64_game.c:1115-1140`](../../submodules/halo-64/port/n64/game/n64_game.c#L1115)). Its excluded-renderer notes explicitly retain CPU-side frame/camera/first-person/HUD state ([`NOTES.md:33-57`](../../submodules/halo-64/port/n64/NOTES.md#L33)). This PS2 integration instead preserves CE's in-place cache contract and streams a selected CBSP through halo-ps2's bounded HP2 visitor into the fixed BSP destination; no N64 arena, reserve, cut, or cadence policy is copied.
