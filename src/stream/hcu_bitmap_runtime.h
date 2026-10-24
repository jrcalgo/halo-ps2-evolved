#ifndef HALO_STREAM_HCU_BITMAP_RUNTIME_H
#define HALO_STREAM_HCU_BITMAP_RUNTIME_H

#include "stream/hcu_bitmap_frame.h"

#ifdef __cplusplus
extern "C" {
#endif

#ifdef HCU_C3_RENDER_BUILT
extern hcu_bitmap_frame_owner hcu_c3_bitmap_frame_owner;
/* Detach the parent hooks after the real renderer fence, before clearing the
 * map's world/cache state. The profile owner is released later by CE. */
int hcu_c3_bitmap_frame_detach(void);
/* Called after CE has released the old profile at its map-released boundary. */
int hcu_c3_bitmap_map_released(void);
/* Reserve/initialize the map-local bitmap owner after bsp_render_set_world. */
int hcu_c3_bitmap_profile_prepare(void);
int hcu_c3_bitmap_map_bind(void);
#endif

#ifdef __cplusplus
}
#endif
#endif
