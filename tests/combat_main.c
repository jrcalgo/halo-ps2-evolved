#include "game/combat.h"

#include <assert.h>
#include <stdio.h>
#include <string.h>

static const combat_weapon_spec specs[] = {
    { .id = 1, .magazine_size = 12, .reserve_capacity = 120,
      .rounds_per_shot = 1, .shot_interval_ticks = 5, .reload_ticks = 30,
      .projectile_lifetime_ticks = 1, .damage = 40, .melee_damage = 55,
      .fire_kind = COMBAT_HITSCAN, .automatic = 0 },
    { .id = 2, .magazine_size = 60, .reserve_capacity = 600,
      .rounds_per_shot = 1, .shot_interval_ticks = 2, .reload_ticks = 45,
      .projectile_lifetime_ticks = 1, .damage = 12, .melee_damage = 45,
      .fire_kind = COMBAT_HITSCAN, .automatic = 1 },
    { .id = 3, .magazine_size = 2, .reserve_capacity = 20,
      .rounds_per_shot = 1, .shot_interval_ticks = 8, .reload_ticks = 45,
      .projectile_lifetime_ticks = 90, .damage = 80, .melee_damage = 45,
      .projectile_speed = 1.0f, .projectile_radius = 0.1f,
      .blast_radius = 2.0f, .blast_damage = 120,
      .fire_kind = COMBAT_EXPLOSIVE, .automatic = 0 },
};

static combat_command command(void)
{
    combat_command c = {0};
    c.aim[0] = 1.0f;
    return c;
}

static void step(combat_world *w, combat_command c)
{
    combat_command all[COMBAT_MAX_PLAYERS] = {0};
    all[0] = c;
    combat_step(w, all);
}

static void new_world(combat_world *w)
{
    assert(combat_init(w, specs, sizeof specs / sizeof specs[0], 23) == 0);
}

static void pistol_and_reload(void)
{
    combat_world w;
    combat_target t = { .position = {5, 0, 0}, .radius = 0.5f,
                        .health = 100, .shield = 25, .alive = 1 };
    combat_command c = command();
    unsigned i;
    new_world(&w);
    assert(combat_set_grenade_spec(&w, 3) == 0);
    assert(combat_add_target(&w, &t) == 0);
    assert(combat_give_weapon(&w, 0, 1, 1, 11) == 0);
    c.fire = 1;
    step(&w, c);
    assert(w.targets[0].shield == 0 && w.targets[0].health == 85);
    assert(w.players[0].weapons[0].rounds_loaded == 0);
    for (i = 0; i < 10; ++i) step(&w, c);
    assert(w.targets[0].health == 85); /* semi-auto needs a new press */
    c.fire = 0; c.reload = 1;
    step(&w, c);
    assert(w.players[0].weapons[0].reload_remaining == 30);
    c.reload = 0;
    for (i = 0; i < 29; ++i) step(&w, c);
    assert(w.players[0].weapons[0].rounds_loaded == 0);
    step(&w, c);
    assert(w.players[0].weapons[0].rounds_loaded == 11);
    assert(w.players[0].weapons[0].rounds_reserve == 0);
    printf("pistol shield=%.0f body=%.0f reload_tick=%u loaded=%u\n",
        w.targets[0].shield, w.targets[0].health, w.tick,
        w.players[0].weapons[0].rounds_loaded);
}

static void automatic_and_pickup(void)
{
    combat_world w;
    combat_command c = command();
    combat_pickup p = { .weapon_id = 2, .rounds_loaded = 60,
                        .rounds_reserve = 120, .active = 1 };
    unsigned i;
    new_world(&w);
    assert(combat_give_weapon(&w, 0, 1, 12, 24) == 0);
    assert(combat_add_pickup(&w, &p) == 0);
    c.pickup = 1;
    step(&w, c);
    assert(!w.pickups[0].active && w.players[0].weapons[1].occupied);
    c.pickup = 0; c.switch_weapon = 1;
    step(&w, c);
    assert(w.players[0].current_slot == 1);
    c.switch_weapon = 0; c.fire = 1;
    for (i = 0; i < 5; ++i) step(&w, c);
    assert(w.players[0].weapons[1].rounds_loaded == 57);
    printf("automatic shots=%u pickup=%u\n", 3u, !w.pickups[0].active);
}

