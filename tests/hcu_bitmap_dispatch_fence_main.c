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
	hcu_bitmap_source_slot slots[1];
	hcu_bitmap_lease leases[1];
	uint16_t readers[1];
	memset(&ctx, 0, sizeof(ctx));
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
