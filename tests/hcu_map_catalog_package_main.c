#include "stream/hcu_map_catalog.h"

#include "stream/cbsp_catalog.h"
#include "stream/hp2.h"

#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static uint8_t *read_file(const char *path, size_t *size_out)
{
	FILE *file = fopen(path, "rb");
	long length;
	uint8_t *bytes;
	assert(file);
	assert(fseek(file, 0, SEEK_END) == 0);
	length = ftell(file);
	assert(length > 0);
	assert(fseek(file, 0, SEEK_SET) == 0);
	bytes = (uint8_t *)malloc((size_t)length);
	assert(bytes);
	assert(fread(bytes, 1, (size_t)length, file) == (size_t)length);
	assert(fclose(file) == 0);
	*size_out = (size_t)length;
	return bytes;
}

static void verify_package(const char *path, const char *map_name)
{
	const hcu_map_catalog_entry *entry = hcu_map_catalog_find(map_name);
	uint8_t hmap_bytes[72];
	uint8_t cbix_bytes[28 + 32 * 16];
	uint8_t *image;
	size_t image_size;
	size_t cbix_size;
	hp2_pack pack;
	const hp2_section *hmap_section;
	const hp2_section *cbix_section;
	cbsp_catalog catalog;
	uint16_t index;

	assert(entry);
	image = read_file(path, &image_size);
	assert(hp2_open(&pack, image, image_size) == HP2_OK);
	assert(strcmp(pack.name, entry->identity.map_name) == 0);
	hmap_section = hp2_find(&pack, "HMAP");
	cbix_section = hp2_find(&pack, "CBIX");
	assert(hmap_section && hmap_section->raw_size == sizeof(hmap_bytes));
	assert(cbix_section && cbix_section->raw_size <= sizeof(cbix_bytes));
	assert(hp2_load(&pack, hmap_section, hmap_bytes,
		sizeof(hmap_bytes)) == HP2_OK);
	assert(hcu_map_catalog_validate_hmap(entry, hmap_bytes,
		sizeof(hmap_bytes), NULL));
	cbix_size = cbix_section->raw_size;
	assert(hp2_load(&pack, cbix_section, cbix_bytes,
		sizeof(cbix_bytes)) == HP2_OK);
	assert(hcu_map_catalog_validate_bsp_catalog(entry,
		cbix_bytes, cbix_size));
	assert(cbsp_catalog_open(&catalog, cbix_bytes, cbix_size,
		entry->identity.file_length));
	assert(catalog.count == entry->bsp_count);
	for (index = 0; index < entry->bsp_count; index++) {
		const hcu_map_bsp_entry *expected = &entry->bsp_catalog[index];
		cbsp_catalog_entry actual;
		assert(cbsp_catalog_find(&catalog, expected->file_offset,
			expected->file_size, &actual));
		assert(memcmp(actual.section_tag, expected->section_tag, 4) == 0);
	}
	free(image);
}

int main(int argc, char **argv)
{
	assert(argc == 3);
	verify_package(argv[1], "ui");
	verify_package(argv[2], "levels\\test\\bloodgulch\\bloodgulch");
	return 0;
}
