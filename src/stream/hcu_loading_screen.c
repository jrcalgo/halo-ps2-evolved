#include "stream/hcu_loading_screen.h"
#include "stream/hcu_boot_diag.h"
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

/* The retail Xbox loading screen (CE source/interface/progress_bar.c, "glowy halo gravy"), redrawn for the PS2 GS.
 *
 * Retail draws, every progress update:
 *   1. the previous frame again, blurred and 1% stretched, at alpha 0.9 (alpha 0.9 - (progress - 0.9) * 9 once the
 *      load is past 90%), onto a cleared frame: a trail that fades behind everything that moves;
 *   2. the 320x240 loading picture (an edge-lit Halo ring with "LOADING...", embedded in default.xbe; the image
 *      comes from the retail disc at build time, tools/build_hcu_loading_assets.py) added through a 128x16
 *      procedural mask, intensity (sin(pi x/127) * sin(pi y/15)^0.75 * 250/255 + 5/255), which sweeps left to right
 *      as the load advances (mask position progress * 768 - 128 on a 640 wide screen), scaled by sin(progress pi)^0.9.
 * The GS cannot multiply two textures, so the mask is a grid of Gouraud triangle strips whose vertex colours carry
 * the mask value; the picture is the only texture. The previous frame is read straight from the other frame buffer. */

enum {
	LOAD_W = 512, LOAD_H = 448, LOAD_BYTES = LOAD_W * LOAD_H * 2,
	/* Loading temporarily reuses menu texture pages. The synchronous CE map precache reads sources into EE memory
	 * and returns before BSP texture uploads begin, so the shared GS range is idle while these frames render. GS base
	 * addresses below use 2048-word (8 KiB) allocation pages. */
	LOAD_PAGE = 0, LOAD_PAGES = (LOAD_BYTES + 8191) / 8192,
	/* The picture is one upload (8 qwords); with the END tag, 40 leaves a spare band. */
	LOAD_CHAIN_QW = 40,
	/* A frame: environment, clear, the trail sprite (about 20 qwords) and MASK_ROWS strips of 1 + 2 (MASK_COLS + 1)
	 * vertices * 3 qwords. */
	MASK_COLS = 12, MASK_ROWS = 8,
	FRAME_PACKET_QW = 1024
};

static video_t *s_video;
static uint8_t *s_dma;
static size_t s_dma_bytes;
/* LOAD_CHAIN_QW counts 16-byte quadwords; each holds two uint64_t. */
static uint64_t s_upload_chain[LOAD_CHAIN_QW * 2] __attribute__((aligned(64)));
static packet2_t s_packet;
static unsigned s_frame;
static unsigned s_begin_frame;
static uint64_t s_bytes_read;
static uint32_t s_last_present_cycles;
static float s_progress, s_last_progress, s_wobble;
static int s_ready, s_active, s_rendering, s_hold, s_finishing;
static uint32_t s_max_gap_ms;

static void texture_state(packet2_t *p, uint32_t base_words, unsigned psm, unsigned w, unsigned h)
{
	unsigned tw = 0, th = 0;
	while ((1u << tw) < w) ++tw;
	while ((1u << th) < h) ++th;
	packet2_add_u64(p, GIF_TAG(4, 0, 0, 0, GIFX_FLG_PACKED, 1));
	packet2_add_u64(p, GIF_REGS_AD);
	/* RGB from the texture, alpha from the vertex, modulated. */
	packet2_add_u64(p, GS_TEX0(base_words / 64u, (w + 63u) / 64u, psm, tw, th, 0, 0, 0, GS_PSMCT32, 0, 0, 1));
	packet2_add_u64(p, GS_A_TEX0_1);
	packet2_add_u64(p, GS_TEX1(1, 0, 1, 1, 0, 0, 0));
	packet2_add_u64(p, GS_A_TEX1_1);
	packet2_add_u64(p, GS_CLAMP(1, 1, 0, w - 1u, 0, h - 1u));
	packet2_add_u64(p, GS_A_CLAMP_1);
	packet2_add_u64(p, 0); packet2_add_u64(p, GS_A_TEXFLUSH);
}

