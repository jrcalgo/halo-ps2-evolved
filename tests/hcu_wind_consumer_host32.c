/* A narrow host ILP32 integration fixture for the real CE wind routines.
 * The generated header is decoded from the original retail Xbox map. */
#include <assert.h>
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "cseries.h"
#define uniform_cubic_spline_vector3d hcu_unused_inline_spline_vector3d
#include "math/real_math.h"
#undef uniform_cubic_spline_vector3d
#include "math/geometry.h"
#include "objects/objects.h"
#include "scenario/scenario.h"
#include "scenario/wind.h"
#include "scenario/wind_definitions.h"
#include "structures/structure_bsp_definitions.h"
#include "tag_files/tag_groups.h"

/* cseries maps the standard allocation/string calls to debug wrappers. This
 * harness implements those wrappers, so use libc allocation in this TU. */
#undef malloc
#undef calloc
#undef realloc
#undef free

struct hcu_weather_palette_entry
{
	char name[32];
	struct tag_reference particle_system;
	word pad30;
	short runtime_particle_system_global_function_index;
	char particle_system_global_function_name[32];
	long particle_system_unused[11];
	struct tag_reference wind;
	real_vector3d wind_direction;
	real wind_magnitude;
	word padA0;
	short wind_global_function_index;
	char wind_global_function_name[32];
	long wind_unused[11];
};

typedef char hcu_weather_size_check[
	sizeof(struct hcu_weather_palette_entry) == 0xF0 ? 1 : -1];
typedef char hcu_weather_wind_offset_check[
	offsetof(struct hcu_weather_palette_entry, wind) == 0x80 ? 1 : -1];
typedef char hcu_weather_wind_index_offset_check[
	offsetof(struct hcu_weather_palette_entry, wind) +
	offsetof(struct tag_reference, index) == 0x8C ? 1 : -1];
typedef char hcu_weather_direction_offset_check[
	offsetof(struct hcu_weather_palette_entry, wind_direction) == 0x90 ? 1 : -1];
typedef char hcu_weather_magnitude_offset_check[
	offsetof(struct hcu_weather_palette_entry, wind_magnitude) == 0x9C ? 1 : -1];

#include "hcu_wind_raw_fixture.h"

struct hcu_wind_tag_fixture
{
	uint32_t datum;
	struct wind_definition definition;
};

static struct hcu_weather_palette_entry weather_palette[HCU_WIND_PALETTE_COUNT];
static struct hcu_wind_tag_fixture wind_tags[HCU_WIND_PALETTE_COUNT];
static struct structure_cluster *clusters;
static struct structure_bsp bsp_fixture;
struct structure_bsp *global_structure_bsp;
static unsigned long expected_global_seed = 0x13579BDFu;
static unsigned long expected_local_seed = HCU_WIND_LOCAL_SEED;
void release_assert_failed(const char *expression, const char *file,
	long line, boolean fatal)
{
	fprintf(stderr, "CE assert: %s at %s:%ld fatal=%d\n", expression,
		file, line, fatal);
	exit(2);
}

boolean game_engine_running(void)
{
	return FALSE;
}

void *debug_malloc(unsigned int size, boolean clear, const char *file,
	long line)
{
	void *result = clear ? calloc(1, size) : malloc(size);
	(void)file;
	(void)line;
	return result;
}

void debug_free(void *pointer, const char *file, long line)
{
	(void)file;
	(void)line;
	free(pointer);
}

unsigned long system_seconds(void)
{
	return 1;
}

unsigned long system_milliseconds(void)
{
	return 2;
}

void *tag_block_get_element_with_size(struct tag_block const *block,
	long index, long element_size)
{
	assert(block != NULL && index >= 0 && index < block->count);
	assert(element_size > 0 && block->address != NULL);
	return (byte *)block->address + (size_t)index * (size_t)element_size;
}

void *tag_get(long group_tag, long tag_index)
{
	unsigned index;
	assert((uint32_t)group_tag == (uint32_t)WIND_TAG);
	for (index = 0; index < HCU_WIND_PALETTE_COUNT; ++index)
	{
		if (wind_tags[index].datum == (uint32_t)tag_index)
			return &wind_tags[index].definition;
	}
	fprintf(stderr, "unexpected CE wind tag lookup: group=%08x datum=%08x\n",
		(uint32_t)group_tag, (uint32_t)tag_index);
	exit(3);
}

/* cseries.h redirects memset in the CE source to csmemset. */
void *csmemset(void *destination, long value, unsigned long bytes)
{
	unsigned char *out = destination;
	while (bytes--)
		*out++ = (unsigned char)value;
	return destination;
}

/* wind.c's macro-renamed header inline is the production spline body. Export
 * the external spelling used by that reconstructed translation unit through
 * this exact inline instead of duplicating its formula. */
void uniform_cubic_spline_vector3d(real_vector3d *result,
	real_vector3d const *f0, real_vector3d const *f1,
	real_vector3d const *f2, real_vector3d const *f3,
	real t0, real h, real t)
{
	hcu_unused_inline_spline_vector3d(result, f0, f1, f2, f3, t0, h, t);
}

