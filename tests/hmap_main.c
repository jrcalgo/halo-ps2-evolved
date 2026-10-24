#include "stream/hmap.h"

#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

int main(int argc, char **argv)
{
	FILE *file;
	long length;
	uint8_t *bytes;
	hmap_identity identity;
	assert(argc == 3);
	file = fopen(argv[1], "rb");
	assert(file && fseek(file, 0, SEEK_END) == 0);
	length = ftell(file);
	assert(length > 0 && fseek(file, 0, SEEK_SET) == 0);
	bytes = (uint8_t *)malloc((size_t)length);
	assert(bytes && fread(bytes, 1, (size_t)length, file) == (size_t)length);
	fclose(file);
	if (!hmap_open(&identity, bytes, (size_t)length, argv[2])) {
		free(bytes);
		return 2;
	}
	assert(identity.file_length == 1000);
	assert(identity.tag_data_offset == 400 && identity.tag_data_size == 100);
	for (unsigned i = 0; i < 32; i++) assert(identity.source_sha256[i] == i);
	free(bytes);
	return 0;
}
