# Visible PCSX2 validation

The project runs PCSX2 on the existing desktop and retains evidence under ignored `build/emulator/`. BIOS bytes, sidecars, settings and captures are private build inputs or outputs, never tracked source. The supplied ROM0 has ROMVER `0110AC20000727`; its SHA-256 is `b0bf7184d50a209cf7ceb1ab0eb3a0c9b8c583f5f6b3c819e6536f282b93063b`.

## Local configuration

Create ignored `.local/emulator.json` with `binary` (PCSX2 launcher), `bios` (ROM0), `profile` (base profile directory), `display` (the desktop display), and `version`. This machine uses PCSX2 2.8.2 and display `:0.0`. Initialize the base settings at `<profile>/PCSX2/inis/PCSX2.ini`. PCSX2 appends `PCSX2` to its `-datapath` argument.

The runner copies the base settings and supplied BIOS/sidecars into a unique run directory. It uses `APPIMAGE_EXTRACT_AND_RUN=1` because FUSE is unavailable, and the XCB desktop backend. Desktop access requires execution outside the ordinary filesystem sandbox. No system packages or global emulator settings are changed.

## Launching C3 gameplay on this desktop

For Codex, run desktop commands with `exec_command` using
`sandbox_permissions="require_escalated"` and a justification that identifies
the requested PCSX2 launch. The ordinary sandbox cannot connect to the existing
X server and hides host processes. Inside it, `/tmp/.X11-unix` can appear owned
by `nobody`, and starting Xvfb can fail with an ownership error. These failures
do not establish that the desktop is unavailable. Check the existing desktop
outside the sandbox first:

```sh
DISPLAY=:0.0 XAUTHORITY=/home/ai/.Xauthority xdpyinfo >/dev/null
```

Use the existing display `:0.0`, the user's existing X authority, and the
installed PCSX2 AppImage. Run with the staged ELF's directory as the working
directory. PCSX2 resolves the guest's `host:` paths relative to this staged
location; the ELF, `maps/`, package paths and source map paths must all agree.
Use the isolated `data` directory from the launch manifest, which already
contains the BIOS and recompiler settings.

The following command launches the manual one-player Blood Gulch build on
2026-10-25. Execute it from the repository root, outside the sandbox. It starts
a persistent desktop window and saves logs under the build's `play/` directory.
Only start another instance after checking for an existing project-owned run;
stop an earlier run only after verifying its command line and process group.

```sh
python3 - <<'PY'
import datetime
import json
import os
from pathlib import Path
import subprocess

repo = Path.cwd()
manifest_path = repo / "build/c3/perf/object-sharing-ab-20261025-r1/quiet-baseline-v1/desktop-launch.json"
manifest = json.loads(manifest_path.read_text())
elf = Path(manifest["elf"])
play = elf.parent

# The generated image header pins the original package path. Mount that path
# too; mounting only the package-tree alias does not satisfy this build.
package = Path(manifest["package_file"])
alias = play / package.relative_to(repo)
alias.parent.mkdir(parents=True, exist_ok=True)
if alias.exists() or alias.is_symlink():
    assert alias.resolve() == package.resolve(), "Wrong staged package path"
else:
    alias.symlink_to(package)
assert alias.is_file(), "Missing package backing"

stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
emulog = play / f"desktop-{stamp}-emu.txt"
launcher = play / f"desktop-{stamp}-launcher.log"
env = dict(os.environ, DISPLAY=":0.0", XAUTHORITY="/home/ai/.Xauthority",
           APPIMAGE_EXTRACT_AND_RUN="1", QT_QPA_PLATFORM="xcb")
subprocess.run(["xdpyinfo", "-display", env["DISPLAY"]], env=env,
               stdout=subprocess.DEVNULL, check=True)
command = ["/home/ai/.local/bin/pcsx2", "-batch", "-nogui",
           "-datapath", manifest["data"], "-logfile", str(emulog),
           "-elf", str(elf)]
with launcher.open("wb") as output:
    process = subprocess.Popen(command, cwd=play, env=env, stdout=output,
                               stderr=subprocess.STDOUT, start_new_session=True)
record = {"pid": process.pid, "process_group": process.pid,
          "command": command, "cwd": str(play), "display": env["DISPLAY"],
          "log": str(emulog), "launcher_log": str(launcher)}
(manifest_path.parent / "desktop-active.json").write_text(
    json.dumps(record, indent=2) + "\n")
print(json.dumps(record, indent=2))
PY
```

