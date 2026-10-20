#!/usr/bin/env python3
"""Measure retail CE structure-BSP file extents against the PS2 current_bsp budget.

This reports the complete retail BSP blocks consumed by CE's current
scenario_structure_bsp_load path. It does not imply that all bytes are needed
for PS2 collision, or that they fit after conversion; it makes the raw-block
capacity gap explicit before a conversion policy is chosen.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

TOOLS = Path(__file__).resolve().parents[1] / "submodules/halo-ps2/tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from halo2ps2 import bsp, mapinfo, tagindex  # noqa: E402


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def audit_map(path: Path, capacity: int) -> dict:
    header = mapinfo.read_header(path)
    index = tagindex.TagIndex.read(path)
    with path.open("rb") as stream:
        stream.seek(header.tag_data_offset)
        region = stream.read(header.tag_data_size)
    if len(region) != header.tag_data_size:
        raise ValueError(f"{path}: truncated tag region")
    locations = bsp.locate(index, region, header.decompressed_size)
    rows = []
    for location in locations:
        if location.file_offset < 0 or location.size < bsp.HEADER_SIZE:
            raise ValueError(f"{path}: invalid BSP extent {location.path}")
        rows.append({
            "path": location.path,
            "file_offset": location.file_offset,
            "file_size": location.size,
            "xbox_base_address": location.address,
            "fits_raw_current_bsp": location.size <= capacity,
        })
    return {
        "map": path.stem,
        "decompressed_file_size": header.decompressed_size,
        "source_sha256": sha256(path),
        "structure_bsp_count": len(rows),
        "largest_structure_bsp_bytes": max((row["file_size"] for row in rows), default=0),
        "raw_bsp_capacity_failures": sum(not row["fits_raw_current_bsp"] for row in rows),
        "structure_bsps": rows,
    }


def audit(maps: list[Path], capacity: int) -> dict:
    map_rows = [audit_map(path, capacity) for path in sorted(maps)]
    rows = [
        {"map": map_row["map"], **bsp_row}
        for map_row in map_rows
        for bsp_row in map_row["structure_bsps"]
    ]
    largest = sorted(rows, key=lambda row: (-row["file_size"], row["map"], row["path"]))
    return {
        "format": "retail-ce-bsp-capacity-audit-v1",
        "capacity_bytes": capacity,
        "map_count": len(map_rows),
        "structure_bsp_count": len(rows),
        "raw_bsp_capacity_failure_count": sum(not row["fits_raw_current_bsp"] for row in rows),
        "largest_raw_structure_bsp_bytes": largest[0]["file_size"] if largest else 0,
        "largest_structure_bsps": largest[:20],
        "maps": map_rows,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("maps", type=Path, help="directory of decompressed retail .map files")
    parser.add_argument("--capacity", type=int, default=6_291_456,
                        help="assigned current_bsp bytes (default: 6,291,456)")
    parser.add_argument("--output", type=Path, help="new JSON output; stdout if omitted")
    args = parser.parse_args(argv)
    paths = sorted(args.maps.glob("*.map"))
    if not paths:
        parser.error(f"no .map files in {args.maps}")
    if args.capacity <= 0:
        parser.error("capacity must be positive")
    try:
        report = audit(paths, args.capacity)
        rendered = json.dumps(report, sort_keys=True, indent=2) + "\n"
        if args.output:
            if args.output.exists():
                parser.error(f"refusing to overwrite existing output: {args.output}")
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(rendered)
        else:
            print(rendered, end="")
    except (OSError, ValueError) as error:
        parser.exit(2, f"retail BSP capacity audit failed: {error}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
