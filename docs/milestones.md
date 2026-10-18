# Execution status

Governing specification: [detailed plan](../plans/0.native-ps2-halo-hybrid-port.md).

Status reviewed 2026-10-18. A milestone is complete only when every required acceptance gate has evidence. Compilation does not establish runtime behavior. A dedicated local commit is made when each milestone closes.

## Handoff — 2026-10-18

Resume baseline is `1d04512`; the platform checkpoint is `0b8ce41`. M00–M05 are complete. M09 closed at `e6eb7e5`. M06 is checkpoint `0b8ce41` and stays open. M07 is compiled only. M08 and M10–M22 have not started. M10 waits on an executed M06. M23 stays blocked on a physical console.

Blood Gulch, Xbox build `01.10.12.2276`, converted twice. BSP SHA-256 is `55ab30028ccd76aa5a3358d062988480c9142fb9b89de2f7a50321b4f4452c09`. The largest axis error is `0.001114` inside the declared bound `0.001116` over 5503 triangles. Pack sizes are 405504, 2344960, and 350208 bytes. Inputs and packs stay under ignored `data/retail`.

`make platform-elf` links the pad poll, GIF/VIF DMA setup, VU1 upload, NTSC video, and the synthetic texture self-test. The self-test draws sprites. The ELF SHA-256 begins `109ca0eb70732463`. No frame was captured. The probe ELF SHA-256 begins `a006fb06e5b26025` and its status is `compiled`.

PCSX2 is installed at `~/.local/bin/pcsx2`. The user supplied PS2 BIOS files under `~/Documents/Halo`; ROM0 has a valid ROM directory (ROMVER `0110AC20000727`). Copies and writable sidecars are isolated under ignored emulator output. The interpreter run, the recompiler run, controller logs, the ten-minute smoke, and the EE integer-math comparison have not run.

A converted multiplayer map and a startup ELF are on disk. Nothing has booted Halo, drawn Blood Gulch, or moved a player.

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
- Converter imports are Python standard library only. `make test-host` passed 17 infrastructure tests, including resource accounting, and 12 synthetic converter checks. Real map checks skipped.
- DVP `world.vsm` object bytes match across environments (SHA-256 `b98e92d27413ade70bfcefa15b78408ffd033376791c9c8f9641fb90f63ca136`). That is assembly parity, not VU execution.
- No PS2 runtime, emulator, or hardware behavior is claimed.

## M04 — Complete

`make reference-scenario` runs `config/reference-scenarios/integer-math-host.json` twice through the ILP32 host fixture. Both runs return the same canonical result: outcome `passed`, seed `1`, tick count `0`. The scenario has no map and no camera. It proves the pinned integer-math closure on the host and does not prove retail behavior. A PCSX2 framebuffer comparison does not apply to this scenario. REA recorded no opened target; source findings stay separate in `evidence-ledger.md`.

## M05 — Complete

`make test-host` runs `tests/test_resource_accounting.py`. The audited `halo-ps2` `arena_*` functions pass alignment, exhaustion, scratch reset, future-mark rejection, and size overflow on LP64 and ILP32 hosts, with identical check records. `config/memory-budget.json` totals 32 MiB and preserves the 5.5 MiB reserve. Overlapping claims fail. Steady-state allocations and pool exhaustion are reported in scenario results. This is host accounting, not EE runtime validation.

## M06 — In progress

`make platform-elf` links `src/platform/main.c` with the pinned pad, GIF/VIF DMA setup, VU1 microcode upload, NTSC video path, and synthetic texture self-test. The native ELF SHA-256 begins `109ca0eb70732463`. The ELF was not executed. PCSX2 is installed at `~/.local/bin/pcsx2`, and the user has now supplied a PS2 BIOS; interpreter, recompiler, controller logs, and the ten-minute smoke remain pending.

## M07 — In progress

`make probe` compiles and links the frozen integer-math closure for R5900. The result status is `compiled`, and the native ELF SHA-256 begins `a006fb06e5b26025`. The ELF was not executed, so host/EE comparison and the no-silent-stub acceptance are unmet. The ILP32 host result remains a separate host check.

## M08 — Not started

The hybrid proof has not run. It waits on M06 and M07 execution, which have not happened.

## M09 — Complete

`MAP=bloodgulch make convert` decompressed the locally configured Xbox cache, build `01.10.12.2276`, and converted it twice. The BSP, object, and texture pack hashes match across the two clean output directories. BSP SHA-256 is `55ab30028ccd76aa5a3358d062988480c9142fb9b89de2f7a50321b4f4452c09`. The largest axis error is `0.001114` against the declared bound `0.001116` over 5503 triangles. Pack sizes are 405504, 2344960, and 350208 bytes, inside the BSP, resident-gameplay, and texture-cache regions. Truncated and bad-magic headers fail in `tests/test_convert_map.py`. Retail inputs and packs stay under ignored `data/retail`.

## M10–M22 — Not started

M09 is closed. These milestones have not been started. M10 waits on an executed M06, and each later milestone waits on its own gate.

## M23 — Blocked

No physical console, storage backend, or operator setup is available. Hardware qualification has not started.

## Next actions

1. Finish M06’s textured VU1 triangle, presentation and polling loop, then execute visibly with the supplied BIOS and retained emulator evidence.
2. M09 has a local Blood Gulch pack. M10 still waits on an executed M06.
3. Do not treat `make probe` or `make platform-elf` as passed runtime gates.
