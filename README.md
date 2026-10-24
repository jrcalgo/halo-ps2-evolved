# halo-ps2-evolved

A native PlayStation 2 port of Halo: Combat Evolved multiplayer, built by compiling the game's own decompiled simulation for the console rather than reimplementing it.

## What it is

The project started as a hybrid: a PS2-native renderer and map pipeline driving a handful of borrowed Halo gameplay routines. It has evolved into a source-ownership port. The authoritative game now comes from the [Halo CE Universal](submodules/halo-ce-universal) source, compiled for the Emotion Engine (R5900). It handles objects, physics and collision, players and vehicles, weapons, damage, game rules, AI, HaloScript, effects and HUD decisions. This repository supplies the machine underneath it:

- **The PS2 machine layer:** boot, fixed-memory arenas, pad, timer and file access, plus a platform layer that replaces the Xbox SDK calls the game expects.
- **Rendering:** the GS/VU1/DMA renderer from [halo-ps2](submodules/halo-ps2). It consumes read-only snapshots of the simulation, so it never feeds results back into gameplay.
- **An offline asset pipeline:** converts retail maps into bounded, verified profile packages that fit the console's memory.

[Halo-64](submodules/halo-64) is the method example: Halo on the Nintendo 64, made by compiling the same CE source and swapping the platform beneath it.

## Scope

- Multiplayer only: the 13 stock Xbox multiplayer maps plus the UI map. Campaign missions are out of scope.
- One to four local players in split screen, stock multiplayer modes, vehicles, Spartan bots, co-op team modes and endless survival.
- CE's fixed 30 Hz simulation, kept intact on real PS2 limits: 32 MiB EE RAM, 4 MiB GS eDRAM, 2 MiB IOP RAM and 2 MiB SPU2 RAM. Features are fitted to the hardware, not given larger pools or heap fallbacks.
- Delivery through Open PS2 Loader.

Out of scope: network play and System Link, PAL, 60 fps and campaign.

## Status

Work proceeds through measured, evidence-backed milestones. A milestone closes only on host, emulator (PCSX2) or hardware evidence, never on compilation alone. The governing plans are [the HCU remake plan](plans/5.hcu-remake.md) and [M2–M4 closure](plans/7.hcu-remake-m2-m4.md). Evidence reports live under [`docs/reports`](docs/reports).

## Getting started

| Command | Purpose |
|---|---|
| `make doctor` | Check local prerequisites and dependency pins |
| `make bootstrap OFFLINE=1` | Restore the pinned submodules from private fork bundles |
| `make toolchain` | Build the pinned EE/IOP compiler and PS2 SDK |
| `make test-host` | Run host-side safety and converter tests |

Dependencies are pinned submodules under `submodules/`. Their commits are recorded in `config/dependencies.json`. See [the toolchain guide](docs/toolchain.md) and [emulator workflow](docs/emulator.md) for details.

Retail maps, converted packs, BIOS files and disc images are never committed. You must supply your own legally obtained game data.
