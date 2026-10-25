/* Diagnostic-only binding/layout test for the aligned 10 MiB MP candidate. */
#include "core/mem.h"
#include "cseries.h"
#include "cache/physical_memory_map.h"
#include "halo_ps2_limits.h"

#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#define CHARGED_STATIC_BSS 2114532u
#define TAG_BYTES 4477120u
#define BSP_BYTES 1993712u
#define MAP_BYTES (TAG_BYTES + BSP_BYTES)
#define TEXTURE_BYTES 4014928u
#define CANDIDATE_BYTES 10485760u
#define CLAIMS_BYTES 808856u

static unsigned char v2_backing[MEM_LAYOUT_V2_BYTES - CHARGED_STATIC_BSS +
	MEM_LAYOUT_V2_GUARDED_SLACK + 64u] __attribute__((aligned(64)));

boolean tag_validate_claims_buffer_ready(void) { return TRUE; }
boolean tag_validate_bind_claims_buffer(void *p, unsigned long n)
{ return p != NULL && n == CLAIMS_BYTES; }
void tag_validate_release_claims_buffer(void) {}
unsigned long tag_validate_claims_buffer_size(void) { return CLAIMS_BYTES; }
void *__real_malloc(unsigned long n) { (void)n; return NULL; }
void __real_free(void *p) { (void)p; }

static uintptr_t offset_of(const void *p, const void *base)
{
	assert((uintptr_t)p >= (uintptr_t)base);
	return (uintptr_t)p - (uintptr_t)base;
}

static void report_and_check_real_regions(void)
{
	mem_layout_v2_t layout;
	arena_t backing, *bsp, *texture;
	uintptr_t bsp_end, texture_base;
	arena_init(&backing, "production-v2-diagnostic", v2_backing,
		sizeof v2_backing);
	assert(mem_layout_v2_init_charged_guarded(&layout, &backing,
		CHARGED_STATIC_BSS, 0xA5u) == 0);
	bsp = mem_layout_v2_get(&layout, MEM_LAYOUT_V2_CURRENT_BSP);
	texture = mem_layout_v2_get(&layout, MEM_LAYOUT_V2_TEXTURE_CACHE);
	assert(bsp && texture);
	bsp_end = (uintptr_t)bsp->base + bsp->cap;
	texture_base = (uintptr_t)texture->base;
	assert(layout.guards[2] == (uint8_t *)bsp_end);
	assert(texture_base == (uintptr_t)layout.guards[2] + MEM_LAYOUT_V2_GUARD_BYTES);
	assert((uintptr_t)bsp->base % 16u == 0 && texture_base % 16u == 0);
	assert(texture_base - bsp_end == MEM_LAYOUT_V2_GUARD_BYTES);
	assert(bsp->cap == 6291456u && texture->cap == 4718592u);
	/* Aligned candidate spans could fit in the raw combined extent, but the
	 * map span crosses the current_bsp post-guard and borrows texture bytes.
	 * Production guarded arenas must not be treated as one span without an
	 * explicit recarve/reownership decision. */
	assert(MAP_BYTES + TEXTURE_BYTES == CANDIDATE_BYTES);
	assert(MAP_BYTES % 16u == 0 && TEXTURE_BYTES % 16u == 0);
	assert((uintptr_t)bsp->base + MAP_BYTES == texture_base + 179360u);
	assert((uintptr_t)bsp->base + CANDIDATE_BYTES ==
		texture_base + texture->cap - 16u);
	printf("candidate-v2-regions bsp_off=%lu bsp_cap=%u guard_after_bsp=%lu texture_off=%lu texture_cap=%u gap=%lu candidate_map_end_in_texture=%lu candidate_end_before_texture_end=%lu aligned=1\n",
		(unsigned long)offset_of(bsp->base, v2_backing), (unsigned)bsp->cap,
		(unsigned long)offset_of(layout.guards[2], v2_backing),
		(unsigned long)offset_of(texture->base, v2_backing),
		(unsigned)texture->cap, (unsigned long)(texture_base - bsp_end),
		(unsigned long)((uintptr_t)bsp->base + MAP_BYTES - texture_base),
		(unsigned long)(texture_base + texture->cap -
			((uintptr_t)bsp->base + CANDIDATE_BYTES)));
	assert(mem_layout_v2_guards_intact(&layout));
}

