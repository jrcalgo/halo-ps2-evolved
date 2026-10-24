/* Host ILP32 semantic fixture; these arrays are not target RAM evidence. */
#include "hcu_mp_lifecycle_generated.h"
#include "hcu_mp_pvs_golden.h"
#include "hcu_mp_sound_environment_golden.h"
#include "hcu_mp_sound_obstruction_golden.h"
#include "hcu_mp_nested_bsp_census.h"

void hcu_test_mp_sound_environment_query(unsigned map_id,
	unsigned bsp_index, unsigned cluster_index, int palette_index,
	long environment_tag, long background_tag, int fog_region,
	int environment_priority, real_point3d const *position);
void hcu_test_mp_weather_wind(unsigned map_id);

static void assert_mp_sound_environment_query(
	const hcu_mp_sound_environment_golden *golden)
{
	real_point3d position;
	assert(golden);
	memcpy(&position, golden->position, sizeof(position));
	hcu_test_mp_sound_environment_query(golden->map_id, golden->bsp_index,
		golden->cluster_index, golden->palette_index, golden->environment_tag,
		golden->background_tag, golden->fog_region,
		golden->environment_priority, &position);
}

static void assert_mp_sound_obstruction(unsigned map_id)
{
	const hcu_mp_sound_obstruction_golden *golden = NULL;
	struct structure_bsp *bsp = global_structure_bsp;
	unsigned index;
	for (index = 0; index < HCU_MP_SOUND_OBSTRUCTION_GOLDEN_COUNT; ++index)
		if (hcu_mp_sound_obstruction_goldens[index].map_id == map_id &&
			hcu_mp_sound_obstruction_goldens[index].bsp_index ==
				(unsigned)global_structure_bsp_index)
			golden = &hcu_mp_sound_obstruction_goldens[index];
	if (!golden)
		return;
	assert(map_id == 102u && bsp != NULL && global_structure_bsp == bsp);
	assert(golden->from_cluster != golden->to_cluster);
	assert(!BIT_VECTOR_TEST_FLAG(structure_bsp_get_cluster_pvs(
		bsp, (short)golden->from_cluster), golden->to_cluster));
	assert(structure_bsp_get_cluster_encoded_sound_distance(
		bsp, (short)golden->from_cluster,
		(short)golden->to_cluster) == golden->encoded_distance);
	{
		real obstruction = -1.0f;
		real occlusion = -1.0f;
		unsigned collision_calls = 99u;
		short collision_depth = global_current_collision_user_depth;
		long collision_user = global_current_collision_users[0];
		hcu_test_compute_sound_obstruction((short)golden->from_cluster,
			(short)golden->to_cluster, sound_obstruction_fixture_tick++,
			golden->distance, &obstruction, &occlusion, &collision_calls);
		assert(fabsf(obstruction - 0.6f) < 0.00001f);
		assert(fabsf(occlusion - golden->expected_occlusion) < 0.0001f);
		assert(collision_calls == 0u);
		assert(global_current_collision_user_depth == collision_depth &&
			global_current_collision_users[0] == collision_user);
		assert(global_structure_bsp == bsp && global_structure_bsp_index == 0);
		printf("mp-sound-obstruction map=%u bsp=%u from=%u to=%u encoded=%u "
			"distance=%.6g obstruction=%.6g occlusion=%.6g collision_calls=0 "
			"status=passed\n", map_id, golden->bsp_index,
			golden->from_cluster, golden->to_cluster,
			golden->encoded_distance, golden->distance,
			obstruction, occlusion);
	}
}

/* The collision-source oracle independently walks the raw BSP3D to select a
 * solid start leaf and proves the segment endpoint is outside. Exercise CE's
 * public location APIs on those exact points, including leaf->cluster mapping. */
