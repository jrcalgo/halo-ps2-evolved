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

	CHECK(hcu_render_layout_compute(2, 640, 448, &l) == 0);
	CHECK(l.view_count == 2 && same(l.views[0], 0, 0, 640, 224) &&
		same(l.views[1], 0, 224, 640, 224) && l.clear.w == 0);

	CHECK(hcu_render_layout_compute(3, 641, 449, &l) == 0);
	CHECK(l.view_count == 3 && same(l.views[0], 0, 0, 641, 224) &&
		same(l.views[1], 0, 224, 320, 225) && same(l.views[2], 320, 224, 321, 225) &&
		l.clear.w == 0);

	CHECK(hcu_render_layout_compute(4, 640, 448, &l) == 0);
	CHECK(l.view_count == 4 && same(l.views[3], 320, 224, 320, 224) && l.clear.w == 0);

	/* Views must tile the screen without overlap for every count. */
	for (n = 1; n <= 4; ++n) {
		int32_t covered = 0;
		uint32_t i;
		CHECK(hcu_render_layout_compute(n, 640, 448, &l) == 0);
		for (i = 0; i < n; ++i)
			covered += l.views[i].w * l.views[i].h;
		CHECK(covered == 640 * 448);
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
