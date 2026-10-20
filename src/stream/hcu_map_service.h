#ifndef HALO_HCU_MAP_SERVICE_H
#define HALO_HCU_MAP_SERVICE_H

#include "core/mem.h"
#include "stream/ctag_map_source.h"

typedef struct {
	arena_t *map_arena;
	arena_t *section_scratch;
	ctag_mount mount;
	ctag_map_source source;
	hmap_identity identity;
	const ctag_mount_backend *backend;
	char staged_map[16];
	int preflight_ready;
	int initialized;
} hcu_map_service;

/* Register the parent-owned loader/unloader after FileXio is initialized.
 * v1 catalog support is intentionally UI bootstrap only; other names fail
 * closed until their capacity and BSP catalogs pass the M2 gates. */
int hcu_map_service_init(hcu_map_service *service,
	mem_layout_v2_t *layout, const char *asset_root);
/* Non-mutating map preflight; caller invokes before unloading the old scenario. */
int hcu_map_service_preflight(const char *map_name);
void hcu_map_service_shutdown(hcu_map_service *service);

#endif
