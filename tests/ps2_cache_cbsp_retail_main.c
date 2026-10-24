#include "cseries.h"
#include "cache/cache_files.h"
#include "cache/physical_memory_map.h"
#include "halo_ps2_cache.h"

#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

/* Host-only capacity is deliberately larger than the PS2 arena. This fixture
 * validates package identity and the production adapter path, not EE fit. */
static unsigned char tag_cache[16u * 1024u * 1024u] __attribute__((aligned(16)));
static unsigned char bsp_cache[8u * 1024u * 1024u] __attribute__((aligned(16)));
static const unsigned char *payloads[2];
static size_t payload_sizes[2];
static unsigned offsets[2];
static unsigned sizes[2];
static unsigned releases;

struct retail_bsp_cache_header
{
	uint32_t base_address;
	int32_t vertex_buffer_count;
	uint32_t vertex_buffers;
	int32_t index_buffer_count;
	uint32_t index_buffers;
	uint32_t signature;
};

static int no_read(void *context, int32_t tag_index, uint32_t offset,
	uint32_t size, void *buffer, int blocking)
{
	(void)context; (void)tag_index; (void)offset; (void)size;
	(void)buffer; (void)blocking;
	return 0;
}

static int load_bsp(void *context, uint32_t offset, uint32_t size)
{
	unsigned i;
	(void)context;
	for (i = 0; i < 2; ++i)
		if (offset == offsets[i] && size == sizes[i])
			return ps2_cache_mount_cbsp_for_extent(payloads[i], payload_sizes[i],
				offsets[i], sizes[i]);
	return 0;
}

static void release_bsp(void *context)
{
	(void)context;
	ps2_cache_unmount_cbsp();
	++releases;
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

static void read_extent(unsigned which)
{
	boolean complete = FALSE;
	struct retail_bsp_cache_header *header;
	short result = cache_file_read(NONE, offsets[which], sizes[which], bsp_cache,
		&complete, TRUE);
	assert(result == NONE && complete == TRUE);
	assert(sizes[which] >= 24 && sizes[which] <= sizeof bsp_cache);
	assert(memcmp(bsp_cache + 20, "psbs", 4) == 0);
	header = (struct retail_bsp_cache_header *)bsp_cache;
	/* PS2 render geometry is in HP2 packs, not Xbox cache arrays. */
	assert(header->vertex_buffer_count == 0 && header->vertex_buffers == 0);
	assert(header->index_buffer_count == 0 && header->index_buffers == 0);
}

int main(int argc, char **argv)
{
	unsigned char header[2048];
	unsigned char *ctag, *first, *second, *snapshot_first, *snapshot_second;
	size_t ctag_size = 0, first_size = 0, second_size = 0;
	unsigned tag_offset, tag_image_size, file_length;
	boolean complete = FALSE;
	if (argc != 11) return 2;
	ctag = read_file(argv[1], &ctag_size);
	first = read_file(argv[2], &first_size);
	second = read_file(argv[3], &second_size);
	if (!ctag || !first || !second) return 3;
	offsets[0] = (unsigned)strtoul(argv[4], NULL, 0);
	sizes[0] = (unsigned)strtoul(argv[5], NULL, 0);
	offsets[1] = (unsigned)strtoul(argv[6], NULL, 0);
	sizes[1] = (unsigned)strtoul(argv[7], NULL, 0);
	tag_offset = (unsigned)strtoul(argv[8], NULL, 0);
	tag_image_size = (unsigned)strtoul(argv[9], NULL, 0);
	/* The source extent is validated by the package audit and Python caller;
	 * the virtual cache length may extend beyond tag_offset for both BSPs. */
	file_length = (unsigned)strtoul(argv[10], NULL, 0);
	if (sizes[0] > sizeof bsp_cache || sizes[1] > sizeof bsp_cache) return 4;
	payloads[0] = first; payloads[1] = second;
	payload_sizes[0] = first_size; payload_sizes[1] = second_size;
	snapshot_first = (unsigned char *)malloc(sizes[0]);
	snapshot_second = (unsigned char *)malloc(sizes[1]);
	assert(snapshot_first && snapshot_second);
	cache_files_initialize();
	assert(ps2_cache_mount_ctag_with_file_source("a30", ctag, ctag_size,
		tag_offset, file_length, no_read, NULL));
	assert(ps2_cache_set_bsp_loader(load_bsp, release_bsp, NULL));
	assert(cache_file_open("a30", (struct cache_file_header *)header));
	cache_file_read(NONE, tag_offset, tag_image_size, tag_cache, &complete, TRUE);
	assert(complete == TRUE);
	read_extent(0);
	memcpy(snapshot_first, bsp_cache, sizes[0]);
	assert(releases == 1);
	/* The candidate overwrites the single BSP destination. Re-reading the old
	 * exact extent must rematerialize byte-identical data at that same address. */
	read_extent(1);
	memcpy(snapshot_second, bsp_cache, sizes[1]);
	assert(releases == 2);
	read_extent(0);
	assert(memcmp(bsp_cache, snapshot_first, sizes[0]) == 0);
	assert(memcmp(bsp_cache, snapshot_second, sizes[1]) != 0);
	assert(releases == 3);
	cache_file_close();
	ps2_cache_unmount_ctag();
	cache_files_dispose();
	free(ctag); free(first); free(second); free(snapshot_first); free(snapshot_second);
	return 0;
}
