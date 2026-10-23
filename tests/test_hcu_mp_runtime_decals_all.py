"""Run CE runtime-decal update against raw Xbox BSP records for all 13 MP maps."""
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
SOURCE = HCU / "source/structures/structure_runtime_decals.c"
MAP_ROOT = ROOT / "build/retail-maps/decompressed"
OUT = ROOT / "build/step7-swarm/decals_all13"
MP_MAPS = (
    "beavercreek", "bloodgulch", "boardingaction", "carousel", "chillout",
    "damnation", "hangemhigh", "longest", "prisoner", "putput", "ratrace",
    "sidewinder", "wizard",
)
MAP_SHA256 = {
    "beavercreek": "eaf90b2abc4fd295469eb2d640063618b0d14396f28e7d7f1758e834c061c50a",
    "bloodgulch": "9eb0374cbe4571af640ae0d2e0ebf6119543cdbbece44d49543b4748c4cf0dc1",
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

sys.path.extend([str(ROOT / "tools"), str(ROOT / "submodules/halo-ps2/tools")])
from halo2ps2 import bsp, mapinfo, tagindex  # noqa: E402
from ctag_schema_walk import read_xbox_tag_region  # noqa: E402


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


def raw_decal_fixture(name):
    path = MAP_ROOT / f"{name}.map"
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if digest != MAP_SHA256[name]:
        raise AssertionError(f"{name}: source hash changed")
    index = tagindex.TagIndex.read(path)
    tag_region, tag_base, _ = read_xbox_tag_region(path)
    locations = bsp.locate(index, tag_region, mapinfo.read_header(path).decompressed_size)
    if len(locations) != 1:
        raise AssertionError(f"{name}: expected one BSP")
    location = locations[0]
    image = path.read_bytes()[location.file_offset:location.file_offset + location.size]
    root = struct.unpack_from("<I", image)[0] - location.address
    cluster_count, cluster_address = struct.unpack_from("<iI", image, root + 0x134)
    decal_count, decal_address = struct.unpack_from("<iI", image, root + 0x258)
    cluster_offset = cluster_address - location.address if cluster_address else 0
    decal_offset = decal_address - location.address if decal_address else 0
    if cluster_count <= 0 or cluster_offset < 0:
        raise AssertionError(f"{name}: invalid cluster block")
    if decal_count < 0 or (decal_count and decal_offset < 0):
        raise AssertionError(f"{name}: invalid runtime decal block")
    clusters = []
    for i in range(cluster_count):
        first, count = struct.unpack_from("<hH", image, cluster_offset + i * 0x68 + 0x0C)
        clusters.append((first, count))
    records = []
    for i in range(decal_count):
        x, y, z, palette, unused, yaw, pitch = struct.unpack_from(
            "<3f4b", image, decal_offset + i * 16)
        records.append((x, y, z, palette & 0xFF, unused & 0xFF, yaw, pitch))
        if not 0 <= (palette & 0xFF) < 256:
            raise AssertionError(f"{name}: palette index out of range")
    scenario = index.entries[index.header.scenario_tag_id & 0xFFFF]
    scenario_offset = scenario.data_address - tag_base
    palette_count, palette_address = struct.unpack_from(
        "<iI", tag_region, scenario_offset + 0x3B4)
    palette_offset = palette_address - tag_base if palette_address else 0
    entry_index_by_datum = {entry.tag_id: i for i, entry in enumerate(index.entries)}
    palette_definitions = []
    for i in range(palette_count):
        entry_offset = palette_offset + i * 16
        group = struct.unpack_from("<I", tag_region, entry_offset)[0]
        datum = struct.unpack_from("<I", tag_region, entry_offset + 12)[0]
        target_index = entry_index_by_datum.get(datum)
        if group != int.from_bytes(b"deca", "big") or target_index is None:
            palette_definitions.append(-1)
        else:
            palette_definitions.append(target_index)
    populated = [i for i, (_first, count) in enumerate(clusters) if count]
    expected_create = sum(count for _first, count in clusters if count)
    return {
        "map": name,
        "source_map_sha256": digest,
        "cluster_count": cluster_count,
        "decal_count": decal_count,
        "populated_clusters": populated,
        "expected_create": expected_create,
        "records": records,
        "clusters": clusters,
        "palette_definitions": palette_definitions,
    }


def c_records(records):
    rows = []
    for x, y, z, palette, unused, yaw, pitch in records:
        rows.append("{%gf,%gf,%gf,%d,%d,%d,%d}" % (x, y, z, palette, unused, yaw, pitch))
    return ",".join(rows) if rows else "{0}"


def c_clusters(clusters):
    return ",".join("{{0},%d,%d,{0}}" % row for row in clusters)


def pvs_init(populated, cluster_count, indent="    "):
    words = (cluster_count + 31) // 32
    bits = [0] * max(words, 1)
    for cluster in populated:
        bits[cluster >> 5] |= 1 << (cluster & 31)
    lines = [f"{indent}unsigned long old_pvs[{max(words, 1)}] = {{0}};"]
    lines.append(f"{indent}unsigned long new_pvs[{max(words, 1)}] = {{" +
                 ",".join(f"{value}UL" for value in bits) + "};")
    return "\n".join(lines)


class MultiplayerRuntimeDecalsAllTest(unittest.TestCase):
    def test_ce_update_against_all_13_raw_bsp_images(self):
        source = SOURCE.read_text()
        update = extract_function(source, "structure_decals_update")
        disconnect = extract_function(source, "structure_decals_disconnect_from_structure_bsp")
        reconnect = extract_function(source, "structure_decals_reconnect_to_structure_bsp")
        OUT.mkdir(parents=True, exist_ok=True)
        rows = []
        with tempfile.TemporaryDirectory(prefix="hcu-mp-decals-") as temp_name:
            temp = Path(temp_name)
            for name in MP_MAPS:
                fixture = raw_decal_fixture(name)
                palette = fixture["palette_definitions"] or [-1]
                cluster_count = fixture["cluster_count"]
                expected = fixture["expected_create"]
                populated = fixture["populated_clusters"]
                first_leave = populated[0] if populated else -1
                leave_count = fixture["clusters"][first_leave][1] if first_leave >= 0 else 0
                harness = r'''
#include <math.h>
#include <stdint.h>
#include <stdio.h>
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
static long created_definition[4096];
static real created_position[4096][3];
static const int palette_definition[] = { __PALETTE__ };
static struct structure_runtime_decal source_decals[] = { __RECORDS__ };
static struct structure_cluster_runtime_decals source_clusters[] = { __CLUSTERS__ };
static struct scenario_decal_palette_entry source_palette[] = { __PALETTE_ENTRIES__ };
struct structure_bsp *global_structure_bsp_get(void) { return &bsp_fixture; }
struct scenario *global_scenario_get(void) { return &scenario_fixture; }
void decal_definition_get(long index) { (void)index; definition_count++; }
void decal_new(long definition, const void *position, const void *normal,
               real scale, long permanent, long owner, boolean flag) {
    const real *p = position;
    (void)normal; (void)scale; (void)permanent; (void)owner; (void)flag;
    if (create_count < 4096) {
        created_definition[create_count] = definition;
        created_position[create_count][0] = p[0];
        created_position[create_count][1] = p[1];
        created_position[create_count][2] = p[2];
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
__DISCONNECT__
__RECONNECT__
__UPDATE__
static int check(int ok, const char *what) {
    if (!ok) { fprintf(stderr, "FAIL %s\n", what); failures++; }
    return ok;
}
int main(void) {
__PVS__
    int populated = __POPULATED__;
    int expected = __EXPECTED__;
    int first_leave = __FIRST_LEAVE__;
    bsp_fixture.clusters.count = __CLUSTER_COUNT__;
    bsp_fixture.clusters.address = source_clusters;
    bsp_fixture.runtime_decals.count = __DECAL_COUNT__;
    bsp_fixture.runtime_decals.address = source_decals;
    scenario_fixture.decal_palette.count = __PALETTE_COUNT__;
    scenario_fixture.decal_palette.address = source_palette;
    structure_decals_update(old_pvs, new_pvs, __CLUSTER_COUNT__);
    check(create_count == expected, "visible clusters create source decals");
    check(delete_count == 0, "initial PVS entry does not delete");
    if (first_leave >= 0) {
        memcpy(old_pvs, new_pvs, sizeof(old_pvs));
        new_pvs[first_leave >> 5] &= ~(1UL << (first_leave & 31));
        structure_decals_update(old_pvs, new_pvs, __CLUSTER_COUNT__);
        check(delete_count == 1, "leaving one decal cluster deletes once");
        memcpy(old_pvs, new_pvs, sizeof(old_pvs));
        structure_decals_update(old_pvs, new_pvs, __CLUSTER_COUNT__);
        check(delete_count == 1 && create_count == expected, "stable PVS is idle");
    }
    structure_decals_disconnect_from_structure_bsp();
    check(delete_count == populated + (first_leave >= 0 ? 1 : 0),
          "disconnect deletes each populated cluster");
    structure_decals_reconnect_to_structure_bsp();
    structure_decals_update(old_pvs, new_pvs, __CLUSTER_COUNT__);
    printf("mp-decals map=__NAME__ clusters=%d decals=%d created=%d populated=%d status=passed\n",
           __CLUSTER_COUNT__, __DECAL_COUNT__, create_count, populated);
    return failures ? 1 : 0;
}
'''
                text = (harness
                        .replace("__PALETTE__", ",".join(str(v) for v in palette))
                        .replace("__RECORDS__", c_records(fixture["records"]))
                        .replace("__CLUSTERS__", c_clusters(fixture["clusters"]))
                        .replace("__PALETTE_ENTRIES__",
                                 ",".join("{{%d}}" % v for v in palette))
                        .replace("__DISCONNECT__", disconnect)
                        .replace("__RECONNECT__", reconnect)
                        .replace("__UPDATE__", update)
                        .replace("__PVS__", pvs_init(populated, cluster_count))
                        .replace("__POPULATED__", str(len(populated)))
                        .replace("__EXPECTED__", str(expected))
                        .replace("__FIRST_LEAVE__", str(first_leave))
                        .replace("__CLUSTER_COUNT__", str(cluster_count))
                        .replace("__DECAL_COUNT__", str(fixture["decal_count"]))
                        .replace("__PALETTE_COUNT__", str(len(palette)))
                        .replace("__NAME__", name))
                c_file = temp / f"{name}.c"
                exe = temp / name
                c_file.write_text(text)
                built = subprocess.run(
                    ["cc", "-std=gnu99", str(c_file), "-lm", "-o", str(exe)],
                    capture_output=True, text=True)
                self.assertEqual(built.returncode, 0, name + "\n" + built.stderr)
                run = subprocess.run([str(exe)], capture_output=True, text=True)
                self.assertEqual(run.returncode, 0, name + "\n" + run.stdout + run.stderr)
                self.assertIn("status=passed", run.stdout)
                rows.append({
                    "map": name,
                    "source_map_sha256": fixture["source_map_sha256"],
                    "clusters": cluster_count,
                    "decals": fixture["decal_count"],
                    "populated_clusters": len(populated),
                    "expected_create": expected,
                    "leave_count": leave_count,
                    "stdout": run.stdout.strip(),
                })
        (OUT / "decal-inventory.json").write_text(
            json.dumps(rows, indent=2, sort_keys=True) + "\n")
        self.assertEqual(len(rows), 13)


if __name__ == "__main__":
    unittest.main()
