/* CE-side pure helpers for the survival driver (M2 C5 steps 6-7).
 *
 * The PS2 adapter (submodules/halo-ce-universal/port/ps2/src/ps2_survival.c) calls CE for placement, deaths and
 * spawning. Everything it decides without touching CE lives here, so the host tests can check it:
 *   - the recipe table (C1 roster variants, docs/reports/m2-c1-actor-roster-2026-10-23.json) and the recipe per slot,
 *   - the secondary spawn worst case read from a unit's tag bounds (survival open item 1),
 *   - the actor-pool admission check against the live CE actor count,
 *   - the per-slot actor table (fixed storage, reused across waves),
 *   - the human respawn gate and the death delta.
 * No CE header is included here. Sources: docs/reports/m4-c5-research-survival-2026-10-26.md, sections 2, 6 and 7.
 */
#ifndef HCU_SURVIVAL_CE_H
#define HCU_SURVIVAL_CE_H

#include <stdint.h>

#include "hcu_c5_limits.h"
#include "hcu_survival.h"

#define HCU_SURVIVAL_CE_RECIPE_COUNT 4u
#define HCU_SURVIVAL_CE_NO_ACTOR (-1)
/* Slot value meaning "no slot" from hcu_survival_ce_slot_of_actor. */
#define HCU_SURVIVAL_CE_NO_SLOT HCU_SURVIVAL_ACTIVE_LIMIT_MAX
/* Human index value meaning "no living human". */
#define HCU_SURVIVAL_CE_NO_HUMAN HCU_SURVIVAL_HUMANS_MAX

/* One enemy kind: the actor variant (actv) placed, and the unit (bipd) whose tag bounds the secondary spawn. Paths are
 * the C1 roster's (backslash separated, as the tag group paths are written). */
typedef struct hcu_survival_ce_recipe {
  const char *variant_path;
  const char *unit_path;
} hcu_survival_ce_recipe;

/* Fixed actor table: one CE actor index per enemy slot, or HCU_SURVIVAL_CE_NO_ACTOR. */
typedef struct hcu_survival_ce_slots {
  int32_t actor[HCU_SURVIVAL_ACTIVE_LIMIT_MAX];
} hcu_survival_ce_slots;

/* Recipe table. NULL past HCU_SURVIVAL_CE_RECIPE_COUNT. */
const hcu_survival_ce_recipe *hcu_survival_ce_recipe_at(unsigned int index);

/* Recipe index for a slot of a wave. Cycles over the table, so each wave mixes kinds. */
unsigned int hcu_survival_ce_recipe_for(unsigned int wave_number, unsigned int slot);

/* Worst secondary spawn count of a unit from its tag bounds. CE draws random_range(lower, upper + 1)
 * (units.c, unit_test_spawning), so the largest value is upper; a negative or inverted range gives 0 or lower. */
unsigned int hcu_survival_ce_secondary_worst(int lower, int upper);

/* 1 when the template's worst secondary count covers a recipe's tag bound. */
int hcu_survival_ce_secondary_fits(const hcu_survival_template *t, unsigned int recipe_worst_secondary);

/* 1 when one enemy's observed expansion (from CE data) stays within the template's worst case. */
int hcu_survival_ce_within_worst(const hcu_survival_template *t, unsigned int mounted, unsigned int swarm,
                                 unsigned int secondary);

/* 1 when a batch can be placed: live CE actors plus the batch's reserved units fit the PS2 pool less its margin. */
int hcu_survival_ce_may_place(unsigned int live_actors, unsigned int reserved_units);

/* Deaths since the last observation. Wrap-safe for the unsigned death counter. */
unsigned int hcu_survival_ce_deaths_delta(unsigned int seen, unsigned int now);

/* Respawn gate for one human: only after a wave admitted the human (hcu_alive), only while no death is unobserved
 * (deaths_now == deaths_seen), and only when the gate is open for that human (may_flag). */
int hcu_survival_ce_respawn_allowed(int hcu_alive, int may_flag, unsigned int deaths_now, unsigned int deaths_seen);

/* Reservation of the next admission (wave number + 1): the same count and worst unit hcu_survival's admit_wave uses.
 * Read before the tick that admits the wave, so the adapter can hold intermission when the pool has no room.
 * Host-tested against the real controller (tests/hcu_survival_ce_main.c). */
unsigned int hcu_survival_ce_next_reserve(const hcu_survival *s);

/* Raises each template's worst secondary count to the largest recipe bound (the controller's default table has 0 or
 * 2 secondary spawns; the tags can say more). Returns 0, with the table possibly raised, when a template's
 * active_limit x worst unit then exceeds HCU_SURVIVAL_RESERVE_MAX: the caller must refuse the profile. */
int hcu_survival_ce_raise_secondary(hcu_survival_template *tmpl, unsigned int count, unsigned int active_limit,
                                    unsigned int worst_secondary);

void hcu_survival_ce_slots_clear(hcu_survival_ce_slots *slots);
unsigned int hcu_survival_ce_slot_of_actor(const hcu_survival_ce_slots *slots, int32_t actor);

/* Human that stands in for a slot: the (slot mod living)-th living human, so new enemies spread over the living humans.
 * Returns HCU_SURVIVAL_CE_NO_HUMAN when nobody lives. */
unsigned int hcu_survival_ce_human_for_slot(const hcu_survival *s, unsigned int slot);

#endif /* HCU_SURVIVAL_CE_H */
