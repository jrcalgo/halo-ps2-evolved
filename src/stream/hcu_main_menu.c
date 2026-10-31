#include "stream/hcu_main_menu.h"

#include <string.h>
#include <stdio.h>
#include <stdlib.h>

#if defined(__mips__)
#include "stream/hcu_spu_playback.h"
#include "stream/hcu_file_bridge.h"
#include "stream/hcu_loading_screen.h"

static void menu_sound(const char *path, unsigned event, unsigned frame)
{
	hcu_sound_request request;
	if (!hcu_spu_ready()) return;
	memset(&request, 0, sizeof(request));
	request.event = (uint16_t)event;
	request.owner_kind = HCU_SOUND_OWNER_UNATTACHED;
	request.owner_datum = path[6] == 'm' ? 0x4843554du : frame;
	/* Keep the retail title music at its extracted tag gain. It is a single
	 * menu voice, so it does not need the extra attenuation used for UI SFX. */
	request.gain = path[6] == 'm' ? 1.0f : 0.8f;
	request.pitch = 1.0f;
	request.priority = path[6] == 'm' ? 1 : 3;
	request.game_time = frame * 1000u / 60u;
	printf("HALO_PS2_LOCAL menu-sound begin path=%s event=%u\n", path, event);
	hcu_spu_request(&request, hcu_spu_name_hash(path));
	printf("HALO_PS2_LOCAL menu-sound end path=%s\n", path);
}
#endif

/* GS-ready assets derived from the user's retail Halo CE ui.map.  The ring's
 * landscape and plated hull remain separate, as they are in the retail scene.
 * The PS2 game loads these from its asset package to keep the ELF in budget. */
#if !defined(__mips__)
__asm__(
	".section .rodata\n"
	".balign 64\n"
	".global hcu_main_menu_ring_inner_rgb5a1\n"
	"hcu_main_menu_ring_inner_rgb5a1:\n"
	".incbin \"src/stream/assets/halo_ce_ring_inner.rgb5a1\"\n"
	".balign 64\n"
	".global hcu_main_menu_ring_outer_rgb5a1\n"
	"hcu_main_menu_ring_outer_rgb5a1:\n"
	".incbin \"src/stream/assets/halo_ce_ring_outer.rgb5a1\"\n"
	".balign 64\n"
	".global hcu_main_menu_ring_shadow_rgb5a1\n"
	"hcu_main_menu_ring_shadow_rgb5a1:\n"
	".incbin \"src/stream/assets/halo_ce_ring_shadow.rgb5a1\"\n"
	".balign 64\n"
	".global hcu_main_menu_map_atlas_rgb5a1\n"
	"hcu_main_menu_map_atlas_rgb5a1:\n"
	".incbin \"src/stream/assets/halo_ce_map_atlas.rgb5a1\"\n"
	".balign 64\n"
	".global hcu_main_menu_gametype_atlas_rgb5a1\n"
	"hcu_main_menu_gametype_atlas_rgb5a1:\n"
	".incbin \"src/stream/assets/halo_ce_gametype_atlas.rgb5a1\"\n"
	".balign 64\n"
	".global hcu_main_menu_logo_rgb5a1\n"
	"hcu_main_menu_logo_rgb5a1:\n"
	".incbin \"src/stream/assets/halo_ce_logo.rgb5a1\"\n"
	".balign 64\n"
	".global hcu_main_menu_buttons_rgb5a1\n"
	"hcu_main_menu_buttons_rgb5a1:\n"
	".incbin \"src/stream/assets/halo_ce_buttons.rgb5a1\"\n"
	".balign 64\n"
	".global hcu_main_menu_planet_rgb5a1\n"
	"hcu_main_menu_planet_rgb5a1:\n"
	".incbin \"src/stream/assets/halo_ce_planet.rgb5a1\"\n"
	".balign 64\n"
	".global hcu_main_menu_space_rgb5a1\n"
	"hcu_main_menu_space_rgb5a1:\n"
	".incbin \"src/stream/assets/halo_ce_space.rgb5a1\"\n"
	".balign 64\n"
	".global hcu_main_menu_stars_rgb5a1\n"
	"hcu_main_menu_stars_rgb5a1:\n"
	".incbin \"src/stream/assets/halo_ce_stars.rgb5a1\"\n"
	".balign 16\n"
	".global hcu_main_menu_camera_bin\n"
	"hcu_main_menu_camera_bin:\n"
	".incbin \"src/stream/assets/halo_ce_camera.bin\"\n"
	".balign 16\n"
	".global hcu_main_menu_ring_mesh_bin\n"
	"hcu_main_menu_ring_mesh_bin:\n"
	".incbin \"src/stream/assets/halo_ce_ring_mesh.bin\"\n"
	".global hcu_main_menu_ring_mesh_end\n"
	"hcu_main_menu_ring_mesh_end:\n"
	".previous\n");

extern const uint16_t hcu_main_menu_ring_inner_rgb5a1[];
extern const uint16_t hcu_main_menu_ring_outer_rgb5a1[];
extern const uint16_t hcu_main_menu_ring_shadow_rgb5a1[];
extern const uint16_t hcu_main_menu_map_atlas_rgb5a1[];
extern const uint16_t hcu_main_menu_gametype_atlas_rgb5a1[];
extern const uint16_t hcu_main_menu_logo_rgb5a1[];
extern const uint16_t hcu_main_menu_buttons_rgb5a1[];
extern const uint16_t hcu_main_menu_planet_rgb5a1[];
extern const uint16_t hcu_main_menu_space_rgb5a1[];
extern const uint16_t hcu_main_menu_stars_rgb5a1[];
extern const uint8_t hcu_main_menu_camera_bin[];
extern const uint8_t hcu_main_menu_ring_mesh_bin[];
extern const uint8_t hcu_main_menu_ring_mesh_end[];
#endif

/* Controller glyphs are small enough to keep in the ELF. A disc package that
 * already includes the atlas is preferred; an older package uses this copy. */
__asm__(
	".section .rodata\n"
	".balign 64\n"
	".global hcu_main_menu_glyphs_rgb5a1\n"
	"hcu_main_menu_glyphs_rgb5a1:\n"
	".incbin \"src/stream/assets/ps2_button_glyphs.rgb5a1\"\n"
	".previous\n");

extern const uint16_t hcu_main_menu_glyphs_rgb5a1[];

static const char *const s_title_items[HCU_MAIN_MENU_ITEM_COUNT] = {
	"MULTIPLAYER", "SETTINGS"
};

static const char *const s_maps[HCU_MAIN_MENU_MAP_COUNT] = {
	"BATTLE CREEK", "SIDEWINDER", "DAMNATION", "RAT RACE", "PRISONER",
	"HANG 'EM HIGH", "CHILL OUT", "DERELICT", "BOARDING ACTION",
	"BLOOD GULCH", "WIZARD", "CHIRON TL-34", "LONGEST"
};

static const char *const s_game_types[HCU_MAIN_MENU_GAME_TYPE_COUNT] = {
	"CAPTURE THE FLAG", "KING OF THE HILL", "SLAYER", "ODDBALL", "RACE",
	"TEAM SLAYER"
};

enum {
	LOBBY_GAME_TYPE, LOBBY_MAP, LOBBY_OPTIONS, LOBBY_SAVE, LOBBY_START,
	LOBBY_ROW_COUNT
};
enum {
	OPTION_MODE_RULES, OPTION_PLAYER, OPTION_ITEMS, OPTION_INDICATORS, OPTION_BACK,
	OPTION_ROW_COUNT
};
enum {
	PLAYER_LIVES, PLAYER_HEALTH, PLAYER_SHIELDS, PLAYER_RESPAWN,
	PLAYER_RESPAWN_GROWTH, PLAYER_ODD_MAN_OUT, PLAYER_INVISIBLE,
	PLAYER_SUICIDE_PENALTY, PLAYER_BACK, PLAYER_ROW_COUNT
};
enum {
	ITEM_GRENADES, ITEM_VEHICLES, ITEM_WEAPONS, ITEM_STARTING_EQUIPMENT,
	ITEM_BACK, ITEM_ROW_COUNT
};
enum {
	INDICATOR_RADAR_DISPLAY, INDICATOR_OTHER_PLAYERS, INDICATOR_FRIENDS,
	INDICATOR_BACK, INDICATOR_ROW_COUNT
};
enum {
	PROFILE_NAME, PROFILE_LAYOUT, PROFILE_COLOR, PROFILE_INVERT, PROFILE_SENSITIVITY,
	PROFILE_VIBRATION, PROFILE_ACTIVE, PROFILE_BACK, PROFILE_ROW_COUNT
};
enum {
	CONTROL_PROFILE, CONTROL_LAYOUT, CONTROL_INVERT, CONTROL_SENSITIVITY,
	CONTROL_VIBRATION, CONTROL_BACK, CONTROL_ROW_COUNT
};
enum {
	SETTING_RESOLUTION, SETTING_ANIMATIONS, SETTING_PARTICLES, SETTING_VIEW_MODEL,
	SETTING_TERRAIN, SETTING_WIDESCREEN, SETTING_HUD_INSET, SETTING_FPS,
	SETTING_SUBTITLES, SETTING_BACK, SETTING_ROW_COUNT
};
enum { SETTINGS_PROFILES, SETTINGS_CONTROLS, SETTINGS_VIDEO, SETTINGS_BACK, SETTINGS_HUB_ROWS };

static unsigned menu_wrap(unsigned value, int step, unsigned count)
{
	if (!count) return 0;
	if (step < 0) return value ? value - 1u : count - 1u;
	return value + 1u < count ? value + 1u : 0u;
}

static void menu_variant_defaults(hcu_main_menu_variant *variant, unsigned game_type)
{
	if (!variant) return;
	memset(variant, 0, sizeof(*variant));
	variant->valid = 1;
	variant->game_type = (uint8_t)(game_type % HCU_MAIN_MENU_GAME_TYPE_COUNT);
	variant->score_index = 1;
	variant->teams = variant->game_type == HCU_GAME_CTF ||
		variant->game_type == HCU_GAME_TEAM_SLAYER;
	variant->maximum_health = 1;
	variant->shields = 1;
	variant->vehicle_set = 2; /* WARTHOG: CE's stock local-game default. */
	variant->radar_display = variant->game_type == HCU_GAME_SLAYER ||
		variant->game_type == HCU_GAME_TEAM_SLAYER ? 0 : 1;
	variant->other_players_radar = 1;
	variant->friends_on_screen = 1;
	variant->oddball_ball_count = 0;
	variant->oddball_speed_with_ball = 1; /* NORMAL in the retail spinner. */
	variant->suicide_penalty = 1;
	if (variant->game_type == HCU_GAME_CTF) variant->respawn_time = 2;
	else if (variant->game_type == HCU_GAME_KING || variant->game_type == HCU_GAME_ODDBALL)
		variant->respawn_time = 1;
	if (variant->game_type == HCU_GAME_SLAYER) {
		variant->score_index = 2; variant->suicide_penalty = 2;
	} else if (variant->game_type == HCU_GAME_TEAM_SLAYER) {
		variant->score_index = 4; variant->respawn_time = 2;
		variant->suicide_penalty = 2;
	} else if (variant->game_type == HCU_GAME_RACE) variant->suicide_penalty = 2;
	if (variant->game_type == HCU_GAME_ODDBALL) variant->vehicle_set = 1;
}

static hcu_main_menu_variant *menu_saved_variants(hcu_main_menu_state *state)
{
	return state->saved_variants[state->port_profile[0] % HCU_MAIN_MENU_PROFILE_COUNT];
}

static const hcu_main_menu_variant *menu_saved_variants_const(
	const hcu_main_menu_state *state)
{
	return state->saved_variants[state->port_profile[0] % HCU_MAIN_MENU_PROFILE_COUNT];
}

static void menu_profile_init(hcu_main_menu_profile *profile, unsigned index)
{
	memset(profile, 0, sizeof(*profile));
	snprintf(profile->name, sizeof(profile->name), "SPARTAN %u", index + 1u);
	profile->name[HCU_MAIN_MENU_PROFILE_NAME_LENGTH] = '\0';
	profile->armor_color = (uint8_t)index;
	profile->look_sensitivity = 5;
	profile->vibration = 1;
}

void hcu_main_menu_state_init(hcu_main_menu_state *state)
{
	unsigned i;
	if (!state) return;
	memset(state, 0, sizeof(*state));
	state->particles = 1;
	state->subtitles = 1;
	state->view_model = 1;
	state->widescreen = 1; /* ANAMORPHIC; menu_storage_load may override */
	for (i = 0; i < HCU_MAIN_MENU_PROFILE_COUNT; ++i) {
		menu_profile_init(&state->profiles[i], i);
		if (i < 4u) state->port_profile[i] = (uint8_t)i;
	}
	state->session.map = 9;
	state->session.variant_index = HCU_GAME_SLAYER;
	menu_variant_defaults(&state->session.variant, HCU_GAME_SLAYER);
}

const char *hcu_main_menu_item_label(unsigned item)
{
	return item < HCU_MAIN_MENU_ITEM_COUNT ? s_title_items[item] : "";
}

const char *hcu_main_menu_map_label(unsigned map)
{
	return map < HCU_MAIN_MENU_MAP_COUNT ? s_maps[map] : "";
}

const char *hcu_main_menu_game_type_label(unsigned game_type)
{
	return game_type < HCU_MAIN_MENU_GAME_TYPE_COUNT ? s_game_types[game_type] : "";
}

static void menu_apply_variant_selection(hcu_main_menu_state *state, unsigned selection)
{
	hcu_main_menu_variant *saved = menu_saved_variants(state);
	state->session.variant_index = (uint8_t)selection;
	if (selection < HCU_MAIN_MENU_GAME_TYPE_COUNT)
		menu_variant_defaults(&state->session.variant, selection);
	else {
		unsigned slot = selection - HCU_MAIN_MENU_GAME_TYPE_COUNT;
		if (slot < HCU_MAIN_MENU_SAVED_VARIANT_COUNT && saved[slot].valid)
			state->session.variant = saved[slot];
	}
}

static void menu_step_variant_selection(hcu_main_menu_state *state, int step)
{
	const hcu_main_menu_variant *saved = menu_saved_variants_const(state);
	unsigned selection = state->session.variant_index;
	unsigned count = HCU_MAIN_MENU_GAME_TYPE_COUNT + HCU_MAIN_MENU_SAVED_VARIANT_COUNT;
	unsigned tries;
	for (tries = 0; tries < count; ++tries) {
		selection = menu_wrap(selection, step, count);
		if (selection < HCU_MAIN_MENU_GAME_TYPE_COUNT ||
			saved[selection - HCU_MAIN_MENU_GAME_TYPE_COUNT].valid) {
			menu_apply_variant_selection(state, selection);
			return;
		}
	}
}

static void menu_profile_owner_changed(hcu_main_menu_state *state)
{
	unsigned selection = state->session.variant_index;
	if (selection >= HCU_MAIN_MENU_GAME_TYPE_COUNT) {
		unsigned slot = selection - HCU_MAIN_MENU_GAME_TYPE_COUNT;
		const hcu_main_menu_variant *saved = menu_saved_variants_const(state);
		if (slot < HCU_MAIN_MENU_SAVED_VARIANT_COUNT && saved[slot].valid)
			state->session.variant = saved[slot];
		else
			menu_apply_variant_selection(state, HCU_GAME_SLAYER);
	}
}

static char menu_name_character(char current, int step)
{
	static const char characters[] = " ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_";
	unsigned i, count = (unsigned)sizeof(characters) - 1u;
	for (i = 0; i < count && characters[i] != current; ++i) {}
	if (i == count) i = 0;
	return characters[menu_wrap(i, step, count)];
}

static void menu_adjust_setting(hcu_main_menu_state *state, int step)
{
	switch (state->row) {
	case SETTING_RESOLUTION: state->resolution = (uint8_t)menu_wrap(state->resolution, step, 4); break;
	case SETTING_ANIMATIONS: state->animation_rate ^= 1; break;
	case SETTING_PARTICLES: state->particles ^= 1; break;
	case SETTING_VIEW_MODEL: state->view_model = (uint8_t)menu_wrap(state->view_model, step, 4); break;
	case SETTING_TERRAIN: state->terrain_detail = (uint8_t)menu_wrap(state->terrain_detail, step, 4); break;
	case SETTING_WIDESCREEN: state->widescreen ^= 1; break;
	case SETTING_HUD_INSET: state->hud_inset = (uint8_t)menu_wrap(state->hud_inset, step, 6); break;
	case SETTING_FPS: state->fps_counter ^= 1; break;
	case SETTING_SUBTITLES: state->subtitles ^= 1; break;
	default: break;
	}
}

static void menu_adjust_profile(hcu_main_menu_state *state, int step, int controls_page)
{
	hcu_main_menu_profile *profile = &state->profiles[state->profile_index];
	unsigned row = state->row;
	if (controls_page && row == CONTROL_PROFILE) {
		state->profile_index = (uint8_t)menu_wrap(state->profile_index, step,
			HCU_MAIN_MENU_PROFILE_COUNT);
		return;
	}
	if (controls_page) {
		if (row == CONTROL_LAYOUT) row = PROFILE_LAYOUT;
		else if (row == CONTROL_INVERT) row = PROFILE_INVERT;
		else if (row == CONTROL_SENSITIVITY) row = PROFILE_SENSITIVITY;
		else if (row == CONTROL_VIBRATION) row = PROFILE_VIBRATION;
	}
	switch (row) {
	case PROFILE_LAYOUT: profile->control_layout = (uint8_t)menu_wrap(profile->control_layout, step, 5); break;
	case PROFILE_COLOR: profile->armor_color = (uint8_t)menu_wrap(profile->armor_color, step, 8); break;
	case PROFILE_INVERT: profile->look_inverted ^= 1; break;
	case PROFILE_SENSITIVITY: profile->look_sensitivity = (uint8_t)menu_wrap(profile->look_sensitivity - 1u, step, 10) + 1u; break;
	case PROFILE_VIBRATION: profile->vibration ^= 1; break;
	default: break;
	}
}

static unsigned menu_mode_row_count(unsigned game_type)
{
	switch (game_type) {
	case HCU_GAME_CTF: return 6;
	case HCU_GAME_KING: return 4;
	case HCU_GAME_ODDBALL: return 9;
	case HCU_GAME_RACE: return 5;
	default: return 6; /* Slayer and Team Slayer. */
	}
}

