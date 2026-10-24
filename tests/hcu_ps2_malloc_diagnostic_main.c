#include "cache/physical_memory_map.h"

#include <stdint.h>
#include <limits.h>
#include <stdio.h>
#include <stdlib.h>

void *__wrap_malloc(unsigned long size);
void __wrap_free(void *block);
void *__wrap_realloc(void *block, unsigned long size);

static unsigned char arena[1024u * 1024u] __attribute__((aligned(16)));
static unsigned real_malloc_calls;
static unsigned real_realloc_calls;

void *__real_malloc(unsigned long size)
{
	real_malloc_calls++;
	return malloc((size_t)size);
}

void __real_free(void *block)
{
	free(block);
}

void *__real_realloc(void *block, unsigned long size)
{
	real_realloc_calls++;
	return realloc(block, (size_t)size);
}

int tag_validate_claims_buffer_ready(void)
{
	return 1;
}

int tag_validate_bind_claims_buffer(void *buffer, unsigned long bytes)
{
	(void)buffer;
	(void)bytes;
	return 1;
}

void tag_validate_release_claims_buffer(void)
{
}

static int check_diagnostics(unsigned long capacity, unsigned long used,
	unsigned long high_water, unsigned long failures)
{
	struct physical_memory_malloc_diagnostics diagnostics;
	if (!physical_memory_get_malloc_diagnostics(&diagnostics))
		return 0;
	return diagnostics.capacity_bytes == capacity &&
		diagnostics.used_bytes == used &&
		diagnostics.high_water_bytes == high_water &&
		diagnostics.failed_allocations == failures;
}

int main(void)
{
	void *preboot;
	void *first;
	void *second;
	void *resized;
	void *reused;
	void *guard;
	void *coalesced;
	unsigned long capacity = sizeof arena;
	unsigned long index;

	preboot = __wrap_malloc(13);
	if (!preboot || physical_memory_get_malloc_diagnostics(
		&(struct physical_memory_malloc_diagnostics){ 0 }))
		return 1;
	preboot = __wrap_realloc(preboot, 26);
	if (!preboot || real_realloc_calls != 1)
		return 12;
	__wrap_free(preboot);
	if (__wrap_malloc(ULONG_MAX) != NULL || real_malloc_calls != 1)
		return 11;

	if (!physical_memory_bind_malloc_arena(arena, capacity))
		return 2;
	physical_memory_allocate();
	if (!check_diagnostics(capacity, 0, 0, 0))
		return 3;
	first = __wrap_malloc(17);
	second = __wrap_malloc(1);
	if (first != arena + 16 || second != arena + 64 ||
		((uintptr_t)first & 15u) || ((uintptr_t)second & 15u) ||
		!check_diagnostics(capacity, 80, 80, 0))
		return 4;
	for (index = 0; index < 17; index++)
		((unsigned char *)first)[index] = (unsigned char)(index + 1u);
	((unsigned char *)second)[0] = 0xA5u;
	resized = __wrap_realloc(first, 40);
	if (resized != arena + 96 ||
		!check_diagnostics(capacity, 96, 144, 0))
		return 13;
	for (index = 0; index < 17; index++)
		if (((unsigned char *)resized)[index] != (unsigned char)(index + 1u))
			return 14;
	reused = __wrap_malloc(17);
	if (reused != first || !check_diagnostics(capacity, 144, 144, 0))
		return 16;
	__wrap_free(reused);
	if (!check_diagnostics(capacity, 96, 144, 0))
		return 17;
	if (__wrap_realloc(second, capacity) != NULL ||
		((unsigned char *)second)[0] != 0xA5u ||
		!check_diagnostics(capacity, 96, 144, 1))
		return 15;
	__wrap_free(first);
	if (!check_diagnostics(capacity, 96, 144, 1))
		return 5;
	if (__wrap_malloc(capacity) != NULL ||
		!check_diagnostics(capacity, 96, 144, 2))
		return 6;
	if (__wrap_malloc(ULONG_MAX) != NULL ||
		!check_diagnostics(capacity, 96, 144, 3))
		return 7;
	guard = __wrap_malloc(100);
	if (!guard)
		return 18;
	__wrap_free(second);
	__wrap_free(resized);
	coalesced = __wrap_malloc(40);
	if (coalesced != first ||
		!check_diagnostics(capacity, 192, 224, 3))
		return 19;
	__wrap_free(coalesced);
	__wrap_free(guard);
	if (!check_diagnostics(capacity, 0, 224, 3))
		return 20;

	physical_memory_free();
	if (physical_memory_get_malloc_diagnostics(
		&(struct physical_memory_malloc_diagnostics){ 0 }) ||
		__wrap_malloc(1) != NULL)
		return 8;
	if (!physical_memory_bind_malloc_arena(arena, capacity))
		return 9;
	physical_memory_allocate();
	if (!check_diagnostics(capacity, 0, 0, 0))
		return 10;
	physical_memory_free();
	puts("ps2-malloc-diagnostic preboot-realloc=preserved align=16 high_water=224 failures=3 free=coalesced-reuse rebind_reset=passed");
	return 0;
}
