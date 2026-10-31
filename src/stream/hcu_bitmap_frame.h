#ifndef HALO_STREAM_HCU_BITMAP_FRAME_H
#define HALO_STREAM_HCU_BITMAP_FRAME_H

#include <stdint.h>
#include "stream/hcu_asset_profile.h"
#include "stream/hcu_bitmap_dispatch.h"

#ifdef __cplusplus
extern "C" {
#endif

typedef enum {
	HCU_BITMAP_FRAME_OK = 0,
	HCU_BITMAP_FRAME_E_ARGUMENT = -1,
	HCU_BITMAP_FRAME_E_NOT_READY = -2,
	HCU_BITMAP_FRAME_E_BUSY = -3,
	HCU_BITMAP_FRAME_E_GENERATION = -4,
	HCU_BITMAP_FRAME_E_VIEW = -5,
	HCU_BITMAP_FRAME_E_QUEUE = -6,
	HCU_BITMAP_FRAME_E_DISPATCH = -7,
	HCU_BITMAP_FRAME_E_FENCE = -8
} hcu_bitmap_frame_status;

/* Must return 1 only after both parent chains have reached their actual GPU
 * completion boundary, 0 while pending, and a negative value on query error. */
typedef int32_t (*hcu_bitmap_frame_fence_query_fn)(void *context,
	uint32_t frame_index);

typedef struct {
	halo_ps2_bitmap_request_queue *queue;
	hcu_bitmap_dispatch_context *dispatch;
	hcu_bitmap_frame_fence_query_fn fence_query;
	void *fence_context;
	const hcu_asset_profile_view *profile;
	hcu_asset_profile_view profile_snapshot;
	const hcu_bitmap_binding *bindings;
	uint32_t binding_count;
	uint32_t generation;
	uint32_t producer_capabilities;
	uint8_t bindings_sha256[32];
	uint32_t frame_index;
	uint16_t active_window_count;
	uint16_t view_call_count;
	uint16_t last_window_index;
	uint8_t bound;
	uint8_t in_frame;
	uint8_t gpu_pending;
	uint8_t queue_consumer_registered;
	uint8_t frame_consumer_registered;
	uint8_t has_last_window;
	uint8_t frame_abort;
	uint8_t drain_pending;   /* port: a sealed CE batch waits for the parent emit window */
	int32_t last_status;
	/* C3.9 counters, monotonic. Written only from the CE frame callbacks. */
	uint32_t stat_begin_calls;
	uint32_t stat_begins;
	uint32_t stat_set_views;
	uint32_t stat_queue_ends;
	uint32_t stat_ends;
	uint32_t stat_end_failures;
	uint32_t stat_requests;
	/* Fail-closed batch drops: a frame with an aborted CE call or a window-count mismatch emits nothing and never blocks the CE frame. */
	uint32_t stat_drops;
	uint32_t last_drop_cause;   /* bit 0 abort, 1 unsupported, 2 missing texture, 3 invalid identity,
	                               4 full, 5 view-count mismatch */
	uint32_t drop_causes_seen;
	/* Degraded batches: a request the PS2 path cannot capture (unsupported, missing texture, bad identity,
	 * queue full) is skipped alone; every other request of the frame still draws. Cause bits as above
	 * (1<<1 .. 1<<4); the reason fields describe the most recent degraded frame. */
	uint32_t stat_partial;
	uint32_t last_partial_cause;
	uint32_t partial_causes_seen;
	uint32_t last_partial_reason;      /* queue first_unsupported_reason */
	uint32_t last_partial_flags;       /* queue first_unsupported_flags */
	uint32_t last_partial_frame;
	uint8_t frame_dropped;
	/* Teardown discards of a sealed batch that was never dispatched, and the leases they released. */
	uint32_t stat_discarded_batches;
	uint32_t stat_discarded_leases;
	/* Binding integrity work. Hash timing is collected only when the EE timer is enabled. */
	uint32_t stat_binding_hash_calls;
	uint64_t stat_binding_hash_bytes;
	uint64_t stat_binding_hash_cycles;
	uint8_t bindings_immutable;
} hcu_bitmap_frame_owner;

/* Initialize caller-owned state only while no frame callback can be running. */
hcu_bitmap_frame_status hcu_bitmap_frame_owner_init(hcu_bitmap_frame_owner *owner);
/* Quiescent map boundary only. Queue/cache/chains/storage/bindings remain caller
 * owned and must outlive this binding. No frame is admitted unless the linked
 * real-producer descriptor validates. */
hcu_bitmap_frame_status hcu_bitmap_frame_owner_bind(
	hcu_bitmap_frame_owner *owner,
	halo_ps2_bitmap_request_queue *queue,
	hcu_bitmap_dispatch_context *dispatch,
	hcu_bitmap_frame_fence_query_fn fence_query, void *fence_context,
	uint32_t producer_capabilities,
	const hcu_asset_profile_view *profile,
	const hcu_bitmap_binding *bindings, uint32_t binding_count,
	uint32_t generation);
/* Bind against an explicitly sealed immutable generation. Caller guarantees that
 * bindings bytes and their referenced metadata are not modified from this call
 * until successful unbind; changes require unbind/rebind with a new generation.
 * Profile, generation, pointer/queue, producer descriptor, reader and DMA/fence
 * checks remain active. This API skips only the per-frame O(binding_count) hash. */
hcu_bitmap_frame_status hcu_bitmap_frame_owner_bind_immutable(
	hcu_bitmap_frame_owner *owner,
	halo_ps2_bitmap_request_queue *queue,
	hcu_bitmap_dispatch_context *dispatch,
	hcu_bitmap_frame_fence_query_fn fence_query, void *fence_context,
	uint32_t producer_capabilities,
	const hcu_asset_profile_view *profile,
	const hcu_bitmap_binding *bindings, uint32_t binding_count,
	uint32_t generation);
/* Refuses while a CPU frame/reader or GPU lease is active. */
hcu_bitmap_frame_status hcu_bitmap_frame_owner_unbind(hcu_bitmap_frame_owner *owner);
/* port: dispatch a batch sealed by CE while no emit window was bound. Call only inside the parent build's
 * emit window, after the chains are bound. No-op when nothing is pending. */
hcu_bitmap_frame_status hcu_bitmap_frame_owner_drain_pending(hcu_bitmap_frame_owner *owner);
/* Teardown only: discard a sealed batch that no emit window will ever dispatch (map release after the last
 * frame). Refuses (E_BUSY/E_FENCE) unless the owner is bound and idle, the queue has no open readers, and the
 * renderer fence has observed the last kick, so no GPU work still references the leases. Releases the batch's
 * leases without drawing and counts the discard. No-op when nothing is pending. */
hcu_bitmap_frame_status hcu_bitmap_frame_owner_discard_pending(hcu_bitmap_frame_owner *owner);
/* Invoke only after the real parent paired-chain GPU FINISH/wait has completed
 * for this frame. This is the sole operation that releases dispatcher leases. */
hcu_bitmap_frame_status hcu_bitmap_frame_owner_gpu_fence_complete(
	hcu_bitmap_frame_owner *owner, uint32_t frame_index);

/* Registered with halo_ps2_bitmap_frame_consumer_register. */
int32_t hcu_bitmap_frame_begin_callback(void *context, uint32_t frame_index,
	uint16_t active_window_count);
int32_t hcu_bitmap_frame_set_view_callback(void *context, uint16_t window_index,
	int16_t local_player_index);
int32_t hcu_bitmap_frame_end_callback(void *context, uint32_t frame_index,
	int32_t prior_status);

#ifdef __cplusplus
}
#endif
#endif
