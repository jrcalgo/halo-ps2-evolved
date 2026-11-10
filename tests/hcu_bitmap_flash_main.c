#include "stream/hcu_bitmap_quad.h"
#include "render/gs.h"

#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

/* Screen flash: decodes the GS packets hcu_bitmap_quad_emit_flash writes and runs the blend each pass sets up on sample
 * destination colours, against retail's per-type formula (rasterizer_xbox_screen_effect.c). Also checks the packet
 * layout, the pane rectangle and the restore. Usage: hcu_bitmap_flash_test <case>. */

#define CAP_QW 128u
#define MAX_PASSES 4u

typedef struct {
	uint64_t alpha, frame;
	uint32_t fbmask, rgb[3], as;
	int has_frame;
} sim_pass;

typedef struct {
	const char *name;
	int16_t type;
	uint32_t argb, intensity;
	int framed;       /* pass the frame register */
	int expect_passes;
	int check_channels; /* bit mask of channels the formula is checked on */
	uint32_t expect_mask0; /* FBMSK of the first pass when framed */
} flash_case;

#define FRAME_BASE GS_FRAME(0x40, 10, GS_PSMCT16S, 0)

static const flash_case cases[] = {
	/* name, type, argb, intensity, framed, passes, channels checked, FBMSK of pass 0 */
	{ "lighten_damage",   1, 0x00CC2222u, 179, 1, 1, 7, 0 },
	{ "lighten_fade",     1, 0xFF000000u, 153, 1, 1, 7, 0 },
	{ "lighten_full",     1, 0x80FF4020u, 200, 1, 2, 7, 0 },
	{ "lighten_white",    1, 0xFFFFFFFFu, 255, 1, 2, 7, 0 },
	{ "lighten_zero",     1, 0x80FF4020u,   0, 1, 0, 7, 0 },
	{ "darken_camo",      2, 0x00595900u, 128, 1, 1, 7, 0 },
	{ "darken_full",      2, 0x00FF8000u, 255, 1, 1, 7, 0 },
	{ "max",              3, 0x33FF8040u, 230, 1, 2, 7, 0 },
	{ "max_noop",         3, 0xFF8080FFu, 204, 1, 0, 7, 0 },
	{ "min",              4, 0x4D808080u, 230, 1, 2, 7, 0 },
	{ "invert_overshield", 5, 0x00CC00CCu, 255, 1, 1, 7, 0xFF00FF00u },
	{ "invert_half",      5, 0x00CC00CCu, 128, 1, 1, 7, 0xFF00FF00u },
	{ "invert_noframe",   5, 0x00CC00CCu, 255, 0, 1, 5, 0 },
	{ "tint_health",      6, 0xFFC5C5C5u, 204, 1, 1, 7, 0xFF000000u },
	{ "tint_teleporter",  6, 0x8059FF59u, 255, 1, 2, 7, 0xFF00FF00u },
	{ "tint_teleporter_noframe", 6, 0x8059FF59u, 255, 0, 1, 5, 0 },
};

static int src(unsigned sel, int cs, int cd) { return sel == 0u ? cs : sel == 1u ? cd : 0; }

/* GS blend: ((A - B) * C >> 7) + D, clamped (COLCLAMP = 1). C: 0 = As, 1 = Ad (128), 2 = FIX. */
static int blend(uint64_t alpha, int cs, int cd, int as)
{
	unsigned a = (unsigned)(alpha & 3u), b = (unsigned)((alpha >> 2) & 3u);
	unsigned c = (unsigned)((alpha >> 4) & 3u), d = (unsigned)((alpha >> 6) & 3u);
	int fix = (int)((alpha >> 32) & 255u);
	int cc = c == 0u ? as : c == 1u ? 128 : fix;
	int v = (((src(a, cs, cd) - src(b, cs, cd)) * cc) >> 7) + src(d, cs, cd);
	return v < 0 ? 0 : v > 255 ? 255 : v;
}

static float sat(float x) { return x < 0.0f ? 0.0f : x > 1.0f ? 1.0f : x; }

