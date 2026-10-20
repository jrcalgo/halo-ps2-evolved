#include "game/collpack.h"
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static int test_water_leaf(collide_bsp *bsp, uint32_t nodes[9],
    collide_location_view *location, uint32_t leaf)
{
    int16_t cluster;
    uint16_t reference;
    uint32_t plane_index;
    int16_t region;
    float equation[4], offset, norm_squared, below[3], above[3];
    uint32_t terminal;
    unsigned axis;
    int water_below, water_above;
    if (leaf >= location->leaf_count) return 5;
    memcpy(&cluster, location->leaf_clusters + (size_t)leaf * 2, 2);
    if (cluster < 0 || (uint32_t)cluster >= location->cluster_count) return 5;
    memcpy(&reference, location->cluster_fog + (size_t)cluster * 2, 2);
    if (reference == 0xFFFFu || !(reference & 0x8000u)) return 5;
    plane_index = reference & 0x7FFFu;
    if (plane_index >= location->fog_plane_count) return 5;
    memcpy(&region, location->fog_planes + (size_t)plane_index * 18, 2);
    if (region < 0 || (uint32_t)region >= location->fog_region_count ||
        !(location->fog_regions[(size_t)region * 8] & 1u)) return 5;
    memcpy(equation, location->fog_planes + (size_t)plane_index * 18 + 2, sizeof equation);
    memcpy(&offset, location->fog_regions + (size_t)region * 8 + 4, 4);
    norm_squared = equation[0] * equation[0] + equation[1] * equation[1] +
        equation[2] * equation[2];
    if (norm_squared <= 0.0f) return 5;
    for (axis = 0; axis < 3; axis++) {
        below[axis] = equation[axis] * (-1.0f + equation[3] - offset) / norm_squared;
        above[axis] = equation[axis] * (1.0f + equation[3] - offset) / norm_squared;
    }
    terminal = 0x80000000u | leaf;
    nodes[0] = 0;
    nodes[1] = terminal;
    nodes[2] = terminal;
    bsp->node_count = 1;
    water_below = collide_location_underwater(bsp, location, below);
    water_above = collide_location_underwater(bsp, location, above);
    printf("water-plane %d %d\n", water_below, water_above);
    return water_below == 1 && water_above == 0 ? 0 : 7;
}

int main(int argc, char **argv)
{
    uint8_t *payload;
    size_t length;
    long file_length;
    FILE *f;
    collide_bsp bsp = {0};
    collide_location_view location;
    float planes[12] = {1,0,0,0, 0,1,0,0, 0,0,1,0};
    uint32_t nodes[9] = {
        0, 0x80000000u, 1,
        1, 0x80000001u, 2,
        2, 0x80000002u, 0xFFFFFFFFu
    };
    char *end;
    float a[3] = {-1,0,-1}, b[3] = {-1,0,-0.25f};
    float c[3] = {1,-1,0}, d[3] = {1,1,-1};
    if ((argc != 2 && argc != 3) || !(f = fopen(argv[1], "rb"))) return 2;
    if (fseek(f, 0, SEEK_END) != 0 || (file_length = ftell(f)) <= 0 ||
        fseek(f, 0, SEEK_SET) != 0) return 3;
    length = (size_t)file_length;
    payload = (uint8_t *)malloc(length);
    if (!payload) return 3;
    if (fread(payload, 1, length, f) != length || ferror(f)) return 3;
    fclose(f);
    if (collpack_location(payload, length, &location) != 0) { free(payload); return 4; }
    bsp.planes = planes;
    bsp.nodes = nodes;
    bsp.node_count = 3;
    bsp.plane_count = 3;
    if (argc == 3) {
        unsigned long leaf = strtoul(argv[2], &end, 0);
        int result;
        if (!argv[2][0] || *end || leaf > 0x7FFFFFFFu) { free(payload); return 5; }
        result = test_water_leaf(&bsp, nodes, &location, (uint32_t)leaf);
        free(payload);
        return result;
    }
    printf("plane %d %d\n", collide_location_underwater(&bsp, &location, a),
           collide_location_underwater(&bsp, &location, b));
    printf("direct %d\n", collide_location_underwater(&bsp, &location, c));
    printf("none %d\n", collide_location_underwater(&bsp, &location, d));
    free(payload);
    return 0;
}
