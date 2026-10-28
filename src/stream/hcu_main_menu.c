#include "stream/hcu_main_menu.h"

#include <string.h>

static const char *const s_title_items[HCU_MAIN_MENU_ITEM_COUNT] = {
	"MULTIPLAYER", "FIREFIGHT", "CONTROLS", "SETTINGS"
};

void hcu_main_menu_state_init(hcu_main_menu_state *state)
{
	if (!state) return;
	memset(state, 0, sizeof(*state));
	state->vibration = 1;
}

const char *hcu_main_menu_item_label(unsigned item)
{
	return item < HCU_MAIN_MENU_ITEM_COUNT ? s_title_items[item] : "";
}

enum hcu_main_menu_action hcu_main_menu_step(hcu_main_menu_state *state,
	int up, int down, int left, int right, int confirm, int back)
{
	if (!state) return HCU_MAIN_MENU_ACTION_NONE;
	if (state->page == HCU_MAIN_MENU_PAGE_TITLE) {
		if (up)
			state->item = (uint8_t)((state->item + HCU_MAIN_MENU_ITEM_COUNT - 1) %
				HCU_MAIN_MENU_ITEM_COUNT);
		else if (down)
			state->item = (uint8_t)((state->item + 1) % HCU_MAIN_MENU_ITEM_COUNT);
		if (!confirm) return HCU_MAIN_MENU_ACTION_NONE;
		if (state->item == HCU_MAIN_MENU_MULTIPLAYER)
			return HCU_MAIN_MENU_ACTION_MULTIPLAYER;
		if (state->item == HCU_MAIN_MENU_FIREFIGHT)
			return HCU_MAIN_MENU_ACTION_FIREFIGHT;
		state->page = state->item == HCU_MAIN_MENU_CONTROLS ?
			HCU_MAIN_MENU_PAGE_CONTROLS : HCU_MAIN_MENU_PAGE_SETTINGS;
		return HCU_MAIN_MENU_ACTION_NONE;
	}
	if (back) {
		state->page = HCU_MAIN_MENU_PAGE_TITLE;
		return HCU_MAIN_MENU_ACTION_NONE;
	}
	if (state->page == HCU_MAIN_MENU_PAGE_SETTINGS) {
		if (up)
			state->settings_row = (uint8_t)((state->settings_row + 1) % 2);
		else if (down)
			state->settings_row = (uint8_t)((state->settings_row + 1) % 2);
		if (confirm || left || right) {
			if (state->settings_row == 0) state->widescreen ^= 1;
			else state->vibration ^= 1;
		}
	}
	return HCU_MAIN_MENU_ACTION_NONE;
}

static uint32_t menu_hash(unsigned x, unsigned y)
{
	uint32_t n = x * 0x45d9f3bu + y * 0x119de1f3u + 0x68bc21ebu;
	n ^= n >> 16;
	n *= 0x7feb352du;
	n ^= n >> 15;
	return n;
}

static unsigned menu_clamp(unsigned value, unsigned maximum)
{
	return value > maximum ? maximum : value;
}

int hcu_main_menu_build_ring_texture(uint16_t *pixels, unsigned width,
	unsigned height)
{
	unsigned x, y;
	if (!pixels || width != 128u || height != 128u) return -1;
	for (y = 0; y < height; ++y) {
		for (x = 0; x < width; ++x) {
			uint32_t noise = menu_hash(x >> 1, y >> 1);
			unsigned ridge = ((x * 5u + y * 3u + (noise >> 25)) & 31u);
			unsigned cloud = ((x * 2u + y + (noise >> 27)) & 15u) < 3u;
			unsigned water = ((x + y * 7u + (noise >> 24)) & 31u) < 9u;
			unsigned r = water ? 5u + (noise & 3u) : 7u + ridge / 6u;
			unsigned g = water ? 12u + ((noise >> 3) & 5u) : 15u + ridge / 3u;
			unsigned b = water ? 20u + ((noise >> 7) & 7u) : 8u + ridge / 8u;
			if (cloud) { r += 10u; g += 9u; b += 8u; }
			pixels[y * width + x] = (uint16_t)(menu_clamp(r, 31u) |
				(menu_clamp(g, 31u) << 5) | (menu_clamp(b, 31u) << 10) | 0x8000u);
		}
	}
	return 0;
}

