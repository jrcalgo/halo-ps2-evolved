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
    python3 -I tools/c2_profile_boot_matrix.py --rows ROW --successor SUCC_ROW [--successor-fault none|preflight|load]

--successor runs the opt-in C2.8 guest successor sequence on one row (see run_successor):
none = foreign-profile replacement, preflight = a failed successor preflight must leave the
old map mounted and usable, load = a late successor failure leaves the empty state and a
retry then loads. Results go to build/m2-c2-foreign/<row>/<successor>-<case>/ and never to
build/m2-c2-matrix/summary.json.
"""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import shutil
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
REUSE_ROOT = ROOT / "build/m2-c2-gaps-reuse"  # output root for --cycles/--ticks runs
C3_ROOT = ROOT / "build/c3/integrate"        # output root for --c3 rows (summary.json is never written)
RESULT_ROOT = MATRIX                           # switched to C3_ROOT by --c3
WORKLOAD_PLAYERS = {"none": 0, "4p4bot": 4}  # local players per --c3-workload
OUTPUT_ROOT: Path | None = None                # --output-root DIR: every row writes to DIR/<row>/ instead
TEXFENCE_CAP_PAGES = 0                         # --texfence-cap-pages N: debug cap on texture cache pages (C3.7), 0 = off
RENDER_ROOT = ROOT / "build/c3/render-loop"   # output root for --c3 --render-views runs (v<N>/<row>)
RENDER_PACKAGE_TREE = ROOT / "build/c3/render-tree"  # <tree>/pkg -> build/c3/render-packages (BSPS/TEXS/LMn chunks)
FOREIGN_ROOT = ROOT / "build/m2-c2-foreign"   # output root for --successor runs
# --successor-fault value -> (guest HALO_PS2_C2_SUCCESSOR_MODE, result directory label)
SUCCESSOR_CASES = {"none": (1, "replace"), "preflight": (2, "failed-preflight"),
                   "load": (3, "fail-then-retry")}
SUCCESSOR_TICKS = 30
SUCCESSOR_GUEST_TIMEOUT = 1500         # guest seconds: two package hashes and two loads
SUCCESSOR_PROCESS_TIMEOUT = 1600

# Rows whose selected package is not in the default corpus tree.
EXTRA_PACKAGE_ROOTS = {
    "bots_sidewinder": ROOT / "build/m2-c2-residual-packages/bots-tree/pkg",
    # The UI package (scenario levels/ui/ui). Its manifest is the hcp2-primary ui manifest with
    # memory.package_file_bytes set to the HCP2 file size, as tools/repack_hcu_profiles_hcp2.py does.
    "ui": ROOT / "build/m2-c2-residual-packages/ui-tree/pkg",
}

RESERVE = 0x1AE0000          # budget v5 reserve start (kernel-reservation reserve=)
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


def parse_guest_log(lines: list[str], row: str, map_name: str, reserve: int = RESERVE,
                    released_map: str | None = None,
                    expected_fault_kind: str | None = None) -> dict:
    """Check the REQUIRED markers of one production guest log.

    lines are HALO_PS2_LOCAL/fault lines with the log timestamp already removed.
    released_map names the map the terminal production-ce-map-released marker reports
    (default map_name); a successor run that ends on the successor's release passes it.
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
    require("map_released", rl.get("result") == "1" and rl.get("map") == (released_map or map_name)
            and rl.get("mounted") == "0" and rl.get("tag-bytes") == "0" and rl.get("bsp-bytes") == "0",
            f"production-ce-map-released result=1 missing or incomplete: {released}")

    order = [next((i for i, line in enumerate(lines) if line.startswith(PREFIX + marker)), None)
             for marker in ("partition-selected ", "profile-runtime row=", "profile-preflight ",
                            "map-mount result=1 ", "production-ce-map-loaded ", "production-ce-map-released ")]
    require("marker_order", all(p is not None for p in order) and order == sorted(order),
            f"markers are missing or out of order: {order}")

    # Failure counters on every owner-telemetry, arena and cache-owner line.
    # The C2.8 late-failure case permits only the one measured failure that
    # follows its named, partial HCP CTAG stream fault.
    expected_fault = next((i for i, line in enumerate(lines)
                           if expected_fault_kind and
                           line.startswith(PREFIX + f"successor-fault injected kind={expected_fault_kind} ")), None)
    nonzero: list[str] = []
    counted = 0
    expected_counter_lines: list[str] = []
    for index, line in enumerate(lines):
        if not line.startswith((PREFIX + "owner-telemetry ", PREFIX + "arena ", PREFIX + "cache-owner ")):
            continue
        fields = fields_of(line)
        for key in FAILURE_KEYS:
            if key in fields:
                counted += 1
                if fields[key] != "0":
                    permitted = False
                    if expected_fault is not None and index > expected_fault:
                        if key == "backing_failures" and fields.get("partition") == row:
                            permitted = fields[key] == "1"
                        elif key == "failures" and fields.get("name") == "tags":
                            permitted = fields[key] == "1"
                    if permitted:
                        expected_counter_lines.append(line)
                    else:
                        nonzero.append(line)
                        break
    values["failure_counters_checked"] = counted
    values["expected_failure_counter_lines"] = expected_counter_lines
    why = ("no failure counters were found" if counted == 0 else
           f"{len(nonzero)} owner/arena line(s) report non-zero failures; first: {nonzero[0] if nonzero else ''}")
    if expected_fault_kind:
        require("expected_fault_counter_scope", expected_fault is not None and
                bool(expected_counter_lines) and not nonzero,
                f"late-failure counters are outside the single expected CTAG fault: {nonzero[:1]}")
    else:
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


def _phase_rows(lines: list[str], start: int, phase: str) -> dict:
    """Owner rows, header and cache-owner rows of one phase that follow a boundary line."""
    out: dict = {"owners": {}, "backing": {}, "cache": {}}
    for line in lines[start + 1:]:
        fields = fields_of(line)
        if fields.get("phase") != phase:
            break
        if line.startswith(PREFIX + "owner-telemetry "):
            if "name" in fields:
                out["owners"][fields["name"]] = {k: _int(fields.get(k)) for k in ("used", "high", "failures", "resets")}
            else:
                out["backing"] = {k: _int(fields.get(k)) for k in ("backing_used", "backing_high", "backing_resets")}
        elif line.startswith(PREFIX + "cache-owner "):
            out["cache"][fields.get("name", "?")] = {
                k: _int(fields.get(k)) for k in ("current", "peak", "publications", "unmounts", "resets")}
    return out


def parse_cycles(lines: list[str], map_name: str, cycles: int, ticks: int = 0) -> dict:
    """Per-cycle load/release checks plus the storage-reuse comparison across cycles 2..N."""
    checks: dict[str, bool] = {}
    reasons: list[str] = []
    per_cycle: list[dict] = []

    def require(name: str, ok: bool, why: str) -> None:
        checks[name] = bool(ok)
        if not ok:
            reasons.append(why)

    def marker(name: str, cycle: int) -> str | None:
        return next((line for line in lines if line.startswith(PREFIX + name + " ")
                     and fields_of(line).get("cycle") == str(cycle)), None)

    def boundary(phase: str, cycle: int) -> int | None:
        return next((i for i, line in enumerate(lines)
                     if line.startswith(PREFIX + "m2-cycle-boundary ")
                     and fields_of(line).get("phase") == phase
                     and fields_of(line).get("cycle") == str(cycle)), None)

    for cycle in range(1, cycles + 1):
        # Cycles before the last print production-ce-map-released-cycle so the host runner keeps going.
        loaded = marker("production-ce-map-loaded", cycle)
        released = marker("production-ce-map-released", cycle) or marker("production-ce-map-released-cycle", cycle)
        ld, rl = fields_of(loaded or ""), fields_of(released or "")
        ok_loaded = (ld.get("result") == "1" and ld.get("map") == map_name and ld.get("scenario") == "1"
                     and ld.get("tag-table") == "1" and (_int(ld.get("tag-count")) or 0) > 0
                     and (_int(ld.get("tag-bytes")) or 0) > 0 and (_int(ld.get("bsp-bytes")) or 0) > 0
                     and ld.get("cycles") == str(cycles))
        ok_released = (rl.get("result") == "1" and rl.get("map") == map_name and rl.get("mounted") == "0"
                       and rl.get("tag-bytes") == "0" and rl.get("bsp-bytes") == "0"
                       and rl.get("cycles") == str(cycles))
        ok_ticks = True
        tick_line = marker("production-ce-ticks", cycle)
        allocation_line = marker("production-ce-tick-allocations", cycle)
        allocation_fields = fields_of(allocation_line or "")
        allocation_trace = None
        if ticks:
            tk = fields_of(tick_line or "")
            ok_ticks = tk.get("result") == "1" and tk.get("ticks") == str(ticks)
            def op_counts(name):
                raw = allocation_fields.get(name, "")
                try:
                    values = tuple(int(value) for value in raw.split("/"))
                except ValueError:
                    return None
                return values if len(values) == 3 and all(value >= 0 for value in values) else None

            op_names = ("malloc", "calloc", "realloc", "free")
            parsed_ops = {name: op_counts(name) for name in op_names}
            scalar_names = ("requested", "current-start", "current-end", "peak", "sdk-malloc",
                            "sdk-realloc", "sdk-free", "refused-unbound")
            scalars = {name: _int(allocation_fields.get(name)) for name in scalar_names}
            trace_valid = (allocation_fields.get("coverage") == "wrapped-compat-malloc"
                           and allocation_fields.get("map") == map_name
                           and allocation_fields.get("cycle") == str(cycle)
                           and allocation_fields.get("ticks") == str(ticks)
                           and all(value is not None for value in parsed_ops.values())
                           and all(value is not None for value in scalars.values()))
            if trace_valid:
                trace_valid = all(a == s + f for a, s, f in parsed_ops.values())
                trace_valid &= scalars["peak"] >= max(scalars["current-start"], scalars["current-end"])
                trace_valid &= all(parsed_ops[name][2] == 0 for name in op_names)
                trace_valid &= all(scalars[name] == 0 for name in
                                   ("sdk-malloc", "sdk-realloc", "sdk-free", "refused-unbound"))
            if trace_valid:
                allocation_trace = {
                    **{name: {"attempts": values[0], "successes": values[1], "failures": values[2]}
                       for name, values in parsed_ops.items()},
                    **scalars,
                    "coverage": allocation_fields["coverage"],
                }
        bl, br = boundary("map-loaded", cycle), boundary("map-released", cycle)
        released_rows = _phase_rows(lines, br, "map-released") if br is not None else {}
        loaded_rows = _phase_rows(lines, bl, "map-loaded") if bl is not None else {}
        row = {"cycle": cycle, "loaded": ok_loaded, "released": ok_released, "ticks_ok": ok_ticks,
               "tick_allocations": allocation_trace,
               "tag_bytes": _int(ld.get("tag-bytes")), "bsp_bytes": _int(ld.get("bsp-bytes")),
               "tick_line": tick_line, "boundary_loaded": bl is not None, "boundary_released": br is not None,
               "at_load": loaded_rows, "at_release": released_rows}
        per_cycle.append(row)
        require(f"cycle_{cycle}_loaded", ok_loaded, f"cycle {cycle}: production-ce-map-loaded incomplete: {loaded}")
        require(f"cycle_{cycle}_released", ok_released, f"cycle {cycle}: production-ce-map-released incomplete: {released}")
        require(f"cycle_{cycle}_boundary", bl is not None and br is not None and bool(released_rows.get("owners")),
                f"cycle {cycle}: m2-cycle-boundary map-loaded/map-released telemetry missing")
        if ticks:
            require(f"cycle_{cycle}_ticks", ok_ticks, f"cycle {cycle}: production-ce-ticks result=1 ticks={ticks} missing: {tick_line}")
            require(f"cycle_{cycle}_tick_allocations", allocation_trace is not None,
                    f"cycle {cycle}: post-load allocation trace is missing, malformed, failed, or used SDK fallback: {allocation_line}")

    # resets increment per cycle on the map owners
    for cycle in range(2, cycles + 1):
        cur, prev = per_cycle[cycle - 1]["at_release"], per_cycle[cycle - 2]["at_release"]
        for kind, name in (("owners", "game_state"), ("owners", "tags"), ("owners", "bsp"),
                           ("cache", "tags"), ("cache", "bsp")):
            a = (cur.get(kind, {}).get(name) or {}).get("resets")
            b = (prev.get(kind, {}).get(name) or {}).get("resets")
            require(f"resets_increment_{cycle}_{kind}_{name}", a is not None and b is not None and a > b,
                    f"cycle {cycle}: {kind} {name} resets {b} -> {a} did not increase")

    # storage reuse: cycles 2..N identical (peak and used), cycle 1 reported
    def signature(cycle_row: dict) -> dict:
        rel = cycle_row["at_release"]
        sig = {f"owner:{n}:{k}": v[k] for n, v in sorted(rel.get("owners", {}).items()) for k in ("used", "high", "failures")}
        sig.update({f"cache:{n}:{k}": v[k] for n, v in sorted(rel.get("cache", {}).items()) for k in ("current", "peak")})
        sig.update({f"backing:{k}": v for k, v in rel.get("backing", {}).items() if k != "backing_resets"})
        return sig
    signatures = [signature(r) for r in per_cycle]
    drift: list[str] = []
    if cycles >= 3:
        for cycle in range(3, cycles + 1):
            for key, value in signatures[1].items():
                if signatures[cycle - 1].get(key) != value:
                    drift.append(f"{key}: cycle2={value} cycle{cycle}={signatures[cycle - 1].get(key)}")
    require("storage_reused_cycles_2_to_n", cycles >= 2 and bool(signatures[1]) and not drift,
            "storage grew or drifted across cycles 2..N: " + "; ".join(drift[:5]) if drift else
            "need --cycles >= 2 with release telemetry for every cycle")
    cycle1_diff = ([k for k, v in signatures[0].items() if signatures[1].get(k) != v]
                   if cycles >= 2 and signatures[0] and signatures[1] else [])
    tick_allocation_drift = []
    if ticks:
        def tick_signature(row):
            trace = row.get("tick_allocations") or {}
            return {key: value for key, value in trace.items() if key not in ("cycle", "map", "ticks")}
        tick_signatures = [tick_signature(row) for row in per_cycle]
        if cycles >= 3 and tick_signatures[1]:
            for cycle in range(3, cycles + 1):
                for key, value in tick_signatures[1].items():
                    if tick_signatures[cycle - 1].get(key) != value:
                        tick_allocation_drift.append(
                            f"{key}: cycle2={value} cycle{cycle}={tick_signatures[cycle - 1].get(key)}")
        require("postload_allocator_reused_cycles_2_to_n",
                cycles >= 2 and bool(tick_signatures[1]) and not tick_allocation_drift,
                "post-load allocation behavior drifted across cycles 2..N: " +
                "; ".join(tick_allocation_drift[:5]) if tick_allocation_drift else
                "need --cycles >= 2 and valid post-load allocator trace for each cycle")
    return {"checks": checks, "failing_checks": [n for n, ok in checks.items() if not ok], "reasons": reasons,
            "per_cycle": per_cycle, "cycle1_vs_cycle2_differences": cycle1_diff,
            "postload_allocator_cycles_2_to_n_drift": tick_allocation_drift}


