#include "game/combat_targets.h"
#include <stdio.h>
#include <string.h>

static void put16(uint8_t *p, uint16_t value) { memcpy(p, &value, 2); }
static void put32(uint8_t *p, uint32_t value) { memcpy(p, &value, 4); }
static void putf(uint8_t *p, float value) { memcpy(p, &value, 4); }

static void make_model(uint8_t data[256], model_section *models)
{
    memset(data, 0, 256);
    memcpy(data, "MODL", 4); put16(data + 4, 1); put32(data + 8, 256);
    put32(data + 12, 0);
    put32(data + 0x20, 96); put32(data + 0x24, 1);
    put32(data + 0x28, 176); put32(data + 0x2C, 1);
    put32(data + 0x30, 256); put32(data + 0x34, 0);
    put32(data + 0x38, 256); put32(data + 0x3C, 0);
    put32(data + 0x40, 256); put32(data + 0x44, 0);
    put32(data + 0x48, 256); put32(data + 0x4C, 0);
    put32(data + 0x50, 256); put32(data + 0x54, 0);
    put32(data + 96, 0x2000); put16(data + 100, 1);
    put32(data + 108, 0); put32(data + 112, 0); put32(data + 116, 0);
    putf(data + 132, 1.0f); put32(data + 156, 0); put32(data + 160, 0); put32(data + 164, 0);
    memcpy(data + 176, "root", 5);
    put16(data + 208, 0xffff); put16(data + 210, 0xffff); put16(data + 212, 0xffff);
    putf(data + 228, 1.0f); putf(data + 244, 1.0f);
    if (model_open(models, data, 256) != MODEL_OK) fprintf(stderr, "synthetic MODL rejected\n");
}

static void make_scen(uint8_t data[272], scen_section *scen)
{
    memset(data, 0, 272);
    memcpy(data, "SCEN", 4); put16(data + 4, 1); put32(data + 8, 272);
    put32(data + 12, 1); put32(data + 16, 0); put32(data + 20, 0);
    put32(data + 24, 128); put32(data + 28, 192); put32(data + 32, 192);
    put32(data + 36, 192); put32(data + 40, 192); put32(data + 44, 0);
    put32(data + 128, 0x1000); put32(data + 132, 0x2000); data[140] = SCEN_BIPED;
    put16(data + 142, SCEN_NO_ANIM); memcpy(data + 144, "test_biped", 11); putf(data + 176, 1.0f);
    if (scen_open(scen, data, 272) != SCEN_OK) fprintf(stderr, "synthetic SCEN rejected\n");
}

static int resolve_test(void *user, uint32_t object_tag, uint32_t model_tag,
    combat_target_definition *out)
{
    combat_target_definition *source = (combat_target_definition *)user;
    if (object_tag != 0x1000 || model_tag != 0x2000) return -1;
    *out = *source;
    return 0;
}

static void make_mesh(uint8_t payload[98], collpack_actor_collision_view *mesh)
{
    memset(payload, 0, 98);
    memcpy(payload, "ACL1", 4);
    put16(payload + 4, 2);
    put16(payload + 6, 1);
    put32(payload + 8, 1);
    put32(payload + 12, 36);
    put16(payload + 16, 0);
    put16(payload + 18, 0xffffu);
    putf(payload + 16 + 4 + 6 * 4, 1.0f);
    put16(payload + 52, 0); /* node */
    put16(payload + 54, 0); /* region */
    put16(payload + 56, 2); /* exported runtime damage-part id */
    put16(payload + 58, 0); /* direct resistance record */
    put16(payload + 60, 0); /* source surface */
    putf(payload + 62, -1.0f); putf(payload + 66, -1.0f); putf(payload + 70, 0.0f);
    putf(payload + 74,  1.0f); putf(payload + 78, -1.0f); putf(payload + 82, 0.0f);
    putf(payload + 86,  0.0f); putf(payload + 90,  1.0f); putf(payload + 94, 0.0f);
    if (collpack_actor_collision(payload, 98, mesh) != 0) {
        fprintf(stderr, "synthetic ACOL rejected\n");
    }
}

static void identity(mat4 *m, float z)
{
    mat4_identity(m);
    m->m[3][2] = z;
}

