#include "game/combat.h"

#include <math.h>
#include <string.h>

#define MELEE_RANGE_DEFAULT 1.25f
#define GRENADE_SPEED 0.20f
#define GRENADE_FUSE_TICKS 90u

static const combat_weapon_spec *find_spec(const combat_world *w, uint16_t id)
{
    uint16_t i;
    for (i = 0; i < w->spec_count; ++i)
        if (w->specs[i].id == id) return &w->specs[i];
    return 0;
}

static void event_push(combat_player *p, uint8_t actor, uint8_t type, int16_t target,
    uint16_t weapon, uint16_t value)
{
    combat_event *e;
    if (p->pending_events >= COMBAT_MAX_EVENTS) return;
    e = &p->events[p->pending_events++];
    e->type = type;
    e->actor = actor;
    e->target = target;
    e->weapon_id = weapon;
    e->value = value;
}

int combat_take_event(combat_player *p, combat_event *out)
{
    uint16_t i;
    if (!p || !out || p->pending_events == 0) return 0;
    *out = p->events[0];
    for (i = 1; i < p->pending_events; ++i) p->events[i - 1] = p->events[i];
    --p->pending_events;
    return 1;
}

int combat_init(combat_world *w, const combat_weapon_spec *specs,
    uint16_t spec_count, uint32_t seed)
{
    uint16_t i, j;
    if (!w || !specs || spec_count == 0) return -1;
    for (i = 0; i < spec_count; ++i) {
        const combat_weapon_spec *s = &specs[i];
        if (s->magazine_size == 0 || s->rounds_per_shot == 0 ||
            s->shot_interval_ticks == 0 || s->damage < 0.0f ||
            s->projectile_radius < 0.0f || s->blast_radius < 0.0f ||
            s->projectile_lifetime_ticks == 0) return -1;
        for (j = 0; j < i; ++j) if (specs[j].id == s->id) return -1;
    }
    memset(w, 0, sizeof *w);
    w->specs = specs;
    w->spec_count = spec_count;
    w->grenade_spec_id = COMBAT_NO_WEAPON;
    w->random_state = seed ? seed : 1u;
    for (i = 0; i < COMBAT_MAX_PLAYERS; ++i) {
        w->players[i].health = 100.0f;
        w->players[i].maximum_health = 100.0f;
        w->players[i].shield = 100.0f;
        w->players[i].maximum_shield = 100.0f;
        w->players[i].grenade_count = 2;
        w->players[i].alive = 1;
    }
    return 0;
}

int combat_add_target(combat_world *w, const combat_target *t)
{
    if (!w || !t || w->target_count >= COMBAT_MAX_TARGETS || t->radius <= 0.0f ||
        t->health < 0.0f || t->shield < 0.0f) return -1;
    w->targets[w->target_count] = *t;
    w->targets[w->target_count].alive = t->alive != 0;
    return w->target_count++;
}

int combat_add_pickup(combat_world *w, const combat_pickup *p)
{
    if (!w || !p || w->pickup_count >= COMBAT_MAX_PICKUPS || !find_spec(w, p->weapon_id)) return -1;
    w->pickups[w->pickup_count] = *p;
    w->pickups[w->pickup_count].active = p->active != 0;
    return w->pickup_count++;
}

int combat_give_weapon(combat_world *w, uint8_t player, uint16_t id,
    uint16_t loaded, uint16_t reserve)
{
    uint16_t i, slot = COMBAT_MAX_WEAPON_SLOTS;
    const combat_weapon_spec *s;
    combat_player *p;
    if (!w || player >= COMBAT_MAX_PLAYERS || !(s = find_spec(w, id))) return -1;
    p = &w->players[player];
    for (i = 0; i < COMBAT_MAX_WEAPON_SLOTS; ++i) {
        if (p->weapons[i].occupied && p->weapons[i].weapon_id == id) {
            slot = i;
            break;
        }
        if (!p->weapons[i].occupied && slot == COMBAT_MAX_WEAPON_SLOTS) slot = i;
    }
    if (slot == COMBAT_MAX_WEAPON_SLOTS) return -1;
    if (loaded > s->magazine_size) loaded = s->magazine_size;
    if (reserve > s->reserve_capacity) reserve = s->reserve_capacity;
    p->weapons[slot].weapon_id = id;
    p->weapons[slot].rounds_loaded = loaded;
    p->weapons[slot].rounds_reserve = reserve;
    p->weapons[slot].occupied = 1;
    if (p->weapons[p->current_slot].occupied == 0) p->current_slot = slot;
    return slot;
}

