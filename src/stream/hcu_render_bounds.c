#include "stream/hcu_render_bounds.h"

#include <float.h>
#include <math.h>
#include <string.h>

static int finite_float(float x)
{
	return x == x && x <= FLT_MAX && x >= -FLT_MAX;
}

int hcu_render_model_bound_resolve(const hcu_render_model_bound *bound,
	uint32_t expected_profile_id, uint32_t expected_source_datum,
	uint32_t expected_model_chunk, const uint8_t expected_model_sha256[32],
	uint32_t expected_tag_datum, uint32_t metadata_map_generation,
	uint32_t snapshot_map_generation, uint32_t resource_generation,
	float center_out[3], float *radius_out)
{
	unsigned i;
	if (!bound || !expected_model_sha256 || !center_out || !radius_out || bound->valid != 1u ||
		!expected_profile_id || bound->profile_id != expected_profile_id ||
		bound->source_datum != expected_source_datum ||
		bound->model_chunk != expected_model_chunk || bound->tag_datum != expected_tag_datum ||
		memcmp(bound->model_sha256, expected_model_sha256, sizeof bound->model_sha256) != 0 ||
		!metadata_map_generation || metadata_map_generation != snapshot_map_generation ||
		resource_generation != snapshot_map_generation || !finite_float(bound->radius) || bound->radius < 0.0f)
		return 0;
	for (i = 0; i < 3u; ++i)
		if (!finite_float(bound->center[i])) return 0;
	memcpy(center_out, bound->center, sizeof bound->center);
	*radius_out = bound->radius;
	return 1;
}

float hcu_render_bounds_root_radius(float ce_radius, float world_scale,
	const float model_center[3], float model_radius)
{
	float x, y, z, scale, center_distance, extent, margin, largest;
	if (!finite_float(ce_radius) || ce_radius < 0.0f) return ce_radius;
	if (!model_center || !finite_float(world_scale) || !finite_float(model_radius) || model_radius < 0.0f)
		return ce_radius;
	x = model_center[0]; y = model_center[1]; z = model_center[2];
	if (!finite_float(x) || !finite_float(y) || !finite_float(z)) return ce_radius;
	scale = fabsf(world_scale);
	largest = fabsf(x);
	if (fabsf(y) > largest) largest = fabsf(y);
	if (fabsf(z) > largest) largest = fabsf(z);
	center_distance = largest == 0.0f ? 0.0f : largest * sqrtf((x / largest) * (x / largest) +
		(y / largest) * (y / largest) + (z / largest) * (z / largest));
	if (!finite_float(center_distance)) return FLT_MAX;
	if (center_distance > FLT_MAX - model_radius) return FLT_MAX;
	extent = scale * (center_distance + model_radius);
	if (!finite_float(extent)) return FLT_MAX;
	/* Round outward so float plane arithmetic cannot undercut the transformed sphere. */
	margin = 16.0f * FLT_EPSILON * (extent > 1.0f ? extent : 1.0f);
	if (!finite_float(margin) || !finite_float(extent + margin)) return FLT_MAX;
	extent += margin;
	return extent > ce_radius ? extent : ce_radius;
}
