#ifndef HALO_HCU_MAP_SERVICE_H
#define HALO_HCU_MAP_SERVICE_H

#include "core/mem.h"
#include "stream/ctag_mount.h"
#include "stream/ctag_map_source.h"
#include "stream/hcu_map_catalog.h"
#include "stream/hcu_asset_profile.h"
#include "stream/hcu_bitmap_frame.h"
#include "stream/hcu_profile_metadata.h"
#include "stream/hcu_profile_mount.h"

/* Caller validates profile-specific CE/media/sound bindings against its pinned
 * dependency manifest. This callback must be read-only and fail closed. */
typedef int (*hcu_map_profile_compatibility_fn)(void *context,
	const hcu_map_catalog_entry *entry, const hcu_asset_profile_view *profile);

/* Caller-owned HCP runtime. Every pointer and span below must stay valid from
 * registration until the service has unloaded the profile (or shut down). The
 * service never allocates or frees any of it. Spans must be pairwise disjoint.
 * frame_owner is the bitmap frame owner whose dispatcher leases gate unload;
 * when it is NULL, readers cannot be proven drained and unload fails closed. */
/* Called at map boundaries: "map-loaded" after a successful load, "map-released"
 * after an owner's storage is released, "map-empty" after a failed load. */
typedef void (*hcu_map_service_boundary_fn)(void *context, const char *phase,
	unsigned int cycle);

typedef struct {
	hcu_asset_profile_read_at package_read_at;
	void *package_context;
	uint32_t package_size;
	uint32_t profile_id;
	uint8_t package_sha256[32];
	hcu_map_profile_compatibility_fn compatibility;
	void *compatibility_context;
	const void *metadata_bytes;
	size_t metadata_size;
	uint8_t metadata_sha256[32];
	void *metadata_storage;
	size_t metadata_storage_bytes;
	hcu_profile_source_read_fn source_read;
	void *source_context;
	void *relocation_storage;
	size_t relocation_storage_bytes;
	void *stream_scratch;
	size_t stream_scratch_bytes;
	uint32_t maximum_tag_image_bytes;
	const hcu_bitmap_frame_owner *frame_owner;
	/* Parent renderer drain predicate. Unload and successor staging require it
	 * to return nonzero: its DMA fence observed and no reference left to the
	 * map's world or texture storage. NULL fails closed. */
	int (*renderer_drained)(void *context);
	void *renderer_context;
	/* Explicit CPU-only guest probe mode. This is never used by the normal
	 * runtime. It permits a NULL frame owner only when the caller proves that
	 * no renderer consumer has started and the BSP lease table is idle. */
	int headless_no_bitmap_consumers;
	int (*renderer_never_started)(void *context);
	void *renderer_start_context;
	/* Only the explicit headless runtime guest may open the candidate
	 * admission branch in the map service. The row is generated into the
	 * runtime header and must already match HCU's selected partition. */
	int headless_candidate_admission;
	const char *partition_row;
	/* Caller-owned CE/CBSP segment residency. Bound before every prepare, so a
	 * registered runtime never reads whole chunks. The arena is whole 64 KiB
	 * slots, 16-byte aligned, and disjoint from every other span. */
	hcu_asset_residency_entry *residency_entries;
	uint32_t residency_entry_capacity;
	void *residency_arena;
	size_t residency_arena_bytes;
} hcu_map_profile_runtime;

typedef struct {
	int valid;
	int active;
	char map_name[16];
	unsigned int cycle;
	/* Current map/run scope. On release, current_bytes is the actual residual
	 * table value after teardown (normally zero); high/counters survive it. */
	hcu_profile_residency_stats map;
	/* Service lifetime: max capacity/high-water, sums for event counters, and
	 * successful quiescent table resets. Nested bytes are never backing totals. */
	hcu_profile_residency_stats lifetime;
} hcu_map_residency_report;

typedef struct {
	arena_t *map_arena;
	arena_t *section_scratch;
	ctag_mount mount;
	ctag_map_source source;
	hmap_identity identity;
	ctag_stream_info ctag_info;
	const hcu_map_catalog_entry *staged_entry;
	const ctag_mount_backend *backend;
	char staged_map[16];
	int preflight_ready;
	int reload_pending;
	int initialized;
	int profile_requested;
	uint32_t expected_profile_id;
	uint32_t profile_image_size;
	uint8_t expected_profile_sha256[32];
	hcu_asset_profile_read_at profile_read_at;
	void *profile_reader_context;
	hcu_map_profile_compatibility_fn profile_compatibility;
	void *profile_compatibility_context;
	/* Integrity/identity preflight view only. Existing mount remains CTAG-backed;
	 * this field does not claim CE profile bytes have been published to CE. */
	hcu_asset_profile_view profile_view;
	char profile_map_name[16];
	/* HCP runtime path. When runtime_registered is set, CE's preflight/load
	 * hooks use hcu_profile_mount instead of the CTAG section path. The legacy
	 * register_profile gate and this runtime are mutually exclusive. */
	int runtime_registered;
	hcu_map_profile_runtime runtime;
	char runtime_map_name[16];
	hcu_profile_mount profile_mount;
	hcu_profile_mount profile_candidate;
	int profile_candidate_ready;
	/* Foreign successor: a second caller-owned runtime for another catalog map.
	 * It is staged while the live owner keeps its storage, and becomes the
	 * registered runtime when CE has released that owner. */
	int successor_registered;
	int successor_staged;
	hcu_map_profile_runtime successor;
	char successor_map_name[16];
	hcu_asset_profile_view successor_view;
	/* Legacy (non-runtime) production path only. When set, CE's legacy unloader
	 * and loader refuse to release or replace map storage while the predicate
	 * reports the renderer busy. NULL keeps the host fixtures unchanged. */
	int (*legacy_renderer_drained)(void *context);
	void *legacy_renderer_context;
	/* Optional boundary hook. boundary_cycle counts successful map loads. */
	hcu_map_service_boundary_fn boundary_hook;
	void *boundary_context;
	unsigned int boundary_cycle;
	char residency_last_map[16];
	unsigned int residency_last_cycle;
	int residency_last_valid;
	hcu_profile_residency_stats residency_last;
	hcu_profile_residency_stats residency_lifetime;
} hcu_map_service;

	/* Register the parent-owned loader/unloader after FileXio is initialized.
	 * The retail catalog binds map identity and BSP extents. Until a gameplay
	 * map passes M2 capacity qualification, only the UI entry may be mounted. */
