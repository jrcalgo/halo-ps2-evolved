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
} hcu_map_profile_runtime;

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
void hcu_map_service_shutdown(hcu_map_service *service);
/* Read-only diagnostic trace used by the opt-in M2 CE lifecycle fixture. */
void hcu_map_service_lifecycle_trace(const char *phase, unsigned int cycle);
#ifdef HALO_PS2_M2_UI_LIFECYCLE_TEST
/* Test-profile-only failure injection at CE's pre-unload and post-unload seams. */
void hcu_map_service_lifecycle_fail_preflight_once(void);
void hcu_map_service_lifecycle_arm_deferred_failure_once(void);
#endif

#endif