typedef struct candidate_guarded_layout {
	arena_t resident;
	arena_t combined_map_texture;
	arena_t tag;
	arena_t bsp;
	arena_t texture;
	arena_t dynamic;
	arena_t dma;
	arena_t streaming;
	arena_t checkpoint;
	arena_t audio;
	arena_t frame_scratch;
	uint8_t *guards[10];
	uint8_t guard_count;
	uint8_t *base;
	uint8_t *end;
} candidate_guarded_layout;

static void *candidate_guarded_region(arena_t *backing, size_t bytes,
	const char *name, size_t alignment, candidate_guarded_layout *candidate)
{
	uint8_t *span = arena_alloc(backing, bytes + MEM_LAYOUT_V2_GUARD_BYTES,
		alignment);
	(void)name;
	if (!span) return NULL;
	candidate->guards[candidate->guard_count++] = span + bytes;
	return span;
}

static void check_candidate_guards(const candidate_guarded_layout *candidate,
	uint8_t pattern)
{
	unsigned guard, byte;
	for (guard = 0; guard < candidate->guard_count; ++guard)
		for (byte = 0; byte < MEM_LAYOUT_V2_GUARD_BYTES; ++byte)
			assert(candidate->guards[guard][byte] == pattern);
}

/* Test-only variant: preserve total pool sizes but replace the independent
 * current_bsp + texture_cache allocations with one combined guarded owner. */
static void build_candidate_guarded_layout(candidate_guarded_layout *candidate)
{
	static const size_t region_bytes[MEM_LAYOUT_V2_REGION_COUNT] = {
		6815744u, 6291456u, 4718592u, 2621440u, 1179648u,
		1572864u, 524288u, 524288u, 393216u
	};
	static const char *region_names[MEM_LAYOUT_V2_REGION_COUNT] = {
		"resident_gameplay", "current_bsp+texture_cache",
		"texture_cache_view", "dynamic_simulation", "dma_commands",
		"streaming", "checkpoint", "audio", "frame_scratch"
	};
	arena_t backing;
	uint8_t *initial_guard;
	uint8_t *combined;
	size_t bytes;
	int i;
	memset(candidate, 0, sizeof *candidate);
	candidate->base = v2_backing;
	arena_init(&backing, "candidate-guarded-layout", v2_backing,
		sizeof v2_backing);
	initial_guard = arena_alloc(&backing, MEM_LAYOUT_V2_GUARD_BYTES, 16);
	assert(initial_guard);
	candidate->guards[candidate->guard_count++] = initial_guard;
	memset(initial_guard, 0xA5, MEM_LAYOUT_V2_GUARD_BYTES);
	for (i = 0; i < MEM_LAYOUT_V2_REGION_COUNT; ++i) {
		if (i == MEM_LAYOUT_V2_TEXTURE_CACHE)
			continue; /* the combined owner is carved at current_bsp */
		bytes = region_bytes[i];
		if (i == MEM_LAYOUT_V2_RESIDENT_GAMEPLAY)
			bytes -= CHARGED_STATIC_BSS;
		if (i == MEM_LAYOUT_V2_CURRENT_BSP)
			bytes = MAP_BYTES + TEXTURE_BYTES;
		if (i == MEM_LAYOUT_V2_RESIDENT_GAMEPLAY) {
			void *base = candidate_guarded_region(&backing, bytes,
				region_names[i], 16, candidate);
			assert(base);
			arena_init(&candidate->resident, region_names[i], base, bytes);
		} else if (i == MEM_LAYOUT_V2_CURRENT_BSP) {
			combined = candidate_guarded_region(&backing, bytes,
				region_names[i], 16, candidate);
			assert(combined);
			arena_init(&candidate->combined_map_texture, region_names[i],
				combined, bytes);
			arena_init(&candidate->tag, "tag_cache", combined, TAG_BYTES);
			arena_init(&candidate->bsp, "structure_bsp", combined + TAG_BYTES,
				BSP_BYTES);
			arena_init(&candidate->texture, "texture_cache",
				combined + MAP_BYTES, TEXTURE_BYTES);
		} else {
			arena_t *target = NULL;
			void *base = candidate_guarded_region(&backing, bytes,
				region_names[i], i == MEM_LAYOUT_V2_DMA_COMMANDS ? 64 : 16,
				candidate);
			assert(base);
			switch (i) {
			case MEM_LAYOUT_V2_DYNAMIC_SIMULATION: target = &candidate->dynamic; break;
			case MEM_LAYOUT_V2_DMA_COMMANDS: target = &candidate->dma; break;
			case MEM_LAYOUT_V2_STREAMING: target = &candidate->streaming; break;
			case MEM_LAYOUT_V2_CHECKPOINT: target = &candidate->checkpoint; break;
			case MEM_LAYOUT_V2_AUDIO: target = &candidate->audio; break;
			case MEM_LAYOUT_V2_FRAME_SCRATCH: target = &candidate->frame_scratch; break;
			default: assert(0); break;
			}
			arena_init(target, region_names[i], base, bytes);
		}
	}
	candidate->end = backing.base + backing.used;
	assert(candidate->guard_count == 9);
	assert((uintptr_t)candidate->tag.base % 16u == 0);
	assert((uintptr_t)candidate->bsp.base % 16u == 0);
	assert((uintptr_t)candidate->texture.base % 16u == 0);
	assert(candidate->tag.base + candidate->tag.cap == candidate->bsp.base);
	assert(candidate->bsp.base + candidate->bsp.cap == candidate->texture.base);
	assert(candidate->combined_map_texture.cap == CANDIDATE_BYTES);
	assert(candidate->tag.used == 0 && candidate->bsp.used == 0 &&
		candidate->texture.used == 0);
	for (i = 0; i < candidate->guard_count; ++i)
		memset(candidate->guards[i], 0xA5, MEM_LAYOUT_V2_GUARD_BYTES);
	assert(candidate->end <= backing.base + backing.cap);
	check_candidate_guards(candidate, 0xA5);
	printf("candidate-guarded-layout combined_off=%lu combined_bytes=%u "
		"tag=%u bsp=%u texture=%u guards=%u marks=zero aligned=16 "
		"status=passed\n", (unsigned long)(combined - candidate->base),
		CANDIDATE_BYTES, TAG_BYTES, BSP_BYTES, TEXTURE_BYTES,
		candidate->guard_count);
}

