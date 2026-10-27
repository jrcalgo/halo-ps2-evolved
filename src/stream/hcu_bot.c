/* C5.1-2: deterministic Spartan bots (see hcu_bot.h). Host-testable: no CE, renderer or EE headers.
 *
 * Each live bot, once per tick, in fixed index order:
 *   1. takes its alive flag and position from CE's percept of its player slot;
 *   2. picks a target (nearest visible enemy, else nearest enemy, kept while it lives) on a timer;
 *   3. decides whether it engages: a visible target within its weapon's fire range, fired in bursts whose
 *      pauses and aim error depend on skill, grenades and melee by chance and reach;
 *   4. moves: keeps its weapon's range from a visible target, goes to the last seen position when it cannot
 *      see one, to a better weapon within reach when no enemy is visible, then to the mode's objective.
 *      Steering follows CE's pathfinding waypoint when there is one, else the straight line; a bot that has
 *      not moved for a while jumps and strafe-unsticks.
 *   5. handles weapons: swaps to its other weapon when this one is empty, else reloads.
 *
 * Every random draw comes from the bot's own stream, seeded from the roster seed and its index. */
#include "stream/hcu_bot.h"

#include <string.h>

/* ---------- constants (game ticks: 30 Hz) */

#define BOT_EYE_HEIGHT 0.6f
#define BOT_TARGET_TICKS 20
#define BOT_STUCK_TICKS 30
#define BOT_STUCK_DISTANCE2 0.09f   /* moved less than 0.3 world units over a stuck window */
#define BOT_UNSTICK_TICKS 15
#define BOT_WEAPON_SEARCH_RANGE2 (14.f * 14.f)
#define BOT_PICKUP_REACH2 (1.0f * 1.0f)
#define BOT_MELEE_RANGE2 (1.2f * 1.2f)
#define BOT_MELEE_TICKS 30
#define BOT_GRENADE_TICKS 60
#define BOT_SWAP_TICKS 40
#define BOT_RELOAD_TICKS 30
#define BOT_STRAFE_TICKS 24

#define HCU_BOT_WEAPON_NONE 0xffu

/* The weapons it knows: how much it wants each, how it fires it, and the range it keeps with it. Names are CE
 * tag paths; the adapter resolves them with the map's tag index. */
typedef struct hcu_bot_weapon_def {
	const char *name;
	short score;
	short style;
	float near_range;
	float far_range;
} hcu_bot_weapon_def;

static const hcu_bot_weapon_def bot_weapons[] = {
	{ "weapons\\rocket launcher\\rocket launcher", 9, HCU_BOT_FIRE_EXPLOSIVE, 7.f, 18.f },
	{ "weapons\\sniper rifle\\sniper rifle", 8, HCU_BOT_FIRE_SEMI, 10.f, 28.f },
	{ "weapons\\shotgun\\shotgun", 8, HCU_BOT_FIRE_SEMI, 1.5f, 5.f },
	{ "weapons\\pistol\\pistol", 8, HCU_BOT_FIRE_SEMI, 4.f, 16.f },
	{ "weapons\\plasma_cannon\\plasma_cannon", 7, HCU_BOT_FIRE_EXPLOSIVE, 7.f, 18.f },
	{ "weapons\\assault rifle\\assault rifle", 6, HCU_BOT_FIRE_AUTO, 2.5f, 10.f },
	{ "weapons\\plasma rifle\\plasma rifle", 6, HCU_BOT_FIRE_AUTO, 3.f, 12.f },
	{ "weapons\\needler\\needler", 5, HCU_BOT_FIRE_AUTO, 4.f, 14.f },
	{ "weapons\\flamethrower\\flamethrower", 4, HCU_BOT_FIRE_AUTO, 1.5f, 5.f },
	{ "weapons\\plasma pistol\\plasma pistol", 3, HCU_BOT_FIRE_SEMI, 3.f, 12.f },
};
#define BOT_WEAPON_COUNT ((uint32_t)(sizeof(bot_weapons) / sizeof(bot_weapons[0])))

