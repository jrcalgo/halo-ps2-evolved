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

## M10 closure — Passed

- Qualifier: `python3 tools/qualify_world.py`; report `build/emulator/world-qualification.json`, SHA-256 `7750a9957ea65a5bd482252a01b26f467d9c93ed13b32e4e4d44c26398b731d8`.
- Current fixed/pad/route identities and results are indexed inside that report. Both CPU modes completed 9,001 route frames. All 12 captures per mode were visually reviewed.
- Interpreter route: `build/emulator/runs/world-interpreter-b6102d1b20874900b675f00ecbf1c44d/`; recompiler route: `build/emulator/runs/world-recompiler-fa69cc52b952440eb3922b5870093d61/`.
- Static-world emulator acceptance only. Sky animation, full Xbox shader equivalence, gameplay integration, streaming stress and physical-console performance are outside this result. See `world-viewer.md`.

## M11 checkpoint — Incomplete

- Host topology and 448 camera colour/depth comparisons: `build/visibility/audit.json`, retaining a unique run under `build/visibility/runs/`. Pre-fix near-plane failure: `build/visibility/audit-before-near-plane.json`.
- Cache negative control: `build/visibility/cache-before.json`; corrected regressions are `tests/texture_residency.c` and the existing upstream cache invariants.
- Guarded ELF parity: `build/visibility/elf-parity.json`; ELF `e002209c53d2a1f239cd1c3c3d50001c4837b83b70fc710d4835188b12219dfa`.
- Four current visible diagnostics and raw frame hashes: `build/visibility/framebuffer-comparison.json`. Exact culling on/off equality within each CPU mode; 23 cross-mode baseline pixel differences are recorded separately. Earlier unsafe unguarded readbacks do not qualify.
- Native/container suites: 39 project tests and 12 upstream synthetic suites. Remaining M11 gates are explicit in `visibility-streaming.md` and section 14 of the governing plan.

- M11 staging lifecycle checkpoint: `tests/test_staging.py` compiles the parent C state machine with C11 warnings as errors and passes cancellation, exhaustion, stale completion and failed-read cases. Synthetic host-only evidence; no EE or GPU ownership claim. See `docs/visibility-streaming.md`.

- M11 EE reader checkpoint: `tests/test_staging.py` now also runs the actual worker with a pthread/semaphore SDK shim and a deliberately delayed read; cancellation, mailbox handoff and drain/shutdown checks pass. `tools/build_streaming.py` cross-compiles both objects with the R5900 compiler and installed SDK headers. Report: ignored `build/streaming-ee/result.json`. Object-only build; no EE execution or viewer integration claimed.

- M11 visible worker integration: separate `stream` viewer, three synthetic cancellation/reload/content/drain cycles, exhausted slots and EOF rejection run alongside Blood Gulch rendering. Interpreter and recompiler complete 181 frames with zero logged drops. SDK owner-priority starvation was reproduced and resolved by diagnostic owner/worker priorities 64/30. Native/container ELF section parity passes. See `docs/visibility-streaming.md` for run IDs, reservation and scope limits; full map unload/cache/GPU acceptance remains open.

- M11 transactional upload checkpoint: actual chain/upload/cache C regression covers full-chain capacity boundaries, rollback and re-upload after failed claims. All 42 project tests and 12 upstream suites pass natively. Updated stream viewer passes a visible 181-frame recompiler diagnostic; native/container allocated ELF parity passes. Fork `f322272`, dependency lock and recovery bundle agree. See `visibility-streaming.md`; async texture lifetimes and full unload/churn remain open.

- M11 cache churn checkpoint: deterministic 200,000-operation cache stress validates map/page/CLUT ownership. It found cancellation could evict committed residents; local halo-ps2 fork `8236f72` adds pending-claim state and commit/cancel rules. Capacity-boundary upload rollback regressions remain passing. Visible recompiler rerun passes 181 frames with zero logged drops and all stream markers. See `visibility-streaming.md`.

- M11 map teardown checkpoint: visible PCSX2 interpreter and recompiler stream-viewer runs each complete three renderer teardown/arena reset/BSP+texture+object reload cycles. Every cycle returns map arena use to 5,279,024 bytes, equal to the initial baseline. Both complete 361 diagnostic frames and render Blood Gulch afterward. Deliberate synchronous reload work causes three dropped frames; this is lifecycle evidence, not steady-state performance. Interpreter final capture was visually inspected. Detailed logs, captures, run identities, and partial memory snapshot are in `visibility-streaming.md`. M11 remains incomplete: actual rendered cache churn, async texture-page lifetimes, broad EE routes, full memory mapping, and hardware verification remain open.

- M11 constrained-cache pixels: visible PCSX2 recompiler and interpreter each sweep 12 fixed views with a 96-page cache cap and record nine actual evictions. Each frame-300 guarded GS readback has zero differing pixels versus its same-mode uncapped baseline, and the captured-frame profiler reports no failed/deferred texture requests. The complete sweep logs 1,426 failed allocation attempts, so this is one clean sampled-view result rather than route-wide texture completeness. Reports `build/streaming-ee/cache-stress-{recompiler,interpreter}.json`; captures and run logs remain private under the corresponding ignored run directories. See `visibility-streaming.md`.

- M11 milder cache cap: the same sweep has no probed cap that both evicts and admits every request. At 168 pages each CPU mode records one eviction and one failure, and raw frames 120, 240, and 300 match the uncapped same-mode image. Caps at 172 pages and above do not evict. Reports `build/streaming-ee/cache-stress-168-{recompiler,interpreter}.json`. Cache-churn acceptance remains open.

- M11 lightmap DMA lease: after map reload, both CPU modes read compressed `LM0` through the staging worker, match page 0 against the loaded lightmap, and refuse to release that slot until GIF DMA of its 8192 bytes completes. The renderer then drops texture claims so the same frame uploads them again. Qualified runs are `world-stream-recompiler-5c8799f2b67a48d4b6ca8e3693a26183` and `world-stream-interpreter-4f81679a508745f3baffcadfa75d962c`.

- M11 staging cache miss: the same diagnostic then copies all 16 BSP mip0 images (299,040 bytes) into two staging slots, poisons the arena copies, and serves one forced rebuild from the lease. Release waits until the next frame's GIF DMA. Recompiler `world-stream-recompiler-889aa026a06a4286b4198d19a172816f` and interpreter `world-stream-interpreter-cfbbe1668b754f54bee51f793630c6d6` both pass, and the recompiler's final capture still shows Blood Gulch. The callback returns to the arena source after that frame. The 524,288 leased bytes stay inside the existing 1 MiB pool (`docs/memory.md`).

- M11 closure: inside-camera portal and conservative frames match in both CPU modes, with portal counts 83 against 0. The 168-page sweep evicts once, fails zero requests, and matches three raw frames per CPU mode. The EE memory-map probe reports kernel below `0x00100000` and heap end `0x01fdf000` unchanged by SIO2MAN and PADMAN. Budget version 2 is the account. Physical hardware remains M23.
