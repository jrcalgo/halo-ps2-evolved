/* C4 narrow consumer probe. Each consumer routine below is spliced in verbatim
 * from the pinned CE source by tests/test_c4_parity_collision_consumers.py
 * (generated .inc files; nothing is retyped). Only the global/runtime reads
 * the routine makes are replaced by host stubs that return the synthetic
 * member values under test. Host ILP32 only. */
#include "cseries/cseries.h"
#include "physics/collision_bsp.h"
#include "physics/collision_bsp_definitions.h"
#include <stdio.h>
#include <string.h>
#include <stdlib.h>

/* cseries.h maps strcmp to csstrcmp, so this body must not call strcmp. */
long csstrcmp(const char *a, const char *b)
{
    while (*a && *a == *b) { a++; b++; }
    return (long)(unsigned char)*a - (long)(unsigned char)*b;
}
#undef strcmp

void error(long type, const char *format, ...) { (void)type; (void)format; }
void display_assert(char *information, char *file, long line, boolean fatal)
{ (void)information; (void)file; (void)line; (void)fatal; }
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

#define MAXIMUM_STRUCTURE_BSPS_PER_SCENARIO_C4 16
#define MAXIMUM_BREAKABLE_SURFACES_PER_MAP_C4 256
#ifndef MAXIMUM_STRUCTURE_BSPS_PER_SCENARIO
#define MAXIMUM_STRUCTURE_BSPS_PER_SCENARIO MAXIMUM_STRUCTURE_BSPS_PER_SCENARIO_C4
#endif
#ifndef MAXIMUM_BREAKABLE_SURFACES_PER_MAP
#define MAXIMUM_BREAKABLE_SURFACES_PER_MAP MAXIMUM_BREAKABLE_SURFACES_PER_MAP_C4
#endif

/* ---- vehicle floor/ceiling: stub for global_structure_bsp_get() ---- */
struct c4_bounds_source { real vehicle_floor; real vehicle_ceiling; };
static struct c4_bounds_source c4_bounds;
struct c4_bounds_source *global_structure_bsp_get(void) { return &c4_bounds; }
struct c4_point { real x, y, z; };
struct c4_vec { real i, j, k; };
struct c4_vehicle {
    struct { struct c4_point position; struct c4_vec translational_velocity; } object;
    struct { real seat_power[1]; } unit;
};

/* ---- breakable flags: stub for breakable_surface_flags_get() ---- */
static long c4_flags[MAXIMUM_BREAKABLE_SURFACES_PER_MAP / 32 + 1];
byte *breakable_surface_flags_get(void) { return (byte *)c4_flags; }
static long global_structure_bsp_index = 0;
static boolean warned_about_breakable_surfaces;
enum { _error_silent = 0 };

/* ---- surface_is_broken (ai/path.c) and breakable extant (physics) ---- */
struct structure_bsp { struct tag_block collision_bsp; };

struct c4_material_breakable { short breakable_surface_index; };

/* items.c:91 defines this flag inside an enum (not in a header). */
enum { _collision_surface_breakable_bit = 3 };

/* ---- compressed vertex (objects/object_lights.c) ---- */
struct c4_material {
    struct tag_block compressed_vertex_data;
    struct tag_block vertices;
};

/* ---- structure_visibility leaf surface-reference loop (verbatim, see .inc) */
struct c4_vis_structure { struct tag_block surface_references; struct tag_block surfaces; };
struct c4_leaf { short surface_reference_count; long first_surface_reference_index; };
static struct { long environment_surface_flags[8]; } render;

#include "c4_extract_consumers.inc"

