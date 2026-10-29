#include "stream/hcu_memory_profile.h"

#include "cache/physical_memory_map.h"
#include "halo_ps2_limits.h"

#include <limits.h>
#include <stdint.h>
#include <string.h>

unsigned long tag_validate_claims_buffer_size(void);

#define HCU_PROFILE_ALIGN 16u
#define HCU_PROFILE_CLAIM_BITS 32u
#define HCU_PROFILE_CLAIM_WORD_BYTES 4u
#define HCU_PROFILE_RESIDENCY_SEGMENT_BYTES 65536u

static int aligned_capacity(size_t bytes)
{
	return bytes != 0 && (bytes & (HCU_PROFILE_ALIGN - 1u)) == 0;
}

static int checked_end(const void *base, size_t bytes, uintptr_t *end)
{
	uintptr_t start = (uintptr_t)base;
	if (!base || bytes > UINTPTR_MAX - start) return 0;
	*end = start + bytes;
	return 1;
}

static int claims_capacity(size_t tag_bytes, size_t bsp_bytes, size_t *result)
{
	size_t address_bytes, words;
	if (tag_bytes > SIZE_MAX - bsp_bytes) return 0;
	address_bytes = tag_bytes + bsp_bytes;
	if (address_bytes > SIZE_MAX - (HCU_PROFILE_CLAIM_BITS - 1u)) return 0;
	words = (address_bytes + HCU_PROFILE_CLAIM_BITS - 1u) /
		HCU_PROFILE_CLAIM_BITS;
	if (words > SIZE_MAX / HCU_PROFILE_CLAIM_WORD_BYTES) return 0;
	*result = words * HCU_PROFILE_CLAIM_WORD_BYTES;
	return *result != 0;
}

