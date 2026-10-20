#include "game/shot.h"
#include "game/collpack.h"
#include <math.h>
#include <string.h>

#define SHOT_GRAVITY 0.0035651792f

const shot_def SHOT_PISTOL = {
    .velocity_bits = 0x41200001u, .final_velocity = 10.0f, .maximum_range = 40.0f,
    .air_gravity_scale = 1.0f, .damage_lower = 25.0f, .damage_upper = 25.0f,
    .damage_material_modifier_21 = 1.5f, .damage_material_modifier_22 = 1.0f,
    .response = { [9] = 3, [29] = 3, [32] = 2 }
};

const shot_def SHOT_ASSAULT_RIFLE = {
    .velocity_bits = 0x412CCCCDu, .final_velocity = 10.0f, .maximum_range = 40.0f,
    .air_gravity_scale = 1.0f, .damage_lower = 10.0f, .damage_upper = 10.0f,
    .damage_material_modifier_21 = 1.0f, .damage_material_modifier_22 = 1.0f,
    .response = { [9] = 3, [11] = 3, [13] = 3, [14] = 3, [15] = 3,
        [16] = 2, [17] = 3, [19] = 3, [20] = 3, [21] = 3, [23] = 3,
        [24] = 3, [28] = 3, [29] = 3, [32] = 2 }
};

static float f32(uint32_t bits)
{
    float value;
    memcpy(&value, &bits, sizeof value);
    return value;
}

static float dot3(const float *a, const float *b)
{
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
}

static float length3(const float *v)
{
    return sqrtf(dot3(v, v));
}

static float seed_range(uint32_t *seed, float lower, float upper)
{
    float unit;
    *seed = *seed * 1664525u + 1013904223u;
    unit = (float)(*seed >> 16) / 65535.0f;
    return lower + (upper - lower) * unit;
}

static uint16_t seed_u16(uint32_t *seed)
{
    *seed = *seed * 1664525u + 1013904223u;
    return (uint16_t)(*seed >> 16);
}

void shot_random_cone(const float axis[3], const float (*directions)[3], unsigned direction_count,
                      const shot_cone *cone, float error_fraction, uint32_t *seed, float result[3])
{
    float random_direction[3], rotation_axis[3], magnitude, angle, outer;
    uint32_t pick;
    int i;
    memcpy(result, axis, 3 * sizeof(float));
    if (!directions || !direction_count || !cone || !seed) return;

    pick = (uint32_t)direction_count * (uint32_t)seed_u16(seed) >> 16;
    if (pick >= direction_count) return;
    memcpy(random_direction, directions[pick], sizeof random_direction);
    rotation_axis[0] = axis[1] * random_direction[2] - axis[2] * random_direction[1];
    rotation_axis[1] = axis[2] * random_direction[0] - axis[0] * random_direction[2];
    rotation_axis[2] = axis[0] * random_direction[1] - axis[1] * random_direction[0];
    magnitude = sqrtf(rotation_axis[0] * rotation_axis[0] +
                      rotation_axis[1] * rotation_axis[1] +
                      rotation_axis[2] * rotation_axis[2]);
    if (magnitude < 0.0001f) return;
    rotation_axis[0] *= 1.0f / magnitude;
    rotation_axis[1] *= 1.0f / magnitude;
    rotation_axis[2] *= 1.0f / magnitude;

    outer = cone->error_lower_bound +
        (cone->error_upper_bound - cone->error_lower_bound) * error_fraction;
    angle = cone->inner_cone_angle +
        (outer - cone->inner_cone_angle) * ((float)seed_u16(seed) / 65535.0f);
    {
        float cosine = (float)cos((double)angle);
        float sine = (float)sin((double)angle);
        float dot = rotation_axis[0] * result[0] + rotation_axis[1] * result[1] +
                    rotation_axis[2] * result[2];
        float one_minus_cosine_times_dot = dot * (1.0f - cosine);
        float cross[3];
        cross[0] = rotation_axis[2] * result[1] - result[2] * rotation_axis[1];
        cross[1] = rotation_axis[0] * result[2] - result[0] * rotation_axis[2];
        cross[2] = rotation_axis[1] * result[0] - result[1] * rotation_axis[0];
        for (i = 0; i < 3; i++)
            result[i] = cosine * result[i] + one_minus_cosine_times_dot * rotation_axis[i] -
                        sine * cross[i];
    }
}

