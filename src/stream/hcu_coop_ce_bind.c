/* C5: CE binding for qualified cooperative modes. Pure data; see hcu_coop_ce_bind.h. */

#include <string.h>

#include "stream/hcu_coop_ce_bind.h"

enum hcu_coop_ce_status hcu_coop_ce_bind(enum hcu_coop_mode mode, const struct hcu_coop_roster *roster,
                                         struct hcu_coop_ce_binding *out)
{
	const struct hcu_coop_mode_row *row;
	struct hcu_coop_variant_snapshot stock;
	unsigned char human_teams[HCU_COOP_MAX_HUMANS];
	unsigned char bot_teams[HCU_COOP_MAX_BOTS];
	unsigned i;

	if (!roster || !out)
		return HCU_COOP_CE_ERR_ARGUMENT;
	row = hcu_coop_mode_row(mode);
	if (!row)
		return HCU_COOP_CE_ERR_ADMIT;

	/* the stock snapshot of the qualified row: admission then only checks roster and cooperative eligibility */
	stock.game_engine_index = (int)row->engine;
	stock.teams = row->teams;
	stock.respawn_time = row->expected_respawn_time;
	stock.score_to_win = row->expected_score_to_win;
	stock.suicide_penalty = row->expected_suicide_penalty;

	if (hcu_coop_admit(mode, roster, &stock, 1) != HCU_COOP_OK)
		return HCU_COOP_CE_ERR_ADMIT;
	if (hcu_coop_assign_teams(mode, roster, human_teams, bot_teams) != HCU_COOP_OK)
		return HCU_COOP_CE_ERR_ADMIT;

	memset(out, 0, sizeof(*out));
	out->mode = mode;
	out->humans = roster->humans;
	out->bots = roster->bots;
	out->variant.game_engine_index = row->engine;
	out->variant.teams = row->teams;
	out->variant.respawn_time = row->expected_respawn_time;
	out->variant.respawn_time_growth = 0;
	out->variant.suicide_penalty = row->expected_suicide_penalty;
	out->variant.score_to_win = row->expected_score_to_win;
	out->variant.lives = 0;
	out->variant.odd_man_out = 0;
	out->variant.auto_team_balance = 0;
	for (i = 0; i < roster->humans; ++i)
		out->team_index[i] = human_teams[i];
	for (i = 0; i < roster->bots; ++i)
		out->team_index[roster->humans + i] = bot_teams[i];
	return HCU_COOP_CE_OK;
}

enum hcu_coop_ce_status hcu_coop_ce_check_live(const struct hcu_coop_ce_binding *binding,
                                               const struct hcu_coop_ce_variant *live)
{
	if (!binding || !live)
		return HCU_COOP_CE_ERR_ARGUMENT;
	/* field by field: struct padding is not part of the value */
	if (binding->variant.game_engine_index != live->game_engine_index ||
		binding->variant.teams != live->teams ||
		binding->variant.respawn_time != live->respawn_time ||
		binding->variant.respawn_time_growth != live->respawn_time_growth ||
		binding->variant.suicide_penalty != live->suicide_penalty ||
		binding->variant.score_to_win != live->score_to_win ||
		binding->variant.lives != live->lives ||
		binding->variant.odd_man_out != live->odd_man_out ||
		binding->variant.auto_team_balance != live->auto_team_balance)
		return HCU_COOP_CE_ERR_MISMATCH;
	return HCU_COOP_CE_OK;
}
