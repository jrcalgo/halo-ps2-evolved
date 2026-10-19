#include "game/arsenal.h"
#include <string.h>

#define ARS_IDLE 0
#define ARS_CHARGING 1
#define ARS_CHARGED 2
#define ARS_RELOAD 3
#define ARS_UNCHAMBERED 4
#define ARS_CHAMBERING 5
#define ARS_LATCHED 8u
#define ARS_ACTION_EXPLODE 1
#define ARS_ACTION_FIRE 2

static int trunc30(float seconds)
{
    float ticks = seconds * 30.0f;
    if (ticks <= 0.0f) return 0;
    if (ticks > 32767.0f) return 32767;
    return (int)ticks;
}

static int ammo_ok(const arsenal_spec *spec, int loaded)
{
    int need = spec->rounds_per_shot[0];
    if (spec->magazine_index[0] < 0 || need <= 0) return 1;
    return loaded >= need;
}

static void spend(const arsenal_spec *spec, int *loaded)
{
    int need = spec->rounds_per_shot[0];
    if (spec->magazine_index[0] < 0 || need <= 0) return;
    *loaded -= need;
    if (*loaded < 0) *loaded = 0;
}

static float required_ticks(const arsenal_spec *spec, float fraction)
{
    float rate = (spec->rate_final[0] - spec->rate_initial[0]) * fraction + spec->rate_initial[0];
    if (rate <= 0.0001f) return 0.0f;
    return 30.0f / rate;
}

void arsenal_run(const arsenal_spec *spec, int ticks, arsenal_result *out)
{
    int loaded = spec->initial_rounds < spec->loaded_max ? spec->initial_rounds : spec->loaded_max;
    int total = spec->initial_rounds - loaded;
    int idle = 127;
    int state = ARS_IDLE;
    int timer = 0;
    int mag = ARS_IDLE;
    int mag_timer = 0;
    float fraction = 0.0f;
    float heat = 0.0f;
    int overheated = 0;
    int released = 1;
    int tick;
    if (spec->loaded_max <= 0) {
        loaded = 0;
        total = 0;
    }
    memset(out, 0, sizeof *out);
    out->melee = spec->trigger_count == 0 ? spec->melee_damage : 0.0f;
    if (spec->trigger_count <= 0) {
        out->loaded = loaded;
        return;
    }
    for (tick = 0; tick < ticks; tick++) {
        int held = 1;
        int fired = 0;
        float loss;
        if (spec->mode == ARSENAL_RELEASE && tick >= 40) held = 0;
        if (heat > 0.0f && state != ARS_CHARGED) {
            loss = spec->heat_loss / 30.0f;
            heat -= loss;
            if (heat < 0.0f) heat = 0.0f;
        }
        if (heat >= spec->heat_overheat && spec->heat_overheat > 0.0f && !overheated)
            overheated = 1;
        if (overheated && heat < spec->heat_recovery) overheated = 0;
        if (mag_timer > 0) mag_timer--;
        if (mag == ARS_RELOAD) {
            if (mag_timer - 1 <= 0) {
                int take = spec->rounds_reloaded;
                if (take > total) take = total;
                loaded += take;
                if (loaded > spec->loaded_max) loaded = spec->loaded_max;
                total -= take;
                if (total < 0) total = 0;
                mag = ARS_IDLE;
                mag_timer = 0;
            }
        } else if (mag == ARS_UNCHAMBERED) {
            mag = ARS_CHAMBERING;
            mag_timer = 0;
        } else if (mag == ARS_CHAMBERING && mag_timer == 0) {
            mag = ARS_IDLE;
        }
        if (timer > 0) timer--;
        if (!held) released = 1;
        if (state == ARS_IDLE) {
            int latched = (spec->flags[0] & ARS_LATCHED) != 0;
            int ready = (float)idle + 1.0f >= required_ticks(spec, fraction);
            if (latched && !released) ready = 0;
            if (loaded < spec->rounds_per_shot[0] && spec->rounds_per_shot[0] > 0 &&
                spec->magazine_index[0] >= 0 && total > 0 && spec->reload_frames > 0 &&
                mag == ARS_IDLE) {
                mag = ARS_RELOAD;
                mag_timer = spec->weapon_type == 1 && spec->enter_frames > 0
                    ? spec->enter_frames : spec->reload_frames;
            } else if (held && mag == ARS_IDLE && !overheated && ready && ammo_ok(spec, loaded)) {
                if (spec->charge[0] > 0.0f) {
                    if (fraction > 0.0f) {
                        spend(spec, &loaded);
                        heat += spec->heat_per_round[0];
                        if (heat > 1.0f) heat = 1.0f;
                        idle = 0;
                        released = 0;
                        fired = 1;
                    }
                    state = ARS_CHARGING;
                    timer = trunc30(spec->charge[0]);
                } else {
                    spend(spec, &loaded);
                    if (loaded > 0 && (spec->magazine_flags & 2)) mag = ARS_UNCHAMBERED;
                    heat += spec->heat_per_round[0];
                    if (heat > 1.0f) heat = 1.0f;
                    idle = 0;
                    released = 0;
                    fired = 1;
                }
            } else if (idle < 127) {
                idle++;
            }
        } else if (state == ARS_CHARGING) {
            if (timer == 0) {
                state = ARS_CHARGED;
                timer = trunc30(spec->charged[0]);
            } else if (!held) {
                if (spec->trigger_count > 1) {
                    spend(spec, &loaded);
                    heat += spec->heat_per_round[0];
                    if (heat > 1.0f) heat = 1.0f;
                    idle = 0;
                    fired = 1;
                }
                state = ARS_IDLE;
                fraction = 0.0f;
            }
        } else if (state == ARS_CHARGED) {
            if (held && timer == 0) {
                if (spec->overcharge_action[0] == ARS_ACTION_FIRE && ammo_ok(spec, loaded)) {
                    spend(spec, &loaded);
                    heat += spec->heat_per_round[0];
                    if (heat > 1.0f) heat = 1.0f;
                    idle = 0;
                    released = 0;
                    fired = 1;
                }
                state = ARS_IDLE;
            } else if (!held) {
                if (ammo_ok(spec, loaded)) {
                    spend(spec, &loaded);
                    heat += spec->heat_per_round[0];
                    if (heat > 1.0f) heat = 1.0f;
                    idle = 0;
                    fired = 1;
                }
                state = ARS_IDLE;
                fraction = 0.0f;
            }
        }
        if (fired && out->tick_count < 128) out->ticks[out->tick_count++] = tick;
        if (fired) {
            out->shots++;
            out->pellets += spec->pellets[0] > 0 ? spec->pellets[0] : 1;
        }
        if (held) {
            fraction += spec->rate_accel[0];
            if (fraction > 1.0f) fraction = 1.0f;
        } else {
            fraction -= spec->rate_decel[0];
            if (fraction < 0.0f) fraction = 0.0f;
        }
    }
    out->overheated = overheated;
    out->loaded = loaded;
    out->heat = heat;
}