def _boundaries(lines: list[str]) -> list[dict]:
    """Every m2-cycle-boundary line with the owner, cache and arena rows printed under it."""
    found = []
    for i, line in enumerate(lines):
        if not line.startswith(PREFIX + "m2-cycle-boundary "):
            continue
        fields = fields_of(line)
        phase = fields.get("phase", "?")
        snapshot = _phase_rows(lines, i, phase)
        snapshot["arena"] = {}
        for later in lines[i + 1:]:
            lf = fields_of(later)
            if lf.get("phase") != phase:
                break
            if later.startswith(PREFIX + "arena "):
                snapshot["arena"][lf.get("name", "?")] = {
                    k: _int(lf.get(k)) for k in ("cap", "used", "high", "alloc_failures", "resets", "releases")}
        found.append({"line": i, "phase": phase, "cycle": _int(fields.get("cycle")), **snapshot})
    return found


def _count(lines: list[str], prefix: str, **want: str) -> int:
    return sum(1 for line in lines if line.startswith(PREFIX + prefix)
               and all(fields_of(line).get(k) == v for k, v in want.items()))


def parse_successor_log(lines: list[str], row: str, map_name: str, succ_row: str, succ_map: str,
                        mode: int, ticks: int = SUCCESSOR_TICKS, reserve: int = RESERVE) -> dict:
    """Check one guest successor run.

    mode 1: foreign replacement (old map A -> successor B through preflight, dispose with A's
            tags live, unload, load); the run ends by releasing B.
    mode 2: B's preflight fails; A must stay mounted, unchanged and usable; the run ends by
            releasing A.
    mode 3: B's first load fails after A is released (empty state), then a retry loads B; the
            run ends by releasing B.
    Every check name is a machine-checkable property of the printed lines; nothing is inferred
    from the absence of a failure alone.
    """
    final_map = map_name if mode == 2 else succ_map
    base = parse_guest_log(lines, row, map_name, reserve, released_map=final_map,
                           expected_fault_kind="hcp-ctag-chunk-read" if mode == 3 else None)
    checks = dict(base["checks"])
    reasons = list(base["reasons"])
    values = dict(base["values"])

    def require(name: str, ok: bool, why: str) -> None:
        checks[name] = bool(ok)
        if not ok:
            reasons.append(why)

    caps = fields_of(first_line(lines, "partition-selected ") or "")
    tag_cap, bsp_cap = _int(caps.get("tag")), _int(caps.get("bsp"))
    values.update({"row_tag_cap": tag_cap, "row_bsp_cap": bsp_cap})

    sr = first_line(lines, "successor-runtime ")
    srf = fields_of(sr) if sr else {}
    require("successor_runtime", srf.get("row") == row and srf.get("successor-row") == succ_row
            and srf.get("map") == succ_map, f"successor-runtime row/successor-row/map mismatch: {sr}")
    values["successor_package_bytes"] = _int(srf.get("package-bytes"))
    values["successor_residency_bytes"] = _int(srf.get("residency-bytes"))

    begin = first_line(lines, "production-ce-successor-begin ")
    bf = fields_of(begin) if begin else {}
    require("successor_begin", bf.get("mode") == str(mode) and bf.get("old") == map_name
            and bf.get("new") == succ_map and _int(bf.get("ticks")) == ticks,
            f"production-ce-successor-begin missing or wrong (mode {mode}, {map_name}->{succ_map}, ticks {ticks}): {begin}")
    old_tag, old_bsp = _int(bf.get("old-tag-bytes")), _int(bf.get("old-bsp-bytes"))
    values.update({"old_tag_bytes": old_tag, "old_bsp_bytes": old_bsp})
    require("old_map_loaded_before_successor", bool(old_tag) and bool(old_bsp),
            f"old map had no tag/BSP bytes when the successor sequence began: {begin}")

    steps = [fields_of(line) for line in lines if line.startswith(PREFIX + "production-ce-successor-step ")]
    names = [st.get("step") for st in steps]
    ok_attempt = ["preflight", "dispose", "unload", "load", "new-map"]
    expected = {1: ok_attempt, 2: ["preflight", "after-failed-preflight"],
                3: ["preflight", "dispose", "unload", "load", "after-failed-load"] + ok_attempt}[mode]
    require("step_sequence", names == expected, f"steps {names}, expected {expected}")
    values["steps"] = names

    def step_ok(st: dict, result: str, old_mounted: str, new_mounted: str, tag, bsp, label: str) -> bool:
        # "any": the mount is published but CE has not read its tag/BSP image yet, so the
        # owner bytes are still zero at the load step and live only after new-map.
        tag_ok = tag == "any" or ((st.get("tag-bytes") == "0") if tag == 0 else (
            _int(st.get("tag-bytes")) == old_tag if tag == "old" else (_int(st.get("tag-bytes")) or 0) > 0))
        bsp_ok = bsp == "any" or ((st.get("bsp-bytes") == "0") if bsp == 0 else (
            _int(st.get("bsp-bytes")) == old_bsp if bsp == "old" else (_int(st.get("bsp-bytes")) or 0) > 0))
        return (st.get("result") == result and st.get("old-mounted") == old_mounted
                and st.get("new-mounted") == new_mounted and tag_ok and bsp_ok
                and st.get("old") == map_name and st.get("new") == succ_map)

    if names == expected:
        # (step name, result, old-mounted, new-mounted, tag bytes, bsp bytes)
        plan_ok = [("preflight", "1", "1", "0", "old", "old"), ("dispose", "1", "1", "0", "old", "old"),
                   ("unload", "1", "0", "0", 0, 0), ("load", "1", "0", "1", "any", "any"),
                   ("new-map", "1", "0", "1", "live", "live")]
        if mode == 1:
            plan = plan_ok
        elif mode == 2:
            plan = [("preflight", "0", "1", "0", "old", "old"), ("after-failed-preflight", "1", "1", "0", "old", "old")]
        else:
            # The retry starts from the empty state the failed load left: nothing mounted, no bytes.
            plan = ([("preflight", "1", "1", "0", "old", "old"), ("dispose", "1", "1", "0", "old", "old"),
                     ("unload", "1", "0", "0", 0, 0), ("load", "0", "0", "0", 0, 0),
                     ("after-failed-load", "1", "0", "0", 0, 0),
                     ("preflight", "1", "0", "0", 0, 0), ("dispose", "1", "0", "0", 0, 0),
                     ("unload", "1", "0", "0", 0, 0)] + plan_ok[3:])
        for index, (name, *want) in enumerate(plan):
            require(f"step_{index}_{name}", step_ok(steps[index], *want, name),
                    f"step {index} {name} wrong: {steps[index]}")
    else:
        for index in range(len(expected)):
            checks[f"step_{index}_{expected[index]}"] = False
    if mode in (1, 3) and steps:
        new_map_step = next((st for st in reversed(steps) if st.get("step") == "new-map"), {})
        require("successor_scenario_and_bsp", new_map_step.get("scenario") == "1" and new_map_step.get("bsp") == "1",
                f"new-map step lacks CE scenario/BSP: {new_map_step}")
    if mode == 2 and steps:
        kept = next((st for st in steps if st.get("step") == "after-failed-preflight"), {})
        require("old_map_scenario_and_bsp_kept", kept.get("scenario") == "1" and kept.get("bsp") == "1",
                f"old map lost its CE scenario/BSP after the failed preflight: {kept}")
    if mode == 3:
        # One CE tag-cache read failure is the injected partial CTAG stream
        # fault. It starts at the failing load step and remains a cumulative
        # count through retry; BSP and mount-rejection counters stay zero.
        step_counter_bad = [st for st in steps if any(
            st.get(k) not in (("0", "1") if k == "tag-failures" else ("0",))
            for k in ("tag-failures", "bsp-failures", "mount-rejections"))]
        # The first three steps are the old-map preflight/dispose/unload. The
        # expected tag failure appears at load and stays at one thereafter.
        expected_tag_counts = ["0", "0", "0", "1", "1", "1", "1", "1", "1", "1"]
        counter_ok = (len(steps) == len(expected_tag_counts) and
                      all(st.get("tag-failures") == want and st.get("bsp-failures") == "0" and
                          st.get("mount-rejections") == "0"
                          for st, want in zip(steps, expected_tag_counts)))
        require("step_owner_counters_expected_once", counter_ok,
                f"mode3 step counters do not show one injected CTAG failure: {step_counter_bad[:1]}")
    else:
        step_counter_bad = [st for st in steps if any(st.get(k) != "0" for k in ("tag-failures", "bsp-failures", "mount-rejections"))]
        require("step_owner_counters_zero", bool(steps) and not step_counter_bad,
                f"step lines with non-zero owner counters: {step_counter_bad[:1]}")

    # fault gate: only the modes that inject a fault may show one, and it must be seen to bite.
    fault_lines = [line for line in lines if line.startswith(PREFIX + "successor-fault ")]
    rejected = _count(lines, "profile-preflight rejected ", reason="successor-package-gate", map=succ_map)
    last_fault_count = _int(steps[-1].get("fault-count")) if steps else None
    if mode == 1:
        require("fault_gate", not fault_lines and rejected == 0 and last_fault_count == 0,
                f"replacement run shows a fault or rejection: faults={fault_lines[:1]} rejected={rejected}")
    elif mode == 2:
        require("fault_gate", len(fault_lines) == 1 and rejected == 1 and (last_fault_count or 0) > 0
                and "kind=package-read" in fault_lines[0],
                f"expected one package preflight fault and one successor-package-gate rejection: "
                f"faults={len(fault_lines)} rejected={rejected} fault-count={last_fault_count}")
    else:
        load_failures = _count(lines, "profile-load failed ", map=succ_map, state="empty")
        fault_fields = fields_of(fault_lines[0]) if len(fault_lines) == 1 else {}
        cleanup = first_line(lines, "successor-fault-cleanup ")
        cleanup_fields = fields_of(cleanup) if cleanup else {}
        require("fault_gate", len(fault_lines) == 1 and rejected == 0 and
                fault_fields.get("kind") == "hcp-ctag-chunk-read" and
                _int(fault_fields.get("callbacks")) == 1 and
                (_int(fault_fields.get("prior-bytes")) or 0) >= 65536 and
                (last_fault_count or 0) == 1 and load_failures == 0 and
                cleanup_fields.get("game-load") == "0" and
                cleanup_fields.get("delayed-error-consumed") == "1" and
                cleanup_fields.get("mounted") == "0" and cleanup_fields.get("scenario") == "0",
                f"expected one active CTAG visitor failure after 64 KiB, CE safe-empty cleanup, and no "
                f"package-gate rejection: faults={len(fault_lines)} rejected={rejected} "
                f"load-failures={load_failures} fault-count={last_fault_count}")
    values["fault_lines"] = fault_lines
    values["successor_package_gate_rejections"] = rejected

    # service-side evidence: successor stages, mounts and boundaries.
    stages = _count(lines, "profile-preflight result=1 ", map=succ_map, successor="1")
    mounts = _count(lines, "map-mount result=1 ", active="1", map=succ_map, source="profile-runtime")
    # replacement: pre-unload stage + the post-unload revalidation CE's unloader forces; retry: the
    # failed attempt's pre-unload stage (its post-unload revalidation is the rejection), then the
    # retry's single stage (nothing was mounted, so CE never calls the unloader and no second
    # revalidation runs); failed preflight: no successful stage at all.
    want_stages, want_mounts = {1: (2, 1), 2: (0, 0), 3: (2, 2)}[mode]
    # The rendered workload also validates once immediately after the real
    # final kick, before CE enters its transaction. Keep the ordinary CE
    # revalidations and account only an explicitly observed successful probe.
    rendered_preflights = _count(lines, "c3-successor-preflight ", result="1", expected="1", mode=str(mode))
    require("rendered_preflight_once", rendered_preflights <= 1,
            f"rendered preflight repeated {rendered_preflights} times")
    if mode in (1, 3):
        want_stages += rendered_preflights
    require("successor_stages_and_mount", stages == want_stages and mounts == want_mounts,
            f"successor stages {stages} (want {want_stages}), successor mounts {mounts} (want {want_mounts})")
    values.update({"successor_stage_passes": stages, "successor_mounts": mounts})

    boundaries = _boundaries(lines)
    seq = [(b["phase"], b["cycle"]) for b in boundaries]
    want_seq = {1: [("map-loaded", 1), ("map-released", 1), ("map-loaded", 2), ("map-released", 2)],
                2: [("map-loaded", 1), ("map-released", 1)],
                3: [("map-loaded", 1), ("map-released", 1),
                    ("map-loaded", 2), ("map-released", 2),
                    ("map-loaded", 3), ("map-released", 3)]}[mode]
    require("boundary_sequence", seq == want_seq, f"map boundaries {seq}, expected {want_seq}")
    values["boundary_sequence"] = seq
    if mode in (1, 3):
        # the old owner is unpublished (boundary 2) before the successor mount, and the successor
        # mount precedes the successor's loaded boundary.
        index = {"unload": next((i for i, l in enumerate(lines) if l.startswith(PREFIX + "production-ce-successor-step step=unload")), None),
                 "mount": next((i for i, l in enumerate(lines) if l.startswith(PREFIX + f"map-mount result=1 active=1 map={succ_map} ")), None)}
        released_a = boundaries[1]["line"] if len(boundaries) > 1 else None
        loaded_b = boundaries[2]["line"] if len(boundaries) > 2 else None
        require("unpublish_before_successor_load",
                None not in (index["unload"], index["mount"], released_a, loaded_b)
                and released_a < index["unload"] < index["mount"] < loaded_b,
                f"old unpublish / successor mount order wrong: {index} released_a={released_a} loaded_b={loaded_b}")
    drained = [fields_of(l).get("renderer_drained") for l in lines
               if l.startswith(PREFIX + "owner-telemetry ") and "backing_cap" in l
               and fields_of(l).get("phase") in ("map-loaded", "map-released", "map-empty")]
    require("renderer_drained_at_boundaries", bool(drained) and all(d == "1" for d in drained),
            f"renderer_drained at boundaries: {drained}")
    values["renderer_drained_at_boundaries"] = drained

    # successor map fits the selected row's guarded owners; the loaded line carries its bytes.
    if mode in (1, 3):
        loaded = first_line(lines, "production-ce-successor-loaded ")
        lf = fields_of(loaded) if loaded else {}
        t, b = _int(lf.get("tag-bytes")), _int(lf.get("bsp-bytes"))
        values.update({"successor_tag_bytes": t, "successor_bsp_bytes": b,
                       "successor_tag_count": _int(lf.get("tag-count"))})
        require("successor_loaded", lf.get("result") == "1" and lf.get("new") == succ_map
                and lf.get("old") == map_name and lf.get("old-mounted") == "0"
                and lf.get("scenario") == "1" and lf.get("tag-table") == "1"
                and (_int(lf.get("tag-count")) or 0) > 0 and bool(t) and bool(b),
                f"production-ce-successor-loaded incomplete: {loaded}")
        require("successor_fits_row_caps", bool(t and b and tag_cap and bsp_cap) and t <= tag_cap and b <= bsp_cap,
                f"successor tag {t}/{tag_cap} or BSP {b}/{bsp_cap} exceeds the row's caps")
        if t and b and tag_cap and bsp_cap:
            values.update({"successor_tag_margin": tag_cap - t, "successor_bsp_margin": bsp_cap - b})
    usable = first_line(lines, "production-ce-successor-usable ")
    uf = fields_of(usable) if usable else {}
    require("usable_after_sequence", uf.get("result") == "1" and _int(uf.get("ticks")) == ticks
            and uf.get("old") == map_name, f"production-ce-successor-usable missing or failed: {usable}")

    # final release leaves both owners empty; reset/publication counts equal the loads/releases made.
    loads = 1 if mode == 2 else 2
    released = [b for b in boundaries if b["phase"] == "map-released"]
    final = released[-1] if released else {}
    owners, cache = final.get("owners", {}), final.get("cache", {})
    require("final_owner_state",
            bool(final) and all((owners.get(n) or {}).get("used") == 0 for n in ("tags", "bsp"))
            and all((cache.get(n) or {}).get("current") == 0 for n in ("tags", "bsp"))
            and (all((owners.get(n) or {}).get("resets") == loads for n in ("game_state", "tags", "bsp"))
                 if mode != 3 else
                 (owners.get("game_state") or {}).get("resets") == 2 and
                 (owners.get("tags") or {}).get("resets") == 3 and
                 (owners.get("bsp") or {}).get("resets") == 2)
            and (all((cache.get(n) or {}).get("publications") == loads and
                     (cache.get(n) or {}).get("unmounts") == loads for n in ("tags", "bsp"))
                 if mode != 3 else
                 (cache.get("tags") or {}).get("publications") == 2 and
                 (cache.get("tags") or {}).get("unmounts") == 3 and
                 (cache.get("bsp") or {}).get("publications") == 2 and
                 (cache.get("bsp") or {}).get("unmounts") == 2),
            f"final release owners/caches do not show {loads} publication(s) and release(s) with zero residue: "
            f"owners={owners} cache={cache}")
    values["final_release_snapshot"] = {k: final.get(k) for k in ("owners", "backing", "cache", "arena")} if final else None
    values["boundaries"] = [{k: b[k] for k in ("phase", "cycle", "owners", "backing", "cache", "arena")} for b in boundaries]

    failing = [name for name, ok in checks.items() if not ok]
    return {"checks": checks, "failing_checks": failing, "reasons": reasons, "values": values,
            "peaks": base["peaks"], "steps": steps}


