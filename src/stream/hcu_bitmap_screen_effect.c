#include "stream/hcu_bitmap_screen_effect.h"

#include "platform/video.h"
#include "render/bsp_render.h"
#include "render/decal_compose.h"
#include "render/gs.h"
#include "render/upload.h"
#include "platform/timer.h"

#include <math.h>
#include <string.h>

#if (defined(HALO_PS2_C3_TIMING) && HALO_PS2_C3_TIMING) || \
	(defined(HALO_PS2_C3_TELEMETRY) && HALO_PS2_C3_TELEMETRY) || \
	(defined(HALO_PS2_C3_LAG_TRACE) && HALO_PS2_C3_LAG_TRACE) || \
	(defined(HALO_PS2_C3_PERF_PROBE) && HALO_PS2_C3_PERF_PROBE)
#define HCU_SCREEN_EFFECT_PROBE 1
#else
#define HCU_SCREEN_EFFECT_PROBE 0
#endif

typedef struct {
	const halo_ps2_bitmap_request *request;
	uint64_t mask_tex0, mask_clamp;
	uint32_t mask_width, mask_height;
	int32_t x0, y0, x1, y1;
	uint32_t tiles;
} screen_effect_view;

static uint64_t frame_state(uint32_t page, uint32_t buffer_width, uint32_t psm, uint32_t mask)
{
	return (uint64_t)page | (uint64_t)buffer_width << 16 | (uint64_t)psm << 24 | (uint64_t)mask << 32;
}

static uint64_t scissor_state(uint32_t x0, uint32_t y0, uint32_t width, uint32_t height)
{
	return (uint64_t)x0 | (uint64_t)(x0 + width - 1u) << 16 |
		(uint64_t)y0 << 32 | (uint64_t)(y0 + height - 1u) << 48;
}

static uint32_t uv_fixed(float uv, uint32_t extent)
{
	float value = uv * (float)extent * 16.0f;
	if (value < 0.0f) value = 0.0f;
	if (value > 16383.0f) value = 16383.0f;
	return (uint32_t)floorf(value + 0.5f);
}

static int emit_pass(chain_t *geometry, const gs_ad state[12],
	uint32_t u0, uint32_t v0, uint32_t u1, uint32_t v1,
	uint32_t x0, uint32_t y0, uint32_t x1, uint32_t y1)
{
	uint64_t sprite[14];
	if (decal_compose_sprite_packet(sprite, u0, v0, u1, v1,
		x0, y0, x1, y1, 128u, 128u, 128u, 128u, 0u) != 0)
		return 0;
	return decal_compose_emit_ad(geometry, state, 12u, 0u) &&
		decal_compose_emit_sprite(geometry, sprite, 0u);
}

