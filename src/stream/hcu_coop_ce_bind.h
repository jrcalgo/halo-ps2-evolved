/* C5: binds a qualified cooperative mode (hcu_coop_modes.h) to the CE values that the game must run with.
 *
 * This module is pure data. It decides the universal_variant and game_variant_options values a cooperative
 * match is started with (teams on, auto team balance off, no lives, no odd-man-out, no respawn growth), and the
 * team index of every participant (humans on HCU_COOP_HUMAN_TEAM, Spartan bots on HCU_COOP_BOT_TEAM). It does
 * not implement any victory, scoring or respawn rule; those stay in CE and are exercised by
 * tests/hcu_coop_ce_bind_main.c against the verbatim CE bodies (tests/test_hcu_coop_ce_bind.py). */
#ifndef HALO_STREAM_HCU_COOP_CE_BIND_H
#define HALO_STREAM_HCU_COOP_CE_BIND_H

#include "stream/hcu_coop_modes.h"

#ifdef __cplusplus
extern "C" {
#endif

enum hcu_coop_ce_status
{
	HCU_COOP_CE_OK = 0,
	HCU_COOP_CE_ERR_ADMIT = 1,       /* mode, roster or CE variant refused by hcu_coop_admit / assign */
	HCU_COOP_CE_ERR_ARGUMENT = 2,
	HCU_COOP_CE_ERR_MISMATCH = 3,    /* live CE values differ from the binding */
};

/* CE values written into global_variant.universal_variant and game_variant_options for the match. */
struct hcu_coop_ce_variant
{
	long game_engine_index;          /* CE game_engine_type */
	int teams;                       /* universal_variant.teams */
	long respawn_time;               /* universal_variant.respawn_time */
	long respawn_time_growth;        /* universal_variant.respawn_time_growth */
	long suicide_penalty;            /* universal_variant.suicide_penalty */
	long score_to_win;               /* universal_variant.score_to_win */
	long lives;                      /* universal_variant.lives */
	int odd_man_out;                 /* universal_variant.odd_man_out */
	int auto_team_balance;           /* game_variant_options.auto_team_balance */
};

struct hcu_coop_ce_binding
{
	enum hcu_coop_mode mode;
	struct hcu_coop_ce_variant variant;
	unsigned humans;
	unsigned bots;
	/* participant order: team_index[0..humans-1] are the humans, then the bots */
	unsigned char team_index[HCU_COOP_MAX_PLAYERS];
};

/* Admits `mode` with `roster` (cooperative modes only) and fills `out`. */
enum hcu_coop_ce_status hcu_coop_ce_bind(enum hcu_coop_mode mode, const struct hcu_coop_roster *roster,
                                         struct hcu_coop_ce_binding *out);

/* Compares live CE values (read by the integrator at match start) with the binding. */
enum hcu_coop_ce_status hcu_coop_ce_check_live(const struct hcu_coop_ce_binding *binding,
                                               const struct hcu_coop_ce_variant *live);

#ifdef __cplusplus
}
#endif

#endif /* HALO_STREAM_HCU_COOP_CE_BIND_H */
