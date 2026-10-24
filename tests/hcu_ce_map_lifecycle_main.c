/* Real CE scenario lifecycle over the production parent UI map service.
 * Reuse the bounded CE tag/BSP shims from the adjacent transaction fixture,
 * but do not inherit its hand-mounted package transaction. */
#define HCU_BSP_RETAIL_INTEGRATION 1
#define __wrap_read hcu_bsp_fixture_wrap_read
#define main hcu_bsp_switch_fixture_main
#include "hcu_scenario_bsp_switch_main.c"
#undef main
#undef __wrap_read

#include "stream/hcu_map_service.h"
#include "core/mem.h"
#include "custom_edition_cache.h"
#include "ps2_animation_trace.h"
#include "stream/sha256.h"
#include <strings.h>

#ifdef HCU_C1_REAL_PROFILE
#include "hcu_c1_real_profile_expectations.h"
#endif

#define LIFECYCLE_TRACE_CAPACITY 64
static struct ps2_animation_trace_event lifecycle_trace_events[LIFECYCLE_TRACE_CAPACITY];
static struct ps2_animation_trace_context lifecycle_trace_contexts[LIFECYCLE_TRACE_CAPACITY];
static mem_layout_v2_t lifecycle_layout;
static hcu_map_service lifecycle_service;
static int lifecycle_read_fault_armed;
static int lifecycle_read_partial_seen;
static int lifecycle_read_eof_seen;
static int lifecycle_owner_release_count;
static int lifecycle_bsp_failure_armed;
static int lifecycle_bsp_failure_injected;
static int lifecycle_bsp_sink_writes;
static int lifecycle_bsp_destination_witness;
static const char *lifecycle_bsp_failure_tag = "B000";
static int lifecycle_d20_fault_visit_count;
static hp2_status lifecycle_d20_fault_last_status = HP2_OK;
static char lifecycle_d20_fault_tag[5];
static uint8_t lifecycle_profile_image[212];
static uint8_t lifecycle_profile_pin[32];
typedef struct lifecycle_profile_reader { uint8_t *bytes; uint32_t size; } lifecycle_profile_reader;
static lifecycle_profile_reader lifecycle_profile_source;
typedef struct lifecycle_active_map_snapshot {
	struct cache_file_globals cache_globals;
	struct scenario_globals scenario_state;
	hcu_map_service service_state;
	void *scenario;
	long scenario_index;
	void *structure_bsp;
	void *collision_bsp;
	void *bsp3d;
	void *game_globals;
	short structure_bsp_index;
	struct cache_file_tag_instance *tag_instances;
	long tag_count;
	size_t owner_used;
	size_t owner_high;
	size_t scratch_used;
	size_t scratch_high;
	uint8_t owner_digest[32];
	uint8_t tag_digest[32];
	uint8_t bsp_digest[32];
} lifecycle_active_map_snapshot;
static void lifecycle_snapshot_active_map(lifecycle_active_map_snapshot *snapshot);
static void lifecycle_assert_active_map_snapshot(
	const lifecycle_active_map_snapshot *snapshot);
#ifdef HCU_C1_REAL_PROFILE
static uint8_t *lifecycle_real_profile_bytes;
static uint32_t lifecycle_real_profile_size;
static int lifecycle_real_profile_read(void *context, uint32_t offset,
	void *destination, uint32_t size)
{
	(void)context;
	if (!lifecycle_real_profile_bytes || offset > lifecycle_real_profile_size ||
		size > lifecycle_real_profile_size - offset) return -1;
	memcpy(destination, lifecycle_real_profile_bytes + offset, size);
	return 0;
}

static int lifecycle_real_profile_compatibility(void *context,
	const hcu_map_catalog_entry *entry, const hcu_asset_profile_view *profile)
{
	uint32_t i;
	(void)context;
	if (!entry || !profile || strcmp(entry->identity.map_name, "ui") != 0 ||
		profile->profile_id != HCU_C1_PROFILE_ID ||
		profile->total_bytes != HCU_C1_PACKAGE_BYTES ||
		profile->chunk_count != HCU_C1_CHUNK_COUNT) return 0;
	for (i = 0; i < HCU_C1_CHUNK_COUNT; ++i) {
		hcu_asset_chunk_view actual;
		const hcu_c1_expected_chunk *expected = &hcu_c1_expected_chunks[i];
		if (hcu_asset_profile_lookup(profile, expected->type, expected->id,
			&actual) != HCU_ASSET_PROFILE_OK || actual.size != expected->size ||
			memcmp(actual.sha256, expected->sha256, 32) != 0) return 0;
	}
	return 1;
}

static void lifecycle_run_real_profile(const char *profile_path)
{
	lifecycle_active_map_snapshot before;
	FILE *input;
	long length;
	assert(lifecycle_real_profile_bytes == NULL);
	input = fopen(profile_path ? profile_path : HCU_C1_PROFILE_PATH, "rb");
	assert(input != NULL && fseek(input, 0, SEEK_END) == 0);
	length = ftell(input);
	assert(length > 0 && (unsigned long)length == HCU_C1_PACKAGE_BYTES);
	rewind(input);
	lifecycle_real_profile_size = (uint32_t)length;
	lifecycle_real_profile_bytes = (uint8_t *)malloc(lifecycle_real_profile_size);
	assert(lifecycle_real_profile_bytes != NULL &&
		fread(lifecycle_real_profile_bytes, 1, lifecycle_real_profile_size, input) ==
		lifecycle_real_profile_size);
	fclose(input);
	lifecycle_snapshot_active_map(&before);
	assert(!hcu_map_service_register_profile(&lifecycle_service, "beavercreek",
		HCU_C1_PROFILE_ID, lifecycle_real_profile_read, NULL,
		lifecycle_real_profile_size, hcu_c1_package_sha256,
		lifecycle_real_profile_compatibility, NULL));
	assert(memcmp(&lifecycle_service, &before.service_state,
		sizeof(lifecycle_service)) == 0);
	lifecycle_assert_active_map_snapshot(&before);
	puts("ce-lifecycle actual UI HCP rejected for incompatible map before teardown");
	assert(hcu_map_service_register_profile(&lifecycle_service, "ui",
		HCU_C1_PROFILE_ID, lifecycle_real_profile_read, NULL,
		lifecycle_real_profile_size, hcu_c1_package_sha256,
		lifecycle_real_profile_compatibility, NULL));
	lifecycle_snapshot_active_map(&before);
	assert(ps2_cache_preflight_map("levels\\ui\\ui"));
	{
		hcu_map_service expected = before.service_state;
		expected.staged_entry = hcu_map_catalog_find("ui");
		memcpy(expected.staged_map, "ui", sizeof("ui"));
		expected.reload_pending = 1;
		assert(memcmp(&lifecycle_service, &expected, sizeof(expected)) == 0);
	}
	lifecycle_assert_active_map_snapshot(&before);
	puts("ce-lifecycle actual validated UI HCP identity and complete chunk inventory accepted before same-map unload");
	/* Damage a real package payload after registration. The same-map preflight
	 * must reject its pinned hash while the active CE/service snapshot survives. */
	{
		uint32_t offset = HCU_C1_FIRST_PAYLOAD_OFFSET;
		uint8_t saved = lifecycle_real_profile_bytes[offset];
		lifecycle_real_profile_bytes[offset] ^= 0x80;
		lifecycle_snapshot_active_map(&before);
		assert(!ps2_cache_preflight_map("levels\\ui\\ui"));
		assert(memcmp(&lifecycle_service, &before.service_state,
			sizeof(lifecycle_service)) == 0);
		lifecycle_assert_active_map_snapshot(&before);
		lifecycle_real_profile_bytes[offset] = saved;
	}
	puts("ce-lifecycle corrupt actual UI HCP rejected before teardown; active CE snapshot retained");
	free(lifecycle_real_profile_bytes);
	lifecycle_real_profile_bytes = NULL;
}
#endif
static void precache_until_ready(const char *name);
static void lifecycle_digest(const void *bytes, size_t size, uint8_t digest[32]);

