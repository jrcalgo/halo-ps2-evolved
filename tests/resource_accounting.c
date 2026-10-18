/* Host checks for the audited halo-ps2 arena. Output is explicit integers only. */
#include "core/mem.h"
#include <stdint.h>
#include <stdio.h>
#include <string.h>

static int g_failures;

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

int main(void)
{
	unsigned char storage[256];
	unsigned char tiny[32];
	arena_t arena;
	arena_t child;
	arena_t overflow;
	void *aligned;
	void *rejected;
	size_t mark;
	size_t used_after = 0;
	size_t high_before_reset;
	uintptr_t address;

	memset(storage, 0x5a, sizeof storage);
	arena_init(&arena, "fixture", storage, sizeof storage);
	printf("{\n \"abi\":{\"pointer\":%u,\"size\":%u},\n \"checks\":[\n",
	       (unsigned)sizeof(void *), (unsigned)sizeof(size_t));

	aligned = arena_alloc(&arena, 1, 16);
	address = (uintptr_t)aligned;
	expect("align-16", aligned != NULL && (address % 16u) == 0);
	expect("reject-non-power-alignment", arena_alloc(&arena, 1, 3) == NULL);
	expect("reject-zero-alignment", arena_alloc(&arena, 1, 0) == NULL);

	mark = arena_mark(&arena);
	expect("scratch-alloc", arena_alloc(&arena, 8, 1) != NULL);
	expect("lifetime-future-mark", release_checked(&arena, arena.used + 1, &used_after) == -1);
	expect("lifetime-used-unchanged", arena.used == mark + 8);
	expect("scratch-release", release_checked(&arena, mark, &used_after) == 0 && used_after == mark);

	high_before_reset = arena.high;
	arena_reset(&arena);
	expect("scratch-reset", arena.used == 0 && arena.high == high_before_reset);

	rejected = arena_alloc(&arena, sizeof storage + 1, 1);
	expect("exhaustion", rejected == NULL && arena.used == 0);
	expect("occupy-one", arena_alloc(&arena, 16, 1) != NULL);
	expect("sub-arena-exhaustion", arena_sub(&child, &arena, "child", sizeof storage) == -1);

	arena_init(&overflow, "overflow", tiny, sizeof tiny);
	expect("size-overflow", arena_alloc(&overflow, SIZE_MAX, 1) == NULL && overflow.used == 0);

	printf("  {\"check\":\"sentinel\",\"pass\":true}\n ],\n \"failures\":%d\n}\n", g_failures);
	return g_failures == 0 ? 0 : 1;
}
