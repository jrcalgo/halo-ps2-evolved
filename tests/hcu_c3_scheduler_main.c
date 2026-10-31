#include <limits.h>
#include <stdio.h>
#include "halo_ps2_scheduler.h"

#define CHECK(x) do { if (!(x)) { fprintf(stderr, "scheduler check failed at %d: %s\n", __LINE__, #x); return 1; } } while (0)

static int frame_rate(unsigned frames_per_second)
{
	halo_ps2_scheduler scheduler;
	unsigned frame, ticks = 0, input_samples = 0, rendered = 0, discarded = 0;
	unsigned long long previous = 0;
	halo_ps2_scheduler_reset(&scheduler);
	for (frame = 1; frame <= frames_per_second * 20; ++frame) {
		unsigned long long now = (unsigned long long)frame * 1000000 / frames_per_second;
		unsigned dropped = 99;
		unsigned steps = halo_ps2_scheduler_advance(&scheduler, now - previous, &dropped);
		CHECK(steps <= HALO_PS2_SCHEDULER_MAX_STEPS);
		ticks += steps;
		discarded += dropped;
		input_samples += steps;
		if (steps) ++rendered;
		previous = now;
	}
	/* Twenty seconds is 600 fixed ticks. 30 Hz and 60 Hz render often enough
	 * to run all of them. A 15 Hz frame periodically owes a third tick, and
	 * the two-step cap drops it. */
	CHECK(ticks + discarded == 600);
	CHECK(input_samples == ticks);
	CHECK(rendered <= frames_per_second * 20 && rendered <= ticks + discarded);
	if (frames_per_second == 15) {
		CHECK(rendered == 300);
		CHECK(ticks == 500 && discarded == 100);
	} else {
		CHECK(discarded == 0);
		CHECK(ticks == 600);
	}
	CHECK(scheduler.accumulated_units == 0);
	CHECK(scheduler.dropped_ticks == discarded);
	return 0;
}

int main(void)
{
	halo_ps2_scheduler scheduler;
	unsigned dropped, steps, i;
	unsigned long long elapsed = 0, ticks = 0, discarded = 0;
	const unsigned intervals[] = {10000, 90000, 33333, 66667, 120000, 1000, 25000};
	CHECK(frame_rate(15) == 0);
	CHECK(frame_rate(30) == 0);
	CHECK(frame_rate(60) == 0);
	/* Intervals longer than the catch-up cap drop the excess whole ticks.
	 * Executed steps plus dropped ticks still match elapsed time. */
	halo_ps2_scheduler_reset(&scheduler);
	for (i = 0; i < 7000; ++i) {
		unsigned interval = intervals[i % 7];
		elapsed += interval;
		steps = halo_ps2_scheduler_advance(&scheduler, interval, &dropped);
		ticks += steps;
		discarded += dropped;
		CHECK(steps <= HALO_PS2_SCHEDULER_MAX_STEPS);
		CHECK(ticks + discarded == elapsed * 30 / 1000000);
		CHECK(scheduler.accumulated_units == elapsed * 30 % 1000000);
		CHECK(scheduler.dropped_ticks == discarded);
	}
	/* An ordinary two-frame interval runs two fixed ticks, not a larger dt. */
	halo_ps2_scheduler_reset(&scheduler);
	CHECK(halo_ps2_scheduler_advance(&scheduler, 66667, &dropped) == 2);
	CHECK(dropped == 0 && scheduler.accumulated_units == 10);
	CHECK(halo_ps2_scheduler_advance(&scheduler, 0, &dropped) == 0);
	CHECK(scheduler.accumulated_units == 10);
	/* Long stalls bound CPU work but account for all discarded whole ticks
	 * and preserve the actual fractional phase. */
	halo_ps2_scheduler_reset(&scheduler);
	steps = halo_ps2_scheduler_advance(&scheduler, 2000000, &dropped);
	CHECK(steps == 2 && dropped == 58);
	CHECK(scheduler.dropped_ticks == 58 && scheduler.accumulated_units == 0);
	halo_ps2_scheduler_reset(&scheduler);
	steps = halo_ps2_scheduler_advance(&scheduler, 250001, &dropped);
	CHECK(steps == 2 && dropped == 5);
	CHECK(scheduler.accumulated_units == 500030);
	CHECK(halo_ps2_scheduler_advance(&scheduler, 16666, &dropped) == 1);
	CHECK(scheduler.accumulated_units == 10);
	halo_ps2_scheduler_reset(&scheduler);
	CHECK(scheduler.dropped_ticks == 0 && scheduler.accumulated_units == 0);
	dropped = 9;
	CHECK(halo_ps2_scheduler_advance(NULL, 1000000, &dropped) == 0 && dropped == 0);
	puts("scheduler-ok rates=15,30,60 fixed-hz=30 stalls=bounded phase=preserved input=per-step");
	return 0;
}
