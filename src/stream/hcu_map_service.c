#include "stream/hcu_map_service.h"

#include "cache/physical_memory_map.h"
#include "halo_ps2_cache.h"
#include "stream/hcu_map_catalog.h"
#include "ps2_ctag.h"
#include "stream/ctag_ps2_backend.h"
#include "stream/ctag_resource_index.h"
#include "stream/sha256.h"
#include "stream/hcu_load_trace.h"
#include "world/section.h"
#ifdef HALO_PS2_M2_ANIMATION_TRACE
#include "ps2_animation_trace.h"
#endif

#include <stdio.h>
#include <stdint.h>
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

/* A NULL hook is a no-op, so the host fixtures and the default build are unchanged. */
static void notify_boundary(hcu_map_service *service, const char *phase)
{
	if (service->boundary_hook)
		service->boundary_hook(service->boundary_context, phase, service->boundary_cycle);
}

#ifdef HALO_PS2_M2_UI_LIFECYCLE_TEST
static int s_lifecycle_fail_preflight_once;
static int s_lifecycle_deferred_failure_armed;
#endif

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

static int verify_profile_package_hash(hcu_asset_profile_read_at reader,
	void *context, uint32_t size, const uint8_t expected[32])
{
	/* Package identity is checked against mutable backing storage each time. */
	uint8_t small[512], digest[32];
	uint8_t *scratch = small;
	uint32_t cap = (uint32_t)sizeof(small);
	size_t mark = 0;
	int from_arena = 0;
	sha256_context sha;
	uint32_t offset = 0;
	if (!reader || !expected || !size) return 0;
	if (s_service && s_service->section_scratch) {
		size_t free_bytes = arena_free(s_service->section_scratch);
		if (free_bytes > 65536u) free_bytes = 65536u;
		if (free_bytes >= 65536u) {
			mark = arena_mark(s_service->section_scratch);
			scratch = (uint8_t *)arena_alloc(s_service->section_scratch, free_bytes, 64);
			if (scratch) { cap = (uint32_t)free_bytes; from_arena = 1; }
			else { scratch = small; cap = (uint32_t)sizeof(small); }
		}
	}
	sha256_init(&sha);
	while (offset < size) {
		uint32_t take = size - offset;
		if (take > cap) take = cap;
		if (reader(context, offset, scratch, take) != 0) {
			if (from_arena) arena_release(s_service->section_scratch, mark);
			return 0;
		}
		HCU_LOAD_TRACE_READ(take);
		sha256_update(&sha, scratch, take);
		offset += take;
	}
	HCU_LOAD_TRACE_HASH("package", size);
	if (from_arena) arena_release(s_service->section_scratch, mark);
	sha256_final(&sha, digest);
	return memcmp(digest, expected, sizeof(digest)) == 0;
}

static uint8_t *load_section(void *context, arena_t *owner,
	const char *path, const char *tag, size_t *size, int optional)
{
	hcu_map_service *service = (hcu_map_service *)context;
	uint8_t *result;
	size_t mark;
	printf("HALO_PS2_LOCAL map-preflight section-begin %s\n", tag);
	mark = arena_mark(owner);
	result = world_load_section_with_scratch(owner, service->section_scratch,
		path, tag, size, optional);
	if (result && strcmp(tag, "CBIX") == 0 &&
		(!service->staged_entry ||
		 !hcu_map_catalog_validate_bsp_catalog(service->staged_entry,
			 result, *size))) {
		printf("HALO_PS2_LOCAL map-preflight catalog-rejected section=CBIX map=%s\n",
			service->staged_entry ?
				service->staged_entry->identity.map_name : "unset");
		arena_release(owner, mark);
		result = NULL;
		if (size) *size = 0;
	}
	printf("HALO_PS2_LOCAL map-preflight section-end %s bytes=%u ok=%d\n",
		tag, size ? (unsigned)*size : 0u, result != NULL);
	return result;
}

typedef struct {
	ctag_bsp_sink_fn sink;
	void *sink_context;
} section_sink_adapter;

typedef struct {
	uint8_t header[52];
	size_t header_bytes;
	size_t received;
	size_t maximum_image_size;
	uint32_t maximum_relocations;
	arena_t *owner;
	ps2_ctag_stream_validator validator;
	uint8_t *relocations;
	size_t relocation_bytes;
	int initialized;
	int failed;
} ctag_first_pass;

static int visit_section_sink(void *context, uint32_t offset,
	const uint8_t *bytes, size_t size)
{
	section_sink_adapter *adapter = (section_sink_adapter *)context;
	/* halo-ps2 HP2 uses zero for success; the PS2 cache visitor uses
	 * nonzero for success. Keep that convention conversion at this seam. */
	return adapter && adapter->sink &&
		adapter->sink(adapter->sink_context, offset, bytes, size) ? 0 : -1;
}

static int visit_section(void *context, const char *path, const char *tag,
	ctag_bsp_sink_fn sink, void *sink_context, size_t *raw_size)
{
	hcu_map_service *service = (hcu_map_service *)context;
	section_sink_adapter adapter;
	if (!service || !service->section_scratch || !path || !tag || !sink ||
		!raw_size)
		return 0;
	printf("HALO_PS2_LOCAL cbsp-section-visit begin tag=%s descriptor=%d scratch=%u/%u\n",
		tag, service->source.reader.descriptor,
		(unsigned)service->section_scratch->used,
		(unsigned)service->section_scratch->cap);
	{
		adapter.sink = sink;
		adapter.sink_context = sink_context;
		hp2_status status = world_visit_section_with_scratch(service->section_scratch,
		path, tag, raw_size, 0,
		visit_section_sink, &adapter);
		printf("HALO_PS2_LOCAL cbsp-section-visit end status=%d raw=%u\n",
			(int)status, (unsigned)*raw_size);
		return status == HP2_OK;
	}
}

static int feed_ctag_first_pass(void *context, uint32_t offset,
	const uint8_t *bytes, size_t size)
{
	ctag_first_pass *pass = (ctag_first_pass *)context;
	size_t consumed = 0;
	if (!pass || (!bytes && size) || offset != pass->received) return 0;
	while (consumed < size && !pass->initialized) {
		size_t take = sizeof(pass->header) - pass->header_bytes;
		ps2_ctag_status status;
		uint32_t relocation_count;
		if (take > size - consumed) take = size - consumed;
		memcpy(pass->header + pass->header_bytes, bytes + consumed, take);
		pass->header_bytes += take;
		consumed += take;
		if (pass->header_bytes < sizeof(pass->header)) continue;
		relocation_count = (uint32_t)pass->header[16] |
			((uint32_t)pass->header[17] << 8) |
			((uint32_t)pass->header[18] << 16) |
			((uint32_t)pass->header[19] << 24);
		if (relocation_count > pass->maximum_relocations) {
			pass->failed = 1;
			return 0;
		}
		pass->relocation_bytes = (size_t)relocation_count * 4u;
		pass->relocations = (uint8_t *)arena_alloc(pass->owner,
			pass->relocation_bytes, 4u);
		if (!pass->relocations) {
			printf("HALO_PS2_LOCAL map-preflight ctag-relocation-allocation-failed "
				"bytes=%u used=%u cap=%u\n",
				(unsigned)pass->relocation_bytes,
				(unsigned)pass->owner->used,
				(unsigned)pass->owner->cap);
			pass->failed = 1;
			return 0;
		}
		status = ps2_ctag_stream_validator_begin(&pass->validator,
			pass->header, sizeof(pass->header), (size_t)-1,
			pass->relocations, pass->relocation_bytes,
			pass->maximum_image_size, pass->maximum_relocations);
		if (status != PS2_CTAG_OK) {
			pass->failed = 1;
			return 0;
		}
		pass->initialized = 1;
	}
	if (consumed < size && ps2_ctag_stream_validator_write(
		&pass->validator, (uint32_t)pass->received +
			(uint32_t)consumed, bytes + consumed, size - consumed) !=
		PS2_CTAG_OK) {
		pass->failed = 1;
		return 0;
	}
	pass->received += size;
	return 1;
}

/* CTAG's HP2 section is replayed by bounded visitors rather than materialized
 * beside HMAP/CRNG/CBIX. One visitor validates outer HP2 CRC, inner image CRC,
 * CE tag table, and relocation field structure. Relative target values are
 * checked by the complete parser/rebaser against the final tag-cache image
 * before CE publishes any pointers. */
