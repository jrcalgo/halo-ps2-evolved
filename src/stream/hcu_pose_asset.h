#ifndef HCU_POSE_ASSET_H
#define HCU_POSE_ASSET_H

#include <stddef.h>
#include <stdint.h>

/* HPOS v1 is a pointer-free little-endian sword/gravity pose asset. These
 * routines borrow the caller's immutable chunk only for the duration of a
 * call. They allocate nothing and retain no chunk or interior pointers. */
int hcu_pose_asset_validate(const void *chunk, size_t chunk_bytes);
int hcu_pose_asset_find_node(const void *chunk, size_t chunk_bytes,
	const char *name);
int hcu_pose_asset_sample(const void *chunk, size_t chunk_bytes,
	uint16_t node_index, uint32_t frame, float quaternion[4],
	float translation[3], uint8_t *translation_override);
int hcu_pose_asset_constants(const void *chunk, size_t chunk_bytes,
	float camera_hold_quaternion[4], float mesh_quaternion[4],
	float mesh_translation[3]);

#endif