#ifdef _EE

#include <dma.h>
#include <draw.h>
#include <gs_psm.h>
#include <kernel.h>
#include <math.h>
#include <packet2.h>
#include <stdio.h>
#include <tamtypes.h>

#include "platform/pad.h"
#include "render/chain.h"
#include "render/gs.h"
#include "render/text.h"
#include "render/upload.h"

#define MENU_PACKET_QW 4096u
#define MENU_RING_W 128u
#define MENU_RING_H 128u
#define MENU_RING_BYTES (MENU_RING_W * MENU_RING_H * 2u)
#define MENU_FONT_BYTES (TEXT_ATLAS_W * TEXT_ATLAS_H)
#define MENU_CLUT_BYTES (256u * sizeof(uint32_t))
#define MENU_PAGE_WORDS 2048u
#define MENU_RING_PAGE 0u
#define MENU_FONT_PAGE 4u
#define MENU_CLUT_PAGE 5u
#define MENU_PAD_UP 0x0010u
#define MENU_PAD_DOWN 0x0040u
#define MENU_DEAD_LOW 72u
#define MENU_DEAD_HIGH 184u

typedef struct menu_input {
	unsigned previous[4];
	unsigned repeat_direction;
	unsigned repeat_frames;
} menu_input;

static uint64_t menu_rgbaq(unsigned r, unsigned g)
{
	return (uint64_t)r | (uint64_t)g << 32;
}

static uint64_t menu_baq(unsigned b, unsigned a)
{
	return (uint64_t)b | (uint64_t)a << 32;
}

static uint64_t menu_xy(int x, int y)
{
	return (uint64_t)((2048 - VIDEO_WIDTH / 2 + x) * 16) |
		(uint64_t)((2048 - VIDEO_HEIGHT / 2 + y) * 16) << 32;
}

static void menu_vertex(packet2_t *packet, int x, int y, int u, int v,
	unsigned r, unsigned g, unsigned b, unsigned a)
{
	packet2_add_u64(packet, menu_rgbaq(r, g));
	packet2_add_u64(packet, menu_baq(b, a));
	packet2_add_u64(packet, (uint64_t)(u * 16) | (uint64_t)(v * 16) << 32);
	packet2_add_u64(packet, 0);
	packet2_add_u64(packet, menu_xy(x, y));
	packet2_add_u64(packet, 0x00ffffffu);
}

static void menu_flat_vertex(packet2_t *packet, int x, int y,
	unsigned r, unsigned g, unsigned b, unsigned a)
{
	packet2_add_u64(packet, menu_rgbaq(r, g));
	packet2_add_u64(packet, menu_baq(b, a));
	packet2_add_u64(packet, menu_xy(x, y));
	packet2_add_u64(packet, 0x00ffffffu);
}

static void menu_flat_rect(packet2_t *packet, int x0, int y0, int x1, int y1,
	unsigned r, unsigned g, unsigned b, unsigned a)
{
	packet2_add_u64(packet, GIF_TAG(2, 0, 1,
		GS_PRIM(GSX_PRIM_SPRITE, 0, 0, 0, a < 0x80u, 0, 1, 0, 0),
		GIFX_FLG_PACKED, 2));
	packet2_add_u64(packet, 0x51);
	menu_flat_vertex(packet, x0, y0, r, g, b, a);
	menu_flat_vertex(packet, x1, y1, r, g, b, a);
}

static void menu_frame(packet2_t *packet, int x0, int y0, int x1, int y1)
{
	menu_flat_rect(packet, x0, y0, x1, y0 + 2, 112, 190, 255, 0x78);
	menu_flat_rect(packet, x0, y1 - 2, x1, y1, 112, 190, 255, 0x78);
	menu_flat_rect(packet, x0, y0 + 2, x0 + 2, y1 - 2, 112, 190, 255, 0x78);
	menu_flat_rect(packet, x1 - 2, y0 + 2, x1, y1 - 2, 112, 190, 255, 0x78);
}

static void menu_flat_state(packet2_t *packet)
{
	packet2_add_u64(packet, GIF_TAG(2, 0, 0, 0, GIFX_FLG_PACKED, 1));
	packet2_add_u64(packet, GIF_REGS_AD);
	packet2_add_u64(packet, GS_ALPHA(0, 1, 0, 1, 0));
	packet2_add_u64(packet, GS_A_ALPHA_1);
	packet2_add_u64(packet, GS_TEST(0, 1, 0, 0, 0, 0, 1, 1));
	packet2_add_u64(packet, GS_A_TEST_1);
}