static int preflight_ctag_stream(hcu_map_service *service,
	const char *pack_path, size_t maximum_image_size,
	arena_t *owner, ctag_stream_info *result)
{
	ps2_ctag_stream_info info;
	ctag_first_pass first_pass;
	size_t raw_size = 0, mark;
	uint32_t maximum_relocations;
	ps2_ctag_status status;
	int ok = 0;
	if (!service || !pack_path || !owner || !result ||
		maximum_image_size < 36u)
		return 0;
	memset(&first_pass, 0, sizeof(first_pass));
	maximum_relocations = (uint32_t)(maximum_image_size / 4u);
	mark = arena_mark(owner);
	first_pass.owner = owner;
	first_pass.maximum_image_size = maximum_image_size;
	first_pass.maximum_relocations = maximum_relocations;
	status = PS2_CTAG_ERR_IO;
	if (visit_section(service, pack_path, "CTAG", feed_ctag_first_pass,
		&first_pass, &raw_size) && !first_pass.failed &&
		first_pass.initialized && raw_size == first_pass.validator.payload_size) {
		status = ps2_ctag_stream_validator_finish(&first_pass.validator, &info);
		if (status == PS2_CTAG_OK) ok = 1;
	}
	if (ok) {
		result->image_size = info.image_size;
		result->relocation_count = info.relocation_count;
		result->scenario_tag_index = info.scenario_tag_index;
	} else {
		printf("HALO_PS2_LOCAL map-preflight ctag-stream-rejected status=%d failed=%d\n",
			(int)status, first_pass.failed);
	}
	arena_release(owner, mark);
	return ok;
}

static void clear_staged_request(hcu_map_service *service)
{
	if (!service) return;
	/* A live mount may still depend on its source reader. Failure cleanup may
	 * close only a reader that is not owned by an active map mount. */
	if (!service->mount.active && service->source.active)
		ctag_map_source_close(&service->source);
	service->preflight_ready = 0;
	service->reload_pending = 0;
	memset(&service->ctag_info, 0, sizeof(service->ctag_info));
	service->staged_map[0] = 0;
	service->staged_entry = NULL;
}

/* port: HCP runtime lifecycle. The live owner is service->profile_mount. A
 * successor is prepared only into profile_candidate, which never aliases a live
 * span, and it is copied into the live slot only after CE has unpublished the
 * old owner. Every profile-path failure leaves either the untouched old owner
 * or an empty owner with no stage. */
static int span_overlaps(const void *left, size_t left_bytes,
	const void *right, size_t right_bytes)
{
	uintptr_t a = (uintptr_t)left, b = (uintptr_t)right;
	if (!left_bytes || !right_bytes) return 0;
	/* Fail closed on address overflow. */
	if (left_bytes > UINTPTR_MAX - a || right_bytes > UINTPTR_MAX - b) return 1;
	return a < b + right_bytes && b < a + left_bytes;
}

/* Residency entries and the segment arena are caller-owned spans like the
 * rest, so they join the same disjointness check. */
#define RUNTIME_SPAN_COUNT 5

static void runtime_spans(const hcu_map_profile_runtime *runtime,
	const void *base[RUNTIME_SPAN_COUNT], size_t bytes[RUNTIME_SPAN_COUNT])
{
	base[0] = runtime->metadata_storage;
	bytes[0] = runtime->metadata_storage_bytes;
	base[1] = runtime->relocation_storage;
	bytes[1] = runtime->relocation_storage_bytes;
	base[2] = runtime->stream_scratch;
	bytes[2] = runtime->stream_scratch_bytes;
	base[3] = runtime->residency_entries;
	bytes[3] = (size_t)runtime->residency_entry_capacity *
		sizeof(*runtime->residency_entries);
	base[4] = runtime->residency_arena;
	bytes[4] = runtime->residency_arena_bytes;
}

/* A runtime must carry whole 64 KiB residency slots; a missing or ragged arena
 * fails closed, since the mount would otherwise fall back to whole-chunk reads. */
static int runtime_residency_valid(const hcu_map_profile_runtime *runtime)
{
	return runtime->residency_entries && runtime->residency_entry_capacity &&
		runtime->residency_arena &&
		runtime->residency_arena_bytes >= HCU_PROFILE_MOUNT_RESIDENCY_SEGMENT_BYTES &&
		runtime->residency_arena_bytes % HCU_PROFILE_MOUNT_RESIDENCY_SEGMENT_BYTES == 0 &&
		((uintptr_t)runtime->residency_arena & 15u) == 0;
}

static int runtime_spans_valid(const hcu_map_profile_runtime *runtime)
{
	const void *base[RUNTIME_SPAN_COUNT];
	size_t bytes[RUNTIME_SPAN_COUNT];
	int i, j;
	runtime_spans(runtime, base, bytes);
	for (i = 0; i < RUNTIME_SPAN_COUNT; ++i)
		if (!base[i] || !bytes[i]) return 0;
	for (i = 0; i < RUNTIME_SPAN_COUNT; ++i)
		for (j = i + 1; j < RUNTIME_SPAN_COUNT; ++j)
			if (span_overlaps(base[i], bytes[i], base[j], bytes[j])) return 0;
	return 1;
}

/* Binds the runtime's residency before every prepare. Prepare on an unbound
 * mount would read whole chunks, so a failed bind stops the stage. */
static int profile_bind_residency(hcu_profile_mount *mount,
	const hcu_map_profile_runtime *rt)
{
	return runtime_residency_valid(rt) &&
		hcu_profile_mount_bind_residency(mount, rt->residency_entries,
			rt->residency_entry_capacity, rt->residency_arena,
			rt->residency_arena_bytes) == HCU_PROFILE_MOUNT_OK;
}

/* The bitmap frame owner's own state is the lease drain hook: no frame in
 * progress, no GPU work pending, and no dispatcher lease outstanding. A missing
 * or unbound owner cannot prove drain, so it fails closed. */
/* Every span of one runtime against every span of another. Storage that
 * overlaps would let a successor's prepare write under the live owner. */
static int runtime_spans_disjoint(const hcu_map_profile_runtime *left,
	const hcu_map_profile_runtime *right)
{
	const void *base_left[RUNTIME_SPAN_COUNT];
	const void *base_right[RUNTIME_SPAN_COUNT];
	size_t bytes_left[RUNTIME_SPAN_COUNT], bytes_right[RUNTIME_SPAN_COUNT];
	int i, j;
	runtime_spans(left, base_left, bytes_left);
	runtime_spans(right, base_right, bytes_right);
	for (i = 0; i < RUNTIME_SPAN_COUNT; ++i)
		for (j = 0; j < RUNTIME_SPAN_COUNT; ++j)
			if (span_overlaps(base_left[i], bytes_left[i], base_right[j],
					bytes_right[j]))
				return 0;
	return 1;
}

/* The bitmap frame owner's own state is the lease drain hook: no frame in
 * progress, no GPU work pending, and no dispatcher lease outstanding. The
 * parent renderer's predicate adds the DMA fence and the world/texture
 * release. A missing owner, unbound owner or predicate cannot prove drain, so
 * it fails closed. */
static int profile_readers_drained(const hcu_map_service *service,
	const hcu_map_profile_runtime *rt)
{
	const hcu_bitmap_frame_owner *owner = rt->frame_owner;
	/* C3.11: every renderer reader registered against the live owner must have
	 * released its reference (VIF/GS retired) before drain can succeed. */
	if (service->reader_count != 0)
		return 0;
	if (!owner)
		return rt->headless_no_bitmap_consumers &&
			rt->renderer_never_started &&
			rt->renderer_never_started(rt->renderer_start_context) != 0 &&
			ps2_cache_bsp_readers_drained() && rt->renderer_drained &&
			rt->renderer_drained(rt->renderer_context) != 0;
	return owner && owner->bound && !owner->in_frame && !owner->gpu_pending &&
		owner->dispatch && owner->dispatch->lease_count == 0 &&
		ps2_cache_bsp_readers_drained() && rt->renderer_drained &&
		rt->renderer_drained(rt->renderer_context) != 0;
}

static int profile_owner_live(const hcu_map_service *service);

/* The renderer is allowed to keep live source references through candidate
 * validation. Quiesce only at the authorization boundary, after every
 * successor input has passed its read-only/isolated preflight. */
static int profile_quiesce_renderer(hcu_map_service *service,
	const hcu_map_profile_runtime *rt, const char *successor_map)
{
	const char *old_map = "unset";
	int callback_ok = 1;
	if (!service || !rt) return 0;
	if (profile_owner_live(service))
		old_map = service->profile_mount.source_identity_snapshot.map_name;
	printf("HALO_PS2_LOCAL map-replacement phase=quiesce-begin old=%s new=%s readers=%u callback=%d\n",
		old_map, successor_map ? successor_map : "unset",
		(unsigned)service->reader_count, rt->renderer_quiesce != NULL);
	if (rt->renderer_quiesce)
		callback_ok = rt->renderer_quiesce(rt->renderer_quiesce_context) != 0;
	callback_ok = callback_ok && profile_readers_drained(service, rt);
	printf("HALO_PS2_LOCAL map-replacement phase=quiesce-end old=%s new=%s readers=%u drained=%d\n",
		old_map, successor_map ? successor_map : "unset",
		(unsigned)service->reader_count, callback_ok);
	return callback_ok;
}

static int profile_owner_live(const hcu_map_service *service)
{
	return service->profile_mount.active || service->profile_mount.backend_mounted;
}

