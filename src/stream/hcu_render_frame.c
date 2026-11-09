#include "stream/hcu_render_frame.h"

#include <string.h>

int hcu_render_layout_compute(uint32_t view_count, int32_t screen_w, int32_t screen_h,
	hcu_render_layout *out)
{
	int32_t half_w, half_h, rest_w, rest_h, gap_x = 0, gap_y = 0;

	if (!out || view_count < 1u || view_count > HCU_RENDER_FRAME_MAX_VIEWS ||
		screen_w < 2 || screen_h < 2)
		return -1;
	memset(out, 0, sizeof(*out));
	out->view_count = view_count;
	half_w = screen_w / 2;
	half_h = screen_h / 2;
	rest_w = screen_w - half_w;
	rest_h = screen_h - half_h;
	/* Halo CE insets each split window's safe frame 4 pixels at every edge it shares with another window
	 * (compute_window_bounds, safe_frame_inset), which leaves a thin black bar between windows: 8 of 480 rows,
	 * 8 of 640 columns. The bar here is thinner than CE's: 4 rows by 4 columns of this 512x448 frame. Tiny frames keep no bar. */
	if (screen_w >= HCU_RENDER_SPLIT_MIN_SIZE && screen_h >= HCU_RENDER_SPLIT_MIN_SIZE) {
		gap_y = HCU_RENDER_SPLIT_GAP_Y / 2;
		gap_x = HCU_RENDER_SPLIT_GAP_X / 2;
	}
	/* The bar between windows is whatever the frame is cleared to before the windows draw, so split layouts ask
	 * for a full-frame clear first. */
	if (view_count > 1u)
		out->clear = (hcu_render_rect){ 0, 0, screen_w, screen_h };
	switch (view_count) {
	case 1:
		out->views[0] = (hcu_render_rect){ 0, 0, screen_w, screen_h };
		break;
	case 2:
		out->views[0] = (hcu_render_rect){ 0, 0, screen_w, half_h - gap_y };
		out->views[1] = (hcu_render_rect){ 0, half_h + gap_y, screen_w, rest_h - gap_y };
		break;
	case 3:
		/* Player 1 takes the full-width top half; players 2 and 3 take the bottom quarters. */
		out->views[0] = (hcu_render_rect){ 0, 0, screen_w, half_h - gap_y };
		out->views[1] = (hcu_render_rect){ 0, half_h + gap_y, half_w - gap_x, rest_h - gap_y };
		out->views[2] = (hcu_render_rect){ half_w + gap_x, half_h + gap_y, rest_w - gap_x, rest_h - gap_y };
		break;
	case 4:
		out->views[0] = (hcu_render_rect){ 0, 0, half_w - gap_x, half_h - gap_y };
		out->views[1] = (hcu_render_rect){ half_w + gap_x, 0, rest_w - gap_x, half_h - gap_y };
		out->views[2] = (hcu_render_rect){ 0, half_h + gap_y, half_w - gap_x, rest_h - gap_y };
		out->views[3] = (hcu_render_rect){ half_w + gap_x, half_h + gap_y, rest_w - gap_x, rest_h - gap_y };
		break;
	}
	return 0;
}

void hcu_render_frame_reset(hcu_render_frame_state *s)
{
	if (s)
		memset(s, 0, sizeof(*s));
}

int hcu_render_frame_begin(hcu_render_frame_state *s, uint32_t view_count)
{
	if (!s || s->open || view_count < 1u || view_count > HCU_RENDER_FRAME_MAX_VIEWS)
		return -1;
	s->open = 1u;
	s->open_views = view_count;
	s->frames_begun++;
	return 0;
}

int hcu_render_frame_end(hcu_render_frame_state *s)
{
	if (!s || !s->open)
		return -1;
	s->open = 0u;
	s->frames_submitted++;
	s->views_rendered += s->open_views;
	s->open_views = 0u;
	return 0;
}
