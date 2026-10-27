/* Survival wave controller for the HCU fork. See hcu_survival.h for the contract. */
#include "hcu_survival.h"

#include <stddef.h>

#define HCU_SURVIVAL_QUAL_SEED_0 0x5EED0001u
#define HCU_SURVIVAL_QUAL_SEED_1 0x5EED0002u
#define HCU_SURVIVAL_QUAL_SEED_2 0x5EED0003u

static const uint32_t g_qual_seeds[HCU_SURVIVAL_QUAL_SEED_COUNT] = {
    HCU_SURVIVAL_QUAL_SEED_0, HCU_SURVIVAL_QUAL_SEED_1, HCU_SURVIVAL_QUAL_SEED_2};

/* Built-in cycle used when a config passes no templates. */
static const hcu_survival_template g_default_templates[4] = {
    {2u, 1u, 1u, 0u, 0u}, /* worst unit 2 */
    {3u, 1u, 0u, 2u, 0u}, /* worst unit 3 */
    {2u, 2u, 1u, 1u, 1u}, /* worst unit 4 */
    {4u, 1u, 0u, 0u, 2u}, /* worst unit 3 */
};

#define HCU_SURVIVAL_DEFAULT_TEMPLATE_COUNT 4u
#define HCU_SURVIVAL_GROWTH_CAP_CYCLES HCU_SURVIVAL_CYCLE_CAP

static unsigned int worst_unit(const hcu_survival_template *t)
{
    return 1u + t->max_mounted + t->max_swarm + t->max_secondary;
}

static int template_valid(const hcu_survival_template *t, unsigned int active_limit)
{
    if (t->base_enemies < 1u) {
        return 0;
    }
    if (worst_unit(t) > active_limit) {
        return 0;
    }
    return 1;
}

static int qualified_seed(unsigned int seed)
{
    unsigned int i;

    if (seed == 0u) {
        return 1;
    }
    for (i = 0u; i < HCU_SURVIVAL_QUAL_SEED_COUNT; i++) {
        if (g_qual_seeds[i] == seed) {
            return 1;
        }
    }
    return 0;
}

static uint32_t rng_next(uint32_t *state)
{
    uint32_t x = *state;

    x ^= x << 13;
    x ^= x >> 17;
    x ^= x << 5;
    *state = x;
    return x;
}

static void budget_init(hcu_survival_budget *b, unsigned int capacity)
{
    unsigned int i;

    b->capacity = capacity;
    b->head = 0u;
    b->count = 0u;
    b->evicted = 0u;
    b->refused = 0u;
    for (i = 0u; i < HCU_SURVIVAL_BUDGET_CAP; i++) {
        b->items[i] = 0u;
    }
}

static int budget_is_ring(hcu_survival_budget_kind kind)
{
    return kind == HCU_SURVIVAL_BUDGET_CORPSE || kind == HCU_SURVIVAL_BUDGET_DROP ||
           kind == HCU_SURVIVAL_BUDGET_EFFECT;
}

/* Admits one wave. Caller has already advanced wave_number. Humans are
 * respawned here, and nowhere else. Returns a status and changes nothing on
 * failure. */
