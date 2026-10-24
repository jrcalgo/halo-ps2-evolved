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

static uint8_t s_b_metadata_storage[256] __attribute__((aligned(16)));
static uint8_t s_b_relocation_storage[4096] __attribute__((aligned(16)));
static uint8_t s_b_stream_scratch[4096] __attribute__((aligned(16)));
static hcu_asset_residency_entry s_b_residency_entries[4] __attribute__((aligned(16)));
static uint8_t s_b_residency_arena[HCU_PROFILE_MOUNT_RESIDENCY_SEGMENT_BYTES]
	__attribute__((aligned(16)));
/* Stands for the published tag cache of the live owner: filled with its map's
 * first letter when the scripted load publishes it, cleared when it unmounts. */
static uint8_t s_live_tags[32] __attribute__((aligned(16)));
/* Two whole 64 KiB residency slots, as the production arena is sized. */
static hcu_asset_residency_entry s_residency_entries[4] __attribute__((aligned(16)));
static uint8_t s_residency_arena[2u * HCU_PROFILE_MOUNT_RESIDENCY_SEGMENT_BYTES]
	__attribute__((aligned(16)));

static unsigned s_prepare_calls;
static unsigned s_load_calls;
static unsigned s_unload_calls;
static unsigned s_unmount_calls;
static int s_prepare_result = HCU_PROFILE_MOUNT_OK;
static unsigned s_load_failures_remaining;
static int s_bindings_valid = 1;
static int s_renderer_drained = 1;
static unsigned s_renderer_calls;
static int s_renderer_quiesce_result = 1;
static unsigned s_renderer_quiesce_calls;
static unsigned s_bind_calls;
static unsigned s_unbound_prepares;
static int s_bind_result = HCU_PROFILE_MOUNT_OK;
static int s_legacy_drained = 1;
/* Ordered record of the seam calls: "prepare:<map>", "publish:<map>",
 * "load-fail:<map>", "dispose:<map>", "unpublish:<map>". */
static char s_trace[16][48];
static unsigned s_trace_count;
/* CE's dispose callback runs while the old owner's tags are still published. */
static void (*s_dispose_callback)(void);

static void trace_event(const char *event, const char *map)
{
	assert(s_trace_count < 16u);
	snprintf(s_trace[s_trace_count++], sizeof(s_trace[0]), "%s:%s", event,
		map ? map : "-");
}

static void expect_trace(const char *const expected[], unsigned count)
{
	unsigned i;
	assert(s_trace_count == count);
	for (i = 0; i < count; ++i)
		assert(strcmp(s_trace[i], expected[i]) == 0);
}

static int scripted_legacy_drained(void *context)
{
	(void)context;
	return s_legacy_drained;
}

static int scripted_renderer_drained(void *context)
{
	(void)context;
	++s_renderer_calls;
	return s_renderer_drained;
}

static int scripted_renderer_quiesce(void *context)
{
	const hcu_map_service *service = (const hcu_map_service *)context;
	(void)context;
	++s_renderer_quiesce_calls;
	/* In this fixture the callback is installed only on the live owner during
	 * foreign-successor preflight. Its candidate must already be fully prepared. */
	assert(service && service->profile_candidate.prepared);
	return s_renderer_quiesce_result;
}

/* Scripted profile mount. Only the seam is replaced; state transitions mirror
 * hcu_profile_mount.c: prepare publishes nothing, load publishes the backend,
 * unload unmounts and clears the struct. */
void hcu_profile_mount_init(hcu_profile_mount *mount)
{
	if (mount) memset(mount, 0, sizeof(*mount));
}

/* Scripted residency bind: records the call and marks the mount bound, as the
 * real bind does, so prepare can be checked for an unbound mount. */
int hcu_profile_mount_bind_residency(hcu_profile_mount *mount,
	hcu_asset_residency_entry *entries, uint32_t entry_capacity,
	void *arena, size_t arena_bytes)
{
	++s_bind_calls;
	if (!mount || !entries || !entry_capacity || !arena || !arena_bytes)
		return HCU_PROFILE_MOUNT_E_ARGUMENT;
	if (s_bind_result != HCU_PROFILE_MOUNT_OK) return s_bind_result;
	mount->residency_entries = entries;
	mount->residency_entry_capacity = entry_capacity;
	mount->residency_arena = (uint8_t *)arena;
	mount->residency_arena_bytes = arena_bytes;
	mount->residency_bound = 1;
	return HCU_PROFILE_MOUNT_OK;
}

