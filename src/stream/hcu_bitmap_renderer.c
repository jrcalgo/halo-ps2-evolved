#include "stream/hcu_bitmap_renderer.h"

#include <string.h>

/* Declared here, not included: render/bsp_render.h needs the EE SDK. The
 * definition is in engine/src/render/bsp_render.c. */
int32_t bsp_render_fence_observed(uint32_t kick_seq);

static int aligned16(const void *p)
{
	return p && (((uintptr_t)p & 15u) == 0);
}

int32_t hcu_bitmap_renderer_init(hcu_bitmap_renderer *r,
	hcu_bitmap_dispatch_context *dispatch,
	tc_t *cache, uint16_t *cache_readers, uint32_t cache_reader_count,
	void *source_storage, uint32_t source_storage_bytes, uint32_t slot_stride,
	void *staging_buffer, uint32_t staging_buffer_bytes,
	hcu_bitmap_source_slot *slots, uint32_t slot_count,
	hcu_bitmap_lease *leases, uint32_t lease_capacity,
	uint32_t texture_page_base_words, uint32_t clut_base_words,
	uint16_t screen_w, uint16_t screen_h)
{
	if (!r || !dispatch || !cache_readers ||
		(cache && cache_reader_count < cache->max_keys) ||
		cache_reader_count > TC_MAX_KEYS || !source_storage || !source_storage_bytes ||
		!slot_stride || !slot_count ||
		!staging_buffer || staging_buffer_bytes < slot_stride || !slots || !leases ||
		!lease_capacity || !screen_w || !screen_h || !aligned16(source_storage) ||
		!aligned16(staging_buffer))
		return HCU_BITMAP_FRAME_E_ARGUMENT;
	if (dispatch->lease_count || dispatch->cache != cache ||
		dispatch->cache_readers != cache_readers || dispatch->cache_reader_count != cache_reader_count ||
		dispatch->source_storage != source_storage ||
		dispatch->source_storage_bytes != source_storage_bytes ||
		dispatch->slot_stride != slot_stride || dispatch->staging_buffer != staging_buffer ||
		dispatch->staging_buffer_bytes != staging_buffer_bytes || dispatch->slots != slots ||
		dispatch->slot_count != slot_count || dispatch->leases != leases ||
		dispatch->lease_capacity != lease_capacity)
		return HCU_BITMAP_FRAME_E_NOT_READY;
	memset(r, 0, sizeof(*r));
	r->dispatch = dispatch;
	r->cache = cache;
	r->cache_readers = cache_readers;
	r->cache_reader_count = cache_reader_count;
	r->source_storage = source_storage;
	r->source_storage_bytes = source_storage_bytes;
	r->slot_stride = slot_stride;
	r->staging_buffer = staging_buffer;
	r->staging_buffer_bytes = staging_buffer_bytes;
	r->slots = slots;
	r->slot_count = slot_count;
	r->leases = leases;
	r->lease_capacity = lease_capacity;
	r->texture_page_base_words = texture_page_base_words;
	r->clut_base_words = clut_base_words;
	r->screen_w = screen_w;
	r->screen_h = screen_h;
	r->bound = 1;
	dispatch->texture_page_base_words = texture_page_base_words;
	dispatch->clut_base_words = clut_base_words;
	dispatch->screen_w = screen_w;
	dispatch->screen_h = screen_h;
	return HCU_BITMAP_FRAME_OK;
}

int32_t hcu_bitmap_renderer_bsp_fence_query(void *context, uint32_t frame_index)
{
	hcu_bitmap_renderer *r = (hcu_bitmap_renderer *)context;
	if (!r || !r->bound || !r->submitted || r->frame_index != frame_index) return -1;
	return bsp_render_fence_observed(r->submitted_kick_seq);
}

int32_t hcu_bitmap_renderer_owner_fence_query(void *context, uint32_t ce_frame_index)
{
	hcu_bitmap_renderer *r = (hcu_bitmap_renderer *)context;
	(void)ce_frame_index;
	if (!r || !r->bound || !r->submitted) return -1;
	return bsp_render_fence_observed(r->submitted_kick_seq);
}

