#include "game/gun.h"
#include <string.h>

const gun_def GUN_PISTOL = {
    3.5f, 1, 12, 60, 12, 35, 67, 0.0f, 1, 0, 0,
    0, 0, 0, 1, 1,
    3.5f, 1.0f, 1.0f, 0, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f,
    0.0f, 0.0f, 0.0f, 1,
    0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0, 0, 0, {{{0, 0}, {0, 0}}, {{0, 0}, {0, 0}}},
};

const gun_def GUN_ASSAULT_RIFLE = {
    15.0f, 1, 60, 240, 60, 29, 87, 0.0f, 1, 0, 0,
    0, 0, 0, 1, 1,
    15.0f, 0.033333335f, 0.333333343f, 0, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f,
    0.0f, 0.0f, 0.0f, 1,
    0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0, 0, 0, {{{0, 0}, {0, 0}}, {{0, 0}, {0, 0}}},
};

const gun_def GUN_SHOTGUN = {
    1.0f, 1, 12, 24, 1, 23, 12, 0.0f, 15, 15, 1,
    0, 0, 0, 1, 1,
    1.0f, 1.0f, 1.0f, 0, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f,
    0.0f, 0.0f, 0.0f, 1,
    0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0, 0, 0, {{{0, 0}, {0, 0}}, {{0, 0}, {0, 0}}},
};

static int16_t imin(int16_t a, int16_t b) { return a < b ? a : b; }

void gun_init(gun *g, const gun_def *def)
{
    g->loaded = imin(def->rounds_total_initial, def->rounds_loaded_maximum);
    g->total = (int16_t)(def->rounds_total_initial - g->loaded);
    g->idle_ticks = 127;
    g->magazine = GUN_MAG_IDLE;
    g->magazine_timer = 0;
    g->trigger = GUN_TRIG_IDLE;
    g->state_timer = 0;
    g->needs_reload = 0;
    g->released = 1;
    g->fraction = 0.0f;
    g->error_fraction = 0.0f;
    g->shot_error_fraction = 0.0f;
    g->heat = 0.0f;
    g->age = 0.0f;
    g->overcharged = 0.0f;
    g->overheated = 0;
    g->recharge_frac = 0;
    g->shots = 0;
    g->pellets = 0;
    g->firing_effects_used_flags = 0;
    g->firing_effect_index = 0;
    g->firing_effect_shots_remaining = 0;
    g->last_firing_effect = -1;
    g->misfired = 0;
}

static int16_t reload_timer(const gun_def *def, int from_button)
{
    if (from_button && def->shotgun_enter_frames > 0) return def->shotgun_enter_frames;
    return def->reload_empty_frames;
}

static void start_reload(gun *g, const gun_def *def, int from_button);

static void finish_reload(gun *g, const gun_def *def, int trigger_held)
{
    int16_t take = def->rounds_reloaded;
    int16_t loaded;
    /* Flag bit 0 throws away the rounds still in the magazine. */
    if (def->wastes_rounds) g->loaded = 0;
    if (take > g->total) take = g->total;
    loaded = (int16_t)(g->loaded + take);
    if (loaded > def->rounds_loaded_maximum) loaded = def->rounds_loaded_maximum;
    g->total = (int16_t)(g->total - loaded + g->loaded);
    g->loaded = loaded;
    g->magazine = GUN_MAG_UNCHAMBERED;
    g->magazine_timer = 0;
    /* A wasting magazine does not chain. Primary trigger is one of the bits
     * that also stop a chained shell. */
    if (!def->wastes_rounds && !trigger_held && g->total > 0 &&
        g->loaded < def->rounds_loaded_maximum)
        start_reload(g, def, 0);
}

static void start_reload(gun *g, const gun_def *def, int from_button)
{
    if (g->trigger != GUN_TRIG_IDLE) return;
    if (g->magazine != GUN_MAG_IDLE && g->magazine != GUN_MAG_UNCHAMBERED) return;
    if (g->total > 0 && g->loaded < def->rounds_loaded_maximum) {
        g->magazine = GUN_MAG_RELOADING;
        g->magazine_timer = reload_timer(def, from_button);
    }
    g->needs_reload = 0;
}

static void gun_reset(gun *g, const gun_def *def)
{
    if (g->magazine == GUN_MAG_RELOADING &&
        2 * (int)g->magazine_timer < def->reload_empty_frames)
        finish_reload(g, def, 0);
    g->magazine = GUN_MAG_IDLE;
    g->magazine_timer = 0;
    g->trigger = GUN_TRIG_UNINITIALIZED;
    g->needs_reload = 0;
}

