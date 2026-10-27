/* Host tests for the CE-side pure helpers (src/stream/hcu_survival_ce.c). Built with hcu_survival.c, which the
 * next-reservation check runs against. */
#include <stdio.h>
#include <string.h>

#include "hcu_survival_ce.h"

static int failures = 0;

#define CHECK(cond, label)                                                  \
	do {                                                                    \
		if (!(cond)) {                                                      \
			printf("FAIL: %s (%s:%d)\n", label, __FILE__, __LINE__);        \
			failures++;                                                     \
		}                                                                   \
	} while (0)

static void test_recipes(void)
{
	unsigned int i;
	unsigned int seen[HCU_SURVIVAL_CE_RECIPE_COUNT];

	memset(seen, 0, sizeof(seen));
	for (i = 0; i < HCU_SURVIVAL_CE_RECIPE_COUNT; i++) {
		const hcu_survival_ce_recipe *r = hcu_survival_ce_recipe_at(i);
		CHECK(r != NULL, "recipe present");
		CHECK(r && r->variant_path && r->variant_path[0] == 'c', "variant path set");
		CHECK(r && r->unit_path && r->unit_path[0] == 'c', "unit path set");
	}
	CHECK(hcu_survival_ce_recipe_at(HCU_SURVIVAL_CE_RECIPE_COUNT) == NULL, "recipe past the table is NULL");
	for (i = 0; i < HCU_SURVIVAL_CE_RECIPE_COUNT; i++) {
		unsigned int r = hcu_survival_ce_recipe_for(7u, i);
		CHECK(r < HCU_SURVIVAL_CE_RECIPE_COUNT, "recipe index in range");
		seen[r]++;
	}
	for (i = 0; i < HCU_SURVIVAL_CE_RECIPE_COUNT; i++)
		CHECK(seen[i] == 1u, "one wave's slots cover every recipe once");
	CHECK(hcu_survival_ce_recipe_for(1u, 0u) != hcu_survival_ce_recipe_for(2u, 0u), "the recipe moves with the wave");
	printf("recipes: ok\n");
}

static void test_bounds(void)
{
	hcu_survival_template t = {2u, 1u, 1u, 0u, 2u};

	CHECK(hcu_survival_ce_secondary_worst(0, 2) == 2u, "secondary worst is the upper bound");
	CHECK(hcu_survival_ce_secondary_worst(1, 1) == 1u, "equal bounds");
	CHECK(hcu_survival_ce_secondary_worst(0, 0) == 0u, "no secondary spawn");
	CHECK(hcu_survival_ce_secondary_worst(-1, -1) == 0u, "negative bound clamps to zero");
	CHECK(hcu_survival_ce_secondary_worst(3, 1) == 3u, "inverted range keeps the lower bound");
	CHECK(hcu_survival_ce_secondary_fits(&t, 2u), "secondary bound fits");
	CHECK(!hcu_survival_ce_secondary_fits(&t, 3u), "secondary bound above the template does not fit");
	CHECK(!hcu_survival_ce_secondary_fits(NULL, 0u), "NULL template does not fit");
	CHECK(hcu_survival_ce_within_worst(&t, 1u, 0u, 2u), "observed within worst");
	CHECK(!hcu_survival_ce_within_worst(&t, 2u, 0u, 0u), "mounted above worst");
	CHECK(!hcu_survival_ce_within_worst(&t, 0u, 1u, 0u), "swarm above worst");
	CHECK(!hcu_survival_ce_within_worst(&t, 0u, 0u, 3u), "secondary above worst");
	CHECK(!hcu_survival_ce_within_worst(NULL, 0u, 0u, 0u), "NULL template is not within");
	printf("bounds: ok\n");
}

static void test_pool(void)
{
	CHECK(hcu_survival_ce_may_place(0u, HCU_C5_ACTOR_RESERVE_MAX), "empty pool takes the full reserve");
	CHECK(!hcu_survival_ce_may_place(0u, HCU_C5_ACTOR_RESERVE_MAX + 1u), "one past the reserve is refused");
	CHECK(!hcu_survival_ce_may_place(HCU_C5_ACTOR_RESERVE_MAX + 1u, 0u), "live actors past the reserve refused");
	CHECK(hcu_survival_ce_may_place(100u, 92u), "exact fit");
	CHECK(!hcu_survival_ce_may_place(100u, 93u), "one over the fit");
	CHECK(!hcu_survival_ce_may_place(0xffffffffu, 0xffffffffu), "huge values cannot wrap into a fit");
	printf("pool: ok\n");
}