/* Prove the proposed ownership shape with one parent cursor before binding
 * provider views. The provider continues to receive fixed tag/BSP/texture
 * spans; this test-only cursor is not a production map-admission change. */
static void check_combined_map_texture_cursor(
	candidate_guarded_layout *candidate)
{
	arena_t *owner = &candidate->combined_map_texture;
	size_t mark = arena_mark(owner);
	void *tag, *bsp, *texture;
	size_t used_after_partition;
	assert(mark == 0);
	tag = arena_alloc(owner, TAG_BYTES, 16);
	bsp = arena_alloc(owner, BSP_BYTES, 16);
	texture = arena_alloc(owner, TEXTURE_BYTES, 16);
	assert(tag == candidate->tag.base);
	assert(bsp == candidate->bsp.base);
	assert(texture == candidate->texture.base);
	used_after_partition = arena_mark(owner);
	assert(used_after_partition == CANDIDATE_BYTES);
	assert((uint8_t *)tag + TAG_BYTES == (uint8_t *)bsp);
	assert((uint8_t *)bsp + BSP_BYTES == (uint8_t *)texture);
	assert((uint8_t *)texture + TEXTURE_BYTES == owner->base + owner->cap);
	/* Exhaustion is failure-atomic: the 10 MiB cap is not enlarged to hide
	 * the shortfall, and a rejected allocation cannot advance its cursor. */
	assert(arena_alloc(owner, 16, 16) == NULL);
	assert(arena_mark(owner) == used_after_partition);
	arena_release(owner, mark);
	assert(arena_mark(owner) == mark);
	assert(owner->high == CANDIDATE_BYTES);
	check_candidate_guards(candidate, 0xA5);
	printf("candidate-combined-cursor map=%u texture=%u used=%u cap=%u "
		"overflow=bounded rollback=zero high=%u guard=1 status=passed\n",
		MAP_BYTES, TEXTURE_BYTES, (unsigned)used_after_partition,
		(unsigned)owner->cap, (unsigned)owner->high);
}

