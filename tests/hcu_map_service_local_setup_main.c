#define NEWLIB_PORT_AWARE
/* C5 local setup gate proof for hcu_map_service_preflight(). The production
 * translation unit is included so map_preflight and the gate run as CE calls
 * them. A map is seeded as live (mount active, identity set): the fixture does
 * not load a real package, so this is a seeded loaded-state fixture.
 *
 * Each rejection must leave the whole service structure byte-identical, which
 * shows the gate runs before any staging, teardown or unload. The Python test
 * checks the printed reason. */
#include "../src/stream/hcu_map_service.c"
#include "stream/hcu_local_setup_rows.inc"

#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include <io_common.h>
#include <fileXio_rpc.h>

/* Inert fixture: the gate never reaches the profile mount or the legacy source
 * open, so these seams fail closed and the physical cache bases stay empty. */
void hcu_profile_mount_init(hcu_profile_mount *mount)
{
	if (mount) memset(mount, 0, sizeof(*mount));
}
int hcu_profile_mount_bind_residency(hcu_profile_mount *mount,
	hcu_asset_residency_entry *entries, uint32_t entry_capacity,
	void *arena, size_t arena_bytes)
{
	(void)mount; (void)entries; (void)entry_capacity; (void)arena; (void)arena_bytes;
	return HCU_PROFILE_MOUNT_E_STATE;
}
int hcu_profile_mount_inputs_match(const hcu_profile_mount *mount)
{
	(void)mount;
	return 0;
}
int hcu_profile_mount_residency_snapshot(const hcu_profile_mount *mount,
	hcu_profile_residency_stats *stats)
{
	(void)mount; (void)stats;
	return HCU_PROFILE_MOUNT_E_STATE;
}
int hcu_profile_mount_prepare(hcu_profile_mount *mount,
	const hcu_asset_profile_view *profile, uint32_t expected_profile_id,
	const hcu_map_catalog_entry *catalog_entry,
	const hcu_profile_cbsp_binding *cbsp_bindings, uint16_t cbsp_binding_count,
	const hcu_profile_resource_range *resource_ranges, uint32_t resource_range_count,
	hcu_profile_source_read_fn source_read, void *source_context,
	const ctag_mount_backend *backend, uint32_t maximum_tag_image_bytes,
	void *relocation_storage, size_t relocation_storage_bytes,
	void *stream_scratch, size_t stream_scratch_bytes)
{
	(void)mount; (void)profile; (void)expected_profile_id; (void)catalog_entry;
	(void)cbsp_bindings; (void)cbsp_binding_count; (void)resource_ranges;
	(void)resource_range_count; (void)source_read; (void)source_context;
	(void)backend; (void)maximum_tag_image_bytes; (void)relocation_storage;
	(void)relocation_storage_bytes; (void)stream_scratch; (void)stream_scratch_bytes;
	return HCU_PROFILE_MOUNT_E_STATE;
}
int hcu_profile_mount_load(hcu_profile_mount *mount)
{
	(void)mount;
	return HCU_PROFILE_MOUNT_E_STATE;
}
int hcu_profile_mount_unload_with_residency_stats(hcu_profile_mount *mount,
	hcu_profile_residency_stats *released_stats)
{
	(void)mount; (void)released_stats;
	return HCU_PROFILE_MOUNT_E_STATE;
}
int hcu_profile_mount_unload(hcu_profile_mount *mount)
{
	return hcu_profile_mount_unload_with_residency_stats(mount, NULL);
}
unsigned long physical_memory_get_tag_cache_size(void) { return 2u * 1024u * 1024u; }
void *physical_memory_get_tag_cache_base_address(void) { return NULL; }
void *physical_memory_get_structure_bsp_cache_base_address(void) { return NULL; }
unsigned long physical_memory_get_structure_bsp_cache_size(void) { return 0; }
int fileXioInit(void) { return 0; }
int fileXioOpen(const char *path, int flags, ...)
{
	(void)path; (void)flags;
	return -1;
}
int fileXioClose(int descriptor) { (void)descriptor; return 0; }
int fileXioRead(int descriptor, void *buffer, int size)
{
	(void)descriptor; (void)buffer; (void)size;
	return -1;
}
int fileXioLseek(int descriptor, int offset, int whence)
{
	(void)descriptor; (void)offset; (void)whence;
	return -1;
}
int fileXioGetStat(const char *path, iox_stat_t *info)
{
	(void)path; (void)info;
	return -1;
}

#define TEST_MAP_ARENA_BYTES (1u * 1024u * 1024u)
#define TEST_SCRATCH_BYTES (1u * 1024u * 1024u)