static void lifecycle_put_le32(uint8_t *p, uint32_t value)
{
	p[0]=(uint8_t)value; p[1]=(uint8_t)(value>>8);
	p[2]=(uint8_t)(value>>16); p[3]=(uint8_t)(value>>24);
}

static int lifecycle_profile_read(void *context, uint32_t offset,
	void *destination, uint32_t size)
{
	lifecycle_profile_reader *reader=(lifecycle_profile_reader *)context;
	if(!reader || offset>reader->size || size>reader->size-offset) return -1;
	memcpy(destination,reader->bytes+offset,size); return 0;
}

static int lifecycle_profile_compatibility(void *context,
	const hcu_map_catalog_entry *entry, const hcu_asset_profile_view *profile)
{
	const char *expected=(const char *)context;
	hcu_asset_chunk_view chunk;
	return expected && entry && profile &&
		strcmp(entry->identity.map_name,expected)==0 &&
		hcu_asset_profile_lookup(profile,HCU_ASSET_CHUNK_CE,0,&chunk)==HCU_ASSET_PROFILE_OK &&
		hcu_asset_profile_lookup(profile,HCU_ASSET_CHUNK_MEDIA,0,&chunk)==HCU_ASSET_PROFILE_OK &&
		hcu_asset_profile_lookup(profile,HCU_ASSET_CHUNK_SOUND_META,0,&chunk)==HCU_ASSET_PROFILE_OK;
}

static void lifecycle_make_profile(void)
{
	static const uint8_t ce[]={1,2,3}, sound[]={4,5,6,7};
	uint8_t digest[32]; sha256_context sha;
	memset(lifecycle_profile_image,0,sizeof(lifecycle_profile_image));
	memcpy(lifecycle_profile_image,"HCP1",4);
	lifecycle_put_le32(lifecycle_profile_image+4,1);
	lifecycle_put_le32(lifecycle_profile_image+8,32);
	lifecycle_put_le32(lifecycle_profile_image+12,0x12345);
	lifecycle_put_le32(lifecycle_profile_image+16,3);
	lifecycle_put_le32(lifecycle_profile_image+20,32);
	lifecycle_put_le32(lifecycle_profile_image+24,144);
	lifecycle_put_le32(lifecycle_profile_image+28,sizeof(lifecycle_profile_image));
	lifecycle_put_le32(lifecycle_profile_image+32,1);
	lifecycle_put_le32(lifecycle_profile_image+40,176);
	lifecycle_put_le32(lifecycle_profile_image+44,sizeof(ce));
	sha256_init(&sha); sha256_update(&sha,ce,sizeof(ce)); sha256_final(&sha,digest);
	memcpy(lifecycle_profile_image+48,digest,32);
	lifecycle_put_le32(lifecycle_profile_image+80,2);
	lifecycle_put_le32(lifecycle_profile_image+88,192);
	lifecycle_put_le32(lifecycle_profile_image+92,sizeof(sound));
	sha256_init(&sha); sha256_update(&sha,sound,sizeof(sound)); sha256_final(&sha,digest);
	memcpy(lifecycle_profile_image+96,digest,32);
	lifecycle_put_le32(lifecycle_profile_image+128,3);
	lifecycle_put_le32(lifecycle_profile_image+136,208);
	lifecycle_put_le32(lifecycle_profile_image+140,sizeof(sound));
	memcpy(lifecycle_profile_image+144,digest,32);
	memcpy(lifecycle_profile_image+176,ce,sizeof(ce));
	memcpy(lifecycle_profile_image+192,sound,sizeof(sound));
	memcpy(lifecycle_profile_image+208,sound,sizeof(sound));
	lifecycle_profile_source.bytes=lifecycle_profile_image;
	lifecycle_profile_source.size=sizeof(lifecycle_profile_image);
}

static void lifecycle_pin_profile(void)
{
	lifecycle_digest(lifecycle_profile_image, sizeof(lifecycle_profile_image),
		lifecycle_profile_pin);
}

static void lifecycle_digest(const void *bytes, size_t size, uint8_t digest[32])
{
	sha256_context context;
	sha256_init(&context);
	sha256_update(&context, bytes, size);
	sha256_final(&context, digest);
}

static void lifecycle_snapshot_active_map(lifecycle_active_map_snapshot *snapshot)
{
	assert(snapshot && lifecycle_service.mount.active &&
		lifecycle_service.source.active && cache_file_globals.tags_loaded &&
		global_scenario && global_structure_bsp && global_collision_bsp &&
		global_bsp3d && global_game_globals);
	memset(snapshot, 0, sizeof(*snapshot));
	snapshot->cache_globals = cache_file_globals;
	snapshot->scenario_state = *scenario_globals;
	snapshot->service_state = lifecycle_service;
	snapshot->scenario = global_scenario;
	snapshot->scenario_index = global_scenario_index;
	snapshot->structure_bsp = global_structure_bsp;
	snapshot->collision_bsp = global_collision_bsp;
	snapshot->bsp3d = global_bsp3d;
	snapshot->game_globals = global_game_globals;
	snapshot->structure_bsp_index = global_structure_bsp_index;
	snapshot->tag_instances = global_tag_instances;
	snapshot->tag_count = global_tag_count;
	snapshot->owner_used = lifecycle_service.map_arena->used;
	snapshot->owner_high = lifecycle_service.map_arena->high;
	snapshot->scratch_used = lifecycle_service.section_scratch->used;
	snapshot->scratch_high = lifecycle_service.section_scratch->high;
	lifecycle_digest(lifecycle_service.map_arena->base,
		lifecycle_service.map_arena->used, snapshot->owner_digest);
	lifecycle_digest(tag_cache, sizeof(tag_cache), snapshot->tag_digest);
	lifecycle_digest(bsp_cache, sizeof(bsp_cache), snapshot->bsp_digest);
}

