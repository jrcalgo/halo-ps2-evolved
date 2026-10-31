#ifndef HCU_LOADING_SCREEN_H
#define HCU_LOADING_SCREEN_H

#include <stddef.h>
#include <stdint.h>
/* Keep CE closure builds independent of the viewer's platform headers. */
void hcu_loading_screen_bind(void *video, void *dma_storage,
	size_t dma_bytes);
/* Start/stop a blocking CE map or startup load. Read progress is fed from
 * the PS2 file layer, so long cache/package reads can present intermediate
 * frames without changing CE's synchronous map ownership rules. */
void hcu_loading_screen_begin(void);
void hcu_loading_screen_end(void);
void hcu_loading_screen_file_read(uint32_t bytes);
/* Keep the screen up after CE's progress_bar_end until hcu_loading_screen_release.
 * The chained gameplay image still binds textures and builds the BSP renderer
 * after CE considers the map loaded. */
void hcu_loading_screen_hold(void);
void hcu_loading_screen_release(void);

#endif
