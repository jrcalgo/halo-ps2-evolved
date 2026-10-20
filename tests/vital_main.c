#include "game/vital.h"
#include <stdio.h>

static void dump(const char *name, const vital *v)
{
    printf("%s shield %.7f body %.7f stun %d dead %d\n",
        name, v->shield, v->body, v->stun, v->dead);
}

static void shots(vital *v, int count, float amount, int part, float modifier, int headshot)
{
    int i;
    for (i = 0; i < count; i++) vital_hurt(v, amount, part, modifier, headshot);
}

int main(void)
{
    vital v;
    vital_damage_profile profile = {
        .maximum_shield = 75.0f, .maximum_body = 75.0f,
        .shield_leak_fraction = 0.2f, .shield_damage_multiplier = 1.0f,
        .body_damage_multiplier = 1.0f, .minimum_shield_stun_damage = 6.0f,
        .shield_stun_ticks = 120, .shield_recharge_step = 1.0f / 120.0f
    };
    int i;
    vital_init(&v);
    vital_hurt(&v, 5.0f, VITAL_BODY, 1.0f, 0);
    dump("below_stun_threshold", &v);
    vital_init(&v);
    v.shield = 0.0f;
    vital_hurt(&v, 10.0f, VITAL_BODY, 1.0f, 0);
    dump("indirect_body", &v);
    vital_init(&v);
    v.shield = 0.0f;
    vital_hurt(&v, 10.0f, VITAL_LEGS, 1.0f, 0);
    dump("indirect_legs", &v);
    vital_init(&v);
    vital_hurt_profile(&v, 10.0f, VITAL_BODY, &profile, 1.0f, 1.0f, 0);
    dump("shield_leak", &v);
    profile.shield_leak_fraction = 0.0f;
    vital_init(&v);
    v.shield = 0.1f;
    vital_hurt_profile(&v, 10.0f, VITAL_BODY, &profile, 1.0f, 2.0f, 0);
    dump("shield_modifier_overflow", &v);
    profile.material_count = 3;
    profile.indirect_material_index = 1;
    profile.material[1].material_type = 21;
    profile.material[1].shield_leak_fraction = 0.0f;
    profile.material[1].shield_damage_multiplier = 1.0f;
    profile.material[1].body_damage_multiplier = 1.0f;
    profile.material[2].material_type = 21;
    profile.material[2].shield_leak_fraction = 0.5f;
    profile.material[2].shield_damage_multiplier = 2.0f;
    profile.material[2].body_damage_multiplier = 1.5f;
    vital_init(&v);
    vital_hurt_material_profile(&v, 10.0f, VITAL_BODY, &profile, 2, 1.0f, 1.0f, 0);
    dump("direct_material", &v);
    vital_init(&v);
    vital_hurt_material_profile(&v, 10.0f, VITAL_BODY, &profile, 99, 1.0f, 1.0f, 0);
    dump("indirect_fallback", &v);
    vital_init(&v);
    shots(&v, 1, 25.0f, VITAL_BODY, 1.5f, 1);
    dump("pistol1", &v);
    shots(&v, 2, 25.0f, VITAL_BODY, 1.5f, 1);
    dump("pistol3", &v);
    shots(&v, 2, 25.0f, VITAL_BODY, 1.5f, 1);
    dump("pistol5", &v);

    vital_init(&v);
    shots(&v, 1, 25.0f, VITAL_HEAD, 1.5f, 1);
    dump("head_shielded", &v);
    v.shield = 0.0f;
    vital_hurt(&v, 25.0f, VITAL_HEAD, 1.5f, 1);
    dump("head_open", &v);

    vital_init(&v);
    shots(&v, 7, 10.0f, VITAL_BODY, 1.0f, 0);
    dump("rifle7", &v);
    vital_hurt(&v, 10.0f, VITAL_BODY, 1.0f, 0);
    dump("rifle8", &v);

    vital_init(&v);
    vital_hurt(&v, 25.0f, VITAL_BODY, 1.5f, 1);
    for (i = 0; i < VITAL_STUN_TICKS; i++) vital_tick(&v);
    dump("recharge_wait", &v);
    vital_tick(&v);
    dump("recharge_step", &v);
    vital_init(&v);
    vital_melee(&v);
    dump("melee", &v);

    /* CE adds normalized actual body damage into an 8-bit per-region
     * accumulator and destroys only after crossing a positive tag threshold. */
    profile.maximum_body = 75.0f;
    profile.material_count = 1;
    profile.indirect_material_index = 0;
    profile.material[0].body_damage_multiplier = 1.0f;
    profile.material[0].shield_damage_multiplier = 1.0f;
    profile.material[0].shield_leak_fraction = 0.0f;
    profile.region_count = 1;
    profile.region_damage_threshold[0] = 0.1f;
    vital_init(&v);
    v.shield = 0.0f;
    vital_hurt_material_region_profile(&v, 10.0f, VITAL_BODY, &profile,
        0, 0, 1.0f, 1.0f, 0);
    if (v.region_damage[0] != 34 || !(v.regions_destroyed_flags & 1u)) return 1;
    vital_hurt_material_region_profile(&v, 10.0f, VITAL_BODY, &profile,
        0, 0, 1.0f, 1.0f, 0);
    if (v.region_damage[0] != 34) return 2;
    printf("region_damage byte=%u destroyed=%u\n", v.region_damage[0],
        (unsigned)(v.regions_destroyed_flags & 1u));
    return 0;
}