static void bind_and_check_candidate_provider(candidate_guarded_layout *candidate)
{
	unsigned char *tag = candidate->tag.base;
	unsigned char *bsp = candidate->bsp.base;
	unsigned char *texture = candidate->texture.base;
	unsigned char *end = texture + TEXTURE_BYTES;
	void *game_state_ptr = arena_alloc(&candidate->resident,
		HALO_PORT_GAME_STATE_SIZE, 16);
	void *claims_ptr = arena_alloc(&candidate->resident, CLAIMS_BYTES, 16);
	void *sound_ptr = candidate->audio.base;
	void *dynamic_ptr = candidate->dynamic.base;
	size_t tag_mark = arena_mark(&candidate->tag);
	size_t bsp_mark = arena_mark(&candidate->bsp);
	size_t texture_mark = arena_mark(&candidate->texture);
	unsigned i;
	assert(game_state_ptr && claims_ptr);
	assert((uintptr_t)game_state_ptr >= (uintptr_t)candidate->resident.base);
	assert((uintptr_t)claims_ptr >= (uintptr_t)candidate->resident.base);
	assert((uint8_t *)claims_ptr + CLAIMS_BYTES <=
		candidate->resident.base + candidate->resident.cap);
	check_candidate_guards(candidate, 0xA5);
	assert((uintptr_t)tag % 16u == 0 && (uintptr_t)bsp % 16u == 0 &&
		(uintptr_t)texture % 16u == 0);
	assert((uintptr_t)bsp == (uintptr_t)tag + TAG_BYTES);
	assert((uintptr_t)texture == (uintptr_t)bsp + BSP_BYTES);
	assert((uintptr_t)end -
		(uintptr_t)candidate->combined_map_texture.base == CANDIDATE_BYTES);
	assert(physical_memory_bind_game_state(game_state_ptr, HALO_PORT_GAME_STATE_SIZE));
	assert(physical_memory_bind_tag_cache(tag, TAG_BYTES));
	assert(physical_memory_bind_structure_bsp_cache(bsp, BSP_BYTES));
	assert(physical_memory_bind_texture_cache(texture, TEXTURE_BYTES));
	assert(physical_memory_bind_sound_cache(sound_ptr, candidate->audio.cap));
	assert(physical_memory_bind_malloc_arena(dynamic_ptr, candidate->dynamic.cap));
	assert(physical_memory_bind_tag_validation_scratch(claims_ptr, CLAIMS_BYTES));
	physical_memory_allocate();
	assert(physical_memory_ready());
	assert(physical_memory_get_tag_cache_base_address() == tag &&
		physical_memory_get_tag_cache_size() == TAG_BYTES);
	assert(physical_memory_get_structure_bsp_cache_base_address() == bsp &&
		physical_memory_get_structure_bsp_cache_size() == BSP_BYTES);
	assert(physical_memory_get_texture_cache_base_address() == texture &&
		physical_memory_get_texture_cache_size() == TEXTURE_BYTES);
	assert((uintptr_t)physical_memory_get_tag_cache_base_address() + TAG_BYTES ==
		(uintptr_t)physical_memory_get_structure_bsp_cache_base_address());
	assert((uintptr_t)physical_memory_get_structure_bsp_cache_base_address() + BSP_BYTES ==
		(uintptr_t)physical_memory_get_texture_cache_base_address());
	assert(physical_memory_bind_texture_cache(texture + 8u, TEXTURE_BYTES) == 0);
	assert(tag_mark == 0 && bsp_mark == 0 && texture_mark == 0);
	assert(arena_alloc(&candidate->tag, 16, 16) == tag);
	assert(arena_alloc(&candidate->bsp, 16, 16) == bsp);
	assert(arena_alloc(&candidate->texture, 16, 16) == texture);
	arena_release(&candidate->tag, tag_mark);
	arena_release(&candidate->bsp, bsp_mark);
	arena_release(&candidate->texture, texture_mark);
	assert(candidate->tag.used == tag_mark && candidate->bsp.used == bsp_mark &&
		candidate->texture.used == texture_mark);
	check_candidate_guards(candidate, 0xA5);
	for (i = 0; i < MEM_LAYOUT_V2_GUARD_BYTES; ++i)
		assert(end[i] == 0xA5);
	printf("candidate-provider-bind tag=%u bsp=%u map=%u texture=%u total=%u "
		"claims=%u align=16 disjoint=1 ready=1 canaries=1 status=passed\n",
		TAG_BYTES, BSP_BYTES, MAP_BYTES, TEXTURE_BYTES,
		MAP_BYTES + TEXTURE_BYTES, CLAIMS_BYTES);
	physical_memory_free();
}

int main(void)
{
	candidate_guarded_layout candidate;
	assert(4477120u + 1993704u == 6470824u);
	assert((4477120u + 1993704u) % 16u == 8u);
	assert(TAG_BYTES + BSP_BYTES == 6470832u);
	assert(TEXTURE_BYTES == 4014928u);
	assert(TAG_BYTES + BSP_BYTES + TEXTURE_BYTES == CANDIDATE_BYTES);
	report_and_check_real_regions();
	build_candidate_guarded_layout(&candidate);
	check_combined_map_texture_cursor(&candidate);
	bind_and_check_candidate_provider(&candidate);
	return 0;
}
