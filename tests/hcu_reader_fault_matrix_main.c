#include "stream/cbsp_catalog.h"
#include "stream/ctag_resource_index.h"
#include "stream/hmap.h"
#include "stream/hp2.h"
#include "ps2_cbsp.h"

#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

static void put_u32(uint8_t *p, uint32_t value)
{
	p[0] = (uint8_t)value;
	p[1] = (uint8_t)(value >> 8);
	p[2] = (uint8_t)(value >> 16);
	p[3] = (uint8_t)(value >> 24);
}

static void make_crng(uint8_t bytes[52])
{
	memset(bytes, 0, 52);
	memcpy(bytes, "CRNG", 4);
	put_u32(bytes + 4, 1);
	put_u32(bytes + 8, 2);
	put_u32(bytes + 12, 1000);
	put_u32(bytes + 16, 400);
	put_u32(bytes + 20, 100);
	put_u32(bytes + 24, 36);
	put_u32(bytes + 36, 100);
	put_u32(bytes + 40, 20);
	put_u32(bytes + 44, 200);
	put_u32(bytes + 48, 50);
	put_u32(bytes + 28, hp2_crc32(bytes + 36, 16));
}

static void assert_bad_crng(const uint8_t *bytes, size_t size,
	uint32_t expected_file, uint32_t tag_offset, uint32_t tag_size)
{
	ctag_resource_index index;
	memset(&index, 0xA5, sizeof(index));
	assert(!ctag_resource_index_open(&index, bytes, size, expected_file,
		tag_offset, tag_size));
}

static void make_cbix(uint8_t bytes[60])
{
	memset(bytes, 0, 60);
	memcpy(bytes, "CBIX", 4);
	put_u32(bytes + 4, 1);
	put_u32(bytes + 8, 2);
	put_u32(bytes + 12, 1000);
	put_u32(bytes + 16, 28);
	put_u32(bytes + 28, 100);
	put_u32(bytes + 32, 20);
	memcpy(bytes + 36, "B000", 4);
	put_u32(bytes + 44, 200);
	put_u32(bytes + 48, 50);
	memcpy(bytes + 52, "B001", 4);
	put_u32(bytes + 20, hp2_crc32(bytes + 28, 32));
}

static void assert_bad_cbix(const uint8_t *bytes, size_t size,
	uint32_t expected_file)
{
	cbsp_catalog catalog;
	memset(&catalog, 0xA5, sizeof(catalog));
	assert(!cbsp_catalog_open(&catalog, bytes, size, expected_file));
}

static void make_hmap(uint8_t bytes[72])
{
	unsigned i;
	memset(bytes, 0, 72);
	memcpy(bytes, "HMAP", 4);
	put_u32(bytes + 4, 1);
	put_u32(bytes + 8, 72);
	put_u32(bytes + 12, 1000);
	put_u32(bytes + 16, 400);
	put_u32(bytes + 20, 100);
	for (i = 0; i < 32; i++) bytes[24 + i] = (uint8_t)i;
	memcpy(bytes + 56, "fixture", 7);
}

static void assert_bad_hmap(const uint8_t *bytes, size_t size,
	const char *expected_name)
{
	hmap_identity identity;
	memset(&identity, 0xA5, sizeof(identity));
	assert(!hmap_open(&identity, bytes, size, expected_name));
}

static void make_cbsp(uint8_t bytes[112])
{
	uint8_t *image = bytes + 36;
	memset(bytes, 0, 112);
	memcpy(bytes, "CBSP", 4);
	put_u32(bytes + 4, 1);
	put_u32(bytes + 8, 64);
	put_u32(bytes + 12, 1);
	put_u32(bytes + 16, 100);
	put_u32(bytes + 24, 2048);
	put_u32(bytes + 28, 64);
	put_u32(image, 24);
	memcpy(image + 20, "psbs", 4);
	put_u32(bytes + 100, 0);
	bytes[104] = 0;
	put_u32(bytes + 108, 24);
	put_u32(bytes + 20, hp2_crc32(image, 64));
}