static uint8_t s_map_arena_memory[TEST_MAP_ARENA_BYTES] __attribute__((aligned(16)));
static uint8_t s_scratch_memory[TEST_SCRATCH_BYTES] __attribute__((aligned(16)));

/* Test-only row set: the one row used for the accept control. It is not
 * evidence and never reaches the generated table. */
static const hcu_local_qualified_row s_control_rows[] = {
	{ "ui", HCU_LOCAL_MODE_STOCK_COOP, 1u << HCU_LOCAL_DIFFICULTY_NORMAL, 4u, 4u },
};

static hcu_local_setup s_setup;

static void make_setup(hcu_local_setup *r, const char *map, uint32_t humans, uint32_t bots)
{
	memset(r, 0, sizeof *r);
	r->mode = HCU_LOCAL_MODE_STOCK_COOP;
	r->variant = HCU_LOCAL_VARIANT_CTF;
	r->difficulty = HCU_LOCAL_DIFFICULTY_NORMAL;
	r->human_mask = humans;
	r->bot_count = bots;
	r->teams = HCU_LOCAL_TEAMS_ON;  /* CTF requires the team switch on */
	r->seed = 0x5eedu;
	strncpy(r->map_name, map, sizeof r->map_name - 1u);
}

static void seed_loaded_map(hcu_map_service *service, const char *map)
{
	service->mount.active = 1;
	memset(service->identity.map_name, 0, sizeof service->identity.map_name);
	strncpy(service->identity.map_name, map, sizeof service->identity.map_name - 1u);
}

int main(int argc, char **argv)
{
	mem_layout_v2_t layout;
	arena_t map_owner, section_scratch;
	static hcu_map_service service;
	static hcu_map_service before;
	int ok;

	setvbuf(stdout, NULL, _IONBF, 0);
	if (argc != 2) {
		fprintf(stderr, "usage: %s asset_root/\n", argv[0]);
		return 2;
	}
	memset(&layout, 0, sizeof layout);
	arena_init(&map_owner, "local setup map owner", s_map_arena_memory,
		sizeof s_map_arena_memory);
	arena_init(&section_scratch, "local setup section scratch", s_scratch_memory,
		sizeof s_scratch_memory);
	layout.regions[MEM_LAYOUT_V2_STREAMING] = map_owner;
	layout.regions[MEM_LAYOUT_V2_FRAME_SCRATCH] = section_scratch;
	assert(hcu_map_service_init(&service, &layout, argv[1]) == 0);
	seed_loaded_map(&service, "ui");

	/* 1. Generated table: no row is qualified, so a populated setup on a
	 * gameplay map is refused for its difficulty before any teardown. */
	make_setup(&s_setup, "beavercreek", 0x3u, 2u);
	assert(hcu_map_service_set_local_setup(&service, &s_setup,
		hcu_local_generated_rows, HCU_LOCAL_GENERATED_ROW_COUNT));
	before = service;
	ok = hcu_map_service_preflight("beavercreek");
	assert(!ok);
	assert(memcmp(&before, &service, sizeof service) == 0);
	printf("PASS generated-table setup refused before teardown; loaded state unchanged\n");

	/* 2. Map-name mismatch between setup and the requested map. */
	make_setup(&s_setup, "bloodgulch", 0x1u, 0u);
	before = service;
	ok = map_preflight(&service, "beavercreek");
	assert(!ok);
	assert(memcmp(&before, &service, sizeof service) == 0);
	printf("PASS setup for another map refused; loaded state unchanged\n");

	/* 3. Invalid roster: no humans. The gate refuses before the catalog path. */
	make_setup(&s_setup, "beavercreek", 0u, 0u);
	before = service;
	assert(!hcu_map_service_preflight("beavercreek"));
	assert(memcmp(&before, &service, sizeof service) == 0);
	printf("PASS empty roster refused; loaded state unchanged\n");

	/* 4. Accept control: a test-only row admits the same map name, so the gate
	 * does not refuse. The seeded ui owner makes the same-map shortcut return 1. */
	make_setup(&s_setup, "ui", 0x1u, 0u);
	assert(hcu_map_service_set_local_setup(&service, &s_setup,
		s_control_rows, sizeof s_control_rows / sizeof s_control_rows[0]));
	assert(hcu_map_service_preflight("ui") == 1);
	printf("PASS qualified control setup admitted by the gate\n");

	/* 5. Clearing the gate restores the unchanged preflight behaviour. */
	assert(hcu_map_service_set_local_setup(&service, NULL, NULL, 0));
	assert(!hcu_map_service_preflight("beavercreek"));
	printf("PASS cleared gate restores unchanged preflight\n");

	puts("hcu-map-service-local-setup passed");
	return 0;
}
