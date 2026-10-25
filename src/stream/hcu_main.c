/* Optional parent machine entry for the CE gameplay closure.
 * The ordinary halo-ps2 viewer remains the default build target. */
#include "core/mem.h"
#include "platform/pad.h"
#include "platform/video.h"
#include "stream/hcu_memory_bind.h"
#include "stream/hcu_memory_profile.h"
#include "stream/hcu_owner_telemetry.h"
#include "stream/hcu_map_service.h"
#include "stream/hcu_file_bridge.h"
#include "stream/hcu_render_snapshot.h"
/* C3:snapshot begin */
#if defined(HCU_C3_FRAME_SNAPSHOT)
#include "stream/hcu_snapshot_bank.h"
#endif
/* C3:snapshot end */
#include "stream/hcu_storage_boot.h"
#include "halo_ps2_cache.h"
#include "halo_ps2_bitmap_frame.h"
#include "ps2_step8_memory_owners.h"
#include "stream/hcu_bitmap_renderer.h"

#include <kernel.h>
#include <dma.h>
#include <draw.h>
#include <graph.h>
#include <gs_psm.h>
#include <packet2.h>
#include "render/bsp_render.h"
#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <string.h>

/* Make the C3 renderer guard visible to the runtime initializer above the
 * map callbacks. This generated header exists only for the explicit --render
 * build; other guests retain their no-bitmap/headless contract. */
#if defined(HCU_C3) && defined(HALO_HCU_HEADLESS_RUNTIME_GUEST) && defined(__has_include)
#if __has_include(<hcu_c3_render.h>)
#include <hcu_c3_render.h>
#define HCU_C3_RENDER_BUILT 1
#endif
#endif
#include "stream/hcu_bitmap_runtime.h"
#include "stream/hcu_profile_metadata.h"

#ifdef HALO_PS2_M2_ANIMATION_TRACE
#include "ps2_animation_trace.h"
#endif

/* C2.4 production image: tools/c2_profile_image_header.py pins one partition
 * row's package, metadata, source maps and datum table. The EE build names the
 * generated header with HALO_HCU_PROFILE_IMAGE_HEADER. */
#ifdef HALO_HCU_PROFILE_IMAGE_HEADER
#include HALO_HCU_PROFILE_IMAGE_HEADER
/* Decode scratch for one 64 KiB segment, carved from the section scratch arena. */
#define HCU_C2_STREAM_SCRATCH_BYTES 65536u

#ifdef HALO_HCU_HEADLESS_RUNTIME_GUEST
/* The headless runtime guest (CE main.c, HALO_PS2_C2_PRODUCTION_RUNTIME_GUEST)
 * loads whichever map and scenario the generated row header pins. CE's main.c
 * defines these buffers (so the rooted CE image has no unresolved symbol and
 * one rooted object serves every row); this entry fills them before the shell. */
extern char hcu_c2_runtime_map_name[64];
extern char hcu_c2_runtime_scenario_path[256];
#endif
/* Opt-in C2.8 successor guest: tools/c2_profile_boot_matrix.py --successor puts
 * hcu_c2_successor.h (mode) and hcu_c2_succ_image.h (the successor row's image,
 * HCU_C2_SUCC_* names) on the include path. Without both, none of the successor
 * code below is compiled and the image is the plain single-row guest. */
#if defined(HALO_HCU_HEADLESS_RUNTIME_GUEST) && defined(__has_include)
#if __has_include(<hcu_c2_successor.h>) && __has_include(<hcu_c2_succ_image.h>)
#include <hcu_c2_successor.h>
#include <hcu_c2_succ_image.h>
#define HCU_C2_SUCCESSOR_BUILT 1
extern char hcu_c2_successor_map_name[64];
extern char hcu_c2_successor_scenario_path[256];
extern volatile int hcu_c2_successor_fault_armed;
extern unsigned hcu_c2_successor_fault_count;
#endif
#endif
#endif

#ifndef HALO_HCU_TAG_CACHE_BYTES
#define HALO_HCU_TAG_CACHE_BYTES 2097152u
#endif
#ifndef HALO_HCU_ASSET_ROOT
#define HALO_HCU_ASSET_ROOT "host:/"
#endif

/* config/memory-budget.json version 4. Physical EE layout, derived from named
 * constants: 1 MiB low kernel, then elf_static (2,490,368 bytes) holding the
 * file-backed ELF sections, then the single boot backing (MEM_LAYOUT_V2_BYTES),
 * then the uncommitted reserve up to the 0x01f80000 high kernel reservation.
 * ELF NOBITS is charged to resident_gameplay, not to elf_static. */
#define HCU_LOW_KERNEL_BYTES 0x00100000u
#define HCU_ELF_STATIC_BYTES 2490368u
#define HCU_FILE_BACKED_END (HCU_LOW_KERNEL_BYTES + HCU_ELF_STATIC_BYTES)
#define HCU_RESERVE_START (HCU_FILE_BACKED_END + (unsigned)MEM_LAYOUT_V2_BYTES)
#define HCU_RESERVE_END 0x01f80000u
#define HCU_RESERVE_BYTES (HCU_RESERVE_END - HCU_RESERVE_START)
/* Partition row bound before CE allocation. The default "bootstrap" keeps the
 * unqualified 2 MiB tag span and is logged as such; any other name must be a
 * row of hcu_memory_partition_select_v2() or boot fails closed. */
#ifndef HALO_HCU_PARTITION_PROFILE
#define HALO_HCU_PARTITION_PROFILE "bootstrap"
#endif
#include "stream/hcu_render_telemetry.h"
#include "halo_ps2_owner_counters.h"
/* C3:world begin */
#if defined(HCU_C3)
#include "stream/hcu_render_world.h"
#endif
/* C3:world end */

static hcu_map_service s_map_service;

#ifdef HCU_C3_RENDER_BUILT
#define HCU_C3_BITMAP_OWNER_BYTES (400u * 1024u)
#define HCU_C3_BITMAP_GUARD_BYTES 16u
#define HCU_C3_BITMAP_OWNER_CAP_BYTES (HCU_C3_BITMAP_OWNER_BYTES - HCU_C3_BITMAP_GUARD_BYTES)
#ifndef HCU_C3_BITMAP_UPLOAD_POOL_BYTES
#define HCU_C3_BITMAP_UPLOAD_POOL_BYTES (256u * 1024u)
#endif
#if HCU_C3_BITMAP_UPLOAD_POOL_BYTES > (256u * 1024u)
#error HCU_C3_BITMAP_UPLOAD_POOL_BYTES may reduce but never widen the measured bitmap pool
#endif
#define HCU_C3_BITMAP_SLOT_COUNT HALO_PS2_BITMAP_REQUEST_CAPACITY
#if defined(HCU_C3_OBJECTS)
#define HCU_C3_BITMAP_OBJECT_KEY_CAPACITY (80u * 32u)
#else
#define HCU_C3_BITMAP_OBJECT_KEY_CAPACITY 0u
#endif
hcu_bitmap_frame_owner hcu_c3_bitmap_frame_owner;
/* C3:bitmap begin */
static uint32_t s_c3b_last[6];
/* C3:bitmap end */
static halo_ps2_bitmap_request_queue *s_c3_bitmap_queue;
static hcu_bitmap_dispatch_context s_c3_bitmap_dispatch;
static hcu_bitmap_renderer s_c3_bitmap_renderer;
static arena_t s_c3_bitmap_owner_arena;
static hcu_profile_metadata_view s_c3_bitmap_metadata;
static uint32_t s_c3_bitmap_key_base;
static uint8_t *s_c3_bitmap_guard;
static int s_c3_bitmap_guard_failed;
static int s_c3_bitmap_bound;
#endif

/* C2.6 owner telemetry: one registry for every named owner. Arena-backed owners
 * are read live through their arena counters; cache owners through the CE cache
 * telemetry. Nested owners are never summed into their parent. */
typedef struct {
	const arena_t *arena;
	size_t capacity;
} hcu_owner_arena_ctx;

static hcu_owner_telemetry_t s_owner_telemetry;
static hcu_owner_arena_ctx s_owner_ctx[HCU_OWNER_COUNT];
static int s_partition_selected;
static hcu_memory_partition_t s_partition;
/* Residency table for the selected row's map service arena: one entry per
 * 64 KiB slot. Lives in ELF static storage, not in CE, so it is not charged to the row. */
#define HCU_PARTITION_RESIDENCY_SLOTS 16u
static hcu_asset_residency_entry s_residency_entries[HCU_PARTITION_RESIDENCY_SLOTS];
static const char *s_partition_name = "bootstrap";

static int hcu_sample_arena(void *ctx, hcu_owner_sample_t *out)
{
	const hcu_owner_arena_ctx *c = (const hcu_owner_arena_ctx *)ctx;
	if (!c || !c->arena || !c->arena->base)
		return 0;
	out->capacity = c->arena->cap;
	out->used = c->arena->used;
	out->high = c->arena->high;
	out->failures = c->arena->failed_allocations;
	out->resets = c->arena->reset_count;
	return 1;
}

static int hcu_sample_dynamic_simulation(void *ctx, hcu_owner_sample_t *out)
{
	struct ps2_step8_dynamic_sim_diagnostics usage;
	(void)ctx;
	if (!out || !ps2_step8_dynamic_sim_diagnostics(&usage))
		return 0;
	out->capacity = (size_t)usage.capacity_bytes;
	out->used = (size_t)usage.used_bytes;
	out->high = (size_t)usage.high_water_bytes;
	out->failures = (uint32_t)usage.failed_allocations;
	out->resets = (uint32_t)usage.resets;
	return 1;
}

/* HCP decoded residency is sourced only from the live verified-segment table.
 * It is nested in render_chunks and never enters the backing-memory sum. */
static int hcu_sample_decoded_asset_residency(void *ctx, hcu_owner_sample_t *out)
{
	hcu_map_residency_report report;
	uint64_t failures;
	(void)ctx;
	if (!out || !hcu_map_service_residency_snapshot(&s_map_service, &report) ||
		!report.valid || !report.map.bound || !report.map.capacity_bytes)
		return 0;
	failures = (uint64_t)report.map.refused_pins + report.map.verify_failures;
	out->capacity = report.map.capacity_bytes;
	out->used = report.map.current_bytes;
	out->high = report.map.high_water_bytes;
	out->failures = failures > UINT32_MAX ? UINT32_MAX : (uint32_t)failures;
	out->resets = report.map.resets;
	return 1;
}

/* CE-owned pools report through the always-on port counters; ctx is the
 * HALO_PS2_OWNER_* index, not a pointer. */
static int hcu_sample_ce_owner(void *ctx, hcu_owner_sample_t *out)
{
	halo_ps2_owner_counters c;
	if (halo_ps2_owner_counters_get((int)(intptr_t)ctx, &c) != 0 || !c.capacity)
		return 0;
	out->capacity = c.capacity;
	out->used = c.used;
	out->high = c.high_water;
	out->failures = c.failures;
	out->resets = c.resets;
	return 1;
}

static int hcu_sample_tags(void *ctx, hcu_owner_sample_t *out)
{
	halo_ps2_cache_owner_telemetry usage;
	const hcu_owner_arena_ctx *c = (const hcu_owner_arena_ctx *)ctx;
	if (!c || c->capacity == 0)
		return 0;
	ps2_cache_get_owner_telemetry(&usage);
	out->capacity = c->capacity;
	out->used = usage.tag_current_bytes;
	out->high = usage.tag_peak_bytes;
	out->failures = usage.tag_failures;
	out->resets = usage.tag_resets;
	return 1;
}

static int hcu_sample_bsp(void *ctx, hcu_owner_sample_t *out)
{
	halo_ps2_cache_owner_telemetry usage;
	const hcu_owner_arena_ctx *c = (const hcu_owner_arena_ctx *)ctx;
	if (!c || c->capacity == 0)
		return 0;
	ps2_cache_get_owner_telemetry(&usage);
	out->capacity = c->capacity;
	out->used = usage.bsp_current_bytes;
	out->high = usage.bsp_peak_bytes;
	out->failures = usage.bsp_failures;
	out->resets = usage.bsp_resets;
	return 1;
}

/* The renderer's fence: 1 once the latest kick is retired, or when no kick has
 * been issued yet. Used as the legacy map gate and by the snapshot printer. */
static int hcu_renderer_drained(void *ctx)
{
	uint32_t kick;
	(void)ctx;
	kick = bsp_render_kick_seq();
	if (kick == 0)
		return 1;
	return bsp_render_fence_observed(kick) == 1;
}

/* The map service calls this only after successor validation has completed and
 * before CE disposes the old scenario. Defined alongside the opt-in C3 loop. */
static int hcu_renderer_quiesce(void *ctx);

/* The explicit headless runtime guest exits before CE's renderer loop. A
 * missing frame owner is safe there only while no bitmap frame or BSP kick
 * has ever started; all other builds keep requiring the real frame owner. */
#ifdef HALO_HCU_HEADLESS_RUNTIME_GUEST
/* C3:render begin */
#if defined(HCU_C3)
/* Set once the C3 render loop has drained GS/DMA, stopped reading the world and released its world
 * reader and media (hcu_c3_render_map_release); cleared when it loads a map. A started renderer in this
 * state has no reference to any map byte, so the headless release may proceed. */
static int s_c3_render_quiescent;
#endif
/* C3:render end */
static int hcu_renderer_never_started(void *ctx)
{
	(void)ctx;
	/* C3:render begin */
#if defined(HCU_C3)
	if (s_c3_render_quiescent && halo_ps2_bitmap_frame_is_active() == 0 &&
		hcu_bitmap_renderer_attachment_count() == 0 && hcu_renderer_drained(NULL))
		return 1;
#endif
	/* C3:render end */
	return bsp_render_kick_seq() == 0 &&
		halo_ps2_bitmap_frame_is_active() == 0 &&
		hcu_bitmap_renderer_attachment_count() == 0;
}
#endif

static void hcu_report_owner_telemetry(const char *phase)
{
	hcu_owner_report_t rep;
	int i;
	if (!hcu_owner_telemetry_snapshot(&s_owner_telemetry, &rep))
		return;
	printf("HALO_PS2_LOCAL owner-telemetry phase=%s partition=%s backing_cap=%u "
		"backing_used=%u backing_high=%u backing_failures=%u backing_resets=%u "
		"gs_cap=%u gs_used=%u gs_high=%u gs_failures=%u gs_resets=%u "
		"nested_within_parent=%d renderer_drained=%d\n",
		phase, s_partition_name,
		(unsigned)rep.backing_capacity, (unsigned)rep.backing_used,
		(unsigned)rep.backing_high, (unsigned)rep.backing_failures,
		(unsigned)rep.backing_resets,
		(unsigned)rep.gs_capacity, (unsigned)rep.gs_used, (unsigned)rep.gs_high,
		(unsigned)rep.gs_failures, (unsigned)rep.gs_resets, rep.nested_within_parent,
		hcu_renderer_drained(NULL));
	for (i = 0; i < (int)HCU_OWNER_COUNT; ++i) {
		const hcu_owner_row_t *row = &rep.rows[i];
		printf("HALO_PS2_LOCAL owner-telemetry phase=%s name=%s kind=%s parent=%s "
			"bound=%d cap=%u used=%u high=%u failures=%u resets=%u domain=%s\n",
			phase, row->name,
			row->kind == HCU_OWNER_KIND_NESTED ? "nested" : "backing",
			row->parent >= 0 ? rep.rows[row->parent].name : "-",
			row->bound,
			(unsigned)row->sample.capacity, (unsigned)row->sample.used,
			(unsigned)row->sample.high, (unsigned)row->sample.failures,
			(unsigned)row->sample.resets,
			row->domain == HCU_OWNER_DOMAIN_GS ? "gs" : "ee");
	}
}

/* Selects the partition row before any CE allocation or binding, logs it, and
 * binds it through the guarded v2 profile path. Returns 0 on success. */
static int hcu_select_and_bind_partition(mem_layout_v2_t *layout)
{
	const hcu_memory_profile_t *profile;
	if (strcmp(HALO_HCU_PARTITION_PROFILE, "bootstrap") == 0) {
		s_partition_name = "bootstrap";
		s_partition_selected = 0;
		printf("HALO_PS2_LOCAL partition-selected name=bootstrap qualified=0 tag=%u\n",
			(unsigned)HALO_HCU_TAG_CACHE_BYTES);
		return hcu_memory_bind_parent_v2(layout,
			(size_t)HALO_HCU_TAG_CACHE_BYTES);
	}
	profile = hcu_memory_partition_select_v2(HALO_HCU_PARTITION_PROFILE);
	if (!profile) {
		printf("[err] partition profile %s is not in the versioned table\n",
			HALO_HCU_PARTITION_PROFILE);
		return -1;
	}
	s_partition_name = HALO_HCU_PARTITION_PROFILE;
	printf("HALO_PS2_LOCAL partition-selected name=%s version=%u tag=%u bsp=%u texture=%u residency=%u qualified=1\n",
		s_partition_name, (unsigned)profile->version,
		(unsigned)profile->tag_cache_bytes,
		(unsigned)profile->structure_bsp_bytes,
		(unsigned)profile->render_texture_bytes,
		(unsigned)profile->residency_bytes);
	if (hcu_memory_bind_profile_v1(layout, profile, &s_partition) != 0)
		return -1;
	s_partition_selected = 1;
	return 0;
}

#ifdef HALO_HCU_PROFILE_IMAGE_HEADER
/* Read-only file slots for the generated image. A token of -1 is closed. */
typedef struct {
	int token;
	unsigned long size;
} hcu_c2_file;

static hcu_c2_file s_c2_package = { -1, 0 };
static hcu_c2_file s_c2_sources[HCU_C2_IMAGE_SOURCE_COUNT];

static void hcu_c2_close_image_files(void)
{
	uint32_t i;
	if (s_c2_package.token >= 0) hcu_file_bridge_close(s_c2_package.token);
	s_c2_package.token = -1;
	s_c2_package.size = 0;
	for (i = 0; i < HCU_C2_IMAGE_SOURCE_COUNT; ++i) {
		if (s_c2_sources[i].token >= 0) hcu_file_bridge_close(s_c2_sources[i].token);
		s_c2_sources[i].token = -1;
		s_c2_sources[i].size = 0;
	}
}

/* Opens one generated path and refuses it unless its size is the pinned size. */
static int hcu_c2_open_file(hcu_c2_file *file, const char *path,
	unsigned long expected_bytes)
{
	unsigned long size = 0;
	file->token = hcu_file_bridge_open(path, &size);
	file->size = 0;
	if (file->token < 0) return 0;
	if (size != expected_bytes) {
		hcu_file_bridge_close(file->token);
		file->token = -1;
		return 0;
	}
	file->size = size;
	return 1;
}

static int hcu_c2_open_image_files(void)
{
	uint32_t i;
	int ok;
	hcu_c2_close_image_files();
	ok = hcu_c2_open_file(&s_c2_package, HCU_C2_IMAGE_PACKAGE_PATH,
		HCU_C2_IMAGE_PACKAGE_BYTES);
	if (!ok) {
		printf("[err] cannot open pinned package %s at %u bytes\n",
			HCU_C2_IMAGE_PACKAGE_PATH, (unsigned)HCU_C2_IMAGE_PACKAGE_BYTES);
		return 0;
	}
	for (i = 0; i < HCU_C2_IMAGE_SOURCE_COUNT; ++i) {
		ok = hcu_c2_open_file(&s_c2_sources[i], HCU_C2_IMAGE_SOURCES[i].path,
			HCU_C2_IMAGE_SOURCES[i].bytes);
		if (!ok) {
			printf("[err] cannot open pinned source map %s at %u bytes\n",
				HCU_C2_IMAGE_SOURCES[i].path,
				(unsigned)HCU_C2_IMAGE_SOURCES[i].bytes);
			hcu_c2_close_image_files();
			return 0;
		}
	}
	return 1;
}

/* Bounded read of an open slot at an absolute offset. Short reads fail. */
static int hcu_c2_read_at(const hcu_c2_file *file, uint32_t offset,
	void *destination, uint32_t size)
{
	unsigned long got = 0;
	if (file->token < 0 || (unsigned long)offset > file->size ||
		(unsigned long)size > file->size - offset) return 0;
	if (hcu_file_bridge_seek(file->token, (long)offset, 0) != (long)offset)
		return 0;
	if (!hcu_file_bridge_read(file->token, destination, size, &got)) return 0;
	return got == size;
}

static int hcu_c2_package_read_at(void *context, uint32_t offset,
	void *destination, uint32_t size)
{
	(void)context;
	return hcu_c2_read_at(&s_c2_package, offset, destination, size) ?
		HCU_ASSET_PROFILE_OK : HCU_ASSET_PROFILE_E_STATE;
}

/* The datum table names the one source map each output datum comes from. A
 * datum outside the table has no source and is refused. */
