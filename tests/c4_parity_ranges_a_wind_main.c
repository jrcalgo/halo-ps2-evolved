/* C4 ranges-a member-exact driver for structure_weather_palette_entry.<unclassified@0x90>.

wind_update (submodules/halo-ce-universal/source/scenario/wind.c) and the euler/vector
conversions euler_angles2d_from_vector3d and vector3d_from_euler_angles2d
(source/math/real_math.c) are extracted verbatim by tests/test_c4_parity_ranges_a.py
(placeholder marker CE_FUNCTIONS). The consumed range is wind_direction (0x90..0x9b) and
wind_magnitude (0x9c); the structure layout below reproduces CE's offsets (asserted).

The random sequence is pinned: seed_random_range returns the fixed pattern PINNED_BITS in
call order, independent of the seed, so the output varies only with the synthetic palette
and definition bytes. arctangent, square_root, cosine and sine are the libm functions.

stdin: n_palette, per entry: wind_index dx dy dz magnitude; n_definitions, per definition:
  velocity_lower velocity_upper variation_yaw variation_pitch local_variation_weight local_variation_rate
stdout: 'w <index> <valid> <velocity> <vi> <vj> <vk>' for each palette entry.
*/
#include <math.h>
#include <stddef.h>
#include <stdio.h>
#include <stdlib.h>

typedef unsigned char byte;
typedef int boolean;
typedef float real;
typedef unsigned short word;
struct tag_block { void *address; long count; };
typedef struct tag_block tag_block;
typedef struct { real i, j, k; } real_vector3d;
typedef struct { real yaw, pitch; } real_euler_angles2d;
typedef struct { real x, y, z; } real_point3d;
typedef struct { unsigned int group_tag; unsigned int name; int name_length; int index; } tag_reference;

#define TRUE 1
#define FALSE 0
#define NONE (-1)
#define MIN(a,b) ((a)<(b)?(a):(b))
#define NUMBEROF(array) (sizeof(array) / sizeof(array[0]))
#define TAG_BLOCK_GET_ELEMENT(b,i,t) ((t*)((byte*)(b)->address+(i)*sizeof(t)))
#define match_assert(file, line, condition) \
	do { if (!(condition)) { printf("assert %d\n", (line)); exit(4); } } while (0)
#define arctangent(y, x) atan2f((y), (x))
#define square_root(x) sqrtf(x)
#define cosine(a) cosf(a)
#define sine(a) sinf(a)
#define _scenario_current_simple_bit 0
#define PIN(value, lower, upper) ((value) < (lower) ? (lower) : ((value) > (upper) ? (upper) : (value)))

struct structure_weather_palette_entry
{
	char name[32];
	tag_reference particle_system;
	word pad30;
	short runtime_particle_system_global_function_index;
	char particle_system_global_function_name[32];
	int particle_system_unused[11];
	tag_reference wind;
	real_vector3d wind_direction;
	real wind_magnitude;
	word padA0;
	short wind_global_function_index;
	char wind_global_function_name[32];
	int wind_unused[11];
};
typedef char palette_size_assert[sizeof(struct structure_weather_palette_entry) == 0xF0 ? 1 : -1];
typedef char palette_direction_offset_assert[offsetof(struct structure_weather_palette_entry, wind_direction) == 0x90 ? 1 : -1];
typedef char palette_magnitude_offset_assert[offsetof(struct structure_weather_palette_entry, wind_magnitude) == 0x9c ? 1 : -1];

struct wind_definition
{
	real velocity_lower_bound;
	real velocity_upper_bound;
	real_euler_angles2d variation_area;
	real local_variation_weight;
	real local_variation_rate;
	real damping;
	long unused[9];
};

struct wind_state
{
	boolean valid;
	real velocity_variance;
	real_euler_angles2d angular_variance;
	real velocity;
	real_vector3d velocity3d;
};

struct structure_bsp { tag_block weather_palette; };

static struct structure_bsp bsp_store;
static struct structure_bsp *global_structure_bsp_get(void) { return &bsp_store; }
static struct wind_definition definition_store[16];
static struct wind_definition *wind_definition_get(long index) { return &definition_store[index]; }

static struct
{
	boolean initialized;
	short count;
	struct wind_state wind_states[32];
	long time;
} wind_globals;

static const int PINNED_BITS[5] = { 1, 0, 1, 1, 0 };
static long pinned_index;
static unsigned long seed_word;
static unsigned long *get_global_local_random_seed_address(void) { return &seed_word; }
static short seed_random_range(unsigned long *seed, short lower_bound, short upper_bound)
{
	int bit;
	(void)seed; (void)lower_bound; (void)upper_bound;
	bit = PINNED_BITS[pinned_index % 5];
	pinned_index++;
	return (short)bit;
}

/*CE_FUNCTIONS*/

static tag_reference no_tag(int index) { tag_reference t = {0, 0, 0, 0}; t.index = index; return t; }

int main(void)
{
	long n, i;
	static struct structure_weather_palette_entry palette[32];

	if (scanf("%ld", &n) != 1) return 3;
	bsp_store.weather_palette.address = palette;
	bsp_store.weather_palette.count = n;
	for (i = 0; i < n; i++) {
		struct structure_weather_palette_entry *e = &palette[i];
		int index;
		if (scanf("%d %f %f %f %f", &index, &e->wind_direction.i, &e->wind_direction.j,
			&e->wind_direction.k, &e->wind_magnitude) != 5) return 3;
		e->wind = no_tag(index);
		e->wind_global_function_index = NONE;
	}
	if (scanf("%ld", &n) != 1) return 3;
	for (i = 0; i < n; i++) {
		struct wind_definition *d = &definition_store[i];
		if (scanf("%f %f %f %f %f %f", &d->velocity_lower_bound, &d->velocity_upper_bound,
			&d->variation_area.yaw, &d->variation_area.pitch,
			&d->local_variation_weight, &d->local_variation_rate) != 6) return 3;
	}
	wind_globals.initialized = TRUE;
	wind_update();
	for (i = 0; i < bsp_store.weather_palette.count && i < (long)NUMBEROF(wind_globals.wind_states); i++) {
		struct wind_state *s = &wind_globals.wind_states[i];
		printf("w %ld %d %.9g %.9g %.9g %.9g\n", i, (int)s->valid, s->velocity,
			s->velocity3d.i, s->velocity3d.j, s->velocity3d.k);
	}
	return 0;
}
