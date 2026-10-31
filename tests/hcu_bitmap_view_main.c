/* Per-view bitmap placement: CE window -> layout rect (hcu_render_layout_compute), viewport-relative
 * vertices offset into the rect, and the GS scissor (SCISSOR_1) clipped to the same rect. Host only. */
#include "stream/hcu_bitmap_quad.h"
#include "stream/hcu_render_frame.h"
#include "render/gs.h"

#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

static uint8_t section[1184];
static void w16(unsigned o, uint16_t v) { section[o] = (uint8_t)v; section[o + 1] = (uint8_t)(v >> 8); }
static void w32(unsigned o, uint32_t v) { w16(o, (uint16_t)v); w16(o + 2, (uint16_t)(v >> 16)); }

static void make_tex(void)
{
	memset(section, 0, sizeof section); memcpy(section, "TEXS", 4); w16(4, 1);
	w32(8, 1); w32(12, 0); w32(16, 64); w32(20, 96); w32(24, 96); w32(28, sizeof section);
	w32(64, 77); w16(68, 8); w16(70, 8); section[72] = GS_PSMT8; section[73] = 1;
	w32(76, 96); w32(80, 1120); w32(84, 64); w16(88, 256); w32(92, 0x80808080);
}

#define SCREEN_W 640
/* GS A+D address of SCISSOR_1 (same value as hcu_bitmap_quad.c's GS_A_SCISSOR_1). */
#define GS_A_SCISSOR_1_ADDR 0x40u
#define GS_A_XYOFFSET_1_ADDR 0x18u
#define SCREEN_H 480

/* CE viewport-relative quad: a 40x30 box at (10,12) inside a 160x120 viewport. */
static const hcu_bitmap_vertex_t ce_quad[4] = {
	{10.0f, 12.0f, 0.0f, 0.0f, 0x80FFFFFFu}, {50.0f, 12.0f, 1.0f, 0.0f, 0x80FFFFFFu},
	{50.0f, 42.0f, 1.0f, 1.0f, 0x80FFFFFFu}, {10.0f, 42.0f, 0.0f, 1.0f, 0x80FFFFFFu}
};

static int failures;
#define CHECK(cond) do { if (!(cond)) { fprintf(stderr, "FAIL %s:%d: %s\n", __FILE__, __LINE__, #cond); failures++; } } while (0)

static uint32_t gs_coord_expect(float v, int extent)
{
	return (uint32_t)floorf((2048.0f - (float)extent * 0.5f + v) * 16.0f + 0.5f);
}

static int rect_eq(hcu_bitmap_rect a, int32_t x, int32_t y, int32_t w, int32_t h)
{
	return a.x == x && a.y == y && a.w == w && a.h == h;
}

static int rects_overlap(hcu_bitmap_rect a, hcu_bitmap_rect b)
{
	return a.x < b.x + b.w && b.x < a.x + a.w && a.y < b.y + b.h && b.y < a.y + a.h;
}

/* Emit one CE quad for window `window_index` through the same resolve/place/emit path as the
 * dispatcher, then read back the GS scissor and the first vertex's absolute position. */
