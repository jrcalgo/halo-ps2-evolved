#include "stream/cbsp_catalog.h"
#include "stream/ctag_resource_index.h"
#include "stream/hcu_map_catalog.h"
#include "stream/hp2.h"
#include "ps2_ctag.h"
#include "ps2_cbsp.h"

#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static uint8_t *read_file(const char *path, size_t *size_out)
{
	FILE *file = fopen(path, "rb");
	long length;
	uint8_t *bytes;
	assert(file);
	assert(fseek(file, 0, SEEK_END) == 0);
	length = ftell(file);
	assert(length > 0);
	assert(fseek(file, 0, SEEK_SET) == 0);
	bytes = (uint8_t *)malloc((size_t)length);
	assert(bytes);
	assert(fread(bytes, 1, (size_t)length, file) == (size_t)length);
	assert(fclose(file) == 0);
	*size_out = (size_t)length;
	return bytes;
}

static uint8_t *load_section(const hp2_pack *pack, const char *tag,
	size_t *size_out)
{
	const hp2_section *section = hp2_find(pack, tag);
	uint8_t *bytes;
	assert(section && section->raw_size > 0);
	bytes = (uint8_t *)malloc(section->raw_size);
	assert(bytes);
	assert(hp2_load(pack, section, bytes, section->raw_size) == HP2_OK);
	*size_out = section->raw_size;
	return bytes;
}

static uint32_t read_u32(const uint8_t *bytes)
{
	return (uint32_t)bytes[0] | (uint32_t)bytes[1] << 8 |
		(uint32_t)bytes[2] << 16 | (uint32_t)bytes[3] << 24;
}

static unsigned resource_read_calls;

static int resource_source_read(void *context, int32_t tag_index,
	uint32_t offset, uint32_t size, void *buffer, int blocking)
{
	uint32_t i;
	(void)context;
	assert(tag_index == 7 && blocking == 1 && size > 0);
	resource_read_calls++;
	for (i = 0; i < size; i++) ((uint8_t *)buffer)[i] = (uint8_t)(offset + i);
	return 1;
}

static void verify_resource_boundaries(const ctag_resource_index *resources)
{
	uint32_t start, length, end;
	uint8_t byte;
	assert(resources->interval_count > 0);
	start = read_u32(resources->bytes + 36u);
	length = read_u32(resources->bytes + 40u);
	assert(length > 0 && start <= resources->file_length &&
		length <= resources->file_length - start);
	end = start + length;
	assert(ctag_resource_index_allows(resources, start, length));
	assert(ctag_resource_index_allows(resources, end - 1u, 1u));
	assert(!ctag_resource_index_allows(resources, end - 1u, 2u));
	assert(!ctag_resource_index_allows(resources, start, 0u));
	assert(!ctag_resource_index_allows(resources,
		resources->file_length, 1u));
	assert(!ctag_resource_index_overlaps(resources,
		resources->tag_data_offset, 1u));
	resource_read_calls = 0;
	assert(ctag_resource_index_read(resources, resource_source_read, NULL,
		7, end - 1u, 1u, &byte, 1));
	assert(resource_read_calls == 1u);
	assert(!ctag_resource_index_read(resources, resource_source_read, NULL,
		7, end - 1u, 2u, &byte, 1));
	assert(!ctag_resource_index_read(resources, resource_source_read, NULL,
		7, resources->tag_data_offset, 1u, &byte, 1));
	assert(resource_read_calls == 1u);
}

static uint8_t ascii_fold(uint8_t value)
{
	return value >= 'A' && value <= 'Z' ? (uint8_t)(value + ('a' - 'A')) : value;
}

static int ascii_case_equal(const char *left, const char *right)
{
	while (*left && *right) {
		if (ascii_fold((uint8_t)*left) != ascii_fold((uint8_t)*right))
			return 0;
		left++;
		right++;
	}
	return *left == *right;
}