void shot_spawn(shot *s, const float origin[3], const float forward[3], const shot_def *def)
{
    float speed = f32(def->velocity_bits);
    s->position[0] = origin[0];
    s->position[1] = origin[1];
    s->position[2] = origin[2];
    s->velocity[0] = forward[0] * speed;
    s->velocity[1] = forward[1] * speed;
    s->velocity[2] = forward[2] * speed;
    s->odometer = 0.0f;
    s->deceleration_timer = def->deceleration_start > 0.0f ? 0.0f : 1.0f;
    s->deceleration_timer_delta = def->deceleration_start > 0.0f && speed != 0.0f ?
        def->deceleration_start / speed : 0.0f;
    s->underwater = 0;
    s->action = SHOT_NONE;
    s->alive = 1;
    s->damage = 0.0f;
    s->hit_object = 0;
    s->hit_object_this_tick = 0;
    s->hit_surface = 0;
    s->hit_material_type = -1;
    s->ignore_target = 0;
    s->attached = 0;
    s->attached_target = 0;
    s->collided_once = 0;
    s->stopped_after_collision = 0;
    s->detonation_timer = 0.0f;
    s->detonation_timer_delta = 0.0f;
    s->attached_damage_event = 0;
    s->damage_modifier_21 = 0.0f;
    s->damage_modifier_22 = 0.0f;
    s->damage_body_material_type = -1;
    s->damage_shield_material_type = -1;
    s->damage_resistance_index = -1;
    s->damage_body_modifier = 1.0f;
    s->damage_shield_modifier = 1.0f;
    s->damage_material_types_valid = 0;
    s->hit_node_index = -1;
    s->hit_damage_part = -1;
    s->hit_region_index = -1;
}

void shot_spawn_seeded(shot *s, const float origin[3], const float forward[3],
                       const shot_def *def, uint32_t *seed)
{
    float seconds;
    shot_spawn(s, origin, forward, def);
    if (!def) return;
    if (def->projectile_flags & (1u << 2)) seconds = def->timer_lower_bound;
    else if (seed)
        seconds = seed_range(seed, def->timer_lower_bound, def->timer_upper_bound);
    else seconds = def->timer_lower_bound;
    if (seconds * 30.0f >= 1.0f) s->detonation_timer_delta = 1.0f / (seconds * 30.0f);
}

int shot_pool_find_free(const shot *pool, unsigned capacity)
{
    unsigned i;
    if (!pool) return -1;
    for (i = 0; i < capacity; ++i)
        if (!pool[i].alive) return (int)i;
    return -1;
}

