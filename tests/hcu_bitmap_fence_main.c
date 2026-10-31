/* Host test: the real fence sequencing (render/bsp_fence_seq.h, the same functions bsp_render.c calls), the
 * adapter, and the frame owner's lease gating. The EE renderer, GS and DMA are simulated by the kick helper. */
#include <stdio.h>
#include <string.h>
#include "render/bsp_fence_seq.h"
#include "stream/hcu_bitmap_renderer.h"
#include "halo_ps2_bitmap_frame.h"

/* ---- simulated parent renderer (mirrors bsp_render.c's state machine) ---- */
static uint32_t s_kick_seq, s_completed;
static int s_vif_seen, s_gs_seen;
static int s_fence_calls;

int32_t bsp_render_fence_observed(uint32_t kick_seq)
{
	s_fence_calls++;
	s_completed = bsp_fence_seq_retire(s_completed, s_kick_seq, s_vif_seen, s_gs_seen);
	return bsp_fence_seq_query(s_completed, s_kick_seq, kick_seq, s_vif_seen, s_gs_seen);
}

/* A kick as bsp_render_kick does it: retire the previous kick, reset observations, start the new one. */
static void sim_kick(int previous_observed)
{
	s_completed = bsp_fence_seq_retire(s_completed, s_kick_seq, s_vif_seen, s_gs_seen);
	s_vif_seen = s_gs_seen = 0;
	s_kick_seq++;
	/* the GS/VIF of the new kick are polled later; `previous_observed` is what wait_gpu saw for the old one */
	(void)previous_observed;
}

/* ---- stubs for the CE request queue and the dispatcher (only the owner's lease gate is under test) ---- */
static int s_fail_dispatch;   /* when set, the dispatcher acquires one lease and then fails (E_DISPATCH) */
hcu_bitmap_dispatch_status hcu_bitmap_dispatch_complete(hcu_bitmap_dispatch_context *c)
{
	c->lease_count = 0;
	return HCU_BITMAP_DISPATCH_OK;
}
int hcu_bitmap_dispatch_reader(const halo_ps2_bitmap_request_reader *reader, void *context)
{
	hcu_bitmap_dispatch_context *ctx = (hcu_bitmap_dispatch_context *)context;
	(void)reader;
	if (s_fail_dispatch) {
		ctx->leases[0].active = 1;
		ctx->lease_count = 1;
		return HCU_BITMAP_FRAME_E_DISPATCH;
	}
	return 0;
}
halo_ps2_bitmap_request_status halo_ps2_bitmap_requests_register_consumer(halo_ps2_bitmap_request_queue *q,
	halo_ps2_bitmap_request_consumer c, void *ctx) { (void)q; (void)c; (void)ctx; return HALO_PS2_BITMAP_REQUEST_OK; }
halo_ps2_bitmap_request_status halo_ps2_bitmap_requests_clear_consumer(halo_ps2_bitmap_request_queue *q)
{ (void)q; return HALO_PS2_BITMAP_REQUEST_OK; }
halo_ps2_bitmap_request_status halo_ps2_bitmap_requests_begin(halo_ps2_bitmap_request_queue *q, uint32_t f,
	uint32_t g, int16_t v, int16_t p) { (void)q; (void)f; (void)g; (void)v; (void)p; return HALO_PS2_BITMAP_REQUEST_OK; }
halo_ps2_bitmap_request_status halo_ps2_bitmap_requests_set_view(halo_ps2_bitmap_request_queue *q, int16_t v, int16_t p)
{ (void)q; (void)v; (void)p; return HALO_PS2_BITMAP_REQUEST_OK; }
halo_ps2_bitmap_request_status halo_ps2_bitmap_requests_end(halo_ps2_bitmap_request_queue *q)
{ (void)q; return HALO_PS2_BITMAP_REQUEST_OK; }
halo_ps2_bitmap_request_status halo_ps2_bitmap_requests_acquire(halo_ps2_bitmap_request_queue *q, uint32_t g,
	halo_ps2_bitmap_request_reader *r)
{ (void)q; (void)g; memset(r, 0, sizeof *r); r->held = 1; return HALO_PS2_BITMAP_REQUEST_OK; }
void halo_ps2_bitmap_requests_release(halo_ps2_bitmap_request_reader *r) { memset(r, 0, sizeof *r); }
int32_t halo_ps2_bitmap_frame_consumer_register(halo_ps2_bitmap_frame_consumer const *c) { (void)c; return 0; }
int32_t halo_ps2_bitmap_frame_consumer_clear(void) { return 0; }
int32_t halo_ps2_bitmap_frame_is_active(void) { return 0; }

static int failures;
#define CHECK(cond) do { if (!(cond)) { printf("FAIL %s:%d %s\n", __FILE__, __LINE__, #cond); failures++; } } while (0)

