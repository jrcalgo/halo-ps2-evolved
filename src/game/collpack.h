/* Read a stored COLL/TAGS pack produced by tools/convert_collision.py.
 * Pointers alias the pack bytes. The caller keeps the pack. No allocation. */
#ifndef GAME_COLLPACK_H
#define GAME_COLLPACK_H
#include "game/collide.h"
#include "game/vital.h"
#include <stddef.h>

#define COLL_TAG_FLOATS 24
#define COLL_RUNTIME_MATERIAL_TYPES 26

int collpack_section(const uint8_t *pack, size_t size, const char tag[4],
    const uint8_t **data, size_t *length);

/* Fills bsp with pointers into the COLL payload. Returns 0 on success. */
int collpack_collision(const uint8_t *payload, size_t length, collide_bsp *bsp);

uint32_t collpack_spawn_count(const uint8_t *payload);
/* out is x, y, z, yaw radians. Returns 0 on success. */
int collpack_spawn(const uint8_t *payload, uint32_t index, float out[4]);

int collpack_tags(const uint8_t *payload, size_t length, float out[COLL_TAG_FLOATS]);

/* Resolve the diagnostic cyborg's indirect resistance material from VIT1.
 * Body/shield material types come from the collision model resistance tags. */
int collpack_vital_profile(const uint8_t *payload, size_t length,
    vital_damage_profile *profile, int16_t *body_material_type,
    int16_t *shield_material_type);

/* ACOL v2 view: packed node-default records and triangles alias the payload.
 * Defaults are bind-pose only; callers must provide animated node transforms
 * before treating these triangles as live actor collision. */
typedef struct {
    const uint8_t *nodes;
    const uint8_t *triangles;
    uint16_t node_count;
    uint32_t triangle_count;
    uint32_t node_stride;
    uint32_t triangle_stride;
} collpack_actor_collision_view;
int collpack_actor_collision(const uint8_t *payload, size_t length,
    collpack_actor_collision_view *view);
#endif
