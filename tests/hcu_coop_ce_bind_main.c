/* C5: humans-on-one-team-vs-bots under the verbatim CE team-mode rules.
 *
 * The ce_* functions below are provided by a generated translation unit (tests/test_hcu_coop_ce_bind.py). That unit
 * contains the verbatim bodies of game_engine_should_end_game, multiple_teams_alive, game_engine_player_killed and
 * game_engine_should_spawn_player (and the helpers they call) copied from submodules/halo-ce-universal, plus mock
 * state with the same field names. This driver only sets state and reads results; it applies no rule itself. */
#include <stdio.h>

#include "stream/hcu_coop_modes.h"
#include "stream/hcu_coop_ce_bind.h"

extern void ce_harness_reset(void);
extern void ce_harness_set_variant(long engine_index, int teams, long respawn_time, long respawn_time_growth,
                                   long suicide_penalty, long score_to_win, long lives, int odd_man_out);
extern void ce_harness_set_auto_team_balance(int on);
extern void ce_harness_set_friendly_fire_penalty(long seconds);
extern void ce_harness_set_time_limit(long minutes);
extern void ce_harness_set_game_time(long ticks);
extern void ce_harness_add_player(long index, long team_index, int has_unit);
extern void ce_harness_set_quit(long index);
extern void ce_harness_set_unit(long index, int has_unit);
extern void ce_harness_set_deaths(long index, long deaths);
extern long ce_harness_team_of(long index);
extern long ce_harness_respawn_timer(long index);
extern long ce_harness_match_asserts(void);
extern int ce_entry_should_end_game(void);
extern int ce_entry_multiple_teams_alive(void);
extern void ce_entry_player_killed(long killer, long object, long dead, int friendly_fire);
extern int ce_entry_should_spawn_player(long index);

#define CE_NONE (-1L)
#define CE_TICKS_PER_SECOND 30L
#define CE_MIN_RESPAWN_TICKS 90L /* game_engine_player_killed clamps the respawn timer to at least this */

static int failures;

#define CHECK(cond) do { if (!(cond)) { printf("FAIL %s line %d\n", #cond, __LINE__); failures++; } } while (0)

static long max_long(long a, long b)
{
	return a > b ? a : b;
}

/* CE's respawn timer after a death: penalty + respawn_time (+ suicide penalty when not a player kill, + the
 * team killer's friendly fire penalty), clamped to at least 90 ticks. */
static long expected_timer(long respawn_time, long extra)
{
	return max_long(respawn_time + extra, CE_MIN_RESPAWN_TICKS);
}

static void fresh(enum hcu_coop_mode mode, struct hcu_coop_roster roster, struct hcu_coop_ce_binding *b)
{
	unsigned i;
	enum hcu_coop_ce_status status = hcu_coop_ce_bind(mode, &roster, b);

	CHECK(status == HCU_COOP_CE_OK);
	ce_harness_reset();
	ce_harness_set_variant(b->variant.game_engine_index, b->variant.teams, b->variant.respawn_time,
		b->variant.respawn_time_growth, b->variant.suicide_penalty, b->variant.score_to_win,
		b->variant.lives, b->variant.odd_man_out);
	ce_harness_set_auto_team_balance(b->variant.auto_team_balance);
	for (i = 0; i < b->humans + b->bots; ++i)
		ce_harness_add_player((long)i, (long)b->team_index[i], 1);
}

