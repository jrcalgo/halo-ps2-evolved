/* Host driver for the bounded HCP2 segment residency table. Usage:
 *   hcu_asset_residency_main <package.hcp> <profile_id> <type:id> [<type:id>...]
 * Every segment of each named chunk is pinned on its own. For each segment the
 * driver proves that pins, leases and gameplay references block eviction, and
 * that eviction after release frees it. Then all segments of the chunk are
 * pinned together, their concatenation is hashed (it must equal the chunk's
 * logical SHA-256), and they are evicted. A table with one slot refuses a
 * second segment and counts the refusal. */
#include "stream/hcu_asset_profile.h"
#include "stream/sha256.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static void hex(const uint8_t *d, char *out)
{ static const char *h = "0123456789abcdef"; int i; for (i = 0; i < 32; i++) { out[2*i] = h[d[i] >> 4]; out[2*i+1] = h[d[i] & 15]; } out[64] = 0; }

static int fail(const char *what, int rc) { fprintf(stderr, "FAIL %s rc=%d\n", what, rc); return 1; }

int main(int argc, char **argv)
{
	FILE *f; long n; unsigned char *img; hcu_asset_profile_view v;
	hcu_asset_residency_entry entries[256], one[1]; hcu_asset_residency table, tiny;
	int i, rc; uint32_t profile, total_segments = 0;
	if (argc < 4) return 2;
	f = fopen(argv[1], "rb"); if (!f) return 3;
	fseek(f, 0, SEEK_END); n = ftell(f); rewind(f);
	img = malloc((size_t)n); if (!img || fread(img, 1, (size_t)n, f) != (size_t)n) return 4;
	fclose(f);
	profile = (uint32_t)strtoul(argv[2], 0, 10);
	rc = hcu_asset_profile_preflight(img, (size_t)n, profile, &v);
	if (rc) return fail("preflight", rc);
	if (hcu_asset_residency_init(&table, entries, 256)) return 5;
	for (i = 3; i < argc; i++) {
		uint32_t type, id, seg, nseg; hcu_asset_chunk_view c; sha256_context s; uint8_t dig[32]; char hx[65];
		unsigned char *logical; const hcu_asset_residency_entry *st;
		if (sscanf(argv[i], "%u:%u", &type, &id) != 2) return 6;
		if (hcu_asset_profile_lookup(&v, type, id, &c)) return fail("lookup", -3);
		nseg = c.segment_count;
		total_segments += nseg;
		/* Phase 1: per-segment lifetime rules. */
		for (seg = 0; seg < nseg; seg++) {
			uint32_t bytes, loff; void *store, *out = 0;
			if (hcu_asset_profile_segment_info(&v, type, id, seg, &bytes, &loff)) return fail("segment info", -4);
			if (bytes > HCU_ASSET_PROFILE_MAX_MEDIA_CHUNK_BYTES) return fail("segment over 64 KiB", -15);
			store = malloc(bytes);
			if (!store) return 7;
			if ((rc = hcu_asset_residency_pin(&table, &v, type, id, seg, store, bytes))) return fail("pin", rc);
			/* Second pin of a resident segment must not copy or allocate again. */
			if ((rc = hcu_asset_residency_pin(&table, &v, type, id, seg, 0, 0))) return fail("second pin", rc);
			if (hcu_asset_residency_lease(&table, type, id, seg)) return fail("lease", -8);
			if (hcu_asset_residency_gameplay_ref(&table, type, id, seg, 1)) return fail("gameplay ref", -8);
			if (hcu_asset_residency_evict(&table, type, id, seg, &out) != HCU_ASSET_PROFILE_E_BUSY) return fail("evict while pinned/leased/referenced", -9);
			if (hcu_asset_residency_unpin(&table, type, id, seg) || hcu_asset_residency_unpin(&table, type, id, seg)) return fail("unpin", -8);
			if (hcu_asset_residency_evict(&table, type, id, seg, &out) != HCU_ASSET_PROFILE_E_BUSY) return fail("evict while leased", -9);
			if (hcu_asset_residency_unpin(&table, type, id, seg) == 0) return fail("unpin underflow accepted", -8);
			if (hcu_asset_residency_release_lease(&table, type, id, seg)) return fail("release lease", -8);
			if (hcu_asset_residency_evict(&table, type, id, seg, &out) != HCU_ASSET_PROFILE_E_BUSY) return fail("evict while gameplay ref", -9);
			if (hcu_asset_residency_gameplay_ref(&table, type, id, seg, -1)) return fail("drop gameplay ref", -8);
			if (hcu_asset_residency_state(&table, type, id, seg, &st) || st->pin_count || st->lease_count || st->gameplay_refs || !st->resident) return fail("state before evict", -10);
			if ((rc = hcu_asset_residency_evict(&table, type, id, seg, &out))) return fail("evict unpinned", rc);
			if (out != store) return fail("evict returned wrong storage", -11);
			free(out);
			if (hcu_asset_residency_state(&table, type, id, seg, &st) == 0 && st->resident) return fail("still resident", -13);
		}
		/* Phase 2: pin every segment, hash the logical concatenation, evict. */
		logical = malloc(c.size ? c.size : 1);
		if (!logical) return 7;
		for (seg = 0; seg < nseg; seg++) {
			uint32_t bytes, loff; void *store;
			hcu_asset_profile_segment_info(&v, type, id, seg, &bytes, &loff);
			store = malloc(bytes);
			if (!store) return 7;
			if ((rc = hcu_asset_residency_pin(&table, &v, type, id, seg, store, bytes))) return fail("pin all", rc);
			memcpy(logical + loff, store, bytes);
		}
		sha256_init(&s); sha256_update(&s, logical, c.size); sha256_final(&s, dig); hex(dig, hx);
		printf("PIN %u:%u bytes=%u segments=%u sha256=%s high_water=%u\n", type, id, c.size, nseg, hx, table.resident_high_water);
		for (seg = 0; seg < nseg; seg++) {
			void *out = 0; uint32_t bytes, loff; (void)loff;
			hcu_asset_profile_segment_info(&v, type, id, seg, &bytes, &loff);
			hcu_asset_residency_unpin(&table, type, id, seg);
			if (hcu_asset_residency_evict(&table, type, id, seg, &out)) return fail("evict after pin all", -14);
			free(out);
		}
		free(logical);
	}
	if (table.resident_bytes != 0) return fail("resident bytes after all evictions", -12);
	/* A one-slot table refuses a second segment, counts it, and keeps the first. */
	if (hcu_asset_residency_init(&tiny, one, 1)) return 5;
	if (total_segments >= 2) {
		uint32_t type, id; hcu_asset_chunk_view c; void *a, *b;
		if (sscanf(argv[3], "%u:%u", &type, &id) != 2) return 6;
		hcu_asset_profile_lookup(&v, type, id, &c);
		a = malloc(HCU_ASSET_PROFILE_MAX_MEDIA_CHUNK_BYTES); b = malloc(HCU_ASSET_PROFILE_MAX_MEDIA_CHUNK_BYTES);
		if (!a || !b) return 7;
		if ((rc = hcu_asset_residency_pin(&tiny, &v, type, id, 0, a, HCU_ASSET_PROFILE_MAX_MEDIA_CHUNK_BYTES))) return fail("tiny pin 0", rc);
		if (hcu_asset_residency_pin(&tiny, &v, type, id, 1, b, HCU_ASSET_PROFILE_MAX_MEDIA_CHUNK_BYTES) != HCU_ASSET_PROFILE_E_MEMORY) return fail("tiny table accepted second segment", -16);
		if (tiny.refused_pins != 1 || tiny.count != 1) return fail("tiny refusal not counted", -17);
		free(a); free(b);
	}
	printf("REFUSED %u evictions %u verify_failures %u refused_pins %u segments %u\n",
		table.refused_evictions, table.evictions, table.verify_failures, table.refused_pins, total_segments);
	return 0;
}