This quiet build includes the controller configuration fix and has
`HCU_C3_TELEMETRY=0`, `HCU_C3_TIMING=0` and `HCU_C3_MOVEMENT_TRACE=0`. Separate
benchmark builds enable sparse timing. Both retain
failure and map lifecycle messages, so a successful process launch is only the
first check: wait for `production-ce-map-loaded result=1`, check the log for
guest failures, and inspect a gameplay capture. Quiet builds omit
`c3-render-ready` and `c3-frame`, so waiting for those markers would never finish.
For captures, the existing `tools/emulator_window.py` helper can locate windows
by the recorded process group and capture only the emulator window. Desktop
inspection and capture require the same execution context outside the sandbox.

The verified launch record is
`build/c3/perf/object-sharing-ab-20261025-r1/quiet-baseline-v1/desktop-active.json`; logs and captures are ignored build
artifacts. Keep timing-only and quiet builds in separate output directories:
changing compiler flags in an existing object directory can leave stale timing
code in an otherwise quiet executable.

The earlier quiet 2026-10-25 desktop launch reached
`production-ce-map-loaded result=1 map=bloodgulch` at log timestamp 99.0727 s.
The visible window was captured to
`build/c3/perf/quiet-r2/desktop-current.png`; it shows the gameplay HUD, textured
world and weapon geometry. The oversized/intersecting first-person geometry
remains a rendering defect, so this capture proves a visible gameplay launch
and does not qualify the C3 renderer. The manual-input session below replaced
that earlier emulator instance.

### Manual gameplay controls and FPS measurement

The isolated desktop profile can be configured for manual play with
`python3 tools/pcsx2_gameplay_controls.py --data PATH --show-fps`, where `PATH`
is the `data` directory passed to PCSX2's `-datapath`. Apply this only while
PCSX2 is stopped. The helper changes that isolated profile: arrow keys drive
the right stick (look), L3 is Control (crouch), R2 is F (fire), and Cross is G
(jump). It clears the arrow-key D-pad bindings to prevent overlap; WASD
movement remains available. `--show-fps` enables PCSX2's FPS, VPS and speed
OSD. The nominal NTSC 59.94 Hz mode and the OSD's VPS/emulation-speed values
are separate emulator metrics and are not themselves measured gameplay FPS.

For manually controlled desktop C3, use
`build/c3/perf/manual-one-view-20261025-r1`. Its `link_row(...,
workload_autofire=False)` setting disables the scripted fire pulses while
preserving the input loop; qualification builds keep the default scripted
workload. This timing-only build uses `HCU_C3_TELEMETRY=0` and
`HCU_C3_TIMING=1`, logging `c3-timing` samples on the first frame and every 30
frames. To measure sustained C3 FPS from samples after startup/warmup,
calculate `(last_frame - first_frame) / (last_log_timestamp -
first_log_timestamp)` using their frame numbers and PCSX2 log timestamps.
Report that measured interval separately from the nominal 59.94 Hz and the
OSD's VPS/speed values.

The manual run measured **2.39757 C3 frames/s** before any control-test input:
frame 30 at 113.6573 s through frame 150 at 163.7080 s, or 120 frames in
50.0507 s. Startup and the first 30 frames were excluded. The exact sample
records, executable hash and source log are in
`build/c3/perf/manual-one-view-20261025-r1/fps-measurement.json`. The sparse
phase samples in this interval average about 354 ms in frame-end/submission
and 26 ms building views; these are guest timer measurements, separate from
the frame rate calculated using host log timestamps.

Runtime snapshot evidence reports `first-person=1 parent=-1`: the local
player is on foot. `mounted_gunner_4p4bot` is the retained package/workload row
name; the desktop build requests one local player and the visible ELF is
named `bloodgulch-1p-manual.elf`. Its own full biped is now suppressed in the
first-person world pass while other views retain it. Oversized weapon geometry
still needs a separate rendering correction.

Live input verification changed the camera forward vector with Right/Up,
lowered camera height from 0.641 to 0.371 with Control, raised it during a G
jump, and produced a weapon fire response to F. The test released all keys.
`input-verification.json` and the `input-*.png` captures under the same run
directory retain the events and images. Scripted trigger pulses stayed disabled.

### Optimized resident HUD desktop build

The resident HUD optimization was measured in one-view Blood Gulch on this
desktop's PCSX2 recompiler: 2.3054 to 14.9850 game frames/s, about 6.5 times
faster. Both 640×480 frame-180 captures had identical decoded RGB pixels.
Warm resident HUD samples made zero backing reads, hashes or TEXS parses.
The [optimization report](reports/c3-hud-resident-optimization-2026-10-25.md)
records the exact executable/package tuple, timings, tests and limitations.
The oversized/intersecting first-person weapon geometry remains open.

The earlier resident-HUD desktop build is retained under
`build/c3/perf/hud-resident-quiet-20261025-r1/resident/`. Its
`desktop-launch.json` identifies the ELF, package, profile and working
directory; `desktop-active.json` identifies its owned process group and log.
It superseded the earlier manual timing session; newer checkpoints are below.

