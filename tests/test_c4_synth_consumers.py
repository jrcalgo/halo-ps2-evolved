"""C4 consumer-level parity for the synthetic nonempty BSP fixtures (see c4_synth_consumer_oracle.py).

Each test decodes a walker-validated fixture, runs the verbatim CE consumer over the decoded values,
and compares its output with an independent Python oracle. Varied inputs are named in each test.
"""
import re
import struct
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))
import c4_synth_consumer_oracle as co  # noqa: E402

SCAN_ROOTS = [
    ROOT / "src",
    ROOT / "submodules/halo-ce-universal/source",
    ROOT / "submodules/halo-ce-universal/port",
    ROOT / "submodules/halo-ps2",
]
# Runtime scope: the parent game source, the CE source and port trees and the halo-ps2 engine. tools/ and
# tests/ hold audit scripts and host mirror structs that name the member as data; they are not readers.
SCAN_SUFFIXES = {".c", ".h", ".cc", ".cpp", ".hpp", ".py", ".inl"}
SCAN_EXCLUDE = re.compile(r"(test_c4_synth_consumers\.py|c4_synth_consumer_|build/|/fixtures/)")


def mutate_block_element(image, field_route, offset_in_element, fmt, value):
    kind, count, addr, size, _ = co.resolve(image, field_route)
    assert kind == "block" and count == 1
    struct.pack_into(fmt, image, addr + offset_in_element, value)
    return co.validated(image)


class LeafMapConsumerTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.leaf_text = co.leaf_bodies()
        cls.portal_fixture = co.fixture_image("leaf_map.portals")

    def _check(self, leaves, portals, ops):
        stdin = co.leaf_case_text(leaves, portals, ops)
        got = co.parse_stdout_to_lines(co.run_harness("leaf", self.leaf_text, stdin))
        expected = co.oracle_leaf(leaves, portals, ops)
        self.assertEqual(got, expected)
        return got

    def test_map_leaf_portal_designators_fixture_value_and_varied(self):
        route = co.route_of("map_leaf.portal_designators")
        base = co.fixture_image("map_leaf.portal_designators")
        self.assertEqual(co.decode_designators(base), [0])  # fixture: one designator, portal 0, open
        portal = [{"leaf_indices": (0, 0), "vertices": 0}]
        ops = ["CLOSED 0", "CLOSE 0", "CLOSED 0"]
        # fixture value: close sets the designator, leaf reads closed
        got = self._check([{"designators": [0], "faces": 0}], portal, ops)
        self.assertEqual(got, ["CLOSED 0 0", "CLOSE 0", "CLOSED 0 1"])
        # varied: designator already closed (sign bit set): stays closed, no assert
        image = mutate_block_element(bytearray(base), route, 0, "<i", -0x80000000)
        self.assertEqual(co.decode_designators(image), [-0x80000000])
        self._check([{"designators": co.decode_designators(image), "faces": 0}], portal, ops)
        # varied: designator names another portal: close finds nothing on both sides and asserts
        image = mutate_block_element(bytearray(base), route, 0, "<i", 1)
        self.assertEqual(co.decode_designators(image), [1])
        got = self._check([{"designators": co.decode_designators(image), "faces": 0}], portal, ops)
        self.assertIn("ASSERT 673", got)

    def test_leaf_map_leaves_fixture_with_portals_fixture(self):
        leaves_image = co.fixture_image("leaf_map.leaves")
        elems = co.elements(leaves_image, "leaf_map.leaves")
        self.assertEqual(len(elems), 1)
        leaf = co.decode_leaf_element(elems[0])
        self.assertEqual((leaf["faces"], leaf["designators_count"]), (0, 0))
        portal_elems = co.elements(self.portal_fixture, "leaf_map.portals")
        portal = co.decode_portal_element(portal_elems[0])
        self.assertEqual(portal["leaf_indices"], (0, 0))
        # the leaf has no designators: close asserts on each side and the leaf stays open
        got = self._check([{"designators": [], "faces": 0}],
                          [{"leaf_indices": portal["leaf_indices"], "vertices": 0}],
                          ["CLOSE 0", "CLOSED 0"])
        self.assertEqual(got, ["CLOSE 0", "ASSERT 673", "ASSERT 673", "CLOSED 0 0"])

    def test_leaf_map_portals_fixture_with_varied_leaf_indices(self):
        portal_elem = co.elements(self.portal_fixture, "leaf_map.portals")[0]
        self.assertEqual(co.decode_portal_element(portal_elem)["leaf_indices"], (0, 0))
        route = co.route_of("leaf_map.portals")
        image = mutate_block_element(bytearray(self.portal_fixture), route, 8, "<i", 1)  # leaf_indices[1] = 1
        decoded = co.decode_portal_element(co.elements(image, "leaf_map.portals")[0])
        self.assertEqual(decoded["leaf_indices"], (0, 1))
        # leaves are test-supplied companions (the portal fixture carries no leaves): both designate portal 0
        leaves = [{"designators": [0], "faces": 0}, {"designators": [0], "faces": 0}]
        portals = [{"leaf_indices": decoded["leaf_indices"], "vertices": decoded["vertices"]}]
        got = self._check(leaves, portals, ["CLOSE 0", "CLOSED 0", "CLOSED 1"])
        self.assertEqual(got, ["CLOSE 0", "CLOSED 0 1", "CLOSED 1 1"])

    def test_map_leaf_faces_fixture_bounds(self):
        faces_image = co.fixture_image("map_leaf.faces")
        leaf_elem = co.elements(faces_image, "map_leaf.faces") and co.elements(faces_image, "leaf_map.leaves")[0]
        leaf = co.decode_leaf_element(leaf_elem)
        self.assertEqual(leaf["faces"], 1)
        face = co.decode_face_element(co.elements(faces_image, "map_leaf.faces")[0])
        self.assertEqual(face, {"node": 0, "vertices": 0})
        # fixture: one face with no vertices contributes nothing; bounds equal the no-face leaf
        base = self._check([{"designators": [], "faces": 1}], [], ["BOUNDS 0"])
        none = self._check([{"designators": [], "faces": 0}], [], ["BOUNDS 0"])
        self.assertEqual(base, none)
        # varied (test-supplied face counts, all vertexless): identical bounds
        for count in (2, 3):
            self.assertEqual(self._check([{"designators": [], "faces": count}], [], ["BOUNDS 0"]), none)


class MaterialConsumerTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = co.material_bodies()
        cls.image = co.fixture_image("structure_material.uncompressed_vertex_data")
        cls.data = co.decode_material_data(cls.image)

    def _check(self, vc, lc, data):
        got = co.parse_stdout_to_lines(co.run_harness("material", self.text, co.material_stdin(vc, lc, data)))
        self.assertEqual(got, co.oracle_material(vc, lc, data))
        return got

    def test_fixture_data_block_is_read_only_when_vertices_exist(self):
        self.assertEqual(self.data, b"DATA")
        self._check(0, 0, self.data)  # no vertices: the consumer reads no data
        # one environment vertex needs 56 bytes; the 4-byte fixture block is too small: CE overruns
        got = self._check(1, 0, self.data)
        self.assertIn("OVERRUN need=56 have=4", got[1])

    def test_composed_vertex_count_reads_fixture_bytes_at_offset_zero(self):
        composed = self.data + bytes(range(52))  # 56 bytes: test-supplied companion to the fixture payload
        got = self._check(1, 0, composed)
        self.assertTrue(got[1].startswith("COMPRESS count=1 dst_offset=0 dst_bytes=56 BYTES 44 41 54 41"))

    def test_lightmap_vertices_follow_environment_vertices(self):
        self._check(1, 1, bytes(76))  # 56 env + 20 lightmap bytes, test-supplied


class ClusterSurfaceConsumerTest(unittest.TestCase):
    SURFACES = [(0, 1, 2), (0, 1, 5)]
    MATERIAL_VERTICES = 3

    @classmethod
    def setUpClass(cls):
        cls.text = co.cluster_bodies()
        cls.image = co.fixture_image("structure_cluster.surface_indices")
        cls.fixture_list = co.decode_cluster_list(cls.image)

    def _run(self, lst):
        stdin = (f"MATERIALS 1\nM {self.MATERIAL_VERTICES}\nSURFACES {len(self.SURFACES)}\n" +
                 "".join(f"S {a} {b} {c}\n" for a, b, c in self.SURFACES) +
                 f"LIST {len(lst)} " + " ".join(str(v) for v in lst) + "\n")
        got = co.parse_stdout_to_lines(co.run_harness("cluster", self.text, stdin))
        expected = co.cluster_output(lst, self.SURFACES, self.MATERIAL_VERTICES)
        self.assertEqual(got, expected)
        return got

    def test_fixture_element_alone_is_a_no_op(self):
        self.assertEqual(self.fixture_list, [0])
        self.assertEqual(self._run(self.fixture_list), ["RUN", "LIST 0"])

    def test_fixture_lightmap_and_material_with_out_of_material_surface(self):
        got = self._run(self.fixture_list + [0, 2, 0, 1])
        self.assertIn("CORRECT cluster 0's surface 1 is not of its group's material (lightmap 0's 0): none", got)
        self.assertEqual(got[-1], "LIST 0 0 2 0 -1")

    def test_group_longer_than_list_clamps_and_out_of_range_surface_is_skipped(self):
        self.assertEqual(self._run(self.fixture_list + [0, 5, 0])[-1], "LIST 0 0 5 0")
        self.assertEqual(self._run(self.fixture_list + [0, 2, 9, 0])[-1], "LIST 0 0 2 9 0")

    def test_varied_fixture_lightmap_index_breaks_the_list(self):
        route = co.route_of("structure_cluster.surface_indices")
        image = bytearray(self.image)
        kind, count, addr, size, _ = co.resolve(bytes(image), route)
        struct.pack_into("<i", image, addr, 7)  # lightmap 7 is out of range
        image = co.validated(image)
        lst = co.decode_cluster_list(image)
        self.assertEqual(lst, [7])
        self.assertEqual(self._run(lst + [0, 2, 0, 1])[-1], "LIST 7 0 2 0 1")


class PathfindingEdgesScanTest(unittest.TestCase):
    """structure_bsp.pathfinding_edges: no runtime reader in scope. The scan records every mention."""

    def test_scan_finds_only_declarations(self):
        hits = []
        for base in SCAN_ROOTS:
            if base.is_file():
                files = [base]
            else:
                files = [p for p in base.rglob("*") if p.is_file() and p.suffix in SCAN_SUFFIXES]
            for path in files:
                rel = path.relative_to(ROOT).as_posix()
                if SCAN_EXCLUDE.search(rel):
                    continue
                try:
                    text = path.read_text(errors="replace")
                except OSError:
                    continue
                for number, line in enumerate(text.splitlines(), 1):
                    if "pathfinding_edges" in line:
                        hits.append(f"{rel}:{number}")
        self.assertEqual(sorted(hits), [
            "submodules/halo-ce-universal/port/linux/game/tag_schema_collision.c:971",
            "submodules/halo-ce-universal/source/structures/structure_bsp_definitions.h:210",
        ])


if __name__ == "__main__":
    unittest.main()
