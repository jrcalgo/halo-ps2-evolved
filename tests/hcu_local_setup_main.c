/* C5 step 8 host proof: the local setup validator accepts only qualified
 * profiles, and every rejection leaves the loaded-map state untouched because
 * the teardown callback is never reached. */
#include "stream/hcu_local_setup.h"

#include <assert.h>
#include <stdio.h>
#include <string.h>

/* Stand-in for the loaded-map state the integrator owns. */
typedef struct fake_map_state {
	char map_name[HCU_LOCAL_MAP_NAME_BYTES];
	uint32_t generation;
	uint32_t teardowns;
	uint32_t bots_spawned;
} fake_map_state;

static int fake_teardown(void *user, const hcu_local_setup_result *accepted)
{
	fake_map_state *m = (fake_map_state *)user;
	m->teardowns++;
	m->generation++;
	memcpy(m->map_name, accepted->setup.map_name, sizeof m->map_name);
	m->bots_spawned = accepted->bot_count;
	return 0;
}

static int failing_teardown(void *user, const hcu_local_setup_result *accepted)
{
	(void)accepted;
	((fake_map_state *)user)->teardowns++;
	return -1;
}

static const hcu_local_qualified_row rows[] = {
	{ "bloodgulch", HCU_LOCAL_MODE_STOCK_COOP, (1u << HCU_LOCAL_DIFFICULTY_NORMAL) | (1u << HCU_LOCAL_DIFFICULTY_EASY), 4u, 4u },
	{ "a10", HCU_LOCAL_MODE_SURVIVAL, 1u << HCU_LOCAL_DIFFICULTY_NORMAL, 2u, 2u },
};

/* Team switch follows the mode: cooperative needs ON, survival needs OFF. Tests override it where needed. */
static void make_request(hcu_local_setup *r, hcu_local_mode mode, hcu_local_variant variant,
	hcu_local_difficulty difficulty, uint32_t humans, uint32_t bots, const char *map)
{
	memset(r, 0, sizeof *r);
	r->mode = mode;
	r->variant = variant;
	r->teams = mode == HCU_LOCAL_MODE_STOCK_COOP ? HCU_LOCAL_TEAMS_ON : HCU_LOCAL_TEAMS_OFF;
	r->difficulty = difficulty;
	r->human_mask = humans;
	r->bot_count = bots;
	r->seed = 0x5eedu;
	strncpy(r->map_name, map, sizeof r->map_name - 1u);
}

static void expect_reject(const char *label, const hcu_local_setup *r,
	hcu_local_setup_reason want, fake_map_state *state)
{
	fake_map_state before = *state;
	hcu_local_setup_result out;
	hcu_local_setup_reason got = hcu_local_setup_admit(r, rows, sizeof rows / sizeof rows[0],
		fake_teardown, state, &out);
	if (got != want) {
		fprintf(stderr, "%s: got %s want %s\n", label,
			hcu_local_setup_reason_name(got), hcu_local_setup_reason_name(want));
	}
	assert(got == want);
	assert(memcmp(&before, state, sizeof *state) == 0);
	printf("reject %s: %s, state unchanged\n", label, hcu_local_setup_reason_name(got));
}