static int enough_rounds(const gun *g, const gun_def *def)
{
    if (!def->uses_magazine || def->rounds_per_shot <= 0) return 1;
    /* Partial ammunition may fire, and the magazine is then empty. */
    if (g->loaded >= def->rounds_per_shot || def->partial_ammo) return 1;
    return 0;
}

static float current_rate(const gun *g, const gun_def *def)
{
    return (def->rate_final - def->rate_of_fire) * g->fraction + def->rate_of_fire;
}

static int can_fire(const gun *g, const gun_def *def)
{
    float rate = current_rate(g, def);
    float required = rate > 0.0001f ? (float)GUN_TICKS_PER_SECOND / rate : 0.0f;
    if (def->age_rate_of_fire_penalty > 0.0f)
        required *= 1.0f + g->age * def->age_rate_of_fire_penalty;
    if (def->latched && !g->released) return 0;
    return g->magazine == GUN_MAG_IDLE &&
        enough_rounds(g, def) &&
        (float)g->idle_ticks + 1.0f >= required;
}

/* rounds_recharged_per_second is split into whole rounds and a 30 Hz remainder. */
static void recharge(gun *g, const gun_def *def)
{
    int whole, frac;
    if (def->rounds_recharged_per_second <= 0) return;
    if (g->loaded >= def->rounds_loaded_maximum) return;
    whole = def->rounds_recharged_per_second / GUN_TICKS_PER_SECOND;
    frac = def->rounds_recharged_per_second % GUN_TICKS_PER_SECOND;
    g->loaded = (int16_t)(g->loaded + whole);
    g->recharge_frac = (int16_t)(g->recharge_frac + frac);
    if (g->recharge_frac >= GUN_TICKS_PER_SECOND) {
        g->loaded++;
        g->recharge_frac = (int16_t)(g->recharge_frac - GUN_TICKS_PER_SECOND);
    }
    if (g->loaded > def->rounds_loaded_maximum) g->loaded = def->rounds_loaded_maximum;
}

static int time_ticks(float seconds)
{
    float ticks = seconds * (float)GUN_TICKS_PER_SECOND;
    if (ticks <= 0.0f) return 0;
    return ticks >= 32767.0f ? 32767 : (int)ticks;
}

static void add_heat(gun *g, const gun_def *def)
{
    g->heat += def->heat_per_round;
    if (g->heat > 1.0f) g->heat = 1.0f;
}

static void update_heat(gun *g, const gun_def *def)
{
    if (g->heat <= 0.0f) return;
    if (g->heat >= def->heat_overheat) g->overheated = 1;
    if (g->overcharged == 0.0f) {
        float heat_loss = def->heat_loss;
        if (def->age_heat_recovery_penalty > 0.0f)
            heat_loss *= 1.0f - g->age * def->age_heat_recovery_penalty;
        g->heat -= heat_loss / (float)GUN_TICKS_PER_SECOND;
        if (g->heat < 0.0f) g->heat = 0.0f;
    }
    if (g->overheated && g->heat < def->heat_recovery) g->overheated = 0;
}

static uint32_t gun_random_seed(uint32_t *seed)
{
    *seed = *seed * 1664525u + 1013904223u;
    return *seed;
}