static int prepare_view(const halo_ps2_bitmap_request_reader *reader,
	const hcu_bitmap_dispatch_context *dispatch, uint32_t view, screen_effect_view *out)
{
	const halo_ps2_screen_effect_state *effect = &dispatch->screen_effects[view];
	halo_ps2_screen_effect_state copied;
	const halo_ps2_bitmap_request *request;
	int32_t x0, y0, x1, y1;
	uint32_t tw, th;
	if (!effect->valid) return 0;
	/* The first implemented production case is the exact Xbox no-convolution
	 * two-texture pass: texture-1 RGB, texture-0 alpha, INV_SRCALPHA blend. */
	if (effect->convolution_type != 0 || effect->convolution_radius != 0.0f ||
		effect->convolution_extra_passes != 0 || effect->light_enhancement_intensity != 0.0f ||
		effect->desaturation_intensity != 0.0f || effect->video_on)
		return -1;
	if (hcu_bitmap_dispatch_screen_effect_get(dispatch, reader->generation,
		reader->queue->frame_index, (uint16_t)view, &copied) != 1 ||
		copied.mask_request_index != effect->mask_request_index ||
		effect->mask_request_index >= reader->count)
		return -1;
	request = &reader->requests[effect->mask_request_index];
	if (!request->screen_effect_mask || request->view_index != (int16_t)view ||
		request->frame_index != reader->queue->frame_index ||
		hcu_bitmap_dispatch_screen_effect_mask_get(dispatch, reader->generation,
			reader->queue->frame_index, (uint16_t)view, &out->mask_tex0, &out->mask_clamp) != 1)
		return -1;
	tw = (uint32_t)((out->mask_tex0 >> 26) & 15u);
	th = (uint32_t)((out->mask_tex0 >> 30) & 15u);
	if (tw > 9u || th > 9u) return -1;
	out->mask_width = 1u << tw;
	out->mask_height = 1u << th;
	x0 = (int32_t)floorf(request->vertices[0].x + 0.5f);
	y0 = (int32_t)floorf(request->vertices[0].y + 0.5f);
	x1 = (int32_t)floorf(request->vertices[2].x + 0.5f);
	y1 = (int32_t)floorf(request->vertices[2].y + 0.5f);
	if (x0 < 0 || y0 < 0 || x1 <= x0 || y1 <= y0 ||
		x1 > VIDEO_WIDTH || y1 > VIDEO_HEIGHT ||
		request->vertices[1].x != request->vertices[2].x ||
		request->vertices[3].y != request->vertices[2].y)
		return -1;
	out->request = request;
	out->x0 = x0; out->y0 = y0; out->x1 = x1; out->y1 = y1;
	out->tiles = (uint32_t)((x1 - x0 + DECAL_COMPOSE_W - 1) / DECAL_COMPOSE_W) *
		(uint32_t)((y1 - y0 + DECAL_COMPOSE_H - 1) / DECAL_COMPOSE_H);
	return 1;
}

static void pass_state(gs_ad out[12], uint64_t frame, uint64_t zbuf, uint64_t tex0,
	uint64_t clamp, uint64_t alpha, uint32_t scissor_x, uint32_t scissor_y,
	uint32_t scissor_w, uint32_t scissor_h)
{
	out[0] = (gs_ad){ frame, DECAL_GS_A_FRAME_1 };
	out[1] = (gs_ad){ 0u, 0x4au }; /* FBA_1 off for CT32 scratch alpha math */
	out[2] = (gs_ad){ zbuf, DECAL_GS_A_ZBUF_1 };
	out[3] = (gs_ad){ GS_TEST(0u, 1u, 0u, 0u, 0u, 0u, 0u, 1u), DECAL_GS_A_TEST_1 };
	out[4] = (gs_ad){ alpha, DECAL_GS_A_ALPHA_1 };
	out[5] = (gs_ad){ 0u, DECAL_GS_A_XYOFFSET_1 };
	out[6] = (gs_ad){ scissor_state(scissor_x, scissor_y, scissor_w, scissor_h), DECAL_GS_A_SCISSOR_1 };
	out[7] = (gs_ad){ tex0, DECAL_GS_A_TEX0_1 };
	out[8] = (gs_ad){ GS_TEX1(1u, 0u, 1u, 1u, 0u, 0u, 0u), 0x14u };
	out[9] = (gs_ad){ clamp, DECAL_GS_A_CLAMP_1 };
	out[10] = (gs_ad){ 0x80ull | (0x80ull << 32), DECAL_GS_A_TEXA };
	out[11] = (gs_ad){ 0u, DECAL_GS_A_TEXFLUSH };
}

