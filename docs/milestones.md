# Execution status

Governing specification: [detailed plan](../plans/0.native-ps2-halo-hybrid-port.md).

Status reviewed 2026-10-18. A milestone is complete only when every required acceptance gate has evidence. Compilation does not establish runtime behavior. A dedicated local commit is made when each milestone closes.

**Current state:** M00–M12 complete; M13 in progress with a host-only combat checkpoint; M14–M22 not started; M23 waits on physical hardware. The older handoff below records the state at its own checkpoint and is retained for provenance.

## Handoff — 2026-10-18

Current implementation baseline is `64aa289`; the M10 closure is recorded below. M00–M10 are complete. M06 closed at `9f57c87`, M07 at `722778f`, and M09 at `e6eb7e5`. M10’s corrected fixed view, free-camera traversal, both inward-facing routes and final retained-evidence qualification pass. Earlier route runs used a visually defective renderer and are historical evidence. M11 is in progress; M12–M22 have not started. M23 stays blocked on a physical console.

Blood Gulch, Xbox build `01.10.12.2276`, converted twice. BSP SHA-256 is `55ab30028ccd76aa5a3358d062988480c9142fb9b89de2f7a50321b4f4452c09`. The largest axis error is `0.001114` inside the declared bound `0.001116` over 5503 triangles. Current static-sky variant pack sizes are 405504, 2441216, and 350208 bytes; the original object pack remains preserved. Inputs and packs stay under ignored `data/retail`.

`make platform-elf` links the pad poll, GIF/VIF DMA setup, VU1 upload, NTSC video, and the synthetic texture self-test. The self-test draws sprites. The ELF SHA-256 begins `109ca0eb70732463`. That checkpoint had no runtime capture. The later triangle now executes visibly; see M06 below. The accepted integer-math probe ELF is `7917b2cdca5c9b9e40f62998ab46081a95a1b730ca4267611f7228a05f8ab824`; see M07 below.

PCSX2 2.8.2 is installed at `~/.local/bin/pcsx2`. The user supplied PS2 BIOS files under `~/Documents/Halo`; ROM0 has a valid ROM directory (ROMVER `0110AC20000727`). Copies and writable sidecars are isolated under ignored emulator output. Full interpreter/recompiler platform stability checks passed at `9f57c87`. The integer-math and datum EE fixtures passed in both CPU modes and match their ILP32 host results. The hybrid proof passed at parent `722778f`: event hash `1235839601` across three presentation schedules, `elapsed_ms=600033`, in both CPU modes.

The supplied PS2 BIOS, the synthetic triangle, and the Blood Gulch viewer have booted visibly. Player simulation has not run.

## M00 — Complete

Parent Git metadata, workspace permissions, source access, and the initial environment inventory are established. Historical recovery notes are retained in `environment.md`.

## M01 — Complete

- Eleven real submodules are registered, initialized recursively, and pinned to the current parent gitlinks.
- Canonical upstream URLs remain in `.gitmodules`; full upstream/fork commits and bundle checksums are in `config/dependencies.json`.
- Local fork adaptations are backed by complete private bundles before fork-only gitlinks are recorded.
- Repeated offline bootstrap and synthetic fresh-parent restoration/refusal tests pass.
- A fresh no-hardlinks checkout of parent commit `e688717` restored all eleven dependencies using only the private bundles. Both recursive status and each exact commit matched the manifest; the parent remained clean.
- A second `OFFLINE=1 make bootstrap` passed and left all eleven pins unchanged.
- Private bundles are ignored and need a separate backup. Public upstreams cannot restore fork-only commits.

## M02 — Complete

- Source inventory, reuse classifications, and the frozen integer-math compile list are in `source-audit.md`, `gameplay-probe.md`, and `config/gameplay-probe-candidates.json`.
- The compile closure is `halo-64` `source/math/integer_math.c`, `source/math/integer_math.h`, and `source/cseries/cseries.h`. Integer math files match the pinned OpenCE copies. `cseries.h` does not. `cseries.c` is excluded because its include graph is wider than `csprintf` and `temporary`.
- `halo-ps2` pin `a571749c8c8de34c045e363726596989097c604a` is `upstream/HEAD` on `claude/open-decisions-review-75968c`. The renderer, VU1 programs, pack reader, converters, arena, pad, timer, and profiler are present in that tree.
- File-level notices: the frozen gameplay files have no per-file copyright lines and remain under `halo-64/LICENSE.md` (CC0-1.0). Inspected `halo-ps2` sources have no per-file banner and remain under GPL-3.0. Retail rights stay unresolved.
- Locked toolchain commits and checksummed host packages are the build inputs. Umbrella fetch scripts are not the build entry point.
- No gameplay algorithm was modified. PS2 runtime is not claimed.

