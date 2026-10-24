#include "ps2_cbsp.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static uint8_t *read_file(const char *path, size_t *size)
{
	FILE *file = fopen(path, "rb");
	long length;
	uint8_t *data;
	if (!file || fseek(file, 0, SEEK_END) != 0) { if (file) fclose(file); return NULL; }
	length = ftell(file);
	if (length < 0 || fseek(file, 0, SEEK_SET) != 0) { fclose(file); return NULL; }
	data = (uint8_t *)malloc(length ? (size_t)length : 1);
	if (!data) { fclose(file); return NULL; }
	if (fread(data, 1, (size_t)length, file) != (size_t)length) {
		free(data); fclose(file); return NULL;
	}
	fclose(file);
	*size = (size_t)length;
	return data;
}

int main(int argc, char **argv)
{
	ps2_cbsp_view view;
	ps2_cbsp_status status;
	size_t payload_size = 0, expected_size = 0;
	uint8_t *payload, *expected, *materialized;
	uint8_t *staged, *bad_table;
	if (argc == 7)
	{
		unsigned long bsp_base, tag_base, maximum_image_size;
		char *end;
		size_t tag_image_size = 0;
		size_t table_bytes;
		uint8_t *tag_image;
		uint8_t *staged;
		ps2_cbsp_view parts_view;
		payload = read_file(argv[1], &payload_size);
		expected = read_file(argv[2], &expected_size);
		tag_image = read_file(argv[5], &tag_image_size);
		if (!payload || !expected || !tag_image) {
			free(payload); free(expected); free(tag_image); return 3;
		}
		bsp_base = strtoul(argv[3], &end, 0);
		if (*end) { free(payload); free(expected); free(tag_image); return 23; }
		tag_base = strtoul(argv[4], &end, 0);
		if (*end) { free(payload); free(expected); free(tag_image); return 24; }
		maximum_image_size = strtoul(argv[6], &end, 0);
		if (*end) { free(payload); free(expected); free(tag_image); return 26; }
		status = ps2_cbsp_open(&view, payload, payload_size,
			(size_t)maximum_image_size, 1000000u);
		if (status != PS2_CBSP_OK) {
			free(payload); free(expected); free(tag_image); return 4 + (int)status;
		}
		materialized = (uint8_t *)malloc(expected_size ? expected_size : 1);
		if (!materialized) {
			free(payload); free(expected); free(tag_image); return 20;
		}
		if (view.image_size != expected_size ||
			ps2_cbsp_materialize(&view, (uint32_t)bsp_base, (uint32_t)tag_base,
				tag_image, tag_image_size, materialized, expected_size) != PS2_CBSP_OK ||
			memcmp(materialized, expected, expected_size) != 0) {
			free(materialized); free(payload); free(expected); free(tag_image); return 21;
		}
		table_bytes = (size_t)view.relocation_count * 12u;
		staged = (uint8_t *)malloc(view.image_size);
		if (!staged) {
			free(materialized); free(payload); free(expected); free(tag_image); return 33;
		}
		memcpy(staged, view.image, view.image_size);
		if (ps2_cbsp_open_parts(&parts_view, payload, 36u, staged,
			view.image_size, view.relocations, table_bytes,
			(size_t)maximum_image_size, 1000000u) != PS2_CBSP_OK ||
			parts_view.payload != NULL ||
			ps2_cbsp_rebase_in_place(&parts_view, (uint32_t)bsp_base,
				(uint32_t)tag_base, tag_image, tag_image_size, staged,
				view.image_size) != PS2_CBSP_OK ||
			memcmp(staged, expected, expected_size) != 0) {
			free(staged); free(materialized); free(payload); free(expected); free(tag_image); return 34;
		}
		free(staged); free(materialized); free(payload); free(expected); free(tag_image);
		return 0;
	}
	if (argc != 3) return 2;
	{
		uint8_t tag_image[256] = {0};
		uint8_t bad_tag_image[256];
		ps2_cbsp_view parts_view;
		size_t i, table_bytes;
	payload = read_file(argv[1], &payload_size);
	expected = read_file(argv[2], &expected_size);
	if (!payload || !expected) { free(payload); free(expected); return 3; }
	status = ps2_cbsp_open(&view, payload, payload_size, 4096, 1000000u);
	if (status != PS2_CBSP_OK) { free(payload); free(expected); return 4 + (int)status; }
	if (view.source_file_offset != 2048u || view.source_file_size != view.image_size) {
		free(payload); free(expected); return 19;
	}
	materialized = (uint8_t *)malloc(expected_size ? expected_size : 1);
	if (!materialized) { free(payload); free(expected); return 20; }
	if (view.image_size != expected_size ||
		ps2_cbsp_materialize(&view, 0x02000000u, 0x01400000u,
			tag_image, sizeof(tag_image),
			materialized, expected_size) != PS2_CBSP_OK ||
		memcmp(materialized, expected, expected_size) != 0) {
		free(materialized); free(payload); free(expected); return 21;
	}
	table_bytes = (size_t)view.relocation_count * 12u;
	staged = (uint8_t *)malloc(view.image_size);
	bad_table = (uint8_t *)malloc(table_bytes ? table_bytes : 1u);
	if (!staged || !bad_table) {
		free(staged); free(bad_table); free(materialized); free(payload); free(expected); return 28;
	}
	memcpy(staged, view.image, view.image_size);
	memcpy(bad_table, view.relocations, table_bytes);
	if (ps2_cbsp_open_parts(&parts_view, payload, 36u, staged,
		view.image_size, view.relocations, table_bytes, 4096,
		1000000u) != PS2_CBSP_OK || parts_view.payload != NULL ||
		ps2_cbsp_rebase_in_place(&parts_view, 0x02000000u, 0x01400000u,
			tag_image, sizeof(tag_image), staged, view.image_size) != PS2_CBSP_OK ||
		memcmp(staged, expected, expected_size) != 0) {
		free(staged); free(bad_table); free(materialized); free(payload); free(expected); return 29;
	}
	memcpy(staged, view.image, view.image_size);
	memcpy(bad_table, view.relocations, table_bytes);
	if (ps2_cbsp_open_parts(&parts_view, payload, 36u, staged,
		view.image_size, view.relocations, table_bytes, 4096,
		1000000u) != PS2_CBSP_OK) {
		free(staged); free(bad_table); free(materialized); free(payload); free(expected); return 36;
	}
	bad_table[table_bytes - 12u] = (uint8_t)view.image_size;
	bad_table[table_bytes - 11u] = (uint8_t)(view.image_size >> 8);
	bad_table[table_bytes - 10u] = (uint8_t)(view.image_size >> 16);
	bad_table[table_bytes - 9u] = (uint8_t)(view.image_size >> 24);
	parts_view.relocations = bad_table;
	if (ps2_cbsp_rebase_in_place(&parts_view, 0x02000000u, 0x01400000u,
		tag_image, sizeof(tag_image), staged, view.image_size) !=
		PS2_CBSP_ERR_BOUNDS || memcmp(staged, view.image, view.image_size) != 0) {
		free(staged); free(bad_table); free(materialized); free(payload); free(expected); return 37;
	}
	memcpy(staged, view.image, view.image_size);
	for (i = 0; i < sizeof(bad_tag_image); i++) bad_tag_image[i] = 'x';
	if (ps2_cbsp_open_parts(&parts_view, payload, 36u, staged,
		view.image_size, view.relocations, table_bytes, 4096,
		1000000u) != PS2_CBSP_OK ||
		ps2_cbsp_rebase_in_place(&parts_view, 0x02000000u, 0x01400000u,
			bad_tag_image, sizeof(bad_tag_image), staged,
			view.image_size) != PS2_CBSP_ERR_BOUNDS ||
		memcmp(staged, view.image, view.image_size) != 0) {
		free(staged); free(bad_table); free(materialized); free(payload); free(expected); return 30;
	}
	/* Corrupt only the final relocation field offset. Parsing must reject it
	 * before the staged destination can be rebased or otherwise modified. */
	if (!table_bytes) {
		free(staged); free(bad_table); free(materialized); free(payload); free(expected); return 31;
	}
	memcpy(bad_table, view.relocations, table_bytes);
	bad_table[table_bytes - 12u] = (uint8_t)view.image_size;
	bad_table[table_bytes - 11u] = (uint8_t)(view.image_size >> 8);
	bad_table[table_bytes - 10u] = (uint8_t)(view.image_size >> 16);
	bad_table[table_bytes - 9u] = (uint8_t)(view.image_size >> 24);
	memcpy(staged, view.image, view.image_size);
	if (ps2_cbsp_open_parts(&parts_view, payload, 36u, staged,
		view.image_size, bad_table, table_bytes, 4096,
		1000000u) != PS2_CBSP_ERR_BOUNDS ||
		memcmp(staged, view.image, view.image_size) != 0) {
		free(staged); free(bad_table); free(materialized); free(payload); free(expected); return 32;
	}
	if (ps2_cbsp_open_parts(&parts_view, payload, 36u, staged,
		view.image_size, staged, table_bytes, 4096,
		1000000u) != PS2_CBSP_ERR_OVERLAP ||
		memcmp(staged, view.image, view.image_size) != 0) {
		free(staged); free(bad_table); free(materialized); free(payload); free(expected); return 35;
	}
	if (ps2_cbsp_materialize(&view, 0x02000000u, 0x01400000u,
		tag_image, sizeof(tag_image),
		materialized, expected_size - 1) != PS2_CBSP_ERR_SPACE ||
		ps2_cbsp_materialize(&view, 0, 0x01400000u,
			tag_image, sizeof(tag_image),
			materialized, expected_size) != PS2_CBSP_ERR_ADDRESS ||
		ps2_cbsp_materialize(&view, 0x02000001u, 0x01400000u,
			tag_image, sizeof(tag_image),
			materialized, expected_size) != PS2_CBSP_ERR_ADDRESS ||
		ps2_cbsp_materialize(&view, 0x01400000u, 0x01400010u,
			tag_image, sizeof(tag_image),
			materialized, expected_size) != PS2_CBSP_ERR_ADDRESS ||
		ps2_cbsp_materialize(&view, 0x02000000u, 0x01400000u,
			tag_image, 128,
			materialized, expected_size) != PS2_CBSP_ERR_BOUNDS) {
		free(materialized); free(payload); free(expected); return 22;
	}
	for (i = 0; i < sizeof(bad_tag_image); i++) bad_tag_image[i] = 'x';
	memset(materialized, 0xA5, expected_size);
	if (ps2_cbsp_materialize(&view, 0x02000000u, 0x01400000u,
		bad_tag_image, sizeof(bad_tag_image), materialized,
		expected_size) != PS2_CBSP_ERR_BOUNDS || materialized[0] != 0xA5) {
		free(materialized); free(payload); free(expected); return 27;
	}
	free(staged); free(bad_table); free(materialized); free(payload); free(expected);
	}
	return 0;
}