static void menu_adjust_mode_option(hcu_main_menu_state *state, int step)
{
	hcu_main_menu_variant *v = &state->session.variant;
	switch (v->game_type) {
	case HCU_GAME_CTF:
		if (state->row == 0) v->ctf_assault ^= 1;
		else if (state->row == 1) v->ctf_single_flag = (uint8_t)menu_wrap(v->ctf_single_flag, step, 6);
		else if (state->row == 2) v->ctf_flag_must_reset ^= 1;
		else if (state->row == 3) v->ctf_flag_at_home ^= 1;
		else if (state->row == 4) v->score_index = (uint8_t)menu_wrap(v->score_index, step, 5);
		break;
	case HCU_GAME_KING:
		if (state->row == 0) v->king_moving_hill ^= 1;
		else if (state->row == 1) v->score_index = (uint8_t)menu_wrap(v->score_index, step, 5);
		else if (state->row == 2) v->teams ^= 1;
		break;
	case HCU_GAME_ODDBALL:
		if (state->row == 0) v->oddball_trait_with_ball = (uint8_t)menu_wrap(v->oddball_trait_with_ball, step, 4);
		else if (state->row == 1) v->oddball_trait_without_ball = (uint8_t)menu_wrap(v->oddball_trait_without_ball, step, 4);
		else if (state->row == 2) v->oddball_speed_with_ball = (uint8_t)menu_wrap(v->oddball_speed_with_ball, step, 3);
		else if (state->row == 3) v->oddball_ball_type = (uint8_t)menu_wrap(v->oddball_ball_type, step, 3);
		else if (state->row == 4) v->oddball_random_start ^= 1;
		else if (state->row == 5) v->oddball_ball_count = (uint8_t)menu_wrap(v->oddball_ball_count, step, 16);
		else if (state->row == 6) v->score_index = (uint8_t)menu_wrap(v->score_index, step, 5);
		else if (state->row == 7) v->teams ^= 1;
		break;
	case HCU_GAME_RACE:
		if (state->row == 0) v->race_team_scoring = (uint8_t)menu_wrap(v->race_team_scoring, step, 3);
		else if (state->row == 1) v->race_type = (uint8_t)menu_wrap(v->race_type, step, 3);
		else if (state->row == 2) v->score_index = (uint8_t)menu_wrap(v->score_index, step, 6);
		else if (state->row == 3) v->teams ^= 1;
		break;
	default:
		if (state->row == 0) v->slayer_death_bonus ^= 1;
		else if (state->row == 1) v->slayer_kill_in_order ^= 1;
		else if (state->row == 2) v->slayer_kill_penalty ^= 1;
		else if (state->row == 3) v->score_index = (uint8_t)menu_wrap(v->score_index, step, 5);
		else if (state->row == 4) v->teams ^= 1;
		break;
	}
}

static void menu_adjust_player_option(hcu_main_menu_state *state, int step)
{
	hcu_main_menu_variant *v = &state->session.variant;
	switch (state->row) {
	case PLAYER_LIVES: v->lives = (uint8_t)menu_wrap(v->lives, step, 4); break;
	case PLAYER_HEALTH: v->maximum_health = (uint8_t)menu_wrap(v->maximum_health, step, 6); break;
	case PLAYER_SHIELDS: v->shields ^= 1; break;
	case PLAYER_RESPAWN: v->respawn_time = (uint8_t)menu_wrap(v->respawn_time, step, 4); break;
	case PLAYER_RESPAWN_GROWTH: v->respawn_growth = (uint8_t)menu_wrap(v->respawn_growth, step, 4); break;
	case PLAYER_ODD_MAN_OUT: v->odd_man_out ^= 1; break;
	case PLAYER_INVISIBLE: v->invisible_players ^= 1; break;
	case PLAYER_SUICIDE_PENALTY: v->suicide_penalty = (uint8_t)menu_wrap(v->suicide_penalty, step, 4); break;
	default: break;
	}
}

static void menu_adjust_item_option(hcu_main_menu_state *state, int step)
{
	hcu_main_menu_variant *v = &state->session.variant;
	switch (state->row) {
	case ITEM_GRENADES: v->infinite_grenades ^= 1; break;
	case ITEM_VEHICLES: v->vehicle_set = (uint8_t)menu_wrap(v->vehicle_set, step, 5); break;
	case ITEM_WEAPONS: v->weapon_set = (uint8_t)menu_wrap(v->weapon_set, step, 11); break;
	case ITEM_STARTING_EQUIPMENT: v->starting_equipment ^= 1; break;
	default: break;
	}
}

static void menu_adjust_indicator_option(hcu_main_menu_state *state, int step)
{
	hcu_main_menu_variant *v = &state->session.variant;
	switch (state->row) {
	case INDICATOR_RADAR_DISPLAY: v->radar_display = (uint8_t)menu_wrap(v->radar_display, step, 3); break;
	case INDICATOR_OTHER_PLAYERS: v->other_players_radar ^= 1; break;
	case INDICATOR_FRIENDS: v->friends_on_screen ^= 1; break;
	default: break;
	}
}

enum hcu_main_menu_action hcu_main_menu_step(hcu_main_menu_state *state,
	int up, int down, int left, int right, int confirm, int back)
{
	int step = left ? -1 : (right || confirm) ? 1 : 0;
	if (!state) return HCU_MAIN_MENU_ACTION_NONE;
	if (state->page == HCU_MAIN_MENU_PAGE_TITLE) {
		if (up) state->item = (uint8_t)menu_wrap(state->item, -1, HCU_MAIN_MENU_ITEM_COUNT);
		else if (down) state->item = (uint8_t)menu_wrap(state->item, 1, HCU_MAIN_MENU_ITEM_COUNT);
		if (!confirm) return HCU_MAIN_MENU_ACTION_NONE;
		state->row = 0;
		switch (state->item) {
		case HCU_MAIN_MENU_MULTIPLAYER: state->page = HCU_MAIN_MENU_PAGE_CONNECT; break;
		default: state->page = HCU_MAIN_MENU_PAGE_SETTINGS; break;
		}
		return HCU_MAIN_MENU_ACTION_NONE;
	}
	if (back) {
		switch (state->page) {
		case HCU_MAIN_MENU_PAGE_MODE_OPTIONS:
		case HCU_MAIN_MENU_PAGE_PLAYER_OPTIONS:
		case HCU_MAIN_MENU_PAGE_ITEM_OPTIONS:
		case HCU_MAIN_MENU_PAGE_INDICATOR_OPTIONS:
			state->page = HCU_MAIN_MENU_PAGE_GAME_OPTIONS; break;
		case HCU_MAIN_MENU_PAGE_GAME_OPTIONS:
		case HCU_MAIN_MENU_PAGE_SAVE_VARIANT: state->page = HCU_MAIN_MENU_PAGE_LOBBY; break;
		case HCU_MAIN_MENU_PAGE_PROFILE_EDIT: state->page = HCU_MAIN_MENU_PAGE_PROFILE_SELECT; break;
		case HCU_MAIN_MENU_PAGE_PROFILE_NAME: state->page = HCU_MAIN_MENU_PAGE_PROFILE_EDIT; break;
		case HCU_MAIN_MENU_PAGE_LOBBY: state->page = HCU_MAIN_MENU_PAGE_CONNECT; break;
		case HCU_MAIN_MENU_PAGE_PROFILE_SELECT:
		case HCU_MAIN_MENU_PAGE_CONTROLS:
		case HCU_MAIN_MENU_PAGE_VIDEO_SETTINGS:
			state->page = HCU_MAIN_MENU_PAGE_SETTINGS; break;
		default: state->page = HCU_MAIN_MENU_PAGE_TITLE; break;
		}
		state->row = state->page == HCU_MAIN_MENU_PAGE_PROFILE_SELECT ? state->profile_index : 0;
		return HCU_MAIN_MENU_ACTION_NONE;
	}
	if (state->page == HCU_MAIN_MENU_PAGE_CONNECT) {
		if (confirm && !state->player_count) {
			state->joined_mask |= 1u;
			state->player_count = 1;
		} else if (confirm && state->player_count) {
			state->page = HCU_MAIN_MENU_PAGE_LOBBY;
			state->row = 0;
		}
		return HCU_MAIN_MENU_ACTION_NONE;
	}
	if (state->page == HCU_MAIN_MENU_PAGE_LOBBY) {
		if (up) state->row = (uint8_t)menu_wrap(state->row, -1, LOBBY_ROW_COUNT);
		else if (down) state->row = (uint8_t)menu_wrap(state->row, 1, LOBBY_ROW_COUNT);
		if ((left || right) && state->row == LOBBY_GAME_TYPE)
			menu_step_variant_selection(state, left ? -1 : 1);
		else if ((left || right) && state->row == LOBBY_MAP)
			state->session.map = (uint8_t)menu_wrap(state->session.map, left ? -1 : 1,
				HCU_MAIN_MENU_MAP_COUNT);
		if (confirm && state->row == LOBBY_OPTIONS) { state->page = HCU_MAIN_MENU_PAGE_GAME_OPTIONS; state->row = 0; }
		else if (confirm && state->row == LOBBY_SAVE) { state->page = HCU_MAIN_MENU_PAGE_SAVE_VARIANT; state->row = 0; }
		else if (confirm && state->row == LOBBY_START && state->player_count)
			return HCU_MAIN_MENU_ACTION_MULTIPLAYER;
		return HCU_MAIN_MENU_ACTION_NONE;
	}
	if (state->page == HCU_MAIN_MENU_PAGE_GAME_OPTIONS) {
		if (up) state->row = (uint8_t)menu_wrap(state->row, -1, OPTION_ROW_COUNT);
		else if (down) state->row = (uint8_t)menu_wrap(state->row, 1, OPTION_ROW_COUNT);
		if (state->row == OPTION_BACK && confirm) { state->page = HCU_MAIN_MENU_PAGE_LOBBY; state->row = LOBBY_OPTIONS; }
		else if (confirm) {
			if (state->row == OPTION_MODE_RULES) state->page = HCU_MAIN_MENU_PAGE_MODE_OPTIONS;
			else if (state->row == OPTION_PLAYER) state->page = HCU_MAIN_MENU_PAGE_PLAYER_OPTIONS;
			else if (state->row == OPTION_ITEMS) state->page = HCU_MAIN_MENU_PAGE_ITEM_OPTIONS;
			else if (state->row == OPTION_INDICATORS) state->page = HCU_MAIN_MENU_PAGE_INDICATOR_OPTIONS;
			state->row = 0;
		}
		return HCU_MAIN_MENU_ACTION_NONE;
	}
	if (state->page == HCU_MAIN_MENU_PAGE_MODE_OPTIONS) {
		unsigned count = menu_mode_row_count(state->session.variant.game_type);
		if (up) state->row = (uint8_t)menu_wrap(state->row, -1, count);
		else if (down) state->row = (uint8_t)menu_wrap(state->row, 1, count);
		if (confirm && state->row + 1u == count) { state->page = HCU_MAIN_MENU_PAGE_GAME_OPTIONS; state->row = OPTION_MODE_RULES; }
		else if (step && state->row + 1u < count) menu_adjust_mode_option(state, step);
		return HCU_MAIN_MENU_ACTION_NONE;
	}
	if (state->page == HCU_MAIN_MENU_PAGE_PLAYER_OPTIONS) {
		if (up) state->row = (uint8_t)menu_wrap(state->row, -1, PLAYER_ROW_COUNT);
		else if (down) state->row = (uint8_t)menu_wrap(state->row, 1, PLAYER_ROW_COUNT);
		if (confirm && state->row == PLAYER_BACK) { state->page = HCU_MAIN_MENU_PAGE_GAME_OPTIONS; state->row = OPTION_PLAYER; }
		else if (step && state->row != PLAYER_BACK) menu_adjust_player_option(state, step);
		return HCU_MAIN_MENU_ACTION_NONE;
	}
	if (state->page == HCU_MAIN_MENU_PAGE_ITEM_OPTIONS) {
		if (up) state->row = (uint8_t)menu_wrap(state->row, -1, ITEM_ROW_COUNT);
		else if (down) state->row = (uint8_t)menu_wrap(state->row, 1, ITEM_ROW_COUNT);
		if (confirm && state->row == ITEM_BACK) { state->page = HCU_MAIN_MENU_PAGE_GAME_OPTIONS; state->row = OPTION_ITEMS; }
		else if (step && state->row != ITEM_BACK) menu_adjust_item_option(state, step);
		return HCU_MAIN_MENU_ACTION_NONE;
	}
	if (state->page == HCU_MAIN_MENU_PAGE_INDICATOR_OPTIONS) {
		if (up) state->row = (uint8_t)menu_wrap(state->row, -1, INDICATOR_ROW_COUNT);
		else if (down) state->row = (uint8_t)menu_wrap(state->row, 1, INDICATOR_ROW_COUNT);
		if (confirm && state->row == INDICATOR_BACK) { state->page = HCU_MAIN_MENU_PAGE_GAME_OPTIONS; state->row = OPTION_INDICATORS; }
		else if (step && state->row != INDICATOR_BACK) menu_adjust_indicator_option(state, step);
		return HCU_MAIN_MENU_ACTION_NONE;
	}
	if (state->page == HCU_MAIN_MENU_PAGE_SAVE_VARIANT) {
		hcu_main_menu_variant *saved = menu_saved_variants(state);
		if (up) state->row = (uint8_t)menu_wrap(state->row, -1, HCU_MAIN_MENU_SAVED_VARIANT_COUNT + 1u);
		else if (down) state->row = (uint8_t)menu_wrap(state->row, 1, HCU_MAIN_MENU_SAVED_VARIANT_COUNT + 1u);
		if (confirm && state->row < HCU_MAIN_MENU_SAVED_VARIANT_COUNT) {
			saved[state->row] = state->session.variant;
			saved[state->row].valid = 1;
			menu_apply_variant_selection(state, HCU_MAIN_MENU_GAME_TYPE_COUNT + state->row);
			state->page = HCU_MAIN_MENU_PAGE_LOBBY;
			state->row = LOBBY_SAVE;
		} else if (confirm) { state->page = HCU_MAIN_MENU_PAGE_LOBBY; state->row = LOBBY_SAVE; }
		return HCU_MAIN_MENU_ACTION_NONE;
	}
	if (state->page == HCU_MAIN_MENU_PAGE_PROFILE_SELECT) {
		if (up && state->row >= 3u) state->row -= 3u;
		else if (down && state->row + 3u < HCU_MAIN_MENU_PROFILE_COUNT) state->row += 3u;
		else if (left && state->row % 3u) --state->row;
		else if (right && state->row % 3u != 2u) ++state->row;
		if (confirm && state->row < HCU_MAIN_MENU_PROFILE_COUNT &&
			(state->profile_present_mask & (1u << state->row))) {
			state->profile_index = state->row;
			state->page = HCU_MAIN_MENU_PAGE_PROFILE_EDIT;
			state->row = 0;
		}
		return HCU_MAIN_MENU_ACTION_NONE;
	}
	if (state->page == HCU_MAIN_MENU_PAGE_PROFILE_EDIT) {
		hcu_main_menu_profile *profile = &state->profiles[state->profile_index];
		if (up) state->row = (uint8_t)menu_wrap(state->row, -1, PROFILE_ROW_COUNT);
		else if (down) state->row = (uint8_t)menu_wrap(state->row, 1, PROFILE_ROW_COUNT);
		if (confirm && state->row == PROFILE_NAME) { state->page = HCU_MAIN_MENU_PAGE_PROFILE_NAME; state->name_cursor = 0; }
		else if (confirm && state->row == PROFILE_ACTIVE) {
			state->port_profile[0] = state->profile_index;
			menu_profile_owner_changed(state);
		}
		else if (confirm && state->row == PROFILE_BACK) { state->page = HCU_MAIN_MENU_PAGE_PROFILE_SELECT; state->row = state->profile_index; }
		else if (step && state->row != PROFILE_NAME) menu_adjust_profile(state, step, 0);
		(void)profile;
		return HCU_MAIN_MENU_ACTION_NONE;
	}
	if (state->page == HCU_MAIN_MENU_PAGE_PROFILE_NAME) {
		hcu_main_menu_profile *profile = &state->profiles[state->profile_index];
		if (left) state->name_cursor = (uint8_t)menu_wrap(state->name_cursor, -1, HCU_MAIN_MENU_PROFILE_NAME_LENGTH);
		else if (right) state->name_cursor = (uint8_t)menu_wrap(state->name_cursor, 1, HCU_MAIN_MENU_PROFILE_NAME_LENGTH);
		if (up) profile->name[state->name_cursor] = menu_name_character(profile->name[state->name_cursor], 1);
		else if (down) profile->name[state->name_cursor] = menu_name_character(profile->name[state->name_cursor], -1);
		if (confirm) { state->page = HCU_MAIN_MENU_PAGE_PROFILE_EDIT; state->row = PROFILE_NAME; }
		return HCU_MAIN_MENU_ACTION_NONE;
	}
	if (state->page == HCU_MAIN_MENU_PAGE_CONTROLS) {
		if (up) state->row = (uint8_t)menu_wrap(state->row, -1, CONTROL_ROW_COUNT);
		else if (down) state->row = (uint8_t)menu_wrap(state->row, 1, CONTROL_ROW_COUNT);
		if (confirm && state->row == CONTROL_BACK) { state->page = HCU_MAIN_MENU_PAGE_SETTINGS; state->row = SETTINGS_CONTROLS; }
		else if (step && state->row != CONTROL_BACK) menu_adjust_profile(state, step, 1);
		return HCU_MAIN_MENU_ACTION_NONE;
	}
	if (state->page == HCU_MAIN_MENU_PAGE_SETTINGS) {
		if (up) state->row = (uint8_t)menu_wrap(state->row, -1, SETTINGS_HUB_ROWS);
		else if (down) state->row = (uint8_t)menu_wrap(state->row, 1, SETTINGS_HUB_ROWS);
		if (confirm) {
			unsigned selection = state->row;
			if (selection == SETTINGS_PROFILES) state->page = HCU_MAIN_MENU_PAGE_PROFILE_SELECT;
			else if (selection == SETTINGS_CONTROLS) state->page = HCU_MAIN_MENU_PAGE_CONTROLS;
			else if (selection == SETTINGS_VIDEO) state->page = HCU_MAIN_MENU_PAGE_VIDEO_SETTINGS;
			else state->page = HCU_MAIN_MENU_PAGE_TITLE;
			state->row = state->page == HCU_MAIN_MENU_PAGE_PROFILE_SELECT ? state->profile_index : 0;
		}
		return HCU_MAIN_MENU_ACTION_NONE;
	}
	if (state->page == HCU_MAIN_MENU_PAGE_VIDEO_SETTINGS) {
		if (up) state->row = (uint8_t)menu_wrap(state->row, -1, SETTING_ROW_COUNT);
		else if (down) state->row = (uint8_t)menu_wrap(state->row, 1, SETTING_ROW_COUNT);
		if (confirm && state->row == SETTING_BACK) { state->page = HCU_MAIN_MENU_PAGE_SETTINGS; state->row = SETTINGS_VIDEO; }
		else if (step && state->row != SETTING_BACK) menu_adjust_setting(state, step);
	}
	return HCU_MAIN_MENU_ACTION_NONE;
}

int hcu_main_menu_create_profile(hcu_main_menu_state *state)
{
	unsigned slot;
	if (!state || state->page != HCU_MAIN_MENU_PAGE_PROFILE_SELECT) return 0;
	slot = state->row;
	if (slot >= HCU_MAIN_MENU_PROFILE_COUNT ||
		(state->profile_present_mask & (1u << slot))) return 0;
	menu_profile_init(&state->profiles[slot], slot);
	memset(state->saved_variants[slot], 0, sizeof(state->saved_variants[slot]));
	state->profile_present_mask |= (uint32_t)(1u << slot);
	state->profile_index = (uint8_t)slot;
	state->page = HCU_MAIN_MENU_PAGE_PROFILE_EDIT;
	state->row = 0;
	return 1;
}

#if !defined(__mips__)
int hcu_main_menu_build_ring_texture(uint16_t *pixels, unsigned width,
	unsigned height)
{
	if (!pixels || width != 128u || height != 128u) return -1;
	memcpy(pixels, hcu_main_menu_ring_inner_rgb5a1,
		width * height * sizeof(*pixels));
	return 0;
}

int hcu_main_menu_build_ring_outer_texture(uint16_t *pixels, unsigned width,
	unsigned height)
{
	if (!pixels || width != 128u || height != 128u) return -1;
	memcpy(pixels, hcu_main_menu_ring_outer_rgb5a1,
		width * height * sizeof(*pixels));
	return 0;
}
#endif

