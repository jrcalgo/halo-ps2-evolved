#include "cseries.h"
#include "stream/hcu_profile_mount.h"
#include "stream/sha256.h"
#include "cache/cache_files.h"
#include "core/mem.h"
#include "tag_schema.h"
#include "halo_ps2_cache.h"
#include "ps2_ctag.h"
#include "hcu_profile_mount_fixture_bindings.h"

#undef malloc
#undef free
#undef memset
#undef memcpy
#undef memcmp
#undef strcat
#undef strcmp
#undef strlen
#undef printf
#undef snprintf
#undef vprintf
#undef vfprintf
#undef vsnprintf
#undef fopen

#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdarg.h>

#define TAG_CACHE_BYTES HCU_PROFILE_MOUNT_TEST_TAG_CACHE_BYTES
#define BSP_CACHE_BYTES HCU_PROFILE_MOUNT_TEST_BSP_CACHE_BYTES
#define TEST_RESOURCE_BYTES 16u

struct cache_file_header {
	uint32_t header_signature;
	int32_t version;
	int32_t file_length;
	byte reservedC[4];
	int32_t tag_data_offset;
	int32_t tag_data_size;
	byte reserved18[8];
	char name[0x20];
	char build[0x20];
	byte reserved60[4];
	uint32_t checksum;
	byte reserved68[0x794];
	uint32_t footer_signature;
};

typedef struct {
	uint32_t *tag_instances;
	int32_t scenario_tag_index;
	uint32_t checksum;
	int32_t tag_count;
	int32_t vertex_buffer_count;
	uint32_t *vertex_buffers;
	int32_t index_buffer_count;
	uint32_t *index_buffers;
	uint32_t signature;
} test_tag_header;

static uint8_t s_tag_cache[TAG_CACHE_BYTES] __attribute__((aligned(16)));
static uint8_t s_bsp_cache[BSP_CACHE_BYTES] __attribute__((aligned(16)));
static uint8_t s_relocations[1024u * 1024u] __attribute__((aligned(16)));
static uint8_t s_stream_scratch[512] __attribute__((aligned(16)));
static uint8_t s_relocations_other[1024u * 1024u] __attribute__((aligned(16)));
static uint8_t s_stream_scratch_other[512] __attribute__((aligned(16)));
/* Slot count is set by -DHCU_PROFILE_MOUNT_TEST_RESIDENCY_SLOTS (default 16). */
#ifndef HCU_PROFILE_MOUNT_TEST_RESIDENCY_SLOTS
#define HCU_PROFILE_MOUNT_TEST_RESIDENCY_SLOTS 16u
#endif
#define RESIDENCY_SLOTS HCU_PROFILE_MOUNT_TEST_RESIDENCY_SLOTS
static uint8_t s_residency_arena[RESIDENCY_SLOTS * HCU_PROFILE_MOUNT_RESIDENCY_SEGMENT_BYTES] __attribute__((aligned(16)));
static hcu_asset_residency_entry s_residency_entries[RESIDENCY_SLOTS];
static uint8_t s_resource[TEST_RESOURCE_BYTES];
static uint8_t s_expected_resource[TEST_RESOURCE_BYTES];
static FILE *s_package_file;
static FILE *s_map_file;
static uint32_t s_package_size;
static uint32_t s_map_file_length;
static uint32_t s_map_reads;
static int32_t s_last_output_datum;
static uint32_t s_residency_high_water;
static uint32_t s_residency_refused_pins;
static uint32_t s_residency_evictions;

unsigned long physical_memory_get_tag_cache_size(void) { return TAG_CACHE_BYTES; }
void *physical_memory_get_tag_cache_base_address(void) { return s_tag_cache; }
void *physical_memory_get_structure_bsp_cache_base_address(void) { return s_bsp_cache; }
unsigned long physical_memory_get_structure_bsp_cache_size(void) { return BSP_CACHE_BYTES; }

