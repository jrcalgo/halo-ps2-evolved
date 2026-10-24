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

# Budget v3: the reserve starts after 1 MiB low kernel + elf_static + the boot backing
# (MEM_LAYOUT_V2_BYTES = 24,117,248), i.e. 0x1a40000. Derived from config/memory-budget.json,
# matching HCU_RESERVE_START in src/stream/hcu_main.c.
MEM_LAYOUT_V2_BYTES = 24117248
LOW_KERNEL_BYTES = 0x100000
_BUDGET = json.loads((ROOT / "config/memory-budget.json").read_text())
ELF_STATIC_BYTES = next(r["bytes"] for r in _BUDGET["regions"] if r["name"] == "elf_static")
GUEST_RESERVE_START = LOW_KERNEL_BYTES + ELF_STATIC_BYTES + MEM_LAYOUT_V2_BYTES

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


def pcsx2_config_identity(data_dir: Path) -> dict:
    """Describe the exact copied PCSX2 config and selected BIOS bytes."""
    ini = data_dir / "PCSX2/inis/PCSX2.ini"
    text = ini.read_text(errors="replace") if ini.is_file() else ""
    section, values = None, {}
    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith("[") and line.endswith("]"):
            section = line[1:-1]
        elif "=" in line and section in ("EmuCore/CPU/Recompiler", "Filenames"):
            key, value = (part.strip() for part in line.split("=", 1))
            values[(section, key)] = value
    switches = {key: values.get(("EmuCore/CPU/Recompiler", key)) for key in
                ("EnableEE", "EnableIOP", "EnableVU0", "EnableVU1")}
    selected_bios = values.get(("Filenames", "BIOS"))
    bios_files = data_dir / "PCSX2/bios"
    bios_identity = []
    if bios_files.is_dir():
        candidates = ([bios_files / selected_bios] if selected_bios else [])
        candidates.extend(p for p in (bios_files / name for name in
                          ("SCPH-30001.rom1", "SCPH-30001.rom2", "SCPH-30001.nvm", "SCPH-30001.mec"))
                          if p.is_file() and p not in candidates)
        for path in candidates:
            if path.is_file():
                bios_identity.append({"name": path.name, "bytes": path.stat().st_size,
                                      "sha256": sha256(path), "selected": path.name == selected_bios})
    return {"config_path": str(ini), "config_sha256": sha256(ini) if ini.is_file() else None,
            "recompiler_switches": switches,
            "execution_backend": ("recompiler-enabled" if any(value == "true" for value in switches.values())
                                 else "interpreter-configured" if switches and
                                 all(value == "false" for value in switches.values())
                                 else "switches-unavailable"),
            "selected_bios": selected_bios, "bios_files": bios_identity}


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
        if ("HALO_PS2_LOCAL" not in raw and "HALO_PS2_FAIL" not in raw and
                "[err]" not in raw and "Address Error" not in raw):
            continue
        lines.append(LOG_PREFIX.sub("", raw, count=1).strip())
    return lines


def check_markers(lines, lifecycle, production=False):
    """Map each required marker name to whether any line carries it."""
    found = {}
    for name, prefix in REQUIRED_MARKERS.items():
        found[name] = any(line.startswith(prefix) for line in lines)
    if lifecycle:
        found["lifecycle-owner-released"] = any(
            line.startswith(LIFECYCLE_EXTRA[0]) for line in lines)
        found["lifecycle-complete"] = any(
            line.startswith(LIFECYCLE_EXTRA[1]) for line in lines)
    if production:
        found["selected-profile-runtime"] = any(
            line.startswith("HALO_PS2_LOCAL profile-runtime row=") for line in lines)
        found["ce-scenario-and-bsp-loaded"] = any(
            line.startswith("HALO_PS2_LOCAL production-ce-map-loaded result=1 ")
            for line in lines)
        found["ce-map-owner-released"] = any(
            line.startswith("HALO_PS2_LOCAL production-ce-map-released result=1 ")
            for line in lines)
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
        elif line.startswith(("HALO_PS2_LOCAL map-", "HALO_PS2_LOCAL cache-ui",
                              "HALO_PS2_LOCAL production-ce-")):
            summary["map_lifecycle"].append(line)
        elif "[err]" in line or "HALO_PS2_FAIL" in line or "Address Error" in line:
            summary["errors"].append(line)
    return summary


