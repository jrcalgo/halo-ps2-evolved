#include "stream/hcu_fx_bitmap.h"

#include <stddef.h>

int hcu_fx_bitmap_resolve(const hcu_bitmap_binding *bindings, uint32_t binding_count,
	uint32_t tag, uint32_t element, uint32_t *binding_index)
{
	uint32_t i;
	if (!binding_index) return 0;
	*binding_index = HCU_FX_BITMAP_NONE;
	if (tag == HCU_FX_BITMAP_NONE || !bindings || element > 0xFFFFu) return 0;
	for (i = 0; i < binding_count; i++) {
		if (bindings[i].bitmap_output_datum == tag &&
			bindings[i].bitmap_index == (uint16_t)element &&
			bindings[i].image_index == 0u) {
			*binding_index = i;
			return 1;
		}
	}
	return 0;
}

int hcu_fx_bucket_quads(const uint32_t *quad_binding, uint32_t quad_count,
	uint16_t *order, hcu_fx_bucket *buckets, uint32_t bucket_capacity)
{
	uint32_t b, q, n = 0, fill;
	/* One view admits at most HCU_FX_BUCKET_CAP quads (HCU_FX_MAX_PER_VIEW). */
	if (!order || !buckets || (!quad_binding && quad_count) || quad_count > HCU_FX_BUCKET_CAP)
		return -1;
	for (q = 0; q < quad_count; q++) {
		uint32_t key = quad_binding[q];
		for (b = 0; b < n && buckets[b].binding != key; b++) {}
		if (b == n) {
			if (n == bucket_capacity || n >= HCU_FX_BUCKET_CAP) return -1;
			buckets[n].binding = key;
			buckets[n].first = 0;
			buckets[n].count = 0;
			n++;
		}
		buckets[b].count++;
	}
	fill = 0;
	for (b = 0; b < n; b++) {
		buckets[b].first = (uint16_t)fill;
		fill += buckets[b].count;
	}
	/* Second pass: place quads in bucket order, stable inside each bucket. */
	for (b = 0; b < n; b++) {
		uint32_t at = buckets[b].first;
		for (q = 0; q < quad_count; q++)
			if (quad_binding[q] == buckets[b].binding) order[at++] = (uint16_t)q;
	}
	return (int)n;
}
