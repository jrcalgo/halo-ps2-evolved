#include "cseries.h"
#include "scenario/scenario.h"
#include "scenario/fog_definitions.h"
#include "scenario/scenario_definitions.h"
#include "structures/structure_bsp_definitions.h"
#include "physics/collision_bsp.h"
#include "physics/collisions.h"
#include "physics/collision_usage.h"
#include "physics/breakable_surfaces.h"
#include "physics/physics.h"
#include "physics/collision_models.h"
#include "structures/structures.h"
#include "physics/collision_bsp_definitions.h"
#include "cache/cache_files.h"
#include "tag_files/tag_groups.h"
#ifdef HCU_BSP_RETAIL_INTEGRATION
#include "game/players.h"
#endif
#ifdef HCU_BSP_RETAIL_INTEGRATION
#include <xtl.h>
#include "tag_schema.h"
#define tag_validate_structure_bsp tag_validate_structure_bsp_actual
#define tag_validate_tags tag_validate_tags_actual
#include "../submodules/halo-ce-universal/port/linux/game/tag_validate.c"
#undef tag_validate_tags
#undef tag_validate_structure_bsp
boolean tag_validate_structure_bsp_actual(long tag_index, void *base, long size);
boolean tag_validate_tags_actual(void *tag_header, long tag_data_size,
	long file_length, char const *map_name);
#endif
#include "../submodules/halo-ce-universal/source/cache/cache_files.c"

#ifdef HCU_BSP_RETAIL_INTEGRATION
/* Test-only seam: the lifecycle fixture can reject once after the real CE
 * validator has accepted the fully materialized image but before cache_files.c
 * publishes tag_header/tags_loaded/global_tag_instances. */
int hcu_bsp_fixture_reject_tag_validation_once;
int hcu_bsp_fixture_tag_validation_rejected;
boolean tag_validate_tags(void *tag_header, long tag_data_size,
	long file_length, char const *map_name)
{
	boolean valid = tag_validate_tags_actual(tag_header, tag_data_size,
		file_length, map_name);
	if (valid && hcu_bsp_fixture_reject_tag_validation_once) {
		hcu_bsp_fixture_reject_tag_validation_once = 0;
		assert(tag_header == physical_memory_get_tag_cache_base_address());
		assert(cache_file_globals.tag_header == NULL &&
			!cache_file_globals.tags_loaded && global_tag_instances == NULL &&
			global_tag_count == 0);
		assert(((unsigned char *)tag_header)[0] != 0xCD ||
			((unsigned char *)tag_header)[1] != 0xCD ||
			((unsigned char *)tag_header)[2] != 0xCD ||
			((unsigned char *)tag_header)[3] != 0xCD);
		hcu_bsp_fixture_tag_validation_rejected = 1;
		return FALSE;
	}
	return valid;
}
#endif

/* Keep the host fixture's file-buffer ownership on libc, not CE debug heaps. */
#undef malloc
#undef free

#ifdef HCU_BSP_RETAIL_INTEGRATION
#include "halo_ps2_cache.h"
#include "stream/ctag_map_source.h"
#include "stream/ctag_mount.h"
#include "stream/ctag_ps2_backend.h"
#include "stream/hcu_map_service.h"
#include "stream/sha256.h"
#include "stream/file.h"
#include "world/section.h"
#include <stdlib.h>
#include "hcu_collision_golden.h"
#include "hcu_player_pvs_golden.h"
#include "hcu_sound_pas_golden.h"
#include "hcu_fog_plane_golden.h"
typedef char fixture_structure_bsp_size_assert[
	sizeof(struct structure_bsp) == 648 ? 1 : -1];
typedef char fixture_structure_bsp_clusters_offset_assert[
	offsetof(struct structure_bsp, clusters) == 308 ? 1 : -1];
typedef char fixture_structure_bsp_cluster_data_offset_assert[
	offsetof(struct structure_bsp, cluster_data) == 320 ? 1 : -1];
typedef char fixture_structure_bsp_sound_cluster_data_offset_assert[
	offsetof(struct structure_bsp, sound_cluster_data) == 532 ? 1 : -1];
typedef char fixture_structure_bsp_fog_planes_offset_assert[
	offsetof(struct structure_bsp, fog_planes) == 376 ? 1 : -1];
typedef char fixture_structure_bsp_fog_regions_offset_assert[
	offsetof(struct structure_bsp, fog_regions) == 388 ? 1 : -1];
typedef char fixture_structure_bsp_fog_palette_offset_assert[
	offsetof(struct structure_bsp, fog_palette) == 400 ? 1 : -1];
typedef char fixture_structure_bsp_weather_palette_offset_assert[
	offsetof(struct structure_bsp, weather_palette) == 436 ? 1 : -1];
typedef char fixture_structure_fog_plane_size_assert[
	sizeof(struct structure_fog_plane) == 0x20 ? 1 : -1];
typedef char fixture_structure_fog_region_size_assert[
	sizeof(struct structure_fog_region) == 0x28 ? 1 : -1];
typedef char fixture_structure_fog_region_weather_offset_assert[
	offsetof(struct structure_fog_region, weather_palette_index) == 0x26 ? 1 : -1];
typedef char fixture_structure_fog_palette_entry_size_assert[
	sizeof(struct structure_fog_palette_entry) == 0x88 ? 1 : -1];
typedef char fixture_tag_data_address_offset_assert[
	offsetof(struct tag_data, address) == 12 ? 1 : -1];
#define TAG_CACHE_BYTES (16u * 1024u * 1024u)
#ifndef BSP_CACHE_BYTES
#define BSP_CACHE_BYTES (8u * 1024u * 1024u)
#endif
#define OWNER_ARENA_BYTES (16u * 1024u * 1024u)
#define BSP_SCRATCH_BYTES (16u * 1024u * 1024u)
#define DIRECT_SECTION_SCRATCH_BYTES 124224u
#else
#define TAG_CACHE_BYTES 1024u
#define BSP_CACHE_BYTES 4096u
#endif

#include <assert.h>
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#ifdef HCU_BSP_RETAIL_INTEGRATION
#include <unistd.h>
#endif

static struct scenario scenario_fixture;
static struct scenario_structure_bsp_reference references[2];
static struct scenario_globals globals_fixture;
static unsigned char tag_cache[TAG_CACHE_BYTES] __attribute__((aligned(16)));
static unsigned char bsp_cache[BSP_CACHE_BYTES] __attribute__((aligned(16)));
struct cache_file_tag_instance tag_instances[2];
struct cache_file_tag_instance *global_tag_instances = tag_instances;
struct scenario_globals *scenario_globals = &globals_fixture;
extern struct structure_bsp *global_structure_bsp;

void *csmemset(void *buffer, long value, unsigned long size)
{
	return __builtin_memset(buffer, (int)value, (size_t)size);
}
void *csmemcpy(void *destination, const void *source, unsigned long size)
{
	return __builtin_memcpy(destination, source, (size_t)size);
}
long csmemcmp(const void *left, const void *right, unsigned long size)
{
	return __builtin_memcmp(left, right, (size_t)size);
}
long csstrcmp(const char *left, const char *right)
{
	return __builtin_strcmp(left, right);
}
unsigned long csstrlen(const char *value)
{
	return (unsigned long)__builtin_strlen(value);
}
void *debug_malloc(unsigned int size, boolean clear, const char *file, long line)
{
	void *result;
	(void)file; (void)line;
	result = malloc(size);
	if (result && clear) __builtin_memset(result, 0, size);
	return result;
}
void debug_free(void *pointer, const char *file, long line)
{
	(void)file; (void)line;
	free(pointer);
}

static int loaded_datum = -1;
static int fail_schema_mask;
static int fail_verify_mask;
static int unload_count;
static int load_count;
static int verify_count;
static int register_count;
static int schema_count;
static int menu_count;
static int error_count;
static int time_stop_count;
static int time_start_count;
static int collision_off_count;
static int collision_on_count;
static int disconnect_count;
static int reconnect_count;
static byte retail_breakable_surface_flags[MAXIMUM_BREAKABLE_SURFACES_PER_MAP / 8];
static int retail_collision_map_id;
static int retail_sound_environment_query_count;

void hcu_test_set_sound_camera_cluster(short local_player_index,
	short cluster_index, real_point3d const *position);
void hcu_test_compute_combined_pas(unsigned long *out_words, size_t word_count);
boolean hcu_test_location_potentially_audible(short cluster_index);

boolean debug_sound_environment = FALSE;
void render_debug_string(boolean high_res, const char *text)
{
	(void)high_res;
	(void)text;
}

/* This transaction fixture has no gameplay tick or breakable-surface damage.
 * All bits set represents CE's fresh-map, still-extant state; it is not an
 * implementation of the game-state-backed breakable-surface subsystem. */
byte *breakable_surface_flags_get(void)
{
	return retail_breakable_surface_flags;
}

short global_current_collision_user_depth = 1;
short global_current_collision_users[MAXIMUM_COLLISION_USER_STACK_DEPTH];
static unsigned forbidden_object_adapter_calls;
static boolean hcu_player_pvs_object_lookup_enabled;
extern unsigned hcu_test_real_object_lookup_count;
void *hcu_test_real_object_get_and_verify_type(
	long object_index, unsigned long valid_type_flags);

void hcu_test_players_compute_combined_pvs(
	unsigned long *combined_pvs, boolean local_player_only);

static void retail_fixture_forbid_object_path(void)
{
	++forbidden_object_adapter_calls;
	abort();
}

/* collision_test_vector() retains a conditional object branch in this host
 * link. The structure-only probe must never enter it; these fail-closed
 * adapters make accidental broadening an immediate test failure. */
void structure_cluster_marker_begin(void) { retail_fixture_forbid_object_path(); }
boolean structure_cluster_mark(short cluster_index)
{
	(void)cluster_index; retail_fixture_forbid_object_path(); return FALSE;
}
void structure_cluster_marker_end(void) { retail_fixture_forbid_object_path(); }
void object_marker_begin(void) { retail_fixture_forbid_object_path(); }
void object_marker_end(void) { retail_fixture_forbid_object_path(); }
long cluster_get_first_collideable_object(long *reference_index, short cluster_index)
{
	(void)reference_index; (void)cluster_index;
	retail_fixture_forbid_object_path(); return NONE;
}
long cluster_get_next_collideable_object(long *reference_index)
{
	(void)reference_index; retail_fixture_forbid_object_path(); return NONE;
}
boolean object_mark_function(long object_index)
{
	(void)object_index; retail_fixture_forbid_object_path(); return FALSE;
}
void *object_get_and_verify_type(long object_index, unsigned long valid_type_flags)
{
	if (hcu_player_pvs_object_lookup_enabled)
		return hcu_test_real_object_get_and_verify_type(
			object_index, valid_type_flags);
	(void)object_index; (void)valid_type_flags;
	retail_fixture_forbid_object_path(); return NULL;
}
boolean fast_vector_intersects_sphere(real_point3d const *point,
	real_vector3d const *vector, real_point3d const *center, real radius)
{
	(void)point; (void)vector; (void)center; (void)radius;
	retail_fixture_forbid_object_path(); return FALSE;
}
boolean physics_instance_new(struct physics_instance *instance, long object_index)
{
	(void)instance; (void)object_index;
	retail_fixture_forbid_object_path(); return FALSE;
}
boolean physics_test_vector(struct physics_instance const *instance,
	real_point3d const *point, real_vector3d const *vector,
	struct physics_test_vector_result *result)
{
	(void)instance; (void)point; (void)vector; (void)result;
	retail_fixture_forbid_object_path(); return FALSE;
}
boolean collision_model_instance_new(struct collision_model_instance *instance,
	long object_index)
{
	(void)instance; (void)object_index;
	retail_fixture_forbid_object_path(); return FALSE;
}
boolean collision_model_test_vector(
	struct collision_model_instance const *instance, unsigned long flags,
	real_point3d const *point, real_vector3d const *vector,
	struct collision_model_test_vector_result *result)
{
	(void)instance; (void)flags; (void)point; (void)vector; (void)result;
	retail_fixture_forbid_object_path(); return FALSE;
}
real_plane3d *matrix4x3_transform_plane(real_matrix4x3 const *matrix,
	real_plane3d const *plane, real_plane3d *result)
{
	(void)matrix; (void)plane; (void)result;
	retail_fixture_forbid_object_path(); return NULL;
}


#ifdef HCU_BSP_RETAIL_INTEGRATION
#define RETAIL_MAX_BSP_REFS 16u
static unsigned retail_offset[RETAIL_MAX_BSP_REFS];
static unsigned retail_size[RETAIL_MAX_BSP_REFS];
static unsigned retail_ref_count;
static int fail_load_index;
static int fail_load_also_index;
static unsigned selected_order[128];
static unsigned selected_count;
static unsigned successful_bsp_sections;
static unsigned cluster_query_count;
static unsigned collision_query_count;
static unsigned ce_collision_wrapper_query_count;
static unsigned sound_obstruction_query_count;
static long sound_obstruction_fixture_tick = 1000;

void hcu_test_compute_sound_obstruction(short camera_cluster,
	short source_cluster, long tick, real distance,
	real *obstruction, real *occlusion, unsigned *collision_calls);
static size_t direct_visit_sink_bytes[RETAIL_MAX_BSP_REFS];
static int direct_visit_succeeded[RETAIL_MAX_BSP_REFS];
static const char *fail_section_once;
static int resource_read_fail_after_bytes = -1;
static int resource_read_partial_seen;
static int resource_read_eof_seen;
static ctag_mount retail_mount;
static ctag_map_source retail_source;
static hcu_map_service direct_visit_service;
static arena_t retail_owner;
static arena_t retail_bsp_scratch;
static arena_t retail_section_scratch;
static unsigned char retail_owner_bytes[OWNER_ARENA_BYTES] __attribute__((aligned(64)));
static unsigned char retail_bsp_scratch_bytes[BSP_SCRATCH_BYTES] __attribute__((aligned(16)));
static unsigned char retail_section_scratch_bytes[131072] __attribute__((aligned(64)));
static unsigned char retail_claims_bytes[4u * 1024u * 1024u] __attribute__((aligned(16)));

typedef struct retail_bsp_snapshot {
	short global_index;
	short scenario_index;
	struct structure_bsp *structure;
	struct collision_bsp *collision;
	struct bsp3d *bsp3d;
	void *header;
	void *tag_bases[RETAIL_MAX_BSP_REFS];
	unsigned long owner_used;
	unsigned long scratch_used;
	unsigned mount_bsp_active;
	unsigned image_bytes;
	unsigned char image_sha256[32];
} retail_bsp_snapshot;

static void retail_bsp_digest(unsigned image_bytes, unsigned char digest[32])
{
	sha256_context context;
	assert(image_bytes <= sizeof bsp_cache);
	sha256_init(&context);
	sha256_update(&context, bsp_cache, image_bytes);
	sha256_final(&context, digest);
}

static void assert_parent_scratch_released(void);
int hcu_map_service_test_visit_section(void *context, const char *path,
	const char *tag, ctag_bsp_sink_fn sink, void *sink_context,
	size_t *raw_size);
void hcu_map_service_test_reset_visit_count(void);
unsigned hcu_map_service_test_visit_count(void);
size_t hcu_map_service_test_last_sink_bytes(void);
static int direct_visitor_mode;
static int direct_inner_crc_mode;
static int direct_rebase_mode;
int hcu_test_before_bsp_visit(const char *tag);
void hcu_test_after_bsp_visit(const char *tag, int succeeded);

