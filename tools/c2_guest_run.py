#!/usr/bin/env python3
"""Run the C2 guest evidence: stage HCU ELFs, check their load map, run them in PCSX2.

The lane stages HCU ELFs that the caller copied out of the parent-link probe output right
after each link (the probe output directory is shared, so the copies live in
build/m2-c2-r9-peaks/elf/). It never relinks, reads their LOAD segments with the EE
readelf, runs each one headless in PCSX2 under Xvfb with a bounded timeout, saves every
HALO_PS2_LOCAL line, and writes a manifest with sha256s.

The manifest is rewritten after every run, and again on any failure, so a partial
run still leaves manifest.json behind with the runs that finished.

Usage:
    python3 -I tools/c2_guest_run.py [--timeout SECONDS] [--only capacity|workload2p|workload4p|lifecycle]
                                     [--source-elf PATH]
"""

import argparse
import hashlib
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "build/m2-c2-r9-peaks"
PROBE = ROOT / "build/hcu-parent-link-probe"
PCSX2 = Path(os.environ.get("PCSX2_BIN", "/home/ai/.local/bin/pcsx2"))
READELF = ROOT / "build/toolchain/install/ee/bin/mips64r5900el-ps2-elf-readelf"
# The probe emulator profile (data/PCSX2 with the ROM0 and settings) is staged from a
# prior M1 run; it is copied, never modified in place.
PROFILE_TEMPLATE = ROOT / ("build/hcu-ps2-closure/"
                           "emulator-m1-interpreter-0139052a7cf940829aa1384ca8c0152f/data")

# The committed budget is 27,787,264 bytes (0x1a80000), and the reserve starts where it
# ends. Round 5 found the guest printing 0x1a00000, a stale literal; src/stream/hcu_main.c
# now prints the value derived from its committed-bytes constant.
GUEST_RESERVE_START = 0x1A80000

# Each run's ELF is a copy of one probe build (see the header). expected_sha_prefix is None:
# these builds are fresh from current source, so the pinned-sha check of earlier rounds does not
# apply; the sha256 of every staged ELF is recorded in the manifest instead.
RUNS = {
    "capacity": {
        "elf": "hcu-gameplay-machine-step8-mp-capacity-tagcache-4477120.elf",
        "source": OUT / "elf/hcu-gameplay-machine-step8-mp-capacity-tagcache-4477120.elf",
        "expected_sha_prefix": None,
    },
    "workload4p": {
        "elf": "hcu-gameplay-machine-step8-mp-workload-4p-tagcache-4477120.elf",
        "source": OUT / "elf/hcu-gameplay-machine-step8-mp-workload-4p-tagcache-4477120.elf",
        "expected_sha_prefix": None,
    },
    "workload2p": {
        "elf": "hcu-gameplay-machine-step8-mp-workload-2p-tagcache-4477120.elf",
        "source": OUT / "elf/hcu-gameplay-machine-step8-mp-workload-2p-tagcache-4477120.elf",
        "expected_sha_prefix": None,
    },
    "lifecycle": {
        "elf": "hcu-gameplay-machine-m2-ui-lifecycle.elf",
        "source": OUT / "elf/hcu-gameplay-machine-m2-ui-lifecycle.elf",
        "expected_sha_prefix": None,
    },
}

# Markers every run must show (prefix match after the log's timestamp).
REQUIRED_MARKERS = {
    "partition-selected": "HALO_PS2_LOCAL partition-selected ",
    "owner-telemetry": "HALO_PS2_LOCAL owner-telemetry ",
    "render-storage-bound": "HALO_PS2_LOCAL render-storage-bound ",
    "arena": "HALO_PS2_LOCAL arena ",
    "cache-owner": "HALO_PS2_LOCAL cache-owner ",
    "map-lifecycle": "HALO_PS2_LOCAL map-mount result=",
}
# The lifecycle test prints these once both unload/reload cycles finish (see
# tests/test_hcu_boot_physical.py for the expected sequence).
LIFECYCLE_EXTRA = ("HALO_PS2_LOCAL m2-ui-lifecycle-owner-released ",
                   "HALO_PS2_LOCAL m2-ui-lifecycle-complete ")
# The Step 8 workload runs have no map lifecycle; their required markers are the arena and
# owner lines and the workload's completion line, checked separately from the lifecycle set.
WORKLOAD_MARKERS = {
    "arena": "HALO_PS2_LOCAL arena ",
    "owner-telemetry": "HALO_PS2_LOCAL owner-telemetry ",
    "workload-complete": "HALO_PS2_LOCAL step8-mp-workload-complete ",
}

