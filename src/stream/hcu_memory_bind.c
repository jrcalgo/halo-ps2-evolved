#include "stream/hcu_memory_bind.h"

#include "cache/physical_memory_map.h"
#include "halo_ps2_limits.h"

#include <limits.h>
#include <stdint.h>

unsigned long tag_validate_claims_buffer_size(void);

static void restore_region_marks(mem_layout_v2_t *layout,
	const size_t marks[MEM_LAYOUT_V2_REGION_COUNT])
{
	int region;
	for (region = 0; region < MEM_LAYOUT_V2_REGION_COUNT; region++)
		layout->regions[region].used = marks[region];
}

int hcu_memory_bind_parent_v2(mem_layout_v2_t *layout,
	size_t tag_cache_bytes)
{
	arena_t *resident, *bsp, *texture, *dynamic, *audio;
	size_t marks[MEM_LAYOUT_V2_REGION_COUNT];
	void *game_state, *tag_cache, *claims;
	unsigned long claims_bytes;
	int region;

	if (!layout || tag_cache_bytes == 0 || tag_cache_bytes > ULONG_MAX)
		return -1;
	for (region = 0; region < MEM_LAYOUT_V2_REGION_COUNT; region++)
		marks[region] = layout->regions[region].used;

	resident = mem_layout_v2_get(layout, MEM_LAYOUT_V2_RESIDENT_GAMEPLAY);
	bsp = mem_layout_v2_get(layout, MEM_LAYOUT_V2_CURRENT_BSP);
	texture = mem_layout_v2_get(layout, MEM_LAYOUT_V2_TEXTURE_CACHE);
	dynamic = mem_layout_v2_get(layout, MEM_LAYOUT_V2_DYNAMIC_SIMULATION);
	audio = mem_layout_v2_get(layout, MEM_LAYOUT_V2_AUDIO);
	if (!resident || !bsp || !texture || !dynamic || !audio)
		return -1;

	/* Reserve tag ownership in one region. BSP and the other fixed stores each
	 * come from their named v2 region; no heap or reserve fallback exists. */
	/* The UI/bootstrap tag image takes the first part of current_bsp. The
	 * remaining BSP span stays disjoint; M2 must remeasure gameplay maps. */
	if (tag_cache_bytes >= bsp->cap || ((uintptr_t)bsp->base & 15u))
		return -1;
	game_state = arena_alloc(resident, HALO_PORT_GAME_STATE_SIZE, 16);
	tag_cache = game_state ? arena_alloc(bsp, tag_cache_bytes, 16) : NULL;
	if (!game_state || !tag_cache ||
		!physical_memory_bind_game_state(game_state,
			HALO_PORT_GAME_STATE_SIZE) ||
		!physical_memory_bind_tag_cache(tag_cache,
			(unsigned long)tag_cache_bytes) ||
		!physical_memory_bind_structure_bsp_cache(
			(uint8_t *)bsp->base + bsp->used,
			(unsigned long)(bsp->cap - bsp->used)) ||
		!physical_memory_bind_texture_cache(texture->base,
			(unsigned long)texture->cap) ||
		!physical_memory_bind_sound_cache(audio->base,
			(unsigned long)audio->cap) ||
		!physical_memory_bind_malloc_arena(dynamic->base,
			(unsigned long)dynamic->cap))
		goto fail;

	/* The real validator computes the bitmap extent from the now-configured
	 * tag+BSP stores. Keep it in resident_gameplay and disjoint from CE stores. */
	claims_bytes = tag_validate_claims_buffer_size();
	claims = claims_bytes ? arena_alloc(resident, claims_bytes, 16) : NULL;
	if (!claims || !physical_memory_bind_tag_validation_scratch(claims,
		claims_bytes))
		goto fail;

	return 0;

fail:
	/* This is a one-shot boot initializer. No CE allocations may exist yet, so
	 * releasing the provider is safe and makes a corrected retry deterministic. */
	physical_memory_free();
	restore_region_marks(layout, marks);
	return -1;
}
