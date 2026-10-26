"""C4 ranges-b member-exact parity: unnamed byte ranges inside CE structs that CE code consumes.

Owner.offset names (ledger members) covered here, with the unnamed range each test varies:
  structure_cluster_portal.<unclassified@0x4>   plane_index / centroid / bounding_radius (consumed); flags, unused (retained)
  structure_cluster.<unclassified@0x0>          sky_index, fog_reference
  structure_mirror.<unclassified@0x0>           plane (consumed) and unused[5] (retained)
  structure_subcluster.<unclassified@0x0>       world_bounds
  predicted_resource.<unclassified@0x2>         resource_index
  structure_surface.<unclassified@0x0>          vertex_indices
  structure_surface_reference.<unclassified@0x4> bsp3d_node_index
  structure_leaf.<unclassified@0x0>             bounds (pad retained)
  structure_leaf.<unclassified@0xa>             surface_reference_count, first_surface_reference_index
  structure_node.<unclassified@0x0>             byte_rectangle3d element of structure_bsp.nodes
  leaf_portal.<unclassified@0x0>                debug draw reader (plane_index, leaf_indices retained by the draw)
  map_leaf_face.<unclassified@0x0>              node_index (leaf_map_leaf_spans_polygon reader; no runtime caller)
  real_point2d.<unclassified@0x0>               x, y of map_leaf_face.vertices (same reader)

Each probe runs verbatim CE bodies (tests/c4_parity_ranges_b_struct_main.c) on synthetic members. The expected
values are computed here from CE's semantics, independent of the C output. Host ILP32 only.
"""
from pathlib import Path
import hashlib
import shutil
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))
sys.path.insert(0, str(ROOT / "tools"))
from host_abi32 import flags as host_abi32_flags, prepare, sysroot  # noqa: E402
import test_hcu_mp_portal_visibility as pv  # noqa: E402

HCU = ROOT / "submodules/halo-ce-universal"
STRUCT_TEMPLATE = ROOT / "tests/c4_parity_ranges_b_struct_main.c"
PREAMBLE = ROOT / "tests/m3_ce_collision_host_preamble.h"
OUT = ROOT / "build/c4-parity-ranges-b"
FLOAT_TOLERANCE = 1e-5

NONE = -1
# (file, marker) pairs; markers are extracted verbatim from the pinned CE tree.
CE_BODIES = (
    ("source/math/geometry.c", "boolean convex_hull2d_test_circle("),
    ("source/math/real_math.c", "boolean point_in_triangle3d("),
    ("source/structures/structures.c", "boolean sphere_intersects_cluster_portal("),
    ("source/structures/structures.c", "boolean structure_render_surface_from_point_and_leaf("),
    ("source/structures/structure_render.c", "static boolean compare_surface_indices("),
    ("source/structures/structure_render.c", "static void structure_render_sort_surface_indices("),
    ("source/structures/structure_render.c", "static void structure_render_dynamic_triangles_from_indices("),
    ("source/structures/structure_visibility.c", "void structure_visibility_find_camera("),
    ("source/scenario/scenario.c", "short scenario_get_fog_region_index("),
    ("source/render/render_cameras.c", "short render_frustum_cube_visible("),
    ("source/structures/leaf_map.c", "void render_debug_leaf_portal("),
    ("source/rasterizer/rasterizer_geometry.c", "void environment_vertex_compressed_get_point("),
)
STRUCT_SOURCES = ()


def build_struct_probe():
    """Compile the verbatim CE bodies into one probe executable (ILP32, same flags as the collision lane)."""
    compiler = shutil.which("gcc")
    if not compiler:
        raise unittest.SkipTest("GCC unavailable for C4 ranges-b probes")
    bodies = []
    for relative, marker in CE_BODIES:
        text = (HCU / relative).read_bytes().decode("utf-8", errors="replace")
        bodies.append(pv.extract_c_function(text, marker))
    OUT.mkdir(parents=True, exist_ok=True)
    unit = OUT / "struct_probe_tu.c"
    unit.write_text(STRUCT_TEMPLATE.read_text().replace("/* CE_RB_FUNCTIONS */", "\n\n".join(bodies)))
    executable = OUT / "struct-probe"
    command = [
        compiler, *host_abi32_flags(), "-std=gnu99", "-O2", "-fno-strict-aliasing", "-fshort-wchar",
        "-DHALO_PS2=1", "-D_X86_=1", "-D_STDCALL_SUPPORTED=1",
        "-D__COLLISION_USAGE_H=1",
        "-D__cdecl=", "-D__stdcall=", "-D__fastcall=", "-D__declspec(x)=",
        "-Wno-unused-function", "-Wno-unused-variable", "-Wno-unused-but-set-variable",
        "-I" + str(HCU / "port/ps2/include"),
        "-I" + str(HCU / "port/include/xdk"),
        "-I" + str(HCU / "source/tag_files"),
        "-I" + str(HCU / "source/memory"),
        "-I" + str(HCU / "source/math"),
        "-I" + str(HCU / "source"), "-I" + str(HCU / "source/cseries"),
        "-I" + str(HCU / "source/objects"), "-I" + str(HCU / "source/scenario"),
        "-I" + str(HCU / "source/physics"),
        "-I" + str(ROOT / "src"),
        "-include", str(PREAMBLE),
        "-include", str(HCU / "port/ps2/include/halo_ps2_limits.h"),
        str(unit),
        *[str(HCU / s) for s in STRUCT_SOURCES],
        "-lm", "-o", str(executable),
    ]
    built = subprocess.run(command, capture_output=True, text=True)
    if built.returncode != 0:
        raise AssertionError((built.stdout + built.stderr)[-20000:])
    return executable


