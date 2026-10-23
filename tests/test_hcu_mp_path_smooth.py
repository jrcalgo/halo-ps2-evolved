"""Extract CE path_smooth / path_state_build_path on a raw Blood Gulch route."""
from pathlib import Path
import hashlib
import json
import struct
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
HCU = ROOT / "submodules/halo-ce-universal"
OUT = ROOT / "build/step7-swarm/pathsmooth"
sys.path.insert(0, str(ROOT / "tests"))
import test_hcu_mp_path_consumer as path_consumer  # noqa: E402


def extract_function(source, name):
    import re
    matches = list(re.finditer(
        r"^[ \t]*(?:static\s+)?[\w\s*]+\b" + re.escape(name) + r"\s*\([^;{}]*\)\s*\{",
        source, re.MULTILINE))
    if len(matches) != 1:
        raise AssertionError(f"expected one {name}, found {len(matches)}")
    start = matches[0].start()
    opening = source.find("{", start)
    depth = 0
    for pos in range(opening, len(source)):
        if source[pos] == "{":
            depth += 1
        elif source[pos] == "}":
            depth -= 1
            if depth == 0:
                return source[start:pos + 1]
    raise AssertionError(f"unterminated {name}")


def centroid(image, location, surface_index):
    root = struct.unpack_from("<I", image)[0] - location.address
    collision = struct.unpack_from("<I", image, root + 0xB4)[0] - location.address
    surface_at = struct.unpack_from("<I", image, collision + 0x40)[0] - location.address
    edge_at = struct.unpack_from("<I", image, collision + 0x4C)[0] - location.address
    vertex_at = struct.unpack_from("<I", image, collision + 0x58)[0] - location.address
    first_edge = struct.unpack_from("<i", image, surface_at + surface_index * 12 + 4)[0]
    xs, ys, zs = [], [], []
    edge_index = first_edge
    for _ in range(8):
        v0, v1, next0, next1, s0, s1 = struct.unpack_from("<6i", image, edge_at + edge_index * 24)
        right = surface_index == s1
        vertex = v1 if right else v0
        x, y, z = struct.unpack_from("<3f", image, vertex_at + vertex * 16)
        xs.append(x)
        ys.append(y)
        zs.append(z)
        edge_index = next1 if right else next0
        if edge_index == first_edge:
            break
    return (sum(xs) / len(xs), sum(ys) / len(ys), sum(zs) / len(zs))


