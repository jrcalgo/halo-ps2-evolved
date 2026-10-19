#include "game/vital.h"
#include <string.h>

static float recharge_step(void)
{
    float value;
    uint32_t bits = VITAL_RECHARGE_BITS;
    memcpy(&value, &bits, sizeof value);
    return value;
}

static float body_multiplier(int part)
{
    if (part == VITAL_LEGS) return 0.800000011920929f;
    return 1.0f;
}

void vital_init(vital *v)
{
    v->shield = 1.0f;
    v->body = 1.0f;
    v->stun = 0;
    v->dead = 0;
}

void vital_hurt(vital *v, float amount, int part, float material_modifier, int headshot)
{
    float total = amount;
    float shield_damage = 0.0f;
    float damage_amount, actual;
    if (v->dead) return;
    if (v->shield > 0.0f) {
        float normalized = amount / VITAL_MAX_SHIELD;
        shield_damage = amount;
        total = 0.0f;
        if (normalized > v->shield) {
            total = amount - VITAL_MAX_SHIELD * v->shield;
            v->shield = 0.0f;
        } else {
            v->shield -= normalized;
        }
    }
    if (shield_damage >= 0.0f || v->shield == 0.0f) v->stun = VITAL_STUN_TICKS;
    damage_amount = body_multiplier(part) * total;
    actual = damage_amount / VITAL_MAX_BODY * material_modifier;
    if (part == VITAL_HEAD && damage_amount > 0.0f && headshot) v->body = 0.0f;
    if (damage_amount > 0.0f) v->body -= actual;
    if (v->body < 0.0f) v->dead = 1;
}

void vital_melee(vital *v)
{
    vital_hurt(v, 1000.0f, VITAL_BODY, 1.0f, 0);
}

void vital_tick(vital *v)
{
    if (v->dead || v->shield >= 1.0f) return;
    if (v->stun == 0) {
        v->shield += recharge_step();
        if (v->shield > 1.0f) v->shield = 1.0f;
    } else {
        v->stun--;
    }
}
