/* Package-backed MP BSP integration of CE's real wind init/update/query path.
 * The Python runner generates the lifecycle/common fixture and expected
 * values from the matching raw retail map. */
#define uniform_cubic_spline_vector3d hcu_unused_inline_spline_vector3d
#include "hcu_mp_wind_lifecycle_generated.h"
#undef uniform_cubic_spline_vector3d

#include <math.h>
#include <stdint.h>

#include "math/real_math.h"
#include "scenario/wind.h"
#include "scenario/wind_definitions.h"
#include "structures/structure_bsp_definitions.h"

#include "hcu_mp_wind_expected.h"
#include "hcu_mp_bsp_failure_atomicity_check.h"

/* wind.c keeps this retail tag record translation-unit local. Mirror its
 * declared schema here only to compare relocated fields against raw bytes. */
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
typedef char hcu_mp_weather_palette_size_assert[
	sizeof(struct hcu_mp_weather_palette_entry) == 0xF0 ? 1 : -1];

static void assert_vector(const char *name, const real_vector3d *actual,
	const real expected[3])
{
	unsigned component;
	for (component = 0; component < 3; ++component) {
		if (!isfinite(actual->n[component])) {
			fprintf(stderr, "%s component %u nonfinite actual=%g expected=%g\n",
				name, component, actual->n[component], expected[component]);
		}
		assert(isfinite(actual->n[component]));
		assert(fabsf(actual->n[component] - expected[component]) < 0.00004f);
	}
}

void uniform_cubic_spline_vector3d(real_vector3d *result,
	real_vector3d const *f0, real_vector3d const *f1,
	real_vector3d const *f2, real_vector3d const *f3,
	real t0, real h, real t)
{
	hcu_unused_inline_spline_vector3d(result, f0, f1, f2, f3, t0, h, t);
}

boolean game_engine_running(void)
{
	return FALSE;
}

unsigned long system_seconds(void)
{
	return 1;
}

