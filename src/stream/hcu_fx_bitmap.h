/* C3.6(c) textured fx: resolve a snapshot fx request's bitmap identity to a native
 * bitmap binding, and bucket the admitted quads by binding so each distinct bitmap
 * is one texture state per view. Pure: no heap, fixed caller storage, no I/O. */
#ifndef HALO_STREAM_HCU_FX_BITMAP_H
#define HALO_STREAM_HCU_FX_BITMAP_H

#include <stdint.h>

#include "stream/hcu_bitmap_dispatch.h"

/* Snapshot value for "no bitmap" (CE NONE, -1 as uint32). */
#define HCU_FX_BITMAP_NONE 0xFFFFFFFFu

/* Quads per view are capped by HCU_FX_MAX_PER_VIEW (64), so 64 buckets bound the table. */
#define HCU_FX_BUCKET_CAP 64u

/* Verified source metadata retained only to try the renderer's resident-acquire path.
 * Pixels and CLUT bytes are never retained here. The descriptor identity includes the
 * complete binding digest and profile/map generation so stale cache-key reuse fails closed. */
#define HCU_FX_DESCRIPTOR_CAP 56u
typedef struct {
	uint32_t bitmap_output_datum, chunk_id, expected_source_datum, expected_profile_id;
	uint32_t profile_id, map_generation;
	uint8_t chunk_sha256[32];
	uint16_t bitmap_index, image_index, cache_key, width, height;
	uint8_t psm, valid;
} hcu_fx_descriptor;
typedef struct {
	hcu_fx_descriptor entries[HCU_FX_DESCRIPTOR_CAP];
	uint32_t next_replace;
} hcu_fx_descriptor_cache;
int hcu_fx_descriptor_cache_lookup(const hcu_fx_descriptor_cache *cache,
	const hcu_bitmap_binding *binding, uint32_t profile_id, uint32_t map_generation,
	hcu_fx_descriptor *out);
void hcu_fx_descriptor_cache_store(hcu_fx_descriptor_cache *cache,
	const hcu_bitmap_binding *binding, uint32_t profile_id, uint32_t map_generation,
	uint16_t width, uint16_t height, uint8_t psm);

/* Shared production/test seam for the cache decision. A resident callback returns 0
 * on hit, HCU_FX_RESIDENT_MISS when the key is no longer resident, or another error.
 * The source callback verifies/opens the bitmap and fills shape; submit consumes that
 * just-loaded source. Metadata is published only after submit succeeds. */
#define HCU_FX_RESIDENT_MISS 1
typedef int (*hcu_fx_resident_query_fn)(void *context, uint32_t cache_key,
	uint16_t width, uint16_t height, uint8_t psm, uint64_t *tex0_out);
typedef int (*hcu_fx_source_load_fn)(void *context, const hcu_bitmap_binding *binding,
	uint16_t *width, uint16_t *height, uint8_t *psm);
typedef int (*hcu_fx_source_submit_fn)(void *context, const hcu_bitmap_binding *binding,
	uint16_t width, uint16_t height, uint8_t psm, uint64_t *tex0_out);
/* Returns nonzero only when admission is provably deferred for this frame. */
typedef int (*hcu_fx_admission_defer_fn)(void *context, uint32_t cache_key,
	uint16_t width, uint16_t height, uint8_t psm);
int hcu_fx_texture_resolve(hcu_fx_descriptor_cache *cache,
	const hcu_bitmap_binding *binding, uint32_t profile_id, uint32_t map_generation,
	hcu_fx_resident_query_fn resident_query, hcu_fx_source_load_fn source_load,
	hcu_fx_source_submit_fn source_submit, void *context, uint64_t *tex0_out,
	int *source_attempted, int *source_loaded);
int hcu_fx_texture_resolve_prechecked(hcu_fx_descriptor_cache *cache,
	const hcu_bitmap_binding *binding, uint32_t profile_id, uint32_t map_generation,
	hcu_fx_resident_query_fn resident_query, hcu_fx_admission_defer_fn admission_defer,
	hcu_fx_source_load_fn source_load, hcu_fx_source_submit_fn source_submit,
	void *context, uint64_t *tex0_out, int *source_attempted, int *source_loaded);

typedef struct {
	uint32_t binding;   /* index into the binding table, or HCU_FX_BITMAP_NONE for flat quads */
	uint16_t first;     /* first slot of this bucket in the order array */
	uint16_t count;     /* quads in this bucket */
	uint8_t blend_function; /* CE shader_framebuffer_blend_function */
	uint8_t fade_mode;      /* CE shader_framebuffer_fade_mode; kept separate from blend */
} hcu_fx_bucket;

/* Binds (bitmap group tag, element) to a binding row. Returns 1 and sets *binding_index
 * when a row matches bitmap_output_datum == tag and bitmap_index == element with
 * image_index 0; returns 0 otherwise (the caller counts fx-no-binding). */
int hcu_fx_bitmap_resolve(const hcu_bitmap_binding *bindings, uint32_t binding_count,
	uint32_t tag, uint32_t element, uint32_t *binding_index);

/* Groups quads by their binding (HCU_FX_BITMAP_NONE for flat). Quads keep their relative
 * order inside a bucket and buckets appear in first-seen order. order[] receives quad
 * indices grouped by bucket. Returns the bucket count, or -1 on bad arguments or when
 * the bucket capacity is exceeded. */
int hcu_fx_bucket_quads(const uint32_t *quad_binding, uint32_t quad_count,
	uint16_t *order, hcu_fx_bucket *buckets, uint32_t bucket_capacity);
int hcu_fx_bucket_quads_state(const uint32_t *quad_binding, const uint8_t *blend_function,
	const uint8_t *fade_mode, uint32_t quad_count, uint16_t *order,
	hcu_fx_bucket *buckets, uint32_t bucket_capacity);

/* Telemetry: per-kind tally of snapshot fx requests. kind_index is 0 effect, 1 particle system,
	 * 2 contrail, 3 decal, 4 live particle; other kinds are ignored. For each kind counts[k][0] is the total,
 * counts[k][1] the requests whose bitmap resolves to a binding row, and counts[k][2] the
 * rest (drawn flat). Fixed storage, no heap, O(requests * bindings) worst case, only
 * called on the periodic telemetry frame. Returns the number of requests tallied. */
#define HCU_FX_KIND_COUNT 5u
uint32_t hcu_fx_kind_tally(const uint16_t *kinds, const uint32_t *tags, const uint32_t *elements,
	uint32_t request_count, const hcu_bitmap_binding *bindings, uint32_t binding_count,
	uint32_t counts[HCU_FX_KIND_COUNT][3]);

#endif /* HALO_STREAM_HCU_FX_BITMAP_H */
