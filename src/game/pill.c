/* Structure-only collision_move_pill.
 * Sphere gather is collision_bsp_test_sphere. Features and the clip
 * loop are collision_features.c and collision_move_point. Objects are
 * not tested. Scratch is caller memory, capped at the source's 256
 * features and 128 BSP nodes. The tick does not allocate. */
#include "game/collide.h"
#include <math.h>
#include <string.h>

#define LONG_MIN_BIT 0x80000000u
#define NONE 0xFFFFFFFFu
#define EPS 0.0001f
#define QUERY_PAD 0.0625f

typedef struct { float n[3], d; } plane3;

typedef struct {
    int32_t object_index, surface_index;
    uint8_t flags, breakable;
    int16_t material;
    float c[3], radius;
} fsphere;

typedef struct {
    int32_t object_index, surface_index;
    uint8_t flags, breakable;
    int16_t material;
    float base[3], axis[3], width;
} fcyl;

typedef struct {
    int32_t object_index, surface_index;
    uint8_t flags, breakable;
    int16_t material;
    float n[3], d, height;
    int16_t proj;
    int8_t sign;
    int32_t npoints;
    float uv[8][2];
} fprism;

typedef struct {
    float t, point[3], n[3], d;
    int32_t surface;
    uint8_t flags;
} cplane;

typedef struct {
    int32_t surfaces[COLLIDE_PILL_FEATURES];
    int32_t edges[COLLIDE_PILL_FEATURES];
    int32_t vertices[COLLIDE_PILL_FEATURES];
    int surface_count, edge_count, vertex_count;
    int32_t plane_stack[COLLIDE_PILL_DEPTH];
    int stack_depth;
    int sc, cc, pc;
    fsphere spheres[COLLIDE_PILL_FEATURES];
    fcyl cylinders[COLLIDE_PILL_FEATURES];
    fprism prisms[COLLIDE_PILL_FEATURES];
} pill_scratch;

static const int k_map[3][2][2] = {
    {{2, 1}, {1, 2}},
    {{0, 2}, {2, 0}},
    {{1, 0}, {0, 1}},
};

static int32_t rdi(const uint8_t *p)
{
    int32_t v;
    memcpy(&v, p, 4);
    return v;
}

static void project(const float p[3], int axis, int sign, float o[2])
{
    o[0] = p[k_map[axis][sign][0]];
    o[1] = p[k_map[axis][sign][1]];
}

static float dot3(const float a[3], const float b[3])
{
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
}

static float len3(const float a[3])
{
    return sqrtf(dot3(a, a));
}

static void cross3(const float a[3], const float b[3], float o[3])
{
    o[0] = a[1] * b[2] - a[2] * b[1];
    o[1] = a[2] * b[0] - a[0] * b[2];
    o[2] = a[0] * b[1] - a[1] * b[0];
}

static float normalize3(float a[3])
{
    float L = len3(a);
    if (L > 0.0f) { a[0] /= L; a[1] /= L; a[2] /= L; }
    return L;
}

static void plane_of(const collide_bsp *bsp, uint32_t designator, plane3 *out)
{
    const float *p = bsp->planes + (size_t)(designator & 0x7FFFFFFFu) * 4;
    float s = (designator & LONG_MIN_BIT) ? -1.0f : 1.0f;
    out->n[0] = s * p[0];
    out->n[1] = s * p[1];
    out->n[2] = s * p[2];
    out->d = s * p[3];
}

static void add_id(int32_t *ids, int *count, int32_t id)
{
    int i;
    for (i = 0; i < *count; i++) if (ids[i] == id) return;
    if (*count < COLLIDE_PILL_FEATURES) ids[(*count)++] = id;
}

static int edge_hits_sphere(const float a[3], const float b[3], const float c[3], float radius)
{
    float p[3] = {a[0] - c[0], a[1] - c[1], a[2] - c[2]};
    float v[3] = {b[0] - a[0], b[1] - a[1], b[2] - a[2]};
    float cc = dot3(p, p) - radius * radius;
    float bb, aa, disc, neg;
    if (cc < 0.0f) return 1;
    bb = dot3(v, p);
    if (bb >= 0.0f) return 0;
    aa = dot3(v, v);
    disc = bb * bb - aa * cc;
    if (disc <= 0.0f) return 0;
    neg = -aa - bb;
    if (neg < 0.0f) return 1;
    return neg * neg < disc;
}

static void vert_at(const collide_bsp *bsp, int32_t index, float o[3])
{
    memcpy(o, bsp->vertices + (size_t)index * 16, 12);
}

typedef struct {
    const collide_bsp *bsp;
    pill_scratch *mem;
    const float *center;
    float radius;
    int axis, sign;
    float center2d[2];
    int *nodes;
    int *depth_limited;
} sphere_walk;

