/* Focused runtime fixture for the real parent binder's MP candidate spans. */
#include "cseries.h"
#include "core/mem.h"
#include "cache/physical_memory_map.h"
#include "halo_ps2_limits.h"
#include "stream/hcu_memory_bind.h"

#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#define TAG_BYTES 4477120u
#define BSP_BYTES 1993712u
#define MAP_BYTES (TAG_BYTES + BSP_BYTES)
#define TEXTURE_BYTES 4014928u
#define CURRENT_BSP_BYTES 6291456u
#define CURRENT_TEXTURE_BYTES 4194304u
#define CLAIMS_BYTES 808856u

static uint8_t backing_bytes[MEM_LAYOUT_V2_BYTES +
	MEM_LAYOUT_V2_GUARDED_SLACK + 64u] __attribute__((aligned(64)));

boolean tag_validate_claims_buffer_ready(void) { return TRUE; }
boolean tag_validate_bind_claims_buffer(void *base, unsigned long bytes)
{ return base != NULL && bytes == CLAIMS_BYTES; }
void tag_validate_release_claims_buffer(void) {}
unsigned long tag_validate_claims_buffer_size(void) { return CLAIMS_BYTES; }
void *__real_malloc(unsigned long bytes) { (void)bytes; return NULL; }
void __real_free(void *base) { (void)base; }

static void fresh_guarded_layout(mem_layout_v2_t *layout, arena_t *backing)
{
	arena_init(backing, "production-binder-test", backing_bytes,
		sizeof(backing_bytes));
	assert(mem_layout_v2_init_charged_guarded(layout, backing, 0, 0xA5u) == 0);
}

/* Reproduce the opt-in candidate carve in hcu_main.c against a fresh layout.
 * The source-audit runner below ties this arithmetic to that gated code. */
static void candidate_recarve(mem_layout_v2_t *layout)
{
	arena_t *bsp = mem_layout_v2_get(layout, MEM_LAYOUT_V2_CURRENT_BSP);
	arena_t *texture = mem_layout_v2_get(layout, MEM_LAYOUT_V2_TEXTURE_CACHE);
	uint8_t *combined_end;
	assert(bsp && texture && bsp->cap == CURRENT_BSP_BYTES);
	assert(texture->cap == CURRENT_TEXTURE_BYTES);
	assert(texture->base == layout->guards[2] + MEM_LAYOUT_V2_GUARD_BYTES);
	assert(MAP_BYTES + TEXTURE_BYTES ==
		CURRENT_BSP_BYTES + CURRENT_TEXTURE_BYTES);
	combined_end = bsp->base + MAP_BYTES + TEXTURE_BYTES;
	assert(combined_end <= texture->base + texture->cap -
		MEM_LAYOUT_V2_GUARD_BYTES);
	bsp->cap = MAP_BYTES;
	texture->base = bsp->base + MAP_BYTES;
	texture->cap = TEXTURE_BYTES;
	layout->guards[2] = combined_end;
	layout->guards[3] = combined_end;
	memset(combined_end, layout->guard_pattern, MEM_LAYOUT_V2_GUARD_BYTES);
}

static void test_default_layout_is_short_and_noncontiguous(void)
{
	arena_t backing;
	mem_layout_v2_t layout;
	arena_t *bsp, *texture;
	unsigned long actual_bsp, actual_texture;
	fresh_guarded_layout(&layout, &backing);
	bsp = mem_layout_v2_get(&layout, MEM_LAYOUT_V2_CURRENT_BSP);
	texture = mem_layout_v2_get(&layout, MEM_LAYOUT_V2_TEXTURE_CACHE);
	assert(bsp && texture);
	assert(hcu_memory_bind_parent_v2(&layout, TAG_BYTES) == 0);
	physical_memory_allocate();
	assert(physical_memory_ready());
	actual_bsp = physical_memory_get_structure_bsp_cache_size();
	actual_texture = physical_memory_get_texture_cache_size();
	assert(physical_memory_get_tag_cache_size() == TAG_BYTES);
	assert(actual_bsp == CURRENT_BSP_BYTES - TAG_BYTES);
	assert(actual_bsp == 1814336u);
	assert(actual_bsp < BSP_BYTES);
	assert(BSP_BYTES - actual_bsp == 179376u);
	assert(actual_texture == CURRENT_TEXTURE_BYTES);
	assert((uint8_t *)physical_memory_get_structure_bsp_cache_base_address() +
		actual_bsp == bsp->base + bsp->cap);
	assert((uint8_t *)physical_memory_get_texture_cache_base_address() ==
		texture->base);
	assert(texture->base == bsp->base + CURRENT_BSP_BYTES +
		MEM_LAYOUT_V2_GUARD_BYTES);
	assert(mem_layout_v2_guards_intact(&layout));
	printf("production-binder-default tag=%u bsp=%lu required_bsp=%u "
		"bsp_shortfall=%u texture=%lu gap=%u ready=1 candidate_fit=0\n",
		TAG_BYTES, actual_bsp, BSP_BYTES, BSP_BYTES - (unsigned)actual_bsp,
		actual_texture, MEM_LAYOUT_V2_GUARD_BYTES);
	physical_memory_free();
}

static void test_existing_opt_in_recarve_binds_candidate_spans(void)
{
	arena_t backing;
	mem_layout_v2_t layout;
	arena_t *bsp, *texture;
	uint8_t *tag_base, *bsp_base, *texture_base;
	size_t parent_used;
	fresh_guarded_layout(&layout, &backing);
	parent_used = backing.used;
	bsp = mem_layout_v2_get(&layout, MEM_LAYOUT_V2_CURRENT_BSP);
	texture = mem_layout_v2_get(&layout, MEM_LAYOUT_V2_TEXTURE_CACHE);
	assert(bsp && texture);
	candidate_recarve(&layout);
	assert(backing.used == parent_used);
	assert(hcu_memory_bind_parent_v2(&layout, TAG_BYTES) == 0);
	physical_memory_allocate();
	assert(physical_memory_ready());
	tag_base = physical_memory_get_tag_cache_base_address();
	bsp_base = physical_memory_get_structure_bsp_cache_base_address();
	texture_base = physical_memory_get_texture_cache_base_address();
	assert(physical_memory_get_tag_cache_size() == TAG_BYTES);
	assert(physical_memory_get_structure_bsp_cache_size() == BSP_BYTES);
	assert(physical_memory_get_texture_cache_size() == TEXTURE_BYTES);
	assert((uint8_t *)bsp_base == tag_base + TAG_BYTES);
	assert((uint8_t *)texture_base == bsp_base + BSP_BYTES);
	assert((uint8_t *)texture_base ==
		bsp->base + MAP_BYTES);
	assert((uint8_t *)texture_base + TEXTURE_BYTES ==
		bsp->base + MAP_BYTES + TEXTURE_BYTES);
	assert(texture->base == texture_base && texture->cap == TEXTURE_BYTES);
	assert(bsp->cap + texture->cap ==
		CURRENT_BSP_BYTES + CURRENT_TEXTURE_BYTES);
	assert(mem_layout_v2_guards_intact(&layout));
	printf("production-binder-recarved tag=%u bsp=%u map=%u texture=%u "
		"total=%u contiguous_views=1 parent_bytes_unchanged=1 guards=1 "
		"ready=1\n", TAG_BYTES, BSP_BYTES, MAP_BYTES, TEXTURE_BYTES,
		MAP_BYTES + TEXTURE_BYTES);
	physical_memory_free();
}

int main(void)
{
	test_default_layout_is_short_and_noncontiguous();
	test_existing_opt_in_recarve_binds_candidate_spans();
	return 0;
}
