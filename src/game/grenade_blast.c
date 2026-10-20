#include "game/grenade.h"
#include "game/combat_targets.h"
#include "game/vital.h"
#include <math.h>
#include <string.h>

static float dot3(const float a[3], const float b[3])
{
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
}

static float length3(const float v[3])
{
    return sqrtf(dot3(v, v));
}

static void cross3(const float a[3], const float b[3], float out[3])
{
    out[0] = a[1] * b[2] - a[2] * b[1];
    out[1] = a[2] * b[0] - a[0] * b[2];
    out[2] = a[0] * b[1] - a[1] * b[0];
}

static void normalize3(float value[3])
{
    float length = length3(value);
    if (length > 0.0f) {
        value[0] /= length;
        value[1] /= length;
        value[2] /= length;
    }
}

/* CE real_math.c perpendicular3d: choose the least-aligned coordinate axis
 * with the same tie ordering, then normalize at the call site. */
static void perpendicular3(const float a[3], float out[3])
{
    float i = fabsf(a[0]), j = fabsf(a[1]), k = fabsf(a[2]);
    if (i <= j && i <= k) {
        out[0] = 0.0f; out[1] = a[2]; out[2] = -a[1];
    } else if (j <= k) {
        out[0] = -a[2]; out[1] = 0.0f; out[2] = a[0];
    } else {
        out[0] = a[1]; out[1] = -a[0]; out[2] = 0.0f;
    }
}

static int blast_line_clear(const collide_bsp *bsp, const float start[3],
    const float end[3])
{
    collide_hit hit;
    float vector[3];
    unsigned i;
    if (!bsp) return 1;
    for (i = 0; i < 3; i++) vector[i] = end[i] - start[i];
    return !collide_test_vector(bsp, start, vector, 1.0f, COLLIDE_FRONT, &hit);
}

static int blast_visible(const collide_bsp *bsp, const float epicenter[3],
    const float target[3], float core_radius)
{
    float to_target[3], perpendicular[3], cross[3];
    unsigned i, ray;
    for (i = 0; i < 3; i++) to_target[i] = target[i] - epicenter[i];
    if (core_radius <= 1.0e-6f) return blast_line_clear(bsp, epicenter, target);

    perpendicular3(to_target, perpendicular);
    normalize3(perpendicular);
    cross3(to_target, perpendicular, cross);
    normalize3(cross);
    for (ray = 0; ray < 4; ray++) {
        const float *axis = ray < 2 ? perpendicular : cross;
        float sign = (ray & 1u) ? -core_radius : core_radius;
        float collision_vector[3], offset_point[3], to_center[3];
        collide_hit hit;
        int blocked;
        for (i = 0; i < 3; i++) collision_vector[i] = axis[i] * sign;
        blocked = bsp && collide_test_vector(bsp, epicenter, collision_vector,
            1.0f, COLLIDE_FRONT, &hit);
        for (i = 0; i < 3; i++)
            offset_point[i] = epicenter[i] + collision_vector[i] *
                (blocked ? hit.t : 1.0f);
        if (blocked) {
            for (i = 0; i < 3; i++) to_center[i] = target[i] - offset_point[i];
            blocked = collide_test_vector(bsp, offset_point, to_center,
                1.0f, COLLIDE_FRONT, &hit);
        } else {
            blocked = !blast_line_clear(bsp, offset_point, target);
        }
        if (!blocked) return 1;
    }
    return 0;
}

int grenade_blast_target(const grenade *g, const grenade_def *def,
    const collide_bsp *bsp, combat_target *target, int owner_object_index,
    uint32_t *seed, float *distance_out, float *damage_out)
{
    float center[3], delta[3], distance, damage;
    unsigned axis;
    if (!g || !def || !target || !target->profile || !distance_out || !damage_out)
        return -1;
    *distance_out = 0.0f;
    *damage_out = 0.0f;
    /* CE's damage flag bit 0 excludes the effect owner before any damage RNG. */
    if ((def->damage_flags & 1u) && target->object_index == owner_object_index) return 0;
    for (axis = 0; axis < 3; axis++) {
        center[axis] = (target->bounds_min[axis] + target->bounds_max[axis]) * 0.5f;
        delta[axis] = center[axis] - g->position[axis];
    }
    distance = length3(delta);
    if (distance >= def->cutoff || !blast_visible(bsp, g->position, center,
            def->core_radius)) return 0;
    damage = grenade_damage(def, distance, seed);
    *distance_out = distance;
    *damage_out = damage;
    if (damage > 0.0f && !target->health.dead) {
        float body_modifier = target->body_damage_material_type == 21 ?
            def->damage_material_modifier_21 : 1.0f;
        float shield_modifier = target->shield_damage_material_type == 22 ?
            def->damage_material_modifier_22 : 1.0f;
        vital_hurt_material_region_profile(&target->health, damage, VITAL_BODY,
            target->profile, target->profile->indirect_material_index, -1,
            body_modifier, shield_modifier, 0);
    }
    return 1;
}
