/* Host fixture for the bounded CE sound-request recorder (C3.8). */
#include "stream/hcu_sound_requests.h"

#include <assert.h>
#include <stdio.h>
#include <string.h>

static hcu_sound_request make(uint16_t event, uint32_t permutation)
{
	hcu_sound_request r;
	memset(&r, 0, sizeof(r));
	r.event = event;
	r.permutation = permutation;
	r.owner_kind = HCU_SOUND_OWNER_OBJECT;
	r.owner_datum = 0x1234u;
	r.sound_index = 7u;
	r.has_position = 1;
	r.position[0] = 1.5f;
	r.position[1] = -2.0f;
	r.position[2] = 3.25f;
	r.priority = 5;
	r.flags = 0x5u;
	r.gain = 0.75f;
	r.pitch = 1.25f;
	r.game_time = 99u;
	return r;
}

static hcu_sound_request_queue queue;

int main(void)
{
	hcu_sound_request in[HCU_SOUND_REQUEST_CAPACITY + 4];
	hcu_sound_request out[HCU_SOUND_REQUEST_CAPACITY + 4];
	hcu_sound_request_counters c;
	size_t n, i;

	hcu_sound_requests_init(&queue);
	assert(queue.spu2_playback_qualified == 0);

	/* Invalid records are rejected and never stored. */
	{
		hcu_sound_request bad = make(HCU_SOUND_EVENT_NONE, 1u);
		assert(!hcu_sound_requests_submit(&queue, &bad));
		bad = make(HCU_SOUND_EVENT_IMPULSE, 1u);
		bad.gain = -1.0f;
		assert(!hcu_sound_requests_submit(&queue, &bad));
		bad = make(HCU_SOUND_EVENT_IMPULSE, 1u);
		bad.pitch = 0.0f;
		assert(!hcu_sound_requests_submit(&queue, &bad));
		bad = make(HCU_SOUND_EVENT_IMPULSE, 1u);
		bad.flags = 0x10u;
		assert(!hcu_sound_requests_submit(&queue, &bad));
		bad = make(HCU_SOUND_EVENT_IMPULSE, 1u);
		bad.position[1] = 0.0f;
		bad.position[1] = bad.position[1] / bad.position[1];
		assert(!hcu_sound_requests_submit(&queue, &bad));
		bad = make(HCU_SOUND_EVENT_IMPULSE, 1u);
		bad.owner_kind = 9;
		assert(!hcu_sound_requests_submit(&queue, &bad));
		assert(queue.count == 0);
		hcu_sound_requests_counters(&queue, &c);
		assert(c.submitted == 6 && c.rejected == 6 && c.accepted == 0);
	}

	/* Fill exactly to capacity, then one more is rejected without evicting. */
	for (i = 0; i < HCU_SOUND_REQUEST_CAPACITY; ++i) {
		in[i] = make(HCU_SOUND_EVENT_PERMUTATION, (uint32_t)(0x100u + i));
		assert(hcu_sound_requests_submit(&queue, &in[i]));
	}
	assert(!hcu_sound_requests_submit(&queue, &in[0]));
	hcu_sound_requests_counters(&queue, &c);
	assert(c.accepted == HCU_SOUND_REQUEST_CAPACITY);
	assert(c.high_water == HCU_SOUND_REQUEST_CAPACITY);
	assert(c.dropped_while_full == 1);
	assert(c.pending == HCU_SOUND_REQUEST_CAPACITY);

	/* Drain in two parts: order is preserved, every field round-trips. */
	n = hcu_sound_requests_drain(&queue, out, 10);
	assert(n == 10);
	for (i = 0; i < n; ++i) {
		assert(out[i].permutation == 0x100u + i);
		assert(out[i].sequence == out[0].sequence + (uint32_t)i);
		assert(out[i].owner_datum == 0x1234u && out[i].owner_kind == HCU_SOUND_OWNER_OBJECT);
		assert(out[i].has_position && out[i].position[2] == 3.25f);
		assert(out[i].priority == 5 && out[i].flags == 0x5u);
		assert(out[i].gain == 0.75f && out[i].pitch == 1.25f);
		assert(out[i].game_time == 99u && out[i].sound_index == 7u);
	}
	n = hcu_sound_requests_drain(&queue, out, HCU_SOUND_REQUEST_CAPACITY + 4);
	assert(n == HCU_SOUND_REQUEST_CAPACITY - 10);
	assert(out[0].permutation == 0x10Au);
	assert(hcu_sound_requests_drain(&queue, out, 4) == 0);
	hcu_sound_requests_counters(&queue, &c);
	assert(c.drained == HCU_SOUND_REQUEST_CAPACITY && c.pending == 0);

	/* Ring wraps after draining: new records keep arrival order. */
	for (i = 0; i < 5; ++i)
		assert(hcu_sound_requests_submit(&queue, &in[i]));
	n = hcu_sound_requests_drain(&queue, out, 5);
	assert(n == 5 && out[0].permutation == 0x100u && out[4].permutation == 0x104u);

	/* Reset drops pending records and keeps the counters. */
	assert(hcu_sound_requests_submit(&queue, &in[1]));
	hcu_sound_requests_reset(&queue);
	assert(queue.count == 0);
	hcu_sound_requests_counters(&queue, &c);
	assert(c.resets == 1 && c.pending == 0 && c.accepted == HCU_SOUND_REQUEST_CAPACITY + 6);

	hcu_sound_requests_print(&queue, "fixture");
	printf("PASS sound request recorder: bounded ring, ordered drain, validation, counters\n");
	return 0;
}