static retail_bsp_snapshot capture_retail_bsp_snapshot(unsigned index)
{
	retail_bsp_snapshot snapshot;
	unsigned i;
	assert(index < retail_ref_count && global_structure_bsp != NULL);
	memset(&snapshot, 0, sizeof(snapshot));
	snapshot.global_index = global_structure_bsp_index;
	snapshot.scenario_index = scenario_globals->structure_bsp_index;
	snapshot.structure = global_structure_bsp;
	snapshot.collision = global_collision_bsp;
	snapshot.bsp3d = global_bsp3d;
	snapshot.header = cache_file_globals.structure_bsp_header;
	for (i = 0; i < retail_ref_count; ++i)
		snapshot.tag_bases[i] = global_tag_instances[(short)references[i].structure_bsp.index].base_address;
	snapshot.owner_used = retail_owner.used;
	snapshot.scratch_used = retail_bsp_scratch.used;
	snapshot.mount_bsp_active = retail_mount.bsp_active;
	snapshot.image_bytes = retail_size[index];
	retail_bsp_digest(snapshot.image_bytes, snapshot.image_sha256);
	return snapshot;
}

static void assert_retail_bsp_snapshot(const retail_bsp_snapshot *snapshot)
{
	unsigned i;
	unsigned char digest[32];
	assert(global_structure_bsp_index == snapshot->global_index);
	assert(scenario_globals->structure_bsp_index == snapshot->scenario_index);
	assert(global_structure_bsp == snapshot->structure);
	assert(global_collision_bsp == snapshot->collision);
	assert(global_bsp3d == snapshot->bsp3d);
	assert(cache_file_globals.structure_bsp_header == snapshot->header);
	for (i = 0; i < retail_ref_count; ++i)
		assert(global_tag_instances[(short)references[i].structure_bsp.index].base_address == snapshot->tag_bases[i]);
	assert(retail_owner.used == snapshot->owner_used);
	assert(retail_bsp_scratch.used == snapshot->scratch_used);
	assert(retail_mount.bsp_active == snapshot->mount_bsp_active);
	retail_bsp_digest(snapshot->image_bytes, digest);
	assert(memcmp(digest, snapshot->image_sha256, sizeof(digest)) == 0);
}

static void retry_candidate_and_restore(unsigned candidate,
	const retail_bsp_snapshot *baseline)
{
	assert(scenario_switch_structure_bsp((short)candidate) == TRUE);
	assert_parent_scratch_released();
	assert(global_structure_bsp_index == (short)candidate);
	assert(scenario_switch_structure_bsp(0) == TRUE);
	assert_parent_scratch_released();
	assert_retail_bsp_snapshot(baseline);
}

static unsigned bsp_tag_index(const char *tag)
{
	assert(tag && tag[0] == 'B' && tag[1] >= '0' && tag[1] <= '9' &&
		tag[2] >= '0' && tag[2] <= '9' && tag[3] >= '0' &&
		tag[3] <= '9' && tag[4] == '\0');
	return (unsigned)(tag[1] - '0') * 100u +
		(unsigned)(tag[2] - '0') * 10u + (unsigned)(tag[3] - '0');
}

int hcu_test_before_bsp_visit(const char *tag)
{
	unsigned index = bsp_tag_index(tag);
	assert(direct_visitor_mode && index < retail_ref_count);
	assert(selected_count < sizeof(selected_order) / sizeof(selected_order[0]));
	selected_order[selected_count++] = index;
	return fail_load_index == (int)index || fail_load_also_index == (int)index;
}

void hcu_test_after_bsp_visit(const char *tag, int succeeded)
{
	unsigned index = bsp_tag_index(tag);
	assert(direct_visitor_mode && index < retail_ref_count);
	direct_visit_sink_bytes[index] = hcu_map_service_test_last_sink_bytes();
	direct_visit_succeeded[index] = succeeded;
	if (succeeded) {
		loaded_datum = (int)index;
		++successful_bsp_sections;
	}
}

static void overwrite_file(const char *destination, const char *source)
{
	FILE *input = fopen(source, "rb");
	FILE *output;
	unsigned char buffer[32768];
	size_t bytes;
	assert(input != NULL);
	output = fopen(destination, "wb");
	assert(output != NULL);
	while ((bytes = fread(buffer, 1, sizeof buffer, input)) != 0)
		assert(fwrite(buffer, 1, bytes, output) == bytes);
	assert(!ferror(input));
	assert(fclose(input) == 0);
	assert(fclose(output) == 0);
}
#endif

void *tag_block_get_element_with_size(struct tag_block const *block,
	long index, long element_size)
{
	(void)block; (void)index; (void)element_size;
	return NULL;
}

char temporary[256];
char *csprintf(char *buffer, char *format, ...)
{
	(void)format;
	return buffer;
}
char *tag_to_string(tag value, char *buffer)
{
	(void)value;
	buffer[0] = '\0';
	return buffer;
}
void *tag_empty_data(void) { static unsigned char empty[16]; return empty; }
boolean custom_edition_structure_bsp_reference_valid(
	struct scenario_structure_bsp_reference const *reference)
{
	(void)reference; return FALSE;
}
boolean custom_edition_structure_bsp_load(struct structure_bsp *structure)
{
	(void)structure; return FALSE;
}
void custom_edition_structure_bsp_unload(void) {}

static struct structure_bsp *structure_at(void)
{
	return (struct structure_bsp *)(bsp_cache + 256);
}

static struct collision_bsp *collision_at(void)
{
	return (struct collision_bsp *)(bsp_cache + 1024);
}

void *physical_memory_get_tag_cache_base_address(void) { return tag_cache; }
unsigned long physical_memory_get_tag_cache_size(void) { return sizeof tag_cache; }
void *physical_memory_get_structure_bsp_cache_base_address(void) { return bsp_cache; }
unsigned long physical_memory_get_structure_bsp_cache_size(void) { return sizeof bsp_cache; }

boolean custom_edition_cache_tags_loaded(void) { return FALSE; }

#ifdef HCU_BSP_RETAIL_INTEGRATION
void SyncDCache(const void *start, const void *end)
{
	(void)start; (void)end;
}

void tag_validate_report(char const *message)
{
	++error_count;
	if (message) fprintf(stderr, "CE tag validator: %s\n", message);
}

char *csstrcat(char *left, char const *right)
{
	return strcat(left, right);
}
#endif

boolean tag_validate_structure_bsp(long tag_index, void *base, long size)
{
	++schema_count;
#ifdef HCU_BSP_RETAIL_INTEGRATION
	assert((short)tag_index >= 0 && (short)tag_index < global_tag_count);
#else
	assert(tag_index >= 0 && tag_index < 2);
#endif
#ifdef HCU_BSP_RETAIL_INTEGRATION
	assert(base == bsp_cache && size >= (long)sizeof(struct cache_file_structure_bsp_header) &&
		(size_t)size <= sizeof bsp_cache);
	{
		struct cache_file_structure_bsp_header *header =
			(struct cache_file_structure_bsp_header *)base;
		/* This is the real CE cache-load boundary after the PS2 adapter has
		 * supplied the retail CBSP. Xbox renderer arrays must be canonical empty
		 * values before CE continues into range and schema validation. */
		assert(header->signature == CACHE_FILE_STRUCTURE_BSP_HEADER_SIGNATURE);
		assert(header->vertex_buffer_count == 0 && header->vertex_buffers == NULL);
		assert(header->index_buffer_count == 0 && header->index_buffers == NULL);
	}
#else
	assert(base == bsp_cache && size == (long)sizeof bsp_cache);
#endif
#ifdef HCU_BSP_RETAIL_INTEGRATION
	return loaded_datum >= 0 &&
		tag_validate_structure_bsp_actual(tag_index, base, size) &&
		!(fail_schema_mask & (1 << loaded_datum));
#else
	return !(fail_schema_mask & (1 << tag_index));
#endif
}

#ifndef HCU_BSP_RETAIL_INTEGRATION
short cache_file_read(long tag_index, long offset, long size, void *buffer,
	boolean *completion, boolean blocking)
{
	struct cache_file_structure_bsp_header *header;
	struct structure_bsp *structure;
	int datum = offset == references[0].file_offset ? 0 :
		offset == references[1].file_offset ? 1 : -1;
	(void)tag_index; (void)blocking;
	assert(datum >= 0 && size == (long)sizeof bsp_cache && buffer == bsp_cache);
	++load_count;
	loaded_datum = datum;
	memset(buffer, 0, (size_t)size);
	header = (struct cache_file_structure_bsp_header *)buffer;
	structure = structure_at();
	header->base_address = structure;
	header->vertex_buffer_count = 0;
	header->vertex_buffers = NULL;
	header->index_buffer_count = 0;
	header->index_buffers = NULL;
	header->signature = CACHE_FILE_STRUCTURE_BSP_HEADER_SIGNATURE;
	structure->collision_bsp.count = 1;
	structure->collision_bsp.address = collision_at();
	structure->vehicle_floor = (real)(datum + 1);
	*completion = TRUE;
	return NONE;
}
#else
static uint8_t *load_package_section(void *context, arena_t *owner,
	const char *pack_path, const char *section_tag, size_t *raw_size,
	int optional)
{
	uint8_t *payload;
	int bsp_index = -1;
	(void)context;
	if (fail_section_once && section_tag &&
		strcmp(fail_section_once, section_tag) == 0) {
		fail_section_once = NULL;
		return NULL;
	}
	if (section_tag && section_tag[0] == 'B' &&
		section_tag[1] >= '0' && section_tag[1] <= '9' &&
		section_tag[2] >= '0' && section_tag[2] <= '9' &&
		section_tag[3] >= '0' && section_tag[3] <= '9' &&
		section_tag[4] == '\0')
		bsp_index = (section_tag[1] - '0') * 100 +
			(section_tag[2] - '0') * 10 + (section_tag[3] - '0');
	if (bsp_index >= 0)
	{
		if ((unsigned)bsp_index >= retail_ref_count) return NULL;
		assert(selected_count < sizeof(selected_order) / sizeof(selected_order[0]));
		selected_order[selected_count++] = (unsigned)bsp_index;
		if (fail_load_index == bsp_index || fail_load_also_index == bsp_index)
			return NULL;
	}
	payload = world_load_section_with_scratch(owner,
		&retail_section_scratch, pack_path, section_tag, raw_size, optional);
	if (!payload || !*raw_size) return NULL;
	if (bsp_index >= 0) {
		loaded_datum = bsp_index;
		++successful_bsp_sections;
	}
	return payload;
}

/* The host file-reader uses read(2) after seeking the retained map descriptor.
 * Wrap only that descriptor so the production CE -> cache adapter -> source
 * path observes a true partial transfer followed by EOF. */
ssize_t __real_read(int fd, void *buffer, size_t size);
ssize_t __wrap_read(int fd, void *buffer, size_t size)
{
	if (resource_read_fail_after_bytes >= 0 && retail_source.active &&
		fd == retail_source.reader.descriptor) {
		size_t partial = (size_t)resource_read_fail_after_bytes;
		if (partial > size) partial = size;
		if (partial) {
			/* The next read in file_reader_read_at's completion loop is EOF. */
			resource_read_fail_after_bytes = 0;
			ssize_t got = __real_read(fd, buffer, partial);
			if (got > 0) resource_read_partial_seen = 1;
			return got;
		}
		resource_read_fail_after_bytes = -1;
		resource_read_eof_seen = 1;
		return 0;
	}
	return __real_read(fd, buffer, size);
}
#endif

void structure_bsp_header_register_vertex_buffers(
	struct cache_file_structure_bsp_header *header)
{
	assert(header == (struct cache_file_structure_bsp_header *)bsp_cache);
	++register_count;
}

void structure_bsp_header_deregister_vertex_buffers(
	struct cache_file_structure_bsp_header *header)
{
	assert(header == (struct cache_file_structure_bsp_header *)bsp_cache);
	++unload_count;
}

int SwitchToThread(void) { return 0; }
unsigned long system_milliseconds(void) { return 0; }
long sound_render_time(void) { return 0; }
void sound_idle(void) { assert(!"unexpected asynchronous BSP read"); }

#ifdef HCU_BSP_RETAIL_INTEGRATION
#define structure_bsp_port_verify structure_bsp_port_verify_ce
#include "../submodules/halo-ce-universal/source/structures/structure_bsp_definitions.c"
#undef structure_bsp_port_verify
#endif

boolean structure_bsp_port_verify(struct structure_bsp const *structure)
{
#ifdef HCU_BSP_RETAIL_INTEGRATION
	boolean valid = structure_bsp_port_verify_ce(structure);
	++verify_count;
	return valid && loaded_datum >= 0 && !(fail_verify_mask & (1 << loaded_datum));
#else
	int datum = structure == structure_at() ? loaded_datum : -1;
	++verify_count;
	return datum >= 0 &&
		!(fail_verify_mask & (1 << datum));
#endif
}

void display_assert(char *information, char *file, long line, boolean fatal)
{
	(void)information; (void)file; (void)line; (void)fatal;
}

void system_exit(long code) { (void)code; assert(!"unexpected CE system_exit"); }
void main_stop_time(void) { ++time_stop_count; }
void main_start_time(void) { ++time_start_count; }
void collision_log_enable(boolean enabled)
{
	if (enabled) ++collision_on_count; else ++collision_off_count;
}
void main_goto_main_menu(void) { ++menu_count; }
void error(short type, const char *format, ...)
{
	(void)type; (void)format; ++error_count;
}

#define BSP_PROC(name, counter) void name(void) { ++counter; }
BSP_PROC(objects_reconnect_to_structure_bsp, reconnect_count)
BSP_PROC(lights_reconnect_to_structure_bsp, reconnect_count)
BSP_PROC(ai_reconnect_to_structure_bsp, reconnect_count)
BSP_PROC(effects_reconnect_to_structure_bsp, reconnect_count)
BSP_PROC(particles_reconnect_to_structure_bsp, reconnect_count)
BSP_PROC(particle_systems_reconnect_to_structure_bsp, reconnect_count)
BSP_PROC(contrails_reconnect_to_structure_bsp, reconnect_count)
BSP_PROC(decals_reconnect_to_structure_bsp, reconnect_count)
BSP_PROC(structure_decals_reconnect_to_structure_bsp, reconnect_count)
BSP_PROC(observer_reconnect_to_structure_bsp, reconnect_count)
BSP_PROC(players_reconnect_to_structure_bsp, reconnect_count)
BSP_PROC(sound_reconnect_to_structure_bsp, reconnect_count)
BSP_PROC(object_types_reconnect_to_structure_bsp, reconnect_count)
BSP_PROC(object_types_disconnect_from_structure_bsp, disconnect_count)
BSP_PROC(objects_disconnect_from_structure_bsp, disconnect_count)
BSP_PROC(lights_disconnect_from_structure_bsp, disconnect_count)
BSP_PROC(ai_disconnect_from_structure_bsp, disconnect_count)
BSP_PROC(effects_disconnect_from_structure_bsp, disconnect_count)
BSP_PROC(particles_disconnect_from_structure_bsp, disconnect_count)
BSP_PROC(particle_systems_disconnect_from_structure_bsp, disconnect_count)
BSP_PROC(contrails_disconnect_from_structure_bsp, disconnect_count)
BSP_PROC(structure_decals_disconnect_from_structure_bsp, disconnect_count)
BSP_PROC(decals_disconnect_from_structure_bsp, disconnect_count)