int hcu_map_service_init(hcu_map_service *service,
	mem_layout_v2_t *layout, const char *asset_root);
/* Production HCU startup may reserve a disjoint tail of frame_scratch for
 * section decode work after placing the immutable render snapshot banks. */
int hcu_map_service_init_with_scratch(hcu_map_service *service,
	mem_layout_v2_t *layout, const char *asset_root,
	arena_t *section_scratch);
/* Bounded production layout may partition streaming into disjoint persistent
 * map ownership and temporary section-decode scratch arenas. */
int hcu_map_service_init_with_arenas(hcu_map_service *service,
	mem_layout_v2_t *layout, const char *asset_root,
	arena_t *map_owner, arena_t *section_scratch);
/* Snapshot the actual segment table for the active map, or the most recently
 * released map, plus service-lifetime high-water and event totals. */
int hcu_map_service_residency_snapshot(const hcu_map_service *service,
	hcu_map_residency_report *report);
/* Non-mutating map preflight; caller invokes before unloading the old scenario. */
int hcu_map_service_preflight(const char *map_name);
/* Pin a profile to one catalog map identity and an externally pinned exact HCP
 * image digest. The reader/context remain caller-owned until unregister or
 * service shutdown; registration and every subsequent preflight verify it. */
int hcu_map_service_register_profile(hcu_map_service *service,
	const char *map_name, uint32_t profile_id,
	hcu_asset_profile_read_at read_at, void *reader_context,
	uint32_t image_size, const uint8_t expected_package_sha256[32],
	hcu_map_profile_compatibility_fn compatibility,
	void *compatibility_context);
/* Unregister only after the active mount/source has been unloaded. */
int hcu_map_service_unregister_profile(hcu_map_service *service);
/* Register the caller-owned HCP runtime for one catalog map. The package digest
 * and compatibility gate are checked here; metadata decode and mount preparation
 * run in every preflight. Refused while any map owner or stage is live. */
int hcu_map_service_register_runtime(hcu_map_service *service,
	const char *map_name, const hcu_map_profile_runtime *runtime);
/* Refused while a profile owner is mounted or a successor is staged. */
int hcu_map_service_unregister_runtime(hcu_map_service *service);
/* Register a second caller-owned runtime for a different catalog map while a
 * runtime is registered, even while its owner is mounted. The successor's
 * spans must be disjoint from the registered runtime's, so staging never
 * writes the live owner's storage. It becomes the registered runtime when CE
 * releases the owner and a load of the successor begins. */
int hcu_map_service_register_successor_runtime(hcu_map_service *service,
	const char *map_name, const hcu_map_profile_runtime *runtime);
/* Returns zero with the service and storage ownership intact while readers or
 * callbacks remain live. The caller must drain and retry before freeing backing. */
int hcu_map_service_shutdown(hcu_map_service *service);
/* Optional, legacy path only, after init: the renderer's drain predicate. Map
 * storage is released or replaced only while it returns nonzero. Refused while
 * a runtime is registered, which carries its own renderer_drained gate. */
int hcu_map_service_set_legacy_renderer_drained(hcu_map_service *service,
	int (*renderer_drained)(void *context), void *context);
/* Optional, after init: a boundary hook for per-cycle telemetry. NULL clears it
 * and makes every boundary a no-op. Resets the cycle counter to zero. */
int hcu_map_service_set_boundary_hook(hcu_map_service *service,
	hcu_map_service_boundary_fn hook, void *context);
/* Read-only diagnostic trace used by the opt-in M2 CE lifecycle fixture. */
void hcu_map_service_lifecycle_trace(const char *phase, unsigned int cycle);
#ifdef HALO_PS2_M2_UI_LIFECYCLE_TEST
/* Test-profile-only failure injection at CE's pre-unload and post-unload seams. */
void hcu_map_service_lifecycle_fail_preflight_once(void);
void hcu_map_service_lifecycle_arm_deferred_failure_once(void);
#endif

#endif
