/* Host tests for the C5 cooperative mode table, admission gate, and team assignment. */
#include <stdio.h>
#include <string.h>

#include "stream/hcu_coop_modes.h"

static int failures;

#define CHECK(cond) do { if (!(cond)) { printf("FAIL %s line %d\n", #cond, __LINE__); failures++; } } while (0)

static struct hcu_coop_variant_snapshot stock(enum hcu_coop_mode mode)
{
	const struct hcu_coop_mode_row *row = hcu_coop_mode_row(mode);
	struct hcu_coop_variant_snapshot s;
	s.game_engine_index = (int)row->engine;
	s.teams = row->teams;
	s.respawn_time = row->expected_respawn_time;
	s.score_to_win = row->expected_score_to_win;
	s.suicide_penalty = row->expected_suicide_penalty;
	return s;
}

int main(void)
{
	struct hcu_coop_roster roster = { 2u, 4u };
	struct hcu_coop_roster bad;
	struct hcu_coop_variant_snapshot snap;
	unsigned char human_teams[HCU_COOP_MAX_HUMANS];
	unsigned char bot_teams[HCU_COOP_MAX_BOTS];
	enum hcu_coop_mode m;
	unsigned i;

	/* table covers all modes and every row matches its own mode */
	CHECK(hcu_coop_mode_count() == HCU_COOP_MODE_COUNT);
	for (m = 0; m < HCU_COOP_MODE_COUNT; ++m) {
		const struct hcu_coop_mode_row *row = hcu_coop_mode_row(m);
		CHECK(row != NULL);
		CHECK(row->mode == m);
		CHECK(row->ce_builder != NULL && strncmp(row->ce_builder, "build_game_variant_", 19) == 0);
		CHECK(row->cooperative_eligible == row->teams);
		CHECK(hcu_coop_check_variant(m, &(struct hcu_coop_variant_snapshot){ 0 }) != HCU_COOP_OK || row->engine == 0);
	}
	CHECK(hcu_coop_mode_row((enum hcu_coop_mode)HCU_COOP_MODE_COUNT) == NULL);

	/* the five cooperative team variants exist; FFA variants are not cooperative */
	CHECK(hcu_coop_mode_row(HCU_COOP_MODE_TEAM_SLAYER)->cooperative_eligible);
	CHECK(hcu_coop_mode_row(HCU_COOP_MODE_TEAM_ODDBALL)->cooperative_eligible);
	CHECK(hcu_coop_mode_row(HCU_COOP_MODE_TEAM_KING)->cooperative_eligible);
	CHECK(hcu_coop_mode_row(HCU_COOP_MODE_CTF)->cooperative_eligible);
	CHECK(hcu_coop_mode_row(HCU_COOP_MODE_TEAM_RACE)->cooperative_eligible);
	CHECK(!hcu_coop_mode_row(HCU_COOP_MODE_SLAYER_FFA)->cooperative_eligible);
	CHECK(!hcu_coop_mode_row(HCU_COOP_MODE_RACE_FFA)->cooperative_eligible);

	/* stock CE values round-trip through the variant check for every mode */
	for (m = 0; m < HCU_COOP_MODE_COUNT; ++m) {
		snap = stock(m);
		CHECK(hcu_coop_check_variant(m, &snap) == HCU_COOP_OK);
	}

	/* each rule-bearing field is enforced */
	snap = stock(HCU_COOP_MODE_TEAM_SLAYER);
	snap.respawn_time = 0;
	CHECK(hcu_coop_check_variant(HCU_COOP_MODE_TEAM_SLAYER, &snap) == HCU_COOP_ERR_VARIANT);
	snap = stock(HCU_COOP_MODE_TEAM_SLAYER);
	snap.score_to_win = 15;
	CHECK(hcu_coop_check_variant(HCU_COOP_MODE_TEAM_SLAYER, &snap) == HCU_COOP_ERR_VARIANT);
	snap = stock(HCU_COOP_MODE_TEAM_SLAYER);
	snap.suicide_penalty = 0;
	CHECK(hcu_coop_check_variant(HCU_COOP_MODE_TEAM_SLAYER, &snap) == HCU_COOP_ERR_VARIANT);
	snap = stock(HCU_COOP_MODE_TEAM_SLAYER);
	snap.teams = 0;
	CHECK(hcu_coop_check_variant(HCU_COOP_MODE_TEAM_SLAYER, &snap) == HCU_COOP_ERR_VARIANT);
	snap = stock(HCU_COOP_MODE_TEAM_SLAYER);
	snap.game_engine_index = (int)HCU_COOP_ENGINE_KING;
	CHECK(hcu_coop_check_variant(HCU_COOP_MODE_TEAM_SLAYER, &snap) == HCU_COOP_ERR_VARIANT);
	CHECK(hcu_coop_check_variant(HCU_COOP_MODE_TEAM_SLAYER, NULL) == HCU_COOP_ERR_ARGUMENT);
	CHECK(hcu_coop_check_variant((enum hcu_coop_mode)99, &snap) == HCU_COOP_ERR_MODE);

	/* roster limits */
	CHECK(hcu_coop_check_roster(&roster) == HCU_COOP_OK);
	bad.humans = 0u; bad.bots = 0u;
	CHECK(hcu_coop_check_roster(&bad) == HCU_COOP_ERR_ROSTER);
	bad.humans = 5u; bad.bots = 0u;
	CHECK(hcu_coop_check_roster(&bad) == HCU_COOP_ERR_ROSTER);
	bad.humans = 1u; bad.bots = HCU_COOP_MAX_BOTS + 1u;
	CHECK(hcu_coop_check_roster(&bad) == HCU_COOP_ERR_ROSTER);
	bad.humans = 4u; bad.bots = 13u;
	CHECK(hcu_coop_check_roster(&bad) == HCU_COOP_ERR_ROSTER);
	bad.humans = 4u; bad.bots = 12u;
	CHECK(hcu_coop_check_roster(&bad) == HCU_COOP_OK);   /* 16 = CE cap */
	CHECK(hcu_coop_check_roster(NULL) == HCU_COOP_ERR_ARGUMENT);

	/* admission gate */
	snap = stock(HCU_COOP_MODE_TEAM_SLAYER);
	CHECK(hcu_coop_admit(HCU_COOP_MODE_TEAM_SLAYER, &roster, &snap, 1) == HCU_COOP_OK);
	CHECK(hcu_coop_admit(HCU_COOP_MODE_SLAYER_FFA, &roster, &snap, 1) == HCU_COOP_ERR_UNSUPPORTED);
	CHECK(hcu_coop_admit(HCU_COOP_MODE_SLAYER_FFA, &roster, &snap, 0) == HCU_COOP_ERR_VARIANT);
	CHECK(hcu_coop_admit(HCU_COOP_MODE_TEAM_SLAYER, &bad, &snap, 1) == HCU_COOP_OK);
	bad.humans = 0u;
	CHECK(hcu_coop_admit(HCU_COOP_MODE_TEAM_SLAYER, &bad, &snap, 1) == HCU_COOP_ERR_ROSTER);

	/* team assignment: all humans on one team, all bots on the other */
	roster.humans = 3u; roster.bots = 5u;
	CHECK(hcu_coop_assign_teams(HCU_COOP_MODE_CTF, &roster, human_teams, bot_teams) == HCU_COOP_OK);
	for (i = 0; i < roster.humans; ++i)
		CHECK(human_teams[i] == HCU_COOP_HUMAN_TEAM);
	for (i = 0; i < roster.bots; ++i)
		CHECK(bot_teams[i] == HCU_COOP_BOT_TEAM);
	CHECK(HCU_COOP_HUMAN_TEAM != HCU_COOP_BOT_TEAM);
	CHECK(hcu_coop_assign_teams(HCU_COOP_MODE_SLAYER_FFA, &roster, human_teams, bot_teams) == HCU_COOP_ERR_UNSUPPORTED);
	CHECK(hcu_coop_assign_teams(HCU_COOP_MODE_TEAM_RACE, &roster, NULL, bot_teams) == HCU_COOP_ERR_ARGUMENT);
	roster.humans = 1u; roster.bots = 0u;
	CHECK(hcu_coop_assign_teams(HCU_COOP_MODE_TEAM_KING, &roster, human_teams, NULL) == HCU_COOP_OK);
	CHECK(human_teams[0] == HCU_COOP_HUMAN_TEAM);

	printf(failures ? "hcu_coop_modes tests FAILED (%d)\n" : "hcu_coop_modes tests passed\n", failures);
	return failures ? 1 : 0;
}
