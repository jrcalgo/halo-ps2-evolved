/* C5.1-2: deterministic Spartan bots as player-backed participants.
 *
 * A bot is a CE player (player_new, then players_update_before_game applies its actions exactly as a
 * controller's are applied). Bots occupy CE player indices HCU_BOT_PLAYER_SLOT_BASE onward, after the four
 * local controller/view slots, so a bot never shares a view, a controller or a local input record.
 *
 * This header and hcu_bot.c are host-testable: they touch no CE, renderer or EE header. The CE adapter
 * fills a hcu_bot_world each tick (player percepts from CE unit state, collision rays through CE's
 * collision and pathfinding paths, pickups, and the mode's objective) and reads the hcu_bot_action of
 * each live bot back into CE's action records. The bot state, its per-bot seeded RNG streams and its
 * counters are hashed by hcu_bot_hash, which the simulation and replay hashes include.
 *
 * Determinism: all state is fixed storage (no heap), every random draw comes from the bot's own stream
 * (hcu_bot_rng_next), and no wall-clock, address or host-dependent value enters a decision. Float state
 * is computed by the same code on every machine of the same build; the hash folds float bit patterns.
 *
 * Scope: this file has no N64 capacity, throttle or cut. HCU_BOT_MAX is the storage bound of the roster
 * (a count above it is refused by hcu_bot_init, never truncated). */
#ifndef HALO_STREAM_HCU_BOT_H
#define HALO_STREAM_HCU_BOT_H

#include <stddef.h>
#include <stdint.h>

#include "hcu_c5_limits.h"