static void lifecycle_assert_active_map_snapshot(
	const lifecycle_active_map_snapshot *snapshot)
{
	uint8_t digest[32];
	assert(snapshot);
	assert(memcmp(&cache_file_globals, &snapshot->cache_globals,
		sizeof(cache_file_globals)) == 0);
	assert(memcmp(scenario_globals, &snapshot->scenario_state,
		sizeof(*scenario_globals)) == 0);
	assert(global_scenario == snapshot->scenario &&
		global_scenario_index == snapshot->scenario_index &&
		global_structure_bsp == snapshot->structure_bsp &&
		global_collision_bsp == snapshot->collision_bsp &&
		global_bsp3d == snapshot->bsp3d &&
		global_game_globals == snapshot->game_globals &&
		global_structure_bsp_index == snapshot->structure_bsp_index &&
		global_tag_instances == snapshot->tag_instances &&
		global_tag_count == snapshot->tag_count);
	assert(lifecycle_service.map_arena->used == snapshot->owner_used &&
		lifecycle_service.map_arena->high == snapshot->owner_high &&
		lifecycle_service.section_scratch->used == snapshot->scratch_used &&
		lifecycle_service.section_scratch->high == snapshot->scratch_high &&
		lifecycle_service.mount.active && lifecycle_service.source.active &&
		lifecycle_service.source.reader.descriptor ==
			snapshot->service_state.source.reader.descriptor);
	lifecycle_digest(lifecycle_service.map_arena->base,
		lifecycle_service.map_arena->used, digest);
	assert(memcmp(digest, snapshot->owner_digest, sizeof(digest)) == 0);
	lifecycle_digest(tag_cache, sizeof(tag_cache), digest);
	assert(memcmp(digest, snapshot->tag_digest, sizeof(digest)) == 0);
	lifecycle_digest(bsp_cache, sizeof(bsp_cache), digest);
	assert(memcmp(digest, snapshot->bsp_digest, sizeof(digest)) == 0);
}

static unsigned long lifecycle_trace_map_epoch(void)
{
	long row = ps2_animation_trace_count();
	struct ps2_animation_trace_event const *events;
	struct ps2_animation_trace_context const *contexts;
	ps2_animation_trace_record(_ps2_animation_trace_frame_info, NULL, NULL,
		0, 0, 0, 1);
	assert(ps2_animation_trace_count() == row + 1);
	events = ps2_animation_trace_events();
	contexts = ps2_animation_trace_contexts();
	assert(events[row].context_token == row + 1);
	assert(contexts[row].valid_mask & _ps2_animation_trace_context_map_epoch);
	printf("ce-lifecycle trace-map-epoch row=%ld epoch=%lu\n",
		row, contexts[row].map_epoch);
	return contexts[row].map_epoch;
}

typedef struct lifecycle_bsp_sink_context {
	world_section_sink_fn sink;
	void *sink_context;
	unsigned calls;
} lifecycle_bsp_sink_context;

static int lifecycle_bsp_fail_after_first_write(void *context,
	uint32_t offset, const uint8_t *bytes, size_t size)
{
	lifecycle_bsp_sink_context *failure =
		(lifecycle_bsp_sink_context *)context;
	int result;
	if (!failure || !failure->sink) return -1;
	if (failure->calls++ == 0) {
		result = failure->sink(failure->sink_context, offset, bytes, size);
		if (result != 0) return result;
		++lifecycle_bsp_sink_writes;
		/* The UI CBSP is one decoded chunk: header followed by image/rows.
		 * Verify image bytes landed in the CE destination, not only that the
		 * callback returned success. */
		if (offset == 0 && lifecycle_bsp_failure_tag &&
			strcmp(lifecycle_bsp_failure_tag, "CTAG") == 0 && size > 52u &&
			memcmp(tag_cache, bytes + 52u,
				size - 52u < 16u ? size - 52u : 16u) == 0)
			lifecycle_bsp_destination_witness = 1;
		else if (offset == 0 && size > 36u &&
			memcmp(bsp_cache, bytes + 36u,
				size - 36u < 16u ? size - 36u : 16u) == 0)
			lifecycle_bsp_destination_witness = 1;
		/* Fail this same callback after its bytes reached the real destination.
		 * UI B000 can fit in one HP2 output chunk, so a second-callback fault
		 * would not reliably exercise late rollback. */
		lifecycle_bsp_failure_armed = 0;
		lifecycle_bsp_failure_injected = 1;
		lifecycle_bsp_failure_tag = NULL;
		return -1;
	}
	return -1;
}

hp2_status __real_world_visit_section_with_scratch(arena_t *scratch_arena,
	const char *path, const char *tag, size_t *raw_size, int optional,
	world_section_sink_fn sink, void *sink_context);

hp2_status __wrap_world_visit_section_with_scratch(arena_t *scratch_arena,
	const char *path, const char *tag, size_t *raw_size, int optional,
	world_section_sink_fn sink, void *sink_context)
{
	lifecycle_bsp_sink_context failure;
	hp2_status status;
	if (!lifecycle_bsp_failure_armed || !tag || !lifecycle_bsp_failure_tag ||
		strcmp(tag, lifecycle_bsp_failure_tag) != 0) {
		status = __real_world_visit_section_with_scratch(scratch_arena, path,
			tag, raw_size, optional, sink, sink_context);
		if (tag && lifecycle_d20_fault_tag[0] &&
			strcmp(tag, lifecycle_d20_fault_tag) == 0) {
			++lifecycle_d20_fault_visit_count;
			lifecycle_d20_fault_last_status = status;
		}
		return status;
	}
	failure.sink = sink;
	failure.sink_context = sink_context;
	failure.calls = 0;
	return __real_world_visit_section_with_scratch(scratch_arena, path, tag,
		raw_size, optional, lifecycle_bsp_fail_after_first_write, &failure);
}

static void verify_ce_tag_read_failure_and_retry(void)
{
	long scenario_tag_index;
	assert(lifecycle_service.mount.active &&
		lifecycle_service.mount.ctag_relocations &&
		lifecycle_service.source.active && !cache_file_globals.tags_loaded &&
		cache_file_globals.tag_header == NULL);
	/* Fail the real streamed HP2 CTAG visitor after its first decoded window has
	 * reached CE's final destination. The cache completion flag must remain
	 * false, so CE cannot publish tag globals from this partial candidate. */
	lifecycle_bsp_failure_tag = "CTAG";
	lifecycle_bsp_failure_armed = 1;
	lifecycle_bsp_failure_injected = 0;
	lifecycle_bsp_destination_witness = 0;
	lifecycle_bsp_sink_writes = 0;
	global_tag_instances = NULL;
	global_tag_count = 0;
	cache_file_globals.tag_header = NULL;
	cache_file_globals.tags_loaded = FALSE;
	assert(!scenario_load("levels\\ui\\ui"));
	assert(!cache_file_globals.tags_loaded &&
		cache_file_globals.tag_header == NULL &&
		global_tag_instances == NULL && global_tag_count == 0 &&
		global_scenario == NULL && global_scenario_index == NONE);
	assert(lifecycle_bsp_failure_injected && lifecycle_bsp_destination_witness &&
		lifecycle_bsp_sink_writes == 1);
	assert(!lifecycle_service.mount.active && !lifecycle_service.source.active &&
		lifecycle_service.source.reader.descriptor < 0 &&
		lifecycle_service.map_arena->used == 0 &&
		!cache_files_precache_map_loaded("ui") &&
		lifecycle_owner_release_count == 1);
	assert(tag_cache[0] != 0xCD || tag_cache[1] != 0xCD ||
		tag_cache[2] != 0xCD || tag_cache[3] != 0xCD);
	/* A fresh mount reopens the package and rewrites from offset zero; the
	 * partial candidate from the failed attempt is not treated as a valid tag. */
	assert(ps2_cache_preflight_map("levels\\ui\\ui"));
	precache_until_ready("levels\\ui\\ui");
	scenario_tag_index = scenario_tags_load("levels\\ui\\ui");
	assert(scenario_tag_index != NONE && cache_file_globals.tags_loaded &&
		cache_file_globals.tag_header == (struct cache_file_tag_header *)tag_cache &&
		global_tag_instances != NULL && global_tag_count > 0);
	/* Return the CE tag layer to its pre-scenario state; scenario_load below
	 * repeats the normal load and then owns the full scenario/BSP publication. */
	scenario_tags_unload();
	assert(!cache_file_globals.tags_loaded &&
		cache_file_globals.tag_header == NULL &&
		global_tag_instances == NULL && global_tag_count == 0 &&
		lifecycle_service.mount.active && lifecycle_service.source.active);
	puts("ce-lifecycle late streamed CTAG visitor failure stayed unpublished; fresh remount retry passed");
}