static int emit_view_tiles(chain_t *geometry, const screen_effect_view *view,
	uint64_t screen_tex0, uint64_t screen_clamp, uint32_t scratch_page,
	uint32_t scratch_z_page, uint32_t framebuffer_page, uint32_t framebuffer_width,
	uint32_t zbuffer_page, uint32_t mask_clut_block)
{
	uint32_t sx, sy;
	uint64_t mask_tex0 = (view->mask_tex0 & ~((uint64_t)0x3FFFu << 37)) |
		((uint64_t)mask_clut_block << 37);
	uint64_t scratch_tex0 = GS_TEX0(scratch_page * 32u, 1u, GS_PSMCT32,
		6u, 5u, 1u, 1u, 0u, GS_PSMCT32, 0u, 0u, 0u);
	uint64_t scratch_clamp = GS_CLAMP(1u, 1u, 0u, DECAL_COMPOSE_W - 1u,
		0u, DECAL_COMPOSE_H - 1u);
	for (sy = (uint32_t)view->y0; sy < (uint32_t)view->y1; sy += DECAL_COMPOSE_H) {
		for (sx = (uint32_t)view->x0; sx < (uint32_t)view->x1; sx += DECAL_COMPOSE_W) {
			uint32_t width = (uint32_t)view->x1 - sx;
			uint32_t height = (uint32_t)view->y1 - sy;
			float fx0, fx1, fy0, fy1, u0, u1, v0, v1;
			gs_ad state[12];
			if (width > DECAL_COMPOSE_W) width = DECAL_COMPOSE_W;
			if (height > DECAL_COMPOSE_H) height = DECAL_COMPOSE_H;
			fx0 = (float)(sx - (uint32_t)view->x0) / (float)(view->x1 - view->x0);
			fx1 = (float)(sx + width - (uint32_t)view->x0) / (float)(view->x1 - view->x0);
			fy0 = (float)(sy - (uint32_t)view->y0) / (float)(view->y1 - view->y0);
			fy1 = (float)(sy + height - (uint32_t)view->y0) / (float)(view->y1 - view->y0);
			u0 = view->request->vertices[0].u + fx0 *
				(view->request->vertices[1].u - view->request->vertices[0].u);
			u1 = view->request->vertices[0].u + fx1 *
				(view->request->vertices[1].u - view->request->vertices[0].u);
			v0 = view->request->vertices[0].v + fy0 *
				(view->request->vertices[3].v - view->request->vertices[0].v);
			v1 = view->request->vertices[0].v + fy1 *
				(view->request->vertices[3].v - view->request->vertices[0].v);
			pass_state(state, frame_state(scratch_page, 1u, GS_PSMCT32, 0u),
				GS_ZBUF(scratch_z_page, GS_PSMZ24, 1u), screen_tex0, screen_clamp,
				GS_ALPHA(0u, 2u, 2u, 2u, 128u), 0u, 0u, width, height);
			if (!emit_pass(geometry, state, sx << 4, sy << 4,
				(sx + width) << 4, (sy + height) << 4,
				0u, 0u, width << 4, height << 4)) return 0;
			pass_state(state, frame_state(scratch_page, 1u, GS_PSMCT32, 0x00FFFFFFu),
				GS_ZBUF(scratch_z_page, GS_PSMZ24, 1u), mask_tex0, view->mask_clamp,
				GS_ALPHA(0u, 2u, 2u, 2u, 128u), 0u, 0u, width, height);
			if (!emit_pass(geometry, state, uv_fixed(u0, view->mask_width),
				uv_fixed(v0, view->mask_height), uv_fixed(u1, view->mask_width),
				uv_fixed(v1, view->mask_height), 0u, 0u, width << 4, height << 4)) return 0;
			pass_state(state, frame_state(scratch_page, 1u, GS_PSMCT32, 0u),
				GS_ZBUF(scratch_z_page, GS_PSMZ24, 1u), screen_tex0, screen_clamp,
				GS_ALPHA(0u, 2u, 1u, 2u, 0u), 0u, 0u, width, height);
			if (!emit_pass(geometry, state, sx << 4, sy << 4,
				(sx + width) << 4, (sy + height) << 4,
				0u, 0u, width << 4, height << 4)) return 0;
			pass_state(state, frame_state(framebuffer_page, framebuffer_width,
				GS_PSMCT16S, 0u), GS_ZBUF(zbuffer_page, GS_PSMZ24, 1u),
				scratch_tex0, scratch_clamp, GS_ALPHA(0u, 2u, 2u, 2u, 128u),
				sx, sy, width, height);
			if (!emit_pass(geometry, state, 0u, 0u, width << 4, height << 4,
				sx << 4, sy << 4, (sx + width) << 4, (sy + height) << 4)) return 0;
		}
	}
	return 1;
}

