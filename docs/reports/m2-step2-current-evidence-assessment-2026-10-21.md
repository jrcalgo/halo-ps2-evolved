# M2 Step 2 current-evidence assessment — 2026-10-21

**Purpose and scope:** independent status review of `plans/7.hcu-remake-m2-m4.md` Step 2 against the current ordinary UI profile, the opt-in UI lifecycle profile, and the higher-level M2 gates in `plans/5.hcu-remake.md`. Report-only: no code or plan changes. This evaluates the UI scenario/lifecycle substep; it does not claim M2 completion.

## Recommendation

The available exact-hash evidence now satisfies the **narrow Step 2 acceptance**: the ordinary UI image fits the fixed ELF limit, reaches `m2-ui-map-loaded` in both PCSX2 interpreter and recompiler, and has separate exact-ELF runtime-placement evidence; a current-source lifecycle diagnostic in both modes demonstrates preflight refusal preserving the live owner, CE global unpublication before owner release, post-unload failure leaving a safe empty state, same-process retry, and two more clean unload/reload cycles. The diagnostic pair requires physical placement and passes it.

Therefore Step 2 can be marked complete as a **UI-load and owner-lifecycle substep**, provided the plan entry is rewritten to cite these current artifacts. The plan currently says it remains partial because the ordinary ELF is `147f…` (388 bytes over) and the prior UI pass is stale; those statements are superseded by the `1012bb…` evidence below. This recommendation does **not** close Remake M2 or authorize Step 6 ahead of its own stated dependencies. `plans/5.hcu-remake.md` requires a supported gameplay-map load after a valid capacity design for M2 exit; that requirement remains open. M0's external-semantic and allocation-ledger gates also remain separate and are not closed by this Step 2 result.

## Current source and artifact identities

The ordinary profile ELF is `build/hcu-parent-link-probe/hcu-gameplay-machine.elf`, SHA-256 `1012bbff41623c1f90005cff8ec9791a7cb6b79d744eef8aef8b54289b44643c`; its linker map SHA-256 is `a09119c133b5feaa20253d8ea2b93ee087d5825efad51c5e68f273d84ae2c780`. `readelf -lW` reports one `LOAD` segment with `p_filesz=0x1fc684` = **2,082,436 bytes** and `p_memsz=0x4013a4` = 4,199,332 bytes. Against unchanged `elf_static=2,097,152`, file-backed headroom is **14,716 bytes**; the ELF/result report has zero undefined imports. The nested `hcu_gameplay_machine` entry in `build/hcu-parent-link-probe/result.json` agrees with `readelf` and binds the ELF SHA. Its separate top-level `hcu_parent_link` record is a stale, different over-cap artifact and must not be mixed into this comparison. The linked probe remains marked `acceptance=false` as a complete playable-image diagnostic; this does not negate the specific guest UI-stage result.

The ordinary HCU root is `cfaa082cfdbf7ea2f8dd2b359fcb350c23c7529d69fc85a0c688b67ea0d1ffa5`; its closure report SHA-256 is `9209c7ff4fc0570ecbbddd31eb8a6f9771e677610820c334eca9e35b9fc5ef89`, manifest SHA-256 `a64018b2b0de1edf0660ad4e9019d2738216db2ae5352c8a8503899ff9d6f93d`, 371 compiled units, zero failures, 342 selected sources, and 321 rooted externals. The lifecycle profile is deliberately compiled separately with `HALO_PS2_M2_UI_LIFECYCLE_TEST`; its rooted object SHA-256 is `0c0b8ed850bf63f03c178997b0e554a9476f9ebe765cae1f46bd752d80bf3859` and diagnostic ELF SHA-256 is `15fcbf8d6b89e6e017501a01afa693661d09b5e1b93e8f710c3e6a0399369fe4` (map SHA-256 `81ebcfa3d8242d5c9f6a31133b43a2c26842effd71c1130b8f9a40fddf435516`). Both ordinary and lifecycle closure manifests were checked against the current HCU checkout: **371 units, zero source-hash mismatches, zero missing source paths** in each. Their build-profile distinction is intentional and should remain explicit; the lifecycle image is not evidence that the ordinary program's loop was qualified through repeated transitions.