static void verify_ce_tag_validation_failure_and_retry(void)
{
	assert(lifecycle_service.mount.active && lifecycle_service.source.active &&
		!cache_file_globals.tags_loaded && cache_file_globals.tag_header == NULL &&
		global_tag_instances == NULL && global_tag_count == 0);
	assert(tag_cache[0] != 0xCD || tag_cache[1] != 0xCD ||
		tag_cache[2] != 0xCD || tag_cache[3] != 0xCD);
	hcu_bsp_fixture_tag_validation_rejected = 0;
	hcu_bsp_fixture_reject_tag_validation_once = 1;
	assert(!scenario_load("levels\\ui\\ui"));
	assert(!hcu_bsp_fixture_reject_tag_validation_once &&
		hcu_bsp_fixture_tag_validation_rejected);
	assert(!cache_file_globals.tags_loaded && cache_file_globals.tag_header == NULL &&
		global_tag_instances == NULL && global_tag_count == 0 &&
		global_scenario == NULL && global_scenario_index == NONE);
	assert(!lifecycle_service.mount.active && !lifecycle_service.source.active &&
		lifecycle_service.source.reader.descriptor < 0 &&
		lifecycle_service.map_arena->used == 0 &&
		lifecycle_service.section_scratch->used == 0 &&
		!cache_files_precache_map_loaded("ui") && lifecycle_owner_release_count == 2);
	assert(ps2_cache_preflight_map("levels\\ui\\ui"));
	precache_until_ready("levels\\ui\\ui");
	loaded_datum = 0;
	assert(scenario_load("levels\\ui\\ui"));
	assert(global_scenario != NULL && global_structure_bsp != NULL &&
		cache_file_globals.tags_loaded && global_tag_instances != NULL &&
		lifecycle_service.mount.active && lifecycle_service.source.active);
	scenario_unload();
	assert(!lifecycle_service.mount.active && !lifecycle_service.source.active &&
		!cache_file_globals.tags_loaded && global_tag_instances == NULL &&
		lifecycle_service.map_arena->used == 0 && lifecycle_owner_release_count == 3);
	assert(ps2_cache_preflight_map("levels\\ui\\ui"));
	precache_until_ready("levels\\ui\\ui");
	puts("ce-lifecycle post-copy tag validation failure released owner; full retry passed");
}

int __real_ps2_cache_release_map_owner(void);
int __wrap_ps2_cache_release_map_owner(void)
{
	/* This is the exact CE-to-parent release boundary, not a post-call check. */
	assert(global_scenario == NULL && global_structure_bsp == NULL &&
		global_collision_bsp == NULL && global_bsp3d == NULL &&
		global_game_globals == NULL && global_scenario_index == NONE &&
		global_structure_bsp_index == NONE &&
		scenario_globals->structure_bsp_index == NONE);
	assert(!cache_file_globals.tags_loaded && global_tag_instances == NULL &&
		global_tag_count == 0 && cache_file_globals.tag_header == NULL);
	++lifecycle_owner_release_count;
	return __real_ps2_cache_release_map_owner();
}

ssize_t __real_read(int fd, void *buffer, size_t size);
ssize_t __wrap_read(int fd, void *buffer, size_t size)
{
	if (lifecycle_read_fault_armed) {
		if (!lifecycle_read_partial_seen) {
			size_t partial = size ? 1u : 0u;
			ssize_t got;
			if (!partial) return 0;
			got = __real_read(fd, buffer, partial);
			if (got > 0) lifecycle_read_partial_seen = 1;
			return got;
		}
		lifecycle_read_fault_armed = 0;
		lifecycle_read_eof_seen = 1;
		return 0;
	}
	return __real_read(fd, buffer, size);
}

int _stricmp(const char *left, const char *right)
{
	return strcasecmp(left, right);
}

boolean bink_playback_active(void) { return FALSE; }
void check_memory_status(struct memory_status *status, const char *location)
{
	(void)status; (void)location;
}
boolean custom_edition_cache_refuse(void const *header, const char *build,
	const char *path)
{
	(void)header; (void)build; (void)path;
	return FALSE;
}
boolean custom_edition_level_name(const char *name)
{
	(void)name;
	return FALSE;
}
struct cache_file_tag_header *custom_edition_cache_tags_load(
	const char *name, void *header)
{
	(void)name; (void)header;
	return NULL;
}
void custom_edition_cache_tags_unload(void) {}
void hud_hires_tags_unloaded(void) {}
void hud_hires_tags_loaded(void) {}
void texture_cache_open(void) {}
void texture_cache_close(void) {}
void sound_cache_open(void) {}
void sound_cache_close(void) {}
void mods_tags_loaded(const char *name) { (void)name; }
void mods_tags_unloaded(void) {}
void menu_tags_loaded(const char *name) { (void)name; }
void menu_tags_unloaded(void) {}
void pal_tags_loaded(const char *build) { (void)build; }
void powerup_render_bounds_tags_loaded(void) {}
void tags_header_register_vertex_and_index_buffers(
	struct cache_file_tag_header *header)
{
	assert(header == (struct cache_file_tag_header *)tag_cache);
	++register_count;
}
void tags_header_deregister_vertex_and_index_buffers(
	struct cache_file_tag_header *header)
{
	assert(header == NULL || header == (struct cache_file_tag_header *)tag_cache);
	if (!header)
		assert(!cache_file_globals.tags_loaded &&
			cache_file_globals.tag_header == NULL);
	++unload_count;
}

boolean map_share_downloading(const char *map_name)
{
	(void)map_name;
	return FALSE;
}

void display_error_damaged_media(void)
{
	fprintf(stderr, "CE lifecycle observed damaged-media callback\n");
}