int main(int argc, char **argv)
{
    if (argc < 2) return 2;
    if (argv[1][0] == 'v' && argv[1][1] == 0 && argc == 7) {
        struct c4_vehicle v;
        memset(&v, 0, sizeof v);
        c4_bounds.vehicle_floor = (real)atof(argv[2]);
        c4_bounds.vehicle_ceiling = (real)atof(argv[3]);
        v.object.position.z = (real)atof(argv[4]);
        v.object.translational_velocity.k = (real)atof(argv[5]);
        v.unit.seat_power[0] = (real)atof(argv[6]);
        c4_vehicle_bounds_clamp(&v);
        printf("vehicle_vz=%.9g\n", (double)v.object.translational_velocity.k);
        return 0;
    }
    if (argv[1][0] == 'm' && argv[1][1] == 0 && argc == 4) {
        short index = (short)atoi(argv[2]);
        memset(c4_flags, 0, sizeof c4_flags);
        c4_flags[0] = strtol(argv[3], NULL, 16);
        struct c4_material_breakable material;
        material.breakable_surface_index = index;
        printf("material_extant=%d\n", c4_material_breakable_gate(&material));
        return 0;
    }
    if (argv[1][0] == 's' && argv[1][1] == 0 && argc == 4) {
        /* argv[2] = breakable index on the surface, argv[3] = flag word */
        struct collision_surface surface;
        struct collision_bsp bsp;
        struct structure_bsp structure;
        struct collision_surface surfaces[1];
        memset(&surface, 0, sizeof surface);
        memset(&bsp, 0, sizeof bsp);
        memset(c4_flags, 0, sizeof c4_flags);
        c4_flags[0] = strtol(argv[3], NULL, 16);
        surface.flags = (byte)(1 << _collision_surface_breakable_bit); /* FLAG(bit) */
        surface.breakable_surface_index = (byte)atoi(argv[2]);
        surfaces[0] = surface;
        bsp.surfaces.count = 1; bsp.surfaces.address = surfaces;
        memset(&structure, 0, sizeof structure);
        structure.collision_bsp.count = 1;
        structure.collision_bsp.address = &bsp;
        printf("surface_broken=%d\n", c4_surface_broken(&structure, 0));
        return 0;
    }
    if (argv[1][0] == 'r' && argv[1][1] == 0 && argc == 5) {
        /* argv[2] = environment flags word, argv[3] = comma list of
         * surface_index values, argv[4] = maximum_count; surfaces.count = 4 */
        struct structure_visibility_surface_reference refs[16];
        struct c4_vis_structure structure;
        struct c4_leaf leaf;
        unsigned long surface_flags[1];
        long out[16];
        short found, i = 0, n = 0;
        char *cursor = argv[3];
        memset(&structure, 0, sizeof structure);
        memset(&leaf, 0, sizeof leaf);
        memset(surface_flags, 0, sizeof surface_flags);
        memset(render.environment_surface_flags, 0, sizeof render.environment_surface_flags);
        render.environment_surface_flags[0] = strtol(argv[2], NULL, 16);
        while (*cursor) {
            refs[n].surface_index = strtol(cursor, &cursor, 10);
            refs[n].bsp3d_node_index = 0;
            n++;
            if (*cursor == ',') cursor++;
        }
        structure.surface_references.count = n;
        structure.surface_references.address = refs;
        structure.surfaces.count = 4;
        leaf.first_surface_reference_index = 0;
        leaf.surface_reference_count = n;
        found = c4_leaf_surface_refs(&structure, &leaf, surface_flags, out, (short)atoi(argv[4]));
        printf("surface_refs=[");
        for (i = 0; i < found; ++i) printf(i ? ",%ld" : "%ld", out[i]);
        printf("] count=%d\n", (int)found);
        return 0;
    }
    if (argv[1][0] == 'x' && argv[1][1] == 0 && argc == 3) {
        /* two synthetic vertex buffers; argv[2] = "A" or "B" selects which
         * one backs compressed_vertex_data, index 1 is read back. */
        static struct environment_vertex_compressed bufA[2] = {{{0,0,0},0,0,0,{0,0}},{{1.f,2.f,3.f},0,0,0,{0,0}}};
        static struct environment_vertex_compressed bufB[2] = {{{0,0,0},0,0,0,{0,0}},{{7.f,8.f,9.f},0,0,0,{0,0}}};
        struct c4_material material;
        struct environment_vertex_compressed const *vertex;
        memset(&material, 0, sizeof material);
        material.compressed_vertex_data.address = argv[2][0] == 'A' ? (void *)bufA : (void *)bufB;
        material.compressed_vertex_data.count = 2;
        vertex = c4_vertex_at(&material, 1);
        printf("vertex_x=%.9g\n", (double)vertex->position.x);
        return 0;
    }
    return 2;
}