static void test_surface(sphere_walk *w, int32_t surface)
{
    const uint8_t *s = w->bsp->surfaces + (size_t)surface * 12;
    int32_t first = rdi(s + 4);
    int32_t edge = first;
    int hit = 0;
    float r2 = w->radius * w->radius;
    do {
        const uint8_t *e = w->bsp->edges + (size_t)edge * 24;
        int rev = rdi(e + 20) == surface;
        int32_t vi = rdi(e + (rev ? 4 : 0));
        float p[3];
        float dx, dy, dz;
        vert_at(w->bsp, vi, p);
        dx = p[0] - w->center[0];
        dy = p[1] - w->center[1];
        dz = p[2] - w->center[2];
        if (dx * dx + dy * dy + dz * dz <= r2)
            add_id(w->mem->vertices, &w->mem->vertex_count, vi), hit = 1;
        edge = rdi(e + (rev ? 12 : 8));
    } while (edge != first);
    edge = first;
    do {
        const uint8_t *e = w->bsp->edges + (size_t)edge * 24;
        int rev = rdi(e + 20) == surface;
        float a[3], b[3];
        vert_at(w->bsp, rdi(e + (rev ? 4 : 0)), a);
        vert_at(w->bsp, rdi(e + (rev ? 0 : 4)), b);
        if (edge_hits_sphere(a, b, w->center, w->radius))
            add_id(w->mem->edges, &w->mem->edge_count, edge), hit = 1;
        edge = rdi(e + (rev ? 12 : 8));
    } while (edge != first);
    if (!hit) {
        edge = first;
        do {
            const uint8_t *e = w->bsp->edges + (size_t)edge * 24;
            int rev = rdi(e + 20) == surface;
            float a[3], b[3], pa[2], pb[2];
            float v0x, v0y, v1x, v1y;
            vert_at(w->bsp, rdi(e + (rev ? 4 : 0)), a);
            vert_at(w->bsp, rdi(e + (rev ? 0 : 4)), b);
            project(a, w->axis, w->sign, pa);
            project(b, w->axis, w->sign, pb);
            v0x = pa[0] - w->center2d[0];
            v0y = pa[1] - w->center2d[1];
            v1x = pb[0] - w->center2d[0];
            v1y = pb[1] - w->center2d[1];
            if (v0x * v1y - v0y * v1x < 0.0f) return;
            edge = rdi(e + (rev ? 12 : 8));
        } while (edge != first);
    }
    add_id(w->mem->surfaces, &w->mem->surface_count, surface);
}

static void walk2d(sphere_walk *w, uint32_t node)
{
    while (!(node & LONG_MIN_BIT)) {
        const uint8_t *n = w->bsp->nodes2d + (size_t)node * 20;
        float nx, ny, d, dist;
        int32_t c0, c1;
        memcpy(&nx, n, 4);
        memcpy(&ny, n + 4, 4);
        memcpy(&d, n + 8, 4);
        c0 = rdi(n + 12);
        c1 = rdi(n + 16);
        dist = nx * w->center2d[0] + ny * w->center2d[1] - d;
        if (dist <= w->radius) walk2d(w, (uint32_t)c0);
        if (dist < -w->radius) return;
        node = (uint32_t)c1;
    }
    if (node != NONE) test_surface(w, (int32_t)(node & 0x7FFFFFFFu));
}

static void walk3d(sphere_walk *w, uint32_t node)
{
    while (!(node & LONG_MIN_BIT)) {
        uint32_t plane_i, back, front;
        const float *pl;
        float dist;
        int back_side, front_side;
        if (++(*w->nodes), w->mem->stack_depth >= COLLIDE_PILL_DEPTH) {
            *w->depth_limited = 1;
            return;
        }
        plane_i = w->bsp->nodes[(size_t)node * 3];
        back = w->bsp->nodes[(size_t)node * 3 + 1];
        front = w->bsp->nodes[(size_t)node * 3 + 2];
        pl = w->bsp->planes + (size_t)plane_i * 4;
        dist = pl[0] * w->center[0] + pl[1] * w->center[1] + pl[2] * w->center[2] - pl[3];
        back_side = dist < w->radius;
        front_side = dist > -w->radius;
        if (back_side && front_side) {
            w->mem->plane_stack[w->mem->stack_depth++] = (int32_t)(plane_i | LONG_MIN_BIT);
            walk3d(w, back);
            w->mem->stack_depth--;
            w->mem->plane_stack[w->mem->stack_depth++] = (int32_t)(plane_i & 0x7FFFFFFFu);
            walk3d(w, front);
            w->mem->stack_depth--;
            return;
        }
        node = front_side ? front : back;
    }
    if (node == NONE) return;
    {
        uint32_t leaf = node & 0x7FFFFFFFu;
        const uint8_t *lb = w->bsp->leaves + (size_t)leaf * 8;
        int32_t count = (int16_t)(lb[2] | (lb[3] << 8));
        int32_t first = rdi(lb + 4);
        int32_t r, s;
        for (r = first; r < first + count; r++) {
            uint32_t designator = w->bsp->refs[(size_t)r * 2];
            uint32_t root = w->bsp->refs[(size_t)r * 2 + 1];
            for (s = 0; s < w->mem->stack_depth; s++) {
                if ((uint32_t)w->mem->plane_stack[s] == designator) {
                    plane3 plane;
                    float pd, ax, ay, az;
                    float projected[3];
                    plane_of(w->bsp, designator, &plane);
                    pd = -(dot3(plane.n, w->center) - plane.d);
                    projected[0] = plane.n[0] * pd + w->center[0];
                    projected[1] = plane.n[1] * pd + w->center[1];
                    projected[2] = plane.n[2] * pd + w->center[2];
                    ax = fabsf(plane.n[0]);
                    ay = fabsf(plane.n[1]);
                    az = fabsf(plane.n[2]);
                    w->axis = (az >= ay && az >= ax) ? 2 : (ay >= ax ? 1 : 0);
                    w->sign = (plane.n[w->axis] > 0.0f) != ((designator & LONG_MIN_BIT) != 0);
                    project(projected, w->axis, w->sign, w->center2d);
                    walk2d(w, root);
                    break;
                }
            }
        }
    }
}

