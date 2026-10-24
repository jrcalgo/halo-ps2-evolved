#!/usr/bin/env python3
"""C2 profile boot matrix: link, boot and qualify one production partition row at a time.

For each row this tool
  1. generates the row's image header (tools/c2_profile_image_header.py) to fail early,
  2. links the HCU headless runtime guest for that row into build/m2-c2-matrix/<row>/link
     with tools/hcu_parent_link_probe.py --output-dir (links are serialized on the shared
     parent-link lock because the HCU closure directory is common to every link),
  3. runs the ELF in PCSX2 through tools/c2_guest_run.py (package tree mounted at the path
     the header pins, source maps staged under the run's host:/ root),
  4. parses the guest log for the REQUIRED markers and writes
     build/m2-c2-matrix/<row>/result.json with pass/fail, reasons and per-owner peaks.

Usage:
    python3 -I tools/c2_profile_boot_matrix.py [--rows a,b,c] [--jobs-link 1] [--skip-existing]
"""
from __future__ import annotations

import argparse
import fcntl
import json
import os
import re
import signal
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MATRIX = ROOT / "build/m2-c2-matrix"
PROFILE_SOURCE = ROOT / "src/stream/hcu_memory_profile.c"
DEFAULT_PACKAGE_ROOT = ROOT / "build/m2-c2-r3-selected-packages/pkg"
LINK_LOCK = ROOT / "build/.hcu-parent-link-probe.lock"

# Rows whose selected package is not in the default corpus tree.
EXTRA_PACKAGE_ROOTS = {
    "bots_sidewinder": ROOT / "build/m2-c2-resume-runtime-guest/bots-package-tree-v2/pkg",
}

RESERVE = 0x1A40000          # budget v3 reserve start (kernel-reservation reserve=)
LINK_TIMEOUT = 3600
GUEST_TIMEOUT = 600          # guest seconds
GUEST_PROCESS_TIMEOUT = 700  # host seconds for the whole c2_guest_run process
EXPECTED_CANARIES = 10

ROW_PATTERN = re.compile(r'^\s*\{\s*"([a-z0-9_]+)"\s*,\s*\{\s*HCU_MEMORY_PROFILE_VERSION_1', re.M)
FIELD_PATTERN = re.compile(r"(?:^|\s)([A-Za-z][A-Za-z0-9_-]*)=([^\s]+)")
PREFIX = "HALO_PS2_LOCAL "

# Owner/arena counters that must be zero on every line that carries them.
FAILURE_KEYS = ("failures", "alloc_failures", "backing_failures", "lease_failures",
                "mount_rejections", "invalid_releases")


def profile_rows(source: Path = PROFILE_SOURCE) -> list[str]:
    """Every row name in the profile table, in table order."""
    return ROW_PATTERN.findall(source.read_text(encoding="utf-8"))


def package_root_for(row: str, default_root: Path = DEFAULT_PACKAGE_ROOT) -> Path | None:
    """The pkg/ directory that holds this row's selected package, or None."""
    for root in (default_root, EXTRA_PACKAGE_ROOTS.get(row)):
        if root and (root / row / f"{row}.hcp").is_file() and (root / row / f"{row}.json").is_file():
            return root
    return None


def default_rows(source: Path = PROFILE_SOURCE, default_root: Path = DEFAULT_PACKAGE_ROOT) -> list[str]:
    return [row for row in profile_rows(source) if package_root_for(row, default_root)]


def fields_of(line: str) -> dict[str, str]:
    return dict(FIELD_PATTERN.findall(line))


def _int(value: str | None, base: int = 10) -> int | None:
    try:
        return int(value, base) if value is not None else None
    except ValueError:
        return None


def strip_log_prefix(raw: str) -> str:
    return re.sub(r"^\[\s*[0-9.]+\]\s?", "", raw, count=1).strip()


def first_line(lines: list[str], marker: str) -> str | None:
    return next((line for line in lines if line.startswith(PREFIX + marker)), None)