def ensure_display():
    """Return (display, owned Xvfb process); wait for our server to become usable."""
    display = os.environ.get("C2_GUEST_DISPLAY", ":99")
    probe = subprocess.run(["xdpyinfo", "-display", display], capture_output=True, text=True)
    if probe.returncode == 0:
        return display, None
    server = subprocess.Popen(["Xvfb", display, "-screen", "0", "1280x1024x24", "-nolisten", "tcp"],
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                              start_new_session=True)
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        if server.poll() is not None:
            raise RuntimeError(f"Xvfb exited early ({server.returncode}) for {display}")
        probe = subprocess.run(["xdpyinfo", "-display", display], capture_output=True, text=True)
        if probe.returncode == 0:
            return display, server
        time.sleep(0.2)
    server.terminate()
    try:
        server.wait(timeout=3)
    except subprocess.TimeoutExpired:
        server.kill()
        server.wait()
    raise RuntimeError(f"Xvfb did not become ready on {display}: {probe.stderr.strip()}")


def stage(which, source_override=None, out_dir=OUT):
    """Copy the probe ELF into the lane directory and verify its bytes.

    A --source-elf override (a fresh build from current source) skips the pinned sha
    check; the sha is still recorded in the manifest so the run stays traceable.
    """
    spec = RUNS[which]
    elf_dir = out_dir / "elf"
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


def _is_guest_fault(line: str) -> bool:
    return ("HALO_PS2_FAIL" in line or "[err]" in line or "Address Error" in line or
            "HALO_PS2_LOCAL halt" in line or "branch delay!!" in line or
            "EXCEPTION halt" in line)


def _post_entry_faults(lines: list[str]) -> list[str]:
    """Ignore the BIOS diagnostic that appears before CE machine entry."""
    entry = next((i for i, line in enumerate(lines)
                 if line.startswith("HALO_PS2_LOCAL machine entry")), None)
    if entry is None:
        return []
    return [line for line in lines[entry:] if _is_guest_fault(line)]


def _boot_diagnostics(lines: list[str]) -> list[str]:
    entry = next((i for i, line in enumerate(lines)
                 if line.startswith("HALO_PS2_LOCAL machine entry")), len(lines))
    return [line for line in lines[:entry] if _is_guest_fault(line)]


def _production_terminal(log_path: Path) -> str | None:
    text = log_path.read_text(errors="replace") if log_path.exists() else ""
    lines = halo_lines(text)
    if _post_entry_faults(lines):
        return "guest-error"
    if "production-ce-map-released result=" in text:
        return "release-marker"
    return None


def _run_terminal(which: str, log_path: Path) -> str | None:
    if which == "partition-selected":
        return _production_terminal(log_path)
    text = log_path.read_text(errors="replace") if log_path.exists() else ""
    lines = halo_lines(text)
    if _post_entry_faults(lines):
        return "guest-error"
    if which == "capacity" and any(
            "HALO_PS2_LOCAL step8-mp-capacity-complete maps=13 query_only=1" in line
            for line in lines):
        return "completion-marker"
    if which in ("workload2p", "workload4p"):
        players = 2 if which == "workload2p" else 4
        scope_reported = any("HALO_PS2_LOCAL step8-mp-workload " in line and
                             re.search(rf"\blocal_players={players}\b", line) and
                             "bots=not-exercised" in line for line in lines)
        workload_done = any("HALO_PS2_LOCAL step8-mp-workload-complete " in line and
                            re.search(rf"\blocal_players={players}\b", line) and
                            "ticks=3" in line and "teardown=clean" in line
                            for line in lines)
        if scope_reported and workload_done:
            return "completion-marker"
    if which == "lifecycle" and any(
            "HALO_PS2_LOCAL m2-ui-lifecycle-complete " in line for line in lines):
        return "completion-marker"
    return None


def _stop_owned_process(process: subprocess.Popen, grace: float = 5.0) -> str:
    if process.poll() is not None:
        return f"host-exited-{process.returncode}"
    os.killpg(process.pid, signal.SIGINT)
    try:
        process.wait(timeout=grace)
        return f"host-stopped-sigint-{process.returncode}"
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGKILL)
        process.wait()
        return f"host-stopped-sigkill-{process.returncode}"


