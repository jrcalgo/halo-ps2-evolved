# Execution status

Governing specification: [detailed plan](../plans/0.native-ps2-halo-hybrid-port.md).

## M00 — Passed for dependency acquisition

The parent Git repository is valid. Git metadata writes and GitHub access work through approved escalation; the ordinary sandbox still restricts metadata writes and GitHub DNS. Historical diagnostics remain in `environment.md`. Existing plans and user files were preserved.

PS2 compilation, emulator configuration, retail inputs and physical-console access remain later prerequisites.

## M01 — Passed initial bootstrap gates

- Eleven actual submodules initialized recursively, including the three compiler orchestration dependencies discovered during M02.
- Canonical upstream URLs retained in `.gitmodules`; full upstream and local fork pins recorded in `config/dependencies.json`.
- Dedicated local bare forks and port branches; verified complete private bundles preserved before recording fork-only gitlinks.
- Offline bootstrap passes for all eleven dependencies.
- Fresh-parent synthetic tests restore a fork-only commit, repeat without pin changes, and refuse dirty trees or missing bundles.
- Private bundles are ignored and require separate backup. Public upstreams cannot restore fork-only commits.

## M02 — In progress

- Source audit and reuse candidates: `source-audit.md`.
- Eleven compiler/SDK leaf refs resolved to full commits; nine selected as required in the initial build profile. Large source acquisition remains pending.
- Eleven compiler acquisition scripts require exact local sources and refuse implicit fetching/ref overrides. Concurrency defaults to two jobs.
- SDK external dependency loading uses verified local paths, with repeat-run and existing-data preservation checks.
- Parent umbrella scripts still have upstream fetching behavior. The new isolated driver bypasses those entry points; full driver execution remains unvalidated.
- Candidate gameplay file hashes, differences and ABI assumptions recorded in `gameplay-probe.md` and `config/gameplay-probe-candidates.json`.
- Complete gameplay include/link closure, provenance review and transitive compiler-source audit remain pending. No gameplay algorithms have been changed or executed.

## M03 — In progress; native host-utility portion built

- `make host-tools` compiled and installed pinned `ps2client` and `fsclient` from an isolated offline checkout, then passed a repeat run.
- Source: ps2client `4af9c6a7a05a3a428270f2d836166cd3965bcb17`; host compiler: Ubuntu GCC 12.4.0.
- Output and SHA-256 identities: `build/toolchain/host-tools.json`; run-specific logs/results under `build/toolchain/runs/`.
- No console connection or target code execution was attempted.
- `make toolchain` correctly refuses missing prerequisites before compiler stages run.
- Remaining blockers: nine compiler/SDK source checkouts, missing native tools/development libraries and storage headroom. Container base/package lock and native/container ELF parity remain pending.

## Validation completed

- Eight infrastructure tests: passed, covering bundle restoration, clean/exact source routing, acquisition refusal and cleanup, stage failure/log retention, build settings, ref resolution and SDK preservation.
- Twelve upstream Python converter scripts: synthetic checks passed; retail checks skipped.
- Fifteen upstream C host executables: sanitizer suite passed through approved escalation; the ordinary sandbox's ptrace restriction prevented LeakSanitizer there.
- No emulator or hardware tests have run.

## M04–M23 — Not started

Preliminary source and host checks do not close REA artifact investigations, resource accounting, platform bring-up, gameplay compatibility, conversion, multiplayer, campaign or hardware gates.

Next: obtain suitable build storage and native prerequisites, acquire and audit locked compiler sources, then validate native/container compilation. Actual retail input paths are also pending user input.
