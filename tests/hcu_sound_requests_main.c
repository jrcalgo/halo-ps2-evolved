/* Host fixture for the bounded CE sound-request recorder (C3.8). */
#include "stream/hcu_sound_requests.h"

#include <assert.h>
#include <math.h>
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
	r.accepted = 1u;
	r.gain = 0.75f;
	r.pitch = 1.25f;
	r.metadata_known = 0x3fu;
	r.game_time = 99u;
	return r;
}

typedef struct {
	uint32_t n;
	uint32_t sequence[128];
	uint32_t sound[128];
	uint16_t event[128];
} collect_t;

static void collect_one(void *context, const hcu_sound_request *r)
{
	collect_t *c = (collect_t *)context;
	c->sequence[c->n] = r->sequence;
	c->sound[c->n] = r->sound_index;
	c->event[c->n] = r->event;
	c->n++;
}

static void count_one(void *context, const hcu_sound_request *r)
{
	(void)r;
	(*(uint32_t *)context)++;
}

static hcu_sound_request perm_req(uint32_t permutation, uint8_t flags)
{
	hcu_sound_request r = make(HCU_SOUND_EVENT_PERMUTATION_REQUEST, permutation);
	r.flags = flags;
	return r;
}

static hcu_sound_request play_req(uint16_t event, uint8_t priority,
	uint32_t sound, uint32_t owner)
{
	hcu_sound_request r = make(event, 1u);
	r.priority = priority;
	r.sound_index = sound;
	r.owner_datum = owner;
	return r;
}

/* 600 mixed requests in 15 ticks of 40, drained at the end of each tick. */
static void test_tick_drain_burst(void)
{
	static hcu_sound_request_queue q;
	hcu_sound_request_counters c;
	uint32_t t, i, drained = 0, seen = 0;
	hcu_sound_requests_init(&q);
	for (t = 0; t < 15; ++t) {
		for (i = 0; i < 40; ++i) {
			uint32_t k = t * 40u + i;
			hcu_sound_request r;
			switch (k % 5u) {
			case 0: r = perm_req(k % 9u, 0x1); break;
			case 1: r = play_req(HCU_SOUND_EVENT_IMPULSE, (uint8_t)(k % 8u), k, 1u); break;
			case 2: r = play_req(HCU_SOUND_EVENT_LOOPING_START, 3, k % 4u, 2u); break;
			case 3: r = play_req(HCU_SOUND_EVENT_LOOPING_STOP, 3, k % 4u, 2u); break;
			default: r = play_req(HCU_SOUND_EVENT_FADE, (uint8_t)(k % 8u), k, 3u); break;
			}
			assert(hcu_sound_requests_submit(&q, &r));
		}
		drained += (uint32_t)hcu_sound_requests_drain_each(&q, count_one, &seen, 64u);
	}
	hcu_sound_requests_counters(&q, &c);
	assert(c.submitted == 600 && c.rejected == 0 && c.evicted == 0);
	assert(c.accepted + c.coalesced == 600);
	assert(c.drained == c.accepted && c.pending == 0 && q.count == 0);
	assert(c.high_water <= 40);
	assert(drained == c.accepted && seen == drained);
	printf("PASS 600 mixed requests drained per tick: rejected=0 coalesced=%u\n",
		(unsigned)c.coalesced);
}