int combat_set_grenade_spec(combat_world *w, uint16_t id)
{
    const combat_weapon_spec *s;
    if (!w || !(s = find_spec(w, id)) || s->blast_radius <= 0.0f ||
        s->blast_damage <= 0.0f) return -1;
    w->grenade_spec_id = id;
    return 0;
}

static uint32_t random_next(combat_world *w)
{
    w->random_state = w->random_state * 1664525u + 1013904223u;
    return w->random_state;
}

static float random_signed(combat_world *w)
{
    return (float)(random_next(w) >> 8) / 8388608.0f - 1.0f;
}

static float dot3(const float *a, const float *b)
{
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
}

static float distance2(const float *a, const float *b)
{
    float x = a[0] - b[0], y = a[1] - b[1], z = a[2] - b[2];
    return x * x + y * y + z * z;
}

static int aim_direction(combat_world *w, const combat_command *cmd,
    float spread, float *out)
{
    float d[3] = { cmd->aim[0], cmd->aim[1], cmd->aim[2] };
    float len;
    if (spread > 0.0f) {
        d[0] += random_signed(w) * spread;
        d[1] += random_signed(w) * spread;
        d[2] += random_signed(w) * spread;
    }
    len = sqrtf(dot3(d, d));
    if (len < 1.0e-6f) return 0;
    out[0] = d[0] / len;
    out[1] = d[1] / len;
    out[2] = d[2] / len;
    return 1;
}

static int first_hit(const combat_world *w, const float *origin,
    const float *direction, float max_distance, float radius)
{
    int hit = -1;
    float best = max_distance;
    uint16_t i;
    for (i = 0; i < w->target_count; ++i) {
        const combat_target *t = &w->targets[i];
        float rel[3], along, perpendicular2, r;
        if (!t->alive) continue;
        rel[0] = t->position[0] - origin[0];
        rel[1] = t->position[1] - origin[1];
        rel[2] = t->position[2] - origin[2];
        along = dot3(rel, direction);
        if (along < 0.0f || along > best) continue;
        perpendicular2 = dot3(rel, rel) - along * along;
        r = t->radius + radius;
        if (perpendicular2 <= r * r) { best = along; hit = (int)i; }
    }
    return hit;
}

static void apply_damage(combat_world *w, uint8_t actor, int16_t index, float damage,
    uint16_t weapon)
{
    combat_target *t;
    float spill;
    if (index < 0 || (uint16_t)index >= w->target_count || damage <= 0.0f) return;
    t = &w->targets[index];
    if (!t->alive) return;
    spill = damage - t->shield;
    if (spill < 0.0f) spill = 0.0f;
    t->shield -= damage;
    if (t->shield < 0.0f) t->shield = 0.0f;
    t->health -= spill;
    event_push(&w->players[actor], actor, COMBAT_EVENT_DAMAGED, index, weapon,
        (uint16_t)(damage * 100.0f));
    if (t->health <= 0.0f) {
        t->health = 0.0f;
        t->alive = 0;
        event_push(&w->players[actor], actor, COMBAT_EVENT_DIED, index, weapon, 0);
    }
}

static int projectile_spawn(combat_world *w, uint8_t owner, const float *origin,
    const float *direction, const combat_weapon_spec *s, int grenade)
{
    uint16_t i;
    for (i = 0; i < COMBAT_MAX_PROJECTILES; ++i) if (!w->projectiles[i].active) {
        combat_projectile *p = &w->projectiles[i];
        memset(p, 0, sizeof *p);
        memcpy(p->position, origin, 3 * sizeof(float));
        p->velocity[0] = direction[0] * (grenade ? GRENADE_SPEED : s->projectile_speed);
        p->velocity[1] = direction[1] * (grenade ? GRENADE_SPEED : s->projectile_speed);
        p->velocity[2] = direction[2] * (grenade ? GRENADE_SPEED : s->projectile_speed) + (grenade ? 0.08f : 0.0f);
        p->damage = s->damage;
        p->weapon_id = s->id;
        p->blast_radius = s->blast_radius;
        p->blast_damage = s->blast_damage;
        p->radius = s->projectile_radius > 0.0f ? s->projectile_radius : 0.04f;
        p->lifetime = grenade ? GRENADE_FUSE_TICKS : s->projectile_lifetime_ticks;
        p->owner = owner;
        p->active = 1;
        p->affected_by_gravity = grenade != 0;
        return i;
    }
    return -1;
}

