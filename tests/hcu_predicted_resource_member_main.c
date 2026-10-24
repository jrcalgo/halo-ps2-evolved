#include <stdint.h>
#include <stdio.h>

typedef int boolean;
enum { FALSE = 0, TRUE = 1, _predicted_resource_bitmap = 0, _predicted_resource_sound = 1 };
#define NONE (-1)
#define BITMAP_GROUP_TAG 0x6269746du
#define SOUND_DEFINITION_TAG 0x736e6421u
#define VALID_INDEX(index, count) ((index) >= 0 && (index) < (count))
#define _error_silent 0

struct predicted_resource {
    int16_t type;
    int16_t resource_index;
    int32_t tag_index;
};
struct bitmap_group_stub { struct { int32_t count; } bitmaps; };

static uint32_t mock_group;
static struct bitmap_group_stub mock_bitmap_group;
static uint32_t tag_get_group_tag(int32_t index) {
    (void)index;
    return mock_group;
}
static struct bitmap_group_stub *bitmap_group_get(int32_t index) {
    (void)index;
    return &mock_bitmap_group;
}
static void error(int severity, const char *format, ...) {
    (void)severity;
    (void)format;
}

/* CE_PREDICTED_RESOURCE_VALID */

int main(void) {
    struct predicted_resource item = { _predicted_resource_bitmap, 0, 4 };
    mock_group = BITMAP_GROUP_TAG;
    mock_bitmap_group.bitmaps.count = 3;
    if (!predicted_resource_valid(&item)) return 1;
    item.resource_index = 2;
    if (!predicted_resource_valid(&item)) return 2;
    item.resource_index = 3;
    if (predicted_resource_valid(&item)) return 3;
    item.resource_index = -1;
    if (predicted_resource_valid(&item)) return 4;
    item.resource_index = 0;
    mock_group = SOUND_DEFINITION_TAG;
    if (predicted_resource_valid(&item)) return 5;
    item.type = _predicted_resource_sound;
    if (!predicted_resource_valid(&item)) return 6;
    item.tag_index = NONE;
    if (predicted_resource_valid(&item)) return 7;
    puts("CE predicted-resource type/tag/resource-index validation passed");
    return 0;
}
