#include "stream/hcu_map_service.h"

#include "cache/physical_memory_map.h"
#include "halo_ps2_cache.h"
#include "ps2_ctag.h"
#include "stream/ctag_ps2_backend.h"
#include "stream/ctag_resource_index.h"

#include <stdio.h>
#include <string.h>

extern uint8_t *world_load_section_with_scratch(arena_t *owner,
	arena_t *scratch, const char *path, const char *tag,
	size_t *raw_size, int optional);

#ifdef HALO_PS2_VERBOSE_BOOT
#define HCU_TRACE(...) printf(__VA_ARGS__)
#else
#define HCU_TRACE(...) ((void)0)
#endif

static hcu_map_service *s_service;

static int verify_source_hash(hcu_map_service *service,
	const uint8_t expected[32])
{
	int result;
	size_t mark, buffer_size;
	uint8_t *buffer;
	if (!service || !service->section_scratch) return 0;
	mark = arena_mark(service->section_scratch);
	buffer_size = arena_free(service->section_scratch);
	if (buffer_size > 262144u) buffer_size = 262144u;
	if (buffer_size < 16384u) {
		printf("HALO_PS2_LOCAL map-preflight sha256-scratch-failed bytes=%u\n",
			(unsigned)buffer_size);
		return 0;
	}
	buffer = (uint8_t *)arena_alloc(service->section_scratch, buffer_size, 64);
	if (!buffer) {
		arena_release(service->section_scratch, mark);
		printf("HALO_PS2_LOCAL map-preflight sha256-scratch-failed bytes=%u\n",
			(unsigned)buffer_size);
		return 0;
	}
	HCU_TRACE("HALO_PS2_LOCAL map-preflight sha256-begin\n");
	result = ctag_map_source_matches_sha256_with_buffer(&service->source,
		expected, buffer, buffer_size);
	arena_release(service->section_scratch, mark);
	HCU_TRACE("HALO_PS2_LOCAL map-preflight sha256-end ok=%d\n", result);
	return result;
}

static int map_leaf(const char *map_name, char leaf[16])
{
	static const char ui_path[] = "levels\\ui\\ui";
	static const char ui_path_slash[] = "levels/ui/ui";
	memset(leaf, 0, 16);
	if (!map_name || (strcmp(map_name, ui_path) != 0 &&
		strcmp(map_name, ui_path_slash) != 0 && strcmp(map_name, "ui") != 0))
		return 0;
	memcpy(leaf, "ui", 3);
	return 1;
}

static uint8_t *load_section(void *context, arena_t *owner,
	const char *path, const char *tag, size_t *size, int optional)
{
	hcu_map_service *service = (hcu_map_service *)context;
	uint8_t *result;
	printf("HALO_PS2_LOCAL map-preflight section-begin %s\n", tag);
	result = world_load_section_with_scratch(owner, service->section_scratch,
		path, tag, size, optional);
	printf("HALO_PS2_LOCAL map-preflight section-end %s bytes=%u ok=%d\n",
		tag, size ? (unsigned)*size : 0u, result != NULL);
	return result;
}

static int map_loader(void *context, const char *map_name)
{
	hcu_map_service *service = (hcu_map_service *)context;
	char leaf[16];
	int result;
	if (!service || !service->initialized || !map_leaf(map_name, leaf) ||
		!service->preflight_ready || strcmp(service->staged_map, leaf) != 0)
		return 0;
	HCU_TRACE("HALO_PS2_LOCAL map-mount begin %s\n", leaf);
	result = ctag_mount_hp2_verified_source_discover(&service->mount,
		service->map_arena, NULL, "maps/ui.hp2", map_name,
		&service->source, &service->identity, service->backend,
		load_section, service);
	printf("HALO_PS2_LOCAL map-mount result=%d active=%d\n",
		result, service->mount.active);
	if (!result) {
		service->preflight_ready = 0;
		service->staged_map[0] = 0;
		return 1;
	}
	ctag_map_source_close(&service->source);
	service->preflight_ready = 0;
	service->staged_map[0] = 0;
	return 0;
}

static int map_preflight(void *context, const char *map_name)
{
	return context == s_service && hcu_map_service_preflight(map_name);
}

static void map_unloader(void *context)
{
	hcu_map_service *service = (hcu_map_service *)context;
	if (!service) return;
	if (service->mount.active)
		ctag_mount_unload(&service->mount);
	else if (service->source.active)
		ctag_map_source_close(&service->source);
	service->preflight_ready = 0;
	service->staged_map[0] = 0;
}

