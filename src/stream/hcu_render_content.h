#ifndef HALO_STREAM_HCU_RENDER_CONTENT_H
#define HALO_STREAM_HCU_RENDER_CONTENT_H

#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/* C3 content binding helpers, host-testable. They hold no DMA memory and
 * never touch the GS. The frame lane calls the fence hooks from its frame
 * loop; the renderer calls the claim functions around each texture upload. */

typedef enum {
	HCU_RENDER_CONTENT_OK = 0,
	HCU_RENDER_CONTENT_E_ARGUMENT = -1,
	HCU_RENDER_CONTENT_E_FULL = -2,
	HCU_RENDER_CONTENT_E_STATE = -3,
	HCU_RENDER_CONTENT_E_FENCE = -4
} hcu_render_content_status;

/* ---- parity log ------------------------------------------------------------
 * One record per drawn source item. Kinds name the consumer that produced it;
 * ids are the CE surface/material indices, so a capture can be compared with
 * the CE source for the same frame. */
typedef enum {
	HCU_RENDER_PARITY_BSP = 1,
	HCU_RENDER_PARITY_LIGHTMAP = 2,
	HCU_RENDER_PARITY_SKY = 3,
	HCU_RENDER_PARITY_OBJECT = 4,
	HCU_RENDER_PARITY_VEHICLE = 5,
	HCU_RENDER_PARITY_WEAPON = 6,
	HCU_RENDER_PARITY_HUD = 7,
	HCU_RENDER_PARITY_EFFECT = 8
} hcu_render_parity_kind;

typedef struct {
	uint32_t frame;
	uint32_t view;
	uint32_t kind;          /* hcu_render_parity_kind */
	int32_t surface_id;     /* CE surface index, -1 when not applicable */
	int32_t material_id;    /* CE material index, -1 when not applicable */
	uint32_t resource_id;   /* texture/bitmap chunk id, 0 when none */
} hcu_render_parity_record;

typedef struct {
	hcu_render_parity_record *records;
	uint32_t capacity;
	uint32_t count;
	uint32_t dropped;       /* records refused after capacity; never silently lost */
} hcu_render_parity_log;

hcu_render_content_status hcu_render_parity_log_init(hcu_render_parity_log *log,
	hcu_render_parity_record *storage, uint32_t capacity);
hcu_render_content_status hcu_render_parity_log_append(hcu_render_parity_log *log,
	const hcu_render_parity_record *record);

/* ---- texture claims ------------------------------------------------------
 * A claim moves FREE -> SOURCE_HELD -> UPLOAD_QUEUED -> PUBLISHED. Source bytes
 * stay held until upload completion (RELEASED). A claim may be published only
 * after its upload queued; a failed queue returns it to FREE. */
typedef enum {
	HCU_RENDER_CLAIM_FREE = 0,
	HCU_RENDER_CLAIM_SOURCE_HELD = 1,
	HCU_RENDER_CLAIM_UPLOAD_QUEUED = 2,
	HCU_RENDER_CLAIM_PUBLISHED = 3
} hcu_render_claim_state;

typedef struct {
	uint32_t chunk_id;
	uint16_t cache_key;
	uint8_t state;          /* hcu_render_claim_state */
	uint8_t reserved;
	uint32_t upload_frame;  /* frame that queued the upload */
} hcu_render_texture_claim;

hcu_render_content_status hcu_render_claim_begin(hcu_render_texture_claim *claim,
	uint32_t chunk_id, uint16_t cache_key);
/* queue_ok = the upload work queued successfully. */
hcu_render_content_status hcu_render_claim_queued(hcu_render_texture_claim *claim,
	int queue_ok, uint32_t frame);
/* Publish only from UPLOAD_QUEUED. */
hcu_render_content_status hcu_render_claim_publish(hcu_render_texture_claim *claim);
/* Source bytes may be dropped only after upload completion (fence observed). */
hcu_render_content_status hcu_render_claim_upload_complete(hcu_render_texture_claim *claim,
	int32_t fence);

/* ---- fence hooks for the frame lane ---------------------------------------
 * fence_query matches hcu_bitmap_frame_fence_query_fn: 1 = the frame's chains
 * and GS FINISH are observed, 0 = pending, negative = error. Reuse is allowed
 * only on 1. */
typedef int32_t (*hcu_render_content_fence_fn)(void *context, uint32_t frame_index);

/* 1 when a cache slot with `readers` in-flight readers may be reused for
 * `frame_index`. Any pending or error fence refuses reuse. */
int hcu_render_content_reuse_allowed(hcu_render_content_fence_fn fence,
	void *context, uint32_t frame_index, uint16_t readers);

#ifdef __cplusplus
}
#endif
#endif
