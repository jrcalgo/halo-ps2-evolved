# Execution status

Governing specification: [detailed plan](../plans/0.native-ps2-halo-hybrid-port.md).

Status reviewed 2026-10-18. A milestone is complete only when every required acceptance gate has evidence. Compilation does not establish runtime behavior. A dedicated local commit is made when each milestone closes.

## M00 — Complete

Parent Git metadata, workspace permissions, source access, and the initial environment inventory are established. Historical recovery notes are retained in `environment.md`.

## M01 — In progress

- Eleven real submodules are registered, initialized recursively, and pinned to the current parent gitlinks.
- Canonical upstream URLs remain in `.gitmodules`; full upstream/fork commits and bundle checksums are in `config/dependencies.json`.
- Local fork adaptations are backed by complete private bundles before fork-only gitlinks are recorded.
- Repeated offline bootstrap and synthetic fresh-parent restoration/refusal tests pass.
- **Remaining acceptance gate:** restore all eleven exact gitlinks from a fresh checkout of the current parent commit using only the private bundles, then rerun bootstrap and verify clean matching heads.
- Private bundles are ignored and need a separate backup. Public upstreams cannot restore fork-only commits.

## M02 — In progress

- Source reuse audit and current findings: `source-audit.md` and `gameplay-probe.md`.
- Eleven toolchain/SDK leaf sources have exact commit locks. Nine required sources were acquired into isolated native and container staging trees.
- The adapted compiler acquisition scripts refuse implicit fetch/reset and require exact locked staging checkouts. SDK external sources are supplied through verified local paths.
- The initial gameplay candidate remains original `integer_math.c`; an ILP32 host fixture now compiles and executes it without changing source algorithms.
- Full transitive gameplay include/link closure, license/provenance review, and post-build source audit remain open. No gameplay source algorithm has been modified.

## M03 — In progress

- Pinned `ps2client` and `fsclient` host utilities build and pass a repeat run.
- Native prerequisite packages are checksum-verified, extracted to a workspace-local prefix, and smoke-linked without changing global packages.
- The immutable container image and archive are pinned in `config/container-environment.json`; container execution is network-isolated and writes only under `build/container`.
- Native compiler/SDK run `build/toolchain/compiler-sdk.json`: compiler stages 00–03 passed; stage 04 is running at last review.
- Container compiler/SDK run `build/container/toolchain/compiler-sdk.json`: stages 00–01 passed; stage 02 is running at last review.
- DVP `world.vsm` assembles natively. The full compiler/SDK builds and native/container EE ELF parity remain pending.
- Native and isolated-container host test suites each pass 10 infrastructure tests and 12 synthetic converter checks. Retail-data checks skipped because no map assets are configured.
- No PS2 runtime or emulator behavior is claimed.

## M04 — Not started

No selected artifact investigation or repeatable xemu reference scenario has been completed.

## M05 — In progress

Original Halo integer math passes selected 32-bit ILP32 host fixtures, including a deliberate negative control. Arena accounting and memory-bound acceptance remain open.

## M06 — Not started

The VU1 source assembles; GS initialization, VU execution, triangle/input/timer, and stability acceptance remain pending.

## M07 — In progress

One untouched original gameplay module passes a bounded ILP32 host baseline. R5900 compilation, target execution, and the broader compatibility criteria remain pending.

## M08–M23 — Not started

Renderer runtime, game-loop integration, map conversion, gameplay systems, split-screen, campaign, streaming, and final hardware gates have not passed.

## Next actions

1. Complete the actual fresh-parent bundle restoration for M01, then record and commit M01 closure.
2. Keep native and container compiler builds running to their terminal reports; diagnose failures without claiming parity prematurely.
3. After full builds pass, create and run the minimal EE ELF in both environments, compare hashes/ABI, and record the limits of emulator/hardware validation.
4. Continue M02 closure audit and M05 resource accounting independently; no retail input or emulator/console path has been supplied yet.
