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

/* config/memory-budget.json version 3. Physical EE layout, derived from named
 * constants: 1 MiB low kernel, then elf_static (2,359,296 bytes) holding the
 * file-backed ELF sections, then the single boot backing (MEM_LAYOUT_V2_BYTES),
 * then the uncommitted reserve up to the 0x01f80000 high kernel reservation.
 * ELF NOBITS is charged to resident_gameplay, not to elf_static. */
#define HCU_LOW_KERNEL_BYTES 0x00100000u
#define HCU_ELF_STATIC_BYTES 2359296u
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
	return bsp_render_fence_observed(kick) != 0;
}

/* The explicit headless runtime guest exits before CE's renderer loop. A
 * missing frame owner is safe there only while no bitmap frame or BSP kick
 * has ever started; all other builds keep requiring the real frame owner. */
#ifdef HALO_HCU_HEADLESS_RUNTIME_GUEST
static int hcu_renderer_never_started(void *ctx)
{
	(void)ctx;
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
/* Defined by the CE port (ps2_sound_cache.c). Each CE sound request reaches
 * the recorder below; the audio backend is not qualified (SPU2). */
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
	(void)accepted;
	memset(&request, 0, sizeof(request));
	request.event = HCU_SOUND_EVENT_PERMUTATION;
	request.permutation = (uint32_t)(uintptr_t)sound;
	request.flags = (uint8_t)((block ? 1u : 0u) | (load ? 2u : 0u) |
		(reference ? 4u : 0u));
	request.gain = 1.0f;
	request.pitch = 1.0f;
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
	printf("HALO_PS2_LOCAL m2-cycle-boundary phase=%s cycle=%u\n", phase, cycle);
	hcu_report_owner_telemetry(phase);
	/* C3:replace begin */
#if defined(HCU_C3_FRAME_SNAPSHOT)
	/* Drain once per boundary. The audio side is not qualified, so drained
	 * records are only counted, never played. */
	{
		hcu_sound_request drained[HCU_SOUND_REQUEST_CAPACITY];
		(void)hcu_sound_requests_drain(&s_c3_sound_queue, drained,
			HCU_SOUND_REQUEST_CAPACITY);
	}
	hcu_sound_requests_print(&s_c3_sound_queue, phase);
	printf("HALO_PS2_LOCAL renderer-readers phase=%s outstanding=%u refused=%u\n",
		phase, hcu_map_service_reader_count(&s_map_service),
		s_map_service.reader_refused);
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
