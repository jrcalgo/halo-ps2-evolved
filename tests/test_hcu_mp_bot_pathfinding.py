"""Exercise unchanged CE actor path search on a synthetic MP collision graph."""
from pathlib import Path
import os
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
HCU = ROOT / "submodules/halo-ce-universal"
import sys
sys.path.insert(0, str(ROOT / "tests"))
from test_hcu_mp_path_consumer import MP_MAPS, raw_fixture  # noqa: E402


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


class MultiplayerBotPathfindingTest(unittest.TestCase):
    def test_stock_mp_bsps_supply_walkable_surface_graph_inputs(self):
        """CE derives adjacency from collision rings; tag path-edge blocks are empty."""
        for map_name in MP_MAPS:
            with self.subTest(map=map_name):
                data = raw_fixture(map_name)
                self.assertGreater(data["surface_count"], 0)
                self.assertEqual(data["path_count"], data["surface_count"])
                self.assertGreater(data["walkable"], 0)
                self.assertGreater(data["edges"], data["surface_count"])

    def test_actual_ce_a_star_traverses_and_respects_walkability(self):
        path_source = HCU / "source/ai/path.c"
        collision_source = HCU / "source/physics/collision_bsp.c"
        names = (
            "static void path_state_reset(",
            "static boolean path_heap_verify(",
            "static void path_heap_bubble_up(",
            "static void path_heap_bubble_down(",
            "static short path_heap_pop_cheapest_node(",
            "static void path_heap_insert(",
            "static boolean path_state_begin(",
            "static short build_path_edges_for_surface(",
            "static boolean path_state_traverse(",
        )
        ce_path = "\n\n".join(extract_function(path_source, name) for name in names)
        ce_collision = "\n\n".join(
            extract_function(collision_source, name)
            for name in (
                "boolean collision_surface_edge_ring_continues(",
                "boolean collision_bsp_valid_surface_index(",
            )
        )
        prototypes = """
static void path_state_reset(struct path_state *state);
static boolean path_heap_verify(struct path_state *state);
static void path_heap_bubble_up(struct path_state *state, short location);
static void path_heap_bubble_down(struct path_state *state, short location);
static short path_heap_pop_cheapest_node(struct path_state *state);
static void path_heap_insert(struct path_state *state, short node, short cost);
static boolean path_state_begin(struct path_state *state);
static short build_path_edges_for_surface(struct structure_bsp const *structure,
    long surface, struct path_edge *edges);
static boolean path_state_traverse(struct path_state *state);
static struct path_node *path_get_node(struct path_state *state, short node);
static boolean surface_is_broken(struct structure_bsp const *structure, long surface);
static real path_attractor_weight(struct path_state *state, real_point3d const *a,
    real_point3d const *b, real *distance_out);
static real closest_available_point_on_surface(struct structure_bsp const *structure,
    long surface, real_point3d const *point, real_point3d *closest);
boolean collision_surface_edge_ring_continues(struct collision_bsp const *, long, short);
boolean collision_bsp_valid_surface_index(struct collision_bsp const *, long);
"""
        with tempfile.TemporaryDirectory(prefix="hcu-mp-bot-path-") as temporary:
            temporary = Path(temporary)
            generated = temporary / "path_harness.c"
            template = (ROOT / "tests/hcu_mp_bot_pathfinding_host.c").read_text()
            generated.write_text(template.replace(
                "/* CE_PATH_AND_COLLISION_FUNCTIONS */",
                prototypes + "\n" + ce_collision + "\n" + ce_path,
            ))
            executable = temporary / "path-harness"
            compile_result = subprocess.run(
                [os.environ.get("CC", "cc"), "-std=c99", "-Wall", "-Wextra",
                 "-Werror", "-Wno-unused-parameter", "-Wno-unused-but-set-variable",
                 str(generated), "-lm", "-o", str(executable)],
                capture_output=True, text=True,
            )
            self.assertEqual(compile_result.returncode, 0,
                             compile_result.stdout + compile_result.stderr)
            run = subprocess.run([str(executable)], capture_output=True, text=True)
            self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
            self.assertIn("synthetic_walkable nodes=3 target_surface=2 parent=1 result=passed", run.stdout)
            self.assertIn("synthetic_blocked nodes=1 target_unreached=1 result=passed", run.stdout)
            for map_name in MP_MAPS:
                with self.subTest(retail_map=map_name):
                    retail = raw_fixture(map_name)
                    retail_payload = temporary / f"{map_name}-bsp.bin"
                    retail_payload.write_bytes(retail["payload"])
                    retail_run = subprocess.run(
                        [str(executable), str(retail_payload),
                         str(retail["route_start"]), str(retail["route_goal"])],
                        capture_output=True, text=True,
                    )
                    self.assertEqual(retail_run.returncode, 0,
                                     retail_run.stdout + retail_run.stderr)
                    line = next((row for row in retail_run.stdout.splitlines()
                                 if " retail_bsp " in row), "")
                    self.assertTrue(line, retail_run.stdout)
                    fields = dict(token.split("=", 1) for token in line.split()[2:]
                                  if "=" in token)
                    self.assertEqual(int(fields["start"]), retail["route_start"])
                    self.assertEqual(int(fields["goal"]), retail["route_goal"])
                    self.assertLessEqual(int(fields["depth"]), 1023)
                    route = [int(value) for value in fields["path"].split(",")]
                    route.reverse()  # CE reports destination-to-root parent order.
                    self.assertEqual(route[0], retail["route_start"])
                    self.assertEqual(route[-1], retail["route_goal"])
                    self.assertEqual(len(route) - 1, int(fields["depth"]))
                    for source, destination in zip(route, route[1:]):
                        self.assertIn(destination, retail["walkable_adjacency"][source],
                                      f"{map_name}: CE route uses non-retail edge {source}->{destination}")
                    self.assertIn("result=passed", line)


if __name__ == "__main__":
    unittest.main()
