/* Focused runtime fixture for the real parent binder's MP candidate spans. */
#include "cseries.h"
#include "core/mem.h"
#include "cache/physical_memory_map.h"
#include "halo_ps2_limits.h"
#include "stream/hcu_memory_bind.h"
#include "stream/hcu_memory_profile.h"

#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#define TAG_BYTES 4477120u
#define BSP_BYTES 1993712u
#define MAP_BYTES (TAG_BYTES + BSP_BYTES)
#define TEXTURE_BYTES 4014928u
#define CURRENT_BSP_BYTES 6291456u
#define CURRENT_TEXTURE_BYTES 4718592u
#define PROFILE_TAG_BYTES 4685920u
#define PROFILE_BSP_BYTES 1993744u
#define PROFILE_MAP_PARENT_BYTES (PROFILE_TAG_BYTES + PROFILE_BSP_BYTES + 16u)
#define PROFILE_RENDER_BYTES \
	(CURRENT_BSP_BYTES + CURRENT_TEXTURE_BYTES - PROFILE_MAP_PARENT_BYTES)

static uint8_t backing_bytes[MEM_LAYOUT_V2_BYTES +
	MEM_LAYOUT_V2_GUARDED_SLACK + 64u] __attribute__((aligned(64)));

boolean tag_validate_claims_buffer_ready(void) { return TRUE; }
boolean tag_validate_bind_claims_buffer(void *base, unsigned long bytes)
{ return base != NULL && bytes == tag_validate_claims_buffer_size(); }
void tag_validate_release_claims_buffer(void) {}
unsigned long tag_validate_claims_buffer_size(void)
{
	unsigned long total = physical_memory_get_tag_cache_size() +
		physical_memory_get_structure_bsp_cache_size();
	return ((total + 31u) / 32u) * 4u;
}
void *__real_malloc(unsigned long bytes) { (void)bytes; return NULL; }
void __real_free(void *base) { (void)base; }
void *__real_realloc(void *base, unsigned long bytes)
{ (void)base; (void)bytes; return NULL; }

static void fresh_guarded_layout(mem_layout_v2_t *layout, arena_t *backing)
{
	arena_init(backing, "production-binder-test", backing_bytes,
		sizeof(backing_bytes));
	assert(mem_layout_v2_init_charged_guarded(layout, backing, 0, 0xA5u) == 0);
}

/* Reproduce the opt-in candidate carve in hcu_main.c against a fresh layout.
 * The source-audit runner below ties this arithmetic to that gated code. */
static void candidate_recarve(mem_layout_v2_t *layout)
{
	arena_t *bsp = mem_layout_v2_get(layout, MEM_LAYOUT_V2_CURRENT_BSP);
	arena_t *texture = mem_layout_v2_get(layout, MEM_LAYOUT_V2_TEXTURE_CACHE);
	uint8_t *combined_end;
	assert(bsp && texture && bsp->cap == CURRENT_BSP_BYTES);
	assert(texture->cap == CURRENT_TEXTURE_BYTES);
	assert(texture->base == layout->guards[2] + MEM_LAYOUT_V2_GUARD_BYTES);
	assert(MAP_BYTES + TEXTURE_BYTES ==
		CURRENT_BSP_BYTES + CURRENT_TEXTURE_BYTES);
	combined_end = bsp->base + MAP_BYTES + TEXTURE_BYTES;
	assert(combined_end <= texture->base + texture->cap -
		MEM_LAYOUT_V2_GUARD_BYTES);
	bsp->cap = MAP_BYTES;
	texture->base = bsp->base + MAP_BYTES;
	texture->cap = TEXTURE_BYTES;
	layout->guards[2] = combined_end;
	layout->guards[3] = combined_end;
	memset(combined_end, layout->guard_pattern, MEM_LAYOUT_V2_GUARD_BYTES);
}

