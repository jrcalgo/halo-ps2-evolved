# Visible PCSX2 validation

The project runs PCSX2 on the existing desktop and retains evidence under ignored `build/emulator/`. BIOS bytes, sidecars, settings and captures are private build inputs or outputs, never tracked source. The supplied ROM0 has ROMVER `0110AC20000727`; its SHA-256 is `b0bf7184d50a209cf7ceb1ab0eb3a0c9b8c583f5f6b3c819e6536f282b93063b`.

## Local configuration

Create ignored `.local/emulator.json` with `binary` (PCSX2 launcher), `bios` (ROM0), `profile` (base profile directory), `display` (the desktop display), and `version`. This machine uses PCSX2 2.8.2 and display `:0.0`. Initialize the base settings at `<profile>/PCSX2/inis/PCSX2.ini`. PCSX2 appends `PCSX2` to its `-datapath` argument.

The runner copies the base settings and supplied BIOS/sidecars into a unique run directory. It uses `APPIMAGE_EXTRACT_AND_RUN=1` because FUSE is unavailable, and the XCB desktop backend. Desktop access requires execution outside the ordinary filesystem sandbox. No system packages or global emulator settings are changed.

## Commands and evidence

`make platform-elf` builds the synthetic platform fixture. `make test-emulator` launches it visibly, first with EE/IOP/VU0/VU1 recompilers disabled, then with them enabled. Both execute 600 guest seconds by default. `SMOKE_SECONDS=15 make test-emulator EMULATOR_MODE=recompiler` is a short diagnostic run and cannot close M06.

Each run retains `result.json`, `emulog.txt`, launcher output, isolated settings, and `visible-start.png`/`visible-final.png`. Results identify the ELF, source, BIOS, settings and emulator hashes. `platform-latest.json` indexes the latest completed invocation; inspect its statuses and durations because a short diagnostic can also write this file. `active.json` identifies the current project-owned process group. Only windows in that process group receive input or capture requests.

The runner sends Start and Cross and requires their guest-side edges. It checks monotonic frame/time progression, fixed heap, bounded DMA chains, intact canaries and requested-duration completion. Interpreter/recompiler comparison covers these observable resource invariants. Allocated ELF section parity is checked separately with `tools/elf_parity.py`; debug-path differences are excluded, assertions remain enabled.

## Current acceptance state

The BIOS and synthetic checker-textured VU1 triangle have booted visibly. The 15-second recompiler diagnostic passed with 900 frames, Start/Cross input, heap `1261568`, chain high-water 20/64 quadwords and intact guards. Native/container allocated ELF contents match. The first full interpreter run completed 600 guest seconds (35965 frames, fixed heap and intact guards), but its acceptance result is **failed** because the one-shot Cross event was not observed. That evidence is retained in `platform-interpreter-d4342250f9554f24ba75e7b236a4ae25`; it must not be cited as a full pass. The runner now retries focused key delivery until guest acknowledgement and fails within 30 seconds if controlled input is missing. The fresh interpreter run `platform-interpreter-a0d37b6cfabc46fdab57f2a9b191d5eb` **passed** 600 guest seconds: 35965 frames, pad edges `[8,16384]`, heap `1261568`, chain high-water 20/64 and intact guards. Recompiler run `platform-recompiler-87ed53e831be4efb97514515817cac1c` **passed** with the same duration, frame count, input and resource observations. `tools/qualify_platform.py` passed its independent retained-evidence check. M06 is **complete**. Native and container host suites passed 25 project tests and all 12 upstream synthetic converter scripts. Optional upstream real-map checks were skipped; M09 has separate retail conversion evidence.

The interpreter can run slower than real time. Guest duration validates the stability loop; emulator wall time does not measure physical PS2 performance. Physical-console qualification remains blocked on hardware. This fixture contains no retail Halo geometry or gameplay; Blood Gulch rendering belongs to M10.

For framebuffer inspection, PCSX2's F8 snapshot is available in each run's `data/PCSX2/snaps/`. The upstream SDK framebuffer dump path needs investigation for CT16S handling before use; the current workflow uses emulator snapshots and owned-window captures.

After both full runs finish, `python3 tools/qualify_platform.py` independently re-reads the retained logs and run records, checks the CPU mode flags, accepted ELF/source identities and isolated BIOS hashes, verifies visible start/final PNGs, and compares stable resource observations. It writes ignored `build/emulator/platform-qualification.json`. Full-duration acceptance requires this check and visual inspection; a short diagnostic or an arbitrary emulator exit cannot substitute.

The current interpreter/recompiler PCSX2 presentation snapshots are both 961×721 and have identical decoded RGB bytes, SHA-256 `7d69dda01f9f01a6a49fa446ff02df1533438c534d540f996205d894c6318e71`. The comparison record is `build/emulator/platform-framebuffer-comparison.json`. These are aspect-corrected presentation snapshots, not a raw 512×448 GS memory dump. Both full-duration gates have passed.

Accepted ELF SHA-256: `b62363fc5a536dede9db7ca886b4b6c4017bf0dc775bc4948c9873ff0484f711`. Aggregate: `build/emulator/platform-latest.json`; independent qualification: `build/emulator/platform-qualification.json`; allocated-section parity: `build/emulator/platform-elf-parity.json`. The implementation checkpoint is `a7c3bfa`; the dedicated M06 closure commit follows this evidence update.
