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

	puts("hcu_local_setup tests passed");
	return 0;
}