static void reset_fixture(int initial_index)
{
	int i;
	memset(&scenario_fixture, 0, sizeof(scenario_fixture));
	memset(&globals_fixture, 0, sizeof(globals_fixture));
	memset(references, 0, sizeof(references));
	memset(tag_cache, 0, sizeof(tag_cache));
	memset(bsp_cache, 0, sizeof(bsp_cache));
	memset(tag_instances, 0, sizeof(tag_instances));
	memset(&cache_file_globals, 0, sizeof(cache_file_globals));
	cache_file_globals.tags_loaded = TRUE;
	cache_file_globals.header.file_length = 10240;
	cache_file_globals.header.tag_data_size = 512;
	global_tag_count = 2;
	for (i = 0; i < 2; ++i)
	{
		references[i].file_offset = i == 0 ? 2048 : 6144;
		references[i].file_size = sizeof bsp_cache;
		references[i].structure_bsp.index = i;
		tag_instances[i].tag_index = i;
		tag_instances[i].group_tag = STRUCTURE_BSP_TAG;
	}
	scenario_fixture.structure_bsp_references.count = 2;
	scenario_fixture.structure_bsp_references.address = references;
	global_scenario = &scenario_fixture;
	scenario_globals = &globals_fixture;
	global_structure_bsp_index = (short)initial_index;
	scenario_globals->structure_bsp_index = (short)initial_index;
	global_structure_bsp = NULL;
	global_collision_bsp = NULL;
	global_bsp3d = NULL;
	loaded_datum = -1;
	fail_schema_mask = 0;
	fail_verify_mask = 0;
	unload_count = load_count = verify_count = register_count = schema_count = menu_count = error_count = 0;
	time_stop_count = time_start_count = collision_off_count = collision_on_count = 0;
	disconnect_count = reconnect_count = 0;
	if (initial_index >= 0)
	{
		assert(scenario_structure_bsp_load(&references[initial_index]));
		assert(structure_at()->collision_bsp.address == collision_at());
		global_structure_bsp = tag_instances[initial_index].base_address;
		global_collision_bsp = structure_at()->collision_bsp.address;
		global_bsp3d = (struct bsp3d *)global_collision_bsp;
		loaded_datum = initial_index;
		load_count = register_count = 0;
	}
}

static void assert_published(int index)
{
	assert(global_structure_bsp_index == index);
	assert(scenario_globals->structure_bsp_index == index);
	assert(global_structure_bsp == structure_at());
	assert(global_collision_bsp == collision_at());
	assert(global_bsp3d == (struct bsp3d *)collision_at());
	assert(references[index].base_address == bsp_cache);
	assert(tag_instances[index].base_address == structure_at());
	assert(cache_file_globals.structure_bsp_header ==
		(struct cache_file_structure_bsp_header *)bsp_cache);
}

static void assert_safe_null(void)
{
	int i;
	assert(global_structure_bsp_index == NONE);
	assert(scenario_globals->structure_bsp_index == NONE);
	assert(global_structure_bsp == NULL && global_collision_bsp == NULL &&
		global_bsp3d == NULL);
	assert(cache_file_globals.structure_bsp_header == NULL);
	for (i = 0; i < 2; ++i)
		assert(tag_instances[i].base_address == NULL);
}

#ifdef HCU_BSP_RETAIL_INTEGRATION
static void assert_parent_scratch_released(void)
{
	assert(!retail_mount.bsp_active);
	assert(retail_bsp_scratch.used == 0);
}

/* Exercise a source-derived paired query on the a30 B000 surface-27/94
 * shared edge. The raw-map oracle proves the +/-0.01 contacts lie uniquely
 * inside the respective polygons; exact-edge tie behavior is intentionally
 * not an acceptance condition. */
static void assert_a30_shared_edge_grazing(void)
{
	struct structure_bsp *structure = global_structure_bsp;
	const hcu_raw_collision_shared_edge_golden *golden = NULL;
	struct collision_surface *surfaces;
	struct collision_result result;
	struct collision_result tie_result;
	unsigned char *snapshot;
	byte breakable_before[sizeof(retail_breakable_surface_flags)];
	long sample;
	unsigned index;
	size_t image_bytes;

	assert(retail_collision_map_id == 30 && global_structure_bsp_index == 0);
	for (index = 0; index < HCU_RAW_COLLISION_SHARED_EDGE_GOLDEN_COUNT; ++index)
	{
		if (hcu_raw_collision_shared_edge_goldens[index].map_id == 30 &&
			hcu_raw_collision_shared_edge_goldens[index].bsp_index == 0)
			golden = &hcu_raw_collision_shared_edge_goldens[index];
	}
	assert(golden != NULL);
	assert(structure != NULL && global_collision_bsp != NULL);
	surfaces = (struct collision_surface *)global_collision_bsp->surfaces.address;
	assert(global_collision_bsp->surfaces.count > golden->surface_index[1]);
	for (sample = 0; sample < 2; ++sample)
	{
		assert(surfaces[golden->surface_index[sample]].flags ==
			(byte)golden->flags[sample]);
		assert(surfaces[golden->surface_index[sample]].material_index ==
			golden->material_index[sample]);
		assert(surfaces[golden->surface_index[sample]].plane_designator ==
			golden->plane_designator[sample]);
	}
	assert(global_scenario->structure_bsp_references.count > 0);
	image_bytes = (size_t)((struct scenario_structure_bsp_reference *)
		global_scenario->structure_bsp_references.address)[0].file_size;
	snapshot = (unsigned char *)malloc(image_bytes);
	assert(snapshot != NULL);
	memcpy(snapshot, structure, image_bytes);
	memcpy(breakable_before, retail_breakable_surface_flags,
		sizeof(breakable_before));
	for (sample = 0; sample < 2; ++sample)
	{
		real_point3d start = {
			golden->start[sample][0], golden->start[sample][1],
			golden->start[sample][2] };
		real_vector3d vector = {
			golden->vector[sample][0], golden->vector[sample][1],
			golden->vector[sample][2] };
		memset(&result, 0xCD, sizeof(result));
		assert(collision_test_vector(
			FLAG(_collision_test_structure_bit) |
			FLAG(_collision_test_front_facing_surfaces_bit),
			&start, &vector, NONE, &result));
		assert(result.type == _collision_result_structure);
		assert(result.surface_index == golden->surface_index[sample]);
		assert(result.material_index == golden->material_index[sample]);
		assert(result.material_type ==
			((struct structure_collision_material *)
			structure->collision_materials.address)[3].runtime_physics_material_type);
		assert(result.plane_designator == golden->plane_designator[sample]);
		assert(result.flags == (byte)golden->flags[sample]);
		assert(result.breakable_surface_index ==
			(byte)golden->breakable_index[sample]);
		assert(result.start_location.leaf_index == golden->start_leaf[sample]);
		assert(result.location.leaf_index == golden->precontact_leaf[sample]);
		assert(golden->end_leaf[sample] == NONE);
		assert(fabsf(result.t - golden->t[sample]) <= 2.0e-4f);
		assert(fabsf(result.point.x - golden->point[sample][0]) <= 1.0e-3f);
		assert(fabsf(result.point.y - golden->point[sample][1]) <= 1.0e-3f);
		assert(fabsf(result.point.z - golden->point[sample][2]) <= 1.0e-3f);
		assert(forbidden_object_adapter_calls == 0);
	}
	{
		real_point3d tie_point = {
			(golden->point[0][0] + golden->point[1][0]) * 0.5f,
			(golden->point[0][1] + golden->point[1][1]) * 0.5f,
			(golden->point[0][2] + golden->point[1][2]) * 0.5f };
		real_point3d start = {
			tie_point.x - golden->vector[0][0] * 0.5f,
			tie_point.y - golden->vector[0][1] * 0.5f,
			tie_point.z - golden->vector[0][2] * 0.5f };
		real_vector3d vector = { golden->vector[0][0],
			golden->vector[0][1], golden->vector[0][2] };
		memset(&tie_result, 0xCD, sizeof(tie_result));
		assert(collision_test_vector(
			FLAG(_collision_test_structure_bit) |
			FLAG(_collision_test_front_facing_surfaces_bit),
			&start, &vector, NONE, &tie_result));
		assert(tie_result.type == _collision_result_structure);
		assert(tie_result.surface_index == golden->surface_index[0] ||
			tie_result.surface_index == golden->surface_index[1]);
		assert(tie_result.material_index == golden->material_index[0]);
		assert(tie_result.flags == 0);
		assert(tie_result.start_location.leaf_index == golden->start_leaf[0]);
		assert(tie_result.location.leaf_index == golden->precontact_leaf[0] ||
			tie_result.location.leaf_index == golden->precontact_leaf[1]);
		assert(fabsf(tie_result.t - 0.5f) <= 2.0e-4f);
		assert(fabsf(tie_result.point.x - tie_point.x) <= 1.0e-3f);
		assert(fabsf(tie_result.point.y - tie_point.y) <= 1.0e-3f);
		assert(fabsf(tie_result.point.z - tie_point.z) <= 1.0e-3f);
	}
	assert(global_structure_bsp == structure &&
		global_collision_bsp == structure->collision_bsp.address &&
		global_structure_bsp_index == 0);
	assert(memcmp(snapshot, structure, image_bytes) == 0);
	assert(memcmp(breakable_before, retail_breakable_surface_flags,
		sizeof(breakable_before)) == 0);
	free(snapshot);
	printf("collision-edge-pair map=30 bsp=0 surfaces=27,94 epsilon=0.01 "
		"tie-surface=%ld status=passed\n", tie_result.surface_index);
}

static void assert_a30_flagged_surface_queries(void)
{
	const hcu_raw_collision_flagged_golden *invisible = NULL;
	const hcu_raw_collision_flagged_golden *breakable = NULL;
	struct collision_surface *surfaces;
	byte flags_before[sizeof(retail_breakable_surface_flags)];
	struct collision_result result;
	int index;

	assert(retail_collision_map_id == 30 && global_structure_bsp_index == 0);
	for (index = 0; index < HCU_RAW_COLLISION_FLAGGED_GOLDEN_COUNT; ++index)
	{
		const hcu_raw_collision_flagged_golden *row =
			&hcu_raw_collision_flagged_goldens[index];
		if (row->map_id != 30 || row->bsp_index != 0)
			continue;
		if (row->kind == 1)
			invisible = row;
		else if (row->kind == 2)
			breakable = row;
	}
	assert(invisible != NULL && breakable != NULL);
	assert(global_collision_bsp != NULL);
	surfaces = (struct collision_surface *)global_collision_bsp->surfaces.address;
	assert(surfaces[invisible->surface_index].flags == (byte)invisible->flags);
	assert(surfaces[breakable->surface_index].flags == (byte)breakable->flags);
	memcpy(flags_before, retail_breakable_surface_flags, sizeof(flags_before));

	{
		real_point3d start = { invisible->start[0], invisible->start[1],
			invisible->start[2] };
		real_vector3d vector = { invisible->vector[0], invisible->vector[1],
			invisible->vector[2] };
		memset(&result, 0xCD, sizeof(result));
		assert(collision_test_vector(
			FLAG(_collision_test_structure_bit) |
			FLAG(_collision_test_front_facing_surfaces_bit),
			&start, &vector, NONE, &result));
		assert(result.surface_index == invisible->surface_index);
		assert(result.flags == (byte)invisible->flags);
		memset(&result, 0xCD, sizeof(result));
		assert(!collision_test_vector(
			FLAG(_collision_test_structure_bit) |
			FLAG(_collision_test_front_facing_surfaces_bit) |
			FLAG(_collision_test_ignore_invisible_surfaces_bit),
			&start, &vector, NONE, &result));
	}

	{
		real_point3d start = { breakable->start[0], breakable->start[1],
			breakable->start[2] };
		real_vector3d vector = { breakable->vector[0], breakable->vector[1],
			breakable->vector[2] };
		byte bit = (byte)(1U << (breakable->breakable_index & 7));
		assert(breakable->breakable_index < 256);
		memset(&result, 0xCD, sizeof(result));
		assert(collision_test_vector(
			FLAG(_collision_test_structure_bit) |
			FLAG(_collision_test_front_facing_surfaces_bit),
			&start, &vector, NONE, &result));
		assert(result.surface_index == breakable->surface_index);
		assert(result.flags == (byte)breakable->flags);
		retail_breakable_surface_flags[breakable->breakable_index >> 3] &=
			(byte)~bit;
		memset(&result, 0xCD, sizeof(result));
		assert(!collision_test_vector(
			FLAG(_collision_test_structure_bit) |
			FLAG(_collision_test_front_facing_surfaces_bit),
			&start, &vector, NONE, &result));
	}
	memcpy(retail_breakable_surface_flags, flags_before, sizeof(flags_before));
	printf("collision-flagged map=30 bsp=0 invisible=%ld breakable=%ld status=passed\n",
		invisible->surface_index, breakable->surface_index);
}

/* Run CE's real static player-PVS aggregator through its test-only wrapper.
 * Player records and selected clusters are synthetic, but the PVS rows are
 * from the currently published, source-hash-bound retail BSP. */