The workspace retains these build and launch helpers (with the private inputs
and run artifacts, under ignored `build/`):

```sh
python3 build/c3/perf/hud-resident-quiet-20261025-r1/build_quiet.py
python3 build/c3/perf/hud-resident-quiet-20261025-r1/launch_quiet.py
```

Run the launcher outside the ordinary sandbox, using the desktop access
described above. Check the active record before starting another instance.
The builder uses its own output directory and profile, one local player,
108,000 render frames, and disables scripted firing. Arrow look, Control
crouch, F fire, G jump and WASD movement are restored in this profile.

This build uses `HCU_C3_BITMAP_RESIDENT=1`, `HCU_C3_TELEMETRY=0` and
`HCU_C3_TIMING=0`. The per-frame timing/bitmap diagnostic strings are absent
from the ELF. Startup, lifecycle and failure messages remain available.
The FPS above comes from the separate matched timing builds, not the PCSX2
OSD refresh-rate value or an uninstrumented FPS measurement of the quiet ELF.

For a repeat comparison in this workspace, use the retained
`build/c3/perf/hud-resident-ab-20261025-r1/build_pair.py`, `run_pair.py` and
`score_pair.py` in that order. The runner fixes each owned window to 640×480,
disables benchmark keyboard input and OSD, captures frame 180, and stops only
its owned emulator group before hashing the log. Do not run it alongside the
interactive session; first verify and stop that session by its active record.

### Fixed-rate interactive simulation

The earlier fixed-rate interactive checkpoint used
`build/c3/perf/realtime-simulation-20261025-r1/quiet/desktop-active.json`.
It superseded the resident-only session above. Its isolated build enables
`HCU_C3_REALTIME_SCHEDULER=1` with timing and telemetry disabled, preserving
arrow look, Control crouch, F fire, G jump and WASD movement.

The retained helpers are:

```sh
python3 build/c3/perf/realtime-simulation-20261025-r1/build_desktop.py --quiet
python3 build/c3/perf/realtime-simulation-20261025-r1/launch_quiet.py
```

Use the same desktop execution context and owned-process checks described
above. The scheduler catches up fixed 30 Hz gameplay steps before drawing a
new frame. A separate timing run measured 30.0096 gameplay ticks/s while
rendering 14.9648 frames/s during movement; this fixes the former link between
low rendering FPS and half-speed gameplay. Bounded overruns can still drop
simulation steps, and the known first-person geometry defect remains.
See the [scheduler evidence](reports/c3-realtime-simulation-2026-10-25.md) and
the [twelve-agent 30 FPS review](reports/c3-30fps-review-2026-10-25.md).

### Combined renderer optimization checkpoint

The earlier combined-optimization quiet checkpoint is
`build/c3/perf/multiview-ab-20261025-r2/quiet-optimized-v1/`. Its active record
and `gameplay-quiet.png` show one-player Blood Gulch with manual controls,
29.97 FPS / 59.94 VPS / 100% emulation speed, and no hot C3 timing output.
The ELF SHA-256 is
`2124217d0683c6b0b5ad03cadd03ddd2c5c4b4b0505118d2bedbbe5ec0c39cd4`.
This retained checkpoint predates the controller configuration fix below.
Inspect the current active process record before controlling or launching
an instance, and use the corrected build for manual play.

The workspace helpers rebuild and launch a quiet optimized guest:

```sh
python3 build/c3/perf/multiview-ab-20261025-r2/build_case.py --case optimized --views 1 --quiet
python3 build/c3/perf/multiview-ab-20261025-r2/launch_quiet.py
```

This enables the resident HUD, realtime scheduler, object span path, per-view
setup cache, immutable-generation binding seal and snapshot identity index.
Timing and C3 telemetry remain disabled. The [multiview A/B report](reports/c3-multiview-fps-ab-2026-10-25.md)
records the controlled 1–4-view comparison, exact output parity, memory fit
and limitations. These flags preserve validation, bank-reader pins and DMA/GS
completion fences. First-person geometry remains a separate visual defect.

For reliable desktop comparisons, fix all test windows to the same monitor,
position and size and keep the owned test window unobscured while rendering.
The first matrix had position-dependent black XWD regions; the fixed-position
repeat produced exact full-frame baseline/optimized pixel parity at all four
view counts. A successful process launch or nonblack corner is insufficient.
The repeat's frame captures use the same recorded immutable snapshot after
the timed interval; ordinary interactive builds omit that capture/replay hook.

### Controller configuration fix