static void test_coalescing(void)
{
	static hcu_sound_request_queue q;
	hcu_sound_request_counters c;
	hcu_sound_request r;
	collect_t got;
	uint32_t i;
	hcu_sound_requests_init(&q);
	r = perm_req(0x42u, 0x1);
	for (i = 0; i < 3; ++i)
		assert(hcu_sound_requests_submit(&q, &r));
	r = perm_req(0x42u, 0x2); /* different flags: separate record */
	assert(hcu_sound_requests_submit(&q, &r));
	hcu_sound_requests_counters(&q, &c);
	assert(c.coalesced == 2 && c.accepted == 2 && c.submitted == 4 && q.count == 2);
	got.n = 0;
	assert(hcu_sound_requests_drain_each(&q, collect_one, &got, 8u) == 2);
	assert(got.event[0] == HCU_SOUND_EVENT_PERMUTATION_REQUEST);
	assert(q.counters.pending == 0);

	/* Saturation: one record repeats 255 times, then a new record starts. */
	hcu_sound_requests_init(&q);
	r = perm_req(0x77u, 0x1);
	for (i = 0; i < 300; ++i)
		assert(hcu_sound_requests_submit(&q, &r));
	hcu_sound_requests_counters(&q, &c);
	assert(c.accepted == 2 && c.coalesced == 298 && q.count == 2);
	{
		hcu_sound_request first;
		assert(hcu_sound_requests_drain(&q, &first, 1u) == 1u);
		assert(first.repeat == 255u);
	}

	/* Only the last 8 slots are searched: a match 9 records back is not merged. */
	hcu_sound_requests_init(&q);
	r = perm_req(0x99u, 0x1);
	assert(hcu_sound_requests_submit(&q, &r));
	for (i = 0; i < 8; ++i) {
		hcu_sound_request p = play_req(HCU_SOUND_EVENT_IMPULSE, 1, i, 9u);
		assert(hcu_sound_requests_submit(&q, &p));
	}
	assert(hcu_sound_requests_submit(&q, &r));
	hcu_sound_requests_counters(&q, &c);
	assert(c.coalesced == 0 && c.accepted == 10);
	printf("PASS permutation coalescing: merges, flags, window and repeat cap\n");
}

static void test_eviction_order(void)
{
	static hcu_sound_request_queue q;
	hcu_sound_request_counters c;
	hcu_sound_request r;
	collect_t got;
	uint32_t i;
	hcu_sound_requests_init(&q);
	for (i = 0; i < 32; ++i) {
		r = perm_req(100u + i, 0);
		assert(hcu_sound_requests_submit(&q, &r));
	}
	for (i = 0; i < 32; ++i) {
		r = play_req(HCU_SOUND_EVENT_IMPULSE, 2, i, 5u);
		assert(hcu_sound_requests_submit(&q, &r));
	}
	assert(q.count == HCU_SOUND_REQUEST_CAPACITY);
	/* Full ring: each high-priority impulse evicts the oldest cache request. */
	for (i = 0; i < 32; ++i) {
		r = play_req(HCU_SOUND_EVENT_IMPULSE, 5, 900u + i, 6u);
		assert(hcu_sound_requests_submit(&q, &r));
	}
	hcu_sound_requests_counters(&q, &c);
	assert(c.evicted == 32 && c.rejected == 0);
	/* No cache requests left: a strictly lower priority impulse is evicted next. */
	r = play_req(HCU_SOUND_EVENT_IMPULSE, 5, 950u, 6u);
	assert(hcu_sound_requests_submit(&q, &r));
	/* Equal priority is not evicted, so this one is rejected. */
	r = play_req(HCU_SOUND_EVENT_IMPULSE, 2, 951u, 6u);
	assert(!hcu_sound_requests_submit(&q, &r));
	hcu_sound_requests_counters(&q, &c);
	assert(c.evicted == 33 && c.rejected == 1 && q.count == HCU_SOUND_REQUEST_CAPACITY);
	got.n = 0;
	assert(hcu_sound_requests_drain_each(&q, collect_one, &got, 64u) == 64);
	for (i = 1; i < got.n; ++i)
		assert(got.sequence[i] > got.sequence[i - 1]);
	assert(got.sound[0] == 1u && got.sound[got.n - 1] == 950u);
	printf("PASS eviction order: cache requests first, strictly lower priority next\n");
}