int32_t hcu_bitmap_screen_effect_emit_mask_tiles(chain_t *geometry,
	uint64_t mask_tex0, uint64_t mask_clamp, uint32_t mask_width, uint32_t mask_height,
	const float uv[4], uint32_t x0, uint32_t y0, uint32_t x1, uint32_t y1,
	uint64_t screen_tex0, uint64_t screen_clamp, uint32_t scratch_page,
	uint32_t scratch_z_page, uint32_t framebuffer_page, uint32_t framebuffer_width,
	uint32_t zbuffer_page, uint32_t mask_clut_block)
{
	halo_ps2_bitmap_request request;
	screen_effect_view view;
	uint32_t tiles;
	if (!geometry || !uv || !mask_width || !mask_height || x1 <= x0 || y1 <= y0 ||
		x1 > VIDEO_WIDTH || y1 > VIDEO_HEIGHT) return -1;
	memset(&request, 0, sizeof(request));
	request.vertices[0].u = uv[0]; request.vertices[0].v = uv[1];
	request.vertices[1].u = uv[2]; request.vertices[1].v = uv[1];
	request.vertices[2].u = uv[2]; request.vertices[2].v = uv[3];
	request.vertices[3].u = uv[0]; request.vertices[3].v = uv[3];
	memset(&view, 0, sizeof(view));
	view.request = &request; view.mask_tex0 = mask_tex0; view.mask_clamp = mask_clamp;
	view.mask_width = mask_width; view.mask_height = mask_height;
	view.x0 = (int32_t)x0; view.y0 = (int32_t)y0;
	view.x1 = (int32_t)x1; view.y1 = (int32_t)y1;
	tiles = ((x1 - x0 + DECAL_COMPOSE_W - 1u) / DECAL_COMPOSE_W) *
		((y1 - y0 + DECAL_COMPOSE_H - 1u) / DECAL_COMPOSE_H);
	if (!chain_has_space(geometry, 84u * tiles + 80u)) return -1;
	return emit_view_tiles(geometry, &view, screen_tex0, screen_clamp, scratch_page,
		scratch_z_page, framebuffer_page, framebuffer_width, zbuffer_page,
		mask_clut_block) ? 1 : -1;
}

