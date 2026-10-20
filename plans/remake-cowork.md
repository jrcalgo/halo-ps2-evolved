# HCU remake cowork progress

Saved 2026-10-20. This is a resume note for `plans/5.hcu-remake.md`. It is not a milestone closure. M1 has not passed, and nothing in this note is committed.

## Where the plan stands

M0 is closed and committed as parent `2879895` ("M0: measure the reachable R5900 gameplay closure"). The HCU pin in that commit is `c406a414` ("ps2: define the local-game closure the decompilation left open") on `ps2-port`. Upstream HCU remains `7524ba61689a912bdec234d9687b178f0b0e7389`.

M1 is in progress. `build/hcu-ps2-closure/all/halo-local.elf` links with no undefined symbols, and the latest image still fits `elf_static`. A PCSX2 recompiler boot reaches `game_initialize` and then halts. That is not a boot of the local-game lifecycle, so M1 must not be committed.

M2 through M6 have not started. After this plan, the parent milestone is still M14. Physical-console qualification stays M23 and is open.

`plans/3.m14-asset-path-audit.md` and `plans/4.m14-source-and-hardware-review.md` are unrelated untracked notes. Leave them out of remake commits.

## Latest ELF

`python3 tools/hcu_ps2_closure.py --layer all` then `python3 tools/hcu_ps2_link.py`. Closure result: 343 compiled, 0 failed. `docs/hcu-ps2-closure.md` still describes an earlier link (1,890,956 code bytes, `.bss` 8,742,128). The image on disk now is:

| Section | Address | Bytes |
|---|---:|---:|
| `.text` | `0x00100000` | 1,526,752 (`0x174be0`) |
| `.data` | `0x00274c80` | 98,980 (`0x182a4`) |
| `.rodata` | `0x0028cf80` | 264,032 (`0x40b60`) |
| Code, constants, and static data | | 1,889,764 |
| `.bss` | `0x002cdb80` | 8,742,192 (`0x856530`) |

`elf_static` is 2,097,152. Spare against the three PROGBITS sections is 207,388. `size` reports text 1,791,832, data 99,012, bss 8,742,192; use the `readelf` rows above for the budget table. `.bss` is still one section. It holds the fixed game-state buffer, the 2 MiB tag cache, 512 KiB texture staging, 512 KiB sound staging, and the 256 KiB startup arena. The region split against budget version 2 is not proven.

## What the last boot did

The boot used `tools/test_emulator.py` `prepare()` with the project BIOS and profile, PCSX2 recompiler, and `build/hcu-ps2-closure/all/halo-local.elf`. The EE log reached these marks, in order:

`entered`, `memory`, `shell`, `modules`, `rasterizer-pre`, `shell-init`, `cseries`, `platform 1`, `errors`, `tags`, `directory`, `math`, `game-state`, `game-state-done`, `rasterizer 1`, `input`, `sound`, `shell-ready`, `main-loop`, `game-initialize`.

About 17 ms after `game-initialize` the log printed:

`HALO_PS2_LOCAL halt 0x1ab76c file_create('custom_maps') error 0x00000002`

`addr2line` places `0x1ab76c` in `error`. The following `camera->z_far>camera->z_near` assert is `halt_and_catch_fire` trying to draw a camera whose near and far planes are both zero. It is not the fault that stopped startup.

`file_create` of a directory calls `CreateDirectoryA`. That symbol is still a generated zero return, so the create fails and `file_create` logs error `0x2`. The shell's earlier `directory_create("custom_maps")` logged and continued. The halt fired later, from inside `error`, while `game_initialize` was running. The message buffer still held the `file_create` line.

## Fixes already in the dirty tree

These are why the boot gets as far as `game_initialize`. They are not committed.

- `DmWalkLoadedModules` and `DmWalkModuleSections` return `XBDM_ENDOFLIST`. A zero return made `fuck_code_in_the_eye` spin.
- `XGetLaunchInfo` returns failure, so the shell does not treat stack garbage as an `XDEMOS` launch.
- `game_state_allocate_buffer` uses the buffer from `physical_memory_allocate` instead of requiring Xbox address `0x80061000`. There is no save file: `z:\savegame.bin` is left closed instead of halting.
- `rasterizer_initialize` returns true. The real rasterizer is not in the link. A zero return made `shell_initialize` refuse `main_loop`.
- `GlobalAlloc` and `GlobalReAlloc` bump the 256 KiB arena. `LocalFree` does not reclaim. `system_malloc` goes through `GlobalAlloc`; a zero return made `geosphere_new` fail and the assert screen spin.
- `DirectSoundCreate` returns `0x80004005`, so `dsound_initialize` does not walk a null device.
- `XInputDebugGetKeystroke` returns `38` (`ERROR_HANDLE_EOF`). `ERROR_SUCCESS` made `input_update` spin.
- `GetFileAttributesA` returns `(unsigned long)-1` and sets the last error to `2` (`ERROR_FILE_NOT_FOUND`). A zero attribute was treated as "file exists". `GetLastError` and `SetLastError` use that slot.
- Stage `printf`s and the halt caller address are temporary boot marks in the shell, `main`, and `display_assert`.

Generated bodies still satisfy the excluded, render, and platform calls that are not in `tools/hcu_ps2_link.py`'s `SKIP` set. A zero success code from one of those is what caused the two spins above.

## Uncommitted files

Parent, on `port/halo-ce-universal-remake`:

- `tools/hcu_ps2_link.py` (untracked)
- `docs/hcu-ps2-closure.md` (ELF section is behind the image above)
- `plans/5.hcu-remake.md` (status line still says the ELF has not been booted)
- `submodules/halo-ce-universal` (dirty)

HCU, on `ps2-port` at `c406a414`, with local edits:

- New: `port/ps2/src/ps2_main.c`, `ps2_abi.c`, `ps2_crt.c`, `ps2_edge.c`, `ps2_memory.c`
- Modified: `source/cseries/cseries.c`, `source/main/main.c`, `source/saved games/game_state_xbox.c`, `source/shell/shell.c`, `source/shell/shell_xbox.c`

`build/hcu-ps2-closure/all/ps2_platform.c` is generated by the link tool. Do not commit it.

## Resume

1. Make `CreateDirectoryA` succeed for a directory that only needs to exist, or stop `file_create` / `error` from halting startup when the directory cannot be created. Confirm the halt caller is that path and not a later `_error_immediate` whose buffer still shows the old `file_create` line.
2. Boot again with `tools/test_emulator.py` `prepare()` until `game_initialize` returns (`HALO_PS2_LOCAL game-initialize-done`) or the next halt names a new caller.
3. Keep using `python3 tools/hcu_ps2_closure.py --layer all` and `python3 tools/hcu_ps2_link.py`. Do not commit M1 until the lifecycle stays up without a Direct3D, DirectSound, Bink, or online-netcode relocation, and the ELF bytes are reported against `elf_static`.
4. Update `docs/hcu-ps2-closure.md` and the status line in `plans/5.hcu-remake.md` from the image that actually booted.
