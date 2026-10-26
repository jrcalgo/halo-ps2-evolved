#include <stdio.h>
#include <math.h>
#include "halo_ps2_fp_pose_update.h"
#include "halo_ps2_camera_fov.h"

typedef struct {
	unsigned calls;
	unsigned history[16];
	unsigned next_camera;
} update_state;

static void update(void *context)
{
	update_state *state = (update_state *)context;
	state->history[state->calls++] = state->next_camera;
}

static int ensure(halo_ps2_fp_pose_tracker *tracker, unsigned player, unsigned camera_id,
	update_state *state)
{
	float p[3] = { (float)camera_id, 2.0f, 3.0f };
	float f[3] = { 1.0f, (float)camera_id, 0.0f };
	float u[3] = { 0.0f, 0.0f, 1.0f };
	state->next_camera = camera_id;
	return halo_ps2_fp_pose_update_once(tracker, player, p, f, u, update, state);
}

static int missing_and_begin_failure(void)
{
	halo_ps2_fp_pose_tracker tracker;
	update_state state = { 0 };
	halo_ps2_fp_pose_tracker_reset(&tracker);
	/* No bitmap producer, or preflight/begin fails before any window update. */
	if (ensure(&tracker, 0, 10, &state) != 1 || ensure(&tracker, 1, 11, &state) != 1)
		return 1;
	if (ensure(&tracker, 0, 10, &state) != 0 || ensure(&tracker, 1, 11, &state) != 0)
		return 2;
	return state.calls == 2 ? 0 : 3;
}

static int successful_and_partial_windows(void)
{
	halo_ps2_fp_pose_tracker tracker;
	update_state state = { 0 };
	unsigned i;
	halo_ps2_fp_pose_tracker_reset(&tracker);
	/* The successful bitmap path updates before its per-window callbacks. */
	for (i = 0; i < 2; ++i)
		if (ensure(&tracker, i, 20 + i, &state) != 1) return 1;
	/* Snapshot copies reuse those exact player/camera contexts. */
	for (i = 0; i < 2; ++i)
		if (ensure(&tracker, i, 20 + i, &state) != 0) return 2;
	/* A set_view failure after view 1 still leaves later snapshot views fresh. */
	for (i = 2; i < 4; ++i)
		if (ensure(&tracker, i, 20 + i, &state) != 1) return 3;
	return state.calls == 4 ? 0 : 4;
}

static int duplicate_player_windows(void)
{
	halo_ps2_fp_pose_tracker tracker;
	update_state state = { 0 };
	halo_ps2_fp_pose_tracker_reset(&tracker);
	/* Same local player in two distinct windows: the second bitmap pose replaces
	 * the first in CE storage, so snapshot must rebuild each view's context. */
	if (ensure(&tracker, 0, 30, &state) != 1 || ensure(&tracker, 0, 31, &state) != 1)
		return 1;
	if (ensure(&tracker, 0, 30, &state) != 1 || ensure(&tracker, 0, 31, &state) != 1)
		return 2;
	if (state.calls != 4 || state.history[0] != 30 || state.history[1] != 31 ||
		state.history[2] != 30 || state.history[3] != 31)
		return 3;
	/* Repeated same-camera views are a duplicate pose and reuse one rebuild. */
	halo_ps2_fp_pose_tracker_reset(&tracker);
	state.calls = 0;
	if (ensure(&tracker, 0, 32, &state) != 1 || ensure(&tracker, 0, 32, &state) != 0 ||
		ensure(&tracker, 0, 32, &state) != 0 || state.calls != 1)
		return 4;
	return 0;
}

static int invalid_and_frame_reset(void)
{
	halo_ps2_fp_pose_tracker tracker;
	update_state state = { 0 };
	float v[3] = { 0.0f, 0.0f, 0.0f };
	halo_ps2_fp_pose_tracker_reset(&tracker);
	if (halo_ps2_fp_pose_update_once(&tracker, 4, v, v, v, update, &state) != -1 || state.calls)
		return 1;
	if (ensure(&tracker, 0, 40, &state) != 1) return 2;
	halo_ps2_fp_pose_tracker_reset(&tracker);
	if (ensure(&tracker, 0, 40, &state) != 1 || state.calls != 2) return 3;
	return 0;
}

static int observer_fallback_fov(void)
{
	float pi = 3.14159265358979323846f;
	float tangent50 = tanf(50.0f * pi / 360.0f) * 0.85f;
	float tangent70 = tanf(70.0f * pi / 360.0f) * 0.85f;
	float vertical50 = halo_ps2_camera_vertical_fov_from_adjusted_tangent(tangent50);
	float vertical70 = halo_ps2_camera_vertical_fov_from_adjusted_tangent(tangent70);
	float expected50 = 33.1113879f * pi / 180.0f;
	float expected70 = 48.1102782f * pi / 180.0f;
	return fabsf(vertical50 - expected50) < 1e-5f &&
		fabsf(vertical70 - expected70) < 1e-5f ? 0 : 1;
}

int main(void)
{
	int result;
	if ((result = missing_and_begin_failure()) != 0) return 10 + result;
	if ((result = successful_and_partial_windows()) != 0) return 20 + result;
	if ((result = duplicate_player_windows()) != 0) return 30 + result;
	if ((result = invalid_and_frame_reset()) != 0) return 40 + result;
	if ((result = observer_fallback_fov()) != 0) return 50 + result;
	puts("PS2 first-person pose freshness helper fixture passed");
	return 0;
}