def parse_guest_log(lines: list[str], row: str, map_name: str, reserve: int = RESERVE) -> dict:
    """Check the REQUIRED markers of one production guest log.

    lines are HALO_PS2_LOCAL/fault lines with the log timestamp already removed.
    Returns {"checks": {name: bool}, "reasons": [...], "values": {...}, "peaks": {...}}.
    """
    checks: dict[str, bool] = {}
    reasons: list[str] = []
    values: dict[str, object] = {}

    def require(name: str, ok: bool, why: str) -> None:
        checks[name] = bool(ok)
        if not ok:
            reasons.append(why)

    reservation = first_line(lines, "kernel-reservation ")
    reserve_seen = _int(fields_of(reservation).get("reserve"), 16) if reservation else None
    values["reserve"] = reserve_seen
    require("kernel_reservation", reserve_seen == reserve,
            f"kernel-reservation reserve={hex(reserve_seen) if reserve_seen is not None else 'missing'}, expected {hex(reserve)}")

    selected = first_line(lines, "partition-selected ")
    sel = fields_of(selected) if selected else {}
    require("partition_selected", sel.get("name") == row and sel.get("qualified") == "1",
            f"partition-selected missing or not qualified=1 for {row}: {selected}")

    physical = first_line(lines, "memory-physical ")
    boot_end = _int(fields_of(physical).get("boot_end"), 16) if physical else None
    values["boot_end"] = boot_end
    require("boot_end_below_reserve", boot_end is not None and boot_end < reserve,
            f"memory-physical boot_end={hex(boot_end) if boot_end is not None else 'missing'} is not below {hex(reserve)}")

    ready = first_line(lines, "memory-ready ")
    canaries = _int(fields_of(ready).get("canaries")) if ready else None
    require("memory_ready", canaries == EXPECTED_CANARIES,
            f"memory-ready canaries={canaries}, expected {EXPECTED_CANARIES}")

    runtime = first_line(lines, "profile-runtime row=")
    rt = fields_of(runtime) if runtime else {}
    values["package_bytes"] = _int(rt.get("package-bytes"))
    values["profile_id"] = _int(rt.get("profile"))
    require("profile_runtime", rt.get("row") == row and rt.get("map") == map_name,
            f"profile-runtime row/map do not match {row}/{map_name}: {runtime}")

    preflight = first_line(lines, "profile-preflight ")
    pf = fields_of(preflight) if preflight else {}
    require("profile_preflight", pf.get("result") == "1" and pf.get("map") == map_name,
            f"profile-preflight result=1 map={map_name} missing: {preflight}")

    mount = next((line for line in lines if line.startswith(PREFIX + "map-mount result=1 ")), None)
    mt = fields_of(mount) if mount else {}
    require("map_mount", mt.get("active") == "1" and mt.get("map") == map_name
            and mt.get("source") == "profile-runtime",
            f"map-mount result=1 active=1 map={map_name} source=profile-runtime missing: {mount}")

    loaded = first_line(lines, "production-ce-map-loaded ")
    ld = fields_of(loaded) if loaded else {}
    tag_bytes, bsp_bytes, tag_count = (_int(ld.get(k)) for k in ("tag-bytes", "bsp-bytes", "tag-count"))
    values.update({"tag_bytes": tag_bytes, "bsp_bytes": bsp_bytes, "tag_count": tag_count})
    require("map_loaded", ld.get("result") == "1" and ld.get("map") == map_name
            and ld.get("scenario") == "1" and ld.get("tag-table") == "1"
            and (tag_count or 0) > 0 and (tag_bytes or 0) > 0 and (bsp_bytes or 0) > 0,
            f"production-ce-map-loaded result=1 missing or incomplete: {loaded}")

    released = first_line(lines, "production-ce-map-released ")
    rl = fields_of(released) if released else {}
    require("map_released", rl.get("result") == "1" and rl.get("map") == map_name
            and rl.get("mounted") == "0" and rl.get("tag-bytes") == "0" and rl.get("bsp-bytes") == "0",
            f"production-ce-map-released result=1 missing or incomplete: {released}")

    order = [next((i for i, line in enumerate(lines) if line.startswith(PREFIX + marker)), None)
             for marker in ("partition-selected ", "profile-runtime row=", "profile-preflight ",
                            "map-mount result=1 ", "production-ce-map-loaded ", "production-ce-map-released ")]
    require("marker_order", all(p is not None for p in order) and order == sorted(order),
            f"markers are missing or out of order: {order}")

    # Failure counters on every owner-telemetry, arena and cache-owner line.
    nonzero: list[str] = []
    counted = 0
    for line in lines:
        if not line.startswith((PREFIX + "owner-telemetry ", PREFIX + "arena ", PREFIX + "cache-owner ")):
            continue
        fields = fields_of(line)
        for key in FAILURE_KEYS:
            if key in fields:
                counted += 1
                if fields[key] != "0":
                    nonzero.append(line)
                    break
    values["failure_counters_checked"] = counted
    why = ("no failure counters were found" if counted == 0 else
           f"{len(nonzero)} owner/arena line(s) report non-zero failures; first: {nonzero[0] if nonzero else ''}")
    require("failures_zero", counted > 0 and not nonzero, why)

    entry = next((i for i, line in enumerate(lines) if line.startswith(PREFIX + "machine entry")), None)
    faults = [line for line in (lines[entry:] if entry is not None else [])
              if "HALO_PS2_FAIL" in line or "[err]" in line or "Address Error" in line
              or "HALO_PS2_LOCAL halt" in line or "EXCEPTION halt" in line or "branch delay!!" in line]
    values["fault_lines"] = faults[:5]
    require("no_guest_faults", entry is not None and not faults,
            "no machine entry line" if entry is None else f"guest fault: {faults[0] if faults else ''}")

    failing = [name for name, ok in checks.items() if not ok]
    return {"checks": checks, "failing_checks": failing, "reasons": reasons,
            "values": values, "peaks": owner_peaks(lines)}