static void reader_table_clear(hcu_map_service *service)
{
	memset(service->readers, 0, sizeof(service->readers));
	service->reader_count = 0;
	service->world_bound = 0;
	service->world_bsp = NULL;
	service->world_source = NULL;
}

int hcu_map_service_bind_world(hcu_map_service *service,
	const struct bsp_section *bsp, const void *source)
{
	if (!service || !bsp || !source || !profile_owner_live(service))
		return 0;
	service->world_bsp = bsp;
	service->world_source = source;
	service->world_bound = 1;
	return 1;
}

int hcu_map_service_current_world(const hcu_map_service *service,
	const struct bsp_section **bsp, const void **source, uint32_t *generation)
{
	if (bsp) *bsp = NULL;
	if (source) *source = NULL;
	if (generation) *generation = 0;
	if (!service || !service->world_bound || !profile_owner_live(service))
		return 0;
	if (bsp) *bsp = service->world_bsp;
	if (source) *source = service->world_source;
	if (generation) *generation = service->boundary_cycle;
	return 1;
}

static uint32_t residency_sat_add(uint32_t left, uint32_t right)
{
	return left > UINT32_MAX - right ? UINT32_MAX : left + right;
}

static void record_residency_release(hcu_map_service *service,
	const char *map_name, unsigned int cycle,
	const hcu_profile_residency_stats *stats)
{
	hcu_profile_residency_stats *life;
	size_t n;
	if (!service || !map_name || !stats || !stats->bound) return;
	service->residency_last = *stats;
	service->residency_last_map[0] = 0;
	n = strlen(map_name);
	if (n >= sizeof(service->residency_last_map))
		n = sizeof(service->residency_last_map) - 1u;
	memcpy(service->residency_last_map, map_name, n);
	service->residency_last_map[n] = 0;
	service->residency_last_cycle = cycle;
	service->residency_last_valid = 1;

	life = &service->residency_lifetime;
	life->bound = 1;
	if (stats->capacity_bytes > life->capacity_bytes)
		life->capacity_bytes = stats->capacity_bytes;
	if (stats->high_water_bytes > life->high_water_bytes)
		life->high_water_bytes = stats->high_water_bytes;
	life->evictions = residency_sat_add(life->evictions, stats->evictions);
	life->refused_evictions = residency_sat_add(life->refused_evictions,
		stats->refused_evictions);
	life->refused_pins = residency_sat_add(life->refused_pins,
		stats->refused_pins);
	life->verify_failures = residency_sat_add(life->verify_failures,
		stats->verify_failures);
	life->resets = residency_sat_add(life->resets, stats->resets);
}

int hcu_map_service_residency_snapshot(const hcu_map_service *service,
	hcu_map_residency_report *report)
{
	if (!service || !report) return 0;
	memset(report, 0, sizeof(*report));
	report->lifetime = service->residency_lifetime;
	if (profile_owner_live(service)) {
		if (hcu_profile_mount_residency_snapshot(&service->profile_mount,
			&report->map) != HCU_PROFILE_MOUNT_OK) return 0;
		memcpy(report->map_name,
			service->profile_mount.source_identity_snapshot.map_name,
			sizeof(report->map_name));
		report->map_name[sizeof(report->map_name) - 1u] = 0;
		report->cycle = service->boundary_cycle;
		report->active = 1;
		report->valid = report->map.bound;
	} else if (service->residency_last_valid) {
		report->map = service->residency_last;
		memcpy(report->map_name, service->residency_last_map,
			sizeof(report->map_name));
		report->cycle = service->residency_last_cycle;
		report->valid = report->map.bound;
	}
	/* Lifetime high/capacity/event counters aggregate released maps; current is
	 * always the exact current owner bytes of the active or last map. */
	report->lifetime.current_bytes = report->valid ? report->map.current_bytes : 0;
	if (report->active) {
		report->lifetime.evictions = residency_sat_add(report->lifetime.evictions,
			report->map.evictions);
		report->lifetime.refused_evictions = residency_sat_add(
			report->lifetime.refused_evictions, report->map.refused_evictions);
		report->lifetime.refused_pins = residency_sat_add(
			report->lifetime.refused_pins, report->map.refused_pins);
		report->lifetime.verify_failures = residency_sat_add(
			report->lifetime.verify_failures, report->map.verify_failures);
	}
	if (report->valid && report->map.capacity_bytes > report->lifetime.capacity_bytes)
		report->lifetime.capacity_bytes = report->map.capacity_bytes;
	if (report->valid && report->map.high_water_bytes > report->lifetime.high_water_bytes)
		report->lifetime.high_water_bytes = report->map.high_water_bytes;
	return 1;
}

static void discard_profile_candidate(hcu_map_service *service)
{
	hcu_profile_mount_init(&service->profile_candidate);
	service->profile_candidate_ready = 0;
	service->preflight_ready = 0;
	service->reload_pending = 0;
	service->successor_staged = 0;
	service->staged_map[0] = 0;
	service->staged_entry = NULL;
}

/* Stages a foreign successor under its own runtime. The live owner keeps its
 * storage and mount: nothing here publishes, and the successor's spans were
 * checked disjoint from the registered runtime's at registration. */
static int profile_preflight_successor(hcu_map_service *service,
	const hcu_map_catalog_entry *entry)
{
	const hcu_map_profile_runtime *rt = &service->successor;
	hcu_asset_profile_view *view = &service->successor_view;
	hcu_profile_metadata_view metadata;
	discard_profile_candidate(service);
	if (!runtime_spans_valid(rt) || !runtime_spans_disjoint(&service->runtime, rt) ||
		rt->maximum_tag_image_bytes == 0 ||
		(unsigned long)rt->maximum_tag_image_bytes >
			physical_memory_get_tag_cache_size()) {
		printf("HALO_PS2_LOCAL profile-preflight rejected reason=successor-capacity-or-spans map=%s\n",
			entry->identity.map_name);
		return 0;
	}
	if (hcu_asset_profile_preflight_reader(rt->package_read_at,
			rt->package_context, rt->package_size, rt->profile_id, view) != HCU_ASSET_PROFILE_OK ||
		!verify_profile_package_hash(rt->package_read_at, rt->package_context,
			rt->package_size, rt->package_sha256) ||
		!rt->compatibility ||
		!rt->compatibility(rt->compatibility_context, entry, view)) {
		printf("HALO_PS2_LOCAL profile-preflight rejected reason=successor-package-gate map=%s\n",
			entry->identity.map_name);
		return 0;
	}
	if (hcu_profile_metadata_decode(rt->metadata_bytes, rt->metadata_size,
			rt->metadata_sha256, rt->profile_id, rt->metadata_storage,
			rt->metadata_storage_bytes, &metadata) != HCU_PROFILE_METADATA_OK ||
		metadata.cbsp_count > 0xffffu) {
		printf("HALO_PS2_LOCAL profile-preflight rejected reason=successor-metadata map=%s\n",
			entry->identity.map_name);
		return 0;
	}
	hcu_profile_mount_init(&service->profile_candidate);
	if (!profile_bind_residency(&service->profile_candidate, rt)) {
		printf("HALO_PS2_LOCAL profile-preflight rejected reason=successor-residency-bind map=%s\n",
			entry->identity.map_name);
		hcu_profile_mount_init(&service->profile_candidate);
		return 0;
	}
	if (hcu_profile_mount_prepare(&service->profile_candidate, view,
			rt->profile_id, entry, metadata.cbsp_bindings,
			(uint16_t)metadata.cbsp_count, metadata.resource_ranges,
			metadata.resource_range_count, rt->source_read, rt->source_context,
			service->backend, rt->maximum_tag_image_bytes,
			rt->relocation_storage, rt->relocation_storage_bytes,
			rt->stream_scratch, rt->stream_scratch_bytes) != HCU_PROFILE_MOUNT_OK) {
		printf("HALO_PS2_LOCAL profile-preflight rejected reason=successor-mount-prepare map=%s\n",
			entry->identity.map_name);
		hcu_profile_mount_init(&service->profile_candidate);
		return 0;
	}
	printf("HALO_PS2_LOCAL map-replacement phase=candidate-validated old=%s new=%s readers=%u\n",
		service->profile_mount.source_identity_snapshot.map_name,
		entry->identity.map_name, (unsigned)service->reader_count);
	/* Candidate bytes and metadata are now fully validated in storage disjoint
	 * from the live owner. Only now may the actual renderer release old-map
	 * readers; failure leaves CE and the mounted owner intact. */
	if (!profile_quiesce_renderer(service, &service->runtime,
		entry->identity.map_name)) {
		discard_profile_candidate(service);
		printf("HALO_PS2_LOCAL profile-preflight rejected reason=renderer-quiesce map=%s readers=%u\n",
			entry->identity.map_name, (unsigned)service->reader_count);
		return 0;
	}
	/* The successor replaces the live owner, so its stage is a reload. */
	service->profile_candidate_ready = 1;
	service->successor_staged = 1;
	service->reload_pending = 1;
	service->staged_entry = entry;
	memcpy(service->staged_map, entry->identity.map_name,
		strlen(entry->identity.map_name) + 1);
	service->preflight_ready = 1;
	printf("HALO_PS2_LOCAL profile-preflight result=1 map=%s successor=1\n",
		entry->identity.map_name);
	return 1;
}