/* retail's result for one channel (all values 0..1) */
static float retail(int16_t type, float c, float ca, float intensity, float cd)
{
	float F = c * intensity, Fa = ca * intensity, S;
	switch (type) {
	case 1: return sat(F + cd * (1.0f - Fa));
	case 2: return sat(cd - F);
	case 3: { float x = sat(F - Fa); return cd > x ? cd : x; }
	case 4: { float x = sat(F + Fa); return cd < x ? cd : x; }
	case 5: S = sat(F * (2.0f * F - 1.0f) + Fa); return sat(S * (1.0f - cd) + cd * (1.0f - F));
	case 6: return sat(Fa + cd * (1.0f - (1.0f - c) * intensity));
	default: return cd;
	}
}

/* Decodes a flash packet that starts at memory[0]. Returns the pass count, or a negative error code; *end_qw is the
 * packet's length in qwords including its DMA tag. */
static int parse(const uint64_t *m, const hcu_bitmap_rect *pane, int framed, sim_pass *out, unsigned *end_qw)
{
	const uint64_t *q = m + 4; /* DMA tag, VIF qword */
	const uint64_t *end;
	unsigned n = 0;
	uint64_t scissor = (uint64_t)pane->x | (uint64_t)(pane->x + pane->w - 1) << 16 |
		(uint64_t)pane->y << 32 | (uint64_t)(pane->y + pane->h - 1) << 48;
	uint32_t xo = (2048u * 16u) - 640u * 8u, yo = (2048u * 16u) - 448u * 8u;
	*end_qw = 1u + (unsigned)(m[0] & 0xFFFFu);
	end = m + (size_t)*end_qw * 2u;
	if (((m[0] >> 28) & 7u) != DMA_ID_CNT) return -1;
	if (q[0] != GIF_TAG(4, 1, 0, 0, GIFX_FLG_PACKED, 1) || q[1] != GIF_REGS_AD) return -2;
	if (q[2] != 1u || q[3] != 0x46u) return -3; /* COLCLAMP = 1 */
	if (q[4] != GS_TEST(0, 1, 0, 0, 0, 0, 1, 1) || q[5] != GS_A_TEST_1) return -4;
	if (q[6] != ((uint64_t)xo | ((uint64_t)yo << 32)) || q[7] != 0x18u) return -5;
	if (q[8] != scissor || q[9] != 0x40u) return -6;
	q += 10;
	while (q < end) {
		sim_pass *p;
		unsigned slot;
		uint32_t cx0, cx1, cy0, cy1;
		if (n >= MAX_PASSES) return -7;
		p = &out[n];
		memset(p, 0, sizeof(*p));
		if (q[1] != GIF_REGS_AD || (q[0] & 0x7FFFu) != (framed ? 2u : 1u)) return -8;
		if (q[3] != GS_A_ALPHA_1) return -9;
		p->alpha = q[2];
		if (framed) {
			if (q[5] != GS_A_FRAME_1) return -10;
			p->frame = q[4];
			p->has_frame = 1;
			p->fbmask = (uint32_t)(q[4] >> 32);
			if ((p->frame & 0xFFFFFFFFu) != (FRAME_BASE & 0xFFFFFFFFu)) return -11;
			q += 6;
		} else {
			q += 4;
		}
		if (q[0] != GIF_TAG(6, 1, 1, GS_PRIM(GSX_PRIM_TRIANGLE, 1, 0, 0, 1, 0, 1, 0, 0), GIFX_FLG_PACKED, 3) ||
			q[1] != 0x531) return -12;
		q += 2;
		p->rgb[0] = (uint32_t)q[0]; p->rgb[1] = (uint32_t)(q[0] >> 32); p->rgb[2] = (uint32_t)q[1];
		p->as = (uint32_t)(q[1] >> 32);
		/* every vertex carries the same colour; the quad is the pane (order 0,1,2,0,2,3) */
		cx0 = (uint32_t)((2048 - 320 + pane->x) * 16); cx1 = (uint32_t)((2048 - 320 + pane->x + pane->w) * 16);
		cy0 = (uint32_t)((2048 - 224 + pane->y) * 16); cy1 = (uint32_t)((2048 - 224 + pane->y + pane->h) * 16);
		for (slot = 0; slot < 6u; slot++) {
			const uint64_t *v = q + 6u * slot;
			static const unsigned xs[6] = { 0, 1, 1, 0, 1, 0 }, ys[6] = { 0, 0, 1, 0, 1, 1 };
			if (v[0] != q[0] || v[1] != q[1]) return -13;
			if ((uint32_t)(v[4] & 0xFFFFu) != (xs[slot] ? cx1 : cx0) ||
				(uint32_t)((v[4] >> 32) & 0xFFFFu) != (ys[slot] ? cy1 : cy0)) return -14;
		}
		q += 36;
		n++;
	}
	if (q != end) return -15;
	return (int)n;
}