static int fire_round(gun *g, const gun_def *def, uint32_t *seed)
{
    int misfired = 0;
    g->misfired = 0;
    if (def->firing_effect_count > 0) {
        int count = def->firing_effect_count > 2 ? 2 : def->firing_effect_count;
        int starting = g->firing_effect_index;
        int index;
        uint32_t used_mask = (1u << count) - 1u;
        if (g->firing_effect_shots_remaining <= 0) {
            int attempts = 0;
            if (starting < 0 || starting >= count) starting = 0;
            index = ((def->trigger_flags & GUN_TRIGGER_RANDOM_FIRING_EFFECTS) && seed) ?
                (int)((gun_random_seed(seed) >> 16) % (uint32_t)count) : starting;
            do {
                if (g->firing_effects_used_flags == used_mask)
                    g->firing_effects_used_flags = 0;
                do {
                    index++;
                    if (index >= count) index = 0;
                } while (g->firing_effects_used_flags & (1u << index));
                g->firing_effect_index = (int16_t)index;
                g->last_firing_effect = (int16_t)index;
                g->firing_effects_used_flags |= 1u << index;
                {
                    int lower = def->firing_effect_shots[0][index][0];
                    int upper = def->firing_effect_shots[0][index][1];
                    if (upper < lower) upper = lower;
                    g->firing_effect_shots_remaining = (int16_t)(lower +
                        (seed ? ((uint32_t)(upper - lower) *
                            (gun_random_seed(seed) >> 16) >> 16) : 0));
                }
                attempts++;
            } while (g->firing_effect_shots_remaining <= 0 && index != starting && attempts < count);
        }
        if (g->firing_effect_shots_remaining > 0) g->firing_effect_shots_remaining--;
        if (def->age_misfire_start > 0.0f && def->age_misfire_start < 1.0f &&
            g->age > def->age_misfire_start && seed) {
            float chance = ((g->age - def->age_misfire_start) * def->age_misfire_chance) /
                (1.0f - def->age_misfire_start);
            float roll;
            if (g->trigger == GUN_TRIG_SPEWING) chance *= 2.0f;
            roll = (float)(gun_random_seed(seed) >> 16) / 65535.0f;
            misfired = roll < chance;
        }
    }
    if (def->uses_magazine && def->cannot_fire_at_maximum_age && g->age >= 1.0f) {
        g->trigger = GUN_TRIG_LOCKED;
        g->state_timer = -1;
        g->idle_ticks = 0;
        return 0;
    }
    if (def->uses_magazine && def->rounds_per_shot > 0) {
        g->loaded = (int16_t)(g->loaded - def->rounds_per_shot);
        if (g->loaded <= 0) g->loaded = 0;
        else if (def->chamber_every_shot) {
            g->magazine = GUN_MAG_UNCHAMBERED;
            g->magazine_timer = 0;
        }
    }
    add_heat(g, def);
    if (def->firing_effect_count > 0 && def->age_generated_per_round > 0.0f) {
        g->age += def->age_generated_per_round;
        if (g->age > 1.0f) g->age = 1.0f;
    }
    g->released = 0;
    g->idle_ticks = 0;
    g->shots++;
    g->pellets += (uint32_t)def->projectiles_per_shot;
    g->misfired = misfired;
    return 1;
}

int gun_tick_seeded(gun *g, const gun_def *def, int trigger, int reload, uint32_t *seed)
{
    int masked;
    int fired = 0;
    g->misfired = 0;
    g->shot_error_fraction = g->error_fraction;
    update_heat(g, def);
    g->overcharged = 0.0f;
    if (g->state_timer > 0) g->state_timer--;
    masked = g->state_timer > 0;
    if (!trigger) g->released = 1;
    if (reload) g->needs_reload = 1;
    if (g->needs_reload) start_reload(g, def, 1);

    recharge(g, def);
    if (g->magazine_timer) g->magazine_timer--;
    if (g->magazine == GUN_MAG_RELOADING) {
        if (g->magazine_timer - 1 <= 0) finish_reload(g, def, trigger);
    } else if (g->magazine == GUN_MAG_UNCHAMBERED) {
        g->magazine = GUN_MAG_CHAMBERING;
        g->magazine_timer = (int16_t)(def->chamber_seconds * (float)GUN_TICKS_PER_SECOND);
    } else if (g->magazine == GUN_MAG_CHAMBERING) {
        if (g->magazine_timer == 0) g->magazine = GUN_MAG_IDLE;
    }

    if (g->trigger == GUN_TRIG_UNINITIALIZED) {
        g->trigger = GUN_TRIG_IDLE;
    } else if (g->trigger == GUN_TRIG_CHARGING) {
        if (g->state_timer == 0) {
            g->trigger = GUN_TRIG_CHARGED;
            g->state_timer = (int16_t)time_ticks(def->charged_seconds);
        } else if (!trigger) {
            if (def->trigger_count > 1 && enough_rounds(g, def)) {
                fired = fire_round(g, def, seed);
            }
            if (g->trigger != GUN_TRIG_LOCKED) {
                g->trigger = GUN_TRIG_IDLE;
                g->fraction = 0.0f;
            }
        }
    } else if (g->trigger == GUN_TRIG_CHARGED) {
        if (trigger) {
            if (def->charged_seconds > 0.0f) {
                g->overcharged = 1.0f - ((float)g->state_timer / (float)GUN_TICKS_PER_SECOND) / def->charged_seconds;
                if (g->overcharged < 0.0f) g->overcharged = 0.0f;
            }
        }
        if (trigger && g->state_timer == 0) {
            if (def->overcharged_action == 2 && enough_rounds(g, def)) {
                fired = fire_round(g, def, seed);
            }
            if (g->trigger != GUN_TRIG_LOCKED) g->trigger = GUN_TRIG_IDLE;
        } else if (!trigger) {
            if (enough_rounds(g, def)) {
                fired = fire_round(g, def, seed);
            }
            if (g->trigger != GUN_TRIG_LOCKED) {
                g->trigger = GUN_TRIG_IDLE;
                g->fraction = 0.0f;
            }
        }
    } else if (g->trigger == GUN_TRIG_IDLE) {
        if (def->uses_magazine && def->rounds_per_shot > 0 && g->total > 0 &&
            (((g->loaded < def->rounds_per_shot) && !def->partial_ammo) || g->loaded == 0))
            start_reload(g, def, 1);
        if (!masked && trigger && !g->overheated && can_fire(g, def)) {
            if (def->charge_seconds > 0.0f) {
                /* CE's single-trigger charging path fires immediately when
                 * the trigger's prior runtime rate fraction is nonzero,
                 * then enters charging. */
                if (def->trigger_count == 1 && g->fraction > 0.0f &&
                    enough_rounds(g, def)) {
                    fired = fire_round(g, def, seed);
                }
                if (g->trigger != GUN_TRIG_LOCKED) {
                    g->trigger = GUN_TRIG_CHARGING;
                    g->state_timer = (int16_t)time_ticks(def->charge_seconds);
                }
            } else {
                fired = fire_round(g, def, seed);
            }
        } else if (g->idle_ticks < 127) {
            g->idle_ticks++;
        }
    } else if (g->trigger == GUN_TRIG_LOCKED && !trigger) {
        g->trigger = GUN_TRIG_IDLE;
        g->state_timer = 0;
    }
    if (trigger) {
        g->fraction += def->rate_accel;
        if (g->fraction > 1.0f) g->fraction = 1.0f;
    } else {
        g->fraction -= def->rate_decel;
        if (g->fraction < 0.0f) g->fraction = 0.0f;
    }
    if (trigger) {
        g->error_fraction += def->error_accel;
        if (g->error_fraction > 1.0f) g->error_fraction = 1.0f;
    } else {
        g->error_fraction -= def->error_decel;
        if (g->error_fraction < 0.0f) g->error_fraction = 0.0f;
    }
    return fired;
}