static void stamp_feature(int32_t *object, int32_t *surface, uint8_t *flags,
    uint8_t *breakable, int16_t *material, int32_t surf, const uint8_t *raw)
{
    uint32_t tail = 0;
    *object = -1;
    *surface = surf;
    memcpy(&tail, raw + 8, 4);
    *flags = (uint8_t)(tail & 0xFF);
    *breakable = (uint8_t)((tail >> 8) & 0xFF);
    *material = (int16_t)((tail >> 16) & 0xFFFF);
}

static void from_point(pill_scratch *m, const float p[3], float height, float width, int32_t surf, const uint8_t *raw)
{
    if (m->sc < COLLIDE_PILL_FEATURES) {
        fsphere *s = &m->spheres[m->sc++];
        stamp_feature(&s->object_index, &s->surface_index, &s->flags, &s->breakable, &s->material, surf, raw);
        memcpy(s->c, p, 12);
        s->radius = width;
    }
    if (height > 0.0f) {
        if (m->sc < COLLIDE_PILL_FEATURES) {
            fsphere *s = &m->spheres[m->sc++];
            stamp_feature(&s->object_index, &s->surface_index, &s->flags, &s->breakable, &s->material, surf, raw);
            s->c[0] = p[0]; s->c[1] = p[1]; s->c[2] = p[2] - height;
            s->radius = width;
        }
        if (m->cc < COLLIDE_PILL_FEATURES) {
            fcyl *c = &m->cylinders[m->cc++];
            stamp_feature(&c->object_index, &c->surface_index, &c->flags, &c->breakable, &c->material, surf, raw);
            c->base[0] = p[0]; c->base[1] = p[1]; c->base[2] = p[2] - height;
            c->axis[0] = c->axis[1] = 0.0f; c->axis[2] = height;
            c->width = width;
        }
    }
}

static void from_polygon(pill_scratch *m, int npoints, const float pts[][3], const plane3 *plane,
    float height, float width, int32_t surf, const uint8_t *raw)
{
    fprism *pr;
    int i, comp;
    if (m->pc >= COLLIDE_PILL_FEATURES || npoints > 8) return;
    pr = &m->prisms[m->pc++];
    stamp_feature(&pr->object_index, &pr->surface_index, &pr->flags, &pr->breakable, &pr->material, surf, raw);
    memcpy(pr->n, plane->n, 12);
    pr->d = plane->d;
    pr->height = width;
    pr->proj = (fabsf(plane->n[2]) >= fabsf(plane->n[1]) && fabsf(plane->n[2]) >= fabsf(plane->n[0])) ? 2 :
        (fabsf(plane->n[1]) >= fabsf(plane->n[0]) ? 1 : 0);
    pr->sign = plane->n[pr->proj] > 0.0f;
    pr->npoints = npoints;
    for (i = 0; i < npoints; i++) project(pts[i], pr->proj, pr->sign, pr->uv[i]);
    if (height > 0.0f && plane->n[2] < 0.0f) {
        pr->d -= height * pr->n[2];
        if (pr->proj != 2) {
            comp = k_map[pr->proj][pr->sign][1] == 2;
            for (i = 0; i < npoints; i++) pr->uv[i][comp] -= height;
        }
    }
}

