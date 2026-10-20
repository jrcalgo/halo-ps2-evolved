#include "game/play_fp.h"
#include "game/vital.h"
#include <stdio.h>
#include <string.h>

int main(void)
{
    const play_fp_trigger *primary, *secondary;
    const shot_def *primary_shot, *secondary_shot;
    gun_trigger_profile profile[GUN_TRIGGER_MAX];
    gun_trigger_pair pair;
    shot live_secondary;
    int16_t loaded[GUN_TRIGGER_MAGAZINES] = {0, 0};
    const shot_def *pistol_shot;
    unsigned fired;
    int i;
    if (play_fp_open() != 0 || play_fp_count() != 23) return 1;
    pistol_shot = play_fp_shot();
    if (!pistol_shot || !pistol_shot->damage_materials_valid ||
        pistol_shot->damage_material_modifier[21] != 1.5f ||
        pistol_shot->damage_material_modifier[22] != 1.0f) return 66;
    primary = play_fp_trigger_at(0);
    if (!primary || play_fp_trigger_uses_weapon_origin(0)) return 54;
    for (i = 0; i < 5; i++) play_fp_cycle();
    if (strcmp(play_fp_path(), "weapons\\plasma pistol\\plasma pistol") != 0 ||
        play_fp_slot() != 5) return 1;
    primary = play_fp_trigger_at(0);
    secondary = play_fp_trigger_at(1);
    primary_shot = play_fp_trigger_shot(0);
    secondary_shot = play_fp_trigger_shot(1);
    if (!primary || !secondary) return 2;
    if (!primary_shot || !secondary_shot) return 7;
    if (strcmp(primary->projectile, "weapons\\plasma pistol\\bolt") != 0 ||
        strcmp(secondary->projectile, "weapons\\plasma rifle\\charged bolt") != 0) return 3;
    if (primary->halves[0] != 0 || secondary->halves[0] != 0) return 4;
    if (primary_shot->maximum_range != 50.0f || secondary_shot->maximum_range != 40.0f ||
        secondary_shot->velocity_bits == primary_shot->velocity_bits) return 5;
    if (play_fp_trigger_at(-1) || play_fp_trigger_at(2) ||
        play_fp_trigger_shot(-1) || play_fp_trigger_shot(2)) return 6;
    if (play_fp_trigger_profiles(profile) != 2 || profile[0].charging_seconds != 0.6f ||
        profile[0].charged_seconds != 45.0f || profile[0].overcharged_action != 0 ||
        profile[0].projectiles_per_shot != primary->halves[10] ||
        profile[1].projectiles_per_shot != secondary->halves[10] ||
        profile[0].error_acceleration != primary->values[PLAY_FP_TRIGGER_RUNTIME_ERROR_ACCEL] ||
        profile[0].error_deceleration != primary->values[PLAY_FP_TRIGGER_RUNTIME_ERROR_DECEL] ||
        profile[0].heat_generated_per_round != primary->values[16] ||
        profile[0].spew_seconds != primary->values[PLAY_FP_TRIGGER_SPEW_SECONDS] ||
        profile[0].age_generated_per_round != 0.002f ||
        profile[0].age_misfire_start != 0.9f || profile[0].age_misfire_chance != 0.5f ||
        profile[0].firing_effect_shots[0][0] != 1 ||
        profile[0].firing_effect_shots[0][1] != 1 ||
        profile[0].firing_effect_count != 1 ||
        profile[1].age_generated_per_round != 0.11f ||
        profile[1].firing_effect_count != 1) return 14;
    /* State-transition fixtures below isolate trigger mechanics; the heat
     * threshold/cooling interaction is exercised by its own dedicated case. */
    profile[0].heat_generated_per_round = 0.0f;
    profile[1].heat_generated_per_round = 0.0f;
    {
        gun_trigger_profile seeded_profile[GUN_TRIGGER_MAX];
        gun_trigger_pair seeded_pair;
        uint32_t seed = 8u;
        memcpy(seeded_profile, profile, sizeof seeded_profile);
        seeded_profile[0].magazine_index = GUN_TRIGGER_NONE;
        gun_trigger_pair_init(&seeded_pair, loaded);
        seeded_pair.player_owned = 1;
        seeded_pair.weapon_age = 0.95f;
        if (gun_trigger_pair_tick_seeded(&seeded_pair, seeded_profile, 2, 1, 0, &seed) != 0) return 70;
        {
            unsigned fired_seeded = gun_trigger_pair_tick_seeded(&seeded_pair,
                seeded_profile, 2, 0, 0, &seed);
            if (fired_seeded != 1u ||
            !seeded_pair.trigger[0].misfired ||
            seeded_pair.weapon_age < 0.95199f || seeded_pair.weapon_age > 0.95201f ||
            seed != 18026106u) return 70;
            if (gun_trigger_pair_tick_seeded(&seeded_pair, seeded_profile, 2,
                    0, 0, &seed) != 0 || seeded_pair.trigger[0].misfired) return 74;
        }
    }
    {
        gun_trigger_profile age_profile[GUN_TRIGGER_MAX];
        gun_trigger_pair age_pair;
        int16_t age_loaded[GUN_TRIGGER_MAGAZINES] = {1, 0};
        uint32_t seed = 8u;
        memcpy(age_profile, profile, sizeof age_profile);
        age_profile[0].age_misfire_start = 0.9f;
        age_profile[0].age_misfire_chance = 0.5f;
        gun_trigger_pair_init(&age_pair, age_loaded);
        age_pair.weapon_flags = GUN_WEAPON_CANNOT_FIRE_AT_MAXIMUM_AGE;
        age_pair.weapon_age = 1.0f;
        if (gun_trigger_pair_tick_seeded(&age_pair, age_profile, 2, 1, 0, &seed) != 0 ||
            age_pair.trigger[0].state != GUN_TRIG_LOCKED ||
            age_pair.magazine_loaded[0] != 1 || seed != 18026106u) return 71;
    }
    {
        gun_trigger_profile charge_profile[GUN_TRIGGER_MAX];
        gun_trigger_pair charge_pair;
        int16_t charge_loaded[GUN_TRIGGER_MAGAZINES] = {1, 1};
        memcpy(charge_profile, profile, sizeof charge_profile);
        charge_profile[0].charging_seconds = 1.0f / 30.0f;
        charge_profile[0].charged_seconds = 10.0f;
        charge_profile[0].magazine_index = 0;
        charge_profile[0].rounds_per_shot = 1;
        charge_profile[1].magazine_index = 1;
        charge_profile[1].rounds_per_shot = 1;
        gun_trigger_pair_init(&charge_pair, charge_loaded);
        if (gun_trigger_pair_tick(&charge_pair, charge_profile, 2, 1u, 0) != 0 ||
            charge_pair.trigger[0].state != GUN_TRIG_CHARGING ||
            gun_trigger_pair_tick(&charge_pair, charge_profile, 2, 1u, 0) != 0 ||
            charge_pair.trigger[0].state != GUN_TRIG_CHARGED) return 72;
        charge_pair.magazine_loaded[0] = 0;
        if (gun_trigger_pair_tick(&charge_pair, charge_profile, 2, 1u, 0) != 2u ||
            charge_pair.magazine_loaded[1] != 0 ||
            charge_pair.trigger[0].state != GUN_TRIG_IDLE) return 73;
    }
    {
        const play_fp_weapon_trigger_policy *policy = play_fp_weapon_trigger_policy_get();
        const play_fp_firing_effect *effect = play_fp_firing_effect_at(0, 0);
        if (!policy || !(policy->flags & GUN_WEAPON_CANNOT_FIRE_AT_MAXIMUM_AGE) ||
            policy->age_misfire_start != 0.9f || policy->age_misfire_chance != 0.5f ||
            !effect || effect->shots_lower_bound != 1 || effect->shots_upper_bound != 1 ||
            play_fp_firing_effect_at(-1, 0) || play_fp_firing_effect_at(0, 2))
            return 63;
    }
    {
        const gun_def *plasma = play_fp_gun();
        gun_def age_def = GUN_PISTOL;
        gun age_gun;
        if (!plasma || !plasma->cannot_fire_at_maximum_age ||
            plasma->age_generated_per_round != 0.002f ||
            plasma->firing_effect_count != 1) return 66;
        age_def.uses_magazine = 0;
        age_def.rate_of_fire = age_def.rate_final = 30.0f;
        age_def.age_rate_of_fire_penalty = 1.0f;
        age_def.age_generated_per_round = 0.25f;
        age_def.firing_effect_count = 1;
        gun_init(&age_gun, &age_def);
        age_gun.idle_ticks = 0;
        age_gun.age = 0.5f;
        if (gun_tick(&age_gun, &age_def, 1, 0) != 0 ||
            gun_tick(&age_gun, &age_def, 1, 0) != 1 ||
            age_gun.age != 0.75f) return 67;
        age_def.uses_magazine = 1;
        age_def.cannot_fire_at_maximum_age = 1;
        gun_init(&age_gun, &age_def);
        age_gun.age = 1.0f;
        if (gun_tick(&age_gun, &age_def, 1, 0) != 0 || age_gun.loaded != 12 ||
            age_gun.trigger != GUN_TRIG_LOCKED ||
            gun_tick(&age_gun, &age_def, 0, 0) != 0 || age_gun.trigger != GUN_TRIG_IDLE)
            return 68;
        age_def.age_misfire_start = 0.9f;
        age_def.age_misfire_chance = 0.5f;
        age_def.firing_effect_count = 1;
        age_def.firing_effect_shots[0][0][0] = 1;
        age_def.firing_effect_shots[0][0][1] = 1;
        gun_init(&age_gun, &age_def);
        age_gun.age = 1.0f;
        {
            uint32_t seed = 8;
            if (gun_tick_seeded(&age_gun, &age_def, 1, 0, &seed) != 0 ||
                age_gun.loaded != 12 || age_gun.trigger != GUN_TRIG_LOCKED ||
                seed != 18026106u) return 69;
        }
    }
    if (!play_fp_trigger_magazine(0) || !play_fp_trigger_loaded(loaded) ||
        loaded[0] != 0 || loaded[1] != 0) return 35;
    gun_trigger_pair_init(&pair, loaded);
    if (gun_trigger_pair_tick(&pair, profile, 2, 1, 0) != 0 ||
        pair.trigger[0].state != GUN_TRIG_CHARGING || pair.trigger[0].state_timer != 18) return 7;
    for (i = 1; i < 9; i++)
        if (gun_trigger_pair_tick(&pair, profile, 2, 1, 0) != 0) return 7;
    if (pair.trigger[0].state_timer != 10) return 7;
    fired = gun_trigger_pair_tick(&pair, profile, 2, 0, 0);
    if (fired != 1 || pair.magazine_loaded[0] != 0) return 8;
    gun_trigger_pair_init(&pair, loaded);
    for (i = 0; i < 18; i++)
        if (gun_trigger_pair_tick(&pair, profile, 2, 1, 0) != 0) return 9;
    if (pair.trigger[0].state != GUN_TRIG_CHARGING || pair.trigger[0].state_timer != 1) return 10;
    if (gun_trigger_pair_tick(&pair, profile, 2, 1, 0) != 0 ||
        pair.trigger[0].state != GUN_TRIG_CHARGED || pair.trigger[0].state_timer != 1350) return 10;
    fired = gun_trigger_pair_tick(&pair, profile, 2, 0, 0);
    if (fired != 2 || pair.magazine_loaded[0] != 0) return 11;
    /* CE's single-trigger charge path fires at charge start when its prior
     * runtime rate fraction is nonzero; this is not the tag's initial rate
     * in rounds per second. Early release must not fire it again. */
    profile[0].magazine_index = GUN_TRIGGER_NONE;
    profile[0].charging_seconds = 2.0f / 30.0f;
    profile[0].rate_initial = 1.0f;
    profile[0].rate_final = 1.0f;
    gun_trigger_pair_init(&pair, loaded);
    if (gun_trigger_pair_tick(&pair, profile, 1, 1, 0) != 0 ||
        pair.trigger[0].state != GUN_TRIG_CHARGING ||
        pair.trigger[0].fired_before_charging) return 44;
    gun_trigger_pair_init(&pair, loaded);
    pair.trigger[0].rate_fraction = 0.5f;
    if (gun_trigger_pair_tick(&pair, profile, 1, 1, 0) != 1 ||
        pair.trigger[0].state != GUN_TRIG_CHARGING ||
        !pair.trigger[0].fired_before_charging) return 42;
    if (gun_trigger_pair_tick(&pair, profile, 1, 0, 0) != 0 ||
        pair.trigger[0].state != GUN_TRIG_IDLE) return 43;
    profile[0].charging_seconds = 1.0f / 30.0f;
    profile[0].charged_seconds = 0.0f;
    profile[0].overcharged_action = 2;
    gun_trigger_pair_init(&pair, loaded);
    if (gun_trigger_pair_tick(&pair, profile, 2, 1, 0) != 0 ||
        gun_trigger_pair_tick(&pair, profile, 2, 1, 0) != 0 ||
        pair.trigger[0].state != GUN_TRIG_CHARGED) return 12;
    fired = gun_trigger_pair_tick(&pair, profile, 2, 1, 0);
    if (fired != 2 || pair.trigger[0].state != GUN_TRIG_IDLE) return 13;
    profile[0].overcharged_action = 1;
    gun_trigger_pair_init(&pair, loaded);
    if (gun_trigger_pair_tick(&pair, profile, 2, 1, 0) != 0 ||
        gun_trigger_pair_tick(&pair, profile, 2, 1, 0) != 0 ||
        gun_trigger_pair_tick(&pair, profile, 2, 1, 0) != 0 || !pair.detonated) return 15;
    profile[0].overcharged_action = 0;
    profile[0].spew_seconds = 2.0f / 30.0f;
    gun_trigger_pair_init(&pair, loaded);
    if (gun_trigger_pair_tick(&pair, profile, 2, 1, 0) != 0 ||
        gun_trigger_pair_tick(&pair, profile, 2, 1, 0) != 0 ||
        pair.trigger[0].state != GUN_TRIG_CHARGED) return 16;
    if (gun_trigger_pair_tick(&pair, profile, 2, 0, 0) != 0 ||
        pair.trigger[0].state != GUN_TRIG_SPEWING || pair.trigger[0].state_timer != 2) return 17;
    if (gun_trigger_pair_tick(&pair, profile, 2, 1, 0) != 1 ||
        pair.trigger[0].state != GUN_TRIG_SPEWING || pair.trigger[0].state_timer != 1) return 18;
    if (gun_trigger_pair_tick(&pair, profile, 2, 1, 0) != 0 ||
        pair.trigger[0].state != GUN_TRIG_IDLE) return 19;
    /* Non-analog rate interpolation uses CE's per-tick acceleration, while
     * the shot test sees the fraction from before this tick's update. */
    profile[0].charging_seconds = 0.0f;
    profile[0].spew_seconds = 0.0f;
    profile[0].overcharged_action = 0;
    profile[0].flags &= ~GUN_TRIGGER_ANALOG_RATE;
    profile[0].magazine_index = GUN_TRIGGER_NONE;
    profile[0].rate_initial = 1.0f;
    profile[0].rate_final = 30.0f;
    profile[0].rate_acceleration = 0.5f;
    profile[0].rate_deceleration = 0.25f;
    gun_trigger_pair_init(&pair, loaded);
    if (gun_trigger_pair_tick(&pair, profile, 1, 1, 0) != 1 ||
        pair.trigger[0].rate_fraction != 0.5f) return 20;
    if (gun_trigger_pair_tick(&pair, profile, 1, 1, 0) != 0 ||
        pair.trigger[0].rate_fraction != 1.0f) return 21;
    if (gun_trigger_pair_tick(&pair, profile, 1, 1, 0) != 1) return 22;
    if (gun_trigger_pair_tick(&pair, profile, 1, 0, 0) != 0 ||
        pair.trigger[0].rate_fraction != 0.75f) return 23;
    profile[0].charging_seconds = 1.0f / 30.0f;
    profile[0].charged_seconds = 1.0f / 30.0f;
    profile[0].rate_acceleration = 0.25f;
    profile[0].rate_deceleration = 0.0f;
    gun_trigger_pair_init(&pair, loaded);
    if (gun_trigger_pair_tick(&pair, profile, 2, 1, 0) != 0 ||
        pair.trigger[0].rate_fraction != 0.25f) return 24;
    if (gun_trigger_pair_tick(&pair, profile, 2, 1, 0) != 0 ||
        pair.trigger[0].rate_fraction != 0.5f) return 25;
    if (gun_trigger_pair_tick(&pair, profile, 2, 0, 0) != 2 ||
        pair.trigger[0].rate_fraction != 0.0f) return 26;
    profile[0].charged_seconds = 10.0f / 30.0f;
    profile[0].spew_seconds = 2.0f / 30.0f;
    profile[0].error_acceleration = 0.25f;
    profile[0].error_deceleration = 0.5f;
    gun_trigger_pair_init(&pair, loaded);
    if (gun_trigger_pair_tick(&pair, profile, 2, 1, 0) != 0 ||
        pair.trigger[0].error_fraction != 0.25f) return 27;
    if (gun_trigger_pair_tick(&pair, profile, 2, 1, 0) != 0 ||
        pair.trigger[0].error_fraction != 0.5f) return 28;
    if (gun_trigger_pair_tick(&pair, profile, 2, 0, 0) != 0 ||
        pair.trigger[0].state != GUN_TRIG_SPEWING ||
        pair.trigger[0].error_fraction != 0.75f) return 29;
    if (gun_trigger_pair_tick(&pair, profile, 2, 0, 0) != 1 ||
        pair.trigger[0].error_fraction != 1.0f ||
        pair.trigger[1].error_fraction != 0.0f) return 30;
    if (gun_trigger_pair_tick(&pair, profile, 2, 0, 0) != 0 ||
        pair.trigger[0].error_fraction != 0.5f) return 31;
    profile[0].charging_seconds = 0.0f;
    profile[0].spew_seconds = 0.0f;
    profile[0].flags |= GUN_TRIGGER_ANALOG_RATE;
    profile[0].rate_initial = 1.0f;
    profile[0].rate_final = 30.0f;
    profile[0].rate_acceleration = 0.0f;
    profile[0].error_acceleration = 0.0f;
    profile[0].error_deceleration = 0.0f;
    {
        const float analog[GUN_TRIGGER_MAX] = {0.5f, 0.0f};
        gun_trigger_pair_init(&pair, loaded);
        if (gun_trigger_pair_tick_input(&pair, profile, 1, 0, analog, 0) != 1) return 32;
        if (gun_trigger_pair_tick_input(&pair, profile, 1, 0, analog, 0) != 0) return 33;
        if (gun_trigger_pair_tick_input(&pair, profile, 1, 0, analog, 0) != 1) return 34;
    }
    /* Scorpion primary trigger consumes its tag-selected magazine; its
     * secondary trigger instead has magazine_index == NONE. */
    for (i = 0; i < 13; i++) play_fp_cycle();
    if (strcmp(play_fp_path(), "vehicles\\scorpion\\scorpion cannon") != 0 ||
        play_fp_slot() != 18 ||
        play_fp_trigger_profiles(profile) != 2 || profile[0].magazine_index != 0 ||
        profile[0].rounds_per_shot != 1 || profile[1].magazine_index != GUN_TRIGGER_NONE) return 36;
    primary = play_fp_trigger_at(0);
    secondary = play_fp_trigger_at(1);
    if (!primary || !(primary->flags & GUN_TRIGGER_USES_WEAPON_ORIGIN) ||
        !play_fp_trigger_uses_weapon_origin(0) ||
        !secondary || secondary->halves[9] != 0 || secondary->halves[10] != 1 ||
        !(secondary->flags & GUN_TRIGGER_USES_WEAPON_ORIGIN) ||
        !play_fp_trigger_uses_weapon_origin(1)) return 52;
    {
        const play_fp_weapon_trigger_policy *policy = play_fp_weapon_trigger_policy_get();
        if (!policy || !(policy->flags & (1u << 12)) || policy->secondary_trigger_mode != 0)
            return 55;
    }
    if (!play_fp_trigger_magazine(0) || play_fp_trigger_magazine(0)->values[3] != 1 ||
        !play_fp_trigger_loaded(loaded) || loaded[0] != 1 || loaded[1] != 0) return 37;
    gun_trigger_pair_init(&pair, loaded);
    if (gun_trigger_pair_tick(&pair, profile, 2, 1, 1u) != 0 || pair.magazine_loaded[0] != 1) return 38;
    if (gun_trigger_pair_tick(&pair, profile, 2, 1, 0) != 1 || pair.magazine_loaded[0] != 0) return 39;
    gun_trigger_pair_init(&pair, loaded);
    fired = gun_trigger_pair_tick(&pair, profile, 2, 2u, 0);
    if (fired != 2 || !play_fp_trigger_shot(1)) return 48;
    if (gun_trigger_pair_tick(&pair, profile, 2, 2u, 0) != 0 ||
        gun_trigger_pair_tick(&pair, profile, 2, 2u, 0) != 2) return 50;
    {
        const float origin[3] = {0.0f, 0.0f, 0.0f};
        const float aim[3] = {1.0f, 0.0f, 0.0f};
        shot_scene scene;
        vital target;
        float expected_body;
        uint32_t shot_seed = 1;
        int tick;
        memset(&live_secondary, 0, sizeof live_secondary);
        shot_spawn(&live_secondary, origin, aim, play_fp_trigger_shot(1));
        if (!live_secondary.alive || live_secondary.velocity[0] <= 0.0f) return 49;
        memset(&scene, 0, sizeof scene);
        scene.target = 1;
        scene.target_is_unit = 1;
        scene.target_center[0] = 2.0f;
        scene.target_radius = 0.5f;
        scene.target_body_damage_material_type = 17;
        scene.target_shield_damage_material_type = 22;
        scene.target_damage_material_types_valid = 1;
        vital_init(&target);
        target.shield = 0.0f;
        for (tick = 0; tick < 4 && live_secondary.alive; tick++)
            shot_tick(&live_secondary, play_fp_trigger_shot(1), &scene, &shot_seed);
        expected_body = 1.0f - live_secondary.damage * 0.6f / VITAL_MAX_BODY;
        if (!live_secondary.hit_object || !live_secondary.hit_object_this_tick) return 53;
        if (!live_secondary.damage_material_types_valid ||
            live_secondary.damage_body_material_type != 17 ||
            live_secondary.damage_shield_material_type != 22) return 67;
        if (live_secondary.damage_body_modifier < 0.599f ||
            live_secondary.damage_body_modifier > 0.601f ||
            live_secondary.damage_shield_modifier != 1.0f) return 68;
        if (!vital_apply_projectile_hit(&target, &live_secondary, VITAL_BODY, 1.0f, 0) ||
            (target.shield == VITAL_MAX_SHIELD && target.body == VITAL_MAX_BODY)) return 69;
        if (target.body < expected_body - 0.0001f ||
            target.body > expected_body + 0.0001f) return 70;
        if (vital_apply_projectile_hit(&target, &live_secondary, VITAL_BODY, 1.0f, 0)) return 71;
    }
    play_fp_cycle();
    {
        const play_fp_weapon_trigger_policy *policy = play_fp_weapon_trigger_policy_get();
        if (strcmp(play_fp_path(), "vehicles\\banshee\\banshee gun") != 0 ||
            !policy || policy->secondary_trigger_mode != 2) return 56;
    }
    /* Verify the packed runtime-error field mapping for every selected tag,
     * including profiles whose ramp values happen to be zero. */
    for (i = 0; i < play_fp_count(); i++) {
        int trigger;
        const gun_def *selected = play_fp_gun();
        if (!selected || play_fp_trigger_profiles(profile) != selected->trigger_count) return 40;
        for (trigger = 0; trigger < GUN_TRIGGER_MAX; trigger++) {
            const play_fp_trigger *record = play_fp_trigger_at(trigger);
            if (!record || profile[trigger].error_acceleration !=
                    record->values[PLAY_FP_TRIGGER_RUNTIME_ERROR_ACCEL] ||
                profile[trigger].error_deceleration !=
                    record->values[PLAY_FP_TRIGGER_RUNTIME_ERROR_DECEL] ||
                profile[trigger].spew_seconds !=
                    record->values[PLAY_FP_TRIGGER_SPEW_SECONDS] ||
                profile[trigger].flags != record->flags ||
                profile[trigger].magazine_index != record->halves[0] ||
                profile[trigger].rounds_per_shot != record->halves[1] ||
                profile[trigger].minimum_rounds != record->halves[2] ||
                profile[trigger].overcharged_action != record->halves[8] ||
                profile[trigger].rate_initial != record->values[PLAY_FP_TRIGGER_RATE_INITIAL] ||
                profile[trigger].rate_final != record->values[PLAY_FP_TRIGGER_RATE_FINAL] ||
                profile[trigger].rate_acceleration !=
                    record->values[PLAY_FP_TRIGGER_RUNTIME_RATE_ACCEL] ||
                profile[trigger].rate_deceleration !=
                    record->values[PLAY_FP_TRIGGER_RUNTIME_RATE_DECEL] ||
                profile[trigger].charging_seconds !=
                    record->values[PLAY_FP_TRIGGER_CHARGING_SECONDS] ||
                profile[trigger].charged_seconds !=
                    record->values[PLAY_FP_TRIGGER_CHARGED_SECONDS] ||
                profile[trigger].age_generated_per_round !=
                    record->values[PLAY_FP_TRIGGER_AGE_GENERATED_PER_ROUND] ||
                profile[trigger].firing_effect_count != record->firing_effect_count) return 41;
        }
        {
            const play_fp_weapon_trigger_policy *policy = play_fp_weapon_trigger_policy_get();
            if (!policy) return 64;
        }
        play_fp_cycle();
    }
    /* Retail fuel-rod tags are single-trigger, charged weapons whose initial
     * cadence value is nonzero. CE checks the runtime fraction (initially
     * zero), so the initial shot starts charging without firing. */
    for (i = 0; i < play_fp_count() &&
         strcmp(play_fp_path(), "weapons\\fuel rod gun\\fuel rod") != 0; i++)
        play_fp_cycle();
    if (strcmp(play_fp_path(), "weapons\\fuel rod gun\\fuel rod") != 0 ||
        play_fp_trigger_profiles(profile) != 1 ||
        profile[0].charging_seconds != 1.25f || profile[0].rate_initial != 10.0f ||
        !play_fp_trigger_loaded(loaded)) return 45;
    gun_trigger_pair_init(&pair, loaded);
    if (gun_trigger_pair_tick(&pair, profile, 1, 1, 0) != 0 ||
        pair.trigger[0].state != GUN_TRIG_CHARGING ||
        pair.trigger[0].fired_before_charging) return 46;
    gun_trigger_pair_init(&pair, loaded);
    pair.trigger[0].rate_fraction = 0.5f;
    if (gun_trigger_pair_tick(&pair, profile, 1, 1, 0) != 1 ||
        pair.trigger[0].state != GUN_TRIG_CHARGING ||
        !pair.trigger[0].fired_before_charging) return 47;
    {
        int trigger;
        for (trigger = 0; trigger < GUN_TRIGGER_MAX; trigger++) {
            memset(&profile[trigger], 0, sizeof profile[trigger]);
            profile[trigger].magazine_index = GUN_TRIGGER_NONE;
            profile[trigger].rate_initial = 30.0f;
            profile[trigger].rate_final = 30.0f;
        }
        /* CE toggle is edge-triggered: the latched control fires while the
         * physical button is up, then the next press edge turns it off. */
        profile[0].flags = GUN_TRIGGER_TOGGLES;
        gun_trigger_pair_init(&pair, NULL);
        if (gun_trigger_pair_tick_controls(&pair, profile, 1,
                GUN_SECONDARY_TRIGGER_NORMAL, 0, 0.0f, 1, 0, 1, 0, 0) != 1u ||
            gun_trigger_pair_tick_controls(&pair, profile, 1,
                GUN_SECONDARY_TRIGGER_NORMAL, 0, 0.0f, 0, 0, 1, 0, 0) != 1u ||
            gun_trigger_pair_tick_controls(&pair, profile, 1,
                GUN_SECONDARY_TRIGGER_NORMAL, 0, 0.0f, 1, 0, 1, 0, 0) != 0u ||
            pair.trigger[0].toggled) return 57;
        /* Secondary inhibition and slaving follow weapon-level CE mode and
         * secondary-trigger override flag before trigger state dispatch. */
        gun_trigger_pair_init(&pair, NULL);
        if (gun_trigger_pair_tick_controls(&pair, profile, 2,
                GUN_SECONDARY_TRIGGER_INHIBITS_PRIMARY,
                GUN_WEAPON_SECONDARY_TRIGGER_OVERRIDES_GRENADES,
                0.0f, 1, 1, 1, 0, 0) != 2u) return 58;
        gun_trigger_pair_init(&pair, NULL);
        if (gun_trigger_pair_tick_controls(&pair, profile, 2,
                GUN_SECONDARY_TRIGGER_SLAVED_TO_PRIMARY,
                GUN_WEAPON_SECONDARY_TRIGGER_OVERRIDES_GRENADES,
                0.0f, 0, 1, 1, 0, 0) != 0u) return 59;
        pair.trigger[0].rate_fraction = 1.0f;
        if (gun_trigger_pair_tick_controls(&pair, profile, 2,
                GUN_SECONDARY_TRIGGER_SLAVED_TO_PRIMARY,
                GUN_WEAPON_SECONDARY_TRIGGER_OVERRIDES_GRENADES,
                0.0f, 0, 1, 1, 0, 0) != 2u) return 60;
        profile[0].flags = GUN_TRIGGER_STICKS_WHEN_DROPPED;
        gun_trigger_pair_init(&pair, NULL);
        if (gun_trigger_pair_tick_controls(&pair, profile, 1,
                GUN_SECONDARY_TRIGGER_NORMAL, 0, 0.0f, 0, 0, 1, 1, 0) != 1u ||
            gun_trigger_pair_tick_controls(&pair, profile, 1,
                GUN_SECONDARY_TRIGGER_NORMAL, 0, 0.0f, 0, 0, 1, 0, 0) != 0u) return 61;
        profile[0].flags = 0;
        profile[0].magazine_index = 0;
        profile[0].rounds_per_shot = 1;
        profile[0].firing_effect_count = 1;
        profile[0].age_generated_per_round = 0.5f;
        loaded[0] = 3;
        gun_trigger_pair_init(&pair, loaded);
        if (gun_trigger_pair_tick_controls(&pair, profile, 1,
                GUN_SECONDARY_TRIGGER_NORMAL, GUN_WEAPON_CANNOT_FIRE_AT_MAXIMUM_AGE,
                0.0f, 1, 0, 1, 0, 0) != 1u || pair.weapon_age != 0.5f ||
            gun_trigger_pair_tick_controls(&pair, profile, 1,
                GUN_SECONDARY_TRIGGER_NORMAL, GUN_WEAPON_CANNOT_FIRE_AT_MAXIMUM_AGE,
                0.0f, 1, 0, 1, 0, 0) != 1u || pair.weapon_age != 1.0f ||
            gun_trigger_pair_tick_controls(&pair, profile, 1,
                GUN_SECONDARY_TRIGGER_NORMAL, GUN_WEAPON_CANNOT_FIRE_AT_MAXIMUM_AGE,
                0.0f, 1, 0, 1, 0, 0) != 0u || pair.magazine_loaded[0] != 1) return 62;
        profile[0].flags = 0;
        profile[0].age_generated_per_round = 0.0f;
        gun_trigger_pair_init(&pair, loaded);
        pair.weapon_age = 0.5f;
        pair.trigger[0].idle_ticks = 0;
        if (gun_trigger_pair_tick_controls(&pair, profile, 1,
                GUN_SECONDARY_TRIGGER_NORMAL, 0, 1.0f,
                1, 0, 1, 0, 0) != 0u || pair.trigger[0].idle_ticks != 1 ||
            gun_trigger_pair_tick_controls(&pair, profile, 1,
                GUN_SECONDARY_TRIGGER_NORMAL, 0, 1.0f,
                1, 0, 1, 0, 0) != 1u) return 65;
    }
    /* PRJ2's newly packed lifecycle values must survive selected-record
     * loading for a projectile whose retail tag uses a rest timer. */
    for (i = 0; i < play_fp_count() - 2; i++) play_fp_cycle();
    primary_shot = play_fp_trigger_shot(0);
    if (strcmp(play_fp_path(), "weapons\\needler\\needler") != 0 || !primary_shot ||
        primary_shot->maximum_range != 20.0f || primary_shot->timer_upper_bound != 0.75f ||
        primary_shot->timer_lower_bound != 0.75f || primary_shot->projectile_flags != 0x0bu ||
        primary_shot->attached_damage_flags != 0 ||
        primary_shot->detonation_timer_starts != 2 ||
        primary_shot->attached_damage_minimum != 10.0f ||
        primary_shot->attached_damage_lower != 10.0f ||
        primary_shot->attached_damage_upper != 10.0f ||
        primary_shot->attached_damage_material_modifier_21 != 1.0f ||
        primary_shot->attached_damage_material_modifier_22 != 1.0f ||
        !primary_shot->damage_materials_valid ||
        primary_shot->attached_damage_material_modifier[17] < 0.599f ||
        primary_shot->attached_damage_material_modifier[17] > 0.601f ||
        primary_shot->minimum_velocity < 0.06666f || primary_shot->minimum_velocity > 0.06668f ||
        primary_shot->maximum_damage_distance != 10.0f ||
        primary_shot->angular_noise[2] < 0.26179f || primary_shot->angular_noise[2] > 0.26181f ||
        primary_shot->angular_noise[16] < 0.61085f || primary_shot->angular_noise[16] > 0.61088f ||
        primary_shot->parallel_friction[5] < 0.299f || primary_shot->parallel_friction[5] > 0.301f ||
        primary_shot->perpendicular_friction[5] < 0.299f ||
        primary_shot->perpendicular_friction[5] > 0.301f ||
        primary_shot->potential_response[2] != 2 ||
        primary_shot->potential_flags[2] != 0 || primary_shot->potential_skip_fraction[2] != 0.0f ||
        primary_shot->potential_angle_lower[2] != 0.0f ||
        primary_shot->potential_angle_upper[2] < 0.4363f ||
        primary_shot->potential_angle_upper[2] > 0.4364f ||
        primary_shot->guided_angular_velocity < 1.5707f ||
        primary_shot->guided_angular_velocity > 1.5709f) return 75;
    play_fp_cycle();
    play_fp_cycle();
    primary_shot = play_fp_trigger_shot(0);
    if (strcmp(play_fp_path(), "weapons\\fuel rod gun\\fuel rod") != 0 || !primary_shot ||
        primary_shot->deceleration_end != 100.0f || primary_shot->air_gravity_scale != 1.0f ||
        primary_shot->water_gravity_scale != 0.4f ||
        primary_shot->water_damage_range_lower_bound != 0.0f ||
        primary_shot->water_damage_range_upper_bound != 10.0f) return 76;
    for (i = 0; i < play_fp_count() &&
         strcmp(play_fp_path(), "weapons\\pistol\\pistol") != 0; i++) play_fp_cycle();
    primary_shot = play_fp_trigger_shot(0);
    if (strcmp(play_fp_path(), "weapons\\pistol\\pistol") != 0 || !primary_shot ||
        primary_shot->damage_flags != 0x2u) return 77;
    puts("selected TRG1/PRJ2 lifecycle/MAG2/WMD1/FEF1 traces and CE charge/release verified");
    return 0;
}
