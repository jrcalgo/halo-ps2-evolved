#include "game/collpack.h"
#include <string.h>

static uint32_t rd32(const uint8_t *p)
{
    uint32_t v;
    memcpy(&v, p, 4);
    return v;
}

int collpack_section(const uint8_t *pack, size_t size, const char tag[4],
    const uint8_t **data, size_t *length)
{
    uint32_t count, index;
    if (size < 64 || memcmp(pack, "HP2P", 4) != 0) return -1;
    count = pack[6] | ((uint32_t)pack[7] << 8);
    if (count > 64 || 64 + count * 32 > size) return -1;
    for (index = 0; index < count; index++) {
        const uint8_t *entry = pack + 64 + index * 32;
        uint32_t offset = rd32(entry + 4);
        uint32_t stored = rd32(entry + 8);
        uint32_t raw = rd32(entry + 12);
        uint32_t codec = rd32(entry + 16);
        if (memcmp(entry, tag, 4) != 0) continue;
        if (codec != 0 || stored != raw || offset + raw > size) return -1;
        *data = pack + offset;
        *length = raw;
        return 0;
    }
    return -1;
}

int collpack_collision(const uint8_t *payload, size_t length, collide_bsp *bsp)
{
    static const uint32_t stride[8] = {16, 12, 8, 8, 20, 12, 24, 16};
    uint32_t counts[9], index, cursor;
    if (length < 36) return -1;
    for (index = 0; index < 9; index++) counts[index] = rd32(payload + index * 4);
    cursor = 36;
    memset(bsp, 0, sizeof *bsp);
    bsp->plane_count = counts[0];
    bsp->node_count = counts[1];
    bsp->leaf_count = counts[2];
    bsp->ref_count = counts[3];
    bsp->node2d_count = counts[4];
    bsp->surface_count = counts[5];
    bsp->edge_count = counts[6];
    bsp->vertex_count = counts[7];
    if (cursor + (size_t)counts[0] * stride[0] > length) return -1;
    bsp->planes = (const float *)(payload + cursor);
    cursor += counts[0] * stride[0];
    if (cursor + (size_t)counts[1] * stride[1] > length) return -1;
    bsp->nodes = (const uint32_t *)(payload + cursor);
    cursor += counts[1] * stride[1];
    if (cursor + (size_t)counts[2] * stride[2] > length) return -1;
    bsp->leaves = payload + cursor;
    cursor += counts[2] * stride[2];
    if (cursor + (size_t)counts[3] * stride[3] > length) return -1;
    bsp->refs = (const uint32_t *)(payload + cursor);
    cursor += counts[3] * stride[3];
    if (cursor + (size_t)counts[4] * stride[4] > length) return -1;
    bsp->nodes2d = payload + cursor;
    cursor += counts[4] * stride[4];
    if (cursor + (size_t)counts[5] * stride[5] > length) return -1;
    bsp->surfaces = payload + cursor;
    cursor += counts[5] * stride[5];
    if (cursor + (size_t)counts[6] * stride[6] > length) return -1;
    bsp->edges = payload + cursor;
    cursor += counts[6] * stride[6];
    if (cursor + (size_t)counts[7] * stride[7] > length) return -1;
    bsp->vertices = payload + cursor;
    cursor += counts[7] * stride[7];
    if (cursor + (size_t)counts[8] * 16 > length) return -1;
    return 0;
}

uint32_t collpack_spawn_count(const uint8_t *payload)
{
    return rd32(payload + 32);
}

int collpack_spawn(const uint8_t *payload, uint32_t index, float out[4])
{
    static const uint32_t stride[8] = {16, 12, 8, 8, 20, 12, 24, 16};
    uint32_t counts[8], cursor = 36, item;
    if (index >= collpack_spawn_count(payload)) return -1;
    for (item = 0; item < 8; item++) {
        counts[item] = rd32(payload + item * 4);
        cursor += counts[item] * stride[item];
    }
    memcpy(out, payload + cursor + index * 16, 16);
    return 0;
}

int collpack_tags(const uint8_t *payload, size_t length, float out[COLL_TAG_FLOATS])
{
    uint32_t count;
    if (length < 4 + COLL_TAG_FLOATS * 4) return -1;
    count = rd32(payload);
    if (count < COLL_TAG_FLOATS) return -1;
    memcpy(out, payload + 4, COLL_TAG_FLOATS * 4);
    return 0;
}
