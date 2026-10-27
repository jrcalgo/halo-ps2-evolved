/* CE-side pure helpers for the survival driver. See hcu_survival_ce.h. */
#include "hcu_survival_ce.h"

#include <stddef.h>

/* C1 roster variants (docs/reports/m2-c1-actor-roster-2026-10-23.json, disposition "combat"). The unit paths are the
 * roster's unit tags, whose spawn bounds the adapter reads at start. */
static const hcu_survival_ce_recipe g_recipes[HCU_SURVIVAL_CE_RECIPE_COUNT] = {
    {"characters\\grunt\\grunt minor plasma pistol", "characters\\grunt\\grunt"},
    {"characters\\jackal\\jackal minor plasma pistol", "characters\\jackal\\jackal"},
    {"characters\\elite\\elite minor\\elite minor plasma rifle", "characters\\elite\\elite"},
    {"characters\\hunter\\hunter", "characters\\hunter\\hunter"},
};

const hcu_survival_ce_recipe *hcu_survival_ce_recipe_at(unsigned int index)
{
    if (index >= HCU_SURVIVAL_CE_RECIPE_COUNT) {
        return NULL;
    }
    return &g_recipes[index];
}

unsigned int hcu_survival_ce_recipe_for(unsigned int wave_number, unsigned int slot)
{
    return (wave_number + slot) % HCU_SURVIVAL_CE_RECIPE_COUNT;
}

unsigned int hcu_survival_ce_secondary_worst(int lower, int upper)
{
    if (upper < lower) {
        return lower > 0 ? (unsigned int)lower : 0u;
    }
    return upper > 0 ? (unsigned int)upper : 0u;
}

int hcu_survival_ce_secondary_fits(const hcu_survival_template *t, unsigned int recipe_worst_secondary)
{
    if (t == NULL) {
        return 0;
    }
    return recipe_worst_secondary <= t->max_secondary;
}

int hcu_survival_ce_within_worst(const hcu_survival_template *t, unsigned int mounted, unsigned int swarm,
                                 unsigned int secondary)
{
    if (t == NULL) {
        return 0;
    }
    return mounted <= t->max_mounted && swarm <= t->max_swarm && secondary <= t->max_secondary;
}

int hcu_survival_ce_may_place(unsigned int live_actors, unsigned int reserved_units)
{
    /* Compared without subtraction, so a reservation larger than the pool cannot wrap. */
    if (live_actors > HCU_C5_ACTOR_POOL_PS2 - HCU_C5_ACTOR_MARGIN) {
        return 0;
    }
    return reserved_units <= (HCU_C5_ACTOR_POOL_PS2 - HCU_C5_ACTOR_MARGIN) - live_actors;
}

unsigned int hcu_survival_ce_deaths_delta(unsigned int seen, unsigned int now)
{
    return now - seen; /* unsigned: a counter that wrapped still gives the true delta */
}

int hcu_survival_ce_respawn_allowed(int hcu_alive, int may_flag, unsigned int deaths_now, unsigned int deaths_seen)
{
    return hcu_alive && may_flag && deaths_now == deaths_seen;
}

unsigned int hcu_survival_ce_next_reserve(const hcu_survival *s)
{
    unsigned int next;
    unsigned int idx;
    unsigned int cycle;
    unsigned int growth_cycles;
    unsigned int count;
    const hcu_survival_template *t;

    if (s == NULL || s->template_count == 0u) {
        return 0u;
    }
    next = s->wave_number + 1u; /* the wave the next tick admits */
    idx = (next - 1u) % s->template_count;
    cycle = (next - 1u) / s->template_count;
    t = &s->tmpl[idx];
    growth_cycles = cycle < HCU_SURVIVAL_CYCLE_CAP ? cycle : HCU_SURVIVAL_CYCLE_CAP;
    count = t->base_enemies + t->growth_per_cycle * growth_cycles;
    if (count > s->active_limit) {
        count = s->active_limit;
    }
    return count * hcu_survival_template_worst_unit(t);
}

int hcu_survival_ce_raise_secondary(hcu_survival_template *tmpl, unsigned int count, unsigned int active_limit,
                                    unsigned int worst_secondary)
{
    unsigned int i;
    int ok = 1;

    if (tmpl == NULL || count == 0u || count > HCU_SURVIVAL_TEMPLATES_MAX) {
        return 0;
    }
    if (worst_secondary > HCU_SURVIVAL_SWARM_EXTRA_MAX + 1u) {
        return 0; /* beyond any tag bound the table is sized for */
    }
    for (i = 0u; i < count; i++) {
        if (tmpl[i].max_secondary < worst_secondary) {
            tmpl[i].max_secondary = worst_secondary;
        }
        if (active_limit * hcu_survival_template_worst_unit(&tmpl[i]) > HCU_SURVIVAL_RESERVE_MAX) {
            ok = 0;
        }
    }
    return ok;
}

void hcu_survival_ce_slots_clear(hcu_survival_ce_slots *slots)
{
    unsigned int i;

    if (slots == NULL) {
        return;
    }
    for (i = 0u; i < HCU_SURVIVAL_ACTIVE_LIMIT_MAX; i++) {
        slots->actor[i] = HCU_SURVIVAL_CE_NO_ACTOR;
    }
}

unsigned int hcu_survival_ce_slot_of_actor(const hcu_survival_ce_slots *slots, int32_t actor)
{
    unsigned int i;

    if (slots == NULL || actor < 0) {
        return HCU_SURVIVAL_CE_NO_SLOT;
    }
    for (i = 0u; i < HCU_SURVIVAL_ACTIVE_LIMIT_MAX; i++) {
        if (slots->actor[i] == actor) {
            return i;
        }
    }
    return HCU_SURVIVAL_CE_NO_SLOT;
}

unsigned int hcu_survival_ce_human_for_slot(const hcu_survival *s, unsigned int slot)
{
    unsigned int living;
    unsigned int want;
    unsigned int i;

    if (s == NULL) {
        return HCU_SURVIVAL_CE_NO_HUMAN;
    }
    living = hcu_survival_living_humans(s);
    if (living == 0u) {
        return HCU_SURVIVAL_CE_NO_HUMAN;
    }
    want = slot % living;
    for (i = 0u; i < s->humans_count; i++) {
        if (s->humans[i].alive) {
            if (want == 0u) {
                return i;
            }
            want--;
        }
    }
    return HCU_SURVIVAL_CE_NO_HUMAN;
}