static void verify_scenario_tag(const hp2_pack *pack,
	const hcu_map_catalog_entry *entry, const cbsp_catalog *catalog)
{
	uint8_t *payload;
	size_t payload_size;
	ps2_ctag_view view;
	uint32_t table_offset, tag_index, name_offset, index, scenario_root;
	const uint8_t *instance;
	const hp2_section *section;
	size_t expected_name_size = strlen(entry->scenario_name);

	payload = load_section(pack, "CTAG", &payload_size);
	section = hp2_find(pack, "CTAG");
	assert(section);
	assert(ps2_ctag_open(&view, payload, payload_size, payload_size,
		(uint32_t)(payload_size / 4u)) == PS2_CTAG_OK);
	index = view.scenario_tag_index & 0xFFFFu;
	assert(index < read_u32(view.image + 12));
	table_offset = read_u32(view.image);
	assert(table_offset <= view.image_size &&
		32u <= view.image_size - table_offset &&
		index <= (view.image_size - table_offset) / 32u - 1u);
	instance = view.image + table_offset + (size_t)index * 32u;
	tag_index = read_u32(instance + 12);
	assert(tag_index == view.scenario_tag_index);
	assert(read_u32(instance) == 0x73636e72u); /* 'scnr' */
	name_offset = read_u32(instance + 16);
	assert(name_offset < view.image_size &&
		expected_name_size < view.image_size - name_offset &&
		view.image[name_offset + expected_name_size] == 0);
	assert(memcmp(view.image + name_offset, entry->scenario_name,
		expected_name_size) == 0);
	/* CE's schema places scenario.structure_bsp_references at +0x5A4;
	 * the referenced record is 0x20 bytes (scenario_definitions.h). */
	scenario_root = read_u32(instance + 20);
	assert(scenario_root <= view.image_size &&
		0x5B0u <= view.image_size - scenario_root);
	{
		int32_t count = (int32_t)read_u32(view.image + scenario_root + 0x5A4u);
		uint32_t references = read_u32(view.image + scenario_root + 0x5A8u);
		uint32_t tag_count = read_u32(view.image + 12u);
		assert(count >= 0 && count <= 32 &&
			(uint16_t)count == entry->bsp_count);
		assert(references <= view.image_size &&
			(uint32_t)count <= (view.image_size - references) / 0x20u);
		for (index = 0; index < (uint32_t)count; index++) {
			const hcu_map_bsp_entry *expected = &entry->bsp_catalog[index];
			cbsp_catalog_entry actual;
			uint32_t ref = references + index * 0x20u;
			uint32_t ref_name = read_u32(view.image + ref + 20u);
			uint32_t datum = read_u32(view.image + ref + 28u);
			uint32_t datum_index = datum & 0xFFFFu;
			uint32_t datum_instance;
			size_t path_size = strlen(expected->scenario_bsp_path);
			size_t path_end;
			char expected_section[5];
			assert(read_u32(view.image + ref) == expected->file_offset);
			assert(read_u32(view.image + ref + 4u) == expected->file_size);
			assert(memcmp(view.image + ref + 16u, "psbs", 4) == 0);
			assert(ref_name < view.image_size);
			path_end = ref_name;
			while (path_end < view.image_size && path_end - ref_name < 256u &&
				view.image[path_end] != 0) path_end++;
			assert(path_end < view.image_size && path_end - ref_name < 256u);
			assert(path_end - ref_name == path_size);
			assert(memcmp(view.image + ref_name, expected->scenario_bsp_path,
				path_size) == 0);
			assert(datum_index < tag_count);
			datum_instance = table_offset + datum_index * 32u;
			assert(read_u32(view.image + datum_instance + 12u) == datum);
			assert(memcmp(view.image + datum_instance, "psbs", 4) == 0);
			name_offset = read_u32(view.image + datum_instance + 16u);
			assert(name_offset == ref_name);
			assert(cbsp_catalog_find(catalog, expected->file_offset,
				expected->file_size, &actual));
			assert(strcmp(actual.section_tag, expected->section_tag) == 0);
			expected_section[0] = 'B';
			expected_section[1] = (char)('0' + (index / 100u));
			expected_section[2] = (char)('0' + ((index / 10u) % 10u));
			expected_section[3] = (char)('0' + (index % 10u));
			expected_section[4] = '\0';
			assert(strcmp(actual.section_tag, expected_section) == 0);
		}
	}
	free(payload);
}

