/* C4 ranges-b member-exact probes: structure_cluster_portal, structure_surface, structure_surface_reference,
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

struct leaf_portal
{
	long plane_index;
	long leaf_indices[2];
	struct tag_block vertices;
};

struct leaf_map
{
	struct tag_block portals;
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

/* CE_RB_FUNCTIONS */

/* ---- probe drivers: the verbatim CE bodies above run on the synthetic member values from argv ---- */

static int parse_real(const char *text, real *out) { return sscanf(text, "%f", out) == 1; }
static int parse_long(const char *text, long *out) { return sscanf(text, "%ld", out) == 1; }

static int run_sphere(int argc, char **argv)
{
	/* sphere <plane_index> <cx> <cy> <cz> <bounding_radius> <px> <py> <pz> <radius> <vcount> [x y z]... */
	struct structure_bsp bsp;
	struct structure_cluster_portal portal;
	struct collision_bsp collision;
	struct real_plane3d plane_storage[1];
	real_point3d vertices[MAXIMUM_VERTICES_PER_CLUSTER_PORTAL];
	long vcount;
	int i;
	int arg = 1;
	real radius;
	real_point3d point;
	boolean result;

	if (argc < 11) return 2;
	parse_long(argv[arg++], &portal.plane_index);
	parse_real(argv[arg++], &portal.centroid.x);
	parse_real(argv[arg++], &portal.centroid.y);
	parse_real(argv[arg++], &portal.centroid.z);
	parse_real(argv[arg++], &portal.bounding_radius);
	parse_real(argv[arg++], &point.x);
	parse_real(argv[arg++], &point.y);
	parse_real(argv[arg++], &point.z);
	parse_real(argv[arg++], &radius);
	parse_long(argv[arg++], &vcount);
	for (i = 0; i < vcount && i < MAXIMUM_VERTICES_PER_CLUSTER_PORTAL; i++)
	{
		parse_real(argv[arg++], &vertices[i].x);
		parse_real(argv[arg++], &vertices[i].y);
		parse_real(argv[arg++], &vertices[i].z);
	}
	portal.vertices.count = vcount;
	portal.vertices.address = vertices;
	plane_storage[0].n.i = 0.0f;
	plane_storage[0].n.j = 0.0f;
	plane_storage[0].n.k = 1.0f;
	plane_storage[0].d = 0.0f;
	collision.bsp3d.planes.count = 1;
	collision.bsp3d.planes.address = plane_storage;
	collision.bsp3d.nodes.count = 0;
	collision.bsp3d.nodes.address = NULL;
	memset(&bsp, 0, sizeof(bsp));
	bsp.collision_bsp.count = 1;
	bsp.collision_bsp.address = &collision;
	bsp.cluster_portals.count = 1;
	bsp.cluster_portals.address = &portal;
	global_structure_bsp_storage = &bsp;
	global_bsp3d_storage = &collision.bsp3d;
	result = sphere_intersects_cluster_portal(&bsp, 0, &point, radius);
	printf("SPHERE %d\n", result ? 1 : 0);
	return 0;
}

static int run_triangles(int argc, char **argv)
{
	/* triangles <surface_count> [w0 w1 w2]... <index_count> [surface_index]... */
	struct structure_surface surfaces[MAXIMUM_SURFACES_PER_PROBE];
	long surface_indices[MAXIMUM_SURFACES_PER_PROBE];
	short triangles[MAXIMUM_SURFACES_PER_PROBE * NUMBER_OF_VERTICES_PER_TRIANGLE];
	struct structure_bsp bsp;
	long surface_count, index_count, i;
	int arg = 1;
	if (argc < 2) return 2;
	parse_long(argv[arg++], &surface_count);
	for (i = 0; i < surface_count; i++)
	{
		long w;
		parse_long(argv[arg++], &w); surfaces[i].vertex_indices[0] = (word)w;
		parse_long(argv[arg++], &w); surfaces[i].vertex_indices[1] = (word)w;
		parse_long(argv[arg++], &w); surfaces[i].vertex_indices[2] = (word)w;
	}
	parse_long(argv[arg++], &index_count);
	for (i = 0; i < index_count; i++) parse_long(argv[arg++], &surface_indices[i]);
	memset(&bsp, 0, sizeof(bsp));
	bsp.surfaces.count = surface_count;
	bsp.surfaces.address = surfaces;
	global_structure_bsp_storage = &bsp;
	structure_render_dynamic_triangles_from_indices(index_count, surface_indices, triangles);
	printf("TRIANGLES");
	for (i = 0; i < index_count * NUMBER_OF_VERTICES_PER_TRIANGLE; i++) printf(" %d", (int)triangles[i]);
	printf("\n");
	return 0;
}

