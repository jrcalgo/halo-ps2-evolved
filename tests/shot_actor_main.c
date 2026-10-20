#include "game/collpack.h"
#include "game/shot.h"
#include <stdio.h>
#include <string.h>

static void put16(uint8_t *p, unsigned value)
{
    uint16_t v = (uint16_t)value;
    memcpy(p, &v, 2);
}

static void put32(uint8_t *p, uint32_t value)
{
    memcpy(p, &value, 4);
}

static void put_float(uint8_t *p, float value)
{
    memcpy(p, &value, 4);
}

int main(void)
{
    uint8_t payload[16 + 36 + 46] = {0};
    collpack_actor_collision_view actor;
    float matrix[1][12] = { {1,0,0,0, 0,1,0,0, 0,0,1,0} };
    float second_matrix[1][12] = { {1,0,0,0, 0,1,0,0, 0,0,1,-0.5f} };
    float origin[3] = {0, 0, 1}, direction[3] = {0, 0, -1};
    shot_scene scene = {0};
    shot projectile, attached_projectile;
    shot_target_view target_view[2] = {{0}};
    vital_damage_profile target_profile = {0};
    shot_def attach_def;
    uint32_t seed = 123;
    memcpy(payload, "ACL1", 4);
    put16(payload + 4, 2);
    put16(payload + 6, 1);
    put32(payload + 8, 1);
    put32(payload + 12, 36);
    put16(payload + 16, 0);
    put16(payload + 18, 0xffffu);
    put_float(payload + 16 + 4 + 6 * 4, 1.0f);
    put16(payload + 52, 0); /* node */
    put16(payload + 54, 0); /* region */
    put16(payload + 56, 2); /* runtime head damage part */
    put16(payload + 58, 2); /* direct resistance record */
    put16(payload + 60, 0); /* source surface */
    put_float(payload + 62, -1.0f);
    put_float(payload + 66, -1.0f);
    put_float(payload + 70, 1.0f);
    put_float(payload + 74, 1.0f);
    put_float(payload + 78, -1.0f);
    put_float(payload + 90, 1.0f);
    if (collpack_actor_collision(payload, sizeof payload, &actor) != 0) return 1;
    scene.target_is_unit = 1;
    scene.target = 1;
    scene.target_material = 0;
    scene.target_body_damage_material_type = 21;
    scene.target_shield_damage_material_type = 22;
    scene.target_damage_material_types_valid = 1;
    target_view[0].object_index = 13;
    target_view[0].body_damage_material_type = 21;
    target_view[0].shield_damage_material_type = 22;
    target_view[0].mesh = &actor;
    target_profile.material_count = 3;
    target_profile.material[2].material_type = 22; /* physics material, not resistance index */
    target_view[0].vitality_profile = &target_profile;
    target_view[0].node_to_world = (const float (*)[12])matrix;
    target_view[1] = target_view[0];
    target_view[1].object_index = 14;
    target_view[1].node_to_world = (const float (*)[12])second_matrix;
    scene.targets = target_view;
    scene.target_count = 2;
    shot_spawn(&projectile, origin, direction, &SHOT_PISTOL);
    shot_tick(&projectile, &SHOT_PISTOL, &scene, &seed);
    if (!projectile.hit_object || !projectile.hit_object_this_tick ||
        projectile.hit_node_index != 0 || projectile.hit_damage_part != 2 ||
        projectile.hit_region_index != 0 || projectile.damage_resistance_index != 2 ||
        projectile.hit_material_type != 22 || projectile.hit_object_index != 13 ||
        projectile.damage <= 0.0f) return 2;
    printf("actor shot node=%d region=%d part=%d resistance=%d damage=%.1f\n",
        projectile.hit_node_index, projectile.hit_region_index,
        projectile.hit_damage_part, projectile.damage_resistance_index, projectile.damage);
    {
        shot_def penetrate_def = SHOT_PISTOL;
        shot penetrating;
        penetrate_def.response[22] = 3;
        penetrate_def.damage_flags = 2;
        shot_spawn(&penetrating, origin, direction, &penetrate_def);
        shot_tick(&penetrating, &penetrate_def, &scene, &seed);
        if (penetrating.impact_count != 2 || penetrating.impacts[0].object_index != 13 ||
            penetrating.impacts[1].object_index != 14 ||
            penetrating.impacts[0].damage_flags != 2 || penetrating.impacts[1].damage_flags != 2 ||
            penetrating.impacts[0].damage <= 0.0f || penetrating.impacts[1].damage <= 0.0f)
            return 5;
        printf("actor penetration impacts=%u objects=%d,%d\n", penetrating.impact_count,
            penetrating.impacts[0].object_index, penetrating.impacts[1].object_index);
    }
    attach_def = SHOT_PISTOL;
    attach_def.response[22] = 4; /* CE damage material -> global physics material -> response. */
    shot_spawn(&attached_projectile, origin, direction, &attach_def);
    shot_tick(&attached_projectile, &attach_def, &scene, &seed);
    if (!attached_projectile.alive || !attached_projectile.attached ||
        !attached_projectile.attached_target || !attached_projectile.attached_node_valid ||
        attached_projectile.attached_node_index != 0 ||
        attached_projectile.attached_object_index != 13) return 3;
    matrix[0][3] = 10.0f;
    shot_tick(&attached_projectile, &attach_def, &scene, &seed);
    if (attached_projectile.position[0] < 9.99f || attached_projectile.position[0] > 10.01f)
        return 4;
    printf("actor attach node=%d follows-x=%.1f\n", attached_projectile.attached_node_index,
        attached_projectile.position[0]);
    return 0;
}
