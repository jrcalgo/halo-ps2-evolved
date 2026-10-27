/* C5 integration session. See hcu_c5_session.h for the start order, the hash order and the markers. */
#include "stream/hcu_c5_session.h"

#include <stdarg.h>
#include <stdio.h>
#include <stdio.h>
#include <string.h>

#define HCU_C5_HASH_DOMAIN 0xC5500001u
#define HCU_C5_FNV_OFFSET 0xcbf29ce484222325ULL
#define HCU_C5_FNV_PRIME 0x100000001b3ULL
#define HCU_C5_MARKER "HALO_PS2_C5 "
#define HCU_C5_SESSION_DEFAULT_ACTIVE_LIMIT 4u

/* ---- hash ---------------------------------------------------------------------------------------------- */

struct c5_hash {
	uint64_t value;
};

static void hash_byte(struct c5_hash *h, uint8_t byte)
{
	h->value ^= (uint64_t)byte;
	h->value *= HCU_C5_FNV_PRIME;
}

static void hash_u32(struct c5_hash *h, uint32_t v)
{
	int i;
	for (i = 0; i < 4; i++) {
		hash_byte(h, (uint8_t)(v & 0xffu));
		v >>= 8;
	}
}

static void hash_u64(struct c5_hash *h, uint64_t v)
{
	int i;
	for (i = 0; i < 8; i++) {
		hash_byte(h, (uint8_t)(v & 0xffu));
		v >>= 8;
	}
}

/* ---- maps ---------------------------------------------------------------------------------------------- */

int hcu_c5_session_coop_mode(hcu_local_variant variant, enum hcu_coop_mode *mode)
{
	if (mode == NULL) {
		return -1;
	}
	switch (variant) {
	case HCU_LOCAL_VARIANT_SLAYER: *mode = HCU_COOP_MODE_TEAM_SLAYER; return 0;
	case HCU_LOCAL_VARIANT_CTF: *mode = HCU_COOP_MODE_CTF; return 0;
	case HCU_LOCAL_VARIANT_ODDBALL: *mode = HCU_COOP_MODE_TEAM_ODDBALL; return 0;
	case HCU_LOCAL_VARIANT_KING: *mode = HCU_COOP_MODE_TEAM_KING; return 0;
	case HCU_LOCAL_VARIANT_RACE: *mode = HCU_COOP_MODE_TEAM_RACE; return 0;
	default: return -1;
	}
}

int hcu_c5_session_bot_skill(hcu_local_difficulty difficulty, uint8_t *skill)
{
	if (skill == NULL) {
		return -1;
	}
	switch (difficulty) {
	case HCU_LOCAL_DIFFICULTY_EASY: *skill = HCU_BOT_SKILL_EASY; return 0;
	case HCU_LOCAL_DIFFICULTY_NORMAL: *skill = HCU_BOT_SKILL_NORMAL; return 0;
	case HCU_LOCAL_DIFFICULTY_HEROIC: *skill = HCU_BOT_SKILL_HEROIC; return 0;
	case HCU_LOCAL_DIFFICULTY_LEGENDARY: *skill = HCU_BOT_SKILL_LEGENDARY; return 0;
	default: return -1;
	}
}

int hcu_c5_session_survival_difficulty(hcu_local_difficulty difficulty, hcu_survival_difficulty *out)
{
	if (out == NULL) {
		return -1;
	}
	switch (difficulty) {
	case HCU_LOCAL_DIFFICULTY_EASY: *out = HCU_SURVIVAL_DIFFICULTY_EASY; return 0;
	case HCU_LOCAL_DIFFICULTY_NORMAL: *out = HCU_SURVIVAL_DIFFICULTY_NORMAL; return 0;
	case HCU_LOCAL_DIFFICULTY_HEROIC: *out = HCU_SURVIVAL_DIFFICULTY_HEAVY; return 0;
	case HCU_LOCAL_DIFFICULTY_LEGENDARY: *out = HCU_SURVIVAL_DIFFICULTY_LEGENDARY; return 0;
	default: return -1;
	}
}

/* ---- markers ------------------------------------------------------------------------------------------- */

static void emit_line(const struct hcu_c5_session *s, const char *fmt, ...)
{
	char line[256];
	va_list args;
	int n;

	if (s->ops.emit == NULL) {
		return;
	}
	n = snprintf(line, sizeof line, "%s", HCU_C5_MARKER);
	if (n < 0 || (size_t)n >= sizeof line) {
		return;
	}
	va_start(args, fmt);
	vsnprintf(line + n, sizeof line - (size_t)n, fmt, args);
	va_end(args);
	s->ops.emit(s->ops.user, line);
}

