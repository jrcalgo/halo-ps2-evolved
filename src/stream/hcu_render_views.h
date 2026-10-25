/* C3.5 per-view camera, HUD and first-person selection for the HCU parent renderer.
 *
 * Pure, host-testable part of the C3:views block in src/stream/hcu_main.c. It takes plain floats
 * (the snapshot's view camera, HUD values and flags), never CE or renderer types, so the glue that
 * reads the pinned snapshot bank stays the only place that knows the wire layout.
 *
 * Camera: a snapshot view gives a position and a forward vector (plus up, which is only validated;
 * roll is zero in camera_t). Its vertical field of view is kept and converted to camera_t's horizontal
 * field of view with the view rectangle's own aspect (w/h), so each split view keeps the CE vertical extent. Anything not finite, a zero forward,
 * or a field of view outside (0.1, 2.8) radians is refused, and that view falls back to a fixed
 * camera. Radians are an assumption about the CE producer; the range check makes a degrees value
 * fail closed instead of drawing a wrong view.
 *
 * HUD values (assumed layout, CE does not fill them yet): hud_values[0] health fraction,
 * [1] shield fraction, [2] ammo count, [3] crosshair spread fraction. HUD_VISIBLE gates the
 * health/shield/ammo lines. The crosshair is always drawn.
 *
 * First person: the snapshot's first-person palette count is reported per view. Drawing it needs the
 * object path (hcu_render_objects.h, not present yet), so nothing here draws first-person geometry. */
#ifndef HCU_RENDER_VIEWS_H
#define HCU_RENDER_VIEWS_H

#include <stdint.h>

#define HCU_RENDER_VIEWS_MAX 4u
#define HCU_RENDER_VIEWS_HUD_LINES 3u
#define HCU_RENDER_VIEWS_HUD_CHARS 24u

typedef enum {
	HCU_VIEW_CAMERA_FIXED = 0,
	HCU_VIEW_CAMERA_SNAPSHOT = 1
} hcu_view_camera_source;

/* camera_t-compatible pose in radians (yaw/pitch as camera_basis reads them). */
typedef struct {
	float pos[3];
	float yaw, pitch;
	float hfov;
	float near_z, far_z;
} hcu_view_camera;

typedef struct {
	uint32_t frames;            /* frames planned */
	uint32_t snapshot_views;    /* views whose camera came from the snapshot */
	uint32_t fixed_views;       /* views on a fixed camera */
	uint32_t refused_views;     /* snapshot views refused (camera, flags or generation) */
	uint32_t generation_refusals;
	uint32_t hud_lines;         /* health/shield/ammo lines drawn */
	uint32_t crosshairs;        /* crosshairs drawn */
	uint32_t fp_nodes_seen;     /* first-person nodes the snapshot lists (not drawn) */
	uint32_t fp_drawn;          /* first-person nodes drawn through the object path */
	uint32_t generation;        /* map generation the snapshot views are accepted for */
	int32_t  have_generation;   /* 0 until the first accepted snapshot of a map */
} hcu_views_stats;

/* Converts a snapshot camera (position, forward, vertical fov in radians, the view rectangle's aspect w/h,
 * near/far). Vertical fov is kept; the horizontal fov is derived from the view aspect. Returns 1 when the
 * camera is usable, 0 otherwise (and out is left unchanged). */
int hcu_views_camera_from_snapshot(const float pos[3], const float forward[3], const float up[3],
	float vertical_fov, float view_aspect, float z_near, float z_far, hcu_view_camera *out);

/* Snapshot views are accepted only for one map generation at a time: the first accepted view sets it,
 * a view from another generation is refused. Returns 1 when accepted. */
int hcu_views_accept_generation(hcu_views_stats *s, uint32_t map_generation);

/* Health/shield/ammo lines for one view. hud_flags is the snapshot's HUD flags; with HUD_VISIBLE clear
 * the result is 0 lines. Writes at most HCU_RENDER_VIEWS_HUD_LINES strings of at most
 * HCU_RENDER_VIEWS_HUD_CHARS characters each and returns their count. */
unsigned hcu_views_hud_lines(const float hud_values[4], uint8_t hud_flags,
	char lines[HCU_RENDER_VIEWS_HUD_LINES][HCU_RENDER_VIEWS_HUD_CHARS]);

/* Crosshair gap in buffer pixels, from hud_values[3] (clamped to 0..1, scaled to 0..12). */
int hcu_views_crosshair_gap(const float hud_values[4]);

/* Placeholder marker text for a first-person debug draw: "FP n" with n = the node count. */
void hcu_views_fp_placeholder_text(unsigned nodes, char out[HCU_RENDER_VIEWS_HUD_CHARS]);

#endif
