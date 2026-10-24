#include "cseries.h"
#include "cache/cache_files.h"
#include "halo_ps2_cache.h"

#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

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

static uint8_t tag_cache[2 * 1024 * 1024];
static uint8_t bsp_cache[2 * 1024 * 1024];
static unsigned long tag_cache_capacity = sizeof tag_cache;
static uint8_t source_file[32768];
static unsigned source_reads;
static unsigned owner_releases;

static int fail_ctag_visit(void *context, ps2_cache_ctag_sink_fn sink,
	void *sink_context, size_t *raw_size)
{
	(void)context;
	(void)sink;
	(void)sink_context;
	(void)raw_size;
	return 0;
}

static void release_owner(void *context)
{
	assert(context == &owner_releases);
	owner_releases++;
	ps2_cache_unmount_ctag();
}

static int read_source(void *context, int32_t tag_index, uint32_t offset,
	uint32_t size, void *buffer, int blocking)
{
	const uint8_t *source = context;
	(void)blocking;
	if (!source || tag_index != 7 || offset > sizeof source_file ||
		size > sizeof source_file - offset)
		return 0;
	memcpy(buffer, source + offset, size);
	source_reads++;
	return 1;
}

void *physical_memory_get_tag_cache_base_address(void)
{
	return tag_cache;
}

unsigned long physical_memory_get_tag_cache_size(void)
{
	return tag_cache_capacity;
}

void *physical_memory_get_structure_bsp_cache_base_address(void)
{
	return bsp_cache;
}

unsigned long physical_memory_get_structure_bsp_cache_size(void)
{
	return sizeof bsp_cache;
}

