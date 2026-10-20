# Post-split rooted externals

The `ps2_m0_batch_*.c` review buckets were split into the port files that own each contract. Rebuilding the rooted image changed caller source hashes, so this pass reviews the 47 symbols the refresh left pending. None of them is a generated stand-in for a simulation or data service.

`halo-ce-universal` `port/ps2` owns these bodies. `halo-ps2` is not a caller. The EE kernel, libgcc, and Newlib supply the toolchain and timer symbols.

## File, thread, and save boundary

`CreateThread` in `port/ps2/src/ps2_edge.c` returns NULL and sets `ERROR_NOT_ENOUGH_MEMORY`. `source/bungie_net/common/thread_win32.c` treats a NULL handle as failure and does not resume a worker.

`DeleteFileA`, `SetEndOfFile`, and `WriteFile` call `ps2_m0_deny_mutation`, which sets `ERROR_ACCESS_DENIED` and returns 0. Callers are `source/saved games/game_state_xbox.c`, `source/tag_files/files_windows.c`, and `source/input/HaloAutoTest.c`. Zero is the Win32 failure result. There is no writable `z:` owner.

`XCalculateSignatureBegin` returns `INVALID_HANDLE_VALUE`. `XCalculateSignatureEnd` and `XCalculateSignatureUpdate` return `ERROR_INVALID_HANDLE`. `XCreateSaveGame` and `XDeleteSaveGame` return `ERROR_ACCESS_DENIED`, not 0. `XFindFirstSaveGame` returns `INVALID_HANDLE_VALUE`. `XFindNextSaveGame` and `XFindClose` return 0. The caller is `source/saved games/saved_game_files.c`. CE treats a zero save result as success and a NULL find handle as a live enumeration, so those returns stay fail-closed.

`SetLastError` in `ps2_edge.c` stores one process-global code. Callers are the fail-closed file paths and `port/ps2/src/ps2_input.c`. This is not a per-thread TEB.

## Memory and timer

`GlobalAlloc`, `LocalFree`, `GlobalReAlloc`, and `GlobalMemoryStatus` are defined in `port/ps2/src/ps2_memory.c`. `source/cseries/cseries_windows.c` and `source/cseries/debug_memory.c` are the callers. `GlobalReAlloc` copies `min(old debug header + user + trailer, new size)`. `GlobalMemoryStatus` reports the 32 MiB EE map minus the bound spans.

`physical_memory_get_tag_cache_size`, `physical_memory_get_structure_bsp_cache_size`, and `physical_memory_get_sound_cache_base_address` are the same provider. Callers are `GlobalMemoryStatus`, `port/ps2/src/ps2_cache.c`, `port/linux/game/tag_validate.c`, `source/cache/cache_files.c`, `port/ps2/src/ps2_sound_cache.c`, and `source/sound/sound_dsound_xbox.c`.

`GetTimerSystemTime` is the pinned PS2SDK EE kernel timer (`submodules/ps2sdk/ee/kernel/src/timer.c`). `port/ps2/src/ps2_time.c` uses it for `GetTickCount`, `QueryPerformanceCounter`, and `Sleep`. The standalone map resolves `libkernel.a(GetTimerSystemTime.o)`. The generator does not emit a body.

`rasterizer_initialize` in `ps2_edge.c` is what `source/shell/shell.c` calls. It sets the screen bounds and the retail clip distances. It does not allocate `global_rasterizer_model_ambient_reflection_tint`. That pointer lives in `port/ps2/src/ps2_rasterizer.c` and stays NULL. `cinematic_stop` and `rasterizer_initialize_for_new_map` both test it before writing.

## CRT and compiler runtime

`_control87` in `port/ps2/src/ps2_crt.c` stores a software control word. `source/math/real_math.c` writes `CW_DEFAULT` and ignores the returned word. The R5900 has no x87 control word, so this does not change the FPU rounding mode.

`_stricmp`, `_vsnwprintf`, `towlower`, and `vswprintf` are the CRT bodies in that same file. Callers are CE identifier compares (`source/ai`, `source/cache/cache_files.c`) and `source/text/unicode.c` / `source/cseries/cseries.c`.

`__divdf3`, `__extendsfdf2`, `__fixdfsi`, `__floatsidf`, `__truncdfsf2`, and `__udivdi3` are pinned GCC 15.2.0 libgcc (`libgcc.a(_div_df.o)`, `_sf_to_df.o`, `_df_to_si.o`, `_si_to_df.o`, `_df_to_sf.o`, `lib2funcs.o`). Callers are CE math, actor, physics, and the Linux tag-schema walkers. Software-double cost stays an M6 measurement. No precision-changing substitute is linked.

`memcpy`, `qsort`, `sqrt`, `strstr`, `sprintf`, `printf`, `puts`, `fopen`, `fclose`, `fprintf`, `rint`, `time`, and `gmtime_r` are pinned Newlib 4.6.0 members, not generated zero bodies. `printf` and `puts` are the console path. `fopen`, `fclose`, and `fprintf` are the Newlib file calls used by director, debug dumps, errors, cheats, and HaloScript. Their success still depends on the M1 storage root; the symbol provider is the C library. `rint` is Newlib's default-mode round. Because `_control87` does not reprogram the R5900, `fast_ftol` and the color converters keep that default. `time` and `gmtime_r` serve `GetSystemTime` in `ps2_time.c` and are not the EE bus-clock frame timer.

## Owned local-profile defaults

`port/ps2/src/ps2_local_profile.c` now defines the contracts that the typed-zero generator used to emit for this image. That includes `game_in_editor` returning FALSE, `halo_interpolation_enabled` returning 0, the Linux mouse and touch overlays returning false, `bink_playback_active` returning false, the cheat datum, the XInput device-type tokens, and the empty HaloScript rasterizer hooks whose CE bodies no-op on a NULL cinematic datum. `halo-ps2` does not provide these symbols.

## Telnet poll

`telnet_console_process` is the generated empty void. `source/main/main.c` calls it from `main_loop` and `main_loop_of_death` after `event_manager_update`. The port has no telnet server. The empty poll does not advance gameplay, UI, or cache state.
