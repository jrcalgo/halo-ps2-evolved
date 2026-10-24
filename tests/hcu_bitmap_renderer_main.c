/* Host test for the parent-renderer adapter. The real chain and texture-cache
 * code is linked; only the per-kick EE fence observation is stubbed. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "stream/hcu_bitmap_renderer.h"
#include "render/chain.h"
#include "render/texcache.h"

static int32_t s_fence_result;      /* what bsp_render_fence_observed returns */
static uint32_t s_fence_last_seq;
static int s_fence_calls;

int32_t bsp_render_fence_observed(uint32_t kick_seq)
{
	s_fence_calls++;
	s_fence_last_seq = kick_seq;
	return s_fence_result;
}

/* The owner's lease gate is covered by tests/hcu_bitmap_fence_main.c; the adapter only calls these two. */
int32_t hcu_bitmap_frame_owner_drain_pending(hcu_bitmap_frame_owner *owner)
{
	(void)owner;
	return HCU_BITMAP_FRAME_OK;
}
hcu_bitmap_frame_status hcu_bitmap_frame_owner_gpu_fence_complete(hcu_bitmap_frame_owner *owner, uint32_t frame_index)
{
	(void)owner; (void)frame_index;
	return HCU_BITMAP_FRAME_OK;
}

static int failures;
#define CHECK(cond) do { if (!(cond)) { printf("FAIL %s:%d %s\n", __FILE__, __LINE__, #cond); failures++; } } while (0)

static uint8_t s_geom_mem[64 * 16] __attribute__((aligned(16)));
static uint8_t s_upl_mem[64 * 16] __attribute__((aligned(16)));
static uint8_t s_geom2_mem[64 * 16] __attribute__((aligned(16)));
static uint8_t s_upl2_mem[64 * 16] __attribute__((aligned(16)));
static uint16_t s_readers[TC_MAX_KEYS];
static uint8_t s_source[4 * 256] __attribute__((aligned(16)));
static uint8_t s_staging[256] __attribute__((aligned(16)));
static hcu_bitmap_source_slot s_slots[4];
static hcu_bitmap_lease s_leases[4];
static tc_t s_cache;
static tc_t s_cache_backup;
static hcu_bitmap_dispatch_context s_dispatch;
static hcu_bitmap_renderer s_r;

static void setup(void)
{
	memset(&s_dispatch, 0, sizeof s_dispatch);
	memset(s_readers, 0, sizeof s_readers);
	memset(s_slots, 0, sizeof s_slots);
	memset(s_leases, 0, sizeof s_leases);
	tc_init(&s_cache, 64, 8, 16, 1536u * 1024u);
	s_dispatch.cache = &s_cache;
	s_dispatch.cache_readers = s_readers;
	s_dispatch.cache_reader_count = TC_MAX_KEYS;
	s_dispatch.source_storage = s_source;
	s_dispatch.source_storage_bytes = sizeof s_source;
	s_dispatch.slot_stride = 256;
	s_dispatch.staging_buffer = s_staging;
	s_dispatch.staging_buffer_bytes = sizeof s_staging;
	s_dispatch.slots = s_slots;
	s_dispatch.slot_count = 4;
	s_dispatch.leases = s_leases;
	s_dispatch.lease_capacity = 4;
}

static int32_t init_ok(void)
{
	return hcu_bitmap_renderer_init(&s_r, &s_dispatch, &s_cache, s_readers, TC_MAX_KEYS,
		s_source, sizeof s_source, 256, s_staging, sizeof s_staging, s_slots, 4,
		s_leases, 4, 0, 0, 640, 448);
}

