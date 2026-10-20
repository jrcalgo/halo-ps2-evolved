"""CE point-to-cluster fog lookup for underwater projectile and weapon gates."""
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "submodules/halo-ps2/tools"))
from halo2ps2.hp2 import parse as parse_hp2
from convert_collision import build_pack, location_payload
from test_collide import MAP


def synthetic_location():
    return (struct.pack("<4sHHIIII", b"LOC1", 1, 0, 3, 3, 1, 2) +
            struct.pack("<3h", 0, 1, 2) +
            struct.pack("<3h", -32768, 1, -1) +
            struct.pack("<h4f", 0, 0.0, 0.0, 1.0, 0.0) +
            struct.pack("<B3xf", 1, 0.25) + struct.pack("<B3xf", 1, 0.0))


class Location(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.exe = Path(cls.temp.name) / "location"
        subprocess.run([
            "cc", "-std=c11", "-Wall", "-Wextra", "-Werror",
            "-I" + str(ROOT / "src"), str(ROOT / "tests/location_main.c"),
            str(ROOT / "src/game/collide.c"), str(ROOT / "src/game/collpack.c"),
            "-lm", "-o", str(cls.exe),
        ], check=True, capture_output=True)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def run_fixture(self, payload):
        path = Path(self.temp.name) / "location.bin"
        path.write_bytes(payload)
        return subprocess.run([str(self.exe), str(path)], capture_output=True, text=True)

    def test_fog_plane_and_direct_fog_reference_match_ce_boundary(self):
        result = self.run_fixture(synthetic_location())
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.splitlines(), ["plane 1 0", "direct 1", "none 0"])

    def test_malformed_fog_plane_reference_is_rejected(self):
        payload = bytearray(synthetic_location())
        struct.pack_into("<h", payload, 24 + 6, -32767)  # plane index 1, but only one plane
        self.assertEqual(self.run_fixture(payload).returncode, 4)

    def test_blood_gulch_location_pack_is_explicitly_dry(self):
        if not MAP.is_file():
            self.skipTest("decompressed Blood Gulch is not in the tree")
        payload = location_payload(MAP)
        magic, version, reserved, leaves, clusters, planes, regions = struct.unpack_from("<4sHHIIII", payload)
        self.assertEqual((magic, version, reserved), (b"LOC1", 1, 0))
        self.assertEqual((leaves, clusters, planes, regions), (5999, 30, 0, 0))
        refs = struct.unpack_from("<" + "h" * clusters, payload, 24 + leaves * 2)
        self.assertEqual(set(refs), {-1})
        pack = parse_hp2(build_pack(MAP))
        self.assertEqual(pack.read("LOC1"), payload)


if __name__ == "__main__":
    unittest.main()
