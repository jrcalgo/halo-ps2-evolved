"""Hash-pinned raw collision-surface breakable inventory for stock MP maps."""
from pathlib import Path
import hashlib
import json
import struct
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "submodules/halo-ps2/tools"))

from halo2ps2 import bsp, mapinfo, tagindex
from ctag_schema_walk import read_xbox_tag_region
from test_hcu_mp_capacity import MP_MAPS, MP_SOURCE_SHA256


EXPECTED_BREAKABLE_SURFACES = {
    "beavercreek": (),
    "bloodgulch": (),
    "boardingaction": (),
    "carousel": (),
    "chillout": (),
    "damnation": (),
    "hangemhigh": (),
    "longest": (),
    "prisoner": (401, 457, 902, 960, 2834, 2835, 2838, 2839),
    "putput": (),
    "ratrace": (),
    "sidewinder": (),
    "wizard": (),
}


def _raw_breakable_inventory(map_name):
    """Decode raw collision-surface flag/index bytes, independently of CE."""
    map_path = ROOT / "build/retail-maps/decompressed" / f"{map_name}.map"
    source_sha = hashlib.sha256(map_path.read_bytes()).hexdigest()
    if source_sha != MP_SOURCE_SHA256[map_name]:
        raise AssertionError(f"source map hash changed: {map_name} {source_sha}")

    index = tagindex.TagIndex.read(map_path)
    tag_region, _tag_base, _source = read_xbox_tag_region(map_path)
    locations = bsp.locate(index, tag_region,
                           mapinfo.read_header(map_path).decompressed_size)
    if len(locations) != 1:
        raise AssertionError(f"expected one stock MP BSP in {map_name}, got {len(locations)}")
    location = locations[0]
    with map_path.open("rb") as stream:
        stream.seek(location.file_offset)
        image = stream.read(location.size)
    if len(image) != location.size:
        raise AssertionError(f"truncated BSP: {map_name}")

    root = struct.unpack_from("<I", image, 0)[0] - location.address
    if root < 0 or root + 0xB8 > len(image):
        raise AssertionError(f"BSP root outside source image: {map_name}")
    collision_count, collision_address = struct.unpack_from("<II", image, root + 0xB0)
    if collision_count != 1:
        raise AssertionError(f"expected one collision BSP in {map_name}")
    collision = collision_address - location.address
    if collision < 0 or collision + 0x60 > len(image):
        raise AssertionError(f"collision BSP outside source image: {map_name}")
    surface_count, surface_address = struct.unpack_from("<II", image, collision + 0x3C)
    surface_offset = surface_address - location.address if surface_address else 0
    if (surface_count < 0 or surface_offset < 0 or
            surface_offset + surface_count * 12 > len(image)):
        raise AssertionError(f"collision surface block outside source image: {map_name}")

    # Raw structure_collision_surface is plane designator (i32), first edge
    # (i32), flags (u8), breakable index (u8), and material index (i16).
    breakable = []
    invisible = []
    for surface_index in range(surface_count):
        row = struct.unpack_from("<iiBBh", image,
                                 surface_offset + surface_index * 12)
        flags, breakable_index, material_index = row[2:]
        if flags & (1 << 3):
            breakable.append({"surface_index": surface_index,
                              "flags": flags,
                              "breakable_index": breakable_index,
                              "material_index": material_index})
        if flags & (1 << 1):
            invisible.append(surface_index)
    return {
        "source_map_sha256": source_sha,
        "raw_bsp_sha256": hashlib.sha256(image).hexdigest(),
        "bsp_path": location.path,
        "collision_surface_count": surface_count,
        "breakable_surfaces": breakable,
        "invisible_surface_count": len(invisible),
    }


class StockMpBreakableInventory(unittest.TestCase):
    def test_all_13_stock_mp_collision_breakable_bits(self):
        self.assertEqual(set(MP_MAPS), set(EXPECTED_BREAKABLE_SURFACES))
        inventory = {name: _raw_breakable_inventory(name) for name in MP_MAPS}
        self.assertEqual(set(inventory), set(MP_MAPS))

        for name, row in inventory.items():
            indices = tuple(item["surface_index"]
                            for item in row["breakable_surfaces"])
            self.assertEqual(indices, EXPECTED_BREAKABLE_SURFACES[name], name)
            self.assertEqual(row["invisible_surface_count"], 0, name)
            for item in row["breakable_surfaces"]:
                self.assertEqual(item["flags"], 9, (name, item))
                self.assertIn(item["breakable_index"], (0, 1), (name, item))
                self.assertGreaterEqual(item["material_index"], 0, (name, item))

        prisoner_rows = inventory["prisoner"]["breakable_surfaces"]
        self.assertEqual({row["breakable_index"] for row in prisoner_rows}, {0, 1})
        artifact_dir = ROOT / "build/m2-mp-breakable-inventory-13"
        artifact_dir.mkdir(parents=True, exist_ok=True)
        artifact = artifact_dir / "inventory.json"
        artifact.write_text(json.dumps({
            "scope": "13 source-hash-pinned stock multiplayer maps",
            "flag_bit": 3,
            "breakable_maps": [name for name in MP_MAPS
                               if inventory[name]["breakable_surfaces"]],
            "maps": inventory,
        }, indent=2, sort_keys=True) + "\n")