int shot_pool_spawn_cone(shot *pool, const shot_def **pool_defs, unsigned capacity, const shot_def *def,
                         const float origin[3], const float forward[3], int pellets,
                         const float (*directions)[3], unsigned direction_count,
                         const shot_cone *cone, float error_fraction,
                         int distribution_function, float distribution_angle, uint32_t *seed,
                         int *dropped)
{
    float first_forward[3];
    int spawned = 0, lost = 0, i;
    if (dropped) *dropped = 0;
    if (!pool || !def || !origin || !forward || pellets <= 0) return 0;
    for (i = 0; i < pellets; ++i) {
        float pellet_forward[3];
        int slot;
        if (cone && directions && direction_count && seed) {
            /* CE samples each pellet first, even when identical-error later
             * replaces its direction and even when object_new then fails. */
            shot_random_cone(forward, directions, direction_count, cone,
                             error_fraction, seed, pellet_forward);
            if (i == 0) memcpy(first_forward, pellet_forward, sizeof first_forward);
            else if (cone->trigger_flags & (1u << 12))
                memcpy(pellet_forward, first_forward, sizeof pellet_forward);
        } else {
            memcpy(pellet_forward, forward, sizeof pellet_forward);
        }
        if (distribution_function == 1 && distribution_angle != 0.0f) {
            float up[3];
            float ai = fabsf(pellet_forward[0]);
            float aj = fabsf(pellet_forward[1]);
            float ak = fabsf(pellet_forward[2]);
            float magnitude;
            int offset;
            if (pellets & 1) {
                if (i == 0) offset = 0;
                else {
                    int step = i - 1;
                    offset = step & 1 ? step >> 1 : -(step >> 1);
                }
            }
            if (ai <= aj && ai <= ak) {
                up[0] = 0.0f; up[1] = pellet_forward[2]; up[2] = -pellet_forward[1];
            } else if (aj <= ak) {
                up[0] = -pellet_forward[2]; up[1] = 0.0f; up[2] = pellet_forward[0];
            } else {
                up[0] = pellet_forward[1]; up[1] = -pellet_forward[0]; up[2] = 0.0f;
            }
            magnitude = length3(up);
            if (magnitude > 0.0f) {
                float angle, sine, cosine, dot, cross[3];
                up[0] /= magnitude; up[1] /= magnitude; up[2] /= magnitude;
                if (pellets & 1) angle = (float)offset * distribution_angle;
                else {
                    float even_offset = (float)(i >> 1) - 0.5f;
                    if (i & 1) even_offset = -even_offset;
                    angle = even_offset * distribution_angle;
                }
                sine = sinf(angle); cosine = cosf(angle);
                dot = dot3(up, pellet_forward);
                cross[0] = up[2] * pellet_forward[1] - pellet_forward[2] * up[1];
                cross[1] = up[0] * pellet_forward[2] - pellet_forward[0] * up[2];
                cross[2] = up[1] * pellet_forward[0] - pellet_forward[1] * up[0];
                pellet_forward[0] = cosine * pellet_forward[0] + dot * (1.0f - cosine) * up[0] - sine * cross[0];
                pellet_forward[1] = cosine * pellet_forward[1] + dot * (1.0f - cosine) * up[1] - sine * cross[1];
                pellet_forward[2] = cosine * pellet_forward[2] + dot * (1.0f - cosine) * up[2] - sine * cross[2];
            }
        }
        slot = shot_pool_find_free(pool, capacity);
        if (slot < 0) { lost++; continue; }
        shot_spawn_seeded(&pool[slot], origin, pellet_forward, def, seed);
        if (pool_defs) pool_defs[slot] = def;
        spawned++;
    }
    if (dropped) *dropped = lost;
    return spawned;
}

static int response_of(const shot_def *def, int material)
{
    if (material < 0 || material >= SHOT_MATERIALS) return 0;
    switch (def->response[material]) {
    case 1: return SHOT_DETONATE;
    case 2: return SHOT_REFLECT;
    case 3: return SHOT_OVERPENETRATE;
    case 4: return SHOT_ATTACH;
    default: return SHOT_DISAPPEAR;
    }
}

static float damage_material_modifier(const shot_def *def, int material, int attached)
{
    if (material < 0 || material >= SHOT_MATERIALS) return 1.0f;
    if (def->damage_materials_valid) {
        return attached ? def->attached_damage_material_modifier[material] :
            def->damage_material_modifier[material];
    }
    if (material == 21) return attached ? def->attached_damage_material_modifier_21 :
        def->damage_material_modifier_21;
    if (material == 22) return attached ? def->attached_damage_material_modifier_22 :
        def->damage_material_modifier_22;
    return 1.0f;
}

static void set_target_damage_modifiers(shot *s, const shot_def *def,
    const shot_scene *scene, int attached, int damage_index)
{
    if (!scene || !scene->target_damage_material_types_valid) return;
    s->damage_resistance_index = damage_index >= 0 ? (int16_t)damage_index :
        (scene->target_damage_resistance_index_valid ? scene->target_damage_resistance_index : -1);
    s->damage_body_material_type = scene->target_body_damage_material_type;
    s->damage_shield_material_type = scene->target_shield_damage_material_type;
    s->damage_body_modifier = damage_material_modifier(def,
        s->damage_body_material_type, attached);
    s->damage_shield_modifier = damage_material_modifier(def,
        s->damage_shield_material_type, attached);
    s->damage_material_types_valid = 1;
}

