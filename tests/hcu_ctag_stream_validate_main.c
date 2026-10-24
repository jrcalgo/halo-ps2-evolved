#include "ps2_ctag.h"

#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

typedef struct
{
	const uint8_t *bytes;
	size_t size;
	long fail_offset;
} memory_reader;

static int read_exact(void *context, size_t offset, uint8_t *destination,
	size_t size)
{
	memory_reader *reader = (memory_reader *)context;
	if (!reader || offset > reader->size || size > reader->size - offset)
		return -1;
	if (reader->fail_offset >= 0 &&
		(size_t)reader->fail_offset >= offset &&
		(size_t)reader->fail_offset - offset < size)
		return -1;
	memcpy(destination, reader->bytes + offset, size);
	return 0;
}

static uint8_t *read_file(const char *path, size_t *size)
{
	FILE *file;
	long length;
	uint8_t *bytes;
	file = fopen(path, "rb");
	if (!file || fseek(file, 0, SEEK_END) != 0) {
		if (file) fclose(file);
		return NULL;
	}
	length = ftell(file);
	if (length < 0 || fseek(file, 0, SEEK_SET) != 0) {
		fclose(file);
		return NULL;
	}
	bytes = (uint8_t *)malloc(length ? (size_t)length : 1u);
	if (!bytes) { fclose(file); return NULL; }
	if (fread(bytes, 1, (size_t)length, file) != (size_t)length) {
		free(bytes);
		fclose(file);
		return NULL;
	}
	fclose(file);
	*size = (size_t)length;
	return bytes;
}

static long parse_long(const char *text, long fallback)
{
	char *end;
	long value;
	errno = 0;
	value = strtol(text, &end, 10);
	if (errno || end == text || *end) return fallback;
	return value;
}

static ps2_ctag_status validate_push_visitors(const uint8_t *payload,
	size_t payload_size, uint8_t *scratch, size_t scratch_size,
	size_t maximum_image_size, uint32_t maximum_relocations)
{
	static const size_t chunks[] = { 1u, 3u, 17u, 4u, 257u, 2u, 63u };
	ps2_ctag_stream_validator first;
	ps2_ctag_stream_info info;
	ps2_ctag_status status;
	size_t offset, chunk_index = 0;
	if (payload_size < 52u) return PS2_CTAG_ERR_TRUNCATED;
	status = ps2_ctag_stream_validator_begin(&first, payload, 52u,
		(size_t)-1, scratch, scratch_size, maximum_image_size,
		maximum_relocations);
	if (status != PS2_CTAG_OK) return status;
	offset = 52u;
	while (offset < payload_size)
	{
		size_t take = chunks[chunk_index++ %
			(sizeof(chunks) / sizeof(chunks[0]))];
		if (take > payload_size - offset) take = payload_size - offset;
		status = ps2_ctag_stream_validator_write(&first, (uint32_t)offset,
			payload + offset, take);
		if (status != PS2_CTAG_OK) return status;
		offset += take;
	}
	return ps2_ctag_stream_validator_finish(&first, &info);
}

int main(int argc, char **argv)
{
	ps2_ctag_view view;
	ps2_ctag_stream_info info;
	ps2_ctag_status status, expected;
	memory_reader reader;
	uint8_t scratch[4096];
	uint8_t *payload;
	size_t payload_size, scratch_size;
	long expected_value, push_expected_value, scratch_value, fail_offset;
	long maximum_relocations;
	if (argc != 7) return 2;
	payload = read_file(argv[1], &payload_size);
	if (!payload) return 3;
	expected_value = parse_long(argv[2], -1);
	push_expected_value = parse_long(argv[3], -1);
	scratch_value = parse_long(argv[4], -1);
	fail_offset = parse_long(argv[5], -1);
	maximum_relocations = parse_long(argv[6], -1);
	if (expected_value < 0 || expected_value > PS2_CTAG_ERR_IO ||
		push_expected_value < 0 || push_expected_value > PS2_CTAG_ERR_IO ||
		scratch_value < 0 || (size_t)scratch_value > sizeof(scratch) ||
		maximum_relocations < 0 || (unsigned long)maximum_relocations > 0xFFFFFFFFul) {
		free(payload);
		return 4;
	}
	scratch_size = (size_t)scratch_value;
	memset(scratch, 0xA5, sizeof(scratch));
	memset(&info, 0x5A, sizeof(info));
	reader.bytes = payload;
	reader.size = payload_size;
	reader.fail_offset = fail_offset;
	status = ps2_ctag_validate_stream(read_exact, &reader, payload_size,
		scratch_size ? scratch : NULL, scratch_size, 32u * 1024u * 1024u,
		(uint32_t)maximum_relocations, &info);
	expected = (ps2_ctag_status)expected_value;
	if (status != expected) {
		fprintf(stderr, "status=%d expected=%d\n", (int)status,
			(int)expected);
		free(payload);
		return 10;
	}
	if (status == PS2_CTAG_OK) {
		if (ps2_ctag_open(&view, payload, payload_size,
			32u * 1024u * 1024u, (uint32_t)maximum_relocations) != PS2_CTAG_OK ||
			info.image_size != view.image_size ||
			info.relocation_count != view.relocation_count ||
			info.scenario_tag_index != view.scenario_tag_index) {
			free(payload);
			return 11;
		}
	} else if (info.image_size || info.relocation_count || info.scenario_tag_index) {
		fprintf(stderr, "failure returned partial info\n");
		free(payload);
		return 12;
	}
	if (fail_offset < 0) {
		ps2_ctag_status push_status = validate_push_visitors(payload,
			payload_size, scratch, scratch_size, 32u * 1024u * 1024u,
			(uint32_t)maximum_relocations);
		if (push_status != (ps2_ctag_status)push_expected_value) {
			fprintf(stderr, "push-status=%d expected=%d\n",
				(int)push_status, (int)push_expected_value);
			free(payload);
			return 13;
		}
	}
	free(payload);
	return 0;
}