/* Cell order matches tools/build_hcu_menu_assets.py GLYPH_SOURCES. */
enum {
	MENU_GLYPH_CROSS = 0, MENU_GLYPH_CIRCLE, MENU_GLYPH_SQUARE, MENU_GLYPH_TRIANGLE,
	MENU_GLYPH_START, MENU_GLYPH_SELECT, MENU_GLYPH_L1, MENU_GLYPH_L2,
	MENU_GLYPH_R1, MENU_GLYPH_R2, MENU_GLYPH_L3, MENU_GLYPH_R3, MENU_GLYPH_DPAD,
	MENU_GLYPH_COUNT
};

enum { MENU_PROMPT_TEXT = 0, MENU_PROMPT_ICON = 1 };

typedef struct menu_prompt_piece {
	uint8_t kind;
	uint8_t icon;
	uint16_t length;
	const char *text;
} menu_prompt_piece;

_Static_assert(MENU_GLYPH_COUNT == HCU_MAIN_MENU_GLYPH_COUNT, "glyph count");

static const char *const menu_glyph_tag[] = {
	"[cross]", "[circle]", "[square]", "[triangle]", "[start]", "[select]",
	"[l1]", "[l2]", "[r1]", "[r2]", "[l3]", "[r3]", "[dpad]"
};

_Static_assert(sizeof(menu_glyph_tag) / sizeof(menu_glyph_tag[0]) == MENU_GLYPH_COUNT,
	"glyph tags");

static int menu_word_char(unsigned char c)
{
	return (c >= 'A' && c <= 'Z') || (c >= '0' && c <= '9');
}

static int menu_button_word(const char *s, int *icon, unsigned *length)
{
	static const struct { const char *word; uint8_t icon; } words[] = {
		{ "TRIANGLE", MENU_GLYPH_TRIANGLE }, { "CIRCLE", MENU_GLYPH_CIRCLE },
		{ "SQUARE", MENU_GLYPH_SQUARE }, { "SELECT", MENU_GLYPH_SELECT },
		{ "CROSS", MENU_GLYPH_CROSS }, { "START", MENU_GLYPH_START },
		{ "RIGHT", MENU_GLYPH_DPAD }, { "LEFT", MENU_GLYPH_DPAD },
		{ "DOWN", MENU_GLYPH_DPAD }, { "L1", MENU_GLYPH_L1 },
		{ "L2", MENU_GLYPH_L2 }, { "L3", MENU_GLYPH_L3 },
		{ "R1", MENU_GLYPH_R1 }, { "R2", MENU_GLYPH_R2 },
		{ "R3", MENU_GLYPH_R3 }, { "UP", MENU_GLYPH_DPAD }
	};
	unsigned i;
	for (i = 0; i < sizeof(words) / sizeof(words[0]); ++i) {
		unsigned n = (unsigned)strlen(words[i].word);
		if (strncmp(s, words[i].word, n) == 0 && !menu_word_char((unsigned char)s[n])) {
			*icon = words[i].icon; *length = n; return 1;
		}
	}
	return 0;
}

/* A slash group is a button only when every piece is a button name. */
static int menu_button_group(const char *s, int *icons, const char **slash,
	unsigned *parts, unsigned *total)
{
	const char *p = s;
	unsigned n = 0;
	while (n < 6u) {
		int icon; unsigned len;
		if (!menu_button_word(p, &icon, &len)) return 0;
		icons[n] = icon; slash[n] = n ? p - 1 : NULL; ++n; p += len;
		if (*p != '/') break;
		++p;
	}
	*parts = n; *total = (unsigned)(p - s);
	return 1;
}

static int menu_piece_add(menu_prompt_piece *out, unsigned max, unsigned *count,
	uint8_t kind, uint8_t icon, const char *text, unsigned length)
{
	if (kind == MENU_PROMPT_TEXT && !length) return 0;
	if (kind == MENU_PROMPT_TEXT && *count && out[*count - 1u].kind == MENU_PROMPT_TEXT &&
		out[*count - 1u].text + out[*count - 1u].length == text) {
		out[*count - 1u].length = (uint16_t)(out[*count - 1u].length + length);
		return 0;
	}
	if (*count >= max) return -1;
	out[*count].kind = kind; out[*count].icon = icon;
	out[*count].text = text; out[*count].length = (uint16_t)length;
	++*count;
	return 0;
}

static int menu_emit_buttons(menu_prompt_piece *out, unsigned max, unsigned *count,
	const int *icons, const char **slash, unsigned parts)
{
	unsigned i = 0;
	while (i < parts) {
		if (icons[i] == MENU_GLYPH_DPAD) {
			unsigned j = i;
			while (j < parts && icons[j] == MENU_GLYPH_DPAD) ++j;
			if (i && menu_piece_add(out, max, count, MENU_PROMPT_TEXT, 0, slash[i], 1)) return -1;
			if (menu_piece_add(out, max, count, MENU_PROMPT_ICON, MENU_GLYPH_DPAD, NULL, 1)) return -1;
			i = j;
		} else {
			if (i && menu_piece_add(out, max, count, MENU_PROMPT_TEXT, 0, slash[i], 1)) return -1;
			if (menu_piece_add(out, max, count, MENU_PROMPT_ICON, (uint8_t)icons[i], NULL, 1)) return -1;
			++i;
		}
	}
	return 0;
}

static int menu_prompt_parse(const char *text, menu_prompt_piece *out, unsigned max,
	unsigned *count)
{
	const char *p = text, *run = text;
	unsigned run_len = 0, spaces = 0;
	int clause_icon = 0;
	*count = 0;
	if (!text) return -1;
	while (*p) {
		int icons[6]; const char *slash[6]; unsigned parts = 0, total = 0;
		if (menu_word_char((unsigned char)*p) &&
			menu_button_group(p, icons, slash, &parts, &total)) {
			/* SELECT after a button in the same clause is the verb, not the key. */
			int verb = parts == 1u && icons[0] == MENU_GLYPH_SELECT && clause_icon;
			if (!verb) {
				if (menu_piece_add(out, max, count, MENU_PROMPT_TEXT, 0, run, run_len)) return -1;
				if (menu_emit_buttons(out, max, count, icons, slash, parts)) return -1;
				p += total; run = p; run_len = 0; spaces = 0; clause_icon = 1;
				continue;
			}
		}
		if (!run_len) run = p;
		++run_len;
		if (*p == ' ') { ++spaces; if (spaces >= 2u) clause_icon = 0; }
		else spaces = 0;
		++p;
	}
	return menu_piece_add(out, max, count, MENU_PROMPT_TEXT, 0, run, run_len);
}

int hcu_main_menu_describe_prompt(const char *prompt, char *out, size_t out_size)
{
	menu_prompt_piece pieces[48];
	unsigned count = 0, i, used = 0;
	if (!prompt || !out || !out_size) return -1;
	if (menu_prompt_parse(prompt, pieces, 48, &count)) return -1;
	for (i = 0; i < count; ++i) {
		const char *src; unsigned len;
		if (pieces[i].kind == MENU_PROMPT_ICON) {
			if (pieces[i].icon >= MENU_GLYPH_COUNT) return -1;
			src = menu_glyph_tag[pieces[i].icon]; len = (unsigned)strlen(src);
		} else { src = pieces[i].text; len = pieces[i].length; }
		if (used + len >= out_size) return -1;
		memcpy(out + used, src, len); used += len;
	}
	out[used] = '\0';
	return 0;
}

#ifdef _EE

#include <dma.h>
#include <draw.h>
#include <fcntl.h>
#include <gs_psm.h>
#include <kernel.h>
#include <libmc.h>
#include <loadfile.h>
#include <math.h>
#include <packet2.h>
#include <stdio.h>
#include <tamtypes.h>

#include "platform/pad.h"
#include "render/chain.h"
#include "render/gs.h"
#include "render/text.h"
#include "render/upload.h"

#define MENU_PACKET_QW 24576u
#define MENU_RING_W 128u
#define MENU_RING_INNER_H 8u
#define MENU_RING_OUTER_H 64u
#define MENU_RING_INNER_BYTES (MENU_RING_W * MENU_RING_INNER_H * 2u)
#define MENU_RING_OUTER_BYTES (MENU_RING_W * MENU_RING_OUTER_H * 2u)
#define MENU_RING_SHADOW_BYTES (MENU_RING_W * MENU_RING_INNER_H * 2u)
#define MENU_MAP_ATLAS_W 512u
#define MENU_MAP_ATLAS_H 256u
#define MENU_MAP_ATLAS_BYTES (MENU_MAP_ATLAS_W * MENU_MAP_ATLAS_H * 2u)
#define MENU_TYPE_ATLAS_W 256u
#define MENU_TYPE_ATLAS_H 256u
#define MENU_TYPE_ATLAS_BYTES (MENU_TYPE_ATLAS_W * MENU_TYPE_ATLAS_H * 2u)
#define MENU_LOGO_BYTES (512u * 128u * 2u)
#define MENU_BUTTONS_BYTES (256u * 256u * 2u)
#define MENU_PLANET_BYTES (256u * 256u * 2u)
#define MENU_CAMERA_COUNT 11u
#define MENU_CAMERA_RECORD_BYTES 40u
#define MENU_CAMERA_HEADER_BYTES 56u
#define MENU_CAMERA_BYTES (MENU_CAMERA_HEADER_BYTES + MENU_CAMERA_COUNT * MENU_CAMERA_RECORD_BYTES)
#define MENU_RING_MESH_PARTS 3u

typedef struct {
	const uint8_t *triangles;
	uint32_t triangle_count;
	uint32_t material;
} menu_ring_mesh_part;

static menu_ring_mesh_part s_menu_ring_mesh_parts[MENU_RING_MESH_PARTS];
static uint8_t *s_menu_ring_mesh_owner;
static const uint8_t *s_menu_ring_mesh_data;

static void menu_ring_mesh_clear(void)
{
	free(s_menu_ring_mesh_owner);
	s_menu_ring_mesh_owner = NULL;
	s_menu_ring_mesh_data = NULL;
	memset(s_menu_ring_mesh_parts, 0, sizeof(s_menu_ring_mesh_parts));
}

static int menu_ring_mesh_import(const uint8_t *blob, size_t bytes, int copy)
{
	uint32_t count, i;
	size_t offset = 8u;
	const uint8_t *data = blob;
	uint8_t *owned = NULL;
	if (!blob || bytes < 8u || memcmp(blob, "HMR1", 4)) return -1;
	memcpy(&count, blob + 4, sizeof(count));
	if (count != MENU_RING_MESH_PARTS) return -1;
	for (i = 0; i < count; ++i) {
		uint32_t kind, triangles;
		if (offset + 8u > bytes) return -1;
		memcpy(&kind, blob + offset, 4); memcpy(&triangles, blob + offset + 4u, 4);
		if (kind >= MENU_RING_MESH_PARTS || triangles > 3000u ||
			offset + 8u + (size_t)triangles * 60u > bytes) return -1;
		offset += 8u + (size_t)triangles * 60u;
	}
	if (offset != bytes) return -1;
	if (copy) {
		owned = (uint8_t *)malloc(bytes);
		if (!owned) return -1;
		memcpy(owned, blob, bytes);
		data = owned;
	}
	menu_ring_mesh_clear();
	s_menu_ring_mesh_owner = owned;
	s_menu_ring_mesh_data = data;
	offset = 8u;
	for (i = 0; i < count; ++i) {
		uint32_t kind, triangles;
		memcpy(&kind, data + offset, 4); memcpy(&triangles, data + offset + 4u, 4);
		s_menu_ring_mesh_parts[kind].material = kind;
		s_menu_ring_mesh_parts[kind].triangle_count = triangles;
		s_menu_ring_mesh_parts[kind].triangles = data + offset + 8u;
		offset += 8u + (size_t)triangles * 60u;
	}
	return 0;
}
#define MENU_FONT_BYTES (TEXT_ATLAS_W * TEXT_ATLAS_H)
#define MENU_CLUT_BYTES (256u * sizeof(uint32_t))
#define MENU_PAGE_WORDS 2048u
#define MENU_RING_INNER_PAGE 0u
#define MENU_MAP_PAGE 4u
#define MENU_TYPE_PAGE 36u
#define MENU_FONT_PAGE 52u
#define MENU_CLUT_PAGE 53u
#define MENU_RING_OUTER_PAGE 54u
#define MENU_LOGO_PAGE 58u
#define MENU_BUTTONS_PAGE 74u
#define MENU_PLANET_PAGE 90u
/* Planet fills pages 90..105. This atlas is 256x16 PSMCT16: four pages wide
 * and one page tall, so it occupies 106..109. video_init leaves 288 pages
 * after the frame and Z buffers; 110 pages fits in that window. */
#define MENU_GLYPH_PAGE 106u
#define MENU_GLYPH_PAGES 4u
#define MENU_SPACE_PAGE 110u
#define MENU_STARS_PAGE 114u
#define MENU_RING_SHADOW_PAGE 118u

static float s_menu_camera_points[MENU_CAMERA_COUNT][10];
static float s_menu_ring_position[3];
static float s_menu_ring_basis[9];
static int s_menu_camera_ready;
static struct {
	int started;
	unsigned last_frame;
	float time;
	float position[3], velocity[3], acceleration[3];
	float forward[3], up[3], spin_velocity[3], spin_acceleration[3];
	float fov;
} s_menu_camera;

static void menu_camera_import(const uint8_t *blob, size_t bytes)
{
	uint32_t count;
	if (!blob || bytes < MENU_CAMERA_HEADER_BYTES || memcmp(blob, "HCM3", 4)) return;
	memcpy(&count, blob + 4, sizeof(count));
	if (count != MENU_CAMERA_COUNT || bytes < MENU_CAMERA_BYTES) return;
	memcpy(s_menu_ring_position, blob + 8, sizeof(s_menu_ring_position));
	memcpy(s_menu_ring_basis, blob + 20, sizeof(s_menu_ring_basis));
	memcpy(s_menu_camera_points, blob + MENU_CAMERA_HEADER_BYTES, sizeof(s_menu_camera_points));
	memset(&s_menu_camera, 0, sizeof(s_menu_camera));
	s_menu_camera_ready = 1;
}

/* Halo's observer glides toward each target over 400 ticks; ring_loop
 * retargets it every 200 ticks, so the camera keeps moving through the path. */
static float menu_camera_glide(float displacement, float *velocity,
	float *acceleration, float remaining, float dt)
{
	float i1, i2, i3, i4, i5, v, a, b, c, r, r2, delta;
	if (remaining <= dt || remaining <= 0.0f) {
		*velocity = *acceleration = 0.0f;
		return displacement;
	}
	i1 = 1.0f / remaining; i2 = i1 * i1; i3 = i2 * i1;
	i4 = i3 * i1; i5 = i4 * i1;
	v = -*velocity;
	a = *acceleration * i3 * 0.5f - (v * i4 * 3.0f + displacement * i5 * 6.0f);
	b = v * i3 * 7.0f + displacement * i4 * 15.0f - *acceleration * i2;
	c = *acceleration * i1 * 0.5f - (v * i2 * 4.0f + displacement * i3 * 10.0f);
	r = remaining - dt; r2 = r * r;
	delta = a * r2 * r2 * r + b * r2 * r2 + c * r2 * r + displacement;
	*velocity = -(5.0f * a * r2 * r2 + 4.0f * b * r2 * r + 3.0f * c * r2);
	*acceleration = 20.0f * a * r2 * r + 12.0f * b * r2 + 6.0f * c * r;
	return delta;
}

static void menu_camera_cross(const float *a, const float *b, float *out)
{
	out[0] = a[1] * b[2] - a[2] * b[1];
	out[1] = a[2] * b[0] - a[0] * b[2];
	out[2] = a[0] * b[1] - a[1] * b[0];
}

static void menu_camera_normalize(float *v)
{
	float length = sqrtf(v[0] * v[0] + v[1] * v[1] + v[2] * v[2]);
	if (length > 1e-6f) { v[0] /= length; v[1] /= length; v[2] /= length; }
}

static void menu_camera_rotate(float *v, const float *axis, float angle)
{
	float cross[3], s = sinf(angle), c = cosf(angle);
	float dot = axis[0] * v[0] + axis[1] * v[1] + axis[2] * v[2];
	menu_camera_cross(axis, v, cross);
	for (unsigned i = 0; i < 3u; ++i)
		v[i] = v[i] * c + cross[i] * s + axis[i] * dot * (1.0f - c);
}

static void menu_camera_rotation_to(const float *forward, const float *up,
	const float *point, float *out)
{
	float left[3], target_left[3], m[3][3], angle, s;
	const float *target_forward = point + 3, *target_up = point + 6;
	menu_camera_cross(up, forward, left);
	menu_camera_cross(target_up, target_forward, target_left);
	for (int i = 0; i < 3; ++i) for (int j = 0; j < 3; ++j)
		m[i][j] = target_forward[i] * forward[j] + target_left[i] * left[j] + target_up[i] * up[j];
	angle = acosf(fmaxf(-1.0f, fminf(1.0f,
		(m[0][0] + m[1][1] + m[2][2] - 1.0f) * 0.5f)));
	s = sinf(angle);
	if (angle < 1e-4f || s < 1e-4f) { out[0] = out[1] = out[2] = 0.0f; return; }
	out[0] = (m[2][1] - m[1][2]) / (2.0f * s) * angle;
	out[1] = (m[0][2] - m[2][0]) / (2.0f * s) * angle;
	out[2] = (m[1][0] - m[0][1]) / (2.0f * s) * angle;
}

static void menu_camera_update(unsigned frame)
{
	const float interval = 200.0f / 30.0f, transition = 400.0f / 30.0f;
	const float *point;
	float dt, since, remaining, turn[3], step[3], angle;
	int command;
	if (!s_menu_camera_ready) return;
	if (!s_menu_camera.started) {
		point = s_menu_camera_points[0];
		memcpy(s_menu_camera.position, point, 3u * sizeof(float));
		memcpy(s_menu_camera.forward, point + 3, 3u * sizeof(float));
		memcpy(s_menu_camera.up, point + 6, 3u * sizeof(float));
		s_menu_camera.fov = point[9];
		s_menu_camera.last_frame = frame;
		s_menu_camera.started = 1;
		return;
	}
	dt = (float)(frame - s_menu_camera.last_frame) / 60.0f;
	s_menu_camera.last_frame = frame;
	if (dt <= 0.0f) return;
	if (dt > 0.1f) dt = 0.1f;
	s_menu_camera.time += dt;
	/* Point zero seeds the camera pose. Point one is the first destination,
	 * so begin the glide immediately instead of spending one full keyframe
	 * interval (6.67 s) targeting the starting pose again. */
	command = (int)(s_menu_camera.time / interval) + 1;
	since = s_menu_camera.time - (float)command * interval;
	remaining = transition - since;
	point = s_menu_camera_points[(unsigned)command % MENU_CAMERA_COUNT];
	for (unsigned k = 0; k < 3u; ++k)
		s_menu_camera.position[k] += menu_camera_glide(point[k] - s_menu_camera.position[k],
			&s_menu_camera.velocity[k], &s_menu_camera.acceleration[k], remaining, dt);
	menu_camera_rotation_to(s_menu_camera.forward, s_menu_camera.up, point, turn);
	for (unsigned k = 0; k < 3u; ++k)
		step[k] = menu_camera_glide(turn[k], &s_menu_camera.spin_velocity[k],
			&s_menu_camera.spin_acceleration[k], remaining, dt);
	angle = sqrtf(step[0] * step[0] + step[1] * step[1] + step[2] * step[2]);
	if (angle > 1e-6f) {
		float axis[3] = {step[0] / angle, step[1] / angle, step[2] / angle}, left[3];
		menu_camera_rotate(s_menu_camera.forward, axis, angle);
		menu_camera_rotate(s_menu_camera.up, axis, angle);
		menu_camera_normalize(s_menu_camera.forward);
		menu_camera_cross(s_menu_camera.up, s_menu_camera.forward, left);
		menu_camera_cross(s_menu_camera.forward, left, s_menu_camera.up);
		menu_camera_normalize(s_menu_camera.up);
	}
	if (point[9] > 0.1f) s_menu_camera.fov = point[9];
}
#define MENU_GLYPH_W HCU_MAIN_MENU_GLYPH_ATLAS_W
#define MENU_GLYPH_H HCU_MAIN_MENU_GLYPH_ATLAS_H
#define MENU_GLYPH_SRC HCU_MAIN_MENU_GLYPH_CELL
#define MENU_GLYPH_BYTES (MENU_GLYPH_W * MENU_GLYPH_H * 2u)
#define MENU_SPACE_BYTES (128u * 128u * 2u)
_Static_assert(MENU_GLYPH_W == 256u && MENU_GLYPH_H == 16u, "glyph atlas page fit");
_Static_assert(MENU_GLYPH_PAGE == MENU_PLANET_PAGE + 16u, "glyph page follows the planet");
_Static_assert(MENU_SPACE_PAGE == MENU_GLYPH_PAGE + MENU_GLYPH_PAGES, "space page follows glyph atlas");
#define MENU_PAD_UP 0x0010u
#define MENU_PAD_RIGHT 0x0020u
#define MENU_PAD_DOWN 0x0040u
#define MENU_PAD_LEFT 0x0080u
#define MENU_DEAD_LOW 72u
#define MENU_DEAD_HIGH 184u