def owner_peaks(lines: list[str]) -> dict:
    """Largest observed high/peak per owner across every telemetry phase."""
    owners: dict[str, int] = {}
    caches: dict[str, int] = {}
    arenas: dict[str, int] = {}
    backing = 0
    for line in lines:
        fields = fields_of(line)
        if line.startswith(PREFIX + "owner-telemetry "):
            if "name" in fields:
                owners[fields["name"]] = max(owners.get(fields["name"], 0), _int(fields.get("high")) or 0)
            else:
                backing = max(backing, _int(fields.get("backing_high")) or 0)
        elif line.startswith(PREFIX + "cache-owner "):
            caches[fields.get("name", "?")] = max(caches.get(fields.get("name", "?"), 0),
                                                  _int(fields.get("peak")) or 0)
        elif line.startswith(PREFIX + "arena "):
            arenas[fields.get("name", "?")] = max(arenas.get(fields.get("name", "?"), 0),
                                                  _int(fields.get("high")) or 0)
    return {"owners": owners, "cache_owners": caches, "arenas": arenas, "backing_high": backing,
            "game_state_peak": owners.get("game_state", 0),
            "tag_peak": caches.get("tags", 0), "bsp_peak": caches.get("bsp", 0)}


CE_FAILURE_PATTERN = re.compile(r"game_load\(\) failed|game_initialize.*failed|scenario.*(?:failed|not found)|"
                                r"cannot open|out of memory", re.I)


def ce_failure_lines(emulator_log: Path, limit: int = 5) -> list[str]:
    """CE-side failure text that never carries a HALO_PS2_LOCAL prefix."""
    if not emulator_log.is_file():
        return []
    found = [strip_log_prefix(raw) for raw in emulator_log.read_text(errors="replace").splitlines()
             if CE_FAILURE_PATTERN.search(raw)]
    return found[:limit]


