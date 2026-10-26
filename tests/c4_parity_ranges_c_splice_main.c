/* C4 ranges-c member-exact probe for owner blocks whose CE consumers need
 * more state than the owner block itself.
 *
 * The CE bodies and loop fragments are spliced verbatim from the pinned
 * sources into c4_extract_ranges.inc by tests/test_c4_parity_ranges_c.py,
 * with boundary assertions. This file supplies only the surrounding state
 * (render globals, lightmaps, breakable flags, error reporting). Every stub is
 * named here. The Python side computes every expected result independently.
 * Host ILP32 only. */
#include "cseries/cseries.h"
#include "physics/collision_bsp.h"
#include "physics/collision_bsp_definitions.h"
#include "math/real_math.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

/* ---- host stubs */
static long c4_match_failures;
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
void error(short type, const char *format, ...) { (void)type; (void)format; }
void display_assert(char *information, char *file, long line, boolean fatal)
{ (void)information; (void)file; (void)line; (void)fatal; c4_match_failures++; }
void system_exit(long code) { (void)code; }
void *csmemset(void *buffer, long value, unsigned long size)
{ return __builtin_memset(buffer, (int)value, size); }
void *csmemcpy(void *dst, const void *src, unsigned long size)
{ return __builtin_memcpy(dst, src, size); }
void *tag_block_get_element_with_size(struct tag_block const *block,
    long index, long element_size)
{
    if (!block || !block->address || index < 0 || index >= block->count)
        return NULL;
    if (block->definition && block->definition->element_size != element_size)
        return NULL;
    return (char *)block->address + index * element_size;
}
enum { _error_silent = 0, _collision_surface_breakable_bit = 3 };
#define MAXIMUM_RENDERED_ENVIRONMENT_SURFACES 32768
#define COMPRESSED_STRUCTURE_VERTEX_SIZE 0x20
#define NUMBER_OF_VERTICES_PER_TRIANGLE 3
#define MAXIMUM_BREAKABLE_SURFACES_PER_MAP_STUB 256

/* CE's match_assert (cseries.h) reports through display_assert; a failed match
 * check is counted here instead of stopping the process. */
static long c4_match_failures;

/* Frustum visibility is outside the owner block: every triangle is visible,
 * so the result isolates the index, group and vertex-range checks. */
static boolean render_frustum_triangle_visible(struct render_frustum const *frustum,
    real_point3d const *a, real_point3d const *b, real_point3d const *c)
{ (void)frustum; (void)a; (void)b; (void)c; return TRUE; }

/* Breakable flags: stands in for the runtime breakable flag vector. */
static long c4_breakable_words[MAXIMUM_BREAKABLE_SURFACES_PER_MAP_STUB / 32];
byte *breakable_surface_flags_get(void) { return (byte *)c4_breakable_words; }

/* ---- CE structures the spliced bodies name (CE members, unrelated ones omitted) */
struct render_frustum { long unused; };
struct c4_size_block { long count; void *address; long size; };
struct structure_material { struct c4_size_block compressed_vertex_data; };
struct structure_lightmap { struct tag_block materials; };
struct structure_visibility_surface { word vertex_indices[NUMBER_OF_VERTICES_PER_TRIANGLE]; };
struct structure_visibility_subcluster { struct tag_block surface_indices; };
struct structure_visibility_cluster { struct tag_block surface_indices; };
struct structure_weather_polyhedron { struct tag_block planes; };
struct structure_bsp
{
    struct tag_block pathfinding_surfaces;
    struct tag_block collision_bsp;
    struct tag_block surfaces;
    struct tag_block lightmaps;
    struct tag_block weather_polyhedra;
};
/* render.environment_surface_flags / environment_surface_count as used by the
 * visibility traversal fragments. */
static struct
{
    long environment_surface_flags[MAXIMUM_RENDERED_ENVIRONMENT_SURFACES / LONG_BITS];
    long environment_surface_count;
} render;

/* Debug draw stand-ins: render_debug_leaf_portal (leaf_map.c:528) only forwards
 * vertices and colours to these, so they print what they were given. */
const union real_argb_color *global_real_argb_red;
static union real_argb_color const c4_red_color = {{1.f, 1.f, 0.f, 0.f}};
static void c4_print_point(real_point3d const *p)
{ printf("(%.6f,%.6f,%.6f)", p->x, p->y, p->z); }
static void c4_print_color(real_argb_color const *color)
{ printf("color=%.1f,%.1f,%.1f,%.1f", color->n[0], color->n[1], color->n[2], color->n[3]); }
void render_debug_triangle(boolean immediate, real_point3d const *point0,
    real_point3d const *point1, real_point3d const *point2, real_argb_color const *color)
{
    (void)immediate;
    printf("TRI ");
    c4_print_point(point0); printf(" "); c4_print_point(point1); printf(" "); c4_print_point(point2);
    printf(" "); c4_print_color(color); printf("\n");
}
void render_debug_line(boolean immediate, real_point3d const *point0,
    real_point3d const *point1, real_argb_color const *color)
{
    (void)immediate;
    printf("LINE ");
    c4_print_point(point0); printf(" "); c4_print_point(point1);
    printf(" "); c4_print_color(color); printf("\n");
}

