/* C4 ranges-b leaf-map probe (leaf_map_leaf_spans_polygon, map_leaf_face and real_point2d readers).
 * Derived from the struct probe header; see tests/c4_parity_ranges_b_struct_main.c. C4 ranges-b member-exact probes: structure_cluster_portal, structure_surface, structure_surface_reference,
 * structure_cluster (sky_index, fog_reference), structure_subcluster (world_bounds), and the debug-only
 * leaf_portal / map_leaf_face / real_point2d readers.
 *
 * The marker CE_RB_FUNCTIONS is replaced with function bodies extracted verbatim from the pinned submodule
 * (structures.c, structure_render.c, structure_visibility.c, scenario.c, render_cameras.c, leaf_map.c).
 * Each run takes one probe: the Python driver passes synthetic member values on argv, the verbatim CE
 * consumer runs, and one result line is printed for the driver to compare against an independent oracle.
 * Only lookups of the enclosing structure (global_structure_bsp_get, bsp3d_test_point, scenario_get_sky)
 * and debug draw sinks are stubbed; they record what the verbatim code asked for.
 * Host ILP32 only; not an EE qualification. */

#include "cseries/cseries.h"
#include "math/real_math.h"
#include "math/geometry.h"
#include <stdio.h>
#include <stdlib.h>
#include <stddef.h>

#define NONE (-1)
#define NUMBEROF(a) (sizeof(a) / sizeof((a)[0]))
#define FLAG(b) (1u << (b))
#define TEST_FLAG(flags, bit) (((flags) & (unsigned long)FLAG(bit)) != 0)
#define VALID_INDEX(index, count) ((index) >= 0 && (index) < (count))
#define MAXIMUM_VERTICES_PER_CLUSTER_PORTAL 128
#define MAXIMUM_SURFACES_PER_PROBE 64
#define _error_silent 2
#define _portal_hull_from_portal_discarded 1
#define _intersection_out 0
#define _intersection_spanning 1
#define _intersection_in 2
#define _shader_type_environment 3
#define _rasterizer_vertex_type_environment_uncompressed 0
#define _rasterizer_vertex_type_environment_compressed 1
#define _render_frustum_point_flags_left_bit 0
#define _render_frustum_point_flags_right_bit 1
#define _render_frustum_point_flags_bottom_bit 2
#define _render_frustum_point_flags_top_bit 3
#define _render_frustum_point_flags_near_bit 4
#define _render_frustum_point_flags_far_bit 5
#define RENDER_FRUSTUM_POINT_FLAGS_PLANE_MASK 0xFu
#define LONG_MAX 2147483647L
#define LONG_MIN (-2147483647L - 1L)
#define SHORT_MAX 32767

#define match_assert(file, line, expr) do { if (!(expr)) { fprintf(stderr, "ASSERT %d\n", (line)); exit(3); } } while (0)
#define TAG_BLOCK_GET_ELEMENT(block_address, index, type) ((type *)((block_address)->address) + (index))

struct tag_block
{
	long count;
	void *address;
	unsigned long definition;
};

struct tag_reference
{
	unsigned long group_tag;
	char *name;
	long name_length;
	long index;
};

struct bsp3d_node
{
	long plane_designator;
	long children[2];
};

struct collision_bsp_bsp3d
{
	struct tag_block planes;
	struct tag_block nodes;
};

struct collision_bsp
{
	struct collision_bsp_bsp3d bsp3d;
};

struct structure_cluster_portal
{
	short cluster_indices[2];
	long plane_index;
	real_point3d centroid;
	real bounding_radius;
	unsigned long flags;
	long unused[6];
	struct tag_block vertices;
};

struct structure_surface
{
	word vertex_indices[3];
};

struct structure_surface_reference
{
	long surface_index;
	long bsp3d_node_index;
};

struct structure_leaf
{
	byte_rectangle3d bounds;
	word pad;
	short cluster_index;
	short surface_reference_count;
	long first_surface_reference_index;
};

struct structure_cluster
{
	short sky_index;
	short fog_reference;
};

struct structure_fog_plane
{
	short region_index;
	short runtime_material_type;
	real_plane3d plane;
	byte unused14[0xC];
};

struct structure_fog_region_stub
{
	long unused;
};

struct structure_lightmap
{
	struct tag_block materials;
};

struct environment_vertex_compressed
{
	real_point3d position;
};

struct structure_material
{
	struct
	{
		short type;
	} vertices;
	struct tag_block compressed_vertex_data;
};

