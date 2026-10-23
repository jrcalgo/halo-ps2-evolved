/* Host probe of CE sphere/pill tests against one raw Blood Gulch floor. */
#include "cseries/cseries.h"
#include "physics/collision_bsp.h"
#include "physics/collision_bsp_definitions.h"
#include <stdio.h>
#include <string.h>
#include <math.h>

struct m3_collision_leaf {
    word flags;
    short bsp2d_reference_count;
    long first_bsp2d_reference_index;
};
struct m3_bsp2d_reference { long plane_designator, root_index; };

void error(long type, const char *format, ...)
{
    (void)type;
    (void)format;
}

short const global_projection3d_mappings[3][2][2] = {
    {{2, 1}, {1, 2}}, {{0, 2}, {2, 0}}, {{1, 0}, {0, 1}}
};

void display_assert(char *information, char *file, long line, boolean fatal)
{
    (void)information;
    (void)file;
    (void)line;
    (void)fatal;
}
void system_exit(long code) { (void)code; }
void halt_and_catch_fire(void) { }
void *csmemset(void *buffer, long value, unsigned long size)
{
    return __builtin_memset(buffer, (int)value, size);
}
void *csmemcpy(void *dst, const void *src, unsigned long size)
{
    return __builtin_memcpy(dst, src, size);
}
#undef malloc
#undef free
void *debug_malloc(unsigned int size, boolean clear, const char *file, long line)
{
    (void)clear;
    (void)file;
    (void)line;
    return malloc(size);
}
void debug_free(void *ptr, const char *file, long line)
{
    (void)file;
    (void)line;
    free(ptr);
}

void *tag_block_get_element_with_size(struct tag_block const *block,
    long index, long element_size)
{
    if (!block || !block->address || index < 0 || index >= block->count)
        return NULL;
    if (block->definition && block->definition->element_size != element_size)
        return NULL;
    return (char *)block->address + index * element_size;
}

struct collision_bsp *global_collision_bsp;
void collision_log_usage(short collision_function)
{
    (void)collision_function;
}
void collision_log_start_time(LARGE_INTEGER *start_time)
{
    (void)start_time;
}
void collision_log_end_time(short collision_function, long long end_time)
{
    (void)collision_function;
    (void)end_time;
}
boolean fast_vector_intersects_sphere(
    real_point3d const *point,
    real_vector3d const *vector,
    real_point3d const *center,
    real radius)
{
    real dx = center->x - point->x;
    real dy = center->y - point->y;
    real dz = center->z - point->z;
    real vx = vector->i, vy = vector->j, vz = vector->k;
    real a = vx * vx + vy * vy + vz * vz;
    real b = dx * vx + dy * vy + dz * vz;
    real c = dx * dx + dy * dy + dz * dz - radius * radius;
    real disc;
    if (a <= 0.f)
        return c <= 0.f;
    disc = b * b - a * c;
    if (disc < 0.f)
        return FALSE;
    return (b + sqrtf(disc)) >= 0.f && (b - sqrtf(disc)) <= a;
}

static const float RAW_PLANE[4] = {
    __RAW_PLANE__
};
static const float RAW_XY[4][3] = {
    __RAW_VERTS__
};

