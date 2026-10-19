/* Pistol and assault rifle bullets from the Blood Gulch proj and jpt! tags
 * and projectile_update / projectile_collision. Velocity is the tag value
 * per tick. Gravity is global_gravity times the air scale. The shot ends
 * at maximum_range. An object hit deals impact damage through the same
 * 32-bit LCG as real_seed_random_range; these two tags have equal bounds,
 * so the amount does not vary, but the seed still advances. A surface hit
 * reads material_index at byte 10 of the 12-byte collision surface and
 * uses that material's default response. Noise on every response is 0, so
 * the two noise draws advance the seed and add nothing. No heap. */
#ifndef GAME_SHOT_H
#define GAME_SHOT_H
#include "game/collide.h"
#include <stdint.h>

#define SHOT_MATERIALS 33
#define SHOT_NONE 0
#define SHOT_DISAPPEAR 1
#define SHOT_DETONATE 2
#define SHOT_REFLECT 3
#define SHOT_OVERPENETRATE 4

typedef struct {
    uint32_t velocity_bits;
    float final_velocity;
    float deceleration_start;
    float deceleration_end;
    float maximum_range;
    float air_gravity_scale;
    float damage_lower;
    float damage_upper;
    uint8_t response[SHOT_MATERIALS];
} shot_def;

typedef struct {
    float position[3];
    float velocity[3];
    float odometer;
    float deceleration_timer;
    int action;
    int alive;
    float damage;
    int hit_object;
    int hit_surface;
} shot;

typedef struct {
    const collide_bsp *bsp;
    int plane;
    float plane_normal[3];
    float plane_d;
    int16_t plane_material;
    int target;
    float target_center[3];
    float target_radius;
    int16_t target_material;
} shot_scene;

extern const shot_def SHOT_PISTOL;
extern const shot_def SHOT_ASSAULT_RIFLE;

void shot_spawn(shot *s, const float origin[3], const float forward[3], const shot_def *def);
/* seed is the global random seed. A collision advances it. Returns 1 while flying. */
int shot_tick(shot *s, const shot_def *def, const shot_scene *scene, uint32_t *seed);
#endif