static int check_restore(const uint64_t *m, unsigned at_qw, int framed, unsigned *total_qw)
{
	const uint64_t *tag = m + at_qw * 2u;
	const uint32_t *words = (const uint32_t *)(tag + 2);
	const uint64_t *q = (const uint64_t *)(words + 4);
	unsigned n = framed ? 5u : 4u;
	uint32_t xo = (2048u * 16u) - 640u * 8u;
	uint32_t yo = (2048u * 16u) - 448u * 8u;
	if ((tag[0] & 0xFFFFu) != n + 2u || ((tag[0] >> 28) & 7u) != DMA_ID_CNT) return 60;
	if ((words[3] & 0xFFFFu) != n + 1u) return 61;
	if (q[0] != GIF_TAG(n, 1, 0, 0, GIFX_FLG_PACKED, 1) || q[1] != GIF_REGS_AD) return 62;
	if (q[2] != GS_TEST(0, 1, 0, 0, 0, 0, 1, 1) || q[3] != GS_A_TEST_1) return 63;
	if (q[4] != GS_ALPHA(0, 1, 0, 1, 0) || q[5] != GS_A_ALPHA_1) return 64;
	if (q[6] != ((uint64_t)xo | ((uint64_t)yo << 32)) || q[7] != 0x18u) return 65;
	if (q[8] != ((639ull << 16) | (447ull << 48)) || q[9] != 0x40u) return 66;
	if (framed && (q[10] != FRAME_BASE || q[11] != GS_A_FRAME_1)) return 67; /* mask back to clear */
	*total_qw = at_qw + 3u + n;
	return 0;
}

static int run_case(const flash_case *fc)
{
	uint64_t memory[CAP_QW * 2];
	chain_t chain;
	hcu_bitmap_rect pane = { 320, 0, 320, 224 };
	sim_pass passes[MAX_PASSES];
	unsigned flash_qw = 0, total = 0, i, ch;
	static const int cds[] = { 0, 17, 64, 128, 200, 255 };
	int np, rc;
	hcu_bitmap_quad_status status;
	float c[3], ca;
	memset(memory, 0xA5, sizeof memory);
	chain_init(&chain, memory, CAP_QW);
	status = hcu_bitmap_quad_emit_flash(&chain, 640, 448, &pane, 0xFFFFFFu, fc->type, fc->argb, fc->intensity,
		fc->framed ? FRAME_BASE : 0u);
	if (status != HCU_BITMAP_QUAD_OK) return 1;
	if (fc->expect_passes == 0) {
		/* nothing to draw at this intensity: the chain is untouched */
		return chain.qw == 0 && ((uint8_t *)memory)[0] == 0xA5 ? 0 : 2;
	}
	np = parse(memory, &pane, fc->framed, passes, &flash_qw);
	if (np < 0) { printf("parse error %d\n", np); return 3; }
	if (np != fc->expect_passes) { printf("passes %d expected %d\n", np, fc->expect_passes); return 4; }
	if (fc->framed && fc->expect_mask0 && passes[0].fbmask != fc->expect_mask0) {
		printf("fbmask %08x expected %08x\n", passes[0].fbmask, fc->expect_mask0);
		return 5;
	}
	c[0] = (float)((fc->argb >> 16) & 255u) / 255.0f; c[1] = (float)((fc->argb >> 8) & 255u) / 255.0f;
	c[2] = (float)(fc->argb & 255u) / 255.0f; ca = (float)(fc->argb >> 24) / 255.0f;
	for (ch = 0; ch < 3u; ch++) {
		if (!(fc->check_channels & (1 << ch))) continue;
		for (i = 0; i < sizeof cds / sizeof cds[0]; i++) {
			int cd = cds[i], v = cd, p, want;
			for (p = 0; p < np; p++) {
				if (passes[p].has_frame && (passes[p].fbmask >> (8u * ch)) & 0xFFu) continue; /* channel masked off */
				v = blend(passes[p].alpha, (int)passes[p].rgb[ch], v, (int)passes[p].as);
			}
			want = (int)(retail(fc->type, c[ch], ca, (float)fc->intensity / 255.0f, (float)cd / 255.0f) * 255.0f + 0.5f);
			if (v - want > 3 || want - v > 3) {
				printf("%s ch%u cd=%d got %d want %d\n", fc->name, ch, cd, v, want);
				return 6;
			}
		}
	}
	if ((rc = check_restore(memory, flash_qw, fc->framed, &total)) != 0) return rc;
	if (chain.qw != total) { printf("chain qw %u expected %u\n", (unsigned)chain.qw, total); return 7; }
	if (((uint8_t *)memory)[chain.qw * 16u] != 0xA5) return 8;
	return 0;
}

