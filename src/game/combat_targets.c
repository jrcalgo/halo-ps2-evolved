#include "game/combat_targets.h"
#include <math.h>
#include <string.h>

static int finite_value(float value)
{
    return isfinite(value) && value > -1.0e20f && value < 1.0e20f;
}

static int profile_valid(const vital_damage_profile *profile)
{
    unsigned i;
    if (!profile || !finite_value(profile->maximum_body) || profile->maximum_body <= 0.0f ||
        !finite_value(profile->maximum_shield) || profile->maximum_shield <= 0.0f ||
        !finite_value(profile->shield_recharge_step) || profile->shield_recharge_step < 0.0f ||
        !finite_value(profile->minimum_shield_stun_damage) || profile->minimum_shield_stun_damage < 0.0f ||
        profile->shield_stun_ticks < 0 || profile->material_count > VITAL_DAMAGE_MATERIAL_MAX ||
        profile->region_count > VITAL_DAMAGE_REGION_MAX) return 0;
    if (profile->material_count &&
        (profile->indirect_material_index < 0 || profile->indirect_material_index >= profile->material_count))
        return 0;
    for (i = 0; i < profile->material_count; i++) {
        const vital_damage_material *m = &profile->material[i];
        if (m->material_type < -1 || m->material_type >= COLL_RUNTIME_MATERIAL_TYPES ||
            !finite_value(m->shield_leak_fraction) || !finite_value(m->shield_damage_multiplier) ||
            !finite_value(m->body_damage_multiplier)) return 0;
    }
    for (i = 0; i < profile->region_count; i++)
        if (!finite_value(profile->region_damage_threshold[i]) || profile->region_damage_threshold[i] < 0.0f)
            return 0;
    return 1;
}

void combat_targets_reset(combat_target_registry *registry)
{
    if (registry) memset(registry, 0, sizeof *registry);
}

static int mesh_valid(const collpack_actor_collision_view *mesh, unsigned model_nodes,
    const object_nodes_t *nodes)
{
    uint32_t i;
    if (!mesh || !mesh->nodes || !mesh->triangles || !mesh->node_count ||
        mesh->node_count > COMBAT_TARGET_MAX_NODES || mesh->node_count > model_nodes ||
        mesh->triangle_count == 0 || mesh->triangle_stride != 46 ||
        mesh->node_stride != 36 || !nodes || nodes->count < mesh->node_count) return 0;
    for (i = 0; i < mesh->node_count; i++) {
        unsigned row, column;
        for (row = 0; row < 4; row++)
            for (column = 0; column < 4; column++)
                if (!finite_value(nodes->world[i].m[row][column])) return 0;
    }
    return 1;
}

static void pose_matrix_to_row_major(const mat4 *source, float target[12])
{
    unsigned row, column;
    /* mat4_transform_point uses basis vectors in m[0..2] and translation m[3]. */
    for (row = 0; row < 3; row++) {
        for (column = 0; column < 3; column++)
            target[row * 4 + column] = source->m[column][row];
        target[row * 4 + 3] = source->m[3][row];
    }
}

static void transform_point(const float matrix[12], const float point[3], float out[3])
{
    unsigned row;
    for (row = 0; row < 3; row++)
        out[row] = matrix[row * 4] * point[0] + matrix[row * 4 + 1] * point[1] +
            matrix[row * 4 + 2] * point[2] + matrix[row * 4 + 3];
}

