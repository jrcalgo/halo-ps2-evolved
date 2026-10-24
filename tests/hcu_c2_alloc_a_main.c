/* Host driver for the CE memory pool's bounded reuse and counters (C2.5 lane
 * alloc-a). It compiles source/memory/memory_pool.c unchanged against the
 * shim in hcu_c2_alloc_a_shim, then drives the allocate, reallocate and free
 * paths the object pool uses. Prints one result line; the Python test checks it. */
#include "cseries.h"
#include "memory_pool.h"

#include <stdio.h>
#include <stdint.h>
#include <string.h>

#define POOL_BYTES (64u * 1024u)
#define SLOTS 48u
#define CYCLES 100000u

static unsigned char storage[sizeof(struct memory_pool) + POOL_BYTES] __attribute__((aligned(16)));
static struct memory_pool *pool = (struct memory_pool *)storage;

struct slot { void *block; long size; unsigned char seed; };
static struct slot slots[SLOTS];
static uint64_t rng = 0x243F6A8885A308D3ull;

static uint32_t next_random(void)
{
	rng ^= rng << 13; rng ^= rng >> 7; rng ^= rng << 17;
	return (uint32_t)rng;
}

static long pick_size(void)
{
	uint32_t r = next_random() % 100u;
	if (r < 70u) return 1 + (long)(next_random() % 256u);
	if (r < 95u) return 256 + (long)(next_random() % 2048u);
	return 2048 + (long)(next_random() % 4096u);
}

static void fill(unsigned char *block, long size, unsigned char seed)
{
	long i;
	for (i = 0; i < size; i++) block[i] = (unsigned char)(seed + i * 31u);
}

static int verify(const unsigned char *block, long size, unsigned char seed)
{
	long i;
	for (i = 0; i < size; i++) if (block[i] != (unsigned char)(seed + i * 31u)) return 0;
	return 1;
}

static int inside_pool(const void *block, long size)
{
	const unsigned char *base = (const unsigned char *)pool->base_address;
	const unsigned char *p = (const unsigned char *)block;
	return p >= base && p + size <= base + pool->size;
}

int main(void)
{
	unsigned long cycle;
	unsigned long failures = 0, corruptions = 0;
	long used_before;
	struct memory_pool_counters counters;
	long used_after_drain;
	unsigned i;

	memory_pool_initialize(pool, "hcu-c2-alloc-a", (long)POOL_BYTES);
	used_before = memory_pool_get_used_size(pool);
	memset(slots, 0, sizeof slots);

	for (cycle = 0; cycle < CYCLES; cycle++) {
		struct slot *s = &slots[next_random() % SLOTS];
		uint32_t r = next_random() % 100u;
		if (!s->block) {
			long size = pick_size();
			void *reference = NULL;
			if (memory_pool_block_allocate(pool, &reference, size)) {
				s->block = reference;
				s->size = size;
				s->seed = (unsigned char)next_random();
				fill((unsigned char *)s->block, size, s->seed);
				if (!inside_pool(s->block, size)) return 3;
			} else {
				failures++;
			}
		} else if (r < 35u) {
			void *reference = s->block;
			memory_pool_block_free(pool, &reference);
			s->block = NULL;
		} else if (r < 70u) {
			long new_size = pick_size();
			void *reference = s->block;
			if (!verify((unsigned char *)s->block, s->size, s->seed)) corruptions++;
			if (memory_pool_block_reallocate(pool, &reference, new_size)) {
				long keep = s->size < new_size ? s->size : new_size;
				if (!inside_pool(reference, new_size)) return 4;
				if (!verify((unsigned char *)reference, keep, s->seed)) corruptions++;
				s->block = reference;
				s->size = new_size;
				s->seed = (unsigned char)next_random();
				fill((unsigned char *)s->block, new_size, s->seed);
			} else {
				/* A refused reallocate must leave the old block intact. */
				if (!verify((unsigned char *)s->block, s->size, s->seed)) corruptions++;
				failures++;
			}
		} else {
			void *reference = s->block;
			memory_pool_block_free(pool, &reference);
			s->block = NULL;
		}
	}

	for (i = 0; i < SLOTS; i++) {
		if (slots[i].block) {
			void *reference = slots[i].block;
			memory_pool_block_free(pool, &reference);
			slots[i].block = NULL;
		}
	}
	used_after_drain = memory_pool_get_used_size(pool) - used_before;
	memory_pool_get_counters(pool, &counters);

	printf("c2-alloc-a cycles=%lu used_after_drain=%ld growth=%ld "
		"allocations=%lu frees=%lu reallocations=%lu moved=%lu "
		"failures=%lu corruptions=%lu escapes=%lu resets=%lu "
		"high_water=%ld sdk_fallbacks=0\n",
		(unsigned long)CYCLES, used_after_drain, used_after_drain,
		counters.allocations, counters.frees, counters.reallocations,
		counters.moved_reallocations,
		counters.allocation_failures + counters.reallocation_failures,
		corruptions, counters.escapes, counters.resets, counters.high_water_size);
	(void)failures;
	return (used_after_drain != 0 || corruptions != 0 || counters.escapes != 0) ? 1 : 0;
}
