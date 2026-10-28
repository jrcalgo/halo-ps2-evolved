#ifndef HCU_MAIN_MENU_H
#define HCU_MAIN_MENU_H

#include <stddef.h>
#include <stdint.h>

enum hcu_main_menu_item {
	HCU_MAIN_MENU_MULTIPLAYER,
	HCU_MAIN_MENU_FIREFIGHT,
	HCU_MAIN_MENU_CONTROLS,
	HCU_MAIN_MENU_SETTINGS,
	HCU_MAIN_MENU_ITEM_COUNT
};

enum hcu_main_menu_page {
	HCU_MAIN_MENU_PAGE_TITLE,
	HCU_MAIN_MENU_PAGE_CONTROLS,
	HCU_MAIN_MENU_PAGE_SETTINGS
};

enum hcu_main_menu_action {
	HCU_MAIN_MENU_ACTION_NONE,
	HCU_MAIN_MENU_ACTION_MULTIPLAYER,
	HCU_MAIN_MENU_ACTION_FIREFIGHT
};

typedef struct hcu_main_menu_state {
	uint8_t item;
	uint8_t page;
	uint8_t settings_row;
	uint8_t widescreen;
	uint8_t vibration;
} hcu_main_menu_state;

void hcu_main_menu_state_init(hcu_main_menu_state *state);
enum hcu_main_menu_action hcu_main_menu_step(hcu_main_menu_state *state,
	int up, int down, int left, int right, int confirm, int back);
const char *hcu_main_menu_item_label(unsigned item);

/* Deterministic RGB5A1 terrain/cloud texture used by the title ring. */
int hcu_main_menu_build_ring_texture(uint16_t *pixels, unsigned width,
	unsigned height);

#ifdef _EE
#include "core/mem.h"
#include "platform/video.h"

/* Runs the interactive title screen. `dma_storage` is borrowed only while the
 * renderer is idle; scratch is restored to its entry mark before return. */
enum hcu_main_menu_action hcu_main_menu_run(video_t *video,
	void *dma_storage, size_t dma_bytes, arena_t *scratch);
#endif

#endif
