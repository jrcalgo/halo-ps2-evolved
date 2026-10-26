"""C4 structure_bsp.world_bounds parity on the real structure_visibility traversal.

tests/c4_parity_collision_worldbounds_host.c is a copy of the PVS lane's instrumented host
(tests/c4_parity_pvs_portal_host.c) with a build mode that calls the real
structure_visibility_build_surfaces(). That function (structure_visibility.c:1534-1588) hands
&structure->world_bounds to structure_visibility_build_surfaces_traverse_node (:1388) as the root
parent_bounds; every node box is dequantized relative to it. The tests mutate
structure_bsp.world_bounds (ledger offset 200, six floats) in the in-memory retail image and
compare against CE semantics derived from the same source.
"""
from pathlib import Path
import os
import struct
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))
sys.path.insert(0, str(ROOT / "tools"))
import test_hcu_mp_portal_visibility as pv  # noqa: E402
from host_abi32 import flags, prepare, sysroot  # noqa: E402

TEMPLATE = ROOT / "tests/c4_parity_collision_worldbounds_host.c"
OUT = ROOT / "build/c4-parity-collision-worldbounds"
MAP = "bloodgulch"
WORLD_BOUNDS_OFFSET = 200  # structure_bsp.world_bounds (ledger row offset)
SPHERE_RADIUS = 1.9        # below structure_sphere_threshold (2.0): traverse_node path


def build_host():
    visibility = (pv.HCU / "source/structures/structure_visibility.c").read_bytes()
    definitions = (pv.HCU / "source/structures/structure_bsp_definitions.c").read_bytes()
    if pv.hashlib.sha256(visibility).hexdigest() != pv.VISIBILITY_SHA256:
        raise AssertionError("structure_visibility.c hash changed")
    if pv.hashlib.sha256(definitions).hexdigest() != pv.BSP_DEFS_SHA256:
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
        (vtext, "static __inline real structure_visibility_dequantize_byte_to_real("),
        (vtext, "real_rectangle3d *dequantize_byte_to_real_rectangle3d("),
        (vtext, "static short structure_visibility_build_surfaces_traverse_node("),
        (vtext, "static short structure_visibility_build_surfaces_traverse_clusters("),
        (vtext, "static short structure_visibility_build_surfaces_traverse_leaf("),
        (vtext, "short structure_visibility_build_surfaces("),
        (vtext, "static void structure_visibility_traverse_cluster("),
        (dtext, "boolean structure_bsp_port_verify("),
        (dtext, "unsigned long *structure_bsp_get_cluster_pvs("),
        (vtext, "boolean structure_visibility_find_mirror("),
    )
    bodies = "\n\n".join(pv.extract_c_function(s, m) for s, m in markers)
    OUT.mkdir(parents=True, exist_ok=True)
    tu = OUT / "worldbounds_host_tu.c"
    tu.write_text(TEMPLATE.read_text().replace("/* CE_PORTAL_VISIBILITY_FUNCTIONS */", bodies))
    if not (sysroot() / "usr/lib32/ld-linux.so.2").exists():
        prepare()
    executable = OUT / "worldbounds-host"
    command = [os.environ.get("CC", "gcc"), "-std=gnu99", "-Wall", "-Wextra", "-Werror",
               "-Wno-unused-parameter", "-Wno-unused-variable", "-Wno-unused-function",
               *flags(), str(tu), "-lm", "-o", str(executable)]
    compiled = subprocess.run(command, capture_output=True, text=True)
    if compiled.returncode != 0:
        raise AssertionError(compiled.stdout + compiled.stderr)
    return executable


def run_build(executable, image, raw, center, radius):
    fixture = OUT / "fixture.bin"
    fixture.write_bytes(struct.pack("<4I", pv.FIXTURE_MAGIC, raw["base"], raw["root"], len(image)) + bytes(image))
    args = [str(executable), str(fixture)]
    if center is not None:
        args = [str(executable), str(fixture), *[repr(float(c)) for c in center], repr(float(radius))]
    run = subprocess.run(args, capture_output=True, text=True)
    return run


def parse_build(stdout):
    for line in stdout.splitlines():
        if line.startswith("BUILD "):
            parts = line.split()
            return [int(v) for v in parts[2:]], int(parts[1])
    raise AssertionError("no BUILD line:\n" + stdout)


class WorldBoundsParity(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.executable = build_host()
        cls.raw = pv.raw_oracle(MAP)
        cls.image = bytearray(cls.raw["image"])
        cls.root = cls.raw["root"]
        cls.at = cls.root + WORLD_BOUNDS_OFFSET
        cls.bounds = list(struct.unpack_from("<6f", cls.image, cls.at))  # x0 x1 y0 y1 z0 z1
        # Deterministic search (seeded) for a sphere centre where the unmodified CE traversal
        # reaches surfaces, so the mutation tests are not vacuous.
        import random
        rng = random.Random(2)
        best = None
        b = cls.bounds
        for _ in range(200):
            centre = [rng.uniform(b[0], b[1]), rng.uniform(b[2], b[3]), rng.uniform(b[4], b[5])]
            run = run_build(cls.executable, cls.image, cls.raw, centre, SPHERE_RADIUS)
            if run.returncode != 0:
                raise AssertionError(run.stdout + run.stderr)
            _, count = parse_build(run.stdout)
            if best is None or count > best[1]:
                best = (centre, count)
            if count >= 50:
                break
        assert best is not None and best[1] > 0, "no centre reaches surfaces in the baseline"
        cls.center, cls.baseline_count = best

    def run_with(self, bounds):
        image = bytearray(self.image)
        struct.pack_into("<6f", image, self.at, *bounds)
        run = run_build(self.executable, image, self.raw, self.center, SPHERE_RADIUS)
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
        return parse_build(run.stdout)

    def test_control_unchanged_world_bounds_reproduces_baseline(self):
        first = self.run_with(self.bounds)
        second = self.run_with(self.bounds)
        self.assertEqual(first, second)
        self.assertEqual(first[1], self.baseline_count)

    def test_world_bounds_shift_out_of_sphere_culls_everything(self):
        # CE: root node box = dequantize(world_bounds, node[0]) lies inside world_bounds. Shifting
        # world_bounds by more than its x-extent moves every node box past the sphere, so
        # traverse_node's bounding_rectangles_intersect rejects the root and nothing is found.
        baseline_surfaces, baseline_count = self.run_with(self.bounds)
        extent = self.bounds[1] - self.bounds[0]
        shift = 2.0 * extent + 10.0
        shifted = list(self.bounds)
        shifted[0] += shift
        shifted[1] += shift
        found, count = self.run_with(shifted)
        self.assertEqual(count, 0, f"shifted world_bounds still found {found}")
        self.assertEqual(found, [])
        self.assertEqual(baseline_count, self.baseline_count)
        self.assertGreater(baseline_count, 0)
        # restoring the bounds restores the baseline exactly (control inside the same run)
        self.assertEqual(self.run_with(self.bounds), (baseline_surfaces, baseline_count))


if __name__ == "__main__":
    unittest.main()
