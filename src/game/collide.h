/* Halo CE structure segment test.
 * collision_bsp_test_vector in halo-64 source/physics/collision_bsp.c,
 * with bsp2d_test_point and collision_surface_test_point.
 * Tables are the Xbox collision BSP: 3D nodes are plane, back, front.
 * No heap. The caller owns the bytes. */
#ifndef GAME_COLLIDE_H
#define GAME_COLLIDE_H
#include <stddef.h>
#include <stdint.h>

#define COLLIDE_FRONT 1u
#define COLLIDE_BACK 2u
#define COLLIDE_IGNORE_TWO_SIDED 4u
#define COLLIDE_IGNORE_INVISIBLE 8u
#define COLLIDE_IGNORE_BREAKABLE 16u

typedef struct {
    const float *planes;          /* plane_count * (nx, ny, nz, d) */
    const uint32_t *nodes;        /* node_count * (plane, back, front) */
    const uint8_t *leaves;        /* leaf_count * 8: flags u16, count i16, first i32 */
    const uint32_t *refs;         /* ref_count * (plane designator, 2d root) */
    const uint8_t *nodes2d;       /* node2d_count * 20: plane f32x3, children i32x2 */
    const uint8_t *surfaces;      /* surface_count * 12 */
    const uint8_t *edges;         /* edge_count * 24: v0 v1 e0 e1 s0 s1, i32 */
    const uint8_t *vertices;      /* vertex_count * 16: xyz f32, first edge i32 */
    const int16_t *material_types;/* CE runtime physics type per BSP collision material */
    uint32_t plane_count, node_count, leaf_count, ref_count;
    uint32_t node2d_count, surface_count, edge_count, vertex_count;
    uint32_t material_count;
} collide_bsp;

typedef struct {
    float t;
    int32_t surface;
    int32_t plane;
} collide_hit;

/* 1 if the segment point + t*vector, t in [0, 1], hits a surface.
 * flags are the collision_bsp_test_vector bits above. */
int collide_test_vector(
    const collide_bsp *bsp,
    const float point[3],
    const float vector[3],
    float maximum_t,
    unsigned flags,
    collide_hit *hit);

/* Resolve a raw BSP surface collision-material index to CE's runtime physics
 * material type. Invalid or unmapped indices resolve to NONE (-1). */
int16_t collide_material_type(const collide_bsp *bsp, int16_t material_index);

/* collision_move_pill for structure only. Scratch is frame scratch,
 * not the heap and not a static in the ELF. 256 features and a BSP
 * depth of 128 are the source caps. */
#define COLLIDE_PILL_FEATURES 256
#define COLLIDE_PILL_DEPTH 128

typedef struct {
    int nodes_visited;
    int features;
    int depth_limited;
    int saturated; /* a 256-feature list filled; the sweep was split */
    int sweeps;
} collide_pill_stats;

typedef struct {
    float pos[3];
    float vel[3];
    float normal[4];
    int32_t surface;
    int grounded;
    int collisions;
} collide_pill_out;

size_t collide_pill_scratch_bytes(void);

/* 0 on success. -1 if scratch is smaller than collide_pill_scratch_bytes. */
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
    collide_pill_stats *stats);

/* 1 when the point is in an empty collision leaf. 0 for solid or outside. */
int collide_point_empty(const collide_bsp *bsp, const float point[3]);
#endif
