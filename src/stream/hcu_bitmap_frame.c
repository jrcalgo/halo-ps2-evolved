#include "stream/hcu_bitmap_frame.h"

#include <string.h>
#include "halo_ps2_bitmap_frame.h"
#include "halo_ps2_bitmap_requests.h"
#include "stream/sha256.h"

#define HCU_BITMAP_FRAME_MAX_BINDINGS 4096u

static void bindings_digest(const hcu_bitmap_binding *bindings,
	uint32_t count, uint8_t digest[32])
{
	sha256_context sha;
	sha256_init(&sha);
	sha256_update(&sha, bindings, (size_t)count * sizeof(*bindings));
	sha256_final(&sha, digest);
}

static int profile_unchanged(const hcu_bitmap_frame_owner *owner)
{
	const hcu_asset_profile_view *a = owner->profile;
	const hcu_asset_profile_view *b = &owner->profile_snapshot;
	uint8_t digest[32];
	if (!a || a->profile_id != b->profile_id || a->total_bytes != b->total_bytes ||
		a->version != b->version || a->record_bytes != b->record_bytes ||
		a->chunk_count != b->chunk_count || a->directory_bytes != b->directory_bytes ||
		a->read_at != b->read_at || a->reader_context != b->reader_context ||
		a->memory_image != b->memory_image || !owner->bindings || !owner->binding_count)
		return 0;
	bindings_digest(owner->bindings, owner->binding_count, digest);
	return memcmp(digest, owner->bindings_sha256, sizeof(digest)) == 0;
}

static int producer_descriptor_has(uint32_t capabilities)
{
	halo_ps2_bitmap_real_producer_descriptor const *d =
		&halo_ps2_real_producer_descriptor_instance;
	return d && capabilities &&
		(capabilities & ~HALO_PS2_BITMAP_FRAME_REQUIRED_PRODUCERS) == 0 &&
		d->magic == HALO_PS2_BITMAP_REAL_PRODUCER_MAGIC &&
		d->version == HALO_PS2_BITMAP_REAL_PRODUCER_VERSION &&
		(d->capabilities & capabilities) == capabilities;
}

/* Fault bits for the sealed batch of the current frame (0 = batch is clean). */
static uint32_t batch_fault(const hcu_bitmap_frame_owner *owner)
{
	const halo_ps2_bitmap_request_queue *q = owner->queue;
	uint32_t fault = 0;
	if (owner->frame_abort) fault |= 1u;
	if (q->unsupported_count) fault |= 2u;
	if (q->missing_texture_count) fault |= 4u;
	if (q->invalid_identity_count) fault |= 8u;
	if (q->full_count) fault |= 16u;
	if (owner->view_call_count != owner->active_window_count) fault |= 32u;
	return fault;
}

/* Drop only this frame's batch: nothing is emitted, nothing stays pending, and the
 * drop is counted. The next frame starts from a clean batch state. */
static void drop_batch(hcu_bitmap_frame_owner *owner, uint32_t fault)
{
	owner->stat_drops++;
	owner->last_drop_cause = fault;
	owner->drop_causes_seen |= fault;
	owner->frame_dropped = 1;
	owner->drain_pending = 0;
}

/* Capture is all-or-nothing at frame granularity. If the bounded CE seam saw
 * an unsupported or malformed call, don't dispatch only the surviving subset. */
static int32_t frame_dispatch_reader(
	halo_ps2_bitmap_request_reader const *reader, void *context)
{
	hcu_bitmap_frame_owner *owner = (hcu_bitmap_frame_owner *)context;
	uint32_t fault;
	if (!reader || !reader->held || !owner || !owner->queue || !owner->dispatch)
		return HCU_BITMAP_FRAME_E_ARGUMENT;
	fault = batch_fault(owner);
	if (fault) {
		drop_batch(owner, fault);
		return HCU_BITMAP_FRAME_OK;
	}
	/* port: CE seals the batch outside the parent build; hold it until the emit window binds the chains. */
	if (!owner->dispatch->geometry_chain || !owner->dispatch->upload_chain) {
		owner->drain_pending = 1;
		return HCU_BITMAP_FRAME_OK;
	}
	return hcu_bitmap_dispatch_reader(reader, owner->dispatch);
}