static int hcu_c2_source_read(void *context, int32_t output_datum,
	uint32_t file_offset, uint32_t size, void *buffer, int blocking)
{
	uint32_t i;
	(void)context;
	(void)blocking;
	for (i = 0; i < HCU_C2_IMAGE_DATUM_COUNT; ++i)
		if (HCU_C2_IMAGE_DATUMS[i].output_datum == (uint32_t)output_datum) break;
	if (i == HCU_C2_IMAGE_DATUM_COUNT) return 0;
	return hcu_c2_read_at(&s_c2_sources[HCU_C2_IMAGE_DATUMS[i].source],
		file_offset, buffer, size);
}

static int hcu_c2_compatible(void *context, const hcu_map_catalog_entry *entry,
	const hcu_asset_profile_view *profile)
{
	(void)context;
	return entry && profile &&
		strcmp(entry->identity.map_name, HCU_C2_IMAGE_MAP) == 0 &&
		profile->profile_id == HCU_C2_IMAGE_PROFILE_ID;
}

#ifdef HCU_C2_SUCCESSOR_BUILT
/* The successor row's package and source maps, opened beside the selected row's
 * (the bridge has 16 slots). Tokens start closed; the selected row's slots are
 * never touched here. */
static hcu_c2_file s_c2s_package = { -1, 0 };
static hcu_c2_file s_c2s_sources[HCU_C2_SUCC_SOURCE_COUNT];
static hcu_asset_residency_entry s_c2s_residency_entries[HCU_PARTITION_RESIDENCY_SLOTS / 2u];
static const arena_t *s_c2s_owner_arena;
static uint32_t s_c2s_fault_bytes;

static void hcu_c2s_close_files(void)
{
	uint32_t i;
	if (s_c2s_package.token >= 0) hcu_file_bridge_close(s_c2s_package.token);
	s_c2s_package.token = -1;
	s_c2s_package.size = 0;
	for (i = 0; i < HCU_C2_SUCC_SOURCE_COUNT; ++i) {
		if (s_c2s_sources[i].token >= 0) hcu_file_bridge_close(s_c2s_sources[i].token);
		s_c2s_sources[i].token = -1;
		s_c2s_sources[i].size = 0;
	}
}

static int hcu_c2s_open_files(void)
{
	uint32_t i;
	s_c2s_package.token = -1;
	s_c2s_package.size = 0;
	for (i = 0; i < HCU_C2_SUCC_SOURCE_COUNT; ++i) {
		s_c2s_sources[i].token = -1;
		s_c2s_sources[i].size = 0;
	}
	if (!hcu_c2_open_file(&s_c2s_package, HCU_C2_SUCC_PACKAGE_PATH,
			HCU_C2_SUCC_PACKAGE_BYTES)) {
		printf("[err] cannot open pinned successor package %s at %u bytes\n",
			HCU_C2_SUCC_PACKAGE_PATH, (unsigned)HCU_C2_SUCC_PACKAGE_BYTES);
		return 0;
	}
	for (i = 0; i < HCU_C2_SUCC_SOURCE_COUNT; ++i) {
		if (!hcu_c2_open_file(&s_c2s_sources[i], HCU_C2_SUCC_SOURCES[i].path,
				HCU_C2_SUCC_SOURCES[i].bytes)) {
			printf("[err] cannot open pinned successor source map %s at %u bytes\n",
				HCU_C2_SUCC_SOURCES[i].path, (unsigned)HCU_C2_SUCC_SOURCES[i].bytes);
			hcu_c2s_close_files();
			return 0;
		}
	}
	return 1;
}

/* Mode 2 injects a preflight package-read fault. Mode 3 faults the actual
 * registered HCP CTAG visitor from CE's cache load (see the mount hook). */
static int hcu_c2s_package_read_at(void *context, uint32_t offset,
	void *destination, uint32_t size)
{
	int ok;
	(void)context;
#if HALO_PS2_C2_SUCCESSOR_MODE == 2
	if (hcu_c2_successor_fault_armed) {
		if (hcu_c2_successor_fault_count++ == 0)
			printf("HALO_PS2_LOCAL successor-fault injected kind=package-read offset=%u size=%u\n",
				(unsigned)offset, (unsigned)size);
		return HCU_ASSET_PROFILE_E_STATE;
	}
#elif HALO_PS2_C2_SUCCESSOR_MODE == 3
	/* Fail only inside the real CTAG visitor, after at least one 64 KiB
	 * segment has reached CE's sink. Candidate preflight has callbacks_active
	 * zero and is never faulted. */
	if (hcu_c2_successor_fault_armed &&
		s_map_service.profile_mount.active &&
		s_map_service.profile_mount.callbacks_active &&
		s_c2s_fault_bytes >= 65536u) {
		if (hcu_c2_successor_fault_count++ == 0)
			printf("HALO_PS2_LOCAL successor-fault injected kind=hcp-ctag-chunk-read callbacks=%u prior-bytes=%u offset=%u size=%u\n",
				(unsigned)s_map_service.profile_mount.callbacks_active,
				(unsigned)s_c2s_fault_bytes, (unsigned)offset, (unsigned)size);
		return HCU_ASSET_PROFILE_E_STATE;
	}
#endif
	ok = hcu_c2_read_at(&s_c2s_package, offset, destination, size);
#if HALO_PS2_C2_SUCCESSOR_MODE == 3
	if (ok && hcu_c2_successor_fault_armed &&
		s_map_service.profile_mount.active &&
		s_map_service.profile_mount.callbacks_active)
		s_c2s_fault_bytes += size;
#endif
	return ok ?
		HCU_ASSET_PROFILE_OK : HCU_ASSET_PROFILE_E_STATE;
}

static int hcu_c2s_source_read(void *context, int32_t output_datum,
	uint32_t file_offset, uint32_t size, void *buffer, int blocking)
{
	uint32_t i;
	(void)context;
	(void)blocking;
	for (i = 0; i < HCU_C2_SUCC_DATUM_COUNT; ++i)
		if (HCU_C2_SUCC_DATUMS[i].output_datum == (uint32_t)output_datum) break;
	if (i == HCU_C2_SUCC_DATUM_COUNT) return 0;
	return hcu_c2_read_at(&s_c2s_sources[HCU_C2_SUCC_DATUMS[i].source],
		file_offset, buffer, size);
}

static int hcu_c2s_compatible(void *context, const hcu_map_catalog_entry *entry,
	const hcu_asset_profile_view *profile)
{
	(void)context;
	return entry && profile &&
		strcmp(entry->identity.map_name, HCU_C2_SUCC_MAP) == 0 &&
		profile->profile_id == HCU_C2_SUCC_PROFILE_ID;
}
#endif
#endif

/* Registers the selected row's profile runtime with the map service. A
 * bootstrap boot has no runtime and keeps the legacy path. A qualified row
 * fails closed unless the generated image header is built in and every input
 * opens at its pinned size. Metadata and relocation storage come from the
 * streaming map owner; the stream scratch comes from the section scratch.
 * The frame owner is not wired yet, so unload fails closed. */
static int hcu_register_selected_runtime(hcu_map_service *service,
	arena_t *owner, arena_t *scratch)
{
	if (!s_partition_selected) return 1;
	if (!service || !s_partition.residency_base ||
		s_partition.residency_bytes != HCU_PARTITION_RESIDENCY_SLOTS * 65536u) {
		printf("[err] partition %s has no residency span for the map service\n",
			s_partition_name);
		return 0;
	}
	memset(s_residency_entries, 0, sizeof(s_residency_entries));
#ifdef HALO_HCU_PROFILE_IMAGE_HEADER
	{
		hcu_map_profile_runtime runtime;
		void *metadata_storage;
		void *relocation_storage;
		void *stream_scratch;
		if (strcmp(s_partition_name, HCU_C2_IMAGE_ROW) != 0) {
			printf("[err] partition %s does not match the generated image row %s\n",
				s_partition_name, HCU_C2_IMAGE_ROW);
			return 0;
		}
		if (!hcu_c2_open_image_files()) {
			printf("[err] partition %s: package or source maps are not under the asset root\n",
				s_partition_name);
			return 0;
		}
		metadata_storage = arena_alloc(owner, HCU_C2_IMAGE_METADATA_STORAGE_BYTES, 16);
		relocation_storage = arena_alloc(owner, HCU_C2_IMAGE_RELOCATION_BYTES, 16);
		stream_scratch = arena_alloc(scratch, HCU_C2_STREAM_SCRATCH_BYTES, 16);
		if (!metadata_storage || !relocation_storage || !stream_scratch) {
			printf("[err] partition %s: owner storage cannot hold metadata %u, relocations %u and stream scratch %u\n",
				s_partition_name, (unsigned)HCU_C2_IMAGE_METADATA_STORAGE_BYTES,
				(unsigned)HCU_C2_IMAGE_RELOCATION_BYTES,
				(unsigned)HCU_C2_STREAM_SCRATCH_BYTES);
			hcu_c2_close_image_files();
			return 0;
		}
		memset(&runtime, 0, sizeof(runtime));
		runtime.package_read_at = hcu_c2_package_read_at;
		runtime.package_size = HCU_C2_IMAGE_PACKAGE_BYTES;
		runtime.profile_id = HCU_C2_IMAGE_PROFILE_ID;
		memcpy(runtime.package_sha256, HCU_C2_IMAGE_PACKAGE_SHA256, 32);
		runtime.compatibility = hcu_c2_compatible;
		runtime.metadata_bytes = HCU_C2_IMAGE_METADATA;
		runtime.metadata_size = HCU_C2_IMAGE_METADATA_BYTES;
		memcpy(runtime.metadata_sha256, HCU_C2_IMAGE_METADATA_SHA256, 32);
		runtime.metadata_storage = metadata_storage;
		runtime.metadata_storage_bytes = HCU_C2_IMAGE_METADATA_STORAGE_BYTES;
		runtime.source_read = hcu_c2_source_read;
		runtime.relocation_storage = relocation_storage;
		runtime.relocation_storage_bytes = HCU_C2_IMAGE_RELOCATION_BYTES;
		runtime.stream_scratch = stream_scratch;
		runtime.stream_scratch_bytes = HCU_C2_STREAM_SCRATCH_BYTES;
		runtime.maximum_tag_image_bytes = (uint32_t)s_partition.tag_cache_bytes;
		runtime.renderer_drained = hcu_renderer_drained;
		runtime.renderer_quiesce = hcu_renderer_quiesce;
		runtime.renderer_quiesce_context = NULL;
#ifdef HCU_C3_RENDER_BUILT
		runtime.frame_owner = &hcu_c3_bitmap_frame_owner;
#endif
#ifdef HALO_HCU_HEADLESS_RUNTIME_GUEST
		runtime.headless_no_bitmap_consumers = 1;
		runtime.renderer_never_started = hcu_renderer_never_started;
		runtime.headless_candidate_admission = 1;
		runtime.partition_row = HCU_C2_IMAGE_ROW;
#endif
		runtime.residency_entries = s_residency_entries;
#ifdef HCU_C2_SUCCESSOR_BUILT
		/* The successor stages beside the live map, so the two runtimes split
		 * the row's residency span: the selected row keeps the first half. */
		runtime.residency_entry_capacity = HCU_PARTITION_RESIDENCY_SLOTS / 2u;
		runtime.residency_arena = s_partition.residency_base;
		runtime.residency_arena_bytes = s_partition.residency_bytes / 2u;
#else
		runtime.residency_entry_capacity = HCU_PARTITION_RESIDENCY_SLOTS;
		runtime.residency_arena = s_partition.residency_base;
		runtime.residency_arena_bytes = s_partition.residency_bytes;
#endif
		if (!hcu_map_service_register_runtime(service, HCU_C2_IMAGE_MAP, &runtime)) {
			printf("[err] partition %s: map service refused the profile runtime (digest, compatibility or span check)\n",
				s_partition_name);
			hcu_c2_close_image_files();
			return 0;
		}
		printf("HALO_PS2_LOCAL profile-runtime row=%s map=%s profile=%u package-bytes=%u metadata-bytes=%u metadata-storage=%u relocation-bytes=%u stream-scratch=%u residency-bytes=%u\n",
			s_partition_name, HCU_C2_IMAGE_MAP, (unsigned)HCU_C2_IMAGE_PROFILE_ID,
			(unsigned)HCU_C2_IMAGE_PACKAGE_BYTES,
			(unsigned)HCU_C2_IMAGE_METADATA_BYTES,
			(unsigned)HCU_C2_IMAGE_METADATA_STORAGE_BYTES,
			(unsigned)HCU_C2_IMAGE_RELOCATION_BYTES,
			(unsigned)HCU_C2_STREAM_SCRATCH_BYTES,
			(unsigned)s_partition.residency_bytes);
		return 1;
	}
#else
	(void)owner;
	(void)scratch;
	printf("[err] partition %s cannot register its profile runtime: no generated image header is built into this image (define HALO_HCU_PROFILE_IMAGE_HEADER)\n",
		s_partition_name);
	return 0;
#endif
}

#ifdef HCU_C2_SUCCESSOR_BUILT
/* Registers the successor row's runtime beside the selected row's. It carries
 * its own metadata, relocation, scratch and residency spans (the second half of
 * the row's residency span), all disjoint from the selected runtime's, and the
 * selected row's partition caps: the successor's tag image and BSP must fit the
 * selected row's guarded owners. */
static int hcu_register_successor_runtime(hcu_map_service *service,
	arena_t *owner, arena_t *scratch)
{
	hcu_map_profile_runtime runtime;
	void *metadata_storage;
	void *relocation_storage;
	void *stream_scratch;
	if (!s_partition_selected) return 1;
	if (!hcu_c2s_open_files()) {
		printf("[err] partition %s: successor package or source maps are not under the asset root\n",
			s_partition_name);
		return 0;
	}
	memset(s_c2s_residency_entries, 0, sizeof(s_c2s_residency_entries));
	metadata_storage = arena_alloc(owner, HCU_C2_SUCC_METADATA_STORAGE_BYTES, 16);
	relocation_storage = arena_alloc(owner, HCU_C2_SUCC_RELOCATION_BYTES, 16);
	stream_scratch = arena_alloc(scratch, HCU_C2_STREAM_SCRATCH_BYTES, 16);
	if (!metadata_storage || !relocation_storage || !stream_scratch) {
		printf("[err] partition %s: owner storage cannot hold successor metadata %u, relocations %u and stream scratch %u\n",
			s_partition_name, (unsigned)HCU_C2_SUCC_METADATA_STORAGE_BYTES,
			(unsigned)HCU_C2_SUCC_RELOCATION_BYTES,
			(unsigned)HCU_C2_STREAM_SCRATCH_BYTES);
		hcu_c2s_close_files();
		return 0;
	}
	memset(&runtime, 0, sizeof(runtime));
	runtime.package_read_at = hcu_c2s_package_read_at;
	runtime.package_size = HCU_C2_SUCC_PACKAGE_BYTES;
	runtime.profile_id = HCU_C2_SUCC_PROFILE_ID;
	memcpy(runtime.package_sha256, HCU_C2_SUCC_PACKAGE_SHA256, 32);
	runtime.compatibility = hcu_c2s_compatible;
	runtime.metadata_bytes = HCU_C2_SUCC_METADATA;
	runtime.metadata_size = HCU_C2_SUCC_METADATA_BYTES;
	memcpy(runtime.metadata_sha256, HCU_C2_SUCC_METADATA_SHA256, 32);
	runtime.metadata_storage = metadata_storage;
	runtime.metadata_storage_bytes = HCU_C2_SUCC_METADATA_STORAGE_BYTES;
	runtime.source_read = hcu_c2s_source_read;
	runtime.relocation_storage = relocation_storage;
	runtime.relocation_storage_bytes = HCU_C2_SUCC_RELOCATION_BYTES;
	runtime.stream_scratch = stream_scratch;
	runtime.stream_scratch_bytes = HCU_C2_STREAM_SCRATCH_BYTES;
	runtime.maximum_tag_image_bytes = (uint32_t)s_partition.tag_cache_bytes;
	runtime.renderer_drained = hcu_renderer_drained;
	runtime.renderer_quiesce = hcu_renderer_quiesce;
	runtime.renderer_quiesce_context = NULL;
#ifdef HCU_C3_RENDER_BUILT
	runtime.frame_owner = &hcu_c3_bitmap_frame_owner;
#endif
	runtime.headless_no_bitmap_consumers = 1;
	runtime.renderer_never_started = hcu_renderer_never_started;
	runtime.headless_candidate_admission = 1;
	runtime.partition_row = HCU_C2_IMAGE_ROW;
	runtime.residency_entries = s_c2s_residency_entries;
	runtime.residency_entry_capacity = HCU_PARTITION_RESIDENCY_SLOTS / 2u;
	runtime.residency_arena = (uint8_t *)s_partition.residency_base +
		s_partition.residency_bytes / 2u;
	runtime.residency_arena_bytes = s_partition.residency_bytes / 2u;
	if (!hcu_map_service_register_successor_runtime(service, HCU_C2_SUCC_MAP, &runtime)) {
		printf("[err] partition %s: map service refused the successor runtime for %s (digest, compatibility or disjointness)\n",
			s_partition_name, HCU_C2_SUCC_MAP);
		hcu_c2s_close_files();
		return 0;
	}
	printf("HALO_PS2_LOCAL successor-runtime row=%s successor-row=%s map=%s profile=%u package-bytes=%u metadata-bytes=%u metadata-storage=%u relocation-bytes=%u stream-scratch=%u residency-bytes=%u residency-entries=%u\n",
		s_partition_name, HCU_C2_SUCC_ROW, HCU_C2_SUCC_MAP,
		(unsigned)HCU_C2_SUCC_PROFILE_ID, (unsigned)HCU_C2_SUCC_PACKAGE_BYTES,
		(unsigned)HCU_C2_SUCC_METADATA_BYTES,
		(unsigned)HCU_C2_SUCC_METADATA_STORAGE_BYTES,
		(unsigned)HCU_C2_SUCC_RELOCATION_BYTES,
		(unsigned)HCU_C2_STREAM_SCRATCH_BYTES,
		(unsigned)runtime.residency_arena_bytes,
		(unsigned)runtime.residency_entry_capacity);
	return 1;
}
#endif

/* Registers every named owner with capacities from the bound layout. Called
 * after CE binding and before the first map service request. */
static void hcu_bind_owner_telemetry(mem_layout_v2_t *layout,
	const arena_t *frame_scratch, const arena_t *dma_commands,
	const arena_t *streaming)
{
	const arena_t *bsp = mem_layout_v2_get(layout, MEM_LAYOUT_V2_CURRENT_BSP);
	const arena_t *texture = mem_layout_v2_get(layout, MEM_LAYOUT_V2_TEXTURE_CACHE);
	const arena_t *audio = mem_layout_v2_get(layout, MEM_LAYOUT_V2_AUDIO);
	size_t tag_bytes = s_partition_selected ? s_partition.tag_cache_bytes
		: (size_t)HALO_HCU_TAG_CACHE_BYTES;
	size_t bsp_bytes = s_partition_selected ? s_partition.structure_bsp_bytes
		: (bsp ? bsp->cap - (size_t)HALO_HCU_TAG_CACHE_BYTES : 0);

	hcu_owner_telemetry_init(&s_owner_telemetry);
	memset(s_owner_ctx, 0, sizeof s_owner_ctx);

	/* Game state and its nested object/actor pools are charged by CE's own
	 * cursors and read through the always-on port counters. */
	hcu_owner_telemetry_bind_sampler(&s_owner_telemetry, HCU_OWNER_GAME_STATE,
		hcu_sample_ce_owner, (void *)(intptr_t)HALO_PS2_OWNER_GAME_STATE);
	hcu_owner_telemetry_bind_sampler(&s_owner_telemetry, HCU_OWNER_OBJECT_POOL,
		hcu_sample_ce_owner, (void *)(intptr_t)HALO_PS2_OWNER_OBJECT_POOL);
	hcu_owner_telemetry_bind_sampler(&s_owner_telemetry, HCU_OWNER_ACTOR_POOL,
		hcu_sample_ce_owner, (void *)(intptr_t)HALO_PS2_OWNER_ACTOR_POOL);
	/* The current UI adapter initializes CE widgets but does not allocate a
	 * separate widget stack pool; leave that nested row unbound. */

	hcu_owner_telemetry_bind_sampler(&s_owner_telemetry, HCU_OWNER_DYNAMIC_SIM,
		hcu_sample_dynamic_simulation, NULL);
	hcu_owner_telemetry_bind_sampler(&s_owner_telemetry,
		HCU_OWNER_DECODED_ASSET_RESIDENCY,
		hcu_sample_decoded_asset_residency, NULL);

	s_owner_ctx[HCU_OWNER_TAGS].capacity = tag_bytes;
	hcu_owner_telemetry_bind_sampler(&s_owner_telemetry, HCU_OWNER_TAGS,
		hcu_sample_tags, &s_owner_ctx[HCU_OWNER_TAGS]);

	s_owner_ctx[HCU_OWNER_BSP].capacity = bsp_bytes;
	hcu_owner_telemetry_bind_sampler(&s_owner_telemetry, HCU_OWNER_BSP,
		hcu_sample_bsp, &s_owner_ctx[HCU_OWNER_BSP]);

	s_owner_ctx[HCU_OWNER_STREAMING].arena = streaming;
	hcu_owner_telemetry_bind_sampler(&s_owner_telemetry, HCU_OWNER_STREAMING,
		hcu_sample_arena, &s_owner_ctx[HCU_OWNER_STREAMING]);

	s_owner_ctx[HCU_OWNER_SCRATCH].arena = frame_scratch;
	hcu_owner_telemetry_bind_sampler(&s_owner_telemetry, HCU_OWNER_SCRATCH,
		hcu_sample_arena, &s_owner_ctx[HCU_OWNER_SCRATCH]);

	s_owner_ctx[HCU_OWNER_DMA].arena = dma_commands;

	/* No separate request queue exists yet; the audio region is the closest
	 * owned store and is reported under its own name, not as a queue. */
	s_owner_ctx[HCU_OWNER_AUDIO_REQUESTS].arena = audio;
	hcu_owner_telemetry_bind_sampler(&s_owner_telemetry, HCU_OWNER_AUDIO_REQUESTS,
		hcu_sample_arena, &s_owner_ctx[HCU_OWNER_AUDIO_REQUESTS]);

	if (!hcu_render_telemetry_bind(&s_owner_telemetry, texture))
		printf("[err] could not bind renderer owners to EE and GS telemetry domains\n");
}

