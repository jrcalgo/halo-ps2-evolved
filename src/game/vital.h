/* Cyborg shield and body from characters\cyborg\cyborg and object_damage_shield
 * / object_damage_body. Vitality is stored normalized, as the object datum
 * does. The diagnostic mesh probe uses direct collision-model resistance
 * indices (indirect record 1/type 21 is the fallback). CE chooses a resistance
 * record from the hit surface, not a generic head/body/legs multiplier. The
 * shot retains node damage-part metadata, but actor-specific damage animation
 * and reaction handling are not implemented yet.
 * Pistol and rifle damage against material 21 is 1.5 and 1. The shield
 * material modifier is 1. Stun threshold/time are 6 damage / 4 seconds.
 * Recharge is the collision
 * tag's runtime velocity, which the map already stores. No heap. */
#ifndef GAME_VITAL_H
#define GAME_VITAL_H
#include "game/shot.h"
#include <stdint.h>

#define VITAL_HEAD 0
#define VITAL_BODY 1
#define VITAL_LEGS 2
#define VITAL_MAX_SHIELD 75.0f
#define VITAL_MAX_BODY 75.0f
#define VITAL_MINIMUM_SHIELD_STUN_DAMAGE 6.0f
#define VITAL_STUN_TICKS 120
#define VITAL_RECHARGE_BITS 0x3c088889u
#define VITAL_DAMAGE_MATERIAL_MAX 40
#define VITAL_DAMAGE_REGION_MAX 16

typedef struct {
    float shield;
    float body;
    short stun;
    int dead;
    uint16_t regions_destroyed_flags;
    uint8_t region_damage[VITAL_DAMAGE_REGION_MAX];
} vital;

typedef struct {
    int16_t material_type;
    float shield_leak_fraction;
    float shield_damage_multiplier;
    float body_damage_multiplier;
} vital_damage_material;

/* Runtime subset of CE damage_resistance + damage_resistance_material.
 * Damage-definition modifiers are supplied per impact because they depend
 * on the target material selected by collision. */
typedef struct vital_damage_profile {
    float maximum_shield;
    float maximum_body;
    float shield_leak_fraction;
    float shield_damage_multiplier;
    float body_damage_multiplier;
    float minimum_shield_stun_damage;
    short shield_stun_ticks;
    float shield_recharge_step;
    int16_t indirect_material_index;
    uint16_t material_count;
    vital_damage_material material[VITAL_DAMAGE_MATERIAL_MAX];
    uint16_t region_count;
    float region_damage_threshold[VITAL_DAMAGE_REGION_MAX];
} vital_damage_profile;

extern const vital_damage_profile VITAL_CYBORG_INDIRECT_PROFILE;

void vital_init(vital *v);
/* Source-equation path: separate damage-definition modifier lookup for the
 * target's shield material and selected body damage material. */
void vital_hurt_profile(vital *v, float amount, int part,
    const vital_damage_profile *profile, float body_material_modifier,
    float shield_material_modifier, int headshot);
/* Collision-backed variant. CE selects a damage-resistance record by
 * collision material index, falling back to indirect_material_index when the
 * hit has no valid direct index. */
void vital_hurt_material_profile(vital *v, float amount, int part,
    const vital_damage_profile *profile, int damage_material_index,
    float body_material_modifier, float shield_material_modifier, int headshot);
/* Actor path additionally applies CE's per-region byte accumulator/threshold. */
void vital_hurt_material_region_profile(vital *v, float amount, int part,
    const vital_damage_profile *profile, int damage_material_index,
    int region_index, float body_material_modifier, float shield_material_modifier,
    int headshot);
/* material_modifier is the damage definition's modifier for target material
 * 21. part currently selects headshot handling only; source damage-material
 * attribution is not available on the diagnostic sphere. */
void vital_hurt(vital *v, float amount, int part, float material_modifier, int headshot);
/* Consume one object-hit event from a projectile exactly once. */
int vital_apply_projectile_hit(vital *v, shot *projectile, int part,
    float material_modifier, int headshot);
int vital_apply_projectile_hit_profile(vital *v, shot *projectile, int part,
    const vital_damage_profile *profile, float body_material_modifier,
    float shield_material_modifier, int headshot);
/* Cyborg melee effect is 1000, with material-21 modifier 1. */
void vital_melee(vital *v);
void vital_tick(vital *v);
/* Tag-profiled 30 Hz recharge path used by the converted player collision tag. */
void vital_tick_profile(vital *v, const vital_damage_profile *profile);
#endif
