/* Frag and plasma grenades from the Blood Gulch proj, jpt!, and cyborg tags.
 * A player throw replaces the projectile velocity with grenade_velocity/30.
 * The fuse length is chosen at spawn. It does not run until the grenade is
 * at rest or attached, matching projectile_update. A floor bounce uses the
 * material friction. Plasma sticks to a unit because that potential response
 * is limited to units. The blast is the explosion effect. No heap. */
#ifndef GAME_GRENADE_H
#define GAME_GRENADE_H
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
} grenade;

typedef struct {
    float normal[3];
    float d;
    int material;
    int unit_surface;
} grenade_surface;

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
/* 0 outside the cutoff. Otherwise the scaled damage, and the seed advances. */
float grenade_damage(const grenade_def *def, float distance, uint32_t *seed);
#endif
