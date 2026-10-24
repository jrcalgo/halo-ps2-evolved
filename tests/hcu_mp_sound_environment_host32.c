/* Source-backed host probe for CE's multiplayer listener-environment selector. */
#include "cseries.h"
#include "scenario/scenario.h"
#include "structures/structure_bsp_definitions.h"
#include "sound/sound_environment_definitions.h"
#include "game/players.h"
#include "objects/objects.h"
#include "physics/collision_usage.h"
#include "tag_files/tag_groups.h"
#include <math.h>
#include <stdio.h>
#include <string.h>

extern struct structure_bsp *global_structure_bsp;
extern short global_structure_bsp_index;
extern short global_current_collision_user_depth;
void hcu_test_set_sound_camera_cluster(short local_player_index,
	short cluster_index, real_point3d const *position);

static real hcu_clamp_delta(real value, real limit)
{
	if (value < -limit) return -limit;
	if (value > limit) return limit;
	return value;
}

static void hcu_assert_environment_step(
	struct sound_environment_definition const *before,
	struct sound_environment_definition const *target,
	struct sound_environment_definition const *after)
{
	static const real limits[12] = {
		0.03f, 0.03f, 0.3f, 0.1f, 0.03f, 0.03f,
		0.09f, 0.03f, 0.003f, 0.03f, 0.03f, 600.0f,
	};
	const real *before_values = &before->room_intensity;
	const real *target_values = &target->room_intensity;
	const real *after_values = &after->room_intensity;
	unsigned index;
	for (index = 0; index < 12; ++index)
	{
		real expected = before_values[index] + hcu_clamp_delta(
			target_values[index] - before_values[index], limits[index]);
		assert(fabsf(after_values[index] - expected) < 0.0001f);
	}
}

void hcu_test_mp_sound_environment_query(unsigned map_id,
	unsigned bsp_index, unsigned cluster_index, int palette_index,
	long environment_tag, long background_tag, int fog_region,
	int environment_priority, real_point3d const *position)
{
	struct players_globals fixture_players;
	struct players_globals *previous_players = players_globals;
	struct structure_bsp *bsp = global_structure_bsp;
	struct structure_cluster *cluster;
	struct structure_sound_environment_palette_entry *environment_entry;
	struct structure_background_sound_palette_entry *background_entry;
	struct sound_environment_definition *tagged_environment;
	struct sound_environment_definition before;
	struct sound_environment_definition const *selected = NULL;
	long selected_background = NONE;
	boolean crossed_water_boundary = TRUE;
	short collision_depth = global_current_collision_user_depth;
	unsigned local_player;
	unsigned call;

	assert(bsp && bsp_index == (unsigned)global_structure_bsp_index);
	assert(cluster_index < (unsigned)bsp->clusters.count);
	assert(VALID_INDEX(palette_index, bsp->sound_environment_palette.count));
	cluster = TAG_BLOCK_GET_ELEMENT(&bsp->clusters, cluster_index,
		struct structure_cluster);
	if (fog_region == NONE)
	{
		assert(cluster->fog_reference == NONE);
	}
	else
	{
		struct location location;
		assert(position && cluster->fog_reference != NONE);
		location.leaf_index = NONE;
		location.cluster_index = (short)cluster_index;
		location.bonus = 0;
		assert(scenario_get_fog_region_index(&location, position) == fog_region);
	}
	assert(cluster->sound_environment_palette_index == palette_index);
	environment_entry = TAG_BLOCK_GET_ELEMENT(&bsp->sound_environment_palette,
		palette_index, struct structure_sound_environment_palette_entry);
	assert(environment_entry->sound_environment.index == environment_tag);
	assert(environment_tag != NONE);
	tagged_environment = sound_environment_definition_get(environment_tag);
	assert(tagged_environment);
	assert(tagged_environment->priority == environment_priority);
	if (VALID_INDEX(cluster->background_sound_palette_index,
		bsp->background_sound_palette.count))
	{
		background_entry = TAG_BLOCK_GET_ELEMENT(&bsp->background_sound_palette,
			cluster->background_sound_palette_index,
			struct structure_background_sound_palette_entry);
		assert(background_entry->background_sound.index == background_tag);
	}
	else
	{
		assert(background_tag == NONE);
	}

	memset(&fixture_players, 0, sizeof(fixture_players));
	for (local_player = 0; local_player < MAXIMUM_NUMBER_OF_LOCAL_PLAYERS;
		++local_player)
		fixture_players.local_players[local_player] = NONE;
	fixture_players.local_players[0] = 0;
	players_globals = &fixture_players;
	hcu_test_set_sound_camera_cluster(0, (short)cluster_index, position);

	/* Exercise CE's real local-player lookup, listener selector, and tag getter
	 * twice, checking each source-defined interpolation step and stable globals. */
	scenario_globals->sound_environment_initialized = FALSE;
	scenario_globals->sound_environment = default_sound_environment;
	for (call = 0; call < 2; ++call)
	{
		before = scenario_globals->sound_environment;
		selected = NULL;
		selected_background = NONE;
		crossed_water_boundary = TRUE;
		scenario_get_sound_environment(&selected_background, &selected,
			&crossed_water_boundary);
		assert(selected == &scenario_globals->sound_environment);
		assert(!crossed_water_boundary);
		assert(!scenario_globals->sound_environment_initialized);
		assert(selected_background == background_tag);
		hcu_assert_environment_step(&before, tagged_environment, selected);
		assert(global_structure_bsp == bsp);
		assert((unsigned)global_structure_bsp_index == bsp_index);
		assert(global_current_collision_user_depth == collision_depth);
	}
	printf("mp-sound-environment map=%u bsp=%u cluster=%u palette=%d tag=%ld background=%ld fog_region=%d priority=%d calls=2 status=passed\n",
		map_id, bsp_index, cluster_index, palette_index, environment_tag,
		background_tag, fog_region, environment_priority);
	players_globals = previous_players;
}