int hcu_profile_mount_inputs_match(const hcu_profile_mount *mount)
{
	return s_bindings_valid && mount && mount->prepared && !mount->callbacks_active;
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
	if (!mount->residency_bound) ++s_unbound_prepares;
	if (s_prepare_result != HCU_PROFILE_MOUNT_OK) return s_prepare_result;
	{
		/* The bind is kept across the scripted reset, as the real prepare keeps it. */
		int bound = mount->residency_bound;
		hcu_asset_residency_entry *entries = mount->residency_entries;
		uint32_t capacity = mount->residency_entry_capacity;
		uint8_t *arena = mount->residency_arena;
		size_t arena_bytes = mount->residency_arena_bytes;
		hcu_profile_mount_init(mount);
		mount->residency_bound = (uint8_t)bound;
		mount->residency_entries = entries;
		mount->residency_entry_capacity = capacity;
		mount->residency_arena = arena;
		mount->residency_arena_bytes = arena_bytes;
	}
	mount->profile = profile;
	mount->profile_snapshot = *profile;
	mount->catalog_entry = catalog_entry;
	mount->source_identity_snapshot = catalog_entry->identity;
	mount->expected_profile_id = expected_profile_id;
	mount->prepared = 1;
	trace_event("prepare", catalog_entry->identity.map_name);
	return HCU_PROFILE_MOUNT_OK;
}

int hcu_profile_mount_load(hcu_profile_mount *mount)
{
	++s_load_calls;
	if (!mount || !mount->prepared || mount->active) return HCU_PROFILE_MOUNT_E_STATE;
	if (s_load_failures_remaining) {
		--s_load_failures_remaining;
		trace_event("load-fail", mount->source_identity_snapshot.map_name);
		return HCU_PROFILE_MOUNT_E_BACKEND;
	}
	mount->backend_mounted = 1;
	mount->active = 1;
	/* Script a real-looking decoded segment working set for the service
	 * lifetime tests; capacity remains the runtime's caller-bound span. */
	mount->residency.resident_bytes = 4096u;
	mount->residency.resident_high_water = 8192u;
	mount->residency.evictions = 2u;
	mount->residency.refused_evictions = 1u;
	mount->residency.refused_pins = 0u;
	mount->residency.verify_failures = 0u;
	memset(s_live_tags, mount->source_identity_snapshot.map_name[0],
		sizeof(s_live_tags));
	trace_event("publish", mount->source_identity_snapshot.map_name);
	return HCU_PROFILE_MOUNT_OK;
}

int hcu_profile_mount_residency_snapshot(const hcu_profile_mount *mount,
	hcu_profile_residency_stats *stats)
{
	if (!mount || !stats) return HCU_PROFILE_MOUNT_E_ARGUMENT;
	if (!mount->prepared || !mount->residency_bound) return HCU_PROFILE_MOUNT_E_STATE;
	memset(stats, 0, sizeof(*stats));
	stats->bound = 1;
	stats->capacity_bytes = mount->residency_arena_bytes;
	stats->current_bytes = mount->residency.resident_bytes;
	stats->high_water_bytes = mount->residency.resident_high_water;
	stats->evictions = mount->residency.evictions;
	stats->refused_evictions = mount->residency.refused_evictions;
	stats->refused_pins = mount->residency.refused_pins;
	stats->verify_failures = mount->residency.verify_failures;
	return HCU_PROFILE_MOUNT_OK;
}

int hcu_profile_mount_unload_with_residency_stats(hcu_profile_mount *mount,
	hcu_profile_residency_stats *released_stats)
{
	hcu_profile_residency_stats stats;
	++s_unload_calls;
	if (!mount) return HCU_PROFILE_MOUNT_E_ARGUMENT;
	if (mount->callbacks_active) return HCU_PROFILE_MOUNT_E_BUSY;
	if (mount->backend_mounted) {
		++s_unmount_calls;
		trace_event("dispose", mount->source_identity_snapshot.map_name);
		if (s_dispose_callback) s_dispose_callback();
		memset(s_live_tags, 0, sizeof(s_live_tags));
		trace_event("unpublish", mount->source_identity_snapshot.map_name);
	}
	if (mount->prepared && mount->residency_bound) {
		(void)hcu_profile_mount_residency_snapshot(mount, &stats);
		stats.current_bytes = 0;
		stats.resets = 1;
	} else memset(&stats, 0, sizeof(stats));
	memset(mount, 0, sizeof(*mount));
	if (released_stats) *released_stats = stats;
	return HCU_PROFILE_MOUNT_OK;
}

