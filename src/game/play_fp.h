/* First-person weapon meshes for the play build.
 * weapons.fp lists all 23 retail weapons. A weapon with no model tag
 * draws the arms only. Q cycles the list. */
#ifndef GAME_PLAY_FP_H
#define GAME_PLAY_FP_H
#include "game/gun.h"
#include "game/shot.h"

#define PLAY_FP_AMMO 80
#define AMMO_WASTE 1
#define AMMO_CHAMBER 2
#define AMMO_PARTIAL 4
#define AMMO_LATCH 8
#define AMMO_MAGAZINE 16
#define AMMO_TRIGGER 32

/* One magazine record in weapons.fp, after the RMP1 pose maps. */
typedef struct {
    int16_t loaded_max, initial, reloaded, rounds_per_shot;
    int16_t reload_frames, ready_frames, enter_frames, flags;
    int16_t pellets, recharge;
    int16_t trigger_count, weapon_type, overcharged_action, pad;
    float rate, rate_final, accel, decel, chamber, error_accel, error_decel;
    float charge, charged, heat_overheat, heat_recovery, heat_loss, heat_per_round;
} play_fp_ammo;

/* One primary projectile in weapons.fp, after the AMO1 magazines. */
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
    uint8_t response[33];
    uint8_t has_projectile;
    uint8_t pellets;
    uint8_t attached_damage_flags; /* bit 0=headshot, bit 1=multiplayer headshot */
    float damage_material_modifier_21;
    float damage_material_modifier_22;
    float timer_upper_bound;
    float minimum_velocity;
    float maximum_damage_distance;
    uint32_t projectile_flags;
    int16_t detonation_timer_starts;
    uint16_t damage_flags;
    float timer_lower_bound;
    float attached_damage_minimum;
    float attached_damage_lower;
    float attached_damage_upper;
    float attached_damage_material_modifier_21;
    float attached_damage_material_modifier_22;
    float water_gravity_scale;
    float water_damage_range_lower_bound;
    float water_damage_range_upper_bound;
    float guided_angular_velocity;
    float damage_material_modifier[33];
    float attached_damage_material_modifier[33];
} play_fp_proj;

/* File-backed TRG1/PRJ2 records for the currently selected weapon. The
 * runtime caches exactly two triggers, not the full 23-weapon table. */
typedef struct __attribute__((packed)) {
    uint32_t flags;
    int16_t halves[11];
    float values[25];
    char projectile[64];
    char charging_effect[64];
    uint16_t firing_effect_count;
} play_fp_trigger;

/* TRG1 values[] follows weapon_trigger_definition's packed float order. */
enum {
    PLAY_FP_TRIGGER_RATE_INITIAL = 0,
    PLAY_FP_TRIGGER_RATE_FINAL = 1,
    PLAY_FP_TRIGGER_CHARGING_SECONDS = 8,
    PLAY_FP_TRIGGER_CHARGED_SECONDS = 9,
    PLAY_FP_TRIGGER_SPEW_SECONDS = 11,
    PLAY_FP_TRIGGER_DISTRIBUTION_ANGLE = 12,
    PLAY_FP_TRIGGER_ERROR_CONE_INNER = 13,
    PLAY_FP_TRIGGER_ERROR_CONE_LOWER = 14,
    PLAY_FP_TRIGGER_ERROR_CONE_UPPER = 15,
    PLAY_FP_TRIGGER_AGE_GENERATED_PER_ROUND = 17,
    PLAY_FP_TRIGGER_RUNTIME_RATE_ACCEL = 21,
    PLAY_FP_TRIGGER_RUNTIME_RATE_DECEL = 22,
    PLAY_FP_TRIGGER_RUNTIME_ERROR_ACCEL = 23,
    PLAY_FP_TRIGGER_RUNTIME_ERROR_DECEL = 24
};

/* Selected weapon's fixed MAG2 record for one of its two magazine slots. */
typedef struct __attribute__((packed)) {
    uint32_t flags;
    int16_t values[4];
    uint8_t reserved[4];
    float reload_seconds;
    int16_t rounds_reloaded;
    int16_t pad;
    float chamber_seconds;
} play_fp_magazine;

typedef struct __attribute__((packed)) {
    uint32_t flags;
    int16_t secondary_trigger_mode;
    int16_t maximum_alternate_shots_loaded;
    float age_heat_recovery_penalty;
    float age_rate_of_fire_penalty;
    float age_misfire_start;
    float age_misfire_chance;
} play_fp_weapon_trigger_policy;

typedef struct __attribute__((packed)) {
    int16_t shots_lower_bound;
    int16_t shots_upper_bound;
    char effects[3][64];
    char damage_effects[3][64];
} play_fp_firing_effect;

typedef shot_cone play_fp_cone;