/* By skill (easy, normal, heroic, legendary). */
static const float bot_aim_error[HCU_BOT_SKILL_COUNT] = { 0.16f, 0.09f, 0.055f, 0.03f };
static const int16_t bot_burst_ticks[HCU_BOT_SKILL_COUNT] = { 8, 12, 16, 22 };
static const int16_t bot_pause_ticks[HCU_BOT_SKILL_COUNT] = { 34, 22, 14, 8 };
static const uint32_t bot_grenade_chance[HCU_BOT_SKILL_COUNT] = { 2, 4, 6, 8 }; /* in 1000 a tick */

/* ---------- small helpers (no libm: the host and the EE must agree bit for bit) */

static float bot_abs(float x)
{
	return x < 0.f ? -x : x;
}

static float bot_dist2(const float a[3], const float b[3])
{
	float dx = a[0] - b[0];
	float dy = a[1] - b[1];
	float dz = a[2] - b[2];
	return dx * dx + dy * dy + dz * dz;
}

static void bot_eye(const float pos[3], float eye[3])
{
	eye[0] = pos[0];
	eye[1] = pos[1];
	eye[2] = pos[2] + BOT_EYE_HEIGHT;
}

/* A world-plane stick toward (dx, dy), scaled so the larger component is 1 (no square root). */
static void bot_stick_toward(const float from[3], const float to[3], float stick[2])
{
	float dx = to[0] - from[0];
	float dy = to[1] - from[1];
	float m = bot_abs(dx) > bot_abs(dy) ? bot_abs(dx) : bot_abs(dy);
	if (m < 0.0001f) {
		stick[0] = 0.f;
		stick[1] = 0.f;
		return;
	}
	stick[0] = dx / m;
	stick[1] = dy / m;
}

static void bot_action_idle(hcu_bot_action *a)
{
	memset(a, 0, sizeof *a);
	a->swap = 0;
}

static uint32_t bot_mix32(uint32_t x)
{
	x ^= x >> 16;
	x *= 0x7feb352dU;
	x ^= x >> 15;
	x *= 0x846ca68bU;
	x ^= x >> 16;
	return x;
}

/* ---------- hashing (FNV-1a 64, fixed field order) */

#define BOT_FNV_OFFSET 0xcbf29ce484222325ULL
#define BOT_FNV_PRIME 0x100000001b3ULL

static uint64_t bot_hash_byte(uint64_t h, uint8_t b)
{
	return (h ^ b) * BOT_FNV_PRIME;
}

static uint64_t bot_hash_u32(uint64_t h, uint32_t v)
{
	int i;
	for (i = 0; i < 4; i++) {
		h = bot_hash_byte(h, (uint8_t)(v >> (8 * i)));
	}
	return h;
}

static uint64_t bot_hash_float(uint64_t h, float f)
{
	uint32_t bits;
	memcpy(&bits, &f, sizeof bits);
	return bot_hash_u32(h, bits);
}

/* ---------- public helpers */

uint32_t hcu_bot_name_index(uint32_t seed, uint32_t bot)
{
	/* Each step is prime to 40, so offset + step * bot visits every name once for bot < 40. */
	static const uint8_t steps[16] = { 1, 3, 7, 9, 11, 13, 17, 19, 21, 23, 27, 29, 31, 33, 37, 39 };
	uint32_t offset = seed % HCU_BOT_NAME_COUNT;
	uint32_t step = steps[((seed / HCU_BOT_NAME_COUNT) ^ (seed >> 16)) & 15u];
	return (offset + step * bot) % HCU_BOT_NAME_COUNT;
}

uint32_t hcu_bot_weapon_count(void)
{
	return BOT_WEAPON_COUNT;
}

const char *hcu_bot_weapon_name(uint32_t weapon)
{
	return weapon < BOT_WEAPON_COUNT ? bot_weapons[weapon].name : NULL;
}

