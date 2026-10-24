#define NEWLIB_PORT_AWARE
/* Host lifecycle fixture for the HCP runtime in hcu_map_service.c.
 *
 * The production translation unit is included so the static CE hooks
 * (map_loader/map_unloader/hcu_map_service_preflight) run exactly as CE calls
 * them. The real HCP envelope (package SHA and CE chunk table) and the real HCM1
 * decoder run; only hcu_profile_mount_* is scripted here, because its byte-level
 * CTAG/CBSP mount is covered by tests/hcu_profile_mount_main.c. The scripted
 * mount records every prepare/load/unload so ordering and leases are observable. */
#include "../src/stream/hcu_map_service.c"

#include <io_common.h>
#include <fileXio_rpc.h>

#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define TEST_TAG_CACHE_BYTES (2u * 1024u * 1024u)
#define TEST_MAP_ARENA_BYTES (1u * 1024u * 1024u)
#define TEST_SCRATCH_BYTES (1u * 1024u * 1024u)
#define TEST_PROFILE_ID 7u

static uint8_t s_map_arena_memory[TEST_MAP_ARENA_BYTES] __attribute__((aligned(16)));
static uint8_t s_scratch_memory[TEST_SCRATCH_BYTES] __attribute__((aligned(16)));
static uint8_t s_metadata_storage[256] __attribute__((aligned(16)));
static uint8_t s_small_metadata_storage[4] __attribute__((aligned(16)));
static uint8_t s_relocation_storage[4096] __attribute__((aligned(16)));
static uint8_t s_stream_scratch[4096] __attribute__((aligned(16)));

static unsigned s_prepare_calls;
static unsigned s_load_calls;
static unsigned s_unload_calls;
static unsigned s_unmount_calls;
static int s_prepare_result = HCU_PROFILE_MOUNT_OK;
static unsigned s_load_failures_remaining;

/* Scripted profile mount. Only the seam is replaced; state transitions mirror
 * hcu_profile_mount.c: prepare publishes nothing, load publishes the backend,
 * unload unmounts and clears the struct. */
void hcu_profile_mount_init(hcu_profile_mount *mount)
{
	if (mount) memset(mount, 0, sizeof(*mount));
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
	(void)cbsp_bindings; (void)cbsp_binding_count; (void)resource_ranges;
	(void)resource_range_count; (void)source_read; (void)source_context;
	(void)backend; (void)maximum_tag_image_bytes; (void)relocation_storage;
	(void)relocation_storage_bytes; (void)stream_scratch;
	(void)stream_scratch_bytes;
	++s_prepare_calls;
	if (!mount || !profile || !catalog_entry) return HCU_PROFILE_MOUNT_E_ARGUMENT;
	if (s_prepare_result != HCU_PROFILE_MOUNT_OK) return s_prepare_result;
	hcu_profile_mount_init(mount);
	mount->profile = profile;
	mount->profile_snapshot = *profile;
	mount->catalog_entry = catalog_entry;
	mount->source_identity_snapshot = catalog_entry->identity;
	mount->expected_profile_id = expected_profile_id;
	mount->prepared = 1;
	return HCU_PROFILE_MOUNT_OK;
}

int hcu_profile_mount_load(hcu_profile_mount *mount)
{
	++s_load_calls;
	if (!mount || !mount->prepared || mount->active) return HCU_PROFILE_MOUNT_E_STATE;
	if (s_load_failures_remaining) {
		--s_load_failures_remaining;
		return HCU_PROFILE_MOUNT_E_BACKEND;
	}
	mount->backend_mounted = 1;
	mount->active = 1;
	return HCU_PROFILE_MOUNT_OK;
}

int hcu_profile_mount_unload(hcu_profile_mount *mount)
{
	++s_unload_calls;
	if (!mount) return HCU_PROFILE_MOUNT_E_ARGUMENT;
	if (mount->callbacks_active) return HCU_PROFILE_MOUNT_E_BUSY;
	if (mount->backend_mounted) ++s_unmount_calls;
	memset(mount, 0, sizeof(*mount));
	return HCU_PROFILE_MOUNT_OK;
}

unsigned long physical_memory_get_tag_cache_size(void)
{
	return TEST_TAG_CACHE_BYTES;
}