int hcu_memory_profile_plan_v1(const mem_layout_v2_t *layout,
	const hcu_memory_profile_t *profile, hcu_memory_partition_t *partition)
{
	const arena_t *resident, *bsp, *texture, *dynamic, *audio;
	hcu_memory_partition_t candidate;
	uintptr_t bsp_end, texture_end, outer_guard, tag_end, bsp_start;
	size_t combined_bytes, map_parent_bytes, render_parent_bytes, claims_bytes;
	if (!layout || !profile || !partition ||
		profile->version != HCU_MEMORY_PROFILE_VERSION_1 ||
		!aligned_capacity(profile->tag_cache_bytes) ||
		!aligned_capacity(profile->structure_bsp_bytes) ||
		!aligned_capacity(profile->render_texture_bytes) ||
		(profile->residency_bytes &&
			profile->residency_bytes % HCU_PROFILE_RESIDENCY_SEGMENT_BYTES != 0)) return -1;
	resident = mem_layout_v2_get_const(layout, MEM_LAYOUT_V2_RESIDENT_GAMEPLAY);
	bsp = mem_layout_v2_get_const(layout, MEM_LAYOUT_V2_CURRENT_BSP);
	texture = mem_layout_v2_get_const(layout, MEM_LAYOUT_V2_TEXTURE_CACHE);
	dynamic = mem_layout_v2_get_const(layout, MEM_LAYOUT_V2_DYNAMIC_SIMULATION);
	audio = mem_layout_v2_get_const(layout, MEM_LAYOUT_V2_AUDIO);
	if (!resident || !bsp || !texture || !dynamic || !audio || resident->used ||
		bsp->used || texture->used || dynamic->used || audio->used ||
		((uintptr_t)bsp->base & (HCU_PROFILE_ALIGN - 1u)) ||
		((uintptr_t)texture->base & (HCU_PROFILE_ALIGN - 1u)) ||
		!aligned_capacity(bsp->cap) || !aligned_capacity(texture->cap) ||
		!checked_end(bsp->base, bsp->cap, &bsp_end) ||
		!checked_end(texture->base, texture->cap, &texture_end)) return -1;
	/* The source has a 16-byte canary between adjacent BSP and texture parents.
	 * Treat the payload capacities as one span and move that canary to the new
	 * map/render boundary. The terminal canary remains at the old texture end. */
	if (!layout->guards[2] || !layout->guards[3] ||
		(uintptr_t)layout->guards[2] != bsp_end ||
	bsp_end > UINTPTR_MAX - MEM_LAYOUT_V2_GUARD_BYTES ||
		(uintptr_t)texture->base != bsp_end + MEM_LAYOUT_V2_GUARD_BYTES ||
		(uintptr_t)layout->guards[3] != texture_end ||
	bsp->cap > SIZE_MAX - texture->cap) return -1;
	combined_bytes = bsp->cap + texture->cap;
	if (profile->tag_cache_bytes > SIZE_MAX - MEM_LAYOUT_V2_GUARD_BYTES ||
		profile->tag_cache_bytes + MEM_LAYOUT_V2_GUARD_BYTES >
			SIZE_MAX - profile->structure_bsp_bytes) return -1;
	map_parent_bytes = profile->tag_cache_bytes +
		MEM_LAYOUT_V2_GUARD_BYTES + profile->structure_bsp_bytes;
	if (map_parent_bytes > combined_bytes) return -1;
	render_parent_bytes = combined_bytes - map_parent_bytes;
	if (profile->render_texture_bytes > render_parent_bytes) return -1;
	/* Residency sits after the render span and one guard, inside the same texture parent. */
	if (profile->residency_bytes &&
		(profile->residency_bytes > render_parent_bytes ||
		profile->render_texture_bytes + MEM_LAYOUT_V2_GUARD_BYTES >
			render_parent_bytes - profile->residency_bytes)) return -1;
	tag_end = (uintptr_t)bsp->base + profile->tag_cache_bytes;
	if (tag_end < (uintptr_t)bsp->base ||
		tag_end > UINTPTR_MAX - MEM_LAYOUT_V2_GUARD_BYTES) return -1;
	bsp_start = tag_end + MEM_LAYOUT_V2_GUARD_BYTES;
	outer_guard = (uintptr_t)bsp->base + map_parent_bytes;
	if (outer_guard < (uintptr_t)bsp->base ||
		outer_guard > UINTPTR_MAX - MEM_LAYOUT_V2_GUARD_BYTES ||
		outer_guard + MEM_LAYOUT_V2_GUARD_BYTES > texture_end ||
		bsp_start > outer_guard ||
		profile->structure_bsp_bytes > outer_guard - bsp_start ||
		!claims_capacity(profile->tag_cache_bytes,
			profile->structure_bsp_bytes, &claims_bytes) ||
		HALO_PORT_GAME_STATE_SIZE > SIZE_MAX - claims_bytes ||
		HALO_PORT_GAME_STATE_SIZE + claims_bytes > resident->cap)
		return -1;
	memset(&candidate, 0, sizeof(candidate));
	candidate.tag_cache_base = bsp->base;
	candidate.structure_bsp_base = (void *)bsp_start;
	candidate.tag_bsp_guard = (void *)tag_end;
	candidate.render_texture_base = (void *)(outer_guard +
		MEM_LAYOUT_V2_GUARD_BYTES);
	candidate.map_parent_bytes = map_parent_bytes;
	candidate.render_parent_bytes = render_parent_bytes;
	candidate.tag_cache_bytes = profile->tag_cache_bytes;
	candidate.structure_bsp_bytes = profile->structure_bsp_bytes;
	candidate.render_texture_bytes = profile->render_texture_bytes;
	candidate.tag_bsp_guard_bytes = MEM_LAYOUT_V2_GUARD_BYTES;
	candidate.map_render_guard_bytes = MEM_LAYOUT_V2_GUARD_BYTES;
	candidate.claims_scratch_bytes = claims_bytes;
	if (profile->residency_bytes) {
		candidate.residency_guard_bytes = MEM_LAYOUT_V2_GUARD_BYTES;
		candidate.residency_bytes = profile->residency_bytes;
		candidate.residency_base = (uint8_t *)candidate.render_texture_base +
			profile->render_texture_bytes + MEM_LAYOUT_V2_GUARD_BYTES;
	}
	/* All capacities and bases are 16-byte aligned; no hidden pad is charged. */
	*partition = candidate;
	return 0;
}

