/* C4 member-exact parity: structure_background_sound_palette_entry.background_sound consumed by CE
 * scenario_location_deafening() (submodules/halo-ce-universal/source/scenario/scenario.c:525-553, the
 * background_sound lookup at 538-548). CE's function body is spliced in verbatim at the marker. The
 * looping sound definition table is a synthetic stub whose flags bit 0 is the only bit CE reads here. */
#include <stdint.h>
#include <stdio.h>
#include <stddef.h>

typedef int boolean;
#define TRUE 1
#define FALSE 0
#define NONE (-1)
#define TEST_FLAG(flags, bit) (((flags) & (1u << (bit))) != 0)
#define VALID_INDEX(index, count) ((index) >= 0 && (index) < (count))

struct tag_block { int32_t count; void *address; uint32_t definition; };
#define TAG_BLOCK_GET_ELEMENT(block, index, type) ((type *)((char *)(block)->address + (index) * sizeof(type)))
struct tag_reference { int32_t index; };

struct structure_background_sound_palette_entry { struct tag_reference background_sound; };
struct structure_cluster { short background_sound_palette_index; };
struct structure_bsp {
    struct tag_block clusters;
    struct tag_block background_sound_palette;
};
struct location { short cluster_index; };
struct looping_sound_definition { unsigned long flags; };

/* Synthetic looping sound definitions: index 0 has bit 0 set, index 1 does not. */
static struct looping_sound_definition looping_definitions[2] = { { 1u }, { 0u } };
static struct looping_sound_definition *looping_sound_definition_get(long index) {
    return &looping_definitions[index];
}

static struct structure_bsp *bsp_global;
static struct structure_bsp *global_structure_bsp_get(void) { return bsp_global; }

/* CE_SCENARIO_LOCATION_DEAFENING */

int main(void) {
    struct structure_background_sound_palette_entry palette[3] = {
        { { 0 } },      /* definition 0: deafening */
        { { 1 } },      /* definition 1: not deafening */
        { { NONE } },   /* no background sound */
    };
    struct structure_cluster clusters[4] = { { 0 }, { 1 }, { 2 }, { 7 } };
    struct structure_bsp bsp;
    struct location location;
    int c;
    int mode;

    for (mode = 0; mode < 3; mode++) {
        struct structure_background_sound_palette_entry local[3];
        for (c = 0; c < 3; c++) local[c] = palette[c];
        if (mode == 1) local[1].background_sound.index = 0; /* entry 1 now names definition 0 */
        if (mode == 2) local[0].background_sound.index = NONE; /* entry 0 now has no sound */
        bsp.clusters.count = 4;
        bsp.clusters.address = clusters;
        bsp.background_sound_palette.count = 3;
        bsp.background_sound_palette.address = local;
        bsp_global = &bsp;
        printf("MODE %d", mode);
        for (c = 0; c < 4; c++) {
            location.cluster_index = (short)c;
            printf(" %d", (int)scenario_location_deafening(&location));
        }
        printf("\n");
    }
    return 0;
}
