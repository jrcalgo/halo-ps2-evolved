#include "stream/hcu_sound_requests.h"

#include <stdio.h>
#include <string.h>

static int request_valid(const hcu_sound_request *request)
{
	if (request->event == HCU_SOUND_EVENT_NONE ||
		request->event > HCU_SOUND_EVENT_FADE)
		return 0;
	if (request->owner_kind > HCU_SOUND_OWNER_UNATTACHED)
		return 0;
	if (request->metadata_known & ~0x3fu)
		return 0;
	if (request->flags & ~0x7u)
		return 0;
	if ((request->metadata_known & 0x08u) && !(request->gain >= 0.0f))
		return 0;
	if ((request->metadata_known & 0x10u) && !(request->pitch > 0.0f))
		return 0;
	if ((request->metadata_known & 0x02u) && request->has_position) {
		size_t i;
		for (i = 0; i < 3; ++i)
			if (request->position[i] != request->position[i])
				return 0;
	}
	return 1;
}

void hcu_sound_requests_init(hcu_sound_request_queue *queue)
{
	if (!queue) return;
	memset(queue, 0, sizeof(*queue));
	queue->spu2_playback_qualified = 0;
}

void hcu_sound_requests_reset(hcu_sound_request_queue *queue)
{
	if (!queue) return;
	queue->head = 0;
	queue->count = 0;
	queue->counters.pending = 0;
	queue->counters.resets++;
}

int hcu_sound_requests_submit(hcu_sound_request_queue *queue,
	const hcu_sound_request *request)
{
	hcu_sound_request *slot;
	uint32_t tail;
	if (!queue || !request) return 0;
	queue->counters.submitted++;
	if (!request_valid(request)) {
		queue->counters.rejected++;
		return 0;
	}
	if (queue->count >= HCU_SOUND_REQUEST_CAPACITY) {
		queue->counters.rejected++;
		queue->counters.dropped_while_full++;
		return 0;
	}
	tail = (queue->head + queue->count) % HCU_SOUND_REQUEST_CAPACITY;
	slot = &queue->ring[tail];
	*slot = *request;
	queue->next_sequence++;
	if (queue->next_sequence == 0) queue->next_sequence = 1;
	slot->sequence = queue->next_sequence;
	queue->count++;
	queue->counters.accepted++;
	queue->counters.pending = queue->count;
	if (queue->count > queue->counters.high_water)
		queue->counters.high_water = queue->count;
	return 1;
}

size_t hcu_sound_requests_drain(hcu_sound_request_queue *queue,
	hcu_sound_request *out, size_t max)
{
	size_t n = 0;
	if (!queue || !out) return 0;
	while (n < max && queue->count > 0) {
		out[n++] = queue->ring[queue->head];
		queue->head = (queue->head + 1) % HCU_SOUND_REQUEST_CAPACITY;
		queue->count--;
	}
	queue->counters.drained += (uint32_t)n;
	queue->counters.pending = queue->count;
	return n;
}

void hcu_sound_requests_counters(const hcu_sound_request_queue *queue,
	hcu_sound_request_counters *out)
{
	if (!queue || !out) return;
	*out = queue->counters;
}

void hcu_sound_requests_print(const hcu_sound_request_queue *queue,
	const char *phase)
{
	if (!queue) return;
	printf("HALO_PS2_LOCAL sound-requests phase=%s submitted=%u accepted=%u "
		"rejected=%u drained=%u pending=%u high=%u dropped-full=%u resets=%u "
		"capacity=%u spu2-playback=not-qualified\n",
		phase ? phase : "-",
		queue->counters.submitted, queue->counters.accepted,
		queue->counters.rejected, queue->counters.drained,
		queue->counters.pending, queue->counters.high_water,
		queue->counters.dropped_while_full, queue->counters.resets,
		(unsigned)HCU_SOUND_REQUEST_CAPACITY);
}
