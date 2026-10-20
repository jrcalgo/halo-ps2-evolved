#include "game/collide.h"
#include <stddef.h>
#include <string.h>

#define LONG_MIN_BIT 0x80000000u
#define NONE 0xFFFFFFFFu

enum { CONTENTS_UNKNOWN, CONTENTS_EMPTY, CONTENTS_SEMI, CONTENTS_SOLID };

int16_t collide_material_type(const collide_bsp *bsp, int16_t material_index)
{
    int16_t material_type;
    if (!bsp || !bsp->material_types || material_index < 0 ||
        (uint32_t)material_index >= bsp->material_count)
        return -1;
    memcpy(&material_type, bsp->material_types + material_index, sizeof material_type);
    if (material_type < -1 || material_type >= 26) return -1;
    return material_type;
}

static const int k_map[3][2][2] = {
    {{2, 1}, {1, 2}},
    {{0, 2}, {2, 0}},
    {{1, 0}, {0, 1}},
};

static int32_t rd_i32(const uint8_t *p)
{
    int32_t v;
    memcpy(&v, p, 4);
    return v;
}

static uint16_t rd_u16(const uint8_t *p)
{
    uint16_t v;
    memcpy(&v, p, 2);
    return v;
}

static int16_t rd_i16(const uint8_t *p)
{
    int16_t v;
    memcpy(&v, p, 2);
    return v;
}

static void project(const float p[3], int axis, int sign, float out[2])
{
    out[0] = p[k_map[axis][sign][0]];
    out[1] = p[k_map[axis][sign][1]];
}

static int surface_contains(
    const collide_bsp *bsp, int32_t surface, int axis, int sign, const float point[2])
{
    const uint8_t *s = bsp->surfaces + (size_t)surface * 12;
    int32_t first = rd_i32(s + 4);
    int32_t edge = first;
    do {
        const uint8_t *e = bsp->edges + (size_t)edge * 24;
        int32_t v_i[2] = {rd_i32(e), rd_i32(e + 4)};
        int32_t e_i[2] = {rd_i32(e + 8), rd_i32(e + 12)};
        int32_t s_i[2] = {rd_i32(e + 16), rd_i32(e + 20)};
        int rev = s_i[1] == surface;
        float a[3], b[3], pa[2], pb[2];
        float vx, vy, ex, ey;
        memcpy(a, bsp->vertices + (size_t)v_i[rev] * 16, 12);
        memcpy(b, bsp->vertices + (size_t)v_i[!rev] * 16, 12);
        project(a, axis, sign, pa);
        project(b, axis, sign, pb);
        vx = point[0] - pa[0];
        vy = point[1] - pa[1];
        ex = pb[0] - pa[0];
        ey = pb[1] - pa[1];
        if (vx * ey - vy * ex > 0.0f) return 0;
        edge = e_i[rev];
    } while (edge != first);
    return 1;
}

static int32_t test2d(const collide_bsp *bsp, const float point[2], uint32_t node)
{
    while (!(node & LONG_MIN_BIT)) {
        const uint8_t *n = bsp->nodes2d + (size_t)node * 20;
        float nx, ny, d, dist;
        memcpy(&nx, n, 4);
        memcpy(&ny, n + 4, 4);
        memcpy(&d, n + 8, 4);
        dist = nx * point[0] + ny * point[1] - d;
        node = (uint32_t)rd_i32(n + (dist >= 0.0f ? 16 : 12));
    }
    return node != NONE ? (int32_t)(node & 0x7FFFFFFFu) : -1;
}