static void build_features(const collide_bsp *bsp, pill_scratch *m, float height, float width)
{
    int i;
    m->sc = m->cc = m->pc = 0;
    for (i = 0; i < m->vertex_count; i++) {
        int32_t vi = m->vertices[i];
        float p[3];
        int32_t edge = rdi(bsp->vertices + (size_t)vi * 16 + 12);
        int32_t surf = rdi(bsp->edges + (size_t)edge * 24 + 16);
        const uint8_t *raw;
        if (surf < 0 || (uint32_t)surf >= bsp->surface_count) continue;
        raw = bsp->surfaces + (size_t)surf * 12;
        vert_at(bsp, vi, p);
        from_point(m, p, height, width, surf, raw);
    }
    for (i = 0; i < m->edge_count; i++) {
        const uint8_t *e = bsp->edges + (size_t)m->edges[i] * 24;
        int32_t s0 = rdi(e + 16), s1 = rdi(e + 20);
        plane3 p0, p1;
        float a[3], b[3], v[3];
        int valid;
        const uint8_t *raw;
        if (s0 < 0 || s1 < 0 || (uint32_t)s0 >= bsp->surface_count || (uint32_t)s1 >= bsp->surface_count) continue;
        if (rdi(bsp->surfaces + (size_t)s0 * 12) == rdi(bsp->surfaces + (size_t)s1 * 12)) continue;
        plane_of(bsp, (uint32_t)rdi(bsp->surfaces + (size_t)s0 * 12), &p0);
        plane_of(bsp, (uint32_t)rdi(bsp->surfaces + (size_t)s1 * 12), &p1);
        vert_at(bsp, rdi(e), a);
        vert_at(bsp, rdi(e + 4), b);
        v[0] = b[0] - a[0]; v[1] = b[1] - a[1]; v[2] = b[2] - a[2];
        {
            uint32_t d0 = (uint32_t)rdi(bsp->surfaces + (size_t)s0 * 12);
            uint32_t d1 = (uint32_t)rdi(bsp->surfaces + (size_t)s1 * 12);
            float cr[3], tp;
            int same = (d0 & LONG_MIN_BIT) == (d1 & LONG_MIN_BIT);
            cross3(p0.n, p1.n, cr);
            tp = dot3(cr, v);
            if ((d0 & 0x7FFFFFFFu) == (d1 & 0x7FFFFFFFu)) valid = 1;
            else if (same) valid = tp > -EPS;
            else valid = tp < EPS;
        }
        if (!valid) continue;
        raw = bsp->surfaces + (size_t)s0 * 12;
        if (m->cc < COLLIDE_PILL_FEATURES) {
            fcyl *c = &m->cylinders[m->cc++];
            stamp_feature(&c->object_index, &c->surface_index, &c->flags, &c->breakable, &c->material, s0, raw);
            memcpy(c->base, a, 12);
            memcpy(c->axis, v, 12);
            c->width = width;
        }
        if (height > 0.0f && m->cc < COLLIDE_PILL_FEATURES) {
            fcyl *c = &m->cylinders[m->cc++];
            stamp_feature(&c->object_index, &c->surface_index, &c->flags, &c->breakable, &c->material, s0, raw);
            c->base[0] = a[0]; c->base[1] = a[1]; c->base[2] = a[2] - height;
            memcpy(c->axis, v, 12);
            c->width = width;
        }
        {
            float n0 = -v[1], n1 = v[0], ln = sqrtf(n0 * n0 + n1 * n1);
            float pts[4][3];
            plane3 side;
            if (ln == 0.0f) continue;
            n0 /= ln; n1 /= ln;
            side.n[0] = n0; side.n[1] = n1; side.n[2] = 0.0f;
            side.d = n0 * a[0] + n1 * a[1];
            pts[0][0] = a[0]; pts[0][1] = a[1]; pts[0][2] = a[2];
            pts[1][0] = b[0]; pts[1][1] = b[1]; pts[1][2] = b[2];
            pts[2][0] = b[0]; pts[2][1] = b[1]; pts[2][2] = b[2] - height;
            pts[3][0] = a[0]; pts[3][1] = a[1]; pts[3][2] = a[2] - height;
            if (height > 0.0f) from_polygon(m, 4, pts, &side, 0.0f, width, s0, raw);
            side.n[0] = -n0; side.n[1] = -n1; side.d = -side.d;
            pts[1][2] = a[2] - height;
            pts[3][2] = b[2];
            /* swapped corners match the source's exchange of points 1 and 3 */
            {
                float t0 = pts[1][0], t1 = pts[1][1], t2 = pts[1][2];
                pts[1][0] = pts[3][0]; pts[1][1] = pts[3][1]; pts[1][2] = pts[3][2];
                pts[3][0] = t0; pts[3][1] = t1; pts[3][2] = t2;
            }
            if (height > 0.0f) from_polygon(m, 4, pts, &side, 0.0f, width, s0, raw);
        }
    }
    for (i = 0; i < m->surface_count; i++) {
        int32_t surf = m->surfaces[i];
        const uint8_t *raw = bsp->surfaces + (size_t)surf * 12;
        int32_t first = rdi(raw + 4), edge = first;
        float pts[8][3];
        int n = 0;
        plane3 plane;
        do {
            const uint8_t *e = bsp->edges + (size_t)edge * 24;
            int rev = rdi(e + 20) == surf;
            if (n < 8) vert_at(bsp, rdi(e + (rev ? 4 : 0)), pts[n]);
            n++;
            edge = rdi(e + (rev ? 12 : 8));
        } while (edge != first && n <= 8);
        if (n > 8) n = 8;
        plane_of(bsp, (uint32_t)rdi(raw), &plane);
        from_polygon(m, n, pts, &plane, height, width, surf, raw);
    }
}

