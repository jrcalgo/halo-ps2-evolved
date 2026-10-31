#ifndef HCU_MAIN_MENU_H
#define HCU_MAIN_MENU_H

#include <stddef.h>
#include <stdint.h>

#define HCU_MAIN_MENU_PROFILE_COUNT 27
#define HCU_MAIN_MENU_PROFILE_NAME_LENGTH 12
#define HCU_MAIN_MENU_SAVED_VARIANT_COUNT 16
#define HCU_MAIN_MENU_MAP_COUNT 13
#define HCU_MAIN_MENU_GAME_TYPE_COUNT 6

enum hcu_main_menu_item {
	HCU_MAIN_MENU_MULTIPLAYER,
	HCU_MAIN_MENU_SETTINGS,
	HCU_MAIN_MENU_ITEM_COUNT
};

enum hcu_main_menu_page {
	HCU_MAIN_MENU_PAGE_TITLE,
	HCU_MAIN_MENU_PAGE_CONNECT,
	HCU_MAIN_MENU_PAGE_LOBBY,
	HCU_MAIN_MENU_PAGE_GAME_OPTIONS,
	HCU_MAIN_MENU_PAGE_MODE_OPTIONS,
	HCU_MAIN_MENU_PAGE_PLAYER_OPTIONS,
	HCU_MAIN_MENU_PAGE_ITEM_OPTIONS,
	HCU_MAIN_MENU_PAGE_INDICATOR_OPTIONS,
	HCU_MAIN_MENU_PAGE_SAVE_VARIANT,
	HCU_MAIN_MENU_PAGE_PROFILE_SELECT,
	HCU_MAIN_MENU_PAGE_PROFILE_EDIT,
	HCU_MAIN_MENU_PAGE_PROFILE_NAME,
	HCU_MAIN_MENU_PAGE_CONTROLS,
	HCU_MAIN_MENU_PAGE_SETTINGS,
	HCU_MAIN_MENU_PAGE_VIDEO_SETTINGS
};

enum hcu_main_menu_action {
	HCU_MAIN_MENU_ACTION_NONE,
	HCU_MAIN_MENU_ACTION_MULTIPLAYER,
	HCU_MAIN_MENU_ACTION_FIREFIGHT
};

enum hcu_main_menu_game_type {
	HCU_GAME_CTF,
	HCU_GAME_KING,
	HCU_GAME_SLAYER,
	HCU_GAME_ODDBALL,
	HCU_GAME_RACE,
	HCU_GAME_TEAM_SLAYER
};

typedef struct hcu_main_menu_profile {
	char name[HCU_MAIN_MENU_PROFILE_NAME_LENGTH + 1];
	uint8_t control_layout;
	uint8_t armor_color;
	uint8_t look_inverted;
	uint8_t look_sensitivity;
	uint8_t vibration;
} hcu_main_menu_profile;

typedef struct hcu_main_menu_variant {
	uint8_t valid;
	uint8_t game_type;
	/* Retail Halo CE game-type rules.  Values are spinner indices matching
	 * the choices stored by the Xbox UI rather than reduced on/off aliases. */
	uint8_t score_index;
	uint8_t teams;
	uint8_t ctf_assault;
	uint8_t ctf_single_flag;
	uint8_t ctf_flag_must_reset;
	uint8_t ctf_flag_at_home;
	uint8_t king_moving_hill;
	uint8_t slayer_death_bonus;
	uint8_t slayer_kill_in_order;
	uint8_t slayer_kill_penalty;
	uint8_t oddball_trait_with_ball;
	uint8_t oddball_trait_without_ball;
	uint8_t oddball_speed_with_ball;
	uint8_t oddball_ball_type;
	uint8_t oddball_random_start;
	uint8_t oddball_ball_count;
	uint8_t race_team_scoring;
	uint8_t race_type;

	/* Player options. */
	uint8_t lives;
	uint8_t maximum_health;
	uint8_t shields;
	uint8_t respawn_time;
	uint8_t respawn_growth;
	uint8_t odd_man_out;
	uint8_t invisible_players;
	uint8_t suicide_penalty;

	/* Item and indicator options. */
	uint8_t infinite_grenades;
	uint8_t vehicle_set;
	uint8_t weapon_set;
	uint8_t starting_equipment;
	uint8_t radar_display;
	uint8_t other_players_radar;
	uint8_t friends_on_screen;
} hcu_main_menu_variant;

