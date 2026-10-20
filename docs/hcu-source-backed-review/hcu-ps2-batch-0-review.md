# CE Win32/XDK file, thread, and save roots under the PS2 M0 profile

Status: the first 32 pending ledger symbols are dispositioned from their live `caller_sections`. Generated zero-return stubs that reported success for signature/save services, left `MEMORYSTATUS` undefined, or omitted the 30 Hz `Sleep` are replaced in `port/ps2/src/ps2_m0_batch_0.c`. Existing `ps2_edge.c` read-only file and EE-semaphore bodies are approved as the current local-pad contract. Thread resume/priority/exit and `CopyFileA`/`SwitchToThread` are unreachable under those contracts.

## Evidence and boundary

Every row below uses the ledger `caller_sections` and `caller_sources`, then the CE call site, the declaration, and the generated or real body. Data-section callers are absent from this slice. `source/interface/ui_widget.c` is excluded by `port/ps2/port.json`, so the UI filesystem thread fallback is not a live rooted caller. `port/ps2/src/ps2_cache.c` completes tag/BSP reads synchronously and never leaves the completion flag at zero, so the `SwitchToThread` poll bodies do not run.

Xbox `z:` mutation, directory creation, and save metadata remain unavailable. `game_state_create_or_open_file` already continues after a failed `z:\\savegame.bin` open (`game_state_xbox.c:257-260`). Profile writes call `create_thread` without a synchronous fallback; with `CreateThread` returning `NULL` they stay memory-resident, matching the read-only volume.

## Disposition rationale

### CloseHandle — `implemented`

- Caller: `source/bungie_net/common/thread_win32.c:142,180,255`; `source/tag_files/files_windows.c:223,395,512,611,737`; `source/saved games/game_state_xbox.c:280,389,416,445,520,624,675,710,723`; `source/input/HaloAutoTest.c:28`.
- Effect: releases a file-bridge slot or deletes an EE semaphore. Thread handles are never created. Invalid handles fail with `ERROR_INVALID_HANDLE`.
- Disposition: implemented by `ps2_edge.c:457-488`.
- Sources: `port/ps2/src/ps2_edge.c:457-488`; `source/tag_files/files_windows.c:737`; `source/bungie_net/common/thread_win32.c:255`.

### CopyFileA — `excluded-proven`

- Caller: `source/saved games/saved_game_files.c:1100,1116,1130` inside `synchronize_metadata_display_name_with_profile_name`.
- Effect: copies `blam.sav` / persistent storage / `blam.lst` after a successful `XCreateSaveGame`.
- Disposition: excluded-proven. `XCreateSaveGame` now returns `ERROR_ACCESS_DENIED`, so `if (!XCreateSaveGame(...))` is false and none of the copies run.
- Sources: `source/saved games/saved_game_files.c:1080-1130`; `port/ps2/src/ps2_m0_batch_0.c` (`XCreateSaveGame`).

### CreateDirectoryA — `state-adapter`

- Caller: `source/tag_files/files_windows.c:401` (`file_create`); `source/saved games/game_state_xbox.c:377` (`game_state_write_core`).
- Effect: both callers treat a zero return as failure and keep going (`file_create` returns `FALSE`; `write_core` still attempts `CreateFileA`).
- Disposition: state-adapter. `ps2_edge.c:233-238` returns 0 and sets `ERROR_ACCESS_DENIED` for a nonempty path.
- Sources: `port/ps2/src/ps2_edge.c:233-238`; `source/tag_files/files_windows.c:400-413`; `source/saved games/game_state_xbox.c:377-391`.

### CreateFileA — `implemented`

- Caller: `source/tag_files/files_windows.c:390,503`; `source/saved games/game_state_xbox.c:245,379,405,433,499`; `source/input/HaloAutoTest.c:93,104`.
- Effect: `GENERIC_READ` + `OPEN_EXISTING` opens a file-bridge slot. Write/create/truncate modes return `INVALID_HANDLE_VALUE`. The HALO_PS2 `game_state_create_or_open_file` path documents that failed `z:\\savegame.bin` startup continues with no persistent image.
- Disposition: implemented by `ps2_edge.c:241-275`.
- Sources: `port/ps2/src/ps2_edge.c:241-275`; `source/saved games/game_state_xbox.c:245-260`; `source/tag_files/files_windows.c:498-516`.

