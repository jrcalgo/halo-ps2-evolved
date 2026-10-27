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
 * swarm members + secondary spawns. Admission reserves the worst case for the
 * whole batch (batch * worst_unit of the template) and never admits past the
 * active limit. The reserved worst case is always >= the actual active units.
 *
 * Only CE Normal is qualified. Seed 0 selects the first qualification seed.
 * No floating point. Single-threaded, called from the tick lane only. */
#ifndef HCU_SURVIVAL_H
#define HCU_SURVIVAL_H

#include <stdint.h>

#define HCU_SURVIVAL_TICK_HZ 30u
#define HCU_SURVIVAL_INTERMISSION_TICKS (5u * HCU_SURVIVAL_TICK_HZ)
#define HCU_SURVIVAL_ACTIVE_LIMIT_MAX 32u
#define HCU_SURVIVAL_HUMANS_MAX 4u
#define HCU_SURVIVAL_TEMPLATES_MAX 8u
#define HCU_SURVIVAL_QUAL_SEED_COUNT 3u
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
  unsigned int max_swarm;      /* worst-case swarm members per enemy */
  unsigned int max_secondary;  /* worst-case secondary spawns per enemy */
} hcu_survival_template;

typedef struct hcu_survival_config {
  hcu_survival_difficulty difficulty;
  unsigned int seed;                       /* 0 or a qualification seed */
  unsigned int humans;                     /* 1..HCU_SURVIVAL_HUMANS_MAX */
  unsigned int active_limit;               /* 1..HCU_SURVIVAL_ACTIVE_LIMIT_MAX */
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

/* Checks a config against the qualified profiles without touching state.
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