/* Additive blend (source colour * source alpha + destination); depth test off. */
static void blend_state(packet2_t *p)
{
	packet2_add_u64(p, GIF_TAG(2, 0, 0, 0, GIFX_FLG_PACKED, 1));
	packet2_add_u64(p, GIF_REGS_AD);
	packet2_add_u64(p, GS_ALPHA(0, 2, 0, 1, 0)); packet2_add_u64(p, GS_A_ALPHA_1);
	packet2_add_u64(p, GS_TEST(0, 1, 0, 0, 0, 0, 0, 1)); packet2_add_u64(p, GS_A_TEST_1);
}

static void add_vertex(packet2_t *p, unsigned r, unsigned g, unsigned b, unsigned a, float u, float v, float x, float y)
{
	const int ox = 2048 - VIDEO_WIDTH / 2, oy = 2048 - VIDEO_HEIGHT / 2;
	if (u < 0.f) u = 0.f;
	if (u > (float)(LOAD_W - 1)) u = (float)(LOAD_W - 1);
	if (v < 0.f) v = 0.f;
	if (v > (float)(LOAD_H - 1)) v = (float)(LOAD_H - 1);
	packet2_add_u64(p, (uint64_t)(r & 0xFFu) | (uint64_t)(g & 0xFFu) << 32);
	packet2_add_u64(p, (uint64_t)(b & 0xFFu) | (uint64_t)(a & 0xFFu) << 32);
	packet2_add_u64(p, (uint64_t)(unsigned)(u * 16.f) | (uint64_t)(unsigned)(v * 16.f) << 32); packet2_add_u64(p, 0);
	packet2_add_u64(p, (uint64_t)(unsigned)(((float)ox + x) * 16.f) |
		(uint64_t)(unsigned)(((float)oy + y) * 16.f) << 32);
	packet2_add_u64(p, 0x00FFFFFFu);
}

/* Retail's feedback pass: the other frame buffer (the frame last shown) sampled from x 3..637 of 640 and y 0..480, so
 * each generation is stretched 1% horizontally, drawn over a cleared frame at `alpha` (0..128 is 0..1). */
static void trail(packet2_t *p, unsigned alpha)
{
	const float u0 = 3.f * (float)LOAD_W / 640.f, u1 = 637.f * (float)LOAD_W / 640.f;
	texture_state(p, (uint32_t)s_video->fb[s_video->back ^ 1].address, GS_PSMCT16S, LOAD_W, LOAD_H);
	blend_state(p);
	packet2_add_u64(p, GIF_TAG(2, 1, 1,
		GS_PRIM(GSX_PRIM_SPRITE, 0, 1, 0, 1, 0, 1, 0, 0), GIFX_FLG_PACKED, 3));
	packet2_add_u64(p, 0x531);
	/* retail's diffuse is 254/255, 254/255, 1 */
	add_vertex(p, 127, 127, 128, alpha, u0, 0.f, 0.f, 0.f);
	add_vertex(p, 127, 127, 128, alpha, u1, (float)LOAD_H, (float)VIDEO_WIDTH, (float)VIDEO_HEIGHT);
}

static float mask_glow(float row_position)
{
	/* the mask's vertical profile: 16 rows over the screen height, sin(pi y / 15) ^ 0.75 sampled at row centres */
	float f = (row_position * 16.f - 0.5f) / 15.f;
	if (f < 0.f) f = 0.f;
	if (f > 1.f) f = 1.f;
	return powf(sinf(3.14159265f * f), 0.75f);
}

