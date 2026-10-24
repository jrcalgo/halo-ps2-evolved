#include "cseries.h"
#include "cache/cache_files.h"
#include "cache/physical_memory_map.h"
#include "core/mem.h"
#include "halo_ps2_cache.h"
#include "stream/ctag_map_source.h"
#include "stream/ctag_mount.h"
#include "stream/ctag_ps2_backend.h"
#include "world/section.h"

#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define LONGEST_TAG_CAPACITY 4477120u
#define LONGEST_BSP_CAPACITY 1814336u
#define LONGEST_SCRATCH_CAPACITY 124224u
#define LONGEST_OWNER_CAPACITY (8u * 1024u * 1024u)
#define LONGEST_SECTION_SCRATCH_CAPACITY 124224u
#define LONGEST_BSP_GUARD 64u

uint8_t *world_load_section_with_scratch(arena_t *owner, arena_t *scratch,
	const char *path, const char *tag, size_t *raw_size, int optional);

/* The cache API deliberately forward-declares this retail-layout record. */
struct cache_file_header
{
	uint32_t header_signature;
	int32_t version;
	int32_t file_length;
	uint8_t reservedC[4];
	int32_t tag_data_offset;
	int32_t tag_data_size;
	uint8_t reserved18[8];
	char name[0x20];
	char build[0x20];
	uint8_t reserved60[4];
	uint32_t checksum;
	uint8_t reserved68[0x794];
	uint32_t footer_signature;
};

static uint8_t tag_cache[LONGEST_TAG_CAPACITY] __attribute__((aligned(16)));
static uint8_t bsp_cache[LONGEST_BSP_CAPACITY + LONGEST_BSP_GUARD]
	__attribute__((aligned(64)));
static uint8_t owner_memory[LONGEST_OWNER_CAPACITY] __attribute__((aligned(64)));
static uint8_t section_scratch_memory[LONGEST_SECTION_SCRATCH_CAPACITY]
	__attribute__((aligned(64)));
static arena_t section_scratch;
static unsigned visit_count;

void *physical_memory_get_tag_cache_base_address(void) { return tag_cache; }
unsigned long physical_memory_get_tag_cache_size(void)
{
	return LONGEST_TAG_CAPACITY;
}
void *physical_memory_get_structure_bsp_cache_base_address(void)
{
	return bsp_cache;
}
unsigned long physical_memory_get_structure_bsp_cache_size(void)
{
	return LONGEST_BSP_CAPACITY;
}

typedef struct {
	ctag_bsp_sink_fn sink;
	void *sink_context;
} sink_adapter;

static int visit_sink(void *context, uint32_t offset,
	const uint8_t *bytes, size_t size)
{
	sink_adapter *adapter = (sink_adapter *)context;
	return adapter && adapter->sink &&
		adapter->sink(adapter->sink_context, offset, bytes, size) ? 0 : -1;
}

static uint8_t *load_section(void *context, arena_t *owner,
	const char *path, const char *tag, size_t *size, int optional)
{
	arena_t *scratch = (arena_t *)context;
	return world_load_section_with_scratch(owner, scratch, path, tag, size,
		optional);
}

static int visit_section(void *context, const char *path, const char *tag,
	ctag_bsp_sink_fn sink, void *sink_context, size_t *raw_size)
{
	arena_t *scratch = (arena_t *)context;
	sink_adapter adapter;
	if (!scratch || !path || !tag || !sink || !raw_size) return 0;
	visit_count++;
	adapter.sink = sink;
	adapter.sink_context = sink_context;
	return world_visit_section_with_scratch(scratch, path, tag, raw_size, 0,
		visit_sink, &adapter) == HP2_OK;
}

static void *read_file(const char *path, size_t *size)
{
	FILE *file = fopen(path, "rb");
	long end;
	uint8_t *bytes;
	if (!file || fseek(file, 0, SEEK_END) != 0) {
		if (file) fclose(file);
		return NULL;
	}
	end = ftell(file);
	if (end < 0 || fseek(file, 0, SEEK_SET) != 0) {
		fclose(file);
		return NULL;
	}
	bytes = (uint8_t *)malloc(end ? (size_t)end : 1u);
	if (!bytes || fread(bytes, 1, (size_t)end, file) != (size_t)end) {
		free(bytes);
		fclose(file);
		return NULL;
	}
	fclose(file);
	*size = (size_t)end;
	return bytes;
}