static int sphere_vector(const fsphere *s, const float p[3], const float v[3], float *t, plane3 *plane)
{
    float w[3] = {s->c[0] - p[0], s->c[1] - p[1], s->c[2] - p[2]};
    float dist = dot3(w, w) - s->radius * s->radius;
    float proj, vs, disc;
    int hit = 0;
    if (dist <= 0.0f) { *t = 0.0f; hit = 1; }
    else {
        proj = dot3(w, v);
        if (proj > 0.0f) {
            vs = dot3(v, v);
            disc = proj * proj - vs * dist;
            if (disc >= 0.0f) {
                proj -= sqrtf(disc);
                if (proj <= vs && vs > 0.0f) { *t = proj / vs; hit = 1; }
            }
        }
    }
    if (!hit) return 0;
    plane->n[0] = v[0] * *t - w[0];
    plane->n[1] = v[1] * *t - w[1];
    plane->n[2] = v[2] * *t - w[2];
    if (normalize3(plane->n) == 0.0f) { plane->n[0] = plane->n[1] = 0.0f; plane->n[2] = 1.0f; }
    plane->d = s->c[0] * plane->n[0] + s->c[1] * plane->n[1] + s->c[2] * plane->n[2] + s->radius;
    return 1;
}

static int cyl_vector(const fcyl *c, const float p[3], const float v[3], float *t, plane3 *plane)
{
    float hs = dot3(c->axis, c->axis);
    float hv = dot3(c->axis, v);
    float vs = dot3(v, v);
    float a = hs * vs - hv * hv;
    float w[3], vw, hw, ws, b, cq, disc, inv, t0, t1, bot, top;
    if (a == 0.0f) return 0;
    w[0] = p[0] - c->base[0]; w[1] = p[1] - c->base[1]; w[2] = p[2] - c->base[2];
    vw = dot3(v, w);
    hw = dot3(c->axis, w);
    ws = dot3(w, w);
    b = hw * hv - hs * vw;
    cq = (ws - c->width * c->width) * hs - hw * hw;
    disc = b * b - a * cq;
    if (disc < 0.0f) return 0;
    disc = sqrtf(disc);
    inv = 1.0f / a;
    t0 = (b - disc) * inv;
    t1 = (b + disc) * inv;
    if (t0 > 1.0f || t1 < 0.0f) return 0;
    if (t0 < 0.0f) t0 = 0.0f;
    if (t1 > 1.0f) t1 = 1.0f;
    if (hv != 0.0f) {
        bot = -hw / hv;
        top = (hs - hw) / hv;
        if (hv > 0.0f) { if (t0 < bot) t0 = bot; if (t1 > top) t1 = top; }
        else { if (t0 < top) t0 = top; if (t1 > bot) t1 = bot; }
        if (t0 > t1) return 0;
    } else if (hw < 0.0f || hw > hs) return 0;
    *t = t0;
    {
        float on[3] = {w[0] + v[0] * t0, w[1] + v[1] * t0, w[2] + v[2] * t0};
        float ht = hs > 0.0f ? -(dot3(on, c->axis) / hs) : 0.0f;
        plane->n[0] = on[0] + c->axis[0] * ht;
        plane->n[1] = on[1] + c->axis[1] * ht;
        plane->n[2] = on[2] + c->axis[2] * ht;
    }
    if (normalize3(plane->n) == 0.0f) { plane->n[0] = 1.0f; plane->n[1] = plane->n[2] = 0.0f; }
    plane->d = c->base[0] * plane->n[0] + c->base[1] * plane->n[1] + c->base[2] * plane->n[2] + c->width;
    return 1;
}