static void test_default_layout_is_short_and_noncontiguous(void)
{
	arena_t backing;
	mem_layout_v2_t layout;
	arena_t *bsp, *texture;
	unsigned long actual_bsp, actual_texture;
	fresh_guarded_layout(&layout, &backing);
	bsp = mem_layout_v2_get(&layout, MEM_LAYOUT_V2_CURRENT_BSP);
	texture = mem_layout_v2_get(&layout, MEM_LAYOUT_V2_TEXTURE_CACHE);
	assert(bsp && texture);
	assert(hcu_memory_bind_parent_v2(&layout, TAG_BYTES) == 0);
	physical_memory_allocate();
	assert(physical_memory_ready());
	actual_bsp = physical_memory_get_structure_bsp_cache_size();
	actual_texture = physical_memory_get_texture_cache_size();
	assert(physical_memory_get_tag_cache_size() == TAG_BYTES);
	assert(actual_bsp == CURRENT_BSP_BYTES - TAG_BYTES);
	assert(actual_bsp == 1814336u);
	assert(actual_bsp < BSP_BYTES);
	assert(BSP_BYTES - actual_bsp == 179376u);
	assert(actual_texture == CURRENT_TEXTURE_BYTES);
	assert((uint8_t *)physical_memory_get_structure_bsp_cache_base_address() +
		actual_bsp == bsp->base + bsp->cap);
	assert((uint8_t *)physical_memory_get_texture_cache_base_address() ==
		texture->base);
	assert(texture->base == bsp->base + CURRENT_BSP_BYTES +
		MEM_LAYOUT_V2_GUARD_BYTES);
	assert(mem_layout_v2_guards_intact(&layout));
	printf("production-binder-default tag=%u bsp=%lu required_bsp=%u "
		"bsp_shortfall=%u texture=%lu gap=%lu ready=1 candidate_fit=0\n",
		TAG_BYTES, actual_bsp, BSP_BYTES, BSP_BYTES - (unsigned)actual_bsp,
		actual_texture, (unsigned long)MEM_LAYOUT_V2_GUARD_BYTES);
	physical_memory_free();
}

static void test_existing_opt_in_recarve_binds_candidate_spans(void)
{
	arena_t backing;
	mem_layout_v2_t layout;
	arena_t *bsp, *texture;
	uint8_t *tag_base, *bsp_base, *texture_base;
	size_t parent_used;
	fresh_guarded_layout(&layout, &backing);
	parent_used = backing.used;
	bsp = mem_layout_v2_get(&layout, MEM_LAYOUT_V2_CURRENT_BSP);
	texture = mem_layout_v2_get(&layout, MEM_LAYOUT_V2_TEXTURE_CACHE);
	assert(bsp && texture);
	candidate_recarve(&layout);
	assert(backing.used == parent_used);
	assert(hcu_memory_bind_parent_v2(&layout, TAG_BYTES) == 0);
	physical_memory_allocate();
	assert(physical_memory_ready());
	tag_base = physical_memory_get_tag_cache_base_address();
	bsp_base = physical_memory_get_structure_bsp_cache_base_address();
	texture_base = physical_memory_get_texture_cache_base_address();
	assert(physical_memory_get_tag_cache_size() == TAG_BYTES);
	assert(physical_memory_get_structure_bsp_cache_size() == BSP_BYTES);
	assert(physical_memory_get_texture_cache_size() == TEXTURE_BYTES);
	assert((uint8_t *)bsp_base == tag_base + TAG_BYTES);
	assert((uint8_t *)texture_base == bsp_base + BSP_BYTES);
	assert((uint8_t *)texture_base ==
		bsp->base + MAP_BYTES);
	assert((uint8_t *)texture_base + TEXTURE_BYTES ==
		bsp->base + MAP_BYTES + TEXTURE_BYTES);
	assert(texture->base == texture_base && texture->cap == TEXTURE_BYTES);
	assert(bsp->cap + texture->cap ==
		CURRENT_BSP_BYTES + CURRENT_TEXTURE_BYTES);
	assert(mem_layout_v2_guards_intact(&layout));
	printf("production-binder-recarved tag=%u bsp=%u map=%u texture=%u "
		"total=%u contiguous_views=1 parent_bytes_unchanged=1 guards=1 "
		"ready=1\n", TAG_BYTES, BSP_BYTES, MAP_BYTES, TEXTURE_BYTES,
		MAP_BYTES + TEXTURE_BYTES);
	physical_memory_free();
}