def probe(executable, *args):
    run = subprocess.run([str(executable), *map(str, args)], capture_output=True, text=True)
    if run.returncode != 0:
        raise AssertionError(run.stdout + run.stderr)
    return run.stdout.strip()


def fmt(value):
    return f"{float(value):.6f}"


class StructProbeCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.exe = build_struct_probe()

    SQUARE = ["-1", "-1", "0", "1", "-1", "0", "1", "1", "0", "-1", "1", "0"]

    def sphere(self, plane, centroid, radius_bound, point, radius):
        args = ["sphere", plane, *centroid, radius_bound, *point, radius, 4, *self.SQUARE]
        return probe(self.exe, *args)

    def test_structure_cluster_portal_unclassified_0x4_centroid_radius_gate_sphere(self):
        """structure_cluster_portal.<unclassified@0x4>: centroid (+8) and bounding_radius (+20) gate the portal sphere test."""
        # Portal in plane z=0 over the unit square; probe point (1.2,0,0.1) r=0.5 is in reach of the square edge.
        base = self.sphere(0, [0, 0, 0], 2.0, [1.2, 0, 0.1], 0.5)
        self.assertEqual(base, "SPHERE 1")
        self.assertEqual(self.sphere(0, [50, 0, 0], 2.0, [1.2, 0, 0.1], 0.5), "SPHERE 0")
        self.assertEqual(self.sphere(0, [0, 0, 0], 0.5, [1.2, 0, 0.1], 0.5), "SPHERE 0")

    def test_structure_cluster_portal_unclassified_0x4_plane_index_selects_plane(self):
        """structure_cluster_portal.<unclassified@0x4>: plane_index (+4) selects the bsp3d plane; out of range is not intersected."""
        self.assertEqual(self.sphere(0, [0, 0, 0], 2.0, [1.2, 0, 0.1], 0.5), "SPHERE 1")
        self.assertEqual(self.sphere(5, [0, 0, 0], 2.0, [1.2, 0, 0.1], 0.5), "SPHERE 0")

    def test_structure_cluster_portal_unclassified_0x4_flags_unused_have_no_consumer(self):
        """structure_cluster_portal.<unclassified@0x4>: flags and unused[6] have zero reads in the portal consumers."""
        text = (HCU / "source/structures/structures.c").read_text(errors="replace")
        vis = (HCU / "source/structures/structure_visibility.c").read_text(errors="replace")
        for source in (text, vis):
            self.assertNotIn("portal->flags", source)
            self.assertNotIn("portal->unused", source)

    def test_structure_cluster_unclassified_0x0_sky_index_selects_sky(self):
        """structure_cluster.<unclassified@0x0>: sky_index (+0) is the visible sky of the leaf's cluster."""
        def sky(index):
            return probe(self.exe, "sky", index)
        self.assertEqual(sky(3), "SKY visible=3 model=1 scenario_arg=3")
        self.assertEqual(sky(9), "SKY visible=9 model=0 scenario_arg=9")

    def test_structure_cluster_unclassified_0x0_fog_reference_selects_region(self):
        """structure_cluster.<unclassified@0x0>: fog_reference (+2) names the fog region; out of domain is none."""
        def fog(reference, plane_region, z):
            return probe(self.exe, "fog", reference, 4, plane_region, 0, 0, 0, z)
        self.assertEqual(fog(2, 1, -1), "FOG region=2")
        self.assertEqual(fog(7, 1, -1), "FOG region=-1")
        # plane-flagged reference (bit 15): region is the plane's region when the position is on its negative side
        self.assertEqual(fog(0x8000, 1, -1), "FOG region=1")
        self.assertEqual(fog(0x8000, 1, 1), "FOG region=-1")

    def test_structure_subcluster_unclassified_0x0_world_bounds_cull(self):
        """structure_subcluster.<unclassified@0x0>: world_bounds (24 bytes) is the box render_frustum_cube_visible tests."""
        frustum = [-10, 10, -10, 10, -10, 10]
        self.assertEqual(probe(self.exe, "frustum", *frustum, -1, 1, -1, 1, -1, 1), "FRUSTUM 2")
        self.assertEqual(probe(self.exe, "frustum", *frustum, 20, 30, -1, 1, -1, 1), "FRUSTUM 0")

    def test_structure_surface_unclassified_0x0_vertex_indices_drive_triangles(self):
        """structure_surface.<unclassified@0x0>: vertex_indices (3 words) become the emitted triangle of that surface."""
        base = probe(self.exe, "triangles", 3, 0, 1, 2, 3, 4, 5, 6, 7, 8, 2, 2, 0)
        self.assertEqual(base, "TRIANGLES 0 1 2 6 7 8")
        mutated = probe(self.exe, "triangles", 3, 0, 1, 2, 3, 4, 5, 6, 20, 8, 2, 2, 0)
        self.assertEqual(mutated, "TRIANGLES 0 1 2 6 20 8")
        # surface 1 is not selected: its vertex change must not appear
        other = probe(self.exe, "triangles", 3, 0, 1, 2, 3, 4, 5, 6, 7, 8, 2, 2, 0)
        self.assertEqual(other, base)

    def test_structure_surface_reference_unclassified_0x4_node_index_gates_surface(self):
        """structure_surface_reference.<unclassified@0x4>: bsp3d_node_index (+4) must name a node whose plane is plane_index."""
        def ref(node, plane):
            return probe(self.exe, "surface_reference", node, plane, 0, 0, 0)
        self.assertEqual(ref(0, 0), "SURFACE_REF found=1 surface=0")
        self.assertEqual(ref(-1, 0), "SURFACE_REF found=0 surface=-1")
        self.assertEqual(ref(1, 0), "SURFACE_REF found=0 surface=-1")
        self.assertEqual(ref(1, 1), "SURFACE_REF found=1 surface=0")


