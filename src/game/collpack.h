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
#endif
