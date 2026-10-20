# Source audit — M02 baseline and HCU migration decision

Pins and upstream identities are recorded in `config/dependencies.json`. Findings below are source observations at those pins, not PS2 runtime evidence.

## HCU gameplay migration decision — 2026-10-20

The project has selected the pinned `halo-ce-universal` fork as the production gameplay source, subject to the closure, ABI, memory, and runtime gates in [`5.hcu-remake.md`](../plans/5.hcu-remake.md). This changes the earlier M02 classification below: HCU is no longer comparison-only as an architectural decision, but it is **not yet integrated or accepted as the production runtime**. The pinned source is `7524ba61689a912bdec234d9687b178f0b0e7389` ([dependency record](../config/dependencies.json#L23)). Pinned `halo-64` (`17541f4444baabb47d1a0deb917f26ccb7b6bc5c`) is the method example for compiling that CE source onto hardware it was not written for ([Halo-64 method](../plans/5.hcu-remake.md#L49)). Its N64 ABI, reduced pools, empty stubs, and omitted AI, script, sound, and campaign systems stay on the N64. The compilation is bound by the PlayStation 2 machine and by budget version 2: 32 MiB EE RDRAM, with GS eDRAM, IOP RAM, and SPU2 RAM accounted as separate stores ([hardware and memory](../plans/5.hcu-remake.md#L63)).

| Responsibility | Intended owner | Evidence and boundary |
|---|---|---|
| Object identity/lifecycle, units, movement, physics, collision, weapons, projectiles, damage | `submodules/halo-ce-universal/source/` | `game_tick` orders units, actors, first-person state, game rules, scripts, and objects ([game tick](../submodules/halo-ce-universal/source/game/game.c#L330)); datum handles carry object identity ([datum lookup](../submodules/halo-ce-universal/source/memory/data.c#L145)). This remains a target decision until the R5900 closure passes. |
| AI, scripts, effect simulation, HUD decisions, local game modes | HCU fork, port-marked | AI and scripts execute in the source tick ([actor update](../submodules/halo-ce-universal/source/ai/actors.c#L4200), [script update](../submodules/halo-ce-universal/source/hs/hs.c#L13544)); no Halo-64 campaign cuts are accepted. |
| PS2 rendering, VU1, DMA, video, pad, timer, profiling | Parent and `halo-ps2` | `tools/ee-world.mk` links the existing renderer and platform objects ([EE object list](../tools/ee-world.mk#L5)); the render-oriented object table is currently a parent simulation prototype and must become a snapshot reader ([object table](../submodules/halo-ps2/engine/src/sim/objects.h#L1)). |
| HP2/world/stream readers, offline geometry/bitmap conversion, fixed boot allocation | Parent and `halo-ps2` | HP2 validates bounded sections/CRCs ([HP2 loader](../submodules/halo-ps2/engine/src/stream/hp2.c#L18)); parent memory is arena-based ([arena allocator](../submodules/halo-ps2/engine/src/core/mem.c#L12)). A separate, measured runtime tag-image path is still required. |
| Render/HUD/effect snapshots and PS2 sound playback | Parent adapter; decisions remain HCU-owned | Add a read-only post-tick snapshot and one-way sound requests. Do not let GS/VU1 or SPU2 callbacks become simulation authorities. |
| Current parent `src/game/` simulation | Temporary parity oracle, then retired from production | The play target currently links the duplicate modules ([play link set](../tools/ee-world.mk#L43)); the runtime also imports them directly ([play imports](../src/game/play_ee.c#L1)). Keep them until equivalent HCU fixtures pass. |
| OpenCE desktop/online implementation and Halo-64 N64 platform objects | Excluded from the EE build | Follow Halo-64's method: compile HCU `source/` behind a dedicated `port/ps2` layer ([N64 build](../submodules/halo-64/tools/n64_build.py#L11), [platform split](../submodules/halo-64/port/n64/src/platform.h#L4)). The Linux manifest's SDL dependencies, and Halo-64's big-endian ABI, reduced pools, and empty stubs, stay out of that layer ([Linux manifest](../submodules/halo-ce-universal/port/linux/port.json#L3), [N64 prefix](../submodules/halo-64/port/n64/include/halo_n64_prefix.h#L15), [N64 stubs](../submodules/halo-64/tools/n64_stubs.py#L6)). |

The single-owner rule applies to collision as well as object identity: CE collision becomes authoritative only after its BSP/model data is available from the converted map image and its R5900 call closure is measured. Parent collision modules remain comparison code until then. The parent plan's local multiplayer, bots, AI, and campaign scope is unchanged ([governing scope](../plans/0.native-ps2-halo-hybrid-port.md#L67)).

Special-weapon ownership is also fixed: the supplied CE map tags drive the fuel rod through HCU's generic weapon/projectile system; the parent fuel-rod pose fallback is not retained. The energy sword and gravity rifle remain supported port features, with gameplay in HCU and only PS2 presentation adaptation in the parent ([tag inventory](../docs/combat.md#L23), [special pose mapping](../src/game/hold_pose.h#L31)).

**M0 progress:** source ownership is recorded; the full compile/link closure, ABI assertions, runtime tag-image design, and initial R5900 linked slice remain open. Nothing in this decision table claims PS2 execution or parity.

| Component and source | Disposition | Dependency/platform assumptions | Validation required |
|---|---|---|---|
| N64 boundary: `halo-64/tools/n64_build.py`, `port/n64/include/halo_n64_prefix.h`, `port/n64/src/xdk_*.c`, `port/n64/game/n64_game.c` | Method example for compiling CE source onto unintended hardware; implement a separate PS2 boundary | libdragon, VR4300 big-endian ABI, and N64 services stay on the N64. The transferable shape is a source manifest, a force-included prefix, XDK replacements type-checked against the game's declarations, and a game-side file that owns the local session, memory map, and cache | Enumerate that shape, then compile the selected closure with the R5900 compiler |
| Integer math: `halo-64/source/math/integer_math.c`, `.h` | Probe candidate; source hash matches pinned OpenCE copy | cseries scalar types, diagnostics, string helpers, and 32-bit `long`; LP64 changes bit-vector semantics | Existing ILP32 fixture passes selected operations and a fault-injection negative control; add R5900 compile, result comparison, and domain coverage |
| Random math: `halo-64/source/math/random_math.c`, `.h` | Defer pending closure | cseries/windows, real/geometry/game-engine state, random globals and time initialization; header is absent from pinned OpenCE tree | Compare source differences and seed/init behavior; compile only after deterministic boundary is designed |
| Datum management: `halo-64/source/memory/data.c`, `.h` | Probe candidate after ABI boundary | cseries and diagnostics, 32-bit pointer/long assumptions, pointer-bearing 0x10-byte data iterator layout | Add layout assertions and allocate/delete/reuse/stale-handle/exhaustion fixtures on host and EE |
| PS2 renderer: `halo-ps2/engine/Makefile`, `src/render/`, `src/vu1/` | Adapt in PS2 fork behind parent interface | PS2SDK EE/GS/VIF APIs, DVP assembler and VU1; renderer owns DMA/GS, gameplay layer must not | Toolchains are built; EE/VU runtime checks and physical PS2 gates remain pending |
| Pack readers/onverters: `halo-ps2/tools/halo2ps2/`, `engine/src/stream/hp2.c`, `engine/src/world/` | Reuse/adapt candidate | Host Python and user-supplied Halo maps; runtime consumes converted pointer-free PS2 layouts | Synthetic converter suite passes. Blood Gulch now converts twice to identical packs inside the assigned regions; retail bytes stay untracked |
| Arenas: `halo-ps2/engine/src/core/mem.c` | Reuse candidate | PS2 EE alignment and fixed 32 MiB memory ceiling; no unbounded runtime heap | Review overflow, lifetime and alignment; add accounting/high-water/exhaustion tests before integration |
| Gameplay source: pinned `halo-ce-universal/source/` | Selected production implementation target; not yet linked or accepted | Pinned decompilation and port fork require an R5900-specific ABI/platform layer; the Linux source manifest is not the PS2 build list | Generate the selected full compile/link closure, port and validate ABI/layout, load converted tags, then pass integrated source-parity and hardware-budget gates |
| N64 graphics/audio: `halo-64/port/n64/src/n64_render.c`, `n64_sound.c`, `xdk_*.c` | Reference only | N64 RSP/RDP, tiny3d, cartridge and sound APIs do not match PS2 services | Do not transplant; use only source-portability and scheduling observations |
| N64 campaign experiment: `halo-64/port/n64/game/n64_campaign.c` | Exclude from this port | Simplified campaign experiment, not the original campaign closure | Do not treat it as the campaign implementation |
| VU1 programs: `halo-ps2/engine/src/vu1/world.vsm`, `bsp.vsm`, `model.vsm` | Adapt in its dedicated fork | DVP assembler; gameplay must not own VU state | `world.vsm` assembly matched across environments; VU execution is untested |
| VIF/DMA chain: `halo-ps2/engine/src/render/chain.c`, `upload.c` | Adapt in its dedicated fork | PS2 DMA/VIF ownership stays in the renderer | Synthetic VIF/VU/GS execution and bounded chains passed M06 in both CPU modes (see `emulator.md`) |
| Pad input: `halo-ps2/engine/src/platform/pad.c` | Adapt in its dedicated fork | IOP `rom0:SIO2MAN` and `rom0:PADMAN` | Virtual pad initialization and Start/Cross edges passed the M06 full-duration runs |
| Timer and profiler: `halo-ps2/engine/src/platform/timer.h`, `profiler.c` | Adapt in its dedicated fork | EE cycle counter and render timing | Synthetic guest frame/time counters now progress; these are not physical-console performance measurements |
| GS video setup: `halo-ps2/engine/src/platform/video.c`, `render/gs.h` | Adapt in its dedicated fork | PS2SDK graph/draw and GS allocation | Source is present; framebuffer sizes are not yet measured on hardware or in PCSX2 |
| Map converters: `halo-ps2/tools/halo2ps2/*.py` | Reuse substantially unchanged where the synthetic checks apply; adapt in the fork when a real map requires it | Python standard library only (`python3 -I`); user-supplied maps stay untracked | Twelve synthetic scripts pass. `MAP=bloodgulch make convert` produced identical Blood Gulch packs; the map files stay untracked |

## Toolchain findings

`ps2dev/scripts/*.sh` clones shallow references and can fetch and forcibly check out `FETCH_HEAD`. `ps2toolchain/scripts/001-dvp.sh`, `002-iop.sh`, and `003-ee.sh` do the same. `ps2toolchain/config/ps2toolchain-config.sh` selects `main` for separate DVP, IOP and EE orchestration repositories. The three orchestration repositories are now separately pinned; the adapted isolated driver bypasses these upstream fetching entry points.

That initial audit note is superseded by the compiler-closure update below and the current execution report in `toolchain.md`. Native and container compiler/SDK builds are now running from the isolated locked source trees.

`halo-ps2/engine/Makefile` uses PS2SDK `draw`, `graph`, `packet2`, `dma`, `debug`, and `pad`, with `dvp-as`; exporting a GSKIT path does not establish a gsKit link dependency.

## Instructions and provenance

Read `halo-ce-universal/AGENTS.md` before modification. It requires minimal marked game-source changes, preserving arithmetic semantics, and prohibits reading `xbox/include`/Xbox SDK headers. This audit did not read those headers. The repository-level license notices are summarized below; file-level third-party provenance remains pending.

Root-level license notices reviewed for the repositories being compiled or adapted:

| Repository | Notice observed | Handling |
|---|---|---|
| `halo-64` | CC0-1.0 | Applies to licensor-owned work; its text does not clear third-party material. Keep all upstream notices. |
| `halo-ce-universal` | CC0-1.0 | Same third-party-rights limit; retain source attribution and provenance. |
| `halo-ps2` | GNU GPL v3 | Keep copied/adapted engine and converter work in its GPL fork and preserve notices. |
| `ps2dev` and EE/IOP/DVP compiler forks | MIT | Retain license and copyright files in their source repositories. |
| `ps2toolchain` | BSD 2-Clause | Retain the license and notices. |
| `ps2sdk` and `ps2link` | Academic Free License 2.0 | Retain the supplied license and source notices. |
| `ps2client` | BSD-style 3-clause terms in `doc/license.txt` | The notice is not at repository root; retain the in-tree license document with compiled source attribution. |

This is a review of repository-level notices, not a complete inventory of every vendored/transitive file or a conclusion about retail-game rights. The project does not commit retail or converted data. Before redistribution, review all copied source and binary notices and the applicable rights for user-provided game data.

## Baseline checks

Twelve `halo-ps2/tools/tests/test_*.py` scripts completed successfully using synthetic inputs. Their optional real-map checks explicitly skipped absent data. The baseline runner is `make test-host`; bootstrap safety tests are included. These results establish host checks only, not converter completeness or PS2 execution.

## Frozen baseline

The integer-math compile closure is frozen in `config/gameplay-probe-candidates.json`. It is `source/math/integer_math.c`, `source/math/integer_math.h`, and `source/cseries/cseries.h` from pinned `halo-64`. Integer math source and header match the pinned OpenCE copies. `cseries.h` does not. `integer_math.c` calls `csprintf` and uses `temporary`; those definitions are in `source/cseries/cseries.c`, which also includes `cseries_windows.h`, `profile.h`, `errors.h`, `real_math.h`, `byte_swapping.h`, and `crc.h`. That wider graph is an explicit non-member of the frozen compile list. The host probe supplies the two symbols. `random_math` stays deferred. The subsequent bounded datum closure is recorded in `gameplay-probe.md` and the candidate manifest.

`submodules/halo-ps2` is pinned at `a571749c8c8de34c045e363726596989097c604a`. That commit is `upstream/HEAD` on `claude/open-decisions-review-75968c`, the only upstream branch advertised by `origin/HEAD`. The local fork branch `ps2-port` is checked out at the same commit. The renderer, VU1 programs, pack reader, converters, arena, pad, timer, and profiler listed above are present in this tree, so no other branch is selected.

File-level notices for the frozen compile list: `integer_math.c`, `integer_math.h`, and `cseries.h` contain no copyright or SPDX lines. They remain under `halo-64/LICENSE.md` (CC0-1.0), which does not clear third-party game rights. Inspected `halo-ps2` engine and converter files likewise have no per-file license banner; `halo-ps2/LICENSE` is GPL-3.0 and stays with that fork. Retail-game rights remain unresolved, and retail data stays untracked.

Build dependencies used by the locked toolchain resolve to the git commits in `config/dependencies.json` and `config/toolchain-sources.json`, or to the checksummed host packages in `config/native-prerequisites.json`. The isolated driver does not invoke the fetching umbrella scripts. Converter Python imports are limited to the standard library and the local `halo2ps2` package.

M02's source inventory, locked dependency identities, bounded gameplay probe list, and explicit remaining gaps are recorded here. Renderer and converter behavior are not accepted from documentation. PS2 runtime execution is not claimed.

## Compiler-closure update

Three additional orchestration repositories are pinned submodules, initialized recursively and preserved as local forks. Eleven compiler/SDK leaf refs have exact commits; see `config/toolchain-sources.json` and [toolchain report](toolchain.md). Nine required source trees have since been acquired and verified in separate native and container staging roots.

Eleven acquisition scripts in the three compiler forks require exact staging checkouts, with no implicit fetching/reset. SDK external dependencies also use verified local paths. The umbrella scripts retain their upstream-fetching behavior and are bypassed by the isolated driver. The integer-math compile closure, branch choice, and file-level notices for that closure are frozen above. Wider gameplay link closure remains a later probe, not an unrecorded gap.

Ten infrastructure tests and twelve synthetic converter tests pass. The original Halo integer math module also passes the bounded ILP32 host probe documented in `gameplay-probe.md`; neither result establishes target execution.

The EE README names newlib 4.5.0 while its configuration selects `ee-v4.6.0`; the recorded source identity follows the actual configuration. The SDK downloader fetches lwIP and FatFs and can reset hard to upstream refs, so pinning PS2SDK alone does not lock its build.

## Runtime preparation follow-up

The current M06 fixture executes a synthetic checker-textured triangle visibly, including VU1 transforms, cache maintenance, guarded DMA submission, frame presentation and pad polling. The first 600-second interpreter attempt completed its stability loop but failed its controlled Cross-input acceptance; fresh full runs then passed in both CPU modes after input delivery was made retryable. M06 is complete, including independent retained-evidence qualification. These are project-fixture observations, not REA findings or evidence that upstream world/model programs have executed.

The unchanged datum module passes bounded ILP32 host tests and the same cases on R5900. Interpreter and recompiler results match the host, and the stale-handle mutation is rejected. The world viewer compiles into parent-owned native/container outputs with matching allocated ELF sections; its Blood Gulch runtime gate remains pending.

Current checkpoint validation passes 25 project host tests and 12 upstream synthetic converter scripts in both native and container environments. Positive and negative integer/datum EE builds have matching allocated ELF contents across those environments. M07 execution is recorded in `gameplay-probe.md`.

## M10 local rendering corrections

The halo-ps2 upstream baseline remains `a571749c8c8de34c045e363726596989097c604a`; the local fork now includes `46787de` (restore BSP constants after sky) and `e1d8e11` (static supported Chicago sky composition). Gitlink, dependency lock, local bare fork, and private recovery bundle are updated together. Only the former changes engine code. `docs/world-viewer.md` records the observed defects, source evidence, current fixed view, tests, and open runtime gates. UV animation and general shader equivalence remain unproven.

## M11 visibility/cache/readback checkpoint

Local halo-ps2 changes add conservative near-plane portal traversal, strict upload budgeting, wrap-safe frame ages, and guarded framebuffer readback. The parent portal adapter selects conservative traversal outside the rendered BSP bounds. The ps2sdk screenshot source now sizes PSMCT16S DMA as 16-bit data; the world-viewer build consumes this locked source directly instead of its old installed debug-archive object. All original notices remain intact. Both fork gitlinks, dependency pins and private recovery bundles are updated. These changes have host and one-camera EE evidence; async streaming, churn, unload and total EE-memory acceptance remain open. See `visibility-streaming.md` for source findings, failed controls, exact comparison scope and cross-mode differences.

M11 texture lifetime audit: renderer keys occupy disjoint world-texture/lightmap/object-texture ranges; current synchronous frame pinning relies on the main loop's GS FINISH wait before subsequent submission. A partial upload-chain failure could leave a cache entry falsely resident. Local halo-ps2 fork `f322272` makes pixel/CLUT emission transactional and drops the unsubmitted claim on failure. Host capacity-boundary regressions cover rollback/retry. Details and remaining async/map-generation limitations: `visibility-streaming.md`.