static void make_cbsp_two_domains(uint8_t bytes[124])
{
	uint8_t *image = bytes + 36;
	memset(bytes, 0, 124);
	memcpy(bytes, "CBSP", 4);
	put_u32(bytes + 4, 1);
	put_u32(bytes + 8, 64);
	put_u32(bytes + 12, 2);
	put_u32(bytes + 16, 100);
	put_u32(bytes + 24, 2048);
	put_u32(bytes + 28, 64);
	put_u32(image, 24);
	put_u32(image + 8, 128);
	memcpy(image + 20, "psbs", 4);
	put_u32(bytes + 100, 0);
	bytes[104] = 0;
	put_u32(bytes + 108, 24);
	put_u32(bytes + 112, 8);
	bytes[116] = 1;
	put_u32(bytes + 120, 128);
	put_u32(bytes + 20, hp2_crc32(image, 64));
}

static void assert_bad_cbsp(const uint8_t *bytes, size_t size)
{
	ps2_cbsp_view view;
	memset(&view, 0xA5, sizeof(view));
	assert(ps2_cbsp_open(&view, bytes, size, 4096, 8) != PS2_CBSP_OK);
	assert(view.payload == NULL && view.image == NULL &&
		view.relocations == NULL && view.image_size == 0 &&
		view.relocation_count == 0);
}

static void reseal_crng(uint8_t bytes[52])
{
	put_u32(bytes + 28, hp2_crc32(bytes + 36, 16));
}

static void reseal_cbix(uint8_t bytes[60])
{
	put_u32(bytes + 20, hp2_crc32(bytes + 28, 32));
}

static void reseal_cbsp(uint8_t bytes[112])
{
	put_u32(bytes + 20, hp2_crc32(bytes + 36, 64));
}

static void reseal_cbsp_two_domains(uint8_t bytes[124])
{
	put_u32(bytes + 20, hp2_crc32(bytes + 36, 64));
}

