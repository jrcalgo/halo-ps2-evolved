"""Host segment test against the Blood Gulch collision BSP."""
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "submodules" / "halo-ps2" / "tools"))
MAP = ROOT / "data/retail/convert/bloodgulch/decompressed/bloodgulch.map"


def collision_fixture(path: Path) -> bytes:
    sys.path.insert(0, str(ROOT / "tools"))
    from convert_collision import collision_payload
    payload, _tags = collision_payload(path)
    return payload


class Collide(unittest.TestCase):
    def test_spawns_sit_on_the_collision_surface(self):
        if not MAP.is_file():
            self.skipTest("decompressed Blood Gulch is not in the tree")
        with tempfile.TemporaryDirectory() as temp:
            fixture = Path(temp) / "bsp"
            fixture.write_bytes(collision_fixture(MAP))
            exe = Path(temp) / "collide"
            subprocess.run(
                ["cc", "-std=c11", "-Wall", "-Wextra", "-Werror",
                 "-I" + str(ROOT / "src"),
                 str(ROOT / "tests/collide_main.c"),
                 str(ROOT / "src/game/collide.c"),
                 "-o", str(exe)],
                check=True, capture_output=True)
            out = subprocess.run([str(exe), str(fixture)], check=True, capture_output=True, text=True)
        lines = [line for line in out.stdout.splitlines() if line]
        self.assertEqual(len(lines), 71)
        for index, line in enumerate(lines):
            kind, *nums = line.split()
            self.assertEqual(kind, "hit", index)
            ground, spawn = float(nums[1]), float(nums[2])
            self.assertLess(ground, spawn + 2.0)
            # The open starts sit on the surface. Later starts can be
            # inside a base, so the first surface downward is farther.
            if index < 12:
                self.assertLess(ground, spawn)
                self.assertLess(abs(ground - spawn), 0.002)


if __name__ == "__main__":
    unittest.main()
