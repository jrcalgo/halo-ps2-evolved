#ifndef HCU_BATCH_PROFILE_H
#define HCU_BATCH_PROFILE_H

/* Small, allocation-free accumulator shared by the sparse runtime logger and
 * its compiled host fixture. Durations are QPC ticks; phase slots are sums. */
typedef struct hcu_batch_profile_accumulator {
	unsigned count, step_total;
	unsigned interval_bins[8];
	unsigned long long phase_sums[8];
	unsigned long long min_interval, max_interval;
} hcu_batch_profile_accumulator;

typedef struct hcu_batch_profile_summary {
	unsigned count, step_total, interval_bins[8];
	unsigned long long phase_sums[8], min_interval, max_interval;
} hcu_batch_profile_summary;

static unsigned hcu_batch_profile_bin(unsigned long long ticks,
	unsigned long long frequency)
{
	/* Integer threshold comparisons avoid ticks*1000 overflow. */
	if (ticks < frequency / 100u) return 0;
	if (ticks < frequency / 50u) return 1;
	if (ticks < frequency * 3u / 100u) return 2;
	if (ticks < frequency * 4u / 100u) return 3;
	if (ticks < frequency * 6u / 100u) return 4;
	if (ticks < frequency / 10u) return 5;
	if (ticks < frequency / 5u) return 6;
	return 7;
}

static int hcu_batch_profile_add(hcu_batch_profile_accumulator *a,
	unsigned steps, const unsigned long long phases[8],
	unsigned long long interval, unsigned long long frequency,
	hcu_batch_profile_summary *out)
{
	unsigned i;
	if (!a || !phases || !out || !frequency) return -1;
	if (!a->count || interval < a->min_interval) a->min_interval = interval;
	if (!a->count || interval > a->max_interval) a->max_interval = interval;
	a->interval_bins[hcu_batch_profile_bin(interval, frequency)]++;
	for (i = 0; i < 8; ++i) a->phase_sums[i] += phases[i];
	a->step_total += steps;
	if (++a->count < 30u) return 0;
	out->count = a->count; out->step_total = a->step_total;
	out->min_interval = a->min_interval; out->max_interval = a->max_interval;
	for (i = 0; i < 8; ++i) {
		out->phase_sums[i] = a->phase_sums[i];
		out->interval_bins[i] = a->interval_bins[i];
	}
	*a = (hcu_batch_profile_accumulator){0};
	return 1;
}
#endif