int gun_tick(gun *g, const gun_def *def, int trigger, int reload)
{
    return gun_tick_seeded(g, def, trigger, reload, NULL);
}

static int trigger_time_ticks(float seconds)
{
    float ticks = seconds * (float)GUN_TICKS_PER_SECOND;
    if (ticks <= 0.0f) return 0;
    return ticks >= 32767.0f ? 32767 : (int)ticks;
}

static int trigger_magazine_valid(const gun_trigger_profile *profile)
{
    return profile->magazine_index == GUN_TRIGGER_NONE ||
        (profile->magazine_index >= 0 && profile->magazine_index < GUN_TRIGGER_MAGAZINES);
}

static int trigger_fire(gun_trigger_pair *pair,
    const gun_trigger_profile profile[GUN_TRIGGER_MAX], int index, uint32_t *seed)
{
    const gun_trigger_profile *definition = &profile[index];
    gun_trigger_runtime *runtime = &pair->trigger[index];
    int was_spewing = runtime->state == GUN_TRIG_SPEWING;
    int fired = 1;
    int effect_count = definition->firing_effect_count > 2 ? 2 : definition->firing_effect_count;
    runtime->misfired = 0;
    if (definition->magazine_index != GUN_TRIGGER_NONE) {
        if (!trigger_magazine_valid(definition)) fired = 0;
        else {
            int16_t loaded = pair->magazine_loaded[definition->magazine_index];
            if (loaded < definition->rounds_per_shot &&
                !(definition->flags & GUN_TRIGGER_CAN_PARTIAL)) fired = 0;
            if ((pair->weapon_flags & GUN_WEAPON_CANNOT_FIRE_AT_MAXIMUM_AGE) &&
                pair->weapon_age >= 1.0f) fired = 0;
            if (loaded < definition->minimum_rounds && !runtime->released_since_shot) fired = 0;
            if (fired && definition->rounds_per_shot > 0) {
                loaded = (int16_t)(loaded - definition->rounds_per_shot);
                pair->magazine_loaded[definition->magazine_index] = loaded > 0 ? loaded : 0;
            }
        }
    }
    if (effect_count > 0) {
        int starting = runtime->firing_effect_index;
        if (runtime->firing_effect_shots_remaining <= 0) {
            int index_effect;
            uint32_t mask = (1u << effect_count) - 1u;
            int attempts = 0;
            if (starting < 0 || starting >= effect_count) starting = 0;
            index_effect = ((definition->flags & GUN_TRIGGER_RANDOM_FIRING_EFFECTS) && seed) ?
                (int)((gun_random_seed(seed) >> 16) % (uint32_t)effect_count) : starting;
            do {
                if (runtime->firing_effects_used_flags == mask)
                    runtime->firing_effects_used_flags = 0;
                do {
                    index_effect++;
                    if (index_effect >= effect_count) index_effect = 0;
                } while (runtime->firing_effects_used_flags & (1u << index_effect));
                runtime->firing_effect_index = (int16_t)index_effect;
                runtime->firing_effects_used_flags |= 1u << index_effect;
                {
                    int lower = definition->firing_effect_shots[index_effect][0];
                    int upper = definition->firing_effect_shots[index_effect][1];
                    if (upper < lower) upper = lower;
                    runtime->firing_effect_shots_remaining = (int16_t)(lower +
                        (seed ? ((uint32_t)(upper - lower) *
                            (gun_random_seed(seed) >> 16) >> 16) : 0));
                }
                attempts++;
            } while (runtime->firing_effect_shots_remaining <= 0 &&
                index_effect != starting && attempts < effect_count);
        }
        if (runtime->firing_effect_shots_remaining > 0)
            runtime->firing_effect_shots_remaining--;
        if (definition->age_misfire_start > 0.0f && definition->age_misfire_start < 1.0f &&
            pair->weapon_age > definition->age_misfire_start && seed) {
            float chance = ((pair->weapon_age - definition->age_misfire_start) *
                definition->age_misfire_chance) / (1.0f - definition->age_misfire_start);
            float roll;
            if (was_spewing) chance *= 2.0f;
            roll = (float)(gun_random_seed(seed) >> 16) / 65535.0f;
            runtime->misfired = roll < chance;
        }
    }
    if (fired && pair->player_owned && definition->firing_effect_count > 0 &&
        definition->age_generated_per_round > 0.0f) {
        pair->weapon_age += definition->age_generated_per_round;
        if (pair->weapon_age > 1.0f) pair->weapon_age = 1.0f;
    }
    if (fired && definition->heat_generated_per_round > 0.0f) {
        pair->heat += definition->heat_generated_per_round;
        if (pair->heat > 1.0f) pair->heat = 1.0f;
    }
    if (!was_spewing || !fired) {
        runtime->state = fired ? GUN_TRIG_IDLE : GUN_TRIG_LOCKED;
        runtime->state_timer = fired ? 0 : -1;
        runtime->idle_ticks = 0;
    }
    runtime->released_since_shot = 0;
    return fired;
}

