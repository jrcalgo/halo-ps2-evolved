/* C5 integration session: the one entry the integrator calls at local game setup.
 *
 * Given an accepted-or-refused hcu_local_setup request, the session runs, in this order:
 *   1. hcu_local_setup_admit   validates; on acceptance calls the teardown callback (map teardown).
 *   2. coop mode:              hcu_coop_ce_bind (the CE team binding of the mode, humans on team 0).
 *   3. coop mode with bots:    ops->bots_start (ps2_bots_start) with the binding.
 *   4. survival mode:          hcu_survival_init, then hcu_survival_begin (wave 1 is admitted).
 * Teardown is the only side effect before the bots start, so a refused request leaves the loaded map alone.
 *
 * Every CE or EE call is behind hcu_c5_session_ops, so the session is host-testable with fakes
 * (tests/hcu_c5_session_main.c). The integrator fills ops with the real CE adapters (see
 * docs/reports/m4-c5-integration-wiring-2026-10-26.md).
 *
 * Per tick the integrator calls hcu_c5_session_tick (survival resolves here, markers are emitted on wave and
 * game-over changes). Bot events from CE (nav, fight, kill, death, respawn, score) are reported with
 * hcu_c5_session_note_event. hcu_c5_session_report emits the hash marker.
 *
 * Hash order (FNV-1a 64; every u32 is folded as 4 little-endian bytes, every u64 as 8, no struct padding):
 *   a. domain tag 0xC5500001
 *   b. session mode (0 none, 1 stock coop, 2 survival)
 *   c. tick count
 *   d. bot hash (ops->bots_hash when a roster runs, else 0 as u64)
 *   e. survival: state, wave_number, living humans, active_units, reserved_units, batch_size,
 *      intermission_left, waves_cleared, enemies_admitted, humans_respawned
 *   f. survival budgets, for each kind in enum order: count, evicted, refused
 *   g. metrics: kills, deaths, respawns, nav_steps, fights, score_events
 * Fields of a stopped or unused part fold as zero, so the layout is fixed for every mode.
 *
 * Storage is caller-owned (no heap). C89 style, as the rest of src/stream. */
#ifndef HALO_STREAM_HCU_C5_SESSION_H
#define HALO_STREAM_HCU_C5_SESSION_H

#include <stddef.h>
#include <stdint.h>

#include "stream/hcu_bot.h"
#include "stream/hcu_coop_ce_bind.h"
#include "stream/hcu_coop_modes.h"
#include "stream/hcu_local_setup.h"
#include "stream/hcu_survival.h"

