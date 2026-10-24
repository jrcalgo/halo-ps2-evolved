/* Candidate-owner and GS-cache stress using the real halo-ps2 section parser/cache. */
#include "core/mem.h"
#include "render/texcache.h"
#include "world/model.h"
#include "world/tex.h"

#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#define OWNER_CAP 4014928u
#define SCRATCH_CAP 524288u
#define GUARD 64u
#define MAX_LM 32u
#define CACHE_PAGES 270u
#define UPLOAD_BUDGET (1536u * 1024u)
#define WORD_GUARD 0xA7u

extern uint8_t *world_load_section_with_scratch(arena_t *, arena_t *,
	const char *, const char *, size_t *, int);

static uint8_t owner_mem[OWNER_CAP + 2u * GUARD] __attribute__((aligned(64)));
static uint8_t scratch_mem[SCRATCH_CAP + 2u * GUARD] __attribute__((aligned(64)));

void SyncDCache(const void *start, const void *end) { (void)start; (void)end; }

static void guards_init(uint8_t *p, size_t cap)
{
	memset(p, WORD_GUARD, GUARD);
	memset(p + GUARD + cap, WORD_GUARD, GUARD);
}

static void guards_check(const uint8_t *p, size_t cap)
{
	size_t i;
	for (i = 0; i < GUARD; ++i) {
		assert(p[i] == WORD_GUARD);
		assert(p[GUARD + cap + i] == WORD_GUARD);
	}
}

static unsigned pages_for(unsigned w, unsigned h, unsigned psm)
{
	unsigned tbw = (w + 63u) / 64u, page_h = psm == TEX_PSMT4 ? 128u : 64u;
	if (!tbw) tbw = 1;
	return ((tbw + 1u) / 2u) * ((h + page_h - 1u) / page_h);
}

static void request_resource(tc_t *cache, unsigned key, unsigned w, unsigned h,
	unsigned psm, uint32_t pixel_bytes, uint32_t clut_bytes,
	uint32_t *uploads, uint32_t *hits, uint32_t *deferred, uint32_t *full)
{
	const tc_entry *entry = NULL;
	tc_result result = tc_acquire(cache, key, pages_for(w, h, psm),
		pixel_bytes + clut_bytes, &entry);
	(void)entry;
	if (result == TC_UPLOAD) { ++*uploads; tc_commit_claim(cache, key); }
	else if (result == TC_HIT) ++*hits;
	else if (result == TC_DEFER) ++*deferred;
	else ++*full;
}

static size_t load_section(arena_t *owner, arena_t *scratch, const char *path,
	const char *tag, int optional, uint8_t **out)
{
	size_t bytes = 0;
	*out = world_load_section_with_scratch(owner, scratch, path, tag, &bytes, optional);
	return bytes;
}