### CreateMutexA — `implemented`

- Caller: `source/bungie_net/common/thread_win32.c:204` (`create_mutex`).
- Effect: `saved_game_files_initialize` requires two successful mutexes (`saved_game_files.c:549-551`). CE never calls `OpenMutex` on the generated name; each create is a new binary EE semaphore.
- Disposition: implemented by `ps2_edge.c:394-427`.
- Sources: `port/ps2/src/ps2_edge.c:394-427`; `source/bungie_net/common/thread_win32.c:187-218`; `source/saved games/saved_game_files.c:549-551`.

### CreateThread — `state-adapter`

- Caller: `source/bungie_net/common/thread_win32.c:117` (`create_thread`).
- Effect: a NULL handle makes `create_thread` return `FALSE` and store a NULL reference. `player_profile_write` / `playlist_profile_write` then skip the worker; in-memory profile state is unchanged. Set/resume/exit/close-thread are not reached.
- Disposition: state-adapter. `ps2_m0_batch_0.c` returns NULL and `ERROR_NOT_ENOUGH_MEMORY` instead of the generated typed zero that looked like a handle-less success path without an explicit last-error.
- Sources: `port/ps2/src/ps2_m0_batch_0.c` (`CreateThread`); `source/bungie_net/common/thread_win32.c:117-155`; `source/saved games/player_profile.c:920-924`.

### DeleteFileA — `state-adapter`

- Caller: `source/saved games/game_state_xbox.c:473` (`delete_persistent_storage`).
- Effect: the caller ignores the return. A success-shaped delete would claim `savegame.bin` was removed.
- Disposition: state-adapter. Explicit `ERROR_ACCESS_DENIED` / FALSE.
- Sources: `port/ps2/src/ps2_m0_batch_0.c` (`DeleteFileA`); `source/saved games/game_state_xbox.c:467-475`.

### FindFirstFileA — `state-adapter`

- Caller: `source/tag_files/files_windows.c:600` (`find_files_next`).
- Effect: `INVALID_HANDLE_VALUE` plus `ERROR_FILE_NOT_FOUND` ends the search. `find_files_globals.handles` start as `INVALID_HANDLE_VALUE`, so `find_files_start` does not close a live handle on first use.
- Disposition: state-adapter empty-volume enumeration (`ps2_edge.c:331-336`).
- Sources: `port/ps2/src/ps2_edge.c:331-336`; `source/tag_files/files_windows.c:165-182,593-612`.

### FindNextFileA — `state-adapter`

- Caller: `source/tag_files/files_windows.c:609` (`find_files_next`).
- Effect: only reached after a successful first match. With `FindFirstFileA` failing, this body is unused; when called it returns 0 / `ERROR_NO_MORE_FILES`.
- Disposition: state-adapter (`ps2_edge.c:338-344`).
- Sources: `port/ps2/src/ps2_edge.c:338-344`; `source/tag_files/files_windows.c:609-612`.

### GetExitCodeThread — `excluded-proven`

- Caller: `source/bungie_net/common/thread_win32.c:166` (`thread_has_exited`).
- Effect: CE treats API failure as “still running”. Profile writers spin on that predicate only when `player_profile_globals.thread` is non-NULL.
- Disposition: excluded-proven. `CreateThread` is NULL, so `create_thread` stores NULL and `thread_has_exited` is not entered.
- Sources: `source/bungie_net/common/thread_win32.c:117-155,158-171`; `source/saved games/player_profile.c:682-691`.

### GetFileAttributesA — `implemented`

- Caller: `source/tag_files/files_windows.c:703` (`file_exists`); `source/input/HaloAutoTest.c:37-45` (`HATReadMain`).
- Effect: mounted paths return `FILE_ATTRIBUTE_NORMAL` or `DIRECTORY`; missing paths return `-1` / `ERROR_FILE_NOT_FOUND`. Absent `d:\\write.xts` / `read.xts` / `loop.xts` leaves HaloAutoTest mode 0, so `HATInit` does not open `state.data` and `HATRun` is a no-op.
- Disposition: implemented by `ps2_edge.c:197-208`.
- Sources: `port/ps2/src/ps2_edge.c:197-208`; `source/tag_files/files_windows.c:694-709`; `source/input/HaloAutoTest.c:34-48,86-114`.

