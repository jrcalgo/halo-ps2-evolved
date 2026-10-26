/* C4 structure_bsp.world_bounds copy of tests/c4_parity_pvs_portal_host.c (itself a copy of
tests/hcu_mp_portal_visibility_host.c). Adds a "build" mode that calls the real
structure_visibility_build_surfaces (structure_visibility.c:1534) with a small sphere, so the
root node bounds are dequantized from structure_bsp.world_bounds (traverse_node:1388, root call
at :1588). Original header follows.
C4 member-exact copy of tests/hcu_mp_portal_visibility_host.c with per-cluster VIS/READ/READP
 * and per-portal HULL output added so mutated fixtures expose what CE traversal consumed. */
/*
Host harness for the retail multiplayer portal/visibility slice.

The marker below is replaced with the CE functions extracted from
structure_visibility.c and structure_bsp_definitions.c. Screen-space portal
clipping is not part of the adjacency comparison: portal_hull_from_points
returns discarded after the real portal_hull_from_portal plane-index check,
so cluster traversal records back/front/plane without recursing. Frustum
cube and triangle tests are held open or unused; cluster surface-index
blocks are empty on these maps, and build_surfaces uses the real CE
rectangle/plane intersection with a containing box.
*/

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

enum
{
	TRUE = 1,
	FALSE = 0,
	NONE = -1,
	_intersection_out = 0,
	_intersection_spanning = 1,
	_intersection_in = 2,
	_portal_hull_from_portal_succeeded = 0,
	_portal_hull_from_portal_discarded = 1,
	_portal_hull_from_portal_degenerate = 2,
	_error_silent = 2,
	_shader_type_environment = 3,
	MAXIMUM_PORTAL_HULL_VERTICES = 256,
	COMPRESSED_STRUCTURE_VERTEX_SIZE = 0x20,
	MAXIMUM_RENDERED_ENVIRONMENT_SURFACES = 32768,
	MAXIMUM_RENDERED_CLUSTERS = 128,
	MAXIMUM_SURFACES_PER_STRUCTURE = 0x20000,
	MAXIMUM_CLUSTERS_PER_STRUCTURE = 512,
	NUMBER_OF_VERTICES_PER_TRIANGLE = 3,
	NUMBER_OF_POINTS_PER_RECTANGLE = 4,
	LONG_BITS = 32,
	LONG_BITS_BITS = 5,
	LONG_MAX = 2147483647L,
	UNSIGNED_CHAR_MAX = 255,
	PORTAL_FIXTURE_MAGIC = 0x54524F50u
};

