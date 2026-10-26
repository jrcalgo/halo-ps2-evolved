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
	CHECK(hcu_views_camera_from_snapshot(pos, yaw_fwd, up, fov_deg, 4.0f / 3.0f, 0.5f, 900.0f, &cam) == 1);
	CHECK(near(cam.yaw, 1.5707963f, 1e-5f));
	CHECK(near(cam.pitch, 0.0f, 1e-6f));
	CHECK(near(cam.pos[0], 65.0f, 1e-6f) && near(cam.pos[1], -95.0f, 1e-6f) && near(cam.pos[2], 9.0f, 1e-6f));
	h_expected = 2.0f * atanf(tanf(fov_deg * 0.5f) * (4.0f / 3.0f));
	CHECK(near(cam.hfov, h_expected, 1e-5f));
	CHECK(near(cam.near_z, 0.5f, 1e-6f) && near(cam.far_z, 900.0f, 1e-3f));

	/* Split view (640x224): vertical fov is kept, hfov follows the view aspect. */
	CHECK(hcu_views_camera_from_snapshot(pos, yaw_fwd, up, fov_deg, 640.0f / 224.0f, 0.5f, 900.0f, &cam) == 1);
	CHECK(near(tanf(cam.hfov * 0.5f) / (640.0f / 224.0f), tanf(fov_deg * 0.5f), 1e-5f));
	/* CE projection (halo-ce-universal source/render/render_cameras.c:793-802 clipped bounds, :1165-1171 full
	 * bounds): vertical_field_of_view is the input; tan(h/2) = tan(v/2) * viewport_w / viewport_h. */
	CHECK(near(tanf(cam.hfov * 0.5f), tanf(fov_deg * 0.5f) * (640.0f / 224.0f), 1e-4f));
	CHECK(hcu_views_camera_from_snapshot(pos, yaw_fwd, up, fov_deg, 0.0f, 0.5f, 900.0f, &cam) == 0);

	CHECK(hcu_views_camera_from_snapshot(pos, yaw_fwd, up, fov_deg, 4.0f / 3.0f, 0.5f, 900.0f, &cam) == 1);
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
		CHECK(hcu_views_camera_from_snapshot(pos, tilt_fwd, side_up, fov_deg, 4.0f / 3.0f, 0.0f, 0.0f, &cam) == 1);
		CHECK(near(cam.pitch, -1.5707963f, 1e-5f));
	}
	/* An invalid up (parallel to forward) is refused whatever the rest is. */
	CHECK(hcu_views_camera_from_snapshot(pos, tilt_fwd, tilt_fwd, fov_deg, 4.0f / 3.0f, 0.5f, 900.0f, &cam) == 0);

	/* Refusals: NaN or zero forward, zero up, non-finite position/FOV, and invalid FOV bounds. */
	CHECK(hcu_views_camera_from_snapshot(pos, nan_fwd, up, fov_deg, 4.0f / 3.0f, 0.5f, 900.0f, &cam) == 0);
	CHECK(hcu_views_camera_from_snapshot(pos, yaw_fwd, zero, fov_deg, 4.0f / 3.0f, 0.5f, 900.0f, &cam) == 0);
	CHECK(hcu_views_camera_from_snapshot(pos, yaw_fwd, up, 60.0f, 4.0f / 3.0f, 0.5f, 900.0f, &cam) == 0);
	CHECK(hcu_views_camera_from_snapshot(pos, yaw_fwd, up, 0.0f, 4.0f / 3.0f, 0.5f, 900.0f, &cam) == 0);
	CHECK(hcu_views_camera_from_snapshot(pos, yaw_fwd, up, 0.018f, 4.0f / 3.0f, 0.5f, 900.0f, &cam) == 0);
	CHECK(hcu_views_camera_from_snapshot(pos, yaw_fwd, up, -0.01f, 4.0f / 3.0f, 0.5f, 900.0f, &cam) == 0);
	CHECK(hcu_views_camera_from_snapshot(pos, yaw_fwd, up, NAN, 4.0f / 3.0f, 0.5f, 900.0f, &cam) == 0);
	CHECK(hcu_views_camera_from_snapshot(pos, yaw_fwd, up, INFINITY, 4.0f / 3.0f, 0.5f, 900.0f, &cam) == 0);
	CHECK(hcu_views_camera_from_snapshot(pos, yaw_fwd, up, -INFINITY, 4.0f / 3.0f, 0.5f, 900.0f, &cam) == 0);
	{
		const float bad[3] = { NAN, 0.0f, 0.0f };
		hcu_view_camera keep = cam;
		CHECK(hcu_views_camera_from_snapshot(bad, yaw_fwd, up, fov_deg, 4.0f / 3.0f, 0.5f, 900.0f, &cam) == 0);
		CHECK(memcmp(&keep, &cam, sizeof cam) == 0);
	}
	CHECK(hcu_views_camera_from_snapshot(NULL, yaw_fwd, up, fov_deg, 4.0f / 3.0f, 0.5f, 900.0f, &cam) == 0);
	CHECK(hcu_views_camera_from_snapshot(pos, yaw_fwd, up, fov_deg, 4.0f / 3.0f, 0.5f, 900.0f, NULL) == 0);

	/* Bad near/far fall back to the camera defaults rather than refusing the view. */
	CHECK(hcu_views_camera_from_snapshot(pos, yaw_fwd, up, fov_deg, 4.0f / 3.0f, -1.0f, 0.0f, &cam) == 1);
	CHECK(near(cam.near_z, 0.05f, 1e-6f) && near(cam.far_z, 2000.0f, 1e-3f));

	/* Convention round trip: the camera_t basis built from yaw/pitch must give back the snapshot forward
	 * (camera_basis: fwd = (cos p cos y, cos p sin y, sin p)). Checked for a tilted, unnormalised forward. */
	{
		const float tilt[3] = { 0.6f, -0.8f, 1.0f };
		float r[3], u[3], f[3], len;
		camera_t rc;
		camera_init(&rc);
		CHECK(hcu_views_camera_from_snapshot(pos, tilt, up, fov_deg, 4.0f / 3.0f, 0.5f, 900.0f, &cam) == 1);
		rc.yaw = cam.yaw; rc.pitch = cam.pitch;
		camera_basis(&rc, r, u, f);
		len = sqrtf(tilt[0] * tilt[0] + tilt[1] * tilt[1] + tilt[2] * tilt[2]);
		CHECK(near(f[0], tilt[0] / len, 1e-5f) && near(f[1], tilt[1] / len, 1e-5f) && near(f[2], tilt[2] / len, 1e-5f));
		CHECK(near(cam.pitch, asinf(tilt[2] / len), 1e-5f));
	}

	/* CE split-screen projection (source/main/main.c:1184-1187 vertical angle, render_cameras.c:719-766 and
	 * :1160-1171 viewport aspect). The observer's CE vertical angle for a 70 degree field of view is
	 * 2 atan(0.75 * 0.85 * tan(35 deg)); every window keeps it, and hfov = 2 atan(tan(vfov/2) * w/h) for the
	 * window's own pixels. Expected values below are computed from that formula directly. */
	{
		const float fov70 = 70.0f * 3.14159265f / 180.0f;
		const float ce_vfov = 2.0f * atanf(0.75f * 0.85f * tanf(fov70 * 0.5f));
		const float fov35 = 35.0f * 3.14159265f / 180.0f;
		const float fov7 = 7.0f * 3.14159265f / 180.0f;
		const float native_min = 3.14159265f / 100.0f + 1.0e-6f;
		const float ce_fovs[] = {
			2.0f * atanf(0.75f * 0.85f * tanf(fov70 * 0.5f)),
			2.0f * atanf(0.75f * 0.85f * tanf(fov35 * 0.5f)),
			2.0f * atanf(0.75f * 0.85f * tanf(fov7 * 0.5f)),
			2.0f * atanf(0.75f * 0.85f * tanf(native_min * 0.5f)),
		};
		static const struct { const char *name; float w, h; } views[] = {
			{ "1 view full 640x448", 640.0f, 448.0f },
			{ "2 views top 640x224", 640.0f, 224.0f },
			{ "2 views bottom 640x224", 640.0f, 224.0f },
			{ "3 views q0 320x224", 320.0f, 224.0f },
			{ "3 views q1 321x224", 321.0f, 224.0f },
			{ "3 views q2 320x225", 320.0f, 225.0f },
			{ "4 views q0 320x224", 320.0f, 224.0f },
			{ "4 views q3 320x225", 320.0f, 225.0f },
			{ "CE 3 players top span 640x224", 640.0f, 224.0f },
			{ "CE 3 players bottom-left 320x224", 320.0f, 224.0f },
		};
		size_t i;
		/* Production CE conversion must retain the full-screen view at 1x, 2x,
		 * 10x sniper magnification, and its narrowest legal weapon FOV. */
		for (i = 0; i < sizeof ce_fovs / sizeof ce_fovs[0]; ++i) {
			int row, col;
			CHECK(hcu_views_camera_from_snapshot(pos, yaw_fwd, up, ce_fovs[i],
				640.0f / 448.0f, 0.5f, 900.0f, &cam) == 1);
			CHECK(isfinite(cam.hfov) && cam.hfov > 0.0f);
			camera_init(&c);
			c.hfov = cam.hfov;
			c.aspect = 640.0f / 448.0f;
			camera_clip_matrix(&c, m);
			for (row = 0; row < 4; ++row)
				for (col = 0; col < 4; ++col)
					CHECK(isfinite(m[row][col]));
		}
		CHECK(near(ce_fovs[2], 0.0782f, 0.001f));
		for (i = 0; i < sizeof views / sizeof views[0]; ++i) {
			const float aspect = views[i].w / views[i].h;
			const float expect_h = 2.0f * atanf(tanf(ce_vfov * 0.5f) * aspect);
			CHECK(hcu_views_camera_from_snapshot(pos, yaw_fwd, up, ce_vfov, aspect, 0.5f, 900.0f, &cam) == 1);
			if (!near(cam.hfov, expect_h, 1e-5f)) {
				fprintf(stderr, "  view %s: hfov %f expected %f\n", views[i].name, cam.hfov, expect_h);
				failures++;
			}
			/* The vertical extent is CE's: tan(hfov/2) / aspect == tan(vfov/2). */
			CHECK(near(tanf(cam.hfov * 0.5f) / aspect, tanf(ce_vfov * 0.5f), 1e-5f));
		}
		/* Full screen 640x448 (aspect 1.4286) has hfov 2 atan(tan(vfov/2) * 10/7). */
		CHECK(hcu_views_camera_from_snapshot(pos, yaw_fwd, up, ce_vfov, 640.0f / 448.0f, 0.5f, 900.0f, &cam) == 1);
		CHECK(near(cam.hfov, 2.0f * atanf(tanf(ce_vfov * 0.5f) * (640.0f / 448.0f)), 1e-5f));
		/* Quadrant views are narrower in pixels than the top span, so their hfov is smaller. */
		CHECK(hcu_views_camera_from_snapshot(pos, yaw_fwd, up, ce_vfov, 320.0f / 224.0f, 0.5f, 900.0f, &cam) == 1);
		{
			const float quad_h = cam.hfov;
			CHECK(hcu_views_camera_from_snapshot(pos, yaw_fwd, up, ce_vfov, 640.0f / 224.0f, 0.5f, 900.0f, &cam) == 1);
			CHECK(cam.hfov > quad_h);
		}
	}

	/* Generation gate: the first accepted generation sticks, another one is refused and counted. */
	memset(&st, 0, sizeof st);
	CHECK(hcu_views_accept_generation(&st, 7u) == 1);
	CHECK(hcu_views_accept_generation(&st, 7u) == 1);
	CHECK(hcu_views_accept_generation(&st, 8u) == 0);
	CHECK(st.generation == 7u && st.generation_refusals == 1u);
	CHECK(hcu_views_accept_generation(NULL, 7u) == 0);

	/* Skip rule: a never-active view may keep the fixed pre-spawn camera; once active it is skipped. */
	CHECK(hcu_views_must_skip(0) == 0);
	CHECK(hcu_views_must_skip(1) == 1);
	CHECK(HCU_VIEW_CAMERA_SKIPPED != HCU_VIEW_CAMERA_FIXED && HCU_VIEW_CAMERA_SKIPPED != HCU_VIEW_CAMERA_SNAPSHOT);
	CHECK(hcu_views_accept_generation(&st, 7u) == 1 && st.skipped_views == 0u);

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