static void precache_until_ready(const char *name)
{
	boolean first;
	/* The first call starts the production loader; the next observes its mount,
	 * matching CE's asynchronous precache contract without faking the callback. */
	first = cache_files_give_time_to_precache(name);
	printf("ce-lifecycle precache-start=%d loaded=%d mount=%d source=%d staged=%s ready=%d reload=%d owner=%lu scratch=%lu\n",
		first, cache_files_precache_map_loaded("ui"),
		lifecycle_service.mount.active, lifecycle_service.source.active,
		lifecycle_service.staged_map[0] ? lifecycle_service.staged_map : "-",
		lifecycle_service.preflight_ready, lifecycle_service.reload_pending,
		(unsigned long)lifecycle_service.map_arena->used,
		(unsigned long)lifecycle_service.section_scratch->used);
	assert(cache_files_give_time_to_precache(name));
	assert(cache_files_precache_map_loaded("ui"));
}

static int run_d20_host_oracle(const char *crc_case)
{
	const char *const scenario_name = "levels\\d20\\d20";
	const char *fault_tag = "B001";
	unsigned fault_index = 1;
	int outer_crc_case = 0;
	int inner_crc_case = 0;
	int visitor_failure_case = 0;
	const hcu_map_catalog_entry *entry = hcu_map_catalog_find("d20");
	struct scenario_structure_bsp_reference *references;
	unsigned char *b000_snapshot;
	unsigned bsp_index;
	unsigned reference_index;
	assert(entry != NULL && entry->bsp_count == 5u);
	assert(entry->bsp_catalog != NULL && entry->bsp_catalog[0].file_offset == 2048u &&
		entry->bsp_catalog[0].file_size == 5408768u);
	assert(ps2_cache_preflight_map(scenario_name));
	/* CE's precache API is asynchronous: one call starts/copies, a later call
	 * observes readiness, exactly like the UI lifecycle helper. */
	(void)cache_files_give_time_to_precache(scenario_name);
	assert(cache_files_give_time_to_precache(scenario_name));
	assert(cache_files_precache_map_loaded("d20"));
	loaded_datum = 0;
	assert(scenario_load(scenario_name));
	assert(global_scenario != NULL && global_scenario_index != NONE);
	assert(global_structure_bsp != NULL && global_collision_bsp != NULL &&
		global_bsp3d != NULL && global_game_globals != NULL);
	assert(global_structure_bsp_index == 0);
	assert(cache_file_globals.tags_loaded && global_tag_instances != NULL &&
		global_tag_count > 0);
	assert(lifecycle_service.mount.active && lifecycle_service.source.active);
	if (crc_case) {
		const char *tag_suffix = strstr(crc_case, "-B");
		assert(tag_suffix != NULL && strlen(tag_suffix + 1) == 4u);
		fault_tag = tag_suffix + 1;
		assert(fault_tag[0] == 'B' && fault_tag[1] >= '0' &&
			fault_tag[1] <= '9' && fault_tag[2] >= '0' &&
			fault_tag[2] <= '9' && fault_tag[3] >= '0' &&
			fault_tag[3] <= '9');
		fault_index = (unsigned)(fault_tag[1] - '0') * 100u +
			(unsigned)(fault_tag[2] - '0') * 10u +
			(unsigned)(fault_tag[3] - '0');
		assert(fault_index > 0 && fault_index < entry->bsp_count &&
			strlen(fault_tag) == 4u);
		outer_crc_case = strstr(crc_case, "outer-crc") != NULL;
		inner_crc_case = strstr(crc_case, "inner-crc") != NULL;
		visitor_failure_case = strstr(crc_case, "visitor-fail") != NULL;
		assert(outer_crc_case || inner_crc_case || visitor_failure_case);
		memcpy(lifecycle_d20_fault_tag, fault_tag, sizeof(lifecycle_d20_fault_tag));
	}
	references = (struct scenario_structure_bsp_reference *)
		global_scenario->structure_bsp_references.address;
	assert(references != NULL &&
		global_scenario->structure_bsp_references.count == entry->bsp_count);
	assert(lifecycle_service.map_arena->used > 0 &&
		lifecycle_service.map_arena->used <= lifecycle_service.map_arena->cap);
	assert(lifecycle_service.section_scratch->high <=
		lifecycle_service.section_scratch->cap);
	printf("ce-d20-oracle loaded scenario=%s bsp_index=%d tags=%ld owner=%lu owner_high=%lu scratch_high=%lu\n",
		scenario_name, global_structure_bsp_index, global_tag_count,
		(unsigned long)lifecycle_service.map_arena->used,
		(unsigned long)lifecycle_service.map_arena->high,
		(unsigned long)lifecycle_service.section_scratch->high);
	/* A late B001 stream failure must leave no candidate BSP published and
	 * reload B000 successfully in the same CE scenario. */
	b000_snapshot = (unsigned char *)malloc(entry->bsp_catalog[0].file_size);
	assert(b000_snapshot != NULL);
	memcpy(b000_snapshot, bsp_cache, entry->bsp_catalog[0].file_size);
	if (crc_case) {
		/* The Python runner corrupts either the enclosing HP2 CRC or the
		 * inner CBSP image CRC in the selected B001-B004 section, or asks the
		 * visitor wrapper to abort after its first candidate write. Keep CE's
		 * real switch/rollback path responsible for the result. */
		lifecycle_d20_fault_visit_count = 0;
		lifecycle_d20_fault_last_status = HP2_OK;
		if (visitor_failure_case) {
			lifecycle_bsp_failure_tag = lifecycle_d20_fault_tag;
			lifecycle_bsp_failure_injected = 0;
			lifecycle_bsp_sink_writes = 0;
			lifecycle_bsp_destination_witness = 0;
			lifecycle_bsp_failure_armed = 1;
			assert(!scenario_switch_structure_bsp((short)fault_index));
			assert(lifecycle_bsp_failure_injected &&
				!lifecycle_bsp_failure_armed && lifecycle_bsp_sink_writes > 0 &&
				lifecycle_bsp_destination_witness);
		} else {
			assert(!scenario_switch_structure_bsp((short)fault_index));
			assert(lifecycle_d20_fault_visit_count == 1);
			if (outer_crc_case)
				assert(lifecycle_d20_fault_last_status == HP2_ERR_CRC);
			else
				assert(lifecycle_d20_fault_last_status == HP2_OK);
		}
		assert(global_structure_bsp_index == 0 &&
			scenario_globals->structure_bsp_index == 0 &&
			global_structure_bsp == global_tag_instances[
				(short)references[0].structure_bsp.index].base_address);
		assert(global_collision_bsp != NULL && global_bsp3d != NULL &&
			memcmp(bsp_cache, b000_snapshot,
				entry->bsp_catalog[0].file_size) == 0);
		assert(lifecycle_service.mount.active && lifecycle_service.source.active &&
			lifecycle_service.section_scratch->used == 0);
		printf("ce-d20-oracle %s rejected %s and restored B000\n",
			crc_case, fault_tag);
		if (visitor_failure_case) {
			assert(scenario_switch_structure_bsp((short)fault_index));
			assert(global_structure_bsp_index == (short)fault_index &&
				scenario_globals->structure_bsp_index == (short)fault_index);
			assert(global_structure_bsp == global_tag_instances[
				(short)references[fault_index].structure_bsp.index].base_address);
			assert(global_collision_bsp != NULL && global_bsp3d != NULL &&
				lifecycle_service.mount.active && lifecycle_service.source.active &&
				lifecycle_service.section_scratch->used == 0);
			printf("ce-d20-oracle %s same-process retry loaded %s\n",
				crc_case, fault_tag);
		}
		free(b000_snapshot);
		scenario_unload();
		assert(global_scenario == NULL && global_structure_bsp == NULL &&
			global_collision_bsp == NULL && global_bsp3d == NULL &&
			!cache_file_globals.tags_loaded && global_tag_instances == NULL &&
			lifecycle_service.map_arena->used == 0 &&
			lifecycle_service.section_scratch->used == 0);
		hcu_map_service_shutdown(&lifecycle_service);
		return 0;
	}
	lifecycle_bsp_failure_tag = "B001";
	lifecycle_bsp_failure_injected = 0;
	lifecycle_bsp_sink_writes = 0;
	lifecycle_bsp_destination_witness = 0;
	lifecycle_bsp_failure_armed = 1;
	assert(!scenario_switch_structure_bsp(1));
	assert(lifecycle_bsp_failure_injected && !lifecycle_bsp_failure_armed &&
		lifecycle_bsp_sink_writes > 0 && lifecycle_bsp_destination_witness);
	assert(global_structure_bsp_index == 0 &&
		scenario_globals->structure_bsp_index == 0 &&
		global_structure_bsp == global_tag_instances[
			(short)references[0].structure_bsp.index].base_address);
	assert(global_collision_bsp != NULL && global_bsp3d != NULL);
	assert(memcmp(bsp_cache, b000_snapshot,
		entry->bsp_catalog[0].file_size) == 0);
	for (reference_index = 0; reference_index < entry->bsp_count;
		reference_index++) {
		void *base = global_tag_instances[(short)
			references[reference_index].structure_bsp.index].base_address;
		assert((reference_index == 0u) == (base != NULL));
	}
	assert(lifecycle_service.mount.active && lifecycle_service.source.active &&
		lifecycle_service.map_arena->used > 0 &&
		lifecycle_service.section_scratch->used == 0);
	free(b000_snapshot);
	puts("ce-d20-oracle B001 late-write failure restored B000; same-process retry remained available");
	/* Exercise each real CE BSP switch transaction, one destination at a time.
	 * The isolated host fixture overrides its BSP destination to 16 MiB so B003
	 * is representable; that buffer is not an EE placement proposal. */
	for (bsp_index = 1; bsp_index < entry->bsp_count; ++bsp_index) {
		assert(entry->bsp_catalog[bsp_index].file_size <= sizeof bsp_cache);
		assert(scenario_switch_structure_bsp((short)bsp_index));
		assert(global_structure_bsp_index == (short)bsp_index &&
			scenario_globals->structure_bsp_index == (short)bsp_index);
		assert(global_structure_bsp == global_tag_instances[
			(short)references[bsp_index].structure_bsp.index].base_address);
		assert(global_collision_bsp != NULL && global_bsp3d != NULL);
		for (reference_index = 0; reference_index < entry->bsp_count;
			reference_index++) {
			void *base = global_tag_instances[(short)
				references[reference_index].structure_bsp.index].base_address;
			assert((reference_index == bsp_index) == (base != NULL));
		}
		assert(lifecycle_service.mount.active && lifecycle_service.source.active);
		printf("ce-d20-oracle bsp-switch index=%u tag=%s source_bytes=%u parent_owner=%lu scratch_high=%lu\n",
			bsp_index, entry->bsp_catalog[bsp_index].section_tag,
			entry->bsp_catalog[bsp_index].file_size,
			(unsigned long)lifecycle_service.map_arena->used,
			(unsigned long)lifecycle_service.section_scratch->high);
	}
	scenario_unload();
	assert(global_scenario == NULL && global_scenario_index == NONE &&
		global_structure_bsp == NULL && global_collision_bsp == NULL &&
		global_bsp3d == NULL && global_game_globals == NULL);
	assert(!cache_file_globals.tags_loaded && global_tag_instances == NULL &&
		global_tag_count == 0 && cache_file_globals.tag_header == NULL);
	assert(!lifecycle_service.mount.active && !lifecycle_service.source.active &&
		lifecycle_service.source.reader.descriptor < 0);
	assert(lifecycle_service.map_arena->used == 0 &&
		lifecycle_service.section_scratch->used == 0);
	assert(lifecycle_owner_release_count == 1);
	puts("ce-d20-oracle scenario unload released CE globals and parent owner");
	hcu_map_service_shutdown(&lifecycle_service);
	return 0;
}

