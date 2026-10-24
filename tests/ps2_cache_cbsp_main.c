#include "cseries.h"
#include "cache/cache_files.h"
#include "cache/physical_memory_map.h"
#include "halo_ps2_cache.h"

#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static unsigned char tag_cache[4096] __attribute__((aligned(16)));
static unsigned char bsp_cache[4096] __attribute__((aligned(16)));
static unsigned char *bsp_payload_one;
static size_t bsp_payload_one_size;
static unsigned char *bsp_payload_two;
static size_t bsp_payload_two_size;
static unsigned bsp_release_count;
static int fail_bsp_two_load;
static int fail_bsp_one_load;
static int fail_bsp_stream;
static size_t bsp_stream_fail_after = (size_t)-1;
static int no_read(void *context, int32_t tag_index, uint32_t offset,
	uint32_t size, void *buffer, int blocking)
{
	(void)context; (void)tag_index; (void)offset; (void)size;
	(void)buffer; (void)blocking;
	return 0;
}

static int load_bsp(void *context, uint32_t offset, uint32_t size)
{
	(void)context;
	if (offset == 2048 && size == 64)
	{
		if (fail_bsp_one_load) return 0;
		return ps2_cache_mount_cbsp_for_extent(bsp_payload_one,
			bsp_payload_one_size, offset, size);
	}
	if (offset == 6144 && size == 64)
	{
		if (fail_bsp_two_load) return 0;
		return ps2_cache_mount_cbsp_for_extent(bsp_payload_two,
			bsp_payload_two_size, offset, size);
	}
	return 0;
}

static int visit_bsp(void *context, uint32_t offset, uint32_t size,
	ps2_cache_bsp_sink_fn sink, void *sink_context, size_t *raw_size)
{
	size_t cursor = 0;
	(void)context;
	if (fail_bsp_stream || offset != 2048 || size != 64 || !sink || !raw_size)
		return 0;
	/* Deliberately split the CBSP header, image, and table across callbacks. */
	while (cursor < bsp_payload_one_size)
	{
		size_t chunk = cursor < 35 ? 7 : 13;
		if (cursor >= bsp_stream_fail_after) return 0;
		if (chunk > bsp_stream_fail_after - cursor)
			chunk = bsp_stream_fail_after - cursor;
		if (chunk > bsp_payload_one_size - cursor)
			chunk = bsp_payload_one_size - cursor;
		if (!sink(sink_context, (uint32_t)cursor,
			bsp_payload_one + cursor, chunk))
			return 0;
		cursor += chunk;
	}
	*raw_size = bsp_payload_one_size;
	return 1;
}

static void release_bsp(void *context)
{
	(void)context;
	ps2_cache_unmount_cbsp();
	++bsp_release_count;
}

void *physical_memory_get_tag_cache_base_address(void) { return tag_cache; }
unsigned long physical_memory_get_tag_cache_size(void) { return sizeof tag_cache; }
void *physical_memory_get_structure_bsp_cache_base_address(void) { return bsp_cache; }
unsigned long physical_memory_get_structure_bsp_cache_size(void) { return sizeof bsp_cache; }

static unsigned char *read_file(const char *path, size_t *size)
{
	FILE *file = fopen(path, "rb");
	long length;
	unsigned char *data;
	if (!file || fseek(file, 0, SEEK_END) != 0) { if (file) fclose(file); return NULL; }
	length = ftell(file);
	if (length < 0 || fseek(file, 0, SEEK_SET) != 0) { fclose(file); return NULL; }
	data = (unsigned char *)malloc(length ? (size_t)length : 1);
	if (!data) { fclose(file); return NULL; }
	if (fread(data, 1, (size_t)length, file) != (size_t)length) {
		free(data); fclose(file); return NULL;
	}
	fclose(file);
	*size = (size_t)length;
	return data;
}

/* Model the CE caller contract around cache_file_read: the scenario code
 * unloads the active BSP before a switch, verifies a materialized candidate,
 * and retries the previous reference if the candidate cannot be used. This
 * test-side driver deliberately does not claim to execute scenario.c; the
 * companion Python test guards the production switch's control-flow shape. */
static int current_bsp_index = -1;

static int read_bsp_reference(int index, int reject_candidate)
{
	boolean completed = FALSE;
	uint32_t offset = index == 0 ? 2048u : 6144u;
	short result;
	if (index < 0 || index > 1) return 0;
	result = cache_file_read(NONE, offset, 64, bsp_cache, &completed, TRUE);
	if (result != NONE || completed != TRUE) return 0;
	if (reject_candidate && bsp_cache[60] == 0x42) return 0;
	return 1;
}

