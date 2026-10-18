/* Blood Gulch player step. The fixture is tests/test_collide.py's
 * collision BSP. Scratch is one buffer for every tick. */
#include "game/collpack.h"
#include "game/move.h"
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

static uint8_t *slurp(const char *path, size_t *size)
{
    FILE *f = fopen(path, "rb");
    long n;
    uint8_t *bytes;
    if (!f) exit(1);
    fseek(f, 0, SEEK_END);
    n = ftell(f);
    fseek(f, 0, SEEK_SET);
    bytes = malloc((size_t)n);
    if (!bytes || fread(bytes, 1, (size_t)n, f) != (size_t)n) exit(1);
    fclose(f);
    *size = (size_t)n;
    return bytes;
}

static void load_pack(const char *path, collide_bsp *bsp, float spawn[4], float tags[COLL_TAG_FLOATS])
{
    size_t pack_size, coll_size, tag_size;
    const uint8_t *coll, *tag;
    uint8_t *pack = slurp(path, &pack_size);
    if (collpack_section(pack, pack_size, "COLL", &coll, &coll_size) != 0) exit(1);
    if (collpack_section(pack, pack_size, "TAGS", &tag, &tag_size) != 0) exit(1);
    if (collpack_collision(coll, coll_size, bsp) != 0) exit(1);
    if (collpack_spawn(coll, 0, spawn) != 0) exit(1);
    if (collpack_tags(tag, tag_size, tags) != 0) exit(1);
    printf("tables %u\n", (unsigned)(coll_size - 36 - collpack_spawn_count(coll) * 16));
    printf("spawns %u\n", collpack_spawn_count(coll));
}

static void copy_mover(mover *d, const mover *s) { *d = *s; }

static void surface_plane(const collide_bsp *bsp, uint32_t surface, float n[4])
{
    uint32_t designator;
    const float *plane;
    float sign;
    memcpy(&designator, bsp->surfaces + (size_t)surface * 12, 4);
    plane = bsp->planes + (size_t)(designator & 0x7fffffffu) * 4;
    sign = (designator & 0x80000000u) ? -1.0f : 1.0f;
    n[0] = sign * plane[0];
    n[1] = sign * plane[1];
    n[2] = sign * plane[2];
    n[3] = sign * plane[3];
}

static int surface_centroid(const collide_bsp *bsp, uint32_t surface, float out[3])
{
    const uint8_t *raw = bsp->surfaces + (size_t)surface * 12;
    int32_t first, edge, count = 0;
    memcpy(&first, raw + 4, 4);
    edge = first;
    out[0] = out[1] = out[2] = 0.0f;
    do {
        const uint8_t *e = bsp->edges + (size_t)edge * 24;
        int32_t side, vertex, next;
        float p[3];
        memcpy(&side, e + 20, 4);
        memcpy(&vertex, e + (side == (int32_t)surface ? 4 : 0), 4);
        memcpy(p, bsp->vertices + (size_t)vertex * 16, 12);
        out[0] += p[0];
        out[1] += p[1];
        out[2] += p[2];
        memcpy(&next, e + (side == (int32_t)surface ? 12 : 8), 4);
        edge = next;
        if (++count > 8) return 0;
    } while (edge != first);
    if (count < 3) return 0;
    out[0] /= (float)count;
    out[1] /= (float)count;
    out[2] /= (float)count;
    return 1;
}