#ifdef __cplusplus
extern "C" {
#endif

enum hcu_c5_session_status {
	HCU_C5_SESSION_OK = 0,
	HCU_C5_SESSION_ERR_ARGUMENT,  /* null pointer or bad argument */
	HCU_C5_SESSION_ERR_SETUP,     /* refused by hcu_local_setup_admit (see session->setup_reason) */
	HCU_C5_SESSION_ERR_COOP,      /* no coop mode for the variant, or the binding was refused */
	HCU_C5_SESSION_ERR_BOTS,      /* ops->bots_start failed */
	HCU_C5_SESSION_ERR_SURVIVAL,  /* hcu_survival_init or _begin refused the config */
	HCU_C5_SESSION_ERR_MODE,      /* survival with bots, or a mode this session does not run */
	HCU_C5_SESSION_ERR_STATE      /* call before start, or after a failed start */
};

enum hcu_c5_session_mode {
	HCU_C5_SESSION_MODE_NONE = 0,
	HCU_C5_SESSION_MODE_COOP = 1,
	HCU_C5_SESSION_MODE_SURVIVAL = 2
};

enum hcu_c5_session_event {
	HCU_C5_EVENT_NAV = 0,  /* a bot followed a CE path step (arg: step index) */
	HCU_C5_EVENT_FIGHT,    /* a bot fired at a target (arg: target player index) */
	HCU_C5_EVENT_KILL,     /* a bot credited a kill (arg: victim player index) */
	HCU_C5_EVENT_DEATH,    /* a bot died (arg: killer player index, or -1) */
	HCU_C5_EVENT_RESPAWN,  /* a bot respawned (arg: the bot's spawn count; emitted from its second spawn on) */
	HCU_C5_EVENT_SCORE     /* the mode's score or objective changed (arg: new value) */
};

/* Environment hooks. Every pointer may be NULL except where stated; a NULL hook is a refusal where the
 * step needs it (bots_start is needed for coop with bots, bots_hash for a running roster). */
struct hcu_c5_session_ops {
	void *user;
	/* Map teardown, passed to hcu_local_setup_admit. NULL skips teardown. */
	hcu_local_teardown_fn teardown;
	/* ps2_bots_start(config, binding). Returns 0 on success. */
	int (*bots_start)(void *user, const hcu_bot_config *config, const struct hcu_coop_ce_binding *binding);
	/* ps2_bots_hash(). */
	uint64_t (*bots_hash)(void *user);
	/* Receives one complete marker line without a newline. NULL is silent. */
	void (*emit)(void *user, const char *line);
};

struct hcu_c5_session_options {
	unsigned int survival_active_limit;          /* enemies per batch, survival only; 0 selects 4 */
	const hcu_survival_template *survival_templates; /* NULL selects the built-in table */
	unsigned int survival_template_count;
};

struct hcu_c5_metrics {
	uint32_t kills;
	uint32_t deaths;
	uint32_t respawns;
	uint32_t nav_steps;
	uint32_t fights;
	uint32_t score_events;
};

struct hcu_c5_session {
	struct hcu_c5_session_ops ops;
	enum hcu_c5_session_mode mode;
	int started;
	enum hcu_local_setup_reason setup_reason;   /* last admit reason (HCU_LOCAL_SETUP_OK when accepted) */
	hcu_local_setup_result setup_result;
	enum hcu_coop_mode coop_mode;
	struct hcu_coop_ce_binding binding;
	int bots_running;
	hcu_survival survival;                      /* valid when mode == SURVIVAL */
	uint32_t tick;
	unsigned int wave_seen;                     /* wave number last reported by tick */
	hcu_survival_state state_seen;              /* survival state last reported by tick */
	struct hcu_c5_metrics metrics;
};

/* Maps a stock-coop local variant to its CE coop mode (teams ON modes). Returns 0 and writes *mode, or -1. */
int hcu_c5_session_coop_mode(hcu_local_variant variant, enum hcu_coop_mode *mode);

/* Maps a local difficulty to the bot skill (HCU_BOT_SKILL_*). Returns 0 and writes *skill, or -1 for NONE. */
int hcu_c5_session_bot_skill(hcu_local_difficulty difficulty, uint8_t *skill);

/* Maps a local difficulty to the survival difficulty. Only NORMAL is qualified; hcu_survival_init refuses the rest. */
int hcu_c5_session_survival_difficulty(hcu_local_difficulty difficulty, hcu_survival_difficulty *out);

/* Runs the start sequence. `session` is caller storage; it is zeroed first. Returns HCU_C5_SESSION_OK on success.
 * On any failure the session is not started and no later step ran (teardown runs only after admission). */
enum hcu_c5_session_status hcu_c5_session_start(struct hcu_c5_session *session,
                                                const hcu_local_setup *setup,
                                                const hcu_local_qualified_row *rows, size_t row_count,
                                                const struct hcu_c5_session_ops *ops,
                                                const struct hcu_c5_session_options *options);

/* Advances one simulated tick. Survival resolves here; a wave change or game over emits a marker. */
enum hcu_c5_session_status hcu_c5_session_tick(struct hcu_c5_session *session);

/* Records one bot event and emits its marker line. `bot` is the bot index (or the player index for score). */
enum hcu_c5_session_status hcu_c5_session_note_event(struct hcu_c5_session *session,
                                                     enum hcu_c5_session_event event, uint32_t bot, long arg);

/* Callback shape the PS2 bot adapter calls (ps2_bots_set_event_sink, HALO_PS2_BOTS). `user` is a session, `kind` is an
 * enum hcu_c5_session_event value (out-of-range kinds are dropped). Pass the session as user when registering. */
void hcu_c5_session_bot_sink(void *user, int kind, uint32_t bot, long arg);

/* Survival controller for the adapter's kill calls (hcu_survival_kill_enemy / _kill_human), or NULL when not running. */
hcu_survival *hcu_c5_session_survival(struct hcu_c5_session *session);

/* Folds the whole session into one hash, in the documented order above. */
uint64_t hcu_c5_session_hash(const struct hcu_c5_session *session);

/* Emits the hash marker for the current tick. */
enum hcu_c5_session_status hcu_c5_session_report(const struct hcu_c5_session *session);

/* Stable name for a status code. */
const char *hcu_c5_session_status_name(enum hcu_c5_session_status status);

#ifdef __cplusplus
}
#endif

#endif /* HALO_STREAM_HCU_C5_SESSION_H */