### GetFileAttributesExA — `implemented`

- Caller: `source/tag_files/files_windows.c:567` (`file_get_size` only).
- Effect: the live caller copies `nFileSizeLow` and ignores `ftLastWriteTime`. The edge body writes attributes and both size words.
- Disposition: implemented by `ps2_edge.c:210-229`.
- Sources: `port/ps2/src/ps2_edge.c:210-229`; `source/tag_files/files_windows.c:551-578`.

### GetFileSize — `implemented`

- Caller: `source/tag_files/files_windows.c:802` (`file_get_eof`); `source/saved games/game_state_xbox.c:504` (`game_state_open_persistent_storage`).
- Effect: a valid file-bridge handle returns the reader size. The save path only runs after a write `CreateFileA`, which the edge rejects, so the save caller does not see a size.
- Disposition: implemented by `ps2_edge.c:296-309`.
- Sources: `port/ps2/src/ps2_edge.c:296-309`; `source/tag_files/files_windows.c:796-810`.

### GetLastError — `state-adapter`

- Caller: `source/tag_files/files_windows.c` file facade; `source/saved games/game_state_xbox.c` save I/O diagnostics; `source/input/input_xbox.c:824,1049` (`input_get_device_states` / `input_update`).
- Effect: returns the process-global `ps2_last_error`. With `CreateThread` failing, file and input calls share the EE main thread, so the slot matches Win32 thread-local last-error for this profile.
- Disposition: state-adapter (`ps2_edge.c:346-349`).
- Sources: `port/ps2/src/ps2_edge.c:130,346-349`; `source/input/input_xbox.c:814-825`; `source/tag_files/files_windows.c:707`.

### GlobalMemoryStatus — `implemented`

- Caller: `source/cseries/debug_memory.c:430` (`check_memory_status`), rooted from `source/scenario/scenario.c:1211`.
- Effect: reads `dwAvailPhys` to maintain min/max. The generated empty body left the local `MEMORYSTATUS` undefined.
- Disposition: implemented. Writes every field from the 32 MiB EE map minus bound CE spans.
- Sources: `port/ps2/src/ps2_m0_batch_0.c` (`GlobalMemoryStatus`); `source/cseries/debug_memory.c:423-448`; `source/scenario/scenario.c:1211`.

### GlobalReAlloc — `implemented`

- Caller: `source/cseries/cseries_windows.c:214` (`system_realloc`), used only by `debug_realloc`.
- Effect: `debug_realloc` passes the 0x20-byte header with user size at offset 12 and a 4-byte trailer. The previous `ps2_memory.c` copy used the new size and could read past the old block. Arrays grow through this path (`source/memory/array.c:144`).
- Disposition: implemented. Copies `min(old_header+user+trailer, new_size)`.
- Sources: `port/ps2/src/ps2_m0_batch_0.c` (`GlobalReAlloc`); `source/cseries/debug_memory.c:136-146,553-592`; `source/cseries/cseries_windows.c:192-218`.

### ReadFile — `implemented`

- Caller: `source/tag_files/files_windows.c:857`; `source/saved games/game_state_xbox.c:347,409,440,578,604,696`; `source/input/HaloAutoTest.c:57,66,71,131`.
- Effect: a valid handle returns the bridge byte count. `file_read` rejects short reads. Save/HAT handles are not created unless a read-only `OPEN_EXISTING` path exists.
- Disposition: implemented by `ps2_edge.c:277-294`.
- Sources: `port/ps2/src/ps2_edge.c:277-294`; `source/tag_files/files_windows.c:842-871`.

### ReleaseMutex — `implemented`

- Caller: `source/bungie_net/common/thread_win32.c:244` (`release_mutex`).
- Effect: `SignalSema` on the create-owned binary semaphore. `release_mutex` ignores the Win32 return. Saved-game take/release pairs run on the EE main thread.
- Disposition: implemented by `ps2_edge.c:449-455`.
- Sources: `port/ps2/src/ps2_edge.c:449-455`; `source/bungie_net/common/thread_win32.c:239-246`.

### ResumeThread — `excluded-proven`

