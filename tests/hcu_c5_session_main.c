/* Host test for the C5 integration session (src/stream/hcu_c5_session.c) with fake CE hooks.
 * Prints one "name: ok" line per passing group, "FAIL ..." lines otherwise, and the hash field dump used by
 * tests/test_hcu_c5_session.py to recompute the documented hash order. */
#include "stream/hcu_c5_session.h"

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

/* ---- fakes --------------------------------------------------------------------------------------------- */

#define MAX_LINES 256
#define MAX_LINE_BYTES 256

struct fake_env {
	int teardown_calls;
	int teardown_status;
	int bots_calls;
	int bots_status;
	hcu_bot_config bot_config;
	struct hcu_coop_ce_binding bot_binding;
	uint64_t bot_hash_value;
	int lines;
	char text[MAX_LINES][MAX_LINE_BYTES];
};

static int fake_teardown(void *user, const hcu_local_setup_result *accepted)
{
	struct fake_env *env = (struct fake_env *)user;
	(void)accepted;
	env->teardown_calls++;
	return env->teardown_status;
}

static int fake_bots_start(void *user, const hcu_bot_config *config, const struct hcu_coop_ce_binding *binding)
{
	struct fake_env *env = (struct fake_env *)user;
	env->bots_calls++;
	env->bot_config = *config;
	env->bot_binding = *binding;
	return env->bots_status;
}

static uint64_t fake_bots_hash(void *user)
{
	struct fake_env *env = (struct fake_env *)user;
	return env->bot_hash_value;
}

static void fake_emit(void *user, const char *line)
{
	struct fake_env *env = (struct fake_env *)user;
	if (env->lines < MAX_LINES) {
		strncpy(env->text[env->lines], line, MAX_LINE_BYTES - 1);
		env->text[env->lines][MAX_LINE_BYTES - 1] = '\0';
		env->lines++;
	}
}

static int saw_line(const struct fake_env *env, const char *needle)
{
	int i;
	for (i = 0; i < env->lines; i++) {
		if (strstr(env->text[i], needle) != NULL) {
			return 1;
		}
	}
	return 0;
}

static void fake_init(struct fake_env *env)
{
	memset(env, 0, sizeof *env);
	env->bots_status = 0;
	env->teardown_status = 0;
	env->bot_hash_value = 0x1234u;
}

static struct hcu_c5_session_ops ops_for(struct fake_env *env)
{
	struct hcu_c5_session_ops ops;
	memset(&ops, 0, sizeof ops);
	ops.user = env;
	ops.teardown = fake_teardown;
	ops.bots_start = fake_bots_start;
	ops.bots_hash = fake_bots_hash;
	ops.emit = fake_emit;
	return ops;
}

/* ---- qualified rows (fixture) -------------------------------------------------------------------------- */

#define ALL_DIFFICULTIES ((1u << 1) | (1u << 2) | (1u << 3) | (1u << 4))

static const hcu_local_qualified_row rows[] = {
	{ "beavercreek", HCU_LOCAL_MODE_STOCK_COOP, ALL_DIFFICULTIES, 4u, 12u },
	{ "beavercreek", HCU_LOCAL_MODE_SURVIVAL, (1u << 2), 4u, 0u },
};

static void coop_setup(hcu_local_setup *s, hcu_local_variant variant, uint32_t humans, uint32_t bots)
{
	memset(s, 0, sizeof *s);
	s->mode = HCU_LOCAL_MODE_STOCK_COOP;
	s->variant = variant;
	s->teams = HCU_LOCAL_TEAMS_ON;
	s->difficulty = HCU_LOCAL_DIFFICULTY_NORMAL;
	s->human_mask = (1u << humans) - 1u;
	s->bot_count = bots;
	s->seed = 0x77u;
	strcpy(s->map_name, "beavercreek");
}

static void survival_setup(hcu_local_setup *s, uint32_t humans)
{
	memset(s, 0, sizeof *s);
	s->mode = HCU_LOCAL_MODE_SURVIVAL;
	s->variant = HCU_LOCAL_VARIANT_NONE;
	s->teams = HCU_LOCAL_TEAMS_OFF;
	s->difficulty = HCU_LOCAL_DIFFICULTY_NORMAL;
	s->human_mask = (1u << humans) - 1u;
	s->bot_count = 0u;
	s->seed = HCU_SURVIVAL_QUAL_SEED_0;
	strcpy(s->map_name, "beavercreek");
}