static void test_stop_after_start(void)
{
	static hcu_sound_request_queue q;
	hcu_sound_request_counters c;
	hcu_sound_request r;
	collect_t got;
	uint32_t i;
	hcu_sound_requests_init(&q);
	r = play_req(HCU_SOUND_EVENT_LOOPING_START, 4, 3u, 0x55u);
	assert(hcu_sound_requests_submit(&q, &r));
	for (i = 0; i < 63; ++i) {
		r = play_req(HCU_SOUND_EVENT_IMPULSE, 1, i, 0x66u);
		assert(hcu_sound_requests_submit(&q, &r));
	}
	/* Ring is full. The matching STOP is kept by evicting an impulse. */
	r = play_req(HCU_SOUND_EVENT_STOP, 0, 3u, 0x55u);
	assert(hcu_sound_requests_submit(&q, &r));
	/* Ring of a START plus stops for another loop: a matching stop still gets in. */
	hcu_sound_requests_reset(&q);
	r = play_req(HCU_SOUND_EVENT_LOOPING_START, 4, 3u, 0x55u);
	assert(hcu_sound_requests_submit(&q, &r));
	for (i = 0; i < 63; ++i) {
		r = play_req(HCU_SOUND_EVENT_LOOPING_STOP, 0, 8u, 0x77u);
		assert(hcu_sound_requests_submit(&q, &r));
	}
	r = play_req(HCU_SOUND_EVENT_LOOPING_STOP, 0, 3u, 0x55u);
	assert(hcu_sound_requests_submit(&q, &r));
	hcu_sound_requests_counters(&q, &c);
	assert(c.rejected == 0);
	got.n = 0;
	assert(hcu_sound_requests_drain_each(&q, collect_one, &got, 64u) == 64);
	{
		int start_kept = 0, stop_kept = 0;
		for (i = 0; i < got.n; ++i) {
			if (got.event[i] == HCU_SOUND_EVENT_LOOPING_START) start_kept = 1;
			if (got.event[i] == HCU_SOUND_EVENT_LOOPING_STOP &&
				got.sound[i] == 3u) stop_kept = 1;
		}
		assert(start_kept && stop_kept);
	}
	printf("PASS STOP-after-START: matching stop is never refused while the ring is full\n");
}

static void test_power_of_two_wrap(void)
{
	static hcu_sound_request_queue q;
	static uint32_t last_sound;
	uint32_t next = 0, want = 0, t;
	collect_t got;
	hcu_sound_requests_init(&q);
	for (t = 0; t < 400; ++t) {
		uint32_t n = 1u + (t * 37u) % 61u, j;
		for (j = 0; j < n; ++j) {
			hcu_sound_request r = play_req(HCU_SOUND_EVENT_IMPULSE, 1, next++, 1u);
			assert(hcu_sound_requests_submit(&q, &r));
		}
		got.n = 0;
		assert(hcu_sound_requests_drain_each(&q, collect_one, &got, 64u) == n);
		for (j = 0; j < n; ++j) {
			assert(got.sound[j] == want);
			want++;
		}
	}
	last_sound = want;
	assert(q.count == 0 && q.head < HCU_SOUND_REQUEST_CAPACITY);
	assert(last_sound == next);
	printf("PASS power-of-two wrap: %u records across %u wraps\n",
		(unsigned)next, (unsigned)(next / HCU_SOUND_REQUEST_CAPACITY));
}

static void test_zero_copy_drain(void)
{
	static hcu_sound_request_queue q;
	collect_t got;
	hcu_sound_request out[4];
	uint32_t i;
	hcu_sound_requests_init(&q);
	for (i = 0; i < 10; ++i) {
		hcu_sound_request r = play_req(HCU_SOUND_EVENT_FADE, 1, i, 1u);
		assert(hcu_sound_requests_submit(&q, &r));
	}
	got.n = 0;
	assert(hcu_sound_requests_drain_each(&q, collect_one, &got, 6u) == 6);
	for (i = 0; i < 6; ++i)
		assert(got.sound[i] == i && got.sequence[i] == got.sequence[0] + i);
	/* Legacy copy drain still returns the rest in order. */
	assert(hcu_sound_requests_drain(&q, out, 4u) == 4);
	assert(out[0].sound_index == 6u && out[3].sound_index == 9u);
	assert(q.count == 0);
	printf("PASS zero-copy drain: in-place callback order matches the legacy drain\n");
}

/* Field coverage: known bits, position gated on has_position, priority range,
 * checksum fold across drain, eviction and reset. */
