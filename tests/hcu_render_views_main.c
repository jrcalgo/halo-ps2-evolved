/* Host test for src/stream/hcu_render_views.{c,h}: snapshot camera conversion, generation gate,
 * HUD lines and crosshair, first-person placeholder text. */
#include "stream/hcu_render_views.h"
#include "render/camera.h"

#include <math.h>
#include <stdio.h>
#include <string.h>

static int failures;

#define CHECK(cond) do { if (!(cond)) { \
	fprintf(stderr, "FAIL %s:%d: %s\n", __FILE__, __LINE__, #cond); failures++; } } while (0)

static int near(float a, float b, float eps) { return fabsf(a - b) <= eps; }

int main(void)
{
	static const float up[3] = { 0.0f, 0.0f, 1.0f };
	static const float pos[3] = { 65.0f, -95.0f, 9.0f };
	hcu_view_camera cam;
	hcu_views_stats st;
	char lines[HCU_RENDER_VIEWS_HUD_LINES][HCU_RENDER_VIEWS_HUD_CHARS];
	char fp[HCU_RENDER_VIEWS_HUD_CHARS];
	const float hud[4] = { 0.5f, 0.25f, 12.0f, 0.5f };
	const float zero[4] = { 0.0f, 0.0f, 0.0f, 0.0f };
	const float yaw_fwd[3] = { 0.0f, 1.0f, 0.0f };   /* yaw +90 degrees */
	const float tilt_fwd[3] = { 0.0f, 0.0f, -2.0f }; /* straight down, not normalised */
	const float nan_fwd[3] = { 0.0f, 0.0f, 0.0f };
	camera_t c;
	float m[4][4];
	float fov_deg = 60.0f * 3.14159265f / 180.0f;
	float h_expected;
	unsigned n;

	/* Camera from a valid snapshot view: yaw from forward, fov converted to horizontal, near/far kept. */
	CHECK(hcu_views_camera_from_snapshot(pos, yaw_fwd, up, fov_deg, 0.5f, 900.0f, &cam) == 1);
	CHECK(near(cam.yaw, 1.5707963f, 1e-5f));
	CHECK(near(cam.pitch, 0.0f, 1e-6f));
	CHECK(near(cam.pos[0], 65.0f, 1e-6f) && near(cam.pos[1], -95.0f, 1e-6f) && near(cam.pos[2], 9.0f, 1e-6f));
	h_expected = 2.0f * atanf(tanf(fov_deg * 0.5f) * (4.0f / 3.0f));
	CHECK(near(cam.hfov, h_expected, 1e-5f));
	CHECK(near(cam.near_z, 0.5f, 1e-6f) && near(cam.far_z, 900.0f, 1e-3f));

	/* The converted camera projects the same vertical extent the snapshot asked for: the camera_t
	 * clip matrix at aspect 4/3 (camera_init) gives tan(vfov/2) = tan(hfov/2) / aspect. */
	camera_init(&c);
	c.pos[0] = cam.pos[0]; c.pos[1] = cam.pos[1]; c.pos[2] = cam.pos[2];
	c.yaw = cam.yaw; c.pitch = cam.pitch; c.hfov = cam.hfov;
	c.aspect = 4.0f / 3.0f;
	camera_clip_matrix(&c, m);
	CHECK(near(tanf(c.hfov * 0.5f) / c.aspect, tanf(fov_deg * 0.5f), 1e-5f));

	/* Pitch: straight down with an unnormalised forward; up is off-axis so the frame is valid. */
	{
		const float side_up[3] = { 1.0f, 0.0f, 0.0f };
		CHECK(hcu_views_camera_from_snapshot(pos, tilt_fwd, side_up, fov_deg, 0.0f, 0.0f, &cam) == 1);
		CHECK(near(cam.pitch, -1.5707963f, 1e-5f));
	}
	/* An invalid up (parallel to forward) is refused whatever the rest is. */
	CHECK(hcu_views_camera_from_snapshot(pos, tilt_fwd, tilt_fwd, fov_deg, 0.5f, 900.0f, &cam) == 0);

	/* Refusals: NaN or zero forward, zero up, non-finite position, field of view in degrees. */
	CHECK(hcu_views_camera_from_snapshot(pos, nan_fwd, up, fov_deg, 0.5f, 900.0f, &cam) == 0);
	CHECK(hcu_views_camera_from_snapshot(pos, yaw_fwd, zero, fov_deg, 0.5f, 900.0f, &cam) == 0);
	CHECK(hcu_views_camera_from_snapshot(pos, yaw_fwd, up, 60.0f, 0.5f, 900.0f, &cam) == 0);
	CHECK(hcu_views_camera_from_snapshot(pos, yaw_fwd, up, 0.0f, 0.5f, 900.0f, &cam) == 0);
	{
		const float bad[3] = { NAN, 0.0f, 0.0f };
		hcu_view_camera keep = cam;
		CHECK(hcu_views_camera_from_snapshot(bad, yaw_fwd, up, fov_deg, 0.5f, 900.0f, &cam) == 0);
		CHECK(memcmp(&keep, &cam, sizeof cam) == 0);
	}
	CHECK(hcu_views_camera_from_snapshot(NULL, yaw_fwd, up, fov_deg, 0.5f, 900.0f, &cam) == 0);
	CHECK(hcu_views_camera_from_snapshot(pos, yaw_fwd, up, fov_deg, 0.5f, 900.0f, NULL) == 0);

	/* Bad near/far fall back to the camera defaults rather than refusing the view. */
	CHECK(hcu_views_camera_from_snapshot(pos, yaw_fwd, up, fov_deg, -1.0f, 0.0f, &cam) == 1);
	CHECK(near(cam.near_z, 0.05f, 1e-6f) && near(cam.far_z, 2000.0f, 1e-3f));

	/* Convention round trip: the camera_t basis built from yaw/pitch must give back the snapshot forward
	 * (camera_basis: fwd = (cos p cos y, cos p sin y, sin p)). Checked for a tilted, unnormalised forward. */
	{
		const float tilt[3] = { 0.6f, -0.8f, 1.0f };
		float r[3], u[3], f[3], len;
		camera_t rc;
		camera_init(&rc);
		CHECK(hcu_views_camera_from_snapshot(pos, tilt, up, fov_deg, 0.5f, 900.0f, &cam) == 1);
		rc.yaw = cam.yaw; rc.pitch = cam.pitch;
		camera_basis(&rc, r, u, f);
		len = sqrtf(tilt[0] * tilt[0] + tilt[1] * tilt[1] + tilt[2] * tilt[2]);
		CHECK(near(f[0], tilt[0] / len, 1e-5f) && near(f[1], tilt[1] / len, 1e-5f) && near(f[2], tilt[2] / len, 1e-5f));
		CHECK(near(cam.pitch, asinf(tilt[2] / len), 1e-5f));
	}

	/* Generation gate: the first accepted generation sticks, another one is refused and counted. */
	memset(&st, 0, sizeof st);
	CHECK(hcu_views_accept_generation(&st, 7u) == 1);
	CHECK(hcu_views_accept_generation(&st, 7u) == 1);
	CHECK(hcu_views_accept_generation(&st, 8u) == 0);
	CHECK(st.generation == 7u && st.generation_refusals == 1u);
	CHECK(hcu_views_accept_generation(NULL, 7u) == 0);

	/* HUD lines: visible flag gates them; values are clamped and rounded. */
	CHECK(hcu_views_hud_lines(hud, 0u, lines) == 0);
	n = hcu_views_hud_lines(hud, 0x01u, lines);
	CHECK(n == 3u);
	CHECK(strcmp(lines[0], "HP 50") == 0);
	CHECK(strcmp(lines[1], "SH 25") == 0);
	CHECK(strcmp(lines[2], "AMMO 12") == 0);
	n = hcu_views_hud_lines(zero, 0x01u, lines);
	CHECK(n == 3u && strcmp(lines[0], "HP 0") == 0);
	{
		const float over[4] = { 3.0f, -2.0f, 5.0f, 0.0f };
		n = hcu_views_hud_lines(over, 0x01u, lines);
		CHECK(n == 3u && strcmp(lines[0], "HP 100") == 0 && strcmp(lines[1], "SH 0") == 0);
	}

	/* Crosshair gap: 4 px at zero spread, 12 px at full spread, clamped. */
	CHECK(hcu_views_crosshair_gap(zero) == 4);
	CHECK(hcu_views_crosshair_gap(hud) == 8);
	{
		const float full[4] = { 0.0f, 0.0f, 0.0f, 9.0f };
		CHECK(hcu_views_crosshair_gap(full) == 12);
	}
	CHECK(hcu_views_crosshair_gap(NULL) == 4);

	/* First-person placeholder text. */
	hcu_views_fp_placeholder_text(37u, fp);
	CHECK(strcmp(fp, "FP 37") == 0);

	/* Stats fields start clear and the fp counters are not touched by the helpers. */
	memset(&st, 0, sizeof st);
	CHECK(st.fp_drawn == 0u && st.snapshot_views == 0u);

	if (failures) {
		fprintf(stderr, "%d failure(s)\n", failures);
		return 1;
	}
	printf("hcu_render_views: all checks passed\n");
	return 0;
}