static const char *mode_name(enum hcu_c5_session_mode mode)
{
	switch (mode) {
	case HCU_C5_SESSION_MODE_COOP: return "coop";
	case HCU_C5_SESSION_MODE_SURVIVAL: return "survival";
	default: return "none";
	}
}

static const char *difficulty_name(hcu_local_difficulty difficulty)
{
	switch (difficulty) {
	case HCU_LOCAL_DIFFICULTY_EASY: return "easy";
	case HCU_LOCAL_DIFFICULTY_NORMAL: return "normal";
	case HCU_LOCAL_DIFFICULTY_HEROIC: return "heroic";
	case HCU_LOCAL_DIFFICULTY_LEGENDARY: return "legendary";
	default: return "none";
	}
}

static const char *event_name(enum hcu_c5_session_event event)
{
	switch (event) {
	case HCU_C5_EVENT_NAV: return "nav";
	case HCU_C5_EVENT_FIGHT: return "fight";
	case HCU_C5_EVENT_KILL: return "kill";
	case HCU_C5_EVENT_DEATH: return "death";
	case HCU_C5_EVENT_RESPAWN: return "respawn";
	case HCU_C5_EVENT_SCORE: return "score";
	}
	return "unknown";
}

/* ---- start --------------------------------------------------------------------------------------------- */

static int build_bot_config(const hcu_local_setup *setup, hcu_bot_config *config)
{
	memset(config, 0, sizeof *config);
	config->seed = setup->seed;
	config->count = (uint8_t)setup->bot_count;
	config->team_mode = 1;
	config->bot_team = HCU_C5_BOT_TEAM;
	return hcu_c5_session_bot_skill(setup->difficulty, &config->skill);
}

enum hcu_c5_session_status hcu_c5_session_start(struct hcu_c5_session *session,
                                                const hcu_local_setup *setup,
                                                const hcu_local_qualified_row *rows, size_t row_count,
                                                const struct hcu_c5_session_ops *ops,
                                                const struct hcu_c5_session_options *options)
{
	hcu_local_setup_reason reason;
	hcu_survival_config cfg;
	hcu_survival_difficulty difficulty;
	hcu_survival_status status;
	struct hcu_coop_roster roster;
	enum hcu_coop_ce_status coop;
	hcu_bot_config bot_config;

	if (session == NULL || setup == NULL || ops == NULL) {
		return HCU_C5_SESSION_ERR_ARGUMENT;
	}
	memset(session, 0, sizeof *session);
	session->ops = *ops;

	/* 1. validate, then teardown only on acceptance */
	reason = hcu_local_setup_admit(setup, rows, row_count, ops->teardown, ops->user, &session->setup_result);
	session->setup_reason = reason;
	if (reason != HCU_LOCAL_SETUP_OK) {
		emit_line(session, "session-refused reason=%s", hcu_local_setup_reason_name(reason));
		return HCU_C5_SESSION_ERR_SETUP;
	}

	if (setup->mode == HCU_LOCAL_MODE_STOCK_COOP) {
		/* 2. coop binding */
		session->mode = HCU_C5_SESSION_MODE_COOP;
		if (hcu_c5_session_coop_mode(setup->variant, &session->coop_mode) != 0) {
			return HCU_C5_SESSION_ERR_COOP;
		}
		roster.humans = session->setup_result.human_count;
		roster.bots = session->setup_result.bot_count;
		coop = hcu_coop_ce_bind(session->coop_mode, &roster, &session->binding);
		if (coop != HCU_COOP_CE_OK) {
			session->mode = HCU_C5_SESSION_MODE_NONE;
			emit_line(session, "session-refused reason=coop-bind status=%d", (int)coop);
			return HCU_C5_SESSION_ERR_COOP;
		}
		/* 3. bots, only when the roster has them */
		if (session->binding.bots > 0) {
			if (build_bot_config(setup, &bot_config) != 0 || ops->bots_start == NULL) {
				return HCU_C5_SESSION_ERR_BOTS;
			}
			if (ops->bots_start(ops->user, &bot_config, &session->binding) != 0) {
				return HCU_C5_SESSION_ERR_BOTS;
			}
			session->bots_running = 1;
		}
	} else if (setup->mode == HCU_LOCAL_MODE_SURVIVAL) {
		/* 4. survival: bots are never part of a survival roster in this session */
		session->mode = HCU_C5_SESSION_MODE_SURVIVAL;
		if (setup->bot_count != 0) {
			return HCU_C5_SESSION_ERR_MODE;
		}
		if (hcu_c5_session_survival_difficulty(setup->difficulty, &difficulty) != 0) {
			return HCU_C5_SESSION_ERR_SURVIVAL;
		}
		memset(&cfg, 0, sizeof cfg);
		cfg.difficulty = difficulty;
		cfg.seed = setup->seed;
		cfg.humans = session->setup_result.human_count;
		/* 0 selects the default batch of 4 enemies (HCU_C5_SESSION_DEFAULT_ACTIVE_LIMIT). */
		cfg.active_limit = (options != NULL && options->survival_active_limit != 0u)
			? options->survival_active_limit : HCU_C5_SESSION_DEFAULT_ACTIVE_LIMIT;
		cfg.templates = options != NULL ? options->survival_templates : NULL;
		cfg.template_count = options != NULL ? options->survival_template_count : 0u;
		status = hcu_survival_init(&session->survival, &cfg);
		if (status != HCU_SURVIVAL_OK) {
			return HCU_C5_SESSION_ERR_SURVIVAL;
		}
		status = hcu_survival_begin(&session->survival);
		if (status != HCU_SURVIVAL_OK) {
			return HCU_C5_SESSION_ERR_SURVIVAL;
		}
		session->wave_seen = hcu_survival_wave_number(&session->survival);
		session->state_seen = hcu_survival_get_state(&session->survival);
	} else {
		return HCU_C5_SESSION_ERR_MODE;
	}

	session->started = 1;
	/* coop is the CE mode number (enum hcu_coop_mode) for coop sessions and -1 otherwise. */
	/* status=measuring marks a MEASURE run: its log claims no qualification (tools/c5_guest_qualification.py). The map
	 * name is a printable name without spaces (hcu_local_setup_validate refuses any other). */
	emit_line(session, "session-start mode=%s coop=%d humans=%u bots=%u qualified=%u map=%s difficulty=%s status=%s",
	          mode_name(session->mode),
	          session->mode == HCU_C5_SESSION_MODE_COOP ? (int)session->coop_mode : -1,
	          session->setup_result.human_count, session->setup_result.bot_count,
	          session->setup_result.qualified_population, setup->map_name,
	          difficulty_name(setup->difficulty),
	          hcu_local_setup_status_name(session->setup_result.status));
	return HCU_C5_SESSION_OK;
}

