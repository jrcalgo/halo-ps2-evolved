/* Survival wave controller for the HCU fork (M2 C5 steps 6-7).
 *
 * Storage is fixed: enemy slots sized by the active limit, human slots, and
 * bounded rings or counters for corpses, drops, projectiles, effects and
 * deferred requests. Completed waves are not kept. The wave template table
 * cycles forever and each wave reuses the same enemy slot array.
 *
 * States:
 *   SETUP        before begin(); nothing is admitted yet.
 *   ACTIVE_WAVE  one batch is admitted. Deaths are marked during the tick and
 *                resolved at the end of it.
 *   INTERMISSION HCU_SURVIVAL_INTERMISSION_TICKS ticks (5 s at 30 Hz). Dead
 *                humans respawn when the next wave is admitted. Nobody
 *                respawns during an active wave.
 *   GAME_OVER    terminal. Zero living humans after a tick's deaths resolve
 *                ends the match, even if the last enemy also died that tick.
 *
 * Accounting: an admitted enemy occupies units = 1 + mounted occupants +
 * extra swarm members + secondary spawns. The active limit caps the number of
 * admitted enemies in a batch. Admission reserves the worst case for the whole
 * batch (batch * worst_unit of the template), and that reservation must fit the
 * PS2 actor reserve (HCU_SURVIVAL_RESERVE_MAX). The reserved worst case is
 * always >= the actual active units.
 *
 * Swarms: a template with any swarm member needs active_limit <= 12
 * (HCU_SURVIVAL_SWARM_ACTIVE_LIMIT_MAX). The worst swarm is 16 units, so
 * 12 x 16 = 192 actors fits the 256-actor PS2 pool with a 64-actor margin.
 * Sources: docs/reports/m4-c5-research-survival-2026-10-26.md, sections 2, 6
 * and 7; numbers in src/stream/hcu_c5_limits.h.
 *
 * Only CE Normal is qualified. Seed 0 selects the first qualification seed.
 * No floating point. Single-threaded, called from the tick lane only. */
#ifndef HCU_SURVIVAL_H
#define HCU_SURVIVAL_H

#include <stdint.h>

#include "hcu_c5_limits.h"

#define HCU_SURVIVAL_TICK_HZ 30u
#define HCU_SURVIVAL_INTERMISSION_TICKS (5u * HCU_SURVIVAL_TICK_HZ)
/* Enemy slot array size (the ceiling for any active limit, non-swarm only). */
#define HCU_SURVIVAL_ACTIVE_LIMIT_MAX 32u
/* Active limit while a swarm template is present (survival report, section 6). */
#define HCU_SURVIVAL_SWARM_ACTIVE_LIMIT_MAX HCU_C5_SWARM_ACTIVE_LIMIT_MAX
/* Worst units of one swarm, and the extra members beyond its base unit (16 - 1 = 15). */
#define HCU_SURVIVAL_SWARM_MEMBERS_MAX HCU_C5_SWARM_MEMBERS_MAX
#define HCU_SURVIVAL_SWARM_EXTRA_MAX (HCU_SURVIVAL_SWARM_MEMBERS_MAX - 1u)
/* Largest batch reservation in actors: 256-actor PS2 pool minus the 64-actor margin (192). */
#define HCU_SURVIVAL_RESERVE_MAX HCU_C5_ACTOR_RESERVE_MAX
/* Qualification seeds (survival report, section 5: fixed seeds per map, plan C6). Seed 0 means the first. */
#define HCU_SURVIVAL_QUAL_SEED_0 0x5EED0001u
#define HCU_SURVIVAL_QUAL_SEED_1 0x5EED0002u
#define HCU_SURVIVAL_QUAL_SEED_2 0x5EED0003u
#define HCU_SURVIVAL_HUMANS_MAX 4u
#define HCU_SURVIVAL_TEMPLATES_MAX 8u
#define HCU_SURVIVAL_QUAL_SEED_COUNT 3u
#define HCU_SURVIVAL_DEFAULT_TEMPLATE_COUNT 4u
#define HCU_SURVIVAL_CYCLE_CAP 1000u
#define HCU_SURVIVAL_BUDGET_CAP 64u

