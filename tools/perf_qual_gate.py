#!/usr/bin/env python3
"""Frame-time gate for a C3 qualification capture.

Reads a frame-ring JSONL produced by tools/collect_c3_frame_ring.py
(kind ``c3_frame_probe``, object ``probe``). This tool does not launch
PCSX2 and does not open a socket. The default invocation only reads the
capture path you pass in.

The qualification ELF is a separate link, not the production ISO. That
link's headers must define ``HCU_C3_WORKLOAD_GUN_PICKUP_TEST`` as 1 and
``HCU_C3_WORKLOAD_LOCAL_PLAYERS`` as 1 or 2, and the link environment
must set ``HCU_C3_PHASE_PROBE=1``. Those switches must not be added to
tools/build_halo_ps2_iso.py. The production ISO must not define the
gun-pickup workload or the phase probe.

``frame_interval_cycles`` converts at the EE timer rate of 294912000
cycles/second. A sample that lacks ``frame_interval_cycles`` is skipped.
Exit 0 when p99 <= 33.3 ms, max <= 50 ms, and no sample is over 66 ms.
Exit 1 otherwise. Sums of ``view_skipped``, ``chain_overflow``,
``emit_failures``, ``fx_stream_drops``, and ``first_person_model_misses``
are printed when those keys exist. They do not fail the gate.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

EE_HZ = 294_912_000
P99_LIMIT_MS = 33.3
MAX_LIMIT_MS = 50.0
OVER_LIMIT_MS = 66.0
COUNTER_KEYS = ("view_skipped", "chain_overflow", "emit_failures",
                "fx_stream_drops", "first_person_model_misses")


def percentile(values, fraction):
    """Same rank as tools/analyze_c3_frame_ring.py."""
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int((len(ordered) - 1) * fraction))]


def evaluate(path: Path) -> dict:
    intervals = []
    skipped = 0
    present = {key: False for key in COUNTER_KEYS}
    totals = {key: 0 for key in COUNTER_KEYS}
    for line in path.read_text().splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if row.get("kind") != "c3_frame_probe":
            continue
        probe = row.get("probe")
        if not isinstance(probe, dict):
            skipped += 1
            continue
        for key in COUNTER_KEYS:
            if key in probe and probe[key] is not None:
                present[key] = True
                totals[key] += int(probe[key])
        if "frame_interval_cycles" not in probe or probe["frame_interval_cycles"] is None:
            skipped += 1
            continue
        intervals.append(int(probe["frame_interval_cycles"]) * 1000.0 / EE_HZ)
    counters = {key: totals[key] for key in COUNTER_KEYS if present[key]}
    report = {
        "samples": len(intervals),
        "skipped_missing_interval": skipped,
        "limits": {"p99_ms": P99_LIMIT_MS, "max_ms": MAX_LIMIT_MS,
                   "over_ms": OVER_LIMIT_MS},
        "counters": counters,
    }
    if not intervals:
        report["pass"] = False
        report["failures"] = ["no_frame_intervals"]
        return report
    p99 = percentile(intervals, 0.99)
    maximum = max(intervals)
    over = sum(value > OVER_LIMIT_MS for value in intervals)
    failures = []
    if p99 > P99_LIMIT_MS:
        failures.append("p99_ms")
    if maximum > MAX_LIMIT_MS:
        failures.append("max_ms")
    if over:
        failures.append("over_66_ms")
    report.update({
        "p99_ms": p99,
        "max_ms": maximum,
        "over_66_ms": over,
        "pass": not failures,
        "failures": failures,
    })
    return report


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("capture", type=Path)
    args = parser.parse_args(argv)
    try:
        report = evaluate(args.capture)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        report = {"pass": False, "error": str(exc)}
    print(json.dumps(report, indent=2))
    return 0 if report.get("pass") else 1


if __name__ == "__main__":
    sys.exit(main())
