#include "stream/hcu_bitmap_dispatch.h"
#include "render/gs.h"
#include "world/tex.h"

#include <math.h>
#include <string.h>
#include <stdint.h>

#if (defined(_EE) || defined(_MIPS_ARCH_R5900)) && ((defined(HALO_PS2_C3_TIMING) && HALO_PS2_C3_TIMING) || \
    (defined(HALO_PS2_C3_TELEMETRY) && HALO_PS2_C3_TELEMETRY))
#include "platform/timer.h"
#define BITMAP_CYCLES() timer_cycles()
#else
#define BITMAP_CYCLES() 0u
#endif

/* C3.10: weak links keep non-renderer host builds linkable. A lease release fails closed
 * when the exact BSP fence or release event is unavailable. */
extern uint32_t bsp_render_kick_seq(void) __attribute__((weak));
extern int32_t bsp_render_fence_observed(uint32_t kick_seq) __attribute__((weak));
extern int32_t bsp_render_source_release(uint32_t kind, uint32_t kick_seq) __attribute__((weak));
#define HCU_BITMAP_RELEASE_KIND_LEASE 2u   /* = BSP_SRC_BITMAP_LEASE in render/bsp_render.h */

#define HCU_BITMAP_PAGE_WORDS 2048u

hcu_bitmap_dispatch_status hcu_bitmap_dispatch_resident_bind(hcu_bitmap_dispatch_context *context,
	hcu_bitmap_resident_descriptor *descriptors, uint32_t descriptor_capacity)
{
	if (!context || (descriptor_capacity && !descriptors) ||
		context->lease_count || descriptor_capacity > UINT16_MAX ||
		(descriptor_capacity && (!context->profile || !context->expected_generation ||
		 !context->profile->profile_id || !context->bindings || !context->binding_count)))
		return HCU_BITMAP_DISPATCH_E_ARGUMENT;
	if (descriptors && descriptor_capacity)
		memset(descriptors, 0, descriptor_capacity * sizeof(*descriptors));
	context->resident_descriptors = descriptors;
	context->resident_capacity = descriptor_capacity;
	context->resident_generation = descriptor_capacity ? context->expected_generation : 0u;
	if (descriptor_capacity) context->resident_profile = *context->profile;
	else memset(&context->resident_profile, 0, sizeof(context->resident_profile));
	memset(&context->counters, 0, sizeof(context->counters));
	return HCU_BITMAP_DISPATCH_OK;
}

void hcu_bitmap_dispatch_resident_reset(hcu_bitmap_dispatch_context *context)
{
	if (!context || context->lease_count) return;
	if (context->resident_descriptors && context->resident_capacity)
		memset(context->resident_descriptors, 0,
			context->resident_capacity * sizeof(*context->resident_descriptors));
	memset(&context->counters, 0, sizeof(context->counters));
}

static int same_profile(const hcu_asset_profile_view *a, const hcu_asset_profile_view *b)
{
	return a && b && a->profile_id == b->profile_id && a->total_bytes == b->total_bytes &&
		a->chunk_count == b->chunk_count && a->directory_bytes == b->directory_bytes &&
		a->version == b->version && a->record_bytes == b->record_bytes &&
		a->read_at == b->read_at && a->reader_context == b->reader_context &&
		a->memory_image == b->memory_image;
}

static int descriptor_matches(const hcu_bitmap_resident_descriptor *d,
	const hcu_bitmap_binding *b, uint32_t generation)
{
	return d->valid && d->generation == generation && d->profile_id == b->expected_profile_id &&
		d->chunk_id == b->chunk_id && d->expected_source_datum == b->expected_source_datum &&
		d->image_index == b->image_index && d->cache_key == b->cache_key &&
		memcmp(d->chunk_sha256, b->expected_chunk_sha256, 32) == 0;
}

typedef struct {
	const hcu_asset_profile_view *source;
	hcu_bitmap_dispatch_counters *counters;
} bitmap_read_probe;