static void assert_relocated_player_pvs_aggregation(void)
{
	struct structure_bsp *structure = global_structure_bsp;
	struct data_array player_array;
	struct data_array object_array;
	struct player_datum player_slots[4];
	struct player_datum player_slots_before[4];
	struct player_datum player_slots_after_expected[4];
	struct object_header_datum object_headers[2];
	struct object_header_datum object_headers_before[2];
	struct object_datum object_datums[2];
	struct object_datum object_datums_before[2];
	struct data_array *previous_player_data = player_data;
	struct data_array *previous_object_header_data = object_header_data;
	const hcu_raw_player_pvs_golden *golden = NULL;
	unsigned long all_pvs[16];
	unsigned long local_pvs[16];
	unsigned char *pvs_before;
	size_t pvs_bytes;
	short published_index = global_structure_bsp_index;
	short collision_depth = global_current_collision_user_depth;
	unsigned index;
	long child_object_index, root_object_index;

	assert(structure != NULL && published_index >= 0);
	for (index = 0; index < HCU_RAW_PLAYER_PVS_GOLDEN_COUNT; ++index)
	{
		const hcu_raw_player_pvs_golden *candidate =
			&hcu_raw_player_pvs_goldens[index];
		if (candidate->map_id == retail_collision_map_id &&
			candidate->bsp_index == published_index)
		{
			golden = candidate;
			break;
		}
	}
	assert(golden != NULL);
	assert(golden->cluster_count == structure->clusters.count);
	assert(sizeof(unsigned long) == 4);
	pvs_bytes = (size_t)structure->cluster_data.size;
	assert(pvs_bytes >= (size_t)structure->clusters.count *
		(size_t)BIT_VECTOR_SIZE_IN_BYTES(structure->clusters.count));
	assert((uintptr_t)structure->cluster_data.address >= (uintptr_t)bsp_cache &&
		(uintptr_t)structure->cluster_data.address + pvs_bytes <=
		(uintptr_t)bsp_cache + retail_size[(unsigned)published_index]);
	pvs_before = (unsigned char *)malloc(pvs_bytes);
	assert(pvs_before != NULL);
	memcpy(pvs_before, structure->cluster_data.address, pvs_bytes);

	memset(&player_array, 0, sizeof(player_array));
	memset(player_slots, 0, sizeof(player_slots));
	__builtin_memcpy(player_array.name, "hcu-player-pvs", 15);
	player_array.maximum_count = 4;
	player_array.size = (short)sizeof(player_slots[0]);
	player_array.valid = TRUE;
	player_array.signature = 'd@t@';
	player_array.first_free_absolute_index = 4;
	player_array.count = 4;
	player_array.actual_count = 4;
	player_array.data = player_slots;
	for (index = 0; index < 4; ++index)
	{
		player_slots[index].identifier = (short)(index + 1);
		player_slots[index].local_player_index = index == 1 ? NONE : (short)index;
		player_slots[index].unit_index = NONE;
		player_slots[index].cluster_index =
			golden->player_clusters[index];
	}
	memcpy(player_slots_before, player_slots, sizeof(player_slots));
	player_data = &player_array;
	hcu_test_players_compute_combined_pvs(all_pvs, FALSE);
	hcu_test_players_compute_combined_pvs(local_pvs, TRUE);
	assert(memcmp(all_pvs, golden->expected_all, sizeof(all_pvs)) == 0);
	assert(memcmp(local_pvs, golden->expected_local, sizeof(local_pvs)) == 0);
	assert(memcmp(all_pvs, local_pvs, sizeof(all_pvs)) != 0);
	assert(memcmp(player_slots, player_slots_before, sizeof(player_slots)) == 0);

	/* Now exercise CE's real player.unit -> object datum -> ultimate parent
	 * lookup. The child biped deliberately carries stale cluster A while its
	 * valid vehicle root carries source-oracle cluster B. */
	memset(&object_array, 0, sizeof(object_array));
	memset(object_headers, 0, sizeof(object_headers));
	memset(object_datums, 0, sizeof(object_datums));
	__builtin_memcpy(object_array.name, "hcu-player-objects", 19);
	object_array.maximum_count = 2;
	object_array.size = (short)sizeof(object_headers[0]);
	object_array.valid = TRUE;
	object_array.identifier_zero_invalid = TRUE;
	object_array.signature = 'd@t@';
	object_array.first_free_absolute_index = 2;
	object_array.count = 2;
	object_array.actual_count = 2;
	object_array.next_identifier = 3;
	object_array.data = object_headers;
	child_object_index = (1L << 16) | 0L;
	root_object_index = (2L << 16) | 1L;
	object_headers[0].identifier = 1;
	object_headers[0].type = _object_type_biped;
	object_headers[0].cluster_index = golden->player_clusters[0];
	object_headers[0].data_size = (short)sizeof(object_datums[0]);
	object_headers[0].datum = &object_datums[0];
	object_headers[1].identifier = 2;
	object_headers[1].type = _object_type_vehicle;
	object_headers[1].cluster_index = golden->root_cluster;
	object_headers[1].data_size = (short)sizeof(object_datums[1]);
	object_headers[1].datum = &object_datums[1];
	object_datums[0].definition_index = NONE;
	object_datums[0].object.type = _object_type_biped;
	object_datums[0].object.parent_object_index = root_object_index;
	object_datums[0].object.location.leaf_index = NONE;
	object_datums[0].object.location.cluster_index = golden->player_clusters[0];
	object_datums[1].definition_index = NONE;
	object_datums[1].object.type = _object_type_vehicle;
	object_datums[1].object.parent_object_index = NONE;
	object_datums[1].object.location.leaf_index = NONE;
	object_datums[1].object.location.cluster_index = golden->root_cluster;
	assert(golden->player_clusters[0] != golden->root_cluster);
	assert(golden->player_clusters[0] != golden->player_clusters[2]);
	assert(object_datums[0].object.location.cluster_index !=
		object_datums[1].object.location.cluster_index);
	memcpy(object_headers_before, object_headers, sizeof(object_headers));
	memcpy(object_datums_before, object_datums, sizeof(object_datums));
	object_header_data = &object_array;
	player_slots[0].unit_index = child_object_index;
	memcpy(player_slots_before, player_slots, sizeof(player_slots));
	memcpy(player_slots_after_expected, player_slots_before,
		sizeof(player_slots_after_expected));
	player_slots_after_expected[0].cluster_index = golden->root_cluster;
	assert(object_headers[0].datum == &object_datums[0]);
	assert(object_headers[1].datum == &object_datums[1]);
	assert(object_datums[0].object.parent_object_index == root_object_index);
	assert(object_datums[1].object.parent_object_index == NONE);
	hcu_test_real_object_lookup_count = 0;
	hcu_player_pvs_object_lookup_enabled = TRUE;
	hcu_test_players_compute_combined_pvs(all_pvs, FALSE);
	hcu_test_players_compute_combined_pvs(local_pvs, TRUE);
	assert(memcmp(all_pvs, golden->expected_root_all, sizeof(all_pvs)) == 0);
	assert(memcmp(local_pvs, golden->expected_root_local, sizeof(local_pvs)) == 0);
	assert(memcmp(local_pvs, golden->expected_local, sizeof(local_pvs)) != 0);
	assert(player_slots[0].cluster_index == golden->root_cluster);
	assert(memcmp(player_slots, player_slots_after_expected,
		sizeof(player_slots)) == 0);
	assert(memcmp(object_headers, object_headers_before,
		sizeof(object_headers)) == 0);
	assert(memcmp(object_datums, object_datums_before,
		sizeof(object_datums)) == 0);
	/* The already-refreshed record makes the second call idempotent. */
	hcu_test_players_compute_combined_pvs(all_pvs, FALSE);
	hcu_test_players_compute_combined_pvs(local_pvs, TRUE);
	assert(memcmp(all_pvs, golden->expected_root_all, sizeof(all_pvs)) == 0);
	assert(memcmp(local_pvs, golden->expected_root_local, sizeof(local_pvs)) == 0);
	assert(memcmp(player_slots, player_slots_after_expected,
		sizeof(player_slots)) == 0);
	/* When the ultimate parent temporarily has no cluster, CE preserves the
	 * player's last known cluster instead of erasing its visibility origin. */
	memcpy(player_slots, player_slots_before, sizeof(player_slots));
	object_datums[1].object.location.cluster_index = NONE;
	memcpy(object_datums_before, object_datums, sizeof(object_datums));
	hcu_test_players_compute_combined_pvs(all_pvs, FALSE);
	hcu_test_players_compute_combined_pvs(local_pvs, TRUE);
	assert(memcmp(all_pvs, golden->expected_all, sizeof(all_pvs)) == 0);
	assert(memcmp(local_pvs, golden->expected_local, sizeof(local_pvs)) == 0);
	assert(memcmp(player_slots, player_slots_before, sizeof(player_slots)) == 0);
	/* And the fallback is stable over a repeated call. */
	hcu_test_players_compute_combined_pvs(all_pvs, FALSE);
	hcu_test_players_compute_combined_pvs(local_pvs, TRUE);
	hcu_player_pvs_object_lookup_enabled = FALSE;
	assert(hcu_test_real_object_lookup_count == 8);
	assert(memcmp(all_pvs, golden->expected_all, sizeof(all_pvs)) == 0);
	assert(memcmp(local_pvs, golden->expected_local, sizeof(local_pvs)) == 0);
	assert(memcmp(player_slots, player_slots_before, sizeof(player_slots)) == 0);
	assert(memcmp(object_headers, object_headers_before,
		sizeof(object_headers)) == 0);
	assert(memcmp(object_datums, object_datums_before,
		sizeof(object_datums)) == 0);
	assert(global_structure_bsp == structure &&
		global_structure_bsp_index == published_index &&
		scenario_globals->structure_bsp_index == published_index);
	assert(global_current_collision_user_depth == collision_depth);
	assert(memcmp(pvs_before, structure->cluster_data.address, pvs_bytes) == 0);
	player_data = previous_player_data;
	object_header_data = previous_object_header_data;
	free(pvs_before);
	printf("player-pvs map=%d bsp=%d clusters=%d words=16 root-refresh=%d root-none-fallback=1 idempotent=1 status=passed\n",
		retail_collision_map_id, published_index,
		(unsigned)structure->clusters.count, golden->root_cluster);
}

/* Execute CE's real PVS and sound-distance accessors against the relocated
 * cluster payloads in the currently published retail BSP. These checks prove
 * pointer/value access through materialized data, not full player visibility
 * aggregation or game_sound occlusion. */
static void assert_relocated_sound_pas(struct structure_bsp *structure,
	int map_id)
{
	struct players_globals fixture_players_globals;
	struct players_globals *previous_players_globals = players_globals;
	const hcu_raw_sound_pas_golden *golden = NULL;
	unsigned long actual_words[16];
	byte *sound_bytes_before;
	size_t sound_data_bytes;
	unsigned active_word_count;
	unsigned index;
	unsigned cluster_index;
	real_point3d camera_position = { 0.0f, 0.0f, 0.0f };

	for (index = 0; index < HCU_RAW_SOUND_PAS_GOLDEN_COUNT; ++index)
	{
		const hcu_raw_sound_pas_golden *candidate =
			&hcu_raw_sound_pas_goldens[index];
		if (candidate->map_id == map_id &&
			candidate->bsp_index == global_structure_bsp_index)
		{
			golden = candidate;
			break;
		}
	}
	assert(golden != NULL);
	assert((unsigned)golden->cluster_count == (unsigned)structure->clusters.count);
	assert(golden->listener_clusters[0] >= 0);
	assert(golden->listener_clusters[1] >= 0);
	assert(golden->listener_clusters[2] == NONE);
	active_word_count = ((unsigned)structure->clusters.count + 31) / 32;
	assert(active_word_count <= 16);
	sound_data_bytes = (size_t)structure->sound_cluster_data.size;
	assert(sound_data_bytes >= (size_t)structure->clusters.count *
		((size_t)structure->clusters.count - 1) / 2);
	sound_bytes_before = (byte *)malloc(sound_data_bytes);
	assert(sound_bytes_before != NULL);
	memcpy(sound_bytes_before, structure->sound_cluster_data.address,
		sound_data_bytes);

	memset(&fixture_players_globals, 0, sizeof(fixture_players_globals));
	for (index = 0; index < MAXIMUM_LOCAL_PLAYERS; ++index)
		fixture_players_globals.local_players[index] = NONE;
	fixture_players_globals.local_players[0] = 0;
	fixture_players_globals.local_players[1] = 1;
	fixture_players_globals.local_players[2] = 2;
	players_globals = &fixture_players_globals;
	hcu_test_set_sound_camera_cluster(0, golden->listener_clusters[0],
		&camera_position);
	hcu_test_set_sound_camera_cluster(1, golden->listener_clusters[1],
		&camera_position);
	hcu_test_set_sound_camera_cluster(2, golden->listener_clusters[2],
		&camera_position);
	/* A disconnected slot has an otherwise audible camera but must not add a
	 * listener to CE's combined set. */
	hcu_test_set_sound_camera_cluster(3, golden->listener_clusters[0],
		&camera_position);
	hcu_test_compute_combined_pas(actual_words, 16);
	for (index = 0; index < active_word_count; ++index)
		assert(actual_words[index] == golden->expected_words[index]);
	for (cluster_index = 0; cluster_index < (unsigned)structure->clusters.count;
		++cluster_index)
	{
		boolean expected = (golden->expected_words[cluster_index / 32] &
			(1UL << (cluster_index % 32))) != 0;
		assert(hcu_test_location_potentially_audible((short)cluster_index) == expected);
	}
	assert(!hcu_test_location_potentially_audible(NONE));

	/* Active local players with no cluster are valid but contribute no PAS. */
	for (index = 0; index < 3; ++index)
		hcu_test_set_sound_camera_cluster((short)index, NONE,
			&camera_position);
	hcu_test_compute_combined_pas(actual_words, 16);
	for (index = 0; index < active_word_count; ++index)
		assert(actual_words[index] == 0);
	for (cluster_index = 0; cluster_index < (unsigned)structure->clusters.count;
		++cluster_index)
		assert(!hcu_test_location_potentially_audible((short)cluster_index));
	assert(memcmp(sound_bytes_before, structure->sound_cluster_data.address,
		sound_data_bytes) == 0);
	free(sound_bytes_before);
	players_globals = previous_players_globals;
	printf("sound-pas map=%d bsp=%d clusters=%d listeners=%d,%d,%d "
		"union=%d words=16 none=0 status=passed\n", map_id,
		global_structure_bsp_index, structure->clusters.count,
		golden->listener_clusters[0], golden->listener_clusters[1],
		golden->listener_clusters[2],
		golden->union_proved);
}

/* Exercise CE's high-bit cluster fog-plane reference through its actual
 * plane -> region -> fog-palette tag and weather fallback path. Goldens are
 * independently decoded from the original retail Xbox BSP. */
static void assert_relocated_fog_plane(struct structure_bsp *structure,
	int map_id)
{
	const hcu_raw_fog_plane_golden *golden = NULL;
	struct structure_cluster *cluster;
	struct structure_fog_plane *plane;
	struct structure_fog_region *region;
	struct structure_fog_palette_entry *palette;
	struct fog_definition *fog;
	struct location location;
	real_point3d point;
	real_point3d opposite_point;
	real water_depth;
	short weather = 0x1234;
	short published_index = global_structure_bsp_index;
	short collision_depth = global_current_collision_user_depth;
	unsigned index;
	float norm_squared;
	float scale;
	boolean underwater;
	for (index = 0; index < HCU_RAW_FOG_PLANE_GOLDEN_COUNT; ++index)
	{
		const hcu_raw_fog_plane_golden *candidate =
			&hcu_raw_fog_plane_goldens[index];
		if (candidate->map_id == map_id &&
			candidate->bsp_index == global_structure_bsp_index)
		{
			golden = candidate;
			break;
		}
	}
	if (golden == NULL)
		return;
	assert(golden->cluster_index >= 0 &&
		golden->cluster_index < structure->clusters.count);
	assert(golden->plane_index >= 0 &&
		golden->plane_index < structure->fog_planes.count);
	assert(golden->region_index >= 0 &&
		golden->region_index < structure->fog_regions.count);
	assert(golden->fog_palette_index >= 0 &&
		golden->fog_palette_index < structure->fog_palette.count);
	cluster = TAG_BLOCK_GET_ELEMENT(&structure->clusters,
		golden->cluster_index, struct structure_cluster);
	plane = TAG_BLOCK_GET_ELEMENT(&structure->fog_planes,
		golden->plane_index, struct structure_fog_plane);
	region = TAG_BLOCK_GET_ELEMENT(&structure->fog_regions,
		golden->region_index, struct structure_fog_region);
	palette = TAG_BLOCK_GET_ELEMENT(&structure->fog_palette,
		golden->fog_palette_index, struct structure_fog_palette_entry);
	assert(cluster->fog_reference == golden->reference);
	assert((cluster->fog_reference & SHORT_MIN) != 0);
	assert(plane->region_index == golden->region_index);
	assert(region->fog_palette_index == golden->fog_palette_index);
	assert(region->weather_palette_index == golden->region_weather);
	assert(cluster->weather_palette_index == golden->cluster_weather);
	assert(palette->fog.index == golden->fog_datum);
	assert(region->weather_palette_index == golden->weather ||
		(region->weather_palette_index == NONE &&
		cluster->weather_palette_index == golden->weather));
	fog = fog_definition_get(palette->fog.index);
	assert(fog != NULL);
	assert(fabsf(plane->plane.n.i - golden->plane[0]) < 0.00001f);
	assert(fabsf(plane->plane.n.j - golden->plane[1]) < 0.00001f);
	assert(fabsf(plane->plane.n.k - golden->plane[2]) < 0.00001f);
	assert(fabsf(plane->plane.d - golden->plane[3]) < 0.0001f);
	location.leaf_index = NONE;
	location.cluster_index = (short)golden->cluster_index;
	location.bonus = 0;
	assert(scenario_get_fog_region_index(&location, NULL) == golden->region_index);
	norm_squared = plane->plane.n.i * plane->plane.n.i +
		plane->plane.n.j * plane->plane.n.j +
		plane->plane.n.k * plane->plane.n.k;
	assert(norm_squared > 0.0f);
	scale = (fabsf(plane->plane.d) + fabsf(fog->plane_distance) + 1000.0f) /
		norm_squared;
	point.x = -plane->plane.n.i * scale;
	point.y = -plane->plane.n.j * scale;
	point.z = -plane->plane.n.k * scale;
	opposite_point.x = plane->plane.n.i * scale;
	opposite_point.y = plane->plane.n.j * scale;
	opposite_point.z = plane->plane.n.k * scale;
	assert(scenario_get_fog_region_index(&location, &point) == golden->region_index);
	underwater = scenario_location_underwater(&location, &point, &weather);
	assert(underwater == TEST_FLAG(fog->flags, 0));
	assert(weather == golden->weather);
	water_depth = scenario_location_water_depth(&location, &point);
	if (TEST_FLAG(fog->flags, 0))
		assert(fabsf(water_depth +
			(plane3d_distance_to_point(&plane->plane, &point) +
			fog->plane_distance)) < 0.01f);
	else
		assert(water_depth == REAL_MIN);
	assert(scenario_get_fog_region_index(&location, &opposite_point) == NONE);
	assert(scenario_location_water_depth(&location, &opposite_point) ==
		(TEST_FLAG(fog->flags, 0) ?
		-(plane3d_distance_to_point(&plane->plane, &opposite_point) +
			fog->plane_distance) : REAL_MIN));
	assert(global_structure_bsp == structure &&
		global_structure_bsp_index == published_index);
	assert(global_current_collision_user_depth == collision_depth);
	printf("fog-plane map=%d bsp=%d cluster=%d reference=%d plane=%d region=%d "
		"fog=%ld weather=%d underwater=%d status=passed\n", map_id,
		global_structure_bsp_index, golden->cluster_index,
		cluster->fog_reference, golden->plane_index, golden->region_index,
		palette->fog.index, weather, underwater);
}

