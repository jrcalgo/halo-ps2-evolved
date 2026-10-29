#include <stdio.h>
#include <string.h>
#include "stream/hcu_bitmap_screen_effect.h"
#include "render/bsp_render.h"
#include "platform/video.h"
#include "render/decal_compose.h"

#define CHECK(x) do { if (!(x)) { fprintf(stderr, "FAIL %s:%d: %s\n", __FILE__, __LINE__, #x); return 1; } } while (0)

bsp_render_screen_effect_probe g_bsp_render_screen_effect_probe;
#define probe g_bsp_render_screen_effect_probe
static int copy_result, copy_calls;
static uint8_t chain_memory[20000u * 16u] __attribute__((aligned(16)));

uint32_t test_timer_cycles(void) { static uint32_t t; return ++t; }

void bsp_render_screen_effect_probe_backend(uint32_t requests, uint32_t views,
	uint32_t tiles, uint32_t cycles, int32_t status, uint32_t emitted_qw,
	uint32_t capacity_refusal)
{
	probe.valid_requests = requests; probe.valid_views = views; probe.tiles = tiles;
	probe.backend_cycles = cycles; probe.backend_status = status; probe.emitted_qw = emitted_qw;
	probe.capacity_refusals += capacity_refusal;
	probe.copy_refusals += capacity_refusal;
}

int32_t hcu_bitmap_dispatch_screen_effect_get(const hcu_bitmap_dispatch_context *ctx,
	uint32_t generation, uint32_t frame, uint16_t view, halo_ps2_screen_effect_state *out)
{
	if (!ctx || !out || generation != ctx->screen_effect_generation ||
		frame != ctx->screen_effect_frame_index || view >= HALO_PS2_BITMAP_MAX_VIEWS) return -1;
	*out = ctx->screen_effects[view];
	return out->valid ? 1 : 0;
}

int32_t hcu_bitmap_dispatch_screen_effect_mask_get(const hcu_bitmap_dispatch_context *ctx,
	uint32_t generation, uint32_t frame, uint16_t view, uint64_t *tex0, uint64_t *clamp)
{
	if (!ctx || !tex0 || !clamp || generation != ctx->screen_effect_generation ||
		frame != ctx->screen_effect_frame_index || view >= HALO_PS2_BITMAP_MAX_VIEWS ||
		!(ctx->screen_effect_mask_texture_valid_mask & (1u << view))) return 0;
	*tex0 = ctx->screen_effect_mask_tex0[view]; *clamp = ctx->screen_effect_mask_clamp[view];
	return 1;
}

int32_t hcu_bitmap_dispatch_screen_effect_mask_complement_clut(
	hcu_bitmap_dispatch_context *ctx, const halo_ps2_bitmap_request_reader *reader,
	uint32_t request_index,
#ifdef HCU_SCREEN_EFFECT_TEST_P4
	uint8_t clut[64])
#else
	uint8_t clut[1024])
#endif
{
	(void)ctx;
	if (!reader || request_index >= reader->count || !clut) return HCU_BITMAP_DISPATCH_E_ARGUMENT;
#ifdef HCU_SCREEN_EFFECT_TEST_P4
	memset(clut, 128, 64u);
#else
	memset(clut, 128, 1024);
#endif
	return HCU_BITMAP_DISPATCH_OK;
}

int bsp_render_decal_compose_tile_pages(uint32_t *color, uint32_t *z)
{ *color = 2u; *z = 3u; return 0; }
int bsp_render_decal_compose_clut_block(unsigned channel, uint32_t *block)
{ if (channel || !block) return -1; *block = 4u; return 0; }
int bsp_render_screen_effect_texture_state(u64 *tex0, u64 *clamp)
{ *tex0 = GS_TEX0(5u, 1u, GS_PSMCT16S, 7u, 7u, 0u, 1u, 4u, GS_PSMCT32, 0u, 0u, 0u); *clamp = GS_CLAMP(1u, 1u, 0u, 0u, 0u, 0u); return 0; }
int bsp_render_screen_effect_copy_framebuffer(const video_t *video, chain_t *geometry)
{
	(void)video; (void)geometry; copy_calls++;
	bsp_screen_copy_probe_event(&probe, BSP_SCREEN_COPY_ATTEMPT);
	if (copy_result) { bsp_screen_copy_probe_event(&probe, BSP_SCREEN_COPY_FENCE_REFUSAL); return -1; }
	bsp_screen_copy_probe_event(&probe, BSP_SCREEN_COPY_QUEUED);
	return 0;
}

