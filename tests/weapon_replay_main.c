#include "game/gun.h"
#include "game/grenade.h"
#include "game/shot.h"
#include "game/vital.h"

#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static uint32_t mix(uint32_t hash, uint32_t value)
{
    int i;
    for (i = 0; i < 4; ++i) {
        hash ^= (value >> (i * 8)) & 255u;
        hash *= 16777619u;
    }
    return hash;
}

static uint32_t float_bits(float value)
{
    uint32_t bits;
    memcpy(&bits, &value, sizeof bits);
    return bits;
}

int main(int argc, char **argv)
{
    gun weapon;
    vital target;
    grenade frag;
    shot_scene scene = {0};
    float origin[3] = {0, 0, 0};
    float forward[3] = {1, 0, 0};
    uint32_t seed = 1, state_hash = 2166136261u, presentation_hash = 2166136261u;
    volatile uint32_t presentation_work = 0;
    unsigned presentations, tick, fired = 0, hits = 0;
    int frag_carried = 1, frag_thrown = 0, frag_exploded = 0;
    if (argc != 2) return 2;
    presentations = (unsigned)strtoul(argv[1], 0, 10);
    gun_init(&weapon, &GUN_PISTOL);
    vital_init(&target);
    scene.target = 1;
    scene.target_center[0] = 5.0f;
    scene.target_radius = 0.5f;
    memset(&frag, 0, sizeof frag);
    for (tick = 0; tick < 180; ++tick) {
        int trigger = tick % 12u == 0;
        if (tick == 60 && !frag_thrown) {
            const float grenade_origin[3] = {0.0f, 0.0f, 0.0f};
            const float grenade_aim[3] = {1.0f, 0.0f, 0.0f};
            frag_thrown = grenade_throw(&frag, &GRENADE_FRAG,
                grenade_origin, grenade_aim, &frag_carried, &seed);
            grenade_rest(&frag);
        }
        if (frag.alive && grenade_tick(&frag)) {
            float damage = grenade_damage(&GRENADE_FRAG, 0.0f, &seed);
            vital_hurt(&target, damage, VITAL_BODY, 1.0f, 0);
            ++frag_exploded;
        }
        if (gun_tick(&weapon, &GUN_PISTOL, trigger, 0)) {
            shot projectile;
            ++fired;
            shot_spawn(&projectile, origin, forward, &SHOT_PISTOL);
            (void)shot_tick(&projectile, &SHOT_PISTOL, &scene, &seed);
            if (projectile.hit_object) {
                ++hits;
                vital_hurt(&target, projectile.damage, VITAL_BODY, 1.0f, 0);
            }
        }
        state_hash = mix(state_hash, (uint32_t)weapon.loaded);
        state_hash = mix(state_hash, float_bits(target.shield));
        state_hash = mix(state_hash, float_bits(target.body));
        state_hash = mix(state_hash, (uint32_t)target.dead);
        state_hash = mix(state_hash, seed);
        state_hash = mix(state_hash, fired);
        state_hash = mix(state_hash, hits);
        state_hash = mix(state_hash, (uint32_t)frag.alive);
        state_hash = mix(state_hash, (uint32_t)frag.exploded);
        state_hash = mix(state_hash, float_bits(frag.timer));
        state_hash = mix(state_hash, frag_exploded);
        for (unsigned i = 0; i < presentations; ++i) {
            presentation_work = presentation_work * 1664525u + tick + i + 1013904223u;
            presentation_hash = mix(presentation_hash, presentation_work);
        }
    }
    printf("state=%08x presentation=%08x tick=%u fired=%u hits=%u frag=%d dead=%d\n",
        state_hash, presentation_hash, tick, fired, hits, frag_exploded, target.dead);
    return target.dead && fired == hits && frag_exploded == 1 && frag_thrown ? 0 : 1;
}