int main(void)
{
    uint8_t payload[98];
    collpack_actor_collision_view mesh;
    combat_target_registry registry;
    float matrices[COMBAT_TARGET_MAX][COMBAT_TARGET_MAX_NODES][12];
    vital_damage_profile profiles[2];
    combat_target_definition resolved[2];
    object_t objects[2];
    scen_def defs[2];
    model_info models[2];
    object_nodes_t poses[2];
    uint8_t model_data[256], scen_data[272];
    model_section model_section_value;
    scen_section scen_section_value;
    object_table_t table;
    object_world_t world;
    object_nodes_t workspace;
    combat_target_hit hit;
    float origin[3] = {0.0f, 0.0f, 5.0f};
    float direction[3] = {0.0f, 0.0f, -10.0f};
    shot projectile;
    unsigned i;

    make_mesh(payload, &mesh);
    if (!mesh.triangles) return 1;
    make_model(model_data, &model_section_value);
    make_scen(scen_data, &scen_section_value);
    memset(profiles, 0, sizeof profiles);
    for (i = 0; i < 2; i++) {
        profiles[i].maximum_body = 100.0f;
        profiles[i].maximum_shield = i ? 100.0f : 50.0f;
        profiles[i].minimum_shield_stun_damage = 6.0f;
        profiles[i].shield_stun_ticks = 120;
        profiles[i].shield_recharge_step = 1.0f / 120.0f;
        profiles[i].indirect_material_index = 0;
        profiles[i].material_count = 1;
        profiles[i].material[0].material_type = 21;
        profiles[i].material[0].shield_damage_multiplier = 1.0f;
        profiles[i].material[0].body_damage_multiplier = 1.0f;
        resolved[i].mesh = &mesh;
        resolved[i].vitality = &profiles[i];
        resolved[i].body_damage_material_type = 21;
        resolved[i].shield_damage_material_type = 22;
        memset(&objects[i], 0, sizeof objects[i]);
        objects[i].type = SCEN_BIPED;
        objects[i].def = (int16_t)i;
        objects[i].model = (int16_t)i;
        objects[i].region_count = 1;
        defs[i].type = SCEN_BIPED;
        defs[i].tag_id = 0x1000u + i;
        defs[i].model_tag = 0x2000u + i;
        models[i].node_count = 1;
        models[i].tag_id = defs[i].model_tag;
        poses[i].count = 1;
    }
    identity(&poses[0].world[0], 0.0f); /* farther collision, registered first */
    identity(&poses[1].world[0], 2.0f); /* nearer collision */
    combat_targets_reset(&registry);
    if (combat_targets_add_pose(&registry, matrices, 4, &objects[0], &defs[0],
            &models[0], &poses[0], &resolved[0]) != COMBAT_TARGET_ACCEPTED ||
        combat_targets_add_pose(&registry, matrices, 9, &objects[1], &defs[1],
            &models[1], &poses[1], &resolved[1]) != COMBAT_TARGET_ACCEPTED ||
        registry.count != 2) return 2;

    /* A BSP hit at t=.25 occludes both actors; at t=.4 the nearer actor wins. */
    if (combat_targets_ray(&registry, origin, direction, 0.25f, &hit) != 0) return 3;
    if (combat_targets_ray(&registry, origin, direction, 0.4f, &hit) != 1 ||
        hit.object_index != 9 || hit.collision.node_index != 0 ||
        hit.collision.resistance_index != 0 || hit.collision.region_index != 0) return 4;

    /* Target-specific profile: a 10-point hit lowers only the nearer target's
     * 100-point shield by 0.1; the other target has a distinct 50-point shield. */
    memset(&projectile, 0, sizeof projectile);
    projectile.hit_object_this_tick = 1;
    projectile.damage = 10.0f;
    projectile.damage_resistance_index = 0;
    projectile.hit_region_index = 0;
    projectile.damage_material_types_valid = 1;
    projectile.damage_body_modifier = 1.0f;
    projectile.damage_shield_modifier = 1.0f;
    if (combat_targets_apply_projectile(&registry, 9, &projectile, VITAL_BODY, 0, 1.0f, 1.0f) != 1 ||
        projectile.hit_object_this_tick || registry.target[1].health.shield != 0.9f ||
        registry.target[0].health.shield != 1.0f) return 5;
    registry.target[1].health.dead = 1;
    projectile.hit_object_this_tick = 1;
    if (combat_targets_apply_projectile(&registry, 9, &projectile, VITAL_BODY, 0, 1.0f, 1.0f) != 1 ||
        projectile.hit_object_this_tick) return 10;
    if (combat_targets_ray(&registry, origin, direction, 0.4f, &hit) != 1 || hit.object_index != 9) return 12;
    if (combat_targets_add_pose(&registry, matrices, 9, &objects[1], &defs[1],
            &models[1], &poses[1], &resolved[1]) != COMBAT_TARGET_REJECT_DUPLICATE ||
        combat_targets_add_pose(&registry, matrices, UINT16_MAX, &objects[1], &defs[1],
            &models[1], &poses[1], &resolved[1]) != COMBAT_TARGET_REJECT_DEFINITION) return 11;

    /* Exercise the real object_table -> objects_pose bridge, then move the
     * posed root and prove vitality survives the rebuilt pose cache. */
    memset(&table, 0, sizeof table); table.count = 1; table.obj[0] = objects[0];
    table.obj[0].def = 0; table.obj[0].model = 0; table.obj[0].graph = -1;
    table.obj[0].anim = SCEN_NO_ANIM; identity(&table.obj[0].root, 2.0f);
    world.scen = &scen_section_value; world.models = &model_section_value; world.anims = NULL;
    combat_targets_reset(&registry);
    combat_targets_update(&registry, matrices, &table, &world, &workspace, resolve_test, &resolved[0]);
    if (registry.count != 1 || registry.target[0].object_index != 0) return 8;
    registry.target[0].health.shield = 0.37f;
    identity(&table.obj[0].root, 3.0f);
    combat_targets_update(&registry, matrices, &table, &world, &workspace, resolve_test, &resolved[0]);
    if (registry.count != 1 || registry.target[0].health.shield != 0.37f ||
        registry.target[0].bounds_min[2] != 3.0f) return 9;

    /* Explicitly exclude incompatible object types and mismatched node tables. */
    objects[0].type = SCEN_VEHICLE;
    if (combat_targets_add_pose(&registry, matrices, 11, &objects[0], &defs[0],
            &models[0], &poses[0], &resolved[0]) != COMBAT_TARGET_REJECT_UNSUPPORTED_TYPE) return 6;
    objects[0].type = SCEN_BIPED;
    poses[0].count = 0;
    if (combat_targets_add_pose(&registry, matrices, 11, &objects[0], &defs[0],
            &models[0], &poses[0], &resolved[0]) != COMBAT_TARGET_REJECT_MESH) return 7;

    printf("combat target registry: object_table pose/update, vitality persistence, occlusion and hit attribution ok (registry=%lu bytes, pose workspace=%lu bytes)\n",
        (unsigned long)sizeof registry, (unsigned long)sizeof workspace);
    return 0;
}