int32_t hcu_bitmap_renderer_begin_frame(hcu_bitmap_renderer *r, uint32_t frame_index)
{
	if (!r || !r->bound) return HCU_BITMAP_FRAME_E_ARGUMENT;
	if (r->frame_open) return HCU_BITMAP_FRAME_E_BUSY;
	if (r->submitted) {
		/* The previous frame's leases must be released by the owner before its
		 * slot is reused; a pending or unobserved fence refuses the new frame.
		 * Leases are released only through the owner's fence-complete path. */
		if (r->owner) {
			if (!r->owner->gpu_pending && r->dispatch->lease_count)
				return HCU_BITMAP_FRAME_E_BUSY;
			if (r->owner->gpu_pending &&
				hcu_bitmap_frame_owner_gpu_fence_complete(r->owner, r->owner->frame_index) != HCU_BITMAP_FRAME_OK)
				return HCU_BITMAP_FRAME_E_BUSY;
		} else if (hcu_bitmap_renderer_bsp_fence_query(r, r->frame_index) != 1) {
			return HCU_BITMAP_FRAME_E_BUSY;
		}
		r->submitted = 0;
	}
	r->frame_index = frame_index;
	r->frame_open = 1;
	return HCU_BITMAP_FRAME_OK;
}

/* Emit hook: binds the live chains for this build window only. */
int32_t hcu_bitmap_renderer_hook_emit(void *user, uint32_t frame, chain_t *geometry, chain_t *upload, tc_t *cache)
{
	hcu_bitmap_renderer *r = (hcu_bitmap_renderer *)user;
	if (!r || !r->bound || !r->frame_open || frame != r->frame_index) return HCU_BITMAP_FRAME_E_NOT_READY;
	if (!geometry || !upload || geometry == upload || !cache ||
		!geometry->base || !upload->base || geometry->cap_qw < 2 || upload->cap_qw < 2 ||
		geometry->overflow || upload->overflow || !aligned16(geometry->base) || !aligned16(upload->base))
		return HCU_BITMAP_FRAME_E_ARGUMENT;
	/* The actual tc_t is private to bsp_render and exists only in this hook.
	 * Bind its exact instance on first emit; a later replacement is rejected. */
	if (!r->cache) {
		if (r->dispatch->cache || cache->max_keys == 0 || cache->max_keys > r->cache_reader_count)
			return HCU_BITMAP_FRAME_E_NOT_READY;
		r->cache = cache;
		r->dispatch->cache = cache;
	} else if (cache != r->cache || r->dispatch->cache != cache) {
		return HCU_BITMAP_FRAME_E_ARGUMENT;
	}
	/* Idle capacity is what remains after the BSP packets; the dispatcher checks
	 * each append and rolls back on overflow (fail-closed). */
	r->dispatch->upload_chain = upload;
	r->dispatch->geometry_chain = geometry;
	if (r->owner) {
		/* port: dispatch the sealed CE batch into these live chains, then unbind them. Leases the drain already
		 * acquired stay held by the owner (gpu_pending) until the real kick fence; they are never released here. */
		int32_t status = hcu_bitmap_frame_owner_drain_pending(r->owner);
		r->dispatch->upload_chain = 0;
		r->dispatch->geometry_chain = 0;
		r->emit_status = status;
		if (status != HCU_BITMAP_FRAME_OK) r->emit_failures++;
		return status;
	}
	r->emit_status = HCU_BITMAP_FRAME_OK;
	return HCU_BITMAP_FRAME_OK;
}

int32_t hcu_bitmap_renderer_emit_status(const hcu_bitmap_renderer *r)
{
	return r ? r->emit_status : HCU_BITMAP_FRAME_E_ARGUMENT;
}

uint32_t hcu_bitmap_renderer_emit_failures(const hcu_bitmap_renderer *r)
{
	return r ? r->emit_failures : 0;
}

int32_t hcu_bitmap_renderer_hook_begin(void *user, uint32_t frame)
{
	return hcu_bitmap_renderer_begin_frame((hcu_bitmap_renderer *)user, frame) == HCU_BITMAP_FRAME_OK ? 0 : 1;
}

void hcu_bitmap_renderer_hook_submit(void *user, uint32_t frame, uint32_t kick_seq)
{
	(void)hcu_bitmap_renderer_submit_frame((hcu_bitmap_renderer *)user, frame, kick_seq);
}

int32_t hcu_bitmap_renderer_submit_frame(hcu_bitmap_renderer *r, uint32_t frame_index, uint32_t kick_seq)
{
	if (!r || !r->bound) return HCU_BITMAP_FRAME_E_ARGUMENT;
	/* Called for every kick; only a frame admitted by begin_frame is recorded. */
	if (!r->frame_open || frame_index != r->frame_index) return HCU_BITMAP_FRAME_OK;
	r->dispatch->upload_chain = 0;
	r->dispatch->geometry_chain = 0;
	r->submitted_kick_seq = kick_seq;
	r->submitted = 1;
	r->frame_open = 0;
	return HCU_BITMAP_FRAME_OK;
}