static inline void play_fp_apply_proj(shot_def *def, const play_fp_proj *proj)
{
    int i;
    def->velocity_bits = proj->velocity_bits;
    def->final_velocity = proj->final_velocity;
    def->deceleration_start = proj->deceleration_start;
    def->deceleration_end = proj->deceleration_end;
    def->maximum_range = proj->maximum_range;
    def->air_gravity_scale = proj->air_gravity_scale;
    def->damage_minimum = proj->damage_minimum;
    def->damage_lower = proj->damage_lower;
    def->damage_upper = proj->damage_upper;
    def->damage_material_modifier_21 = proj->damage_material_modifier_21;
    def->damage_material_modifier_22 = proj->damage_material_modifier_22;
    def->timer_upper_bound = proj->timer_upper_bound;
    def->minimum_velocity = proj->minimum_velocity;
    def->maximum_damage_distance = proj->maximum_damage_distance;
    for (i = 0; i < 33; i++) def->response[i] = proj->response[i];
    def->projectile_flags = proj->projectile_flags;
    def->damage_flags = proj->damage_flags;
    def->attached_damage_flags = (uint16_t)((proj->attached_damage_flags & 1u) << 1) |
        (uint16_t)((proj->attached_damage_flags & 2u) << 10);
    def->detonation_timer_starts = proj->detonation_timer_starts;
    def->timer_lower_bound = proj->timer_lower_bound;
    def->attached_damage_minimum = proj->attached_damage_minimum;
    def->attached_damage_lower = proj->attached_damage_lower;
    def->attached_damage_upper = proj->attached_damage_upper;
    def->attached_damage_material_modifier_21 = proj->attached_damage_material_modifier_21;
    def->attached_damage_material_modifier_22 = proj->attached_damage_material_modifier_22;
    def->water_gravity_scale = proj->water_gravity_scale;
    def->water_damage_range_lower_bound = proj->water_damage_range_lower_bound;
    def->water_damage_range_upper_bound = proj->water_damage_range_upper_bound;
    def->guided_angular_velocity = proj->guided_angular_velocity;
    def->damage_materials_valid = 1;
    for (i = 0; i < 33; i++) {
        def->damage_material_modifier[i] = proj->damage_material_modifier[i];
        def->attached_damage_material_modifier[i] =
            proj->attached_damage_material_modifier[i];
    }
}

static inline void play_fp_apply_ammo(gun_def *def, const play_fp_ammo *ammo)
{
    def->rate_of_fire = ammo->rate;
    def->rate_final = ammo->rate_final;
    def->rate_accel = ammo->accel;
    def->rate_decel = ammo->decel;
    def->rounds_per_shot = ammo->rounds_per_shot;
    def->rounds_loaded_maximum = ammo->loaded_max;
    def->rounds_total_initial = ammo->initial;
    def->rounds_reloaded = ammo->reloaded;
    def->ready_frames = ammo->ready_frames;
    def->reload_empty_frames = ammo->reload_frames;
    def->chamber_seconds = ammo->chamber;
    def->projectiles_per_shot = ammo->pellets > 0 ? ammo->pellets : 1;
    def->shotgun_enter_frames = ammo->enter_frames;
    def->chamber_every_shot = (ammo->flags & AMMO_CHAMBER) != 0;
    def->wastes_rounds = (ammo->flags & AMMO_WASTE) != 0;
    def->partial_ammo = (ammo->flags & AMMO_PARTIAL) != 0;
    def->latched = (ammo->flags & AMMO_LATCH) != 0;
    def->uses_magazine = (ammo->flags & AMMO_MAGAZINE) != 0;
    def->has_trigger = (ammo->flags & AMMO_TRIGGER) != 0;
    def->rounds_recharged_per_second = ammo->recharge;
    def->error_accel = ammo->error_accel;
    def->error_decel = ammo->error_decel;
    def->charge_seconds = ammo->charge;
    def->charged_seconds = ammo->charged;
    def->heat_overheat = ammo->heat_overheat;
    def->heat_recovery = ammo->heat_recovery;
    def->heat_loss = ammo->heat_loss;
    def->heat_per_round = ammo->heat_per_round;
    def->overcharged_action = ammo->overcharged_action;
    def->trigger_count = ammo->trigger_count;
}

/* 0 when host:/weapons.fp loaded. The pistol remains if the file is absent. */
int play_fp_open(void);
int play_fp_count(void);
int play_fp_model_count(void);
int play_fp_slot(void);
const char *play_fp_name(void);
const char *play_fp_path(void);
void play_fp_cycle(void);
/* Magazine of the selected weapon. The pistol when weapons.fp has no magazines. */
const gun_def *play_fp_gun(void);
/* Primary projectile. NULL when the weapon has no projectile tag. */
const shot_def *play_fp_shot(void);
/* Trigger index 0 or 1 from TRG1; NULL if the extension is unavailable. */
const play_fp_trigger *play_fp_trigger_at(int index);
/* True when CE expects the trigger marker from the weapon object/mount. */
int play_fp_trigger_uses_weapon_origin(int index);
/* Projectile selected by the same trigger in PRJ2, if one is tagged. */
const shot_def *play_fp_trigger_shot(int index);
const play_fp_magazine *play_fp_trigger_magazine(int index);
const play_fp_weapon_trigger_policy *play_fp_weapon_trigger_policy_get(void);
const play_fp_firing_effect *play_fp_firing_effect_at(int trigger, int effect);
/* Retail weapon_new initial rounds, bounded to the loaded maximum. */
int play_fp_trigger_loaded(int16_t loaded[GUN_TRIGGER_MAGAZINES]);
/* Copies the selected weapon's two CE profiles to aligned runtime records. */
int play_fp_trigger_profiles(gun_trigger_profile profiles[GUN_TRIGGER_MAX]);
const play_fp_cone *play_fp_spread(void);
const float (*play_fp_directions(void))[3];
unsigned play_fp_direction_count(void);
#endif
