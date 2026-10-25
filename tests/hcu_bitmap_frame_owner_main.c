#include "stream/hcu_bitmap_frame.h"
#include "halo_ps2_bitmap_frame.h"
#include "render/chain.h"
#include <stdio.h>
#include <string.h>

#ifndef HALO_PS2_BITMAP_FRAME_TEST_CAPS
#define HALO_PS2_BITMAP_FRAME_TEST_CAPS 3u
#endif

const halo_ps2_bitmap_real_producer_descriptor halo_ps2_real_producer_descriptor_instance = {
	HALO_PS2_BITMAP_REAL_PRODUCER_MAGIC,
	HALO_PS2_BITMAP_REAL_PRODUCER_VERSION,
	HALO_PS2_BITMAP_FRAME_TEST_CAPS
};

static halo_ps2_bitmap_frame_consumer s_frame_consumer;
static int s_frame_registered, s_dispatch_complete_calls, s_dispatch_calls;
static int s_fence_observed;

static int32_t fake_fence_query(void *context, uint32_t frame_index)
{
	(void)context;
	return ((frame_index == 10 || frame_index == 12) && s_fence_observed) ? 1 : 0;
}

halo_ps2_bitmap_request_status halo_ps2_bitmap_requests_register_consumer(
	halo_ps2_bitmap_request_queue *q, halo_ps2_bitmap_request_consumer cb, void *ctx)
{
	if (!q || q->open || q->readers || !cb) return HALO_PS2_BITMAP_REQUEST_BUSY;
	q->consumer = cb; q->consumer_context = ctx; return HALO_PS2_BITMAP_REQUEST_OK;
}
halo_ps2_bitmap_request_status halo_ps2_bitmap_requests_clear_consumer(halo_ps2_bitmap_request_queue *q)
{
	if (!q || q->open || q->readers) return HALO_PS2_BITMAP_REQUEST_BUSY;
	q->consumer = 0; q->consumer_context = 0; return HALO_PS2_BITMAP_REQUEST_OK;
}
halo_ps2_bitmap_request_status halo_ps2_bitmap_requests_begin(
	halo_ps2_bitmap_request_queue *q, uint32_t frame, uint32_t gen, int16_t view, int16_t player)
{
	if (!q || q->open || q->readers) return HALO_PS2_BITMAP_REQUEST_BUSY;
	q->frame_index=frame; q->generation=gen; q->view_index=view; q->player_index=player;
	q->count=0; q->unsupported_count=q->missing_texture_count=q->invalid_identity_count=q->full_count=0;
	q->open=1; q->closed=0; return HALO_PS2_BITMAP_REQUEST_OK;
}
halo_ps2_bitmap_request_status halo_ps2_bitmap_requests_set_view(
	halo_ps2_bitmap_request_queue *q, int16_t view, int16_t player)
{
	if (!q || !q->open || view<0 || player<0) return HALO_PS2_BITMAP_REQUEST_INVALID_ARGUMENT;
	q->view_index=view; q->player_index=player; return HALO_PS2_BITMAP_REQUEST_OK;
}
halo_ps2_bitmap_request_status halo_ps2_bitmap_requests_acquire(
	halo_ps2_bitmap_request_queue *q, uint32_t generation, halo_ps2_bitmap_request_reader *r)
{
	(void)q; (void)generation; memset(r, 0, sizeof *r); r->held = 1;
	return HALO_PS2_BITMAP_REQUEST_OK;
}
void halo_ps2_bitmap_requests_release(halo_ps2_bitmap_request_reader *r) { memset(r, 0, sizeof *r); }
halo_ps2_bitmap_request_status halo_ps2_bitmap_requests_end(halo_ps2_bitmap_request_queue *q)
{
	halo_ps2_bitmap_request_reader reader;
	if (!q || !q->open) return HALO_PS2_BITMAP_REQUEST_NO_ACTIVE_FRAME;
	q->open=0; q->closed=1;
	if (q->consumer) {
		memset(&reader,0,sizeof(reader)); reader.queue=q; reader.requests=q->requests;
		reader.generation=q->generation; reader.count=q->count; reader.held=1;
		if (q->consumer(&reader,q->consumer_context)) return HALO_PS2_BITMAP_REQUEST_CONSUMER_FAILED;
	}
	return HALO_PS2_BITMAP_REQUEST_OK;
}
int32_t halo_ps2_bitmap_frame_consumer_register(const halo_ps2_bitmap_frame_consumer *c)
{
	if (!c || s_frame_registered) return HALO_PS2_BITMAP_FRAME_BUSY;
	s_frame_consumer=*c; s_frame_registered=1; return HALO_PS2_BITMAP_FRAME_OK;
}
int32_t halo_ps2_bitmap_frame_consumer_clear(void)
{
	if (!s_frame_registered) return HALO_PS2_BITMAP_FRAME_OK;
	memset(&s_frame_consumer,0,sizeof(s_frame_consumer)); s_frame_registered=0;
	return HALO_PS2_BITMAP_FRAME_OK;
}
int32_t halo_ps2_bitmap_frame_last_status(void) { return 0; }
uint32_t halo_ps2_bitmap_frame_failure_count(void) { return 0; }
int32_t halo_ps2_bitmap_frame_is_active(void) { return 0; }
int32_t hcu_bitmap_dispatch_reader(const halo_ps2_bitmap_request_reader *reader, void *ctx)
{
	hcu_bitmap_dispatch_context *d=(hcu_bitmap_dispatch_context *)ctx;
	if (!reader || !reader->held || !d) return -1;
	s_dispatch_calls++; d->lease_count=1; return 0;
}
void hcu_bitmap_dispatch_complete(hcu_bitmap_dispatch_context *ctx)
{
	if (!ctx) return;
	ctx->lease_count=0;
	s_dispatch_complete_calls++;
}

