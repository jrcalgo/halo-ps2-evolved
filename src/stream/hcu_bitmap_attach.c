/* port: EE-only attach/detach of the HCU bitmap adapter on the parent BSP renderer's frame hooks.
 * Host builds do not compile this file; the adapter itself is host-testable. */
#include <string.h>
#include "render/bsp_render.h"
#include "stream/hcu_bitmap_renderer.h"

/* The engine's hook table uses u32 and chain_t; these wrappers keep the exact engine signatures. */
static int32_t attach_begin(void *user, u32 frame)
{
	return hcu_bitmap_renderer_hook_begin(user, (uint32_t)frame);
}

static int32_t attach_emit(void *user, u32 frame, chain_t *geometry, chain_t *upload, tc_t *cache)
{
	return hcu_bitmap_renderer_hook_emit(user, (uint32_t)frame, geometry, upload, cache);
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
	return HCU_BITMAP_FRAME_OK;
}

int32_t hcu_bitmap_renderer_detach_frame(hcu_bitmap_renderer *r)
{
	if (!r || !r->bound) return HCU_BITMAP_FRAME_E_ARGUMENT;
	if (r->frame_open || (r->owner && r->owner->gpu_pending)) return HCU_BITMAP_FRAME_E_BUSY;
	bsp_render_set_frame_hooks(0);
	r->owner = 0;
	return HCU_BITMAP_FRAME_OK;
}
