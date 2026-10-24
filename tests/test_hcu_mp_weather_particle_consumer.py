"""Run CE weather-particle selection against raw Xbox multiplayer BSP data.

The test source-extracts CE's real scenario/weather dispatch functions. It does
not synthesize weather palette values or infer runtime selection from tags
alone. Since retail MP palettes may not reference rain tags, the no-particle
path is itself an explicit expected result.
"""
from pathlib import Path
import hashlib
import os
import re
import struct
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
HCU = ROOT / "submodules/halo-ce-universal"
MAP_ROOT = ROOT / "build/retail-maps/decompressed"
MP_MAPS = (
    "beavercreek", "bloodgulch", "boardingaction", "carousel", "chillout",
    "damnation", "hangemhigh", "longest", "prisoner", "putput", "ratrace",
    "sidewinder", "wizard",
)
MAP_SHA256 = {
    "beavercreek": "eaf90b2abc4fd295469eb2d640063618b0d14396f28e7d7f1758e834c061c50a",
    "bloodgulch": "9eb0374c" "be4571af" "640ae0d2" "e0ebf611" "9543cdbb" "ece44d49" "543b4748" "c4cf0dc1",
    "boardingaction": "34ddf961973b6aaf05f40f26bd9ad536ca97f8af503995611535ccf6ce911522",
    "carousel": "3e4be29a7952af0b3f19a7540e454fd0deece6d6078c256cde70a734beba55e1",
    "chillout": "52bc3e23b9142cf479770d1d601fe08b13d78fe3eb05eca72d313b7ebbd21ffb",
    "damnation": "87bd92c1821ff20bed03c559d7be5ac43baeb44aa68342ffdbb5a8cd978f711c",
    "hangemhigh": "e3e4b25ed36178926f0df11f3cd82b07e2071f6aa0efaa77f0cfde8f8480981f",
    "longest": "e045b0843f4a167a516f050161a651610fafc94ccc8c5f2c5d5725d108d5d1b9",
    "prisoner": "85ff2fdc117b7640bda85a490b30c662f2626bd6d0685e41832935422891c307",
    "putput": "efbe723188f34053d318105f20c7046f263171fbb937fbad45e3d00f8437f243",
    "ratrace": "577886f949f2648f04cf99e354fb04ca08d7b9199636c2f9fe1a161ccdaa4b1e",
    "sidewinder": "995561a68c8c5b142f13f1967730ce8c08d4f0db9574db8e987d915f2b118dcc",
    "wizard": "978539ff70085998485870a15d4ec81d3811442ac48f9265db668a396f6ff1eb",
}
BSP_WEATHER_PALETTE_OFFSET = 436
BSP_CLUSTER_BLOCK_OFFSET = 308
WEATHER_PALETTE_STRIDE = 0xF0
CLUSTER_STRIDE = 0x68
WEATHER_PARTICLE_REFERENCE_INDEX_OFFSET = 0x2C
CLUSTER_WEATHER_INDEX_OFFSET = 0x08
NONE = -1

import sys
sys.path.extend([str(ROOT / "tools"), str(ROOT / "submodules/halo-ps2/tools")])
from halo2ps2 import bsp, mapinfo, tagindex  # noqa: E402
from ctag_schema_walk import read_xbox_tag_region  # noqa: E402


def extract_function(path, name):
    source = path.read_text()
    matches = list(re.finditer(r"^[ \t]*(?:static\s+)?[\w\s*]+\b" +
                               re.escape(name) + r"\s*\([^;{}]*\)\s*\{",
                               source, re.MULTILINE))
    if len(matches) != 1:
        raise AssertionError(f"expected one definition for {name}, found {len(matches)}")
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
    raise AssertionError(f"unterminated function {name}")