typedef struct menu_pad_event {
	pad_sample sample;
	unsigned edges;
} menu_pad_event;

typedef struct menu_input {
	unsigned previous[4];
	unsigned repeat_direction;
	unsigned repeat_frames;
} menu_input;

static hcu_main_menu_profile s_kept_profiles[HCU_MAIN_MENU_PROFILE_COUNT];
static hcu_main_menu_variant s_kept_variants[HCU_MAIN_MENU_PROFILE_COUNT]
	[HCU_MAIN_MENU_SAVED_VARIANT_COUNT];
static unsigned s_kept_ready;
static hcu_main_menu_session s_selected_session;
static int s_menu_widescreen = 1;

const hcu_main_menu_session *hcu_main_menu_selected_session(void)
{
	return &s_selected_session;
}

#define MENU_PROFILE_MAGIC 0x32525048u /* HPR2 */
#define MENU_SYSTEM_MAGIC 0x32535948u /* HYS2 */
#define MENU_SAVE_VERSION 2u
#define MENU_PROFILE_VERSION 3u

typedef struct menu_profile_record {
	uint32_t magic;
	uint32_t version;
	uint32_t checksum;
	uint32_t profile_slot;
	hcu_main_menu_profile profile;
	hcu_main_menu_variant variants[HCU_MAIN_MENU_SAVED_VARIANT_COUNT];
	uint8_t reserved[32];
} menu_profile_record;

typedef struct menu_profile_legacy_record {
	uint32_t magic, version, checksum, profile_slot;
	hcu_main_menu_profile profile;
	hcu_main_menu_variant variants[4];
	uint8_t reserved[32];
} menu_profile_legacy_record;

typedef struct menu_system_record {
	uint32_t magic;
	uint32_t version;
	uint32_t checksum;
	uint8_t settings[9];
	uint8_t reserved[43];
} menu_system_record;

static menu_profile_record s_menu_profile_save __attribute__((aligned(64)));
static menu_system_record s_menu_system_save __attribute__((aligned(64)));
static int s_menu_mc_ready;
static int s_menu_mc_checked;

static uint32_t menu_save_checksum(const void *record, size_t size)
{
	const uint8_t *bytes = (const uint8_t *)record;
	uint32_t hash = 2166136261u; unsigned i;
	for (i = 0; i < size; ++i) {
		uint8_t value = i >= 8u && i < 12u ? 0 : bytes[i];
		hash ^= value; hash *= 16777619u;
	}
	return hash;
}

static int menu_mc_sync_result(int request)
{
	int result = -1;
	if (request < 0 || mcSync(MC_WAIT, NULL, &result) < 0) return -1;
	return result;
}

static int menu_storage_ready(void)
{
	int type = 0, free_clusters = 0, formatted = 0, result;
	if (s_menu_mc_checked) return s_menu_mc_ready;
	s_menu_mc_checked = 1;
	/* XSIO2MAN is already owned by the pad service.  The memory-card pair is
	 * additive and failure is non-fatal (the menu still keeps session data). */
	(void)SifLoadModule("rom0:XMCMAN", 0, NULL);
	(void)SifLoadModule("rom0:XMCSERV", 0, NULL);
	if (mcInit(MC_TYPE_XMC) < 0) return 0;
	result = menu_mc_sync_result(mcGetInfo(0, 0, &type, &free_clusters, &formatted));
	if (result < -1 || type != MC_TYPE_PS2) return 0;
	s_menu_mc_ready = 1;
	printf("HALO_PS2_LOCAL main-menu-memory-card-ready free=%d formatted=%d\n",
		free_clusters, formatted);
	return 1;
}

static void menu_sanitize_variant(hcu_main_menu_variant *v)
{
	if (!v->valid || v->game_type >= HCU_MAIN_MENU_GAME_TYPE_COUNT) {
		memset(v, 0, sizeof(*v)); return;
	}
	v->score_index %= v->game_type == HCU_GAME_RACE ? 6 : 5;
	v->teams = v->teams != 0; v->ctf_assault = v->ctf_assault != 0;
	v->ctf_single_flag %= 6; v->ctf_flag_must_reset = v->ctf_flag_must_reset != 0;
	v->ctf_flag_at_home = v->ctf_flag_at_home != 0; v->king_moving_hill = v->king_moving_hill != 0;
	v->slayer_death_bonus = v->slayer_death_bonus != 0; v->slayer_kill_in_order = v->slayer_kill_in_order != 0;
	v->slayer_kill_penalty = v->slayer_kill_penalty != 0;
	v->oddball_trait_with_ball %= 4; v->oddball_trait_without_ball %= 4;
	v->oddball_speed_with_ball %= 3; v->oddball_ball_type %= 3;
	v->oddball_random_start = v->oddball_random_start != 0; v->oddball_ball_count %= 16;
	v->race_team_scoring %= 3; v->race_type %= 3; v->lives %= 4;
	v->maximum_health %= 6; v->shields = v->shields != 0; v->respawn_time %= 4;
	v->respawn_growth %= 4; v->odd_man_out = v->odd_man_out != 0;
	v->invisible_players = v->invisible_players != 0; v->suicide_penalty %= 4;
	v->infinite_grenades = v->infinite_grenades != 0; v->vehicle_set %= 5;
	v->weapon_set %= 11; v->starting_equipment = v->starting_equipment != 0;
	v->radar_display %= 3; v->other_players_radar = v->other_players_radar != 0;
	v->friends_on_screen = v->friends_on_screen != 0;
}

static void menu_sanitize_profile(hcu_main_menu_profile *profile, unsigned index)
{
	profile->name[HCU_MAIN_MENU_PROFILE_NAME_LENGTH] = '\0';
	if (profile->control_layout >= 5) profile->control_layout = 0;
	if (profile->armor_color >= 8) profile->armor_color = (uint8_t)index;
	profile->look_inverted = profile->look_inverted != 0;
	if (profile->look_sensitivity < 1 || profile->look_sensitivity > 10)
		profile->look_sensitivity = 5;
	profile->vibration = profile->vibration != 0;
}

static void menu_profile_path(char *path, size_t size, unsigned profile)
{
	snprintf(path, size, "/HALOPS2/PROFILE%u.DAT", profile + 1u);
}

static int menu_storage_load_profile(hcu_main_menu_state *state, unsigned p)
{
	unsigned v; int fd, read_bytes; char path[32];
	if (p >= HCU_MAIN_MENU_PROFILE_COUNT || !menu_storage_ready()) return 0;
		menu_profile_path(path, sizeof(path), p);
		fd = menu_mc_sync_result(mcOpen(0, 0, path, O_RDONLY));
		if (fd < 0) return 0;
		read_bytes = menu_mc_sync_result(mcRead(fd, &s_menu_profile_save, sizeof(s_menu_profile_save)));
		(void)menu_mc_sync_result(mcClose(fd));
		if (s_menu_profile_save.magic != MENU_PROFILE_MAGIC ||
			s_menu_profile_save.profile_slot != p) return 0;
		if (read_bytes == (int)sizeof(s_menu_profile_save) &&
			s_menu_profile_save.version == MENU_PROFILE_VERSION &&
			s_menu_profile_save.checksum == menu_save_checksum(&s_menu_profile_save, sizeof(s_menu_profile_save))) {
			state->profiles[p] = s_menu_profile_save.profile;
			memcpy(state->saved_variants[p], s_menu_profile_save.variants,
				sizeof(state->saved_variants[p]));
		} else if (read_bytes == (int)sizeof(menu_profile_legacy_record)) {
			const menu_profile_legacy_record *old = (const menu_profile_legacy_record *)&s_menu_profile_save;
			if (old->version != MENU_SAVE_VERSION ||
				old->checksum != menu_save_checksum(old, sizeof(*old))) return 0;
			state->profiles[p] = old->profile;
			memset(state->saved_variants[p], 0, sizeof(state->saved_variants[p]));
			memcpy(state->saved_variants[p], old->variants, sizeof(old->variants));
		} else return 0;
		state->profile_present_mask |= (uint32_t)(1u << p);
		menu_sanitize_profile(&state->profiles[p], p);
		for (v = 0; v < HCU_MAIN_MENU_SAVED_VARIANT_COUNT; ++v)
			menu_sanitize_variant(&state->saved_variants[p][v]);
		printf("HALO_PS2_LOCAL profile-loaded slot=%u bytes=%u\n", p + 1u,
			(unsigned)sizeof(s_menu_profile_save));
		return 1;
}

static void menu_storage_load(hcu_main_menu_state *state)
{
	unsigned p; int fd, read_bytes;
	if (!menu_storage_ready()) return;
	for (p = 0; p < HCU_MAIN_MENU_PROFILE_COUNT; ++p)
		(void)menu_storage_load_profile(state, p);
	fd = menu_mc_sync_result(mcOpen(0, 0, "/HALOPS2/SYSTEM.DAT", O_RDONLY));
	if (fd >= 0) {
		read_bytes = menu_mc_sync_result(mcRead(fd, &s_menu_system_save, sizeof(s_menu_system_save)));
		(void)menu_mc_sync_result(mcClose(fd));
		if (read_bytes == (int)sizeof(s_menu_system_save) &&
			s_menu_system_save.magic == MENU_SYSTEM_MAGIC &&
			s_menu_system_save.version == MENU_SAVE_VERSION &&
			s_menu_system_save.checksum == menu_save_checksum(&s_menu_system_save, sizeof(s_menu_system_save))) {
			state->resolution = s_menu_system_save.settings[0] % 4;
			state->animation_rate = s_menu_system_save.settings[1] != 0;
			state->particles = s_menu_system_save.settings[2] != 0;
			state->view_model = s_menu_system_save.settings[3] % 4;
			state->terrain_detail = s_menu_system_save.settings[4] % 4;
			state->widescreen = s_menu_system_save.settings[5] != 0;
			state->hud_inset = s_menu_system_save.settings[6] % 6;
			state->fps_counter = s_menu_system_save.settings[7] != 0;
			state->subtitles = s_menu_system_save.settings[8] != 0;
		}
	}
}

static void menu_storage_save_profile(const hcu_main_menu_state *state, unsigned p)
{
	int fd, written; char path[32];
	if (!menu_storage_ready() || p >= HCU_MAIN_MENU_PROFILE_COUNT) return;
	memset(&s_menu_profile_save, 0, sizeof(s_menu_profile_save));
	s_menu_profile_save.magic = MENU_PROFILE_MAGIC;
	s_menu_profile_save.version = MENU_PROFILE_VERSION;
	s_menu_profile_save.profile_slot = p;
	s_menu_profile_save.profile = state->profiles[p];
	memcpy(s_menu_profile_save.variants, state->saved_variants[p],
		sizeof(s_menu_profile_save.variants));
	s_menu_profile_save.checksum = menu_save_checksum(&s_menu_profile_save, sizeof(s_menu_profile_save));
	(void)menu_mc_sync_result(mcMkDir(0, 0, "/HALOPS2"));
	menu_profile_path(path, sizeof(path), p);
	fd = menu_mc_sync_result(mcOpen(0, 0, path, O_WRONLY | O_CREAT | O_TRUNC));
	if (fd < 0) { printf("HALO_PS2_FAIL profile-save slot=%u open=%d\n", p + 1u, fd); return; }
	written = menu_mc_sync_result(mcWrite(fd, &s_menu_profile_save, sizeof(s_menu_profile_save)));
	(void)menu_mc_sync_result(mcFlush(fd)); (void)menu_mc_sync_result(mcClose(fd));
	printf("HALO_PS2_LOCAL profile-save slot=%u result=%d bytes=%u\n", p + 1u,
		written == (int)sizeof(s_menu_profile_save), (unsigned)sizeof(s_menu_profile_save));
}

static void menu_storage_save(const hcu_main_menu_state *state)
{
	unsigned p; int fd, written;
	if (!menu_storage_ready()) return;
	for (p = 0; p < HCU_MAIN_MENU_PROFILE_COUNT; ++p)
		if (state->profile_present_mask & (1u << p))
			menu_storage_save_profile(state, p);
	memset(&s_menu_system_save, 0, sizeof(s_menu_system_save));
	s_menu_system_save.magic = MENU_SYSTEM_MAGIC; s_menu_system_save.version = MENU_SAVE_VERSION;
	s_menu_system_save.settings[0] = state->resolution; s_menu_system_save.settings[1] = state->animation_rate;
	s_menu_system_save.settings[2] = state->particles; s_menu_system_save.settings[3] = state->view_model;
	s_menu_system_save.settings[4] = state->terrain_detail; s_menu_system_save.settings[5] = state->widescreen;
	s_menu_system_save.settings[6] = state->hud_inset; s_menu_system_save.settings[7] = state->fps_counter;
	s_menu_system_save.settings[8] = state->subtitles;
	s_menu_system_save.checksum = menu_save_checksum(&s_menu_system_save, sizeof(s_menu_system_save));
	fd = menu_mc_sync_result(mcOpen(0, 0, "/HALOPS2/SYSTEM.DAT", O_WRONLY | O_CREAT | O_TRUNC));
	if (fd < 0) return;
	written = menu_mc_sync_result(mcWrite(fd, &s_menu_system_save, sizeof(s_menu_system_save)));
	(void)menu_mc_sync_result(mcFlush(fd)); (void)menu_mc_sync_result(mcClose(fd));
	printf("HALO_PS2_LOCAL system-save result=%d bytes=%u\n",
		written == (int)sizeof(s_menu_system_save), (unsigned)sizeof(s_menu_system_save));
}

static uint32_t menu_hash(unsigned x, unsigned y)
{
	uint32_t n = x * 0x45d9f3bu + y * 0x119de1f3u + 0x68bc21ebu;
	n ^= n >> 16; n *= 0x7feb352du; n ^= n >> 15;
	return n;
}

static uint64_t menu_rgbaq(unsigned r, unsigned g) { return (uint64_t)r | (uint64_t)g << 32; }
static uint64_t menu_baq(unsigned b, unsigned a) { return (uint64_t)b | (uint64_t)a << 32; }
static uint64_t menu_xy(int x, int y)
{
	return (uint64_t)((2048 - VIDEO_WIDTH / 2 + x) * 16) |
		(uint64_t)((2048 - VIDEO_HEIGHT / 2 + y) * 16) << 32;
}

static void menu_vertex(packet2_t *packet, int x, int y, int u, int v,
	unsigned r, unsigned g, unsigned b, unsigned a)
{
	packet2_add_u64(packet, menu_rgbaq(r, g)); packet2_add_u64(packet, menu_baq(b, a));
	packet2_add_u64(packet, (uint64_t)(u * 16) | (uint64_t)(v * 16) << 32); packet2_add_u64(packet, 0);
	packet2_add_u64(packet, menu_xy(x, y)); packet2_add_u64(packet, 0x00ffffffu);
}

static void menu_vertex_3d(packet2_t *packet, int x, int y, int u16, int v16,
	uint32_t z, unsigned shade, unsigned alpha)
{
	packet2_add_u64(packet, menu_rgbaq(shade, shade)); packet2_add_u64(packet, menu_baq(shade, alpha));
	packet2_add_u64(packet, (uint64_t)(uint32_t)u16 | (uint64_t)(uint32_t)v16 << 32);
	packet2_add_u64(packet, 0);
	packet2_add_u64(packet, menu_xy(x, y)); packet2_add_u64(packet, z & 0x00ffffffu);
}

static void menu_flat_vertex(packet2_t *packet, int x, int y,
	unsigned r, unsigned g, unsigned b, unsigned a)
{
	packet2_add_u64(packet, menu_rgbaq(r, g)); packet2_add_u64(packet, menu_baq(b, a));
	packet2_add_u64(packet, menu_xy(x, y)); packet2_add_u64(packet, 0x00ffffffu);
}

static void menu_flat_rect(packet2_t *packet, int x0, int y0, int x1, int y1,
	unsigned r, unsigned g, unsigned b, unsigned a)
{
	packet2_add_u64(packet, GIF_TAG(2, 0, 1,
		GS_PRIM(GSX_PRIM_SPRITE, 0, 0, 0, a < 0x80u, 0, 1, 0, 0), GIFX_FLG_PACKED, 2));
	packet2_add_u64(packet, 0x51);
	menu_flat_vertex(packet, x0, y0, r, g, b, a); menu_flat_vertex(packet, x1, y1, r, g, b, a);
}

static void menu_frame(packet2_t *packet, int x0, int y0, int x1, int y1)
{
	menu_flat_rect(packet, x0, y0, x1, y0 + 2, 112, 190, 255, 0x78);
	menu_flat_rect(packet, x0, y1 - 2, x1, y1, 112, 190, 255, 0x78);
	menu_flat_rect(packet, x0, y0 + 2, x0 + 2, y1 - 2, 112, 190, 255, 0x78);
	menu_flat_rect(packet, x1 - 2, y0 + 2, x1, y1 - 2, 112, 190, 255, 0x78);
}

static void menu_flat_state(packet2_t *packet, const video_t *video)
{
	packet2_add_u64(packet, GIF_TAG(3, 0, 0, 0, GIFX_FLG_PACKED, 1)); packet2_add_u64(packet, GIF_REGS_AD);
	packet2_add_u64(packet, GS_ALPHA(0, 1, 0, 1, 0)); packet2_add_u64(packet, GS_A_ALPHA_1);
	packet2_add_u64(packet, GS_ZBUF(video->z.address / MENU_PAGE_WORDS, GS_PSMZ24, 1));
	packet2_add_u64(packet, GS_A_ZBUF_1);
	packet2_add_u64(packet, GS_TEST(0, 1, 0, 0, 0, 0, 1, 1)); packet2_add_u64(packet, GS_A_TEST_1);
}

