# M0 rooted Win32 file API review

This review covers the rooted Win32 file surface shared by CE's tag-file facade,
Xbox saved-game code, profile metadata, and HaloAutoTest. It does not turn M1's
read-only asset bridge into a general filesystem, nor approve the generated
placeholder functions.

## Caller inventory and current contract

`source/tag_files/files_windows.c` owns the normal `file_create`, `file_open`,
`file_delete`, `file_exists`, `file_read_only`, `file_get_last_modification_date`,
`file_get_size`, `find_files_next`, `file_read`, `file_write`, `file_set_eof`,
and position wrappers. Important semantics are checked by CE: `file_read`
rejects short reads, `file_write` requires a complete byte count, and failed
operations report `GetLastError`. The host game-state family in
`source/saved games/game_state_xbox.c` additionally creates/truncates/deletes
`z:\\savegame.bin` and writes `d:\\core` files. HaloAutoTest probes and reads or
writes `d:\\*.xts`. `saved_game_files.c` copies profile metadata on rename.

The parent bridge (`src/stream/hcu_file_bridge.c`) has 16 fixed descriptors,
maps `d:\\` to a relative asset path, and delegates bounded reads/seeks/stats
to the FileXio reader. `port/ps2/src/ps2_edge.c` implements a narrow
read-only subset: `CreateFileA` accepts only `GENERIC_READ` and
`OPEN_EXISTING`; `ReadFile`, `GetFileSize`, `SetFilePointer`, and attribute
queries delegate to that bridge. The bridge returns actual read counts,
rejects invalid slots/paths, and seeks only inside `[0, file_size]`. These
facts support diagnostic/optical read tests but not writes, OPL mount behavior,
or every CE caller.

## Unresolved semantics

- `CreateFileA` is mixed-mode: cache/tag reads can use the implemented subset,
  while save/export/HaloAutoTest callers request create, write, or truncate.
  Failure is currently explicit, but whether every such failure is harmless
  to local startup and gameplay has not been proven.
- `WriteFile`, `SetEndOfFile`, `CreateDirectoryA`, `DeleteFileA`, and
  `CopyFileA` need a writable-storage owner and exact short-write/atomicity/
  deletion policy. The M1 profile is read-only; generated failures are not
  equivalent to a successful write.
- `FindFirstFileA`/`FindNextFileA` have no search-handle implementation. CE's
  `find_files_next` uses wildcard enumeration and closes the handle on normal
  exhaustion. Returning no first match can hide files rather than prove the
  product has no enumeration requirement.
- `GetFileAttributesA` exposes only normal-file/directory bits, not read-only
  status; `GetFileAttributesExA` currently leaves `ftLastWriteTime` untouched,
  but CE copies it to the caller while reporting success. The latter is a
  concrete undefined-output defect.
- `GetFileSize`, `ReadFile`, and `SetFilePointer` are useful for the supported
  bounded read subset, but rooted sources also include Xbox save and
  HaloAutoTest callers whose paths/modes are not qualified by the asset reader.

Keep all reviewed symbols pending until the product's writable-save policy,
directory enumeration contract, deterministic timestamp behavior, and actual
mounted-device path matrix are resolved. Do not paper over these findings by
making unsupported write calls return success.

## Evidence and follow-up tests

The exact rooted callers are in `build/hcu-ps2-closure/all/result.json` under
`rooted_link.live_externals`. The current source review regression is
`tests/test_hcu_external_review.py::test_rooted_file_mutations_remain_pending_without_writable_storage_contract`.
It locks down call families, the 16-slot read-only bridge, checked short-read
behavior, unsupported mutations/enumeration, and the uninitialized timestamp
field. It is a source regression, not an EE device qualification. Future
acceptance still needs open/read/seek/stat/close and malformed-path tests on
each supported medium, short reads/EOF, pool exhaustion/reuse, file and
directory enumeration, deterministic timestamps, plus explicit read-only
failure tests for every mutation caller.
