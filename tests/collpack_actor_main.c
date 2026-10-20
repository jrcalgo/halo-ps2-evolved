#include "game/collpack.h"
#include <stdio.h>
#include <string.h>

static void put16(uint8_t *p, unsigned value)
{
    uint16_t v = (uint16_t)value;
    memcpy(p, &v, 2);
}

static void put32(uint8_t *p, uint32_t value)
{
    memcpy(p, &value, 4);
}

static void put_float(uint8_t *p, float value)
{
    memcpy(p, &value, 4);
}

int main(void)
{
    uint8_t payload[16 + 2 * 36 + 46];
    collpack_actor_collision_view view;
    float matrices[2][12] = {{0}}, origin[3] = {0.0f, 0.0f, 1.0f};
    float direction[3] = {0.0f, 0.0f, -1.0f};
    collpack_actor_hit hit;
    unsigned i;
    memset(payload, 0, sizeof payload);
    memcpy(payload, "ACL1", 4);
    put16(payload + 4, 2);
    put16(payload + 6, 2);
    put32(payload + 8, 1);
    put32(payload + 12, 36);
    for (i = 0; i < 2; i++) {
        uint8_t *node = payload + 16 + i * 36;
        put16(node, i);
        put16(node + 2, i == 0 ? 0xffffu : 0);
        put_float(node + 4 + 3 * 4, 0.0f);
        put_float(node + 4 + 6 * 4, 1.0f);
    }
    put16(payload + 16 + 72, 1);
    put16(payload + 16 + 74, 0);
    put16(payload + 16 + 76, 2);
    put16(payload + 16 + 78, 1);
    put16(payload + 16 + 80, 5);
    for (i = 0; i < 2; i++) {
        matrices[i][0] = matrices[i][5] = matrices[i][10] = 1.0f;
    }
    put_float(payload + 88 + 10, -1.0f);
    put_float(payload + 88 + 14, -1.0f);
    put_float(payload + 88 + 22, 1.0f);
    put_float(payload + 88 + 26, -1.0f);
    put_float(payload + 88 + 38, 1.0f);
    if (collpack_actor_collision(payload, sizeof payload, &view) != 0 ||
        view.node_count != 2 || view.triangle_count != 1 ||
        view.nodes != payload + 16 || view.triangles != payload + 88) return 1;
    if (collpack_actor_ray(&view, matrices, origin, direction, 2.0f, &hit) != 1) return 4;
    if (hit.node_index != 1 || hit.damage_part != 2 || hit.resistance_index != 1 ||
        hit.surface_index != 5 || hit.distance < 0.999f || hit.distance > 1.001f) return 6;
    origin[0] = 3.0f;
    if (collpack_actor_ray(&view, matrices, origin, direction, 2.0f, &hit) != 0) return 5;
    origin[0] = 0.0f;
    put16(payload + 16 + 72, 2);
    if (collpack_actor_collision(payload, sizeof payload, &view) == 0) return 2;
    put16(payload + 16 + 72, 1);
    if (collpack_actor_collision(payload, sizeof payload - 1, &view) == 0) return 3;
    puts("actor collision pack view ok");
    return 0;
}
