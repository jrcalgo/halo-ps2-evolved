/*
 * Host-only fail-loud stubs for the two unit camera accessors.
 *
 * CE sound_listener_camera() only calls these when the observer camera has no
 * cluster and a zero position AND the local player owns a unit. The MP host
 * fixtures place their listeners with explicit observer cameras
 * (hcu_test_set_sound_camera_cluster), so the unit branch is not reached.
 * Extracting the real bodies would pull the biped/model graph into the
 * fixtures, so these abort instead of returning an invented position. Any
 * fixture that reaches them is a fixture error and fails loudly.
 */
#include <stdlib.h>

#include "cseries.h"
#include "units/units.h"

void unit_get_camera_position(long unit_index, real_point3d *camera_position)
{
	(void)unit_index;
	(void)camera_position;
	abort();
}

void unit_get_aiming_vector(long unit_index, real_vector3d *aiming_vector)
{
	(void)unit_index;
	(void)aiming_vector;
	abort();
}
