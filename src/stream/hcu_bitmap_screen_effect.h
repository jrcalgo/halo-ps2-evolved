#ifndef HALO_STREAM_HCU_BITMAP_SCREEN_EFFECT_H
#define HALO_STREAM_HCU_BITMAP_SCREEN_EFFECT_H

#include "stream/hcu_bitmap_renderer.h"

/* Native GS implementation for CE's masked screen-output case with no warp,
 * convolution radius, color filters, or video stage. Unsupported parameters
 * fail inactive and never fall back to a mask overlay. */
int32_t hcu_bitmap_screen_effect_backend_native(void *backend_user,
	const halo_ps2_bitmap_request_reader *reader,
	hcu_bitmap_dispatch_context *dispatch, const void *video,
	chain_t *geometry, chain_t *upload, tc_t *cache);

/* Shared native packet kernel used by the private GS pixel fixture. UVs and
 * destination rectangle are the captured mask rectangle; all GS target and
 * scratch page addresses are explicit so the fixture exercises identical
 * packets with its validated resident mask texture. */
int32_t hcu_bitmap_screen_effect_emit_mask_tiles(chain_t *geometry,
	uint64_t mask_tex0, uint64_t mask_clamp, uint32_t mask_width, uint32_t mask_height,
	const float uv[4], uint32_t x0, uint32_t y0, uint32_t x1, uint32_t y1,
	uint64_t screen_tex0, uint64_t screen_clamp, uint32_t scratch_page,
	uint32_t scratch_z_page, uint32_t framebuffer_page, uint32_t framebuffer_width,
	uint32_t zbuffer_page, uint32_t mask_clut_block);

#endif