int hcu_map_service_init(hcu_map_service *service,
	mem_layout_v2_t *layout, const char *asset_root)
{
	if (!service || !layout || !asset_root || s_service) return -1;
	memset(service, 0, sizeof(*service));
	service->map_arena = mem_layout_v2_get(layout, MEM_LAYOUT_V2_STREAMING);
	service->section_scratch = mem_layout_v2_get(layout,
		MEM_LAYOUT_V2_FRAME_SCRATCH);
	service->backend = ctag_ps2_cache_backend();
	if (!service->map_arena || !service->section_scratch ||
		!service->map_arena->base || !service->section_scratch->base ||
		!service->backend || !file_set_default_root(asset_root))
		return -1;
	ctag_mount_init(&service->mount);
	service->source.reader.descriptor = -1;
	if (!ps2_cache_set_map_preflight(map_preflight, service) ||
		!ps2_cache_set_map_loader(map_loader, service) ||
		!ps2_cache_set_map_unloader(map_unloader, service)) {
		ps2_cache_set_map_preflight(NULL, NULL);
		ps2_cache_set_map_loader(NULL, NULL);
		ps2_cache_set_map_unloader(NULL, NULL);
		return -1;
	}
	service->initialized = 1;
	s_service = service;
	return 0;
}

int hcu_map_service_preflight(const char *map_name)
{
	hcu_map_service *service = s_service;
	char leaf[16];
	uint8_t *hmap_bytes, *ctag_bytes, *crng_bytes;
	hmap_identity identity;
	ctag_resource_index resource_index;
	ps2_ctag_view ctag_view;
	size_t mark, hmap_size = 0, ctag_size = 0, crng_size = 0;
	unsigned long tag_cache_size;
	int valid = 0;
	if (!service || !service->initialized || !map_leaf(map_name, leaf))
		return 0;
	if (service->preflight_ready)
		return strcmp(service->staged_map, leaf) == 0;
	if (service->mount.active || service->source.active) return 0;
	printf("HALO_PS2_LOCAL map-preflight source-open-begin\n");
	if (ctag_map_source_open_any(&service->source, "maps/ui.map") != 0) {
		printf("HALO_PS2_LOCAL map-preflight source-open-failed\n");
		return 0;
	}
	printf("HALO_PS2_LOCAL map-preflight source-opened bytes=%u\n",
		(unsigned)service->source.reader.size);
	mark = arena_mark(service->map_arena);
	HCU_TRACE("HALO_PS2_LOCAL map-preflight sections-begin\n");
	hmap_bytes = load_section(service, service->map_arena, "maps/ui.hp2",
		"HMAP", &hmap_size, 0);
	ctag_bytes = load_section(service, service->map_arena, "maps/ui.hp2",
		"CTAG", &ctag_size, 0);
	crng_bytes = load_section(service, service->map_arena, "maps/ui.hp2",
		"CRNG", &crng_size, 0);
	HCU_TRACE("HALO_PS2_LOCAL map-preflight sections-done hmap=%u ctag=%u crng=%u\n",
		(unsigned)hmap_size, (unsigned)ctag_size, (unsigned)crng_size);
	tag_cache_size = physical_memory_get_tag_cache_size();
	HCU_TRACE("HALO_PS2_LOCAL map-preflight validate-begin\n");
	if (hmap_bytes && ctag_bytes && crng_bytes &&
		hmap_open(&identity, hmap_bytes, hmap_size, leaf) &&
		identity.file_length == service->source.reader.size &&
		ctag_resource_index_open_discover(&resource_index, crng_bytes,
			crng_size, service->source.reader.size) &&
		resource_index.tag_data_offset == identity.tag_data_offset &&
		resource_index.tag_data_size == identity.tag_data_size &&
		ps2_ctag_open(&ctag_view, ctag_bytes, ctag_size, tag_cache_size,
			(uint32_t)(tag_cache_size / 4u)) == PS2_CTAG_OK &&
		verify_source_hash(service,
			identity.source_sha256))
		valid = 1;
	printf("HALO_PS2_LOCAL map-preflight result=%d\n", valid);
	arena_release(service->map_arena, mark);
	if (!valid) {
		ctag_map_source_close(&service->source);
		return 0;
	}
	service->identity = identity;
	memcpy(service->staged_map, leaf, sizeof(service->staged_map));
	service->preflight_ready = 1;
	return 1;
}

void hcu_map_service_shutdown(hcu_map_service *service)
{
	if (!service) return;
	map_unloader(service);
	ps2_cache_set_map_preflight(NULL, NULL);
	ps2_cache_set_map_loader(NULL, NULL);
	ps2_cache_set_map_unloader(NULL, NULL);
	service->initialized = 0;
	if (s_service == service) s_service = NULL;
}
