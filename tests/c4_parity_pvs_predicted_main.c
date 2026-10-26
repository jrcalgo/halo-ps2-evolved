/* C4 member-exact parity: structure_cluster.predicted_resources consumed by CE predicted_resources_precache()
 * (submodules/halo-ce-universal/source/cache/predicted_resources.c, cluster entry at observer.c:1215).
 * CE's precache and validator bodies are spliced in verbatim at the marker. The texture and sound caches
 * are stubs that record what they were asked to precache. */
#include <stdint.h>
#include <stdio.h>
#include <stddef.h>

typedef int boolean;
enum { FALSE = 0, TRUE = 1, _predicted_resource_bitmap = 0, _predicted_resource_sound = 1 };
#define NONE (-1)
#define BITMAP_GROUP_TAG 0x6269746du
#define SOUND_DEFINITION_TAG 0x736e6421u
#define VALID_INDEX(index, count) ((index) >= 0 && (index) < (count))
#define _error_silent 0

struct tag_block { int32_t count; void *address; uint32_t definition; };
#define TAG_BLOCK_GET_ELEMENT(block, index, type) ((type *)((char *)(block)->address + (index) * sizeof(type)))

struct predicted_resource {
    int16_t type;
    int16_t resource_index;
    int32_t tag_index;
};
struct bitmap_data { int32_t id; };
struct bitmap_group_stub { struct { int32_t count; struct bitmap_data *address; } bitmaps; };

#define TAG_COUNT 4
static const uint32_t tag_groups[TAG_COUNT] = {
    BITMAP_GROUP_TAG, SOUND_DEFINITION_TAG, BITMAP_GROUP_TAG, 0x7a7a7a7au
};
static struct bitmap_data bitmap_table0[2] = { { 100 }, { 101 } };
static struct bitmap_data bitmap_table2[1] = { { 200 } };
static struct bitmap_group_stub bitmap_groups[TAG_COUNT] = {
    { { 2, bitmap_table0 } }, { { 0, NULL } }, { { 1, bitmap_table2 } }, { { 0, NULL } }
};

static uint32_t tag_get_group_tag(int32_t index) {
    return (index >= 0 && index < TAG_COUNT) ? tag_groups[index] : 0u;
}
static struct bitmap_group_stub *bitmap_group_get(int32_t index) {
    return &bitmap_groups[index];
}
static void error(int severity, const char *format, ...) {
    (void)severity;
    (void)format;
}

/* Recorded sink calls. */
static int sink_count;
static char sink_log[64][32];
static void record(const char *fmt, long a, long b) {
    if (sink_count < 64) {
        if (b < 0) snprintf(sink_log[sink_count], 32, fmt, a);
        else snprintf(sink_log[sink_count], 32, fmt, a, b);
        sink_count++;
    }
}
struct texture_stub_sink { int unused; };
static void _texture_cache_bitmap_get_hardware_format(struct bitmap_data *bitmap, boolean a, boolean b) {
    (void)a;
    (void)b;
    /* Recover the (group tag, bitmap id) pair the sink was given. */
    record("BITMAP id=%ld", bitmap->id, -1);
}
static void predicted_resources_sound_precache(long sound_definition_index) {
    record("SOUND tag=%ld", sound_definition_index, -1);
}

/* CE_PREDICTED_RESOURCES_FUNCTIONS */

int main(void) {
    struct predicted_resource entries[4] = {
        { _predicted_resource_bitmap, 1, 0 },   /* bitmap group 0, bitmap 1 -> valid */
        { _predicted_resource_sound, 0, 1 },    /* sound definition tag 1 -> valid */
        { _predicted_resource_bitmap, 0, 2 },   /* bitmap group 2, bitmap 0 -> valid */
        { _predicted_resource_bitmap, 5, 2 },   /* bitmap index out of range -> invalid */
    };
    struct tag_block block = { 4, entries, 0 };
    long i;
    int mode;

    for (mode = 0; mode < 4; mode++) {
        struct predicted_resource local[4];
        struct tag_block local_block;
        sink_count = 0;
        for (i = 0; i < 4; i++) local[i] = entries[i];
        local_block = block;
        local_block.address = local;
        if (mode == 1) local[1].tag_index = 0;    /* sound entry names a bitmap group: must not precache */
        if (mode == 2) local[0].tag_index = 2;    /* bitmap entry 1 of group 2 (one bitmap): invalid */
        if (mode == 3) local_block.count = 2;     /* only the first two entries are visited */
        predicted_resources_precache(&local_block);
        printf("MODE %d sinks=%d", mode, sink_count);
        for (i = 0; i < sink_count; i++) printf(" [%s]", sink_log[i]);
        printf("\n");
    }
    return 0;
}