typedef enum {
  HCU_SURVIVAL_DIFFICULTY_NORMAL = 0, /* the only qualified difficulty */
  HCU_SURVIVAL_DIFFICULTY_EASY,
  HCU_SURVIVAL_DIFFICULTY_HEAVY,
  HCU_SURVIVAL_DIFFICULTY_LEGENDARY
} hcu_survival_difficulty;

typedef enum {
  HCU_SURVIVAL_STATE_SETUP = 0,
  HCU_SURVIVAL_STATE_ACTIVE_WAVE,
  HCU_SURVIVAL_STATE_INTERMISSION,
  HCU_SURVIVAL_STATE_GAME_OVER
} hcu_survival_state;

typedef enum {
  HCU_SURVIVAL_OK = 0,
  HCU_SURVIVAL_ERR_ARG,         /* null pointer, index or config value out of range */
  HCU_SURVIVAL_ERR_UNSUPPORTED, /* difficulty, seed or profile not qualified */
  HCU_SURVIVAL_ERR_LIMIT,       /* worst-case reservation cannot fit the active limit */
  HCU_SURVIVAL_ERR_STATE,       /* call not valid in the current state */
  HCU_SURVIVAL_ERR_BUDGET       /* bounded request refused at capacity */
} hcu_survival_status;

typedef enum {
  HCU_SURVIVAL_BUDGET_CORPSE = 0, /* ring: evicts oldest at capacity */
  HCU_SURVIVAL_BUDGET_DROP,       /* ring */
  HCU_SURVIVAL_BUDGET_EFFECT,     /* ring */
  HCU_SURVIVAL_BUDGET_PROJECTILE, /* counter: refuses at capacity */
  HCU_SURVIVAL_BUDGET_DEFERRED,   /* FIFO: refuses at capacity */
  HCU_SURVIVAL_BUDGET_KIND_COUNT
} hcu_survival_budget_kind;

typedef struct hcu_survival_template {
  unsigned int base_enemies;   /* batch size in wave 1 of the cycle, >= 1 */
  unsigned int growth_per_cycle;
  unsigned int max_mounted;    /* worst-case mounted occupants per enemy */
  unsigned int max_swarm;      /* worst-case extra swarm members per enemy, 0..HCU_SURVIVAL_SWARM_EXTRA_MAX */
  unsigned int max_secondary;  /* worst-case secondary spawns per enemy */
} hcu_survival_template;

typedef struct hcu_survival_config {
  hcu_survival_difficulty difficulty;
  unsigned int seed;                       /* 0 or a qualification seed */
  unsigned int humans;                     /* 1..HCU_SURVIVAL_HUMANS_MAX */
  unsigned int active_limit;               /* enemies per batch, 1..HCU_SURVIVAL_ACTIVE_LIMIT_MAX (<= 12 with swarms) */
  const hcu_survival_template *templates;  /* NULL selects the built-in table */
  unsigned int template_count;             /* 1..HCU_SURVIVAL_TEMPLATES_MAX */
} hcu_survival_config;

typedef struct hcu_survival_enemy {
  unsigned char alive;
  unsigned char pending_death;
  unsigned char mounted;
  unsigned char swarm;
  unsigned char secondary;
  unsigned char units; /* 1 + mounted + swarm + secondary */
} hcu_survival_enemy;

typedef struct hcu_survival_human {
  unsigned char alive;
  unsigned char pending_death;
} hcu_survival_human;

/* Bounded store. Ring kinds evict the oldest entry at capacity. Counter and
 * FIFO kinds refuse new work at capacity. None of them can reach live enemy
 * or human slots. */
typedef struct hcu_survival_budget {
  unsigned int capacity;
  unsigned int head;
  unsigned int count;
  unsigned int evicted;
  unsigned int refused;
  uint32_t items[HCU_SURVIVAL_BUDGET_CAP];
} hcu_survival_budget;

