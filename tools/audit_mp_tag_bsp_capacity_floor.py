#!/usr/bin/env python3
"""Measure the unavoidable resident CTAG + one decoded CBSP image floor.

This is a package-structure audit, not a runtime high-water measurement. It
decodes every CBSP envelope so compressed/transport size is not confused with
the destination image that CE retains. All 13 stock multiplayer maps are
required; campaign inputs are intentionally rejected by the completeness gate.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import struct
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "submodules/halo-ps2/tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))
from halo2ps2 import hp2  # noqa: E402

sys.path.insert(0, str(ROOT / "tools"))
import cbsp  # noqa: E402

MP_MAPS = {
    "beavercreek", "bloodgulch", "boardingaction", "carousel", "chillout",
    "damnation", "hangemhigh", "longest", "prisoner", "putput", "ratrace",
    "sidewinder", "wizard",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def audit_package(path: Path) -> dict:
    pack = hp2.parse(path.read_bytes())
    name = pack.name.lower().replace("_", "").replace(" ", "")
    if name not in MP_MAPS:
        raise ValueError(f"{path}: unexpected/non-MP package name {pack.name!r}")
    ctag_payload = pack.read("CTAG")
    if len(ctag_payload) < 52 or ctag_payload[:4] != b"CTAG":
        raise ValueError(f"{path}: truncated or invalid CTAG envelope")
    tag_image = struct.unpack_from("<I", ctag_payload, 12)[0]
    ctag_relocation_count = struct.unpack_from("<I", ctag_payload, 16)[0]
    ctag_relocation_bytes = ctag_relocation_count * 4
    if 52 + tag_image + ctag_relocation_bytes != len(ctag_payload):
        raise ValueError(f"{path}: CTAG image/relocation extents do not match section")
    bsps = []
    for section in pack.sections:
        if not re.fullmatch(r"B\d{3}", section.tag):
            continue
        decoded = cbsp.decode(pack.read(section.tag), max_image_size=0xFFFFFFFF)
        bsps.append({
            "tag": section.tag,
            "image_bytes": len(decoded.image),
            "relocation_count": len(decoded.relocations) +
                                len(decoded.tag_relocations),
            "relocation_bytes": 12 * (len(decoded.relocations) +
                                      len(decoded.tag_relocations)),
            "bsp_cache_bytes_image_plus_relocations": len(decoded.image) +
                12 * (len(decoded.relocations) + len(decoded.tag_relocations)),
            "transport_bytes": section.raw_size,
        })
    if not bsps:
        raise ValueError(f"{path}: package has no CBSP image sections")
    largest = max(bsps, key=lambda item: item["bsp_cache_bytes_image_plus_relocations"])
    return {
        "map": name,
        "package_path": str(path),
        "package_sha256": sha256(path),
        "ctag_image_bytes": tag_image,
        "ctag_relocation_count": ctag_relocation_count,
        "ctag_relocation_scratch_bytes": ctag_relocation_bytes,
        "cbsp_count": len(bsps),
        "cbsp_images": bsps,
        "largest_cbsp_image_bytes": largest["image_bytes"],
        "largest_cbsp_cache_bytes": largest["bsp_cache_bytes_image_plus_relocations"],
        "largest_cbsp_tag": largest["tag"],
        "resident_floor_bytes": tag_image + largest["bsp_cache_bytes_image_plus_relocations"],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("packages", nargs="+", type=Path,
                        help="all 13 generated all-BSP HP2 packages")
    parser.add_argument("--budget-json", type=Path,
                        default=ROOT / "config/memory-budget.json")
    parser.add_argument("--tag-cache-bytes", type=int, default=2 * 1024 * 1024,
                        help="current configured tag-cache split (default: 2 MiB)")
    parser.add_argument("--output", type=Path,
                        help="optional new JSON report; existing files are not overwritten")
    args = parser.parse_args()
    rows = [audit_package(path) for path in args.packages]
    names = [row["map"] for row in rows]
    if set(names) != MP_MAPS or len(names) != len(MP_MAPS):
        missing = sorted(MP_MAPS - set(names))
        duplicates = sorted(name for name in set(names) if names.count(name) > 1)
        raise SystemExit(f"need exactly all 13 MP maps; missing={missing}, duplicates={duplicates}")

    budget = json.loads(args.budget_json.read_text())
    bsp_budget = next(region["bytes"] for region in budget["regions"]
                      if region["name"] == "current_bsp")
    if args.tag_cache_bytes <= 0 or args.tag_cache_bytes >= bsp_budget:
        raise SystemExit("tag-cache split must be positive and smaller than current_bsp")
    for row in rows:
        row["current_bsp_bytes"] = bsp_budget
        row["current_tag_cache_split_bytes"] = args.tag_cache_bytes
        row["current_bsp_remainder_for_cbsp_bytes"] = bsp_budget - args.tag_cache_bytes
        row["current_split_ctag_fits"] = row["ctag_image_bytes"] <= args.tag_cache_bytes
        row["current_split_largest_cbsp_fits"] = (
            row["largest_cbsp_cache_bytes"] <= bsp_budget - args.tag_cache_bytes)
        row["combined_floor_fits_current_bsp"] = row["resident_floor_bytes"] <= bsp_budget
        row["maximum_tag_split_for_largest_cbsp"] = max(
            0, bsp_budget - row["largest_cbsp_cache_bytes"])
    rows.sort(key=lambda row: row["map"])
    output = {
        "schema": "halo-ps2-mp-tag-bsp-capacity-floor-v1",
        "scope": "exactly 13 stock Halo CE multiplayer maps; campaign excluded",
        "method": "CTAG decoded image plus largest CBSP decoded image and relocation rows retained in the BSP-cache tail; excludes CTAG relocation scratch (map-owner), stack headers, allocator metadata, claims, padding, and other transient overlap",
        "tool_sha256": sha256(Path(__file__).resolve()),
        "halo_ps2_commit": subprocess.check_output(
            ["git", "-C", str(ROOT / "submodules/halo-ps2"), "rev-parse", "HEAD"], text=True).strip(),
        "halo_ce_universal_commit": subprocess.check_output(
            ["git", "-C", str(ROOT / "submodules/halo-ce-universal"), "rev-parse", "HEAD"], text=True).strip(),
        "budget_json_sha256": sha256(args.budget_json),
        "current_bsp_capacity_bytes": bsp_budget,
        "current_tag_cache_split_bytes": args.tag_cache_bytes,
        "map_count": len(rows),
        "all_maps_combined_floor_fit": all(row["combined_floor_fits_current_bsp"] for row in rows),
        "all_maps_current_split_fit": all(row["current_split_ctag_fits"] and
                                           row["current_split_largest_cbsp_fits"] for row in rows),
        "largest_combined_floor": max(rows, key=lambda row: row["resident_floor_bytes"]),
        "maps": rows,
        "limits": [
            "lower bound only: includes the CE-resident CTAG image and CBSP relocation rows retained in the BSP-cache tail; CTAG relocation rows are a separate map-owner allocation and are excluded here",
            "also excludes stack headers, claims bitmap, alignment, cache metadata, and other runtime overlap",
            "does not prove host or EE allocation/high-water behavior",
            "a fit result is necessary but not sufficient; a floor overflow proves the current single-region design cannot fit that map",
        ],
    }
    rendered = json.dumps(output, sort_keys=True, indent=2) + "\n"
    if args.output:
        if args.output.exists():
            raise SystemExit(f"refusing to overwrite existing output: {args.output}")
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered)
    else:
        print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