/* Source-backed failure case: a raw cluster whose fog reference is NONE must
 * stay outside all fog regions in CE, for both position-independent and
 * position-dependent lookup. */
static void assert_relocated_fog_none_reference(struct structure_bsp *structure,
	int map_id)
{
	const hcu_raw_fog_none_golden *golden = NULL;
	struct structure_cluster *cluster;
	struct location location;
	real_point3d point = { 0.f, 0.f, 0.f };
	unsigned index;
	short published_index = global_structure_bsp_index;
	for (index = 0; index < HCU_RAW_FOG_NONE_GOLDEN_COUNT; ++index)
	{
		const hcu_raw_fog_none_golden *candidate =
			&hcu_raw_fog_none_goldens[index];
		if (candidate->map_id == map_id &&
			candidate->bsp_index == global_structure_bsp_index)
		{
			golden = candidate;
			break;
		}
	}
	if (golden == NULL)
		return;
	assert(golden->cluster_index >= 0 &&
		golden->cluster_index < structure->clusters.count);
	cluster = TAG_BLOCK_GET_ELEMENT(&structure->clusters,
		golden->cluster_index, struct structure_cluster);
	assert(cluster->fog_reference == golden->reference &&
		golden->reference == NONE);
	location.leaf_index = NONE;
	location.cluster_index = (short)golden->cluster_index;
	location.bonus = 0;
	assert(scenario_get_fog_region_index(&location, NULL) == NONE);
	assert(scenario_get_fog_region_index(&location, &point) == NONE);
	assert(global_structure_bsp == structure &&
		global_structure_bsp_index == published_index);
	printf("fog-none map=%d bsp=%d cluster=%d reference=%d status=passed\n",
		map_id, global_structure_bsp_index, golden->cluster_index,
		cluster->fog_reference);
}

static void assert_relocated_cluster_queries(void)
{
	struct structure_bsp *structure = global_structure_bsp;
	unsigned cluster_count;
	size_t pvs_stride, pvs_bytes, sound_pairs, sound_bytes;
	unsigned char *pvs_before, *sound_before;
	unsigned i, j;
	unsigned visible_nonself_pairs = 0;
	unsigned hidden_nonself_pairs = 0;
	unsigned visible_from = 0xFFFFFFFFu, visible_to = 0xFFFFFFFFu;
	unsigned hidden_from = 0xFFFFFFFFu, hidden_to = 0xFFFFFFFFu;

	assert(structure != NULL);
	cluster_count = (unsigned)structure->clusters.count;
	assert(cluster_count > 1 && cluster_count <= MAXIMUM_CLUSTERS_PER_STRUCTURE);
	pvs_stride = ((size_t)cluster_count + 31u) / 32u * sizeof(unsigned long);
	pvs_bytes = pvs_stride * cluster_count;
	sound_pairs = (size_t)cluster_count * (cluster_count - 1u) / 2u;
	sound_bytes = (size_t)structure->sound_cluster_data.size;
	assert(structure->cluster_data.size >= (long)pvs_bytes);
	assert(sound_bytes >= sound_pairs);
	assert(pvs_bytes <= retail_size[(unsigned)global_structure_bsp_index]);
	assert(sound_bytes <= retail_size[(unsigned)global_structure_bsp_index]);
	assert((uintptr_t)structure->cluster_data.address >= (uintptr_t)bsp_cache &&
		(uintptr_t)structure->cluster_data.address - (uintptr_t)bsp_cache <=
		(size_t)retail_size[(unsigned)global_structure_bsp_index] - pvs_bytes);
	assert((uintptr_t)structure->sound_cluster_data.address >= (uintptr_t)bsp_cache &&
		(uintptr_t)structure->sound_cluster_data.address - (uintptr_t)bsp_cache <=
		(size_t)retail_size[(unsigned)global_structure_bsp_index] - sound_bytes);
	pvs_before = (unsigned char *)malloc(pvs_bytes);
	sound_before = sound_bytes ? (unsigned char *)malloc(sound_bytes) : NULL;
	assert(pvs_before && (!sound_bytes || sound_before));
	memcpy(pvs_before, structure->cluster_data.address, pvs_bytes);
	if (sound_bytes) memcpy(sound_before, structure->sound_cluster_data.address, sound_bytes);
	for (i = 0; i < cluster_count; ++i)
	{
		unsigned long *pvs = structure_bsp_get_cluster_pvs(structure, (short)i);
		assert((uintptr_t)pvs == (uintptr_t)structure->cluster_data.address + i * pvs_stride);
		/* CE PVS rows include their own cluster. This validates bit meaning,
		 * not just the relocated row address. */
		assert((pvs[i / 32u] & (1UL << (i & 31u))) != 0);
		for (j = 0; j < cluster_count; ++j)
		{
			if (j == i)
				continue;
			/* Exercise CE's bit-vector convention on distinct clusters. A
			 * row-address check alone cannot catch inverted/empty PVS data. */
			if (BIT_VECTOR_TEST_FLAG(pvs, j))
			{
				++visible_nonself_pairs;
				if (visible_from == 0xFFFFFFFFu)
				{
					visible_from = i;
					visible_to = j;
				}
			}
			else
			{
				++hidden_nonself_pairs;
				if (hidden_from == 0xFFFFFFFFu)
				{
					hidden_from = i;
					hidden_to = j;
				}
			}
		}
		assert(structure_bsp_get_cluster_encoded_sound_distance(
			structure, (short)i, (short)i) == 0);
		for (j = i + 1; j < cluster_count; ++j)
		{
			byte *pair = structure_bsp_get_cluster_encoded_sound_data(
				structure, (short)i, (short)j);
			byte forward = structure_bsp_get_cluster_encoded_sound_distance(
				structure, (short)i, (short)j);
			byte reverse = structure_bsp_get_cluster_encoded_sound_distance(
				structure, (short)j, (short)i);
			assert(pair != NULL && (uintptr_t)pair >=
				(uintptr_t)structure->sound_cluster_data.address &&
				(uintptr_t)pair < (uintptr_t)structure->sound_cluster_data.address + sound_bytes);
			assert(forward == reverse && forward == *pair);
		}
	}
	assert(visible_nonself_pairs > 0);
	assert(hidden_nonself_pairs > 0);
	printf("pvs-pair bsp=%d clusters=%u visible=%u,%u hidden=%u,%u\n",
		global_structure_bsp_index, cluster_count,
		visible_from, visible_to, hidden_from, hidden_to);
	assert(memcmp(pvs_before, structure->cluster_data.address, pvs_bytes) == 0);
	if (sound_bytes)
		assert(memcmp(sound_before, structure->sound_cluster_data.address, sound_bytes) == 0);
	free(pvs_before);
	free(sound_before);
	{
		unsigned unreachable_from = 0xFFFFFFFFu;
		unsigned unreachable_to = 0xFFFFFFFFu;
		byte unreachable_raw = 0;
		unsigned hidden_from = 0xFFFFFFFFu;
		unsigned hidden_to = 0xFFFFFFFFu;
		byte hidden_raw = 0;

		/* These are the first row-major sound-distance examples also selected
		 * independently from the original Xbox BSP by the Python oracle. */
		for (i = 0; i < cluster_count; ++i)
		{
			unsigned long *pvs = structure_bsp_get_cluster_pvs(
				structure, (short)i);
			for (j = i + 1; j < cluster_count; ++j)
			{
				byte encoded = structure_bsp_get_cluster_encoded_sound_distance(
					structure, (short)i, (short)j);
				int pvs_visible = BIT_VECTOR_TEST_FLAG(pvs, j);
				if (unreachable_from == 0xFFFFFFFFu && encoded == 0xFF)
				{
					unreachable_from = i;
					unreachable_to = j;
					unreachable_raw = encoded;
				}
				if (hidden_from == 0xFFFFFFFFu && !pvs_visible &&
					(encoded & 0x7F) < 127)
				{
					hidden_from = i;
					hidden_to = j;
					hidden_raw = encoded;
				}
			}
		}

		/* Missing camera cluster must preserve CE's initialized defaults. */
		{
			real obstruction = -1.0f, occlusion = -1.0f;
			short depth_before = global_current_collision_user_depth;
			long base_user = global_current_collision_users[0];
			unsigned collision_calls = 0;
			hcu_test_compute_sound_obstruction(NONE, 0,
				sound_obstruction_fixture_tick++, 10.0f,
				&obstruction, &occlusion, &collision_calls);
			assert(fabsf(obstruction - 0.6f) < 0.00001f);
			assert(fabsf(occlusion - 1.0f) < 0.00001f);
			assert(global_current_collision_user_depth == depth_before);
			assert(global_current_collision_users[0] == base_user);
			assert(collision_calls == 0);
			printf("sound-obstruction bsp=%d case=missing from=-1 to=0 raw=-1 pvs=-1 distance=10 obstruction=%.9g occlusion=%.9g\n",
				global_structure_bsp_index, obstruction, occlusion);
			++sound_obstruction_query_count;
		}

		/* The CE formula masks bit 7, scales 0x7F to 256, then uses a strict
		 * less-than test. Retail 0xFF is therefore exactly max-distance. */
		if (unreachable_from != 0xFFFFFFFFu)
		{
			real obstruction = -1.0f, occlusion = -1.0f;
			short depth_before = global_current_collision_user_depth;
			long base_user = global_current_collision_users[0];
			unsigned collision_calls = 0;
			hcu_test_compute_sound_obstruction((short)unreachable_from,
				(short)unreachable_to, sound_obstruction_fixture_tick++,
				10.0f, &obstruction, &occlusion, &collision_calls);
			assert(unreachable_raw == 0xFF);
			assert(fabsf(obstruction - 0.6f) < 0.00001f);
			assert(fabsf(occlusion - 1.0f) < 0.00001f);
			assert(global_current_collision_user_depth == depth_before);
			assert(global_current_collision_users[0] == base_user);
			assert(collision_calls == 0);
			printf("sound-obstruction bsp=%d case=unreachable from=%u to=%u raw=%u pvs=%d distance=10 obstruction=%.9g occlusion=%.9g\n",
				global_structure_bsp_index, unreachable_from, unreachable_to,
				(unsigned)unreachable_raw,
				BIT_VECTOR_TEST_FLAG(structure_bsp_get_cluster_pvs(
					structure, (short)unreachable_from), unreachable_to),
				obstruction, occlusion);
			++sound_obstruction_query_count;
		}

		/* A reachable but hidden pair performs the CE encoded-distance
		 * attenuation calculation, but does not call collision traversal. */
		if (hidden_from != 0xFFFFFFFFu)
		{
			real obstruction = -1.0f, occlusion = -1.0f;
			real cluster_distance = (hidden_raw & 0x7F) * (256.0f / 127.0f);
			real expected = (1.0f - 10.0f / (cluster_distance + 10.0f)) * 1.4f;
			short depth_before = global_current_collision_user_depth;
			long base_user = global_current_collision_users[0];
			unsigned collision_calls = 0;
			if (expected < 0.0f) expected = 0.0f;
			if (expected > 1.0f) expected = 1.0f;
			hcu_test_compute_sound_obstruction((short)hidden_from,
				(short)hidden_to, sound_obstruction_fixture_tick++,
				10.0f, &obstruction, &occlusion, &collision_calls);
			assert(fabsf(obstruction - 0.6f) < 0.00001f);
			assert(fabsf(occlusion - expected) < 0.0001f);
			assert(global_current_collision_user_depth == depth_before);
			assert(global_current_collision_users[0] == base_user);
			assert(collision_calls == 0);
			printf("sound-obstruction bsp=%d case=hidden from=%u to=%u raw=%u pvs=0 distance=10 obstruction=%.9g occlusion=%.9g\n",
				global_structure_bsp_index, hidden_from, hidden_to,
				(unsigned)hidden_raw, obstruction, occlusion);
			++sound_obstruction_query_count;
		}
		assert(forbidden_object_adapter_calls == 0);
	}
	/* Query CE's location/environment API using a real, source-selected
	 * unfogged cluster. The raw-map oracle independently checks its weather
	 * palette result; no fog tags or synthetic cluster are needed. */
	{
		unsigned cluster_index;
		for (cluster_index = 0; cluster_index < cluster_count; ++cluster_index)
		{
			struct structure_cluster *cluster = TAG_BLOCK_GET_ELEMENT(
				&structure->clusters, cluster_index, struct structure_cluster);
			if (cluster->fog_reference == NONE)
			{
				struct location location;
				real_point3d position = { 0.0f, 0.0f, 0.0f };
				short weather_palette_index = 0x1234;
				boolean underwater;
				short depth_before = global_current_collision_user_depth;
				struct structure_bsp *published_bsp = global_structure_bsp;
				short published_bsp_index = global_structure_bsp_index;
				location.leaf_index = NONE;
				location.cluster_index = (short)cluster_index;
				location.bonus = 0;
				underwater = scenario_location_underwater(&location, &position,
					&weather_palette_index);
				assert(!underwater);
				assert(global_structure_bsp == published_bsp);
				assert(global_structure_bsp_index == published_bsp_index);
				assert(global_current_collision_user_depth == depth_before);
				printf("underwater-weather bsp=%d cluster=%u fog=-1 weather=%d result=%d\n",
					global_structure_bsp_index, cluster_index,
					weather_palette_index, underwater);
				break;
			}
		}
	}
	/* Root CE's real listener-environment selector against a package-backed
	 * cluster with a valid sound-environment palette reference. The camera
	 * comes through the same observer bridge used by CE sound consumers. */
	{
		unsigned cluster_index;
		struct players_globals fixture_players_globals;
		struct players_globals *previous_players_globals = players_globals;
		unsigned local_index;
		memset(&fixture_players_globals, 0, sizeof(fixture_players_globals));
		for (local_index = 0; local_index < MAXIMUM_NUMBER_OF_LOCAL_PLAYERS;
			++local_index)
			fixture_players_globals.local_players[local_index] = NONE;
		fixture_players_globals.local_players[0] = 0;
		players_globals = &fixture_players_globals;
		for (cluster_index = 0; cluster_index < cluster_count; ++cluster_index)
		{
			struct structure_cluster *cluster = TAG_BLOCK_GET_ELEMENT(
				&structure->clusters, cluster_index, struct structure_cluster);
			short palette_index = cluster->sound_environment_palette_index;
			struct structure_sound_environment_palette_entry *environment_entry;
			struct structure_background_sound_palette_entry *background_entry;
			struct sound_environment_definition const *environment = NULL;
			long background_sound_index = NONE;
			long expected_background_sound_index = NONE;
			struct sound_environment_definition *tagged_environment;
			boolean crossed_water_boundary = TRUE;
			if (cluster->fog_reference != NONE ||
				!VALID_INDEX(palette_index, structure->sound_environment_palette.count))
				continue;
			environment_entry = TAG_BLOCK_GET_ELEMENT(
				&structure->sound_environment_palette, palette_index,
				struct structure_sound_environment_palette_entry);
			if (environment_entry->sound_environment.index == NONE)
				continue;
			tagged_environment = (struct sound_environment_definition *)tag_get(
				SOUND_ENVIRONMENT_TAG,
				environment_entry->sound_environment.index);
			assert(tagged_environment != NULL);
			if (VALID_INDEX(cluster->background_sound_palette_index,
				structure->background_sound_palette.count))
			{
				background_entry = TAG_BLOCK_GET_ELEMENT(
					&structure->background_sound_palette,
					cluster->background_sound_palette_index,
					struct structure_background_sound_palette_entry);
				expected_background_sound_index =
					background_entry->background_sound.index;
			}
			globals_fixture.sound_environment_initialized = FALSE;
			globals_fixture.sound_environment = default_sound_environment;
			hcu_test_set_sound_camera_cluster(0, (short)cluster_index,
				&(real_point3d){ 0.0f, 0.0f, 0.0f });
			scenario_get_sound_environment(&background_sound_index,
				&environment, &crossed_water_boundary);
			assert(environment == &globals_fixture.sound_environment);
			assert(!crossed_water_boundary);
			assert(background_sound_index == expected_background_sound_index);
			{
				real expected_room = default_sound_environment.room_intensity;
				real delta = tagged_environment->room_intensity - expected_room;
				if (delta < -0.03f) delta = -0.03f;
				if (delta > 0.03f) delta = 0.03f;
				assert(fabsf(environment->room_intensity -
					(expected_room + delta)) < 0.00001f);
			}
			printf("sound-environment map=%d bsp=%d cluster=%u palette=%d tag=%ld background=%ld boundary=%d status=passed\n",
				retail_collision_map_id, global_structure_bsp_index,
				cluster_index, palette_index,
				environment_entry->sound_environment.index,
				background_sound_index, crossed_water_boundary);
			++retail_sound_environment_query_count;
			break;
		}
		assert_relocated_sound_pas(structure, retail_collision_map_id);
		assert_relocated_fog_plane(structure, retail_collision_map_id);
		players_globals = previous_players_globals;
	}
	assert_relocated_player_pvs_aggregation();
	++cluster_query_count;
}

