/* C5: cooperative/team mode qualification table and human-vs-bot team assignment for the HCU fork.
 *
 * This is a host-testable pure core. It does not implement any victory, scoring, or respawn rule. Those stay
 * in CE (game_engine.c: game_engine_should_end_game, game_engine_did_player_win, respawn paths). This module:
 *   - records the CE gametype/variant values each qualified mode must carry (from the CE build_game_variant_*
 *     builders in submodules/halo-ce-universal/source/game/game_engine.c), and rejects a runtime variant snapshot
 *     that disagrees with them before map teardown;
 *   - decides which modes may run cooperatively (all local humans on one team, Spartan bots on the other);
 *   - assigns team indices for a roster under that rule.
 *
 * Team indices are CE team indices as used by the variant (teams == TRUE). Runtime qualification also needs
 * guest evidence; a passing host table check is not a runtime qualification row. */
#ifndef HALO_STREAM_HCU_COOP_MODES_H
#define HALO_STREAM_HCU_COOP_MODES_H

#include <stddef.h>

#ifdef __cplusplus
extern "C" {
#endif

#define HCU_COOP_MAX_HUMANS 4u        /* local controller/view slots */
#define HCU_COOP_MAX_BOTS 12u         /* Spartan bots; bot slots are separate from the local slots */
#define HCU_COOP_MAX_PLAYERS 16u      /* CE player cap: humans + bots */
#define HCU_COOP_HUMAN_TEAM 0          /* cooperative team for every local human */
#define HCU_COOP_BOT_TEAM 1            /* opposing team for every Spartan bot */

/* CE game_engine_type values (game_engine.h); kept numerically identical. */
enum hcu_coop_engine
{
	HCU_COOP_ENGINE_CTF = 1,
	HCU_COOP_ENGINE_SLAYER = 2,
	HCU_COOP_ENGINE_ODDBALL = 3,
	HCU_COOP_ENGINE_KING = 4,
	HCU_COOP_ENGINE_RACE = 5,
};

enum hcu_coop_mode
{
	HCU_COOP_MODE_SLAYER_FFA = 0,   /* stock Slayer: individual scoring, not cooperative */
	HCU_COOP_MODE_TEAM_SLAYER,
	HCU_COOP_MODE_ODDBALL_FFA,
	HCU_COOP_MODE_TEAM_ODDBALL,
	HCU_COOP_MODE_KING_FFA,
	HCU_COOP_MODE_TEAM_KING,
	HCU_COOP_MODE_CTF,
	HCU_COOP_MODE_RACE_FFA,
	HCU_COOP_MODE_TEAM_RACE,
	HCU_COOP_MODE_COUNT
};

/* One row per CE gametype variant. The expected_* fields are the stock CE builder values. */
struct hcu_coop_mode_row
{
	enum hcu_coop_mode mode;
	enum hcu_coop_engine engine;
	const char *ce_builder;          /* CE build_game_variant_* name */
	int teams;                       /* universal_variant.teams */
	long expected_respawn_time;      /* ticks, universal_variant.respawn_time */
	long expected_score_to_win;      /* universal_variant.score_to_win */
	long expected_suicide_penalty;   /* universal_variant.suicide_penalty */
	int cooperative_eligible;        /* 1 when humans may share a team against bots */
};

/* Runtime snapshot of a CE variant, filled by the integrator from global_variant at setup time. */
struct hcu_coop_variant_snapshot
{
	int game_engine_index;           /* CE game_engine_type */
	int teams;
	long respawn_time;
	long score_to_win;
	long suicide_penalty;
};

/* Roster for one match. Humans are local controller slots; bots are Spartan bots. */
struct hcu_coop_roster
{
	unsigned humans;                 /* 1..HCU_COOP_MAX_HUMANS */
	unsigned bots;                   /* 0..HCU_COOP_MAX_BOTS */
};

enum hcu_coop_status
{
	HCU_COOP_OK = 0,
	HCU_COOP_ERR_MODE = 1,           /* unknown mode */
	HCU_COOP_ERR_ROSTER = 2,         /* humans or bots outside limits */
	HCU_COOP_ERR_UNSUPPORTED = 3,    /* mode is not cooperative; cannot host humans-vs-bots team split */
	HCU_COOP_ERR_VARIANT = 4,        /* runtime CE variant disagrees with the qualified row */
	HCU_COOP_ERR_ARGUMENT = 5,
};

/* Returns the row for a mode, or NULL. Table is static and read-only. */
const struct hcu_coop_mode_row *hcu_coop_mode_row(enum hcu_coop_mode mode);

/* Number of table rows (HCU_COOP_MODE_COUNT). */
size_t hcu_coop_mode_count(void);

/* Checks the roster against the limits. */
enum hcu_coop_status hcu_coop_check_roster(const struct hcu_coop_roster *roster);

/* Checks that a runtime CE variant snapshot matches the stock row for `mode` (engine, teams, respawn,
 * score-to-win, suicide penalty). Call before map teardown; any mismatch is a refusal, not a silent override. */
enum hcu_coop_status hcu_coop_check_variant(enum hcu_coop_mode mode, const struct hcu_coop_variant_snapshot *snapshot);

/* Full setup gate: mode exists, roster in range, variant matches, and (if humans_share_team) the mode is
 * cooperative_eligible. Returns HCU_COOP_OK when the mode/roster may be admitted. */
enum hcu_coop_status hcu_coop_admit(enum hcu_coop_mode mode, const struct hcu_coop_roster *roster,
                                    const struct hcu_coop_variant_snapshot *snapshot, int humans_share_team);

/* Team assignment for the roster in a cooperative mode. Writes one team index per participant:
 * human_teams[0..humans-1] = HCU_COOP_HUMAN_TEAM, bot_teams[0..bots-1] = HCU_COOP_BOT_TEAM.
 * Only cooperative_eligible modes are accepted. Buffers must hold the roster counts. */
enum hcu_coop_status hcu_coop_assign_teams(enum hcu_coop_mode mode, const struct hcu_coop_roster *roster,
                                           unsigned char *human_teams, unsigned char *bot_teams);

#ifdef __cplusplus
}
#endif

#endif /* HALO_STREAM_HCU_COOP_MODES_H */