def successor_header_text(succ_row: str, package_root: Path) -> str:
    """The successor row's generated image header, renamed so it can sit beside the selected row's.

    tools/c2_profile_image_header.py emits one row's HCU_C2_IMAGE_* names; the guest includes a
    second image under HCU_C2_SUCC_*. The content (digests, metadata blob, source table, datum
    table) is the generator's output verbatim; only the identifiers are renamed.
    """
    sys.path.insert(0, str(ROOT / "tools"))
    try:
        import c2_profile_image_header as header_tool
    finally:
        sys.path.pop(0)
    text = header_tool.build_header(succ_row, package_root, ROOT)
    for old, new in (("HCU_C2_PROFILE_IMAGE_", "HCU_C2_PROFILE_SUCC_"), ("HCU_C2_IMAGE_", "HCU_C2_SUCC_"),
                     ("hcu_c2_image_source", "hcu_c2_succ_source"), ("hcu_c2_image_datum", "hcu_c2_succ_datum")):
        text = text.replace(old, new)
    return text


def write_successor_includes(out: Path, succ_row: str, package_root: Path, mode: int, ticks: int) -> Path:
    """<out>/succ-inc: hcu_c2_successor.h (mode, ticks) and hcu_c2_succ_image.h (successor image)."""
    include_dir = out / "succ-inc"
    include_dir.mkdir(parents=True, exist_ok=True)
    (include_dir / "hcu_c2_successor.h").write_text(
        f"#define HALO_PS2_C2_SUCCESSOR_MODE {mode}\n#define HALO_PS2_C2_SUCCESSOR_TICKS {ticks}\n")
    (include_dir / "hcu_c2_succ_image.h").write_text(successor_header_text(succ_row, package_root), encoding="utf-8")
    return include_dir


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


def link_row(row: str, package_root: Path, out: Path, cycles: int = 1, ticks: int = 0,
             include_dir: Path | None = None, render_views: int = 0,
             render_frames: int = 300, workload_players: int = 0) -> tuple[Path | None, str]:
    """Link the row's runtime-guest ELF under out/link, holding the shared link lock.

    include_dir (the --successor headers) is added to C_INCLUDE_PATH for every compile."""
    link_dir = out / "link"
    LINK_LOCK.parent.mkdir(parents=True, exist_ok=True)
    command = [sys.executable, str(ROOT / "tools/hcu_parent_link_probe.py"),
               "--asset-profile", "host", "--partition-profile", row,
               "--profile-package-root", str(package_root),
               "--headless-runtime-guest", "--output-dir", str(link_dir)]
    env = None
    include_dirs: list[str] = []
    if cycles != 1 or ticks:
        # main.c includes <hcu_c2_cycles.h> when it exists; no build script has a flag for it.
        cycles_dir = out / "cycles-inc"
        cycles_dir.mkdir(parents=True, exist_ok=True)
        (cycles_dir / "hcu_c2_cycles.h").write_text(
            f"#define HALO_PS2_C2_PRODUCTION_RUNTIME_CYCLES {cycles}\n"
            f"#define HALO_PS2_C2_PRODUCTION_RUNTIME_TICKS {ticks}\n")
        include_dirs.append(str(cycles_dir))
    if render_views:
        # hcu_main.c includes <hcu_c3_render.h> under HCU_C3 when it exists (C3:render block).
        render_dir = out / "render-inc"
        render_dir.mkdir(parents=True, exist_ok=True)
        (render_dir / "hcu_c3_render.h").write_text(
            f"#define HCU_C3_RENDER_VIEWS {render_views}\n"
            f"#define HCU_C3_RENDER_FRAMES {render_frames}\n"
            f"#define HCU_C3_TEXFENCE_CAP_PAGES {TEXFENCE_CAP_PAGES}\n")
        include_dirs.append(str(render_dir))
    if workload_players:
        # main.c includes <hcu_c3_workload.h> (C3:workload block): CE's player_spawn_count.
        workload_dir = out / "workload-inc"
        workload_dir.mkdir(parents=True, exist_ok=True)
        (workload_dir / "hcu_c3_workload.h").write_text(
            f"#define HCU_C3_WORKLOAD_LOCAL_PLAYERS {workload_players}\n")
        include_dirs.append(str(workload_dir))
    if include_dir is not None:
        include_dirs.append(str(include_dir))
    # C3.6b begin: the objects table is generated per row from its own scenario map (sky reference) and the
    # EE build reads it through HCU_C3_OBJECTS_GEN (tools/ee-world.mk), so a row never links another map's table.
    if os.environ.get("HCU_C3_OBJECTS") == "1":
        objects_dir = out / "objects-gen"
        objects_dir.mkdir(parents=True, exist_ok=True)
        generated = subprocess.run(
            [sys.executable, "-I", str(ROOT / "tools/hcu_c3_objects_table.py"), "--package-json",
             str(package_root / row / f"{row}.json"), "--sky-from-scenario",
             "--output", str(objects_dir / "hcu_c3_objects_table.h")],
            cwd=ROOT, capture_output=True, text=True)
        if generated.returncode:
            return None, f"objects table generation failed: {generated.stderr.strip()[-400:]}"
        env = dict(os.environ, HCU_C3_OBJECTS_GEN=str(objects_dir))
    if include_dirs:
        env = dict(env or os.environ, C_INCLUDE_PATH=":".join(include_dirs))
    # C3.6b end
    with LINK_LOCK.open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        rc, timed_out = run_group(command, log=out / "link.log", timeout=LINK_TIMEOUT, env=env)
    elf = link_dir / f"hcu-gameplay-machine-partition-{row}-headless-runtime-guest.elf"
    if timed_out:
        return None, f"link timed out after {LINK_TIMEOUT}s"
    if rc or not elf.is_file():
        return None, f"link failed (exit {rc}); see {out / 'link.log'}"
    return elf, ""


# PCSX2 execution mode for every guest run of this invocation (--emu-mode). The
# interpreter is the default; recompiler sets the four Enable switches in each run's ini.
EMU_MODE = "interpreter"