static void menu_texture_state(packet2_t *packet, const video_t *video,
	unsigned page, unsigned psm, unsigned tw, unsigned th, unsigned tbw,
	unsigned clut_page, int nearest)
{
	uint32_t base = video->tex_base + page * MENU_PAGE_WORDS;
	uint32_t clut = video->tex_base + clut_page * MENU_PAGE_WORDS;
	unsigned filter = nearest ? 0u : 1u;
	packet2_add_u64(packet, GIF_TAG(6, 0, 0, 0, GIFX_FLG_PACKED, 1)); packet2_add_u64(packet, GIF_REGS_AD);
	packet2_add_u64(packet, GS_TEX0(base / 64u, tbw, psm, tw, th, 1, 0,
		clut / 64u, GS_PSMCT32, 0, 0, 1)); packet2_add_u64(packet, GS_A_TEX0_1);
	packet2_add_u64(packet, GS_TEX1(1, 0, filter, filter, 0, 0, 0)); packet2_add_u64(packet, GS_A_TEX1_1);
	packet2_add_u64(packet, GS_CLAMP(0, 0, 0, 0, 0, 0)); packet2_add_u64(packet, GS_A_CLAMP_1);
	packet2_add_u64(packet, GS_ALPHA(0, 1, 0, 1, 0)); packet2_add_u64(packet, GS_A_ALPHA_1);
	packet2_add_u64(packet, GS_TEST(0, 1, 0, 0, 0, 0, 1, 1)); packet2_add_u64(packet, GS_A_TEST_1);
	packet2_add_u64(packet, 0); packet2_add_u64(packet, GS_A_TEXFLUSH);
}

static void menu_image_draw(packet2_t *packet, const video_t *video, unsigned page,
	unsigned tw, unsigned th, unsigned tbw, int x0, int y0, int x1, int y1,
	int u0, int v0, int u1, int v1, int cutout)
{
	menu_texture_state(packet, video, page, GS_PSMCT16S, tw, th, tbw, 0, 0);
	if (cutout) {
		/* A cleared RGB5A1 bit is the empty plate around the title art. */
		packet2_add_u64(packet, GIF_TAG(2, 0, 0, 0, GIFX_FLG_PACKED, 1));
		packet2_add_u64(packet, GIF_REGS_AD);
		packet2_add_u64(packet, 0x80ull << 32); packet2_add_u64(packet, GS_A_TEXA);
		packet2_add_u64(packet, GS_TEST(1, 6, 0, 0, 0, 0, 1, 1)); packet2_add_u64(packet, GS_A_TEST_1);
	}
	packet2_add_u64(packet, GIF_TAG(2, 0, 1,
		GS_PRIM(GSX_PRIM_SPRITE, 0, 1, 0, 1, 0, 1, 0, 0), GIFX_FLG_PACKED, 3));
	packet2_add_u64(packet, 0x531);
	menu_vertex(packet, x0, y0, u0, v0, 128, 128, 128, 0x80);
	menu_vertex(packet, x1, y1, u1, v1, 128, 128, 128, 0x80);
}

static void menu_image(packet2_t *packet, const video_t *video, unsigned page,
	unsigned tw, unsigned th, unsigned tbw, int x0, int y0, int x1, int y1,
	int u0, int v0, int u1, int v1)
{
	menu_image_draw(packet, video, page, tw, th, tbw, x0, y0, x1, y1, u0, v0, u1, v1, 0);
}

typedef struct { float x, y, z, u, v; } menu_ring_vertex;

static menu_ring_vertex menu_ring_to_camera(const float *local, const float *uv)
{
	menu_ring_vertex out;
	float world[3], delta[3], right[3];
	for (unsigned k = 0; k < 3u; ++k)
		world[k] = s_menu_ring_position[k] + s_menu_ring_basis[k] * local[0] +
			s_menu_ring_basis[3u + k] * local[1] + s_menu_ring_basis[6u + k] * local[2];
	for (unsigned k = 0; k < 3u; ++k) delta[k] = world[k] - s_menu_camera.position[k];
	menu_camera_cross(s_menu_camera.forward, s_menu_camera.up, right);
	out.x = delta[0] * right[0] + delta[1] * right[1] + delta[2] * right[2];
	out.y = delta[0] * s_menu_camera.up[0] + delta[1] * s_menu_camera.up[1] + delta[2] * s_menu_camera.up[2];
	out.z = delta[0] * s_menu_camera.forward[0] + delta[1] * s_menu_camera.forward[1] + delta[2] * s_menu_camera.forward[2];
	out.u = uv[0]; out.v = uv[1];
	return out;
}

#define MENU_RING_CLIP_VERTICES 12u

static float menu_ring_clip_distance(menu_ring_vertex v, unsigned plane,
	float horizontal, float vertical)
{
	switch (plane) {
	case 0: return v.z - 0.05f;
	case 1: return v.x + v.z * horizontal;
	case 2: return v.z * horizontal - v.x;
	case 3: return v.y + v.z * vertical;
	case 4: return v.z * vertical - v.y;
	default: return 96.0f - v.z;
	}
}

static unsigned menu_ring_clip(const menu_ring_vertex input[3],
	menu_ring_vertex output[MENU_RING_CLIP_VERTICES])
{
	menu_ring_vertex a[MENU_RING_CLIP_VERTICES], b[MENU_RING_CLIP_VERTICES];
	menu_ring_vertex *source = a, *destination = b, *swap;
	float fov = s_menu_camera.fov > 0.1f ? s_menu_camera.fov : 1.22173f;
	float horizontal = tanf(fov * 0.5f);
	float vertical = horizontal * (float)VIDEO_HEIGHT / (float)VIDEO_WIDTH;
	/* The GS output is anamorphically stretched to 16:9. Widen only the
	 * horizontal world frustum; keep the vertical field of view unchanged. */
	if (s_menu_widescreen) horizontal *= (4.0f / 3.0f);
	unsigned count = 3u;
	memcpy(a, input, 3u * sizeof(*input));
	/* Clip against the complete view frustum before perspective division. Near-
	 * plane-only clipping projected vertices to enormous coordinates, then the
	 * GS coordinate clamp turned crossing triangles into full-screen wedges. */
	for (unsigned plane = 0; plane < 6u && count; ++plane) {
		unsigned written = 0;
		menu_ring_vertex previous = source[count - 1u];
		float previous_distance = menu_ring_clip_distance(previous, plane,
			horizontal, vertical);
		int previous_inside = previous_distance >= 0.0f;
		for (unsigned i = 0; i < count; ++i) {
			menu_ring_vertex current = source[i];
			float current_distance = menu_ring_clip_distance(current, plane,
				horizontal, vertical);
			int current_inside = current_distance >= 0.0f;
			if (previous_inside != current_inside && written < MENU_RING_CLIP_VERTICES) {
				float t = previous_distance / (previous_distance - current_distance);
				destination[written++] = (menu_ring_vertex){
					previous.x + (current.x - previous.x) * t,
					previous.y + (current.y - previous.y) * t,
					previous.z + (current.z - previous.z) * t,
					previous.u + (current.u - previous.u) * t,
					previous.v + (current.v - previous.v) * t};
			}
			if (current_inside && written < MENU_RING_CLIP_VERTICES)
				destination[written++] = current;
			previous = current;
			previous_distance = current_distance;
			previous_inside = current_inside;
		}
		count = written;
		swap = source; source = destination; destination = swap;
	}
	if (count) memcpy(output, source, count * sizeof(*output));
	return count;
}

static void menu_ring_emit_vertex(packet2_t *packet, const video_t *video,
	menu_ring_vertex v, unsigned material)
{
	float fov = s_menu_camera.fov > 0.1f ? s_menu_camera.fov : 1.22173f;
	float focal_x = (float)VIDEO_WIDTH * 0.5f / tanf(fov * 0.5f);
	float focal_y = (float)VIDEO_HEIGHT * 0.5f /
		(tanf(fov * 0.5f) * (float)VIDEO_HEIGHT / (float)VIDEO_WIDTH);
	if (s_menu_widescreen) focal_x *= (3.0f / 4.0f);
	unsigned tw = MENU_RING_W;
	unsigned th = material == 1u ? MENU_RING_OUTER_H : MENU_RING_INNER_H;
	float u = fmodf(v.u * (float)tw, (float)tw), vv = fmodf(v.v * (float)th, (float)th);
	int x = (int)((float)VIDEO_WIDTH * 0.5f + v.x * focal_x / v.z);
	int y = (int)((float)VIDEO_HEIGHT * 0.5f - v.y * focal_y / v.z);
	uint32_t z = (uint32_t)(0x00ffffffu * (0.02f / v.z));
	if (u < 0.0f) u += (float)tw;
	if (vv < 0.0f) vv += (float)th;
	if (x < -2048) x = -2048; if (x > 2047) x = 2047;
	if (y < -2048) y = -2048; if (y > 2047) y = 2047;
	menu_vertex_3d(packet, x, y, (int)(u * 16.0f), (int)(vv * 16.0f), z,
		material == 1u ? 216u : 240u, material == 2u ? 0x70u : 0x80u);
	(void)video;
}

static void menu_depth_state(packet2_t *packet, const video_t *video,
	unsigned zmask, unsigned ztest)
{
	packet2_add_u64(packet, GIF_TAG(2, 0, 0, 0, GIFX_FLG_PACKED, 1));
	packet2_add_u64(packet, GIF_REGS_AD);
	packet2_add_u64(packet, GS_ZBUF(video->z.address / MENU_PAGE_WORDS, GS_PSMZ24, zmask));
	packet2_add_u64(packet, GS_A_ZBUF_1);
	packet2_add_u64(packet, GS_TEST(0, 1, 0, 0, 0, 0, 1, ztest));
	packet2_add_u64(packet, GS_A_TEST_1);
}

static unsigned menu_ring_triangle_polygon(const menu_ring_mesh_part *part,
	unsigned tri, menu_ring_vertex polygon[MENU_RING_CLIP_VERTICES])
{
	menu_ring_vertex source[3];
	for (unsigned j = 0; j < 3u; ++j) {
		float local[3], uv[2];
		const uint8_t *raw = part->triangles + ((size_t)tri * 3u + j) * 20u;
		memcpy(local, raw, sizeof(local)); memcpy(uv, raw + 12u, sizeof(uv));
		source[j] = menu_ring_to_camera(local, uv);
	}
	return menu_ring_clip(source, polygon);
}

static void menu_ring_draw_part(packet2_t *packet, const video_t *video,
	const menu_ring_mesh_part *part)
{
	menu_ring_vertex polygon[MENU_RING_CLIP_VERTICES];
	unsigned tri, vertex_count = 0;
	if (!part->triangles || !part->triangle_count) return;
	for (tri = 0; tri < part->triangle_count; ++tri) {
		unsigned n = menu_ring_triangle_polygon(part, tri, polygon);
		if (n >= 3u) vertex_count += (n - 2u) * 3u;
	}
	if (!vertex_count) return;
	menu_texture_state(packet, video,
		part->material == 1u ? MENU_RING_OUTER_PAGE :
			(part->material == 2u ? MENU_RING_SHADOW_PAGE : MENU_RING_INNER_PAGE),
		GS_PSMCT16S, 7, part->material == 1u ? 6u : 3u, MENU_RING_W / 64u, 0, 0);
	menu_depth_state(packet, video, part->material == 2u, 2u);
	packet2_add_u64(packet, GIF_TAG(vertex_count, 0, 1,
		GS_PRIM(GSX_PRIM_TRIANGLE, 1, 1, 0, part->material == 2u, 0, 1, 0, 0),
		GIFX_FLG_PACKED, 3));
	packet2_add_u64(packet, 0x531);
	for (tri = 0; tri < part->triangle_count; ++tri) {
		unsigned n = menu_ring_triangle_polygon(part, tri, polygon);
		for (unsigned j = 1; j + 1 < n; ++j) {
			menu_ring_emit_vertex(packet, video, polygon[0], part->material);
			menu_ring_emit_vertex(packet, video, polygon[j], part->material);
			menu_ring_emit_vertex(packet, video, polygon[j + 1u], part->material);
		}
	}
}

static void menu_ring(packet2_t *packet, const video_t *video, unsigned frame)
{
	(void)frame;
	if (!s_menu_camera_ready || !s_menu_ring_mesh_data || !s_menu_camera.started) return;
	menu_ring_draw_part(packet, video, &s_menu_ring_mesh_parts[1]);
	menu_ring_draw_part(packet, video, &s_menu_ring_mesh_parts[0]);
	menu_ring_draw_part(packet, video, &s_menu_ring_mesh_parts[2]);
	menu_depth_state(packet, video, 1u, 1u);
}

static void menu_planet(packet2_t *packet, const video_t *video, unsigned frame)
{
	float phase = (float)frame / 60.0f, dx, dy;
	int x, y;
	menu_camera_update(frame);
	if (s_menu_camera_ready) {
		dx = s_menu_camera.position[0]; dy = s_menu_camera.position[2];
	} else { dx = -0.35f * sinf(phase * 0.11f); dy = 0.36f * cosf(phase * 0.088f); }
	x = -35 + (int)(dx * 35.0f); y = 194 + (int)(dy * 22.0f);
	menu_image_draw(packet, video, MENU_PLANET_PAGE, 8, 8, 4,
		x, y, x + 238, y + 238, 0, 0, 255, 255, 1);
}

static unsigned menu_text_width(const char *text, unsigned scale)
{
	return (unsigned)strlen(text) * TEXT_CELL_W * scale;
}

static void menu_text_span(packet2_t *packet, const video_t *video, int x, int y,
	unsigned scale, unsigned r, unsigned g, unsigned b, unsigned a,
	const char *text, unsigned length)
{
	unsigned count = 0, i;
	if (!text || !length) return;
	for (i = 0; i < length; ++i) if (text[i] != ' ') ++count;
	if (!count) return;
	menu_texture_state(packet, video, MENU_FONT_PAGE, GS_PSMT8, 7, 6,
		TEXT_ATLAS_W / 64u, MENU_CLUT_PAGE, 0);
	packet2_add_u64(packet, GIF_TAG(count * 2u, 0, 1,
		GS_PRIM(GSX_PRIM_SPRITE, 0, 1, 0, 1, 0, 1, 0, 0), GIFX_FLG_PACKED, 3));
	packet2_add_u64(packet, 0x531);
	for (i = 0; i < length; ++i) {
		unsigned ch = (unsigned char)text[i], cell, u, v;
		if (ch >= 'a' && ch <= 'z') ch -= 32;
		if (ch == ' ') continue;
		if (ch < 32u || ch >= 128u) ch = '?';
		cell = ch - 32u; u = (cell % 16u) * 8u; v = (cell / 16u) * 8u;
		menu_vertex(packet, x + (int)(i * TEXT_CELL_W * scale), y, (int)u, (int)v, r, g, b, a);
		menu_vertex(packet, x + (int)((i * TEXT_CELL_W + TEXT_CELL_W) * scale),
			y + (int)(TEXT_CELL_H * scale), (int)(u + TEXT_CELL_W),
			(int)(v + TEXT_CELL_H), r, g, b, a);
	}
}

static void menu_text(packet2_t *packet, const video_t *video, int x, int y,
	unsigned scale, unsigned r, unsigned g, unsigned b, unsigned a, const char *text)
{
	menu_text_span(packet, video, x, y, scale, r, g, b, a, text, (unsigned)strlen(text));
}

static void menu_glyph(packet2_t *packet, const video_t *video, int x, int y,
	unsigned size, unsigned icon)
{
	int u;
	if (icon >= (unsigned)MENU_GLYPH_COUNT) return;
	u = (int)icon * (int)MENU_GLYPH_SRC;
	/* Nearest keeps the 1px transparent gutter from blending into the next cell.
	 * RGB5A1 stores transparency as a cleared alpha bit. TEXA must map that bit
	 * to alpha 0, and the test must discard it, or the GS paints a black square. */
	menu_texture_state(packet, video, MENU_GLYPH_PAGE, GS_PSMCT16S, 8, 4,
		MENU_GLYPH_W / 64u, 0, 1);
	packet2_add_u64(packet, GIF_TAG(2, 0, 0, 0, GIFX_FLG_PACKED, 1));
	packet2_add_u64(packet, GIF_REGS_AD);
	packet2_add_u64(packet, 0x80ull << 32); packet2_add_u64(packet, GS_A_TEXA);
	packet2_add_u64(packet, GS_TEST(1, 6, 0, 0, 0, 0, 1, 1)); packet2_add_u64(packet, GS_A_TEST_1);
	packet2_add_u64(packet, GIF_TAG(2, 0, 1,
		GS_PRIM(GSX_PRIM_SPRITE, 0, 1, 0, 1, 0, 1, 0, 0), GIFX_FLG_PACKED, 3));
	packet2_add_u64(packet, 0x531);
	menu_vertex(packet, x, y, u, 0, 128, 128, 128, 0x80);
	menu_vertex(packet, x + (int)size, y + (int)size,
		u + (int)MENU_GLYPH_SRC - 1, (int)MENU_GLYPH_SRC - 1, 128, 128, 128, 0x80);
}

static unsigned menu_prompt_width(const menu_prompt_piece *pieces, unsigned count,
	unsigned scale)
{
	unsigned i, width = 0;
	for (i = 0; i < count; ++i) {
		width += pieces[i].kind == MENU_PROMPT_ICON ? MENU_GLYPH_SRC * scale :
			pieces[i].length * TEXT_CELL_W * scale;
	}
	return width;
}

static void menu_prompt_pieces(packet2_t *packet, const video_t *video, int x, int y,
	unsigned scale, unsigned r, unsigned g, unsigned b, unsigned a,
	const menu_prompt_piece *pieces, unsigned count)
{
	unsigned i; int cursor = x;
	int icon_y = y + ((int)(TEXT_CELL_H * scale) - (int)(MENU_GLYPH_SRC * scale)) / 2;
	for (i = 0; i < count; ++i) {
		unsigned advance;
		if (pieces[i].kind == MENU_PROMPT_ICON) {
			menu_glyph(packet, video, cursor, icon_y, MENU_GLYPH_SRC * scale, pieces[i].icon);
			advance = MENU_GLYPH_SRC * scale;
		} else {
			menu_text_span(packet, video, cursor, y, scale, r, g, b, a,
				pieces[i].text, pieces[i].length);
			advance = pieces[i].length * TEXT_CELL_W * scale;
		}
		cursor += (int)advance;
	}
}

static void menu_prompt(packet2_t *packet, const video_t *video, int x, int y,
	unsigned scale, unsigned r, unsigned g, unsigned b, unsigned a, const char *text)
{
	menu_prompt_piece pieces[48]; unsigned count = 0;
	if (!text || menu_prompt_parse(text, pieces, 48, &count)) {
		menu_text(packet, video, x, y, scale, r, g, b, a, text ? text : "");
		return;
	}
	menu_prompt_pieces(packet, video, x, y, scale, r, g, b, a, pieces, count);
}

static void menu_text_center(packet2_t *packet, const video_t *video, int y,
	unsigned scale, unsigned r, unsigned g, unsigned b, unsigned a, const char *text)
{
	menu_text(packet, video, (VIDEO_WIDTH - (int)menu_text_width(text, scale)) / 2,
		y, scale, r, g, b, a, text);
}

static void menu_prompt_center(packet2_t *packet, const video_t *video, int y,
	unsigned scale, unsigned r, unsigned g, unsigned b, unsigned a, const char *text)
{
	menu_prompt_piece pieces[48]; unsigned count = 0, width;
	if (!text || menu_prompt_parse(text, pieces, 48, &count)) {
		menu_text_center(packet, video, y, scale, r, g, b, a, text ? text : "");
		return;
	}
	width = menu_prompt_width(pieces, count, scale);
	menu_prompt_pieces(packet, video, (VIDEO_WIDTH - (int)width) / 2, y,
		scale, r, g, b, a, pieces, count);
}