/* Probe the actual CE collision-BSP traversal against the active materialized
 * retail image. Candidate vertical segments are derived from serialized
 * collision vertices; no collision algorithm or geometry is reimplemented in
 * the harness. */
static void assert_relocated_collision_query(void)
{
	struct structure_bsp *structure = global_structure_bsp;
	struct collision_bsp *bsp = global_collision_bsp;
	struct collision_surface *surfaces;
	struct structure_collision_material *materials;
	struct structure_leaf *structure_leaves;
	struct scenario_structure_bsp_reference *scenario_refs;
	unsigned char *bsp_image_snapshot;
	void *bsp_image_base;
	size_t bsp_image_bytes;
	short published_bsp_index;
	long sample_count, sample, stride;
	int found = 0;

	assert(structure != NULL && bsp != NULL);
	assert((void *)bsp == structure->collision_bsp.address);
	assert(bsp->vertices.count > 0 && bsp->vertices.address != NULL);
	assert(bsp->surfaces.count > 0 && bsp->surfaces.address != NULL);
	assert(bsp->bsp3d.planes.count > 0 && bsp->bsp3d.planes.address != NULL);
	assert(structure->collision_materials.count > 0 &&
		structure->collision_materials.address != NULL);
	assert(structure->leaves.count > 0 && structure->leaves.address != NULL);
	surfaces = (struct collision_surface *)bsp->surfaces.address;
	materials = (struct structure_collision_material *)structure->collision_materials.address;
	structure_leaves = (struct structure_leaf *)structure->leaves.address;
	sample_count = bsp->surfaces.count < 2048 ? bsp->surfaces.count : 2048;
	stride = bsp->surfaces.count / sample_count;
	if (stride < 1) stride = 1;
	for (sample = 0; sample < sample_count && !found; ++sample)
	{
		struct collision_bsp_test_vector_result result;
		struct collision_result ce_result;
		real_plane3d expected_plane;
		byte breakable_flags_before[sizeof(retail_breakable_surface_flags)];
		real_point3d polygon[MAXIMUM_VERTICES_PER_COLLISION_SURFACE];
		real_point3d center = { 0.0f, 0.0f, 0.0f };
		real_vector3d normal;
		real_point3d start;
		real_vector3d movement;
		long surface_index = sample * stride;
		long point_count, point;
		long plane_index;
		long leaf;
		int valid_cluster_seen = 0;
		uintptr_t plane_base, plane_end, plane_result;
		float normal_length_squared;

		if (surface_index >= bsp->surfaces.count)
			surface_index = bsp->surfaces.count - 1;
		point_count = collision_surface_polygon(bsp, surface_index, polygon);
		if (point_count < 3 || point_count > MAXIMUM_VERTICES_PER_COLLISION_SURFACE)
			continue;
		for (point = 0; point < point_count; ++point)
		{
			center.x += polygon[point].x;
			center.y += polygon[point].y;
			center.z += polygon[point].z;
		}
		center.x /= (float)point_count;
		center.y /= (float)point_count;
		center.z /= (float)point_count;
		plane_index = (long)((unsigned long)surfaces[surface_index].plane_designator & 0x7FFFFFFFUL);
		if (plane_index < 0 || plane_index >= bsp->bsp3d.planes.count)
			continue;
		normal.i = ((real_plane3d *)bsp->bsp3d.planes.address)[plane_index].n.i;
		normal.j = ((real_plane3d *)bsp->bsp3d.planes.address)[plane_index].n.j;
		normal.k = ((real_plane3d *)bsp->bsp3d.planes.address)[plane_index].n.k;
		if ((unsigned long)surfaces[surface_index].plane_designator & 0x80000000UL)
		{
			normal.i = -normal.i;
			normal.j = -normal.j;
			normal.k = -normal.k;
		}
		normal_length_squared = normal.i * normal.i + normal.j * normal.j + normal.k * normal.k;
		if (normal_length_squared < 0.25f || normal_length_squared > 2.25f)
			continue;
		start.x = center.x + normal.i * 2.0f;
		start.y = center.y + normal.j * 2.0f;
		start.z = center.z + normal.k * 2.0f;
		movement.i = -normal.i * 4.0f;
		movement.j = -normal.j * 4.0f;
		movement.k = -normal.k * 4.0f;
		memset(&result, 0, sizeof(result));
		if (!collision_bsp_test_vector(3UL, bsp, 0, NULL, &start,
			&movement, 1.0f, &result))
			continue;
		assert(result.surface_index >= 0 && result.surface_index < bsp->surfaces.count);
		assert(result.t >= 0.0f && result.t <= 1.0f);
		assert(result.plane != NULL);
		plane_base = (uintptr_t)bsp->bsp3d.planes.address;
		plane_end = plane_base + (size_t)bsp->bsp3d.planes.count * sizeof(real_plane3d);
		plane_result = (uintptr_t)result.plane;
		assert(plane_result >= plane_base && plane_result + sizeof(real_plane3d) <= plane_end);
		/* Retail collision surfaces may intentionally use NONE (untyped).
		 * Keep searching until the probe exercises a mapped material. */
		if (result.material_index == NONE)
			continue;
		assert(result.material_index >= 0 &&
			result.material_index < structure->collision_materials.count);
		assert(materials[result.material_index].runtime_physics_material_type >= 0);
		assert(result.leaf_count >= 0 && result.leaf_count <= 256);
		for (leaf = 0; leaf < result.leaf_count; ++leaf)
		{
			long leaf_index = result.leaf_indices[leaf] & LONG_MAX;
			short cluster_index;
			assert(leaf_index >= 0 && leaf_index < bsp->leaves.count);
			assert(leaf_index < structure->leaves.count);
			cluster_index = structure_leaves[leaf_index].cluster_index;
			assert(cluster_index == NONE ||
				(cluster_index >= 0 && cluster_index < structure->clusters.count));
			if (cluster_index != NONE)
				valid_cluster_seen = 1;
		}
		if (!valid_cluster_seen)
			continue;

		/* Exercise CE's public collision wrapper on the exact same real-map
		 * segment. Object and media flags are intentionally absent, so this
		 * qualifies structure-result composition only, not those other paths. */
		published_bsp_index = global_structure_bsp_index;
		scenario_refs = (struct scenario_structure_bsp_reference *)
			global_scenario->structure_bsp_references.address;
		assert(scenario_refs != NULL && published_bsp_index >= 0 &&
			published_bsp_index < global_scenario->structure_bsp_references.count);
		bsp_image_bytes = (size_t)scenario_refs[published_bsp_index].file_size;
		bsp_image_base = global_tag_instances[(short)
			scenario_refs[published_bsp_index].structure_bsp.index].base_address;
		assert(bsp_image_base == (void *)structure && bsp_image_bytes > 0);
		bsp_image_snapshot = (unsigned char *)malloc(bsp_image_bytes);
		assert(bsp_image_snapshot != NULL);
		memcpy(bsp_image_snapshot, bsp_image_base, bsp_image_bytes);
		memcpy(breakable_flags_before, retail_breakable_surface_flags,
			sizeof(breakable_flags_before));
		memset(&ce_result, 0xCD, sizeof(ce_result));
		assert(collision_test_vector(
			FLAG(_collision_test_structure_bit) |
			FLAG(_collision_test_front_facing_surfaces_bit),
			&start, &movement, NONE, &ce_result));
		assert(ce_result.type == _collision_result_structure);
		assert(ce_result.t >= 0.0f && ce_result.t <= 1.0f);
		assert(fabsf(ce_result.t - result.t) < 0.0001f);
		assert(ce_result.surface_index == result.surface_index);
		assert(ce_result.material_index == result.material_index);
		assert(ce_result.material_type ==
			materials[result.material_index].runtime_physics_material_type);
		assert(ce_result.plane_designator == result.plane_designator);
		expected_plane = *result.plane;
		if ((unsigned long)result.plane_designator & 0x80000000UL)
		{
			expected_plane.n.i = -expected_plane.n.i;
			expected_plane.n.j = -expected_plane.n.j;
			expected_plane.n.k = -expected_plane.n.k;
			expected_plane.d = -expected_plane.d;
		}
		assert(fabsf(ce_result.plane.n.i - expected_plane.n.i) < 0.0001f);
		assert(fabsf(ce_result.plane.n.j - expected_plane.n.j) < 0.0001f);
		assert(fabsf(ce_result.plane.n.k - expected_plane.n.k) < 0.0001f);
		assert(fabsf(ce_result.plane.d - expected_plane.d) < 0.0001f);
		assert(ce_result.start_location.leaf_index ==
			(result.leaf_indices[0] & LONG_MAX));
		assert(ce_result.location.leaf_index ==
			(result.leaf_indices[result.leaf_count - 1] & LONG_MAX));
		assert(ce_result.start_location.leaf_index >= 0 &&
			ce_result.start_location.leaf_index < structure->leaves.count);
		assert(ce_result.location.leaf_index >= 0 &&
			ce_result.location.leaf_index < structure->leaves.count);
		assert(ce_result.start_location.cluster_index ==
			structure_leaves[ce_result.start_location.leaf_index].cluster_index);
		assert(ce_result.location.cluster_index ==
			structure_leaves[ce_result.location.leaf_index].cluster_index);
		assert(fabsf(ce_result.point.x -
			(start.x + ce_result.t * movement.i)) < 0.0001f);
		assert(fabsf(ce_result.point.y - (start.y + ce_result.t * movement.j)) < 0.0001f);
		assert(fabsf(ce_result.point.z - (start.z + ce_result.t * movement.k)) < 0.0001f);
		assert(forbidden_object_adapter_calls == 0);
		assert(global_structure_bsp_index == published_bsp_index);
		assert(scenario_globals->structure_bsp_index == published_bsp_index);
		{
			const hcu_raw_collision_golden *golden = NULL;
			struct collision_result raw_result;
			real_point3d raw_start;
			real_vector3d raw_vector;
			unsigned golden_index;
			for (golden_index = 0;
				golden_index < HCU_RAW_COLLISION_GOLDEN_COUNT;
				++golden_index)
			{
				const hcu_raw_collision_golden *candidate =
					&hcu_raw_collision_goldens[golden_index];
				if (candidate->map_id == retail_collision_map_id &&
					candidate->bsp_index == published_bsp_index)
				{
					golden = candidate;
					break;
				}
			}
			assert(golden != NULL && "raw-source collision golden is missing");
			raw_start.x = golden->start[0];
			raw_start.y = golden->start[1];
			raw_start.z = golden->start[2];
			raw_vector.i = golden->vector[0];
			raw_vector.j = golden->vector[1];
			raw_vector.k = golden->vector[2];
			memset(&raw_result, 0xCD, sizeof(raw_result));
			assert(collision_test_vector(
				FLAG(_collision_test_structure_bit) |
				FLAG(_collision_test_front_facing_surfaces_bit),
				&raw_start, &raw_vector, NONE, &raw_result));
			assert(raw_result.type == _collision_result_structure);
			assert(raw_result.surface_index == golden->surface_index);
			assert(raw_result.material_index == golden->material_index);
			assert(raw_result.material_type == golden->material_type);
			assert(raw_result.plane_designator == golden->plane_designator);
			assert(fabsf(raw_result.t - golden->t) < 0.0001f);
			assert(raw_result.plane.n.i == golden->plane[0]);
			assert(raw_result.plane.n.j == golden->plane[1]);
			assert(raw_result.plane.n.k == golden->plane[2]);
			assert(raw_result.plane.d == golden->plane[3]);
			assert(fabsf(raw_result.point.x - golden->point[0]) < 0.0001f);
			assert(fabsf(raw_result.point.y - golden->point[1]) < 0.0001f);
			assert(fabsf(raw_result.point.z - golden->point[2]) < 0.0001f);
			assert(raw_result.start_location.leaf_index == golden->leaf_index);
			assert(raw_result.location.leaf_index == golden->location_leaf_index);
			assert(raw_result.start_location.cluster_index == golden->cluster_index);
			assert(raw_result.location.cluster_index == golden->location_cluster_index);
			assert(forbidden_object_adapter_calls == 0);
			assert(global_structure_bsp_index == published_bsp_index);
			assert(scenario_globals->structure_bsp_index == published_bsp_index);
			{
				const hcu_raw_collision_directional_golden *directional = NULL;
				struct collision_result directional_result;
				real_point3d directional_start;
				real_vector3d directional_vector;
				unsigned directional_index;
				for (directional_index = 0;
					directional_index < HCU_RAW_COLLISION_DIRECTIONAL_GOLDEN_COUNT;
					++directional_index)
				{
					const hcu_raw_collision_directional_golden *candidate =
						&hcu_raw_collision_directional_goldens[directional_index];
					if (candidate->map_id == retail_collision_map_id &&
						candidate->bsp_index == published_bsp_index)
					{
						directional = candidate;
						break;
					}
				}
				if (directional != NULL)
				{
					/* A raw-source-proven short segment stays within one empty
					 * leaf and intersects none of the decoded source polygons.
					 * On a miss only wrapper-initialized or traversal-written
					 * fields are inspected; hit-only fields remain poisoned. */
					directional_start.x = directional->miss_start[0];
					directional_start.y = directional->miss_start[1];
					directional_start.z = directional->miss_start[2];
					directional_vector.i = directional->miss_vector[0];
					directional_vector.j = directional->miss_vector[1];
					directional_vector.k = directional->miss_vector[2];
					memset(&directional_result, 0xCD, sizeof(directional_result));
					assert(!collision_test_vector(
						FLAG(_collision_test_structure_bit) |
						FLAG(_collision_test_front_facing_surfaces_bit),
						&directional_start, &directional_vector, NONE,
						&directional_result));
					assert(directional_result.type == NONE);
					assert(directional_result.t == 1.0f);
					assert(directional_result.start_location.leaf_index ==
						directional->miss_leaf);
					assert(directional_result.location.leaf_index ==
						directional->miss_leaf);
					assert(directional_result.start_location.cluster_index ==
						directional->miss_cluster);
					assert(directional_result.location.cluster_index ==
						directional->miss_cluster);

					/* Reverse the exact raw hit. Front-only rejects the
					 * solid-to-empty transition; back-only accepts it. */
					directional_start.x = directional->reverse_start[0];
					directional_start.y = directional->reverse_start[1];
					directional_start.z = directional->reverse_start[2];
					directional_vector.i = directional->reverse_vector[0];
					directional_vector.j = directional->reverse_vector[1];
					directional_vector.k = directional->reverse_vector[2];
					memset(&directional_result, 0xCD, sizeof(directional_result));
					assert(!collision_test_vector(
						FLAG(_collision_test_structure_bit) |
						FLAG(_collision_test_front_facing_surfaces_bit),
						&directional_start, &directional_vector, NONE,
						&directional_result));
					assert(directional_result.type == NONE);
					assert(directional_result.t == 1.0f);
					assert(directional_result.start_location.leaf_index ==
						golden->leaf_index);
					assert(directional_result.location.leaf_index ==
						golden->leaf_index);
					assert(directional_result.start_location.cluster_index ==
						golden->cluster_index);
					assert(directional_result.location.cluster_index ==
						golden->cluster_index);

					memset(&directional_result, 0xCD, sizeof(directional_result));
					assert(collision_test_vector(
						FLAG(_collision_test_structure_bit) |
						FLAG(_collision_test_back_facing_surfaces_bit),
						&directional_start, &directional_vector, NONE,
						&directional_result));
					assert(directional_result.type == _collision_result_structure);
					assert(directional_result.surface_index ==
						directional->reverse_surface);
					assert(directional_result.surface_index == golden->surface_index);
					assert(directional_result.material_index == golden->material_index);
					assert(directional_result.material_type == golden->material_type);
					assert(directional_result.plane_designator ==
						golden->plane_designator);
					assert(fabsf(directional_result.t - directional->reverse_t) <
						0.0001f);
					assert(fabsf(directional_result.point.x -
						directional->reverse_point[0]) < 0.0001f);
					assert(fabsf(directional_result.point.y -
						directional->reverse_point[1]) < 0.0001f);
					assert(fabsf(directional_result.point.z -
						directional->reverse_point[2]) < 0.0001f);
					/* CE returns from the solid-to-empty face test before
					 * appending the current empty leaf. The wrapper therefore
					 * leaves these preinitialized location fields at NONE. */
					assert(directional_result.start_location.leaf_index == NONE);
					assert(directional_result.location.leaf_index == NONE);
					assert(directional_result.start_location.cluster_index == NONE);
					assert(directional_result.location.cluster_index == NONE);
					assert(forbidden_object_adapter_calls == 0);
					assert(global_structure_bsp_index == published_bsp_index);
					assert(scenario_globals->structure_bsp_index ==
						published_bsp_index);
					assert(memcmp(bsp_image_snapshot, bsp_image_base,
						bsp_image_bytes) == 0);
					assert(memcmp(breakable_flags_before,
						retail_breakable_surface_flags,
						sizeof(breakable_flags_before)) == 0);
					printf("collision-directional-golden map=%d bsp=%d miss-leaf=%d "
						"cluster=%d reverse-surface=%d t=%.9g status=passed\n",
						retail_collision_map_id, published_bsp_index,
						directional->miss_leaf, directional->miss_cluster,
						directional_result.surface_index,
						directional_result.t);
				}
			}
			printf("collision-golden map=%d bsp=%d surface=%d material=%d "
				"type=%d leaf=%d cluster=%d t=%.9g point=%.9g,%.9g,%.9g\n",
				retail_collision_map_id, published_bsp_index,
				golden->surface_index, golden->material_index,
				golden->material_type, golden->leaf_index, golden->cluster_index,
				raw_result.t, raw_result.point.x, raw_result.point.y,
				raw_result.point.z);
		}
		assert(global_structure_bsp == structure && global_collision_bsp == bsp);
		assert(memcmp(bsp_image_snapshot, bsp_image_base, bsp_image_bytes) == 0);
		assert(memcmp(breakable_flags_before, retail_breakable_surface_flags,
			sizeof(breakable_flags_before)) == 0);
		free(bsp_image_snapshot);
		++ce_collision_wrapper_query_count;
		found = 1;
		++collision_query_count;
	}
	assert(found && "CE collision traversal found no material-bearing retail hit");
	if (retail_collision_map_id == 30 && global_structure_bsp_index == 0)
	{
		assert_a30_shared_edge_grazing();
		assert_a30_flagged_surface_queries();
	}
}

