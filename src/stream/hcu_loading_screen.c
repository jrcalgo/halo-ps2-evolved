#include "stream/hcu_loading_screen.h"
#include "platform/video.h"

#include "render/chain.h"
#include "render/gs.h"
#include "render/upload.h"
#include "stream/hcu_file_bridge.h"
#include "platform/timer.h"

#include <dma.h>
#include <draw.h>
#include <packet2.h>
#include <stdio.h>
#include <kernel.h>
#include <malloc.h>
#include <stdlib.h>
#include <stdio.h>
#include <string.h>
#include <math.h>

enum {
	LOAD_W = 512, LOAD_H = 448, LOAD_BYTES = LOAD_W * LOAD_H * 2,
	MASK_W = 128, MASK_H = 16, MASK_BYTES = MASK_W * MASK_H * 4,
	/* Loading temporarily reuses menu texture pages. The synchronous CE map
	 * precache reads sources into EE memory and returns before BSP texture
	 * uploads begin, so the shared GS range is idle while these frames render. */
	LOAD_PAGE = 0, LOAD_PAGES = 64, MASK_PAGE = LOAD_PAGE + LOAD_PAGES,
	MASK_PAGES = 1,
	LOAD_CHAIN_QW = 16, FRAME_PACKET_QW = 128
};

static video_t *s_video;
static uint8_t *s_dma;
static size_t s_dma_bytes;
static uint64_t s_upload_chain[LOAD_CHAIN_QW] __attribute__((aligned(64)));
static packet2_t s_packet;
static unsigned s_frame;
static uint64_t s_bytes_read;
static uint32_t s_last_present_cycles;
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
	video_t *video = (video_t *)video_ptr;
	s_ready = 0;
	s_active = 0;
	if (!video || !dma_storage || dma_bytes < FRAME_PACKET_QW * 16u) return;
	if ((video->tex_base & 2047u) != 0u ||
		video->tex_base > VIDEO_VRAM_WORDS ||
		(LOAD_PAGE + LOAD_PAGES + MASK_PAGES) * 2048u >
			VIDEO_VRAM_WORDS - video->tex_base) return;
	s_video = video; s_dma = (uint8_t *)dma_storage; s_dma_bytes = dma_bytes;
	s_ready = 1;
}

static int upload_assets(void)
{
	chain_t chain;
	uint16_t *background;
	uint32_t *mask;
	if (!s_video || !s_dma || !s_ready) return 0;
	background = load_background();
	mask = (uint32_t *)memalign(64u, MASK_BYTES);
	if (!background || !mask) { free(background); free(mask); return 0; }
	make_mask(mask);
	SyncDCache(background, (uint8_t *)background + LOAD_BYTES);
	SyncDCache(mask, (uint8_t *)mask + MASK_BYTES);
	chain_init(&chain, s_upload_chain, LOAD_CHAIN_QW);
	if (gs_upload(&chain, background, LOAD_BYTES,
		(s_video->tex_base + LOAD_PAGE * 2048u) / 64u, LOAD_W / 64u,
		GS_PSMCT16S, LOAD_W, LOAD_H) ||
		gs_upload(&chain, mask, MASK_BYTES,
		(s_video->tex_base + MASK_PAGE * 2048u) / 64u, MASK_W / 64u,
		GS_PSMCT32, MASK_W, MASK_H)) { free(background); free(mask); return 0; }
	chain_end(&chain, 0);
	SyncDCache(s_upload_chain, s_upload_chain + chain_qwords(&chain));
	dma_channel_send_chain(DMA_CHANNEL_GIF, s_upload_chain, 0, 0, 0);
	dma_wait_fast(); free(background); free(mask);
	return 1;
}

