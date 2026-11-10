/* The ammo meter palette against the retail HUD parameters (native build of the real hcu_bitmap_meter_build_clut,
 * extracted from src/stream/hcu_bitmap_dispatch.c by test_hcu_bitmap_meter.py and included here).
 *
 * The HUD asks for threshold = mult * rounds + bias, and the bullets' Y (the fill order) is mult * (k + 1) for the
 * sniper rifle (60), rocket launcher (120) and assault rifle (4), or 20 * k + 10 for the magnum. N rounds must fill
 * exactly N bullets, including a full magazine: the palette once used the bin centre (Y * 4 + 2), which lifted the top
 * bullet's Y over a threshold of Y + 1 and showed one round spent on a full magazine. */
#include <stdio.h>
#include <string.h>
#include <stdint.h>
#include "halo_ps2_bitmap_requests.h"
#include METER_SOURCE

#define METER_E(idx) (clut + ((((idx) & 0xE7u) | (((idx) & 0x08u) << 1) | (((idx) & 0x10u) >> 1))) * 4u)

int main(void)
{
	static const struct { const char *name; unsigned count, y0, step, mult, bias; } meters[] = {
		{ "sniper rifle", 4u, 60u, 60u, 60u, 1u },
		{ "rocket launcher", 2u, 120u, 120u, 120u, 1u },
		{ "assault rifle", 60u, 4u, 4u, 4u, 2u },
		{ "magnum", 12u, 10u, 20u, 20u, 0u },
	};
	unsigned mi, ri, bad = 0;
	for (mi = 0; mi < sizeof(meters) / sizeof(meters[0]); ++mi) {
		const unsigned rounds[3] = { meters[mi].count, meters[mi].count - 1u, 1u };
		for (ri = 0; ri < 3u; ++ri) {
			halo_ps2_bitmap_request m;
			uint8_t clut[1024];
			unsigned t = meters[mi].mult * rounds[ri] + meters[mi].bias, k, filled = 0;
			int premult;
			if (t > 255u) t = 255u;
			memset(&m, 0, sizeof(m));
			m.has_meter = HALO_PS2_BITMAP_METER_PRESENT;
			m.meter_value = (uint8_t)t;
			m.meter_flash_color = (uint32_t)t << 24;           /* empty threshold = the same value */
			m.meter_gradient_min_color = 0xFFFF0000u;
			m.meter_gradient_max_color = 0xFF0000FFu;
			m.meter_background_color = 0x40101010u;            /* empty: keeps 25%, alpha 96 */
			m.meter_tint_color = 0x00FFFFFFu;                  /* filled: keeps nothing, alpha 128 */
			premult = hcu_bitmap_meter_build_clut(&m, clut);
			if (premult != 0 && premult != 1) return 2;
			for (k = 0; k < meters[mi].count; ++k) {
				const uint8_t *e = METER_E((3u << 6) | ((meters[mi].y0 + meters[mi].step * k) >> 2));
				if (e[3] == 128u) filled++;
			}
			if (filled != rounds[ri]) {
				fprintf(stderr, "meter %s: %u rounds filled %u bullets (threshold %u)\n", meters[mi].name,
					rounds[ri], filled, t);
				bad++;
			}
		}
	}
	return bad ? 1 : 0;
}