static int queue_idle(const halo_ps2_bitmap_request_queue *q)
{
	return q && !q->open && !q->readers;
}

hcu_bitmap_frame_status hcu_bitmap_frame_owner_init(hcu_bitmap_frame_owner *owner)
{
	if (!owner) return HCU_BITMAP_FRAME_E_ARGUMENT;
	memset(owner, 0, sizeof(*owner));
	return HCU_BITMAP_FRAME_OK;
}

hcu_bitmap_frame_status hcu_bitmap_frame_owner_bind(
	hcu_bitmap_frame_owner *owner,
	halo_ps2_bitmap_request_queue *queue,
	hcu_bitmap_dispatch_context *dispatch,
	hcu_bitmap_frame_fence_query_fn fence_query, void *fence_context,
	uint32_t producer_capabilities,
	const hcu_asset_profile_view *profile,
	const hcu_bitmap_binding *bindings, uint32_t binding_count,
	uint32_t generation)
{
	halo_ps2_bitmap_frame_consumer consumer;
	if (!owner || !queue || !dispatch || !fence_query || !profile || !bindings || !binding_count ||
		binding_count > HCU_BITMAP_FRAME_MAX_BINDINGS || !generation ||
		!producer_capabilities ||
		(producer_capabilities & ~HALO_PS2_BITMAP_FRAME_REQUIRED_PRODUCERS) != 0 ||
		dispatch->profile != profile || dispatch->bindings != bindings ||
		dispatch->binding_count != binding_count || dispatch->expected_generation != generation ||
		profile->profile_id == 0 || (!profile->memory_image && !profile->read_at) ||
		!producer_descriptor_has(producer_capabilities))
		return HCU_BITMAP_FRAME_E_NOT_READY;
	if (owner->bound || owner->in_frame || owner->gpu_pending || dispatch->lease_count ||
		!queue_idle(queue) || queue->consumer || halo_ps2_bitmap_frame_is_active())
		return HCU_BITMAP_FRAME_E_BUSY;
	if (halo_ps2_bitmap_requests_register_consumer(queue,
		frame_dispatch_reader, owner) !=
		HALO_PS2_BITMAP_REQUEST_OK)
		return HCU_BITMAP_FRAME_E_QUEUE;
	owner->queue = queue;
	owner->dispatch = dispatch;
	owner->fence_query = fence_query;
	owner->fence_context = fence_context;
	owner->profile = profile;
	owner->profile_snapshot = *profile;
	owner->bindings = bindings;
	owner->binding_count = binding_count;
	bindings_digest(bindings, binding_count, owner->bindings_sha256);
	owner->generation = generation;
	owner->producer_capabilities = producer_capabilities;
	owner->queue_consumer_registered = 1;
	memset(&consumer, 0, sizeof(consumer));
	consumer.begin = hcu_bitmap_frame_begin_callback;
	consumer.set_view = hcu_bitmap_frame_set_view_callback;
	consumer.end = hcu_bitmap_frame_end_callback;
	consumer.context = owner;
	consumer.producer_capabilities = producer_capabilities;
	if (halo_ps2_bitmap_frame_consumer_register(&consumer) != HALO_PS2_BITMAP_FRAME_OK) {
		(void)halo_ps2_bitmap_requests_clear_consumer(queue);
		memset(owner, 0, sizeof(*owner));
		return HCU_BITMAP_FRAME_E_BUSY;
	}
	owner->frame_consumer_registered = 1;
	owner->bound = 1;
	return HCU_BITMAP_FRAME_OK;
}