/* Count actual backing callbacks, including directory reads, without logging. */
static int bitmap_counted_read(void *opaque, uint32_t offset, void *destination, uint32_t bytes)
{
	bitmap_read_probe *p = (bitmap_read_probe *)opaque;
	uint32_t begin = BITMAP_CYCLES();
	int result;
	p->counters->read_calls++;
	p->counters->read_bytes += bytes;
	if (offset > p->source->total_bytes || bytes > p->source->total_bytes - offset) result = -1;
	else if (p->source->memory_image) {
		memcpy(destination, p->source->memory_image + offset, bytes);
		result = 0;
	} else result = p->source->read_at ?
		p->source->read_at(p->source->reader_context, offset, destination, bytes) : -1;
	p->counters->read_cycles += BITMAP_CYCLES() - begin;
	return result;
}

static int log2_exact(uint32_t n)
{
	int r = 0;
	if (!n || (n & (n - 1u))) return -1;
	while (n > 1u) { n >>= 1; r++; }
	return r;
}

static unsigned pages_for(uint32_t w, uint32_t h, uint32_t psm)
{
	uint32_t tbw = (w + 63u) / 64u;
	uint32_t page_h = psm == GS_PSMT4 ? 128u : 64u;
	if (tbw < 1u) tbw = 1u;
	return ((tbw + 1u) / 2u) * ((h + page_h - 1u) / page_h);
}

/* Meter (CE hud meter shader): the bitmap's alpha encodes the fill order and the request's
 * meter_value is the fill threshold (0..255). Two exact GS alpha-test passes partition it:
 * EMPTY draws the background where texel alpha < value, then FILL draws the gradient where it
 * is >= value. The gradient is min->max lerped at value/255 (integer), or the flash colour when
 * CE's flash is active. CE's per-channel combiner and subtractive flash are not reproduced.
 * Each pass is its own GIF packet with TEST set and restored, so no state leaks. */
static uint32_t meter_lerp_channel(uint32_t a, uint32_t b, uint32_t t)
{
	return (a * (255u - t) + b * t + 127u) / 255u;
}

static hcu_bitmap_quad_status meter_emit(chain_t *geometry_chain, const tex_info *image,
	hcu_bitmap_quad_state_t *state,
	const hcu_bitmap_vertex_t vertices[4], const halo_ps2_bitmap_request *request)
{
	hcu_bitmap_vertex_t quad[4];
	uint32_t t = request->meter_value, empty = request->meter_background_color, fill, i;
	hcu_bitmap_quad_status status;
	if (request->has_meter & HALO_PS2_BITMAP_METER_FLASHING) {
		fill = request->meter_flash_color & 0x00FFFFFFu;
	} else {
		uint32_t mn = request->meter_gradient_min_color, mx = request->meter_gradient_max_color;
		fill = (meter_lerp_channel((mn >> 16) & 255u, (mx >> 16) & 255u, t) << 16) |
			(meter_lerp_channel((mn >> 8) & 255u, (mx >> 8) & 255u, t) << 8) |
			meter_lerp_channel(mn & 255u, mx & 255u, t);
	}
	memcpy(quad, vertices, sizeof(quad));
	if (empty >> 24) {
		for (i = 0; i < 4; i++) quad[i].argb = empty;
		state->alpha_test = HCU_BITMAP_ALPHA_TEST_EMPTY;
		state->alpha_ref = (uint8_t)t;
		status = hcu_bitmap_quad_emit_validated(geometry_chain, image, state, quad);
		if (status != HCU_BITMAP_QUAD_OK) return status;
	}
	for (i = 0; i < 4; i++) quad[i].argb = fill | 0xFF000000u;
	state->alpha_test = HCU_BITMAP_ALPHA_TEST_FILL;
	state->alpha_ref = (uint8_t)t;
	return hcu_bitmap_quad_emit_validated(geometry_chain, image, state, quad);
}

static int blend_for(int16_t ce_blend, hcu_bitmap_blend_t *out)
{
	/* Values are the pinned CE shader_framebuffer_blend_function enum. */
	switch (ce_blend) {
	case 0: *out = HCU_BITMAP_BLEND_ALPHA; return 1;
	case 3: *out = HCU_BITMAP_BLEND_RAW_ADD; return 1;
	case 7: *out = HCU_BITMAP_BLEND_PREMULTIPLIED; return 1;
	default: return 0;
	}
}

