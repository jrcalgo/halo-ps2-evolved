/* Host ILP32 semantic fixture; backing stores are not target RAM evidence. */
#include <assert.h>
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "cseries.h"
#include "math/real_math.h"
#include "scenario/scenario.h"
#include "scenario/wind.h"
#include "scenario/wind_definitions.h"
#include "structures/structure_bsp_definitions.h"
#include "tag_files/tag_groups.h"
#include "hcu_mp_weather_wind_golden.h"

struct hcu_mp_weather_palette_entry
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

typedef char hcu_mp_weather_palette_entry_size_assert[
	sizeof(struct hcu_mp_weather_palette_entry) == 0xF0 ? 1 : -1];

extern short global_structure_bsp_index;
extern struct structure_bsp *global_structure_bsp;

boolean game_engine_running(void) { return FALSE; }
unsigned long system_seconds(void) { return 1u; }

static void hcu_mp_weather_wind_assert_vector(
	unsigned map_id, unsigned palette_index, const char *mode,
	const real_vector3d *actual, const float expected[3])
{
	unsigned component;
	for (component = 0; component < 3; ++component)
	{
		if (!isfinite(actual->n[component]) ||
			fabsf(actual->n[component] - expected[component]) >= 0.00008f)
			fprintf(stderr, "mp-weather-wind mismatch map=%u palette=%u mode=%s "
				"actual=%.9g,%.9g,%.9g expected=%.9g,%.9g,%.9g "
				"global_seed=0x%08lx local_seed=0x%08lx\n",
				map_id, palette_index, mode, actual->i, actual->j, actual->k,
				expected[0], expected[1], expected[2], get_random_seed(),
				*get_global_local_random_seed_address());
		assert(isfinite(actual->n[component]));
		assert(fabsf(actual->n[component] - expected[component]) < 0.00008f);
	}
}

static const hcu_mp_weather_wind_palette_golden *hcu_mp_weather_wind_find(
	unsigned map_id, unsigned palette_index)
{
	unsigned index;
	for (index = 0; index < HCU_MP_WEATHER_WIND_PALETTE_GOLDEN_COUNT; ++index)
		if (hcu_mp_weather_wind_palette[index].map_id == map_id &&
			hcu_mp_weather_wind_palette[index].palette_index == palette_index)
			return &hcu_mp_weather_wind_palette[index];
	return NULL;
}

