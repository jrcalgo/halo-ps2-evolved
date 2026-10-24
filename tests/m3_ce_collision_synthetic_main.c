/* Synthetic host-only probe of CE collision BSP primitives against the
 * parent collision oracle. Geometry is one bounded square floor. */
#include "cseries/cseries.h"
#include "physics/collision_bsp.h"
#include "physics/collision_bsp_definitions.h"
#include "game/collide.h"
#include <stdio.h>
#include <string.h>
#include <stdarg.h>
#include <math.h>

struct m3_collision_leaf {
    word flags;
    short bsp2d_reference_count;
    long first_bsp2d_reference_index;
};
struct m3_bsp2d_reference { long plane_designator, root_index; };

/* The retained CE collision-bsp function section can call these only on
 * malformed inputs or through the slow tag-block fallback. Valid fixture
 * paths stay inside the source's inline fast accessors. */
void error(long type, const char *format, ...)
{
    (void)type; (void)format;
}

short const global_projection3d_mappings[3][2][2] = {
    {{2,1},{1,2}}, {{0,2},{2,0}}, {{1,0},{0,1}}
};

void display_assert(char *information, char *file, long line, boolean fatal)
{ (void)information; (void)file; (void)line; (void)fatal; }
void system_exit(long code) { (void)code; }
void halt_and_catch_fire(void) { }
void *csmemset(void *buffer, long value, unsigned long size)
{ return __builtin_memset(buffer, (int)value, size); }
void *csmemcpy(void *dst, const void *src, unsigned long size)
{ return __builtin_memcpy(dst, src, size); }
#undef malloc
#undef free
void *debug_malloc(unsigned int size, boolean clear, const char *file, long line)
{ (void)clear; (void)file; (void)line; return malloc(size); }
void debug_free(void *ptr, const char *file, long line)
{ (void)file; (void)line; free(ptr); }

void *tag_block_get_element_with_size(struct tag_block const *block,
    long index, long element_size)
{
    if (!block || !block->address || index < 0 || index >= block->count)
        return NULL;
    if (block->definition && block->definition->element_size != element_size)
        return NULL;
    return (char *)block->address + index * element_size;
}

