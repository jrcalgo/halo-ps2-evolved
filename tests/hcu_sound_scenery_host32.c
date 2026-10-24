/* Exercise the unmodified CE sound-scenery lifecycle callback in isolation. */
#include "cseries.h"
#undef memset
#undef memcmp
#include "objects/objects.h"
#include "objects/object_types.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>

boolean sound_scenery_new(long object_index);
void sound_scenery_delete(long object_index);

static struct object_datum fixture_object;
static unsigned lookup_count;
static long lookup_index;
static unsigned long lookup_type_mask;

void *object_get_and_verify_type(long object_index, unsigned long valid_type_flags)
{
	++lookup_count;
	lookup_index = object_index;
	lookup_type_mask = valid_type_flags;
	return &fixture_object;
}

int main(void)
{
	struct object_datum before;
	const unsigned long original_flags = 0xA5A55A5Au;
	const long object_index = 0x1234;

	memset(&fixture_object, 0x5A, sizeof(fixture_object));
	fixture_object.object.flags = original_flags;
	before = fixture_object;

	assert(sound_scenery_new(object_index));
	assert(lookup_count == 1);
	assert(lookup_index == object_index);
	assert(lookup_type_mask == _object_mask_sound_scenery);
	assert(fixture_object.object.flags ==
		(original_flags | FLAG(_object_shadowless_bit)));
	before.object.flags |= FLAG(_object_shadowless_bit);
	assert(memcmp(&fixture_object, &before, sizeof(before)) == 0);

	/* CE's delete callback is intentionally empty; it must not mutate object
	 * identity/state or trigger any platform audio request. */
	sound_scenery_delete(object_index);
	assert(lookup_count == 1);
	assert(memcmp(&fixture_object, &before, sizeof(before)) == 0);

	printf("ce-sound-scenery lifecycle=passed callback_effect=shadowless audio_request=none\n");
	return 0;
}
