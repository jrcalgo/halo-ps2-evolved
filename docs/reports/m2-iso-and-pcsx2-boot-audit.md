# M2 data ISO, BIOS prompt, and PCSX2 launch audit

Date: 2026-10-21. This is an independent, report-only audit of the supplied BIOS screen, the preserved M2 failure ELF/data ISO, the current rebuilt ELF/data ISO, the available boot-disc artifact, and the exact retained PCSX2 launch records. It makes no source or runtime changes.

## Conclusion

The screenshot `/home/ai/Pictures/ps2fail.jpg` (SHA-256 `bec2c7708c3fbc7f98cbd8972ec5c1ec0d51ccf764dad5c15e96b8af2c10abc0`) is the PS2 BIOS fallback: it says no recognized PlayStation/PlayStation 2 boot disc is selected. It is not a Halo renderer image and is not proof that the current ELF reached guest code.

The retained M2 data ISO is intentionally not bootable: its ISO9660 tree contains only `maps/ui.map` and `maps/ui.hp2`; it has no `SYSTEM.CNF` or `BOOT.ELF`, and xorriso reports no El Torito boot information. Inference: if selected as the BIOS boot medium, this ISO is expected to produce the supplied prompt. The same ISO is valid as *data* for an ELF launched directly with `-elf`.

The preserved failing M2 run did launch the old ELF directly, reached `m2-ui-map-loaded`, then faulted in HaloScript and halted. Its log does not report the BIOS prompt. The latest attempt against the current ELF did not launch guest code at all: Qt failed before the first guest marker. Thus neither log proves that the pictured BIOS screen came from that exact run. A separate previously successful UI-load image (`4a9bcc…`) ran with a data ISO attached, reached the UI map marker in both PCSX2 CPU modes, but its captured game viewport is black. That image is older than the current ELF and is not render evidence.

## Exact artifact identities

| Role | Artifact | SHA-256 | Size |
|---|---|---|---:|
| Preserved M2 fault ELF | [`failing-b347420832736d53.elf`](../../build/m2-artifacts/failing-b347420832736d53.elf) | `b347420832736d5370c3dfa338522b9849d1cc1e726d554d0590ead49fb9c970` | 4,412,868 B |
| Current combined diagnostic ELF | [`hcu-gameplay-machine.elf`](../../build/hcu-parent-link-probe/hcu-gameplay-machine.elf) | `20950de9940b058a80a175b90824317607cf6ca09078747400001273fbd554ca` | 4,422,212 B |
| Preserved M2/data ISO | [`data-79f2855a59534836.iso`](../../build/m2-artifacts/data-79f2855a59534836.iso) | `79f2855a5953483637ca060e778589a9f8c54e5fc4cda4a69347f22484457d79` | 34,240,512 B |
| Same data ISO at active path | [`hcu-m1-disc-data.iso`](../../build/hcu-m1-disc-data.iso) | `79f2855a5953483637ca060e778589a9f8c54e5fc4cda4a69347f22484457d79` | 34,240,512 B |
| Separate boot-disc candidate | [`hcu-m1-boot-disc.iso`](../../build/hcu-m1-boot-disc.iso) | `5c21cf894efb9da1d77b1e0189cf7b162b190d498e87ac616b6664a45e226237` | 38,701,056 B |
| User screenshot | `/home/ai/Pictures/ps2fail.jpg` | `bec2c7708c3fbc7f98cbd8972ec5c1ec0d51ccf764dad5c15e96b8af2c10abc0` | 1,048 × 588 px |

The current directory names and sizes were rechecked during this audit. SHA-256s of the preserved/current ELF and data ISO match the retained manifest and run identities; the old and current ELFs are distinct. Both ELF headers are ELF32, little-endian, MIPS, with flags `0x20920025` (`abi2`, `5900`, `mips3`) and entry point `0x001010b0`. REA `open_binary` independently fingerprinted the old ELF as MIPS with its recorded hash and did the same for the current ELF. REA’s available deep providers reject this machine-specific MIPS target (Ghidra processor profile unavailable; Hopper rejects MIPS; IDA is not configured and has no verified MIPS lane). Accordingly this report claims REA fingerprinting only, not REA disassembly/decompilation.

The recorded source commit identifiers for the old M2 fault run are parent `70e2ed0cf2145a45d23aa07414a3a88c05155d4c`, HCU `6933490b2d16bb1c637295b6a0f3880ba23a7d56`, and halo-ps2 `71183bb0a9adc586cd267b2780c82bbc12cfd95b`. Those commits do not fingerprint dirty submodule files; the ELF SHA is the definitive built-artifact identity. The current run manifest records the same commit IDs and current ELF SHA.

