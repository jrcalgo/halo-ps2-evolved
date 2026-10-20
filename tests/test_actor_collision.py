"""Retail cyborg actor collision-mesh extraction remains node/material aware."""
from collections import Counter
from pathlib import Path
import math
import struct
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
MAP = ROOT / "data/retail/convert/bloodgulch/decompressed/bloodgulch.map"


class ActorCollision(unittest.TestCase):
    def test_cyborg_node_bsp_triangles_keep_ce_indices(self):
        if not MAP.is_file():
            self.skipTest("decompressed Blood Gulch is not in the tree")
        sys.path.insert(0, str(ROOT / "tools"))
        from convert_collision import build_pack, _cyborg_actor_collision, _decompressed

        data, _raw, _location = _decompressed(MAP)
        payload = _cyborg_actor_collision(data)
        magic, version, node_count, triangle_count, node_stride = struct.unpack_from("<4sHHII", payload)
        self.assertEqual((magic, version, node_count, triangle_count, node_stride),
                         (b"ACL1", 2, 19, 236, 36))
        node_offset = struct.calcsize("<4sHHII")
        triangle_offset = node_offset + node_count * node_stride
        self.assertEqual(len(payload), triangle_offset + triangle_count * struct.calcsize("<5h9f"))

        parents = []
        for index in range(node_count):
            record_index, parent, *defaults = struct.unpack_from("<hh8f", payload,
                                                                  node_offset + index * node_stride)
            self.assertEqual(record_index, index)
            self.assertTrue(-1 <= parent < node_count and parent != index)
            self.assertTrue(all(math.isfinite(value) for value in defaults))
            self.assertAlmostEqual(sum(value * value for value in defaults[3:7]), 1.0, places=4)
            parents.append(parent)
        self.assertEqual(parents[0], -1)
        self.assertEqual(parents[12], 9, "head default pose retains the source parent chain")

        node_triangles = Counter()
        material_indices = Counter()
        node_parts = {}
        for offset in range(triangle_offset, len(payload), 46):
            node, region, part, material_index, surface, *vertices = struct.unpack_from(
                "<5h9f", payload, offset)
            self.assertGreaterEqual(node, 0)
            self.assertEqual(region, 0)
            self.assertGreaterEqual(part, 0)
            self.assertIn(material_index, (0, 1, 2, 3))
            self.assertGreaterEqual(surface, 0)
            self.assertTrue(all(math.isfinite(value) for value in vertices))
            self.assertLess(max(abs(value) for value in vertices), 0.25,
                            "node BSP vertices should stay in their source-local space")
            node_triangles[node] += 1
            material_indices[material_index] += 1
            node_parts[node] = part

        self.assertEqual(len(node_triangles), 16)
        self.assertEqual(material_indices, Counter({1: 162, 2: 48, 0: 24, 3: 2}))
        self.assertEqual(node_parts[12], 2, "head collision node retains CE runtime damage part")
        self.assertEqual(node_parts[4], 6, "left-calf collision node retains CE runtime damage part")
        self.assertEqual(node_parts[14], 7, "right-upperarm collision node retains CE runtime damage part")

        pack = build_pack(MAP)
        section_count, = struct.unpack_from("<H", pack, 6)
        actor_section = None
        for index in range(section_count):
            entry = 64 + index * 32
            tag = pack[entry:entry + 4]
            offset, stored, raw, codec = struct.unpack_from("<IIII", pack, entry + 4)
            if tag == b"ACOL":
                self.assertEqual((stored, raw, codec), (len(payload), len(payload), 0))
                actor_section = pack[offset:offset + raw]
        self.assertEqual(actor_section, payload, "HP2 must carry the extracted actor collision section")

        with tempfile.TemporaryDirectory() as temp:
            exe = Path(temp) / "collpack_actor"
            subprocess.run(
                ["cc", "-std=c11", "-Wall", "-Wextra", "-Werror", "-I" + str(ROOT / "src"),
                 str(ROOT / "tests/collpack_actor_main.c"), str(ROOT / "src/game/collpack.c"),
                 "-o", str(exe)], check=True, capture_output=True)
            output = subprocess.run([str(exe)], check=True, capture_output=True, text=True).stdout
        self.assertIn("actor collision pack view ok", output)


if __name__ == "__main__":
    unittest.main()
