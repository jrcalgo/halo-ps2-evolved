#include "game/gun.h"
#include <stdio.h>

static void hold(const gun_def *def, int ticks, const char *name)
{
    gun g;
    int i, n = 0;
    gun_init(&g, def);
    printf("%s loaded %d total %d\n", name, g.loaded, g.total);
    for (i = 0; i < ticks; i++) if (gun_tick(&g, def, 1, 0)) n++;
    printf("%s shots %d loaded %d idle %u\n", name, n, g.loaded, g.idle_ticks);
}

static void empty_reload(const gun_def *def, const char *name)
{
    gun g;
    int tick = 0, last = -1, gap = -1;
    gun_init(&g, def);
    while (tick < 800 && gap < 0) {
        int before = g.loaded;
        int shot = gun_tick(&g, def, 1, 0);
        if (before == 0 && g.loaded > 0)
            printf("%s reload_ticks %d loaded %d total %d\n",
                name, tick - last, g.loaded, g.total);
        if (shot) {
            if (g.shots == (uint32_t)def->rounds_loaded_maximum + 1) gap = tick - last;
            last = tick;
        }
        tick++;
    }
    printf("%s refire %d\n", name, gap);
}

static void ready_shot(const gun_def *def, const char *name)
{
    gun_carrier carrier;
    int tick, shot = -1;
    gun_carrier_init(&carrier);
    gun_carrier_pickup(&carrier, def);
    for (tick = 0; tick < 80 && shot < 0; tick++)
        if (gun_carrier_tick(&carrier, 1, 0)) shot = tick;
    printf("%s ready_shot %d\n", name, shot);
}

static void switch_to_pistol(void)
{
    gun_carrier carrier;
    int tick, armed = -1, gap = -1;
    gun_carrier_init(&carrier);
    gun_carrier_pickup(&carrier, &GUN_ASSAULT_RIFLE);
    gun_carrier_pickup(&carrier, &GUN_PISTOL);
    for (tick = 0; tick < 160 && gap < 0; tick++) {
        if (armed < 0 && carrier.slot[0].weapon.shots > 0) {
            gun_carrier_select(&carrier, 1);
            armed = tick;
        }
        if (gun_carrier_tick(&carrier, 1, 0) && armed >= 0 && carrier.current == 1)
            gap = tick - armed;
    }
    printf("switch_gap %d\n", gap);
}

static void overflow(void)
{
    gun_carrier carrier;
    int slot;
    gun_carrier_init(&carrier);
    gun_carrier_pickup(&carrier, &GUN_PISTOL);
    gun_carrier_pickup(&carrier, &GUN_PISTOL);
    gun_carrier_pickup(&carrier, &GUN_PISTOL);
    gun_carrier_pickup(&carrier, &GUN_PISTOL);
    slot = gun_carrier_pickup(&carrier, &GUN_PISTOL);
    printf("overflow %d\n", slot);
}

static void shotgun(void)
{
    gun g;
    int tick, first = -1, full = -1, fired = -1;
    gun_init(&g, &GUN_SHOTGUN);
    printf("shotgun loaded %d total %d\n", g.loaded, g.total);
    for (tick = 0; tick < 31; tick++) gun_tick(&g, &GUN_SHOTGUN, 1, 0);
    printf("shotgun shots %u pellets %u loaded %d\n", g.shots, g.pellets, g.loaded);
    gun_init(&g, &GUN_SHOTGUN);
    g.loaded = 0;
    for (tick = 0; tick < 200 && full < 0; tick++) {
        int before = g.loaded;
        gun_tick(&g, &GUN_SHOTGUN, 0, tick == 0);
        if (first < 0 && before == 0 && g.loaded == 1) first = tick;
        if (g.loaded == 12) full = tick;
    }
    printf("shotgun shells %d %d total %d\n", first, full, g.total);
    gun_init(&g, &GUN_SHOTGUN);
    g.loaded = 0;
    g.idle_ticks = 127;
    for (tick = 0; tick < 40 && fired < 0; tick++)
        if (gun_tick(&g, &GUN_SHOTGUN, 1, 0)) fired = tick;
    printf("shotgun held %d pellets %u loaded %d\n", fired, g.pellets, g.loaded);
}

/* Blood Gulch magazines beyond the pistol, rifle, and shotgun. */
static const gun_def GUN_FLAMETHROWER = {
    15.0f, 1, 100, 600, 100, 30, 104, 0.0f, 1, 0, 0,
    1, 0, 0, 1, 1,
    15.0f, 0.166666672f, 1.0f, 0, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f,
    0.0f, 0.0f, 0.0f, 1,
    0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0, 0, 0, {{{0, 0}, {0, 0}}, {{0, 0}, {0, 0}}},
};