static int32_t leaf_surface(
    const collide_bsp *bsp,
    int32_t leaf,
    int32_t plane_index,
    const float point[3],
    const float vector[3],
    float t,
    int test_surface)
{
    const uint8_t *leaf_b = bsp->leaves + (size_t)leaf * 8;
    int16_t count = rd_i16(leaf_b + 2);
    int32_t first = rd_i32(leaf_b + 4);
    int32_t r;
    for (r = first; r < first + count; r++) {
        uint32_t designator = bsp->refs[(size_t)r * 2];
        uint32_t root = bsp->refs[(size_t)r * 2 + 1];
        if ((designator & 0x7FFFFFFFu) == (uint32_t)plane_index) {
            const float *pl = bsp->planes + (size_t)plane_index * 4;
            float ax = pl[0] < 0 ? -pl[0] : pl[0];
            float ay = pl[1] < 0 ? -pl[1] : pl[1];
            float az = pl[2] < 0 ? -pl[2] : pl[2];
            int axis = (az >= ay && az >= ax) ? 2 : (ay >= ax ? 1 : 0);
            int positive = pl[axis] > 0.0f;
            int flipped = (designator & LONG_MIN_BIT) != 0;
            int sign = positive != flipped;
            float hit[3] = {
                point[0] + vector[0] * t,
                point[1] + vector[1] * t,
                point[2] + vector[2] * t,
            };
            float p2[2];
            int32_t surface;
            project(hit, axis, sign, p2);
            surface = test2d(bsp, p2, root);
            if (surface < 0) return -1;
            if (!test_surface || surface_contains(bsp, surface, axis, sign, p2))
                return surface;
            return -1;
        }
    }
    return -1;
}

typedef struct {
    const collide_bsp *bsp;
    const float *point;
    const float *vector;
    unsigned flags;
    collide_hit *hit;
    uint32_t last_leaf;
    int32_t last_plane;
    int last_contents;
} walk;

static int walk_node(walk *w, uint32_t node, float t0, float t1);

static int accept_surface(walk *w, int32_t surface, float t)
{
    const uint8_t *s = w->bsp->surfaces + (size_t)surface * 12;
    uint32_t tail = 0;
    memcpy(&tail, s + 8, 4);
    {
        unsigned surf_flags = tail & 0xFFu;
        if ((surf_flags & 2u) && (w->flags & COLLIDE_IGNORE_INVISIBLE)) return 0;
        if ((surf_flags & 8u) && (w->flags & COLLIDE_IGNORE_BREAKABLE)) return 0;
    }
    w->hit->t = t;
    w->hit->surface = surface;
    w->hit->plane = w->last_plane;
    return 1;
}

static int walk_node(walk *w, uint32_t node, float t0, float t1)
{
    if (!(node & LONG_MIN_BIT)) {
        uint32_t plane_i = w->bsp->nodes[(size_t)node * 3];
        uint32_t back = w->bsp->nodes[(size_t)node * 3 + 1];
        uint32_t front = w->bsp->nodes[(size_t)node * 3 + 2];
        const float *pl = w->bsp->planes + (size_t)plane_i * 4;
        float dist = pl[0] * w->point[0] + pl[1] * w->point[1] + pl[2] * w->point[2] - pl[3];
        float dot = pl[0] * w->vector[0] + pl[1] * w->vector[1] + pl[2] * w->vector[2];
        float d0 = dot * t0 + dist;
        float d1 = dot * t1 + dist;
        int reaches_back = d0 < 0.0f || d1 < 0.0f;
        int reaches_front = d0 >= 0.0f || d1 >= 0.0f;
        uint32_t child[2] = {back, front};
        if (reaches_back && reaches_front) {
            int front_side = dot > 0.0f;
            float t = -(dist / dot);
            if (walk_node(w, child[!front_side], t0, t)) return 1;
            if (w->hit->t <= t) return 0;
            w->last_plane = (int32_t)plane_i;
            if (walk_node(w, child[front_side], t, t1)) return 1;
        } else if (walk_node(w, child[reaches_front], t0, t1)) {
            return 1;
        }
        return 0;
    }

    {
        uint32_t leaf = NONE;
        int contents = CONTENTS_SOLID;
        int test_surface = 0;
        uint32_t test_leaf = NONE;
        if (node != NONE) {
            uint16_t flags;
            leaf = node & 0x7FFFFFFFu;
            flags = rd_u16(w->bsp->leaves + (size_t)leaf * 8);
            contents = (flags & 1u) ? CONTENTS_SEMI : CONTENTS_EMPTY;
        }
        if ((w->flags & COLLIDE_FRONT) &&
            (w->last_contents == CONTENTS_EMPTY || w->last_contents == CONTENTS_SEMI) &&
            contents == CONTENTS_SOLID) {
            test_leaf = w->last_leaf;
        } else if ((w->flags & COLLIDE_BACK) &&
            w->last_contents == CONTENTS_SOLID &&
            (contents == CONTENTS_EMPTY || contents == CONTENTS_SEMI)) {
            test_leaf = leaf;
        } else if (!(w->flags & COLLIDE_IGNORE_TWO_SIDED) &&
            w->last_contents == CONTENTS_SEMI && contents == CONTENTS_SEMI) {
            test_leaf = (w->flags & COLLIDE_FRONT) ? w->last_leaf : leaf;
            test_surface = 1;
        }
        if (test_leaf != NONE) {
            int32_t surface = leaf_surface(
                w->bsp, (int32_t)test_leaf, w->last_plane, w->point, w->vector, t0, test_surface);
            if (surface >= 0 && accept_surface(w, surface, t0)) return 1;
        }
        w->last_leaf = leaf;
        w->last_contents = contents;
    }
    return 0;
}