# ---------------------------------------------------------------------------------------------------------------
# Retail-map members: the PVS/portal host (tests/c4_parity_ranges_b_host.c, a copy of the PVS lane's instrumented
# host with MIRROR/OFFS/LEAFP/NODEP output added) runs CE's verbatim leaf, node, portal and mirror code on
# bloodgulch from the decompressed retail image, after in-memory byte mutations of one member at a time.
# ---------------------------------------------------------------------------------------------------------------
import os
import re
import struct

RETAIL_TEMPLATE = ROOT / "tests/c4_parity_ranges_b_host.c"
RETAIL_MAP = "bloodgulch"
RETAIL_OUT = ROOT / "build/c4-parity-ranges-b"
LEAF_SIZE = 16          # structure_leaf
NODE_SIZE = 6           # structure_node: byte_rectangle3d
REF_SIZE = 8            # structure_visibility_surface_reference
PORTAL_SIZE = 0x40      # structure_visibility_portal
MIRROR_SIZE = 0x40      # structure_visibility_mirror
CLUSTER_SIZE = 0x68
RETAIL_MARKERS = (
    ("source/structures/structure_visibility.c", "static short bounding_rectangles_intersect("),
    ("source/structures/structure_visibility.c", "static long planes_intersect_rectangle("),
    ("source/structures/structure_visibility.c", "static void grow_clipping_rectangle_by_portal_hull("),
    ("source/structures/structure_visibility.c", "static short portal_hull_from_portal("),
    ("source/structures/structure_visibility.c", "static void structure_visibility_traverse_subclusters("),
    ("source/structures/structure_visibility.c", "static void structure_visibility_traverse_surface_lists("),
    ("source/structures/structure_visibility.c", "static __inline real structure_visibility_dequantize_byte_to_real("),
    ("source/structures/structure_visibility.c", "real_rectangle3d *dequantize_byte_to_real_rectangle3d("),
    ("source/structures/structure_visibility.c", "static short structure_visibility_build_surfaces_traverse_node("),
    ("source/structures/structure_visibility.c", "static short structure_visibility_build_surfaces_traverse_clusters("),
    ("source/structures/structure_visibility.c", "static short structure_visibility_build_surfaces_traverse_leaf("),
    ("source/structures/structure_visibility.c", "short structure_visibility_build_surfaces("),
    ("source/structures/structure_visibility.c", "static void structure_visibility_traverse_cluster("),
    ("source/structures/structure_bsp_definitions.c", "boolean structure_bsp_port_verify("),
    ("source/structures/structure_bsp_definitions.c", "unsigned long *structure_bsp_get_cluster_pvs("),
    ("source/structures/structure_visibility.c", "boolean structure_visibility_find_mirror("),
)


def build_retail_host():
    visibility = (pv.HCU / "source/structures/structure_visibility.c").read_bytes()
    definitions = (pv.HCU / "source/structures/structure_bsp_definitions.c").read_bytes()
    if hashlib.sha256(visibility).hexdigest() != pv.VISIBILITY_SHA256:
        raise AssertionError("structure_visibility.c hash changed")
    if hashlib.sha256(definitions).hexdigest() != pv.BSP_DEFS_SHA256:
        raise AssertionError("structure_bsp_definitions.c hash changed")
    texts = {
        "source/structures/structure_visibility.c": visibility.decode("utf-8"),
        "source/structures/structure_bsp_definitions.c": definitions.decode("utf-8"),
    }
    bodies = "\n\n".join(pv.extract_c_function(texts[rel], marker) for rel, marker in RETAIL_MARKERS)
    RETAIL_OUT.mkdir(parents=True, exist_ok=True)
    unit = RETAIL_OUT / "retail_host_tu.c"
    unit.write_text(RETAIL_TEMPLATE.read_text().replace("/* CE_PORTAL_VISIBILITY_FUNCTIONS */", bodies))
    if not (sysroot() / "usr/lib32/ld-linux.so.2").exists():
        prepare()
    executable = RETAIL_OUT / "retail-host"
    command = [os.environ.get("CC", "gcc"), "-std=gnu99", "-Wall", "-Wextra", "-Werror",
               "-Wno-unused-parameter", "-Wno-unused-variable", *host_abi32_flags(), str(unit), "-lm", "-o", str(executable)]
    compiled = subprocess.run(command, capture_output=True, text=True)
    if compiled.returncode != 0:
        raise AssertionError(compiled.stdout + compiled.stderr)
    return executable


def run_retail(executable, image, raw, name, env_extra=None):
    fixture = RETAIL_OUT / f"{name}.fixture"
    fixture.write_bytes(struct.pack("<4I", pv.FIXTURE_MAGIC, raw["base"], raw["root"], len(image)) + bytes(image))
    env = dict(os.environ)
    env.pop("C4_RB_BOX", None)
    env.pop("C4_RB_LEAF", None)
    env.update(env_extra or {})
    run = subprocess.run([str(executable), str(fixture)], capture_output=True, text=True, env=env)
    return run


def parse_retail(text):
    out = {"LEAFP": None, "NODEP": None, "MIRROR": None, "OFFS": None, "HULL": {}, "STATUS": None}
    for line in text.splitlines():
        if line.startswith("LEAFP "):
            parts = line.split()
            found = int(parts[2].split("=", 1)[1])
            out["LEAFP"] = (int(parts[1]), found, [int(v) for v in parts[3:]])
        elif line.startswith("NODEP "):
            out["NODEP"] = int(line.split("=", 1)[1])
        elif line.startswith("MIRROR "):
            out["MIRROR"] = line
        elif line.startswith("OFFS "):
            out["OFFS"] = {k: int(v) for k, v in (p.split("=") for p in line.split()[1:])}
        elif line.startswith("HULL ") and " reached=" in line:
            parts = line.split()
            out["HULL"][int(parts[1])] = (int(parts[2].split("=", 1)[1]), int(parts[3].split("=", 1)[1]))
        elif line.startswith("HANDOFFPLANE "):
            out.setdefault("HANDOFFPLANE", []).append(line)
        elif line.startswith("STATUS"):
            out["STATUS"] = line
    return out