static hcu_survival_status admit_wave(hcu_survival *s)
{
    const hcu_survival_template *t;
    unsigned int idx;
    unsigned int cycle;
    unsigned int worst;
    unsigned int fit;
    unsigned int count;
    unsigned int growth_cycles;
    unsigned int slot;
    unsigned int i;

    idx = (s->wave_number - 1u) % s->template_count;
    cycle = (s->wave_number - 1u) / s->template_count;
    t = &s->tmpl[idx];
    worst = worst_unit(t);
    fit = s->active_limit / worst;
    if (fit == 0u) {
        return HCU_SURVIVAL_ERR_LIMIT;
    }
    growth_cycles = cycle < HCU_SURVIVAL_GROWTH_CAP_CYCLES ? cycle : HCU_SURVIVAL_GROWTH_CAP_CYCLES;
    count = t->base_enemies + t->growth_per_cycle * growth_cycles;
    if (count > fit) {
        count = fit;
    }
    if (count * worst > s->active_limit) {
        return HCU_SURVIVAL_ERR_LIMIT;
    }

    /* Respawn dead humans between waves only. */
    for (i = 0u; i < s->humans_count; i++) {
        if (!s->humans[i].alive) {
            s->humans[i].alive = 1u;
            s->humans[i].pending_death = 0u;
            s->humans_respawned++;
        }
    }

    s->active_units = 0u;
    s->mounted_active = 0u;
    s->swarm_active = 0u;
    s->secondary_active = 0u;
    for (slot = 0u; slot < HCU_SURVIVAL_ACTIVE_LIMIT_MAX; slot++) {
        hcu_survival_enemy *e = &s->enemies[slot];

        e->alive = 0u;
        e->pending_death = 0u;
        e->mounted = 0u;
        e->swarm = 0u;
        e->secondary = 0u;
        e->units = 0u;
    }
    for (slot = 0u; slot < count; slot++) {
        hcu_survival_enemy *e = &s->enemies[slot];
        uint32_t r = rng_next(&s->rng);
        unsigned int m = (unsigned int)(r % (t->max_mounted + 1u));
        unsigned int sw = (unsigned int)((r >> 8) % (t->max_swarm + 1u));
        unsigned int sc = (unsigned int)((r >> 16) % (t->max_secondary + 1u));

        e->alive = 1u;
        e->mounted = (unsigned char)m;
        e->swarm = (unsigned char)sw;
        e->secondary = (unsigned char)sc;
        e->units = (unsigned char)(1u + m + sw + sc);
        s->active_units += e->units;
        s->mounted_active += m;
        s->swarm_active += sw;
        s->secondary_active += sc;
    }

    s->batch_size = count;
    s->reserved_units = count * worst;
    s->enemies_admitted += count;
    s->state = HCU_SURVIVAL_STATE_ACTIVE_WAVE;
    return HCU_SURVIVAL_OK;
}

hcu_survival_status hcu_survival_validate(const hcu_survival_config *cfg)
{
    unsigned int i;
    unsigned int tc;
    const hcu_survival_template *tmpl;

    if (cfg == NULL) {
        return HCU_SURVIVAL_ERR_ARG;
    }
    if (cfg->difficulty != HCU_SURVIVAL_DIFFICULTY_NORMAL) {
        return HCU_SURVIVAL_ERR_UNSUPPORTED;
    }
    if (!qualified_seed(cfg->seed)) {
        return HCU_SURVIVAL_ERR_UNSUPPORTED;
    }
    if (cfg->humans < 1u || cfg->humans > HCU_SURVIVAL_HUMANS_MAX) {
        return HCU_SURVIVAL_ERR_ARG;
    }
    if (cfg->active_limit < 1u || cfg->active_limit > HCU_SURVIVAL_ACTIVE_LIMIT_MAX) {
        return HCU_SURVIVAL_ERR_ARG;
    }
    if (cfg->templates == NULL) {
        tmpl = g_default_templates;
        tc = HCU_SURVIVAL_DEFAULT_TEMPLATE_COUNT;
    } else {
        tmpl = cfg->templates;
        tc = cfg->template_count;
    }
    if (tc < 1u || tc > HCU_SURVIVAL_TEMPLATES_MAX) {
        return HCU_SURVIVAL_ERR_ARG;
    }
    for (i = 0u; i < tc; i++) {
        if (!template_valid(&tmpl[i], cfg->active_limit)) {
            return HCU_SURVIVAL_ERR_LIMIT;
        }
    }
    return HCU_SURVIVAL_OK;
}

