#!/usr/bin/env python3
"""Summarize the lossless C3 frame-ring rows from a PINE JSONL capture."""
import argparse
import json
from pathlib import Path

EE_HZ = 294_912_000
NTSC_30_CYCLES = EE_HZ / (60000 / 1001 / 2)
TIMINGS = ("frame_interval_cycles", "total_cycles", "build_cycles",
           "view0_cycles", "view1_cycles", "view2_cycles", "view3_cycles",
           "gs_wait_cycles", "video_wait_cycles", "present_cycles",
           "submit_cycles", "publication_cycles")


def percentile(values, fraction):
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int((len(ordered) - 1) * fraction))]


def summarize(path: Path) -> dict:
    frames, loss, queue_drops, seen_frontiers = [], 0, 0, set()
    for line in path.read_text().splitlines():
        row = json.loads(line)
        if row.get("kind") == "c3_frame_probe":
            frames.append(row["probe"])
            frontier = row.get("ring_write_sequence")
            if frontier not in seen_frontiers:
                loss += int(row.get("lost_since_last_read") or 0)
                seen_frontiers.add(frontier)
        if row.get("kind") == "collector_health":
            queue_drops = max(queue_drops, int(row.get("queue_drops") or 0))
    if not frames:
        raise ValueError("capture contains no C3 frame-ring records")
    intervals = [f["frame_interval_cycles"] for f in frames
                 if f["frame_interval_cycles"]]
    timings = {}
    for field in TIMINGS:
        values = [f[field] for f in frames if f[field] and
                  (field != "frame_interval_cycles" or f["frame_interval_cycles"])]
        if values:
            timings[field] = {"p50_ms": percentile(values, .5) * 1000 / EE_HZ,
                              "p95_ms": percentile(values, .95) * 1000 / EE_HZ,
                              "p99_ms": percentile(values, .99) * 1000 / EE_HZ,
                              "max_ms": max(values) * 1000 / EE_HZ}
    return {"frames": len(frames), "ring_loss": loss, "queue_drops": queue_drops,
            "missed_ntsc_30_deadlines": sum(x > NTSC_30_CYCLES for x in intervals),
            "timings": timings}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("capture", type=Path)
    args = parser.parse_args()
    print(json.dumps(summarize(args.capture), indent=2))
