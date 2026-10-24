/* Explicit, opt-in versioned capacities for the guarded map/render partition. */
#ifndef HALO_HCU_MEMORY_PROFILE_H
#define HALO_HCU_MEMORY_PROFILE_H

#include "core/mem.h"
#include <stddef.h>

#define HCU_MEMORY_PROFILE_VERSION_1 1u

typedef struct {
	unsigned version;
	size_t tag_cache_bytes;
	size_t structure_bsp_bytes;
	size_t render_texture_bytes;
	/* Whole 64 KiB residency slots for the map service's CE/CBSP segment arena.
	 * Zero means the profile has no residency span. */
	size_t residency_bytes;
} hcu_memory_profile_t;

/* Output of a successful bind, useful for accounting without double counting.
 * Each canary/alignment field is charged once to the named parent owner. */
typedef struct {
	void *tag_cache_base;
	void *structure_bsp_base;
	void *tag_bsp_guard;
	void *render_texture_base;
	void *claims_scratch_base;
	size_t map_parent_bytes;
	size_t render_parent_bytes;
	size_t tag_cache_bytes;
	size_t structure_bsp_bytes;
	size_t render_texture_bytes;
	size_t tag_bsp_guard_bytes;
	size_t map_render_guard_bytes;
	size_t bsp_alignment_bytes;
	size_t texture_alignment_bytes;
	size_t claims_scratch_bytes;
	void *residency_base;
	size_t residency_bytes;
	size_t residency_guard_bytes;
} hcu_memory_partition_t;

/* Validates the exact request against the untouched adjacent map/render span and
 * returns an address/cost plan without mutating it. */
int hcu_memory_profile_plan_v1(const mem_layout_v2_t *layout,
	const hcu_memory_profile_t *profile, hcu_memory_partition_t *partition);

/* Bind exact spans into CE before physical_memory_allocate(). The v2 BSP and
 * texture arenas are repartitioned in a trial layout and committed only after
 * all provider and claims-size checks succeed. */
int hcu_memory_bind_profile_v1(mem_layout_v2_t *layout,
	const hcu_memory_profile_t *profile, hcu_memory_partition_t *partition);

/* Runtime check for the exact owners and both nested and outer canaries. */
int hcu_memory_partition_guards_intact(const mem_layout_v2_t *layout,
	const hcu_memory_partition_t *partition);


/* Versioned production partition table (profile-v2): one row per measured
 * selectable map/matrix case, each a v1 profile whose map/render span is exactly
 * the 10 MiB backing minus its CE, BSP, guards and residency span (render, one
 * 16-byte guard, then the residency span at the top of the texture parent). Selected at a quiescent map
 * boundary before CE allocation; never rebound after allocate. */
#define HCU_MEMORY_PARTITION_TABLE_VERSION_2 2u

typedef struct {
	const char *name;
	hcu_memory_profile_t profile;
} hcu_memory_partition_entry_t;

/* Returns the row named exactly `name`, or NULL when the name is not in the
 * versioned table. Lookup is a linear scan of a fixed const table. */
const hcu_memory_profile_t *hcu_memory_partition_select_v2(const char *name);

/* Number of rows in the versioned table. */
unsigned hcu_memory_partition_count_v2(void);

/* Row by index, or NULL past the end. Used by the host and audit tests. */
const hcu_memory_partition_entry_t *hcu_memory_partition_entry_v2(unsigned index);

#endif
