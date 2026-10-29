#include "stream/hcu_asset_profile.h"
#include "stream/hcu_bitmap_dispatch.h"
#include "render/hud_effect.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static uint8_t package_bytes[24u * 1024u * 1024u];
static uint8_t native_p4_indices[512u * 512u / 2u];
static uint8_t native_p4_palette[16u * 4u];
static uint8_t source_storage[256u * 1024u];
static uint8_t staging[2u * 1024u * 1024u];
static uint8_t upload_memory[4096u * 16u];
static uint8_t geometry_memory[4096u * 16u];
static hcu_bitmap_source_slot slots[16];
static hcu_bitmap_lease leases[16];
static uint16_t cache_readers[TC_MAX_KEYS];
static halo_ps2_bitmap_request_queue request_queue;
static tc_t cache;
static tc_journal_t journal;
static chain_t upload_chain, geometry_chain;
static hcu_bitmap_dispatch_context context;
static hcu_bitmap_binding bindings[2];
static hcu_asset_profile_view profile;
static int fence_complete;

uint32_t bsp_render_kick_seq(void) { return 40u; }
int32_t bsp_render_fence_observed(uint32_t seq)
{
	return seq == 41u && fence_complete ? 1 : 0;
}
int32_t bsp_render_source_release(uint32_t kind, uint32_t seq)
{
	return kind == 2u ? bsp_render_fence_observed(seq) : -1;
}
int32_t bsp_render_hud_effect_texture_base_words(uint32_t *base)
{
	if (!base) return -1;
	*base = 0x10000u; /* synthetic, 2048-word-page-aligned GS window in this host fixture */
	return 0;
}
int32_t bsp_render_hud_effect_texture_page_count(uint32_t *pages)
{
	if (!pages) return -1;
	*pages = 64u;
	return 0;
}
int32_t bsp_render_hud_effect_clut_base_words(uint32_t *base)
{
	if (!base) return -1;
	*base = 0x30000u; /* follows the 64-page HUD texture region */
	return 0;
}

static int parse_sha(const char *text, uint8_t hash[32])
{
	unsigned i, value;
	if (!text || strlen(text) != 64u) return 0;
	for (i = 0; i < 32u; ++i) {
		if (sscanf(text + i * 2u, "%2x", &value) != 1) return 0;
		hash[i] = (uint8_t)value;
	}
	return 1;
}

static int load_package(const char *path, uint32_t *size)
{
	FILE *file = fopen(path, "rb");
	long bytes;
	if (!file || fseek(file, 0, SEEK_END) || (bytes = ftell(file)) <= 0 ||
		(uint32_t)bytes > sizeof(package_bytes) || fseek(file, 0, SEEK_SET)) {
		if (file) fclose(file);
		return 0;
	}
	if (fread(package_bytes, 1, (size_t)bytes, file) != (size_t)bytes) {
		fclose(file); return 0;
	}
	fclose(file); *size = (uint32_t)bytes; return 1;
}

static void request_init(halo_ps2_bitmap_request *request, uint32_t generation)
{
	unsigned i;
	memset(request, 0, sizeof(*request));
	request->generation = generation;
	request->frame_index = 1;
	request->view_index = 0;
	request->bitmap_tag_index = (int32_t)bindings[0].bitmap_output_datum;
	request->bitmap_index = bindings[0].bitmap_index;
	request->framebuffer_blend_function = 0;
	request->point_sampled = 1; /* CE's multitexture overlay uses one local player's point-sampled path */
	request->has_multiply_map = 1;
	request->bitmap_wrap = 1; /* CE WPHI sets map_wrapped[0] for angle_ticks_mask. */
	request->multiply_bitmap_tag_index = (int32_t)bindings[1].bitmap_output_datum;
	request->multiply_bitmap_index = bindings[1].bitmap_index;
	request->multiply_slot = 0;
	request->multiply_scale_u = 1.0f;
	request->multiply_scale_v = 0.5f; /* retail WPHI map_scale[1].j=2, CE inverts it */
	request->multiply_offset_v = -0.232f;
	request->multiply_wrap = 0; /* WPHI map_clamp[1]=0 => CE map_wrapped=false */
	memset(request->multiply_tint, 255, sizeof(request->multiply_tint));
	for (i = 0; i < 4u; ++i) {
		request->vertices[i].x = (i == 1u || i == 2u) ? 100.0f : 92.0f;
		request->vertices[i].y = (i >= 2u) ? 597.0f : 85.0f;
		request->vertices[i].u = (i == 1u || i == 2u) ? 1.0f : 0.0f;
		request->vertices[i].v = (i >= 2u) ? 1.0f : 0.0f;
		request->vertices[i].color = 0xFFFFFFFFu;
	}
}

