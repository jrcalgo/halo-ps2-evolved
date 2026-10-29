/* Host checks for the audited halo-ps2 arena. Output is explicit integers only. */
#include "core/mem.h"
#include <stdint.h>
#include <stdio.h>
#include <string.h>

static int g_failures;
static unsigned char g_layout_storage[MEM_LAYOUT_V2_BYTES + 64u]
	__attribute__((aligned(64)));

static void expect(const char *name, int pass)
{
	printf("  {\"check\":\"%s\",\"pass\":%s},\n", name, pass ? "true" : "false");
	if (!pass)
		g_failures++;
}

static int release_checked(arena_t *arena, size_t mark, size_t *used_after)
{
	size_t before = arena->used;
	if (mark > before)
		return -1;
	arena_release(arena, mark);
	*used_after = arena->used;
	return mark <= before && arena->used == mark ? 0 : -1;
}

static mem_layout_v2_t g_layout;

static void test_memory_layout_v2(void)
{
	static const size_t expected[MEM_LAYOUT_V2_REGION_COUNT] = {
		6815744u, 6291456u, 6815744u, 2621440u, 1179648u,
		1572864u, 524288u, 524288u, 393216u
	};
	static const char *names[MEM_LAYOUT_V2_REGION_COUNT] = {
		"resident_gameplay", "current_bsp", "texture_cache",
		"dynamic_simulation", "dma_commands", "streaming", "checkpoint",
		"audio", "frame_scratch"
	};
	arena_t backing, too_small;
	mem_layout_v2_t untouched, before;
	int i, contiguous = 1;

	memset(&g_layout, 0xA5, sizeof g_layout);
	untouched = g_layout;
	arena_init(&too_small, "short", g_layout_storage + 1,
		MEM_LAYOUT_V2_BYTES);
	expect("v2-layout-reject-short-backing", mem_layout_v2_init(&g_layout, &too_small) == -1);
	expect("v2-layout-failure-is-atomic", too_small.used == 0 && too_small.high == 0 &&
		memcmp(&g_layout, &untouched, sizeof g_layout) == 0);

	arena_init(&backing, "ee-managed", g_layout_storage + 1,
		MEM_LAYOUT_V2_BYTES + 63u);
	expect("v2-layout-exact-capacity", mem_layout_v2_init(&g_layout, &backing) == 0 &&
		backing.used == MEM_LAYOUT_V2_BYTES + 63u);
	for (i = 0; i < MEM_LAYOUT_V2_REGION_COUNT; i++) {
		const arena_t *region = mem_layout_v2_get_const(&g_layout,
			(mem_layout_v2_region_t)i);
		if (!region || region->cap != expected[i] ||
			((uintptr_t)region->base & 15u) != 0 || region->used != 0 ||
			strcmp(region->name, names[i]) != 0)
			contiguous = 0;
		if (i > 0) {
			uintptr_t previous_end = (uintptr_t)g_layout.regions[i - 1].base +
				g_layout.regions[i - 1].cap;
			uintptr_t current = (uintptr_t)g_layout.regions[i].base;
			if (current < previous_end ||
				(i != MEM_LAYOUT_V2_DMA_COMMANDS && current != previous_end) ||
				(i == MEM_LAYOUT_V2_DMA_COMMANDS &&
					(current - previous_end > 63u || (current & 63u) != 0u)))
				contiguous = 0;
		}
	}
	expect("v2-layout-names-capacities-and-aligned-disjoint-order", contiguous);
	expect("v2-layout-invalid-region-rejected",
		mem_layout_v2_get(&g_layout, (mem_layout_v2_region_t)-1) == NULL &&
		mem_layout_v2_get_const(&g_layout, MEM_LAYOUT_V2_REGION_COUNT) == NULL);
	before = g_layout;
	expect("v2-layout-second-carve-fails-atomically",
		mem_layout_v2_init(&g_layout, &backing) == -1 &&
		backing.used == MEM_LAYOUT_V2_BYTES + 63u &&
		memcmp(&g_layout, &before, sizeof g_layout) == 0);
}

