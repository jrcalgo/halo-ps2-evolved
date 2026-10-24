/* Diagnostic bridge: load converter-produced texture sections while the CE
 * candidate topology fixture still has the same map's tags/BSP resident. */
#include "core/mem.h"
#include "world/tex.h"

#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#ifndef HCU_MP_CANDIDATE_TEXTURE_BYTES
#define HCU_MP_CANDIDATE_TEXTURE_BYTES 4014936u
#endif
#define TEXTURE_OWNER_BYTES HCU_MP_CANDIDATE_TEXTURE_BYTES
#define SECTION_SCRATCH_BYTES 524288u
#define MAX_LIGHTMAP_SECTIONS 32u

extern uint8_t *world_load_section_with_scratch(arena_t *, arena_t *,
	const char *, const char *, size_t *, int);
extern void *hcu_mp_candidate_texture_storage(void);
extern void *hcu_mp_candidate_section_scratch(void);


static int range_ok(const uint8_t *p, size_t n, const uint8_t *base, size_t bytes)
{
	uintptr_t address = (uintptr_t)p, start = (uintptr_t)base;
	return address >= start && n <= bytes && address - start <= bytes - n;
}

static void validate_tex(const tex_section *tex)
{
	uint32_t i, level;
	for (i = 0; i < tex->texture_count; ++i) {
		tex_info info = tex_get(tex, i);
		const uint8_t *clut = tex_clut(tex, &info);
		assert(range_ok(clut, (size_t)info.clut_entries * 4u,
			tex->data, tex->size));
		for (level = 0; level < info.mip_count; ++level) {
			tex_mip_view mip;
			assert(tex_mip(tex, &info, level, &mip));
			assert(mip.bytes && range_ok(mip.pixels, mip.bytes,
				tex->data, tex->size));
		}
	}
}

int mp_texture_candidate_load_map(const char *map, const char *texture_root,
	unsigned cycle)
{
	arena_t owner, scratch;
	char path[256], bad_path[256], tag[8];
	uint8_t *section;
	size_t bytes, retained, normal_high, failed_high, raw_sum = 0;
	size_t texs_bytes, otex_bytes, lm_bytes = 0;
	unsigned lm_count = 0, lm_index;
	tex_section tex, otex;
	int n;
	uint8_t *texture_base = (uint8_t *)hcu_mp_candidate_texture_storage();
	uint8_t *scratch_base = (uint8_t *)hcu_mp_candidate_section_scratch();
	assert(map && texture_root && texture_base && scratch_base);
	assert(TEXTURE_OWNER_BYTES == HCU_MP_CANDIDATE_TEXTURE_BYTES &&
		SECTION_SCRATCH_BYTES == 524288u);
	/* Reuse the fixture's exact 512 KiB section-scratch slice. CE map loading
	 * has completed, and its scratch cursor is zero; no second scratch budget is
	 * introduced by the texture phase. */
	arena_init(&owner, "candidate adjacent texture owner", texture_base,
		TEXTURE_OWNER_BYTES);
	arena_init(&scratch, "candidate shared section scratch", scratch_base,
		SECTION_SCRATCH_BYTES);
	n = snprintf(path, sizeof path, "%s/%s.tex.hp2", texture_root, map);
	assert(n > 0 && (size_t)n < sizeof path);
	n = snprintf(bad_path, sizeof bad_path, "%s/%s.bad.tex.hp2", texture_root, map);
	assert(n > 0 && (size_t)n < sizeof bad_path);
	section = world_load_section_with_scratch(&owner, &scratch,
		path, "TEXS", &bytes, 0);
	assert(section && bytes >= 64u && ((uintptr_t)section & 63u) == 0);
	assert(scratch.used == 0);
	texs_bytes = bytes;
	raw_sum += bytes;
	assert(tex_open(&tex, section, bytes) == TEX_OK);
	validate_tex(&tex);
	for (lm_index = 0; lm_index < MAX_LIGHTMAP_SECTIONS; ++lm_index) {
		lm_section lm;
		snprintf(tag, sizeof tag, "LM%u", lm_index);
		section = world_load_section_with_scratch(&owner, &scratch,
			path, tag, &bytes, 1);
		assert(scratch.used == 0);
		if (!section) continue;
		assert(((uintptr_t)section & 63u) == 0);
		assert(lm_open(&lm, section, bytes) == TEX_OK);
		lm_bytes += bytes;
		raw_sum += bytes;
		lm_count++;
	}
	assert(lm_count > 0);
	n = snprintf(path, sizeof path, "%s/%s.obj.hp2", texture_root, map);
	assert(n > 0 && (size_t)n < sizeof path);
	section = world_load_section_with_scratch(&owner, &scratch,
		path, "OTEX", &bytes, 0);
	assert(section && bytes >= 64u && ((uintptr_t)section & 63u) == 0);
	assert(scratch.used == 0);
	otex_bytes = bytes;
	raw_sum += bytes;
	assert(tex_open(&otex, section, bytes) == TEX_OK);
	validate_tex(&otex);
	retained = owner.used;
	normal_high = owner.high;
	assert(normal_high <= owner.cap && retained <= owner.cap);
	assert(scratch.high <= scratch.cap);
	{
		size_t failed_size = 0;
		uint8_t *failed = world_load_section_with_scratch(&owner, &scratch,
			bad_path, "TEXS", &failed_size, 0);
		assert(!failed && failed_size == 0);
		assert(owner.used == retained && owner.high <= owner.cap);
		assert(scratch.used == 0 && scratch.high <= scratch.cap);
		failed_high = owner.high;
	}
	assert(tex_open(&tex, tex.data, tex.size) == TEX_OK);
	assert(tex_open(&otex, otex.data, otex.size) == TEX_OK);
	assert(owner.used == retained);
	printf("mp-combined-texture map=%s cycle=%u texs=%zu lm_bytes=%zu lm_count=%u otex=%zu raw=%zu retained=%zu align_pad=%zu peak=%zu rollback_peak=%zu scratch=%zu/%zu rollback=crc-safe\n",
		map, cycle, texs_bytes, lm_bytes, lm_count, otex_bytes, raw_sum,
		retained, retained - raw_sum, normal_high, failed_high,
		scratch.high, scratch.cap);
	return 0;
}