static int profile_preflight(hcu_map_service *service,
	const hcu_map_catalog_entry *entry)
{
	const hcu_map_profile_runtime *rt = &service->runtime;
	hcu_asset_profile_view candidate;
	hcu_profile_metadata_view metadata;
	if (!service->runtime_registered || !entry)
		return 0;
	if (strcmp(service->runtime_map_name, entry->identity.map_name) != 0) {
		if (service->successor_registered &&
			strcmp(service->successor_map_name, entry->identity.map_name) == 0)
			return profile_preflight_successor(service, entry);
		return 0;
	}
	if (profile_owner_live(service)) {
		uint8_t metadata_digest[32];
		sha256_context metadata_hash;
		/* Revalidate the exact successor before authorizing CE teardown. Decode
		 * buffers and relocation storage still belong to the live map here, so
		 * check their retained pins instead of writing a second prepare over them. */
		if (strcmp(service->profile_mount.source_identity_snapshot.map_name,
			entry->identity.map_name) != 0) {
			printf("HALO_PS2_LOCAL profile-preflight rejected reason=owner-live map=%s\n",
				entry->identity.map_name);
			return 0;
		}
		if (!rt->metadata_bytes || !rt->metadata_size ||
			rt->metadata_size > UINT32_MAX || !runtime_spans_valid(rt) ||
			!hcu_profile_mount_inputs_match(&service->profile_mount) ||
			hcu_asset_profile_preflight_reader(rt->package_read_at,
				rt->package_context, rt->package_size, rt->profile_id,
				&candidate) != HCU_ASSET_PROFILE_OK ||
			!verify_profile_package_hash(rt->package_read_at, rt->package_context,
				rt->package_size, rt->package_sha256) ||
			!rt->compatibility || !rt->compatibility(rt->compatibility_context,
				entry, &candidate)) {
			discard_profile_candidate(service);
			printf("HALO_PS2_LOCAL profile-preflight rejected reason=live-successor-gate\n");
			return 0;
		}
		sha256_init(&metadata_hash);
		sha256_update(&metadata_hash, rt->metadata_bytes, (uint32_t)rt->metadata_size);
		sha256_final(&metadata_hash, metadata_digest);
		if (memcmp(metadata_digest, rt->metadata_sha256, sizeof(metadata_digest))) {
			discard_profile_candidate(service);
			printf("HALO_PS2_LOCAL profile-preflight rejected reason=live-metadata-pin\n");
			return 0;
		}
		printf("HALO_PS2_LOCAL map-replacement phase=candidate-validated old=%s new=%s readers=%u same-map=1\n",
			service->profile_mount.source_identity_snapshot.map_name,
			entry->identity.map_name, (unsigned)service->reader_count);
		if (!profile_quiesce_renderer(service, rt,
			entry->identity.map_name)) {
			discard_profile_candidate(service);
			printf("HALO_PS2_LOCAL profile-preflight rejected reason=renderer-quiesce map=%s readers=%u\n",
				entry->identity.map_name, (unsigned)service->reader_count);
			return 0;
		}
		service->staged_entry = entry;
		memcpy(service->staged_map, entry->identity.map_name,
			strlen(entry->identity.map_name) + 1);
		service->reload_pending = 1;
		return 1;
	}
	/* A new attempt supersedes every earlier empty-state stage, including when
	 * corruption is detected before metadata or mount preparation can run. */
	discard_profile_candidate(service);
	if (!runtime_spans_valid(rt) || rt->maximum_tag_image_bytes == 0 ||
		(unsigned long)rt->maximum_tag_image_bytes >
			physical_memory_get_tag_cache_size()) {
		printf("HALO_PS2_LOCAL profile-preflight rejected reason=capacity-or-spans\n");
		return 0;
	}
	if (hcu_asset_profile_preflight_reader(rt->package_read_at,
			rt->package_context, rt->package_size, rt->profile_id,
			&candidate) != HCU_ASSET_PROFILE_OK ||
		!verify_profile_package_hash(rt->package_read_at, rt->package_context,
			rt->package_size, rt->package_sha256) ||
		!rt->compatibility ||
		!rt->compatibility(rt->compatibility_context, entry, &candidate)) {
		printf("HALO_PS2_LOCAL profile-preflight rejected reason=package-gate map=%s\n",
			entry->identity.map_name);
		return 0;
	}
	service->profile_view = candidate;
	if (hcu_profile_metadata_decode(rt->metadata_bytes, rt->metadata_size,
			rt->metadata_sha256, rt->profile_id, rt->metadata_storage,
			rt->metadata_storage_bytes, &metadata) != HCU_PROFILE_METADATA_OK ||
		metadata.cbsp_count > 0xffffu) {
		printf("HALO_PS2_LOCAL profile-preflight rejected reason=metadata\n");
		return 0;
	}
	hcu_profile_mount_init(&service->profile_candidate);
	if (!profile_bind_residency(&service->profile_candidate, rt)) {
		printf("HALO_PS2_LOCAL profile-preflight rejected reason=residency-bind map=%s\n",
			entry->identity.map_name);
		hcu_profile_mount_init(&service->profile_candidate);
		return 0;
	}
	if (hcu_profile_mount_prepare(&service->profile_candidate,
			&service->profile_view, rt->profile_id, entry,
			metadata.cbsp_bindings, (uint16_t)metadata.cbsp_count,
			metadata.resource_ranges, metadata.resource_range_count,
			rt->source_read, rt->source_context, service->backend,
			rt->maximum_tag_image_bytes, rt->relocation_storage,
			rt->relocation_storage_bytes, rt->stream_scratch,
			rt->stream_scratch_bytes) != HCU_PROFILE_MOUNT_OK) {
		printf("HALO_PS2_LOCAL profile-preflight rejected reason=mount-prepare map=%s\n",
			entry->identity.map_name);
		hcu_profile_mount_init(&service->profile_candidate);
		return 0;
	}
	service->profile_candidate_ready = 1;
	service->staged_entry = entry;
	memcpy(service->staged_map, entry->identity.map_name,
		strlen(entry->identity.map_name) + 1);
	service->preflight_ready = 1;
	printf("HALO_PS2_LOCAL profile-preflight result=1 map=%s\n", entry->identity.map_name);
	return 1;
}

static int profile_load(hcu_map_service *service, const char *map_name)
{
	const hcu_map_catalog_entry *entry;
	if (profile_owner_live(service)) {
		printf("HALO_PS2_LOCAL profile-load rejected reason=owner-still-active\n");
		if (service->reload_pending) discard_profile_candidate(service);
		return 0;
	}
	if (service->reload_pending && !service->preflight_ready &&
		!hcu_map_service_preflight(map_name)) {
		discard_profile_candidate(service);
		return 0;
	}
	if (!(entry = service->staged_entry) || !service->profile_candidate_ready ||
		!map_name || strcmp(service->staged_map, entry->identity.map_name) != 0 ||
		hcu_map_catalog_find(map_name) != entry) {
		if (service->reload_pending) discard_profile_candidate(service);
		return 0;
	}
	if (service->successor_staged) {
		/* CE has released the old owner, so the successor's runtime becomes the
		 * registered one. A failed load below leaves it registered for a retry. */
		service->runtime = service->successor;
		memset(service->runtime_map_name, 0, sizeof(service->runtime_map_name));
		memcpy(service->runtime_map_name, service->successor_map_name,
			strlen(service->successor_map_name) + 1);
		service->profile_view = service->successor_view;
		service->successor_registered = 0;
		service->successor_staged = 0;
	}
	reader_table_clear(service);
	service->profile_mount = service->profile_candidate;
	hcu_profile_mount_init(&service->profile_candidate);
	service->profile_candidate_ready = 0;
	HCU_LOAD_TRACE_BEGIN("mount-load");
	if (hcu_profile_mount_load(&service->profile_mount) != HCU_PROFILE_MOUNT_OK) {
	HCU_LOAD_TRACE_END("mount-load");
		hcu_profile_residency_stats released_stats;
		/* Safe empty state: no backend is published and no stage remains. The
		 * registered runtime stays available, so a later corrected preflight may
		 * retry. */
		if (hcu_profile_mount_unload_with_residency_stats(
			&service->profile_mount, &released_stats) == HCU_PROFILE_MOUNT_OK)
			record_residency_release(service, entry->identity.map_name,
				service->boundary_cycle, &released_stats);
		hcu_profile_mount_init(&service->profile_mount);
		service->preflight_ready = 0;
		service->reload_pending = 0;
		service->staged_map[0] = 0;
		service->staged_entry = NULL;
		printf("HALO_PS2_LOCAL profile-load failed map=%s state=empty\n",
			entry->identity.map_name);
		notify_boundary(service, "map-empty");
		return 0;
	}
	service->preflight_ready = 0;
	service->reload_pending = 0;
	service->staged_map[0] = 0;
	service->staged_entry = NULL;
	printf("HALO_PS2_LOCAL map-mount result=1 active=1 map=%s source=profile-runtime\n",
		entry->identity.map_name);
#ifdef HALO_PS2_M2_ANIMATION_TRACE
	ps2_animation_trace_map_epoch_advance();
#endif
	service->boundary_cycle++;
	HCU_LOAD_TRACE_END("mount-load");
	notify_boundary(service, "map-loaded");
	return 1;
}