hcu_survival_status hcu_survival_init(hcu_survival *s, const hcu_survival_config *cfg)
{
    hcu_survival_status st;
    const hcu_survival_template *src;
    unsigned int i;

    if (s == NULL) {
        return HCU_SURVIVAL_ERR_ARG;
    }
    st = hcu_survival_validate(cfg);
    if (st != HCU_SURVIVAL_OK) {
        return st;
    }

    s->difficulty = cfg->difficulty;
    s->state = HCU_SURVIVAL_STATE_SETUP;
    s->seed_used = cfg->seed == 0u ? g_qual_seeds[0] : cfg->seed;
    s->rng = s->seed_used;
    s->humans_count = cfg->humans;
    s->active_limit = cfg->active_limit;

    if (cfg->templates == NULL) {
        src = g_default_templates;
        s->template_count = HCU_SURVIVAL_DEFAULT_TEMPLATE_COUNT;
    } else {
        src = cfg->templates;
        s->template_count = cfg->template_count;
    }
    for (i = 0u; i < s->template_count; i++) {
        s->tmpl[i] = src[i];
    }

    s->wave_number = 0u;
    s->batch_size = 0u;
    s->reserved_units = 0u;
    s->active_units = 0u;
    s->mounted_active = 0u;
    s->swarm_active = 0u;
    s->secondary_active = 0u;
    s->intermission_left = 0u;
    s->waves_cleared = 0u;
    s->enemies_admitted = 0u;
    s->humans_respawned = 0u;

    for (i = 0u; i < HCU_SURVIVAL_ACTIVE_LIMIT_MAX; i++) {
        s->enemies[i].alive = 0u;
        s->enemies[i].pending_death = 0u;
        s->enemies[i].mounted = 0u;
        s->enemies[i].swarm = 0u;
        s->enemies[i].secondary = 0u;
        s->enemies[i].units = 0u;
    }
    for (i = 0u; i < HCU_SURVIVAL_HUMANS_MAX; i++) {
        s->humans[i].alive = 0u;
        s->humans[i].pending_death = 0u;
    }

    budget_init(&s->budgets[HCU_SURVIVAL_BUDGET_CORPSE], 16u);
    budget_init(&s->budgets[HCU_SURVIVAL_BUDGET_DROP], 16u);
    budget_init(&s->budgets[HCU_SURVIVAL_BUDGET_EFFECT], HCU_SURVIVAL_BUDGET_CAP);
    budget_init(&s->budgets[HCU_SURVIVAL_BUDGET_PROJECTILE], 32u);
    budget_init(&s->budgets[HCU_SURVIVAL_BUDGET_DEFERRED], 16u);
    return HCU_SURVIVAL_OK;
}

hcu_survival_status hcu_survival_begin(hcu_survival *s)
{
    hcu_survival_status st;
    unsigned int i;

    if (s == NULL) {
        return HCU_SURVIVAL_ERR_ARG;
    }
    if (s->state != HCU_SURVIVAL_STATE_SETUP) {
        return HCU_SURVIVAL_ERR_STATE;
    }
    for (i = 0u; i < s->humans_count; i++) {
        s->humans[i].alive = 1u;
        s->humans[i].pending_death = 0u;
    }
    s->wave_number = 1u;
    st = admit_wave(s);
    if (st != HCU_SURVIVAL_OK) {
        s->state = HCU_SURVIVAL_STATE_GAME_OVER;
    }
    return st;
}

hcu_survival_status hcu_survival_kill_enemy(hcu_survival *s, unsigned int slot)
{
    if (s == NULL || slot >= HCU_SURVIVAL_ACTIVE_LIMIT_MAX) {
        return HCU_SURVIVAL_ERR_ARG;
    }
    if (s->state != HCU_SURVIVAL_STATE_ACTIVE_WAVE) {
        return HCU_SURVIVAL_ERR_STATE;
    }
    if (slot >= s->batch_size) {
        return HCU_SURVIVAL_ERR_ARG;
    }
    if (!s->enemies[slot].alive) {
        return HCU_SURVIVAL_ERR_STATE;
    }
    s->enemies[slot].pending_death = 1u;
    return HCU_SURVIVAL_OK;
}

hcu_survival_status hcu_survival_kill_human(hcu_survival *s, unsigned int human)
{
    if (s == NULL || human >= s->humans_count) {
        return HCU_SURVIVAL_ERR_ARG;
    }
    if (s->state != HCU_SURVIVAL_STATE_ACTIVE_WAVE) {
        return HCU_SURVIVAL_ERR_STATE;
    }
    if (!s->humans[human].alive) {
        return HCU_SURVIVAL_ERR_STATE;
    }
    s->humans[human].pending_death = 1u;
    return HCU_SURVIVAL_OK;
}