static void explode(combat_world *w, uint8_t owner, const float *at,
    float radius, float damage, uint16_t weapon)
{
    uint16_t i;
    float r2 = radius * radius;
    for (i = 0; i < w->target_count; ++i) {
        combat_target *t = &w->targets[i];
        float d2;
        if (!t->alive || (d2 = distance2(t->position, at)) > r2) continue;
        apply_damage(w, owner, (int16_t)i,
            damage * (1.0f - 0.5f * sqrtf(d2 / r2)), weapon);
    }
}

static void reload_start(combat_weapon_state *state,
    const combat_weapon_spec *s)
{
    if (state->reload_remaining || state->rounds_loaded >= s->magazine_size ||
        state->rounds_reserve == 0 || s->reload_ticks == 0) return;
    state->reload_remaining = s->reload_ticks;
}

static void player_fire(combat_world *w, uint8_t player, const combat_command *cmd)
{
    combat_player *p = &w->players[player];
    combat_weapon_state *st;
    const combat_weapon_spec *s;
    float direction[3];
    int target;
    int pressed = cmd->fire && !p->previous_fire;
    if (!p->alive || p->current_slot >= COMBAT_MAX_WEAPON_SLOTS) return;
    st = &p->weapons[p->current_slot];
    if (!st->occupied || !(s = find_spec(w, st->weapon_id))) return;
    if (cmd->reload) reload_start(st, s);
    if (st->reload_remaining || st->shot_cooldown || !(s->automatic ? cmd->fire : pressed)) return;
    if (st->rounds_loaded < s->rounds_per_shot) {
        event_push(p, player, COMBAT_EVENT_DRY_FIRE, -1, s->id, 0);
        reload_start(st, s);
        return;
    }
    if (!aim_direction(w, cmd, s->spread, direction)) return;
    st->rounds_loaded -= s->rounds_per_shot;
    st->shot_cooldown = s->shot_interval_ticks;
    event_push(p, player, COMBAT_EVENT_FIRED, -1, s->id, st->rounds_loaded);
    if (s->fire_kind == COMBAT_HITSCAN) {
        target = first_hit(w, p->position, direction, 100.0f, 0.0f);
        if (target >= 0) {
            event_push(p, player, COMBAT_EVENT_HIT, (int16_t)target, s->id, 0);
            apply_damage(w, player, (int16_t)target, s->damage, s->id);
        }
    } else if (projectile_spawn(w, player, p->position, direction, s, 0) < 0) {
        /* The round has fired: bounded projectile exhaustion is an observable miss. */
        event_push(p, player, COMBAT_EVENT_POOL_FULL, -1, s->id, 0);
    }
}

static void player_melee(combat_world *w, uint8_t player, const combat_command *cmd)
{
    combat_player *p = &w->players[player];
    float dir[3];
    int hit;
    const combat_weapon_spec *s = 0;
    if (!cmd->melee || p->previous_melee || !p->alive || !aim_direction(w, cmd, 0.0f, dir)) return;
    if (p->current_slot < COMBAT_MAX_WEAPON_SLOTS && p->weapons[p->current_slot].occupied)
        s = find_spec(w, p->weapons[p->current_slot].weapon_id);
    hit = first_hit(w, p->position, dir, MELEE_RANGE_DEFAULT, 0.0f);
    if (hit >= 0) {
        uint16_t wid = s ? s->id : COMBAT_NO_WEAPON;
        float damage = s && s->melee_damage > 0.0f ? s->melee_damage : 50.0f;
        apply_damage(w, player, (int16_t)hit, damage, wid);
        event_push(p, player, COMBAT_EVENT_MELEE, (int16_t)hit, wid, 0);
    }
}

static void player_grenade(combat_world *w, uint8_t player, const combat_command *cmd)
{
    combat_player *p = &w->players[player];
    const combat_weapon_spec *s;
    float direction[3];
    if (!cmd->throw_grenade || p->previous_grenade || !p->alive || p->grenade_count == 0 ||
        !aim_direction(w, cmd, 0.0f, direction)) return;
    s = find_spec(w, w->grenade_spec_id);
    if (!s) return;
    if (projectile_spawn(w, player, p->position, direction, s, 1) < 0) {
        event_push(p, player, COMBAT_EVENT_POOL_FULL, -1, s->id, 0);
        return;
    }
    --p->grenade_count;
    event_push(p, player, COMBAT_EVENT_GRENADE, -1, s->id, p->grenade_count);
}

