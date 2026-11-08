#include "stream/hcu_bitmap_quad.h"
#include "render/gs.h"

#include <stdint.h>
#include <stdlib.h>
#include <string.h>

/* Every DualShock glyph emits one alpha-blended triangle packet whose vertices stay inside the
 * glyph's own scissor. A zero fade draws nothing and a full chain reports CAPACITY. */
int main(void)
{
	enum { CAP = 1200 };
	static uint64_t memory[CAP * 2];
	hcu_bitmap_rect rect = { 0, 0, 640, 448 };
	unsigned glyph;
	for (glyph = 1; glyph <= 8; glyph++) {
		chain_t chain;
		hcu_bitmap_quad_status status;
		const uint64_t *tag, *q;
		uint32_t nloop, x0, x1, y0, y1;
		unsigned i;
		memset(memory, 0xA5, sizeof memory);
		chain_init(&chain, memory, CAP);
		status = hcu_bitmap_quad_emit_glyph(&chain, 640, 448, &rect, glyph, 100.0f, 200.0f, 26.0f, 0xFFFFFFFFu);
		if (status != HCU_BITMAP_QUAD_OK || chain.qw < 9u) return 10 + (int)glyph;
		tag = memory;
		q = (const uint64_t *)((const uint32_t *)(tag + 2) + 4);
		if (q[2] != GS_ALPHA(0, 1, 0, 1, 0)) return 30;
		x0 = (uint32_t)(q[8] & 0xFFFFu); x1 = (uint32_t)((q[8] >> 16) & 0xFFFFu);
		y0 = (uint32_t)((q[8] >> 32) & 0xFFFFu); y1 = (uint32_t)((q[8] >> 48) & 0xFFFFu);
		if (x1 <= x0 || y1 <= y0 || x1 - x0 > 60u || y1 - y0 > 40u) return 31;
		nloop = (uint32_t)(q[10] & 0x7FFFu);
		if (nloop < 9u || nloop % 3u) return 32;
		q += 12;
		for (i = 0; i < nloop; i++, q += 6) {
			/* XYZ2 is 12.4 fixed point around 2048 - extent/2; compare against the scissor in pixels */
			float px = (float)(uint32_t)q[4] / 16.0f - (2048.0f - 640.0f * 0.5f);
			float py = (float)(uint32_t)(q[4] >> 32) / 16.0f - (2048.0f - 448.0f * 0.5f);
			if (px < (float)x0 - 1.0f || px > (float)x1 + 1.0f || py < (float)y0 - 1.0f || py > (float)y1 + 1.0f) return 33;
		}
	}
	{
		chain_t chain;
		memset(memory, 0xA5, sizeof memory);
		chain_init(&chain, memory, CAP);
		if (hcu_bitmap_quad_emit_glyph(&chain, 640, 448, &rect, 1, 100.0f, 200.0f, 26.0f, 0x00FFFFFFu) != HCU_BITMAP_QUAD_OK || chain.qw) return 40;
		chain_init(&chain, memory, 8);
		if (hcu_bitmap_quad_emit_glyph(&chain, 640, 448, &rect, 6, 100.0f, 200.0f, 26.0f, 0xFFFFFFFFu) != HCU_BITMAP_QUAD_CAPACITY) return 41;
		if (hcu_bitmap_quad_emit_glyph(&chain, 640, 448, &rect, 9, 100.0f, 200.0f, 26.0f, 0xFFFFFFFFu) != HCU_BITMAP_QUAD_INVALID) return 42;
	}
	return 0;
}
