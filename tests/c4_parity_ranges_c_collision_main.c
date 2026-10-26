/* C4 ranges-c member-exact probe for the collision_bsp owner blocks.
 *
 * This translation unit #includes the unmodified CE sources collision_bsp.c,
 * bsp2d.c and bsp3d.c so their static consumers (collision_leaf_test_vector,
 * collision_bsp_valid_leaf, collision_surface_test_point) are reachable without
 * editing CE. Only the host runtime (error, memory, tag block access) is stubbed.
 *
 * Each mode takes key=value arguments, sets exactly the member(s) named in the
 * mode on a synthetic fixture, runs the real consumer and prints its result. The
 * Python side (tests/test_c4_parity_ranges_c.py) computes the expected result
 * independently from the same arguments. Host ILP32 only; not a retail-BSP run.
 *
 * Synthetic fixture geometry: a unit square in the z=0 plane, vertices
 * (0,0,0) (1,0,0) (1,1,0) (0,1,0), edge i joins vertex i and i+1, surface 0 owns
 * the four edges. bsp3d plane 0 is the z=0 plane with normal (0,0,1). */
#include "cseries/cseries.h"
#include "physics/collision_bsp.h"
#include "physics/collision_bsp_definitions.h"
#include "physics/bsp2d.h"
#include "physics/bsp3d.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>

/* ---- host stubs (same contract as tests/c4_parity_collision_walk_main.c) */
void error(short type, const char *format, ...)
{ (void)type; (void)format; }

/* cseries.h maps the str functions to cs* names; CE's bodies call these. */
long csstrcmp(const char *a, const char *b)
{
    while (*a && *a == *b) { a++; b++; }
    return (long)(unsigned char)*a - (long)(unsigned char)*b;
}
long csstrncmp(const char *a, const char *b, unsigned long n)
{
    while (n && *a && *a == *b) { a++; b++; n--; }
    return n ? (long)(unsigned char)*a - (long)(unsigned char)*b : 0;
}
unsigned long csstrlen(const char *a)
{
    unsigned long n = 0;
    while (a[n]) n++;
    return n;
}
#undef strcmp
#undef strncmp
#undef strlen

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
real_point3d *matrix4x3_transform_point(real_matrix4x3 const *matrix,
    real_point3d const *point, real_point3d *result)
{ (void)matrix; *result = *point; return result; }

/* ---- the CE sources, unmodified */
#include "physics/collision_bsp.c"
#include "physics/bsp2d.c"
#include "physics/bsp3d.c"

/* ---- fixture */
static struct collision_bsp bsp;
static struct collision_surface surfaces[2];
static struct collision_edge edges[4];
static struct collision_vertex vertices[4];
static struct collision_leaf leaves[2];
static struct bsp2d_reference references[2];
static struct bsp2d_node bsp2d_nodes[2];
static struct bsp3d_node bsp3d_nodes[2];
static real_plane3d planes[2];

static long parse_long(const char *text) { return strtol(text, NULL, 0); }
static real parse_real(const char *text) { return (real)strtod(text, NULL); }

static const char *arg_value(int argc, char **argv, const char *key)
{
    size_t length = strlen(key);
    int i;
    for (i = 0; i < argc; ++i)
    {
        if (!strncmp(argv[i], key, length) && argv[i][length] == '=')
            return argv[i] + length + 1;
    }
    return NULL;
}

static long arg_long(int argc, char **argv, const char *key, long fallback)
{
    const char *value = arg_value(argc, argv, key);
    return value ? parse_long(value) : fallback;
}

static real arg_real(int argc, char **argv, const char *key, real fallback)
{
    const char *value = arg_value(argc, argv, key);
    return value ? parse_real(value) : fallback;
}

