#ifndef HCU_PS2_CACHE_TEST_CACHE_FILES_H
#define HCU_PS2_CACHE_TEST_CACHE_FILES_H

#include "cseries.h"

enum cached_map_file_precache_state
{
	_cached_map_file_in_progress,
	_cached_map_file_success,
	_cached_map_file_failed,
};

enum { _cache_file_read_failed = 2 };

struct cache_file_header;

void cache_files_initialize(void);
void cache_files_dispose(void);
void cache_files_precache_set_priority(boolean blocking);
boolean cache_files_precache_in_progress(void);
boolean cache_files_precache_is_copying_map(const char *map_name);
boolean cache_files_precache_map_loaded(const char *map_name);
short cache_files_precache_map_status(real *progress);
void cache_files_precache_map_end(void);
void cache_files_precache_map_queue_end(void);
boolean cache_files_precache_map_begin(const char *map_name, boolean copy_map);
void cache_file_close(void);
boolean cache_file_open(const char *scenario_name, struct cache_file_header *header);
short cache_file_read(long tag_index, long offset, long size, void *buffer,
	boolean *completion_flag_reference, boolean blocking);

#endif