int hcu_profile_mount_unload(hcu_profile_mount *mount)
{
	return hcu_profile_mount_unload_with_residency_stats(mount, NULL);
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

static int reject_compatibility(void *context, const hcu_map_catalog_entry *entry,
	const hcu_asset_profile_view *profile)
{
	(void)context; (void)entry; (void)profile;
	return 0;
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
	runtime.renderer_drained = scripted_renderer_drained;
	runtime.residency_entries = s_residency_entries;
	runtime.residency_entry_capacity = sizeof(s_residency_entries) /
		sizeof(s_residency_entries[0]);
	runtime.residency_arena = s_residency_arena;
	runtime.residency_arena_bytes = sizeof(s_residency_arena);
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

/* Stands for CE's dispose of map A: its tags must still read as A's. */
static void dispose_reads_live_tags(void)
{
	assert(s_live_tags[0] == 'u');
	assert(s_live_tags[sizeof(s_live_tags) - 1u] == 'u');
}

#ifdef HALO_HCU_HEADLESS_RUNTIME_GUEST
static int headless_never_started(void *context)
{
	(void)context;
	return 1;
}
#endif

/* Boundary hook recorder: phase and cycle of every boundary, in call order. */
static char s_boundary_phase[8][16];
static unsigned s_boundary_cycle[8];
static unsigned s_boundary_count;

static void record_boundary(void *context, const char *phase, unsigned int cycle)
{
	assert(context == &s_boundary_count);
	assert(s_boundary_count < 8u);
	snprintf(s_boundary_phase[s_boundary_count], sizeof(s_boundary_phase[0]), "%s", phase);
	s_boundary_cycle[s_boundary_count++] = cycle;
}

int main(int argc, char **argv)
{
	mem_layout_v2_t layout;
	arena_t map_owner, section_scratch;
	hcu_map_service service;
	hcu_map_residency_report residency_report;
	memory_image package;
	uint8_t package_sha[32], meta_ok_sha[32], meta_big_sha[32];
	uint8_t *package_bytes, *meta_ok, *meta_big;
	uint32_t meta_ok_size, meta_big_size;
	uint8_t bad_sha[32];
	hcu_map_profile_runtime runtime;
	hcu_bitmap_frame_owner owner;
	hcu_bitmap_dispatch_context dispatch;
	unsigned prepares_before;
	/* Unbuffered, so the lines before an assertion abort still reach the log. */
	setvbuf(stdout, NULL, _IONBF, 0);
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

	/* 1b. A runtime without residency, or with a ragged arena, fails closed at
	 * registration: its mount would otherwise read whole chunks. */
	runtime = make_runtime(&package, package_sha, meta_ok, meta_ok_size,
		meta_ok_sha, s_metadata_storage, sizeof(s_metadata_storage), &owner);
	runtime.residency_arena = NULL;
	assert(!hcu_map_service_register_runtime(&service, "ui", &runtime));
	runtime.residency_arena = s_residency_arena;
	runtime.residency_arena_bytes = HCU_PROFILE_MOUNT_RESIDENCY_SEGMENT_BYTES + 8u;
	assert(!hcu_map_service_register_runtime(&service, "ui", &runtime));
	assert(!service.runtime_registered);
	printf("PASS runtime without whole-slot residency arena is refused at registration\n");

	/* 1d. A compatibility gate that rejects the profile refuses registration.
	 * The service registers nothing, so no later preflight can reach the mount. */
	runtime = make_runtime(&package, package_sha, meta_ok, meta_ok_size,
		meta_ok_sha, s_metadata_storage, sizeof(s_metadata_storage), &owner);
	runtime.compatibility = reject_compatibility;
	assert(!hcu_map_service_register_runtime(&service, "ui", &runtime));
	assert(!service.runtime_registered);
	printf("PASS runtime rejected by the compatibility gate is not registered\n");

	/* 1c. A failed residency bind stops the stage before prepare runs. */
	runtime = make_runtime(&package, package_sha, meta_ok, meta_ok_size,
		meta_ok_sha, s_metadata_storage, sizeof(s_metadata_storage), &owner);
	assert(hcu_map_service_register_runtime(&service, "ui", &runtime));
	prepares_before = s_prepare_calls;
	s_bind_result = HCU_PROFILE_MOUNT_E_STATE;
	assert(!hcu_map_service_preflight("ui"));
	assert(s_bind_calls > 0 && s_prepare_calls == prepares_before);
	expect_no_stage(&service);
	s_bind_result = HCU_PROFILE_MOUNT_OK;
	assert(hcu_map_service_unregister_runtime(&service));
	printf("PASS failed residency bind stops the stage before mount preparation\n");

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
	package_bytes[package.size - 1u] ^= 1u;
	assert(!hcu_map_service_preflight("ui"));
	expect_no_stage(&service);
	expect_live_owner(&service, 0);
	package_bytes[package.size - 1u] ^= 1u;
	assert(hcu_map_service_preflight("ui") == 1);
	printf("PASS repeated preflight revalidates and discards a corrupted empty stage\n");
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
	assert(!hcu_map_service_shutdown(&service));
	assert(service.initialized && service.runtime_registered);
	expect_live_owner(&service, 1);
	assert(s_unload_calls == 0 && s_unmount_calls == 0);
	printf("PASS busy shutdown retains callbacks and initialized owner for retry\n");

	/* 5b. Renderer readers (C3.11): registered source references hold the live
	 * owner exactly like a bitmap lease, and each release is matched once. */
	{
		hcu_map_reader_ref refs[HCU_MAP_READER_CAPACITY + 1u];
		hcu_map_reader_ref stale;
		unsigned i;
		uint32_t saved_leases = dispatch.lease_count;
		dispatch.lease_count = 0;
		assert(hcu_map_service_readers_drained(&service));
		assert(!hcu_map_service_reader_acquire(&service, HCU_MAP_READER_TEXTURE_UPLOAD,
			NULL, 16u, &refs[0]));
		assert(!hcu_map_service_reader_acquire(&service, HCU_MAP_READER_NONE,
			package_bytes, 16u, &refs[0]));
		assert(!hcu_map_service_reader_acquire(&service, HCU_MAP_READER_DRAW_CHAIN,
			package_bytes, 0u, &refs[0]));
		assert(hcu_map_service_reader_acquire(&service, HCU_MAP_READER_TEXTURE_UPLOAD,
			package_bytes, 16u, &refs[0]));
		assert(hcu_map_service_reader_count(&service) == 1);
		assert(!hcu_map_service_readers_drained(&service));
		map_unloader(&service);
		assert(s_unload_calls == 0 && s_unmount_calls == 0);
		expect_live_owner(&service, 1);
		assert(map_loader(&service, "ui") == 0);
		/* A reader from before a release cannot release a reused slot. */
		stale = refs[0];
		assert(hcu_map_service_reader_release(&service, refs[0]));
		assert(!hcu_map_service_reader_release(&service, stale));
		assert(hcu_map_service_reader_count(&service) == 0);
		assert(hcu_map_service_readers_drained(&service));
		/* Fill the table: the next acquire is refused and counted. */
		for (i = 0; i < HCU_MAP_READER_CAPACITY; ++i)
			assert(hcu_map_service_reader_acquire(&service,
				HCU_MAP_READER_DRAW_CHAIN, package_bytes + i, 1u, &refs[i]));
		assert(!hcu_map_service_reader_acquire(&service, HCU_MAP_READER_SOURCE_SPAN,
			package_bytes, 1u, &refs[HCU_MAP_READER_CAPACITY]));
		assert(service.reader_refused >= 1u);
		assert(!hcu_map_service_readers_drained(&service));
		for (i = 0; i < HCU_MAP_READER_CAPACITY; ++i)
			assert(hcu_map_service_reader_release(&service, refs[i]));
		assert(hcu_map_service_readers_drained(&service));
		dispatch.lease_count = saved_leases;
		printf("PASS renderer readers hold the live owner, refuse stale releases and a full table\n");
		/* World accessor: unbound until the loader binds it, returns the bound
		 * pointers and the map generation while mounted, and clears on release. */
		{
			static int fixture_bsp;
			static int fixture_source;
			const struct bsp_section *got_bsp = NULL;
			const void *got_source = NULL;
			uint32_t generation = 99u;
			assert(!hcu_map_service_current_world(&service, &got_bsp, &got_source, &generation));
			assert(got_bsp == NULL && got_source == NULL && generation == 0u);
			assert(!hcu_map_service_bind_world(&service, NULL, &fixture_source));
			assert(hcu_map_service_bind_world(&service, (const struct bsp_section *)&fixture_bsp,
				&fixture_source));
			assert(hcu_map_service_current_world(&service, &got_bsp, &got_source, &generation));
			assert((const void *)got_bsp == (const void *)&fixture_bsp && got_source == &fixture_source);
			assert(generation == service.boundary_cycle);
			assert(hcu_map_service_current_world(&service, NULL, NULL, NULL));
		}
		printf("PASS world accessor returns the bound world and generation while mounted\n");
	}

	/* 6. A preflight for a different map while live is refused without teardown. */
	assert(!hcu_map_service_preflight("beavercreek"));
	expect_live_owner(&service, 1);
	assert(s_unload_calls == 0);
	printf("PASS preflight failure preserves the live owner\n");

	/* Corruption discovered before teardown must retain the old live owner.
	 * Repeat after authorizing a reload to prove a stale authorization is cleared. */
	dispatch.lease_count = 0;
	owner.drain_pending = 1;
	assert(!hcu_map_service_preflight("ui"));
	expect_live_owner(&service, 1);
	map_unloader(&service);
	assert(s_unload_calls == 0 && s_unmount_calls == 0);
	owner.drain_pending = 0;
	assert(hcu_map_service_preflight("ui") == 1);
	package_bytes[package.size - 1u] ^= 1u;
	assert(!hcu_map_service_preflight("ui"));
	expect_live_owner(&service, 1);
	expect_no_stage(&service);
	assert(s_unload_calls == 0);
	package_bytes[package.size - 1u] ^= 1u;
	meta_ok[meta_ok_size - 1u] ^= 1u;
	assert(!hcu_map_service_preflight("ui"));
	expect_live_owner(&service, 1);
	expect_no_stage(&service);
	meta_ok[meta_ok_size - 1u] ^= 1u;
	s_bindings_valid = 0;
	assert(!hcu_map_service_preflight("ui"));
	expect_live_owner(&service, 1);
	expect_no_stage(&service);
	s_bindings_valid = 1;
	printf("PASS corrupt package, metadata and bindings rejected before live teardown\n");

	/* 7. Lease drained: same-map preflight reuses the owner, unload happens, and a
	 * post-unload load failure yields an empty service that can retry. */
	assert(hcu_map_service_set_boundary_hook(&service, record_boundary, &s_boundary_count));
	dispatch.lease_count = 0;
	assert(hcu_map_service_preflight("ui") == 1);
	assert(service.reload_pending && service.runtime_registered);
	map_unloader(&service);
	assert(s_unload_calls == 1 && s_unmount_calls == 1);
	expect_live_owner(&service, 0);
	assert(hcu_map_service_residency_snapshot(&service, &residency_report));
	assert(residency_report.valid && !residency_report.active);
	assert(strcmp(residency_report.map_name, "ui") == 0 && residency_report.cycle == 0u);
	assert(residency_report.map.bound && residency_report.map.capacity_bytes > 0);
	assert(residency_report.map.current_bytes == 0u &&
		residency_report.map.high_water_bytes == 8192u &&
		residency_report.map.evictions == 2u &&
		residency_report.map.refused_evictions == 1u &&
		residency_report.map.resets == 1u);
	assert(residency_report.lifetime.high_water_bytes == 8192u &&
		residency_report.lifetime.resets == 1u);
	s_load_failures_remaining = 1;
	assert(map_loader(&service, "ui") == 0);
	expect_live_owner(&service, 0);
	expect_no_stage(&service);
	assert(service.runtime_registered);
	assert(hcu_map_service_residency_snapshot(&service, &residency_report));
	assert(residency_report.valid && !residency_report.active);
	assert(residency_report.map.current_bytes == 0u &&
		residency_report.map.high_water_bytes == 0u &&
		residency_report.map.resets == 1u);
	assert(residency_report.lifetime.high_water_bytes == 8192u &&
		residency_report.lifetime.resets == 2u);
	printf("PASS post-unload load failure leaves a safe empty state\n");

	/* 8. Retry after the failure publishes again. */
	assert(hcu_map_service_preflight("ui") == 1);
	assert(map_loader(&service, "ui") == 1);
	expect_live_owner(&service, 1);
	assert(hcu_map_service_residency_snapshot(&service, &residency_report));
	assert(residency_report.valid && residency_report.active &&
		residency_report.map.current_bytes == 4096u &&
		residency_report.map.high_water_bytes == 8192u);
	map_unloader(&service);
	expect_live_owner(&service, 0);
	assert(hcu_map_service_residency_snapshot(&service, &residency_report));
	assert(residency_report.valid && !residency_report.active &&
		residency_report.map.current_bytes == 0u &&
		residency_report.map.high_water_bytes == 8192u &&
		residency_report.lifetime.resets == 3u);
	assert(hcu_map_service_unregister_runtime(&service));
	printf("PASS retry after empty state reloads the same runtime\n");

	/* The hook saw release, empty state, load, then release, with the cycle
	 * counting successful loads. */
	assert(s_boundary_count == 4u);
	assert(strcmp(s_boundary_phase[0], "map-released") == 0 && s_boundary_cycle[0] == 0u);
	assert(strcmp(s_boundary_phase[1], "map-empty") == 0 && s_boundary_cycle[1] == 0u);
	assert(strcmp(s_boundary_phase[2], "map-loaded") == 0 && s_boundary_cycle[2] == 1u);
	assert(strcmp(s_boundary_phase[3], "map-released") == 0 && s_boundary_cycle[3] == 1u);
	assert(hcu_map_service_set_boundary_hook(&service, NULL, NULL));
	printf("PASS boundary hook orders release, empty, load and release across a failed reload\n");

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

	/* 11. Foreign replacement A (ui) -> B (beavercreek). A stays live under its
	 * own runtime; B is a distinct runtime with disjoint storage. */
	{
		hcu_map_profile_runtime successor;
		static const char *const ordered[] = {
			"dispose:ui", "unpublish:ui", "prepare:beavercreek",
			"load-fail:beavercreek", "prepare:beavercreek", "publish:beavercreek"
		};
		unsigned unloads_before;
		runtime = make_runtime(&package, package_sha, meta_ok, meta_ok_size,
			meta_ok_sha, s_metadata_storage, sizeof(s_metadata_storage), &owner);
		runtime.renderer_quiesce = scripted_renderer_quiesce;
		runtime.renderer_quiesce_context = &service;
		assert(hcu_map_service_register_runtime(&service, "ui", &runtime));
		successor = make_runtime(&package, package_sha, meta_ok, meta_ok_size,
			meta_ok_sha, s_b_metadata_storage, sizeof(s_b_metadata_storage), &owner);
		successor.relocation_storage = s_b_relocation_storage;
		successor.relocation_storage_bytes = sizeof(s_b_relocation_storage);
		successor.stream_scratch = s_b_stream_scratch;
		successor.stream_scratch_bytes = sizeof(s_b_stream_scratch);
		successor.residency_entries = s_b_residency_entries;
		successor.residency_entry_capacity = sizeof(s_b_residency_entries) /
			sizeof(s_b_residency_entries[0]);
		successor.residency_arena = s_b_residency_arena;
		successor.residency_arena_bytes = sizeof(s_b_residency_arena);
		assert(!hcu_map_service_register_successor_runtime(&service, "ui", &successor));
		assert(hcu_map_service_register_successor_runtime(&service, "beavercreek", &successor));
		assert(!hcu_map_service_register_successor_runtime(&service, "beavercreek", &successor));
		assert(hcu_map_service_preflight("ui") == 1);
		assert(map_loader(&service, "ui") == 1);
		expect_live_owner(&service, 1);
		assert(s_live_tags[0] == 'u');
		unloads_before = s_unload_calls;

		/* A failed successor preparation leaves the live owner A untouched. */
		s_trace_count = 0;
		s_renderer_quiesce_calls = 0;
		s_prepare_result = HCU_PROFILE_MOUNT_E_CAPACITY;
		assert(!hcu_map_service_preflight("beavercreek"));
		s_prepare_result = HCU_PROFILE_MOUNT_OK;
		assert(s_renderer_quiesce_calls == 0);
		expect_live_owner(&service, 1);
		expect_no_stage(&service);
		assert(strcmp(service.profile_mount.source_identity_snapshot.map_name, "ui") == 0);
		assert(s_live_tags[0] == 'u' && s_trace_count == 0);
		printf("PASS successor preparation failure keeps live owner A untouched\n");

		/* B's complete candidate is valid, but a failed renderer drain must
		 * veto teardown while preserving A and discarding only the candidate. */
		s_renderer_quiesce_result = 0;
		assert(!hcu_map_service_preflight("beavercreek"));
		assert(s_renderer_quiesce_calls == 1);
		expect_live_owner(&service, 1);
		expect_no_stage(&service);
		assert(strcmp(service.profile_mount.source_identity_snapshot.map_name, "ui") == 0);
		assert(s_live_tags[0] == 'u' && s_unload_calls == unloads_before);
		assert(s_trace_count == 1 && strcmp(s_trace[0], "prepare:beavercreek") == 0);
		printf("PASS renderer drain refusal preserves the live owner after validated candidate\n");

		/* B validates while A stays live: its prepare publishes nothing, then
		 * and only then the renderer quiesce callback runs. */
		s_renderer_quiesce_result = 1;
		s_trace_count = 0;
		assert(hcu_map_service_preflight("beavercreek") == 1);
		assert(s_renderer_quiesce_calls == 2);
		assert(service.successor_staged && service.reload_pending && service.preflight_ready);
		expect_live_owner(&service, 1);
		assert(s_live_tags[0] == 'u' && s_unload_calls == unloads_before);
		assert(s_trace_count == 1 && strcmp(s_trace[0], "prepare:beavercreek") == 0);
		printf("PASS successor B validates while live owner A stays untouched\n");

		/* A busy renderer blocks the unload: A and the staged B are retained. */
		s_renderer_drained = 0;
		unloads_before = s_unload_calls;
		map_unloader(&service);
		assert(s_unload_calls == unloads_before);
		expect_live_owner(&service, 1);
		assert(service.successor_staged && service.reload_pending);
		s_renderer_drained = 1;
		printf("PASS unload blocked while renderer reports busy keeps A and staged B\n");

		/* A missing renderer predicate fails closed as well. */
		{
			int (*saved)(void *) = service.runtime.renderer_drained;
			service.runtime.renderer_drained = NULL;
			unloads_before = s_unload_calls;
			map_unloader(&service);
			assert(s_unload_calls == unloads_before);
			expect_live_owner(&service, 1);
			service.runtime.renderer_drained = saved;
		}
		printf("PASS missing renderer predicate fails closed\n");

		/* Drained: CE disposes A while its tags are readable, A is unpublished,
		 * and B's staged successor is prepared and loaded. */
		s_trace_count = 0;
		s_dispose_callback = dispose_reads_live_tags;
		unloads_before = s_unload_calls;
		map_unloader(&service);
		s_dispose_callback = NULL;
		assert(s_unload_calls == unloads_before + 1);
		expect_live_owner(&service, 0);
		assert(service.reload_pending && service.successor_staged);
		/* A failed load after A is released leaves a safe empty state, and the
		 * successor stays registered as the runtime for a later retry. */
		s_load_failures_remaining = 1;
		assert(map_loader(&service, "beavercreek") == 0);
		expect_live_owner(&service, 0);
		expect_no_stage(&service);
		assert(service.runtime_registered && !service.successor_registered);
		assert(strcmp(service.runtime_map_name, "beavercreek") == 0);
		assert(s_trace_count == 4);
		assert(strcmp(s_trace[0], ordered[0]) == 0 && strcmp(s_trace[1], ordered[1]) == 0 &&
			strcmp(s_trace[2], ordered[2]) == 0 && strcmp(s_trace[3], ordered[3]) == 0);
		printf("PASS ordered dispose of A, unpublish, then failed B load leaves safe empty state\n");

		/* The retry prepares and loads B from its runtime alone. */
		assert(hcu_map_service_preflight("beavercreek") == 1);
		assert(map_loader(&service, "beavercreek") == 1);
		expect_live_owner(&service, 1);
		expect_trace(ordered, sizeof(ordered) / sizeof(ordered[0]));
		assert(s_live_tags[0] == 'b');
		map_unloader(&service);
		expect_live_owner(&service, 0);
		assert(hcu_map_service_unregister_runtime(&service));
		printf("PASS retry after failed load publishes successor B\n");
	}

#ifdef HALO_HCU_HEADLESS_RUNTIME_GUEST
	/* 11b. Headless candidate admission of a foreign successor (the opt-in C2.8
	 * guest sequence). The successor is admitted under its own runtime when it
	 * names the same partition row as the selected runtime; A's own preflight is
	 * unchanged. Without the successor branch B would be refused as
	 * headless-candidate-capacity. */
	{
		hcu_map_profile_runtime successor;
		s_trace_count = 0;
		runtime = make_runtime(&package, package_sha, meta_ok, meta_ok_size,
			meta_ok_sha, s_metadata_storage, sizeof(s_metadata_storage), NULL);
		runtime.headless_no_bitmap_consumers = 1;
		runtime.renderer_never_started = headless_never_started;
		runtime.headless_candidate_admission = 1;
		runtime.partition_row = "row_a";
		assert(hcu_map_service_register_runtime(&service, "ui", &runtime));
		successor = make_runtime(&package, package_sha, meta_ok, meta_ok_size,
			meta_ok_sha, s_b_metadata_storage, sizeof(s_b_metadata_storage), NULL);
		successor.relocation_storage = s_b_relocation_storage;
		successor.relocation_storage_bytes = sizeof(s_b_relocation_storage);
		successor.stream_scratch = s_b_stream_scratch;
		successor.stream_scratch_bytes = sizeof(s_b_stream_scratch);
		successor.residency_entries = s_b_residency_entries;
		successor.residency_entry_capacity = sizeof(s_b_residency_entries) /
			sizeof(s_b_residency_entries[0]);
		successor.residency_arena = s_b_residency_arena;
		successor.residency_arena_bytes = sizeof(s_b_residency_arena);
		successor.headless_no_bitmap_consumers = 1;
		successor.renderer_never_started = headless_never_started;
		successor.headless_candidate_admission = 1;
		successor.partition_row = "row_a";
		assert(hcu_map_service_register_successor_runtime(&service, "beavercreek", &successor));
		assert(hcu_map_service_preflight("ui") == 1);
		assert(map_loader(&service, "ui") == 1);
		expect_live_owner(&service, 1);
		/* A successor that names another partition row is refused; A stays live. */
		service.successor.partition_row = "row_b";
		assert(!hcu_map_service_preflight("beavercreek"));
		assert(!service.successor_staged);
		expect_live_owner(&service, 1);
		assert(s_live_tags[0] == 'u');
		service.successor.partition_row = "row_a";
		printf("PASS headless admission refuses a successor of another partition row\n");
		/* B passes CE's pre-unload check while A stays live and untouched. */
		assert(hcu_map_service_preflight("beavercreek") == 1);
		assert(service.successor_staged && service.reload_pending);
		expect_live_owner(&service, 1);
		assert(s_live_tags[0] == 'u');
		/* An unknown map is still refused by the same branch. */
		assert(!hcu_map_service_preflight("carousel"));
		assert(hcu_map_service_preflight("beavercreek") == 1);
		s_dispose_callback = dispose_reads_live_tags;
		map_unloader(&service);
		s_dispose_callback = NULL;
		expect_live_owner(&service, 0);
		assert(map_loader(&service, "beavercreek") == 1);
		expect_live_owner(&service, 1);
		assert(s_live_tags[0] == 'b');
		assert(strcmp(service.runtime_map_name, "beavercreek") == 0);
		/* B's own cycles keep being admitted as the selected runtime. */
		map_unloader(&service);
		assert(hcu_map_service_preflight("beavercreek") == 1);
		assert(map_loader(&service, "beavercreek") == 1);
		map_unloader(&service);
		expect_live_owner(&service, 0);
		assert(hcu_map_service_unregister_runtime(&service));
		printf("PASS headless admission accepts a registered foreign successor under its own runtime\n");
	}
#endif

	/* 5. Legacy production path: a busy renderer keeps a published owner, and
	 * the successor load and shutdown are refused until the fence retires. The
	 * owner is simulated by its flag only, so no CTAG unload is reached. */
	assert(hcu_map_service_set_legacy_renderer_drained(&service,
		scripted_legacy_drained, NULL));
	assert(!hcu_map_service_set_legacy_renderer_drained(&service, NULL, NULL));

	/* 5a. A legacy load while the previous mount is still active is refused by
	 * the owner gate, which checks the mount only. The successful first load
	 * after a preflight needs a real CE map with its matching source SHA, which
	 * this fixture does not carry, so it is covered by the guest lifecycle run. */
	assert(!service.mount.active);
	s_legacy_drained = 0;
	service.mount.active = 1;
	assert(!map_loader(&service, "ui"));
	map_unloader(&service);
	assert(service.mount.active);
	service.mount.active = 0;
	printf("PASS legacy load while the previous mount is active is rejected\n");

	s_legacy_drained = 0;
	service.mount.active = 1;
	map_unloader(&service);
	assert(service.mount.active);
	assert(!map_loader(&service, "ui"));
	assert(!hcu_map_service_shutdown(&service));
	assert(service.initialized);
	service.mount.active = 0;
	s_legacy_drained = 1;
	printf("PASS legacy unload, load and shutdown blocked while renderer is busy\n");
	map_unloader(&service);
	assert(!service.mount.active);
	printf("PASS legacy owner released after renderer drains\n");

	assert(s_unbound_prepares == 0);
	printf("PASS every profile prepare saw a residency-bound mount\n");
	hcu_map_service_shutdown(&service);
	free(package_bytes);
	free(meta_ok);
	free(meta_big);
	printf("HALO_PS2_LOCAL map-service-profile-lifecycle passed\n");
	return 0;
}