int main(void)
{
	uint8_t bytes[112], changed[112];
	uint8_t two_domains[124], changed_two_domains[124];
	hmap_identity identity;
	ctag_resource_index range_index;
	cbsp_catalog catalog;
	cbsp_catalog_entry found;
	ps2_cbsp_view cbsp_view;

	/* HMAP C contract: canonical identity, exact shape, safe extents, and
	 * failure must not publish an output identity. */
	make_hmap(bytes);
	assert(hmap_open(&identity, bytes, 72, "fixture"));
	assert(identity.file_length == 1000 && identity.tag_data_offset == 400);
	assert(!hmap_open(&identity, bytes, 72, "other"));
	assert_bad_hmap(bytes, 71, "fixture");
	memcpy(changed, bytes, 72); changed[0] = 'X'; assert_bad_hmap(changed, 72, "fixture");
	memcpy(changed, bytes, 72); put_u32(changed + 4, 2); assert_bad_hmap(changed, 72, "fixture");
	memcpy(changed, bytes, 72); put_u32(changed + 8, 71); assert_bad_hmap(changed, 72, "fixture");
	memcpy(changed, bytes, 72); put_u32(changed + 12, 0); assert_bad_hmap(changed, 72, "fixture");
	memcpy(changed, bytes, 72); put_u32(changed + 16, 1000); assert_bad_hmap(changed, 72, "fixture");
	memcpy(changed, bytes, 72); put_u32(changed + 20, 0); assert_bad_hmap(changed, 72, "fixture");
	memcpy(changed, bytes, 72); put_u32(changed + 20, 601); assert_bad_hmap(changed, 72, "fixture");
	memcpy(changed, bytes, 72); changed[56] = 'F'; assert_bad_hmap(changed, 72, "fixture");
	memcpy(changed, bytes, 72); changed[63] = 'x'; assert_bad_hmap(changed, 72, "fixture");

	/* CRNG C contract: header/identity/body CRC and independent range rules. */
	make_crng(bytes);
	assert(ctag_resource_index_open(&range_index, bytes, 52, 1000, 400, 100));
	assert(ctag_resource_index_allows(&range_index, 100, 20));
	assert(ctag_resource_index_allows(&range_index, 119, 1));
	assert(!ctag_resource_index_allows(&range_index, 119, 2));
	assert(!ctag_resource_index_allows(&range_index, 100, 0));
	assert(!ctag_resource_index_allows(&range_index, 1000, 1));
	assert_bad_crng(bytes, 35, 1000, 400, 100);
	memcpy(changed, bytes, 52); changed[0] = 'X'; assert_bad_crng(changed, 52, 1000, 400, 100);
	memcpy(changed, bytes, 52); put_u32(changed + 4, 2); assert_bad_crng(changed, 52, 1000, 400, 100);
	memcpy(changed, bytes, 52); put_u32(changed + 24, 35); assert_bad_crng(changed, 52, 1000, 400, 100);
	memcpy(changed, bytes, 52); put_u32(changed + 32, 1); assert_bad_crng(changed, 52, 1000, 400, 100);
	memcpy(changed, bytes, 52); changed[51] ^= 1; assert_bad_crng(changed, 52, 1000, 400, 100);
	assert_bad_crng(bytes, 52, 999, 400, 100);
	assert_bad_crng(bytes, 52, 1000, 401, 100);
	assert_bad_crng(bytes, 52, 1000, 400, 99);
	memcpy(changed, bytes, 52); put_u32(changed + 40, 0); reseal_crng(changed); assert_bad_crng(changed, 52, 1000, 400, 100);
	memcpy(changed, bytes, 52); put_u32(changed + 44, 120); reseal_crng(changed); assert_bad_crng(changed, 52, 1000, 400, 100);
	memcpy(changed, bytes, 52); put_u32(changed + 44, 119); reseal_crng(changed); assert_bad_crng(changed, 52, 1000, 400, 100);
	memcpy(changed, bytes, 52); put_u32(changed + 44, 450); reseal_crng(changed); assert_bad_crng(changed, 52, 1000, 400, 100);
	memcpy(changed, bytes, 52); put_u32(changed + 44, 990); put_u32(changed + 48, 20); reseal_crng(changed); assert_bad_crng(changed, 52, 1000, 400, 100);
	memcpy(changed, bytes, 52); put_u32(changed + 44, 0xFFFFFFFFu); put_u32(changed + 48, 2); reseal_crng(changed); assert_bad_crng(changed, 52, 1000, 400, 100);

	/* CBIX C contract: exact record shape, checksum, sorted bounded extents,
	 * unique printable nonreserved section tags, and exact lookup. */
	make_cbix(bytes);
	assert(cbsp_catalog_open(&catalog, bytes, 60, 1000));
	assert(cbsp_catalog_find(&catalog, 100, 20, &found));
	assert(!cbsp_catalog_find(&catalog, 100, 19, &found));
	assert(!cbsp_catalog_find(&catalog, 101, 20, &found));
	assert(!cbsp_catalog_find(&catalog, 100, 0, &found));
	assert_bad_cbix(bytes, 27, 1000);
	memcpy(changed, bytes, 60); changed[0] = 'X'; assert_bad_cbix(changed, 60, 1000);
	memcpy(changed, bytes, 60); put_u32(changed + 4, 2); assert_bad_cbix(changed, 60, 1000);
	memcpy(changed, bytes, 60); put_u32(changed + 8, 0); assert_bad_cbix(changed, 28, 1000);
	memcpy(changed, bytes, 60); put_u32(changed + 8, 33); assert_bad_cbix(changed, 60, 1000);
	memcpy(changed, bytes, 60); put_u32(changed + 16, 27); assert_bad_cbix(changed, 60, 1000);
	memcpy(changed, bytes, 60); put_u32(changed + 24, 1); assert_bad_cbix(changed, 60, 1000);
	memcpy(changed, bytes, 60); changed[59] ^= 1; assert_bad_cbix(changed, 60, 1000);
	memcpy(changed, bytes, 60); put_u32(changed + 56, 1); reseal_cbix(changed); assert_bad_cbix(changed, 60, 1000);
	assert_bad_cbix(bytes, 60, 999);
	memcpy(changed, bytes, 60); put_u32(changed + 32, 0); reseal_cbix(changed); assert_bad_cbix(changed, 60, 1000);
	memcpy(changed, bytes, 60); put_u32(changed + 44, 119); reseal_cbix(changed); assert_bad_cbix(changed, 60, 1000);
	memcpy(changed, bytes, 60); put_u32(changed + 44, 100); reseal_cbix(changed); assert_bad_cbix(changed, 60, 1000);
	memcpy(changed, bytes, 60); put_u32(changed + 44, 990); put_u32(changed + 48, 20); reseal_cbix(changed); assert_bad_cbix(changed, 60, 1000);
	memcpy(changed, bytes, 60); memcpy(changed + 52, "B000", 4); reseal_cbix(changed); assert_bad_cbix(changed, 60, 1000);
	memcpy(changed, bytes, 60); memcpy(changed + 36, "CTAG", 4); reseal_cbix(changed); assert_bad_cbix(changed, 60, 1000);
	memcpy(changed, bytes, 60); changed[36] = 0x1F; reseal_cbix(changed); assert_bad_cbix(changed, 60, 1000);

	/* PS2 CBSP C contract: malformed envelopes/relocations clear the view,
	 * even when inner metadata is resealed to pass the image checksum. */
	make_cbsp(bytes);
	assert(ps2_cbsp_open(&cbsp_view, bytes, 112, 4096, 8) == PS2_CBSP_OK);
	assert(cbsp_view.source_file_offset == 2048 && cbsp_view.source_file_size == 64);
	assert_bad_cbsp(bytes, 35);
	memcpy(changed, bytes, 112); put_u32(changed + 4, 2); assert_bad_cbsp(changed, 112);
	memcpy(changed, bytes, 112); put_u32(changed + 16, 99); assert_bad_cbsp(changed, 112);
	memcpy(changed, bytes, 112); put_u32(changed + 32, 1); assert_bad_cbsp(changed, 112);
	memcpy(changed, bytes, 112); put_u32(changed + 28, 63); assert_bad_cbsp(changed, 112);
	memcpy(changed, bytes, 112); put_u32(changed + 24, 0xFFFFFFFFu); assert_bad_cbsp(changed, 112);
	memcpy(changed, bytes, 112); changed[56] ^= 1; assert_bad_cbsp(changed, 112);
	memcpy(changed, bytes, 112); memcpy(changed + 56, "xxxx", 4); reseal_cbsp(changed); assert_bad_cbsp(changed, 112);
	memcpy(changed, bytes, 112); changed[105] = 1; assert_bad_cbsp(changed, 112);
	memcpy(changed, bytes, 112); changed[104] = 2; assert_bad_cbsp(changed, 112);
	memcpy(changed, bytes, 112); put_u32(changed + 100, 1); assert_bad_cbsp(changed, 112);
	memcpy(changed, bytes, 112); put_u32(changed + 100, 64); assert_bad_cbsp(changed, 112);
	memcpy(changed, bytes, 112); put_u32(changed + 108, 25); assert_bad_cbsp(changed, 112);
	memcpy(changed, bytes, 112); put_u32(changed + 108, 100); reseal_cbsp(changed); assert_bad_cbsp(changed, 112);
	memcpy(changed, bytes, 112); put_u32(changed + 28, 65); assert_bad_cbsp(changed, 112);
	memcpy(changed, bytes, 112); put_u32(changed + 12, 2); assert_bad_cbsp(changed, 112);
	make_cbsp_two_domains(two_domains);
	assert(ps2_cbsp_open(&cbsp_view, two_domains, sizeof(two_domains),
		4096, 8) == PS2_CBSP_OK);
	assert(cbsp_view.relocation_count == 2);
	memcpy(changed_two_domains, two_domains, sizeof(two_domains));
	put_u32(changed_two_domains + 112, 0); /* duplicate/cross-domain field */
	put_u32(changed_two_domains + 120, 24);
	assert_bad_cbsp(changed_two_domains, sizeof(changed_two_domains));
	memcpy(changed_two_domains, two_domains, sizeof(two_domains));
	put_u32(changed_two_domains + 100, 8);
	put_u32(changed_two_domains + 108, 0);
	put_u32(changed_two_domains + 112, 0);
	changed_two_domains[116] = 0;
	put_u32(changed_two_domains + 120, 24); /* descending slots */
	assert_bad_cbsp(changed_two_domains, sizeof(changed_two_domains));
	memcpy(changed_two_domains, two_domains, sizeof(two_domains));
	put_u32(changed_two_domains + 112, 3); /* unaligned slot */
	assert_bad_cbsp(changed_two_domains, sizeof(changed_two_domains));
	memcpy(changed_two_domains, two_domains, sizeof(two_domains));
	put_u32(changed_two_domains + 120, 129); /* row/image target disagreement */
	assert_bad_cbsp(changed_two_domains, sizeof(changed_two_domains));
	memcpy(changed_two_domains, two_domains, sizeof(two_domains));
	put_u32(changed_two_domains + 44, 64); /* internal pointer at image end */
	put_u32(changed_two_domains + 108, 64);
	reseal_cbsp_two_domains(changed_two_domains);
	assert_bad_cbsp(changed_two_domains, sizeof(changed_two_domains));

	printf("reader-fault-matrix hmap=11 crng=15 cbix=16 cbsp=21; crc-resealed semantic cases rejected\n");
	return 0;
}