static int potential_response_of(const shot_def *def, int material, int object_is_unit,
                                 float impact_angle, float impact_velocity, uint32_t *seed)
{
    int response;
    if (material < 0 || material >= SHOT_MATERIALS) return 0;
    response = def->response[material];
    if (def->potential_response[material] != 0 &&
        (def->potential_angle_upper[material] == 0.0f ||
            (impact_angle >= def->potential_angle_lower[material] &&
             impact_angle <= def->potential_angle_upper[material])) &&
        (def->potential_velocity_upper[material] == 0.0f ||
            (impact_velocity >= def->potential_velocity_lower[material] &&
             impact_velocity <= def->potential_velocity_upper[material])) &&
        (!(def->potential_flags[material] & 1u) || object_is_unit) &&
        seed && seed_range(seed, 0.0f, 1.0f) >= def->potential_skip_fraction[material])
        response = def->potential_response[material];
    return response;
}

static void reflect_with_friction(float velocity[3], const float normal[3],
                                  float parallel_friction, float perpendicular_friction)
{
    float scale = dot3(velocity, normal);
    float dd = dot3(normal, normal);
    int i;
    if (dd == 0.0f) return;
    scale /= dd;
    for (i = 0; i < 3; i++) {
        float parallel = normal[i] * scale;
        float perpendicular = velocity[i] - parallel;
        velocity[i] = (1.0f - perpendicular_friction) * perpendicular -
            (1.0f - parallel_friction) * parallel;
    }
}

static int nearest_hit(
    const shot *s, const shot_scene *scene,
    const float end[3], float *t, float normal[3], int *object_hit, int *material,
    int *damage_index, int16_t *node_index, int16_t *damage_part, int16_t *region_index)
{
    float segment[3], best;
    int found = 0, i;
    *damage_index = -1;
    *node_index = -1;
    *damage_part = -1;
    *region_index = -1;
    for (i = 0; i < 3; i++) segment[i] = end[i] - s->position[i];
    best = 2.0f;
    if (scene && scene->bsp) {
        collide_hit hit;
        if (collide_test_vector(scene->bsp, s->position, segment, 1.0f, COLLIDE_FRONT, &hit) &&
            hit.t > 0.0f && hit.t < best && hit.surface >= 0) {
            int16_t material_index = -1;
            memcpy(&material_index, scene->bsp->surfaces + (size_t)hit.surface * 12 + 10, 2);
            best = hit.t;
            *material = collide_material_type(scene->bsp, material_index);
            *object_hit = 0;
            if (hit.plane >= 0 && (uint32_t)hit.plane < scene->bsp->plane_count) {
                const float *plane = scene->bsp->planes + (size_t)hit.plane * 4;
                normal[0] = plane[0];
                normal[1] = plane[1];
                normal[2] = plane[2];
            }
            found = 1;
        }
    }
    if (scene && scene->plane) {
        float dist = dot3(s->position, scene->plane_normal) - scene->plane_d;
        float along = dot3(segment, scene->plane_normal);
        if (along != 0.0f) {
            float hit_t = -dist / along;
            if (hit_t > 0.0f && hit_t <= 1.0f && hit_t < best) {
                best = hit_t;
                *material = scene->plane_material;
                *object_hit = 0;
                normal[0] = scene->plane_normal[0];
                normal[1] = scene->plane_normal[1];
                normal[2] = scene->plane_normal[2];
                found = 1;
            }
        }
    }
    if (scene && scene->target && !s->ignore_target && scene->target_radius > 0.0f) {
        float offset[3], a, b, c, disc;
        for (i = 0; i < 3; i++) offset[i] = s->position[i] - scene->target_center[i];
        a = dot3(segment, segment);
        b = 2.0f * dot3(offset, segment);
        c = dot3(offset, offset) - scene->target_radius * scene->target_radius;
        disc = b * b - 4.0f * a * c;
        if (a > 0.0f && disc >= 0.0f) {
            float root = sqrtf(disc);
            float hit_t = (-b - root) / (2.0f * a);
            if (hit_t <= 0.0f) hit_t = (-b + root) / (2.0f * a);
            if (hit_t > 0.0f && hit_t <= 1.0f && hit_t < best) {
                best = hit_t;
                *material = scene->target_material;
                *object_hit = 1;
                *damage_index = scene->target_damage_resistance_index_valid ?
                    scene->target_damage_resistance_index : -1;
                for (i = 0; i < 3; i++)
                    normal[i] = offset[i] + segment[i] * hit_t;
                found = 1;
            }
        }
    }
    if (scene && scene->actor_mesh && scene->actor_node_to_world && !s->ignore_target) {
        collpack_actor_hit hit;
        if (collpack_actor_ray(scene->actor_mesh, scene->actor_node_to_world,
                s->position, segment, best, &hit) == 1 && hit.distance > 0.0f && hit.distance < best) {
            best = hit.distance;
            *material = scene->target_material;
            *object_hit = 1;
            *damage_index = hit.resistance_index;
            *node_index = hit.node_index;
            *damage_part = hit.damage_part;
            *region_index = hit.region_index;
            normal[0] = hit.normal[0];
            normal[1] = hit.normal[1];
            normal[2] = hit.normal[2];
            found = 1;
        }
    }
    *t = best;
    return found;
}