static void present(float progress)
{
	unsigned char *storage = s_dma;
	int x;
	float glow;
	unsigned tint;
	if (!s_ready || !s_video || !storage || s_rendering || s_dma_bytes < FRAME_PACKET_QW * 16u)
		return;
	s_rendering = 1;
	s_wobble += 0.01f;
	progress = (float)((sin(s_wobble) * 0.05 + progress - s_last_progress) * 0.2 + s_last_progress);
	if (progress > 1.f) progress = 1.f;
	if (progress < 0.f) progress = 0.f;
	s_last_progress = progress;
	packet2_reset(&s_packet, 0);
	s_packet.max_qwords_count = FRAME_PACKET_QW; s_packet.type = P2_TYPE_NORMAL;
	s_packet.mode = P2_MODE_NORMAL; s_packet.base = s_packet.next = (qword_t *)storage;
	video_add_setup_env(s_video, &s_packet);
	video_add_clear(s_video, &s_packet, 0, 0, 0);
	/* CE modulates the loading image with a sin(progress*pi)^0.9 pulse. */
	glow = powf(fmaxf(0.f, sinf(progress * 3.14159f)), 0.9f);
	tint = (unsigned)(glow * 255.f);
	/* The 512x448 backplate matches the PS2 field without aspect distortion. */
	sprite(&s_packet, LOAD_PAGE, GS_PSMCT16S, LOAD_W, LOAD_H,
		0, 0, VIDEO_WIDTH, VIDEO_HEIGHT, tint, tint, tint, 0x80, 0);
	/* Retail progress_bar.c moves its 128-pixel sine mask from just left of the
	 * field to just beyond the right edge. Scale the travel to this 512-pixel
	 * PS2 frame, retaining the CE easing and blue brightness envelope. */
	x = (int)(progress * (VIDEO_WIDTH + MASK_W)) - MASK_W;
	{
		sprite(&s_packet, MASK_PAGE, GS_PSMCT32, MASK_W, MASK_H,
			x, VIDEO_HEIGHT / 2 - MASK_H / 2,
			x + MASK_W, VIDEO_HEIGHT / 2 + MASK_H / 2,
			40, 112, 255, tint, 1);
	}
	packet2_update(&s_packet, draw_finish(s_packet.next));
	SyncDCache(storage, storage + (s_packet.next - s_packet.base) * 16u);
	dma_channel_send_packet2(&s_packet, DMA_CHANNEL_GIF, 1);
	dma_wait_fast(); draw_wait_finish(); video_present(s_video);
	s_last_present_cycles = timer_cycles();
	++s_frame; s_rendering = 0;
}

void hcu_loading_screen_begin(void)
{
	/* The main menu and BSP renderer share the GS texture window. Reload into
	 * page zero when a loading interval begins: menu textures can be replaced
	 * after selection, and BSP cache uploads begin at page 17 only after the
	 * synchronous precache callback returns. */
	if (!s_ready || !upload_assets()) return;
	s_bytes_read = 0;
	s_progress = 0.f; s_last_progress = 0.f; s_wobble = 0.f;
	s_active = 1; present(0.01f);
}

void hcu_loading_screen_end(void)
{
	unsigned frames = 0;
	packet2_t *finish;
	if (s_active) {
		s_progress = 1.f;
		/* Match CE's easing tail: continue presenting until the sweep passes the
		 * right edge and its backdrop pulse fades toward black. */
		do {
			present(1.f);
		} while (++frames < 40u && s_last_progress < 0.995f);
		s_active = 0;
	}
	/* The menu and any loading present wait for GS FINISH and clear it.
	 * CE's first draw_wait_finish needs one still pending, or it spins on
	 * the last menu frame and never reaches gameplay. */
	finish = packet2_create(2, P2_TYPE_NORMAL, P2_MODE_NORMAL, 0);
	if (!finish) return;
	packet2_update(finish, draw_finish(finish->next));
	dma_channel_send_packet2(finish, DMA_CHANNEL_GIF, 1);
	dma_wait_fast();
	packet2_free(finish);
	printf("HALO_PS2_LOCAL gs-finish-primed\n");
}

void hcu_loading_screen_file_read(uint32_t bytes)
{
	const uint64_t byte_budget = 32u * 1024u * 1024u;
	if (!s_active || !bytes) return;
	/* Reads may revisit bytes, so use them as a coarse indicator and leave the
	 * final tenth for CE's end callback. A byte budget avoids reaching the end
	 * of the sweep early during a long source scan. */
	s_bytes_read += bytes;
	s_progress = s_bytes_read >= byte_budget ? 0.9f :
		(float)s_bytes_read * (0.9f / (float)byte_budget);
	/* Optical/tag reads can arrive in 16 KiB chunks. A 30 Hz cap keeps each
	 * synchronization useful without turning every small read into a vblank. */
	if (timer_ms(s_last_present_cycles, timer_cycles()) >= (1000.f / 30.f))
		present(s_progress);
}