## ISO structure and what the BIOS screen establishes

Read-only `xorriso` inspection of the preserved data ISO reports volume ID `ISOIMAGE`, no loaded system area and no El Torito information. Its complete file listing contains only:

| Path | Bytes | SHA-256 |
|---|---:|---|
| `/maps/ui.map` | 33,582,080 | `8556b647b82742d07282fe4e6db0cf847b542c046484e91e71ec31fea5f5fd7e` |
| `/maps/ui.hp2` | 282,624 | `c5b4760afa3b3e8484dc232b2332fb6855d52c0ca271c4427e29c745eec7b51c` |

It has no `SYSTEM.CNF` or `BOOT.ELF`. The accepted HCU harness distinguishes direct ELF launch from boot-from-disc: `boot_once` adds `-elf <path>` unless `boot_from_disc` is true, and passes an optional ISO after `--` as the CDVD data source ([`tools/test_hcu_boot.py`](../../tools/test_hcu_boot.py:203)). The CLI makes the distinction explicit: `--boot-from-disc` means “boot the PS2 executable named by the ISO SYSTEM.CNF”; it requires `--disc`, while the default `--disc` is documented as an optional mounted guest DVD source ([`tools/test_hcu_boot.py`](../../tools/test_hcu_boot.py:360)). Therefore mounting this data ISO with `-elf` is correct; selecting it as the BIOS boot disc is not.

The separate `hcu-m1-boot-disc.iso` does include `/SYSTEM.CNF` (52 bytes) and `/BOOT.ELF` (4,457,068 bytes). Its system-configuration fixture is `BOOT2 = cdrom0:\\BOOT.ELF;1` ([`tests/fixtures/hcu-boot-system.cnf`](../../tests/fixtures/hcu-boot-system.cnf:1)). The ISO listing places `BOOT.ELF` at sector 33; its exact extracted bytes hash to `3eb4852512519f87ae89c611538a6d7819040a7eac989e48b00e39a858ccee94`. That differs from the current machine ELF hash `20950de9…` and size, so this boot ISO embeds a stale executable. It is a structurally prepared boot-disc candidate, but no retained `--boot-from-disc` run proves that the BIOS accepts it; `xorriso`’s lack of El Torito metadata is normal for this PS2-style layout and is not, by itself, a defect or proof of validity.

The supplied screen establishes only that the BIOS is displaying its no-valid-boot-disc fallback at the time of capture. It does not reveal whether the preceding action was selecting the data-only ISO, returning from a terminated guest, or another disc/device state. It cannot be correlated to an ELF hash without a matching PCSX2 run/result or live capture.

## PCSX2 records and command-path correlation

### Preserved failing ELF: guest did start, then stopped

The exact retained run is [`emulator-m1-interpreter-6f826d3c…/result.json`](../../build/hcu-ps2-closure/emulator-m1-interpreter-6f826d3c62fc4a278f31b34be974f0b6/result.json), SHA-256 `3b5f188efb1b0a17c25736565668d7ee0e0105298c673d17052cfbe9588b8ce7`; its guest log is [`emulog.txt`](../../build/hcu-ps2-closure/emulator-m1-interpreter-6f826d3c62fc4a278f31b34be974f0b6/emulog.txt), SHA-256 `79c94c24ef2db8d74bed9bb83161248301dcaf76c98fbeb4b6b14b40ab8ae9b9`. The recorded command is:

```text
/home/ai/.local/bin/pcsx2 -datapath <run>/data -nofullscreen -logfile <run>/emulog.txt \
  -elf build/hcu-parent-link-probe/hcu-gameplay-machine.elf -- build/hcu-m1-disc-data.iso
```

The JSON binds the ELF to `b3474208…`, ISO to `79f2855a…`, and `boot_from_disc: false`. The guest reaches `HALO_PS2_LOCAL m2-ui-map-loaded` at 31.8715 s, then at 32.1361 s reports unaligned accesses at `0x7d2dc6`/`0x7d2dca`; it asserts on script node `#58608`, halts, and PCSX2 pauses. This is a guest-side M2 failure, not the BIOS’s invalid-disc message. The original detailed post-marker diagnosis remains [`m2-artifact-delta-independent.md`](m2-artifact-delta-independent.md) and [`m2-exact-artifact-and-postmarker-fault.md`](m2-exact-artifact-and-postmarker-fault.md).

### Current rebuilt ELF: attempted, but no guest execution

