/* C4 member-exact parity: predicted_resource.tag_index consumed by CE predicted_resource_valid().
 * The tag table is keyed by tag_index so each tag_index value selects its own group tag and
 * bitmap count. CE's real validator body is spliced in at the marker by the pytest wrapper. */
#include <stdint.h>
#include <stdio.h>

typedef int boolean;
enum { FALSE = 0, TRUE = 1, _predicted_resource_bitmap = 0, _predicted_resource_sound = 1 };
#define NONE (-1)
#define BITMAP_GROUP_TAG 0x6269746du
#define SOUND_DEFINITION_TAG 0x736e6421u
#define VALID_INDEX(index, count) ((index) >= 0 && (index) < (count))
#define _error_silent 0
#define TAG_COUNT 4

struct predicted_resource {
    int16_t type;
    int16_t resource_index;
    int32_t tag_index;
};
struct bitmap_group_stub { struct { int32_t count; } bitmaps; };

/* Synthetic tag table: index 0 bitmap group with 3 bitmaps, 1 sound definition,
 * 2 bitmap group with 1 bitmap, 3 unknown group. */
static const uint32_t tag_groups[TAG_COUNT] = {
    BITMAP_GROUP_TAG, SOUND_DEFINITION_TAG, BITMAP_GROUP_TAG, 0x7a7a7a7au
};
static struct bitmap_group_stub bitmap_groups[TAG_COUNT] = {
    { { 3 } }, { { 0 } }, { { 1 } }, { { 0 } }
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
static void predicted_resources_sound_precache(int32_t index) {
    (void)index;
}

/* CE_PREDICTED_RESOURCE_VALID */

static int expect(const char *label, struct predicted_resource *item, boolean want) {
    boolean got = predicted_resource_valid(item);
    printf("%s tag=%d type=%d valid=%d\n", label, (int)item->tag_index, (int)item->type, (int)got);
    return got == want ? 0 : 1;
}

int main(void) {
    struct predicted_resource bitmap = { _predicted_resource_bitmap, 0, 0 };
    struct predicted_resource sound = { _predicted_resource_sound, 0, 1 };
    struct predicted_resource wrong_group = { _predicted_resource_bitmap, 0, 1 };
    struct predicted_resource unknown = { _predicted_resource_bitmap, 0, 3 };
    struct predicted_resource out_of_range = { _predicted_resource_bitmap, 0, 4 };
    struct predicted_resource none = { _predicted_resource_bitmap, 0, NONE };
    struct predicted_resource bitmap2 = { _predicted_resource_bitmap, 0, 2 };
    int failures = 0;

    failures += expect("bitmap tag 0", &bitmap, TRUE);
    failures += expect("sound tag 1", &sound, TRUE);
    failures += expect("bitmap type on sound tag 1", &wrong_group, FALSE);
    failures += expect("unknown group tag 3", &unknown, FALSE);
    failures += expect("out-of-range tag 4", &out_of_range, FALSE);
    failures += expect("NONE tag", &none, FALSE);
    failures += expect("bitmap tag 2 (one bitmap)", &bitmap2, TRUE);
    /* Member-exact: changing only tag_index flips the result exactly as the table dictates. */
    bitmap2.resource_index = 1;
    failures += expect("bitmap tag 2 resource_index 1 (past count)", &bitmap2, FALSE);
    bitmap2.resource_index = 0;
    bitmap2.tag_index = 0;
    failures += expect("bitmap tag 0 resource_index 0 again", &bitmap2, TRUE);
    if (failures) {
        printf("tag_index parity failures=%d\n", failures);
        return 1;
    }
    puts("C4 predicted_resource.tag_index parity passed");
    return 0;
}
