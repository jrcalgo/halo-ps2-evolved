"""Execute CE runtime decal selection against raw stock Blood Gulch BSP bytes.

The fixture extracts the actual CE update body and supplies only bounded tag
blocks plus spies for decal effect creation/deletion. It does not link effects
or rendering.
"""
from pathlib import Path
import hashlib
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
HCU = ROOT / "submodules/halo-ce-universal"
SOURCE = HCU / "source/structures/structure_runtime_decals.c"
MAP = ROOT / "build/retail-maps/decompressed/bloodgulch.map"
sys.path.extend([str(ROOT / "tests"), str(ROOT / "tools"),
                 str(ROOT / "submodules/halo-ps2/tools")])
from halo2ps2 import bsp, mapinfo, tagindex  # noqa: E402
from ctag_schema_walk import read_xbox_tag_region  # noqa: E402


def extract_function(source, name):
    import re
    matches = list(re.finditer(r"^[ \t]*(?:static\s+)?[\w\s*]+\b" +
                               re.escape(name) + r"\s*\([^;{}]*\)\s*\{",
                               source, re.MULTILINE))
    if len(matches) != 1:
        raise AssertionError(f"expected one {name} definition, found {len(matches)}")
    start = matches[0].start()
    brace = source.find("{", start)
    depth = 0
    for pos in range(brace, len(source)):
        if source[pos] == "{":
            depth += 1
        elif source[pos] == "}":
            depth -= 1
            if depth == 0:
                return source[start:pos + 1]
    raise AssertionError(f"unterminated {name}")


def bloodgulch_raw_decal_fixture():
    index = tagindex.TagIndex.read(MAP)
    tag_region, _tag_base, _metadata = read_xbox_tag_region(MAP)
    locations = bsp.locate(index, tag_region, mapinfo.read_header(MAP).decompressed_size)
    if len(locations) != 1:
        raise AssertionError(f"expected one BSP, found {len(locations)}")
    location = locations[0]
    image = MAP.read_bytes()[location.file_offset:location.file_offset + location.size]
    root = struct.unpack_from("<I", image)[0] - location.address
    # Raw Xbox BSP root: clusters at +0x134, runtime decals at +0x258.
    cluster_count, cluster_address = struct.unpack_from("<iI", image, root + 0x134)
    decal_count, decal_address = struct.unpack_from("<iI", image, root + 0x258)
    cluster_offset = cluster_address - location.address
    decal_offset = decal_address - location.address
    if (cluster_count != 30 or decal_count != 8 or cluster_offset < 0 or
            decal_offset < 0 or cluster_offset + cluster_count * 0x68 > len(image) or
            decal_offset + decal_count * 16 > len(image)):
        raise AssertionError("Blood Gulch raw decal/cluster extents differ from pinned source case")
    clusters = []
    for i in range(cluster_count):
        first, count = struct.unpack_from("<hH", image, cluster_offset + i * 0x68 + 0x0C)
        clusters.append((first, count))
    records = []
    for i in range(decal_count):
        x, y, z, palette, unused, yaw, pitch = struct.unpack_from(
            "<3f4b", image, decal_offset + i * 16)
        records.append((x, y, z, palette & 0xFF, unused & 0xFF, yaw, pitch))
    if [(i, *clusters[i]) for i in range(len(clusters)) if clusters[i][1]] != [
            (6, 0, 4), (19, 4, 4)]:
        raise AssertionError("Blood Gulch raw cluster ownership changed")
    # Raw Xbox scenario root's decal palette block. Resolve each referenced
    # datum through this same stock map's tag index, which is the CE palette
    # reference index after tag loading.
    scenario = index.entries[index.header.scenario_tag_id & 0xFFFF]
    if scenario.group != "scnr":
        raise AssertionError("map scenario index is not an scnr tag")
    scenario_offset = scenario.data_address - _tag_base
    palette_count, palette_address = struct.unpack_from("<iI", tag_region,
                                                        scenario_offset + 0x3B4)
    palette_offset = palette_address - _tag_base
    if palette_count != 4 or palette_offset < 0 or palette_offset + 4 * 16 > len(tag_region):
        raise AssertionError("Blood Gulch scenario decal palette extent differs from source case")
    entry_index_by_datum = {entry.tag_id: i for i, entry in enumerate(index.entries)}
    palette_definitions = []
    for i in range(palette_count):
        entry_offset = palette_offset + i * 16
        group = struct.unpack_from("<I", tag_region, entry_offset)[0]
        datum = struct.unpack_from("<I", tag_region, entry_offset + 12)[0]
        target_index = entry_index_by_datum.get(datum)
        if group != int.from_bytes(b"deca", "big") or target_index is None or \
                index.entries[target_index].group != "deca":
            raise AssertionError(f"scenario decal palette entry {i} is not a resolvable deca tag")
        palette_definitions.append(target_index)
    return location, image, records, clusters, palette_definitions


