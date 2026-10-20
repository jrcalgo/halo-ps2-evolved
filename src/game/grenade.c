#include "game/grenade.h"
#include <math.h>
#include <string.h>

#define GRENADE_GRAVITY 0.0035651792f
#define GRENADE_REFLECT 2
#define GRENADE_OVERPENETRATE 3
#define GRENADE_ATTACH 4
#define GRENADE_DETONATE 1

typedef struct {
    unsigned char response, potential, potential_flags;
    float parallel, perpendicular, skip, angle_upper, velocity_lower, velocity_upper;
    float angle_lower;
} grenade_material;

static const grenade_material FRAG_MATERIAL[33] = {
    {2, 0, 0, 0.800000012f, 0.899999976f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f},
    {2, 0, 0, 0.800000012f, 0.899999976f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f},
    {2, 0, 0, 0.699999988f, 0.800000012f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f},
    {2, 0, 0, 0.899999976f, 0.949999988f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f},
    {2, 0, 0, 0.800000012f, 0.899999976f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f},
    {2, 0, 0, 0.699999988f, 0.800000012f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f},
    {2, 0, 0, 0.699999988f, 0.800000012f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f},
    {2, 0, 0, 0.699999988f, 0.800000012f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f},
    {2, 0, 0, 0.699999988f, 0.800000012f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f},
    {2, 0, 0, 0.800000012f, 0.899999976f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f},
    {2, 0, 0, 0.600000024f, 0.699999988f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f},
    {2, 0, 0, 0.800000012f, 0.899999976f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f},
    {2, 0, 0, 0.800000012f, 0.899999976f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f},
    {2, 0, 0, 0.800000012f, 0.899999976f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f},
    {2, 0, 0, 0.800000012f, 0.899999976f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f},
    {2, 0, 0, 0.800000012f, 0.899999976f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f},
    {2, 0, 0, 0.800000012f, 0.800000012f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f},
    {2, 0, 0, 0.5f, 0.699999988f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f},
    {2, 0, 0, 0.800000012f, 0.899999976f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f},
    {2, 0, 0, 0.800000012f, 0.899999976f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f},
    {2, 0, 0, 0.600000024f, 0.699999988f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f},
    {2, 0, 0, 0.800000012f, 0.899999976f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f},
    {2, 0, 0, 0.800000012f, 0.899999976f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f},
    {2, 0, 0, 0.800000012f, 0.899999976f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f},
    {2, 0, 0, 0.800000012f, 0.899999976f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f},
    {2, 0, 0, 0.800000012f, 0.899999976f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f},
    {2, 0, 0, 0.800000012f, 0.899999976f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f},
    {2, 0, 0, 0.800000012f, 0.899999976f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f},
    {3, 2, 0, 0.699999988f, 0.699999988f, 0.0f, 0.52359879f, 0.0333333351f, 33.3333359f, 0.0f},
    {2, 3, 0, 0.800000012f, 0.899999976f, 0.200000003f, 0.0f, 0.0f, 0.0f, 0.0f},
    {2, 0, 0, 0.800000012f, 0.899999976f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f},
    {2, 0, 0, 0.550000012f, 0.649999976f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f},
    {2, 0, 0, 0.800000012f, 0.899999976f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f},
};
static const grenade_material PLASMA_MATERIAL[33] = {
    {2, 4, 1, 0.899999976f, 0.949999988f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f},
    {2, 4, 1, 0.899999976f, 0.949999988f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f},
    {2, 4, 1, 0.899999976f, 0.949999988f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f},
    {2, 4, 1, 0.899999976f, 0.949999988f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f},
    {2, 4, 1, 0.899999976f, 0.949999988f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f},
    {2, 4, 1, 0.899999976f, 0.949999988f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f},
    {2, 4, 1, 0.899999976f, 0.949999988f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f},
    {2, 4, 1, 0.899999976f, 0.949999988f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f},
    {2, 4, 1, 0.899999976f, 0.949999988f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f},
    {2, 0, 0, 0.699999988f, 0.800000012f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f},
    {2, 0, 0, 0.699999988f, 0.800000012f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f},
    {2, 4, 1, 0.899999976f, 0.949999988f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f},
    {2, 4, 1, 0.899999976f, 0.949999988f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f},
    {2, 4, 1, 0.899999976f, 0.949999988f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f},
    {2, 4, 1, 0.899999976f, 0.949999988f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f},
    {2, 4, 1, 0.899999976f, 0.949999988f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f},
    {2, 2, 0, 0.800000012f, 0.800000012f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f},
    {2, 4, 1, 0.899999976f, 0.949999988f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f},
    {2, 0, 0, 0.899999976f, 0.949999988f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f},
    {2, 4, 1, 0.899999976f, 0.949999988f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f},
    {2, 4, 1, 0.899999976f, 0.949999988f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f},
    {2, 4, 1, 0.899999976f, 0.949999988f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f},
    {2, 4, 1, 0.899999976f, 0.949999988f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f},
    {2, 4, 1, 0.899999976f, 0.949999988f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f},
    {2, 4, 1, 0.899999976f, 0.949999988f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f},
    {2, 4, 1, 0.899999976f, 0.949999988f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f},
    {2, 0, 0, 0.899999976f, 0.949999988f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f},
    {2, 4, 1, 0.899999976f, 0.949999988f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f},
    {3, 0, 0, 0.5f, 0.5f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f},
    {2, 4, 1, 0.899999976f, 0.949999988f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f},
    {2, 4, 1, 0.899999976f, 0.949999988f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f},
    {2, 4, 1, 0.649999976f, 0.75f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f},
    {2, 0, 0, 0.899999976f, 0.949999988f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f},
};

