#include "stream/hcu_loading_screen.h"
#include "platform/video.h"

#include "render/bsp_render.h"
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
	MASK_W = LOAD_W, MASK_H = LOAD_H, MASK_BYTES = MASK_W * MASK_H * 4,
	/* Loading temporarily reuses menu texture pages. The synchronous CE map
	 * precache reads sources into EE memory and returns before BSP texture
	 * uploads begin, so the shared GS range is idle while these frames render. */
	/* GS base addresses below use 2048-word (8 KiB) allocation pages. Keep the
	 * coverage mask after the complete RGB16 backplate to avoid overlap. */
	LOAD_PAGE = 0, LOAD_PAGES = (LOAD_BYTES + 8191) / 8192,
	MASK_PAGE = LOAD_PAGE + LOAD_PAGES,
	MASK_PAGES = (MASK_BYTES + 8191) / 8192,
	/* Backplate is one upload (8 qwords). The 512x448 PSMCT32 mask is 57344 qwords,
	 * over the GIF IMAGE limit, so gs_upload splits it into two 224-row bands (16
	 * qwords). Plus the END tag: 25 qwords. 40 leaves a spare band. */
	LOAD_CHAIN_QW = 40, FRAME_PACKET_QW = 128
};

static video_t *s_video;
static uint8_t *s_dma;
static size_t s_dma_bytes;
/* LOAD_CHAIN_QW counts 16-byte quadwords; each holds two uint64_t. */
static uint64_t s_upload_chain[LOAD_CHAIN_QW * 2] __attribute__((aligned(64)));
static packet2_t s_packet;
static unsigned s_frame;
static uint64_t s_bytes_read;
static uint32_t s_last_present_cycles;
static float s_progress, s_last_progress;
static int s_ready, s_active, s_rendering, s_hold;
static uint32_t s_max_gap_ms;

static void set_scissor(packet2_t *p, unsigned x0, unsigned x1)
{
	uint64_t value = (uint64_t)x0 | (uint64_t)x1 << 16 |
		(uint64_t)0 << 32 | (uint64_t)(VIDEO_HEIGHT - 1) << 48;
	packet2_add_u64(p, GIF_TAG(1, 0, 0, 0, GIFX_FLG_PACKED, 1));
	packet2_add_u64(p, GIF_REGS_AD);
	packet2_add_u64(p, value); packet2_add_u64(p, 0x40u); /* SCISSOR_1 */
}

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
	packet2_add_u64(p, GIF_TAG(2, 0, 0, 0, GIFX_FLG_PACKED, 1));
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

static void make_mask(const uint16_t *background, uint32_t *mask)
{
	unsigned i;
	for (i = 0; i < MASK_W * MASK_H; ++i) {
		unsigned pixel = background[i];
		unsigned red = (pixel & 31u) << 3;
		unsigned green = ((pixel >> 5) & 31u) << 3;
		unsigned blue = ((pixel >> 10) & 31u) << 3;
		unsigned luminance = (red * 3u + green * 6u + blue) / 10u;
		/* Reuse the backplate as coverage: dark space stays untouched while
		 * visible ring edges and the LOADING glyphs receive the blue tint. */
		unsigned intensity = luminance > 12u ? (luminance - 12u) * 5u : 0u;
		if (intensity > 192u) intensity = 192u;
		mask[i] = (intensity << 24) | (intensity << 16) |
			(intensity << 8) | intensity;
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
	make_mask(background, mask);
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
	SyncDCache(s_upload_chain, (uint8_t *)s_upload_chain + chain_qwords(&chain) * 16u);
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
	if (!s_ready || !s_video || !storage || s_rendering || s_dma_bytes < FRAME_PACKET_QW * 16u) {
		static unsigned s_skip_reports;
		if (s_skip_reports++ < 3u)
			printf("HALO_PS2_LOCAL loading-screen-skip ready=%d video=%d storage=%d rendering=%d dma=%u\n",
				s_ready, s_video != NULL, storage != NULL, s_rendering, (unsigned)s_dma_bytes);
		return;
	}
	s_rendering = 1;
	if (progress > 1.f) progress = 1.f;
	if (progress < 0.f) progress = 0.f;
	/* Keep the sweep monotonic even if read accounting reports a smaller target
	 * or frame timing varies. Ease forward only; the lightbar never retreats. */
	if (progress < s_last_progress) progress = s_last_progress;
	else progress = s_last_progress + (progress - s_last_progress) * 0.2f;
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
		0, 0, VIDEO_WIDTH, VIDEO_HEIGHT, 255, 255, 255, 0xFF, 0);
	/* A narrow column travels strictly left-to-right. Scissoring the full-frame
	 * coverage texture colors only the visible ring and LOADING letters. */
	{
		const unsigned column_w = 36u;
		unsigned left;
		unsigned right;
		x = (int)(progress * (VIDEO_WIDTH - column_w));
		left = (unsigned)x;
		right = left + column_w - 1u;
		set_scissor(&s_packet, left, right);
		sprite(&s_packet, MASK_PAGE, GS_PSMCT32, MASK_W, MASK_H,
			0, 0, VIDEO_WIDTH, VIDEO_HEIGHT, 48, 132, 255, tint, 1);
		set_scissor(&s_packet, 0u, VIDEO_WIDTH - 1u);
	}
	packet2_update(&s_packet, draw_finish(s_packet.next));
	SyncDCache(storage, storage + (s_packet.next - s_packet.base) * 16u);
	dma_channel_send_packet2(&s_packet, DMA_CHANNEL_GIF, 1);
	dma_wait_fast(); draw_wait_finish(); video_present(s_video);
	{
		uint32_t now = timer_cycles();
		uint32_t gap = (uint32_t)timer_ms(s_last_present_cycles, now);
		if (s_last_present_cycles && gap > s_max_gap_ms) s_max_gap_ms = gap;
		s_last_present_cycles = now;
	}
	++s_frame; s_rendering = 0;
}