static void test_versioned_guarded_profile(void)
{
	arena_t backing;
	mem_layout_v2_t layout;
	hcu_memory_profile_t profile = { HCU_MEMORY_PROFILE_VERSION_1,
		PROFILE_TAG_BYTES, PROFILE_BSP_BYTES, PROFILE_RENDER_BYTES };
	hcu_memory_partition_t plan, bound;
	arena_t *bsp, *texture;
	uint8_t *old_suffix_guard;
	size_t bsp_used, texture_used;
	fresh_guarded_layout(&layout, &backing);
	bsp = mem_layout_v2_get(&layout, MEM_LAYOUT_V2_CURRENT_BSP);
	texture = mem_layout_v2_get(&layout, MEM_LAYOUT_V2_TEXTURE_CACHE);
	old_suffix_guard = layout.guards[3];
	assert(bsp && texture);
	bsp_used = bsp->used;
	texture_used = texture->used;
	assert(hcu_memory_profile_plan_v1(&layout, &profile, &plan) == 0);
	assert(plan.tag_cache_base == bsp->base);
	assert(plan.tag_bsp_guard_bytes == 16u && plan.bsp_alignment_bytes == 0u);
	assert(plan.map_parent_bytes == PROFILE_MAP_PARENT_BYTES);
	assert(plan.render_parent_bytes == PROFILE_RENDER_BYTES);
	assert(plan.structure_bsp_base == (uint8_t *)plan.tag_cache_base +
		profile.tag_cache_bytes + MEM_LAYOUT_V2_GUARD_BYTES);
	assert(plan.render_texture_base == (uint8_t *)plan.tag_cache_base +
		plan.map_parent_bytes + MEM_LAYOUT_V2_GUARD_BYTES);
	assert(plan.claims_scratch_bytes == 834960u);
	assert(hcu_memory_bind_profile_v1(&layout, &profile, &bound) == 0);
	assert(bound.claims_scratch_base != NULL);
	assert(!physical_memory_bindings_locked() && !physical_memory_ready());
	physical_memory_allocate();
	assert(physical_memory_ready());
	assert(physical_memory_get_tag_cache_base_address() == bound.tag_cache_base);
	assert(physical_memory_get_structure_bsp_cache_base_address() ==
		bound.structure_bsp_base);
	assert(physical_memory_get_texture_cache_base_address() ==
		bound.render_texture_base);
	assert(physical_memory_get_tag_cache_size() == profile.tag_cache_bytes);
	assert(physical_memory_get_structure_bsp_cache_size() ==
		profile.structure_bsp_bytes);
	assert(physical_memory_get_texture_cache_size() ==
		profile.render_texture_bytes);
	assert(bsp->cap == plan.map_parent_bytes);
	assert(texture->base == plan.render_texture_base &&
		texture->cap == plan.render_parent_bytes);
	assert(layout.guards[2] == bsp->base + bsp->cap);
	assert(layout.guards[3] == old_suffix_guard);
	assert(mem_layout_v2_guards_intact(&layout));
	assert(hcu_memory_partition_guards_intact(&layout, &bound));
	assert(bound.tag_bsp_guard != layout.guards[2]);
	assert(memcmp(bound.tag_bsp_guard, (uint8_t[16]){[0 ... 15] = 0xA5}, 16) == 0);
	{
		uint8_t saved_inner = *(uint8_t *)bound.tag_bsp_guard;
		uint8_t saved_outer = *layout.guards[2];
		uint8_t *saved_outer_ptr = layout.guards[2];
		void *saved_render = bound.render_texture_base;
		*(uint8_t *)bound.tag_bsp_guard ^= 1u;
		assert(!hcu_memory_partition_guards_intact(&layout, &bound));
		*(uint8_t *)bound.tag_bsp_guard = saved_inner;
		*layout.guards[2] ^= 1u;
		assert(!hcu_memory_partition_guards_intact(&layout, &bound));
		*layout.guards[2] = saved_outer;
		layout.guards[2]++;
		assert(!hcu_memory_partition_guards_intact(&layout, &bound));
		layout.guards[2] = saved_outer_ptr;
		bound.render_texture_base = (uint8_t *)saved_render + 16u;
		assert(!hcu_memory_partition_guards_intact(&layout, &bound));
		bound.render_texture_base = saved_render;
		assert(hcu_memory_partition_guards_intact(&layout, &bound));
	}
	assert(bsp->used - bsp_used == plan.map_parent_bytes);
	assert(texture->used - texture_used == profile.render_texture_bytes);
	assert(bound.map_parent_bytes + bound.render_parent_bytes ==
		CURRENT_BSP_BYTES + CURRENT_TEXTURE_BYTES);
	assert(bound.map_render_guard_bytes == MEM_LAYOUT_V2_GUARD_BYTES);
	assert(bsp->used - bsp_used == profile.tag_cache_bytes + 16u +
		profile.structure_bsp_bytes);
	printf("profile-v1 tag=%lu bsp=%lu map_parent=%lu internal_guard=%lu "
		"texture=%lu render_parent=%lu claims=%lu "
		"bsp_alignment=%lu texture_alignment=%lu "
		"owners=current_bsp[tag+bsp+guard],texture_cache[render],"
		"resident_gameplay[claims=%lu] outer_map_texture_guard=%lu ready=1\n",
		(unsigned long)bound.tag_cache_bytes,
		(unsigned long)bound.structure_bsp_bytes,
		(unsigned long)bound.map_parent_bytes,
		(unsigned long)bound.tag_bsp_guard_bytes,
		(unsigned long)bound.render_texture_bytes,
		(unsigned long)bound.render_parent_bytes,
		(unsigned long)bound.claims_scratch_bytes,
		(unsigned long)bound.bsp_alignment_bytes,
		(unsigned long)bound.texture_alignment_bytes,
		(unsigned long)bound.claims_scratch_bytes,
		(unsigned long)MEM_LAYOUT_V2_GUARD_BYTES);
	physical_memory_free();
}

