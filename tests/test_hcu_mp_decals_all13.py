"""Run CE structure-decal lifecycle against all 13 stock multiplayer maps.

The Blood Gulch consumer stays untouched. This test reads each map's raw Xbox
BSP and scenario, feeds those bytes to the extracted CE functions
structure_decals_update, structure_decals_disconnect_from_structure_bsp and
structure_decals_reconnect_to_structure_bsp, and compares every decal_new
request with an oracle computed from the same raw bytes.
"""
from pathlib import Path
import hashlib
import math
import os
import shutil
import struct
import subprocess
import sys
import traceback
import unittest

ROOT = Path(__file__).resolve().parents[1]
HCU = ROOT / "submodules/halo-ce-universal"
OUT = ROOT / "build/step7-swarm/decals"
SOURCE = HCU / "source/structures/structure_runtime_decals.c"
REAL_MATH_C = HCU / "source/math/real_math.c"
REAL_MATH_H = HCU / "source/math/real_math.h"
CSERIES_H = HCU / "source/cseries/cseries.h"
TAG_GROUPS_H = HCU / "source/tag_files/tag_groups.h"
BSP_H = HCU / "source/structures/structure_bsp_definitions.h"
SCENARIO_H = HCU / "source/scenario/scenario_definitions.h"
MAP_DIR = ROOT / "build/retail-maps/decompressed"

# ILP32 tag_block is 12 bytes. scenario.device_groups is 0x288 and
# scenario.netgame_flags is 0x378 (20 blocks). scenario.decal_palette is five
# tag_blocks after netgame_flags. structure_bsp.clusters is 0x134;
# weather_palette is 0x1B4; runtime_decals follows the same tag_block/tag_data
# stride and lands at 0x258. Cluster stride 0x68 and the decal range at +0x0C
# are structure_cluster_runtime_decals / structure_cluster_schema.
CLUSTER_BLOCK_OFFSET = 0x134
RUNTIME_DECAL_BLOCK_OFFSET = 0x258
CLUSTER_STRIDE = 0x68
CLUSTER_DECAL_OFFSET = 0x0C
RUNTIME_DECAL_STRIDE = 16
SCENARIO_DECAL_PALETTE_OFFSET = 0x3B4
PALETTE_STRIDE = 16
BSP_ROOT_BYTES = 0x264
SCALE_1 = 0x3F800000

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

sys.path.extend([str(ROOT / "tests"), str(ROOT / "tools"),
                 str(ROOT / "submodules/halo-ps2/tools")])
from halo2ps2 import bsp, mapinfo, tagindex  # noqa: E402
from ctag_schema_walk import read_xbox_tag_region  # noqa: E402
from host_abi32 import flags as host_abi32_flags  # noqa: E402
from test_hcu_runtime_decals_consumer import (  # noqa: E402
    bloodgulch_raw_decal_fixture, extract_function)

_PI = struct.unpack("<f", struct.pack("<f", 3.14159265358979323846))[0]
_PI_OVER_127 = struct.unpack("<f", struct.pack("<f", _PI / 127.0))[0]
_PI_OVER_254 = struct.unpack("<f", struct.pack("<f", _PI / 254.0))[0]