/* ---- groups -------------------------------------------------------------------------------------------- */

static void test_coop_start(void)
{
	struct fake_env env;
	struct hcu_c5_session session;
	struct hcu_c5_session_ops ops;
	hcu_local_setup setup;
	enum hcu_c5_session_status status;

	fake_init(&env);
	ops = ops_for(&env);
	coop_setup(&setup, HCU_LOCAL_VARIANT_SLAYER, 2u, 3u);
	status = hcu_c5_session_start(&session, &setup, rows, sizeof rows / sizeof rows[0], &ops, NULL);
	CHECK(status == HCU_C5_SESSION_OK, "coop start ok");
	CHECK(env.teardown_calls == 1, "coop teardown once");
	CHECK(session.mode == HCU_C5_SESSION_MODE_COOP && session.started, "coop mode started");
	CHECK(session.coop_mode == HCU_COOP_MODE_TEAM_SLAYER, "slayer maps to team slayer");
	CHECK(session.binding.humans == 2u && session.binding.bots == 3u, "binding roster");
	CHECK(env.bots_calls == 1, "bots started once");
	CHECK(env.bot_config.count == 3u, "bot count");
	CHECK(env.bot_config.skill == HCU_BOT_SKILL_NORMAL, "bot skill normal");
	CHECK(env.bot_config.team_mode == 1u && env.bot_config.bot_team == HCU_C5_BOT_TEAM, "bot team");
	CHECK(env.bot_config.seed == 0x77u, "bot seed");
	CHECK(session.bots_running == 1, "bots running");
	CHECK(saw_line(&env, "HALO_PS2_C5 session-start mode=coop coop=1 humans=2 bots=3"), "start marker");
	printf("coop start: ok\n");
}

static void test_refusals_leave_map_alone(void)
{
	struct fake_env env;
	struct hcu_c5_session session;
	struct hcu_c5_session_ops ops;
	hcu_local_setup setup;

	/* unqualified map: refused before teardown */
	fake_init(&env);
	ops = ops_for(&env);
	coop_setup(&setup, HCU_LOCAL_VARIANT_SLAYER, 2u, 3u);
	strcpy(setup.map_name, "nosuchmap");
	CHECK(hcu_c5_session_start(&session, &setup, rows, 2u, &ops, NULL) == HCU_C5_SESSION_ERR_SETUP, "unqualified map refused");
	CHECK(env.teardown_calls == 0, "refusal runs no teardown");
	CHECK(env.bots_calls == 0, "refusal starts no bots");
	CHECK(!session.started, "refusal not started");
	CHECK(session.setup_reason == HCU_LOCAL_SETUP_MAP_NOT_QUALIFIED, "refusal reason kept");
	CHECK(saw_line(&env, "session-refused reason="), "refusal marker");

	/* too many bots: refused before teardown */
	fake_init(&env);
	ops = ops_for(&env);
	coop_setup(&setup, HCU_LOCAL_VARIANT_SLAYER, 2u, 13u);
	CHECK(hcu_c5_session_start(&session, &setup, rows, 2u, &ops, NULL) == HCU_C5_SESSION_ERR_SETUP, "too many bots refused");
	CHECK(env.teardown_calls == 0, "bots refusal runs no teardown");

	/* teardown failure: admit reports it, bots never start */
	fake_init(&env);
	env.teardown_status = 1;
	ops = ops_for(&env);
	coop_setup(&setup, HCU_LOCAL_VARIANT_SLAYER, 2u, 3u);
	CHECK(hcu_c5_session_start(&session, &setup, rows, 2u, &ops, NULL) == HCU_C5_SESSION_ERR_SETUP, "teardown failure refused");
	CHECK(env.teardown_calls == 1, "teardown attempted");
	CHECK(env.bots_calls == 0, "no bots after teardown failure");
	CHECK(session.setup_reason == HCU_LOCAL_SETUP_TEARDOWN_FAILED, "teardown reason");

	/* bots_start failure */
	fake_init(&env);
	env.bots_status = -1;
	ops = ops_for(&env);
	coop_setup(&setup, HCU_LOCAL_VARIANT_SLAYER, 2u, 3u);
	CHECK(hcu_c5_session_start(&session, &setup, rows, 2u, &ops, NULL) == HCU_C5_SESSION_ERR_BOTS, "bots failure refused");
	CHECK(!session.started, "bots failure not started");
	CHECK(!session.bots_running, "bots failure not running");

	/* survival with bots is a session mode refusal (after admission, so teardown ran) */
	fake_init(&env);
	ops = ops_for(&env);
	survival_setup(&setup, 2u);
	setup.bot_count = 1u;
	CHECK(hcu_c5_session_start(&session, &setup, rows, 2u, &ops, NULL) != HCU_C5_SESSION_OK, "survival with bots refused");
	CHECK(env.bots_calls == 0, "survival starts no bots");

	/* NULL arguments */
	CHECK(hcu_c5_session_start(NULL, &setup, rows, 2u, &ops, NULL) == HCU_C5_SESSION_ERR_ARGUMENT, "null session");
	CHECK(hcu_c5_session_start(&session, NULL, rows, 2u, &ops, NULL) == HCU_C5_SESSION_ERR_ARGUMENT, "null setup");
	printf("refusals: ok\n");
}

