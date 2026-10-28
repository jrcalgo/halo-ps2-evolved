/* Host tests for C3.6 textured fx: binding resolution and per-view bucketing. */
#include <stdio.h>
#include <string.h>

#include "stream/hcu_fx_bitmap.h"

static int failures;
#define CHECK(cond) do { if (!(cond)) { printf("FAIL %s:%d %s\n", __FILE__, __LINE__, #cond); failures++; } } while (0)

static hcu_bitmap_binding make_binding(uint32_t tag, uint16_t element, uint16_t image)
{
	hcu_bitmap_binding b;
	memset(&b, 0, sizeof b);
	b.bitmap_output_datum = tag;
	b.bitmap_index = element;
	b.image_index = image;
	return b;
}

static void test_resolve(void)
{
	hcu_bitmap_binding table[3];
	uint32_t index = 99;
	table[0] = make_binding(10, 0, 0);
	table[1] = make_binding(10, 3, 0);
	table[2] = make_binding(20, 0, 1);   /* image index != 0 never binds an fx quad */

	CHECK(hcu_fx_bitmap_resolve(table, 3, 10, 3, &index) == 1 && index == 1);
	CHECK(hcu_fx_bitmap_resolve(table, 3, 10, 0, &index) == 1 && index == 0);
	CHECK(hcu_fx_bitmap_resolve(table, 3, 10, 2, &index) == 0 && index == HCU_FX_BITMAP_NONE);
	CHECK(hcu_fx_bitmap_resolve(table, 3, 20, 0, &index) == 0);
	CHECK(hcu_fx_bitmap_resolve(table, 3, HCU_FX_BITMAP_NONE, 0, &index) == 0);
	CHECK(hcu_fx_bitmap_resolve(table, 3, 10, 0x10000u, &index) == 0);
	CHECK(hcu_fx_bitmap_resolve(NULL, 0, 10, 0, &index) == 0);
	CHECK(hcu_fx_bitmap_resolve(table, 3, 10, 0, NULL) == 0);
}

static void test_bucket(void)
{
	uint32_t quads[6] = { 2, HCU_FX_BITMAP_NONE, 0, 2, 0, HCU_FX_BITMAP_NONE };
	uint16_t order[6];
	hcu_fx_bucket buckets[6];
	int n;
	uint32_t i;

	n = hcu_fx_bucket_quads(quads, 6, order, buckets, 6);
	CHECK(n == 3);
	/* first seen order: 2, NONE, 0 */
	CHECK(buckets[0].binding == 2 && buckets[0].first == 0 && buckets[0].count == 2);
	CHECK(buckets[1].binding == HCU_FX_BITMAP_NONE && buckets[1].first == 2 && buckets[1].count == 2);
	CHECK(buckets[2].binding == 0 && buckets[2].first == 4 && buckets[2].count == 2);
	CHECK(order[0] == 0 && order[1] == 3);
	CHECK(order[2] == 1 && order[3] == 5);
	CHECK(order[4] == 2 && order[5] == 4);
	/* every quad appears exactly once */
	for (i = 0; i < 6; i++) {
		uint32_t seen = 0, k;
		for (k = 0; k < 6; k++) if (order[k] == i) seen++;
		CHECK(seen == 1);
	}

	/* a bucket capacity shortfall is refused, not truncated */
	CHECK(hcu_fx_bucket_quads(quads, 6, order, buckets, 2) == -1);
	/* zero quads is valid and empty */
	CHECK(hcu_fx_bucket_quads(NULL, 0, order, buckets, 6) == 0);
	CHECK(hcu_fx_bucket_quads(quads, 6, NULL, buckets, 6) == -1);
	/* all-flat view: one bucket, NONE */
	{
		uint32_t flat[3] = { HCU_FX_BITMAP_NONE, HCU_FX_BITMAP_NONE, HCU_FX_BITMAP_NONE };
		n = hcu_fx_bucket_quads(flat, 3, order, buckets, 6);
		CHECK(n == 1 && buckets[0].count == 3 && order[2] == 2);
	}
	/* 64 distinct bitmaps: 64 buckets fit the fixed cap */
	{
		uint32_t many[64];
		uint16_t order64[64];
		hcu_fx_bucket b64[64];
		for (i = 0; i < 64; i++) many[i] = i;
		CHECK(hcu_fx_bucket_quads(many, 64, order64, b64, 64) == 64);
	}
	/* Identical textures with different CE shader/fade state cannot share a draw bucket. */
	{
		uint32_t same[4] = { 7, 7, 7, 7 };
		uint8_t blend[4] = { 0, 3, 0, 3 }, fade[4] = { 0, 0, 1, 0 };
		n = hcu_fx_bucket_quads_state(same, blend, fade, 4, order, buckets, 6);
		CHECK(n == 3);
		CHECK(buckets[0].binding == 7 && buckets[0].blend_function == 0 && buckets[0].fade_mode == 0);
		CHECK(buckets[1].binding == 7 && buckets[1].blend_function == 3 && buckets[1].fade_mode == 0);
		CHECK(buckets[2].binding == 7 && buckets[2].blend_function == 0 && buckets[2].fade_mode == 1);
		CHECK(order[0] == 0 && order[1] == 1 && order[2] == 3 && order[3] == 2);
	}
}