void tag_validate_report(char const *message)
{
	if (message) fprintf(stderr, "%s\n", message);
}
int halo_linux_printf(const char *format, ...)
{
	va_list args; int result; va_start(args, format); result = vprintf(format, args); va_end(args); return result;
}
int halo_linux_fprintf(FILE *stream, const char *format, ...)
{
	va_list args; int result; va_start(args, format); result = vfprintf(stream, format, args); va_end(args); return result;
}
int halo_linux_snprintf(char *buffer, size_t size, const char *format, ...)
{
	va_list args; int result; va_start(args, format); result = vsnprintf(buffer, size, format, args); va_end(args); return result;
}
int halo_linux_vsnprintf(char *buffer, size_t size, const char *format, va_list args)
{ return vsnprintf(buffer, size, format, args); }
FILE *halo_linux_fopen(const char *path, const char *mode) { return fopen(path, mode); }
long csmemcmp(const void *left, const void *right, unsigned long size)
{ return (long)memcmp(left, right, (size_t)size); }
void *csmemset(void *buffer, long value, unsigned long size)
{ return memset(buffer, (int)value, (size_t)size); }
void *csmemcpy(void *destination, const void *source, unsigned long size)
{ return memcpy(destination, source, (size_t)size); }
void *debug_malloc(unsigned int size, boolean clear, const char *file, long line)
{
	void *p = malloc((size_t)size); (void)file; (void)line;
	if (clear && p) memset(p, 0, (size_t)size); return p;
}
void debug_free(void *buffer, const char *file, long line)
{ (void)file; (void)line; free(buffer); }
char *csstrcat(char *left, char const *right) { return strcat(left, right); }
unsigned long csstrlen(char const *text) { return (unsigned long)strlen(text); }
long csstrcmp(char const *left, char const *right) { return (long)strcmp(left, right); }

static int profile_read_at(void *context, uint32_t offset, void *destination,
	uint32_t size)
{
	FILE *file = (FILE *)context;
	if (!file || !destination || offset > s_package_size || size > s_package_size - offset ||
		fseek(file, (long)offset, SEEK_SET) != 0 || fread(destination, 1, size, file) != size)
		return -1;
	return 0;
}

static int source_read_at(void *context, int32_t output_datum,
	uint32_t offset, uint32_t size, void *destination, int blocking)
{
	FILE *file = (FILE *)context;
	(void)blocking;
	if (!file || !destination || offset > s_map_file_length ||
		size > s_map_file_length - offset ||
		fseek(file, (long)offset, SEEK_SET) != 0 || fread(destination, 1, size, file) != size)
		return 0;
	s_map_reads++;
	s_last_output_datum = output_datum;
	return 1;
}

static int source_read_exact(uint32_t offset, uint32_t size, void *destination)
{
	if (!s_map_file || !destination || offset > s_map_file_length ||
		size > s_map_file_length - offset ||
		fseek(s_map_file, (long)offset, SEEK_SET) != 0 || fread(destination, 1, size, s_map_file) != size)
		return 0;
	return 1;
}

static int set_profile_file_size(FILE *file)
{
	long size;
	if (fseek(file, 0, SEEK_END) != 0 || (size = ftell(file)) <= 0 ||
		(size_t)size > UINT32_MAX || fseek(file, 0, SEEK_SET) != 0)
		return 0;
	s_package_size = (uint32_t)size;
	return 1;
}

/* Every flipped byte is recorded so that an early exit restores the copy. */
static FILE *s_pending_file;
static long s_pending_offset;
static uint8_t s_pending_original;

static void restore_pending_flip(void)
{
	if (s_pending_file) {
		fseek(s_pending_file, s_pending_offset, SEEK_SET);
		fputc(s_pending_original, s_pending_file);
		fflush(s_pending_file);
		s_pending_file = NULL;
	}
}

static int flip_byte(FILE *file, uint32_t offset, uint8_t *original)
{
	int value;
	if (!file || !original || fseek(file, (long)offset, SEEK_SET) != 0 ||
		(value = fgetc(file)) == EOF) return 0;
	*original = (uint8_t)value;
	s_pending_file = file;
	s_pending_offset = (long)offset;
	s_pending_original = (uint8_t)value;
	if (fseek(file, (long)offset, SEEK_SET) != 0 || fputc(value ^ 0x40, file) == EOF ||
		fflush(file) != 0) return 0;
	return 1;
}

static int restore_byte(FILE *file, uint32_t offset, uint8_t original)
{
	if (!file || fseek(file, (long)offset, SEEK_SET) != 0 ||
		fputc(original, file) == EOF || fflush(file) != 0) return 0;
	s_pending_file = NULL;
	return 1;
}

/* Wrapper backend that records the CE visitor so a fixture can drive it with a
 * counting sink and observe exactly how many bytes were published. */