static int prism_vector(const fprism *pr, const float p[3], const float v[3], float *t, plane3 *plane)
{
    float t_out = 0.0f, t_in = 1.0f;
    float d = pr->n[0] * p[0] + pr->n[1] * p[1] + pr->n[2] * p[2] - pr->d;
    float vn = pr->n[0] * v[0] + pr->n[1] * v[1] + pr->n[2] * v[2];
    float p3[3], v3[3], p2[2], v2[2];
    int i;
    if (vn != 0.0f) {
        float o = 1.0f / vn;
        float t0 = -o * d, t1 = -o * (d - pr->height);
        if (vn > 0.0f) { if (t_out < t0) t_out = t0; if (t_in > t1) t_in = t1; }
        else { if (t_out < t1) t_out = t1; if (t_in > t0) t_in = t0; }
        if (t_out > t_in) return 0;
    } else if (d < 0.0f || d >= pr->height) return 0;
    p3[0] = p[0] - pr->n[0] * d; p3[1] = p[1] - pr->n[1] * d; p3[2] = p[2] - pr->n[2] * d;
    v3[0] = v[0] - pr->n[0] * vn; v3[1] = v[1] - pr->n[1] * vn; v3[2] = v[2] - pr->n[2] * vn;
    project(p3, pr->proj, pr->sign, p2);
    project(v3, pr->proj, pr->sign, v2);
    for (i = 0; i < pr->npoints; i++) {
        int n = i + 1 < pr->npoints ? i + 1 : 0;
        float wx = pr->uv[n][0] - pr->uv[i][0];
        float wy = pr->uv[n][1] - pr->uv[i][1];
        float xx = p2[0] - pr->uv[i][0];
        float xy = p2[1] - pr->uv[i][1];
        float vw = v2[0] * wy - v2[1] * wx;
        float wxc = wx * xy - wy * xx;
        if (vw != 0.0f) {
            float te = wxc / vw;
            if (vw < 0.0f) { if (t_out < te) t_out = te; }
            else if (t_in > te) t_in = te;
            if (t_out > t_in) return 0;
        } else if (wxc < 0.0f) return 0;
    }
    *t = t_out;
    memcpy(plane->n, pr->n, 12);
    plane->d = pr->d + pr->height;
    return 1;
}

static int closest_feature(const pill_scratch *m, const float p[3], const float v[3], cplane *hit)
{
    float best = 1.0e30f;
    int found = 0, i;
    plane3 plane;
    float t;
    for (i = 0; i < m->sc; i++) {
        if (sphere_vector(&m->spheres[i], p, v, &t, &plane) && t < best && dot3(v, plane.n) < -EPS) {
            best = t; found = 1;
            hit->surface = m->spheres[i].surface_index;
            hit->flags = m->spheres[i].flags;
            memcpy(hit->n, plane.n, 12); hit->d = plane.d;
        }
    }
    for (i = 0; i < m->cc; i++) {
        if (cyl_vector(&m->cylinders[i], p, v, &t, &plane) && t < best && dot3(v, plane.n) < -EPS) {
            best = t; found = 1;
            hit->surface = m->cylinders[i].surface_index;
            hit->flags = m->cylinders[i].flags;
            memcpy(hit->n, plane.n, 12); hit->d = plane.d;
        }
    }
    for (i = 0; i < m->pc; i++) {
        if (dot3(v, m->prisms[i].n) < -EPS && prism_vector(&m->prisms[i], p, v, &t, &plane) && t < best) {
            best = t; found = 1;
            hit->surface = m->prisms[i].surface_index;
            hit->flags = m->prisms[i].flags;
            memcpy(hit->n, plane.n, 12); hit->d = plane.d;
        }
    }
    if (!found) {
        hit->t = 1.0f;
        hit->point[0] = p[0] + v[0];
        hit->point[1] = p[1] + v[1];
        hit->point[2] = p[2] + v[2];
        return 0;
    }
    hit->t = best;
    hit->point[0] = p[0] + v[0] * best;
    hit->point[1] = p[1] + v[1] * best;
    hit->point[2] = p[2] + v[2] * best;
    return 1;
}

static void clip_pos_plane(const float p[3], const plane3 *plane, float o[3])
{
    float dist = dot3(plane->n, p) - plane->d;
    o[0] = p[0] - plane->n[0] * dist;
    o[1] = p[1] - plane->n[1] * dist;
    o[2] = p[2] - plane->n[2] * dist;
}

static void clip_vel_plane(const float v[3], const plane3 *plane, float o[3])
{
    float dist = -dot3(v, plane->n);
    o[0] = plane->n[0] * dist + v[0];
    o[1] = plane->n[1] * dist + v[1];
    o[2] = plane->n[2] * dist + v[2];
}

static int line_from_planes(const plane3 *a, const plane3 *b, float point[3], float dir[3])
{
    float local[3], det, dist;
    cross3(a->n, b->n, dir);
    det = dot3(dir, dir);
    if (fabsf(det) < EPS) return 0;
    cross3(b->n, dir, local);
    point[0] = local[0] * a->d; point[1] = local[1] * a->d; point[2] = local[2] * a->d;
    cross3(dir, a->n, local);
    dist = b->d;
    point[0] = (local[0] * dist + point[0]) / det;
    point[1] = (local[1] * dist + point[1]) / det;
    point[2] = (local[2] * dist + point[2]) / det;
    return 1;
}