static void profile_unload(hcu_map_service *service)
{
	int preserve_reload = service->reload_pending;
	int owner_live = profile_owner_live(service);
	if (owner_live) {
		hcu_profile_residency_stats released_stats;
		char released_map_name[16];
		/* CE's unloader cannot report failure. Keep the mount and its storage
		 * published rather than unmount under a live bitmap reader; profile_load
		 * refuses while the owner remains live. */
		if (!profile_readers_drained(service, &service->runtime)) {
			printf("HALO_PS2_LOCAL profile-unload blocked reason=bitmap-leases-outstanding\n");
			return;
		}
		memcpy(released_map_name,
			service->profile_mount.source_identity_snapshot.map_name,
			sizeof(released_map_name));
		released_map_name[sizeof(released_map_name) - 1u] = 0;
		if (hcu_profile_mount_unload_with_residency_stats(
			&service->profile_mount, &released_stats) != HCU_PROFILE_MOUNT_OK) {
			printf("HALO_PS2_LOCAL profile-unload blocked reason=callbacks-active\n");
			return;
		}
		record_residency_release(service, released_map_name,
			service->boundary_cycle, &released_stats);
		service->world_bound = 0;
		service->world_bsp = NULL;
		service->world_source = NULL;
	}
#ifdef HALO_PS2_M2_ANIMATION_TRACE
	ps2_animation_trace_map_epoch_advance();
#endif
	service->preflight_ready = 0;
	if (!preserve_reload) discard_profile_candidate(service);
	if (owner_live) notify_boundary(service, "map-released");
}

int hcu_map_service_reader_acquire(hcu_map_service *service,
	hcu_map_reader_kind kind, const void *source, uint32_t bytes,
	hcu_map_reader_ref *ref)
{
	uint32_t i;
	if (ref) memset(ref, 0, sizeof(*ref));
	if (!service || !ref || !source || bytes == 0 ||
		kind <= HCU_MAP_READER_NONE || kind > HCU_MAP_READER_SOURCE_SPAN ||
		!profile_owner_live(service)) {
		if (service) service->reader_refused++;
		return 0;
	}
	for (i = 0; i < HCU_MAP_READER_CAPACITY; ++i) {
		hcu_map_reader_slot *slot = &service->readers[i];
		if (slot->live) continue;
		service->reader_generation++;
		if (service->reader_generation == 0) service->reader_generation = 1;
		memset(slot, 0, sizeof(*slot));
		slot->kind = (uint8_t)kind;
		slot->live = 1;
		slot->generation = service->reader_generation;
		slot->map_cycle = service->boundary_cycle;
		slot->source = source;
		slot->bytes = bytes;
		service->reader_count++;
		ref->slot = i;
		ref->generation = slot->generation;
		return 1;
	}
	service->reader_refused++;
	return 0;
}

int hcu_map_service_reader_release(hcu_map_service *service,
	hcu_map_reader_ref ref)
{
	hcu_map_reader_slot *slot;
	if (!service || ref.slot >= HCU_MAP_READER_CAPACITY) return 0;
	slot = &service->readers[ref.slot];
	if (!slot->live || slot->generation != ref.generation) return 0;
	memset(slot, 0, sizeof(*slot));
	service->reader_count--;
	return 1;
}

uint32_t hcu_map_service_reader_count(const hcu_map_service *service)
{
	return service ? service->reader_count : 0;
}

int hcu_map_service_readers_drained(const hcu_map_service *service)
{
	if (!service || service->reader_count != 0) return 0;
	return !service->runtime_registered || !profile_owner_live(service) ||
		profile_readers_drained(service, &service->runtime);
}

/* Legacy owners release only after the renderer's fence has retired. Without a
 * predicate (host fixtures) the legacy path behaves as before. */
static int legacy_renderer_ready(const hcu_map_service *service)
{
	return !service->legacy_renderer_drained ||
		service->legacy_renderer_drained(service->legacy_renderer_context) != 0;
}

static int legacy_owner_live(const hcu_map_service *service)
{
	return service->mount.active || service->source.active;
}

static int map_loader(void *context, const char *map_name)
{
	hcu_map_service *service = (hcu_map_service *)context;
	const hcu_map_catalog_entry *entry;
	int result;
	if (!service || !service->initialized) return 0;
	if (service->runtime_registered) return profile_load(service, map_name);
	if (service->legacy_renderer_drained && service->mount.active) {
		/* The previous mount was not released, so its storage is still in use.
		 * An open source alone is the validated stage this load consumes. */
		printf("HALO_PS2_LOCAL map-mount rejected reason=owner-still-active\n");
		clear_staged_request(service);
		return 0;
	}
	/* A deferred reload is legal only after CE has actually released the old
	 * owner. Otherwise do not mistake the active map's same-map shortcut for a
	 * fresh post-unload validation pass. */
	if (service->reload_pending &&
		(service->mount.active || service->source.active)) {
		printf("HALO_PS2_LOCAL map-reload rejected reason=owner-still-active\n");
		clear_staged_request(service);
		return 0;
	}
	/* CE preflights before game_unload(). For a same-map reload the active
	 * package was already qualified, but the full byte/CRC/source checks must
	 * run again after its owner is released and before the new cache is mounted. */
	if (service && service->reload_pending && !service->preflight_ready &&
		!hcu_map_service_preflight(map_name)) {
		clear_staged_request(service);
		return 0;
	}
	if (!(entry = service->staged_entry) ||
		!service->preflight_ready ||
		strcmp(service->staged_map, entry->identity.map_name) != 0 ||
		!map_name || hcu_map_catalog_find(map_name) != entry) {
		/* A mismatched cache request must not consume a previously validated
		 * request: CE may probe/reject another scenario before loading the
		 * staged one. Only a deferred reload owns cleanup responsibility here. */
		if (service->reload_pending)
			clear_staged_request(service);
		return 0;
	}
	HCU_TRACE("HALO_PS2_LOCAL map-mount begin %s\n",
		entry->identity.map_name);
	result = ctag_mount_hp2_stream_verified_source_discover(&service->mount,
		service->map_arena, service->section_scratch,
		entry->hp2_path, entry->scenario_name,
		service->identity.tag_data_offset, service->identity.tag_data_size,
		service->identity.file_length, ctag_map_source_read,
		&service->source, ctag_map_source_close_context,
		&service->identity, &service->ctag_info, service->backend,
		load_section, service);
	if (result == 0 &&
		(!ctag_mount_set_ctag_section_visitor(&service->mount, visit_section) ||
		 !ctag_mount_set_bsp_section_visitor(&service->mount, visit_section))) {
		printf("HALO_PS2_LOCAL map-mount failed reason=section-visitor-registration\n");
		ctag_mount_unload(&service->mount);
		result = -1;
	}
	printf("HALO_PS2_LOCAL map-mount result=%d active=%d\n",
		result, service->mount.active);
	if (!result) {
		service->preflight_ready = 0;
		service->staged_map[0] = 0;
		service->staged_entry = NULL;
		service->reload_pending = 0;
#ifdef HALO_PS2_M2_ANIMATION_TRACE
		/* New mounted tag/object indices must not alias the prior map's trace. */
		ps2_animation_trace_map_epoch_advance();
#endif
		service->boundary_cycle++;
		notify_boundary(service, "map-loaded");
		return 1;
	}
	ctag_map_source_close(&service->source);
	service->preflight_ready = 0;
	service->staged_map[0] = 0;
	service->staged_entry = NULL;
	service->reload_pending = 0;
	notify_boundary(service, "map-empty");
	return 0;
}

static int map_preflight(void *context, const char *map_name)
{
	return context == s_service && hcu_map_service_preflight(map_name);
}

static void map_unloader(void *context)
{
	hcu_map_service *service = (hcu_map_service *)context;
	int preserve_reload;
	if (!service) return;
	if (service->runtime_registered) {
		profile_unload(service);
		return;
	}
	if (legacy_owner_live(service) && !legacy_renderer_ready(service)) {
		/* CE's unloader cannot report failure, so the owner stays published and
		 * map_loader refuses the successor until a drained retry releases it. */
		printf("HALO_PS2_LOCAL map-unload blocked reason=renderer-busy\n");
		return;
	}
	preserve_reload = service->reload_pending;
	if (service->mount.active) {
		ctag_mount_unload(&service->mount);
		notify_boundary(service, "map-released");
	} else if (service->source.active) {
		ctag_map_source_close(&service->source);
	}
#ifdef HALO_PS2_M2_ANIMATION_TRACE
	/* Advance even for an empty/deferred unload boundary: identity is diagnostic,
	 * not a statement that the old map had gameplay pose data. */
	ps2_animation_trace_map_epoch_advance();
#endif
	service->preflight_ready = 0;
	if (!preserve_reload) {
		service->staged_map[0] = 0;
		service->staged_entry = NULL;
	}
}