static hcu_bitmap_dispatch_status dispatch_request_impl(
	hcu_bitmap_dispatch_context *context,
	const halo_ps2_bitmap_request *request,
	const hcu_bitmap_binding *bindings, uint32_t binding_count,
	const hcu_asset_profile_view *profile,
	uint32_t expected_generation,
	tc_t *cache, tc_journal_t *journal,
	uint16_t *cache_readers, uint32_t cache_reader_count,
	hcu_bitmap_source_slot *slots, uint32_t slot_count,
	void *source_storage, uint32_t source_storage_bytes, uint32_t slot_stride,
	void *staging_buffer, uint32_t staging_buffer_bytes,
	chain_t *upload_chain, chain_t *geometry_chain,
	uint32_t texture_page_base_words, uint32_t clut_base_words,
	uint16_t screen_w, uint16_t screen_h,
	hcu_bitmap_rect target, hcu_bitmap_lease *lease)
{
	uint32_t i, slot_index = 0, read_bytes;
	hcu_asset_chunk_view chunk_view;
	const hcu_bitmap_binding *binding = NULL;
	hcu_bitmap_source_slot *slot = NULL;
	uint8_t *raw;
	tex_section section;
	tex_info image;
	tex_mip_view mip;
	const uint8_t *clut;
	uint32_t clut_bytes, clut_w, clut_h, pages, tbw, tbp, cbp;
	uint32_t retained_bytes;
	const tc_entry *entry;
	tc_result acquired;
	chain_t upload_before, geometry_before;
	hcu_bitmap_quad_state_t state;
	hcu_bitmap_vertex_t vertices[4], placed[4];
	hcu_bitmap_blend_t blend;
	int upload_source;
	int resident_hit = 0;
	int resident_mode = context && context->resident_descriptors && context->resident_capacity;
	hcu_bitmap_resident_descriptor *descriptor = NULL, *empty_descriptor = NULL;
	hcu_asset_profile_view observed_profile;
	const hcu_asset_profile_view *read_profile = profile;
	bitmap_read_probe probe;
	uint32_t source_begin = 0, parse_begin = 0;

	if (!request || !bindings || !profile || !cache || !journal || !cache_readers || !slots ||
		!binding_count || !slot_count || !source_storage || !slot_stride || !staging_buffer || !upload_chain ||
		!geometry_chain || !lease || lease->active || !screen_w || !screen_h ||
		target.x < 0 || target.y < 0 || target.w <= 0 || target.h <= 0 ||
		target.x + target.w > screen_w || target.y + target.h > screen_h ||
		slot_count > UINT16_MAX || cache_reader_count < cache->max_keys ||
		cache_reader_count > TC_MAX_KEYS || !source_storage_bytes ||
		!slot_stride || slot_stride > staging_buffer_bytes ||
		(slot_stride & 15u) ||
		((uintptr_t)source_storage & 15u))
		return HCU_BITMAP_DISPATCH_E_ARGUMENT;
	if (request->generation != expected_generation)
		return HCU_BITMAP_DISPATCH_E_IDENTITY;
	if (request->bitmap_tag_index < 0 || request->bitmap_index >= 4096u)
		return HCU_BITMAP_DISPATCH_E_IDENTITY;
	for (i = 0; i < binding_count; i++)
		if (bindings[i].bitmap_output_datum == (uint32_t)request->bitmap_tag_index &&
			bindings[i].bitmap_index == request->bitmap_index) { binding = &bindings[i]; break; }
	if (!binding || binding->image_index != 0u || binding->cache_key >= cache->max_keys)
		return HCU_BITMAP_DISPATCH_E_IDENTITY;
	if (binding->expected_profile_id != profile->profile_id)
		return HCU_BITMAP_DISPATCH_E_IDENTITY;
	if (!blend_for(request->framebuffer_blend_function, &blend))
		return HCU_BITMAP_DISPATCH_E_UNSUPPORTED;

	if (cache_readers[binding->cache_key] == UINT16_MAX) return HCU_BITMAP_DISPATCH_E_BUSY;
	if (resident_mode) {
		if (context->resident_generation != expected_generation ||
			!same_profile(profile, &context->resident_profile))
			return HCU_BITMAP_DISPATCH_E_IDENTITY;
		for (i = 0; i < context->resident_capacity; ++i) {
			hcu_bitmap_resident_descriptor *d = &context->resident_descriptors[i];
			if (!d->valid) { if (!empty_descriptor) empty_descriptor = d; continue; }
			if (d->cache_key != binding->cache_key) continue;
			/* Reusing a numeric key for different bytes requires a new bound
			 * resource generation, even when the old VRAM entry was evicted. */
			if (!descriptor_matches(d, binding, expected_generation))
				return HCU_BITMAP_DISPATCH_E_IDENTITY;
			descriptor = d;
			break;
		}
	}
	memset(&image, 0, sizeof(image));
	memset(&mip, 0, sizeof(mip));
	clut = NULL;
	if (descriptor && cache->map[binding->cache_key]) {
		uint32_t index = cache->map[binding->cache_key] - 1u;
		if (index >= TC_MAX_ENTRIES || !cache->entry[index].valid ||
			cache->entry[index].key != binding->cache_key || cache->entry[index].pending_upload)
			return HCU_BITMAP_DISPATCH_E_BUSY;
		image.source_id = descriptor->expected_source_datum;
		image.width = descriptor->width; image.height = descriptor->height;
		image.psm = descriptor->psm; image.clut_entries = descriptor->clut_entries;
		mip.bytes = descriptor->mip_bytes;
		clut_bytes = descriptor->clut_bytes;
		resident_hit = 1;
		/* No package/directory lookup, read, hash, parser or source pointer on
		 * this path. A GPU lease is still acquired below for every draw. */
	} else {
		source_begin = BITMAP_CYCLES();
		if (context) {
			context->counters.misses++;
			probe.source = profile; probe.counters = &context->counters;
			observed_profile = *profile;
			observed_profile.memory_image = NULL;
			observed_profile.read_at = bitmap_counted_read;
			observed_profile.reader_context = &probe;
			read_profile = &observed_profile;
		}
		if (hcu_asset_profile_lookup(read_profile, HCU_ASSET_CHUNK_MEDIA,
			binding->chunk_id, &chunk_view) != HCU_ASSET_PROFILE_OK || chunk_view.size > slot_stride)
			return HCU_BITMAP_DISPATCH_E_CHUNK;
		if (memcmp(chunk_view.sha256, binding->expected_chunk_sha256, 32))
			return HCU_BITMAP_DISPATCH_E_IDENTITY;
		raw = (uint8_t *)staging_buffer;
		if (context) {
			context->counters.source_reads++;
			context->counters.source_bytes += chunk_view.size;
			context->counters.hash_checks++;
		}
		if (resident_mode) {
			hcu_asset_profile_staged_stats stats;
			int result = hcu_asset_profile_read_chunk_staged_profiled(read_profile,
				HCU_ASSET_CHUNK_MEDIA, binding->chunk_id, raw, slot_stride, &stats);
			context->counters.hash_cycles += stats.hash_cycles;
			context->counters.source_cycles += BITMAP_CYCLES() - source_begin;
			if (result != HCU_ASSET_PROFILE_OK) return HCU_BITMAP_DISPATCH_E_CHUNK;
		} else {
			int result = hcu_asset_profile_read_chunk(read_profile, HCU_ASSET_CHUNK_MEDIA,
				binding->chunk_id, raw, slot_stride);
			if (context) context->counters.source_cycles += BITMAP_CYCLES() - source_begin;
			if (result != HCU_ASSET_PROFILE_OK) return HCU_BITMAP_DISPATCH_E_CHUNK;
		}
		read_bytes = chunk_view.size;
		parse_begin = BITMAP_CYCLES();
		if (context) context->counters.parses++;
		if (tex_open(&section, raw, read_bytes) != TEX_OK || binding->image_index >= section.texture_count)
			return HCU_BITMAP_DISPATCH_E_FORMAT;
		image = tex_get(&section, binding->image_index);
		if (image.source_id != binding->expected_source_datum)
			return HCU_BITMAP_DISPATCH_E_IDENTITY;
		if ((image.psm != GS_PSMT8 && image.psm != GS_PSMT4) || !image.width || !image.height ||
			image.width > 256u || image.height > 256u || log2_exact(image.width) < 0 ||
			log2_exact(image.height) < 0 || !tex_mip(&section, &image, 0, &mip))
			return HCU_BITMAP_DISPATCH_E_FORMAT;
		clut = tex_clut(&section, &image);
		clut_bytes = (uint32_t)image.clut_entries * 4u;
		if (!clut || !clut_bytes || (mip.bytes & 15u) || (clut_bytes & 15u))
			return HCU_BITMAP_DISPATCH_E_FORMAT;
		if (context) context->counters.parse_cycles += BITMAP_CYCLES() - parse_begin;
	}
	if ((image.psm != GS_PSMT8 && image.psm != GS_PSMT4) ||
		!image.width || !image.height || image.width > 256u || image.height > 256u ||
		log2_exact(image.width) < 0 || log2_exact(image.height) < 0 ||
		!mip.bytes || (mip.bytes & 15u) || !clut_bytes || (clut_bytes & 15u) ||
		clut_bytes != (uint32_t)image.clut_entries * 4u)
		return HCU_BITMAP_DISPATCH_E_FORMAT;
	upload_source = !cache->map[binding->cache_key];
	if (upload_source) {
		for (slot_index = 0; slot_index < slot_count && slots[slot_index].valid; slot_index++) {}
		if (slot_index == slot_count) return HCU_BITMAP_DISPATCH_E_CAPACITY;
		slot = &slots[slot_index]; upload_source = 1;
	}
	clut_w = image.psm == GS_PSMT4 ? 8u : 16u;
	clut_h = image.psm == GS_PSMT4 ? 2u : 16u;
	pages = pages_for(image.width, image.height, image.psm);
	if (!pages || pages > cache->total_pages) return HCU_BITMAP_DISPATCH_E_CAPACITY;
	if (resident_hit && cache->entry[cache->map[binding->cache_key] - 1u].pages != pages)
		return HCU_BITMAP_DISPATCH_E_IDENTITY;
	if (texture_page_base_words > 0x3FFFu * 64u || clut_base_words > 0x3FFFu * 64u)
		return HCU_BITMAP_DISPATCH_E_ARGUMENT;

	/* Protect each outstanding source/GPU lease from tc's LRU eviction policy. */
	/* C3.7/bounded transaction: the journal records only what this request mutates (no whole-table copy).
	 * The reader-batch touch of leased entries runs once per batch before the first request. */
	tc_journal_begin(cache, journal);
	upload_before = *upload_chain;
	geometry_before = *geometry_chain;
	acquired = tc_acquire_j(cache, journal, binding->cache_key, pages,
		upload_source ? mip.bytes + clut_bytes : 0u, &entry);
	if (acquired != TC_HIT && acquired != TC_UPLOAD) {
		tc_journal_rollback(cache, journal);
		/* TC_DEFER: pages or budget are held by entries used this frame; retry next frame, not a failure. */
		return acquired == TC_DEFER ? HCU_BITMAP_DISPATCH_E_DEFERRED : HCU_BITMAP_DISPATCH_E_CAPACITY;
	}
	tbw = (image.width + 63u) / 64u;
	tbp = (texture_page_base_words + entry->first_page * HCU_BITMAP_PAGE_WORDS) / 64u;
	cbp = clut_base_words / 64u + entry->clut_slot * 4u;
	if (tbp > 0x3FFFu || cbp > 0x3FFFu) goto rollback;
	if (acquired == TC_UPLOAD) {
		if (!mip.pixels || !clut) goto rollback;
		/* Keep only the bytes the GIF upload chain references. HCP2 may make a
		 * TEXS resource much larger than its selected image; retaining the whole
		 * resource per lease would make storage scale with queue capacity instead
		 * of the existing per-frame tc upload budget. */
		retained_bytes = mip.bytes + clut_bytes;
		if (retained_bytes > source_storage_bytes) goto rollback;
		/* Each successful tc upload is charged against cache->budget_bytes. The
		 * packed cursor is monotonic until the actual paired-chain fence. */
		{
			uint32_t offset = 0;
			for (i = 0; i < slot_count; ++i) {
				uint32_t end;
				if (!slots[i].valid) continue;
				if (slots[i].storage_offset > source_storage_bytes ||
					slots[i].storage_bytes > source_storage_bytes - slots[i].storage_offset)
					goto rollback;
				end = slots[i].storage_offset + slots[i].storage_bytes;
				if (end > offset) offset = end;
			}
			if (offset > source_storage_bytes || retained_bytes > source_storage_bytes - offset)
				goto rollback;
			memcpy((uint8_t *)source_storage + offset, mip.pixels, mip.bytes);
			memcpy((uint8_t *)source_storage + offset + mip.bytes, clut, clut_bytes);
			mip.pixels = (const uint8_t *)source_storage + offset;
			clut = (const uint8_t *)source_storage + offset + mip.bytes;
			slot->storage_offset = offset;
			slot->storage_bytes = retained_bytes;
		}
		{
			uint32_t qwords_before = chain_qwords(upload_chain);
			if (gs_upload_pair(upload_chain, mip.pixels, mip.bytes, tbp, tbw, image.psm,
				image.width, image.height, clut, clut_bytes, cbp, clut_w, clut_h))
				goto rollback;
			/* C3.7: counted publish; queued is observed as the upload chain growing */
			if (!tc_publish_claim_j(cache, journal, binding->cache_key, chain_qwords(upload_chain) > qwords_before))
				goto rollback;
		}
	}
	memset(&state, 0, sizeof(state));
	state.tex0 = GS_TEX0(tbp, tbw, image.psm, (uint32_t)log2_exact(image.width),
		(uint32_t)log2_exact(image.height), 1, 0, cbp, GS_PSMCT32, 0, 0, 1);
	state.screen_w = screen_w; state.screen_h = screen_h;
	state.z = 0xFFFFFFu; state.blend = blend; state.texture_layers = 1;
	state.point_sampled = request->point_sampled;
	for (i = 0; i < 4; i++) {
		vertices[i].x = request->vertices[i].x; vertices[i].y = request->vertices[i].y;
		vertices[i].u = request->vertices[i].u; vertices[i].v = request->vertices[i].v;
		vertices[i].argb = request->vertices[i].color;
	}
	/* CE vertices are viewport-relative: offset into this view and clip to it. */
	if (hcu_bitmap_quad_place(&state, &target, vertices, placed) != 0) goto rollback;
	memcpy(vertices, placed, sizeof(vertices));
	if (request->has_meter & HALO_PS2_BITMAP_METER_PRESENT) {
		if (meter_emit(geometry_chain, &image,
			&state, vertices, request) != HCU_BITMAP_QUAD_OK)
			goto rollback;
	} else if (hcu_bitmap_quad_emit_validated(geometry_chain, &image,
		&state, vertices) != HCU_BITMAP_QUAD_OK) {
		goto rollback;
	}
	if (acquired == TC_UPLOAD) {
		slot->chunk_id = binding->chunk_id; slot->cache_key = binding->cache_key;
		slot->storage_bytes = retained_bytes; slot->valid = 1;
		slot->readers++;
	}
	cache_readers[binding->cache_key]++;
	lease->slot = acquired == TC_UPLOAD ? (uint16_t)slot_index : UINT16_MAX;
	lease->cache_key = binding->cache_key; lease->generation = request->generation; lease->active = 1;
	/* tc's built-in two-frame guard is supplemented by the explicit lease count. */
	for (i = 0; i < slot_count; i++)
		if (slots[i].valid && !slots[i].readers && slots[i].cache_key < cache->max_keys &&
			!cache->map[slots[i].cache_key]) memset(&slots[i], 0, sizeof(slots[i]));
	tc_journal_commit(journal);
	if (resident_hit) context->counters.hits++;
	else if (resident_mode && (descriptor || empty_descriptor)) {
		hcu_bitmap_resident_descriptor *d = descriptor ? descriptor : empty_descriptor;
		memset(d, 0, sizeof(*d));
		d->bitmap_output_datum = binding->bitmap_output_datum;
		d->bitmap_index = binding->bitmap_index; d->image_index = binding->image_index;
		d->cache_key = binding->cache_key; d->chunk_id = binding->chunk_id;
		d->expected_source_datum = binding->expected_source_datum;
		d->profile_id = binding->expected_profile_id; d->generation = expected_generation;
		d->width = image.width; d->height = image.height; d->psm = image.psm;
		d->clut_entries = image.clut_entries; d->mip_bytes = mip.bytes; d->clut_bytes = clut_bytes;
		d->source_offset = image.pixel_offset;
		memcpy(d->chunk_sha256, binding->expected_chunk_sha256, 32);
		d->valid = 1;
	}
	return HCU_BITMAP_DISPATCH_OK;

rollback:
	*upload_chain = upload_before;
	*geometry_chain = geometry_before;
	tc_journal_rollback(cache, journal);
	if (upload_source && slot) memset(slot, 0, sizeof(*slot));
	return HCU_BITMAP_DISPATCH_E_CAPACITY;
}

