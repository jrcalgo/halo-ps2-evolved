# Toolchain source lock and build preflight

## Execution update — 2026-10-18

The older status notes below describe the initial preflight and have since been superseded. Nine required locked sources are now acquired in isolated native and container staging roots. Fifteen pinned Ubuntu package archives are verified and unpacked under `build/host-prerequisites`; local wrappers and a static GMP/MPFR/MPC link probe pass. No global package installation was performed.

The base container image, requested package versions, full installed package inventory, and image ID are recorded in `config/container-environment.json`. Its private archive is `build/container-environment.tar`; its checksum is recorded separately in ignored run metadata. The container uses no network, runs as the current UID/GID, mounts the checkout read-only, and writes to `build/container`.

Two isolated compiler/SDK builds are active. At the last review, native stages compiler-00 through compiler-03 had passed and compiler-04 was running; container stages compiler-00 and compiler-01 had passed and compiler-02 was running. See each report and its run-specific logs under `build/toolchain/runs/` or `build/container/toolchain/runs/`. Do not infer completion from an active stage.

The standalone DVP assembler bootstrap and host utilities have passed. `src/vu1/world.vsm` assembles with the installed DVP assembler. The corrected container host suite passes ten infrastructure tests and twelve synthetic converter checks; retail map checks skipped. The native infrastructure suite also passes ten tests. No EE ELF, PS2 runtime, emulator, or physical-console behavior has yet been validated.

The installed native host prefix is selected with `HALO_HOST_PREREQUISITE_PREFIX`; this allows the container to consume the same verified read-only host prerequisites while keeping build outputs separate. The native environment unit test explicitly overrides that variable with its temporary fixture prefix, preventing a developer environment from redirecting its test data.

## Acquired orchestration repositories

The parent has eleven initialized submodules. Three additional repositories split compiler construction into EE, IOP and DVP stages. Their original upstream commits and current local fork commits are in `config/dependencies.json`. Local fork changes are backed by verified private bundles before the parent gitlinks were updated.

## Resolved compiler and SDK source identities

These are upstream reference resolutions. Nine required source trees have since been acquired at these exact commits and are being built; no archive SHA-256 is claimed for material that has not been acquired.

| Source | Declared ref | Resolved commit |
|---|---|---|
| `ps2toolchain_ee_binutils` | `ee-v2.45.1` | `616e51fa6ed9d1e8f4bda7d0087fac30c5398aa9` |
| `ps2toolchain_ee_gcc` | `ee-v15.2.0` | `df77d03bc1bd5765b40de554918a5ff541202548` |
| `ps2toolchain_ee_newlib` | `ee-v4.6.0` | `8881dc4b138f0561596980ac9a481c7e638aebd0` |
| `ps2toolchain_ee_pthread_embedded` | `platform_agnostic` | `b1746fd2b52d5aeafc1173761eb50e0958e8994b` |
| `ps2toolchain_iop_binutils` | `binutils-2_45_1` | `48324fde1e284293dd3d570dba597cb644921c92` |
| `ps2toolchain_iop_gcc` | `releases/gcc-15.2.0` | `5115c7e447fc07457443df874bf57840e8316d5f` |
| `ps2toolchain_dvp_binutils` | `dvp-v2.45.1` | `3eb45ea37f0efd498d1de3cf9562de07197aefa8` |
| `ps2toolchain_dvp_masp` | `v0.1.16` | `ddb4fa5fb1546e74662979a4e417217c27201c3f` |
| `ps2toolchain_dvp_openvcl` | `v0.4.0` | `5d432985669f9ed2ecde7058a8d2faeb0396b2d4` |
| `ps2sdk_lwip` | `STABLE-2_2_1_RELEASE` | `77dcd25a72509eb83f72b033d219b1d40cd8eb95` |
| `ps2sdk_fatfs` | `iop-r0.16` | `18cc3d9e07473a6aa3d783a66224b243a7b4974c` |

The lock resolver is an explicit maintenance operation: `python3 tools/lock_toolchain.py --resolve`. Ordinary builds and bootstrap never invoke it. It resolves annotated tags to their peeled commits and rejects a same-name branch/tag disagreement before writing the lock.

## Adapted build scripts

All eleven acquisition scripts inside the EE, IOP and DVP forks now invoke the parent `tools/locked_source.py` helper. They refuse positional ref overrides, never clone/fetch/reset, and require an already acquired staging checkout at the recorded commit. Tracked source modifications cause refusal. Builds must use staging trees outside `submodules/`, leaving dependency working trees separate from generated build state.

