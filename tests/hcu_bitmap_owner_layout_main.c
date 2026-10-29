#include <assert.h>
#include <stddef.h>
#include <stdint.h>
#include <string.h>
#include "stream/hcu_bitmap_owner_layout.h"
#include "stream/hcu_bitmap_dispatch.h"
#include "stream/hcu_asset_profile.h"
#include "halo_ps2_bitmap_requests.h"
#include "render/texcache.h"

#define CAP (400u * 1024u - 16u)
#define POOL_OLD (256u * 1024u)
#define POOL_NEW (224u * 1024u)
#define STAGING 132192u

static void *alloc16(uint8_t *base, size_t cap, size_t *used, size_t bytes)
{
	size_t aligned = (*used + 15u) & ~(size_t)15u;
	if (aligned > cap || bytes > cap - aligned) return NULL;
	*used = aligned + bytes;
	return base + aligned;
}

int main(void)
{
	size_t descriptors = 64u * sizeof(hcu_bitmap_resident_descriptor);
	size_t base = hcu_bitmap_owner_required(sizeof(tc_journal_t),
		(size_t)TC_MAX_KEYS * sizeof(uint16_t),
		(size_t)HALO_PS2_BITMAP_REQUEST_CAPACITY * sizeof(hcu_bitmap_source_slot),
		(size_t)HALO_PS2_BITMAP_REQUEST_CAPACITY * sizeof(hcu_bitmap_lease),
		sizeof(halo_ps2_bitmap_request_queue), 0, STAGING, descriptors);
	size_t old_required = base + POOL_OLD;
	size_t new_required = base + POOL_NEW;
	static uint8_t owner[400u * 1024u] __attribute__((aligned(16)));
	size_t used = 0;
	uint8_t *guard = owner;
	uint8_t *arena = owner + 16u;
	size_t cap = CAP;
	void *parts[8];
	const size_t sizes[8] = { sizeof(tc_journal_t), (size_t)TC_MAX_KEYS * sizeof(uint16_t),
		POOL_NEW, STAGING,
		(size_t)HALO_PS2_BITMAP_REQUEST_CAPACITY * sizeof(hcu_bitmap_source_slot),
		(size_t)HALO_PS2_BITMAP_REQUEST_CAPACITY * sizeof(hcu_bitmap_lease),
		sizeof(halo_ps2_bitmap_request_queue), descriptors };
	unsigned i;
	assert(old_required > CAP);
	assert(new_required <= CAP);
	assert(old_required - new_required == 32u * 1024u);
	assert(new_required == 401132u);
	assert(CAP - new_required == 8452u);
	memset(guard, 0xa5, 16u);
	for (i = 0; i < 8u; ++i) {
		parts[i] = alloc16(arena, cap, &used, sizes[i]);
		assert(parts[i] != NULL);
		assert(((uintptr_t)parts[i] & 15u) == 0u);
	}
	assert(used <= new_required);
	assert(cap - used >= 8452u);
	for (i = 0; i < 16u; ++i) assert(guard[i] == 0xa5u);
	assert(alloc16(arena, cap, &used, cap - used) != NULL);
	assert(used == cap);
	assert(alloc16(arena, cap, &used, 1u) == NULL);
	return 0;
}
