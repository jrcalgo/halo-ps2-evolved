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
	HCU_BITMAP_BLEND_RAW_ADD = 4 /* Cs + Cd */
} hcu_bitmap_blend_t;

typedef struct {
	float x, y;             /* screen pixels, top-left origin */
	float u, v;             /* normalized [0,1] image coordinates */
	uint32_t argb;          /* CE colour; alpha is converted to GS 0..128 */
} hcu_bitmap_vertex_t;

typedef struct {
	uint64_t tex0;          /* caller-owned resident GS TEX0, including TBP/CBP */
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

#endif