const grenade_def GRENADE_FRAG = {
    .fuse_seconds = 0.5f, .falloff = 1.5f, .cutoff = 2.5f,
    .damage_minimum = 80.0f, .damage_lower = 120.0f, .damage_upper = 120.0f,
    .damage_material_modifier_21 = 1.0f, .damage_material_modifier_22 = 1.0f,
    .core_radius = 0.4f, .damage_flags = 0x20u, .fixed_fuse = 0
};
const grenade_def GRENADE_PLASMA = {
    .fuse_seconds = 2.0f, .falloff = 0.5f, .cutoff = 2.0f,
    .damage_minimum = 80.0f, .damage_lower = 120.0f, .damage_upper = 120.0f,
    .damage_material_modifier_21 = 1.0f, .damage_material_modifier_22 = 1.0f,
    .core_radius = 0.4f, .damage_flags = 0x20u, .fixed_fuse = 1
};

static const grenade_material *table_for(const grenade_def *def)
{
    if (def == &GRENADE_PLASMA) return PLASMA_MATERIAL;
    return FRAG_MATERIAL;
}

static float seed_range(uint32_t *seed, float lower, float upper)
{
    float unit;
    *seed = *seed * 1664525u + 1013904223u;
    unit = (float)(*seed >> 16) / 65535.0f;
    return lower + (upper - lower) * unit;
}

static float dot3(const float *a, const float *b)
{
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
}

static float length3(const float *v)
{
    return sqrtf(dot3(v, v));
}

static float blast_scale(const grenade_def *def, float distance)
{
    float span = def->cutoff - def->falloff;
    float scale;
    if (span <= 0.0f) return 1.0f;
    scale = 1.0f - (distance - def->falloff) / span;
    if (scale < 0.0f) return 0.0f;
    if (scale > 1.0f) return 1.0f;
    return scale;
}

static void bounce(float velocity[3], const float normal[3], float parallel_friction, float perpendicular_friction)
{
    float scale = dot3(velocity, normal);
    float dd = dot3(normal, normal);
    int i;
    if (dd == 0.0f) return;
    scale /= dd;
    for (i = 0; i < 3; i++) {
        float parallel = normal[i] * scale;
        float tangent = velocity[i] - parallel;
        velocity[i] = (1.0f - perpendicular_friction) * tangent - (1.0f - parallel_friction) * parallel;
    }
}

