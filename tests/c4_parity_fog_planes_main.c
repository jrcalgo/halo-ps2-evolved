/* C4 fog-plane vertices consumer driver.

Compiles CE render_debug_fog_planes, extracted verbatim from
submodules/halo-ce-universal/source/structures/structures.c by
tests/test_c4_parity_fog.py (placeholder marker CE_FUNCTIONS). It is the only CE
reader of structure_fog_plane.vertices (the render-side struct
structure_fog_plane_render, tag block at offset 20). Rasterizer and point helpers
are stubs that log their arguments; the Python oracle checks the logged geometry.
stdin: debug flag, cluster fog reference, maximum distance, plane count, then per
plane: vertex count and vertex coordinates. */
#include <stddef.h>
#include <string.h>
#include <stdio.h>
#include <stdlib.h>

typedef float real;
typedef int boolean;
typedef unsigned short word;
typedef unsigned char byte;
#define TRUE 1
#define FALSE 0
#define SHORT_MAX 32767
#define TAG_BLOCK_GET_ELEMENT(b,i,t) ((t*)((byte*)(b)->address+(i)*sizeof(t)))
#define _render_planar_fog_mode_normal 1
#define NONE (-1)

typedef struct { real i, j, k; } real_vector3d;
typedef struct { real x, y, z; } real_point3d;
typedef struct { real_vector3d n; real d; } real_plane3d;
typedef struct { void *address; int count; } tag_block;

struct structure_fog_plane_render
{
	short region_index;
	word pad;
	real_plane3d plane;
	tag_block vertices;
};
/* ILP32 offset of vertices is 20 (plane at 4, 16 bytes); LP64 host widens the tag block pointer, so only the plane offset is asserted here. */
typedef char structure_fog_plane_render_plane_offset_assert[offsetof(struct structure_fog_plane_render, plane) == 4 ? 1 : -1];

struct structure_cluster { short unused0; short fog_reference; };
struct structure_bsp { tag_block clusters; tag_block fog_planes; };
static struct structure_bsp bsp;
static struct structure_bsp *global_structure_bsp_get(void) { return &bsp; }

static struct { struct { short planar_mode; real planar_maximum_distance; } fog; short cluster_index; } render_state;
#define render render_state
static boolean debug_fog_planes;
static char const *global_real_argb_white = "white", *global_real_argb_black = "black";

static void point_from_line3d(real_point3d const *point, real_vector3d const *direction, real distance, real_point3d *result)
{
	result->x = point->x + direction->i * distance;
	result->y = point->y + direction->j * distance;
	result->z = point->z + direction->k * distance;
}
static void rasterizer_debug_line(real_point3d const *a, real_point3d const *b, void const *c)
{ (void)c; printf("L %.7g,%.7g,%.7g %.7g,%.7g,%.7g %s\n", a->x, a->y, a->z, b->x, b->y, b->z, (char const *)c); }
static void rasterizer_debug_line_shaded(real_point3d const *a, real_point3d const *b, void const *c0, void const *c1)
{ (void)c0; (void)c1; printf("S %.7g,%.7g,%.7g %.7g,%.7g,%.7g\n", a->x, a->y, a->z, b->x, b->y, b->z); }

/*CE_FUNCTIONS*/

static int ri(void) { int v; if (scanf("%d", &v) != 1) exit(3); return v; }
static real rd(void) { float v; if (scanf("%f", &v) != 1) exit(3); return v; }

int main(void)
{
	int i, n, count, v;
	static struct structure_cluster clusters[1];
	static struct structure_fog_plane_render planes[4];
	static real_point3d points[4][16];
	debug_fog_planes = (boolean)ri();
	clusters[0].fog_reference = (short)ri();
	render.fog.planar_maximum_distance = rd();
	render.fog.planar_mode = _render_planar_fog_mode_normal;
	render.cluster_index = 0;
	bsp.clusters.address = clusters; bsp.clusters.count = 1;
	count = ri();
	bsp.fog_planes.address = planes; bsp.fog_planes.count = count;
	for (i = 0; i < count; i++) {
		n = ri();
		planes[i].region_index = 0;
		planes[i].plane.n.i = 0; planes[i].plane.n.j = 0; planes[i].plane.n.k = 1; planes[i].plane.d = 0;
		planes[i].vertices.address = points[i]; planes[i].vertices.count = n;
		for (v = 0; v < n; v++) { points[i][v].x = rd(); points[i][v].y = rd(); points[i][v].z = rd(); }
	}
	render_debug_fog_planes();
	printf("done\n");
	return 0;
}