static void menu_texture_state(packet2_t *packet, const video_t *video,
	unsigned page, unsigned psm, unsigned tw, unsigned th, unsigned tbw,
	unsigned clut_page)
{
	uint32_t base = video->tex_base + page * MENU_PAGE_WORDS;
	uint32_t clut = video->tex_base + clut_page * MENU_PAGE_WORDS;
	packet2_add_u64(packet, GIF_TAG(6, 0, 0, 0, GIFX_FLG_PACKED, 1));
	packet2_add_u64(packet, GIF_REGS_AD);
	packet2_add_u64(packet, GS_TEX0(base / 64u, tbw, psm, tw, th, 1, 0,
		clut / 64u, GS_PSMCT32, 0, 0, 1));
	packet2_add_u64(packet, GS_A_TEX0_1);
	packet2_add_u64(packet, GS_TEX1(1, 0, 1, 1, 0, 0, 0));
	packet2_add_u64(packet, GS_A_TEX1_1);
	packet2_add_u64(packet, GS_CLAMP(0, 0, 0, 0, 0, 0));
	packet2_add_u64(packet, GS_A_CLAMP_1);
	packet2_add_u64(packet, GS_ALPHA(0, 1, 0, 1, 0));
	packet2_add_u64(packet, GS_A_ALPHA_1);
	packet2_add_u64(packet, GS_TEST(0, 1, 0, 0, 0, 0, 1, 1));
	packet2_add_u64(packet, GS_A_TEST_1);
	packet2_add_u64(packet, 0);
	packet2_add_u64(packet, GS_A_TEXFLUSH);
}

static void menu_ring(packet2_t *packet, const video_t *video, unsigned frame)
{
	const int segments = 64;
	float phase = (float)frame * 0.0035f;
	float roll = -0.22f + 0.025f * sinf(phase * 0.37f);
	float cr = cosf(roll), sr = sinf(roll);
	int center_x = 332 + (int)(10.0f * sinf(phase * 0.51f));
	int center_y = 178 + (int)(7.0f * cosf(phase * 0.43f));
	int i;
	menu_texture_state(packet, video, MENU_RING_PAGE, GS_PSMCT16S,
		7, 7, MENU_RING_W / 64u, 0);
	packet2_add_u64(packet, GIF_TAG(segments * 6, 0, 1,
		GS_PRIM(GSX_PRIM_TRIANGLE, 1, 1, 0, 0, 0, 1, 0, 0),
		GIFX_FLG_PACKED, 3));
	packet2_add_u64(packet, 0x531);
	for (i = 0; i < segments; ++i) {
		int j;
		int index[6] = {i, i + 1, i, i, i + 1, i + 1};
		int edge[6] = {0, 0, 1, 1, 0, 1};
		for (j = 0; j < 6; ++j) {
			float a = (float)index[j] * 6.28318530718f / (float)segments + phase * 0.08f;
			float depth = 0.5f + 0.5f * sinf(a);
			float rx = edge[j] ? 222.0f : 260.0f;
			float ry = edge[j] ? 157.0f : 190.0f;
			float px = cosf(a) * rx;
			float py = sinf(a) * ry;
			int x = center_x + (int)(px * cr - py * sr);
			int y = center_y + (int)(px * sr + py * cr);
			int tile = index[j] & 15;
			int u = tile * 8;
			unsigned shade = 82u + (unsigned)(depth * 90.0f);
			if (tile == 0 && index[j] != 0) u = 128;
			menu_vertex(packet, x, y, u, edge[j] ? 122 : 6,
				shade, shade, shade, 0x80);
		}
	}
}

static unsigned menu_text_width(const char *text, unsigned scale)
{
	return (unsigned)strlen(text) * TEXT_CELL_W * scale;
}

