#include <stdint.h>

/* Host fixtures that link ctag_map_source.c do not pull the GS loading screen.
 * The EE guest defines the real function in hcu_loading_screen.c. */
void hcu_loading_screen_file_read(uint32_t bytes)
{
	(void)bytes;
}
