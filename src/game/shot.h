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
#define SHOT_MATERIAL_PROFILE_FLOATS 5
#define SHOT_NONE 0
#define SHOT_DISAPPEAR 1
#define SHOT_DETONATE 2
#define SHOT_REFLECT 3
#define SHOT_OVERPENETRATE 4
#define SHOT_ATTACH 5

struct collpack_actor_collision_view;
struct vital_damage_profile;

typedef struct {
    uint32_t velocity_bits;
    float final_velocity;
    float deceleration_start;
    float deceleration_end;
    float maximum_range;
    float air_gravity_scale;
    float damage_minimum;
    float damage_lower;
    float damage_upper;
    float damage_material_modifier_21;
    float damage_material_modifier_22;
    uint8_t response[SHOT_MATERIALS];
    /* projectile_material_response fields, indexed by CE material */
    float initial_friction[SHOT_MATERIALS];
    float parallel_friction[SHOT_MATERIALS];
    float perpendicular_friction[SHOT_MATERIALS];
    float angular_noise[SHOT_MATERIALS];
    float velocity_noise[SHOT_MATERIALS];
    int16_t potential_response[SHOT_MATERIALS];
    uint16_t potential_flags[SHOT_MATERIALS];
    float potential_skip_fraction[SHOT_MATERIALS];
    float potential_angle_lower[SHOT_MATERIALS];
    float potential_angle_upper[SHOT_MATERIALS];
    float potential_velocity_lower[SHOT_MATERIALS];
    float potential_velocity_upper[SHOT_MATERIALS];
    float timer_upper_bound;
    float timer_lower_bound;
    float minimum_velocity;
    float maximum_damage_distance;
    float water_gravity_scale;
    float water_damage_range_lower_bound;
    float water_damage_range_upper_bound;
    uint32_t projectile_flags;
    int16_t detonation_timer_starts;
    float attached_damage_minimum;
    float attached_damage_lower;
    float attached_damage_upper;
    float attached_damage_material_modifier_21;
    float attached_damage_material_modifier_22;
    float guided_angular_velocity;
    uint8_t damage_materials_valid;
    float damage_material_modifier[SHOT_MATERIALS];
    float attached_damage_material_modifier[SHOT_MATERIALS];
} shot_def;

typedef struct {
    float position[3];
    float velocity[3];
    float odometer;
    float deceleration_timer;
    float deceleration_timer_delta;
    int underwater;
    int action;
    int alive;
    float damage;
    int hit_object;
    int hit_object_this_tick;
    int hit_surface;
    int16_t hit_material_type;
    int ignore_target;
    int attached;
    int attached_target;
    int16_t attached_node_index;
    uint8_t attached_node_valid;
    uint8_t attached_pad;
    float attached_local_position[3];
    float attached_target_offset[3];
    int collided_once;
    int stopped_after_collision;
    float detonation_timer;
    float detonation_timer_delta;
    int attached_damage_event;
    float damage_modifier_21;
    float damage_modifier_22;
    int16_t damage_body_material_type;
    int16_t damage_shield_material_type;
    int16_t damage_resistance_index;
    float damage_body_modifier;
    float damage_shield_modifier;
    uint8_t damage_material_types_valid;
    int16_t hit_node_index;
    int16_t hit_damage_part;
    int16_t hit_region_index;
    int16_t hit_object_index;
    int16_t attached_object_index;
    int16_t ignored_object_index;
} shot;

/* Optional multi-object collision views supplied by the bounded play-runtime
 * actor registry. The identity is the stable object-table slot for the map. */
typedef struct {
    int16_t object_index;
    int16_t body_damage_material_type;
    int16_t shield_damage_material_type;
    const struct collpack_actor_collision_view *mesh;
    const struct vital_damage_profile *vitality_profile;
    const float (*node_to_world)[12];
    float center[3];
    float bounds_min[3], bounds_max[3];
} shot_target_view;

typedef struct {
    const collide_bsp *bsp;
    int plane;
    float plane_normal[3];
    float plane_d;
    int16_t plane_material;
    int target;
    int target_is_unit;
    /* Set only when source aim-assist supplied a projectile target. */
    int guidance_target;
    float target_center[3];
    float target_radius;
    int16_t target_material;
    int16_t target_body_damage_material_type;
    int16_t target_shield_damage_material_type;
    int16_t target_damage_resistance_index;
    int target_damage_resistance_index_valid;
    int target_damage_material_types_valid;
    const struct collpack_actor_collision_view *actor_mesh;
    const float (*actor_node_to_world)[12];
    const struct vital_damage_profile *target_vitality_profile;
    const shot_target_view *targets;
    unsigned target_count;
    int underwater;
    const float (*directions)[3];
    unsigned direction_count;
} shot_scene;

typedef struct {
    float inner_cone_angle;
    float error_lower_bound;
    float error_upper_bound;
    uint32_t trigger_flags;
} shot_cone;

extern const shot_def SHOT_PISTOL;
extern const shot_def SHOT_ASSAULT_RIFLE;

void shot_spawn(shot *s, const float origin[3], const float forward[3], const shot_def *def);
/* Projectile creation variant that consumes CE's timer-range random draw. */
void shot_spawn_seeded(shot *s, const float origin[3], const float forward[3],
                       const shot_def *def, uint32_t *seed);
/* First inactive slot, or -1 when the bounded pool is exhausted. */
int shot_pool_find_free(const shot *pool, unsigned capacity);
/* CE trigger_create_projectiles ordering: consume cone RNG per requested
 * projectile before attempting allocation, including dropped projectiles. */
int shot_pool_spawn_cone(shot *pool, const shot_def **pool_defs, unsigned capacity, const shot_def *def,
                         const float origin[3], const float forward[3], int pellets,
                         const float (*directions)[3], unsigned direction_count,
                         const shot_cone *cone, float error_fraction,
                         int distribution_function, float distribution_angle, uint32_t *seed,
                         int *dropped);
/* CE random_vector_in_cone3d using its 16-segment geosphere lookup table. */
void shot_random_cone(const float axis[3], const float (*directions)[3], unsigned direction_count,
                      const shot_cone *cone, float error_fraction, uint32_t *seed, float result[3]);
/* seed is the global random seed. A collision advances it. Returns 1 while flying. */
int shot_tick(shot *s, const shot_def *def, const shot_scene *scene, uint32_t *seed);
#endif