static void test_kind_tally(void)
{
	hcu_bitmap_binding table[1];
	/* ABI kinds: 1 effect, 2 particle system, 3 contrail, 5 decal, 6 live particle;
	 * 4 (light) and 0 are ignored. */
	uint16_t kinds[7] = { 1, 1, 2, 5, 4, 0, 6 };
	uint32_t tags[7] = { 10, HCU_FX_BITMAP_NONE, 10, 30, 10, 10, 10 };
	uint32_t elements[7] = { 0, 0, 0, 0, 0, 0, 0 };
	uint32_t counts[HCU_FX_KIND_COUNT][3];
	uint32_t tallied;

	table[0] = make_binding(10, 0, 0);
	tallied = hcu_fx_kind_tally(kinds, tags, elements, 7, table, 1, counts);
	CHECK(tallied == 5);
	/* effect: one bound (tag 10), one unbound (no tag) */
	CHECK(counts[0][0] == 2 && counts[0][1] == 1 && counts[0][2] == 1);
	/* particle: bound */
	CHECK(counts[1][0] == 1 && counts[1][1] == 1 && counts[1][2] == 0);
	/* contrail: none */
	CHECK(counts[2][0] == 0 && counts[2][1] == 0 && counts[2][2] == 0);
	/* decal: tag 30 has no binding row, so unbound */
	CHECK(counts[3][0] == 1 && counts[3][1] == 0 && counts[3][2] == 1);
	CHECK(counts[4][0] == 1 && counts[4][1] == 1 && counts[4][2] == 0);
	/* bad arguments tally nothing */
	CHECK(hcu_fx_kind_tally(NULL, tags, elements, 6, table, 1, counts) == 0);
	CHECK(counts[0][0] == 0 && counts[3][2] == 0 && counts[4][0] == 0);
	CHECK(hcu_fx_kind_tally(kinds, tags, elements, 0, NULL, 0, counts) == 0);
}

static void test_verified_descriptor_cache(void)
{
	hcu_fx_descriptor_cache cache;
	hcu_bitmap_binding binding;
	hcu_fx_descriptor out;
	memset(&cache, 0, sizeof cache);
	binding = make_binding(10, 2, 0);
	binding.chunk_id = 30;
	binding.expected_source_datum = 40;
	binding.expected_profile_id = 50;
	binding.cache_key = 60;
	memset(binding.expected_chunk_sha256, 0x5a, sizeof binding.expected_chunk_sha256);
	CHECK(sizeof cache <= 4096u);
	CHECK(hcu_fx_descriptor_cache_lookup(&cache, &binding, 50, 7, &out) == 0);
	hcu_fx_descriptor_cache_store(&cache, &binding, 50, 7, 64, 32, 0x13);
	CHECK(hcu_fx_descriptor_cache_lookup(&cache, &binding, 50, 7, &out) == 1);
	CHECK(out.width == 64 && out.height == 32 && out.psm == 0x13);
	CHECK(hcu_fx_descriptor_cache_lookup(&cache, &binding, 51, 7, &out) == 0);
	CHECK(hcu_fx_descriptor_cache_lookup(&cache, &binding, 50, 8, &out) == 0);
	binding.expected_chunk_sha256[0] ^= 1u;
	CHECK(hcu_fx_descriptor_cache_lookup(&cache, &binding, 50, 7, &out) == 0);
	binding.expected_chunk_sha256[0] ^= 1u;
	binding.cache_key++;
	CHECK(hcu_fx_descriptor_cache_lookup(&cache, &binding, 50, 7, &out) == 0);
	binding.cache_key--;
	hcu_fx_descriptor_cache_store(&cache, &binding, 50, 8, 128, 64, 0x14);
	CHECK(hcu_fx_descriptor_cache_lookup(&cache, &binding, 50, 7, &out) == 0);
	CHECK(hcu_fx_descriptor_cache_lookup(&cache, &binding, 50, 8, &out) == 1 && out.width == 128);
	/* Bounded replacement evicts a whole identity, never a truncated digest/key. */
	memset(&cache, 0, sizeof cache);
	{
		hcu_bitmap_binding rows[HCU_FX_DESCRIPTOR_CAP + 1u];
		uint32_t i;
		for (i = 0; i < HCU_FX_DESCRIPTOR_CAP + 1u; ++i) {
			rows[i] = make_binding(100u + i, (uint16_t)i, 0);
			rows[i].chunk_id = 200u + i;
			rows[i].expected_profile_id = 9u;
			rows[i].cache_key = (uint16_t)(300u + i);
			memset(rows[i].expected_chunk_sha256, (int)i, sizeof rows[i].expected_chunk_sha256);
			hcu_fx_descriptor_cache_store(&cache, &rows[i], 9u, 10u, 32, 32, 0x13);
		}
		CHECK(hcu_fx_descriptor_cache_lookup(&cache, &rows[0], 9u, 10u, &out) == 0);
		CHECK(hcu_fx_descriptor_cache_lookup(&cache, &rows[HCU_FX_DESCRIPTOR_CAP], 9u, 10u, &out) == 1);
	}
}