def production_guest_qualification(lines: list[str]) -> dict:
    """Require exact selected tuple identity and a real CE mount/release sequence."""
    keys = ("partition_selected", "profile_runtime", "profile_map_mount",
            "ce_map_loaded", "ce_map_released")
    markers = (
        "HALO_PS2_LOCAL partition-selected ",
        "HALO_PS2_LOCAL profile-runtime row=",
        "HALO_PS2_LOCAL map-mount result=1 active=1 ",
        "HALO_PS2_LOCAL production-ce-map-loaded result=1 ",
        "HALO_PS2_LOCAL production-ce-map-released result=1 ",
    )
    positions = [next((i for i, line in enumerate(lines)
                       if line.startswith(marker)), None) for marker in markers]
    ordered = (all(pos is not None for pos in positions) and
               positions == sorted(positions))
    errors = _post_entry_faults(lines)
    return {"guest_completed": bool(ordered and not errors),
            "production_marker_order": dict(zip(keys, positions)),
            "guest_error_lines": errors,
            "boot_diagnostics": _boot_diagnostics(lines)}


def _fields(line: str) -> dict[str, str]:
    return dict(re.findall(r"(?:^|\s)([a-z][a-z0-9_-]*)=([^\s]+)", line))


def _int_field(fields: dict[str, str], key: str) -> int:
    try:
        return int(fields.get(key, "0"), 10)
    except ValueError:
        return 0


def production_tuple_qualification(lines: list[str], row: str, map_name: str,
                                   profile_id: int, package_bytes: int,
                                   released_map: str | None = None) -> dict:
    base = production_guest_qualification(lines)
    markers = {}
    for key, prefix in (("partition", "HALO_PS2_LOCAL partition-selected "),
                         ("runtime", "HALO_PS2_LOCAL profile-runtime row="),
                         ("mount", "HALO_PS2_LOCAL map-mount "),
                         ("loaded", "HALO_PS2_LOCAL production-ce-map-loaded "),
                         ("released", "HALO_PS2_LOCAL production-ce-map-released ")):
        markers[key] = next((line for line in lines if line.startswith(prefix)), "")
    p = _fields(markers["partition"])
    r = _fields(markers["runtime"])
    m = _fields(markers["mount"])
    loaded = _fields(markers["loaded"])
    released = _fields(markers["released"])
    checks = {
        "partition_row_matches": p.get("name") == row and p.get("qualified") == "1",
        "runtime_tuple_matches": r.get("row") == row and r.get("map") == map_name and
            r.get("profile") == str(profile_id) and
            r.get("package-bytes") == str(package_bytes),
        "profile_map_mount_matches": m.get("result") == "1" and m.get("active") == "1" and
            m.get("map") == map_name and m.get("source") == "profile-runtime",
        "ce_scenario_bsp_loaded": loaded.get("result") == "1" and
            loaded.get("map") == map_name and loaded.get("scenario") == "1" and
            loaded.get("tag-table") == "1" and
            _int_field(loaded, "tag-count") > 0 and
            _int_field(loaded, "tag-bytes") > 0 and
            _int_field(loaded, "bsp-bytes") > 0,
        "ce_owner_released": released.get("result") == "1" and
            released.get("map") == (released_map or map_name) and released.get("mounted") == "0" and
            released.get("tag-bytes") == "0" and released.get("bsp-bytes") == "0",
    }
    base["tuple_checks"] = checks
    base["guest_completed"] = base["guest_completed"] and all(checks.values())
    return base


def mount_guest_package_tree(lane_run: Path, package_tree: Path, guest_package_root: str):
    mount = Path(guest_package_root)
    if mount.is_absolute() or ".." in mount.parts or not mount.parts:
        raise ValueError("guest package root must be a non-empty relative host: path")
    mount_path = lane_run / mount
    mount_path.parent.mkdir(parents=True, exist_ok=True)
    mount_path.symlink_to(Path(package_tree).resolve())


def stage_host_paths(lane_run: Path, relative_paths):
    """Symlink repo-relative files into the run's host:/ root so the guest can open them.

    Paths must be relative, free of '..', and exist under the repo; a path already
    reachable through an earlier symlink (for example build/retail-maps) is skipped.
    """
    staged = []
    for text in relative_paths:
        rel = Path(text)
        if rel.is_absolute() or ".." in rel.parts or not rel.parts:
            raise ValueError(f"host staging path must be relative without '..': {text}")
        source = ROOT / rel
        if not source.exists():
            raise FileNotFoundError(f"host staging source is missing: {source}")
        target = lane_run / rel
        if target.exists():
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.symlink_to(source.resolve())
        staged.append(str(rel))
    return staged


FFMPEG = shutil.which("ffmpeg") or "/home/ai/miniconda3/envs/dl/bin/ffmpeg"