static void geometry_cases(const collide_bsp *bsp, void *scratch, size_t bytes, const float spawn[4])
{
    collide_pill_stats stats;
    move_cmd idle = {0}, walk = {1, 0, 0, 0};
    uint32_t surface;
    int slope = 0, ceiling = 0, corner = 0;
    for (surface = 0; surface < bsp->surface_count && !slope; surface++) {
        float n[4], c[3], origin[3], down[3] = {0, 0, -2}, feet[3];
        collide_hit hit;
        mover body;
        float yaw, pitch, z0;
        int tick, grounded = 0;
        surface_plane(bsp, surface, n);
        if (n[2] < 0.80f || n[2] > 0.94f) continue;
        if (!surface_centroid(bsp, surface, c)) continue;
        origin[0] = c[0];
        origin[1] = c[1];
        origin[2] = c[2] + 1.0f;
        if (!collide_test_vector(bsp, origin, down, 1.0f, COLLIDE_FRONT, &hit)) continue;
        feet[0] = c[0];
        feet[1] = c[1];
        feet[2] = origin[2] + down[2] * hit.t + 0.05f;
        if (fabsf(feet[2] - c[2]) > 0.35f) continue;
        mover_init(&body, feet);
        for (tick = 0; tick < 20; tick++)
            mover_tick_map(&body, &idle, 0, bsp, scratch, bytes, 0, &stats);
        if (!body.grounded || body.ground[2] < 0.75f || body.ground[2] > 0.97f) continue;
        z0 = body.pos[2];
        yaw = atan2f(-body.ground[1], -body.ground[0]);
        for (tick = 0; tick < 30; tick++) {
            mover_tick_map(&body, &walk, yaw, bsp, scratch, bytes, 1, &stats);
            grounded += body.grounded;
        }
        printf("slope rise %.4f grounded_ticks %d normal %.3f\n",
            body.pos[2] - z0, grounded, body.ground[2]);
        (void)pitch;
        slope = body.pos[2] > z0 + 0.02f && grounded >= 20;
    }
    printf("slope_found %d\n", slope);
    for (surface = 0; surface < bsp->surface_count && !ceiling; surface++) {
        float n[4], c[3], origin[3], down[3] = {0, 0, -3};
        collide_hit hit;
        float gap, ceiling_z, head;
        mover body;
        move_cmd hop = {0};
        int tick;
        surface_plane(bsp, surface, n);
        if (n[2] > -0.7f) continue;
        if (!surface_centroid(bsp, surface, c)) continue;
        origin[0] = c[0];
        origin[1] = c[1];
        origin[2] = c[2];
        if (!collide_test_vector(bsp, origin, down, 1.0f, COLLIDE_FRONT | COLLIDE_BACK, &hit)) continue;
        gap = -down[2] * hit.t;
        if (gap < 0.55f || gap > 1.05f) continue;
        ceiling_z = c[2];
        mover_init(&body, (float[3]){c[0], c[1], c[2] - gap + 0.02f});
        for (tick = 0; tick < 20; tick++)
            mover_tick_map(&body, &idle, 0, bsp, scratch, bytes, 2, &stats);
        if (!body.grounded) continue;
        hop.jump = 1;
        mover_tick_map(&body, &hop, 0, bsp, scratch, bytes, 2, &stats);
        head = body.pos[2] + MOVE_STAND_HEIGHT;
        for (tick = 0; tick < 20; tick++) {
            mover_tick_map(&body, &idle, 0, bsp, scratch, bytes, 2, &stats);
            if (body.pos[2] + MOVE_STAND_HEIGHT > head) head = body.pos[2] + MOVE_STAND_HEIGHT;
        }
        printf("ceiling gap %.3f head %.3f limit %.3f\n", gap, head, ceiling_z);
        ceiling = head < ceiling_z + 0.05f;
    }
    printf("ceiling_found %d\n", ceiling);
    (void)spawn;
    for (surface = 0; surface < bsp->edge_count && !corner; surface++) {
        const uint8_t *edge = bsp->edges + (size_t)surface * 24;
        int32_t s0, s1, vertex;
        float a[4], b[4], dot, v[3], out[3], scale;
        mover body;
        float before, after;
        int tick;
        memcpy(&s0, edge + 16, 4);
        memcpy(&s1, edge + 20, 4);
        if (s0 < 0 || s1 < 0) continue;
        surface_plane(bsp, (uint32_t)s0, a);
        surface_plane(bsp, (uint32_t)s1, b);
        if (fabsf(a[2]) > 0.2f || fabsf(b[2]) > 0.2f) continue;
        dot = a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
        if (dot > 0.3f) continue;
        memcpy(&vertex, edge, 4);
        memcpy(v, bsp->vertices + (size_t)vertex * 16, 12);
        out[0] = a[0] + b[0];
        out[1] = a[1] + b[1];
        scale = sqrtf(out[0] * out[0] + out[1] * out[1]);
        if (scale < 0.2f) continue;
        mover_init(&body, (float[3]){v[0] + out[0] / scale * 0.45f, v[1] + out[1] / scale * 0.45f, v[2] + 0.1f});
        for (tick = 0; tick < 20; tick++)
            mover_tick_map(&body, &idle, 0, bsp, scratch, bytes, 0, &stats);
        if (!body.grounded) continue;
        before = body.pos[0];
        body.vel[0] = -out[0] / scale * 3.0f;
        body.vel[1] = -out[1] / scale * 3.0f;
        body.vel[2] = 0;
        mover_tick_map(&body, &idle, 0, bsp, scratch, bytes, 0, &stats);
        after = hypotf(body.pos[0] - v[0], body.pos[1] - v[1]);
        printf("corner remain %.3f\n", after);
        (void)before;
        corner = after > 0.15f;
    }
    printf("corner_found %d\n", corner);
}

