/* C4 item 5 fault-injection harness for the PS2 CBSP decoder boundaries.
 *
 * Test-only driver. It links the production decoder (ps2_cbsp.c) unmodified and
 * runs each manifest case against three regions:
 *   - PUB: the previously published BSP image (materialized from the clean
 *     payload before any fault). It must be byte-identical after every case.
 *   - CAND: the candidate destination. Guard bytes surround it and a neighbour
 *     owner region follows it; all guards must be intact after every case.
 *   - Retry: the clean payload is decoded into CAND again and must equal the
 *     clean expected bytes produced by the independent Python oracle.
 *
 * Manifest line (one case per line):
 *   name mode max_image max_relocs dest_size payload_path tag_path
 * mode: W = open + materialize (whole payload)
 *       S = streamed split: copy image+table into CAND, open_parts, rebase_in_place
 *       OT = open_parts with the table pointer aliasing the image (overlap)
 *       OB = materialize with bsp_base == tag_base (address overlap)
 *
 * Output line per case:
 *   CASE name mode open=<status> op=<status> raw=<0|1> pub=<ok|bad> guards=<ok|bad> retry=<ok|bad>
 * Status codes: 0 OK, 1 TRUNCATED, 2 FORMAT, 3 BOUNDS, 4 CHECKSUM, 5 SPACE,
 * 6 ADDRESS, 7 OVERLAP, -1 not reached.
 */
#include "ps2_cbsp.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define CAND_CAPACITY 512u
#define GUARD_BYTES 64u
#define OWNER_BYTES 256u
#define PUB_CAPACITY 512u
#define HEADER_BYTES 36u
#define BSP_BASE 0x02000000u
#define TAG_BASE 0x01400000u

static unsigned char arena[GUARD_BYTES + CAND_CAPACITY + GUARD_BYTES + OWNER_BYTES];
static unsigned char pub[PUB_CAPACITY];
static unsigned char expected[PUB_CAPACITY];
static size_t expected_size;
static unsigned char *cand = arena + GUARD_BYTES;
static unsigned char *owner = arena + GUARD_BYTES + CAND_CAPACITY + GUARD_BYTES;

static unsigned char *read_file(const char *path, size_t *size)
{
	FILE *file = fopen(path, "rb");
	long length;
	unsigned char *data;
	if (!file || fseek(file, 0, SEEK_END) != 0) { if (file) fclose(file); return NULL; }
	length = ftell(file);
	if (length < 0 || fseek(file, 0, SEEK_SET) != 0) { fclose(file); return NULL; }
	data = (unsigned char *)malloc(length ? (size_t)length : 1u);
	if (!data) { fclose(file); return NULL; }
	if (fread(data, 1, (size_t)length, file) != (size_t)length) {
		free(data); fclose(file); return NULL;
	}
	fclose(file);
	*size = (size_t)length;
	return data;
}

static uint32_t read_u32(const unsigned char *p)
{
	return (uint32_t)p[0] | (uint32_t)p[1] << 8 |
		(uint32_t)p[2] << 16 | (uint32_t)p[3] << 24;
}

static int guards_intact(void)
{
	size_t i;
	for (i = 0; i < GUARD_BYTES; i++) {
		if (arena[i] != 0xC4) return 0;
		if (arena[GUARD_BYTES + CAND_CAPACITY + i] != 0xC4) return 0;
	}
	for (i = 0; i < OWNER_BYTES; i++)
		if (owner[i] != 0x5A) return 0;
	return 1;
}

/* Whole-payload path: open then materialize into CAND. */
static int run_whole(const unsigned char *payload, size_t payload_size,
	size_t max_image, uint32_t max_relocs, const unsigned char *tag,
	size_t tag_size, size_t dest_size, uint32_t bsp_base, uint32_t tag_base,
	int *open_status, int *op_status)
{
	ps2_cbsp_view view;
	ps2_cbsp_status st;
	st = ps2_cbsp_open(&view, payload, payload_size, max_image, max_relocs);
	*open_status = (int)st;
	*op_status = -1;
	if (st != PS2_CBSP_OK) return 0;
	st = ps2_cbsp_materialize(&view, bsp_base, tag_base, tag, tag_size,
		cand, dest_size);
	*op_status = (int)st;
	return st == PS2_CBSP_OK;
}

