#include "stream/hmap.h"

#include <string.h>

#define HMAP_SIZE 72u

static uint32_t read_u32(const uint8_t *bytes)
{
	return (uint32_t)bytes[0] | (uint32_t)bytes[1] << 8 |
		(uint32_t)bytes[2] << 16 | (uint32_t)bytes[3] << 24;
}

static int canonical_name(const uint8_t *name, size_t size)
{
	size_t i;
	if (!size || size > 15) return 0;
	for (i = 0; i < size; i++) {
		uint8_t c = name[i];
		if (!((c >= 'a' && c <= 'z') || (c >= '0' && c <= '9') ||
			c == '_' || c == '-'))
			return 0;
	}
	return 1;
}

int hmap_open(hmap_identity *identity, const void *data, size_t size,
	const char *expected_map_name)
{
	const uint8_t *bytes = (const uint8_t *)data;
	const uint8_t *name;
	size_t name_length = 0, expected_length = 0, i;
	uint32_t file_length, tag_offset, tag_size;
	if (!identity || !bytes || size != HMAP_SIZE ||
		memcmp(bytes, "HMAP", 4) != 0 || read_u32(bytes + 4) != 1 ||
		read_u32(bytes + 8) != HMAP_SIZE)
		return 0;
	file_length = read_u32(bytes + 12);
	tag_offset = read_u32(bytes + 16);
	tag_size = read_u32(bytes + 20);
	if (!file_length || !tag_size || tag_offset > file_length ||
		tag_size > file_length - tag_offset)
		return 0;
	name = bytes + 56;
	while (name_length < 16 && name[name_length]) name_length++;
	if (name_length == 16 || !canonical_name(name, name_length)) return 0;
	for (i = name_length; i < 16; i++) if (name[i] != 0) return 0;
	if (expected_map_name) {
		expected_length = strlen(expected_map_name);
		if (expected_length != name_length ||
			memcmp(name, expected_map_name, name_length) != 0)
			return 0;
	}
	memset(identity, 0, sizeof(*identity));
	memcpy(identity->map_name, name, name_length);
	identity->file_length = file_length;
	identity->tag_data_offset = tag_offset;
	identity->tag_data_size = tag_size;
	memcpy(identity->source_sha256, bytes + 24,
		sizeof(identity->source_sha256));
	return 1;
}
