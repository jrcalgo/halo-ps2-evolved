/* File-backed corpus preflight: no package image or directory allocation. */
#include "stream/hcu_asset_profile.h"
#include <stdio.h>
#include <stdlib.h>

typedef struct {
	FILE *file;
	uint32_t size, maximum_read, reads;
} corpus_reader;

static int read_at(void *context, uint32_t offset, void *destination, uint32_t size)
{
	corpus_reader *reader = context;
	if (offset > reader->size || size > reader->size - offset ||
		fseek(reader->file, offset, SEEK_SET) != 0)
		return -1;
	if (size > reader->maximum_read) reader->maximum_read = size;
	reader->reads++;
	return fread(destination, 1, size, reader->file) == size ? 0 : -1;
}

int main(int argc, char **argv)
{
	corpus_reader reader = { 0 };
	hcu_asset_profile_view view;
	hcu_asset_chunk_view ce;
	uint8_t crossing[40];
	long length;
	int status;
	if (argc != 3 || !(reader.file = fopen(argv[1], "rb"))) return 2;
	if (fseek(reader.file, 0, SEEK_END) != 0 || (length = ftell(reader.file)) < 0 ||
		(unsigned long)length > UINT32_MAX) return 3;
	reader.size = (uint32_t)length;
	status = hcu_asset_profile_preflight_reader(read_at, &reader, reader.size,
		(uint32_t)strtoul(argv[2], NULL, 0), &view);
	if (status || view.version != 2 ||
		hcu_asset_profile_lookup(&view, HCU_ASSET_CHUNK_CE, 0, &ce) ||
		ce.size < 65560u || hcu_asset_profile_read_range(&view,
			HCU_ASSET_CHUNK_CE, 0, 65520u, crossing, sizeof crossing)) return 4;
	printf("OK %u %u %u %u %u\n", view.profile_id, view.chunk_count,
		ce.size, reader.maximum_read, reader.reads);
	fclose(reader.file);
	return 0;
}