static int run_surface_reference(int argc, char **argv)
{
	/* surface_reference <bsp3d_node_index> <plane_index> <px> <py> <pz>
	 * Fixed synthetic leaf 0 spans reference 0 -> surface 0 (triangle in z=0 around the origin).
	 * bsp3d node 0 designates plane 0 (z=0), node 1 designates plane 1 (x=0). */
	struct structure_bsp bsp;
	struct collision_bsp collision;
	struct bsp3d_node nodes[2];
	struct real_plane3d planes[2];
	struct structure_surface_reference reference;
	struct structure_leaf leaf;
	struct structure_surface surface;
	struct structure_lightmap lightmap;
	struct structure_material material;
	static real_point3d material_vertices[3] = { { -1, -1, 0 }, { 1, -1, 0 }, { 0, 1, 0 } };
	real_point3d point;
	long node_index, plane_index, surface_index = -1;
	short lightmap_index = 0, material_index = 0;
	real s = 0, t = 0;
	boolean found;
	int arg = 1;
	if (argc < 6) return 2;
	parse_long(argv[arg++], &node_index);
	parse_long(argv[arg++], &plane_index);
	parse_real(argv[arg++], &point.x);
	parse_real(argv[arg++], &point.y);
	parse_real(argv[arg++], &point.z);
	memset(&bsp, 0, sizeof(bsp));
	memset(&collision, 0, sizeof(collision));
	nodes[0].plane_designator = 0; nodes[0].children[0] = NONE; nodes[0].children[1] = NONE;
	nodes[1].plane_designator = 1; nodes[1].children[0] = NONE; nodes[1].children[1] = NONE;
	planes[0].n.i = 0; planes[0].n.j = 0; planes[0].n.k = 1; planes[0].d = 0;
	planes[1].n.i = 1; planes[1].n.j = 0; planes[1].n.k = 0; planes[1].d = 0;
	collision.bsp3d.nodes.count = 2; collision.bsp3d.nodes.address = nodes;
	collision.bsp3d.planes.count = 2; collision.bsp3d.planes.address = planes;
	surface.vertex_indices[0] = 0; surface.vertex_indices[1] = 1; surface.vertex_indices[2] = 2;
	reference.surface_index = 0;
	reference.bsp3d_node_index = node_index;
	material.vertices.type = _rasterizer_vertex_type_environment_uncompressed;
	material.compressed_vertex_data.count = 3;
	material.compressed_vertex_data.address = material_vertices;
	lightmap.materials.count = 1;
	lightmap.materials.address = &material;
	leaf.bounds.x0 = leaf.bounds.x1 = leaf.bounds.y0 = leaf.bounds.y1 = leaf.bounds.z0 = leaf.bounds.z1 = 0;
	leaf.pad = 0;
	leaf.cluster_index = 0;
	leaf.surface_reference_count = 1;
	leaf.first_surface_reference_index = 0;
	bsp.collision_bsp.count = 1; bsp.collision_bsp.address = &collision;
	bsp.surface_references.count = 1; bsp.surface_references.address = &reference;
	bsp.surfaces.count = 1; bsp.surfaces.address = &surface;
	bsp.lightmaps.count = 1; bsp.lightmaps.address = &lightmap;
	bsp.leaves.count = 1; bsp.leaves.address = &leaf;
	global_structure_bsp_storage = &bsp;
	found = structure_render_surface_from_point_and_leaf(&point, 0, plane_index, &lightmap_index, &material_index, &surface_index, &s, &t);
	printf("SURFACE_REF found=%d surface=%ld\n", found ? 1 : 0, found ? surface_index : -1L);
	return 0;
}

static int run_sky(int argc, char **argv)
{
	/* sky <cluster_sky_index> ; leaf 0 in cluster 0; bsp3d_test_point returns leaf 0 */
	struct structure_bsp bsp;
	struct structure_leaf leaf;
	struct structure_cluster cluster;
	struct render_camera camera;
	long sky;
	if (argc < 2) return 2;
	parse_long(argv[1], &sky);
	memset(&bsp, 0, sizeof(bsp));
	memset(&leaf, 0, sizeof(leaf));
	cluster.sky_index = (short)sky;
	cluster.fog_reference = NONE;
	leaf.cluster_index = 0;
	bsp.clusters.count = 1; bsp.clusters.address = &cluster;
	bsp.leaves.count = 1; bsp.leaves.address = &leaf;
	global_structure_bsp_storage = &bsp;
	bsp.collision_bsp.count = 0;
	bsp3d_test_point_result = 0;
	last_scenario_sky_arg = -99;
	memset(&camera, 0, sizeof(camera));
	structure_visibility_find_camera(&camera);
	printf("SKY visible=%d model=%d scenario_arg=%ld\n", (int)render.visible_sky_index,
		(int)render.visible_sky_model, last_scenario_sky_arg);
	return 0;
}

