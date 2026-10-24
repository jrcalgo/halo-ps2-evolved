# D20 CE scenario/B000 host-oracle load

## Result

The native ILP32 host fixture loaded the current converted D20 package through the real HCU CE `scenario_load()` path and the parent map service, published 2,743 tags plus D20's initial B000 structure/collision BSP state, injected a partial-write failure during the B001 switch and verified CE restored B000, then switched through B001–B004 successfully using CE's real `scenario_switch_structure_bsp()` transaction one BSP at a time. Each successful switch asserted that only the selected BSP tag remained published. Final unload returned the parent map owner to zero. A second build with the production admission profile rejected D20 before opening its assets. This is a host lifecycle oracle only: it does not demonstrate EE memory fit, campaign actor/AI behavior, scene rendering, or PCSX2 map loading.

The new fixture is [`test_hcu_ce_d20_oracle.py`](../../tests/test_hcu_ce_d20_oracle.py) and extends the existing real-CE harness in [`hcu_ce_map_lifecycle_main.c:428-494`](../../tests/hcu_ce_map_lifecycle_main.c#L428). It intentionally follows CE's asynchronous precache contract: the first `cache_files_give_time_to_precache()` starts/copies, the next observes readiness; the implementation is visible at [`cache_files.c:1168-1205`](../../submodules/halo-ce-universal/source/cache/cache_files.c#L1168). It then calls `scenario_load("levels\\d20\\d20")`, exercises CE's BSP transition routine ([`scenario.c:1088-1180`](../../submodules/halo-ce-universal/source/scenario/scenario.c#L1088)), and calls `scenario_unload()`, asserting tag/scenario/BSP publication and teardown.

## Exact input and execution evidence

| Item | Identity |
|---|---|
| Parent HEAD | `70e2ed0cf2145a45d23aa07414a3a88c05155d4c` (dirty worktree) |
| HCU HEAD | `6933490b2d16bb1c637295b6a0f3880ba23a7d56` (dirty worktree) |
| halo-ps2 HEAD | `71183bb0a9adc586cd267b2780c82bbc12cfd95b` (dirty worktree) |
| Halo-64 HEAD | `17541f4444baabb47d1a0deb917f26ccb7b6bc5c` |
| Schema ELF | `build/hcu-ps2-closure/all-no-bootstrap-memory/halo-local.elf`, SHA-256 `175597376cceb8365110ce65ce4307c9b2f2583ce88cba4089e5e00ac4a54214` |
| Generated schema manifest | SHA-256 `ac06b15e1f0cb9882051b79ef37e127eb13ce37f8218a7d7561afbbf37a1c8c2`; 79 groups, 352 definitions |
| Decompressed source map | `build/retail-maps/decompressed/d20.map`, 205,501,952 bytes, SHA-256 `30d8fc02bcd209a7ce03174d8cf6cf771dd3621837d9a2d02111718dcc5e792c` |
| Converted host package | `build/m2-artifacts/d20-host-oracle-30b2a4a3/d20.hp2`, 25,516,032 bytes, SHA-256 `44f96afa5b9fa20efd5c2dcb0d1fca436953d436e8b40015c7dce6e759005fe1` |
| CTAG image | 10,183,696 bytes; 2,743 tags; 14,524,560-byte original tag-data region compacted to 10,046,996-byte schema image with 34,162 relocations |
| Native host fixture ELF | SHA-256 `42c65374f0f3c4908035079b0a0a14a30d35b0f5ea0a8a62e59ecb9cb83e9e2f` |
| Host link map | SHA-256 `4d2ea2e5d9db0ce60980db2a15a476781dfc9e6ced4ae68b66d7280c2a106189` |
| D20 runtime log | SHA-256 `7fe4c277260d052c848bc8f55abb276683bdcb54b3868a2f70a4f1e59984fdb4` |
| Production-guard ELF/log | ELF `af6fabfdc8a0e994d9cd75ee5f4a5870c12967cf3b2398fbd96acc50851bf4f7`; log `5b6c8f0e9d980c239d6539f13b41f89a57a7db2aa382e4c6915a9074e74461b0` |
| Run manifest | SHA-256 `f49aaf172ed7b33b9b703e57c63a5c5fc880112283615c7be5efb0e4ad43cc5a` |
| Fixture/test/service source hashes | Lifecycle C `4aa59dc7a9b54dc55fade9168a243b7a1b4d7be2bd10c0b96ba1cb45050e9126`; BSP-shim C `6f42120078cad6ec46b6b410df53ae09fd42dcbcd340fe6ae17a9d670390e8a3`; Python runner `695b5bdb75cd8df25e251ec6da7a0af159d84509d06b202af0adf1d77e29d813`; map service `b9edaf7320bae962b5ca8a5bd0e9720475a3be7c37cc85cd78da8388f3755a67` |
| Run manifest | `build/m2-d20-host-oracle/manifest.json` |

The package/catalog identity matches [`hcu_map_catalog.c:191-195`](../../src/stream/hcu_map_catalog.c#L191). The catalog contains five D20 extents ([`hcu_map_catalog.c:72-76`](../../src/stream/hcu_map_catalog.c#L72)); the parent visitor successfully decoded B000–B004 to 5,425,904 / 5,104,740 / 8,420,296 / 8,543,144 / 3,818,380 bytes, respectively. The host fixture overrides its BSP destination to 16 MiB so B003's 8,517,632-byte source extent is representable; it checks exactly one BSP tag base is published after each successful switch. It also injects a callback failure after B001 bytes reach the real destination: the visitor returns status 9, CE rejects that candidate, reloads B000 in-process, and the test compares B000's source extent byte-for-byte with its pre-failure snapshot before continuing with successful B001–B004 switches. Runtime map-owner high-water was 10,220,268 bytes, current owner use before unload 10,220,140 bytes, and section-scratch high-water 131,072 bytes (the entire configured host scratch span). These are deliberately overprovisioned host-test spans, not estimates or proof of EE placement. The scratch span reaching its full host cap is a follow-up sizing/instrumentation concern, not a safe-fit claim.

The focused test passed outside the sandbox restriction: `python3 -m pytest -q -rs tests/test_hcu_ce_d20_oracle.py` — **1 passed**. The sandbox run compiled but skipped runtime because the host ILP32 process was terminated with SIGSYS. The external rerun completed B001 failure rollback, all five BSP states, final unload, and the production-guard execution. The combined regression `python3 -m pytest -q -rs tests/test_hcu_ce_d20_oracle.py tests/test_hcu_ce_map_lifecycle.py tests/test_hcu_map_catalog.py tests/test_hcu_scenario_bsp_switch.py` passed **5 tests**, with 3 optional retail-package cases skipped because their package-manifest environment variables were not set.

## Production isolation and source findings

The opt-in `HCU_M2_D20_HOST_ORACLE` branch in [`hcu_map_service.c:305-317`](../../src/stream/hcu_map_service.c#L305) allows only D20 for the dedicated host fixture; the second executable is built without this define and proves the default production path still rejects it as `capacity-not-qualified`. The Python test also asserts that the define is absent from `tools/ee-world.mk` and HCU's PS2 port configuration. Do not use this fixture macro in a PS2 profile or turn it into campaign admission.

The test reaches CE's actual scenario load/unload boundary ([`scenario.c:370-414`](../../submodules/halo-ce-universal/source/scenario/scenario.c#L370)) and checks the parent owner-release callback runs after CE globals are cleared. The successful output is `ce-d20-oracle loaded scenario=levels\\d20\\d20 bsp_index=0 tags=2743 owner=10220140 owner_high=10220268 scratch_high=131072`, followed by `ce-d20-oracle scenario unload released CE globals and parent owner`.

CE's host validator emits correction warnings for render-geometry buffer references absent from the converted tag/BSP image (for example sky/model geometry and some lightmap/material vertex references); the package intentionally strips Xbox render payloads. CE nevertheless accepted this converted CTAG and initial B000, but those corrections reinforce that this is neither an accepted rendering input nor proof that every CE consumer has its required data. The run did not inspect actor spawning, AI, scripts, weapons, animation pose, or runtime rendering.

## D20 B001 checksum rollback follow-up

The D20 oracle now has two isolated package mutations that use CE's real `scenario_switch_structure_bsp(1)` path and preserve B000:

| Case | Mutation and observed boundary | Retained evidence |
|---|---|---|
| Outer HP2 CRC | Flip only B001's HP2 section-table CRC field; `world_visit_section_with_scratch()` returns `HP2_ERR_CRC` (numeric status 8), CE rejects the candidate, reloads B000, and the test compares the live BSP destination byte-for-byte. | Package SHA-256 `53ae82d9fd967c8c29c28fcabdc5462dfab22d7c85f19436e8a2154924eb2f44`; log SHA-256 `6e5d672fec4153d74c6da6e951976b41d0baaa69b60fa75a167866f202a81bce`. |
| Inner CBSP image CRC | Flip a B001 image byte while preserving its embedded CBSP CRC, then rebuild HP2 so the enclosing B001 CRC is valid. The HP2 visitor returns `HP2_OK`; CE's CBSP validation rejects the candidate, reloads B000, and the test verifies the same live-state invariants. | Package SHA-256 `512f5aa9db0404eefc5a25fb2f2f5acc1591d6ba4cfc13dc7f53e03fe7822470`; log SHA-256 `7a8dd3e9f3aa7d81b70546bc6f2f9919d6055979bef307b08ebff0f748dbe8cd`. |

Updated source/build identities: host executable SHA-256 `c326222b72f8ea44e9cdb63305e01b567da45d6528e350281dfd94d6c1920dd9`, link map SHA-256 `f8a622b7b450afad3cac9787144a7f4d96db43e82ac21c0c7d38cfe2f6300886`, lifecycle C SHA-256 `d236db4e50525211859c1c76e3e561f1df777081ddea522f5a492e0ab498f46d`, and test runner SHA-256 `5ddbe9784ccc2e28ab293b82d4f449a8ee750b5f16d4e20d27e32811f2b4f735`. Exact inputs and outputs are listed in `build/m2-d20-host-oracle/manifest.json`. The focused test passed **1 test** outside the sandbox; the default sandbox compiles but skips native ILP32 execution because of SIGSYS. This adds B001 checksum rollback coverage, not every BSP failure/retry boundary, and makes no PS2 capacity or map-admission claim.

## Expanded B001–B004 CRC and visitor-abort matrix (2026-10-21)

The focused native fixture was extended to parameterize the fault section and target CE BSP index. It independently flips the HP2 directory CRC for B001–B004, flips a CBSP image byte while rebuilding a valid enclosing HP2 package for B001–B004, and injects a visitor sink abort after candidate bytes have been written for B001–B004. Every isolated run starts from B000 and exercises the real `scenario_switch_structure_bsp(index)` path. Outer faults require `HP2_ERR_CRC`; inner faults require HP2 `HP2_OK` followed by CE CBSP rejection; visitor faults require a verified first destination write, CE transition failure, and a successful same-process retry of that exact BSP. Each case verifies B000's full destination bytes and CE publication pointers/index remain unchanged after failure, checks the retained mount/source and scratch cursor, then unloads with owner release. The unmodified package still exercises all five BSP states; the production-profile binary still rejects D20. Outside-sandbox verification: `python3 -m pytest -q -rs tests/test_hcu_ce_d20_oracle.py tests/test_hcu_ce_initial_bsp_rollback_source.py -x` — **6 passed in 124.30 s**.

The latest artifact manifest is `build/m2-d20-host-oracle/manifest.json`, SHA-256 `a8a5396892d4dcf69cfbb7dd145f7f41977b6cc18b4dec95fbfd773116aebed4`. It records per-index package/log hashes for all eight CRC faults and per-index logs for all four late visitor abort/retry cases. Latest fixture ELF/link map SHA-256 are `72756e0dea907094a006228dc4b30e00403afbf6a9441998cb323757f9d745f4` / `d5ba5e19c79829881eaa5506fd2c6e8d74483faeacce70d3e38fa80450535fd6`; test/lifecycle C sources are `933be9a44c7ef98c49101a6782733b9f8e6e266ce7b2c652fe5d186891ccf3c4` / `795486a63b8bd5dd14a5fb1cf2c79236578468768c7f43bd35cd0191f9ad56f3`. This closes the specifically named B001–B004 outer- and inner-CRC index matrix and late visitor partial-write rollback/retry across those BSPs. Other HP2/CTAG/schema/missing-resource boundaries and any EE capacity/guest claim remain open.

## Next bounded work

1. Keep the production capacity guard unchanged while capturing a source-backed high-water breakdown for host validator claims, tag image, BSP decode, and scratch. Explain why the section-scratch high-water reaches its full 128 KiB allocation before considering any topology.
2. Extend the CE failure matrix beyond the now-covered B001–B004 outer/inner CRC and late visitor-abort cases: connect tag relocation, schema, and missing-resource failures to the same exact snapshot, cleanup, and same-process retry assertions. Keep this host lifecycle matrix separate from any target memory claim.
3. Add a separate real-CE gameplay executable beginning with `game_initialize()` → `game_load(D20)` → `game_unload()`, then incrementally add map initialization, authored actors, player/tick, and pose. Follow [`m2-d20-gameplay-oracle-first-slice-2026-10-21.md`](m2-d20-gameplay-oracle-first-slice-2026-10-21.md); do not infer representative animation access from the scenario-only fixture.
4. Reconcile all host observations with the known whole-map lower-bound deficit and the real EE 32 MiB owner table. Host load success does not override the 30,087,556-byte known-owner lower bound against the 27,787,264-byte committed ceiling, and must not authorize reserve use, data dropping, or map admission.