static const ctag_mount_backend *s_real_backend;
static ctag_mount_backend s_wrapped_backend;
static ctag_ctag_payload_visit_fn s_ctag_visit;
static void *s_ctag_visit_context;

static int wrap_register_ctag_visitor(void *context,
	ctag_ctag_payload_visit_fn visit, void *visitor_context)
{
	(void)context;
	s_ctag_visit = visit;
	s_ctag_visit_context = visitor_context;
	return s_real_backend->register_ctag_visitor(s_real_backend->context,
		visit, visitor_context);
}

static int s_force_bsp_register_failure;

static int wrap_register_bsp_visitor(void *context, ctag_bsp_visitor_fn visit,
	void *visitor_context)
{
	if (s_force_bsp_register_failure) return 0;
	return s_real_backend->register_bsp_visitor(s_real_backend->context,
		visit, visitor_context);
}

static int count_sink(void *context, uint32_t section_offset,
	const uint8_t *bytes, size_t size)
{
	(void)section_offset; (void)bytes;
	*(size_t *)context += size;
	return 1;
}

static int read_tags(hcu_profile_mount *mount, int validate)
{
	struct cache_file_header cache_header;
	boolean complete = FALSE;
	test_tag_header *tag_header;
	unsigned long claims_size;
	void *claims;
	if (!cache_file_open(HCU_PROFILE_MOUNT_TEST_MAP_NAME, &cache_header) ||
		cache_header.tag_data_offset != mount->source_identity_snapshot.tag_data_offset ||
		cache_header.file_length != mount->source_identity_snapshot.file_length)
		return 0;
	if (cache_file_read(NONE, cache_header.tag_data_offset,
		cache_header.tag_data_size, s_tag_cache, &complete, TRUE) != NONE || complete != TRUE)
		return 0;
	tag_header = (test_tag_header *)s_tag_cache;
	if (tag_header->signature != 0x74616773u || tag_header->tag_count <= 0)
		return 0;
	if (validate) {
		claims_size = tag_validate_claims_buffer_size();
		claims = malloc(claims_size);
		if (!claims || !claims_size || !tag_validate_bind_claims_buffer(claims, claims_size)) {
			free(claims); return 0;
		}
		if (!tag_validate_tags(tag_header, cache_header.tag_data_size,
			cache_header.file_length, HCU_PROFILE_MOUNT_TEST_MAP_NAME)) {
			tag_validate_release_claims_buffer(); free(claims); return 0;
		}
		tag_validate_release_claims_buffer();
		free(claims);
	}
	(void)mount;
	return 1;
}

static int read_bsp(void)
{
	boolean complete = FALSE;
	if (cache_file_read(NONE, HCU_PROFILE_MOUNT_TEST_BSP_OFFSET,
		HCU_PROFILE_MOUNT_TEST_BSP_SIZE, s_bsp_cache, &complete, TRUE) != NONE ||
		complete != TRUE || memcmp(s_bsp_cache + 20, "psbs", 4) != 0)
		return 0;
	return 1;
}

