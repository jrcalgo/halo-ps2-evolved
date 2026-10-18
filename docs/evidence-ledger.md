# Evidence ledger

M04 remains incomplete. This record separates source inspection from REA and records the missing reference runtime.

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

## Reference runtime

`xemu` and `pcsx2` are not on `PATH`. No retail ISO, map directory, BIOS, or reference scenario configuration is present. No player action was observed in xemu. A repeatable reference scenario is therefore not established.

## Source findings kept separate

The frozen integer-math closure and the NTSC video startup described in `source-audit.md` come from reading the pinned source trees. They are not REA findings.