LOG_PREFIX = re.compile(r"^\[\s*[0-9.]+\]\s?")
LOAD_LINE = re.compile(
    r"^\s*LOAD\s+0x([0-9a-f]+)\s+0x([0-9a-f]+)\s+0x([0-9a-f]+)\s+0x([0-9a-f]+)\s+0x([0-9a-f]+)")


def sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_load_segments(readelf_text):
    """Return LOAD segments as dicts from `readelf -lW` output."""
    segments = []
    for line in readelf_text.splitlines():
        match = LOAD_LINE.match(line)
        if not match:
            continue
        offset, vaddr, paddr, filesz, memsz = (int(group, 16) for group in match.groups())
        segments.append({"offset": offset, "vaddr": vaddr, "paddr": paddr,
                         "filesz": filesz, "memsz": memsz, "end": vaddr + memsz})
    return segments


def highest_guest_byte(segments):
    return max((segment["end"] for segment in segments), default=0)


def halo_lines(log_text):
    """Every HALO_PS2_LOCAL line with its log timestamp removed, in order."""
    lines = []
    for raw in log_text.splitlines():
        if "HALO_PS2_LOCAL" not in raw and "HALO_PS2_FAIL" not in raw:
            continue
        lines.append(LOG_PREFIX.sub("", raw, count=1).strip())
    return lines


def check_markers(lines, lifecycle):
    """Map each required marker name to whether any line carries it."""
    found = {}
    for name, prefix in REQUIRED_MARKERS.items():
        found[name] = any(line.startswith(prefix) for line in lines)
    if lifecycle:
        found["lifecycle-unload-reload-complete"] = any(line.startswith(LIFECYCLE_EXTRA) for line in lines)
    return found


def numbers_of(line, key):
    """Integer value of key=N on a line, or None."""
    match = re.search(r"\b" + re.escape(key) + r"=(-?\d+)", line)
    return int(match.group(1)) if match else None


def summarize(lines):
    """Pull per-owner counters out of the owner, cache, arena and map lines."""
    summary = {"arenas": {}, "cache_owners": {}, "owner_telemetry": [],
               "partition_selected": [], "map_lifecycle": [], "errors": []}
    for line in lines:
        if line.startswith("HALO_PS2_LOCAL arena "):
            name = re.search(r"name=(\S+)", line).group(1)
            summary["arenas"][name] = {key: numbers_of(line, key) for key in ("cap", "used", "high")}
        elif line.startswith("HALO_PS2_LOCAL cache-owner "):
            name = re.search(r"name=(\S+)", line).group(1)
            summary["cache_owners"].setdefault(name, []).append(
                {"phase": re.search(r"phase=(\S+)", line).group(1),
                 "current": numbers_of(line, "current"), "peak": numbers_of(line, "peak")})
        elif line.startswith("HALO_PS2_LOCAL owner-telemetry "):
            summary["owner_telemetry"].append(line)
        elif line.startswith("HALO_PS2_LOCAL partition-selected "):
            summary["partition_selected"].append(line)
        elif line.startswith(("HALO_PS2_LOCAL map-", "HALO_PS2_LOCAL cache-ui")):
            summary["map_lifecycle"].append(line)
        elif "[err]" in line or "HALO_PS2_FAIL" in line or "Address Error" in line:
            summary["errors"].append(line)
    return summary


