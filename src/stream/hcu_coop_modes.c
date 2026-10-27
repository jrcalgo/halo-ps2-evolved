/* C5: cooperative/team mode qualification table and team assignment. Host-testable pure core; see the header.
 * Values in the table are the stock CE build_game_variant_* results (game_engine.c). */

#include "stream/hcu_coop_modes.h"

static const struct hcu_coop_mode_row kCoopModes[HCU_COOP_MODE_COUNT] = {
	{ HCU_COOP_MODE_SLAYER_FFA, HCU_COOP_ENGINE_SLAYER, "build_game_variant_slayer", 0, 0, 15, 300, 0 },
	{ HCU_COOP_MODE_TEAM_SLAYER, HCU_COOP_ENGINE_SLAYER, "build_game_variant_team_slayer", 1, 300, 50, 300, 1 },
	{ HCU_COOP_MODE_ODDBALL_FFA, HCU_COOP_ENGINE_ODDBALL, "build_game_variant_oddball", 0, 150, 2, 150, 0 },
	{ HCU_COOP_MODE_TEAM_ODDBALL, HCU_COOP_ENGINE_ODDBALL, "build_game_variant_team_oddball", 1, 300, 2, 150, 1 },
	{ HCU_COOP_MODE_KING_FFA, HCU_COOP_ENGINE_KING, "build_game_variant_king", 0, 150, 2, 150, 0 },
	{ HCU_COOP_MODE_TEAM_KING, HCU_COOP_ENGINE_KING, "build_game_variant_team_king", 1, 300, 2, 150, 1 },
	{ HCU_COOP_MODE_CTF, HCU_COOP_ENGINE_CTF, "build_game_variant_ctf", 1, 300, 3, 150, 1 },
	{ HCU_COOP_MODE_RACE_FFA, HCU_COOP_ENGINE_RACE, "build_game_variant_race", 0, 0, 3, 300, 0 },
	{ HCU_COOP_MODE_TEAM_RACE, HCU_COOP_ENGINE_RACE, "build_game_variant_team_race", 1, 0, 3, 300, 1 },
};

const struct hcu_coop_mode_row *hcu_coop_mode_row(enum hcu_coop_mode mode)
{
	if ((unsigned)mode >= HCU_COOP_MODE_COUNT)
		return NULL;
	return &kCoopModes[mode];
}

size_t hcu_coop_mode_count(void)
{
	return HCU_COOP_MODE_COUNT;
}

enum hcu_coop_status hcu_coop_check_roster(const struct hcu_coop_roster *roster)
{
	if (!roster)
		return HCU_COOP_ERR_ARGUMENT;
	if (roster->humans < 1u || roster->humans > HCU_COOP_MAX_HUMANS)
		return HCU_COOP_ERR_ROSTER;
	if (roster->bots > HCU_COOP_MAX_BOTS)
		return HCU_COOP_ERR_ROSTER;
	if (roster->humans + roster->bots > HCU_COOP_MAX_PLAYERS)
		return HCU_COOP_ERR_ROSTER;
	return HCU_COOP_OK;
}

enum hcu_coop_status hcu_coop_check_variant(enum hcu_coop_mode mode, const struct hcu_coop_variant_snapshot *snapshot)
{
	const struct hcu_coop_mode_row *row = hcu_coop_mode_row(mode);

	if (!row)
		return HCU_COOP_ERR_MODE;
	if (!snapshot)
		return HCU_COOP_ERR_ARGUMENT;
	if (snapshot->game_engine_index != (int)row->engine)
		return HCU_COOP_ERR_VARIANT;
	if (snapshot->teams != row->teams)
		return HCU_COOP_ERR_VARIANT;
	if (snapshot->respawn_time != row->expected_respawn_time)
		return HCU_COOP_ERR_VARIANT;
	if (snapshot->score_to_win != row->expected_score_to_win)
		return HCU_COOP_ERR_VARIANT;
	if (snapshot->suicide_penalty != row->expected_suicide_penalty)
		return HCU_COOP_ERR_VARIANT;
	return HCU_COOP_OK;
}

enum hcu_coop_status hcu_coop_admit(enum hcu_coop_mode mode, const struct hcu_coop_roster *roster,
                                    const struct hcu_coop_variant_snapshot *snapshot, int humans_share_team)
{
	const struct hcu_coop_mode_row *row = hcu_coop_mode_row(mode);
	enum hcu_coop_status status;

	if (!row)
		return HCU_COOP_ERR_MODE;
	status = hcu_coop_check_roster(roster);
	if (status != HCU_COOP_OK)
		return status;
	if (humans_share_team && !row->cooperative_eligible)
		return HCU_COOP_ERR_UNSUPPORTED;
	return hcu_coop_check_variant(mode, snapshot);
}

enum hcu_coop_status hcu_coop_check_team_indices(unsigned human_team, unsigned bot_team)
{
	if (human_team != HCU_COOP_HUMAN_TEAM || bot_team != HCU_COOP_BOT_TEAM)
		return HCU_COOP_ERR_TEAM;
	return HCU_COOP_OK;
}

enum hcu_coop_status hcu_coop_assign_teams(enum hcu_coop_mode mode, const struct hcu_coop_roster *roster,
                                           unsigned char *human_teams, unsigned char *bot_teams)
{
	const struct hcu_coop_mode_row *row = hcu_coop_mode_row(mode);
	enum hcu_coop_status status;
	unsigned i;

	if (!row)
		return HCU_COOP_ERR_MODE;
	status = hcu_coop_check_roster(roster);
	if (status != HCU_COOP_OK)
		return status;
	if (!row->cooperative_eligible)
		return HCU_COOP_ERR_UNSUPPORTED;
	if (!human_teams || (roster->bots > 0u && !bot_teams))
		return HCU_COOP_ERR_ARGUMENT;

	for (i = 0; i < roster->humans; ++i)
		human_teams[i] = HCU_COOP_HUMAN_TEAM;
	for (i = 0; i < roster->bots; ++i)
		bot_teams[i] = HCU_COOP_BOT_TEAM;
	return HCU_COOP_OK;
}
