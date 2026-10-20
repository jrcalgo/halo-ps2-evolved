#include "game/gun.h"
#include "game/shot.h"
#include "game/vital.h"

#include <assert.h>
#include <stdio.h>

int main(void)
{
    gun weapon;
    vital target;
    shot_scene scene = {0};
    float origin[3] = {0, 0, 0};
    float forward[3] = {1, 0, 0};
    uint32_t seed = 1;
    unsigned tick, fired = 0, hits = 0;

    gun_init(&weapon, &GUN_PISTOL);
    vital_init(&target);
    scene.target = 1;
    scene.target_center[0] = 5.0f;
    scene.target_radius = 0.5f;
    for (tick = 0; tick < 240 && !target.dead; ++tick) {
        if (gun_tick(&weapon, &GUN_PISTOL, 1, 0)) {
            shot projectile;
            ++fired;
            shot_spawn(&projectile, origin, forward, &SHOT_PISTOL);
            (void)shot_tick(&projectile, &SHOT_PISTOL, &scene, &seed);
            if (vital_apply_projectile_hit(&target, &projectile, VITAL_BODY, 1.0f, 0)) {
                ++hits;
                assert(!vital_apply_projectile_hit(&target, &projectile,
                    VITAL_BODY, 1.0f, 0));
            }
        }
    }
    assert(target.dead);
    assert(fired > 0 && hits == fired);
    assert(target.shield == 0.0f && target.body < 0.0f);
    printf("pistol-unit ticks=%u fired=%u hits=%u shield=%.1f body=%.3f dead=%d seed=%08x\n",
        tick, fired, hits, target.shield, target.body, target.dead, seed);

    /* Carry the direct CE collision-model resistance index through the
     * projectile hit event into damage, distinct from its runtime material
     * type used to select the jpt! modifier. */
    {
        shot_def def = SHOT_PISTOL;
        shot projectile;
        shot_scene direct_scene = {0};
        vital_damage_profile profile = {
            .maximum_shield = 75.0f, .maximum_body = 75.0f,
            .shield_leak_fraction = 0.0f, .shield_damage_multiplier = 1.0f,
            .body_damage_multiplier = 1.0f, .minimum_shield_stun_damage = 6.0f,
            .shield_stun_ticks = 120, .shield_recharge_step = 1.0f / 120.0f,
            .indirect_material_index = 1, .material_count = 3
        };
        def.damage_minimum = def.damage_lower = def.damage_upper = 10.0f;
        def.damage_materials_valid = 1;
        def.damage_material_modifier[21] = 1.0f;
        def.damage_material_modifier[22] = 1.0f;
        profile.material[1].material_type = 21;
        profile.material[1].shield_leak_fraction = 0.0f;
        profile.material[1].shield_damage_multiplier = 1.0f;
        profile.material[1].body_damage_multiplier = 1.0f;
        profile.material[2].material_type = 21;
        profile.material[2].shield_leak_fraction = 0.5f;
        profile.material[2].shield_damage_multiplier = 1.0f;
        profile.material[2].body_damage_multiplier = 0.8f;
        direct_scene.target = 1;
        direct_scene.target_center[0] = 1.0f;
        direct_scene.target_radius = 0.25f;
        direct_scene.target_damage_material_types_valid = 1;
        direct_scene.target_body_damage_material_type = 21;
        direct_scene.target_shield_damage_material_type = 22;
        direct_scene.target_damage_resistance_index = 2;
        direct_scene.target_damage_resistance_index_valid = 1;
        vital_init(&target);
        shot_spawn(&projectile, origin, forward, &def);
        assert(!shot_tick(&projectile, &def, &direct_scene, &seed));
        assert(projectile.damage_resistance_index == 2);
        assert(vital_apply_projectile_hit_profile(&target, &projectile,
            VITAL_BODY, &profile, 99.0f, 99.0f, 0));
        assert(target.shield > 0.933f && target.shield < 0.934f);
        assert(target.body > 0.946f && target.body < 0.947f);
        printf("direct-material index=%d shield=%.3f body=%.3f\n",
            projectile.damage_resistance_index, target.shield, target.body);
    }

    /* Retail Needler: attach to the target, wait 0.75 s at rest, then apply
     * the attached jpt! damage once. The attached damage modifiers are
     * selected by the projectile event, not the zero-damage impact tag. */
    {
        shot_def needler = SHOT_PISTOL;
        shot projectile;
        shot_scene attached_scene = {0};
        uint32_t attached_seed = 1;
        unsigned fuse_tick;
        needler.response[0] = 4;
        needler.damage_minimum = needler.damage_lower = needler.damage_upper = 0.0f;
        needler.projectile_flags = 1u << 2;
        needler.detonation_timer_starts = 2;
        needler.timer_lower_bound = 0.75f;
        needler.timer_upper_bound = 0.75f;
        needler.attached_damage_minimum = 10.0f;
        needler.attached_damage_lower = needler.attached_damage_upper = 10.0f;
        needler.attached_damage_material_modifier_21 = 1.0f;
        needler.attached_damage_material_modifier_22 = 1.0f;
        attached_scene.target = 1;
        attached_scene.target_center[0] = 5.0f;
        attached_scene.target_radius = 0.5f;
        vital_init(&target);
        shot_spawn_seeded(&projectile, origin, forward, &needler, &attached_seed);
        (void)shot_tick(&projectile, &needler, &attached_scene, &attached_seed);
        assert(projectile.alive && projectile.attached && projectile.attached_target);
        assert(projectile.hit_object_this_tick && projectile.damage == 0.0f);
        assert(vital_apply_projectile_hit(&target, &projectile, VITAL_BODY, 1.0f, 0));
        assert(target.shield == 1.0f && target.body == 1.0f);
        for (fuse_tick = 0; fuse_tick < 23; ++fuse_tick) {
            (void)shot_tick(&projectile, &needler, &attached_scene, &attached_seed);
            if (projectile.hit_object_this_tick)
                assert(vital_apply_projectile_hit_profile(&target, &projectile,
                    VITAL_BODY, &VITAL_CYBORG_INDIRECT_PROFILE, 99.0f, 99.0f, 0));
        }
        assert(!projectile.alive && projectile.action == SHOT_DETONATE);
        assert(target.shield < 1.0f && target.body == 1.0f);
        assert(!vital_apply_projectile_hit(&target, &projectile, VITAL_BODY, 1.0f, 0));
        printf("needler-attach fuse_ticks=%u damage=%.1f shield=%.3f body=%.1f seed=%08x\n",
            fuse_tick, projectile.damage, target.shield, target.body, attached_seed);
    }
    return 0;
}