void hcu_bot_rng_seed(hcu_bot_rng *rng, uint32_t seed, uint32_t stream)
{
	uint32_t s = bot_mix32(seed ^ bot_mix32(stream * 0x9e3779b9U + 0x6a09e667U));
	rng->state = s ? s : 0x1234567u; /* xorshift must never hold zero */
}

uint32_t hcu_bot_rng_next(hcu_bot_rng *rng)
{
	uint32_t x = rng->state;
	x ^= x << 13;
	x ^= x >> 17;
	x ^= x << 5;
	rng->state = x;
	return x;
}

/* Uniform in [-1, 1): a draw for aim error. */
static float bot_rng_signed(hcu_bot_rng *rng)
{
	uint32_t v = hcu_bot_rng_next(rng) >> 8; /* 24 bits */
	return ((float)v / 8388608.0f) - 1.0f;
}

int hcu_bot_init(hcu_bot_state *state, const hcu_bot_config *config)
{
	uint32_t i;
	memset(state, 0, sizeof *state);
	if (config->count > HCU_BOT_MAX || config->skill >= HCU_BOT_SKILL_COUNT) {
		return -1;
	}
	state->seed = config->seed;
	state->count = config->count;
	state->skill = config->skill;
	state->team_mode = config->team_mode ? 1u : 0u;
	state->bot_team = config->bot_team;
	for (i = 0; i < state->count; i++) {
		hcu_bot_slot *slot = &state->slots[i];
		slot->alive = 1;
		slot->team = state->team_mode ? config->bot_team : (uint8_t)HCU_BOT_TEAM_NONE;
		slot->skill = config->skill;
		slot->name = (uint8_t)hcu_bot_name_index(config->seed, i);
		slot->weapon = HCU_BOT_WEAPON_NONE;
		slot->target = 0xffu;
		hcu_bot_rng_seed(&slot->rng, config->seed, i);
	}
	state->valid = 1;
	return 0;
}

void hcu_bot_note_death(hcu_bot_state *state, uint32_t bot, uint32_t killer_player_index)
{
	hcu_bot_slot *slot;
	if (bot >= state->count) {
		return;
	}
	slot = &state->slots[bot];
	slot->alive = 0;
	slot->deaths++;
	slot->trigger_down = 0;
	slot->fire_timer = 0;
	slot->target = 0xffu;
	if (killer_player_index >= HCU_BOT_PLAYER_SLOT_BASE) {
		uint32_t killer = killer_player_index - HCU_BOT_PLAYER_SLOT_BASE;
		if (killer < state->count && killer != bot) {
			state->slots[killer].kills++;
		}
	}
}

void hcu_bot_note_spawn(hcu_bot_state *state, uint32_t bot, const float pos[3])
{
	hcu_bot_slot *slot;
	if (bot >= state->count) {
		return;
	}
	slot = &state->slots[bot];
	slot->alive = 1;
	slot->spawns++;
	slot->pos[0] = pos[0];
	slot->pos[1] = pos[1];
	slot->pos[2] = pos[2];
	slot->last_pos[0] = pos[0];
	slot->last_pos[1] = pos[1];
	slot->last_pos[2] = pos[2];
	slot->stuck_timer = 0;
	slot->unstick_timer = 0;
	slot->target = 0xffu;
	slot->fire_timer = 0;
	slot->weapon = HCU_BOT_WEAPON_NONE;
}

/* ---------- decisions */

static int bot_is_enemy(const hcu_bot_state *state, const hcu_bot_world *world, uint32_t self_player, uint32_t other)
{
	const hcu_bot_percept *p;
	if (other == self_player || other >= HCU_BOT_PLAYER_SLOTS) {
		return 0;
	}
	p = &world->players[other];
	if (!p->alive) {
		return 0;
	}
	if (state->team_mode) {
		return p->team != world->players[self_player].team;
	}
	return 1;
}

