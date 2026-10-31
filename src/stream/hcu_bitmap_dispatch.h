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
	uint16_t gs_page_first, gs_page_count;
	uint16_t compose_clut_slot, reserved16;
} hcu_bitmap_source_slot;

/* The retail sniper's two-map overlays retain four indexed source images and
 * compose into a bounded PSMT4 pool until the exact parent fence. */
#define HCU_BITMAP_COMPOSE_SOURCE_COUNT 4u
#define HCU_BITMAP_COMPOSE_SOURCE_BYTES 6144u
#define HCU_BITMAP_COMPOSE_OUTPUT_REQUESTS 8u
#define HCU_BITMAP_COMPOSE_OUTPUT_COUNT 16u /* two parent frames may own all eight request slots */
/* Retail angle-ticks overlays cover 8×512 native pixels. Sixteen physical
 * slots (two frames × eight requests) need 33,792 bytes plus alignment. */
#define HCU_BITMAP_COMPOSE_OUTPUT_POOL_BYTES (40u * 1024u)
#define HCU_BITMAP_COMPOSE_RESERVED_BYTES \
	(HCU_BITMAP_COMPOSE_SOURCE_COUNT * HCU_BITMAP_COMPOSE_SOURCE_BYTES + \
	 HCU_BITMAP_COMPOSE_OUTPUT_POOL_BYTES)

typedef struct {
	uint32_t generation;
	uint32_t bitmap_output_datum, chunk_id, expected_source_datum, expected_profile_id;
	uint32_t storage_offset, index_bytes, clut_bytes;
	uint16_t bitmap_index, image_index, width, height, clut_entries;
	uint8_t psm, valid;
	uint8_t chunk_sha256[32];
} hcu_bitmap_compose_source;

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
	uint32_t screen_flashes; /* monotonic: screen flash quads emitted */
	hcu_bitmap_resident_descriptor *resident_descriptors;
	uint32_t resident_capacity;
	uint32_t resident_generation;
	hcu_asset_profile_view resident_profile;
	hcu_bitmap_dispatch_counters counters;
	uint32_t compose_cache_generation;
	uint32_t compose_source_cursor;
	hcu_bitmap_compose_source compose_sources[HCU_BITMAP_COMPOSE_SOURCE_COUNT];
	/* Native CE screen-effect inputs are copied from the sealed request queue
	 * during the existing bitmap drain. They remain valid for exactly this
	 * captured generation/frame and do not retain queue or tag pointers. */
	halo_ps2_screen_effect_state screen_effects[HALO_PS2_BITMAP_MAX_VIEWS];
	uint64_t screen_effect_mask_tex0[HALO_PS2_BITMAP_MAX_VIEWS];
	uint64_t screen_effect_mask_clamp[HALO_PS2_BITMAP_MAX_VIEWS];
	uint32_t screen_effect_generation, screen_effect_frame_index;
	uint32_t screen_effect_valid_mask;
	uint32_t screen_effect_mask_texture_valid_mask;
	uint32_t screen_effect_masks_deferred;
	uint32_t screen_effect_prepared_request_mask[HALO_PS2_BITMAP_REQUEST_CAPACITY / 32u];
	uint32_t screen_effect_prepared_count;
	uint8_t screen_effect_snapshot_valid;
	uint8_t screen_effect_backend_active;
} hcu_bitmap_dispatch_context;

/* Snapshot the native parameter block from a sealed CE queue. The current PS2
 * backend has no native warp/filter implementation, so captured masks remain
 * inactive and the ordinary bitmap dispatcher will not draw them as overlays. */
int32_t hcu_bitmap_dispatch_capture_screen_effects(hcu_bitmap_dispatch_context *context,
	const halo_ps2_bitmap_request_queue *queue);
void hcu_bitmap_dispatch_screen_effect_reset(hcu_bitmap_dispatch_context *context);
/* Returns 1 for a matching per-view snapshot, 0 when absent, and -1 for stale
 * or invalid arguments. The returned struct contains values only, no CE pointers. */
int32_t hcu_bitmap_dispatch_screen_effect_get(const hcu_bitmap_dispatch_context *context,
	uint32_t generation, uint32_t frame_index, uint16_t view_index,
	halo_ps2_screen_effect_state *state);
int32_t hcu_bitmap_dispatch_screen_effect_mask_get(const hcu_bitmap_dispatch_context *context,
	uint32_t generation, uint32_t frame_index, uint16_t view_index,
	uint64_t *tex0, uint64_t *clamp);
/* Pre-HUD callback path: transactionally acquire the real CE mask bitmap,
 * append only its upload if needed, pin it through the carrying kick, and
 * return the resident GS texture state without emitting an ordinary quad. */
int32_t hcu_bitmap_dispatch_prepare_screen_effect_mask(hcu_bitmap_dispatch_context *context,
	const halo_ps2_bitmap_request_reader *reader, uint32_t request_index,
	uint64_t *tex0, uint64_t *clamp);
/* Return a full PSMT8 CLUT copy for the native inverse-mask GS pass. Indices
 * and RGB bytes are unchanged; the 0..128 GS alpha byte is complemented. */
int32_t hcu_bitmap_dispatch_screen_effect_mask_complement_clut(
	hcu_bitmap_dispatch_context *context,
	const halo_ps2_bitmap_request_reader *reader, uint32_t request_index,
	uint8_t clut_rgba32[1024]);

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

/* GS alpha-test reference for a meter pass (see hcu_bitmap_dispatch.c). */
uint8_t hcu_bitmap_meter_alpha_ref(uint32_t value, uint32_t vertex_alpha);

#endif
