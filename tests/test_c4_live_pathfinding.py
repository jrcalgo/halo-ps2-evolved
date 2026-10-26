"""C4 item 3: live-unit pathfinding evidence over the unchanged CE path search.

Extracts CE path.c / collision_bsp.c functions by name (unchanged source) into
tests/c4_live_pathfinding_host.c and builds it natively and as ILP32 (clang -m32).
The synthetic grid scenarios and a retail-derived Prisoner breakable scenario must
produce identical output from both builds."""
from pathlib import Path
import json
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
HCU = ROOT / "submodules/halo-ce-universal"
HARNESS = ROOT / "tests/c4_live_pathfinding_host.c"
MARKER = "/* CE_PATH_FUNCTIONS */"
sys.path.insert(0, str(ROOT / "tests"))
from test_hcu_mp_path_consumer import raw_fixture  # noqa: E402

CE_PATH_NAMES = (
    "static void path_state_reset(",
    "static boolean path_heap_verify(",
    "static void path_heap_bubble_up(",
    "static void path_heap_bubble_down(",
    "static short path_heap_pop_cheapest_node(",
    "static void path_heap_insert(",
    "static boolean surface_is_broken(",
    "static boolean path_state_begin(",
    "static short build_path_edges_for_surface(",
    "static boolean path_state_traverse(",
)
PROTOTYPES = """
static void path_state_reset(struct path_state *state);
static boolean path_heap_verify(struct path_state *state);
static void path_heap_bubble_up(struct path_state *state, short location);
static void path_heap_bubble_down(struct path_state *state, short location);
static short path_heap_pop_cheapest_node(struct path_state *state);
static void path_heap_insert(struct path_state *state, short node, short cost);
static boolean surface_is_broken(struct structure_bsp const *structure, long surface_index);
static boolean path_state_begin(struct path_state *state);
static short build_path_edges_for_surface(struct structure_bsp const *structure,
    long surface, struct path_edge *edges);
static boolean path_state_traverse(struct path_state *state);
static struct path_node *path_get_node(struct path_state *state, int16_t index);
static real closest_available_point_on_surface(struct structure_bsp const *structure,
    long surface_index, real_point3d const *point, real_point3d *closest);
static real path_attractor_weight(struct path_state *state, real_point3d const *a,
    real_point3d const *b, real *distance_out);
boolean collision_surface_edge_ring_continues(struct collision_bsp const *, long, short);
boolean collision_bsp_valid_surface_index(struct collision_bsp const *, long);
"""

SYNTHETIC_EXPECTED = (
    "c4-live-path surface_selection.none_start rejected=1 result=passed",
    "c4-live-path surface_selection.below_world rejected=1 result=passed",
    "c4-live-path surface_selection.gate_start_broken start_not_tested=1 result=passed",
    "c4-live-path path_construction.segments_on_route",
    "c4-live-path obstacle_avoidance.gate_blocked",
    "c4-live-path obstacle_avoidance.detour_blocked no_path=1 result=passed",
    "c4-live-path movement_progress ticks=",
    "c4-live-path recovery.stall_replan stall_ticks=30 replans=1",
    "c4-live-path breakable_mutation.destroy_mid_path",
    "c4-live-path breakable_mutation.off_route_control route_unchanged=1 result=passed",
    "c4-live-path summary scenarios=7 result=passed",
)


def extract_function(source_path, marker):
    source = source_path.read_text()
    start = source.index(marker)
    opening = source.index("{", start)
    semicolon = source.find(";", start, opening)
    if semicolon != -1:
        start = source.index(marker, semicolon + 1)
        opening = source.index("{", start)
    depth = 0
    for offset in range(opening, len(source)):
        if source[offset] == "{":
            depth += 1
        elif source[offset] == "}":
            depth -= 1
            if depth == 0:
                return source[start:offset + 1]
    raise AssertionError(f"unterminated function {marker}")


