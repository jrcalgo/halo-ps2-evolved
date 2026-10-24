"""Run CE's cluster lens-flare selector over source-derived retail BSP records."""
from pathlib import Path
import hashlib
import struct
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
LIGHTS = ROOT / "submodules/halo-ce-universal/source/rasterizer/rasterizer_lights.c"
MAPS = {
    "boardingaction": "34ddf961973b6aaf05f40f26bd9ad536ca97f8af503995611535ccf6ce911522",
    "damnation": "87bd92c1821ff20bed03c559d7be5ac43baeb44aa68342ffdbb5a8cd978f711c",
    "putput": "efbe723188f34053d318105f20c7046f263171fbb937fbad45e3d00f8437f243",
}
sys.path.insert(0, str(ROOT / "submodules/halo-ps2/tools"))
from halo2ps2 import bsp, mapinfo, tagindex
from tools.ctag_schema_walk import read_xbox_tag_region


def extract_function(source, marker):
    start = source.index(marker)
    opening = source.index("{", start)
    depth = 0
    for i in range(opening, len(source)):
        if source[i] == "{": depth += 1
        elif source[i] == "}":
            depth -= 1
            if depth == 0: return source[start:i + 1]
    raise AssertionError(f"unterminated CE function: {marker}")


def read_raw(name):
    path = ROOT / "build/retail-maps/decompressed" / f"{name}.map"
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if digest != MAPS[name]: raise AssertionError(f"{name} source changed: {digest}")
    region, _, _ = read_xbox_tag_region(path)
    locs = bsp.locate(tagindex.TagIndex.read(path), region,
                      mapinfo.read_header(path).decompressed_size)
    if len(locs) != 1: raise AssertionError(f"{name}: expected one BSP")
    loc = locs[0]
    with path.open("rb") as f:
        f.seek(loc.file_offset); image = f.read(loc.size)
    root = struct.unpack_from("<I", image)[0] - loc.address
    if root < 0 or root + 648 > len(image): raise AssertionError("invalid BSP root")

    def block(offset, stride, label):
        count, address = struct.unpack_from("<iI", image, root + offset)
        data = address - loc.address if address else 0
        if count < 0 or data < 0 or data + count * stride > len(image):
            raise AssertionError(f"{name}: invalid {label} extent")
        return [image[data + i * stride:data + (i + 1) * stride]
                for i in range(count)]

    flares = block(284, 16, "lens flare palette")
    markers = block(296, 16, "lens flare markers")
    clusters = block(308, 104, "clusters")
    return digest, flares, markers, clusters


