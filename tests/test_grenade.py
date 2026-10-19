"""Frag and plasma grenades, and the cyborg melee effect, from Blood Gulch."""
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
MAP = ROOT / "data/retail/convert/bloodgulch/decompressed/bloodgulch.map"


def read_map():
    sys.path[:0] = [str(ROOT / "submodules/halo-ps2/tools")]
    from halo2ps2 import mapinfo, tagindex
    index = tagindex.TagIndex.read(MAP)
    header = mapinfo.read_header(MAP)
    with MAP.open("rb") as handle:
        handle.seek(header.tag_data_offset)
        region = handle.read(header.tag_data_size)
    cyborg = next(item for item in index.entries
                  if item.group == "bipd" and item.path == r"characters\cyborg_mp\cyborg_mp")
    data = cyborg.data_address - index.base
    velocity = struct.unpack_from("<f", region, data + 0x2C0)[0]
    kind, count = struct.unpack_from("<hh", region, data + 0x2C4)
    melee_id = struct.unpack_from("<I", region, data + 0x294)[0]
    melee = next(item for item in index.entries if item.tag_id == melee_id)
    melee_damage = struct.unpack_from("<f", region, melee.data_address - index.base + 468)[0]
    blasts = {}
    for name in (r"weapons\frag grenade\explosion", r"weapons\plasma grenade\explosion"):
        effect = next(item for item in index.entries if item.group == "jpt!" and item.path == name)
        point = effect.data_address - index.base
        falloff, cutoff = struct.unpack_from("<ff", region, point)
        minimum, lower, upper = struct.unpack_from("<fff", region, point + 464)
        blasts[name] = (falloff, cutoff, minimum, lower, upper)
    fuses = {}
    for name in (r"weapons\frag grenade\frag grenade", r"weapons\plasma grenade\plasma grenade"):
        projectile = next(item for item in index.entries if item.group == "proj" and item.path == name)
        point = projectile.data_address - index.base + 0x17C
        fuses[name] = struct.unpack_from("<f", region, point + 64)[0]
    return velocity, kind, count, melee_damage, blasts, fuses


class Grenade(unittest.TestCase):
    def test_throw_fuse_and_blast(self):
        if not MAP.is_file():
            self.skipTest("decompressed Blood Gulch is not in the tree")
        velocity, kind, count, melee_damage, blasts, fuses = read_map()
        self.assertEqual((velocity, kind, count, melee_damage), (10.0, 0, 4, 1000.0))
        self.assertEqual(fuses[r"weapons\frag grenade\frag grenade"], 0.5)
        self.assertEqual(fuses[r"weapons\plasma grenade\plasma grenade"], 2.0)
        self.assertEqual(blasts[r"weapons\frag grenade\explosion"], (1.5, 2.5, 80.0, 120.0, 120.0))
        self.assertEqual(blasts[r"weapons\plasma grenade\explosion"][:2], (0.5, 2.0))
        with tempfile.TemporaryDirectory() as temp:
            exe = Path(temp) / "grenade"
            subprocess.run(
                ["cc", "-std=c11", "-Wall", "-Wextra", "-Werror", "-I" + str(ROOT / "src"),
                 str(ROOT / "tests/grenade_main.c"), str(ROOT / "src/game/grenade.c"),
                 str(ROOT / "src/game/vital.c"), "-lm", "-o", str(exe)],
                check=True, capture_output=True)
            out = subprocess.run([str(exe)], check=True, capture_output=True, text=True).stdout
        rows = {line.split()[0]: line.split() for line in out.splitlines()}
        self.assertEqual(rows["throw"][1], "3")
        self.assertAlmostEqual(float(rows["throw"][2]), 10.0 / 30.0, places=6)
        self.assertAlmostEqual(float(rows["throw"][3]), 1.0 - 0.0035651792 / 2.0, places=5)
        self.assertEqual(rows["throw"][4], "75432777")
        self.assertEqual(rows["air"][1], "0")
        self.assertEqual(rows["frag_fuse"][1], "15")
        self.assertEqual(rows["plasma_fuse"][1], "61")
        self.assertEqual(rows["blast0"][1], "120.0")
        self.assertEqual(rows["blast_seed"][1], "75432777")
        self.assertEqual(rows["blast2"][1], "100.0")
        self.assertEqual(rows["blast_far"][1], "0.0")
        self.assertAlmostEqual(float(rows["blast_body"][1]), 0.4, places=4)
        self.assertEqual(rows["blast_body"][2], "0")
        self.assertEqual(rows["blast_second"][1], "1")
        self.assertEqual(rows["empty"][1:], ["0", "0"])
        self.assertEqual(rows["frag_rest"][1:4], ["34", "2", "8.2088"])
        self.assertEqual(rows["frag_rest"][6], "84de0e9b")
        self.assertEqual(rows["frag_after"][1], "15")
        self.assertEqual(rows["plasma_rest"][1:4], ["29", "2", "7.9716"])
        self.assertEqual(rows["plasma_rest"][6], "4b5c952c")
        self.assertEqual(rows["plasma_after"][1], "61")
        self.assertEqual(rows["stick_rest"][1:3], ["3", "1"])
        self.assertEqual(rows["stick_rest"][6], "25dbfac1")
        self.assertEqual(rows["stick_after"][1], "61")


if __name__ == "__main__":
    unittest.main()
