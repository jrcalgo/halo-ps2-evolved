# M2 Group A current-artifact PCSX2 run

Date: 2026-10-21

## Result

The newest integrated machine ELF in `build/` is
`build/hcu-parent-link-probe/hcu-gameplay-machine.elf`, SHA-256
`72fe0034df7a70a13e26d95ef470006054e6e5ff5425170c89a80e98b2319ff2`.
Fresh Group A attempts were made in both requested PCSX2 modes using the
existing `tools/test_hcu_boot.py` harness and `--stage m2-ui`. Neither attempt
started the guest: the PCSX2 process exited with status 127 before creating a
guest log. Consequently, this run provides **no new guest evidence** and does
not establish whether this ELF reaches `m2-ui-map-loaded`.

The failure is host display/Qt launch infrastructure, not a guest crash. Both
`launcher.log` files report that Qt could not connect to configured display
`:0.0` and could not initialize its XCB platform. The per-run `emulog.txt` is
absent/empty, `reached_success_marker` is false, and the harness reports no
guest fault or post-marker interval. I also confirmed no Xorg/Xvfb/Xwayland or
PCSX2 process was running at the time. No data ISO was booted.

## Exact inputs and run records

| Field | Value |
|---|---|
| Parent commit | `70e2ed0cf2145a45d23aa07414a3a88c05155d4c` |
| HCU commit | `6933490b2d16bb1c637295b6a0f3880ba23a7d56` |
| halo-ps2 commit | `71183bb0a9adc586cd267b2780c82bbc12cfd95b` |
| Source-tree state | HCU and halo-ps2 worktrees are dirty; these commits alone do not identify all compiled source bytes. See each `result.json` and current worktree for the run boundary. |
| PCSX2 binary SHA-256 | `0c46bb6a88aa2782b10853a7b07cf3387ba99cbef2b966372cd2315b8571abea` |
| BIOS SHA-256 | `b0bf7184d50a209cf7ceb1ab0eb3a0c9b8c583f5f6b3c819e6536f282b93063b` |
| Data ISO SHA-256 | `79f2855a5953483637ca060e778589a9f8c54e5fc4cda4a69347f22484457d79` |
| UI map SHA-256 | `8556b647b82742d07282fe4e6db0cf847b542c046484e91e71ec31fea5f5fd7e` (33,582,080 bytes) |
| UI HP2 SHA-256 | `a83ded5049128dc0287b975af9c17f4224e467ad5e10ffa079468934e6241e90` (286,720 bytes) |
| Asset root | `build/hcu-parent-link-probe/` (`host:/maps/ui.map`, `host:/maps/ui.hp2`); manifests before and after are equal in each result record. |
| Boot mode | Direct `-elf`; ISO passed after `--` only as data source (`boot_from_disc=false`). |

Interpreter run directory:
`build/hcu-ps2-closure/emulator-m1-interpreter-7ceb9d35356749efad9f261c87f1e141`

- Settings SHA-256: `174dd6ec0f02ad73d0a44b262834dff9d05b914ec64fc4b19061aabc77830f15`
- `result.json` SHA-256: `4d83c990c170d352032dcccbce03d1fbafcdd98720ac1c114438fa39e476bb32`
- `launcher.log` SHA-256: `d4e353e3b1e7915bdb756934b4a16682ffca01f8ecc1cad9cff77b91ca6ff779`
- Guest log absent; status `failed`, process exit 127, marker not reached.

Recompiler run directory:
`build/hcu-ps2-closure/emulator-m1-recompiler-3ecfffa85f374362a60614a12c7fcffc`

- Settings SHA-256: `a490ebf91e7ff10ba1b5a56dec6ea17a18acf5b162a3b4f6453372c687b3f689`
- `result.json` SHA-256: `05010860613bc44f7908136275f5fa8ac63b0d9a0bc7ad98b65337e92e16d998`
- `launcher.log` SHA-256: `d4e353e3b1e7915bdb756934b4a16682ffca01f8ecc1cad9cff77b91ca6ff779`
- Guest log absent; status `failed`, process exit 127, marker not reached.

The failing launcher output in both modes is:

```text
qt.qpa.xcb: could not connect to display :0.0
qt.qpa.plugin: From 6.5.0, xcb-cursor0 or libxcb-cursor0 is needed to load the Qt xcb platform plugin.
qt.qpa.plugin: Could not load the Qt platform plugin "xcb" in "" even though it was found.
```

The bundled XCB cursor library exists in the extracted AppImage, but adding its
directory to `LD_LIBRARY_PATH` and the bundled plugin directory to
`QT_PLUGIN_PATH` did not change the outcome: the current display socket has no
live X server. Thus the actionable failure is unavailable display service;
the generic Qt dependency message is not proof that installing a library alone
will fix it.

## Commands

```sh
APPIMAGE_EXTRACT_AND_RUN=1 python3 tools/test_hcu_boot.py \
  --mode both --stage m2-ui --stable-seconds 5 --timeout 180 \
  --elf build/hcu-parent-link-probe/hcu-gameplay-machine.elf \
  --disc build/hcu-m1-disc-data.iso

APPIMAGE_EXTRACT_AND_RUN=1 python3 tools/test_hcu_boot.py \
  --mode recompiler --stage m2-ui --stable-seconds 5 --timeout 180 \
  --elf build/hcu-parent-link-probe/hcu-gameplay-machine.elf \
  --disc build/hcu-m1-disc-data.iso
```

The first command stopped on the interpreter launch failure, so the recompiler
was separately attempted with the second command. Both failed before guest
startup for the same host-side reason. The pre-existing plan evidence for
`72fe0034…` remains historical evidence; these unsuccessful fresh attempts do
not supersede it, but neither do they refresh its runtime qualification.

## Group A disposition

This run does not satisfy the current-image Group A guest UI check. To resume,
provide a live display server/session accessible to the PCSX2 process (or an
equivalent supported headless Qt setup), then rerun both modes with the same
ELF/assets and fresh run directories. A successful guest run must show the
`m2-ui-map-loaded` marker and its requested stable post-marker interval; that
still proves only UI package load, not gameplay-map capacity or visible scene
rendering.