static void assert_mp_location_queries(
	unsigned map_id,
	struct structure_bsp *bsp,
	const hcu_raw_collision_golden *golden)
{
	real_point3d start, outside;
	real_vector3d vector;
	struct location start_location, outside_location;
	short published_index = global_structure_bsp_index;
	short collision_depth = global_current_collision_user_depth;
	assert(bsp && global_bsp3d && golden);
	memcpy(&start, golden->start, sizeof start);
	memcpy(&vector, golden->vector, sizeof vector);
	outside.x = start.x + vector.i;
	outside.y = start.y + vector.j;
	outside.z = start.z + vector.k;
	assert(scenario_leaf_index_from_point(&start) == golden->leaf_index);
	scenario_location_from_point(&start_location, &start);
	assert(start_location.leaf_index == golden->leaf_index);
	assert(start_location.cluster_index == golden->cluster_index);
	assert(scenario_leaf_index_from_point(&outside) == NONE);
	scenario_location_from_point(&outside_location, &outside);
	assert(outside_location.leaf_index == NONE);
	assert(outside_location.cluster_index == NONE);
	assert(global_structure_bsp == bsp &&
		global_structure_bsp_index == published_index &&
		scenario_globals->structure_bsp_index == published_index);
	assert(global_current_collision_user_depth == collision_depth);
	printf("mp-location map=%u bsp=%u start_leaf=%d start_cluster=%d "
		"outside_leaf=-1 outside_cluster=-1 status=passed\n",
		map_id, (unsigned)published_index, (int)start_location.leaf_index,
		(int)start_location.cluster_index);
}