int collide_test_vector(
    const collide_bsp *bsp,
    const float point[3],
    const float vector[3],
    float maximum_t,
    unsigned flags,
    collide_hit *hit)
{
    walk w;
    float t1;
    w.bsp = bsp;
    w.point = point;
    w.vector = vector;
    w.flags = flags;
    w.hit = hit;
    w.last_leaf = NONE;
    w.last_plane = -1;
    w.last_contents = CONTENTS_UNKNOWN;
    hit->t = maximum_t < 0.0f ? 0.0f : maximum_t;
    hit->surface = -1;
    hit->plane = -1;
    t1 = maximum_t < 0.0f ? 0.0f : (maximum_t > 1.0f ? 1.0f : maximum_t);
    return walk_node(&w, 0, 0.0f, t1);
}

int collide_location_underwater(const collide_bsp *bsp,
    const collide_location_view *location, const float point[3])
{
    uint32_t node = 0, step, leaf, cluster, encoded;
    int32_t fog_region = -1;
    float plane_distance = 0.0f;
    int has_plane = 0;
    if (!bsp || !location || !point || !bsp->nodes || !bsp->planes ||
        !location->leaf_clusters || !location->cluster_fog || bsp->node_count == 0)
        return 0;
    for (step = 0; step < bsp->node_count; step++) {
        uint32_t plane_index;
        const float *plane;
        float distance;
        if (node & LONG_MIN_BIT) break;
        if (node >= bsp->node_count) return 0;
        plane_index = bsp->nodes[(size_t)node * 3];
        if (plane_index >= bsp->plane_count) return 0;
        plane = bsp->planes + (size_t)plane_index * 4;
        distance = plane[0] * point[0] + plane[1] * point[1] +
                   plane[2] * point[2] - plane[3];
        node = bsp->nodes[(size_t)node * 3 + (distance >= 0.0f ? 2 : 1)];
    }
    if (!(node & LONG_MIN_BIT) || node == NONE) return 0;
    leaf = node & 0x7FFFFFFFu;
    if (leaf >= location->leaf_count) return 0;
    cluster = (uint16_t)rd_i16(location->leaf_clusters + (size_t)leaf * 2);
    if ((int16_t)cluster < 0 || cluster >= location->cluster_count) return 0;
    encoded = (uint16_t)rd_i16(location->cluster_fog + (size_t)cluster * 2);
    if (encoded == 0xFFFFu) return 0;
    if (encoded & 0x8000u) {
        uint32_t plane_index = encoded & 0x7FFFu;
        const uint8_t *fog_plane;
        float equation[4];
        float fog_distance = 0.0f;
        if (plane_index >= location->fog_plane_count) return 0;
        fog_plane = location->fog_planes + (size_t)plane_index * 18;
        fog_region = rd_i16(fog_plane);
        memcpy(equation, fog_plane + 2, sizeof equation);
        if (fog_region < 0 || (uint32_t)fog_region >= location->fog_region_count) return 0;
        if (location->fog_regions[(size_t)fog_region * 8] & 1u) {
            memcpy(&fog_distance, location->fog_regions + (size_t)fog_region * 8 + 4, 4);
            plane_distance = equation[0] * point[0] + equation[1] * point[1] +
                             equation[2] * point[2] - equation[3] + fog_distance;
            has_plane = 1;
        }
    } else {
        fog_region = (int32_t)(encoded & 0x7FFFu);
        if ((uint32_t)fog_region >= location->fog_region_count) return 0;
    }
    if (fog_region < 0 || !(location->fog_regions[(size_t)fog_region * 8] & 1u)) return 0;
    return !has_plane || plane_distance < 0.0f;
}
