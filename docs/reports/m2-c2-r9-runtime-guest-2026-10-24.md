# M2 C2 r9 runtime guest evidence (2026-10-24)

Lane: runtime-guest (C2.2 and C2.4 guest proof of the production profile runtime).
Build and run directory: `build/m2-c2-r9-runtime/` (link in `link/`, run in `run/`, result in `guest_result.json`).
Row: `sidewinder_marine_shotgun_4p4bot` (profile 26, map `sidewinder`), the partition-selected ELF.

## Changed files

- No source file was changed by this lane. The lane's own files are the scripts in `build/m2-c2-r9-runtime/`
  (`link_image.py`, `run_guest.py`, `run_wiring_tests.py`) and the outputs there. No file under `src/`, `tools/` or `tests/` was edited.

## Frame owner (task 1): not wired, fail-closed kept

- `hcu_main.c` has no reference to the bitmap frame owner, and no production path calls
  `hcu_bitmap_frame_owner_init` or `hcu_bitmap_frame_owner_bind`. The only binds are in `tests/hcu_bitmap_frame_owner_main.c`.
- `hcu_map_service.c` reads `rt->frame_owner` and returns "not drained" when it is NULL. The registration path
  (`hcu_register_selected_runtime`) builds `hcu_map_profile_runtime` with `memset` to 0, so `frame_owner` stays NULL.
- Result: there is no bound bitmap frame owner in production startup to wire. Unload and successor staging stay
  fail-closed. Creating one (queue, dispatch, fence query and renderer attachment) is a cross-lane change, not a
  one-line `frame_owner` assignment, so it is not made here. See "Cross-lane changes".

## Link (task 2)

- Objects: the 62 r8 EE objects in `build/m2-c2-r8-runtime/ee-gameplay/` (read only), plus the six closure objects
  from `build/hcu-ps2-closure/all-no-bootstrap-memory/`. Linked with the r8 link line into
  `build/m2-c2-r9-runtime/link/hcu-partition-image.elf` (`python3 -I build/m2-c2-r9-runtime/link_image.py`): rc 0,
  4,958,640 bytes, `nm -u` empty.
- LOAD segment: `vaddr 0x100000, memsz 0x3e2cbc`, so the highest guest byte is `0x4e2cbc` (5,123,260).
  The reserve starts at `0x1a80000` (27,787,264). The highest byte is 22,664,004 bytes below the reserve start.
- The objects are not rebuilt from current source in this lane. The r8 object set was reused as it stood.

## Staging

- The run directory is `build/m2-c2-r9-runtime/run/`. It holds the ELF copy, a copy of the probe emulator
  profile template, a `maps` symlink to `build/hcu-parent-link-probe/maps`, and `build/` symlinks to
  `build/m2-c2-r3-selected-packages` and `build/retail-maps`, so that the header's relative paths resolve under
  `host:/`. The package is `build/m2-c2-r3-selected-packages/pkg/sidewinder_marine_shotgun_4p4bot/sidewinder_marine_shotgun_4p4bot.hcp`
  (29,531,846 bytes). The source maps are `build/retail-maps/decompressed/{a50,beavercreek,c10,c40,sidewinder}.map`.

## Run

- `tools/c2_guest_run.py` was not run directly, because it writes to `build/m2-c2-r9-peaks/` (another lane's output)
  and its run table has no partition-selected entry. Its helper functions were imported read only
  (`halo_lines`, `check_markers`, `summarize`, `parse_load_segments`, `highest_guest_byte`, `sha256`), and
  `run_guest.py` launched PCSX2 with the runner's command line into `build/m2-c2-r9-runtime/run/`.
- Command: `timeout 700 python3 -I build/m2-c2-r9-runtime/run_guest.py`, guest bound 600 s, Xvfb `:99` (already up, reused).
- PCSX2 log: `build/m2-c2-r9-runtime/run/emu.txt`; HALO lines: `build/m2-c2-r9-runtime/run/halo_ps2_local.txt`.

## Results

- Boot output, the only HALO lines produced (exact, from `emu.txt`):

      [    1.5642] HALO_PS2_LOCAL machine entry
      [    1.5644] [err] ELF/boot backing exceeds EE fixed budget

- The guest halted at 1.56 s. No `partition-selected`, `profile-runtime`, map-mount, owner-telemetry,
  boundary, or arena line was produced. The registration result is therefore **not reached**, so no
  "qualified=1" line is observed. The budget error is the one the lane brief expected until C2.3 closes.
- The halt line `[err] ELF/boot backing exceeds EE fixed budget` is in the raw `emu.txt` at 1.5644 s. It has no
  `HALO_PS2_LOCAL` prefix, so the runner's HALO filter (`halo_ps2_local.txt`, one line) drops it.
- PCSX2 stayed idle (0% CPU) after the halt. The run ended at the 600 s bound (`bounded timeout after 600s (SIGINT)`),
  and `guest_result.json` records it. Its `summary.errors` list is empty because of the same filter.
- Partition-selected qualified=1: **not observed** (the ELF halts before the partition-selected line).
- Map mount result: **not observed**.
- Highest guest byte against the reserve (0x1a80000): `0x4e2cbc` (5,123,260), below the reserve start by 22,664,004 bytes.

## Wiring test

- `python3 -I build/m2-c2-r9-runtime/run_wiring_tests.py` runs `tests/test_hcu_main_wiring.py` with its scratch
  `OUT` moved to `build/m2-c2-r9-runtime/wiring-scratch` (the test's default writes into `build/m2-c2-r8-runtime`).
  Result: 16 tests, OK.

## Open gaps

- The ELF halts at the EE fixed budget (`ELF/boot backing exceeds EE fixed budget`) before registration. The
  registration path, the package and source reads, and the map mount are untested at run time. This blocks the
  lane's goal until C2.3 closes the budget.
- `frame_owner` is NULL. No production bitmap frame owner exists to pass.
- Source maps are size-checked on the EE only. The SHA-256 check happens in the host generator.
- The package and source paths are resolved under `host:/` and the ELF's directory. This is verified only by the
  staging layout above, and the halt happened before any read.
- The objects were not rebuilt from the current source tree in this lane.

## Cross-lane changes needed (not made here)

1. A production bitmap frame owner: construct and bind `hcu_bitmap_frame_owner` in startup (`hcu_main.c`, C3/C2 owner)
   and set `runtime.frame_owner` in `hcu_register_selected_runtime`. Until then unload and successor staging fail closed.
2. The budget lane must bring the partition-selected ELF under the EE fixed budget (the "ELF/boot backing" check),
   so the registration can run.
3. `tools/c2_guest_run.py` has no partition-selected run and writes to `build/m2-c2-r9-peaks/`. A lane-scoped output
   option and a partition run entry are needed for the runtime lane to use it without the workaround above.

## Verdict

- C2.2 (runtime registration proof on the guest): **not passed**. The ELF halts at the budget check before registration.
- C2.4 (guest proof of the production profile runtime): **not passed**. Registration is not reached on the guest,
  and the frame owner stays fail-closed because no production owner exists.
