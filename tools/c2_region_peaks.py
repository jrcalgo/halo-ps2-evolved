#!/usr/bin/env python3
"""Worst-case region peaks measured on the guest, for the C2 budget lane.

Reads the HALO_PS2_LOCAL lines that tools/c2_guest_run.py saved for every run in
build/m2-c2-r9-peaks/runs/<run>/halo_ps2_local.txt, and the run list in manifest.json.
For each committed region of config/memory-budget.json it reports the capacity, the
largest observed high-water, the run and map or lifecycle context that produced it,
the failures seen, and slack = capacity - max high. Owners that are not budget regions
are reported in their own rows. Nothing is summed across owners except where a row says
so (current_bsp's upper bound).

Sources of a number (line families of the guest build):
  arena name=<region> cap used high alloc_failures resets     (region arenas)
  owner-telemetry phase name=<owner> kind parent bound cap used high failures resets
  owner-telemetry phase partition backing_cap backing_used backing_high backing_failures
  cache-owner phase name=tags|bsp current peak failures
  step8-mp-workload ... game_state_used/peak/fail, object_pool_used/peak/fail

Context: the map named by the last step8-mp-capacity-* or step8-mp-workload line, or the
lifecycle phase of the last m2-cycle-boundary line, or "boot" before either.

Usage:
    python3 -I tools/c2_region_peaks.py [--lane DIR] [--out-json PATH] [--out-md PATH]
"""

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LANE = ROOT / "build/m2-c2-r9-peaks"
BUDGET = ROOT / "config/memory-budget.json"
PREFIX = "HALO_PS2_LOCAL "
KEY_VALUE = re.compile(r"\b([A-Za-z_][A-Za-z0-9_-]*)=(\S+)")

# Owners that are budget regions in name, and the ones whose budget region is a name match.
# Anything else is reported in an owner row with no budget region.
OWNER_TO_REGION = {
    "game_state": "resident_gameplay",
    "dynamic_simulation": "dynamic_simulation",
    "scratch": "frame_scratch",
    "dma": "dma_commands",
    "streaming": "streaming",
    "audio_requests": "audio",
    "render_texture": "texture_cache",
    "tags": "current_bsp",
    "bsp": "current_bsp",
}
# Budget regions with no runtime owner or arena in the guest's output (a reservation or a
# constant), so a number for them can only come from the static ELF extent.
STATIC_REGIONS = ("system_kernel", "elf_static", "uncommitted_reserve")
BOOT_CONTEXTS = ("boot",)


def number(text):
    try:
        return int(text, 0)
    except (TypeError, ValueError):
        return None


def key_values(line):
    return dict(KEY_VALUE.findall(line))


def budget_regions(path):
    data = json.loads(Path(path).read_text())
    return {region["name"]: region for region in data["regions"]}, data


def manifest_runs(lane):
    path = Path(lane) / "manifest.json"
    if not path.exists():
        return [], {}
    manifest = json.loads(path.read_text())
    runs = [{"run": run.get("run"), "exit": run.get("exit"), "error": run.get("error"),
             "halo_line_count": run.get("halo_line_count"),
             "markers_all_present": run.get("markers_all_present")}
            for run in manifest.get("runs", [])]
    extents = {name: info.get("highest_guest_byte") for name, info in manifest.get("elfs", {}).items()}
    return runs, extents


def parse_run(run_name, lines):
    """Return (records, failures) for one run's HALO lines, in order."""
    records = []
    failures = []
    context = "boot"
    for raw in lines:
        if "HALO_PS2_FAIL" in raw:
            failures.append(raw.split("HALO_PS2_FAIL", 1)[1].strip())
            continue
        if not raw.startswith(PREFIX):
            continue
        line = raw[len(PREFIX):]
        fields = key_values(line)
        if line.startswith("step8-mp-capacity-") and "map" in fields:
            context = "map " + fields["map"]
        elif line.startswith("step8-mp-path-memory") and "map" in fields:
            context = "map " + fields["map"]
        elif line.startswith("step8-mp-workload ") and "map" in fields:
            context = "map " + fields["map"] + " (workload)"
            records.append(workload_record(run_name, context, fields))
        elif line.startswith("m2-cycle-boundary "):
            context = "lifecycle %s cycle %s" % (fields.get("phase"), fields.get("cycle"))
        elif line.startswith("m2-ui-lifecycle-"):
            if "cycle" in fields:
                context = "ui lifecycle cycle " + fields["cycle"]
            elif context == "boot":
                context = "ui lifecycle"
        if line.startswith("arena "):
            records.append(arena_record(run_name, context, fields))
        elif line.startswith("owner-telemetry "):
            record = owner_record(run_name, context, fields)
            if record is not None:
                records.append(record)
        elif line.startswith("cache-owner "):
            records.append(cache_record(run_name, context, fields))
    return records, failures


