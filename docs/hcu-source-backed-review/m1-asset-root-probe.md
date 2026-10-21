# M1 asset-root probe implementation and evidence

Date: 2026-10-20

## Scope

This implements the bounded read-only probe in Milestone 4, Step 4 of `/home/ai/Desktop/HCU plan`. It exercises the selected root through the same `file_reader`/FileXio bridge used by HCU's map cache before `halo_shell_main()`. It does not load or validate a map, establish OPL device mounting, or prove IOP preservation on hardware.

## Implementation

- `hcu_file_bridge_probe()` in `src/stream/hcu_file_bridge.c` checks `stat`, rejects missing paths/directories/empty files, opens one token, cross-checks the opened size, seeks to byte zero, reads one bounded byte, seeks to EOF, verifies a zero-byte EOF read, and closes the handle.
- Failure is reported with a stable stage token; any successfully opened token is closed on every failure path.
- `src/stream/hcu_main.c` probes `D:\\maps\\ui.map` after `hcu_map_service_init()` has selected the deterministic root and before entering the CE shell. Failure reports the configured root and failed stage, shuts down the map service and exits; success reports root and byte size.
- The probe allocates no dynamic memory and keeps no file token after return. `hcu_storage_boot_init()` remains the preceding no-reset storage setup.

## Host verification

`pytest -q tests/test_hcu_file_bridge.py tests/test_hcu_storage_boot.py tests/test_hcu_asset_profiles.py`: **3 passed**.

The FileXio shim compiles and executes the actual parent `file.c` and HCU bridge. It verifies success, missing-path (`stat`) and directory (`validate-file`) failures, bounded first-byte/EOF behavior, zero retained descriptors, failure when all 16 slots are occupied (`open`), cleanup following a read error (`read-first-byte`), and 100 repeated open/close cycles without descriptor high-water growth. Linker-wrapped `malloc`/`calloc`/`realloc` counters also remain unchanged across the probe and repeated lifecycle, so the fixture confirms no heap-allocation calls on this path. The storage bootstrap test continues to guard the no-IOP-reset policy; it does not emulate a live OPL IOP.

## Target build and guest attempt

The pinned-toolchain `python3 tools/hcu_parent_link_probe.py --asset-profile host` completed. After the ABI runtime smoke was added, the current gameplay machine ELF has SHA-256 `2eb1f907d781bcfe4fb6170ba698f05d58090510b818c595acb8f2921fb1c54e`, contains the asset-probe success/failure diagnostics and ABI-failure diagnostic, and has zero undefined imports in its link report. This exact image includes the production asset probe. The separate parent-linked diagnostic viewer remains over the `elf_static` limit and is not an acceptance artifact.

A current-image PCSX2 launch was attempted with `tools/test_hcu_boot.py` and the available `build/hcu-m1-disc-data.iso`, but the emulator exited before guest startup because Qt could not connect to a display / initialize its xcb plugin (status 127). The configured X sockets were not reachable, and a temporary Xvfb could not bind in this restricted environment. No guest marker was observed; this is **not** evidence of a probe pass or a guest-side asset-root failure. Earlier PCSX2 placement results predate this image hash and must not be reused as current-image qualification.

## Remaining acceptance

- Run the exact gameplay ELF successfully in PCSX2 and record the expected probe result for a populated asset root and a missing/corrupt root.
- Demonstrate the device paths and FileXio operations on real OPL-launched USB (`mass:/`), SMB (`smb0:/`), and HDD (`pfs0:/`), plus optical media. Verify the running IOP state is preserved and no reset occurs.
- Re-run interpreter/recompiler guest gates for the current image and bind evidence to its exact ELF/source pins/settings before closing M1.

The step is therefore **implemented and host-tested, but not guest- or hardware-qualified**.
