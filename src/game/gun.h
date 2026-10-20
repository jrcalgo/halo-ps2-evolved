/* Pistol and assault rifle, from weapons.c and the Blood Gulch tags.
 * The trigger is not the analog-rate flag and the age penalty is 0.
 * Reload length is the first-person reload-empty animation's frame
 * count. Ready length is the first-person ready animation. Both guns
 * leave the weapon state idle: the assault rifle has no object
 * animation graph, and the pistol's ready and reload slots are empty.
 * Chamber time is the tag value, which is 0. A player owns the weapon,
 * so a reload draws the rounds that enter the magazine from reserve.
 * Four inventory slots. No heap. */
#ifndef GAME_GUN_H
#define GAME_GUN_H
#include <stdint.h>

#define GUN_TICKS_PER_SECOND 30
#define GUN_CARRIER_SLOTS 4
#define GUN_MAG_IDLE 0
#define GUN_MAG_RELOADING 1
#define GUN_MAG_UNCHAMBERED 2
#define GUN_MAG_CHAMBERING 3
#define GUN_TRIG_IDLE 0
#define GUN_TRIG_CHARGING 1
#define GUN_TRIG_CHARGED 2
#define GUN_TRIG_LOCKED 3
#define GUN_TRIG_SPEWING 4
#define GUN_TRIG_UNINITIALIZED 8
#define GUN_TRIGGER_MAX 2
#define GUN_TRIGGER_MAGAZINES 2
#define GUN_TRIGGER_NONE (-1)
#define GUN_TRIGGER_CAN_PARTIAL (1u << 2)
#define GUN_TRIGGER_RANDOM_FIRING_EFFECTS (1u << 1)
#define GUN_TRIGGER_LATCHED (1u << 3)
#define GUN_TRIGGER_TOGGLES (1u << 4)
#define GUN_TRIGGER_USES_WEAPON_ORIGIN (1u << 5)
#define GUN_TRIGGER_STICKS_WHEN_DROPPED (1u << 6)
#define GUN_TRIGGER_ANALOG_RATE (1u << 9)
#define GUN_WEAPON_SECONDARY_TRIGGER_OVERRIDES_GRENADES (1u << 12)
#define GUN_WEAPON_CANNOT_FIRE_AT_MAXIMUM_AGE (1u << 11)
#define GUN_SECONDARY_TRIGGER_NORMAL 0
#define GUN_SECONDARY_TRIGGER_SLAVED_TO_PRIMARY 1
#define GUN_SECONDARY_TRIGGER_INHIBITS_PRIMARY 2
#define GUN_SECONDARY_TRIGGER_LOADS_ALTERNATE_AMMO 3
#define GUN_SECONDARY_TRIGGER_LOADS_MULTIPLE_PRIMARY_AMMO 4

typedef struct {
    float rate_of_fire;
    int16_t rounds_per_shot;
    int16_t rounds_loaded_maximum;
    int16_t rounds_total_initial;
    int16_t rounds_reloaded;
    int16_t ready_frames;
    int16_t reload_empty_frames;
    float chamber_seconds;
    int16_t projectiles_per_shot;
    int16_t shotgun_enter_frames; /* 0 unless weapon_type is shotgun */
    int chamber_every_shot;
    /* Magazine flag bit 0. A reload drops whatever is still loaded. */
    int wastes_rounds;
    /* Trigger flag bit 2. A short magazine can still fire and is then empty. */
    int partial_ammo;
    /* Trigger flag bit 3. The trigger must be released before another shot. */
    int latched;
    /* Trigger magazine index is valid and the magazine holds rounds. */
    int uses_magazine;
    /* The tag has a primary trigger. Sword, flag, and ball do not. */
    int has_trigger;
    float rate_final;
    float rate_accel;
    float rate_decel;
    int16_t rounds_recharged_per_second;
    float error_accel;
    float error_decel;
    float charge_seconds;
    float charged_seconds;
    float heat_overheat;
    float heat_recovery;
    float heat_loss;
    float heat_per_round;
    int16_t overcharged_action;
    int16_t trigger_count;
    float age_generated_per_round;
    float age_heat_recovery_penalty;
    float age_rate_of_fire_penalty;
    float age_misfire_start;
    float age_misfire_chance;
    int cannot_fire_at_maximum_age;
    int firing_effect_count;
    uint32_t trigger_flags;
    int16_t firing_effect_shots[2][2][2];
} gun_def;

typedef struct {
    int16_t loaded;
    int16_t total;
    uint8_t idle_ticks;
    int8_t magazine;
    int16_t magazine_timer;
    int8_t trigger;
    int16_t state_timer;
    int needs_reload;
    int released;
    float fraction;
    float error_fraction;
    float shot_error_fraction;
    float heat;
    float age;
    float overcharged;
    int16_t overheated;
    int16_t recharge_frac;
    uint32_t shots;
    uint32_t pellets;
    uint32_t firing_effects_used_flags;
    int16_t firing_effect_index;
    int16_t firing_effect_shots_remaining;
    int16_t last_firing_effect;
    int misfired;
} gun;

/* Bounded CE trigger profile/state used while porting multi-trigger weapons.
 * The first implementation scope is charging/release; it is intentionally
 * separate from the legacy single-trigger gun until tick traces agree. */
