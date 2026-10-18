/* Reads a collision-BSP fixture and prints one line per spawn:
 * hit <t> <ground z> <spawn z>
 * or miss. The fixture is built by tests/test_collide.py from the
 * retail collision BSP. */
#include "game/collide.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static void *need(FILE *f, size_t n)
{
    void *p = malloc(n ? n : 1);
    if (!p || (n && fread(p, 1, n, f) != n)) {
        fprintf(stderr, "truncated fixture\n");
        exit(1);
    }
    return p;
}

int main(int argc, char **argv)
{
    FILE *f;
    uint32_t counts[9];
    collide_bsp bsp;
    uint32_t i;
    if (argc != 2) return 2;
    f = fopen(argv[1], "rb");
    if (!f) return 2;
    if (fread(counts, 4, 9, f) != 9) return 1;
    memset(&bsp, 0, sizeof bsp);
    bsp.plane_count = counts[0];
    bsp.node_count = counts[1];
    bsp.leaf_count = counts[2];
    bsp.ref_count = counts[3];
    bsp.node2d_count = counts[4];
    bsp.surface_count = counts[5];
    bsp.edge_count = counts[6];
    bsp.vertex_count = counts[7];
    bsp.planes = need(f, (size_t)counts[0] * 16);
    bsp.nodes = need(f, (size_t)counts[1] * 12);
    bsp.leaves = need(f, (size_t)counts[2] * 8);
    bsp.refs = need(f, (size_t)counts[3] * 8);
    bsp.nodes2d = need(f, (size_t)counts[4] * 20);
    bsp.surfaces = need(f, (size_t)counts[5] * 12);
    bsp.edges = need(f, (size_t)counts[6] * 24);
    bsp.vertices = need(f, (size_t)counts[7] * 16);
    for (i = 0; i < counts[8]; i++) {
        float s[4], point[3], vector[3] = {0, 0, -4};
        collide_hit hit;
        if (fread(s, 4, 4, f) != 4) return 1;
        point[0] = s[0];
        point[1] = s[1];
        point[2] = s[2] + 2.0f;
        if (collide_test_vector(&bsp, point, vector, 1.0f, COLLIDE_FRONT, &hit))
            printf("hit %.6f %.6f %.6f\n", hit.t, s[2] + 2.0f - 4.0f * hit.t, s[2]);
        else
            printf("miss\n");
    }
    return 0;
}
