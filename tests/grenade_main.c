#include "game/grenade.h"
#include "game/vital.h"
#include <stdio.h>

static void floor_rest(const grenade_def *def, const char *name, int unit, const float aim[3])
{
    grenade g;
    grenade_surface surface;
    int carried = GRENADE_CARRY_MAX;
    uint32_t seed = 0x12345678u;
    float origin[3] = {0, 0, 1};
    int ticks = 0;
    surface.normal[0] = 0;
    surface.normal[1] = 0;
    surface.normal[2] = 1;
    surface.d = 0;
    surface.material = 0;
    surface.unit_surface = unit;
    grenade_throw(&g, def, origin, aim, &carried, &seed);
    while (!g.resting && g.alive && ticks < 400) {
        grenade_tick_on(&g, def, &surface, &seed);
        ticks++;
    }
    printf("%s_rest %d %d %.4f %.4f %d %08x\n",
        name, ticks, g.bounces, g.position[0], g.position[2], g.resting, seed);
    if (g.resting) {
        int fuse = 0;
        while (fuse < 80 && g.alive && !grenade_tick(&g)) fuse++;
        printf("%s_after %d\n", name, fuse + 1);
    }
}

static int fuse_ticks(const grenade_def *def)
{
    grenade g;
    int carried = GRENADE_CARRY_MAX;
    uint32_t seed = 1;
    float origin[3] = {0, 0, 0};
    float aim[3] = {1, 0, 0};
    int ticks = 0;
    grenade_throw(&g, def, origin, aim, &carried, &seed);
    grenade_rest(&g);
    while (ticks < 80 && !grenade_tick(&g)) ticks++;
    return ticks + 1;
}

int main(void)
{
    grenade g;
    vital v;
    int carried = GRENADE_CARRY_MAX;
    uint32_t seed = 0x12345678u;
    float origin[3] = {0, 0, 1};
    float aim[3] = {1, 0, 0};
    int i, air = 0;
    grenade_throw(&g, &GRENADE_FRAG, origin, aim, &carried, &seed);
    grenade_tick(&g);
    printf("throw %d %.9f %.9f %08x\n", carried, g.position[0], g.position[2], seed);
    for (i = 0; i < 40; i++) air += grenade_tick(&g);
    printf("air %d\n", air);
    printf("frag_fuse %d\n", fuse_ticks(&GRENADE_FRAG));
    printf("plasma_fuse %d\n", fuse_ticks(&GRENADE_PLASMA));
    seed = 0x12345678u;
    printf("blast0 %.1f\n", grenade_damage(&GRENADE_FRAG, 0.0f, &seed));
    printf("blast_seed %08x\n", seed);
    printf("blast2 %.1f\n", grenade_damage(&GRENADE_FRAG, 2.0f, &seed));
    printf("blast_far %.1f\n", grenade_damage(&GRENADE_FRAG, 2.5f, &seed));
    vital_init(&v);
    vital_hurt(&v, grenade_damage(&GRENADE_FRAG, 0.0f, &seed), VITAL_BODY, 1.0f, 0);
    printf("blast_body %.4f %d\n", v.body, v.dead);
    vital_hurt(&v, grenade_damage(&GRENADE_FRAG, 0.0f, &seed), VITAL_BODY, 1.0f, 0);
    printf("blast_second %d\n", v.dead);
    while (carried > 0) grenade_throw(&g, &GRENADE_FRAG, origin, aim, &carried, &seed);
    {
        float across[3] = {1, 0, 0};
        float down[3] = {0, 0, -1};
        floor_rest(&GRENADE_FRAG, "frag", 0, across);
        floor_rest(&GRENADE_PLASMA, "plasma", 0, across);
        floor_rest(&GRENADE_PLASMA, "stick", 1, down);
    }
    printf("empty %d %d\n", carried, grenade_throw(&g, &GRENADE_FRAG, origin, aim, &carried, &seed));
    return 0;
}