def base_record(run_name, context, source, name, fields):
    return {"run": run_name, "context": context, "source": source, "name": name,
            "cap": None, "used": None, "high": None, "failures": None, "resets": None,
            "phase": fields.get("phase")}


def arena_record(run_name, context, fields):
    record = base_record(run_name, context, "arena", fields.get("name"), fields)
    record.update(cap=number(fields.get("cap")), used=number(fields.get("used")),
                  high=number(fields.get("high")), failures=number(fields.get("alloc_failures")),
                  resets=number(fields.get("resets")))
    return record


def owner_record(run_name, context, fields):
    if "partition" in fields:
        record = base_record(run_name, context, "partition", "partition_backing", fields)
        record.update(cap=number(fields.get("backing_cap")), used=number(fields.get("backing_used")),
                      high=number(fields.get("backing_high")),
                      failures=number(fields.get("backing_failures")),
                      resets=number(fields.get("backing_resets")))
        record["partition"] = fields.get("partition")
        return record
    if "name" not in fields:
        return None
    record = base_record(run_name, context, "owner", fields["name"], fields)
    record.update(cap=number(fields.get("cap")), used=number(fields.get("used")),
                  high=number(fields.get("high")), failures=number(fields.get("failures")),
                  resets=number(fields.get("resets")))
    record["kind"] = fields.get("kind")
    record["parent"] = fields.get("parent")
    record["bound"] = number(fields.get("bound"))
    return record


def cache_record(run_name, context, fields):
    record = base_record(run_name, context, "cache-owner", "cache_" + fields.get("name", "?"), fields)
    record.update(cap=None, used=number(fields.get("current")), high=number(fields.get("peak")),
                  failures=number(fields.get("failures")), resets=number(fields.get("resets")))
    return record


def workload_record(run_name, context, fields):
    """Game-state and object-pool peaks of one Step 8 workload (no capacity on the line)."""
    record = base_record(run_name, context, "workload", "game_state", fields)
    record.update(cap=None, used=number(fields.get("game_state_used")),
                  high=number(fields.get("game_state_peak")), failures=number(fields.get("game_state_fail")))
    return record


def groups_by_name(records):
    grouped = {}
    for record in records:
        grouped.setdefault(record["name"], []).append(record)
    return grouped


def best(records):
    """The record with the largest high water; None when no record has one."""
    with_high = [record for record in records if record["high"] is not None]
    return max(with_high, key=lambda record: record["high"]) if with_high else None


def row_for(name, budget_region, records, cap_override=None):
    cap = budget_region["bytes"] if budget_region else cap_override
    if cap is None:
        for record in records:
            if record["cap"] is not None:
                cap = record["cap"]
                break
    top = best(records)
    failures = [record["failures"] for record in records if record["failures"] is not None]
    resets = [record["resets"] for record in records if record["resets"] is not None]
    row = {"name": name,
           "budget_region": budget_region["name"] if budget_region else None,
           "capacity": cap,
           "max_high": top["high"] if top else None,
           "max_high_run": top["run"] if top else None,
           "max_high_context": top["context"] if top else None,
           "max_high_source": top["source"] if top else None,
           "failures_max": max(failures) if failures else None,
           "resets_max": max(resets) if resets else None,
           "samples": len(records),
           "contexts": sorted({record["context"] for record in records}),
           "slack": (cap - top["high"]) if (top and cap is not None) else None,
           "measured": top is not None}
    row["workload_measured"] = any(not context_is_boot(record["context"]) for record in records
                                   if record["high"] is not None)
    if name == "current_bsp" and records:
        row["upper_bound_sum_of_owner_highs"] = sum_upper_bound(records)
    return row


def context_is_boot(context):
    return context in BOOT_CONTEXTS or context in ("ui lifecycle", "lifecycle")


def sum_upper_bound(records):
    """Max over (run, context) of the sum of the tags and bsp highs seen there."""
    totals = {}
    for record in records:
        if record["source"] != "owner" or record["high"] is None:
            continue
        key = (record["run"], record["context"])
        totals[key] = totals.get(key, 0) + record["high"]
    return max(totals.values()) if totals else None