static void test_profile_rejection_is_atomic(void)
{
	arena_t backing;
	mem_layout_v2_t layout;
	hcu_memory_profile_t profile = { HCU_MEMORY_PROFILE_VERSION_1,
		2u * 1024u * 1024u, 2u * 1024u * 1024u, 4u * 1024u * 1024u };
	hcu_memory_partition_t out, before;
	arena_t *bsp, *texture;
	size_t bsp_used, texture_used;
	fresh_guarded_layout(&layout, &backing);
	bsp = mem_layout_v2_get(&layout, MEM_LAYOUT_V2_CURRENT_BSP);
	texture = mem_layout_v2_get(&layout, MEM_LAYOUT_V2_TEXTURE_CACHE);
	memset(&out, 0x5A, sizeof(out)); before = out;
	profile.version++;
	assert(hcu_memory_profile_plan_v1(&layout, &profile, &out) != 0);
	assert(memcmp(&out, &before, sizeof(out)) == 0);
	profile.version = HCU_MEMORY_PROFILE_VERSION_1;
	profile.tag_cache_bytes++;
	assert(hcu_memory_profile_plan_v1(&layout, &profile, &out) != 0);
	profile.tag_cache_bytes = 4u * 1024u * 1024u;
	profile.structure_bsp_bytes = 3u * 1024u * 1024u;
	assert(hcu_memory_profile_plan_v1(&layout, &profile, &out) != 0);
	profile.tag_cache_bytes = 2u * 1024u * 1024u;
	profile.structure_bsp_bytes = 2u * 1024u * 1024u;
	{
		size_t bsp_cap = bsp->cap;
		uint8_t *bsp_base = bsp->base;
		bsp->cap = SIZE_MAX;
		assert(hcu_memory_profile_plan_v1(&layout, &profile, &out) != 0);
		bsp->cap = bsp_cap;
		bsp->base = (uint8_t *)(uintptr_t)(UINTPTR_MAX - 7u);
		assert(hcu_memory_profile_plan_v1(&layout, &profile, &out) != 0);
		bsp->base = bsp_base;
	}
	bsp->used = 16u;
	assert(hcu_memory_profile_plan_v1(&layout, &profile, &out) != 0);
	bsp->used = 0;
	texture->base += MEM_LAYOUT_V2_GUARD_BYTES;
	assert(hcu_memory_profile_plan_v1(&layout, &profile, &out) != 0);
	texture->base -= MEM_LAYOUT_V2_GUARD_BYTES;
	bsp_used = bsp->used; texture_used = texture->used;
	assert(hcu_memory_bind_profile_v1(&layout, &profile, &out) == 0);
	physical_memory_free();
	assert(bsp->used == bsp_used + profile.tag_cache_bytes + 16u +
		profile.structure_bsp_bytes);
	assert(texture->used == texture_used + profile.render_texture_bytes);
	printf("profile-v1-invalid version=1 alignment=1 bounds=1 used=1 "
		"adjacency=1 plan_atomic=1\n");
}

