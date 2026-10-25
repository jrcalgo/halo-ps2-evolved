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

/* Emits one bounded GIF packet containing two textured triangles. The input
 * tex_section must already be validated by tex_open; `image_index` selects one
 * PS2 TEXS image, not a CE bitmap sequence. No VRAM allocation/upload lifetime
 * is owned here: the caller must keep the resident TEX0 and texture lease valid
 * through DMA completion. */
hcu_bitmap_quad_status hcu_bitmap_quad_emit(chain_t *chain,
	const tex_section *textures, uint32_t image_index,
	const hcu_bitmap_quad_state_t *state,
	const hcu_bitmap_vertex_t vertices[4]);

#endif