int main(void)
{
	fake_map_state state;
	hcu_local_setup req;
	hcu_local_setup alt;
	hcu_local_setup_result out;
	hcu_local_setup_reason r;
	size_t nrows = sizeof rows / sizeof rows[0];

	memset(&state, 0, sizeof state);
	strcpy(state.map_name, "a10");
	state.generation = 7u;

	/* Rejections, each before teardown. */
	make_request(&req, HCU_LOCAL_MODE_STOCK_COOP, HCU_LOCAL_VARIANT_SLAYER, HCU_LOCAL_DIFFICULTY_NORMAL, 0x3u, 4u, "bloodgulch");
	expect_reject("unknown-mode", &(hcu_local_setup){ .mode = 0 }, HCU_LOCAL_SETUP_UNKNOWN_MODE, &state);
	make_request(&req, HCU_LOCAL_MODE_STOCK_COOP, HCU_LOCAL_VARIANT_SLAYER, HCU_LOCAL_DIFFICULTY_NORMAL, 0x3u, 4u, "a30");
	expect_reject("map-not-qualified", &req, HCU_LOCAL_SETUP_MAP_NOT_QUALIFIED, &state);
	make_request(&req, HCU_LOCAL_MODE_STOCK_COOP, HCU_LOCAL_VARIANT_SLAYER, HCU_LOCAL_DIFFICULTY_HEROIC, 0x3u, 4u, "bloodgulch");
	expect_reject("difficulty-not-qualified", &req, HCU_LOCAL_SETUP_DIFFICULTY_NOT_QUALIFIED, &state);
	make_request(&req, HCU_LOCAL_MODE_STOCK_COOP, HCU_LOCAL_VARIANT_SLAYER, HCU_LOCAL_DIFFICULTY_NORMAL, 0x1fu, 4u, "bloodgulch");
	expect_reject("bad-human-mask", &req, HCU_LOCAL_SETUP_BAD_HUMAN_MASK, &state);
	make_request(&req, HCU_LOCAL_MODE_STOCK_COOP, HCU_LOCAL_VARIANT_SLAYER, HCU_LOCAL_DIFFICULTY_NORMAL, 0u, 4u, "bloodgulch");
	expect_reject("no-humans", &req, HCU_LOCAL_SETUP_NO_HUMANS, &state);
	make_request(&req, HCU_LOCAL_MODE_STOCK_COOP, HCU_LOCAL_VARIANT_SLAYER, HCU_LOCAL_DIFFICULTY_NORMAL, 0x3u, 13u, "bloodgulch");
	expect_reject("too-many-bots", &req, HCU_LOCAL_SETUP_TOO_MANY_BOTS, &state);
	make_request(&req, HCU_LOCAL_MODE_STOCK_COOP, HCU_LOCAL_VARIANT_SLAYER, HCU_LOCAL_DIFFICULTY_NORMAL, 0x3u, 12u, "bloodgulch");
	expect_reject("bots-12-not-qualified-on-row", &req, HCU_LOCAL_SETUP_POPULATION_ABOVE_QUALIFIED, &state);
	make_request(&req, HCU_LOCAL_MODE_STOCK_COOP, HCU_LOCAL_VARIANT_SLAYER, HCU_LOCAL_DIFFICULTY_NORMAL, 0x3u, 4u, "bloodgulch");
	req.teams = HCU_LOCAL_TEAMS_OFF;
	expect_reject("team-mismatch", &req, HCU_LOCAL_SETUP_TEAM_MISMATCH, &state);
	make_request(&req, HCU_LOCAL_MODE_STOCK_COOP, HCU_LOCAL_VARIANT_CTF, HCU_LOCAL_DIFFICULTY_NORMAL, 0x3u, 4u, "bloodgulch");
	req.teams = HCU_LOCAL_TEAMS_OFF;
	expect_reject("ctf-needs-teams", &req, HCU_LOCAL_SETUP_TEAM_MISMATCH, &state);
	make_request(&req, HCU_LOCAL_MODE_SURVIVAL, HCU_LOCAL_VARIANT_NONE, HCU_LOCAL_DIFFICULTY_NORMAL, 0x1u, 0u, "a10");
	req.teams = HCU_LOCAL_TEAMS_ON;
	expect_reject("survival-with-teams", &req, HCU_LOCAL_SETUP_TEAM_MISMATCH, &state);
	make_request(&req, HCU_LOCAL_MODE_STOCK_COOP, HCU_LOCAL_VARIANT_SLAYER, HCU_LOCAL_DIFFICULTY_NORMAL, 0x3u, 4u, "bloodgulch");
	req.teams = (hcu_local_teams)7;
	expect_reject("bad-team-switch", &req, HCU_LOCAL_SETUP_TEAM_MISMATCH, &state);
	make_request(&req, HCU_LOCAL_MODE_STOCK_COOP, HCU_LOCAL_VARIANT_NONE, HCU_LOCAL_DIFFICULTY_NORMAL, 0x3u, 0u, "bloodgulch");
	expect_reject("coop-without-variant", &req, HCU_LOCAL_SETUP_VARIANT_NOT_APPLICABLE, &state);
	make_request(&req, HCU_LOCAL_MODE_SURVIVAL, HCU_LOCAL_VARIANT_SLAYER, HCU_LOCAL_DIFFICULTY_NORMAL, 0x1u, 0u, "a10");
	expect_reject("survival-with-variant", &req, HCU_LOCAL_SETUP_VARIANT_NOT_APPLICABLE, &state);
	make_request(&req, HCU_LOCAL_MODE_STOCK_COOP, (hcu_local_variant)99, HCU_LOCAL_DIFFICULTY_NORMAL, 0x3u, 0u, "bloodgulch");
	expect_reject("unknown-variant", &req, HCU_LOCAL_SETUP_UNKNOWN_VARIANT, &state);
	make_request(&req, HCU_LOCAL_MODE_STOCK_COOP, HCU_LOCAL_VARIANT_SLAYER, HCU_LOCAL_DIFFICULTY_NONE, 0x3u, 0u, "bloodgulch");
	expect_reject("unknown-difficulty", &req, HCU_LOCAL_SETUP_UNKNOWN_DIFFICULTY, &state);
	make_request(&req, HCU_LOCAL_MODE_SURVIVAL, HCU_LOCAL_VARIANT_NONE, HCU_LOCAL_DIFFICULTY_NORMAL, 0x7u, 0u, "a10");
	expect_reject("population-above-qualified", &req, HCU_LOCAL_SETUP_POPULATION_ABOVE_QUALIFIED, &state);
	make_request(&req, HCU_LOCAL_MODE_SURVIVAL, HCU_LOCAL_VARIANT_NONE, HCU_LOCAL_DIFFICULTY_NORMAL, 0x1u, 3u, "a10");
	expect_reject("bots-above-qualified", &req, HCU_LOCAL_SETUP_POPULATION_ABOVE_QUALIFIED, &state);
	make_request(&req, HCU_LOCAL_MODE_SURVIVAL, HCU_LOCAL_VARIANT_NONE, HCU_LOCAL_DIFFICULTY_NORMAL, 0x1u, 0u, "");
	expect_reject("empty-map", &req, HCU_LOCAL_SETUP_BAD_MAP_NAME, &state);
	make_request(&req, HCU_LOCAL_MODE_SURVIVAL, HCU_LOCAL_VARIANT_NONE, HCU_LOCAL_DIFFICULTY_NORMAL, 0x1u, 0u, "a10");
	r = hcu_local_setup_admit(&req, NULL, 0u, fake_teardown, &state, &out);
	assert(r == HCU_LOCAL_SETUP_BAD_ARGUMENT || r == HCU_LOCAL_SETUP_MAP_NOT_QUALIFIED);
	assert(state.teardowns == 0u);
	printf("reject null-rows: %s, state unchanged\n", hcu_local_setup_reason_name(r));

	/* Teardown failure after acceptance is reported, not hidden. */
	make_request(&req, HCU_LOCAL_MODE_SURVIVAL, HCU_LOCAL_VARIANT_NONE, HCU_LOCAL_DIFFICULTY_NORMAL, 0x1u, 1u, "a10");
	memset(&state, 0, sizeof state);
	strcpy(state.map_name, "a10");
	state.generation = 7u;
	r = hcu_local_setup_admit(&req, rows, nrows, failing_teardown, &state, &out);
	assert(r == HCU_LOCAL_SETUP_TEARDOWN_FAILED);
	assert(state.teardowns == 1u);
	printf("teardown-failure: %s\n", hcu_local_setup_reason_name(r));

	/* Accepted coop profile: bots separate from the four human slots. */
	make_request(&req, HCU_LOCAL_MODE_STOCK_COOP, HCU_LOCAL_VARIANT_CTF, HCU_LOCAL_DIFFICULTY_NORMAL, 0xfu, 4u, "bloodgulch");
	memset(&out, 0xAA, sizeof out);
	r = hcu_local_setup_validate(&req, rows, nrows, &out);
	assert(r == HCU_LOCAL_SETUP_OK);
	assert(out.human_count == 4u);
	assert(out.bot_count == 4u);
	assert(out.qualified_population == 8u);
	assert(out.setup.seed == 0x5eedu);
	assert(out.setup.variant == HCU_LOCAL_VARIANT_CTF);
	assert(out.setup.teams == HCU_LOCAL_TEAMS_ON);
	assert(out.human_team == 0u);   /* humans explicit team 0 */
	assert(out.bot_team == 1u);     /* bots explicit team 1, not left at the CE default */
	printf("accept coop: humans=%u bots=%u qualified=%u\n", out.human_count, out.bot_count, out.qualified_population);
	printf("accept teams: human team %u, bot team %u\n", out.human_team, out.bot_team);

	/* Individual survival: no team split, so both team fields are NONE. */
	make_request(&alt, HCU_LOCAL_MODE_SURVIVAL, HCU_LOCAL_VARIANT_NONE, HCU_LOCAL_DIFFICULTY_NORMAL, 0x1u, 1u, "a10");
	r = hcu_local_setup_validate(&alt, rows, nrows, &out);
	assert(r == HCU_LOCAL_SETUP_OK);
	assert(out.human_team == HCU_C5_TEAM_NONE && out.bot_team == HCU_C5_TEAM_NONE);

	/* Accepted profile runs teardown exactly once, with the map mutated. */
	memset(&state, 0, sizeof state);
	strcpy(state.map_name, "a10");
	state.generation = 7u;
	r = hcu_local_setup_admit(&req, rows, nrows, fake_teardown, &state, &out);
	assert(r == HCU_LOCAL_SETUP_OK);
	assert(state.teardowns == 1u);
	assert(state.generation == 8u);
	assert(strcmp(state.map_name, "bloodgulch") == 0);
	assert(state.bots_spawned == 4u);

	/* MEASURE: an unqualified row is admitted with status "measuring" and no population claim. Every hard check still
	 * refuses before teardown. The fixture table holds one unqualified row (difficulty mask 0, population 0). */
	{
		static const hcu_local_qualified_row mrows[] = {
			{ "beavercreek", HCU_LOCAL_MODE_STOCK_COOP, 0u, 0u, 0u },
		};
		size_t mn = sizeof mrows / sizeof mrows[0];
		fake_map_state ms;
		hcu_local_setup m;
		hcu_local_setup_result mo;

		memset(&ms, 0, sizeof ms);
		strcpy(ms.map_name, "a10");
		ms.generation = 3u;
		make_request(&m, HCU_LOCAL_MODE_STOCK_COOP, HCU_LOCAL_VARIANT_SLAYER, HCU_LOCAL_DIFFICULTY_NORMAL, 0xfu, 12u,
			"beavercreek");
		m.intent = HCU_LOCAL_INTENT_MEASURE;
		r = hcu_local_setup_admit(&m, mrows, mn, fake_teardown, &ms, &mo);
		assert(r == HCU_LOCAL_SETUP_OK);
		assert(mo.status == HCU_LOCAL_STATUS_MEASURING);
		assert(mo.qualified_population == 0u);
		assert(mo.human_count == 4u && mo.bot_count == 12u);
		assert(ms.teardowns == 1u);
		assert(strcmp(hcu_local_setup_status_name(mo.status), "measuring") == 0);
		printf("accept measure: status=%s humans=%u bots=%u\n", hcu_local_setup_status_name(mo.status),
			mo.human_count, mo.bot_count);

		/* The same row under PLAY is refused: no qualification, no teardown. */
		m.intent = HCU_LOCAL_INTENT_PLAY;
		r = hcu_local_setup_admit(&m, mrows, mn, fake_teardown, &ms, &mo);
		assert(r == HCU_LOCAL_SETUP_DIFFICULTY_NOT_QUALIFIED);
		assert(ms.teardowns == 1u);
		printf("reject play-unqualified-row: %s\n", hcu_local_setup_reason_name(r));

		/* Each hard check still refuses under MEASURE, with the loaded map untouched. */
		{
			struct measure_case {
				const char *label;
				hcu_local_setup_reason want;
				hcu_local_setup req;
			};
			hcu_local_setup base;
			struct measure_case cases[8];
			size_t i;

			make_request(&base, HCU_LOCAL_MODE_STOCK_COOP, HCU_LOCAL_VARIANT_SLAYER, HCU_LOCAL_DIFFICULTY_NORMAL,
				0x3u, 4u, "beavercreek");
			base.intent = HCU_LOCAL_INTENT_MEASURE;
			cases[0].label = "measure-team-mismatch"; cases[0].want = HCU_LOCAL_SETUP_TEAM_MISMATCH;
			cases[0].req = base; cases[0].req.teams = HCU_LOCAL_TEAMS_OFF;
			cases[1].label = "measure-too-many-bots"; cases[1].want = HCU_LOCAL_SETUP_TOO_MANY_BOTS;
			cases[1].req = base; cases[1].req.bot_count = 13u;
			cases[2].label = "measure-bad-human-mask"; cases[2].want = HCU_LOCAL_SETUP_BAD_HUMAN_MASK;
			cases[2].req = base; cases[2].req.human_mask = 0x1fu;
			cases[3].label = "measure-no-humans"; cases[3].want = HCU_LOCAL_SETUP_NO_HUMANS;
			cases[3].req = base; cases[3].req.human_mask = 0u;
			cases[4].label = "measure-bad-map-name"; cases[4].want = HCU_LOCAL_SETUP_BAD_MAP_NAME;
			cases[4].req = base; memset(cases[4].req.map_name, 0, sizeof cases[4].req.map_name);
			cases[5].label = "measure-map-without-row"; cases[5].want = HCU_LOCAL_SETUP_MAP_NOT_QUALIFIED;
			cases[5].req = base; strcpy(cases[5].req.map_name, "a30");
			cases[6].label = "measure-unknown-intent"; cases[6].want = HCU_LOCAL_SETUP_BAD_ARGUMENT;
			cases[6].req = base; cases[6].req.intent = (hcu_local_intent)9;
			cases[7].label = "measure-unknown-difficulty"; cases[7].want = HCU_LOCAL_SETUP_UNKNOWN_DIFFICULTY;
			cases[7].req = base; cases[7].req.difficulty = HCU_LOCAL_DIFFICULTY_NONE;
			for (i = 0; i < sizeof cases / sizeof cases[0]; i++) {
				fake_map_state before = ms;
				r = hcu_local_setup_admit(&cases[i].req, mrows, mn, fake_teardown, &ms, &mo);
				if (r != cases[i].want) {
					fprintf(stderr, "%s: got %s want %s\n", cases[i].label, hcu_local_setup_reason_name(r),
						hcu_local_setup_reason_name(cases[i].want));
				}
				assert(r == cases[i].want);
				assert(memcmp(&before, &ms, sizeof ms) == 0);
				printf("reject %s: %s, state unchanged\n", cases[i].label, hcu_local_setup_reason_name(r));
			}
		}
		assert(strcmp(hcu_local_setup_intent_name(HCU_LOCAL_INTENT_MEASURE), "measure") == 0);
	}

	/* The committed table: every row is unqualified until guest evidence is recorded. */
	{
		size_t n = 0u;
		size_t i;
		const hcu_local_qualified_row *table = hcu_local_setup_rows(&n);
		assert(table != NULL && n == 13u);
		assert(hcu_local_setup_rows(NULL) == NULL);
		for (i = 0; i < n; i++) {
			assert(table[i].difficulty_mask == 0u && table[i].max_humans == 0u && table[i].max_bots == 0u);
		}
		printf("rows table: %u rows, all unqualified\n", (unsigned)n);
	}

	puts("hcu_local_setup tests passed");
	return 0;
}
