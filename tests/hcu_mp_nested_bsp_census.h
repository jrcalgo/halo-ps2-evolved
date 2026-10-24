/* Post-load CE tag/BSP nested-block address and full-extent assertions.
 * Included only by the host MP capacity fixture; this is not EE RAM evidence. */
#ifndef HCU_MP_NESTED_BSP_CENSUS_H
#define HCU_MP_NESTED_BSP_CENSUS_H

struct hcu_census_structure_detail_object_data
{
	struct tag_block cells;
	struct tag_block detail_objects;
	struct tag_block counts;
	struct tag_block z_reference_vectors;
	byte valid;
	byte pad31[3];
	long unused34[3];
};

struct hcu_census_detail_object_cell
{
	short cell_x;
	short cell_y;
	short cell_z;
	short offset_z;
	unsigned long valid_layers;
	long start_index;
	long count_index;
	long unused14[3];
};

struct hcu_census_structure_cluster
{
	short sky_index;
	short fog_designator;
	short background_sound_palette_index;
	short sound_environment_palette_index;
	short weather_palette_index;
	short transition_structure_bsp_index;
	short first_runtime_decal_index;
	word runtime_decal_count;
	long unused[6];
	struct tag_block predicted_resources;
	struct tag_block subclusters;
	word first_lens_flare_marker_index;
	word lens_flare_marker_count;
	struct tag_block surface_indices;
	struct tag_block mirrors;
	struct tag_block portal_indices;
};

typedef char hcu_census_detail_root_is_ce_0x40[
	sizeof(struct hcu_census_structure_detail_object_data) == 0x40 ? 1 : -1];
typedef char hcu_census_detail_cell_is_ce_0x20[
	sizeof(struct hcu_census_detail_object_cell) == 0x20 ? 1 : -1];
typedef char hcu_census_cluster_is_ce_0x68[
	sizeof(struct hcu_census_structure_cluster) == 0x68 ? 1 : -1];

static void hcu_census_assert_span(
	const char *field,
	const void *address,
	long count,
	size_t stride,
	const void *owner_base,
	size_t owner_bytes)
{
	uintptr_t base = (uintptr_t)owner_base;
	uintptr_t p = (uintptr_t)address;
	size_t bytes;
	assert(field && owner_base && count >= 0 && stride > 0);
	if (count == 0)
		return;
	assert(address && (size_t)count <= SIZE_MAX / stride);
	bytes = (size_t)count * stride;
	assert(p >= base && p - base <= owner_bytes &&
		bytes <= owner_bytes - (size_t)(p - base));
}