static void hcu_report_cache_owners(const char *phase)
{
	halo_ps2_cache_owner_telemetry usage;
	ps2_cache_get_owner_telemetry(&usage);
	printf("HALO_PS2_LOCAL cache-owner phase=%s name=tags current=%u peak=%u "
		"publications=%u failures=%u unmounts=%u resets=%u\n", phase,
		(unsigned)usage.tag_current_bytes, (unsigned)usage.tag_peak_bytes,
		(unsigned)usage.tag_publications, (unsigned)usage.tag_failures,
		(unsigned)usage.tag_unmounts, (unsigned)usage.tag_resets);
	printf("HALO_PS2_LOCAL cache-owner phase=%s name=bsp current=%u peak=%u "
		"publications=%u failures=%u unmounts=%u resets=%u lease_failures=%u "
		"readers_drained=%d mount_rejections=%u\n", phase,
		(unsigned)usage.bsp_current_bytes, (unsigned)usage.bsp_peak_bytes,
		(unsigned)usage.bsp_publications, (unsigned)usage.bsp_failures,
		(unsigned)usage.bsp_unmounts, (unsigned)usage.bsp_resets,
		(unsigned)usage.bsp_lease_failures, ps2_cache_bsp_readers_drained(),
		(unsigned)usage.mount_rejections);
}

/* C3:replace begin */
#if defined(HCU_C3_FRAME_SNAPSHOT)
#include "stream/hcu_sound_requests.h"
#include "ps2_sound_playback.h"
/* Defined by the CE port (ps2_sound_cache.c). This seam reports permutation
 * cache requests only; playback event context is unavailable here. */
void halo_ps2_sound_request_bind_sink(
	void (*sink)(void *context, const void *sound, int block, int load,
		int reference, int accepted),
	void *context);
static hcu_sound_request_queue s_c3_sound_queue;
static void hcu_c3_sound_request_sink(void *context, const void *sound,
	int block, int load, int reference, int accepted)
{
	hcu_sound_request request;
	(void)context;
	memset(&request, 0, sizeof(request));
	request.event = HCU_SOUND_EVENT_PERMUTATION_REQUEST;
	request.permutation = (uint32_t)(uintptr_t)sound;
	request.owner_datum = UINT32_MAX;
	request.sound_index = UINT32_MAX;
	request.flags = (uint8_t)((block ? 1u : 0u) | (load ? 2u : 0u) |
		(reference ? 4u : 0u));
	request.priority = UINT8_MAX;
	request.accepted = accepted ? 1u : 0u;
	/* Owner, position, priority, gain, pitch and game time are not arguments
	 * to _sound_cache_sound_request. Leave them explicitly unknown. */
	request.gain = 0.0f;
	request.pitch = 0.0f;
	request.metadata_known = 0;
	(void)hcu_sound_requests_submit(&s_c3_sound_queue, &request);
}
/* C3:sound begin */
#if defined(HCU_C3_FRAME_SNAPSHOT)
/* Drains the request ring once per CE tick, so gameplay never fills it. The
 * drainer only counts records until SPU2 playback is qualified. */
static void hcu_c3_sound_tick(void)
{
	static unsigned ticks;
	(void)hcu_sound_requests_drain_each(&s_c3_sound_queue, NULL, NULL,
		HCU_SOUND_REQUEST_CAPACITY);
	/* Counters only, once per 30 ticks to match the periodic c3-frame cadence. */
	if (++ticks % 30u == 0u)
		hcu_sound_requests_print(&s_c3_sound_queue, "periodic");
}
#endif
/* C3:sound end */
static void hcu_c3_sound_playback_sink(void *context, const void *sound,
	unsigned event, unsigned sound_definition, int owner_kind, unsigned owner_datum, int has_position,
	float x, float y, float z, int priority, float gain, float pitch,
	unsigned game_time, unsigned metadata_known)
{
	hcu_sound_request request;
	float position[3];
	uint16_t captured_owner_kind;
	uint32_t captured_owner_datum;
	uint8_t captured_metadata_known;
	(void)context;
	captured_owner_kind = owner_kind >= HCU_SOUND_OWNER_NONE &&
		owner_kind <= HCU_SOUND_OWNER_CE_SOURCE ? (uint16_t)owner_kind :
		HCU_SOUND_OWNER_NONE;
	captured_owner_datum = owner_kind >= 0 ? (uint32_t)owner_datum : UINT32_MAX;
	captured_metadata_known = (uint8_t)metadata_known;
	if (priority < 0 || priority >= 255)
		captured_metadata_known &= (uint8_t)~0x04u;
	position[0] = x; position[1] = y; position[2] = z;
	if (!hcu_sound_request_capture_playback(&request, (uint16_t)event,
		(uint32_t)(uintptr_t)sound, sound_definition, captured_owner_kind,
		captured_owner_datum, has_position, position,
		priority >= 0 && priority < 255 ? (uint8_t)priority : UINT8_MAX,
		gain, pitch, game_time, captured_metadata_known))
		return;
	(void)hcu_sound_requests_submit(&s_c3_sound_queue, &request);
}
#endif
/* C3:replace end */

/* Map boundary telemetry: the owner counters and the cache owners at each
 * map load, release and empty state of the lifecycle. */
static void hcu_map_boundary_report(void *context, const char *phase,
	unsigned int cycle)
{
	hcu_map_residency_report residency;
	(void)context;
	/* The runtime owner points into profile metadata. Unbind only after the
	 * map service has completed CE teardown and released that backing. */
#ifdef HCU_C3_RENDER_BUILT
	if (phase && strcmp(phase, "map-released") == 0 &&
		!hcu_c3_bitmap_map_released())
		printf("HALO_PS2_FAIL c3-bitmap map-released owner-unbind-failed cycle=%u\n", cycle);
#endif
	printf("HALO_PS2_LOCAL m2-cycle-boundary phase=%s cycle=%u\n", phase, cycle);
	hcu_report_owner_telemetry(phase);
	/* C3:replace begin */
#if defined(HCU_C3_FRAME_SNAPSHOT)
	/* Drain once per boundary. The audio side is not qualified, so drained
	 * records are only counted, never played. */
	(void)hcu_sound_requests_drain_each(&s_c3_sound_queue, NULL, NULL,
		HCU_SOUND_REQUEST_CAPACITY);
	hcu_sound_requests_print(&s_c3_sound_queue, phase);
	printf("HALO_PS2_LOCAL renderer-readers phase=%s outstanding=%u refused=%u\n",
		phase, (unsigned)hcu_map_service_reader_count(&s_map_service),
		(unsigned)s_map_service.reader_refused);
#endif
	/* C3:replace end */
	if (hcu_map_service_residency_snapshot(&s_map_service, &residency) &&
		residency.valid && residency.map.bound) {
		printf("HALO_PS2_LOCAL decoded-residency phase=%s scope=map map=%s cycle=%u "
			"active=%d bound=%d cap=%u current=%u high=%u evictions=%u "
			"refused_evictions=%u refused_pins=%u verify_failures=%u resets=%u "
			"lifetime_high=%u lifetime_evictions=%u lifetime_refused_evictions=%u "
			"lifetime_refused_pins=%u lifetime_verify_failures=%u lifetime_resets=%u\n",
			phase, residency.map_name, residency.cycle, residency.active,
			residency.map.bound, (unsigned)residency.map.capacity_bytes,
			(unsigned)residency.map.current_bytes,
			(unsigned)residency.map.high_water_bytes,
			(unsigned)residency.map.evictions,
			(unsigned)residency.map.refused_evictions,
			(unsigned)residency.map.refused_pins,
			(unsigned)residency.map.verify_failures,
			(unsigned)residency.map.resets,
			(unsigned)residency.lifetime.high_water_bytes,
			(unsigned)residency.lifetime.evictions,
			(unsigned)residency.lifetime.refused_evictions,
			(unsigned)residency.lifetime.refused_pins,
			(unsigned)residency.lifetime.verify_failures,
			(unsigned)residency.lifetime.resets);
	}
	hcu_report_cache_owners(phase);
#ifdef HCU_C2_SUCCESSOR_BUILT
	if (s_c2s_owner_arena)
		printf("HALO_PS2_LOCAL arena phase=%s name=%s cap=%u used=%u high=%u "
			"alloc_failures=%u resets=%u releases=%u invalid_releases=%u\n",
			phase, s_c2s_owner_arena->name, (unsigned)s_c2s_owner_arena->cap,
			(unsigned)s_c2s_owner_arena->used, (unsigned)s_c2s_owner_arena->high,
			(unsigned)s_c2s_owner_arena->failed_allocations,
			(unsigned)s_c2s_owner_arena->reset_count,
			(unsigned)s_c2s_owner_arena->release_count,
			(unsigned)s_c2s_owner_arena->invalid_releases);
#endif
}
#ifdef HALO_PS2_STEP8_MP_CAPACITY_DIAGNOSTIC
static mem_layout_v2_t *s_step8_candidate_layout;
#endif

/* The host link/guest placement gate budgets this exact worst-case padding. */
_Static_assert(MEM_LAYOUT_V2_GUARDED_SLACK == 310u,
	"update the M1 physical placement probe when guard layout changes");

static const char *const s_region_names[MEM_LAYOUT_V2_REGION_COUNT] = {
	"resident_gameplay", "current_bsp", "texture_cache",
	"dynamic_simulation", "dma_commands", "streaming", "checkpoint",
	"audio", "frame_scratch"
};

/* The machine owns the target mode; CE's CPU camera uses these dimensions
 * without taking ownership of GS setup or drawing. */
long halo_screen_width(void) { return VIDEO_WIDTH; }
long halo_ps2_display_height(void) { return VIDEO_HEIGHT; }

int ps2_abi_check(void);
void physical_memory_allocate(void);
int physical_memory_ready(void);
void physical_memory_free(void);
int halo_shell_main(void);
void *__real_malloc(unsigned long size);
void __real_free(void *ptr);
extern char _fbss;
extern char _end;
extern char _ftext;

#ifdef HALO_PS2_M3_RENDER_CLEAR_TEST
/*
 * Diagnostic-only GS bring-up before bsp_render_init(). Borrow a small packet
 * from geometry chain 0 while all four bound chains are still idle.
 */
static int hcu_m3_render_clear_test(void *dma_storage, size_t dma_bytes)
{
	video_t video;
	packet2_t packet;
	uintptr_t packet_address;
	uintptr_t storage_start = (uintptr_t)dma_storage;
	const size_t packet_bytes = 64u * sizeof(qword_t);
	const uint32_t fb_words = (VIDEO_WIDTH * VIDEO_HEIGHT) / 2u;
	const uint32_t z_words = VIDEO_WIDTH * VIDEO_HEIGHT;
	const uint32_t tex_words = 2048u;
	uint32_t fb0, fb1, zbuf, texture;

	if (!dma_storage || dma_bytes < packet_bytes + 63u)
		return -1;
	packet_address = (storage_start + 63u) & ~(uintptr_t)63u;
	if (packet_address < storage_start ||
		packet_address > storage_start + dma_bytes ||
		packet_bytes > storage_start + dma_bytes - packet_address)
		return -1;
	/* packet2_create_from() allocates its descriptor and packet2_free() frees
	 * the borrowed base. Initialize the public descriptor over arena storage
	 * directly to preserve the no-post-boot-allocation contract. */
	memset(&packet, 0, sizeof packet);
	packet.max_qwords_count = 64;
	packet.type = P2_TYPE_NORMAL;
	packet.mode = P2_MODE_NORMAL;
	packet.base = packet.next = (qword_t *)packet_address;
	memset(packet.base, 0, packet_bytes);

	dma_channel_initialize(DMA_CHANNEL_GIF, NULL, 0);
	dma_channel_fast_waits(DMA_CHANNEL_GIF);
	video_init(&video);
	fb0 = video.fb[0].address;
	fb1 = video.fb[1].address;
	zbuf = video.z.address;
	texture = video.tex_base;
	if (fb0 == UINT32_MAX || fb1 == UINT32_MAX || zbuf == UINT32_MAX ||
		texture == UINT32_MAX || fb0 > VIDEO_VRAM_WORDS ||
		fb_words > VIDEO_VRAM_WORDS - fb0 || fb1 > VIDEO_VRAM_WORDS ||
		fb_words > VIDEO_VRAM_WORDS - fb1 || zbuf > VIDEO_VRAM_WORDS ||
		z_words > VIDEO_VRAM_WORDS - zbuf || texture > VIDEO_VRAM_WORDS ||
		tex_words > VIDEO_VRAM_WORDS - texture ||
		(fb0 < fb1 + fb_words && fb1 < fb0 + fb_words) ||
		(fb0 < zbuf + z_words && zbuf < fb0 + fb_words) ||
		(fb1 < zbuf + z_words && zbuf < fb1 + fb_words) ||
		(texture < fb0 + fb_words && fb0 < texture + tex_words) ||
		(texture < fb1 + fb_words && fb1 < texture + tex_words) ||
		(texture < zbuf + z_words && zbuf < texture + tex_words)) {
		printf("HALO_PS2_FAIL m3 GS eDRAM ranges invalid or overlapping\n");
		return -1;
	}
	video_add_setup_env(&video, &packet);
	video_add_clear(&video, &packet, 24, 72, 120);
	packet2_update(&packet, draw_finish(packet.next));
	if ((uintptr_t)packet.next < packet_address ||
		((uintptr_t)packet.next - packet_address) % sizeof(qword_t) != 0u ||
		((uintptr_t)packet.next - packet_address) / sizeof(qword_t) == 0u ||
		((uintptr_t)packet.next - packet_address) / sizeof(qword_t) >
			packet.max_qwords_count) {
		printf("HALO_PS2_FAIL m3 GIF clear packet exceeded its arena slice\n");
		return -1;
	}
	dma_channel_send_packet2(&packet, DMA_CHANNEL_GIF, 1);
	dma_wait_fast();
	draw_wait_finish();
	video_present(&video);
	printf("HALO_PS2_LOCAL m3-render-clear-presented color=24,72,120 frames=%u\n",
		(unsigned)video.frames);
	return 0;
}
#endif

static uintptr_t ee_physical_address(const void *pointer)
{
	uintptr_t address = (uintptr_t)pointer;
	if (address >= 0x80000000u && address < 0xc0000000u)
		return address & 0x1fffffffu;
	return address;
}

/* C3:render begin */
/* C3.4/C3.5/C3.6/C3.10 render loop for the headless runtime guest. Compiled only with HCU_C3 and
 * only when <hcu_c3_render.h> (written by tools/c2_profile_boot_matrix.py --c3 --render-views N)
 * is on the include path; it defines HCU_C3_RENDER_VIEWS (1..4) and HCU_C3_RENDER_FRAMES. The CE
 * guest calls the three hooks below (halo-ce-universal source/main/main.c, C3:render blocks):
 * after the map loads, once per in-map tick, and before the map is released. */
#ifdef HCU_C3_RENDER_BUILT
#include "stream/hcu_render_media.h"
#include "stream/hcu_render_frame.h"
#include "render/camera.h"
/* C3:texfence begin */
/* C3.7 texture fence counters. They are recorded inside the texture cache at the real event points
 * (tc_publish_claim, the upload chain release and the eviction path); this block only prints them.
 * HCU_C3_TEXFENCE_CAP_PAGES (debug, 0 = off) caps the renderer's texture cache pages so that slot reuse
 * happens under pressure; it is set by --texfence-cap-pages in the boot matrix. */
#ifndef HCU_C3_TEXFENCE_CAP_PAGES
#define HCU_C3_TEXFENCE_CAP_PAGES 0
#endif

static void hcu_c3_print_texfence(const char *kind, uint32_t frame)
{
	const tc_fence_t *t = bsp_render_texfence_counters();
	printf("HALO_PS2_LOCAL c3-texfence kind=%s frame=%u kick-seq=%u fence-seq=%u claims-published=%u "
		"claims-published-before-queue=%u source-released=%u source-released-before-fence=%u "
		"reuse-blocked-by-fence=%u reuse-after-fence=%u reuse-unfenced=%u evictions=%u cap-pages=%u\n",
		kind, (unsigned)frame, (unsigned)bsp_render_kick_seq(), (unsigned)bsp_render_completed_kick_seq(),
		(unsigned)t->claims_published, (unsigned)t->claims_published_before_queue,
		(unsigned)t->sources_released, (unsigned)t->source_released_before_fence,
		(unsigned)t->reuse_blocked_by_fence, (unsigned)t->reuse_after_fence, (unsigned)t->reuse_unfenced,
		(unsigned)t->evictions, (unsigned)HCU_C3_TEXFENCE_CAP_PAGES);
}
/* C3:texfence end */
#ifndef HCU_C3_RENDER_VIEWS
#define HCU_C3_RENDER_VIEWS 1
#endif
#ifndef HCU_C3_RENDER_FRAMES
#define HCU_C3_RENDER_FRAMES 300
#endif
#ifndef HCU_C3_RENDER_HOLD_VSYNCS
#define HCU_C3_RENDER_HOLD_VSYNCS 240
#endif
#define HCU_C3_DEG 0.017453292519943295f

typedef struct {
	int active, gs_ready;
	uint32_t frames;
	hcu_render_media media;
	hcu_render_world world;
	arena_t level;
	video_t video;
	hcu_render_frame_state state;
	uint32_t bank_views;
	uint32_t draw_batches_last, draw_tris_last, uploads_last, textured_miss_last;
} hcu_c3_render_state;

static hcu_c3_render_state s_c3r;
static qword_t s_c3_prime_packet[8] __attribute__((aligned(64)));
static int s_c3_bitmap_detach_ok = 1;

static void hcu_c3_flush(void *base, size_t bytes)
{
	SyncDCache(base, (uint8_t *)base + bytes);
}

/* Fixed spawn cameras (x y z yaw pitch, degrees); view 0 is the independently checked Blood Gulch
 * reference valley view, the rest are other fixed Blood Gulch vantage points. They do not come from
 * the CE snapshot bank: the headless guest never runs CE render_frame, so no snapshot is published. */
static const float s_c3_cameras[4][5] = {
	{ 65.0f, -95.0f, 9.0f, -70.0f, -5.0f },
	{ 98.49f, -157.64f, 3.10f, 76.1f, 0.0f },
	{ 65.0f, -145.0f, 32.0f, 84.0f, -5.0f },
	{ 118.0f, -105.0f, 32.0f, -167.0f, -5.0f }
};

static void hcu_c3_make_camera(camera_t *c, unsigned view)
{
	camera_init(c);
	c->far_z = 4000.0f;
	c->pos[0] = s_c3_cameras[view][0];
	c->pos[1] = s_c3_cameras[view][1];
	c->pos[2] = s_c3_cameras[view][2];
	c->yaw = s_c3_cameras[view][3] * HCU_C3_DEG;
	c->pitch = s_c3_cameras[view][4] * HCU_C3_DEG;
}

/* Queue one GS FINISH (no allocation: a static packet). The renderer's present and clear_world both
 * wait for a pending FINISH, and graph_wait_vsync() consumes it. */
static void hcu_c3_prime_finish(void)
{
	packet2_t p;
	memset(&p, 0, sizeof p);
	p.max_qwords_count = 8;
	p.type = P2_TYPE_NORMAL;
	p.mode = P2_MODE_NORMAL;
	p.base = p.next = s_c3_prime_packet;
	packet2_update(&p, draw_finish(p.next));
	dma_channel_send_packet2(&p, DMA_CHANNEL_GIF, 1);
	dma_wait_fast();
}

