#ifndef HCU_INGAME_OVERLAY_H
#define HCU_INGAME_OVERLAY_H

#include "render/text.h"

/* Select holds the retail scoreboard. Start opens the retail pause list
 * (RESUME GAME / LEAVE GAME) and stops the simulation until it closes. */
void hcu_ingame_overlay_draw(text_batch_t *tb, int view_w, int view_h,
	unsigned view_index, unsigned frame);

#endif