static void hcu_mp_nested_bsp_census(unsigned map_id)
{
	struct scenario_structure_bsp_reference *reference;
	struct hcu_census_structure_detail_object_data *detail_roots;
	struct hcu_census_structure_cluster *clusters;
	void *tag_base = physical_memory_get_tag_cache_base_address();
	void *bsp_base;
	size_t tag_bytes;
	size_t bsp_bytes;
	long i;
	assert(map_id >= 101u && map_id < 114u);
	assert(global_scenario && global_structure_bsp);
	assert(cache_file_globals.tags_loaded && cache_file_globals.header.tag_data_size > 0);
	tag_bytes = (size_t)cache_file_globals.header.tag_data_size;
	assert(tag_bytes <= physical_memory_get_tag_cache_size());
	hcu_census_assert_span("scenario.root", global_scenario, 1,
		sizeof(*global_scenario), tag_base, tag_bytes);
	hcu_census_assert_span("scenario.sound_scenery", global_scenario->sound_scenery.address,
		global_scenario->sound_scenery.count, 0x28u, tag_base, tag_bytes);
	hcu_census_assert_span("scenario.sound_scenery_palette",
		global_scenario->sound_scenery_palette.address,
		global_scenario->sound_scenery_palette.count, 0x30u, tag_base, tag_bytes);
	hcu_census_assert_span("scenario.structure_bsp_references",
		global_scenario->structure_bsp_references.address,
		global_scenario->structure_bsp_references.count,
		sizeof(struct scenario_structure_bsp_reference), tag_base, tag_bytes);
	assert(global_structure_bsp_index >= 0 &&
		global_structure_bsp_index < global_scenario->structure_bsp_references.count);
	reference = TAG_BLOCK_GET_ELEMENT(&global_scenario->structure_bsp_references,
		global_structure_bsp_index, struct scenario_structure_bsp_reference);
	assert(reference->file_size > 0 && (size_t)reference->file_size <=
		physical_memory_get_structure_bsp_cache_size());
	bsp_base = reference->base_address;
	bsp_bytes = (size_t)reference->file_size;
	assert(bsp_base == physical_memory_get_structure_bsp_cache_base_address());
	hcu_census_assert_span("structure_bsp.root", global_structure_bsp, 1,
		sizeof(*global_structure_bsp), bsp_base, bsp_bytes);

	/* Top-level variable-sized arrays exercised by this ledger. All strides
	 * come from the CE schema's size assertions, not from inferred raw bytes. */
	hcu_census_assert_span("bsp.pathfinding_surfaces",
		global_structure_bsp->pathfinding_surfaces.address,
		global_structure_bsp->pathfinding_surfaces.count, 1u, bsp_base, bsp_bytes);
	hcu_census_assert_span("bsp.pathfinding_edges",
		global_structure_bsp->pathfinding_edges.address,
		global_structure_bsp->pathfinding_edges.count, 1u, bsp_base, bsp_bytes);
	hcu_census_assert_span("bsp.runtime_decals",
		global_structure_bsp->runtime_decals.address,
		global_structure_bsp->runtime_decals.count, 8u, bsp_base, bsp_bytes);
	hcu_census_assert_span("bsp.detail_object_data",
		global_structure_bsp->detail_object_data.address,
		global_structure_bsp->detail_object_data.count,
		sizeof(struct hcu_census_structure_detail_object_data), bsp_base, bsp_bytes);
	hcu_census_assert_span("bsp.clusters", global_structure_bsp->clusters.address,
		global_structure_bsp->clusters.count, 0x68u, bsp_base, bsp_bytes);
	hcu_census_assert_span("bsp.lens_flare_markers",
		global_structure_bsp->lens_flare_markers.address,
		global_structure_bsp->lens_flare_markers.count, 0x10u, bsp_base, bsp_bytes);

	detail_roots = global_structure_bsp->detail_object_data.address;
	for (i = 0; i < global_structure_bsp->detail_object_data.count; ++i)
	{
		struct hcu_census_structure_detail_object_data *root = &detail_roots[i];
		hcu_census_assert_span("detail.cells", root->cells.address,
			root->cells.count, sizeof(struct hcu_census_detail_object_cell),
			bsp_base, bsp_bytes);
		hcu_census_assert_span("detail.instances", root->detail_objects.address,
			root->detail_objects.count, 6u, bsp_base, bsp_bytes);
		hcu_census_assert_span("detail.counts", root->counts.address,
			root->counts.count, sizeof(word), bsp_base, bsp_bytes);
		hcu_census_assert_span("detail.z_reference_vectors",
			root->z_reference_vectors.address, root->z_reference_vectors.count,
			4u * sizeof(real), bsp_base, bsp_bytes);
	}

	clusters = global_structure_bsp->clusters.address;
	for (i = 0; i < global_structure_bsp->clusters.count; ++i)
	{
		struct hcu_census_structure_cluster *cluster = &clusters[i];
		if (cluster->runtime_decal_count)
		{
			assert(cluster->first_runtime_decal_index >= 0 &&
				cluster->first_runtime_decal_index <=
				global_structure_bsp->runtime_decals.count - cluster->runtime_decal_count);
		}
		if (cluster->lens_flare_marker_count)
		{
			assert(cluster->first_lens_flare_marker_index <=
				global_structure_bsp->lens_flare_markers.count -
				cluster->lens_flare_marker_count);
		}
	}
	printf("mp-nested-census map=%u bsp=%d path_surfaces=%ld path_edges=%ld "
		"decals=%ld detail_roots=%ld lens_markers=%ld sound_scenery=%ld "
		"status=passed\n", map_id, global_structure_bsp_index,
		global_structure_bsp->pathfinding_surfaces.count,
		global_structure_bsp->pathfinding_edges.count,
		global_structure_bsp->runtime_decals.count,
		global_structure_bsp->detail_object_data.count,
		global_structure_bsp->lens_flare_markers.count,
		global_scenario->sound_scenery.count);
}

#endif