def read_guest_lines(path: Path) -> list[str]:
    if not path.is_file():
        return []
    return [strip_log_prefix(raw) for raw in path.read_text(errors="replace").splitlines() if raw.strip()]


def stage_plan(row: str, package_root: Path) -> dict:
    """Where the guest finds this row's inputs under its host:/ root."""
    manifest = json.loads((package_root / row / f"{row}.json").read_text(encoding="utf-8"))
    profile = manifest["profile"]
    tree = package_root.parent
    guest_root = tree.resolve().relative_to(ROOT)
    outside = sorted(entry["path"] for entry in manifest["source_maps"].values()
                     if not entry["path"].startswith("build/retail-maps/"))
    return {"map": profile["map"], "profile_id": int(profile["id"]),
            "scenario": (profile.get("scenario") or {}).get("path"),
            "package_tree": tree, "guest_package_root": guest_root.as_posix(),
            "stage_paths": outside}


def run_group(command: list[str], *, log: Path, timeout: int, env: dict | None = None) -> tuple[int, bool]:
    """Run a command in its own session; kill only that session on timeout. -> (rc, timed_out)."""
    log.parent.mkdir(parents=True, exist_ok=True)
    with log.open("w") as handle:
        process = subprocess.Popen(command, cwd=ROOT, env=env, stdout=handle, stderr=subprocess.STDOUT,
                                   start_new_session=True)
        try:
            return process.wait(timeout=timeout), False
        except (subprocess.TimeoutExpired, KeyboardInterrupt) as stop:
            for sig, grace in ((signal.SIGINT, 10), (signal.SIGKILL, 10)):
                try:
                    os.killpg(process.pid, sig)
                    process.wait(timeout=grace)
                    break
                except (ProcessLookupError, subprocess.TimeoutExpired):
                    continue
            if isinstance(stop, KeyboardInterrupt):
                raise
            return -9, True


def link_row(row: str, package_root: Path, out: Path) -> tuple[Path | None, str]:
    """Link the row's runtime-guest ELF under out/link, holding the shared link lock."""
    link_dir = out / "link"
    LINK_LOCK.parent.mkdir(parents=True, exist_ok=True)
    command = [sys.executable, str(ROOT / "tools/hcu_parent_link_probe.py"),
               "--asset-profile", "host", "--partition-profile", row,
               "--profile-package-root", str(package_root),
               "--headless-runtime-guest", "--output-dir", str(link_dir)]
    with LINK_LOCK.open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        rc, timed_out = run_group(command, log=out / "link.log", timeout=LINK_TIMEOUT)
    elf = link_dir / f"hcu-gameplay-machine-partition-{row}-headless-runtime-guest.elf"
    if timed_out:
        return None, f"link timed out after {LINK_TIMEOUT}s"
    if rc or not elf.is_file():
        return None, f"link failed (exit {rc}); see {out / 'link.log'}"
    return elf, ""


def guest_row(row: str, elf: Path, plan: dict, out: Path) -> tuple[bool, str]:
    command = [sys.executable, "-I", str(ROOT / "tools/c2_guest_run.py"),
               "--timeout", str(GUEST_TIMEOUT), "--output-dir", str(out / "guest"),
               "--production-elf", str(elf), "--package-tree", str(plan["package_tree"]),
               "--guest-package-root", plan["guest_package_root"],
               "--production-row", row, "--production-map", plan["map"],
               "--production-profile-id", str(plan["profile_id"])]
    for path in plan["stage_paths"]:
        command += ["--stage-path", path]
    rc, timed_out = run_group(command, log=out / "guest.log", timeout=GUEST_PROCESS_TIMEOUT)
    if timed_out:
        return False, f"guest runner exceeded {GUEST_PROCESS_TIMEOUT}s"
    if rc:
        return False, f"guest runner exited {rc}; see {out / 'guest.log'}"
    return True, ""