static combat_target_reject add_pose(combat_target_registry *registry,
    float (*matrix_pool)[COMBAT_TARGET_MAX_NODES][12], uint16_t object_index,
    const object_t *object, const scen_def *definition, const model_info *model,
    const object_nodes_t *nodes, const combat_target_definition *resolved)
{
    combat_target *target;
    uint32_t triangle;
    unsigned node;
    float node_min[COMBAT_TARGET_MAX_NODES][3];
    float node_max[COMBAT_TARGET_MAX_NODES][3];
    uint8_t node_has_geometry[COMBAT_TARGET_MAX_NODES] = {0};
    if (!object || !definition || !model || !nodes || !resolved)
        return COMBAT_TARGET_REJECT_DEFINITION;
    if (object->type != SCEN_BIPED) return COMBAT_TARGET_REJECT_UNSUPPORTED_TYPE;
    if (object->def < 0 || object->model < 0 || definition->type != SCEN_BIPED ||
        !definition->tag_id || !definition->model_tag)
        return COMBAT_TARGET_REJECT_DEFINITION;
    if (!model->node_count || model->tag_id != definition->model_tag)
        return COMBAT_TARGET_REJECT_MODEL;
    if (!resolved->mesh || !resolved->vitality || !matrix_pool ||
        !mesh_valid(resolved->mesh, model->node_count, nodes))
        return COMBAT_TARGET_REJECT_MESH;
    if (!profile_valid(resolved->vitality) ||
        resolved->body_damage_material_type < -1 ||
        resolved->body_damage_material_type >= COLL_RUNTIME_MATERIAL_TYPES ||
        resolved->shield_damage_material_type < -1 ||
        resolved->shield_damage_material_type >= COLL_RUNTIME_MATERIAL_TYPES)
        return COMBAT_TARGET_REJECT_PROFILE;
    if (object_index >= OBJ_MAX) return COMBAT_TARGET_REJECT_DEFINITION;
    {
        unsigned i;
        for (i = 0; i < registry->count; i++)
            if (registry->target[i].object_index == object_index)
                return COMBAT_TARGET_REJECT_DUPLICATE;
    }
    if (registry->count >= COMBAT_TARGET_MAX) return COMBAT_TARGET_REJECT_CAPACITY;

    target = &registry->target[registry->count];
    memset(target, 0, sizeof *target);
    target->object_index = object_index;
    target->definition_index = object->def;
    target->model_index = object->model;
    target->object_tag_id = definition->tag_id;
    target->model_tag_id = definition->model_tag;
    target->object = object;
    target->mesh = resolved->mesh;
    target->profile = resolved->vitality;
    target->body_damage_material_type = resolved->body_damage_material_type;
    target->shield_damage_material_type = resolved->shield_damage_material_type;
    target->node_to_world = matrix_pool[registry->count];
    for (node = 0; node < target->mesh->node_count; node++)
        pose_matrix_to_row_major(&nodes->world[node], target->node_to_world[node]);
    for (node = 0; node < 3; node++) {
        target->bounds_min[node] = 1.0e20f;
        target->bounds_max[node] = -1.0e20f;
    }
    for (node = 0; node < target->mesh->node_count; node++) {
        unsigned axis;
        for (axis = 0; axis < 3; axis++) {
            node_min[node][axis] = 1.0e20f;
            node_max[node][axis] = -1.0e20f;
        }
    }
    for (triangle = 0; triangle < target->mesh->triangle_count; triangle++) {
        const uint8_t *record = target->mesh->triangles + triangle * target->mesh->triangle_stride;
        int16_t tri_node;
        unsigned vertex, axis;
        memcpy(&tri_node, record, sizeof tri_node);
        if (tri_node < 0 || tri_node >= (int16_t)target->mesh->node_count)
            return COMBAT_TARGET_REJECT_MESH;
        for (vertex = 0; vertex < 3; vertex++) {
            float local[3];
            memcpy(local, record + 10 + vertex * 12, sizeof local);
            if (!finite_value(local[0]) || !finite_value(local[1]) || !finite_value(local[2]))
                return COMBAT_TARGET_REJECT_MESH;
            for (axis = 0; axis < 3; axis++) {
                if (local[axis] < node_min[tri_node][axis]) node_min[tri_node][axis] = local[axis];
                if (local[axis] > node_max[tri_node][axis]) node_max[tri_node][axis] = local[axis];
            }
            node_has_geometry[tri_node] = 1;
        }
    }
    /* Transform each node's local AABB corners once. This conservative broad
     * phase bound avoids transforming every collision vertex every tick. */
    for (node = 0; node < target->mesh->node_count; node++) {
        unsigned corner, axis;
        if (!node_has_geometry[node]) continue;
        for (corner = 0; corner < 8; corner++) {
            float local[3], world[3];
            for (axis = 0; axis < 3; axis++)
                local[axis] = (corner & (1u << axis)) ? node_max[node][axis] : node_min[node][axis];
            transform_point(target->node_to_world[node], local, world);
            for (axis = 0; axis < 3; axis++) {
                if (!finite_value(world[axis])) return COMBAT_TARGET_REJECT_POSE;
                if (world[axis] < target->bounds_min[axis]) target->bounds_min[axis] = world[axis];
                if (world[axis] > target->bounds_max[axis]) target->bounds_max[axis] = world[axis];
            }
        }
    }
    vital_init(&target->health);
    registry->count++;
    return COMBAT_TARGET_ACCEPTED;
}