static int trigger_begin(gun_trigger_pair *pair,
    const gun_trigger_profile profile[GUN_TRIGGER_MAX], int index,
    unsigned busy_magazines, int trigger_count, int force, uint32_t *seed)
{
    const gun_trigger_profile *definition = &profile[index];
    gun_trigger_runtime *runtime = &pair->trigger[index];
    if (pair->overheated) return 0;
    if (!trigger_magazine_valid(definition)) return 0;
    if (definition->magazine_index != GUN_TRIGGER_NONE &&
        (busy_magazines & (1u << definition->magazine_index))) return 0;
    if (!force && definition->charging_seconds > 0.0f) {
        int fired_before_charge = 0;
        if ((pair->weapon_flags & GUN_WEAPON_CANNOT_FIRE_AT_MAXIMUM_AGE) &&
            pair->weapon_age >= 1.0f)
            return trigger_fire(pair, profile, index, seed);
        /* CE's single-trigger charged weapons with a nonzero current rate
         * discharge once when charging begins, then enter charging. For a
         * two-trigger weapon CE defers that shot to premature release. */
        /* weapon_trigger_begin_firing tests trigger->rate_of_fire (the
         * runtime fraction), not the interpolated rounds-per-second value. */
        if (trigger_count == 1 && runtime->rate_fraction > 0.0f) {
            fired_before_charge = trigger_fire(pair, profile, index, seed);
        }
        runtime->state = GUN_TRIG_CHARGING;
        runtime->state_timer = (int16_t)trigger_time_ticks(definition->charging_seconds);
        runtime->fired_before_charging = (uint8_t)fired_before_charge;
        return fired_before_charge;
    }
    return trigger_fire(pair, profile, index, seed);
}

static unsigned trigger_release_charge(gun_trigger_pair *pair,
    const gun_trigger_profile profile[GUN_TRIGGER_MAX], int count, int index,
    uint32_t *seed)
{
    gun_trigger_runtime *runtime = &pair->trigger[index];
    unsigned fired = 0;
    if (profile[index].spew_seconds > 0.0f) {
        runtime->state = GUN_TRIG_SPEWING;
        runtime->state_timer = (int16_t)trigger_time_ticks(profile[index].spew_seconds);
    } else {
        if (count > 1 && trigger_fire(pair, profile, 1, seed)) fired |= 1u << 1;
        runtime->state = GUN_TRIG_IDLE;
        runtime->state_timer = 0;
        runtime->idle_ticks = 0;
    }
    runtime->rate_fraction = 0.0f;
    return fired;
}

