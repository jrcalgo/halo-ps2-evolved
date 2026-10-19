#include "game/shot.h"
#include <math.h>
#include <string.h>

#define SHOT_GRAVITY 0.0035651792f

const shot_def SHOT_PISTOL = {
    0x41200001u, 10.0f, 0.0f, 0.0f, 40.0f, 1.0f, 25.0f, 25.0f,
    {0, 0, 0, 0, 0, 0, 0, 0, 0, 3, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 3, 0, 0, 2},
};

const shot_def SHOT_ASSAULT_RIFLE = {
    0x412CCCCDu, 10.0f, 0.0f, 0.0f, 40.0f, 1.0f, 10.0f, 10.0f,
    {0, 0, 0, 0, 0, 0, 0, 0, 0, 3, 0, 3, 0, 3, 3, 3, 2, 3, 0, 3, 3, 3, 0, 3, 3, 0, 0, 0, 3, 3, 0, 0, 2},
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
    s->action = SHOT_NONE;
    s->alive = 1;
    s->damage = 0.0f;
    s->hit_object = 0;
    s->hit_surface = 0;
}

static int response_of(const shot_def *def, int material)
{
    if (material < 0 || material >= SHOT_MATERIALS) return 0;
    switch (def->response[material]) {
    case 2: return SHOT_REFLECT;
    case 3: return SHOT_OVERPENETRATE;
    default: return SHOT_DISAPPEAR;
    }
}

static void reflect(float velocity[3], const float normal[3])
{
    float scale = dot3(velocity, normal);
    float parallel[3], perpendicular[3];
    int i;
    float dd = dot3(normal, normal);
    if (dd == 0.0f) return;
    scale /= dd;
    for (i = 0; i < 3; i++) {
        parallel[i] = normal[i] * scale;
        perpendicular[i] = velocity[i] - parallel[i];
        velocity[i] = perpendicular[i] - parallel[i];
    }
}

static int nearest_hit(
    const shot *s, const shot_scene *scene,
    const float end[3], float *t, float normal[3], int *object_hit, int *material)
{
    float segment[3], best;
    int found = 0, i;
    for (i = 0; i < 3; i++) segment[i] = end[i] - s->position[i];
    best = 2.0f;
    if (scene && scene->bsp) {
        collide_hit hit;
        if (collide_test_vector(scene->bsp, s->position, segment, 1.0f, COLLIDE_FRONT, &hit) &&
            hit.t > 0.0f && hit.t < best && hit.surface >= 0) {
            int16_t index = 0;
            memcpy(&index, scene->bsp->surfaces + (size_t)hit.surface * 12 + 10, 2);
            best = hit.t;
            *material = index;
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
    if (scene && scene->target && scene->target_radius > 0.0f) {
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
                for (i = 0; i < 3; i++)
                    normal[i] = offset[i] + segment[i] * hit_t;
                found = 1;
            }
        }
    }
    *t = best;
    return found;
}

int shot_tick(shot *s, const shot_def *def, const shot_scene *scene, uint32_t *seed)
{
    float time_left = 1.0f;
    int collisions = 0;
    if (!s->alive) return 0;
    while (s->alive && s->action == SHOT_NONE && time_left > 0.0f && collisions < 4) {
        float speed = length3(s->velocity);
        float deceleration = 0.0f;
        float new_velocity[3], average[3], end[3], fraction;
        int i;
        float hit_t, normal[3];
        int object_hit = 0, material = 0, hit;
        if (def->final_velocity != speed && def->deceleration_end > def->deceleration_start) {
            float initial_speed = f32(def->velocity_bits);
            float interval = def->deceleration_end - def->deceleration_start;
            deceleration = (initial_speed * initial_speed -
                def->final_velocity * def->final_velocity) / (2.0f * interval);
        }
        for (i = 0; i < 3; i++) {
            new_velocity[i] = s->velocity[i];
            average[i] = s->velocity[i];
        }
        if (def->deceleration_start > 0.0f)
            s->deceleration_timer += def->deceleration_start / f32(def->velocity_bits);
        if (s->deceleration_timer >= 1.0f && speed > def->final_velocity && deceleration > 0.0f) {
            float reduced = fmaxf(def->final_velocity, speed - deceleration * time_left);
            float average_speed = (speed + reduced) * 0.5f;
            float end_scale = speed > 0.0f ? reduced / speed : 1.0f;
            float average_scale = speed > 0.0f ? average_speed / speed : 1.0f;
            for (i = 0; i < 3; i++) {
                new_velocity[i] *= end_scale;
                average[i] *= average_scale;
            }
        }
        new_velocity[2] -= SHOT_GRAVITY * def->air_gravity_scale * time_left;
        average[2] -= SHOT_GRAVITY * def->air_gravity_scale * time_left * 0.5f;
        fraction = 1.0f;
        if (def->maximum_range != 0.0f && speed * time_left + s->odometer > def->maximum_range) {
            fraction = speed != 0.0f ? (def->maximum_range - s->odometer) / speed * time_left : 0.0f;
            s->action = SHOT_DETONATE;
        }
        for (i = 0; i < 3; i++) end[i] = s->position[i] + average[i] * fraction * time_left;
        hit = nearest_hit(s, scene, end, &hit_t, normal, &object_hit, &material);
        if (hit) {
            float traveled[3];
            int response;
            collisions++;
            for (i = 0; i < 3; i++) {
                traveled[i] = (end[i] - s->position[i]) * hit_t;
                s->position[i] += traveled[i];
            }
            s->odometer += length3(traveled);
            time_left = 1.0f - hit_t;
            new_velocity[2] += SHOT_GRAVITY * def->air_gravity_scale * time_left;
            if (object_hit && seed) {
                s->damage = seed_range(seed, def->damage_lower, def->damage_upper);
                s->hit_object = 1;
            }
            if (seed) {
                (void)seed_range(seed, 0.0f, 0.0f);
                (void)seed_range(seed, 0.0f, 0.0f);
            }
            response = response_of(def, material);
            if (response == SHOT_OVERPENETRATE && !object_hit) response = SHOT_DETONATE;
            if (response == SHOT_REFLECT) {
                reflect(new_velocity, normal);
                for (i = 0; i < 3; i++) s->velocity[i] = new_velocity[i];
                s->action = SHOT_NONE;
            } else {
                s->velocity[0] = s->velocity[1] = s->velocity[2] = 0.0f;
                s->action = response == SHOT_DETONATE ? SHOT_DETONATE : SHOT_DISAPPEAR;
                s->hit_surface = 1;
                s->alive = 0;
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
    if (s->action == SHOT_DETONATE) s->alive = 0;
    return s->alive;
}
