# Evidence ledger

M04 remains incomplete. This record separates source inspection from REA and records the reference workflow still to be defined.

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

No emulation of the original console is part of this workflow, and no firmware or disk image for it is requested or stored. Expected results come from the pinned original source through the host harness, and for visual checks from the independent software renderer in the pinned `halo-ps2` tree compared against PCSX2 framebuffer output. One repeatable source-derived reference scenario still needs to be defined, so a reference scenario is not yet established. `pcsx2` is not on `PATH`; that absence remains an M06 and M07 execution blocker, recorded separately from M04.

## Source findings kept separate

The frozen integer-math closure and the NTSC video startup described in `source-audit.md` come from reading the pinned source trees. They are not REA findings.