def capture_root(display, base):
    """C3: `xwd -root` of the guest display, converted to PNG. Returns a result dict."""
    xwd = base.with_suffix(".xwd")
    png = base.with_suffix(".png")
    env = {**os.environ, "DISPLAY": display}
    r = subprocess.run(["xwd", "-root", "-silent", "-out", str(xwd)], env=env, capture_output=True)
    if r.returncode != 0:
        return {"file": None, "error": r.stderr.decode(errors="replace").strip()}
    c = subprocess.run([FFMPEG, "-loglevel", "error", "-y", "-i", str(xwd), str(png)], capture_output=True)
    if c.returncode != 0:
        return {"file": str(xwd), "error": "ffmpeg: " + c.stderr.decode(errors="replace").strip()}
    return {"file": str(png), "xwd": str(xwd), "bytes": png.stat().st_size}


def run_guest(which, elf_info, timeout, out_dir=OUT, package_tree=None,
              maps_dir=PROBE / "maps", production_tuple=None,
              guest_package_root="build/m2-c2-r3-selected-packages", stage_paths=(),
              capture_dir=None, capture_markers=()):
    lane_run = out_dir / "runs" / which
    if lane_run.exists():
        shutil.rmtree(lane_run)
    lane_run.mkdir(parents=True)
    data = lane_run / "data"
    shutil.copytree(PROFILE_TEMPLATE, data)
    config_identity = pcsx2_config_identity(data)
    elf_copy = lane_run / Path(elf_info["path"]).name
    shutil.copy2(elf_info["path"], elf_copy)
    # PCSX2's host: root is the ELF's directory, which must hold the probe's maps/.
    (lane_run / "maps").symlink_to(Path(maps_dir).resolve())
    if package_tree:
        mount_guest_package_tree(lane_run, package_tree, guest_package_root)
        (lane_run / "build/retail-maps").symlink_to((ROOT / "build/retail-maps").resolve())
        stage_host_paths(lane_run, stage_paths)
    log = lane_run / "emu.txt"
    command = [str(PCSX2), "-batch", "-nogui", "-datapath", str(data),
               "-logfile", str(log), "-elf", str(elf_copy)]
    env = {**os.environ, "APPIMAGE_EXTRACT_AND_RUN": "1", "QT_QPA_PLATFORM": "xcb"}
    start = time.monotonic()
    guest_terminal = None
    captures = []
    with (lane_run / "launcher.log").open("w") as launcher:
        process = subprocess.Popen(command, cwd=lane_run, env=env, stdout=launcher,
                                   stderr=subprocess.STDOUT, start_new_session=True)
        deadline = time.monotonic() + timeout
        pending_markers = list(capture_markers)
        while process.poll() is None and time.monotonic() < deadline:
            if capture_dir and pending_markers:
                log_text = log.read_text(errors="replace") if log.exists() else ""
                for marker in list(pending_markers):
                    if marker in log_text:
                        pending_markers.remove(marker)
                        Path(capture_dir).mkdir(parents=True, exist_ok=True)
                        tag = re.sub(r"[^A-Za-z0-9]+", "-", marker).strip("-")
                        info = capture_root(os.environ.get("DISPLAY", ":99"),
                                            Path(capture_dir) / f"capture-{len(captures) + 1:02d}-{tag}")
                        info["marker"] = marker
                        captures.append(info)
            guest_terminal = _run_terminal(which, log)
            if guest_terminal:
                # Let PCSX2 flush the CE teardown tail before stopping it.
                time.sleep(1.5)
                break
            time.sleep(0.2)
        if guest_terminal:
            exit_status = f"{guest_terminal}; {_stop_owned_process(process, grace=5.0)}"
        elif process.poll() is not None:
            exit_status = f"host-exited-{process.returncode}"
        else:
            exit_status = f"bounded timeout after {timeout}s; {_stop_owned_process(process, grace=20.0)}"
    elapsed = round(time.monotonic() - start, 1)
    text = log.read_text(errors="replace") if log.exists() else ""
    lines = halo_lines(text)
    (lane_run / "halo_ps2_local.txt").write_text("\n".join(lines) + "\n")
    lifecycle = which == "lifecycle"
    markers = check_markers(lines, lifecycle, production=which == "partition-selected")
    if which.startswith("workload"):
        markers = {name: any(line.startswith(prefix) for line in lines)
                   for name, prefix in WORKLOAD_MARKERS.items()}
    result = {"run": which, "elf": elf_info["path"], "elf_sha256": elf_info["sha256"],
            "exit": exit_status, "elapsed_seconds": elapsed, "log": str(log),
            "pcsx2_config": config_identity,
            "halo_lines_saved": str(lane_run / "halo_ps2_local.txt"), "halo_line_count": len(lines),
            "captures": captures,
            "markers": markers, "markers_all_present": all(markers.values()),
            "summary": summarize(lines)}
    if which == "partition-selected":
        result.update(production_tuple_qualification(lines, **(production_tuple or {})))
        result["guest_terminal"] = guest_terminal or "host-exit-or-timeout"
    else:
        complete = guest_terminal == "completion-marker"
        if which == "lifecycle":
            lifecycle = check_markers(lines, lifecycle=True)
            complete = complete and lifecycle.get("lifecycle-owner-released", False) and \
                lifecycle.get("lifecycle-complete", False)
        result.update({"guest_terminal": guest_terminal or "host-exit-or-timeout",
                       "guest_completed": complete,
                       "guest_error_lines": _post_entry_faults(lines),
                       "boot_diagnostics": _boot_diagnostics(lines)})
    return result


