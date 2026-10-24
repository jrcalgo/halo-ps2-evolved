/* Host exercise of halo-ps2's real HP2 section loader and TEXS/LMAP readers.
 * The runner supplies production-converter packs for one stock MP map at a time. */
#include "core/mem.h"
#include "stream/file.h"
#include "world/tex.h"

#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#define TEXTURE_CAPACITY 4014936u
#define SECTION_SCRATCH_CAPACITY 524288u
#define GUARD_BYTES 64u
#define MAP_COUNT 13u
#define MAX_LIGHTMAP_SECTIONS 32u

extern uint8_t *world_load_section_with_scratch(arena_t *owner,
	arena_t *scratch, const char *path, const char *tag, size_t *raw_size,
	int optional);

typedef struct {
	uint8_t before[GUARD_BYTES];
	uint8_t texture[TEXTURE_CAPACITY] __attribute__((aligned(64)));
	uint8_t after[GUARD_BYTES];
} texture_store_t;

typedef struct {
	uint8_t before[GUARD_BYTES];
	uint8_t scratch[SECTION_SCRATCH_CAPACITY] __attribute__((aligned(64)));
	uint8_t after[GUARD_BYTES];
} scratch_store_t;

static texture_store_t texture_store __attribute__((aligned(64)));
static scratch_store_t scratch_store __attribute__((aligned(64)));

void SyncDCache(const void *start, const void *end)
{
	(void)start;
	(void)end;
}

static const char *const map_names[MAP_COUNT] = {
	"beavercreek", "bloodgulch", "boardingaction", "carousel", "chillout",
	"damnation", "hangemhigh", "longest", "prisoner", "putput", "ratrace",
	"sidewinder", "wizard"
};

static void guards_init(void)
{
	memset(texture_store.before, 0xA5, sizeof texture_store.before);
	memset(texture_store.after, 0x5A, sizeof texture_store.after);
	memset(scratch_store.before, 0x3C, sizeof scratch_store.before);
	memset(scratch_store.after, 0xC3, sizeof scratch_store.after);
}

static void guards_check(void)
{
	unsigned i;
	for (i = 0; i < GUARD_BYTES; ++i) {
		assert(texture_store.before[i] == 0xA5);
		assert(texture_store.after[i] == 0x5A);
		assert(scratch_store.before[i] == 0x3C);
		assert(scratch_store.after[i] == 0xC3);
	}
}

static int in_range(const uint8_t *p, size_t n, const uint8_t *base,
	size_t bytes)
{
	uintptr_t address = (uintptr_t)p;
	uintptr_t start = (uintptr_t)base;
	return address >= start && n <= bytes && address - start <= bytes - n;
}

static void validate_tex(const tex_section *tex)
{
	uint32_t i, level;
	for (i = 0; i < tex->texture_count; ++i) {
		tex_info info = tex_get(tex, i);
		const uint8_t *clut = tex_clut(tex, &info);
		assert(in_range(clut, (size_t)info.clut_entries * 4u,
			tex->data, tex->size));
		for (level = 0; level < info.mip_count; ++level) {
			tex_mip_view mip;
			assert(tex_mip(tex, &info, level, &mip));
			assert(mip.bytes && in_range(mip.pixels, mip.bytes,
				tex->data, tex->size));
		}
	}
}

static void validate_lm(const lm_section *lm, uint32_t *page_count,
	uint64_t *pixel_bytes)
{
	uint32_t i;
	for (i = 0; i < lm->page_count; ++i) {
		lm_page_info page;
		if (!lm_get_page(lm, i, &page)) continue;
		assert(page.pixel_bytes && in_range(page.pixels, page.pixel_bytes,
			lm->data, lm->size));
		(*page_count)++;
		*pixel_bytes += page.pixel_bytes;
	}
}

static uint8_t *load_required(arena_t *owner, arena_t *scratch,
	const char *path, const char *tag, size_t *bytes)
{
	uint8_t *section = world_load_section_with_scratch(owner, scratch,
		path, tag, bytes, 0);
	assert(section && *bytes >= 64u);
	assert(((uintptr_t)section & 63u) == 0);
	assert(scratch->used == 0);
	return section;
}

