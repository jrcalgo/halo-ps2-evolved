# Current PCSX2 UI-stage evidence (2026-10-21)

## Fresh exact-artifact rerun and viewport capture

The current host-profile combined ELF is `build/hcu-parent-link-probe/hcu-gameplay-machine.elf`, SHA-256 `c1e83f7515a7a6a97b68bad75a9811aaf7fddd0564cb3bdd8722d16bab8d6386` (result JSON `982209e2422cbd7206f661ed5ca8e39d615f994154d501db160bd2b22efb9a0d`, link map `8439e9a6345776a4363911b020feeb08cc2eef78059f48a1f16db1092c354a58`). It binds parent/HCU/halo-ps2 pins `70e2ed0cf2145a45d23aa07414a3a88c05155d4c` / `6933490b2d16bb1c637295b6a0f3880ba23a7d56` / `71183bb0a9adc586cd267b2780c82bbc12cfd95b`. Direct-ELF interpreter invocation with `--stage m2-ui --stable-seconds 5` passed in 37.089 s, including 5.0155 s after the marker (result SHA `4aa33475018622916aaa7ebe96e9b4982b8d86f36e69c1a4059d840a14283b10`, guest log SHA `75fccc1088b5bfc57ae6cf45decedb63e6bd0aaa604deaa26598e7f2a661c61b`). Recompiler mode with `--stable-seconds 10` passed in 29.329 s, including 10.0320 s after the marker (result SHA `66e3920238b878ba48b74a9e481bf4a7b1bcb34bf86e75285057c06b439f8ed4`, guest log SHA `ca9258b2f906eaeeff43f63635a0e95a4d1b44226b5ca893df7884df96bfc78f`, settings SHA `a251dc1eb21da37968be97e84d310050cc7f52f1f097e1607835d179746162dc`). Both reached `game-initialize-done` and `m2-ui-map-loaded`, and the UI host assets remained unchanged. The data ISO was mounted as data (`boot_from_disc=false`), not booted.

While the recompiler process was active, I captured the PCSX2 game window only: [`pcsx2-viewport.png`](../../build/hcu-ps2-closure/emulator-m1-recompiler-77cad19e92c444019698c31d3955f4da/pcsx2-viewport.png), SHA-256 `e9b2fbea1b63c6e1df84d01a759eb66cebf172dff1650719e99b4c3bccd0405b`. The client area is black and the status bar says “No Image” (GPU 0%). So the exact answer to “should I be seeing anything?” is: the current run successfully loads the UI package, but there is no rendered game image yet. This is the expected current limitation, not a guest boot failure. Snapshot commit/CPU packet logs still do not show VIF1/GS submission; M3 Step 13 remains partial.

## Observation

The combined machine ELF SHA-256 `72fe0034df7a70a13e26d95ef470006054e6e5ff5425170c89a80e98b2319ff2` reached `HALO_PS2_LOCAL m2-ui-map-loaded` in both PCSX2 interpreter and recompiler modes, after `game-initialize-done`, and remained fault-free for the required three seconds. Exact reports, logs, emulator settings, BIOS/emulator hashes, and asset identity checks are retained in `build/hcu-ps2-closure/emulator-m1-latest.json` and its run directories. Both report `boot_from_disc=false`: PCSX2 launched the ELF directly and mounted the ISO only as data.

The guest test runner's marker is defined as `HALO_PS2_LOCAL m2-ui-map-loaded` in [`tools/test_hcu_boot.py`](../../tools/test_hcu_boot.py#L42). Its result means the UI package/scenario load reached the requested milestone, not that a gameplay scene or rendered pixels appeared. Earlier markers `render-snapshot-bound` and `snapshot-dma qwords=5` show CPU-side snapshot/packet preparation; they are not evidence of VIF1 submission, GS drawing, or screen presentation. The runner monitors guest logs and stops PCSX2 after the marker-stability interval; this run did not preserve a screenshot.

## Why direct ISO boot shows the PS2 insert-disc screen

The same disc image, `build/hcu-m1-disc-data.iso` (SHA-256 `79f2855a5953483637ca060e778589a9f8c54e5fc4cda4a69347f22484457d79`), is data-only. Read-only `isoinfo -i build/hcu-m1-disc-data.iso -f` listed only:

```text
/MAPS
/MAPS/UI.HP2;1
/MAPS/UI.MAP;1
```

It has no `SYSTEM.CNF` or PS2 boot ELF. Therefore direct booting this ISO is expected to land at the PS2 browser's “insert a PlayStation or PlayStation 2 format disc” screen. That screen does not contradict the successful direct-ELF PCSX2 runs. The runner itself passes the ELF with `-elf` and the data ISO after `--`; it explicitly does not claim `boot_from_disc`.

## Execution detail and limits

An initial sandboxed PCSX2 attempt failed before guest execution with status 127 because Qt/XCB could not connect to display `:0.0`. The same command succeeded when launched outside the sandbox on the active display:

```sh
APPIMAGE_EXTRACT_AND_RUN=1 PYTHONPATH=. \
python3 tools/test_hcu_boot.py --mode both --stage m2-ui \
  --elf build/hcu-parent-link-probe/hcu-gameplay-machine.elf \
  --disc build/hcu-m1-disc-data.iso --timeout 45 --stable-seconds 3
```

Both runs used parent/HCU/halo-ps2 revisions `70e2ed0cf2145a45d23aa07414a3a88c05155d4c`, `6933490b2d16bb1c637295b6a0f3880ba23a7d56`, and `71183bb0a9adc586cd267b2780c82bbc12cfd95b`. The UI source assets were unchanged across each run: `ui.map` 33,582,080 bytes, SHA-256 `8556b647b82742d07282fe4e6db0cf847b542c046484e91e71ec31fea5f5fd7e`; `ui.hp2` 286,720 bytes, SHA-256 `a83ded5049128dc0287b975af9c17f4224e467ad5e10ffa079468934e6241e90`.

REA opened the exact ELF as a MIPS ELF but its configured Ghidra/Hopper/IDA providers reported no supported MIPS analysis lane; REA also rejected this ISO as an unsupported artifact format. Thus no REA decompilation claim is made. The ISO inventory above is independently observed with `isoinfo`, and the gameplay/runtime claim is tied to the exact PCSX2 guest logs/results.

This is UI-stage startup evidence only. The campaign admission guard remains closed because the all-map memory lower bound exceeds the committed EE budget. No gameplay BSP was loaded and no rendered game scene is qualified by this run.