/* leaf_map and leaf_portal stand-ins: only the owner blocks read by the spliced body. */
struct leaf_portal { struct tag_block vertices; };
struct leaf_map { struct tag_block portals; };

/* ---- generated verbatim CE bodies and fragments */
#include "c4_extract_ranges.inc"

/* ---- driver */
static long parse_long(const char *text) { return strtol(text, NULL, 0); }

static const char *value_of(int argc, char **argv, const char *key)
{
    size_t n = strlen(key);
    int i;
    for (i = 0; i < argc; ++i)
        if (!strncmp(argv[i], key, n) && argv[i][n] == '=')
            return argv[i] + n + 1;
    return NULL;
}

static long parse_list(const char *text, long *out, long capacity)
{
    long n = 0;
    while (text && *text && n < capacity)
    {
        out[n++] = strtol(text, (char **)&text, 0);
        if (text && *text == ',') text++;
    }
    return n;
}

static void print_surface_flags(long surface_count)
{
    long i;
    printf("count=%ld set=[", render.environment_surface_count);
    for (i = 0; i < surface_count; ++i)
        if (BIT_VECTOR_TEST_FLAG(render.environment_surface_flags, i))
            printf("%ld,", i);
    printf("]\n");
}

/* mode pathbyte: owner block = bytes=<list>; the byte before it is guard=<n>.
 * Prints path_pathfinding_surface(index). */
static int mode_pathbyte(int argc, char **argv)
{
    unsigned char buffer[64];
    long values[63];
    long count, i;
    struct structure_bsp structure;
    count = parse_list(value_of(argc, argv, "bytes"), values, 63);
    memset(buffer, 0, sizeof buffer);
    buffer[0] = (unsigned char)parse_long(value_of(argc, argv, "guard"));
    for (i = 0; i < count; ++i) buffer[1 + i] = (unsigned char)values[i];
    memset(&structure, 0, sizeof structure);
    structure.pathfinding_surfaces.count = count;
    structure.pathfinding_surfaces.address = buffer + 1;
    printf("pathbyte=%d\n", (int)path_pathfinding_surface(&structure,
        parse_long(value_of(argc, argv, "index"))));
    return 0;
}

/* mode broken: surface_is_broken (ai/path.c) on surface 0 with the flags and
 * breakable_surface_index bytes given; bits = breakable flag word 0. */
static int mode_broken(int argc, char **argv)
{
    struct collision_surface surfaces[1];
    struct collision_bsp bsp;
    struct structure_bsp structure;
    memset(surfaces, 0, sizeof surfaces);
    memset(&bsp, 0, sizeof bsp);
    memset(&structure, 0, sizeof structure);
    memset(c4_breakable_words, 0, sizeof c4_breakable_words);
    c4_breakable_words[0] = parse_long(value_of(argc, argv, "bits"));
    surfaces[0].flags = (byte)parse_long(value_of(argc, argv, "flags"));
    surfaces[0].breakable_surface_index = (byte)parse_long(value_of(argc, argv, "breakable_index"));
    bsp.surfaces.count = 1; bsp.surfaces.address = surfaces;
    structure.collision_bsp.count = 1; structure.collision_bsp.address = &bsp;
    printf("broken=%d\n", (int)surface_is_broken(&structure, 0));
    return 0;
}

/* mode subcluster: subcluster surface list=<list>, surfaces=<count>. */
static int mode_subcluster(int argc, char **argv)
{
    long list[256];
    struct structure_bsp structure;
    struct structure_visibility_subcluster subcluster;
    memset(&structure, 0, sizeof structure);
    memset(&render, 0, sizeof render);
    memset(&subcluster, 0, sizeof subcluster);
    subcluster.surface_indices.count = parse_list(value_of(argc, argv, "list"), list, 256);
    subcluster.surface_indices.address = list;
    structure.surfaces.count = parse_long(value_of(argc, argv, "surfaces"));
    c4_subcluster_surface_loop(&structure, &subcluster);
    print_surface_flags(structure.surfaces.count);
    return 0;
}

/* mode cluster: cluster surface list=<list>; lightmaps=<n>; materials=<m0,m1,..>
 * per lightmap; vbytes=<b,..> compressed vertex bytes per (lightmap, material)
 * in row order with 8 slots per lightmap; surfaces=<n>; vertices=<a:b:c,..>. */
