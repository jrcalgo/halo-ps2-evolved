"""Cyborg shield and body from the Blood Gulch collision tag."""
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
MAP = ROOT / "data/retail/convert/bloodgulch/decompressed/bloodgulch.map"


def cyborg(path):
    sys.path[:0] = [str(ROOT / "submodules/halo-ps2/tools")]
    from halo2ps2 import mapinfo, tagindex
    index = tagindex.TagIndex.read(path)
    header = mapinfo.read_header(path)
    with path.open("rb") as handle:
        handle.seek(header.tag_data_offset)
        region = handle.read(header.tag_data_size)
    coll = next(item for item in index.entries
                if item.group == "coll" and item.path == r"characters\cyborg\cyborg")
    data = coll.data_address - index.base
    body, shield = struct.unpack_from("<f", region, data + 8)[0], struct.unpack_from("<f", region, data + 204)[0]
    recharge = struct.unpack_from("<I", region, data + 448)[0]
    count, address = struct.unpack_from("<II", region, data + 564)
    materials = []
    for i in range(count):
        raw = region[address - index.base + i * 0x48:address - index.base + (i + 1) * 0x48]
        materials.append(struct.unpack_from("<f", raw, 0x3C)[0])
    mods = {}
    for name in (r"weapons\pistol\bullet", r"weapons\assault rifle\bullet"):
        effect = next(item for item in index.entries if item.group == "jpt!" and item.path == name)
        point = effect.data_address - index.base
        flags = struct.unpack_from("<I", region, point + 456)[0]
        modifier = struct.unpack_from("<f", region, point + 512 + 21 * 4)[0]
        mods[name] = (flags, modifier)
    return body, shield, recharge, materials, mods


class Vital(unittest.TestCase):
    def test_shield_body_and_death(self):
        if not MAP.is_file():
            self.skipTest("decompressed Blood Gulch is not in the tree")
        body, shield, recharge, materials, mods = cyborg(MAP)
        self.assertEqual((body, shield), (75.0, 75.0))
        self.assertEqual(recharge, 0x3C088889)
        self.assertEqual(materials[0], 1.0)
        self.assertEqual(materials[2], struct.unpack("<f", struct.pack("<I", 0x3F4CCCCD))[0])
        self.assertEqual(mods[r"weapons\pistol\bullet"], (0x2, 1.5))
        self.assertEqual(mods[r"weapons\assault rifle\bullet"][1], 1.0)
        with tempfile.TemporaryDirectory() as temp:
            exe = Path(temp) / "vital"
            subprocess.run(
                ["cc", "-std=c11", "-Wall", "-Wextra", "-Werror", "-I" + str(ROOT / "src"),
                 str(ROOT / "tests/vital_main.c"), str(ROOT / "src/game/vital.c"), "-o", str(exe)],
                check=True, capture_output=True)
            out = subprocess.run([str(exe)], check=True, capture_output=True, text=True).stdout
        rows = {line.split()[0]: line.split() for line in out.splitlines()}
        self.assertAlmostEqual(float(rows["pistol1"][2]), 2.0 / 3.0, places=5)
        self.assertEqual(float(rows["pistol1"][4]), 1.0)
        self.assertEqual(rows["pistol1"][8], "0")
        self.assertEqual(rows["pistol3"][2], "0.0000000")
        self.assertEqual(rows["pistol3"][8], "0")
        self.assertEqual(rows["pistol5"][8], "1")
        self.assertEqual(rows["head_shielded"][8], "0")
        self.assertEqual(rows["head_open"][8], "1")
        self.assertAlmostEqual(float(rows["head_open"][4]), -0.5, places=5)
        self.assertGreater(float(rows["rifle7"][2]), 0.0)
        self.assertEqual(rows["rifle7"][8], "0")
        self.assertEqual(rows["rifle8"][2], "0.0000000")
        self.assertAlmostEqual(float(rows["rifle8"][4]), 1.0 - 5.0 / 75.0, places=5)
        self.assertEqual(rows["recharge_wait"][6], "0")
        self.assertAlmostEqual(float(rows["recharge_wait"][2]), 2.0 / 3.0, places=5)
        self.assertAlmostEqual(float(rows["recharge_step"][2]), 2.0 / 3.0 + 1.0 / 120.0, places=4)
        self.assertEqual(rows["melee"][8], "1")
        self.assertEqual(rows["melee"][2], "0.0000000")


if __name__ == "__main__":
    unittest.main()
