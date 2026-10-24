#include "ps2_ctag.h"

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
	data = malloc(length ? (size_t)length : 1);
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
	ps2_ctag_view view;
	ps2_ctag_status status;
	size_t payload_size = 0, expected_size = 0;
	uint8_t *payload, *expected, *materialized;
	if (argc != 3) return 2;
	payload = read_file(argv[1], &payload_size);
	expected = read_file(argv[2], &expected_size);
	if (!payload || !expected) { free(payload); free(expected); return 3; }
	status = ps2_ctag_open(&view, payload, payload_size,
		32u * 1024u * 1024u, 1000000u);
	if (status != PS2_CTAG_OK) { free(payload); free(expected); return 4 + (int)status; }
	{
		ps2_ctag_view split_view;
		uint32_t image_size = (uint32_t)payload[12] |
			((uint32_t)payload[13] << 8) | ((uint32_t)payload[14] << 16) |
			((uint32_t)payload[15] << 24);
		uint32_t relocation_count = (uint32_t)payload[16] |
			((uint32_t)payload[17] << 8) | ((uint32_t)payload[18] << 16) |
			((uint32_t)payload[19] << 24);
		if (ps2_ctag_open_parts(&split_view, payload, 52,
			payload + 52, image_size, payload + 52 + image_size,
			(size_t)relocation_count * 4u, 32u * 1024u * 1024u,
			1000000u) != PS2_CTAG_OK ||
			split_view.image != view.image ||
			split_view.relocations != view.relocations ||
			split_view.image_size != view.image_size ||
			split_view.relocation_count != view.relocation_count ||
			split_view.scenario_tag_index != view.scenario_tag_index ||
			ps2_ctag_open_parts(&split_view, payload, 52,
				payload + 52, image_size - 1u,
				payload + 52 + image_size, (size_t)relocation_count * 4u,
				32u * 1024u * 1024u, 1000000u) == PS2_CTAG_OK) {
			free(payload); free(expected); return 27;
		}
	}
	materialized = malloc(expected_size ? expected_size : 1);
	if (!materialized) { free(payload); free(expected); return 20; }
	if (view.image_size != expected_size ||
		ps2_ctag_materialize(&view, 0x00100000u, materialized, expected_size) != PS2_CTAG_OK ||
		memcmp(materialized, expected, expected_size) != 0) {
		free(materialized); free(payload); free(expected); return 21;
	}
	{
		ps2_ctag_view staged = view;
		uint8_t *image_copy = malloc(view.image_size);
		uint8_t *before = malloc(view.image_size);
		uint32_t field;
		if (!image_copy || !before) {
			free(image_copy); free(before); free(materialized);
			free(payload); free(expected); return 28;
		}
		memcpy(image_copy, view.image, view.image_size);
		staged.image = image_copy;
		if (ps2_ctag_rebase_in_place(&staged, 0x00100000u, image_copy,
			view.image_size) != PS2_CTAG_OK ||
			memcmp(image_copy, expected, expected_size) != 0) {
			free(image_copy); free(before); free(materialized);
			free(payload); free(expected); return 29;
		}
		memcpy(image_copy, view.image, view.image_size);
		field = (uint32_t)view.relocations[view.relocation_count * 4u - 4u] |
			((uint32_t)view.relocations[view.relocation_count * 4u - 3u] << 8) |
			((uint32_t)view.relocations[view.relocation_count * 4u - 2u] << 16) |
			((uint32_t)view.relocations[view.relocation_count * 4u - 1u] << 24);
		memset(image_copy + field, 0xFF, 4);
		memcpy(before, image_copy, view.image_size);
		if (ps2_ctag_rebase_in_place(&staged, 0x00100000u, image_copy,
			view.image_size) != PS2_CTAG_ERR_BOUNDS ||
			memcmp(image_copy, before, view.image_size) != 0) {
			free(image_copy); free(before); free(materialized);
			free(payload); free(expected); return 30;
		}
		free(image_copy); free(before);
	}
	if (ps2_ctag_materialize(&view, 0x00100000u, materialized, expected_size - 1) != PS2_CTAG_ERR_SPACE ||
		ps2_ctag_materialize(&view, 0, materialized, expected_size) != PS2_CTAG_ERR_ADDRESS) {
		free(materialized); free(payload); free(expected); return 22;
	}
	{
		uint8_t *payload_before = malloc(payload_size);
		if (!payload_before) {
			free(materialized); free(payload); free(expected); return 23;
		}
		memcpy(payload_before, payload, payload_size);
		if (ps2_ctag_materialize(&view, 0x00100000u,
			(uint8_t *)view.image, expected_size) != PS2_CTAG_ERR_OVERLAP ||
			memcmp(payload, payload_before, payload_size) != 0) {
			free(payload_before); free(materialized); free(payload); free(expected);
			return 24;
		}
		free(payload_before);
	}
	{
		ps2_ctag_view malformed = view;
		uint8_t *before = malloc(expected_size ? expected_size : 1);
		uint32_t field, saved;
		if (!before) {
			free(materialized); free(payload); free(expected); return 25;
		}
		memset(materialized, 0xA5, expected_size);
		memcpy(before, materialized, expected_size);
		field = ((uint32_t)view.relocations[view.relocation_count * 4u - 4u]) |
			((uint32_t)view.relocations[view.relocation_count * 4u - 3u] << 8) |
			((uint32_t)view.relocations[view.relocation_count * 4u - 2u] << 16) |
			((uint32_t)view.relocations[view.relocation_count * 4u - 1u] << 24);
		saved = ((uint32_t)view.image[field]) |
			((uint32_t)view.image[field + 1u] << 8) |
			((uint32_t)view.image[field + 2u] << 16) |
			((uint32_t)view.image[field + 3u] << 24);
		/* The final fixup field is valid but its target is outside the image.
		 * The late error must be rejected before even the initial memcpy. */
		((uint8_t *)view.image)[field] = 0xFF;
		((uint8_t *)view.image)[field + 1u] = 0xFF;
		((uint8_t *)view.image)[field + 2u] = 0xFF;
		((uint8_t *)view.image)[field + 3u] = 0xFF;
		if (ps2_ctag_materialize(&malformed, 0x00100000u, materialized,
			expected_size) != PS2_CTAG_ERR_BOUNDS ||
			memcmp(materialized, before, expected_size) != 0) {
			free(before); free(materialized); free(payload); free(expected);
			return 26;
		}
		((uint8_t *)view.image)[field] = (uint8_t)saved;
		((uint8_t *)view.image)[field + 1u] = (uint8_t)(saved >> 8);
		((uint8_t *)view.image)[field + 2u] = (uint8_t)(saved >> 16);
		((uint8_t *)view.image)[field + 3u] = (uint8_t)(saved >> 24);
		free(before);
	}
	{
		ps2_ctag_view undersized;
		uint8_t tiny_image[3] = { 0, 0, 0 };
		uint8_t tiny_relocations[4] = { 0, 0, 0, 0 };
		uint8_t destination[3] = { 0xA5, 0xA5, 0xA5 };
		memset(&undersized, 0, sizeof(undersized));
		undersized.image = tiny_image;
		undersized.relocations = tiny_relocations;
		undersized.image_size = sizeof(tiny_image);
		undersized.relocation_count = 1;
		if (ps2_ctag_materialize(&undersized, 0x00100000u, destination,
			sizeof(destination)) != PS2_CTAG_ERR_BOUNDS ||
			destination[0] != 0xA5 || destination[1] != 0xA5 ||
			destination[2] != 0xA5) {
			free(materialized); free(payload); free(expected); return 31;
		}
	}
	free(materialized); free(payload); free(expected);
	return 0;
}
