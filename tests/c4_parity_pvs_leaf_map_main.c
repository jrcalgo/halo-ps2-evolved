/* C4 member-exact parity: structure_bsp.leaf_map consumed by CE leaf_map_close_portal() and
 * leaf_map_leaf_is_closed() (submodules/halo-ce-universal/source/structures/leaf_map.c:472-530). Both
 * bodies are spliced in verbatim at the marker. match_assert is reduced to a printed failure. */
#include <stdint.h>
#include <stdio.h>
#include <stddef.h>
#include <limits.h>

typedef int boolean;
#define TRUE 1
#define FALSE 0
#define LONG_MAX_VALUE LONG_MAX
#define LONG_MIN_VALUE LONG_MIN
#define LONG_MAX_MASK 0x7fffffffL
#define LONG_MIN_BIT (-2147483647L - 1L)
#define match_assert(file, line, expr) do { if (!(expr)) printf("ASSERT line %d\n", (line)); } while (0)

struct tag_block { int32_t count; void *address; uint32_t definition; };
#define TAG_BLOCK_GET_ELEMENT(block, index, type) ((type *)((char *)(block)->address + (index) * sizeof(type)))

struct map_leaf { struct tag_block portal_designators; };
struct leaf_portal { long plane_index; long leaf_indices[2]; struct tag_block vertices; };
struct leaf_map { const void *bsp; struct tag_block leaves; struct tag_block portals; };

/* Map the CE LONG_MAX / LONG_MIN spellings onto the masks above. */
#undef LONG_MAX
#define LONG_MAX LONG_MAX_MASK
#undef LONG_MIN
#define LONG_MIN LONG_MIN_BIT

/* CE_LEAF_MAP_FUNCTIONS */

static void print_closed(struct leaf_map *map) {
    long leaf;
    for (leaf = 0; leaf < map->leaves.count; leaf++)
        printf(" %d", (int)leaf_map_leaf_is_closed(map, leaf));
    printf("\n");
}

int main(void) {
    struct leaf_portal portals[2];
    struct leaf_map map;
    int mode;

    portals[0].plane_index = 0; portals[0].leaf_indices[0] = 0; portals[0].leaf_indices[1] = 1;
    portals[1].plane_index = 1; portals[1].leaf_indices[0] = 0; portals[1].leaf_indices[1] = 2;

    for (mode = 0; mode < 3; mode++) {
        long d0[2] = { 0, 1 }, d1[1] = { 0 }, d2[1] = { 1 };
        struct map_leaf l[3];
        struct leaf_portal p[2];
        long saved_count = 0;
        l[0].portal_designators.count = 2; l[0].portal_designators.address = d0;
        l[1].portal_designators.count = 1; l[1].portal_designators.address = d1;
        l[2].portal_designators.count = 1; l[2].portal_designators.address = d2;
        p[0] = portals[0]; p[1] = portals[1];
        if (mode == 1) { saved_count = l[1].portal_designators.count; l[1].portal_designators.count = 0; }
        if (mode == 2) p[0].leaf_indices[1] = 2; /* portal 0 now claims leaf 2, which has no designator for it */
        map.bsp = NULL;
        map.leaves.count = 3; map.leaves.address = l;
        map.portals.count = 2; map.portals.address = p;
        printf("MODE %d before", mode);
        print_closed(&map);
        leaf_map_close_portal(&map, 0);
        printf("MODE %d after", mode);
        print_closed(&map);
        if (mode == 1) l[1].portal_designators.count = saved_count;
    }
    return 0;
}