void gun_trigger_pair_init(gun_trigger_pair *pair, const int16_t loaded[GUN_TRIGGER_MAGAZINES])
{
    int i;
    memset(pair, 0, sizeof *pair);
    for (i = 0; i < GUN_TRIGGER_MAX; i++) {
        pair->trigger[i].state = GUN_TRIG_IDLE;
        pair->trigger[i].idle_ticks = 127;
        pair->trigger[i].released_since_shot = 1;
    }
    for (i = 0; i < GUN_TRIGGER_MAGAZINES; i++) pair->magazine_loaded[i] = loaded ? loaded[i] : 0;
}

unsigned gun_trigger_pair_tick_input_seeded(gun_trigger_pair *pair,
    const gun_trigger_profile profile[GUN_TRIGGER_MAX], int trigger_count,
    unsigned held_triggers, const float trigger_values[GUN_TRIGGER_MAX],
    unsigned busy_magazines, uint32_t *seed)
{
    unsigned fired = 0;
    int i;
    pair->detonated = 0;
    for (i = 0; i < GUN_TRIGGER_MAX; i++) pair->trigger[i].misfired = 0;
    if (pair->heat > 0.0f) {
        float heat_loss = pair->heat_loss_per_second / (float)GUN_TICKS_PER_SECOND;
        if (pair->heat >= pair->heat_overheated_threshold) pair->overheated = 1;
        if (pair->overcharged == 0.0f) {
            if (pair->age_heat_recovery_penalty > 0.0f)
                heat_loss *= 1.0f - pair->weapon_age * pair->age_heat_recovery_penalty;
            pair->heat -= heat_loss;
            if (pair->heat < 0.0f) pair->heat = 0.0f;
        }
        if (pair->overheated && pair->heat < pair->heat_recovery_threshold)
            pair->overheated = 0;
    }
    pair->overcharged = 0.0f;
    if (trigger_count < 0) trigger_count = 0;
    if (trigger_count > GUN_TRIGGER_MAX) trigger_count = GUN_TRIGGER_MAX;
    for (i = 0; i < trigger_count; i++) {
        gun_trigger_runtime *runtime = &pair->trigger[i];
        const gun_trigger_profile *definition = &profile[i];
        int held = (held_triggers & (1u << i)) != 0;
        float input_level = held ? 1.0f : 0.0f;
        if (trigger_values) {
            input_level = trigger_values[i];
            if (!(input_level > 0.0f)) input_level = 0.0f;
            if (input_level > 1.0f) input_level = 1.0f;
        }
        if (definition->flags & GUN_TRIGGER_ANALOG_RATE) held = input_level > 0.05f;
        if (runtime->state_timer > 0) runtime->state_timer--;
        if (!held) runtime->released_since_shot = 1;
        if (runtime->state == GUN_TRIG_IDLE) {
            float fraction = (definition->flags & GUN_TRIGGER_ANALOG_RATE) ?
                input_level : runtime->rate_fraction;
            float rate = (definition->rate_final - definition->rate_initial) *
                fraction + definition->rate_initial;
            float required = rate > 0.0001f ? (float)GUN_TICKS_PER_SECOND / rate : 0.0f;
            if (pair->age_rate_of_fire_penalty > 0.0f)
                required *= 1.0f + pair->weapon_age * pair->age_rate_of_fire_penalty;
            int can_fire = !((definition->flags & GUN_TRIGGER_LATCHED) &&
                !runtime->released_since_shot) &&
                (float)runtime->idle_ticks + 1.0f >= required;
            if (held && can_fire) {
                if (trigger_begin(pair, profile, i, busy_magazines,
                                  trigger_count, 0, seed))
                    fired |= 1u << i;
            } else if (runtime->idle_ticks < 127) {
                runtime->idle_ticks++;
            }
        } else if (runtime->state == GUN_TRIG_CHARGING) {
            if (runtime->state_timer == 0) {
                runtime->state = GUN_TRIG_CHARGED;
                runtime->state_timer = (int16_t)trigger_time_ticks(definition->charged_seconds);
            } else if (!held) {
                if (i == 0 && trigger_count > 1 && !runtime->fired_before_charging) {
                    if (trigger_begin(pair, profile, i, busy_magazines, trigger_count, 1, seed))
                        fired |= 1u << i;
                } else {
                    runtime->state = GUN_TRIG_IDLE;
                    runtime->state_timer = 0;
                }
            }
        } else if (runtime->state == GUN_TRIG_CHARGED) {
            int release = !held;
            if (held && definition->charged_seconds > 0.0f) {
                pair->overcharged = 1.0f -
                    ((float)runtime->state_timer / (float)GUN_TICKS_PER_SECOND) /
                    definition->charged_seconds;
                if (pair->overcharged < 0.0f) pair->overcharged = 0.0f;
            }
            if (held && runtime->state_timer == 0) {
                if (definition->overcharged_action == 1) pair->detonated = 1;
                else if (definition->overcharged_action == 2) release = 1;
            } else if (held && runtime->state_timer > 0 &&
                definition->magazine_index >= 0 &&
                definition->magazine_index < GUN_TRIGGER_MAGAZINES &&
                pair->magazine_loaded[definition->magazine_index] < definition->rounds_per_shot &&
                !(definition->flags & GUN_TRIGGER_CAN_PARTIAL)) {
                release = 1;
            }
            if (release) {
                fired |= trigger_release_charge(pair, profile, trigger_count, i, seed);
            }
        } else if (runtime->state == GUN_TRIG_SPEWING) {
            if (runtime->state_timer > 0) {
                if (trigger_begin(pair, profile, i, busy_magazines, trigger_count, 1, seed))
                    fired |= 1u << i;
            } else {
                runtime->state = GUN_TRIG_IDLE;
                runtime->idle_ticks = 0;
            }
        } else if (runtime->state == GUN_TRIG_LOCKED && !held) {
            runtime->state = GUN_TRIG_IDLE;
            runtime->state_timer = 0;
        } else if (runtime->state == GUN_TRIG_UNINITIALIZED && runtime->state_timer == 0) {
            runtime->state = GUN_TRIG_IDLE;
            runtime->state_timer = 0;
        }
        /* CE updates rate_fraction after state dispatch, so a shot on this
         * tick uses the previous fraction. Analog-rate profiles instead use
         * the scalar input level directly for this tick's cadence test. */
        if (held) {
            runtime->rate_fraction += definition->rate_acceleration;
            if (runtime->rate_fraction > 1.0f) runtime->rate_fraction = 1.0f;
        } else {
            runtime->rate_fraction -= definition->rate_deceleration;
            if (runtime->rate_fraction < 0.0f) runtime->rate_fraction = 0.0f;
        }
        /* CE ramps trigger error while firing input is held or while the
         * trigger remains in its spewing state; otherwise it recovers. */
        if (held || runtime->state == GUN_TRIG_SPEWING) {
            runtime->error_fraction += definition->error_acceleration;
            if (runtime->error_fraction > 1.0f) runtime->error_fraction = 1.0f;
        } else {
            runtime->error_fraction -= definition->error_deceleration;
            if (runtime->error_fraction < 0.0f) runtime->error_fraction = 0.0f;
        }
    }
    return fired;
}

