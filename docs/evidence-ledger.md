# Evidence ledger

M04's host scenario has been repeated. This record keeps that source-derived result separate from REA.

## REA session

`binary_session` was called with no target. `open` is false. No binary was opened and no Evidence ID was produced.

| Field | Observed value |
|---|---|
| Package | `rea-agents` 6.5.0 |
| Server | `rea` 6.5.0, started `2026-10-18T01:23:57.503Z` |
| SDK | server, client_test, and core `2.3.1` |
| Protocol | `2025-11-25` |
| Client | Cursor 1.0.0 |
| Catalog | 207 MCP tools, tools SHA-256 `805433f17bb4f709558ff20c04f96fe561fca2938fd0f459b1f8cc0f6b438ded` |
| Ghidra | available, 12.1.4 |
| Hopper | available at the user-local launcher |
| IDA | unavailable, `REA_IDA_MCP_CONFIG` is not set |

REA does not claim support here for an Xbox executable, R5900 disassembly, VU microcode, or emulator control. No such artifact was supplied, so those capabilities were not tested.

## Reference workflow

No emulation of the original console is part of this workflow, and no firmware or disk image for it is requested or stored. Scenario `integer-math-host` was run twice on the ILP32 host harness. Both runs produced the same canonical result, outcome `passed`, seed `1`, tick count `0`. The scenario has no map and no camera, so it has no framebuffer to compare in PCSX2. That visual check remains for a later scenario that has a camera. PCSX2 is installed at `~/.local/bin/pcsx2`. The user supplied a PS2 ROM0 and sidecars under `~/Documents/Halo`. The supplied BIOS booted visibly from an ignored profile copy. M06 passed both full 600-second platform runs and retained-evidence qualification. M07 execution remains pending. See [emulator evidence](emulator.md).

## Source-derived scenario

| Field | Value |
|---|---|
| Question | Do the frozen integer-math operations repeat on the host? |
| Artifact | None. The input is pinned source, not a shipped binary. |
| Tool | Host harness `make reference-scenario` |
| Evidence IDs | None. REA was not used. |
| Observation | Two runs returned identical canonical JSON with outcome `passed`. |
| Inference | The pinned integer-math closure is stable under this host scenario. |
| Limitation | This does not prove retail behavior or R5900 execution. |
| Resulting test | `tests/test_reference_scenario.py` |

## Source findings kept separate

The frozen integer-math closure and the NTSC video startup described in `source-audit.md` come from reading the pinned source trees. They are not REA findings.

## M06 platform acceptance

The accepted runs are `platform-interpreter-a0d37b6cfabc46fdab57f2a9b191d5eb` and `platform-recompiler-87ed53e831be4efb97514515817cac1c` under ignored `build/emulator/runs/`. Both report 35965 frames, Start/Cross input, fixed heap `1261568`, chain high-water 20/64 and intact guards over 600 guest seconds. The common ELF SHA-256 is `b62363fc5a536dede9db7ca886b4b6c4017bf0dc775bc4948c9873ff0484f711`. Presentation RGB hashes match (`7d69dda01f9f01a6a49fa446ff02df1533438c534d540f996205d894c6318e71`). `platform-qualification.json` retains independent log/configuration/identity/capture checks. This is synthetic emulator evidence, not retail gameplay or real-console qualification; REA was not used.

## M10 resume correction evidence (incomplete milestone)

- Corrected fixed view: `build/emulator/runs/world-recompiler-24b291464c9445dc99fd327804f60cd4/`; independent reference: `build/reference/bloodgulch-valley.png` (same camera and BSP).
- Corrected pad flight, original object pack: `build/emulator/runs/world-recompiler-2ce3b40f236a4d29bb5669fe264e5daa/`; 3,001 frames, five recorded waypoints, zero logged drops.
- ELF parity: `build/emulator/world-elf-parity.json`; corrected ELF `e16df34e5d80a87d5e023b6d7f84dacfe5b329a49fc17f82dc141c0c75009726`.
- Static-sky variant: `build/convert/bloodgulch.json`; repeated pack identity and geometry bounds pass. Historical conversion report retained at `build/convert/bloodgulch-pre-m10-sky.json`.
- Corrected five-minute routes remain pending. No physical-console performance claim is made.
