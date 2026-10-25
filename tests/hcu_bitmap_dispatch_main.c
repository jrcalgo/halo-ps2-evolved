#include "cseries.h"
#include "bitmaps/bitmap_group.h"
#include "interface/interface.h"
#include "rasterizer/rasterizer.h"
#include "halo_ps2_bitmap_requests.h"
#include "stream/hcu_asset_profile.h"
#include "stream/hcu_bitmap_dispatch.h"
#include "render/gs.h"

#undef memcpy
#undef memcmp
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

typedef char fixture_ilp32[sizeof(void *) == 4 && sizeof(long) == 4 ? 1 : -1];

static struct bitmap_group s_group;
static struct bitmap_data s_bitmap;
static uint32_t s_datum;
static halo_ps2_bitmap_request_queue s_queue;
static hcu_asset_profile_view s_profile;
static tc_t s_cache;
static tc_journal_t s_journal;
static uint16_t s_cache_readers[TC_MAX_KEYS];
static hcu_bitmap_source_slot s_slots[4];
static hcu_bitmap_lease s_leases[HALO_PS2_BITMAP_REQUEST_CAPACITY];
static uint8_t s_package[16 * 1024 * 1024];
static uint8_t s_source_storage[4 * 128 * 1024];
static uint8_t s_staging[128 * 1024];
static uint8_t s_upload_memory[4096 * 16];
static uint8_t s_geometry_memory[4096 * 16];
static chain_t s_upload, s_geometry;
static hcu_bitmap_binding s_binding;
static hcu_bitmap_dispatch_context s_context;
static tc_t s_cache_before;
static int s_bitmap_fence_complete;

uint32_t bsp_render_kick_seq(void) { return 40u; }
int32_t bsp_render_fence_observed(uint32_t kick_seq)
{
	return kick_seq == 41u && s_bitmap_fence_complete ? 1 : 0;
}
int32_t bsp_render_source_release(uint32_t kind, uint32_t kick_seq)
{
	return kind == 2u ? bsp_render_fence_observed(kick_seq) : -1;
}

static unsigned log2_exact(unsigned n)
{
	unsigned result = 0;
	while (n > 1u) { n >>= 1; result++; }
	return result;
}

static int parse_sha256(const char *hex, uint8_t out[32])
{
	unsigned i; unsigned value; unsigned length = 0;
	while (hex[length]) length++;
	if (length != 64) return 0;
	for (i = 0; i < 32; i++) {
		if (sscanf(hex + i * 2, "%2x", &value) != 1) return 0;
		out[i] = (uint8_t)value;
	}
	return 1;
}

static int rejection_preserves_state(const hcu_bitmap_binding *binding,
	const halo_ps2_bitmap_request *request, uint32_t generation,
	hcu_bitmap_dispatch_status expected)
{
	hcu_bitmap_lease lease = {0};
	chain_t upload_before = s_upload, geometry_before = s_geometry;
	memcpy(&s_cache_before, &s_cache, sizeof(s_cache));
	if (hcu_bitmap_dispatch_request(request, binding, 1, &s_profile, generation,
		&s_cache, &s_journal, s_cache_readers, TC_MAX_KEYS, s_slots, 4,
		s_source_storage, sizeof(s_source_storage), sizeof(s_staging), s_staging, sizeof(s_staging),
		&s_upload, &s_geometry, s_context.texture_page_base_words,
		s_context.clut_base_words, 640, 448, &lease) != expected)
		return 0;
	return !lease.active && !memcmp(&s_cache, &s_cache_before, sizeof(s_cache)) &&
		s_upload.qw == upload_before.qw && s_upload.overflow == upload_before.overflow &&
		s_geometry.qw == geometry_before.qw && s_geometry.overflow == geometry_before.overflow;
}

void *csmemset(void *p, long value, unsigned long size)
{
	unsigned long i; byte *b = (byte *)p;
	for (i = 0; i < size; i++) b[i] = (byte)value;
	return p;
}
void *tag_block_get_element_with_size(struct tag_block const *block, long index, long size)
{
	if (!block || index < 0 || index >= block->count || !block->address || size <= 0) return NULL;
	return (byte *)block->address + index * size;
}
void *tag_get(long group_tag, long tag_index)
{
	return group_tag == BITMAP_GROUP_TAG && (uint32_t)tag_index == s_datum ? &s_group : NULL;
}