/* The lifecycle fixture never reaches CE's legacy cache publication, so the
 * FileXio and physical-cache bases are inert: every source open fails. */
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

typedef struct {
	const uint8_t *bytes;
	uint32_t size;
} memory_image;

static int image_read(void *context, uint32_t offset, void *destination,
	uint32_t size)
{
	const memory_image *image = (const memory_image *)context;
	if (!image || offset > image->size || size > image->size - offset) return -1;
	memcpy(destination, image->bytes + offset, size);
	return 0;
}

static int source_read(void *context, int32_t output_datum, uint32_t file_offset,
	uint32_t size, void *buffer, int blocking)
{
	(void)context; (void)output_datum; (void)file_offset; (void)size;
	(void)buffer; (void)blocking;
	return -1;
}

static int accept_compatibility(void *context, const hcu_map_catalog_entry *entry,
	const hcu_asset_profile_view *profile)
{
	(void)context; (void)entry;
	return profile != NULL;
}

static int hex_nibble(char c)
{
	if (c >= '0' && c <= '9') return c - '0';
	if (c >= 'a' && c <= 'f') return c - 'a' + 10;
	if (c >= 'A' && c <= 'F') return c - 'A' + 10;
	return -1;
}

static void parse_sha256(const char *hex, uint8_t out[32])
{
	int i;
	assert(strlen(hex) == 64u);
	for (i = 0; i < 32; ++i) {
		int high = hex_nibble(hex[2 * i]);
		int low = hex_nibble(hex[2 * i + 1]);
		assert(high >= 0 && low >= 0);
		out[i] = (uint8_t)((high << 4) | low);
	}
}

static uint8_t *read_file(const char *path, uint32_t *size)
{
	FILE *file = fopen(path, "rb");
	uint8_t *bytes;
	long length;
	assert(file);
	assert(fseek(file, 0, SEEK_END) == 0);
	length = ftell(file);
	assert(length > 0 && length < 0x7fffffff);
	assert(fseek(file, 0, SEEK_SET) == 0);
	bytes = (uint8_t *)malloc((size_t)length);
	assert(bytes);
	assert(fread(bytes, 1, (size_t)length, file) == (size_t)length);
	fclose(file);
	*size = (uint32_t)length;
	return bytes;
}

static hcu_map_profile_runtime make_runtime(const memory_image *package,
	const uint8_t package_sha[32], const uint8_t *metadata, size_t metadata_size,
	const uint8_t metadata_sha[32], void *metadata_storage,
	size_t metadata_storage_bytes, const hcu_bitmap_frame_owner *owner)
{
	hcu_map_profile_runtime runtime;
	memset(&runtime, 0, sizeof(runtime));
	runtime.package_read_at = image_read;
	runtime.package_context = (void *)package;
	runtime.package_size = package->size;
	runtime.profile_id = TEST_PROFILE_ID;
	memcpy(runtime.package_sha256, package_sha, 32);
	runtime.compatibility = accept_compatibility;
	runtime.metadata_bytes = metadata;
	runtime.metadata_size = metadata_size;
	memcpy(runtime.metadata_sha256, metadata_sha, 32);
	runtime.metadata_storage = metadata_storage;
	runtime.metadata_storage_bytes = metadata_storage_bytes;
	runtime.source_read = source_read;
	runtime.relocation_storage = s_relocation_storage;
	runtime.relocation_storage_bytes = sizeof(s_relocation_storage);
	runtime.stream_scratch = s_stream_scratch;
	runtime.stream_scratch_bytes = sizeof(s_stream_scratch);
	runtime.maximum_tag_image_bytes = TEST_TAG_CACHE_BYTES;
	runtime.frame_owner = owner;
	return runtime;
}

static void expect_live_owner(const hcu_map_service *service, int live)
{
	assert((service->profile_mount.active != 0) == (live != 0));
	assert((service->profile_mount.backend_mounted != 0) == (live != 0));
}

static void expect_no_stage(const hcu_map_service *service)
{
	assert(!service->profile_candidate_ready);
	assert(!service->preflight_ready);
	assert(!service->reload_pending);
	assert(service->staged_entry == NULL);
	assert(service->staged_map[0] == 0);
}