/* Compatibility entry point: mutable backing is revalidated on every call. */
hcu_bitmap_dispatch_status hcu_bitmap_dispatch_request(
	const halo_ps2_bitmap_request *request,
	const hcu_bitmap_binding *bindings, uint32_t binding_count,
	const hcu_asset_profile_view *profile, uint32_t expected_generation,
	tc_t *cache, tc_journal_t *journal, uint16_t *cache_readers, uint32_t cache_reader_count,
	hcu_bitmap_source_slot *slots, uint32_t slot_count,
	void *source_storage, uint32_t source_storage_bytes, uint32_t slot_stride,
	void *staging_buffer, uint32_t staging_buffer_bytes,
	chain_t *upload_chain, chain_t *geometry_chain,
	uint32_t texture_page_base_words, uint32_t clut_base_words,
	uint16_t screen_w, uint16_t screen_h, hcu_bitmap_rect target, hcu_bitmap_lease *lease)
{
	hcu_bitmap_dispatch_status status = dispatch_request_impl(NULL, request, bindings, binding_count, profile,
		expected_generation, cache, journal, cache_readers, cache_reader_count, slots, slot_count,
		source_storage, source_storage_bytes, slot_stride, staging_buffer, staging_buffer_bytes,
		upload_chain, geometry_chain, texture_page_base_words, clut_base_words,
		screen_w, screen_h, target, lease);
	/* Single-request callers have no batch to defer into; they keep the capacity status. */
	return status == HCU_BITMAP_DISPATCH_E_DEFERRED ? HCU_BITMAP_DISPATCH_E_CAPACITY : status;
}

