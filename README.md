# Native PS2 Halo hybrid port

Private integration project combining selected Halo gameplay sources with PS2-native rendering and offline conversion. The governing scope and acceptance gates are in [the implementation plan](plans/0.native-ps2-halo-hybrid-port.md).

The project is at the source-audit/build-foundation stage. It does not yet build or run a Halo PS2 executable.

## Available commands

| Command | Current behavior |
|---|---|
| `make doctor` | Local prerequisite and dependency-pin inventory |
| `make bootstrap OFFLINE=1` | Restore pinned submodules from separately supplied private fork bundles |
| `make test-host` | Infrastructure safety tests and upstream synthetic converter checks |
| `make toolchain-plan` | Read-only native build preflight; exits nonzero for missing prerequisites |
| `make host-tools` | Build/install pinned `ps2client` and `fsclient` in native or container staging |
| `make native-prerequisites` | Verify and extract separately acquired native prerequisite packages locally |
| `make host-abi32` | Verify and prepare the private 32-bit host runtime |
| `make test-gameplay-host32` | Compile unchanged Halo integer math and run selected ILP32 host fixtures/negative control |
| `make vu-smoke` | Assemble the existing renderer VU1 program without runtime claims |
| `make smoke-elf` | Compile a minimal EE ABI/logging ELF after SDK installation |
| `make toolchain` | Run selected compiler/SDK stages only after preflight succeeds; full execution unvalidated |

`probe`, `convert`, `elf`, `test-emulator`, and `iso` still fail explicitly because their implementations and runtime prerequisites are pending. The pinned container host-tool path is verified; complete compiler/SDK builds and EE parity remain in progress. Use `BUILD_ENV=container` for supported compilation and host-test targets.

`HALO_BUILD_ROOT` selects generated output; the default is ignored `build/`. `HALO_TOOLCHAIN_SOURCE_ROOT` optionally selects compiler staging checkouts. `HALO_BUILD_JOBS` defaults to two and the driver accepts 1–64. No target changes global Git transport policy or installs system packages.

The source acquisition command accepts one explicit ID from `config/toolchain-sources.json`:

```sh
python3 tools/acquire_sources.py --id SOURCE_ID --from-local /path/to/repository --offline
```

Omit `--from-local` and `--offline` only for intentional network acquisition. The command fetches the locked commit, not the current branch, and refuses existing modified or mismatched checkouts. Remote compiler acquisition requires storage headroom. Source acquisition and compiler execution are separate operations; newly acquired sources and their instructions still require audit before build acceptance.

## Dependencies and local forks

All upstream repositories are actual submodules under `submodules/`, initialized recursively after registration. Canonical URLs remain in `.gitmodules`; the local configuration points to ignored bare forks. `config/dependencies.json` records upstream/fork commits and complete bundle checksums.

Private bundles in `.local/bundles/` must be preserved separately from source. They contain fork-only commits and are required to restore this private development baseline. A public upstream URL alone cannot supply those commits.

## Status and evidence

See [milestone status](docs/milestones.md), [toolchain workflow](docs/toolchain.md), and [gameplay probe audit](docs/gameplay-probe.md). Build runs retain logs and JSON results under the selected build root. Retail maps, converted packs, BIOS files, and data-bearing images must remain outside tracked source.

Native prerequisite and ABI packages are extracted under ignored build directories, without host administrator changes. The ordinary sandbox blocks 32-bit execution with SIGSYS; the ILP32 fixture requires a compatible execution environment. Container images are selected by immutable image ID, run with networking disabled, and mount source read-only with separate writable output. Preserve the checksummed private image archive separately for exact offline restoration.
