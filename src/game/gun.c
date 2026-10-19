#include "game/gun.h"

const gun_def GUN_PISTOL = {
    3.5f, 1, 12, 60, 12, 35, 67, 0.0f, 1, 0, 0,
    0, 0, 0, 1, 1,
    3.5f, 1.0f, 1.0f, 0,
};

const gun_def GUN_ASSAULT_RIFLE = {
    15.0f, 1, 60, 240, 60, 29, 87, 0.0f, 1, 0, 0,
    0, 0, 0, 1, 1,
    15.0f, 0.033333335f, 0.333333343f, 0,
};

const gun_def GUN_SHOTGUN = {
    1.0f, 1, 12, 24, 1, 23, 12, 0.0f, 15, 15, 1,
    0, 0, 0, 1, 1,
    1.0f, 1.0f, 1.0f, 0,
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
    g->recharge_frac = 0;
    g->shots = 0;
    g->pellets = 0;
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

int gun_tick(gun *g, const gun_def *def, int trigger, int reload)
{
    int masked;
    int fired = 0;
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
    } else if (g->trigger == GUN_TRIG_IDLE) {
        if (def->uses_magazine && def->rounds_per_shot > 0 && g->total > 0 &&
            (((g->loaded < def->rounds_per_shot) && !def->partial_ammo) || g->loaded == 0))
            start_reload(g, def, 1);
        if (!masked && trigger && can_fire(g, def)) {
            if (def->uses_magazine && def->rounds_per_shot > 0) {
                g->loaded = (int16_t)(g->loaded - def->rounds_per_shot);
                /* An emptying shot does not chamber. The next tick reloads. */
                if (g->loaded <= 0) g->loaded = 0;
                else if (def->chamber_every_shot) {
                    g->magazine = GUN_MAG_UNCHAMBERED;
                    g->magazine_timer = 0;
                }
            }
            g->released = 0;
            g->idle_ticks = 0;
            g->shots++;
            g->pellets += (uint32_t)def->projectiles_per_shot;
            fired = 1;
        } else if (g->idle_ticks < 127) {
            g->idle_ticks++;
        }
    }
    if (trigger) {
        g->fraction += def->rate_accel;
        if (g->fraction > 1.0f) g->fraction = 1.0f;
    } else {
        g->fraction -= def->rate_decel;
        if (g->fraction < 0.0f) g->fraction = 0.0f;
    }
    return fired;
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
