/*
 * CE sound-scenery placement/lifecycle assertions, driven by the all-MP
 * package-backed host matrix. The wrapper seams intercept only object-pool
 * allocation/type placement; object_new_from_scenario and sound-scenery
 * callbacks are CE implementations.
 */
#include "cseries.h"
#include "objects/objects.h"
#include "objects/object_types.h"
#include "scenario/scenario.h"
#include "scenario/scenario_definitions.h"
#include "sound/sound_scenery.h"
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#include "hcu_mp_sound_scenery_golden.h"

typedef char hcu_sound_scenery_datum_must_be_0x28[
	sizeof(struct scenario_object_datum) == 0x28 ? 1 : -1];
typedef char hcu_sound_scenery_palette_must_be_0x30[
	sizeof(struct scenario_object_palette_entry) == 0x30 ? 1 : -1];

struct object_datum hcu_test_mp_sound_scenery_object;
unsigned hcu_test_mp_sound_scenery_type_lookup_calls;
#define callback_object hcu_test_mp_sound_scenery_object
#define type_lookup_calls hcu_test_mp_sound_scenery_type_lookup_calls
static struct object_placement_data captured_placement;
static const struct scenario_object_datum *expected_placement_datum;
long hcu_test_mp_sound_scenery_current_object = NONE;
static long next_fake_object_index = 0x4000;
static long current_fake_object_index = NONE;
static unsigned object_new_calls;
static unsigned object_place_calls;

/* object_new_from_scenario is CE source; only its allocator boundary is
 * intercepted so package-backed tag data can exercise it without a running
 * object pool or a simulation tick. */
void hcu_test_object_placement_data_new(
	struct object_placement_data *data,
	long definition_index,
	long owner_object_index)
{
	memset(data, 0, sizeof(*data));
	data->definition_index = definition_index;
	data->owner_object_index = owner_object_index;
	data->owner_player_index = NONE;
	data->owner_team_index = NONE;
}

long hcu_test_object_new(struct object_placement_data *data)
{
	assert(data && expected_placement_datum);
	captured_placement = *data;
	object_new_calls++;
	current_fake_object_index = next_fake_object_index++;
	hcu_test_mp_sound_scenery_current_object = current_fake_object_index;
	return current_fake_object_index;
}

void __wrap_object_type_place(
	long object_index,
	struct scenario_object_datum *scenario_object)
{
	assert(object_index == current_fake_object_index);
	assert(scenario_object == expected_placement_datum);
	object_place_calls++;
}

static const struct hcu_mp_sound_scenery_map_golden *golden_for_map(unsigned map_id)
{
	unsigned i;
	for (i = 0; i < HCU_MP_SOUND_SCENERY_MAP_COUNT; ++i)
		if (hcu_mp_sound_scenery_maps[i].map_id == map_id)
			return &hcu_mp_sound_scenery_maps[i];
	return NULL;
}

static const struct hcu_mp_sound_scenery_placement_golden *golden_placement(
	unsigned map_id,
	unsigned placement_index)
{
	unsigned i;
	for (i = 0; i < HCU_MP_SOUND_SCENERY_PLACEMENT_COUNT; ++i)
		if (hcu_mp_sound_scenery_placements[i].map_id == map_id &&
			hcu_mp_sound_scenery_placements[i].placement_index == placement_index)
			return &hcu_mp_sound_scenery_placements[i];
	return NULL;
}

static const struct hcu_mp_sound_scenery_palette_golden *golden_palette(
	unsigned map_id,
	unsigned palette_index)
{
	unsigned i;
	for (i = 0; i < HCU_MP_SOUND_SCENERY_PALETTE_COUNT; ++i)
		if (hcu_mp_sound_scenery_palettes[i].map_id == map_id &&
			hcu_mp_sound_scenery_palettes[i].palette_index == palette_index)
			return &hcu_mp_sound_scenery_palettes[i];
	return NULL;
}

