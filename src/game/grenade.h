/* Frag and plasma grenades from the Blood Gulch proj, jpt!, and cyborg tags.
 * A player throw replaces the projectile velocity with grenade_velocity/30.
 * The fuse length is chosen at spawn. It does not run until the grenade is
 * at rest or attached, matching projectile_update. A floor bounce uses the
 * material friction. Plasma sticks to a unit because that potential response
 * is limited to units. The blast is the explosion effect. No heap. */
#ifndef GAME_GRENADE_H
#define GAME_GRENADE_H
#include "game/collide.h"
#include <stdint.h>

#define GRENADE_CARRY_MAX 4
#define GRENADE_THROW_SPEED (10.0f / 30.0f)

typedef struct {
    float fuse_seconds;
    float falloff;
    float cutoff;
    float damage_minimum;
    float damage_lower;
    float damage_upper;
    float damage_material_modifier_21;
    float damage_material_modifier_22;
    float core_radius;
    uint32_t damage_flags;
    int fixed_fuse;
} grenade_def;

typedef struct {
    float position[3];
    float velocity[3];
    float timer;
    float timer_delta;
    int resting;
    int alive;
    int exploded;
    int bounces;
    int16_t owner_object_index;
} grenade;

struct combat_target;

typedef struct {
    float normal[3];
    float d;
    int material;
    int unit_surface;
} grenade_surface;

/* Read-only material-response view used to audit the bounded tag tables. */
typedef struct {
    int response;
    int potential_response;
    int potential_flags;
    float parallel_friction;
    float perpendicular_friction;
    float potential_skip_fraction;
    float potential_angle_lower_bound;
    float potential_angle_upper_bound;
    float potential_velocity_lower_bound;
    float potential_velocity_upper_bound;
} grenade_material_profile;

extern const grenade_def GRENADE_FRAG;
extern const grenade_def GRENADE_PLASMA;

int grenade_throw(grenade *g, const grenade_def *def, const float origin[3],
    const float aim[3], int *carried, uint32_t *seed);
void grenade_rest(grenade *g);
/* 1 when the fuse finishes this tick. No surface. */
int grenade_tick(grenade *g);
/* Same, and a plane may bounce or stick the grenade. */
int grenade_tick_on(grenade *g, const grenade_def *def,
    const grenade_surface *surface, uint32_t *seed);
/* Sweep the tick's CE-equation segment through the static collision BSP and
 * use the selected retail surface plane/material for projectile response. */
int grenade_tick_bsp(grenade *g, const grenade_def *def,
    const collide_bsp *bsp, uint32_t *seed);
/* 0 outside the cutoff. Otherwise the scaled damage, and the seed advances. */
float grenade_damage(const grenade_def *def, float distance, uint32_t *seed);
/* CE area-damage query for one already-enumerated target. Returns 1 when the
 * target is inside cutoff and passes LOS/ownership checks; outputs the exact
 * center distance and rolled falloff damage. No per-event storage or heap. */
int grenade_blast_target(const grenade *g, const grenade_def *def,
    const collide_bsp *bsp, struct combat_target *target,
    int owner_object_index, uint32_t *seed, float *distance, float *damage);
int grenade_material_profile_get(int plasma, int material, grenade_material_profile *out);
#endif
