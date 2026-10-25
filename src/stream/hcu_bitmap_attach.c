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

int32_t hcu_bitmap_renderer_attach_frame(hcu_bitmap_renderer *r, hcu_bitmap_frame_owner *owner)
{
	bsp_render_frame_hooks hooks;
	if (!r || !r->bound || !owner || !owner->bound || r->owner || owner->fence_query !=
		hcu_bitmap_renderer_owner_fence_query || owner->fence_context != r)
		return HCU_BITMAP_FRAME_E_ARGUMENT;
	memset(&hooks, 0, sizeof hooks);
	hooks.begin = attach_begin;
	hooks.emit = attach_emit;
	hooks.submit = attach_submit;
	hooks.user = r;
	r->owner = owner;
	bsp_render_set_frame_hooks(&hooks);
	s_frame_attachment_count++;
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
