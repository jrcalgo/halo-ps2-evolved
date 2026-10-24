#include "cseries.h"
#include "cache/physical_memory_map.h"
#include "core/mem.h"
#include "stream/hcu_memory_bind.h"

#include <assert.h>
#include <stdint.h>
#include <string.h>

void *__wrap_malloc(unsigned long size);
void *__wrap_calloc(unsigned long count, unsigned long size);
void *__stdcall GlobalAlloc(unsigned int flags, unsigned long size);
void *__stdcall LocalFree(void *pointer);

#define TEST_STATE_BYTES HALO_PORT_GAME_STATE_SIZE
#define TEST_TAG_BYTES 8192
#define TEST_BSP_BYTES 4096
#define TEST_TEXTURE_BYTES (512 * 1024)
#define TEST_SOUND_BYTES (512 * 1024)
#define TEST_MALLOC_BYTES (1024 * 1024)
#define TEST_ARENA_BYTES (8 * 1024 * 1024)
#define TEST_VALIDATOR_SCRATCH_BYTES (1024 * 1024)

static int validator_claims_ready = 1;
static unsigned long validator_claims_bytes = TEST_VALIDATOR_SCRATCH_BYTES;

boolean tag_validate_claims_buffer_ready(void)
{
	return validator_claims_ready;
}

unsigned long tag_validate_claims_buffer_size(void)
{
	return validator_claims_bytes;
}

boolean tag_validate_bind_claims_buffer(void *buffer, unsigned long buffer_size)
{
	if (!buffer || !buffer_size) return 0;
	validator_claims_ready = 1;
	return 1;
}

void tag_validate_release_claims_buffer(void)
{
	validator_claims_ready = 1;
}

static unsigned char arena[TEST_ARENA_BYTES] __attribute__((aligned(64)));
static unsigned char parent_layout_storage[MEM_LAYOUT_V2_BYTES + 64u]
	__attribute__((aligned(64)));
static unsigned char preboot_heap[1024] __attribute__((aligned(16)));
static size_t preboot_heap_used;
static unsigned real_heap_frees;

void *__real_malloc(unsigned long size)
{
	size_t aligned = ((size_t)size + 15u) & ~(size_t)15u;
	void *result;
	if (aligned > sizeof preboot_heap - preboot_heap_used) return NULL;
	result = preboot_heap + preboot_heap_used;
	preboot_heap_used += aligned;
	return result;
}

void __real_free(void *block)
{
	if (block >= (void *)preboot_heap &&
		block < (void *)(preboot_heap + sizeof preboot_heap))
		real_heap_frees++;
}

static void bind_all_regions(void)
{
	unsigned char *tag = arena + TEST_STATE_BYTES + 4096;
	unsigned char *bsp = tag + TEST_TAG_BYTES + 4096;
	unsigned char *texture = bsp + TEST_BSP_BYTES + 4096;
	unsigned char *sound = texture + TEST_TEXTURE_BYTES + 4096;
	unsigned char *heap = sound + TEST_SOUND_BYTES + 4096;
	assert((size_t)(heap - arena) + TEST_MALLOC_BYTES <= sizeof arena);
	assert(physical_memory_bind_game_state(arena, TEST_STATE_BYTES));
	assert(physical_memory_bind_tag_cache(tag, TEST_TAG_BYTES));
	assert(physical_memory_bind_structure_bsp_cache(bsp, TEST_BSP_BYTES));
	assert(physical_memory_bind_texture_cache(texture, TEST_TEXTURE_BYTES));
	assert(physical_memory_bind_sound_cache(sound, TEST_SOUND_BYTES));
	assert(physical_memory_bind_malloc_arena(heap, TEST_MALLOC_BYTES));
}

