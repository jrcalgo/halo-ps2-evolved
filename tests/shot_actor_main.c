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
    float origin[3] = {0, 0, 1}, direction[3] = {0, 0, -1};
    shot_scene scene = {0};
    shot projectile;
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
    scene.target = 1;
    scene.target_is_unit = 1;
    scene.target_material = 0;
    scene.target_body_damage_material_type = 21;
    scene.target_shield_damage_material_type = 22;
    scene.target_damage_material_types_valid = 1;
    scene.actor_mesh = &actor;
    scene.actor_node_to_world = matrix;
    shot_spawn(&projectile, origin, direction, &SHOT_PISTOL);
    shot_tick(&projectile, &SHOT_PISTOL, &scene, &seed);
    if (!projectile.hit_object || !projectile.hit_object_this_tick ||
        projectile.hit_node_index != 0 || projectile.hit_damage_part != 2 ||
        projectile.hit_region_index != 0 || projectile.damage_resistance_index != 2 ||
        projectile.damage <= 0.0f) return 2;
    printf("actor shot node=%d region=%d part=%d resistance=%d damage=%.1f\n",
        projectile.hit_node_index, projectile.hit_region_index,
        projectile.hit_damage_part, projectile.damage_resistance_index, projectile.damage);
    return 0;
}
