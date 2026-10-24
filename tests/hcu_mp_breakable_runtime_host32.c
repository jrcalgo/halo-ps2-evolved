/* Test adapter for the real CE breakable-surface state machine.
 * The effect renderer/audio path is intentionally disabled by the caller;
 * this fixture exercises damage vitality, collision flags, and reset only. */
#include <assert.h>
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#include "cseries.h"
#include "hcu_collision_golden.h"
#include "game/game_globals.h"
#include "objects/damage.h"
#include "objects/damage_effect_definitions.h"
#include "physics/breakable_surfaces.h"
#include "physics/collisions.h"
#include "scenario/scenario.h"
#include "saved games/game_state.h"
#include "effects/material_effect_definitions.h"

#define HCU_BREAKABLE_TEST_DAMAGE_INDEX 0x48534231L

static struct damage_effect_definition hcu_breakable_test_damage;
static unsigned char hcu_breakable_state_storage[32768];
static size_t hcu_breakable_state_used;
static boolean hcu_breakable_initialized;
extern boolean breakable_surface_effect_enabled;

void *game_state_malloc(const char *name, const char *type, long size)
{
	uintptr_t aligned;
	(void)name;
	(void)type;
	assert(size >= 0);
	aligned = ((uintptr_t)hcu_breakable_state_storage +
		hcu_breakable_state_used + 15u) & ~(uintptr_t)15u;
	assert(aligned + (uintptr_t)size <=
		(uintptr_t)hcu_breakable_state_storage + sizeof hcu_breakable_state_storage);
	hcu_breakable_state_used = (size_t)(aligned + (uintptr_t)size -
		(uintptr_t)hcu_breakable_state_storage);
	return (void *)aligned;
}

boolean __real_tag_index_is_group(long tag_index, long group_tag);
boolean __wrap_tag_index_is_group(long tag_index, long group_tag)
{
	if (tag_index == HCU_BREAKABLE_TEST_DAMAGE_INDEX &&
		group_tag == DAMAGE_EFFECT_DEFINITION_TAG)
		return TRUE;
	return __real_tag_index_is_group(tag_index, group_tag);
}

void *__real_tag_get(long group_tag, long tag_index);
void *__wrap_tag_get(long group_tag, long tag_index)
{
	if (group_tag == DAMAGE_EFFECT_DEFINITION_TAG &&
		tag_index == HCU_BREAKABLE_TEST_DAMAGE_INDEX)
		return &hcu_breakable_test_damage;
	return __real_tag_get(group_tag, tag_index);
}

void network_coop_note_surface_broken(
	short breakable_surface_index,
	real_point3d const *epicenter)
{
	(void)breakable_surface_index;
	(void)epicenter;
}

void hcu_test_breakable_runtime_begin_map(void)
{
	if (!hcu_breakable_initialized)
	{
		breakable_surfaces_initialize();
		hcu_breakable_initialized = TRUE;
	}
	breakable_surfaces_initialize_for_new_map();
}

static void hcu_breakable_damage_amount(real amount, short material_type)
{
	struct damage_data damage;
	memset(&damage, 0, sizeof damage);
	damage.definition_index = HCU_BREAKABLE_TEST_DAMAGE_INDEX;
	damage.material_type = material_type;
	damage.scale = 1.0f;
	hcu_breakable_test_damage.damage.damage_minimum = amount;
	hcu_breakable_test_damage.damage.damage_lower_bound = amount;
	hcu_breakable_test_damage.damage.damage_upper_bound = amount;
	hcu_breakable_test_damage.damage.material_modifiers[material_type] = 1.0f;
	breakable_surface_damage(1, &damage, 457);
}