static void init_floor(struct collision_bsp *ce,
    struct bsp3d_node *ce_nodes, real_plane3d *ce_planes,
    struct m3_collision_leaf *ce_leaves, struct m3_bsp2d_reference *ce_refs,
    struct collision_surface *ce_surfaces, struct collision_edge *ce_edges,
    struct collision_vertex *ce_vertices)
{
    int i;
    memset(ce, 0, sizeof *ce);
    ce_planes[0].n.i = RAW_PLANE[0];
    ce_planes[0].n.j = RAW_PLANE[1];
    ce_planes[0].n.k = RAW_PLANE[2];
    ce_planes[0].d = RAW_PLANE[3];
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
        ce_vertices[i].point.x = RAW_XY[i][0];
        ce_vertices[i].point.y = RAW_XY[i][1];
        ce_vertices[i].point.z = RAW_XY[i][2];
        ce_vertices[i].first_edge_index = i;
        ce_edges[i].vertex_indices[0] = i;
        ce_edges[i].vertex_indices[1] = (i + 1) % 4;
        ce_edges[i].edge_indices[0] = (i + 1) % 4;
        ce_edges[i].edge_indices[1] = (i + 3) % 4;
        ce_edges[i].surface_indices[0] = 0;
        ce_edges[i].surface_indices[1] = NONE;
    }
    ce->bsp3d.nodes.count = 1;
    ce->bsp3d.nodes.address = ce_nodes;
    ce->bsp3d.planes.count = 1;
    ce->bsp3d.planes.address = ce_planes;
    ce->leaves.count = 1;
    ce->leaves.address = ce_leaves;
    ce->bsp2d_references.count = 1;
    ce->bsp2d_references.address = ce_refs;
    ce->bsp2d.nodes.count = 0;
    ce->bsp2d.nodes.address = NULL;
    ce->surfaces.count = 1;
    ce->surfaces.address = ce_surfaces;
    ce->edges.count = 4;
    ce->edges.address = ce_edges;
    ce->vertices.count = 4;
    ce->vertices.address = ce_vertices;
}

int main(void)
{
    struct collision_bsp ce;
    struct bsp3d_node nodes[1];
    real_plane3d planes[1];
    struct m3_collision_leaf leaves[1];
    struct m3_bsp2d_reference refs[1];
    struct collision_surface surfaces[1];
    struct collision_edge edges[4];
    struct collision_vertex vertices[4];
    struct collision_bsp_test_sphere_result sphere;
    struct collision_bsp_test_pill_result pill;
    real_point3d center, start;
    real_vector3d movement;
    real cx, cy, cz, height;
    int miss, hit, pill_hit;

    init_floor(&ce, nodes, planes, leaves, refs, surfaces, edges, vertices);
    cx = 0.25f * (RAW_XY[0][0] + RAW_XY[1][0] + RAW_XY[2][0] + RAW_XY[3][0]);
    cy = 0.25f * (RAW_XY[0][1] + RAW_XY[1][1] + RAW_XY[2][1] + RAW_XY[3][1]);
    cz = 0.25f * (RAW_XY[0][2] + RAW_XY[1][2] + RAW_XY[2][2] + RAW_XY[3][2]);
    height = RAW_PLANE[0] * cx + RAW_PLANE[1] * cy + RAW_PLANE[2] * cz - RAW_PLANE[3];

    center.x = cx;
    center.y = cy;
    center.z = cz + 2.0f;
    memset(&sphere, 0, sizeof sphere);
    miss = collision_bsp_test_sphere(&ce, 0, NULL, &center, 0.25f, &sphere);

    center.z = cz + 0.10f;
    memset(&sphere, 0, sizeof sphere);
    hit = collision_bsp_test_sphere(&ce, 0, NULL, &center, 0.50f, &sphere);

    start.x = cx;
    start.y = cy;
    start.z = cz + 1.0f;
    movement.i = 0.f;
    movement.j = 0.f;
    movement.k = -2.f;
    memset(&pill, 0, sizeof pill);
    pill_hit = collision_bsp_test_pill(&ce, &start, &movement, 0.25f, 1.f, &pill);

    if (miss || !hit || !pill_hit || sphere.surface_count < 1 ||
        pill.surface_index != 0) {
        fprintf(stderr,
            "FAIL miss=%d hit=%d pill=%d sphere_surfaces=%ld pill_surface=%ld t=%f height=%f\n",
            miss, hit, pill_hit, (long)sphere.surface_count,
            (long)pill.surface_index, pill.t, height);
        return 1;
    }
    printf("mp-swept map=bloodgulch surface=__SURFACE__ "
           "sphere_miss=0 sphere_hit_surfaces=%ld pill_surface=%ld pill_t=%.6f "
           "status=passed\n",
           (long)sphere.surface_count, (long)pill.surface_index, pill.t);
    return 0;
}