static void test_mapping_tables(void)
{
	enum hcu_coop_mode mode;
	uint8_t skill;
	hcu_survival_difficulty sd;

	CHECK(hcu_c5_session_coop_mode(HCU_LOCAL_VARIANT_CTF, &mode) == 0 && mode == HCU_COOP_MODE_CTF, "ctf map");
	CHECK(hcu_c5_session_coop_mode(HCU_LOCAL_VARIANT_RACE, &mode) == 0 && mode == HCU_COOP_MODE_TEAM_RACE, "race map");
	CHECK(hcu_c5_session_coop_mode(HCU_LOCAL_VARIANT_NONE, &mode) != 0, "none variant has no coop mode");
	CHECK(hcu_c5_session_bot_skill(HCU_LOCAL_DIFFICULTY_LEGENDARY, &skill) == 0 && skill == HCU_BOT_SKILL_LEGENDARY, "skill legendary");
	CHECK(hcu_c5_session_bot_skill(HCU_LOCAL_DIFFICULTY_NONE, &skill) != 0, "no skill for none");
	CHECK(hcu_c5_session_survival_difficulty(HCU_LOCAL_DIFFICULTY_HEROIC, &sd) == 0 && sd == HCU_SURVIVAL_DIFFICULTY_HEAVY, "heroic is heavy");
	printf("mapping: ok\n");
}

static void test_survival_waves(void)
{
	struct fake_env env;
	struct hcu_c5_session session;
	struct hcu_c5_session_ops ops;
	hcu_local_setup setup;
	hcu_survival *s;
	uint64_t before, after;
	unsigned int guard;
	enum hcu_c5_session_status status;

	fake_init(&env);
	ops = ops_for(&env);
	survival_setup(&setup, 2u);
	status = hcu_c5_session_start(&session, &setup, rows, 2u, &ops, NULL);
	CHECK(status == HCU_C5_SESSION_OK, "survival start ok");
	CHECK(env.bots_calls == 0, "survival runs no bots");
	s = hcu_c5_session_survival(&session);
	CHECK(s != NULL, "survival controller exposed");
	CHECK(hcu_survival_wave_number(s) == 1u, "wave 1 admitted at start");
	CHECK(saw_line(&env, "HALO_PS2_C5 session-start mode=survival coop=-1 humans=2"), "survival start marker");

	/* wave clear: kill every admitted enemy, then tick through intermission into wave 2 */
	{
		unsigned int i;
		for (i = 0u; i < hcu_survival_batch_size(s); i++) {
			CHECK(hcu_survival_kill_enemy(s, i) == HCU_SURVIVAL_OK, "kill enemy");
		}
	}
	hcu_c5_session_tick(&session);
	CHECK(hcu_survival_get_state(s) == HCU_SURVIVAL_STATE_INTERMISSION, "intermission after clear");
	before = hcu_c5_session_hash(&session);
	guard = 0u;
	while (hcu_survival_wave_number(s) < 2u && guard < 10u * HCU_SURVIVAL_TICK_HZ) {
		hcu_c5_session_tick(&session);
		guard++;
	}
	CHECK(hcu_survival_wave_number(s) == 2u, "wave 2 admitted after intermission");
	CHECK(saw_line(&env, "survival-wave "), "wave marker emitted");
	after = hcu_c5_session_hash(&session);
	CHECK(before != after, "hash moves with waves");

	/* game over: kill both humans, then one tick */
	CHECK(hcu_survival_kill_human(s, 0u) == HCU_SURVIVAL_OK, "kill human 0");
	CHECK(hcu_survival_kill_human(s, 1u) == HCU_SURVIVAL_OK, "kill human 1");
	hcu_c5_session_tick(&session);
	CHECK(hcu_survival_get_state(s) == HCU_SURVIVAL_STATE_GAME_OVER, "game over with no humans");
	CHECK(saw_line(&env, "HALO_PS2_C5 survival-over "), "game over marker");
	guard = hcu_survival_wave_number(s);
	hcu_c5_session_tick(&session);
	CHECK(hcu_survival_wave_number(s) == guard, "game over is terminal");
	printf("survival: ok\n");
}

