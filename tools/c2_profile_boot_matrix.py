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
             render_frames: int = 300) -> tuple[Path | None, str]:
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
            f"#define HCU_C3_RENDER_FRAMES {render_frames}\n")
        include_dirs.append(str(render_dir))
    if include_dir is not None:
        include_dirs.append(str(include_dir))
    if include_dirs:
        env = dict(os.environ, C_INCLUDE_PATH=":".join(include_dirs))
    with LINK_LOCK.open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        rc, timed_out = run_group(command, log=out / "link.log", timeout=LINK_TIMEOUT, env=env)
    elf = link_dir / f"hcu-gameplay-machine-partition-{row}-headless-runtime-guest.elf"
    if timed_out:
        return None, f"link timed out after {LINK_TIMEOUT}s"
    if rc or not elf.is_file():
        return None, f"link failed (exit {rc}); see {out / 'link.log'}"
    return elf, ""


def guest_row(row: str, elf: Path, plan: dict, out: Path, timeout: int = GUEST_TIMEOUT,
              process_timeout: int = GUEST_PROCESS_TIMEOUT, extra_stage_paths=(),
              released_map: str | None = None, capture_markers=()) -> tuple[bool, str]:
    command = [sys.executable, "-I", str(ROOT / "tools/c2_guest_run.py"),
               "--timeout", str(timeout), "--output-dir", str(out / "guest"),
               "--production-elf", str(elf), "--package-tree", str(plan["package_tree"]),
               "--guest-package-root", plan["guest_package_root"],
               "--production-row", row, "--production-map", plan["map"],
               "--production-profile-id", str(plan["profile_id"])]
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


def prepare_render_tree() -> Path:
    """Stage build/c3/render-tree/pkg from build/c3/render-packages.

    The HCP is symlinked unchanged (its SHA-256 pin is still checked by the guest runner). The render-media
    producer left memory.package_file_bytes at the pre-render-chunk size, so the staged manifest copy carries the
    HCP's real size, as tools/repack_hcu_profiles_hcp2.py does for a re-enveloped package; nothing else changes."""
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
            data["memory"]["package_file_bytes_before_render_stage"] = data["memory"]["package_file_bytes"]
            data["memory"]["package_file_bytes"] = real
        (out / manifest.name).write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return pkg


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
        # a 3-view frame also submits the unused-quadrant clear as a fourth renderer view
        "render_views": ff.get("views") == str(views + (1 if views == 3 else 0)),
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


def run_row(row: str, package_root_override: Path | None = None, cycles: int = 1, ticks: int = 0,
            render_views: int = 0, render_frames: int = 300) -> dict:
    if render_views:
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
        elf, why = link_row(row, package_root, out, cycles, ticks, None, render_views, render_frames)
        if elf is None:
            raise RuntimeError(why)
        result["elf"] = str(elf.relative_to(ROOT))
        ok, why = guest_row(row, elf, plan, out, capture_markers=(
            [f"c3-frame kind=periodic frame={render_frames // 2 // 30 * 30} ", "c3-render-held "]
            if render_views else ()))
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
            result["failing_checks"] = parsed["failing_checks"] + [k for k, v in rc["checks"].items() if not v]
            parsed = {**parsed, "failing_checks": result["failing_checks"]}
            result["reasons"].extend(rc["reasons"])
            result["captures"] = json.loads(
                (out / "guest/manifest.json").read_text())["runs"][-1].get("captures", []) \
                if (out / "guest/manifest.json").is_file() else []
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


def successor_stage_paths(plan: dict, succ_plan: dict, succ_row: str, succ_root: Path) -> list[str]:
    """Repo-relative files the guest must reach beyond the selected row's tree and retail maps."""
    paths = [*plan["stage_paths"], *succ_plan["stage_paths"]]
    hcp = (succ_root / succ_row / f"{succ_row}.hcp").resolve().relative_to(ROOT).as_posix()
    if not hcp.startswith(plan["guest_package_root"].rstrip("/") + "/"):
        paths.append(hcp)
    return list(dict.fromkeys(paths))


def run_successor(row: str, succ_row: str, fault: str = "none", ticks: int = SUCCESSOR_TICKS) -> dict:
    """Link and run one guest successor sequence; results go to build/m2-c2-foreign/<row>/<succ>-<case>/.

    The selected row's map A is loaded by the production path; CE then runs the successor
    transaction for succ_row's map B (see HALO_PS2_C2_SUCCESSOR_MODE in the CE main.c).
    Never touches build/m2-c2-matrix/summary.json.
    """
    mode, label = SUCCESSOR_CASES[fault]
    out = FOREIGN_ROOT / row / f"{succ_row}-{label}"
    out.mkdir(parents=True, exist_ok=True)
    started = time.time()
    result: dict = {"row": row, "successor_row": succ_row, "successor_fault": fault, "mode": mode,
                    "case": label, "pass": False, "reasons": [], "started_unix": int(started),
                    "ticks": ticks}
    (out / "result.json").write_text(json.dumps({**result, "state": "running"}, indent=2) + "\n")
    try:
        if row == succ_row:
            raise RuntimeError("the successor row must differ from the selected row")
        package_root = package_root_for(row)
        succ_root = package_root_for(succ_row)
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
        elf, why = link_row(row, package_root, out, include_dir=include_dir)
        if elf is None:
            raise RuntimeError(why)
        result["elf"] = str(elf.relative_to(ROOT))
        ok, why = guest_row(row, elf, plan, out, SUCCESSOR_GUEST_TIMEOUT, SUCCESSOR_PROCESS_TIMEOUT,
                            successor_stage_paths(plan, succ_plan, succ_row, succ_root),
                            released_map=plan["map"] if mode == 2 else succ_plan["map"])
        log_path = out / "guest/runs/partition-selected/halo_ps2_local.txt"
        lines = read_guest_lines(log_path)
        result["guest_log"] = str(log_path.relative_to(ROOT))
        result["guest_line_count"] = len(lines)
        parsed = parse_successor_log(lines, row, plan["map"], succ_row, succ_plan["map"], mode, ticks)
        result.update(parsed)
        result["ce_failure_lines"] = ce_failure_lines(out / "guest/runs/partition-selected/emu.txt")
        if parsed["failing_checks"] and result["ce_failure_lines"]:
            result["reasons"].append("CE reported: " + " | ".join(result["ce_failure_lines"][:2]))
        if not ok:
            result["reasons"].insert(0, why)
        result["pass"] = bool(ok and not parsed["failing_checks"])
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
    global RESULT_ROOT
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
    args = parser.parse_args(argv)
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
    if args.package_root and not args.c3:
        parser.error("--package-root needs --c3")
    if args.c3:
        if (args.cycles != 1 or args.ticks) and not args.render_views:
            parser.error("--c3 runs the default single-cycle rows only")
        if args.successor:
            parser.error("--c3 cannot be combined with --successor")
        # Every subprocess (closure, link probe, guest runner) inherits HCU_C3=1.
        os.environ["HCU_C3"] = "1"
        RESULT_ROOT = C3_ROOT
    summary = []
    for row in rows:
        if args.skip_existing and previously_passed(row):
            print(f"{row}: skipped (previous pass)")
            continue
        result = run_row(row, args.package_root, cycles=args.cycles,
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
