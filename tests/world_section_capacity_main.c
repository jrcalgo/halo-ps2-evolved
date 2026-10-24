#include "core/mem.h"
#include "ps2_ctag.h"

#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>

#define STREAMING_CAPACITY 1572864u
#define FRAME_SCRATCH_CAPACITY 393216u
#define TAG_CACHE_CAPACITY 2097152u
#define BSP_CAPACITY 6291456u

extern uint8_t *world_load_section_with_scratch(arena_t *owner,
	arena_t *scratch, const char *path, const char *tag, size_t *raw_size,
	int optional);

static uint8_t streaming_memory[STREAMING_CAPACITY] __attribute__((aligned(64)));
static uint8_t scratch_memory[FRAME_SCRATCH_CAPACITY] __attribute__((aligned(64)));
static uint8_t tag_cache_memory[TAG_CACHE_CAPACITY] __attribute__((aligned(16)));
static uint8_t bsp_memory[BSP_CAPACITY] __attribute__((aligned(64)));

static size_t parse_size(const char *value)
{
	char *end = NULL;
	unsigned long long parsed = strtoull(value, &end, 10);
	assert(end && *end == '\0');
	assert(parsed <= SIZE_MAX);
	return (size_t)parsed;
}

int main(int argc, char **argv)
{
	arena_t streaming, scratch, bsp_owner;
	ps2_ctag_view view;
	size_t expected_ctag, expected_crng, ctag_size = 0, crng_size = 0;
	uint8_t *ctag, *crng;
	assert(argc == 4);
	expected_ctag = parse_size(argv[2]);
	expected_crng = parse_size(argv[3]);
	arena_init(&streaming, "streaming", streaming_memory,
		sizeof(streaming_memory));
	arena_init(&scratch, "frame scratch", scratch_memory,
		sizeof(scratch_memory));
	arena_init(&bsp_owner, "current bsp", bsp_memory, sizeof(bsp_memory));

	ctag = world_load_section_with_scratch(&streaming, &scratch, argv[1],
		"CTAG", &ctag_size, 0);
	/* Retail negative control: reject a section that cannot fit the current
	 * streaming owner before allocating scratch or disturbing its mark. */
	if (expected_ctag > streaming.cap) {
		assert(!ctag && ctag_size == 0);
		assert(streaming.used == 0 && scratch.used == 0);
		assert(streaming.high == 0 && scratch.high == 0);
		{
			size_t bsp_size = 0;
			uint8_t *bsp = world_load_section_with_scratch(&scratch,
				&scratch, argv[1], "B000", &bsp_size, 0);
			assert(!bsp && bsp_size == 0);
			assert(scratch.used == 0 && scratch.high == 0);
			bsp = world_load_section_with_scratch(&bsp_owner, &scratch,
				argv[1], "B000", &bsp_size, 0);
			assert(bsp && bsp_size == 1303092u);
			assert(bsp_owner.used == bsp_size &&
				scratch.used == 0 && scratch.high == 98304u);
			arena_release(&bsp_owner, 0);
		}
		printf("CTAG=%zu expected=bounded-reject streaming=%zu/%zu frame_scratch=%zu/%zu B000=bounded-decode owner_high=%zu/%zu\n",
			expected_ctag, streaming.high, streaming.cap,
			scratch.high, scratch.cap, bsp_owner.high, bsp_owner.cap);
		return 0;
	}
	assert(ctag && ctag_size == expected_ctag);
	crng = world_load_section_with_scratch(&streaming, &scratch, argv[1],
		"CRNG", &crng_size, 0);
	assert(crng && crng_size == expected_crng);
	assert(ctag < crng && ctag + ctag_size <= crng);
	assert(streaming.used <= streaming.cap);
	assert(scratch.used == 0);
	assert(ps2_ctag_open(&view, ctag, ctag_size, TAG_CACHE_CAPACITY,
		TAG_CACHE_CAPACITY / 4) == PS2_CTAG_OK);
	assert(view.image_size == 1510628u);
	assert(ps2_ctag_materialize(&view, 0x20000000u, tag_cache_memory,
		sizeof(tag_cache_memory)) == PS2_CTAG_OK);
	printf("CTAG=%zu CRNG=%zu streaming_high=%zu/%zu frame_scratch_high=%zu/%zu\n",
		ctag_size, crng_size, streaming.high, streaming.cap,
		scratch.high, scratch.cap);
	return 0;
}