def guest_row(row: str, elf: Path, plan: dict, out: Path, timeout: int = GUEST_TIMEOUT,
              process_timeout: int = GUEST_PROCESS_TIMEOUT, extra_stage_paths=(),
              released_map: str | None = None, capture_markers=()) -> tuple[bool, str]:
    # These directories are owned exclusively by this row attempt. Remove them before
    # invoking the runner so a display/launch failure cannot leave prior logs, captures,
    # or a manifest available to the result parser.
    for path in (out / "guest", out / "captures", out / "guest.log"):
        if path.is_symlink() or path.is_file():
            path.unlink()
        elif path.is_dir():
            shutil.rmtree(path)
    command = [sys.executable, "-I", str(ROOT / "tools/c2_guest_run.py"),
               "--timeout", str(timeout), "--output-dir", str(out / "guest"),
               "--production-elf", str(elf), "--package-tree", str(plan["package_tree"]),
               "--guest-package-root", plan["guest_package_root"],
               "--production-row", row, "--production-map", plan["map"],
               "--production-profile-id", str(plan["profile_id"]),
               "--emu-mode", EMU_MODE]
    if released_map:
        command += ["--production-release-map", released_map]
    if capture_markers:
        command += ["--capture-dir", str(out / "captures")]
        for marker in capture_markers:
            command += ["--capture-marker", marker]
    for path in dict.fromkeys([*plan["stage_paths"], *extra_stage_paths]):
        command += ["--stage-path", path]
    rc, timed_out = run_group(command, log=out / "guest.log", timeout=process_timeout)
    if timed_out:
        return False, f"guest runner exceeded {process_timeout}s"
    if rc:
        return False, f"guest runner exited {rc}; see {out / 'guest.log'}"
    return True, ""


def validate_guest_provenance(out: Path, attempt_started_unix_ns: int,
                              emu_mode: str, expected_captures: int = 0) -> tuple[dict | None, str]:
    """Accept only logs/captures produced by this successful guest launch."""
    manifest_path = out / "guest/manifest.json"
    if not manifest_path.is_file():
        return None, "guest runner produced no manifest for this attempt"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        return None, f"guest manifest is unreadable: {error}"
    runs = [run for run in manifest.get("runs", [])
            if run.get("run") == "partition-selected" and "error" not in run]
    if len(runs) != 1:
        return None, f"expected one current partition-selected guest run, found {len(runs)}"
    run = runs[0]
    launch_id = run.get("launch_id")
    started = run.get("launch_started_unix_ns")
    if (not launch_id or not manifest.get("invocation_id") or
            run.get("invocation_id") != manifest.get("invocation_id") or
            not isinstance(started, int) or started < attempt_started_unix_ns):
        return None, "guest manifest does not identify a launch from this attempt"
    config = run.get("pcsx2_config", {})
    if config.get("emu_mode") != emu_mode or config.get("emu_mode_verified") is not True:
        return None, f"PCSX2 {emu_mode} settings were not verified for this launch"
    for field, hash_field in (("log", "log_sha256"), ("halo_lines_saved", "halo_lines_sha256")):
        path = Path(run.get(field, ""))
        if not path.is_file() or path.stat().st_mtime_ns < started:
            return None, f"current guest {field} is missing or predates this launch"
        if not run.get(hash_field) or sha256_file(path) != run[hash_field]:
            return None, f"current guest {field} hash does not match its manifest"
    captures = run.get("captures", [])
    if len(captures) != expected_captures:
        return None, f"expected {expected_captures} current captures, found {len(captures)}"
    for capture in captures:
        path = Path(capture.get("file", ""))
        if (capture.get("launch_id") != launch_id or not path.is_file() or
                not isinstance(capture.get("captured_unix_ns"), int) or
                capture["captured_unix_ns"] < started or path.stat().st_mtime_ns < started or
                not capture.get("sha256") or sha256_file(path) != capture["sha256"]):
            return None, "capture is missing, stale, or belongs to a different guest launch"
    return run, ""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def prepare_render_tree() -> Path:
    """Stage build/c3/render-tree/pkg from build/c3/render-packages.

    The HCP is linked or copied unchanged and the guest checks its SHA-256 pin.
    The producer must declare its actual envelope size; staging never repairs a manifest."""
    source = ROOT / "build/c3/render-packages"
    pkg = RENDER_PACKAGE_TREE / "pkg"
    if pkg.is_symlink():
        pkg.unlink()
    for directory in sorted(p for p in source.iterdir() if p.is_dir()):
        row = directory.name
        hcp, manifest = directory / f"{row}.hcp", directory / f"{row}.json"
        if not (hcp.is_file() and manifest.is_file()):
            continue
        out = pkg / row
        out.mkdir(parents=True, exist_ok=True)
        link = out / hcp.name
        if link.is_symlink() or link.exists():
            link.unlink()
        try:
            os.link(hcp, link)  # the image header pins the staged path, so it must not resolve back to render-packages
        except OSError:
            shutil.copy2(hcp, link)
        data = json.loads(manifest.read_text(encoding="utf-8"))
        real = hcp.stat().st_size
        if data["memory"]["package_file_bytes"] != real:
            raise RuntimeError(f"render manifest package size differs from {hcp}; regenerate it with hcu_render_media.py")
        (out / manifest.name).write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return pkg


def texfence_lines(lines: list[str], kind: str | None = None) -> list[dict]:
    """Parsed c3-texfence lines (periodic and final), in guest order."""
    out = []
    for line in lines:
        if "c3-texfence " not in line:
            continue
        f = fields_of(line)
        if kind is None or f.get("kind") == kind:
            out.append(f)
    return out


def c3_7_texfence_checks(lines: list[str], views: int, frames: int, cap_pages: int = 0) -> dict:
    """C3.7 texture fence evidence from the guest log.

    Rules: (a) claims published only after their upload is queued; (b) source bytes released only after the
    fence is observed; (c) slot reuse fenced against the last kick of the slot. Counters are recorded in the
    texture cache at the real event points; the final c3-texfence line holds the totals. Under cap_pages (debug pressure)
    the run must also show real reuse after a fence. Nothing qualifies without a final line and a
    rendered-frame final line with the requested view count.
    """
    periodic = texfence_lines(lines, "periodic")
    final = texfence_lines(lines, "final")
    frame_final = [l for l in lines if "c3-frame kind=final " in l]
    ff = fields_of(frame_final[-1]) if frame_final else {}
    tf = final[-1] if final else {}
    def num(f: dict, k: str) -> int | None:
        return _int(f.get(k))
    checks = {
        "texfence_final_present": bool(final) and len(periodic) >= 1,
        "texfence_frames_match": tf.get("frame") == str(frames) and ff.get("frame") == str(frames),
        "claims_published_before_queue_zero": num(tf, "claims-published-before-queue") == 0 and
            all(num(p, "claims-published-before-queue") == 0 for p in periodic),
        "source_released_before_fence_zero": num(tf, "source-released-before-fence") == 0 and
            all(num(p, "source-released-before-fence") == 0 for p in periodic),
        "reuse_unfenced_zero": num(tf, "reuse-unfenced") == 0 and
            all(num(p, "reuse-unfenced") == 0 for p in periodic),
        "claims_published_nonzero": (num(tf, "claims-published") or 0) > 0,
        "upload_sources_released": (num(tf, "source-released") or 0) > 0,
        "rendered_views_match": ff.get("views") == str(views),
        # the completed fence may lag the newest kick by at most one (the kick still in flight)
        "fence_lag_at_most_one": (num(tf, "kick-seq") or 0) - (num(tf, "fence-seq") or 0) <= 1,
        "kicks_observed": (num(tf, "kick-seq") or 0) >= frames,
        "cap_pages_recorded": tf.get("cap-pages") == str(cap_pages),
    }
    if cap_pages:
        checks["pressure_evictions_seen"] = (num(tf, "evictions") or 0) > 0
        checks["reuse_after_fence_seen"] = (num(tf, "reuse-after-fence") or 0) > 0
        checks["reuse_blocked_while_in_flight"] = (num(tf, "reuse-blocked-by-fence") or 0) > 0
    qualified = all(checks.values())
    reasons = [f"c3-7 check failed: {k}" for k, v in checks.items() if not v]
    return {"checks": checks, "reasons": reasons, "qualified": qualified, "final": tf,
            "periodic_lines": len(periodic), "views": views}


def render_checks(lines: list[str], views: int, frames: int) -> dict:
    """C3 render-loop evidence from the guest log: ready, final counters, teardown order, no render failure."""
    out = {"checks": {}, "reasons": []}
    ready = [l for l in lines if "c3-render-ready " in l]
    final = [l for l in lines if "c3-frame kind=final " in l]
    held = [l for l in lines if "c3-render-held " in l]
    down = [l for l in lines if "c3-render-teardown " in l]
    fails = [l for l in lines if "HALO_PS2_FAIL c3-render" in l]
    ff = fields_of(final[-1]) if final else {}
    tf = fields_of(down[-1]) if down else {}
    checks = {
        "render_ready": len(ready) == 1,
        "render_no_failure": not fails,
        "render_final_frames": ff.get("frame") == str(frames) and ff.get("frames") == str(frames),
        "render_views": ff.get("views") == str(views),
        "render_overflow_zero": ff.get("overflow") == "0",
        "render_idle_violations_zero": ff.get("idle-violations") == "0" and ff.get("emit-failures") == "0",
        "render_held": len(held) == 1,
        "render_ticks": any("production-ce-ticks result=1 " in l for l in lines),
        "render_teardown": bool(down) and tf.get("world-unbind") == "0" and tf.get("readers-after") == "0"
                           and tf.get("media-loaded") == "0",
    }
    out["checks"] = checks
    out["reasons"] = [f"render check failed: {k}" for k, v in checks.items() if not v]
    out["final"] = ff
    out["teardown"] = tf
    out["failures"] = fails
    return out


C3_5_CLEAR_RGB = (16, 16, 24)  # the unused-quadrant clear colour of hcu_c3_render_tick
C3_5_LAYOUT_SIZE = (512, 448)  # VIDEO_WIDTH x VIDEO_HEIGHT, the space the layout rectangles are written in
# PCSX2's default GS display (640x480). tools/c2_guest_run.py does not set the window size and the guest does not
# log its output size, so this is the fallback when neither is known. Real captures match it (game pixels fill
# exactly 0..639 x 0..479 of the 1280x1024 root); the captured window size, when one exists, takes precedence.
PCSX2_DEFAULT_GAME_SIZE = (640, 480)


def c3_5_game_size(captures: list[dict]) -> tuple[int, int] | None:
    """Game output size of a run from its captures: the PCSX2 window size when the window itself was captured
    (the capture is then exactly the window); None when only the root was captured (its size is the Xvfb screen,
    not the game area)."""
    for c in captures or []:
        size = str(c.get("window_size") or "")
        if c.get("window") not in (None, "", "root") and "x" in size:
            w, h = size.split("x", 1)
            if w.isdigit() and h.isdigit():
                return int(w), int(h)
    return None


