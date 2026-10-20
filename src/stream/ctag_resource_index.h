#ifndef HALO_CTAG_RESOURCE_INDEX_H
#define HALO_CTAG_RESOURCE_INDEX_H

#include <stddef.h>
#include <stdint.h>

typedef struct {
	const uint8_t *bytes;
	size_t size;
	uint32_t file_length;
	uint32_t tag_data_offset;
	uint32_t tag_data_size;
	uint32_t interval_count;
} ctag_resource_index;

typedef int (*ctag_resource_source_read_fn)(void *context, int32_t tag_index,
	uint32_t file_offset, uint32_t size, void *buffer, int blocking);

/* Validate a CRNG v1 map-only resource index against the source file and the
 * original retail tag extent. `bytes` remains caller-owned and immutable. */
int ctag_resource_index_open(ctag_resource_index *index, const void *bytes,
	size_t size, uint32_t expected_file_length,
	uint32_t expected_tag_data_offset, uint32_t expected_tag_data_size);

/* Discover the retail tag extent from a CRNG v1 header while still requiring
 * the source map length to match the packaged resource ranges. */
int ctag_resource_index_open_discover(ctag_resource_index *index,
	const void *bytes, size_t size, uint32_t expected_file_length);

/* Authorize a nonempty source-file read only when wholly covered by one row. */
int ctag_resource_index_allows(const ctag_resource_index *index,
	uint32_t offset, uint32_t size);
/* Reject a BSP extent if any portion aliases an authorized external resource. */
int ctag_resource_index_overlaps(const ctag_resource_index *index,
	uint32_t offset, uint32_t size);

/* Verify the request against CRNG before forwarding it to the platform source.
 * The source is never called for a gap, tag-region, or out-of-file request. */
int ctag_resource_index_read(const ctag_resource_index *index,
	ctag_resource_source_read_fn source_read, void *context,
	int32_t tag_index, uint32_t offset, uint32_t size, void *buffer,
	int blocking);

#endif