void hcu_test_mp_weather_wind(unsigned map_id)
{
	struct structure_bsp *bsp = global_structure_bsp_get();
	struct hcu_mp_weather_palette_entry *palette;
	unsigned palette_count = 0;
	unsigned cluster_count = 0;
	unsigned index;
	unsigned none_palette_count = 0;
	unsigned none_cluster_count = 0;
	unsigned valid_cluster_count = 0;
	unsigned long *global_seed;
	unsigned long *local_seed;
	real_point3d position = { 0.f, 0.f, 0.f };
	assert(bsp != NULL && global_structure_bsp == bsp);
	assert(map_id >= 101u && map_id < 114u);
	for (index = 0; index < HCU_MP_WEATHER_WIND_PALETTE_GOLDEN_COUNT; ++index)
		if (hcu_mp_weather_wind_palette[index].map_id == map_id)
			++palette_count;
	for (index = 0; index < HCU_MP_WEATHER_WIND_CLUSTER_GOLDEN_COUNT; ++index)
		if (hcu_mp_weather_wind_clusters[index].map_id == map_id)
			++cluster_count;
	assert(palette_count > 0u && palette_count <= 32u);
	assert(bsp->weather_palette.count == (long)palette_count);
	assert(bsp->clusters.count == (long)cluster_count);
	palette = (struct hcu_mp_weather_palette_entry *)bsp->weather_palette.address;
	assert(palette != NULL);
	for (index = 0; index < palette_count; ++index)
	{
		const hcu_mp_weather_wind_palette_golden *golden =
			hcu_mp_weather_wind_find(map_id, index);
		unsigned component;
		assert(golden != NULL);
		assert((uint32_t)palette[index].wind.group_tag == (uint32_t)WIND_TAG);
		assert((uint32_t)palette[index].wind.index == golden->datum);
		for (component = 0; component < 3; ++component)
			assert(palette[index].wind_direction.n[component] ==
				golden->direction[component]);
		assert(palette[index].wind_magnitude == golden->magnitude);
		if (golden->datum == 0xFFFFFFFFu)
			++none_palette_count;
	}
	{
		unsigned local_cluster = 0;
		for (index = 0; index < HCU_MP_WEATHER_WIND_CLUSTER_GOLDEN_COUNT; ++index)
		{
			if (hcu_mp_weather_wind_clusters[index].map_id == map_id)
			{
				const hcu_mp_weather_wind_cluster_golden *golden =
					&hcu_mp_weather_wind_clusters[index];
				struct structure_cluster *cluster;
				assert(golden->cluster_index == local_cluster);
				cluster = TAG_BLOCK_GET_ELEMENT(&bsp->clusters, local_cluster,
					struct structure_cluster);
				assert(cluster->weather_palette_index == golden->weather_palette_index);
				if (golden->weather_palette_index == NONE)
					++none_cluster_count;
				else
				{
					assert(golden->weather_palette_index >= 0 &&
						(unsigned)golden->weather_palette_index < palette_count);
					++valid_cluster_count;
				}
				++local_cluster;
			}
		}
	}

	/* Start from fixed seeds for each map/reload so the raw-source golden is
	 * independent of the order in which the thirteen maps are visited. */
	global_seed = get_global_random_seed_address();
	*global_seed = 0x13579BDFu;
	random_math_initialize();
	local_seed = get_global_local_random_seed_address();
	*local_seed = 0x89ABCDEFu;
	wind_initialize_for_new_map();
	*local_seed = 0x89ABCDEFu;
	wind_update();
	for (index = 0; index < palette_count; ++index)
	{
		const hcu_mp_weather_wind_palette_golden *golden =
			hcu_mp_weather_wind_find(map_id, index);
		real_vector3d normal, simple, damped;
		assert(golden != NULL);
		scenario_get_current_from_weather_palette(&position, &normal, 0,
			(short)index);
		scenario_get_current_from_weather_palette(&position, &simple,
			FLAG(_scenario_current_simple_bit), (short)index);
		scenario_get_current_from_weather_palette(&position, &damped,
			FLAG(_scenario_current_damped_bit), (short)index);
		hcu_mp_weather_wind_assert_vector(map_id, index, "normal",
			&normal, golden->normal);
		hcu_mp_weather_wind_assert_vector(map_id, index, "simple",
			&simple, golden->simple);
		hcu_mp_weather_wind_assert_vector(map_id, index, "damped",
			&damped, golden->damped);
	}
	{
		for (index = 0; index < HCU_MP_WEATHER_WIND_CLUSTER_GOLDEN_COUNT; ++index)
		{
			if (hcu_mp_weather_wind_clusters[index].map_id == map_id)
			{
				const hcu_mp_weather_wind_cluster_golden *golden =
					&hcu_mp_weather_wind_clusters[index];
				real_vector3d current;
				const float zero[3] = { 0.f, 0.f, 0.f };
				scenario_get_current_from_weather_palette(&position, &current, 0,
					(short)golden->weather_palette_index);
				if (golden->weather_palette_index == NONE)
				hcu_mp_weather_wind_assert_vector(map_id,
					(unsigned)golden->weather_palette_index, "cluster-none",
					&current, zero);
				else
				{
					const hcu_mp_weather_wind_palette_golden *entry =
						hcu_mp_weather_wind_find(map_id,
							(unsigned)golden->weather_palette_index);
					assert(entry != NULL);
					hcu_mp_weather_wind_assert_vector(map_id,
						(unsigned)golden->weather_palette_index, "cluster",
						&current, entry->normal);
				}
			}
		}
	}
	wind_dispose_from_old_map();
	random_math_dispose();
	assert(global_structure_bsp == bsp && global_structure_bsp_index == 0);
	printf("mp-weather-wind map=%u bsp=0 palettes=%u clusters=%u "
		"none_palette=%u none_clusters=%u valid_clusters=%u "
		"wind_update=passed query=passed reload_cycle=stable status=passed\n",
		map_id, palette_count, cluster_count, none_palette_count,
		none_cluster_count, valid_cluster_count);
}
