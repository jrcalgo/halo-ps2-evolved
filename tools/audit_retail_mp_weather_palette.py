#!/usr/bin/env python3
"""Inventory raw Halo CE multiplayer BSP weather palettes and cluster indices.

This is a source-data structural audit, not a runtime wind simulation test. It
walks every BSP in the 13 stock multiplayer maps, validates Xbox virtual-address
extents against each raw decompressed BSP, and checks palette/cluster indices
against CE's 32-entry wind-state array.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import struct
import sys

ROOT = Path(__file__).resolve().parents[1]
MP_MAPS = (
    "beavercreek", "bloodgulch", "boardingaction", "carousel", "chillout",
    "damnation", "hangemhigh", "longest", "prisoner", "putput", "ratrace",
    "sidewinder", "wizard",
)
WEATHER_PALETTE_OFFSET = 436
WEATHER_PALETTE_STRIDE = 0xF0
CLUSTER_BLOCK_OFFSET = 308
CLUSTER_STRIDE = 0x68
CLUSTER_WEATHER_INDEX_OFFSET = 8
CE_WIND_STATE_CAPACITY = 32

sys.path.insert(0, str(ROOT / "submodules/halo-ps2/tools"))
sys.path.insert(0, str(ROOT / "tools"))
from halo2ps2 import bsp, mapinfo, tagindex  # noqa: E402
from ctag_schema_walk import read_xbox_tag_region  # noqa: E402


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def git_pin(path: Path) -> str:
    try:
        return subprocess.check_output(
            ["git", "-C", str(path), "rev-parse", "HEAD"],
            text=True, stderr=subprocess.DEVNULL).strip()
    except (OSError, subprocess.CalledProcessError):
        return "unavailable"


def inventory_map(map_path: Path) -> dict:
    index = tagindex.TagIndex.read(map_path)
    tag_region, _tag_base, _source = read_xbox_tag_region(map_path)
    locations = bsp.locate(index, tag_region,
                           mapinfo.read_header(map_path).decompressed_size)
    bsp_rows = []
    map_palette_max = 0
    total_clusters = 0
    total_palette_entries = 0
    none_references = 0
    valid_references = 0
    invalid_references = []

    with map_path.open("rb") as stream:
        for bsp_index, location in enumerate(locations):
            stream.seek(location.file_offset)
            image = stream.read(location.size)
            if len(image) != location.size:
                raise ValueError(f"truncated BSP {location.path}")
            root = struct.unpack_from("<I", image, 0)[0] - location.address
            if root < 0 or root + 648 > len(image):
                raise ValueError(f"BSP root outside image: {location.path}")

            palette_count, palette_address = struct.unpack_from(
                "<iI", image, root + WEATHER_PALETTE_OFFSET)
            palette_offset = palette_address - location.address if palette_address else 0
            if (palette_count < 0 or
                    (palette_count and (palette_offset < 0 or
                     palette_offset + palette_count * WEATHER_PALETTE_STRIDE > len(image)))):
                raise ValueError(f"weather palette extent outside {location.path}")

            cluster_count, cluster_address = struct.unpack_from(
                "<iI", image, root + CLUSTER_BLOCK_OFFSET)
            cluster_offset = cluster_address - location.address if cluster_address else 0
            if (cluster_count < 0 or
                    (cluster_count and (cluster_offset < 0 or
                     cluster_offset + cluster_count * CLUSTER_STRIDE > len(image)))):
                raise ValueError(f"cluster extent outside {location.path}")

            references = {}
            for cluster_index in range(cluster_count):
                cluster = cluster_offset + cluster_index * CLUSTER_STRIDE
                weather_index = struct.unpack_from(
                    "<h", image, cluster + CLUSTER_WEATHER_INDEX_OFFSET)[0]
                references[str(weather_index)] = references.get(str(weather_index), 0) + 1
                if weather_index == -1:
                    none_references += 1
                elif 0 <= weather_index < palette_count:
                    valid_references += 1
                else:
                    invalid_references.append({
                        "bsp_index": bsp_index,
                        "bsp_path": location.path,
                        "cluster_index": cluster_index,
                        "weather_palette_index": weather_index,
                        "weather_palette_count": palette_count,
                    })

            bsp_rows.append({
                "bsp_index": bsp_index,
                "bsp_path": location.path,
                "raw_bsp_sha256": hashlib.sha256(image).hexdigest(),
                "raw_bsp_bytes": len(image),
                "weather_palette_count": palette_count,
                "cluster_count": cluster_count,
                "cluster_weather_indices": references,
            })
            map_palette_max = max(map_palette_max, palette_count)
            total_clusters += cluster_count
            total_palette_entries += palette_count

    return {
        "map": map_path.stem,
        "source_map_sha256": sha256(map_path),
        "bsp_count": len(locations),
        "max_weather_palette_count": map_palette_max,
        "total_weather_palette_entries_across_bsps": total_palette_entries,
        "total_clusters": total_clusters,
        "cluster_weather_none_references": none_references,
        "cluster_weather_valid_references": valid_references,
        "invalid_cluster_weather_references": invalid_references,
        "bsps": bsp_rows,
    }


def build_report(source_dir: Path) -> dict:
    maps = [inventory_map(source_dir / f"{name}.map") for name in MP_MAPS]
    wind_source = ROOT / "submodules/halo-ce-universal/source/scenario/wind.c"
    structures_source = ROOT / "submodules/halo-ce-universal/source/structures/structures.h"
    catalog_source = ROOT / "src/stream/hcu_map_catalog.c"
    violations = []
    for row in maps:
        if row["max_weather_palette_count"] > CE_WIND_STATE_CAPACITY:
            violations.append({"map": row["map"], "reason": "palette-count-exceeds-wind_states"})
        if row["invalid_cluster_weather_references"]:
            violations.append({"map": row["map"], "reason": "cluster-weather-index-out-of-range"})
    return {
        "schema": "halo-ps2-mp-weather-palette-inventory-v1",
        "scope": "13 stock multiplayer maps only; campaign excluded",
        "kind": "raw decompressed Xbox source-data structural inventory; not CE runtime evidence",
        "source_directory": str(source_dir),
        "capacity": {
            "wind_states_entries": CE_WIND_STATE_CAPACITY,
            "wind_state_bytes_each": 0x20,
            "weather_palette_entry_bytes": WEATHER_PALETTE_STRIDE,
            "cluster_weather_index_offset": CLUSTER_WEATHER_INDEX_OFFSET,
            "none_sentinel": -1,
            "source_references": [
                "submodules/halo-ce-universal/source/scenario/wind.c:59-69,121,188-211",
                "submodules/halo-ce-universal/source/structures/structures.h:35-36",
            ],
            "wind_source_sha256": sha256(wind_source),
            "structures_header_sha256": sha256(structures_source),
        },
        "pins": {
            "parent": git_pin(ROOT),
            "halo_ce_universal": git_pin(ROOT / "submodules/halo-ce-universal"),
            "halo_ps2": git_pin(ROOT / "submodules/halo-ps2"),
            "catalog_sha256": sha256(catalog_source),
        },
        "map_count": len(maps),
        "maps": maps,
        "violations": violations,
        "pass": len(maps) == len(MP_MAPS) and not violations,
        "limits": [
            "Counts and indices are read from raw decompressed source BSP bytes; this does not prove package relocation preserves them.",
            "A palette count at or below 32 only establishes static capacity compatibility; no wind tag resolution, wind update, query, particle simulation, or render-tick cadence is exercised.",
            "CE wind_initialize_for_new_map clamps to wind_states capacity; an over-capacity map would be silently truncated by that code, so the inventory treats it as a failure rather than accepting the clamp.",
            "No PS2 arena, EE runtime, co-op/bot load, weather-particle pool high-water, or target performance evidence is produced.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", type=Path,
                        default=ROOT / "build/retail-maps/decompressed")
    args = parser.parse_args()
    report = build_report(args.source_dir)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