void hcu_survival_tick(hcu_survival *s)
{
    unsigned int i;
    unsigned int living_humans;
    unsigned int living_enemies;
    hcu_survival_status st;

    if (s == NULL) {
        return;
    }

    switch (s->state) {
    case HCU_SURVIVAL_STATE_ACTIVE_WAVE:
        /* All deaths for this tick resolve here, before any end check. */
        for (i = 0u; i < s->batch_size; i++) {
            hcu_survival_enemy *e = &s->enemies[i];

            if (e->alive && e->pending_death) {
                e->alive = 0u;
                e->pending_death = 0u;
                s->active_units -= e->units;
                s->mounted_active -= e->mounted;
                s->swarm_active -= e->swarm;
                s->secondary_active -= e->secondary;
                (void)hcu_survival_budget_add(s, HCU_SURVIVAL_BUDGET_CORPSE, (s->wave_number << 8) | i);
            }
        }
        living_humans = 0u;
        for (i = 0u; i < s->humans_count; i++) {
            hcu_survival_human *h = &s->humans[i];

            if (h->alive && h->pending_death) {
                h->alive = 0u;
                h->pending_death = 0u;
                (void)hcu_survival_budget_add(s, HCU_SURVIVAL_BUDGET_CORPSE, 0x80000000u | i);
            }
            if (h->alive) {
                living_humans++;
            }
        }
        /* Human elimination ends the match even if the last enemy died too. */
        if (living_humans == 0u) {
            s->state = HCU_SURVIVAL_STATE_GAME_OVER;
            return;
        }
        living_enemies = 0u;
        for (i = 0u; i < s->batch_size; i++) {
            if (s->enemies[i].alive) {
                living_enemies++;
            }
        }
        if (living_enemies == 0u) {
            s->waves_cleared++;
            s->state = HCU_SURVIVAL_STATE_INTERMISSION;
            s->intermission_left = HCU_SURVIVAL_INTERMISSION_TICKS;
        }
        break;

    case HCU_SURVIVAL_STATE_INTERMISSION:
        if (s->intermission_left > 0u) {
            s->intermission_left--;
        }
        if (s->intermission_left == 0u) {
            s->wave_number++;
            st = admit_wave(s);
            if (st != HCU_SURVIVAL_OK) {
                /* Validation makes this unreachable; fail closed if it is not. */
                s->state = HCU_SURVIVAL_STATE_GAME_OVER;
            }
        }
        break;

    case HCU_SURVIVAL_STATE_SETUP:
    case HCU_SURVIVAL_STATE_GAME_OVER:
    default:
        break;
    }
}

hcu_survival_status hcu_survival_budget_add(hcu_survival *s, hcu_survival_budget_kind kind, uint32_t id)
{
    hcu_survival_budget *b;

    if (s == NULL || (unsigned int)kind >= HCU_SURVIVAL_BUDGET_KIND_COUNT) {
        return HCU_SURVIVAL_ERR_ARG;
    }
    if (kind == HCU_SURVIVAL_BUDGET_PROJECTILE) {
        return HCU_SURVIVAL_ERR_ARG; /* use the acquire call for counters */
    }
    b = &s->budgets[kind];
    if (b->count < b->capacity) {
        b->items[(b->head + b->count) % b->capacity] = id;
        b->count++;
        return HCU_SURVIVAL_OK;
    }
    if (budget_is_ring(kind)) {
        b->items[b->head] = id;
        b->head = (b->head + 1u) % b->capacity;
        b->evicted++;
        return HCU_SURVIVAL_OK;
    }
    b->refused++;
    return HCU_SURVIVAL_ERR_BUDGET;
}

hcu_survival_status hcu_survival_projectile_acquire(hcu_survival *s)
{
    hcu_survival_budget *b;

    if (s == NULL) {
        return HCU_SURVIVAL_ERR_ARG;
    }
    b = &s->budgets[HCU_SURVIVAL_BUDGET_PROJECTILE];
    if (b->count < b->capacity) {
        b->count++;
        return HCU_SURVIVAL_OK;
    }
    b->refused++;
    return HCU_SURVIVAL_ERR_BUDGET;
}