- Caller: `source/bungie_net/common/thread_win32.c:136` after a non-NULL `CreateThread` and successful `SetThreadPriority`.
- Effect: would resume a suspended worker. The generated zero return is success-shaped, but the success path is not taken.
- Disposition: excluded-proven by the `CreateThread` NULL adapter.
- Sources: `source/bungie_net/common/thread_win32.c:117-136`.

### SetEndOfFile — `state-adapter`

- Caller: `source/tag_files/files_windows.c:824`; `source/saved games/game_state_xbox.c:251,511`.
- Effect: CE requires a TRUE truncate. The save callers only run after a write `CreateFileA` succeeds. `file_set_eof` reports failure through `GetLastError`.
- Disposition: state-adapter. Explicit FALSE / `ERROR_ACCESS_DENIED`.
- Sources: `port/ps2/src/ps2_m0_batch_0.c` (`SetEndOfFile`); `source/tag_files/files_windows.c:816-836`.

### SetFilePointer — `implemented`

- Caller: `source/tag_files/files_windows.c:510,760,782`; `source/saved games/game_state_xbox.c` save seeks; `source/input/HaloAutoTest.c:70`.
- Effect: BEGIN/CURRENT/END seeks on a file-bridge handle, no high dword. Invalid handles fail. Save/HAT write handles are not created.
- Disposition: implemented by `ps2_edge.c:311-329`.
- Sources: `port/ps2/src/ps2_edge.c:311-329`; `source/tag_files/files_windows.c:760-782`.

### SetLastError — `state-adapter`

- Caller: `port/ps2/src/ps2_input.c` (`XInputOpen`); `source/tag_files/files_windows.c` file facade clear/set.
- Effect: writes the same process-global slot `GetLastError` reads. Serialized on the EE main thread for this profile.
- Disposition: state-adapter (`ps2_edge.c:351-354`).
- Sources: `port/ps2/src/ps2_edge.c:351-354`; `port/ps2/src/ps2_input.c` (`SetLastError(ERROR_DEVICE_NOT_CONNECTED)`).

### SetThreadPriority — `excluded-proven`

- Caller: `source/bungie_net/common/thread_win32.c:136` only after `CreateThread` returns a handle.
- Effect: CE requires success before resume. Unreachable under the NULL thread adapter.
- Disposition: excluded-proven.
- Sources: `source/bungie_net/common/thread_win32.c:117-136`.

### Sleep — `implemented`

- Caller: `source/main/main.c:2702` (`main_loop` 30 Hz idle); `source/main/main.c:2789` (`main_rasterizer_throttle` 1 ms vblank wait).
- Effect: the generated empty body busy-spins the EE and breaks the intended idle. The replacement waits on `GetTimerSystemTime` / `MSec2TimerBusClock`.
- Disposition: implemented.
- Sources: `port/ps2/src/ps2_m0_batch_0.c` (`Sleep`); `source/main/main.c:2698-2703,2781-2789`; `port/ps2/src/ps2_time.c:14-17`.

### SwitchToThread — `excluded-proven`

- Caller: `source/cache/cache_files.c:1273` (`scenario_tags_load`); `source/cache/cache_files.c:1435` (`scenario_structure_bsp_load`).
- Effect: both loops are `while (!read_complete)`. `ps2_cache.c` sets the flag to `_cache_file_read_failed` (2) or `TRUE` (1) before return; never 0. `!read_complete` is therefore false and the yield is not called.
- Disposition: excluded-proven for the current synchronous cache seam.
- Sources: `source/cache/cache_files.c:1264-1274,1426-1440`; `source/cache/cache_files.h:30`; `port/ps2/src/ps2_cache.c:358-426`.

### WaitForSingleObject — `implemented`

- Caller: `source/bungie_net/common/thread_win32.c:230` (`take_mutex`).
- Effect: `PollSema` / `WaitSema` / `WaitSemaEx` on the create-owned semaphore. CE accepts `WAIT_OBJECT_0`. Saved-game locks are taken and released on the EE main thread.
- Disposition: implemented by `ps2_edge.c:429-447`.
- Sources: `port/ps2/src/ps2_edge.c:429-447`; `source/bungie_net/common/thread_win32.c:221-236`.

### WriteFile — `state-adapter`