typedef struct hcu_survival {
  hcu_survival_difficulty difficulty;
  hcu_survival_state state;
  unsigned int seed_used;
  uint32_t rng;
  unsigned int humans_count;
  unsigned int active_limit;
  unsigned int template_count;
  hcu_survival_template tmpl[HCU_SURVIVAL_TEMPLATES_MAX];
  unsigned int wave_number;     /* 0 before begin; the active or last wave */
  unsigned int batch_size;      /* enemies admitted in the current wave */
  unsigned int reserved_units;  /* worst-case units reserved at admission */
  unsigned int active_units;    /* sum of units over live enemies */
  unsigned int mounted_active;
  unsigned int swarm_active;
  unsigned int secondary_active;
  unsigned int intermission_left;
  unsigned int waves_cleared;
  unsigned int enemies_admitted; /* base enemies admitted across all waves */
  unsigned int humans_respawned; /* respawns, applied only at wave admission */
  hcu_survival_enemy enemies[HCU_SURVIVAL_ACTIVE_LIMIT_MAX];
  hcu_survival_human humans[HCU_SURVIVAL_HUMANS_MAX];
  hcu_survival_budget budgets[HCU_SURVIVAL_BUDGET_KIND_COUNT];
} hcu_survival;

/* Worst units of one enemy of the template: 1 + max_mounted + max_swarm + max_secondary. */
unsigned int hcu_survival_template_worst_unit(const hcu_survival_template *t);

/* Checks a config against the qualified profiles without touching state.
 * Refuses swarm templates with an active limit above 12, any template whose
 * worst batch (active_limit x worst unit) exceeds HCU_SURVIVAL_RESERVE_MAX,
 * and swarms above HCU_SURVIVAL_SWARM_EXTRA_MAX extra members.
 * Call before map teardown; a refusal leaves a running match untouched. */
hcu_survival_status hcu_survival_validate(const hcu_survival_config *cfg);

hcu_survival_status hcu_survival_init(hcu_survival *s, const hcu_survival_config *cfg);

/* SETUP -> ACTIVE_WAVE: admits wave 1. Humans start alive. */
hcu_survival_status hcu_survival_begin(hcu_survival *s);

/* Marks an enemy slot as dying this tick. Only valid in ACTIVE_WAVE. */
hcu_survival_status hcu_survival_kill_enemy(hcu_survival *s, unsigned int slot);

/* Marks a human as dying this tick. Only valid in ACTIVE_WAVE. */
hcu_survival_status hcu_survival_kill_human(hcu_survival *s, unsigned int human);

/* Resolves the tick. ACTIVE_WAVE applies all deaths, then checks humans (zero
 * living ends the match), then checks the wave. INTERMISSION counts down and
 * admits the next wave at zero. */
void hcu_survival_tick(hcu_survival *s);

hcu_survival_status hcu_survival_budget_add(hcu_survival *s, hcu_survival_budget_kind kind, uint32_t id);
hcu_survival_status hcu_survival_projectile_acquire(hcu_survival *s);
hcu_survival_status hcu_survival_projectile_release(hcu_survival *s);

/* Pops up to max deferred ids in FIFO order; returns the count popped. */
unsigned int hcu_survival_deferred_drain(hcu_survival *s, uint32_t *out, unsigned int max);

hcu_survival_state hcu_survival_get_state(const hcu_survival *s);
unsigned int hcu_survival_wave_number(const hcu_survival *s);
unsigned int hcu_survival_living_humans(const hcu_survival *s);
unsigned int hcu_survival_active_units(const hcu_survival *s);
unsigned int hcu_survival_reserved_units(const hcu_survival *s);
unsigned int hcu_survival_batch_size(const hcu_survival *s);
unsigned int hcu_survival_intermission_left(const hcu_survival *s);
unsigned int hcu_survival_seed(const hcu_survival *s);
unsigned int hcu_survival_budget_count(const hcu_survival *s, hcu_survival_budget_kind kind);
unsigned int hcu_survival_budget_evicted(const hcu_survival *s, hcu_survival_budget_kind kind);
unsigned int hcu_survival_budget_refused(const hcu_survival *s, hcu_survival_budget_kind kind);
const hcu_survival_enemy *hcu_survival_enemy_at(const hcu_survival *s, unsigned int slot);
const hcu_survival_human *hcu_survival_human_at(const hcu_survival *s, unsigned int human);

/* Recounts active units from the enemy slots; equals hcu_survival_active_units
 * whenever the accounting is consistent. */
unsigned int hcu_survival_recount_active_units(const hcu_survival *s);

/* Bytes the controller occupies. Constant for the life of the process. */
unsigned int hcu_survival_storage_bytes(void);

#endif /* HCU_SURVIVAL_H */