def run_row(row: str, package_root_override: Path | None = None) -> dict:
    out = MATRIX / row
    out.mkdir(parents=True, exist_ok=True)
    started = time.time()
    result: dict = {"row": row, "pass": False, "reasons": [], "started_unix": int(started)}
    (out / "result.json").write_text(json.dumps({**result, "state": "running"}, indent=2) + "\n")
    try:
        package_root = package_root_override or package_root_for(row)
        if package_root is None:
            raise RuntimeError(f"no selected package for {row} under {DEFAULT_PACKAGE_ROOT}")
        plan = stage_plan(row, package_root)
        result.update({"map": plan["map"], "scenario": plan["scenario"], "package_root": str(package_root)})
        header = subprocess.run(
            [sys.executable, "-I", str(ROOT / "tools/c2_profile_image_header.py"), "--row", row,
             "--package-root", str(package_root), "--output", str(out / f"{row}.h")],
            cwd=ROOT, capture_output=True, text=True)
        if header.returncode:
            raise RuntimeError(f"row header failed: {header.stderr.strip()}")
        elf, why = link_row(row, package_root, out)
        if elf is None:
            raise RuntimeError(why)
        result["elf"] = str(elf.relative_to(ROOT))
        ok, why = guest_row(row, elf, plan, out)
        log_path = out / "guest/runs/partition-selected/halo_ps2_local.txt"
        lines = read_guest_lines(log_path)
        result["guest_log"] = str(log_path.relative_to(ROOT))
        result["guest_line_count"] = len(lines)
        parsed = parse_guest_log(lines, row, plan["map"])
        result.update(parsed)
        result["ce_failure_lines"] = ce_failure_lines(out / "guest/runs/partition-selected/emu.txt")
        if parsed["failing_checks"] and result["ce_failure_lines"]:
            result["reasons"].append("CE reported: " + " | ".join(result["ce_failure_lines"][:2]))
        if not ok:
            result["reasons"].insert(0, why)
        result["pass"] = bool(ok and not parsed["failing_checks"])
    except Exception as error:  # record and keep the matrix moving
        result["reasons"].append(f"{type(error).__name__}: {error}")
        result["pass"] = False
    result["elapsed_seconds"] = round(time.time() - started, 1)
    (out / "result.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    return result


def previously_passed(row: str) -> bool:
    path = MATRIX / row / "result.json"
    try:
        return json.loads(path.read_text()).get("pass") is True
    except (OSError, ValueError):
        return False


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--rows", help="comma-separated row names (default: every row with a selected package)")
    parser.add_argument("--jobs-link", type=int, default=1,
                        help=("link concurrency; links always take the shared parent-link lock because every link "
                              "rewrites the common HCU closure directory, so they stay serialized"))
    parser.add_argument("--skip-existing", action="store_true", help="skip rows whose result.json already passed")
    args = parser.parse_args(argv)
    rows = [r for r in (args.rows.split(",") if args.rows else default_rows()) if r]
    unknown = [r for r in rows if r not in profile_rows()]
    if unknown:
        parser.error(f"rows not in {PROFILE_SOURCE.name}: {', '.join(unknown)}")
    if args.jobs_link < 1:
        parser.error("--jobs-link must be at least 1")
    summary = []
    for row in rows:
        if args.skip_existing and previously_passed(row):
            print(f"{row}: skipped (previous pass)")
            continue
        result = run_row(row)
        summary.append(result)
        print(f"{row}: {'PASS' if result['pass'] else 'FAIL'} {'; '.join(result['reasons'][:2])}", flush=True)
    MATRIX.mkdir(parents=True, exist_ok=True)
    (MATRIX / "summary.json").write_text(json.dumps(
        {"rows": [{"row": r["row"], "pass": r["pass"], "reasons": r["reasons"][:3]} for r in summary]},
        indent=2) + "\n")
    return 0 if all(r["pass"] for r in summary) else 1


if __name__ == "__main__":
    sys.exit(main())