static void hcu_c3_gs_init(void)
{
	if (s_c3r.gs_ready) return;
	dma_channel_initialize(DMA_CHANNEL_GIF, NULL, 0);
	dma_channel_fast_waits(DMA_CHANNEL_GIF);
	video_init(&s_c3r.video);
	if (bsp_render_init(&s_c3r.video)) {
		printf("HALO_PS2_FAIL c3-render bsp_render_init\n");
		return;
	}
	hcu_c3_prime_finish();
	s_c3r.gs_ready = 1;
}

/* Decode the already integrity-checked HCM again into the same runtime arena
 * used by profile preflight. Its arrays have the identical fixed layout, so
 * the mounted CBSP/range pointers remain at the same addresses and contents. */
int hcu_c3_bitmap_profile_prepare(void)
{
	const hcu_map_profile_runtime *rt = &s_map_service.runtime;
	uint32_t i, first_free_key = 0, max_chunk = 0;
	if (!s_map_service.runtime_registered || s_c3_bitmap_bound ||
		hcu_c3_bitmap_frame_owner.bound || !rt->metadata_storage ||
		!rt->metadata_storage_bytes || !rt->metadata_bytes || !rt->metadata_size ||
		hcu_profile_metadata_decode(rt->metadata_bytes, rt->metadata_size,
			rt->metadata_sha256, rt->profile_id, rt->metadata_storage,
			rt->metadata_storage_bytes, &s_c3_bitmap_metadata) != HCU_PROFILE_METADATA_OK ||
		s_c3_bitmap_metadata.profile_id != s_map_service.profile_view.profile_id ||
		!s_c3_bitmap_metadata.bitmap_count || !s_c3_bitmap_metadata.bitmap_bindings ||
		s_c3_bitmap_metadata.bitmap_count > 4096u) {
		printf("HALO_PS2_FAIL c3-bitmap metadata-bindings-unavailable\n");
		return 0;
	}
	for (i = 0; i < s_c3_bitmap_metadata.bitmap_count; ++i) {
		const hcu_bitmap_binding *binding = &s_c3_bitmap_metadata.bitmap_bindings[i];
		hcu_asset_chunk_view chunk;
		uint32_t j;
		if (binding->expected_profile_id != rt->profile_id || binding->cache_key >= TC_MAX_KEYS ||
			binding->image_index != 0u ||
			hcu_asset_profile_lookup(&s_map_service.profile_view, HCU_ASSET_CHUNK_MEDIA,
				binding->chunk_id, &chunk) != HCU_ASSET_PROFILE_OK ||
			memcmp(chunk.sha256, binding->expected_chunk_sha256, 32) != 0) {
			printf("HALO_PS2_FAIL c3-bitmap metadata-binding-invalid index=%u\n", (unsigned)i);
			return 0;
		}
		if (chunk.size > max_chunk) max_chunk = chunk.size;
		if ((uint32_t)binding->cache_key + 1u > first_free_key)
			first_free_key = (uint32_t)binding->cache_key + 1u;
		/* A cache key can only alias an identical media identity. */
		for (j = 0; j < i; ++j) {
			const hcu_bitmap_binding *prior = &s_c3_bitmap_metadata.bitmap_bindings[j];
			if (prior->cache_key == binding->cache_key &&
				(prior->chunk_id != binding->chunk_id || prior->image_index != binding->image_index ||
				prior->expected_source_datum != binding->expected_source_datum ||
				memcmp(prior->expected_chunk_sha256, binding->expected_chunk_sha256, 32) != 0)) {
				printf("HALO_PS2_FAIL c3-bitmap metadata-cache-key-collision key=%u\n",
					(unsigned)binding->cache_key);
				return 0;
			}
		}
	}
	if (!max_chunk || max_chunk > UINT32_MAX - 15u ||
		first_free_key + HCU_C3_BITMAP_OBJECT_KEY_CAPACITY > TC_MAX_KEYS ||
		bsp_render_reserve_texture_key_base(first_free_key,
			HCU_C3_BITMAP_OBJECT_KEY_CAPACITY) != 0) {
		printf("HALO_PS2_FAIL c3-bitmap key-or-chunk-capacity bitmap-key-end=%u object-key-cap=%u max-chunk=%u\n",
			(unsigned)first_free_key, (unsigned)HCU_C3_BITMAP_OBJECT_KEY_CAPACITY,
			(unsigned)max_chunk);
		return 0;
	}
	s_c3_bitmap_key_base = first_free_key;
	printf("HALO_PS2_LOCAL c3-bitmap-metadata profile=%u bindings=%u cache-key-range=0..%u object-key-reserve=%u max-media-chunk=%u\n",
		(unsigned)s_c3_bitmap_metadata.profile_id, (unsigned)s_c3_bitmap_metadata.bitmap_count,
		(unsigned)(first_free_key - 1u), (unsigned)HCU_C3_BITMAP_OBJECT_KEY_CAPACITY,
		(unsigned)max_chunk);
	return 1;
}

int hcu_c3_bitmap_map_bind(void)
{
	const halo_ps2_bitmap_real_producer_descriptor *producer =
		&halo_ps2_real_producer_descriptor_instance;
	const uint32_t generation = s_c3r.world.generation;
	uint32_t max_chunk = 0, staging_bytes, i;
	void *journal, *readers, *source_storage, *staging, *slots, *leases, *queue, *owner_base;
	tc_t *unused_cache = NULL;
	size_t required;
	if (!s_c3r.world.bound || !generation || !s_c3_bitmap_metadata.bitmap_count ||
		!producer || producer->magic != HALO_PS2_BITMAP_REAL_PRODUCER_MAGIC ||
		producer->version != HALO_PS2_BITMAP_REAL_PRODUCER_VERSION ||
		!(producer->capabilities & HALO_PS2_BITMAP_FRAME_PRODUCER_INTERFACE) ||
		(producer->capabilities & ~HALO_PS2_BITMAP_FRAME_REQUIRED_PRODUCERS) != 0) {
		printf("HALO_PS2_FAIL c3-bitmap producer-or-world-not-ready\n");
		return 0;
	}
	for (i = 0; i < s_c3_bitmap_metadata.bitmap_count; ++i) {
		hcu_asset_chunk_view chunk;
		const hcu_bitmap_binding *binding = &s_c3_bitmap_metadata.bitmap_bindings[i];
		if (hcu_asset_profile_lookup(&s_map_service.profile_view, HCU_ASSET_CHUNK_MEDIA,
			binding->chunk_id, &chunk) != HCU_ASSET_PROFILE_OK) return 0;
		if (chunk.size > max_chunk) max_chunk = chunk.size;
	}
	staging_bytes = (max_chunk + 15u) & ~15u;
	if (!staging_bytes || staging_bytes > HCU_C3_BITMAP_OWNER_CAP_BYTES ||
		s_c3r.level.cap < HCU_C3_BITMAP_OWNER_BYTES ||
		s_c3r.level.used > s_c3r.level.cap - HCU_C3_BITMAP_OWNER_BYTES) {
		printf("HALO_PS2_FAIL c3-bitmap owner-tail-unavailable cap=%u used=%u staging=%u reserve=%u\n",
			(unsigned)s_c3r.level.cap, (unsigned)s_c3r.level.used, (unsigned)staging_bytes,
			(unsigned)HCU_C3_BITMAP_OWNER_BYTES);
		return 0;
	}
	/* Keep the measured C3.6 object residency peak available in the capped
	 * object sub-arena. If it cannot fit, refuse bitmap publication. */
#if defined(HCU_C3_OBJECTS)
	if (s_c3r.level.cap - HCU_C3_BITMAP_OWNER_BYTES - s_c3r.level.used < 1400000u) {
		printf("HALO_PS2_FAIL c3-bitmap object-pool-reserve-under-1.4m available=%u\n",
			(unsigned)(s_c3r.level.cap - HCU_C3_BITMAP_OWNER_BYTES - s_c3r.level.used));
		return 0;
	}
#endif
	/* Prove the exact owner allocation fits before touching it. arena_alloc is
	 * 16-byte aligned; charge the worst possible per-allocation padding. */
	required = sizeof(tc_journal_t) + (size_t)TC_MAX_KEYS * sizeof(uint16_t) +
		(size_t)HCU_C3_BITMAP_SLOT_COUNT * sizeof(hcu_bitmap_source_slot) +
		(size_t)HCU_C3_BITMAP_SLOT_COUNT * sizeof(hcu_bitmap_lease) +
		sizeof(halo_ps2_bitmap_request_queue) + HCU_C3_BITMAP_UPLOAD_POOL_BYTES +
		staging_bytes + 7u * 15u;
	if (required > HCU_C3_BITMAP_OWNER_CAP_BYTES) {
		printf("HALO_PS2_FAIL c3-bitmap owner-budget required=%u cap=%u staging=%u\n",
			(unsigned)required, (unsigned)HCU_C3_BITMAP_OWNER_CAP_BYTES, (unsigned)staging_bytes);
		return 0;
	}
	owner_base = s_c3r.level.base + s_c3r.level.cap - HCU_C3_BITMAP_OWNER_BYTES;
	s_c3_bitmap_guard = (uint8_t *)owner_base;
	memset(s_c3_bitmap_guard, 0xa5, HCU_C3_BITMAP_GUARD_BYTES);
	s_c3_bitmap_guard_failed = 0;
	owner_base = (uint8_t *)owner_base + HCU_C3_BITMAP_GUARD_BYTES;
	arena_init(&s_c3_bitmap_owner_arena, "c3_bitmap_owner", owner_base,
		HCU_C3_BITMAP_OWNER_CAP_BYTES);
	journal = arena_alloc(&s_c3_bitmap_owner_arena, sizeof(tc_journal_t), 16);
	readers = arena_alloc(&s_c3_bitmap_owner_arena,
		(size_t)TC_MAX_KEYS * sizeof(uint16_t), 16);
	source_storage = arena_alloc(&s_c3_bitmap_owner_arena,
		HCU_C3_BITMAP_UPLOAD_POOL_BYTES, 16);
	staging = arena_alloc(&s_c3_bitmap_owner_arena, staging_bytes, 16);
	slots = arena_alloc(&s_c3_bitmap_owner_arena,
		(size_t)HCU_C3_BITMAP_SLOT_COUNT * sizeof(hcu_bitmap_source_slot), 16);
	leases = arena_alloc(&s_c3_bitmap_owner_arena,
		(size_t)HCU_C3_BITMAP_SLOT_COUNT * sizeof(hcu_bitmap_lease), 16);
	queue = arena_alloc(&s_c3_bitmap_owner_arena, sizeof(halo_ps2_bitmap_request_queue), 16);
	if (!journal || !readers || !source_storage || !staging || !slots || !leases || !queue) {
		printf("HALO_PS2_FAIL c3-bitmap owner-arena-allocation used=%u cap=%u\n",
			(unsigned)s_c3_bitmap_owner_arena.used, (unsigned)s_c3_bitmap_owner_arena.cap);
		return 0;
	}
	memset(journal, 0, sizeof(tc_journal_t));
	memset(readers, 0, (size_t)TC_MAX_KEYS * sizeof(uint16_t));
	memset(source_storage, 0, HCU_C3_BITMAP_UPLOAD_POOL_BYTES);
	memset(staging, 0, staging_bytes);
	memset(slots, 0, (size_t)HCU_C3_BITMAP_SLOT_COUNT * sizeof(hcu_bitmap_source_slot));
	memset(leases, 0, (size_t)HCU_C3_BITMAP_SLOT_COUNT * sizeof(hcu_bitmap_lease));
	s_c3_bitmap_queue = (halo_ps2_bitmap_request_queue *)queue;
	halo_ps2_bitmap_requests_init(s_c3_bitmap_queue);
	memset(&s_c3_bitmap_dispatch, 0, sizeof(s_c3_bitmap_dispatch));
	s_c3_bitmap_dispatch.bindings = s_c3_bitmap_metadata.bitmap_bindings;
	s_c3_bitmap_dispatch.binding_count = s_c3_bitmap_metadata.bitmap_count;
	s_c3_bitmap_dispatch.profile = &s_map_service.profile_view;
	s_c3_bitmap_dispatch.expected_generation = generation;
	s_c3_bitmap_dispatch.cache = unused_cache;
	s_c3_bitmap_dispatch.journal = (tc_journal_t *)journal;
	s_c3_bitmap_dispatch.cache_readers = (uint16_t *)readers;
	s_c3_bitmap_dispatch.cache_reader_count = TC_MAX_KEYS;
	s_c3_bitmap_dispatch.slots = (hcu_bitmap_source_slot *)slots;
	s_c3_bitmap_dispatch.slot_count = HCU_C3_BITMAP_SLOT_COUNT;
	s_c3_bitmap_dispatch.source_storage = source_storage;
	s_c3_bitmap_dispatch.source_storage_bytes = HCU_C3_BITMAP_UPLOAD_POOL_BYTES;
	s_c3_bitmap_dispatch.slot_stride = staging_bytes;
	s_c3_bitmap_dispatch.staging_buffer = staging;
	s_c3_bitmap_dispatch.staging_buffer_bytes = staging_bytes;
	s_c3_bitmap_dispatch.leases = (hcu_bitmap_lease *)leases;
	s_c3_bitmap_dispatch.lease_capacity = HCU_C3_BITMAP_SLOT_COUNT;
	{
		u32 texture_base, clut_base;
		if (bsp_render_bitmap_texture_bases(&texture_base, &clut_base) != 0 ||
			hcu_bitmap_renderer_init(&s_c3_bitmap_renderer, &s_c3_bitmap_dispatch,
				NULL, (uint16_t *)readers, TC_MAX_KEYS,
				source_storage, HCU_C3_BITMAP_UPLOAD_POOL_BYTES, staging_bytes,
				staging, staging_bytes, (hcu_bitmap_source_slot *)slots,
				HCU_C3_BITMAP_SLOT_COUNT, (hcu_bitmap_lease *)leases,
				HCU_C3_BITMAP_SLOT_COUNT, texture_base, clut_base,
				VIDEO_WIDTH, VIDEO_HEIGHT) != HCU_BITMAP_FRAME_OK ||
			hcu_bitmap_frame_owner_init(&hcu_c3_bitmap_frame_owner) != HCU_BITMAP_FRAME_OK ||
			hcu_bitmap_frame_owner_bind(&hcu_c3_bitmap_frame_owner, s_c3_bitmap_queue,
				&s_c3_bitmap_dispatch, hcu_bitmap_renderer_owner_fence_query,
				&s_c3_bitmap_renderer,
				producer->capabilities & HALO_PS2_BITMAP_FRAME_REQUIRED_PRODUCERS,
				&s_map_service.profile_view, s_c3_bitmap_metadata.bitmap_bindings,
				s_c3_bitmap_metadata.bitmap_count, generation) != HCU_BITMAP_FRAME_OK ||
			hcu_bitmap_renderer_attach_frame(&s_c3_bitmap_renderer,
				&hcu_c3_bitmap_frame_owner) != HCU_BITMAP_FRAME_OK) {
			if (hcu_c3_bitmap_frame_owner.bound)
				(void)hcu_bitmap_frame_owner_unbind(&hcu_c3_bitmap_frame_owner);
			printf("HALO_PS2_FAIL c3-bitmap frame-owner-bind\n");
			return 0;
		}
	}
	/* Keep object residency's original measured high-water span available. The
	 * object loader sees the prefix arena; bitmap resources occupy only the tail. */
#if defined(HCU_C3_OBJECTS)
	s_c3r.level.cap -= HCU_C3_BITMAP_OWNER_BYTES;
#endif
	s_c3_bitmap_bound = 1;
	printf("HALO_PS2_LOCAL c3-bitmap-bound generation=%u bindings=%u producer=0x%x key-base=%u "
		"guard-base=0x%x guard-bytes=%u guard-pattern=0xa5 tail-base=0x%x tail-end=0x%x parent-end=0x%x "
		"owner-used=%u owner-cap=%u static-bytes=%u "
		"source-pool=%u staging=%u slots=%u queue-bytes=%u cache-backup=%u cache-reader-cap=%u object-pool-available=%u\n",
		(unsigned)generation, (unsigned)s_c3_bitmap_metadata.bitmap_count,
		(unsigned)(producer->capabilities & HALO_PS2_BITMAP_FRAME_REQUIRED_PRODUCERS),
		(unsigned)s_c3_bitmap_key_base,
		(unsigned)ee_physical_address(s_c3_bitmap_guard),
		(unsigned)HCU_C3_BITMAP_GUARD_BYTES,
		(unsigned)ee_physical_address(owner_base),
		(unsigned)ee_physical_address((uint8_t *)owner_base + HCU_C3_BITMAP_OWNER_CAP_BYTES),
		(unsigned)ee_physical_address((uint8_t *)s_partition.render_texture_base +
			s_partition.render_texture_bytes),
		(unsigned)s_c3_bitmap_owner_arena.used, (unsigned)s_c3_bitmap_owner_arena.cap,
		(unsigned)(sizeof(hcu_c3_bitmap_frame_owner) + sizeof(s_c3_bitmap_queue) +
			sizeof(s_c3_bitmap_dispatch) + sizeof(s_c3_bitmap_renderer) +
			sizeof(s_c3_bitmap_owner_arena) + sizeof(s_c3_bitmap_metadata) +
			sizeof(s_c3_bitmap_key_base) + sizeof(s_c3_bitmap_guard) +
			sizeof(s_c3_bitmap_guard_failed) + sizeof(s_c3_bitmap_bound)),
		(unsigned)HCU_C3_BITMAP_UPLOAD_POOL_BYTES, (unsigned)staging_bytes,
		(unsigned)HCU_C3_BITMAP_SLOT_COUNT, (unsigned)sizeof(halo_ps2_bitmap_request_queue),
		(unsigned)sizeof(tc_t), (unsigned)TC_MAX_KEYS,
		(unsigned)(s_c3r.level.cap - s_c3r.level.used));
	return 1;
}

int hcu_c3_bitmap_frame_detach(void)
{
	if (!s_c3_bitmap_renderer.bound) return 1;
	if (hcu_c3_bitmap_frame_owner.bound &&
		(hcu_c3_bitmap_frame_owner.in_frame || hcu_c3_bitmap_frame_owner.drain_pending ||
		!hcu_c3_bitmap_frame_owner.queue || hcu_c3_bitmap_frame_owner.queue->open ||
		hcu_c3_bitmap_frame_owner.queue->readers || !hcu_c3_bitmap_frame_owner.dispatch ||
		(!hcu_c3_bitmap_frame_owner.gpu_pending &&
			hcu_c3_bitmap_frame_owner.dispatch->lease_count != 0u)))
		return 0;
	if (hcu_c3_bitmap_frame_owner.bound &&
		hcu_c3_bitmap_frame_owner.gpu_pending &&
		hcu_bitmap_frame_owner_gpu_fence_complete(&hcu_c3_bitmap_frame_owner,
			hcu_c3_bitmap_frame_owner.frame_index) != HCU_BITMAP_FRAME_OK)
		return 0;
	if (s_c3_bitmap_renderer.owner &&
		hcu_bitmap_renderer_detach_frame(&s_c3_bitmap_renderer) != HCU_BITMAP_FRAME_OK)
		return 0;
	if (s_c3_bitmap_guard) {
		unsigned i;
		for (i = 0; i < HCU_C3_BITMAP_GUARD_BYTES; ++i) {
			if (s_c3_bitmap_guard[i] != 0xa5u) {
				if (!s_c3_bitmap_guard_failed)
					printf("HALO_PS2_FAIL c3-bitmap guard-corrupt offset=%u value=0x%x\n",
						(unsigned)i, (unsigned)s_c3_bitmap_guard[i]);
				s_c3_bitmap_guard_failed = 1;
				return 0;
			}
		}
	}
	return 1;
}

static int hcu_c3_bitmap_guard_check(void)
{
	unsigned i;
	if (!s_c3_bitmap_bound || !s_c3_bitmap_guard || s_c3_bitmap_guard_failed)
		return !s_c3_bitmap_guard_failed;
	for (i = 0; i < HCU_C3_BITMAP_GUARD_BYTES; ++i) {
		if (s_c3_bitmap_guard[i] != 0xa5u) {
			if (!s_c3_bitmap_guard_failed)
				printf("HALO_PS2_FAIL c3-bitmap guard-corrupt offset=%u value=0x%x\n",
					(unsigned)i, (unsigned)s_c3_bitmap_guard[i]);
			s_c3_bitmap_guard_failed = 1;
			return 0;
		}
	}
	return 1;
}