static void check_victory(enum hcu_coop_mode mode, struct hcu_coop_roster roster)
{
	struct hcu_coop_ce_binding b;
	unsigned i, n = roster.humans + roster.bots;

	/* everyone present: no end */
	fresh(mode, roster, &b);
	CHECK(ce_entry_multiple_teams_alive() == 1);
	CHECK(ce_entry_should_end_game() == 0);

	/* deaths alone do not end a team game (lives 0: a dead player is still in the match) */
	fresh(mode, roster, &b);
	for (i = 0; i < n; ++i) {
		ce_harness_set_unit((long)i, 0);
		ce_harness_set_deaths((long)i, 1);
	}
	CHECK(ce_entry_should_end_game() == 0);

	/* all bots gone: humans win */
	fresh(mode, roster, &b);
	for (i = roster.humans; i < n; ++i)
		ce_harness_set_quit((long)i);
	CHECK(ce_entry_multiple_teams_alive() == 0);
	CHECK(ce_entry_should_end_game() == 1);

	/* all humans gone: bots win */
	fresh(mode, roster, &b);
	for (i = 0; i < roster.humans; ++i)
		ce_harness_set_quit((long)i);
	CHECK(ce_entry_should_end_game() == 1);

	/* one bot left: still a bot team, no end */
	if (roster.bots >= 2) {
		fresh(mode, roster, &b);
		ce_harness_set_quit((long)roster.humans);
		CHECK(ce_entry_should_end_game() == 0);
	}

	/* time limit (minutes) ends the match on its own */
	fresh(mode, roster, &b);
	ce_harness_set_time_limit(1);
	ce_harness_set_game_time(60L * CE_TICKS_PER_SECOND - 1L);
	CHECK(ce_entry_should_end_game() == 0);
	ce_harness_set_game_time(60L * CE_TICKS_PER_SECOND);
	CHECK(ce_entry_should_end_game() == 1);
}

static void check_respawn(enum hcu_coop_mode mode, struct hcu_coop_roster roster)
{
	struct hcu_coop_ce_binding b;
	long rt, sp;
	long bot = (long)roster.humans;
	long timer;
	long k, first = -1;

	fresh(mode, roster, &b);
	rt = b.variant.respawn_time;
	sp = b.variant.suicide_penalty;

	/* human kills bot: the victim gets the team respawn time (no suicide penalty) */
	ce_entry_player_killed(0, CE_NONE, bot, 0);
	CHECK(ce_harness_respawn_timer(bot) == expected_timer(rt, 0));

	/* bot kills human */
	fresh(mode, roster, &b);
	ce_entry_player_killed(bot, CE_NONE, 0, 0);
	CHECK(ce_harness_respawn_timer(0) == expected_timer(rt, 0));

	/* suicide: the suicide penalty applies */
	fresh(mode, roster, &b);
	ce_entry_player_killed(0, CE_NONE, 0, 0);
	CHECK(ce_harness_respawn_timer(0) == expected_timer(rt, sp));

	/* respawn timing: the victim spawns on the tick the timer runs out, on its own tick slot */
	fresh(mode, roster, &b);
	ce_entry_player_killed(0, CE_NONE, bot, 0);
	timer = ce_harness_respawn_timer(bot);
	ce_harness_set_unit(bot, 0);
	ce_harness_set_deaths(bot, 1);
	for (k = 1; k <= timer + 2 && first < 0; ++k) {
		ce_harness_set_game_time(32L * (k + 10L) + (bot % 32L));
		if (ce_entry_should_spawn_player(bot))
			first = k;
	}
	CHECK(first == timer);

	if (roster.humans >= 2) {
		/* team kill (teams TRUE): the victim takes the suicide penalty; the killer's next death carries
		 * the friendly fire penalty */
		fresh(mode, roster, &b);
		ce_harness_set_friendly_fire_penalty(5);
		ce_entry_player_killed(0, CE_NONE, 1, 1);
		CHECK(ce_harness_respawn_timer(1) == expected_timer(rt, sp));
		ce_harness_set_unit(0, 0);
		ce_entry_player_killed(bot, CE_NONE, 0, 0);
		CHECK(ce_harness_respawn_timer(0) == expected_timer(rt, 5L * CE_TICKS_PER_SECOND));
	}
}

static void check_auto_balance(enum hcu_coop_mode mode, struct hcu_coop_roster roster)
{
	struct hcu_coop_ce_binding b;
	long bot = (long)roster.humans;

	/* 2 humans vs 4 bots: a killed bot is moved to the human team when auto balance is on
	 * (bots 4 >= humans 2 + 2), which would break the human/bot split; off, it stays on the bot team */
	fresh(mode, roster, &b);
	CHECK(b.variant.auto_team_balance == 0);
	ce_entry_player_killed(0, CE_NONE, bot, 0);
	CHECK(ce_harness_team_of(bot) == HCU_COOP_BOT_TEAM);

	fresh(mode, roster, &b);
	ce_harness_set_auto_team_balance(1);
	ce_entry_player_killed(0, CE_NONE, bot, 0);
	CHECK(ce_harness_team_of(bot) == HCU_COOP_HUMAN_TEAM);
}