static void menu_text(packet2_t *packet, const video_t *video, int x, int y,
	unsigned scale, unsigned r, unsigned g, unsigned b, unsigned a,
	const char *text)
{
	unsigned count = 0, i;
	const char *p;
	menu_texture_state(packet, video, MENU_FONT_PAGE, GS_PSMT8, 7, 6,
		TEXT_ATLAS_W / 64u, MENU_CLUT_PAGE);
	for (p = text; *p; ++p) if (*p != ' ') ++count;
	if (!count) return;
	packet2_add_u64(packet, GIF_TAG(count * 2u, 0, 1,
		GS_PRIM(GSX_PRIM_SPRITE, 0, 1, 0, 1, 0, 1, 0, 0),
		GIFX_FLG_PACKED, 3));
	packet2_add_u64(packet, 0x531);
	for (i = 0; text[i]; ++i) {
		unsigned ch = (unsigned char)text[i];
		unsigned cell, u, v;
		if (ch >= 'a' && ch <= 'z') ch -= 32;
		if (ch == ' ') continue;
		if (ch < 32u || ch >= 128u) ch = '?';
		cell = ch - 32u;
		u = (cell % 16u) * 8u;
		v = (cell / 16u) * 8u;
		menu_vertex(packet, x + (int)(i * TEXT_CELL_W * scale), y,
			(int)u, (int)v, r, g, b, a);
		menu_vertex(packet, x + (int)((i * TEXT_CELL_W + TEXT_CELL_W) * scale),
			y + (int)(TEXT_CELL_H * scale), (int)(u + TEXT_CELL_W),
			(int)(v + TEXT_CELL_H), r, g, b, a);
	}
}

static void menu_text_center(packet2_t *packet, const video_t *video, int y,
	unsigned scale, unsigned r, unsigned g, unsigned b, unsigned a,
	const char *text)
{
	int x = (VIDEO_WIDTH - (int)menu_text_width(text, scale)) / 2;
	menu_text(packet, video, x, y, scale, r, g, b, a, text);
}

static void menu_stars(packet2_t *packet, unsigned frame)
{
	unsigned i;
	for (i = 0; i < 48u; ++i) {
		uint32_t n = menu_hash(i, 91u);
		int x = (int)((n + frame / (18u + i % 7u)) % VIDEO_WIDTH);
		int y = (int)(((n >> 16) + i * 37u) % 272u);
		unsigned c = 72u + (n & 63u);
		menu_flat_rect(packet, x, y, x + 1 + (int)(i % 7u == 0u), y + 1,
			c, c + 12u, c + 28u, 0x70);
	}
}

static void menu_title(packet2_t *packet, const video_t *video,
	const hcu_main_menu_state *state, unsigned frame)
{
	unsigned i;
	unsigned pulse = 202u + (unsigned)(53.0f * (0.5f + 0.5f * sinf((float)frame * 0.085f)));
	menu_text_center(packet, video, 56, 9, 20, 46, 82, 0x70, "HALO");
	menu_text_center(packet, video, 52, 9, 218, 232, 244, 0x80, "HALO");
	menu_text_center(packet, video, 120, 6, 24, 60, 102, 0x70, "PS2");
	menu_text_center(packet, video, 117, 6, 206, 225, 242, 0x80, "PS2");
	for (i = 0; i < HCU_MAIN_MENU_ITEM_COUNT; ++i) {
		int y = 270 + (int)i * 34;
		if (i == state->item) {
			menu_flat_rect(packet, 144, y - 7, 368, y + 25, 27, 67, 116, 0x58);
			menu_frame(packet, 144, y - 7, 368, y + 25);
			menu_text_center(packet, video, y, 3, pulse, pulse, pulse, 0x80,
				s_title_items[i]);
		} else {
			menu_text_center(packet, video, y, 3, 126, 185, 236, 0x78,
				s_title_items[i]);
		}
	}
	menu_text_center(packet, video, 420, 2, 68, 105, 157, 0x68,
		"SPLIT SCREEN  -  UP TO 4 PLAYERS");
}