static void bind_parent_layout_regions(void)
{
	arena_t backing;
	mem_layout_v2_t layout;
	arena_t *resident;
	arena_t *current_bsp;
	size_t resident_mark;

	arena_init(&backing, "parent-v2", parent_layout_storage,
		MEM_LAYOUT_V2_BYTES + 64u);
	assert(mem_layout_v2_init(&layout, &backing) == 0);
	resident = mem_layout_v2_get(&layout, MEM_LAYOUT_V2_RESIDENT_GAMEPLAY);
	assert(resident);
	resident_mark = arena_mark(resident);
	assert(hcu_memory_bind_parent_v2(&layout, resident->cap) != 0);
	assert(arena_mark(resident) == resident_mark);
	assert(physical_memory_bind_tag_cache(arena, TEST_TAG_BYTES));
	physical_memory_free();

	/* Force claims-scratch exhaustion after the game/cache/BSP/texture/audio/
	 * dynamic stores have all been bound. The helper must clear every partial
	 * provider binding as well as restore the arena transaction. */
	arena_init(&backing, "parent-v2-retry", parent_layout_storage,
		MEM_LAYOUT_V2_BYTES + 64u);
	assert(mem_layout_v2_init(&layout, &backing) == 0);
	resident = mem_layout_v2_get(&layout, MEM_LAYOUT_V2_RESIDENT_GAMEPLAY);
	assert(resident);
	resident_mark = arena_mark(resident);
	validator_claims_bytes = resident->cap - TEST_STATE_BYTES + 16u;
	assert(hcu_memory_bind_parent_v2(&layout, 2u * 1024u * 1024u) != 0);
	assert(arena_mark(resident) == resident_mark);
	assert(physical_memory_bind_tag_cache(arena, TEST_TAG_BYTES));
	physical_memory_free();
	validator_claims_bytes = TEST_VALIDATOR_SCRATCH_BYTES;

	/* Retry from a fresh layout after both allocation and partial-bind failures. */
	arena_init(&backing, "parent-v2-final", parent_layout_storage,
		MEM_LAYOUT_V2_BYTES + 64u);
	assert(mem_layout_v2_init(&layout, &backing) == 0);
	resident = mem_layout_v2_get(&layout, MEM_LAYOUT_V2_RESIDENT_GAMEPLAY);
	assert(resident);
	assert(hcu_memory_bind_parent_v2(&layout, 2u * 1024u * 1024u) == 0);
	validator_claims_ready = 0;
	physical_memory_allocate();
	assert(!physical_memory_ready());
	/* The real validator computes readiness from the configured cache+BSP
	 * spans; the memory provider holds shell startup until that check passes. */
	validator_claims_ready = 1;
	assert(physical_memory_ready());
	assert(physical_memory_get_game_state_base_address() != NULL);
	assert(physical_memory_get_tag_cache_base_address() != NULL);
	assert(physical_memory_get_structure_bsp_cache_base_address() != NULL);
	assert(physical_memory_get_structure_bsp_cache_size() == 4194304u);
	assert(mem_layout_v2_get(&layout, MEM_LAYOUT_V2_CURRENT_BSP)->used ==
		2u * 1024u * 1024u);
	assert(physical_memory_get_texture_cache_base_address() != NULL);
	assert(physical_memory_get_texture_cache_size() == 4194304u);
	assert(physical_memory_get_sound_cache_base_address() != NULL);
	assert(physical_memory_get_sound_cache_size() == 524288u);
	assert(physical_memory_get_malloc_arena_size() == 2621440u);
	physical_memory_free();

	/* Exercise the proposed boot-fixed Longest/Blood-Gulch candidate split.
	 * This is layout/binder evidence, not a measured retail map fit: the claims
	 * provider is still a fixture, while capacities come from the retail audit. */
	validator_claims_bytes = 786432u; /* (6 MiB tag+BSP address space) / 8 */
	arena_init(&backing, "parent-v2-retail-split", parent_layout_storage,
		MEM_LAYOUT_V2_BYTES + 64u);
	assert(mem_layout_v2_init(&layout, &backing) == 0);
	resident = mem_layout_v2_get(&layout, MEM_LAYOUT_V2_RESIDENT_GAMEPLAY);
	current_bsp = mem_layout_v2_get(&layout, MEM_LAYOUT_V2_CURRENT_BSP);
	assert(resident && current_bsp);
	assert(hcu_memory_bind_parent_v2(&layout, 4477120u) == 0);
	assert(physical_memory_get_tag_cache_size() == 4477120u);
	assert(physical_memory_get_structure_bsp_cache_size() == 1814336u);
	assert(physical_memory_bind_tag_cache(parent_layout_storage, 4096u) == 0);
	physical_memory_allocate();
	assert(physical_memory_ready());
	assert((uintptr_t)physical_memory_get_tag_cache_base_address() + 4477120u ==
		(uintptr_t)physical_memory_get_structure_bsp_cache_base_address());
	assert((uintptr_t)physical_memory_get_structure_bsp_cache_base_address() + 1814336u ==
		(uintptr_t)current_bsp->base + current_bsp->cap);
	assert(!physical_memory_bind_tag_cache(parent_layout_storage, 4096u));
	assert(physical_memory_get_tag_cache_size() == 4477120u);
	assert(physical_memory_get_structure_bsp_cache_size() == 1814336u);
	physical_memory_free();
	validator_claims_bytes = TEST_VALIDATOR_SCRATCH_BYTES;

	/* The combined image charges its NOBITS bytes to resident_gameplay and
	 * carves only the remaining budget from the boot backing allocation. */
	arena_init(&backing, "parent-v2-charged", parent_layout_storage,
		MEM_LAYOUT_V2_BYTES - 2056200u + 64u);
	assert(mem_layout_v2_init_charged(&layout, &backing, 6815745u) != 0);
	assert(backing.used == 0);
	assert(mem_layout_v2_init_charged(&layout, &backing, 2056200u) == 0);
	resident = mem_layout_v2_get(&layout, MEM_LAYOUT_V2_RESIDENT_GAMEPLAY);
	assert(resident->cap == 6815744u - 2056200u);
	assert(hcu_memory_bind_parent_v2(&layout, 2u * 1024u * 1024u) == 0);
	physical_memory_allocate();
	assert(physical_memory_ready());
	assert(physical_memory_get_structure_bsp_cache_size() == 4194304u);
	physical_memory_free();
}

