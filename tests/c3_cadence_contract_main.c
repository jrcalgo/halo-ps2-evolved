#include "halo_ps2_presentation_clock.h"
#include "stream/hcu_snapshot_bank.h"

#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

static uint8_t storage[2 * 1024 * 1024] __attribute__((aligned(16)));

static void test_60_opportunities_for_30_tick_clock(void)
{
	halo_ps2_presentation_clock p;
	uint64_t ns = 0;
	unsigned tick, presents = 0;
	halo_ps2_presentation_clock_init(&p, 60, ns);
	for (tick = 0; tick < 30; ++tick) {
		/* fixed simulation tick count is explicitly separate from presentation */
		ns += UINT64_C(1000000000) / 30u;
		presents += halo_ps2_presentation_clock_advance(&p, ns, 0);
	}
	assert(tick == 30);
	assert(presents == 59 || presents == 60); /* integer ns tick approximation */
	assert(p.dropped == 0);
	printf("cadence: 30 fixed ticks, %u presentation opportunities (not FPS evidence)\n", presents);
}

static void test_fractional_long_run_and_edges(void)
{
	halo_ps2_presentation_clock p;
	uint64_t i, due = 0;
	halo_ps2_presentation_clock_init(&p, 60, 100);
	for (i = 1; i <= 60000; ++i)
		due += halo_ps2_presentation_clock_advance(&p, 100 + i * 1000000u, 0);
	assert(due == 3600);
	assert(p.phase == 0);
	assert(halo_ps2_presentation_clock_advance(&p, p.last_ns + 10000000u, 0) == 0);
	assert(halo_ps2_presentation_clock_advance(&p, p.last_ns - 1u, 0) == 0);
	assert(halo_ps2_presentation_clock_advance(&p, p.last_ns + 1000000000u, 0) == 8);
	assert(p.dropped > 0);
	printf("cadence edges: fractional long-run, backward reset, clamp and dropped count ok\n");
}

static void test_pause_does_not_accumulate(void)
{
	halo_ps2_presentation_clock p;
	halo_ps2_presentation_clock_init(&p, 60, 0);
	assert(halo_ps2_presentation_clock_advance(&p, 10000000u, 0) == 0);
	assert(halo_ps2_presentation_clock_advance(&p, 1000000000u, 1) == 0);
	assert(halo_ps2_presentation_clock_advance(&p, 1010000000u, 0) == 0);
	assert(halo_ps2_presentation_clock_advance(&p, 1026666667u, 0) == 1);
	puts("cadence pause: pause and resume baseline ok");
}

static const halo_ps2_frame_snapshot *publish(uint32_t x)
{
	halo_ps2_frame_snapshot *s = hcu_snapshot_bank_begin_write();
	assert(s);
	s->view_count = 0;
	s->object_count = 0;
	(void)x;
	assert(hcu_snapshot_bank_commit(s) == 0);
	return hcu_snapshot_bank_latest();
}

static void test_two_endpoint_reader_contract(void)
{
	hcu_snapshot_reader ra = { 0, NULL }, rb = { 0, NULL };
	const halo_ps2_frame_snapshot *a, *b, *c;
	hcu_snapshot_bank_stats stats;
	assert(hcu_snapshot_bank_bind(storage, hcu_snapshot_bank_storage_required()) == 0);
	hcu_snapshot_bank_set_map_generation(7);
	a = publish(101);
	assert(hcu_snapshot_bank_begin_read(&ra) == a);
	b = publish(102);
	assert(b != a && hcu_snapshot_bank_begin_read(&rb) == b);
	assert(a->sequence == 1 && b->sequence == 2);
	c = publish(103);
	assert(c != a && c != b);
	assert(hcu_snapshot_bank_begin_write() == NULL);
	assert(a->sequence == 1 && b->sequence == 2);
	assert(a->map_generation == 7 && b->map_generation == 7);
	hcu_snapshot_bank_get_stats(&stats);
	assert(stats.write_refusals > 0);
	hcu_snapshot_bank_end_read(&ra);
	assert(hcu_snapshot_bank_begin_write() == (halo_ps2_frame_snapshot *)a);
	hcu_snapshot_bank_abandon((halo_ps2_frame_snapshot *)a);
	hcu_snapshot_bank_end_read(&rb);
	assert(hcu_snapshot_bank_unbind() == 0);
	puts("snapshot endpoints: A/B pinned, C published, next write refused safely; payloads intact");
}

int main(void)
{
	test_60_opportunities_for_30_tick_clock();
	test_fractional_long_run_and_edges();
	test_pause_does_not_accumulate();
	test_two_endpoint_reader_contract();
	return 0;
}