class MultiplayerPathSmoothTest(unittest.TestCase):
    def test_ce_build_path_smooths_raw_bloodgulch_route_without_discs(self):
        raw = path_consumer.raw_fixture("bloodgulch")
        self.assertEqual(
            raw["source_map_sha256"],
            path_consumer.MP_SOURCE_SHA256["bloodgulch"])
        path = ROOT / "build/retail-maps/decompressed/bloodgulch.map"
        sys.path.extend([str(ROOT / "tools"),
                         str(ROOT / "submodules/halo-ps2/tools")])
        from halo2ps2 import bsp, mapinfo, tagindex
        from ctag_schema_walk import read_xbox_tag_region
        region, _, _ = read_xbox_tag_region(path)
        locations = bsp.locate(
            tagindex.TagIndex.read(path), region,
            mapinfo.read_header(path).decompressed_size)
        image = path.read_bytes()[locations[0].file_offset:
                                  locations[0].file_offset + locations[0].size]
        start = centroid(image, locations[0], raw["route_start"])
        goal = centroid(image, locations[0], raw["route_goal"])
        path_source = (HCU / "source/ai/path.c").read_text()
        smooth_source = (HCU / "source/ai/path_smoothing.c").read_text()
        get_node = extract_function(path_source, "path_get_node")
        from_hash = extract_function(path_source, "path_node_from_hash_table")
        build = extract_function(path_source, "path_state_build_path")
        smooth = extract_function(smooth_source, "path_smooth")
        harness = r'''
#include <math.h>
#include <stdio.h>
#include <string.h>
#define long int
typedef int boolean;
typedef float real;
#define TRUE 1
#define FALSE 0
#define NONE -1
#define MIN(a,b) ((a)<(b)?(a):(b))
#define FLAG(bit) (1u << (bit))
#define match_assert(file, line, condition) ((void)0)
#define TAG_BLOCK_GET_ELEMENT(block, index, type) ((type *)0)
#define _game_connection_local 0
#define _path_test_pill_endpoint_near_wall_ok_bit 0
#define _z 2
#define assert(x) ((void)0)
enum {
    _path_build_result_none = 0,
    _path_build_result_no_destination,
    _path_build_result_cached_node_missing,
    _path_build_result_not_close_enough_to_destination,
    _path_build_result_obstacle_avoidance_failed,
    _path_build_result_success
};
typedef struct { real x,y,z; } real_point3d;
typedef struct { real x,y; } real_point2d;
struct path_collision_result {
    boolean collision; real_point3d point; int surface_index; int edge_index; real t;
};
struct path_step { int surface_index; real_point3d point; };
struct path_destination { real_point3d point; int surface_index; real target_radius; };
struct path_result {
    boolean valid; struct path_destination endpoint; boolean steps_finish_path;
    char step_count; char step_index; struct path_step steps[4];
};
struct path_input {
    real pathfinding_radius; boolean ignore_broken_surfaces;
    int ignore_source_object_index; int ignore_target_object_index;
    boolean start_valid; real_point3d start_point; int start_surface_index;
};
struct path_node {
    short child_node_index; short parent_node_index;
    int parent_node_surface_index; int surface_index;
    real_point3d entry_point; real unused[6];
    short unused_s[3]; short depth; short pad[2];
    real unused2[4];
};
struct structure_bsp;
struct collision_bsp;
struct path_debug_storage {
    int path_build_result; int failure; struct path_result result;
    short raw_step_count; struct path_step raw_steps[64];
    short smoothed_step_count; struct path_step smoothed_steps[4];
    short avoided_step_count; struct path_step avoided_steps[4];
};
struct ai_debug_globals { boolean path_disable_smoothing; boolean path_disable_obstacle_avoidance; };
struct path_state {
    struct path_input input;
    struct path_debug_storage *debug;
    boolean destination_valid;
    struct path_destination destination;
    struct structure_bsp const *structure;
    short closest_node_index;
    real closest_distance;
    real closest_cost_estimate;
    real_point3d closest_point;
    short node_count;
    struct path_node node_list[8];
    short heap_count;
    short pad_heap;
    short hash_table[4096];
};
static struct ai_debug_globals ai_debug;
int game_connection(void) { return _game_connection_local; }
void *csmemcpy(void *dst, const void *src, unsigned long n) { return memcpy(dst, src, n); }
real distance3d(const real_point3d *a, const real_point3d *b) {
    real dx=a->x-b->x, dy=a->y-b->y, dz=a->z-b->z;
    return sqrtf(dx*dx+dy*dy+dz*dz);
}
boolean structure_test_pill2d(const void *structure, boolean ignore,
    const real_point2d *start, int start_surface, const real_point2d *end,
    int end_surface, real radius, unsigned flags, void *result) {
    (void)structure; (void)ignore; (void)start; (void)start_surface;
    (void)end; (void)end_surface; (void)radius; (void)flags; (void)result;
    return FALSE;
}
static boolean find_turning_point(const void *a, const void *b, real c, int d,
    boolean e, boolean f, void *g) {
    (void)a;(void)b;(void)c;(void)d;(void)e;(void)f;(void)g; return FALSE;
}
static boolean choose_turning_point(const void *a, const void *b, const void *c,
    const void *d, const void *e, void *f) {
    (void)a;(void)b;(void)c;(void)d;(void)e;(void)f; return FALSE;
}
static void find_tangent_point(const void *a, const void *b, real c, boolean d, void *e) {
    (void)a;(void)b;(void)c;(void)d;(void)e;
}
static void find_avoidance_point(const void *a, const void *b, const void *c, real d, void *e) {
    (void)a;(void)b;(void)c;(void)d;(void)e;
}
static int structure_surface_index_from_point(const void *a, boolean b,
    const void *c, int d, const void *e) {
    (void)a;(void)b;(void)c;(void)e; return d;
}
static void collision_surface_project_point2d(const void *a, int b, int c,
    boolean d, const void *e, void *f) {
    (void)a;(void)b;(void)c;(void)d;(void)e;(void)f;
}
boolean path_avoid_obstacles(struct path_state *state, short count,
    struct path_step *in, short *out_count, struct path_step *out, boolean *fin) {
    (void)state; *out_count = count; memcpy(out, in, count * sizeof *out); (void)fin; return TRUE;
}
''' + get_node + "\n" + from_hash + "\n" + smooth + "\n" + build + r'''
int main(void) {
    struct path_state state;
    struct path_result path;
    int i;
    memset(&state, 0, sizeof state);
    memset(&path, 0, sizeof path);
    for (i = 0; i < 4096; ++i) state.hash_table[i] = NONE;
    ai_debug.path_disable_smoothing = FALSE;
    ai_debug.path_disable_obstacle_avoidance = TRUE;
    state.input.start_valid = TRUE;
    state.input.start_point.x = __SX__f;
    state.input.start_point.y = __SY__f;
    state.input.start_point.z = __SZ__f;
    state.input.start_surface_index = __START__;
    state.destination_valid = TRUE;
    state.destination.point.x = __GX__f;
    state.destination.point.y = __GY__f;
    state.destination.point.z = __GZ__f;
    state.destination.surface_index = __GOAL__;
    state.destination.target_radius = 0.f;
    state.node_count = 2;
    state.node_list[0].parent_node_index = NONE;
    state.node_list[0].surface_index = __START__;
    state.node_list[0].entry_point = state.input.start_point;
    state.node_list[0].depth = 0;
    state.node_list[1].parent_node_index = 0;
    state.node_list[1].surface_index = __GOAL__;
    state.node_list[1].entry_point = state.destination.point;
    state.node_list[1].depth = 1;
        {
            int start_slot = (__START__ & 0x1FF) << 3;
            int goal_slot = (__GOAL__ & 0x1FF) << 3;
            state.hash_table[start_slot] = 0;
            if (goal_slot == start_slot)
                goal_slot = (goal_slot + 1) & 0xFFF;
            state.hash_table[goal_slot] = 1;
        }
    if (!path_state_build_path(&state, &path) && !path.valid) {
        fprintf(stderr, "FAIL path invalid\n");
        return 1;
    }
    if (!path.valid || path.step_count < 1 || !path.steps_finish_path) {
        fprintf(stderr, "FAIL steps=%d finish=%d valid=%d\n",
            path.step_count, path.steps_finish_path, path.valid);
        return 1;
    }
    printf("mp-pathsmooth map=bloodgulch start=%d goal=%d depth=%d "
           "steps=%d finish=%d discs=0 status=passed\n",
           __START__, __GOAL__, __DEPTH__, path.step_count, path.steps_finish_path);
    return 0;
}
'''
        text = (harness
                .replace("__SX__", "%.9g" % start[0])
                .replace("__SY__", "%.9g" % start[1])
                .replace("__SZ__", "%.9g" % start[2])
                .replace("__GX__", "%.9g" % goal[0])
                .replace("__GY__", "%.9g" % goal[1])
                .replace("__GZ__", "%.9g" % goal[2])
                .replace("__START__", str(raw["route_start"]))
                .replace("__GOAL__", str(raw["route_goal"]))
                .replace("__DEPTH__", str(raw["route_depth"])))
        OUT.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="hcu-mp-pathsmooth-") as temp_name:
            temp = Path(temp_name)
            c_file = temp / "pathsmooth.c"
            exe = temp / "pathsmooth"
            c_file.write_text(text)
            built = subprocess.run(
                ["cc", "-std=gnu99", str(c_file), "-lm", "-o", str(exe)],
                capture_output=True, text=True)
            self.assertEqual(built.returncode, 0, built.stdout + built.stderr)
            run = subprocess.run([str(exe)], capture_output=True, text=True)
            self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
            self.assertIn("status=passed", run.stdout)
            payload = {
                "map": "bloodgulch",
                "source_map_sha256": raw["source_map_sha256"],
                "route_start": raw["route_start"],
                "route_goal": raw["route_goal"],
                "route_depth": raw["route_depth"],
                "start_point": start,
                "goal_point": goal,
                "stdout": run.stdout.strip(),
            }
            (OUT / "pathsmooth-bloodgulch.json").write_text(
                json.dumps(payload, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    unittest.main()
