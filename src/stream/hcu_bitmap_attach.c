/* port: EE-only attach/detach of the HCU bitmap adapter on the parent BSP renderer's frame hooks.
 * Host builds do not compile this file; the adapter itself is host-testable. */
#include <string.h>
#include "render/bsp_render.h"
#include "stream/hcu_bitmap_renderer.h"
#include "stream/hcu_render_snapshot.h"

static uint32_t s_frame_attachment_count;

uint32_t hcu_bitmap_renderer_attachment_count(void)
{
	return s_frame_attachment_count;
}

/* The engine's hook table uses u32 and chain_t; these wrappers keep the exact engine signatures. */
static int32_t attach_begin(void *user, u32 frame)
{
	hcu_bitmap_renderer *r = (hcu_bitmap_renderer *)user;
	if (r && r->dispatch) hcu_bitmap_dispatch_screen_effect_reset(r->dispatch);
	return hcu_bitmap_renderer_hook_begin(user, (uint32_t)frame);
}

/* port: C2.7 snapshot matrices are appended to the idle geometry chain before the bitmap drain, so they share the
 * build window with the BSP packets. The drain always runs, so a failed snapshot append does not seal the batch; the
 * failure is returned as this emit's status and counted by bsp_render_emit_failures. */
static int32_t attach_emit(void *user, u32 frame, chain_t *geometry, chain_t *upload, tc_t *cache)
{
	int snapshot_failed = 0;
	int32_t status;
	/* C3:chain begin */
	/* C3: the v1 double bank is never bound or published under HCU_C3_FRAME_SNAPSHOT (the v2 bank
	 * replaces it in frame_scratch), so hcu_render_snapshot_latest() is NULL and the v1 matrix append
	 * always fails, which every baseline frame reported as E_QUEUE (emit-status=-6). Under C3 the
	 * object matrices reach the idle geometry chain through the object pass, so the v1 append is
	 * skipped and no failure is counted for it. */
#if !defined(HCU_C3_FRAME_SNAPSHOT)
	snapshot_failed = geometry && hcu_render_snapshot_emit_chain(geometry) < 0;
#endif
	/* C3:chain end */
	status = hcu_bitmap_renderer_hook_emit(user, (uint32_t)frame, geometry, upload, cache);
	return snapshot_failed ? HCU_BITMAP_FRAME_E_QUEUE : status;
}

static void attach_submit(void *user, u32 frame, u32 kick_seq)
{
	hcu_bitmap_renderer_hook_submit(user, (uint32_t)frame, (uint32_t)kick_seq);
}

/* The native hook runs after the world pass and before the bitmap drain. Acquire
 * the sealed CE queue here so screen parameters are available to an installed
 * GS backend before it appends any native effect packets. */
static int32_t attach_screen_effect(void *user, u32 frame, const video_t *video,
	chain_t *geometry, chain_t *upload, tc_t *cache)
{
	hcu_bitmap_renderer *r = (hcu_bitmap_renderer *)user;
	halo_ps2_bitmap_request_reader reader;
	int32_t backend_status;
	uint32_t view;
	(void)frame;
	if (!r || !r->owner || !r->owner->queue || !r->dispatch || !r->screen_effect_backend ||
		!video || !geometry || !upload || !cache)
		return -1;
	if (!r->cache) {
		if (r->dispatch->cache || !cache->max_keys || cache->max_keys > r->cache_reader_count)
			return -1;
		r->cache = cache;
		r->dispatch->cache = cache;
	} else if (r->cache != cache || r->dispatch->cache != cache) {
		return -1;
	}
	r->dispatch->geometry_chain = geometry;
	r->dispatch->upload_chain = upload;
	memset(&reader, 0, sizeof(reader));
	if (halo_ps2_bitmap_requests_acquire(r->owner->queue, r->owner->generation, &reader) !=
		HALO_PS2_BITMAP_REQUEST_OK)
		return 0; /* No sealed CE effect batch for this parent build. */
	if (hcu_bitmap_dispatch_capture_screen_effects(r->dispatch, reader.queue) != HCU_BITMAP_DISPATCH_OK) {
		halo_ps2_bitmap_requests_release(&reader);
		return -1;
	}
	for (view = 0; view < HALO_PS2_BITMAP_MAX_VIEWS; ++view) {
		halo_ps2_screen_effect_state state;
		uint64_t tex0, clamp;
		int32_t captured = hcu_bitmap_dispatch_screen_effect_get(r->dispatch,
			reader.generation, reader.queue->frame_index, (uint16_t)view, &state);
		if (captured < 0) {
			halo_ps2_bitmap_requests_release(&reader);
			return -1;
		}
		if (!captured) continue;
		if (hcu_bitmap_dispatch_prepare_screen_effect_mask(r->dispatch, &reader,
			state.mask_request_index, &tex0, &clamp) != HCU_BITMAP_DISPATCH_OK) {
			halo_ps2_bitmap_requests_release(&reader);
			return -1;
		}
	}
	backend_status = r->screen_effect_backend(r->screen_effect_backend_user, &reader,
		r->dispatch, video, geometry, upload, cache);
	r->dispatch->screen_effect_backend_active = backend_status > 0;
	halo_ps2_bitmap_requests_release(&reader);
	return backend_status < 0 ? backend_status : 0;
}

int32_t hcu_bitmap_renderer_attach_frame(hcu_bitmap_renderer *r, hcu_bitmap_frame_owner *owner)
{
	bsp_render_frame_hooks hooks;
	if (!r || !r->bound || !owner || !owner->bound || r->owner || owner->fence_query !=
		hcu_bitmap_renderer_owner_fence_query || owner->fence_context != r)
		return HCU_BITMAP_FRAME_E_ARGUMENT;
	memset(&hooks, 0, sizeof hooks);
	hooks.begin = attach_begin;
	if (r->screen_effect_backend) hooks.screen_effect = attach_screen_effect;
	hooks.emit = attach_emit;
	hooks.submit = attach_submit;
	hooks.user = r;
	r->owner = owner;
	bsp_render_set_frame_hooks(&hooks);
	s_frame_attachment_count++;
	return HCU_BITMAP_FRAME_OK;
}

int32_t hcu_bitmap_renderer_set_screen_effect_backend(hcu_bitmap_renderer *r,
	hcu_bitmap_screen_effect_backend_fn backend, void *backend_user)
{
	if (!r || !r->bound) return HCU_BITMAP_FRAME_E_ARGUMENT;
	if (r->owner || r->frame_open || r->submitted || (r->owner && r->owner->gpu_pending))
		return HCU_BITMAP_FRAME_E_BUSY;
	r->screen_effect_backend = backend;
	r->screen_effect_backend_user = backend ? backend_user : 0;
	return HCU_BITMAP_FRAME_OK;
}

int32_t hcu_bitmap_renderer_detach_frame(hcu_bitmap_renderer *r)
{
	if (!r || !r->bound) return HCU_BITMAP_FRAME_E_ARGUMENT;
	if (r->frame_open || (r->owner && r->owner->gpu_pending)) return HCU_BITMAP_FRAME_E_BUSY;
	bsp_render_set_frame_hooks(0);
	r->owner = 0;
	if (s_frame_attachment_count)
		s_frame_attachment_count--;
	return HCU_BITMAP_FRAME_OK;
}
