#ifndef HALO_PS2_GAME_COMBAT_H
#define HALO_PS2_GAME_COMBAT_H

#include <stdint.h>

#define COMBAT_MAX_PLAYERS 4
#define COMBAT_MAX_WEAPON_SLOTS 2
#define COMBAT_MAX_TARGETS 16
#define COMBAT_MAX_PICKUPS 16
#define COMBAT_MAX_PROJECTILES 32
#define COMBAT_MAX_EVENTS 32
#define COMBAT_NO_WEAPON 0xffffu

typedef enum {
    COMBAT_HITSCAN = 0,
    COMBAT_PROJECTILE = 1,
    COMBAT_EXPLOSIVE = 2
} combat_fire_kind;

typedef struct {
    uint16_t id;
    uint16_t magazine_size;
    uint16_t reserve_capacity;
    uint16_t rounds_per_shot;
    uint16_t shot_interval_ticks;
    uint16_t reload_ticks;
    uint16_t projectile_lifetime_ticks;
    float damage;
    float melee_damage;
    float projectile_speed;
    float projectile_radius;
    float spread;
    float blast_radius;
    float blast_damage;
    combat_fire_kind fire_kind;
    uint8_t automatic;
} combat_weapon_spec;

typedef struct {
    float position[3];
    float direction[3];
    float radius;
    float health;
    float shield;
    uint8_t alive;
} combat_target;

typedef struct {
    uint16_t weapon_id;
    uint16_t rounds_loaded;
    uint16_t rounds_reserve;
    uint16_t reload_remaining;
    uint16_t shot_cooldown;
    uint8_t occupied;
} combat_weapon_state;

typedef struct {
    float position[3];
    float velocity[3];
    float damage;
    float blast_radius;
    float blast_damage;
    float radius;
    uint16_t weapon_id;
    uint16_t age;
    uint16_t lifetime;
    uint8_t owner;
    uint8_t active;
    uint8_t affected_by_gravity;
} combat_projectile;

typedef struct {
    uint16_t weapon_id;
    uint16_t rounds_loaded;
    uint16_t rounds_reserve;
    float position[3];
    uint8_t active;
} combat_pickup;

typedef struct {
    uint8_t fire;
    uint8_t reload;
    uint8_t switch_weapon;
    uint8_t melee;
    uint8_t throw_grenade;
    uint8_t pickup;
    float aim[3];
} combat_command;

typedef struct {
    uint8_t type;
    uint8_t actor;
    int16_t target;
    uint16_t weapon_id;
    uint16_t value;
} combat_event;

typedef struct {
    float position[3];
    float health;
    float maximum_health;
    float shield;
    float maximum_shield;
    uint16_t grenade_count;
    uint16_t current_slot;
    combat_weapon_state weapons[COMBAT_MAX_WEAPON_SLOTS];
    uint8_t alive;
    uint8_t previous_fire;
    uint8_t previous_switch;
    uint8_t previous_melee;
    uint8_t previous_grenade;
    uint8_t previous_pickup;
    uint8_t pending_events;
    combat_event events[COMBAT_MAX_EVENTS];
} combat_player;

typedef struct {
    uint32_t tick;
    uint32_t random_state;
    const combat_weapon_spec *specs;
    uint16_t spec_count;
    uint16_t grenade_spec_id;
    uint16_t target_count;
    uint16_t pickup_count;
    combat_player players[COMBAT_MAX_PLAYERS];
    combat_target targets[COMBAT_MAX_TARGETS];
    combat_pickup pickups[COMBAT_MAX_PICKUPS];
    combat_projectile projectiles[COMBAT_MAX_PROJECTILES];
} combat_world;

enum {
    COMBAT_EVENT_FIRED = 1,
    COMBAT_EVENT_RELOADED,
    COMBAT_EVENT_HIT,
    COMBAT_EVENT_DAMAGED,
    COMBAT_EVENT_DIED,
    COMBAT_EVENT_PICKED_UP,
    COMBAT_EVENT_DRY_FIRE,
    COMBAT_EVENT_POOL_FULL,
    COMBAT_EVENT_MELEE,
    COMBAT_EVENT_GRENADE
};

int combat_init(combat_world *world, const combat_weapon_spec *specs,
    uint16_t spec_count, uint32_t seed);
int combat_add_target(combat_world *world, const combat_target *target);
int combat_add_pickup(combat_world *world, const combat_pickup *pickup);
int combat_give_weapon(combat_world *world, uint8_t player, uint16_t weapon_id,
    uint16_t loaded, uint16_t reserve);
int combat_set_grenade_spec(combat_world *world, uint16_t weapon_id);
void combat_step(combat_world *world, const combat_command commands[COMBAT_MAX_PLAYERS]);
int combat_take_event(combat_player *player, combat_event *event);

#endif