int hcu_memory_bind_profile_v1(mem_layout_v2_t *layout,
	const hcu_memory_profile_t *profile, hcu_memory_partition_t *partition)
{
	mem_layout_v2_t trial;
	arena_t *resident, *bsp, *texture, *audio, *dynamic;
	hcu_memory_partition_t plan;
	void *game_state, *tag, *inner_guard, *structure_bsp, *render, *claims;
	void *residency_guard = NULL, *residency = NULL;
	unsigned long claims_bytes;
	if (!layout || !partition || !physical_memory_bindings_clean() ||
		hcu_memory_profile_plan_v1(layout, profile, &plan) != 0) return -1;
	trial = *layout;
	resident = mem_layout_v2_get(&trial, MEM_LAYOUT_V2_RESIDENT_GAMEPLAY);
	bsp = mem_layout_v2_get(&trial, MEM_LAYOUT_V2_CURRENT_BSP);
	texture = mem_layout_v2_get(&trial, MEM_LAYOUT_V2_TEXTURE_CACHE);
	audio = mem_layout_v2_get(&trial, MEM_LAYOUT_V2_AUDIO);
	dynamic = mem_layout_v2_get(&trial, MEM_LAYOUT_V2_DYNAMIC_SIMULATION);
	bsp->cap = plan.map_parent_bytes;
	texture->base = (uint8_t *)plan.render_texture_base;
	texture->cap = plan.render_parent_bytes;
	trial.guards[2] = bsp->base + bsp->cap;
	game_state = arena_alloc(resident, HALO_PORT_GAME_STATE_SIZE, HCU_PROFILE_ALIGN);
	tag = arena_alloc(bsp, plan.tag_cache_bytes, HCU_PROFILE_ALIGN);
	inner_guard = arena_alloc(bsp, MEM_LAYOUT_V2_GUARD_BYTES,
		HCU_PROFILE_ALIGN);
	structure_bsp = arena_alloc(bsp, plan.structure_bsp_bytes,
		HCU_PROFILE_ALIGN);
	render = arena_alloc(texture, plan.render_texture_bytes, HCU_PROFILE_ALIGN);
	claims = game_state ? arena_alloc(resident, plan.claims_scratch_bytes,
		HCU_PROFILE_ALIGN) : NULL;
	if (plan.residency_bytes) {
		residency_guard = arena_alloc(texture, MEM_LAYOUT_V2_GUARD_BYTES,
			HCU_PROFILE_ALIGN);
		residency = residency_guard ? arena_alloc(texture, plan.residency_bytes,
			HCU_PROFILE_ALIGN) : NULL;
		if (!residency || residency != plan.residency_base) goto fail;
	}
	if (!game_state || tag != plan.tag_cache_base ||
		inner_guard != plan.tag_bsp_guard ||
		structure_bsp != plan.structure_bsp_base ||
		render != plan.render_texture_base || !claims ||
		!physical_memory_bind_game_state(game_state, HALO_PORT_GAME_STATE_SIZE) ||
		!physical_memory_bind_tag_cache(tag, (unsigned long)plan.tag_cache_bytes) ||
		!physical_memory_bind_structure_bsp_cache(structure_bsp,
			(unsigned long)plan.structure_bsp_bytes) ||
		!physical_memory_bind_texture_cache(render,
			(unsigned long)plan.render_texture_bytes) ||
		!physical_memory_bind_sound_cache(audio->base,
			(unsigned long)audio->cap) ||
		!physical_memory_bind_malloc_arena(dynamic->base,
			(unsigned long)dynamic->cap)) goto fail;
	/* The real validator derives this from the newly configured tag+BSP stores.
	 * Require the explicit v1 formula to match before reserving its scratch. */
	claims_bytes = tag_validate_claims_buffer_size();
	if (claims_bytes != plan.claims_scratch_bytes ||
		!physical_memory_bind_tag_validation_scratch(claims, claims_bytes))
		goto fail;
	memset(inner_guard, trial.guard_pattern, MEM_LAYOUT_V2_GUARD_BYTES);
	memset(trial.guards[2], trial.guard_pattern, MEM_LAYOUT_V2_GUARD_BYTES);
	if (residency_guard)
		memset(residency_guard, trial.guard_pattern, MEM_LAYOUT_V2_GUARD_BYTES);
	*layout = trial;
	plan.claims_scratch_base = claims;
	*partition = plan;
	return 0;

fail:
	physical_memory_free();
	return -1;
}