static void test_field_coverage(void)
{
	hcu_sound_request_queue q;
	hcu_sound_coverage cov;
	hcu_sound_request r;
	hcu_sound_request out[8];
	size_t n;
	uint32_t i;

	hcu_sound_requests_init(&q);
	hcu_sound_requests_coverage(&q, &cov);
	assert(cov.priority_min == 255u && cov.priority_max == 0u && cov.playback == 0u);

	/* Fully known impulse, priority 9. */
	r = play_req(HCU_SOUND_EVENT_IMPULSE, 9, 3u, 0x55u);
	assert(hcu_sound_requests_submit(&q, &r));
	/* Looping start without position: priority, gain, pitch known; owner and position not. */
	r = play_req(HCU_SOUND_EVENT_LOOPING_START, 2, 4u, 0x66u);
	r.has_position = 0;
	r.metadata_known = 0x1cu;
	assert(hcu_sound_requests_submit(&q, &r));
	/* Fade whose gain and pitch are not known. */
	r = play_req(HCU_SOUND_EVENT_FADE, 200, 5u, 0x77u);
	r.metadata_known = 0x07u;
	assert(hcu_sound_requests_submit(&q, &r));
	/* Permutation request: kinds only, no playback field coverage. */
	r = perm_req(0x99u, 0x1u);
	r.metadata_known = 0;
	r.owner_datum = UINT32_MAX;
	r.priority = UINT8_MAX;
	r.gain = 0.0f;
	r.pitch = 0.0f;
	assert(hcu_sound_requests_submit(&q, &r));

	n = hcu_sound_requests_drain(&q, out, 8);
	assert(n == 4);
	hcu_sound_requests_coverage(&q, &cov);
	assert(cov.kinds[HCU_SOUND_EVENT_IMPULSE] == 1u);
	assert(cov.kinds[HCU_SOUND_EVENT_LOOPING_START] == 1u);
	assert(cov.kinds[HCU_SOUND_EVENT_FADE] == 1u);
	assert(cov.kinds[HCU_SOUND_EVENT_PERMUTATION_REQUEST] == 1u);
	assert(cov.playback == 3u);
	assert(cov.owner_known == 2u);      /* impulse and fade; looping start lacks bit 0 */
	assert(cov.position_known == 2u);   /* impulse and fade; looping start has no position */
	assert(cov.priority_known == 3u);   /* all three playback records */
	assert(cov.gain_known == 2u);       /* impulse and looping start */
	assert(cov.pitch_known == 2u);
	assert(cov.priority_min == 2u && cov.priority_max == 200u);
	assert(cov.record_fold == cov.checksum && cov.out_fold == 0u);

	/* Checksum is order-independent and changes with a preserved field. */
	{
		hcu_sound_request a = play_req(HCU_SOUND_EVENT_IMPULSE, 4, 1u, 0x10u);
		hcu_sound_request b = play_req(HCU_SOUND_EVENT_IMPULSE, 4, 1u, 0x10u);
		uint32_t before, after;
		hcu_sound_request_queue z;
		hcu_sound_requests_init(&z);
		assert(hcu_sound_requests_submit(&z, &a));
		hcu_sound_requests_coverage(&z, &cov);
		before = cov.record_fold;
		hcu_sound_requests_init(&z);
		b.gain = 0.5f;
		assert(hcu_sound_requests_submit(&z, &b));
		hcu_sound_requests_coverage(&z, &cov);
		after = cov.record_fold;
		assert(before != after);
	}

	/* Eviction and reset move the record into out_fold; the invariant still holds. */
	hcu_sound_requests_init(&q);
	for (i = 0; i < HCU_SOUND_REQUEST_CAPACITY; ++i) {
		r = play_req(HCU_SOUND_EVENT_IMPULSE, 1, 10u + i, 0x20u + i);
		assert(hcu_sound_requests_submit(&q, &r));
	}
	r = play_req(HCU_SOUND_EVENT_STOP, 3, 99u, 0x20u);
	assert(hcu_sound_requests_submit(&q, &r)); /* evicts the oldest impulse */
	hcu_sound_requests_coverage(&q, &cov);
	assert(cov.out_fold != 0u);
	hcu_sound_requests_reset(&q);
	hcu_sound_requests_coverage(&q, &cov);
	assert(hcu_sound_requests_submit(&q, &r));
	n = hcu_sound_requests_drain(&q, out, 8);
	assert(n == 1);
	hcu_sound_requests_coverage(&q, &cov);
	/* Drained records equal accepted records minus those dropped unsent. */
	assert((cov.record_fold ^ cov.out_fold) == cov.checksum);
	assert(cov.kinds[HCU_SOUND_EVENT_STOP] == 1u);
}

