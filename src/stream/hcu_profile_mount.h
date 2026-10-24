#ifndef HALO_STREAM_HCU_PROFILE_MOUNT_H
#define HALO_STREAM_HCU_PROFILE_MOUNT_H

#include <stddef.h>
#include <stdint.h>
#include "stream/ctag_mount.h"
#include "stream/hcu_asset_profile.h"
#include "stream/hcu_map_catalog.h"

#ifdef __cplusplus
extern "C" {
#endif

enum {
	HCU_PROFILE_MOUNT_OK = 0,
	HCU_PROFILE_MOUNT_E_ARGUMENT = -1,
	HCU_PROFILE_MOUNT_E_BUSY = -2,
	HCU_PROFILE_MOUNT_E_IDENTITY = -3,
	HCU_PROFILE_MOUNT_E_CHUNK = -4,
	HCU_PROFILE_MOUNT_E_CAPACITY = -5,
	HCU_PROFILE_MOUNT_E_CTAG = -6,
	HCU_PROFILE_MOUNT_E_BACKEND = -7,
	HCU_PROFILE_MOUNT_E_RESOURCE = -8,
	HCU_PROFILE_MOUNT_E_STATE = -9
};

typedef struct {
	uint32_t source_file_offset;
	uint32_t source_file_size;
	uint32_t media_chunk_id;
	uint8_t source_map_sha256[32];
	uint8_t expected_chunk_sha256[32];
} hcu_profile_cbsp_binding;

typedef struct {
	uint32_t output_datum;
	uint32_t source_offset;
	uint32_t size;
} hcu_profile_resource_range;

typedef int (*hcu_profile_source_read_fn)(void *context, int32_t output_datum,
	uint32_t file_offset, uint32_t size, void *buffer, int blocking);

typedef struct hcu_profile_mount {
	const hcu_asset_profile_view *profile;
	hcu_asset_profile_view profile_snapshot;
	const hcu_map_catalog_entry *catalog_entry;
	hmap_identity source_identity_snapshot;
	const hcu_map_bsp_entry *catalog_bsp;
	uint16_t catalog_bsp_count;
	uint8_t catalog_bsp_sha256[32];
	const hcu_profile_cbsp_binding *cbsp_bindings;
	uint16_t cbsp_binding_count;
	uint8_t cbsp_bindings_sha256[32];
	const hcu_profile_resource_range *resource_ranges;
	uint32_t resource_range_count;
	uint8_t resource_ranges_sha256[32];
	hcu_profile_source_read_fn source_read;
	void *source_context;
	ctag_mount_backend backend;
	ctag_stream_info ctag_info;
	hcu_asset_chunk_view ce_chunk;
	uint8_t *relocation_storage;
	size_t relocation_storage_bytes;
	void *stream_scratch;
	size_t stream_scratch_bytes;
	uint32_t expected_profile_id;
	uint32_t maximum_tag_image_bytes;
	uint32_t callbacks_active;
	uint8_t prepared;
	uint8_t active;
	uint8_t backend_mounted;
	uint8_t reserved;
} hcu_profile_mount;

void hcu_profile_mount_init(hcu_profile_mount *mount);
/* Read-only preflight. HCP itself stays in caller-owned storage/file-backed
 * reads. The profile must already have passed package SHA and HCP preflight.
 * Scratch and relocations are caller-owned, disjoint spans that remain valid
 * until unload. `maximum_tag_image_bytes` is the real target tag-cache limit. */
int hcu_profile_mount_prepare(hcu_profile_mount *mount,
	const hcu_asset_profile_view *profile, uint32_t expected_profile_id,
	const hcu_map_catalog_entry *catalog_entry,
	const hcu_profile_cbsp_binding *cbsp_bindings, uint16_t cbsp_binding_count,
	const hcu_profile_resource_range *resource_ranges, uint32_t resource_range_count,
	hcu_profile_source_read_fn source_read, void *source_context,
	const ctag_mount_backend *backend, uint32_t maximum_tag_image_bytes,
	void *relocation_storage, size_t relocation_storage_bytes,
	void *stream_scratch, size_t stream_scratch_bytes);
/* Call only after the old CE map has been unpublished. Fails closed without
 * tearing down any existing backend mount. No full HCP chunk is copied. */
int hcu_profile_mount_load(hcu_profile_mount *mount);
/* Backend unpublishes CTAG/CBSP visitors and CE cache state before returning.
 * Caller may release profile/source/tables/scratch only after success. */
int hcu_profile_mount_unload(hcu_profile_mount *mount);

#ifdef __cplusplus
}
#endif
#endif