int hcu_memory_partition_guards_intact(const mem_layout_v2_t *layout,
	const hcu_memory_partition_t *partition)
{
	const arena_t *resident, *bsp, *texture;
	uintptr_t bsp_end, texture_end, tag_end, inner_guard_end, render_end;
	uintptr_t claims_start, claims_end, resident_end, used_end;
	size_t total_map;
	size_t i;
	if (!layout || !partition) return 0;
	resident = mem_layout_v2_get_const(layout, MEM_LAYOUT_V2_RESIDENT_GAMEPLAY);
	bsp = mem_layout_v2_get_const(layout, MEM_LAYOUT_V2_CURRENT_BSP);
	texture = mem_layout_v2_get_const(layout, MEM_LAYOUT_V2_TEXTURE_CACHE);
	if (!resident || !bsp || !texture || !partition->tag_cache_base ||
		!partition->structure_bsp_base || !partition->tag_bsp_guard ||
		!partition->render_texture_base || !partition->claims_scratch_base ||
		partition->bsp_alignment_bytes || partition->texture_alignment_bytes ||
		partition->tag_bsp_guard_bytes != MEM_LAYOUT_V2_GUARD_BYTES ||
		partition->map_render_guard_bytes != MEM_LAYOUT_V2_GUARD_BYTES ||
		partition->tag_cache_base != bsp->base ||
		partition->map_parent_bytes != bsp->cap ||
		partition->render_parent_bytes != texture->cap ||
		partition->render_texture_base != texture->base ||
		partition->render_texture_bytes + partition->residency_guard_bytes +
			partition->residency_bytes != texture->used ||
		partition->map_parent_bytes != bsp->used ||
		partition->tag_cache_bytes > SIZE_MAX - partition->tag_bsp_guard_bytes ||
		partition->tag_cache_bytes + partition->tag_bsp_guard_bytes >
			SIZE_MAX - partition->structure_bsp_bytes) return 0;
	total_map = partition->tag_cache_bytes + partition->tag_bsp_guard_bytes +
		partition->structure_bsp_bytes;
	if (total_map != partition->map_parent_bytes ||
		!checked_end(bsp->base, bsp->cap, &bsp_end) ||
		!checked_end(texture->base, texture->cap, &texture_end) ||
		!checked_end(partition->tag_cache_base, partition->tag_cache_bytes,
			&tag_end) ||
		!checked_end(partition->tag_bsp_guard,
			partition->tag_bsp_guard_bytes, &inner_guard_end) ||
		!checked_end(partition->render_texture_base,
			partition->render_texture_bytes, &render_end) ||
		!checked_end(resident->base, resident->cap, &resident_end) ||
		!checked_end(resident->base, resident->used, &used_end) ||
		!checked_end(partition->claims_scratch_base,
			partition->claims_scratch_bytes, &claims_end)) return 0;
	claims_start = (uintptr_t)partition->claims_scratch_base;
	if ((uintptr_t)layout->guards[2] != bsp_end ||
		(uintptr_t)layout->guards[3] != texture_end ||
		bsp_end > UINTPTR_MAX - MEM_LAYOUT_V2_GUARD_BYTES ||
		(uintptr_t)texture->base != bsp_end + MEM_LAYOUT_V2_GUARD_BYTES ||
		!mem_layout_v2_guards_intact(layout) ||
		partition->tag_bsp_guard != (void *)tag_end ||
		partition->structure_bsp_base != (void *)inner_guard_end ||
		(uintptr_t)partition->render_texture_base < bsp_end +
			MEM_LAYOUT_V2_GUARD_BYTES ||
		render_end > texture_end ||
		(partition->residency_bytes &&
			(!partition->residency_base ||
			(uintptr_t)partition->residency_base != render_end +
				partition->residency_guard_bytes ||
			(uintptr_t)partition->residency_base + partition->residency_bytes >
				texture_end)) ||
		claims_start < (uintptr_t)resident->base || claims_end > resident_end ||
		claims_end > used_end ||
		!partition->claims_scratch_bytes) return 0;
	for (i = 0; i < partition->tag_bsp_guard_bytes; i++)
		if (((const uint8_t *)partition->tag_bsp_guard)[i] !=
			layout->guard_pattern) return 0;
	if (partition->residency_guard_bytes)
		for (i = 0; i < partition->residency_guard_bytes; i++)
			if (((const uint8_t *)render_end)[i] != layout->guard_pattern) return 0;
	return 1;
}

