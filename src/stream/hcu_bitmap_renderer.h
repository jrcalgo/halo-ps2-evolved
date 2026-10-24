#ifndef HALO_STREAM_HCU_BITMAP_RENDERER_H
#define HALO_STREAM_HCU_BITMAP_RENDERER_H

#include "stream/hcu_bitmap_frame.h"
#include "render/texcache.h"
#include "render/chain.h"

#ifdef __cplusplus
extern "C" {
#endif

/* Adapter between the parent BSP renderer's frame hooks and the HCU bitmap
 * dispatcher. Chains are NOT stored here: the renderer alternates two static
 * chain pairs per build, so the live pair is handed in through the emit hook
 * for the duration of one build window. All other resources are caller-owned
 * and must outlive the binding. Nothing here allocates DMA memory. */
typedef struct {
	hcu_bitmap_dispatch_context *dispatch;
	tc_t *cache;
	uint16_t *cache_readers;
	uint32_t cache_reader_count;
	void *source_storage;
	uint32_t source_storage_bytes;
	uint32_t slot_stride;
	void *staging_buffer;
	uint32_t staging_buffer_bytes;
	hcu_bitmap_source_slot *slots;
	uint32_t slot_count;
	hcu_bitmap_lease *leases;
	uint32_t lease_capacity;
	uint32_t texture_page_base_words;
	uint32_t clut_base_words;
	uint16_t screen_w;
	uint16_t screen_h;
	uint32_t frame_index;
	uint32_t submitted_kick_seq;
	hcu_bitmap_frame_owner *owner;   /* port: frame owner whose sealed batch drains in emit; NULL = no HCU owner */
	int32_t emit_status;             /* port: result of the last emit hook (HCU_BITMAP_FRAME_OK = drained) */
	uint32_t emit_failures;          /* port: emit hooks that returned a failure (E_QUEUE/E_DISPATCH/...) */
	uint8_t bound;
	uint8_t frame_open;
	uint8_t submitted;
	uint8_t reserved;
} hcu_bitmap_renderer;

int32_t hcu_bitmap_renderer_init(hcu_bitmap_renderer *renderer,
	hcu_bitmap_dispatch_context *dispatch,
	tc_t *cache, uint16_t *cache_readers, uint32_t cache_reader_count,
	void *source_storage, uint32_t source_storage_bytes, uint32_t slot_stride,
	void *staging_buffer, uint32_t staging_buffer_bytes,
	hcu_bitmap_source_slot *slots, uint32_t slot_count,
	hcu_bitmap_lease *leases, uint32_t lease_capacity,
	uint32_t texture_page_base_words, uint32_t clut_base_words,
	uint16_t screen_w, uint16_t screen_h);

/* Parent-renderer frame hooks (signatures match bsp_render_frame_hooks in
 * render/bsp_render.h; the caller fills that struct with `user` = renderer). */
int32_t hcu_bitmap_renderer_hook_begin(void *user, uint32_t frame);
int32_t hcu_bitmap_renderer_hook_emit(void *user, uint32_t frame,
	chain_t *geometry, chain_t *upload, tc_t *cache);
void hcu_bitmap_renderer_hook_submit(void *user, uint32_t frame, uint32_t kick_seq);

/* port: failure report for a caller or test. A failed drain keeps the leases it acquired (owner gpu_pending) until
 * the real kick fence; nothing is released on failure. */
int32_t hcu_bitmap_renderer_emit_status(const hcu_bitmap_renderer *renderer);
uint32_t hcu_bitmap_renderer_emit_failures(const hcu_bitmap_renderer *renderer);

/* Frame-owner fence query. 1 only when the submitted frame's own kick has its
 * VIF1 chain and GS FINISH observed; 0 pending; -1 for a stale or unsubmitted
 * frame index or an unbound renderer. */
int32_t hcu_bitmap_renderer_bsp_fence_query(void *context, uint32_t frame_index);

/* port: fence query for hcu_bitmap_frame_owner.fence_query (context = the renderer). The owner passes its own
 * CE frame index, which it has already checked. Returns -1 when no kick is submitted. */
int32_t hcu_bitmap_renderer_owner_fence_query(void *context, uint32_t ce_frame_index);

int32_t hcu_bitmap_renderer_begin_frame(hcu_bitmap_renderer *renderer, uint32_t frame_index);
int32_t hcu_bitmap_renderer_submit_frame(hcu_bitmap_renderer *renderer, uint32_t frame_index, uint32_t kick_seq);

/* port: EE-only (src/stream/hcu_bitmap_attach.c). Registers the three hooks on the parent renderer for the bound
 * owner; the owner must have been bound with fence_query = hcu_bitmap_renderer_owner_fence_query and
 * fence_context = the renderer. Detach refuses while a kick's leases are pending. */
int32_t hcu_bitmap_renderer_attach_frame(hcu_bitmap_renderer *renderer, hcu_bitmap_frame_owner *owner);
int32_t hcu_bitmap_renderer_detach_frame(hcu_bitmap_renderer *renderer);

#ifdef __cplusplus
}
#endif
#endif