static const gun_def GUN_ROCKET = {
    0.5f, 1, 2, 4, 2, 22, 125, 0.0f, 1, 0, 0,
    0, 0, 1, 1, 1,
    0.5f, 1.0f, 1.0f, 0, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f,
    0.0f, 0.0f, 0.0f, 1,
    0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0, 0, 0, {{{0, 0}, {0, 0}}, {{0, 0}, {0, 0}}},
};

static const gun_def GUN_SNIPER = {
    2.0f, 1, 4, 12, 4, 29, 94, 0.0f, 1, 0, 0,
    0, 0, 1, 1, 1,
    2.0f, 1.0f, 1.0f, 0, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f,
    0.0f, 0.0f, 0.0f, 1,
    0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0, 0, 0, {{{0, 0}, {0, 0}}, {{0, 0}, {0, 0}}},
};

static const gun_def GUN_NEEDLER = {
    3.0f, 1, 20, 80, 20, 23, 70, 0.0f, 1, 0, 0,
    0, 0, 0, 1, 1,
    10.0f, 0.0666666701f, 0.222222224f, 0, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f,
    0.0f, 0.0f, 0.0f, 1,
    0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0, 0, 0, {{{0, 0}, {0, 0}}, {{0, 0}, {0, 0}}},
};

static const gun_def GUN_GRAVITY = {
    30.0f, 1, 200, 200, 200, 0, 0, 0.0f, 1, 0, 0,
    0, 0, 0, 1, 1,
    30.0f, 1.0f, 1.0f, 0, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f,
    0.0f, 0.0f, 0.0f, 1,
    0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0, 0, 0, {{{0, 0}, {0, 0}}, {{0, 0}, {0, 0}}},
};

static const gun_def GUN_FUEL_ROD = {
    10.0f, 0, 4, 12, 4, 0, 0, 0.0f, 1, 0, 0,
    0, 0, 1, 1, 1,
    10.0f, 1.0f, 1.0f, 0, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f,
    0.0f, 0.0f, 0.0f, 1,
    0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0, 0, 0, {{{0, 0}, {0, 0}}, {{0, 0}, {0, 0}}},
};

static const gun_def GUN_SCORPION = {
    0.0f, 1, 1, 9999, 1, 0, 0, 4.0f, 1, 0, 1,
    0, 0, 1, 1, 1,
    0.0f, 1.0f, 1.0f, 0, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f,
    0.0f, 0.0f, 0.0f, 1,
    0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0, 0, 0, {{{0, 0}, {0, 0}}, {{0, 0}, {0, 0}}},
};

static void flame_waste(void)
{
    gun g;
    int tick, reported = 0;
    gun_init(&g, &GUN_FLAMETHROWER);
    printf("flame loaded %d total %d\n", g.loaded, g.total);
    g.loaded = 40;
    for (tick = 0; tick < 200 && !reported; tick++) {
        int before = g.loaded;
        gun_tick(&g, &GUN_FLAMETHROWER, 0, tick == 0);
        if (before != 100 && g.loaded == 100) {
            printf("flame waste %d total %d\n", tick, g.total);
            reported = 1;
        }
    }
}

static void needler_reload(void)
{
    gun g;
    int tick, twentieth = -1, next = -1;
    gun_init(&g, &GUN_NEEDLER);
    printf("needler loaded %d total %d\n", g.loaded, g.total);
    for (tick = 0; tick < 250 && next < 0; tick++) {
        if (!gun_tick(&g, &GUN_NEEDLER, 1, 0)) continue;
        if (g.shots == 20) twentieth = tick;
        if (g.shots == 21) next = tick;
    }
    printf("needler shots %d %d loaded %d total %d\n", twentieth, next, g.loaded, g.total);
}

static void scorpion_chamber(void)
{
    gun g;
    int tick, second = -1;
    gun_init(&g, &GUN_SCORPION);
    printf("scorpion loaded %d total %d\n", g.loaded, g.total);
    for (tick = 0; tick < 200 && second < 0; tick++) {
        if (!gun_tick(&g, &GUN_SCORPION, tick != 1, 0)) continue;
        if (g.shots == 2) second = tick;
    }
    printf("scorpion second %d loaded %d total %d\n", second, g.loaded, g.total);
}

