#ifndef HALO_HCU_MAP_CATALOG_H
#define HALO_HCU_MAP_CATALOG_H

#include "stream/hmap.h"

#include <stddef.h>
#include <stdint.h>

typedef struct {
	uint32_t file_offset;
	uint32_t file_size;
	char section_tag[5];
	const char *scenario_bsp_path;
} hcu_map_bsp_entry;

typedef struct {
	hmap_identity identity;
	const char *scenario_name;
	const char *hp2_path;
	const char *map_path;
	const hcu_map_bsp_entry *bsp_catalog;
	uint16_t bsp_count;
} hcu_map_catalog_entry;

/* Exact stock retail CE map catalog. Accepts a canonical scenario path or
 * the exact cache-map leaf; names are never synthesized from caller input. */
size_t hcu_map_catalog_count(void);
const hcu_map_catalog_entry *hcu_map_catalog_at(size_t index);
const hcu_map_catalog_entry *hcu_map_catalog_find(const char *map_name);

/* Validate package metadata against the pinned source identity, not merely
 * against the self-consistency of the HMAP record. */
int hcu_map_catalog_validate_hmap(const hcu_map_catalog_entry *entry,
	const void *bytes, size_t size, hmap_identity *identity_out);

/* Require the packaged CBIX to contain every exact BSP source extent and
 * HP2 section tag in the pinned catalog, with no extras. */
int hcu_map_catalog_validate_bsp_catalog(
	const hcu_map_catalog_entry *entry, const void *bytes, size_t size);

#endif