def c3_5_layout_checks(views: int, capture_files: list[str], game_size: tuple[int, int] | None = None) -> dict:
    """C3.5 layout evidence from the newest framebuffer capture: each view rectangle is non-black and carries
    scene pixels, and no clear colour bleeds into a view (3 views: top half plus bottom quarters, nothing cleared).

    Rectangles are defined in the 512x448 layout space (hcu_render_layout_compute, halo-ps2 video.h). The game
    occupies the top-left of the capture at `game_size` (the window size when known, else PCSX2_DEFAULT_GAME_SIZE),
    so each layout point maps to capture pixel gx + x * gw / 512, gy + y * gh / 448. The game rectangle is never
    derived from pixel content: a black view would then shrink it and make a neighbouring view pass wrongly."""
    out = {"views": views, "checks": {}, "reasons": [], "regions": {}}
    try:
        from PIL import Image
    except ImportError:
        out["checks"] = {"layout_pil_available": False}
        out["reasons"] = ["layout check needs PIL"]
        return out
    if not capture_files:
        out["checks"] = {"layout_capture_present": False}
        out["reasons"] = ["no framebuffer capture for layout check"]
        return out
    img = Image.open(capture_files[-1]).convert("RGB")
    sw, sh = img.size
    px = img.load()
    gw, gh = game_size if game_size else PCSX2_DEFAULT_GAME_SIZE
    gx, gy = 0, 0
    source = "window" if game_size else "pcsx2-default"
    out["game_rect"] = {"rect": (gx, gy, gw, gh), "source": source}
    lw, lh = C3_5_LAYOUT_SIZE
    fx, fy = gw / float(lw), gh / float(lh)
    rects = {
        1: [(0, 0, 512, 448)],
        2: [(0, 0, 512, 224), (0, 224, 512, 224)],
        3: [(0, 0, 512, 224), (0, 224, 256, 224), (256, 224, 256, 224)],
        4: [(0, 0, 256, 224), (256, 0, 256, 224), (0, 224, 256, 224), (256, 224, 256, 224)],
    }[views]
    clear_rect = None  # the 3-view layout has no unused quadrant; every pixel belongs to a view

    def to_capture(x, y):
        return (min(sw - 1, int(gx + x * fx)), min(sh - 1, int(gy + y * fy)))

    def sample(rect, inset=4, step=6):
        x0, y0, w, h = rect
        for y in range(y0 + inset, y0 + h - inset, step):
            for x in range(x0 + inset, x0 + w - inset, step):
                yield px[to_capture(x, y)]

    def is_clear(c):
        return all(abs(c[i] - C3_5_CLEAR_RGB[i]) <= 3 for i in range(3))

    def is_black(c):
        return max(c) <= 6

    checks = {
        "layout_capture_size_known": sw >= 320 and sh >= 224,
        "layout_game_rect_in_capture": gw > 0 and gh > 0 and gx + gw <= sw and gy + gh <= sh,
    }
    for i, r in enumerate(rects):
        pts = list(sample(r))
        nonblack = sum(1 for c in pts if not is_black(c)) / max(1, len(pts))
        clear_frac = sum(1 for c in pts if is_clear(c)) / max(1, len(pts))
        out["regions"][f"view{i}"] = {"rect": r, "capture_rect": (*to_capture(r[0], r[1]), round(r[2] * fx),
                                                                   round(r[3] * fy)),
                                      "nonblack": round(nonblack, 3), "clear": round(clear_frac, 3)}
        checks[f"layout_view{i}_nonblack"] = nonblack >= 0.05
        checks[f"layout_view{i}_no_clear_bleed"] = clear_frac < 0.05
    if clear_rect:
        pts = list(sample(clear_rect, inset=2, step=3))
        uniform = sum(1 for c in pts if is_clear(c)) / max(1, len(pts))
        out["regions"]["clear"] = {"rect": clear_rect, "uniform": round(uniform, 4)}
        checks["layout_unused_quadrant_cleared"] = uniform >= 0.99
    out["checks"] = checks
    out["reasons"] = [f"layout check failed: {k}" for k, v in checks.items() if not v]
    return out


def c3_3_scene_checks(lines: list[str], views: int, workload_players: int) -> dict:
    """C3.3 workload presence: per-scene expected counts against snapshot counts and drawn objects.

    Snapshot types: biped, weapon, vehicle. Stock CE multiplayer has no AI, so in a multi-player scene the
    enemies are the opposing players (user decision 2026-10-24); AI bots remain C5 work. Enemies are present
    when there are at least two players and every player's biped is in the published snapshot.
    Submitted counts use the unique identity sets (hcu_render_objects note_submission), never the per-view
    submitted counters, so a repeated draw of one player or one inflated identity cannot prove the scene.
    """
    snaps = [line for line in lines if "c3-snapshot " in line and " biped=" in line]
    final = [line for line in lines if "c3-objects-final " in line]
    snap = fields_of(snaps[-1]) if snaps else {}
    drawn = fields_of(final[-1]) if final else {}
    biped, weapon, vehicle = _int(snap.get("biped")), _int(snap.get("weapon")), _int(snap.get("vehicle"))
    active = _int(snap.get("active-views"))
    players_present = biped is not None and biped >= workload_players and active == views
    checks = {
        "snapshot_present": bool(snaps),
        "players_present": players_present,
        "enemies_present": players_present and workload_players >= 2,
        "weapons_present": weapon is not None and weapon >= workload_players,
        "vehicles_present": vehicle is not None and vehicle >= 1,
        "drawn_objects_nonzero": (_int(drawn.get("drawn")) or 0) > 0,
        # A snapshot count alone is not a submitted draw. These counters advance
        # only after the object renderer emitted geometry for this source identity.
        # unique-bipeds counts distinct {datum index, datum identifier} identities over the whole map
        # lifetime. Stable identities give exactly one identity per player. Any extra identity is
        # mutable-generation inflation or unexplained churn (the old 146-biped run), so it fails closed.
        "player_bodies_submitted": _int(drawn.get("unique-bipeds")) == workload_players,
        "weapons_submitted": (_int(drawn.get("unique-weapons")) or 0) >= workload_players,
        "vehicles_submitted": (_int(drawn.get("unique-vehicles")) or 0) >= 1,
        "draw_identity_set_complete": _int(drawn.get("drawn-identity-overflow")) == 0,
    }
    reasons = [f"scene check failed: {name}" for name, ok in checks.items() if not ok]
    return {
        "expected": {"players": workload_players, "enemies": "opposing-players",
                     "enemy_count": max(workload_players - 1, 0), "views": views},
        "snapshot": {"biped": biped, "weapon": weapon, "vehicle": vehicle, "active_views": active},
        "drawn_objects": _int(drawn.get("drawn")),
        "checks": checks,
        "enemies": {"kind": "opposing-players", "ai_bots": "C5"},
        "reasons": reasons,
        "c3_3_qualified": all(checks.values()),
    }


def c3_2_contract_checks(lines: list[str], views: int) -> dict:
    """C3.2 parent-consumer evidence from existing telemetry only.

    The parent may only read CE-published snapshot data. The guest log shows this through:
      - `HALO c3-views ... camera=snapshot|fixed|skipped active=`: once a view has been active, every one of
        its rows must use camera=snapshot (a fixed or skipped camera fails the contract). Rows before the
        view's first active row are the pre-spawn state and are exempt; each view needs at least one active row;
      - `c3-snapshot ... seq= active-views=`: CE publishes sequences that advance, with every view active;
      - `c3-objects ... source=`: object geometry must come from the bank, never the synthetic test producer.
    These counters cannot prove the absence of a parent call to CE simulation; the static audit in
    tests/test_c3_2_parent_boundary.py covers that. The check fails honestly on the current regression
    (fixed cameras, no snapshot publication) and needs no new telemetry.
    """
    view_rows = [fields_of(l) for l in lines if re.search(r"\bc3-views frame=", l)]
    snap_rows = [fields_of(l) for l in lines if re.search(r"\bc3-snapshot frame=", l) and " seq=" in l]
    object_rows = [fields_of(l) for l in lines if re.search(r"\bc3-objects frame=", l)]
    in_range = [row for row in view_rows if _int(row.get("view")) is not None and _int(row.get("view")) < views]
    cameras = [row.get("camera") for row in in_range]
    snapshot_views = sum(1 for c in cameras if c == "snapshot")
    fixed_views = sum(1 for c in cameras if c == "fixed")
    skipped_views = sum(1 for c in cameras if c == "skipped")
    seen_active: set[int] = set()
    active_rows = {v: 0 for v in range(views)}
    contract_rows = []
    pre_spawn_rows = 0
    for row in in_range:
        v = _int(row.get("view"))
        if row.get("active") == "1":
            seen_active.add(v)
            active_rows[v] += 1
        elif v not in seen_active:
            pre_spawn_rows += 1
            continue
        contract_rows.append(row)
    seqs = [_int(row.get("seq")) for row in snap_rows]
    seq_advancing = bool(seqs) and all(s is not None for s in seqs) and all(b > a for a, b in zip(seqs, seqs[1:])) \
        and seqs[-1] > seqs[0]
    last_active = _int(snap_rows[-1].get("active-views")) if snap_rows else None
    checks = {
        "views_reported_per_view": all(any(_int(r.get("view")) == v for r in view_rows) for v in range(views)),
        "views_active_per_view": all(active_rows[v] > 0 for v in range(views)),
        "camera_from_snapshot_all_views": bool(contract_rows) and
            all(row.get("camera") == "snapshot" for row in contract_rows),
        "snapshot_sequence_advances": seq_advancing,
        "snapshot_active_views_match": last_active == views,
        "object_source_bank_only": bool(object_rows) and all(r.get("source") == "bank" for r in object_rows),
    }
    reasons = [f"c3.2 contract check failed: {name}" for name, ok in checks.items() if not ok]
    return {
        "views": views,
        "camera_rows": {"snapshot": snapshot_views, "fixed": fixed_views, "skipped": skipped_views,
                        "pre_spawn_inactive": pre_spawn_rows},
        "active_rows_per_view": [active_rows[v] for v in range(views)],
        "snapshot_sequences": {"first": seqs[0] if seqs else None, "last": seqs[-1] if seqs else None,
                               "rows": len(seqs)},
        "checks": checks,
        "reasons": reasons,
        "c3_2_qualified": all(checks.values()),
    }


def capture_has_scene_variation(capture: dict) -> bool:
    """Reject clear-color/HUD-only evidence; this does not replace visual review."""
    return (not capture.get("error") and
            (capture.get("nonblack_fraction") or 0) >= 0.01 and
            (capture.get("scene_color_buckets") or 0) >= 16 and
            (capture.get("scene_nonflat_fraction") or 0) >= 0.005)


def c3_9_bitmap_checks(lines: list[str], views: int) -> dict:
    """C3.9 bitmap evidence: registration, per-frame begin/set_view/requests/end, queue-end
    inside each CE frame, and release with no leases. Counters come from the parent frame
    owner (src/stream/hcu_bitmap_frame.c) printed as c3-bitmap lines.

    Upload/draw proof is the held-frame capture review, which this checker does not replace.
    """
    ticks = [fields_of(l) for l in lines if "c3-bitmap tick=" in l]
    bound = [l for l in lines if "c3-bitmap-bound " in l]
    released = [fields_of(l) for l in lines if "c3-bitmap map-released " in l]
    fails = [l for l in lines if "HALO_PS2_FAIL c3-bitmap" in l]
    total = {k: sum(_int(t.get(k)) or 0 for t in ticks)
             for k in ("begin-calls", "begin", "set-view", "requests", "queue-end", "end")}
    rel = released[-1] if released else {}
    # Accepted frames are begun CE frames whose sealed batch was not dropped. Drops are cumulative,
    # so the last tick line carries the run total.
    dropped_total = _int(ticks[-1].get("bitmap-frames-dropped")) if ticks else None
    accepted = total["begin"] - (dropped_total or 0)
    checks = {
        "bitmap_registered": len(bound) == 1,
        "bitmap_no_failure": not fails,
        # (a) each CE frame in the run calls begin, one set_view per view, queue end and end.
        "bitmap_frames_seen": total["begin"] > 0 and total["begin-calls"] == total["begin"],
        # A run whose every frame was dropped (or never began) is not bitmap evidence.
        "bitmap_accepted_frames_nonzero": accepted > 0,
        "bitmap_set_view_per_view": bool(ticks) and all(
            1 <= (_int(t.get("windows")) or 0) <= views and
            _int(t.get("set-view")) == (_int(t.get("windows")) or 0) * (_int(t.get("begin")) or 0)
            for t in ticks if (_int(t.get("begin")) or 0) > 0) and
            any(t.get("windows") == str(views) and (_int(t.get("requests")) or 0) > 0 for t in ticks),
        "bitmap_requests_registered": total["requests"] > 0,
        # (b) queue-end exactly once per frame, inside that frame's begin/end, never across ticks.
        "bitmap_queue_end_once_per_frame": total["queue-end"] == total["begin"] == total["end"],
        "bitmap_no_frame_open_at_tick": bool(ticks) and all(
            t.get("in-frame") == "0" and t.get("drain-pending") == "0" for t in ticks),
        "bitmap_end_status_ok": bool(ticks) and all(t.get("last-status") == "0" for t in ticks),
        # Dropped batches are fail-closed and counted; any drop means the bitmap evidence is incomplete.
        "bitmap_no_dropped_batches": bool(ticks) and ticks[-1].get("bitmap-frames-dropped") == "0",
        # (d) release with no leaked leases or readers; totals match the per-tick counters.
        "bitmap_released_no_leases": len(released) == 1 and rel.get("leases") == "0"
            and rel.get("readers") == "0" and rel.get("in-frame") == "0",
        "bitmap_release_totals_match": bool(released) and rel.get("requests-total") == str(total["requests"])
            and rel.get("begins-total") == str(total["begin"])
            and rel.get("queue-end-total") == str(total["queue-end"]),
    }
    return {
        "checks": checks,
        "totals": total,
        "release": rel,
        "reasons": [f"c3.9 bitmap check failed: {k}" for k, v in checks.items() if not v],
        "c3_9_qualified": all(checks.values()),
        "remaining_requirement": "Upload/draw of HUD bitmaps must be confirmed by reviewing the held captures; "
                                 "both emulator modes and all 1-4 view runs are required.",
    }


def _overflow_handled(final_frame: dict, last: dict) -> bool:
    """No overflow, or every overflowed build was counted per chain and refused (chain-refused > 0), and the last
    completed kick is the one before the newest kick or later (the FINISH of the overflowed frame was observed)."""
    overflow = _int(final_frame.get("overflow")) or 0
    if overflow == 0:
        return True
    ovf = [_int(x) or 0 for x in last.get("chain-overflow", "0,0,0,0").split(",")]
    ref = [_int(x) or 0 for x in last.get("chain-refused", "0,0,0,0").split(",")]
    kick = _int(last.get("kick-seq")) or 0
    done = _int(last.get("completed")) or 0
    return overflow <= sum(ovf) and sum(ref) > 0 and done >= kick - 1