static void prepare_fixture(void)
{
	unsigned index;
	clusters = calloc(HCU_WIND_CLUSTER_COUNT, sizeof(*clusters));
	assert(clusters != NULL);
	for (index = 0; index < HCU_WIND_PALETTE_COUNT; ++index)
	{
		weather_palette[index].wind.group_tag = WIND_TAG;
		weather_palette[index].wind.index = (long)HCU_WIND_DATUMS[index];
		weather_palette[index].wind_direction.i = HCU_WIND_DIRECTIONS[index][0];
		weather_palette[index].wind_direction.j = HCU_WIND_DIRECTIONS[index][1];
		weather_palette[index].wind_direction.k = HCU_WIND_DIRECTIONS[index][2];
		weather_palette[index].wind_magnitude = HCU_WIND_MAGNITUDES[index];
		wind_tags[index].datum = HCU_WIND_DATUMS[index];
		wind_tags[index].definition.velocity_lower_bound = HCU_WIND_DEFINITIONS[index][0];
		wind_tags[index].definition.velocity_upper_bound = HCU_WIND_DEFINITIONS[index][1];
		wind_tags[index].definition.variation_area.pitch = HCU_WIND_DEFINITIONS[index][2];
		wind_tags[index].definition.variation_area.yaw = HCU_WIND_DEFINITIONS[index][3];
		wind_tags[index].definition.local_variation_weight = HCU_WIND_DEFINITIONS[index][4];
		wind_tags[index].definition.local_variation_rate = HCU_WIND_DEFINITIONS[index][5];
		wind_tags[index].definition.damping = HCU_WIND_DEFINITIONS[index][6];
	}
	clusters[HCU_WIND_SELECTED_CLUSTER].fog_reference = NONE;
	clusters[HCU_WIND_SELECTED_CLUSTER].weather_palette_index =
		HCU_WIND_SELECTED_PALETTE;
	bsp_fixture.clusters.count = HCU_WIND_CLUSTER_COUNT;
	bsp_fixture.clusters.address = clusters;
	bsp_fixture.weather_palette.count = HCU_WIND_PALETTE_COUNT;
	bsp_fixture.weather_palette.address = weather_palette;
	global_structure_bsp = &bsp_fixture;
}

int main(void)
{
	struct location location;
	struct geosphere *sphere;
	real_point3d position = { 0.f, 0.f, 0.f };
	real_vector3d current, simple, damped, repeated;
	unsigned long *global_seed;
	unsigned long *local_seed;
	unsigned update;
	prepare_fixture();
	sphere = geosphere_new(16);
	assert(sphere != NULL && sphere->vertex_count == 1026);
	for (update = 0; update < (unsigned)sphere->vertex_count; ++update)
	{
		assert(fabsf(sphere->vertices[update].x -
			HCU_GEOSPHERE_DIRECTIONS[update][0]) < 0.000005f);
		assert(fabsf(sphere->vertices[update].y -
			HCU_GEOSPHERE_DIRECTIONS[update][1]) < 0.000005f);
		assert(fabsf(sphere->vertices[update].z -
			HCU_GEOSPHERE_DIRECTIONS[update][2]) < 0.000005f);
	}
	geosphere_dispose(sphere);
	global_seed = get_global_random_seed_address();
	*global_seed = expected_global_seed;
	random_math_initialize();
	local_seed = get_global_local_random_seed_address();
	*local_seed = expected_local_seed;
	wind_initialize_for_new_map();
	*local_seed = expected_local_seed;
	wind_update();
	location.leaf_index = NONE;
	location.cluster_index = HCU_WIND_SELECTED_CLUSTER;
	location.bonus = 0;
	scenario_get_wind(&location, &position, &current, 0);
	scenario_get_current_from_weather_palette(&position, &simple,
		FLAG(_scenario_current_simple_bit), HCU_WIND_SELECTED_PALETTE);
	scenario_get_current_from_weather_palette(&position, &damped,
		FLAG(_scenario_current_damped_bit), HCU_WIND_SELECTED_PALETTE);
	for (update = 0; update < 3; ++update)
	{
		assert(isfinite(current.n[update]));
		assert(fabsf(current.n[update] - hcu_wind_expected_normal[update]) < 0.00003f);
		assert(fabsf(simple.n[update] - hcu_wind_expected_simple[update]) < 0.00003f);
		assert(fabsf(damped.n[update] - hcu_wind_expected_damped[update]) < 0.00003f);
	}
	location.cluster_index = NONE;
	scenario_get_wind(&location, &position, &repeated, 0);
	assert(repeated.i == 0.f && repeated.j == 0.f && repeated.k == 0.f);
	location.cluster_index = HCU_WIND_SELECTED_CLUSTER;

	/* A full map wind reset with identical seeds must reproduce the vector. */
	wind_dispose_from_old_map();
	random_math_dispose();
	*global_seed = expected_global_seed;
	random_math_initialize();
	*local_seed = expected_local_seed;
	wind_initialize_for_new_map();
	*local_seed = expected_local_seed;
	wind_update();
	scenario_get_wind(&location, &position, &repeated, 0);
	assert(current.i == repeated.i && current.j == repeated.j &&
		current.k == repeated.k);
	printf("ce-wind map=a30 bsp=0 cluster=%d palette=%d datum=%08x "
		"vector=%.8g,%.8g,%.8g simple=%.8g,%.8g,%.8g "
		"damped=%.8g,%.8g,%.8g missing=zero repeat=stable status=passed\n",
		HCU_WIND_SELECTED_CLUSTER, HCU_WIND_SELECTED_PALETTE,
		HCU_WIND_DATUMS[HCU_WIND_SELECTED_PALETTE],
		current.i, current.j, current.k, simple.i, simple.j, simple.k,
		damped.i, damped.j, damped.k);
	wind_dispose_from_old_map();
	random_math_dispose();
	free(clusters);
	return 0;
}
