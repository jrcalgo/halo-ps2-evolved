#include "stream/hcu_bitmap_dispatch.h"
#include "render/gs.h"
#include "world/tex.h"

#include <math.h>
#include <string.h>
#include <stdint.h>

/* C3.10: weak links to the renderer's kick sequence and source-release event. Host builds do not link bsp_render,
 * so the references resolve to NULL and the lease kick/release bookkeeping is skipped. */
extern uint32_t bsp_render_kick_seq(void) __attribute__((weak));
extern int32_t bsp_render_source_release(uint32_t kind, uint32_t kick_seq) __attribute__((weak));
#define HCU_BITMAP_RELEASE_KIND_LEASE 2u   /* = BSP_SRC_BITMAP_LEASE in render/bsp_render.h */

#define HCU_BITMAP_PAGE_WORDS 2048u

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

hcu_bitmap_dispatch_status hcu_bitmap_dispatch_request(
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
	hcu_bitmap_lease *lease)
{
	uint32_t i, slot_index = 0, read_bytes;
	hcu_asset_chunk_view chunk_view;
	const hcu_bitmap_binding *binding = NULL;
	hcu_bitmap_source_slot *slot;
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
	hcu_bitmap_vertex_t vertices[4];
	hcu_bitmap_blend_t blend;
	int upload_source;

	if (!request || !bindings || !profile || !cache || !journal || !cache_readers || !slots ||
		!binding_count || !slot_count || !source_storage || !slot_stride || !staging_buffer || !upload_chain ||
		!geometry_chain || !lease || lease->active || !screen_w || !screen_h ||
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
	if (hcu_asset_profile_lookup(profile, HCU_ASSET_CHUNK_MEDIA,
		binding->chunk_id, &chunk_view) != HCU_ASSET_PROFILE_OK || chunk_view.size > slot_stride)
		return HCU_BITMAP_DISPATCH_E_CHUNK;
	if (memcmp(chunk_view.sha256, binding->expected_chunk_sha256, 32))
		return HCU_BITMAP_DISPATCH_E_IDENTITY;
	raw = (uint8_t *)staging_buffer;
	if (hcu_asset_profile_read_chunk(profile, HCU_ASSET_CHUNK_MEDIA,
		binding->chunk_id, raw, slot_stride) != HCU_ASSET_PROFILE_OK)
		return HCU_BITMAP_DISPATCH_E_CHUNK;
	read_bytes = chunk_view.size;
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
	upload_source = !cache->map[binding->cache_key];
	if (upload_source) {
		for (slot_index = 0; slot_index < slot_count && slots[slot_index].valid; slot_index++) {}
		if (slot_index == slot_count) return HCU_BITMAP_DISPATCH_E_CAPACITY;
		slot = &slots[slot_index]; upload_source = 1;
	}
	if (upload_source) {
		clut_w = image.psm == GS_PSMT4 ? 8u : 16u;
		clut_h = image.psm == GS_PSMT4 ? 2u : 16u;
	} else {
		clut_w = image.psm == GS_PSMT4 ? 8u : 16u;
		clut_h = image.psm == GS_PSMT4 ? 2u : 16u;
	}
	pages = pages_for(image.width, image.height, image.psm);
	if (!pages || pages > cache->total_pages) return HCU_BITMAP_DISPATCH_E_CAPACITY;
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
		return HCU_BITMAP_DISPATCH_E_CAPACITY;
	}
	tbw = (image.width + 63u) / 64u;
	tbp = (texture_page_base_words + entry->first_page * HCU_BITMAP_PAGE_WORDS) / 64u;
	cbp = clut_base_words / 64u + entry->clut_slot * 4u;
	if (tbp > 0x3FFFu || cbp > 0x3FFFu) goto rollback;
	if (acquired == TC_UPLOAD) {
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
	state.clip_w = screen_w; state.clip_h = screen_h;
	state.z = 0xFFFFFFu; state.blend = blend; state.texture_layers = 1;
	state.point_sampled = request->point_sampled;
	for (i = 0; i < 4; i++) {
		vertices[i].x = request->vertices[i].x; vertices[i].y = request->vertices[i].y;
		vertices[i].u = request->vertices[i].u; vertices[i].v = request->vertices[i].v;
		vertices[i].argb = request->vertices[i].color;
	}
	if (hcu_bitmap_quad_emit(geometry_chain, &section, binding->image_index,
		&state, vertices) != HCU_BITMAP_QUAD_OK)
		goto rollback;
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
	return HCU_BITMAP_DISPATCH_OK;

rollback:
	*upload_chain = upload_before;
	*geometry_chain = geometry_before;
	tc_journal_rollback(cache, journal);
	if (upload_source && slot) memset(slot, 0, sizeof(*slot));
	return HCU_BITMAP_DISPATCH_E_CAPACITY;
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
		memset(lease, 0, sizeof(*lease));
		status = hcu_bitmap_dispatch_request(&reader->requests[i], ctx->bindings,
			ctx->binding_count, ctx->profile, ctx->expected_generation,
			ctx->cache, ctx->journal, ctx->cache_readers, ctx->cache_reader_count,
			ctx->slots, ctx->slot_count,
			ctx->source_storage, ctx->source_storage_bytes, ctx->slot_stride,
			ctx->staging_buffer, ctx->staging_buffer_bytes,
			ctx->upload_chain, ctx->geometry_chain,
			ctx->texture_page_base_words, ctx->clut_base_words,
			ctx->screen_w, ctx->screen_h, lease);
		if (status == HCU_BITMAP_DISPATCH_OK) {
			/* C3.10: dispatch runs inside the parent emit window, so the upload rides the next kick */
			lease->kick_seq = bsp_render_kick_seq ? bsp_render_kick_seq() + 1u : 0u;
			ctx->lease_count++;
		} else if (ctx->first_error == HCU_BITMAP_DISPATCH_OK) ctx->first_error = status;
	}
	return ctx->first_error;
}

void hcu_bitmap_dispatch_complete(hcu_bitmap_dispatch_context *ctx)
{
	uint32_t i;
	if (!ctx || !ctx->leases || !ctx->slots) return;
	for (i = 0; i < ctx->lease_count; i++) {
		/* C3.10: the release event reads the fence of the kick that carried this lease's upload */
		if (ctx->leases[i].active && bsp_render_source_release)
			(void)bsp_render_source_release(HCU_BITMAP_RELEASE_KIND_LEASE, ctx->leases[i].kick_seq);
		hcu_bitmap_dispatch_release(ctx->slots, ctx->slot_count, ctx->cache_readers,
			ctx->cache_reader_count, &ctx->leases[i]);
	}
	ctx->lease_count = 0;
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
