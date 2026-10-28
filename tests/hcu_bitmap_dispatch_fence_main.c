#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include "stream/hcu_bitmap_dispatch.h"

static int32_t s_fence_result;
static int32_t s_source_release_result = 1;
static uint32_t s_fence_calls, s_release_calls;

int32_t bsp_render_fence_observed(uint32_t kick_seq)
{
	s_fence_calls++;
	return kick_seq == 23u ? s_fence_result : -1;
}

int32_t bsp_render_source_release(uint32_t kind, uint32_t kick_seq)
{
	s_release_calls++;
	if (kind != 2u || bsp_render_fence_observed(kick_seq) != 1) return -1;
	return s_source_release_result;
}

int main(void)
{
	hcu_bitmap_dispatch_context ctx;
	halo_ps2_bitmap_request_queue queue;
	halo_ps2_screen_effect_state state;
	uint64_t screen_mask_tex0, screen_mask_clamp;
	hcu_bitmap_source_slot slots[1];
	hcu_bitmap_lease leases[1];
	uint16_t readers[1];
	memset(&ctx, 0, sizeof(ctx));
	memset(&queue, 0, sizeof(queue));
	ctx.expected_generation = 91u;
	queue.closed = 1; queue.generation = 91u; queue.frame_index = 44u; queue.readers = 1u;
	queue.screen_effects[1].valid = 1u;
	queue.screen_effects[1].convolution_type = 2;
	queue.screen_effects[1].convolution_radius = 0.375f;
	queue.screen_effects[1].convolution_extra_passes = 4;
	queue.screen_effects[1].light_enhancement_intensity = 0.75f;
	queue.screen_effects[1].desaturation_intensity = 0.25f;
	queue.screen_effects[1].desaturation_tint[0] = 0.125f;
	queue.screen_effects[1].desaturation_tint[1] = 0.5f;
	queue.screen_effects[1].desaturation_tint[2] = 0.875f;
	queue.screen_effects[1].desaturation_is_additive = 1u;
	queue.screen_effects[1].light_uses_mask = 1u;
	queue.screen_effects[1].desaturation_uses_mask = 1u;
	queue.screen_effects[1].video_on = 1u;
	queue.screen_effects[1].mask_request_index = 3u;
	if (hcu_bitmap_dispatch_capture_screen_effects(&ctx, &queue) != HCU_BITMAP_DISPATCH_OK ||
		ctx.screen_effect_backend_active ||
		hcu_bitmap_dispatch_screen_effect_get(&ctx, 91u, 44u, 1u, &state) != 1 ||
		state.convolution_type != 2 || state.convolution_radius != 0.375f ||
		state.convolution_extra_passes != 4 || state.light_enhancement_intensity != 0.75f ||
		state.desaturation_intensity != 0.25f || state.desaturation_tint[0] != 0.125f ||
		state.desaturation_tint[1] != 0.5f || state.desaturation_tint[2] != 0.875f ||
		!state.desaturation_is_additive || !state.light_uses_mask ||
		!state.desaturation_uses_mask || !state.video_on || state.mask_request_index != 3u ||
		hcu_bitmap_dispatch_screen_effect_mask_get(&ctx, 91u, 44u, 1u,
			&screen_mask_tex0, &screen_mask_clamp) != 0 ||
		hcu_bitmap_dispatch_screen_effect_get(&ctx, 91u, 45u, 1u, &state) != HCU_BITMAP_DISPATCH_E_VIEW)
		return 5;
	/* Model the pre-HUD native hook marking work applied. The later queue drain
	 * sees the same frame and must not clear that result or replace its inputs. */
	ctx.screen_effect_backend_active = 1u;
	if (hcu_bitmap_dispatch_capture_screen_effects(&ctx, &queue) != HCU_BITMAP_DISPATCH_OK ||
		!ctx.screen_effect_backend_active ||
		hcu_bitmap_dispatch_screen_effect_get(&ctx, 91u, 44u, 1u, &state) != 1 ||
		state.mask_request_index != 3u) return 6;
	hcu_bitmap_dispatch_screen_effect_reset(&ctx);
	if (hcu_bitmap_dispatch_screen_effect_get(&ctx, 91u, 44u, 1u, &state) != HCU_BITMAP_DISPATCH_E_VIEW ||
		hcu_bitmap_dispatch_capture_screen_effects(&ctx, &queue) != HCU_BITMAP_DISPATCH_OK)
		return 7;
	memset(slots, 0, sizeof(slots));
	memset(leases, 0, sizeof(leases));
	memset(readers, 0, sizeof(readers));
	slots[0].valid = 1;
	slots[0].cache_key = 0;
	slots[0].storage_bytes = 64;
	slots[0].readers = 1;
	readers[0] = 1;
	leases[0].slot = 0;
	leases[0].cache_key = 0;
	leases[0].kick_seq = 23;
	leases[0].active = 1;
	ctx.slots = slots;
	ctx.slot_count = 1;
	ctx.cache_readers = readers;
	ctx.cache_reader_count = 1;
	ctx.leases = leases;
	ctx.lease_capacity = 1;
	ctx.lease_count = 1;
	s_fence_result = 0;
	if (hcu_bitmap_dispatch_complete(&ctx) != HCU_BITMAP_DISPATCH_E_BUSY ||
		ctx.lease_count != 1 || !leases[0].active || !slots[0].valid ||
		slots[0].readers != 1 || readers[0] != 1 || s_release_calls != 0) return 1;
	s_fence_result = -1;
	if (hcu_bitmap_dispatch_complete(&ctx) != HCU_BITMAP_DISPATCH_E_BUSY ||
		ctx.lease_count != 1 || !leases[0].active || readers[0] != 1 || s_release_calls != 0) return 2;
	s_fence_result = 1;
	s_source_release_result = 0;
	if (hcu_bitmap_dispatch_complete(&ctx) != HCU_BITMAP_DISPATCH_E_BUSY ||
		ctx.lease_count != 1 || !leases[0].active || !slots[0].valid || readers[0] != 1 || s_release_calls != 1)
		return 3;
	s_source_release_result = 1;
	if (hcu_bitmap_dispatch_complete(&ctx) != HCU_BITMAP_DISPATCH_OK ||
		ctx.lease_count != 0 || leases[0].active || slots[0].valid || readers[0] || s_release_calls != 2)
		return 4;
	printf("bitmap-dispatch-fence-ok fences=%u releases=%u\n", s_fence_calls, s_release_calls);
	return 0;
}
