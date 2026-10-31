#include "stream/hcu_fx_bitmap.h"

#include <stddef.h>
#include <string.h>

_Static_assert(sizeof(hcu_fx_descriptor_cache) <= 4096u,
	"FX verified descriptor cache exceeds its frame_scratch reservation");

static int descriptor_matches(const hcu_fx_descriptor *d, const hcu_bitmap_binding *b,
	uint32_t profile_id, uint32_t map_generation)
{
	return d->valid && d->bitmap_output_datum == b->bitmap_output_datum &&
		d->bitmap_index == b->bitmap_index && d->image_index == b->image_index &&
		d->chunk_id == b->chunk_id && d->expected_source_datum == b->expected_source_datum &&
		d->expected_profile_id == b->expected_profile_id && d->profile_id == profile_id &&
		d->map_generation == map_generation && d->cache_key == b->cache_key &&
		memcmp(d->chunk_sha256, b->expected_chunk_sha256, sizeof d->chunk_sha256) == 0;
}

static int descriptor_same_binding(const hcu_fx_descriptor *d, const hcu_bitmap_binding *b)
{
	return d->valid && d->bitmap_output_datum == b->bitmap_output_datum &&
		d->bitmap_index == b->bitmap_index && d->image_index == b->image_index &&
		d->chunk_id == b->chunk_id && d->expected_source_datum == b->expected_source_datum &&
		d->expected_profile_id == b->expected_profile_id && d->cache_key == b->cache_key &&
		memcmp(d->chunk_sha256, b->expected_chunk_sha256, sizeof d->chunk_sha256) == 0;
}

int hcu_fx_descriptor_cache_lookup(const hcu_fx_descriptor_cache *cache,
	const hcu_bitmap_binding *binding, uint32_t profile_id, uint32_t map_generation,
	hcu_fx_descriptor *out)
{
	uint32_t i;
	if (!cache || !binding || !out) return 0;
	for (i = 0; i < HCU_FX_DESCRIPTOR_CAP; ++i) {
		if (descriptor_matches(&cache->entries[i], binding, profile_id, map_generation)) {
			*out = cache->entries[i];
			return 1;
		}
	}
	return 0;
}

void hcu_fx_descriptor_cache_store(hcu_fx_descriptor_cache *cache,
	const hcu_bitmap_binding *binding, uint32_t profile_id, uint32_t map_generation,
	uint16_t width, uint16_t height, uint8_t psm)
{
	hcu_fx_descriptor *d;
	uint32_t i;
	if (!cache || !binding || !width || !height) return;
	for (i = 0; i < HCU_FX_DESCRIPTOR_CAP; ++i)
		if (descriptor_same_binding(&cache->entries[i], binding)) break;
	if (i == HCU_FX_DESCRIPTOR_CAP) {
		i = cache->next_replace++ % HCU_FX_DESCRIPTOR_CAP;
	}
	d = &cache->entries[i];
	memset(d, 0, sizeof *d);
	d->bitmap_output_datum = binding->bitmap_output_datum;
	d->bitmap_index = binding->bitmap_index;
	d->image_index = binding->image_index;
	d->chunk_id = binding->chunk_id;
	d->expected_source_datum = binding->expected_source_datum;
	d->expected_profile_id = binding->expected_profile_id;
	d->profile_id = profile_id;
	d->map_generation = map_generation;
	d->cache_key = binding->cache_key;
	memcpy(d->chunk_sha256, binding->expected_chunk_sha256, sizeof d->chunk_sha256);
	d->width = width;
	d->height = height;
	d->psm = psm;
	d->valid = 1u;
}

int hcu_fx_texture_resolve(hcu_fx_descriptor_cache *cache,
	const hcu_bitmap_binding *binding, uint32_t profile_id, uint32_t map_generation,
	hcu_fx_resident_query_fn resident_query, hcu_fx_source_load_fn source_load,
	hcu_fx_source_submit_fn source_submit, void *context, uint64_t *tex0_out,
	int *source_attempted, int *source_loaded)
{
	return hcu_fx_texture_resolve_prechecked(cache, binding, profile_id, map_generation,
		resident_query, NULL, source_load, source_submit, context, tex0_out,
		source_attempted, source_loaded);
}

