#include "stream/hcu_render_frame.h"

#include <string.h>

int hcu_render_layout_compute(uint32_t view_count, int32_t screen_w, int32_t screen_h,
	hcu_render_layout *out)
{
	int32_t half_w, half_h, rest_w, rest_h;

	if (!out || view_count < 1u || view_count > HCU_RENDER_FRAME_MAX_VIEWS ||
		screen_w < 2 || screen_h < 2)
		return -1;
	memset(out, 0, sizeof(*out));
	out->view_count = view_count;
	half_w = screen_w / 2;
	half_h = screen_h / 2;
	rest_w = screen_w - half_w;
	rest_h = screen_h - half_h;
	switch (view_count) {
	case 1:
		out->views[0] = (hcu_render_rect){ 0, 0, screen_w, screen_h };
		break;
	case 2:
		out->views[0] = (hcu_render_rect){ 0, 0, screen_w, half_h };
		out->views[1] = (hcu_render_rect){ 0, half_h, screen_w, rest_h };
		break;
	case 3:
	case 4:
		out->views[0] = (hcu_render_rect){ 0, 0, half_w, half_h };
		out->views[1] = (hcu_render_rect){ half_w, 0, rest_w, half_h };
		out->views[2] = (hcu_render_rect){ 0, half_h, half_w, rest_h };
		if (view_count == 4u)
			out->views[3] = (hcu_render_rect){ half_w, half_h, rest_w, rest_h };
		else
			out->clear = (hcu_render_rect){ half_w, half_h, rest_w, rest_h };
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
	s->cache_age_advances++;
	s->upload_budget_resets++;
	s->frames_submitted++;
	s->views_rendered += s->open_views;
	s->open_views = 0u;
	return 0;
}