## M03 — Complete

- Native and container `make toolchain` reports are `passed`: compiler stages 00–09, `sdk-build`, and `sdk-install`. Identities are EE `657b9e646920fda447079be56d915eb4f8a33c25`, IOP `4afa44d71fee30ecfd1aa014f2a11736b824be6a`, DVP `28d83d34d85360988aa32b9a783062d394a7d62e`, and SDK `a3ce5d035ceae1218dc0b83e465d1e5c927d951d`.
- Both environments report `mips64r5900el-ps2-elf-gcc (GCC) 15.2.0` and GNU assembler 2.45.1.
- `make smoke-elf` and `BUILD_ENV=container make smoke-elf` produced `build/platform-smoke/halo-smoke.elf` (`cae68909c4a540801274d63bff384f9825973ad0d74aa11f08769fcb7181d8a2`) and `build/container/platform-smoke/halo-smoke.elf` (`887c3b1794f7f5e8c0cc3eb0b5788bc87c86f57fd0582fc2f432d6957598e4d8`).
- Allocatable ELF sections match, including `.text` and `.data`. File hashes differ because debug strings embed `build/toolchain` versus `build/container` paths and local symbol suffixes differ. The same fixture compiled from `/tmp/halo-ee-anywhere` reproduced the allocatable bytes.
- All 211 IOP `.irx` modules match on allocatable section bytes. Static library file hashes still differ by path metadata.
- Converter imports are Python standard library only. `make test-host` passed 20 infrastructure tests, including resource accounting, and 12 synthetic converter checks. Real map checks skipped.
- DVP `world.vsm` object bytes match across environments (SHA-256 `b98e92d27413ade70bfcefa15b78408ffd033376791c9c8f9641fb90f63ca136`). That is assembly parity, not VU execution.
- No PS2 runtime, emulator, or hardware behavior is claimed.

## M04 — Complete

`make reference-scenario` runs `config/reference-scenarios/integer-math-host.json` twice through the ILP32 host fixture. Both runs return the same canonical result: outcome `passed`, seed `1`, tick count `0`. The scenario has no map and no camera. It proves the pinned integer-math closure on the host and does not prove retail behavior. A PCSX2 framebuffer comparison does not apply to this scenario. REA recorded no opened target; source findings stay separate in `evidence-ledger.md`.

## M05 — Complete

`make test-host` runs `tests/test_resource_accounting.py`. The audited `halo-ps2` `arena_*` functions pass alignment, exhaustion, scratch reset, future-mark rejection, and size overflow on LP64 and ILP32 hosts, with identical check records. `config/memory-budget.json` totals 32 MiB and preserves the 5.5 MiB reserve. Overlapping claims fail. Steady-state allocations and pool exhaustion are reported in scenario results. This is host accounting, not EE runtime validation. Measured EE and GS figures, and the places they overlap this budget, are in `memory.md`.

## M06 — Complete

Both CPU modes passed 600 guest seconds with the same platform ELF: 35965 frames, Start/Cross `[8,16384]`, heap `1261568`, DMA high-water 20/64 and intact guards. Presentation snapshots match exactly. Native/container allocated ELF parity and independent retained-evidence qualification passed. The first full attempt that missed Cross remains classified as failed; it is not the acceptance run. See `emulator.md` for run IDs, hashes and commands. This closes the emulator platform gate; physical-console qualification remains M23.

## M07 — Complete

Prerequisites are M02, M05, and M06 (`9f57c87`). The compiler is `mips64r5900el-ps2-elf-gcc (GCC) 15.2.0`. halo-64 is `17541f4444baabb47d1a0deb917f26ccb7b6bc5c`. PCSX2 is 2.8.2. `make test-emulator SCENARIO=probe` runs `tools/test_probe_emulator.py`, which is the acceptance command. A one-line integer-math success is not acceptance.