typedef struct hcu_main_menu_session {
	uint8_t map;
	uint8_t variant_index;
	uint8_t player_count;
	uint8_t widescreen;
	hcu_main_menu_variant variant;
} hcu_main_menu_session;

typedef struct hcu_main_menu_state {
	uint8_t item;
	uint8_t page;
	uint8_t row;
	uint8_t profile_index;
	uint8_t name_cursor;
	uint8_t joined_mask;
	uint8_t guest_mask;
	uint8_t player_count;
	uint32_t profile_present_mask;
	uint8_t port_profile[4];

	/* Console-wide presentation settings. */
	uint8_t resolution;
	uint8_t animation_rate;
	uint8_t particles;
	uint8_t view_model;
	uint8_t terrain_detail;
	uint8_t widescreen;
	uint8_t hud_inset;
	uint8_t fps_counter;
	uint8_t subtitles;

	hcu_main_menu_profile profiles[HCU_MAIN_MENU_PROFILE_COUNT];
	hcu_main_menu_session session;
	/* Each profile owns its own saved game types on the memory card. */
	hcu_main_menu_variant saved_variants[HCU_MAIN_MENU_PROFILE_COUNT]
		[HCU_MAIN_MENU_SAVED_VARIANT_COUNT];
} hcu_main_menu_state;

void hcu_main_menu_state_init(hcu_main_menu_state *state);
enum hcu_main_menu_action hcu_main_menu_step(hcu_main_menu_state *state,
	int up, int down, int left, int right, int confirm, int back);
/* Creates the highlighted empty memory-card slot and opens its editor. */
int hcu_main_menu_create_profile(hcu_main_menu_state *state);
const char *hcu_main_menu_item_label(unsigned item);
const char *hcu_main_menu_map_label(unsigned map);
const char *hcu_main_menu_game_type_label(unsigned game_type);

/* RGB5A1 controller glyphs. Thirteen 16x16 cells in a 256x16 atlas, in order:
 * cross, circle, square, triangle, start, select, L1, L2, R1, R2, L3, R3, d-pad. */
#define HCU_MAIN_MENU_GLYPH_CELL 16u
#define HCU_MAIN_MENU_GLYPH_COUNT 13u
#define HCU_MAIN_MENU_GLYPH_ATLAS_W 256u
#define HCU_MAIN_MENU_GLYPH_ATLAS_H 16u

/* Rewrites button names in a footer or prompt as icon tags. Action words stay
 * text. Tags are [cross] [circle] [square] [triangle] [start] [select]
 * [l1] [l2] [r1] [r2] [l3] [r3] [dpad]. Returns 0, or -1 if the buffer is short. */
int hcu_main_menu_describe_prompt(const char *prompt, char *out, size_t out_size);

/* Copies the retail RGB5A1 landscape texture used by the ring's inner face. */
int hcu_main_menu_build_ring_texture(uint16_t *pixels, unsigned width,
	unsigned height);
/* Copies the retail RGB5A1 plated hull texture used by the ring's outer face. */
int hcu_main_menu_build_ring_outer_texture(uint16_t *pixels, unsigned width,
	unsigned height);

#ifdef _EE
#include "core/mem.h"
#include "platform/video.h"

/* Runs the interactive title and local-multiplayer setup screens. `dma_storage`
 * is borrowed only while the renderer is idle; scratch is restored on return. */
enum hcu_main_menu_action hcu_main_menu_run(video_t *video,
	void *dma_storage, size_t dma_bytes, arena_t *scratch);
/* Valid only after hcu_main_menu_run returns MULTIPLAYER. */
const hcu_main_menu_session *hcu_main_menu_selected_session(void);
#endif

#endif