class C4LivePathfindingTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        path_source = HCU / "source/ai/path.c"
        collision_source = HCU / "source/physics/collision_bsp.c"
        ce_path = "\n\n".join(extract_function(path_source, name) for name in CE_PATH_NAMES)
        ce_collision = "\n\n".join(
            extract_function(collision_source, name)
            for name in ("boolean collision_surface_edge_ring_continues(",
                         "boolean collision_bsp_valid_surface_index(")
        )
        generated = HARNESS.read_text().replace(
            MARKER, PROTOTYPES + "\n" + ce_collision + "\n" + ce_path)
        cls.tmp = tempfile.TemporaryDirectory(prefix="c4-live-path-")
        cls.addClassCleanup(cls.tmp.cleanup)
        temporary = Path(cls.tmp.name)
        source = temporary / "c4_live_pathfinding.c"
        source.write_text(generated)
        cls.native = cls.build(source, temporary / "native", [], shutil.which("cc") or "cc")
        clang = shutil.which("clang")
        cls.ilp32 = None
        if clang:
            cls.ilp32 = cls.build(source, temporary / "ilp32",
                                  ["-m32", "-msse2", "-mfpmath=sse"], clang)

    @staticmethod
    def build(source, executable, extra, cc):
        result = subprocess.run(
            [cc, "-std=c99", "-Wall", "-Wextra", "-Werror",
             "-Wno-unused-parameter", "-Wno-unused-but-set-variable", *extra,
             str(source), "-lm", "-o", str(executable)],
            capture_output=True, text=True)
        assert result.returncode == 0, result.stdout + result.stderr
        return executable

    @staticmethod
    def run_exe(executable, args=()):
        run = subprocess.run([str(executable), *args], capture_output=True, text=True)
        return run.returncode, run.stdout + run.stderr

    def runs(self, args=()):
        code, native_out = self.run_exe(self.native, args)
        self.assertEqual(code, 0, native_out)
        if self.ilp32 is None:
            self.skipTest("clang -m32 unavailable; ILP32 parity not run")
        code32, ilp32_out = self.run_exe(self.ilp32, args)
        self.assertEqual(code32, 0, ilp32_out)
        self.assertEqual(native_out, ilp32_out, "ILP32 output diverges from the 64-bit reference")
        return native_out

    def test_synthetic_live_unit_scenarios_native_and_ilp32_agree(self):
        output = self.runs()
        for needle in SYNTHETIC_EXPECTED:
            self.assertIn(needle, output)

    def test_retail_prisoner_breakables_destroyed_route_invariant(self):
        """Retail-derived Prisoner: the eight source breakable surfaces (inventory pinned by
        raw_bsp_sha256) carry no pathfinding walkable bit, so the CE graph never routes
        through them and destroying their breakable indices leaves the route unchanged.
        The C-side check flips every breakable and requires an identical route."""
        fixture = raw_fixture("prisoner")
        inventory = json.loads((ROOT / "build/m2-mp-breakable-inventory-13/inventory.json").read_text())
        prisoner = inventory["maps"]["prisoner"]
        self.assertEqual(prisoner["raw_bsp_sha256"], fixture["raw_bsp_sha256"])
        breakable_index = {row["surface_index"]: row["breakable_index"]
                           for row in prisoner["breakable_surfaces"]}
        payload = bytearray(fixture["payload"])
        surface_count, _edges, _vertices, path_count = (
            int.from_bytes(payload[i * 4:i * 4 + 4], "little") for i in range(4))
        flags = bytes(payload[len(payload) - path_count:])
        # Rebuild surface records with collision flags (bit 3 breakable) and breakable index.
        records = bytearray()
        for surface in range(surface_count):
            first = int.from_bytes(payload[16 + surface * 12 + 4:16 + surface * 12 + 8], "little", signed=True)
            is_breakable = surface in breakable_index
            records += struct.pack("<iiBBh", 0, first, 8 if is_breakable else 0,
                                   breakable_index.get(surface, 0), 9)
        body = bytes(payload[:16]) + bytes(records) + bytes(payload[16 + surface_count * 12:])
        walkable = {s: bool(flags[s] & (1 << 6)) for s in range(surface_count)}
        self.assertFalse(any(walkable[s] for s in breakable_index),
                         "a stock breakable surface carries the walkable bit")
        payload_path = Path(self.tmp.name) / "prisoner-breakable-bsp.bin"
        payload_path.write_bytes(body)
        output = self.runs(["retail", str(payload_path), str(fixture["route_start"]),
                            str(fixture["route_goal"])])
        self.assertIn("c4-live-path retail.breakable_mutation breakables=8 route_unchanged=1 result=passed", output)
        self.assertIn("retail.intact invariants=walkable,unbroken,monotone_cost result=passed", output)
        self.assertEqual(output.count("retail.breakable surface="), 8)

if __name__ == "__main__":
    unittest.main()
