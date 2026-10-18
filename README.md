# Native PS2 Halo hybrid port

Private integration project combining selected Halo gameplay sources with PS2-native rendering and offline conversion. The governing scope and acceptance gates are in [the implementation plan](plans/0.native-ps2-halo-hybrid-port.md).

M00–M09 are complete. Native and container toolchains are built, the integer-math and datum probes have executed on R5900, and a synthetic gameplay object has driven a visible PS2 triangle for the platform smoke duration. Blood Gulch has been drawn on a 300-second scripted route in both CPU modes. M10 stays open until the free-camera traversal passes.

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
| `make toolchain` | Build the pinned compiler/SDK; native and container builds have passed |
| `make probe` | Build the frozen original integer-math closure for R5900 |
| `make test-emulator` | Visibly run the platform fixture in interpreter/recompiler modes; retains private evidence |
| `make test-emulator SCENARIO=probe` | Visibly run the strict integer-math and datum fixtures, including their failure controls |
| `make hybrid-elf` | Build the M08 hybrid ELF; compilation alone does not pass M08 |
| `make test-emulator SCENARIO=hybrid` | Visibly run the 18,000-tick hybrid proof in interpreter and recompiler modes |
| `make platform-elf` | Build the M06 platform fixture; compilation alone does not pass M06 |
| `make reference-scenario` | Repeat the source-derived ILP32 integer-math reference |
| `make convert MAP=bloodgulch` | Convert the privately configured Xbox map twice; existing output directories are preserved through refusal |

`elf` and `iso` remain unavailable until their implementation gates are met. Use `BUILD_ENV=container` for supported compilation and host-test targets. The [visible emulator workflow](docs/emulator.md) is implemented. M06 stability acceptance and M07 probe qualification have passed. `SCENARIO=probe` uses the strict fixture runner; a single integer-math success line is not that gate.

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
