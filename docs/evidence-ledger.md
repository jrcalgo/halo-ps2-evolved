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

No emulation of the original console is part of this workflow, and no firmware or disk image for it is requested or stored. Scenario `integer-math-host` was run twice on the ILP32 host harness. Both runs produced the same canonical result, outcome `passed`, seed `1`, tick count `0`. The scenario has no map and no camera, so it has no framebuffer to compare in PCSX2. That visual check remains for a later scenario that has a camera. `pcsx2` is not on `PATH`; that absence remains an M06 and M07 execution blocker.

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