hcu_bitmap_frame_status hcu_bitmap_frame_owner_unbind(hcu_bitmap_frame_owner *owner)
{
	if (!owner || !owner->bound) return HCU_BITMAP_FRAME_E_ARGUMENT;
	if (owner->in_frame || owner->gpu_pending || owner->drain_pending || halo_ps2_bitmap_frame_is_active() ||
		!owner->queue || !queue_idle(owner->queue) ||
		!owner->dispatch || owner->dispatch->lease_count)
		return HCU_BITMAP_FRAME_E_BUSY;
	if (halo_ps2_bitmap_frame_consumer_clear() != HALO_PS2_BITMAP_FRAME_OK)
		return HCU_BITMAP_FRAME_E_BUSY;
	owner->frame_consumer_registered = 0;
	if (owner->queue_consumer_registered &&
		halo_ps2_bitmap_requests_clear_consumer(owner->queue) != HALO_PS2_BITMAP_REQUEST_OK)
		return HCU_BITMAP_FRAME_E_QUEUE;
	memset(owner, 0, sizeof(*owner));
	return HCU_BITMAP_FRAME_OK;
}

/* port: drain the sealed batch inside the parent emit window. The queue stays sealed (no new frame may begin
 * while drain_pending is set), so the reader re-acquired here still holds the frame's requests. */
hcu_bitmap_frame_status hcu_bitmap_frame_owner_drain_pending(hcu_bitmap_frame_owner *owner)
{
	halo_ps2_bitmap_request_reader reader;
	int32_t status;
	if (!owner || !owner->bound || !owner->dispatch) return HCU_BITMAP_FRAME_E_ARGUMENT;
	if (!owner->drain_pending) return HCU_BITMAP_FRAME_OK;
	if (owner->in_frame || !owner->queue || !owner->queue->closed || owner->queue->open ||
		!owner->dispatch->geometry_chain || !owner->dispatch->upload_chain)
		return HCU_BITMAP_FRAME_E_NOT_READY;
	memset(&reader, 0, sizeof(reader));
	if (halo_ps2_bitmap_requests_acquire(owner->queue, owner->queue->generation, &reader) !=
		HALO_PS2_BITMAP_REQUEST_OK)
		return HCU_BITMAP_FRAME_E_QUEUE;
	status = frame_dispatch_reader(&reader, owner);
	halo_ps2_bitmap_requests_release(&reader);
	owner->drain_pending = 0;
	owner->gpu_pending = owner->dispatch->lease_count != 0;
	owner->last_status = status;
	return status;
}

hcu_bitmap_frame_status hcu_bitmap_frame_owner_gpu_fence_complete(
	hcu_bitmap_frame_owner *owner, uint32_t frame_index)
{
	if (!owner || !owner->bound || !owner->dispatch) return HCU_BITMAP_FRAME_E_ARGUMENT;
	if (owner->in_frame || !owner->gpu_pending || owner->frame_index != frame_index ||
		!queue_idle(owner->queue)) return HCU_BITMAP_FRAME_E_FENCE;
	{
		int32_t observed = owner->fence_query(owner->fence_context, frame_index);
		if (observed == 0) return HCU_BITMAP_FRAME_E_BUSY;
		if (observed < 0) return HCU_BITMAP_FRAME_E_FENCE;
	}
	hcu_bitmap_dispatch_complete(owner->dispatch);
	if (owner->dispatch->lease_count) return HCU_BITMAP_FRAME_E_BUSY;
	owner->gpu_pending = 0;
	return HCU_BITMAP_FRAME_OK;
}