static int choose_response(const grenade_material *material, int unit_surface,
    const float velocity[3], const float normal[3], uint32_t *seed)
{
    int response = material->response;
    int gates = 1;
    if (seed) {
        (void)seed_range(seed, 0.0f, 0.0f);
        (void)seed_range(seed, 0.0f, 0.0f);
    }
    if (!material->potential) return response;
    if ((material->potential_flags & 1u) && !unit_surface) gates = 0;
    if (gates && (material->angle_lower != 0.0f || material->angle_upper != 0.0f)) {
        float speed = length3(velocity);
        float nlen = length3(normal);
        float cosine, angle;
        if (speed == 0.0f || nlen == 0.0f) gates = 0;
        else {
            cosine = dot3(velocity, normal) / (speed * nlen);
            if (cosine > 1.0f) cosine = 1.0f;
            if (cosine < -1.0f) cosine = -1.0f;
            angle = acosf(cosine) - 1.57079632679f;
            if (angle < material->angle_lower || angle > material->angle_upper) gates = 0;
        }
    }
    if (gates && material->velocity_upper != 0.0f) {
        float impact = -dot3(velocity, normal);
        if (impact < material->velocity_lower || impact > material->velocity_upper) gates = 0;
    }
    if (gates && seed && seed_range(seed, 0.0f, 1.0f) >= material->skip) response = material->potential;
    else if (gates && !seed) response = material->potential;
    return response;
}

int grenade_throw(grenade *g, const grenade_def *def, const float origin[3],
    const float aim[3], int *carried, uint32_t *seed)
{
    float ticks;
    if (*carried <= 0) return 0;
    (*carried)--;
    g->position[0] = origin[0];
    g->position[1] = origin[1];
    g->position[2] = origin[2];
    g->velocity[0] = aim[0] * GRENADE_THROW_SPEED;
    g->velocity[1] = aim[1] * GRENADE_THROW_SPEED;
    g->velocity[2] = aim[2] * GRENADE_THROW_SPEED;
    if (def->fixed_fuse) ticks = def->fuse_seconds * 30.0f;
    else ticks = seed_range(seed, def->fuse_seconds, def->fuse_seconds) * 30.0f;
    g->timer = 0.0f;
    g->timer_delta = ticks >= 1.0f ? 1.0f / ticks : 0.0f;
    g->resting = 0;
    g->alive = 1;
    g->exploded = 0;
    g->bounces = 0;
    g->owner_object_index = -1;
    return 1;
}

void grenade_rest(grenade *g)
{
    if (!g->alive) return;
    g->velocity[0] = g->velocity[1] = g->velocity[2] = 0.0f;
    g->resting = 1;
}

static int advance_fuse(grenade *g)
{
    g->timer += g->timer_delta;
    if (g->timer >= 1.0f) {
        g->exploded = 1;
        g->alive = 0;
        return 1;
    }
    return 0;
}

int grenade_tick_on(grenade *g, const grenade_def *def,
    const grenade_surface *surface, uint32_t *seed)
{
    float time_left = 1.0f;
    int collisions = 0;
    if (!g->alive) return 0;
    if (g->resting) return advance_fuse(g);
    while (g->alive && !g->resting && !g->exploded && time_left > 0.0f && collisions < 4) {
        float new_velocity[3], average[3], end[3];
        int i;
        for (i = 0; i < 3; i++) {
            new_velocity[i] = g->velocity[i];
            average[i] = g->velocity[i];
        }
        new_velocity[2] -= GRENADE_GRAVITY * time_left;
        average[2] -= GRENADE_GRAVITY * time_left * 0.5f;
        for (i = 0; i < 3; i++) end[i] = g->position[i] + average[i] * time_left;
        if (surface) {
            float segment[3], dist, along, hit_t = 2.0f;
            for (i = 0; i < 3; i++) segment[i] = end[i] - g->position[i];
            dist = dot3(g->position, surface->normal) - surface->d;
            along = dot3(segment, surface->normal);
            if (along != 0.0f) hit_t = -dist / along;
            if (hit_t > 0.0f && hit_t <= 1.0f && def) {
                const grenade_material *material = table_for(def);
                int index = surface->material;
                int response;
                float speed2;
                if (index < 0 || index >= 33) index = 0;
                material += index;
                collisions++;
                g->bounces++;
                for (i = 0; i < 3; i++) g->position[i] += segment[i] * hit_t;
                time_left = 1.0f - hit_t;
                new_velocity[2] += GRENADE_GRAVITY * time_left;
                response = choose_response(material, surface->unit_surface, new_velocity, surface->normal, seed);
                if (response == GRENADE_REFLECT)
                    bounce(new_velocity, surface->normal, material->parallel, material->perpendicular);
                else if (response != GRENADE_OVERPENETRATE)
                    new_velocity[0] = new_velocity[1] = new_velocity[2] = 0.0f;
                for (i = 0; i < 3; i++) g->velocity[i] = new_velocity[i];
                speed2 = dot3(g->velocity, g->velocity);
                if (response == GRENADE_ATTACH || (speed2 < 0.0001f && surface->normal[2] > 0.3f &&
                    response != GRENADE_OVERPENETRATE)) {
                    g->resting = 1;
                    if (response == GRENADE_ATTACH) {
                        g->velocity[0] = g->velocity[1] = g->velocity[2] = 0.0f;
                        if (def->fixed_fuse) {
                            float ticks = def->fuse_seconds * 30.0f;
                            g->timer_delta = ticks >= 1.0f ? 1.0f / ticks : 0.0f;
                        }
                    }
                }
                if (response == GRENADE_DETONATE) {
                    g->exploded = 1;
                    g->alive = 0;
                }
                continue;
            }
        }
        for (i = 0; i < 3; i++) {
            g->position[i] = end[i];
            g->velocity[i] = new_velocity[i];
        }
        time_left = 0.0f;
    }
    return g->exploded;
}