static uint8_t *read_expected(const char *path, size_t *size)
{
	return (uint8_t *)read_file(path, size);
}

static int print_bases(void)
{
	uintptr_t tag = (uintptr_t)tag_cache;
	uintptr_t bsp = (uintptr_t)bsp_cache;
	if (tag > UINT32_MAX || bsp > UINT32_MAX) return 2;
	printf("tag_base=0x%08x bsp_base=0x%08x\n",
		(unsigned)tag, (unsigned)bsp);
	return 0;
}

int main(int argc, char **argv)
{
	arena_t owner;
	ctag_mount mount;
	ctag_map_source source;
	const ctag_mount_backend *backend;
	struct cache_file_header header;
	uint8_t *expected, *expected_tag;
	size_t expected_size, expected_tag_size;
	boolean complete = FALSE;
	if (argc == 2 && strcmp(argv[1], "--bases") == 0)
		return print_bases();
	if (argc != 5) return 2;
	if (print_bases() != 0) return 3;
	backend = ctag_ps2_cache_backend();
	assert(backend != NULL);
	arena_init(&owner, "host Longest package owner", owner_memory,
		sizeof(owner_memory));
	arena_init(&section_scratch, "124224-byte Longest visitor lease",
		section_scratch_memory, sizeof(section_scratch_memory));
	memset(bsp_cache + LONGEST_BSP_CAPACITY, 0xC7, LONGEST_BSP_GUARD);
	ctag_mount_init(&mount);
	assert(ctag_mount_hp2_file_verified_discover_with_bsp_catalog(&mount,
		&owner, &section_scratch, argv[1], "longest", argv[2], &source,
		backend, load_section, &section_scratch) == 0);
	assert(mount.active && source.active && mount.bsp_catalog.count == 1);
	assert(mount.resource_index.tag_data_size == 7079296u);
	assert(ctag_mount_set_bsp_section_visitor(&mount, visit_section));
	cache_files_initialize();
	assert(cache_file_open("longest", &header));
	assert(header.tag_data_size == 4263624);
	assert(cache_file_read(NONE, header.tag_data_offset, header.tag_data_size,
		tag_cache, &complete, TRUE) == NONE && complete == TRUE);
	expected_tag = (uint8_t *)read_file(argv[3], &expected_tag_size);
	assert(expected_tag && expected_tag_size == (size_t)header.tag_data_size);
	assert(memcmp(tag_cache, expected_tag, expected_tag_size) == 0);
	expected = read_expected(argv[4], &expected_size);
	assert(expected && expected_size == 374784u);
	complete = FALSE;
	assert(cache_file_read(NONE, 2048, 374784, bsp_cache,
		&complete, TRUE) == NONE && complete == TRUE);
	assert(visit_count == 1);
	assert(memcmp(bsp_cache, expected, expected_size) == 0);
	assert(memcmp(bsp_cache + 20, "psbs", 4) == 0);
	assert(((uint32_t *)bsp_cache)[1] == 0 && ((uint32_t *)bsp_cache)[2] == 0 &&
		((uint32_t *)bsp_cache)[3] == 0 && ((uint32_t *)bsp_cache)[4] == 0);
	assert(section_scratch.used == 0 && section_scratch.high <=
		LONGEST_SCRATCH_CAPACITY);
	assert(mount.active && source.active && !mount.bsp_active);
	{
		size_t index;
		for (index = 0; index < LONGEST_BSP_GUARD; index++)
			assert(bsp_cache[LONGEST_BSP_CAPACITY + index] == 0xC7);
	}
	printf("longest B000 direct visitor passed: source=2048/374784 image=%u rows=214 scratch=%u/%u owner=%u/%u tag=%u/%u bsp=%u/%u\n",
		(unsigned)expected_size, (unsigned)section_scratch.high,
		(unsigned)section_scratch.cap, (unsigned)owner.used,
		(unsigned)owner.cap, (unsigned)header.tag_data_size,
		(unsigned)LONGEST_TAG_CAPACITY, (unsigned)expected_size,
		(unsigned)LONGEST_BSP_CAPACITY);
	cache_file_close();
	ctag_mount_unload(&mount);
	assert(!mount.active && !source.active && owner.used == 0 &&
		section_scratch.used == 0);
	cache_files_dispose();
	free(expected);
	free(expected_tag);
	return 0;
}