static void verify_map(const char *package_root,
	const hcu_map_catalog_entry *entry, size_t *bsp_total)
{
	char path[1024];
	uint8_t *image, *hmap, *crng, *cbix;
	size_t image_size, hmap_size, crng_size, cbix_size;
	hp2_pack pack;
	hmap_identity parsed_identity;
	ctag_resource_index resources;
	cbsp_catalog catalog;
	uint16_t i;
	int written;

	written = snprintf(path, sizeof path, "%s/%s.hp2", package_root,
		entry->identity.map_name);
	assert(written > 0 && (size_t)written < sizeof path);
	image = read_file(path, &image_size);
	assert(hp2_open(&pack, image, image_size) == HP2_OK);
	assert(strcmp(pack.name, entry->identity.map_name) == 0);
	hmap = load_section(&pack, "HMAP", &hmap_size);
	assert(hmap_size == 72u);
	assert(hcu_map_catalog_validate_hmap(entry, hmap, hmap_size,
		&parsed_identity));
	crng = load_section(&pack, "CRNG", &crng_size);
	assert(ctag_resource_index_open(&resources, crng, crng_size,
		entry->identity.file_length, entry->identity.tag_data_offset,
		entry->identity.tag_data_size));
	verify_resource_boundaries(&resources);
	cbix = load_section(&pack, "CBIX", &cbix_size);
	assert(hcu_map_catalog_validate_bsp_catalog(entry, cbix, cbix_size));
	assert(cbsp_catalog_open(&catalog, cbix, cbix_size,
		entry->identity.file_length));
	assert(catalog.count == entry->bsp_count);
	verify_scenario_tag(&pack, entry, &catalog);
	for (i = 0; i < entry->bsp_count; i++) {
		const hcu_map_bsp_entry *expected = &entry->bsp_catalog[i];
		cbsp_catalog_entry actual;
		const hp2_section *section;
		uint8_t *payload;
		size_t payload_size;
		ps2_cbsp_view view;
		assert(cbsp_catalog_find(&catalog, expected->file_offset,
			expected->file_size, &actual));
		assert(memcmp(actual.section_tag, expected->section_tag, 4) == 0);
		section = hp2_find(&pack, expected->section_tag);
		assert(section);
		payload = load_section(&pack, expected->section_tag, &payload_size);
		assert(ps2_cbsp_open(&view, payload, payload_size, payload_size,
			(uint32_t)(payload_size / 12u)) == PS2_CBSP_OK);
		assert(view.source_file_offset == expected->file_offset);
		assert(view.source_file_size == expected->file_size);
		assert(view.image_size == expected->file_size);
		free(payload);
	}
	*bsp_total += entry->bsp_count;
	free(cbix);
	free(crng);
	free(hmap);
	free(image);
}

int main(int argc, char **argv)
{
	const char *package_root;
	size_t bsp_total = 0;
	size_t index;
	assert(argc == 2);
	package_root = argv[1];
	assert(hcu_map_catalog_count() == 24u);
	for (index = 0; index < hcu_map_catalog_count(); index++) {
		const hcu_map_catalog_entry *entry = hcu_map_catalog_at(index);
		size_t prior;
		assert(entry);
		for (prior = 0; prior < index; prior++) {
			const hcu_map_catalog_entry *prior_entry =
				hcu_map_catalog_at(prior);
			assert(strcmp(entry->identity.map_name,
				prior_entry->identity.map_name) != 0);
			assert(!ascii_case_equal(entry->map_path, prior_entry->map_path));
			assert(!ascii_case_equal(entry->hp2_path, prior_entry->hp2_path));
			assert(!ascii_case_equal(entry->scenario_name,
				prior_entry->scenario_name));
		}
		verify_map(package_root, entry, &bsp_total);
	}
	assert(bsp_total == 82u);
	printf("package-matrix maps=24 scenario=24/24 scenario-bsp-refs=%lu/82 hmap=24/24 crng=24/24 cbix=24/24 cbsp=%lu/82\n",
		(unsigned long)bsp_total,
		(unsigned long)bsp_total);
	return 0;
}