int grenade_tick(grenade *g)
{
    return grenade_tick_on(g, 0, 0, 0);
}

int grenade_tick_bsp(grenade *g, const grenade_def *def,
    const collide_bsp *bsp, uint32_t *seed)
{
    grenade_surface surface;
    float end[3], segment[3], plane[4], average_z;
    collide_hit hit;
    int i;
    int16_t material;
    if (!g || !g->alive) return 0;
    if (g->resting || !bsp) return grenade_tick_on(g, def, 0, seed);

    /* Match projectile_update's one-tick ballistic segment. Collision chooses
     * the nearest front-facing BSP surface exactly as the bullet path does. */
    average_z = g->velocity[2] - GRENADE_GRAVITY * 0.5f;
    end[0] = g->position[0] + g->velocity[0];
    end[1] = g->position[1] + g->velocity[1];
    end[2] = g->position[2] + average_z;
    for (i = 0; i < 3; ++i) segment[i] = end[i] - g->position[i];
    if (!collide_test_vector(bsp, g->position, segment, 1.0f, COLLIDE_FRONT, &hit) ||
        hit.t <= 0.0f || hit.surface < 0 || hit.plane < 0 ||
        (uint32_t)hit.surface >= bsp->surface_count ||
        (uint32_t)hit.plane >= bsp->plane_count)
        return grenade_tick_on(g, def, 0, seed);

    memcpy(plane, bsp->planes + (size_t)hit.plane * 4, sizeof plane);
    memcpy(&material, bsp->surfaces + (size_t)hit.surface * 12 + 10, sizeof material);
    surface.normal[0] = plane[0];
    surface.normal[1] = plane[1];
    surface.normal[2] = plane[2];
    surface.d = plane[3];
    surface.material = collide_material_type(bsp, material);
    surface.unit_surface = 0;
    return grenade_tick_on(g, def, &surface, seed);
}

float grenade_damage(const grenade_def *def, float distance, uint32_t *seed)
{
    float scale = blast_scale(def, distance);
    float rolled;
    if (scale <= 0.0f) return 0.0f;
    rolled = seed_range(seed, def->damage_lower, def->damage_upper);
    return ((1.0f - scale) * def->damage_minimum + rolled * scale);
}

int grenade_material_profile_get(int plasma, int material, grenade_material_profile *out)
{
    const grenade_material *record;
    if (!out || material < 0 || material >= 33) return 0;
    record = (plasma ? PLASMA_MATERIAL : FRAG_MATERIAL) + material;
    out->response = record->response;
    out->potential_response = record->potential;
    out->potential_flags = record->potential_flags;
    out->parallel_friction = record->parallel;
    out->perpendicular_friction = record->perpendicular;
    out->potential_skip_fraction = record->skip;
    out->potential_angle_upper_bound = record->angle_upper;
    out->potential_angle_lower_bound = record->angle_lower;
    out->potential_velocity_lower_bound = record->velocity_lower;
    out->potential_velocity_upper_bound = record->velocity_upper;
    return 1;
}