static void menu_space_background(packet2_t *packet, const video_t *video,
	unsigned frame)
{
	int drift = (int)(frame / 24u) % 128;
	/* Use CE's nebula and actual star bitmap as the two sky layers. */
	menu_image(packet, video, MENU_SPACE_PAGE, 7, 7, 2,
		0, 0, VIDEO_WIDTH, VIDEO_HEIGHT, 0, 0, 255, 255);
	menu_image_draw(packet, video, MENU_STARS_PAGE, 7, 7, 2,
		0, 0, VIDEO_WIDTH, VIDEO_HEIGHT, drift, 0, 255 + drift, 255, 1);
}

static void menu_page(packet2_t *packet, const video_t *video, const char *title, const char *footer)
{
	menu_flat_rect(packet, 14, 18, 498, 430, 0, 7, 22, 0x64); menu_frame(packet, 14, 18, 498, 430);
	menu_text(packet, video, 34, 34, 3, 225, 236, 248, 0x80, title);
	menu_flat_rect(packet, 32, 66, 480, 68, 84, 145, 220, 0x68);
	if (footer) menu_prompt_center(packet, video, 408, 1, 82, 128, 181, 0x72, footer);
}

static void menu_row(packet2_t *packet, const video_t *video, int x0, int x1,
	int y, int selected, const char *label, const char *value)
{
	if (selected) { menu_flat_rect(packet, x0, y, x1, y + 30, 27, 67, 116, 0x58); menu_frame(packet, x0, y, x1, y + 30); }
	menu_text(packet, video, x0 + 10, y + 7, 2, selected ? 231 : 126,
		selected ? 239 : 185, selected ? 248 : 236, 0x80, label);
	if (value) {
		int x = x1 - 10 - (int)menu_text_width(value, 2);
		menu_text(packet, video, x, y + 7, 2, selected ? 255 : 143,
			selected ? 255 : 199, selected ? 255 : 239, 0x80, value);
	}
}

static void menu_profile_name(char out[HCU_MAIN_MENU_PROFILE_NAME_LENGTH + 1],
	const hcu_main_menu_profile *profile)
{
	int i;
	memcpy(out, profile->name, HCU_MAIN_MENU_PROFILE_NAME_LENGTH);
	out[HCU_MAIN_MENU_PROFILE_NAME_LENGTH] = '\0';
	for (i = HCU_MAIN_MENU_PROFILE_NAME_LENGTH - 1; i >= 0 && out[i] == ' '; --i) out[i] = '\0';
	if (!out[0]) strcpy(out, "UNNAMED");
}

static void menu_title(packet2_t *packet, const video_t *video,
	const hcu_main_menu_state *state, unsigned frame)
{
	unsigned i;
	(void)frame;
	menu_image_draw(packet, video, MENU_LOGO_PAGE, 9, 7, 8,
		30, 78, 482, 191, 0, 0, 511, 127, 1);
	for (i = 0; i < HCU_MAIN_MENU_ITEM_COUNT; ++i) {
		/* Atlas rows: bright, dark, bright, dark. Highlight uses the bright row. */
		int y = 250 + (int)i * 58;
		int base = i == HCU_MAIN_MENU_MULTIPLAYER ? 0 : 2;
		int row = base + (i == state->item ? 0 : 1);
		menu_image_draw(packet, video, MENU_BUTTONS_PAGE, 8, 8, 4,
			136, y, 376, y + 51, 0, row * 64, 255, row * 64 + 63, 1);
	}
}

static void menu_color_swatch(packet2_t *packet, int x0, int y0, int x1, int y1, unsigned color)
{
	static const uint8_t rgb[8][3] = {{218,224,230},{180,30,30},{35,70,190},{30,145,65},
		{222,105,22},{125,55,180},{214,176,38},{218,80,145}};
	color %= 8u; menu_flat_rect(packet, x0, y0, x1, y1, rgb[color][0], rgb[color][1], rgb[color][2], 0x80);
	menu_frame(packet, x0, y0, x1, y1);
}

static void menu_connect(packet2_t *packet, const video_t *video,
	const hcu_main_menu_state *state, const menu_pad_event pads[4])
{
	unsigned p;
	menu_page(packet, video, "CONNECT CONTROLLERS", "LEFT/RIGHT PROFILE   CROSS LOAD/JOIN   TRIANGLE GUEST   START CONTINUE");
	for (p = 0; p < 4; ++p) {
		int x = 30 + (int)(p & 1u) * 238, y = 86 + (int)(p >> 1) * 145;
		int joined = (state->joined_mask >> p) & 1u; char title[16], name[HCU_MAIN_MENU_PROFILE_NAME_LENGTH + 1];
		snprintf(title, sizeof(title), "PLAYER %u", p + 1u);
		menu_flat_rect(packet, x, y, x + 214, y + 124, joined ? 12 : 4, joined ? 32 : 13, joined ? 62 : 30, 0x68);
		menu_frame(packet, x, y, x + 214, y + 124);
		menu_text(packet, video, x + (214 - (int)menu_text_width(title, 2)) / 2,
			y + 14, 2, 218, 232, 245, 0x80, title);
		if (!pads[p].sample.connected) menu_text(packet, video, x + 43, y + 61, 2, 80, 105, 140, 0x70, "NO CONTROLLER");
		else if (!joined) {
			menu_profile_name(name, &state->profiles[state->port_profile[p]]);
			menu_text(packet, video, x + 25, y + 52, 2, 126, 190, 238, 0x78, name);
			menu_prompt(packet, video, x + 25, y + 82, 1, 210, 228, 244, 0x80, "CROSS PROFILE  TRIANGLE GUEST");
		} else {
			if (state->guest_mask & (1u << p)) snprintf(name, sizeof(name), "GUEST %u", p + 1u);
			else menu_profile_name(name, &state->profiles[state->port_profile[p]]);
			menu_text(packet, video, x + (214 - (int)menu_text_width(name, 2)) / 2,
				y + 48, 2, 230, 239, 248, 0x80, name);
			if (!(state->guest_mask & (1u << p))) menu_color_swatch(packet, x + 76, y + 82, x + 138, y + 104,
				state->profiles[state->port_profile[p]].armor_color);
		}
	}
}

static void menu_variant_name(const hcu_main_menu_state *state, char *out, size_t size)
{
	unsigned v = state->session.variant_index;
	if (v < HCU_MAIN_MENU_GAME_TYPE_COUNT) snprintf(out, size, "%s", s_game_types[v]);
	else snprintf(out, size, "CUSTOM %u", v - HCU_MAIN_MENU_GAME_TYPE_COUNT + 1u);
}

static void menu_lobby(packet2_t *packet, const video_t *video, const hcu_main_menu_state *state)
{
	static const char *const labels[LOBBY_ROW_COUNT] = {"GAME TYPE", "MAP", "GAME OPTIONS", "SAVE VARIANT", "START GAME"};
	static const unsigned type_picture[HCU_MAIN_MENU_GAME_TYPE_COUNT] = {0,1,2,3,4,2};
	unsigned r, p, map = state->session.map, type = state->session.variant.game_type;
	char variant[32], players[24];
	menu_variant_name(state, variant, sizeof(variant));
	snprintf(players, sizeof(players), "%u PLAYER%s", state->player_count, state->player_count == 1 ? "" : "S");
	menu_page(packet, video, "MULTIPLAYER", "CROSS JOIN/SELECT   CIRCLE LEAVE   START PLAY");
	menu_text(packet, video, 374, 38, 2, 100, 159, 218, 0x72, players);
	for (r = 0; r < LOBBY_ROW_COUNT; ++r) {
		const char *value = r == LOBBY_GAME_TYPE ? variant : r == LOBBY_MAP ? s_maps[map] : NULL;
		menu_row(packet, video, 26, 304, 80 + (int)r * 47, r == state->row, labels[r], value);
	}
	menu_image(packet, video, MENU_MAP_PAGE, 9, 8, MENU_MAP_ATLAS_W / 64u,
		322, 82, 488, 168, (int)(map % 4u) * 128 + 1, (int)(map / 4u) * 64 + 1,
		(int)(map % 4u) * 128 + 127, (int)(map / 4u) * 64 + 63);
	menu_frame(packet, 320, 80, 490, 170);
	{
		unsigned picture = type_picture[type % HCU_MAIN_MENU_GAME_TYPE_COUNT];
		menu_image(packet, video, MENU_TYPE_PAGE, 8, 8, MENU_TYPE_ATLAS_W / 64u,
			340, 190, 470, 255, (int)(picture % 2u) * 128 + 1, (int)(picture / 2u) * 64 + 1,
			(int)(picture % 2u) * 128 + 127, (int)(picture / 2u) * 64 + 63);
		menu_frame(packet, 338, 188, 472, 257);
	}
	for (p = 0; p < 4; ++p) {
		int x = 24 + (int)p * 119; char name[HCU_MAIN_MENU_PROFILE_NAME_LENGTH + 1];
		menu_flat_rect(packet, x, 332, x + 108, 397, 4, 15, 34, 0x68); menu_frame(packet, x, 332, x + 108, 397);
		if ((state->joined_mask >> p) & 1u) {
			if (state->guest_mask & (1u << p)) snprintf(name, sizeof(name), "GUEST %u", p + 1u);
			else menu_profile_name(name, &state->profiles[state->port_profile[p]]);
			menu_text(packet, video, x + 8, 344, 1, 225, 236, 248, 0x80, name);
			if (!(state->guest_mask & (1u << p))) menu_color_swatch(packet, x + 24, 368, x + 84, 388, state->profiles[state->port_profile[p]].armor_color);
		} else {
			const char *join = "PRESS CROSS";
			menu_prompt_piece pieces[8]; unsigned count = 0, width = 0;
			if (!menu_prompt_parse(join, pieces, 8, &count))
				width = menu_prompt_width(pieces, count, 1);
			else width = menu_text_width(join, 1);
			menu_prompt(packet, video, x + (108 - (int)width) / 2, 360, 1, 86, 124, 168, 0x70, join);
		}
	}
}

static void menu_game_options(packet2_t *packet, const video_t *video, const hcu_main_menu_state *state)
{
	static const char *const labels[OPTION_ROW_COUNT] = {
		"GAME TYPE RULES", "PLAYER OPTIONS", "ITEM OPTIONS", "INDICATOR OPTIONS", "BACK"};
	unsigned r;
	menu_page(packet, video, "GAME OPTIONS", "CROSS SELECT   CIRCLE BACK");
	for (r = 0; r < OPTION_ROW_COUNT; ++r)
		menu_row(packet, video, 50, 462, 94 + (int)r * 55, r == state->row, labels[r], NULL);
}

static const char *menu_yes_no(unsigned value) { return value ? "YES" : "NO"; }

static void menu_mode_option(const hcu_main_menu_variant *v, unsigned row,
	const char **label, const char **value, char *number, size_t number_size)
{
	static const unsigned ctf_scores[5] = {1,3,5,10,15};
	static const unsigned general_scores[5] = {1,2,5,10,15};
	static const unsigned slayer_scores[5] = {5,10,15,25,50};
	static const unsigned race_scores[6] = {1,3,5,10,15,25};
	static const char *const single_flag[6] = {"OFF","1 MIN","2 MIN","3 MIN","5 MIN","10 MIN"};
	static const char *const traits[4] = {"NONE","INVISIBLE","EXTRA DAMAGE","DAMAGE RESISTANT"};
	static const char *const speeds[3] = {"FAST","NORMAL","SLOW"};
	static const char *const balls[3] = {"NORMAL","REVERSE TAG","JUGGERNAUT"};
	static const char *const team_scoring[3] = {"MINIMUM","MAXIMUM","SUM"};
	static const char *const race_types[3] = {"NORMAL","ANY ORDER","RALLY"};
	*label = "BACK"; *value = NULL;
	switch (v->game_type) {
	case HCU_GAME_CTF:
		if (row == 0) { *label = "ASSAULT"; *value = menu_yes_no(v->ctf_assault); }
		else if (row == 1) { *label = "SINGLE FLAG"; *value = single_flag[v->ctf_single_flag % 6u]; }
		else if (row == 2) { *label = "FLAG MUST RESET"; *value = menu_yes_no(v->ctf_flag_must_reset); }
		else if (row == 3) { *label = "FLAG AT HOME TO SCORE"; *value = menu_yes_no(v->ctf_flag_at_home); }
		else if (row == 4) { *label = "CAPTURES TO WIN"; snprintf(number, number_size, "%u", ctf_scores[v->score_index % 5u]); *value = number; }
		break;
	case HCU_GAME_KING:
		if (row == 0) { *label = "MOVING HILL"; *value = menu_yes_no(v->king_moving_hill); }
		else if (row == 1) { *label = "SCORE TO WIN"; snprintf(number, number_size, "%u", general_scores[v->score_index % 5u]); *value = number; }
		else if (row == 2) { *label = "TEAMS"; *value = menu_yes_no(v->teams); }
		break;
	case HCU_GAME_ODDBALL:
		if (row == 0) { *label = "TRAIT WITH BALL"; *value = traits[v->oddball_trait_with_ball % 4u]; }
		else if (row == 1) { *label = "TRAIT WITHOUT BALL"; *value = traits[v->oddball_trait_without_ball % 4u]; }
		else if (row == 2) { *label = "SPEED WITH BALL"; *value = speeds[v->oddball_speed_with_ball % 3u]; }
		else if (row == 3) { *label = "BALL TYPE"; *value = balls[v->oddball_ball_type % 3u]; }
		else if (row == 4) { *label = "RANDOM START"; *value = menu_yes_no(v->oddball_random_start); }
		else if (row == 5) { *label = "BALL SPAWN COUNT"; snprintf(number, number_size, "%u", v->oddball_ball_count + 1u); *value = number; }
		else if (row == 6) { *label = "SCORE TO WIN"; snprintf(number, number_size, "%u", general_scores[v->score_index % 5u]); *value = number; }
		else if (row == 7) { *label = "TEAMS"; *value = menu_yes_no(v->teams); }
		break;
	case HCU_GAME_RACE:
		if (row == 0) { *label = "TEAM SCORING"; *value = team_scoring[v->race_team_scoring % 3u]; }
		else if (row == 1) { *label = "RACE TYPE"; *value = race_types[v->race_type % 3u]; }
		else if (row == 2) { *label = "LAPS TO WIN"; snprintf(number, number_size, "%u", race_scores[v->score_index % 6u]); *value = number; }
		else if (row == 3) { *label = "TEAMS"; *value = menu_yes_no(v->teams); }
		break;
	default:
		if (row == 0) { *label = "DEATH BONUS"; *value = menu_yes_no(v->slayer_death_bonus); }
		else if (row == 1) { *label = "KILL IN ORDER"; *value = menu_yes_no(v->slayer_kill_in_order); }
		else if (row == 2) { *label = "KILL PENALTY"; *value = menu_yes_no(v->slayer_kill_penalty); }
		else if (row == 3) { *label = "KILLS TO WIN"; snprintf(number, number_size, "%u", slayer_scores[v->score_index % 5u]); *value = number; }
		else if (row == 4) { *label = "TEAMS"; *value = menu_yes_no(v->teams); }
		break;
	}
}

static void menu_mode_options(packet2_t *packet, const video_t *video, const hcu_main_menu_state *state)
{
	unsigned r, count = menu_mode_row_count(state->session.variant.game_type);
	char number[16]; const char *label, *value;
	menu_page(packet, video, s_game_types[state->session.variant.game_type], "LEFT/RIGHT CHANGE   CROSS SELECT   CIRCLE BACK");
	for (r = 0; r < count; ++r) {
		menu_mode_option(&state->session.variant, r, &label, &value, number, sizeof(number));
		menu_row(packet, video, 28, 484, 78 + (int)r * (count > 7 ? 35 : 46), r == state->row, label, value);
	}
}

static void menu_player_options(packet2_t *packet, const video_t *video, const hcu_main_menu_state *state)
{
	static const char *const labels[PLAYER_ROW_COUNT] = {"NUMBER OF LIVES","MAXIMUM HEALTH","SHIELDS","RESPAWN TIME",
		"RESPAWN TIME GROWTH","ODD MAN OUT","INVISIBLE PLAYERS","SUICIDE PENALTY","BACK"};
	static const char *const lives[4] = {"UNLIMITED","1","3","5"};
	static const char *const health[6] = {"50%","100%","150%","200%","300%","400%"};
	static const char *const times[4] = {"INSTANT","5 SECONDS","10 SECONDS","15 SECONDS"};
	unsigned r; const hcu_main_menu_variant *v = &state->session.variant; const char *value;
	menu_page(packet, video, "PLAYER OPTIONS", "LEFT/RIGHT CHANGE   CROSS SELECT   CIRCLE BACK");
	for (r = 0; r < PLAYER_ROW_COUNT; ++r) {
		value = r == PLAYER_LIVES ? lives[v->lives % 4u] :
			r == PLAYER_HEALTH ? health[v->maximum_health % 6u] :
			r == PLAYER_SHIELDS ? menu_yes_no(v->shields) :
			r == PLAYER_RESPAWN ? times[v->respawn_time % 4u] :
			r == PLAYER_RESPAWN_GROWTH ? times[v->respawn_growth % 4u] :
			r == PLAYER_ODD_MAN_OUT ? menu_yes_no(v->odd_man_out) :
			r == PLAYER_INVISIBLE ? menu_yes_no(v->invisible_players) :
			r == PLAYER_SUICIDE_PENALTY ? times[v->suicide_penalty % 4u] : NULL;
		menu_row(packet, video, 24, 488, 76 + (int)r * 36, r == state->row, labels[r], value);
	}
}

static void menu_item_options(packet2_t *packet, const video_t *video, const hcu_main_menu_state *state)
{
	static const char *const labels[ITEM_ROW_COUNT] = {"INFINITE GRENADES","VEHICLE SET","WEAPON SET","STARTING EQUIPMENT","BACK"};
	static const char *const vehicles[5] = {"DEFAULT","NONE","WARTHOG","GHOST","SCORPION"};
	static const char *const weapons[11] = {"NORMAL","PISTOLS","RIFLES","PLASMA WEAPONS","SNIPER",
		"NO SNIPING","ROCKET LAUNCHERS","SHOTGUNS","SHORT RANGE","HUMAN","NONE"};
	unsigned r; const hcu_main_menu_variant *v = &state->session.variant; const char *value;
	menu_page(packet, video, "ITEM OPTIONS", "LEFT/RIGHT CHANGE   CROSS SELECT   CIRCLE BACK");
	for (r = 0; r < ITEM_ROW_COUNT; ++r) {
		value = r == ITEM_GRENADES ? menu_yes_no(v->infinite_grenades) :
			r == ITEM_VEHICLES ? vehicles[v->vehicle_set % 5u] :
			r == ITEM_WEAPONS ? weapons[v->weapon_set % 11u] :
			r == ITEM_STARTING_EQUIPMENT ? (v->starting_equipment ? "GENERIC" : "CUSTOM") : NULL;
		menu_row(packet, video, 36, 476, 96 + (int)r * 54, r == state->row, labels[r], value);
	}
}

static void menu_indicator_options(packet2_t *packet, const video_t *video, const hcu_main_menu_state *state)
{
	static const char *const labels[INDICATOR_ROW_COUNT] = {"RADAR DISPLAY","OTHER PLAYERS ON RADAR","FRIENDS ON SCREEN","BACK"};
	static const char *const displays[3] = {"MOTION TRACKER","NAV POINTS","NONE"};
	unsigned r; const hcu_main_menu_variant *v = &state->session.variant; const char *value;
	menu_page(packet, video, "INDICATOR OPTIONS", "LEFT/RIGHT CHANGE   CROSS SELECT   CIRCLE BACK");
	for (r = 0; r < INDICATOR_ROW_COUNT; ++r) {
		value = r == INDICATOR_RADAR_DISPLAY ? displays[v->radar_display % 3u] :
			r == INDICATOR_OTHER_PLAYERS ? menu_yes_no(v->other_players_radar) :
			r == INDICATOR_FRIENDS ? menu_yes_no(v->friends_on_screen) : NULL;
		menu_row(packet, video, 30, 482, 108 + (int)r * 62, r == state->row, labels[r], value);
	}
}

