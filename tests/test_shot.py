"""Pistol and assault rifle bullets from the Blood Gulch projectile tags."""
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
MAP = ROOT / "data/retail/convert/bloodgulch/decompressed/bloodgulch.map"


def bullet(path, name):
    sys.path[:0] = [str(ROOT / "submodules/halo-ps2/tools")]
    from halo2ps2 import mapinfo, tagindex
    index = tagindex.TagIndex.read(path)
    header = mapinfo.read_header(path)
    with path.open("rb") as handle:
        handle.seek(header.tag_data_offset)
        region = handle.read(header.tag_data_size)
    entry = next(item for item in index.entries if item.group == "proj" and item.path == name)
    data = entry.data_address - index.base
    base = data + 0x17C
    velocity = struct.unpack_from("<I", region, base + 104)[0]
    maximum_range = struct.unpack_from("<f", region, base + 76)[0]
    count, address = struct.unpack_from("<II", region, base + 196)
    responses = [struct.unpack_from("<h", region, address - index.base + i * 160 + 2)[0]
                 for i in range(count)]
    damage_id = struct.unpack_from("<I", region, base + 180)[0]
    damage = next(item for item in index.entries if item.tag_id == damage_id)
    point = damage.data_address - index.base
    lower, upper = struct.unpack_from("<ff", region, point + 468)
    return velocity, maximum_range, responses, lower, upper


class Shot(unittest.TestCase):
    def test_bullet_flight_hit_and_damage(self):
        if not MAP.is_file():
            self.skipTest("decompressed Blood Gulch is not in the tree")
        pistol = bullet(MAP, r"weapons\pistol\bullet")
        rifle = bullet(MAP, r"weapons\assault rifle\bullet")
        self.assertEqual(pistol[0], 0x41200001)
        self.assertEqual(rifle[0], 0x412CCCCD)
        self.assertEqual(pistol[1], 40.0)
        self.assertEqual(rifle[1], 40.0)
        self.assertEqual((pistol[3], pistol[4]), (25.0, 25.0))
        self.assertEqual((rifle[3], rifle[4]), (10.0, 10.0))
        self.assertEqual((pistol[2][0], pistol[2][9], pistol[2][32]), (0, 3, 2))
        self.assertEqual((rifle[2][0], rifle[2][9], rifle[2][32]), (0, 3, 2))
        with tempfile.TemporaryDirectory() as temp:
            exe = Path(temp) / "shot"
            subprocess.run(
                ["cc", "-std=c11", "-Wall", "-Wextra", "-Werror", "-I" + str(ROOT / "src"),
                 str(ROOT / "tests/shot_main.c"), str(ROOT / "src/game/shot.c"),
                 str(ROOT / "src/game/collide.c"), "-lm", "-o", str(exe)],
                check=True, capture_output=True)
            out = subprocess.run([str(exe)], check=True, capture_output=True, text=True).stdout
        reports = out.splitlines()
        first = [line.split() for line in reports if line.startswith("pistol first")][0]
        self.assertAlmostEqual(float(first[2]), 10.000000954, places=6)
        self.assertAlmostEqual(float(first[3]), -0.0035651792 / 2, places=6)
        self.assertAlmostEqual(float(first[5]), -0.0035651792, places=6)
        range_line = [line.split() for line in reports if line.startswith("pistol range")][0]
        self.assertEqual(range_line[2], "3")
        self.assertAlmostEqual(float(range_line[3]), 40.0, places=3)
        self.assertEqual(range_line[4], "2")
        stop = [line.split() for line in reports if line.startswith("pistol_stop")][0]
        self.assertEqual(stop[2:5], ["0", "1", "5.0000"])
        self.assertEqual(stop[7], "cd305e6a")
        through = [line.split() for line in reports if line.startswith("pistol_through")][0]
        self.assertEqual(through[2:5], ["0", "2", "5.0000"])
        bounce = [line.split() for line in reports if line.startswith("pistol_bounce")][0]
        self.assertEqual(bounce[2], "1")
        self.assertAlmostEqual(float(bounce[4]), 0.0, places=3)
        self.assertAlmostEqual(float(bounce[5]), -10.0, places=3)
        self.assertAlmostEqual(float(bounce[6]), -0.0035651792, places=4)
        body = [line.split() for line in reports if line.startswith("pistol body")][0]
        rifle_body = [line.split() for line in reports if line.startswith("rifle body")][0]
        self.assertEqual(body[3], "25.0")
        self.assertEqual(rifle_body[3], "10.0")
        self.assertEqual(body[5], "25dbfac1")
        self.assertAlmostEqual(float(body[4]), 4.5, places=3)

    def test_pistol_hits_the_spawn_floor(self):
        map_path = ROOT / "data/retail/convert/bloodgulch/decompressed/bloodgulch.map"
        if not map_path.is_file():
            self.skipTest("decompressed Blood Gulch is not in the tree")
        sys.path[:0] = [str(ROOT / "tools")]
        from convert_collision import build_pack
        with tempfile.TemporaryDirectory() as temp:
            fixture = Path(temp) / "collision.hp2"
            fixture.write_bytes(build_pack(map_path))
            exe = Path(temp) / "playshot"
            subprocess.run(
                ["cc", "-std=c11", "-Wall", "-Wextra", "-Werror", "-I" + str(ROOT / "src"),
                 str(ROOT / "tests/play_shot_main.c"),
                 str(ROOT / "src/game/collpack.c"), str(ROOT / "src/game/collide.c"),
                 str(ROOT / "src/game/move.c"), str(ROOT / "src/game/pill.c"),
                 str(ROOT / "src/game/gun.c"), str(ROOT / "src/game/shot.c"),
                 "-lm", "-o", str(exe)],
                check=True, capture_output=True)
            out = subprocess.run([str(exe), str(fixture)], check=True, capture_output=True, text=True).stdout
        line = out.split()
        self.assertEqual(line[1], "hit")
        self.assertEqual(line[5], "11")
        self.assertGreater(float(line[7]), 0.4)
        self.assertLess(float(line[7]), 1.2)


if __name__ == "__main__":
    unittest.main()