static void square_fixture(void)
{
    int i;
    memset(&bsp, 0, sizeof bsp);
    memset(surfaces, 0, sizeof surfaces);
    memset(edges, 0, sizeof edges);
    memset(vertices, 0, sizeof vertices);
    memset(leaves, 0, sizeof leaves);
    memset(references, 0, sizeof references);
    memset(bsp2d_nodes, 0, sizeof bsp2d_nodes);
    memset(bsp3d_nodes, 0, sizeof bsp3d_nodes);
    memset(planes, 0, sizeof planes);

    planes[0].n.i = 0.f; planes[0].n.j = 0.f; planes[0].n.k = 1.f; planes[0].d = 0.f;
    planes[1].n.i = 0.f; planes[1].n.j = 0.f; planes[1].n.k = -1.f; planes[1].d = 0.f;

    vertices[0].point.x = 0.f; vertices[0].point.y = 0.f; vertices[0].point.z = 0.f;
    vertices[1].point.x = 1.f; vertices[1].point.y = 0.f; vertices[1].point.z = 0.f;
    vertices[2].point.x = 1.f; vertices[2].point.y = 1.f; vertices[2].point.z = 0.f;
    vertices[3].point.x = 0.f; vertices[3].point.y = 1.f; vertices[3].point.z = 0.f;
    for (i = 0; i < 4; ++i)
    {
        vertices[i].first_edge_index = i;
        edges[i].vertex_indices[0] = i;
        edges[i].vertex_indices[1] = (i + 1) % 4;
        edges[i].edge_indices[0] = (i + 1) % 4;
        edges[i].edge_indices[1] = (i + 3) % 4;
        edges[i].surface_indices[0] = 0;
        edges[i].surface_indices[1] = NONE;
    }
    surfaces[0].plane_designator = 0;
    surfaces[0].first_edge_index = 0;
    surfaces[0].flags = 0;
    surfaces[0].breakable_surface_index = 0;
    surfaces[0].material_index = 0;
    surfaces[1].plane_designator = 0;
    surfaces[1].first_edge_index = NONE;

    bsp.bsp3d.planes.count = 2; bsp.bsp3d.planes.address = planes;
    bsp.surfaces.count = 2; bsp.surfaces.address = surfaces;
    bsp.edges.count = 4; bsp.edges.address = edges;
    bsp.vertices.count = 4; bsp.vertices.address = vertices;
}

/* mode vertex: vertex k (k=0..3) point set to (x,y,z); prints the polygon the
 * real collision_surface_polygon emits for surface 0. */
static int mode_vertex(int argc, char **argv)
{
    real_point3d points[MAXIMUM_VERTICES_PER_COLLISION_SURFACE];
    short count, i;
    long k = arg_long(argc, argv, "k", 0);

    square_fixture();
    vertices[k].point.x = arg_real(argc, argv, "x", vertices[k].point.x);
    vertices[k].point.y = arg_real(argc, argv, "y", vertices[k].point.y);
    vertices[k].point.z = arg_real(argc, argv, "z", vertices[k].point.z);
    count = collision_surface_polygon(&bsp, 0, points);
    printf("polygon count=%d", (int)count);
    for (i = 0; i < count; ++i)
        printf(" p%d=%.6f,%.6f,%.6f", (int)i, points[i].x, points[i].y, points[i].z);
    printf("\n");
    return 0;
}

/* mode area: surface 0 plane_designator = designator (sign bit = negated);
 * planes[0] is the z=0 plane with normal (0,0,1) unless n/d are given. */
static int mode_area(int argc, char **argv)
{
    real area;
    long designator = arg_long(argc, argv, "designator", 0);

    square_fixture();
    planes[0].n.i = arg_real(argc, argv, "ni", 0.f);
    planes[0].n.j = arg_real(argc, argv, "nj", 0.f);
    planes[0].n.k = arg_real(argc, argv, "nk", 1.f);
    planes[0].d = arg_real(argc, argv, "d", 0.f);
    surfaces[0].plane_designator = designator;
    area = collision_surface_area(&bsp, 0);
    printf("area=%.6f\n", area);
    return 0;
}

/* mode project: collision_surface_project_point2d on surface 0 (whose
 * plane_designator is designator); the consumer masks the sign bit. */
static int mode_project(int argc, char **argv)
{
    real_point2d point2d;
    real_point3d result;
    long designator = arg_long(argc, argv, "designator", 0);
    short projection = (short)arg_long(argc, argv, "projection", _z);
    boolean sign = arg_long(argc, argv, "sign", 1) != 0;

    square_fixture();
    planes[0].n.i = arg_real(argc, argv, "ni", 0.f);
    planes[0].n.j = arg_real(argc, argv, "nj", 0.f);
    planes[0].n.k = arg_real(argc, argv, "nk", 1.f);
    planes[0].d = arg_real(argc, argv, "d", 0.f);
    surfaces[0].plane_designator = designator;
    point2d.x = arg_real(argc, argv, "px", 0.f);
    point2d.y = arg_real(argc, argv, "py", 0.f);
    collision_surface_project_point2d(&bsp, 0, projection, sign, &point2d, &result);
    printf("projected=%.6f,%.6f,%.6f\n", result.x, result.y, result.z);
    return 0;
}

