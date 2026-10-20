#include "stream/cbsp_catalog.h"

#include "stream/hp2.h"

#include <string.h>

#define CBIX_HEADER_SIZE 28u
#define CBIX_RECORD_SIZE 16u
#define CBIX_MAX_ENTRIES 32u

static uint32_t read_u32(const uint8_t *p)
{
	return (uint32_t)p[0] | (uint32_t)p[1] << 8 |
		(uint32_t)p[2] << 16 | (uint32_t)p[3] << 24;
}

static int reserved_tag(const uint8_t *tag)
{
	return memcmp(tag, "CTAG", 4) == 0 || memcmp(tag, "CRNG", 4) == 0 ||
		memcmp(tag, "CBIX", 4) == 0;
}

int cbsp_catalog_open(cbsp_catalog *catalog, const void *data, size_t size,
	uint32_t expected_file_length)
{
	const uint8_t *bytes = (const uint8_t *)data;
	uint32_t count, file_length;
	uint64_t previous_end = 0;
	size_t i;
	if (!catalog || !bytes || size < CBIX_HEADER_SIZE ||
		memcmp(bytes, "CBIX", 4) != 0 || read_u32(bytes + 4) != 1)
		return 0;
	count = read_u32(bytes + 8);
	file_length = read_u32(bytes + 12);
	if (!count || count > CBIX_MAX_ENTRIES || file_length != expected_file_length ||
		read_u32(bytes + 16) != CBIX_HEADER_SIZE ||
		read_u32(bytes + 24) != 0 ||
		size != CBIX_HEADER_SIZE + (size_t)count * CBIX_RECORD_SIZE ||
		hp2_crc32(bytes + CBIX_HEADER_SIZE, size - CBIX_HEADER_SIZE) !=
			read_u32(bytes + 20))
		return 0;
	for (i = 0; i < count; i++) {
		const uint8_t *row = bytes + CBIX_HEADER_SIZE + i * CBIX_RECORD_SIZE;
		uint32_t offset = read_u32(row);
		uint32_t length = read_u32(row + 4);
		uint64_t end = (uint64_t)offset + length;
		unsigned j;
		if (!length || end > file_length || offset < previous_end ||
			read_u32(row + 12) != 0 || reserved_tag(row + 8))
			return 0;
		for (j = 0; j < 4; j++)
			if (row[8 + j] < 0x20 || row[8 + j] > 0x7E) return 0;
		for (j = 0; j < i; j++)
			if (memcmp(row + 8,
				bytes + CBIX_HEADER_SIZE + j * CBIX_RECORD_SIZE + 8, 4) == 0)
				return 0;
		previous_end = end;
	}
	catalog->bytes = bytes;
	catalog->size = size;
	catalog->file_length = file_length;
	catalog->count = count;
	return 1;
}

int cbsp_catalog_find(const cbsp_catalog *catalog, uint32_t file_offset,
	uint32_t file_size, cbsp_catalog_entry *entry)
{
	uint32_t lo = 0, hi;
	if (!catalog || !catalog->bytes || !entry || !file_size) return 0;
	hi = catalog->count;
	while (lo < hi) {
		uint32_t mid = lo + (hi - lo) / 2;
		const uint8_t *row = catalog->bytes + CBIX_HEADER_SIZE +
			(size_t)mid * CBIX_RECORD_SIZE;
		uint32_t start = read_u32(row);
		if (file_offset < start) hi = mid;
		else if (file_offset > start) lo = mid + 1;
		else {
			if (read_u32(row + 4) != file_size) return 0;
			entry->file_offset = start;
			entry->file_size = file_size;
			memcpy(entry->section_tag, row + 8, 4);
			entry->section_tag[4] = 0;
			return 1;
		}
	}
	return 0;
}