Both PCSX2 result sets record the same source pins: parent `70e2ed0cf2145a45d23aa07414a3a88c05155d4c`, HCU `6933490b2d16bb1c637295b6a0f3880ba23a7d56`, halo-ps2 `71183bb0a9adc586cd267b2780c82bbc12cfd95b`; data ISO SHA-256 `79f2855a5953483637ca060e778589a9f8c54e5fc4cda4a69347f22484457d79`. Their manifests bind the HLE `host:/` UI inputs: `ui.map` 33,582,080 bytes, SHA-256 `8556b647b82742d07282fe4e6db0cf847b542c046484e91e71ec31fea5f5fd7e`; `ui.hp2` 286,720 bytes, SHA-256 `a83ded5049128dc0287b975af9c17f4224e467ad5e10ffa079468934e6241e90`; before/after hashes are unchanged. The ISO was mounted as data in the harness, but the result manifest identifies HLE host paths as the guest asset source. This is not optical-media read qualification. Since HCU is a dirty submodule, the exact ELF, map, rooted-object, manifest, and per-unit source hashes—not the commit alone—define the image identity.

## Ordinary UI image: exact guest + physical evidence

| Test | Outcome and evidence |
|---|---|
| UI scenario, interpreter | Passed `m2-ui-map-loaded`, stable 5.0158 s; result SHA-256 `a08c77680b43724c52e81c94042a76aa8a1f3c05983cb752c7cdca523f1ed7d3`; run directory `build/hcu-ps2-closure/emulator-m1-interpreter-81de4a079a304b368bcef7da4b6c6a9d/`. |
| UI scenario, recompiler | Passed `m2-ui-map-loaded`, stable 5.0165 s; result SHA-256 `4f56635d711b1156685af6b808c5d3d10357fbaa8011604fab3aebe19f6704c8`; run directory `build/hcu-ps2-closure/emulator-m1-recompiler-2968c9203b654474b02e9914120a06c0/`. |
| Runtime placement, interpreter | Same ordinary ELF; `linked_physical.passed=true`; all load interval, allocator, arena, non-overlap, and canary checks true; runtime headroom before reserve 13,742 bytes; result SHA-256 `81dda58779bfdcbbc602e41a102d44bd0adcddc90680dc827757e31442bb93a0`. |
| Runtime placement, recompiler | Same ordinary ELF and checks; runtime headroom before reserve 13,742 bytes; result SHA-256 `9b1ca53bdef7953f980b63277e49435c83d43c5eb87ede7c6e52b49c77141dc7`. |

The independent memory-ready stage is placement evidence, not a second UI load or a playable-state claim. The interpreter attempts with the same ELF that exited 127 before guest startup are host Qt/XCB launch failures (run IDs `03c0…`, `f8b4…`, `90e0…`, `f279…`), not contradictory guest failures; later accessible-display runs passed. Do not mistake the data ISO for a boot disc: it is mounted as data for direct-ELF tests.

## Lifecycle diagnostic: guest trace and memory evidence

The lifecycle diagnostic ELF `15fcbf8d…` passed `--stage m2-ui-lifecycle --require-physical-placement` in both emulator modes with more than 5 seconds of post-marker stability and `linked_physical.passed=true`. Interpreter result/log SHA-256: `03f4cb078a92af46605f5394890f802accec7f9d0af013663cee426353a99498` / `e135484decde3b297237e774edc60c56dc138cf649ff71e4ca37520cb217e37a`. Recompiler result/log SHA-256: `7a117c498aea6dcb0e9f614c599f0175b133a4155e224bf5f6b91417fef3d6e8` / `98c32d60800f0e7f02d121d80096bd4afee7539fd6beea54d29ffc94deeee799`. Both show 222,118 bytes runtime headroom before the protected reserve, all nine arenas valid/non-overlapping, boundary canaries verified, and kernel stack within its reservation.

Both logs show this order:

1. `preflight-before-unload` injection while arena `used=39,752`, mount/source/descriptor live; owner values are identical before/after and `m2-ui-lifecycle-preunload-failure-preserved` is emitted.
2. CE unpublishes scenario, BSP, collision BSP, BSP3D, game globals, indices, and tag-instance globals. At the pre-release seam `cache=1` is expected because the cache owner remains live until release.
3. Parent owner release returns `used=0`, clears mount/source, and closes descriptor (`descriptor=-1`).
4. `preflight-after-unload` injection is refused while owner is empty; `m2-ui-lifecycle-postunload-failure-safe-empty` confirms the failure did not resurrect partial state.
5. Same-process valid retry remounts UI, then two additional normal unload/reload cycles complete; each cycle observes CE unpublication before parent release and remounts with the same high-water. The terminal `m2-ui-lifecycle-complete cycles=2` marker is present in both logs.