static int emit_for_window(const hcu_bitmap_view *views, uint32_t view_count, int32_t window_index,
	hcu_bitmap_rect *rect_out, uint64_t *scissor_out, uint32_t *vx_out, uint32_t *vy_out)
{
	uint64_t memory[64 * 2];
	chain_t chain;
	tex_section textures;
	hcu_bitmap_quad_state_t state;
	hcu_bitmap_vertex_t placed[4];
	hcu_bitmap_rect rect;
	uint64_t *q;
	if (hcu_bitmap_view_resolve(views, view_count, window_index, SCREEN_W, SCREEN_H, &rect) != 0) return -1;
	if (rect_out) *rect_out = rect;
	make_tex();
	if (tex_open(&textures, section, sizeof section) != TEX_OK) return -2;
	memset(memory, 0xA5, sizeof memory);
	chain_init(&chain, memory, 64);
	memset(&state, 0, sizeof state);
	state.tex0 = GS_TEX0(10, 1, GS_PSMT8, 3, 3, 1, 0, 30, GS_PSMCT32, 0, 0, 1);
	state.screen_w = SCREEN_W; state.screen_h = SCREEN_H;
	state.clip_w = SCREEN_W; state.clip_h = SCREEN_H;
	state.z = 0x1234; state.blend = HCU_BITMAP_BLEND_ALPHA; state.texture_layers = 1;
	if (hcu_bitmap_quad_place(&state, &rect, ce_quad, placed) != 0) return -3;
	if (hcu_bitmap_quad_emit(&chain, &textures, 0, &state, placed) != HCU_BITMAP_QUAD_OK) return -4;
	q = (uint64_t *)((uint8_t *)memory + 32);
	if (q[13] != GS_A_XYOFFSET_1_ADDR || q[15] != GS_A_SCISSOR_1_ADDR) return -5;
	{
		int xo = (2048 * 16) - SCREEN_W * 8, yo = (2048 * 16) - SCREEN_H * 8;
		uint64_t expect = (uint64_t)(xo & 0xFFFF) | ((uint64_t)(yo & 0xFFFF) << 32);
		if (q[12] != expect) return -6;
	}
	if (scissor_out) *scissor_out = q[14];
	/* Vertex 0 of the two-triangle packet starts at q[18]; its position is q[22]. */
	if (vx_out) *vx_out = (uint32_t)q[22];
	if (vy_out) *vy_out = (uint32_t)(q[22] >> 32);
	return 0;
}

static uint64_t scissor_for(int32_t x, int32_t y, int32_t w, int32_t h)
{
	uint32_t x1 = (uint32_t)x + (uint32_t)w - 1u, y1 = (uint32_t)y + (uint32_t)h - 1u;
	return (uint64_t)x | (uint64_t)x1 << 16 | (uint64_t)y << 32 | (uint64_t)y1 << 48;
}

/* Layout windows: the CE window indices have a gap (console-free indices 0, 2, 3, 5) so the table
 * must be matched by window index, not by array position. */
static const int32_t gap_windows[4] = { 0, 2, 3, 5 };

static void check_views(uint32_t count)
{
	hcu_render_layout layout;
	hcu_bitmap_view views[HCU_BITMAP_MAX_VIEWS];
	uint32_t k;
	CHECK(hcu_render_layout_compute(count, SCREEN_W, SCREEN_H, &layout) == 0);
	for (k = 0; k < count; k++) {
		views[k].window_index = gap_windows[k];
		views[k].rect.x = layout.views[k].x; views[k].rect.y = layout.views[k].y;
		views[k].rect.w = layout.views[k].w; views[k].rect.h = layout.views[k].h;
	}
	for (k = 0; k < count; k++) {
		hcu_bitmap_rect r;
		uint64_t scissor = 0;
		uint32_t vx = 0, vy = 0;
		int32_t expect_x = layout.views[k].x, expect_y = layout.views[k].y;
		CHECK(emit_for_window(views, count, gap_windows[k], &r, &scissor, &vx, &vy) == 0);
		CHECK(rect_eq(r, layout.views[k].x, layout.views[k].y, layout.views[k].w, layout.views[k].h));
		/* Scissor is exactly this view's rectangle. */
		CHECK(scissor == scissor_for(layout.views[k].x, layout.views[k].y, layout.views[k].w, layout.views[k].h));
		/* CE (10,12) is scaled by the pane/screen ratio and offset by the view origin. */
		{
			float sx = (float)layout.views[k].w / SCREEN_W, sy = (float)layout.views[k].h / SCREEN_H;
			float sc = sx < sy ? sx : sy;
			CHECK(vx == gs_coord_expect((float)expect_x + 10.0f * sc, SCREEN_W));
			CHECK(vy == gs_coord_expect((float)expect_y + 12.0f * sc, SCREEN_H));
		}
	}
	/* Each view's CE quad stays inside its own rectangle. */
	for (k = 0; k < count; k++) {
		hcu_bitmap_rect r = views[k].rect;
		CHECK(10 + r.x >= r.x && 50 + r.x <= r.x + r.w);
		CHECK(12 + r.y >= r.y && 42 + r.y <= r.y + r.h);
	}
	/* Views never overlap each other. */
	for (k = 0; k < count; k++)
		for (uint32_t j = k + 1; j < count; j++)
			CHECK(!rects_overlap(views[k].rect, views[j].rect));
}