/* CE's collision-BSP implementation profiles query calls through these
 * functions. Profiling is not part of this fixture's behavioral contract. */
short const global_projection3d_mappings[3][2][2] = {
	{{2, 1}, {1, 2}}, {{0, 2}, {2, 0}}, {{1, 0}, {0, 1}}
};
void collision_log_usage(short collision_function)
{
	(void)collision_function;
}
void collision_log_start_time(LARGE_INTEGER *start_time)
{
	start_time->QuadPart = 0;
}
void collision_log_end_time(short collision_function, __int64 end_time)
{
	(void)collision_function;
	(void)end_time;
}

static void package_transaction(char **argv, int direct_mode)
{
	struct cache_file_header opened_header;
	struct cache_file_tag_header *tag_header;
	struct cache_file_tag_instance *tag_table;
	struct scenario *scenario;
	struct scenario_structure_bsp_reference *refs;
	boolean complete = FALSE;
	unsigned scenario_datum;
	unsigned i;
	unsigned j;
	unsigned failure_index;
	unsigned char *first_bsp_snapshot;
	unsigned char resource_actual[16], resource_expected[16];
	uint32_t resource_offset;
	FILE *source_file;
	retail_bsp_snapshot committed_bsp;
	const char *clean_package_path = NULL;
	memset(retail_breakable_surface_flags, 0xFF,
		sizeof(retail_breakable_surface_flags));
	unsigned visitor_count_before;
	direct_visitor_mode = direct_mode;

	retail_ref_count = (unsigned)strtoul(argv[8], NULL, 0);
	retail_collision_map_id = strcmp(argv[2], "a30") == 0 ? 30 : 50;
	assert(strcmp(argv[2], "a30") == 0 || strcmp(argv[2], "a50") == 0);
	assert(retail_ref_count >= 2 && retail_ref_count <= RETAIL_MAX_BSP_REFS);
	if (direct_mode) {
		assert(retail_ref_count > 1);
		clean_package_path = argv[9 + 2 * retail_ref_count];
		assert(clean_package_path && strcmp(clean_package_path, argv[1]) != 0);
	}
	for (i = 0; i < retail_ref_count; ++i)
	{
		retail_offset[i] = (unsigned)strtoul(argv[9 + i * 2], NULL, 0);
		retail_size[i] = (unsigned)strtoul(argv[10 + i * 2], NULL, 0);
		assert(retail_size[i] <= sizeof bsp_cache);
	}
	failure_index = retail_ref_count - 1;

	cache_files_initialize();
	arena_init(&retail_owner, "test-ctag-owner", retail_owner_bytes,
		sizeof retail_owner_bytes);
	arena_init(&retail_bsp_scratch, "test-bsp-scratch", retail_bsp_scratch_bytes,
		sizeof retail_bsp_scratch_bytes);
	arena_init(&retail_section_scratch, "test-section-scratch",
		retail_section_scratch_bytes,
		direct_mode ? DIRECT_SECTION_SCRATCH_BYTES :
			sizeof retail_section_scratch_bytes);
	memset(&direct_visit_service, 0, sizeof direct_visit_service);
	direct_visit_service.section_scratch = &retail_section_scratch;
	ctag_mount_init(&retail_mount);
	{
		int mount_result;
		/* This package copy has an incorrect stored CBIX CRC. HMAP/CTAG/CRNG
		 * decode first, and CBIX's payload is fully streamed into its owner
		 * before the real decoder reports the checksum mismatch. */
		mount_result = ctag_mount_hp2_file_verified_discover_with_bsp_catalog(
			&retail_mount, &retail_owner, &retail_bsp_scratch, argv[7], argv[2],
			argv[3], &retail_source, ctag_ps2_cache_backend(),
			load_package_section, NULL);
		assert(mount_result != 0);
		assert(!retail_source.active && retail_source.reader.descriptor < 0);
		assert(!retail_mount.active && !cache_files_precache_map_loaded(argv[2]));
		assert(retail_owner.used == 0 && retail_bsp_scratch.used == 0);
		assert(!cache_file_open(argv[2], &(struct cache_file_header){0}));

		fail_section_once = "CBIX";
		mount_result = ctag_mount_hp2_file_verified_discover_with_bsp_catalog(
			&retail_mount, &retail_owner, &retail_bsp_scratch, argv[1], argv[2],
			argv[3], &retail_source, ctag_ps2_cache_backend(),
			load_package_section,
			direct_mode ? (void *)&direct_visit_service : NULL);
		assert(mount_result != 0);
		assert(!retail_source.active && retail_source.reader.descriptor < 0);
		assert(!retail_mount.active && !cache_files_precache_map_loaded(argv[2]));
		assert(retail_owner.used == 0 && retail_bsp_scratch.used == 0);
		assert(!cache_file_open(argv[2], &(struct cache_file_header){0}));

		/* Retry through the same production bounded HP2 reader and keep the
		 * actual retail map descriptor owned by the mount. */
		mount_result = ctag_mount_hp2_file_verified_discover_with_bsp_catalog(
			&retail_mount, &retail_owner, &retail_bsp_scratch, argv[1], argv[2],
			argv[3], &retail_source, ctag_ps2_cache_backend(),
			load_package_section,
			direct_mode ? (void *)&direct_visit_service : NULL);
		if (mount_result != 0)
			fprintf(stderr, "parent mount failed result=%d owner=%lu scratch=%lu\n",
				mount_result, (unsigned long)retail_owner.used,
				(unsigned long)retail_bsp_scratch.used);
		assert(mount_result == 0);
	}
	assert(retail_source.active && retail_source.reader.descriptor >= 0);
	if (direct_mode) {
		direct_visit_service.source = retail_source;
		assert(ctag_mount_set_bsp_section_visitor(&retail_mount,
			hcu_map_service_test_visit_section));
		hcu_map_service_test_reset_visit_count();
		printf("test-only capacity bypass: mounted a50 fixture directly; ");
		printf("normal hcu_map_service_preflight remains UI-only\n");
	}
	assert(retail_source.reader.size == (uint32_t)strtoul(argv[4], NULL, 0));
	assert(cache_file_open(argv[2], &opened_header));
	assert(opened_header.tag_data_size > 0 &&
		(unsigned)opened_header.tag_data_size <= sizeof tag_cache);
	cache_file_globals.header = opened_header;
	cache_file_read(NONE, opened_header.tag_data_offset,
		opened_header.tag_data_size, tag_cache, &complete, TRUE);
	assert(complete == TRUE);
	tag_header = (struct cache_file_tag_header *)tag_cache;
	tag_table = tag_header->tag_instances;
	assert(tag_header->signature == CACHE_FILE_TAG_HEADER_SIGNATURE);
	assert(tag_header->tag_count > 1 && (uintptr_t)tag_table >=
		(uintptr_t)tag_cache &&
		(uintptr_t)tag_table + (size_t)tag_header->tag_count *
		sizeof(*tag_table) <= (uintptr_t)tag_cache +
		(unsigned long)opened_header.tag_data_size);
	global_tag_instances = tag_table;
	global_tag_count = tag_header->tag_count;
	cache_file_globals.tag_header = tag_header;
	cache_file_globals.tags_loaded = TRUE;
	assert(tag_validate_claims_buffer_size() <= sizeof retail_claims_bytes);
	assert(tag_validate_bind_claims_buffer(retail_claims_bytes,
		sizeof retail_claims_bytes));
	if (!tag_validate_tags(tag_header, opened_header.tag_data_size,
		(long)strtoul(argv[4], NULL, 0), argv[2]))
	{
		fprintf(stderr, "real CE tag_validate_tags rejected %s CTAG (%d reports)\n", argv[2],
			error_count);
		assert(0);
	}
	scenario_datum = (unsigned)tag_header->scenario_tag_index;
	scenario = (struct scenario *)tag_get(SCENARIO_TAG, scenario_datum);
	assert(scenario != NULL);
	/* A non-NONE tag resource read must be CRNG-authorized and served from the
	 * retained, verified retail map descriptor rather than a fake callback. */
	assert(retail_mount.resource_index.interval_count > 0);
	resource_offset = (uint32_t)retail_mount.resource_index.bytes[36] |
		((uint32_t)retail_mount.resource_index.bytes[37] << 8) |
		((uint32_t)retail_mount.resource_index.bytes[38] << 16) |
		((uint32_t)retail_mount.resource_index.bytes[39] << 24);
	assert(ctag_resource_index_allows(&retail_mount.resource_index,
		resource_offset, sizeof resource_actual));
	source_file = fopen(argv[3], "rb");
	assert(source_file && fseek(source_file, (long)resource_offset, SEEK_SET) == 0);
	assert(fread(resource_expected, 1, sizeof resource_expected, source_file) ==
		sizeof resource_expected);
	fclose(source_file);
	complete = FALSE;
	cache_file_read((long)tag_header->scenario_tag_index, resource_offset,
		sizeof resource_actual, resource_actual, &complete, TRUE);
	assert(complete == TRUE && memcmp(resource_actual, resource_expected,
		sizeof resource_actual) == 0);
	global_scenario = scenario;
	refs = (struct scenario_structure_bsp_reference *)scenario->structure_bsp_references.address;
	assert((unsigned)scenario->structure_bsp_references.count == retail_ref_count && refs != NULL);
	for (i = 0; i < retail_ref_count; ++i)
	{
		assert((unsigned)refs[i].file_offset == retail_offset[i]);
		assert((unsigned)refs[i].file_size == retail_size[i]);
		assert(global_tag_instances[(short)refs[i].structure_bsp.index].group_tag ==
			STRUCTURE_BSP_TAG);
	}

	memset(&globals_fixture, 0, sizeof(globals_fixture));
	scenario_globals = &globals_fixture;
	global_structure_bsp_index = NONE;
	scenario_globals->structure_bsp_index = NONE;
	global_structure_bsp = NULL;
	global_collision_bsp = NULL;
	global_bsp3d = NULL;
	loaded_datum = -1;
	fail_schema_mask = fail_verify_mask = 0;
	fail_load_index = -1;
	fail_load_also_index = -1;
	unload_count = load_count = verify_count = register_count = schema_count = menu_count = error_count = 0;
	time_stop_count = time_start_count = collision_off_count = collision_on_count = 0;
	disconnect_count = reconnect_count = selected_count = successful_bsp_sections = 0;
	cluster_query_count = collision_query_count = ce_collision_wrapper_query_count = 0;
	forbidden_object_adapter_calls = 0;
	memset(direct_visit_sink_bytes, 0, sizeof(direct_visit_sink_bytes));
	memset(direct_visit_succeeded, 0, sizeof(direct_visit_succeeded));

	/* The map is retail package-backed, and its scenario/tag table is the real
	 * relocated CTAG. Only schema/port and machine leaves remain controlled. */
	assert(scenario_switch_structure_bsp(0) == TRUE);
	assert_parent_scratch_released();
	assert(global_structure_bsp_index == 0 && scenario_globals->structure_bsp_index == 0);
	assert(global_structure_bsp == global_tag_instances[(short)refs[0].structure_bsp.index].base_address);
	for (j = 1; j < retail_ref_count; ++j)
		assert(global_tag_instances[(short)refs[j].structure_bsp.index].base_address == NULL);
	assert_relocated_cluster_queries();
	assert_relocated_collision_query();
	committed_bsp = capture_retail_bsp_snapshot(0);
	first_bsp_snapshot = (unsigned char *)malloc((size_t)refs[0].file_size);
	assert(first_bsp_snapshot != NULL);
	memcpy(first_bsp_snapshot, bsp_cache, (size_t)refs[0].file_size);
	/* A transport EOF after a real partial cache_file_read must not set CE's
	 * completion flag. The destination may contain a partial prefix, so callers
	 * must honor that flag; committed scenario/BSP publication and ownership
	 * must remain unchanged, and the same resource must be retryable. */
	memset(resource_actual, 0xA5, sizeof resource_actual);
	complete = TRUE;
	resource_read_partial_seen = 0;
	resource_read_eof_seen = 0;
	resource_read_fail_after_bytes = 3;
	cache_file_read((long)tag_header->scenario_tag_index, resource_offset,
		sizeof resource_actual, resource_actual, &complete, TRUE);
	assert(resource_read_partial_seen && resource_read_eof_seen &&
		complete != TRUE);
	assert(memcmp(resource_actual, resource_expected, 3) == 0);
	for (i = 3; i < sizeof resource_actual; ++i)
		assert(resource_actual[i] == 0xA5);
	assert_retail_bsp_snapshot(&committed_bsp);
	memset(resource_actual, 0xA5, sizeof resource_actual);
	complete = FALSE;
	cache_file_read((long)tag_header->scenario_tag_index, resource_offset,
		sizeof resource_actual, resource_actual, &complete, TRUE);
	assert(complete == TRUE && memcmp(resource_actual, resource_expected,
		sizeof resource_actual) == 0);
	assert_retail_bsp_snapshot(&committed_bsp);
	assert(selected_count == 1 && selected_order[0] == 0);
	if (direct_mode) {
		unsigned successful_before = successful_bsp_sections;
		visitor_count_before = hcu_map_service_test_visit_count();
		/* The package has a deliberately bad stored B001 CRC. The real visitor
		 * writes candidate data, then rejects its outer HP2 section checksum;
		 * CE must restore B000 before any candidate publication. */
		assert(scenario_switch_structure_bsp(1) == FALSE);
		assert(hcu_map_service_test_visit_count() == visitor_count_before + 2);
		assert(selected_order[selected_count - 2] == 1 &&
			selected_order[selected_count - 1] == 0);
		/* The first 36 bytes are only the stack-buffered CBSP envelope header;
		 * this proves at least one candidate image byte reached the destination. */
		assert(direct_visit_sink_bytes[1] > 36u);
		/* A valid outer HP2 section reaches the full direct sink; the bad
		 * inner CBSP image CRC is rejected only after HP2 visitation succeeds. */
		assert(direct_visit_succeeded[1] ==
			(direct_inner_crc_mode || direct_rebase_mode));
		assert(successful_bsp_sections == successful_before +
			((direct_inner_crc_mode || direct_rebase_mode) ? 2u : 1u));
		assert_retail_bsp_snapshot(&committed_bsp);
		assert(memcmp(first_bsp_snapshot, bsp_cache,
			(size_t)refs[0].file_size) == 0);
		assert_parent_scratch_released();
		/* Replace the corrupted package at the same path and retry without
		 * restarting CE, the mount, source descriptor, or cache backend. */
		overwrite_file(argv[1], clean_package_path);
		retry_candidate_and_restore(1, &committed_bsp);
		assert(hcu_map_service_test_visit_count() == visitor_count_before + 4);
		assert(direct_visit_sink_bytes[1] > 36u && direct_visit_succeeded[1]);
		assert(successful_bsp_sections == successful_before +
			((direct_inner_crc_mode || direct_rebase_mode) ? 4u : 3u));
		assert(memcmp(first_bsp_snapshot, bsp_cache,
			(size_t)refs[0].file_size) == 0);
		/* Keep the baseline B000 selection that the remainder of this fixture
		 * expects before it exercises the ordinary CE switch/failure cases. */
		selected_count = 1;
		selected_order[0] = 0;
		successful_bsp_sections = 1;
		hcu_map_service_test_reset_visit_count();
	}
	for (i = 1; i < retail_ref_count; ++i)
	{
		assert(scenario_switch_structure_bsp((short)i) == TRUE);
		assert_parent_scratch_released();
		assert(global_structure_bsp_index == (short)i &&
			scenario_globals->structure_bsp_index == (short)i);
		assert(global_tag_instances[(short)refs[i - 1].structure_bsp.index].base_address == NULL);
		assert(global_structure_bsp ==
			global_tag_instances[(short)refs[i].structure_bsp.index].base_address);
		assert_relocated_cluster_queries();
		assert_relocated_collision_query();
		for (j = 0; j < retail_ref_count; ++j)
			if (j != i)
				assert(global_tag_instances[(short)refs[j].structure_bsp.index].base_address == NULL);
		assert(selected_count == i + 1 && selected_order[i] == i);
		assert(memcmp(first_bsp_snapshot, bsp_cache,
			(size_t)refs[0].file_size) != 0);
	}
	assert(scenario_switch_structure_bsp(0) == TRUE);
	assert_parent_scratch_released();
	assert(global_tag_instances[(short)refs[retail_ref_count - 1].structure_bsp.index].base_address == NULL);
	assert(global_structure_bsp == global_tag_instances[(short)refs[0].structure_bsp.index].base_address);
	for (j = 1; j < retail_ref_count; ++j)
		assert(global_tag_instances[(short)refs[j].structure_bsp.index].base_address == NULL);
	assert_relocated_cluster_queries();
	assert_relocated_collision_query();
	assert(selected_count == retail_ref_count + 1 &&
		selected_order[retail_ref_count] == 0);
	assert(memcmp(first_bsp_snapshot, bsp_cache, (size_t)refs[0].file_size) == 0);

	/* Fail B001's owner read: CE must rematerialize B000 and retain only its
	 * datum/global publication. Exact source identity is observed in callback. */
	fail_load_index = (int)failure_index;
	assert(scenario_switch_structure_bsp((short)failure_index) == FALSE);
	assert_parent_scratch_released();
	assert(global_structure_bsp_index == 0 && scenario_globals->structure_bsp_index == 0);
	assert(global_tag_instances[(short)refs[0].structure_bsp.index].base_address ==
		global_structure_bsp);
	assert(global_tag_instances[(short)refs[failure_index].structure_bsp.index].base_address == NULL);
	assert(selected_order[selected_count - 2] == failure_index &&
		selected_order[selected_count - 1] == 0);
	assert(register_count == unload_count + 1);
	assert(memcmp(first_bsp_snapshot, bsp_cache, (size_t)refs[0].file_size) == 0);
	assert_retail_bsp_snapshot(&committed_bsp);
	fail_load_index = -1;
	retry_candidate_and_restore(failure_index, &committed_bsp);

	/* A materialized candidate rejected by CE's port-capacity verifier must be
	 * unloaded, then the real old retail extent must be selected and restored. */
	fail_verify_mask = 1 << failure_index;
	assert(scenario_switch_structure_bsp((short)failure_index) == FALSE);
	assert_parent_scratch_released();
	assert(global_structure_bsp_index == 0 && scenario_globals->structure_bsp_index == 0);
	assert(global_tag_instances[(short)refs[0].structure_bsp.index].base_address ==
		global_structure_bsp);
	assert(global_tag_instances[(short)refs[failure_index].structure_bsp.index].base_address == NULL);
	assert(selected_order[selected_count - 2] == failure_index &&
		selected_order[selected_count - 1] == 0);
	assert(memcmp(first_bsp_snapshot, bsp_cache, (size_t)refs[0].file_size) == 0);
	assert(register_count == unload_count + 1);
	assert_retail_bsp_snapshot(&committed_bsp);
	fail_verify_mask = 0;
	retry_candidate_and_restore(failure_index, &committed_bsp);

	/* A candidate rejected by the schema boundary also rematerializes B000. */
	fail_schema_mask = 1 << failure_index;
	assert(scenario_switch_structure_bsp((short)failure_index) == FALSE);
	assert_parent_scratch_released();
	assert(global_structure_bsp_index == 0 && scenario_globals->structure_bsp_index == 0);
	assert(global_tag_instances[(short)refs[0].structure_bsp.index].base_address ==
		global_structure_bsp);
	assert(global_tag_instances[(short)refs[failure_index].structure_bsp.index].base_address == NULL);
	assert(selected_order[selected_count - 2] == failure_index &&
		selected_order[selected_count - 1] == 0);
	assert(memcmp(first_bsp_snapshot, bsp_cache, (size_t)refs[0].file_size) == 0);
	assert(register_count == unload_count + 1);
	assert_retail_bsp_snapshot(&committed_bsp);
	fail_schema_mask = 0;
	retry_candidate_and_restore(failure_index, &committed_bsp);

	/* If both candidate and old-source reads fail, CE must publish safe-null
	 * state and enter the menu rather than retain pointers into overwritten data. */
	fail_load_index = (int)failure_index;
	fail_load_also_index = 0;
	assert(scenario_switch_structure_bsp((short)failure_index) == FALSE);
	assert_parent_scratch_released();
	assert(global_structure_bsp_index == NONE && scenario_globals->structure_bsp_index == NONE);
	assert(global_structure_bsp == NULL && global_collision_bsp == NULL && global_bsp3d == NULL);
	assert(global_tag_instances[(short)refs[0].structure_bsp.index].base_address == NULL);
	assert(global_tag_instances[(short)refs[failure_index].structure_bsp.index].base_address == NULL);
	assert(menu_count == 1 &&
		selected_order[selected_count - 2] == failure_index &&
		selected_order[selected_count - 1] == 0);
	assert(register_count == unload_count);
	assert(global_structure_bsp_index == NONE && scenario_globals->structure_bsp_index == NONE);
	assert(global_structure_bsp == NULL && global_collision_bsp == NULL && global_bsp3d == NULL);
	assert(cache_file_globals.structure_bsp_header == NULL);
	assert(retail_owner.used == committed_bsp.owner_used && retail_bsp_scratch.used == 0);
	assert(!retail_mount.bsp_active);
	fail_load_index = fail_load_also_index = -1;
	retry_candidate_and_restore(failure_index, &committed_bsp);

	assert(successful_bsp_sections == retail_ref_count + 14);
	assert(cluster_query_count == retail_ref_count + 1);
	assert(collision_query_count == retail_ref_count + 1);
	assert(ce_collision_wrapper_query_count == collision_query_count);
	assert(!retail_mount.bsp_active && retail_bsp_scratch.used == 0);
	assert(retail_source.active && retail_source.reader.descriptor >= 0);

	printf("retail-ce-ps2-bsp-transaction map=%s refs=%u selections=%u bsp-sections=%u cluster-query-bsp=%u collision-query-bsp=%u status=passed\n",
		argv[2], retail_ref_count, selected_count, successful_bsp_sections,
		cluster_query_count, collision_query_count);
	free(first_bsp_snapshot);
	tag_validate_release_claims_buffer();
	cache_file_close();
	cache_file_globals.tags_loaded = FALSE;
	cache_file_globals.tag_header = NULL;
	global_tag_instances = NULL;
	global_tag_count = 0;
	ctag_mount_unload(&retail_mount);
	assert(retail_owner.used == 0 && retail_bsp_scratch.used == 0);
	assert(!retail_source.active && retail_source.reader.descriptor < 0);
	cache_files_dispose();
}
#endif