static void init_square(struct collision_bsp *ce,
    struct bsp3d_node *ce_nodes, real_plane3d *ce_planes,
    struct m3_collision_leaf *ce_leaves, struct m3_bsp2d_reference *ce_refs,
    struct collision_surface *ce_surfaces, struct collision_edge *ce_edges,
    struct collision_vertex *ce_vertices,
    collide_bsp *parent, float parent_planes[4], uint32_t parent_nodes[3],
    uint8_t parent_leaves[8], uint32_t parent_refs[2],
    uint8_t parent_surface[12], uint8_t parent_edges[96],
    uint8_t parent_vertices[64])
{
    static const float xy[4][2] = {{-2.f,-2.f},{2.f,-2.f},{2.f,2.f},{-2.f,2.f}};
    int i;
    memset(ce, 0, sizeof *ce);
    memset(parent, 0, sizeof *parent);
    ce_planes[0].n.i = 0.f; ce_planes[0].n.j = 0.f;
    ce_planes[0].n.k = 1.f; ce_planes[0].d = 0.f;
    ce_nodes[0].plane_designator = 0;
    ce_nodes[0].children[0] = NONE;
    ce_nodes[0].children[1] = (long)(0x80000000u | 0u);
    ce_leaves[0].flags = 0;
    ce_leaves[0].bsp2d_reference_count = 1;
    ce_leaves[0].first_bsp2d_reference_index = 0;
    ce_refs[0].plane_designator = 0;
    ce_refs[0].root_index = (long)0x80000000u;
    ce_surfaces[0].plane_designator = 0;
    ce_surfaces[0].first_edge_index = 0;
    ce_surfaces[0].flags = 0;
    ce_surfaces[0].material_index = 0;
    for (i = 0; i < 4; ++i) {
        ce_vertices[i].point.x = xy[i][0];
        ce_vertices[i].point.y = xy[i][1];
        ce_vertices[i].point.z = 0.f;
        ce_vertices[i].first_edge_index = i;
        ce_edges[i].vertex_indices[0] = i;
        ce_edges[i].vertex_indices[1] = (i + 1) % 4;
        ce_edges[i].edge_indices[0] = (i + 1) % 4;
        ce_edges[i].edge_indices[1] = (i + 3) % 4;
        ce_edges[i].surface_indices[0] = 0;
        ce_edges[i].surface_indices[1] = NONE;
    }
    ce->bsp3d.nodes.count = 1; ce->bsp3d.nodes.address = ce_nodes;
    ce->bsp3d.planes.count = 1; ce->bsp3d.planes.address = ce_planes;
    ce->leaves.count = 1; ce->leaves.address = ce_leaves;
    ce->bsp2d_references.count = 1; ce->bsp2d_references.address = ce_refs;
    ce->bsp2d.nodes.count = 0; ce->bsp2d.nodes.address = NULL;
    ce->surfaces.count = 1; ce->surfaces.address = ce_surfaces;
    ce->edges.count = 4; ce->edges.address = ce_edges;
    ce->vertices.count = 4; ce->vertices.address = ce_vertices;

    parent_planes[0] = 0.f; parent_planes[1] = 0.f;
    parent_planes[2] = 1.f; parent_planes[3] = 0.f;
    parent_nodes[0] = 0; parent_nodes[1] = 0xFFFFFFFFu;
    parent_nodes[2] = 0x80000000u;
    memset(parent_leaves, 0, 8);
    { int16_t refs = 1; int32_t first = 0;
      memcpy(parent_leaves + 2, &refs, 2); memcpy(parent_leaves + 4, &first, 4); }
    parent_refs[0] = 0; parent_refs[1] = 0x80000000u;
    memset(parent_surface, 0, 12);
    { int32_t first_edge = 0; memcpy(parent_surface + 4, &first_edge, 4); }
    memset(parent_edges, 0, 96);
    memset(parent_vertices, 0, 64);
    for (i = 0; i < 4; ++i) {
        int32_t data[6] = {i, (i + 1) % 4, (i + 1) % 4,
            (i + 3) % 4, 0, -1};
        float point[3] = {xy[i][0], xy[i][1], 0.f};
        int32_t first_edge = i;
        memcpy(parent_edges + i * 24, data, sizeof data);
        memcpy(parent_vertices + i * 16, point, sizeof point);
        memcpy(parent_vertices + i * 16 + 12, &first_edge, 4);
    }
    parent->planes = parent_planes; parent->nodes = parent_nodes;
    parent->leaves = parent_leaves; parent->refs = parent_refs;
    parent->surfaces = parent_surface; parent->edges = parent_edges;
    parent->vertices = parent_vertices;
    parent->plane_count = 1; parent->node_count = 1; parent->leaf_count = 1;
    parent->ref_count = 1; parent->node2d_count = 0; parent->surface_count = 1;
    parent->edge_count = 4; parent->vertex_count = 4;
}

