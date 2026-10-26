"""Run CE path_state_build_path, including obstacle smoothing, on one raw route."""
from pathlib import Path
import hashlib
import importlib.util
import json
import os
import struct
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
HCU = ROOT / "submodules/halo-ce-universal"
OUT = ROOT / "build/step7-swarm/pathsmooth"
MAPS = (
    "beavercreek", "bloodgulch", "boardingaction", "carousel", "chillout",
    "damnation", "hangemhigh", "longest", "prisoner", "putput", "ratrace",
    "sidewinder", "wizard",
)
sys.path.insert(0, str(ROOT))
from tools.host_abi32 import flags as abi32_flags  # noqa: E402


def sha256(path):
    digest = hashlib.sha256()
    digest.update(path.read_bytes())
    return digest.hexdigest()


def load_consumer():
    spec = importlib.util.spec_from_file_location(
        "hcu_mp_path_consumer_ro", ROOT / "tests/test_hcu_mp_path_consumer.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def extract_last(text, signature):
    start = -1
    search = 0
    while True:
        found = text.find(signature, search)
        if found < 0:
            break
        opening = text.find("{", found)
        semi = text.find(";", found)
        if opening >= 0 and (semi < 0 or opening < semi):
            start = found
        search = found + len(signature)
    if start < 0:
        raise AssertionError(f"missing CE function {signature}")
    opening = text.find("{", start)
    depth = 0
    for index in range(opening, len(text)):
        if text[index] == "{":
            depth += 1
        elif text[index] == "}":
            depth -= 1
            if depth == 0:
                return text[start:index + 1]
    raise AssertionError(f"unterminated CE function {signature}")


def extract_brace(text, needle):
    start = text.rfind(needle)
    if start < 0:
        raise AssertionError(f"missing {needle}")
    line = text.rfind("\n", 0, start) + 1
    brace = text.find("{", start)
    depth = 0
    for index in range(brace, len(text)):
        if text[index] == "{":
            depth += 1
        elif text[index] == "}":
            depth -= 1
            if depth == 0:
                end = index + 1
                if end < len(text) and text[end] == ";":
                    end += 1
                return text[line:end]
    raise AssertionError(f"unterminated {needle}")


def raw_records(map_name):
    consumer = load_consumer()
    map_path = ROOT / "build/retail-maps/decompressed" / f"{map_name}.map"
    header = consumer.mapinfo.read_header(map_path)
    index = consumer.tagindex.TagIndex.read(map_path)
    region, _tag_base, _ = consumer.read_xbox_tag_region(map_path)
    locations = consumer.bsp.locate(index, region, header.decompressed_size)
    if len(locations) != 1:
        raise AssertionError(f"{map_name}: expected one BSP")
    location = locations[0]
    image = map_path.read_bytes()[location.file_offset:location.file_offset + location.size]
    root = struct.unpack_from("<I", image, 0)[0] - location.address
    count, address = struct.unpack_from("<iI", image, root + 0xB0)
    collision_offset = address - location.address
    if count != 1:
        raise AssertionError(f"{map_name}: collision count {count}")

    def element(at, stride):
        element_count, element_address = struct.unpack_from("<iI", image, collision_offset + at)
        element_offset = element_address - location.address
        if element_count < 0 or (element_count and (
                element_offset < 0 or element_offset + element_count * stride > len(image))):
            raise AssertionError(f"{map_name}: bad collision block {at:#x}")
        return element_count, image[element_offset:element_offset + element_count * stride]

    surface_count, surfaces = element(0x3C, 12)
    edge_count, edges = element(0x48, 24)
    vertex_count, vertices = element(0x54, 16)
    plane_count, planes = element(0x0C, 16)
    path_count, address = struct.unpack_from("<iI", image, root + 0x1E4)
    path_offset = address - location.address
    if path_count < 0 or path_offset < 0 or path_offset + path_count > len(image):
        raise AssertionError(f"{map_name}: bad pathfinding surfaces")
    flags = image[path_offset:path_offset + path_count]
    return {
        "surfaces": surfaces, "edges": edges, "vertices": vertices,
        "planes": planes, "flags": flags,
        "surface_count": surface_count, "edge_count": edge_count,
        "vertex_count": vertex_count, "plane_count": plane_count,
        "path_count": path_count,
    }


def f32(value):
    return struct.unpack("<f", struct.pack("<f", float(value)))[0]


def surface_ring(records, surface_index):
    surfaces = records["surfaces"]
    edges = records["edges"]
    vertices = records["vertices"]
    _plane, first_edge = struct.unpack_from("<ii", surfaces, surface_index * 12)
    edge_index = first_edge
    ring = []
    for _step in range(8):
        if not 0 <= edge_index < records["edge_count"]:
            break
        v0, v1, e0, e1, s0, s1 = struct.unpack_from("<6i", edges, edge_index * 24)
        reverse = s1 == surface_index
        vertex_index = (v0, v1)[1 if reverse else 0]
        if not 0 <= vertex_index < records["vertex_count"]:
            break
        point = struct.unpack_from("<3f", vertices, vertex_index * 16)
        ring.append((edge_index, point, (v0, v1), (e0, e1), reverse))
        edge_index = (e0, e1)[1 if reverse else 0]
        if edge_index == first_edge:
            break
    return ring


def point_on_raw_surface(records, surface_index, x, y, z):
    plane = struct.unpack_from("<4f", records["planes"], (struct.unpack_from(
        "<i", records["surfaces"], surface_index * 12)[0] & 0x7FFFFFFF) * 16)
    distance = abs(f32(f32(f32(plane[0] * x) + f32(plane[1] * y)) + f32(plane[2] * z)) - plane[3])
    ring = surface_ring(records, surface_index)
    # CE collision_surface_test_point2d(_z, TRUE) rejects cross>0 and therefore
    # only accepts clockwise XY rings. Blood Gulch surface 108 is CCW in XY
    # (positive shoelace) while still planar, so that hardcoded CW test rejects
    # the 3D centroid. Pathfinding copies the destination after a clear pill and
    # does not require that 2D test. Use the ring's own winding so a barycenter
    # on a CCW floor counts as on-surface.
    shoelace = 0.0
    for index, item in enumerate(ring):
        nxt = ring[(index + 1) % len(ring)] if ring else None
        if nxt is None:
            break
        ax, ay = item[1][0], item[1][1]
        bx, by = nxt[1][0], nxt[1][1]
        shoelace = f32(shoelace + f32(f32(ax * by) - f32(bx * ay)))
    edges = records["edges"]
    vertices = records["vertices"]
    first_edge = struct.unpack_from("<i", records["surfaces"], surface_index * 12 + 4)[0]
    edge_index = first_edge
    inside = bool(ring)
    nearest = None
    for _step in range(8):
        if not 0 <= edge_index < records["edge_count"]:
            inside = False
            break
        v0, v1, e0, e1, s0, s1 = struct.unpack_from("<6i", edges, edge_index * 24)
        reverse = s1 == surface_index
        a = struct.unpack_from("<3f", vertices, (v1 if reverse else v0) * 16)
        b = struct.unpack_from("<3f", vertices, (v0 if reverse else v1) * 16)
        ax, ay = f32(x - a[0]), f32(y - a[1])
        bx, by = f32(x - b[0]), f32(y - b[1])
        cross = f32(f32(ax * by) - f32(ay * bx))
        if f32(cross * shoelace) < 0.0:
            inside = False
        edge_dx, edge_dy = f32(b[0] - a[0]), f32(b[1] - a[1])
        length_squared = f32(f32(edge_dx * edge_dx) + f32(edge_dy * edge_dy))
        if length_squared > 0.0:
            t = f32(f32(f32((x - a[0]) * edge_dx) + f32((y - a[1]) * edge_dy)) / length_squared)
            if t < 0.0:
                t = 0.0
            elif t > 1.0:
                t = 1.0
            qx, qy = f32(a[0] + f32(edge_dx * t)), f32(a[1] + f32(edge_dy * t))
            dx, dy = f32(x - qx), f32(y - qy)
            gap = f32(f32(dx * dx) + f32(dy * dy)) ** 0.5
            nearest = gap if nearest is None else min(nearest, gap)
        edge_index = (e0, e1)[1 if reverse else 0]
        if edge_index == first_edge:
            break
    on_plane = distance < 1e-2
    on_polygon = inside or (nearest is not None and nearest < 0.02)
    return on_plane and on_polygon, distance, nearest, inside, shoelace


def compile_flags(semantics):
    port = json.loads((HCU / "port/linux/port.json").read_text())
    includes = ["-I" + str(HCU / rel) for rel in port["game"]["include_dirs"]]
    includes += ["-I" + str(HCU / rel) for rel in (
        "port/linux/include", "port/include/xdk", "port/linux/game", "port/include")]
    return [
        "clang", "--target=i686-linux-gnu", "-std=gnu89", "-fms-extensions",
        "-fshort-wchar", "-malign-double", "-fcommon", "-fno-pic",
        "-fno-strict-aliasing", "-fwrapv", "-ffp-contract=off",
        "-D__STRICT_ANSI__", "-DDEBUG", "-Dxbox", "-w",
        "-include", str(HCU / "port/linux/include/halo_linux_prefix.h"),
        "-include", str(semantics),
    ] + abi32_flags() + includes


def write_extract(path):
    source = HCU / "source"
    parts = []

    def add(title, body):
        parts.append(f"\n/* ---- {title} ---- */\n")
        parts.append(body)
        if not body.endswith("\n"):
            parts.append("\n")

    includes = """
#define BUILDING_CSERIES 1
#include "cseries.h"
#include "errors.h"
#include "tag_groups.h"
#include "data.h"
#include "memory_pool.h"
#include "game_state.h"
#include "objects.h"
#include "object_types.h"
#include "units.h"
#include "unit_definitions.h"
#include "bipeds.h"
#include "vehicles.h"
#include "vehicle_definitions.h"
#include "actors.h"
#include "actor_definitions.h"
#include "actor_types.h"
#include "ai_debug.h"
#include "actions.h"
#include "encounters.h"
#include "breakable_surfaces.h"
#include "collision_bsp.h"
#include "collision_bsp_definitions.h"
#include "scenario.h"
#include "structure_bsp_definitions.h"
#include "cluster_partitions.h"
#include "real_math.h"
#include "game.h"
#include "custom_edition_cache.h"
#include <stdio.h>
#include <stdlib.h>
struct bitmap_data;
enum { TAG_EMPTY_DATA_SIZE = 0x10000 };
"""
    add("includes", includes)
    add("actor stubs", """
static void actor_input_update(long actor_index)
{
	(void)actor_index;
}

static void actor_verify_unit_activation(
	long actor_index,
	long unit_index,
	char const *name)
{
	(void)actor_index;
	(void)unit_index;
	(void)name;
}
""")
    cseries = (source / "cseries/cseries.c").read_text()
    add("cseries limits", cseries[cseries.index("enum\n{\n\tMAXIMUM_MEMCPY"):cseries.index("/* ---------- structures */")])
    add("temporary", "char temporary[256];\n")
    for signature in (
            "void *csmemset(", "void *csmemcpy(", "long csmemcmp(",
            "char *csstrncpy(", "char *csprintf("):
        add(signature, extract_last(cseries, signature))
    data = (source / "memory/data.c").read_text()
    add("platform_log", "void platform_log(const char *format, ...);\n")
    for signature in (
            "static boolean data_usable(", "static void datum_initialize(",
            "long data_allocation_size(", "void data_initialize(",
            "void data_verify(", "void *datum_get(", "long datum_new_at_index(",
            "long datum_new(", "void data_make_valid(", "void data_delete_all("):
        add(signature, extract_last(data, signature))
    tags = (source / "tag_files/tag_groups.c").read_text()
    add("empty tag", "static unsigned long tag_empty_data_bytes[0x10000 / sizeof(unsigned long)];\n")
    for signature in (
            "static void tag_index_error(", "void *tag_empty_data(",
            "void *tag_block_get_element_with_size("):
        add(signature, extract_last(tags, signature))
    breakable = (source / "physics/breakable_surfaces.c").read_text()
    add("breakable globals", breakable[breakable.index("struct breakable_surface_globals"):breakable.index("/* ---------- prototypes */")])
    add("breakable storage", """
static struct breakable_surface_globals *globals;
static struct breakable_surface_datum breakable_surface_scratch;
static byte breakable_surface_flags_scratch[32];
static boolean warned_about_breakable_surfaces;
static boolean breakable_surface_indices_valid(short breakable_surface_index);
""")
    for signature in (
            "void breakable_surfaces_initialize(",
            "void breakable_surfaces_initialize_for_new_map(",
            "byte *breakable_surface_flags_get(",
            "static boolean breakable_surface_indices_valid("):
        add(signature, extract_last(breakable, signature))
    collision = (source / "physics/collision_bsp.c").read_text()
    add("collision warnings", """
static boolean warned_about_collision_surface_edges;
static boolean warned_about_collision_surface_index;
""")
    for signature in (
            "boolean collision_surface_edge_ring_continues(",
            "boolean collision_bsp_valid_surface_index(",
            "real_point3d *collision_surface_project_point2d(",
            "boolean collision_surface_test_point2d(",
            "boolean collision_surface_find_closest_point2d(",
            "boolean collision_surface_test_line2d("):
        add(signature, extract_last(collision, signature))
    objects = (source / "objects/objects.c").read_text()
    add("object globals", objects[objects.index("struct object_globals"):objects.index("/* port: when a collection")])
    add("object storage", """
static long *object_name_list = NULL;
static struct memory_pool *object_memory_pool = NULL;
static struct object_globals *object_globals = NULL;
long global_object_marker;
struct cluster_partition noncollideable_object_cluster_partition;
struct cluster_partition collideable_object_cluster_partition;
struct data_array *object_header_data;
""")
    # port helper called by the extracted pool paths; verbatim from CE objects.c.
    # Its HALO_PS2 body is compiled out in this host build, as in production.
    add("object pool counters note", extract_last(objects, "static void object_pool_counters_note("))
    for signature in (
            "static void object_name_list_allocate(", "static void object_name_list_clear(",
            "void objects_initialize(", "void objects_initialize_for_new_map(",
            "void object_marker_begin(", "void object_marker_end(",
            "boolean object_mark_function(", "short objects_in_clusters_by_indices(",
            "short objects_in_sphere(", "void object_activate(", "void object_deactivate(",
            "void object_set_automatic_deactivation("):
        add(signature, extract_last(objects, signature))
    units = (source / "units/units.c").read_text()
    for signature in (
            "static void unit_update_driver_and_gunner(",
            "void unit_set_actively_controlled("):
        add(signature, extract_last(units, signature))
    actors = (source / "ai/actors.c").read_text()
    enum_start = actors.index("enum\n{\n\t_actor_mode_braindead")
    enum_end = actors.index("/* ---------- macros */", enum_start)
    add("actor local enums", actors[enum_start:enum_end])
    moving = (source / "ai/actor_moving.c").read_text()
    firing = (source / "ai/actor_firing_position.c").read_text()
    add("actor storage", """
struct data_array *swarm_data;
struct data_array *swarm_component_data;
struct data_array *actor_data;
struct data_array *encounter_data;
long global_updating_actor_index = NONE;
struct encounter_actor_iterator
{
	long encounter_index;
	long index;
	long next_index;
};
struct vehicle_definition
{
	byte __unknown0[0x2F8];
	real maximum_forward_speed;
	real maximum_reverse_speed;
	real speed_acceleration;
	real speed_deceleration;
	byte __unknown308[0x78];
	real ai_sideslip_distance;
	byte __unknown384[4];
	real ai_avoidance_distance;
	real ai_pathfinding_radius;
	byte __unknown390[8];
	real ai_oversteer_angle_lower_bound;
	real ai_oversteer_angle_upper_bound;
	real ai_steering_max_angle;
	real ai_steering_max_throttle;
};
""")
    # actors_initialize() resets these file-static telemetry counters; copy the
    # declarations verbatim from CE actors.c (each must occur exactly once).
    for counter in ("s_actor_pool_high_water", "s_actor_pool_failed_allocations",
                    "s_actor_pool_resets"):
        declaration = f"static unsigned long {counter};"
        if actors.count(declaration) != 1:
            raise AssertionError(f"CE actors.c telemetry declaration changed: {counter}")
        add("actor telemetry " + counter, declaration + "\n")
    for signature in (
            "void actors_initialize(", "void actors_initialize_for_new_map(",
            "long actor_new(", "long actor_create_for_unit(", "void actor_attach_unit(",
            "void actor_verify_activation(", "void actor_find_pathfinding_location("):
        add(signature, extract_last(actors, signature))
    add("actor_path_input_new", extract_last(moving, "void actor_path_input_new("))
    add("clear firing", extract_last(firing, "void actor_clear_discarded_firing_positions("))
    scenario = (source / "scenario/scenario.c").read_text()
    add("bsp globals", """
short global_structure_bsp_index = NONE;
struct structure_bsp *global_structure_bsp;
struct collision_bsp *global_collision_bsp;
struct bsp3d *global_bsp3d;
""")
    for signature in (
            "struct structure_bsp *global_structure_bsp_get(",
            "struct collision_bsp *global_collision_bsp_get(",
            "struct bsp3d *global_bsp3d_get(",
            "short global_structure_bsp_index_get("):
        add(signature, extract_last(scenario, signature))
    main = (source / "main/main.c").read_text()
    struct_start = main.index("struct _main_globals\n{\n\tunsigned long frame_start_milliseconds;")
    struct_end = main.index("typedef char main_hud_globals", struct_start)
    add("main globals", main[struct_start:struct_end] + "\nstatic struct _main_globals main_globals = { 0 };\n")
    for signature in ("void game_connection_set(", "short game_connection("):
        add(signature, extract_last(main, signature))
    custom = (HCU / "port/ps2/src/ps2_custom_edition.c").read_text()
    add("custom edition", extract_last(custom, "boolean custom_edition_cache_tags_loaded("))
    import re
    type_bodies = []
    names = []
    for type_path in sorted((source / "ai").glob("actor_type_*.c")):
        if type_path.name == "actor_types.c":
            continue
        body = extract_brace(type_path.read_text(), "struct actor_type_definition " + type_path.stem)
        type_bodies.append((type_path.name, body))
        names.extend(re.findall(r"\b([A-Za-z_][A-Za-z0-9_]*)\s*(?:,|\n|\})", body))
    unique = []
    for name in names:
        if name in ("NULL", "TRUE", "FALSE") or name.startswith("actor_type"):
            continue
        if name not in unique and name.endswith((
                "decide_action", "swarm_control", "swarm_aim_jump")):
            unique.append(name)
    stubs = ["static void pathsmooth_blocked_actor(const char *name) {\n"
             "\tfprintf(stderr, \"BLOCKED unexpected CE call %s\\n\", name);\n"
             "\texit(3);\n}\n"]
    for name in unique:
        if name.endswith("swarm_aim_jump"):
            stubs.append(
                f"void {name}(long actor_index, long unit_index, real jump_magnitude, "
                f"real_vector3d *jump_velocity)\n{{\n"
                f"\t(void)actor_index; (void)unit_index; (void)jump_magnitude; (void)jump_velocity;\n"
                f"\tpathsmooth_blocked_actor(\"{name}\");\n}}\n")
        else:
            stubs.append(
                f"void {name}(long actor_index)\n{{\n\t(void)actor_index;\n"
                f"\tpathsmooth_blocked_actor(\"{name}\");\n}}\n")
    add("actor type procs", "".join(stubs))
    for name, body in type_bodies:
        add(name, body)
    path.write_text("".join(parts))
    return unique


def write_stubs(path, names):
    lines = [
        "#include <stdio.h>",
        "#include <stdlib.h>",
        "static void pathsmooth_unexpected(const char *name) {",
        '\tfprintf(stderr, "BLOCKED unexpected CE call %s\\n", name);',
        "\texit(3);",
        "}",
    ]
    for name in names:
        lines.append(f"void {name}(void) {{ pathsmooth_unexpected(\"{name}\"); }}")
    path.write_text("\n".join(lines) + "\n")


class PathSmoothingTest(unittest.TestCase):
    def test_identity_and_bloodgulch_smoothing(self):
        OUT.mkdir(parents=True, exist_ok=True)
        checks = []
        issues = []

        def check(condition, message):
            checks.append(message)
            if not condition:
                issues.append(message)

        smoothing = (HCU / "source/ai/path_smoothing.c").read_text().splitlines()
        walkable = "\n".join(smoothing[107:158])
        turning = "\n".join(smoothing[375:419])
        check("actor" not in walkable and "unit_index" not in walkable,
              "path_smoothing.c:108-158 reads no actor/unit field")
        check("actor" not in turning and "unit_index" not in turning,
              "path_smoothing.c:376-419 reads no actor/unit field")
        build = extract_last((HCU / "source/ai/path.c").read_text(), "boolean path_state_build_path(")
        check("path_smooth(" in build and "path_avoid_obstacles(" in build,
              "path_state_build_path calls path_smooth and path_avoid_obstacles")
        discs = extract_last((HCU / "source/ai/path_obstacles.c").read_text(),
                             "void obstacles_get_discs_in_sphere(")
        check("ignore_source_object_index" in discs and "object.location" in discs,
              "obstacles_get_discs_in_sphere reads ignore_source and object.location")
        moving = extract_last((HCU / "source/ai/actor_moving.c").read_text(), "void actor_path_input_new(")
        check("meta.unit_index" in moving and "pathfinding_radius" in moving
              and "ignorant_of_broken_surfaces" in moving and "pathfinding_surface_index" in moving,
              "actor_path_input_new reads unit, radius, broken-surface flag, and pathfinding location")

        consumer = load_consumer()
        fixture = consumer.raw_fixture("bloodgulch")
        check(fixture["source_map_sha256"] == consumer.MP_SOURCE_SHA256["bloodgulch"],
              "bloodgulch source sha")
        records = raw_records("bloodgulch")
        check(records["surface_count"] == fixture["surface_count"], "surface count matches route fixture")
        check(records["path_count"] == fixture["path_count"], "path flag count matches route fixture")
        route_start = fixture["route_start"]
        route_goal = fixture["route_goal"]
        check(records["flags"][route_start] & (1 << 6) != 0, "route start walkable in raw flags")
        check(records["flags"][route_goal] & (1 << 6) != 0, "route goal walkable in raw flags")
        for surface_index in range(records["surface_count"]):
            designator = struct.unpack_from("<i", records["surfaces"], surface_index * 12)[0]
            if (designator & 0x7FFFFFFF) >= records["plane_count"]:
                issues.append(f"surface {surface_index} plane out of range")
                break
        else:
            checks.append("every raw plane designator indexes the plane block")

        groups = {}
        map_path = ROOT / "build/retail-maps/decompressed/bloodgulch.map"
        index = consumer.tagindex.TagIndex.read(map_path)
        data = map_path.read_bytes()
        actv_none = 0
        actv_count = 0
        for entry in index.entries:
            groups[entry.group] = groups.get(entry.group, 0) + 1
            if entry.group == "actv":
                actv_count += 1
                reference = struct.unpack_from("<i", data, index.addr_to_off(entry.data_address) + 16)[0]
                if reference == -1:
                    actv_none += 1
        check(groups.get("actr", 0) == 0 and actv_count == 3 and actv_none == 3,
              "raw bloodgulch has 0 actr and 3 actv whose actor_reference.index is NONE")

        payload_path = OUT / "bloodgulch-route.bin"
        payload = struct.pack(
            "<7I", records["surface_count"], records["edge_count"], records["vertex_count"],
            records["plane_count"], records["path_count"], route_start, route_goal)
        payload += records["surfaces"] + records["edges"] + records["vertices"]
        payload += records["planes"] + records["flags"]
        payload_path.write_bytes(payload)
        payload_sha = hashlib.sha256(payload).hexdigest()

        extract_path = OUT / "pathsmooth_ce_extract.c"
        write_extract(extract_path)
        stub_path = OUT / "pathsmooth_abort_stubs.c"
        write_stubs(stub_path, [])
        semantics = OUT / "halo_msvc_semantics.h"
        generated = subprocess.run([
            sys.executable, str(HCU / "tools/linux_msvc_semantics.py"),
            "--output", str(semantics), "--all-inlines",
            "--tags", str(HCU / "source"),
            "--inlines", str(HCU / "source"),
            "--inlines", str(HCU / "port/include/xdk"),
        ], cwd=ROOT, capture_output=True, text=True)
        if generated.returncode != 0:
            self._finish(checks, issues + ["semantics header failed: " + generated.stderr[-500:]],
                         [generated.stderr], None, None)
            return
        compile = compile_flags(semantics)
        plain = [
            "clang", "--target=i686-linux-gnu", "-ffp-contract=off", "-fno-pic",
            "-fno-builtin", "-w",
        ] + abi32_flags()
        musl_dir = HCU / "port/third_party/musl-math"
        musl_compile = plain + [
            "-std=gnu11",
            "-I" + str(musl_dir / "include"),
            "-include", str(musl_dir / "include/libm.h"),
        ]
        objects = []
        sources = [
            HCU / "source/ai/path.c",
            HCU / "source/ai/path_smoothing.c",
            HCU / "source/ai/path_structure_bsp.c",
            HCU / "source/ai/path_obstacle_avoidance.c",
            HCU / "source/ai/path_obstacles.c",
            HCU / "source/ai/actor_types.c",
            HCU / "source/math/real_math.c",
            HCU / "source/structures/structures.c",
            extract_path,
            ROOT / "tests/pathsmooth_hcu_mp_host.c",
            ROOT / "tests/pathsmooth_crt.c",
        ]
        log_lines = []

        def compile_one(command, source_path):
            object_path = OUT / (source_path.stem + ".o")
            full = command + ["-c", str(source_path), "-o", str(object_path)]
            result = subprocess.run(full, cwd=ROOT, capture_output=True, text=True)
            log_lines.append("$ " + " ".join(full))
            log_lines.append(result.stdout)
            log_lines.append(result.stderr)
            if result.returncode != 0:
                self._finish(checks, issues + [f"compile failed {source_path.name}"], log_lines, None, None)
                return None
            return object_path

        for source_path in sources:
            flags = plain + ["-std=gnu89"] if source_path.name == "pathsmooth_crt.c" else compile
            object_path = compile_one(flags, source_path)
            if object_path is None:
                return
            objects.append(object_path)
        for source_path in sorted((musl_dir / "src").glob("*.c")):
            object_path = compile_one(musl_compile, source_path)
            if object_path is None:
                return
            objects.append(object_path)
        stub_object = compile_one(plain + ["-std=gnu89"], stub_path)
        if stub_object is None:
            return
        objects.append(stub_object)

        executable = OUT / "pathsmooth_hcu_mp_host"
        link = compile + ["-no-pie", "-Wl,--wrap,objects_in_sphere", "-lm", "-o", str(executable)] + [
            str(item) for item in objects]
        result = subprocess.run(link, cwd=ROOT, capture_output=True, text=True)
        log_lines.append("$ " + " ".join(link))
        log_lines.append(result.stderr)
        if result.returncode != 0:
            missing = []
            for line in result.stderr.splitlines():
                if "undefined reference to `" in line:
                    name = line.split("undefined reference to `", 1)[1].split("'", 1)[0]
                    if name not in missing:
                        missing.append(name)
            if missing:
                write_stubs(stub_path, missing)
                stub_object = OUT / "pathsmooth_abort_stubs.o"
                rebuild = subprocess.run(
                    plain + ["-std=gnu89", "-c", str(stub_path), "-o", str(stub_object)],
                    cwd=ROOT, capture_output=True, text=True)
                log_lines.append(rebuild.stderr)
                result = subprocess.run(link, cwd=ROOT, capture_output=True, text=True)
                log_lines.append(result.stderr)
            if result.returncode != 0:
                self._finish(checks, issues + ["link failed: " + result.stderr[-2000:]], log_lines, None, None)
                return

        hp2 = Path("/tmp/hcu-m2-capacity-repro.P5qdmI/packages/bloodgulch.hp2")
        hp2_before = sha256(hp2) if hp2.is_file() else None
        run = subprocess.run(
            [str(executable), str(payload_path)], cwd=ROOT, capture_output=True, text=True, timeout=180)
        if run.returncode in (-31, 159) or (run.returncode < 0 and -run.returncode == 31):
            log_lines.append("SIGSYS; rerunning outside the sandbox is required")
            self._finish(checks, issues + ["SIGSYS"], log_lines, run.stdout, run.stderr, sigsys=True)
            return
        log_lines.append(run.stdout)
        log_lines.append(run.stderr)
        hp2_after = sha256(hp2) if hp2.is_file() else None
        check(hp2_before == hp2_after, "bloodgulch.hp2 bytes unchanged")
        if "BLOCKED" in run.stderr:
            issues.append(run.stderr.strip().splitlines()[-1])
        elif run.returncode != 0:
            issues.append(f"harness exit {run.returncode}")
        parsed = self._parse(run.stdout)
        if run.returncode == 0:
            self._geometry(records, fixture, parsed, check, issues)
        self._finish(checks, issues, log_lines, run.stdout, run.stderr,
                     payload_sha=payload_sha, fixture=fixture, parsed=parsed,
                     hp2_before=hp2_before)

    def _geometry(self, records, fixture, parsed, check, issues):
        chain = parsed.get("chain", [[], []])
        points = parsed.get("points", [[], []])
        check(chain[0] == chain[1] and chain[0], "A* chains match across two runs")
        check(points[0] == points[1] and points[0], "built points match across two runs")
        if not chain[0] or not points[0]:
            return
        adjacency = fixture["walkable_adjacency"]
        check(chain[0][0] == fixture["route_start"] and chain[0][-1] == fixture["route_goal"],
              "A* chain starts and ends on the raw route")
        linked = True
        for left, right in zip(chain[0], chain[0][1:]):
            if right not in adjacency[left]:
                linked = False
        check(linked, "A* chain steps are raw walkable-adjacent")
        chain_set = set(chain[0])
        for surface, x, y, z in points[0]:
            flags = records["flags"][surface]
            collision_flags = records["surfaces"][surface * 12 + 8]
            on_surface, distance, nearest, inside, shoelace = point_on_raw_surface(
                records, surface, x, y, z)
            ring = surface_ring(records, surface)
            bary = ""
            if len(ring) == 3:
                ax, ay = ring[0][1][0], ring[0][1][1]
                bx, by = ring[1][1][0], ring[1][1][1]
                cx, cy = ring[2][1][0], ring[2][1][1]
                den = (by - cy) * (ax - cx) + (cx - bx) * (ay - cy)
                wv = ((by - cy) * (x - cx) + (cx - bx) * (y - cy)) / den
                vv = ((cy - ay) * (x - cx) + (ax - cx) * (y - cy)) / den
                area = ax * (by - cy) + bx * (cy - ay) + cx * (ay - by)
                bary = " bary=(%.6f,%.6f,%.6f) shoelace=%.6f" % (1.0 - wv - vv, wv, vv, area)
            check(surface in chain_set, f"step surface {surface} is on the A* chain")
            check(flags & (1 << 6) != 0, f"step surface {surface} raw walkable bit")
            if flags & (1 << 7):
                check(collision_flags & (1 << 3) != 0,
                      f"step surface {surface} raw collision breakable bit")
            check(on_surface,
                  "step surface %s on-plane/winding-adaptive polygon "
                  "(CE _z,TRUE CW test is not the 3D-on-surface oracle): "
                  "d=%s gap=%s inside=%s shoelace=%s%s"
                  % (surface, distance, nearest, inside, shoelace, bary))

    def _parse(self, stdout):
        parsed = {"chain": [[], []], "points": [[], []], "lines": stdout.splitlines()}
        for line in parsed["lines"]:
            if line.startswith("CHAIN "):
                run = int(line.split("run=", 1)[1].split()[0])
                parsed["chain"][run] = [int(item) for item in line.split()[3:]]
            elif line.startswith("POINT RESULT "):
                parts = line.split()
                values = {item.split("=", 1)[0]: item.split("=", 1)[1] for item in parts if "=" in item}
                run = int(values["run"])
                parsed["points"][run].append((
                    int(values["surface"]), float(values["x"]), float(values["y"]), float(values["z"])))
            elif line.startswith("IDENTITY "):
                parsed["identity"] = line
            elif line.startswith("BUILD "):
                parsed.setdefault("build", []).append(line)
            elif line.startswith("SPHERE ") or line.startswith("BSP_") or line.startswith("BREAKABLE") \
                    or line.startswith("COLLISION") or line.startswith("DETERMINISTIC") \
                    or line.startswith("ROUTE ") or line.startswith("STATUS "):
                parsed.setdefault("status", []).append(line)
        return parsed

    def _finish(self, checks, issues, log_lines, stdout, stderr, payload_sha=None,
                fixture=None, parsed=None, hp2_before=None, sigsys=False):
        log_path = OUT / "pathsmooth.log"
        log_path.write_text("".join(item or "" for item in log_lines))
        executable = OUT / "pathsmooth_hcu_mp_host"
        sources = [
            ROOT / "tests/test_hcu_mp_path_smoothing.py",
            ROOT / "tests/pathsmooth_hcu_mp_host.c",
            ROOT / "tests/pathsmooth_crt.c",
        ]
        if sigsys:
            verdict = "BLOCKED"
        elif any(item.startswith("BLOCKED") or "compile failed" in item or "link failed" in item
                 for item in issues):
            verdict = "BLOCKED"
        elif issues:
            verdict = "ISSUES"
        else:
            verdict = "PASS"
        rows = []
        for name in MAPS:
            if name == "bloodgulch" and fixture is not None:
                rows.append(
                    f"| bloodgulch | route {fixture['route_start']}->{fixture['route_goal']} "
                    f"depth {fixture['route_depth']} walkable {fixture['walkable']} | {verdict} |")
            elif name == "bloodgulch":
                rows.append("| bloodgulch | route not executed | " + verdict + " |")
            else:
                rows.append(f"| {name} | not this slice (one route) | n/a |")
        identity = (parsed or {}).get("identity", "")
        status = "\n".join((parsed or {}).get("status", []))
        builds = "\n".join((parsed or {}).get("build", []))
        report = [
            f"# pathsmooth {verdict}",
            "",
            "Blood Gulch only. `path_smoothing.c` lines 108-158 and 376-419 read pathfinding flags, collision-surface flags, and breakable-surface runtime bits. Actor identity enters through `actor_path_input_new`: `meta.unit_index`, `moving.pathfinding_radius`, `emotions.ignorant_of_broken_surfaces`, and `input.pathfinding_point/surface_index`.",
            "",
            f"Raw tag census: 0 `actr`, 3 `actv`, each `actor_reference.index` NONE. The actor definition is the zeroed step8 record (type 0 elite, radius 0, glass chance 0). CE clamps that radius with `MAX(0.2f, radius)` in `path.c`.",
            "",
            identity,
            "",
            builds,
            "",
            status,
            "",
            "## Maps",
            "",
            "| map | result | verdict |",
            "| --- | --- | --- |",
            *rows,
            "",
            f"Checks: {len(checks)}. Issues: {len(issues)}.",
        ]
        if issues:
            report.append("")
            report.extend(f"- {item}" for item in issues)
        report.extend([
            "",
            "## Hashes",
            "",
        ])
        for source in sources:
            report.append(f"- `{source.name}` `{sha256(source)}`")
        if executable.is_file():
            report.append(f"- `pathsmooth_hcu_mp_host` `{sha256(executable)}`")
        report.append(f"- `pathsmooth.log` `{sha256(log_path)}`")
        if payload_sha:
            report.append(f"- route payload `{payload_sha}`")
        if hp2_before:
            report.append(f"- bloodgulch.hp2 `{hp2_before}`")
        report.extend([
            "",
            "Limits: no PCSX2/GS/VU/SPU2 claim. `actor_input_update` and `actor_verify_unit_activation` are the step8 empty stubs. `encounterless_attach_actor` sets `meta.encounterless` without `ai_globals`. Actor definition is the synthetic step8 record, not a retail tag. `debug_malloc`/`debug_free` are libc wrappers, not `debug_memory.c`. Trigonometry is the port musl math. Other maps were not run.",
            "",
            "Reproduce: `python3 -m pytest -q tests/test_hcu_mp_path_smoothing.py`",
            "",
        ])
        (OUT / "report.md").write_text("\n".join(report))
        if issues or sigsys:
            self.fail(verdict + "\n" + "\n".join(issues))


if __name__ == "__main__":
    unittest.main()