struct fog_definition
{
	unsigned long flags;
	real plane_distance;
};
#define fog_definition_get(index) ((struct fog_definition *)0)

struct structure_visibility_sky
{
	struct tag_reference model;
};

struct shader
{
	short type;
};

struct location
{
	short cluster_index;
};

struct render_camera
{
	real_point3d position;
};

struct structure_bsp
{
	struct tag_block collision_bsp;
	struct tag_block cluster_portals;
	struct tag_block surfaces;
	struct tag_block surface_references;
	struct tag_block leaves;
	struct tag_block lightmaps;
	struct tag_block clusters;
	struct tag_block fog_planes;
	struct tag_block fog_regions;
	union real_rectangle3d world_bounds;
};

struct render_frustum
{
	union real_rectangle3d world_bounds;
	real_plane3d world_planes[6];
	real_point3d world_vertices[8];
};

/* render state read and written by structure_visibility_find_camera */
static struct
{
	long leaf_index;
	short cluster_index;
	short visible_sky_index;
	boolean visible_sky_model;
} render;

static struct structure_bsp *global_structure_bsp_storage;
static struct collision_bsp_bsp3d *global_bsp3d_storage;
static long bsp3d_test_point_result = NONE;
static long last_scenario_sky_arg = -99;
static struct structure_visibility_sky sky_storage;
static union real_argb_color global_real_argb_red_value = { { 1.0f, 1.0f, 0.0f, 0.0f } };
const union real_argb_color *global_real_argb_red = &global_real_argb_red_value;
static boolean structure_warned_about_portal_vertices;

/* qsort_4byte (cseries/sort.c) is a stable comparison sort; the probe only needs its ordering contract. */
void qsort_4byte(long *elements, unsigned long element_count, boolean (*compare)(long, long))
{
	unsigned long i, j;
	for (i = 1; i < element_count; i++)
		for (j = i; j > 0 && compare(elements[j - 1], elements[j]); j--)
		{
			long swap = elements[j - 1];
			elements[j - 1] = elements[j];
			elements[j] = swap;
		}
}
static int debug_sink_lines;
static int debug_sink_triangles;

static struct structure_bsp *global_structure_bsp_get(void)
{
	return global_structure_bsp_storage;
}

static struct collision_bsp_bsp3d *global_bsp3d_get(void)
{
	return global_bsp3d_storage;
}

/* structure_bsp_find_material_for_surface (structure_bsp_definitions.c:73) is a lightmap/material range search
 * outside the bsp3d-node question this probe varies. Stub: surface 0 lives in lightmap 0 material 0. */
static boolean structure_bsp_find_material_for_surface(struct structure_bsp *structure, long surface_index,
	short *lightmap_index, short *material_index)
{
	(void)structure;
	*lightmap_index = 0;
	*material_index = 0;
	return surface_index == 0;
}

static void error(short priority, const char *format, ...)
{
	(void)priority;
	(void)format;
}

static long bsp3d_test_point(void const *bsp, long root, real_point3d const *point)
{
	(void)bsp;
	(void)root;
	(void)point;
	return bsp3d_test_point_result;
}

static void *scenario_get_sky(short index)
{
	last_scenario_sky_arg = index;
	return (index >= 0 && index < 8) ? (void *)&sky_storage : NULL;
}

static void render_debug_triangle(boolean immediate, real_point3d const *a, real_point3d const *b,
	real_point3d const *c, real_argb_color const *color)
{
	(void)immediate; (void)a; (void)b; (void)c; (void)color;
	debug_sink_triangles++;
}

static void render_debug_line(boolean immediate, real_point3d const *a, real_point3d const *b, real_argb_color const *color)
{
	(void)immediate; (void)color;
	debug_sink_lines++;
	printf("LINE %.3f,%.3f,%.3f %.3f,%.3f,%.3f\n", a->x, a->y, a->z, b->x, b->y, b->z);
}

/* scenario_fog_region_get_fog_index: no fog definitions in the probe, so every fog plane keeps its plane distance 0 */
static long scenario_fog_region_get_fog_index(short fog_region_index)
{
	(void)fog_region_index;
	return NONE;
}


/* host stand-ins for cseries helpers the verbatim bodies call (the probe does not exercise allocation or logging) */
/* cseries.h maps memset/strcmp/realloc onto these helpers, so the stand-ins must not call the libc names */
void *csmemset(void *buffer, long c, unsigned long size)
{
	unsigned char *bytes = (unsigned char *)buffer;
	unsigned long i;
	for (i = 0; i < size; i++)
		bytes[i] = (unsigned char)c;
	return buffer;
}

