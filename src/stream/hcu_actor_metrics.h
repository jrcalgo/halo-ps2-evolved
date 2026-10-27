/* C5 actor metrics: Spartan player-backed bots and retail actor records are counted
 * separately. A zero retail count never implies zero bots, and a player-only run never
 * claims bot coverage. Pure: fixed storage, no heap, no I/O. */
#ifndef HALO_STREAM_HCU_ACTOR_METRICS_H
#define HALO_STREAM_HCU_ACTOR_METRICS_H

#include <stdint.h>

typedef struct {
	uint32_t current;   /* last sampled live count */
	uint32_t peak;      /* highest sampled live count */
	uint32_t failures;  /* allocation/placement failures reported by the caller */
	uint32_t samples;   /* number of sample calls; 0 means the counter was never measured */
} hcu_actor_counter;

typedef struct {
	hcu_actor_counter spartan_bots;  /* player-backed Spartan bots (CE player units) */
	hcu_actor_counter retail_actors; /* retail CE actor records (actor_new datums) */
	uint32_t human_players;          /* local/network humans, reported for context only */
} hcu_actor_metrics;

void hcu_actor_metrics_reset(hcu_actor_metrics *m);
void hcu_actor_metrics_sample_bots(hcu_actor_metrics *m, uint32_t live_bots);
void hcu_actor_metrics_sample_retail(hcu_actor_metrics *m, uint32_t live_records);
void hcu_actor_metrics_sample_humans(hcu_actor_metrics *m, uint32_t humans);
void hcu_actor_metrics_bot_failure(hcu_actor_metrics *m);
void hcu_actor_metrics_retail_failure(hcu_actor_metrics *m);

/* Coverage claims require at least one sample of that counter and a non-zero peak.
 * Zero measured records is a valid claim of "measured zero" only through samples>0. */
int hcu_actor_metrics_bot_coverage_claimed(const hcu_actor_metrics *m);
int hcu_actor_metrics_retail_coverage_claimed(const hcu_actor_metrics *m);

#endif
