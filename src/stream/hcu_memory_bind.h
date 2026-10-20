/* Parent fixed-region to HCU PS2 memory-provider bridge. */
#ifndef HALO_HCU_MEMORY_BIND_H
#define HALO_HCU_MEMORY_BIND_H

#include "core/mem.h"

#include <stddef.h>

/* Bind every HCU backing store to budget-v2 arenas before
 * physical_memory_allocate(). tag_cache_bytes is an explicit measured choice;
 * this function does not claim that any retail map fits that capacity. The
 * caller must invoke this once during fresh machine startup, before CE owns
 * pointers into any of these spans. On failure, provider bindings and arena
 * cursors are rolled back to their entry state. */
int hcu_memory_bind_parent_v2(mem_layout_v2_t *layout,
	size_t tag_cache_bytes);

#endif
