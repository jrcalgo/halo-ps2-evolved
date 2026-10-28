#ifndef HALO_STREAM_HCU_RENDER_BOUNDS_H
#define HALO_STREAM_HCU_RENDER_BOUNDS_H

#include <stdint.h>

/* Generated from the exact MODL payload in the mounted profile. Identity fields
 * bind the geometry sphere to the HCP profile, RMD resource, and MODL hash. */
typedef struct {
	uint32_t profile_id;
	uint32_t model_chunk;
	uint32_t source_datum;
	uint32_t tag_datum;
	uint8_t model_sha256[32];
	float center[3];
	float radius;
	uint32_t valid;
} hcu_render_model_bound;

/* Return 1 and copy the sphere only when profile, resource, model chunk/hash,
 * and current map generation all match. A missing/stale row is a safe fallback. */
int hcu_render_model_bound_resolve(const hcu_render_model_bound *bound,
	uint32_t expected_profile_id, uint32_t expected_source_datum,
	uint32_t expected_model_chunk, const uint8_t expected_model_sha256[32],
	uint32_t expected_tag_datum, uint32_t metadata_map_generation,
	uint32_t snapshot_map_generation, uint32_t resource_generation,
	float center_out[3], float *radius_out);

/* Conservative radius about the object root covering the transformed MODL
 * sphere. Returns the larger of CE's radius and |scale|*(|center|+radius), or
 * CE's radius on invalid/missing MODL metadata. */
float hcu_render_bounds_root_radius(float ce_radius, float world_scale,
	const float model_center[3], float model_radius);

#endif