The test parser in [`tools/test_hcu_boot.py:97-163`](../../tools/test_hcu_boot.py#L97) enforces injection ordering, live-owner preservation, safe-empty state, successful retry, and the CE-unpublish → release → cycle-complete ordering. The diagnostic's test-only path idles after `hcu_m2_ui_lifecycle_test_run()` ([`main.c:3471-3478`](../../submodules/halo-ce-universal/source/main/main.c#L3471)); ordinary CE main-loop code remains on the `#else` path. Production `scenario_unload()` clears scenario globals before calling `ps2_cache_release_map_owner()` in every HALO_PS2 build; only trace lines are diagnostic-only ([`scenario.c:387-418`](../../submodules/halo-ce-universal/source/scenario/scenario.c#L387)).

The interpreter log contains the known pre-guest BIOS `Address Error, addr=0x1ff [store]` at 1.6217 s, before `m2-ui-lifecycle-start` at 32.7877 s; the recompiler trace likewise contains no post-marker guest fault. The harness reports both runs passed and stable. Treat this `0x1ff` startup noise as BIOS/emulator setup evidence, not a scenario-lifecycle error.

## Conflicts and explicit non-claims

- `plans/7.hcu-remake-m2-m4.md` lines 541–549 contain historical statements that Step 2 is still partial due to an unqualified lifecycle trace and an ordinary `147f…` ELF that is 388 bytes over budget. They conflict with current evidence: the current ordinary image is `1012bb…`, fits by 14,716 bytes, passed both UI modes, and has exact-image physical placement; current lifecycle ELF `15fcbf…` passed failure/retry/two-cycle runs in both modes. Those plan lines should be superseded with references to this report/results before the plan status is changed.
- Earlier reports on `c1167…` and its guest runs remain useful history but are not the latest lifecycle profile. Current lifecycle artifact is `15fcbf…`; never attribute the current two injected-failure traces to the older `c1167…` image.
- The `1012bb…` probe's `acceptance=false` means it is a diagnostic combined link, not a finished game. It does not invalidate the explicit `--stage m2-ui` test marker, but it precludes claims of a playable/rendered scene.
- Step 2/Group A evidence is UI-only. It does not establish retail campaign map admission, capacity or working-set fit, map switching across supported maps, optical/OPL hardware storage, visible GS/VU scene rendering, SPU2/audio behavior, M2 exit, or M0 closure. `plans/5.hcu-remake.md` requires at least one gameplay-map load after an approved capacity design for M2 exit; capacity findings elsewhere still say campaign admission is closed.
- Current memory audit (`hcu-gameplay-machine-memory-audit.json`, SHA-256 `cd194bbb2a9c0af40ca63b7d8cb948ba0217f13887ebb6c5bc58fb0031ce6807`) assigns 2,082,224 bytes to `elf_static`, 212 bytes below the exact 2,082,436-byte PT_LOAD; it labels logical assignment provisional. This small ledger mismatch does not contradict the exact `readelf` static-size measurement or runtime `linked_physical` proof, but M0's allocation-ownership gate must reconcile it before global M0 closure.

## Source/plan citations

- Step 2 instructions and stale status: [`plans/7.hcu-remake-m2-m4.md:532-550`](../../plans/7.hcu-remake-m2-m4.md#L532).
- M2 exit and UI-vs-gameplay boundary: [`plans/7.hcu-remake-m2-m4.md:190-204`](../../plans/7.hcu-remake-m2-m4.md#L190) and [`plans/5.hcu-remake.md:338-346`](../../plans/5.hcu-remake.md#L338).
- CE's required `m2-ui-map-loaded` marker is emitted after successful scenario load: [`source/game/game.c`](../../submodules/halo-ce-universal/source/game/game.c).
- Owner release ordering: [`source/scenario/scenario.c:387-418`](../../submodules/halo-ce-universal/source/scenario/scenario.c#L387).
- Lifecycle diagnostic loop isolation: [`source/main/main.c:3471-3478`](../../submodules/halo-ce-universal/source/main/main.c#L3471).
- Guest verification and parser gates: [`tools/test_hcu_boot.py:97-163,506-533`](../../tools/test_hcu_boot.py#L97).

**Conclusion:** mark the narrowly defined M2 Step 2 UI scenario/lifecycle qualification complete after replacing its stale status paragraph with the exact ordinary/lifecycle hashes above. Keep the M2 milestone and all later steps open until the separately specified all-map capacity, gameplay-map transaction, and M2 exit requirements pass.
