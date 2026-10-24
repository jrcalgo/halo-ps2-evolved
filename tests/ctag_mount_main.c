#define NEWLIB_PORT_AWARE
#include "stream/ctag_mount.h"
#include "stream/ctag_map_source.h"
#include "stream/ctag_ps2_backend.h"
#include "stream/hcu_map_service.h"
#include "cache/cache_files.h"
#include "core/mem.h"
#include "halo_ps2_cache.h"

#include <io_common.h>
#include <fileXio_rpc.h>

#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <stdarg.h>
#include <string.h>

#define TAG_CACHE_SIZE (2 * 1024 * 1024)
#define ARENA_SIZE (1572864u)
#define BSP_SCRATCH_SIZE (393216u)
#define SECTION_OUTPUT_SIZE 8192

struct cache_file_header
{
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

static uint8_t tag_cache[TAG_CACHE_SIZE] __attribute__((aligned(16)));
static uint8_t bsp_cache[TAG_CACHE_SIZE] __attribute__((aligned(16)));
static unsigned long tag_cache_capacity = TAG_CACHE_SIZE;
static unsigned long tag_cache_capacity_fault = TAG_CACHE_SIZE;
static int tag_cache_capacity_fault_after_queries = -1;
static int tag_cache_capacity_fault_query_count;
static uint8_t map_source[0x8000];
static ctag_map_source disk_map_source;
static uint8_t arena_memory[ARENA_SIZE] __attribute__((aligned(64)));
static uint8_t bsp_scratch_memory[BSP_SCRATCH_SIZE] __attribute__((aligned(64)));
static uint8_t section_output_memory[SECTION_OUTPUT_SIZE] __attribute__((aligned(64)));
static uint8_t section_scratch_memory[98304] __attribute__((aligned(64)));
static uint8_t service_section_scratch_memory[393216] __attribute__((aligned(64)));
static uint8_t outside_payload[76];
static const ctag_mount_backend *backend;
static arena_t map_arena;
static arena_t bsp_scratch_arena;
static arena_t section_output_arena;
static arena_t section_scratch_arena;
static ctag_mount active_mount;
static const char *map_pack_path;
static const char *resource_map_path;
#define FILEXIO_FAKE_HANDLES 16
static FILE *filexio_map_files[FILEXIO_FAKE_HANDLES];
static char filexio_map_paths[FILEXIO_FAKE_HANDLES][512];
static int filexio_open_count;
static int filexio_close_count;
/* -1 disables injection; a nonnegative count allows that many bytes through
 * FileXioRead before the fake device reports EOF while the file still has its
 * original length (the open/seek path has already succeeded). */
static int filexio_read_bytes_before_eof = -1;
static int filexio_injected_eof_count;
static int filexio_successful_read_calls;
static long filexio_corrupt_hp2_offset = -1;
static int filexio_corrupt_hp2_count;

typedef struct {
	const arena_t *map_arena_object;
	const arena_t *scratch_arena_object;
	void *map_base;
	size_t map_cap;
	size_t map_used;
	size_t map_high;
	void *scratch_base;
	size_t scratch_cap;
	size_t scratch_used;
	size_t scratch_high;
	int mount_active;
	const arena_t *mount_owner;
	size_t mount_mark;
	const ctag_mount_backend *mount_backend;
	void *mount_read_context;
	ctag_read_at_fn mount_source_read;
	const uint8_t *mount_payload;
	size_t mount_payload_size;
	const uint8_t *mount_resource_bytes;
	size_t mount_resource_size;
	const uint8_t *mount_catalog_bytes;
	size_t mount_catalog_size;
	uint32_t mount_catalog_count;
	int mount_bsp_active;
	int source_active;
	int source_descriptor;
	uint32_t source_size;
	uint64_t tag_cache_hash;
	uint64_t bsp_cache_hash;
	int preflight_ready;
	int reload_pending;
	const hcu_map_catalog_entry *staged_entry;
	char staged_map[sizeof(((hcu_map_service *)0)->staged_map)];
	int cache_loaded;
	int open_count;
	int close_count;
} map_service_snapshot;

static uint64_t snapshot_hash64(const uint8_t *bytes, size_t size)
{
	uint64_t hash = UINT64_C(1469598103934665603);
	size_t i;
	for (i = 0; i < size; ++i) {
		hash ^= bytes[i];
		hash *= UINT64_C(1099511628211);
	}
	return hash;
}

static uint32_t read_le32(const uint8_t *bytes)
{
	return (uint32_t)bytes[0] | ((uint32_t)bytes[1] << 8) |
		((uint32_t)bytes[2] << 16) | ((uint32_t)bytes[3] << 24);
}

/* Test-only mutation of a copied package: flip one selected section's first
 * payload byte without updating its CRC, then flip it back exactly. */
static int flip_hp2_section_payload_byte(const char *path, const char section_tag[4])
{
	uint8_t header[64], entry[32];
	uint16_t count;
	uint32_t payload_offset = 0;
	unsigned i;
	FILE *file = fopen(path, "r+b");
	if (!file) return 0;
	if (fread(header, 1, sizeof(header), file) != sizeof(header) ||
		memcmp(header, "HP2P", 4) != 0) {
		fclose(file); return 0;
	}
	count = (uint16_t)(header[6] | ((uint16_t)header[7] << 8));
	if (count > 64) { fclose(file); return 0; }
	for (i = 0; i < count; ++i) {
		if (fseek(file, (long)(64u + i * 32u), SEEK_SET) != 0 ||
			fread(entry, 1, sizeof(entry), file) != sizeof(entry)) {
			fclose(file); return 0;
		}
		if (memcmp(entry, section_tag, 4) == 0) {
			payload_offset = read_le32(entry + 4);
			break;
		}
	}
	if (!payload_offset || fseek(file, (long)payload_offset, SEEK_SET) != 0) {
		fclose(file); return 0;
	}
	{
		int value = fgetc(file);
		if (value == EOF || fseek(file, (long)payload_offset, SEEK_SET) != 0 ||
			fputc(value ^ 0x80, file) == EOF || fflush(file) != 0) {
			fclose(file); return 0;
		}
	}
	return fclose(file) == 0;
}

static map_service_snapshot capture_map_service_snapshot(
	const hcu_map_service *service)
{
	map_service_snapshot snapshot;
	memset(&snapshot, 0, sizeof(snapshot));
	snapshot.map_arena_object = service->map_arena;
	snapshot.scratch_arena_object = service->section_scratch;
	snapshot.map_base = service->map_arena->base;
	snapshot.map_cap = service->map_arena->cap;
	snapshot.map_used = service->map_arena->used;
	snapshot.map_high = service->map_arena->high;
	snapshot.scratch_base = service->section_scratch->base;
	snapshot.scratch_cap = service->section_scratch->cap;
	snapshot.scratch_used = service->section_scratch->used;
	snapshot.scratch_high = service->section_scratch->high;
	snapshot.mount_active = service->mount.active;
	snapshot.mount_owner = service->mount.owner;
	snapshot.mount_mark = service->mount.arena_mark;
	snapshot.mount_backend = service->mount.backend;
	snapshot.mount_read_context = service->mount.read_context;
	snapshot.mount_source_read = service->mount.source_read;
	snapshot.mount_payload = service->mount.payload;
	snapshot.mount_payload_size = service->mount.payload_size;
	snapshot.mount_resource_bytes = service->mount.resource_index_bytes;
	snapshot.mount_resource_size = service->mount.resource_index_size;
	snapshot.mount_catalog_bytes = service->mount.bsp_catalog.bytes;
	snapshot.mount_catalog_size = service->mount.bsp_catalog.size;
	snapshot.mount_catalog_count = service->mount.bsp_catalog.count;
	snapshot.mount_bsp_active = service->mount.bsp_active;
	snapshot.source_active = service->source.active;
	snapshot.source_descriptor = service->source.reader.descriptor;
	snapshot.source_size = service->source.reader.size;
	snapshot.preflight_ready = service->preflight_ready;
	snapshot.reload_pending = service->reload_pending;
	snapshot.staged_entry = service->staged_entry;
	memcpy(snapshot.staged_map, service->staged_map,
		sizeof(snapshot.staged_map));
	snapshot.cache_loaded = cache_files_precache_map_loaded("ui");
	snapshot.open_count = filexio_open_count;
	snapshot.close_count = filexio_close_count;
	snapshot.tag_cache_hash = snapshot_hash64(tag_cache, sizeof(tag_cache));
	snapshot.bsp_cache_hash = snapshot_hash64(bsp_cache, sizeof(bsp_cache));
	return snapshot;
}

static void assert_mounted_service_preserved_snapshot(
	const hcu_map_service *service, const map_service_snapshot *before)
{
	map_service_snapshot after = capture_map_service_snapshot(service);
	assert(after.map_arena_object == before->map_arena_object &&
		after.scratch_arena_object == before->scratch_arena_object);
	assert(after.map_base == before->map_base && after.map_cap == before->map_cap &&
		after.map_used == before->map_used && after.map_high == before->map_high);
	assert(after.scratch_base == before->scratch_base &&
		after.scratch_cap == before->scratch_cap &&
		after.scratch_used == before->scratch_used &&
		after.scratch_high == before->scratch_high);
	assert(after.mount_active && before->mount_active);
	assert(after.mount_owner == before->mount_owner &&
		after.mount_mark == before->mount_mark &&
		after.mount_backend == before->mount_backend &&
		after.mount_read_context == before->mount_read_context &&
		after.mount_source_read == before->mount_source_read &&
		after.mount_payload == before->mount_payload &&
		after.mount_payload_size == before->mount_payload_size &&
		after.mount_resource_bytes == before->mount_resource_bytes &&
		after.mount_resource_size == before->mount_resource_size &&
		after.mount_catalog_bytes == before->mount_catalog_bytes &&
		after.mount_catalog_size == before->mount_catalog_size &&
		after.mount_catalog_count == before->mount_catalog_count &&
		after.mount_bsp_active == before->mount_bsp_active);
	assert(after.source_active == before->source_active &&
		after.source_descriptor == before->source_descriptor &&
		after.source_size == before->source_size);
	assert(after.preflight_ready == before->preflight_ready &&
		after.reload_pending == before->reload_pending &&
		after.staged_entry == before->staged_entry &&
		memcmp(after.staged_map, before->staged_map, sizeof(after.staged_map)) == 0);
	assert(after.cache_loaded == before->cache_loaded && after.cache_loaded);
	assert(after.open_count == before->open_count &&
		after.close_count == before->close_count);
	assert(after.tag_cache_hash == before->tag_cache_hash &&
		after.bsp_cache_hash == before->bsp_cache_hash);
}

static void assert_failed_preflight_snapshot(
	const hcu_map_service *service, const map_service_snapshot *before)
{
	map_service_snapshot after = capture_map_service_snapshot(service);
	assert(after.map_base == before->map_base &&
		after.map_cap == before->map_cap && after.map_used == before->map_used);
	assert(after.scratch_base == before->scratch_base &&
		after.scratch_cap == before->scratch_cap &&
		after.scratch_used == before->scratch_used);
	/* high-water is monotonic evidence; a failed validation may legitimately
	 * raise it, but neither arena may exceed its fixed capacity. */
	assert(after.map_high >= before->map_high && after.map_high <= after.map_cap);
	assert(after.scratch_high >= before->scratch_high &&
		after.scratch_high <= after.scratch_cap);
	assert(!after.mount_active && !after.source_active &&
		after.source_descriptor == -1 && !after.preflight_ready &&
		!after.reload_pending && after.staged_entry == NULL &&
		after.staged_map[0] == 0 && !after.cache_loaded);
	assert(after.open_count == after.close_count);
}

static FILE *filexio_get_file(int descriptor)
{
	int slot = descriptor - 7;
	return slot >= 0 && slot < FILEXIO_FAKE_HANDLES ? filexio_map_files[slot] : NULL;
}

/* Exercise the production direct-FileXio branch without requiring an IOP.
 * The fake maps its descriptor operations to one host FILE. */
int fileXioInit(void)
{
	return 0;
}

int fileXioOpen(const char *path, int flags, ...)
{
	va_list args;
	int mode, slot;
	va_start(args, flags);
	mode = va_arg(args, int);
	va_end(args);
	assert(flags == FIO_O_RDONLY && mode == 0);
	for (slot = 0; slot < FILEXIO_FAKE_HANDLES; slot++)
		if (!filexio_map_files[slot]) break;
	if (slot == FILEXIO_FAKE_HANDLES) return -1;
	filexio_map_files[slot] = fopen(path, "rb");
	if (!filexio_map_files[slot]) return -1;
	strncpy(filexio_map_paths[slot], path,
		sizeof(filexio_map_paths[slot]) - 1u);
	filexio_map_paths[slot][sizeof(filexio_map_paths[slot]) - 1u] = 0;
	filexio_open_count++;
	return slot + 7;
}

int fileXioClose(int descriptor)
{
	FILE *file = filexio_get_file(descriptor);
	assert(file != NULL);
	assert(fclose(file) == 0);
	filexio_map_files[descriptor - 7] = NULL;
	filexio_map_paths[descriptor - 7][0] = 0;
	filexio_close_count++;
	return 0;
}

int fileXioRead(int descriptor, void *buffer, int size)
{
	size_t count;
	long offset;
	FILE *file = filexio_get_file(descriptor);
	assert(file != NULL && size >= 0);
	if (filexio_read_bytes_before_eof == 0) {
		filexio_read_bytes_before_eof = -1;
		filexio_injected_eof_count++;
		return 0;
	}
	if (filexio_read_bytes_before_eof > 0 &&
		(size_t)size > (size_t)filexio_read_bytes_before_eof)
		size = filexio_read_bytes_before_eof;
	offset = ftell(file);
	count = fread(buffer, 1, (size_t)size, file);
	if (count && filexio_corrupt_hp2_offset >= offset &&
		filexio_corrupt_hp2_offset - offset < (long)count &&
		strstr(filexio_map_paths[descriptor - 7], ".hp2") != NULL) {
		((uint8_t *)buffer)[filexio_corrupt_hp2_offset - offset] ^= 1u;
		filexio_corrupt_hp2_offset = -1;
		filexio_corrupt_hp2_count++;
	}
	if (count) filexio_successful_read_calls++;
	if (filexio_read_bytes_before_eof > 0)
		filexio_read_bytes_before_eof -= (int)count;
	if (!count && ferror(file)) return -1;
	return (int)count;
}

int fileXioLseek(int descriptor, int offset, int whence)
{
	int host_whence;
	long position;
	FILE *file = filexio_get_file(descriptor);
	assert(file != NULL);
	if (whence == FIO_SEEK_SET) host_whence = SEEK_SET;
	else if (whence == FIO_SEEK_CUR) host_whence = SEEK_CUR;
	else if (whence == FIO_SEEK_END) host_whence = SEEK_END;
	else return -1;
	if (fseek(file, offset, host_whence) != 0) return -1;
	position = ftell(file);
	return position < 0 || position > INT32_MAX ? -1 : (int)position;
}

int fileXioGetStat(const char *path, iox_stat_t *info)
{
	(void)path;
	(void)info;
	return -1;
}

void *physical_memory_get_tag_cache_base_address(void) { return tag_cache; }
unsigned long physical_memory_get_tag_cache_size(void)
{
	unsigned long capacity = tag_cache_capacity;
	if (tag_cache_capacity_fault_after_queries >= 0) {
		if (tag_cache_capacity_fault_query_count >=
			tag_cache_capacity_fault_after_queries)
			capacity = tag_cache_capacity_fault;
		tag_cache_capacity_fault_query_count++;
	}
	return capacity;
}
void *physical_memory_get_structure_bsp_cache_base_address(void) { return bsp_cache; }
unsigned long physical_memory_get_structure_bsp_cache_size(void) { return sizeof bsp_cache; }

extern uint8_t *world_load_section_with_scratch(arena_t *owner,
	arena_t *scratch, const char *pack_path, const char *tag,
	size_t *raw_size, int optional);

static uint8_t *load_section(void *context, arena_t *owner,
	const char *pack_path, const char *tag, size_t *raw_size, int optional)
{
	return world_load_section_with_scratch(owner, (arena_t *)context,
		pack_path, tag, raw_size, optional);
}

static uint8_t *load_outside(void *context, arena_t *owner,
	const char *pack_path, const char *tag, size_t *raw_size, int optional)
{
	(void)context; (void)owner; (void)pack_path; (void)tag; (void)optional;
	*raw_size = sizeof(outside_payload);
	return outside_payload;
}

static uint8_t *load_preexisting(void *context, arena_t *owner,
	const char *pack_path, const char *tag, size_t *raw_size, int optional)
{
	(void)context; (void)pack_path; (void)tag; (void)optional;
	*raw_size = 16;
	return owner->base;
}

static int reject_backend_mount(void *context, const char *map_name,
	const uint8_t *payload, size_t payload_size, uint32_t tag_data_offset,
	uint32_t file_length, ctag_read_at_fn read_at, void *read_context)
{
	int *calls = (int *)context;
	(void)map_name;
	(void)payload;
	(void)payload_size;
	(void)tag_data_offset;
	(void)file_length;
	(void)read_at;
	(void)read_context;
	(*calls)++;
	return 0;
}

static int reject_bsp_loader_registration(void *context,
	ctag_bsp_load_fn load, ctag_bsp_release_fn release, void *loader_context)
{
	int *calls = (int *)context;
	(void)load; (void)release; (void)loader_context;
	++*calls;
	return 0;
}

static int parent_map_loader(void *context, const char *map_name)
{
	(void)context;
	if (strcmp(map_name, "ui") != 0) return 0;
	return ctag_mount_hp2_file_verified_discover_with_bsp_catalog(
		&active_mount, &map_arena, &bsp_scratch_arena, map_pack_path,
		map_name, resource_map_path, &disk_map_source, backend, load_section,
		context) == 0;
}

static int run_retail_ui_mount(const char *pack_path,
	const char *resource_map_path_arg)
{
	static const uint8_t expected_source_sha256[32] = {
		0x85, 0x56, 0xb6, 0x47, 0xb8, 0x27, 0x42, 0xd0,
		0x72, 0x82, 0xfe, 0x4e, 0x6d, 0xb0, 0xcf, 0x84,
		0x7b, 0x54, 0x2c, 0x04, 0x64, 0x84, 0xe9, 0x1e,
		0x71, 0xec, 0x31, 0xfe, 0xa5, 0xf5, 0xfd, 0x7e
	};
	static uint8_t source_hash_scratch[32768];
	struct cache_file_header header;
	boolean complete = FALSE;
	uint8_t *tag_cache_base = tag_cache;
	uint8_t resource[32], expected_resource[32];
	uint32_t resource_offset, resource_bytes;
	size_t baseline;
	int mount_status;
	backend = ctag_ps2_cache_backend();
	assert(backend != NULL);
	assert(file_reader_filexio_init() == 0);
	tag_cache_capacity = TAG_CACHE_SIZE;
	map_pack_path = pack_path;
	resource_map_path = resource_map_path_arg;
	arena_init(&map_arena, "retail UI streaming", arena_memory,
		sizeof(arena_memory));
	arena_init(&bsp_scratch_arena, "retail UI section scratch",
		bsp_scratch_memory, sizeof(bsp_scratch_memory));
	ctag_mount_init(&active_mount);
	baseline = map_arena.used;
	mount_status = ctag_mount_hp2_file_verified_discover_with_bsp_catalog(
		&active_mount, &map_arena, &bsp_scratch_arena, pack_path, "ui",
		resource_map_path_arg, &disk_map_source, backend, load_section,
		&bsp_scratch_arena);
	if (mount_status != 0)
		fprintf(stderr, "retail UI BSP-catalog mount failed: %d\n", mount_status);
	assert(mount_status == 0);
	assert(active_mount.active && disk_map_source.active);
	assert(active_mount.resource_index.tag_data_offset == 31939584u);
	assert(active_mount.resource_index.tag_data_size == 1642244u);
	assert(active_mount.resource_index.file_length == 33582080u);
	assert(active_mount.bsp_catalog.count == 1u);
	assert(ctag_map_source_matches_sha256_with_buffer(&disk_map_source,
		expected_source_sha256, source_hash_scratch,
		sizeof(source_hash_scratch)));
	assert(map_arena.high == 1550444u);
	assert(bsp_scratch_arena.high <= bsp_scratch_arena.cap);
	assert(cache_file_open("ui", &header));
	assert(header.tag_data_offset == 31939584);
	assert(header.tag_data_size == 1510628);
	assert(cache_file_read(NONE, header.tag_data_offset, header.tag_data_size,
		tag_cache_base, &complete, TRUE) == NONE);
	assert(complete == TRUE);
	{
		static const uint8_t tag_signature[4] = { 0x73, 0x67, 0x61, 0x74 };
		assert(memcmp(tag_cache_base + 32, tag_signature,
			sizeof(tag_signature)) == 0);
	}
	assert(active_mount.resource_index.interval_count > 0);
	{
		const uint8_t *first = active_mount.resource_index.bytes + 36;
		resource_offset = (uint32_t)first[0] |
			(uint32_t)first[1] << 8 | (uint32_t)first[2] << 16 |
			(uint32_t)first[3] << 24;
		resource_bytes = (uint32_t)first[4] |
			(uint32_t)first[5] << 8 | (uint32_t)first[6] << 16 |
			(uint32_t)first[7] << 24;
	}
	if (resource_bytes > sizeof(resource)) resource_bytes = sizeof(resource);
	assert(resource_bytes > 0);
	assert(ctag_map_source_read(&disk_map_source, 0, resource_offset,
		resource_bytes, expected_resource, 1));
	complete = FALSE;
	assert(cache_file_read(0, resource_offset, resource_bytes, resource,
		&complete, TRUE) == NONE);
	assert(complete == TRUE && memcmp(resource, expected_resource,
		resource_bytes) == 0);
	complete = FALSE;
	assert(cache_file_read(NONE, 2048, 2048, bsp_cache,
		&complete, TRUE) == NONE);
	assert(complete == TRUE && memcmp(bsp_cache + 20, "psbs", 4) == 0);
	assert(bsp_scratch_arena.used == 0);
	printf("retail-ui mounted: CTAG=%u streaming=%zu/%zu scratch_high=%zu/%zu\n",
		(unsigned)header.tag_data_size, map_arena.high, map_arena.cap,
		bsp_scratch_arena.high, bsp_scratch_arena.cap);
	ctag_mount_unload(&active_mount);
	assert(!disk_map_source.active && map_arena.used == baseline);
	return 0;
}

static int verify_retail_ui_source(const char *path)
{
	static const uint8_t expected[32] = {
		0x85, 0x56, 0xb6, 0x47, 0xb8, 0x27, 0x42, 0xd0,
		0x72, 0x82, 0xfe, 0x4e, 0x6d, 0xb0, 0xcf, 0x84,
		0x7b, 0x54, 0x2c, 0x04, 0x64, 0x84, 0xe9, 0x1e,
		0x71, 0xec, 0x31, 0xfe, 0xa5, 0xf5, 0xfd, 0x7e
	};
	ctag_map_source source;
	int matches;
	if (file_reader_filexio_init() != 0 ||
		ctag_map_source_open_any(&source, path) != 0)
		return 4;
	matches = ctag_map_source_matches_sha256(&source, expected);
	ctag_map_source_close(&source);
	return matches ? 0 : 5;
}

/* Exercise real service rollback when the source or its HP2 partner is absent.
 * These failures happen before map publication and must leave a reusable,
 * empty owner; the caller may correct the asset root and retry. */
static int run_retail_ui_service_open_failure(const char *asset_root)
{
	mem_layout_v2_t layout;
	arena_t map_arena, section_scratch;
	hcu_map_service service;
	map_service_snapshot before;
	assert(file_reader_filexio_init() == 0);
	memset(&layout, 0, sizeof(layout));
	arena_init(&map_arena, "missing asset streaming", arena_memory,
		sizeof(arena_memory));
	arena_init(&section_scratch, "missing asset scratch",
		service_section_scratch_memory, sizeof(service_section_scratch_memory));
	layout.regions[MEM_LAYOUT_V2_STREAMING] = map_arena;
	layout.regions[MEM_LAYOUT_V2_FRAME_SCRATCH] = section_scratch;
	tag_cache_capacity = TAG_CACHE_SIZE;
	assert(hcu_map_service_init(&service, &layout, asset_root) == 0);
	before = capture_map_service_snapshot(&service);
	assert(!ps2_cache_preflight_map("levels\\ui\\ui"));
	assert_failed_preflight_snapshot(&service, &before);
	hcu_map_service_shutdown(&service);
	puts("retail-ui service: missing source/package failed closed without owner publication");
	return 0;
}

/* File size and open/seek are valid, then return a short HP2 header/table
 * read followed by EOF. This distinguishes
 * transport truncation from a short file whose stat/seek length differs. */
static int run_retail_ui_service_short_read(const char *asset_root)
{
	mem_layout_v2_t layout;
	arena_t map_arena, section_scratch;
	hcu_map_service service;
	map_service_snapshot before;
	assert(file_reader_filexio_init() == 0);
	memset(&layout, 0, sizeof(layout));
	arena_init(&map_arena, "short-read streaming", arena_memory,
		sizeof(arena_memory));
	arena_init(&section_scratch, "short-read scratch",
		service_section_scratch_memory, sizeof(service_section_scratch_memory));
	layout.regions[MEM_LAYOUT_V2_STREAMING] = map_arena;
	layout.regions[MEM_LAYOUT_V2_FRAME_SCRATCH] = section_scratch;
	tag_cache_capacity = TAG_CACHE_SIZE;
	assert(hcu_map_service_init(&service, &layout, asset_root) == 0);
	before = capture_map_service_snapshot(&service);
	filexio_read_bytes_before_eof = 1;
	filexio_injected_eof_count = 0;
	filexio_successful_read_calls = 0;
	assert(!ps2_cache_preflight_map("levels\\ui\\ui"));
	assert(filexio_injected_eof_count == 1);
	assert(filexio_read_bytes_before_eof == -1);
	assert(filexio_successful_read_calls > 0);
	assert_failed_preflight_snapshot(&service, &before);
	hcu_map_service_shutdown(&service);
	puts("retail-ui service: HP2 header short-read EOF failed closed after valid open/seek");
	return 0;
}

static long find_hp2_section_crc_offset(const char *path, const char *tag)
{
	uint8_t header[64 + 32 * 64];
	FILE *file = fopen(path, "rb");
	uint16_t count;
	unsigned index;
	long result = -1;
	assert(file != NULL);
	assert(fread(header, 1, sizeof(header), file) == sizeof(header));
	assert(fclose(file) == 0);
	count = (uint16_t)(header[6] | (uint16_t)header[7] << 8);
	assert(count <= 64);
	for (index = 0; index < count; index++) {
		size_t entry = 64u + (size_t)index * 32u;
		if (memcmp(header + entry, tag, 4) == 0) {
			result = (long)(entry + 20u);
			break;
		}
	}
	return result;
}

static int run_retail_ui_service(const char *asset_root, int reject_package,
	int late_bsp_crc_failure)
{
	mem_layout_v2_t layout;
	arena_t map_arena, section_scratch;
	hcu_map_service service;
	struct cache_file_header header;
	boolean complete = FALSE;
	char hp2_path[512];
	size_t streaming_high;
	size_t streaming_used;
	size_t catalog_index;
	assert(file_reader_filexio_init() == 0);
	memset(&layout, 0, sizeof(layout));
	arena_init(&map_arena, "service streaming", arena_memory,
		sizeof(arena_memory));
	arena_init(&section_scratch, "service section scratch",
		service_section_scratch_memory, sizeof(service_section_scratch_memory));
	layout.regions[MEM_LAYOUT_V2_STREAMING] = map_arena;
	layout.regions[MEM_LAYOUT_V2_FRAME_SCRATCH] = section_scratch;
	tag_cache_capacity = TAG_CACHE_SIZE;
	assert(hcu_map_service_init(&service, &layout, asset_root) == 0);
	assert(snprintf(hp2_path, sizeof(hp2_path), "%smaps/ui.hp2",
		asset_root) > 0);
	if (reject_package) {
		assert(!ps2_cache_preflight_map("levels\\ui\\ui"));
		assert(!service.preflight_ready && !service.mount.active &&
			!service.source.active && service.map_arena->used == 0 &&
			section_scratch.used == 0);
		hcu_map_service_shutdown(&service);
		assert(filexio_open_count == filexio_close_count);
		puts("retail-ui service: corrupt package rejected before publication");
		return 0;
	}
	/* The owner must reject absent/corrupt data before CE begins publication. */
	assert(!ps2_cache_preflight_map("levels\\b30\\b30"));
	assert(ps2_cache_preflight_map("levels\\ui\\ui"));
	/* The cache adapter may call the loader without repeating preflight. A
	 * stale UI preflight must not let a different scenario mount the UI package. */
	assert(!cache_files_precache_map_begin("levels\\b30\\b30", TRUE));
	assert(!service.mount.active && service.preflight_ready &&
		service.staged_entry != NULL);
	assert(cache_files_precache_map_begin("levels\\ui\\ui", TRUE));
	assert(cache_files_precache_map_loaded("ui"));
	hcu_map_service_lifecycle_trace("owner-start", 0);
	assert(cache_file_open("ui", &header));
	assert(header.tag_data_size == 1510628);
	assert(cache_file_read(NONE, header.tag_data_offset, header.tag_data_size,
		tag_cache, &complete, TRUE) == NONE && complete == TRUE);
	memset(bsp_cache, 0xA5, sizeof(bsp_cache));
	complete = FALSE;
	assert(cache_file_read(NONE, 2048, 2048, bsp_cache,
		&complete, TRUE) == NONE && complete == TRUE);
	assert(memcmp(bsp_cache + 20, "psbs", 4) == 0);
	assert(section_scratch.used == 0);
	/* Inject transport EOF while the production BSP callback decodes its CBSP
	 * section. The candidate must not become an active BSP lease or overwrite
	 * the fixed destination; retry the same request in-process afterward. */
	{
		uint64_t bsp_before = snapshot_hash64(bsp_cache, sizeof(bsp_cache));
		int opens_before = filexio_open_count;
		int closes_before = filexio_close_count;
		filexio_read_bytes_before_eof = 1;
		filexio_injected_eof_count = 0;
		filexio_successful_read_calls = 0;
		complete = TRUE;
		assert(cache_file_read(NONE, 2048, 2048, bsp_cache,
			&complete, TRUE) == NONE);
		assert(complete != TRUE && filexio_injected_eof_count == 1 &&
			filexio_successful_read_calls > 0);
		assert(!service.mount.bsp_active && section_scratch.used == 0 &&
			service.mount.active && service.source.active &&
			cache_files_precache_map_loaded("ui"));
		assert(snapshot_hash64(bsp_cache, sizeof(bsp_cache)) == bsp_before);
		assert(filexio_open_count == opens_before + 1 &&
			filexio_close_count == closes_before + 1);
		filexio_read_bytes_before_eof = -1;
		complete = FALSE;
		assert(cache_file_read(NONE, 2048, 2048, bsp_cache,
			&complete, TRUE) == NONE && complete == TRUE);
		assert(memcmp(bsp_cache + 20, "psbs", 4) == 0 &&
			!service.mount.bsp_active && section_scratch.used == 0);
		puts("retail-ui service: BSP CBSP EOF preserved destination; retry passed");
	}
	if (late_bsp_crc_failure) {
		uint64_t good_hash = snapshot_hash64(bsp_cache, sizeof(bsp_cache));
		uint64_t failed_hash;
		int opens_before = filexio_open_count;
		int closes_before = filexio_close_count;
		long crc_offset = find_hp2_section_crc_offset(hp2_path, "B000");
		assert(crc_offset >= 0);
		memset(bsp_cache, 0xA5, sizeof(bsp_cache));
		failed_hash = snapshot_hash64(bsp_cache, sizeof(bsp_cache));
		filexio_corrupt_hp2_offset = crc_offset;
		complete = TRUE;
		assert(cache_file_read(NONE, 2048, 2048, bsp_cache,
			&complete, TRUE) == NONE);
		assert(filexio_corrupt_hp2_offset == -1 &&
			filexio_corrupt_hp2_count == 1 && complete != TRUE);
		assert(snapshot_hash64(bsp_cache, sizeof(bsp_cache)) != failed_hash);
		assert(!service.mount.bsp_active && section_scratch.used == 0 &&
			service.mount.active && service.source.active &&
			cache_files_precache_map_loaded("ui"));
		assert(filexio_open_count == opens_before + 1 &&
			filexio_close_count == closes_before + 1);
		complete = FALSE;
		assert(cache_file_read(NONE, 2048, 2048, bsp_cache,
			&complete, TRUE) == NONE && complete == TRUE);
		assert(snapshot_hash64(bsp_cache, sizeof(bsp_cache)) == good_hash &&
			!service.mount.bsp_active && section_scratch.used == 0);
		puts("retail-ui service: late CBSP section-CRC failure stayed unpublished; exact retry passed");
	}
	/* Force a FileXio transport EOF after one byte of an authorized CRNG
	 * resource has been copied into the caller's candidate buffer. The cache
	 * API's completion flag must remain false, the mounted owner/source must
	 * remain usable, and an immediate exact retry must succeed. */
	{
		uint8_t resource[32], expected_resource[32];
		const uint8_t *first = service.mount.resource_index.bytes + 36;
		uint32_t resource_offset = (uint32_t)first[0] |
			(uint32_t)first[1] << 8 | (uint32_t)first[2] << 16 |
			(uint32_t)first[3] << 24;
		uint32_t resource_size = (uint32_t)first[4] |
			(uint32_t)first[5] << 8 | (uint32_t)first[6] << 16 |
			(uint32_t)first[7] << 24;
		map_service_snapshot before = capture_map_service_snapshot(&service);
		if (resource_size > sizeof(resource)) resource_size = sizeof(resource);
		assert(resource_size > 1 && ctag_map_source_read(&service.source, 0,
			resource_offset, resource_size, expected_resource, 1));
		memset(resource, 0xA5, sizeof(resource));
		filexio_read_bytes_before_eof = 1;
		filexio_injected_eof_count = 0;
		filexio_successful_read_calls = 0;
		complete = TRUE;
		assert(cache_file_read(0, resource_offset, resource_size, resource,
			&complete, TRUE) == NONE);
		assert(complete != TRUE && filexio_injected_eof_count == 1 &&
			filexio_successful_read_calls > 0);
		assert(service.mount.active && service.source.active &&
			service.source.reader.descriptor == before.source_descriptor &&
			service.map_arena->used == before.map_used &&
			section_scratch.used == before.scratch_used &&
			cache_files_precache_map_loaded("ui"));
		assert(filexio_open_count == before.open_count &&
			filexio_close_count == before.close_count);
		filexio_read_bytes_before_eof = -1;
		complete = FALSE;
		assert(cache_file_read(0, resource_offset, resource_size, resource,
			&complete, TRUE) == NONE);
		assert(complete == TRUE && memcmp(resource, expected_resource,
			resource_size) == 0);
		puts("retail-ui service: authorized resource EOF left completion false; retry passed");
	}
	streaming_high = service.map_arena->high;
	streaming_used = service.map_arena->used;
	assert(streaming_high <= service.map_arena->cap);
	/* Every non-UI catalog entry remains fail-closed until its map-specific
	 * resident/BSP peak is qualified. Reject all entries before disturbing
	 * the currently published UI state or opening another source file. */
	{
		int opens_before = filexio_open_count;
		int closes_before = filexio_close_count;
		map_service_snapshot old_state = capture_map_service_snapshot(&service);
		for (catalog_index = 0;
			catalog_index < hcu_map_catalog_count(); catalog_index++) {
			const hcu_map_catalog_entry *entry =
				hcu_map_catalog_at(catalog_index);
			if (strcmp(entry->identity.map_name, "ui") == 0) continue;
			assert(!ps2_cache_preflight_map(entry->scenario_name));
			assert(service.mount.active &&
				cache_files_precache_map_loaded("ui"));
			assert(service.map_arena->used == streaming_used);
			assert(!service.preflight_ready && service.source.active);
			assert_mounted_service_preserved_snapshot(&service, &old_state);
		}
		assert(filexio_open_count == opens_before);
		assert(filexio_close_count == closes_before);
	}
	printf("retail-ui service: streaming=%zu/%zu preflight=verified\n",
		streaming_high, service.map_arena->cap);
	/* CE preflights the next map before game_unload(). The service must permit
	 * only this exact same-map transition without allocating over the live
	 * owner's bytes; the old scenario then unpublishes before owner release. */
	{
		int opens_before = filexio_open_count;
		int closes_before = filexio_close_count;
		assert(ps2_cache_preflight_map("levels\\ui\\ui"));
		assert(service.reload_pending && !service.preflight_ready &&
			service.mount.active && service.source.active &&
			service.map_arena->used == streaming_used);
		assert(filexio_open_count == opens_before &&
			filexio_close_count == closes_before);
	}
	/* Match scenario_unload's post-unpublication owner release callback. The
	 * pending identity survives only this release so map_loader can rerun all
	 * file/hash/section validation against the now-empty arena. */
	assert(ps2_cache_release_map_owner());
	hcu_map_service_lifecycle_trace("owner-released", 1);
	assert(service.map_arena->used == 0 && !service.mount.active &&
		!service.source.active && service.reload_pending &&
		service.staged_entry != NULL);
	assert(!cache_files_precache_map_loaded("ui"));
	/* Corrupt the now-closed backing file between CE preflight and the deferred
	 * post-unload validation. The new map must fail closed with no owner/handle
	 * leak; restoring the exact source must permit a fresh preflight and retry. */
	{
		char map_path[512];
		FILE *file;
		int opens_before = filexio_open_count;
		int closes_before = filexio_close_count;
		uint8_t changed;
		snprintf(map_path, sizeof(map_path), "%smaps/ui.map", asset_root);
		file = fopen(map_path, "r+b");
		assert(file != NULL && fseek(file, 4096, SEEK_SET) == 0);
		assert(fread(&changed, 1, 1, file) == 1);
		assert(fseek(file, 4096, SEEK_SET) == 0);
		changed ^= 0x80;
		assert(fwrite(&changed, 1, 1, file) == 1 && fclose(file) == 0);
		assert(!cache_files_precache_map_begin("levels\\ui\\ui", TRUE));
		assert(!service.reload_pending && !service.preflight_ready &&
			service.staged_entry == NULL && !service.mount.active &&
			!service.source.active && service.map_arena->used == 0 &&
			section_scratch.used == 0);
		assert(filexio_open_count == filexio_close_count);
		file = fopen(map_path, "r+b");
		assert(file != NULL && fseek(file, 4096, SEEK_SET) == 0);
		changed ^= 0x80;
		assert(fwrite(&changed, 1, 1, file) == 1 && fclose(file) == 0);
		assert(filexio_open_count > opens_before &&
			filexio_close_count > closes_before);
	}
	assert(ps2_cache_preflight_map("levels\\ui\\ui"));
	assert(cache_files_precache_map_begin("levels\\ui\\ui", TRUE));
	assert(cache_files_precache_map_loaded("ui"));
	assert(!service.reload_pending && !service.preflight_ready &&
		service.mount.active && service.source.active);
	assert(service.map_arena->used == streaming_used &&
		service.map_arena->high == streaming_high &&
		section_scratch.used == 0);
	hcu_map_service_lifecycle_trace("owner-reloaded", 1);
	complete = FALSE;
	assert(cache_file_open("ui", &header));
	assert(cache_file_read(NONE, 2048, 2048, bsp_cache,
		&complete, TRUE) == NONE && complete == TRUE);
	assert(memcmp(bsp_cache + 20, "psbs", 4) == 0);
	assert(filexio_open_count == filexio_close_count + 1);
	/* Exercise a transport EOF on the deferred post-unload revalidation path,
	 * after the active map owner was released but before a replacement mount. */
	assert(ps2_cache_preflight_map("levels\\ui\\ui"));
	assert(service.reload_pending && service.mount.active && service.source.active);
	assert(ps2_cache_release_map_owner());
	assert(service.reload_pending && !service.mount.active && !service.source.active);
	filexio_read_bytes_before_eof = 1;
	filexio_injected_eof_count = 0;
	filexio_successful_read_calls = 0;
	assert(!cache_files_precache_map_begin("levels\\ui\\ui", TRUE));
	assert(filexio_injected_eof_count == 1 && filexio_successful_read_calls > 0);
	assert(!service.mount.active && !service.source.active &&
		service.source.reader.descriptor == -1 && !service.preflight_ready &&
		!service.reload_pending && service.staged_entry == NULL &&
		service.staged_map[0] == 0 && service.map_arena->used == 0 &&
		section_scratch.used == 0 && !cache_files_precache_map_loaded("ui"));
	assert(filexio_open_count == filexio_close_count);
	/* A corrected, valid request in the same process must still mount. */
	assert(ps2_cache_preflight_map("levels\\ui\\ui"));
	assert(cache_files_precache_map_begin("levels\\ui\\ui", TRUE));
	assert(cache_files_precache_map_loaded("ui") && service.mount.active &&
		service.source.active && service.map_arena->used == streaming_used);
	assert(section_scratch.used == 0);
	/* Corrupt each required metadata/tag section after CE's pre-unload
	 * preflight. Deferred revalidation must fail cleanly and permit exact retry. */
	{
		static const char *section_tags[] = { "HMAP", "CTAG", "CRNG", "CBIX" };
		char package_path[512];
		size_t section_index;
		snprintf(package_path, sizeof(package_path), "%smaps/ui.hp2", asset_root);
		for (section_index = 0;
			section_index < sizeof(section_tags) / sizeof(section_tags[0]);
			++section_index) {
			assert(ps2_cache_preflight_map("levels\\ui\\ui"));
			assert(ps2_cache_release_map_owner());
			assert(flip_hp2_section_payload_byte(package_path,
				section_tags[section_index]));
			assert(!cache_files_precache_map_begin("levels\\ui\\ui", TRUE));
			assert(!service.mount.active && !service.source.active &&
				service.source.reader.descriptor == -1 && !service.preflight_ready &&
				!service.reload_pending && service.staged_entry == NULL &&
				service.staged_map[0] == 0 && service.map_arena->used == 0 &&
				section_scratch.used == 0 && !cache_files_precache_map_loaded("ui"));
			assert(filexio_open_count == filexio_close_count);
			assert(flip_hp2_section_payload_byte(package_path,
				section_tags[section_index]));
			assert(ps2_cache_preflight_map("levels\\ui\\ui"));
			assert(cache_files_precache_map_begin("levels\\ui\\ui", TRUE));
			assert(cache_files_precache_map_loaded("ui") && service.mount.active &&
				service.source.active && service.map_arena->used == streaming_used);
			assert(section_scratch.used == 0);
		}
	}
	/* Keep preflight valid, then make the PS2 cache backend reject CTAG during
	 * the deferred post-unload mount. This covers the composed transaction's
	 * late publication failure (after source/hash/section validation), rather
	 * than only corrupt-input failures that stop before the backend callback. */
	{
		map_service_snapshot before, after;
		int opens_before, closes_before;
		assert(ps2_cache_preflight_map("levels\\ui\\ui"));
		assert(service.reload_pending && service.mount.active &&
			service.source.active);
		assert(ps2_cache_release_map_owner());
		assert(service.map_arena->used == 0 && !service.mount.active &&
			!service.source.active && service.reload_pending);
		before = capture_map_service_snapshot(&service);
		opens_before = filexio_open_count;
		closes_before = filexio_close_count;
		/* The first query belongs to deferred preflight and sees full capacity;
		 * every later query belongs to CTAG mount and sees an undersized span.
		 * The query count proves rejection happened at the backend boundary. */
		tag_cache_capacity_fault = 1024 * 1024;
		tag_cache_capacity_fault_after_queries = 1;
		tag_cache_capacity_fault_query_count = 0;
		assert(!cache_files_precache_map_begin("levels\\ui\\ui", TRUE));
		after = capture_map_service_snapshot(&service);
		assert(tag_cache_capacity_fault_query_count >= 2);
		assert(after.map_used == before.map_used &&
			after.scratch_used == before.scratch_used &&
			after.map_high <= after.map_cap &&
			after.scratch_high <= after.scratch_cap);
		assert(!after.mount_active && !after.source_active &&
			after.source_descriptor == -1 && !after.preflight_ready &&
			!after.reload_pending && after.staged_entry == NULL &&
			after.staged_map[0] == 0 && !after.cache_loaded);
		assert(after.open_count == after.close_count &&
			after.open_count > opens_before && after.close_count > closes_before);
		assert(after.tag_cache_hash == before.tag_cache_hash &&
			after.bsp_cache_hash == before.bsp_cache_hash);
		assert(filexio_open_count == filexio_close_count);
		puts("retail-ui service: late cache-mount capacity rejection rolled back and closed source");
		/* Disable the one-shot capacity schedule; a fresh preflight must recover. */
		tag_cache_capacity_fault_after_queries = -1;
		tag_cache_capacity = TAG_CACHE_SIZE;
		assert(ps2_cache_preflight_map("levels\\ui\\ui"));
		assert(cache_files_precache_map_begin("levels\\ui\\ui", TRUE));
		assert(cache_files_precache_map_loaded("ui") && service.mount.active &&
			service.source.active && service.map_arena->used == streaming_used);
		assert(section_scratch.used == 0 &&
			filexio_open_count == filexio_close_count + 1);
	}
	/* Fault-inject the opposite ordering: the cache is unpublished but its
	 * parent owner has not been released. A deferred loader must reject this
	 * inconsistent transition and preserve the still-live source/arena until
	 * shutdown performs the owner release. */
	assert(ps2_cache_preflight_map("levels\\ui\\ui"));
	ps2_cache_unmount_ctag();
	assert(!cache_files_precache_map_begin("levels\\ui\\ui", TRUE));
	assert(!service.reload_pending && service.staged_entry == NULL &&
		service.mount.active && service.source.active &&
		service.map_arena->used == streaming_used &&
		!cache_files_precache_map_loaded("ui"));
	puts("retail-ui service: same-map unload/revalidate/fail-closed/retry and active-owner guard passed");
	/* Shutdown must release the still-live owner and its reader after the
	 * injected cache-before-owner invalidation. */
	hcu_map_service_shutdown(&service);
	assert(service.map_arena->used == 0 && !service.mount.active &&
		!service.source.active && !service.reload_pending &&
		service.staged_entry == NULL);
	assert(filexio_open_count == filexio_close_count);
	return 0;
}

int main(int argc, char **argv)
{
	ctag_mount competing_mount;
	ctag_mount_backend backend_rejecting_mount;
	struct cache_file_header header;
	boolean complete = FALSE;
	uint8_t resource[32];
	uint8_t *preserved;
	size_t baseline, used;
	int backend_mount_calls = 0;
	int bsp_registration_calls = 0;
	unsigned i;
	if (argc == 3 && strcmp(argv[1], "--verify-ui-source") == 0)
		return verify_retail_ui_source(argv[2]);
	if (argc == 4 && strcmp(argv[1], "--retail-ui") == 0)
		return run_retail_ui_mount(argv[2], argv[3]);
	if (argc == 3 && strcmp(argv[1], "--retail-ui-service") == 0)
		return run_retail_ui_service(argv[2], 0, 0);
	if (argc == 3 && strcmp(argv[1], "--retail-ui-service-bsp-crc-failure") == 0)
		return run_retail_ui_service(argv[2], 0, 1);
	if (argc == 3 && strcmp(argv[1], "--retail-ui-service-reject") == 0)
		return run_retail_ui_service(argv[2], 1, 0);
	if (argc == 3 && strcmp(argv[1], "--retail-ui-service-open-failure") == 0)
		return run_retail_ui_service_open_failure(argv[2]);
	if (argc == 3 && strcmp(argv[1], "--retail-ui-service-short-read") == 0)
		return run_retail_ui_service_short_read(argv[2]);
	assert(argc == 11);
	backend = ctag_ps2_cache_backend();
	assert(backend != NULL);
	assert(file_reader_filexio_init() == 0);
	arena_init(&section_output_arena, "exact section output",
		section_output_memory, sizeof(section_output_memory));
	arena_init(&section_scratch_arena, "section compressed scratch",
		section_scratch_memory, sizeof(section_scratch_memory));
	{
		size_t section_size = 0;
		/* Decoded bytes consume the whole owner. The same-arena layout must
		 * fail, while split compressed-input scratch must succeed. */
		assert(!world_load_section_with_scratch(&section_output_arena,
			&section_output_arena, argv[1], "DATA", &section_size, 0));
		assert(section_output_arena.used == 0);
		assert(world_load_section_with_scratch(&section_output_arena,
			&section_scratch_arena, argv[1], "DATA", &section_size, 0));
		assert(section_size == SECTION_OUTPUT_SIZE);
		assert(section_output_arena.used == SECTION_OUTPUT_SIZE);
		assert(section_scratch_arena.used == 0);
		for (i = 0; i < SECTION_OUTPUT_SIZE; i++)
			assert(section_output_memory[i] == 0);
	}
	for (i = 0; i < sizeof(map_source); i++) map_source[i] = (uint8_t)(i * 19u + 5u);
	resource_map_path = argv[4];
	arena_init(&map_arena, "test resident", arena_memory, sizeof(arena_memory));
	arena_init(&bsp_scratch_arena, "test BSP scratch", bsp_scratch_memory,
		sizeof(bsp_scratch_memory));
	preserved = arena_alloc(&map_arena, 32, 16);
	assert(preserved);
	memset(preserved, 0xA5, 32);
	ctag_mount_init(&active_mount);
	ctag_mount_init(&competing_mount);
	baseline = map_arena.used;
	/* An in-arena pointer is not sufficient: the section must belong to this
	 * transaction, or unload could release an older live arena allocation. */
	assert(ctag_mount_hp2(&competing_mount, &map_arena, argv[1], "ui",
		0x4000, 0x1000, sizeof(map_source), ctag_map_source_read,
		&disk_map_source, backend,
		load_preexisting, NULL) != 0);
	assert(map_arena.used == baseline && !competing_mount.active);
	for (i = 0; i < 32; i++) assert(preserved[i] == 0xA5);
	assert(ctag_mount_hp2(&competing_mount, &map_arena, argv[1], "ui",
		0x4000, 0x1000, sizeof(map_source), ctag_map_source_read,
		&disk_map_source, backend,
		load_outside, NULL) != 0);
	assert(map_arena.used == baseline && !competing_mount.active);
	/* L3 backend-mount rejection occurs only after real CTAG/CRNG decoding.
	 * It must roll back the mount transaction, leave the singleton HCU cache
	 * unpublished, close no borrowed source implicitly, and allow the following
	 * normal loader path to mount successfully in this same process. */
	backend_rejecting_mount = *backend;
	backend_rejecting_mount.context = &backend_mount_calls;
	backend_rejecting_mount.mount = reject_backend_mount;
	assert(ctag_map_source_open_any(&disk_map_source, resource_map_path) == 0);
	assert(ctag_mount_hp2(&competing_mount, &map_arena, argv[1], "ui",
		0x4000, 0x1000, sizeof(map_source), ctag_map_source_read,
		&disk_map_source, &backend_rejecting_mount,
		load_section, &bsp_scratch_arena) != 0);
	assert(backend_mount_calls == 1 && map_arena.used == baseline &&
		!competing_mount.active && disk_map_source.active &&
		bsp_scratch_arena.used == 0 &&
		!cache_files_precache_map_loaded("ui"));
	ctag_map_source_close(&disk_map_source);
	assert(!disk_map_source.active);
	assert(filexio_open_count == filexio_close_count);
	/* Fail after CTAG/CRNG and CBIX have been materialized and mounted, at the
	 * final parent-to-cache BSP-loader registration boundary. Rollback must
	 * unmount adapter callbacks and return the owner to its exact mark. */
	backend_rejecting_mount = *backend;
	backend_rejecting_mount.context = &bsp_registration_calls;
	backend_rejecting_mount.register_bsp_loader = reject_bsp_loader_registration;
	assert(ctag_mount_hp2_file_verified_discover_with_bsp_catalog(
		&competing_mount, &map_arena, &bsp_scratch_arena, argv[1], "ui",
		resource_map_path, &disk_map_source, &backend_rejecting_mount,
		load_section, &bsp_scratch_arena) != 0);
	assert(bsp_registration_calls == 1 && map_arena.used == baseline &&
		!competing_mount.active && !disk_map_source.active &&
		disk_map_source.reader.descriptor == -1 && bsp_scratch_arena.used == 0 &&
		!cache_files_precache_map_loaded("ui"));
	assert(filexio_open_count == filexio_close_count);
	/* Exercise a rejection inside the real HCU backend: CTAG/CRNG decode
	 * succeeds, but the fixed cache span is deliberately too small for the
	 * validated image. The adapter must refuse publication and the parent must
	 * roll back; the borrowed source remains caller-owned until explicitly shut. */
	tag_cache_capacity = 75;
	assert(ctag_map_source_open_any(&disk_map_source, resource_map_path) == 0);
	assert(ctag_mount_hp2(&competing_mount, &map_arena, argv[1], "ui",
		0x4000, 0x1000, sizeof(map_source), ctag_map_source_read,
		&disk_map_source, backend, load_section, &bsp_scratch_arena) != 0);
	assert(map_arena.used == baseline && !competing_mount.active &&
		disk_map_source.active && !cache_files_precache_map_loaded("ui") &&
		bsp_scratch_arena.used == 0);
	ctag_map_source_close(&disk_map_source);
	assert(!disk_map_source.active &&
		filexio_open_count == filexio_close_count);
	tag_cache_capacity = TAG_CACHE_SIZE;
	assert(ps2_cache_set_map_loader(parent_map_loader, &bsp_scratch_arena));

	/* The CE-precache path delegates to the parent owner and fails closed on a
	 * corrupt HP2 section, with its decoded allocation rolled back. */
	map_pack_path = argv[2];
	tag_cache_capacity = TAG_CACHE_SIZE;
	assert(!cache_files_precache_map_begin("ui", FALSE));
	assert(!disk_map_source.active);
	assert(map_arena.used == baseline && !active_mount.active);
	assert(!cache_files_precache_map_loaded("ui"));
	/* Invalid HP2 headers, codec metadata, out-of-file extents, and overlapping
	 * sections must fail at the production C section-reader boundary, restore
	 * the owner cursor, close the source, and leave cache state unpublished. */
	map_pack_path = argv[7];
	assert(!cache_files_precache_map_begin("ui", FALSE));
	assert(!disk_map_source.active && map_arena.used == baseline &&
		!active_mount.active && !cache_files_precache_map_loaded("ui"));
	map_pack_path = argv[8];
	assert(!cache_files_precache_map_begin("ui", FALSE));
	assert(!disk_map_source.active && map_arena.used == baseline &&
		!active_mount.active && !cache_files_precache_map_loaded("ui"));
	map_pack_path = argv[9];
	assert(!cache_files_precache_map_begin("ui", FALSE));
	assert(!disk_map_source.active && map_arena.used == baseline &&
		!active_mount.active && !cache_files_precache_map_loaded("ui"));
	map_pack_path = argv[10];
	assert(!cache_files_precache_map_begin("ui", FALSE));
	assert(!disk_map_source.active && map_arena.used == baseline &&
		!active_mount.active && !cache_files_precache_map_loaded("ui"));
	/* Same-size source substitution is rejected by HMAP before any cache or
	 * owner arena state is published. */
	map_pack_path = argv[1];
	resource_map_path = argv[6];
	assert(!cache_files_precache_map_begin("ui", FALSE));
	assert(!disk_map_source.active);
	assert(map_arena.used == baseline && !active_mount.active);
	assert(!cache_files_precache_map_loaded("ui"));
	resource_map_path = argv[4];
	/* Force the first resident-section reservation to fail with only 16 bytes
	 * left after the preserved prefix. Restore the arena contract and let the
	 * later positive load prove that this allocation failure is retryable. */
	{
		size_t original_cap = map_arena.cap;
		map_pack_path = argv[1];
		map_arena.cap = baseline + 16u;
		assert(!cache_files_precache_map_begin("ui", FALSE));
		map_arena.cap = original_cap;
		assert(map_arena.used == baseline && map_arena.high <= map_arena.cap &&
			!disk_map_source.active && !active_mount.active &&
			!cache_files_precache_map_loaded("ui"));
		assert(filexio_open_count == filexio_close_count);
	}

	/* A valid HP2 container cannot mask a corrupt CRNG table CRC. */
	map_pack_path = argv[3];
	assert(!cache_files_precache_map_begin("ui", FALSE));
	assert(!disk_map_source.active);
	assert(map_arena.used == baseline && !active_mount.active);
	assert(!cache_files_precache_map_loaded("ui"));
	/* Cache-capacity refusal through the same path also restores the mark. */
	map_pack_path = argv[1];
	tag_cache_capacity = 75;
	assert(!cache_files_precache_map_begin("ui", FALSE));
	assert(!disk_map_source.active);
	assert(map_arena.used == baseline && !active_mount.active);
	assert(!cache_files_precache_map_loaded("ui"));

	tag_cache_capacity = TAG_CACHE_SIZE;
	assert(cache_files_precache_map_begin("ui", FALSE));
	assert(active_mount.active && active_mount.payload && active_mount.payload_size > 0);
	assert(active_mount.bsp_catalog.count == 2);
	assert(disk_map_source.active);
	assert(map_arena.used > baseline);
	used = map_arena.used;
	assert(cache_files_precache_map_begin("ui", FALSE));
	assert(!cache_files_precache_map_begin("b30", FALSE));
	assert(map_arena.used == used && active_mount.active);
	assert(ctag_mount_hp2(&competing_mount, &map_arena, argv[1], "ui",
			0x4000, 0x1000, sizeof(map_source), ctag_map_source_read,
			&disk_map_source, backend,
			load_section, &bsp_scratch_arena) != 0);
	assert(map_arena.used == used && !competing_mount.active && active_mount.active);
	assert(cache_files_precache_map_loaded("ui"));
	assert(cache_file_open("ui", &header));
	assert(header.tag_data_offset == 0x4000);
	assert(header.file_length == sizeof(map_source));
	assert(cache_file_read(NONE, header.tag_data_offset, header.tag_data_size,
		tag_cache, &complete, TRUE) == NONE);
	assert(complete == TRUE);
	complete = FALSE;
	assert(cache_file_read(NONE, 0x2000, 24, bsp_cache,
		&complete, TRUE) == NONE);
	assert(complete == TRUE && memcmp(bsp_cache + 20, "psbs", 4) == 0);
	assert(bsp_scratch_arena.used == 0);
	complete = FALSE;
	assert(cache_file_read(NONE, 0x3000, 24, bsp_cache,
		&complete, TRUE) == NONE);
	assert(complete == TRUE && bsp_cache[0] == 0x42);
	assert(bsp_scratch_arena.used == 0);
	ctag_mount_unload(&active_mount);
	ctag_mount_init(&active_mount);
	map_pack_path = argv[5];
	assert(cache_files_precache_map_begin("ui", FALSE));
	assert(cache_file_open("ui", &header));
	complete = FALSE;
	cache_file_read(NONE, 0x3000, 24, bsp_cache, &complete, TRUE);
	assert(complete == _cache_file_read_failed && bsp_scratch_arena.used == 0);
	ctag_mount_unload(&active_mount);
	ctag_mount_init(&active_mount);
	map_pack_path = argv[1];
	assert(cache_files_precache_map_begin("ui", FALSE));
	assert(cache_file_open("ui", &header));
	complete = FALSE;
	assert(cache_file_read(NONE, 0x2000, 24, bsp_cache,
		&complete, TRUE) == NONE && complete == TRUE);
	assert(cache_file_read(7, 0x1000, sizeof(resource), resource,
		&complete, FALSE) == NONE);
	assert(complete == TRUE && memcmp(resource, map_source + 0x1000,
		sizeof(resource)) == 0);
	complete = FALSE;
	assert(cache_file_read(NONE, 0x2000, 24, bsp_cache,
		&complete, TRUE) == NONE);
	assert(complete == TRUE && memcmp(bsp_cache + 20, "psbs", 4) == 0);
	memset(resource, 0xCC, sizeof(resource));
	complete = TRUE;
	assert(cache_file_read(7, 0x3000, sizeof(resource), resource,
		&complete, FALSE) == NONE);
	assert(complete == _cache_file_read_failed);
	for (i = 0; i < sizeof(resource); i++) assert(resource[i] == 0xCC);

	ctag_mount_unload(&active_mount);
	assert(!active_mount.active && !disk_map_source.active && map_arena.used == baseline);
	assert(bsp_scratch_arena.used == 0);
	assert(!cache_files_precache_map_loaded("ui"));
	assert(!cache_file_open("ui", &header));
	ctag_mount_unload(&active_mount);
	assert(map_arena.used == baseline);
	for (i = 0; i < FILEXIO_FAKE_HANDLES; i++) assert(filexio_map_files[i] == NULL);
	assert(filexio_open_count == filexio_close_count);
	return 0;
}