int32_t hcu_bitmap_frame_begin_callback(void *context, uint32_t frame_index,
	uint16_t active_window_count)
{
	hcu_bitmap_frame_owner *owner = (hcu_bitmap_frame_owner *)context;
	if (owner) owner->stat_begin_calls++;
	if (!owner || !owner->bound || !owner->queue || !owner->dispatch ||
		owner->profile != owner->dispatch->profile || owner->bindings != owner->dispatch->bindings ||
		owner->binding_count != owner->dispatch->binding_count ||
		owner->generation != owner->dispatch->expected_generation ||
		!owner->producer_capabilities ||
		(owner->producer_capabilities &
			~HALO_PS2_BITMAP_FRAME_REQUIRED_PRODUCERS) != 0 ||
		!profile_unchanged(owner) ||
		!producer_descriptor_has(owner->producer_capabilities))
		return HCU_BITMAP_FRAME_E_NOT_READY;
	if (owner->in_frame || owner->gpu_pending || owner->drain_pending || owner->dispatch->lease_count ||
		!queue_idle(owner->queue)) return HCU_BITMAP_FRAME_E_BUSY;
	if (!active_window_count || active_window_count > HALO_PS2_BITMAP_FRAME_MAX_WINDOWS)
		return HCU_BITMAP_FRAME_E_VIEW;
	if (halo_ps2_bitmap_requests_begin(owner->queue, frame_index, owner->generation, 0, 0) !=
		HALO_PS2_BITMAP_REQUEST_OK) return HCU_BITMAP_FRAME_E_QUEUE;
	owner->stat_begins++;
	owner->frame_index = frame_index;
	owner->frame_dropped = 0;
	owner->active_window_count = active_window_count;
	owner->view_call_count = 0;
	owner->last_window_index = 0;
	owner->has_last_window = 0;
	owner->frame_abort = 0;
	owner->in_frame = 1;
	owner->last_status = HCU_BITMAP_FRAME_OK;
	return HCU_BITMAP_FRAME_OK;
}

int32_t hcu_bitmap_frame_set_view_callback(void *context, uint16_t window_index,
	int16_t local_player_index)
{
	hcu_bitmap_frame_owner *owner = (hcu_bitmap_frame_owner *)context;
	if (!owner || !owner->in_frame || !owner->queue) return HCU_BITMAP_FRAME_E_BUSY;
	/* Console windows are skipped by the CE producer loop, so original window
	 * indices may have gaps. Require increasing indices and exactly the active
	 * window count, rather than equating an index with a dense ordinal. */
	if (owner->view_call_count >= owner->active_window_count ||
		window_index >= HALO_PS2_BITMAP_FRAME_MAX_WINDOWS ||
		(owner->has_last_window && window_index <= owner->last_window_index) ||
		local_player_index < 0) return HCU_BITMAP_FRAME_E_VIEW;
	if (halo_ps2_bitmap_requests_set_view(owner->queue, (int16_t)window_index,
		local_player_index) != HALO_PS2_BITMAP_REQUEST_OK) return HCU_BITMAP_FRAME_E_QUEUE;
	owner->view_call_count++;
	owner->stat_set_views++;
	owner->last_window_index = window_index;
	owner->has_last_window = 1;
	return HCU_BITMAP_FRAME_OK;
}

int32_t hcu_bitmap_frame_end_callback(void *context, uint32_t frame_index,
	int32_t prior_status)
{
	hcu_bitmap_frame_owner *owner = (hcu_bitmap_frame_owner *)context;
	int32_t status = prior_status;
	if (!owner || !owner->in_frame || !owner->queue || owner->frame_index != frame_index)
		return HCU_BITMAP_FRAME_E_BUSY;
	owner->stat_ends++;
	owner->stat_requests += owner->queue->count;
	owner->frame_abort = status != 0 ||
		owner->view_call_count != owner->active_window_count;
	{
		halo_ps2_bitmap_request_status queue_status =
			halo_ps2_bitmap_requests_end(owner->queue);
		owner->stat_queue_ends++;
		if (queue_status != HALO_PS2_BITMAP_REQUEST_OK && status == 0)
			status = owner->queue->last_consumer_status != 0
				? owner->queue->last_consumer_status : HCU_BITMAP_FRAME_E_QUEUE;
	}
	/* A faulted batch is dropped whole and counted. The CE frame is not failed for it. */
	if (batch_fault(owner) && !owner->frame_dropped) drop_batch(owner, batch_fault(owner));
	owner->in_frame = 0;
	owner->gpu_pending = owner->dispatch && owner->dispatch->lease_count != 0;
	owner->last_status = status;
	if (status != 0) {
		owner->stat_end_failures++;
		return status;
	}
	if (owner->frame_dropped) return HCU_BITMAP_FRAME_OK;
	status = owner->dispatch ? owner->dispatch->first_error : HCU_BITMAP_FRAME_E_NOT_READY;
	owner->last_status = status;
	return status;
}
