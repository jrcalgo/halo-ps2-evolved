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
    cursor += counts[8] * 16;
    if (cursor + 4 > length) return -1;
    bsp->material_count = rd32(payload + cursor);
    cursor += 4;
    if (bsp->material_count > 256 || cursor + (size_t)bsp->material_count * 2 > length) return -1;
    bsp->material_types = (const int16_t *)(payload + cursor);
    for (index = 0; index < bsp->material_count; index++) {
        int16_t type;
        memcpy(&type, payload + cursor + index * 2, sizeof type);
        if (type < -1 || type >= COLL_RUNTIME_MATERIAL_TYPES) return -1;
    }
    return 0;
}

uint32_t collpack_spawn_count(const uint8_t *payload)
{
    return rd32(payload + 32);
}

static int finite_float(float value)
{
    return value == value && value > -1.0e20f && value < 1.0e20f;
}

int collpack_actor_collision(const uint8_t *payload, size_t length,
    collpack_actor_collision_view *view)
{
    uint16_t version, node_count;
    uint32_t triangle_count, node_stride, cursor, i;
    const uint32_t triangle_stride = 46;
    if (!payload || !view || length < 16 || memcmp(payload, "ACL1", 4) != 0) return -1;
    memcpy(&version, payload + 4, 2);
    memcpy(&node_count, payload + 6, 2);
    triangle_count = rd32(payload + 8);
    node_stride = rd32(payload + 12);
    if (version != 2 || node_count == 0 || node_count > 64 || node_stride != 36 ||
        triangle_count > 8192) return -1;
    cursor = 16;
    if ((size_t)cursor + (size_t)node_count * node_stride > length) return -1;
    view->nodes = payload + cursor;
    for (i = 0; i < node_count; i++) {
        const uint8_t *node = view->nodes + i * node_stride;
        int16_t index, parent;
        float values[8], norm;
        unsigned j;
        memcpy(&index, node, 2);
        memcpy(&parent, node + 2, 2);
        if (index != (int16_t)i || parent < -1 || parent >= (int16_t)node_count || parent == index)
            return -1;
        memcpy(values, node + 4, sizeof values);
        norm = values[3] * values[3] + values[4] * values[4] +
            values[5] * values[5] + values[6] * values[6];
        if (!finite_float(norm) || norm < 0.9f || norm > 1.1f) return -1;
        for (j = 0; j < 8; j++) if (!finite_float(values[j])) return -1;
    }
    cursor += node_count * node_stride;
    if ((size_t)cursor + (size_t)triangle_count * triangle_stride != length) return -1;
    view->triangles = payload + cursor;
    for (i = 0; i < triangle_count; i++) {
        const uint8_t *triangle = view->triangles + i * triangle_stride;
        int16_t node, region, part, material, surface;
        float xyz[9];
        unsigned j;
        memcpy(&node, triangle, 2);
        memcpy(&region, triangle + 2, 2);
        memcpy(&part, triangle + 4, 2);
        memcpy(&material, triangle + 6, 2);
        memcpy(&surface, triangle + 8, 2);
        memcpy(xyz, triangle + 10, sizeof xyz);
        if (node < 0 || node >= (int16_t)node_count || region < 0 || part < 0 ||
            material < 0 || surface < 0) return -1;
        for (j = 0; j < 9; j++) if (!finite_float(xyz[j])) return -1;
    }
    view->node_count = node_count;
    view->triangle_count = triangle_count;
    view->node_stride = node_stride;
    view->triangle_stride = triangle_stride;
    return 0;
}

int collpack_vital_profile(const uint8_t *payload, size_t length,
    vital_damage_profile *profile, int16_t *body_material_type,
    int16_t *shield_material_type)
{
    uint16_t version, material_count;
    int16_t indirect_index, shield_type, body_type = -1;
    uint32_t index, offset = 32;
    float maximum_body, maximum_shield, minimum_stun, stun_seconds, recharge_step;
    float shield_leak, shield_multiplier, body_multiplier;
    const uint8_t *record;
    if (!payload || !profile || !body_material_type || !shield_material_type || length < 32 ||
        memcmp(payload, "VIT1", 4) != 0) return -1;
    memcpy(&version, payload + 4, 2);
    memcpy(&material_count, payload + 6, 2);
    memcpy(&indirect_index, payload + 8, 2);
    memcpy(&shield_type, payload + 10, 2);
    if (version != 1 || material_count == 0 || material_count > 40 || indirect_index < 0 ||
        indirect_index >= material_count || length != 32u + (size_t)material_count * 14u ||
        shield_type < -1 || shield_type >= COLL_RUNTIME_MATERIAL_TYPES) return -1;
    memcpy(&maximum_body, payload + 12, 4);
    memcpy(&maximum_shield, payload + 16, 4);
    memcpy(&minimum_stun, payload + 20, 4);
    memcpy(&stun_seconds, payload + 24, 4);
    memcpy(&recharge_step, payload + 28, 4);
    if (!finite_float(maximum_body) || !finite_float(maximum_shield) ||
        !finite_float(minimum_stun) || !finite_float(stun_seconds) ||
        !finite_float(recharge_step) || maximum_body <= 0.0f || maximum_shield <= 0.0f ||
        minimum_stun < 0.0f || stun_seconds < 0.0f || stun_seconds * 30.0f > 32767.0f ||
        recharge_step < 0.0f || recharge_step > 1.0f) return -1;
    for (index = 0; index < material_count; index++) {
        int16_t type;
        record = payload + offset + index * 14u;
        memcpy(&type, record, 2);
        memcpy(&shield_leak, record + 2, 4);
        memcpy(&shield_multiplier, record + 6, 4);
        memcpy(&body_multiplier, record + 10, 4);
        if (type < -1 || type >= COLL_RUNTIME_MATERIAL_TYPES ||
            !finite_float(shield_leak) || !finite_float(shield_multiplier) ||
            !finite_float(body_multiplier) || shield_leak < 0.0f || shield_leak > 1.0f ||
            shield_multiplier < 0.0f || body_multiplier < 0.0f) return -1;
        if (index == (uint32_t)indirect_index) body_type = type;
    }
    if (body_type < 0) return -1;
    record = payload + offset + (uint32_t)indirect_index * 14u;
    memcpy(&shield_leak, record + 2, 4);
    memcpy(&shield_multiplier, record + 6, 4);
    memcpy(&body_multiplier, record + 10, 4);
    profile->maximum_body = maximum_body;
    profile->maximum_shield = maximum_shield;
    profile->shield_leak_fraction = shield_leak;
    profile->shield_damage_multiplier = shield_multiplier;
    profile->body_damage_multiplier = body_multiplier;
    profile->minimum_shield_stun_damage = minimum_stun;
    profile->shield_stun_ticks = (short)(stun_seconds * 30.0f + 0.5f);
    profile->shield_recharge_step = recharge_step;
    profile->indirect_material_index = indirect_index;
    profile->material_count = material_count;
    for (index = 0; index < material_count; index++) {
        record = payload + offset + index * 14u;
        memcpy(&profile->material[index].material_type, record, 2);
        memcpy(&profile->material[index].shield_leak_fraction, record + 2, 4);
        memcpy(&profile->material[index].shield_damage_multiplier, record + 6, 4);
        memcpy(&profile->material[index].body_damage_multiplier, record + 10, 4);
    }
    *body_material_type = body_type;
    *shield_material_type = shield_type;
    return 0;
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