static int move_point(const pill_scratch *mem, const float pos[3], const float vel[3],
    float out_pos[3], float out_vel[3], cplane *hits, int *nhits)
{
    float position[3], velocity[3], clipped_p[3], clipped_v[3];
    int clip_count = 0, clip_index[3], count = 0;
    plane3 clip_plane;
    float line_p[3], line_v[3];
    memcpy(position, pos, 12);
    memcpy(velocity, vel, 12);
    memcpy(clipped_p, pos, 12);
    memcpy(clipped_v, vel, 12);
    while (fabsf(clipped_v[0]) >= EPS || fabsf(clipped_v[1]) >= EPS || fabsf(clipped_v[2]) >= EPS) {
        cplane hit;
        if (count >= 16) break;
        if (!closest_feature(mem, clipped_p, clipped_v, &hit)) {
            memcpy(clipped_p, hit.point, 12);
            break;
        }
        hits[count++] = hit;
        velocity[0] *= 1.0f - hit.t;
        velocity[1] *= 1.0f - hit.t;
        velocity[2] *= 1.0f - hit.t;
        memcpy(position, hit.point, 12);
        {
            plane3 hp;
            int new_count = 1, new_index[3];
            memcpy(hp.n, hit.n, 12); hp.d = hit.d;
            new_index[0] = count - 1;
            clip_plane = hp;
            clip_vel_plane(velocity, &clip_plane, clipped_v);
            clip_pos_plane(position, &clip_plane, clipped_p);
            if (clip_count > 0 && dot3(clipped_v, hits[clip_index[0]].n) < -EPS &&
                line_from_planes(&hp, (plane3 *)&hits[clip_index[0]].n, line_p, line_v)) {
                float along, mag;
                new_count = 2;
                new_index[1] = clip_index[0];
                mag = dot3(line_v, line_v);
                along = mag > 0.0f ? dot3(velocity, line_v) / mag : 0.0f;
                clipped_v[0] = line_v[0] * along;
                clipped_v[1] = line_v[1] * along;
                clipped_v[2] = line_v[2] * along;
                {
                    float off[3] = {position[0] - line_p[0], position[1] - line_p[1], position[2] - line_p[2]};
                    float u = mag > 0.0f ? dot3(off, line_v) / mag : 0.0f;
                    clipped_p[0] = line_p[0] + line_v[0] * u;
                    clipped_p[1] = line_p[1] + line_v[1] * u;
                    clipped_p[2] = line_p[2] + line_v[2] * u;
                }
            }
            clip_count = new_count;
            memcpy(clip_index, new_index, sizeof clip_index);
        }
        if (count >= 16) break;
    }
    memcpy(out_pos, clipped_p, 12);
    if (clip_count == 0) memcpy(out_vel, vel, 12);
    else if (clip_count == 1) clip_vel_plane(vel, &clip_plane, out_vel);
    else {
        float mag = dot3(line_v, line_v);
        float along = mag > 0.0f ? dot3(vel, line_v) / mag : 0.0f;
        out_vel[0] = line_v[0] * along;
        out_vel[1] = line_v[1] * along;
        out_vel[2] = line_v[2] * along;
    }
    *nhits = count;
    return count;
}

size_t collide_pill_scratch_bytes(void)
{
    return sizeof(pill_scratch);
}

int collide_point_empty(const collide_bsp *bsp, const float point[3])
{
    uint32_t node = 0;
    uint32_t step;
    if (bsp->node_count == 0) return 0;
    for (step = 0; step < bsp->node_count; step++) {
        uint32_t plane_i, back, front;
        const float *pl;
        float dist;
        if (node & LONG_MIN_BIT) return node != NONE;
        plane_i = bsp->nodes[(size_t)node * 3];
        back = bsp->nodes[(size_t)node * 3 + 1];
        front = bsp->nodes[(size_t)node * 3 + 2];
        pl = bsp->planes + (size_t)plane_i * 4;
        dist = pl[0] * point[0] + pl[1] * point[1] + pl[2] * point[2] - pl[3];
        node = dist >= 0.0f ? front : back;
    }
    return 0;
}