static void test_profile_provider_failure_is_atomic(void)
{
	arena_t backing;
	mem_layout_v2_t layout;
	hcu_memory_profile_t profile = { HCU_MEMORY_PROFILE_VERSION_1,
		2u * 1024u * 1024u, 2u * 1024u * 1024u, 4u * 1024u * 1024u };
	hcu_memory_partition_t out;
	arena_t *resident, *bsp, *texture, *dynamic;
	arena_t resident_before, bsp_before, texture_before;
	uint8_t saved_guard[MEM_LAYOUT_V2_GUARD_BYTES];
	size_t resident_used, bsp_used, texture_used;
	fresh_guarded_layout(&layout, &backing);
	resident = mem_layout_v2_get(&layout, MEM_LAYOUT_V2_RESIDENT_GAMEPLAY);
	bsp = mem_layout_v2_get(&layout, MEM_LAYOUT_V2_CURRENT_BSP);
	texture = mem_layout_v2_get(&layout, MEM_LAYOUT_V2_TEXTURE_CACHE);
	dynamic = mem_layout_v2_get(&layout, MEM_LAYOUT_V2_DYNAMIC_SIMULATION);
	resident_used = resident->used; bsp_used = bsp->used; texture_used = texture->used;
	resident_before = *resident; bsp_before = *bsp; texture_before = *texture;
	memcpy(saved_guard, layout.guards[2], sizeof(saved_guard));
	/* Force the final CE provider bind to collide after earlier binds succeeded. */
	dynamic->base = texture->base;
	assert(hcu_memory_bind_profile_v1(&layout, &profile, &out) != 0);
	assert(!physical_memory_bindings_locked() && !physical_memory_ready());
	assert(resident->used == resident_used && bsp->used == bsp_used &&
		texture->used == texture_used);
	assert(memcmp(resident, &resident_before, sizeof(*resident)) == 0);
	assert(memcmp(bsp, &bsp_before, sizeof(*bsp)) == 0);
	assert(memcmp(texture, &texture_before, sizeof(*texture)) == 0);
	assert(memcmp(saved_guard, layout.guards[2], sizeof(saved_guard)) == 0);
	assert(physical_memory_get_tag_cache_base_address() == NULL);
	assert(physical_memory_get_structure_bsp_cache_base_address() == NULL);
	assert(physical_memory_get_texture_cache_base_address() == NULL);
	printf("profile-v1-provider-failure rollback=1 cursors=1 provider-spans=1 canary=1\n");
}