static void menu_save_variant(packet2_t *packet, const video_t *video, const hcu_main_menu_state *state)
{
	const hcu_main_menu_variant *saved = menu_saved_variants_const(state);
	unsigned i, first = state->row > 5u ? state->row - 5u : 0u;
	char slot[32], type[32], position[32];
	char owner[HCU_MAIN_MENU_PROFILE_NAME_LENGTH + 1];
	menu_profile_name(owner, &state->profiles[state->port_profile[0]]);
	menu_page(packet, video, "SAVE GAME TYPE", "PLAYER 1 PROFILE   UP/DOWN SCROLL   CROSS SAVE   CIRCLE BACK");
	menu_text(packet, video, 58, 76, 1, 100, 159, 218, 0x72, owner);
	for (i = first; i < first + 6u && i <= HCU_MAIN_MENU_SAVED_VARIANT_COUNT; ++i) {
		if (i == HCU_MAIN_MENU_SAVED_VARIANT_COUNT) {
			menu_row(packet, video, 58, 454, 106 + (int)(i - first) * 48,
				state->row == i, "BACK", NULL);
			continue;
		}
		if (saved[i].valid && saved[i].game_type < HCU_MAIN_MENU_GAME_TYPE_COUNT)
			snprintf(type, sizeof(type), "%s", s_game_types[saved[i].game_type]);
		else snprintf(type, sizeof(type), "EMPTY");
		snprintf(slot, sizeof(slot), "CUSTOM %u", i + 1u);
		menu_row(packet, video, 58, 454, 106 + (int)(i - first) * 48,
			i == state->row, slot, type);
	}
	snprintf(position, sizeof(position), "%u / %u", state->row + 1u,
		(unsigned)HCU_MAIN_MENU_SAVED_VARIANT_COUNT + 1u);
	menu_text_center(packet, video, 385, 1, 142, 181, 217, 0x80, position);
}

static const char *menu_layout_name(unsigned value)
{
	static const char *const names[5] = {"DEFAULT","SOUTHPAW","BOXER","GREEN THUMB","LEGACY"};
	return names[value % 5u];
}

static const char *menu_color_name(unsigned value)
{
	static const char *const names[8] = {"WHITE","RED","BLUE","GREEN","ORANGE","PURPLE","GOLD","PINK"};
	return names[value % 8u];
}

static void menu_profile_select(packet2_t *packet, const video_t *video, const hcu_main_menu_state *state)
{
	unsigned i, first = 0;
	char name[HCU_MAIN_MENU_PROFILE_NAME_LENGTH + 1], slot[16], position[32];
	if (state->row >= 9u) first = (state->row / 3u - 2u) * 3u;
	menu_page(packet, video, "MEMORY CARD PROFILES", "CROSS LOAD   SQUARE CREATE   CIRCLE BACK");
	for (i = first; i < first + 9u && i < HCU_MAIN_MENU_PROFILE_COUNT; ++i) {
		unsigned cell = i - first;
		int x = 27 + (int)(cell % 3u) * 154;
		int y = 76 + (int)(cell / 3u) * 104;
		int selected = i == state->row;
		menu_profile_name(name, &state->profiles[i]); snprintf(slot, sizeof(slot), "PROFILE %u", i + 1u);
		menu_flat_rect(packet, x, y, x + 148, y + 97,
			selected ? 22u : 4u, selected ? 53u : 17u, selected ? 91u : 37u, 0x70);
		menu_frame(packet, x, y, x + 148, y + 97);
		menu_text(packet, video, x + 10, y + 12, 1, 218, 233, 248, 0x80, slot);
		if (state->profile_present_mask & (1u << i)) {
			menu_text(packet, video, x + 10, y + 49, 1, 225, 239, 250, 0x80, name);
			menu_color_swatch(packet, x + 101, y + 73, x + 132, y + 86,
				state->profiles[i].armor_color);
		} else menu_text(packet, video, x + 10, y + 49, 1, 106, 151, 187, 0x80, "EMPTY");
	}
	snprintf(position, sizeof(position), "%u / %u", state->row + 1u,
		(unsigned)HCU_MAIN_MENU_PROFILE_COUNT);
	menu_text_center(packet, video, 392, 1, 142, 181, 217, 0x80, position);
}

static void menu_profile_edit(packet2_t *packet, const video_t *video, const hcu_main_menu_state *state)
{
	static const char *const labels[PROFILE_ROW_COUNT] = {"USERNAME","CONTROL LAYOUT","ARMOR COLOR","INVERT LOOK",
		"LOOK SENSITIVITY","VIBRATION","MAKE ACTIVE","BACK"};
	unsigned r; char name[HCU_MAIN_MENU_PROFILE_NAME_LENGTH + 1], value[16];
	const hcu_main_menu_profile *profile = &state->profiles[state->profile_index];
	menu_page(packet, video, "CUSTOMIZE PROFILE", "CROSS/LEFT/RIGHT CHANGE   CIRCLE BACK");
	menu_profile_name(name, profile);
	for (r = 0; r < PROFILE_ROW_COUNT; ++r) {
		const char *shown = NULL;
		if (r == PROFILE_NAME) shown = name;
		else if (r == PROFILE_LAYOUT) shown = menu_layout_name(profile->control_layout);
		else if (r == PROFILE_COLOR) shown = menu_color_name(profile->armor_color);
		else if (r == PROFILE_INVERT) shown = profile->look_inverted ? "YES" : "NO";
		else if (r == PROFILE_SENSITIVITY) { snprintf(value, sizeof(value), "%u", profile->look_sensitivity); shown = value; }
		else if (r == PROFILE_VIBRATION) shown = profile->vibration ? "ON" : "OFF";
		else if (r == PROFILE_ACTIVE) shown = state->port_profile[0] == state->profile_index ? "PLAYER 1" : NULL;
		menu_row(packet, video, 42, 470, 78 + (int)r * 39, r == state->row, labels[r], shown);
	}
	menu_color_swatch(packet, 405, 163, 450, 181, profile->armor_color);
}

static void menu_profile_name_edit(packet2_t *packet, const video_t *video, const hcu_main_menu_state *state)
{
	unsigned i; const hcu_main_menu_profile *profile = &state->profiles[state->profile_index];
	menu_page(packet, video, "EDIT USERNAME", "LEFT/RIGHT CURSOR   UP/DOWN CHARACTER   CROSS DONE");
	menu_flat_rect(packet, 52, 150, 460, 250, 4, 17, 38, 0x72); menu_frame(packet, 52, 150, 460, 250);
	for (i = 0; i < HCU_MAIN_MENU_PROFILE_NAME_LENGTH; ++i) {
		char letter[2] = {profile->name[i], '\0'}; int x = 69 + (int)i * 32;
		if (i == state->name_cursor) { menu_flat_rect(packet, x - 5, 180, x + 25, 221, 27, 67, 116, 0x68); menu_frame(packet, x - 5, 180, x + 25, 221); }
		menu_text(packet, video, x, 188, 3, 230, 239, 248, 0x80, letter);
	}
}

static void menu_controls(packet2_t *packet, const video_t *video, const hcu_main_menu_state *state)
{
	static const char *const labels[CONTROL_ROW_COUNT] = {"PROFILE","CONTROL LAYOUT","INVERT LOOK","LOOK SENSITIVITY","VIBRATION","BACK"};
	unsigned r; char name[HCU_MAIN_MENU_PROFILE_NAME_LENGTH + 1], value[16];
	const hcu_main_menu_profile *profile = &state->profiles[state->profile_index];
	menu_page(packet, video, "CONTROLS", "EACH PROFILE KEEPS ITS OWN CONTROLS"); menu_profile_name(name, profile);
	for (r = 0; r < CONTROL_ROW_COUNT; ++r) {
		const char *shown = NULL;
		if (r == CONTROL_PROFILE) shown = name;
		else if (r == CONTROL_LAYOUT) shown = menu_layout_name(profile->control_layout);
		else if (r == CONTROL_INVERT) shown = profile->look_inverted ? "YES" : "NO";
		else if (r == CONTROL_SENSITIVITY) { snprintf(value, sizeof(value), "%u", profile->look_sensitivity); shown = value; }
		else if (r == CONTROL_VIBRATION) shown = profile->vibration ? "ON" : "OFF";
		menu_row(packet, video, 48, 464, 92 + (int)r * 50, r == state->row, labels[r], shown);
	}
}

static void menu_settings(packet2_t *packet, const video_t *video, const hcu_main_menu_state *state)
{
	static const char *const labels[SETTINGS_HUB_ROWS] = {
		"PLAYER PROFILES", "CONTROLLER SETTINGS", "VIDEO AND AUDIO", "BACK"
	};
	unsigned row;
	menu_page(packet, video, "SETTINGS", "CROSS SELECT   CIRCLE BACK");
	for (row = 0; row < SETTINGS_HUB_ROWS; ++row)
		menu_row(packet, video, 54, 458, 113 + (int)row * 62,
			row == state->row, labels[row], NULL);
	menu_text_center(packet, video, 374, 1, 119, 169, 211, 0x80,
		"PROFILES AND GAME TYPES SAVE TO MEMORY CARD 1");
}

static void menu_video_settings(packet2_t *packet, const video_t *video, const hcu_main_menu_state *state)
{
	static const char *const labels[SETTING_ROW_COUNT] = {"3D RESOLUTION","ANIMATIONS","PARTICLES","VIEW MODEL",
		"TERRAIN DETAIL","WIDESCREEN","HUD INSET","FPS COUNTER","SUBTITLES","BACK"};
	static const char *const resolutions[4] = {"STANDARD","MEDIUM","CHUNKY","HIGH DETAIL"};
	static const char *const view_models[4] = {"LOW","MEDIUM","HIGH","OFF IN SPLIT"};
	static const char *const terrain[4] = {"FULL","HIGH","MEDIUM","LOW"};
	unsigned r; char inset[16];
	menu_page(packet, video, "VIDEO AND AUDIO", "LEFT/RIGHT CHANGE   CROSS SELECT   CIRCLE BACK");
	for (r = 0; r < SETTING_ROW_COUNT; ++r) {
		const char *value = NULL;
		if (r == SETTING_RESOLUTION) value = resolutions[state->resolution % 4u];
		else if (r == SETTING_ANIMATIONS) value = state->animation_rate ? "HALF RATE" : "FULL RATE";
		else if (r == SETTING_PARTICLES) value = state->particles ? "ON" : "OFF";
		else if (r == SETTING_VIEW_MODEL) value = view_models[state->view_model % 4u];
		else if (r == SETTING_TERRAIN) value = terrain[state->terrain_detail % 4u];
		else if (r == SETTING_WIDESCREEN) value = state->widescreen ? "ANAMORPHIC" : "OFF";
		else if (r == SETTING_HUD_INSET) { if (state->hud_inset) snprintf(inset, sizeof(inset), "%u PIXELS", state->hud_inset * 4u); else strcpy(inset, "OFF"); value = inset; }
		else if (r == SETTING_FPS) value = state->fps_counter ? "ON" : "OFF";
		else if (r == SETTING_SUBTITLES) value = state->subtitles ? "ON" : "OFF";
		menu_row(packet, video, 38, 474, 75 + (int)r * 33, r == state->row, labels[r], value);
	}
}

static int menu_load_textures(const uint16_t *textures[11], void **allocation)
{
#if defined(__mips__)
	/* Order matches tools/build_hcu_menu_assets.py. Older discs omit the glyph atlas. */
	const size_t rings_bytes = MENU_RING_INNER_BYTES + MENU_RING_OUTER_BYTES;
	const size_t base_bytes = rings_bytes + MENU_MAP_ATLAS_BYTES + MENU_TYPE_ATLAS_BYTES +
		MENU_LOGO_BYTES + MENU_BUTTONS_BYTES + MENU_PLANET_BYTES;
	const size_t glyph_bytes = base_bytes + MENU_GLYPH_BYTES;
	const size_t legacy_full_bytes = glyph_bytes + 2u * MENU_SPACE_BYTES;
	const size_t full_bytes = legacy_full_bytes + MENU_RING_SHADOW_BYTES;
	unsigned long file_size = 0, read_size = 0;
	uint8_t *data;
	int file = hcu_file_bridge_open("D:\\packages\\menu_textures.bin", &file_size);
	if (file < 0 || (file_size != base_bytes && file_size != glyph_bytes &&
		file_size != legacy_full_bytes && file_size < full_bytes + MENU_CAMERA_BYTES + 8u)) {
		if (file >= 0) hcu_file_bridge_close(file);
		return -1;
	}
	data = (uint8_t *)malloc((size_t)file_size);
	if (!data) { hcu_file_bridge_close(file); return -1; }
	if (!hcu_file_bridge_read(file, data, (unsigned long)file_size, &read_size) ||
		read_size != file_size) {
		hcu_file_bridge_close(file); free(data); return -1;
	}
	hcu_file_bridge_close(file);
	if (file_size >= full_bytes + MENU_CAMERA_BYTES + 8u) {
		menu_camera_import(data + full_bytes, MENU_CAMERA_BYTES);
		if (menu_ring_mesh_import(data + full_bytes + MENU_CAMERA_BYTES,
			(size_t)file_size - full_bytes - MENU_CAMERA_BYTES, 1)) {
			free(data); return -1;
		}
	}
	textures[0] = (const uint16_t *)data;
	textures[1] = (const uint16_t *)(data + MENU_RING_INNER_BYTES);
	textures[2] = (const uint16_t *)(data + rings_bytes);
	textures[3] = (const uint16_t *)(data + rings_bytes + MENU_MAP_ATLAS_BYTES);
	textures[4] = (const uint16_t *)(data + rings_bytes + MENU_MAP_ATLAS_BYTES + MENU_TYPE_ATLAS_BYTES);
	textures[5] = (const uint16_t *)((const uint8_t *)textures[4] + MENU_LOGO_BYTES);
	textures[6] = (const uint16_t *)((const uint8_t *)textures[5] + MENU_BUTTONS_BYTES);
	textures[7] = file_size >= glyph_bytes ?
		(const uint16_t *)((const uint8_t *)textures[6] + MENU_PLANET_BYTES) :
		hcu_main_menu_glyphs_rgb5a1;
	textures[8] = file_size >= legacy_full_bytes ?
		(const uint16_t *)((const uint8_t *)textures[7] + MENU_GLYPH_BYTES) :
		textures[6];
	textures[9] = file_size >= legacy_full_bytes ?
		(const uint16_t *)((const uint8_t *)textures[8] + MENU_SPACE_BYTES) :
		textures[1];
	textures[10] = file_size >= full_bytes ?
		(const uint16_t *)(data + legacy_full_bytes) : textures[0];
	*allocation = data;
#else
	textures[0] = hcu_main_menu_ring_inner_rgb5a1;
	textures[1] = hcu_main_menu_ring_outer_rgb5a1;
	textures[2] = hcu_main_menu_map_atlas_rgb5a1;
	textures[3] = hcu_main_menu_gametype_atlas_rgb5a1;
	textures[4] = hcu_main_menu_logo_rgb5a1;
	textures[5] = hcu_main_menu_buttons_rgb5a1;
	textures[6] = hcu_main_menu_planet_rgb5a1;
	textures[7] = hcu_main_menu_glyphs_rgb5a1;
	textures[8] = hcu_main_menu_space_rgb5a1;
	textures[9] = hcu_main_menu_stars_rgb5a1;
	textures[10] = hcu_main_menu_ring_shadow_rgb5a1;
	menu_camera_import(hcu_main_menu_camera_bin, MENU_CAMERA_BYTES);
	if (menu_ring_mesh_import(hcu_main_menu_ring_mesh_bin,
		(size_t)(hcu_main_menu_ring_mesh_end - hcu_main_menu_ring_mesh_bin), 0)) return -1;
	*allocation = NULL;
#endif
	return 0;
}

static int menu_upload_assets(video_t *video, void *dma_storage, size_t dma_bytes,
	uint8_t *font, uint32_t *clut, const uint16_t *textures[11])
{
	chain_t chain;
	if (dma_bytes < 144u * 16u) return -1;
	if ((uint64_t)video->tex_base +
		(uint64_t)(MENU_RING_SHADOW_PAGE + 1u) * MENU_PAGE_WORDS > VIDEO_VRAM_WORDS)
		return -1;
	text_build_atlas(font); text_build_clut(clut);
	SyncDCache((void *)textures[0], (uint8_t *)textures[0] + MENU_RING_INNER_BYTES);
	SyncDCache((void *)textures[1], (uint8_t *)textures[1] + MENU_RING_OUTER_BYTES);
	SyncDCache((void *)textures[2], (uint8_t *)textures[2] + MENU_MAP_ATLAS_BYTES);
	SyncDCache((void *)textures[3], (uint8_t *)textures[3] + MENU_TYPE_ATLAS_BYTES);
	SyncDCache((void *)textures[4], (uint8_t *)textures[4] + MENU_LOGO_BYTES);
	SyncDCache((void *)textures[5], (uint8_t *)textures[5] + MENU_BUTTONS_BYTES);
	SyncDCache((void *)textures[6], (uint8_t *)textures[6] + MENU_PLANET_BYTES);
	SyncDCache((void *)textures[7], (uint8_t *)textures[7] + MENU_GLYPH_BYTES);
	SyncDCache((void *)textures[8], (uint8_t *)textures[8] + MENU_SPACE_BYTES);
	SyncDCache((void *)textures[9], (uint8_t *)textures[9] + MENU_SPACE_BYTES);
	SyncDCache((void *)textures[10], (uint8_t *)textures[10] + MENU_RING_SHADOW_BYTES);
	SyncDCache(font, font + MENU_FONT_BYTES); SyncDCache(clut, (uint8_t *)clut + MENU_CLUT_BYTES);
	chain_init(&chain, dma_storage, 144u);
	if (gs_upload(&chain, textures[0], MENU_RING_INNER_BYTES,
		(video->tex_base + MENU_RING_INNER_PAGE * MENU_PAGE_WORDS) / 64u,
		MENU_RING_W / 64u, GS_PSMCT16S, MENU_RING_W, MENU_RING_INNER_H) ||
		gs_upload(&chain, textures[1], MENU_RING_OUTER_BYTES,
		(video->tex_base + MENU_RING_OUTER_PAGE * MENU_PAGE_WORDS) / 64u,
		MENU_RING_W / 64u, GS_PSMCT16S, MENU_RING_W, MENU_RING_OUTER_H) ||
		gs_upload(&chain, textures[2], MENU_MAP_ATLAS_BYTES,
		(video->tex_base + MENU_MAP_PAGE * MENU_PAGE_WORDS) / 64u,
		MENU_MAP_ATLAS_W / 64u, GS_PSMCT16S, MENU_MAP_ATLAS_W, MENU_MAP_ATLAS_H) ||
		gs_upload(&chain, textures[3], MENU_TYPE_ATLAS_BYTES,
		(video->tex_base + MENU_TYPE_PAGE * MENU_PAGE_WORDS) / 64u,
		MENU_TYPE_ATLAS_W / 64u, GS_PSMCT16S, MENU_TYPE_ATLAS_W, MENU_TYPE_ATLAS_H) ||
		gs_upload(&chain, textures[4], MENU_LOGO_BYTES,
			(video->tex_base + MENU_LOGO_PAGE * MENU_PAGE_WORDS) / 64u,
			512u / 64u, GS_PSMCT16S, 512u, 128u) ||
		gs_upload(&chain, textures[5], MENU_BUTTONS_BYTES,
			(video->tex_base + MENU_BUTTONS_PAGE * MENU_PAGE_WORDS) / 64u,
			256u / 64u, GS_PSMCT16S, 256u, 256u) ||
		gs_upload(&chain, textures[6], MENU_PLANET_BYTES,
			(video->tex_base + MENU_PLANET_PAGE * MENU_PAGE_WORDS) / 64u,
			256u / 64u, GS_PSMCT16S, 256u, 256u) ||
		gs_upload(&chain, textures[7], MENU_GLYPH_BYTES,
			(video->tex_base + MENU_GLYPH_PAGE * MENU_PAGE_WORDS) / 64u,
			MENU_GLYPH_W / 64u, GS_PSMCT16S, MENU_GLYPH_W, MENU_GLYPH_H) ||
		gs_upload(&chain, textures[8], MENU_SPACE_BYTES,
			(video->tex_base + MENU_SPACE_PAGE * MENU_PAGE_WORDS) / 64u,
			2u, GS_PSMCT16S, 128u, 128u) ||
		gs_upload(&chain, textures[9], MENU_SPACE_BYTES,
			(video->tex_base + MENU_STARS_PAGE * MENU_PAGE_WORDS) / 64u,
			2u, GS_PSMCT16S, 128u, 128u) ||
		gs_upload(&chain, textures[10], MENU_RING_SHADOW_BYTES,
			(video->tex_base + MENU_RING_SHADOW_PAGE * MENU_PAGE_WORDS) / 64u,
			MENU_RING_W / 64u, GS_PSMCT16S, MENU_RING_W, MENU_RING_INNER_H) ||
		gs_upload(&chain, font, MENU_FONT_BYTES,
		(video->tex_base + MENU_FONT_PAGE * MENU_PAGE_WORDS) / 64u,
		TEXT_ATLAS_W / 64u, GS_PSMT8, TEXT_ATLAS_W, TEXT_ATLAS_H) ||
		gs_upload(&chain, clut, MENU_CLUT_BYTES,
		(video->tex_base + MENU_CLUT_PAGE * MENU_PAGE_WORDS) / 64u,
		1u, GS_PSMCT32, 16u, 16u)) return -1;
	chain_end(&chain, 0); SyncDCache(dma_storage, (uint8_t *)dma_storage + chain_qwords(&chain) * 16u);
	dma_channel_send_chain(DMA_CHANNEL_GIF, dma_storage, 0, 0, 0); dma_wait_fast();
	return chain.overflow ? -1 : 0;
}