- Caller: `source/tag_files/files_windows.c:892`; `source/saved games/game_state_xbox.c:303,383,507,659,662`; `source/input/HaloAutoTest.c:81,125`.
- Effect: `file_write` requires a complete byte count. A generated FALSE is fail-closed but does not set last-error. The replacement reports `ERROR_ACCESS_DENIED` and zero bytes written.
- Disposition: state-adapter.
- Sources: `port/ps2/src/ps2_m0_batch_0.c` (`WriteFile`); `source/tag_files/files_windows.c:877-899`.

### XCalculateSignatureBegin — `state-adapter`

- Caller: `source/saved games/saved_game_files.c:930`.
- Effect: CE compares against `INVALID_HANDLE_VALUE`. The generated NULL is a valid handle, so Update/End would run.
- Disposition: state-adapter. Returns `INVALID_HANDLE_VALUE`.
- Sources: `port/ps2/src/ps2_m0_batch_0.c` (`XCalculateSignatureBegin`); `source/saved games/saved_game_files.c:918-947`.

### XCalculateSignatureEnd — `state-adapter`

- Caller: `source/saved games/saved_game_files.c:939`.
- Effect: a zero return is success and would leave `checksum` untouched after a bogus handle. Reached only after a valid Begin.
- Disposition: state-adapter. Returns `ERROR_INVALID_HANDLE`.
- Sources: `port/ps2/src/ps2_m0_batch_0.c` (`XCalculateSignatureEnd`); `source/saved games/saved_game_files.c:939-942`.

### XCalculateSignatureUpdate — `state-adapter`

- Caller: `source/saved games/saved_game_files.c:934`.
- Effect: a zero return is success without hashing bytes.
- Disposition: state-adapter. Returns `ERROR_INVALID_HANDLE`.
- Sources: `port/ps2/src/ps2_m0_batch_0.c` (`XCalculateSignatureUpdate`); `source/saved games/saved_game_files.c:934-937`.

### XCreateSaveGame — `state-adapter`

- Caller: `source/saved games/saved_game_files.c:1080` (`synchronize_metadata_display_name_with_profile_name`).
- Effect: zero means success and enters `CopyFileA`. Non-zero logs failure and leaves the display name unchanged.
- Disposition: state-adapter. Returns `ERROR_ACCESS_DENIED`.
- Sources: `port/ps2/src/ps2_m0_batch_0.c` (`XCreateSaveGame`); `source/saved games/saved_game_files.c:1080-1170`.

### XDeleteSaveGame — `state-adapter`

- Caller: `source/saved games/saved_game_files.c:1144,1161` (rename cleanup); `:1536` (`delete_enumerated_saved_game_file`); `:1820` (`saved_game_files_delete_all_custom_profiles`).
- Effect: zero is treated as successful deletion. The generated zero would claim metadata was removed.
- Disposition: state-adapter. Returns `ERROR_ACCESS_DENIED`.
- Sources: `port/ps2/src/ps2_m0_batch_0.c` (`XDeleteSaveGame`); `source/saved games/saved_game_files.c:1532-1540,1811-1823`.

## Regression

`tests/test_hcu_external_review_batch_0.py::test_batch_0_rooted_symbols_are_dispositioned` locks the pending `[0:32]` slice, every batch JSON field, skip-list definitions, and a real source snippet for each approved contract.

## Sources

- `docs/hcu-source-backed-review/hcu-ps2-external-review.json` (slice caller_sections / caller_sources)
- `submodules/halo-ce-universal/port/ps2/src/ps2_m0_batch_0.c`
- `submodules/halo-ce-universal/port/ps2/src/ps2_edge.c`
- `submodules/halo-ce-universal/port/ps2/src/ps2_cache.c`
- `submodules/halo-ce-universal/source/bungie_net/common/thread_win32.c`
- `submodules/halo-ce-universal/source/tag_files/files_windows.c`
- `submodules/halo-ce-universal/source/saved games/game_state_xbox.c`
- `submodules/halo-ce-universal/source/saved games/saved_game_files.c`
- `submodules/halo-ce-universal/source/cseries/debug_memory.c`
- `submodules/halo-ce-universal/source/cseries/cseries_windows.c`
- `submodules/halo-ce-universal/source/main/main.c`
- `submodules/halo-ce-universal/source/cache/cache_files.c`
- `submodules/halo-ce-universal/source/input/HaloAutoTest.c`
- `build/hcu-ps2-closure/all/ps2_platform.c`
