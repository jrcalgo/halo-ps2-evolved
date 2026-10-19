/* First-person weapon meshes for the play build.
 * weapons.fp lists all 23 retail weapons. A weapon with no model tag
 * draws the arms only. Q cycles the list. */
#ifndef GAME_PLAY_FP_H
#define GAME_PLAY_FP_H
#include "game/gun.h"
#include "game/shot.h"

#define PLAY_FP_AMMO 40
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
    float rate, rate_final, accel, decel, chamber;
} play_fp_ammo;

/* One primary projectile in weapons.fp, after the AMO1 magazines. */
typedef struct {
    uint32_t velocity_bits;
    float final_velocity;
    float deceleration_start;
    float deceleration_end;
    float maximum_range;
    float air_gravity_scale;
    float damage_lower;
    float damage_upper;
    uint8_t response[33];
    uint8_t has_projectile;
    uint8_t pellets;
    uint8_t pad;
} play_fp_proj;

static inline void play_fp_apply_proj(shot_def *def, const play_fp_proj *proj)
{
    int i;
    def->velocity_bits = proj->velocity_bits;
    def->final_velocity = proj->final_velocity;
    def->deceleration_start = proj->deceleration_start;
    def->deceleration_end = proj->deceleration_end;
    def->maximum_range = proj->maximum_range;
    def->air_gravity_scale = proj->air_gravity_scale;
    def->damage_lower = proj->damage_lower;
    def->damage_upper = proj->damage_upper;
    for (i = 0; i < 33; i++) def->response[i] = proj->response[i];
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
}

/* 0 when host:/weapons.fp loaded. The pistol remains if the file is absent. */
int play_fp_open(void);
int play_fp_count(void);
int play_fp_model_count(void);
const char *play_fp_name(void);
const char *play_fp_path(void);
void play_fp_cycle(void);
/* Magazine of the selected weapon. The pistol when weapons.fp has no magazines. */
const gun_def *play_fp_gun(void);
/* Primary projectile. NULL when the weapon has no projectile tag. */
const shot_def *play_fp_shot(void);
#endif
