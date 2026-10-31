#include "core/mem.h"
#include "ps2_ctag.h"
#include "stream/file.h"
#include "world/section.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

enum { CTAG_HEADER_BYTES = 52 };

typedef struct {
	uint8_t *header;
	uint8_t *image;
	size_t image_bytes;
	uint8_t *relocations;
	size_t relocation_bytes;
	size_t received;
	size_t fail_after;
} ctag_sink;

static int copy_span(uint8_t *destination, size_t destination_bytes,
	size_t source_offset, const uint8_t *bytes, size_t size,
	size_t *consumed)
{
	size_t count;
	if (source_offset > destination_bytes) return 0;
	count = destination_bytes - source_offset;
	if (count > size) count = size;
	if (count) memcpy(destination + source_offset, bytes, count);
	*consumed = count;
	return 1;
}

static int ctag_sink_write(void *context, uint32_t offset,
	const uint8_t *bytes, size_t size)
{
	ctag_sink *sink = (ctag_sink *)context;
	size_t consumed = 0, count;
	if (!sink || !bytes || (size_t)offset != sink->received) return -1;
	while (consumed < size)
	{
		size_t position = (size_t)offset + consumed;
		if (sink->fail_after && position >= sink->fail_after) {
			sink->received += consumed;
			return -1;
		}
		if (sink->fail_after && size - consumed > sink->fail_after - position)
			size = consumed + sink->fail_after - position;
		if (position < CTAG_HEADER_BYTES)
		{
			if (!copy_span(sink->header, CTAG_HEADER_BYTES, position,
				bytes + consumed, size - consumed, &count)) return -1;
		}
		else if (position < CTAG_HEADER_BYTES + sink->image_bytes)
		{
			if (!copy_span(sink->image, sink->image_bytes,
				position - CTAG_HEADER_BYTES, bytes + consumed,
				size - consumed, &count)) return -1;
		}
		else
		{
			size_t relocation_offset = position - CTAG_HEADER_BYTES -
				sink->image_bytes;
			if (!copy_span(sink->relocations, sink->relocation_bytes,
				relocation_offset, bytes + consumed, size - consumed,
				&count)) return -1;
		}
		if (!count) return -1;
		consumed += count;
		if (sink->fail_after && (size_t)offset + consumed >= sink->fail_after)
		{
			sink->received += consumed;
			return -1;
		}
	}
	sink->received += size;
	return 0;
}

static int read_exact(const char *path, uint8_t *destination, size_t size)
{
	file_reader_t reader = { .descriptor = -1 };
	int result;
	if (file_reader_open(&reader, path) != 0) return 0;
	result = reader.size == size && file_reader_read_at(&reader, 0,
		destination, size) == 0;
	file_reader_close(&reader);
	return result;
}

void SyncDCache(const void *start, const void *end)
{
	(void)start;
	(void)end;
}