static int mode_cluster(int argc, char **argv)
{
    long list[256], counts[8], bytes[64], points[192];
    long lightmaps, surface_total, i, j, count;
    struct structure_lightmap lightmap_array[8];
    struct structure_material material_array[8][8];
    struct structure_visibility_surface surface_array[64];
    struct structure_bsp structure;
    struct structure_visibility_cluster cluster;
    struct render_frustum frustum;
    const char *text;

    memset(&structure, 0, sizeof structure);
    memset(&render, 0, sizeof render);
    memset(surface_array, 0, sizeof surface_array);
    memset(material_array, 0, sizeof material_array);
    memset(lightmap_array, 0, sizeof lightmap_array);
    memset(&cluster, 0, sizeof cluster);

    lightmaps = parse_long(value_of(argc, argv, "lightmaps"));
    count = parse_list(value_of(argc, argv, "materials"), counts, 8);
    (void)count;
    parse_list(value_of(argc, argv, "vbytes"), bytes, 64);
    for (i = 0; i < lightmaps; ++i)
    {
        lightmap_array[i].materials.count = counts[i];
        lightmap_array[i].materials.address = material_array[i];
        for (j = 0; j < counts[i]; ++j)
            material_array[i][j].compressed_vertex_data.size = bytes[i * 8 + j];
    }
    structure.lightmaps.count = lightmaps;
    structure.lightmaps.address = lightmap_array;

    surface_total = parse_long(value_of(argc, argv, "surfaces"));
    count = parse_list(value_of(argc, argv, "vertices"), points, 192);
    for (i = 0; i < surface_total && i * 3 < count; ++i)
        for (j = 0; j < 3; ++j)
            surface_array[i].vertex_indices[j] = (word)points[i * 3 + j];
    structure.surfaces.count = surface_total;
    structure.surfaces.address = surface_array;

    cluster.surface_indices.count = parse_list(value_of(argc, argv, "list"), list, 256);
    cluster.surface_indices.address = list;
    c4_cluster_surface_loop(&structure, &cluster, &frustum);
    print_surface_flags(surface_total);
    printf("match_failures=%ld\n", c4_match_failures);
    return 0;
}

/* mode weather: planes=<nx:ny:nz:d;..>, position px,py,pz. The fragment is the
 * CE polyhedron test; drawn=1 when the particle lies outside the polyhedron. */
static int mode_weather(int argc, char **argv)
{
    real_plane3d planes[16];
    struct structure_weather_polyhedron polyhedron;
    struct structure_bsp structure;
    short indices[1] = {0};
    long plane_count = 0;
    const char *text = value_of(argc, argv, "planes");
    real_point3d position;
    boolean drawn;

    memset(&structure, 0, sizeof structure);
    while (text && *text && plane_count < 16)
    {
        char *end;
        planes[plane_count].n.i = strtof(text, &end); text = end + 1;
        planes[plane_count].n.j = strtof(text, &end); text = end + 1;
        planes[plane_count].n.k = strtof(text, &end); text = end + 1;
        planes[plane_count].d = strtof(text, &end);
        text = end;
        plane_count++;
        if (*text == ';') text++;
    }
    polyhedron.planes.count = plane_count;
    polyhedron.planes.address = planes;
    structure.weather_polyhedra.count = 1;
    structure.weather_polyhedra.address = &polyhedron;
    position.x = strtof(value_of(argc, argv, "px"), NULL);
    position.y = strtof(value_of(argc, argv, "py"), NULL);
    position.z = strtof(value_of(argc, argv, "pz"), NULL);
    drawn = c4_weather_polyhedron_drawn(&structure, 1, indices, position);
    printf("drawn=%d\n", (int)drawn);
    return 0;
}

/* mode leafportal: structure_bsp.leaf_map.portals[0] vertices=<x:y:z,...> (at
 * least three), closed=<0|1> selects the portal designator's closed bit. The CE
 * renderer's debug calls print the vertices and colour they were given. */
static int mode_leafportal(int argc, char **argv)
{
    real_point3d vertices[32];
    struct leaf_portal portal;
    struct leaf_map map;
    struct tag_block portal_block;
    const char *text = value_of(argc, argv, "vertices");
    long closed = parse_long(value_of(argc, argv, "closed"));
    long count = 0;
    char *end;

    global_real_argb_red = &c4_red_color;
    while (text && *text && count < 32)
    {
        vertices[count].x = strtof(text, &end); text = end + 1;
        vertices[count].y = strtof(text, &end); text = end + 1;
        vertices[count].z = strtof(text, &end); text = end;
        count++;
        if (*text == ',') text++;
    }
    memset(&portal, 0, sizeof portal);
    memset(&map, 0, sizeof map);
    portal.vertices.count = count;
    portal.vertices.address = vertices;
    portal_block.count = 1;
    portal_block.address = &portal;
    map.portals = portal_block;
    render_debug_leaf_portal(&map, closed ? (long)LONG_MIN : 0L);
    return 0;
}

int main(int argc, char **argv)
{
    if (argc < 2) return 2;
    argc -= 1;
    argv += 1;
    if (!strcmp(argv[0], "pathbyte")) return mode_pathbyte(argc, argv);
    if (!strcmp(argv[0], "broken")) return mode_broken(argc, argv);
    if (!strcmp(argv[0], "subcluster")) return mode_subcluster(argc, argv);
    if (!strcmp(argv[0], "cluster")) return mode_cluster(argc, argv);
    if (!strcmp(argv[0], "weather")) return mode_weather(argc, argv);
    if (!strcmp(argv[0], "leafportal")) return mode_leafportal(argc, argv);
    return 2;
}
