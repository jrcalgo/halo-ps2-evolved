#include "core/mem.h"

#include <assert.h>
#include <stdint.h>
#include <string.h>

#define CHARGED_BSS 2114532u
#define BACKING_BYTES (MEM_LAYOUT_V2_BYTES - CHARGED_BSS + MEM_LAYOUT_V2_GUARDED_SLACK)

static unsigned char storage[BACKING_BYTES + 64u];

int main(void)
{
	mem_layout_v2_t layout, before;
	arena_t backing, short_backing;
	arena_t *resident;
	size_t used;
	unsigned char saved;

	arena_init(&short_backing, "short", storage + 1,
		MEM_LAYOUT_V2_BYTES - CHARGED_BSS + 15u);
	memset(&layout, 0x5A, sizeof layout);
	before = layout;
	assert(mem_layout_v2_init_charged_guarded(&layout, &short_backing,
		CHARGED_BSS, 0xA5u) != 0);
	assert(short_backing.used == 0 && memcmp(&layout, &before, sizeof layout) == 0);

	arena_init(&backing, "guarded", storage + 1, BACKING_BYTES);
	assert(mem_layout_v2_init_charged_guarded(&layout, &backing,
		CHARGED_BSS, 0xA5u) == 0);
	assert(mem_layout_v2_guards_intact(&layout));
	assert(backing.used <= backing.cap);
	resident = mem_layout_v2_get(&layout, MEM_LAYOUT_V2_RESIDENT_GAMEPLAY);
	assert(resident->cap == 6815744u - CHARGED_BSS);
	assert(arena_alloc(resident, resident->cap + 1u, 1u) == NULL);
	assert(arena_alloc(resident, resident->cap, 1u) == resident->base);
	assert(mem_layout_v2_guards_intact(&layout));
	saved = layout.guards[1][0];
	layout.guards[1][0] ^= 0xFFu;
	assert(!mem_layout_v2_guards_intact(&layout));
	layout.guards[1][0] = saved;
	used = backing.used;
	assert(mem_layout_v2_init_charged_guarded(&layout, &backing,
		CHARGED_BSS, 0xA5u) != 0);
	assert(backing.used == used && mem_layout_v2_guards_intact(&layout));
	arena_reset(&backing);
	assert(mem_layout_v2_init_charged_guarded(&layout, &backing,
		CHARGED_BSS, 0xA5u) == 0);
	assert(mem_layout_v2_guards_intact(&layout));
	return 0;
}
