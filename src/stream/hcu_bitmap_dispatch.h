#ifndef HCU_BITMAP_DISPATCH_H
#define HCU_BITMAP_DISPATCH_H

#include <stddef.h>
#include <stdint.h>
#include "stream/hcu_asset_profile.h"
#include "stream/hcu_bitmap_quad.h"
#include "halo_ps2_bitmap_requests.h"
#include "render/texcache.h"
#include "render/upload.h"

typedef struct {
	uint32_t bitmap_output_datum;
	uint16_t bitmap_index;
	uint16_t image_index;
	uint32_t chunk_id;
	uint32_t expected_source_datum;
	uint32_t expected_profile_id;
	uint8_t expected_chunk_sha256[32];
	uint16_t cache_key;
	uint16_t reserved;
} hcu_bitmap_binding;

typedef struct {
	uint32_t chunk_id;
	uint16_t cache_key;
	uint16_t reserved;
	uint32_t storage_offset;
	uint32_t storage_bytes;
	uint16_t readers;
	uint8_t valid;
	uint8_t reserved8;
} hcu_bitmap_source_slot;

typedef struct {
	uint16_t slot;
	uint16_t active;
	uint16_t cache_key;
	uint16_t reserved;
	uint32_t generation;
	uint32_t kick_seq;   /* C3.10: the parent kick that carries this lease's upload (0 = not bound to a kick) */
} hcu_bitmap_lease;

/* Pointer-free metadata for a verified resident resource generation. No source
 * pixels are retained here; upload slots retain bytes through their real fence. */
typedef struct {
	uint32_t bitmap_output_datum, chunk_id, expected_source_datum, profile_id, generation;
	uint32_t source_offset, mip_bytes, clut_bytes;
	uint16_t bitmap_index, image_index, cache_key;
	uint16_t width, height, clut_entries;
	uint8_t psm, valid;
	uint8_t chunk_sha256[32];
} hcu_bitmap_resident_descriptor;

typedef struct {
	uint32_t hits, misses, source_reads, source_bytes, hash_checks, parses;
	uint32_t read_calls, read_bytes;
	uint32_t read_cycles, hash_cycles, parse_cycles, source_cycles;
	uint32_t deferred;
} hcu_bitmap_dispatch_counters;

typedef enum {
	HCU_BITMAP_DISPATCH_OK = 0,
	HCU_BITMAP_DISPATCH_E_ARGUMENT = -1,
	HCU_BITMAP_DISPATCH_E_IDENTITY = -2,
	HCU_BITMAP_DISPATCH_E_CHUNK = -3,
	HCU_BITMAP_DISPATCH_E_FORMAT = -4,
	HCU_BITMAP_DISPATCH_E_CAPACITY = -5,
	HCU_BITMAP_DISPATCH_E_BUSY = -6,
	HCU_BITMAP_DISPATCH_E_UNSUPPORTED = -7,
	HCU_BITMAP_DISPATCH_E_VIEW = -8,
	/* Texture cache could not admit this request this frame (no evictable victim or upload budget). Not a
	 * failure: the request is counted as deferred and CE re-issues it next frame. Internal to the reader;
	 * hcu_bitmap_dispatch_request reports it as E_CAPACITY. */
	HCU_BITMAP_DISPATCH_E_DEFERRED = -9
} hcu_bitmap_dispatch_status;

/* Every backing store is caller-owned. `source_storage` packs only the pixel and
 * CLUT bytes referenced by successful uploads, up to its total byte capacity;
 * `slot_stride` bounds the one serialized TEXS chunk read through staging. This
 * keeps the per-frame source retention bounded by the texcache upload budget.
 * `journal` is the bounded per-request undo journal for the shared tc_t (no whole-table copy).
 * Keep a lease until both upload and draw DMA have fenced. */
hcu_bitmap_dispatch_status hcu_bitmap_dispatch_request(
	const halo_ps2_bitmap_request *request,
	const hcu_bitmap_binding *bindings, uint32_t binding_count,
	const hcu_asset_profile_view *profile,
	uint32_t expected_generation,
	tc_t *cache, tc_journal_t *journal,
	uint16_t *cache_readers, uint32_t cache_reader_count,
	hcu_bitmap_source_slot *slots, uint32_t slot_count,
	void *source_storage, uint32_t source_storage_bytes, uint32_t slot_stride,
	void *staging_buffer, uint32_t staging_buffer_bytes,
	chain_t *upload_chain, chain_t *geometry_chain,
	uint32_t texture_page_base_words, uint32_t clut_base_words,
	uint16_t screen_w, uint16_t screen_h,
	hcu_bitmap_rect target, hcu_bitmap_lease *lease);
void hcu_bitmap_dispatch_release(hcu_bitmap_source_slot *slots,
	uint32_t slot_count, uint16_t *cache_readers, uint32_t cache_reader_count,
	hcu_bitmap_lease *lease);

typedef struct {
	const hcu_bitmap_binding *bindings;
	uint32_t binding_count;
	const hcu_asset_profile_view *profile;
	uint32_t expected_generation;
	tc_t *cache;
	tc_journal_t *journal;
	uint16_t *cache_readers;
	uint32_t cache_reader_count;
	hcu_bitmap_source_slot *slots;
	uint32_t slot_count;
	void *source_storage;
	uint32_t source_storage_bytes;
	uint32_t slot_stride;
	void *staging_buffer;
	uint32_t staging_buffer_bytes;
	chain_t *upload_chain;
	chain_t *geometry_chain;
	uint32_t texture_page_base_words;
	uint32_t clut_base_words;
	uint16_t screen_w, screen_h;
	/* Per-frame view table written by the frame owner (CE window index -> screen rect).
	 * view_count 0 means full-screen placement for single-view producers. */
	hcu_bitmap_view views[HCU_BITMAP_MAX_VIEWS];
	uint32_t view_count;
	hcu_bitmap_lease *leases;
	uint32_t lease_capacity, lease_count;
	hcu_bitmap_dispatch_status first_error;
	uint32_t meter_quads;   /* monotonic: meter requests emitted (each is a fill pass plus an empty pass) */
	hcu_bitmap_resident_descriptor *resident_descriptors;
	uint32_t resident_capacity;
	uint32_t resident_generation;
	hcu_asset_profile_view resident_profile;
	hcu_bitmap_dispatch_counters counters;
} hcu_bitmap_dispatch_context;

/* Opt in to resident descriptor mode. Bind/reset only at a map/profile lifecycle
 * boundary after all outstanding leases have completed. */
hcu_bitmap_dispatch_status hcu_bitmap_dispatch_resident_bind(hcu_bitmap_dispatch_context *context,
	hcu_bitmap_resident_descriptor *descriptors, uint32_t descriptor_capacity);
void hcu_bitmap_dispatch_resident_reset(hcu_bitmap_dispatch_context *context);

/* Suitable for registration as the queue's closed-reader consumer. The queue
 * reader can be released after return; source leases remain until GPU fence. */
int hcu_bitmap_dispatch_reader(const halo_ps2_bitmap_request_reader *reader,
	void *context);
/* Releases only leases whose exact carrying kick is observed complete. Pending or
 * unknown fences leave those leases, slots, and cache readers intact. */
hcu_bitmap_dispatch_status hcu_bitmap_dispatch_complete(hcu_bitmap_dispatch_context *context);
/* Call after tc_begin_frame and before any shared-cache acquisition while leases
 * remain outstanding; this makes the existing two-frame LRU honor GPU pins. */
void hcu_bitmap_dispatch_touch_cache(tc_t *cache, const uint16_t *cache_readers,
	uint32_t cache_reader_count);

#endif
