/* C3.4/C3.5 one-frame view layout for the HCU parent renderer.
 * Pure host-testable state: viewport rectangles for 1-4 local views, the unused
 * quadrant clear rule for 3 views, and a begin/end cycle that counts one submit
 * per frame. Renderer binding (chains, indexes, workspaces) is not done here. */
#ifndef HCU_RENDER_FRAME_H
#define HCU_RENDER_FRAME_H

#include <stdint.h>

#define HCU_RENDER_FRAME_MAX_VIEWS 4u

typedef struct {
	int32_t x, y, w, h;
} hcu_render_rect;

typedef struct {
	uint32_t view_count;
	hcu_render_rect views[HCU_RENDER_FRAME_MAX_VIEWS];
	/* Quadrant clear rectangle for the unused quadrant of a 3-view frame (w == 0 when none). */
	hcu_render_rect clear;
} hcu_render_layout;

/* Full screen for 1 view, horizontal halves (stacked) for 2, quadrants for 3 or 4.
 * Returns 0 and fills out on success; -1 for view_count outside 1..4 or a screen
 * too small to split (each half/quadrant needs at least 1 pixel). */
int hcu_render_layout_compute(uint32_t view_count, int32_t screen_w, int32_t screen_h,
	hcu_render_layout *out);

typedef struct {
	uint32_t frames_begun;
	uint32_t frames_submitted;
	uint32_t views_rendered;         /* sum of view counts over submitted frames */
	uint32_t open;                   /* 1 between begin and end */
	uint32_t open_views;
} hcu_render_frame_state;

void hcu_render_frame_reset(hcu_render_frame_state *s);
/* Starts a frame; fails (-1) if one is already open or the view count is invalid. */
int hcu_render_frame_begin(hcu_render_frame_state *s, uint32_t view_count);
/* Ends the open frame and counts one submit. The cache-age advance and upload-budget reset are NOT counted
 * here: the renderer counts them at its own frame start (bsp_render_frame_counters). Fails (-1) when no frame
 * is open. */
int hcu_render_frame_end(hcu_render_frame_state *s);

#endif