hcu_survival_status hcu_survival_projectile_release(hcu_survival *s)
{
    hcu_survival_budget *b;

    if (s == NULL) {
        return HCU_SURVIVAL_ERR_ARG;
    }
    b = &s->budgets[HCU_SURVIVAL_BUDGET_PROJECTILE];
    if (b->count == 0u) {
        return HCU_SURVIVAL_ERR_STATE;
    }
    b->count--;
    return HCU_SURVIVAL_OK;
}

unsigned int hcu_survival_deferred_drain(hcu_survival *s, uint32_t *out, unsigned int max)
{
    hcu_survival_budget *b;
    unsigned int n = 0u;

    if (s == NULL || out == NULL) {
        return 0u;
    }
    b = &s->budgets[HCU_SURVIVAL_BUDGET_DEFERRED];
    while (n < max && b->count > 0u) {
        out[n++] = b->items[b->head];
        b->head = (b->head + 1u) % b->capacity;
        b->count--;
    }
    return n;
}

hcu_survival_state hcu_survival_get_state(const hcu_survival *s)
{
    return s == NULL ? HCU_SURVIVAL_STATE_GAME_OVER : s->state;
}

unsigned int hcu_survival_wave_number(const hcu_survival *s)
{
    return s == NULL ? 0u : s->wave_number;
}

unsigned int hcu_survival_living_humans(const hcu_survival *s)
{
    unsigned int i;
    unsigned int n = 0u;

    if (s == NULL) {
        return 0u;
    }
    for (i = 0u; i < s->humans_count; i++) {
        if (s->humans[i].alive) {
            n++;
        }
    }
    return n;
}

unsigned int hcu_survival_active_units(const hcu_survival *s)
{
    return s == NULL ? 0u : s->active_units;
}

unsigned int hcu_survival_reserved_units(const hcu_survival *s)
{
    return s == NULL ? 0u : s->reserved_units;
}

unsigned int hcu_survival_batch_size(const hcu_survival *s)
{
    return s == NULL ? 0u : s->batch_size;
}

unsigned int hcu_survival_intermission_left(const hcu_survival *s)
{
    return s == NULL ? 0u : s->intermission_left;
}

unsigned int hcu_survival_seed(const hcu_survival *s)
{
    return s == NULL ? 0u : s->seed_used;
}

unsigned int hcu_survival_budget_count(const hcu_survival *s, hcu_survival_budget_kind kind)
{
    if (s == NULL || (unsigned int)kind >= HCU_SURVIVAL_BUDGET_KIND_COUNT) {
        return 0u;
    }
    return s->budgets[kind].count;
}

unsigned int hcu_survival_budget_evicted(const hcu_survival *s, hcu_survival_budget_kind kind)
{
    if (s == NULL || (unsigned int)kind >= HCU_SURVIVAL_BUDGET_KIND_COUNT) {
        return 0u;
    }
    return s->budgets[kind].evicted;
}

unsigned int hcu_survival_budget_refused(const hcu_survival *s, hcu_survival_budget_kind kind)
{
    if (s == NULL || (unsigned int)kind >= HCU_SURVIVAL_BUDGET_KIND_COUNT) {
        return 0u;
    }
    return s->budgets[kind].refused;
}

const hcu_survival_enemy *hcu_survival_enemy_at(const hcu_survival *s, unsigned int slot)
{
    if (s == NULL || slot >= HCU_SURVIVAL_ACTIVE_LIMIT_MAX) {
        return NULL;
    }
    return &s->enemies[slot];
}

const hcu_survival_human *hcu_survival_human_at(const hcu_survival *s, unsigned int human)
{
    if (s == NULL || human >= s->humans_count) {
        return NULL;
    }
    return &s->humans[human];
}

unsigned int hcu_survival_recount_active_units(const hcu_survival *s)
{
    unsigned int i;
    unsigned int n = 0u;

    if (s == NULL) {
        return 0u;
    }
    for (i = 0u; i < s->batch_size; i++) {
        if (s->enemies[i].alive) {
            n += s->enemies[i].units;
        }
    }
    return n;
}

unsigned int hcu_survival_storage_bytes(void)
{
    return (unsigned int)sizeof(hcu_survival);
}