int main(int argc, char **argv)
{
	FILE *file;
	long length;
	unsigned i;
	uint8_t *payload;
	struct cache_file_header header;
	real progress = 0.0f;
	boolean completed = FALSE;
	uint32_t tag_table, vertex_table, index_table, name_pointer, data_pointer;
	uint8_t resource_read[16];
	uint32_t stream_relocations[5];
	ps2_ctag_stream_info stream_info;
	ps2_ctag_view decoded_view;
	ps2_cache_owner_telemetry owner_stats;
	assert(argc == 2);
	file = fopen(argv[1], "rb");
	assert(file && fseek(file, 0, SEEK_END) == 0);
	length = ftell(file);
	assert(length > 0 && fseek(file, 0, SEEK_SET) == 0);
	payload = malloc((size_t)length);
	assert(payload && fread(payload, 1, (size_t)length, file) == (size_t)length);
	fclose(file);

	assert(!cache_files_precache_map_loaded("ui"));
	tag_cache_capacity = 75;
	assert(!ps2_cache_mount_ctag("levels\\ui\\ui", payload, (size_t)length));
	tag_cache_capacity = 76;
	assert(ps2_cache_mount_ctag("levels\\ui\\ui", payload, (size_t)length));
	assert(cache_files_precache_map_loaded("ui"));
	assert(cache_files_precache_map_status(&progress) == _cached_map_file_success);
	assert(progress == 1.0f);
	assert(!cache_file_open("b30", &header));
	assert(cache_file_open("ui", &header));
	assert(header.header_signature == 0x68656164u);
	assert(header.footer_signature == 0x666F6F74u);
	assert(header.version == 5);
	assert(header.tag_data_offset == 0x800);
	assert(header.tag_data_size == 76);
	assert(header.file_length == 0x800 + 76);
	assert(strcmp(header.name, "ui") == 0);
	assert(strcmp(header.build, "01.10.12.2276") == 0);
	assert(cache_file_read(NONE, header.tag_data_offset, header.tag_data_size,
		tag_cache, &completed, TRUE) == NONE);
	assert(completed == TRUE);
	ps2_cache_owner_telemetry_snapshot(&owner_stats);
	assert(owner_stats.tag_current_bytes == 76);
	assert(owner_stats.tag_peak_bytes == 76);
	assert(owner_stats.tag_publications == 1);
	ps2_cache_owner_telemetry_reset(); /* mounted owners keep live counters */
	ps2_cache_owner_telemetry_snapshot(&owner_stats);
	assert(owner_stats.tag_current_bytes == 76 && owner_stats.tag_publications == 1);
	memcpy(&tag_table, tag_cache, sizeof tag_table);
	memcpy(&vertex_table, tag_cache + 20, sizeof vertex_table);
	memcpy(&index_table, tag_cache + 28, sizeof index_table);
	memcpy(&name_pointer, tag_cache + 52, sizeof name_pointer);
	memcpy(&data_pointer, tag_cache + 56, sizeof data_pointer);
	assert(tag_table == (uint32_t)(uintptr_t)tag_cache + 36);
	assert(vertex_table == 0 && index_table == 0);
	assert(name_pointer == (uint32_t)(uintptr_t)tag_cache + 68);
	assert(data_pointer == (uint32_t)(uintptr_t)tag_cache + 72);
	completed = TRUE;
	assert(cache_file_read(NONE, header.tag_data_offset, header.tag_data_size - 1,
		tag_cache, &completed, TRUE) == NONE);
	assert(completed == _cache_file_read_failed);
	ps2_cache_owner_telemetry_snapshot(&owner_stats);
	assert(owner_stats.tag_failures == 0 && owner_stats.tag_current_bytes == 76);
	cache_file_close();
	assert(cache_files_precache_map_loaded("levels\\ui\\ui"));
	ps2_cache_unmount_ctag();
	ps2_cache_owner_telemetry_snapshot(&owner_stats);
	assert(owner_stats.tag_resets == 1);
	assert(!cache_files_precache_map_loaded("ui"));
	assert(!cache_file_open("ui", &header));
	completed = TRUE;
	assert(cache_file_read(NONE, 0x800, 76, tag_cache, &completed, TRUE) == NONE);
	assert(completed == _cache_file_read_failed);
	assert(ps2_ctag_open(&decoded_view, payload, (size_t)length,
		tag_cache_capacity, tag_cache_capacity / 4) == PS2_CTAG_OK);
	memset(&stream_info, 0, sizeof(stream_info));
	stream_info.image_size = (uint32_t)decoded_view.image_size;
	stream_info.relocation_count = decoded_view.relocation_count;
	stream_info.scenario_tag_index = decoded_view.scenario_tag_index;
	assert(ps2_cache_mount_ctag_stream("ui", &stream_info,
		(uint8_t *)stream_relocations, sizeof(stream_relocations), 0x800,
		0x800 + stream_info.image_size, read_source, source_file));
	assert(ps2_cache_set_ctag_visitor(fail_ctag_visit, NULL));
	assert(cache_file_open("ui", &header));
	completed = TRUE;
	assert(cache_file_read(NONE, header.tag_data_offset, header.tag_data_size,
		tag_cache, &completed, TRUE) == NONE);
	assert(completed == _cache_file_read_failed);
	ps2_cache_owner_telemetry_snapshot(&owner_stats);
	assert(owner_stats.tag_failures == 1 && owner_stats.tag_current_bytes == 0);
	assert(owner_stats.tag_peak_bytes == 76);
	ps2_cache_unmount_ctag();
	/* CE stores the pathless map leaf in cache_file_header.name (32 bytes),
	 * while the scenario request may be a longer canonical levels path. */
	assert(ps2_cache_mount_ctag("levels\\test\\bloodgulch\\bloodgulch",
		payload, (size_t)length));
	assert(cache_files_precache_map_loaded(
		"levels\\test\\bloodgulch\\bloodgulch"));
	assert(cache_file_open("bloodgulch", &header));
	assert(strcmp(header.name, "bloodgulch") == 0);
	assert(cache_file_read(NONE, header.tag_data_offset, header.tag_data_size,
		tag_cache, &completed, TRUE) == NONE && completed == TRUE);
	ps2_cache_owner_telemetry_snapshot(&owner_stats);
	assert(owner_stats.tag_current_bytes == 76 && owner_stats.tag_peak_bytes == 76);
	ps2_cache_unmount_ctag();
	ps2_cache_owner_telemetry_snapshot(&owner_stats);
	assert(owner_stats.tag_current_bytes == 0 && owner_stats.tag_unmounts == 3);
	assert(owner_stats.tag_resets == 3);
	assert(owner_stats.mount_rejections >= 1);
	assert(!cache_files_precache_map_loaded("bloodgulch"));
	for (i = 0; i < sizeof source_file; i++)
		source_file[i] = (uint8_t)(i * 37u + 11u);
	assert(!ps2_cache_mount_ctag_with_file_source("ui", payload, (size_t)length,
	0x4000, 0x4000 + 75, read_source, source_file));
	assert(ps2_cache_set_map_unloader(release_owner, &owner_releases));
	assert(ps2_cache_mount_ctag_with_file_source("ui", payload, (size_t)length,
	0x4000, sizeof source_file, read_source, source_file));
	assert(cache_file_open("ui", &header));
	assert(header.tag_data_offset == 0x4000);
	assert(header.file_length == sizeof source_file);
	assert(cache_file_read(NONE, header.tag_data_offset, header.tag_data_size,
		tag_cache, &completed, TRUE) == NONE);
	assert(completed == TRUE);
	assert(cache_file_read(7, 0x1000, sizeof resource_read, resource_read,
		&completed, FALSE) == NONE);
	assert(completed == TRUE);
	assert(source_reads == 1);
	assert(memcmp(resource_read, source_file + 0x1000, sizeof resource_read) == 0);
	completed = TRUE;
	assert(cache_file_read(7, header.tag_data_offset + 1, sizeof resource_read,
		resource_read, &completed, TRUE) == NONE);
	assert(completed == _cache_file_read_failed);
	assert(source_reads == 1);
	completed = TRUE;
	assert(cache_file_read(7, sizeof source_file - 4, sizeof resource_read,
		resource_read, &completed, TRUE) == NONE);
	assert(completed == _cache_file_read_failed);
	assert(source_reads == 1);
	assert(cache_file_read(7, -1, sizeof resource_read, resource_read,
		&completed, TRUE) == NONE);
	assert(completed == _cache_file_read_failed);
	assert(source_reads == 1);
	assert(ps2_cache_release_map_owner());
	assert(owner_releases == 1);
	assert(!cache_files_precache_map_loaded("ui"));
	assert(ps2_cache_release_map_owner());
	assert(owner_releases == 1);
	ps2_cache_owner_telemetry_reset();
	ps2_cache_owner_telemetry_snapshot(&owner_stats);
	assert(owner_stats.tag_current_bytes == 0 && owner_stats.tag_peak_bytes == 0);
	assert(owner_stats.tag_failures == 0 && owner_stats.mount_rejections == 0);
	free(payload);
	return 0;
}