def c_array(values, formatter):
    return ",\n".join("{" + ",".join(formatter(v) for v in row) + "}"
                     for row in values)


class RuntimeDecalConsumerTest(unittest.TestCase):
    def test_actual_ce_update_body_with_bloodgulch_source_records(self):
        compiler = shutil.which("gcc")
        if not compiler or not MAP.exists():
            self.skipTest("GCC and decompressed retail Blood Gulch fixture are required")
        source = SOURCE.read_text()
        update = extract_function(source, "structure_decals_update")
        disconnect = extract_function(source, "structure_decals_disconnect_from_structure_bsp")
        reconnect = extract_function(source, "structure_decals_reconnect_to_structure_bsp")
        location, image, records, clusters, palette_definitions = bloodgulch_raw_decal_fixture()
        source_sha = hashlib.sha256(MAP.read_bytes()).hexdigest()
        with tempfile.TemporaryDirectory() as temporary:
            temp = Path(temporary)
            cfile, exe = temp / "runtime_decals.c", temp / "runtime-decals"
            rows = c_array(records, lambda v: (f"{v:.9g}f" if isinstance(v, float)
                                                else str(v)))
            cluster_rows = ",\n".join(
                "{{0},%d,%d,{0}}" % row for row in clusters)
            palette_definition_rows = ",".join(str(value) for value in palette_definitions)
            palette_entry_rows = ",".join("{{%d}}" % value for value in palette_definitions)
            harness = r'''
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
typedef unsigned char byte;
typedef unsigned char boolean;
typedef unsigned short word;
typedef float real;
#define TRUE 1
#define FALSE 0
#define NONE -1
#define _pi 3.14159265358979323846f
#define match_assert(file, line, condition) ((void)0)
#define BIT_VECTOR_TEST_FLAG(bits, bit) (((bits)[(bit) >> 5] >> ((bit) & 31)) & 1)
struct tag_block { int32_t count; void *address; };
struct structure_cluster_runtime_decals { byte unused[12]; short first_decal_index; word decal_count; byte unused2[88]; };
struct structure_runtime_decal { struct { real x,y,z; } position; byte palette_index, unused; char yaw,pitch; };
struct tag_reference { long index; };
struct scenario_decal_palette_entry { struct tag_reference reference; };
struct structure_bsp { struct tag_block clusters, runtime_decals; };
struct scenario { struct tag_block decal_palette; };
typedef struct real_euler_angles2d { real yaw,pitch; } real_euler_angles2d;
typedef struct real_vector3d { real i,j,k; } real_vector3d;
struct structure_decals_globals { boolean reconnect_to_structure_bsp; byte pad[3]; };
static struct structure_decals_globals globals;
static struct structure_bsp bsp_fixture;
static struct scenario scenario_fixture;
static struct structure_decals_globals *structure_decals_globals = &globals;
static int create_count, delete_count, definition_count, failures;
static long created_definition[32];
static real created_position[32][3], created_normal[32][3];
static const int palette_definition[] = { __RAW_PALETTE_DEFINITIONS__ };
static struct structure_runtime_decal source_decals[] = { __RAW_DECAL_ROWS__ };
static struct structure_cluster_runtime_decals source_clusters[] = { __RAW_CLUSTER_ROWS__ };
static struct scenario_decal_palette_entry source_palette[] = {
    __RAW_PALETTE_ENTRIES__
};
struct structure_bsp *global_structure_bsp_get(void) { return &bsp_fixture; }
struct scenario *global_scenario_get(void) { return &scenario_fixture; }
void decal_definition_get(long index) { (void)index; definition_count++; }
void decal_new(long definition, const void *position, const void *normal,
               real scale, long permanent, long owner, boolean flag) {
    const real *p = position, *n = normal;
    (void)scale; (void)permanent; (void)owner; (void)flag;
    if (create_count < 32) {
        created_definition[create_count] = definition;
        memcpy(created_position[create_count], p, 3*sizeof(real));
        memcpy(created_normal[create_count], n, 3*sizeof(real));
    }
    create_count++;
}
void decals_delete_permanent_from_cluster(short cluster) { (void)cluster; delete_count++; }
void vector3d_from_euler_angles2d(struct real_vector3d *v, const struct real_euler_angles2d *a) {
    real cp = cosf(a->pitch);
    v->i = cosf(a->yaw)*cp; v->j = sinf(a->yaw)*cp; v->k = sinf(a->pitch);
}
#define TAG_BLOCK_GET_ELEMENT(block, index, type) (&((type *)(block)->address)[index])
enum { _error_silent = 0 };
void error(long level, const char *format, ...) { (void)level; (void)format; }
static void structure_decals_report_malformed(long index) { (void)index; }
__CE_DISCONNECT_BODY__
__CE_RECONNECT_BODY__
__CE_UPDATE_BODY__
static int check(int ok, const char *what) { if (!ok) { fprintf(stderr,"FAIL %s\n",what); failures++; } return ok; }
static int near(real a, real b) { return fabsf(a-b) < 1e-5f; }
int main(void) {
    unsigned long old_pvs[1] = {0}, new_pvs[1] = {(1UL<<6)|(1UL<<19)};
    int i;
    struct structure_runtime_decal *decal = source_decals;
    bsp_fixture.clusters.count = 30; bsp_fixture.clusters.address = source_clusters;
    bsp_fixture.runtime_decals.count = 8; bsp_fixture.runtime_decals.address = source_decals;
    scenario_fixture.decal_palette.count = 4; scenario_fixture.decal_palette.address = source_palette;
    structure_decals_update(old_pvs, new_pvs, 30);
    check(create_count == 8 && definition_count == 8, "visible clusters create all source decals");
    for (i=0; i<8; i++) {
        struct real_euler_angles2d a = { decal[i].yaw * (_pi/127.f), decal[i].pitch * (_pi/254.f) };
        struct real_vector3d expected = { cosf(a.yaw)*cosf(a.pitch), sinf(a.yaw)*cosf(a.pitch), sinf(a.pitch) };
        check(created_definition[i] == palette_definition[decal[i].palette_index], "palette selector resolves expected definition");
        check(near(created_position[i][0], decal[i].position.x) && near(created_position[i][1], decal[i].position.y) && near(created_position[i][2], decal[i].position.z), "raw source position reaches decal API");
        check(near(created_normal[i][0], expected.i) && near(created_normal[i][1], expected.j) && near(created_normal[i][2], expected.k), "CE orientation matches independent trig oracle");
    }
    check(delete_count == 0, "initial PVS entry does not delete");
    memcpy(old_pvs,new_pvs,sizeof(old_pvs)); new_pvs[0] &= ~(1UL<<6);
    structure_decals_update(old_pvs,new_pvs,30);
    check(delete_count == 1 && create_count == 8, "leaving one decal cluster deletes once");
    memcpy(old_pvs,new_pvs,sizeof(old_pvs));
    structure_decals_update(old_pvs,new_pvs,30);
    check(delete_count == 1 && create_count == 8, "stable PVS causes no duplicate lifecycle calls");
    structure_decals_disconnect_from_structure_bsp();
    check(delete_count == 3, "BSP disconnect deletes each populated decal cluster");
    structure_decals_reconnect_to_structure_bsp();
    structure_decals_update(old_pvs,new_pvs,30);
    check(create_count == 12, "BSP reconnect recreates visible decal cluster");
    puts("actual-ce-runtime-decals source=bloodgulch created=12 deleted_clusters=3 status=passed");
    return failures ? 1 : 0;
}
'''
            cfile.write_text(harness.replace("__RAW_DECAL_ROWS__", rows)
                             .replace("__RAW_CLUSTER_ROWS__", cluster_rows)
                             .replace("__RAW_PALETTE_DEFINITIONS__", palette_definition_rows)
                             .replace("__RAW_PALETTE_ENTRIES__", palette_entry_rows)
                             .replace("__CE_DISCONNECT_BODY__", disconnect)
                             .replace("__CE_RECONNECT_BODY__", reconnect)
                             .replace("__CE_UPDATE_BODY__", update))
            result = subprocess.run([compiler, "-std=gnu99", str(cfile), "-lm", "-o", str(exe)],
                                    capture_output=True, text=True)
            if result.returncode:
                self.fail(result.stderr)
            run = subprocess.run([str(exe)], capture_output=True, text=True)
            if run.returncode:
                self.fail(run.stdout + run.stderr)
            self.assertIn("status=passed", run.stdout)
            self.assertEqual(source_sha, "9eb0374cbe4571af640ae0d2e0ebf6119543cdbbece44d49543b4748c4cf0dc1")
            print(f"fixture map=bloodgulch map_sha256={source_sha} bsp={location.path} "
                  f"bsp_sha256={hashlib.sha256(image).hexdigest()}\n{run.stdout.strip()}")


if __name__ == "__main__":
    unittest.main()