static void runtime_error(void)
{
    gun g;
    gun_def def = GUN_PISTOL;
    int fired;
    def.error_accel = 0.06666667014360428f;
    def.error_decel = 0.1666666716337204f;
    gun_init(&g, &def);
    fired = gun_tick(&g, &def, 1, 0);
    printf("error shot %d used %.8f next %.8f\n", fired,
        g.shot_error_fraction, g.error_fraction);
    (void)gun_tick(&g, &def, 0, 0);
    printf("error recover used %.8f next %.8f\n",
        g.shot_error_fraction, g.error_fraction);
}

static void charge_and_heat(void)
{
    gun charge_gun, single_charge_gun, single_charge_zero, heat_gun;
    gun_def charge_def = GUN_PISTOL, single_charge_def = GUN_PISTOL;
    gun_def heat_def = GUN_ASSAULT_RIFLE;
    int tick, fired_tick = -1, overheats = 0, was_overheated = 0;
    charge_def.uses_magazine = 0;
    charge_def.rounds_per_shot = 0;
    charge_def.trigger_count = 2;
    charge_def.charge_seconds = 0.6f;
    charge_def.charged_seconds = 45.0f;
    charge_def.heat_per_round = 0.16f;
    charge_def.heat_loss = 0.65f;
    gun_init(&charge_gun, &charge_def);
    for (tick = 0; tick < 40; ++tick)
        if (gun_tick(&charge_gun, &charge_def, 1, 0)) fired_tick = tick;
    if (gun_tick(&charge_gun, &charge_def, 0, 0)) fired_tick = 40;

    single_charge_def.uses_magazine = 0;
    single_charge_def.rounds_per_shot = 0;
    single_charge_def.trigger_count = 1;
    single_charge_def.charge_seconds = 0.6f;
    gun_init(&single_charge_zero, &single_charge_def);
    if (gun_tick(&single_charge_zero, &single_charge_def, 1, 0) ||
        single_charge_zero.shots != 0 ||
        single_charge_zero.trigger != GUN_TRIG_CHARGING) {
        fprintf(stderr, "zero trigger rate fraction fired at charge start\n");
        return;
    }
    gun_init(&single_charge_gun, &single_charge_def);
    /* CE checks the trigger's existing runtime rate fraction here, not the
     * tag's interpolated initial rounds-per-second value. */
    single_charge_gun.fraction = 0.5f;
    if (!gun_tick(&single_charge_gun, &single_charge_def, 1, 0) ||
        single_charge_gun.shots != 1 ||
        single_charge_gun.trigger != GUN_TRIG_CHARGING) {
        fprintf(stderr, "single trigger did not fire at charge start\n");
        return;
    }
    for (tick = 0; tick < 3; ++tick)
        if (gun_tick(&single_charge_gun, &single_charge_def, 1, 0)) {
            fprintf(stderr, "single trigger fired twice while charging\n");
            return;
        }
    if (gun_tick(&single_charge_gun, &single_charge_def, 0, 0) ||
        single_charge_gun.shots != 1) {
        fprintf(stderr, "single trigger early release duplicated charge shot\n");
        return;
    }

    heat_def.uses_magazine = 0;
    heat_def.rounds_per_shot = 0;
    heat_def.heat_overheat = 0.8f;
    heat_def.heat_recovery = 0.7f;
    heat_def.heat_loss = 0.3f;
    heat_def.heat_per_round = 0.08f;
    gun_init(&heat_gun, &heat_def);
    for (tick = 0; tick < 120; ++tick) {
        (void)gun_tick(&heat_gun, &heat_def, 1, 0);
        if (heat_gun.overheated && !was_overheated) ++overheats;
        was_overheated = heat_gun.overheated;
    }
    printf("charge release tick=%d shots=%u heat=%.2f\n",
        fired_tick, charge_gun.shots, charge_gun.heat);
    printf("single charge start shots=%u\n", single_charge_gun.shots);
    printf("heat rifle shots=%u overheat_events=%d heat=%.2f\n",
        heat_gun.shots, overheats, heat_gun.heat);
}