int main(int argc, char **argv)
{
	unsigned map;
	assert(argc == 2);
	setvbuf(stdout, NULL, _IONBF, 0);
	assert(file_set_default_root("./"));
	guards_init();
	for (map = 0; map < MAP_COUNT; ++map) {
		arena_t owner, scratch;
		char tex_path[256], obj_path[256], bad_path[256], tag[8];
		uint8_t *section;
		size_t section_bytes, texs_bytes, object_bytes, normal_high, failure_high;
		size_t retained, raw_section_bytes, lightmap_section_bytes = 0;
		uint32_t lightmap_pages = 0, loaded_lms = 0;
		uint64_t lightmap_pixel_bytes = 0;
		tex_section tex, object_tex;
		unsigned lm_index;
		int n;
		n = snprintf(tex_path, sizeof tex_path, "%s/%s.tex.hp2", argv[1], map_names[map]);
		assert(n > 0 && (size_t)n < sizeof tex_path);
		n = snprintf(obj_path, sizeof obj_path, "%s/%s.obj.hp2", argv[1], map_names[map]);
		assert(n > 0 && (size_t)n < sizeof obj_path);
		n = snprintf(bad_path, sizeof bad_path, "%s/%s.bad.tex.hp2", argv[1], map_names[map]);
		assert(n > 0 && (size_t)n < sizeof bad_path);
		arena_init(&owner, "candidate texture owner", texture_store.texture,
			sizeof texture_store.texture);
		arena_init(&scratch, "section decode scratch", scratch_store.scratch,
			sizeof scratch_store.scratch);

		section = load_required(&owner, &scratch, tex_path, "TEXS", &section_bytes);
		texs_bytes = section_bytes;
		raw_section_bytes = section_bytes;
		assert(tex_open(&tex, section, section_bytes) == TEX_OK);
		validate_tex(&tex);
		for (lm_index = 0; lm_index < MAX_LIGHTMAP_SECTIONS; ++lm_index) {
			lm_section lm;
			snprintf(tag, sizeof tag, "LM%u", lm_index);
			section = world_load_section_with_scratch(&owner, &scratch,
				tex_path, tag, &section_bytes, 1);
			assert(scratch.used == 0);
			if (!section) continue;
			assert(((uintptr_t)section & 63u) == 0);
			assert(lm_open(&lm, section, section_bytes) == TEX_OK);
			lightmap_section_bytes += section_bytes;
			raw_section_bytes += section_bytes;
			validate_lm(&lm, &lightmap_pages, &lightmap_pixel_bytes);
			loaded_lms++;
		}
		assert(loaded_lms > 0);

		section = load_required(&owner, &scratch, obj_path, "OTEX", &section_bytes);
		object_bytes = section_bytes;
		raw_section_bytes += section_bytes;
		assert(tex_open(&object_tex, section, section_bytes) == TEX_OK);
		validate_tex(&object_tex);
		retained = owner.used;
		normal_high = owner.high;
		assert(normal_high <= owner.cap && retained <= owner.cap);
		assert(scratch.high <= scratch.cap);
		guards_check();

		/* Corrupt only the TEXS CRC in a generated test pack. The real loader
		 * writes/decompresses the section, detects CRC failure, and must rewind
		 * the owner cursor while preserving all already-published sections. */
		{
			size_t failed_size = 0;
			uint8_t *failed = world_load_section_with_scratch(&owner,
				&scratch, bad_path, "TEXS", &failed_size, 0);
			assert(!failed && failed_size == 0);
			assert(owner.used == retained && owner.high <= owner.cap);
			assert(scratch.used == 0 && scratch.high <= scratch.cap);
			failure_high = owner.high;
		}
		assert(tex_open(&tex, tex.data, tex.size) == TEX_OK);
		assert(tex_open(&object_tex, object_tex.data, object_tex.size) == TEX_OK);
		guards_check();
		assert(owner.used == retained);
		printf("mp-texture-runtime map=%s texs=%zu otex=%zu lm_section_bytes=%zu lm_sections=%u lm_pages=%u lm_pixels=%llu raw_sections=%zu retained=%zu alignment_overhead=%zu normal_peak=%zu rollback_peak=%zu scratch_peak=%zu/%zu rollback=crc-rejected-safe\n",
			map_names[map], texs_bytes, object_bytes, lightmap_section_bytes, loaded_lms,
			lightmap_pages, (unsigned long long)lightmap_pixel_bytes,
			raw_section_bytes, retained, retained - raw_section_bytes,
			normal_high, failure_high, scratch.high, scratch.cap);
	}
	guards_check();
	printf("mp-texture-runtime all=%u maps capacity=%u no-canary-overwrite; section loader/TEXS/LMAP checks passed (host diagnostic)\n",
		MAP_COUNT, TEXTURE_CAPACITY);
	return 0;
}