long csstrcmp(const char *s1, const char *s2)
{
	while (*s1 && *s1 == *s2)
	{
		s1++;
		s2++;
	}
	return (long)(unsigned char)*s1 - (long)(unsigned char)*s2;
}

void *debug_realloc(void *pointer, unsigned int size, const char *file, long line)
{
	(void)file; (void)line;
	return realloc(pointer, size);
}

#define structure_material_get_vertex(material, vertex_index) \
	((struct environment_vertex_compressed const *) \
		(material)->compressed_vertex_data.address + (vertex_index))

/* CE math table (math/real_math.c:56) used by the inline project_point3d() */
short const global_projection3d_mappings[3][2][2] = { { { 2, 1 }, { 1, 2 }, }, { { 0, 2 }, { 2, 0 }, }, { { 1, 0 }, { 0, 1 }, } };

/* leaf_map / map_leaf / map_leaf_face / bsp3d layouts used by the verbatim spans routine */
struct map_leaf_face
{
	long node_index;
	struct tag_block vertices;
};

struct map_leaf
{
	struct tag_block faces;
	struct tag_block portal_designators;
};

struct leaf_map_bsp3d
{
	struct tag_block planes;
	struct tag_block nodes;
};

struct leaf_map
{
	const struct leaf_map_bsp3d *bsp;
	struct tag_block leaves;
	struct tag_block portals;
};

/* CE assertion sinks used by the match_assert of the verbatim bodies */
void display_assert(char *information, char *file, long line, boolean fatal)
{
	(void)information; (void)file; (void)line; (void)fatal;
	exit(3);
}

void system_exit(long code)
{
	exit((int)code);
}

/* CE_RB_FUNCTIONS */

static int parse_real_l(const char *text, real *out) { return sscanf(text, "%f", out) == 1; }

int main(int argc, char **argv)
{
	/* spans <node_index> <face_count_vertices> [u v]...  ; face plane = nodes[node].plane_designator
	 * test plane x=0 (normal (1,0,0), d=0); test polygon is the square [-3,3]^2 in its projection. */
	struct bsp3d_node nodes[2];
	struct real_plane3d planes[2];
	struct leaf_map_bsp3d bsp3d;
	struct leaf_map map;
	struct map_leaf leaf;
	struct map_leaf_face face;
	real_point2d face_vertices[16];
	real_point2d polygon[4];
	real_plane3d test_plane;
	long node_index, count, i;
	int arg = 4;
	boolean result;
	short projection;
	boolean sign;

	if (argc < 4) return 2;
	sscanf(argv[2], "%ld", &node_index);
	sscanf(argv[3], "%ld", &count);
	for (i = 0; i < count; i++)
	{
		parse_real_l(argv[arg++], &face_vertices[i].x);
		parse_real_l(argv[arg++], &face_vertices[i].y);
	}
	nodes[0].plane_designator = 0; nodes[0].children[0] = NONE; nodes[0].children[1] = NONE;
	nodes[1].plane_designator = 1; nodes[1].children[0] = NONE; nodes[1].children[1] = NONE;
	planes[0].n.i = 0; planes[0].n.j = 0; planes[0].n.k = 1; planes[0].d = 0;
	planes[1].n.i = 0; planes[1].n.j = 0; planes[1].n.k = 1; planes[1].d = 5;
	bsp3d.planes.count = 2; bsp3d.planes.address = planes;
	bsp3d.nodes.count = 2; bsp3d.nodes.address = nodes;
	face.node_index = node_index;
	face.vertices.count = count;
	face.vertices.address = face_vertices;
	leaf.faces.count = 1; leaf.faces.address = &face;
	leaf.portal_designators.count = 0; leaf.portal_designators.address = NULL;
	map.bsp = &bsp3d;
	map.leaves.count = 1; map.leaves.address = &leaf;
	map.portals.count = 0; map.portals.address = NULL;
	polygon[0].x = -3; polygon[0].y = -3;
	polygon[1].x = 3; polygon[1].y = -3;
	polygon[2].x = 3; polygon[2].y = 3;
	polygon[3].x = -3; polygon[3].y = 3;
	test_plane.n.i = 1; test_plane.n.j = 0; test_plane.n.k = 0; test_plane.d = 0;
	projection = projection_from_vector3d(&test_plane.n);
	sign = projection_sign_from_vector3d(&test_plane.n, projection);
	result = leaf_map_leaf_spans_polygon(&map, 0, &test_plane, projection, sign, 4, polygon);
	printf("SPANS %d\n", result ? 1 : 0);
	return 0;
}