combat_target_reject combat_targets_add_pose(combat_target_registry *registry,
    float (*matrix_pool)[COMBAT_TARGET_MAX_NODES][12], uint16_t object_index,
    const object_t *object, const scen_def *definition, const model_info *model,
    const object_nodes_t *nodes, const combat_target_definition *resolved)
{
    combat_target_reject result;
    if (!registry) return COMBAT_TARGET_REJECT_DEFINITION;
    result = add_pose(registry, matrix_pool, object_index, object, definition, model, nodes, resolved);
    if (result != COMBAT_TARGET_ACCEPTED && result <= COMBAT_TARGET_REJECT_CAPACITY)
        registry->rejected[result]++;
    return result;
}

typedef struct {
    uint16_t object_index;
    int16_t definition_index, model_index;
    uint32_t object_tag_id, model_tag_id;
    vital health;
} combat_target_saved_state;

static int same_saved_key(const combat_target_saved_state *a, uint16_t index,
    const object_t *object, const scen_def *definition)
{
    return a->object_index == index && a->definition_index == object->def &&
        a->model_index == object->model && a->object_tag_id == definition->tag_id &&
        a->model_tag_id == definition->model_tag;
}

void combat_targets_update(combat_target_registry *registry,
    float (*matrix_pool)[COMBAT_TARGET_MAX_NODES][12],
    const object_table_t *table, const object_world_t *world,
    object_nodes_t *workspace, combat_target_resolver resolver, void *user)
{
    /* Single-threaded EE simulation scratch: keep the tick stack small. */
    static combat_target_saved_state previous[COMBAT_TARGET_MAX];
    unsigned old_count, i;
    if (!registry || !matrix_pool || !table || !world || !world->scen || !world->models ||
        !workspace || !resolver || table->count > OBJ_MAX) return;
    old_count = registry->count > COMBAT_TARGET_MAX ? COMBAT_TARGET_MAX : registry->count;
    for (i = 0; i < old_count; i++) {
        previous[i].object_index = registry->target[i].object_index;
        previous[i].definition_index = registry->target[i].definition_index;
        previous[i].model_index = registry->target[i].model_index;
        previous[i].object_tag_id = registry->target[i].object_tag_id;
        previous[i].model_tag_id = registry->target[i].model_tag_id;
        previous[i].health = registry->target[i].health;
    }
    registry->count = 0;
    memset(registry->rejected, 0, sizeof registry->rejected);
    for (i = 0; i < table->count; i++) {
        const object_t *object = &table->obj[i];
        scen_def definition;
        model_info model;
        combat_target_definition resolved;
        combat_target_reject result;
        unsigned k;
        if (object->type != SCEN_BIPED) {
            registry->rejected[COMBAT_TARGET_REJECT_UNSUPPORTED_TYPE]++;
            continue;
        }
        if (object->def < 0 || (uint32_t)object->def >= world->scen->def_count || object->model < 0 ||
            (uint32_t)object->model >= world->models->model_count) {
            registry->rejected[COMBAT_TARGET_REJECT_DEFINITION]++;
            continue;
        }
        definition = scen_get_def(world->scen, (uint32_t)object->def);
        if (definition.type != SCEN_BIPED || !definition.model_tag) {
            registry->rejected[COMBAT_TARGET_REJECT_DEFINITION]++;
            continue;
        }
        model = model_get(world->models, (uint32_t)object->model);
        memset(&resolved, 0, sizeof resolved);
        if (resolver(user, definition.tag_id, definition.model_tag, &resolved) != 0) {
            registry->rejected[COMBAT_TARGET_REJECT_MESH]++;
            continue;
        }
        if (!objects_pose(object, world, workspace)) {
            registry->rejected[COMBAT_TARGET_REJECT_POSE]++;
            continue;
        }
        result = add_pose(registry, matrix_pool, (uint16_t)i, object, &definition,
            &model, workspace, &resolved);
        if (result != COMBAT_TARGET_ACCEPTED) {
            registry->rejected[result]++;
            continue;
        }
        for (k = 0; k < old_count; k++) {
            if (same_saved_key(&previous[k], (uint16_t)i, object, &definition)) {
                registry->target[registry->count - 1].health = previous[k].health;
                break;
            }
        }
    }
}

static int ray_aabb(const float origin[3], const float direction[3],
    const float minimum[3], const float maximum[3], float max_t)
{
    float near_t = 0.0f, far_t = max_t;
    unsigned axis;
    for (axis = 0; axis < 3; axis++) {
        if (fabsf(direction[axis]) < 1.0e-12f) {
            if (origin[axis] < minimum[axis] || origin[axis] > maximum[axis]) return 0;
        } else {
            float a = (minimum[axis] - origin[axis]) / direction[axis];
            float b = (maximum[axis] - origin[axis]) / direction[axis];
            float swap;
            if (a > b) { swap = a; a = b; b = swap; }
            if (a > near_t) near_t = a;
            if (b < far_t) far_t = b;
            if (near_t > far_t) return 0;
        }
    }
    return far_t > 0.0f;
}