int main(int argc, char **argv)
{
	mem_layout_v2_t layout;
	arena_t map_owner, section_scratch;
	hcu_map_service service;
	memory_image package;
	uint8_t package_sha[32], meta_ok_sha[32], meta_big_sha[32];
	uint8_t *package_bytes, *meta_ok, *meta_big;
	uint32_t meta_ok_size, meta_big_size;
	uint8_t bad_sha[32];
	hcu_map_profile_runtime runtime;
	hcu_bitmap_frame_owner owner;
	hcu_bitmap_dispatch_context dispatch;
	unsigned prepares_before;
	if (argc != 8) {
		fprintf(stderr, "usage: %s package.hcp package_sha256 meta_ok.hcm meta_ok_sha256 meta_big.hcm meta_big_sha256 asset_root\n",
			argv[0]);
		return 2;
	}
	package_bytes = read_file(argv[1], &package.size);
	package.bytes = package_bytes;
	parse_sha256(argv[2], package_sha);
	meta_ok = read_file(argv[3], &meta_ok_size);
	parse_sha256(argv[4], meta_ok_sha);
	meta_big = read_file(argv[5], &meta_big_size);
	parse_sha256(argv[6], meta_big_sha);
	memset(bad_sha, 0xa5, sizeof(bad_sha));

	memset(&layout, 0, sizeof(layout));
	arena_init(&map_owner, "profile map owner", s_map_arena_memory,
		sizeof(s_map_arena_memory));
	arena_init(&section_scratch, "profile section scratch", s_scratch_memory,
		sizeof(s_scratch_memory));
	layout.regions[MEM_LAYOUT_V2_STREAMING] = map_owner;
	layout.regions[MEM_LAYOUT_V2_FRAME_SCRATCH] = section_scratch;
	assert(hcu_map_service_init(&service, &layout, argv[7]) == 0);
	assert(hcu_map_catalog_find("ui") != NULL);

	memset(&owner, 0, sizeof(owner));
	memset(&dispatch, 0, sizeof(dispatch));
	owner.bound = 1;
	owner.dispatch = &dispatch;

	/* 1. A wrong package pin is refused at registration and registers nothing. */
	runtime = make_runtime(&package, bad_sha, meta_ok, meta_ok_size, meta_ok_sha,
		s_metadata_storage, sizeof(s_metadata_storage), &owner);
	assert(!hcu_map_service_register_runtime(&service, "ui", &runtime));
	assert(!service.runtime_registered);

	/* 2. Over-capacity: the metadata claims a range but its storage is too small.
	 * Preflight rejects before any mount preparation and before teardown. */
	runtime = make_runtime(&package, package_sha, meta_big, meta_big_size,
		meta_big_sha, s_small_metadata_storage, sizeof(s_small_metadata_storage),
		&owner);
	assert(hcu_map_service_register_runtime(&service, "ui", &runtime));
	prepares_before = s_prepare_calls;
	assert(!hcu_map_service_preflight("ui"));
	assert(s_prepare_calls == prepares_before);
	expect_live_owner(&service, 0);
	expect_no_stage(&service);
	printf("PASS over-capacity metadata rejected before mount preparation\n");
	assert(hcu_map_service_unregister_runtime(&service));

	/* 3. Mount-side capacity rejection also keeps the service empty. */
	runtime = make_runtime(&package, package_sha, meta_ok, meta_ok_size,
		meta_ok_sha, s_metadata_storage, sizeof(s_metadata_storage), &owner);
	assert(hcu_map_service_register_runtime(&service, "ui", &runtime));
	s_prepare_result = HCU_PROFILE_MOUNT_E_CAPACITY;
	assert(!hcu_map_service_preflight("ui"));
	assert(!service.profile_candidate_ready);
	expect_live_owner(&service, 0);
	s_prepare_result = HCU_PROFILE_MOUNT_OK;
	printf("PASS mount-prepare capacity rejection leaves no stage\n");

	/* 4. A valid successor passes preflight, then CE's loader publishes it. */
	assert(hcu_map_service_preflight("ui") == 1);
	assert(service.profile_candidate_ready);
	assert(map_loader(&service, "ui") == 1);
	expect_live_owner(&service, 1);
	assert(service.profile_mount.source_identity_snapshot.map_name[0] == 'u');
	expect_no_stage(&service);
	printf("PASS validated successor loads after unpublish\n");

	/* 5. Leases outstanding: the live owner and its storage stay exactly in place. */
	dispatch.lease_count = 1;
	assert(!service.reload_pending);
	assert(!hcu_map_service_preflight("ui"));
	assert(!service.reload_pending);
	map_unloader(&service);
	assert(s_unload_calls == 0 && s_unmount_calls == 0);
	expect_live_owner(&service, 1);
	assert(service.runtime.metadata_storage == s_metadata_storage);
	assert(map_loader(&service, "ui") == 0);
	expect_live_owner(&service, 1);
	printf("PASS storage held while bitmap leases are outstanding\n");

	/* 6. A preflight for a different map while live is refused without teardown. */
	assert(!hcu_map_service_preflight("beavercreek"));
	expect_live_owner(&service, 1);
	assert(s_unload_calls == 0);
	printf("PASS preflight failure preserves the live owner\n");

	/* 7. Lease drained: same-map preflight reuses the owner, unload happens, and a
	 * post-unload load failure yields an empty service that can retry. */
	dispatch.lease_count = 0;
	assert(hcu_map_service_preflight("ui") == 1);
	assert(service.reload_pending && service.runtime_registered);
	map_unloader(&service);
	assert(s_unload_calls == 1 && s_unmount_calls == 1);
	expect_live_owner(&service, 0);
	s_load_failures_remaining = 1;
	assert(map_loader(&service, "ui") == 0);
	expect_live_owner(&service, 0);
	expect_no_stage(&service);
	assert(service.runtime_registered);
	printf("PASS post-unload load failure leaves a safe empty state\n");

	/* 8. Retry after the failure publishes again. */
	assert(hcu_map_service_preflight("ui") == 1);
	assert(map_loader(&service, "ui") == 1);
	expect_live_owner(&service, 1);
	map_unloader(&service);
	expect_live_owner(&service, 0);
	assert(hcu_map_service_unregister_runtime(&service));
	printf("PASS retry after empty state reloads the same runtime\n");

	/* 9. Legacy path: with no runtime registered, the profile mount is never
	 * touched. The legacy source is absent from this asset root, so it fails. */
	prepares_before = s_prepare_calls;
	assert(!hcu_map_service_preflight("ui"));
	assert(s_prepare_calls == prepares_before);
	expect_live_owner(&service, 0);
	printf("PASS legacy preflight without runtime does not touch profile mount\n");

	/* 10. Stale stage regression. A successful earlier preflight of "ui" left
	 * its validated stage behind (simulated here: the legacy success path needs
	 * real assets this fixture lacks). A second preflight of "ui" that fails the
	 * asset-profile gate must clear that stage, so map_loader("ui") refuses. */
	{
		const hcu_map_catalog_entry *ui = hcu_map_catalog_find("ui");
		assert(ui != NULL);
		assert(!service.runtime_registered && !service.reload_pending);
		service.preflight_ready = 1;
		service.staged_entry = ui;
		memcpy(service.staged_map, ui->identity.map_name,
			strlen(ui->identity.map_name) + 1);
		service.profile_requested = 1;
		memset(service.profile_map_name, 0, sizeof(service.profile_map_name));
		memcpy(service.profile_map_name, "beavercreek",
			strlen("beavercreek") + 1);
		prepares_before = s_prepare_calls;
		assert(!hcu_map_service_preflight("ui"));
		assert(!service.preflight_ready);
		assert(service.staged_entry == NULL);
		assert(service.staged_map[0] == 0);
		assert(!service.reload_pending);
		assert(s_prepare_calls == prepares_before);
		assert(map_loader(&service, "ui") == 0);
		expect_live_owner(&service, 0);
		expect_no_stage(&service);
		service.profile_requested = 0;
		printf("PASS failed gate preflight clears stale stage; loader refuses\n");
	}

	hcu_map_service_shutdown(&service);
	free(package_bytes);
	free(meta_ok);
	free(meta_big);
	printf("HALO_PS2_LOCAL map-service-profile-lifecycle passed\n");
	return 0;
}
