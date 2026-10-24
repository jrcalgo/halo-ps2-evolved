#include "ps2_claim_intervals.h"
#include <stddef.h>

typedef char interval_entry_is_eight_bytes[
	sizeof(struct ps2_claim_interval) == 8 ? 1 : -1];
typedef char interval_context_is_forty_bytes[
	sizeof(struct ps2_claim_intervals) == 40 ? 1 : -1];
typedef char interval_counter_is_eight_aligned[
	offsetof(struct ps2_claim_intervals, comparisons) == 24 ? 1 : -1];
