#ifndef HALO_STREAM_HCU_PROFILE_METADATA_H
#define HALO_STREAM_HCU_PROFILE_METADATA_H

#include <stddef.h>
#include <stdint.h>
#include "stream/hcu_bitmap_dispatch.h"
#include "stream/hcu_profile_mount.h"

#ifdef __cplusplus
extern "C" {
#endif

enum {
	HCU_PROFILE_METADATA_OK = 0,
	HCU_PROFILE_METADATA_E_ARGUMENT = -1,
	HCU_PROFILE_METADATA_E_FORMAT = -2,
	HCU_PROFILE_METADATA_E_HASH = -3,
	HCU_PROFILE_METADATA_E_PROFILE = -4,
	HCU_PROFILE_METADATA_E_CAPACITY = -5
};

typedef struct {
	uint32_t profile_id;
	uint32_t bitmap_count;
	const hcu_bitmap_binding *bitmap_bindings;
	uint32_t cbsp_count;
	const hcu_profile_cbsp_binding *cbsp_bindings;
	uint32_t resource_range_count;
	const hcu_profile_resource_range *resource_ranges;
} hcu_profile_metadata_view;

/* HCM1 v1 is fixed-width little endian. All decoded arrays occupy caller storage;
 * no pointers in the input are followed and no allocation is performed. The
 * supplied SHA-256 is an external pin for the complete serialized metadata. */
int hcu_profile_metadata_decode(const void *bytes, size_t byte_count,
	const uint8_t expected_sha256[32], uint32_t expected_profile_id,
	void *storage, size_t storage_bytes, hcu_profile_metadata_view *view);

#ifdef __cplusplus
}
#endif
#endif
