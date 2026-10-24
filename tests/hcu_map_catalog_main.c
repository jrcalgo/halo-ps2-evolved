#include "stream/hcu_map_catalog.h"

#include "stream/cbsp_catalog.h"
#include "stream/hp2.h"

#include <assert.h>
#include <stdint.h>
#include <string.h>

static void write_u32(uint8_t *bytes, uint32_t value)
{
	bytes[0] = (uint8_t)value;
	bytes[1] = (uint8_t)(value >> 8);
	bytes[2] = (uint8_t)(value >> 16);
	bytes[3] = (uint8_t)(value >> 24);
}

static void make_hmap(const hcu_map_catalog_entry *entry, uint8_t bytes[72])
{
	memset(bytes, 0, 72);
	memcpy(bytes, "HMAP", 4);
	write_u32(bytes + 4, 1);
	write_u32(bytes + 8, 72);
	write_u32(bytes + 12, entry->identity.file_length);
	write_u32(bytes + 16, entry->identity.tag_data_offset);
	write_u32(bytes + 20, entry->identity.tag_data_size);
	memcpy(bytes + 24, entry->identity.source_sha256, 32);
	memcpy(bytes + 56, entry->identity.map_name,
		strlen(entry->identity.map_name));
}

static size_t make_cbix(const hcu_map_catalog_entry *entry,
	uint8_t bytes[28 + 32 * 16])
{
	uint32_t i;
	size_t size = 28u + (size_t)entry->bsp_count * 16u;
	memset(bytes, 0, size);
	memcpy(bytes, "CBIX", 4);
	write_u32(bytes + 4, 1);
	write_u32(bytes + 8, entry->bsp_count);
	write_u32(bytes + 12, entry->identity.file_length);
	write_u32(bytes + 16, 28);
	for (i = 0; i < entry->bsp_count; i++) {
		const hcu_map_bsp_entry *bsp = &entry->bsp_catalog[i];
		uint8_t *row = bytes + 28u + (size_t)i * 16u;
		write_u32(row, bsp->file_offset);
		write_u32(row + 4, bsp->file_size);
		memcpy(row + 8, bsp->section_tag, 4);
	}
	write_u32(bytes + 20, hp2_crc32(bytes + 28, size - 28));
	return size;
}

int main(void)
{
	const hcu_map_catalog_entry *ui, *bloodgulch;
	uint8_t hmap[72], cbix[28 + 32 * 16];
	size_t i, cbix_size;
	assert(hcu_map_catalog_count() == 24);
	ui = hcu_map_catalog_find("levels\\ui\\ui");
	assert(ui && ui == hcu_map_catalog_find("levels/ui/ui"));
	assert(ui == hcu_map_catalog_find("ui"));
	assert(strcmp(ui->hp2_path, "maps/ui.hp2") == 0);
	assert(strcmp(ui->map_path, "maps/ui.map") == 0);
	assert(strcmp(ui->scenario_name, "levels\\ui\\ui") == 0);
	assert(hcu_map_catalog_find("levels\\ui\\unknown") == NULL);
	assert(hcu_map_catalog_find("../ui") == NULL);
	assert(hcu_map_catalog_find("not-a-retail-map") == NULL);

	for (i = 0; i < hcu_map_catalog_count(); i++) {
		const hcu_map_catalog_entry *entry = hcu_map_catalog_at(i);
		assert(entry && entry->identity.file_length > 0);
		assert(entry->identity.tag_data_size > 0);
		assert(entry->identity.tag_data_offset <= entry->identity.file_length);
		assert(entry->identity.tag_data_size <= entry->identity.file_length -
			entry->identity.tag_data_offset);
		assert(entry->bsp_count > 0 && entry->bsp_count <= 32);
		make_hmap(entry, hmap);
		assert(hcu_map_catalog_validate_hmap(entry, hmap, sizeof(hmap), NULL));
		cbix_size = make_cbix(entry, cbix);
		assert(hcu_map_catalog_validate_bsp_catalog(entry, cbix, cbix_size));
	}

	make_hmap(ui, hmap);
	hmap[24] ^= 0x80;
	assert(!hcu_map_catalog_validate_hmap(ui, hmap, sizeof(hmap), NULL));
	make_hmap(ui, hmap);
	hmap[12] ^= 1;
	assert(!hcu_map_catalog_validate_hmap(ui, hmap, sizeof(hmap), NULL));
	assert(!hcu_map_catalog_validate_hmap(ui, hmap, 71, NULL));

	bloodgulch = hcu_map_catalog_find("levels\\test\\bloodgulch\\bloodgulch");
	assert(bloodgulch && strcmp(bloodgulch->identity.map_name, "bloodgulch") == 0);
	cbix_size = make_cbix(bloodgulch, cbix);
	cbix[28 + 8] ^= 1;
	write_u32(cbix + 20, hp2_crc32(cbix + 28, cbix_size - 28));
	assert(!hcu_map_catalog_validate_bsp_catalog(bloodgulch, cbix, cbix_size));
	return 0;
}