def c3_10_dma_checks(lines: list[str], views: int, frames: int, captures: list | None = None) -> dict:
    """C3.10 DMA evidence from the guest log: the owner/chain layout at bind (c3-dma-owner), one c3-dma line per
    frame (per-chain kicks, emits, busy-emits, fence observations, pinned/released source generations,
    released-before-fence, overflow refusals, emit status histogram) and the c3-frame overflow counter.
    Captures are required here too: the run must hold at least two captures with a held render capture, and the
    per-view checks (kick per frame, view count) are evaluated per frame line."""
    owner = [fields_of(l) for l in lines if "c3-dma-owner " in l]
    frame_lines = [fields_of(l) for l in lines if "HALO_PS2_LOCAL c3-dma frame=" in l]
    cframe = [fields_of(l) for l in lines if "c3-frame kind=" in l]
    o = owner[-1] if owner else {}
    last = frame_lines[-1] if frame_lines else {}
    final_frame = cframe[-1] if cframe else {}
    owner_bytes = 1179648
    ob = _int(o.get("owner-base"), 16) if o else None
    g0 = o.get("geom0", "0x0/0").split("/") if o else ["0", "0"]
    g1 = o.get("geom1", "0x0/0").split("/") if o else ["0", "0"]
    u0 = o.get("up0", "0x0/0").split("/") if o else ["0", "0"]
    u1 = o.get("up1", "0x0/0").split("/") if o else ["0", "0"]
    chain_pairs = [g0, g1, u0, u1]
    chain_base = [_int(c[0], 16) or 0 for c in chain_pairs]
    chain_size = [_int(c[1]) or 0 for c in chain_pairs]
    contiguous = (chain_base[0] + chain_size[0] == chain_base[1] and
                  chain_base[1] + chain_size[1] == chain_base[2] and
                  chain_base[2] + chain_size[2] == chain_base[3])
    refusals = _int(last.get("overflow-refusals")) or 0
    checks = {
        "owner_line_present": bool(owner),
        "owner_cap_is_fixed": _int(o.get("owner-cap")) == owner_bytes and _int(o.get("storage-bytes")) == owner_bytes,
        "owner_sum_is_fixed": _int(o.get("sum")) == owner_bytes,
        # the storage is the first and only allocation in dma_commands: used == cap, storage at the owner base
        "owner_used_is_fixed": _int(o.get("owner-used")) == owner_bytes,
        "storage_is_owner_base": _int(o.get("storage-base"), 16) == ob and _int(o.get("storage-bytes")) == owner_bytes,
        "chain_sizes_match_layout": chain_size == [557056, 557056, 32768, 32768],
        "chains_contiguous_in_owner": bool(owner) and contiguous and ob is not None and
                                      chain_base[0] == ob and chain_base[0] + owner_bytes == chain_base[3] + chain_size[3],
        "frame_lines_complete": [_int(f.get("frame")) for f in frame_lines] == list(range(1, frames + 1)),
        "views_match": final_frame.get("views") == str(views),
        "no_busy_emits": last.get("c0-busy-emits") == "0" and last.get("c1-busy-emits") == "0",
        "no_idle_violations": final_frame.get("idle-violations") == "0",
        # every frame's kick is one submission: kick-seq equals the frame index (one bsp_render_kick per frame)
        "one_kick_per_frame": bool(frame_lines) and all(
            _int(f.get("kick-seq")) == _int(f.get("frame")) for f in frame_lines),
        # real fence observations on both geometry chains and both upload chains (observed, not assumed)
        "fence_observed_geometry": all(
            any(f.get(f"c{i}-fence") == "1" for f in frame_lines) for i in (0, 1)),
        "fence_observed_upload": all(
            any(f.get(f"up{i}-fence") == "1" for f in frame_lines) for i in (0, 1)),
        "released_before_fence_zero": bool(frame_lines) and all(f.get("released-before-fence") == "0" for f in frame_lines),
        # each chain must have been released at least once (reuse) and every release event must carry a fence read
        "chain_release_observed": bool(frame_lines) and (_int(last.get("src-rel-chain", "0/0").split("/")[0]) or 0) > 0,
        "both_geometry_chains_submitted": all((_int(last.get(f"c{i}-kicks")) or 0) > 0 for i in (0, 1)),
        "both_geometry_chains_released": all(
            (_int(last.get(f"geom-rel{i}", "0/0").split("/")[0]) or 0) > 0 for i in (0, 1)),
        "both_upload_chains_submitted": all((_int(last.get(f"up{i}-kicks")) or 0) > 0 for i in (0, 1)),
        "both_upload_chains_released": all((_int(last.get(f"up{i}-releases")) or 0) > 0 for i in (0, 1)),
        "per_chain_releases_fenced": bool(frame_lines) and all(
            f.get(f"up{i}-before") == "0" and f.get(f"geom-rel{i}", "").split("/")[-1] == "0"
            for f in frame_lines for i in (0, 1)),
        "object_pin_releases_observed": (_int(last.get("src-rel-pin", "0/0").split("/")[0]) or 0) > 0,
        "bitmap_lease_releases_observed": (_int(last.get("src-rel-bitmap", "0/0").split("/")[0]) or 0) > 0,
        # overflow is either absent or counted per chain at the refusal point, and the frame still fenced
        "overflow_counted_and_fenced": _overflow_handled(final_frame, last),
        # captures: the run must hold its two captures, one of them the held render capture
        "captures_present": bool(captures) and len(captures) >= 2 and any(
            "c3-render-held" in c.get("marker", "") for c in captures),
        "emit_failures_zero": final_frame.get("emit-failures") == "0",
    }
    reasons = [f"c3.10 dma check failed: {k}" for k, v in checks.items() if not v]
    return {
        "checks": checks,
        "views": views,
        "frames": frames,
        "owner": o,
        "last_frame": last,
        "reasons": reasons,
        "c3_10_qualified": all(checks.values()),
    }