static int dispatch_one(uint32_t generation, uint8_t slot, halo_ps2_bitmap_request *request)
{
	halo_ps2_bitmap_request_reader reader;
	memset(&request_queue, 0, sizeof(request_queue));
	memset(&reader, 0, sizeof(reader));
	request_init(request, generation);
	request->multiply_slot = slot;
	request_queue.closed = 1; request_queue.readers = 1;
	request_queue.generation = generation; request_queue.frame_index = request->frame_index;
	request_queue.count = 1; request_queue.requests[0] = *request;
	reader.queue = &request_queue; reader.requests = request_queue.requests;
	reader.count = 1; reader.generation = generation; reader.held = 1;
	return hcu_bitmap_dispatch_reader(&reader, &context);
}

int main(int argc, char **argv)
{
	uint32_t package_size, generation;
	halo_ps2_bitmap_request request;
	hcu_bitmap_compose_source *first, *second;
	uint32_t output_offset, output_bytes, i, unique = 0;
	uint8_t seen[256] = {0};
	uint8_t native_palette_entries = 0;
	if (argc != 14 || !load_package(argv[1], &package_size)) return 2;
	generation = (uint32_t)strtoul(argv[3], NULL, 0);
	if (!generation || hcu_asset_profile_preflight(package_bytes, package_size,
		(uint32_t)strtoul(argv[2], NULL, 0), &profile) != HCU_ASSET_PROFILE_OK)
		return 3;
	memset(bindings, 0, sizeof(bindings));
	for (i = 0; i < 2u; ++i) {
		const unsigned arg = 4u + i * 4u;
		bindings[i].bitmap_output_datum = (uint32_t)strtoul(argv[arg], NULL, 0);
		bindings[i].bitmap_index = (uint16_t)strtoul(argv[arg + 1], NULL, 0);
		bindings[i].image_index = 0;
		bindings[i].chunk_id = (uint32_t)strtoul(argv[arg + 2], NULL, 0);
		bindings[i].cache_key = (uint16_t)(i + 1u);
		bindings[i].expected_source_datum = (uint32_t)strtoul(argv[arg + 3], NULL, 0);
		bindings[i].expected_profile_id = profile.profile_id;
	}
	/* The overlay hash is supplied by the exact profile manifest. */
	if (!parse_sha(argv[12], bindings[1].expected_chunk_sha256)) return 4;
	/* The base hash is read from the package directory entry by a fixture helper below. */
	{
		hcu_asset_chunk_view chunk;
		if (hcu_asset_profile_lookup(&profile, HCU_ASSET_CHUNK_MEDIA,
			bindings[0].chunk_id, &chunk) != HCU_ASSET_PROFILE_OK) return 5;
		memcpy(bindings[0].expected_chunk_sha256, chunk.sha256, 32);
	}
	tc_init(&cache, 64, 64, TC_MAX_KEYS, 1024u * 1024u);
	tc_begin_frame(&cache, 1);
	chain_init(&upload_chain, upload_memory, 4096u);
	chain_init(&geometry_chain, geometry_memory, 4096u);
	memset(&context, 0, sizeof(context));
	context.bindings = bindings; context.binding_count = 2;
	context.profile = &profile; context.expected_generation = generation; context.cache = &cache;
	context.journal = &journal; context.cache_readers = cache_readers; context.cache_reader_count = TC_MAX_KEYS;
	context.slots = slots; context.slot_count = 16;
	context.source_storage = source_storage; context.source_storage_bytes = sizeof(source_storage);
	context.slot_stride = sizeof(staging); context.staging_buffer = staging;
	context.staging_buffer_bytes = sizeof(staging); context.upload_chain = &upload_chain;
	context.geometry_chain = &geometry_chain; context.texture_page_base_words = 4096u;
	context.clut_base_words = 8192u; context.screen_w = 512; context.screen_h = 448;
	context.leases = leases; context.lease_capacity = 16;
	for (i = 0; i < HCU_BITMAP_COMPOSE_OUTPUT_REQUESTS; ++i) {
		int rc = dispatch_one(generation, (uint8_t)i, &request);
		if (rc != HCU_BITMAP_DISPATCH_OK ||
		context.lease_count != i + 1u || !leases[i].active || leases[i].cache_key != UINT16_MAX ||
			leases[i].slot != i || slots[i].storage_bytes != 2112u || slots[i].gs_page_count != 4u ||
			context.first_error != HCU_BITMAP_DISPATCH_OK) {
			fprintf(stderr, "dispatch1 i=%u rc=%d leases=%u active=%u key=%u slot=%u bytes=%u pages=%u first=%d\n",
				i, rc, context.lease_count, leases[i].active, leases[i].cache_key, leases[i].slot,
				slots[i].storage_bytes, slots[i].gs_page_count, context.first_error);
			return 6;
		}
	}
	if (!upload_chain.qw || !geometry_chain.qw) return 6;
	output_offset = slots[0].storage_offset;
	output_bytes = slots[0].storage_bytes;
	for (i = 0; i < output_bytes; ++i) if (!seen[source_storage[output_offset + i]]) {
		seen[source_storage[output_offset + i]] = 1; unique++;
	}
	if (unique < 2u || context.compose_sources[0].valid + context.compose_sources[1].valid != 2u)
		return 7;
	first = &context.compose_sources[0]; second = &context.compose_sources[1];
	if (first->generation != generation || second->generation != generation ||
		first->storage_offset < sizeof(source_storage) -
			HCU_BITMAP_COMPOSE_SOURCE_COUNT * HCU_BITMAP_COMPOSE_SOURCE_BYTES ||
		second->storage_offset < sizeof(source_storage) -
			HCU_BITMAP_COMPOSE_SOURCE_COUNT * HCU_BITMAP_COMPOSE_SOURCE_BYTES ||
		output_offset != sizeof(source_storage) - HCU_BITMAP_COMPOSE_RESERVED_BYTES ||
		output_offset + output_bytes > sizeof(source_storage) -
			HCU_BITMAP_COMPOSE_SOURCE_COUNT * HCU_BITMAP_COMPOSE_SOURCE_BYTES)
		return 8;
	fence_complete = 1;
	/* Hold all eight request slots from generation N, then fill the second physical
	 * frame bank for N+1 before either fence. This proves no live output is reused. */
	context.expected_generation = generation + 1u;
	for (i = 0; i < HCU_BITMAP_COMPOSE_OUTPUT_REQUESTS; ++i) {
		if (dispatch_one(generation + 1u, (uint8_t)i, &request) != HCU_BITMAP_DISPATCH_OK ||
			context.lease_count != HCU_BITMAP_COMPOSE_OUTPUT_REQUESTS + i + 1u ||
			leases[HCU_BITMAP_COMPOSE_OUTPUT_REQUESTS + i].slot != HCU_BITMAP_COMPOSE_OUTPUT_REQUESTS + i ||
			slots[HCU_BITMAP_COMPOSE_OUTPUT_REQUESTS + i].gs_page_first < 32u)
			return 10;
	}
	{
		hcu_bitmap_compose_source *base_source = NULL, *overlay_source = NULL;
		hud_effect_indexed_image base, overlay;
		hud_effect_map_transform base_transform, overlay_transform;
		char p4_path[1024];
		FILE *p4_file;
		for (i = 0; i < HCU_BITMAP_COMPOSE_SOURCE_COUNT; ++i) {
			hcu_bitmap_compose_source *source = &context.compose_sources[i];
			if (!source->valid || source->generation != generation + 1u) continue;
			if (source->expected_source_datum == bindings[0].expected_source_datum) base_source = source;
			if (source->expected_source_datum == bindings[1].expected_source_datum) overlay_source = source;
		}
		if (!base_source || !overlay_source) {
			for (i = 0; i < HCU_BITMAP_COMPOSE_SOURCE_COUNT; ++i)
				fprintf(stderr, "source[%u] valid=%u gen=%u id=%u\n", i,
					context.compose_sources[i].valid, context.compose_sources[i].generation,
					context.compose_sources[i].expected_source_datum);
			fprintf(stderr, "wanted=%u,%u current=%u\n", bindings[0].expected_source_datum,
				bindings[1].expected_source_datum, generation + 1u);
			return 14;
		}
		base.indices = source_storage + base_source->storage_offset;
		base.indices_bytes = base_source->index_bytes;
		base.clut_rgba32 = base.indices + base_source->index_bytes;
		base.width = base_source->width; base.height = base_source->height;
		base.clut_entries = base_source->clut_entries; base.psm = base_source->psm;
		overlay.indices = source_storage + overlay_source->storage_offset;
		overlay.indices_bytes = overlay_source->index_bytes;
		overlay.clut_rgba32 = overlay.indices + overlay_source->index_bytes;
		overlay.width = overlay_source->width; overlay.height = overlay_source->height;
		overlay.clut_entries = overlay_source->clut_entries; overlay.psm = overlay_source->psm;
		memset(&base_transform, 0, sizeof(base_transform));
		base_transform.scale_u = base_transform.scale_v = 1.0f;
		base_transform.wrap_u = base_transform.wrap_v = request.bitmap_wrap ? 1u : 0u;
		base_transform.tint_r = base_transform.tint_g = base_transform.tint_b = base_transform.fade = 255u;
		memset(&overlay_transform, 0, sizeof(overlay_transform));
		overlay_transform.scale_u = 1.0f; overlay_transform.scale_v = 0.5f;
		overlay_transform.offset_v = -0.232f; /* map_clamp[1]=0 keeps CE's clamp addressing */
		overlay_transform.tint_r = overlay_transform.tint_g = overlay_transform.tint_b = overlay_transform.fade = 255u;
		if (hud_effect_compose_multiply_indexed_psmt4_grid(&base, &overlay,
			&base_transform, &overlay_transform, 1, 8u, 512u,
			0.5f / 8.0f, 0.5f / 512.0f, 1.0f / 8.0f, 1.0f / 512.0f,
			native_p4_indices, sizeof(native_p4_indices), native_p4_palette,
			sizeof(native_p4_palette), &native_palette_entries) != 0 || native_palette_entries > 16u)
			return 15;
		if (snprintf(p4_path, sizeof(p4_path), "%s.p4", argv[13]) < 0) return 16;
		p4_file = fopen(p4_path, "wb");
		if (!p4_file || fwrite(native_p4_indices, 1, 8u * 512u / 2u, p4_file) != 8u * 512u / 2u ||
			fwrite(native_p4_palette, 1, sizeof(native_p4_palette), p4_file) != sizeof(native_p4_palette) ||
			fwrite(&native_palette_entries, 1, 1, p4_file) != 1) {
			if (p4_file) fclose(p4_file);
			return 17;
		}
		fclose(p4_file);
		printf("native-grid-p4-ok size=8x512 destination=8x512 palette=%u bytes=%u\n",
			(unsigned)native_palette_entries, (unsigned)(8u * 512u / 2u));
	}
	if (slots[0].storage_offset == slots[HCU_BITMAP_COMPOSE_OUTPUT_REQUESTS].storage_offset ||
		context.compose_sources[0].generation != generation + 1u ||
		hcu_bitmap_dispatch_complete(&context) != HCU_BITMAP_DISPATCH_OK || context.lease_count)
		return 9;
	for (i = 0; i < HCU_BITMAP_COMPOSE_OUTPUT_COUNT; ++i) if (slots[i].valid) return 9;
	/* A replaced map datum with a wrong expected source identity is refused before either chain changes. */
	context.expected_generation = generation + 2u;
	bindings[1].expected_source_datum++;
	{
		uint32_t up_before = upload_chain.qw, geom_before = geometry_chain.qw;
		if (dispatch_one(generation + 2u, 0u, &request) != HCU_BITMAP_DISPATCH_E_IDENTITY ||
			upload_chain.qw != up_before || geometry_chain.qw != geom_before ||
			request.generation != generation + 2u)
			return 11;
	}
	{
		FILE *output_file = fopen(argv[13], "wb");
		if (!output_file || fwrite(source_storage + output_offset, 1, output_bytes, output_file) != output_bytes) {
			if (output_file) fclose(output_file);
			return 13;
		}
		fclose(output_file);
	}
	printf("bitmap-compose-ok output=8x512 bytes=%u gs_pages=4 double_buffer_slots=16 sources=verified-indexed source_cache_generation=%u fence=held-and-released\n",
		output_bytes, (unsigned)(generation + 1u));
	return 0;
}