static void test_deaths_and_gate(void)
{
	CHECK(hcu_survival_ce_deaths_delta(3u, 3u) == 0u, "no deaths");
	CHECK(hcu_survival_ce_deaths_delta(3u, 5u) == 2u, "two deaths");
	CHECK(hcu_survival_ce_deaths_delta(0xffffffffu, 1u) == 2u, "wrapped counter gives the true delta");
	CHECK(hcu_survival_ce_respawn_allowed(1, 1, 4u, 4u), "respawn when gate open and no unseen death");
	CHECK(!hcu_survival_ce_respawn_allowed(0, 1, 4u, 4u), "dead for the match: no respawn");
	CHECK(!hcu_survival_ce_respawn_allowed(1, 0, 4u, 4u), "gate closed for this wave");
	CHECK(!hcu_survival_ce_respawn_allowed(1, 1, 5u, 4u), "unobserved death blocks the respawn");
	printf("deaths and gate: ok\n");
}

static void test_slots(void)
{
	hcu_survival_ce_slots slots;
	unsigned int i;

	hcu_survival_ce_slots_clear(&slots);
	for (i = 0; i < HCU_SURVIVAL_ACTIVE_LIMIT_MAX; i++)
		CHECK(slots.actor[i] == HCU_SURVIVAL_CE_NO_ACTOR, "clear marks every slot free");
	slots.actor[3] = 77;
	slots.actor[9] = 78;
	CHECK(hcu_survival_ce_slot_of_actor(&slots, 78) == 9u, "actor found in its slot");
	CHECK(hcu_survival_ce_slot_of_actor(&slots, 99) == HCU_SURVIVAL_CE_NO_SLOT, "unknown actor has no slot");
	CHECK(hcu_survival_ce_slot_of_actor(&slots, -1) == HCU_SURVIVAL_CE_NO_SLOT, "negative actor has no slot");
	CHECK(hcu_survival_ce_slot_of_actor(NULL, 77) == HCU_SURVIVAL_CE_NO_SLOT, "NULL table has no slot");
	slots.actor[3] = HCU_SURVIVAL_CE_NO_ACTOR;
	CHECK(hcu_survival_ce_slot_of_actor(&slots, 77) == HCU_SURVIVAL_CE_NO_SLOT, "retired slot no longer matches");
	printf("slots: ok\n");
}

static void test_human_for_slot(void)
{
	hcu_survival_config cfg;
	hcu_survival s;

	memset(&cfg, 0, sizeof(cfg));
	cfg.difficulty = HCU_SURVIVAL_DIFFICULTY_NORMAL;
	cfg.seed = 0u;
	cfg.humans = 3u;
	cfg.active_limit = 6u;
	CHECK(hcu_survival_init(&s, &cfg) == HCU_SURVIVAL_OK, "init for human test");
	CHECK(hcu_survival_ce_human_for_slot(&s, 0u) == HCU_SURVIVAL_CE_NO_HUMAN, "no living human, no owner");
	CHECK(hcu_survival_begin(&s) == HCU_SURVIVAL_OK, "begin for human test");
	CHECK(hcu_survival_ce_human_for_slot(&s, 0u) == 0u, "slot 0 serves human 0");
	CHECK(hcu_survival_ce_human_for_slot(&s, 4u) == 1u, "slot 4 serves human 1 of 3");
	s.humans[0].alive = 0u;
	CHECK(hcu_survival_ce_human_for_slot(&s, 0u) == 1u, "dead human 0 skipped");
	CHECK(hcu_survival_ce_human_for_slot(&s, 1u) == 2u, "slot 1 serves the second living human");
	s.humans[1].alive = 0u;
	s.humans[2].alive = 0u;
	CHECK(hcu_survival_ce_human_for_slot(&s, 2u) == HCU_SURVIVAL_CE_NO_HUMAN, "nobody lives");
	CHECK(hcu_survival_ce_human_for_slot(NULL, 0u) == HCU_SURVIVAL_CE_NO_HUMAN, "NULL core has no owner");
	printf("human for slot: ok\n");
}