static int map_service_init(hcu_map_service *service,
	mem_layout_v2_t *layout, const char *asset_root,
	arena_t *map_owner, arena_t *section_scratch)
{
	arena_t *streaming, *frame_scratch;
	uintptr_t stream_start, scratch_start, owner_start;
	size_t scratch_offset;
	if (!service || !layout || !asset_root || s_service) return -1;
	memset(service, 0, sizeof(*service));
	streaming = mem_layout_v2_get(layout, MEM_LAYOUT_V2_STREAMING);
	service->map_arena = map_owner ? map_owner : streaming;
	frame_scratch = mem_layout_v2_get(layout, MEM_LAYOUT_V2_FRAME_SCRATCH);
	service->section_scratch = section_scratch ? section_scratch : frame_scratch;
	service->backend = ctag_ps2_cache_backend();
	stream_start = streaming ? (uintptr_t)streaming->base : 0;
	owner_start = service->map_arena ? (uintptr_t)service->map_arena->base : 0;
	scratch_start = service->section_scratch ?
		(uintptr_t)service->section_scratch->base : 0;
	if (!streaming || !streaming->base || !service->map_arena || !frame_scratch ||
		!service->section_scratch ||
		!service->map_arena->base || !frame_scratch->base ||
		!service->section_scratch->base || !service->section_scratch->cap ||
		service->map_arena->used > service->map_arena->cap ||
		service->section_scratch->used > service->section_scratch->cap ||
		owner_start < stream_start || scratch_start < stream_start)
		return -1;
	if (map_owner) {
		size_t owner_offset = (size_t)(owner_start - stream_start);
		size_t scratch_stream_offset = (size_t)(scratch_start - stream_start);
		if (owner_offset > streaming->cap ||
			service->map_arena->cap > streaming->cap - owner_offset ||
			scratch_stream_offset > streaming->cap ||
			service->section_scratch->cap > streaming->cap - scratch_stream_offset ||
			(owner_offset < scratch_stream_offset + service->section_scratch->cap &&
			scratch_stream_offset < owner_offset + service->map_arena->cap))
			return -1;
	} else {
		uintptr_t frame_start = (uintptr_t)frame_scratch->base;
		if (scratch_start < frame_start) return -1;
		scratch_offset = (size_t)(scratch_start - frame_start);
		if (scratch_offset > frame_scratch->cap ||
			service->section_scratch->cap > frame_scratch->cap - scratch_offset)
			return -1;
	}
	if (
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

int hcu_map_service_init(hcu_map_service *service,
	mem_layout_v2_t *layout, const char *asset_root)
{
	return map_service_init(service, layout, asset_root, NULL, NULL);
}

int hcu_map_service_init_with_scratch(hcu_map_service *service,
	mem_layout_v2_t *layout, const char *asset_root,
	arena_t *section_scratch)
{
	if (!section_scratch) return -1;
	return map_service_init(service, layout, asset_root, NULL, section_scratch);
}

int hcu_map_service_init_with_arenas(hcu_map_service *service,
	mem_layout_v2_t *layout, const char *asset_root,
	arena_t *map_owner, arena_t *section_scratch)
{
	if (!map_owner || !section_scratch) return -1;
	return map_service_init(service, layout, asset_root, map_owner, section_scratch);
}

/* A failed preflight for the staged map invalidates a validated stage
 * (preflight_ready), so a later map_loader() for it must refuse. A failed
 * preflight for any other map leaves the stage intact: CE may probe another
 * scenario before loading the staged one. A same-map reuse stage (reload_pending
 * without preflight_ready) is not a validated stage; map_loader() re-runs the
 * full checks for it, so it is left untouched here. */
static void fail_preflight_for_entry(hcu_map_service *service,
	const hcu_map_catalog_entry *entry)
{
	if (service->staged_entry == entry && service->preflight_ready)
		clear_staged_request(service);
}

/* Per-load package preflight with 64 KiB reads from section_scratch when free. */
static int preflight_package_reader(hcu_map_service *service, hcu_asset_profile_view *candidate)
{
	uint8_t small[512];
	size_t mark, free_bytes;
	uint8_t *scratch;
	int rc;
	if (!service->section_scratch) return hcu_asset_profile_preflight_reader(service->profile_read_at,
		service->profile_reader_context, service->profile_image_size, service->expected_profile_id, candidate);
	free_bytes = arena_free(service->section_scratch);
	if (free_bytes > 65536u) free_bytes = 65536u;
	if (free_bytes < 65536u) return hcu_asset_profile_preflight_reader(service->profile_read_at,
		service->profile_reader_context, service->profile_image_size, service->expected_profile_id, candidate);
	mark = arena_mark(service->section_scratch);
	scratch = (uint8_t *)arena_alloc(service->section_scratch, free_bytes, 64);
	if (!scratch) { (void)small; return hcu_asset_profile_preflight_reader(service->profile_read_at,
		service->profile_reader_context, service->profile_image_size, service->expected_profile_id, candidate); }
	rc = hcu_asset_profile_preflight_reader_scratch(service->profile_read_at,
		service->profile_reader_context, service->profile_image_size, service->expected_profile_id,
		candidate, scratch, (uint32_t)free_bytes);
	arena_release(service->section_scratch, mark);
	return rc;
}

static int hcu_map_service_preflight_impl(const char *map_name);

int hcu_map_service_preflight(const char *map_name)
{
	int ok;
	HCU_LOAD_TRACE_BEGIN("preflight");
	ok = hcu_map_service_preflight_impl(map_name);
	HCU_LOAD_TRACE_END("preflight");
	return ok;
}

static int hcu_map_service_preflight_impl(const char *map_name)
{
	hcu_map_service *service = s_service;
	const hcu_map_catalog_entry *entry;
	uint8_t *hmap_bytes, *crng_bytes, *cbix_bytes;
	hmap_identity identity;
	ctag_resource_index resource_index;
	ctag_stream_info ctag_info;
	size_t mark, hmap_size = 0, crng_size = 0;
	size_t cbix_size = 0;
	unsigned long tag_cache_size;
	int valid = 0;
	if (!service || !service->initialized ||
		!(entry = hcu_map_catalog_find(map_name)))
		return 0;
	/* The profile gate precedes same-map reuse, staging, source open, and arena
	 * marks. Its reader is caller-owned and re-read on every CE pre-unload check. */
	if (service->profile_requested) {
		hcu_asset_profile_view candidate;
		if (strcmp(service->profile_map_name, entry->identity.map_name) != 0 ||
			preflight_package_reader(service, &candidate) != HCU_ASSET_PROFILE_OK ||
			!verify_profile_package_hash(service->profile_read_at,
				service->profile_reader_context, service->profile_image_size,
				service->expected_profile_sha256) ||
			!service->profile_compatibility ||
			!service->profile_compatibility(service->profile_compatibility_context,
				entry, &candidate)) {
			printf("HALO_PS2_LOCAL map-preflight rejected reason=asset-profile-gate map=%s\n",
				entry->identity.map_name);
			fail_preflight_for_entry(service, entry);
			return 0;
		}
		service->profile_view = candidate;
	}
#ifdef HALO_PS2_M2_UI_LIFECYCLE_TEST
	if (s_lifecycle_fail_preflight_once) {
		s_lifecycle_fail_preflight_once = 0;
		printf("HALO_PS2_LOCAL m2-ui-lifecycle-injected preflight-before-unload\n");
		fail_preflight_for_entry(service, entry);
		return 0;
	}
#endif
#ifdef HALO_HCU_HEADLESS_RUNTIME_GUEST
	/* This opt-in guest admits only its exact selected partition runtime. It
	 * bypasses the unqualified legacy-map whitelist, not the runtime's package,
	 * metadata, catalog, span, residency, or compatibility preflight. */
	if (service->runtime_registered &&
		service->runtime.headless_candidate_admission) {
		/* A registered foreign successor (the opt-in C2.8 guest successor
		 * sequence) is admitted under its own runtime, which carries the same
		 * admission fields and is checked against the same partition row. A
		 * service with no successor registered behaves exactly as before. */
		const hcu_map_profile_runtime *admitted = &service->runtime;
		if (service->successor_registered &&
			strcmp(service->successor_map_name, entry->identity.map_name) == 0 &&
			strcmp(service->runtime_map_name, entry->identity.map_name) != 0 &&
			service->successor.headless_candidate_admission &&
			service->successor.partition_row && service->runtime.partition_row &&
			strcmp(service->successor.partition_row,
				service->runtime.partition_row) == 0)
			admitted = &service->successor;
		if (!admitted->partition_row ||
			!admitted->partition_row[0] ||
			(admitted == &service->runtime &&
				strcmp(service->runtime_map_name, entry->identity.map_name) != 0) ||
			admitted->maximum_tag_image_bytes !=
				physical_memory_get_tag_cache_size()) {
			printf("HALO_PS2_LOCAL map-preflight rejected reason=headless-candidate-capacity map=%s row=%s\n",
				entry->identity.map_name,
				service->runtime.partition_row ? service->runtime.partition_row : "unset");
			return 0;
		}
		printf("HALO_PS2_LOCAL map-preflight candidate row=%s map=%s profile=%u package-bytes=%u tag-cap=%lu bsp-cap=%lu\n",
			admitted->partition_row, entry->identity.map_name,
			(unsigned)admitted->profile_id,
			(unsigned)admitted->package_size,
			physical_memory_get_tag_cache_size(),
			physical_memory_get_structure_bsp_cache_size());
		return profile_preflight(service, entry);
	}
#endif
	if (service->preflight_ready && !service->runtime_registered)
		return service->staged_entry == entry;
	/* The full catalog is available for identity and extent checks, but no
	 * gameplay map is enabled until its M2 resident/BSP peak is qualified.
	 * This opt-in exists only for the isolated host D20 lifecycle oracle; it
	 * must never be defined by the production EE manifest. */
#if defined(HCU_M2_D20_HOST_ORACLE)
	if (strcmp(entry->identity.map_name, "d20") != 0) {
#elif defined(HCU_M2_MP_HOST_ORACLE)
	/* Diagnostic-only oracle for the production-sized MP fixture cases.
	 * This define is never in the EE profile or product map-admission gate. */
	if (strcmp(entry->identity.map_name, "ui") != 0 &&
		strcmp(entry->identity.map_name, "longest") != 0 &&
		strcmp(entry->identity.map_name, "bloodgulch") != 0 &&
		strcmp(entry->identity.map_name, "beavercreek") != 0) {
#elif defined(HALO_PS2_STEP8_MP_CAPACITY_DIAGNOSTIC)
	/* The corpus capacity probe is a separate ELF; the ordinary admission
	 * branch below remains UI-only. */
	if (strcmp(entry->identity.map_name, "ui") != 0 &&
		strcmp(entry->identity.map_name, "beavercreek") != 0 &&
		strcmp(entry->identity.map_name, "bloodgulch") != 0 &&
		strcmp(entry->identity.map_name, "boardingaction") != 0 &&
		strcmp(entry->identity.map_name, "carousel") != 0 &&
		strcmp(entry->identity.map_name, "chillout") != 0 &&
		strcmp(entry->identity.map_name, "damnation") != 0 &&
		strcmp(entry->identity.map_name, "hangemhigh") != 0 &&
		strcmp(entry->identity.map_name, "longest") != 0 &&
		strcmp(entry->identity.map_name, "prisoner") != 0 &&
		strcmp(entry->identity.map_name, "putput") != 0 &&
		strcmp(entry->identity.map_name, "ratrace") != 0 &&
		strcmp(entry->identity.map_name, "sidewinder") != 0 &&
		strcmp(entry->identity.map_name, "wizard") != 0) {
#else
	if (strcmp(entry->identity.map_name, "ui") != 0) {
#endif
		printf("HALO_PS2_LOCAL map-preflight rejected map=%s reason=capacity-not-qualified\n",
			entry->identity.map_name);
		fail_preflight_for_entry(service, entry);
		return 0;
	}
	if (service->runtime_registered)
		return profile_preflight(service, entry);
	if (service->mount.active || service->source.active) {
		/* Do not allocate or overwrite a live owner's arena during CE's
		 * preflight-before-unload transition. Reuse is safe only for the exact
		 * currently mounted map; the loader repeats full checks after unload. */
		if (service->mount.active &&
			strcmp(service->identity.map_name, entry->identity.map_name) == 0) {
			service->staged_entry = entry;
			memcpy(service->staged_map, entry->identity.map_name,
				strlen(entry->identity.map_name) + 1);
			service->reload_pending = 1;
			return 1;
		}
		fail_preflight_for_entry(service, entry);
		return 0;
	}
	/* Stage the identity for the loader callback so CBIX can be checked before
	 * CE tears down the currently published scenario. This is private pending
	 * state only; no cache or scenario pointer is published here. */
	service->staged_entry = entry;
	memcpy(service->staged_map, entry->identity.map_name,
		strlen(entry->identity.map_name) + 1);
	printf("HALO_PS2_LOCAL map-preflight source-open-begin\n");
	if (ctag_map_source_open_any(&service->source, entry->map_path) != 0) {
		printf("HALO_PS2_LOCAL map-preflight source-open-failed\n");
		clear_staged_request(service);
		return 0;
	}
	printf("HALO_PS2_LOCAL map-preflight source-opened bytes=%u\n",
		(unsigned)service->source.reader.size);
	mark = arena_mark(service->map_arena);
	HCU_TRACE("HALO_PS2_LOCAL map-preflight sections-begin\n");
	hmap_bytes = load_section(service, service->map_arena, entry->hp2_path,
		"HMAP", &hmap_size, 0);
	crng_bytes = load_section(service, service->map_arena, entry->hp2_path,
		"CRNG", &crng_size, 0);
	cbix_bytes = load_section(service, service->map_arena, entry->hp2_path,
		"CBIX", &cbix_size, 0);
	HCU_TRACE("HALO_PS2_LOCAL map-preflight sections-done hmap=%u crng=%u cbix=%u\n",
		(unsigned)hmap_size, (unsigned)crng_size,
		(unsigned)cbix_size);
	tag_cache_size = physical_memory_get_tag_cache_size();
	HCU_TRACE("HALO_PS2_LOCAL map-preflight validate-begin\n");
	memset(&ctag_info, 0, sizeof(ctag_info));
	if (hmap_bytes && crng_bytes && cbix_bytes &&
		hcu_map_catalog_validate_hmap(entry, hmap_bytes, hmap_size,
			&identity) &&
		hcu_map_catalog_validate_bsp_catalog(entry, cbix_bytes, cbix_size) &&
		identity.file_length == service->source.reader.size &&
		ctag_resource_index_open_discover(&resource_index, crng_bytes,
			crng_size, service->source.reader.size) &&
		resource_index.tag_data_offset == identity.tag_data_offset &&
		resource_index.tag_data_size == identity.tag_data_size &&
		preflight_ctag_stream(service, entry->hp2_path, tag_cache_size,
			service->map_arena, &ctag_info) &&
		verify_source_hash(service,
			identity.source_sha256))
		valid = 1;
#ifdef HALO_PS2_M2_UI_LIFECYCLE_TEST
	/* Inject only after the complete post-unload validation has succeeded. This
	 * is reached through CE's normal ps2_cache_preflight_map() call from
	 * main_load_ui_scenario(), not by calling map_loader() from the diagnostic. */
	if (valid && s_lifecycle_deferred_failure_armed) {
		s_lifecycle_deferred_failure_armed = 0;
		valid = 0;
		printf("HALO_PS2_LOCAL m2-ui-lifecycle-injected preflight-after-unload\n");
	}
#endif
	printf("HALO_PS2_LOCAL map-preflight result=%d\n", valid);
	arena_release(service->map_arena, mark);
	if (!valid) {
		clear_staged_request(service);
		return 0;
	}
	service->identity = identity;
	service->ctag_info = ctag_info;
	service->preflight_ready = 1;
	return 1;
}

int hcu_map_service_register_profile(hcu_map_service *service,
	const char *map_name, uint32_t profile_id,
	hcu_asset_profile_read_at read_at, void *reader_context,
	uint32_t image_size, const uint8_t expected_package_sha256[32],
	hcu_map_profile_compatibility_fn compatibility, void *compatibility_context)
{
	const hcu_map_catalog_entry *entry;
	hcu_asset_profile_view candidate;
	char canonical_name[sizeof(service->profile_map_name)];
	if (!service || service != s_service || !service->initialized ||
		service->runtime_registered ||
		!map_name || !read_at || !profile_id || !expected_package_sha256 ||
		!compatibility ||
		!(entry = hcu_map_catalog_find(map_name)) ||
		strcmp(map_name, entry->identity.map_name) != 0 ||
		hcu_asset_profile_preflight_reader(read_at, reader_context, image_size,
			profile_id, &candidate) != HCU_ASSET_PROFILE_OK ||
		!verify_profile_package_hash(read_at, reader_context, image_size,
		expected_package_sha256) ||
		!compatibility(compatibility_context, entry, &candidate))
		return 0;
	if (strlen(entry->identity.map_name) >= sizeof(canonical_name)) return 0;
	memset(canonical_name, 0, sizeof(canonical_name));
	memcpy(canonical_name, entry->identity.map_name,
		strlen(entry->identity.map_name) + 1);
	/* Commit the new request only after map and every chunk have passed. */
	service->profile_requested = 1;
	service->expected_profile_id = profile_id;
	service->profile_image_size = image_size;
	memcpy(service->expected_profile_sha256, expected_package_sha256, 32);
	service->profile_read_at = read_at;
	service->profile_reader_context = reader_context;
	service->profile_compatibility = compatibility;
	service->profile_compatibility_context = compatibility_context;
	service->profile_view = candidate;
	memcpy(service->profile_map_name, canonical_name, sizeof(canonical_name));
	return 1;
}

int hcu_map_service_unregister_profile(hcu_map_service *service)
{
	if (!service || service != s_service || !service->initialized ||
		service->mount.active || service->source.active || service->reload_pending)
		return 0;
	service->profile_requested = 0;
	service->expected_profile_id = 0;
	service->profile_image_size = 0;
	service->profile_read_at = NULL;
	service->profile_reader_context = NULL;
	service->profile_compatibility = NULL;
	service->profile_compatibility_context = NULL;
	memset(service->expected_profile_sha256, 0,
		sizeof(service->expected_profile_sha256));
	memset(&service->profile_view, 0, sizeof(service->profile_view));
	memset(service->profile_map_name, 0, sizeof(service->profile_map_name));
	return 1;
}

/* The checks every registered runtime passes: its catalog entry's package pin,
 * its compatibility gate and its storage. The candidate view is the package's
 * identity, kept for later preflights. */
static int runtime_registration_valid(const hcu_map_catalog_entry *entry,
	const hcu_map_profile_runtime *runtime, hcu_asset_profile_view *candidate)
{
	if (!entry || !runtime) return 0;
#ifdef HALO_HCU_HEADLESS_RUNTIME_GUEST
	if (runtime->headless_candidate_admission &&
		(!runtime->partition_row || !runtime->partition_row[0] ||
		 runtime->maximum_tag_image_bytes != physical_memory_get_tag_cache_size()))
		return 0;
#endif
	return runtime->package_read_at && runtime->compatibility &&
		runtime->package_size && runtime->profile_id &&
		runtime->metadata_bytes && runtime->metadata_size &&
		runtime->source_read && runtime->maximum_tag_image_bytes &&
		runtime_residency_valid(runtime) && runtime_spans_valid(runtime) &&
		hcu_asset_profile_preflight_reader(runtime->package_read_at,
			runtime->package_context, runtime->package_size, runtime->profile_id,
			candidate) == HCU_ASSET_PROFILE_OK &&
		verify_profile_package_hash(runtime->package_read_at,
			runtime->package_context, runtime->package_size,
			runtime->package_sha256) &&
		runtime->compatibility(runtime->compatibility_context, entry, candidate);
}

int hcu_map_service_register_runtime(hcu_map_service *service,
	const char *map_name, const hcu_map_profile_runtime *runtime)
{
	const hcu_map_catalog_entry *entry;
	hcu_asset_profile_view candidate;
	if (!service || service != s_service || !service->initialized || !map_name ||
		!runtime || service->runtime_registered || service->profile_requested ||
		service->mount.active || service->source.active ||
		profile_owner_live(service) || service->profile_candidate_ready ||
		service->reload_pending || service->preflight_ready)
		return 0;
	if (!(entry = hcu_map_catalog_find(map_name)) ||
		strcmp(map_name, entry->identity.map_name) != 0 ||
		strlen(entry->identity.map_name) >= sizeof(service->runtime_map_name) ||
		!runtime_registration_valid(entry, runtime, &candidate))
		return 0;
	service->runtime = *runtime;
	memset(service->runtime_map_name, 0, sizeof(service->runtime_map_name));
	memcpy(service->runtime_map_name, entry->identity.map_name,
		strlen(entry->identity.map_name) + 1);
	service->profile_view = candidate;
	service->runtime_registered = 1;
	return 1;
}

int hcu_map_service_register_successor_runtime(hcu_map_service *service,
	const char *map_name, const hcu_map_profile_runtime *runtime)
{
	const hcu_map_catalog_entry *entry;
	hcu_asset_profile_view candidate;
	if (!service || service != s_service || !service->initialized || !map_name ||
		!runtime || !service->runtime_registered || service->successor_registered ||
		service->profile_candidate_ready)
		return 0;
	if (!(entry = hcu_map_catalog_find(map_name)) ||
		strcmp(map_name, entry->identity.map_name) != 0 ||
		strcmp(map_name, service->runtime_map_name) == 0 ||
		strlen(entry->identity.map_name) >= sizeof(service->successor_map_name) ||
		!runtime_registration_valid(entry, runtime, &candidate) ||
		!runtime_spans_disjoint(&service->runtime, runtime))
		return 0;
	service->successor = *runtime;
	memset(service->successor_map_name, 0, sizeof(service->successor_map_name));
	memcpy(service->successor_map_name, entry->identity.map_name,
		strlen(entry->identity.map_name) + 1);
	service->successor_view = candidate;
	service->successor_registered = 1;
	return 1;
}

int hcu_map_service_set_boundary_hook(hcu_map_service *service,
	hcu_map_service_boundary_fn hook, void *context)
{
	if (!service) return 0;
	service->boundary_hook = hook;
	service->boundary_context = context;
	service->boundary_cycle = 0;
	return 1;
}

int hcu_map_service_set_legacy_renderer_drained(hcu_map_service *service,
	int (*renderer_drained)(void *context), void *context)
{
	if (!service || service != s_service || !service->initialized ||
		!renderer_drained || service->runtime_registered)
		return 0;
	service->legacy_renderer_drained = renderer_drained;
	service->legacy_renderer_context = context;
	return 1;
}

int hcu_map_service_unregister_runtime(hcu_map_service *service)
{
	if (!service || service != s_service || !service->initialized ||
		!service->runtime_registered || profile_owner_live(service) ||
		service->successor_registered ||
		service->profile_candidate_ready || service->reload_pending)
		return 0;
	memset(&service->runtime, 0, sizeof(service->runtime));
	memset(service->runtime_map_name, 0, sizeof(service->runtime_map_name));
	memset(&service->profile_view, 0, sizeof(service->profile_view));
	service->runtime_registered = 0;
	return 1;
}

int hcu_map_service_shutdown(hcu_map_service *service)
{
	if (!service || !service->initialized) return 1;
	map_unloader(service);
	if (service->legacy_renderer_drained && legacy_owner_live(service)) {
		printf("HALO_PS2_LOCAL map-shutdown retained live legacy owner\n");
		return 0;
	}
	if (service->runtime_registered && profile_owner_live(service)) {
		/* Keep callback registration and initialization intact as well as the
		 * backing. A drained retry must still be able to release this owner. */
		printf("HALO_PS2_LOCAL map-shutdown retained live profile owner\n");
		return 0;
	}
	service->reload_pending = 0;
	service->staged_map[0] = 0;
	service->staged_entry = NULL;
	service->runtime_registered = 0;
	memset(&service->runtime, 0, sizeof(service->runtime));
	memset(service->runtime_map_name, 0, sizeof(service->runtime_map_name));
	service->successor_registered = 0;
	memset(&service->successor, 0, sizeof(service->successor));
	memset(service->successor_map_name, 0, sizeof(service->successor_map_name));
	discard_profile_candidate(service);
	(void)hcu_map_service_unregister_profile(service);
	ps2_cache_set_map_preflight(NULL, NULL);
	ps2_cache_set_map_loader(NULL, NULL);
	ps2_cache_set_map_unloader(NULL, NULL);
	service->initialized = 0;
	if (s_service == service) s_service = NULL;
	return 1;
}

void hcu_map_service_lifecycle_trace(const char *phase, unsigned int cycle)
{
	hcu_map_service *service = s_service;
	if (!service || !phase) {
		printf("HALO_PS2_LOCAL m2-ui-owner cycle=%u phase=%s service=unavailable\n",
			cycle, phase ? phase : "unset");
		return;
	}
	printf("HALO_PS2_LOCAL m2-ui-owner cycle=%u phase=%s base=%p cap=%u used=%u high=%u mount=%d source=%d descriptor=%d preflight=%d reload=%d staged=%s\n",
		cycle, phase, (void *)service->map_arena->base,
		(unsigned)service->map_arena->cap, (unsigned)service->map_arena->used,
		(unsigned)service->map_arena->high, service->mount.active,
		service->source.active, service->source.reader.descriptor,
		service->preflight_ready, service->reload_pending,
		service->staged_map[0] ? service->staged_map : "-");
}

#ifdef HALO_PS2_M2_UI_LIFECYCLE_TEST
void hcu_map_service_lifecycle_fail_preflight_once(void)
{
	s_lifecycle_fail_preflight_once = 1;
}

void hcu_map_service_lifecycle_arm_deferred_failure_once(void)
{
	s_lifecycle_deferred_failure_armed = 1;
}

#endif