static void menu_read_input(menu_input *input, menu_pad_event events[4],
	int *up, int *down, int *left, int *right, int *confirm, int *back, int *start)
{
	pad_sample pads[4]; unsigned p, direction = 0;
	*up = *down = *left = *right = *confirm = *back = *start = 0;
	(void)pad_poll_players(pads);
	for (p = 0; p < 4u; ++p) {
		unsigned edges = pads[p].buttons & ~input->previous[p];
		input->previous[p] = pads[p].buttons; events[p].sample = pads[p]; events[p].edges = edges;
		*up |= (edges & MENU_PAD_UP) != 0; *down |= (edges & MENU_PAD_DOWN) != 0;
		*left |= (edges & MENU_PAD_LEFT) != 0; *right |= (edges & MENU_PAD_RIGHT) != 0;
		*confirm |= (edges & PAD_BTN_CROSS) != 0; *back |= (edges & PAD_BTN_CIRCLE) != 0;
		*start |= (edges & PAD_BTN_START) != 0;
		if (!direction && pads[p].connected) {
			if (pads[p].ly < MENU_DEAD_LOW) direction = 1; else if (pads[p].ly > MENU_DEAD_HIGH) direction = 2;
			else if (pads[p].lx < MENU_DEAD_LOW) direction = 3; else if (pads[p].lx > MENU_DEAD_HIGH) direction = 4;
		}
	}
	if (!direction) { input->repeat_direction = 0; input->repeat_frames = 0; }
	else if (direction != input->repeat_direction) {
		input->repeat_direction = direction; input->repeat_frames = 18;
		*up |= direction == 1; *down |= direction == 2; *left |= direction == 3; *right |= direction == 4;
	} else if (input->repeat_frames && --input->repeat_frames == 0) {
		input->repeat_frames = 6;
		*up |= direction == 1; *down |= direction == 2; *left |= direction == 3; *right |= direction == 4;
	}
}

static void menu_join_players(hcu_main_menu_state *state, menu_pad_event events[4],
	int allow_continue, int *suppress_confirm, int *suppress_back)
{
	unsigned p;
	for (p = 0; p < 4u; ++p) {
		int joined = (state->joined_mask >> p) & 1u;
		if (!events[p].sample.connected && joined) {
			/* A guest slot has no pad of its own; it stays until Down removes it. */
			if ((state->guest_mask >> p) & 1u) continue;
			state->joined_mask &= (uint8_t)~(1u << p); if (state->player_count) --state->player_count;
			continue;
		}
		if (!events[p].sample.connected) continue;
		{
			unsigned old_profile = state->port_profile[p];
			if (events[p].edges & MENU_PAD_LEFT) state->port_profile[p] = (uint8_t)menu_wrap(state->port_profile[p], -1, HCU_MAIN_MENU_PROFILE_COUNT);
			if (events[p].edges & MENU_PAD_RIGHT) state->port_profile[p] = (uint8_t)menu_wrap(state->port_profile[p], 1, HCU_MAIN_MENU_PROFILE_COUNT);
			if (p == 0 && old_profile != state->port_profile[p]) menu_profile_owner_changed(state);
		}
		if (!joined && (events[p].edges & PAD_BTN_CROSS)) {
			(void)menu_storage_load_profile(state, state->port_profile[p]);
			state->guest_mask &= (uint8_t)~(1u << p);
			state->joined_mask |= (uint8_t)(1u << p); ++state->player_count; *suppress_confirm = 1;
		} else if (!joined && (events[p].edges & PAD_BTN_TRIANGLE)) {
			state->guest_mask |= (uint8_t)(1u << p);
			state->joined_mask |= (uint8_t)(1u << p); ++state->player_count;
		} else if (joined && (events[p].edges & PAD_BTN_CIRCLE)) {
			state->joined_mask &= (uint8_t)~(1u << p); state->guest_mask &= (uint8_t)~(1u << p);
			if (state->player_count) --state->player_count;
			*suppress_back = 1;
		} else if (!allow_continue && (events[p].edges & PAD_BTN_CROSS)) *suppress_confirm = 1;
	}
}

enum hcu_main_menu_action hcu_main_menu_run(video_t *video,
	void *dma_storage, size_t dma_bytes, arena_t *scratch)
{
	hcu_main_menu_state state; menu_input input; menu_pad_event events[4]; packet2_t packet;
	enum hcu_main_menu_action action = HCU_MAIN_MENU_ACTION_NONE; size_t mark;
	uint8_t *font; uint32_t *clut; unsigned frame = 0;
#if defined(__mips__)
	int theme_loop_started = 0;
#endif
	const uint16_t *textures[11]; void *texture_allocation = NULL;
	if (!video || !dma_storage || dma_bytes < MENU_PACKET_QW * 16u || !scratch)
		return HCU_MAIN_MENU_ACTION_MULTIPLAYER;
	mark = arena_mark(scratch);
	font = (uint8_t *)arena_alloc(scratch, MENU_FONT_BYTES, 64u);
	clut = (uint32_t *)arena_alloc(scratch, MENU_CLUT_BYTES, 64u);
	if (!font || !clut || menu_load_textures(textures, &texture_allocation)) {
#if defined(__mips__)
		hcu_loading_screen_end();
#endif
		free(texture_allocation);
		menu_ring_mesh_clear();
		arena_release(scratch, mark); printf("HALO_PS2_FAIL main-menu asset load\n"); return HCU_MAIN_MENU_ACTION_MULTIPLAYER;
	}
#if defined(__mips__)
	/* Finish the boot sweep while the loading image still owns its GS pages.
	 * Uploading the menu atlases first replaces those pages and makes the tail
	 * frames display atlas tiles instead of the loading screen. */
	hcu_loading_screen_end();
#endif
	if (menu_upload_assets(video, dma_storage, dma_bytes, font, clut, textures)) {
		free(texture_allocation);
		menu_ring_mesh_clear();
		arena_release(scratch, mark); printf("HALO_PS2_FAIL main-menu asset upload\n"); return HCU_MAIN_MENU_ACTION_MULTIPLAYER;
	}
	free(texture_allocation);
	hcu_main_menu_state_init(&state);
	menu_storage_load(&state);
	s_menu_widescreen = state.widescreen != 0;
	if (hcu_spu_init() == 0)
		(void)hcu_spu_load_bank("D:\\packages\\menu_audio.hsb");
	if (s_kept_ready) { memcpy(state.profiles, s_kept_profiles, sizeof(s_kept_profiles)); memcpy(state.saved_variants, s_kept_variants, sizeof(s_kept_variants)); }
	memset(&input, 0, sizeof(input)); memset(events, 0, sizeof(events)); memset(&packet, 0, sizeof(packet));
	packet.max_qwords_count = MENU_PACKET_QW; packet.type = P2_TYPE_NORMAL; packet.mode = P2_MODE_NORMAL;
	packet.base = packet.next = (qword_t *)dma_storage;
	printf("HALO_PS2_LOCAL main-menu-ready items=%u texture=%ux%u maps=%u profiles=%u\n",
		(unsigned)HCU_MAIN_MENU_ITEM_COUNT, MENU_RING_W, MENU_RING_OUTER_H,
		(unsigned)HCU_MAIN_MENU_MAP_COUNT, (unsigned)HCU_MAIN_MENU_PROFILE_COUNT);
#if defined(__mips__)
	menu_sound("sound\\music\\title1\\in", HCU_SOUND_EVENT_IMPULSE, 0);
#endif
	while (action == HCU_MAIN_MENU_ACTION_NONE) {
		int up, down, left, right, confirm, back, start, suppress_confirm = 0, suppress_back = 0;
		unsigned previous_page = state.page;
		if (frame == 0) printf("HALO_PS2_LOCAL main-menu-frame stage=input\n");
		menu_read_input(&input, events, &up, &down, &left, &right, &confirm, &back, &start);
#if defined(__mips__)
		hcu_spu_tick(frame * 1000u / 60u);
		/* Retail title1 intro is 33.29 seconds; start the loop at the
		 * nearest frame so the port does not leave an audible pause. */
		if (!theme_loop_started && frame >= 1997u) {
			menu_sound("sound\\music\\title1\\loops", HCU_SOUND_EVENT_LOOPING_START, frame);
			theme_loop_started = 1;
		}
		if (confirm || start)
			menu_sound("sound\\sfx\\ui\\forward", HCU_SOUND_EVENT_IMPULSE, frame);
		else if (back)
			menu_sound("sound\\sfx\\ui\\back", HCU_SOUND_EVENT_IMPULSE, frame);
		else if (up || down || left || right)
			menu_sound("sound\\sfx\\ui\\cursor", HCU_SOUND_EVENT_IMPULSE, frame);
#endif
		if (state.page == HCU_MAIN_MENU_PAGE_CONNECT) {
			menu_join_players(&state, events, 1, &suppress_confirm, &suppress_back);
			/* One pad can still open the other split slots. Up adds a guest,
			 * Down removes the highest one. Port 0 stays the physical pad. */
			if (up && state.player_count < 4u) {
				unsigned p;
				for (p = 0; p < 4u; ++p) {
					if ((state.joined_mask >> p) & 1u) continue;
					state.guest_mask |= (uint8_t)(1u << p);
					state.joined_mask |= (uint8_t)(1u << p);
					++state.player_count;
					printf("HALO_PS2_LOCAL menu-split players=%u\n", state.player_count);
					break;
				}
			} else if (down && state.player_count > 1u) {
				unsigned p;
				for (p = 4u; p-- > 0u; ) {
					if (p == 0u || !((state.joined_mask >> p) & 1u)) continue;
					state.joined_mask &= (uint8_t)~(1u << p);
					state.guest_mask &= (uint8_t)~(1u << p);
					--state.player_count;
					break;
				}
			}
			if (start && state.player_count) { state.page = HCU_MAIN_MENU_PAGE_LOBBY; state.row = 0; }
			else if (back && !suppress_back && !state.player_count) { state.page = HCU_MAIN_MENU_PAGE_TITLE; state.row = 0; }
		} else if (state.page == HCU_MAIN_MENU_PAGE_LOBBY) {
			menu_join_players(&state, events, 0, &suppress_confirm, &suppress_back);
			if (!state.player_count) { state.page = HCU_MAIN_MENU_PAGE_CONNECT; state.row = 0; }
			else {
				action = hcu_main_menu_step(&state, up, down, left, right,
					(confirm && !suppress_confirm) || start, 0);
			}
		} else action = hcu_main_menu_step(&state, up, down, left, right,
			confirm || start, back);
		if (state.page == HCU_MAIN_MENU_PAGE_PROFILE_SELECT &&
			(events[0].edges & PAD_BTN_SQUARE) && hcu_main_menu_create_profile(&state)) {
			menu_storage_save_profile(&state, state.profile_index);
			printf("HALO_PS2_LOCAL profile-created slot=%u\n", state.profile_index + 1u);
		}
		if (previous_page == HCU_MAIN_MENU_PAGE_PROFILE_SELECT &&
			state.page == HCU_MAIN_MENU_PAGE_PROFILE_EDIT)
			(void)menu_storage_load_profile(&state, state.profile_index);
		if (state.page != previous_page &&
			(previous_page == HCU_MAIN_MENU_PAGE_PROFILE_EDIT ||
			 previous_page == HCU_MAIN_MENU_PAGE_PROFILE_NAME))
			state.profile_present_mask |= (uint32_t)(1u << state.profile_index);
		memcpy(s_kept_profiles, state.profiles, sizeof(s_kept_profiles));
		memcpy(s_kept_variants, state.saved_variants, sizeof(s_kept_variants)); s_kept_ready = 1;
		if (state.page != previous_page &&
			(previous_page == HCU_MAIN_MENU_PAGE_SAVE_VARIANT ||
			 previous_page == HCU_MAIN_MENU_PAGE_MODE_OPTIONS ||
			 previous_page == HCU_MAIN_MENU_PAGE_PLAYER_OPTIONS ||
			 previous_page == HCU_MAIN_MENU_PAGE_ITEM_OPTIONS ||
			 previous_page == HCU_MAIN_MENU_PAGE_INDICATOR_OPTIONS ||
			 previous_page == HCU_MAIN_MENU_PAGE_PROFILE_EDIT ||
			 previous_page == HCU_MAIN_MENU_PAGE_PROFILE_NAME ||
			 previous_page == HCU_MAIN_MENU_PAGE_CONTROLS ||
			 previous_page == HCU_MAIN_MENU_PAGE_SETTINGS))
			menu_storage_save(&state);
		s_menu_widescreen = state.widescreen != 0;
		packet2_reset(&packet, 0); video_add_setup_env(video, &packet);
		if (frame == 0) printf("HALO_PS2_LOCAL main-menu-frame stage=setup\n");
		{ static const u8 top[3] = {2,5,14}, horizon[3] = {5,10,23}; video_add_sky(video, &packet, top, horizon, 310); }
		menu_flat_state(&packet, video);
		/* Leave enough space in the fixed DMA packet for options and profiles. */
		menu_space_background(&packet, video, frame);
		menu_planet(&packet, video, frame);
		menu_ring(&packet, video, frame);
		switch (state.page) {
		case HCU_MAIN_MENU_PAGE_TITLE: menu_title(&packet, video, &state, frame); break;
		case HCU_MAIN_MENU_PAGE_CONNECT: menu_connect(&packet, video, &state, events); break;
		case HCU_MAIN_MENU_PAGE_LOBBY: menu_lobby(&packet, video, &state); break;
		case HCU_MAIN_MENU_PAGE_GAME_OPTIONS: menu_game_options(&packet, video, &state); break;
		case HCU_MAIN_MENU_PAGE_MODE_OPTIONS: menu_mode_options(&packet, video, &state); break;
		case HCU_MAIN_MENU_PAGE_PLAYER_OPTIONS: menu_player_options(&packet, video, &state); break;
		case HCU_MAIN_MENU_PAGE_ITEM_OPTIONS: menu_item_options(&packet, video, &state); break;
		case HCU_MAIN_MENU_PAGE_INDICATOR_OPTIONS: menu_indicator_options(&packet, video, &state); break;
		case HCU_MAIN_MENU_PAGE_SAVE_VARIANT: menu_save_variant(&packet, video, &state); break;
		case HCU_MAIN_MENU_PAGE_PROFILE_SELECT: menu_profile_select(&packet, video, &state); break;
		case HCU_MAIN_MENU_PAGE_PROFILE_EDIT: menu_profile_edit(&packet, video, &state); break;
		case HCU_MAIN_MENU_PAGE_PROFILE_NAME: menu_profile_name_edit(&packet, video, &state); break;
		case HCU_MAIN_MENU_PAGE_CONTROLS: menu_controls(&packet, video, &state); break;
		case HCU_MAIN_MENU_PAGE_VIDEO_SETTINGS: menu_video_settings(&packet, video, &state); break;
		default: menu_settings(&packet, video, &state); break;
		}
		if ((size_t)(packet.next - packet.base) >= MENU_PACKET_QW - 16u) {
			printf("HALO_PS2_FAIL main-menu packet full qwords=%u\n", (unsigned)(packet.next - packet.base));
			break;
		}
		if (frame == 0) printf("HALO_PS2_LOCAL main-menu-frame stage=built qwords=%u\n",
			(unsigned)(packet.next - packet.base));
		packet2_update(&packet, draw_finish(packet.next));
		if ((size_t)(packet.next - packet.base) > MENU_PACKET_QW) {
			printf("HALO_PS2_FAIL main-menu packet overflow qwords=%u\n", (unsigned)(packet.next - packet.base));
			action = HCU_MAIN_MENU_ACTION_MULTIPLAYER;
		}
		dma_channel_send_packet2(&packet, DMA_CHANNEL_GIF, 1);
		if (frame == 0) printf("HALO_PS2_LOCAL main-menu-frame stage=sent\n");
		dma_wait_fast();
		if (frame == 0) printf("HALO_PS2_LOCAL main-menu-frame stage=dma-done\n");
		draw_wait_finish();
		if (frame == 0) printf("HALO_PS2_LOCAL main-menu-frame stage=finish\n");
		video_present(video); ++frame;
		if (frame == 1) printf("HALO_PS2_LOCAL main-menu-frame stage=presented\n");
	}
#if defined(__mips__)
	menu_sound("sound\\music\\title1\\in", HCU_SOUND_EVENT_STOP, frame);
	menu_sound("sound\\music\\title1\\loops", HCU_SOUND_EVENT_LOOPING_STOP, frame);
#endif
	menu_storage_save(&state);
	if (action == HCU_MAIN_MENU_ACTION_MULTIPLAYER) {
		s_selected_session = state.session;
		s_selected_session.player_count = state.player_count;
		s_selected_session.widescreen = state.widescreen;
	}
	menu_ring_mesh_clear();
	arena_release(scratch, mark);
	printf("HALO_PS2_LOCAL main-menu-selected item=%s map=%s game=%s players=%u frames=%u\n",
		action == HCU_MAIN_MENU_ACTION_FIREFIGHT ? "firefight" : "multiplayer",
		s_maps[state.session.map], s_game_types[state.session.variant.game_type], state.player_count, frame);
	return action;
}

#endif