static void explosive_and_exhaustion(void)
{
    combat_world w;
    combat_target t = { .position = {2, 0, 0}, .radius = 0.5f,
                        .health = 100, .alive = 1 };
    combat_command c = command();
    unsigned i;
    new_world(&w);
    assert(combat_give_weapon(&w, 0, 3, 2, 0) == 0);
    assert(combat_add_target(&w, &t) == 0);
    c.fire = 1;
    step(&w, c);
    assert(w.targets[0].alive);
    c.fire = 0;
    step(&w, c);
    assert(!w.targets[0].alive && w.targets[0].health == 0);
    for (i = 0; i < COMBAT_MAX_PROJECTILES; ++i) {
        w.projectiles[i].active = 1;
        w.projectiles[i].lifetime = 100;
    }
    for (i = 0; i < 8; ++i) step(&w, c);
    c.fire = 1;
    step(&w, c);
    assert(w.players[0].weapons[0].rounds_loaded == 0);
    assert(w.projectiles[COMBAT_MAX_PROJECTILES - 1].active);
    printf("explosive target_alive=%u projectile_cap=%u\n",
        w.targets[0].alive, COMBAT_MAX_PROJECTILES);
}

static void melee_and_replay(void)
{
    combat_world a, b;
    combat_target t = { .position = {1, 0, 0}, .radius = 0.4f,
                        .health = 45, .alive = 1 };
    combat_command c = command();
    unsigned i;
    volatile unsigned render_work = 0;
    new_world(&a);
    new_world(&b);
    assert(combat_add_target(&a, &t) == 0);
    assert(combat_add_target(&b, &t) == 0);
    assert(combat_give_weapon(&a, 0, 1, 12, 24) == 0);
    assert(combat_give_weapon(&b, 0, 1, 12, 24) == 0);
    c.melee = 1;
    step(&a, c);
    step(&b, c);
    assert(!a.targets[0].alive);
    for (i = 0; i < 100; ++i) {
        c.melee = 0;
        c.fire = (i % 7u) == 0;
        step(&a, c);
        render_work += i; /* presentation work between the same simulation ticks */
        step(&b, c);
    }
    assert(render_work > 0);
    assert(memcmp(&a, &b, sizeof a) == 0);
    printf("melee alive=%u replay_ticks=%u equal=1\n", a.targets[0].alive, a.tick);
}

static void grenade_uses_grenade_damage(void)
{
    combat_world w;
    combat_target t = { .position = {1.0f, 0, 0}, .radius = 0.3f,
                        .health = 100, .alive = 1 };
    combat_command c = command();
    unsigned i;
    new_world(&w);
    assert(combat_give_weapon(&w, 0, 1, 12, 24) == 0);
    assert(combat_set_grenade_spec(&w, 3) == 0);
    assert(combat_add_target(&w, &t) == 0);
    c.throw_grenade = 1;
    step(&w, c);
    assert(w.players[0].grenade_count == 1);
    c.throw_grenade = 0;
    for (i = 0; i < 90 && w.targets[0].alive; ++i) step(&w, c);
    assert(!w.targets[0].alive);
    assert(w.players[0].weapons[0].rounds_loaded == 12);
    printf("grenade target_alive=%u pistol_loaded=%u\n", w.targets[0].alive,
        w.players[0].weapons[0].rounds_loaded);
}

static void unarmed_melee(void)
{
    combat_world w;
    combat_target t = { .position = {1.0f, 0, 0}, .radius = 0.3f,
                        .health = 45, .alive = 1 };
    combat_command c = command();
    new_world(&w);
    assert(combat_add_target(&w, &t) == 0);
    c.melee = 1;
    step(&w, c);
    assert(!w.targets[0].alive);
}

int main(void)
{
    pistol_and_reload();
    automatic_and_pickup();
    explosive_and_exhaustion();
    melee_and_replay();
    grenade_uses_grenade_damage();
    unarmed_melee();
    return 0;
}