def write_manifest(path, manifest):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, indent=2) + "\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    parser.add_argument("--timeout", type=int, default=600, help="seconds per guest run")
    parser.add_argument("--only", choices=tuple(RUNS), help="run one guest only")
    parser.add_argument("--source-elf", type=Path,
                        help="stage this ELF for --only instead of the lane copy in build/m2-c2-r9-peaks/elf/")
    parser.add_argument("--output-dir", type=Path, default=OUT,
                        help="isolated evidence directory (defaults to build/m2-c2-r9-peaks)")
    parser.add_argument("--production-elf", type=Path,
                        help="run a partition-selected production ELF as the sole guest")
    parser.add_argument("--package-tree", type=Path,
                        help="selected packages tree exposed under host:/build/m2-c2-r3-selected-packages")
    parser.add_argument("--guest-package-root", default="build/m2-c2-r3-selected-packages",
                        help="relative host: path where this package tree is mounted")
    parser.add_argument("--stage-path", action="append", default=[],
                        help="repo-relative file to symlink into the guest host:/ root (repeatable)")
    parser.add_argument("--maps-dir", type=Path, default=PROBE / "maps",
                        help="directory exposed at host:/maps for the guest")
    parser.add_argument("--capture-dir", type=Path,
                        help="C3: save an `xwd -root` PNG of the guest display here when a --capture-marker appears in the log")
    parser.add_argument("--capture-marker", action="append", default=[],
                        help="log substring that triggers one capture (repeatable)")
    parser.add_argument("--production-row", default="sidewinder_marine_shotgun_4p4bot")
    parser.add_argument("--production-map", default="sidewinder")
    parser.add_argument("--production-release-map",
                        help="expected terminal map after an opt-in successor lifecycle guest")
    parser.add_argument("--production-profile-id", type=int, default=26)
    args = parser.parse_args()
    if args.source_elf and not args.only:
        parser.error("--source-elf requires --only")
    if args.production_elf and (args.only or args.source_elf):
        parser.error("--production-elf cannot be combined with --only or --source-elf")
    if args.production_elf and not args.package_tree:
        parser.error("--production-elf requires --package-tree so package/source inputs are pinned")
    if args.production_elf and not args.production_elf.is_file():
        parser.error("--production-elf path does not exist")
    out_dir = args.output_dir.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    selected = ["partition-selected"] if args.production_elf else ([args.only] if args.only else list(RUNS))
    display, xvfb = ensure_display()
    os.environ["DISPLAY"] = display
    manifest = {"lane": "guest", "date": "2026-10-24", "display": display,
                "pcsx2": str(PCSX2), "pcsx2_sha256": sha256(PCSX2),
                "guest_reserve_start": hex(GUEST_RESERVE_START), "timeout_seconds": args.timeout,
                "output_dir": str(out_dir),
                "no_run_errors": False, "elfs": {}, "runs": []}
    if args.production_elf:
        row = args.production_row
        package_rel = Path("pkg") / row / f"{row}.hcp"
        package = args.package_tree.resolve() / package_rel if args.package_tree else None
        package_manifest = (args.package_tree.resolve() / "pkg" / row / f"{row}.json"
                            if args.package_tree else None)
        manifest_data = (json.loads(package_manifest.read_text())
                         if package_manifest and package_manifest.is_file() else {})
        profile = manifest_data.get("profile", {})
        if args.production_elf and not profile:
            parser.error(f"profile manifest is missing: {package_manifest}")
        if profile and (profile.get("name") != row or profile.get("map") != args.production_map or
                        int(profile.get("id", -1)) != args.production_profile_id):
            parser.error("package manifest does not match the selected row/map/profile id")
        if not package or not package.is_file():
            parser.error(f"profile package is missing: {package}")
        if not package_manifest or not package_manifest.is_file():
            parser.error(f"profile manifest is missing: {package_manifest}")
        source_files = {name: ROOT / entry["path"]
                        for name, entry in manifest_data.get("source_maps", {}).items()}
        for name, path in source_files.items():
            if not path.is_file() or sha256(path) != manifest_data["source_maps"][name]["sha256"]:
                parser.error(f"source map is missing or differs from package pin: {path}")
        if manifest_data.get("package_sha256") != sha256(package):
            parser.error(f"package differs from its manifest pin: {package}")
        if not source_files:
            parser.error("profile manifest has no source-map pins")
        manifest["runtime_profile"] = {
            "row": row, "profile_name": profile.get("name"),
            "partition_profile": row, "map": args.production_map,
            "profile_id": args.production_profile_id,
            "scenario_mode": "production-ce-map-load-headless",
            "package_path": str(package) if package else None,
            "package_bytes": package.stat().st_size if package and package.is_file() else None,
            "package_sha256": sha256(package) if package and package.is_file() else None,
            "package_manifest_path": str(package_manifest) if package_manifest else None,
            "package_manifest_sha256": sha256(package_manifest)
                                        if package_manifest and package_manifest.is_file() else None,
            "source_maps": {name: {"path": str(path), "bytes": path.stat().st_size,
                                   "sha256": sha256(path)} for name, path in source_files.items()}
                            if source_files and all(path.is_file() for path in source_files.values()) else None,
        }
        manifest["profile_name"] = profile.get("name")
        manifest["partition_profile"] = row
        manifest["profile_package_sha256"] = manifest["runtime_profile"]["package_sha256"]
        manifest["scenario_mode"] = "production-ce-map-load-headless"
    manifest_path = out_dir / "manifest.json"
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
                if args.production_elf:
                    source = args.production_elf.resolve()
                    if not source.is_file():
                        raise FileNotFoundError(source)
                    readelf = subprocess.run([str(READELF), "-lW", str(source)], capture_output=True,
                                             text=True, check=True)
                    segments = parse_load_segments(readelf.stdout)
                    info = {"path": str(source), "sha256": sha256(source), "sha_checked": False,
                            "load_segments": segments, "highest_guest_byte": highest_guest_byte(segments)}
                else:
                    info = stage(which, args.source_elf.resolve() if args.source_elf else None,
                                 out_dir)
                manifest["elfs"][which] = {key: info[key] for key in
                                           ("path", "sha256", "sha_checked", "highest_guest_byte")}
                manifest["elfs"][which]["highest_below_guest_reserve"] = info["highest_guest_byte"] < GUEST_RESERVE_START
                manifest["elfs"][which]["load_segments"] = info["load_segments"]
                manifest["runs"].append(run_guest(which, info, args.timeout, out_dir,
                                                   args.package_tree if args.production_elf else None,
                                                   args.maps_dir,
                                                   ({"row": row, "map_name": args.production_map,
                                                     "profile_id": args.production_profile_id,
                                                     "package_bytes": manifest["runtime_profile"]["package_bytes"],
                                                     "released_map": args.production_release_map}
                                                    if args.production_elf else None),
                                                   args.guest_package_root, args.stage_path,
                                                   args.capture_dir, args.capture_marker))
            except Exception as error:  # record the failure and keep the partial manifest
                manifest["runs"].append({"run": which, "error": f"{type(error).__name__}: {error}"})
            write_manifest(manifest_path, manifest)
    finally:
        manifest["no_run_errors"] = all("error" not in run for run in manifest["runs"])
        write_manifest(manifest_path, manifest)
        if xvfb is not None:
            xvfb.terminate()
            try:
                xvfb.wait(timeout=3)
            except subprocess.TimeoutExpired:
                xvfb.kill()
                xvfb.wait()
    print(f"manifest: {manifest_path}")
    for run in manifest["runs"]:
        if "error" in run:
            print(run["run"], "ERROR", run["error"])
        else:
            print(run["run"], run["exit"], "lines", run["halo_line_count"],
                  "markers_all_present", run["markers_all_present"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