static void mp_query(unsigned map_id)
{
	const hcu_raw_collision_golden *g = NULL;
	struct collision_result hit;
	real_point3d start;
	real_vector3d vector;
	unsigned i;
	struct structure_bsp *bsp = global_structure_bsp;
	const hcu_mp_sound_environment_golden *sound_golden = NULL;
	static const unsigned long *const pvs_by_map[] = {
		mp_pvs_0, mp_pvs_1, mp_pvs_2, mp_pvs_3, mp_pvs_4,
		mp_pvs_5, mp_pvs_6, mp_pvs_7, mp_pvs_8, mp_pvs_9,
		mp_pvs_10, mp_pvs_11, mp_pvs_12
	};
	static const unsigned clusters_by_map[] = {
		MP_CLUSTERS_0, MP_CLUSTERS_1, MP_CLUSTERS_2, MP_CLUSTERS_3,
		MP_CLUSTERS_4, MP_CLUSTERS_5, MP_CLUSTERS_6, MP_CLUSTERS_7,
		MP_CLUSTERS_8, MP_CLUSTERS_9, MP_CLUSTERS_10, MP_CLUSTERS_11,
		MP_CLUSTERS_12
	};
	unsigned map_index;
	const unsigned long *raw_pvs;
	unsigned clusters;
	unsigned words;
	unsigned sound_index;
	assert(map_id >= 101u && map_id < 101u + 13u);
	hcu_mp_nested_bsp_census(map_id);
	hcu_test_mp_weather_wind(map_id);
	assert_relocated_fog_none_reference(global_structure_bsp, (int)map_id);
	map_index = map_id - 101u;
	raw_pvs = pvs_by_map[map_index];
	clusters = clusters_by_map[map_index];
	words = (clusters + 31u) / 32u;
	for (i = 0; i < HCU_RAW_COLLISION_GOLDEN_COUNT; ++i)
		if (hcu_raw_collision_goldens[i].map_id == map_id &&
			hcu_raw_collision_goldens[i].bsp_index ==
				(unsigned)global_structure_bsp_index)
			g = &hcu_raw_collision_goldens[i];
	assert(g);
	assert_mp_location_queries(map_id, bsp, g);
	if (map_id == 104u)
	{
		/* Prisoner has no usable PVS golden in this fixture; its collision
		 * directional and breakable topology is checked independently below. */
		const hcu_raw_collision_golden *hit_golden = NULL;
		const hcu_raw_collision_directional_golden *directional = NULL;
		const hcu_raw_collision_flagged_golden *breakable = NULL;
		struct collision_surface *surfaces;
		struct collision_result result;
		byte flags_before[sizeof(retail_breakable_surface_flags)];
		unsigned index;
		unsigned char *image_snapshot;
		size_t image_bytes;
		byte breakable_bit;
		assert(global_structure_bsp && global_collision_bsp && global_bsp3d);
		assert(global_structure_bsp_index == 0 && scenario_globals->structure_bsp_index == 0);
		retail_collision_map_id = 104;
		for (sound_index = 0;
			sound_index < HCU_MP_SOUND_ENVIRONMENT_GOLDEN_COUNT; ++sound_index)
			if (hcu_mp_sound_environment_goldens[sound_index].map_id == 104u &&
				hcu_mp_sound_environment_goldens[sound_index].bsp_index == 0u)
			{
				sound_golden = &hcu_mp_sound_environment_goldens[sound_index];
				break;
			}
		if (sound_golden)
			assert_mp_sound_environment_query(sound_golden);
		for (index = 0; index < HCU_RAW_COLLISION_GOLDEN_COUNT; ++index)
			if (hcu_raw_collision_goldens[index].map_id == 104)
				hit_golden = &hcu_raw_collision_goldens[index];
		for (index = 0; index < HCU_RAW_COLLISION_DIRECTIONAL_GOLDEN_COUNT; ++index)
			if (hcu_raw_collision_directional_goldens[index].map_id == 104)
				directional = &hcu_raw_collision_directional_goldens[index];
		for (index = 0; index < HCU_RAW_COLLISION_FLAGGED_GOLDEN_COUNT; ++index)
			if (hcu_raw_collision_flagged_goldens[index].map_id == 104 &&
				hcu_raw_collision_flagged_goldens[index].kind == 2)
				breakable = &hcu_raw_collision_flagged_goldens[index];
		assert(hit_golden && directional && breakable);
		assert(breakable->surface_group_count == 2);
		assert(breakable->surface_group[0] == 457 &&
			breakable->surface_group[1] == 2835);
		assert(breakable->breakable_index == 1);
		surfaces = (struct collision_surface *)global_collision_bsp->surfaces.address;
		for (index = 0; index < (unsigned)breakable->surface_group_count; ++index)
		{
			struct collision_surface const *surface =
				&surfaces[breakable->surface_group[index]];
			/* CE's collision_surface_flags enum is private to collision_bsp.c;
			 * raw and tagged CE records identify the breakable flag as bit 3. */
			assert(surface->flags & (1u << 3));
			assert(surface->breakable_surface_index == breakable->breakable_index);
			assert(surface->material_index == breakable->material_index);
		}
		{
			real_point3d start = {hit_golden->start[0], hit_golden->start[1],
				hit_golden->start[2]};
			real_vector3d vector = {hit_golden->vector[0], hit_golden->vector[1],
				hit_golden->vector[2]};
			memset(&result, 0xCD, sizeof(result));
			if (!collision_test_vector(FLAG(_collision_test_structure_bit) |
				FLAG(_collision_test_front_facing_surfaces_bit), &start, &vector,
				NONE, &result))
			{
				printf("prisoner-hit-miss surface=%d plane=%d start=(%.9g,%.9g,%.9g) "
					"vector=(%.9g,%.9g,%.9g) start_leaf=%ld end_leaf=%ld t=%.9g\n",
					hit_golden->surface_index, hit_golden->plane_designator,
					start.x, start.y, start.z, vector.i, vector.j, vector.k,
					result.start_location.leaf_index,
					result.location.leaf_index, result.t);
				assert(0 && "source-backed Prisoner hit is not selected by CE");
			}
			assert(result.type == _collision_result_structure &&
				result.surface_index == hit_golden->surface_index &&
				result.material_index == hit_golden->material_index &&
				result.plane_designator == hit_golden->plane_designator &&
				result.start_location.leaf_index == hit_golden->leaf_index &&
				result.location.leaf_index == hit_golden->location_leaf_index &&
				fabsf(result.t - hit_golden->t) < 0.0002f);
		}
		{
			real_point3d start = {directional->miss_start[0],
				directional->miss_start[1], directional->miss_start[2]};
			real_vector3d vector = {directional->miss_vector[0],
				directional->miss_vector[1], directional->miss_vector[2]};
			memset(&result, 0xCD, sizeof(result));
			assert(!collision_test_vector(FLAG(_collision_test_structure_bit) |
				FLAG(_collision_test_front_facing_surfaces_bit), &start, &vector,
				NONE, &result));
			assert(result.type == NONE && result.t == 1.0f);
			assert(result.start_location.leaf_index == directional->miss_leaf &&
				result.location.leaf_index == directional->miss_leaf);
			assert(result.start_location.cluster_index == directional->miss_cluster &&
				result.location.cluster_index == directional->miss_cluster);
		}
		{
			real_point3d start = {directional->reverse_start[0],
				directional->reverse_start[1], directional->reverse_start[2]};
			real_vector3d vector = {directional->reverse_vector[0],
				directional->reverse_vector[1], directional->reverse_vector[2]};
			memset(&result, 0xCD, sizeof(result));
			assert(!collision_test_vector(FLAG(_collision_test_structure_bit) |
				FLAG(_collision_test_front_facing_surfaces_bit), &start, &vector,
				NONE, &result));
			memset(&result, 0xCD, sizeof(result));
			assert(collision_test_vector(FLAG(_collision_test_structure_bit) |
				FLAG(_collision_test_back_facing_surfaces_bit), &start, &vector,
				NONE, &result));
			assert(result.surface_index == directional->reverse_surface &&
				fabsf(result.t - directional->reverse_t) < 0.0002f);
		}
		image_bytes = (size_t)((struct scenario_structure_bsp_reference *)
			global_scenario->structure_bsp_references.address)[0].file_size;
		image_snapshot = (unsigned char *)malloc(image_bytes);
		assert(image_snapshot != NULL);
		memcpy(image_snapshot, global_structure_bsp, image_bytes);
		memcpy(flags_before, retail_breakable_surface_flags, sizeof(flags_before));
		breakable_bit = (byte)(1u << (breakable->breakable_index & 7));
		assert((flags_before[breakable->breakable_index >> 3] & breakable_bit) == 0);
		retail_breakable_surface_flags[breakable->breakable_index >> 3] |= breakable_bit;
		{
			real_point3d start = {breakable->start[0], breakable->start[1],
				breakable->start[2]};
			real_vector3d vector = {breakable->vector[0], breakable->vector[1],
				breakable->vector[2]};
			memset(&result, 0xCD, sizeof(result));
			assert(collision_test_vector(FLAG(_collision_test_structure_bit) |
				FLAG(_collision_test_front_facing_surfaces_bit), &start, &vector,
				NONE, &result));
			assert(result.surface_index == breakable->surface_index &&
				result.breakable_surface_index == breakable->breakable_index &&
				result.material_index == breakable->material_index &&
				result.flags == (byte)breakable->flags &&
				fabsf(result.t - breakable->t) < 0.0002f);
			retail_breakable_surface_flags[breakable->breakable_index >> 3] &=
				(byte)~breakable_bit;
			memset(&result, 0xCD, sizeof(result));
			assert(!collision_test_vector(FLAG(_collision_test_structure_bit) |
				FLAG(_collision_test_front_facing_surfaces_bit), &start, &vector,
				NONE, &result));
			assert(result.type == NONE && result.t == 1.0f);
			memcpy(retail_breakable_surface_flags, flags_before, sizeof(flags_before));
			memset(&result, 0xCD, sizeof(result));
			assert(!collision_test_vector(FLAG(_collision_test_structure_bit) |
				FLAG(_collision_test_front_facing_surfaces_bit), &start, &vector,
				NONE, &result));
			assert(result.type == NONE && result.t == 1.0f);
		}
		assert(memcmp(retail_breakable_surface_flags, flags_before,
			sizeof(flags_before)) == 0);
		assert(memcmp(image_snapshot, global_structure_bsp, image_bytes) == 0);
		assert(global_structure_bsp_index == 0 &&
			global_structure_bsp == bsp && global_collision_bsp == bsp->collision_bsp.address &&
			forbidden_object_adapter_calls == 0);
		free(image_snapshot);
		printf("collision-directional-golden map=104 miss-leaf=%d cluster=%d status=passed\n",
			directional->miss_leaf, directional->miss_cluster);
		printf("collision-breakable-group map=104 surfaces=%d,%d selected=%d index=%d status=passed\n",
			breakable->surface_group[0], breakable->surface_group[1],
			breakable->surface_index, breakable->breakable_index);
		return;
	}
	assert(bsp && global_collision_bsp && global_bsp3d);
	assert((unsigned)bsp->clusters.count == clusters);
	/* The generated raw-BSP oracle binds the CE listener query to the real
	 * fog-free palette candidate for this retail multiplayer map. */
	for (sound_index = 0;
		sound_index < HCU_MP_SOUND_ENVIRONMENT_GOLDEN_COUNT; ++sound_index)
		if (hcu_mp_sound_environment_goldens[sound_index].map_id == map_id &&
			hcu_mp_sound_environment_goldens[sound_index].bsp_index ==
				(unsigned)global_structure_bsp_index)
		{
			sound_golden = &hcu_mp_sound_environment_goldens[sound_index];
			break;
		}
	if (sound_golden)
		assert_mp_sound_environment_query(sound_golden);
	/* Beaver Creek supplies a retail fog-plane/region/tag chain. The helper
	 * is inert for maps without a generated source oracle row. */
	assert_relocated_fog_plane(bsp, (int)map_id);
	assert_mp_sound_obstruction(map_id);
	memcpy(&start, g->start, sizeof start);
	memcpy(&vector, g->vector, sizeof vector);
	memset(&hit, 0, sizeof hit);
	assert(collision_test_vector(FLAG(_collision_test_structure_bit) |
		FLAG(_collision_test_front_facing_surfaces_bit), &start, &vector,
		NONE, &hit));
	assert(hit.type == _collision_result_structure);
	assert(hit.surface_index == g->surface_index);
	assert(hit.material_index == g->material_index);
	assert(hit.material_type == g->material_type);
	assert(hit.plane_designator == g->plane_designator);
	assert(hit.start_location.leaf_index == g->leaf_index);
	assert(hit.location.leaf_index == g->location_leaf_index);
	assert(fabsf(hit.t - g->t) < 0.0002f);
	for (i = 0; i < (unsigned)bsp->clusters.count; ++i) {
		unsigned long *pvs = structure_bsp_get_cluster_pvs(bsp, (short)i);
		assert(pvs && BIT_VECTOR_TEST_FLAG(pvs, i));
		assert(memcmp(pvs, raw_pvs + i * words, words * sizeof(*pvs)) == 0);
	}
	assert(forbidden_object_adapter_calls == 0);
}

