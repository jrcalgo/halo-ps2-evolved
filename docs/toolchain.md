# Toolchain source lock and build preflight

## EE executable parity — 2026-10-18

Both `build/toolchain/compiler-sdk.json` and `build/container/toolchain/compiler-sdk.json` finished with status `passed`. Each run completed compiler stages 00–09, then `sdk-build` and `sdk-install`. Host `ps2client` and `fsclient` were rebuilt from the pinned source during the same native and container driver runs. The compiler identity in both environments is `mips64r5900el-ps2-elf-gcc (GCC) 15.2.0`. The EE assembler is GNU assembler 2.45.1. The SDK commit is `a3ce5d035ceae1218dc0b83e465d1e5c927d951d`. The IOP tree used by this profile contains `001-binutils.sh` and `002-gcc-stage1.sh` only.

`make smoke-elf` and `BUILD_ENV=container make smoke-elf` each produced `halo-smoke.elf`. Native file SHA-256 is `cae68909c4a540801274d63bff384f9825973ad0d74aa11f08769fcb7181d8a2`. Container file SHA-256 is `887c3b1794f7f5e8c0cc3eb0b5788bc87c86f57fd0582fc2f432d6957598e4d8`. ELF class, endianness, machine flags `0x20920025`, and entry point `0x100b20` match. Every allocatable section (`.text`, `.ctors`, `.dtors`, `.data`, `.rodata`, `.MIPS.abiflags`, `.eh_frame`, `.sdata`, `.bss`) has identical bytes. The file hashes differ because `.debug_str` embeds the native versus `build/container` staging paths, and `.strtab` local symbols carry different per-build suffixes. The same fixture compiled from `/tmp/halo-ee-anywhere` reproduced those allocatable bytes, so the compile is not tied to this checkout path. All 211 installed IOP `.irx` modules have identical allocatable section bytes across the two environments. Static library file hashes differ for the same path-metadata reason. No ELF was executed. PCSX2 and hardware gates remain open.

Converter code under `submodules/halo-ps2/tools` imports only the Python standard library and the local `halo2ps2` package. There is no third-party Python lock to add. Keep `python3 -I`.

## Execution update — 2026-10-18

The older status notes below describe the initial preflight and have since been superseded. Nine required locked sources are now acquired in isolated native and container staging roots. Fifteen pinned Ubuntu package archives are verified and unpacked under `build/host-prerequisites`; local wrappers and a static GMP/MPFR/MPC link probe pass. No global package installation was performed.

The base container image, requested package versions, full installed package inventory, and image ID are recorded in `config/container-environment.json`. Its private archive is `build/container-environment.tar`; its checksum is recorded separately in ignored run metadata. The container uses no network, runs as the current UID/GID, mounts the checkout read-only, and writes to `build/container`.

The compiler and SDK builds recorded below have since finished. See the parity section above for the terminal reports. Historical run logs remain under `build/toolchain/runs/` and `build/container/toolchain/runs/`.

The standalone DVP assembler bootstrap and host utilities have passed. `src/vu1/world.vsm` assembles in native and container environments; both `world.o` files have SHA-256 `b98e92d27413ade70bfcefa15b78408ffd033376791c9c8f9641fb90f63ca136`. This establishes identical assembly output for that source, not VU execution.

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

The isolated build driver exports absolute `HALO_LOCKED_SOURCE_HELPER` and `HALO_TOOLCHAIN_SOURCE_ROOT` paths. Staging directories are named by source IDs in the table. The explicit acquisition helper can fetch a selected exact commit or restore it from a local repository without resetting existing trees. Nine required compiler and SDK source trees are acquired in both isolated staging roots.

The parent `ps2toolchain` and `ps2dev` umbrella scripts still contain their upstream fetching behavior and must not be used as the locked build entry point. The SDK downloader now obtains validated local source paths and links them into its external dependency locations, refusing existing directories or different links. Both destinations are checked before either link is created.

`config/toolchain-profile.json` specifies the initial stage order and nine required leaf sources. MASP/OpenVCL remain locked but optional: the inspected renderer invokes `dvp-as` and no MASP/OpenVCL invocation was found in the inspected renderer/SDK makefiles. Full builds have not validated this profile yet. Newlib-nano remains included because SDK samples select it; the default engine link uses ordinary libc.

## Preflight and current constraints

Run `make toolchain-plan` for a read-only report. It neither installs packages nor acquires sources. Its latest native run passed with eleven resolved source identities and 218.56 GiB free; it did not execute a toolchain build.

- Native host tools absent from the global PATH are supplied from the verified local prefix; the preflight sets PATH for the build process only.
- The compiler acquisition script used a conservative free-space requirement. The native filesystem now has ample available headroom, and the builds report their own space checks; no unrelated data was removed.
- Docker access works through the isolated runner. The pinned image is locally available and no network is permitted inside its build container.
- Native and container source and configuration are the same pins. Allocatable EE ELF and IOP IRX bytes match; debug path metadata does not. Emulator execution remains open.

## Validation

Ten host infrastructure tests pass, including acquisition, build-stage failure/log retention, build settings, package checksum prechecks, container mount isolation, and SDK preservation checks. Offline bootstrap passes against all eleven submodules. Twelve upstream converter test scripts pass their synthetic checks; real-map tests skip in the absence of private assets. These checks do not establish compiler output correctness.

## Next steps

1. Let the native and container compiler/SDK builds reach terminal reports; diagnose and fix any stage failures.
2. Build the minimal EE ELF in both environments and compare target ABI and artifact hashes.
3. Run the ELF in PCSX2 interpreter mode when an emulator path is available; retain native PS2 verification as a separate gate.
4. Continue archive/source provenance review and update the remaining M02 audit.

## Build-location selection

Set `HALO_BUILD_ROOT` to select a build filesystem. The read-only preflight measures the nearest existing ancestor without creating directories. `HALO_TOOLCHAIN_SOURCE_ROOT` can explicitly select compiler staging checkouts; otherwise it defaults under that build root. Source readiness is determined by actual clean Git checkouts and exact commits, not by a mutable acquisition flag in the versioned lock. An external location still needs suitable environment write access.

The 32-bit host gameplay harness uses a private extracted sysroot, as described in `gameplay-probe.md`.

## Executable native workflow

`make host-tools` builds the small native utilities independently of the missing cross compiler. It stages the exact pinned ps2client commit from the local initialized dependency, builds and installs under `build/toolchain/install`, and records compiler identity and output hashes. This command has passed, including a repeat run. No console was contacted.

`make toolchain` implements the selected compiler scripts, isolated SDK build/install and SDK glue links, followed by host tools. Both environments have now passed that driver. ELF parity is recorded above and is not emulator validation.

`tools/acquire_sources.py --id SOURCE_ID` performs intentional network acquisition; `--from-local /path --offline` uses only that local repository. Existing dirty, mismatched or symlinked destinations are preserved through refusal. Failed new acquisitions remove only their own temporary directory. Nested source submodules require a separate explicit audit rather than automatic fetching. Remote compiler acquisition requires the conservative storage allowance.

The driver clears inherited build/install overrides, bounds jobs through `HALO_BUILD_JOBS`, and writes unique per-run logs/results. Failed commands stop subsequent stages. The latest report is convenient for tooling; historical run records remain separate. Source object IDs provide Git content identity. VU1 assembly output matches between environments. Normalized EE and IOP executable contents match as recorded above.