/* The nearest enemy the bot can see, else the nearest enemy at all. Returns the CE player index or -1. */
static int bot_choose_target(const hcu_bot_state *state, const hcu_bot_world *world, uint32_t self_player,
	int *visible)
{
	float eye_self[3];
	int best_visible = -1;
	int best_any = -1;
	float best_visible_d = 0.f;
	float best_any_d = 0.f;
	uint32_t j;

	bot_eye(world->players[self_player].pos, eye_self);
	for (j = 0; j < HCU_BOT_PLAYER_SLOTS; j++) {
		float eye_other[3];
		float d;
		if (!bot_is_enemy(state, world, self_player, j)) {
			continue;
		}
		d = bot_dist2(world->players[self_player].pos, world->players[j].pos);
		if (best_any < 0 || d < best_any_d) {
			best_any = (int)j;
			best_any_d = d;
		}
		bot_eye(world->players[j].pos, eye_other);
		if (world->line_clear(world->ctx, eye_self, eye_other) &&
			(best_visible < 0 || d < best_visible_d)) {
			best_visible = (int)j;
			best_visible_d = d;
		}
	}
	if (best_visible >= 0) {
		*visible = 1;
		return best_visible;
	}
	*visible = 0;
	return best_any;
}

/* The pickup a bot goes for: the nearest valid weapon within reach that it wants more than what it holds (or
 * any weapon while its own is empty). Returns the pickup index or -1. */
static int bot_choose_pickup(const hcu_bot_world *world, const hcu_bot_percept *self)
{
	int best = -1;
	float best_d = 0.f;
	uint32_t k;
	for (k = 0; k < HCU_BOT_PICKUP_MAX; k++) {
		const hcu_bot_pickup *pickup = &world->pickups[k];
		float d;
		short held_score = -1;
		if (!pickup->valid || pickup->weapon >= BOT_WEAPON_COUNT) {
			continue;
		}
		if (self->weapon < BOT_WEAPON_COUNT) {
			held_score = bot_weapons[self->weapon].score;
		}
		if (!self->weapon_empty && held_score >= bot_weapons[pickup->weapon].score) {
			continue;
		}
		d = bot_dist2(self->pos, pickup->pos);
		if (d > BOT_WEAPON_SEARCH_RANGE2) {
			continue;
		}
		if (best < 0 || d < best_d) {
			best = (int)k;
			best_d = d;
		}
	}
	return best;
}

/* Steering: CE's waypoint toward goal when it has one, else the goal itself. */
static void bot_steer(const hcu_bot_world *world, uint32_t bot, const float from[3], const float goal[3],
	float stick[2])
{
	float next[3];
	if (world->path_step && world->path_step(world->ctx, bot, from, goal, next)) {
		bot_stick_toward(from, next, stick);
	} else {
		bot_stick_toward(from, goal, stick);
	}
}

