/* Host test for src/stream/hcu_render_frame.{c,h}: layout rules and frame cycle. */
#include "stream/hcu_render_frame.h"

#include <stdio.h>

static int failures;

#define CHECK(cond) do { if (!(cond)) { \
	fprintf(stderr, "FAIL %s:%d: %s\n", __FILE__, __LINE__, #cond); failures++; } } while (0)

static int same(hcu_render_rect a, int32_t x, int32_t y, int32_t w, int32_t h)
{
	return a.x == x && a.y == y && a.w == w && a.h == h;
}

int main(void)
{
	hcu_render_layout l;
	hcu_render_frame_state s;
	uint32_t n;

	CHECK(hcu_render_layout_compute(0, 640, 448, &l) != 0);
	CHECK(hcu_render_layout_compute(5, 640, 448, &l) != 0);
	CHECK(hcu_render_layout_compute(1, 1, 448, &l) != 0);
	CHECK(hcu_render_layout_compute(1, 640, 448, NULL) != 0);

	CHECK(hcu_render_layout_compute(1, 640, 448, &l) == 0);
	CHECK(l.view_count == 1 && same(l.views[0], 0, 0, 640, 448) && l.clear.w == 0);

	/* Split layouts leave a black bar: 4 rows between stacked windows, 4 columns between side-by-side ones. */
	CHECK(hcu_render_layout_compute(2, 640, 448, &l) == 0);
	CHECK(l.view_count == 2 && same(l.views[0], 0, 0, 640, 222) &&
		same(l.views[1], 0, 226, 640, 222) && same(l.clear, 0, 0, 640, 448));

	CHECK(hcu_render_layout_compute(3, 640, 448, &l) == 0);
	CHECK(l.view_count == 3 && same(l.views[0], 0, 0, 640, 222) &&
		same(l.views[1], 0, 226, 318, 222) && same(l.views[2], 322, 226, 318, 222) &&
		same(l.clear, 0, 0, 640, 448));

	CHECK(hcu_render_layout_compute(4, 640, 448, &l) == 0);
	CHECK(l.view_count == 4 && same(l.views[0], 0, 0, 318, 222) && same(l.views[1], 322, 0, 318, 222) &&
		same(l.views[2], 0, 226, 318, 222) && same(l.views[3], 322, 226, 318, 222) &&
		same(l.clear, 0, 0, 640, 448));

	/* The 512x448 frame: 222-row windows, 254-column quarters. */
	CHECK(hcu_render_layout_compute(4, 512, 448, &l) == 0);
	CHECK(same(l.views[0], 0, 0, 254, 222) && same(l.views[3], 258, 226, 254, 222));

	/* A tiny frame keeps no bar and tiles exactly. */
	CHECK(hcu_render_layout_compute(3, 101, 99, &l) == 0);
	CHECK(same(l.views[0], 0, 0, 101, 49) && same(l.views[1], 0, 49, 50, 50) && same(l.views[2], 50, 49, 51, 50));

	/* Windows never overlap each other or leave the frame; a split asks for a black clear first. */
	for (n = 1; n <= 4; ++n) {
		uint32_t i, j;
		CHECK(hcu_render_layout_compute(n, 512, 448, &l) == 0);
		for (i = 0; i < n; ++i) {
			CHECK(l.views[i].x >= 0 && l.views[i].y >= 0 && l.views[i].x + l.views[i].w <= 512 &&
				l.views[i].y + l.views[i].h <= 448);
			for (j = i + 1; j < n; ++j)
				CHECK(l.views[i].x + l.views[i].w <= l.views[j].x || l.views[j].x + l.views[j].w <= l.views[i].x ||
					l.views[i].y + l.views[i].h <= l.views[j].y || l.views[j].y + l.views[j].h <= l.views[i].y);
		}
		CHECK((n > 1) == (l.clear.w > 0));
	}

	hcu_render_frame_reset(&s);
	CHECK(hcu_render_frame_end(&s) != 0);
	CHECK(hcu_render_frame_begin(&s, 4) == 0);
	CHECK(hcu_render_frame_begin(&s, 4) != 0);
	CHECK(hcu_render_frame_end(&s) == 0);
	CHECK(hcu_render_frame_end(&s) != 0);
	for (n = 1; n <= 4; ++n) {
		CHECK(hcu_render_frame_begin(&s, n) == 0);
		CHECK(hcu_render_frame_end(&s) == 0);
	}
	CHECK(s.frames_begun == 5 && s.frames_submitted == 5);
	CHECK(s.views_rendered == 4 + 1 + 2 + 3 + 4);
	CHECK(s.open == 0);

	if (failures) {
		fprintf(stderr, "%d failure(s)\n", failures);
		return 1;
	}
	printf("hcu_render_frame: all checks passed\n");
	return 0;
}
