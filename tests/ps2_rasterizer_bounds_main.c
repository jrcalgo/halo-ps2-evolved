#include <stdio.h>
#include "ps2_rasterizer_bounds.h"

static int equal(struct ps2_rasterizer_rect a, short x0, short y0,
	short x1, short y1)
{
	return a.x0 == x0 && a.y0 == y0 && a.x1 == x1 && a.y1 == y1;
}

int main(void)
{
	struct ps2_rasterizer_rect screen = { 11, 12, 13, 14 };
	struct ps2_rasterizer_rect frame = { 21, 22, 23, 24 };
	if (!ps2_rasterizer_calculate_bounds(512, 448, &screen, &frame) ||
		!equal(screen, 0, 0, 512, 448) ||
		!equal(frame, 38, 33, 474, 415))
		return 1;
	if (!ps2_rasterizer_calculate_bounds(640, 480, &screen, &frame) ||
		!equal(frame, 48, 36, 592, 444))
		return 2;
	if (ps2_rasterizer_calculate_bounds(0, 448, &screen, &frame) ||
		ps2_rasterizer_calculate_bounds(512, 32768, &screen, &frame) ||
		ps2_rasterizer_calculate_bounds(512, 448, NULL, &frame))
		return 3;
	if (!equal(screen, 0, 0, 640, 480) || !equal(frame, 48, 36, 592, 444))
		return 4;
	puts("PS2 rasterizer bounds fixture passed");
	return 0;
}
