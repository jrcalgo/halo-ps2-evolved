#!/usr/bin/env python3
"""Summarize the lossless C3 frame-ring rows from a PINE JSONL capture."""
import argparse
import json
from pathlib import Path

EE_HZ = 294_912_000
NTSC_30_CYCLES = EE_HZ / (60000 / 1001 / 2)
# COP0 timing and host scheduling jitter make an exact floating-point NTSC
# threshold count normal 33.367 ms frames as misses. Keep a small 0.1 ms
# tolerance and report 40 ms spikes separately.
DEADLINE_CYCLES = EE_HZ * .033467
SPIKE_CYCLES = EE_HZ * .040
TIMINGS = ("frame_interval_cycles", "total_cycles", "build_cycles",
           "view0_cycles", "view1_cycles", "view2_cycles", "view3_cycles",
           "gs_wait_cycles", "video_wait_cycles", "present_cycles",
           "submit_cycles", "publication_cycles", "view_visibility_cycles",
           "view_clip_gather_cycles", "view_material_sort_cycles", "view_world_emit_cycles",
           "view_object_hook_cycles", "view_hud_cycles", "view_overlay_cycles",
           "view_other_cycles", "gif_wait_cycles", "vif_submit_cycles", "upload_submit_cycles",
           "bitmap_source_cycles", "fx_publish_cycles")
# Count fields from the v4 frame tail. Absent keys are old captures; they are
# omitted rather than treated as zero. These sums are diagnostic only.
COUNTERS = ("fx_source_calls", "fx_source_bytes", "decal_lock_count",
            "fx_stream_drops", "tc_defer_count", "first_person_model_misses",
            "view_skipped", "chain_overflow", "emit_failures",
            "scheduler_steps", "dropped_delta")


def percentile(values, fraction):
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int((len(ordered) - 1) * fraction))]


def summarize(path: Path) -> dict:
    frames, loss, queue_drops, seen_frontiers = [], 0, 0, set()
    for line in path.read_text().splitlines():
        row = json.loads(line)
        if row.get("kind") == "c3_frame_probe":
            probe = row["probe"]
            frames.append(probe)
            frontier = row.get("ring_write_sequence")
            if frontier not in seen_frontiers:
                loss += int(row.get("lost_since_last_read") or 0)
                seen_frontiers.add(frontier)
        if row.get("kind") == "collector_health":
            queue_drops = max(queue_drops, int(row.get("queue_drops") or 0))
        if row.get("kind") == "identity" and row.get("diagnostic_overwrites") is not None:
            loss += int(row.get("diagnostic_overwrites") or 0)
    if not frames:
        raise ValueError("capture contains no C3 frame-ring records")
    intervals = [f["frame_interval_cycles"] for f in frames
                 if f["frame_interval_cycles"]]
    correlated = {"spike_frames": 0, "spikes_with_cache_eviction": 0,
                  "spikes_with_pool_refusal": 0, "spikes_with_bitmap_read": 0,
                  "spikes_with_bitmap_defer": 0, "spikes_with_model_refusal": 0,
                  "spikes_with_pool_event_detail": 0,
                  "pool_event_frames": 0, "pool_event_types": {},
                  "pool_event_resources": {}, "spike_pool_event_types": {},
                  "spike_pool_event_resources": {}}
    previous = None
    for frame in frames:
        is_spike = frame["frame_interval_cycles"] > SPIKE_CYCLES
        if frame.get("last_pool_event", 0):
            correlated["pool_event_frames"] += 1
            event = str(frame["last_pool_event"])
            resource = str(frame.get("last_pool_event_resource", 0))
            correlated["pool_event_types"][event] = correlated["pool_event_types"].get(event, 0) + 1
            correlated["pool_event_resources"][resource] = correlated["pool_event_resources"].get(resource, 0) + 1
            if is_spike:
                correlated["spikes_with_pool_event_detail"] += 1
                correlated["spike_pool_event_types"][event] = correlated["spike_pool_event_types"].get(event, 0) + 1
                correlated["spike_pool_event_resources"][resource] = correlated["spike_pool_event_resources"].get(resource, 0) + 1
        if is_spike:
            correlated["spike_frames"] += 1
            if previous and frame["sequence"] == previous["sequence"] + 1:
                for key, label in (("cache_evictions", "spikes_with_cache_eviction"),
                                   ("cache_pool_refusals", "spikes_with_pool_refusal"),
                                   ("cache_loads_refused", "spikes_with_model_refusal")):
                    if (frame.get(key, 0) - previous.get(key, 0)) & 0xffffffff:
                        correlated[label] += 1
            if frame["bitmap_read_calls"]:
                correlated["spikes_with_bitmap_read"] += 1
            if frame.get("bitmap_deferred", 0):
                correlated["spikes_with_bitmap_defer"] += 1
        previous = frame
    timings = {}
    for field in TIMINGS:
        values = [f[field] for f in frames if f.get(field, 0) and
                  (field != "frame_interval_cycles" or f["frame_interval_cycles"])]
        if values:
            timings[field] = {"p50_ms": percentile(values, .5) * 1000 / EE_HZ,
                              "p95_ms": percentile(values, .95) * 1000 / EE_HZ,
                              "p99_ms": percentile(values, .99) * 1000 / EE_HZ,
                              "max_ms": max(values) * 1000 / EE_HZ}
    counters = {}
    for key in COUNTERS:
        if any(key in frame for frame in frames):
            counters[key] = sum(int(frame[key]) for frame in frames if key in frame)
    flashes = [frame for frame in frames if "flash_type" in frame or "flash_argb" in frame]
    summary = {"frames": len(frames), "ring_loss": loss, "queue_drops": queue_drops,
               "nominal_ntsc_frame_ms": NTSC_30_CYCLES * 1000 / EE_HZ,
               "frames_over_33_467_ms": sum(x > DEADLINE_CYCLES for x in intervals),
               "frames_over_40_ms": sum(x > SPIKE_CYCLES for x in intervals),
               "spike_correlations": correlated,
               "timings": timings}
    if counters:
        summary["diagnostic_counters"] = counters
    if flashes:
        summary["last_flash"] = {"flash_type": flashes[-1].get("flash_type"),
                                 "flash_argb": flashes[-1].get("flash_argb")}
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("capture", type=Path)
    args = parser.parse_args()
    print(json.dumps(summarize(args.capture), indent=2))