int main(int argc, char **argv)
{
	static const char *const maps[] = {"beavercreek", "bloodgulch", "boardingaction",
		"carousel", "chillout", "damnation", "hangemhigh", "longest",
		"prisoner", "putput", "ratrace", "sidewinder", "wizard"};
	unsigned map_i;
	assert(argc == 2);
	for (map_i = 0; map_i < sizeof maps / sizeof maps[0]; ++map_i) {
		arena_t owner, scratch;
		char tex_path[512], obj_path[512], tag[8];
		uint8_t *section;
		size_t bytes;
		tex_section bsp_tex, obj_tex;
		lm_section lm;
		model_section model;
		tc_t cache;
		unsigned lm_count = 0, resource_count = 0, lm_idx, pass;
		uint32_t uploads[2] = {0, 0}, hits[2] = {0, 0};
		uint32_t deferred[2] = {0, 0}, full[2] = {0, 0};
		snprintf(tex_path, sizeof tex_path, "%s/%s.tex.hp2", argv[1], maps[map_i]);
		snprintf(obj_path, sizeof obj_path, "%s/%s.obj.hp2", argv[1], maps[map_i]);
		guards_init(owner_mem, OWNER_CAP);
		guards_init(scratch_mem, SCRATCH_CAP);
		arena_init(&owner, "candidate render owner", owner_mem + GUARD, OWNER_CAP);
		arena_init(&scratch, "shared section scratch", scratch_mem + GUARD, SCRATCH_CAP);

		section = NULL;
		bytes = load_section(&owner, &scratch, tex_path, "TEXS", 0, &section);
		assert(section && tex_open(&bsp_tex, section, bytes) == TEX_OK);
		for (lm_idx = 0; lm_idx < MAX_LM; ++lm_idx) {
			lm_section candidate;
			snprintf(tag, sizeof tag, "LM%u", lm_idx);
			section = NULL;
			bytes = load_section(&owner, &scratch, tex_path, tag, 1, &section);
			if (!section) continue;
			assert(lm_open(&candidate, section, bytes) == TEX_OK);
			if (lm_idx == 0) lm = candidate;
			++lm_count;
		}
		assert(lm_count > 0);
		section = NULL;
		bytes = load_section(&owner, &scratch, obj_path, "MODL", 0, &section);
		assert(section && model_open(&model, section, bytes) == MODEL_OK);
		section = NULL;
		bytes = load_section(&owner, &scratch, obj_path, "OTEX", 0, &section);
		assert(section && tex_open(&obj_tex, section, bytes) == TEX_OK);

		/* Same key order as bsp_render.c: BSP textures, lightmap slots, object textures. */
		resource_count = bsp_tex.texture_count + lm.page_count + obj_tex.texture_count;
		assert(resource_count <= TC_MAX_KEYS);
		tc_init(&cache, CACHE_PAGES, 127u, resource_count, UPLOAD_BUDGET);
		for (pass = 0; pass < 2; ++pass) {
			uint32_t key = 0;
			uint32_t i;
			tc_begin_frame(&cache, pass);
			for (i = 0; i < bsp_tex.texture_count; ++i) {
				tex_info info = tex_get(&bsp_tex, i);
				tex_mip_view mip;
				assert(tex_mip(&bsp_tex, &info, 0, &mip));
				request_resource(&cache, key++, info.width, info.height, info.psm,
					mip.bytes, (uint32_t)info.clut_entries * 4u,
					&uploads[pass], &hits[pass], &deferred[pass], &full[pass]);
			}
			for (lm_idx = 0; lm_idx < lm.page_count; ++lm_idx) {
				lm_page_info page;
				if (lm_get_page(&lm, lm_idx, &page)) {
					request_resource(&cache, key, page.width, page.height, page.psm,
						page.pixel_bytes, LM_CLUT_BYTES, &uploads[pass], &hits[pass],
						&deferred[pass], &full[pass]);
				}
				++key;
			}
			for (i = 0; i < obj_tex.texture_count; ++i) {
				tex_info info = tex_get(&obj_tex, i);
				tex_mip_view mip;
				assert(tex_mip(&obj_tex, &info, 0, &mip));
				request_resource(&cache, key++, info.width, info.height, info.psm,
					mip.bytes, (uint32_t)info.clut_entries * 4u,
					&uploads[pass], &hits[pass], &deferred[pass], &full[pass]);
			}
			assert(key == resource_count);
		}
		assert(scratch.used == 0 && scratch.high <= scratch.cap);
		assert(owner.used == owner.high && owner.high <= owner.cap);
		printf("mp-render-cache map=%s owner=%lu/%lu resources=%u cache_pages=%u "
			"uploads=%u,%u hits=%u,%u deferred=%u,%u full=%u,%u "
			"highwater=%u/%u scratch=%lu/%lu modls=%u parts=%u batches=%u teardown=checked\n",
			maps[map_i], (unsigned long)owner.high, (unsigned long)owner.cap,
			resource_count, CACHE_PAGES, uploads[0], uploads[1], hits[0], hits[1],
			deferred[0], deferred[1], full[0], full[1],
			(CACHE_PAGES - tc_pages_free(&cache)), CACHE_PAGES,
			(unsigned long)scratch.high, (unsigned long)scratch.cap,
			(unsigned)model.model_count, (unsigned)model.part_count, (unsigned)model.batch_count);
		tc_flush(&cache); /* renderer flushes only after the GPU-drain/map-switch boundary */
		guards_check(owner_mem, OWNER_CAP);
		guards_check(scratch_mem, SCRATCH_CAP);
		assert(scratch.used == 0);
		owner.used = owner.high = 0; /* rewind only after cache users are invalidated */
		assert(owner.used == 0 && tc_pages_free(&cache) == CACHE_PAGES);
	}
	return 0;
}