int main(int argc, char **argv)
{
	const char *names[] = {"longest", "bloodgulch", "beavercreek",
		"prisoner", "boardingaction", "carousel", "chillout", "damnation",
		"hangemhigh", "putput", "ratrace", "sidewinder", "wizard"};
	unsigned map, cycle;
	arena_t streaming;
	arena_t host_owner;
	arena_t host_scratch;
	arena_t bad_scratch;
	arena_t bad_owner;
	hcu_map_service rejected_service;
	static unsigned char streaming_bytes[1572864u] __attribute__((aligned(64)));
	assert(argc == 2);
	setvbuf(stdout, NULL, _IONBF, 0);
	assert(file_set_default_root(argv[1]));
	arena_init(&streaming, "host semantic streaming", streaming_bytes,
		sizeof streaming_bytes);
	arena_init(&host_owner, "host map owner", streaming_bytes,
		1048576u);
	arena_init(&host_scratch, "host section scratch",
		streaming_bytes + 1048576u, 524288u);
	lifecycle_layout.regions[MEM_LAYOUT_V2_STREAMING] = streaming;
	lifecycle_layout.regions[MEM_LAYOUT_V2_FRAME_SCRATCH] = host_scratch;
	arena_init(&bad_scratch, "overlap section scratch",
		streaming_bytes + 524288u, 524288u);
	assert(hcu_map_service_init_with_arenas(&rejected_service,
		&lifecycle_layout, argv[1], &host_owner, &bad_scratch) == -1);
	arena_init(&bad_scratch, "outside section scratch",
		streaming_bytes + sizeof streaming_bytes - 16u, 64u);
	assert(hcu_map_service_init_with_arenas(&rejected_service,
		&lifecycle_layout, argv[1], &host_owner, &bad_scratch) == -1);
	arena_init(&bad_owner, "outside map owner",
		streaming_bytes + sizeof streaming_bytes - 16u, 64u);
	assert(hcu_map_service_init_with_arenas(&rejected_service,
		&lifecycle_layout, argv[1], &bad_owner, &host_scratch) == -1);
	/* This host fixture uses disjoint map-owner and section-scratch child arenas;
	 * neither is evidence that the target memory budget fits all stock maps. */
	assert(hcu_map_service_init_with_arenas(&lifecycle_service, &lifecycle_layout,
		argv[1], &host_owner, &host_scratch) == 0);
	assert(sizeof tag_cache + sizeof bsp_cache == 24u * 1024u * 1024u);
	assert(tag_validate_claims_buffer_size() <= sizeof retail_claims_bytes);
	assert(tag_validate_bind_claims_buffer(retail_claims_bytes, sizeof retail_claims_bytes));
	cache_files_initialize();
	scenario_globals = &globals_fixture;
	scenario_globals->structure_bsp_index = NONE;
	for (map = 0; map < 13; ++map) {
		char scenario[128];
		snprintf(scenario, sizeof scenario, "levels\\test\\%s\\%s", names[map], names[map]);
		for (cycle = 0; cycle < 2; ++cycle) {
			lifecycle_active_map_snapshot snapshot;
			assert(ps2_cache_preflight_map(scenario));
			(void)cache_files_give_time_to_precache(scenario);
			assert(cache_files_give_time_to_precache(scenario));
			assert(cache_files_precache_map_loaded(names[map]));
			loaded_datum = 0;
			if (cycle == 0) {
				/* Exercise every MP package's real late-CBSP failure boundary: the
				 * injected wrapper writes a nonzero decoded prefix into the CE BSP
				 * destination, then fails. CE must leave no candidate globals or
				 * parent map owner published; the same process must preflight and
				 * load this map again before the parity queries below. */
				lifecycle_bsp_failure_tag = "B000";
				lifecycle_bsp_failure_armed = 1;
				lifecycle_bsp_failure_injected = 0;
				lifecycle_bsp_sink_writes = 0;
				lifecycle_bsp_destination_witness = 0;
				assert(!scenario_load(scenario));
				assert(lifecycle_bsp_failure_injected &&
					!lifecycle_bsp_failure_armed &&
					lifecycle_bsp_sink_writes > 0 &&
					lifecycle_bsp_destination_witness);
				assert(!global_scenario && !global_structure_bsp &&
					!global_collision_bsp && !global_bsp3d &&
					!global_game_globals && global_scenario_index == NONE &&
					global_structure_bsp_index == NONE &&
					scenario_globals->structure_bsp_index == NONE);
				assert(!cache_file_globals.tags_loaded &&
					!cache_file_globals.tag_header && !global_tag_instances &&
					global_tag_count == 0);
				assert(!lifecycle_service.mount.active &&
					!lifecycle_service.source.active &&
					lifecycle_service.source.reader.descriptor < 0 &&
					lifecycle_service.map_arena->used == 0 &&
					lifecycle_service.section_scratch->used == 0);
				assert(ps2_cache_preflight_map(scenario));
				(void)cache_files_give_time_to_precache(scenario);
				assert(cache_files_give_time_to_precache(scenario));
				assert(cache_files_precache_map_loaded(names[map]));
				printf("mp-capacity late-B000-failure unpublished-and-retry map=%s cycle=%u\n",
					names[map], cycle);
			}
			assert(scenario_load(scenario));
			assert(global_structure_bsp_index == 0);
			if (map == 1) {
				/* Bind the source-derived player-PVS golden to this MP map; this
				 * semantic host fixture has a larger BSP array than the EE budget. */
				retail_collision_map_id = 102;
				retail_size[0] = (unsigned)sizeof bsp_cache;
				assert_relocated_player_pvs_aggregation();
			}
			mp_query(101 + map);
			lifecycle_snapshot_active_map(&snapshot);
			assert(!ps2_cache_preflight_map("levels\\a30\\a30"));
			lifecycle_assert_active_map_snapshot(&snapshot);
			assert(lifecycle_service.map_arena->used <= host_owner.cap);
			assert(lifecycle_service.section_scratch->used == 0);
			printf("mp-host-map map=%s cycle=%u tag_cap=%u bsp_cap=%u owner_used=%u owner_high=%u owner_cap=%u scratch_high=%u scratch_cap=%u claims_cap=%u\n",
				names[map], cycle, (unsigned)sizeof tag_cache, (unsigned)sizeof bsp_cache,
				(unsigned)lifecycle_service.map_arena->used,
				(unsigned)lifecycle_service.map_arena->high,
				(unsigned)host_owner.cap,
				(unsigned)lifecycle_service.section_scratch->high,
				(unsigned)sizeof retail_section_scratch_bytes,
				(unsigned)sizeof retail_claims_bytes);
			scenario_unload();
			assert(!global_scenario && !global_structure_bsp && !global_collision_bsp &&
				!global_bsp3d && !global_tag_instances && !cache_file_globals.tags_loaded);
			assert(!lifecycle_service.mount.active && !lifecycle_service.source.active &&
				lifecycle_service.map_arena->used == 0 &&
				lifecycle_service.section_scratch->used == 0);
		}
	}
	assert(host_scratch.high <= host_scratch.cap);
	assert((uintptr_t)host_owner.base + host_owner.cap <=
		(uintptr_t)host_scratch.base);
	hcu_map_service_shutdown(&lifecycle_service);
	puts("mp-host-collision 13-map CE hit/PVS/reload matrix passed; target capacity not tested");
	return 0;
}