static hcu_sound_request_queue queue;

int main(void)
{
	hcu_sound_request in[HCU_SOUND_REQUEST_CAPACITY + 4];
	hcu_sound_request out[HCU_SOUND_REQUEST_CAPACITY + 4];
	hcu_sound_request_counters c;
	hcu_sound_request_queue bridge_queue;
	size_t n, i;
	float position[3] = { 10.5f, -2.25f, 4.0f };
	hcu_sound_request playback;

	assert(hcu_sound_request_capture_playback(&playback,
		HCU_SOUND_EVENT_IMPULSE, 0xabcdefu, 0x123456u,
		HCU_SOUND_OWNER_OBJECT, 0x765432u, 1, position, 7u,
		0.625f, 1.25f, 9876u, 0x3fu));
	assert(playback.event == HCU_SOUND_EVENT_IMPULSE);
	assert(playback.permutation == 0xabcdefu && playback.sound_index == 0x123456u);
	assert(playback.owner_kind == HCU_SOUND_OWNER_OBJECT && playback.owner_datum == 0x765432u);
	assert(playback.has_position && playback.position[0] == 10.5f &&
		playback.position[1] == -2.25f && playback.position[2] == 4.0f);
	assert(playback.priority == 7u && playback.gain == 0.625f && playback.pitch == 1.25f);
	assert(playback.game_time == 9876u && playback.metadata_known == 0x3fu);
	assert(playback.accepted == 1u);
	hcu_sound_requests_init(&bridge_queue);
	assert(hcu_sound_requests_submit(&bridge_queue, &playback));
	assert(hcu_sound_requests_drain(&bridge_queue, out, 1u) == 1u);
	assert(out[0].event == HCU_SOUND_EVENT_IMPULSE &&
		out[0].sound_index == 0x123456u && out[0].owner_datum == 0x765432u);
	assert(out[0].position[1] == -2.25f && out[0].priority == 7u &&
		out[0].gain == 0.625f && out[0].pitch == 1.25f && out[0].game_time == 9876u);
	assert(!hcu_sound_request_capture_playback(&playback,
		HCU_SOUND_EVENT_IMPULSE, 1u, 2u, HCU_SOUND_OWNER_OBJECT, 3u,
		1, position, 1u, NAN, 1.0f, 1u, 0x3fu));
	assert(!hcu_sound_request_capture_playback(&playback,
		HCU_SOUND_EVENT_IMPULSE, 1u, 2u, HCU_SOUND_OWNER_OBJECT, 3u,
		1, position, 1u, 1.0f, INFINITY, 1u, 0x3fu));
	assert(!hcu_sound_request_capture_playback(&playback,
		HCU_SOUND_EVENT_IMPULSE, 1u, 2u, HCU_SOUND_OWNER_OBJECT, 3u,
		1, (const float[3]){ 0.0f, NAN, 0.0f }, 1u,
		1.0f, 1.0f, 1u, 0x3fu));
	assert(hcu_sound_request_capture_playback(&playback,
		HCU_SOUND_EVENT_STOP, 0xabcdu, 0x1234u,
		HCU_SOUND_OWNER_CE_SOURCE, 0x9988u, 0, NULL, 4u,
		0.0f, 1.0f, 123u, 0x37u));
	assert(playback.event == HCU_SOUND_EVENT_STOP && !playback.has_position);
	assert(playback.owner_kind == HCU_SOUND_OWNER_CE_SOURCE &&
		playback.owner_datum == 0x9988u && playback.sound_index == 0x1234u);
	assert(playback.metadata_known == 0x37u && playback.pitch == 1.0f);

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
		in[i] = make(HCU_SOUND_EVENT_PERMUTATION_REQUEST, (uint32_t)(0x100u + i));
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
		assert(out[i].accepted == 1u && out[i].metadata_known == 0x3fu);
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

	test_tick_drain_burst();
	test_coalescing();
	test_eviction_order();
	test_stop_after_start();
	test_power_of_two_wrap();
	test_zero_copy_drain();
	test_field_coverage();

	hcu_sound_requests_print(&queue, "fixture");
	printf("PASS sound request recorder: bounded ring, ordered drain, validation, counters\n");
	return 0;
}
