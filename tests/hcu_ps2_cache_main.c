#include "cseries.h"
#include "cache/cache_files.h"
#include <assert.h>
#include <stddef.h>

static unsigned char tag_cache[2 * 1024 * 1024];

void *physical_memory_get_structure_bsp_cache_base_address(void)
{
	return NULL;
}

unsigned long physical_memory_get_structure_bsp_cache_size(void)
{
	return 0;
}

void *physical_memory_get_tag_cache_base_address(void)
{
	return tag_cache;
}

unsigned long physical_memory_get_tag_cache_size(void)
{
	return sizeof tag_cache;
}

int main(void)
{
	real progress = 1.0f;
	boolean completed = FALSE;
	char destination[8] = "stable";

	cache_files_initialize();
	assert(!cache_files_precache_in_progress());
	assert(!cache_files_precache_is_copying_map("ui"));
	assert(!cache_files_precache_map_loaded("ui"));
	assert(cache_files_precache_map_status(&progress) == _cached_map_file_failed);
	assert(progress == 0.0f);
	assert(!cache_files_precache_map_begin("ui", TRUE));
	assert(!cache_file_open("ui", 0));
	assert(cache_file_read(0, 0, sizeof(destination), destination,
		&completed, TRUE) == NONE);
	assert(completed == _cache_file_read_failed);
	assert(destination[0] == 's');
	cache_file_close();
	cache_files_precache_map_end();
	cache_files_precache_map_queue_end();
	cache_files_dispose();
	return 0;
}
