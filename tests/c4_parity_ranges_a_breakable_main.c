/* C4 ranges-a member-exact driver for structure_breakable_surface.<unclassified@0x0>.

Compiles breakable_surface_damage_area_of_effect and its extant and index-validity helpers,
extracted verbatim from submodules/halo-ce-universal/source/physics/breakable_surfaces.c by
tests/test_c4_parity_ranges_a.py (placeholder marker CE_FUNCTIONS). The consumed members are
centroid (0x0), bounding_radius (0xc) and collision_surface_index (0x10); unused[7] (0x14)
has no access.

The breakable surface queue is data-only: breakable_surface_get returns a vitality slot,
breakable_surface_flags_get returns the broken bit vector, breakable_surface_effect records
the call it is given, and network_coop_note_surface_broken is a no-op. The damage definition
lookup is a table. match_assert exits non-zero so a failed CE assertion is reported.

stdin: n_surfaces, per surface: cx cy cz radius collision_index; broken flags (n values 0/1);
  enabled (0/1); damage_lower damage_upper cutoff_radius; epicenter x y z.
stdout: 'effect <index> <collision_index>' per surface the damage breaks, in CE order.
*/
#include <stddef.h>
#include <stdio.h>
#include <stdlib.h>

typedef unsigned char byte;
typedef int boolean;
typedef float real;
typedef struct { real x, y, z; } real_point3d;
struct tag_block { void *address; long count; };
typedef struct tag_block tag_block;

#define TRUE 1
#define FALSE 0
#define NONE (-1)
#define LONG_BITS 32
#define LONG_BITS_BITS 5
#define MAXIMUM_BREAKABLE_SURFACES_PER_MAP 256
#define MAXIMUM_STRUCTURE_BSPS_PER_SCENARIO 0x10
#define DAMAGE_EFFECT_DEFINITION_TAG 0
#define TEST_FLAG(v, b) ((((unsigned long)(v)) >> (b)) & 1)
#define BIT_VECTOR_TEST_FLAG(bit_vector, bit) (TEST_FLAG((bit_vector)[(bit) >> LONG_BITS_BITS], ((bit) & (LONG_BITS - 1))))
#define BIT_VECTOR_SET_FLAG(bit_vector, bit, value) \
	((value) ? ((bit_vector)[(bit) >> LONG_BITS_BITS] |= (1L << ((bit) & (LONG_BITS - 1))))  \
		: ((bit_vector)[(bit) >> LONG_BITS_BITS] &= ~(1L << ((bit) & (LONG_BITS - 1)))))
#define TAG_BLOCK_GET_ELEMENT(b,i,t) ((t*)((byte*)(b)->address+(i)*sizeof(t)))
#define match_assert(file, line, condition) \
	do { if (!(condition)) { printf("assert %d\n", (line)); exit(4); } } while (0)
#define error(level, ...) ((void)0)
#define _error_silent 0

struct structure_breakable_surface
{
	real_point3d centroid;
	real bounding_radius;
	long collision_surface_index;
	long unused[7];
};
typedef char breakable_surface_index_offset_assert[offsetof(struct structure_breakable_surface, collision_surface_index) == 0x10 ? 1 : -1];

struct breakable_surface_datum { real vitality; };
struct damage_effect_definition { real cutoff_radius; struct { real damage_lower_bound, damage_upper_bound; } damage; };
struct damage_data { long definition_index; real_point3d epicenter; };
struct breakable_surface_globals { boolean enabled; };
struct structure_bsp { tag_block breakable_surfaces; };

static struct structure_bsp bsp_store;
static struct structure_bsp *global_structure_bsp_get(void) { return &bsp_store; }
static long global_structure_bsp_index = 0;
static struct breakable_surface_globals globals_store;
static struct breakable_surface_globals *globals = &globals_store;
static struct structure_breakable_surface surface_store[MAXIMUM_BREAKABLE_SURFACES_PER_MAP];
static struct breakable_surface_datum datum_store[MAXIMUM_BREAKABLE_SURFACES_PER_MAP];
static long flags_store[MAXIMUM_STRUCTURE_BSPS_PER_SCENARIO][MAXIMUM_BREAKABLE_SURFACES_PER_MAP / LONG_BITS];
static struct damage_effect_definition definition_store;
static struct damage_effect_definition *damage_effect_definition_get(long index)
{
	(void)index;
	return &definition_store;
}
static boolean tag_index_is_group(long index, long group) { (void)group; return index >= 0; }
static real distance_squared3d(real_point3d const *a, real_point3d const *b)
{
	real dx = a->x - b->x, dy = a->y - b->y, dz = a->z - b->z;
	return dx * dx + dy * dy + dz * dz;
}
static boolean point_in_sphere(real_point3d const *point, real_point3d const *center, real radius)
{
	return distance_squared3d(point, center) <= (radius * radius);
}
static struct breakable_surface_datum *breakable_surface_get(short index)
{
	return &datum_store[index];
}
static byte *breakable_surface_flags_get(void)
{
	return (byte *)flags_store[global_structure_bsp_index];
}
static void breakable_surface_effect(short index, struct damage_data const *damage, long collision_surface_index)
{
	(void)damage;
	printf("effect %d %ld\n", (int)index, collision_surface_index);
}
static void network_coop_note_surface_broken(short index, real_point3d const *epicenter)
{
	(void)index; (void)epicenter;
}

static int warned_about_breakable_surfaces;
static boolean breakable_surface_indices_valid(short breakable_surface_index);

/*CE_FUNCTIONS*/

int main(void)
{
	long n, i;
	int enabled;
	struct damage_data damage;
	struct structure_bsp *bsp = &bsp_store;

	if (scanf("%ld", &n) != 1) return 3;
	bsp->breakable_surfaces.address = surface_store;
	bsp->breakable_surfaces.count = n;
	for (i = 0; i < n; i++) {
		struct structure_breakable_surface *s = &surface_store[i];
		if (scanf("%f %f %f %f %ld", &s->centroid.x, &s->centroid.y, &s->centroid.z,
			&s->bounding_radius, &s->collision_surface_index) != 5) return 3;
	}
	for (i = 0; i < n; i++) {
		int broken;
		if (scanf("%d", &broken) != 1) return 3;
		/* CE flag set = extant (intact); a broken surface has its flag cleared */
		BIT_VECTOR_SET_FLAG(flags_store[0], i, !broken);
	}
	if (scanf("%d", &enabled) != 1) return 3;
	globals->enabled = (boolean)enabled;
	if (scanf("%f %f %f", &definition_store.damage.damage_lower_bound,
		&definition_store.damage.damage_upper_bound, &definition_store.cutoff_radius) != 3) return 3;
	damage.definition_index = 0;
	if (scanf("%f %f %f", &damage.epicenter.x, &damage.epicenter.y, &damage.epicenter.z) != 3) return 3;

	breakable_surface_damage_area_of_effect(&damage);
	return 0;
}