/* The next-reservation read before a tick must equal what the tick admits, for every wave of a run. */
static void test_next_reserve_matches_admission(void)
{
	hcu_survival_config cfg;
	hcu_survival s;
	unsigned int wave;
	unsigned int i;

	memset(&cfg, 0, sizeof(cfg));
	cfg.difficulty = HCU_SURVIVAL_DIFFICULTY_NORMAL;
	cfg.humans = 2u;
	cfg.active_limit = 6u;
	CHECK(hcu_survival_init(&s, &cfg) == HCU_SURVIVAL_OK, "init for reserve test");
	CHECK(hcu_survival_begin(&s) == HCU_SURVIVAL_OK, "begin for reserve test");
	for (wave = 1u; wave <= 12u; wave++) {
		unsigned int predicted;

		CHECK(hcu_survival_get_state(&s) == HCU_SURVIVAL_STATE_ACTIVE_WAVE, "wave active");
		for (i = 0u; i < hcu_survival_batch_size(&s); i++)
			CHECK(hcu_survival_kill_enemy(&s, i) == HCU_SURVIVAL_OK, "kill enemy");
		hcu_survival_tick(&s); /* resolves the deaths: intermission starts */
		CHECK(hcu_survival_get_state(&s) == HCU_SURVIVAL_STATE_INTERMISSION, "intermission after the clear");
		/* the read happens on the last intermission tick, before the admitting tick */
		while (hcu_survival_intermission_left(&s) > 1u)
			hcu_survival_tick(&s);
		predicted = hcu_survival_ce_next_reserve(&s);
		hcu_survival_tick(&s);
		CHECK(hcu_survival_wave_number(&s) == wave + 1u, "next wave admitted");
		CHECK(hcu_survival_reserved_units(&s) == predicted, "predicted reservation equals admitted reservation");
	}
	printf("next reserve matches admission: ok\n");
}

static void test_raise_secondary(void)
{
	hcu_survival_config cfg;
	hcu_survival s;
	hcu_survival_template copy[HCU_SURVIVAL_TEMPLATES_MAX];
	unsigned int i;

	memset(&cfg, 0, sizeof(cfg));
	cfg.difficulty = HCU_SURVIVAL_DIFFICULTY_NORMAL;
	cfg.humans = 1u;
	cfg.active_limit = 6u;
	CHECK(hcu_survival_init(&s, &cfg) == HCU_SURVIVAL_OK, "init for raise test");
	CHECK(hcu_survival_ce_raise_secondary(s.tmpl, s.template_count, s.active_limit, 3u) == 1, "raise to 3 fits");
	for (i = 0u; i < s.template_count; i++)
		CHECK(s.tmpl[i].max_secondary >= 3u, "every template raised");
	memcpy(copy, s.tmpl, sizeof(copy));
	CHECK(hcu_survival_ce_raise_secondary(s.tmpl, s.template_count, 0u, 1u) == 1, "zero limit is trivially fine");
	CHECK(memcmp(copy, s.tmpl, sizeof(copy)) == 0, "a second raise to the same bound changes nothing");
	CHECK(hcu_survival_ce_raise_secondary(s.tmpl, s.template_count, 12u, 15u) == 0, "12 x 17 units refused");
	CHECK(hcu_survival_ce_raise_secondary(s.tmpl, s.template_count, 6u, 17u) == 0, "bound past the table refused");
	CHECK(hcu_survival_ce_raise_secondary(NULL, 1u, 6u, 1u) == 0, "NULL table refused");
	printf("raise secondary: ok\n");
}

int main(void)
{
	test_recipes();
	test_bounds();
	test_pool();
	test_deaths_and_gate();
	test_slots();
	test_human_for_slot();
	test_next_reserve_matches_admission();
	test_raise_secondary();
	if (failures) {
		printf("hcu_survival_ce tests failed: %d\n", failures);
		return 1;
	}
	printf("hcu_survival_ce tests passed\n");
	return 0;
}