void hcu_test_prisoner_breakable_runtime(void)
{
	const hcu_raw_collision_flagged_golden *golden = NULL;
	struct collision_result hit;
	struct collision_result after_break;
	struct collision_result after_reset;
	struct material_definition *material;
	struct breakable_surface_datum *surface;
	real_point3d start;
	real_vector3d vector;
	float maximum_vitality;
	unsigned index;

	assert(global_structure_bsp_index == 0 && global_structure_bsp_get() != NULL);
	for (index = 0; index < HCU_RAW_COLLISION_FLAGGED_GOLDEN_COUNT; ++index)
	{
		const hcu_raw_collision_flagged_golden *candidate =
			&hcu_raw_collision_flagged_goldens[index];
		if (candidate->map_id == 104 && candidate->bsp_index == 0 &&
			candidate->kind == 2)
			golden = candidate;
	}
	assert(golden != NULL && golden->breakable_index == 1);
	start = (real_point3d){golden->start[0], golden->start[1], golden->start[2]};
	vector = (real_vector3d){golden->vector[0], golden->vector[1], golden->vector[2]};
	breakable_surface_effect_enabled = FALSE;
	assert(breakable_surface_extant((short)golden->breakable_index));
	assert(fabsf(breakable_surface_get((short)golden->breakable_index)->vitality - 1.0f) < 1.0e-6f);
	memset(&hit, 0xCD, sizeof hit);
	assert(collision_test_vector(FLAG(_collision_test_structure_bit) |
		FLAG(_collision_test_front_facing_surfaces_bit), &start, &vector,
		NONE, &hit));
	assert(hit.surface_index == golden->surface_index &&
		hit.breakable_surface_index == golden->breakable_index &&
		hit.material_index == golden->material_index);
	material = scenario_material_definition_get(hit.material_type);
	assert(material != NULL);
	maximum_vitality = material->breakable_surface.maximum_vitality;
	assert(maximum_vitality > 0.0f);

	/* A quarter-strength controlled CE damage datum must reduce vitality while
	 * preserving collision; a lethal datum then clears CE's own breakable bit. */
	hcu_breakable_damage_amount(maximum_vitality * 0.25f, hit.material_type);
	surface = breakable_surface_get((short)golden->breakable_index);
	assert(fabsf(surface->vitality - 0.75f) < 0.0002f);
	assert(breakable_surface_extant((short)golden->breakable_index));
	memset(&hit, 0xCD, sizeof hit);
	assert(collision_test_vector(FLAG(_collision_test_structure_bit) |
		FLAG(_collision_test_front_facing_surfaces_bit), &start, &vector,
		NONE, &hit));
	assert(hit.surface_index == golden->surface_index);

	hcu_breakable_damage_amount(maximum_vitality, hit.material_type);
	assert(breakable_surface_get((short)golden->breakable_index)->vitality <= 0.0f);
	assert(!breakable_surface_extant((short)golden->breakable_index));
	memset(&after_break, 0xCD, sizeof after_break);
	assert(!collision_test_vector(FLAG(_collision_test_structure_bit) |
		FLAG(_collision_test_front_facing_surfaces_bit), &start, &vector,
		NONE, &after_break));
	assert(after_break.type == NONE && after_break.t == 1.0f);

	/* Further damage to a broken state is ignored; reset restores vitality and
	 * collision, matching CE's map-reset path. */
	hcu_breakable_damage_amount(maximum_vitality * 100.0f, hit.material_type);
	assert(!breakable_surface_extant((short)golden->breakable_index));
	breakable_surfaces_reset();
	assert(breakable_surface_extant((short)golden->breakable_index));
	assert(fabsf(breakable_surface_get((short)golden->breakable_index)->vitality - 1.0f) < 1.0e-6f);
	memset(&after_reset, 0xCD, sizeof after_reset);
	assert(collision_test_vector(FLAG(_collision_test_structure_bit) |
		FLAG(_collision_test_front_facing_surfaces_bit), &start, &vector,
		NONE, &after_reset));
	assert(after_reset.surface_index == golden->surface_index &&
		after_reset.breakable_surface_index == golden->breakable_index);
	printf("prisoner-breakable-runtime map=104 surface=%d breakable=%d material=%d "
		"vitality=1.0->0.75->broken reset=restored collision=restored "
		"effect_path=disabled status=passed\n",
		golden->surface_index, golden->breakable_index, hit.material_type);
}