/* ---- tick and events ----------------------------------------------------------------------------------- */

enum hcu_c5_session_status hcu_c5_session_tick(struct hcu_c5_session *session)
{
	hcu_survival_state state;
	unsigned int wave;

	if (session == NULL) {
		return HCU_C5_SESSION_ERR_ARGUMENT;
	}
	if (!session->started) {
		return HCU_C5_SESSION_ERR_STATE;
	}
	session->tick++;
	if (session->mode != HCU_C5_SESSION_MODE_SURVIVAL) {
		return HCU_C5_SESSION_OK;
	}
	if (hcu_survival_get_state(&session->survival) != HCU_SURVIVAL_STATE_GAME_OVER) {
		hcu_survival_tick(&session->survival);
	}
	state = hcu_survival_get_state(&session->survival);
	wave = hcu_survival_wave_number(&session->survival);
	if (wave != session->wave_seen) {
		session->wave_seen = wave;
		emit_line(session, "survival-wave tick=%u wave=%u batch=%u humans=%u units=%u",
		          (unsigned)session->tick, wave, hcu_survival_batch_size(&session->survival),
		          hcu_survival_living_humans(&session->survival),
		          hcu_survival_active_units(&session->survival));
	}
	if (state != session->state_seen) {
		session->state_seen = state;
		if (state == HCU_SURVIVAL_STATE_GAME_OVER) {
			emit_line(session, "survival-over tick=%u wave=%u waves-cleared=%u",
			          (unsigned)session->tick, wave, session->survival.waves_cleared);
		}
	}
	return HCU_C5_SESSION_OK;
}

enum hcu_c5_session_status hcu_c5_session_note_event(struct hcu_c5_session *session,
                                                     enum hcu_c5_session_event event, uint32_t bot, long arg)
{
	if (session == NULL) {
		return HCU_C5_SESSION_ERR_ARGUMENT;
	}
	if (!session->started) {
		return HCU_C5_SESSION_ERR_STATE;
	}
	switch (event) {
	case HCU_C5_EVENT_NAV: session->metrics.nav_steps++; break;
	case HCU_C5_EVENT_FIGHT: session->metrics.fights++; break;
	case HCU_C5_EVENT_KILL: session->metrics.kills++; break;
	case HCU_C5_EVENT_DEATH: session->metrics.deaths++; break;
	case HCU_C5_EVENT_RESPAWN: session->metrics.respawns++; break;
	case HCU_C5_EVENT_SCORE: session->metrics.score_events++; break;
	default: return HCU_C5_SESSION_ERR_ARGUMENT;
	}
	emit_line(session, "bot-event tick=%u kind=%s bot=%u arg=%ld",
	          (unsigned)session->tick, event_name(event), (unsigned)bot, arg);
	return HCU_C5_SESSION_OK;
}