/* Streamed path: copy the header-declared image and table into the candidate
 * as the ps2_cache sink does, validate the split envelope, then rebase in place.
 * The header is read from the complete payload so truncation is seen as a
 * short image or table. */
static int run_stream(const unsigned char *payload, size_t payload_size,
	size_t max_image, uint32_t max_relocs, const unsigned char *tag,
	size_t tag_size, size_t dest_size, int *open_status, int *op_status,
	int *raw_unchanged)
{
	ps2_cbsp_view view;
	ps2_cbsp_status st;
	size_t available, image_size, table_size;
	*raw_unchanged = 1;
	*op_status = -1;
	if (payload_size < HEADER_BYTES) {
		st = ps2_cbsp_open_parts(&view, payload, payload_size, NULL, 0, NULL, 0,
			max_image, max_relocs);
		*open_status = (int)st;
		return 0;
	}
	available = payload_size - HEADER_BYTES;
	image_size = read_u32(payload + 8);
	if (image_size > available) image_size = available;
	table_size = available - image_size;
	if (image_size + table_size > CAND_CAPACITY) {
		*open_status = -1;
		return 0;
	}
	memcpy(cand, payload + HEADER_BYTES, image_size);
	if (table_size) memcpy(cand + image_size, payload + HEADER_BYTES + image_size, table_size);
	st = ps2_cbsp_open_parts(&view, payload, HEADER_BYTES, cand, image_size,
		cand + image_size, table_size, max_image, max_relocs);
	*open_status = (int)st;
	if (st != PS2_CBSP_OK) {
		*raw_unchanged = memcmp(cand, payload + HEADER_BYTES, image_size) == 0;
		return 0;
	}
	st = ps2_cbsp_rebase_in_place(&view, BSP_BASE, TAG_BASE, tag, tag_size,
		cand, dest_size);
	*op_status = (int)st;
	/* A rejected rebase must leave the candidate image unrelocated. */
	*raw_unchanged = memcmp(cand, payload + HEADER_BYTES, image_size) == 0;
	return st == PS2_CBSP_OK;
}

static int run_overlap_table(const unsigned char *payload, size_t payload_size,
	int *open_status, int *op_status)
{
	ps2_cbsp_view view;
	size_t image_size, table_size;
	ps2_cbsp_status st;
	*op_status = -1;
	image_size = read_u32(payload + 8);
	table_size = payload_size - HEADER_BYTES - image_size;
	st = ps2_cbsp_open_parts(&view, payload, HEADER_BYTES, payload + HEADER_BYTES,
		image_size, payload + HEADER_BYTES + 8u, table_size, 4096u, 1000000u);
	*open_status = (int)st;
	return st == PS2_CBSP_OK;
}

static int parse_manifest_line(char *line, char *name, char *mode, size_t *max_image,
	uint32_t *max_relocs, size_t *dest_size, char *payload_path, char *tag_path)
{
	unsigned long a, b, c;
	if (sscanf(line, "%63s %3s %lu %lu %lu %511s %511s", name, mode, &a, &b, &c,
		payload_path, tag_path) != 7) return 0;
	*max_image = (size_t)a;
	*max_relocs = (uint32_t)b;
	*dest_size = (size_t)c;
	return 1;
}

