#ifndef HALO_STREAM_HMAP_H
#define HALO_STREAM_HMAP_H

#include <stddef.h>
#include <stdint.h>

typedef struct {
	char map_name[16];
	uint32_t file_length;
	uint32_t tag_data_offset;
	uint32_t tag_data_size;
	uint8_t source_sha256[32];
} hmap_identity;

/* Parse a canonical HMAP v1 record and optionally bind it to an expected leaf. */
int hmap_open(hmap_identity *identity, const void *bytes, size_t size,
	const char *expected_map_name);

#endif
