# Initial source audit — M02 in progress

Pins and upstream identities are recorded in `config/dependencies.json`. Findings below are source observations at those pins, not PS2 runtime evidence.

| Component | Source | Initial disposition | Remaining gate |
|---|---|---|---|
| N64 portability boundary | `halo-64/tools/n64_build.py`, `port/n64/include/halo_n64_prefix.h`, `port/n64/src/xdk_*.c` | Reference for a separate HALO_PS2 boundary | Enumerate compiler fixups, ABI assumptions and excluded services |
| Integer math | `halo-64/source/math/integer_math.c`, `.h` | Probe candidate | Depends on cseries declarations, diagnostic functions and Xbox-width long; host LP64 is not equivalent |
| Random math | `halo-64/source/math/random_math.c` | Probe candidate | Audit seed state, arithmetic widths and all calls |
| Datum management | `halo-64/source/memory/data.c`, `.h` | Probe candidate after math | Audit allocation, assertions, pointer layouts and stale-handle behavior |
| PS2 renderer | `halo-ps2/engine/Makefile`, `src/render/`, `src/vu1/` | Adapt in PS2 fork behind parent interface | Compile EE/VU path; runtime and hardware gates remain pending |
| Pack readers and converters | `halo-ps2/tools/halo2ps2/`, `engine/src/stream/hp2.c`, `engine/src/world/` | Reuse/adapt with synthetic baselines | Retail Blood Gulch format, full validation and budget audit |
| Arenas | `halo-ps2/engine/src/core/mem.c` | Reuse candidate | Full overflow, lifetime, platform alignment and accounting review |
| Upstream gameplay | `halo-ce-universal/source/` | Independent comparison source | Diff selected closure against halo-64; no blanket portability claim |
| N64 graphics/audio | `halo-64/port/n64/src/` | Reference only | Do not transplant target-specific backend |

## Toolchain findings

`ps2dev/scripts/*.sh` clones shallow references and can fetch and forcibly check out `FETCH_HEAD`. `ps2toolchain/scripts/001-dvp.sh`, `002-iop.sh`, and `003-ee.sh` do the same. `ps2toolchain/config/ps2toolchain-config.sh` selects `main` for separate DVP, IOP and EE orchestration repositories. Therefore the eight pinned top-level repositories do not yet lock the complete compiler closure. Do not run these scripts as the reproducible build.

That initial audit note is superseded by the compiler-closure update below and the current execution report in `toolchain.md`. Native and container compiler/SDK builds are now running from the isolated locked source trees.

`halo-ps2/engine/Makefile` uses PS2SDK `draw`, `graph`, `packet2`, `dma`, `debug`, and `pad`, with `dvp-as`; exporting a GSKIT path does not establish a gsKit link dependency.

## Instructions and provenance

Read `halo-ce-universal/AGENTS.md` before modification. It requires minimal marked game-source changes, preserving arithmetic semantics, and prohibits reading `xbox/include`/Xbox SDK headers. This audit did not read those headers. The PS2 project has a GPL license file; preserve its notices and keep its adaptations in the dedicated fork. Complete license/provenance review is still pending.

## Baseline checks

Twelve `halo-ps2/tools/tests/test_*.py` scripts completed successfully using synthetic inputs. Their optional real-map checks explicitly skipped absent data. The baseline runner is `make test-host`; bootstrap safety tests are included. These results establish host checks only, not converter completeness or PS2 execution.

The initial gameplay source list above is provisional, not a frozen compilable dependency closure. M02 is not passed.

## Compiler-closure update

Three additional orchestration repositories are pinned submodules, initialized recursively and preserved as local forks. Eleven compiler/SDK leaf refs have exact commits; see `config/toolchain-sources.json` and [toolchain report](toolchain.md). Nine required source trees have since been acquired and verified in separate native and container staging roots.

Eleven acquisition scripts in the three compiler forks require exact staging checkouts, with no implicit fetching/reset. SDK external dependencies also use verified local paths. The umbrella scripts retain their upstream-fetching behavior and are bypassed by the isolated driver. M02 remains in progress: transitive gameplay include/link closure, license/provenance audit, and source/build profile closure require further review.

Ten infrastructure tests and twelve synthetic converter tests pass. The original Halo integer math module also passes the bounded ILP32 host probe documented in `gameplay-probe.md`; neither result establishes target execution.

The EE README names newlib 4.5.0 while its configuration selects `ee-v4.6.0`; the recorded source identity follows the actual configuration. The SDK downloader fetches lwIP and FatFs and can reset hard to upstream refs, so pinning PS2SDK alone does not lock its build.
