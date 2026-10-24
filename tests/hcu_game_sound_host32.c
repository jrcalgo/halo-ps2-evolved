/* Test-only bridge into CE's private sound_source implementation. */
#include "cseries.h"
#include "camera/observer.h"
#include "game/game.h"
#include "physics/collisions.h"
#include "physics/collision_usage.h"
#include "sound/game_sound.h"

static unsigned hcu_fixture_collision_calls;
static boolean hcu_sound_collision_spy(unsigned long flags,
	real_point3d const *point, real_vector3d const *vector,
	long ignore_object_index, struct collision_result *collision);

/* The selected cases are all CE branches which must not request geometry.
 * Interpose only this private test translation unit's call site so zero calls
 * is directly asserted without changing the production collision sources. */
#define collision_test_vector hcu_sound_collision_spy
#include "../submodules/halo-ce-universal/source/sound/game_sound.c"
#undef collision_test_vector

static struct observer_result hcu_fixture_cameras[MAXIMUM_LOCAL_PLAYERS];
static long hcu_fixture_game_time;

/* Share the controlled listener with the package-backed scenario consumer
 * fixture without exposing the private observer storage. */
void hcu_test_set_sound_camera_cluster(short local_player_index,
	short cluster_index, real_point3d const *position)
{
	assert(local_player_index >= 0 && local_player_index < MAXIMUM_LOCAL_PLAYERS);
	assert(position);
	memset(&hcu_fixture_cameras[local_player_index], 0,
		sizeof(hcu_fixture_cameras[local_player_index]));
	hcu_fixture_cameras[local_player_index].location.cluster_index = cluster_index;
	hcu_fixture_cameras[local_player_index].position = *position;
}

struct observer_result const *observer_get_camera(short local_player_index)
{
	assert(local_player_index >= 0 && local_player_index < MAXIMUM_LOCAL_PLAYERS);
	return &hcu_fixture_cameras[local_player_index];
}

long game_time_get(void)
{
	return hcu_fixture_game_time;
}

static boolean hcu_sound_collision_spy(unsigned long flags,
	real_point3d const *point, real_vector3d const *vector,
	long ignore_object_index, struct collision_result *collision)
{
	(void)flags;
	(void)point;
	(void)vector;
	(void)ignore_object_index;
	(void)collision;
	++hcu_fixture_collision_calls;
	return FALSE;
}

void hcu_test_compute_sound_obstruction(
	short camera_cluster,
	short source_cluster,
	long tick,
	real distance,
	real *obstruction,
	real *occlusion,
	unsigned *collision_calls)
{
	struct sound_source source;
	unsigned collision_calls_before = hcu_fixture_collision_calls;

	memset(&hcu_fixture_cameras[0], 0, sizeof(hcu_fixture_cameras[0]));
	memset(&source, 0, sizeof(source));
	hcu_fixture_cameras[0].location.cluster_index = camera_cluster;
	hcu_fixture_cameras[0].position.x = 1.25f;
	hcu_fixture_cameras[0].position.y = 2.5f;
	hcu_fixture_cameras[0].position.z = 3.75f;
	hcu_fixture_game_time = tick;
	source.spatialization_mode = _sound_spatialization_mode_absolute;
	source.location.position.x = 19.0f + (real)tick * 0.125f;
	source.location.position.y = -7.0f;
	source.location.position.z = 4.0f;
	source.location.game_location.cluster_index = source_cluster;
	compute_sound_obstruction(0, &source, distance);
	*obstruction = source.obstruction;
	*occlusion = source.occlusion;
	*collision_calls = hcu_fixture_collision_calls - collision_calls_before;
}

void hcu_test_compute_combined_pas(unsigned long *out_words, size_t word_count)
{
	assert(out_words != NULL);
	assert(word_count <= BIT_VECTOR_SIZE_IN_LONGS(MAXIMUM_CLUSTERS_PER_STRUCTURE));
	compute_combined_pas();
	memcpy(out_words, combined_pas, word_count * sizeof(combined_pas[0]));
}

boolean hcu_test_location_potentially_audible(short cluster_index)
{
	struct location location;
	memset(&location, 0, sizeof(location));
	location.cluster_index = cluster_index;
	return location_potentially_audible(&location);
}
