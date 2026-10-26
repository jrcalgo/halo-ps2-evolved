/* C4 structure_fog_plane.runtime_material_type consumer driver.
 *
 * collision_cluster_fog_plane() (physics/collisions.c, ~325-400) is spliced in
 * verbatim by tests/test_c4_parity_collision_fogplane.py at the CE_COLLISION_FOG_PLANE
 * marker. The CE gate on runtime_material_type (collisions.c:357) and the material
 * value handed to collision->material_type (collisions.c:626) are exercised through
 * this function's outputs. Host-only fakes replace the tag block accessors and the
 * fog definition lookup; the structure field layouts match structure_bsp_definitions.h. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

typedef unsigned char byte;
typedef int boolean;
typedef float real;
typedef unsigned short word;
enum { FALSE = 0, TRUE = 1, NONE = -1, SHORT_MAX = 0x7FFF, _error_silent = 0 };
#define TEST_FLAG(flags, bit) ((((unsigned long)(flags)) & (1UL << (bit))) != 0)
#define TAG_BLOCK_GET_ELEMENT(block, index, type) \
	((type *)((char *)(block)->address + (long)(index) * (long)sizeof(type)))

struct tag_block { long count; void *address; };
typedef struct { real i, j, k; } real_vector3d;
typedef struct { real_vector3d n; real d; } real_plane3d;
struct fog_definition { long id; };
struct structure_cluster { short sky_index; short fog_reference; };
struct structure_fog_plane { short region_index; short runtime_material_type; real_plane3d plane; byte unused14[0xC]; };
struct structure_fog_region { short fog_palette_index; byte pad[0x26]; };
struct structure_fog_palette_entry { struct { long index; } fog; };
struct structure_bsp {
	struct tag_block clusters;
	struct tag_block fog_planes;
	struct tag_block fog_regions;
	struct tag_block fog_palette;
};

static struct fog_definition fog_defs[4] = { {0}, {1}, {2}, {3} };
static struct fog_definition const *fog_definition_get(long index) { return &fog_defs[index]; }
static void error(long type, const char *format, ...) { (void)type; (void)format; }
static boolean warned_about_collision_fog;

/* CE_COLLISION_FOG_PLANE */

int main(int argc, char **argv)
{
	/* argv[1] = cluster fog_reference (hex), argv[2] = runtime_material_type,
	 * argv[3] = region_index (for the chain), argv[4] = fog palette index */
	struct structure_cluster clusters[1];
	struct structure_fog_plane planes[1];
	struct structure_fog_region regions[1];
	struct structure_fog_palette_entry palette[1];
	struct structure_bsp bsp;
	struct structure_fog_plane const *fog_plane = NULL;
	struct fog_definition const *fog = NULL;
	boolean found;

	if (argc != 5) return 2;
	clusters[0].sky_index = 0;
	clusters[0].fog_reference = (short)strtol(argv[1], NULL, 16);
	planes[0].region_index = (short)atoi(argv[3]);
	planes[0].runtime_material_type = (short)atoi(argv[2]);
	regions[0].fog_palette_index = (short)atoi(argv[4]);
	palette[0].fog.index = 2;
	bsp.clusters.count = 1; bsp.clusters.address = clusters;
	bsp.fog_planes.count = 1; bsp.fog_planes.address = planes;
	bsp.fog_regions.count = 1; bsp.fog_regions.address = regions;
	bsp.fog_palette.count = 1; bsp.fog_palette.address = palette;
	found = collision_cluster_fog_plane(&bsp, 0, &fog_plane, &fog);
	printf("fog_plane found=%d material=%d fog=%ld\n", found,
		fog_plane ? (int)fog_plane->runtime_material_type : -999,
		fog ? fog->id : -999L);
	return 0;
}