int main(int argc, char **argv)
{
	uint8_t *expected, *image, header[CTAG_HEADER_BYTES];
	uint8_t scratch_bytes[393216] __attribute__((aligned(64)));
	arena_t scratch;
	ps2_ctag_view view;
	ctag_sink sink;
	size_t image_bytes, relocation_count, relocation_bytes;
	size_t raw_bytes = 0, mark;
	uint32_t base_address = 0x00100000u;
	hp2_status stream_status;
	ps2_ctag_status ctag_status;
	if (argc < 4 || argc > 6) return 2;
	image_bytes = (size_t)strtoul(argv[3], NULL, 10);
	if (!image_bytes || image_bytes > 32u * 1024u * 1024u) return 3;
	expected = (uint8_t *)malloc(image_bytes);
	image = (uint8_t *)malloc(image_bytes);
	if (!expected || !image || !read_exact(argv[2], expected, image_bytes))
		return 4;
	memset(image, 0xCD, image_bytes);
	arena_init(&scratch, "ctag stream scratch", scratch_bytes,
		sizeof(scratch_bytes));
	mark = arena_mark(&scratch);
	/* The relocation count is preflight metadata; reject multiplication overflow
	 * and reserve it before the visitor leases its decoder work buffers. */
	/* The test uses the audited Longest count; production obtains this from its
	 * verified preflight record and checks it against the streamed header. */
	relocation_count = 18855u;
	if (relocation_count > SIZE_MAX / 4u) return 6;
	relocation_bytes = relocation_count * 4u;
	sink.header = header;
	sink.image = image;
	sink.image_bytes = image_bytes;
	sink.relocations = (uint8_t *)arena_alloc(&scratch, relocation_bytes, 16);
	sink.relocation_bytes = relocation_bytes;
	sink.received = 0;
	sink.fail_after = argc >= 5 && strcmp(argv[4], "expect-partial-sink-fail") == 0 ?
		CTAG_HEADER_BYTES + image_bytes + 16u : 0;
	if (!sink.relocations) return 7;
	memset(header, 0, sizeof(header));
	memset(sink.relocations, 0, relocation_bytes);
	stream_status = world_visit_section_with_scratch(&scratch, argv[1],
		"CTAG", &raw_bytes, 0, ctag_sink_write, &sink);
	if (argc >= 5 && strcmp(argv[4], "expect-partial-sink-fail") == 0)
	{
		uint8_t *raw_image = (uint8_t *)malloc(image_bytes);
		if (!raw_image || argc != 6 || !read_exact(argv[5], raw_image, image_bytes) ||
			stream_status != HP2_ERR_IO || sink.received != sink.fail_after ||
			memcmp(image, raw_image, image_bytes) != 0 ||
			scratch.used != relocation_bytes)
			return 12;
		printf("streamed CTAG partial sink failure: staged=%u image-unmodified\n",
			(unsigned)sink.received);
		free(raw_image);
		arena_release(&scratch, mark);
		free(image);
		free(expected);
		return 0;
	}
	if (argc >= 5 && strcmp(argv[4], "expect-crc-fail") == 0)
	{
		uint8_t *raw_image = (uint8_t *)malloc(image_bytes);
		if (!raw_image || argc != 6 || !read_exact(argv[5], raw_image, image_bytes) ||
			stream_status != HP2_ERR_CRC || raw_bytes != 0 ||
			sink.received != CTAG_HEADER_BYTES + image_bytes + relocation_bytes ||
			scratch.used != relocation_bytes ||
			memcmp(image, raw_image, image_bytes) != 0)
			return 10;
		printf("streamed CTAG outer-CRC rejected: staged=%u image-unmodified\n",
			(unsigned)sink.received);
		free(raw_image);
		arena_release(&scratch, mark);
		free(image);
		free(expected);
		return 0;
	}
	if (argc >= 5 && strcmp(argv[4], "expect-inner-crc-fail") == 0)
	{
		uint8_t *raw_image = (uint8_t *)malloc(image_bytes);
		if (!raw_image || argc != 6 || !read_exact(argv[5], raw_image, image_bytes))
			return 13;
		ctag_status = ps2_ctag_open_parts(&view, header, sizeof(header), image,
			image_bytes, sink.relocations, relocation_bytes, image_bytes,
			(uint32_t)relocation_count);
		if (stream_status != HP2_OK || !raw_bytes ||
			sink.received != CTAG_HEADER_BYTES + image_bytes + relocation_bytes ||
			scratch.used != relocation_bytes ||
			ctag_status != PS2_CTAG_ERR_CHECKSUM ||
			memcmp(image, raw_image, image_bytes) != 0)
			return 11;
		printf("streamed CTAG inner-CRC rejected: staged=%u image-unmodified\n",
			(unsigned)sink.received);
		free(raw_image);
		arena_release(&scratch, mark);
		free(image);
		free(expected);
		return 0;
	}
	if (stream_status != HP2_OK ||
		raw_bytes != CTAG_HEADER_BYTES + image_bytes + relocation_bytes ||
		sink.received != raw_bytes || scratch.used != relocation_bytes)
		return 8;
	ctag_status = ps2_ctag_open_parts(&view, header, sizeof(header), image,
		image_bytes, sink.relocations, relocation_bytes, image_bytes,
		(uint32_t)relocation_count);
	if (ctag_status != PS2_CTAG_OK ||
		ps2_ctag_rebase_in_place(&view, base_address, image, image_bytes) !=
			PS2_CTAG_OK || memcmp(image, expected, image_bytes) != 0)
		return 9;
	printf("streamed CTAG commit: image=%u relocations=%u scratch_high=%u\n",
		(unsigned)image_bytes, (unsigned)relocation_count,
		(unsigned)scratch.high);
	arena_release(&scratch, mark);
	free(image);
	free(expected);
	return 0;
}