static int switch_bsp_reference(int requested_index, int reject_candidate)
{
	int previous_index = current_bsp_index;
	if (requested_index < 0 || requested_index > 1) return 0;
	/* Match CE's boolean contract: same-index is a no-transition result. */
	if (requested_index == current_bsp_index) return 0;
	if (previous_index >= 0)
	{
		ps2_cache_unmount_cbsp();
		assert(ps2_cache_bsp_image_unpublish());
	}
	current_bsp_index = -1;
	if (read_bsp_reference(requested_index, reject_candidate))
	{
		current_bsp_index = requested_index;
		return 1;
	}
	ps2_cache_unmount_cbsp();
	(void)ps2_cache_bsp_image_unpublish();
	if (previous_index >= 0 && read_bsp_reference(previous_index, 0))
	{
		current_bsp_index = previous_index;
		return 0;
	}
	return 0;
}

int main(int argc, char **argv)
{
	unsigned char header[2048];
	uint32_t bsp_internal_target, tag_name_target;
	boolean completed = FALSE;
	size_t ctag_size = 0, cbsp_size = 0;
	unsigned char *ctag, *cbsp, *cbsp_two;
	size_t cbsp_two_size = 0;
	if (argc != 6) return 2;
	ctag = read_file(argv[1], &ctag_size);
	cbsp = read_file(argv[2], &cbsp_size);
	cbsp_two = read_file(argv[5], &cbsp_two_size);
	if (!ctag || !cbsp || !cbsp_two) return 3;
	bsp_payload_one = cbsp;
	bsp_payload_one_size = cbsp_size;
	bsp_payload_two = cbsp_two;
	bsp_payload_two_size = cbsp_two_size;
	cache_files_initialize();
	assert(ps2_cache_mount_ctag_with_file_source("bloodgulch", ctag, ctag_size,
		4096, 8192, no_read, NULL));
	assert(ps2_cache_set_bsp_loader(load_bsp, release_bsp, NULL));
	{
		size_t bad_size = 0;
		unsigned char *bad = read_file(argv[3], &bad_size);
		assert(bad && !ps2_cache_mount_cbsp(bad, bad_size));
		free(bad);
		bad = read_file(argv[4], &bad_size);
		assert(bad && !ps2_cache_mount_cbsp(bad, bad_size));
		free(bad);
	}
	assert(cache_file_open("bloodgulch", (struct cache_file_header *)header));
	cache_file_read(NONE, 4096, 76, tag_cache, &completed, TRUE);
	assert(completed == TRUE);
	assert(switch_bsp_reference(0, 0));
	bsp_internal_target = (uint32_t)(uintptr_t)(bsp_cache + 24);
	tag_name_target = (uint32_t)(uintptr_t)(tag_cache + 68);
	assert(*(uint32_t *)bsp_cache == bsp_internal_target);
	assert(*(uint32_t *)(bsp_cache + 4) == 0);
	assert(*(uint32_t *)(bsp_cache + 8) == 0);
	assert(*(uint32_t *)(bsp_cache + 12) == 0);
	assert(*(uint32_t *)(bsp_cache + 16) == 0);
	assert(*(uint32_t *)(bsp_cache + 28) == tag_name_target);
	assert(current_bsp_index == 0 && bsp_cache[60] == 0x11 && bsp_release_count == 1);
	{
		ps2_cache_bsp_read_lease lease, stale;
		ps2_cache_owner_telemetry owner_stats;
		uint32_t original = *(uint32_t *)bsp_cache;
		boolean lease_read = FALSE;
		assert(ps2_cache_bsp_read_lease_acquire(&lease));
		assert(lease.base == bsp_cache && lease.bytes == 64);
		ps2_cache_get_owner_telemetry(&owner_stats);
		assert(owner_stats.bsp_current_bytes == 64 &&
			owner_stats.bsp_peak_bytes == 64 && owner_stats.bsp_publications == 1);
		assert(ps2_cache_bsp_read_lease_valid(&lease));
		assert(!ps2_cache_bsp_readers_drained());
		assert(!ps2_cache_bsp_image_unpublish());
		assert(cache_file_read(NONE, 6144, 64, bsp_cache, &lease_read, TRUE) == NONE);
		assert(lease_read == _cache_file_read_failed);
		assert(*(uint32_t *)bsp_cache == original);
		assert(ps2_cache_bsp_read_lease_valid(&lease));
		stale = lease;
		assert(ps2_cache_bsp_read_lease_release(&lease));
		assert(!ps2_cache_bsp_read_lease_valid(&stale));
		assert(!ps2_cache_bsp_read_lease_release(&stale));
		assert(ps2_cache_bsp_readers_drained());
		assert(ps2_cache_bsp_image_unpublish());
	}
	/* BSP 1 materializes, but its verification is rejected; BSP 0 must be
	 * fetched again and remain the published reference. */
	assert(!switch_bsp_reference(1, 1));
	assert(current_bsp_index == 0 && bsp_cache[60] == 0x11 && bsp_release_count == 3);
	/* A loader failure after the old BSP has been released follows the same
	 * rollback path. */
	fail_bsp_two_load = 1;
	assert(!switch_bsp_reference(1, 0));
	fail_bsp_two_load = 0;
	assert(current_bsp_index == 0 && bsp_cache[60] == 0x11 && bsp_release_count == 4);
	/* A valid index switch publishes BSP 1 only after the adapter supplies it. */
	assert(switch_bsp_reference(1, 0));
	assert(current_bsp_index == 1 && bsp_cache[60] == 0x42 && bsp_release_count == 5);
	completed = FALSE;
	cache_file_read(NONE, 2049, 64, bsp_cache, &completed, TRUE);
	assert(completed == _cache_file_read_failed);
	assert(!switch_bsp_reference(4, 0));
	assert(current_bsp_index == 1 && bsp_cache[60] == 0x42 && bsp_release_count == 5);
	/* Same-index requests are also no-ops and must not release or rematerialize. */
	assert(!switch_bsp_reference(1, 0));
	assert(current_bsp_index == 1 && bsp_cache[60] == 0x42 && bsp_release_count == 5);
	/* If both the candidate and old-reference reload fail, keep the model's
	 * published index null; no pointer into the overwritten cache is retained. */
	fail_bsp_one_load = 1;
	fail_bsp_two_load = 1;
	assert(!switch_bsp_reference(0, 0));
	assert(current_bsp_index == -1 && bsp_release_count == 5);
	/* A first-load failure has no prior BSP to restore, and a later valid retry
	 * remains possible in the same cache instance. */
	assert(!switch_bsp_reference(0, 0));
	assert(current_bsp_index == -1 && bsp_release_count == 5);
	fail_bsp_one_load = 0;
	fail_bsp_two_load = 0;
	assert(switch_bsp_reference(0, 0));
	assert(current_bsp_index == 0 && bsp_cache[60] == 0x11 && bsp_release_count == 6);
	/* Exercise the bounded streamed transaction independently of the retained
	 * whole-payload oracle. A failed stream leaves CE's failure sentinel and an
	 * immediate same-request retry overwrites the unpublished candidate. */
	assert(ps2_cache_set_bsp_visitor(visit_bsp, NULL));
	completed = FALSE;
	assert(cache_file_read(NONE, 2048, 64, bsp_cache, &completed, TRUE) == NONE);
	assert(completed == TRUE && bsp_cache[60] == 0x11);
	memset(bsp_cache, 0xA5, sizeof(bsp_cache));
	bsp_stream_fail_after = 80;
	completed = TRUE;
	assert(cache_file_read(NONE, 2048, 64, bsp_cache, &completed, TRUE) == NONE);
	assert(completed == _cache_file_read_failed && bsp_cache[0] != 0xA5);
	bsp_stream_fail_after = (size_t)-1;
	completed = FALSE;
	assert(cache_file_read(NONE, 2048, 64, bsp_cache, &completed, TRUE) == NONE);
	assert(completed == TRUE && bsp_cache[60] == 0x11);
	fail_bsp_stream = 1;
	completed = FALSE;
	assert(cache_file_read(NONE, 2048, 64, bsp_cache, &completed, TRUE) == NONE);
	assert(completed == _cache_file_read_failed);
	fail_bsp_stream = 0;
	completed = FALSE;
	assert(cache_file_read(NONE, 2048, 64, bsp_cache, &completed, TRUE) == NONE);
	assert(completed == TRUE && bsp_cache[60] == 0x11);
	/* Full streamed bytes with a malformed final relocation must still fail
	 * before rebasing/publication, and the restored source must be retryable. */
	{
		unsigned char saved = bsp_payload_one[bsp_payload_one_size - 1];
		bsp_payload_one[bsp_payload_one_size - 1] ^= 0x80;
		completed = TRUE;
		assert(cache_file_read(NONE, 2048, 64, bsp_cache, &completed, TRUE) == NONE);
		assert(completed == _cache_file_read_failed);
		bsp_payload_one[bsp_payload_one_size - 1] = saved;
		completed = FALSE;
		assert(cache_file_read(NONE, 2048, 64, bsp_cache, &completed, TRUE) == NONE);
		assert(completed == TRUE && bsp_cache[60] == 0x11);
	}
	cache_file_close();
	ps2_cache_unmount_ctag();
	{
		ps2_cache_owner_telemetry owner_stats;
		ps2_cache_get_owner_telemetry(&owner_stats);
		assert(owner_stats.bsp_current_bytes == 0);
		assert(owner_stats.bsp_publications >= 2 && owner_stats.bsp_resets >= 1);
	}
	cache_files_dispose();
	free(ctag); free(cbsp); free(cbsp_two);
	return 0;
}
