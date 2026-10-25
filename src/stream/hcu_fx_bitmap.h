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

typedef struct {
	uint32_t binding;   /* index into the binding table, or HCU_FX_BITMAP_NONE for flat quads */
	uint16_t first;     /* first slot of this bucket in the order array */
	uint16_t count;     /* quads in this bucket */
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

#endif /* HALO_STREAM_HCU_FX_BITMAP_H */