The newest retained attempt is [`emulator-m1-interpreter-9f725f65…/result.json`](../../build/hcu-ps2-closure/emulator-m1-interpreter-9f725f65c985428ba9897d09ee8e1445/result.json), SHA-256 `81d37b86e9c9a3cba8b2ac321639c1038c1a38431fedfbfe13aa02bf8cff695f`; launcher output is [`launcher.log`](../../build/hcu-ps2-closure/emulator-m1-interpreter-9f725f65c985428ba9897d09ee8e1445/launcher.log), SHA-256 `80ce3c0d35fef7d886286dc17ec01b1bbffb8b7b7a7c342f5e006ee8914b6510`. It binds the current ELF `20950de9…`, `boot_from_disc: false`, with no `--disc` argument. The launcher reports that Qt’s requested `offscreen` plugin is unavailable; status 127 occurs before any guest log exists. This is host/frontend infrastructure failure, not evidence of guest success, guest failure, or the BIOS prompt’s cause.

### Older UI-load pair: black viewport, not current-image rendering

The latest retained stable UI-load pair is bound to a different ELF, `4a9bcce6fcc15b5f41298073ad0d8c37304528ec1148aac33bf2caf7757ba41e`, with the same data ISO hash. The interpreter result reached `m2-ui-map-loaded` and remained stable 30.0878 seconds; recompiler reached it and remained stable 25.0920 seconds. Both use `-elf ... -- <data ISO>` (not boot-from-disc). The recompiler screenshot [`pcsx2-viewport.png`](../../build/hcu-ps2-closure/emulator-m1-recompiler-2ece2e90b9854867bdaa6743fd117dfb/pcsx2-viewport.png), SHA-256 `82e7b3dab039d12eb5ce065ee0cb5473e3907a1716f7cdf4a7c7f873fd248e42`, is an all-black game viewport. This proves a UI scenario-load marker on that older binary, not visible UI, scene rendering, or behavior of the current rebuilt ELF. The detailed run audit is [`m2-final-guest-run-audit.md`](m2-final-guest-run-audit.md).

## Required next evidence

1. For ordinary M2 iteration, launch the exact rebuilt ELF through `tools/test_hcu_boot.py` with `--elf` and, if desired, the data ISO via `--disc`; never choose the data ISO as the executable/BIOS boot image. Fix the current display route first, then retain the current ELF hash, command, settings hash, result, and guest log. The current attempt produced no guest evidence.
2. If boot-from-disc acceptance is desired, rebuild `hcu-m1-boot-disc.iso` with the exact current combined ELF as `BOOT.ELF`, preserve the `SYSTEM.CNF` target and asset files, hash the ISO and embedded ELF, then run the harness with `--boot-from-disc --disc <new ISO>` and confirm guest entry. Do not treat `xorriso` file-listing alone as BIOS acceptance.
3. If the BIOS prompt is seen again, record whether PCSX2 is booting the data ISO, boot-disc ISO, direct ELF, or a physical device, and retain the PCSX2 command/log. Then distinguish an unrecognized boot medium from a guest that loaded and later halted.
4. Neither the historical stable UI-load marker nor memory-ready qualifies rendered output. Current-source render acceptance requires a visible screenshot or equivalent frame evidence tied to the exact current ELF and a passed M2 render gate.

## Evidence and limitations

Commands used read-only in this audit: `sha256sum`; `file`; `readelf -h/-l`; `xorriso -indev ... -report_system_area -pvd_info -find / -type f -exec lsdl --`; `xorriso -report_el_torito`; `isoinfo -R -l`; `strings`; and the recorded result/log inspection. The `BOOT.ELF` digest was computed directly from ISO sectors (LBA 33, exact file length 4,457,068 bytes) and matched the staging copy’s hash. REA recognized/fingerprinted the two ELFs, but does not currently supply a supported MIPS/R5900 decompiler. No PCSX2 process was launched as part of this report-only pass; the report checks retained run records. No source, ISO, ELF, or emulator settings were modified.

## Current M2 lifecycle-image reconciliation (2026-10-21)

The current PCSX2 lifecycle evidence uses the dedicated test-profile ELF `build/hcu-parent-link-probe/hcu-gameplay-machine-m2-ui-lifecycle.elf`, SHA-256 `8d3c9aa1dba93b2ad77ef0b37b32ed39d4ad7ad3a33b634ab8521b19bb3ec222`. The preserved earlier M2 fault ELF remains `b347420832736d5370c3dfa338522b9849d1cc1e726d554d0590ead49fb9c970`. Both are ELF32 little-endian MIPS/N32 R5900, entry `0x001010b0`, with the same flags `0x20920025`; the test-profile image has a larger load range, so raw ELF size/segment deltas are not a controlled one-function code comparison. It is a diagnostic lifecycle build, not a production/playable image.

