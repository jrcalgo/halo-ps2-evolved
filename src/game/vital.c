#include "game/vital.h"
#include <string.h>

const vital_damage_profile VITAL_CYBORG_INDIRECT_PROFILE = {
    .maximum_shield = 75.0f, .maximum_body = 75.0f,
    .shield_leak_fraction = 0.0f, .shield_damage_multiplier = 1.0f,
    .body_damage_multiplier = 1.0f,
    .minimum_shield_stun_damage = VITAL_MINIMUM_SHIELD_STUN_DAMAGE,
    .shield_stun_ticks = VITAL_STUN_TICKS,
    .shield_recharge_step = 0.008333333767950535f,
    .indirect_material_index = 0, .material_count = 0
};

static float recharge_step(void)
{
    float value;
    uint32_t bits = VITAL_RECHARGE_BITS;
    memcpy(&value, &bits, sizeof value);
    return value;
}

void vital_init(vital *v)
{
    memset(v, 0, sizeof *v);
    v->shield = 1.0f;
    v->body = 1.0f;
}

void vital_hurt_profile(vital *v, float amount, int part,
    const vital_damage_profile *profile, float body_material_modifier,
    float shield_material_modifier, int headshot)
{
    vital_hurt_material_profile(v, amount, part, profile,
        profile ? profile->indirect_material_index : -1,
        body_material_modifier, shield_material_modifier, headshot);
}

void vital_hurt_material_profile(vital *v, float amount, int part,
    const vital_damage_profile *profile, int damage_material_index,
    float body_material_modifier, float shield_material_modifier, int headshot)
{
    vital_hurt_material_region_profile(v, amount, part, profile, damage_material_index,
        -1, body_material_modifier, shield_material_modifier, headshot);
}

void vital_hurt_material_region_profile(vital *v, float amount, int part,
    const vital_damage_profile *profile, int damage_material_index, int region_index,
    float body_material_modifier, float shield_material_modifier, int headshot)
{
    float total = amount;
    float shield_damage = 0.0f;
    float damage_amount, actual;
    float shield_leak_fraction, resistance_shield_multiplier, resistance_body_multiplier;
    const vital_damage_material *material = NULL;
    if (!v || !profile || v->dead) return;
    if (profile->material_count > 0 && profile->material_count <= VITAL_DAMAGE_MATERIAL_MAX) {
        if (damage_material_index < 0 || damage_material_index >= profile->material_count)
            damage_material_index = profile->indirect_material_index;
        if (damage_material_index >= 0 && damage_material_index < profile->material_count)
            material = &profile->material[damage_material_index];
    }
    shield_leak_fraction = material ? material->shield_leak_fraction : profile->shield_leak_fraction;
    resistance_shield_multiplier = material ? material->shield_damage_multiplier : profile->shield_damage_multiplier;
    resistance_body_multiplier = material ? material->body_damage_multiplier : profile->body_damage_multiplier;
    if (v->shield > 0.0f) {
        float actual_shield_damage, normalized;
        shield_damage = (1.0f - shield_leak_fraction) * total;
        if (shield_damage < 0.0f) shield_damage = 0.0f;
        total -= shield_damage;
        actual_shield_damage = resistance_shield_multiplier * shield_damage *
            shield_material_modifier;
        normalized = actual_shield_damage / profile->maximum_shield;
        if (normalized > v->shield) {
            float excess = actual_shield_damage - profile->maximum_shield * v->shield;
            if (excess > 0.0f) total += excess;
            v->shield = 0.0f;
        } else {
            v->shield -= normalized;
        }
    }
    if (shield_damage >= profile->minimum_shield_stun_damage || v->shield == 0.0f)
        v->stun = profile->shield_stun_ticks;
    /* The probe uses the indirect damage material from the cyborg collision
     * tag, whose body_damage_multiplier is 1.0. Do not infer a multiplier from
     * a coarse body-part enum: CE selects this value from a collision material. */
    damage_amount = resistance_body_multiplier * total;
    actual = damage_amount / profile->maximum_body * body_material_modifier;
    if (part == VITAL_HEAD && damage_amount > 0.0f && headshot) v->body = 0.0f;
    if (damage_amount > 0.0f && region_index >= 0 &&
        profile->region_count <= VITAL_DAMAGE_REGION_MAX &&
        (unsigned)region_index < profile->region_count &&
        !(v->regions_destroyed_flags & (uint16_t)(1u << region_index))) {
        float accumulated = actual * 255.0f + (float)v->region_damage[region_index];
        if (accumulated >= 0.0f && accumulated < 16777216.0f) {
            v->region_damage[region_index] = (uint8_t)((uint32_t)accumulated & 0xffu);
            if (profile->region_damage_threshold[region_index] > 0.0f &&
                (float)v->region_damage[region_index] * (1.0f / 255.0f) >
                    profile->region_damage_threshold[region_index])
                v->regions_destroyed_flags |= (uint16_t)(1u << region_index);
        }
    }
    if (damage_amount > 0.0f) v->body -= actual;
    if (v->body < 0.0f) v->dead = 1;
}

void vital_hurt(vital *v, float amount, int part, float material_modifier, int headshot)
{
    vital_hurt_profile(v, amount, part, &VITAL_CYBORG_INDIRECT_PROFILE,
        material_modifier, 1.0f, headshot);
}

int vital_apply_projectile_hit(vital *v, shot *projectile, int part,
    float material_modifier, int headshot)
{
    return vital_apply_projectile_hit_profile(v, projectile, part,
        &VITAL_CYBORG_INDIRECT_PROFILE, material_modifier, 1.0f, headshot);
}

int vital_apply_projectile_hit_profile(vital *v, shot *projectile, int part,
    const vital_damage_profile *profile, float body_material_modifier,
    float shield_material_modifier, int headshot)
{
    if (!v || !projectile || !profile || !projectile->hit_object_this_tick) return 0;
    if (projectile->damage_material_types_valid) {
        body_material_modifier = projectile->damage_body_modifier;
        shield_material_modifier = projectile->damage_shield_modifier;
    } else if (projectile->attached_damage_event) {
        body_material_modifier = projectile->damage_modifier_21;
        shield_material_modifier = projectile->damage_modifier_22;
    }
    projectile->hit_object_this_tick = 0;
    if (projectile->damage > 0.0f) {
        vital_hurt_material_region_profile(v, projectile->damage, part, profile,
            projectile->damage_resistance_index, projectile->hit_region_index,
            body_material_modifier, shield_material_modifier, headshot);
    }
    return 1;
}

void vital_melee(vital *v)
{
    vital_hurt(v, 1000.0f, VITAL_BODY, 1.0f, 0);
}

void vital_tick(vital *v)
{
    vital_tick_profile(v, &VITAL_CYBORG_INDIRECT_PROFILE);
}

void vital_tick_profile(vital *v, const vital_damage_profile *profile)
{
    if (v->dead || v->shield >= 1.0f) return;
    if (v->stun == 0) {
        v->shield += profile ? profile->shield_recharge_step : recharge_step();
        if (v->shield > 1.0f) v->shield = 1.0f;
    } else {
        v->stun--;
    }
}
