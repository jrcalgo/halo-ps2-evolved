/* Relocated stock-MP detail-object gate.

 * The production PS2 cache/CBSP path publishes each map. This file then
 * calls the real CE detail-object init and structure_render_detail_objects
 * with the camera at every raw-proven subcluster bounds center. Rasterizer
 * entry points are counters only; this is not a detail-sprite renderer.
 */
#include "hcu_detail_present_bound_lifecycle.h"
#include "hcu_detail_present_bound_oracle.h"

#include "render/render.h"
#include "saved games/game_state.h"

#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

struct hcu_detail_root {
	struct tag_block cells;
	struct tag_block detail_objects;
	struct tag_block counts;
	struct tag_block z_reference_vectors;
	byte valid;
	byte pad31[3];
	long unused34[3];
};

struct hcu_detail_cluster {
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

struct hcu_detail_subcluster {
	real_rectangle3d world_bounds;
	struct tag_block surface_indices;
};

typedef char hcu_detail_root_size_assert[
	sizeof(struct hcu_detail_root) == 0x40 ? 1 : -1];
typedef char hcu_detail_cluster_size_assert[
	sizeof(struct hcu_detail_cluster) == 0x68 ? 1 : -1];
typedef char hcu_detail_subcluster_size_assert[
	sizeof(struct hcu_detail_subcluster) == 0x24 ? 1 : -1];
typedef char hcu_detail_subclusters_offset_assert[
	offsetof(struct hcu_detail_cluster, subclusters) == 0x34 ? 1 : -1];
typedef char hcu_detail_object_data_offset_assert[
	offsetof(struct structure_bsp, detail_object_data) == 588 ? 1 : -1];

struct render_globals render;

static unsigned hcu_detail_bsp_get_calls;
static unsigned hcu_detail_rasterizer_begin_calls;
static unsigned hcu_detail_rasterizer_rebuild_calls;
static unsigned hcu_detail_rasterizer_draw_calls;
static unsigned hcu_detail_rasterizer_end_calls;
static int hcu_detail_runtime_allocated;

static unsigned char hcu_detail_state_heap[1u << 20];
static size_t hcu_detail_state_used;

static struct players_globals hcu_detail_players;

struct structure_bsp *__real_global_structure_bsp_get(void);

static void hcu_detail_fail(const char *what)
{
	fprintf(stderr, "detail-present FAIL %s\n", what);
	abort();
}

#define CHECK(condition) \
	do { \
		if (!(condition)) \
			hcu_detail_fail(#condition); \
	} while (0)

struct structure_bsp *__wrap_global_structure_bsp_get(void)
{
	hcu_detail_bsp_get_calls++;
	return __real_global_structure_bsp_get();
}

struct detail_object_view_data;

void rasterizer_detail_objects_begin(void)
{
	hcu_detail_rasterizer_begin_calls++;
}

void rasterizer_detail_objects_rebuild_vertices(
	struct detail_object_view_data *view_data)
{
	(void)view_data;
	hcu_detail_rasterizer_rebuild_calls++;
}

void rasterizer_detail_objects_draw(
	struct detail_object_view_data *view_data)
{
	(void)view_data;
	hcu_detail_rasterizer_draw_calls++;
}

void rasterizer_detail_objects_end(void)
{
	hcu_detail_rasterizer_end_calls++;
}

void *game_state_malloc(const char *name, const char *type, long size)
{
	size_t aligned;
	(void)type;
	CHECK(size > 0);
	aligned = (hcu_detail_state_used + 15u) & ~(size_t)15u;
	CHECK(aligned + (size_t)size <= sizeof hcu_detail_state_heap);
	if (name && strcmp(name, "structure detail objects") == 0) {
		CHECK(size == 0xA430);
		hcu_detail_runtime_allocated = 1;
	}
	hcu_detail_state_used = aligned + (size_t)size;
	return hcu_detail_state_heap + aligned;
}

static int hcu_detail_span_inside(const void *base, size_t bytes,
	const void *pointer, size_t need)
{
	uintptr_t start = (uintptr_t)base;
	uintptr_t value = (uintptr_t)pointer;
	if (!pointer || value < start || (size_t)(value - start) > bytes)
		return 0;
	return need <= bytes - (size_t)(value - start);
}

static void hcu_detail_digest(const void *bytes, size_t size, uint8_t out[32])
{
	sha256_context context;
	sha256_init(&context);
	sha256_update(&context, bytes, size);
	sha256_final(&context, out);
}

static void hcu_detail_print_digest(const uint8_t digest[32])
{
	unsigned index;
	for (index = 0; index < 32u; ++index)
		printf("%02x", digest[index]);
}

static void hcu_detail_query_map(const struct hcu_detail_map_oracle *oracle)
{
	struct scenario_structure_bsp_reference *reference;
	struct structure_bsp *bsp;
	struct hcu_detail_root *root;
	struct hcu_detail_cluster *clusters;
	struct tag_block *children;
	unsigned char *image;
	unsigned char *snapshot;
	uint8_t digest_before[32];
	uint8_t digest_after[32];
	short collision_depth;
	short collision_user0;
	unsigned row;
	unsigned cluster_index;
	unsigned camera_calls = 0;
	size_t image_bytes;
	struct players_globals *saved_players = players_globals;

	CHECK(global_scenario && global_structure_bsp && global_structure_bsp_index == 0);
	CHECK(global_scenario->structure_bsp_references.count == 1);
	reference = (struct scenario_structure_bsp_reference *)
		global_scenario->structure_bsp_references.address;
	CHECK(reference);
	CHECK((unsigned)reference->file_offset == oracle->bsp_file_offset);
	CHECK((unsigned)reference->file_size == oracle->bsp_file_size);
	CHECK(reference->base_address == physical_memory_get_structure_bsp_cache_base_address());
	image = reference->base_address;
	image_bytes = (size_t)reference->file_size;
	CHECK(hcu_detail_span_inside(image, image_bytes, global_structure_bsp,
		sizeof(*global_structure_bsp)));
	bsp = global_structure_bsp;
	CHECK((unsigned)bsp->detail_object_data.count == oracle->detail_count);
	CHECK(oracle->detail_count == 1u);
	CHECK(bsp->detail_object_data.definition == NULL);
	CHECK(hcu_detail_span_inside(image, image_bytes,
		bsp->detail_object_data.address, sizeof(*root)));
	root = bsp->detail_object_data.address;
	CHECK(memcmp(root, oracle->raw_root, sizeof oracle->raw_root) == 0);
	CHECK(root->valid == 0);
	CHECK(oracle->valid == 0u);
	children = &root->cells;
	{
		unsigned child;
		for (child = 0; child < 4u; ++child) {
			CHECK(children[child].count == oracle->child_count[child]);
			CHECK(oracle->child_address[child] == 0u);
			CHECK(children[child].address == NULL);
			CHECK(children[child].count == 0);
		}
	}
	CHECK((unsigned)bsp->clusters.count == oracle->cluster_count);
	CHECK(hcu_detail_span_inside(image, image_bytes, bsp->clusters.address,
		(size_t)bsp->clusters.count * sizeof(*clusters)));
	clusters = bsp->clusters.address;

	memset(&hcu_detail_players, 0, sizeof hcu_detail_players);
	hcu_detail_players.local_player_count = 1;
	players_globals = &hcu_detail_players;
	render.local_player_index = 0;
	structure_detail_objects_initialize_for_new_map();

	snapshot = malloc(image_bytes);
	CHECK(snapshot);
	memcpy(snapshot, image, image_bytes);
	hcu_detail_digest(image, image_bytes, digest_before);
	collision_depth = global_current_collision_user_depth;
	collision_user0 = global_current_collision_users[0];
	hcu_detail_rasterizer_begin_calls = 0;
	hcu_detail_rasterizer_rebuild_calls = 0;
	hcu_detail_rasterizer_draw_calls = 0;
	hcu_detail_rasterizer_end_calls = 0;

	row = oracle->subcluster_begin;
	for (cluster_index = 0; cluster_index < oracle->cluster_count; ++cluster_index) {
		struct hcu_detail_cluster *cluster = &clusters[cluster_index];
		unsigned subcluster_index;
		CHECK(cluster->subclusters.count >= 0);
		if (cluster->subclusters.count == 0) {
			CHECK(cluster->subclusters.address == NULL);
			continue;
		}
		CHECK(hcu_detail_span_inside(image, image_bytes,
			cluster->subclusters.address,
			(size_t)cluster->subclusters.count * sizeof(struct hcu_detail_subcluster)));
		for (subcluster_index = 0;
			subcluster_index < (unsigned)cluster->subclusters.count;
			++subcluster_index) {
			struct hcu_detail_subcluster *subcluster =
				(struct hcu_detail_subcluster *)((byte *)cluster->subclusters.address +
					subcluster_index * sizeof(*subcluster));
			const struct hcu_detail_subcluster_oracle *sample;
			unsigned gets_before;
			CHECK(row < HCU_DETAIL_SUBCLUSTER_COUNT);
			sample = &hcu_detail_subclusters[row++];
			CHECK(sample->map_id == oracle->map_id);
			CHECK(sample->cluster_index == cluster_index);
			CHECK(sample->subcluster_index == subcluster_index);
			CHECK(memcmp(&subcluster->world_bounds, sample->bounds_bits,
				sizeof sample->bounds_bits) == 0);
			render.camera.position.x =
				(subcluster->world_bounds.x0 + subcluster->world_bounds.x1) * 0.5f;
			render.camera.position.y =
				(subcluster->world_bounds.y0 + subcluster->world_bounds.y1) * 0.5f;
			render.camera.position.z =
				(subcluster->world_bounds.z0 + subcluster->world_bounds.z1) * 0.5f;
			CHECK(local_player_count() == 1);
			CHECK(render.local_player_index == 0);
			gets_before = hcu_detail_bsp_get_calls;
			structure_render_detail_objects();
			if (hcu_detail_bsp_get_calls - gets_before != 2u) {
				fprintf(stderr, "detail-present FAIL bsp_get delta=%u map=%s cluster=%u sub=%u\n",
					hcu_detail_bsp_get_calls - gets_before, oracle->name,
					cluster_index, subcluster_index);
				abort();
			}
			CHECK(hcu_detail_rasterizer_begin_calls == 0u);
			CHECK(hcu_detail_rasterizer_rebuild_calls == 0u);
			CHECK(hcu_detail_rasterizer_draw_calls == 0u);
			CHECK(hcu_detail_rasterizer_end_calls == 0u);
			CHECK(root->valid == 0);
			CHECK(memcmp(image, snapshot, image_bytes) == 0);
			CHECK(global_structure_bsp == bsp);
			CHECK(global_current_collision_user_depth == collision_depth);
			CHECK(global_current_collision_users[0] == collision_user0);
			camera_calls++;
		}
	}
	CHECK(row == oracle->subcluster_begin + oracle->subcluster_count);
	CHECK(camera_calls == oracle->subcluster_count);
	hcu_detail_digest(image, image_bytes, digest_after);
	CHECK(memcmp(digest_before, digest_after, sizeof digest_before) == 0);
	printf("detail-present map=%s id=%u bsp=%d detail_roots=%ld valid=%u "
		"cells=%d objects=%d counts=%d zrefs=%d child_addresses=0 "
		"clusters=%u subclusters=%u camera_calls=%u bsp_gets=%u "
		"rasterizer_begin=%u rebuild=%u draw=%u end=%u bsp_bytes=%u bsp_sha256=",
		oracle->name, oracle->map_id, (int)global_structure_bsp_index,
		bsp->detail_object_data.count, (unsigned)root->valid,
		root->cells.count, root->detail_objects.count, root->counts.count,
		root->z_reference_vectors.count, oracle->cluster_count,
		oracle->subcluster_count, camera_calls,
		camera_calls * 2u,
		hcu_detail_rasterizer_begin_calls, hcu_detail_rasterizer_rebuild_calls,
		hcu_detail_rasterizer_draw_calls, hcu_detail_rasterizer_end_calls,
		(unsigned)image_bytes);
	hcu_detail_print_digest(digest_after);
	printf(" bsp_unchanged=1 collision_depth=%d collision_depth_unchanged=1 "
		"status=passed\n", (int)collision_depth);
	free(snapshot);
	players_globals = saved_players;
}

int main(int argc, char **argv)
{
	static unsigned char streaming_bytes[1572864u] __attribute__((aligned(64)));
	arena_t production_owner;
	arena_t production_scratch;
	arena_t streaming;
	unsigned map_index;
	unsigned camera_total = 0;

	CHECK(argc == 2);
	setvbuf(stdout, NULL, _IONBF, 0);
	CHECK(file_set_default_root(argv[1]));
	CHECK(ps2_animation_trace_bind(lifecycle_trace_events, LIFECYCLE_TRACE_CAPACITY));
	CHECK(ps2_animation_trace_bind_contexts(lifecycle_trace_contexts,
		LIFECYCLE_TRACE_CAPACITY));
	ps2_animation_trace_reset();
	arena_init(&streaming, "detail streaming", streaming_bytes, sizeof streaming_bytes);
	arena_init(&production_owner, "detail package owner", streaming_bytes, 1048576u);
	arena_init(&production_scratch, "detail section scratch",
		streaming_bytes + 1048576u, 524288u);
	lifecycle_layout.regions[MEM_LAYOUT_V2_STREAMING] = streaming;
	lifecycle_layout.regions[MEM_LAYOUT_V2_FRAME_SCRATCH] = production_scratch;
	CHECK(hcu_map_service_init_with_arenas(&lifecycle_service, &lifecycle_layout,
		argv[1], &production_owner, &production_scratch) == 0);
	CHECK(tag_validate_bind_claims_buffer(retail_claims_bytes, sizeof retail_claims_bytes));
	cache_files_initialize();
	scenario_globals = &globals_fixture;
	scenario_globals->structure_bsp_index = NONE;
	global_tag_instances = tag_instances;
	global_tag_count = 0;
	structure_detail_objects_initialize();
	CHECK(hcu_detail_runtime_allocated);

	for (map_index = 0; map_index < HCU_DETAIL_MAP_COUNT; ++map_index) {
		const struct hcu_detail_map_oracle *oracle = &hcu_detail_maps[map_index];
		char scenario[128];
		CHECK(snprintf(scenario, sizeof scenario, "levels\\test\\%s\\%s",
			oracle->name, oracle->name) < (int)sizeof scenario);
		retail_ref_count = 1u;
		retail_offset[0] = oracle->bsp_file_offset;
		retail_size[0] = oracle->bsp_file_size;
		CHECK(retail_size[0] > 0u && retail_size[0] <= sizeof bsp_cache);
		CHECK(ps2_cache_preflight_map(scenario));
		(void)cache_files_give_time_to_precache(scenario);
		CHECK(cache_files_give_time_to_precache(scenario));
		CHECK(cache_files_precache_map_loaded(oracle->name));
		loaded_datum = 0;
		CHECK(scenario_load(scenario));
		CHECK(global_scenario && global_structure_bsp && global_collision_bsp &&
			global_bsp3d && cache_file_globals.tags_loaded &&
			lifecycle_service.mount.active && lifecycle_service.source.active);
		hcu_detail_query_map(oracle);
		camera_total += oracle->subcluster_count;
		scenario_unload();
		CHECK(!global_scenario && !global_structure_bsp && !global_collision_bsp &&
			!global_bsp3d && !cache_file_globals.tags_loaded &&
			!lifecycle_service.mount.active && !lifecycle_service.source.active &&
			lifecycle_service.map_arena->used == 0u &&
			lifecycle_service.section_scratch->used == 0u);
	}
	hcu_map_service_shutdown(&lifecycle_service);
	CHECK(hcu_detail_rasterizer_begin_calls == 0u);
	printf("detail-present summary maps=%u camera_calls=%u rasterizer_calls=0 "
		"status=passed\n", HCU_DETAIL_MAP_COUNT, camera_total);
	return 0;
}