int hcu_c3_bitmap_map_released(void)
{
	/* C3:bitmap begin */
	uint32_t released_leases = s_c3_bitmap_dispatch.lease_count;
	uint32_t released_readers = s_c3_bitmap_queue ? s_c3_bitmap_queue->readers : 0u;
	/* C3:bitmap end */
	if (!s_c3_bitmap_bound && !hcu_c3_bitmap_frame_owner.bound &&
		!s_c3_bitmap_renderer.bound) return 1;
	if (!hcu_c3_bitmap_frame_detach()) return 0;
	if (hcu_c3_bitmap_frame_owner.bound &&
		hcu_bitmap_frame_owner_unbind(&hcu_c3_bitmap_frame_owner) != HCU_BITMAP_FRAME_OK)
		return 0;
	/* C3:bitmap begin */
	printf("HALO_PS2_LOCAL c3-bitmap map-released leases=%u readers=%u requests-total=%u begins-total=%u "
		"queue-end-total=%u in-frame=%u\n", (unsigned)released_leases, (unsigned)released_readers,
		(unsigned)hcu_c3_bitmap_frame_owner.stat_requests, (unsigned)hcu_c3_bitmap_frame_owner.stat_begins,
		(unsigned)hcu_c3_bitmap_frame_owner.stat_queue_ends, (unsigned)hcu_c3_bitmap_frame_owner.in_frame);
	memset(s_c3b_last, 0, sizeof(s_c3b_last));
	/* C3:bitmap end */
	memset(&s_c3_bitmap_renderer, 0, sizeof(s_c3_bitmap_renderer));
	memset(&s_c3_bitmap_dispatch, 0, sizeof(s_c3_bitmap_dispatch));
	memset(&s_c3_bitmap_metadata, 0, sizeof(s_c3_bitmap_metadata));
	s_c3_bitmap_queue = NULL;
	s_c3_bitmap_key_base = 0;
	s_c3_bitmap_guard = NULL;
	s_c3_bitmap_bound = 0;
	return 1;
}

void hcu_c3_render_map_loaded(const char *map_name)
{
	uint8_t *base;
	size_t bytes;
	/* C3:pack begin */
	size_t bsps_need, tex_need;
	hcu_render_media_pack pack;
	/* C3:pack end */
	hcu_render_media_span bsps, tex;
	hcu_render_world_span owner;
	int rc, world_touched = 0;
	memset(&s_c3r.media, 0, sizeof s_c3r.media);
	s_c3_bitmap_detach_ok = 1;
	s_c3_render_quiescent = 0;
	s_c3r.active = 0;
	s_c3r.frames = 0;
	hcu_render_frame_reset(&s_c3r.state);
	if (!s_partition_selected || !s_partition.render_texture_base ||
		s_partition.render_texture_bytes < 4096u) {
		printf("HALO_PS2_FAIL c3-render partition render_texture owner unavailable\n");
		return;
	}
	/* C3:pack begin */
	/* render_texture: BSPS at base, TEXS+LMn packed at align64(BSPS end), the level arena at
	 * align64(TEXS+LMn end) with the rest of the owner. Sizes come from the chunk directory
	 * before any read. The owner is 16-byte aligned; the spans need 64. */
	base = (uint8_t *)(((uintptr_t)s_partition.render_texture_base + 63u) & ~(uintptr_t)63u);
	bytes = s_partition.render_texture_bytes - (size_t)(base - (uint8_t *)s_partition.render_texture_base);
	if (hcu_render_media_measure(&s_map_service.profile_view, 0, &bsps_need, &tex_need) != HCU_RENDER_MEDIA_OK ||
		hcu_render_media_pack_plan(bytes, bsps_need, tex_need, &pack) != HCU_RENDER_MEDIA_OK ||
		pack.arena_bytes == 0) {
		printf("HALO_PS2_FAIL c3-render pack-overflow bsps=%u tex=%u owner=%u\n",
			(unsigned)bsps_need, (unsigned)tex_need, (unsigned)bytes);
		return;
	}
	bsps.base = base + pack.bsps_off;  bsps.bytes = pack.bsps_bytes;
	tex.base = base + pack.tex_off;    tex.bytes = pack.tex_bytes;
	rc = hcu_render_media_load(&s_c3r.media, &s_map_service.profile_view, 0, bsps, tex, hcu_c3_flush);
	if (rc != HCU_RENDER_MEDIA_OK) {
		printf("HALO_PS2_FAIL c3-render media-load rc=%d map=%s\n", rc, map_name);
		return;
	}
	arena_init(&s_c3r.level, "c3_render_level", base + pack.arena_off, pack.arena_bytes);
	/* C3:pack end */
	hcu_c3_gs_init();
	if (!s_c3r.gs_ready) goto fail;
	/* Validate exact HCM keys and reserve the cache namespace before publishing
	 * this world to the map service or installing BSP material bindings. */
	if (!hcu_c3_bitmap_profile_prepare()) goto fail;
	owner.base = base;
	owner.bytes = bytes;
	rc = hcu_render_world_bind(&s_c3r.world, &s_map_service, owner, s_c3r.media.bsps,
		s_c3r.media.bsps_bytes, &s_c3r.media.source);
	if (rc != HCU_RENDER_WORLD_OK) {
		printf("HALO_PS2_FAIL c3-render world-bind rc=%d\n", rc);
		bsp_render_clear_world();
		hcu_render_media_clear(&s_c3r.media);
		return;
	}
	world_touched = 1;
	if (bsp_render_set_world(&s_c3r.level, &s_c3r.world.bsp, &s_c3r.media.source)) {
		printf("HALO_PS2_FAIL c3-render set_world\n");
		goto fail;
	}
	if (!hcu_c3_bitmap_map_bind()) {
		(void)hcu_c3_bitmap_map_released();
		bsp_render_clear_world();
		world_touched = 0;
		goto fail;
	}
	/* The map generation is advanced before this hook. Do not report/consume a
	 * stale last-published bank from the preceding map as this map's views. */
	s_c3r.bank_views = 0;
	/* C3:texfence begin */
	if (HCU_C3_TEXFENCE_CAP_PAGES) bsp_render_cache_limit(HCU_C3_TEXFENCE_CAP_PAGES);
	/* C3:texfence end */
	s_c3r.active = 1;
	printf("HALO_PS2_LOCAL c3-render-ready map=%s views=%u frames=%u bsps=%u texs=%u lm=%u texture-count=%u "
		"render-texture-base=0x%x render-texture-bytes=%u media-bsps-used=%u media-tex-used=%u level-arena-used=%u level-arena-cap=%u "
		"pack-bsps-off=%u pack-tex-off=%u pack-arena-off=%u "
		"camera-source=fixed-spawn bank-views=%u world-reader-count=%u\n",
		map_name, (unsigned)HCU_C3_RENDER_VIEWS, (unsigned)HCU_C3_RENDER_FRAMES,
		(unsigned)s_c3r.media.bsps_bytes, (unsigned)s_c3r.media.texs_bytes, (unsigned)s_c3r.media.lm_bytes,
		(unsigned)s_c3r.media.source.texture_count, (unsigned)ee_physical_address(base), (unsigned)bytes,
		(unsigned)s_c3r.media.bsps_span_used, (unsigned)s_c3r.media.tex_span_used,
		(unsigned)s_c3r.level.used, (unsigned)s_c3r.level.cap,
		(unsigned)pack.bsps_off, (unsigned)pack.tex_off, (unsigned)pack.arena_off, (unsigned)s_c3r.bank_views,
		(unsigned)hcu_map_service_reader_count(&s_map_service));
	return;
fail:
	if (world_touched) bsp_render_clear_world();
	(void)hcu_render_world_unbind(&s_c3r.world, &s_map_service);
	hcu_render_media_clear(&s_c3r.media);
}

static void hcu_c3_print_frame(const char *kind)
{
	bsp_render_frame_counters fc;
	const render_stats_t *rs = bsp_render_stats();
	u32 seq = bsp_render_kick_seq();
	bsp_render_frame_counters_get(&fc);
	printf("HALO_PS2_LOCAL c3-frame kind=%s frame=%u views=%u chain-bytes=%u upload-bytes=%u uploads=%u overflow=%u "
		"frames=%u kick-seq=%u fence=%d prev-fence=%d idle-redirects=%u idle-violations=%u emit-failures=%u "
		"batches=%u triangles=%u tex-hits=%u tex-misses=%u tex-failed=%u tex-deferred=%u untextured=%u "
		"clusters-visible=%u/%u pages-free=%u "
		"state-begun=%u state-submitted=%u state-age-adv=%u state-budget-resets=%u state-views=%u\n",
		kind, (unsigned)s_c3r.frames, (unsigned)fc.views_last, (unsigned)fc.chain_bytes_last,
		(unsigned)fc.upload_bytes_last, (unsigned)rs->uploads, (unsigned)fc.overflow_total,
		(unsigned)fc.frames_total, (unsigned)seq, (int)bsp_render_fence_observed(seq),
		seq > 1u ? (int)bsp_render_fence_observed(seq - 1u) : 1,
		(unsigned)bsp_render_idle_redirects(), (unsigned)bsp_render_idle_violations(),
		(unsigned)bsp_render_emit_failures(), (unsigned)rs->batches, (unsigned)rs->triangles,
		(unsigned)rs->tex_hits, (unsigned)rs->tex_misses, (unsigned)rs->tex_failed,
		(unsigned)rs->tex_deferred, (unsigned)rs->untextured_batches,
		(unsigned)rs->clusters_visible, (unsigned)rs->clusters_total, (unsigned)rs->pages_free,
		(unsigned)s_c3r.state.frames_begun, (unsigned)s_c3r.state.frames_submitted,
		(unsigned)s_c3r.state.cache_age_advances, (unsigned)s_c3r.state.upload_budget_resets,
		(unsigned)s_c3r.state.views_rendered);
}

/* C3:views begin */
/* C3.5 per-view camera, HUD and first-person state. One pinned snapshot-bank slot serves the whole frame
 * (begin before the views, end after them). A view takes its camera from the snapshot when that view is
 * active, its camera is valid and the map generation matches; otherwise it keeps the fixed camera and
 * reports camera=fixed. HUD: a crosshair always, health/shield/ammo when the snapshot says HUD_VISIBLE,
 * drawn with the overlay text batch inside the view's viewport. First person: the snapshot's node count is
 * reported; the object path (hcu_render_objects.h) is not present, so no first-person geometry is drawn.
 * HCU_C3_VIEWS_FP_PLACEHOLDER=1 adds an "FP n" marker only (not counted as drawn). */
#include "stream/hcu_render_views.h"
#if defined(HCU_C3_FRAME_SNAPSHOT)
#include "stream/hcu_snapshot_bank.h"
#endif
#ifndef HCU_C3_VIEWS_FP_PLACEHOLDER
#define HCU_C3_VIEWS_FP_PLACEHOLDER 0
#endif
#define HCU_C3_VIEWS_PRINT_PERIOD 30u
#define HCU_C3_VIEWS_RGB_HUD 0xE0E0E0u
#define HCU_C3_VIEWS_RGB_CROSS 0x80FF80u
#define HCU_C3_VIEWS_RGB_FP 0xFFC040u

typedef struct {
	int pinned;
	hcu_snapshot_reader reader;
	const halo_ps2_frame_snapshot *snap;
	hcu_views_stats stats;
	hcu_view_camera_source source[HCU_RENDER_VIEWS_MAX];
	uint32_t hud_lines[HCU_RENDER_VIEWS_MAX];
	uint32_t fp_nodes[HCU_RENDER_VIEWS_MAX];
	uint32_t fp_draws[HCU_RENDER_VIEWS_MAX];
	int fp_placeholder[HCU_RENDER_VIEWS_MAX];
	float fov_h_deg[HCU_RENDER_VIEWS_MAX];
	float pitch_deg[HCU_RENDER_VIEWS_MAX];
	uint32_t active[HCU_RENDER_VIEWS_MAX];
	float pos[HCU_RENDER_VIEWS_MAX][3];
	bsp_viewport vp[HCU_RENDER_VIEWS_MAX];
	text_batch_t text[HCU_RENDER_VIEWS_MAX];
} hcu_c3_views_state;

static hcu_c3_views_state s_c3v;

static int hcu_c3_views_hund(float v)
{
	return (int)(v >= 0.0f ? v * 100.0f + 0.5f : v * 100.0f - 0.5f);
}

static void hcu_c3_views_begin(void)
{
	if (s_c3r.frames == 0u) memset(&s_c3v.stats, 0, sizeof s_c3v.stats);
	s_c3v.stats.frames++;
	s_c3v.snap = NULL;
	s_c3v.pinned = 0;
#if defined(HCU_C3_FRAME_SNAPSHOT)
	s_c3v.snap = hcu_snapshot_bank_begin_read(&s_c3v.reader);
	s_c3v.pinned = s_c3v.snap != NULL;
#endif
}

/* text_batch_emit places a glyph at (VIDEO_WIDTH/2 - screen_w/2 + x) and the view's XYOFFSET
 * (2048 - vp.x - vp.w/2) is subtracted, so a glyph at x would land at x + vp.x + vp.w/2 - VIDEO_WIDTH/2.
 * Pre-compensating by VIDEO_WIDTH/2 - vp.w/2 puts local (xl, yl) at buffer pixel (vp.x + xl, vp.y + yl). */
static void hcu_c3_views_text(text_batch_t *tb, const bsp_viewport *vp, int xl, int yl, uint32_t rgb,
	const char *str)
{
	text_batch_print(tb, xl + VIDEO_WIDTH / 2 - vp->w / 2, yl + VIDEO_HEIGHT / 2 - vp->h / 2, rgb, str);
}

/* Sets up view v: its camera (snapshot or fixed), its overlay batch and its bookkeeping. Returns the overlay
 * for bsp_render_view. */
static const text_batch_t *hcu_c3_views_camera(unsigned v, camera_t *cam, const bsp_viewport *vp)
{
	hcu_view_camera hc;
	const halo_ps2_frame_view *view = NULL;
	text_batch_t *tb = &s_c3v.text[v];
	int from_snapshot = 0;
	char lines[HCU_RENDER_VIEWS_HUD_LINES][HCU_RENDER_VIEWS_HUD_CHARS];
	unsigned i, n = 0;
	uint32_t first_person_palettes = 0;
	int gap, cx, cy;

	s_c3v.vp[v] = *vp;
	s_c3v.hud_lines[v] = 0;
	s_c3v.fp_nodes[v] = 0;
	s_c3v.fp_draws[v] = 0;
	s_c3v.fp_placeholder[v] = 0;
#if defined(HCU_C3_FRAME_SNAPSHOT)
	if (s_c3v.snap && v < s_c3v.snap->view_count) {
		view = &s_c3v.snap->views[v];
		if (!(view->flags & HALO_PS2_FRAME_VIEW_ACTIVE)) {
			s_c3v.stats.refused_views++;
			view = NULL;
		} else if (hcu_views_accept_generation(&s_c3v.stats, s_c3v.snap->map_generation) &&
			hcu_views_camera_from_snapshot(view->camera.position, view->camera.forward, view->camera.up,
				view->camera.vertical_field_of_view, (float)vp->w / (float)vp->h,
				view->camera.z_near, view->camera.z_far, &hc)) {
			from_snapshot = 1;
		} else {
			s_c3v.stats.refused_views++;
		}
	}
#endif
#if defined(HCU_C3_FRAME_SNAPSHOT)
	/* Unit position beside the camera position, for the spawn-cam versus conversion question. */
	if ((s_c3r.frames == 0u || (s_c3r.frames % 30u) == 0u) && s_c3v.snap && view &&
		view->unit_object < s_c3v.snap->object_count) {
		const halo_ps2_snapshot_matrix4x3 *uw = &s_c3v.snap->objects[view->unit_object].world;
		printf("HALO_PS2_LOCAL c3-view-camera frame=%u view=%u source=%s unit-object=%u "
			"unit-pos=%.2f,%.2f,%.2f camera-pos=%.2f,%.2f,%.2f camera-fwd=%.3f,%.3f,%.3f pitch-x100=%d\n",
			(unsigned)s_c3r.frames, v, from_snapshot ? "snapshot" : "fixed", (unsigned)view->unit_object,
			uw->position[0], uw->position[1], uw->position[2],
			view->camera.position[0], view->camera.position[1], view->camera.position[2],
			view->camera.forward[0], view->camera.forward[1], view->camera.forward[2],
			(int)((from_snapshot ? hc.pitch : 0.0f) * 100.0f));
	}
#endif
	camera_init(cam);
	if (from_snapshot) {
		cam->pos[0] = hc.pos[0]; cam->pos[1] = hc.pos[1]; cam->pos[2] = hc.pos[2];
		cam->yaw = hc.yaw; cam->pitch = hc.pitch; cam->hfov = hc.hfov;
		cam->near_z = hc.near_z; cam->far_z = hc.far_z;
		s_c3v.source[v] = HCU_VIEW_CAMERA_SNAPSHOT;
		s_c3v.stats.snapshot_views++;
	} else {
		hcu_c3_make_camera(cam, v);
		s_c3v.source[v] = HCU_VIEW_CAMERA_FIXED;
		s_c3v.stats.fixed_views++;
	}
	s_c3v.pos[v][0] = cam->pos[0]; s_c3v.pos[v][1] = cam->pos[1]; s_c3v.pos[v][2] = cam->pos[2];
	s_c3v.fov_h_deg[v] = cam->hfov / HCU_C3_DEG;
	s_c3v.pitch_deg[v] = cam->pitch / HCU_C3_DEG;
	s_c3v.active[v] = view ? 1u : 0u;

	/* HUD: viewport-local pixels (bsp_render_view sets the view's XYOFFSET to its origin, so absolute
	 * positions would be shifted by the origin a second time). Kept inside the rectangle. */
	text_batch_clear(tb);
	if (view) {
		n = hcu_views_hud_lines(view->hud_values, view->hud_flags, lines);
		/* The view's XYOFFSET is its own origin, so overlay text is in viewport-local pixels. */
		for (i = 0; i < n; ++i)
			hcu_c3_views_text(tb, vp, 4, 4 + (int)i * 10, HCU_C3_VIEWS_RGB_HUD, lines[i]);
		s_c3v.stats.hud_lines += n;
		s_c3v.hud_lines[v] = n;
		first_person_palettes = (uint32_t)view->first_person_weapon_palette_count +
			(uint32_t)view->first_person_hands_palette_count;
		s_c3v.fp_nodes[v] = first_person_palettes;
		s_c3v.stats.fp_nodes_seen += first_person_palettes;
	}
	/* Crosshair: two dashes either side of the centre, spread from the snapshot (4 px when there is none). */
	gap = view ? hcu_views_crosshair_gap(view->hud_values) : hcu_views_crosshair_gap(NULL);
	cx = vp->w / 2;
	cy = vp->h / 2;
	hcu_c3_views_text(tb, vp, cx - gap - 6, cy - 4, HCU_C3_VIEWS_RGB_CROSS, "-");
	hcu_c3_views_text(tb, vp, cx + gap, cy - 4, HCU_C3_VIEWS_RGB_CROSS, "-");
	if (!view && s_c3v.snap && v < s_c3v.snap->view_count)
		hcu_c3_views_text(tb, vp, 4, 4, HCU_C3_VIEWS_RGB_FP, "RESPAWNING");
	s_c3v.stats.crosshairs++;
#if HCU_C3_VIEWS_FP_PLACEHOLDER
	if (view && (view->flags & HALO_PS2_FRAME_VIEW_FIRST_PERSON) && first_person_palettes) {
		char fp[HCU_RENDER_VIEWS_HUD_CHARS];
		hcu_views_fp_placeholder_text(first_person_palettes, fp);
		hcu_c3_views_text(tb, vp, 4, vp->h - 12, HCU_C3_VIEWS_RGB_FP, fp);
		s_c3v.fp_placeholder[v] = 1;
	}
#endif
	return tb;
}

static void hcu_c3_views_end(unsigned view_count)
{
	unsigned v;
	int print = s_c3r.frames == 0u || (s_c3r.frames % HCU_C3_VIEWS_PRINT_PERIOD) == 0u;
	hcu_snapshot_bank_stats bs;
	uint32_t seq = s_c3v.snap ? s_c3v.snap->sequence : 0u;

	if (s_c3v.pinned) {
#if defined(HCU_C3_FRAME_SNAPSHOT)
		hcu_snapshot_bank_end_read(&s_c3v.reader);
#endif
		s_c3v.pinned = 0;
	}
	if (!print || view_count == 0u) return;
	hcu_snapshot_bank_get_stats(&bs);
	for (v = 0; v < view_count && v < HCU_RENDER_VIEWS_MAX; ++v) {
		printf("HALO c3-views frame=%u view=%u camera=%s pos_x100=%d,%d,%d fov_h_x100=%d "
			"pitch_x100=%d active=%u viewport=%d,%d,%d,%d hud=%u fp-nodes=%u fp-drawn=%u fp-placeholder=%d "
			"bank-views=%u bank-seq=%u pins=%u\n",
			(unsigned)s_c3r.frames, v,
			s_c3v.source[v] == HCU_VIEW_CAMERA_SNAPSHOT ? "snapshot" : "fixed",
			hcu_c3_views_hund(s_c3v.pos[v][0]), hcu_c3_views_hund(s_c3v.pos[v][1]),
			hcu_c3_views_hund(s_c3v.pos[v][2]), hcu_c3_views_hund(s_c3v.fov_h_deg[v]), hcu_c3_views_hund(s_c3v.pitch_deg[v]), (unsigned)s_c3v.active[v],
			s_c3v.vp[v].x, s_c3v.vp[v].y, s_c3v.vp[v].w, s_c3v.vp[v].h,
			(unsigned)s_c3v.hud_lines[v], (unsigned)s_c3v.fp_nodes[v], (unsigned)s_c3v.fp_draws[v], s_c3v.fp_placeholder[v],
			(unsigned)(seq ? s_c3v.snap->view_count : 0u), (unsigned)seq, (unsigned)bs.read_pins_active);
	}
}
/* C3:views end */