static int run_fog(int argc, char **argv)
{
	/* fog <fog_reference> <region_count> <plane_region_index> <plane_distance> <px> <py> <pz> */
	struct structure_bsp bsp;
	struct structure_cluster cluster;
	struct structure_fog_plane fog_plane;
	struct structure_fog_region_stub region[4];
	struct location location;
	long fog_reference, region_count, plane_region;
	real_point3d position;
	real plane_distance;
	short result;
	if (argc < 8) return 2;
	parse_long(argv[1], &fog_reference);
	parse_long(argv[2], &region_count);
	parse_long(argv[3], &plane_region);
	parse_real(argv[4], &plane_distance);
	parse_real(argv[5], &position.x);
	parse_real(argv[6], &position.y);
	parse_real(argv[7], &position.z);
	memset(&bsp, 0, sizeof(bsp));
	memset(region, 0, sizeof(region));
	cluster.sky_index = NONE;
	cluster.fog_reference = (short)fog_reference;
	fog_plane.region_index = (short)plane_region;
	fog_plane.runtime_material_type = 0;
	fog_plane.plane.n.i = 0; fog_plane.plane.n.j = 0; fog_plane.plane.n.k = 1; fog_plane.plane.d = plane_distance;
	bsp.clusters.count = 1; bsp.clusters.address = &cluster;
	bsp.fog_planes.count = 1; bsp.fog_planes.address = &fog_plane;
	bsp.fog_regions.count = region_count; bsp.fog_regions.address = region;
	global_structure_bsp_storage = &bsp;
	location.cluster_index = 0;
	result = scenario_get_fog_region_index(&location, &position);
	printf("FOG region=%d\n", (int)result);
	return 0;
}

static int run_frustum(int argc, char **argv)
{
	/* frustum <wx0> <wx1> <wy0> <wy1> <wz0> <wz1> <bx0> <bx1> <by0> <by1> <bz0> <bz1>
	 * frustum world_planes are all inside (d = 1e9), so only the world-bounds rejection can fire first. */
	real vals[12];
	int i;
	short result;
	struct render_frustum frustum;
	real_rectangle3d bounds;
	if (argc < 13) return 2;
	for (i = 0; i < 12; i++) parse_real(argv[1 + i], &vals[i]);
	memset(&frustum, 0, sizeof(frustum));
	frustum.world_bounds.x0 = vals[0]; frustum.world_bounds.x1 = vals[1];
	frustum.world_bounds.y0 = vals[2]; frustum.world_bounds.y1 = vals[3];
	frustum.world_bounds.z0 = vals[4]; frustum.world_bounds.z1 = vals[5];
	for (i = 0; i < 4; i++)
	{
		frustum.world_planes[i].n.i = 0; frustum.world_planes[i].n.j = 0; frustum.world_planes[i].n.k = 0;
		frustum.world_planes[i].d = 1.0e9f;
	}
	bounds.x0 = vals[6]; bounds.x1 = vals[7];
	bounds.y0 = vals[8]; bounds.y1 = vals[9];
	bounds.z0 = vals[10]; bounds.z1 = vals[11];
	result = render_frustum_cube_visible(&frustum, &bounds, FALSE);
	printf("FRUSTUM %d\n", (int)result);
	return 0;
}

static int run_debug(int argc, char **argv)
{
	/* debug <plane_index> <leaf0> <leaf1> <vcount> [x y z]... */
	struct leaf_map map;
	struct leaf_portal portal;
	real_point3d vertices[MAXIMUM_VERTICES_PER_CLUSTER_PORTAL];
	long plane, l0, l1, vcount, i;
	int arg = 1;
	if (argc < 5) return 2;
	parse_long(argv[arg++], &plane);
	parse_long(argv[arg++], &l0);
	parse_long(argv[arg++], &l1);
	parse_long(argv[arg++], &vcount);
	for (i = 0; i < vcount; i++)
	{
		parse_real(argv[arg++], &vertices[i].x);
		parse_real(argv[arg++], &vertices[i].y);
		parse_real(argv[arg++], &vertices[i].z);
	}
	memset(&map, 0, sizeof(map));
	portal.plane_index = plane;
	portal.leaf_indices[0] = l0;
	portal.leaf_indices[1] = l1;
	portal.vertices.count = vcount;
	portal.vertices.address = vertices;
	map.portals.count = 1;
	map.portals.address = &portal;
	debug_sink_lines = 0;
	debug_sink_triangles = 0;
	render_debug_leaf_portal(&map, 0);
	printf("DEBUG lines=%d triangles=%d\n", debug_sink_lines, debug_sink_triangles);
	return 0;
}

int main(int argc, char **argv)
{
	if (argc < 2) return 2;
	if (!strcmp(argv[1], "sphere")) return run_sphere(argc - 1, argv + 1);
	if (!strcmp(argv[1], "triangles")) return run_triangles(argc - 1, argv + 1);
	if (!strcmp(argv[1], "surface_reference")) return run_surface_reference(argc - 1, argv + 1);
	if (!strcmp(argv[1], "sky")) return run_sky(argc - 1, argv + 1);
	if (!strcmp(argv[1], "fog")) return run_fog(argc - 1, argv + 1);
	if (!strcmp(argv[1], "frustum")) return run_frustum(argc - 1, argv + 1);
	if (!strcmp(argv[1], "debug")) return run_debug(argc - 1, argv + 1);
	return 2;
}
