/* C4 member-exact parity probe for collision surface/edge/vertex members.
 *
 * Drives the real CE consumers (collision_bsp.c surface ring walks and
 * collision_features.c vertex feature construction) on one synthetic square
 * where exactly one member is varied per case. Each vertex is placed at
 * (index, 0, 0) so emitted points identify the vertex by its x value.
 * Expected values are derived from the geometry, not from CE output.
 * Host ILP32 only; not a retail-BSP or EE qualification. */
#include "cseries/cseries.h"
#include "physics/collision_bsp.h"
#include "physics/collision_bsp_definitions.h"
#include "physics/collision_features.h"
#include <stdio.h>
#include <string.h>
#include <stdarg.h>
#include <math.h>

/* ---- host stubs (same contract as tests/m3_ce_collision_synthetic_main.c) */
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

/* collision_features_from_vertex passes a NULL matrix; this only has to link. */
real_point3d *matrix4x3_transform_point(real_matrix4x3 const *matrix,
    real_point3d const *point, real_point3d *result)
{ (void)matrix; *result = *point; return result; }

/* ---- fixture: one square surface, four edges, four vertices */
static struct collision_bsp bsp;
static struct collision_surface surfaces[1];
static struct collision_edge edges[4];
static struct collision_vertex vertices[4];
static struct collision_feature_list features;

static void fixture(void)
{
    int i;
    memset(&bsp, 0, sizeof bsp);
    memset(surfaces, 0, sizeof surfaces);
    memset(edges, 0, sizeof edges);
    memset(vertices, 0, sizeof vertices);
    surfaces[0].plane_designator = 0;
    surfaces[0].first_edge_index = 0;
    surfaces[0].flags = 0;
    surfaces[0].breakable_surface_index = 0;
    surfaces[0].material_index = 0;
    for (i = 0; i < 4; ++i) {
        edges[i].vertex_indices[0] = i;
        edges[i].vertex_indices[1] = (i + 1) % 4;
        edges[i].edge_indices[0] = (i + 1) % 4;
        edges[i].edge_indices[1] = (i + 3) % 4;
        edges[i].surface_indices[0] = 0;
        edges[i].surface_indices[1] = NONE;
        vertices[i].point.x = (float)i;
        vertices[i].point.y = 0.f;
        vertices[i].point.z = 0.f;
        vertices[i].first_edge_index = i;
    }
    bsp.surfaces.count = 1; bsp.surfaces.address = surfaces;
    bsp.edges.count = 4; bsp.edges.address = edges;
    bsp.vertices.count = 4; bsp.vertices.address = vertices;
    memset(&features, 0, sizeof features);
}

/* Walk surface 0 with the real CE consumer; return the point count and
 * write the vertex x values (vertex indices) into out. */
static int walk(int *out, int *edge_count_out)
{
    real_point3d points[MAXIMUM_VERTICES_PER_COLLISION_SURFACE];
    short count = collision_surface_polygon(&bsp, 0, points);
    int i;
    for (i = 0; i < count; ++i) out[i] = (int)points[i].x;
    if (edge_count_out)
        *edge_count_out = collision_surface_edge_count(&bsp, 0);
    return count;
}

static void print_list(const char *label, int *v, int n)
{
    int i;
    printf("%s=[", label);
    for (i = 0; i < n; ++i) printf(i ? ",%d" : "%d", v[i]);
    printf("]");
}

static int expect_list(int *got, int got_n, const int *want, int want_n)
{
    int i;
    if (got_n != want_n) return 0;
    for (i = 0; i < want_n; ++i) if (got[i] != want[i]) return 0;
    return 1;
}

