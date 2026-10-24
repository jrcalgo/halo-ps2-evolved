/* C3.5 per-view camera, HUD and first-person selection. See hcu_render_views.h. Pure C11 with float
 * math only (no double), so it builds for the EE and for host tests. */
#include "stream/hcu_render_views.h"

#include <math.h>
#include <stdio.h>
#include <string.h>

/* Reference display aspect (camera_init's default); the horizontal field of view is the camera's. */
#define VIEWS_REFERENCE_ASPECT (4.0f / 3.0f)
#define VIEWS_FOV_MIN 0.1f
#define VIEWS_FOV_MAX 2.8f
#define VIEWS_NEAR_DEFAULT 0.05f
#define VIEWS_FAR_DEFAULT 2000.0f

static int finite_f(float v)
{
	return v == v && v < 3.0e38f && v > -3.0e38f;
}

static int finite3(const float v[3])
{
	return finite_f(v[0]) && finite_f(v[1]) && finite_f(v[2]);
}

static float clampf(float v, float lo, float hi)
{
	return v < lo ? lo : (v > hi ? hi : v);
}

int hcu_views_camera_from_snapshot(const float pos[3], const float forward[3], const float up[3],
	float vertical_fov, float z_near, float z_far, hcu_view_camera *out)
{
	float len2, up_len2, len, fx, fy, fz, unit_z;
	float near_z, far_z;

	if (!out || !pos || !forward || !up)
		return 0;
	if (!finite3(pos) || !finite3(forward) || !finite3(up))
		return 0;
	if (!finite_f(vertical_fov) || vertical_fov < VIEWS_FOV_MIN || vertical_fov > VIEWS_FOV_MAX)
		return 0;
	len2 = forward[0] * forward[0] + forward[1] * forward[1] + forward[2] * forward[2];
	if (!finite_f(len2) || len2 < 1.0e-8f)
		return 0;
	/* up must be a real vector and not parallel to forward: a degenerate frame cannot be built. */
	up_len2 = up[0] * up[0] + up[1] * up[1] + up[2] * up[2];
	if (!finite_f(up_len2) || up_len2 < 1.0e-8f)
		return 0;
	if (fabsf(forward[0] * up[0] + forward[1] * up[1] + forward[2] * up[2]) >
		0.999f * sqrtf(len2) * sqrtf(up_len2))
		return 0;
	len = sqrtf(len2);
	fx = forward[0] / len;
	fy = forward[1] / len;
	fz = forward[2] / len;
	unit_z = clampf(fz, -1.0f, 1.0f);
	near_z = (finite_f(z_near) && z_near > 0.0f) ? z_near : VIEWS_NEAR_DEFAULT;
	far_z = (finite_f(z_far) && z_far > near_z) ? z_far : VIEWS_FAR_DEFAULT;

	memcpy(out->pos, pos, sizeof out->pos);
	out->yaw = atan2f(fy, fx);
	out->pitch = asinf(unit_z);
	/* tan(vfov/2) = tan(hfov/2) / aspect, so hfov = 2 atan(tan(vfov/2) * aspect). */
	out->hfov = 2.0f * atanf(tanf(vertical_fov * 0.5f) * VIEWS_REFERENCE_ASPECT);
	out->near_z = near_z;
	out->far_z = far_z;
	return 1;
}

int hcu_views_accept_generation(hcu_views_stats *s, uint32_t map_generation)
{
	if (!s)
		return 0;
	if (!s->have_generation) {
		s->have_generation = 1;
		s->generation = map_generation;
		return 1;
	}
	if (s->generation != map_generation) {
		s->generation_refusals++;
		return 0;
	}
	return 1;
}

static void copy_line(char *dst, const char *src)
{
	size_t n = strlen(src);
	if (n >= HCU_RENDER_VIEWS_HUD_CHARS)
		n = HCU_RENDER_VIEWS_HUD_CHARS - 1u;
	memcpy(dst, src, n);
	dst[n] = '\0';
}

unsigned hcu_views_hud_lines(const float hud_values[4], uint8_t hud_flags,
	char lines[HCU_RENDER_VIEWS_HUD_LINES][HCU_RENDER_VIEWS_HUD_CHARS])
{
	char buf[HCU_RENDER_VIEWS_HUD_CHARS];
	unsigned count = 0;
	int health, shield, ammo;

	if (!hud_values || !lines || !(hud_flags & 0x01u))
		return 0;
	health = (int)(clampf(hud_values[0], 0.0f, 1.0f) * 100.0f + 0.5f);
	shield = (int)(clampf(hud_values[1], 0.0f, 1.0f) * 100.0f + 0.5f);
	ammo = (hud_values[2] == hud_values[2] && hud_values[2] > 0.0f && hud_values[2] < 100000.0f)
		? (int)(hud_values[2] + 0.5f) : 0;
	snprintf(buf, sizeof buf, "HP %d", health);
	copy_line(lines[count++], buf);
	snprintf(buf, sizeof buf, "SH %d", shield);
	copy_line(lines[count++], buf);
	snprintf(buf, sizeof buf, "AMMO %d", ammo);
	copy_line(lines[count++], buf);
	return count;
}

int hcu_views_crosshair_gap(const float hud_values[4])
{
	float spread;
	if (!hud_values)
		return 4;
	spread = hud_values[3] == hud_values[3] ? clampf(hud_values[3], 0.0f, 1.0f) : 0.0f;
	return 4 + (int)(spread * 8.0f + 0.5f);
}

void hcu_views_fp_placeholder_text(unsigned nodes, char out[HCU_RENDER_VIEWS_HUD_CHARS])
{
	char buf[HCU_RENDER_VIEWS_HUD_CHARS];
	snprintf(buf, sizeof buf, "FP %u", nodes);
	copy_line(out, buf);
}