static void bot_think_one(hcu_bot_state *state, const hcu_bot_world *world, uint32_t i, hcu_bot_action *out)
{
	hcu_bot_slot *slot = &state->slots[i];
	uint32_t self_player = HCU_BOT_PLAYER_SLOT_BASE + i;
	const hcu_bot_percept *self = &world->players[self_player];
	const hcu_bot_weapon_def *weapon;
	float eye_self[3];
	int has_target = 0;
	int engage = 0;
	int visible = 0;
	float d2 = 0.f;
	float goal[3];
	int have_goal = 0;
	int pickup_index;

	bot_action_idle(out);
	slot->alive = self->alive ? 1u : 0u;
	slot->team = self->team;
	if (!self->alive) {
		slot->trigger_down = 0;
		slot->fire_timer = 0;
		return;
	}
	memcpy(slot->last_pos, slot->pos, sizeof slot->pos);
	memcpy(slot->pos, self->pos, sizeof slot->pos);
	if (self->weapon < BOT_WEAPON_COUNT) {
		slot->weapon = self->weapon;
	}
	weapon = &bot_weapons[slot->weapon < BOT_WEAPON_COUNT ? slot->weapon : 0];
	bot_eye(slot->pos, eye_self);

	/* Timers count down one per tick (game ticks, not wall time). */
	slot->choose_timer -= 1;
	slot->strafe_timer -= 1;
	slot->melee_timer -= 1;
	slot->grenade_timer -= 1;
	slot->swap_timer -= 1;
	slot->reload_timer -= 1;
	slot->unstick_timer -= 1;

	/* Target: re-chosen on its timer, when it dies or leaves the enemy set. */
	if (slot->choose_timer <= 0 || slot->target == 0xffu || slot->target >= HCU_BOT_PLAYER_SLOTS ||
		!bot_is_enemy(state, world, self_player, slot->target)) {
		int chosen = bot_choose_target(state, world, self_player, &visible);
		slot->choose_timer = BOT_TARGET_TICKS;
		slot->target = chosen >= 0 ? (uint8_t)chosen : 0xffu;
		if (slot->target != 0xffu) {
			slot->target_visible = (uint8_t)visible;
		}
	}
	if (slot->target != 0xffu && bot_is_enemy(state, world, self_player, slot->target)) {
		float eye_target[3];
		has_target = 1;
		bot_eye(world->players[slot->target].pos, eye_target);
		/* Perception each tick: a sight line through CE collision, objects included. */
		visible = world->line_clear(world->ctx, eye_self, eye_target) ? 1 : 0;
		slot->target_visible = (uint8_t)visible;
		if (visible) {
			memcpy(slot->last_seen, world->players[slot->target].pos, sizeof slot->last_seen);
		}
		d2 = bot_dist2(slot->pos, world->players[slot->target].pos);
		engage = visible && d2 <= weapon->far_range * weapon->far_range &&
			!(weapon->style == HCU_BOT_FIRE_EXPLOSIVE && d2 < weapon->near_range * weapon->near_range);
	} else {
		slot->target = 0xffu;
		slot->target_visible = 0;
	}

	/* Firing: a burst at a visible target in range, then a pause; the aim error is drawn per burst. */
	if (engage) {
		if (slot->fire_timer == 0) {
			int k;
			slot->fire_timer = bot_burst_ticks[slot->skill];
			slot->burst_started = 1;
			for (k = 0; k < 3; k++) {
				slot->aim_error[k] = bot_rng_signed(&slot->rng) * bot_aim_error[slot->skill];
			}
		} else if (slot->fire_timer < 0) {
			slot->fire_timer++;
		}
		if (slot->fire_timer > 0) {
			slot->fire_timer--;
			if (slot->fire_timer == 0) {
				slot->fire_timer = (int16_t)-bot_pause_ticks[slot->skill];
			}
		}
		if (slot->fire_timer > 0) {
			/* Automatic weapons are held; the others are pressed on alternate ticks of the burst. */
			slot->trigger_down = weapon->style == HCU_BOT_FIRE_AUTO ? 1u : (uint8_t)((slot->fire_timer & 1) == 0);
		} else {
			slot->trigger_down = 0;
		}
		out->trigger = slot->trigger_down;
	} else {
		slot->fire_timer = 0;
		slot->trigger_down = 0;
	}

	/* Grenades (chance per tick, at a visible target out of melee), melee up close. */
	if (engage && slot->grenade_timer <= 0 && hcu_bot_rng_next(&slot->rng) % 1000u < bot_grenade_chance[slot->skill]) {
		out->grenade = 1;
		slot->grenade_timer = BOT_GRENADE_TICKS;
	}
	if (has_target && visible && d2 < BOT_MELEE_RANGE2 && slot->melee_timer <= 0) {
		out->melee = 1;
		slot->melee_timer = BOT_MELEE_TICKS;
	}

	/* Aim: from the eye to the target's eye, with the burst's error (zero aim keeps the facing). */
	if (has_target) {
		float eye_target[3];
		bot_eye(world->players[slot->target].pos, eye_target);
		out->aim[0] = eye_target[0] - eye_self[0] + slot->aim_error[0];
		out->aim[1] = eye_target[1] - eye_self[1] + slot->aim_error[1];
		out->aim[2] = eye_target[2] - eye_self[2] + slot->aim_error[2];
	}

	/* Movement goal, in this order: a visible target (kept at its range), its last seen position, a better
	 * weapon within reach, the mode's objective. */
	if (has_target && visible) {
		float dd = d2;
		float near2 = weapon->near_range * weapon->near_range;
		float far2 = weapon->far_range * weapon->far_range;
		memcpy(goal, world->players[slot->target].pos, sizeof goal);
		have_goal = 1;
		if (dd > far2) {
			bot_steer(world, i, slot->pos, goal, out->stick);
		} else if (dd < near2) {
			/* Too close for its weapon: back off, straight away from the target. */
			bot_stick_toward(goal, slot->pos, out->stick);
		} else {
			/* In range: strafe, its direction flipping on a timer. */
			float along[2];
			if (slot->strafe_timer <= 0) {
				slot->strafe_direction = (uint8_t)(hcu_bot_rng_next(&slot->rng) & 1u);
				slot->strafe_timer = BOT_STRAFE_TICKS;
			}
			bot_stick_toward(slot->pos, goal, along);
			out->stick[0] = -along[1];
			out->stick[1] = along[0];
			if (slot->strafe_direction) {
				out->stick[0] = -out->stick[0];
				out->stick[1] = -out->stick[1];
			}
		}
	} else if (has_target) {
		memcpy(goal, slot->last_seen, sizeof goal);
		have_goal = 1;
		bot_steer(world, i, slot->pos, goal, out->stick);
	}

	pickup_index = (!has_target || !visible) ? bot_choose_pickup(world, self) : -1;
	if (pickup_index >= 0) {
		const hcu_bot_pickup *pickup = &world->pickups[pickup_index];
		float reach = bot_dist2(slot->pos, pickup->pos);
		memcpy(goal, pickup->pos, sizeof goal);
		have_goal = 1;
		if (reach < BOT_PICKUP_REACH2) {
			out->action = 1;
			out->stick[0] = 0.f;
			out->stick[1] = 0.f;
		} else {
			bot_steer(world, i, slot->pos, goal, out->stick);
		}
	} else if (!has_target && world->objective && world->objective(world->ctx, i, goal)) {
		have_goal = 1;
		bot_steer(world, i, slot->pos, goal, out->stick);
	}

	/* Unsticking: a bot with a goal that has not moved for a window jumps and strafes for a while. */
	if (have_goal) {
		slot->stuck_timer++;
		if (slot->stuck_timer >= BOT_STUCK_TICKS) {
			if (bot_dist2(slot->pos, slot->last_pos) < BOT_STUCK_DISTANCE2 && slot->unstick_timer <= 0) {
				slot->unstick_timer = BOT_UNSTICK_TICKS;
				slot->strafe_direction = (uint8_t)(hcu_bot_rng_next(&slot->rng) & 1u);
			}
			memcpy(slot->last_pos, slot->pos, sizeof slot->last_pos);
			slot->stuck_timer = 0;
		}
		if (slot->unstick_timer > 0) {
			/* Jump and go sideways (the stick rotated a quarter turn, either way). */
			float along0 = out->stick[0];
			float along1 = out->stick[1];
			out->jump = 1;
			if (slot->strafe_direction) {
				out->stick[0] = -along1;
				out->stick[1] = along0;
			} else {
				out->stick[0] = along1;
				out->stick[1] = -along0;
			}
		}
	} else {
		slot->stuck_timer = 0;
	}

	/* Weapons: an empty weapon is swapped for the other, or reloaded when there is none. */
	if (self->weapon_empty) {
		if (self->other_weapon < BOT_WEAPON_COUNT && slot->swap_timer <= 0) {
			out->swap = 1;
			slot->swap_timer = BOT_SWAP_TICKS;
		} else if (slot->reload_timer <= 0) {
			out->reload = 1;
			slot->reload_timer = BOT_RELOAD_TICKS;
		}
	}

	/* Stick components never leave [-1, 1] (the strafe and unstick rotations can exceed it). */
	if (out->stick[0] > 1.f) out->stick[0] = 1.f;
	if (out->stick[0] < -1.f) out->stick[0] = -1.f;
	if (out->stick[1] > 1.f) out->stick[1] = 1.f;
	if (out->stick[1] < -1.f) out->stick[1] = -1.f;
}

