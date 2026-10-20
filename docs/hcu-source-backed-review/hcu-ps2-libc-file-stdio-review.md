# M0 rooted file-backed Newlib stdio review (pending)

This batch reviewed the rooted file-backed Newlib stdio family. The symbols
resolve from Newlib, but that fact alone does not establish a correct CE PS2
file-service contract. The current guest and source-path evidence show a
read-only mounted-root bridge for HCU cache data, while several CE callers use
Xbox `d:`/`z:` paths, console input files, or writes. Stdout is a separate
already-reviewed `tty0:` path; this report does not reopen or broaden that
approval.

| Symbol | Rooted callers and risk | Required before disposition |
|---|---|---|
| `fopen` | CE camera/cheat/console/error/main/object/game-state paths and tag/cache diagnostics open paths with differing read/write modes. The PCSX2 M1 log records Xbox `d:` and `z:` paths rejected by the current host profile. | Establish device translation and per-mode contract; prove writes fail nonfatally where saves/configs are out of scope; test mapped reads and missing devices. |
| `fclose` | Paired with those `FILE*` paths across debug output, game state, and object/camera work. | Validate descriptor close, invalid handles, failed-open behavior, repeated close, and no descriptor/heap growth on every accepted source profile. |
| `fflush` | Used for diagnostics, game-state and structure lens-flare files; a no-op may lose output or leave stale buffered writes. | Prove its supported streams and write/flush failure semantics; do not treat console `tty0:` as file-backed data. |
| `fgets` | Reads cheat/config/console text. Its availability controls whether these file-driven features can proceed. | Exercise mapped read-only inputs, EOF, short lines, overlong lines, and unsupported Xbox roots. |
| `fprintf` | Formats file-backed debug dumps, error logs, and save data; distinct from reviewed `printf` to stdout. | Test format output plus the underlying file write/flush/error contract and save failure behavior. |
| `fputc` | Rooted by object output path; must not silently lose a required byte or report success on a failed file. | Verify actual byte write and return/error semantics on mapped and unavailable paths. |
| `fputs` | Rooted by object and structure-lens-flare file paths. | Verify complete write and error reporting, including partial/unavailable writes. |
| `fread` | Rooted from main startup/file reads and may supply data to a CE file path. | Verify element-count semantics on full, short, EOF, and failed reads through the chosen device adapter. |
| `fscanf` | Rooted by camera/director text input and can affect camera/config state. | Verify format parsing and mapped-path behavior, or prove the caller unreachable in the accepted local product path. |

The exact current caller sections/source hashes and rooted identities remain in
`docs/hcu-ps2-external-review.json`. These nine rows remain `pending`; the
regression `test_file_backed_newlib_stdio_stays_pending_until_device_contract`
prevents accidental promotion based only on their linked archive members.
This is an explicit source-backed risk review, not a platform implementation
or a conclusion that all nine functions must be absent forever.