def raw_mp_weather(map_name):
    path = MAP_ROOT / f"{map_name}.map"
    raw_map = path.read_bytes()
    map_hash = hashlib.sha256(raw_map).hexdigest()
    if map_hash != MAP_SHA256[map_name]:
        raise AssertionError(f"{map_name}: source map hash changed: {map_hash}")
    index = tagindex.TagIndex.read(path)
    tag_region, _tag_base, _ = read_xbox_tag_region(path)
    locations = bsp.locate(index, tag_region,
                           mapinfo.read_header(path).decompressed_size)
    if len(locations) != 1:
        raise AssertionError(f"{map_name}: expected one stock MP BSP, got {len(locations)}")
    location = locations[0]
    image = raw_map[location.file_offset:location.file_offset + location.size]
    if len(image) != location.size:
        raise AssertionError(f"{map_name}: truncated raw BSP image")
    root = struct.unpack_from("<I", image)[0] - location.address
    if root < 0 or root + 648 > len(image):
        raise AssertionError(f"{map_name}: invalid raw BSP root extent")

    def block(offset, stride, label):
        count, address = struct.unpack_from("<iI", image, root + offset)
        data_offset = address - location.address if address else 0
        if count < 0 or (count and (data_offset < 0 or
                                    data_offset + count * stride > len(image))):
            raise AssertionError(f"{map_name}: invalid raw {label} extent")
        return count, data_offset

    palette_count, palette_offset = block(BSP_WEATHER_PALETTE_OFFSET,
                                          WEATHER_PALETTE_STRIDE,
                                          "weather palette")
    cluster_count, cluster_offset = block(BSP_CLUSTER_BLOCK_OFFSET,
                                          CLUSTER_STRIDE, "cluster")
    particle_refs = []
    for i in range(palette_count):
        entry = palette_offset + i * WEATHER_PALETTE_STRIDE
        group, _name, _name_length, datum = struct.unpack_from("<4I", image, entry + 0x20)
        if group != int.from_bytes(b"rain", "big"):
            raise AssertionError(f"{map_name}: palette {i} particle ref is not rain")
        particle_refs.append(datum if datum != 0xFFFFFFFF else NONE)
    cluster_refs = [struct.unpack_from(
        "<h", image, cluster_offset + i * CLUSTER_STRIDE + CLUSTER_WEATHER_INDEX_OFFSET)[0]
        for i in range(cluster_count)]
    for i, weather_index in enumerate(cluster_refs):
        if weather_index != NONE and not 0 <= weather_index < palette_count:
            raise AssertionError(f"{map_name}: cluster {i} selects invalid palette {weather_index}")
    return {
        "map_hash": map_hash,
        "bsp_hash": hashlib.sha256(image).hexdigest(),
        "bsp_path": location.path,
        "particle_refs": particle_refs,
        "cluster_refs": cluster_refs,
    }


def c_int_array(values):
    return ",".join(str(value) for value in values) if values else "0"


