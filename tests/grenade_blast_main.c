#include "game/grenade.h"
#include "game/combat_targets.h"
#include "game/vital.h"
#include <assert.h>
#include <math.h>
#include <stdio.h>
#include <string.h>

static void target_at(combat_target *target, float x)
{
    memset(target, 0, sizeof *target);
    target->object_index = 7;
    target->profile = &VITAL_CYBORG_INDIRECT_PROFILE;
    target->bounds_min[0] = x - 0.1f;
    target->bounds_max[0] = x + 0.1f;
    target->bounds_min[1] = target->bounds_min[2] = -0.1f;
    target->bounds_max[1] = target->bounds_max[2] = 0.1f;
    vital_init(&target->health);
    target->health.shield = 0.0f;
}

int main(void)
{
    grenade item;
    combat_target target;
    uint32_t seed = 0x12345678u, before;
    float distance, damage;
    memset(&item, 0, sizeof item);
    item.position[0] = item.position[1] = item.position[2] = 0.0f;

    target_at(&target, 1.0f);
    target.profile = &(vital_damage_profile){
        .maximum_shield = 75.0f, .maximum_body = 300.0f,
        .shield_damage_multiplier = 1.0f, .body_damage_multiplier = 1.0f,
        .minimum_shield_stun_damage = 6.0f, .indirect_material_index = 0
    };
    assert(grenade_blast_target(&item, &GRENADE_FRAG, NULL, &target, -1,
        &seed, &distance, &damage) == 1);
    assert(fabsf(distance - 1.0f) < 1e-5f && damage == 120.0f);
    assert(fabsf(target.health.body - 0.6f) < 1e-5f);
    printf("falloff distance=%.2f damage=%.1f body=%.3f\n",
        distance, damage, target.health.body);

    target_at(&target, 2.0f);
    target.profile = &(vital_damage_profile){
        .maximum_shield = 75.0f, .maximum_body = 300.0f,
        .shield_damage_multiplier = 1.0f, .body_damage_multiplier = 1.0f,
        .minimum_shield_stun_damage = 6.0f, .indirect_material_index = 0
    };
    assert(grenade_blast_target(&item, &GRENADE_FRAG, NULL, &target, -1,
        &seed, &distance, &damage) == 1);
    assert(fabsf(distance - 2.0f) < 1e-5f && damage == 100.0f);

    before = seed;
    target_at(&target, 2.5f);
    assert(grenade_blast_target(&item, &GRENADE_FRAG, NULL, &target, -1,
        &seed, &distance, &damage) == 0);
    assert(seed == before && damage == 0.0f);

    {
        grenade_def owner_immune = GRENADE_FRAG;
        owner_immune.damage_flags |= 1u;
        target_at(&target, 0.5f);
        before = seed;
        assert(grenade_blast_target(&item, &owner_immune, NULL, &target, 7,
            &seed, &distance, &damage) == 0);
        assert(seed == before && target.health.body == 1.0f);
        /* Retail frag/plasma flags are 0x20, so the thrower remains damageable. */
        assert(grenade_blast_target(&item, &GRENADE_FRAG, NULL, &target, 7,
            &seed, &distance, &damage) == 1);
        assert(target.health.body < 1.0f);
    }
    puts("owner immunity and retail self-damage passed");
    return 0;
}