void hcu_bitmap_dispatch_release(hcu_bitmap_source_slot *slots,
	uint32_t slot_count, uint16_t *cache_readers, uint32_t cache_reader_count,
	hcu_bitmap_lease *lease)
{
	if (!lease || !lease->active) return;
	if (cache_readers && lease->cache_key < cache_reader_count && cache_readers[lease->cache_key])
		cache_readers[lease->cache_key]--;
	if (slots && lease->slot < slot_count && slots[lease->slot].readers) {
		slots[lease->slot].readers--;
		if (!slots[lease->slot].readers) memset(&slots[lease->slot], 0, sizeof(slots[lease->slot]));
	}
	lease->active = 0;
}

int hcu_bitmap_dispatch_reader(const halo_ps2_bitmap_request_reader *reader,
	void *context)
{
	hcu_bitmap_dispatch_context *ctx = (hcu_bitmap_dispatch_context *)context;
	uint32_t i;
	if (!reader || !reader->held || !ctx || !reader->requests ||
		!ctx->leases || reader->count > ctx->lease_capacity ||
		reader->count > ctx->lease_capacity - ctx->lease_count || !ctx->cache ||
		!ctx->cache_readers || ctx->cache_reader_count < ctx->cache->max_keys ||
		reader->generation != ctx->expected_generation)
		return HCU_BITMAP_DISPATCH_E_ARGUMENT;
	ctx->first_error = HCU_BITMAP_DISPATCH_OK;
	/* leased entries stay protected for the whole batch; the touch is idempotent within the frame */
	hcu_bitmap_dispatch_touch_cache(ctx->cache, ctx->cache_readers, ctx->cache_reader_count);
	for (i = 0; i < reader->count; i++) {
		hcu_bitmap_lease *lease = &ctx->leases[ctx->lease_count];
		hcu_bitmap_dispatch_status status;
		hcu_bitmap_rect target;
		memset(lease, 0, sizeof(*lease));
		if (hcu_bitmap_view_resolve(ctx->views, ctx->view_count, reader->requests[i].view_index,
			ctx->screen_w, ctx->screen_h, &target) != 0) {
			if (ctx->first_error == HCU_BITMAP_DISPATCH_OK) ctx->first_error = HCU_BITMAP_DISPATCH_E_VIEW;
			continue;
		}
		status = dispatch_request_impl(ctx, &reader->requests[i], ctx->bindings,
			ctx->binding_count, ctx->profile, ctx->expected_generation,
			ctx->cache, ctx->journal, ctx->cache_readers, ctx->cache_reader_count,
			ctx->slots, ctx->slot_count,
			ctx->source_storage, ctx->source_storage_bytes, ctx->slot_stride,
			ctx->staging_buffer, ctx->staging_buffer_bytes,
			ctx->upload_chain, ctx->geometry_chain,
			ctx->texture_page_base_words, ctx->clut_base_words,
			ctx->screen_w, ctx->screen_h, target, lease);
		if (status == HCU_BITMAP_DISPATCH_OK) {
			if (reader->requests[i].has_meter & HALO_PS2_BITMAP_METER_PRESENT) ctx->meter_quads++;
			/* C3.10: dispatch runs inside the parent emit window, so the upload rides the next kick */
			lease->kick_seq = bsp_render_kick_seq ? bsp_render_kick_seq() + 1u : 0u;
			ctx->lease_count++;
		} else if (status == HCU_BITMAP_DISPATCH_E_DEFERRED) {
			/* Rolled back with no state change; the request is not drawn this frame and CE re-issues it. */
			ctx->counters.deferred++;
		} else if (ctx->first_error == HCU_BITMAP_DISPATCH_OK) ctx->first_error = status;
	}
	return ctx->first_error;
}