#ifdef __cplusplus
extern "C" {
#endif

/* Local controller/view slots (CE player indices 0..3). Bots start after them. */
#define HCU_BOT_LOCAL_SLOTS HCU_C5_LOCAL_HUMAN_SLOTS
#define HCU_BOT_PLAYER_SLOT_BASE HCU_BOT_LOCAL_SLOTS
/* Fixed storage bound of the roster (bot i is CE player HCU_BOT_PLAYER_SLOT_BASE + i). Seats = 16 - 4 humans
 * (hcu_c5_limits.h); bots take machines 1-3. */
#define HCU_BOT_MAX HCU_C5_BOT_SEATS_MAX
#define HCU_BOT_PLAYER_SLOTS (HCU_BOT_LOCAL_SLOTS + HCU_BOT_MAX)
#define HCU_BOT_NAME_COUNT 40u
#define HCU_BOT_PICKUP_MAX 16u
#define HCU_BOT_TEAM_NONE 0xffu /* free-for-all: every other player is an enemy */

/* Skill levels (Halo's easy, normal, heroic, legendary). */
enum {
	HCU_BOT_SKILL_EASY = 0,
	HCU_BOT_SKILL_NORMAL = 1,
	HCU_BOT_SKILL_HEROIC = 2,
	HCU_BOT_SKILL_LEGENDARY = 3,
	HCU_BOT_SKILL_COUNT = 4
};

/* Weapon handling: how a weapon is fired. */
enum {
	HCU_BOT_FIRE_SEMI = 0,      /* pressed shot by shot */
	HCU_BOT_FIRE_AUTO = 1,      /* held */
	HCU_BOT_FIRE_EXPLOSIVE = 2  /* pressed, never up close */
};

/* Deterministic per-bot RNG stream (xorshift32; never zero). */
typedef struct hcu_bot_rng {
	uint32_t state;
} hcu_bot_rng;

typedef struct hcu_bot_config {
	uint32_t seed;          /* lobby/qualification seed; the roster and every stream derive from it */
	uint8_t count;          /* 0..HCU_BOT_MAX */
	uint8_t skill;          /* HCU_BOT_SKILL_* */
	uint8_t team_mode;      /* 1: bots share bot_team and fight every other team; 0: free-for-all */
	uint8_t bot_team;       /* team of every bot in team_mode (ignored otherwise) */
} hcu_bot_config;

/* What CE reports about one player slot each tick. */
typedef struct hcu_bot_percept {
	uint8_t alive;
	uint8_t team;          /* HCU_BOT_TEAM_NONE in free-for-all */
	uint8_t has_weapon;
	uint8_t weapon_empty;  /* current weapon has no ammunition left (own slot only) */
	uint8_t weapon;        /* hcu_bot_weapon index of the current weapon (own slot), or 0xff */
	uint8_t other_weapon;  /* hcu_bot_weapon index of the other held weapon (own slot), or 0xff */
	float pos[3];
} hcu_bot_percept;

typedef struct hcu_bot_pickup {
	uint8_t valid;
	uint8_t weapon;        /* hcu_bot_weapon index */
	float pos[3];
} hcu_bot_pickup;

typedef struct hcu_bot_world {
	hcu_bot_percept players[HCU_BOT_PLAYER_SLOTS]; /* CE player slots, bots at HCU_BOT_PLAYER_SLOT_BASE+i */
	hcu_bot_pickup pickups[HCU_BOT_PICKUP_MAX];
	/* Line of sight through CE collision, objects included: returns 1 when the segment is clear. */
	int (*line_clear)(void *ctx, const float from[3], const float to[3]);
	/* Next waypoint from CE pathfinding toward goal: returns 1 and writes next, or 0 when no path. */
	int (*path_step)(void *ctx, uint32_t bot, const float from[3], const float goal[3], float next[3]);
	/* Mode objective hook (oddball, CTF, king, race): returns 1 and writes goal when the bot should go there. */
	int (*objective)(void *ctx, uint32_t bot, float goal[3]);
	void *ctx;
} hcu_bot_world;

/* One tick's controller-equivalent output for a bot (CE's player action record). */
typedef struct hcu_bot_action {
	float stick[2];        /* world-plane movement, each component in [-1, 1] */
	float aim[3];          /* aim direction (not normalised) from the bot's eye */
	uint8_t trigger;       /* primary trigger */
	uint8_t grenade;
	uint8_t melee;
	uint8_t jump;
	uint8_t reload;
	uint8_t action;        /* action button: picks up a weapon in reach */
	int8_t swap;           /* +1 swap to the other weapon */
} hcu_bot_action;

typedef struct hcu_bot_slot {
	uint8_t alive;
	uint8_t team;
	uint8_t skill;
	uint8_t name;          /* index into the name pool */
	uint8_t weapon;        /* hcu_bot_weapon index of the weapon it is firing */
	uint8_t target;        /* bot-relative CE player index of its target, or 0xff */
	uint8_t target_visible;
	uint8_t trigger_down;
	uint8_t strafe_direction;
	uint8_t burst_started;
	int16_t fire_timer;    /* > 0 firing ticks left, < 0 paused ticks left */
	int16_t choose_timer;
	int16_t strafe_timer;
	int16_t stuck_timer;
	int16_t unstick_timer;
	int16_t melee_timer;
	int16_t grenade_timer;
	int16_t swap_timer;
	int16_t reload_timer;
	int16_t sight_timer;
	float pos[3];
	float last_pos[3];
	float last_seen[3];
	float aim_error[3];    /* this burst's aim error, drawn from the bot's stream */
	hcu_bot_rng rng;
	uint32_t kills;
	uint32_t deaths;
	uint32_t spawns;
} hcu_bot_slot;

typedef struct hcu_bot_state {
	uint32_t seed;
	uint32_t tick;
	uint8_t count;
	uint8_t skill;
	uint8_t team_mode;
	uint8_t bot_team;
	uint8_t valid;
	hcu_bot_slot slots[HCU_BOT_MAX];
} hcu_bot_state;

/* Name index for bot i of a roster seeded by seed: distinct for every bot of up to 40. */
uint32_t hcu_bot_name_index(uint32_t seed, uint32_t bot);

/* Weapon table size and per-weapon name (CE tag path, for the adapter's lookup). */
uint32_t hcu_bot_weapon_count(void);
const char *hcu_bot_weapon_name(uint32_t weapon);

/* Deterministic RNG stream helpers (stream id distinguishes bots). */
void hcu_bot_rng_seed(hcu_bot_rng *rng, uint32_t seed, uint32_t stream);
uint32_t hcu_bot_rng_next(hcu_bot_rng *rng);

/* Validate and build the roster. Returns 0 on success, -1 for a count above HCU_BOT_MAX or a skill out of range
 * (the state is left invalid and nothing is started). */
int hcu_bot_init(hcu_bot_state *state, const hcu_bot_config *config);

/* Lifecycle, driven by CE's death and respawn paths. A respawn restores the bot's alive flag and position and
 * keeps its stream, counters and name (a respawn is not a new roster member). */
void hcu_bot_note_death(hcu_bot_state *state, uint32_t bot, uint32_t killer_player_index);
void hcu_bot_note_spawn(hcu_bot_state *state, uint32_t bot, const float pos[3]);

/* Advance every bot one tick from the world percepts; writes out[i] for i < count. Dead bots get an idle action. */
void hcu_bot_think(hcu_bot_state *state, const hcu_bot_world *world, hcu_bot_action out[HCU_BOT_MAX]);

/* FNV-1a 64 over the roster, the tick, every stream, every counter and every float bit pattern, in a fixed
 * field order (no struct padding is hashed). Simulation and replay hashes fold this value in. */
uint64_t hcu_bot_hash(const hcu_bot_state *state);

#ifdef __cplusplus
}
#endif

#endif