int main(int argc, char **argv)
{
	int cycle;
	assert(argc == 2 || argc == 3 || argc == 4);
	assert(ps2_animation_trace_bind(lifecycle_trace_events,
		LIFECYCLE_TRACE_CAPACITY));
	assert(ps2_animation_trace_bind_contexts(lifecycle_trace_contexts,
		LIFECYCLE_TRACE_CAPACITY));
	ps2_animation_trace_reset();
	setvbuf(stdout, NULL, _IONBF, 0);
	assert(file_set_default_root(argv[1]));
	/* Exercise the production service against fixed host owner/scratch spans;
	 * this fixture is lifecycle semantics, not a PS2-capacity assertion. */
	arena_init(&retail_owner, "CE lifecycle map owner", retail_owner_bytes,
		sizeof retail_owner_bytes);
	arena_init(&retail_section_scratch, "CE lifecycle decode scratch",
		retail_section_scratch_bytes, sizeof retail_section_scratch_bytes);
	lifecycle_layout.regions[MEM_LAYOUT_V2_STREAMING] = retail_owner;
	lifecycle_layout.regions[MEM_LAYOUT_V2_FRAME_SCRATCH] = retail_section_scratch;
	assert(hcu_map_service_init(&lifecycle_service, &lifecycle_layout,
		argv[1]) == 0);
	assert(tag_validate_bind_claims_buffer(retail_claims_bytes,
		sizeof retail_claims_bytes));
	cache_files_initialize();
	scenario_globals = &globals_fixture;
	scenario_globals->structure_bsp_index = NONE;
	global_tag_instances = tag_instances;
	global_tag_count = 0;
	if (argc == 4 && strcmp(argv[2], "owner-exhaustion") == 0) {
		char *end = NULL;
		unsigned long limited_cap = strtoul(argv[3], &end, 10);
		size_t original_cap = lifecycle_service.map_arena->cap;
		ctag_stream_info zero_ctag_info;
		assert(end && *end == 0 && limited_cap > 0 &&
			limited_cap < original_cap);
		lifecycle_service.map_arena->cap = (size_t)limited_cap;
		/* The Python runner derives this cap from actual HP2 section lengths,
		 * arena alignment, and the CTAG relocation count: HMAP/CRNG/CBIX fit,
		 * while the exact relocation-vector request is one byte too large. */
		assert(!ps2_cache_preflight_map("levels\\ui\\ui"));
		memset(&zero_ctag_info, 0, sizeof(zero_ctag_info));
		assert(lifecycle_service.map_arena->used == 0 &&
			lifecycle_service.section_scratch->used == 0 &&
			!lifecycle_service.source.active &&
			lifecycle_service.source.reader.descriptor < 0 &&
			!lifecycle_service.mount.active &&
			!lifecycle_service.preflight_ready &&
			!lifecycle_service.reload_pending &&
			lifecycle_service.staged_entry == NULL &&
			lifecycle_service.staged_map[0] == 0 &&
			memcmp(&lifecycle_service.ctag_info, &zero_ctag_info,
				sizeof(zero_ctag_info)) == 0 &&
			!cache_files_precache_map_loaded("ui"));
		lifecycle_service.map_arena->cap = original_cap;
		assert(ps2_cache_preflight_map("levels\\ui\\ui"));
		precache_until_ready("levels\\ui\\ui");
		loaded_datum = 0;
		assert(scenario_load("levels\\ui\\ui"));
		assert(global_scenario && global_structure_bsp && global_collision_bsp &&
			global_bsp3d && cache_file_globals.tags_loaded &&
			lifecycle_service.mount.active && lifecycle_service.source.active);
		scenario_unload();
		assert(!global_scenario && !global_structure_bsp &&
			!global_collision_bsp && !global_bsp3d &&
			!cache_file_globals.tags_loaded && !global_tag_instances &&
			lifecycle_service.map_arena->used == 0 &&
			lifecycle_service.section_scratch->used == 0 &&
			!lifecycle_service.mount.active && !lifecycle_service.source.active &&
			lifecycle_service.source.reader.descriptor < 0);
		puts("ce-lifecycle bounded-owner exhaustion rolled back relocation allocation; same-process scenario retry passed");
		hcu_map_service_shutdown(&lifecycle_service);
		return 0;
	}
#ifdef HCU_C1_REAL_PROFILE
	if (argc == 4 && strcmp(argv[2], "actual-profile") == 0) {
		assert(ps2_cache_preflight_map("levels\\ui\\ui"));
		precache_until_ready("levels\\ui\\ui");
		verify_ce_tag_read_failure_and_retry();
		verify_ce_tag_validation_failure_and_retry();
		lifecycle_bsp_failure_tag = "B000";
		lifecycle_bsp_failure_armed = 1;
		lifecycle_bsp_failure_injected = 0;
		lifecycle_bsp_sink_writes = 0;
		lifecycle_bsp_destination_witness = 0;
		assert(!scenario_load("levels\\ui\\ui"));
		assert(lifecycle_bsp_failure_injected && !lifecycle_bsp_failure_armed &&
			lifecycle_bsp_sink_writes > 0 && lifecycle_bsp_destination_witness);
		assert(ps2_cache_preflight_map("levels\\ui\\ui"));
		precache_until_ready("levels\\ui\\ui");
		assert(scenario_load("levels\\ui\\ui"));
		lifecycle_run_real_profile(argv[3]);
		scenario_unload();
		hcu_map_service_shutdown(&lifecycle_service);
		return 0;
	}
#endif
	if (argc >= 3 && strcmp(argv[2], "d20") == 0) {
#if defined(HCU_M2_D20_HOST_ORACLE)
		assert(argc == 3 || (argc == 4 &&
			(strlen(argv[3]) >= 15u &&
			 (memcmp(argv[3], "d20-outer-crc-B", 15) == 0 ||
			  memcmp(argv[3], "d20-inner-crc-B", 15) == 0 ||
			  memcmp(argv[3], "d20-visitor-fail-B", 18) == 0))));
		return run_d20_host_oracle(argc == 4 ? argv[3] : NULL);
#else
		assert(argc == 3);
		assert(!ps2_cache_preflight_map("levels\\d20\\d20"));
		puts("ce-d20-oracle production admission guard rejected d20");
		hcu_map_service_shutdown(&lifecycle_service);
		return 0;
#endif
	}

	for (cycle = 0; cycle < 2; ++cycle) {
		/* First request is explicit. The second is the deferred loader request
		 * retained by same-map preflight before the prior CE unload. */
		if (cycle == 0) {
			assert(ps2_cache_preflight_map("levels\\ui\\ui"));
			precache_until_ready("levels\\ui\\ui");
			verify_ce_tag_read_failure_and_retry();
			verify_ce_tag_validation_failure_and_retry();
		} else {
			/* The old map is already unpublished and its owner released. Fail
			 * the first HP2 read in deferred validation after one real byte. */
			unsigned long epoch_before_failed_preflight =
				lifecycle_trace_map_epoch();
			unsigned long epoch_after_failed_preflight;
			lifecycle_read_fault_armed = 1;
			assert(!cache_files_give_time_to_precache("levels\\ui\\ui"));
			epoch_after_failed_preflight = lifecycle_trace_map_epoch();
			assert(epoch_after_failed_preflight == epoch_before_failed_preflight);
			puts("ce-lifecycle trace-map-epoch failed-preflight-stable");
			assert(lifecycle_read_partial_seen && lifecycle_read_eof_seen &&
				!lifecycle_read_fault_armed);
			assert(!lifecycle_service.mount.active && !lifecycle_service.source.active &&
				lifecycle_service.source.reader.descriptor < 0 &&
				lifecycle_service.map_arena->used == 0 &&
				!lifecycle_service.staged_entry &&
				!lifecycle_service.preflight_ready &&
				!lifecycle_service.reload_pending &&
				!cache_files_precache_map_loaded("ui"));
			assert(global_scenario == NULL && global_structure_bsp == NULL &&
				global_collision_bsp == NULL && global_bsp3d == NULL &&
				!cache_file_globals.tags_loaded && global_tag_instances == NULL);
			assert(ps2_cache_preflight_map("levels\\ui\\ui"));
			precache_until_ready("levels\\ui\\ui");
			assert(lifecycle_trace_map_epoch() == epoch_before_failed_preflight + 1);
			puts("ce-lifecycle trace-map-epoch successful-remount-advanced");
		}
		loaded_datum = 0;
		if (cycle == 0) {
			/* Fail B000 only after the first decoded chunk has reached CE's
			 * real BSP destination. This is the initial scenario-load path, not
			 * the active-BSP switch transaction exercised by a50. */
			/* Earlier CTAG fault injection consumes and clears this selector. */
			lifecycle_bsp_failure_tag = "B000";
			lifecycle_bsp_failure_armed = 1;
			lifecycle_bsp_failure_injected = 0;
			lifecycle_bsp_sink_writes = 0;
			lifecycle_bsp_destination_witness = 0;
			assert(!scenario_load("levels\\ui\\ui"));
			assert(lifecycle_bsp_failure_injected &&
				!lifecycle_bsp_failure_armed && lifecycle_bsp_sink_writes > 0 &&
				lifecycle_bsp_destination_witness);
			assert(global_scenario == NULL && global_structure_bsp == NULL &&
				global_collision_bsp == NULL && global_bsp3d == NULL &&
				global_game_globals == NULL && global_scenario_index == NONE &&
				global_structure_bsp_index == NONE &&
				scenario_globals->structure_bsp_index == NONE);
			assert(!cache_file_globals.tags_loaded &&
				cache_file_globals.tag_header == NULL &&
				global_tag_instances == NULL && global_tag_count == 0);
			assert(!lifecycle_service.mount.active &&
				!lifecycle_service.source.active &&
				lifecycle_service.source.reader.descriptor < 0 &&
				lifecycle_service.map_arena->used == 0 &&
				lifecycle_service.section_scratch->used == 0);
			assert(lifecycle_owner_release_count == 4);
			assert(ps2_cache_preflight_map("levels\\ui\\ui"));
			precache_until_ready("levels\\ui\\ui");
			puts("ce-lifecycle initial B000 late-write failure rolled back; retry passed");
		}
		assert(scenario_load("levels\\ui\\ui"));
		assert(global_scenario != NULL && global_structure_bsp != NULL);
		assert(global_collision_bsp != NULL && global_bsp3d != NULL);
		assert(global_tag_instances != NULL && global_tag_count > 0);
		assert(cache_file_globals.tags_loaded);
		assert(lifecycle_service.mount.active && lifecycle_service.source.active);
		printf("ce-lifecycle cycle=%d scenario=%p bsp=%p tags=%ld owner=%lu\n",
			cycle, (void *)global_scenario, (void *)global_structure_bsp,
			global_tag_count, (unsigned long)lifecycle_service.map_arena->used);

		if (cycle == 0) {
			lifecycle_active_map_snapshot active_before;
			sha256_context profile_sha;
			uint8_t profile_digest[32];
			lifecycle_make_profile();
			lifecycle_pin_profile();
			assert(hcu_map_service_register_profile(&lifecycle_service,
				"bloodgulch", 0x12345, lifecycle_profile_read,
				&lifecycle_profile_source, lifecycle_profile_source.size,
				lifecycle_profile_pin,lifecycle_profile_compatibility,"bloodgulch"));
			lifecycle_snapshot_active_map(&active_before);
			assert(!ps2_cache_preflight_map("levels\\ui\\ui"));
			assert(memcmp(&lifecycle_service, &active_before.service_state,
				sizeof(lifecycle_service)) == 0);
			lifecycle_profile_image[208] ^= 1;
			sha256_init(&profile_sha);
			sha256_update(&profile_sha, lifecycle_profile_image + 208, 4);
			sha256_final(&profile_sha, profile_digest);
			memcpy(lifecycle_profile_image + 144, profile_digest, 32);
			assert(!hcu_map_service_register_profile(&lifecycle_service, "ui",
				0x12345, lifecycle_profile_read, &lifecycle_profile_source,
				lifecycle_profile_source.size, lifecycle_profile_pin,
				lifecycle_profile_compatibility,"ui"));
			assert(memcmp(&lifecycle_service, &active_before.service_state,
				sizeof(lifecycle_service)) == 0);
			lifecycle_make_profile(); lifecycle_pin_profile();
			assert(!hcu_map_service_register_profile(&lifecycle_service, "ui",
				0x12345, lifecycle_profile_read, &lifecycle_profile_source,
				lifecycle_profile_source.size, lifecycle_profile_pin,
				lifecycle_profile_compatibility,"beavercreek"));
			assert(memcmp(&lifecycle_service, &active_before.service_state,
				sizeof(lifecycle_service)) == 0);
			assert(hcu_map_service_register_profile(&lifecycle_service, "ui",
				0x12345, lifecycle_profile_read, &lifecycle_profile_source,
				lifecycle_profile_source.size, lifecycle_profile_pin,
				lifecycle_profile_compatibility,"ui"));
			lifecycle_snapshot_active_map(&active_before);
			lifecycle_profile_image[208] ^= 1;
			sha256_init(&profile_sha);
			sha256_update(&profile_sha, lifecycle_profile_image + 208, 4);
			sha256_final(&profile_sha, profile_digest);
			memcpy(lifecycle_profile_image + 144, profile_digest, 32);
			assert(!ps2_cache_preflight_map("levels\\ui\\ui"));
			assert(memcmp(&lifecycle_service,
				&active_before.service_state, sizeof(lifecycle_service)) == 0);
			lifecycle_assert_active_map_snapshot(&active_before);
			lifecycle_make_profile(); lifecycle_pin_profile();
			puts("ce-lifecycle rejected corrupt registered profile before same-map reuse");
			lifecycle_snapshot_active_map(&active_before);
			/* A non-qualified gameplay map must not disturb the active UI map,
			 * even though both identities are present in the immutable catalog. */
			hcu_map_service expected_pending;
			lifecycle_snapshot_active_map(&active_before);
			assert(!ps2_cache_preflight_map(
				"levels\\test\\bloodgulch\\bloodgulch"));
			assert(memcmp(&lifecycle_service,
				&active_before.service_state, sizeof(lifecycle_service)) == 0);
			lifecycle_assert_active_map_snapshot(&active_before);
			puts("ce-lifecycle rejected gameplay preflight preserved active UI snapshot");

			/* CE preflight-before-unload for the same map may set only the
			 * private deferred-reload identity; live CE/owner bytes stay fixed. */
			assert(ps2_cache_preflight_map("levels\\ui\\ui"));
			lifecycle_assert_active_map_snapshot(&active_before);
			expected_pending = active_before.service_state;
			expected_pending.staged_entry = hcu_map_catalog_find("ui");
			memcpy(expected_pending.staged_map, "ui", sizeof("ui"));
			expected_pending.reload_pending = 1;
			assert(expected_pending.staged_entry != NULL &&
				memcmp(&lifecycle_service, &expected_pending,
					sizeof(lifecycle_service)) == 0);
			puts("ce-lifecycle same-map preflight changed only deferred request state");
#ifdef HCU_C1_REAL_PROFILE
#endif
		}
		{
			unsigned long epoch_before_unload = lifecycle_trace_map_epoch();
			scenario_unload();
			assert(lifecycle_trace_map_epoch() == epoch_before_unload + 1);
			puts("ce-lifecycle trace-map-epoch unload-advanced");
		}
		assert(global_scenario == NULL && global_structure_bsp == NULL);
		assert(global_collision_bsp == NULL && global_bsp3d == NULL);
		assert(global_game_globals == NULL && global_scenario_index == NONE);
		assert(global_structure_bsp_index == NONE &&
			scenario_globals->structure_bsp_index == NONE);
		assert(!cache_file_globals.tags_loaded && global_tag_instances == NULL &&
			global_tag_count == 0 && cache_file_globals.tag_header == NULL);
		assert(!lifecycle_service.mount.active && !lifecycle_service.source.active);
		assert(lifecycle_service.source.reader.descriptor < 0);
		assert(lifecycle_service.map_arena->used == 0);
		assert(!cache_files_precache_map_loaded("ui"));
	}
	assert(lifecycle_owner_release_count == 6);
	hcu_map_service_shutdown(&lifecycle_service);
	puts("same-process deferred UI reload passed");
	return 0;
}
