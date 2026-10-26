/* C4 fog/weather member-exact consumer driver.

Compiles the CE scenario fog/weather consumer bodies extracted verbatim from
submodules/halo-ce-universal/source/scenario/scenario.c by
tests/test_c4_parity_fog.py (placeholder marker CE_FUNCTIONS below), over a
synthetic BSP whose members are read from stdin. Output is one line per query
plus one line per fog region, compared by the Python test against an
independent oracle. */
#include <assert.h>
#include <stddef.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

typedef unsigned char byte;
typedef int boolean;
typedef float real;
typedef struct { real i, j, k; } real_vector3d;
typedef struct { real x, y, z; } real_point3d;
typedef struct { real_vector3d n; real d; } real_plane3d;
typedef struct { void *address; int count; } tag_block;
/* ILP32 layout of CE struct tag_reference (16 bytes): group_tag, name, name_length, index. */
typedef struct { unsigned int group_tag; unsigned int name; int name_length; int index; } tag_reference;
typedef unsigned short word;

#define TRUE 1
#define FALSE 0
#define NONE (-1)
#define SHORT_MAX 32767
#define FLAG(b) (1u << (b))
#define TEST_FLAG(flags, bit) (((flags)&(unsigned)FLAG(bit))!=0)
#define VALID_INDEX(index, count) (index>=0 && index<count)
#define TAG_BLOCK_GET_ELEMENT(b,i,t) ((t*)((byte*)(b)->address+(i)*sizeof(t)))
#define match_assert(file, line, condition) ((void)0)
#define match_vassert(file, line, condition, x) ((void)0)

struct location { short cluster_index; short leaf_index; };

struct fog_definition { unsigned long flags; real plane_distance; };

struct structure_cluster
{
	short unused0;
	short fog_reference;
	short background_sound_palette_index;
	byte unused1[2];
	short weather_palette_index;
	byte unused2[0x68 - 10];
};
typedef char structure_cluster_fog_offset_assert[offsetof(struct structure_cluster, fog_reference) == 0x02 ? 1 : -1];
typedef char structure_cluster_weather_offset_assert[offsetof(struct structure_cluster, weather_palette_index) == 0x08 ? 1 : -1];
typedef char structure_cluster_size_assert[sizeof(struct structure_cluster) == 0x68 ? 1 : -1];

struct structure_fog_plane
{
	short region_index;
	short runtime_material_type;
	real_plane3d plane;
	byte unused14[0xC];
};
typedef char structure_fog_plane_size_assert[sizeof(struct structure_fog_plane) == 0x20 ? 1 : -1];

struct structure_fog_region
{
	byte unused[0x24];
	short fog_palette_index;
	short weather_palette_index;
};
typedef char structure_fog_region_size_assert[sizeof(struct structure_fog_region) == 0x28 ? 1 : -1];
typedef char structure_fog_region_weather_offset_assert[offsetof(struct structure_fog_region, weather_palette_index) == 0x26 ? 1 : -1];

struct structure_fog_palette_entry
{
	byte unused[0x20];
	tag_reference fog;
	byte unused2[0x58];
};
typedef char structure_fog_palette_entry_size_assert[sizeof(struct structure_fog_palette_entry) == 0x88 ? 1 : -1];

struct structure_weather_palette_entry { byte unused[0x20]; };

struct structure_bsp
{
	tag_block clusters;
	tag_block fog_planes;
	tag_block fog_regions;
	tag_block fog_palette;
	long fog_unused[6];
	tag_block weather_palette;
	long weather_unused[6];
};

static struct structure_bsp bsp;
long scenario_fog_region_get_fog_index(short fog_region_index);
short scenario_get_fog_region_index(const struct location *location, const real_point3d *position);
static struct structure_bsp *global_structure_bsp_get(void) { return &bsp; }
static struct fog_definition fog_defs[64];
static int fog_def_count;
static struct fog_definition *fog_definition_get(long index)
{
	assert(index >= 0 && index < fog_def_count);
	return &fog_defs[index];
}

static real plane3d_distance_to_point(real_plane3d const *plane, real_point3d const *point)
{
	return (point->x * plane->n.i + point->y * plane->n.j + point->z * plane->n.k - plane->d);
}

/*CE_FUNCTIONS*/

/* stdin: fog defs, palette, regions, planes, weather count, clusters, queries, fill */
static struct structure_cluster cluster_store[64];
static struct structure_fog_plane plane_store[64];
static struct structure_fog_region region_store[64];
static struct structure_fog_palette_entry palette_store[64];
static struct structure_weather_palette_entry weather_store[64];

static int read_int(void) { int v; if (scanf("%d", &v) != 1) exit(3); return v; }

int main(void)
{
	int i, n, fill;
	int query_count;

	n = read_int();
	fog_def_count = n;
	for (i = 0; i < n; i++) { fog_defs[i].flags = (unsigned long)read_int(); fog_defs[i].plane_distance = (real)read_int(); }

	n = read_int();
	bsp.fog_palette.address = palette_store; bsp.fog_palette.count = n;
	for (i = 0; i < n; i++) { palette_store[i].fog.index = read_int(); }

	n = read_int();
	bsp.fog_regions.address = region_store; bsp.fog_regions.count = n;
	for (i = 0; i < n; i++) { region_store[i].fog_palette_index = (short)read_int(); region_store[i].weather_palette_index = (short)read_int(); }

	n = read_int();
	bsp.fog_planes.address = plane_store; bsp.fog_planes.count = n;
	for (i = 0; i < n; i++) {
		plane_store[i].region_index = (short)read_int();
		plane_store[i].plane.n.i = (real)read_int();
		plane_store[i].plane.n.j = (real)read_int();
		plane_store[i].plane.n.k = (real)read_int();
		plane_store[i].plane.d = (real)read_int();
	}

	n = read_int();
	bsp.weather_palette.address = weather_store; bsp.weather_palette.count = n;

	n = read_int();
	bsp.clusters.address = cluster_store; bsp.clusters.count = n;
	for (i = 0; i < n; i++) { cluster_store[i].fog_reference = (short)read_int(); cluster_store[i].weather_palette_index = (short)read_int(); }

	fill = read_int();
	if (fill) {
		memset(bsp.fog_unused, 0xA5, sizeof(bsp.fog_unused));
		memset(bsp.weather_unused, 0x5A, sizeof(bsp.weather_unused));
		for (i = 0; i < 64; i++) memset(region_store[i].unused, 0xA5, sizeof(region_store[i].unused));
		for (i = 0; i < 64; i++) memset(plane_store[i].unused14, 0x5A, sizeof(plane_store[i].unused14));
		for (i = 0; i < 64; i++) memset(palette_store[i].unused, 0x3C, sizeof(palette_store[i].unused));
	}

	query_count = read_int();
	for (i = 0; i < query_count; i++) {
		struct location location;
		real_point3d position;
		real_point3d *pos;
		short weather = NONE;
		boolean underwater;
		short region;
		location.cluster_index = (short)read_int();
		location.leaf_index = NONE;
		pos = NULL;
		if (read_int()) {
			position.x = (real)read_int(); position.y = (real)read_int(); position.z = (real)read_int();
			pos = &position;
		} else { read_int(); read_int(); read_int(); }
		region = scenario_get_fog_region_index(&location, pos);
		underwater = scenario_location_underwater(&location, pos, &weather);
		printf("q %d region=%d underwater=%d weather=%d\n", i, (int)region, (int)underwater, (int)weather);
	}
	for (i = 0; i < bsp.fog_regions.count; i++)
		printf("r %d fog=%ld\n", i, scenario_fog_region_get_fog_index((short)i));
	return 0;
}