int main(int argc, char **argv)
{
	hcu_asset_profile_view profile;
	const hcu_map_catalog_entry *catalog;
	hcu_profile_mount mount;
	hcu_profile_cbsp_binding bindings[HCU_PROFILE_MOUNT_TEST_CBSP_COUNT];
	hcu_profile_resource_range resources[HCU_PROFILE_MOUNT_TEST_RESOURCE_COUNT];
	const ctag_mount_backend *backend;
	hcu_asset_chunk_view media_chunk;
	uint8_t original;
	long map_length;
	uint32_t first_resource_offset, first_resource_size, first_resource_datum;
	unsigned cycle;
	int status;
	if (argc != 3) return 2;
	atexit(restore_pending_flip);
	s_package_file = fopen(argv[1], "r+b");
	s_map_file = fopen(argv[2], "rb");
	if (!s_package_file || !s_map_file || !set_profile_file_size(s_package_file)) return 3;
	catalog = hcu_map_catalog_find(HCU_PROFILE_MOUNT_TEST_MAP_NAME);
	s_real_backend = ctag_ps2_cache_backend();
	s_wrapped_backend = *s_real_backend;
	s_wrapped_backend.register_ctag_visitor = wrap_register_ctag_visitor;
	s_wrapped_backend.register_bsp_visitor = wrap_register_bsp_visitor;
	backend = &s_wrapped_backend;
	if (!catalog || !backend || fseek(s_map_file, 0, SEEK_END) != 0 ||
		(map_length = ftell(s_map_file)) < 0 ||
		(uint32_t)map_length != catalog->identity.file_length ||
		fseek(s_map_file, 0, SEEK_SET) != 0 ||
		hcu_asset_profile_preflight_reader(profile_read_at, s_package_file,
			s_package_size, HCU_PROFILE_MOUNT_TEST_PROFILE_ID, &profile) != HCU_ASSET_PROFILE_OK)
		return 4;
	s_map_file_length = catalog->identity.file_length;
	memcpy(bindings, hcu_profile_mount_test_cbsp_bindings, sizeof(bindings));
	memcpy(resources, hcu_profile_mount_test_resource_ranges, sizeof(resources));
	if (hcu_asset_profile_lookup(&profile, HCU_ASSET_CHUNK_MEDIA,
		bindings[0].media_chunk_id, &media_chunk) != HCU_ASSET_PROFILE_OK)
		return 5;
	first_resource_offset = resources[0].source_offset;
	first_resource_size = resources[0].size;
	first_resource_datum = resources[0].output_datum;
	if (first_resource_size > sizeof(s_expected_resource))
		first_resource_size = sizeof(s_expected_resource);
	if (!source_read_exact(first_resource_offset, first_resource_size, s_expected_resource))
		return 6;

	for (cycle = 0; cycle < 3; ++cycle) {
		int with_reader = cycle != 1;
		hcu_profile_mount_init(&mount);
		if (hcu_profile_mount_bind_residency(&mount, s_residency_entries,
			RESIDENCY_SLOTS, s_residency_arena, sizeof(s_residency_arena)) != HCU_PROFILE_MOUNT_OK) return 7;
		status = hcu_profile_mount_prepare(&mount, &profile,
			HCU_PROFILE_MOUNT_TEST_PROFILE_ID, catalog, bindings,
			HCU_PROFILE_MOUNT_TEST_CBSP_COUNT, resources,
			HCU_PROFILE_MOUNT_TEST_RESOURCE_COUNT,
			with_reader ? source_read_at : NULL,
			with_reader ? s_map_file : NULL, backend, TAG_CACHE_BYTES,
			s_relocations, sizeof(s_relocations), s_stream_scratch,
			sizeof(s_stream_scratch));
		if (status != HCU_PROFILE_MOUNT_OK) {
			fprintf(stderr, "prepare cycle=%u status=%d\n", cycle, status); return 10;
		}
		if (cycle == 0) {
			/* Capacity boundary: the UI CTAG image size is read from the real
			 * CE chunk header. One byte below it must be rejected before any
			 * backend mount exists; exactly that size must be accepted. */
			hcu_profile_mount rejected;
			uint8_t image_bytes[4];
			uint32_t image_size;
			hcu_asset_chunk_view ce_view;
			if (hcu_asset_profile_lookup(&profile, HCU_ASSET_CHUNK_CE, 0, &ce_view) !=
				HCU_ASSET_PROFILE_OK || profile_read_at(s_package_file,
				ce_view.offset + 12u, image_bytes, 4) != 0) return 11;
			image_size = (uint32_t)image_bytes[0] | (uint32_t)image_bytes[1] << 8 |
				(uint32_t)image_bytes[2] << 16 | (uint32_t)image_bytes[3] << 24;
			if (image_size < 2u) return 11;
			hcu_profile_mount_init(&rejected);
			if (hcu_profile_mount_prepare(&rejected, &profile,
				HCU_PROFILE_MOUNT_TEST_PROFILE_ID, catalog, bindings,
				HCU_PROFILE_MOUNT_TEST_CBSP_COUNT, resources,
				HCU_PROFILE_MOUNT_TEST_RESOURCE_COUNT, source_read_at,
				s_map_file, backend, image_size - 1u,
				s_relocations, sizeof(s_relocations), s_stream_scratch,
				sizeof(s_stream_scratch)) != HCU_PROFILE_MOUNT_E_CAPACITY ||
				rejected.backend_mounted || rejected.prepared) return 11;
			hcu_profile_mount_init(&rejected);
			if (hcu_profile_mount_prepare(&rejected, &profile,
				HCU_PROFILE_MOUNT_TEST_PROFILE_ID, catalog, bindings,
				HCU_PROFILE_MOUNT_TEST_CBSP_COUNT, resources,
				HCU_PROFILE_MOUNT_TEST_RESOURCE_COUNT, source_read_at,
				s_map_file, backend, image_size,
				s_relocations, sizeof(s_relocations), s_stream_scratch,
				sizeof(s_stream_scratch)) != HCU_PROFILE_MOUNT_OK ||
				rejected.backend_mounted || !rejected.prepared) return 11;
		}
		if (cycle == 0) {
			/* Identity mismatch: a changed source-map pin or a foreign profile
			 * ID must be rejected before any backend state exists. */
			hcu_profile_cbsp_binding bad_bindings[HCU_PROFILE_MOUNT_TEST_CBSP_COUNT];
			hcu_profile_mount rejected;
			memcpy(bad_bindings, bindings, sizeof(bad_bindings));
			bad_bindings[0].source_map_sha256[0] ^= 0x01;
			hcu_profile_mount_init(&rejected);
			if (hcu_profile_mount_prepare(&rejected, &profile,
				HCU_PROFILE_MOUNT_TEST_PROFILE_ID, catalog, bad_bindings,
				HCU_PROFILE_MOUNT_TEST_CBSP_COUNT, resources,
				HCU_PROFILE_MOUNT_TEST_RESOURCE_COUNT, source_read_at,
				s_map_file, backend, TAG_CACHE_BYTES,
				s_relocations, sizeof(s_relocations), s_stream_scratch,
				sizeof(s_stream_scratch)) == HCU_PROFILE_MOUNT_OK ||
				rejected.prepared || rejected.backend_mounted) return 24;
			hcu_profile_mount_init(&rejected);
			if (hcu_profile_mount_prepare(&rejected, &profile,
				HCU_PROFILE_MOUNT_TEST_PROFILE_ID + 1u, catalog, bindings,
				HCU_PROFILE_MOUNT_TEST_CBSP_COUNT, resources,
				HCU_PROFILE_MOUNT_TEST_RESOURCE_COUNT, source_read_at,
				s_map_file, backend, TAG_CACHE_BYTES,
				s_relocations, sizeof(s_relocations), s_stream_scratch,
				sizeof(s_stream_scratch)) != HCU_PROFILE_MOUNT_E_ARGUMENT ||
				rejected.prepared || rejected.backend_mounted) return 25;
		}
		if (cycle == 0) {
			/* Forced post-mount failure: the CTAG backend mounts, then the CBSP
			 * visitor registration is refused. Load must unmount everything and
			 * leave the mount object and the CE cache in the empty state. */
			hcu_profile_mount forced;
			hcu_profile_mount_init(&forced);
			if (hcu_profile_mount_prepare(&forced, &profile,
				HCU_PROFILE_MOUNT_TEST_PROFILE_ID, catalog, bindings,
				HCU_PROFILE_MOUNT_TEST_CBSP_COUNT, resources,
				HCU_PROFILE_MOUNT_TEST_RESOURCE_COUNT, source_read_at,
				s_map_file, backend, TAG_CACHE_BYTES,
				s_relocations_other, sizeof(s_relocations_other),
				s_stream_scratch_other, sizeof(s_stream_scratch_other)) != HCU_PROFILE_MOUNT_OK)
				return 31;
			s_force_bsp_register_failure = 1;
			if (hcu_profile_mount_load(&forced) != HCU_PROFILE_MOUNT_E_BACKEND) return 32;
			s_force_bsp_register_failure = 0;
			if (forced.backend_mounted || forced.active || forced.callbacks_active) return 33;
			if (cache_file_open(HCU_PROFILE_MOUNT_TEST_MAP_NAME, &(struct cache_file_header){0})) return 34;
			/* The failed object stays prepared and must accept an exact retry. */
			if (!forced.prepared || hcu_profile_mount_load(&forced) != HCU_PROFILE_MOUNT_OK) return 35;
			if (hcu_profile_mount_unload(&forced) != HCU_PROFILE_MOUNT_OK) return 36;
		}
		if (hcu_profile_mount_load(&mount) != HCU_PROFILE_MOUNT_OK ||
			hcu_profile_mount_load(&mount) != HCU_PROFILE_MOUNT_E_STATE)
			return 12;
		if (cycle == 0) {
			/* HCP storage can change after map preflight; late visitor hash
			 * mismatch must leave CE completion false until exact retry. */
			if (!flip_byte(s_package_file, mount.ce_chunk.offset, &original)) return 13;
			/* Post-prepare corruption: the visitor must fail before the sink
			 * receives any byte, so nothing unverified reaches the CTAG cache. */
			{
				size_t sunk = 0, raw = 0;
				if (!s_ctag_visit || s_ctag_visit(s_ctag_visit_context,
					count_sink, &sunk, &raw) != 0 || sunk != 0 || raw != 0)
					return 30;
			}
			{
				struct cache_file_header h;
				boolean complete = TRUE;
				if (!cache_file_open(HCU_PROFILE_MOUNT_TEST_MAP_NAME, &h) ||
					cache_file_read(NONE, h.tag_data_offset, h.tag_data_size,
						s_tag_cache, &complete, TRUE) != NONE || complete != _cache_file_read_failed)
					return 14;
			}
			if (!restore_byte(s_package_file, mount.ce_chunk.offset, original) ||
				!read_tags(&mount, 1)) return 15;
			/* A corrupt CBSP chunk is rejected by the exact source-extent visitor. */
			if (!flip_byte(s_package_file, media_chunk.offset, &original)) return 16;
			{
				boolean complete = TRUE;
				if (cache_file_read(NONE, HCU_PROFILE_MOUNT_TEST_BSP_OFFSET,
					HCU_PROFILE_MOUNT_TEST_BSP_SIZE, s_bsp_cache,
					&complete, TRUE) != NONE || complete != _cache_file_read_failed) return 17;
			}
			if (!restore_byte(s_package_file, media_chunk.offset, original)) return 18;
		}
		if (cycle == 0) {
			/* A second mount object must not tear down or replace the live one. */
			hcu_profile_mount other;
			hcu_profile_mount_init(&other);
			if (hcu_profile_mount_prepare(&other, &profile,
				HCU_PROFILE_MOUNT_TEST_PROFILE_ID, catalog, bindings,
				HCU_PROFILE_MOUNT_TEST_CBSP_COUNT, resources,
				HCU_PROFILE_MOUNT_TEST_RESOURCE_COUNT, source_read_at,
				s_map_file, backend, TAG_CACHE_BYTES,
				s_relocations_other, sizeof(s_relocations_other),
				s_stream_scratch_other, sizeof(s_stream_scratch_other)) != HCU_PROFILE_MOUNT_OK)
				return 26;
			if (hcu_profile_mount_load(&other) != HCU_PROFILE_MOUNT_E_BACKEND ||
				other.backend_mounted || other.active) return 27;
			if (!read_tags(&mount, 1)) return 28;
			if (hcu_profile_mount_unload(&other) != HCU_PROFILE_MOUNT_OK) return 29;
		}
		if (!read_tags(&mount, cycle != 1) || !read_bsp()) return 19;
		if (with_reader) {
			boolean complete = FALSE;
			s_map_reads = 0;
			if (cache_file_read((long)first_resource_datum, first_resource_offset,
				first_resource_size, s_resource, &complete, TRUE) != NONE ||
				complete != TRUE || s_map_reads != 1 ||
				s_last_output_datum != (int32_t)first_resource_datum ||
				memcmp(s_resource, s_expected_resource, first_resource_size)) return 20;
			complete = TRUE;
			if (cache_file_read((long)(first_resource_datum + 1u), first_resource_offset,
				first_resource_size, s_resource, &complete, TRUE) != NONE ||
				complete != _cache_file_read_failed || s_map_reads != 1) return 21;
		} else {
			boolean complete = TRUE;
			if (cache_file_read((long)first_resource_datum, first_resource_offset,
				first_resource_size, s_resource, &complete, TRUE) != NONE ||
				complete != _cache_file_read_failed) return 22;
		}
		if (cycle == 0) {
			/* Residency gates: a lease or pin keeps the mount live and makes unload
			 * return busy with no teardown. Releasing them allows unload again. Then
			 * a gameplay-held segment evicts only after its reference is released. */
			void *released = NULL;
			uint32_t e, evictions0, refused0;
			/* Larger packages recycle staging slots during the walk, so make
			 * CE segment 0 resident in slot 0 before exercising the gates. */
			for (e = 0; e < mount.residency.count; ++e)
				if (mount.residency.entries[e].resident)
					(void)hcu_asset_residency_evict(&mount.residency,
						mount.residency.entries[e].type, mount.residency.entries[e].chunk_id,
						mount.residency.entries[e].segment, NULL);
			if (hcu_asset_residency_pin(&mount.residency, mount.profile, HCU_ASSET_CHUNK_CE, 0, 0,
				s_residency_arena, HCU_PROFILE_MOUNT_RESIDENCY_SEGMENT_BYTES) != HCU_ASSET_PROFILE_OK ||
				hcu_asset_residency_unpin(&mount.residency, HCU_ASSET_CHUNK_CE, 0, 0) != HCU_ASSET_PROFILE_OK) return 53;
			evictions0 = mount.residency.evictions; refused0 = mount.residency.refused_evictions;
			if (hcu_asset_residency_lease(&mount.residency, HCU_ASSET_CHUNK_CE, 0, 0) != HCU_ASSET_PROFILE_OK) return 40;
			if (hcu_profile_mount_unload(&mount) != HCU_PROFILE_MOUNT_E_BUSY ||
				!mount.active || !mount.backend_mounted || mount.residency.refused_evictions != refused0) return 41;
			if (!read_tags(&mount, 0)) return 42;
			if (hcu_asset_residency_release_lease(&mount.residency, HCU_ASSET_CHUNK_CE, 0, 0) != HCU_ASSET_PROFILE_OK) return 43;
			if (hcu_asset_residency_pin(&mount.residency, mount.profile, HCU_ASSET_CHUNK_CE, 0, 0, NULL, 0) != HCU_ASSET_PROFILE_OK) return 44;
			if (hcu_profile_mount_unload(&mount) != HCU_PROFILE_MOUNT_E_BUSY || !mount.backend_mounted) return 45;
			if (hcu_asset_residency_unpin(&mount.residency, HCU_ASSET_CHUNK_CE, 0, 0) != HCU_ASSET_PROFILE_OK) return 46;
			/* Model a gameplay pointer into this resident segment. */
			if (hcu_asset_residency_gameplay_ref(&mount.residency, HCU_ASSET_CHUNK_CE, 0, 0, 1) != HCU_ASSET_PROFILE_OK) return 52;
			if (hcu_asset_residency_evict(&mount.residency, HCU_ASSET_CHUNK_CE, 0, 0, &released) != HCU_ASSET_PROFILE_E_BUSY) return 47;
			if (hcu_asset_residency_gameplay_ref(&mount.residency, HCU_ASSET_CHUNK_CE, 0, 0, -1) != HCU_ASSET_PROFILE_OK) return 48;
			if (hcu_asset_residency_evict(&mount.residency, HCU_ASSET_CHUNK_CE, 0, 0, &released) != HCU_ASSET_PROFILE_OK ||
				released != (void *)s_residency_arena) return 49;
			if (!read_tags(&mount, 1)) return 50;
			if (mount.residency.evictions - evictions0 < 1u ||
				mount.residency.refused_evictions - refused0 != 1u) return 51;
		}
		/* Residency statistics of this cycle, kept as the maximum over cycles. */
		if (mount.residency.resident_high_water > s_residency_high_water)
			s_residency_high_water = mount.residency.resident_high_water;
		s_residency_refused_pins += mount.residency.refused_pins;
		s_residency_evictions += mount.residency.evictions;
		if (hcu_profile_mount_unload(&mount) != HCU_PROFILE_MOUNT_OK ||
			cache_file_open(HCU_PROFILE_MOUNT_TEST_MAP_NAME, &(struct cache_file_header){0})) return 23;
	}
	printf("RESIDENCY_STATS map=%s slots=%u segment_bytes=%u resident_high_water=%u refused_pins=%u evictions=%u\n",
		HCU_PROFILE_MOUNT_TEST_MAP_NAME, (unsigned)RESIDENCY_SLOTS,
		(unsigned)HCU_PROFILE_MOUNT_RESIDENCY_SEGMENT_BYTES, (unsigned)s_residency_high_water,
		(unsigned)s_residency_refused_pins, (unsigned)s_residency_evictions);
	fclose(s_package_file); fclose(s_map_file);
	printf("PROFILE_MOUNT_OK map=%s ctag=loaded+rebased+schema-validated cbsp=loaded+rebased resource=allowlisted missing-reader=denied late-corruption=fail-closed post-mount-failure=unmounted retry=passed identity-mismatch=rejected double-load=denied second-mount=denied residency=pinned+leases-gate-unload+evict-after-release cycles=3\\n", HCU_PROFILE_MOUNT_TEST_MAP_NAME);
	return 0;
}
