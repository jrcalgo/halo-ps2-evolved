#include "stream/cbsp_catalog.h"

#include <assert.h>
#include <stdio.h>
#include <stdlib.h>

static unsigned char *read_file(const char *path, size_t *length)
{
	FILE *file = fopen(path, "rb");
	long size;
	unsigned char *bytes;
	if (!file || fseek(file, 0, SEEK_END) != 0) return NULL;
	size = ftell(file);
	if (size < 0 || fseek(file, 0, SEEK_SET) != 0) { fclose(file); return NULL; }
	bytes = (unsigned char *)malloc(size ? (size_t)size : 1);
	if (!bytes || fread(bytes, 1, (size_t)size, file) != (size_t)size) {
		free(bytes); fclose(file); return NULL;
	}
	fclose(file);
	*length = (size_t)size;
	return bytes;
}

int main(int argc, char **argv)
{
	cbsp_catalog catalog;
	cbsp_catalog_entry entry;
	size_t size;
	unsigned char *bytes;
	assert(argc == 2);
	bytes = read_file(argv[1], &size);
	assert(bytes);
	assert(cbsp_catalog_open(&catalog, bytes, size, 8192));
	assert(catalog.count == 2);
	assert(cbsp_catalog_find(&catalog, 2048, 64, &entry));
	assert(entry.file_offset == 2048 && entry.file_size == 64);
	assert(entry.section_tag[0] == 'B' && entry.section_tag[1] == '0' &&
		entry.section_tag[2] == '0' && entry.section_tag[3] == '0');
	assert(cbsp_catalog_find(&catalog, 6144, 64, &entry));
	assert(entry.section_tag[3] == '1');
	assert(!cbsp_catalog_find(&catalog, 6144, 65, &entry));
	assert(!cbsp_catalog_find(&catalog, 4096, 64, &entry));
	free(bytes);
	return 0;
}
