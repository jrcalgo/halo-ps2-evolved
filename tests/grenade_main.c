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

static void simultaneous_frag_stress(void)
{
    enum { COUNT = 8 };
    grenade blasts[COUNT];
    vital target;
    int carried = COUNT, exploded = 0, tick, i;
    uint32_t seed = 0x31415926u;
    const float origin[3] = {0, 0, 0};
    const float aim[3] = {1, 0, 0};

    vital_init(&target);
    for (i = 0; i < COUNT; ++i) {
        if (!grenade_throw(&blasts[i], &GRENADE_FRAG, origin, aim, &carried, &seed))
            return;
        grenade_rest(&blasts[i]);
    }
    for (tick = 0; tick < 20 && exploded < COUNT; ++tick) {
        for (i = 0; i < COUNT; ++i) {
            if (blasts[i].alive && grenade_tick(&blasts[i])) {
                float damage = grenade_damage(&GRENADE_FRAG, 0.0f, &seed);
                vital_hurt(&target, damage, VITAL_BODY, 1.0f, 0);
                ++exploded;
            }
        }
    }
    printf("simultaneous %d %d %d %.3f %.3f %d %08x\n", exploded,
        tick, carried, target.shield, target.body, target.dead, seed);
}

int main(void)
{
    grenade g;
    vital v;
    int carried = GRENADE_CARRY_MAX;
    uint32_t seed = 0x12345678u;
    float origin[3] = {0, 0, 1};
    float aim[3] = {1, 0, 0};
    int i, air = 0, plasma;
    grenade_throw(&g, &GRENADE_FRAG, origin, aim, &carried, &seed);
    grenade_tick(&g);
    printf("throw %d %.9f %.9f %08x\n", carried, g.position[0], g.position[2], seed);
    for (i = 0; i < 40; i++) air += grenade_tick(&g);
    printf("air %d\n", air);
    printf("frag_fuse %d\n", fuse_ticks(&GRENADE_FRAG));
    printf("plasma_fuse %d\n", fuse_ticks(&GRENADE_PLASMA));
    printf("blast_material %.1f %.1f %.1f %.1f\n",
        GRENADE_FRAG.damage_material_modifier_21,
        GRENADE_FRAG.damage_material_modifier_22,
        GRENADE_PLASMA.damage_material_modifier_21,
        GRENADE_PLASMA.damage_material_modifier_22);
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
    simultaneous_frag_stress();
    printf("empty %d %d\n", carried, grenade_throw(&g, &GRENADE_FRAG, origin, aim, &carried, &seed));
    for (plasma = 0; plasma < 2; ++plasma) {
        for (i = 0; i < 33; ++i) {
            grenade_material_profile profile;
            if (grenade_material_profile_get(plasma, i, &profile))
                printf("material %d %d %d %d %d %.9f %.9f %.9f %.9f %.9f %.9f %.9f\n",
                    plasma, i, profile.response, profile.potential_response,
                    profile.potential_flags, profile.potential_skip_fraction,
                    profile.potential_angle_lower_bound, profile.potential_angle_upper_bound,
                    profile.potential_velocity_lower_bound,
                    profile.potential_velocity_upper_bound, profile.parallel_friction,
                    profile.perpendicular_friction);
        }
    }
    return 0;
}
