/* C4 lens-flare member-exact consumer driver.

Compiles CE rasterizer_lens_flare_submit_for_cluster, extracted verbatim from
submodules/halo-ce-universal/source/rasterizer/rasterizer_lights.c by
tests/test_c4_parity_fog.py (placeholder marker CE_FUNCTIONS), over a synthetic
BSP whose lens_flares, lens_flare_markers, clusters and marker lens_flare_index
members are read from stdin. Output lines are compared by the Python test with
an independent oracle. */
#include <assert.h>
#include <stddef.h>
#include <stdio.h>
#include <stdlib.h>

typedef unsigned char byte;
typedef int boolean;
typedef float real;
typedef struct { real i, j, k; } real_vector3d;
typedef struct { real x, y, z; } real_point3d;
typedef struct { void *address; int count; } tag_block;
/* ILP32 layout of CE struct tag_reference (16 bytes): group_tag, name, name_length, index. */
typedef struct { unsigned int group_tag; unsigned int name; int name_length; int index; } tag_reference;
typedef unsigned short word;

#define NONE (-1)
#define SHORT_MAX 32767
#define MAXIMUM_QUEUED_LENS_FLARES 128
#define MIN(a,b) ((a)<(b)?(a):(b))
#define TAG_BLOCK_GET_ELEMENT(b,i,t) ((t*)((byte*)(b)->address+(i)*sizeof(t)))

struct structure_cluster
{
	byte reserved[0x40];
	word first_lens_flare_marker_index;
	word lens_flare_marker_count;
	byte tail[0x24];
};
typedef char structure_cluster_size_assert[sizeof(struct structure_cluster) == 0x68 ? 1 : -1];
typedef char cluster_marker_first_offset_assert[offsetof(struct structure_cluster, first_lens_flare_marker_index) == 0x40 ? 1 : -1];

struct structure_lens_flare_marker
{
	real_point3d position;
	char i_direction, j_direction, k_direction;
	byte lens_flare_index;
};
typedef char structure_lens_flare_marker_size_assert[sizeof(struct structure_lens_flare_marker) == 0x10 ? 1 : -1];

struct structure_lens_flare { tag_reference lens_flare; };

struct lens_flare_definition { int unused; };

struct rasterizer_lens_flare_submit_parameters
{
	struct lens_flare_definition *definition;
	real_point3d position;
	unsigned long compressed_direction, compressed_up, compressed_light_color;
	short light_identifier, light_index, lens_flare_index;
	byte compressed_window_index, compressed_light_scale;
	long internal__occlusion_pixels;
};

struct structure_bsp
{
	tag_block lens_flares;
	tag_block lens_flare_markers;
	tag_block clusters;
};

static struct structure_bsp bsp;
static struct structure_bsp *global_structure_bsp_get(void) { return &bsp; }
static struct { int draw_lens_flares; } rasterizer_debug_options = { 1 };
static int screenshot_in_progress(void) { return 0; }
static struct lens_flare_definition lens_flare_defs[256];
static struct lens_flare_definition *lens_flare_definition_get(long index)
{
	return (index >= 0 && index < 256) ? &lens_flare_defs[index] : NULL;
}
static int current_cluster;
static void lens_flare_data_error(char const *s) { printf("e %d %s\n", current_cluster, s); }
static void set_real_vector3d(real_vector3d *v, real i, real j, real k) { v->i = i; v->j = j; v->k = k; }
static void perpendicular3d(real_vector3d const *v, real_vector3d *u) { (void)v; u->i = 1; u->j = 0; u->k = 0; }
static void normalize3d(real_vector3d *v) { (void)v; }
static unsigned long compress_real_vector3d_to_int32_clamp(real_vector3d const *v) { (void)v; return 0; }
static struct { int window_index; } render = { 0 };
static struct structure_lens_flare flare_store[256];
static struct structure_lens_flare_marker marker_store[33000];
static struct structure_cluster cluster_store[64];

static void rasterizer_lens_flare_submit(struct rasterizer_lens_flare_submit_parameters *p)
{
	long def = p->definition ? (long)(p->definition - lens_flare_defs) : -1;
	printf("s %d %d %ld %d\n", current_cluster, (int)p->lens_flare_index, def, (int)p->light_index);
}

/*CE_FUNCTIONS*/

static int read_int(void) { int v; if (scanf("%d", &v) != 1) exit(3); return v; }

int main(void)
{
	int i, n, c, nc;
	n = read_int();
	bsp.lens_flares.address = flare_store; bsp.lens_flares.count = n;
	for (i = 0; i < n; i++) flare_store[i].lens_flare.index = read_int();

	n = read_int();
	bsp.lens_flare_markers.address = marker_store; bsp.lens_flare_markers.count = n;
	for (i = 0; i < n; i++) marker_store[i].lens_flare_index = (byte)read_int();

	nc = read_int();
	bsp.clusters.address = cluster_store; bsp.clusters.count = nc;
	for (c = 0; c < nc; c++) {
		cluster_store[c].first_lens_flare_marker_index = (word)read_int();
		cluster_store[c].lens_flare_marker_count = (word)read_int();
	}

	for (c = 0; c < nc; c++) {
		current_cluster = c;
		rasterizer_lens_flare_submit_for_cluster((short)c);
		printf("c %d done\n", c);
	}
	return 0;
}
