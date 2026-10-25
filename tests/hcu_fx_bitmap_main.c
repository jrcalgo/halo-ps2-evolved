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
}

static void test_kind_tally(void)
{
	hcu_bitmap_binding table[1];
	/* kinds: 1 effect, 2 particle, 3 contrail, 4 decal, 0 and 5 are ignored */
	uint16_t kinds[6] = { 1, 1, 2, 4, 5, 0 };
	uint32_t tags[6] = { 10, HCU_FX_BITMAP_NONE, 10, 30, 10, 10 };
	uint32_t elements[6] = { 0, 0, 0, 0, 0, 0 };
	uint32_t counts[HCU_FX_KIND_COUNT][3];
	uint32_t tallied;

	table[0] = make_binding(10, 0, 0);
	tallied = hcu_fx_kind_tally(kinds, tags, elements, 6, table, 1, counts);
	CHECK(tallied == 4);
	/* effect: one bound (tag 10), one unbound (no tag) */
	CHECK(counts[0][0] == 2 && counts[0][1] == 1 && counts[0][2] == 1);
	/* particle: bound */
	CHECK(counts[1][0] == 1 && counts[1][1] == 1 && counts[1][2] == 0);
	/* contrail: none */
	CHECK(counts[2][0] == 0 && counts[2][1] == 0 && counts[2][2] == 0);
	/* decal: tag 30 has no binding row, so unbound */
	CHECK(counts[3][0] == 1 && counts[3][1] == 0 && counts[3][2] == 1);
	/* bad arguments tally nothing */
	CHECK(hcu_fx_kind_tally(NULL, tags, elements, 6, table, 1, counts) == 0);
	CHECK(counts[0][0] == 0 && counts[3][2] == 0);
	CHECK(hcu_fx_kind_tally(kinds, tags, elements, 0, NULL, 0, counts) == 0);
}

int main(void)
{
	test_resolve();
	test_bucket();
	test_kind_tally();
	if (failures) {
		printf("hcu_fx_bitmap_main: %d failure(s)\n", failures);
		return 1;
	}
	printf("hcu_fx_bitmap_main: all checks passed\n");
	return 0;
}