REA 6.5.0 independently fingerprinted the preserved failure ELF and the exact lifecycle ELF by SHA-256 as MIPS. Its live provider inventory rejects machine-specific MIPS variants for the configured Ghidra lane, rejects MIPS for Hopper, and reports no configured/verified MIPS lane for IDA. Thus this turn has REA artifact-identity evidence but no REA pseudocode, call graph, or data-flow claim. For code/data interpretation, use the already established source/layout evidence in [`m2-exact-artifact-and-postmarker-fault.md`](m2-exact-artifact-and-postmarker-fault.md): the older post-marker `Address Error` data addresses fell inside CE `game_state`, and the PS2 HaloScript fix aligns the actual returned byte-stack pointer in `hs_stack_allocate` (`submodules/halo-ce-universal/source/hs/hs_runtime.c`, documented with the source/layout analysis there). The fault address was not an EPC and does not alone identify the writer.

The exact test-profile ELF was run through the harness with `boot_from_disc=false`, the same data ISO `79f2855a5953483637ca060e778589a9f8c54e5fc4cda4a69347f22484457d79`, and the same source commit IDs (parent `70e2ed0cf2145a45d23aa07414a3a88c05155d4c`, HCU `6933490b2d16bb1c637295b6a0f3880ba23a7d56`, halo-ps2 `71183bb0a9adc586cd267b2780c82bbc12cfd95b`). The interpreter and recompiler result records both report `m2-ui-lifecycle-marker-stable`, completion of two unload/reload cycles, and five fault-free seconds after the marker; they bind to settings hashes `a1711c6251ac6fea704efbd4f5cc72e65a44a89a3a3dbc5a95d2c6f4675d3d63` and `8b36509c24363a25eedb063384af4df18b69699b5f068cf2064c8889577d34f1`. Their result/log hashes are recorded by the files themselves and currently recompute to interpreter `3ed8f024b2957a320a1ce9429f302af9a940bb63f4fc971fa4b97eab3eeb0d84` / `aa064e6dc669d39f631525cd841b86eec6354e1c6aa9fab31d7fe6182bdf4a58`, recompiler `ad04f74b56ccd5824282a5b556faeed5c30ad890c6edad1acaff00299eba9167` / `984f73c202686a4202030ae0aeda766a322851c99335ca572e55a5bcb96e61ad` (result/log respectively). Both logs show the UI asset HLE host root and UI lifecycle markers; neither is a gameplay-map or renderer acceptance run and neither retained a viewport screenshot.

A fresh direct PCSX2 rerun in this session reproduced the same lifecycle result on both modes for the exact same ELF, disc, and source pins. Interpreter run `emulator-m1-interpreter-a8adce4666154b03a83bc42989ea4a20`: result/log SHA-256 `c8ddd34b1a4dc6005f670de6d416649499fbf6466b1fe957f1120a678ea127c2` / `3c90cafeabff3e1f22e79b0729303ab5b42a3906b2e9a389a91987be9ca40dc4`, settings `7e9d6f92368b5f63edda31ef39c5d42fa6b835739f88696493e78c76f978faae`, 5.015 s stable. Recompiler run `emulator-m1-recompiler-33230a6978924fcca86118febd8b2329`: result/log SHA-256 `db4b11267a442845b59a0654df6ae7764c1efdc1ddac61419cd5b3b6a418adca` / `91056a30d888c0474ebfd1f82bc9e4e261a2084f7af4b0528d2db323edcb97c5`, settings `8a16a4b80fb00ed413ad43f4122cf1c8d7c2b4cae39ee26c39eed749192c4eab`, 5.019 s stable. Each logged both lifecycle cycle completions, expected fixed owner baseline/high-water, unchanged host UI MAP/HP2 hashes, and no post-marker fault. The runner itself exits PCSX2 after the success window; this successful lifecycle test is not intended to leave an interactive game window open.

This narrows the supplied BIOS-screen question: the screen is not a frame from the game. The data ISO is for `-elf ... -- <ISO>` mounting and is not a boot disc; booting it directly has no `SYSTEM.CNF`/`BOOT.ELF`. The current lifecycle harness proves direct-ELF guest execution on its exact image, but it deliberately stops after a lifecycle marker and does not capture/render a gameplay scene. A BIOS fallback after selecting the data ISO or after leaving/terminating a guest is consistent with the screenshot; without an exact matching launch record, which route produced that particular screenshot remains unknown. A scene screenshot is still required for any claim that the game renders.
