#include "game/collpack.h"
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>

int main(int argc, char **argv)
{
    uint8_t payload[256];
    size_t length;
    FILE *f;
    collide_bsp bsp = {0};
    collide_location_view location;
    float planes[12] = {1,0,0,0, 0,1,0,0, 0,0,1,0};
    uint32_t nodes[9] = {
        0, 0x80000000u, 1,
        1, 0x80000001u, 2,
        2, 0x80000002u, 0xFFFFFFFFu
    };
    float a[3] = {-1,0,-1}, b[3] = {-1,0,-0.25f};
    float c[3] = {1,-1,0}, d[3] = {1,1,-1};
    if (argc != 2 || !(f = fopen(argv[1], "rb"))) return 2;
    length = fread(payload, 1, sizeof payload, f);
    if (ferror(f) || !feof(f)) return 3;
    fclose(f);
    if (collpack_location(payload, length, &location) != 0) return 4;
    bsp.planes = planes;
    bsp.nodes = nodes;
    bsp.node_count = 3;
    bsp.plane_count = 3;
    printf("plane %d %d\n", collide_location_underwater(&bsp, &location, a),
           collide_location_underwater(&bsp, &location, b));
    printf("direct %d\n", collide_location_underwater(&bsp, &location, c));
    printf("none %d\n", collide_location_underwater(&bsp, &location, d));
    return 0;
}
