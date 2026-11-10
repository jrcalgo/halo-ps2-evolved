#ifndef HCU_BITMAP_QUAD_H
#define HCU_BITMAP_QUAD_H

#include <stdint.h>
#include "render/chain.h"
#include "world/tex.h"

typedef enum {
	HCU_BITMAP_BLEND_OPAQUE = 0,
	HCU_BITMAP_BLEND_ALPHA = 1,
	HCU_BITMAP_BLEND_ADD = 2, /* source RGB weighted by source alpha */
	HCU_BITMAP_BLEND_PREMULTIPLIED = 3, /* Cs + Cd * (1 - As), two GS draws */
	HCU_BITMAP_BLEND_RAW_ADD = 4, /* Cs + Cd */
	HCU_BITMAP_BLEND_SUBTRACT = 5 /* Cd - Cs */
} hcu_bitmap_blend_t;

typedef struct {
	float x, y;             /* screen pixels, top-left origin */
	float u, v;             /* normalized image coordinates; [-8,8] when uv_extended */
	uint32_t argb;          /* CE colour; alpha is converted to GS 0..128 */
} hcu_bitmap_vertex_t;

typedef struct {
	uint64_t tex0;          /* caller-owned resident GS TEX0, including TBP/CBP */
	uint64_t clamp;         /* GS CLAMP; zero selects clamp to the validated image bounds */
	uint16_t screen_w, screen_h;
	uint16_t clip_x, clip_y, clip_w, clip_h;
	uint32_t z;             /* GS 24-bit depth */
	hcu_bitmap_blend_t blend;
	uint8_t texture_layers; /* only one sampled texture is currently supported */
	uint8_t point_sampled;
	/* Meter fill: GS alpha test on the texel alpha, which encodes the fill order.
	 * FILL keeps texels with alpha >= alpha_ref; EMPTY keeps alpha < alpha_ref.
	 * The pair partitions the meter exactly, so each pass is one quad. */
	uint8_t alpha_test;     /* HCU_BITMAP_ALPHA_TEST_* */
	uint8_t alpha_ref;
	/* Wrapped HUD overlays (sweep, sliding shine) sample outside [0,1].
	 * Left clear, UVs must stay in [0,1]. */
	uint8_t uv_extended;
} hcu_bitmap_quad_state_t;

enum {
	HCU_BITMAP_ALPHA_TEST_NONE = 0,
	HCU_BITMAP_ALPHA_TEST_FILL = 1,
	HCU_BITMAP_ALPHA_TEST_EMPTY = 2
};

typedef enum {
	HCU_BITMAP_QUAD_OK = 0,
	HCU_BITMAP_QUAD_INVALID = -1,
	HCU_BITMAP_QUAD_CAPACITY = -2,
	HCU_BITMAP_QUAD_TEX = -3
} hcu_bitmap_quad_status;

/* Per-view placement. CE captures HUD vertices relative to the viewport origin of
 * the window that drew them (hud_draw.c subtracts viewport_bounds.x0/y0). The
 * parent frame owner records one entry per CE window, in set-view order, with the
 * rectangle that hcu_render_layout_compute assigns to that ordinal. */
#define HCU_BITMAP_MAX_VIEWS 4u

typedef struct {
	int32_t x, y, w, h;
} hcu_bitmap_rect;

typedef struct {
	int32_t window_index;   /* CE window index (may have gaps) */
	hcu_bitmap_rect rect;   /* screen rectangle of this view */
} hcu_bitmap_view;

/* view_count 0 selects the full screen (single-view producers). Otherwise the
 * window must be present in views[0..view_count). Returns 0, or -1 when no
 * entry matches or the screen is unusable. */
int hcu_bitmap_view_resolve(const hcu_bitmap_view *views, uint32_t view_count,
	int32_t window_index, int32_t screen_w, int32_t screen_h, hcu_bitmap_rect *out);

/* Offsets CE viewport-relative vertices into `rect` and sets the quad's scissor
 * (state->clip_*) to exactly `rect`. Returns 0, or -1 when `rect` is empty or
 * leaves the screen. Pure arithmetic: no heap, O(1) per quad. */
int hcu_bitmap_quad_place(hcu_bitmap_quad_state_t *state, const hcu_bitmap_rect *rect,
	const hcu_bitmap_vertex_t in[4], hcu_bitmap_vertex_t out[4]);

/* Emits one bounded GIF packet containing two textured triangles. The input
 * tex_section must already be validated by tex_open; `image_index` selects one
 * PS2 TEXS image, not a CE bitmap sequence. No VRAM allocation/upload lifetime
 * is owned here: the caller must keep the resident TEX0 and texture lease valid
 * through DMA completion. */
hcu_bitmap_quad_status hcu_bitmap_quad_emit(chain_t *chain,
	const tex_section *textures, uint32_t image_index,
	const hcu_bitmap_quad_state_t *state,
	const hcu_bitmap_vertex_t vertices[4]);

/* Emits using metadata already validated and retained by a resident descriptor.
 * This path does not require the original TEXS bytes or a tex_section. */
