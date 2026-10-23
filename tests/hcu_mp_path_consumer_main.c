/* Native host harness for source-extracted CE path/BSP functions. The Python
 * test injects the unchanged function bodies from path.c and collision_bsp.c. */
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

typedef uint8_t byte;
typedef int boolean;
typedef float real;
typedef int32_t ce_long;
typedef struct { real x, y, z; } real_point3d;
typedef struct { real i, j, k; } real_vector3d;
struct tag_block { void *address; ce_long count; };
struct collision_surface { ce_long plane_designator, first_edge_index; byte flags, breakable; int16_t material; };
struct collision_edge { ce_long vertex_indices[2], edge_indices[2], surface_indices[2]; };
struct collision_vertex { real_point3d point; ce_long first_edge_index; };
struct collision_bsp { struct tag_block surfaces, edges, vertices; };
struct structure_bsp { struct tag_block collision_bsp, pathfinding_surfaces; };
struct path_edge {
	ce_long adjacent_surface_index;
	byte adjacent_pathfinding_surface, pad[3];
	real_point3d base_point;
	real_vector3d edge_vector;
};

enum { MAXIMUM_EDGES_PER_COLLISION_SURFACE = 8,
	MAXIMUM_PATH_EDGES_PER_COLLISION_SURFACE = 64,
	_error_silent = 0 };
#define NONE (-1)
#define TRUE 1
#define FALSE 0
#define VALID_INDEX(index, count) ((index) >= 0 && (index) < (count))
#define TAG_BLOCK_GET_ELEMENT(block, index, type) \
	((type *)((byte *)(block)->address + (index) * sizeof(type)))
#define match_assert(file, line, expression) assert(expression)

static boolean warned_about_collision_surface_edges;
static boolean warned_about_collision_surface_index;
static void error(short priority, const char *format, ...)
{
	(void)priority; (void)format;
}
static real_vector3d *vector_from_points3d(real_point3d const *from,
	real_point3d const *to, real_vector3d *vector)
{
	vector->i = to->x - from->x;
	vector->j = to->y - from->y;
	vector->k = to->z - from->z;
	return vector;
}

/* CE_PATH_AND_BSP_FUNCTIONS */

static unsigned long long fnv_byte(unsigned long long hash, unsigned char value)
{
	return (hash ^ value) * 1099511628211ULL;
}
static unsigned long long fnv_u32(unsigned long long hash, uint32_t value)
{
	int i;
	for (i = 0; i < 4; ++i) hash = fnv_byte(hash, (byte)(value >> (i * 8)));
	return hash;
}
static unsigned long long fnv_float(unsigned long long hash, real value)
{
	union { real f; uint32_t u; } bits;
	bits.f = value;
	return fnv_u32(hash, bits.u);
}

int main(int argc, char **argv)
{
	FILE *input;
	uint32_t surface_count, edge_count, vertex_count, path_count;
	struct collision_surface *surfaces;
	struct collision_edge *collision_edges;
	struct collision_vertex *vertices;
	byte *path_surfaces;
	uint32_t i, j, total_edges = 0, walkable = 0;
	uint64_t digest = 14695981039346656037ULL;
	uint64_t flag_digest = 14695981039346656037ULL;
	struct collision_bsp collision;
	struct structure_bsp structure;
	if (argc != 2 || !(input = fopen(argv[1], "rb"))) return 2;
	if (fread(&surface_count, 4, 1, input) != 1 ||
		fread(&edge_count, 4, 1, input) != 1 ||
		fread(&vertex_count, 4, 1, input) != 1 ||
		fread(&path_count, 4, 1, input) != 1) return 3;
	surfaces = calloc(surface_count, sizeof(*surfaces));
	collision_edges = calloc(edge_count, sizeof(*collision_edges));
	vertices = calloc(vertex_count, sizeof(*vertices));
	path_surfaces = calloc(path_count, 1);
	if (!surfaces || !collision_edges || !vertices || !path_surfaces) return 4;
	if (fread(surfaces, sizeof(*surfaces), surface_count, input) != surface_count ||
		fread(collision_edges, sizeof(*collision_edges), edge_count, input) != edge_count ||
		fread(vertices, sizeof(*vertices), vertex_count, input) != vertex_count ||
		fread(path_surfaces, 1, path_count, input) != path_count) return 5;
	fclose(input);
	collision.surfaces.address = surfaces; collision.surfaces.count = surface_count;
	collision.edges.address = collision_edges; collision.edges.count = edge_count;
	collision.vertices.address = vertices; collision.vertices.count = vertex_count;
	structure.collision_bsp.address = &collision; structure.collision_bsp.count = 1;
	structure.pathfinding_surfaces.address = path_surfaces;
	structure.pathfinding_surfaces.count = path_count;
	for (i = 0; i < surface_count; ++i)
	{
		struct path_edge found[MAXIMUM_PATH_EDGES_PER_COLLISION_SURFACE];
		short count;
		memset(found, 0, sizeof(found));
		count = build_path_edges_for_surface(&structure, i, found);
		if (i < path_count && (path_surfaces[i] & (1u << 6))) ++walkable;
		flag_digest = fnv_byte(flag_digest, i < path_count ? path_surfaces[i] : 0);
		digest = fnv_u32(digest, i);
		digest = fnv_u32(digest, (uint16_t)count);
		total_edges += (uint16_t)count;
		for (j = 0; j < (uint16_t)count; ++j)
		{
			struct path_edge const *edge = &found[j];
			digest = fnv_u32(digest, (uint32_t)edge->adjacent_surface_index);
			digest = fnv_byte(digest, edge->adjacent_pathfinding_surface);
			digest = fnv_float(digest, edge->base_point.x);
			digest = fnv_float(digest, edge->base_point.y);
			digest = fnv_float(digest, edge->base_point.z);
			digest = fnv_float(digest, edge->edge_vector.i);
			digest = fnv_float(digest, edge->edge_vector.j);
			digest = fnv_float(digest, edge->edge_vector.k);
		}
		if (i == 0 || i == surface_count / 2 || i + 1 == surface_count)
		{
			printf("sample surface=%u count=%u", i, (uint16_t)count);
			if (count > 0)
				printf(" adjacent=%d flags=%u base=%.9g,%.9g,%.9g vector=%.9g,%.9g,%.9g",
					found[0].adjacent_surface_index,
					found[0].adjacent_pathfinding_surface,
					found[0].base_point.x, found[0].base_point.y,
					found[0].base_point.z, found[0].edge_vector.i,
					found[0].edge_vector.j, found[0].edge_vector.k);
			printf("\n");
		}
	}
	printf("ce-path-consumer surfaces=%u path_flags=%u walkable=%u edges=%u flags_fnv=%016llx edges_fnv=%016llx status=passed\n",
		surface_count, path_count, walkable, total_edges,
		(unsigned long long)flag_digest, (unsigned long long)digest);
	free(path_surfaces); free(vertices); free(collision_edges); free(surfaces);
	return 0;
}