def sha256_file(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def f32(value):
    return struct.unpack("<f", struct.pack("<f", float(value)))[0]


def f32_bits(value):
    return struct.unpack("<I", struct.pack("<f", f32(value)))[0]


def cosine(angle):
    # CE's real_math.h inline returns float, so the double libm result is
    # rounded before vector3d_from_euler_angles2d multiplies it.
    return f32(math.cos(float(angle)))


def sine(angle):
    return f32(math.sin(float(angle)))


def normal_bits(yaw, pitch):
    """Independent raw-yaw/pitch normal. Mirrors the CE formula, not its call."""
    yaw_r = f32(int(yaw) * _PI_OVER_127)
    pitch_r = f32(int(pitch) * _PI_OVER_254)
    cosine_pitch = cosine(pitch_r)
    return (
        f32_bits(cosine(yaw_r) * cosine_pitch),
        f32_bits(sine(yaw_r) * cosine_pitch),
        f32_bits(sine(pitch_r)),
    )


def c_string(text):
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'


def extract_struct(text, name):
    marker = f"struct {name}\n"
    start = text.index(marker)
    opening = text.index("{", start)
    depth = 0
    for pos in range(opening, len(text)):
        if text[pos] == "{":
            depth += 1
        elif text[pos] == "}":
            depth -= 1
            if depth == 0:
                end = pos + 1
                if end < len(text) and text[end] == ";":
                    end += 1
                return text[start:end]
    raise AssertionError(f"unterminated struct {name}")


def macro_block(text):
    start = text.index("#define FLAG(b)")
    end = text.index("#define VALID_FLAGS")
    return text[start:end].strip()


def static_inline(body, name):
    body = body.lstrip()
    if not body.startswith("__inline"):
        raise AssertionError(f"{name} extract did not start with __inline")
    # Linkage only. -O0 does not emit a bare __inline, and the body stays the CE inline.
    return "static " + body


def load_ce_text():
    runtime = SOURCE.read_text()
    real_c = REAL_MATH_C.read_text()
    real_h = REAL_MATH_H.read_text()
    cseries = CSERIES_H.read_text()
    errors = (HCU / "source/cseries/errors.h").read_text()
    error_start = errors.index("\t_error_immediate = 0,")
    error_end = errors.index("NUMBER_OF_ERROR_MESSAGE_PRIORITIES,", error_start)
    error_enum = "enum {\n" + errors[error_start:error_end] + "\tNUMBER_OF_ERROR_MESSAGE_PRIORITIES\n};"
    tags = TAG_GROUPS_H.read_text()
    bsp_h = BSP_H.read_text()
    scenario_h = SCENARIO_H.read_text()
    pieces = {
        "update": extract_function(runtime, "structure_decals_update"),
        "disconnect": extract_function(runtime, "structure_decals_disconnect_from_structure_bsp"),
        "reconnect": extract_function(runtime, "structure_decals_reconnect_to_structure_bsp"),
        "report": extract_function(runtime, "structure_decals_report_malformed"),
        "vector": extract_function(real_c, "vector3d_from_euler_angles2d"),
        "sine": static_inline(extract_function(real_h, "sine"), "sine"),
        "cosine": static_inline(extract_function(real_h, "cosine"), "cosine"),
        "fast": extract_function(tags, "tag_block_get_element_fast"),
        "macros": macro_block(cseries),
        "pi": next(line for line in real_h.splitlines() if line.startswith("#define _pi ")),
        "tag_element": next(line for line in tags.splitlines()
                            if line.startswith("#define TAG_BLOCK_GET_ELEMENT(")),
        "runtime_decal": extract_struct(bsp_h, "structure_runtime_decal"),
        "cluster_decals": extract_struct(bsp_h, "structure_cluster_runtime_decals"),
        "palette_entry": extract_struct(scenario_h, "scenario_decal_palette_entry"),
        "tag_block": extract_struct(tags, "tag_block"),
        "tag_reference": extract_struct(tags, "tag_reference"),
        "globals": extract_struct(runtime, "structure_decals_globals"),
        "errors": error_enum,
    }
    required = {
        "update": ("decal_new(", "vector3d_from_euler_angles2d(",
                   "reconnect_to_structure_bsp = FALSE", "decals_delete_permanent_from_cluster("),
        "disconnect": ("decals_delete_permanent_from_cluster(", "runtime_decals.count"),
        "reconnect": ("reconnect_to_structure_bsp = TRUE",),
        "report": ("warned_about_runtime_decals", "error("),
        "vector": ("cosine(angles->pitch)", "sine(angles->pitch)", "cosine(angles->yaw)"),
        "sine": ("return sin(angle);",),
        "cosine": ("return cos(angle);",),
        "fast": ("tag_block_get_element_with_size", "element_size"),
    }
    for key, needles in required.items():
        for needle in needles:
            if needle not in pieces[key]:
                raise AssertionError(f"extracted {key} lost {needle}")
    if "LONG_BITS = 32" not in cseries or "LONG_BITS_BITS = 5" not in cseries:
        raise AssertionError("CE long bit-width constants moved")
    if "#define NONE -1" not in cseries or "#define TRUE 1" not in cseries:
        raise AssertionError("CE NONE/TRUE macros moved")
    return pieces


def read_map(name):
    path = MAP_DIR / f"{name}.map"
    data = path.read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    if digest != MAP_SHA256[name]:
        raise AssertionError(f"{name} map sha256 {digest} != pinned retail digest")
    index = tagindex.TagIndex.read(path)
    tag_region, tag_base, _metadata = read_xbox_tag_region(path)
    locations = bsp.locate(index, tag_region, mapinfo.read_header(path).decompressed_size)
    if len(locations) != 1:
        raise AssertionError(f"{name}: expected one BSP, found {len(locations)}")
    location = locations[0]
    image = data[location.file_offset:location.file_offset + location.size]
    if len(image) != location.size:
        raise AssertionError(f"{name}: truncated BSP image")
    root_ptr = struct.unpack_from("<I", image, 0)[0]
    root = root_ptr - location.address
    if root < 0 or root + BSP_ROOT_BYTES > len(image):
        raise AssertionError(f"{name}: BSP root {root:#x} outside image")
    cluster_count, cluster_address = struct.unpack_from("<iI", image, root + CLUSTER_BLOCK_OFFSET)
    decal_count, decal_address = struct.unpack_from("<iI", image, root + RUNTIME_DECAL_BLOCK_OFFSET)
    if cluster_count <= 0 or cluster_count > 32767:
        raise AssertionError(f"{name}: cluster count {cluster_count}")
    cluster_offset = cluster_address - location.address
    cluster_bytes = cluster_count * CLUSTER_STRIDE
    if cluster_offset < 0 or cluster_offset + cluster_bytes > len(image):
        raise AssertionError(f"{name}: cluster block leaves the BSP")
    if decal_count < 0 or (decal_count == 0) != (decal_address == 0):
        raise AssertionError(f"{name}: runtime decal count/address {decal_count}/{decal_address:#x}")
    decal_offset = decal_address - location.address if decal_count else 0
    decal_bytes = decal_count * RUNTIME_DECAL_STRIDE
    if decal_count and (decal_offset < 0 or decal_offset + decal_bytes > len(image)):
        raise AssertionError(f"{name}: runtime decals leave the BSP")
    clusters = []
    for cluster_index in range(cluster_count):
        first, count = struct.unpack_from(
            "<hH", image, cluster_offset + cluster_index * CLUSTER_STRIDE + CLUSTER_DECAL_OFFSET)
        clusters.append((first, count))
    raw_decals = image[decal_offset:decal_offset + decal_bytes] if decal_count else b""
    decals = []
    unused_nonzero = 0
    for decal_index in range(decal_count):
        raw = raw_decals[decal_index * RUNTIME_DECAL_STRIDE:(decal_index + 1) * RUNTIME_DECAL_STRIDE]
        x, y, z = struct.unpack_from("<III", raw, 0)
        palette = raw[12]
        unused = raw[13]
        yaw, pitch = struct.unpack_from("<bb", raw, 14)
        if unused:
            unused_nonzero += 1
        decals.append({
            "x": x, "y": y, "z": z, "palette": palette, "unused": unused,
            "yaw": yaw, "pitch": pitch,
        })
    scenario = index.scenario
    if scenario.group != "scnr":
        raise AssertionError(f"{name}: scenario group {scenario.group}")
    scenario_offset = scenario.data_address - tag_base
    if scenario_offset < 0 or scenario_offset + SCENARIO_DECAL_PALETTE_OFFSET + 8 > len(tag_region):
        raise AssertionError(f"{name}: scenario decal palette header outside tag region")
    palette_count, palette_address = struct.unpack_from(
        "<iI", tag_region, scenario_offset + SCENARIO_DECAL_PALETTE_OFFSET)
    if palette_count < 0 or (palette_count == 0) != (palette_address == 0):
        raise AssertionError(f"{name}: decal palette count/address {palette_count}/{palette_address:#x}")
    palette_offset = palette_address - tag_base if palette_count else 0
    if palette_count and (palette_offset < 0 or
                          palette_offset + palette_count * PALETTE_STRIDE > len(tag_region)):
        raise AssertionError(f"{name}: decal palette leaves the tag region")
    by_datum = {}
    for entry_index, entry in enumerate(index.entries):
        if entry.index != entry_index:
            raise AssertionError(f"{name}: tag id index {entry.index} != slot {entry_index}")
        by_datum[entry.tag_id] = entry
    palette = []
    for palette_index in range(palette_count):
        entry_offset = palette_offset + palette_index * PALETTE_STRIDE
        group = struct.unpack_from("<I", tag_region, entry_offset)[0]
        datum = struct.unpack_from("<I", tag_region, entry_offset + 12)[0]
        if group != int.from_bytes(b"deca", "big"):
            raise AssertionError(f"{name}: palette {palette_index} group {group:#x} is not deca")
        entry = by_datum.get(datum)
        if entry is None or entry.group != "deca" or not entry.path or "\t" in entry.path:
            raise AssertionError(f"{name}: palette {palette_index} datum {datum:#x} is not a deca tag")
        palette.append({
            "group": group, "datum": datum, "tag_index": entry.index, "path": entry.path,
        })
    owned = []
    for cluster_index, (first, count) in enumerate(clusters):
        if count == 0:
            if first != -1:
                raise AssertionError(f"{name}: empty cluster {cluster_index} first={first}, expected NONE")
            continue
        if first < 0:
            raise AssertionError(f"{name}: cluster {cluster_index} decal range {first},{count}")
        for offset in range(count):
            owned.append(first + offset)
    if owned != list(range(decal_count)):
        raise AssertionError(f"{name}: cluster decal ranges do not partition 0..{decal_count - 1}: {owned}")
    for decal in decals:
        if decal["palette"] >= len(palette):
            raise AssertionError(f"{name}: palette index {decal['palette']} outside {len(palette)}")
    if name == "bloodgulch":
        _location, pinned_image, records, pinned_clusters, pinned_palette = bloodgulch_raw_decal_fixture()
        if pinned_image != image or pinned_clusters != clusters:
            raise AssertionError("general reader disagrees with the Blood Gulch decal fixture")
        if pinned_palette != [entry["tag_index"] for entry in palette]:
            raise AssertionError("Blood Gulch palette resolution disagrees with the existing fixture")
        for record, decal in zip(records, decals):
            raw_x, raw_y, raw_z = struct.unpack("<3f", struct.pack("<III", decal["x"], decal["y"], decal["z"]))
            if (record[0], record[1], record[2], record[3], record[4], record[5], record[6]) != (
                    raw_x, raw_y, raw_z, decal["palette"], decal["unused"], decal["yaw"], decal["pitch"]):
                raise AssertionError(f"Blood Gulch record mismatch {record} vs {decal}")
    return {
        "name": name,
        "map_sha256": digest,
        "bsp_path": location.path,
        "bsp_sha256": hashlib.sha256(image).hexdigest(),
        "bsp_bytes": len(image),
        "clusters": clusters,
        "decals": decals,
        "raw_decals": raw_decals,
        "decal_address": decal_address,
        "palette": palette,
        "unused_nonzero": unused_nonzero,
        "image_sha_before": hashlib.sha256(image).hexdigest(),
    }


def oracle_requests(fix):
    requests = []
    for cluster_index, (first, count) in enumerate(fix["clusters"]):
        if first == -1 or count == 0:
            continue
        for offset in range(count):
            decal_index = first + offset
            if decal_index < 0 or decal_index >= len(fix["decals"]):
                break
            decal = fix["decals"][decal_index]
            if decal["palette"] >= len(fix["palette"]):
                continue
            entry = fix["palette"][decal["palette"]]
            if entry["tag_index"] < 0:
                continue
            ni, nj, nk = normal_bits(decal["yaw"], decal["pitch"])
            requests.append({
                "cluster": cluster_index,
                "decal_index": decal_index,
                "palette": decal["palette"],
                "tag_index": entry["tag_index"],
                "path": entry["path"],
                "datum": entry["datum"],
                "x": decal["x"], "y": decal["y"], "z": decal["z"],
                "i": ni, "j": nj, "k": nk,
                "yaw": decal["yaw"], "pitch": decal["pitch"],
                "scale": SCALE_1, "permanent": 1, "sequence": -1, "editor": 0,
            })
    return requests


def render_c(fix, ce):
    paths = {}
    for entry in fix["palette"]:
        previous = paths.get(entry["tag_index"])
        if previous is not None and previous != entry["path"]:
            raise AssertionError(f"{fix['name']}: tag {entry['tag_index']} has two paths")
        paths[entry["tag_index"]] = entry["path"]
    path_cases = "\n".join(
        f"    case {index}: return {c_string(path)};" for index, path in sorted(paths.items()))
    cluster_rows = ",\n".join(
        "    { .first_decal_index = %d, .decal_count = %d }" % row for row in fix["clusters"])
    if fix["raw_decals"]:
        raw_bytes = ", ".join(f"0x{byte:02x}" for byte in fix["raw_decals"])
        decal_data = f"""static unsigned char raw_decal_bytes[] = {{ {raw_bytes} }};
static struct structure_runtime_decal decal_storage[DECAL_TOTAL];
static struct structure_runtime_decal *decal_base = decal_storage;"""
    else:
        decal_data = "static struct structure_runtime_decal *decal_base = 0;"
    if fix["palette"]:
        palette_rows = ",\n".join(
            "    { { 0x%08xUL, 0, 0, %d } }" % (entry["group"], entry["tag_index"])
            for entry in fix["palette"])
        palette_data = f"static struct scenario_decal_palette_entry palette[PALETTE_TOTAL] = {{\n{palette_rows}\n}};"
    else:
        palette_data = ""
    bodies = "\n".join((ce["sine"], ce["cosine"], ce["vector"], ce["report"],
                        ce["disconnect"], ce["reconnect"], ce["update"]))
    return f"""/* Generated fixture. CE function bodies below are verbatim extracts. */
#include <math.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
typedef unsigned char byte;
typedef unsigned short word;
typedef float real;
typedef byte boolean;
#define TRUE 1
#define FALSE 0
#define NONE -1
{ce["errors"]}
{ce["pi"]}
#define match_assert(file, line, condition) ((void)0)
enum {{ LONG_BITS = 32, LONG_BITS_BITS = 5 }};
{ce["macros"]}
{ce["tag_element"]}
{ce["tag_reference"]}
{ce["tag_block"]}
struct tag_block_definition {{
    char *name;
    unsigned long flags;
    long maximum_element_count;
    long element_size;
}};
typedef struct real_point3d {{ real x, y, z; }} real_point3d;
typedef struct real_vector3d {{ real i, j, k; }} real_vector3d;
typedef struct real_euler_angles2d {{ real yaw, pitch; }} real_euler_angles2d;
{ce["runtime_decal"]}
{ce["cluster_decals"]}
{ce["palette_entry"]}
{ce["globals"]}
struct structure_bsp {{ struct tag_block clusters; struct tag_block runtime_decals; }};
struct scenario {{ struct tag_block decal_palette; }};
#define CLUSTER_TOTAL {len(fix["clusters"])}
#define DECAL_TOTAL {len(fix["decals"])}
#define PALETTE_TOTAL {len(fix["palette"])}
static const char map_name[] = {c_string(fix["name"])};
static struct structure_decals_globals globals_storage;
static struct structure_decals_globals *structure_decals_globals = &globals_storage;
static boolean warned_about_runtime_decals;
static struct structure_bsp bsp_fixture;
static struct scenario scenario_fixture;
static const char *phase = "none";
static int spy_cluster = -1;
static int create_count, delete_count, definition_count, error_calls, fast_fallback;
static int step_creates, step_deletes, step_defs, step_errors;
static struct structure_cluster_runtime_decals clusters[CLUSTER_TOTAL] = {{
{cluster_rows}
}};
{decal_data}
static long decal_limit = DECAL_TOTAL;
{palette_data}
static const char *tag_path(long index) {{
    switch (index) {{
{path_cases}
    default: return "";
    }}
}}
struct structure_bsp *global_structure_bsp_get(void) {{ return &bsp_fixture; }}
struct scenario *global_scenario_get(void) {{ return &scenario_fixture; }}
void *tag_block_get_element_with_size(struct tag_block const *block, long index, long element_size) {{
    (void)block; (void)index; (void)element_size;
    fast_fallback++;
    return 0;
}}
{ce["fast"]}
static int error_sink;
void error(long level, const char *format, ...) {{ (void)level; (void)format; error_calls++; error_sink++; }}
void decal_definition_get(long index) {{ (void)index; definition_count++; }}
void decals_delete_permanent_from_cluster(short cluster_index) {{
    printf("DELETE\\t%s\\t%d\\n", phase, (int)cluster_index);
    delete_count++;
}}
static uint32_t fbits(const void *pointer) {{
    uint32_t bits;
    memcpy(&bits, pointer, 4);
    return bits;
}}
void decal_new(long decal_definition_index, real_point3d const *origin, real_vector3d const *velocity,
               real radius_modifier, boolean permanent, short forced_sequence_index, void *editor_geometry) {{
    long decal_index = -1;
    unsigned palette = 255;
    if (decal_base && origin) {{
        uintptr_t off = (uintptr_t)origin - (uintptr_t)decal_base;
        if (off % sizeof(*decal_base) == 0) {{
            decal_index = (long)(off / sizeof(*decal_base));
            if (decal_index >= 0 && decal_index < decal_limit)
                palette = decal_base[decal_index].palette_index;
            else
                decal_index = -1;
        }}
    }}
    printf("CREATE\\t%s\\t%d\\t%ld\\t%u\\t%ld\\t%s\\t%08x\\t%08x\\t%08x\\t%08x\\t%08x\\t%08x\\t%08x\\t%u\\t%d\\t%d\\n",
           phase, spy_cluster, decal_index, palette, decal_definition_index, tag_path(decal_definition_index),
           origin ? fbits(&origin->x) : 0u, origin ? fbits(&origin->y) : 0u, origin ? fbits(&origin->z) : 0u,
           velocity ? fbits(&velocity->i) : 0u, velocity ? fbits(&velocity->j) : 0u, velocity ? fbits(&velocity->k) : 0u,
           fbits(&radius_modifier), (unsigned)permanent, (int)forced_sequence_index, editor_geometry ? 1 : 0);
    create_count++;
}}
{bodies}
static void begin_step(const char *name, int cluster) {{
    phase = name;
    spy_cluster = cluster;
    step_creates = create_count;
    step_deletes = delete_count;
    step_defs = definition_count;
    step_errors = error_calls;
}}
static void end_step(void) {{
    printf("STEP\\t%s\\t%d\\t%d\\t%d\\t%d\\t%d\\n", phase, spy_cluster,
           create_count - step_creates, delete_count - step_deletes,
           definition_count - step_defs, error_calls - step_errors);
}}
static int abi_ok(void) {{
    return sizeof(long) == 4 && sizeof(void *) == 4 && sizeof(unsigned long) == 4 &&
        sizeof(struct structure_runtime_decal) == 16 &&
        offsetof(struct structure_runtime_decal, palette_index) == 12 &&
        offsetof(struct structure_runtime_decal, yaw) == 14 &&
        offsetof(struct structure_runtime_decal, pitch) == 15 &&
        sizeof(struct structure_cluster_runtime_decals) == 0x68 &&
        offsetof(struct structure_cluster_runtime_decals, first_decal_index) == 0x0C &&
        sizeof(struct tag_reference) == 16 && offsetof(struct tag_reference, index) == 12 &&
        offsetof(struct tag_block_definition, element_size) == 12 &&
        ((char)-1) < 0;
}}
static int pvs_ok(void) {{
    unsigned long bits[2];
    memset(bits, 0, sizeof bits);
    BIT_VECTOR_SET_FLAG(bits, 31, TRUE);
    BIT_VECTOR_SET_FLAG(bits, 32, TRUE);
    return BIT_VECTOR_TEST_FLAG(bits, 31) && BIT_VECTOR_TEST_FLAG(bits, 32) &&
        !BIT_VECTOR_TEST_FLAG(bits, 30) && !BIT_VECTOR_TEST_FLAG(bits, 33) &&
        bits[0] == 0x80000000UL && bits[1] == 1UL;
}}
int main(void) {{
    unsigned long *old_pvs;
    unsigned long *new_pvs;
    size_t words = (size_t)BIT_VECTOR_SIZE_IN_LONGS(CLUSTER_TOTAL);
    size_t pvs_bytes = words * sizeof(unsigned long);
    int left = -1;
    int i;
    int decals_same = 1, clusters_same = 1, palette_same = 1;
    void *cluster_snapshot = 0;
    void *palette_snapshot = 0;
    unsigned short endian = 1;
    if (*((unsigned char *)&endian) != 1 || !abi_ok()) {{
        printf("ABI\\t%u\\t%u\\t0\\n", (unsigned)sizeof(long), (unsigned)sizeof(void *));
        return 2;
    }}
    printf("MAP\\t%s\\n", map_name);
    printf("ABI\\t%u\\t%u\\t1\\n", (unsigned)sizeof(long), (unsigned)sizeof(void *));
    printf("PVSBITS\\t%d\\n", pvs_ok());
    printf("COUNTS\\t%d\\t%d\\t%d\\n", DECAL_TOTAL, CLUSTER_TOTAL, PALETTE_TOTAL);
#if DECAL_TOTAL
    if (sizeof raw_decal_bytes != sizeof decal_storage) return 5;
    memcpy(decal_storage, raw_decal_bytes, sizeof raw_decal_bytes);
#endif
    cluster_snapshot = malloc(sizeof clusters);
    if (!cluster_snapshot) return 6;
    memcpy(cluster_snapshot, clusters, sizeof clusters);
#if PALETTE_TOTAL
    palette_snapshot = malloc(sizeof palette);
    if (!palette_snapshot) return 6;
    memcpy(palette_snapshot, palette, sizeof palette);
#endif
    for (i = 0; i < CLUSTER_TOTAL; i++) {{
        if (clusters[i].first_decal_index != NONE && clusters[i].decal_count) {{
            left = i;
            break;
        }}
    }}
    printf("LEFT\\t%d\\n", left);
    bsp_fixture.clusters.count = CLUSTER_TOTAL;
    bsp_fixture.clusters.address = clusters;
    bsp_fixture.clusters.definition = 0;
    bsp_fixture.runtime_decals.count = DECAL_TOTAL;
#if DECAL_TOTAL
    bsp_fixture.runtime_decals.address = decal_storage;
#else
    bsp_fixture.runtime_decals.address = 0;
#endif
    bsp_fixture.runtime_decals.definition = 0;
    scenario_fixture.decal_palette.count = PALETTE_TOTAL;
#if PALETTE_TOTAL
    scenario_fixture.decal_palette.address = palette;
#else
    scenario_fixture.decal_palette.address = 0;
#endif
    scenario_fixture.decal_palette.definition = 0;
    globals_storage.reconnect_to_structure_bsp = FALSE;
    warned_about_runtime_decals = FALSE;
    old_pvs = calloc(words, sizeof(unsigned long));
    new_pvs = calloc(words, sizeof(unsigned long));
    if (!old_pvs || !new_pvs) return 7;
    for (i = 0; i < CLUSTER_TOTAL; i++) {{
        BIT_VECTOR_SET_FLAG(new_pvs, i, TRUE);
        begin_step("enter", i);
        structure_decals_update(old_pvs, new_pvs, (short)CLUSTER_TOTAL);
        end_step();
        memcpy(old_pvs, new_pvs, pvs_bytes);
    }}
    begin_step("stable_full", -1);
    structure_decals_update(old_pvs, new_pvs, (short)CLUSTER_TOTAL);
    end_step();
    begin_step("reconnect_full", -1);
    structure_decals_reconnect_to_structure_bsp();
    structure_decals_update(old_pvs, new_pvs, (short)CLUSTER_TOTAL);
    end_step();
    begin_step("stable_after_reconnect", -1);
    structure_decals_update(old_pvs, new_pvs, (short)CLUSTER_TOTAL);
    end_step();
    if (left >= 0)
        BIT_VECTOR_SET_FLAG(new_pvs, left, FALSE);
    else
        memset(new_pvs, 0, pvs_bytes);
    begin_step("leave", left);
    structure_decals_update(old_pvs, new_pvs, (short)CLUSTER_TOTAL);
    end_step();
    memcpy(old_pvs, new_pvs, pvs_bytes);
    begin_step("stable_after_leave", -1);
    structure_decals_update(old_pvs, new_pvs, (short)CLUSTER_TOTAL);
    end_step();
    begin_step("disconnect", -1);
    structure_decals_disconnect_from_structure_bsp();
    end_step();
    begin_step("reconnect_partial", -1);
    structure_decals_reconnect_to_structure_bsp();
    structure_decals_update(old_pvs, new_pvs, (short)CLUSTER_TOTAL);
    end_step();
    if (left >= 0) {{
        BIT_VECTOR_SET_FLAG(new_pvs, left, TRUE);
        begin_step("reenter", left);
        structure_decals_update(old_pvs, new_pvs, (short)CLUSTER_TOTAL);
        end_step();
    }}
#if DECAL_TOTAL
    decals_same = memcmp(decal_storage, raw_decal_bytes, sizeof raw_decal_bytes) == 0;
#endif
    clusters_same = memcmp(cluster_snapshot, clusters, sizeof clusters) == 0;
#if PALETTE_TOTAL
    palette_same = palette_snapshot && memcmp(palette_snapshot, palette, sizeof palette) == 0;
#endif
    printf("FIXTURE\\t%d\\t%d\\t%d\\n", decals_same, clusters_same, palette_same);
    printf("FAST\\t%d\\n", fast_fallback);
    printf("FLAG\\t%d\\n", globals_storage.reconnect_to_structure_bsp ? 1 : 0);
    printf("WARNED\\t%d\\n", warned_about_runtime_decals ? 1 : 0);
    printf("STATUS\\t%d\\n", (decals_same && clusters_same && palette_same && pvs_ok()) ? 0 : 1);
    free(cluster_snapshot);
    free(palette_snapshot);
    free(old_pvs);
    free(new_pvs);
    return 0;
}}
"""


def compile_and_run(fix, source_text):
    out_src = OUT / "src" / f"{fix['name']}.c"
    out_bin = OUT / "bin" / fix["name"]
    out_log = OUT / "logs" / f"{fix['name']}.log"
    out_src.parent.mkdir(parents=True, exist_ok=True)
    out_bin.parent.mkdir(parents=True, exist_ok=True)
    out_log.parent.mkdir(parents=True, exist_ok=True)
    out_src.write_text(source_text)
    compiler = os.environ.get("CC", shutil.which("gcc") or "gcc")
    command = [compiler, *host_abi32_flags(), "-std=gnu99", "-O0", "-fsigned-char",
               "-msse2", "-mfpmath=sse", str(out_src), "-lm", "-o", str(out_bin)]
    compiled = subprocess.run(command, capture_output=True, text=True)
    if compiled.returncode != 0:
        raise AssertionError(f"compile failed\n{compiled.stderr}")
    ran = subprocess.run([str(out_bin)], capture_output=True, text=True)
    out_log.write_text(ran.stdout)
    if compiled.stderr.strip():
        (OUT / "logs" / f"{fix['name']}.compile.stderr").write_text(compiled.stderr)
    if ran.returncode != 0:
        raise AssertionError(
            f"fixture exit {ran.returncode}\n{ran.stdout}\n{ran.stderr}")
    return out_src, out_bin, out_log, ran.stdout, compiled.stderr


def parse_log(text):
    header = {}
    steps = []
    pending_creates = []
    pending_deletes = []
    for line_number, line in enumerate(text.splitlines(), start=1):
        parts = line.split("\t")
        kind = parts[0]
        if kind == "CREATE":
            if len(parts) != 17:
                raise AssertionError(f"line {line_number}: CREATE fields {len(parts)}")
            pending_creates.append({
                "phase": parts[1], "spy_cluster": int(parts[2]), "decal_index": int(parts[3]),
                "palette": int(parts[4]), "tag_index": int(parts[5]), "path": parts[6],
                "x": int(parts[7], 16), "y": int(parts[8], 16), "z": int(parts[9], 16),
                "i": int(parts[10], 16), "j": int(parts[11], 16), "k": int(parts[12], 16),
                "scale": int(parts[13], 16), "permanent": int(parts[14]),
                "sequence": int(parts[15]), "editor": int(parts[16]),
            })
        elif kind == "DELETE":
            pending_deletes.append(int(parts[2]))
        elif kind == "STEP":
            step = {
                "phase": parts[1], "cluster": int(parts[2]),
                "ncreate": int(parts[3]), "ndelete": int(parts[4]),
                "ndef": int(parts[5]), "nmal": int(parts[6]),
                "creates": pending_creates, "deletes": pending_deletes,
            }
            if step["ncreate"] != len(pending_creates) or step["ndelete"] != len(pending_deletes):
                raise AssertionError(f"{step['phase']} summary does not match request lines")
            steps.append(step)
            pending_creates = []
            pending_deletes = []
        elif kind in {"MAP", "ABI", "PVSBITS", "COUNTS", "LEFT", "FIXTURE", "FAST", "FLAG", "WARNED", "STATUS"}:
            header[kind] = parts[1:]
        else:
            raise AssertionError(f"unexpected fixture line {line}")
    if pending_creates or pending_deletes:
        raise AssertionError("requests were not attached to a step")
    return header, steps


def payload(record):
    keys = ("decal_index", "palette", "tag_index", "path", "x", "y", "z",
            "i", "j", "k", "scale", "permanent", "sequence", "editor")
    return tuple(record[key] for key in keys)


def same_request(observed, expected, cluster_key):
    if observed[cluster_key] != expected["cluster"]:
        return False
    return payload(observed) == payload(expected)


def check_map(fix, stdout):
    issues = []
    header, steps = parse_log(stdout)
    expected = oracle_requests(fix)
    by_cluster = {}
    for request in expected:
        by_cluster.setdefault(request["cluster"], []).append(request)
    populated = [index for index, (first, count) in enumerate(fix["clusters"])
                 if first != -1 and count]
    left = populated[0] if populated else -1
    if header.get("MAP") != [fix["name"]]:
        issues.append(f"MAP header {header.get('MAP')}")
    if header.get("ABI") != ["4", "4", "1"]:
        issues.append(f"ABI {header.get('ABI')} (need ILP32)")
    if header.get("PVSBITS") != ["1"]:
        issues.append(f"PVS bit 31/32 self-test {header.get('PVSBITS')}")
    if header.get("COUNTS") != [str(len(fix["decals"])), str(len(fix["clusters"])), str(len(fix["palette"]))]:
        issues.append(f"COUNTS {header.get('COUNTS')}")
    if header.get("LEFT") != [str(left)]:
        issues.append(f"LEFT {header.get('LEFT')} expected {left}")
    if header.get("FIXTURE") != ["1", "1", "1"]:
        issues.append(f"fixture bytes changed {header.get('FIXTURE')}")
    if header.get("FAST") != ["0"]:
        issues.append(f"tag block fast-path fallback {header.get('FAST')}")
    if header.get("FLAG") != ["0"] or header.get("WARNED") != ["0"] or header.get("STATUS") != ["0"]:
        issues.append(f"FLAG/WARNED/STATUS {header.get('FLAG')} {header.get('WARNED')} {header.get('STATUS')}")
    phases = [step["phase"] for step in steps]
    expected_phases = (["enter"] * len(fix["clusters"]) +
                       ["stable_full", "reconnect_full", "stable_after_reconnect",
                        "leave", "stable_after_leave", "disconnect", "reconnect_partial"])
    if left >= 0:
        expected_phases.append("reenter")
    if phases != expected_phases:
        issues.append(f"phase sequence {phases}")
    enter_steps = [step for step in steps if step["phase"] == "enter"]
    observed_enter = []
    for cluster_index, step in enumerate(enter_steps):
        wanted = by_cluster.get(cluster_index, [])
        if step["cluster"] != cluster_index or step["ndelete"] or step["nmal"] or step["ndef"] != step["ncreate"]:
            issues.append(f"enter cluster {cluster_index} metadata {step['cluster']} "
                          f"deletes={step['ndelete']} def={step['ndef']} mal={step['nmal']}")
        if len(step["creates"]) != len(wanted):
            issues.append(f"enter cluster {cluster_index}: {len(step['creates'])} creates, expected {len(wanted)}")
        for observed, request in zip(step["creates"], wanted):
            if not same_request(observed, request, "spy_cluster"):
                issues.append(f"enter mismatch cluster {cluster_index} observed={observed} expected={request}")
                break
        else:
            observed_enter.extend(step["creates"])
    if len(observed_enter) != len(expected):
        issues.append(f"enter total {len(observed_enter)} != oracle {len(expected)}")

    def step_named(phase):
        matches = [step for step in steps if step["phase"] == phase]
        if len(matches) != 1:
            issues.append(f"missing step {phase}")
            return None
        return matches[0]

    def require_quiet(phase):
        step = step_named(phase)
        if step is not None and (step["creates"] or step["deletes"] or step["nmal"]):
            issues.append(f"{phase} was not quiet: creates={step['ncreate']} deletes={step['deletes']}")

    require_quiet("stable_full")
    require_quiet("stable_after_reconnect")
    require_quiet("stable_after_leave")
    full = step_named("reconnect_full")
    if full is None:
        full = {"ndelete": -1, "nmal": -1, "ndef": -1, "ncreate": -1, "cluster": None, "creates": []}
    if full["ndelete"] or full["nmal"] or full["ndef"] != full["ncreate"] or full["cluster"] != -1:
        issues.append(f"reconnect_full metadata off {full['ndelete']} {full['ndef']} {full['nmal']}")
    if [payload(item) for item in full["creates"]] != [payload(item) for item in observed_enter]:
        issues.append("reconnect_full did not recreate the enter request list")
    if any(item["spy_cluster"] != -1 for item in full["creates"]):
        issues.append("reconnect_full labeled a single cluster inside one update")
    leave = step_named("leave") or {"creates": ["missing"], "nmal": 1, "ndef": 1, "deletes": [], "cluster": None}
    if leave["creates"] or leave["nmal"] or leave["ndef"]:
        issues.append(f"leave created or warned: {leave['creates']}")
    if left < 0:
        if leave["deletes"]:
            issues.append(f"empty map leave deleted {leave['deletes']}")
    elif leave["deletes"] != [left] or leave["cluster"] != left:
        issues.append(f"leave deleted {leave['deletes']} expected [{left}]")
    disconnect = step_named("disconnect") or {"creates": ["missing"], "nmal": 1, "deletes": []}
    if disconnect["creates"] or disconnect["nmal"] or disconnect["deletes"] != populated:
        issues.append(f"disconnect deleted {disconnect['deletes']} expected {populated}")
    partial_expected = [request for request in expected if request["cluster"] != left]
    partial = step_named("reconnect_partial") or {
        "ndelete": -1, "nmal": -1, "ndef": -1, "ncreate": -1, "creates": []}
    if partial["ndelete"] or partial["nmal"] or partial["ndef"] != partial["ncreate"]:
        issues.append("reconnect_partial metadata off")
    if [payload(item) for item in partial["creates"]] != [payload(item) for item in partial_expected]:
        issues.append("reconnect_partial did not recreate only the still-visible clusters")
    if left >= 0:
        reenter = step_named("reenter") or {
            "deletes": ["missing"], "nmal": 1, "ndef": 1, "ncreate": 1, "creates": []}
        wanted = by_cluster.get(left, [])
        if reenter["deletes"] or reenter["nmal"] or reenter["ndef"] != reenter["ncreate"]:
            issues.append("reenter metadata off")
        if len(reenter["creates"]) != len(wanted) or any(
                not same_request(observed, request, "spy_cluster")
                for observed, request in zip(reenter["creates"], wanted)):
            issues.append(f"reenter mismatch {[payload(item) for item in reenter['creates']]}")
    ranges = [(index, first, count) for index, (first, count) in enumerate(fix["clusters"]) if count]
    return {
        "name": fix["name"],
        "issues": issues,
        "clusters": len(fix["clusters"]),
        "decals": len(fix["decals"]),
        "ranges": len(ranges),
        "range_text": ",".join(f"{index}:{first}+{count}" for index, first, count in ranges) or "-",
        "palette": len(fix["palette"]),
        "decal_address": fix["decal_address"],
        "unused_nonzero": fix["unused_nonzero"],
        "bsp_path": fix["bsp_path"],
        "bsp_bytes": fix["bsp_bytes"],
        "bsp_sha256": fix["bsp_sha256"],
        "map_sha256": fix["map_sha256"],
        "enter": len(expected),
        "leave_cluster": left,
        "leave_deletes": 0 if left < 0 else 1,
        "disconnect_deletes": len(populated),
        "reconnect_full": len(expected),
        "reconnect_partial": len(partial_expected),
        "requests": expected,
        "empty": len(fix["decals"]) == 0,
    }


def write_requests(result):
    path = OUT / "requests" / f"{result['name']}.tsv"
    path.parent.mkdir(parents=True, exist_ok=True)
    if result["empty"]:
        path.write_text(
            "EMPTY\truntime_decals=0\taddress=0x0\tclusters=%d\tranges=0\tpalette=%d\t"
            "empty_cluster_sentinel=NONE\tce_creates=0\tce_deletes=0\n" % (
                result["clusters"], result["palette"]))
        return
    lines = ["phase\tcluster\tdecal_index\tpalette\ttag_index\tdatum\tpath\tx\ty\tz\ti\tj\tk\tyaw\tpitch"]
    for request in result["requests"]:
        lines.append("\t".join([
            "enter", str(request["cluster"]), str(request["decal_index"]), str(request["palette"]),
            str(request["tag_index"]), f"0x{request['datum']:08x}", request["path"],
            f"{request['x']:08x}", f"{request['y']:08x}", f"{request['z']:08x}",
            f"{request['i']:08x}", f"{request['j']:08x}", f"{request['k']:08x}",
            str(request["yaw"]), str(request["pitch"]),
        ]))
    path.write_text("\n".join(lines) + "\n")


def write_report(results, problems):
    OUT.mkdir(parents=True, exist_ok=True)
    source = ROOT / "tests/test_hcu_mp_decals_all13.py"
    logs = sorted((OUT / "logs").glob("*.log")) if (OUT / "logs").exists() else []
    bins = sorted(path for path in (OUT / "bin").iterdir()) if (OUT / "bin").exists() else []
    generated = sorted((OUT / "src").glob("*.c")) if (OUT / "src").exists() else []
    status = "PASS" if len(results) == len(MP_MAPS) and not any(result["issues"] for result in results) and not problems else "ISSUES"
    rows = ["| map | clusters | runtime decals | ranges | palette | enter/reconnect | leave | disconnect | partial reconnect | result |",
            "|---|---:|---:|---:|---:|---:|---|---:|---:|---|"]
    for result in results:
        kind = "EMPTY raw count 0 address 0" if result["empty"] else "requests match raw oracle"
        if result["issues"]:
            kind = "FAIL " + "; ".join(result["issues"][:2])
        leave = "-" if result["leave_cluster"] < 0 else f"cluster {result['leave_cluster']} x{result['leave_deletes']}"
        rows.append(
            f"| {result['name']} | {result['clusters']} | {result['decals']} | {result['ranges']} | "
            f"{result['palette']} | {result['enter']} | {leave} | {result['disconnect_deletes']} | "
            f"{result['reconnect_partial']} | {kind} |")
    hashes = [f"- tests/test_hcu_mp_decals_all13.py {sha256_file(source)}"]
    for path in generated:
        hashes.append(f"- {path.relative_to(ROOT)} {sha256_file(path)}")
    for path in bins:
        hashes.append(f"- {path.relative_to(ROOT)} {sha256_file(path)}")
    for path in logs:
        hashes.append(f"- {path.relative_to(ROOT)} {sha256_file(path)}")
    empty = [result["name"] for result in results if result["empty"]]
    nonempty = [f"{result['name']} ({result['decals']})" for result in results if not result["empty"]]
    issue_lines = [f"- {result['name']}: {issue}" for result in results for issue in result["issues"]]
    issue_lines.extend(f"- {problem}" for problem in problems)
    text = f"""# Step 7 decals: all 13 multiplayer maps

Status: {status}

CE `structure_decals_update`, `structure_decals_disconnect_from_structure_bsp` and `structure_decals_reconnect_to_structure_bsp` were extracted from `source/structures/structure_runtime_decals.c` and executed. `vector3d_from_euler_angles2d` and the `sine`/`cosine` inlines were extracted with them. `decal_new` is a recording spy. No GS, rasterizer, or `rasterizer_xbox_decals.c` backend is compiled.

Raw oracle: decompressed Xbox BSP `runtime_decals` at structure_bsp+0x258, cluster decal range at cluster+0x0C, scenario `decal_palette` at scenario+0x3B4. Palette datums resolve through that map's tag index. Normals use the CE yaw/pitch scale (`pi/127`, `pi/254`) and float-rounded libm sine/cosine. Positions are the raw float bits passed through `decal_new`.

Lifecycle per map: cumulative PVS enter, stable, reconnect while every cluster stays visible, stable, leave the first populated cluster, stable, disconnect, reconnect of the clusters that stayed visible, then re-enter the cluster that left. Fixture decal bytes and cluster records are compared after the calls.

Empty maps ({len(empty)}): {', '.join(empty) if empty else 'none'}. Each has raw `runtime_decals` count 0 and address 0, every cluster range `first=NONE` and `count=0`, and every CE enter/leave/stable/disconnect/reconnect step created 0 and deleted 0.

Non-empty maps: {', '.join(nonempty) if nonempty else 'none'}. Cluster ranges partition `0 .. count-1` with no overlap. Every runtime decal's palette index names a `deca` tag.

{chr(10).join(rows)}

Reproduction:

```
python3 tests/test_hcu_mp_decals_all13.py -v
```

Host compile: `host_abi32` `-m32` sysroot, `-std=gnu99 -O0 -fsigned-char -msse2 -mfpmath=sse -lm`.

## SHA-256

{chr(10).join(hashes)}

## Issues

{chr(10).join(issue_lines) if issue_lines else '- none'}

## Limits

- The spy stops at `decal_new`. No decal mesh, GS upload, or draw was run.
- HP2 packages were not opened. Published BSP bytes and `global_current_collision_user_depth` were not touched.
- Normals are exact for this SSE ILP32 libm compile of the CE formula. This is not an Xbox x87 capture and not PCSX2/GS/VU/SPU2 output.
- `decal_definition_get` is the call in the extracted source; the real `tag_get` macro is not linked.
"""
    (OUT / "report.md").write_text(text)
    return status


class MultiplayerRuntimeDecalsAll13Test(unittest.TestCase):
    def test_all_thirteen_maps(self):
        ce = load_ce_text()
        results = []
        problems = []
        try:
            for name in MP_MAPS:
                with self.subTest(map=name):
                    try:
                        fix = read_map(name)
                        if hashlib.sha256((MAP_DIR / f"{name}.map").read_bytes()).hexdigest() != fix["map_sha256"]:
                            raise AssertionError("map bytes changed while reading")
                        _src, _bin, _log, stdout, _stderr = compile_and_run(fix, render_c(fix, ce))
                        result = check_map(fix, stdout)
                        write_requests(result)
                    except Exception:
                        problem = f"{name}: {traceback.format_exc()}"
                        problems.append(problem)
                        result = {"name": name, "issues": [problem], "empty": False, "clusters": -1,
                                  "decals": -1, "ranges": -1, "palette": -1, "enter": -1,
                                  "leave_cluster": -1, "leave_deletes": -1, "disconnect_deletes": -1,
                                  "reconnect_partial": -1}
                    results.append(result)
                    self.assertEqual(result["issues"], [], "\n".join(result["issues"]))
        finally:
            write_report(results, problems)


if __name__ == "__main__":
    unittest.main(verbosity=2)
