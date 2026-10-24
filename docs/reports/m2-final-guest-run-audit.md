# M2 UI guest-run audit — clean candidate ELF

## Result

The exact clean candidate ELF `2c907c1f9c6332412630be42a5b28acf036a404c221745c74f7b23e26945514c` reached the `m2-ui-map-loaded` marker in both PCSX2 interpreter and recompiler modes. Each run remained past the marker for the requested 30-second stability window, recorded unchanged hashes for the same host-root `ui.map` and `ui.hp2` before/after, and has no post-marker address-error, branch-delay, exception-halt, or HALO failure marker in its complete guest log. This closes the earlier interpreter/recompiler post-marker crash gap for this exact artifact over that observed interval.

The viewport capture available for this pair is black; there is no corresponding recompiler image in that run directory. No visible UI or rendered scene is established. The black capture does not negate the scenario-load marker: the plan explicitly separates successful tag/scenario loading from scene-render acceptance. Conversely, the stable UI load does not establish M2 completion. Step 2 is best recorded as **UI scenario load and 30-second cross-mode stability demonstrated; teardown/rollback and visual rendering not demonstrated**. If the step’s “compare both traces through load and teardown” clause is treated literally as an exit condition, Step 2 should remain partial until an explicit unload/reload or rollback cycle is recorded. M2 as a milestone remains open regardless: the candidate link is labeled diagnostic, and the required capacity-qualified gameplay-map load/high-water evidence is absent.

## Exact artifact and guest-run provenance

| Evidence | Interpreter | Recompiler |
|---|---|---|
| Run directory | `build/hcu-ps2-closure/emulator-m1-interpreter-0facebd1f0774a6d8749a9a7842ab9ad` | `build/hcu-ps2-closure/emulator-m1-recompiler-475563c7829741ff864d2ce31e8fc29a` |
| Result JSON SHA-256 | `fb0740f753330aa2acf7f7a6cc65bfe42d5ccb2f172e7f3b5d3879c5d14c63c4` | `f5e95c5c1fdcec19fb4a67fd013b0ce4ef345b476c1bbfc3b8267bdfb5ef96d5` |
| Guest-log SHA-256 | `d4bd287180c73c1abb4f38bead5390a5a071a7bfde74333449d3aab8409dc75c` | `4e232e31f2d8ac0d67b981656d754e1b093d7e809e70c87d987d2c824e6c0bdb` |
| PCSX2 settings SHA-256 | `66c8537b0736527c6767ac5b7cfddda10a6c980469aa2340cdc7e5557e3ac827` | `30abdafce46be5ef2909e2eb1218148dffdc521e9d4d347a6856f878c387a62c` |
| Mode configuration check | EE/IOP/VU recompiler options disabled | EE/IOP/VU recompiler options enabled |
| Success marker | `m2-ui-map-loaded` | `m2-ui-map-loaded` |
| Marker time in guest log | 31.0124 s | 18.3292 s |
| Stability after marker | 30.0933 s (requested 30.0 s) | 30.1093 s (requested 30.0 s) |
| Harness result | `passed`, `m2-ui-marker-stable` | `passed`, `m2-ui-marker-stable` |
| Viewport capture | `pcsx2-viewport.png`, SHA-256 `6a88db7c9674dbd93dfb33885c4dce90e8ed3ca6b33ff313497c0f86780dee27`; black game viewport | No image file present in run directory |

Both run manifests identify the same tested inputs:

* ELF path: `build/hcu-parent-link-probe/hcu-gameplay-machine.elf`; SHA-256 `2c907c1f9c6332412630be42a5b28acf036a404c221745c74f7b23e26945514c`.
* The clean candidate’s strings include `HALO_PS2_LOCAL m2-ui-map-loaded` and do not include the prior temporary `game-state-fault-offset` diagnostic string.
* Parent pin: `70e2ed0cf2145a45d23aa07414a3a88c05155d4c`.
* halo-ce-universal pin: `6933490b2d16bb1c637295b6a0f3880ba23a7d56`.
* halo-ps2 pin: `71183bb0a9adc586cd267b2780c82bbc12cfd95b`.
* PCSX2 binary SHA-256: `0c46bb6a88aa2782b10853a7b07cf3387ba99cbef2b966372cd2315b8571abea` (launcher logs identify PCSX2 v2.8.2); BIOS SHA-256 `b0bf7184d50a209cf7ceb1ab0eb3a0c9b8c583f5f6b3c819e6536f282b93063b`.
* Data ISO argument: `build/hcu-m1-disc-data.iso`; SHA-256 `79f2855a5953483637ca060e778589a9f8c54e5fc4cda4a69347f22484457d79`. `boot_from_disc` is false: this is an ELF boot with data ISO argument, not a boot-from-disc qualification.

The emulator settings hashes are tied to each run’s saved `data/PCSX2/inis/PCSX2.ini` (the harness hashes the exact INI bytes). Their distinct settings are expected for interpreter versus recompiler: `EnableEE`, `EnableIOP`, `EnableVU0`, and `EnableVU1` are false for the interpreter and true for the recompiler. No comparison that assumes identical CPU mode settings is intended.

## Asset path and contents observed

Both result manifests record the HLE `host:/` root as `build/hcu-parent-link-probe`, with identical before/after asset manifests:

| Asset | Bytes | SHA-256 |
|---|---:|---|
| `maps/ui.map` | 33,582,080 | `8556b647b82742d07282fe4e6db0cf847b542c046484e91e71ec31fea5f5fd7e` |
| `maps/ui.hp2` | 286,720 | `a83ded5049128dc0287b975af9c17f4224e467ad5e10ffa079468934e6241e90` |

Each guest log explicitly sets that `host:/` root, announces the asset probe, reads HMAP, CTAG, CRNG, and CBIX during preflight, then mounts the UI cache and reads B000 before emitting `m2-ui-map-loaded`. The mounted-source path reports `map-mount result=0 active=1`; the cache then reports `loaded=1 mounted=1 name=levelsuiui`. The harness’s before/after manifests are equal (`host_assets_unchanged: true`), which binds the tested host files against accidental mutation during the run. This does not mean the ISO’s embedded HP2 was the file opened at runtime: it was the explicitly recorded HLE host path.

## Full-log fault scan and run boundary

Searched both entire `emulog.txt` files, not only the result summary, for `Address Error`, `branch delay`, `EXCEPTION halt`, `HALO_PS2_LOCAL halt`, `HALO_PS2_FAIL`, fatal/panic/assert/trap/fault/corruption markers, and the loaded marker.

* Interpreter: one `Address Error, addr=0x1ff [store]` occurs at 1.6605 s, before the PS2 game’s `machine entry` and before all HCU success markers. This is the known early BIOS/emulator noise, not a post-marker guest failure. No address error or other searched guest-fault marker occurs after `m2-ui-map-loaded` at 31.0124 s.
* Recompiler: no address-error or searched guest-fault marker appears in the full log; it reaches the marker at 18.3292 s and remains stable for the requested interval.
* Both runs are intentionally stopped after the stability interval; logs end in normal PCSX2 VM pause/host cleanup. This is emulator-run teardown, not evidence that CE unloaded the UI scenario, rewound arenas, and reloaded it successfully. No UI unload marker, same-process map retry, or rollback assertion is recorded.

The logs contain recurring controller diagnostics (`Unknown device 'd'` alongside pad configuration messages) during the stability window. These are not classified as a guest trap by the harness and do not prevent this map-load result; input-device correctness is not qualified by this test.

## Acceptance assessment

