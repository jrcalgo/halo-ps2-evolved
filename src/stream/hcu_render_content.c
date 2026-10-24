#include "stream/hcu_render_content.h"

#include <stddef.h>

hcu_render_content_status hcu_render_parity_log_init(hcu_render_parity_log *log,
	hcu_render_parity_record *storage, uint32_t capacity)
{
	if (!log || (!storage && capacity)) return HCU_RENDER_CONTENT_E_ARGUMENT;
	log->records = storage;
	log->capacity = capacity;
	log->count = 0;
	log->dropped = 0;
	return HCU_RENDER_CONTENT_OK;
}

hcu_render_content_status hcu_render_parity_log_append(hcu_render_parity_log *log,
	const hcu_render_parity_record *record)
{
	if (!log || !record || !log->records) return HCU_RENDER_CONTENT_E_ARGUMENT;
	if (record->kind < HCU_RENDER_PARITY_BSP || record->kind > HCU_RENDER_PARITY_EFFECT)
		return HCU_RENDER_CONTENT_E_ARGUMENT;
	if (log->count >= log->capacity) {
		log->dropped++;
		return HCU_RENDER_CONTENT_E_FULL;
	}
	log->records[log->count++] = *record;
	return HCU_RENDER_CONTENT_OK;
}

hcu_render_content_status hcu_render_claim_begin(hcu_render_texture_claim *claim,
	uint32_t chunk_id, uint16_t cache_key)
{
	if (!claim) return HCU_RENDER_CONTENT_E_ARGUMENT;
	if (claim->state != HCU_RENDER_CLAIM_FREE) return HCU_RENDER_CONTENT_E_STATE;
	claim->chunk_id = chunk_id;
	claim->cache_key = cache_key;
	claim->upload_frame = 0;
	claim->state = HCU_RENDER_CLAIM_SOURCE_HELD;
	return HCU_RENDER_CONTENT_OK;
}

hcu_render_content_status hcu_render_claim_queued(hcu_render_texture_claim *claim,
	int queue_ok, uint32_t frame)
{
	if (!claim) return HCU_RENDER_CONTENT_E_ARGUMENT;
	if (claim->state != HCU_RENDER_CLAIM_SOURCE_HELD) return HCU_RENDER_CONTENT_E_STATE;
	if (!queue_ok) {
		/* Failed queue: nothing was published, drop the claim. */
		claim->state = HCU_RENDER_CLAIM_FREE;
		return HCU_RENDER_CONTENT_E_STATE;
	}
	claim->upload_frame = frame;
	claim->state = HCU_RENDER_CLAIM_UPLOAD_QUEUED;
	return HCU_RENDER_CONTENT_OK;
}

hcu_render_content_status hcu_render_claim_publish(hcu_render_texture_claim *claim)
{
	if (!claim) return HCU_RENDER_CONTENT_E_ARGUMENT;
	if (claim->state != HCU_RENDER_CLAIM_UPLOAD_QUEUED) return HCU_RENDER_CONTENT_E_STATE;
	claim->state = HCU_RENDER_CLAIM_PUBLISHED;
	return HCU_RENDER_CONTENT_OK;
}

hcu_render_content_status hcu_render_claim_upload_complete(hcu_render_texture_claim *claim,
	int32_t fence)
{
	if (!claim) return HCU_RENDER_CONTENT_E_ARGUMENT;
	if (claim->state != HCU_RENDER_CLAIM_PUBLISHED && claim->state != HCU_RENDER_CLAIM_UPLOAD_QUEUED)
		return HCU_RENDER_CONTENT_E_STATE;
	if (fence < 0) return HCU_RENDER_CONTENT_E_FENCE;
	if (fence == 0) return HCU_RENDER_CONTENT_E_FENCE;
	/* Source bytes may be released here; the claim stays published. */
	return HCU_RENDER_CONTENT_OK;
}

int hcu_render_content_reuse_allowed(hcu_render_content_fence_fn fence,
	void *context, uint32_t frame_index, uint16_t readers)
{
	int32_t observed;
	if (!fence) return 0;
	if (readers != 0) return 0;
	observed = fence(context, frame_index);
	return observed == 1;
}