void hcu_loading_screen_begin(void)
{
	/* The main menu and BSP renderer share the GS texture window. Reload into
	 * page zero when a loading interval begins: menu textures can be replaced
	 * after selection, and BSP cache uploads begin at page 17 only after the
	 * synchronous precache callback returns. */
	if (!s_ready) {
		printf("HALO_PS2_FAIL loading-screen-unavailable\n");
		return;
	}
	if (s_hold && s_active) return;
	if (!upload_assets()) {
		printf("HALO_PS2_FAIL loading-screen-assets\n");
		return;
	}
	s_bytes_read = 0;
	s_progress = 0.f; s_last_progress = 0.f;
	s_active = 1;
	printf("HALO_PS2_LOCAL loading-screen-begin frame=%u\n", s_frame);
	present(0.01f);
}

void hcu_loading_screen_hold(void)
{
	s_hold = 1;
}

void hcu_loading_screen_release(void)
{
	if (!s_hold) return;
	s_hold = 0;
	printf("HALO_PS2_LOCAL loading-screen-release max-gap-ms=%u\n", (unsigned)s_max_gap_ms);
	hcu_loading_screen_end();
	bsp_render_restore_font();
}

void hcu_loading_screen_end(void)
{
	unsigned frames = 0;
	packet2_t *finish;
	if (s_hold && s_active) return;
	if (s_active) {
		s_progress = 1.f;
		/* Match CE's easing tail: continue presenting until the sweep passes the
		 * right edge and its backdrop pulse fades toward black. */
		do {
			present(1.f);
		} while (++frames < 40u && s_last_progress < 0.995f);
		s_active = 0;
	}
	printf("HALO_PS2_LOCAL loading-screen-end frames=%u bytes=%llu presented=%u progress=%.3f\n",
		frames, (unsigned long long)s_bytes_read, s_frame, (double)s_last_progress);
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
	const uint64_t byte_budget = (s_hold ? 160u : 32u) * 1024u * 1024u;
	if (!s_active || !bytes) return;
	/* Reads may revisit bytes, so use them as a coarse indicator and leave the
	 * final tenth for CE's end callback. A byte budget avoids reaching the end
	 * of the sweep early during a long source scan. */
	if (!s_bytes_read) printf("HALO_PS2_LOCAL loading-screen-first-read bytes=%u\n", (unsigned)bytes);
	s_bytes_read += bytes;
	s_progress = s_bytes_read >= byte_budget ? 0.9f :
		(float)s_bytes_read * (0.9f / (float)byte_budget);
	/* Optical/tag reads can arrive in 16 KiB chunks. A 30 Hz cap keeps each
	 * synchronization useful without turning every small read into a vblank. */
	if (timer_ms(s_last_present_cycles, timer_cycles()) >= (1000.f / 30.f))
		present(s_progress);
}
