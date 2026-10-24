#include "stream/ctag_resource_index.h"

#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>

static unsigned source_calls;

static int source_read(void *context, int32_t tag_index, uint32_t offset,
	uint32_t size, void *buffer, int blocking)
{
	(void)context;
	assert(tag_index == 7 && blocking == 1 && size <= 32);
	source_calls++;
	for (uint32_t i = 0; i < size; i++) ((uint8_t *)buffer)[i] = (uint8_t)(offset + i);
	return 1;
}

int main(int argc, char **argv)
{
	FILE *file;
	long length;
	uint8_t *bytes;
	ctag_resource_index index;
	uint8_t read_buffer[32];
	assert(argc == 2);
	file = fopen(argv[1], "rb");
	assert(file);
	assert(fseek(file, 0, SEEK_END) == 0);
	length = ftell(file);
	assert(length > 0 && fseek(file, 0, SEEK_SET) == 0);
	bytes = malloc((size_t)length);
	assert(bytes && fread(bytes, 1, (size_t)length, file) == (size_t)length);
	fclose(file);
	assert(ctag_resource_index_open(&index, bytes, (size_t)length,
		1000, 400, 100));
	{
		ctag_resource_index discovered;
		assert(ctag_resource_index_open_discover(&discovered, bytes,
			(size_t)length, 1000));
		assert(discovered.tag_data_offset == 400);
		assert(discovered.tag_data_size == 100);
		assert(discovered.interval_count == index.interval_count);
	}
	assert(ctag_resource_index_allows(&index, 100, 20));
	assert(ctag_resource_index_allows(&index, 110, 10));
	assert(!ctag_resource_index_allows(&index, 119, 2));
	assert(!ctag_resource_index_allows(&index, 150, 1));
	assert(ctag_resource_index_allows(&index, 200, 50));
	assert(!ctag_resource_index_allows(&index, 245, 10));
	assert(!ctag_resource_index_allows(&index, 400, 1));
	assert(!ctag_resource_index_allows(&index, 999, 2));
	assert(!ctag_resource_index_allows(&index, 100, 0));
	assert(ctag_resource_index_overlaps(&index, 110, 10));
	assert(ctag_resource_index_overlaps(&index, 115, 10));
	assert(!ctag_resource_index_overlaps(&index, 120, 80));
	assert(ctag_resource_index_overlaps(&index, 999, 2));
	assert(ctag_resource_index_read(&index, source_read, NULL, 7,
	100, 20, read_buffer, 1));
	assert(source_calls == 1 && read_buffer[0] == 100 && read_buffer[19] == 119);
	assert(!ctag_resource_index_read(&index, source_read, NULL, 7,
		150, 1, read_buffer, 1));
	assert(source_calls == 1);
	assert(!ctag_resource_index_open(&index, bytes, (size_t)length,
		999, 400, 100));
	bytes[28] ^= 1;
	assert(!ctag_resource_index_open(&index, bytes, (size_t)length,
		1000, 400, 100));
	free(bytes);
	return 0;
}
