/* Host tests for C5 actor metrics: bots and retail records are separate counters. */
#include <stdio.h>

#include "stream/hcu_actor_metrics.h"

static int failures;
#define CHECK(cond) do { if (!(cond)) { printf("FAIL %s:%d %s\n", __FILE__, __LINE__, #cond); failures++; } } while (0)

/* Zero retail records must not report zero Spartan bots. */
static void test_zero_retail_does_not_zero_bots(void)
{
	hcu_actor_metrics m;
	hcu_actor_metrics_reset(&m);
	hcu_actor_metrics_sample_retail(&m, 0);
	hcu_actor_metrics_sample_bots(&m, 4);
	CHECK(m.retail_actors.peak == 0);
	CHECK(m.spartan_bots.peak == 4);
	CHECK(m.spartan_bots.current == 4);
	CHECK(!hcu_actor_metrics_retail_coverage_claimed(&m));
	CHECK(hcu_actor_metrics_bot_coverage_claimed(&m));
}

/* Player-only run: humans are sampled, bots never are, so no bot coverage is claimed. */
static void test_player_only_claims_no_bot_coverage(void)
{
	hcu_actor_metrics m;
	hcu_actor_metrics_reset(&m);
	hcu_actor_metrics_sample_humans(&m, 4);
	hcu_actor_metrics_sample_retail(&m, 0);
	CHECK(m.human_players == 4);
	CHECK(m.spartan_bots.samples == 0);
	CHECK(!hcu_actor_metrics_bot_coverage_claimed(&m));
	CHECK(!hcu_actor_metrics_retail_coverage_claimed(&m));
}

/* Measured bots with zero sampled bots peak is still not a bot coverage claim. */
static void test_measured_zero_bots_is_not_coverage(void)
{
	hcu_actor_metrics m;
	hcu_actor_metrics_reset(&m);
	hcu_actor_metrics_sample_bots(&m, 0);
	CHECK(m.spartan_bots.samples == 1);
	CHECK(!hcu_actor_metrics_bot_coverage_claimed(&m));
}

/* Peak tracks the maximum, current tracks the last sample, failures stay separate. */
static void test_peak_current_and_failures(void)
{
	hcu_actor_metrics m;
	hcu_actor_metrics_reset(&m);
	hcu_actor_metrics_sample_retail(&m, 7);
	hcu_actor_metrics_sample_retail(&m, 3);
	hcu_actor_metrics_retail_failure(&m);
	hcu_actor_metrics_bot_failure(&m);
	hcu_actor_metrics_bot_failure(&m);
	CHECK(m.retail_actors.peak == 7);
	CHECK(m.retail_actors.current == 3);
	CHECK(m.retail_actors.failures == 1);
	CHECK(m.spartan_bots.failures == 2);
	CHECK(m.spartan_bots.peak == 0);
	CHECK(hcu_actor_metrics_retail_coverage_claimed(&m));
	CHECK(!hcu_actor_metrics_bot_coverage_claimed(&m));
}

static void test_null_and_reset(void)
{
	hcu_actor_metrics m;
	hcu_actor_metrics_reset(NULL);
	hcu_actor_metrics_sample_bots(NULL, 9);
	hcu_actor_metrics_retail_failure(NULL);
	CHECK(!hcu_actor_metrics_bot_coverage_claimed(NULL));
	hcu_actor_metrics_reset(&m);
	hcu_actor_metrics_sample_bots(&m, 2);
	hcu_actor_metrics_reset(&m);
	CHECK(m.spartan_bots.peak == 0 && m.spartan_bots.samples == 0);
}

int main(void)
{
	test_zero_retail_does_not_zero_bots();
	test_player_only_claims_no_bot_coverage();
	test_measured_zero_bots_is_not_coverage();
	test_peak_current_and_failures();
	test_null_and_reset();
	if (failures) {
		printf("hcu_actor_metrics tests failed: %d\n", failures);
		return 1;
	}
	printf("hcu_actor_metrics tests passed\n");
	return 0;
}