/* The loading picture through the sweeping mask. `mask_x` is the lobe's left edge in frame pixels. */
static void lobe(packet2_t *p, float mask_x, float pulse)
{
	const float lobe_w = 128.f * (float)VIDEO_WIDTH / 640.f;
	float glow[MASK_ROWS + 1];
	unsigned row, col;
	if (pulse <= 0.002f || mask_x + lobe_w <= 0.f || mask_x >= (float)VIDEO_WIDTH) return;
	for (row = 0; row <= MASK_ROWS; ++row) glow[row] = mask_glow((float)row / (float)MASK_ROWS);
	texture_state(p, (uint32_t)(s_video->tex_base + LOAD_PAGE * 2048u), GS_PSMCT16S, LOAD_W, LOAD_H);
	blend_state(p);
	for (row = 0; row < MASK_ROWS; ++row) {
		const float y0 = (float)row * (float)VIDEO_HEIGHT / (float)MASK_ROWS;
		const float y1 = (float)(row + 1) * (float)VIDEO_HEIGHT / (float)MASK_ROWS;
		packet2_add_u64(p, GIF_TAG(2u * (MASK_COLS + 1u), row + 1u == MASK_ROWS, 1,
			GS_PRIM(4 /* triangle strip */, 1, 1, 0, 1, 0, 1, 0, 0), GIFX_FLG_PACKED, 3));
		packet2_add_u64(p, 0x531);
		for (col = 0; col <= MASK_COLS; ++col) {
			const float x = mask_x + lobe_w * (float)col / (float)MASK_COLS;
			const float across = sinf(3.14159265f * (float)col / (float)MASK_COLS);
			float level0 = (5.f / 255.f + across * glow[row] * (250.f / 255.f)) * pulse;
			float level1 = (5.f / 255.f + across * glow[row + 1u] * (250.f / 255.f)) * pulse;
			unsigned c0 = (unsigned)(level0 * 128.f + 0.5f), c1 = (unsigned)(level1 * 128.f + 0.5f);
			if (c0 > 128u) c0 = 128u;
			if (c1 > 128u) c1 = 128u;
			add_vertex(p, c0, c0, c0, 128, x, y0, x, y0);
			add_vertex(p, c1, c1, c1, 128, x, y1, x, y1);
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
		(LOAD_PAGE + LOAD_PAGES) * 2048u > VIDEO_VRAM_WORDS - video->tex_base) return;
	s_video = video; s_dma = (uint8_t *)dma_storage; s_dma_bytes = dma_bytes;
	s_ready = 1;
}

static int upload_assets(void)
{
	chain_t chain;
	uint16_t *background;
	if (!s_video || !s_dma || !s_ready) return 0;
	background = load_background();
	if (!background) return 0;
	SyncDCache(background, (uint8_t *)background + LOAD_BYTES);
	chain_init(&chain, s_upload_chain, LOAD_CHAIN_QW);
	if (gs_upload(&chain, background, LOAD_BYTES,
		(s_video->tex_base + LOAD_PAGE * 2048u) / 64u, LOAD_W / 64u,
		GS_PSMCT16S, LOAD_W, LOAD_H)) { free(background); return 0; }
	chain_end(&chain, 0);
	SyncDCache(s_upload_chain, (uint8_t *)s_upload_chain + chain_qwords(&chain) * 16u);
	hcu_boot_diag_note("load upld", LOAD_BYTES, 0, 0);
	dma_channel_send_chain(DMA_CHANNEL_GIF, s_upload_chain, 0, 0, 0);
	hcu_boot_diag_note("load upwait", 0, 0, 0);
	dma_wait_fast(); free(background);
	return 1;
}

static void present(float progress)
{
	unsigned char *storage = s_dma;
	float pulse, fade;
	if (!s_ready || !s_video || !storage || s_rendering || s_dma_bytes < FRAME_PACKET_QW * 16u) {
		static unsigned s_skip_reports;
		if (s_skip_reports++ < 3u)
			printf("HALO_PS2_LOCAL loading-screen-skip ready=%d video=%d storage=%d rendering=%d dma=%u\n",
				s_ready, s_video != NULL, storage != NULL, s_rendering, (unsigned)s_dma_bytes);
		return;
	}
	hcu_boot_diag_note("load calc", s_frame, (unsigned)s_bytes_read, 0);
	s_rendering = 1;
	if (progress > 1.f) progress = 1.f;
	if (progress < 0.f) progress = 0.f;
	/* Retail eases toward the reported progress and wobbles it a little, so the sweep never moves in a straight line. */
	s_wobble += 0.01f;
	progress = ((s_finishing ? 0.f : sinf(s_wobble) * 0.05f) + progress - s_last_progress) * 0.2f + s_last_progress;
	if (progress > 1.f) progress = 1.f;
	if (progress < 0.f) progress = 0.f;
	s_last_progress = progress;
	pulse = powf(fmaxf(0.f, sinf(progress * 3.14159f)), 0.9f);
	fade = progress < 0.9f ? 0.9f : 0.9f - (progress - 0.9f) * 9.f;
	if (fade < 0.f) fade = 0.f;
	packet2_reset(&s_packet, 0);
	s_packet.max_qwords_count = FRAME_PACKET_QW; s_packet.type = P2_TYPE_NORMAL;
	s_packet.mode = P2_MODE_NORMAL; s_packet.base = s_packet.next = (qword_t *)storage;
	video_add_setup_env(s_video, &s_packet);
	video_add_clear(s_video, &s_packet, 0, 0, 0);
	/* The first two frames of a load have no earlier loading frame to carry on from (the other buffer holds the menu
	 * or nothing): they start from black. */
	if (s_frame - s_begin_frame >= 2u && fade > 0.f)
		trail(&s_packet, (unsigned)(fade * 128.f + 0.5f));
	lobe(&s_packet, (progress * 768.f - 128.f) * (float)VIDEO_WIDTH / 640.f, pulse);
	packet2_update(&s_packet, draw_finish(s_packet.next));
	SyncDCache(storage, storage + (s_packet.next - s_packet.base) * 16u);
	hcu_boot_diag_note("load send", s_frame, (unsigned)(s_packet.next - s_packet.base), 0);
	dma_channel_send_packet2(&s_packet, DMA_CHANNEL_GIF, 1);
	hcu_boot_diag_note("load DMA", s_frame, 0, 0);
	dma_wait_fast();
	hcu_boot_diag_note("load FINISH", s_frame, 0, 0);
	draw_wait_finish();
	hcu_boot_diag_note("load vsync", s_frame, 0, 0);
	video_present(s_video);
	hcu_boot_diag_note("load shown", s_frame, 0, 0);
	{
		uint32_t now = timer_cycles();
		uint32_t gap = (uint32_t)timer_ms(s_last_present_cycles, now);
		if (s_last_present_cycles && gap > s_max_gap_ms) s_max_gap_ms = gap;
		s_last_present_cycles = now;
	}
	++s_frame; s_rendering = 0;
}

/* One black frame. The GS keeps whatever the last program left in its buffers, so before the first loading frame is ready
 * (its background is read from disc) the display would show the menu again for about a second. Two calls blacken both
 * buffers. */
static void present_black(void)
{
	unsigned char *storage = s_dma;
	if (!s_ready || !s_video || !storage || s_rendering || s_dma_bytes < FRAME_PACKET_QW * 16u) return;
	s_rendering = 1;
	packet2_reset(&s_packet, 0);
	s_packet.max_qwords_count = FRAME_PACKET_QW; s_packet.type = P2_TYPE_NORMAL;
	s_packet.mode = P2_MODE_NORMAL; s_packet.base = s_packet.next = (qword_t *)storage;
	video_add_setup_env(s_video, &s_packet);
	video_add_clear(s_video, &s_packet, 0, 0, 0);
	packet2_update(&s_packet, draw_finish(s_packet.next));
	SyncDCache(storage, storage + (s_packet.next - s_packet.base) * 16u);
	dma_channel_send_packet2(&s_packet, DMA_CHANNEL_GIF, 1);
	dma_wait_fast();
	draw_wait_finish();
	video_present(s_video);
	s_rendering = 0;
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
	present_black();
	present_black();
	if (!upload_assets()) {
		printf("HALO_PS2_FAIL loading-screen-assets\n");
		return;
	}
	s_bytes_read = 0;
	s_progress = 0.f; s_last_progress = 0.f; s_wobble = 0.f; s_finishing = 0;
	s_begin_frame = s_frame;
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
		s_finishing = 1;
		/* Match CE's easing tail: continue presenting until the sweep passes the
		 * right edge and its trail fades to black. */
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
	const uint64_t byte_budget = (s_hold ? 13u : 32u) * 1024u * 1024u;   /* a Blood Gulch load now reads about 13 MB: the package payload is not read or hashed at run time */
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