unsigned gun_trigger_pair_tick_input(gun_trigger_pair *pair,
    const gun_trigger_profile profile[GUN_TRIGGER_MAX], int trigger_count,
    unsigned held_triggers, const float trigger_values[GUN_TRIGGER_MAX],
    unsigned busy_magazines)
{
    return gun_trigger_pair_tick_input_seeded(pair, profile, trigger_count,
        held_triggers, trigger_values, busy_magazines, NULL);
}

unsigned gun_trigger_pair_tick_seeded(gun_trigger_pair *pair,
    const gun_trigger_profile profile[GUN_TRIGGER_MAX], int trigger_count,
    unsigned held_triggers, unsigned busy_magazines, uint32_t *seed)
{
    float input[GUN_TRIGGER_MAX];
    int i;
    for (i = 0; i < GUN_TRIGGER_MAX; i++)
        input[i] = (held_triggers & (1u << i)) ? 1.0f : 0.0f;
    return gun_trigger_pair_tick_input_seeded(pair, profile, trigger_count,
        held_triggers, input, busy_magazines, seed);
}

unsigned gun_trigger_pair_tick(gun_trigger_pair *pair,
    const gun_trigger_profile profile[GUN_TRIGGER_MAX], int trigger_count,
    unsigned held_triggers, unsigned busy_magazines)
{
    return gun_trigger_pair_tick_seeded(pair, profile, trigger_count,
        held_triggers, busy_magazines, NULL);
}