typedef struct {
    uint32_t flags;
    int16_t magazine_index;
    int16_t rounds_per_shot;
    int16_t projectiles_per_shot;
    int16_t minimum_rounds;
    int16_t overcharged_action;
    float rate_initial;
    float rate_final;
    float rate_acceleration;
    float rate_deceleration;
    float error_acceleration;
    float error_deceleration;
    float charging_seconds;
    float charged_seconds;
    float spew_seconds;
    float age_generated_per_round;
    float heat_generated_per_round;
    uint16_t firing_effect_count;
    int16_t firing_effect_shots[2][2];
    float age_misfire_start;
    float age_misfire_chance;
} gun_trigger_profile;

typedef struct {
    int16_t state;
    int16_t state_timer;
    int16_t idle_ticks;
    uint8_t released_since_shot;
    uint8_t fired_before_charging;
    uint8_t was_down;
    uint8_t toggled;
    uint8_t misfired;
    uint8_t pad;
    float rate_fraction;
    float error_fraction;
    uint32_t firing_effects_used_flags;
    int16_t firing_effect_index;
    int16_t firing_effect_shots_remaining;
} gun_trigger_runtime;

typedef struct {
    gun_trigger_runtime trigger[GUN_TRIGGER_MAX];
    int16_t magazine_loaded[GUN_TRIGGER_MAGAZINES];
    uint8_t detonated;
    uint8_t player_owned;
    uint32_t weapon_flags;
    float weapon_age;
    float age_rate_of_fire_penalty;
    float age_heat_recovery_penalty;
    float heat_overheated_threshold;
    float heat_recovery_threshold;
    float heat_loss_per_second;
    float heat;
    float overcharged;
    uint8_t overheated;
    uint8_t can_begin_firing;
} gun_trigger_pair;

typedef struct {
    const gun_def *def;
    gun weapon;
    int occupied;
} gun_carry;

typedef struct {
    gun_carry slot[GUN_CARRIER_SLOTS];
    int current;
    int desired;
} gun_carrier;

extern const gun_def GUN_PISTOL;
extern const gun_def GUN_ASSAULT_RIFLE;
extern const gun_def GUN_SHOTGUN;

void gun_init(gun *g, const gun_def *def);
/* trigger and reload are held. Returns 1 when a shot is discharged. */
int gun_tick(gun *g, const gun_def *def, int trigger, int reload);
/* Seeded variant shares CE's LCG stream with cone, projectile and damage
 * sampling. `seed` may be NULL for deterministic state-only host traces. */
int gun_tick_seeded(gun *g, const gun_def *def, int trigger, int reload, uint32_t *seed);
void gun_trigger_pair_init(gun_trigger_pair *pair, const int16_t loaded[GUN_TRIGGER_MAGAZINES]);
/* Returns a bit per discharged trigger. busy_magazines uses one bit per slot. */
unsigned gun_trigger_pair_tick(gun_trigger_pair *pair,
    const gun_trigger_profile profile[GUN_TRIGGER_MAX], int trigger_count,
    unsigned held_triggers, unsigned busy_magazines);
/* Input magnitudes are [0,1]; analog-rate profiles use the scalar directly. */
unsigned gun_trigger_pair_tick_input(gun_trigger_pair *pair,
    const gun_trigger_profile profile[GUN_TRIGGER_MAX], int trigger_count,
    unsigned held_triggers, const float trigger_values[GUN_TRIGGER_MAX],
    unsigned busy_magazines);
/* Seeded variants share the weapon/projectile LCG; NULL keeps state-only traces. */
unsigned gun_trigger_pair_tick_seeded(gun_trigger_pair *pair,
    const gun_trigger_profile profile[GUN_TRIGGER_MAX], int trigger_count,
    unsigned held_triggers, unsigned busy_magazines, uint32_t *seed);
unsigned gun_trigger_pair_tick_input_seeded(gun_trigger_pair *pair,
    const gun_trigger_profile profile[GUN_TRIGGER_MAX], int trigger_count,
    unsigned held_triggers, const float trigger_values[GUN_TRIGGER_MAX],
    unsigned busy_magazines, uint32_t *seed);
/* CE control preprocessing. Secondary input requires the weapon's override
 * flag. `enabled` models CE's user-busy/weapon-state-timer gate; `dropped`
 * models an unparented weapon. Modes 3/4 also change magazine loading and are
 * not emulated by this firing-only boundary. */
unsigned gun_trigger_pair_tick_controls(gun_trigger_pair *pair,
    const gun_trigger_profile profile[GUN_TRIGGER_MAX], int trigger_count,
    int secondary_trigger_mode, uint32_t weapon_flags, float age_rate_of_fire_penalty,
    int primary_down, int secondary_down, int enabled, int dropped,
    unsigned busy_magazines);
unsigned gun_trigger_pair_tick_controls_seeded(gun_trigger_pair *pair,
    const gun_trigger_profile profile[GUN_TRIGGER_MAX], int trigger_count,
    int secondary_trigger_mode, uint32_t weapon_flags, float age_rate_of_fire_penalty,
    int primary_down, int secondary_down, int enabled, int dropped,
    unsigned busy_magazines, uint32_t *seed);

void gun_carrier_init(gun_carrier *carrier);
/* First free slot. The first weapon, with nothing desired, becomes desired. */
int gun_carrier_pickup(gun_carrier *carrier, const gun_def *def);
void gun_carrier_select(gun_carrier *carrier, int slot);
int gun_carrier_tick(gun_carrier *carrier, int trigger, int reload);
#endif