def dequantize(lo, hi, value):
    if value == 255:
        return hi
    return (hi - lo) * (value / 255.0) + lo


def dequantize_rect(parent, rect):
    px0, px1, py0, py1, pz0, pz1 = parent
    return (dequantize(px0, px1, rect[0]), dequantize(px0, px1, rect[1]),
            dequantize(py0, py1, rect[2]), dequantize(py0, py1, rect[3]),
            dequantize(pz0, pz1, rect[4]), dequantize(pz0, pz1, rect[5]))


def inside(rect, point_box):
    """CE bounding_rectangles_intersect: spanning when the test box is inside the rectangle (interior probe)."""
    return all(rect[2 * i] <= point_box[2 * i] and point_box[2 * i + 1] <= rect[2 * i + 1] for i in range(3))


class RetailLeafNodeParity(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.exe = build_retail_host()
        cls.raw = pv.raw_oracle(RETAIL_MAP)
        cls.image = bytearray(cls.raw["image"])
        cls.base = cls.raw["base"]
        cls.root = cls.raw["root"]
        base_run = run_retail(cls.exe, cls.image, cls.raw, "baseline")
        assert base_run.returncode == 0, base_run.stdout + base_run.stderr
        cls.offs = parse_retail(base_run.stdout)["OFFS"]
        leaves = struct.unpack_from("<iII", cls.image, cls.root + cls.offs["leaves"])
        cls.leaf_count, cls.leaves_at = leaves[0], leaves[1] - cls.base
        nodes = struct.unpack_from("<iII", cls.image, cls.root + cls.offs["nodes"])
        cls.node_count, cls.nodes_at = nodes[0], nodes[1] - cls.base
        refs = struct.unpack_from("<iII", cls.image, cls.root + cls.offs["refs"])
        cls.ref_count, cls.refs_at = refs[0], refs[1] - cls.base
        surfaces = struct.unpack_from("<iII", cls.image, cls.root + cls.offs["surfaces"])
        cls.surface_count = surfaces[0]
        cls.world = struct.unpack_from("<6f", cls.image, cls.root + cls.offs["world"])

    def leaf_at(self, index):
        return self.leaves_at + index * LEAF_SIZE

    def leaf_fields(self, index):
        at = self.leaf_at(index)
        rect = struct.unpack_from("<6B", self.image, at)
        cluster, count, first = struct.unpack_from("<hhi", self.image, at + 8)
        return rect, cluster, count, first

    def refs_of(self, first, count):
        out = []
        for r in range(first, first + count):
            surface, _node = struct.unpack_from("<ii", self.image, self.refs_at + r * REF_SIZE)
            if 0 <= surface < self.surface_count and surface not in out:
                out.append(surface)
        return out

    def probe(self, name, leaf, box, mutate=None):
        image = bytearray(self.image)
        if mutate:
            mutate(image)
        env = {"C4_RB_BOX": ",".join(f"{v:.9f}" for v in box), "C4_RB_LEAF": str(leaf)}
        run = run_retail(self.exe, image, self.raw, name, env)
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
        return parse_retail(run.stdout)

    def pick_target(self):
        """A leaf with surface references whose dequantized bounds (parent = world) have room for a probe box."""
        for index in range(self.leaf_count):
            rect, _cluster, count, first = self.leaf_fields(index)
            if count < 2:
                continue
            bounds = dequantize_rect(self.world, rect)
            cx = [(bounds[2 * i] + bounds[2 * i + 1]) / 2 for i in range(3)]
            half = [(bounds[2 * i + 1] - bounds[2 * i]) / 8 for i in range(3)]
            if min(half) <= 0:
                continue
            box = (cx[0] - half[0], cx[0] + half[0], cx[1] - half[1], cx[1] + half[1],
                   cx[2] - half[2], cx[2] + half[2])
            if self.refs_of(first, count):
                return index, box, bounds
        raise AssertionError("no retail leaf with references and room for a probe box")

    def test_structure_leaf_unclassified_0x0_bounds_gate_surface_walk(self):
        """structure_leaf.<unclassified@0x0>: bounds (byte_rectangle3d, dequantized against the parent) gate the leaf walk."""
        target, box, bounds = self.pick_target()
        rect, _cluster, count, first = self.leaf_fields(target)
        expected = self.refs_of(first, count) if inside(bounds, box) else []
        base = self.probe("leaf_bounds_base", target, box)
        self.assertEqual(base["LEAFP"][0], target)
        self.assertEqual(base["LEAFP"][1], len(expected))
        self.assertEqual(base["LEAFP"][2], expected)
        # Mutation: bounds bytes to the parent minimum corner, a degenerate box disjoint from the probe.
        def zero_bounds(image):
            image[self.leaf_at(target):self.leaf_at(target) + 6] = bytes(6)
        mutated = self.probe("leaf_bounds_zero", target, box, zero_bounds)
        self.assertEqual(mutated["LEAFP"][1], 0, "leaf bounds moved outside the probe must reject its references")
        # Member-exact: another leaf's walk is unchanged by the mutation of this leaf's bounds.
        other = (target + 1) % self.leaf_count
        _r, _c, ocount, ofirst = self.leaf_fields(other)
        other_base = self.probe("other_base", other, box)
        other_mut = self.probe("other_mut", other, box, zero_bounds)
        self.assertEqual(other_base["LEAFP"], other_mut["LEAFP"])

    def test_structure_leaf_unclassified_0x0_pad_retained_no_result_change(self):
        """structure_leaf.<unclassified@0x0>: pad (word at +6) has no CE access; bytes retained, walk unchanged."""
        target, box, _bounds = self.pick_target()
        base = self.probe("pad_base", target, box)
        def pad(image):
            struct.pack_into("<H", image, self.leaf_at(target) + 6, 0xA5A5)
        mutated = self.probe("pad_mut", target, box, pad)
        self.assertEqual(base["LEAFP"], mutated["LEAFP"])
        image = bytearray(self.image)
        pad(image)
        self.assertEqual(struct.unpack_from("<H", image, self.leaf_at(target) + 6)[0], 0xA5A5)

    def test_structure_leaf_unclassified_0xa_reference_span_gates_surfaces(self):
        """structure_leaf.<unclassified@0xa>: surface_reference_count (+10) and first_surface_reference_index (+12)."""
        target, box, bounds = self.pick_target()
        rect, _cluster, count, first = self.leaf_fields(target)
        def zero_count(image):
            struct.pack_into("<h", image, self.leaf_at(target) + 10, 0)
        mutated = self.probe("count_zero", target, box, zero_count)
        self.assertEqual(mutated["LEAFP"][1], 0, "a leaf with no references yields no surfaces")
        # first index moved to reference 0: the walk now reads the span starting at reference 0.
        def first_zero(image):
            struct.pack_into("<i", image, self.leaf_at(target) + 12, 0)
        expected = self.refs_of(0, count) if inside(bounds, box) else []
        moved = self.probe("first_zero", target, box, first_zero)
        self.assertEqual(moved["LEAFP"][2], expected)

    def test_structure_node_unclassified_0x0_bounds_gate_root_descent(self):
        """structure_node.<unclassified@0x0>: byte_rectangle3d element 0 of structure_bsp.nodes bounds the root descent."""
        target, box, _bounds = self.pick_target()
        base = self.probe("node_base", target, box)
        self.assertGreater(base["NODEP"], 0, "probe box must be reachable from the root node")
        def zero_root(image):
            image[self.nodes_at:self.nodes_at + NODE_SIZE] = bytes(NODE_SIZE)
        mutated = self.probe("node_zero", target, box, zero_root)
        self.assertEqual(mutated["NODEP"], 0, "root node box moved outside the probe must end the descent")


class RetailPortalMirrorParity(unittest.TestCase):
    """structure_cluster_portal (plane_index, flags, unused) and structure_mirror (plane, unused) on retail bloodgulch."""

    @classmethod
    def setUpClass(cls):
        cls.exe = build_retail_host()
        cls.raw = pv.raw_oracle(RETAIL_MAP)
        cls.image = bytearray(cls.raw["image"])
        cls.base = cls.raw["base"]
        cls.root = cls.raw["root"]
        base_run = run_retail(cls.exe, cls.image, cls.raw, "portal_baseline")
        assert base_run.returncode == 0, base_run.stdout + base_run.stderr
        cls.baseline = parse_retail(base_run.stdout)
        ptr = struct.unpack_from("<iI", cls.image, cls.root + 0x154)
        cls.portal_count, cls.portals_at = ptr[0], ptr[1] - cls.base
        ptr = struct.unpack_from("<iI", cls.image, cls.root + 0x134)
        cls.cluster_count, cls.clusters_at = ptr[0], ptr[1] - cls.base

    def run_image(self, name, image, env=None):
        run = run_retail(self.exe, image, self.raw, name, env)
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
        return run.stdout, parse_retail(run.stdout)

    def target_portal(self):
        for index in range(self.portal_count):
            entry = self.portals_at + index * PORTAL_SIZE
            vcount = struct.unpack_from("<i", self.image, entry + 0x34)[0]
            if vcount >= 3 and self.baseline["HULL"].get(index, (0, 0))[1] == 1:
                return index, entry
        raise AssertionError("no retail cluster portal with a hull")

    def test_structure_cluster_portal_unclassified_0x4_plane_index_selects_hull(self):
        """structure_cluster_portal.<unclassified@0x4>: plane_index (+4) selects the portal plane; out of range -> discarded."""
        target, entry = self.target_portal()
        image = bytearray(self.image)
        struct.pack_into("<i", image, entry + 4, 0x7FFFFFFF)
        run = run_retail(self.exe, image, self.raw, "portal_plane_bad")
        # rc 6: the host's end-of-run check requires every portal to reach the hull builder; exactly one fewer
        # (the mutated portal, discarded by CE's plane-index check) is the expected consumer outcome.
        self.assertEqual(run.returncode, 6, run.stdout + run.stderr)
        m = re.search(r"plane=(\d+)/(\d+)", run.stderr)
        self.assertIsNotNone(m, run.stderr)
        self.assertEqual(int(m.group(1)), int(m.group(2)) - 1)
        got = parse_retail(run.stdout)
        self.assertEqual(self.baseline["HULL"][target][1], 1, "baseline portal reaches the hull builder")
        self.assertEqual(got["HULL"][target][1], 0, "CE returns before the hull builder for an out-of-range plane")
        for index, value in self.baseline["HULL"].items():
            if index != target:
                self.assertEqual(got["HULL"][index], value, f"portal {index} must not change")

    def test_structure_cluster_portal_unclassified_0x4_flags_unused_retained_no_result_change(self):
        """structure_cluster_portal.<unclassified@0x4>: flags (+24) and unused[6] (+28..52) have no CE read; retained, hulls unchanged."""
        target, entry = self.target_portal()
        image = bytearray(self.image)
        struct.pack_into("<I", image, entry + 24, 0xFFFFFFFF)
        for i in range(6):
            struct.pack_into("<i", image, entry + 28 + 4 * i, 0x5A5A0000 + i)
        _out, got = self.run_image("portal_flags_unused", image)
        self.assertEqual(got["HULL"], self.baseline["HULL"])
        self.assertEqual(got["HANDOFFPLANE"] if "HANDOFFPLANE" in got else [],
                         self.baseline.get("HANDOFFPLANE", []))
        self.assertIn("bytes_same=1", _out)

    def test_structure_mirror_unclassified_0x0_plane_is_mirror_result_plane(self):
        """structure_mirror.<unclassified@0x0>: plane (bytes 0..16) is copied into the mirror result by CE."""
        image = self.synthetic_mirror_image(plane=(0.0, 0.0, 1.0, 0.0))
        out, got = self.run_image("mirror_base", image, {"C4_ALLOW_MIRRORS": "1"})
        base_line = next(l for l in out.splitlines() if l.startswith("HANDOFFPLANE 100000 "))
        self.assertIn("n=0.000000,0.000000,1.000000 d=0.000000", base_line)
        mutated = bytearray(image)
        struct.pack_into("<f", mutated, self.mirror_at + 12, 0.5)
        out2, _ = self.run_image("mirror_plane_d", mutated, {"C4_ALLOW_MIRRORS": "1"})
        line = next(l for l in out2.splitlines() if l.startswith("HANDOFFPLANE 100000 "))
        self.assertIn("n=0.000000,0.000000,1.000000 d=0.500000", line, "CE must hand the mutated mirror plane on")

    def test_structure_mirror_unclassified_0x0_unused_retained_no_result_change(self):
        """structure_mirror.<unclassified@0x0>: unused[5] (bytes 16..36) has no CE access; retained, result unchanged."""
        image = self.synthetic_mirror_image(plane=(0.0, 0.0, 1.0, 0.0))
        out, _ = self.run_image("mirror_unused_base", image, {"C4_ALLOW_MIRRORS": "1"})
        mutated = bytearray(image)
        for i in range(5):
            struct.pack_into("<i", mutated, self.mirror_at + 16 + 4 * i, 0x5A5A0000 + i)
        out2, _ = self.run_image("mirror_unused", mutated, {"C4_ALLOW_MIRRORS": "1"})
        self.assertEqual([l for l in out.splitlines() if l.startswith("HANDOFF")],
                         [l for l in out2.splitlines() if l.startswith("HANDOFF")])
        self.assertIn("bytes_same=1", out2)

    def synthetic_mirror_image(self, plane):
        """Mirror appended to cluster 0 (as the PVS lane's mirror test does), three points in its own plane."""
        image = bytearray(self.image)
        mirror_off = len(image)
        points_off = mirror_off + MIRROR_SIZE
        pts = [(-10.0, -10.0, 0.0), (10.0, -10.0, 0.0), (0.0, 10.0, 0.0)]
        image += bytes(MIRROR_SIZE + 12 * len(pts))
        struct.pack_into("<4f", image, mirror_off, *plane)
        for i, (x, y, z) in enumerate(pts):
            struct.pack_into("<fff", image, points_off + 12 * i, x, y, z)
        struct.pack_into("<iI", image, mirror_off + 0x34, len(pts), self.base + points_off)
        struct.pack_into("<iI", image, self.clusters_at + 0x50, 1, self.base + mirror_off)
        self.mirror_at = mirror_off
        return bytes(image)


PREDICTED_RB_TEMPLATE = ROOT / "tests/c4_parity_ranges_b_predicted_main.c"


class PredictedResourceIndexParity(unittest.TestCase):
    """predicted_resource.<unclassified@0x2>: resource_index (+2) selects the bitmap in the tag group."""

    def test_structure_cluster_predicted_resource_unclassified_0x2_resource_index(self):
        from test_c4_parity_pvs import PREDICTED_TEMPLATE  # noqa: F401  (same CE precache body as the PVS lane)
        source_bytes = (HCU / "source/cache/predicted_resources.c").read_bytes()
        text = source_bytes.decode()
        bodies = "\n".join([
            pv.extract_c_function(text, "static boolean predicted_resource_valid("),
            pv.extract_c_function(text, "void predicted_resources_precache("),
        ])
        OUT_PRED = RETAIL_OUT
        OUT_PRED.mkdir(parents=True, exist_ok=True)
        source = OUT_PRED / "predicted_rb.c"
        executable = OUT_PRED / "predicted_rb"
        source.write_text(PREDICTED_RB_TEMPLATE.read_text().replace("/* CE_PREDICTED_RESOURCES_FUNCTIONS */", bodies))
        compiled = subprocess.run([os.environ.get("CC", "cc"), "-std=c99", "-Wall", "-Wextra", "-Werror",
                                   "-Wno-unused-function", "-Wno-unused-parameter", "-Wno-unused-variable",
                                   str(source), "-o", str(executable)], capture_output=True, text=True)
        self.assertEqual(compiled.returncode, 0, compiled.stdout + compiled.stderr)
        out = subprocess.run([str(executable)], capture_output=True, text=True).stdout
        got = {line.split(" sinks=", 1)[0][5:]: line.split(" sinks=", 1)[1] for line in out.splitlines() if line.startswith("MODE")}
        # modes 0-3 are the PVS lane's table; mode 4 moves entry 0 to bitmap 0 of group 0 (id 100) and mode 5 to index 2 (invalid).
        self.assertEqual(got["0"], "3 [BITMAP id=101] [SOUND tag=1] [BITMAP id=200]")
        self.assertEqual(got["4"], "3 [BITMAP id=100] [SOUND tag=1] [BITMAP id=200]")
        self.assertEqual(got["5"], "2 [SOUND tag=1] [BITMAP id=200]")


class DebugLeafPortalReaders(unittest.TestCase):
    """leaf_portal.<unclassified@0x0>: the debug draw (render_debug_leaf_portal) reads the vertex block only;
    plane_index and leaf_indices (the 12-byte range) are retained and do not change the emitted draw."""

    @classmethod
    def setUpClass(cls):
        cls.exe = build_struct_probe()

    def test_structure_leaf_portal_unclassified_0x0_debug_draw_retains_plane_and_leaf_indices(self):
        square = ["0", "0", "0", "1", "0", "0", "1", "1", "0", "0", "1", "0"]
        base = probe(self.exe, "debug", 0, 1, 2, 4, *square)
        self.assertEqual(base.splitlines()[-1], "DEBUG lines=4 triangles=2")
        mutated = probe(self.exe, "debug", 7, 5, 6, 4, *square)
        self.assertEqual(mutated, base)


LEAF_TEMPLATE = ROOT / "tests/c4_parity_ranges_b_leaf_main.c"
LEAF_BODIES = (
    ("source/structures/leaf_map.c", "boolean leaf_map_leaf_spans_polygon("),
    ("source/math/geometry.c", "boolean convex_hull2d_test_point("),
)


def build_leaf_probe():
    """Verbatim leaf_map_leaf_spans_polygon (leaf_map.c:566) with CE's convex_hull2d_test_point (geometry.c)."""
    compiler = shutil.which("gcc")
    if not compiler:
        raise unittest.SkipTest("GCC unavailable for C4 ranges-b leaf probe")
    bodies = []
    for relative, marker in LEAF_BODIES:
        text = (HCU / relative).read_bytes().decode("utf-8", errors="replace")
        if relative.endswith(".h"):
            text = text.replace("\r\n", "\n")
        bodies.append(pv.extract_c_function(text, marker))
    OUT.mkdir(parents=True, exist_ok=True)
    unit = OUT / "leaf_probe_tu.c"
    unit.write_text(LEAF_TEMPLATE.read_text().replace("/* CE_RB_FUNCTIONS */", "\n\n".join(bodies)))
    executable = OUT / "leaf-probe"
    command = [
        compiler, *host_abi32_flags(), "-std=gnu99", "-O2", "-fno-strict-aliasing", "-fshort-wchar",
        "-DHALO_PS2=1", "-D_X86_=1", "-D_STDCALL_SUPPORTED=1", "-D__COLLISION_USAGE_H=1",
        "-D__cdecl=", "-D__stdcall=", "-D__fastcall=", "-D__declspec(x)=",
        "-Wno-unused-function", "-Wno-unused-variable", "-Wno-unused-but-set-variable",
        "-I" + str(HCU / "port/ps2/include"), "-I" + str(HCU / "port/include/xdk"),
        "-I" + str(HCU / "source/tag_files"), "-I" + str(HCU / "source/memory"),
        "-I" + str(HCU / "source/math"), "-I" + str(HCU / "source"), "-I" + str(HCU / "source/cseries"),
        "-I" + str(HCU / "source/objects"), "-I" + str(HCU / "source/scenario"),
        "-I" + str(HCU / "source/physics"), "-I" + str(ROOT / "src"),
        "-include", str(PREAMBLE), "-include", str(HCU / "port/ps2/include/halo_ps2_limits.h"),
        str(unit), "-lm", "-o", str(executable),
    ]
    built = subprocess.run(command, capture_output=True, text=True)
    if built.returncode != 0:
        raise AssertionError((built.stdout + built.stderr)[-20000:])
    return executable


class LeafMapSpansPolygonParity(unittest.TestCase):
    """map_leaf_face.<unclassified@0x0> (node_index) and real_point2d.<unclassified@0x0> (x, y of map_leaf_face.vertices).

    Oracle: test plane x=0 against the face square (+-2,+-2) on the face plane z=zf. The two edges that vary in x
    cross x=0 at (0,+-2,zf). The test polygon is [-3,3]^2 in the projection, so the crossing is inside exactly when
    |zf| <= 3 (zf is 0 for plane 0 and 5 for plane 1). Axis order of the projection does not change the answer
    because both coordinates are bounded symmetrically."""

    @classmethod
    def setUpClass(cls):
        cls.exe = build_leaf_probe()

    SQUARE = [(-2, -2), (2, -2), (2, 2), (-2, 2)]

    def spans(self, node, points):
        args = ["spans", node, len(points), *[v for p in points for v in p]]
        out = probe(self.exe, *args)
        self.assertIn(out, ("SPANS 0", "SPANS 1"))
        return out == "SPANS 1"

    def test_map_leaf_face_unclassified_0x0_node_index_selects_face_plane(self):
        """map_leaf_face.<unclassified@0x0>: node_index (+0) selects the face plane through the bsp3d node."""
        self.assertTrue(self.spans(0, self.SQUARE), "face on z=0 crosses x=0 inside the polygon")
        self.assertFalse(self.spans(1, self.SQUARE), "face on z=5 crosses x=0 outside the polygon")

    def test_real_point2d_unclassified_0x0_vertex_coordinates_drive_crossings(self):
        """real_point2d.<unclassified@0x0>: the (x, y) bytes of map_leaf_face.vertices decide the edge crossings."""
        self.assertTrue(self.spans(0, self.SQUARE))
        all_positive = [(1, -2), (3, -2), (3, 2), (1, 2)]
        self.assertFalse(self.spans(0, all_positive), "no edge changes sign across x=0: no crossing")
        # moving one corner across the plane restores a crossing
        moved = [(-2, -2), (2, -2), (2, 2), (1, 2)]
        self.assertTrue(self.spans(0, moved))


def debug_draw_oracle(vertices):
    """CE render_debug_leaf_portal (leaf_map.c:528): fan triangles over vertices 2..n-1 with their edge lines,
    then the two closing lines from vertex 0 to vertex 1 and to vertex n-1. Returns the LINE strings it emits."""
    fmt = lambda p: f"{p[0]:.3f},{p[1]:.3f},{p[2]:.3f}"  # noqa: E731
    lines = []
    n = len(vertices)
    for i in range(2, n):
        lines.append(f"LINE {fmt(vertices[i - 1])} {fmt(vertices[i])}")
    lines.append(f"LINE {fmt(vertices[0])} {fmt(vertices[1])}")
    lines.append(f"LINE {fmt(vertices[0])} {fmt(vertices[n - 1])}")
    return lines


class LeafPortalVerticesParity(unittest.TestCase):
    """leaf_portal.vertices: the vertex block is the only input render_debug_leaf_portal reads."""

    @classmethod
    def setUpClass(cls):
        cls.exe = build_struct_probe()

    def draw(self, vertices):
        args = ["debug", 0, 1, 2, len(vertices)]
        for v in vertices:
            args += [f"{v[0]}", f"{v[1]}", f"{v[2]}"]
        out = probe(self.exe, *args)
        lines = [l for l in out.splitlines() if l.startswith("LINE ")]
        return lines, out.splitlines()[-1]

    def test_leaf_portal_vertices_drive_debug_draw(self):
        """leaf_portal_vertices: each vertex coordinate lands in the emitted lines exactly as the oracle draws them."""
        cases = [
            [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (1.0, 1.0, 0.0), (0.0, 1.0, 0.0)],
            [(2.5, -1.0, 4.0), (5.0, -1.0, 4.0), (6.0, 2.0, 4.5), (4.0, 3.0, 5.0), (2.0, 1.0, 4.0)],
            [(-3.0, 0.5, 1.0), (3.0, 0.5, 1.0), (0.0, 7.0, -2.0)],
        ]
        for vertices in cases:
            lines, summary = self.draw(vertices)
            self.assertEqual(lines, debug_draw_oracle(vertices))
            self.assertEqual(summary, f"DEBUG lines={len(vertices)} triangles={len(vertices) - 2}")

    def test_leaf_portal_vertices_moved_vertex_changes_only_its_lines(self):
        """leaf_portal_vertices: moving vertex 3 changes exactly the lines that name it."""
        base = [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (1.0, 1.0, 0.0), (0.0, 1.0, 0.0), (-1.0, 0.5, 0.0)]
        moved = list(base)
        moved[3] = (0.0, 2.0, 0.0)
        base_lines, _ = self.draw(base)
        moved_lines, _ = self.draw(moved)
        self.assertEqual(moved_lines, debug_draw_oracle(moved))
        self.assertNotEqual(base_lines, moved_lines)
        self.assertEqual(base_lines[0], moved_lines[0], "lines that do not name vertex 3 are unchanged")


POLY_TEST = [(-3.0, -3.0), (3.0, -3.0), (3.0, 3.0), (-3.0, 3.0)]


def spans_oracle(face, zf=0.0):
    """Independent oracle for leaf_map_leaf_spans_polygon with test plane x=0 and the test square [-3,3]^2 in (y,z).
    Face vertices (x,y) lie on z=zf. An edge crosses x=0 when its endpoints have opposite signs (margin 0.03); the
    crossing is at y = y0 + (y1-y0)*(0-x0)/(x1-x0), and it is accepted when |y| <= 3 and |zf| <= 3 (0.05 margin)."""
    n = len(face)
    for i in range(n):
        x0, y0 = face[i]
        x1, y1 = face[(i + 1) % n]
        if (x0 < -0.03 and x1 > 0.03) or (x0 > 0.03 and x1 < -0.03):
            y = y0 + (y1 - y0) * (0.0 - x0) / (x1 - x0)
            if abs(y) <= 2.95 and abs(zf) <= 2.95:
                return True
    return False


class MapLeafFaceVerticesParity(unittest.TestCase):
    """map_leaf_face.vertices: the real_point2d face vertex block feeds leaf_map_leaf_spans_polygon."""

    @classmethod
    def setUpClass(cls):
        cls.exe = build_leaf_probe()

    def spans(self, node, face):
        args = ["spans", node, len(face), *[v for p in face for v in p]]
        return probe(self.exe, *args) == "SPANS 1"

    def test_map_leaf_face_vertices_drive_span_decision(self):
        """map_leaf_face_vertices: varied face vertex data gives the decision the oracle computes."""
        cases = [
            [(-2.0, -2.0), (2.0, -2.0), (2.0, 2.0), (-2.0, 2.0)],      # crossing at y in [-2,2]
            [(-2.0, 1.0), (2.0, 1.0), (2.0, 2.5), (-2.0, 2.5)],        # crossing at y in [1,2.5]
            [(-2.0, 2.0), (2.0, 2.0), (2.0, 4.0), (-2.0, 4.0)],        # edges cross at y=2 (inside) and y=4 (outside)
            [(1.0, -2.0), (3.0, -2.0), (3.0, 2.0), (1.0, 2.0)],        # no sign change
            [(-1.0, -5.0), (1.0, -5.0), (1.0, 5.0), (-1.0, 5.0)],      # crossing at y=+-5, outside
        ]
        for face in cases:
            self.assertEqual(self.spans(0, face), spans_oracle(face), face)

    def test_map_leaf_face_vertices_moved_corner_changes_decision(self):
        """map_leaf_face_vertices: moving one corner off the test range flips the decision the oracle predicts."""
        inside = [(-2.0, -2.0), (2.0, -2.0), (2.0, 2.0), (-2.0, 2.0)]
        moved = [(-2.0, -2.0), (2.0, -2.0), (2.0, 5.0), (-2.0, 5.0)]
        self.assertTrue(self.spans(0, inside))
        self.assertEqual(self.spans(0, moved), spans_oracle(moved))
