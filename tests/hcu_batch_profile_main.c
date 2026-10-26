#include "../src/stream/hcu_batch_profile.h"
#include <assert.h>
#include <string.h>

int main(void)
{
	hcu_batch_profile_accumulator a;
	hcu_batch_profile_summary s;
	unsigned long long p[8];
	unsigned i, rc;
	memset(&a, 0, sizeof a); memset(&s, 0, sizeof s);
	for (i = 0; i < 8; ++i) p[i] = i + 1;
	/* Invalid clock input is ignored without corrupting the pending window. */
	assert(hcu_batch_profile_add(&a, 1, p, 10, 0, &s) == -1);
	assert(a.count == 0);
	/* A 100 ms poll interval can contain sleep plus unassigned residual; each
	 * submitted interval and phase bucket is counted exactly once. */
	for (i = 0; i < 29; ++i) {
		p[7] = 4; rc = hcu_batch_profile_add(&a, 2, p, 100, 1000, &s);
		assert(rc == 0);
	}
	assert(a.count == 29);
	p[7] = 4;
	assert(hcu_batch_profile_add(&a, 1, p, 200, 1000, &s) == 1);
	assert(s.count == 30 && s.step_total == 59);
	assert(s.min_interval == 100 && s.max_interval == 200);
	assert(s.interval_bins[6] == 29 && s.interval_bins[7] == 1);
	for (i = 0; i < 7; ++i) assert(s.phase_sums[i] == (unsigned long long)(i+1)*30);
	assert(s.phase_sums[7] == 120);
	assert(a.count == 0 && a.phase_sums[7] == 0);
	/* Subsequent window is independent and catches the under-10 ms bin edge. */
	for (i = 0; i < 29; ++i)
		assert(hcu_batch_profile_add(&a, 0, p, 9, 1000, &s) == 0);
	assert(hcu_batch_profile_add(&a, 0, p, 10, 1000, &s) == 1);
	assert(s.count == 30 && s.interval_bins[0] == 29 && s.interval_bins[1] == 1);
	return 0;
}