/* C3:objects begin */
/* C3.objects: draws the published object snapshot (players, bots, vehicles, weapons, one effect) through the
 * halo-ps2 object pass. The pass is installed inside bsp_render_view, so the objects draw after the BSP pass
 * of the same view. Views call begin before and end after their bsp_render_view; frame begin/end pin the
 * snapshot bank slot until the frame's kick has completed. Without HCU_C3_OBJECTS every hook is a no-op. */
#if defined(HCU_C3_OBJECTS)
#include "stream/hcu_render_objects.h"
#include <hcu_c3_objects_table.h>
#if defined(HCU_C3_OBJECTS_SYNTHETIC)
#define HCU_C3_OBJECTS_SOURCE "synthetic"
#else
#define HCU_C3_OBJECTS_SOURCE "bank"
#endif
static int s_c3o_loaded, s_c3o_installed, s_c3o_released;
static hcu_render_objects_load_info s_c3o_info;

static void hcu_c3_objects_frame_begin(void)
{
	halo_ps2_snapshot_camera cams[HALO_PS2_FRAME_MAX_VIEWS];
	uint32_t views = 0;
#if defined(HCU_C3_OBJECTS_SYNTHETIC)
	uint32_t v;
#endif
	if (s_c3r.frames == 0u) {
		s_c3o_loaded = 0;
		s_c3o_installed = 0;
		s_c3o_released = 0;
		if (hcu_render_objects_load(&s_map_service.profile_view, &s_c3r.level, hcu_c3_objects_table,
			HCU_C3_OBJECTS_TABLE_COUNT, &s_c3o_info) == 0 && s_c3o_info.entries)
			s_c3o_loaded = 1;
		printf("HALO_PS2_LOCAL c3-objects-load entries=%u refused=%u pool-bytes=%u arena-before=%u arena-after=%u\n",
			(unsigned)s_c3o_info.entries, (unsigned)s_c3o_info.models_refused, (unsigned)s_c3o_info.pool_bytes,
			(unsigned)s_c3o_info.arena_before, (unsigned)s_c3o_info.arena_after);
	}
#if defined(HCU_C3_OBJECTS_SYNTHETIC)
	if (s_c3o_loaded) {
		views = (uint32_t)HCU_C3_RENDER_VIEWS;
		for (v = 0; v < views; ++v) {
			camera_t c;
			float right[3], up[3], fwd[3];
			hcu_c3_make_camera(&c, v);
			camera_basis(&c, right, up, fwd);
			memcpy(cams[v].position, c.pos, sizeof cams[v].position);
			memcpy(cams[v].forward, fwd, sizeof cams[v].forward);
			memcpy(cams[v].up, up, sizeof cams[v].up);
			cams[v].vertical_field_of_view = c.hfov;
			cams[v].z_near = c.near_z;
			cams[v].z_far = c.far_z;
		}
	}
#endif
	(void)hcu_render_objects_frame_begin(s_c3r.frames, views, cams);
	if (s_c3o_loaded && !s_c3o_installed) {
		hcu_render_objects_install();
		s_c3o_installed = 1;
	}
}

static void hcu_c3_objects_view_begin(uint32_t view)
{
	hcu_render_objects_view_begin(view);
}

static void hcu_c3_objects_view_end(uint32_t view)
{
	hcu_render_objects_view_stats st;
	hcu_render_objects_view_end(view, &st);
	if (view < HCU_RENDER_VIEWS_MAX)
		s_c3v.fp_draws[view] = st.first_person_draws;
	if (s_c3r.frames == 0u || (s_c3r.frames % 30u) == 0u)
		printf("HALO_PS2_LOCAL c3-objects frame=%u view=%u source=%s drawn=%u triangles=%u skinned-nodes=%u "
			"model-hits=%u model-misses=%u tex-hits=%u tex-misses=%u failures=%u parity=%u "
			"fp-drawn=%u fp-hits=%u fp-misses=%u fp-generation=%u fp-weapon=%u fp-hands=%u "
			"fp-weapon-slot=%u fp-hands-slot=%u\n",
			(unsigned)s_c3r.frames, (unsigned)view, HCU_C3_OBJECTS_SOURCE, (unsigned)st.drawn,
			(unsigned)st.triangles, (unsigned)st.skinned_nodes, (unsigned)st.model_hits,
			(unsigned)st.model_misses, (unsigned)st.texture_hits, (unsigned)st.texture_misses,
			(unsigned)st.failures, (unsigned)st.parity_records,
			(unsigned)st.first_person_draws, (unsigned)st.first_person_model_hits,
			(unsigned)st.first_person_model_misses, (unsigned)st.first_person_map_generation,
			(unsigned)st.first_person_weapon_resource_id, (unsigned)st.first_person_hands_resource_id,
			(unsigned)st.first_person_weapon_resource_slot, (unsigned)st.first_person_hands_resource_slot);
	/* C3:content begin */
	if (s_c3r.frames == 0u || (s_c3r.frames % 30u) == 0u)
		printf("HALO_PS2_LOCAL c3-fp frame=%u view=%u fp-weapon-draws=%u fp-hands-draws=%u fp-drawn=%u "
			"parts=%u effects-selected=%u effects-refused=%u\n",
			(unsigned)s_c3r.frames, (unsigned)view, (unsigned)st.first_person_weapon_draws,
			(unsigned)st.first_person_hands_draws, (unsigned)st.first_person_draws,
			(unsigned)st.parts_logged, (unsigned)st.effects_selected, (unsigned)st.effects_refused);
	if (s_c3r.frames == 0u || (s_c3r.frames % 30u) == 0u)
		printf("HALO_PS2_LOCAL c3-fx frame=%u view=%u fx-drawn=%u fx-skipped-space=%u fx-textured=%u fx-flat=%u "
			"effects-selected=%u effects-refused=%u\n",
			(unsigned)s_c3r.frames, (unsigned)view, (unsigned)st.fx_drawn, (unsigned)st.fx_skipped_space,
			(unsigned)st.fx_textured, (unsigned)st.fx_flat, (unsigned)st.effects_selected,
			(unsigned)st.effects_refused);
	/* C3:content end */
}

static void hcu_c3_objects_frame_end(void)
{
	hcu_render_objects_frame_end();
	/* C3:content begin */
	if (s_c3r.frames == 0u) {
		hcu_render_parity_summary ps;
		if (hcu_render_objects_parity_summary(&ps) == 0)
			printf("HALO_PS2_LOCAL c3-parity frame=0 records=%u dropped=%u object=%u vehicle=%u weapon=%u "
				"effect=%u materials-known=%u hash=%08x\n", (unsigned)ps.records, (unsigned)ps.dropped,
				(unsigned)ps.per_kind[HCU_RENDER_PARITY_OBJECT], (unsigned)ps.per_kind[HCU_RENDER_PARITY_VEHICLE],
				(unsigned)ps.per_kind[HCU_RENDER_PARITY_WEAPON], (unsigned)ps.per_kind[HCU_RENDER_PARITY_EFFECT],
				(unsigned)ps.materials_known, (unsigned)ps.hash);
	}
	if (s_c3r.frames == 0u || (s_c3r.frames % 30u) == 0u) {
		hcu_render_objects_counters t;
		hcu_render_objects_totals(&t);
		printf("HALO_PS2_LOCAL c3-pose frame=%u pose-changes=%u pose-static=%u fp-weapon-draws=%u "
			"fp-hands-draws=%u effects-selected=%u\n", (unsigned)s_c3r.frames, (unsigned)t.pose_changes,
			(unsigned)t.pose_static, (unsigned)t.first_person_weapon_draws,
			(unsigned)t.first_person_hands_draws, (unsigned)t.effects_selected);
	}
	/* C3:content end */
	if (s_c3r.frames == 0u || (s_c3r.frames % 30u) == 0u) {
		hcu_render_objects_residency rs;
		hcu_render_objects_residency_stats(&rs);
		printf("HALO_PS2_LOCAL c3-objects-residency frame=%u resident=%u loads=%u hits=%u misses=%u evictions=%u "
			"pool-refusals=%u fence-blocked=%u entry-refusals=%u keys-refused=%u pool-bytes=%u pool-used=%u pool-peak=%u "
			"evict-refused-pinned=%u\n",
			(unsigned)s_c3r.frames, (unsigned)rs.resident, (unsigned)rs.loads, (unsigned)rs.hits, (unsigned)rs.misses,
			(unsigned)rs.evictions, (unsigned)rs.pool_refusals, (unsigned)rs.fence_blocked, (unsigned)rs.entry_refusals,
			(unsigned)rs.keys_refused, (unsigned)rs.pool_bytes, (unsigned)rs.pool_used, (unsigned)rs.pool_used_peak,
			(unsigned)rs.evict_refused_pinned);
	}
}

static void hcu_c3_objects_final(void)
{
	hcu_render_objects_counters t;
	if (s_c3o_released) return;
	hcu_render_objects_release();
	s_c3o_released = 1;
	hcu_render_objects_totals(&t);
	printf("HALO_PS2_LOCAL c3-objects-final frames=%u drawn=%u triangles=%u skinned-nodes=%u model-hits=%u "
		"model-misses=%u tex-hits=%u tex-misses=%u failures=%u deduped=%u pins=%u unpins=%u pin-refusals=%u "
		"parity-dropped=%u model-bytes=%u texture-bytes=%u fp-drawn=%u fp-hits=%u fp-misses=%u\n", (unsigned)s_c3r.frames, (unsigned)t.objects_drawn,
		(unsigned)t.triangles, (unsigned)t.skinned_nodes, (unsigned)t.model_hits, (unsigned)t.model_misses,
		(unsigned)t.texture_hits, (unsigned)t.texture_misses, (unsigned)t.failures, (unsigned)t.deduped,
		(unsigned)t.pins, (unsigned)t.unpins, (unsigned)t.pin_refusals, (unsigned)t.parity_dropped,
		(unsigned)s_c3o_info.model_bytes, (unsigned)s_c3o_info.texture_bytes,
		(unsigned)t.first_person_draws, (unsigned)t.first_person_model_hits,
		(unsigned)t.first_person_model_misses);
}
#else
#define hcu_c3_objects_frame_begin() ((void)0)
#define hcu_c3_objects_view_begin(v) ((void)(v))
#define hcu_c3_objects_view_end(v) ((void)(v))
#define hcu_c3_objects_frame_end() ((void)0)
#define hcu_c3_objects_final() ((void)0)
#endif
/* C3:objects end */

/* C3:bitmap begin */
/* C3.9: per-tick deltas of the CE bitmap frame callbacks (begin, set_view, queue end). Counters only
 * advance inside CE render_frame, so a tick line reports every CE frame that ran since the previous tick. */
static void hcu_c3_bitmap_print_tick(int tick)
{
	hcu_bitmap_frame_owner *o = &hcu_c3_bitmap_frame_owner;
	uint32_t cur[6];
	uint32_t failed_delta;
	if (!o->bound) return;
	cur[0] = o->stat_begin_calls; cur[1] = o->stat_begins; cur[2] = o->stat_set_views;
	cur[3] = o->stat_queue_ends; cur[4] = o->stat_ends; cur[5] = o->stat_requests;
	failed_delta = o->stat_end_failures;
	printf("HALO_PS2_LOCAL c3-bitmap tick=%d begin-calls=%u begin=%u set-view=%u requests=%u queue-end=%u end=%u "
		"end-failed-total=%u in-frame=%u drain-pending=%u gpu-pending=%u leases=%u last-status=%d "
		"bitmap-frames-dropped=%u drop-cause=0x%x ce-status=%d ce-failures=%u\n",
		tick,
		(unsigned)(cur[0] - s_c3b_last[0]), (unsigned)(cur[1] - s_c3b_last[1]),
		(unsigned)(cur[2] - s_c3b_last[2]), (unsigned)(cur[5] - s_c3b_last[5]),
		(unsigned)(cur[3] - s_c3b_last[3]), (unsigned)(cur[4] - s_c3b_last[4]),
		(unsigned)failed_delta, (unsigned)o->in_frame, (unsigned)o->drain_pending,
		(unsigned)o->gpu_pending, (unsigned)(o->dispatch ? o->dispatch->lease_count : 0u),
		(int)o->last_status, (unsigned)o->stat_drops, (unsigned)o->last_drop_cause,
		(int)halo_ps2_bitmap_frame_last_status(), (unsigned)halo_ps2_bitmap_frame_failure_count());
	memcpy(s_c3b_last, cur, sizeof(s_c3b_last));
}
/* C3:bitmap end */

/* C3:dma begin */
#if defined(HCU_C3_OBJECTS)
#include "render/obj_render.h"
#endif
/* C3.10 DMA proof: the owner and chain layout at bind, then one c3-dma line per frame. The release events
 * (chain reuse, objects pin, bitmap lease) are counted by the renderer and the objects module at the release point;
 * this block only reads them. */
#if defined(HCU_C3)
static uint32_t s_c3d_owner_phys, s_c3d_owner_cap, s_c3d_storage_phys;
static uint32_t s_c3d_chain_kicks[2], s_c3d_last_kick[2];
static void hcu_c3_dma_note_owner(void *storage, const arena_t *owner)
{
	bsp_render_chain_probe p;
	int i;
	s_c3d_owner_phys = (uint32_t)((uintptr_t)owner->base & 0x0FFFFFFFu);
	s_c3d_owner_cap = (uint32_t)owner->cap;
	s_c3d_storage_phys = (uint32_t)((uintptr_t)storage & 0x0FFFFFFFu);
	bsp_render_chain_probe_get(&p);
	printf("HALO_PS2_LOCAL c3-dma-owner owner-base=0x%x owner-cap=%u owner-used=%u storage-base=0x%x storage-bytes=%u "
		"chains=4 geom0=0x%x/%u geom1=0x%x/%u up0=0x%x/%u up1=0x%x/%u sum=%u\n",
		(unsigned)s_c3d_owner_phys, (unsigned)s_c3d_owner_cap, (unsigned)owner->used,
		(unsigned)s_c3d_storage_phys, (unsigned)bsp_render_dma_storage_required(),
		(unsigned)p.base[0], (unsigned)p.bytes[0], (unsigned)p.base[1], (unsigned)p.bytes[1],
		(unsigned)p.base[2], (unsigned)p.bytes[2], (unsigned)p.base[3], (unsigned)p.bytes[3],
		(unsigned)(p.bytes[0] + p.bytes[1] + p.bytes[2] + p.bytes[3]));
	for (i = 0; i < 2; i++) s_c3d_last_kick[i] = 0;
}
static void hcu_c3_dma_frame(uint32_t frame)
{
	bsp_render_chain_probe p;
	bsp_render_source_counters src;
	uint32_t codes[17], rel_total = 0, before_total = 0, refusals = 0;
	int i;
	int32_t fence[2];
#if defined(HCU_C3_OBJECTS)
	hcu_render_objects_counters t;
	hcu_render_objects_totals(&t);
	refusals = obj_render_space_refusals();
#endif
	bsp_render_chain_probe_get(&p);
	bsp_render_emit_code_counts(codes);
	bsp_render_source_get(&src);
	for (i = 0; i < BSP_SRC_KINDS; i++) {
		rel_total += src.releases[i];
		before_total += src.before_fence[i];
	}
	for (i = 0; i < 2; i++) {
		if (p.kick[i] != 0 && p.kick[i] != s_c3d_last_kick[i]) s_c3d_chain_kicks[i]++;
		s_c3d_last_kick[i] = p.kick[i];
		fence[i] = bsp_render_fence_observed(p.kick[i]);
	}
	printf("HALO_PS2_LOCAL c3-dma frame=%u kick-seq=%u completed=%u inflight=%u "
		"c0-kick=%u c0-fence=%d c0-kicks=%u c0-emits=%u c0-busy-emits=%u c0-used-qw=%u "
		"c1-kick=%u c1-fence=%d c1-kicks=%u c1-emits=%u c1-busy-emits=%u c1-used-qw=%u "
		"src-gen=%u src-released=%u released-before-fence=%u "
		"src-rel-chain=%u/%u src-rel-pin=%u/%u src-rel-bitmap=%u/%u "
		"overflow-refusals=%u emit-status=%d emit-codes-neg=%u,%u,%u,%u,%u,%u,%u,%u emit-codes-pos=%u,%u,%u,%u,%u,%u,%u,%u,%u\n",
		(unsigned)frame, (unsigned)p.kick_seq, (unsigned)p.completed_seq, (unsigned)p.inflight,
		(unsigned)p.kick[0], (int)fence[0], (unsigned)s_c3d_chain_kicks[0], (unsigned)p.emits[0],
		(unsigned)p.busy_emits[0], (unsigned)p.used_qw[0],
		(unsigned)p.kick[1], (int)fence[1], (unsigned)s_c3d_chain_kicks[1], (unsigned)p.emits[1],
		(unsigned)p.busy_emits[1], (unsigned)p.used_qw[1],
		(unsigned)p.kick_seq, (unsigned)rel_total, (unsigned)before_total,
		(unsigned)src.releases[BSP_SRC_CHAIN], (unsigned)src.before_fence[BSP_SRC_CHAIN],
		(unsigned)src.releases[BSP_SRC_OBJECT_PIN], (unsigned)src.before_fence[BSP_SRC_OBJECT_PIN],
		(unsigned)src.releases[BSP_SRC_BITMAP_LEASE], (unsigned)src.before_fence[BSP_SRC_BITMAP_LEASE],
		(unsigned)refusals, (int)bsp_render_emit_status(),
		(unsigned)codes[0], (unsigned)codes[1], (unsigned)codes[2], (unsigned)codes[3],
		(unsigned)codes[4], (unsigned)codes[5], (unsigned)codes[6], (unsigned)codes[7],
		(unsigned)codes[9], (unsigned)codes[10], (unsigned)codes[11], (unsigned)codes[12],
		(unsigned)codes[13], (unsigned)codes[14], (unsigned)codes[15], (unsigned)codes[16], (unsigned)codes[8]);
}
#else
#define hcu_c3_dma_note_owner(s, o) ((void)(s), (void)(o))
#define hcu_c3_dma_frame(f) ((void)(f))
#endif
/* C3:dma end */