static void menu_subpage(packet2_t *packet, const video_t *video,
	const hcu_main_menu_state *state)
{
	const char *title = state->page == HCU_MAIN_MENU_PAGE_CONTROLS ?
		"CONTROLS" : "SETTINGS";
	menu_flat_rect(packet, 24, 34, 488, 414, 0, 8, 24, 0x58);
	menu_frame(packet, 24, 34, 488, 414);
	menu_text(packet, video, 48, 56, 4, 224, 236, 248, 0x80, title);
	menu_flat_rect(packet, 48, 94, 464, 96, 112, 190, 255, 0x68);
	if (state->page == HCU_MAIN_MENU_PAGE_CONTROLS) {
		menu_text(packet, video, 62, 126, 3, 132, 191, 238, 0x78,
			"MOVE       LEFT STICK");
		menu_text(packet, video, 62, 168, 3, 132, 191, 238, 0x78,
			"LOOK       RIGHT STICK");
		menu_text(packet, video, 62, 210, 3, 132, 191, 238, 0x78,
			"SELECT     CROSS / START");
		menu_text(packet, video, 62, 252, 3, 132, 191, 238, 0x78,
			"BACK       CIRCLE");
	} else {
		int y0 = 142 + (int)state->settings_row * 62;
		menu_flat_rect(packet, 48, y0 - 12, 464, y0 + 25, 27, 67, 116, 0x58);
		menu_frame(packet, 48, y0 - 12, 464, y0 + 25);
		menu_text(packet, video, 66, 142, 3, 224, 236, 248, 0x80,
			state->widescreen ? "WIDESCREEN       ON" : "WIDESCREEN       OFF");
		menu_text(packet, video, 66, 204, 3, 224, 236, 248, 0x80,
			state->vibration ? "VIBRATION        ON" : "VIBRATION        OFF");
	}
	menu_text(packet, video, 330, 382, 2, 80, 126, 178, 0x70, "CIRCLE  BACK");
}

static int menu_upload_assets(video_t *video, void *dma_storage, size_t dma_bytes,
	uint16_t *ring, uint8_t *font, uint32_t *clut)
{
	chain_t chain;
	if (dma_bytes < 64u * 16u) return -1;
	text_build_atlas(font);
	text_build_clut(clut);
	if (hcu_main_menu_build_ring_texture(ring, MENU_RING_W, MENU_RING_H)) return -1;
	SyncDCache(ring, (uint8_t *)ring + MENU_RING_BYTES);
	SyncDCache(font, font + MENU_FONT_BYTES);
	SyncDCache(clut, (uint8_t *)clut + MENU_CLUT_BYTES);
	chain_init(&chain, dma_storage, 64u);
	if (gs_upload(&chain, ring, MENU_RING_BYTES,
		(video->tex_base + MENU_RING_PAGE * MENU_PAGE_WORDS) / 64u,
		MENU_RING_W / 64u, GS_PSMCT16S, MENU_RING_W, MENU_RING_H) ||
		gs_upload(&chain, font, MENU_FONT_BYTES,
		(video->tex_base + MENU_FONT_PAGE * MENU_PAGE_WORDS) / 64u,
		TEXT_ATLAS_W / 64u, GS_PSMT8, TEXT_ATLAS_W, TEXT_ATLAS_H) ||
		gs_upload(&chain, clut, MENU_CLUT_BYTES,
		(video->tex_base + MENU_CLUT_PAGE * MENU_PAGE_WORDS) / 64u,
		1u, GS_PSMCT32, 16u, 16u)) return -1;
	chain_end(&chain, 0);
	SyncDCache(dma_storage, (uint8_t *)dma_storage + chain_qwords(&chain) * 16u);
	dma_channel_send_chain(DMA_CHANNEL_GIF, dma_storage, 0, 0, 0);
	dma_wait_fast();
	return chain.overflow ? -1 : 0;
}

static void menu_read_input(menu_input *input, int *up, int *down, int *left,
	int *right, int *confirm, int *back)
{
	pad_sample pads[4];
	unsigned p, direction = 0;
	*up = *down = *left = *right = *confirm = *back = 0;
	(void)pad_poll_players(pads);
	for (p = 0; p < 4u; ++p) {
		unsigned edges = pads[p].buttons & ~input->previous[p];
		input->previous[p] = pads[p].buttons;
		*up |= (edges & MENU_PAD_UP) != 0;
		*down |= (edges & MENU_PAD_DOWN) != 0;
		*left |= (edges & 0x0080u) != 0;
		*right |= (edges & 0x0020u) != 0;
		*confirm |= (edges & (PAD_BTN_CROSS | PAD_BTN_START)) != 0;
		*back |= (edges & PAD_BTN_CIRCLE) != 0;
		if (!direction && pads[p].connected) {
			if (pads[p].ly < MENU_DEAD_LOW) direction = 1;
			else if (pads[p].ly > MENU_DEAD_HIGH) direction = 2;
			else if (pads[p].lx < MENU_DEAD_LOW) direction = 3;
			else if (pads[p].lx > MENU_DEAD_HIGH) direction = 4;
		}
	}
	if (!direction) {
		input->repeat_direction = 0;
		input->repeat_frames = 0;
	} else if (direction != input->repeat_direction) {
		input->repeat_direction = direction;
		input->repeat_frames = 18;
		*up |= direction == 1; *down |= direction == 2;
		*left |= direction == 3; *right |= direction == 4;
	} else if (input->repeat_frames && --input->repeat_frames == 0) {
		input->repeat_frames = 6;
		*up |= direction == 1; *down |= direction == 2;
		*left |= direction == 3; *right |= direction == 4;
	}
}