int main(void)
{
    hold(&GUN_ASSAULT_RIFLE, 30, "ar");
    hold(&GUN_PISTOL, 30, "pistol");
    empty_reload(&GUN_ASSAULT_RIFLE, "ar");
    empty_reload(&GUN_PISTOL, "pistol");
    ready_shot(&GUN_ASSAULT_RIFLE, "ar");
    ready_shot(&GUN_PISTOL, "pistol");
    switch_to_pistol();
    overflow();
    shotgun();
    flame_waste();
    hold(&GUN_ROCKET, 90, "rocket");
    hold(&GUN_SNIPER, 90, "sniper");
    needler_reload();
    hold(&GUN_GRAVITY, 200, "gravity");
    hold(&GUN_FUEL_ROD, 30, "fuel");
    scorpion_chamber();
    runtime_error();
    charge_and_heat();
    {
        gun_def effect_def = GUN_PISTOL;
        gun effect_gun;
        uint32_t seed = 12345u;
        effect_def.uses_magazine = 0;
        effect_def.rate_final = 30.0f;
        effect_def.firing_effect_count = 2;
        effect_def.trigger_flags = GUN_TRIGGER_RANDOM_FIRING_EFFECTS;
        effect_def.firing_effect_shots[0][0][0] = 2;
        effect_def.firing_effect_shots[0][0][1] = 3;
        effect_def.firing_effect_shots[0][1][0] = 3;
        effect_def.firing_effect_shots[0][1][1] = 4;
        effect_def.age_misfire_start = 0.9f;
        effect_def.age_misfire_chance = 0.5f;
        gun_init(&effect_gun, &effect_def);
        effect_gun.age = 0.95f;
        if (!gun_tick_seeded(&effect_gun, &effect_def, 1, 0, &seed)) return 1;
        if (
            effect_gun.last_firing_effect != 0 ||
            effect_gun.firing_effect_shots_remaining != 1 ||
            effect_gun.misfired || seed != 2332836374u) {
            fprintf(stderr, "CE firing-effect/misfire RNG first draw mismatch\n");
            return 1;
        }
        effect_gun.idle_ticks = 127;
        if (!gun_tick_seeded(&effect_gun, &effect_def, 1, 0, &seed) ||
            effect_gun.last_firing_effect != 0 ||
            effect_gun.firing_effect_shots_remaining != 0 ||
            effect_gun.misfired || seed != 2726892157u) {
            fprintf(stderr, "CE retained firing-effect count/RNG mismatch\n");
            return 1;
        }
        printf("seeded firing effect=%d remaining=%d seed=%u\n",
            effect_gun.last_firing_effect, effect_gun.firing_effect_shots_remaining, seed);
    }
    {
        gun_def misfire_def = GUN_PISTOL;
        gun misfire_gun;
        uint32_t seed = 8u;
        misfire_def.uses_magazine = 0;
        misfire_def.rate_final = 30.0f;
        misfire_def.firing_effect_count = 1;
        misfire_def.firing_effect_shots[0][0][0] = 1;
        misfire_def.firing_effect_shots[0][0][1] = 1;
        misfire_def.age_generated_per_round = 0.01f;
        misfire_def.age_misfire_start = 0.9f;
        misfire_def.age_misfire_chance = 0.5f;
        gun_init(&misfire_gun, &misfire_def);
        misfire_gun.age = 0.95f;
        if (!gun_tick_seeded(&misfire_gun, &misfire_def, 1, 0, &seed) ||
            !misfire_gun.misfired || misfire_gun.shots != 1 ||
            misfire_gun.age != 0.96f || seed != 18026106u) {
            fprintf(stderr, "CE age-misfire firing commit mismatch\n");
            return 1;
        }
        printf("seeded age misfire committed shot=%u age=%.2f seed=%u\n",
            misfire_gun.shots, misfire_gun.age, seed);
    }
    {
        gun_trigger_profile heat_profile[GUN_TRIGGER_MAX] = {{0}};
        gun_trigger_pair heat_pair;
        int16_t loaded[GUN_TRIGGER_MAGAZINES] = {0, 0};
        heat_profile[0].magazine_index = GUN_TRIGGER_NONE;
        heat_profile[0].rate_initial = 30.0f;
        heat_profile[0].rate_final = 30.0f;
        heat_profile[0].heat_generated_per_round = 0.1f;
        gun_trigger_pair_init(&heat_pair, loaded);
        heat_pair.player_owned = 1;
        heat_pair.heat = 0.79f;
        heat_pair.heat_overheated_threshold = 0.8f;
        heat_pair.heat_recovery_threshold = 0.6f;
        heat_pair.heat_loss_per_second = 0.3f;
        heat_pair.overcharged = 0.5f;
        if (gun_trigger_pair_tick(&heat_pair, heat_profile, 1, 1u, 0) != 1u ||
            heat_pair.heat < 0.889f || heat_pair.heat > 0.891f || heat_pair.overheated ||
            gun_trigger_pair_tick(&heat_pair, heat_profile, 1, 1u, 0) != 0u ||
            heat_pair.heat < 0.879f || heat_pair.heat > 0.881f || !heat_pair.overheated)
            return 1;
        printf("trigger-pair heat threshold=%.2f overheated=%u\n",
            heat_pair.heat, heat_pair.overheated);
    }
    return 0;
}
