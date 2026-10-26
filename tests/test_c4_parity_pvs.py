"""C4 member-exact parity for the PVS / portal / cluster / leaf members.

Two drivers live here:
  * predicted_resource.tag_index: CE predicted_resource_valid() against a tag table keyed by tag_index.
  * PVS members: CE's real structure_visibility / structure_bsp_get_cluster_pvs traversal, compiled from
    the pinned submodule source and run on retail MP BSPs (recipe and raw oracle from
    test_hcu_mp_portal_visibility.py) after in-memory byte mutations of one member at a time.
    tests/c4_parity_pvs_portal_host.c is an instrumented copy that prints the per-cluster visible set,
    the portal records CE read, and the portal hull CE built from each portal's vertices.
"""
from pathlib import Path
import hashlib
import os
import struct
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))
import test_hcu_mp_portal_visibility as pv  # noqa: E402
from host_abi32 import flags, prepare, sysroot  # noqa: E402

SOURCE = ROOT / "submodules/halo-ce-universal/source/cache/predicted_resources.c"
SOURCE_SHA256 = "c2f81e7cab0307a5cb33f2094837556b3638594711a2e88dc187a1ec1c093eb4"
TAG_TEMPLATE = ROOT / "tests/c4_parity_pvs_tag_index_main.c"
PORTAL_TEMPLATE = ROOT / "tests/c4_parity_pvs_portal_host.c"
OUT = ROOT / "build/c4-parity-pvs"
PORTAL_MAP = "bloodgulch"
CLUSTER_UNUSED_OFFSET = 0x160  # root + 0x154 cluster_portals block, long cluster_unused[3] follows at +12


def extract_definition(source: str, marker: str) -> str:
    start = source.index(marker)
    opening = source.index("{", start)
    prototype_end = source.find(";", start, opening)
    if prototype_end >= 0:
        start = source.index(marker, prototype_end + 1)
        opening = source.index("{", start)
    depth = 0
    for position in range(opening, len(source)):
        if source[position] == "{":
            depth += 1
        elif source[position] == "}":
            depth -= 1
            if depth == 0:
                return source[start:position + 1]
    raise AssertionError(f"unterminated CE function {marker}")


