"""Inventory Xbox Halo weapon tags without exporting retail tag payloads.

Offsets follow the 32-bit structures in pinned halo-64
source/items/weapon_definitions.h. The first-person-model reference at 0x45c
is independently verified by halo-ps2 scenconv.py; subtracting the weapon
interface field offset (340) places the weapon portion at 0x308. This tool
validates every tag-region access before reading a magazine or trigger.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import struct
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "submodules/halo-ps2/tools"))
from halo2ps2 import mapinfo, tagindex  # noqa: E402

WEAPON_OFFSET = 0x308
MAGAZINES_OFFSET = WEAPON_OFFSET + 488
TRIGGERS_OFFSET = WEAPON_OFFSET + 500
MAGAZINE_SIZE = 112
TRIGGER_SIZE = 276
MAX_RECORDS = 8


def _read(region: bytes, base: int, address: int, size: int) -> bytes:
    off = address - base
    if off < 0 or size < 0 or off + size > len(region):
        raise ValueError(f"tag access outside region: {address:#x}, {size} bytes")
    return region[off:off + size]


def _records(region: bytes, base: int, root: int, offset: int, size: int) -> list[bytes]:
    count, address, pad = struct.unpack("<III", _read(region, base, root + offset, 12))
    if count > MAX_RECORDS or pad != 0 or (count and not address) or (not count and address):
        raise ValueError(f"invalid weapon reflexive at {root + offset:#x}")
    return [_read(region, base, address + i * size, size) for i in range(count)]


def audit_region(index: tagindex.TagIndex, region: bytes) -> list[dict]:
    by_id = {e.tag_id: e for e in index.entries}
    result = []
    for entry in index.entries:
        if entry.group != "weap":
            continue
        mags = _records(region, index.base, entry.data_address,
                        MAGAZINES_OFFSET, MAGAZINE_SIZE)
        triggers = _records(region, index.base, entry.data_address,
                            TRIGGERS_OFFSET, TRIGGER_SIZE)
        rows = []
        for raw in triggers:
            projectile_id = struct.unpack_from("<I", raw, 148 + 12)[0]
            projectile = by_id.get(projectile_id)
            rows.append({
                "flags": struct.unpack_from("<I", raw, 0)[0],
                "rate_initial": struct.unpack_from("<f", raw, 4)[0],
                "rate_final": struct.unpack_from("<f", raw, 8)[0],
                "magazine_index": struct.unpack_from("<h", raw, 32)[0],
                "rounds_per_shot": struct.unpack_from("<h", raw, 34)[0],
                "charging_time": struct.unpack_from("<f", raw, 72)[0],
                "projectiles_per_shot": struct.unpack_from("<h", raw, 110)[0],
                "projectile": projectile.path if projectile and projectile.group == "proj" else None,
            })
        result.append({
            "path": entry.path,
            "magazines": [{
                "rounds_initial": struct.unpack_from("<h", raw, 6)[0],
                "rounds_total_max": struct.unpack_from("<h", raw, 8)[0],
                "rounds_loaded_max": struct.unpack_from("<h", raw, 10)[0],
                "reload_seconds_tag": struct.unpack_from("<f", raw, 20)[0],
                "rounds_reloaded": struct.unpack_from("<h", raw, 24)[0],
            } for raw in mags],
            "triggers": rows,
        })
    return result


def audit_map(path: Path) -> dict:
    index = tagindex.TagIndex.read(path)
    header = mapinfo.read_header(path)
    with path.open("rb") as file:
        file.seek(header.tag_data_offset)
        region = file.read(header.tag_data_size)
    if len(region) != header.tag_data_size:
        raise ValueError("truncated tag region")
    return {
        "map_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "source": "halo-64 weapon_definitions.h 32-bit layout; halo-ps2 scenconv.py 0x45c anchor",
        "weapons": audit_region(index, region),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("map", type=Path, help="decompressed user-owned Xbox map")
    parser.add_argument("--output", type=Path, default=ROOT / "build/combat-m13/weapons.json")
    args = parser.parse_args()
    report = audit_map(args.map)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(f"{len(report['weapons'])} weapon tags -> {args.output}")


if __name__ == "__main__":
    main()