typedef struct {
	uint32_t reads, hashes, parses, submits, resident_queries;
	int resident, fail_submit;
} fx_probe;

static int fx_probe_resident(void *context, uint32_t cache_key, uint16_t width,
	uint16_t height, uint8_t psm, uint64_t *tex0_out)
{
	fx_probe *p = (fx_probe *)context;
	(void)cache_key; (void)width; (void)height; (void)psm;
	p->resident_queries++;
	if (!p->resident) return HCU_FX_RESIDENT_MISS;
	*tex0_out = 0x12345678u;
	return 0;
}

static int fx_probe_source(void *context, const hcu_bitmap_binding *binding,
	uint16_t *width, uint16_t *height, uint8_t *psm)
{
	fx_probe *p = (fx_probe *)context;
	(void)binding;
	p->reads++; p->hashes++; p->parses++;
	*width = 64; *height = 32; *psm = 0x13;
	return 0;
}

static int fx_probe_submit(void *context, const hcu_bitmap_binding *binding,
	uint16_t width, uint16_t height, uint8_t psm, uint64_t *tex0_out)
{
	fx_probe *p = (fx_probe *)context;
	(void)binding; (void)width; (void)height; (void)psm;
	p->submits++;
	if (p->fail_submit) return -2;
	p->resident = 1;
	*tex0_out = 0x87654321u;
	return 0;
}

static int fx_resolve_probe(hcu_fx_descriptor_cache *cache, hcu_bitmap_binding *binding,
	uint32_t profile_id, uint32_t map_generation, fx_probe *probe,
	int *attempted, int *loaded)
{
	uint64_t tex0 = 0;
	return hcu_fx_texture_resolve(cache, binding, profile_id, map_generation,
		fx_probe_resident, fx_probe_source, fx_probe_submit, probe, &tex0, attempted, loaded);
}

static void test_production_cache_decision_path(void)
{
	hcu_fx_descriptor_cache cache;
	hcu_bitmap_binding binding = make_binding(11, 3, 0);
	fx_probe probe;
	int attempted, loaded;
	uint32_t view;
	memset(&cache, 0, sizeof cache);
	memset(&probe, 0, sizeof probe);
	binding.chunk_id = 22; binding.expected_source_datum = 33;
	binding.expected_profile_id = 44; binding.cache_key = 55;
	memset(binding.expected_chunk_sha256, 0x6c, sizeof binding.expected_chunk_sha256);
	/* First admitted view verifies/reads/parses once and publishes metadata only after submit succeeds. */
	CHECK(fx_resolve_probe(&cache, &binding, 44, 1, &probe, &attempted, &loaded) == 0);
	CHECK(attempted == 1 && loaded == 1 && probe.reads == 1 && probe.hashes == 1 && probe.parses == 1);
	/* Four warm views hit the same production resolver and never invoke the source callback. */
	for (view = 0; view < 4; ++view) {
		CHECK(fx_resolve_probe(&cache, &binding, 44, 1, &probe, &attempted, &loaded) == 0);
		CHECK(attempted == 0 && loaded == 0);
	}
	CHECK(probe.reads == 1 && probe.hashes == 1 && probe.parses == 1 && probe.submits == 1);
	CHECK(probe.resident_queries == 4);
	/* Generation and full digest changes reject metadata; resident eviction falls cold too. */
	probe.resident = 0;
	CHECK(fx_resolve_probe(&cache, &binding, 44, 2, &probe, &attempted, &loaded) == 0 && attempted == 1);
	binding.expected_chunk_sha256[0] ^= 1u;
	CHECK(fx_resolve_probe(&cache, &binding, 44, 2, &probe, &attempted, &loaded) == 0 && attempted == 1);
	binding.expected_chunk_sha256[0] ^= 1u;
	probe.resident = 0;
	CHECK(fx_resolve_probe(&cache, &binding, 44, 2, &probe, &attempted, &loaded) == 0 && attempted == 1);
	/* Failed queueing leaves no descriptor, so the next attempt verifies the source again. */
	binding.bitmap_output_datum++;
	probe.resident = 0; probe.fail_submit = 1;
	CHECK(fx_resolve_probe(&cache, &binding, 44, 2, &probe, &attempted, &loaded) == -2);
	CHECK(hcu_fx_descriptor_cache_lookup(&cache, &binding, 44, 2, &(hcu_fx_descriptor){0}) == 0);
	probe.fail_submit = 0;
	CHECK(fx_resolve_probe(&cache, &binding, 44, 2, &probe, &attempted, &loaded) == 0 && attempted == 1);
}

int main(void)
{
	test_resolve();
	test_bucket();
	test_kind_tally();
	test_verified_descriptor_cache();
	test_production_cache_decision_path();
	if (failures) {
		printf("hcu_fx_bitmap_main: %d failure(s)\n", failures);
		return 1;
	}
	printf("hcu_fx_bitmap_main: all checks passed\n");
	return 0;
}