class PredictedResourceTagIndexParity(unittest.TestCase):
    def test_ce_validator_tag_index_drives_result_exactly(self):
        source_bytes = SOURCE.read_bytes()
        self.assertEqual(hashlib.sha256(source_bytes).hexdigest(), SOURCE_SHA256)
        function = extract_definition(
            source_bytes.decode(), "static boolean predicted_resource_valid(")
        runner = TAG_TEMPLATE.read_text().replace("/* CE_PREDICTED_RESOURCE_VALID */", function)
        with tempfile.TemporaryDirectory(prefix="c4-pvs-tag-index-") as temp:
            temp = Path(temp)
            source = temp / "main.c"
            executable = temp / "tag-index"
            source.write_text(runner)
            compiled = subprocess.run(
                [os.environ.get("CC", "cc"), "-std=c99", "-Wall", "-Wextra", "-Werror",
                 "-Wno-unused-function", "-Wno-unused-parameter", str(source), "-o", str(executable)],
                capture_output=True, text=True)
            self.assertEqual(compiled.returncode, 0, compiled.stdout + compiled.stderr)
            result = subprocess.run([str(executable)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("C4 predicted_resource.tag_index parity passed", result.stdout)


PREDICTED_TEMPLATE = ROOT / "tests/c4_parity_pvs_predicted_main.c"


def run_c_harness(template_path, marker, bodies, name):
    OUT.mkdir(parents=True, exist_ok=True)
    source = OUT / f"{name}.c"
    executable = OUT / name
    source.write_text(template_path.read_text().replace(marker, bodies))
    compiled = subprocess.run(
        [os.environ.get("CC", "cc"), "-std=c99", "-Wall", "-Wextra", "-Werror",
         "-Wno-unused-function", "-Wno-unused-parameter", "-Wno-unused-variable",
         str(source), "-o", str(executable)],
        capture_output=True, text=True)
    if compiled.returncode != 0:
        raise AssertionError(compiled.stdout + compiled.stderr)
    result = subprocess.run([str(executable)], capture_output=True, text=True)
    if result.returncode != 0:
        raise AssertionError(result.stdout + result.stderr)
    return result.stdout


class ClusterPredictedResourcesParity(unittest.TestCase):
    def test_ce_precache_walks_cluster_list_and_records_sinks(self):
        source_bytes = SOURCE.read_bytes()
        self.assertEqual(hashlib.sha256(source_bytes).hexdigest(), SOURCE_SHA256)
        text = source_bytes.decode()
        bodies = "\n".join([
            extract_definition(text, "static boolean predicted_resource_valid("),
            extract_definition(text, "void predicted_resources_precache("),
        ])
        stdout = run_c_harness(PREDICTED_TEMPLATE, "/* CE_PREDICTED_RESOURCES_FUNCTIONS */", bodies,
                               "c4_predicted_precache")
        got = {line.split(" sinks=", 1)[0][5:]: line.split(" sinks=", 1)[1] for line in stdout.splitlines() if line.startswith("MODE")}
        # Oracle from the synthetic list and CE's validity rules (bitmap: tag group 0 with 2 bitmaps,
        # tag group 2 with 1 bitmap; sound: tag 1; entry 3 index 5 is out of range).
        self.assertEqual(got["0"], "3 [BITMAP id=101] [SOUND tag=1] [BITMAP id=200]")
        self.assertEqual(got["1"], "2 [BITMAP id=101] [BITMAP id=200]")
        self.assertEqual(got["2"], "2 [SOUND tag=1] [BITMAP id=200]")
        self.assertEqual(got["3"], "2 [BITMAP id=101] [SOUND tag=1]")


BACKGROUND_TEMPLATE = ROOT / "tests/c4_parity_pvs_background_main.c"
SCENARIO = ROOT / "submodules/halo-ce-universal/source/scenario/scenario.c"


class BackgroundSoundPaletteParity(unittest.TestCase):
    def test_ce_deafening_lookup_follows_background_sound_entry(self):
        text = SCENARIO.read_text(errors="replace")
        body = extract_definition(text, "boolean scenario_location_deafening(")
        stdout = run_c_harness(BACKGROUND_TEMPLATE, "/* CE_SCENARIO_LOCATION_DEAFENING */", body,
                               "c4_background_sound")
        got = {line.split()[1]: line.split()[2:] for line in stdout.splitlines() if line.startswith("MODE")}
        # Oracle: cluster 0 names palette 0 (definition 0, bit 0 set) -> 1; cluster 1 names palette 1
        # (definition 1, bit 0 clear) -> 0; cluster 2 names palette 2 (NONE) -> 0; cluster 3 has palette
        # index 7, out of range -> 0.
        self.assertEqual(got["0"], ["1", "0", "0", "0"])
        # Mutation: palette entry 1 now names definition 0. Only cluster 1 changes.
        self.assertEqual(got["1"], ["1", "1", "0", "0"])
        # Mutation: palette entry 0 now NONE. Only cluster 0 changes.
        self.assertEqual(got["2"], ["0", "0", "0", "0"])


LEAF_MAP_TEMPLATE = ROOT / "tests/c4_parity_pvs_leaf_map_main.c"
LEAF_MAP_SOURCE = ROOT / "submodules/halo-ce-universal/source/structures/leaf_map.c"


class LeafMapParity(unittest.TestCase):
    def test_ce_close_and_closed_follow_leaf_map_members(self):
        text = LEAF_MAP_SOURCE.read_text(errors="replace")
        bodies = "\n".join([
            extract_definition(text, "void leaf_map_close_portal("),
            extract_definition(text, "boolean leaf_map_leaf_is_closed("),
        ])
        stdout = run_c_harness(LEAF_MAP_TEMPLATE, "/* CE_LEAF_MAP_FUNCTIONS */", bodies, "c4_leaf_map")
        lines = stdout.splitlines()
        # Oracle: leaves 0..2 start open. Closing portal 0 closes its designator on leaf 0 (side 0) and
        # leaf 1 (side 1). Leaf 0 keeps designator 1 open, so only leaf 1 reads closed.
        self.assertEqual(lines, [
            "MODE 0 before 0 0 0",
            "MODE 0 after 0 1 0",
            # Mutation: leaf 1 has no designators, so side 1 finds nothing to close. CE asserts (line 673)
            # and leaf 1 still reads open.
            "MODE 1 before 0 0 0",
            "ASSERT line 673",
            "MODE 1 after 0 0 0",
            # Mutation: portal 0 names leaf 2 on side 1, which has no designator for portal 0.
            "MODE 2 before 0 0 0",
            "ASSERT line 673",
            "MODE 2 after 0 0 0",
        ])


def build_portal_host():
    visibility = (pv.HCU / "source/structures/structure_visibility.c").read_bytes()
    definitions = (pv.HCU / "source/structures/structure_bsp_definitions.c").read_bytes()
    if hashlib.sha256(visibility).hexdigest() != pv.VISIBILITY_SHA256:
        raise AssertionError("structure_visibility.c hash changed")
    if hashlib.sha256(definitions).hexdigest() != pv.BSP_DEFS_SHA256:
        raise AssertionError("structure_bsp_definitions.c hash changed")
    vtext = visibility.decode("utf-8")
    dtext = definitions.decode("utf-8")
    markers = (
        (vtext, "static short bounding_rectangles_intersect("),
        (vtext, "static long planes_intersect_rectangle("),
        (vtext, "static void grow_clipping_rectangle_by_portal_hull("),
        (vtext, "static short portal_hull_from_portal("),
        (vtext, "static void structure_visibility_traverse_subclusters("),
        (vtext, "static void structure_visibility_traverse_surface_lists("),
        (vtext, "static short structure_visibility_build_surfaces_traverse_clusters("),
        (vtext, "static short structure_visibility_build_surfaces_traverse_leaf("),
        (vtext, "static void structure_visibility_traverse_cluster("),
        (dtext, "boolean structure_bsp_port_verify("),
        (dtext, "unsigned long *structure_bsp_get_cluster_pvs("),
        (vtext, "boolean structure_visibility_find_mirror("),
    )
    bodies = "\n\n".join(pv.extract_c_function(s, m) for s, m in markers)
    OUT.mkdir(parents=True, exist_ok=True)
    tu = OUT / "portal_host_tu.c"
    tu.write_text(PORTAL_TEMPLATE.read_text().replace("/* CE_PORTAL_VISIBILITY_FUNCTIONS */", bodies))
    if not (sysroot() / "usr/lib32/ld-linux.so.2").exists():
        prepare()
    executable = OUT / "portal-host"
    command = [os.environ.get("CC", "gcc"), "-std=gnu99", "-Wall", "-Wextra", "-Werror",
               "-Wno-unused-parameter", *flags(), str(tu), "-lm", "-o", str(executable)]
    compiled = subprocess.run(command, capture_output=True, text=True)
    if compiled.returncode != 0:
        raise AssertionError(compiled.stdout + compiled.stderr)
    return executable


def run_fixture(executable, name, image, raw):
    fixture = OUT / f"{name}.fixture"
    fixture.write_bytes(struct.pack("<4I", pv.FIXTURE_MAGIC, raw["base"], raw["root"], len(image)) + image)
    run = subprocess.run([str(executable), str(fixture)], capture_output=True, text=True)
    return run


def parse_lines(text):
    out = {"VIS": {}, "READ": {}, "READP": [], "HULL": {}, "CLUSTER": {}, "STATUS": None}
    for line in text.splitlines():
        parts = line.split()
        if not parts:
            continue
        if parts[0] == "VIS":
            out["VIS"][int(parts[1])] = [int(p) for p in parts[2:]]
        elif parts[0] == "READ":
            out["READ"][int(parts[1])] = [int(p) for p in parts[2:]]
        elif parts[0] == "READP":
            out["READP"].append(tuple(int(p) for p in parts[1:]))
        elif parts[0] == "HULL":
            out["HULL"][int(parts[1])] = line.split(None, 2)[2]
        elif parts[0] == "CLUSTER":
            out["CLUSTER"][int(parts[1])] = {k: v for k, v in (p.split("=", 1) for p in parts[2:])}
        elif parts[0] == "STATUS":
            out["STATUS"] = line
    return out


def parse_handoffs(text):
    out = {}
    for line in text.splitlines():
        if line.startswith("HANDOFF "):
            parts = line.split()
            values = {k: v for k, v in (p.split("=", 1) for p in parts[2:])}
            out.setdefault(int(parts[1]), (int(values["n"]), float(values["x"]),
                                           float(values["y"]), float(values["z"])))
    return out


class PvsMemberParity(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.executable = build_portal_host()
        cls.raw = pv.raw_oracle(PORTAL_MAP)
        cls.image = cls.raw["image"]
        cls.base = cls.raw["base"]
        cls.root = cls.raw["root"]
        ptr = struct.unpack_from("<iI", cls.image, cls.root + 0x154)
        cls.portal_count, cls.portals_at = ptr[0], ptr[1] - cls.base
        ptr = struct.unpack_from("<iI", cls.image, cls.root + 0x134)
        cls.cluster_count, cls.clusters_at = ptr[0], ptr[1] - cls.base
        cls.baseline_run = run_fixture(cls.executable, "baseline", cls.image, cls.raw)
        assert cls.baseline_run.returncode == 0, cls.baseline_run.stdout + cls.baseline_run.stderr
        cls.baseline = parse_lines(cls.baseline_run.stdout)
        layout_line = next(l for l in cls.baseline_run.stdout.splitlines() if l.startswith("LAYOUT "))
        cls.layout = {k: int(v) for k, v in (p.split("=") for p in layout_line.split()[1:])}
        assert cls.baseline["STATUS"] == "STATUS passed", cls.baseline_run.stdout

    def run_mutated(self, name, mutate):
        image = bytearray(self.image)
        mutate(image)
        run = run_fixture(self.executable, name, bytes(image), self.raw)
        return run, parse_lines(run.stdout)

    def test_cluster_unused_bytes_retained_and_not_read(self):
        # CE source must not read cluster_unused (zero-read proof by grep of the pinned tree).
        for source in (pv.HCU / "source").rglob("*.c"):
            text = source.read_text(errors="replace")
            self.assertNotIn("cluster_unused", text, str(source))
        def mutate(image):
            for i in range(3):
                struct.pack_into("<i", image, self.root + CLUSTER_UNUSED_OFFSET + 4 * i, 0x5A5A0000 + i)
        run, got = self.run_mutated("cluster_unused", mutate)
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
        self.assertEqual(got["VIS"], self.baseline["VIS"])
        self.assertEqual(got["READ"], self.baseline["READ"])
        self.assertEqual(got["HULL"], self.baseline["HULL"])
        self.assertEqual(got["CLUSTER"], self.baseline["CLUSTER"])
        self.assertIn("bytes_same=1", run.stdout)

    def test_portal_back_front_swap_changes_read_record(self):
        # structure_cluster_portal.cluster_indices[2]: back/front at entry +0 and +2.
        target = next(i for i in range(self.portal_count)
                      if struct.unpack_from("<hh", self.image, self.portals_at + i * 0x40)[0] !=
                      struct.unpack_from("<hh", self.image, self.portals_at + i * 0x40)[1])
        entry = self.portals_at + target * 0x40
        back, front = struct.unpack_from("<hh", self.image, entry)
        def mutate(image):
            struct.pack_into("<hh", image, entry, front, back)
        run, got = self.run_mutated("portal_swap", mutate)
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
        seen = [rec for rec in got["READP"] if rec[0] == target]
        self.assertTrue(seen, "CE never read the mutated portal")
        for rec in seen:
            self.assertEqual((rec[1], rec[2]), (front, back))
        base_seen = [rec for rec in self.baseline["READP"] if rec[0] == target]
        self.assertTrue(all((rec[1], rec[2]) == (back, front) for rec in base_seen))

    def test_portal_vertices_feed_portal_hull(self):
        # structure_cluster_portal.vertices: CE hands each portal's vertex block to portal_hull_from_points.
        # The host records the first vertex and count CE passed (HANDOFF lines; the hull math itself is stubbed).
        target = 0
        entry = self.portals_at + target * 0x40
        vcount, vaddr = struct.unpack_from("<iI", self.image, entry + 0x34)
        self.assertGreater(vcount, 0)
        voff = vaddr - self.base
        base_x, base_y, base_z = struct.unpack_from("<fff", self.image, voff)
        def mutate(image):
            struct.pack_into("<fff", image, voff, base_x + 500.0, base_y, base_z)
        run, got = self.run_mutated("portal_vertices", mutate)
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
        handoff = parse_handoffs(run.stdout)
        base_handoff = parse_handoffs(self.baseline_run.stdout)
        self.assertEqual(set(handoff), set(base_handoff))
        self.assertIn(target, handoff, "CE never handed portal 0 to the hull builder")
        n, x, y, z = handoff[target]
        self.assertEqual(n, vcount)
        self.assertAlmostEqual(x, base_x + 500.0, places=3)
        self.assertAlmostEqual(y, base_y, places=3)
        self.assertAlmostEqual(z, base_z, places=3)
        for index in base_handoff:
            if index != target:
                self.assertEqual(handoff[index], base_handoff[index])

    def test_cluster_portal_index_order_changes_read_and_hash(self):
        # cluster.portal_indices / portal_index.portal_index: swap the first two listed portal indices.
        count_at = self.clusters_at
        target = None
        for c in range(self.cluster_count):
            entry = self.clusters_at + c * 0x68
            n, addr = struct.unpack_from("<iI", self.image, entry + 0x5C)
            if n >= 2:
                target = (c, addr - self.base, n)
                break
        self.assertIsNotNone(target, "no cluster lists two portals")
        cluster, list_at, n = target
        listed = list(struct.unpack_from(f"<{n}h", self.image, list_at))
        swapped = [listed[1], listed[0]] + listed[2:]
        def mutate(image):
            struct.pack_into(f"<{n}h", image, list_at, *swapped)
        run, got = self.run_mutated("portal_index_swap", mutate)
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
        self.assertEqual(got["READ"][cluster], swapped)
        self.assertEqual(self.baseline["READ"][cluster], listed)
        self.assertEqual(
            got["CLUSTER"][cluster]["pfnv"],
            f"{pv.portal_fnv(swapped, self.raw['portals']):016x}")

    def test_cluster_subclusters_count_drives_surface_set(self):
        # cluster.subclusters: a cluster whose subcluster block is set to count 0 must see no subcluster surfaces.
        target = None
        for c in range(self.cluster_count):
            entry = self.clusters_at + c * 0x68
            n, _addr = struct.unpack_from("<iI", self.image, entry + 0x34)
            if n >= 1 and self.raw["cluster_surfaces"][c]:
                target = (c, entry + 0x34)
                break
        self.assertIsNotNone(target)
        cluster, count_at = target
        def mutate(image):
            struct.pack_into("<i", image, count_at, 0)
        run, got = self.run_mutated("subcluster_zero", mutate)
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
        self.assertEqual(got["CLUSTER"][cluster]["sub"], "0")
        self.assertEqual(
            got["CLUSTER"][cluster]["sfnv"], f"{pv.hash_sorted([]):016x}")

    def test_sound_unused_bytes_retained_and_not_read(self):
        # Zero-read: sound_unused is named only in the CE definition header.
        readers = sorted(str(path.relative_to(ROOT)) for path in (pv.HCU / "source").rglob("*")
                         if path.is_file() and path.suffix in (".c", ".h", ".inl")
                         and "sound_unused" in path.read_text(errors="replace"))
        self.assertEqual(readers, [
            "submodules/halo-ce-universal/source/structures/structure_bsp_definitions.h"])
        offset = self.layout["sound_unused"]
        def mutate(image):
            for i in range(6):
                struct.pack_into("<i", image, self.root + offset + 4 * i, 0x5A5A0000 + i)
        run, got = self.run_mutated("sound_unused", mutate)
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
        self.assertEqual(got["VIS"], self.baseline["VIS"])
        self.assertEqual(got["READ"], self.baseline["READ"])
        self.assertEqual(got["HULL"], self.baseline["HULL"])
        self.assertEqual(got["CLUSTER"], self.baseline["CLUSTER"])
        self.assertIn("bytes_same=1", run.stdout)

    def test_mirror_points_handed_to_portal_hull(self):
        # structure_mirror.points: synthetic mirror appended to cluster 0 (in its own PVS) of the retail BSP.
        pts = [(1.0, 2.0, 3.0), (4.0, 5.0, 6.0), (7.0, 8.0, 9.0)]
        def build(points, count=None):
            image = bytearray(self.image)
            base_size = len(image)
            mirror_off = base_size
            points_off = base_size + 0x40
            image += bytes(0x40 + 12 * len(points))
            for i, (x, y, z) in enumerate(points):
                struct.pack_into("<fff", image, points_off + 12 * i, x, y, z)
            struct.pack_into("<iI", image, mirror_off + 0x34,
                             len(points) if count is None else count, self.base + points_off)
            entry = self.clusters_at + 0x50
            struct.pack_into("<iI", image, entry, 1, self.base + mirror_off)
            return bytes(image)
        def run(name, image):
            return run_fixture(self.executable, name, image, self.raw)
        env = dict(os.environ, C4_ALLOW_MIRRORS="1")
        def run_env(name, image):
            fixture = OUT / f"{name}.fixture"
            fixture.write_bytes(struct.pack("<4I", pv.FIXTURE_MAGIC, self.base, self.root, len(image)) + image)
            return subprocess.run([str(self.executable), str(fixture)], capture_output=True, text=True, env=env)
        base = run_env("mirror_base", build(pts))
        self.assertEqual(base.returncode, 0, base.stdout + base.stderr)
        handoff = parse_handoffs(base.stdout)
        self.assertIn(100000, handoff, "CE never handed the mirror points to the hull builder")
        self.assertEqual(handoff[100000][0], 3)
        self.assertAlmostEqual(handoff[100000][1], 1.0, places=5)
        moved = [(50.0, 2.0, 3.0), pts[1], pts[2]]
        run_moved = run_env("mirror_moved", build(moved))
        self.assertEqual(run_moved.returncode, 0, run_moved.stdout + run_moved.stderr)
        self.assertAlmostEqual(parse_handoffs(run_moved.stdout)[100000][1], 50.0, places=5)
        run_short = run_env("mirror_short", build(pts, count=2))
        self.assertEqual(run_short.returncode, 0, run_short.stdout + run_short.stderr)
        self.assertEqual(parse_handoffs(run_short.stdout)[100000][0], 2)


if __name__ == "__main__":
    unittest.main()