static void test_events_and_hash(void)
{
	struct fake_env env;
	struct hcu_c5_session a, b;
	struct hcu_c5_session_ops ops;
	hcu_local_setup setup;
	uint64_t ha, hb, base;

	fake_init(&env);
	ops = ops_for(&env);
	coop_setup(&setup, HCU_LOCAL_VARIANT_ODDBALL, 1u, 2u);
	CHECK(hcu_c5_session_start(&a, &setup, rows, 2u, &ops, NULL) == HCU_C5_SESSION_OK, "oddball start");
	CHECK(hcu_c5_session_note_event(&a, HCU_C5_EVENT_KILL, 0u, 2) == HCU_C5_SESSION_OK, "kill event");
	CHECK(a.metrics.kills == 1u, "kill counted");
	CHECK(saw_line(&env, "HALO_PS2_C5 bot-event tick=0 kind=kill bot=0 arg=2"), "kill marker");
	hcu_c5_session_note_event(&a, HCU_C5_EVENT_DEATH, 1u, -1);
	hcu_c5_session_note_event(&a, HCU_C5_EVENT_RESPAWN, 1u, 3);
	hcu_c5_session_note_event(&a, HCU_C5_EVENT_NAV, 0u, 4);
	hcu_c5_session_note_event(&a, HCU_C5_EVENT_FIGHT, 0u, 5);
	hcu_c5_session_note_event(&a, HCU_C5_EVENT_SCORE, 0u, 1);
	CHECK(a.metrics.deaths == 1u && a.metrics.respawns == 1u, "death and respawn counted");
	CHECK(a.metrics.nav_steps == 1u && a.metrics.fights == 1u && a.metrics.score_events == 1u, "nav fight score counted");
	CHECK(hcu_c5_session_note_event(&a, (enum hcu_c5_session_event)99, 0u, 0) == HCU_C5_SESSION_ERR_ARGUMENT, "bad event refused");
	CHECK(hcu_c5_session_note_event(NULL, HCU_C5_EVENT_NAV, 0u, 0) == HCU_C5_SESSION_ERR_ARGUMENT, "null event session");

	/* identical sequences give identical hashes */
	ha = hcu_c5_session_hash(&a);
	fake_init(&env);
	ops = ops_for(&env);
	CHECK(hcu_c5_session_start(&b, &setup, rows, 2u, &ops, NULL) == HCU_C5_SESSION_OK, "second start");
	hcu_c5_session_note_event(&b, HCU_C5_EVENT_KILL, 0u, 2);
	hcu_c5_session_note_event(&b, HCU_C5_EVENT_DEATH, 1u, -1);
	hcu_c5_session_note_event(&b, HCU_C5_EVENT_RESPAWN, 1u, 3);
	hcu_c5_session_note_event(&b, HCU_C5_EVENT_NAV, 0u, 4);
	hcu_c5_session_note_event(&b, HCU_C5_EVENT_FIGHT, 0u, 5);
	hcu_c5_session_note_event(&b, HCU_C5_EVENT_SCORE, 0u, 1);
	hb = hcu_c5_session_hash(&b);
	CHECK(ha == hb, "same sequence same hash");

	/* the bot hash is folded in: a different bot core changes the session hash */
	base = hcu_c5_session_hash(&b);
	env.bot_hash_value = 0x9999u;
	CHECK(hcu_c5_session_hash(&b) != base, "bot hash folded");
	env.bot_hash_value = 0x1234u;
	CHECK(hcu_c5_session_hash(&b) == base, "bot hash restored");

	/* a tick moves the hash */
	CHECK(hcu_c5_session_tick(&b) == HCU_C5_SESSION_OK, "tick");
	CHECK(hcu_c5_session_hash(&b) != base, "tick folded");
	CHECK(hcu_c5_session_report(&b) == HCU_C5_SESSION_OK, "report");
	CHECK(saw_line(&env, "HALO_PS2_C5 session-hash tick=1 hash="), "hash marker");

	/* the hash field dump for the Python order check: name value, one per line */
	printf("hash-fields begin\n");
	printf("domain 0xC5500001\n");
	printf("mode %u\n", (unsigned)b.mode);
	printf("tick %u\n", (unsigned)b.tick);
	printf("bot_hash 0x%016llx\n", (unsigned long long)(b.bots_running ? env.bot_hash_value : 0u));
	printf("survival_state 0\n");
	printf("wave 0\n");
	printf("living 0\n");
	printf("active 0\n");
	printf("reserved 0\n");
	printf("batch 0\n");
	printf("intermission 0\n");
	printf("waves_cleared 0\n");
	printf("enemies_admitted 0\n");
	printf("humans_respawned 0\n");
	printf("budgets 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0\n");
	printf("kills %u\n", (unsigned)b.metrics.kills);
	printf("deaths %u\n", (unsigned)b.metrics.deaths);
	printf("respawns %u\n", (unsigned)b.metrics.respawns);
	printf("nav %u\n", (unsigned)b.metrics.nav_steps);
	printf("fights %u\n", (unsigned)b.metrics.fights);
	printf("score %u\n", (unsigned)b.metrics.score_events);
	printf("hash 0x%016llx\n", (unsigned long long)hcu_c5_session_hash(&b));
	printf("hash-fields end\n");
	printf("hash-order: ok\n");
}