static int collide_move_once(
    const collide_bsp *bsp,
    const float position[3],
    const float velocity[3],
    float height,
    float radius,
    float minimum_normal_k,
    pill_scratch *mem,
    collide_pill_out *out,
    collide_pill_stats *stats,
    int *saturated)
{
    float speed, center[3], reach;
    sphere_walk walk;
    cplane hits[16];
    int nhits = 0, i, best = -1;
    float best_k = -1.0e30f;
    memset(mem, 0, sizeof *mem);
    speed = len3(velocity);
    center[0] = position[0] + velocity[0] * 0.5f;
    center[1] = position[1] + velocity[1] * 0.5f;
    center[2] = position[2] + velocity[2] * 0.5f + height * 0.5f;
    reach = speed * 0.5f + height * 0.5f + radius + QUERY_PAD;
    {
        int nodes_local = 0, limited_local = 0;
        walk.bsp = bsp;
        walk.mem = mem;
        walk.center = center;
        walk.radius = reach;
        walk.nodes = &nodes_local;
        walk.depth_limited = &limited_local;
        walk3d(&walk, 0);
        if (stats) {
            stats->nodes_visited += nodes_local;
            stats->depth_limited |= limited_local;
        }
    }
    build_features(bsp, mem, height, radius);
    *saturated = mem->sc == COLLIDE_PILL_FEATURES || mem->cc == COLLIDE_PILL_FEATURES ||
        mem->pc == COLLIDE_PILL_FEATURES;
    if (stats) {
        int nfeat = mem->sc + mem->cc + mem->pc;
        if (nfeat > stats->features) stats->features = nfeat;
        stats->saturated |= *saturated;
        stats->sweeps++;
    }
    if (mem->sc + mem->cc + mem->pc == 0) {
        out->pos[0] = position[0] + velocity[0];
        out->pos[1] = position[1] + velocity[1];
        out->pos[2] = position[2] + velocity[2];
        memcpy(out->vel, velocity, 12);
        out->collisions = 0;
        out->grounded = 0;
        out->surface = -1;
        out->normal[0] = out->normal[1] = 0.0f;
        out->normal[2] = 1.0f;
        out->normal[3] = 0.0f;
        return 0;
    }
    move_point(mem, position, velocity, out->pos, out->vel, hits, &nhits);
    out->collisions = nhits;
    for (i = 0; i < nhits; i++) {
        if (hits[i].n[2] > best_k) { best_k = hits[i].n[2]; best = i; }
    }
    if (best >= 0 && best_k >= minimum_normal_k) {
        out->grounded = 1;
        out->surface = hits[best].surface;
        memcpy(out->normal, hits[best].n, 12);
        out->normal[3] = hits[best].d;
    } else {
        out->grounded = 0;
        out->surface = -1;
        out->normal[0] = out->normal[1] = 0.0f;
        out->normal[2] = 1.0f;
        out->normal[3] = 0.0f;
    }
    return 0;
}

static int collide_move_fit(
    const collide_bsp *bsp,
    const float position[3],
    const float velocity[3],
    float height,
    float radius,
    float minimum_normal_k,
    void *scratch,
    collide_pill_out *out,
    collide_pill_stats *stats)
{
    int saturated = 0;
    float span;
    if (collide_move_once(bsp, position, velocity, height, radius, minimum_normal_k,
            scratch, out, stats, &saturated) != 0)
        return -1;
    span = len3(velocity);
    if (!saturated) return 0;
    /* A full 256-feature list can omit a closer wall, so the step is
     * halved. The features that did fit still block: a finer sweep
     * must not travel farther than that contact. */
    if (span > 0.05f) {
        float half[3] = {velocity[0] * 0.5f, velocity[1] * 0.5f, velocity[2] * 0.5f};
        collide_pill_out kept = *out, mid, finer;
        float kept_dx = kept.pos[0] - position[0];
        float kept_dy = kept.pos[1] - position[1];
        float kept_dz = kept.pos[2] - position[2];
        float kept_d = sqrtf(kept_dx * kept_dx + kept_dy * kept_dy + kept_dz * kept_dz);
        if (collide_move_fit(bsp, position, half, height, radius, minimum_normal_k,
                scratch, &mid, stats) != 0)
            return -1;
        if (collide_move_fit(bsp, mid.pos, mid.vel, height, radius, minimum_normal_k,
                scratch, &finer, stats) != 0)
            return -1;
        {
            float dx = finer.pos[0] - position[0];
            float dy = finer.pos[1] - position[1];
            float dz = finer.pos[2] - position[2];
            if (sqrtf(dx * dx + dy * dy + dz * dz) > kept_d + 0.02f) *out = kept;
            else *out = finer;
        }
        return 0;
    }
    out->pos[0] = position[0];
    out->pos[1] = position[1];
    out->pos[2] = position[2];
    out->vel[0] = out->vel[1] = out->vel[2] = 0.0f;
    out->grounded = 0;
    return 0;
}

int collide_move_pill(
    const collide_bsp *bsp,
    const float position[3],
    const float velocity[3],
    float height,
    float radius,
    float minimum_normal_k,
    void *scratch,
    size_t scratch_bytes,
    collide_pill_out *out,
    collide_pill_stats *stats)
{
    if (scratch_bytes < sizeof(pill_scratch) || scratch == NULL) return -1;
    if (stats) memset(stats, 0, sizeof *stats);
    return collide_move_fit(bsp, position, velocity, height, radius, minimum_normal_k,
        scratch, out, stats);
}