static void check_mode(enum hcu_coop_mode mode, struct hcu_coop_roster roster)
{
	struct hcu_coop_ce_binding b;
	unsigned i, n = roster.humans + roster.bots;

	fresh(mode, roster, &b);
	CHECK(b.variant.teams == 1);
	CHECK(b.variant.auto_team_balance == 0);
	CHECK(b.variant.lives == 0);
	CHECK(b.variant.odd_man_out == 0);
	CHECK(b.variant.respawn_time_growth == 0);
	for (i = 0; i < n; ++i) {
		unsigned want = i < roster.humans ? HCU_COOP_HUMAN_TEAM : HCU_COOP_BOT_TEAM;
		CHECK(ce_harness_team_of((long)i) == (long)want);
	}
	CHECK(hcu_coop_ce_check_live(&b, &b.variant) == HCU_COOP_CE_OK);

	check_victory(mode, roster);
	check_respawn(mode, roster);
	if (roster.humans == 2 && roster.bots == 4)
		check_auto_balance(mode, roster);
}

static void check_admission(void)
{
	struct hcu_coop_ce_binding b;
	struct hcu_coop_roster good = { 2u, 4u };
	struct hcu_coop_roster too_many_humans = { 5u, 0u };
	struct hcu_coop_roster too_many_bots = { 1u, HCU_COOP_MAX_BOTS + 1u };
	enum hcu_coop_mode ffa[] = {
		HCU_COOP_MODE_SLAYER_FFA, HCU_COOP_MODE_ODDBALL_FFA,
		HCU_COOP_MODE_KING_FFA, HCU_COOP_MODE_RACE_FFA,
	};
	struct hcu_coop_ce_variant live = { 0 };
	unsigned i;

	for (i = 0; i < sizeof(ffa) / sizeof(ffa[0]); ++i)
		CHECK(hcu_coop_ce_bind(ffa[i], &good, &b) == HCU_COOP_CE_ERR_ADMIT);
	CHECK(hcu_coop_ce_bind(HCU_COOP_MODE_TEAM_SLAYER, &too_many_humans, &b) == HCU_COOP_CE_ERR_ADMIT);
	CHECK(hcu_coop_ce_bind(HCU_COOP_MODE_TEAM_SLAYER, &too_many_bots, &b) == HCU_COOP_CE_ERR_ADMIT);
	CHECK(hcu_coop_ce_bind((enum hcu_coop_mode)99, &good, &b) == HCU_COOP_CE_ERR_ADMIT);
	CHECK(hcu_coop_ce_bind(HCU_COOP_MODE_CTF, NULL, &b) == HCU_COOP_CE_ERR_ARGUMENT);

	/* a live value that differs from the binding is refused (auto balance left on) */
	CHECK(hcu_coop_ce_bind(HCU_COOP_MODE_CTF, &good, &b) == HCU_COOP_CE_OK);
	live = b.variant;
	live.auto_team_balance = 1;
	CHECK(hcu_coop_ce_check_live(&b, &live) == HCU_COOP_CE_ERR_MISMATCH);
}

int main(void)
{
	static const enum hcu_coop_mode team_modes[] = {
		HCU_COOP_MODE_TEAM_SLAYER, HCU_COOP_MODE_CTF, HCU_COOP_MODE_TEAM_ODDBALL,
		HCU_COOP_MODE_TEAM_KING, HCU_COOP_MODE_TEAM_RACE,
	};
	struct hcu_coop_roster rosters[] = { { 2u, 4u }, { 1u, 1u } };
	unsigned m, r;

	check_admission();
	for (m = 0; m < sizeof(team_modes) / sizeof(team_modes[0]); ++m)
		for (r = 0; r < sizeof(rosters) / sizeof(rosters[0]); ++r)
			check_mode(team_modes[m], rosters[r]);

	CHECK(ce_harness_match_asserts() == 0);
	if (failures) {
		printf("hcu_coop_ce_bind: %d failure(s)\n", failures);
		return 1;
	}
	printf("hcu_coop_ce_bind tests passed\n");
	return 0;
}