int main(void)
{
    int out[MAXIMUM_VERTICES_PER_COLLISION_SURFACE];
    int n, ec, ok, failures = 0;
    static const int want_base[4] = {0, 1, 2, 3};
    static const int want_rotated[4] = {2, 3, 0, 1};
    static const int want_edge_ring[3] = {0, 2, 3};
    static const int want_flipped[2] = {1, 3};

    /* collision_surface.first_edge_index: baseline ring from edge 0. */
    fixture();
    n = walk(out, &ec);
    ok = expect_list(out, n, want_base, 4) && ec == 4;
    printf("member=collision_surface.first_edge_index variant=baseline ");
    print_list("points", out, n); printf(" edge_count=%d status=%s\n", ec, ok ? "passed" : "failed");
    failures += !ok;

    /* collision_surface.first_edge_index = 2: same ring, rotated start. */
    fixture();
    surfaces[0].first_edge_index = 2;
    n = walk(out, &ec);
    ok = expect_list(out, n, want_rotated, 4) && ec == 4;
    printf("member=collision_surface.first_edge_index variant=start2 ");
    print_list("points", out, n); printf(" edge_count=%d status=%s\n", ec, ok ? "passed" : "failed");
    failures += !ok;

    /* collision_surface.first_edge_index = 7 (no such edge): bounded empty. */
    fixture();
    surfaces[0].first_edge_index = 7;
    n = walk(out, &ec);
    ok = (n == 0 && ec == 0);
    printf("member=collision_surface.first_edge_index variant=out_of_range points=%d edge_count=%d status=%s\n",
        n, ec, ok ? "bounded" : "failed");
    failures += !ok;

    /* collision_edge.edge_indices: edge 0 links to edge 2, skipping vertex 1. */
    fixture();
    edges[0].edge_indices[0] = 2;
    n = walk(out, &ec);
    ok = expect_list(out, n, want_edge_ring, 3) && ec == 3;
    printf("member=collision_edge.edge_indices variant=skip_edge1 ");
    print_list("points", out, n); printf(" edge_count=%d status=%s\n", ec, ok ? "passed" : "failed");
    failures += !ok;

    /* collision_edge.surface_indices: edge 0 owned by surface 0 on the
     * reverse side selects vertex 1 and edge 3, which closes after two. */
    fixture();
    edges[0].surface_indices[0] = NONE;
    edges[0].surface_indices[1] = 0;
    n = walk(out, &ec);
    ok = expect_list(out, n, want_flipped, 2) && ec == 2;
    printf("member=collision_edge.surface_indices variant=reverse_edge0 ");
    print_list("points", out, n); printf(" edge_count=%d status=%s\n", ec, ok ? "passed" : "failed");
    failures += !ok;

    /* collision_vertex.first_edge_index: vertex 0 feature built from its
     * first edge's surface (baseline emits one sphere on surface 0). */
    fixture();
    collision_features_new(&features);
    collision_features_from_vertex(&bsp, 0, NULL, 0.f, 0.5f, NONE, &features);
    ok = features.count[_collision_feature_sphere] == 1 &&
        features.spheres[0].surface_index == 0 &&
        fabsf(features.spheres[0].center.x - 0.f) < 1e-6f;
    printf("member=collision_vertex.first_edge_index variant=baseline sphere_count=%d surface=%ld status=%s\n",
        features.count[_collision_feature_sphere], features.spheres[0].surface_index,
        ok ? "passed" : "failed");
    failures += !ok;

    /* collision_vertex.first_edge_index = 7 (no edge): no feature. */
    fixture();
    collision_features_new(&features);
    vertices[0].first_edge_index = 7;
    collision_features_from_vertex(&bsp, 0, NULL, 0.f, 0.5f, NONE, &features);
    ok = features.count[_collision_feature_sphere] == 0;
    printf("member=collision_vertex.first_edge_index variant=out_of_range sphere_count=%d status=%s\n",
        features.count[_collision_feature_sphere], ok ? "bounded" : "failed");
    failures += !ok;

    /* collision_vertex.first_edge_index = 1 where edge 1 has no surface:
     * the feature is refused instead of reading a surface. */
    fixture();
    collision_features_new(&features);
    vertices[0].first_edge_index = 1;
    edges[1].surface_indices[0] = NONE;
    collision_features_from_vertex(&bsp, 0, NULL, 0.f, 0.5f, NONE, &features);
    ok = features.count[_collision_feature_sphere] == 0;
    printf("member=collision_vertex.first_edge_index variant=edge_without_surface sphere_count=%d status=%s\n",
        features.count[_collision_feature_sphere], ok ? "bounded" : "failed");
    /* (bounded: the feature is refused, not emitted) */
    failures += !ok;

    printf("c4_collision_walk failures=%d\n", failures);
    return failures ? 1 : 0;
}