int hcu_fx_texture_resolve_prechecked(hcu_fx_descriptor_cache *cache,
	const hcu_bitmap_binding *binding, uint32_t profile_id, uint32_t map_generation,
	hcu_fx_resident_query_fn resident_query, hcu_fx_admission_defer_fn admission_defer,
	hcu_fx_source_load_fn source_load, hcu_fx_source_submit_fn source_submit,
	void *context, uint64_t *tex0_out, int *source_attempted, int *source_loaded)
{
	hcu_fx_descriptor d;
	uint16_t width = 0, height = 0;
	uint8_t psm = 0;
	int st;
	if (source_attempted) *source_attempted = 0;
	if (source_loaded) *source_loaded = 0;
	if (!binding || !source_load || !source_submit || !tex0_out) return -1;
	if (cache && resident_query &&
		hcu_fx_descriptor_cache_lookup(cache, binding, profile_id, map_generation, &d)) {
		st = resident_query(context, binding->cache_key, d.width, d.height, d.psm, tex0_out);
		if (st != HCU_FX_RESIDENT_MISS) return st;
		width = d.width; height = d.height; psm = d.psm;
		if (admission_defer) {
			st = admission_defer(context, binding->cache_key, width, height, psm);
			if (st != 0) return st;
		}
	}
	if (source_attempted) *source_attempted = 1;
	st = source_load(context, binding, &width, &height, &psm);
	if (st != 0) return st;
	if (source_loaded) *source_loaded = 1;
	/* Validated pointer-free metadata survives admission deferral. */
	if (cache) hcu_fx_descriptor_cache_store(cache, binding, profile_id, map_generation, width, height, psm);
	st = source_submit(context, binding, width, height, psm, tex0_out);
	return st;
}

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
	{ return hcu_fx_bucket_quads_state(quad_binding, NULL, NULL, quad_count, order, buckets, bucket_capacity); }

int hcu_fx_bucket_quads_state(const uint32_t *quad_binding, const uint8_t *blend_function,
	const uint8_t *fade_mode, uint32_t quad_count, uint16_t *order,
	hcu_fx_bucket *buckets, uint32_t bucket_capacity)
{
	uint32_t b, q, n = 0, fill;
	#define FX_BF(qi) (blend_function ? blend_function[(qi)] : 0u)
	#define FX_FM(qi) (fade_mode ? fade_mode[(qi)] : 0u)
	/* One view admits at most HCU_FX_BUCKET_CAP quads (HCU_FX_MAX_PER_VIEW). */
	if (!order || !buckets || (!quad_binding && quad_count) || quad_count > HCU_FX_BUCKET_CAP)
		return -1;
	for (q = 0; q < quad_count; q++) {
		uint32_t key = quad_binding[q];
		for (b = 0; b < n && (buckets[b].binding != key ||
			buckets[b].blend_function != FX_BF(q) || buckets[b].fade_mode != FX_FM(q)); b++) {}
		if (b == n) {
			if (n == bucket_capacity || n >= HCU_FX_BUCKET_CAP) return -1;
			buckets[n].binding = key;
			buckets[n].first = 0;
			buckets[n].count = 0;
			buckets[n].blend_function = (uint8_t)FX_BF(q);
			buckets[n].fade_mode = (uint8_t)FX_FM(q);
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
			if (quad_binding[q] == buckets[b].binding &&
				FX_BF(q) == buckets[b].blend_function && FX_FM(q) == buckets[b].fade_mode)
				order[at++] = (uint16_t)q;
	}
	#undef FX_BF
	#undef FX_FM
	return (int)n;
}

uint32_t hcu_fx_kind_tally(const uint16_t *kinds, const uint32_t *tags, const uint32_t *elements,
	uint32_t request_count, const hcu_bitmap_binding *bindings, uint32_t binding_count,
	uint32_t counts[HCU_FX_KIND_COUNT][3])
{
	uint32_t i, k, tallied = 0;
	uint32_t binding;
	if (!counts) return 0;
	for (k = 0; k < HCU_FX_KIND_COUNT; k++) counts[k][0] = counts[k][1] = counts[k][2] = 0;
	if (!kinds || !tags || !elements) return 0;
	for (i = 0; i < request_count; i++) {
		/* Snapshot ABI kinds: effect, particle system, contrail, decal, live particle.
		 * 4 is LIGHT, currently unpublished. */
		if (kinds[i] == 5u) k = 3u;
		else if (kinds[i] == 6u) k = 4u;
		else if (kinds[i] >= 1u && kinds[i] <= 3u) k = (uint32_t)kinds[i] - 1u;
		else continue;
		counts[k][0]++;
		if (hcu_fx_bitmap_resolve(bindings, binding_count, tags[i], elements[i], &binding))
			counts[k][1]++;
		else
			counts[k][2]++;
		tallied++;
	}
	return tallied;
}