void hcu_bot_think(hcu_bot_state *state, const hcu_bot_world *world, hcu_bot_action out[HCU_BOT_MAX])
{
	uint32_t i;
	state->tick++;
	/* Only the roster's entries are written (out[i] for i < count); the rest of out is left alone. */
	for (i = 0; i < state->count; i++) {
		bot_action_idle(&out[i]);
	}
	if (!state->valid) {
		return;
	}
	for (i = 0; i < state->count; i++) {
		bot_think_one(state, world, i, &out[i]);
	}
}

uint64_t hcu_bot_hash(const hcu_bot_state *state)
{
	uint64_t h = BOT_FNV_OFFSET;
	uint32_t i;
	uint32_t k;
	h = bot_hash_u32(h, state->seed);
	h = bot_hash_u32(h, state->tick);
	h = bot_hash_byte(h, state->count);
	h = bot_hash_byte(h, state->skill);
	h = bot_hash_byte(h, state->team_mode);
	h = bot_hash_byte(h, state->bot_team);
	h = bot_hash_byte(h, state->valid);
	for (i = 0; i < HCU_BOT_MAX; i++) {
		const hcu_bot_slot *s = &state->slots[i];
		h = bot_hash_byte(h, s->alive);
		h = bot_hash_byte(h, s->team);
		h = bot_hash_byte(h, s->skill);
		h = bot_hash_byte(h, s->name);
		h = bot_hash_byte(h, s->weapon);
		h = bot_hash_byte(h, s->target);
		h = bot_hash_byte(h, s->target_visible);
		h = bot_hash_byte(h, s->trigger_down);
		h = bot_hash_byte(h, s->strafe_direction);
		h = bot_hash_byte(h, s->burst_started);
		h = bot_hash_u32(h, (uint32_t)(int32_t)s->fire_timer);
		h = bot_hash_u32(h, (uint32_t)(int32_t)s->choose_timer);
		h = bot_hash_u32(h, (uint32_t)(int32_t)s->strafe_timer);
		h = bot_hash_u32(h, (uint32_t)(int32_t)s->stuck_timer);
		h = bot_hash_u32(h, (uint32_t)(int32_t)s->unstick_timer);
		h = bot_hash_u32(h, (uint32_t)(int32_t)s->melee_timer);
		h = bot_hash_u32(h, (uint32_t)(int32_t)s->grenade_timer);
		h = bot_hash_u32(h, (uint32_t)(int32_t)s->swap_timer);
		h = bot_hash_u32(h, (uint32_t)(int32_t)s->reload_timer);
		h = bot_hash_u32(h, (uint32_t)(int32_t)s->sight_timer);
		for (k = 0; k < 3; k++) {
			h = bot_hash_float(h, s->pos[k]);
		}
		for (k = 0; k < 3; k++) {
			h = bot_hash_float(h, s->last_pos[k]);
		}
		for (k = 0; k < 3; k++) {
			h = bot_hash_float(h, s->last_seen[k]);
		}
		for (k = 0; k < 3; k++) {
			h = bot_hash_float(h, s->aim_error[k]);
		}
		h = bot_hash_u32(h, s->rng.state);
		h = bot_hash_u32(h, s->kills);
		h = bot_hash_u32(h, s->deaths);
		h = bot_hash_u32(h, s->spawns);
	}
	return h;
}