The isolated build driver exports absolute `HALO_LOCKED_SOURCE_HELPER` and `HALO_TOOLCHAIN_SOURCE_ROOT` paths. Staging directories are named by source IDs in the table. The explicit acquisition helper can fetch a selected exact commit or restore it from a local repository without resetting existing trees. Large compiler source acquisition has not been executed. A successful source lookup alone does not validate a compiler build.

The parent `ps2toolchain` and `ps2dev` umbrella scripts still contain their upstream fetching behavior and must not be used as the locked build entry point. The SDK downloader now obtains validated local source paths and links them into its external dependency locations, refusing existing directories or different links. Both destinations are checked before either link is created.

`config/toolchain-profile.json` specifies the initial stage order and nine required leaf sources. MASP/OpenVCL remain locked but optional: the inspected renderer invokes `dvp-as` and no MASP/OpenVCL invocation was found in the inspected renderer/SDK makefiles. Full builds have not validated this profile yet. Newlib-nano remains included because SDK samples select it; the default engine link uses ordinary libc.

## Preflight and current constraints

Run `make toolchain-plan` for a read-only report. It intentionally exits nonzero until readiness is established. It neither installs packages nor acquires sources.

- Native host tools absent from the global PATH are supplied from the verified local prefix; the preflight sets PATH for the build process only.
- The compiler acquisition script used a conservative free-space requirement. The native filesystem now has ample available headroom, and the builds report their own space checks; no unrelated data was removed.
- Docker access works through the isolated runner. The pinned image is locally available and no network is permitted inside its build container.
- Native/container source and configuration are intentionally identical, but artifact parity awaits completion of both compiler/SDK builds. SDK installation and minimal ELF compilation remain pending.

## Validation

Ten host infrastructure tests pass, including acquisition, build-stage failure/log retention, build settings, package checksum prechecks, container mount isolation, and SDK preservation checks. Offline bootstrap passes against all eleven submodules. Twelve upstream converter test scripts pass their synthetic checks; real-map tests skip in the absence of private assets. These checks do not establish compiler output correctness.

## Next steps

1. Let the native and container compiler/SDK builds reach terminal reports; diagnose and fix any stage failures.
2. Build the minimal EE ELF in both environments and compare target ABI and artifact hashes.
3. Run the ELF in PCSX2 interpreter mode when an emulator path is available; retain native PS2 verification as a separate gate.
4. Continue archive/source provenance review and update the remaining M02 audit.

## Build-location selection

Set `HALO_BUILD_ROOT` to select a build filesystem. The read-only preflight measures the nearest existing ancestor without creating directories. `HALO_TOOLCHAIN_SOURCE_ROOT` can explicitly select compiler staging checkouts; otherwise it defaults under that build root. Source readiness is determined by actual clean Git checkouts and exact commits, not by a mutable acquisition flag in the versioned lock. An external location still needs suitable environment write access.

The normal 32-bit host gameplay harness also needs libc development support: the initial `gcc -m32` header probe failed before linking. See `gameplay-probe.md`.

## Executable native workflow

`make host-tools` builds the small native utilities independently of the missing cross compiler. It stages the exact pinned ps2client commit from the local initialized dependency, builds and installs under `build/toolchain/install`, and records compiler identity and output hashes. This command has passed, including a repeat run. No console was contacted.

`make toolchain` implements the selected compiler scripts, isolated SDK build/install and SDK glue links, followed by host tools. It currently fails preflight as intended; its full compilation path has not run. `BUILD_ENV=container` is explicitly unavailable until its image/package environment is implemented and pinned.

`tools/acquire_sources.py --id SOURCE_ID` performs intentional network acquisition; `--from-local /path --offline` uses only that local repository. Existing dirty, mismatched or symlinked destinations are preserved through refusal. Failed new acquisitions remove only their own temporary directory. Nested source submodules require a separate explicit audit rather than automatic fetching. Remote compiler acquisition requires the conservative storage allowance.

The driver clears inherited build/install overrides, bounds jobs through `HALO_BUILD_JOBS`, and writes unique per-run logs/results. Failed commands stop subsequent stages. The latest report is convenient for tooling; historical run records remain separate. Source object IDs provide Git content identity; no downloaded archive checksum or native/container parity is claimed.
