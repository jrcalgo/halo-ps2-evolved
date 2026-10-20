#include "game/grenade.h"
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static void *need(FILE *f, size_t n)
{
    void *p = malloc(n ? n : 1);
    if (!p || (n && fread(p, 1, n, f) != n)) exit(2);
    return p;
}

int main(int argc, char **argv)
{
    FILE *f;
    uint32_t counts[9];
    collide_bsp bsp;
    grenade item;
    float sample[4], eye;
    uint32_t seed = 0x12345678u;
    int exploded;
    if (argc != 2 || !(f = fopen(argv[1], "rb"))) return 2;
    if (fread(counts, 4, 9, f) != 9) return 2;
    memset(&bsp, 0, sizeof bsp);
    bsp.plane_count = counts[0]; bsp.node_count = counts[1];
    bsp.leaf_count = counts[2]; bsp.ref_count = counts[3];
    bsp.node2d_count = counts[4]; bsp.surface_count = counts[5];
    bsp.edge_count = counts[6]; bsp.vertex_count = counts[7];
    bsp.planes = need(f, (size_t)counts[0] * 16);
    bsp.nodes = need(f, (size_t)counts[1] * 12);
    bsp.leaves = need(f, (size_t)counts[2] * 8);
    bsp.refs = need(f, (size_t)counts[3] * 8);
    bsp.nodes2d = need(f, (size_t)counts[4] * 20);
    bsp.surfaces = need(f, (size_t)counts[5] * 12);
    bsp.edges = need(f, (size_t)counts[6] * 24);
    bsp.vertices = need(f, (size_t)counts[7] * 16);
    if (fread(sample, 4, 4, f) != 4 || fread(&eye, 4, 1, f) != 1) return 2;

    memset(&item, 0, sizeof item);
    item.position[0] = sample[0];
    item.position[1] = sample[1];
    item.position[2] = sample[2] + 0.2f;
    item.velocity[2] = -0.3f;
    item.timer_delta = 1.0f / 15.0f;
    item.alive = 1;
    exploded = grenade_tick_bsp(&item, &GRENADE_FRAG, &bsp, &seed);
    printf("bsp_grenade hit=%d bounces=%d alive=%d z=%.4f seed=%08x\n",
        item.bounces > 0, item.bounces, item.alive, item.position[2], seed);
    if (exploded || !item.alive || item.bounces != 1) return 1;

    /* Reproduce the EE smoke's actual player-origin horizontal throw against
     * the retail Blood Gulch COLL tables, then inspect rest/fuse progression. */
    {
        int carried = GRENADE_CARRY_MAX;
        int tick, rest_tick = -1;
        float pitch = -0.5f;
        float aim[3] = {cosf(pitch) * cosf(sample[3]),
            cosf(pitch) * sinf(sample[3]), sinf(pitch)};
        memset(&item, 0, sizeof item);
        seed = 0x12345678u;
        if (!grenade_throw(&item, &GRENADE_FRAG,
                (float[3]){sample[0], sample[1], sample[2] + eye}, aim,
                &carried, &seed)) return 1;
        for (tick = 1; tick <= 300 && item.alive; ++tick) {
            int prior_bounces = item.bounces;
            (void)grenade_tick_bsp(&item, &GRENADE_FRAG, &bsp, &seed);
            if (item.resting && rest_tick < 0) rest_tick = tick;
            if (item.bounces != prior_bounces)
                printf("retail_throw_bounce=%d tick=%d rest=%d pos=%.4f,%.4f,%.4f vel=%.5f,%.5f,%.5f\n",
                    item.bounces, tick, item.resting, item.position[0], item.position[1],
                    item.position[2], item.velocity[0], item.velocity[1], item.velocity[2]);
        }
        printf("retail_throw_exploded=%d tick=%d rest_tick=%d bounces=%d timer=%.5f pos=%.4f,%.4f,%.4f\n",
            item.exploded, tick - 1, rest_tick, item.bounces, item.timer,
            item.position[0], item.position[1], item.position[2]);
        return item.exploded ? 0 : 1;
    }
}