def ensure_display():
    display = os.environ.get("C2_GUEST_DISPLAY", ":99")
    os.environ["DISPLAY"] = display
    probe = subprocess.run(["xdpyinfo", "-display", display], capture_output=True, text=True)
    if probe.returncode != 0:
        subprocess.Popen(["Xvfb", display, "-screen", "0", "1280x1024x24"],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
        time.sleep(2)
    return display


def stage(which, source_override=None):
    """Copy the probe ELF into the lane directory and verify its bytes.

    A --source-elf override (a fresh build from current source) skips the pinned sha
    check; the sha is still recorded in the manifest so the run stays traceable.
    """
    spec = RUNS[which]
    elf_dir = OUT / "elf"
    elf_dir.mkdir(parents=True, exist_ok=True)
    dest = elf_dir / spec["elf"]
    source = source_override or spec["source"]
    if Path(source).resolve() != dest.resolve():
        shutil.copy2(source, dest)
    digest = sha256(dest)
    sha_checked = spec["expected_sha_prefix"] is not None and source_override is None
    if sha_checked and not digest.startswith(spec["expected_sha_prefix"]):
        raise RuntimeError(f"{spec['elf']} sha256 {digest} does not start with "
                           f"{spec['expected_sha_prefix']}")
    readelf = subprocess.run([str(READELF), "-lW", str(dest)], capture_output=True, text=True, check=True)
    segments = parse_load_segments(readelf.stdout)
    return {"path": str(dest), "sha256": digest, "sha_checked": sha_checked,
            "load_segments": segments, "highest_guest_byte": highest_guest_byte(segments)}


def run_guest(which, elf_info, timeout):
    lane_run = OUT / "runs" / which
    if lane_run.exists():
        shutil.rmtree(lane_run)
    lane_run.mkdir(parents=True)
    data = lane_run / "data"
    shutil.copytree(PROFILE_TEMPLATE, data)
    elf_copy = lane_run / Path(elf_info["path"]).name
    shutil.copy2(elf_info["path"], elf_copy)
    # PCSX2's host: root is the ELF's directory, which must hold the probe's maps/.
    (lane_run / "maps").symlink_to(PROBE / "maps")
    log = lane_run / "emu.txt"
    command = [str(PCSX2), "-batch", "-nogui", "-datapath", str(data),
               "-logfile", str(log), "-elf", str(elf_copy)]
    env = {**os.environ, "APPIMAGE_EXTRACT_AND_RUN": "1", "QT_QPA_PLATFORM": "xcb"}
    start = time.monotonic()
    with (lane_run / "launcher.log").open("w") as launcher:
        process = subprocess.Popen(command, cwd=lane_run, env=env, stdout=launcher,
                                   stderr=subprocess.STDOUT, start_new_session=True)
        try:
            process.wait(timeout=timeout)
            exit_status = f"exited {process.returncode}"
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGINT)
            try:
                process.wait(timeout=20)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()
            exit_status = f"bounded timeout after {timeout}s (SIGINT)"
    elapsed = round(time.monotonic() - start, 1)
    text = log.read_text(errors="replace") if log.exists() else ""
    lines = halo_lines(text)
    (lane_run / "halo_ps2_local.txt").write_text("\n".join(lines) + "\n")
    lifecycle = which == "lifecycle"
    markers = check_markers(lines, lifecycle)
    if which.startswith("workload"):
        markers = {name: any(line.startswith(prefix) for line in lines)
                   for name, prefix in WORKLOAD_MARKERS.items()}
    return {"run": which, "elf": elf_info["path"], "elf_sha256": elf_info["sha256"],
            "exit": exit_status, "elapsed_seconds": elapsed, "log": str(log),
            "halo_lines_saved": str(lane_run / "halo_ps2_local.txt"), "halo_line_count": len(lines),
            "markers": markers, "markers_all_present": all(markers.values()),
            "summary": summarize(lines)}


def write_manifest(path, manifest):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, indent=2) + "\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    parser.add_argument("--timeout", type=int, default=600, help="seconds per guest run")
    parser.add_argument("--only", choices=tuple(RUNS), help="run one guest only")
    parser.add_argument("--source-elf", type=Path,
                        help="stage this ELF for --only instead of the lane copy in build/m2-c2-r9-peaks/elf/")
    args = parser.parse_args()
    if args.source_elf and not args.only:
        parser.error("--source-elf requires --only")
    OUT.mkdir(parents=True, exist_ok=True)
    selected = [args.only] if args.only else list(RUNS)
    display = ensure_display()
    manifest = {"lane": "guest", "date": "2026-10-24", "display": display,
                "pcsx2": str(PCSX2), "pcsx2_sha256": sha256(PCSX2),
                "guest_reserve_start": hex(GUEST_RESERVE_START), "timeout_seconds": args.timeout,
                "no_run_errors": False, "elfs": {}, "runs": []}
    manifest_path = OUT / "manifest.json"
    # Keep the results of earlier invocations for guests this one does not repeat.
    if manifest_path.exists():
        previous = json.loads(manifest_path.read_text())
        kept = [run for run in previous.get("runs", []) if run.get("run") not in selected]
        manifest["runs"].extend(kept)
        manifest["elfs"].update({key: value for key, value in previous.get("elfs", {}).items()
                                 if key not in selected})
    try:
        for which in selected:
            try:
                info = stage(which, args.source_elf.resolve() if args.source_elf else None)
                manifest["elfs"][which] = {key: info[key] for key in
                                           ("path", "sha256", "sha_checked", "highest_guest_byte")}
                manifest["elfs"][which]["highest_below_guest_reserve"] = info["highest_guest_byte"] < GUEST_RESERVE_START
                manifest["elfs"][which]["load_segments"] = info["load_segments"]
                manifest["runs"].append(run_guest(which, info, args.timeout))
            except Exception as error:  # record the failure and keep the partial manifest
                manifest["runs"].append({"run": which, "error": f"{type(error).__name__}: {error}"})
            write_manifest(manifest_path, manifest)
    finally:
        manifest["no_run_errors"] = all("error" not in run for run in manifest["runs"])
        write_manifest(manifest_path, manifest)
    print(f"manifest: {manifest_path}")
    for run in manifest["runs"]:
        print(run["run"], run["exit"], "lines", run["halo_line_count"],
              "markers_all_present", run["markers_all_present"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
