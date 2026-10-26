/* C4 ranges-a member-exact driver for structure_lens_flare_marker.<unclassified@0x0>.

Compiles CE rasterizer_lens_flare_submit_for_cluster, extracted verbatim from
submodules/halo-ce-universal/source/rasterizer/rasterizer_lights.c by
tests/test_c4_parity_ranges_a.py (placeholder marker CE_FUNCTIONS). The marker's
position (0x0..0xb) and its i/j/k direction bytes (0xc..0xe) are the consumed members;
the stand-ins below record the submitted position and the direction and up vectors that
the consumer derives from them. perpendicular3d and normalize3d are plain stand-ins for
CE's math (the test checks the returned vectors against an independent oracle, so a
wrong stand-in is detected, not assumed correct). compress_real_vector3d_to_int32_clamp
records its input so the test reads the vectors, not packed values.

stdin: n_flares, tags; n_markers, per marker 'lens_flare_index i j k x y z';
n_clusters, per cluster 'first count'.
stdout: 'v <cluster> <px> <py> <pz> <di> <dj> <dk> <ui> <uj> <uk>' per submit.
*/
#include <assert.h>
#include <math.h>
#include <stddef.h>
#include <stdio.h>
#include <stdlib.h>

typedef unsigned char byte;
typedef int boolean;
typedef float real;
typedef struct { real i, j, k; } real_vector3d;
typedef struct { real x, y, z; } real_point3d;
typedef struct { void *address; int count; } tag_block;
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

struct structure_lens_flare_marker
{
	real_point3d position;
	char i_direction, j_direction, k_direction;
	byte lens_flare_index;
};
typedef char structure_lens_flare_marker_size_assert[sizeof(struct structure_lens_flare_marker) == 0x10 ? 1 : -1];
typedef char marker_k_offset_assert[offsetof(struct structure_lens_flare_marker, k_direction) == 0xe ? 1 : -1];

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
static void lens_flare_data_error(char const *s) { (void)s; }
static void set_real_vector3d(real_vector3d *v, real i, real j, real k) { v->i = i; v->j = j; v->k = k; }
static void perpendicular3d(real_vector3d const *v, real_vector3d *u)
{
	/* stand-in: cross the vector with the axis it is least aligned with */
	real ax = fabsf(v->i), ay = fabsf(v->j), az = fabsf(v->k);
	real_vector3d axis = {0, 0, 0};
	if (ax <= ay && ax <= az) axis.i = 1; else if (ay <= az) axis.j = 1; else axis.k = 1;
	u->i = v->j * axis.k - v->k * axis.j;
	u->j = v->k * axis.i - v->i * axis.k;
	u->k = v->i * axis.j - v->j * axis.i;
}
static void normalize3d(real_vector3d *v)
{
	real l = sqrtf(v->i * v->i + v->j * v->j + v->k * v->k);
	if (l > 0) { v->i /= l; v->j /= l; v->k /= l; }
}
static real_vector3d last_direction, last_up;
static unsigned long compress_real_vector3d_to_int32_clamp(real_vector3d const *v)
{
	/* records the vectors in call order: direction, then up */
	static int calls;
	if (calls++ % 2 == 0) last_direction = *v; else last_up = *v;
	return 0;
}
static struct { int window_index; } render = { 0 };
static struct structure_lens_flare flare_store[256];
static struct structure_lens_flare_marker marker_store[33000];
static struct structure_cluster cluster_store[64];

static void rasterizer_lens_flare_submit(struct rasterizer_lens_flare_submit_parameters *p)
{
	printf("v %d %.9g %.9g %.9g %.9g %.9g %.9g %.9g %.9g %.9g\n",
		current_cluster,
		p->position.x, p->position.y, p->position.z,
		last_direction.i, last_direction.j, last_direction.k,
		last_up.i, last_up.j, last_up.k);
}

/*CE_FUNCTIONS*/

static int read_int(void) { int v; if (scanf("%d", &v) != 1) exit(3); return v; }
static float read_float(void) { float v; if (scanf("%f", &v) != 1) exit(3); return v; }

int main(void)
{
	int i, n, c, nc;
	n = read_int();
	bsp.lens_flares.address = flare_store; bsp.lens_flares.count = n;
	for (i = 0; i < n; i++) flare_store[i].lens_flare.index = read_int();

	n = read_int();
	bsp.lens_flare_markers.address = marker_store; bsp.lens_flare_markers.count = n;
	for (i = 0; i < n; i++) {
		struct structure_lens_flare_marker *m = &marker_store[i];
		m->lens_flare_index = (byte)read_int();
		m->i_direction = (char)read_int();
		m->j_direction = (char)read_int();
		m->k_direction = (char)read_int();
		m->position.x = read_float();
		m->position.y = read_float();
		m->position.z = read_float();
	}

	nc = read_int();
	bsp.clusters.address = cluster_store; bsp.clusters.count = nc;
	for (c = 0; c < nc; c++) {
		cluster_store[c].first_lens_flare_marker_index = (word)read_int();
		cluster_store[c].lens_flare_marker_count = (word)read_int();
	}

	for (c = 0; c < nc; c++) {
		current_cluster = c;
		rasterizer_lens_flare_submit_for_cluster((short)c);
	}
	return 0;
}