/* mode surface: collision_surface_test_point on surface 0 at (0.5,0.5).
 * flags is the collision_surface.flags byte (bit 3 = breakable);
 * breakable_index is collision_surface.breakable_surface_index; bits is the
 * breakable surface flag vector (bit n set = breakable surface n intact). */
static int mode_surface(int argc, char **argv)
{
    long bits[2];
    boolean hit;
    short count = (short)arg_long(argc, argv, "count", 4);
    real_point2d point;

    square_fixture();
    surfaces[0].flags = (byte)arg_long(argc, argv, "flags", 0);
    surfaces[0].breakable_surface_index = (byte)arg_long(argc, argv, "breakable_index", 0);
    bits[0] = arg_long(argc, argv, "bits", 0);
    bits[1] = 0;
    point.x = 0.5f;
    point.y = 0.5f;
    hit = collision_surface_test_point(&bsp, count, (byte const *)bits, 0, _z, TRUE, &point);
    printf("hit=%d\n", hit ? 1 : 0);
    return 0;
}

/* mode bsp3d: one bsp3d node (plane 0 with n/d) whose children are leaves
 * named by c0/c1; bsp3d_test_point from root 0 at (px,py,pz). */
static int mode_bsp3d(int argc, char **argv)
{
    union real_point3d point;
    long result;
    long c0 = arg_long(argc, argv, "c0", 0);
    long c1 = arg_long(argc, argv, "c1", 1);

    square_fixture();
    planes[0].n.i = arg_real(argc, argv, "ni", 1.f);
    planes[0].n.j = arg_real(argc, argv, "nj", 0.f);
    planes[0].n.k = arg_real(argc, argv, "nk", 0.f);
    planes[0].d = arg_real(argc, argv, "d", 0.5f);
    bsp3d_nodes[0].plane_designator = 0;
    bsp3d_nodes[0].children[0] = c0;
    bsp3d_nodes[0].children[1] = c1;
    bsp.bsp3d.nodes.count = 1; bsp.bsp3d.nodes.address = bsp3d_nodes;
    point.x = arg_real(argc, argv, "px", 0.f);
    point.y = arg_real(argc, argv, "py", 0.f);
    point.z = arg_real(argc, argv, "pz", 0.f);
    result = bsp3d_test_point(&bsp.bsp3d, 0, &point);
    printf("leaf=%ld\n", result);
    return 0;
}

/* mode leaf: one bsp2d node (plane n/d, children c0/c1) reached through one
 * bsp2d_reference whose plane_designator/root_index are given. The ray
 * (hx,hy) hits the z=0 plane straight down. collision_leaf_test_vector is
 * called with test_surface FALSE, so the answer is the bsp2d result alone.
 * collision_bsp_valid_leaf is reported for the same leaf. */
static int mode_leaf(int argc, char **argv)
{
    real_point3d point, hit;
    real_vector3d vector;
    long surface;
    long reference_count = arg_long(argc, argv, "refs", 1);
    long first = arg_long(argc, argv, "first", 0);
    long leaf_count = arg_long(argc, argv, "leafcount", 1);
    long leaf_flags = arg_long(argc, argv, "leafflags", 0);
    long root = arg_long(argc, argv, "root", 0);
    long designator = arg_long(argc, argv, "designator", 0);
    long c0 = arg_long(argc, argv, "c0", -2147483647L - 1);
    long c1 = arg_long(argc, argv, "c1", -2147483647L - 1);
    square_fixture();
    bsp2d_nodes[0].plane.n.n[0] = arg_real(argc, argv, "nx", 1.f);
    bsp2d_nodes[0].plane.n.n[1] = arg_real(argc, argv, "ny", 0.f);
    bsp2d_nodes[0].plane.d = arg_real(argc, argv, "nd", 0.5f);
    bsp2d_nodes[0].child_indices[0] = c0;
    bsp2d_nodes[0].child_indices[1] = c1;
    bsp.bsp2d.nodes.count = 1; bsp.bsp2d.nodes.address = bsp2d_nodes;

    references[0].plane_designator = designator;
    references[0].root_index = root;
    references[1].plane_designator = 0;
    references[1].root_index = -2147483647L - 1;
    bsp.bsp2d_references.count = 2; bsp.bsp2d_references.address = references;

    leaves[0].flags = (word)leaf_flags;
    leaves[0].bsp2d_reference_count = (short)reference_count;
    leaves[0].first_bsp2d_reference_index = first;
    bsp.leaves.count = 2; bsp.leaves.address = leaves;

    hit.x = arg_real(argc, argv, "hx", 0.2f);
    hit.y = arg_real(argc, argv, "hy", 0.8f);
    hit.z = 1.f;
    point = hit;
    vector.i = 0.f; vector.j = 0.f; vector.k = -1.f;
    if (!collision_bsp_valid_leaf(&bsp, 0))
    {
        /* CE never walks a leaf whose reference span fails the check */
        printf("surface=skipped valid=0\n");
        return 0;
    }
    surface = collision_leaf_test_vector(&bsp, 0, NULL, &point, &vector, 0, 0, 1.f, FALSE);
    printf("surface=%ld valid=1\n", surface);
    return 0;
}