def run_row(row: str, package_root_override: Path | None = None, cycles: int = 1, ticks: int = 0,
            render_views: int = 0, render_frames: int = 300, workload_players: int = 0) -> dict:
    if OUTPUT_ROOT is not None:
        out = OUTPUT_ROOT / row
    elif render_views:
        out = RENDER_ROOT / f"v{render_views}" / row
    else:
        out = (RESULT_ROOT if cycles == 1 and not ticks else REUSE_ROOT) / row
    out.mkdir(parents=True, exist_ok=True)
    started = time.time()
    result: dict = {"row": row, "pass": False, "reasons": [], "started_unix": int(started),
                    "cycles": cycles, "ticks": ticks}
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
        elf, why = link_row(row, package_root, out, cycles, ticks, None, render_views, render_frames,
                            workload_players=workload_players)
        if elf is None:
            raise RuntimeError(why)
        result["elf"] = str(elf.relative_to(ROOT))
        guest_attempt_started_ns = time.time_ns()
        ok, why = guest_row(row, elf, plan, out, capture_markers=(
            [f"c3-frame kind=periodic frame={render_frames // 2 // 30 * 30} ", "c3-render-held "]
            if render_views else ()))
        if not ok:
            raise RuntimeError(why)
        guest_run, provenance_error = validate_guest_provenance(
            out, guest_attempt_started_ns, EMU_MODE,
            expected_captures=2 if render_views else 0)
        if guest_run is None:
            raise RuntimeError(provenance_error)
        result["guest_launch_id"] = guest_run["launch_id"]
        log_path = out / "guest/runs/partition-selected/halo_ps2_local.txt"
        lines = read_guest_lines(log_path)
        result["guest_log"] = str(log_path.relative_to(ROOT))
        result["guest_line_count"] = len(lines)
        parsed = parse_guest_log(lines, row, plan["map"])
        result.update(parsed)
        if (cycles != 1 or ticks) and not render_views:
            multi = parse_cycles(lines, plan["map"], cycles, ticks)
            result["cycle_checks"] = multi
            parsed = {**parsed, "failing_checks": parsed["failing_checks"] + multi["failing_checks"]}
            result["failing_checks"] = parsed["failing_checks"]
            result["reasons"].extend(multi["reasons"])
        if render_views:
            rc = render_checks(lines, render_views, render_frames)
            result["render"] = {"views": render_views, "frames": render_frames, **rc}
            c37 = c3_7_texfence_checks(lines, render_views, render_frames, TEXFENCE_CAP_PAGES)
            result["c3_7"] = c37
            result["c3_7_qualified"] = c37["qualified"]
            result["failing_checks"] = parsed["failing_checks"] + [k for k, v in rc["checks"].items() if not v]
            parsed = {**parsed, "failing_checks": result["failing_checks"]}
            result["reasons"].extend(rc["reasons"])
            if workload_players:
                # C3.3 presence: scene qualification is separate from the render pass verdict.
                result["c3_3"] = c3_3_scene_checks(lines, render_views, workload_players)
                result["c3_3_qualified"] = result["c3_3"]["c3_3_qualified"]
            result["captures"] = guest_run.get("captures", [])
            # C3.5 layout: geometry of the split views and the unused 3-view quadrant (pixel checks).
            layout = c3_5_layout_checks(render_views, [c.get("file", "") for c in result["captures"]
                                                        if "c3-render-held" in c.get("marker", "")],
                                        game_size=c3_5_game_size(result["captures"]))
            result["layout"] = layout
            result["failing_checks"] = result["failing_checks"] + [k for k, v in layout["checks"].items() if not v]
            result["reasons"].extend(layout["reasons"])
            # C3.9 bitmap registration, per-frame queue ends and release (counters, not pixels).
            c39 = c3_9_bitmap_checks(lines, render_views)
            result["c3_9"] = c39
            # C3.10 DMA ownership, idle chains, source release and overflow (per-frame c3-dma lines).
            c310 = c3_10_dma_checks(lines, render_views, render_frames, guest_run.get("captures", []))
            result["c3_10"] = c310
            result["failing_checks"] = result["failing_checks"] + [k for k, v in c310["checks"].items() if not v]
            result["reasons"].extend(c310["reasons"])
            result["failing_checks"] = result["failing_checks"] + [k for k, v in c39["checks"].items() if not v]
            result["reasons"].extend(c39["reasons"])
            # C3.2 parent contract: cameras, snapshot sequence and object source come from the CE bank only.
            c32 = c3_2_contract_checks(lines, render_views)
            result["c3_2"] = c32
            result["failing_checks"] = result["failing_checks"] + [k for k, v in c32["checks"].items() if not v]
            result["reasons"].extend(c32["reasons"])
            # A held capture must show the game, not a black frame (C3 capture reliability).
            held = [c for c in result["captures"] if "c3-render-held" in c.get("marker", "")]
            held_fraction = held[0].get("nonblack_fraction") if held else None
            result["capture_nonblack_fraction"] = held_fraction
            if held_fraction is None or held_fraction < 0.01:
                result["failing_checks"] = [*result["failing_checks"], "held_capture_nonblack"]
                parsed = {**parsed, "failing_checks": result["failing_checks"]}
                result["reasons"].append(f"held capture is black (non-black fraction {held_fraction})")
            if not held or not capture_has_scene_variation(held[0]):
                result["failing_checks"] = [*result["failing_checks"], "held_capture_scene_variation"]
                parsed = {**parsed, "failing_checks": result["failing_checks"]}
                result["reasons"].append("held capture lacks scene variation (clear color or HUD alone cannot qualify)")
        run_config = guest_run.get("pcsx2_config", {})
        result["emu_mode_verified"] = run_config.get("emu_mode_verified")
        if not run_config.get("emu_mode_verified"):
            result["failing_checks"] = [*result["failing_checks"], "emu_mode_not_verified"]
            parsed = {**parsed, "failing_checks": result["failing_checks"]}
            result["reasons"].append(f"PCSX2 {EMU_MODE} mode was not verified")
        result["ce_failure_lines"] = ce_failure_lines(out / "guest/runs/partition-selected/emu.txt")
        if parsed["failing_checks"] and result["ce_failure_lines"]:
            result["reasons"].append("CE reported: " + " | ".join(result["ce_failure_lines"][:2]))
        result["pass"] = bool(ok and not parsed["failing_checks"])
    except Exception as error:  # record and keep the matrix moving
        result["reasons"].append(f"{type(error).__name__}: {error}")
        result["pass"] = False
    result["elapsed_seconds"] = round(time.time() - started, 1)
    (out / "result.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    return result


def guest_fault_lines(path: Path, limit: int = 5) -> list[str]:
    """The guest's own failure lines ([err], HALO_PS2_FAIL), so a run reports its real cause."""
    if not path.is_file():
        return []
    text = path.read_text(errors="replace").splitlines()
    return [line.strip() for line in text if "[err]" in line or "HALO_PS2_FAIL" in line][:limit]


def successor_stage_paths(plan: dict, succ_plan: dict, succ_row: str, succ_root: Path) -> list[str]:
    """Repo-relative files the guest must reach beyond the selected row's tree and retail maps."""
    paths = [*plan["stage_paths"], *succ_plan["stage_paths"]]
    hcp = (succ_root / succ_row / f"{succ_row}.hcp").resolve().relative_to(ROOT).as_posix()
    if not hcp.startswith(plan["guest_package_root"].rstrip("/") + "/"):
        paths.append(hcp)
    return list(dict.fromkeys(paths))


def rendered_successor_checks(lines: list[str], old_map: str, new_map: str, mode: int,
                               views: int, captures: list[dict]) -> dict:
    """Ordered rendered-replacement checks for one guest log (C3.11 diagnostics).

    The renderer markers come from hcu_main.c (c3-render-*, c3-frame) and hcu_map_service.c
    (map-replacement). The step markers come from CE (production-ce-successor-step). A pass
    here is necessary but not sufficient: C3.11 stays open until both emulator modes pass on
    the exact executable/package tuple and in-flight uploads/draws are observed.
    """
    def indexed(prefix: str):
        return [(index, fields_of(line)) for index, line in enumerate(lines) if line.startswith(PREFIX + prefix)]

    ready = indexed("c3-render-ready ")
    frames = [index for index, _ in indexed("c3-frame ")]
    held = [index for index, _ in indexed("c3-render-held ")]
    boundaries = indexed("map-replacement ")
    begin = [(i, r) for i, r in boundaries if r.get("phase") == "quiesce-begin"]
    validated = [(i, r) for i, r in boundaries if r.get("phase") == "candidate-validated"]
    drained = [(i, r) for i, r in boundaries if r.get("phase") == "quiesce-end"]
    quiesce = indexed("c3-render-quiesce ")
    observations = indexed("c3-replacement-boundary ")
    before = [(i, r) for i, r in observations if r.get("phase") == "before-preflight"]
    rejected_observations = [(i, r) for i, r in observations if r.get("phase") == "after-preflight-rejected"]
    after_drain = [(i, r) for i, r in observations if r.get("phase") == "after-drain"]
    steps = [(index, fields_of(line)) for index, line in enumerate(lines)
             if line.startswith(PREFIX + "production-ce-successor-step ")]
    usable = [index for index, line in enumerate(lines) if line.startswith(PREFIX + "production-ce-successor-usable result=1 ")]
    usable_rows = [(index, fields_of(line)) for index, line in enumerate(lines)
                   if line.startswith(PREFIX + "production-ce-successor-usable result=1 ")]
    begin_lines = [fields_of(line) for line in lines if line.startswith(PREFIX + "production-ce-successor-begin ")]
    begin_fields = begin_lines[0] if begin_lines else {}
    # The parent's map-released boundary (hcu_profile_mount unload through the map service) is the owner release.
    released = [index for index, line in enumerate(lines)
                if line.startswith(PREFIX + "m2-cycle-boundary ") and fields_of(line).get("phase") == "map-released"]
    retry_markers = [index for index, line in enumerate(lines)
                     if line.startswith(PREFIX + "production-ce-successor-retry ")]
    failed_preflight = [i for i, r in steps if r.get("step") == "after-failed-preflight"]
    failed_load = [i for i, r in steps if r.get("step") == "after-failed-load"]
    dispose = [(i, r) for i, r in steps if r.get("step") == "dispose"]
    unload = [(i, r) for i, r in steps if r.get("step") == "unload"]
    loads = [(i, r) for i, r in steps if r.get("step") == "load"]
    new_ready = [i for i, r in ready if r.get("map") == new_map]
    expected_maps = [old_map] if mode == 2 else [old_map, new_map]

    def window_quiesce(lo: int, hi: int) -> bool:
        return any(lo < i < hi and q.get("result") == "1" and q.get("readers") == "0" and
                   q.get("fence") == "1" and (_int(q.get("kick-seq")) or 0) > 0 for i, q in quiesce)

    def captured_visible(capture: dict) -> bool:
        return capture_has_scene_variation(capture)

    checks = {
        "rendered_maps": [row.get("map") for _, row in ready] == expected_maps,
        "rendered_view_counts": bool(ready) and all(row.get("views") == str(views) for _, row in ready),
        "render_failure_free": not any("HALO_PS2_FAIL c3-" in line for line in lines),
        "replacement_captures_visible": len(captures) == 2 and all(captured_visible(c) for c in captures),
        "capture_order_map_a_then_map_b": len(captures) == 2 and
            str(captures[0].get("marker", "")).startswith("c3-render-held") and
            str(captures[1].get("marker", "")).startswith("production-ce-successor-usable"),
        "preflight_started_with_live_submission": bool(before) and any(
            r.get("inflight") == "1" and r.get("fence") == "0" and
            (_int(r.get("kick-seq")) or 0) > 0 and (_int(r.get("map-generation")) or 0) > 0 and
            (_int(r.get("service-readers")) or 0) > 0 and r.get("world-bound") == "1" and
            r.get("media-loaded") == "1" and r.get("object-pin-live") == "1"
            for _, r in before),
    }
    if mode == 2:
        checks["failed_preflight_preserves_renderer"] = (
            not begin and not validated and not drained and not quiesce and
            bool(failed_preflight) and bool(rejected_observations) and
            any(i > rejected_observations[0][0] for i in frames) and
            len(ready) == 1)
        checks["failed_preflight_no_quiesce_or_dispose"] = not begin and not dispose and not unload
        # The rejected successor leaves the old owner's tag/BSP bytes and mount exactly as begin reported them.
        checks["failed_preflight_owner_unchanged"] = bool(rejected_observations) and bool(begin_fields) and any(
            si > rejected_observations[0][0] and r.get("result") == "1" and r.get("old-mounted") == "1" and
            r.get("new-mounted") == "0" and r.get("tag-bytes") == begin_fields.get("old-tag-bytes") and
            r.get("bsp-bytes") == begin_fields.get("old-bsp-bytes")
            for si, r in steps if r.get("step") == "after-failed-preflight")
        # After the rejection the old map is still usable and rendering: a usable marker for it follows.
        checks["failed_preflight_old_map_usable"] = bool(rejected_observations) and any(
            ui > rejected_observations[0][0] and r.get("old") == old_map and r.get("new") is None
            for ui, r in usable_rows) and any(i > rejected_observations[0][0] for i in frames)
        checks["failed_preflight_preserves_source_identity"] = any(
            bi < ri and all(b.get(k) == r.get(k) for k in
                ("map-generation", "kick-seq", "service-readers", "world-bound", "media-loaded", "object-pin-live"))
            for bi, b in before for ri, r in rejected_observations)
        return {"checks": checks,
                "reasons": [f"rendered successor check failed: {name}" for name, passed in checks.items() if not passed],
                "c3_11_qualified": False,
                "remaining_requirement": "Verify actual in-flight uploads/draw source references and both emulator modes on the exact tuple."}
    checks["readers_held_while_drawing"] = bool(begin) and any(
        r.get("old") == old_map and (_int(r.get("readers")) or 0) > 0 and any(f < bi for f in frames)
        for bi, r in begin)
    checks["drain_releases_real_submission_sources"] = any(
        bi < ai and b.get("map-generation") == a.get("map-generation") and
        b.get("kick-seq") == a.get("kick-seq") and a.get("fence") == "1" and
        a.get("inflight") == "0" and a.get("service-readers") == "0" and
        a.get("object-pin-live") == "0" and a.get("bitmap-leases") == "0"
        for bi, b in before for ai, a in after_drain)
    checks["candidate_before_quiesce"] = bool(begin) and all(
        any(vi < bi and v.get("new") == r.get("new") for vi, v in validated) for bi, r in begin)
    checks["drain_readers_zero_fence_observed"] = bool(begin) and bool(drained) and all(
        window_quiesce(bi, ei) and e.get("drained") == "1" and e.get("readers") == "0"
        for bi, _ in begin for ei, e in drained if ei > bi)
    checks["ce_dispose_with_old_tags_live"] = bool(dispose) and any(
        d.get("result") == "1" and d.get("old") == old_map and d.get("old-mounted") == "1" and
        (_int(d.get("tag-bytes")) or 0) > 0 and (_int(d.get("bsp-bytes")) or 0) > 0 and
        bool(begin) and any(bi < di for bi, _ in begin) and
        any(ei < di for ei, _ in drained)
        for di, d in dispose)
    checks["release_before_successor_load"] = bool(unload) and bool(loads) and any(
        u.get("result") == "1" and u.get("old-mounted") == "0" and
        any(li > ui and l.get("result") == "1" and l.get("new-mounted") == "1" for li, l in loads) and
        any(ui > di for di, _ in dispose)
        for ui, u in unload)
    # The old owner is released by the parent (map-released) after CE dispose and before the successor load, and the
    # unload step proves zero tag/BSP bytes remain: a blocked unpublish (profile-unload blocked) fails here.
    checks["old_owner_unpublished_zero_bytes"] = any(
        u.get("result") == "1" and u.get("old-mounted") == "0" and u.get("tag-bytes") == "0" and
        u.get("bsp-bytes") == "0" for _, u in unload)
    checks["parent_release_between_dispose_and_unload"] = any(
        di < ri < ui for di, _ in dispose for ri in released for ui, u in unload if u.get("result") == "1")
    if mode == 3:
        checks["late_failure_empty_then_retry"] = bool(failed_load) and any(
            li > failed_load[0] for li, l in loads if l.get("result") == "1") and bool(new_ready)
        # The failed load leaves CE with no map and zero owner bytes; the retry marker follows it.
        checks["late_failure_empty_state"] = any(
            r.get("result") == "1" and r.get("old-mounted") == "0" and r.get("new-mounted") == "0" and
            r.get("tag-bytes") == "0" and r.get("bsp-bytes") == "0"
            for i, r in steps if r.get("step") == "after-failed-load")
        retry_windows = [(fi, li) for fi in failed_load for li, l in loads
                         if li > fi and l.get("result") == "1"]
        first_retry = min(retry_windows, key=lambda w: w[1]) if retry_windows else None
        checks["late_failure_retry_marker_then_load"] = first_retry is not None and any(
            first_retry[0] < ri < first_retry[1] for ri in retry_markers)
        # Nothing is published, drawn or usable between the failed load and the successful retry.
        checks["late_failure_no_render_while_empty"] = first_retry is not None and not any(
            first_retry[0] < i < first_retry[1] for i, _ in ready) and not any(
            first_retry[0] < i < first_retry[1] for i in frames) and not any(
            first_retry[0] < i < first_retry[1] for i in usable)
    checks["successor_frames_render"] = bool(new_ready) and any(i > new_ready[-1] for i in frames) and bool(usable)
    return {"checks": checks,
            "reasons": [f"rendered successor check failed: {name}" for name, passed in checks.items() if not passed],
            "c3_11_qualified": False,
            "remaining_requirement": "Verify actual in-flight uploads/draw source references and both emulator modes on the exact tuple."}


def run_successor(row: str, succ_row: str, fault: str = "none", ticks: int = SUCCESSOR_TICKS,
                  *, package_root_override: Path | None = None, render_views: int = 0,
                  render_frames: int = 300, workload_players: int = 0) -> dict:
    """Link and run one guest successor sequence; results go to build/m2-c2-foreign/<row>/<succ>-<case>/.

    The selected row's map A is loaded by the production path; CE then runs the successor
    transaction for succ_row's map B (see HALO_PS2_C2_SUCCESSOR_MODE in the CE main.c).
    Never touches build/m2-c2-matrix/summary.json.
    """
    mode, label = SUCCESSOR_CASES[fault]
    root = OUTPUT_ROOT if OUTPUT_ROOT is not None else (
        C3_ROOT.parent / "replacement" if render_views else FOREIGN_ROOT)
    out = root / row / f"{succ_row}-{label}"
    out.mkdir(parents=True, exist_ok=True)
    started = time.time()
    result: dict = {"row": row, "successor_row": succ_row, "successor_fault": fault, "mode": mode,
                    "case": label, "pass": False, "reasons": [], "started_unix": int(started),
                    "ticks": ticks}
    (out / "result.json").write_text(json.dumps({**result, "state": "running"}, indent=2) + "\n")
    try:
        if row == succ_row:
            raise RuntimeError("the successor row must differ from the selected row")
        package_root = package_root_override or package_root_for(row)
        succ_root = package_root_override or package_root_for(succ_row)
        if package_root is None or succ_root is None:
            raise RuntimeError(f"no selected package for {row if package_root is None else succ_row}")
        plan = stage_plan(row, package_root)
        succ_plan = stage_plan(succ_row, succ_root)
        if plan["map"] == succ_plan["map"]:
            raise RuntimeError(f"{row} and {succ_row} are both map {plan['map']}; a foreign successor needs a different map")
        result.update({"map": plan["map"], "successor_map": succ_plan["map"], "scenario": plan["scenario"],
                       "successor_scenario": succ_plan["scenario"], "package_root": str(package_root),
                       "successor_package_root": str(succ_root)})
        header = subprocess.run(
            [sys.executable, "-I", str(ROOT / "tools/c2_profile_image_header.py"), "--row", row,
             "--package-root", str(package_root), "--output", str(out / f"{row}.h")],
            cwd=ROOT, capture_output=True, text=True)
        if header.returncode:
            raise RuntimeError(f"row header failed: {header.stderr.strip()}")
        include_dir = write_successor_includes(out, succ_row, succ_root, mode, ticks)
        elf, why = link_row(row, package_root, out, include_dir=include_dir,
                            ticks=render_frames + 5 if render_views else 0,
                            render_views=render_views, render_frames=render_frames,
                            workload_players=workload_players)
        if elf is None:
            raise RuntimeError(why)
        result["elf"] = str(elf.relative_to(ROOT))
        attempt_started_ns = time.time_ns()
        ok, why = guest_row(row, elf, plan, out, SUCCESSOR_GUEST_TIMEOUT, SUCCESSOR_PROCESS_TIMEOUT,
                            successor_stage_paths(plan, succ_plan, succ_row, succ_root),
                            released_map=plan["map"] if mode == 2 else succ_plan["map"],
                            capture_markers=("c3-render-held ", "production-ce-successor-usable result=1 ")
                            if render_views else ())
        if not ok:
            raise RuntimeError(why)
        guest_run, provenance_error = validate_guest_provenance(
            out, attempt_started_ns, EMU_MODE, expected_captures=2 if render_views else 0)
        if guest_run is None:
            faults = guest_fault_lines(out / "guest/runs/partition-selected/halo_ps2_local.txt")
            detail = f" (guest fault: {' | '.join(faults[:2])})" if faults else ""
            raise RuntimeError(provenance_error + detail)
        result["guest_launch_id"] = guest_run["launch_id"]
        result["emu_mode_verified"] = guest_run["pcsx2_config"]["emu_mode_verified"]
        log_path = out / "guest/runs/partition-selected/halo_ps2_local.txt"
        lines = read_guest_lines(log_path)
        result["guest_log"] = str(log_path.relative_to(ROOT))
        result["guest_line_count"] = len(lines)
        parsed = parse_successor_log(lines, row, plan["map"], succ_row, succ_plan["map"], mode, ticks)
        result.update(parsed)
        if render_views:
            result["captures"] = guest_run.get("captures", [])
            checks = rendered_successor_checks(lines, plan["map"], succ_plan["map"], mode,
                                                render_views, result["captures"])
            result["render_replacement"] = checks
            result["failing_checks"] += [name for name, passed in checks["checks"].items() if not passed]
            result["reasons"] += checks["reasons"]
        result["ce_failure_lines"] = ce_failure_lines(out / "guest/runs/partition-selected/emu.txt")
        if result["failing_checks"] and result["ce_failure_lines"]:
            result["reasons"].append("CE reported: " + " | ".join(result["ce_failure_lines"][:2]))
        if not ok:
            result["reasons"].insert(0, why)
        result["pass"] = bool(ok and not result["failing_checks"])
    except Exception as error:  # record the failure
        result["reasons"].append(f"{type(error).__name__}: {error}")
        result["pass"] = False
    result["elapsed_seconds"] = round(time.time() - started, 1)
    (out / "result.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    return result


def write_summary(updated: list[dict] | None = None) -> None:
    """Rebuild build/m2-c2-matrix/summary.json from every per-row result.json under the matrix directory.

    A --rows run passes only its own results; they replace those rows' entries and every other row comes
    from its result.json, so a partial run never shrinks the summary."""
    entries: dict[str, dict] = {}
    for path in sorted(MATRIX.glob("*/result.json")):
        try:
            data = json.loads(path.read_text())
        except (OSError, ValueError):
            continue
        if data.get("state") == "running" or "row" not in data:
            continue
        entries[data["row"]] = {"row": data["row"], "pass": data.get("pass") is True,
                                "reasons": data.get("reasons", [])[:3]}
    for r in updated or []:
        entries[r["row"]] = {"row": r["row"], "pass": r["pass"], "reasons": r["reasons"][:3]}
    MATRIX.mkdir(parents=True, exist_ok=True)
    order = profile_rows()
    rows = sorted(entries.values(), key=lambda e: (order.index(e["row"]) if e["row"] in order else len(order), e["row"]))
    (MATRIX / "summary.json").write_text(json.dumps({"rows": rows}, indent=2) + "\n")


def previously_passed(row: str) -> bool:
    path = MATRIX / row / "result.json"
    try:
        return json.loads(path.read_text()).get("pass") is True
    except (OSError, ValueError):
        return False


def main(argv=None) -> int:
    global RESULT_ROOT, OUTPUT_ROOT
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--rows", help="comma-separated row names (default: every row with a selected package)")
    parser.add_argument("--jobs-link", type=int, default=1,
                        help=("link concurrency; links always take the shared parent-link lock because every link "
                              "rewrites the common HCU closure directory, so they stay serialized"))
    parser.add_argument("--cycles", type=int, default=1,
                        help=("load/map-loaded/release cycles the guest repeats (default 1); above 1 every cycle must "
                              "pass and storage must be reused; results go to build/m2-c2-gaps-reuse/<row>"))
    parser.add_argument("--ticks", type=int, default=0,
                        help="in-map CE ticks to run per cycle (default 0)")
    parser.add_argument("--skip-existing", action="store_true", help="skip rows whose result.json already passed")
    parser.add_argument("--c3", action="store_true",
                        help=("run the opt-in HCU_C3=1 variant: closure, link and guest use the C3 flags and results "
                              "go to build/c3/integrate/<row>/; summary.json is not written"))
    parser.add_argument("--render-views", type=int, choices=(1, 2, 3, 4), default=0,
                        help=("with --c3: build the C3 render loop (hcu_main.c C3:render block) for N views, run it in "
                              "PCSX2 with framebuffer captures; results go to build/c3/render-loop/v<N>/<row>/"))
    parser.add_argument("--render-frames", type=int, default=300,
                        help="frames the render loop draws with --render-views (default %(default)s; must be a multiple of 30)")
    parser.add_argument("--texfence-cap-pages", type=int, default=0, metavar="N",
                        help="C3.7 debug: cap the texture cache at N pages to force slot reuse (default 0 = off)")
    parser.add_argument("--output-root", type=Path, metavar="DIR",
                        help=("write each row's results to DIR/<row>/ instead of the default root (build/c3/integrate, "
                              "build/c3/render-loop/v<N>, build/m2-c2-gaps-reuse, ...); default unchanged"))
    parser.add_argument("--c3-workload", choices=("none", "4p4bot"), default="none",
                        help=("with --c3: 4p4bot starts 4 local players (CE's player_spawn_count, the split-screen path) "
                              "on the first map load; no bots are spawned because stock CE has no bot path"))
    parser.add_argument("--c3-local-players", type=int, choices=(1, 2, 3, 4),
                        help="explicit CE local player population for C3 render qualification")
    parser.add_argument("--package-root", type=Path,
                        help=("override the selected package root (<root>/<row>/<row>.hcp + .json); with --render-views the "
                              "default is the C3 render package tree build/c3/render-tree/pkg"))
    parser.add_argument("--successor", metavar="ROW",
                        help=("run the guest successor sequence on the one --rows row: after its map loads, replace it with "
                              "ROW's map through the real map service; results go to build/m2-c2-foreign/<row>/"))
    parser.add_argument("--successor-fault", choices=sorted(SUCCESSOR_CASES), default="none",
                        help=("none: foreign replacement; preflight: the successor's preflight fails and the old map must stay "
                              "mounted and usable; load: the successor's first load fails after the old owner is released, "
                              "then a retry loads"))
    parser.add_argument("--successor-ticks", type=int, default=SUCCESSOR_TICKS,
                        help="in-map CE ticks run on the surviving map (default %(default)s)")
    parser.add_argument("--emu-mode", choices=("interpreter", "recompiler"), default="interpreter",
                        help=("PCSX2 execution for every guest run: interpreter (default) or recompiler "
                              "(EnableEE/IOP/VU0/VU1 = true in each run's PCSX2.ini)"))
    args = parser.parse_args(argv)
    global EMU_MODE
    EMU_MODE = args.emu_mode
    if args.output_root is not None:
        OUTPUT_ROOT = (ROOT / args.output_root if not args.output_root.is_absolute() else args.output_root).resolve()
    global TEXFENCE_CAP_PAGES
    if args.texfence_cap_pages < 0 or args.texfence_cap_pages > 4096:
        parser.error("--texfence-cap-pages must be 0..4096")
    TEXFENCE_CAP_PAGES = args.texfence_cap_pages
    if args.render_views and not args.c3:
        parser.error("--render-views needs --c3")
    if args.render_views and (args.render_frames < 30 or args.render_frames % 30):
        parser.error("--render-frames must be a positive multiple of 30")
    if args.c3_workload != "none" and not args.c3:
        parser.error("--c3-workload needs --c3")
    if args.c3_local_players is not None and (not args.c3 or args.c3_workload != "none"):
        parser.error("--c3-local-players requires --c3 and cannot be combined with --c3-workload")
    workload_players = args.c3_local_players or WORKLOAD_PLAYERS[args.c3_workload]
    if args.package_root and not args.c3:
        parser.error("--package-root needs --c3")
    if args.successor:
        if not args.rows or "," in args.rows:
            parser.error("--successor needs exactly one --rows row")
        if args.cycles != 1 or args.ticks or args.skip_existing:
            parser.error("--successor cannot be combined with --cycles, --ticks or --skip-existing")
        if args.successor_ticks < 1:
            parser.error("--successor-ticks must be at least 1")
        known = profile_rows()
        if args.rows not in known or args.successor not in known:
            parser.error(f"--rows and --successor must be rows in {PROFILE_SOURCE.name}")
        if args.c3:
            if not args.render_views:
                parser.error("--c3 --successor requires --render-views for a live renderer consumer")
            os.environ["HCU_C3"] = "1"
            args.package_root = args.package_root or prepare_render_tree()
            result = run_successor(args.rows, args.successor, args.successor_fault,
                                   args.successor_ticks, package_root_override=args.package_root,
                                   render_views=args.render_views, render_frames=args.render_frames,
                                   workload_players=workload_players)
        else:
            result = run_successor(args.rows, args.successor, args.successor_fault, args.successor_ticks)
        print(f"{args.rows} -> {args.successor} [{result['case']}]: {'PASS' if result['pass'] else 'FAIL'} "
              f"{'; '.join(result['reasons'][:2])}", flush=True)
        return 0 if result["pass"] else 1
    if args.successor_fault != "none" or args.successor_ticks != SUCCESSOR_TICKS:
        parser.error("--successor-fault and --successor-ticks need --successor")
    rows = [r for r in (args.rows.split(",") if args.rows else default_rows()) if r]
    unknown = [r for r in rows if r not in profile_rows()]
    if unknown:
        parser.error(f"rows not in {PROFILE_SOURCE.name}: {', '.join(unknown)}")
    if args.cycles < 1 or args.ticks < 0:
        parser.error("--cycles must be at least 1 and --ticks at least 0")
    if args.jobs_link < 1:
        parser.error("--jobs-link must be at least 1")
    if args.render_views and not args.c3:
        parser.error("--render-views needs --c3")
    if args.render_views:
        if args.render_frames < 30 or args.render_frames % 30:
            parser.error("--render-frames must be a positive multiple of 30")
        if args.cycles != 1 or args.ticks or args.skip_existing:
            parser.error("--render-views sets its own tick count (frames + 5); do not pass --cycles/--ticks/--skip-existing")
        if not args.package_root:
            args.package_root = prepare_render_tree()
    if args.c3_workload != "none" and not args.c3:
        parser.error("--c3-workload needs --c3")
    if args.package_root and not args.c3:
        parser.error("--package-root needs --c3")
    if args.c3:
        if (args.cycles != 1 or args.ticks) and not args.render_views:
            parser.error("--c3 runs the default single-cycle rows only")
        # Every subprocess (closure, link probe, guest runner) inherits HCU_C3=1.
        os.environ["HCU_C3"] = "1"
        RESULT_ROOT = C3_ROOT
    summary = []
    for row in rows:
        if args.skip_existing and previously_passed(row):
            print(f"{row}: skipped (previous pass)")
            continue
        result = run_row(row, args.package_root, cycles=args.cycles,
                         workload_players=workload_players,
                         ticks=(args.render_frames + 5) if args.render_views else args.ticks,
                         render_views=args.render_views, render_frames=args.render_frames)
        summary.append(result)
        print(f"{row}: {'PASS' if result['pass'] else 'FAIL'} {'; '.join(result['reasons'][:2])}", flush=True)
    if args.cycles != 1 or args.ticks or args.render_views:
        return 0 if all(r["pass"] for r in summary) else 1
    if args.c3:
        return 0 if all(r["pass"] for r in summary) else 1
    write_summary(summary)
    return 0 if all(r["pass"] for r in summary) else 1


if __name__ == "__main__":
    sys.exit(main())