int main(void)
{
	chain_t geom, upl, geom2, upl2;
	setup();

	/* unbound renderer: nothing is admitted and the fence refuses */
	CHECK(hcu_bitmap_renderer_hook_begin(&s_r, 0) == 1);
	CHECK(hcu_bitmap_renderer_bsp_fence_query(&s_r, 0) == -1);

	/* init fails closed on a mismatched dispatch context and on a too-small reader array */
	CHECK(hcu_bitmap_renderer_init(&s_r, &s_dispatch, &s_cache, s_readers, 1, s_source, sizeof s_source, 256,
		s_staging, sizeof s_staging, s_slots, 4, s_leases, 4, 0, 0, 640, 448) == HCU_BITMAP_FRAME_E_ARGUMENT);
	s_dispatch.slot_stride = 128;
	CHECK(init_ok() == HCU_BITMAP_FRAME_E_NOT_READY);
	s_dispatch.slot_stride = 256;
	CHECK(init_ok() == HCU_BITMAP_FRAME_OK);
	CHECK(s_r.bound == 1 && s_dispatch.screen_w == 640);

	chain_init(&geom, s_geom_mem, 64);
	chain_init(&upl, s_upl_mem, 64);
	chain_init(&geom2, s_geom2_mem, 64);
	chain_init(&upl2, s_upl2_mem, 64);

	/* frame 5 admitted; emit only for that frame and only with the cache it was bound to */
	CHECK(hcu_bitmap_renderer_begin_frame(&s_r, 5) == HCU_BITMAP_FRAME_OK);
	CHECK(hcu_bitmap_renderer_begin_frame(&s_r, 6) == HCU_BITMAP_FRAME_E_BUSY);
	CHECK(hcu_bitmap_renderer_hook_emit(&s_r, 4, &geom, &upl, &s_cache) == HCU_BITMAP_FRAME_E_NOT_READY);
	CHECK(hcu_bitmap_renderer_hook_emit(&s_r, 5, &geom, &upl, &s_cache_backup) == HCU_BITMAP_FRAME_E_ARGUMENT);
	CHECK(hcu_bitmap_renderer_hook_emit(&s_r, 5, &geom, &geom, &s_cache) == HCU_BITMAP_FRAME_E_ARGUMENT);
	CHECK(hcu_bitmap_renderer_hook_emit(&s_r, 5, &geom, &upl, &s_cache) == HCU_BITMAP_FRAME_OK);
	CHECK(s_dispatch.geometry_chain == &geom && s_dispatch.upload_chain == &upl);

	/* a kick for a frame that was never begun is ignored */
	hcu_bitmap_renderer_hook_submit(&s_r, 9, 77);
	CHECK(s_r.submitted == 0);
	CHECK(hcu_bitmap_renderer_bsp_fence_query(&s_r, 5) == -1);

	/* submit records the kick; the fence follows the real per-kick observation */
	hcu_bitmap_renderer_hook_submit(&s_r, 5, 7);
	CHECK(s_r.submitted == 1 && s_dispatch.geometry_chain == 0 && s_dispatch.upload_chain == 0);
	s_fence_result = 0;
	CHECK(hcu_bitmap_renderer_bsp_fence_query(&s_r, 5) == 0);
	CHECK(s_fence_last_seq == 7);
	CHECK(hcu_bitmap_renderer_bsp_fence_query(&s_r, 4) == -1);      /* wrong frame never reaches the EE fence */
	s_fence_result = -1;                                           /* a later kick superseded it */
	CHECK(hcu_bitmap_renderer_bsp_fence_query(&s_r, 5) == -1);
	CHECK(hcu_bitmap_renderer_begin_frame(&s_r, 6) == HCU_BITMAP_FRAME_E_BUSY);   /* pending fence blocks reuse */

	/* completed fence admits the next frame; emit rebinds to the other chain pair */
	s_fence_result = 1;
	CHECK(hcu_bitmap_renderer_bsp_fence_query(&s_r, 5) == 1);
	CHECK(hcu_bitmap_renderer_hook_begin(&s_r, 6) == 0);
	CHECK(hcu_bitmap_renderer_hook_emit(&s_r, 6, &geom2, &upl2, &s_cache) == HCU_BITMAP_FRAME_OK);
	CHECK(s_dispatch.geometry_chain == &geom2);
	hcu_bitmap_renderer_hook_submit(&s_r, 6, 8);
	CHECK(s_r.submitted_kick_seq == 8 && s_r.frame_index == 6);

	/* a second submit for the same frame after completion is a no-op for the adapter state */
	CHECK(hcu_bitmap_renderer_submit_frame(&s_r, 6, 9) == HCU_BITMAP_FRAME_OK);
	printf("%s: %d failure(s), %d fence call(s)\n", failures ? "FAILED" : "PASSED", failures, s_fence_calls);
	return failures ? 1 : 0;
}
