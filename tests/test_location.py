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
from convert_collision import _decompressed, build_pack, location_payload
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
            str(ROOT / "src/game/gun.c"),
            "-lm", "-o", str(cls.exe),
        ], check=True, capture_output=True)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def run_fixture(self, payload, leaf=None):
        path = Path(self.temp.name) / "location.bin"
        path.write_bytes(payload)
        command = [str(self.exe), str(path)]
        if leaf is not None:
            command.append(str(leaf))
        return subprocess.run(command, capture_output=True, text=True)

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

    def test_retail_map_fog_palette_resolves_from_bsp_block_tag_reference(self):
        fog_map = ROOT / "data/retail/weapon-audit-maps/a10.map"
        if not fog_map.is_file():
            self.skipTest("decompressed a10 source map is not in the tree")
        source, raw, bsp = _decompressed(fog_map)
        block = raw[bsp.file_offset:bsp.file_offset + bsp.size]
        root = struct.unpack_from("<I", block)[0] - bsp.address
        region_count, region_address = struct.unpack_from("<II", block, root + 0x184)
        palette_count, palette_address = struct.unpack_from("<II", block, root + 0x190)
        self.assertEqual((region_count, palette_count), (1, 1))
        palette_index = struct.unpack_from(
            "<h", block, region_address - bsp.address + 0x24)[0]
        self.assertEqual(palette_index, 0)
        palette_start = palette_address - bsp.address
        group = block[palette_start + 0x20:palette_start + 0x24][::-1].decode("ascii")
        fog_id, = struct.unpack_from("<I", block, palette_start + 0x2C)
        self.assertEqual(group, "fog ")
        self.assertEqual(source.by_id[fog_id].group, "fog ")
        payload = location_payload(fog_map)
        magic, version, reserved, leaves, clusters, planes, regions = struct.unpack_from(
            "<4sHHIIII", payload)
        self.assertEqual((magic, version, reserved), (b"LOC1", 1, 0))
        self.assertEqual((planes, regions), (1, 1))
        self.assertEqual(len(payload), 24 + leaves * 2 + clusters * 2 + planes * 18 + regions * 8)
        cluster_start = 24 + leaves * 2
        fog_refs = struct.unpack_from("<" + "h" * clusters, payload, cluster_start)
        self.assertTrue(any(reference == -32768 for reference in fog_refs))
        fog_plane_start = cluster_start + clusters * 2
        plane = struct.unpack_from("<h4f", payload, fog_plane_start)
        self.assertEqual(plane[0], 0)
        region_start = fog_plane_start + planes * 18
        water_flag, plane_distance = struct.unpack_from("<B3xf", payload, region_start)
        self.assertEqual(water_flag, 0)
        self.assertEqual(plane_distance, 0.0)

    def test_retail_underwater_fog_tags_load_from_two_campaign_maps(self):
        maps = ROOT / "data/retail/weapon-audit-maps"
        for name, expected_distance in (("b30", 0.0), ("c10", 0.4)):
            source = maps / f"{name}.map"
            if not source.is_file():
                self.skipTest(f"decompressed {name} source map is not in the tree")
            payload = location_payload(source)
            _, _, _, leaves, clusters, planes, regions = struct.unpack_from(
                "<4sHHIIII", payload)
            self.assertGreater(planes, 0)
            self.assertGreater(regions, 0)
            plane_start = 24 + leaves * 2 + clusters * 2
            plane = struct.unpack_from("<h4f", payload, plane_start)
            self.assertEqual(plane[0], 0)
            region_start = plane_start + planes * 18
            water_flag, plane_distance = struct.unpack_from("<B3xf", payload, region_start)
            self.assertEqual(water_flag, 1)
            self.assertAlmostEqual(plane_distance, expected_distance, places=5)
            leaf_clusters = struct.unpack_from("<" + "h" * leaves, payload, 24)
            cluster_refs = struct.unpack_from("<" + "h" * clusters, payload, 24 + leaves * 2)
            water_leaf = next(index for index, cluster in enumerate(leaf_clusters)
                              if cluster >= 0 and
                              (cluster_refs[cluster] & 0xFFFF) & 0x8000 and
                              (cluster_refs[cluster] & 0x7FFF) < planes)
            result = self.run_fixture(payload, water_leaf)
            self.assertEqual(result.returncode, 0, f"{name}: {result.stderr}")
            self.assertEqual(result.stdout.splitlines(), [
                "water-plane 1 0", "underwater-fire 0 dry-fire 1"], name)


if __name__ == "__main__":
    unittest.main()