void hcu_c5_session_bot_sink(void *user, int kind, uint32_t bot, long arg)
{
	if (user == NULL || kind < (int)HCU_C5_EVENT_NAV || kind > (int)HCU_C5_EVENT_SCORE) {
		return;
	}
	(void)hcu_c5_session_note_event((struct hcu_c5_session *)user, (enum hcu_c5_session_event)kind, bot, arg);
}

hcu_survival *hcu_c5_session_survival(struct hcu_c5_session *session)
{
	if (session == NULL || session->mode != HCU_C5_SESSION_MODE_SURVIVAL || !session->started) {
		return NULL;
	}
	return &session->survival;
}

/* ---- hash ---------------------------------------------------------------------------------------------- */

uint64_t hcu_c5_session_hash(const struct hcu_c5_session *session)
{
	struct c5_hash h;
	const hcu_survival *s;
	uint64_t bot_hash = 0u;
	unsigned int k;
	int survival_on;

	h.value = HCU_C5_FNV_OFFSET;
	if (session == NULL) {
		hash_u32(&h, HCU_C5_HASH_DOMAIN);
		return h.value;
	}
	survival_on = session->mode == HCU_C5_SESSION_MODE_SURVIVAL && session->started;
	s = survival_on ? &session->survival : NULL;

	hash_u32(&h, HCU_C5_HASH_DOMAIN);                       /* a */
	hash_u32(&h, (uint32_t)session->mode);                  /* b */
	hash_u32(&h, session->tick);                            /* c */
	if (session->bots_running && session->ops.bots_hash != NULL) {
		bot_hash = session->ops.bots_hash(session->ops.user);
	}
	hash_u64(&h, bot_hash);                                 /* d */
	hash_u32(&h, s ? (uint32_t)s->state : 0u);              /* e */
	hash_u32(&h, s ? s->wave_number : 0u);
	hash_u32(&h, s ? hcu_survival_living_humans(s) : 0u);
	hash_u32(&h, s ? hcu_survival_active_units(s) : 0u);
	hash_u32(&h, s ? hcu_survival_reserved_units(s) : 0u);
	hash_u32(&h, s ? s->batch_size : 0u);
	hash_u32(&h, s ? s->intermission_left : 0u);
	hash_u32(&h, s ? s->waves_cleared : 0u);
	hash_u32(&h, s ? s->enemies_admitted : 0u);
	hash_u32(&h, s ? s->humans_respawned : 0u);
	for (k = 0u; k < HCU_SURVIVAL_BUDGET_KIND_COUNT; k++) {    /* f */
		hash_u32(&h, s ? hcu_survival_budget_count(s, (hcu_survival_budget_kind)k) : 0u);
		hash_u32(&h, s ? hcu_survival_budget_evicted(s, (hcu_survival_budget_kind)k) : 0u);
		hash_u32(&h, s ? hcu_survival_budget_refused(s, (hcu_survival_budget_kind)k) : 0u);
	}
	hash_u32(&h, session->metrics.kills);                   /* g */
	hash_u32(&h, session->metrics.deaths);
	hash_u32(&h, session->metrics.respawns);
	hash_u32(&h, session->metrics.nav_steps);
	hash_u32(&h, session->metrics.fights);
	hash_u32(&h, session->metrics.score_events);
	return h.value;
}

enum hcu_c5_session_status hcu_c5_session_report(const struct hcu_c5_session *session)
{
	if (session == NULL) {
		return HCU_C5_SESSION_ERR_ARGUMENT;
	}
	emit_line(session, "session-hash tick=%u hash=%016llx",
	          (unsigned)session->tick, (unsigned long long)hcu_c5_session_hash(session));
	return HCU_C5_SESSION_OK;
}

const char *hcu_c5_session_status_name(enum hcu_c5_session_status status)
{
	switch (status) {
	case HCU_C5_SESSION_OK: return "ok";
	case HCU_C5_SESSION_ERR_ARGUMENT: return "argument";
	case HCU_C5_SESSION_ERR_SETUP: return "setup-refused";
	case HCU_C5_SESSION_ERR_COOP: return "coop-refused";
	case HCU_C5_SESSION_ERR_BOTS: return "bots-refused";
	case HCU_C5_SESSION_ERR_SURVIVAL: return "survival-refused";
	case HCU_C5_SESSION_ERR_MODE: return "mode-refused";
	case HCU_C5_SESSION_ERR_STATE: return "state";
	}
	return "unknown";
}