int main(void)
{
	unsigned char *tag = arena + TEST_STATE_BYTES + 4096;
	unsigned char *bsp = tag + TEST_TAG_BYTES + 4096;
	unsigned char *texture = bsp + TEST_BSP_BYTES + 4096;
	unsigned char *sound = texture + TEST_TEXTURE_BYTES + 4096;
	unsigned char *heap = sound + TEST_SOUND_BYTES + 4096;
	unsigned char *allocation;
	unsigned char *zeroed;
	void *startup_allocation;

	assert(!physical_memory_ready());
	/* PS2SDK libcglue reaches malloc before the machine entry can bind CE's
	 * fixed dynamic arena. Such short-lived startup storage must use the SDK
	 * heap, and free must return it there rather than treating it as CE memory. */
	startup_allocation = __wrap_malloc(17);
	assert(startup_allocation == preboot_heap);
	__wrap_free(startup_allocation);
	assert(real_heap_frees == 1);
#ifndef HALO_PS2_NO_BOOTSTRAP_MEMORY
	assert(physical_memory_get_tag_cache_size() == 2u * 1024u * 1024u);
	physical_memory_allocate();
	assert(physical_memory_ready());
	assert(physical_memory_get_structure_bsp_cache_base_address() == NULL);
	physical_memory_free();
	assert(physical_memory_bind_tag_validation_scratch(tag, TEST_TAG_BYTES));
	assert(!physical_memory_bind_tag_cache(tag, TEST_TAG_BYTES));
	physical_memory_free();
#else
	assert(physical_memory_get_tag_cache_size() == 0);
	physical_memory_allocate();
	assert(!physical_memory_ready());
	physical_memory_free();
#endif

	/* All caller-owned stores require aligned, nonempty, bounded, disjoint spans. */
	assert(!physical_memory_bind_game_state(NULL, TEST_STATE_BYTES));
	assert(!physical_memory_bind_game_state(arena + 1, TEST_STATE_BYTES));
	assert(!physical_memory_bind_game_state(arena, TEST_STATE_BYTES - 1));
	assert(!physical_memory_bind_game_state(
		(void *)(uintptr_t)(UINTPTR_MAX - 15u), TEST_STATE_BYTES));
	assert(!physical_memory_bind_tag_cache(tag, 0));
	assert(!physical_memory_bind_tag_cache(tag + 1, TEST_TAG_BYTES));
	assert(!physical_memory_bind_sound_cache(NULL, TEST_SOUND_BYTES));
	assert(!physical_memory_bind_malloc_arena(arena, 32u * 1024u * 1024u + 16u));
	assert(physical_memory_bind_game_state(arena, TEST_STATE_BYTES));
	assert(physical_memory_bind_tag_cache(tag, TEST_TAG_BYTES));
	assert(!physical_memory_bind_structure_bsp_cache(tag + 2048, TEST_BSP_BYTES));
	assert(!physical_memory_bind_texture_cache(tag, TEST_TEXTURE_BYTES));
	assert(physical_memory_bind_structure_bsp_cache(bsp, TEST_BSP_BYTES));
	assert(physical_memory_bind_texture_cache(texture, TEST_TEXTURE_BYTES));
	assert(physical_memory_bind_sound_cache(sound, TEST_SOUND_BYTES));
	assert(physical_memory_bind_malloc_arena(heap, TEST_MALLOC_BYTES));
	assert(!physical_memory_bind_tag_validation_scratch(tag, TEST_TAG_BYTES));
	assert(physical_memory_get_tag_cache_size() == TEST_TAG_BYTES);
	assert(physical_memory_bind_tag_cache(tag, TEST_TAG_BYTES) == 0);
	physical_memory_allocate();
	assert(physical_memory_ready());
	assert(physical_memory_get_game_state_base_address() == arena);
	assert(physical_memory_get_game_state_size() == TEST_STATE_BYTES);
	assert(physical_memory_get_tag_cache_base_address() == tag);
	assert(physical_memory_get_tag_cache_size() == TEST_TAG_BYTES);
	assert(physical_memory_get_structure_bsp_cache_base_address() == bsp);
	assert(physical_memory_get_structure_bsp_cache_size() == TEST_BSP_BYTES);
	assert(physical_memory_get_texture_cache_base_address() == texture);
	assert(physical_memory_get_texture_cache_size() == TEST_TEXTURE_BYTES);
	assert(physical_memory_get_sound_cache_base_address() == sound);
	assert(physical_memory_get_sound_cache_size() == TEST_SOUND_BYTES);
	assert(physical_memory_get_malloc_arena_size() == TEST_MALLOC_BYTES);
	/* The backing contract is frozen once CE can retain pointers into it. */
	assert(!physical_memory_bind_tag_cache(tag, TEST_TAG_BYTES));
	assert(!physical_memory_bind_texture_cache(arena, TEST_TEXTURE_BYTES));

	allocation = __wrap_malloc(17);
	assert(allocation == heap);
	assert(((uintptr_t)allocation & 15u) == 0);
	__wrap_free(allocation);
	assert(real_heap_frees == 1);
	memset(allocation, 0xA5, 17);
	zeroed = __wrap_calloc(8, 4);
	assert(zeroed == heap + 32);
	for (allocation = zeroed; allocation < zeroed + 32; allocation++)
		assert(*allocation == 0);
	assert(__wrap_malloc(TEST_MALLOC_BYTES) == NULL);

	/* Allocation freezes ownership; free clears every binding for the next boot. */
	physical_memory_allocate(); /* idempotent; must not reset heap allocations */
	assert(__wrap_malloc(16) == heap + 64);
	physical_memory_free();
	assert(!physical_memory_ready());
	assert(__wrap_malloc(16) == NULL);
	assert(physical_memory_get_game_state_base_address() == NULL);
	assert(physical_memory_get_tag_cache_base_address() == NULL);
	assert(physical_memory_get_structure_bsp_cache_base_address() == NULL);
	assert(physical_memory_get_texture_cache_base_address() == NULL);
	assert(physical_memory_get_sound_cache_base_address() == NULL);
	bind_all_regions();
	physical_memory_allocate();
	assert(physical_memory_ready());
	allocation = GlobalAlloc(0, 17);
	assert(allocation == heap);
	assert(LocalFree(allocation) == NULL);
	zeroed = GlobalAlloc(0x40u, 16);
	assert(zeroed == heap + 32);
	for (allocation = zeroed; allocation < zeroed + 16; allocation++)
		assert(*allocation == 0);
	physical_memory_free();
	bind_parent_layout_regions();
	return 0;
}
