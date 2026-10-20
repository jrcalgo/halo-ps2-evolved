#ifndef HALO_CBSP_CATALOG_H
#define HALO_CBSP_CATALOG_H

#include <stddef.h>
#include <stdint.h>

typedef struct {
	const uint8_t *bytes;
	size_t size;
	uint32_t file_length;
	uint32_t count;
} cbsp_catalog;

typedef struct {
	uint32_t file_offset;
	uint32_t file_size;
	char section_tag[5];
} cbsp_catalog_entry;

int cbsp_catalog_open(cbsp_catalog *catalog, const void *bytes, size_t size,
	uint32_t expected_file_length);
int cbsp_catalog_find(const cbsp_catalog *catalog, uint32_t file_offset,
	uint32_t file_size, cbsp_catalog_entry *entry);

#endif