int main(int argc, char **argv)
{
	FILE *manifest;
	char line[1200], name[64], mode[4], payload_path[512], tag_path[512];
	size_t max_image, dest_size, payload_size = 0, tag_size = 0;
	uint32_t max_relocs;
	unsigned char *payload, *tag;
	int open_status, op_status, raw;
	unsigned char *clean;
	size_t clean_size = 0;
	unsigned char *clean_tag;
	size_t clean_tag_size = 0;

	if (argc != 5) return 2;
	if (!(clean = read_file(argv[1], &clean_size))) return 3;
	if (!(clean_tag = read_file(argv[2], &clean_tag_size))) return 3;
	expected_size = 0;
	{
		size_t n = 0;
		unsigned char *exp = read_file(argv[3], &n);
		if (!exp || n > PUB_CAPACITY) return 4;
		memcpy(expected, exp, n);
		expected_size = n;
		free(exp);
	}

	/* Publish the clean image first; this is the previous BSP that a failed
	 * candidate must leave intact. */
	memset(arena, 0xC4, sizeof(arena));
	memset(owner, 0x5A, OWNER_BYTES);
	{
		int o1, o2;
		if (!run_whole(clean, clean_size, 4096u, 1000000u, clean_tag,
			clean_tag_size, PUB_CAPACITY, BSP_BASE, TAG_BASE, &o1, &o2) ||
			memcmp(cand, expected, expected_size) != 0) return 5;
		memcpy(pub, cand, expected_size);
	}

	manifest = fopen(argv[4], "r");
	if (!manifest) return 6;
	while (fgets(line, sizeof(line), manifest)) {
		unsigned char *payload_bytes, *tag_bytes;
		int retry_ok, guards_ok, pub_ok;
		if (!parse_manifest_line(line, name, mode, &max_image, &max_relocs,
			&dest_size, payload_path, tag_path)) continue;
		payload_bytes = read_file(payload_path, &payload_size);
		tag_bytes = read_file(tag_path, &tag_size);
		if (!payload_bytes || !tag_bytes) return 7;
		payload = payload_bytes;
		tag = tag_bytes;
		raw = 1;
		open_status = -1;
		op_status = -1;

		/* Candidate attempt: a fresh candidate region for every case. */
		memset(cand, 0xEE, CAND_CAPACITY);
		if (strcmp(mode, "W") == 0) {
			(void)run_whole(payload, payload_size, max_image, max_relocs, tag,
				tag_size, dest_size, BSP_BASE, TAG_BASE, &open_status, &op_status);
		} else if (strcmp(mode, "S") == 0) {
			(void)run_stream(payload, payload_size, max_image, max_relocs, tag,
				tag_size, dest_size, &open_status, &op_status, &raw);
		} else if (strcmp(mode, "OT") == 0) {
			(void)run_overlap_table(payload, payload_size, &open_status, &op_status);
		} else if (strcmp(mode, "OB") == 0) {
			(void)run_whole(payload, payload_size, max_image, max_relocs, tag,
				tag_size, dest_size, BSP_BASE, BSP_BASE, &open_status, &op_status);
		} else {
			return 8;
		}

		guards_ok = guards_intact();
		pub_ok = memcmp(pub, expected, expected_size) == 0;

		/* Retry with the clean payload into the same candidate region, using
		 * the streamed path for S and the whole path otherwise. The retry must
		 * reproduce the clean expected bytes exactly. */
		memset(cand, 0xEE, CAND_CAPACITY);
		{
			int r_open, r_op, r_raw;
			if (strcmp(mode, "S") == 0) {
				retry_ok = run_stream(clean, clean_size, 4096u, 1000000u,
					clean_tag, clean_tag_size, PUB_CAPACITY, &r_open, &r_op, &r_raw) &&
					memcmp(cand, expected, expected_size) == 0;
			} else {
				retry_ok = run_whole(clean, clean_size, 4096u, 1000000u, clean_tag,
					clean_tag_size, PUB_CAPACITY, BSP_BASE, TAG_BASE, &r_open, &r_op) &&
					memcmp(cand, expected, expected_size) == 0;
			}
		}
		printf("CASE %s %s open=%d op=%d raw=%d pub=%s guards=%s retry=%s\n",
			name, mode, open_status, op_status, raw,
			pub_ok ? "ok" : "bad", guards_ok ? "ok" : "bad",
			retry_ok ? "ok" : "bad");
		free(payload_bytes);
		free(tag_bytes);
	}
	fclose(manifest);
	free(clean);
	free(clean_tag);
	return 0;
}