int main(void)
{
	hcu_render_layout layout;
	hcu_bitmap_view views[HCU_BITMAP_MAX_VIEWS];
	hcu_bitmap_rect r;
	hcu_bitmap_vertex_t out[4];
	hcu_bitmap_quad_state_t state;
	uint32_t n;

	/* 1 to 4 views: each rect, the scissor, and the absolute offset. */
	for (n = 1; n <= 4; n++) check_views(n);

	/* Two-view layout is stacked halves; the four-view layout is the quadrant set. */
	hcu_render_layout_compute(2, SCREEN_W, SCREEN_H, &layout);
	CHECK(layout.views[0].x == 0 && layout.views[0].y == 0 && layout.views[0].w == 640 && layout.views[0].h == 240);
	CHECK(layout.views[1].x == 0 && layout.views[1].y == 240 && layout.views[1].h == 240);

	/* 3-view layout: player 1 is the full-width top half, players 2 and 3 are the bottom quarters; no clear. */
	hcu_render_layout_compute(3, SCREEN_W, SCREEN_H, &layout);
	CHECK(layout.clear.w == 0 && layout.views[0].w == SCREEN_W && layout.views[0].h == 240);
	for (uint32_t k = 0; k < 3; k++) {
		views[k].window_index = gap_windows[k];
		views[k].rect.x = layout.views[k].x; views[k].rect.y = layout.views[k].y;
		views[k].rect.w = layout.views[k].w; views[k].rect.h = layout.views[k].h;
	}
	/* A request addressed to a window with no table entry fails closed (no quad, no target). */
	CHECK(hcu_bitmap_view_resolve(views, 3, 1, SCREEN_W, SCREEN_H, &r) == -1);
	CHECK(hcu_bitmap_view_resolve(views, 3, 5, SCREEN_W, SCREEN_H, &r) == -1); /* window 5 is the 4th, not in a 3-view table */
	/* Window 3 is the third active window, ordinal 2: bottom-right quarter. */
	CHECK(hcu_bitmap_view_resolve(views, 3, 3, SCREEN_W, SCREEN_H, &r) == 0 && rect_eq(r, 320, 240, 320, 240));

	/* Zero views is full-screen placement for single-view producers. */
	CHECK(hcu_bitmap_view_resolve(NULL, 0, 0, SCREEN_W, SCREEN_H, &r) == 0);
	CHECK(rect_eq(r, 0, 0, SCREEN_W, SCREEN_H));
	CHECK(hcu_bitmap_view_resolve(NULL, 0, 0, 0, SCREEN_H, &r) == -1);
	CHECK(hcu_bitmap_view_resolve(views, HCU_BITMAP_MAX_VIEWS + 1u, 0, SCREEN_W, SCREEN_H, &r) == -1);
	CHECK(hcu_bitmap_view_resolve(views, 1, 0, SCREEN_W, SCREEN_H, NULL) == -1);

	/* Placement rejects an empty or off-screen rectangle without touching the state. */
	memset(&state, 0, sizeof state);
	state.screen_w = SCREEN_W; state.screen_h = SCREEN_H; state.clip_w = 7; state.clip_h = 9;
	{
		hcu_bitmap_rect bad[] = { { 0, 0, 0, 10 }, { 0, 0, 10, 0 }, { -1, 0, 10, 10 },
			{ 320, 0, 321, 10 }, { 0, 470, 10, 11 } };
		unsigned i;
		for (i = 0; i < sizeof(bad) / sizeof(bad[0]); i++)
			CHECK(hcu_bitmap_quad_place(&state, &bad[i], ce_quad, out) == -1);
		CHECK(state.clip_w == 7 && state.clip_h == 9);
	}
	/* Full-screen placement is the identity: vertices unchanged, clip equals the screen. */
	{
		hcu_bitmap_rect full = { 0, 0, SCREEN_W, SCREEN_H };
		CHECK(hcu_bitmap_quad_place(&state, &full, ce_quad, out) == 0);
		CHECK(out[0].x == ce_quad[0].x && out[2].y == ce_quad[2].y);
		CHECK(state.clip_x == 0 && state.clip_y == 0 && state.clip_w == SCREEN_W && state.clip_h == SCREEN_H);
	}

	if (failures) {
		fprintf(stderr, "hcu-bitmap-view failures=%d\n", failures);
		return 1;
	}
	printf("HCU_BITMAP_VIEW_OK\n");
	return 0;
}
