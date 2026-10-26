#include <limits.h>
#include <stdio.h>
#include "halo_ps2_scheduler.h"

#define CHECK(x) do { if (!(x)) { fprintf(stderr, "scheduler check failed at %d: %s\n", __LINE__, #x); return 1; } } while (0)

static int frame_rate(unsigned frames_per_second)
{
	halo_ps2_scheduler scheduler;
	unsigned frame, ticks = 0, input_samples = 0, rendered = 0;
	unsigned long long previous = 0;
	halo_ps2_scheduler_reset(&scheduler);
	for (frame = 1; frame <= frames_per_second * 20; ++frame) {
		unsigned long long now = (unsigned long long)frame * 1000000 / frames_per_second;
		unsigned dropped = 99;
		unsigned steps = halo_ps2_scheduler_advance(&scheduler, now - previous, &dropped);
		CHECK(steps <= HALO_PS2_SCHEDULER_MAX_STEPS);
		CHECK(dropped == 0);
		ticks += steps;
		input_samples += steps;
		if (steps) ++rendered;
		previous = now;
	}
	/* Movement integrates the same 600 fixed steps over 20 seconds even
	 * though the render opportunities and input polling batch sizes differ. */
	CHECK(ticks == 600);
	CHECK(input_samples == 600);
	CHECK(rendered <= frames_per_second * 20 && rendered <= ticks);
	if (frames_per_second == 15) CHECK(rendered == 300);
	CHECK(scheduler.accumulated_units == 0);
	CHECK(scheduler.dropped_ticks == 0);
	return 0;
}

int main(void)
{
	halo_ps2_scheduler scheduler;
	unsigned dropped, steps, i;
	unsigned long long elapsed = 0, ticks = 0;
	const unsigned intervals[] = {10000, 90000, 33333, 66667, 120000, 1000, 25000};
	CHECK(frame_rate(15) == 0);
	CHECK(frame_rate(30) == 0);
	CHECK(frame_rate(60) == 0);
	halo_ps2_scheduler_reset(&scheduler);
	for (i = 0; i < 7000; ++i) {
		unsigned interval = intervals[i % 7];
		elapsed += interval;
		ticks += halo_ps2_scheduler_advance(&scheduler, interval, &dropped);
		CHECK(dropped == 0);
		CHECK(ticks == elapsed * 30 / 1000000);
		CHECK(scheduler.accumulated_units == elapsed * 30 % 1000000);
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
	CHECK(steps == 4 && dropped == 56);
	CHECK(scheduler.dropped_ticks == 56 && scheduler.accumulated_units == 0);
	halo_ps2_scheduler_reset(&scheduler);
	steps = halo_ps2_scheduler_advance(&scheduler, 250001, &dropped);
	CHECK(steps == 4 && dropped == 3);
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