#define FLAG(b) (1 << (b))
#define TEST_FLAG(flags, bit) (((flags) & (unsigned)FLAG(bit)) != 0)
#define SET_FLAG(f, b, v) ((v) ? ((f) |= (unsigned)FLAG(b)) : ((f) &= (unsigned)~FLAG(b)))
#define BIT_VECTOR_SIZE_IN_LONGS(bit_count) (((bit_count) + (LONG_BITS - 1)) >> LONG_BITS_BITS)
#define BIT_VECTOR_SIZE_IN_BYTES(bit_count) (sizeof(long) * BIT_VECTOR_SIZE_IN_LONGS(bit_count))
#define BIT_VECTOR_TEST_FLAG(bit_vector, bit) (TEST_FLAG((bit_vector)[(bit) >> LONG_BITS_BITS], ((bit) & (LONG_BITS - 1))))
#define BIT_VECTOR_SET_FLAG(bit_vector, bit, enable) (SET_FLAG((bit_vector)[(bit) >> LONG_BITS_BITS], ((bit) & (LONG_BITS - 1)), enable))
#define MIN(a, b) ((a) > (b) ? (b) : (a))
#define REAL_MAX 3.4028235e38f
#define REAL_MIN -3.4028235e38f
#define profile_enter(section) ((void)0)
#define profile_exit(section) ((void)0)
#define match_assert(file, line, expr) \
	do { if (!(expr)) { display_assert(#expr, (char *)(file), (line), TRUE); system_exit(1); } } while (0)
#define match_vassert(file, line, expr, string) \
	do { if (!(expr)) { display_assert((char *)(string), (char *)(file), (line), TRUE); system_exit(1); } } while (0)
#define valid_portal_hull(hull) \
	((hull) && (hull)->vertex_count >= 0 && (hull)->vertex_count <= MAXIMUM_PORTAL_HULL_VERTICES)
#define shader_definition_get(index) ((struct shader *)tag_get(0x73686472u, (index)))
#define structure_visibility_shader_environment_get(shader) \
	((struct structure_visibility_shader_environment *)shader_get_and_verify_type((shader), _shader_type_environment))
#define TAG_BLOCK_GET_ELEMENT(block_address, index, type) \
	((type *)tag_block_get_element_fast((block_address), (index), (long)sizeof(type)))

struct tag_block_definition
{
	void *name;
	unsigned long flags;
	long maximum_element_count;
	long element_size;
};

struct tag_block
{
	long count;
	void *address;
	struct tag_block_definition *definition;
};

struct tag_reference
{
	unsigned long group_tag;
	char *name;
	long name_length;
	long index;
};

struct tag_data
{
	long size;
	unsigned long pad;
	long file_offset;
	void *address;
	void *definition;
};

union real_point2d
{
	real n[2];
	struct { real x, y; };
};

union real_point3d
{
	real n[3];
	struct { real x, y, z; };
};

union real_vector3d
{
	real n[3];
	struct { real i, j, k; };
};

struct real_plane3d
{
	union real_vector3d n;
	real d;
};

union real_rectangle2d
{
	real n[4];
	struct { real x0, x1, y0, y1; };
};

union real_rectangle3d
{
	real n[6];
	struct { real x0, x1, y0, y1, z0, z1; };
};

struct real_argb_color
{
	real n[4];
};

union byte_rectangle3d
{
	byte n[6];
	struct { byte x0, x1, y0, y1, z0, z1; };
};

struct shader_base
{
	short type;
};

struct shader
{
	struct shader_base base;
};

struct structure_visibility_shader_environment
{
	struct shader shader;
	byte unused[0x2E4];
	real mirror_index_of_refraction;
	real mirror_depth;
};

struct render_camera
{
	union real_point3d position;
	union real_vector3d forward;
	real z_far;
};

struct render_frustum
{
	int unused;
};

struct rendered_cluster
{
	short cluster_index;
	union real_rectangle2d clip_bounds;
	struct render_frustum frustum;
};

struct render_mirror
{
	struct real_plane3d plane;
	real index_of_refraction;
	real depth;
	short cluster_index;
	word pad;
};

struct render_globals
{
	struct render_camera camera;
	struct render_frustum frustum;
	long cluster_index;
	boolean visible_sky_model;
	unsigned long visible_cluster_flags[MAXIMUM_CLUSTERS_PER_STRUCTURE / LONG_BITS];
	struct rendered_cluster rendered_clusters[MAXIMUM_RENDERED_CLUSTERS];
	short rendered_cluster_count;
	unsigned long environment_surface_flags[MAXIMUM_SURFACES_PER_STRUCTURE / LONG_BITS];
	long environment_surface_count;
};

struct structure_leaf
{
	union byte_rectangle3d bounds;
	word pad;
	short cluster_index;
	short surface_reference_count;
	long first_surface_reference_index;
};

struct structure_visibility_surface_reference
{
	long surface_index;
	long bsp3d_node_index;
};

struct structure_visibility_surface
{
	word vertex_indices[NUMBER_OF_VERTICES_PER_TRIANGLE];
};

struct vertex_buffer
{
	short type;
	word pad;
	long count;
	long offset;
	void *base_address;
	void *hardware_format;
};

struct structure_material
{
	struct tag_reference shader;
	short permutation_index;
	word flags;
	long first_surface_index;
	long surface_count;
	union real_point3d centroid;
	byte lighting[0x74];
	struct real_plane3d plane;
	short breakable_surface_index;
	word copious_unused_space;
	struct vertex_buffer vertices;
	struct vertex_buffer lightmap_vertices;
	struct tag_data uncompressed_vertex_data;
	struct tag_data compressed_vertex_data;
};

struct structure_lightmap
{
	short bitmap_index;
	word pad;
	long unused[4];
	struct tag_block materials;
};

struct bsp3d
{
	struct tag_block nodes;
	struct tag_block planes;
};

struct collision_bsp
{
	struct bsp3d bsp3d;
	byte rest[72];
};

struct structure_visibility_cluster
{
	short sky_index;
	short fog_designator;
	short background_sound_palette_index;
	short sound_environment_palette_index;
	short weather_palette_index;
	short transition_structure_bsp_index;
	short first_runtime_decal_index;
	word runtime_decal_count;
	long unused[6];
	struct tag_block predicted_resources;
	struct tag_block subclusters;
	word first_lens_flare_marker_index;
	word lens_flare_marker_count;
	struct tag_block surface_indices;
	struct tag_block mirrors;
	struct tag_block portal_indices;
};

struct structure_visibility_subcluster
{
	union real_rectangle3d world_bounds;
	struct tag_block surface_indices;
};

struct structure_visibility_portal
{
	short cluster_indices[2];
	long plane_index;
	union real_point3d centroid;
	real bounding_radius;
	unsigned long flags;
	long unused[6];
	struct tag_block vertices;
};

struct structure_visibility_mirror
{
	struct real_plane3d plane;
	long unused[5];
	struct tag_reference shader;
	struct tag_block points;
};

struct portal_hull
{
	short vertex_count;
	word pad;
	union real_point2d vertices[MAXIMUM_PORTAL_HULL_VERTICES];
};

struct structure_visibility_globals
{
	unsigned long *visited_cluster_flags;
	short rendered_cluster_indices[MAXIMUM_CLUSTERS_PER_STRUCTURE];
};

struct structure_bsp
{
	struct tag_reference lightmap_group;
	real vehicle_floor;
	real vehicle_ceiling;
	long sad_unused[5];
	byte default_lighting[0x74];
	long lonely_unused;
	struct tag_block collision_materials;
	struct tag_block collision_bsp;
	struct tag_block nodes;
	union real_rectangle3d world_bounds;
	struct tag_block leaves;
	struct tag_block surface_references;
	struct tag_block surfaces;
	struct tag_block lightmaps;
	long render_unused[3];
	struct tag_block lens_flares;
	struct tag_block lens_flare_markers;
	struct tag_block clusters;
	struct tag_data cluster_data;
	struct tag_block cluster_portals;
	long cluster_unused[3];
	struct tag_block breakable_surfaces;
	struct tag_block fog_planes;
	struct tag_block fog_regions;
	struct tag_block fog_palette;
	long fog_unused[6];
	struct tag_block weather_palette;
	struct tag_block weather_polyhedra;
	long weather_unused[6];
	struct tag_block pathfinding_surfaces;
	struct tag_block pathfinding_edges;
	struct tag_block background_sound_palette;
	struct tag_block sound_environment_palette;
	struct tag_data sound_cluster_data;
	long sound_unused[6];
};

typedef char portals_tag_block_size[(sizeof(struct tag_block) == 12) ? 1 : -1];
typedef char portals_tag_data_size[(sizeof(struct tag_data) == 20) ? 1 : -1];
typedef char portals_plane_size[(sizeof(struct real_plane3d) == 16) ? 1 : -1];
typedef char portals_point_size[(sizeof(union real_point3d) == 12) ? 1 : -1];
typedef char portals_box_size[(sizeof(union real_rectangle3d) == 24) ? 1 : -1];
typedef char portals_leaf_size[(sizeof(struct structure_leaf) == 16) ? 1 : -1];
typedef char portals_reference_size[(sizeof(struct structure_visibility_surface_reference) == 8) ? 1 : -1];
typedef char portals_surface_size[(sizeof(struct structure_visibility_surface) == 6) ? 1 : -1];
typedef char portals_collision_size[(sizeof(struct collision_bsp) == 96) ? 1 : -1];
typedef char portals_cluster_size[(sizeof(struct structure_visibility_cluster) == 0x68) ? 1 : -1];
typedef char portals_subcluster_size[(sizeof(struct structure_visibility_subcluster) == 0x24) ? 1 : -1];
typedef char portals_portal_size[(sizeof(struct structure_visibility_portal) == 0x40) ? 1 : -1];
typedef char portals_mirror_size[(sizeof(struct structure_visibility_mirror) == 0x40) ? 1 : -1];
typedef char portals_lightmap_size[(sizeof(struct structure_lightmap) == 32) ? 1 : -1];
typedef char portals_material_size[(sizeof(struct structure_material) == 0x100) ? 1 : -1];
typedef char portals_subcluster_off[(offsetof(struct structure_visibility_cluster, subclusters) == 0x34) ? 1 : -1];
typedef char portals_legacy_off[(offsetof(struct structure_visibility_cluster, surface_indices) == 0x44) ? 1 : -1];
typedef char portals_mirror_off[(offsetof(struct structure_visibility_cluster, mirrors) == 0x50) ? 1 : -1];
typedef char portals_plist_off[(offsetof(struct structure_visibility_cluster, portal_indices) == 0x5C) ? 1 : -1];
typedef char portals_vertices_off[(offsetof(struct structure_visibility_portal, vertices) == 0x34) ? 1 : -1];
typedef char portals_collision_off[(offsetof(struct structure_bsp, collision_bsp) == 0xB0) ? 1 : -1];
typedef char portals_leaves_off[(offsetof(struct structure_bsp, leaves) == 0xE0) ? 1 : -1];
typedef char portals_refs_off[(offsetof(struct structure_bsp, surface_references) == 0xEC) ? 1 : -1];
typedef char portals_surfaces_off[(offsetof(struct structure_bsp, surfaces) == 0xF8) ? 1 : -1];
typedef char portals_clusters_off[(offsetof(struct structure_bsp, clusters) == 0x134) ? 1 : -1];
typedef char portals_cdata_off[(offsetof(struct structure_bsp, cluster_data) == 0x140) ? 1 : -1];
typedef char portals_cportals_off[(offsetof(struct structure_bsp, cluster_portals) == 0x154) ? 1 : -1];
typedef char portals_sound_off[(offsetof(struct structure_bsp, sound_cluster_data) == 0x214) ? 1 : -1];
typedef char portals_compressed_off[(offsetof(struct structure_material, compressed_vertex_data) == 0xEC) ? 1 : -1];

typedef union real_point2d real_point2d;
typedef union real_point3d real_point3d;
typedef union real_vector3d real_vector3d;
typedef struct real_plane3d real_plane3d;
typedef union real_rectangle2d real_rectangle2d;
typedef union real_rectangle3d real_rectangle3d;
typedef struct real_argb_color real_argb_color;
typedef union byte_rectangle3d byte_rectangle3d;

struct render_globals render;
boolean structures_use_pvs_for_vs;
boolean debug_portals;
short global_current_collision_user_depth;
static struct structure_bsp *active_bsp;
static struct structure_visibility_globals structure_visibility_globals;
static boolean warned_about_rendered_clusters;
static unsigned long structure_bsp_empty_cluster_pvs[BIT_VECTOR_SIZE_IN_LONGS(MAXIMUM_CLUSTERS_PER_STRUCTURE)];
static unsigned long visited_clusters[BIT_VECTOR_SIZE_IN_LONGS(MAXIMUM_CLUSTERS_PER_STRUCTURE)];
static union real_rectangle2d null_rectangle_storage;
real_rectangle2d const *global_null_rectangle2d = &null_rectangle_storage;
static struct real_argb_color red_storage;
const struct real_argb_color *global_real_argb_red = &red_storage;
static int hull_points_calls;
static long handoff_portal = -1;
static int error_calls;
static int oob_gets;
static int capture;
static struct tag_block *capture_index_block;
static struct tag_block *capture_portal_block;

enum { MAX_PORTAL_EVENTS = 8192 };

static short cap_shorts[MAX_PORTAL_EVENTS];
static int cap_short_count;
static struct cap_portal
{
	long index;
	short back;
	short front;
	long plane;
} cap_portals[MAX_PORTAL_EVENTS];
static int cap_portal_count;

void display_assert(char *information, char *file, long line, boolean fatal)
{
	fprintf(stderr, "assert %s:%ld %s fatal=%u\n", file ? file : "?", line,
		information ? information : "", fatal);
}

void system_exit(long code)
{
	exit(code ? (int)code : 1);
}

void error(short priority, const char *format, ...)
{
	(void)priority;
	(void)format;
	error_calls++;
}

void *tag_get(unsigned long group, long index)
{
	(void)group;
	(void)index;
	return 0;
}

struct shader *shader_get_and_verify_type(struct shader *shader, short shader_type)
{
	(void)shader_type;
	return shader;
}

struct structure_bsp *global_structure_bsp_get(void)
{
	return active_bsp;
}

struct rendered_cluster *rendered_cluster_get(short rendered_cluster_index)
{
	if (rendered_cluster_index < 0 || rendered_cluster_index >= MAXIMUM_RENDERED_CLUSTERS)
	{
		fprintf(stderr, "rendered cluster index %d\n", rendered_cluster_index);
		exit(11);
	}
	return &render.rendered_clusters[rendered_cluster_index];
}

static void *tag_block_get_element_with_size(struct tag_block const *block, long index, long element_size)
{
	static byte empty_element[256];

	(void)block;
	(void)index;
	oob_gets++;
	if (element_size < 0 || element_size > (long)sizeof(empty_element))
		return 0;
	memset(empty_element, 0, sizeof(empty_element));
	return empty_element;
}

static void *tag_block_get_element_fast(struct tag_block const *block, long index, long element_size)
{
	void *element;

	if (block && index >= 0 && index < block->count && block->address &&
		(!block->definition || block->definition->element_size == element_size))
	{
		element = (char *)block->address + index * element_size;
	}
	else
	{
		element = tag_block_get_element_with_size(block, index, element_size);
	}

	if (capture && element && block == capture_index_block && element_size == (long)sizeof(short))
	{
		if (cap_short_count >= MAX_PORTAL_EVENTS)
			exit(13);
		cap_shorts[cap_short_count++] = *(short *)element;
	}
	if (capture && element && block == capture_portal_block &&
		element_size == (long)sizeof(struct structure_visibility_portal))
	{
		struct structure_visibility_portal *portal = element;

		if (cap_portal_count >= MAX_PORTAL_EVENTS)
			exit(13);
		cap_portals[cap_portal_count].index = index;
		cap_portals[cap_portal_count].back = portal->cluster_indices[0];
		cap_portals[cap_portal_count].front = portal->cluster_indices[1];
		cap_portals[cap_portal_count].plane = portal->plane_index;
		cap_portal_count++;
	}
	return element;
}

static short portal_hull_from_points(
	struct render_camera const *camera,
	struct render_frustum const *frustum,
	struct real_plane3d const *plane,
	short vertex_count,
	union real_point3d const *vertices,
	short winding,
	struct portal_hull *result)
{
	(void)camera;
	(void)frustum;
	(void)plane;
	(void)vertex_count;
	(void)vertices;
	(void)winding;
	hull_points_calls++;
	if (handoff_portal >= 0)
		printf("HANDOFF %ld n=%d x=%.6f y=%.6f z=%.6f\n", handoff_portal, (int)vertex_count,
			(double)vertices[0].x, (double)vertices[0].y, (double)vertices[0].z);
	if (handoff_portal >= 0)
		printf("HANDOFFPLANE %ld n=%.6f,%.6f,%.6f d=%.6f\n", handoff_portal, (double)plane->n.i,
			(double)plane->n.j, (double)plane->n.k, (double)plane->d);
	result->vertex_count = 0;
	return _portal_hull_from_portal_discarded;
}

static boolean points_within_distance(short point_count, union real_point3d const *points, real distance)
{
	(void)point_count;
	(void)points;
	(void)distance;
	return FALSE;
}

static void structure_visibility_render_debug_portal_hull(
	struct portal_hull const *hull,
	struct real_argb_color const *color,
	real offset)
{
	(void)hull;
	(void)color;
	(void)offset;
}

short convex_hull2d_intersect(
	short p_count,
	union real_point2d const *p,
	short q_count,
	union real_point2d const *q,
	short maximum_count,
	union real_point2d *result,
	real epsilon)
{
	(void)p_count;
	(void)p;
	(void)q_count;
	(void)q;
	(void)maximum_count;
	(void)result;
	(void)epsilon;
	return 0;
}

boolean ai_debug_highlight_cluster(short index, struct real_argb_color const **highlight_color)
{
	(void)index;
	(void)highlight_color;
	return FALSE;
}

short render_frustum_cube_visible(
	struct render_frustum const *frustum,
	union real_rectangle3d const *bounds,
	boolean test_frustum_against_cube)
{
	(void)frustum;
	(void)bounds;
	(void)test_frustum_against_cube;
	return 1;
}

boolean render_frustum_triangle_visible(
	struct render_frustum const *frustum,
	union real_point3d const *point0,
	union real_point3d const *point1,
	union real_point3d const *point2)
{
	(void)frustum;
	(void)point0;
	(void)point1;
	(void)point2;
	return FALSE;
}

void render_frustum_get_projection_bounds(struct render_frustum const *frustum, union real_rectangle2d *bounds)
{
	(void)frustum;
	bounds->x0 = -1.0f;
	bounds->x1 = 1.0f;
	bounds->y0 = -1.0f;
	bounds->y1 = 1.0f;
}

/* dequantize_byte_to_real_rectangle3d is the real CE function (structure_visibility.c:883-910),
 * spliced in by the test driver; the PVS lane's no-op stub is not used by this copy. */

boolean structure_bsp_port_verify(struct structure_bsp const *structure_bsp);
unsigned long *structure_bsp_get_cluster_pvs(struct structure_bsp *structure_bsp, short cluster_index);

/* structure_visibility.c:138 and physics/bsp3d.h:38-42 (verbatim layouts) */
struct bsp3d_node
{
	long plane_designator;
	long children[2];
};
enum { MAXIMUM_STRUCTURE_BSP_TRAVERSAL_DEPTH = 1024 };
static boolean warned_about_structure_bsp_depth;

/* Helpers build_surfaces references. The small-sphere branch (radius < 2.0, which the
 * probe uses) returns before these; they trap if the probe ever reaches them. */
#ifndef NUMBEROF
#define NUMBEROF(array) ((long)(sizeof(array) / sizeof((array)[0])))
#endif
#ifndef LONG_MIN
#define LONG_MIN ((long)0x80000000L)
#endif
#define csmemset(p, v, n) memset((p), (v), (n))
#ifndef NONE
#define NONE (-1)
#endif
struct location { long cluster_index; char pad[60]; };
static real structure_sphere_threshold = 2.0f;
void scenario_location_from_point(struct location *location, const real_point3d *point)
{ (void)point; location->cluster_index = NONE; abort(); }
short structure_clusters_in_sphere(short cluster_index, real_point3d const *position,
    real radius, short maximum_count, short *intersected_indices)
{ (void)cluster_index; (void)position; (void)radius; (void)maximum_count;
  (void)intersected_indices; abort(); return 0; }
static short structure_visibility_build_surfaces_traverse_leaf(long leaf_index, real_rectangle3d const *parent_bounds,
    unsigned long *surface_flags, long *surface_indices, short maximum_count, real_point3d const *cull_sphere_center,
    real cull_sphere_radius, real_rectangle3d const *cull_bounds, short cull_plane_count,
    real_plane3d const *cull_planes, short intersection);

/* CE_PORTAL_VISIBILITY_FUNCTIONS */

static int fix_block(
	struct tag_block *block,
	uint32_t base,
	unsigned char *image,
	uint32_t size,
	uint32_t stride,
	char const *label)
{
	uint32_t va;
	uint32_t off;
	uint32_t bytes;

	if (block->count < 0 || (uint32_t)block->count > 0x1000000u)
	{
		fprintf(stderr, "bad count %s %ld\n", label, block->count);
		return -1;
	}
	if (block->count == 0)
		return 0;
	va = (uint32_t)(uintptr_t)block->address;
	bytes = (uint32_t)block->count * stride;
	if (va < base)
	{
		fprintf(stderr, "%s address %08x below base\n", label, va);
		return -1;
	}
	off = va - base;
	if (off > size || bytes > size - off)
	{
		fprintf(stderr, "%s extent off=%u bytes=%u size=%u\n", label, off, bytes, size);
		return -1;
	}
	block->address = image + off;
	block->definition = 0;
	return 0;
}

static int fix_data(
	struct tag_data *data,
	uint32_t base,
	unsigned char *image,
	uint32_t size,
	char const *label)
{
	uint32_t va;
	uint32_t off;

	if (data->size < 0)
		return -1;
	if (data->size == 0)
		return 0;
	va = (uint32_t)(uintptr_t)data->address;
	if (va < base)
	{
		fprintf(stderr, "%s data address below base\n", label);
		return -1;
	}
	off = va - base;
	if (off > size || (uint32_t)data->size > size - off)
	{
		fprintf(stderr, "%s data extent\n", label);
		return -1;
	}
	data->address = image + off;
	data->definition = 0;
	return 0;
}

static int relocate(struct structure_bsp *bsp, uint32_t base, unsigned char *image, uint32_t size)
{
	long cluster_index;
	long subcluster_index;
	long portal_index;
	long mirror_index;
	struct collision_bsp *collision;

	if (fix_block(&bsp->collision_bsp, base, image, size, 96, "collision_bsp"))
		return -1;
	if (bsp->collision_bsp.count < 1)
		return -1;
	collision = bsp->collision_bsp.address;
	if (fix_block(&collision->bsp3d.planes, base, image, size, 16, "planes"))
		return -1;
	/* structure_bsp.nodes (byte_rectangle3d, 6 bytes) and collision bsp3d nodes (12 bytes):
	 * the world_bounds traversal reads both (structure_visibility.c:1388+). */
	if (fix_block(&bsp->nodes, base, image, size, 6, "structure_nodes"))
		return -1;
	if (fix_block(&collision->bsp3d.nodes, base, image, size, 12, "bsp3d_nodes"))
		return -1;
	if (fix_block(&bsp->leaves, base, image, size, 16, "leaves"))
		return -1;
	if (fix_block(&bsp->surface_references, base, image, size, 8, "surface_references"))
		return -1;
	if (fix_block(&bsp->surfaces, base, image, size, 6, "surfaces"))
		return -1;
	if (fix_block(&bsp->clusters, base, image, size, 0x68, "clusters"))
		return -1;
	if (fix_data(&bsp->cluster_data, base, image, size, "cluster_data"))
		return -1;
	if (fix_block(&bsp->cluster_portals, base, image, size, 0x40, "cluster_portals"))
		return -1;

	for (cluster_index = 0; cluster_index < bsp->clusters.count; cluster_index++)
	{
		struct structure_visibility_cluster *cluster =
			(struct structure_visibility_cluster *)bsp->clusters.address + cluster_index;

		if (fix_block(&cluster->subclusters, base, image, size, 0x24, "subclusters"))
			return -1;
		for (subcluster_index = 0; subcluster_index < cluster->subclusters.count; subcluster_index++)
		{
			struct structure_visibility_subcluster *subcluster =
				(struct structure_visibility_subcluster *)cluster->subclusters.address + subcluster_index;

			if (fix_block(&subcluster->surface_indices, base, image, size, 4, "subcluster_surfaces"))
				return -1;
		}
		if (fix_block(&cluster->surface_indices, base, image, size, 4, "legacy_surfaces"))
			return -1;
		if (fix_block(&cluster->mirrors, base, image, size, 0x40, "mirrors"))
			return -1;
		for (mirror_index = 0; mirror_index < cluster->mirrors.count; mirror_index++)
		{
			struct structure_visibility_mirror *mirror =
				(struct structure_visibility_mirror *)cluster->mirrors.address + mirror_index;

			if (fix_block(&mirror->points, base, image, size, 12, "mirror_points"))
				return -1;
		}
		if (fix_block(&cluster->portal_indices, base, image, size, 2, "portal_indices"))
			return -1;
	}
	for (portal_index = 0; portal_index < bsp->cluster_portals.count; portal_index++)
	{
		struct structure_visibility_portal *portal =
			(struct structure_visibility_portal *)bsp->cluster_portals.address + portal_index;

		if (fix_block(&portal->vertices, base, image, size, 12, "portal_vertices"))
			return -1;
	}
	return 0;
}

static unsigned long long fnv_u32(unsigned long long hash, unsigned long value)
{
	hash ^= (unsigned long long)(value & 0xFFFFFFFFul);
	hash *= 1099511628211ull;
	return hash;
}

static int cmp_long(void const *left, void const *right)
{
	long a = *(long const *)left;
	long b = *(long const *)right;

	return (a > b) - (a < b);
}

static int flags_to_sorted(unsigned long const *flags, long count, long *out)
{
	long index;
	int total = 0;

	for (index = 0; index < count; index++)
	{
		if (BIT_VECTOR_TEST_FLAG(flags, index))
			out[total++] = index;
	}
	return total;
}

static unsigned long long hash_sorted(long const *values, int count)
{
	unsigned long long hash = 14695981039346656037ull;
	int index;

	hash = fnv_u32(hash, (unsigned long)count);
	for (index = 0; index < count; index++)
		hash = fnv_u32(hash, (unsigned long)values[index]);
	return hash;
}

static void containing_box(union real_rectangle3d *box)
{
	box->x0 = REAL_MIN;
	box->x1 = REAL_MAX;
	box->y0 = REAL_MIN;
	box->y1 = REAL_MAX;
	box->z0 = REAL_MIN;
	box->z1 = REAL_MAX;
}

static int surfaces_from_build(struct structure_bsp *bsp, short cluster_index, long *out)
{
	unsigned long surface_flags[BIT_VECTOR_SIZE_IN_LONGS(MAXIMUM_SURFACES_PER_STRUCTURE)];
	long *batch;
	union real_rectangle3d box;
	union real_point3d origin;
	short identity = cluster_index;
	int total = 0;

	batch = malloc(sizeof(long) * 32767);
	if (!batch)
		exit(14);
	memset(&origin, 0, sizeof(origin));
	containing_box(&box);
	memset(render.environment_surface_flags, 0xFF,
		BIT_VECTOR_SIZE_IN_BYTES(bsp->surfaces.count));
	memset(surface_flags, 0, sizeof(surface_flags));
	for (;;)
	{
		short found = structure_visibility_build_surfaces_traverse_clusters(
			batch,
			32767,
			&origin,
			1.0f,
			&box,
			0,
			0,
			surface_flags,
			1,
			&identity);

		if (found < 0 || total + found > bsp->surfaces.count)
		{
			free(batch);
			return -1;
		}
		memcpy(out + total, batch, (size_t)found * sizeof(long));
		total += found;
		if (found < 32767)
			break;
	}
	free(batch);
	qsort(out, (size_t)total, sizeof(long), cmp_long);
	return total;
}

static int surfaces_from_subclusters(struct structure_bsp *bsp, short cluster_index, long *out)
{
	memset(render.environment_surface_flags, 0, sizeof(render.environment_surface_flags));
	render.environment_surface_count = 0;
	render.rendered_cluster_count = 1;
	render.rendered_clusters[0].cluster_index = cluster_index;
	structures_use_pvs_for_vs = TRUE;
	structure_visibility_traverse_subclusters(bsp);
	return flags_to_sorted(render.environment_surface_flags, bsp->surfaces.count, out);
}

static unsigned long long portal_hash_for_cluster(struct structure_visibility_cluster *cluster)
{
	unsigned long long hash = 14695981039346656037ull;
	int short_index;
	int portal_cursor = 0;

	if (cap_short_count != cluster->portal_indices.count)
	{
		fprintf(stderr, "portal list capture %d != %ld\n", cap_short_count, cluster->portal_indices.count);
		exit(3);
	}
	for (short_index = 0; short_index < cap_short_count; short_index++)
	{
		struct cap_portal *record;

		if (portal_cursor >= cap_portal_count)
			exit(3);
		record = &cap_portals[portal_cursor++];
		if (record->index != cap_shorts[short_index])
		{
			fprintf(stderr, "portal read %ld != list %d\n", record->index, cap_shorts[short_index]);
			exit(3);
		}
		hash = fnv_u32(hash, (unsigned long)cap_shorts[short_index]);
		hash = fnv_u32(hash, (unsigned long)record->back);
		hash = fnv_u32(hash, (unsigned long)record->front);
		hash = fnv_u32(hash, (unsigned long)record->plane);
		if (portal_cursor < cap_portal_count && cap_portals[portal_cursor].index == record->index)
		{
			if (cap_portals[portal_cursor].back != record->back ||
				cap_portals[portal_cursor].front != record->front ||
				cap_portals[portal_cursor].plane != record->plane)
			{
				exit(3);
			}
			portal_cursor++;
		}
	}
	if (portal_cursor != cap_portal_count)
	{
		fprintf(stderr, "unconsumed portal reads %d/%d\n", portal_cursor, cap_portal_count);
		exit(3);
	}
	return hash;
}

static unsigned char *read_fixture(char const *path, uint32_t *base, uint32_t *root, uint32_t *size)
{
	FILE *stream;
	uint32_t header[4];
	unsigned char *image;

	stream = fopen(path, "rb");
	if (!stream)
	{
		perror(path);
		exit(2);
	}
	if (fread(header, 4, 4, stream) != 4 || header[0] != PORTAL_FIXTURE_MAGIC)
	{
		fprintf(stderr, "bad fixture header\n");
		exit(2);
	}
	*base = header[1];
	*root = header[2];
	*size = header[3];
	if (*root > *size || *size < 0x288 || *size > 0x4000000u)
		exit(2);
	image = malloc(*size);
	if (!image || fread(image, 1, *size, stream) != *size)
		exit(2);
	fclose(stream);
	return image;
}

int main(int argc, char **argv)
{
	uint32_t base;
	uint32_t root;
	uint32_t size;
	unsigned char *image;
	unsigned char *snapshot;
	struct structure_bsp *bsp;
	long *surfaces_a;
	long *surfaces_b;
	long *leaf_batch;
	unsigned long *union_flags;
	unsigned long *leaf_flags;
	long cluster_index;
	long leaf_index;
	long portal_index;
	long legacy = 0;
	long mirrors = 0;
	int sub_unique;
	int leaf_emit = 0;
	int plane_before;
	int traverse_plane_checks;
	unsigned long long sub_fnv;
	unsigned long long leaf_fnv;
	union real_rectangle3d box;
	union real_point3d origin;
	struct portal_hull screen_hull;
	struct render_mirror mirror_result;
	boolean mirror_found;
	int unref_count = 0;
	int bytes_same;
	short depth_before;

	if (argc != 2 && argc != 6)
	{
		fprintf(stderr, "usage: portal-visibility fixture\n");
		return 2;
	}
	null_rectangle_storage.x0 = REAL_MAX;
	null_rectangle_storage.x1 = REAL_MIN;
	null_rectangle_storage.y0 = REAL_MAX;
	null_rectangle_storage.y1 = REAL_MIN;
	memset(&render, 0, sizeof(render));
	memset(&origin, 0, sizeof(origin));
	containing_box(&box);
	image = read_fixture(argv[1], &base, &root, &size);
	bsp = (struct structure_bsp *)(image + root);
	printf("LAYOUT cluster_unused=%lu sound_unused=%lu size=%lu\n",
		(unsigned long)offsetof(struct structure_bsp, cluster_unused),
		(unsigned long)offsetof(struct structure_bsp, sound_unused),
		(unsigned long)sizeof(struct structure_bsp));
	active_bsp = bsp;
	if (relocate(bsp, base, image, size))
		return 2;
	snapshot = malloc(size);
	if (!snapshot)
		return 2;
	memcpy(snapshot, image, size);
	depth_before = global_current_collision_user_depth;
	if (!structure_bsp_port_verify(bsp))
	{
		fprintf(stderr, "structure_bsp_port_verify rejected the relocated bsp\n");
		return 8;
	}

	if (argc == 6)
	{
		/* argv: fixture cx cy cz radius -> real structure_visibility_build_surfaces */
		real_point3d center;
		long found_surfaces[4096];
		short found;
		short index;

		center.x = (real)atof(argv[2]);
		center.y = (real)atof(argv[3]);
		center.z = (real)atof(argv[4]);
		memset(render.environment_surface_flags, 0xFF,
			BIT_VECTOR_SIZE_IN_BYTES(bsp->surfaces.count));
		found = structure_visibility_build_surfaces(found_surfaces, 4096, &center,
			(real)atof(argv[5]), NULL, 0, NULL, 0, NULL);
		printf("COUNTS leaves=%ld surface_references=%ld surfaces=%ld\n", bsp->leaves.count,
			bsp->surface_references.count, bsp->surfaces.count);
		printf("BUILD %d", (int)found);
		for (index = 0; index < found; index++)
			printf(" %ld", found_surfaces[index]);
		printf("\n");
		printf("STATUS passed\n");
		return 0;
	}

	structures_use_pvs_for_vs = TRUE;
	render.cluster_index = 0;
	render.rendered_cluster_count = (short)bsp->clusters.count;
	for (cluster_index = 0; cluster_index < bsp->clusters.count; cluster_index++)
	{
		struct structure_visibility_cluster *cluster =
			(struct structure_visibility_cluster *)bsp->clusters.address + cluster_index;

		render.rendered_clusters[cluster_index].cluster_index = (short)cluster_index;
		legacy += cluster->surface_indices.count;
		mirrors += cluster->mirrors.count;
	}
	if (legacy != 0)
	{
		fprintf(stderr, "legacy cluster surface lists are present (%ld)\n", legacy);
		return 9;
	}
	memset(render.environment_surface_flags, 0, sizeof(render.environment_surface_flags));
	render.environment_surface_count = 0;
	structure_visibility_traverse_surface_lists(bsp);
	if (render.environment_surface_count != 0)
		return 9;

	surfaces_a = malloc(sizeof(long) * (size_t)bsp->surfaces.count);
	surfaces_b = malloc(sizeof(long) * (size_t)bsp->surfaces.count);
	union_flags = calloc(BIT_VECTOR_SIZE_IN_LONGS(MAXIMUM_SURFACES_PER_STRUCTURE), sizeof(unsigned long));
	leaf_flags = calloc(BIT_VECTOR_SIZE_IN_LONGS(MAXIMUM_SURFACES_PER_STRUCTURE), sizeof(unsigned long));
	if (!surfaces_a || !surfaces_b || !union_flags || !leaf_flags)
		return 14;

	printf("CLUSTERS %ld\n", bsp->clusters.count);
	for (cluster_index = 0; cluster_index < bsp->clusters.count; cluster_index++)
	{
		struct structure_visibility_cluster *cluster =
			(struct structure_visibility_cluster *)bsp->clusters.address + cluster_index;
		int from_flags;
		int from_build;
		unsigned long long surface_hash;
		unsigned long long portals_hash;

		from_flags = surfaces_from_subclusters(bsp, (short)cluster_index, surfaces_a);
		from_build = surfaces_from_build(bsp, (short)cluster_index, surfaces_b);
		if (from_flags < 0 || from_build < 0 || from_flags != from_build ||
			memcmp(surfaces_a, surfaces_b, (size_t)from_flags * sizeof(long)) != 0)
		{
			fprintf(stderr, "cluster %ld surface collectors differ flags=%d build=%d\n",
				cluster_index, from_flags, from_build);
			return 4;
		}
		{
			int bit;

			for (bit = 0; bit < from_flags; bit++)
				BIT_VECTOR_SET_FLAG(union_flags, surfaces_a[bit], TRUE);
		}
		surface_hash = hash_sorted(surfaces_a, from_flags);

		memset(render.visible_cluster_flags, 0, sizeof(render.visible_cluster_flags));
		memset(visited_clusters, 0, sizeof(visited_clusters));
		render.rendered_cluster_count = 0;
		render.cluster_index = cluster_index;
		structure_visibility_globals.visited_cluster_flags = visited_clusters;
		memset(&screen_hull, 0, sizeof(screen_hull));
		screen_hull.vertex_count = NUMBER_OF_POINTS_PER_RECTANGLE;
		cap_short_count = 0;
		cap_portal_count = 0;
		capture_index_block = &cluster->portal_indices;
		capture_portal_block = &bsp->cluster_portals;
		capture = 1;
		structure_visibility_traverse_cluster((short)cluster_index, &screen_hull);
		capture = 0;
		printf("VIS %ld", cluster_index);
		for (portal_index = 0; portal_index < bsp->clusters.count; portal_index++)
			if (BIT_VECTOR_TEST_FLAG(render.visible_cluster_flags, portal_index))
				printf(" %ld", portal_index);
		printf("\n");
		printf("READ %ld", cluster_index);
		{
			int read_index;

			for (read_index = 0; read_index < cap_short_count; read_index++)
				printf(" %d", cap_shorts[read_index]);
		}
		printf("\n");
		{
			int read_index;

			for (read_index = 0; read_index < cap_portal_count; read_index++)
				printf("READP %ld %d %d %ld\n", cap_portals[read_index].index,
					cap_portals[read_index].back, cap_portals[read_index].front,
					cap_portals[read_index].plane);
		}
		portals_hash = portal_hash_for_cluster(cluster);
		printf("CLUSTER %ld sub=%d sfnv=%016llx ports=%ld pfnv=%016llx\n",
			cluster_index, from_flags, surface_hash, cluster->portal_indices.count, portals_hash);
	}

	memset(render.environment_surface_flags, 0, sizeof(render.environment_surface_flags));
	render.environment_surface_count = 0;
	render.rendered_cluster_count = (short)bsp->clusters.count;
	for (cluster_index = 0; cluster_index < bsp->clusters.count; cluster_index++)
		render.rendered_clusters[cluster_index].cluster_index = (short)cluster_index;
	structure_visibility_traverse_subclusters(bsp);
	sub_unique = flags_to_sorted(render.environment_surface_flags, bsp->surfaces.count, surfaces_a);
	if (memcmp(render.environment_surface_flags, union_flags,
			BIT_VECTOR_SIZE_IN_BYTES(bsp->surfaces.count)) != 0)
	{
		fprintf(stderr, "global subcluster walk differs from the per-cluster union\n");
		return 4;
	}
	sub_fnv = hash_sorted(surfaces_a, sub_unique);
	traverse_plane_checks = hull_points_calls;

	leaf_batch = malloc(sizeof(long) * 32767);
	if (!leaf_batch)
		return 14;
	leaf_fnv = 14695981039346656037ull;
	memset(render.environment_surface_flags, 0xFF, BIT_VECTOR_SIZE_IN_BYTES(bsp->surfaces.count));
	for (leaf_index = 0; leaf_index < bsp->leaves.count; leaf_index++)
	{
		unsigned long surface_flags[BIT_VECTOR_SIZE_IN_LONGS(MAXIMUM_SURFACES_PER_STRUCTURE)];
		short found;
		short cursor;

		memset(surface_flags, 0, sizeof(surface_flags));
		found = structure_visibility_build_surfaces_traverse_leaf(
			leaf_index,
			&box,
			surface_flags,
			leaf_batch,
			32767,
			&origin,
			1.0f,
			&box,
			0,
			0,
			_intersection_in);
		if (found < 0)
			return 4;
		leaf_fnv = fnv_u32(leaf_fnv, (unsigned long)leaf_index);
		leaf_fnv = fnv_u32(leaf_fnv, (unsigned long)found);
		for (cursor = 0; cursor < found; cursor++)
		{
			leaf_fnv = fnv_u32(leaf_fnv, (unsigned long)leaf_batch[cursor]);
			BIT_VECTOR_SET_FLAG(leaf_flags, leaf_batch[cursor], TRUE);
		}
		leaf_emit += found;
	}

	hull_points_calls = 0;
	for (portal_index = 0; portal_index < bsp->cluster_portals.count; portal_index++)
	{
		struct portal_hull hull;

		memset(&hull, 0, sizeof(hull));
		handoff_portal = portal_index;
		portal_hull_from_portal((short)portal_index, FALSE, &hull);
		handoff_portal = -1;
		{
			short point;

			printf("HULL %ld n=%d", portal_index, hull.vertex_count);
			for (point = 0; point < hull.vertex_count; point++)
				printf(" %.6f,%.6f", hull.vertices[point].x, hull.vertices[point].y);
			printf("\n");
		}
	}
	plane_before = hull_points_calls;

	if (mirrors != 0 && !getenv("C4_ALLOW_MIRRORS"))
	{
		fprintf(stderr, "mirrors present (%ld); plane hull stub would hide them\n", mirrors);
		return 10;
	}
	render.cluster_index = 0;
	memset(&mirror_result, 0, sizeof(mirror_result));
	handoff_portal = 100000;
	mirror_found = structure_visibility_find_mirror(&render.camera, &render.frustum, &mirror_result);
	printf("MIRROR found=%d plane=%.6f,%.6f,%.6f,%.6f\n", mirror_found ? 1 : 0,
		mirror_result.plane.n.i, mirror_result.plane.n.j, mirror_result.plane.n.k, mirror_result.plane.d);
	{
		long hull_index;
		struct portal_hull hull;
		for (hull_index = 0; hull_index < bsp->cluster_portals.count; hull_index++)
		{
			int calls_before = hull_points_calls;
			portal_hull_from_portal((short)hull_index, FALSE, &hull);
			printf("HULL %ld n=%d reached=%d\n", hull_index, hull.vertex_count, hull_points_calls - calls_before);
		}
	}

	handoff_portal = -1;

	printf("UNREF count=");
	{
		long surface_index;
		int emitted = 0;

		for (surface_index = 0; surface_index < bsp->surfaces.count; surface_index++)
		{
			if (!BIT_VECTOR_TEST_FLAG(union_flags, surface_index) &&
				!BIT_VECTOR_TEST_FLAG(leaf_flags, surface_index))
			{
				unref_count++;
			}
		}
		printf("%d indices=", unref_count);
		if (unref_count == 0)
		{
			printf("-");
		}
		else
		{
			for (surface_index = 0; surface_index < bsp->surfaces.count; surface_index++)
			{
				if (!BIT_VECTOR_TEST_FLAG(union_flags, surface_index) &&
					!BIT_VECTOR_TEST_FLAG(leaf_flags, surface_index))
				{
					printf("%s%ld", emitted ? "," : "", surface_index);
					emitted++;
				}
			}
		}
	}
	printf("\n");

	bytes_same = memcmp(snapshot, image, size) == 0;
	if (!bytes_same || depth_before != 0 || global_current_collision_user_depth != 0 ||
		oob_gets != 0 || error_calls != 0 || plane_before != bsp->cluster_portals.count)
	{
		fprintf(stderr, "bytes=%d depth=%d->%d oob=%d errors=%d plane=%d/%ld\n",
			bytes_same, depth_before, global_current_collision_user_depth, oob_gets,
			error_calls, plane_before, bsp->cluster_portals.count);
		return 6;
	}

	printf("GLOBAL clusters=%ld surfaces=%ld portals=%ld leaves=%ld refs=%ld mirrors=%ld "
		"mirror_found=%d plane_ok=%d plane_fail=%ld traverse_plane_checks=%d oob_get=%d "
		"legacy=%ld list_added=%ld sub_unique=%d sub_fnv=%016llx leaf_emit=%d leaf_fnv=%016llx "
		"bytes_same=%d depth=%d\n",
		bsp->clusters.count, bsp->surfaces.count, bsp->cluster_portals.count, bsp->leaves.count,
		bsp->surface_references.count, mirrors, mirror_found ? 1 : 0, plane_before,
		bsp->cluster_portals.count - plane_before, traverse_plane_checks, oob_gets, legacy,
		(long)0, sub_unique, sub_fnv, leaf_emit, leaf_fnv, bytes_same,
		global_current_collision_user_depth);
printf("OFFS world=%lu leaves=%lu nodes=%lu refs=%lu surfaces=%lu\n",
		(unsigned long)offsetof(struct structure_bsp, world_bounds),
		(unsigned long)offsetof(struct structure_bsp, leaves),
		(unsigned long)offsetof(struct structure_bsp, nodes),
		(unsigned long)offsetof(struct structure_bsp, surface_references),
		(unsigned long)offsetof(struct structure_bsp, surfaces));
	/* C4 ranges-b probe (structure_leaf / structure_node members): CE leaf and node walks over one caller-chosen
	 * probe box C4_RB_BOX=x0,x1,y0,y1,z0,z1 (interior of the target leaf) and target leaf C4_RB_LEAF. */
	if (getenv("C4_RB_BOX") && getenv("C4_RB_LEAF"))
	{
		union real_rectangle3d pbox;
		union real_point3d center;
		real radius;
		long target = atol(getenv("C4_RB_LEAF"));
		unsigned long *leaf_surface_flags;
		long *batch = malloc(sizeof(long) * 32767);
		short found;
		long k;

		if (!batch || sscanf(getenv("C4_RB_BOX"), "%f,%f,%f,%f,%f,%f", &pbox.x0, &pbox.x1, &pbox.y0, &pbox.y1,
			&pbox.z0, &pbox.z1) != 6)
			return 15;
		center.x = (pbox.x0 + pbox.x1) * 0.5f;
		center.y = (pbox.y0 + pbox.y1) * 0.5f;
		center.z = (pbox.z0 + pbox.z1) * 0.5f;
		radius = 1.0e6f;
		memset(render.environment_surface_flags, 0xFF, BIT_VECTOR_SIZE_IN_BYTES(bsp->surfaces.count));
		leaf_surface_flags = calloc(BIT_VECTOR_SIZE_IN_LONGS(MAXIMUM_SURFACES_PER_STRUCTURE), sizeof(unsigned long));
		if (!leaf_surface_flags)
			return 15;
		found = structure_visibility_build_surfaces_traverse_leaf(target, &bsp->world_bounds, leaf_surface_flags,
			batch, 32767, &center, radius, &pbox, 0, 0, _intersection_spanning);
		printf("LEAFP %ld found=%d", target, found);
		for (k = 0; k < found; k++)
			printf(" %ld", batch[k]);
		printf("\n");
		memset(leaf_surface_flags, 0, BIT_VECTOR_SIZE_IN_BYTES(MAXIMUM_SURFACES_PER_STRUCTURE));
		found = structure_visibility_build_surfaces_traverse_node(0, &bsp->world_bounds, leaf_surface_flags,
			batch, 32767, &center, radius, &pbox, 0, 0, _intersection_spanning, 0);
		printf("NODEP found=%d\n", found);
		free(leaf_surface_flags);
		free(batch);
	}
	printf("STATUS passed\n");
	free(surfaces_a);
	free(surfaces_b);
	free(leaf_batch);
	free(union_flags);
	free(leaf_flags);
	free(snapshot);
	free(image);
	return 0;
}
