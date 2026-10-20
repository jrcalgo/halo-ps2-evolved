#include "game/collpack.h"
#include <math.h>
#include <string.h>

static uint32_t rd32(const uint8_t *p)
{
    uint32_t v;
    memcpy(&v, p, 4);
    return v;
}

static int finite_float(float value);

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

int collpack_location(const uint8_t *payload, size_t length, collide_location_view *location)
{
    uint16_t version, reserved;
    uint32_t leaf_count, cluster_count, plane_count, region_count, cursor;
    uint32_t i;
    if (!payload || !location || length < 24 || memcmp(payload, "LOC1", 4) != 0) return -1;
    memcpy(&version, payload + 4, 2);
    memcpy(&reserved, payload + 6, 2);
    leaf_count = rd32(payload + 8);
    cluster_count = rd32(payload + 12);
    plane_count = rd32(payload + 16);
    region_count = rd32(payload + 20);
    if (version != 1 || reserved != 0 || leaf_count > 32767 ||
        cluster_count > 32767 || plane_count > 32767 || region_count > 32767) return -1;
    cursor = 24;
    if ((size_t)cursor + (size_t)leaf_count * 2 > length) return -1;
    location->leaf_clusters = payload + cursor;
    cursor += leaf_count * 2;
    for (i = 0; i < leaf_count; i++) {
        int16_t cluster;
        memcpy(&cluster, payload + 24 + i * 2, 2);
        if (cluster < -1 || cluster >= (int32_t)cluster_count) return -1;
    }
    if ((size_t)cursor + (size_t)cluster_count * 2 > length) return -1;
    location->cluster_fog = payload + cursor;
    for (i = 0; i < cluster_count; i++) {
        uint16_t reference;
        memcpy(&reference, payload + cursor + i * 2, 2);
        if (reference == 0xFFFFu) continue;
        if (reference & 0x8000u) {
            if ((reference & 0x7FFFu) >= plane_count) return -1;
        } else if (reference >= region_count) return -1;
    }
    cursor += cluster_count * 2;
    if ((size_t)cursor + (size_t)plane_count * 18 > length) return -1;
    location->fog_planes = payload + cursor;
    for (i = 0; i < plane_count; i++) {
        const uint8_t *row = location->fog_planes + i * 18;
        int16_t region;
        float plane[4];
        unsigned j;
        memcpy(&region, row, 2);
        memcpy(plane, row + 2, sizeof plane);
        if (region < -1 || region >= (int32_t)region_count) return -1;
        for (j = 0; j < 4; j++)
            if (!finite_float(plane[j])) return -1;
    }
    cursor += plane_count * 18;
    if ((size_t)cursor + (size_t)region_count * 8 > length) return -1;
    location->fog_regions = payload + cursor;
    for (i = 0; i < region_count; i++) {
        const uint8_t *row = location->fog_regions + i * 8;
        float distance;
        if (row[0] & ~1u) return -1;
        memcpy(&distance, row + 4, 4);
        if (!finite_float(distance)) return -1;
    }
    cursor += region_count * 8;
    if (cursor != length) return -1;
    location->leaf_count = leaf_count;
    location->cluster_count = cluster_count;
    location->fog_plane_count = plane_count;
    location->fog_region_count = region_count;
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

static float actor_dot3(const float a[3], const float b[3])
{
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
}

static void actor_cross3(const float a[3], const float b[3], float out[3])
{
    out[0] = a[1] * b[2] - a[2] * b[1];
    out[1] = a[2] * b[0] - a[0] * b[2];
    out[2] = a[0] * b[1] - a[1] * b[0];
}

static void actor_transform_point(const float matrix[12], const float point[3], float out[3])
{
    unsigned row;
    for (row = 0; row < 3; row++)
        out[row] = matrix[row * 4] * point[0] + matrix[row * 4 + 1] * point[1] +
            matrix[row * 4 + 2] * point[2] + matrix[row * 4 + 3];
}

int collpack_actor_ray(const collpack_actor_collision_view *view,
    const float (*node_to_world)[12], const float origin[3],
    const float direction[3], float maximum_distance, collpack_actor_hit *hit)
{
    uint32_t i;
    int found = 0;
    float nearest = maximum_distance;
    if (!view || !view->nodes || !view->triangles || !node_to_world || !origin ||
        !direction || !hit || view->node_count == 0 || view->triangle_stride != 46 ||
        !finite_float(maximum_distance) || maximum_distance <= 0.0f) return -1;
    for (i = 0; i < 3; i++)
        if (!finite_float(origin[i]) || !finite_float(direction[i])) return -1;
    for (i = 0; i < view->node_count; i++) {
        unsigned j;
        for (j = 0; j < 12; j++) if (!finite_float(node_to_world[i][j])) return -1;
    }
    for (i = 0; i < view->triangle_count; i++) {
        const uint8_t *record = view->triangles + i * view->triangle_stride;
        int16_t node, region, part, material, surface;
        float local[9], p[3][3], edge1[3], edge2[3], pvec[3], tvec[3], qvec[3];
        float determinant, inverse, u, v, distance;
        float normal[3], normal_length;
        unsigned vertex;
        memcpy(&node, record, 2);
        memcpy(&region, record + 2, 2);
        memcpy(&part, record + 4, 2);
        memcpy(&material, record + 6, 2);
        memcpy(&surface, record + 8, 2);
        if (node < 0 || node >= (int16_t)view->node_count || region < 0 || part < 0 ||
            material < 0 || surface < 0) return -1;
        memcpy(local, record + 10, sizeof local);
        for (vertex = 0; vertex < 3; vertex++)
            actor_transform_point(node_to_world[node], local + vertex * 3, p[vertex]);
        for (vertex = 0; vertex < 3; vertex++) {
            edge1[vertex] = p[1][vertex] - p[0][vertex];
            edge2[vertex] = p[2][vertex] - p[0][vertex];
            tvec[vertex] = origin[vertex] - p[0][vertex];
        }
        actor_cross3(direction, edge2, pvec);
        determinant = actor_dot3(edge1, pvec);
        if (determinant > -1.0e-8f && determinant < 1.0e-8f) continue;
        inverse = 1.0f / determinant;
        u = actor_dot3(tvec, pvec) * inverse;
        if (u < 0.0f || u > 1.0f) continue;
        actor_cross3(tvec, edge1, qvec);
        v = actor_dot3(direction, qvec) * inverse;
        if (v < 0.0f || u + v > 1.0f) continue;
        distance = actor_dot3(edge2, qvec) * inverse;
        if (distance < 0.0f || distance >= nearest) continue;
        actor_cross3(edge1, edge2, normal);
        normal_length = sqrtf(actor_dot3(normal, normal));
        if (!(normal_length > 0.0f) || !finite_float(normal_length)) continue;
        normal[0] /= normal_length;
        normal[1] /= normal_length;
        normal[2] /= normal_length;
        nearest = distance;
        hit->distance = distance;
        hit->barycentric_u = u;
        hit->barycentric_v = v;
        memcpy(hit->normal, normal, sizeof hit->normal);
        hit->node_index = node;
        hit->region_index = region;
        hit->damage_part = part;
        hit->resistance_index = material;
        hit->surface_index = surface;
        found = 1;
    }
    return found;
}

int collpack_vital_profile(const uint8_t *payload, size_t length,
    vital_damage_profile *profile, int16_t *body_material_type,
    int16_t *shield_material_type)
{
    uint16_t version, material_count, region_count, reserved;
    int16_t indirect_index, shield_type, body_type = -1;
    uint32_t index, offset, material_stride;
    float maximum_body, maximum_shield, minimum_stun, stun_seconds, recharge_step;
    float shield_leak, shield_multiplier, body_multiplier;
    const uint8_t *record;
    if (!payload || !profile || !body_material_type || !shield_material_type || length < 36 ||
        memcmp(payload, "VIT1", 4) != 0) return -1;
    memcpy(&version, payload + 4, 2);
    memcpy(&material_count, payload + 6, 2);
    memcpy(&indirect_index, payload + 8, 2);
    memcpy(&shield_type, payload + 10, 2);
    memcpy(&region_count, payload + 32, 2);
    memcpy(&reserved, payload + 34, 2);
    offset = 36u + (uint32_t)region_count * 4u;
    if ((version != 2 && version != 3) || material_count == 0 || material_count > 40 ||
        region_count > VITAL_DAMAGE_REGION_MAX || reserved != 0 || indirect_index < 0 ||
        indirect_index >= material_count) return -1;
    material_stride = version == 3 ? 16u : 14u;
    if (length != (size_t)offset + (size_t)material_count * material_stride ||
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
    profile->region_count = region_count;
    for (index = 0; index < VITAL_DAMAGE_REGION_MAX; index++) {
        float threshold = 0.0f;
        if (index < region_count) {
            memcpy(&threshold, payload + 36 + index * 4u, 4);
            if (!finite_float(threshold) || threshold < 0.0f) return -1;
        }
        profile->region_damage_threshold[index] = threshold;
    }
    for (index = 0; index < material_count; index++) {
        int16_t type;
        record = payload + offset + index * material_stride;
        memcpy(&type, record, 2);
        memcpy(&shield_leak, record + (version == 3 ? 4 : 2), 4);
        memcpy(&shield_multiplier, record + (version == 3 ? 8 : 6), 4);
        memcpy(&body_multiplier, record + (version == 3 ? 12 : 10), 4);
        if (type < -1 || type >= COLL_RUNTIME_MATERIAL_TYPES ||
            !finite_float(shield_leak) || !finite_float(shield_multiplier) ||
            !finite_float(body_multiplier) || shield_leak < 0.0f || shield_leak > 1.0f ||
            shield_multiplier < 0.0f || body_multiplier < 0.0f) return -1;
        if (index == (uint32_t)indirect_index) body_type = type;
    }
    if (body_type < 0) return -1;
    record = payload + offset + (uint32_t)indirect_index * material_stride;
    memcpy(&shield_leak, record + (version == 3 ? 4 : 2), 4);
    memcpy(&shield_multiplier, record + (version == 3 ? 8 : 6), 4);
    memcpy(&body_multiplier, record + (version == 3 ? 12 : 10), 4);
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
        record = payload + offset + index * material_stride;
        memcpy(&profile->material[index].material_type, record, 2);
        if (version == 3) memcpy(&profile->material[index].flags, record + 2, 2);
        else profile->material[index].flags = 0;
        memcpy(&profile->material[index].shield_leak_fraction, record + (version == 3 ? 4 : 2), 4);
        memcpy(&profile->material[index].shield_damage_multiplier, record + (version == 3 ? 8 : 6), 4);
        memcpy(&profile->material[index].body_damage_multiplier, record + (version == 3 ? 12 : 10), 4);
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
