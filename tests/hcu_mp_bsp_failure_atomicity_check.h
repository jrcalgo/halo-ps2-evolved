/* Failure-atomic BSP replacement check included only by the MP wind fixture.
 * Damnation is a stock multiplayer package with one BSP, so the test temporarily
 * duplicates its real scenario reference in host memory to enter CE's genuine
 * scenario_switch_structure_bsp rollback path. No production tag or source is
 * modified. */
static void hcu_mp_assert_bsp_replacement_failure_atomicity(void)
{
	struct scenario_structure_bsp_reference references[2];
	struct scenario *scenario;
	struct structure_bsp *restored_structure;
	struct structure_cluster *restored_cluster;
	struct tag_block original_block;
	lifecycle_active_map_snapshot before;
	void *old_structure;
	void *old_collision;
	void *old_bsp3d;
	short old_index;

	assert(global_scenario && global_structure_bsp && global_collision_bsp &&
		global_bsp3d && lifecycle_service.mount.active &&
		lifecycle_service.source.active);
	scenario = global_scenario_get();
	original_block = scenario->structure_bsp_references;
	assert(original_block.count == 1 && original_block.address != NULL);
	memcpy(&references[0], original_block.address, sizeof(references[0]));
	references[1] = references[0];
	old_structure = global_structure_bsp;
	old_collision = global_collision_bsp;
	old_bsp3d = global_bsp3d;
	old_index = global_structure_bsp_index;
	assert(old_index == 0);
	lifecycle_snapshot_active_map(&before);

	/* Synthetic second reference only makes the single-BSP MP package exercise
	 * the same CE replacement transaction used by multi-BSP scenarios. The
	 * candidate load writes decoded B000 bytes into the actual CE BSP destination
	 * before the visitor aborts; CE must restore the prior BSP from the same MP
	 * package, leaving the published map and source owner intact. */
	scenario->structure_bsp_references.address = references;
	scenario->structure_bsp_references.count = 2;
	lifecycle_bsp_failure_tag = "B000";
	lifecycle_bsp_failure_armed = 1;
	lifecycle_bsp_failure_injected = 0;
	lifecycle_bsp_sink_writes = 0;
	lifecycle_bsp_destination_witness = 0;
	assert(!scenario_switch_structure_bsp(1));
	assert(lifecycle_bsp_failure_injected && !lifecycle_bsp_failure_armed &&
		lifecycle_bsp_sink_writes > 0 && lifecycle_bsp_destination_witness);
	assert(global_structure_bsp_index == old_index &&
		scenario_globals->structure_bsp_index == old_index &&
		global_structure_bsp == old_structure &&
		global_collision_bsp == old_collision && global_bsp3d == old_bsp3d);
	scenario->structure_bsp_references = original_block;
	lifecycle_assert_active_map_snapshot(&before);
	restored_structure = global_structure_bsp_get();
	assert(restored_structure == old_structure &&
		restored_structure->clusters.count == 12 &&
		restored_structure->weather_palette.count == 2);
	restored_cluster = (struct structure_cluster *)TAG_BLOCK_GET_ELEMENT(
		&restored_structure->clusters, 0, struct structure_cluster);
	assert(restored_cluster && restored_cluster->weather_palette_index == 0);
	puts("mp-bsp-atomicity injected candidate B000 write failure restored old BSP; CE globals, owner bytes/cursors, and source handle preserved");

	/* Retry the exact candidate after the one-shot fault, then return to BSP 0
	 * and unload. This proves the failure did not poison the transaction or
	 * leak the map owner/reader. */
	scenario->structure_bsp_references.address = references;
	scenario->structure_bsp_references.count = 2;
	assert(scenario_switch_structure_bsp(1));
	assert(global_structure_bsp_index == 1 &&
		scenario_globals->structure_bsp_index == 1 &&
		global_structure_bsp && global_collision_bsp && global_bsp3d &&
		lifecycle_service.mount.active && lifecycle_service.source.active &&
		lifecycle_service.section_scratch->used == 0);
	assert(scenario_switch_structure_bsp(0));
	assert(global_structure_bsp_index == 0 && global_structure_bsp &&
		global_collision_bsp && global_bsp3d);
	scenario->structure_bsp_references = original_block;
	scenario_unload();
	assert(global_scenario == NULL && global_structure_bsp == NULL &&
		global_collision_bsp == NULL && global_bsp3d == NULL &&
		!cache_file_globals.tags_loaded && global_tag_instances == NULL &&
		lifecycle_service.map_arena->used == 0 &&
		lifecycle_service.section_scratch->used == 0 &&
		!lifecycle_service.mount.active && !lifecycle_service.source.active &&
		lifecycle_service.source.reader.descriptor < 0);
	puts("mp-bsp-atomicity same-process replacement retry and owner/source unload passed");

	/* Restore the fixture's expected loaded-map state for the wind query. */
	assert(ps2_cache_preflight_map("levels\\test\\damnation\\damnation"));
	(void)cache_files_give_time_to_precache("levels\\test\\damnation\\damnation");
	assert(cache_files_give_time_to_precache("levels\\test\\damnation\\damnation"));
	assert(cache_files_precache_map_loaded("damnation"));
	loaded_datum = 0;
	assert(scenario_load("levels\\test\\damnation\\damnation"));
	assert(global_scenario && global_structure_bsp && global_collision_bsp &&
		global_bsp3d && lifecycle_service.mount.active &&
		lifecycle_service.source.active);
}