static void test_survival_hash_matches_fields(void)
{
	struct fake_env env;
	struct hcu_c5_session session;
	struct hcu_c5_session_ops ops;
	hcu_local_setup setup;
	hcu_survival *s;
	unsigned int k;

	fake_init(&env);
	ops = ops_for(&env);
	survival_setup(&setup, 2u);
	CHECK(hcu_c5_session_start(&session, &setup, rows, 2u, &ops, NULL) == HCU_C5_SESSION_OK, "survival hash start");
	s = hcu_c5_session_survival(&session);
	CHECK(s != NULL, "survival hash controller");
	printf("survival-hash-fields begin\n");
	printf("domain 0xC5500001\n");
	printf("mode %u\n", (unsigned)session.mode);
	printf("tick %u\n", (unsigned)session.tick);
	printf("bot_hash 0x%016llx\n", 0ULL);
	printf("survival_state %u\n", (unsigned)hcu_survival_get_state(s));
	printf("wave %u\n", hcu_survival_wave_number(s));
	printf("living %u\n", hcu_survival_living_humans(s));
	printf("active %u\n", hcu_survival_active_units(s));
	printf("reserved %u\n", hcu_survival_reserved_units(s));
	printf("batch %u\n", hcu_survival_batch_size(s));
	printf("intermission %u\n", hcu_survival_intermission_left(s));
	printf("waves_cleared %u\n", s->waves_cleared);
	printf("enemies_admitted %u\n", s->enemies_admitted);
	printf("humans_respawned %u\n", s->humans_respawned);
	printf("budgets");
	for (k = 0u; k < HCU_SURVIVAL_BUDGET_KIND_COUNT; k++) {
		printf(" %u %u %u", hcu_survival_budget_count(s, (hcu_survival_budget_kind)k),
		       hcu_survival_budget_evicted(s, (hcu_survival_budget_kind)k),
		       hcu_survival_budget_refused(s, (hcu_survival_budget_kind)k));
	}
	printf("\n");
	printf("kills 0\ndeaths 0\nrespawns 0\nnav 0\nfights 0\nscore 0\n");
	printf("hash 0x%016llx\n", (unsigned long long)hcu_c5_session_hash(&session));
	printf("survival-hash-fields end\n");
	printf("survival-hash: ok\n");
}

int main(void)
{
	test_coop_start();
	test_refusals_leave_map_alone();
	test_mapping_tables();
	test_survival_waves();
	test_events_and_hash();
	test_survival_hash_matches_fields();
	if (failures) {
		printf("hcu_c5_session tests FAILED: %d\n", failures);
		return 1;
	}
	printf("hcu_c5_session tests passed\n");
	return 0;
}
