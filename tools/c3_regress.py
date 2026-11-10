#!/usr/bin/env python3
"""C3 performance regression suite: summarise a headless PCSX2 log of a lag-trace build and gate it against a baseline.

A lag-trace ISO (HCU_C3_LAG_TRACE=1, plus the HCU_DEBUG_* scenario hooks in players.c) prints, with the emulator's
timestamp, one `pickup-spike frame=N total-ms=X ... loads=N hud-reads=N` line per frame, a `lag-draw ... fp-ms=` line
every 30 frames, and scenario markers (`debug-weapon`, `debug-zoom`, `debug-vehicle`, `debug-camo`, `debug-flashlight`).
This tool turns the log into one JSON summary:

  frames      whole-run frame time: median / p95 / p99 / max and the number of frames over 50 and 66 ms
  weapons     S2: fp-ms median per held weapon (`debug-weapon` markers) and the frame median while held
  zoom        S4: per zoom window (`debug-zoom` markers): frame median, loads, HUD reads, zoom level, weapon
  vehicle     S5: for 3 s after each `debug-vehicle exit`: frame p99 / max, loads, HUD reads
  counters    loads, HUD reads and `hud-chunk-miss` lines over the run (steady-state churn)

Usage:
  c3_regress.py summarize LOG [--tag TAG] [--out FILE]      write / print the summary JSON
  c3_regress.py compare SUMMARY BASELINE [--tolerance MS]   gate a summary against a baseline (exit 1 on a miss)
  c3_regress.py show SUMMARY                                one-screen table

Gates (a miss blocks the change): frame median <= baseline + 1.0 ms; frames over 66 ms <= baseline + 2; fp-ms median per
weapon <= baseline + 1.0 ms; zoomed frame median <= unzoomed + 1.0 ms of the same weapon; vehicle-exit p99 <= baseline + 5
ms; `hud-chunk-miss` lines <= baseline + 3. The suite only compares like with like: same ISO family, same scenario hooks.
"""
from __future__ import annotations

import argparse
import json
import re
import statistics
import sys
from pathlib import Path

TS = re.compile(r"^\[\s*([\d.]+)\]")
SPIKE = re.compile(r"pickup-spike frame=(\d+) total-ms=([\d.]+).*? loads=(\d+) pool=\S+ page-ins=(\d+)")
HUD_READS = re.compile(r"hud-reads=(\d+)")
LAG_DRAW = re.compile(r"lag-draw frame=(\d+) view=(\d+) world-ms=([\d.]+) fp-ms=([\d.]+)")
WEAPON = re.compile(r"debug-weapon (?:held|step=\d+) tick=\d+ (.*?)(?: object=\S+| tag-missing)?\s*$")
ZOOM = re.compile(r"debug-zoom step=(\d+) tick=(\d+) (?:give (.*?) object=|zoom=(-?\d+) held=)")
VEHICLE_EXIT = re.compile(r"debug-vehicle exit step=(\d+) tick=(\d+) ok=(\d)")
CHUNK_MISS = re.compile(r"hud-chunk-miss")
WARMUP_FRAMES = 240          # the first seconds load the map: not steady state


def weapon_key(raw: str) -> str:
    """`weapons\\plasma pistol\\plasma pistol` with its backslashes dropped by the log is `weaponsplasma pistolplasma pistol`:
    the directory and tag name are the same string twice."""
    rest = raw.replace("\\", "")
    if rest.startswith("weapons"):
        rest = rest[len("weapons"):]
    half = len(rest) // 2
    if len(rest) % 2 == 0 and rest[:half] == rest[half:]:
        rest = rest[:half]
    return rest.strip() or raw