int shot_tick(shot *s, const shot_def *def, const shot_scene *scene, uint32_t *seed)
{
    float time_left = 1.0f;
    float gravity_scale;
    float damage_range_lower, damage_range_upper;
    int collisions = 0;
    if (!s->alive) return 0;
    if (scene && s->underwater != (scene->underwater != 0)) {
        float initial_speed = f32(def->velocity_bits);
        s->underwater = scene->underwater != 0;
        damage_range_lower = s->underwater ? def->water_damage_range_lower_bound :
            def->deceleration_start;
        if (damage_range_lower > 0.0f && initial_speed != 0.0f) {
            s->deceleration_timer_delta = damage_range_lower / initial_speed;
        } else {
            s->deceleration_timer = 1.0f;
            s->deceleration_timer_delta = 0.0f;
        }
    }
    gravity_scale = s->underwater ? def->water_gravity_scale : def->air_gravity_scale;
    damage_range_lower = s->underwater ? def->water_damage_range_lower_bound :
        def->deceleration_start;
    damage_range_upper = s->underwater ? def->water_damage_range_upper_bound :
        def->deceleration_end;
    s->hit_object_this_tick = 0;
    s->attached_damage_event = 0;
    if (s->attached) {
        s->detonation_timer += s->detonation_timer_delta;
        if (s->detonation_timer >= 1.0f) {
            if (s->attached_target) {
                float scale = 1.0f;
                float random_damage = seed ?
                    seed_range(seed, def->attached_damage_lower, def->attached_damage_upper) :
                    def->attached_damage_lower;
                s->damage = (1.0f - scale) * def->attached_damage_minimum + random_damage * scale;
                s->hit_object_this_tick = 1;
                s->attached_damage_event = 1;
                s->damage_modifier_21 = def->attached_damage_material_modifier_21;
                s->damage_modifier_22 = def->attached_damage_material_modifier_22;
            }
            s->action = SHOT_DETONATE;
            s->alive = 0;
        }
        return s->alive;
    }
    /* Halo CE and Halo-64 both fall through from the "after first bounce"
     * switch arm into the at-rest arm, so modes 1 and 2 actually gate on the
     * stopped-after-collision flag. Preserve that source behavior. */
    if (def->detonation_timer_starts == 0 ||
        ((def->detonation_timer_starts == 1 || def->detonation_timer_starts == 2) &&
            s->stopped_after_collision) ||
        def->detonation_timer_starts < 0 || def->detonation_timer_starts > 2) {
        s->detonation_timer += s->detonation_timer_delta;
        if (s->detonation_timer >= 1.0f) {
            s->action = SHOT_DETONATE;
            s->alive = 0;
            return 0;
        }
    }
    while (s->alive && s->action == SHOT_NONE && time_left > 0.0f && collisions < 4) {
        float speed = length3(s->velocity);
        float deceleration = 0.0f;
        float new_velocity[3], average[3], end[3], fraction;
        int i;
        float hit_t, normal[3];
        int object_hit = 0, material = 0, hit, damage_index;
        int16_t hit_node = -1, hit_part = -1, hit_region = -1;
        if (f32(def->velocity_bits) != def->final_velocity &&
            damage_range_upper != damage_range_lower) {
            float initial_speed = f32(def->velocity_bits);
            float interval = damage_range_upper - damage_range_lower;
            deceleration = (initial_speed * initial_speed -
                def->final_velocity * def->final_velocity) / (2.0f * interval);
        }
        for (i = 0; i < 3; i++) {
            new_velocity[i] = s->velocity[i];
            average[i] = s->velocity[i];
        }
        /* The CE wander scale is exactly zero at target distances <= 2.
         * Reproduce that bounded region without inventing the seeded global
         * wander table; callers must explicitly provide an aim-assist target. */
        if (scene && scene->guidance_target && def->guided_angular_velocity > 0.0f) {
            float target_vector[3], rotation_axis[3];
            float target_distance, speed = length3(s->velocity);
            float angle = def->guided_angular_velocity * (1.0f / 30.0f);
            for (i = 0; i < 3; i++) target_vector[i] = scene->target_center[i] - s->position[i];
            target_distance = length3(target_vector);
            if (target_distance <= 2.0f && dot3(target_vector, s->velocity) > 0.0f && speed > 0.0f) {
                rotation_axis[0] = s->velocity[1] * target_vector[2] - s->velocity[2] * target_vector[1];
                rotation_axis[1] = s->velocity[2] * target_vector[0] - s->velocity[0] * target_vector[2];
                rotation_axis[2] = s->velocity[0] * target_vector[1] - s->velocity[1] * target_vector[0];
                {
                    float axis_length = length3(rotation_axis);
                    if (axis_length > 0.0f) {
                        float sine = sinf(angle), cosine = cosf(angle);
                        float dot;
                        for (i = 0; i < 3; i++) rotation_axis[i] /= axis_length;
                        dot = dot3(rotation_axis, new_velocity) * (1.0f - cosine);
                        {
                            float cross[3] = {
                                rotation_axis[2] * new_velocity[1] - new_velocity[2] * rotation_axis[1],
                                rotation_axis[0] * new_velocity[2] - new_velocity[0] * rotation_axis[2],
                                rotation_axis[1] * new_velocity[0] - new_velocity[1] * rotation_axis[0]
                            };
                            for (i = 0; i < 3; i++)
                                new_velocity[i] = cosine * new_velocity[i] + dot * rotation_axis[i] - sine * cross[i];
                        }
                    }
                }
            }
        }
        s->deceleration_timer += s->deceleration_timer_delta;
        if (s->deceleration_timer >= 1.0f && speed > def->final_velocity && deceleration != 0.0f) {
            float final_speed = speed - deceleration * time_left;
            if (final_speed <= def->final_velocity) {
                float fraction = (speed - def->final_velocity) /
                    (deceleration * time_left);
                final_speed = def->final_velocity * 0.99f;
                for (i = 0; i < 3; i++) {
                    float original_velocity = s->velocity[i];
                    new_velocity[i] *= final_speed / speed;
                    average[i] = (new_velocity[i] + original_velocity) * fraction * 0.5f +
                        (1.0f - fraction) * new_velocity[i];
                }
            } else {
                float scale = final_speed / speed;
                for (i = 0; i < 3; i++) {
                    new_velocity[i] *= scale;
                    average[i] = (new_velocity[i] + s->velocity[i]) * 0.5f;
                }
            }
        } else if (s->deceleration_timer >= 1.0f &&
                   def->maximum_range == 0.0f && def->timer_upper_bound == 0.0f &&
                   def->minimum_velocity <= def->final_velocity &&
                   (deceleration != 0.0f || s->odometer >= def->maximum_damage_distance)) {
            /* projectile_update's source-order special case: projectiles with
             * no range/timer and a minimum speed below final velocity vanish
             * once their damage/deceleration travel is exhausted. */
            s->action = SHOT_DISAPPEAR;
        } else if (s->deceleration_timer >= 1.0f &&
                   speed < def->final_velocity && speed > 0.0f) {
            float scale = def->final_velocity / speed * 0.99f;
            for (i = 0; i < 3; i++) new_velocity[i] *= scale;
        }
        if (s->action == SHOT_DISAPPEAR) {
            s->alive = 0;
            break;
        }
        new_velocity[2] -= SHOT_GRAVITY * gravity_scale * time_left;
        average[2] -= SHOT_GRAVITY * gravity_scale * time_left * 0.5f;
        fraction = 1.0f;
        if (def->maximum_range != 0.0f && speed * time_left + s->odometer > def->maximum_range) {
            fraction = speed != 0.0f ? (def->maximum_range - s->odometer) / speed * time_left : 0.0f;
            s->action = SHOT_DETONATE;
        }
        for (i = 0; i < 3; i++) end[i] = s->position[i] + average[i] * fraction * time_left;
        hit = nearest_hit(s, scene, end, &hit_t, normal, &object_hit, &material,
            &damage_index, &hit_node, &hit_part, &hit_region);
        if (hit) {
            float traveled[3];
            int response, object_overpenetrated = 0;
            float angular_noise, velocity_noise;
            collisions++;
            for (i = 0; i < 3; i++) {
                traveled[i] = (end[i] - s->position[i]) * hit_t;
                s->position[i] += traveled[i];
            }
            s->odometer += length3(traveled);
            time_left = 1.0f - hit_t;
            s->hit_material_type = (int16_t)material;
            if (normal[2] > 0.3f) s->collided_once = 1;
            new_velocity[2] += SHOT_GRAVITY * gravity_scale * time_left;
            if (object_hit) {
                float impact_speed = length3(new_velocity);
                float damage_scale = 1.0f;
                s->hit_object = 1;
                s->hit_object_this_tick = 1;
                s->hit_node_index = hit_node;
                s->hit_damage_part = hit_part;
                s->hit_region_index = hit_region;
                set_target_damage_modifiers(s, def, scene, 0, damage_index);
                if (def->final_velocity != f32(def->velocity_bits)) {
                    float initial_speed = fabsf(f32(def->velocity_bits));
                    damage_scale = (impact_speed - def->final_velocity) /
                        (initial_speed - def->final_velocity);
                    if (damage_scale < 0.0f) damage_scale = 0.0f;
                    if (damage_scale > 1.0f) damage_scale = 1.0f;
                }
                if (seed) {
                    float random_damage = seed_range(seed, def->damage_lower, def->damage_upper);
                    s->damage = (1.0f - damage_scale) * def->damage_minimum +
                        random_damage * damage_scale;
                }
            }
            {
                float impact_speed = -dot3(new_velocity, normal);
                float speed = length3(new_velocity);
                float normal_speed = length3(normal);
                float impact_angle = 0.0f;
                angular_noise = material >= 0 && material < SHOT_MATERIALS ?
                    def->angular_noise[material] : 0.0f;
                velocity_noise = material >= 0 && material < SHOT_MATERIALS ?
                    def->velocity_noise[material] : 0.0f;
                /* CE consumes velocity- and angle-noise draws before the
                 * short-circuited potential-response tests, including zero. */
                if (seed) {
                    impact_speed += seed_range(seed, -velocity_noise, 0.0f);
                    impact_angle = seed_range(seed, -angular_noise, angular_noise);
                }
                if (speed != 0.0f && normal_speed != 0.0f) {
                    float cosine = dot3(new_velocity, normal) / (speed * normal_speed);
                    if (cosine > 1.0f) cosine = 1.0f;
                    if (cosine < -1.0f) cosine = -1.0f;
                    impact_angle += acosf(cosine) - 1.57079632679f;
                }
                response = response_of(def, material);
                {
                    int selected = potential_response_of(def, material,
                        object_hit && scene && scene->target_is_unit,
                        impact_angle, impact_speed, seed);
                    if (selected) {
                        switch (selected) {
                        case 1: response = SHOT_DETONATE; break;
                        case 2: response = SHOT_REFLECT; break;
                        case 3: response = SHOT_OVERPENETRATE; break;
                        case 4: response = SHOT_ATTACH; break;
                        default: response = SHOT_DISAPPEAR; break;
                        }
                    }
                }
            }
            angular_noise = material >= 0 && material < SHOT_MATERIALS ?
                def->angular_noise[material] : 0.0f;
            velocity_noise = material >= 0 && material < SHOT_MATERIALS ?
                def->velocity_noise[material] : 0.0f;
            if (response == SHOT_OVERPENETRATE && !object_hit) response = SHOT_DETONATE;
            if (response == SHOT_OVERPENETRATE && object_hit) {
                float friction = material >= 0 && material < SHOT_MATERIALS ?
                    def->initial_friction[material] : 0.0f;
                for (i = 0; i < 3; i++) {
                    new_velocity[i] *= 1.0f - friction;
                    s->velocity[i] = new_velocity[i];
                }
                /* projectile_collision sets ignore_object_index after applying
                 * initial_friction, preventing a second hit on the same object. */
                s->ignore_target = 1;
                s->action = SHOT_NONE;
                object_overpenetrated = 1;
            }
            if (response == SHOT_REFLECT) {
                reflect_with_friction(new_velocity, normal,
                    material >= 0 && material < SHOT_MATERIALS ? def->parallel_friction[material] : 0.0f,
                    material >= 0 && material < SHOT_MATERIALS ? def->perpendicular_friction[material] : 0.0f);
            } else if (response == SHOT_ATTACH) {
                if (object_hit) set_target_damage_modifiers(s, def, scene, 1, -1);
                new_velocity[0] = new_velocity[1] = new_velocity[2] = 0.0f;
                s->velocity[0] = s->velocity[1] = s->velocity[2] = 0.0f;
                s->attached = 1;
                s->attached_target = object_hit;
                s->stopped_after_collision = 1;
                s->hit_surface = !object_hit;
                s->action = SHOT_NONE;
                if ((def->projectile_flags & (1u << 2)) && def->timer_upper_bound * 30.0f >= 1.0f)
                    s->detonation_timer_delta = 1.0f / (def->timer_upper_bound * 30.0f);
            } else if (!object_overpenetrated) {
                new_velocity[0] = new_velocity[1] = new_velocity[2] = 0.0f;
                s->velocity[0] = s->velocity[1] = s->velocity[2] = 0.0f;
                s->action = response == SHOT_DETONATE ? SHOT_DETONATE : SHOT_DISAPPEAR;
                s->hit_surface = 1;
                s->alive = 0;
            }
            if (angular_noise != 0.0f && seed && scene && scene->directions &&
                scene->direction_count) {
                shot_cone noise = {0.0f, 0.0f, angular_noise, 0};
                float noisy_velocity[3];
                shot_random_cone(new_velocity, scene->directions, scene->direction_count,
                    &noise, 1.0f, seed, noisy_velocity);
                memcpy(new_velocity, noisy_velocity, sizeof new_velocity);
            }
            if (velocity_noise != 0.0f && seed) {
                float magnitude = length3(new_velocity);
                if (magnitude != 0.0f) {
                    float scale = seed_range(seed, -velocity_noise, velocity_noise) + magnitude;
                    for (i = 0; i < 3; i++) new_velocity[i] *= scale / magnitude;
                }
            }
            if (response == SHOT_REFLECT || response == SHOT_ATTACH || object_overpenetrated) {
                if (length3(new_velocity) < def->minimum_velocity) {
                    if (response == SHOT_ATTACH) return s->alive;
                    s->action = SHOT_DETONATE;
                    s->alive = 0;
                    break;
                }
                for (i = 0; i < 3; i++) s->velocity[i] = new_velocity[i];
                s->action = SHOT_NONE;
            }
        } else {
            float traveled[3];
            for (i = 0; i < 3; i++) {
                traveled[i] = end[i] - s->position[i];
                s->position[i] = end[i];
                s->velocity[i] = new_velocity[i];
            }
            s->odometer += length3(traveled);
            time_left = 0.0f;
        }
    }
    if (s->action == SHOT_DETONATE || s->action == SHOT_DISAPPEAR) s->alive = 0;
    return s->alive;
}
