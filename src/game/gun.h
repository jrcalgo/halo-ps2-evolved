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
#define GUN_TRIG_UNINITIALIZED 8

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
    int16_t recharge_frac;
    uint32_t shots;
    uint32_t pellets;
} gun;

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

void gun_carrier_init(gun_carrier *carrier);
/* First free slot. The first weapon, with nothing desired, becomes desired. */
int gun_carrier_pickup(gun_carrier *carrier, const gun_def *def);
void gun_carrier_select(gun_carrier *carrier, int slot);
int gun_carrier_tick(gun_carrier *carrier, int trigger, int reload);
#endif