def pct(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    return s[min(len(s) - 1, int(q * len(s)))]


def frame_stats(values: list[float]) -> dict:
    if not values:
        return {"n": 0, "median": 0.0, "p95": 0.0, "p99": 0.0, "max": 0.0, "over50": 0, "over66": 0}
    return {"n": len(values), "median": round(statistics.median(values), 2), "p95": round(pct(values, 0.95), 2),
            "p99": round(pct(values, 0.99), 2), "max": round(max(values), 2),
            "over50": sum(1 for v in values if v > 50.0), "over66": sum(1 for v in values if v > 66.0)}


def parse(log: Path) -> dict:
    frames = []      # (t, frame, ms, loads, hud_reads)
    draws = []       # (t, fp_ms)
    markers = []     # (t, kind, payload)
    chunk_miss = 0
    for line in log.read_text(errors="ignore").splitlines():
        m = TS.match(line)
        if not m:
            continue
        t = float(m.group(1))
        if "HALO_PS2_LOCAL" not in line:
            continue
        if CHUNK_MISS.search(line):
            chunk_miss += 1
            continue
        s = SPIKE.search(line)
        if s:
            hr = HUD_READS.search(line)
            frames.append((t, int(s.group(1)), float(s.group(2)), int(s.group(3)), int(hr.group(1)) if hr else 0))
            continue
        d = LAG_DRAW.search(line)
        if d and int(d.group(2)) == 0 and float(d.group(4)) > 0.0:
            draws.append((t, float(d.group(4))))
            continue
        w = WEAPON.search(line)
        if w:
            markers.append((t, "weapon", w.group(1)))
            continue
        z = ZOOM.search(line)
        if z:
            markers.append((t, "zoom", {"step": int(z.group(1)), "give": z.group(3), "zoom": z.group(4)}))
            continue
        v = VEHICLE_EXIT.search(line)
        if v:
            markers.append((t, "exit", {"step": int(v.group(1)), "ok": int(v.group(3))}))
    return {"frames": frames, "draws": draws, "markers": markers, "chunk_miss": chunk_miss}


def window(frames, t0: float, t1: float):
    return [f for f in frames if t0 <= f[0] < t1]


def summarize(log: Path, tag: str) -> dict:
    p = parse(log)
    steady = [f for f in p["frames"] if f[1] >= WARMUP_FRAMES]
    out: dict = {"tag": tag, "log": str(log), "frames": frame_stats([f[2] for f in steady])}
    out["counters"] = {"loads": sum(f[3] for f in steady), "hud_reads": sum(f[4] for f in steady),
                       "hud_chunk_miss": p["chunk_miss"]}
    # S2: fp-ms per held weapon, windows between `weapon` markers (the marker names the weapon from then on)
    wm = [(t, name) for t, kind, name in p["markers"] if kind == "weapon"]
    weapons: dict[str, dict] = {}
    for i, (t, name) in enumerate(wm):
        t1 = wm[i + 1][0] if i + 1 < len(wm) else float("inf")
        key = weapon_key(name)
        fp = [ms for (td, ms) in p["draws"] if t <= td < t1]
        fr = [f[2] for f in window(steady, t, t1)]
        row = weapons.setdefault(key, {"fp": [], "frames": []})
        row["fp"] += fp
        row["frames"] += fr
    out["weapons"] = {k: {"n": len(v["fp"]), "fp_median": round(statistics.median(v["fp"]), 2) if v["fp"] else 0.0,
                          "frame_median": round(statistics.median(v["frames"]), 2) if v["frames"] else 0.0}
                      for k, v in weapons.items()}
    # S4: zoom windows
    zm = [(t, pl) for t, kind, pl in p["markers"] if kind == "zoom"]
    zoom = []
    weapon = None
    for i, (t, pl) in enumerate(zm):
        if pl["give"]:
            weapon = weapon_key(pl["give"])
        t1 = zm[i + 1][0] if i + 1 < len(zm) else t + 12.0
        fr = window(steady, t + 1.0, t1)          # skip the first second: the weapon swap and zoom ramp
        level = -1 if pl["give"] else int(pl["zoom"])
        zoom.append({"step": pl["step"], "weapon": weapon, "zoom": level, "frames": frame_stats([f[2] for f in fr]),
                     "loads": sum(f[3] for f in fr), "hud_reads": sum(f[4] for f in fr)})
    out["zoom"] = zoom
    # S5: 3 s after each exit
    vehicle = []
    for t, kind, pl in p["markers"]:
        if kind != "exit":
            continue
        fr = window(steady, t, t + 3.0)
        vehicle.append({"step": pl["step"], "ok": pl["ok"], "frames": frame_stats([f[2] for f in fr]),
                        "loads": sum(f[3] for f in fr), "hud_reads": sum(f[4] for f in fr)})
    out["vehicle"] = vehicle
    return out


def zoom_pairs(summary: dict):
    """(weapon, unzoomed median, zoomed median) for every weapon with both windows."""
    by: dict[str, dict] = {}
    for z in summary.get("zoom", []):
        if not z["weapon"] or not z["frames"]["n"]:
            continue
        slot = by.setdefault(z["weapon"], {"off": [], "on": []})
        slot["on" if z["zoom"] >= 0 else "off"].append(z["frames"]["median"])
    return {w: (statistics.median(v["off"]), statistics.median(v["on"])) for w, v in by.items() if v["off"] and v["on"]}


def compare(summary: dict, baseline: dict, tolerance: float = 1.0) -> list[str]:
    miss = []
    f, b = summary["frames"], baseline["frames"]
    if f["median"] > b["median"] + tolerance:
        miss.append(f"frame median {f['median']} > baseline {b['median']} + {tolerance}")
    if f["over66"] > b["over66"] + 2:
        miss.append(f"frames over 66 ms {f['over66']} > baseline {b['over66']} + 2")
    for name, row in summary.get("weapons", {}).items():
        base = baseline.get("weapons", {}).get(name)
        if base and row["fp_median"] > base["fp_median"] + tolerance:
            miss.append(f"fp-ms {name} {row['fp_median']} > baseline {base['fp_median']} + {tolerance}")
    for name, (off, on) in zoom_pairs(summary).items():
        if on > off + tolerance:
            miss.append(f"zoomed frame median {name} {on} > unzoomed {off} + {tolerance}")
    base_ex = [v for v in baseline.get("vehicle", []) if v["frames"]["n"]]
    cur_ex = [v for v in summary.get("vehicle", []) if v["frames"]["n"]]
    if base_ex and cur_ex:
        cur, base = max(v["frames"]["p99"] for v in cur_ex), max(v["frames"]["p99"] for v in base_ex)
        if cur > base + 5.0:
            miss.append(f"vehicle-exit p99 {cur} > baseline {base} + 5")
    if summary["counters"]["hud_chunk_miss"] > baseline["counters"]["hud_chunk_miss"] + 3:
        miss.append(f"hud-chunk-miss {summary['counters']['hud_chunk_miss']} > baseline "
                    f"{baseline['counters']['hud_chunk_miss']} + 3")
    return miss


def show(summary: dict) -> None:
    f = summary["frames"]
    print(f"{summary['tag']}: frames n={f['n']} median={f['median']} p95={f['p95']} p99={f['p99']} max={f['max']} "
          f">50={f['over50']} >66={f['over66']}")
    c = summary["counters"]
    print(f"  counters loads={c['loads']} hud_reads={c['hud_reads']} hud_chunk_miss={c['hud_chunk_miss']}")
    for name, row in summary.get("weapons", {}).items():
        print(f"  weapon {name:18s} fp n={row['n']:3d} median={row['fp_median']:6.2f} frame median={row['frame_median']:6.2f}")
    for name, (off, on) in zoom_pairs(summary).items():
        print(f"  zoom {name:18s} unzoomed {off:6.2f} zoomed {on:6.2f} ms")
    for v in summary.get("vehicle", []):
        print(f"  vehicle exit step {v['step']}: p99={v['frames']['p99']} max={v['frames']['max']} loads={v['loads']} "
              f"hud_reads={v['hud_reads']}")


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("summarize")
    s.add_argument("log", type=Path)
    s.add_argument("--tag", default="")
    s.add_argument("--out", type=Path)
    c = sub.add_parser("compare")
    c.add_argument("summary", type=Path)
    c.add_argument("baseline", type=Path)
    c.add_argument("--tolerance", type=float, default=1.0)
    w = sub.add_parser("show")
    w.add_argument("summary", type=Path)
    a = ap.parse_args(argv)
    if a.cmd == "summarize":
        summary = summarize(a.log, a.tag or a.log.stem)
        text = json.dumps(summary, indent=1)
        if a.out:
            a.out.parent.mkdir(parents=True, exist_ok=True)
            a.out.write_text(text + "\n")
        show(summary)
        return 0
    if a.cmd == "show":
        show(json.loads(a.summary.read_text()))
        return 0
    miss = compare(json.loads(a.summary.read_text()), json.loads(a.baseline.read_text()), a.tolerance)
    for line in miss:
        print("FAIL", line)
    print("PASS" if not miss else f"{len(miss)} gate(s) missed")
    return 1 if miss else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