unsigned gun_trigger_pair_tick_controls_seeded(gun_trigger_pair *pair,
    const gun_trigger_profile profile[GUN_TRIGGER_MAX], int trigger_count,
    int secondary_trigger_mode, uint32_t weapon_flags, float age_rate_of_fire_penalty,
    int primary_down, int secondary_down, int enabled, int dropped,
    unsigned busy_magazines, uint32_t *seed)
{
    float values[GUN_TRIGGER_MAX] = {0.0f, 0.0f};
    unsigned held = 0;
    int i;
    if (!pair || !profile || trigger_count < 0 || trigger_count > GUN_TRIGGER_MAX ||
        secondary_trigger_mode < GUN_SECONDARY_TRIGGER_NORMAL ||
        secondary_trigger_mode > GUN_SECONDARY_TRIGGER_LOADS_MULTIPLE_PRIMARY_AMMO)
        return 0;

    if (enabled) {
        values[0] = primary_down ? 1.0f : 0.0f;
        values[1] = secondary_down &&
            (weapon_flags & GUN_WEAPON_SECONDARY_TRIGGER_OVERRIDES_GRENADES) ? 1.0f : 0.0f;
    }
    pair->weapon_flags = weapon_flags;
    pair->player_owned = (uint8_t)!dropped;
    pair->age_rate_of_fire_penalty = age_rate_of_fire_penalty > 0.0f ?
        age_rate_of_fire_penalty : 0.0f;
    if (secondary_trigger_mode == GUN_SECONDARY_TRIGGER_SLAVED_TO_PRIMARY &&
        values[1] > 0.0f && trigger_count > 0 && pair->trigger[0].rate_fraction != 1.0f)
        values[1] = 0.0f;
    else if (secondary_trigger_mode == GUN_SECONDARY_TRIGGER_INHIBITS_PRIMARY &&
        values[1] > 0.0f)
        values[0] = 0.0f;

    for (i = 0; i < trigger_count; i++) {
        gun_trigger_runtime *runtime = &pair->trigger[i];
        int down = values[i] > 0.0f;
        if ((profile[i].flags & GUN_TRIGGER_STICKS_WHEN_DROPPED) && dropped)
            down = 1;
        if (profile[i].flags & GUN_TRIGGER_TOGGLES) {
            if (!runtime->was_down && down) runtime->toggled ^= 1u;
            runtime->was_down = (uint8_t)down;
            down = runtime->toggled != 0;
        } else {
            runtime->was_down = (uint8_t)down;
        }
        values[i] = down ? 1.0f : 0.0f;
        if (down) held |= 1u << i;
    }
    return gun_trigger_pair_tick_input_seeded(pair, profile, trigger_count, held,
                                       values, busy_magazines, seed);
}

unsigned gun_trigger_pair_tick_controls(gun_trigger_pair *pair,
    const gun_trigger_profile profile[GUN_TRIGGER_MAX], int trigger_count,
    int secondary_trigger_mode, uint32_t weapon_flags, float age_rate_of_fire_penalty,
    int primary_down, int secondary_down, int enabled, int dropped,
    unsigned busy_magazines)
{
    return gun_trigger_pair_tick_controls_seeded(pair, profile, trigger_count,
        secondary_trigger_mode, weapon_flags, age_rate_of_fire_penalty,
        primary_down, secondary_down, enabled, dropped, busy_magazines, NULL);
}

void gun_carrier_init(gun_carrier *carrier)
{
    int slot;
    for (slot = 0; slot < GUN_CARRIER_SLOTS; slot++) carrier->slot[slot].occupied = 0;
    carrier->current = -1;
    carrier->desired = -1;
}

int gun_carrier_pickup(gun_carrier *carrier, const gun_def *def)
{
    int slot;
    for (slot = 0; slot < GUN_CARRIER_SLOTS; slot++) {
        if (carrier->slot[slot].occupied) continue;
        carrier->slot[slot].occupied = 1;
        carrier->slot[slot].def = def;
        gun_init(&carrier->slot[slot].weapon, def);
        if (carrier->current < 0 && carrier->desired < 0) carrier->desired = slot;
        return slot;
    }
    return -1;
}

void gun_carrier_select(gun_carrier *carrier, int slot)
{
    if (slot >= 0 && slot < GUN_CARRIER_SLOTS && carrier->slot[slot].occupied)
        carrier->desired = slot;
}

int gun_carrier_tick(gun_carrier *carrier, int trigger, int reload)
{
    if (carrier->desired != carrier->current && carrier->desired >= 0) {
        gun_carry *next = &carrier->slot[carrier->desired];
        if (carrier->current >= 0) {
            gun_carry *current = &carrier->slot[carrier->current];
            gun_reset(&current->weapon, current->def);
        }
        carrier->current = carrier->desired;
        gun_reset(&next->weapon, next->def);
        next->weapon.state_timer = next->def->ready_frames;
    }
    if (carrier->current < 0) return 0;
    return gun_tick(&carrier->slot[carrier->current].weapon,
        carrier->slot[carrier->current].def, trigger, reload);
}