static uint8_t s_source[4 * 256] __attribute__((aligned(16)));
static uint8_t s_staging[256] __attribute__((aligned(16)));
static hcu_bitmap_source_slot s_slots[4];
static hcu_bitmap_lease s_leases[4];
static uint16_t s_readers[TC_MAX_KEYS];
static uint8_t s_geom_mem[64 * 16] __attribute__((aligned(16)));
static uint8_t s_upl_mem[64 * 16] __attribute__((aligned(16)));
static tc_t s_cache;
static hcu_bitmap_dispatch_context s_dispatch;
static hcu_bitmap_renderer s_r;
static halo_ps2_bitmap_request_queue s_queue;
static hcu_bitmap_frame_owner s_owner;

int main(void)
{
	chain_t geom, upl;
	memset(&s_dispatch, 0, sizeof s_dispatch);
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
	CHECK(hcu_bitmap_renderer_init(&s_r, &s_dispatch, &s_cache, s_readers, TC_MAX_KEYS, s_source, sizeof s_source,
		256, s_staging, sizeof s_staging, s_slots, 4, s_leases, 4, 0, 0, 640, 448) == HCU_BITMAP_FRAME_OK);
	chain_init(&geom, s_geom_mem, 64);
	chain_init(&upl, s_upl_mem, 64);

	/* A. frame 5 admitted and submitted as kick 1; the next frame is refused while kick 1 is pending. */
	CHECK(hcu_bitmap_renderer_begin_frame(&s_r, 5) == HCU_BITMAP_FRAME_OK);
	CHECK(hcu_bitmap_renderer_hook_emit(&s_r, 5, &geom, &upl, &s_cache) == HCU_BITMAP_FRAME_OK);
	sim_kick(0);
	hcu_bitmap_renderer_hook_submit(&s_r, 5, s_kick_seq);
	CHECK(s_kick_seq == 1 && s_r.submitted_kick_seq == 1);
	CHECK(hcu_bitmap_renderer_begin_frame(&s_r, 6) == HCU_BITMAP_FRAME_E_BUSY);

	/* B. skip-then-kick: frame 6 was refused, so the renderer kicks without an admitted frame (kick 2). Kick 1
	 * was never observed, so the fence is -1 and the adapter fails closed; nothing is released. */
	sim_kick(0);
	CHECK(bsp_render_fence_observed(1) == -1);
	CHECK(hcu_bitmap_renderer_begin_frame(&s_r, 7) == HCU_BITMAP_FRAME_E_BUSY);
	CHECK(s_r.submitted == 1);

	/* C. kick 2 is observed before kick 3 (wait_gpu order). The retire records it; kick 1 is then complete and the
	 * next frame is admitted. */
	s_vif_seen = s_gs_seen = 1;
	sim_kick(1);                                  /* retires kick 2 */
	CHECK(bsp_render_fence_observed(2) == 1);
	CHECK(hcu_bitmap_renderer_begin_frame(&s_r, 7) == HCU_BITMAP_FRAME_OK);
	CHECK(s_r.submitted == 0);

	/* D. lease gate: frame 7 owns a lease from kick 3. Kick 4 supersedes kick 3 before it is observed (-1). The
	 * owner must refuse and keep the lease; begin must refuse too. */
	memset(&s_owner, 0, sizeof s_owner);
	memset(&s_queue, 0, sizeof s_queue);
	s_owner.bound = 1;
	s_owner.queue = &s_queue;
	s_owner.dispatch = &s_dispatch;
	s_owner.fence_query = hcu_bitmap_renderer_owner_fence_query;
	s_owner.fence_context = &s_r;
	s_owner.frame_index = 7;
	s_owner.gpu_pending = 1;
	s_dispatch.lease_count = 1;
	s_leases[0].active = 1;
	s_r.owner = &s_owner;
	s_r.frame_open = 0;
	s_r.submitted = 1;
	s_r.frame_index = 7;
	s_r.submitted_kick_seq = s_kick_seq;          /* kick 3 */
	sim_kick(0);                                  /* kick 4: kick 3 unobserved */
	CHECK(bsp_render_fence_observed(3) == -1);
	CHECK(hcu_bitmap_frame_owner_gpu_fence_complete(&s_owner, 7) == HCU_BITMAP_FRAME_E_FENCE);
	CHECK(s_dispatch.lease_count == 1 && s_owner.gpu_pending == 1);
	CHECK(hcu_bitmap_renderer_begin_frame(&s_r, 8) == HCU_BITMAP_FRAME_E_BUSY);
	CHECK(s_dispatch.lease_count == 1 && s_leases[0].active == 1);

	/* E. kick 4 observed: the owner releases through its own path only, then the next frame is admitted. */
	s_vif_seen = s_gs_seen = 1;
	s_r.submitted_kick_seq = s_kick_seq;
	CHECK(bsp_render_fence_observed(s_kick_seq) == 1);
	CHECK(hcu_bitmap_frame_owner_gpu_fence_complete(&s_owner, 7) == HCU_BITMAP_FRAME_OK);
	CHECK(s_dispatch.lease_count == 0 && s_owner.gpu_pending == 0);
	CHECK(hcu_bitmap_renderer_begin_frame(&s_r, 8) == HCU_BITMAP_FRAME_OK);

	/* F. deferred drain: CE sealed a batch with no emit window (pending), a drain without chains is refused, and
	 * the emit window drains it into the live chains and clears them. */
	s_owner.drain_pending = 1;
	s_queue.closed = 1;
	CHECK(hcu_bitmap_frame_owner_drain_pending(&s_owner) == HCU_BITMAP_FRAME_E_NOT_READY);
	CHECK(hcu_bitmap_renderer_hook_emit(&s_r, 8, &geom, &upl, &s_cache) == HCU_BITMAP_FRAME_OK);
	CHECK(s_owner.drain_pending == 0);
	CHECK(s_dispatch.geometry_chain == 0 && s_dispatch.upload_chain == 0);
	CHECK(s_r.emit_status == HCU_BITMAP_FRAME_OK && hcu_bitmap_renderer_emit_failures(&s_r) == 0);

	/* G. failed drain after a lease was acquired (E_DISPATCH): the failure is recorded in the renderer and the
	 * owner, and the acquired lease stays held (gpu_pending) until a real fence. */
	s_owner.drain_pending = 1;
	s_fail_dispatch = 1;
	CHECK(hcu_bitmap_renderer_hook_emit(&s_r, 8, &geom, &upl, &s_cache) == HCU_BITMAP_FRAME_E_DISPATCH);
	CHECK(hcu_bitmap_renderer_emit_status(&s_r) == HCU_BITMAP_FRAME_E_DISPATCH);
	CHECK(hcu_bitmap_renderer_emit_failures(&s_r) == 1);
	CHECK(s_owner.last_status == HCU_BITMAP_FRAME_E_DISPATCH);
	CHECK(s_owner.drain_pending == 0 && s_owner.gpu_pending == 1);
	CHECK(s_dispatch.lease_count == 1 && s_leases[0].active == 1);
	CHECK(s_dispatch.geometry_chain == 0 && s_dispatch.upload_chain == 0);
	CHECK(hcu_bitmap_frame_owner_gpu_fence_complete(&s_owner, 7) == HCU_BITMAP_FRAME_E_FENCE);   /* no kick submitted yet */
	CHECK(s_dispatch.lease_count == 1 && s_leases[0].active == 1);                                 /* still held */

	/* H. a fatally faulted sealed batch (window-count mismatch) is dropped whole and counted: the emit window reports OK so
	 * the CE frame keeps rendering, no emit failure is recorded, nothing stays pending and no lease is acquired. */
	s_fail_dispatch = 0;
	s_owner.view_call_count = s_owner.active_window_count + 1u;
	s_owner.drain_pending = 1;
	s_owner.gpu_pending = 0;
	s_dispatch.lease_count = 0;
	s_leases[0].active = 0;
	{
		uint32_t drops_before = s_owner.stat_drops;
		CHECK(hcu_bitmap_renderer_hook_emit(&s_r, 8, &geom, &upl, &s_cache) == HCU_BITMAP_FRAME_OK);
		CHECK(hcu_bitmap_renderer_emit_status(&s_r) == HCU_BITMAP_FRAME_OK);
		CHECK(s_owner.stat_drops == drops_before + 1);                 /* drop is counted */
		CHECK(s_owner.last_drop_cause == 32u);                         /* bit 5: view-count mismatch */
		CHECK((s_owner.drop_causes_seen & 32u) != 0);
		CHECK(s_owner.drain_pending == 0 && s_owner.gpu_pending == 0); /* nothing stays pending */
		CHECK(s_dispatch.lease_count == 0 && s_leases[0].active == 0);
		CHECK(s_dispatch.geometry_chain == 0 && s_dispatch.upload_chain == 0);
		CHECK(hcu_bitmap_renderer_emit_failures(&s_r) == 1);           /* only the G failure */
	}
	s_owner.view_call_count = s_owner.active_window_count;
	CHECK(hcu_bitmap_renderer_hook_emit(&s_r, 8, &geom, &upl, &s_cache) == HCU_BITMAP_FRAME_OK);
	CHECK(hcu_bitmap_renderer_emit_status(&s_r) == HCU_BITMAP_FRAME_OK);
	CHECK(hcu_bitmap_renderer_emit_failures(&s_r) == 1);
	/* I. the following CE frame starts clean after the whole faulted batch was discarded. */
	s_r.frame_open = 0; /* previous frame's parent submit boundary */
	CHECK(hcu_bitmap_renderer_begin_frame(&s_r, 9) == HCU_BITMAP_FRAME_OK);
	CHECK(s_owner.frame_dropped == 1 && s_owner.last_drop_cause == 32u);
	CHECK(!s_owner.in_frame && !s_owner.drain_pending && !s_owner.gpu_pending && !s_dispatch.lease_count);

	printf("%s: %d failure(s), %d fence call(s)\n", failures ? "FAILED" : "PASSED", failures, s_fence_calls);
	return failures ? 1 : 0;
}
