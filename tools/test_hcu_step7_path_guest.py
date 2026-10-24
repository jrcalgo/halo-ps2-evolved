#!/usr/bin/env python3
"""Qualify CE A* route and bounded-workspace probes on all stock MP BSPs."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re

from test_hcu_boot import ROOT, boot_once
from test_emulator import save


DEFAULT_ELF = ROOT / "build/hcu-parent-link-probe/hcu-gameplay-machine-step8-mp-capacity-tagcache-4477120.elf"
ROUTES = {
    "beavercreek": (47, 201), "bloodgulch": (101, 108),
    "boardingaction": (393, 486), "carousel": (17, 74),
    "chillout": (20, 195), "damnation": (131, 476),
    "hangemhigh": (39, 65), "longest": (0, 29), "prisoner": (0, 94),
    "putput": (267, 268), "ratrace": (0, 33), "sidewinder": (69, 121),
    "wizard": (25, 46),
}
PATH = re.compile(
    r"HALO_PS2_LOCAL step8-mp-path map=(\w+) start=(-?\d+) goal=(-?\d+) "
    r"explored=(\d+) chain_nodes=(\d+) root=(-?\d+) reached=(\d+)"
)
MEMORY = re.compile(
    r"HALO_PS2_LOCAL step8-mp-path-memory map=(\w+) state_bytes=(\d+) "
    r"used_delta=(\d+) after_delta=(\d+) high=(\d+) capacity=(\d+) failures=(\d+)"
)
COMPLETE = "HALO_PS2_LOCAL step8-mp-capacity-complete maps=13 query_only=1"


def validate_log(path: Path) -> list[dict]:
    text = path.read_text(errors="replace")
    if "HALO_PS2_FAIL" in text:
        raise RuntimeError("guest emitted HALO_PS2_FAIL")
    paths = PATH.findall(text)
    memories = MEMORY.findall(text)
    if len(paths) != len(ROUTES) or len(memories) != len(ROUTES):
        raise RuntimeError(f"expected 13 A* and memory rows, got {len(paths)} and {len(memories)}")
    by_memory = {row[0]: row[1:] for row in memories}
    output = []
    for map_name, start_text, goal_text, explored_text, chain_text, root_text, reached_text in paths:
        if map_name not in ROUTES or map_name in {row["map"] for row in output}:
            raise RuntimeError(f"unexpected or duplicate A* map row: {map_name}")
        start, goal = int(start_text), int(goal_text)
        if ROUTES[map_name] != (start, goal):
            raise RuntimeError(f"wrong A* route for {map_name}: {start}->{goal}")
        explored, chain_nodes, root, reached = map(
            int, (explored_text, chain_text, root_text, reached_text))
        if explored < chain_nodes or chain_nodes < 2 or root != start or reached != 1:
            raise RuntimeError(f"invalid goal/parent-chain evidence for {map_name}")
        state_bytes, used_delta, after_delta, high, capacity, failures = map(int, by_memory[map_name])
        aligned = (state_bytes + 15) & ~15
        # CE's path search may allocate small ancillary scratch besides the
        # fixed path_state. Require that the state was charged, without
        # assuming those callsite-specific allocations are exactly zero.
        if used_delta < aligned or used_delta > capacity or after_delta != 0 or high > capacity or failures != 0:
            raise RuntimeError(f"invalid bounded allocator evidence for {map_name}")
        output.append({"map": map_name, "start_surface": start, "goal_surface": goal,
                       "explored_nodes": explored, "chain_nodes": chain_nodes,
                       "root_surface": root, "path_found": True,
                       "path_state_bytes": state_bytes, "allocator_bytes_consumed": used_delta,
                       "allocator_after_free_delta_bytes": after_delta,
                       "allocator_high_water": high, "allocator_capacity": capacity,
                       "allocator_failures": failures})
    if set(row["map"] for row in output) != set(ROUTES):
        raise RuntimeError("A* rows do not cover the complete 13-map set")
    if COMPLETE not in text or text.index(COMPLETE) < max(
            text.index(f"step8-mp-path map={row['map']} ") for row in output):
        raise RuntimeError("query completion marker missing or precedes a route")
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--elf", type=Path, default=DEFAULT_ELF)
    parser.add_argument("--mode", choices=("interpreter", "recompiler"), default="recompiler")
    parser.add_argument("--timeout", type=int, default=600)
    parser.add_argument("--stable-seconds", type=float, default=2.0)
    args = parser.parse_args()
    elf = args.elf.resolve()
    if not elf.is_file():
        raise RuntimeError(f"diagnostic ELF does not exist: {elf}")
    config = json.loads((ROOT / ".local/emulator.json").read_text())
    result = boot_once(config, elf, args.mode,
        os.environ.get("DISPLAY", config["display"]), args.timeout,
        "step8-mp-capacity", COMPLETE, stable_seconds=args.stable_seconds)
    routes = validate_log(Path(result["log"]))
    result["ce_astar_routes"] = routes
    result["scope"] = "diagnostic CE A*; not actor steering, playable match, or renderer acceptance"
    save(Path(result["run_directory"]) / "step7-path-validation.json", result)
    print(json.dumps({"status": "passed", "elf_sha256": result["elf_sha256"],
                      "mode": args.mode, "maps": len(routes),
                      "log": result["log"], "routes": routes}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