The corrected quiet Blood Gulch build is retained under
`build/c3/movement/fixed-quiet-20261025-r1/quiet-optimized-v1/`. Its manifest
pins parent `8be0d23`, CE `6e35c0c` and renderer `ed88dbc`; its ELF SHA-256 is
`3e5d95311b8485dad19a32b6196f5b571f63b1642fe995b6723f833632b30619`.
It retains the combined renderer optimizations and manual controls, with
timing, C3 telemetry and movement tracing all disabled.
The fresh quiet run reached map-loaded at 95.7116 s. Its full-window
`gameplay-quiet.png` capture shows 29.97 FPS / 59.94 VPS / 100% speed; manual
W and Right tests responded before any jump, with no recurring pad setup
messages. The active record identifies process group `931368`, left open
after testing. Check that record before controlling it. The weapon mesh
remains oversized/intersecting.

```sh
python3 build/c3/movement/fixed-quiet-20261025-r1/build.py --case optimized --views 1 --quiet
python3 build/c3/movement/fixed-quiet-20261025-r1/launch.py
```

The pad driver previously restarted asynchronous mode setup during normal
command-busy polls. That intermittently replaced held movement and look input
with neutral samples even at 30 FPS. The staged handshake now waits for each
request to complete and resets on a real disconnect. In the diagnostic
same-spawn regression test, grounded forward movement settled near 2.245
world units/s instead of the earlier 0.107 world units/s interval average;
arrow-key facing and the published camera updated on every active test frame.
The repaired run needed no jump or fall to recover input. These two speed
figures use different windows (steady speed versus whole-interval average),
so they are not a matched speedup ratio. See the
[controller evidence](reports/c3-controller-input-recovery-2026-10-25.md)
for interval measurements, tests, launch identities and limitations.

### Prepared world-object cache comparison

The subsequent [cross-view cache A/B](reports/c3-object-sharing-ab-2026-10-25.md)
measured the prior optimizations with `HCU_C3_OBJECT_PREPARE_CACHE=0` versus `1`.
All four framebuffer pairs matched, but FPS gains were inconsistent. The new
cache remains off by default; it is also off in the restored quiet desktop
build. That build retains the controller fix and all previous optimizations.

The current quiet launch manifest and active record are under
`build/c3/perf/object-sharing-ab-20261025-r1/quiet-baseline-v1/`. Its ELF SHA-256
is `830224d4cc9ab7909b99d1a80855d111ae111f730ccb2c3d7bb1b602c722db03`.
Within this experiment, `baseline` means only that the new preparation cache
is disabled; the resident HUD, fixed-rate scheduler and four earlier renderer
optimizations are enabled.

```sh
python3 build/c3/perf/object-sharing-ab-20261025-r1/build_case.py --case baseline --views 1 --quiet
python3 build/c3/perf/object-sharing-ab-20261025-r1/launch_quiet.py
```

Use the owned-process and desktop checks above before launching. Build and
launch manifests identify the exact source, package, emulator settings and
process group; do not infer the live session from an older capture.
The restored run was verified with a full `gameplay-quiet.png` capture at
29.97 FPS / 59.94 VPS / 100% speed. Its `reportquiet-verification.json`
records the owned window and source identity. Timing, movement tracing and
C3 telemetry remain disabled; the known first-person mesh issue persists.

### `Unknown device 'd'` and `Unknown device 'z'`

These messages are emitted by the PS2 SDK's I/O manager when a filename's
prefix before `:` does not match a registered device. CE still has direct
Xbox-style file operations: `source/cseries/errors.c` opens `d:\\debug.txt`,
and saved-game code uses `z:\\saved\\...`. The parent file bridge strips `d:`
for its bridged operations, but CE's direct C-library `fopen` calls bypass that
bridge. The SDK therefore receives an unsupported drive prefix.

CE enables debug-file output at initialization. When opening `d:\\debug.txt`
fails, no file handle is retained, so another error/log line tries the open
again and produces another SDK warning. Save-directory and optional-file
probes account for other potential drive-letter accesses. The SDK warning
contains only the device name, so it cannot identify the full path of each
individual failure without additional tracing. Disabling C3 telemetry does
not disable these SDK warnings. The current map package still loads through
its working `host:` paths; debug-file and Xbox save-path support remain
incomplete, and their failed I/O attempts have an unmeasured performance cost.

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

Accepted ELF SHA-256: `b62363fc5a536dede9db7ca886b4b6c4017bf0dc775bc4948c9873ff0484f711`. Aggregate: `build/emulator/platform-latest.json`; independent qualification: `build/emulator/platform-qualification.json`; allocated-section parity: `build/emulator/platform-elf-parity.json`. The implementation checkpoint is `a7c3bfa`. M06 closed at `9f57c87`. M07’s separate probe runs and qualification are recorded in `docs/gameplay-probe.md`.