def build_rows(records, regions, extents):
    grouped = groups_by_name(records)
    rows = []
    fed = set()
    for region_name, region in regions.items():
        feeders = [name for name, mapped in OWNER_TO_REGION.items() if mapped == region_name]
        pool = list(grouped.get(region_name, []))
        for feeder in feeders:
            pool.extend(grouped.get(feeder, []))
            fed.add(feeder)
        if region_name in STATIC_REGIONS:
            rows.append(static_row(region_name, region, extents))
            continue
        rows.append(row_for(region_name, region, pool))
        fed.add(region_name)
    for name in sorted(grouped):
        if name in fed or name in regions:
            continue
        cap = None
        rows.append(row_for(name, None, grouped[name], cap_override=cap))
    partition = grouped.get("partition_backing", [])
    if partition:
        rows.append(row_for("partition_backing", None, partition))
    return rows


def static_row(region_name, region, extents):
    """Static regions: a constant reservation, or the static image extent for elf_static."""
    row = {"name": region_name, "budget_region": region_name, "capacity": region["bytes"],
           "max_high": None, "max_high_run": None, "max_high_context": None, "max_high_source": None,
           "failures_max": None, "resets_max": None, "samples": 0, "contexts": [], "slack": None,
           "measured": False, "workload_measured": False}
    if region_name == "elf_static" and extents:
        guest_top = max(value for value in extents.values() if value is not None)
        row["max_high"] = guest_top - 0x100000
        row["max_high_source"] = "elf LOAD highest byte (memsz) minus 0x100000, static extent"
        row["max_high_run"] = "elf:" + ",".join(sorted(extents))
        row["slack"] = region["bytes"] - row["max_high"]
        row["measured"] = True
        row["note"] = ("static extent of the LOAD segments, not a runtime peak; the budget lane "
                       "measures the ELF owners separately")
    else:
        row["note"] = "reservation or constant; no runtime high-water is recorded"
    return row


def fmt(value):
    return "-" if value is None else str(value)


def markdown(report):
    lines = ["# C2 region peaks (measured on the guest)", "",
             "Generated by tools/c2_region_peaks.py from build/m2-c2-r9-peaks. Slack = capacity - max high.", "",
             "| region | budget region | capacity | max high | slack | run | context | source | failures | measured | workload measured |",
             "| --- | --- | ---: | ---: | ---: | --- | --- | --- | ---: | --- | --- |"]
    for row in report["rows"]:
        lines.append("| %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s |" % (
            row["name"], fmt(row["budget_region"]), fmt(row["capacity"]), fmt(row["max_high"]),
            fmt(row["slack"]), fmt(row["max_high_run"]), fmt(row["max_high_context"]),
            fmt(row["max_high_source"]), fmt(row["failures_max"]),
            "yes" if row["measured"] else "no", "yes" if row["workload_measured"] else "no"))
    lines += ["", "## Runs", ""]
    for run in report["runs"]:
        lines.append("- %s: exit=%s lines=%s markers_all_present=%s error=%s" % (
            run["run"], run["exit"], run["halo_line_count"], run["markers_all_present"], run.get("error")))
    lines += ["", "## Failure lines", ""]
    if not report["failures"]:
        lines.append("- none")
    for item in report["failures"]:
        lines.append("- %s: %s" % (item["run"], item["line"]))
    return "\n".join(lines) + "\n"


def build_report(lane, budget_path):
    regions, budget = budget_regions(budget_path)
    runs, extents = manifest_runs(lane)
    records = []
    failures = []
    run_dirs = sorted(path for path in (Path(lane) / "runs").glob("*") if path.is_dir())
    for run_dir in run_dirs:
        text_path = run_dir / "halo_ps2_local.txt"
        if not text_path.exists():
            continue
        lines = text_path.read_text(errors="replace").splitlines()
        run_records, run_failures = parse_run(run_dir.name, lines)
        records.extend(run_records)
        failures.extend({"run": run_dir.name, "line": line} for line in run_failures)
    return {"budget_committed_bytes": budget["committed_bytes"],
            "budget_reserve_bytes": budget["reserve_bytes"],
            "runs": runs, "record_count": len(records),
            "rows": build_rows(records, regions, extents), "failures": failures,
            "records": records}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    parser.add_argument("--lane", type=Path, default=LANE)
    parser.add_argument("--budget", type=Path, default=BUDGET)
    parser.add_argument("--out-json", type=Path, default=LANE / "region-peaks.json")
    parser.add_argument("--out-md", type=Path)
    args = parser.parse_args(argv)
    report = build_report(args.lane, args.budget)
    args.out_json.parent.mkdir(parents=True, exist_ok=True)
    args.out_json.write_text(json.dumps(report, indent=2) + "\n")
    if args.out_md:
        args.out_md.parent.mkdir(parents=True, exist_ok=True)
        args.out_md.write_text(markdown(report))
    print(markdown(report))
    return 0


if __name__ == "__main__":
    sys.exit(main())