class MultiplayerWeatherParticleConsumerTest(unittest.TestCase):
    def test_ce_selection_dispatch_against_all_raw_stock_mp_clusters(self):
        compiler = os.environ.get("CC", "cc")
        source_root = HCU / "source"
        weather_source = source_root / "effects/weather_particle_systems.c"
        scenario_source = source_root / "scenario/scenario.c"
        weather_dispatch = extract_function(weather_source, "weather_particle_systems_render")
        location_selection = extract_function(scenario_source, "scenario_location_underwater")

        cases = {name: raw_mp_weather(name) for name in MP_MAPS}
        self.assertEqual(set(cases), set(MP_MAPS))
        self.assertTrue(all(all(ref == NONE for ref in case["particle_refs"])
                            for case in cases.values()),
                        "all stock MP rain references should be NONE for this test oracle")

        declarations = []
        map_rows = []
        for index, (name, case) in enumerate(cases.items()):
            declarations.append(
                f"static struct structure_weather_palette_entry palette_{index}[] = {{" +
                ",".join("{ .particle_system = { .index = %d } }" % ref
                         for ref in case["particle_refs"]) + "};")
            declarations.append(
                f"static struct structure_cluster cluster_{index}[] = {{" +
                ",".join("{ .weather_palette_index = %d }" % ref
                         for ref in case["cluster_refs"]) + "};")
            map_rows.append(
                "{\"%s\", %du, %du, palette_%d, cluster_%d}" %
                (name, len(case["particle_refs"]), len(case["cluster_refs"]), index, index))

        harness = r'''
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
typedef unsigned char boolean;
typedef float real;
#define TRUE 1
#define FALSE 0
#define NONE (-1)
#define VALID_INDEX(i, count) ((i) >= 0 && (i) < (count))
#define match_assert(file, line, condition) ((void)0)
#define TAG_BLOCK_GET_ELEMENT(block, index, type) (&((type *)(block)->address)[index])
struct tag_block { int count; void *address; };
struct real_point3d { real x, y, z; };
typedef struct real_point3d real_point3d;
struct location { short cluster_index, leaf_index; };
struct structure_cluster { short unused[4]; short weather_palette_index; };
struct structure_fog_region { short unused, weather_palette_index; };
struct tag_reference { uint32_t group_tag; void *name; int name_length; long index; };
struct structure_weather_palette_entry { struct tag_reference particle_system; };
struct structure_bsp { struct tag_block fog_regions, clusters, weather_palette; };
struct weather_particle_system {
    long definition_index;
    struct location location;
    short weather_palette_index;
    boolean under_water;
};
struct render_camera { struct real_point3d position; };
struct render_state {
    short local_player_index, cluster_index, leaf_index;
    struct render_camera camera;
};
static struct structure_bsp active_bsp;
static struct weather_particle_system systems[4];
static struct render_state render;
static boolean render_particle_systems_enabled = TRUE;
boolean weather = TRUE;
static unsigned new_calls, delete_calls, update_render_calls, scenario_queries;
struct structure_bsp *global_structure_bsp_get(void) { return &active_bsp; }
static struct weather_particle_system *weather_particle_system_get(short index) {
    assert(index >= 0 && index < 4); return &systems[index];
}
short scenario_get_fog_region_index(const struct location *location,
                                    const struct real_point3d *position) {
    (void)location; (void)position; scenario_queries++; return NONE;
}
struct fog_definition { unsigned flags; };
long scenario_fog_region_get_fog_index(short index) { (void)index; return NONE; }
struct fog_definition *fog_definition_get(long index) { (void)index; return 0; }
#define TEST_FLAG(value, bit) (((value) >> (bit)) & 1u)
void weather_particle_system_new(short index, long definition, real scale) {
    (void)scale; new_calls++; systems[index].definition_index = definition;
}
void weather_particle_system_delete(short index) {
    delete_calls++; systems[index].definition_index = NONE;
}
static void weather_particle_system_render(short index) {
    (void)index; update_render_calls++;
}
__CE_LOCATION_SELECTION__
__CE_WEATHER_DISPATCH__
__RAW_MAP_TABLE__
struct raw_map_case {
    const char *name; unsigned palettes, clusters;
    struct structure_weather_palette_entry *palette;
    struct structure_cluster *cluster;
};
int main(void) {
    unsigned map_index, cluster_index, visited = 0;
    for (map_index = 0; map_index < sizeof(maps)/sizeof(maps[0]); ++map_index) {
        const struct raw_map_case *map = &maps[map_index];
        active_bsp.weather_palette.count = (int)map->palettes;
        active_bsp.weather_palette.address = map->palette;
        active_bsp.clusters.count = (int)map->clusters;
        active_bsp.clusters.address = map->cluster;
        active_bsp.fog_regions.count = 0;
        active_bsp.fog_regions.address = 0;
        memset(systems, 0, sizeof(systems));
        systems[0].definition_index = NONE;
        render.local_player_index = 0;
        render.leaf_index = NONE;
        render.camera.position.x = render.camera.position.y = render.camera.position.z = 0.0f;
        for (cluster_index = 0; cluster_index < map->clusters; ++cluster_index) {
            short expected = map->cluster[cluster_index].weather_palette_index;
            render.cluster_index = (short)cluster_index;
            weather_particle_systems_render();
            visited++;
            if (systems[0].location.cluster_index != (short)cluster_index ||
                systems[0].weather_palette_index != expected ||
                systems[0].definition_index != NONE || systems[0].under_water != FALSE ||
                new_calls || delete_calls || update_render_calls) {
                fprintf(stderr, "weather particle dispatch mismatch map=%s cluster=%u "
                    "selected=%d expected=%d definition=%ld new=%u delete=%u update=%u\n",
                    map->name, cluster_index, systems[0].weather_palette_index, expected,
                    systems[0].definition_index, new_calls, delete_calls, update_render_calls);
                return 2;
            }
        }
        printf("mp-weather-particle map=%s palettes=%u clusters=%u rain_refs=0 "
               "clusters_visited=%u ce_selection=passed update=not-entered status=passed\n",
               map->name, map->palettes, map->clusters, map->clusters);
    }
    {
        struct structure_weather_palette_entry control_palette[1] = {
            { .particle_system = { .index = 7 } }
        };
        struct structure_cluster control_cluster[1] = {
            { .weather_palette_index = 0 }
        };
        memset(systems, 0, sizeof(systems));
        systems[0].definition_index = NONE;
        active_bsp.weather_palette.count = 1;
        active_bsp.weather_palette.address = control_palette;
        active_bsp.clusters.count = 1;
        active_bsp.clusters.address = control_cluster;
        render.local_player_index = 0;
        render.cluster_index = 0;
        render.leaf_index = NONE;
        weather_particle_systems_render();
        if (scenario_queries != visited + 1 || new_calls != 1 || delete_calls != 0 ||
            update_render_calls != 1 || systems[0].definition_index != 7) {
            fprintf(stderr, "synthetic dispatch sensitivity control failed\n");
            return 4;
        }
        printf("mp-weather-particle-control rain_ref=7 new=1 update=1 status=passed\n");
    }
    printf("mp-weather-particle-summary maps=%u cluster_queries=%u new=%u delete=%u "
           "updates=%u result=passed\n", map_index, visited, new_calls,
           delete_calls, update_render_calls);
    return (map_index == 13 && scenario_queries == visited + 1 && visited == 239 &&
            new_calls == 1 && update_render_calls == 1) ? 0 : 3;
}
'''
        # Put the table after its element type is defined in the C source.
        table = "\n".join(declarations) + "\nstatic const struct raw_map_case maps[] = {" + ",".join(map_rows) + "};"
        # The source-extracted bodies follow their referenced declarations.
        harness = harness.replace("__CE_LOCATION_SELECTION__", location_selection)
        harness = harness.replace("__CE_WEATHER_DISPATCH__", weather_dispatch)
        harness = harness.replace("__RAW_MAP_TABLE__", "")
        # Insert map declarations/table after raw_map_case declaration, before main.
        anchor = "};\nint main(void) {"
        self.assertIn(anchor, harness)
        harness = harness.replace(anchor, "};\n" + table + "\nint main(void) {")

        with tempfile.TemporaryDirectory(prefix="hcu-mp-weather-particles-") as temp_name:
            temp = Path(temp_name)
            c_file = temp / "weather_particle_consumer.c"
            executable = temp / "weather-particle-consumer"
            c_file.write_text(harness)
            built = subprocess.run([compiler, "-std=c99", "-Wall", "-Wextra",
                                    "-Werror", str(c_file), "-o", str(executable)],
                                   capture_output=True, text=True)
            self.assertEqual(built.returncode, 0, built.stdout + built.stderr)
            run = subprocess.run([str(executable)], capture_output=True, text=True)
            self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
            self.assertEqual(run.stdout.count("ce_selection=passed update=not-entered"), 13)
            self.assertIn("mp-weather-particle-summary maps=13 cluster_queries=239 new=1 delete=0 updates=1 result=passed",
                          run.stdout)
            self.assertIn("mp-weather-particle-control rain_ref=7 new=1 update=1 status=passed",
                          run.stdout)
            self.assertEqual(len(cases), 13)


if __name__ == "__main__":
    unittest.main()