int main(int argc, char **argv)
{
	const char *scenario_name = "levels\\test\\damnation\\damnation";
	static unsigned char streaming_bytes[1572864u] __attribute__((aligned(64)));
	arena_t production_owner;
	arena_t production_scratch;
	arena_t streaming;
	struct structure_bsp *structure;
	struct hcu_mp_weather_palette_entry *palette;
	struct location location;
	real_point3d position = { 0.f, 0.f, 0.f };
	real_vector3d normal, simple, damped, none, repeated;
	unsigned index;
	unsigned long *global_seed;
	unsigned long *local_seed;

	assert(argc == 4);
	setvbuf(stdout, NULL, _IONBF, 0);
	assert(file_set_default_root(argv[1]));
	retail_ref_count = 1u;
	retail_offset[0] = (unsigned)strtoul(argv[2], NULL, 0);
	retail_size[0] = (unsigned)strtoul(argv[3], NULL, 0);
	assert(retail_size[0] > 0u && retail_size[0] <= sizeof bsp_cache);
	assert(ps2_animation_trace_bind(lifecycle_trace_events,
		LIFECYCLE_TRACE_CAPACITY));
	assert(ps2_animation_trace_bind_contexts(lifecycle_trace_contexts,
		LIFECYCLE_TRACE_CAPACITY));
	ps2_animation_trace_reset();

	arena_init(&streaming, "MP wind streaming", streaming_bytes,
		sizeof(streaming_bytes));
	arena_init(&production_owner, "MP wind package owner", streaming_bytes,
		1048576u);
	arena_init(&production_scratch, "MP wind section scratch",
		streaming_bytes + 1048576u, 524288u);
	lifecycle_layout.regions[MEM_LAYOUT_V2_STREAMING] = streaming;
	lifecycle_layout.regions[MEM_LAYOUT_V2_FRAME_SCRATCH] = production_scratch;
	assert(hcu_map_service_init_with_arenas(&lifecycle_service,
		&lifecycle_layout, argv[1], &production_owner,
		&production_scratch) == 0);
	assert(tag_validate_bind_claims_buffer(retail_claims_bytes,
		sizeof(retail_claims_bytes)));
	cache_files_initialize();
	scenario_globals = &globals_fixture;
	scenario_globals->structure_bsp_index = NONE;
	global_tag_instances = tag_instances;
	global_tag_count = 0;

	assert(ps2_cache_preflight_map(scenario_name));
	(void)cache_files_give_time_to_precache(scenario_name);
	assert(cache_files_give_time_to_precache(scenario_name));
	assert(cache_files_precache_map_loaded("damnation"));
	loaded_datum = 0;
	assert(scenario_load(scenario_name));
	assert(global_scenario && global_structure_bsp && global_collision_bsp &&
		global_bsp3d && cache_file_globals.tags_loaded &&
		lifecycle_service.mount.active && lifecycle_service.source.active);
	hcu_mp_assert_bsp_replacement_failure_atomicity();

	structure = global_structure_bsp_get();
	assert(structure->weather_palette.count == HCU_MP_WIND_PALETTE_COUNT);
	assert(structure->clusters.count == HCU_MP_WIND_CLUSTER_COUNT);
	palette = (struct hcu_mp_weather_palette_entry *)
		structure->weather_palette.address;
	assert(palette != NULL);
	for (index = 0; index < HCU_MP_WIND_PALETTE_COUNT; ++index) {
		assert((uint32_t)palette[index].wind.index ==
			HCU_MP_WIND_DATUMS[index]);
		assert((uint32_t)palette[index].wind.group_tag == (uint32_t)WIND_TAG);
		assert(palette[index].wind_direction.i ==
			HCU_MP_WIND_DIRECTIONS[index][0]);
		assert(palette[index].wind_direction.j ==
			HCU_MP_WIND_DIRECTIONS[index][1]);
		assert(palette[index].wind_direction.k ==
			HCU_MP_WIND_DIRECTIONS[index][2]);
		assert(palette[index].wind_magnitude == HCU_MP_WIND_MAGNITUDES[index]);
	}
	assert(palette[1].wind.index == NONE);
	for (index = 0; index < (unsigned)structure->clusters.count; ++index) {
		struct structure_cluster *cluster = TAG_BLOCK_GET_ELEMENT(
			&structure->clusters, index, struct structure_cluster);
		assert(cluster->weather_palette_index == 0);
	}

	global_seed = get_global_random_seed_address();
	*global_seed = 0x13579BDFu;
	random_math_initialize();
	local_seed = get_global_local_random_seed_address();
	*local_seed = HCU_MP_WIND_LOCAL_SEED;
	wind_initialize_for_new_map();
	*local_seed = HCU_MP_WIND_LOCAL_SEED;
	wind_update();
	scenario_get_current_from_weather_palette(&position, &normal, 0, 0);
	scenario_get_current_from_weather_palette(&position, &simple,
		FLAG(_scenario_current_simple_bit), 0);
	scenario_get_current_from_weather_palette(&position, &damped,
		FLAG(_scenario_current_damped_bit), 0);
	scenario_get_current_from_weather_palette(&position, &none, 0, 1);
	assert_vector("simple", &simple, hcu_mp_wind_expected_simple);
	assert_vector("normal", &normal, hcu_mp_wind_expected_normal);
	assert_vector("damped", &damped, hcu_mp_wind_expected_damped);
	assert(none.i == 0.f && none.j == 0.f && none.k == 0.f);

	memset(&location, 0, sizeof(location));
	location.leaf_index = NONE;
	location.cluster_index = 0;
	location.bonus = 0;
	scenario_get_wind(&location, &position, &repeated, 0);
	assert_vector("scenario-wind", &repeated, hcu_mp_wind_expected_normal);

	wind_dispose_from_old_map();
	random_math_dispose();
	*global_seed = 0x13579BDFu;
	random_math_initialize();
	local_seed = get_global_local_random_seed_address();
	*local_seed = HCU_MP_WIND_LOCAL_SEED;
	wind_initialize_for_new_map();
	*local_seed = HCU_MP_WIND_LOCAL_SEED;
	wind_update();
	scenario_get_current_from_weather_palette(&position, &repeated, 0, 0);
	assert_vector("repeat", &repeated, hcu_mp_wind_expected_normal);
	wind_dispose_from_old_map();
	random_math_dispose();

	printf("ce-mp-wind map=damnation bsp=0 palette_count=%d cluster_count=%d "
		"wind_tag=%08x none_entry=zero current=%.8g,%.8g,%.8g "
		"repeat=stable relocated=passed status=passed\n",
		structure->weather_palette.count, structure->clusters.count,
		HCU_MP_WIND_DATUMS[0], normal.i, normal.j, normal.k);
	scenario_unload();
	assert(!global_scenario && !global_structure_bsp && !global_collision_bsp &&
		!global_bsp3d && !cache_file_globals.tags_loaded &&
		!lifecycle_service.mount.active && !lifecycle_service.source.active &&
		lifecycle_service.map_arena->used == 0u &&
		lifecycle_service.section_scratch->used == 0u);
	hcu_map_service_shutdown(&lifecycle_service);
	return 0;
}