enum hcu_main_menu_action hcu_main_menu_run(video_t *video,
	void *dma_storage, size_t dma_bytes, arena_t *scratch)
{
	hcu_main_menu_state state;
	menu_input input;
	packet2_t packet;
	enum hcu_main_menu_action action = HCU_MAIN_MENU_ACTION_NONE;
	size_t mark;
	uint16_t *ring;
	uint8_t *font;
	uint32_t *clut;
	unsigned frame = 0;
	if (!video || !dma_storage || dma_bytes < MENU_PACKET_QW * 16u || !scratch)
		return HCU_MAIN_MENU_ACTION_MULTIPLAYER;
	mark = arena_mark(scratch);
	ring = (uint16_t *)arena_alloc(scratch, MENU_RING_BYTES, 64u);
	font = (uint8_t *)arena_alloc(scratch, MENU_FONT_BYTES, 64u);
	clut = (uint32_t *)arena_alloc(scratch, MENU_CLUT_BYTES, 64u);
	if (!ring || !font || !clut ||
		menu_upload_assets(video, dma_storage, dma_bytes, ring, font, clut)) {
		arena_release(scratch, mark);
		printf("HALO_PS2_FAIL main-menu asset upload\n");
		return HCU_MAIN_MENU_ACTION_MULTIPLAYER;
	}
	hcu_main_menu_state_init(&state);
	memset(&input, 0, sizeof(input));
	memset(&packet, 0, sizeof(packet));
	packet.max_qwords_count = MENU_PACKET_QW;
	packet.type = P2_TYPE_NORMAL;
	packet.mode = P2_MODE_NORMAL;
	packet.base = packet.next = (qword_t *)dma_storage;
	printf("HALO_PS2_LOCAL main-menu-ready items=%u texture=%ux%u\n",
		(unsigned)HCU_MAIN_MENU_ITEM_COUNT, MENU_RING_W, MENU_RING_H);
	while (action == HCU_MAIN_MENU_ACTION_NONE) {
		int up, down, left, right, confirm, back;
		menu_read_input(&input, &up, &down, &left, &right, &confirm, &back);
		action = hcu_main_menu_step(&state, up, down, left, right, confirm, back);
		packet2_reset(&packet, 0);
		video_add_setup_env(video, &packet);
		{
			static const u8 top[3] = {2, 5, 14};
			static const u8 horizon[3] = {5, 10, 23};
			video_add_sky(video, &packet, top, horizon, 310);
		}
		menu_flat_state(&packet);
		menu_stars(&packet, frame);
		menu_ring(&packet, video, frame);
		if (state.page == HCU_MAIN_MENU_PAGE_TITLE)
			menu_title(&packet, video, &state, frame);
		else
			menu_subpage(&packet, video, &state);
		packet2_update(&packet, draw_finish(packet.next));
		if ((size_t)(packet.next - packet.base) > MENU_PACKET_QW) {
			printf("HALO_PS2_FAIL main-menu packet overflow qwords=%u\n",
				(unsigned)(packet.next - packet.base));
			action = HCU_MAIN_MENU_ACTION_MULTIPLAYER;
		}
		dma_channel_send_packet2(&packet, DMA_CHANNEL_GIF, 1);
		dma_wait_fast();
		draw_wait_finish();
		video_present(video);
		++frame;
	}
	arena_release(scratch, mark);
	printf("HALO_PS2_LOCAL main-menu-selected item=%s frames=%u\n",
		action == HCU_MAIN_MENU_ACTION_FIREFIGHT ? "firefight" : "multiplayer", frame);
	return action;
}

#endif
