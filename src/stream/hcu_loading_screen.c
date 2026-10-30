#include "stream/hcu_loading_screen.h"
#include "platform/video.h"

#include "render/chain.h"
#include "render/gs.h"
#include "render/upload.h"
#include "stream/hcu_file_bridge.h"

#include <dma.h>
#include <draw.h>
#include <packet2.h>
#include <kernel.h>
#include <malloc.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>

enum {
	LOAD_W = 512, LOAD_H = 256, LOAD_BYTES = LOAD_W * LOAD_H * 2,
	MASK_W = 128, MASK_H = 16, MASK_BYTES = MASK_W * MASK_H * 4,
	LOAD_PAGE = 110, LOAD_PAGES = 32, MASK_PAGE = 142, MASK_PAGES = 1,
	LOAD_CHAIN_QW = 16, FRAME_PACKET_QW = 128
};

static video_t *s_video;
static uint8_t *s_dma;
static size_t s_dma_bytes;
static uint64_t s_upload_chain[LOAD_CHAIN_QW] __attribute__((aligned(64)));
static packet2_t s_packet;
static unsigned s_frame;
static float s_progress, s_last_progress, s_wobble;
static int s_ready, s_active, s_rendering;

static void texture_state(packet2_t *p, unsigned page, unsigned psm,
	unsigned w, unsigned h)
{
	unsigned tw = 0, th = 0;
	while ((1u << tw) < w) ++tw;
	while ((1u << th) < h) ++th;
	packet2_add_u64(p, GIF_TAG(4, 0, 0, 0, GIFX_FLG_PACKED, 1));
	packet2_add_u64(p, GIF_REGS_AD);
	packet2_add_u64(p, GS_TEX0((s_video->tex_base + page * 2048u) / 64u,
		(w + 63u) / 64u, psm, tw, th, 1, page == MASK_PAGE ? 0 : 1,
		0, GS_PSMCT32, 0, 0, 1));
	packet2_add_u64(p, GS_A_TEX0_1);
	packet2_add_u64(p, GS_TEX1(1, 0, 1, 1, 0, 0, 0));
	packet2_add_u64(p, GS_A_TEX1_1);
	packet2_add_u64(p, GS_CLAMP(1, 1, 0, w - 1u, 0, h - 1u));
	packet2_add_u64(p, GS_A_CLAMP_1);
	packet2_add_u64(p, 0); packet2_add_u64(p, GS_A_TEXFLUSH);
}

static void sprite(packet2_t *p, unsigned page, unsigned psm,
	unsigned w, unsigned h, int x0, int y0, int x1, int y1,
	unsigned cr, unsigned cg, unsigned cb, unsigned alpha, int additive)
{
	int ox = 2048 - VIDEO_WIDTH / 2, oy = 2048 - VIDEO_HEIGHT / 2;
	texture_state(p, page, psm, w, h);
	packet2_add_u64(p, GIF_TAG(1, 0, 0, 0, GIFX_FLG_PACKED, 1));
	packet2_add_u64(p, GIF_REGS_AD);
	packet2_add_u64(p, GS_ALPHA(0, 1, 0, 1, 0)); packet2_add_u64(p, GS_A_ALPHA_1);
	packet2_add_u64(p, GS_TEST(0, 1, 0, 0, 0, 0, 0, 1)); packet2_add_u64(p, GS_A_TEST_1);
	packet2_add_u64(p, GIF_TAG(2, 1, 1,
		GS_PRIM(GSX_PRIM_SPRITE, 0, 1, 0, additive, 0, 1, 0, 0),
		GIFX_FLG_PACKED, 3));
	packet2_add_u64(p, 0x531);
	packet2_add_u64(p, (uint64_t)(cr & 0xFFu) | (uint64_t)(cg & 0xFFu) << 32);
	packet2_add_u64(p, (uint64_t)(cb & 0xFFu) | (uint64_t)(alpha & 0xFFu) << 32);
	packet2_add_u64(p, 0); packet2_add_u64(p, 0);
	packet2_add_u64(p, (uint64_t)((ox + x0) * 16) | (uint64_t)((oy + y0) * 16) << 32);
	packet2_add_u64(p, 0x00FFFFFFu);
	packet2_add_u64(p, (uint64_t)(cr & 0xFFu) | (uint64_t)(cg & 0xFFu) << 32);
	packet2_add_u64(p, (uint64_t)(cb & 0xFFu) | (uint64_t)(alpha & 0xFFu) << 32);
	packet2_add_u64(p, (uint64_t)(w << 4) | (uint64_t)(h << 4) << 32); packet2_add_u64(p, 0);
	packet2_add_u64(p, (uint64_t)((ox + x1) * 16) | (uint64_t)((oy + y1) * 16) << 32);
	packet2_add_u64(p, 0x00FFFFFFu);
}

static void make_mask(uint32_t *mask)
{
	unsigned x, y;
	for (y = 0; y < MASK_H; ++y) {
		double gy = pow(sin(3.1415 * (double)y / 15.0), 0.75);
		for (x = 0; x < MASK_W; ++x) {
			double gx = sin(3.1415 * (double)x / 127.0);
			unsigned intensity = (unsigned)((gx * gy * (250.0 / 255.0) + 5.0 / 255.0) * 255.0);
			/* CE's A8B8G8R8 mask has the same intensity in all channels. */
			mask[y * MASK_W + x] = (intensity << 24) | (intensity << 16) |
				(intensity << 8) | intensity;
		}
	}
}

