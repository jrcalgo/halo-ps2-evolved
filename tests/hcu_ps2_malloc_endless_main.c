/* Endless-play churn driver for the PS2 compatibility allocator. Builds against
 * the real ps2_memory.c with the same shim as the diagnostic driver. The live
 * set is bounded by policy; the allocator must keep contents, coalesce, avoid
 * SDK fallbacks after activation and never corrupt a block on failed realloc. */
#include "cache/physical_memory_map.h"

#include <limits.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

void *__wrap_malloc(unsigned long size);
void __wrap_free(void *block);
void *__wrap_realloc(void *block, unsigned long size);

struct ps2_malloc_fallback_counters {
	unsigned long sdk_malloc_preactivation, sdk_realloc, sdk_free, refused_unbound;
};
int physical_memory_get_malloc_fallback_counters(struct ps2_malloc_fallback_counters *counters);

static unsigned char arena[1024u * 1024u] __attribute__((aligned(16)));

void *__real_malloc(unsigned long size) { return malloc((size_t)size); }
void __real_free(void *block) { free(block); }
void *__real_realloc(void *block, unsigned long size) { return realloc(block, (size_t)size); }
int tag_validate_claims_buffer_ready(void) { return 1; }
int tag_validate_bind_claims_buffer(void *buffer, unsigned long bytes) { (void)buffer; (void)bytes; return 1; }
void tag_validate_release_claims_buffer(void) {}

#define SLOTS 384u
#define LIVE_BUDGET (capacity_bytes / 2u)
#define OPERATIONS 2000000u

struct slot { unsigned char *block; unsigned long size; unsigned char seed; };
static struct slot slots[SLOTS];
static unsigned long capacity_bytes = sizeof arena;
static uint64_t rng = 0x9E3779B97F4A7C15ull;

static uint32_t next_random(void)
{
	rng ^= rng << 13; rng ^= rng >> 7; rng ^= rng << 17;
	return (uint32_t)rng;
}

static unsigned long pick_size(void)
{
	/* Mostly small CE-like records, with occasional large tag/bitmap blocks. */
	uint32_t r = next_random() % 100u;
	if (r < 70u) return 1u + next_random() % 256u;
	if (r < 95u) return 256u + next_random() % 4096u;
	return 4096u + next_random() % 65536u;
}

static void fill(unsigned char *block, unsigned long size, unsigned char seed)
{
	unsigned long i;
	for (i = 0; i < size; i++) block[i] = (unsigned char)(seed + i * 31u);
}

static int verify(const unsigned char *block, unsigned long size, unsigned char seed)
{
	unsigned long i;
	for (i = 0; i < size; i++) if (block[i] != (unsigned char)(seed + i * 31u)) return 0;
	return 1;
}

static unsigned long used_bytes(void)
{
	struct physical_memory_malloc_diagnostics d;
	return physical_memory_get_malloc_diagnostics(&d) ? d.used_bytes : ULONG_MAX;
}

static int check_fallbacks_clean(void)
{
	struct ps2_malloc_fallback_counters c;
	if (!physical_memory_get_malloc_fallback_counters(&c)) return 0;
	return c.sdk_realloc == 0 && c.sdk_free == 0 && c.refused_unbound == 0;
}

int main(void)
{
	unsigned long op, allocs = 0, frees = 0, reallocs = 0, failures = 0, fragmentation_failures = 0;
	unsigned long realloc_failures_preserved = 0, largest = 0;
	struct ps2_malloc_fallback_counters before, after;
	unsigned i;

	if (!physical_memory_bind_malloc_arena(arena, capacity_bytes)) return 2;
	physical_memory_allocate();
	if (!physical_memory_get_malloc_fallback_counters(&before)) return 3;
	if (before.sdk_malloc_preactivation != 0) return 4;

	for (op = 0; op < OPERATIONS; op++) {
		struct slot *s = &slots[next_random() % SLOTS];
		uint32_t r = next_random() % 100u;
		if (!s->block || r < 40u) {
			unsigned long size;
			if (s->block) {
				/* Allocation without a free slot is replaced by free. */
				__wrap_free(s->block); s->block = 0; frees++;
				continue;
			}
			size = pick_size();
			if (used_bytes() + size + 32u > LIVE_BUDGET) continue;
			s->block = __wrap_malloc(size);
			if (!s->block) {
				failures++;
				if (used_bytes() + size + 32u <= capacity_bytes) fragmentation_failures++;
				continue;
			}
			s->size = size; s->seed = (unsigned char)next_random();
			fill(s->block, size, s->seed); allocs++;
		} else if (r < 70u) {
			__wrap_free(s->block); s->block = 0; frees++;
		} else {
			unsigned long new_size = pick_size();
			unsigned char *next;
			if (used_bytes() + new_size > LIVE_BUDGET + 64u * 1024u) continue;
			if (!verify(s->block, s->size, s->seed)) return 5;
			next = __wrap_realloc(s->block, new_size);
			if (!next) {
				/* Failed realloc keeps the original block intact. */
				if (!verify(s->block, s->size, s->seed)) return 6;
				failures++;
				realloc_failures_preserved++;
				continue;
			}
			{
				unsigned long keep = s->size < new_size ? s->size : new_size;
				if (!verify(next, keep, s->seed)) return 7;
			}
			s->block = next; s->size = new_size; fill(s->block, s->size, s->seed);
			reallocs++;
		}
		if ((op & 0x3FFFu) == 0u) {
			for (i = 0; i < SLOTS; i++)
				if (slots[i].block && !verify(slots[i].block, slots[i].size, slots[i].seed)) return 8;
			if (used_bytes() > capacity_bytes) return 9;
		}
	}

	for (i = 0; i < SLOTS; i++) if (slots[i].block) { __wrap_free(slots[i].block); slots[i].block = 0; }
	if (used_bytes() != 0) return 10;
	/* Full coalescing: after a complete drain one arena-sized request fits again. */
	for (largest = capacity_bytes; largest > 1024; largest -= 16) {
		void *probe = __wrap_malloc(largest);
		if (probe) { __wrap_free(probe); break; }
	}
	if (largest < capacity_bytes - 4096u) return 11;
	if (!physical_memory_get_malloc_fallback_counters(&after)) return 12;
	if (!check_fallbacks_clean() || after.sdk_malloc_preactivation != before.sdk_malloc_preactivation) return 13;
	if (used_bytes() != 0) return 14;
	printf("ps2-malloc-endless ops=%lu allocs=%lu frees=%lu reallocs=%lu failures=%lu fragmentation_failures=%lu realloc_failures_preserved=%lu largest_after_drain=%lu sdk_fallbacks=0\n",
		(unsigned long)OPERATIONS, allocs, frees, reallocs, failures, fragmentation_failures, realloc_failures_preserved, largest);
	physical_memory_free();
	return 0;
}
