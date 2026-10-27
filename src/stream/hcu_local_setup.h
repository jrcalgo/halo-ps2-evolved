/* Local setup descriptor for the HCU C5 bot and cooperative profiles.
 *
 * The descriptor carries what the local setup screen chooses: game mode,
 * team variant, human roster (the four local controller/view slots), Spartan
 * bot count (kept separate from the human slots), difficulty, the fixed
 * qualification seed and the qualified population row it runs under.
 *
 * Validation is pure. hcu_local_setup_validate() reads its inputs and writes
 * only to the caller's result object, and only on acceptance. The integrator
 * calls hcu_local_setup_admit() before any map teardown: it validates first
 * and invokes the teardown callback only when the profile is accepted, so a
 * rejected profile leaves the loaded map exactly as it was.
 */
#ifndef HCU_LOCAL_SETUP_H
#define HCU_LOCAL_SETUP_H

#include <stddef.h>
#include <stdint.h>

#include "hcu_c5_limits.h"

#define HCU_LOCAL_MAP_NAME_BYTES 32u
/* Slot counts come from hcu_c5_limits.h. Bots are 12 seats (16 - 4 humans), not the four local slots. */
#define HCU_LOCAL_HUMAN_SLOTS HCU_C5_LOCAL_HUMAN_SLOTS /* local controller/view slots */
#define HCU_LOCAL_BOT_SLOTS HCU_C5_BOT_SEATS_MAX       /* Spartan bot seats, separate from human slots */

typedef enum hcu_local_mode {
	HCU_LOCAL_MODE_NONE = 0,
	HCU_LOCAL_MODE_STOCK_COOP,   /* stock cooperative team modes (variant applies) */
	HCU_LOCAL_MODE_SURVIVAL      /* wave survival (no variant) */
} hcu_local_mode;

typedef enum hcu_local_variant {
	HCU_LOCAL_VARIANT_NONE = 0,
	HCU_LOCAL_VARIANT_SLAYER,
	HCU_LOCAL_VARIANT_CTF,
	HCU_LOCAL_VARIANT_ODDBALL,
	HCU_LOCAL_VARIANT_KING,
	HCU_LOCAL_VARIANT_RACE
} hcu_local_variant;

/* Halo CE difficulty names. NONE is never valid. */
typedef enum hcu_local_difficulty {
	HCU_LOCAL_DIFFICULTY_NONE = 0,
	HCU_LOCAL_DIFFICULTY_EASY,
	HCU_LOCAL_DIFFICULTY_NORMAL,
	HCU_LOCAL_DIFFICULTY_HEROIC,
	HCU_LOCAL_DIFFICULTY_LEGENDARY
} hcu_local_difficulty;

/* Team switch (CE universal_variant.teams). Cooperative modes need ON, survival needs OFF, and CTF is always ON. */
typedef enum hcu_local_teams {
	HCU_LOCAL_TEAMS_OFF = 0,
	HCU_LOCAL_TEAMS_ON
} hcu_local_teams;

/* Reason codes. HCU_LOCAL_SETUP_OK is the only accepting value. */
typedef enum hcu_local_setup_reason {
	HCU_LOCAL_SETUP_OK = 0,
	HCU_LOCAL_SETUP_BAD_ARGUMENT,
	HCU_LOCAL_SETUP_UNKNOWN_MODE,
	HCU_LOCAL_SETUP_UNKNOWN_VARIANT,
	HCU_LOCAL_SETUP_UNKNOWN_DIFFICULTY,
	HCU_LOCAL_SETUP_VARIANT_NOT_APPLICABLE, /* survival with a team variant, or coop without one */
	HCU_LOCAL_SETUP_BAD_MAP_NAME,
	HCU_LOCAL_SETUP_NO_HUMANS,              /* human mask empty */
	HCU_LOCAL_SETUP_BAD_HUMAN_MASK,         /* bits above the four local slots */
	HCU_LOCAL_SETUP_TOO_MANY_BOTS,
	HCU_LOCAL_SETUP_MAP_NOT_QUALIFIED,      /* no qualification row for map and mode */
	HCU_LOCAL_SETUP_DIFFICULTY_NOT_QUALIFIED,
	HCU_LOCAL_SETUP_POPULATION_ABOVE_QUALIFIED,
	HCU_LOCAL_SETUP_TEARDOWN_FAILED,        /* accepted, but the teardown callback failed */
	HCU_LOCAL_SETUP_TEAM_MISMATCH           /* team switch disagrees with mode or variant */
} hcu_local_setup_reason;

/* Requested profile. Bot slots are never part of human_mask. */
typedef struct hcu_local_setup {
	hcu_local_mode mode;
	hcu_local_variant variant;
	hcu_local_teams teams;       /* team switch: ON splits local humans (team 0) from bots (team 1) */
	hcu_local_difficulty difficulty;
	uint32_t human_mask;   /* bit n = local controller/view slot n (0..3) */
	uint32_t bot_count;    /* Spartan bots, 0..HCU_LOCAL_BOT_SLOTS */
	uint32_t seed;         /* fixed qualification seed */
	char map_name[HCU_LOCAL_MAP_NAME_BYTES]; /* NUL-terminated map file name */
} hcu_local_setup;

/* One qualified population row. A map and mode with no row is refused. The
 * difficulty mask uses bit (1u << difficulty). */
typedef struct hcu_local_qualified_row {
	const char *map_name;
	hcu_local_mode mode;
	uint32_t difficulty_mask;
	uint32_t max_humans;
	uint32_t max_bots;
} hcu_local_qualified_row;

/* Accepted descriptor, filled only on success. qualified_population is the
 * matched row's humans + bots capacity (the highest admitted total). */
typedef struct hcu_local_setup_result {
	hcu_local_setup setup;
	uint32_t human_count;
	uint32_t bot_count;
	uint32_t qualified_population;
	/* Team index written to every human and bot when teams is ON (hcu_c5_limits.h). Both are HCU_C5_TEAM_NONE
	 * when teams is OFF; the adapter must then give each player its own team index. */
	uint8_t human_team;
	uint8_t bot_team;
} hcu_local_setup_result;

/* Pure validator. Writes `out` only when it returns HCU_LOCAL_SETUP_OK.
 * Performs no allocation and touches no global state. */
hcu_local_setup_reason hcu_local_setup_validate(const hcu_local_setup *request,
	const hcu_local_qualified_row *rows, size_t row_count,
	hcu_local_setup_result *out);

/* Teardown callback invoked by hcu_local_setup_admit() only after acceptance.
 * Returns 0 on success; nonzero makes admit return HCU_LOCAL_SETUP_TEARDOWN_FAILED
 * with `out` still filled (the teardown owns any partial state it left). */
typedef int (*hcu_local_teardown_fn)(void *user, const hcu_local_setup_result *accepted);

/* Entry point for the integrator. Validates first. On rejection it returns the
 * reason and performs no teardown and no write to `out`. On acceptance it
 * calls teardown (if non-NULL) and returns its status with `out` filled. */
hcu_local_setup_reason hcu_local_setup_admit(const hcu_local_setup *request,
	const hcu_local_qualified_row *rows, size_t row_count,
	hcu_local_teardown_fn teardown, void *user, hcu_local_setup_result *out);

/* Stable diagnostic name for a reason code. */
const char *hcu_local_setup_reason_name(hcu_local_setup_reason reason);

#endif /* HCU_LOCAL_SETUP_H */