int main(void)
{
	unsigned char storage[256];
	unsigned char tiny[32];
	arena_t arena;
	arena_t child;
	arena_t overflow;
	arena_t invalid_base;
	arena_t address_overflow;
	void *aligned;
	void *rejected;
	size_t mark;
	size_t used_after = 0;
	size_t high_before_reset;
	uintptr_t address;
	int i;

	memset(storage, 0x5a, sizeof storage);
	arena_init(&arena, "fixture", storage, sizeof storage);
	printf("{\n \"abi\":{\"pointer\":%u,\"size\":%u},\n \"checks\":[\n",
	       (unsigned)sizeof(void *), (unsigned)sizeof(size_t));
	expect("reject-null-arena", arena_alloc(NULL, 1, 1) == NULL);
	arena_init(&invalid_base, "null-base", NULL, 16);
	expect("reject-null-base", arena_alloc(&invalid_base, 1, 1) == NULL &&
		invalid_base.used == 0 && invalid_base.failed_allocations == 1);
	arena_init(&address_overflow, "address-overflow",
		(void *)(uintptr_t)(UINTPTR_MAX - 7u), 32);
	expect("reject-address-range-overflow",
		arena_alloc(&address_overflow, 1, 16) == NULL &&
		address_overflow.used == 0 && address_overflow.high == 0 &&
		address_overflow.failed_allocations == 1);

	aligned = arena_alloc(&arena, 1, 16);
	address = (uintptr_t)aligned;
	expect("align-16", aligned != NULL && (address % 16u) == 0);
	expect("reject-non-power-alignment", arena_alloc(&arena, 1, 3) == NULL);
	expect("reject-zero-alignment", arena_alloc(&arena, 1, 0) == NULL);
	expect("allocation-failures-counted",
		arena.failed_allocations == 2);

	mark = arena_mark(&arena);
	expect("scratch-alloc", arena_alloc(&arena, 8, 1) != NULL);
	expect("lifetime-future-mark", release_checked(&arena, arena.used + 1, &used_after) == -1);
	arena_release(&arena, arena.used + 1);
	expect("lifetime-used-unchanged", arena.used == mark + 8);
	expect("scratch-release", release_checked(&arena, mark, &used_after) == 0 && used_after == mark);
	expect("release-counters",
		arena.release_count == 1 && arena.invalid_releases == 1);

	high_before_reset = arena.high;
	arena_reset(&arena);
	expect("scratch-reset", arena.used == 0 && arena.high == high_before_reset &&
		arena.reset_count == 1);

	rejected = arena_alloc(&arena, sizeof storage + 1, 1);
	expect("exhaustion", rejected == NULL && arena.used == 0);
	expect("occupy-one", arena_alloc(&arena, 16, 1) != NULL);
	expect("sub-arena-exhaustion", arena_sub(&child, &arena, "child", sizeof storage) == -1);
	expect("exhaustion-counter", arena.failed_allocations == 4);

	arena_init(&overflow, "overflow", tiny, sizeof tiny);
	expect("size-overflow", arena_alloc(&overflow, SIZE_MAX, 1) == NULL &&
		overflow.used == 0 && overflow.failed_allocations == 1);
	test_memory_layout_v2();

	printf("  {\"check\":\"sentinel\",\"pass\":true}\n ],\n \"layout_v2\":[\n");
	for (i = 0; i < MEM_LAYOUT_V2_REGION_COUNT; i++) {
		const arena_t *region = mem_layout_v2_get_const(&g_layout,
			(mem_layout_v2_region_t)i);
		printf("  {\"name\":\"%s\",\"bytes\":%u}%s\n", region->name,
			(unsigned)region->cap,
			i + 1 == MEM_LAYOUT_V2_REGION_COUNT ? "" : ",");
	}
	printf(" ],\n \"failures\":%d\n}\n", g_failures);
	return g_failures == 0 ? 0 : 1;
}