static void test_bind_rejected_after_provider_lock(void)
{
	arena_t backing;
	mem_layout_v2_t layout;
	hcu_memory_profile_t profile = { HCU_MEMORY_PROFILE_VERSION_1,
		2u * 1024u * 1024u, 2u * 1024u * 1024u, 4u * 1024u * 1024u };
	hcu_memory_partition_t out;
	arena_t *resident, *bsp, *texture;
	void *tag_before, *bsp_before, *texture_before;
	size_t resident_used, bsp_used, texture_used;
	fresh_guarded_layout(&layout, &backing);
	resident = mem_layout_v2_get(&layout, MEM_LAYOUT_V2_RESIDENT_GAMEPLAY);
	bsp = mem_layout_v2_get(&layout, MEM_LAYOUT_V2_CURRENT_BSP);
	texture = mem_layout_v2_get(&layout, MEM_LAYOUT_V2_TEXTURE_CACHE);
	physical_memory_allocate(); /* allocated, deliberately not provider-ready */
	assert(physical_memory_bindings_locked() && !physical_memory_ready());
	tag_before = physical_memory_get_tag_cache_base_address();
	bsp_before = physical_memory_get_structure_bsp_cache_base_address();
	texture_before = physical_memory_get_texture_cache_base_address();
	resident_used = resident->used; bsp_used = bsp->used; texture_used = texture->used;
	memset(backing_bytes, 0x6D, sizeof(backing_bytes));
	assert(hcu_memory_bind_parent_v2(&layout, TAG_BYTES) != 0);
	assert(hcu_memory_bind_profile_v1(&layout, &profile, &out) != 0);
	assert(physical_memory_bindings_locked() && !physical_memory_ready());
	assert(physical_memory_get_tag_cache_base_address() == tag_before);
	assert(physical_memory_get_structure_bsp_cache_base_address() == bsp_before);
	assert(physical_memory_get_texture_cache_base_address() == texture_before);
	assert(resident->used == resident_used && bsp->used == bsp_used &&
		texture->used == texture_used);
	assert(backing_bytes[0] == 0x6D && backing_bytes[sizeof(backing_bytes)-1] == 0x6D);
	physical_memory_free();
	/* Also exercise the ready state: neither binder may free live CE stores. */
	fresh_guarded_layout(&layout, &backing);
	resident = mem_layout_v2_get(&layout, MEM_LAYOUT_V2_RESIDENT_GAMEPLAY);
	bsp = mem_layout_v2_get(&layout, MEM_LAYOUT_V2_CURRENT_BSP);
	texture = mem_layout_v2_get(&layout, MEM_LAYOUT_V2_TEXTURE_CACHE);
	assert(hcu_memory_bind_parent_v2(&layout, TAG_BYTES) == 0);
	physical_memory_allocate();
	assert(physical_memory_bindings_locked() && physical_memory_ready());
	tag_before = physical_memory_get_tag_cache_base_address();
	bsp_before = physical_memory_get_structure_bsp_cache_base_address();
	texture_before = physical_memory_get_texture_cache_base_address();
	resident_used = resident->used; bsp_used = bsp->used; texture_used = texture->used;
	assert(hcu_memory_bind_parent_v2(&layout, TAG_BYTES) != 0);
	assert(hcu_memory_bind_profile_v1(&layout, &profile, &out) != 0);
	assert(physical_memory_bindings_locked() && physical_memory_ready());
	assert(physical_memory_get_tag_cache_base_address() == tag_before);
	assert(physical_memory_get_structure_bsp_cache_base_address() == bsp_before);
	assert(physical_memory_get_texture_cache_base_address() == texture_before);
	assert(resident->used == resident_used && bsp->used == bsp_used &&
		texture->used == texture_used);
	physical_memory_free();
	printf("provider-locked-rebind rejected=1 ready0=unchanged ready1=unchanged "
		"spans=unchanged cursors=unchanged contents=unchanged\n");
}

int main(void)
{
	test_default_layout_is_short_and_noncontiguous();
	test_existing_opt_in_recarve_binds_candidate_spans();
	test_versioned_guarded_profile();
	test_profile_rejection_is_atomic();
	test_profile_provider_failure_is_atomic();
	test_bind_rejected_after_provider_lock();
	return 0;
}
