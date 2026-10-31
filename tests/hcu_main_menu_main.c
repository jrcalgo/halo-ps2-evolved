#include <stdint.h>
#include <stdio.h>
#include <string.h>

#include "stream/hcu_main_menu.h"

static uint32_t texture_hash(const uint16_t *pixels, unsigned count)
{
	uint32_t hash = 2166136261u;
	unsigned i;
	for (i = 0; i < count; ++i) {
		hash ^= pixels[i] & 0xffu; hash *= 16777619u;
		hash ^= pixels[i] >> 8; hash *= 16777619u;
	}
	return hash;
}

int main(void)
{
	hcu_main_menu_state state;
	uint16_t a[128 * 128], b[128 * 128];
	unsigned i, changed = 0;

	hcu_main_menu_state_init(&state);
	if (state.item != HCU_MAIN_MENU_MULTIPLAYER ||
		state.page != HCU_MAIN_MENU_PAGE_TITLE || !state.particles ||
		!state.profiles[0].vibration || state.session.map != 9) return 1;
	if (strcmp(hcu_main_menu_item_label(0), "MULTIPLAYER") ||
		strcmp(hcu_main_menu_item_label(1), "SETTINGS") ||
		*hcu_main_menu_item_label(2) ||
		strcmp(hcu_main_menu_map_label(9), "BLOOD GULCH") ||
		strcmp(hcu_main_menu_game_type_label(HCU_GAME_SLAYER), "SLAYER")) return 2;
	(void)hcu_main_menu_step(&state, 1, 0, 0, 0, 0, 0);
	if (state.item != HCU_MAIN_MENU_SETTINGS) return 3;
	(void)hcu_main_menu_step(&state, 0, 1, 0, 0, 0, 0);
	if (state.item != HCU_MAIN_MENU_MULTIPLAYER) return 4;
	if (hcu_main_menu_step(&state, 0, 0, 0, 0, 1, 0) != HCU_MAIN_MENU_ACTION_NONE ||
		state.page != HCU_MAIN_MENU_PAGE_CONNECT) return 5;
	(void)hcu_main_menu_step(&state, 0, 0, 0, 0, 1, 0);
	if (state.player_count != 1 || state.page != HCU_MAIN_MENU_PAGE_CONNECT) return 6;
	(void)hcu_main_menu_step(&state, 0, 0, 0, 0, 1, 0);
	if (state.page != HCU_MAIN_MENU_PAGE_LOBBY) return 7;
	/* GAME OPTIONS, change score, return, then save CUSTOM 1. */
	(void)hcu_main_menu_step(&state, 0, 1, 0, 0, 0, 0);
	(void)hcu_main_menu_step(&state, 0, 1, 0, 0, 0, 0);
	(void)hcu_main_menu_step(&state, 0, 0, 0, 0, 1, 0);
	if (state.page != HCU_MAIN_MENU_PAGE_GAME_OPTIONS) return 8;
	/* GAME TYPE RULES -> Slayer -> KILLS TO WIN. */
	(void)hcu_main_menu_step(&state, 0, 0, 0, 0, 1, 0);
	if (state.page != HCU_MAIN_MENU_PAGE_MODE_OPTIONS) return 9;
	state.row = 3;
	(void)hcu_main_menu_step(&state, 0, 0, 0, 1, 0, 0);
	if (state.session.variant.score_index != 3) return 10;
	state.row = 5;
	(void)hcu_main_menu_step(&state, 0, 0, 0, 1, 0, 0);
	if (state.session.variant.time_limit != 1 || state.session.variant.score_index != 3) return 40;
	(void)hcu_main_menu_step(&state, 0, 0, 0, 0, 0, 1);
	if (state.page != HCU_MAIN_MENU_PAGE_GAME_OPTIONS) return 11;
	(void)hcu_main_menu_step(&state, 0, 0, 0, 0, 0, 1);
	state.row = 3;
	(void)hcu_main_menu_step(&state, 0, 0, 0, 0, 1, 0);
	if (state.page != HCU_MAIN_MENU_PAGE_SAVE_VARIANT) return 12;
	(void)hcu_main_menu_step(&state, 0, 0, 0, 0, 1, 0);
	if (!state.saved_variants[0][0].valid || state.page != HCU_MAIN_MENU_PAGE_LOBBY ||
		state.session.variant_index != HCU_MAIN_MENU_GAME_TYPE_COUNT) return 13;
	/* The same slot belongs independently to whichever profile is Player 1. */
	state.port_profile[0] = 1;
	if (state.saved_variants[1][0].valid) return 14;
	hcu_main_menu_state_init(&state);
	state.item = HCU_MAIN_MENU_SETTINGS;
	(void)hcu_main_menu_step(&state, 0, 0, 0, 0, 1, 0);
	(void)hcu_main_menu_step(&state, 0, 0, 0, 0, 1, 0);
	if (hcu_main_menu_create_profile(&state) != 1 ||
		!(state.profile_present_mask & 1u)) return 26;
	if (state.page != HCU_MAIN_MENU_PAGE_PROFILE_EDIT) return 15;
	(void)hcu_main_menu_step(&state, 0, 0, 0, 0, 1, 0);
	if (state.page != HCU_MAIN_MENU_PAGE_PROFILE_NAME) return 16;
	(void)hcu_main_menu_step(&state, 1, 0, 0, 0, 0, 0);
	if (state.profiles[0].name[0] != 'T') return 17;
	(void)hcu_main_menu_step(&state, 0, 0, 0, 0, 1, 0);
	(void)hcu_main_menu_step(&state, 0, 1, 0, 0, 0, 0);
	(void)hcu_main_menu_step(&state, 0, 0, 0, 1, 0, 0);
	if (state.profiles[0].control_layout != 1) return 18;
	(void)hcu_main_menu_step(&state, 0, 0, 0, 0, 0, 1);
	(void)hcu_main_menu_step(&state, 0, 0, 0, 0, 0, 1);
	(void)hcu_main_menu_step(&state, 0, 0, 0, 0, 0, 1);
	state.item = HCU_MAIN_MENU_SETTINGS;
	(void)hcu_main_menu_step(&state, 0, 0, 0, 0, 1, 0);
	(void)hcu_main_menu_step(&state, 0, 1, 0, 0, 0, 0);
	(void)hcu_main_menu_step(&state, 0, 1, 0, 0, 0, 0);
	(void)hcu_main_menu_step(&state, 0, 0, 0, 0, 1, 0);
	(void)hcu_main_menu_step(&state, 0, 0, 0, 1, 0, 0);
	if (state.page != HCU_MAIN_MENU_PAGE_VIDEO_SETTINGS || state.resolution != 1) return 19;
	if (hcu_main_menu_build_ring_texture(a, 128, 128) ||
		hcu_main_menu_build_ring_texture(b, 128, 128) || memcmp(a, b, sizeof(a)) ||
		!texture_hash(a, 128 * 128)) return 20;
	for (i = 0; i < 128u * 128u; ++i) {
		if (!(a[i] & 0x8000u)) return 21;
		if (i && a[i] != a[0]) changed++;
	}
	if (changed < 12000u || hcu_main_menu_build_ring_texture(a, 64, 64) == 0)
		return 22;
	if (hcu_main_menu_build_ring_outer_texture(b, 128, 128) ||
		!texture_hash(b, 128 * 128) || !memcmp(a, b, sizeof(a)) ||
		hcu_main_menu_build_ring_outer_texture(b, 64, 64) == 0)
		return 23;
	changed = 0;
	for (i = 0; i < 128u * 128u; ++i) {
		if (!(b[i] & 0x8000u)) return 24;
		if (i && b[i] != b[0]) changed++;
	}
	if (changed < 12000u) return 25;
	hcu_main_menu_state_init(&state);
	state.item = HCU_MAIN_MENU_SETTINGS;
	(void)hcu_main_menu_step(&state, 0, 0, 0, 0, 1, 0);
	(void)hcu_main_menu_step(&state, 0, 0, 0, 0, 1, 0);
	for (i = 0; i < 3u; ++i)
		(void)hcu_main_menu_step(&state, 0, 1, 0, 0, 0, 0);
	if (state.row != 9u || hcu_main_menu_create_profile(&state) != 1 ||
		state.profile_index != 9u || !(state.profile_present_mask & (1u << 9))) return 27;
	(void)hcu_main_menu_step(&state, 0, 0, 0, 0, 0, 1);
	(void)hcu_main_menu_step(&state, 0, 0, 0, 0, 1, 0);
	if (state.page != HCU_MAIN_MENU_PAGE_PROFILE_EDIT || state.profile_index != 9u)
		return 28;
	hcu_main_menu_state_init(&state);
	state.page = HCU_MAIN_MENU_PAGE_SAVE_VARIANT;
	for (i = 0; i < 15u; ++i)
		(void)hcu_main_menu_step(&state, 0, 1, 0, 0, 0, 0);
	if (state.row != 15u) return 29;
	(void)hcu_main_menu_step(&state, 0, 0, 0, 0, 1, 0);
	if (!state.saved_variants[0][15].valid ||
		state.session.variant_index != HCU_MAIN_MENU_GAME_TYPE_COUNT + 15u)
		return 30;
	{
		extern const uint16_t hcu_main_menu_glyphs_rgb5a1[];
		unsigned opaque = 0, clear = 0, cell;
		static const char *const prompts[][2] = {
			{ "CROSS SELECT   CIRCLE BACK", "[cross] SELECT   [circle] BACK" },
			{ "LEFT/RIGHT PROFILE   CROSS LOAD/JOIN   TRIANGLE GUEST   START CONTINUE",
				"[dpad] PROFILE   [cross] LOAD/JOIN   [triangle] GUEST   [start] CONTINUE" },
			{ "CROSS JOIN/SELECT   CIRCLE LEAVE   START PLAY",
				"[cross] JOIN/SELECT   [circle] LEAVE   [start] PLAY" },
			{ "LEFT/RIGHT CHANGE   CROSS SELECT   CIRCLE BACK",
				"[dpad] CHANGE   [cross] SELECT   [circle] BACK" },
			{ "PLAYER 1 PROFILE   UP/DOWN SCROLL   CROSS SAVE   CIRCLE BACK",
				"PLAYER 1 PROFILE   [dpad] SCROLL   [cross] SAVE   [circle] BACK" },
			{ "CROSS LOAD   SQUARE CREATE   CIRCLE BACK",
				"[cross] LOAD   [square] CREATE   [circle] BACK" },
			{ "CROSS/LEFT/RIGHT CHANGE   CIRCLE BACK",
				"[cross]/[dpad] CHANGE   [circle] BACK" },
			{ "LEFT/RIGHT CURSOR   UP/DOWN CHARACTER   CROSS DONE",
				"[dpad] CURSOR   [dpad] CHARACTER   [cross] DONE" },
			{ "EACH PROFILE KEEPS ITS OWN CONTROLS", "EACH PROFILE KEEPS ITS OWN CONTROLS" },
			{ "CROSS PROFILE  TRIANGLE GUEST", "[cross] PROFILE  [triangle] GUEST" },
			{ "PRESS CROSS", "PRESS [cross]" },
			{ "PRESS SELECT", "PRESS [select]" },
			{ "SELECT BACK", "[select] BACK" },
			{ "L1 STRAFE   L2 ZOOM   R1 FIRE   R2 THROW   L3 CROUCH   R3 MELEE",
				"[l1] STRAFE   [l2] ZOOM   [r1] FIRE   [r2] THROW   [l3] CROUCH   [r3] MELEE" },
			{ "STARTING EQUIPMENT", "STARTING EQUIPMENT" },
			{ "UP/DOWN", "[dpad]" },
			{ "LEFT", "[dpad]" },
			{ "RIGHT", "[dpad]" }
		};
		char described[256];
		for (i = 0; i < sizeof(prompts) / sizeof(prompts[0]); ++i) {
			if (hcu_main_menu_describe_prompt(prompts[i][0], described, sizeof(described)) ||
				strcmp(described, prompts[i][1])) {
				printf("prompt-mismatch in='%s' out='%s' want='%s'\n",
					prompts[i][0], described, prompts[i][1]);
				return 32;
			}
		}
		if (hcu_main_menu_describe_prompt(NULL, described, sizeof(described)) == 0) return 33;
		for (i = 0; i < HCU_MAIN_MENU_GLYPH_ATLAS_W * HCU_MAIN_MENU_GLYPH_ATLAS_H; ++i) {
			if (hcu_main_menu_glyphs_rgb5a1[i] & 0x8000u) ++opaque;
			else ++clear;
		}
		if (opaque < 800u || clear < 800u) return 34;
		for (cell = 0; cell < HCU_MAIN_MENU_GLYPH_COUNT; ++cell) {
			unsigned covered = 0, y, x;
			for (y = 0; y < HCU_MAIN_MENU_GLYPH_CELL; ++y)
				for (x = 0; x < HCU_MAIN_MENU_GLYPH_CELL; ++x) {
					unsigned index = y * HCU_MAIN_MENU_GLYPH_ATLAS_W +
						cell * HCU_MAIN_MENU_GLYPH_CELL + x;
					if (hcu_main_menu_glyphs_rgb5a1[index] & 0x8000u) ++covered;
				}
			if (!covered) return 35;
		}
		for (i = HCU_MAIN_MENU_GLYPH_COUNT * HCU_MAIN_MENU_GLYPH_CELL;
			i < HCU_MAIN_MENU_GLYPH_ATLAS_W; ++i) {
			unsigned y;
			for (y = 0; y < HCU_MAIN_MENU_GLYPH_ATLAS_H; ++y)
				if (hcu_main_menu_glyphs_rgb5a1[y * HCU_MAIN_MENU_GLYPH_ATLAS_W + i] & 0x8000u)
					return 36;
		}
	}
	printf("main-menu-ok texture-hash=%08x changed=%u\n",
		texture_hash(a, 128 * 128) ^ texture_hash(b, 128 * 128), changed);
	return 0;
}
