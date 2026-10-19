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
    15.0f, 0.166666672f, 1.0f, 0,
};

static const gun_def GUN_ROCKET = {
    0.5f, 1, 2, 4, 2, 22, 125, 0.0f, 1, 0, 0,
    0, 0, 1, 1, 1,
    0.5f, 1.0f, 1.0f, 0,
};

static const gun_def GUN_SNIPER = {
    2.0f, 1, 4, 12, 4, 29, 94, 0.0f, 1, 0, 0,
    0, 0, 1, 1, 1,
    2.0f, 1.0f, 1.0f, 0,
};

static const gun_def GUN_NEEDLER = {
    3.0f, 1, 20, 80, 20, 23, 70, 0.0f, 1, 0, 0,
    0, 0, 0, 1, 1,
    10.0f, 0.0666666701f, 0.222222224f, 0,
};

static const gun_def GUN_GRAVITY = {
    30.0f, 1, 200, 200, 200, 0, 0, 0.0f, 1, 0, 0,
    0, 0, 0, 1, 1,
    30.0f, 1.0f, 1.0f, 0,
};

static const gun_def GUN_FUEL_ROD = {
    10.0f, 0, 4, 12, 4, 0, 0, 0.0f, 1, 0, 0,
    0, 0, 1, 1, 1,
    10.0f, 1.0f, 1.0f, 0,
};

static const gun_def GUN_SCORPION = {
    0.0f, 1, 1, 9999, 1, 0, 0, 4.0f, 1, 0, 1,
    0, 0, 1, 1, 1,
    0.0f, 1.0f, 1.0f, 0,
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
    return 0;
}