void hcu_test_mp_sound_scenery_placements(unsigned map_id)
{
	unsigned map_new_begin = object_new_calls;
	unsigned map_lookup_begin = type_lookup_calls;
	const struct hcu_mp_sound_scenery_map_golden *map_golden = golden_for_map(map_id);
	struct tag_block *placements;
	struct tag_block *palette;
	unsigned i;
	assert(map_golden && global_scenario);
	placements = &global_scenario->sound_scenery;
	palette = &global_scenario->sound_scenery_palette;
	assert(placements->count == (long)map_golden->placement_count);
	assert(palette->count == (long)map_golden->palette_count);
	assert(placements->count >= 0 && palette->count >= 0);
	if (placements->count)
		assert(placements->address);
	if (palette->count)
		assert(palette->address);

	for (i = 0; i < map_golden->palette_count; ++i)
	{
		const struct hcu_mp_sound_scenery_palette_golden *expected =
			golden_palette(map_id, i);
		struct scenario_object_palette_entry *actual =
			(struct scenario_object_palette_entry *)palette->address + i;
		assert(expected && actual);
		assert(actual->reference.group_tag == expected->group_tag);
		assert((uint32_t)actual->reference.index == expected->reference_index);
		assert(expected->group_tag == (unsigned long)'ssce');
	}

	for (i = 0; i < map_golden->placement_count; ++i)
	{
		const struct hcu_mp_sound_scenery_placement_golden *expected =
			golden_placement(map_id, i);
		struct scenario_object_datum *actual =
			(struct scenario_object_datum *)placements->address + i;
		const struct hcu_mp_sound_scenery_palette_golden *expected_palette;
		struct object_datum before;
		uint32_t words[10];
		long object_index;
		unsigned prior_new = object_new_calls;
		unsigned prior_place = object_place_calls;
		unsigned prior_lookup = type_lookup_calls;
		unsigned long flags_before;
		assert(expected && actual);
		memcpy(words, actual, sizeof(words));
		assert(memcmp(words, expected->raw_words, sizeof(words)) == 0);
		assert(actual->name_index == NONE);
		assert(VALID_INDEX(actual->palette_entry_index, palette->count));
		expected_palette = golden_palette(map_id,
			(unsigned short)actual->palette_entry_index);
		assert(expected_palette && expected_palette->reference_index != 0xFFFFFFFFu);

		/* Execute CE's placement conversion for this exact relocated datum. */
		expected_placement_datum = actual;
		object_index = object_new_from_scenario(actual, palette);
		assert(object_index == current_fake_object_index);
		assert(object_new_calls == prior_new + 1u);
		assert(object_place_calls == prior_place + 1u);
		assert(captured_placement.definition_index ==
			(long)expected_palette->reference_index);
		assert(captured_placement.variant_number == actual->variant_number);
		assert(memcmp(&captured_placement.position, &actual->position,
			sizeof(actual->position)) == 0);

		/* Then run CE's actual sound-scenery new/delete callbacks on the
		 * resulting typed-object boundary. Creation only sets shadowless; delete
		 * is deliberately a no-op and makes no platform sound request. */
		memset(&callback_object, 0x5A, sizeof(callback_object));
		flags_before = callback_object.object.flags;
		before = callback_object;
		assert(sound_scenery_new(object_index));
		assert(type_lookup_calls == prior_lookup + 1u);
		assert(callback_object.object.flags ==
			(flags_before | FLAG(_object_shadowless_bit)));
		before.object.flags |= FLAG(_object_shadowless_bit);
		assert(memcmp(&callback_object, &before, sizeof(before)) == 0);
		sound_scenery_delete(object_index);
		assert(type_lookup_calls == prior_lookup + 1u);
		assert(memcmp(&callback_object, &before, sizeof(before)) == 0);
	}

	printf("mp-sound-scenery map=%u placements=%u palette=%u ce_created=%u "
		"callback_cycles=%u status=passed\n", map_id,
		map_golden->placement_count, map_golden->palette_count,
		object_new_calls - map_new_begin, type_lookup_calls - map_lookup_begin);
}