static uint16_t *load_background(void)
{
	unsigned long size = 0, got = 0;
	uint16_t *background;
	int file = hcu_file_bridge_open("D:\\packages\\load.rgb", &size);
	if (file < 0 || size != LOAD_BYTES) {
		if (file >= 0) hcu_file_bridge_close(file);
		return NULL;
	}
	background = (uint16_t *)memalign(64u, LOAD_BYTES);
	if (!background) { hcu_file_bridge_close(file); return NULL; }
	if (!hcu_file_bridge_read(file, background, LOAD_BYTES, &got) || got != LOAD_BYTES) {
		hcu_file_bridge_close(file); free(background); return NULL;
	}
	hcu_file_bridge_close(file);
	return background;
}

void hcu_loading_screen_bind(void *video_ptr, void *dma_storage, size_t dma_bytes)
{
	chain_t chain;
	video_t *video = (video_t *)video_ptr;
	uint16_t *background;
	uint32_t *mask;
	if (!video || !dma_storage || dma_bytes < FRAME_PACKET_QW * 16u) return;
	s_video = video; s_dma = (uint8_t *)dma_storage; s_dma_bytes = dma_bytes;
	background = load_background();
	mask = (uint32_t *)memalign(64u, MASK_BYTES);
	if (!background || !mask) { free(background); free(mask); return; }
	make_mask(mask);
	SyncDCache(background, (uint8_t *)background + LOAD_BYTES);
	SyncDCache(mask, (uint8_t *)mask + MASK_BYTES);
	chain_init(&chain, s_upload_chain, LOAD_CHAIN_QW);
	if (gs_upload(&chain, background, LOAD_BYTES,
		(video->tex_base + LOAD_PAGE * 2048u) / 64u, LOAD_W / 64u,
		GS_PSMCT16S, LOAD_W, LOAD_H) ||
		gs_upload(&chain, mask, MASK_BYTES,
		(video->tex_base + MASK_PAGE * 2048u) / 64u, MASK_W / 64u,
		GS_PSMCT32, MASK_W, MASK_H)) { free(background); free(mask); return; }
	chain_end(&chain, 0);
	SyncDCache(s_upload_chain, s_upload_chain + chain_qwords(&chain));
	dma_channel_send_chain(DMA_CHANNEL_GIF, s_upload_chain, 0, 0, 0);
	dma_wait_fast(); free(background); free(mask); s_ready = 1;
}

static void present(float progress)
{
	unsigned char *storage = s_dma;
	int x;
	if (!s_ready || !s_video || !storage || s_rendering || s_dma_bytes < FRAME_PACKET_QW * 16u)
		return;
	s_rendering = 1;
	s_wobble += 0.01f;
	progress = (float)((sin(s_wobble) * 0.05 + progress - s_last_progress) * 0.2 + s_last_progress);
	if (progress > 0.98f) progress = 0.98f;
	if (progress < 0.f) progress = 0.f;
	s_last_progress = progress;
	packet2_reset(&s_packet, 0);
	s_packet.max_qwords_count = FRAME_PACKET_QW; s_packet.type = P2_TYPE_NORMAL;
	s_packet.mode = P2_MODE_NORMAL; s_packet.base = s_packet.next = (qword_t *)storage;
	video_add_setup_env(s_video, &s_packet);
	video_add_clear(s_video, &s_packet, 0, 0, 0);
	/* The CE backplate is a 320x240 retail composition scaled to the PS2 field. */
	sprite(&s_packet, LOAD_PAGE, GS_PSMCT16S, LOAD_W, LOAD_H,
		0, 0, VIDEO_WIDTH, VIDEO_HEIGHT, 128, 128, 128, 0x80, 0);
	/* Retail progress_bar.c moves its 128-pixel sine mask across a 640-pixel
	 * logical field, with a sinusoidal ease and a blue brightness envelope. */
	x = (int)(progress * 768.f) - 128;
	{
		float glow = powf(fmaxf(0.f, sinf(progress * 3.14159f)), 0.9f);
		unsigned tint = (unsigned)(glow * 255.f);
		sprite(&s_packet, MASK_PAGE, GS_PSMCT32, MASK_W, MASK_H,
			x, 120, x + 128, 136, 40, 112, 255, tint, 1);
	}
	packet2_update(&s_packet, draw_finish(s_packet.next));
	SyncDCache(storage, storage + (s_packet.next - s_packet.base) * 16u);
	dma_channel_send_packet2(&s_packet, DMA_CHANNEL_GIF, 1);
	dma_wait_fast(); draw_wait_finish(); video_present(s_video);
	++s_frame; s_rendering = 0;
}

void hcu_loading_screen_begin(void)
{
	if (!s_ready) return;
	s_progress = 0.f; s_last_progress = 0.f; s_wobble = 0.f;
	s_active = 1; present(0.01f);
}

void hcu_loading_screen_end(void)
{
	unsigned frames = 0;
	if (!s_active) return;
	s_progress = 1.f;
	/* Match CE's easing tail: continue presenting until the sweep reaches the
	 * right edge instead of stopping on the first final-progress update. */
	do {
		present(1.f);
	} while (++frames < 40u && s_last_progress < 0.995f);
	s_active = 0;
}

void hcu_loading_screen_file_read(uint32_t bytes)
{
	if (!s_active || !bytes) return;
	/* Reads are not a byte-perfect measure of remaining CE work. Advance
	 * monotonically with a soft asymptote; CE's renderer likewise eases updates. */
	s_progress += (1.f - s_progress) * (bytes > 65536u ? 0.075f : 0.018f);
	if ((s_frame & 1u) == 0u) present(s_progress);
}