int combat_targets_ray(const combat_target_registry *registry,
    const float origin[3], const float direction[3], float maximum_t,
    combat_target_hit *hit)
{
    unsigned i;
    int found = 0;
    float nearest = maximum_t;
    combat_target_hit best;
    if (!registry || !origin || !direction || !hit || !finite_value(maximum_t) || maximum_t <= 0.0f)
        return -1;
    for (i = 0; i < registry->count; i++) {
        const combat_target *target = &registry->target[i];
        collpack_actor_hit candidate;
        int result;
        /* Death is a damage-state decision, not a collision-geometry removal;
         * CE projectiles still encounter corpse collision/materials. */
        if (!target->mesh || !target->node_to_world ||
            !ray_aabb(origin, direction, target->bounds_min, target->bounds_max, nearest)) continue;
        result = collpack_actor_ray(target->mesh,
            (const float (*)[12])target->node_to_world,
            origin, direction, nearest, &candidate);
        if (result < 0) return -1;
        if (result == 1 && candidate.distance > 0.0f && candidate.distance < nearest) {
            nearest = candidate.distance;
            best.object_index = target->object_index;
            best.collision = candidate;
            found = 1;
        }
    }
    if (found) *hit = best;
    return found;
}

int combat_targets_apply_impact(combat_target_registry *registry,
    const shot_impact_event *impact, int vital_part, int headshot)
{
    unsigned i;
    if (!registry || !impact || impact->object_index < 0) return 0;
    for (i = 0; i < registry->count; i++) {
        combat_target *target = &registry->target[i];
        if (target->object_index == (uint16_t)impact->object_index) {
            /* CE's damage path consumes the collision event even if vitality
             * is already zero; a corpse cannot replay that event next tick. */
            if (target->health.dead) return 1;
            if (impact->damage > 0.0f)
                vital_hurt_material_region_profile(&target->health, impact->damage,
                    vital_part, target->profile, impact->resistance_index,
                    impact->region_index, impact->body_modifier,
                    impact->shield_modifier,
                    headshot || (impact->damage_flags & (1u << 1)) != 0);
            return 1;
        }
    }
    return 0;
}

int combat_targets_apply_projectile(combat_target_registry *registry,
    uint16_t object_index, shot *projectile, int vital_part, int headshot,
    float body_material_modifier, float shield_material_modifier)
{
    shot_impact_event impact;
    if (!registry || !projectile || !projectile->hit_object_this_tick) return 0;
    memset(&impact, 0, sizeof impact);
    impact.object_index = (int16_t)object_index;
    impact.node_index = projectile->hit_node_index;
    impact.damage_part = projectile->hit_damage_part;
    impact.region_index = projectile->hit_region_index;
    impact.resistance_index = projectile->damage_resistance_index;
    impact.body_material_type = projectile->damage_body_material_type;
    impact.shield_material_type = projectile->damage_shield_material_type;
    impact.material_types_valid = projectile->damage_material_types_valid;
    impact.damage = projectile->damage;
    impact.body_modifier = body_material_modifier;
    impact.shield_modifier = shield_material_modifier;
    {
        unsigned i;
        for (i = 0; i < registry->count; i++) {
            const combat_target *target = &registry->target[i];
            if (target->object_index != object_index) continue;
            if (impact.material_types_valid &&
                impact.body_material_type == target->body_damage_material_type &&
                impact.shield_material_type == target->shield_damage_material_type) {
                impact.body_modifier = projectile->damage_body_modifier;
                impact.shield_modifier = projectile->damage_shield_modifier;
            } else {
                impact.body_material_type = target->body_damage_material_type;
                impact.shield_material_type = target->shield_damage_material_type;
                impact.material_types_valid = 1;
            }
            break;
        }
    }
    projectile->hit_object_this_tick = 0;
    return combat_targets_apply_impact(registry, &impact, vital_part, headshot);
}

void combat_targets_tick(combat_target_registry *registry)
{
    unsigned i;
    if (!registry) return;
    for (i = 0; i < registry->count; i++)
        vital_tick_profile(&registry->target[i].health, registry->target[i].profile);
}