static int load_package(const char *path, uint32_t *size)
{
	FILE *f = fopen(path, "rb"); long n;
	if (!f || fseek(f, 0, SEEK_END) || (n = ftell(f)) < 0 || fseek(f, 0, SEEK_SET) ||
		(uint32_t)n > sizeof(s_package)) { if (f) fclose(f); return 0; }
	if (fread(s_package, 1, (size_t)n, f) != (size_t)n) { fclose(f); return 0; }
	fclose(f); *size = (uint32_t)n; return 1;
}

int main(int argc, char **argv)
{
	uint32_t package_size, bitmap_index, chunk_id, cache_key, width, height, source_datum;
	short registration_x, registration_y;
	point2d point; real_rectangle2d clip; real_argb_color tint;
	const tc_entry *entry;
	tex_section section; tex_info dispatched_image;
	int rc;
	if (argc != 12 || !load_package(argv[1], &package_size)) return 2;
	s_datum = (uint32_t)strtoul(argv[2], NULL, 0);
	bitmap_index = (uint32_t)strtoul(argv[3], NULL, 0);
	chunk_id = (uint32_t)strtoul(argv[4], NULL, 0);
	cache_key = (uint32_t)strtoul(argv[5], NULL, 0);
	width = (uint32_t)strtoul(argv[6], NULL, 0);
	height = (uint32_t)strtoul(argv[7], NULL, 0);
	registration_x = (short)strtol(argv[8], NULL, 0);
	registration_y = (short)strtol(argv[9], NULL, 0);
	source_datum = (uint32_t)strtoul(argv[10], NULL, 0);
	if (bitmap_index != 0 || hcu_asset_profile_preflight(s_package, package_size, 1, &s_profile) != HCU_ASSET_PROFILE_OK)
		return 3;
	if (!parse_sha256(argv[11], s_binding.expected_chunk_sha256)) return 11;
	memset(&s_bitmap, 0, sizeof(s_bitmap)); memset(&s_group, 0, sizeof(s_group));
	s_group.bitmaps.count = 1; s_group.bitmaps.address = &s_bitmap;
	s_bitmap.width = (short)width; s_bitmap.height = (short)height;
	s_bitmap.tag_index = (long)(int32_t)s_datum;
	s_bitmap.registration_point.x = (real)registration_x;
	s_bitmap.registration_point.y = (real)registration_y;
	s_binding.bitmap_output_datum = s_datum;
	s_binding.bitmap_index = (uint16_t)bitmap_index;
	s_binding.image_index = 0; s_binding.chunk_id = chunk_id;
	s_binding.cache_key = (uint16_t)cache_key;
	s_binding.expected_source_datum = source_datum; s_binding.expected_profile_id = 1;
	tc_init(&s_cache, 128, 128, TC_MAX_KEYS, 1024 * 1024);
	tc_begin_frame(&s_cache, 1);
	chain_init(&s_upload, s_upload_memory, 4096);
	chain_init(&s_geometry, s_geometry_memory, 4096);
	halo_ps2_bitmap_requests_init(&s_queue);
	memset(&s_context, 0, sizeof(s_context));
	s_context.bindings = &s_binding; s_context.binding_count = 1;
	s_context.profile = &s_profile; s_context.cache = &s_cache;
	s_context.expected_generation = 9001;
	s_context.journal = &s_journal; s_context.cache_readers = s_cache_readers;
	s_context.cache_reader_count = TC_MAX_KEYS;
	s_context.slots = s_slots; s_context.slot_count = 4;
	s_context.source_storage = s_source_storage;
	s_context.source_storage_bytes = sizeof(s_source_storage);
	s_context.slot_stride = sizeof(s_staging);
	s_context.staging_buffer = s_staging; s_context.staging_buffer_bytes = sizeof(s_staging);
	s_context.upload_chain = &s_upload;
	s_context.geometry_chain = &s_geometry; s_context.texture_page_base_words = 4096;
	s_context.clut_base_words = 8192; s_context.screen_w = 640; s_context.screen_h = 448;
	s_context.leases = s_leases; s_context.lease_capacity = HALO_PS2_BITMAP_REQUEST_CAPACITY;
	if (halo_ps2_bitmap_requests_register_consumer(&s_queue,
		(halo_ps2_bitmap_request_consumer)hcu_bitmap_dispatch_reader, &s_context) != HALO_PS2_BITMAP_REQUEST_OK)
		return 4;
	if (halo_ps2_bitmap_requests_begin(&s_queue, 71, 9001, 0, 0) != HALO_PS2_BITMAP_REQUEST_OK) return 5;
	point.x = 320.0f; point.y = 224.0f;
	clip.x0 = 0.0f; clip.x1 = 1.0f; clip.y0 = 0.0f; clip.y1 = 1.0f;
	interface_draw_bitmap(&s_bitmap, &point, &clip, 1.0f, 0.0f, 1.0f);
	tint.alpha = 1.0f; tint.red = 1.0f; tint.green = 1.0f; tint.blue = 1.0f;
	interface_draw_bitmap_modulated(&s_bitmap, &point, &clip, 1.0f, 0.0f, &tint, 0);
	interface_draw_bitmap_modulated(&s_bitmap, &point, &clip, 1.0f, 0.0f, &tint, 3);
	rc = halo_ps2_bitmap_requests_end(&s_queue);
	if (rc != HALO_PS2_BITMAP_REQUEST_OK || s_queue.count != 3 || !s_geometry.qw || !s_upload.qw ||
		s_context.lease_count != 3 || s_context.first_error != HCU_BITMAP_DISPATCH_OK ||
		s_queue.readers || s_cache.hits != 2 || s_cache.misses != 1) {
		fprintf(stderr, "dispatch-failed status=%d consumer=%ld count=%u up=%u geom=%u\n", rc,
			(long)s_queue.last_consumer_status, (unsigned)s_queue.count,
			(unsigned)s_upload.qw, (unsigned)s_geometry.qw);
		return 6;
	}
	entry = &s_cache.entry[s_cache.map[cache_key] - 1u];
	if (!entry->valid || entry->pending_upload || !s_cache_readers[cache_key] ||
		!s_slots[s_leases[0].slot].readers || s_slots[s_leases[0].slot].readers != 1 ||
		s_leases[1].slot != UINT16_MAX || s_leases[2].slot != UINT16_MAX) return 7;
	if (hcu_asset_profile_read_chunk(&s_profile, HCU_ASSET_CHUNK_MEDIA,
		chunk_id, s_staging, sizeof(s_staging)) != HCU_ASSET_PROFILE_OK) return 9;
	{
		hcu_asset_chunk_view chunk;
		if (hcu_asset_profile_lookup(&s_profile, HCU_ASSET_CHUNK_MEDIA, chunk_id, &chunk) != HCU_ASSET_PROFILE_OK ||
			tex_open(&section, s_staging, chunk.size) != TEX_OK) return 10;
	}
	dispatched_image = tex_get(&section, 0);
	{
		uint64_t *geo = (uint64_t *)(s_geometry_memory + 32);
		tex_mip_view retained_mip;
		const uint8_t *retained_clut;
		uint32_t retained_clut_bytes = (uint32_t)dispatched_image.clut_entries * 4u;
		const hcu_bitmap_source_slot *slot = &s_slots[s_leases[0].slot];
		const uint8_t *retained = s_source_storage + slot->storage_offset;
		if (!tex_mip(&section, &dispatched_image, 0, &retained_mip) ||
			!(retained_clut = tex_clut(&section, &dispatched_image)) ||
			slot->storage_bytes != retained_mip.bytes + retained_clut_bytes ||
			memcmp(retained, retained_mip.pixels, retained_mip.bytes) ||
			memcmp(retained + retained_mip.bytes, retained_clut, retained_clut_bytes)) return 11;
		if (geo[6] != GS_ALPHA(2,1,0,1,0) ||
			geo[52] != GS_ALPHA(0,2,2,1,128) || /* CE enum 7's second pass */
			geo[102] != GS_ALPHA(0,1,0,1,0) ||
			geo[156] != GS_ALPHA(0,2,2,1,128)) return 12;
	}
	{
		halo_ps2_bitmap_request req = s_queue.requests[0];
		hcu_bitmap_binding bad = s_binding;
		hcu_asset_chunk_view view;
		chain_t saved_upload = s_upload;
		chain_t saved_geometry = s_geometry;
		uint8_t *mutable_package = s_package;
		if (!rejection_preserves_state(&s_binding, &req, 9002, HCU_BITMAP_DISPATCH_E_IDENTITY)) return 13;
		bad.expected_profile_id++;
		if (!rejection_preserves_state(&bad, &req, 9001, HCU_BITMAP_DISPATCH_E_IDENTITY)) return 14;
		bad = s_binding; bad.expected_source_datum++;
		if (!rejection_preserves_state(&bad, &req, 9001, HCU_BITMAP_DISPATCH_E_IDENTITY)) return 15;
		bad = s_binding; bad.expected_chunk_sha256[0] ^= 1;
		if (!rejection_preserves_state(&bad, &req, 9001, HCU_BITMAP_DISPATCH_E_IDENTITY)) return 16;
		if (hcu_asset_profile_lookup(&s_profile, HCU_ASSET_CHUNK_MEDIA, chunk_id, &view) != HCU_ASSET_PROFILE_OK) return 17;
		mutable_package[view.offset] ^= 1;
		if (!rejection_preserves_state(&s_binding, &req, 9001, HCU_BITMAP_DISPATCH_E_CHUNK)) return 18;
		mutable_package[view.offset] ^= 1;
		s_geometry.cap_qw = s_geometry.qw + 1;
		if (!rejection_preserves_state(&s_binding, &req, 9001, HCU_BITMAP_DISPATCH_E_CAPACITY)) return 19;
		s_geometry = saved_geometry;
		bad = s_binding; bad.cache_key++;
		s_upload.cap_qw = s_upload.qw + 1;
		if (!rejection_preserves_state(&bad, &req, 9001, HCU_BITMAP_DISPATCH_E_CAPACITY)) return 20;
		s_upload = saved_upload;
	}
	printf("bitmap-dispatch-ok profile=ui ctag_reader=end-hook request=%u output_datum=%u bitmap_index=%u chunk=%u cache_key=%u tex0=%016llx upload_qw=%u geometry_qw=%u cache_hits=%u cache_misses=%u blend7=premult blend0=alpha blend3=raw_add rejected=profile,generation,source,hash,corrupt_chunk rollback=geometry,upload leases=held frame=%u\n",
		(unsigned)s_queue.count, (unsigned)s_datum, (unsigned)bitmap_index,
		(unsigned)chunk_id, (unsigned)cache_key,
		(unsigned long long)GS_TEX0((4096u + entry->first_page * 2048u) / 64u,
			(dispatched_image.width + 63u) / 64u, dispatched_image.psm,
			log2_exact(dispatched_image.width), log2_exact(dispatched_image.height), 1, 0,
			8192u / 64u + entry->clut_slot * 4u, GS_PSMCT32, 0, 0, 1),
		(unsigned)s_upload.qw, (unsigned)s_geometry.qw, (unsigned)s_cache.hits,
		(unsigned)s_cache.misses, (unsigned)s_queue.frame_index);
	/* The host proof calls this only at the simulated paired-chain fence boundary. */
	if (hcu_bitmap_dispatch_complete(&s_context) != HCU_BITMAP_DISPATCH_E_BUSY ||
		s_context.lease_count != 1 || !s_leases[0].active || !s_cache_readers[cache_key] ||
		!s_slots[s_leases[0].slot].readers) return 8;
	s_bitmap_fence_complete = 1;
	if (hcu_bitmap_dispatch_complete(&s_context) != HCU_BITMAP_DISPATCH_OK) return 9;
	if (s_context.lease_count || s_cache_readers[cache_key] || s_slots[s_leases[0].slot].readers) return 8;
	return 0;
}