static void player_pickup(combat_world *w, uint8_t player, const combat_command *cmd)
{
    combat_player *p = &w->players[player];
    uint16_t i;
    if (!cmd->pickup || p->previous_pickup || !p->alive) return;
    for (i = 0; i < w->pickup_count; ++i) {
        combat_pickup *pick = &w->pickups[i];
        if (pick->active && distance2(p->position, pick->position) <= 1.0f) {
            int slot = combat_give_weapon(w, player, pick->weapon_id,
                pick->rounds_loaded, pick->rounds_reserve);
            if (slot >= 0) {
                pick->active = 0;
                event_push(p, player, COMBAT_EVENT_PICKED_UP, (int16_t)i, pick->weapon_id, (uint16_t)slot);
            }
            return;
        }
    }
}

static void world_projectiles(combat_world *w)
{
    uint16_t i;
    for (i = 0; i < COMBAT_MAX_PROJECTILES; ++i) {
        combat_projectile *p = &w->projectiles[i];
        float next[3], delta[3], len;
        int hit;
        if (!p->active) continue;
        next[0] = p->position[0] + p->velocity[0];
        next[1] = p->position[1] + p->velocity[1];
        next[2] = p->position[2] + p->velocity[2];
        delta[0] = next[0] - p->position[0]; delta[1] = next[1] - p->position[1]; delta[2] = next[2] - p->position[2];
        len = sqrtf(dot3(delta, delta));
        if (len > 1.0e-6f) {
            float direction[3] = { delta[0] / len, delta[1] / len, delta[2] / len };
            hit = first_hit(w, p->position, direction, len, p->radius);
        } else hit = -1;
        if (hit >= 0 || ++p->age >= p->lifetime) {
            if (hit >= 0 && p->blast_radius <= 0.0f)
                apply_damage(w, p->owner, (int16_t)hit, p->damage, p->weapon_id);
            else if (p->blast_radius > 0.0f)
                explode(w, p->owner, hit >= 0 ? w->targets[hit].position : next,
                    p->blast_radius, p->blast_damage, p->weapon_id);
            p->active = 0;
            continue;
        }
        memcpy(p->position, next, sizeof next);
        if (p->affected_by_gravity) p->velocity[2] -= 0.0035651792f;
    }
}

void combat_step(combat_world *w, const combat_command commands[COMBAT_MAX_PLAYERS])
{
    uint16_t i, slot;
    if (!w || !commands) return;
    for (i = 0; i < COMBAT_MAX_PLAYERS; ++i) {
        combat_player *p = &w->players[i];
        const combat_command *cmd = &commands[i];
        for (slot = 0; slot < COMBAT_MAX_WEAPON_SLOTS; ++slot) {
            combat_weapon_state *st = &p->weapons[slot];
            const combat_weapon_spec *s = st->occupied ? find_spec(w, st->weapon_id) : 0;
            if (st->shot_cooldown) --st->shot_cooldown;
            if (st->reload_remaining && --st->reload_remaining == 0 && s) {
                uint16_t missing = s->magazine_size - st->rounds_loaded;
                uint16_t transfer = missing < st->rounds_reserve ? missing : st->rounds_reserve;
                st->rounds_loaded += transfer;
                st->rounds_reserve -= transfer;
                event_push(p, (uint8_t)i, COMBAT_EVENT_RELOADED, -1, s->id, st->rounds_loaded);
            }
        }
        if (cmd->switch_weapon && !p->previous_switch) {
            uint16_t other = (uint16_t)(p->current_slot ^ 1u);
            if (other < COMBAT_MAX_WEAPON_SLOTS && p->weapons[other].occupied) p->current_slot = other;
        }
        player_pickup(w, (uint8_t)i, cmd);
        player_fire(w, (uint8_t)i, cmd);
        player_melee(w, (uint8_t)i, cmd);
        player_grenade(w, (uint8_t)i, cmd);
        p->previous_fire = cmd->fire != 0;
        p->previous_switch = cmd->switch_weapon != 0;
        p->previous_melee = cmd->melee != 0;
        p->previous_grenade = cmd->throw_grenade != 0;
        p->previous_pickup = cmd->pickup != 0;
    }
    world_projectiles(w);
    ++w->tick;
}