At parent `9f57c87`, both CPU modes passed the positive integer-math fixture, the rectangle-boundary mutation, the assertion-expression control, the positive datum fixture, and the stale-handle rejection. Positive results equal the ILP32 host records. Diagnostic expressions were evaluated. The mutation and stale-handle controls were rejected. Integer-math ELF `7917b2cdca5c9b9e40f62998ab46081a95a1b730ca4267611f7228a05f8ab824`. Datum ELF `3613c2999d6a0b032ce5318667521d04482149678e0a79f5b6c2746d8a7db96b`. `python3 tools/qualify_probe.py` rechecked retained logs, CPU flags, hashes, BIOS copies, and visible PNGs. The aggregate is ignored `build/emulator/gameplay-qualification.json`.

`ceiling_log2(1)` was not executed. This does not establish floating-point equivalence, a general object lifecycle, or integrated gameplay. The next step is the M08 EE hybrid proof. See `gameplay-probe.md`.

## M08 — Complete

Prerequisites are M06 (`9f57c87`) and M07 (`722778f`). The compiler is `mips64r5900el-ps2-elf-gcc (GCC) 15.2.0`. halo-64 is `17541f4444baabb47d1a0deb917f26ccb7b6bc5c`. PCSX2 is 2.8.2. `make test-emulator SCENARIO=hybrid` is the acceptance command.

Both CPU modes ran ELF `defae213cf558a118194137d99e5fa8088d9e6f61dd8605c3e1e1e8ebcc7e3ca` for 18,000 ticks. Suppressed, delayed, and normal schedules all reported event hash `1235839601`, matching the ILP32 host. The paced normal schedule reached `elapsed_ms=600033` with heap `1269760` and chain high-water 20. `python3 tools/qualify_hybrid.py` rechecked the retained logs and captures. The record is ignored `build/emulator/hybrid-qualification.json`.

The visible object is synthetic. It is not a Halo player or a retail scene. The next step is M10’s Blood Gulch route. See `hybrid-proof.md`.

## M09 — Complete

`MAP=bloodgulch make convert` decompressed the locally configured Xbox cache, build `01.10.12.2276`, and converted it twice. The BSP, object, and texture pack hashes match across the two clean output directories. BSP SHA-256 is `55ab30028ccd76aa5a3358d062988480c9142fb9b89de2f7a50321b4f4452c09`. The largest axis error is `0.001114` against the declared bound `0.001116` over 5503 triangles. Pack sizes are 405504, 2344960, and 350208 bytes, inside the BSP, resident-gameplay, and texture-cache regions. Truncated and bad-magic headers fail in `tests/test_convert_map.py`. Retail inputs and packs stay under ignored `data/retail`.

## M10 — Complete

Corrected ELF `e16df34e5d80a87d5e023b6d7f84dacfe5b329a49fc17f82dc141c0c75009726` passes native/container allocated-section parity. In PCSX2 2.8.2, the fixed valley view agrees with the independent reference, the pad flight covers five waypoints, and each CPU-mode route completes 9,001 frames. All 12 retained views per mode were inspected. `python3 tools/qualify_world.py` passes current source/ELF/pack/configuration/log/capture checks. No texture failure, clipped-geometry loss or DMA overflow was logged. See `world-viewer.md` for corrected run identities, historical failures, guest profiler data and appearance limits. M11 is next; physical-console performance is unproven.

## M11 — Complete

Portal culling at `(65,-80,9)` matches the uncullled frame in both CPU modes while cutting the view from 20 clusters to 11 and testing 83 portals. The 448 host views already matched. A 168-page sweep evicts one texture, fails none, defers one retry, and matches frames 120, 240, and 300 in both CPU modes. The staging lease holds all 16 mip0 images for 360 frames. Three reloads return the arena to 5,279,024 bytes. Budget version 2 and the EE memory-map probe fit the measured kernel, stack, ELF, arena, DMA, and streaming bytes. Details are in `visibility-streaming.md` and `memory.md`. A physical console has not repeated this. That remains M23.

## M12 — Complete