def fixture_c(ce_function, flares, markers, clusters):
    def byte_array(name, rows):
        flat = b"".join(rows)
        return f"static unsigned char {name}[] = {{{','.join(str(x) for x in flat)}}};\n"
    code = r'''#include <assert.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
typedef unsigned char byte; typedef unsigned short word; typedef int boolean;
typedef float real; typedef struct { real x,y,z; } real_point3d;
typedef struct { real i,j,k; } real_vector3d;
typedef struct { void *address; int count; } tag_block;
typedef struct { int group_tag,name,index; } tag_reference;
struct structure_bsp { byte reserved[0x11c]; tag_block lens_flares,lens_flare_markers,clusters; };
struct structure_cluster { byte reserved[0x40]; word first_lens_flare_marker_index,lens_flare_marker_count; byte tail[0x24]; };
struct structure_lens_flare { tag_reference lens_flare; };
struct structure_lens_flare_marker { real_point3d position; char i_direction,j_direction,k_direction; byte lens_flare_index; };
struct lens_flare_definition { int unused; };
struct rasterizer_lens_flare_submit_parameters { struct lens_flare_definition *definition; real_point3d position; unsigned long compressed_direction,compressed_up,compressed_light_color; short light_identifier,light_index,lens_flare_index; byte compressed_window_index,compressed_light_scale; long internal__occlusion_pixels; };
typedef char cluster_size_check[sizeof(struct structure_cluster)==0x68?1:-1];
typedef char marker_size_check[sizeof(struct structure_lens_flare_marker)==0x10?1:-1];
#define TRUE 1
#define FALSE 0
#define NONE (-1)
#define SHORT_MAX 32767
#define MAXIMUM_QUEUED_LENS_FLARES 128
#define MIN(a,b) ((a)<(b)?(a):(b))
#define TAG_BLOCK_GET_ELEMENT(b,i,t) ((t*)((byte*)(b)->address+(i)*sizeof(t)))
static int enabled=1, screenshot=0, submitted[4096], submit_count, errors;
static struct structure_bsp bsp;
static struct structure_bsp *global_structure_bsp_get(void) { return &bsp; }
static int rasterizer_debug_options_draw_lens_flares(void) { return enabled; }
static int screenshot_in_progress(void) { return screenshot; }
static struct lens_flare_definition *lens_flare_definition_get(int i) { static struct lens_flare_definition d[256]; return i>=0&&i<256?&d[i]:NULL; }
static void lens_flare_data_error(char const *s) { (void)s; errors++; }
static void set_real_vector3d(real_vector3d *v, real i, real j, real k) { v->i=i;v->j=j;v->k=k; }
static void perpendicular3d(real_vector3d const *v, real_vector3d *u) { (void)v;u->i=1;u->j=0;u->k=0; }
static void normalize3d(real_vector3d *v) { (void)v; }
static unsigned long compress_real_vector3d_to_int32_clamp(real_vector3d const *v) { (void)v; return 0; }
static struct { int window_index; } render;
static void rasterizer_lens_flare_submit(struct rasterizer_lens_flare_submit_parameters *p) { submitted[submit_count++]=p->lens_flare_index; }
''' + byte_array("flare_bytes", flares) + byte_array("marker_bytes", markers) + byte_array("cluster_bytes", clusters) + r'''
static struct structure_lens_flare flare_records[256];
static void initialize(void) {
  int i; bsp.lens_flares.address=flare_records; bsp.lens_flares.count=HCU_FLARE_COUNT;
  bsp.lens_flare_markers.address=marker_bytes; bsp.lens_flare_markers.count=HCU_MARKER_COUNT;
  bsp.clusters.address=cluster_bytes; bsp.clusters.count=HCU_CLUSTER_COUNT;
  for(i=0;i<HCU_FLARE_COUNT;i++) flare_records[i].lens_flare.index=i;
}
''' + ce_function + r'''
int main(void) {
 int c, i; initialize();
 for(c=0;c<bsp.clusters.count;c++) {
   struct structure_cluster *cl=TAG_BLOCK_GET_ELEMENT(&bsp.clusters,c,struct structure_cluster);
   int before=submit_count; rasterizer_lens_flare_submit_for_cluster((short)c);
   for(i=0;i<cl->lens_flare_marker_count && cl->first_lens_flare_marker_index+i<bsp.lens_flare_markers.count;i++) {
     int ix=cl->first_lens_flare_marker_index+i;
     struct structure_lens_flare_marker *m=TAG_BLOCK_GET_ELEMENT(&bsp.lens_flare_markers,ix,struct structure_lens_flare_marker);
     if(m->lens_flare_index < bsp.lens_flares.count) { if(submitted[before++]!=ix) return 4; }
   }
   if(before!=submit_count) return 5;
 }
 printf("markers=%d clusters=%d submissions=%d badref_errors=%d indices=",HCU_MARKER_COUNT,HCU_CLUSTER_COUNT,submit_count,errors);
 for(i=0;i<submit_count;i++) printf("%s%d",i?",":"",submitted[i]);
 printf("\n");
 return 0;
}
'''
    return (code.replace("HCU_FLARE_COUNT", str(len(flares)))
            .replace("HCU_MARKER_COUNT", str(len(markers)))
            .replace("HCU_CLUSTER_COUNT", str(len(clusters))))


class LensFlareConsumerTest(unittest.TestCase):
    def test_ce_cluster_marker_iteration_matches_raw_bsp(self):
        ce = extract_function(LIGHTS.read_text(), "void rasterizer_lens_flare_submit_for_cluster(")
        ce = ce.replace("rasterizer_debug_options.draw_lens_flares", "rasterizer_debug_options_draw_lens_flares()")
        self.assertIn("structure_lens_flare_marker_index= cluster->first_lens_flare_marker_index+lens_flare_marker_index", ce)
        summaries = []
        with tempfile.TemporaryDirectory(prefix="hcu-mp-lens-flare-") as td:
            for name in MAPS:
                digest, flares, markers, clusters = read_raw(name)
                self.assertGreater(len(markers), 0, name)
                source = Path(td) / f"{name}.c"
                executable = Path(td) / name
                source.write_text(fixture_c(ce, flares, markers, clusters))
                subprocess.run(["cc", "-std=c99", "-O2", str(source), "-o", str(executable)], check=True)
                run = subprocess.run([str(executable)], check=True, capture_output=True, text=True)
                values = dict(part.split("=", 1) for part in run.stdout.strip().split())
                observed = [int(v) for v in values["indices"].split(",") if v]
                expected = []
                for cluster in clusters:
                    first, count = struct.unpack_from("<HH", cluster, 0x40)
                    for ix in range(first, first + count):
                        if ix < len(markers) and markers[ix][15] < len(flares):
                            expected.append(ix)
                self.assertEqual(observed, expected, name)
                self.assertEqual(int(values["badref_errors"]), 0, name)
                summaries.append((name, digest, len(markers), len(clusters), len(observed)))
        self.assertEqual(len(summaries), len(MAPS))


if __name__ == "__main__": unittest.main()
