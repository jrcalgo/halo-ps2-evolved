#include "stream/hcu_survival.h"

#include <stdio.h>
#include <string.h>

static int failures;

#define CHECK(cond, label)                                                  \
	do {                                                                    \
		if (!(cond)) {                                                      \
			printf("FAIL %s: %s (line %d)\n", label, #cond, __LINE__);      \
			failures++;                                                     \
		}                                                                   \
	} while (0)

static hcu_survival_config default_config(unsigned int humans, unsigned int limit)
{
	hcu_survival_config cfg;
	memset(&cfg, 0, sizeof cfg);
	cfg.difficulty = HCU_SURVIVAL_DIFFICULTY_NORMAL;
	cfg.seed = 0u;
	cfg.humans = humans;
	cfg.active_limit = limit;
	cfg.templates = NULL;
	cfg.template_count = 0u;
	return cfg;
}

/* Every tick-level invariant the contract promises. */
static void check_invariants(const hcu_survival *s, const char *where)
{
	unsigned int i;
	unsigned int alive_units = 0u;

	CHECK(hcu_survival_active_units(s) == hcu_survival_recount_active_units(s), where);
	CHECK(hcu_survival_batch_size(s) <= s->active_limit, where);
	CHECK(hcu_survival_reserved_units(s) <= s->active_limit, where);
	CHECK(hcu_survival_active_units(s) <= hcu_survival_reserved_units(s), where);
	for (i = 0u; i < hcu_survival_batch_size(s); i++) {
		const hcu_survival_enemy *e = hcu_survival_enemy_at(s, i);
		if (e->alive) {
			alive_units += e->units;
			CHECK(e->units == 1u + e->mounted + e->swarm + e->secondary, where);
		}
	}
	CHECK(alive_units == hcu_survival_active_units(s), where);
}

static unsigned int kill_all_enemies_two_ticks(hcu_survival *s)
{
	unsigned int i;
	unsigned int n = hcu_survival_batch_size(s);

	for (i = 0u; i < n; i += 2u) {
		(void)hcu_survival_kill_enemy(s, i);
	}
	hcu_survival_tick(s);
	for (i = 1u; i < n; i += 2u) {
		(void)hcu_survival_kill_enemy(s, i);
	}
	hcu_survival_tick(s);
	return n;
}

static void test_validation(void)
{
	hcu_survival_config cfg = default_config(2u, 16u);
	hcu_survival_template big = {1u, 0u, 20u, 0u, 0u}; /* worst unit 21 > limit 16 */
	hcu_survival_template ok = {1u, 0u, 0u, 0u, 0u};

	CHECK(hcu_survival_validate(&cfg) == HCU_SURVIVAL_OK, "default config valid");
	cfg.difficulty = HCU_SURVIVAL_DIFFICULTY_LEGENDARY;
	CHECK(hcu_survival_validate(&cfg) == HCU_SURVIVAL_ERR_UNSUPPORTED, "legendary refused");
	cfg.difficulty = HCU_SURVIVAL_DIFFICULTY_NORMAL;
	cfg.seed = 0x12345u;
	CHECK(hcu_survival_validate(&cfg) == HCU_SURVIVAL_ERR_UNSUPPORTED, "unqualified seed refused");
	cfg.seed = 0x5EED0002u;
	CHECK(hcu_survival_validate(&cfg) == HCU_SURVIVAL_OK, "qualified seed accepted");
	cfg.humans = 0u;
	CHECK(hcu_survival_validate(&cfg) == HCU_SURVIVAL_ERR_ARG, "zero humans refused");
	cfg.humans = 2u;
	cfg.active_limit = 0u;
	CHECK(hcu_survival_validate(&cfg) == HCU_SURVIVAL_ERR_ARG, "zero limit refused");
	cfg.active_limit = 16u;
	cfg.templates = &big;
	cfg.template_count = 1u;
	CHECK(hcu_survival_validate(&cfg) == HCU_SURVIVAL_ERR_LIMIT, "oversized template refused");
	cfg.templates = &ok;
	CHECK(hcu_survival_validate(&cfg) == HCU_SURVIVAL_OK, "single template accepted");
	printf("validation: ok\n");
}

static void test_repeated_mixed_waves(void)
{
	hcu_survival_config cfg = default_config(2u, 16u);
	hcu_survival s;
	unsigned int wave;
	unsigned int n;
	unsigned int prev_wave = 0u;
	const hcu_survival_enemy *first_slot;
	unsigned int distinct_batches_seen[HCU_SURVIVAL_ACTIVE_LIMIT_MAX + 1u];
	unsigned int idx;

	memset(distinct_batches_seen, 0, sizeof distinct_batches_seen);
	CHECK(hcu_survival_init(&s, &cfg) == HCU_SURVIVAL_OK, "init mixed");
	CHECK(hcu_survival_begin(&s) == HCU_SURVIVAL_OK, "begin mixed");
	first_slot = hcu_survival_enemy_at(&s, 0u);
	CHECK(hcu_survival_get_state(&s) == HCU_SURVIVAL_STATE_ACTIVE_WAVE, "wave 1 active");

	for (wave = 1u; wave <= 1200u; wave++) {
		unsigned int t;

		CHECK(hcu_survival_wave_number(&s) == wave, "wave number advances by one");
		CHECK(hcu_survival_get_state(&s) == HCU_SURVIVAL_STATE_ACTIVE_WAVE, "active during wave");
		check_invariants(&s, "mixed active");
		n = kill_all_enemies_two_ticks(&s);
		check_invariants(&s, "mixed cleared");
		CHECK(hcu_survival_get_state(&s) == HCU_SURVIVAL_STATE_INTERMISSION, "cleared enters intermission");
		CHECK(hcu_survival_living_humans(&s) == 2u, "humans survive a cleared wave");
		distinct_batches_seen[n]++;
		prev_wave = hcu_survival_wave_number(&s);

		for (t = 0u; t < HCU_SURVIVAL_INTERMISSION_TICKS - 1u; t++) {
			hcu_survival_tick(&s);
			CHECK(hcu_survival_get_state(&s) == HCU_SURVIVAL_STATE_INTERMISSION, "intermission holds");
		}
		hcu_survival_tick(&s);
		CHECK(hcu_survival_get_state(&s) == HCU_SURVIVAL_STATE_ACTIVE_WAVE, "next wave admitted");
		CHECK(hcu_survival_wave_number(&s) == prev_wave + 1u, "wave advanced after intermission");
		CHECK(first_slot == hcu_survival_enemy_at(&s, 0u), "enemy storage stable");
	}
	/* Some batches reached the active limit and some stayed at template size. */
	idx = 0u;
	for (n = 0u; n <= HCU_SURVIVAL_ACTIVE_LIMIT_MAX; n++) {
		if (distinct_batches_seen[n]) {
			idx++;
		}
	}
	CHECK(idx >= 3u, "mixed batch sizes cycle through several values");
	CHECK(distinct_batches_seen[16] == 0u, "no batch exceeds the limit");
	CHECK(s.enemies_admitted > 1000u, "many enemies admitted");
	CHECK(hcu_survival_get_state(&s) != HCU_SURVIVAL_STATE_GAME_OVER, "mixed run survives");
	printf("repeated mixed waves: ok (%u waves, %u enemies admitted)\n", hcu_survival_wave_number(&s), s.enemies_admitted);
}

static void test_storage_reuse(void)
{
	hcu_survival_config cfg = default_config(2u, 20u);
	hcu_survival s;
	const void *enemy_base;
	const void *human_base;
	const void *budget_base;
	unsigned int bytes_before;
	unsigned int wave;

	CHECK(hcu_survival_init(&s, &cfg) == HCU_SURVIVAL_OK, "init storage");
	bytes_before = hcu_survival_storage_bytes();
	CHECK(hcu_survival_begin(&s) == HCU_SURVIVAL_OK, "begin storage");
	enemy_base = &s.enemies[0];
	human_base = &s.humans[0];
	budget_base = &s.budgets[0];
	for (wave = 0u; wave < 1000u; wave++) {
		(void)kill_all_enemies_two_ticks(&s);
		{
			unsigned int t;
			for (t = 0u; t < HCU_SURVIVAL_INTERMISSION_TICKS; t++) {
				hcu_survival_tick(&s);
			}
		}
		CHECK(hcu_survival_get_state(&s) == HCU_SURVIVAL_STATE_ACTIVE_WAVE, "storage run stays active");
		if (hcu_survival_get_state(&s) != HCU_SURVIVAL_STATE_ACTIVE_WAVE) {
			break;
		}
	}
	CHECK(bytes_before == hcu_survival_storage_bytes(), "storage size constant");
	CHECK(enemy_base == &s.enemies[0], "enemy storage not reallocated");
	CHECK(human_base == &s.humans[0], "human storage not reallocated");
	CHECK(budget_base == &s.budgets[0], "budget storage not reallocated");
	CHECK(hcu_survival_wave_number(&s) == 1001u, "1000 cycles completed on fixed storage");
	printf("storage reuse: ok (%u bytes, %u waves)\n", bytes_before, hcu_survival_wave_number(&s));
}

static void test_same_tick_elimination(void)
{
	hcu_survival_config cfg = default_config(1u, 8u);
	hcu_survival s;

	CHECK(hcu_survival_init(&s, &cfg) == HCU_SURVIVAL_OK, "init elimination");
	CHECK(hcu_survival_begin(&s) == HCU_SURVIVAL_OK, "begin elimination");
	CHECK(hcu_survival_kill_human(&s, 0u) == HCU_SURVIVAL_OK, "queue human death");
	CHECK(hcu_survival_kill_enemy(&s, 0u) == HCU_SURVIVAL_OK, "queue last enemy death");
	{
		unsigned int i;
		for (i = 1u; i < hcu_survival_batch_size(&s); i++) {
			CHECK(hcu_survival_kill_enemy(&s, i) == HCU_SURVIVAL_OK, "queue remaining enemy death");
		}
	}
	hcu_survival_tick(&s);
	CHECK(hcu_survival_get_state(&s) == HCU_SURVIVAL_STATE_GAME_OVER, "last human down ends match same tick");
	CHECK(hcu_survival_living_humans(&s) == 0u, "no living humans at game over");
	CHECK(hcu_survival_recount_active_units(&s) == 0u, "no living enemies at game over");
	printf("same-tick elimination: ok\n");
}

static void test_no_active_wave_respawn(void)
{
	hcu_survival_config cfg = default_config(2u, 12u);
	hcu_survival s;
	unsigned int t;

	CHECK(hcu_survival_init(&s, &cfg) == HCU_SURVIVAL_OK, "init respawn");
	CHECK(hcu_survival_begin(&s) == HCU_SURVIVAL_OK, "begin respawn");
	CHECK(hcu_survival_kill_human(&s, 1u) == HCU_SURVIVAL_OK, "queue human 1 death");
	hcu_survival_tick(&s);
	CHECK(hcu_survival_living_humans(&s) == 1u, "one human left mid-wave");
	CHECK(hcu_survival_get_state(&s) == HCU_SURVIVAL_STATE_ACTIVE_WAVE, "wave continues with a survivor");
	CHECK(hcu_survival_kill_human(&s, 1u) == HCU_SURVIVAL_ERR_STATE, "dead human cannot die again");
	for (t = 0u; t < 6u; t++) {
		hcu_survival_tick(&s);
	}
	CHECK(hcu_survival_living_humans(&s) == 1u, "no respawn during active wave");
	CHECK(s.humans_respawned == 0u, "no respawn counted during active wave");
	/* Clear the wave; the dead human comes back only at the next admission. */
	(void)kill_all_enemies_two_ticks(&s);
	CHECK(hcu_survival_get_state(&s) == HCU_SURVIVAL_STATE_INTERMISSION, "wave cleared");
	CHECK(hcu_survival_living_humans(&s) == 1u, "no respawn at intermission start");
	for (t = 0u; t < HCU_SURVIVAL_INTERMISSION_TICKS; t++) {
		hcu_survival_tick(&s);
	}
	CHECK(hcu_survival_living_humans(&s) == 2u, "dead human respawned between waves");
	CHECK(s.humans_respawned == 1u, "exactly one respawn counted");
	printf("no active-wave respawn: ok\n");
}

static void test_intermission_length(void)
{
	hcu_survival_config cfg = default_config(1u, 4u);
	hcu_survival s;
	unsigned int t = 0u;

	CHECK(hcu_survival_init(&s, &cfg) == HCU_SURVIVAL_OK, "init intermission");
	CHECK(hcu_survival_begin(&s) == HCU_SURVIVAL_OK, "begin intermission");
	(void)kill_all_enemies_two_ticks(&s);
	CHECK(hcu_survival_get_state(&s) == HCU_SURVIVAL_STATE_INTERMISSION, "in intermission");
	while (hcu_survival_get_state(&s) == HCU_SURVIVAL_STATE_INTERMISSION) {
		hcu_survival_tick(&s);
		t++;
		if (t > 10000u) {
			break;
		}
	}
	CHECK(t == HCU_SURVIVAL_INTERMISSION_TICKS, "intermission lasts 5 s of 30 Hz ticks");
	CHECK(HCU_SURVIVAL_INTERMISSION_TICKS == 150u, "5 s is 150 ticks");
	printf("intermission length: ok (%u ticks)\n", t);
}

static void test_expansion_reservation(void)
{
	hcu_survival_config cfg = default_config(2u, 9u);
	hcu_survival s;
	unsigned int wave;
	unsigned int max_reserved = 0u;

	CHECK(hcu_survival_init(&s, &cfg) == HCU_SURVIVAL_OK, "init reservation");
	CHECK(hcu_survival_begin(&s) == HCU_SURVIVAL_OK, "begin reservation");
	for (wave = 0u; wave < 200u; wave++) {
		unsigned int reserved = hcu_survival_reserved_units(&s);
		unsigned int actual = hcu_survival_active_units(&s);
		if (reserved > max_reserved) {
			max_reserved = reserved;
		}
		CHECK(reserved <= 9u, "reservation fits active limit");
		CHECK(actual <= reserved, "actual units within reservation");
		CHECK(actual == hcu_survival_recount_active_units(&s), "active accounting equals recount");
		(void)kill_all_enemies_two_ticks(&s);
		{
			unsigned int t;
			for (t = 0u; t < HCU_SURVIVAL_INTERMISSION_TICKS; t++) {
				hcu_survival_tick(&s);
			}
		}
	}
	CHECK(max_reserved <= 9u, "maximum reservation within limit");
	CHECK(max_reserved >= 6u, "reservation actually reached expansion");
	printf("expansion reservation: ok (max reserved %u of 9)\n", max_reserved);
}

static void test_budgets(void)
{
	hcu_survival_config cfg = default_config(1u, 8u);
	hcu_survival s;
	uint32_t out[32];
	unsigned int i;
	unsigned int n;

	CHECK(hcu_survival_init(&s, &cfg) == HCU_SURVIVAL_OK, "init budgets");
	CHECK(hcu_survival_begin(&s) == HCU_SURVIVAL_OK, "begin budgets");

	/* Corpse ring: wraps and counts evictions; enemy and human slots are untouched. */
	for (i = 0u; i < 40u; i++) {
		(void)hcu_survival_budget_add(&s, HCU_SURVIVAL_BUDGET_CORPSE, 1000u + i);
	}
	CHECK(hcu_survival_budget_count(&s, HCU_SURVIVAL_BUDGET_CORPSE) == 16u, "corpse ring full at capacity");
	CHECK(hcu_survival_budget_evicted(&s, HCU_SURVIVAL_BUDGET_CORPSE) == 24u, "corpse evictions counted");
	CHECK(hcu_survival_get_state(&s) == HCU_SURVIVAL_STATE_ACTIVE_WAVE, "budget churn leaves wave live");
	CHECK(hcu_survival_active_units(&s) == hcu_survival_recount_active_units(&s), "budget churn keeps accounting");

	/* Deferred FIFO refuses at capacity and keeps earlier entries. */
	for (i = 0u; i < 16u; i++) {
		CHECK(hcu_survival_budget_add(&s, HCU_SURVIVAL_BUDGET_DEFERRED, 7u + i) == HCU_SURVIVAL_OK, "deferred accepted");
	}
	CHECK(hcu_survival_budget_add(&s, HCU_SURVIVAL_BUDGET_DEFERRED, 99u) == HCU_SURVIVAL_ERR_BUDGET, "deferred refused at capacity");
	CHECK(hcu_survival_budget_refused(&s, HCU_SURVIVAL_BUDGET_DEFERRED) == 1u, "deferred refusal counted");
	n = hcu_survival_deferred_drain(&s, out, 5u);
	CHECK(n == 5u, "drain partial");
	CHECK(out[0] == 7u && out[4] == 11u, "deferred drains FIFO");
	n = hcu_survival_deferred_drain(&s, out, 32u);
	CHECK(n == 11u, "remaining deferred drained");
	CHECK(out[10] == 22u, "last deferred in FIFO order");

	/* Projectile counter refuses at capacity and releases correctly. */
	for (i = 0u; i < 32u; i++) {
		CHECK(hcu_survival_projectile_acquire(&s) == HCU_SURVIVAL_OK, "projectile acquired");
	}
	CHECK(hcu_survival_projectile_acquire(&s) == HCU_SURVIVAL_ERR_BUDGET, "projectile refused at capacity");
	CHECK(hcu_survival_projectile_release(&s) == HCU_SURVIVAL_OK, "projectile released");
	CHECK(hcu_survival_budget_count(&s, HCU_SURVIVAL_BUDGET_PROJECTILE) == 31u, "projectile count after release");
	CHECK(hcu_survival_budget_add(&s, HCU_SURVIVAL_BUDGET_PROJECTILE, 1u) == HCU_SURVIVAL_ERR_ARG, "projectile add uses acquire");
	printf("budgets: ok\n");
}

static void test_refusal_leaves_match_untouched(void)
{
	hcu_survival_config cfg = default_config(2u, 8u);
	hcu_survival s;

	CHECK(hcu_survival_init(&s, &cfg) == HCU_SURVIVAL_OK, "init refusal");
	CHECK(hcu_survival_begin(&s) == HCU_SURVIVAL_OK, "begin refusal");
	cfg.difficulty = HCU_SURVIVAL_DIFFICULTY_HEAVY;
	CHECK(hcu_survival_init(&s, &cfg) == HCU_SURVIVAL_ERR_UNSUPPORTED, "unsupported init refused");
	CHECK(hcu_survival_get_state(&s) == HCU_SURVIVAL_STATE_ACTIVE_WAVE, "refused init leaves state");
	printf("refusal: ok\n");
}

int main(void)
{
	test_validation();
	test_repeated_mixed_waves();
	test_storage_reuse();
	test_same_tick_elimination();
	test_no_active_wave_respawn();
	test_intermission_length();
	test_expansion_reservation();
	test_budgets();
	test_refusal_leaves_match_untouched();
	if (failures != 0) {
		printf("hcu_survival tests failed: %d\n", failures);
		return 1;
	}
	printf("hcu_survival tests passed\n");
	return 0;
}
