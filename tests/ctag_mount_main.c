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
static uint8_t map_source[0x8000];
static ctag_map_source disk_map_source;
static uint8_t arena_memory[ARENA_SIZE] __attribute__((aligned(64)));
static uint8_t bsp_scratch_memory[BSP_SCRATCH_SIZE] __attribute__((aligned(64)));
static uint8_t section_output_memory[SECTION_OUTPUT_SIZE] __attribute__((aligned(64)));
static uint8_t section_scratch_memory[128] __attribute__((aligned(16)));
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
static int filexio_open_count;
static int filexio_close_count;

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
	filexio_open_count++;
	return slot + 7;
}

int fileXioClose(int descriptor)
{
	FILE *file = filexio_get_file(descriptor);
	assert(file != NULL);
	assert(fclose(file) == 0);
	filexio_map_files[descriptor - 7] = NULL;
	filexio_close_count++;
	return 0;
}

int fileXioRead(int descriptor, void *buffer, int size)
{
	size_t count;
	FILE *file = filexio_get_file(descriptor);
	assert(file != NULL && size >= 0);
	count = fread(buffer, 1, (size_t)size, file);
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
unsigned long physical_memory_get_tag_cache_size(void) { return tag_cache_capacity; }
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
	assert(ctag_mount_hp2_file_verified_discover(&active_mount, &map_arena,
		pack_path, "ui", resource_map_path_arg, &disk_map_source, backend,
		load_section, &bsp_scratch_arena) == 0);
	assert(active_mount.active && disk_map_source.active);
	assert(active_mount.resource_index.tag_data_offset == 31939584u);
	assert(active_mount.resource_index.tag_data_size == 1642244u);
	assert(active_mount.resource_index.file_length == 33582080u);
	assert(ctag_map_source_matches_sha256_with_buffer(&disk_map_source,
		expected_source_sha256, source_hash_scratch,
		sizeof(source_hash_scratch)));
	assert(map_arena.high == 1550356u);
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

static int run_retail_ui_service(const char *asset_root)
{
	mem_layout_v2_t layout;
	arena_t map_arena, section_scratch;
	hcu_map_service service;
	struct cache_file_header header;
	boolean complete = FALSE;
	size_t streaming_high;
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
	/* The owner must reject absent/corrupt data before CE begins publication. */
	assert(!ps2_cache_preflight_map("levels\\b30\\b30"));
	assert(ps2_cache_preflight_map("levels\\ui\\ui"));
	assert(cache_files_precache_map_begin("levels\\ui\\ui", TRUE));
	assert(cache_files_precache_map_loaded("ui"));
	assert(cache_file_open("ui", &header));
	assert(header.tag_data_size == 1510628);
	assert(cache_file_read(NONE, header.tag_data_offset, header.tag_data_size,
		tag_cache, &complete, TRUE) == NONE && complete == TRUE);
	/* An unsupported target is rejected before disturbing the mounted UI map. */
	assert(!ps2_cache_preflight_map("levels\\b30\\b30"));
	assert(service.mount.active && cache_files_precache_map_loaded("ui"));
	streaming_high = service.map_arena->high;
	assert(streaming_high <= service.map_arena->cap);
	printf("retail-ui service: streaming=%zu/%zu preflight=verified\n",
		streaming_high, service.map_arena->cap);
	/* Match scenario_unload's post-unpublication owner release callback. */
	assert(ps2_cache_release_map_owner());
	assert(service.map_arena->used == 0 && !service.mount.active &&
		!service.source.active);
	assert(filexio_open_count == filexio_close_count);
	hcu_map_service_shutdown(&service);
	return 0;
}

int main(int argc, char **argv)
{
	ctag_mount competing_mount;
	struct cache_file_header header;
	boolean complete = FALSE;
	uint8_t resource[32];
	uint8_t *preserved;
	size_t baseline, used;
	unsigned i;
	if (argc == 3 && strcmp(argv[1], "--verify-ui-source") == 0)
		return verify_retail_ui_source(argv[2]);
	if (argc == 4 && strcmp(argv[1], "--retail-ui") == 0)
		return run_retail_ui_mount(argv[2], argv[3]);
	if (argc == 3 && strcmp(argv[1], "--retail-ui-service") == 0)
		return run_retail_ui_service(argv[2]);
	assert(argc == 7);
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
	assert(ps2_cache_set_map_loader(parent_map_loader, &bsp_scratch_arena));

	/* The CE-precache path delegates to the parent owner and fails closed on a
	 * corrupt HP2 section, with its decoded allocation rolled back. */
	map_pack_path = argv[2];
	tag_cache_capacity = TAG_CACHE_SIZE;
	assert(!cache_files_precache_map_begin("ui", FALSE));
	assert(!disk_map_source.active);
	assert(map_arena.used == baseline && !active_mount.active);
	assert(!cache_files_precache_map_loaded("ui"));
	/* Same-size source substitution is rejected by HMAP before any cache or
	 * owner arena state is published. */
	map_pack_path = argv[1];
	resource_map_path = argv[6];
	assert(!cache_files_precache_map_begin("ui", FALSE));
	assert(!disk_map_source.active);
	assert(map_arena.used == baseline && !active_mount.active);
	assert(!cache_files_precache_map_loaded("ui"));
	resource_map_path = argv[4];

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