int32_t hcu_bitmap_screen_effect_backend_native(void *backend_user,
	const halo_ps2_bitmap_request_reader *reader,
	hcu_bitmap_dispatch_context *dispatch, const void *video_ptr,
	chain_t *geometry, chain_t *upload, tc_t *cache)
{
	const video_t *video = (const video_t *)video_ptr;
	screen_effect_view views[HALO_PS2_BITMAP_MAX_VIEWS];
	u32 view_count = 0, tiles = 0, scratch_page, scratch_z_page, clut_block, i;
	uint64_t screen_tex0, screen_clamp;
	uint32_t framebuffer_page, framebuffer_width, zbuffer_page;
	uint32_t palette[256];
	int32_t result = -1;
#if HCU_SCREEN_EFFECT_PROBE
	uint32_t valid_requests = 0u, capacity_refusal = 0u;
	uint32_t probe_start = timer_cycles();
	uint32_t chain_qw_start = 0u;
	int chain_valid = 0;
#endif
	(void)backend_user; (void)upload; (void)cache;
	if (!reader || !reader->held || !reader->queue || !dispatch || !video || !geometry ||
		reader->generation != dispatch->screen_effect_generation ||
		reader->queue->frame_index != dispatch->screen_effect_frame_index ||
		video->back < 0 || video->back > 1 || video->fb[video->back].psm != GS_PSMCT16S ||
		video->fb[video->back].width != VIDEO_WIDTH || video->fb[video->back].height != VIDEO_HEIGHT)
		goto done;
#if HCU_SCREEN_EFFECT_PROBE
	chain_valid = 1;
	chain_qw_start = chain_qwords(geometry);
#endif
	for (i = 0; i < HALO_PS2_BITMAP_MAX_VIEWS; ++i) {
		int result = prepare_view(reader, dispatch, i, &views[view_count]);
		if (result < 0) goto done; /* unsupported native inputs stay wholly inactive */
		if (result > 0) {
			tiles += views[view_count].tiles;
#if HCU_SCREEN_EFFECT_PROBE
			valid_requests++;
#endif
			view_count++;
		}
	}
	if (!view_count) { result = 0; goto done; }
	if (!chain_has_space(geometry, 32u + 84u * tiles + 80u * view_count)) {
#if HCU_SCREEN_EFFECT_PROBE
		capacity_refusal = 1u;
#endif
		goto done;
	}
	if (bsp_render_decal_compose_tile_pages(&scratch_page, &scratch_z_page) != 0 ||
		bsp_render_decal_compose_clut_block(0u, &clut_block) != 0 ||
		bsp_render_screen_effect_copy_framebuffer(video, geometry) != 0 ||
		bsp_render_screen_effect_texture_state(&screen_tex0, &screen_clamp) != 0)
		goto done;
	framebuffer_page = video->fb[video->back].address / 2048u;
	framebuffer_width = video->fb[video->back].width / 64u;
	zbuffer_page = video->z.address / 2048u;
	for (i = 0; i < view_count; ++i) {
		uint8_t complement[1024];
		uint32_t palette_index;
		if (hcu_bitmap_dispatch_screen_effect_mask_complement_clut(dispatch, reader,
			views[i].request->frame_index == reader->queue->frame_index ?
			dispatch->screen_effects[(uint16_t)views[i].request->view_index].mask_request_index :
				HALO_PS2_BITMAP_REQUEST_CAPACITY, complement) != HCU_BITMAP_DISPATCH_OK)
			goto done;
		memset(palette, 0, sizeof(palette));
		for (palette_index = 0; palette_index < 256u; ++palette_index)
			palette[palette_index] = (uint32_t)complement[palette_index * 4u] |
				(uint32_t)complement[palette_index * 4u + 1u] << 8 |
				(uint32_t)complement[palette_index * 4u + 2u] << 16 |
				(uint32_t)complement[palette_index * 4u + 3u] << 24;
		if (!decal_compose_emit_palette(geometry, palette, clut_block, 0u) ||
			!emit_view_tiles(geometry, &views[i], screen_tex0, screen_clamp,
				scratch_page, scratch_z_page, framebuffer_page, framebuffer_width,
				zbuffer_page, clut_block))
			goto done;
	}
	/* Restore the full 512x448 target state expected by the following bitmap and
	 * text passes. */
	{
		gs_ad restore[11];
		uint64_t xyoffset = (uint64_t)(2048u - VIDEO_WIDTH / 2u) * 16u |
			(uint64_t)(2048u - VIDEO_HEIGHT / 2u) * 16u << 32;
		uint64_t scissor = (uint64_t)(VIDEO_WIDTH - 1u) << 16 |
			(uint64_t)(VIDEO_HEIGHT - 1u) << 48;
		if (decal_compose_restore_state(restore,
			frame_state(framebuffer_page, framebuffer_width, GS_PSMCT16S, 0u),
			1u,
			GS_ZBUF(zbuffer_page, GS_PSMZ24, 1u),
			GS_TEST(0u, 1u, 0u, 0u, 0u, 0u, 1u, 1u), GS_ALPHA(0u, 1u, 0u, 1u, 0u),
			xyoffset, scissor, 0x80ull | (0x80ull << 32),
			GS_CLAMP(1u, 1u, 0u, 0u, 0u, 0u), 0u,
			GS_TEX1(1u, 0u, 0u, 0u, 0u, 0u, 0u)) != 0 ||
			!decal_compose_emit_ad(geometry, restore, 11u, 0u))
			goto done;
	}
	result = 1;
done:
#if HCU_SCREEN_EFFECT_PROBE
	{
		uint32_t chain_qw_end = chain_valid ? chain_qwords(geometry) : chain_qw_start;
		bsp_render_screen_effect_probe_backend(valid_requests, view_count, tiles,
			timer_cycles() - probe_start, result,
			chain_qw_end >= chain_qw_start ? chain_qw_end - chain_qw_start : 0u,
			capacity_refusal);
	}
#endif
	return result;
}