hcu_bitmap_quad_status hcu_bitmap_quad_emit_validated(chain_t *chain,
	const tex_info *image, const hcu_bitmap_quad_state_t *state,
	const hcu_bitmap_vertex_t vertices[4]);

/* Screen flash: untextured blend passes over `rect`, scissored to it. `type` is CE's render_screen_flash type (1 lighten,
 * 2 darken, 3 max, 4 min, 5 invert, 6 tint), `argb` the flash definition's colour (not scaled) and `intensity` the
 * flash intensity 0..255; each type draws retail's formula (see hcu_bitmap_quad.c) with no alpha caps. `frame_base` is the
 * GS FRAME_1 value with FBMSK clear (0 when unknown): it lets invert and tint treat channels separately and is written
 * back after the draw. COLCLAMP is set to 1. A flash whose passes are all no-ops at this intensity returns OK
 * without drawing. The draw is followed by a GS restore. */
hcu_bitmap_quad_status hcu_bitmap_quad_emit_flash(chain_t *chain,
	uint16_t screen_w, uint16_t screen_h, const hcu_bitmap_rect *rect,
	uint32_t z, int16_t type, uint32_t argb, uint32_t intensity, uint64_t frame_base);

/* Untextured quad in the same virtual-frame space as other HUD vertices.
 * `subtract` selects Cd - Cs (a hole punched out of a previous additive quad);
 * otherwise the blend is Cs + Cd. The packet writes the full-framebuffer
 * XYOFFSET, so it does not depend on the last split view's offset. */
/* Radar sweep: a ring of `outer` radius centred on (cx, cy) in the same virtual
 * frame as the HUD, with a transparent hole of `inner` radius, clipped to the
 * outer circle so it stays inside the radar disc. `inner` 0 draws a filled
 * disc. The centre and radii are scaled into `rect` the same way a HUD quad is. */
hcu_bitmap_quad_status hcu_bitmap_quad_emit_ring(chain_t *chain,
	uint16_t screen_w, uint16_t screen_h, const hcu_bitmap_rect *rect,
	float cx, float cy, float outer, float inner, uint32_t argb);

/* Controller button glyph (HALO_PS2_BUTTON_GLYPH_* 1..8) centred on (cx, cy) in the HUD's virtual
 * frame, `height` tall, as alpha-blended vector triangles. `argb`'s alpha is the prompt fade. */
hcu_bitmap_quad_status hcu_bitmap_quad_emit_glyph(chain_t *chain,
	uint16_t screen_w, uint16_t screen_h, const hcu_bitmap_rect *rect,
	unsigned glyph, float cx, float cy, float height, uint32_t argb);

hcu_bitmap_quad_status hcu_bitmap_quad_emit_marker(chain_t *chain,
	uint16_t screen_w, uint16_t screen_h, const hcu_bitmap_rect *rect,
	const hcu_bitmap_vertex_t vertices[4], int subtract);

/* Defined for the flash emitter and the screen-effect backend. Other includes
 * of this header leave the helper out so they do not pull the compositor. */
#ifdef HCU_BITMAP_GS_RESTORE_IMPL
#include "render/decal_compose.h"

#define HCU_BITMAP_GS_RESTORE_DRAW_N 4u
#define HCU_BITMAP_GS_RESTORE_FULL_N 11u
/* DMA tag plus chain_cnt(2+n): VIF qword, GIF tag, n A+D registers. */
#define HCU_BITMAP_GS_RESTORE_QW(n) (3u + (n))

/* NULL frame/zbuf restores TEST, ALPHA, XYOFFSET and SCISSOR. A resident target
 * also restores FRAME (FBMSK clear), FBA, ZBUF, TEXA, CLAMP, TEX0 and TEX1. */
static inline int hcu_bitmap_restore_gs_draw_state(chain_t *chain,
	const uint64_t *frame, const uint64_t *zbuf, uint64_t xyoffset, uint64_t scissor)
{
	gs_ad ad[11];
	unsigned n;
	uint64_t test = GS_TEST(0u, 1u, 0u, 0u, 0u, 0u, 1u, 1u);
	uint64_t alpha = GS_ALPHA(0u, 1u, 0u, 1u, 0u);
	if (!chain) return 0;
	if (frame && zbuf) {
		if (decal_compose_restore_state(ad, *frame, 1u, *zbuf, test, alpha, xyoffset, scissor,
			0x80ull | (0x80ull << 32), GS_CLAMP(1u, 1u, 0u, 0u, 0u, 0u), 0u,
			GS_TEX1(1u, 0u, 0u, 0u, 0u, 0u, 0u)) != 0)
			return 0;
		n = HCU_BITMAP_GS_RESTORE_FULL_N;
	} else {
		ad[0].data = test; ad[0].addr = DECAL_GS_A_TEST_1;
		ad[1].data = alpha; ad[1].addr = DECAL_GS_A_ALPHA_1;
		ad[2].data = xyoffset; ad[2].addr = DECAL_GS_A_XYOFFSET_1;
		ad[3].data = scissor; ad[3].addr = DECAL_GS_A_SCISSOR_1;
		n = HCU_BITMAP_GS_RESTORE_DRAW_N;
	}
	return decal_compose_emit_ad(chain, ad, n, 0);
}
#endif

#endif
