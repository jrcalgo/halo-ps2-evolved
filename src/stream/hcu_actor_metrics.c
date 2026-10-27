#include "stream/hcu_actor_metrics.h"

#include <string.h>

void hcu_actor_metrics_reset(hcu_actor_metrics *m)
{
	if (m)
		memset(m, 0, sizeof *m);
}

static void sample(hcu_actor_counter *c, uint32_t live)
{
	c->current = live;
	if (live > c->peak)
		c->peak = live;
	if (c->samples != UINT32_MAX)
		c->samples++;
}

static void bump_failure(hcu_actor_counter *c)
{
	if (c->failures != UINT32_MAX)
		c->failures++;
}

void hcu_actor_metrics_sample_bots(hcu_actor_metrics *m, uint32_t live_bots)
{
	if (m)
		sample(&m->spartan_bots, live_bots);
}

void hcu_actor_metrics_sample_retail(hcu_actor_metrics *m, uint32_t live_records)
{
	if (m)
		sample(&m->retail_actors, live_records);
}

void hcu_actor_metrics_sample_humans(hcu_actor_metrics *m, uint32_t humans)
{
	if (m)
		m->human_players = humans;
}

void hcu_actor_metrics_bot_failure(hcu_actor_metrics *m)
{
	if (m)
		bump_failure(&m->spartan_bots);
}

void hcu_actor_metrics_retail_failure(hcu_actor_metrics *m)
{
	if (m)
		bump_failure(&m->retail_actors);
}

int hcu_actor_metrics_bot_coverage_claimed(const hcu_actor_metrics *m)
{
	return m && m->spartan_bots.samples > 0 && m->spartan_bots.peak > 0;
}

int hcu_actor_metrics_retail_coverage_claimed(const hcu_actor_metrics *m)
{
	return m && m->retail_actors.samples > 0 && m->retail_actors.peak > 0;
}