static void setup(hcu_bitmap_dispatch_context *dispatch,
	halo_ps2_bitmap_request_reader *reader, halo_ps2_bitmap_request_queue *queue,
	halo_ps2_bitmap_request requests[4], video_t *video)
{
	memset(dispatch, 0, sizeof(*dispatch)); memset(reader, 0, sizeof(*reader));
	memset(queue, 0, sizeof(*queue)); memset(requests, 0, sizeof(halo_ps2_bitmap_request) * 4u);
	memset(video, 0, sizeof(*video)); memset(&probe, 0, sizeof(probe));
	dispatch->screen_effect_generation = 9u; dispatch->screen_effect_frame_index = 20u;
	reader->held = 1u; reader->queue = queue; reader->requests = requests; reader->count = 4u; reader->generation = 9u;
	queue->frame_index = 20u;
	video->back = 0; video->fb[0].address = 100u * 2048u; video->fb[0].width = VIDEO_WIDTH;
	video->fb[0].height = VIDEO_HEIGHT; video->fb[0].psm = GS_PSMCT16S; video->z.address = 200u * 2048u;
	for (unsigned i = 0; i < 4u; ++i) {
		requests[i].generation = 9u; requests[i].frame_index = 20u;
		requests[i].view_index = (int16_t)i; requests[i].screen_effect_mask = 1u;
		requests[i].vertices[0].x = 0.0f; requests[i].vertices[0].y = 0.0f;
		requests[i].vertices[1].x = 128.0f; requests[i].vertices[1].y = 0.0f;
		requests[i].vertices[2].x = 128.0f; requests[i].vertices[2].y = 64.0f;
		requests[i].vertices[3].x = 0.0f; requests[i].vertices[3].y = 64.0f;
		dispatch->screen_effects[i].valid = 0u;
		dispatch->screen_effects[i].mask_request_index = (uint8_t)i;
		dispatch->screen_effect_mask_tex0[i] = (uint64_t)7u << 26 | (uint64_t)7u << 30;
		dispatch->screen_effect_mask_texture_valid_mask |= 1u << i;
	}
}

int main(void)
{
	hcu_bitmap_dispatch_context dispatch;
	halo_ps2_bitmap_request_reader reader;
	halo_ps2_bitmap_request_queue queue;
	halo_ps2_bitmap_request requests[4];
	video_t video;
	chain_t chain;
	int32_t result;
	setup(&dispatch, &reader, &queue, requests, &video);
	chain_init(&chain, chain_memory, 20000u);
	result = hcu_bitmap_screen_effect_backend_native(NULL, &reader, &dispatch, &video, &chain, NULL, NULL);
	CHECK(result == 0 && probe.valid_requests == 0u && probe.valid_views == 0u);
	CHECK(copy_calls == 0 && probe.copy_attempts == 0u && probe.copy_queued == 0u && probe.emitted_qw == 0u);

	setup(&dispatch, &reader, &queue, requests, &video);
	dispatch.screen_effects[0].valid = 1u; dispatch.screen_effects[1].valid = 1u;
	dispatch.screen_effects[2].valid = dispatch.screen_effects[3].valid = 0u;
	reader.count = 2u;
	chain_init(&chain, chain_memory, 20000u);
	result = hcu_bitmap_screen_effect_backend_native(NULL, &reader, &dispatch, &video, &chain, NULL, NULL);
	CHECK(result == 1 && probe.valid_requests == 2u && probe.valid_views == 2u);
	CHECK(probe.tiles == 8u && copy_calls == 1 && probe.copy_attempts == 1u && probe.copy_queued == 1u);
	CHECK(probe.emitted_qw > 0u && probe.backend_cycles > 0u && probe.backend_status == 1);

	setup(&dispatch, &reader, &queue, requests, &video);
	dispatch.screen_effects[0].valid = 1u; reader.count = 1u;
	chain_init(&chain, chain_memory, 8u);
	result = hcu_bitmap_screen_effect_backend_native(NULL, &reader, &dispatch, &video, &chain, NULL, NULL);
	CHECK(result == -1 && probe.valid_requests == 1u && probe.valid_views == 1u);
	CHECK(probe.copy_attempts == 0u && probe.capacity_refusals == 1u && probe.copy_refusals == 1u);
	CHECK(copy_calls == 1);

	setup(&dispatch, &reader, &queue, requests, &video);
	dispatch.screen_effects[0].valid = 1u; reader.count = 1u; copy_result = -1;
	chain_init(&chain, chain_memory, 20000u);
	result = hcu_bitmap_screen_effect_backend_native(NULL, &reader, &dispatch, &video, &chain, NULL, NULL);
	CHECK(result == -1 && probe.copy_attempts == 1u && probe.copy_queued == 0u);
	CHECK(probe.copy_fence_refusals == 1u && probe.copy_refusals == 1u);
	printf("screen-effect-probe-ok no-effect=0 multi-view-copy=1 capacity-refusal=1 fence-refusal=1\n");
	return 0;
}
