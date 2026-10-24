/* Measure co-resident converter output with the real PS2 HP2 section loader. */
#include "core/mem.h"
#include "world/model.h"
#include "world/tex.h"

#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#define OWNER_BYTES (16u * 1024u * 1024u)
#define TARGET_TEXTURE_BYTES 4014928u
#define SCRATCH_BYTES 524288u
#define MAX_LM 32u

extern uint8_t *world_load_section_with_scratch(arena_t *, arena_t *,
	const char *, const char *, size_t *, int);

static uint8_t owner_memory[OWNER_BYTES] __attribute__((aligned(64)));
static uint8_t scratch_memory[SCRATCH_BYTES] __attribute__((aligned(64)));

void SyncDCache(const void *start, const void *end)
{
	(void)start;
	(void)end;
}

int main(int argc, char **argv)
{
	static const char *const maps[] = {"beavercreek", "bloodgulch", "boardingaction",
		"carousel", "chillout", "damnation", "hangemhigh", "longest",
		"prisoner", "putput", "ratrace", "sidewinder", "wizard"};
	arena_t owner, scratch;
	unsigned i;
	assert(argc == 2);
	for (i = 0; i < sizeof maps / sizeof maps[0]; ++i) {
		char texture_path[512], object_path[512], tag[8];
		uint8_t *section;
		size_t bytes, texture_bytes = 0, modl_bytes, otex_bytes;
		unsigned lm_count = 0, lm;
		model_section model;
		tex_section tex;
		snprintf(texture_path, sizeof texture_path, "%s/%s.tex.hp2", argv[1], maps[i]);
		snprintf(object_path, sizeof object_path, "%s/%s.obj.hp2", argv[1], maps[i]);
		arena_init(&owner, "co-resident render owner", owner_memory, sizeof owner_memory);
		arena_init(&scratch, "shared section scratch", scratch_memory, sizeof scratch_memory);
		section = world_load_section_with_scratch(&owner, &scratch, texture_path,
			"TEXS", &bytes, 0);
		assert(section && tex_open(&tex, section, bytes) == TEX_OK);
		texture_bytes += bytes;
		for (lm = 0; lm < MAX_LM; ++lm) {
			lm_section lightmap;
			snprintf(tag, sizeof tag, "LM%u", lm);
			section = world_load_section_with_scratch(&owner, &scratch, texture_path,
				tag, &bytes, 1);
			if (!section) continue;
			assert(lm_open(&lightmap, section, bytes) == TEX_OK);
			texture_bytes += bytes;
			lm_count++;
		}
		assert(lm_count > 0);
		section = world_load_section_with_scratch(&owner, &scratch, object_path,
			"MODL", &bytes, 0);
		assert(section && model_open(&model, section, bytes) == MODEL_OK);
		modl_bytes = bytes;
		section = world_load_section_with_scratch(&owner, &scratch, object_path,
			"OTEX", &bytes, 0);
		assert(section && tex_open(&tex, section, bytes) == TEX_OK);
		otex_bytes = bytes;
		assert(scratch.used == 0 && scratch.high <= scratch.cap);
		assert(owner.used == owner.high && owner.high <= owner.cap);
		printf("mp-render-owner map=%s texture_sections=%lu modl=%lu otex=%lu "
			"retained=%lu peak=%lu candidate_texture_cap=%u exceeds_candidate=%u "
			"scratch=%lu/%lu models=%u parts=%u batches=%u\n",
			maps[i], (unsigned long)texture_bytes, (unsigned long)modl_bytes,
			(unsigned long)otex_bytes, (unsigned long)owner.used,
			(unsigned long)owner.high, TARGET_TEXTURE_BYTES,
			owner.high > TARGET_TEXTURE_BYTES, (unsigned long)scratch.high,
			(unsigned long)scratch.cap, (unsigned)model.model_count,
			(unsigned)model.part_count, (unsigned)model.batch_count);
	}
	return 0;
}