void hcu_c3_render_tick(int tick)
{
	hcu_render_layout layout;
	bsp_viewport vp;
	camera_t cam;
	unsigned v;
	(void)tick;
	/* C3:bitmap begin */
	hcu_c3_bitmap_print_tick(tick);
	/* C3:bitmap end */
	/* C3:sound begin */
#if defined(HCU_C3_FRAME_SNAPSHOT)
	hcu_c3_sound_tick();
#endif
	/* C3:sound end */
	if (!s_c3r.active || s_c3r.frames >= (uint32_t)HCU_C3_RENDER_FRAMES) return;
	if (hcu_render_layout_compute((uint32_t)HCU_C3_RENDER_VIEWS, VIDEO_WIDTH, VIDEO_HEIGHT, &layout) != 0 ||
		hcu_render_frame_begin(&s_c3r.state, (uint32_t)HCU_C3_RENDER_VIEWS) != 0 ||
		bsp_render_frame_begin(s_c3r.frames) != 0) {
		printf("HALO_PS2_FAIL c3-render frame-begin frame=%u\n", (unsigned)s_c3r.frames);
		s_c3r.active = 0;
		return;
	}
	/* C3:views begin */
	hcu_c3_views_begin();
	/* C3:views end */
	/* C3:objects begin */
	hcu_c3_objects_frame_begin();
	/* C3:objects end */
	for (v = 0; v < layout.view_count; ++v) {
		memset(&vp, 0, sizeof vp);
		vp.x = layout.views[v].x; vp.y = layout.views[v].y;
		vp.w = layout.views[v].w; vp.h = layout.views[v].h;
		/* C3:objects begin */
		hcu_c3_objects_view_begin(v);
		/* C3:objects end */
		/* C3:views begin */
		if (bsp_render_view(&cam, hcu_c3_views_camera(v, &cam, &vp), &vp) != 0) {
			hcu_c3_views_end(0u);
		/* C3:views end */
			printf("HALO_PS2_FAIL c3-render view=%u frame=%u\n", v, (unsigned)s_c3r.frames);
			s_c3r.active = 0;
			return;
		}
		/* C3:objects begin */
		hcu_c3_objects_view_end(v);
		/* C3:objects end */
	}
	/* C3:views begin */
	hcu_c3_views_end(layout.view_count);
	/* C3:views end */
	if (layout.clear.w > 0) {
		memset(&vp, 0, sizeof vp);
		vp.x = layout.clear.x; vp.y = layout.clear.y; vp.w = layout.clear.w; vp.h = layout.clear.h;
		vp.clear = 1; vp.clear_rgb[0] = 16; vp.clear_rgb[1] = 16; vp.clear_rgb[2] = 24;
		(void)bsp_render_view(NULL, NULL, &vp);
	}
	/* Same order as the viewer's frame: build, wait for the previous kick's GS FINISH, present, kick. */
	bsp_render_wait_gpu();
	video_wait_gpu();
	video_present(&s_c3r.video);
	if (bsp_render_frame_end(&s_c3r.video) != 0 || hcu_render_frame_end(&s_c3r.state) != 0) {
		printf("HALO_PS2_FAIL c3-render frame-end frame=%u\n", (unsigned)s_c3r.frames);
		s_c3r.active = 0;
		return;
	}
	if (!hcu_c3_bitmap_guard_check()) {
		s_c3r.active = 0;
		printf("HALO_PS2_FAIL c3-bitmap frame-guard frame=%u\n", (unsigned)s_c3r.frames);
		return;
	}
	/* C3:objects begin */
	hcu_c3_objects_frame_end();
	/* C3:objects end */
	s_c3r.frames++;
	/* C3:dma begin */
	hcu_c3_dma_frame(s_c3r.frames);
	/* C3:dma end */
	if (s_c3r.frames == 1u || (s_c3r.frames % 30u) == 0u) {
		hcu_c3_print_frame("periodic");
		/* C3:texfence begin */
		hcu_c3_print_texfence("periodic", s_c3r.frames);
		/* C3:texfence end */
	}
	if (s_c3r.frames == (uint32_t)HCU_C3_RENDER_FRAMES) {
		unsigned i;
		bsp_render_wait_gpu();
		video_wait_gpu();
		/* C3:objects begin */
		hcu_c3_objects_final();
		/* C3:objects end */
		hcu_c3_print_frame("final");
		/* C3:texfence begin */
		hcu_c3_print_texfence("final", s_c3r.frames);
		/* C3:texfence end */
		/* Hold the last presented frame on screen so the host can capture it. */
		video_present(&s_c3r.video);
		printf("HALO_PS2_LOCAL c3-render-held views=%u frames=%u\n", (unsigned)HCU_C3_RENDER_VIEWS,
			(unsigned)s_c3r.frames);
		for (i = 0; i < (unsigned)HCU_C3_RENDER_HOLD_VSYNCS; ++i) graph_wait_vsync();
	}
}

/* Order: drain GS/DMA, stop the renderer reading the world, unbind the world reader, clear the media. The
 * CE dispose and owner release that follow wait on the reader table. */
void hcu_c3_render_map_release(void)
{
	bsp_render_frame_counters fc;
	int world_rc = -99;
	uint32_t readers_before, readers_after;
	if (!s_c3r.media.loaded && !s_c3r.world.bound) {
		/* No BSP media is installed, but bitmap work can still have used the
		 * parent frame hooks. Retire the DMA/fence boundary before detaching them. */
		bsp_render_wait_gpu();
		dma_wait_fast();
		if (!hcu_renderer_drained(NULL) || !hcu_c3_bitmap_frame_detach()) {
			s_c3_bitmap_detach_ok = 0;
			s_c3_render_quiescent = 0;
			printf("HALO_PS2_LOCAL c3-render-teardown order=already-empty result=blocked readers=%u\n",
				(unsigned)hcu_map_service_reader_count(&s_map_service));
			return;
		}
		s_c3_bitmap_detach_ok = 1;
		s_c3r.active = 0;
		s_c3_render_quiescent = hcu_map_service_reader_count(&s_map_service) == 0;
		printf("HALO_PS2_LOCAL c3-render-teardown order=already-empty dma-wait=1 readers=%u quiescent=%d\n",
			(unsigned)hcu_map_service_reader_count(&s_map_service), s_c3_render_quiescent);
		return;
	}
	/* No video_wait_gpu() here: graph_wait_vsync() (the hold and presents) clears the GS FINISH flag, so
	 * waiting for it would spin forever. bsp_render_wait_gpu() is bounded and its observations stick. */
	bsp_render_wait_gpu();
	dma_wait_fast();
	if (!hcu_renderer_drained(NULL)) {
		s_c3_bitmap_detach_ok = 0;
		s_c3_render_quiescent = 0;
		printf("HALO_PS2_LOCAL c3-render-teardown order=drain result=blocked readers=%u kick-seq=%u fence=%d\n",
			(unsigned)hcu_map_service_reader_count(&s_map_service),
			(unsigned)bsp_render_kick_seq(),
			(int)bsp_render_fence_observed(bsp_render_kick_seq()));
		return;
	}
	hcu_c3_prime_finish();   /* the hold's vsyncs consumed the last FINISH; clear_world waits for one */
	if (!hcu_c3_bitmap_frame_detach()) {
		s_c3_bitmap_detach_ok = 0;
		s_c3_render_quiescent = 0;
		printf("HALO_PS2_LOCAL c3-render-teardown order=frame-detach result=blocked readers=%u\n",
			(unsigned)hcu_map_service_reader_count(&s_map_service));
		return;
	}
	s_c3_bitmap_detach_ok = 1;
	/* Object models/textures and their profile-residency pins are separate from
	 * the BSP world reader. Release them only after the outstanding kick drains. */
	hcu_c3_objects_final();
	bsp_render_clear_world();
	readers_before = hcu_map_service_reader_count(&s_map_service);
	if (s_c3r.world.bound)
		world_rc = hcu_render_world_unbind(&s_c3r.world, &s_map_service);
	readers_after = hcu_map_service_reader_count(&s_map_service);
	hcu_render_media_clear(&s_c3r.media);
	s_c3r.active = 0;
	s_c3_render_quiescent = (world_rc == 0 || world_rc == -99) && readers_after == 0;
	bsp_render_frame_counters_get(&fc);
	printf("HALO_PS2_LOCAL c3-render-teardown order=drain,frame-detach,clear-world,unbind-reader,media-clear world-unbind=%d "
		"readers-before=%u readers-after=%u frames=%u overflow=%u media-loaded=%d\n",
		world_rc, (unsigned)readers_before, (unsigned)readers_after, (unsigned)fc.frames_total,
		(unsigned)fc.overflow_total, s_c3r.media.loaded);
}
#endif
/* C3:render end */

/* The map service calls this after the candidate is fully validated and before
 * CE disposes its live scenario. A false result vetoes CE teardown. */
static int hcu_renderer_quiesce(void *ctx)
{
	int ok;
	(void)ctx;
#ifdef HCU_C3_RENDER_BUILT
	hcu_c3_render_map_release();
	ok = s_c3_render_quiescent &&
		s_c3_bitmap_detach_ok &&
		hcu_map_service_reader_count(&s_map_service) == 0 &&
		hcu_renderer_drained(NULL) && !halo_ps2_bitmap_frame_is_active() &&
		hcu_bitmap_renderer_attachment_count() == 0;
#elif defined(HALO_HCU_HEADLESS_RUNTIME_GUEST)
	ok = hcu_renderer_never_started(NULL) &&
		hcu_map_service_reader_count(&s_map_service) == 0;
#else
	ok = hcu_renderer_drained(NULL) &&
		hcu_map_service_reader_count(&s_map_service) == 0;
#endif
#ifdef HCU_C3_RENDER_BUILT
	{
		uint32_t kick = bsp_render_kick_seq();
		int fence = kick == 0u ? 1 : bsp_render_fence_observed(kick);
		printf("HALO_PS2_LOCAL c3-render-quiesce result=%d readers=%u kick-seq=%u fence=%d "
			"frame-active=%d bitmap-attachments=%u\n", ok,
			(unsigned)hcu_map_service_reader_count(&s_map_service), (unsigned)kick,
			fence, (int)halo_ps2_bitmap_frame_is_active(),
			(unsigned)hcu_bitmap_renderer_attachment_count());
	}
#endif
	return ok;
}

/* C3:snapshot begin */
#if defined(HCU_C3_FRAME_SNAPSHOT)
/* Per-tick report of the CE frame snapshot the guest publishes through
 * main_game_render -> render_frame (submodules/halo-ce-universal port/ps2
 * ps2_c3_publish_frame_snapshot). Each map load starts a new map generation. */
static uint32_t s_c3s_map_generation;
static uint32_t s_c3s_ticks;

void hcu_c3_snapshot_map_loaded(const char *map_name)
{
	(void)map_name;
	s_c3s_map_generation++;
	s_c3s_ticks = 0;
	hcu_snapshot_bank_set_map_generation(s_c3s_map_generation);
#ifdef HCU_C3_RENDER_BUILT
	/* Lock view acceptance to the new generation before any frame can run. The
	 * previous map's latest bank remains readable as bytes, but is refused until
	 * CE publishes the first snapshot for this map. */
	memset(&s_c3v.stats, 0, sizeof(s_c3v.stats));
	s_c3v.stats.have_generation = 1;
	s_c3v.stats.generation = s_c3s_map_generation;
#endif
}

void hcu_c3_snapshot_tick(int tick)
{
	hcu_snapshot_reader reader;
	const halo_ps2_frame_snapshot *s;
	hcu_snapshot_bank_stats st;
	unsigned biped = 0, weapon = 0, vehicle = 0, other = 0, active = 0, i;
	unsigned palette = 0, attachments = 0, resources = 0, views = 0, object_count = 0;
	unsigned sequence = 0, view_refs = 0;
	unsigned effects = 0, decals = 0, fx_dropped = 0;
	int slot;

	(void)tick;
	s_c3s_ticks++;
	if (s_c3s_ticks % 30u)
		return;
	s = hcu_snapshot_bank_begin_read(&reader);
	if (!s) {
		hcu_snapshot_bank_get_stats(&st);
		printf("HALO_PS2_LOCAL c3-snapshot frame=%u map-gen=%u views=0 objects=0 published=0 "
			"effects=0 decals=0 fx-dropped=0 "
			"refused-writes=%u commit-rejects=%u\n", (unsigned)s_c3s_ticks,
			(unsigned)s_c3s_map_generation, (unsigned)st.write_refusals, (unsigned)st.commit_rejects);
		return;
	}
	for (i = 0; i < s->object_count; ++i) {
		switch (s->objects[i].type) {
		case 0: biped++; break;      /* _object_type_biped */
		case 1: vehicle++; break;    /* _object_type_vehicle */
		case 2: weapon++; break;     /* _object_type_weapon */
		default: other++; break;
		}
	}
	for (i = 0; i < s->view_count; ++i)
		if (s->views[i].flags & HALO_PS2_FRAME_VIEW_ACTIVE)
			active++;
	views = s->view_count;
	object_count = s->object_count;
	palette = s->palette_count;
	attachments = s->attachment_count;
	resources = s->resource_count;
	view_refs = s->view_ref_count;
	effects = s->effect_count;
	decals = s->decal_count;
	fx_dropped = s->fx_dropped;
	sequence = s->sequence;
	slot = hcu_snapshot_bank_published_slot();
	hcu_snapshot_bank_get_stats(&st);   /* pins are read while this reader holds one */
	hcu_snapshot_bank_end_read(&reader);
	printf("HALO_PS2_LOCAL c3-snapshot frame=%u map-gen=%u seq=%u views=%u active-views=%u "
		"objects=%u biped=%u weapon=%u vehicle=%u other=%u palette=%u attachments=%u "
		"effects=%u decals=%u fx-dropped=%u "
		"resources=%u view-refs=%u dedupe-hits=%u bank-slot=%d reader-pins=%u pins-taken=%u "
		"refused-writes=%u commit-rejects=%u commits=%u\n",
		(unsigned)s_c3s_ticks, (unsigned)s->map_generation, sequence, views, active,
		object_count, biped, weapon, vehicle, other, palette, attachments,
		effects, decals, fx_dropped, resources, view_refs,
		(unsigned)st.object_dedupe_hits, slot, (unsigned)st.read_pins_active,
		(unsigned)st.read_pins_taken, (unsigned)st.write_refusals, (unsigned)st.commit_rejects,
		(unsigned)st.commits);
}
#endif
/* C3:snapshot end */

static int hcu_guard_intact(const uint8_t *guard, uint8_t pattern)
{
	size_t i;
	if (!guard) return 0;
	for (i = 0; i < MEM_LAYOUT_V2_GUARD_BYTES; ++i)
		if (guard[i] != pattern) return 0;
	return 1;
}

static int report_and_validate_regions(const mem_layout_v2_t *layout,
	uintptr_t boot_start, size_t boot_bytes)
{
	uintptr_t starts[MEM_LAYOUT_V2_REGION_COUNT];
	uintptr_t ends[MEM_LAYOUT_V2_REGION_COUNT];
	uintptr_t boot_end;
	int i, j;

	if (boot_bytes > UINTPTR_MAX - boot_start)
		return -1;
	boot_end = boot_start + boot_bytes;
	for (i = 0; i < MEM_LAYOUT_V2_REGION_COUNT; i++) {
		const arena_t *region = &layout->regions[i];
		uintptr_t base = ee_physical_address(region->base);

		if (!region->base || region->cap == 0 || region->used > region->cap ||
			region->high > region->cap || region->cap > UINTPTR_MAX - base)
			return -1;
		starts[i] = base;
		ends[i] = base + region->cap;
		if (starts[i] < boot_start || ends[i] > boot_end ||
			ends[i] > HCU_RESERVE_START)
			return -1;
		for (j = 0; j < i; j++) {
			if (starts[i] < ends[j] && starts[j] < ends[i])
				return -1;
		}
		printf("HALO_PS2_LOCAL arena name=%s base=0x%x cap=%u used=%u high=%u "
			"alloc_failures=%u resets=%u releases=%u invalid_releases=%u\n",
			s_region_names[i], (unsigned)starts[i], (unsigned)region->cap,
			(unsigned)region->used, (unsigned)region->high,
			(unsigned)region->failed_allocations,
			(unsigned)region->reset_count,
			(unsigned)region->release_count,
			(unsigned)region->invalid_releases);
	}
	return 0;
}

#ifdef HALO_PS2_STEP8_MP_CAPACITY_DIAGNOSTIC
/* Stock MP corpus candidate: the max aligned CTAG and Sidewinder BSP spans
 * need 6,470,832 bytes. Borrow 179,376 bytes from texture_cache; total owner
 * storage is unchanged and the end canary remains in the original regions. */
static int hcu_step8_mp_candidate_recarve(mem_layout_v2_t *layout)
{
	arena_t *bsp = mem_layout_v2_get(layout, MEM_LAYOUT_V2_CURRENT_BSP);
	arena_t *texture = mem_layout_v2_get(layout, MEM_LAYOUT_V2_TEXTURE_CACHE);
	const size_t map_bytes = 6470832u;
	const size_t texture_bytes = 4014928u;
	uint8_t *combined_end;
	if (!bsp || !texture || !bsp->base || !texture->base ||
		bsp->cap != 6291456u || texture->cap != 4194304u ||
		((uintptr_t)bsp->base & 15u) ||
		texture->base != layout->guards[2] + MEM_LAYOUT_V2_GUARD_BYTES ||
		map_bytes + texture_bytes != 10485760u)
		return -1;
	combined_end = bsp->base + map_bytes + texture_bytes;
	if (combined_end > texture->base + texture->cap - MEM_LAYOUT_V2_GUARD_BYTES ||
		((uintptr_t)(bsp->base + map_bytes) & 15u))
		return -1;
	bsp->cap = map_bytes;
	texture->base = bsp->base + map_bytes;
	texture->cap = texture_bytes;
	/* The original post-BSP canary sat inside the candidate BSP span. Move it
	 * to the candidate combined owner's end and retain the old pointers for
	 * other guarded regions. Duplicate pointer checks are intentional. */
	layout->guards[2] = combined_end;
	layout->guards[3] = combined_end;
	memset(combined_end, layout->guard_pattern, MEM_LAYOUT_V2_GUARD_BYTES);
	printf("HALO_PS2_LOCAL step8-mp-candidate-layout tag=4477120 bsp=1993712 map=6470832 texture=4014928 total=10485760 base=0x%x texture-base=0x%x end=0x%x\n",
		(unsigned)ee_physical_address(bsp->base),
		(unsigned)ee_physical_address(texture->base),
		(unsigned)ee_physical_address(combined_end));
	return 0;
}

int halo_ps2_step8_mp_candidate_guards_intact(void)
{
	return s_step8_candidate_layout &&
		mem_layout_v2_guards_intact(s_step8_candidate_layout);
}
#endif

static int report_kernel_stack(void)
{
	ee_thread_status_t status;
	int thread_id = GetThreadId();
	uintptr_t stack_start, stack_end;
	if (thread_id < 0 || ReferThreadStatus(thread_id, &status) <= 0 ||
		!status.stack || status.stack_size <= 0)
		return -1;
	stack_start = ee_physical_address(status.stack);
	if ((uintptr_t)status.stack_size > UINTPTR_MAX - stack_start)
		return -1;
	stack_end = stack_start + (uintptr_t)status.stack_size;
	/* The reserve is [HCU_RESERVE_START, 0x01f80000); the top 512 KiB
	 * plus low 1 MiB are the 1.5 MiB kernel/system reservation. */
	if (stack_start < HCU_RESERVE_END || stack_end > 0x02000000u)
		return -1;
	printf("HALO_PS2_LOCAL kernel-stack base=0x%x size=%u end=0x%x\n",
		(unsigned)stack_start, (unsigned)status.stack_size,
		(unsigned)stack_end);
	printf("HALO_PS2_LOCAL kernel-reservation low=0x0 low_bytes=1048576 "
		"high=0x1f80000 high_bytes=524288 reserve=0x%x "
		"reserve_bytes=%u\n", (unsigned)HCU_RESERVE_START,
		(unsigned)HCU_RESERVE_BYTES);
	return 0;
}