int main(void)
{
    struct collision_bsp ce;
    struct bsp3d_node nodes[1]; real_plane3d planes[1];
    struct m3_collision_leaf leaves[1]; struct m3_bsp2d_reference refs[1];
    struct collision_surface surfaces[1]; struct collision_edge edges[4];
    struct collision_vertex vertices[4];
    collide_bsp parent; float parent_planes[4]; uint32_t parent_nodes[3];
    uint8_t parent_leaves[8], parent_surface[12], parent_edges[96], parent_vertices[64];
    uint32_t parent_refs[2];
    real_point3d start = { .x = 0.f, .y = 0.f, .z = 1.f };
    real_point3d outside = { .x = 3.f, .y = 0.f, .z = 1.f };
    real_vector3d movement = { .i = 0.f, .j = 0.f, .k = -2.f };
    real real_t; real_vector3d real_normal;
    struct collision_bsp_test_pill_result ce_result;
    float pstart[3] = {0.f,0.f,1.f}, pvel[3] = {0.f,0.f,-2.f};
    collide_pill_out parent_result; collide_hit vector_result;
    void *scratch;
    int ce_hit, parent_rc, parent_vector_hit;

    init_square(&ce, nodes, planes, leaves, refs, surfaces, edges, vertices,
        &parent, parent_planes, parent_nodes, parent_leaves, parent_refs,
        parent_surface, parent_edges, parent_vertices);
    /* Parent raw surface bytes must be independent of the CE struct layout. */
    { int32_t plane_designator = 0, first_edge = 0;
      memset(parent_surface, 0, sizeof parent_surface);
      memcpy(parent_surface, &plane_designator, 4);
      memcpy(parent_surface + 4, &first_edge, 4); }
    parent.surfaces = parent_surface;
    ce_hit = collision_bsp_test_pill(&ce, &start, &movement, 0.25f, 1.f, &ce_result);
    scratch = malloc(collide_pill_scratch_bytes());
    if (!scratch) return 2;
    parent_rc = collide_move_pill(&parent, pstart, pvel, 0.f, 0.25f, 0.70f,
        scratch, collide_pill_scratch_bytes(), &parent_result, NULL);
    parent_vector_hit = collide_test_vector(&parent, pstart, pvel, 1.f,
        COLLIDE_FRONT, &vector_result);
    free(scratch);
    if (!ce_hit || parent_rc != 0 || !parent_result.grounded ||
        !parent_vector_hit || ce_result.surface_index != 0 ||
        fabsf(ce_result.t - 0.375f) > 0.0001f ||
        fabsf(parent_result.pos[2] - 0.25f) > 0.01f ||
        fabsf(parent_result.normal[2] - 1.f) > 0.001f ||
        fabsf(vector_result.t - 0.5f) > 0.0001f) return 3;
    printf("synthetic_floor ce_surface=%ld ce_t=%.6f parent_pill_z=%.6f parent_vector_t=%.6f status=passed\n",
        ce_result.surface_index, ce_result.t, parent_result.pos[2], vector_result.t);

    /* The newer API reports an outside-BSP boundary, not this finite floor's
     * surface/material. Keep that distinct from the old surface-aware path. */
    ce_hit = collision_bsp_test_pill_new(&ce, 0, NULL, &start, &movement,
        0.25f, &real_t, &real_normal);
    if (!ce_hit || fabsf(real_t - 0.375f) > 0.0001f ||
        fabsf(real_normal.k - 1.f) > 0.001f) return 4;
    printf("synthetic_boundary pill_new_t=%.6f normal_z=%.3f status=observed\n",
        real_t, real_normal.k);

    /* Same finite floor, but outside its square edge. Surface-aware CE and
     * the parent pill mover should both miss. pill_new is intentionally not
     * asserted here: this one-node BSP does not encode outside-volume splits. */
    ce_hit = collision_bsp_test_pill(&ce, &outside, &movement, 0.25f, 1.f, &ce_result);
    pstart[0] = 3.f; pstart[1] = 0.f; pstart[2] = 1.f;
    scratch = malloc(collide_pill_scratch_bytes());
    if (!scratch) return 6;
    parent_rc = collide_move_pill(&parent, pstart, pvel, 0.f, 0.25f, 0.70f,
        scratch, collide_pill_scratch_bytes(), &parent_result, NULL);
    free(scratch);
    if (ce_hit || parent_rc != 0 || parent_result.grounded ||
        fabsf(parent_result.pos[2] + 1.f) > 0.001f) return 5;
    printf("synthetic_outside_square ce_surface_hit=0 parent_grounded=0 parent_z=%.3f status=passed\n",
        parent_result.pos[2]);

    /* Defensive runtime guards: malformed graphs are still rejected by the
     * CE schema gate before gameplay, but collision traversal itself must be
     * bounded if such a graph reaches it. */
    init_square(&ce, nodes, planes, leaves, refs, surfaces, edges, vertices,
        &parent, parent_planes, parent_nodes, parent_leaves, parent_refs,
        parent_surface, parent_edges, parent_vertices);
    nodes[0].children[0] = 0; /* cycle back to the same 3D node */
    nodes[0].children[1] = (long)0x80000001u; /* invalid leaf index */
    {
        struct {
            uint32_t before;
            struct collision_bsp_test_pill_result result;
            uint32_t after;
        } guarded;
        guarded.before = 0x13579bdfu;
        guarded.after = 0x2468ace0u;
        ce_hit = collision_bsp_test_pill(&ce, &start, &movement, 0.25f,
            1.f, &guarded.result);
        if (ce_hit || guarded.before != 0x13579bdfu ||
            guarded.after != 0x2468ace0u) return 7;
    }
    real_t = -7.f;
    real_normal.i = 31.f; real_normal.j = 32.f; real_normal.k = 33.f;
    if (collision_bsp_test_pill_new(&ce, 0, NULL, &start, &movement,
        0.25f, &real_t, &real_normal)) return 8;
    if (!isfinite(real_t)) return 9;
    printf("malformed_cycle ce_surface_hit=0 pill_new_hit=0 status=bounded\n");

    init_square(&ce, nodes, planes, leaves, refs, surfaces, edges, vertices,
        &parent, parent_planes, parent_nodes, parent_leaves, parent_refs,
        parent_surface, parent_edges, parent_vertices);
    nodes[0].children[0] = 1; /* outside the single-node block */
    nodes[0].children[1] = (long)0x80000001u;
    if (collision_bsp_test_pill(&ce, &start, &movement, 0.25f, 1.f,
        &ce_result)) return 10;
    printf("malformed_child ce_surface_hit=0 status=bounded\n");

    init_square(&ce, nodes, planes, leaves, refs, surfaces, edges, vertices,
        &parent, parent_planes, parent_nodes, parent_leaves, parent_refs,
        parent_surface, parent_edges, parent_vertices);
    leaves[0].first_bsp2d_reference_index = 1;
    leaves[0].bsp2d_reference_count = 1; /* interval exceeds references */
    if (collision_bsp_test_pill(&ce, &start, &movement, 0.25f, 1.f,
        &ce_result)) return 11;
    printf("malformed_leaf_refs ce_surface_hit=0 status=bounded\n");

    {
        struct collision_edge long_ring[9];
        real_point3d polygon[MAXIMUM_VERTICES_PER_COLLISION_SURFACE];
        int edge;
        init_square(&ce, nodes, planes, leaves, refs, surfaces, edges, vertices,
            &parent, parent_planes, parent_nodes, parent_leaves, parent_refs,
            parent_surface, parent_edges, parent_vertices);
        memset(long_ring, 0, sizeof long_ring);
        for (edge = 0; edge < 9; ++edge) {
            long_ring[edge].vertex_indices[0] = edge % 4;
            long_ring[edge].edge_indices[0] = (edge + 1) % 9;
            long_ring[edge].edge_indices[1] = NONE;
            long_ring[edge].surface_indices[0] = 0;
            long_ring[edge].surface_indices[1] = NONE;
        }
        ce.edges.address = long_ring;
        ce.edges.count = 9;
        if (collision_surface_edge_count(&ce, 0) !=
            MAXIMUM_EDGES_PER_COLLISION_SURFACE ||
            collision_surface_polygon(&ce, 0, polygon) !=
            MAXIMUM_VERTICES_PER_COLLISION_SURFACE) return 12;
        printf("malformed_edge_ring edge_limit=%d polygon_limit=%d status=bounded\n",
            MAXIMUM_EDGES_PER_COLLISION_SURFACE,
            MAXIMUM_VERTICES_PER_COLLISION_SURFACE);
    }
    return 0;
}
