/* Exact production-capacity HCU map-service preflight failure fixture.
 * This is not a gameplay, mount, or collision-query test. */
#include "hcu_mp_target_preflight_lifecycle.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>

static unsigned char target_streaming_bytes[1572864u] __attribute__((aligned(64)));

static void assert_empty_ce_state(void)
{
	assert(global_scenario == NULL && global_scenario_index == NONE);
	assert(global_structure_bsp == NULL && global_collision_bsp == NULL &&
		global_bsp3d == NULL && global_game_globals == NULL &&
		global_structure_bsp_index == NONE);
	assert(!cache_file_globals.tags_loaded && cache_file_globals.tag_header == NULL);
	assert(global_tag_instances == NULL && global_tag_count == 0);
	assert(!lifecycle_service.mount.active && !lifecycle_service.source.active &&
		lifecycle_service.source.reader.descriptor < 0);
	assert(!lifecycle_service.preflight_ready && !lifecycle_service.reload_pending &&
		lifecycle_service.staged_entry == NULL && lifecycle_service.staged_map[0] == 0);
	assert(lifecycle_service.map_arena->used == 0 &&
		lifecycle_service.section_scratch->used == 0);
}

int main(int argc, char **argv)
{
	static const char *const names[] = {
		"beavercreek", "bloodgulch", "boardingaction", "carousel",
		"chillout", "damnation", "hangemhigh", "longest", "prisoner",
		"putput", "ratrace", "sidewinder", "wizard"
	};
	arena_t streaming;
	unsigned i, attempt;
	assert(argc == 2);
	setvbuf(stdout, NULL, _IONBF, 0);
	assert(file_set_default_root(argv[1]));
	assert(sizeof tag_cache == 2u * 1024u * 1024u);
	assert(sizeof bsp_cache == 4u * 1024u * 1024u);
	assert(sizeof retail_owner_bytes == 1024u * 1024u);
	assert(sizeof retail_section_scratch_bytes == 512u * 1024u);
	assert(sizeof retail_claims_bytes == 786432u);
	arena_init(&streaming, "production-capacity streaming",
		target_streaming_bytes, sizeof target_streaming_bytes);
	arena_init(&retail_owner, "production-capacity map owner",
		target_streaming_bytes, sizeof retail_owner_bytes);
	arena_init(&retail_section_scratch, "production-capacity section scratch",
		target_streaming_bytes + sizeof retail_owner_bytes,
		sizeof retail_section_scratch_bytes);
	lifecycle_layout.regions[MEM_LAYOUT_V2_STREAMING] = streaming;
	lifecycle_layout.regions[MEM_LAYOUT_V2_FRAME_SCRATCH] = retail_section_scratch;
	assert(hcu_map_service_init_with_arenas(&lifecycle_service,
		&lifecycle_layout, argv[1], &retail_owner,
		&retail_section_scratch) == 0);
	assert(tag_validate_claims_buffer_size() == sizeof retail_claims_bytes);
	assert(tag_validate_bind_claims_buffer(retail_claims_bytes,
		sizeof retail_claims_bytes));
	cache_files_initialize();
	scenario_globals = &globals_fixture;
	scenario_globals->structure_bsp_index = NONE;
	global_scenario = NULL;
	global_scenario_index = NONE;
	global_structure_bsp = NULL;
	global_collision_bsp = NULL;
	global_bsp3d = NULL;
	global_game_globals = NULL;
	global_structure_bsp_index = NONE;
	global_tag_instances = NULL;
	global_tag_count = 0;
	assert_empty_ce_state();
	for (i = 0; i < sizeof names / sizeof names[0]; ++i) {
		char scenario[128];
		snprintf(scenario, sizeof scenario, "levels\\test\\%s\\%s",
			names[i], names[i]);
		for (attempt = 0; attempt < 2; ++attempt) {
			unsigned long owner_high_before =
				(unsigned long)retail_owner.high;
			unsigned long scratch_high_before =
				(unsigned long)retail_section_scratch.high;
			assert(!ps2_cache_preflight_map(scenario));
			assert_empty_ce_state();
			assert(retail_owner.high >= owner_high_before &&
				retail_owner.high <= retail_owner.cap);
			assert(retail_section_scratch.high >= scratch_high_before &&
				retail_section_scratch.high <= retail_section_scratch.cap);
			assert(!cache_files_precache_map_loaded(names[i]));
			printf("mp-target-capacity-preflight map=%s attempt=%u "
				"result=reject expected=ctag-image-capacity owner_used=%lu "
				"owner_high=%lu owner_cap=%lu scratch_used=%lu "
				"scratch_high=%lu scratch_cap=%lu tags_published=0 bsp_published=0\n",
				names[i], attempt,
				(unsigned long)retail_owner.used,
				(unsigned long)retail_owner.high,
				(unsigned long)retail_owner.cap,
				(unsigned long)retail_section_scratch.used,
				(unsigned long)retail_section_scratch.high,
				(unsigned long)retail_section_scratch.cap);
		}
	}
	assert(retail_owner.high <= retail_owner.cap &&
		retail_section_scratch.high <= retail_section_scratch.cap);
	hcu_map_service_shutdown(&lifecycle_service);
	puts("mp-target-capacity-preflight 13-map x2 CTAG rejection/cleanup passed; no map loaded or queried");
	return 0;
}