int main(int argc, char **argv)
{
#ifdef HCU_BSP_RETAIL_INTEGRATION
	int base_argc;
	int direct_mode;
	if (argc < 11) return 2;
	base_argc = 9 + 2 * (int)strtoul(argv[8], NULL, 0);
	direct_inner_crc_mode = argc == base_argc + 2 &&
		strcmp(argv[argc - 1], "--direct-cbsp-inner-crc") == 0;
	direct_rebase_mode = argc == base_argc + 2 &&
		strcmp(argv[argc - 1], "--direct-cbsp-rebase") == 0;
	direct_mode = direct_inner_crc_mode || direct_rebase_mode ||
		(argc == base_argc + 2 && strcmp(argv[argc - 1], "--direct-cbsp") == 0);
	if ((!direct_mode && argc != base_argc) ||
		(direct_mode && argc != base_argc + 2)) return 2;
	package_transaction(argv, direct_mode);
	return 0;
#else
	reset_fixture(0);
	assert(scenario_switch_structure_bsp(0) == FALSE);
	assert(unload_count == 0 && load_count == 0 && verify_count == 0);
	assert(disconnect_count == 0 && reconnect_count == 0);
	assert_published(0);

	assert(scenario_switch_structure_bsp(2) == FALSE);
	assert(unload_count == 0 && load_count == 0 && verify_count == 0);
	assert_published(0);

	assert(scenario_switch_structure_bsp(1) == TRUE);
	assert(unload_count == 1 && load_count == 1 && verify_count == 1);
	assert(disconnect_count == 10 && reconnect_count == 13);
	assert_published(1);

	reset_fixture(0);
	fail_schema_mask = 1 << 1;
	assert(scenario_switch_structure_bsp(1) == FALSE);
	assert(load_count == 2 && unload_count == 1 && verify_count == 1);
	assert_published(0);
	assert(menu_count == 0 && reconnect_count == 13);

	reset_fixture(0);
	fail_verify_mask = 1 << 1;
	assert(scenario_switch_structure_bsp(1) == FALSE);
	assert(load_count == 2 && unload_count == 2 && verify_count == 2);
	assert_published(0);
	assert(menu_count == 0 && reconnect_count == 13);

	reset_fixture(0);
	fail_verify_mask = (1 << 1) | (1 << 0);
	assert(scenario_switch_structure_bsp(1) == FALSE);
	assert(load_count == 2 && unload_count == 3 && verify_count == 2);
	assert(menu_count == 1);
	assert(disconnect_count == 10 && reconnect_count == 0);
	assert_safe_null();

	reset_fixture(0);
	fail_schema_mask = (1 << 1) | (1 << 0);
	/* The candidate fails, then the old reference also fails to reload. */
	assert(scenario_switch_structure_bsp(1) == FALSE);
	assert(load_count == 2 && menu_count == 1);
	assert_safe_null();

	reset_fixture(NONE);
	fail_schema_mask = 1 << 1;
	assert(scenario_switch_structure_bsp(1) == FALSE);
	assert_safe_null();
	assert(menu_count == 0);

	puts("real-ce-load-unload-switch branches=8 status=passed");
	return 0;
#endif
}