static int run_panes(const char *mode)
{
	uint64_t memory[CAP_QW * 2];
	chain_t chain;
	hcu_bitmap_rect pane = !strcmp(mode, "pane_2p") ? (hcu_bitmap_rect){ 0, 224, 640, 224 } :
		!strcmp(mode, "pane_4p") ? (hcu_bitmap_rect){ 320, 224, 320, 224 } : (hcu_bitmap_rect){ 0, 0, 640, 448 };
	sim_pass passes[MAX_PASSES];
	unsigned flash_qw;
	memset(memory, 0xA5, sizeof memory);
	chain_init(&chain, memory, CAP_QW);
	/* the quad is the whole pane: a 2P pane (640x224), a 4P pane (320x224) and the full frame */
	if (hcu_bitmap_quad_emit_flash(&chain, 640, 448, &pane, 0xFFFFFFu, 2, 0x80FF4020u, 255u, 0u) != HCU_BITMAP_QUAD_OK) return 33;
	return parse(memory, &pane, 0, passes, &flash_qw) == 1 ? 0 : 34;
}

int main(int argc, char **argv)
{
	const char *mode = argc > 1 ? argv[1] : "";
	uint64_t memory[CAP_QW * 2];
	chain_t chain;
	hcu_bitmap_rect rect = { 320, 0, 320, 224 };
	unsigned i;
	int rc;
	for (i = 0; i < sizeof cases / sizeof cases[0]; i++) {
		if (strcmp(mode, cases[i].name)) continue;
		rc = run_case(&cases[i]);
		if (rc) printf("case %s failed: %d\n", cases[i].name, rc);
		return rc;
	}
	if (!strcmp(mode, "pane_2p") || !strcmp(mode, "pane_4p") || !strcmp(mode, "pane_full")) return run_panes(mode);
	memset(memory, 0xA5, sizeof memory);
	chain_init(&chain, memory, CAP_QW);
	if (!strcmp(mode, "overflow")) {
		chain.cap_qw = 40;
		return hcu_bitmap_quad_emit_flash(&chain, 640, 448, &rect, 0xFFFFFFu, 1, 0x80FF0000u, 255u, FRAME_BASE) ==
			HCU_BITMAP_QUAD_CAPACITY && chain.qw == 0 && !chain.overflow && ((uint8_t *)memory)[0] == 0xA5 ? 0 : 31;
	}
	if (!strcmp(mode, "bad_rect")) {
		rect.w = 400;
		return hcu_bitmap_quad_emit_flash(&chain, 640, 448, &rect, 0xFFFFFFu, 1, 0x80FF0000u, 255u, 0u) ==
			HCU_BITMAP_QUAD_INVALID && chain.qw == 0 ? 0 : 32;
	}
	if (!strcmp(mode, "bad_type")) {
		return hcu_bitmap_quad_emit_flash(&chain, 640, 448, &rect, 0xFFFFFFu, 0, 0x80FF0000u, 255u, 0u) ==
			HCU_BITMAP_QUAD_INVALID && hcu_bitmap_quad_emit_flash(&chain, 640, 448, &rect, 0xFFFFFFu, 7, 0x80FF0000u, 255u, 0u) ==
			HCU_BITMAP_QUAD_INVALID && hcu_bitmap_quad_emit_flash(&chain, 640, 448, &rect, 0xFFFFFFu, 1, 0x80FF0000u, 256u, 0u) ==
			HCU_BITMAP_QUAD_INVALID ? 0 : 35;
	}
	printf("unknown mode '%s'\n", mode);
	return 99;
}