/* Generated rows plus a static, package-derived bots-sidewinder candidate.
 * The candidate's 10 MiB span is a partition plan, not a measured fit claim;
 * see tests/fixtures/hcu_bots_sidewinder_partition_candidate.json. */
static const hcu_memory_partition_entry_t hcu_partition_table_v2[] = {
	{ "beavercreek_marine_shotgun_4p4bot", { HCU_MEMORY_PROFILE_VERSION_1, 6838928, 730208, 4489456, 1048576 } }, /* marine_shotgun */
	{ "beavercreek_mounted_gunner_4p4bot", { HCU_MEMORY_PROFILE_VERSION_1, 4619936, 730208, 6708448, 1048576 } }, /* mounted_gunner */
	{ "bloodgulch_marine_shotgun_4p4bot", { HCU_MEMORY_PROFILE_VERSION_1, 7014976, 1303104, 3740512, 1048576 } }, /* marine_shotgun */
	{ "bloodgulch_mounted_gunner_4p4bot", { HCU_MEMORY_PROFILE_VERSION_1, 4795984, 1303104, 5959504, 1048576 } }, /* mounted_gunner */
	{ "boardingaction_marine_shotgun_4p4bot", { HCU_MEMORY_PROFILE_VERSION_1, 6892096, 1354160, 3812336, 1048576 } }, /* marine_shotgun */
	{ "boardingaction_mounted_gunner_4p4bot", { HCU_MEMORY_PROFILE_VERSION_1, 4673104, 1354160, 6031328, 1048576 } }, /* mounted_gunner */
	{ "carousel_marine_shotgun_4p4bot", { HCU_MEMORY_PROFILE_VERSION_1, 6811648, 515248, 4731696, 1048576 } }, /* marine_shotgun */
	{ "carousel_mounted_gunner_4p4bot", { HCU_MEMORY_PROFILE_VERSION_1, 4592656, 515248, 6950688, 1048576 } }, /* mounted_gunner */
	{ "chillout_marine_shotgun_4p4bot", { HCU_MEMORY_PROFILE_VERSION_1, 6786560, 573424, 4698608, 1048576 } }, /* marine_shotgun */
	{ "chillout_mounted_gunner_4p4bot", { HCU_MEMORY_PROFILE_VERSION_1, 4567568, 573424, 6917600, 1048576 } }, /* mounted_gunner */
	{ "damnation_marine_shotgun_4p4bot", { HCU_MEMORY_PROFILE_VERSION_1, 6881632, 1326816, 3850144, 1048576 } }, /* marine_shotgun */
	{ "damnation_mounted_gunner_4p4bot", { HCU_MEMORY_PROFILE_VERSION_1, 4662640, 1326816, 6069136, 1048576 } }, /* mounted_gunner */
	{ "hangemhigh_marine_shotgun_4p4bot", { HCU_MEMORY_PROFILE_VERSION_1, 6778944, 595856, 4683792, 1048576 } }, /* marine_shotgun */
	{ "hangemhigh_mounted_gunner_4p4bot", { HCU_MEMORY_PROFILE_VERSION_1, 4559952, 595856, 6902784, 1048576 } }, /* mounted_gunner */
	{ "longest_marine_shotgun_4p4bot", { HCU_MEMORY_PROFILE_VERSION_1, 6797024, 377392, 4884176, 1048576 } }, /* marine_shotgun */
	{ "longest_mounted_gunner_4p4bot", { HCU_MEMORY_PROFILE_VERSION_1, 4578032, 377392, 7103168, 1048576 } }, /* mounted_gunner */
	{ "prisoner_marine_shotgun_4p4bot", { HCU_MEMORY_PROFILE_VERSION_1, 6774176, 888336, 4396080, 1048576 } }, /* marine_shotgun */
	{ "prisoner_mounted_gunner_4p4bot", { HCU_MEMORY_PROFILE_VERSION_1, 4555184, 888336, 6615072, 1048576 } }, /* mounted_gunner */
	{ "putput_marine_shotgun_4p4bot", { HCU_MEMORY_PROFILE_VERSION_1, 6782240, 1643056, 3633296, 1048576 } }, /* marine_shotgun */
	{ "putput_mounted_gunner_4p4bot", { HCU_MEMORY_PROFILE_VERSION_1, 4563248, 1643056, 5852288, 1048576 } }, /* mounted_gunner */
	{ "ratrace_marine_shotgun_4p4bot", { HCU_MEMORY_PROFILE_VERSION_1, 6804448, 550816, 4703328, 1048576 } }, /* marine_shotgun */
	{ "ratrace_mounted_gunner_4p4bot", { HCU_MEMORY_PROFILE_VERSION_1, 4585472, 550816, 6922304, 1048576 } }, /* mounted_gunner */
	{ "sidewinder_marine_shotgun_4p4bot", { HCU_MEMORY_PROFILE_VERSION_1, 6913936, 1993744, 3150912, 1048576 } }, /* marine_shotgun */
	{ "sidewinder_mounted_gunner_4p4bot", { HCU_MEMORY_PROFILE_VERSION_1, 4694944, 1993744, 5369904, 1048576 } }, /* mounted_gunner */
	{ "bots_sidewinder", { HCU_MEMORY_PROFILE_VERSION_1, 4584880, 1993744, 5479968, 1048576 } }, /* static package-derived candidate; not measured fit */
	{ "wizard_marine_shotgun_4p4bot", { HCU_MEMORY_PROFILE_VERSION_1, 6792912, 556944, 4708736, 1048576 } }, /* marine_shotgun */
	{ "wizard_mounted_gunner_4p4bot", { HCU_MEMORY_PROFILE_VERSION_1, 4573920, 556944, 6927728, 1048576 } }, /* mounted_gunner */
	{ "ui", { HCU_MEMORY_PROFILE_VERSION_1, 789152, 2288, 11267152, 1048576 } }, /* ui */
};

const hcu_memory_profile_t *hcu_memory_partition_select_v2(const char *name)
{
	unsigned i;
	if (!name) return NULL;
	for (i = 0; i < hcu_memory_partition_count_v2(); i++)
		if (strcmp(hcu_partition_table_v2[i].name, name) == 0)
			return &hcu_partition_table_v2[i].profile;
	return NULL;
}

unsigned hcu_memory_partition_count_v2(void)
{
	return (unsigned)(sizeof(hcu_partition_table_v2) / sizeof(hcu_partition_table_v2[0]));
}

const hcu_memory_partition_entry_t *hcu_memory_partition_entry_v2(unsigned index)
{
	return index < hcu_memory_partition_count_v2() ? &hcu_partition_table_v2[index] : NULL;
}
