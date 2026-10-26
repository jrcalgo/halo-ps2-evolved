#include "halo_ps2_camera_fallback.h"

#include <math.h>
#include <stdio.h>

static int vector_is(const float actual[3], const float expected[3])
{
	return fabsf(actual[0] - expected[0]) < 1e-6f &&
		fabsf(actual[1] - expected[1]) < 1e-6f &&
		fabsf(actual[2] - expected[2]) < 1e-6f;
}

int main(void)
{
	const float body_ground[3] = { 1.0f, 0.0f, 0.0f };
	const float aim_ground[3] = { 0.0f, 1.0f, 0.0f };
	const float control_ground[3] = { 0.0f, 0.0f, 1.0f };
	const float aim_air[3] = { -0.4270736f, 0.9042169f, 0.0f };
	const float control_air[3] = { 0.8673052f, 0.4977768f, 0.0f };
	const float zero[3] = { 0.0f, 0.0f, 0.0f };
	float forward[3];

	/* Grounded FP follows CE control-facing even when body/aim differ. */
	halo_ps2_camera_fallback_select_forward(1, aim_ground,
		control_ground, forward);
	if (!vector_is(forward, control_ground)) return 1;
	if (vector_is(forward, body_ground)) return 2;

	/* Airborne FP reproduces the captured tick-60 divergence and follows control. */
	halo_ps2_camera_fallback_select_forward(1, aim_air,
		control_air, forward);
	if (!vector_is(forward, control_air)) return 3;

	/* Third-person camera fallback keeps the established unit-aim contract. */
	halo_ps2_camera_fallback_select_forward(0, aim_air,
		control_air, forward);
	if (!vector_is(forward, aim_air)) return 4;

	/* A zero native control vector remains zero here; production retains its
	 * existing normalized unit-aim, then body-forward fallback. */
	halo_ps2_camera_fallback_select_forward(1, aim_air, zero, forward);
	if (!vector_is(forward, zero)) return 5;

	return 0;
}