/* mode vector: collision_bsp_test_vector_recursive entered at leaf 0 (a leaf
 * node index), so the CE leaf branch reads leaf->flags for the contents
 * (collision_bsp.c:2216-2224). leafflags=<word>, last=<contents 1 empty,
 * 2 semi-empty, 3 solid>, ignore2=<0|1> sets the ignore-two-sided test flag.
 * The ray is (0.2,0.8,1) straight down, t0=0.25. */
static int mode_vector(int argc, char **argv)
{
    struct collision_bsp_test_vector_context data;
    struct collision_bsp_test_vector_result result;
    real_point3d point;
    real_vector3d vector;
    boolean hit;
    long leaf_flags = arg_long(argc, argv, "leafflags", 0);
    long last = arg_long(argc, argv, "last", _contents_semi_empty);
    long ignore2 = arg_long(argc, argv, "ignore2", 0);

    square_fixture();
    leaves[0].flags = (word)leaf_flags;
    leaves[0].bsp2d_reference_count = 1;
    leaves[0].first_bsp2d_reference_index = 0;
    bsp.leaves.count = 1; bsp.leaves.address = leaves;
    references[0].plane_designator = 0;
    references[0].root_index = LONG_MIN;
    bsp.bsp2d_references.count = 1; bsp.bsp2d_references.address = references;

    memset(&data, 0, sizeof data);
    memset(&result, 0, sizeof result);
    data.flags = (unsigned long)(1UL << _collision_test_ignore_two_sided_surfaces_bit) * ignore2;
    data.bsp = &bsp;
    data.breakable_surface_count = 0;
    data.breakable_surface_flags = NULL;
    point.x = 0.2f; point.y = 0.8f; point.z = 1.f;
    vector.i = 0.f; vector.j = 0.f; vector.k = -1.f;
    data.point = &point;
    data.vector = &vector;
    data.result = &result;
    data.last_leaf_index = NONE;
    data.last_contents = (byte)last;
    data.last_plane_index = 0;
    data.nodes_left = 1000;
    result.t = 1.f;
    hit = collision_bsp_test_vector_recursive(&data, LONG_MIN, 0.25f, 1.f, 0);
    printf("hit=%d t=%.6f surface=%ld last_contents=%d leaf_count=%ld\n",
        hit ? 1 : 0, result.t, result.surface_index, (int)data.last_contents, result.leaf_count);
    return 0;
}

int main(int argc, char **argv)
{
    const char *mode;

    if (argc < 2)
    {
        fprintf(stderr, "usage: c4-ranges-c-collision <vertex|area|project|surface|bsp3d|leaf> key=value...\n");
        return 2;
    }
    mode = argv[1];
    argc -= 1;
    argv += 1;
    if (!strcmp(mode, "vertex")) return mode_vertex(argc, argv);
    if (!strcmp(mode, "area")) return mode_area(argc, argv);
    if (!strcmp(mode, "project")) return mode_project(argc, argv);
    if (!strcmp(mode, "surface")) return mode_surface(argc, argv);
    if (!strcmp(mode, "bsp3d")) return mode_bsp3d(argc, argv);
    if (!strcmp(mode, "leaf")) return mode_leaf(argc, argv);
    if (!strcmp(mode, "vector")) return mode_vector(argc, argv);
    fprintf(stderr, "unknown mode %s\n", mode);
    return 2;
}