**Demonstrated for this exact artifact:** both CPU modes reached CE `game-initialize-done` and the M2 UI scenario-loaded marker; the marker is preceded by successful UI cache mount and B000 access; both guest logs remain free of post-marker faults for at least 30 seconds; host-root MAP/HP2 paths, sizes, and hashes match between runs and remain unchanged before/after.

**Not demonstrated:** visible rendering (the only screenshot is black), matching frame-by-frame simulation state across interpreter and recompiler, CE map unload/reload or rollback, physical PS2 behavior, physical-placement proof in these M2 runs (`require_physical_placement` is false), HLE-root equivalence to ISO-contained files, or any gameplay-map load and per-region peak/high-water fit. Parent link report labels the image `linked-diagnostic` and `acceptance: false`, and explicitly says ordinary retail map capacity is not qualified. Therefore, this evidence supports updating Step 2’s prior interpreter-crash status to a successful stable UI-load sub-result, but does not close overall M2 or justify a rendered-game claim.

## Reproduction and retained files

No guest was relaunched during this audit. The exact evidence is already retained in the two directories named above: each `result.json`, `emulog.txt`, `launcher.log`, saved PCSX2 INI, and the interpreter `pcsx2-viewport.png`. Artifact hashes in this report were recomputed from the ELF, data ISO, host assets, screenshot, and guest logs. The M2 operational plan is [`plans/7.hcu-remake-m2-m4.md`](../../plans/7.hcu-remake-m2-m4.md); its Step 2 is the scope used for this assessment.

## Follow-up — post-debug-stack-reader candidate (2026-10-21)

This section supersedes the earlier `2c907c1f…` run pair as the latest UI-load evidence. The 2c candidate remains a valid historical observation, but it is no longer the current candidate after the HaloScript debug stack-reader alignment correction. This follow-up is report-only; it does not change runtime code or the operational plan.

### Exact candidate and source identity

* Candidate ELF: `build/hcu-parent-link-probe/hcu-gameplay-machine.elf`, SHA-256 `4a9bcce6fcc15b5f41298073ad0d8c37304528ec1148aac33bf2caf7757ba41e` (recomputed from the current artifact and matched against both run manifests).
* Parent pin in both run manifests: `70e2ed0cf2145a45d23aa07414a3a88c05155d4c`.
* halo-ce-universal submodule pin in both run manifests: `6933490b2d16bb1c637295b6a0f3880ba23a7d56`.
* halo-ps2 submodule pin in both run manifests: `71183bb0a9adc586cd267b2780c82bbc12cfd95b`.
* The HCU pin has uncommitted PS2-specific HaloScript edits in the build input. The contemporaneous plan records the corrected `source/hs/hs_runtime.c` SHA-256 as `008fca1e333d74598a398f6d058cad8be09e4e5b8cbc6c8b8ab09c3aa3f9a174`; thus the commit pin alone is not the full source identity for this ELF.
* Result manifests identify the same data-ISO argument in both modes: `build/hcu-m1-disc-data.iso`, SHA-256 `79f2855a5953483637ca060e778589a9f8c54e5fc4cda4a69347f22484457d79`; this is not a boot-from-disc run.

### Interpreter/recompiler evidence

| Evidence | Interpreter | Recompiler |
|---|---|---|
| Run directory | `build/hcu-ps2-closure/emulator-m1-interpreter-76d8d15a36cd4078b29f799e19f4d1d9` | `build/hcu-ps2-closure/emulator-m1-recompiler-2ece2e90b9854867bdaa6743fd117dfb` |
| Result JSON SHA-256 | `ea7971664dc614bba7c7ded5ac696d9721062b586d273b81fafc8d2fd393a457` | `e14f5dad37269fb520bff6cdead785b53fb6d41057bec79fb12af706999410a9` |
| Guest log SHA-256 | `8bb0dd0e9bb3c960c4e43390d7058793721413c35196fbb323aea9cb6e79fe5e` | `d5600b64e270675fa81438d4aca80f8d8619333ba32681199ef9550873f005df` |
| Status/stage/mode | `passed`, `m2-ui`, interpreter | `passed`, `m2-ui`, recompiler |
| `game-initialize-done` → UI marker | 6.8233 s → 30.9926 s | 4.5840 s → 18.3619 s |
| Post-marker stable interval | 30.0878 s (30.0 s requested) | 25.0920 s (25.0 s requested) |
| Settings SHA-256 recorded by harness | `23256e5a43eb21657bc42a8f2a0b641019db3ec05a240d21dc1cd02f909836c4` | `95ce85bc693a4696f54cfe2ba9efe0d7c49745486bd7d647aec07208d612fe64` |
| Available viewport capture | none in run directory | `pcsx2-viewport.png`, SHA-256 `82e7b3dab039d12eb5ce065ee0cb5473e3907a1716f7cdf4a7c7f873fd248e42` |