int main(void)
{
	hcu_bitmap_frame_owner owner;
	halo_ps2_bitmap_request_queue queue;
	hcu_bitmap_dispatch_context dispatch;
	hcu_asset_profile_view profile;
	hcu_bitmap_binding binding;
	memset(&queue,0,sizeof(queue)); memset(&dispatch,0,sizeof(dispatch));
	memset(&profile,0,sizeof(profile)); memset(&binding,0,sizeof(binding));
	profile.profile_id=19; profile.memory_image=(const uint8_t *)1;
	binding.expected_profile_id=19;
	dispatch.profile=&profile; dispatch.bindings=&binding; dispatch.binding_count=1;
	dispatch.expected_generation=7;
	if (hcu_bitmap_frame_owner_init(&owner) != HCU_BITMAP_FRAME_OK) return 1;
	/* A pre-existing unrelated renderer consumer must survive a busy register. */
	s_frame_consumer.context=&profile; s_frame_registered=1;
	if (hcu_bitmap_frame_owner_bind(&owner,&queue,&dispatch,fake_fence_query,0,
		HALO_PS2_BITMAP_FRAME_TEST_CAPS,&profile,&binding,1,7) != HCU_BITMAP_FRAME_E_BUSY ||
		s_frame_consumer.context != &profile || queue.consumer != 0) return 19;
	(void)halo_ps2_bitmap_frame_consumer_clear();
#if HALO_PS2_BITMAP_FRAME_TEST_CAPS == 1u
	if (hcu_bitmap_frame_owner_bind(&owner,&queue,&dispatch,fake_fence_query,0,
		HALO_PS2_BITMAP_FRAME_REQUIRED_PRODUCERS,&profile,&binding,1,7) !=
		HCU_BITMAP_FRAME_E_NOT_READY) return 18;
#endif
	if (hcu_bitmap_frame_owner_bind(&owner,&queue,&dispatch,fake_fence_query,0,
		HALO_PS2_BITMAP_FRAME_TEST_CAPS,&profile,&binding,1,7) != HCU_BITMAP_FRAME_OK) return 2;
	if (hcu_bitmap_frame_begin_callback(&owner,10,2) != 0) return 3;
	if (hcu_bitmap_frame_set_view_callback(&owner,0,0) != 0) return 4;
	if (hcu_bitmap_frame_set_view_callback(&owner,2,1) != 0) return 5;
	/* CE end seals the batch; with no emit window bound it must not dispatch yet. */
	if (hcu_bitmap_frame_end_callback(&owner,10,0) != 0 || owner.gpu_pending || !owner.drain_pending) return 6;
	if (s_dispatch_calls != 0 || dispatch.lease_count != 0) return 7;
	/* The parent emit window binds the live chains and drains the sealed batch into them. */
	{
		chain_t gc, uc;
		memset(&gc,0,sizeof(gc)); memset(&uc,0,sizeof(uc));
		dispatch.geometry_chain=&gc; dispatch.upload_chain=&uc;
		if (hcu_bitmap_frame_owner_drain_pending(&owner) != HCU_BITMAP_FRAME_OK) return 6;
		dispatch.geometry_chain=0; dispatch.upload_chain=0;
	}
	if (s_dispatch_calls != 1 || dispatch.lease_count != 1 || !owner.gpu_pending || owner.drain_pending) return 7;
	if (hcu_bitmap_frame_owner_unbind(&owner) != HCU_BITMAP_FRAME_E_BUSY) return 8;
	if (hcu_bitmap_frame_begin_callback(&owner,11,1) != HCU_BITMAP_FRAME_E_BUSY) return 9;
	if (hcu_bitmap_frame_owner_gpu_fence_complete(&owner,9) != HCU_BITMAP_FRAME_E_FENCE) return 10;
	if (hcu_bitmap_frame_owner_gpu_fence_complete(&owner,10) != HCU_BITMAP_FRAME_E_BUSY ||
		dispatch.lease_count != 1 || s_dispatch_complete_calls != 0) return 11;
	s_fence_observed = 1;
	if (hcu_bitmap_frame_owner_gpu_fence_complete(&owner,10) != HCU_BITMAP_FRAME_OK ||
		dispatch.lease_count || s_dispatch_complete_calls != 1) return 11;
	binding.chunk_id++;
	if (hcu_bitmap_frame_begin_callback(&owner,11,1) != HCU_BITMAP_FRAME_E_NOT_READY) return 12;
	binding.chunk_id--;
	if (hcu_bitmap_frame_begin_callback(&owner,11,1) != 0) return 13;
	if (hcu_bitmap_frame_set_view_callback(&owner,0,0) != 0) return 14;
	/* A faulted batch drops only its frame: the CE end succeeds, nothing emits, nothing stays pending. */
	queue.full_count=1;
	if (hcu_bitmap_frame_end_callback(&owner,11,0) != HCU_BITMAP_FRAME_OK) return 15;
	if (owner.stat_drops != 1 || owner.last_drop_cause != 16u || owner.drain_pending ||
		owner.gpu_pending || owner.in_frame) return 16;
	if (s_dispatch_calls != 1 || dispatch.lease_count) return 16;
	/* Recovery: the next frame starts clean; its batch emits once the chains bind and the fence completes. */
	if (hcu_bitmap_frame_begin_callback(&owner,12,1) != 0) return 20;
	if (hcu_bitmap_frame_set_view_callback(&owner,0,0) != 0) return 21;
	if (hcu_bitmap_frame_end_callback(&owner,12,0) != 0 || owner.stat_drops != 1 || !owner.drain_pending) return 22;
	{
		chain_t gc, uc;
		memset(&gc,0,sizeof(gc)); memset(&uc,0,sizeof(uc));
		dispatch.geometry_chain=&gc; dispatch.upload_chain=&uc;
		if (hcu_bitmap_frame_owner_drain_pending(&owner) != HCU_BITMAP_FRAME_OK) return 23;
		dispatch.geometry_chain=0; dispatch.upload_chain=0;
	}
	if (s_dispatch_calls != 2 || dispatch.lease_count != 1 || !owner.gpu_pending || owner.drain_pending) return 24;
	if (hcu_bitmap_frame_owner_gpu_fence_complete(&owner,12) != HCU_BITMAP_FRAME_OK ||
		dispatch.lease_count || owner.gpu_pending) return 25;
	if (hcu_bitmap_frame_owner_unbind(&owner) != HCU_BITMAP_FRAME_OK) return 17;
	puts("FRAME_OWNER_OK binds/views/dispatch/fence/unbind/drop-and-recover");
	return 0;
}
