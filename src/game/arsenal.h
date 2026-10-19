/* Every retail weap path. The record is the tag fields that change a shot:
 * rate, latch, charge, heat, ammo, and the shotgun shell reload. Flag and
 * ball have no trigger. The energy sword reports its melee damage and does
 * not fire. No heap. The caller owns the record. */
#ifndef GAME_ARSENAL_H
#define GAME_ARSENAL_H
#include <stdint.h>

#define ARSENAL_NAME 64
#define ARSENAL_HOLD 0
#define ARSENAL_RELEASE 1

#pragma pack(push, 1)
typedef struct {
    char name[ARSENAL_NAME];
    int16_t weapon_type;
    int16_t trigger_count;
    int16_t loaded_max, initial_rounds, rounds_reloaded, magazine_flags;
    int16_t ready_frames, reload_frames, enter_frames;
    float heat_overheat, heat_recovery, heat_loss;
    float melee_damage;
    uint32_t flags[2];
    float rate_initial[2], rate_final[2], charge[2], charged[2];
    float heat_per_round[2], rate_accel[2], rate_decel[2];
    int16_t rounds_per_shot[2], pellets[2], magazine_index[2], overcharge_action[2];
    int16_t mode;
} arsenal_spec;
#pragma pack(pop)

typedef struct {
    int shots;
    int pellets;
    int overheated;
    int loaded;
    float heat;
    float melee;
    int tick_count;
    int ticks[128];
} arsenal_result;

void arsenal_run(const arsenal_spec *spec, int ticks, arsenal_result *out);
#endif
