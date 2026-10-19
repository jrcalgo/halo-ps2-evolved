/* Cyborg shield and body from characters\cyborg\cyborg and object_damage_shield
 * / object_damage_body. Vitality is stored normalized, as the object datum
 * does. A hit uses the indirect material (body): no shield leak, shield
 * multiplier 1. Head, body, and legs then use their body multipliers.
 * Pistol and rifle damage against material 21 is 1.5 and 1. The shield
 * material modifier is 1. Stun is 6 seconds. Recharge is the collision
 * tag's runtime velocity, which the map already stores. No heap. */
#ifndef GAME_VITAL_H
#define GAME_VITAL_H
#include <stdint.h>

#define VITAL_HEAD 0
#define VITAL_BODY 1
#define VITAL_LEGS 2
#define VITAL_MAX_SHIELD 75.0f
#define VITAL_MAX_BODY 75.0f
#define VITAL_STUN_TICKS 180
#define VITAL_RECHARGE_BITS 0x3c088889u

typedef struct {
    float shield;
    float body;
    short stun;
    int dead;
} vital;

void vital_init(vital *v);
/* material_modifier is the bullet's modifier for material 21.
 * headshot is the pistol's headshot flag. */
void vital_hurt(vital *v, float amount, int part, float material_modifier, int headshot);
/* Cyborg melee effect is 1000, with material-21 modifier 1. */
void vital_melee(vital *v);
void vital_tick(vital *v);
#endif