hcu_bitmap_dispatch_status hcu_bitmap_dispatch_complete(hcu_bitmap_dispatch_context *ctx)
{
	uint32_t i, remaining = 0;
	int blocked = 0;
	if (!ctx || !ctx->leases || !ctx->slots || !ctx->cache_readers ||
		ctx->lease_count > ctx->lease_capacity)
		return HCU_BITMAP_DISPATCH_E_ARGUMENT;
	for (i = 0; i < ctx->lease_count; i++) {
		hcu_bitmap_lease *lease = &ctx->leases[i];
		if (lease->active && lease->cache_key < ctx->cache_reader_count &&
			ctx->cache_readers[lease->cache_key] &&
			(lease->slot == UINT16_MAX || (lease->slot < ctx->slot_count &&
				ctx->slots[lease->slot].valid && ctx->slots[lease->slot].readers)) &&
			lease->kick_seq && bsp_render_fence_observed &&
			bsp_render_fence_observed(lease->kick_seq) == 1 && bsp_render_source_release &&
			bsp_render_source_release(HCU_BITMAP_RELEASE_KIND_LEASE, lease->kick_seq) == 1) {
			hcu_bitmap_dispatch_release(ctx->slots, ctx->slot_count, ctx->cache_readers,
				ctx->cache_reader_count, lease);
		}
		if (lease->active) {
			if (remaining != i) ctx->leases[remaining] = *lease;
			remaining++;
			blocked = 1;
		}
	}
	if (remaining < ctx->lease_count)
		memset(ctx->leases + remaining, 0, (ctx->lease_count - remaining) * sizeof(*ctx->leases));
	ctx->lease_count = remaining;
	return blocked ? HCU_BITMAP_DISPATCH_E_BUSY : HCU_BITMAP_DISPATCH_OK;
}

void hcu_bitmap_dispatch_touch_cache(tc_t *cache, const uint16_t *cache_readers,
	uint32_t cache_reader_count)
{
	uint32_t i;
	if (!cache || !cache_readers || cache_reader_count < cache->max_keys ||
		cache_reader_count > TC_MAX_KEYS) return;
	for (i = 0; i < cache->max_keys; i++) if (cache_readers[i] && cache->map[i])
		cache->entry[cache->map[i] - 1u].last_used = cache->frame;
}