`test_move.py`, `test_pad.py`, `test_collide.py`, and `test_player.py` pass. The pill settles, jumps, crouches, walks a slope, stops at walls and a corner, and recovers outside the BSP. Scratch is 47,644 bytes. The EE collision walk in `world-recompiler-6faf9afd611e4bf8aaccc40727fa45fd` holds 30 fps at the first start, with the heap break at 16,222 KB of the 27,136 KB committed budget. Object collision is not in this pill. See `player-movement.md`. M13 has not started.

## M13 — In progress

The bounded synthetic host combat state machine and its regression pass. It cross-compiles to an R5900 object. The audit reads all 24 supplied maps and identifies 23 distinct weapon paths, including magazine and trigger records, through the pinned tag index. The current complete host suite passes 55 project tests and 12 upstream synthetic suites after rebuilding the stale portal viewer; the four rendered-movement checks ran visibly. This is a checkpoint, not M13 acceptance: source-equivalent behavior for all retail weapons, BSP hits, player damage and EE combat execution are open. See `combat.md`.

## M14–M22 — Not started

Each milestone waits on its own acceptance prerequisites.

## M23 — Blocked

No physical console, storage backend, or operator setup is available. Hardware qualification has not started.

## Next actions

1. Continue M13 from the source/tag audit in `combat.md`; cover all weapon families and run visible EE combat gates before closure. M14 through M22 stay unstarted.
2. Do not treat the completed 300-second route alone as M10 acceptance.
3. Do not treat `make probe` or `make platform-elf` as passed runtime gates. M07’s runtime gate is `make test-emulator SCENARIO=probe`.

## Current implementation checkpoints

`a7c3bfa` saves M06 implementation, `52a389b` saves M07 fixture preparation, `ac46127` saves M08 host replay preparation, and `87a913f` saves M10 viewer/reference preparation. These are explicitly incomplete checkpoints. That earlier checkpoint passed 25 project tests plus all 12 synthetic converter scripts; the current container suite passes 33 project tests and 12 synthetic suites. Original retail-data checks inside that synthetic suite remain skipped; M09 has its own separate conversion evidence.

### M10 resume correction checkpoint

The free-camera runner reached all five waypoints with corrected renderer ELF `e16df34e5d80a87d5e023b6d7f84dacfe5b329a49fc17f82dc141c0c75009726`, 3,001 frames and zero logged drops. The review also found missing BSP geometry caused by sky-state writes over the BSP matrix, and incorrect first-layer-only sky conversion. Both have scoped local-fork fixes and the fixed view now agrees with the geometry reference. The new static-sky object pack is deterministic across two conversions. At that checkpoint M10 remained incomplete pending corrected five-minute routes; those gates subsequently passed as recorded in the closure below. See `world-viewer.md`; M11 has not started.

### M10 closure — Passed

The corrected recompiler and interpreter routes each finished 9,001 frames with zero logged drops or resource failures. All 12 views per CPU mode were inspected; the independent fixed-view geometry comparison and five-waypoint pad flight pass. `python3 tools/qualify_world.py` rechecked the current retained evidence and passed. Corrected ELF is `e16df34e5d80a87d5e023b6d7f84dacfe5b329a49fc17f82dc141c0c75009726`. Fork `e1d8e11b348d941894873ef9cd0fc02c8b4a635a`, its recovery bundle, and dependency lock agree. Full evidence and limitations are in `world-viewer.md`. Prior pending-status checkpoint entries above are historical. At that closure M11–M22 were unstarted; M11 is now in progress as recorded above. M23 remains blocked on physical hardware.

M11 worker checkpoint: the separate `stream` viewer now executes the bounded EE reader alongside rendering. Visible interpreter/recompiler diagnostics pass three synthetic cancellation/reload/content/drain cycles, exhaustion and short-read discard; native/container ELF parity passes.

M11 map teardown checkpoint: visible interpreter/recompiler stream-viewer runs each pass three actual renderer clear, arena reset, BSP/texture/object reload cycles. Arena usage returns to the exact 5,279,024-byte baseline each time; both finish 361 frames and render Blood Gulch. Three dropped frames are from deliberate synchronous reload work. Actual rendered cache churn, async texture-page/GPU lifetime, broad EE routes, full physical memory accounting, and hardware confirmation remain open. See `visibility-streaming.md` for retained evidence.