int main(int argc, char **argv)
{
    collide_bsp bsp;
    float spawn[4];
    float tags[COLL_TAG_FLOATS];
    float face;
    mover a, b, c;
    move_cmd idle = {0}, walk = {1, 0, 0, 0}, jump = {0}, crouch = {0};
    void *scratch;
    size_t bytes = collide_pill_scratch_bytes();
    collide_pill_stats stats, peak = {0};
    clock_t t0, t1;
    int i;
    float x0, z0;
    if (argc != 2) return 2;
    load_pack(argv[1], &bsp, spawn, tags);
    scratch = malloc(bytes);
    if (!scratch) return 1;
    printf("scratch %zu\n", bytes);
    printf("tags %.5f %.5f %.5f\n", tags[0], tags[9], tags[23]);
    player_spawn(&a, spawn, &face, &x0);
    for (i = 0; i < 90; i++) mover_tick_map(&a, &idle, face, &bsp, scratch, bytes, 0, &stats);
    printf("settle grounded %d z %.4f spawn %.4f eye %.3f oow %d features %d nodes %d\n",
        a.grounded, a.pos[2], spawn[2], a.eye, a.out_of_world, stats.features, stats.nodes_visited);
    /* Viewer camera is degrees. Yaw is the first player-start facing. */
    printf("eye %.4f %.4f %.4f %.4f 0\n",
        a.pos[0], a.pos[1], a.pos[2] + a.eye, 1.328281f * 57.2957795f);
    z0 = a.pos[2];
    jump.jump = 1;
    mover_tick_map(&a, &jump, 0, &bsp, scratch, bytes, 0, &stats);
    printf("jump grounded %d vz %.5f\n", a.grounded, a.vel[2]);
    {
        float peak = a.pos[2];
        for (i = 0; i < 40; i++) {
            mover_tick_map(&a, &idle, 0, &bsp, scratch, bytes, 0, &stats);
            if (a.pos[2] > peak) peak = a.pos[2];
        }
        printf("land grounded %d z %.4f peak %.4f\n", a.grounded, a.pos[2], peak);
    }
    mover_init(&a, spawn);
    for (i = 0; i < 30; i++) mover_tick_map(&a, &idle, 0, &bsp, scratch, bytes, 0, &stats);
    x0 = a.pos[0];
    {
        float y0 = a.pos[1];
        /* first player-start facing, from the scenario location */
        for (i = 0; i < 30; i++) mover_tick_map(&a, &walk, face, &bsp, scratch, bytes, 0, &stats);
        printf("walk dx %.4f dy %.4f z %.4f grounded %d\n",
            a.pos[0] - x0, a.pos[1] - y0, a.pos[2], a.grounded);
    }
    crouch.crouch = 1;
    for (i = 0; i < 6; i++) mover_tick_map(&a, &crouch, 0, &bsp, scratch, bytes, 0, &stats);
    printf("crouch %.3f eye %.3f height %.3f\n", a.crouch, a.eye, a.height);
    mover_init(&b, spawn);
    b.pos[0] += 80.0f;
    b.pos[1] += 80.0f;
    b.pos[2] += 40.0f;
    b.last_safe[0] = spawn[0];
    b.last_safe[1] = spawn[1];
    b.last_safe[2] = spawn[2];
    mover_tick_map(&b, &idle, 0, &bsp, scratch, bytes, 0, &stats);
    printf("recover oow %d x %.3f z %.3f\n", b.out_of_world, b.pos[0], b.pos[2]);
    mover_init(&a, spawn);
    mover_init(&b, spawn);
    mover_init(&c, spawn);
    for (i = 0; i < 20; i++) {
        mover_tick_map(&a, &walk, 0, &bsp, scratch, bytes, 0, &stats);
        mover_tick_map(&b, &walk, 0, &bsp, scratch, bytes, 1, &stats);
        mover_tick_map(&c, &walk, 0, &bsp, scratch, bytes, 2, &stats);
    }
    printf("schedule %d\n",
        a.pos[0] == b.pos[0] && a.pos[0] == c.pos[0] &&
        a.pos[2] == b.pos[2] && a.pos[2] == c.pos[2] && a.tick == 20);
    {
        float origin[3] = {spawn[0], spawn[1], spawn[2] + 0.5f};
        float dir[4][3] = {{20, 0, 0}, {-20, 0, 0}, {0, 20, 0}, {0, -20, 0}};
        int k, blocked = 0;
        for (k = 0; k < 4; k++) {
            collide_hit hit;
            if (!collide_test_vector(&bsp, origin, dir[k], 1, COLLIDE_FRONT, &hit)) continue;
            {
                const float *pl = bsp.planes + (size_t)hit.plane * 4;
                float span = dir[k][0] * dir[k][0] + dir[k][1] * dir[k][1];
                float wall = hit.t * sqrtf(span);
                mover_init(&a, spawn);
                for (i = 0; i < 30; i++) mover_tick_map(&a, &idle, 0, &bsp, scratch, bytes, 0, &stats);
                a.vel[0] = dir[k][0];
                a.vel[1] = dir[k][1];
                a.vel[2] = 0;
                mover_tick_map(&a, &idle, 0, &bsp, scratch, bytes, 0, &stats);
                {
                    float moved = ((a.pos[0] - spawn[0]) * dir[k][0] + (a.pos[1] - spawn[1]) * dir[k][1]) / sqrtf(span);
                    printf("fast dir %d t %.3f wall %.3f moved %.3f nz %.3f features %d nodes %d limited %d\n",
                        k, hit.t, wall, moved, pl[2], stats.features, stats.nodes_visited, stats.depth_limited);
                    if (fabsf(pl[2]) < 0.25f && moved < wall + MOVE_RADIUS) blocked++;
                }
            }
        }
        printf("fast_blocked %d\n", blocked);
    }
    mover_init(&a, spawn);
    t0 = clock();
    for (i = 0; i < 300; i++) {
        mover_tick_map(&a, &walk, 0, &bsp, scratch, bytes, 0, &stats);
        if (stats.features > peak.features) peak.features = stats.features;
        if (stats.nodes_visited > peak.nodes_visited) peak.nodes_visited = stats.nodes_visited;
        peak.depth_limited |= stats.depth_limited;
    }
    t1 = clock();
    printf("bench usec %ld max_features %d max_nodes %d depth_limited %d z %.3f\n",
        (long)((t1 - t0) * 1000000L / CLOCKS_PER_SEC / 300),
        peak.features, peak.nodes_visited, peak.depth_limited, a.pos[2]);
    (void)z0;
    (void)copy_mover;
    geometry_cases(&bsp, scratch, bytes, spawn);
    return 0;
}