The harness records `settings_sha256` from the PCSX2 INI bytes at launch. The INI files currently persisted in the run directories have later hashes—`32fbcb2fa760765cea0ed02986aec1bc70fdf74aa7678670238000ee06ce6133` for interpreter and `f5177e66bf9ca5620e7607eead6da18c486a5831d161cd3a3b4eacfe87c17eb5` for recompiler—so the result-manifest values are the settings identities for the run, whereas the current on-disk INIs are post-run files. Those INIs distinguish the expected modes (`EnableEE`, `EnableIOP`, `EnableVU0`, and `EnableVU1` false in interpreter, true in recompiler); they must not be substituted for the recorded launch hashes.

Both run manifests record an identical unchanged HLE host-root asset manifest before and after execution:

| `host:/` asset | Bytes | SHA-256 |
|---|---:|---|
| `build/hcu-parent-link-probe/maps/ui.map` | 33,582,080 | `8556b647b82742d07282fe4e6db0cf847b542c046484e91e71ec31fea5f5fd7e` |
| `build/hcu-parent-link-probe/maps/ui.hp2` | 286,720 | `a83ded5049128dc0287b975af9c17f4224e467ad5e10ffa079468934e6241e90` |

The interpreter log has the early BIOS `Address Error, addr=0x1ff [store]` before `machine entry`; neither complete guest log contains a post-marker address error, branch-delay trap, exception halt, or `HALO_PS2_FAIL`. Both logs reach `m2-ui-map-loaded` after successful UI map mount/B000 access, and each result manifest says `host_assets_unchanged: true`. The interpreter run is fault-free after the marker for 30.0878 seconds; the recompiler run is fault-free after it for 25.0920 seconds.

### REA identity, screenshot, and scope limit

REA `open_binary` was run on the exact candidate and returned `format=elf`, `kind=executable`, `architecture=mips`, with SHA-256 matching `4a9bcce6…7ba41e`. `binary_overview` then rejected deep analysis for this target: Ghidra’s available profile requires a separately supported machine-specific MIPS processor profile; Hopper’s adapter does not admit MIPS; IDA is unconfigured and its adapter has no verified MIPS lane. No disassembly/decompilation/source attribution is claimed.

The only capture in this pair is the recompiler `pcsx2-viewport.png` (SHA-256 above). Visual inspection shows the PCSX2 game viewport entirely black, with the UI/menu chrome and status bar only; there is no visible Halo UI or scene. There is no interpreter screenshot in its run directory.

**Assessment:** this newer pair supersedes the 2c candidate for the current UI-load result and demonstrates fault-free `m2-ui-map-loaded` stability for the stated 30.0878 s / 25.0920 s intervals on the same ELF, pins, and HLE UI assets. It remains UI-load evidence only. The blank capture is not a render pass; this test does not establish CE scenario unload, arena rewind, same-process reload, rollback/retry, gameplay-map capacity, per-region gameplay high-water, or physical-console placement. Step 2 may carry this newer stable-load sub-result, but its literal unload/teardown trace remains unproven; M2 remains open.