int main(int argc, char **argv)
{
	void *backing;
	arena_t boot;
	arena_t render_section_scratch;
	arena_t map_owner_storage;
	arena_t *frame_scratch;
	arena_t *dma_commands;
	arena_t *streaming;
	void *snapshot_storage = NULL;
	uint8_t *snapshot_guard = NULL;
	void *renderer_dma_storage = NULL;
	void *renderer_workspace = NULL;
	uint8_t *renderer_workspace_guard = NULL;
	mem_layout_v2_t layout;
	size_t resident_static_bytes, backing_bytes, snapshot_bytes;
	size_t renderer_workspace_bytes;
	int snapshot_bound = 0;
	int result;
#ifdef HALO_PS2_M2_ANIMATION_TRACE
	arena_t *resident_gameplay;
	struct ps2_animation_trace_event *animation_trace_storage;
	struct ps2_animation_trace_context *animation_context_storage;
#endif
	(void)argc;
	(void)argv;

	setbuf(stdout, NULL);
	printf("HALO_PS2_LOCAL machine entry\n");
	if (!ps2_abi_check()) {
		printf("HALO_PS2_FAIL CE ABI runtime smoke failed\n");
		return 1;
	}
	/* CRT clears this NOBITS span before main. Charge it to resident_gameplay
	 * so the one boot allocation covers only the rest of the v2 layout. */
	if ((uintptr_t)&_end < (uintptr_t)&_fbss) {
		printf("[err] invalid ELF NOBITS bounds\n");
		return 1;
	}
	resident_static_bytes = (size_t)((uintptr_t)&_end - (uintptr_t)&_fbss);
	if (resident_static_bytes > 6815744u) {
		printf("[err] ELF NOBITS exceeds resident_gameplay\n");
		return 1;
	}
	backing_bytes = MEM_LAYOUT_V2_BYTES - resident_static_bytes;
	/* Alignment slack is required because arena_init receives an
	 * allocator-owned address. The link/runtime ledger includes this slack. */
	/* Bypass HCU's post-boot malloc arena wrapper for the single machine-owned
	 * backing allocation. The linked HCU profile supplies --wrap=malloc/free. */
	backing = __real_malloc((unsigned long)(backing_bytes + MEM_LAYOUT_V2_GUARDED_SLACK));
	if (!backing)
	{
		printf("[err] cannot allocate budget-v2 backing\n");
		return 1;
	}
	/* EE RAM below 1 MiB and above 31.5 MiB belongs to system/kernel;
	 * [HCU_RESERVE_START, 0x01f80000) is the untouched reserve. The full boot allocation,
	 * including allocator metadata between _end and the returned pointer,
	 * must finish before that reserve. */
	if (ee_physical_address(&_ftext) < HCU_LOW_KERNEL_BYTES ||
		ee_physical_address(&_fbss) > HCU_FILE_BACKED_END ||
		ee_physical_address(backing) < ee_physical_address(&_end) ||
		ee_physical_address(backing) > HCU_RESERVE_START ||
		backing_bytes + MEM_LAYOUT_V2_GUARDED_SLACK >
			HCU_RESERVE_START - ee_physical_address(backing))
	{
		printf("[err] ELF/boot backing exceeds EE fixed budget\n");
		__real_free(backing);
		return 1;
	}
	if (report_kernel_stack() != 0) {
		printf("[err] cannot prove kernel stack is inside system_kernel reservation\n");
		__real_free(backing);
		return 1;
	}
	arena_init(&boot, "boot", backing,
		backing_bytes + MEM_LAYOUT_V2_GUARDED_SLACK);
	if (mem_layout_v2_init_charged_guarded(&layout, &boot,
		resident_static_bytes, 0xA5u) != 0
#ifdef HALO_PS2_STEP8_MP_CAPACITY_DIAGNOSTIC
		|| hcu_step8_mp_candidate_recarve(&layout) != 0
#endif
		)
	{
		printf("[err] cannot initialize budget-v2 layout\n");
		__real_free(backing);
		return 1;
	}
	/* Partition selection happens here, before physical_memory_allocate(); a
	 * row that is not in the versioned table never reaches CE. */
	if (hcu_select_and_bind_partition(&layout) != 0)
	{
		printf("[err] cannot bind CE fixed memory regions\n");
		physical_memory_free();
		__real_free(backing);
		return 1;
	}
#ifdef HALO_PS2_M2_ANIMATION_TRACE
	/* Opt-in diagnostic storage is charged to resident_gameplay only after CE's
	 * game-state and claims allocations. Never borrow frame scratch, streaming,
	 * dynamic simulation, or the uncommitted reserve. */
	resident_gameplay = mem_layout_v2_get(&layout,
		MEM_LAYOUT_V2_RESIDENT_GAMEPLAY);
	animation_trace_storage = resident_gameplay ? arena_alloc(
		resident_gameplay,
		PS2_ANIMATION_TRACE_CAPACITY * sizeof(*animation_trace_storage), 16) : NULL;
	animation_context_storage = resident_gameplay ? arena_alloc(
		resident_gameplay,
		PS2_ANIMATION_TRACE_CAPACITY * sizeof(*animation_context_storage), 16) : NULL;
	if (!animation_trace_storage || !animation_context_storage ||
		!ps2_animation_trace_bind(animation_trace_storage,
			PS2_ANIMATION_TRACE_CAPACITY) ||
		!ps2_animation_trace_bind_contexts(animation_context_storage,
			PS2_ANIMATION_TRACE_CAPACITY)) {
		printf("[err] cannot bind budgeted M2 animation trace buffer\n");
		physical_memory_free();
		__real_free(backing);
		return 1;
	}
	printf("HALO_PS2_LOCAL animation-trace-bound events=0x%x contexts=0x%x count=%u event-bytes=%u context-bytes=%u resident-used=%u\n",
		(unsigned)ee_physical_address(animation_trace_storage),
		(unsigned)ee_physical_address(animation_context_storage),
		(unsigned)PS2_ANIMATION_TRACE_CAPACITY,
		(unsigned)(PS2_ANIMATION_TRACE_CAPACITY * sizeof(*animation_trace_storage)),
		(unsigned)(PS2_ANIMATION_TRACE_CAPACITY * sizeof(*animation_context_storage)),
		(unsigned)resident_gameplay->used);
#endif
	if (report_and_validate_regions(&layout,
		ee_physical_address(backing),
		backing_bytes + MEM_LAYOUT_V2_GUARDED_SLACK) != 0 ||
		!mem_layout_v2_guards_intact(&layout)) {
		printf("[err] budget-v2 intervals or boundary canaries invalid\n");
		physical_memory_free();
		__real_free(backing);
		return 1;
	}
	printf("HALO_PS2_LOCAL memory-layout bss=%u backing=%u guard_slack=%u\n",
		(unsigned)resident_static_bytes, (unsigned)backing_bytes,
		(unsigned)MEM_LAYOUT_V2_GUARDED_SLACK);
	printf("HALO_PS2_LOCAL memory-physical elf_end=0x%x boot=0x%x boot_end=0x%x reserve=0x%x allocator_gap=%u\n",
		(unsigned)ee_physical_address(&_end),
		(unsigned)ee_physical_address(backing),
		(unsigned)(ee_physical_address(backing) + backing_bytes +
			MEM_LAYOUT_V2_GUARDED_SLACK),
		(unsigned)HCU_RESERVE_START,
		(unsigned)(ee_physical_address(backing) -
			ee_physical_address(&_end)));
	physical_memory_allocate();
	if (!physical_memory_ready())
	{
		printf("[err] required CE fixed memory regions are unavailable\n");
		physical_memory_free();
		__real_free(backing);
		return 1;
	}
	if (!mem_layout_v2_guards_intact(&layout) ||
		(s_partition_selected &&
			!hcu_memory_partition_guards_intact(&layout, &s_partition))) {
		printf("[err] budget-v2 boundary canary corrupted during CE bind\n");
		physical_memory_free();
		__real_free(backing);
		return 1;
	}
	printf("HALO_PS2_LOCAL memory-ready canaries=%u\n",
		(unsigned)(MEM_LAYOUT_V2_REGION_COUNT + 1));
	if (!pad_init())
	{
		printf("[err] PS2 pad service initialization failed\n");
		physical_memory_free();
		__real_free(backing);
		return 1;
	}
	printf("HALO_PS2_LOCAL pad-ready\n");
	/* pad_init starts SIF RPC. Reuse OPL's IOP modules when present; never
	 * reset the IOP because that can destroy the launcher's storage driver. */
	printf("HALO_PS2_LOCAL storage-boot-begin\n");
	if (hcu_storage_boot_init() != 0)
	{
		physical_memory_free();
		__real_free(backing);
		return 1;
	}
	printf("HALO_PS2_LOCAL storage-boot-ready\n");
	frame_scratch = mem_layout_v2_get(&layout, MEM_LAYOUT_V2_FRAME_SCRATCH);
	dma_commands = mem_layout_v2_get(&layout, MEM_LAYOUT_V2_DMA_COMMANDS);
	streaming = mem_layout_v2_get(&layout, MEM_LAYOUT_V2_STREAMING);
	/* C3:snapshot begin */
#if defined(HCU_C3_FRAME_SNAPSHOT)
	/* Opt-in v2 bank replaces the v1 double bank in frame_scratch; the two
	 * do not fit together in the 393,216-byte owner. */
	snapshot_bytes = hcu_snapshot_bank_storage_required();
#else
	snapshot_bytes = hcu_render_snapshot_storage_required();
#endif
	/* C3:snapshot end */
	renderer_workspace_bytes = bsp_render_workspace_required();
	if (!frame_scratch || !dma_commands || !streaming ||
		dma_commands->cap != bsp_render_dma_storage_required() ||
		streaming->cap < 1572864u)
	{
		printf("[err] cannot bind bounded CE snapshot/renderer storage\n");
		physical_memory_free();
		__real_free(backing);
		return 1;
	}
	snapshot_storage = arena_alloc(frame_scratch, snapshot_bytes, 16);
	snapshot_guard = arena_alloc(frame_scratch,
		MEM_LAYOUT_V2_GUARD_BYTES, 1);
	renderer_workspace = arena_alloc(frame_scratch,
		renderer_workspace_bytes, 64);
	renderer_workspace_guard = arena_alloc(frame_scratch,
		MEM_LAYOUT_V2_GUARD_BYTES, 1);
	renderer_dma_storage = arena_alloc(dma_commands,
		bsp_render_dma_storage_required(), 64);
	if (!snapshot_storage || !snapshot_guard || !renderer_workspace ||
		!renderer_workspace_guard || !renderer_dma_storage)
	{
		printf("[err] cannot reserve exact snapshot, renderer workspace, and DMA spans\n");
		physical_memory_free();
		__real_free(backing);
		return 1;
	}
	memset(snapshot_guard, 0xC7, MEM_LAYOUT_V2_GUARD_BYTES);
	memset(renderer_workspace_guard, 0xC7, MEM_LAYOUT_V2_GUARD_BYTES);
	/* C3:snapshot begin */
#if defined(HCU_C3_FRAME_SNAPSHOT)
	if (hcu_snapshot_bank_bind(snapshot_storage, snapshot_bytes) != 0)
#else
	if (hcu_render_snapshot_bind(snapshot_storage, snapshot_bytes) != 0)
#endif
	/* C3:snapshot end */
	{
		printf("[err] cannot bind bounded CE render snapshot storage\n");
		physical_memory_free();
		__real_free(backing);
		return 1;
	}
	snapshot_bound = 1;
	if (bsp_render_bind_storage(renderer_dma_storage,
		bsp_render_dma_storage_required(), renderer_workspace,
		renderer_workspace_bytes) != 0)
	{
		printf("[err] cannot bind bounded bsp_render DMA chains/workspace\n");
		hcu_render_snapshot_unbind();
		physical_memory_free();
		__real_free(backing);
		return 1;
	}
	/* C3:dma begin */
#ifdef HCU_C3_RENDER_BUILT
	hcu_c3_dma_note_owner(renderer_dma_storage, dma_commands);
#endif
	/* C3:dma end */
	/* Keep simulation snapshot storage in frame_scratch. Map owners and decode
	 * scratch receive disjoint bounded slices of streaming so section loads do
	 * not consume render-time frame scratch. */
	arena_init(&map_owner_storage, "streaming_map_owner",
		streaming->base, 1048576u);
	arena_init(&render_section_scratch, "streaming_section_scratch",
		streaming->base + 1048576u, 524288u);
	printf("HALO_PS2_LOCAL render-storage-bound snapshot-cap=%u renderer-workspace-cap=%u renderer-dma-cap=%u geometry-chain-qw=%u upload-chain-qw=%u frame-parent-used=%u frame-parent-high=%u streaming-map-cap=%u section-scratch-base=0x%x section-scratch-cap=%u\n",
		(unsigned)snapshot_bytes,
		(unsigned)renderer_workspace_bytes,
		(unsigned)bsp_render_dma_storage_required(),
		(unsigned)BSP_RENDER_GEOMETRY_CHAIN_QW,
		(unsigned)BSP_RENDER_UPLOAD_CHAIN_QW,
		(unsigned)frame_scratch->used,
		(unsigned)frame_scratch->high,
		(unsigned)map_owner_storage.cap,
		(unsigned)ee_physical_address(render_section_scratch.base),
		(unsigned)render_section_scratch.cap);
	/* C3:snapshot begin */
#if defined(HCU_C3_FRAME_SNAPSHOT)
	/* C3.3 layout: the three banks, the renderer workspace and both guards all live in frame_scratch.
	 * The pose tracker is static BSS (hcu_render_objects.c s_poses) and is not part of this owner. */
	_Static_assert(HCU_SNAPSHOT_BANK_BYTES + MEM_LAYOUT_V2_GUARD_BYTES + 63u + BSP_RENDER_WORKSPACE_BYTES +
		MEM_LAYOUT_V2_GUARD_BYTES <= HCU_C3_FRAME_SCRATCH_BYTES,
		"C3.3: snapshot banks plus renderer workspace exceed frame_scratch");
	_Static_assert(HCU_C3_FRAME_SCRATCH_BYTES == 393216u, "C3.3: frame_scratch owner size changed");
	printf("HALO_PS2_LOCAL c3-scratch-layout cap=%u used=%u high=%u banks=%u bank-stride=%u bank-bytes=%u "
		"workspace=%u guards=%u worst-case=%u free-worst=%u snapshot-size=%u\n",
		(unsigned)frame_scratch->cap, (unsigned)frame_scratch->used, (unsigned)frame_scratch->high,
		(unsigned)HCU_SNAPSHOT_BANK_SLOTS, (unsigned)HCU_SNAPSHOT_BANK_STRIDE,
		(unsigned)HCU_SNAPSHOT_BANK_BYTES, (unsigned)BSP_RENDER_WORKSPACE_BYTES,
		(unsigned)(2u * MEM_LAYOUT_V2_GUARD_BYTES),
		(unsigned)(HCU_SNAPSHOT_BANK_BYTES + MEM_LAYOUT_V2_GUARD_BYTES + 63u + BSP_RENDER_WORKSPACE_BYTES +
			MEM_LAYOUT_V2_GUARD_BYTES),
		(unsigned)(HCU_C3_FRAME_SCRATCH_BYTES - (HCU_SNAPSHOT_BANK_BYTES + MEM_LAYOUT_V2_GUARD_BYTES + 63u +
			BSP_RENDER_WORKSPACE_BYTES + MEM_LAYOUT_V2_GUARD_BYTES)),
		(unsigned)sizeof(halo_ps2_frame_snapshot));
#endif
	/* C3:snapshot end */
	/* Telemetry is registered before the first map service request, so the first
	 * map load and every later one see the same owner registry. */
	hcu_bind_owner_telemetry(&layout, frame_scratch, dma_commands, streaming);
	hcu_report_owner_telemetry("bound");
	if (hcu_map_service_init_with_arenas(&s_map_service, &layout,
		HALO_HCU_ASSET_ROOT, &map_owner_storage, &render_section_scratch) != 0)
	{
		printf("[err] cannot initialize HCU map service at %s\n",
			HALO_HCU_ASSET_ROOT);
		hcu_render_snapshot_unbind();
		physical_memory_free();
		__real_free(backing);
		return 1;
	}
	/* A qualified row must register its runtime or boot stops here. */
	if (hcu_register_selected_runtime(&s_map_service, &map_owner_storage,
		&render_section_scratch) != 1) {
		hcu_render_snapshot_unbind();
		physical_memory_free();
		__real_free(backing);
		return 1;
	}
#ifdef HCU_C2_SUCCESSOR_BUILT
	s_c2s_owner_arena = &map_owner_storage;
	if (hcu_register_successor_runtime(&s_map_service, &map_owner_storage,
		&render_section_scratch) != 1) {
		hcu_render_snapshot_unbind();
		physical_memory_free();
		__real_free(backing);
		return 1;
	}
#endif
	/* Per-cycle telemetry at each map boundary. NULL hook costs nothing. */
	(void)hcu_map_service_set_boundary_hook(&s_map_service,
		hcu_map_boundary_report, NULL);
	/* C3:world begin */
#if defined(HCU_C3)
	{
		/* No profile package carries a BSPS section, so no world can be bound yet.
		 * The renderer keeps its flat/empty state until the producer exists. */
		const uint8_t *c3_bsps = NULL;
		size_t c3_bsps_bytes = 0;
		if (hcu_render_world_profile_bsps(&s_map_service, &c3_bsps, &c3_bsps_bytes) != 0)
			printf("[c3] world source: no BSPS section in the profile package\n");
	}
#endif
	/* C3:world end */
	/* C3:replace begin */
#if defined(HCU_C3_FRAME_SNAPSHOT)
	hcu_sound_requests_init(&s_c3_sound_queue);
	halo_ps2_sound_request_bind_sink(hcu_c3_sound_request_sink, NULL);
	halo_ps2_sound_playback_bind_sink(hcu_c3_sound_playback_sink, NULL);
#endif
	/* C3:replace end */
	/* Legacy bootstrap map storage is released only after the renderer fence
	 * has retired. Without this gate the unload path would free live GS/DMA
	 * readers. */
	if (!s_partition_selected &&
		!hcu_map_service_set_legacy_renderer_drained(&s_map_service,
			hcu_renderer_drained, NULL)) {
		printf("[err] cannot bind renderer drain gate to HCU map service\n");
		hcu_render_snapshot_unbind();
		physical_memory_free();
		__real_free(backing);
		return 1;
	}
	{
		unsigned long asset_bytes = 0;
		const char *failed_stage = NULL;
		if (!hcu_file_bridge_probe("D:\\maps\\ui.map", &asset_bytes,
			&failed_stage)) {
			printf("[err] asset root %s failed read-only maps/ui.map probe at %s\n",
				HALO_HCU_ASSET_ROOT,
				failed_stage ? failed_stage : "unknown");
			if (!hcu_map_service_shutdown(&s_map_service)) return 1;
			hcu_render_snapshot_unbind();
			physical_memory_free();
			__real_free(backing);
			return 1;
		}
		printf("HALO_PS2_LOCAL asset-probe-ready root=%s bytes=%u\n",
			HALO_HCU_ASSET_ROOT, (unsigned)asset_bytes);
	}
	printf("HALO_PS2_LOCAL memory-and-input-ready (cache=%u bytes; bootstrap only)\n",
		(unsigned)HALO_HCU_TAG_CACHE_BYTES);
#ifdef HALO_PS2_M3_RENDER_CLEAR_TEST
	{
		const arena_t *dma_commands = mem_layout_v2_get(&layout,
			MEM_LAYOUT_V2_DMA_COMMANDS);
		if (!dma_commands || hcu_m3_render_clear_test(renderer_dma_storage,
			BSP_RENDER_GEOMETRY_CHAIN_QW * 16u) != 0) {
			printf("HALO_PS2_FAIL m3 renderer clear diagnostic could not initialize/present\n");
			if (!hcu_map_service_shutdown(&s_map_service)) return 1;
			if (snapshot_bound)
				hcu_render_snapshot_unbind();
			physical_memory_free();
			__real_free(backing);
			return 1;
		}
	}
#endif
#ifdef HALO_PS2_STEP8_MP_CAPACITY_DIAGNOSTIC
	s_step8_candidate_layout = &layout;
#endif
	hcu_report_cache_owners("before-shell");
	hcu_report_owner_telemetry("before-shell");
#if defined(HALO_HCU_HEADLESS_RUNTIME_GUEST) && defined(HALO_HCU_PROFILE_IMAGE_HEADER)
	strncpy(hcu_c2_runtime_map_name, HCU_C2_IMAGE_MAP, sizeof(hcu_c2_runtime_map_name) - 1);
	strncpy(hcu_c2_runtime_scenario_path, HCU_C2_IMAGE_SCENARIO,
		sizeof(hcu_c2_runtime_scenario_path) - 1);
#ifdef HCU_C2_SUCCESSOR_BUILT
	strncpy(hcu_c2_successor_map_name, HCU_C2_SUCC_MAP,
		sizeof(hcu_c2_successor_map_name) - 1);
	strncpy(hcu_c2_successor_scenario_path, HCU_C2_SUCC_SCENARIO,
		sizeof(hcu_c2_successor_scenario_path) - 1);
#endif
#endif
	result = halo_shell_main();
	hcu_report_cache_owners("after-shell");
	hcu_report_owner_telemetry("after-shell");
	if (!hcu_guard_intact(snapshot_guard, 0xC7u) ||
		!hcu_guard_intact(renderer_workspace_guard, 0xC7u)) {
		printf("HALO_PS2_FAIL renderer owner canary corrupted\n");
		result = 1;
	}
	printf("HALO_PS2_LOCAL render-owner name=snapshot cap=%u guard=%s\n",
		(unsigned)snapshot_bytes,
		hcu_guard_intact(snapshot_guard, 0xC7u) ? "ok" : "corrupt");
	printf("HALO_PS2_LOCAL render-owner name=renderer_workspace cap=%u guard=%s\n",
		(unsigned)renderer_workspace_bytes,
		hcu_guard_intact(renderer_workspace_guard, 0xC7u) ? "ok" : "corrupt");
	printf("HALO_PS2_LOCAL frame-parent name=frame_scratch used=%u high=%u cap=%u nested-counted-once=1\n",
		(unsigned)frame_scratch->used, (unsigned)frame_scratch->high,
		(unsigned)frame_scratch->cap);
	if (report_and_validate_regions(&layout,
		ee_physical_address(backing),
		backing_bytes + MEM_LAYOUT_V2_GUARDED_SLACK) != 0 ||
		!mem_layout_v2_guards_intact(&layout)) {
		printf("HALO_PS2_FAIL budget-v2 boundary canary corrupted\n");
		result = 1;
	}
	printf("HALO_PS2_LOCAL arena name=%s cap=%u used=%u high=%u "
		"alloc_failures=%u resets=%u releases=%u invalid_releases=%u\n",
		map_owner_storage.name, (unsigned)map_owner_storage.cap,
		(unsigned)map_owner_storage.used, (unsigned)map_owner_storage.high,
		(unsigned)map_owner_storage.failed_allocations,
		(unsigned)map_owner_storage.reset_count,
		(unsigned)map_owner_storage.release_count,
		(unsigned)map_owner_storage.invalid_releases);
	printf("HALO_PS2_LOCAL arena name=%s cap=%u used=%u high=%u "
		"alloc_failures=%u resets=%u releases=%u invalid_releases=%u\n",
		render_section_scratch.name, (unsigned)render_section_scratch.cap,
		(unsigned)render_section_scratch.used,
		(unsigned)render_section_scratch.high,
		(unsigned)render_section_scratch.failed_allocations,
		(unsigned)render_section_scratch.reset_count,
		(unsigned)render_section_scratch.release_count,
		(unsigned)render_section_scratch.invalid_releases);
	if (!hcu_map_service_shutdown(&s_map_service)) {
		printf("HALO_PS2_FAIL shutdown readers remain live; backing retained\n");
		return 1;
	}
	hcu_report_owner_telemetry("shutdown");
	if (snapshot_bound)
		hcu_render_snapshot_unbind();
	physical_memory_free();
	__real_free(backing);
	return result;
}
