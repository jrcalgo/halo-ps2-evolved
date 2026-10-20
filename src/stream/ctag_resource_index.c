#include "stream/ctag_resource_index.h"

#include "stream/hp2.h"

#include <string.h>

#define CRNG_HEADER_SIZE 36u
#define CRNG_RECORD_SIZE 8u
#define CRNG_VERSION 1u
#define CRNG_MAX_INTERVALS 1000000u

static uint32_t read_u32(const uint8_t *p)
{
	return (uint32_t)p[0] | (uint32_t)p[1] << 8 |
		(uint32_t)p[2] << 16 | (uint32_t)p[3] << 24;
}

int ctag_resource_index_open(ctag_resource_index *index, const void *data,
	size_t size, uint32_t expected_file_length,
	uint32_t expected_tag_data_offset, uint32_t expected_tag_data_size)
{
	const uint8_t *bytes = (const uint8_t *)data;
	uint32_t count, file_length, tag_offset, tag_size, body_crc;
	uint64_t tag_end, prior_end = 0;
	size_t i;
	if (!index || !bytes || size < CRNG_HEADER_SIZE ||
		memcmp(bytes, "CRNG", 4) != 0 || read_u32(bytes + 4) != CRNG_VERSION)
		return 0;
	count = read_u32(bytes + 8);
	file_length = read_u32(bytes + 12);
	tag_offset = read_u32(bytes + 16);
	tag_size = read_u32(bytes + 20);
	body_crc = read_u32(bytes + 28);
	if (read_u32(bytes + 24) != CRNG_HEADER_SIZE || read_u32(bytes + 32) != 0 ||
		count > CRNG_MAX_INTERVALS ||
		(size_t)count > (size - CRNG_HEADER_SIZE) / CRNG_RECORD_SIZE ||
	size != CRNG_HEADER_SIZE + (size_t)count * CRNG_RECORD_SIZE ||
	file_length == 0 || file_length != expected_file_length ||
	tag_offset != expected_tag_data_offset || tag_size != expected_tag_data_size ||
	tag_offset > file_length || tag_size > file_length - tag_offset ||
	hp2_crc32(bytes + CRNG_HEADER_SIZE, size - CRNG_HEADER_SIZE) != body_crc)
		return 0;
	tag_end = (uint64_t)tag_offset + tag_size;
	for (i = 0; i < count; i++) {
		const uint8_t *row = bytes + CRNG_HEADER_SIZE + i * CRNG_RECORD_SIZE;
		uint32_t offset = read_u32(row);
		uint32_t length = read_u32(row + 4);
		uint64_t end = (uint64_t)offset + length;
		if (length == 0 || end > file_length ||
			(i != 0 && offset <= prior_end) ||
			((uint64_t)offset < tag_end && tag_offset < end))
			return 0;
		prior_end = end;
	}
	index->bytes = bytes;
	index->size = size;
	index->file_length = file_length;
	index->tag_data_offset = tag_offset;
	index->tag_data_size = tag_size;
	index->interval_count = count;
	return 1;
}

int ctag_resource_index_open_discover(ctag_resource_index *index,
	const void *data, size_t size, uint32_t expected_file_length)
{
	const uint8_t *bytes = (const uint8_t *)data;
	uint32_t tag_offset, tag_size;
	if (!bytes || size < CRNG_HEADER_SIZE ||
		memcmp(bytes, "CRNG", 4) != 0 || read_u32(bytes + 4) != CRNG_VERSION)
		return 0;
	tag_offset = read_u32(bytes + 16);
	tag_size = read_u32(bytes + 20);
	return ctag_resource_index_open(index, bytes, size, expected_file_length,
		tag_offset, tag_size);
}

int ctag_resource_index_allows(const ctag_resource_index *index,
	uint32_t offset, uint32_t size)
{
	uint32_t lo = 0, hi;
	if (!index || !index->bytes || size == 0 || offset > index->file_length ||
	size > index->file_length - offset)
		return 0;
	hi = index->interval_count;
	while (lo < hi) {
		uint32_t mid = lo + (hi - lo) / 2;
		const uint8_t *row = index->bytes + CRNG_HEADER_SIZE + mid * CRNG_RECORD_SIZE;
		uint32_t start = read_u32(row);
		uint32_t length = read_u32(row + 4);
		uint32_t end = start + length;
		if (offset < start) {
			hi = mid;
		} else if (offset >= end) {
			lo = mid + 1;
		} else {
			return size <= end - offset;
		}
	}
	return 0;
}

int ctag_resource_index_overlaps(const ctag_resource_index *index,
	uint32_t offset, uint32_t size)
{
	uint32_t lo = 0, hi;
	uint64_t request_end;
	if (!index || !index->bytes || !size || offset > index->file_length ||
		size > index->file_length - offset)
		return 1;
	request_end = (uint64_t)offset + size;
	hi = index->interval_count;
	while (lo < hi) {
		uint32_t mid = lo + (hi - lo) / 2;
		const uint8_t *row = index->bytes + CRNG_HEADER_SIZE +
			(size_t)mid * CRNG_RECORD_SIZE;
		uint32_t start = read_u32(row);
		uint32_t length = read_u32(row + 4);
		if ((uint64_t)start + length <= offset) lo = mid + 1;
		else hi = mid;
	}
	if (lo == index->interval_count) return 0;
	{
		const uint8_t *row = index->bytes + CRNG_HEADER_SIZE +
			(size_t)lo * CRNG_RECORD_SIZE;
		uint32_t start = read_u32(row);
		return (uint64_t)start < request_end;
	}
}

int ctag_resource_index_read(const ctag_resource_index *index,
	ctag_resource_source_read_fn source_read, void *context,
	int32_t tag_index, uint32_t offset, uint32_t size, void *buffer,
	int blocking)
{
	if (!source_read || !buffer ||
		!ctag_resource_index_allows(index, offset, size))
		return 0;
	return source_read(context, tag_index, offset, size, buffer, blocking);
}
