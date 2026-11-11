#include <stdio.h>
#include "stream/hcu_bitmap_dispatch.h"
#include "stream/hcu_bitmap_defer_probe.h"
#include "render/gs.h"
#include "render/hud_effect.h"
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
extern int32_t bsp_render_hud_effect_texture_base_words(uint32_t *texture_page_base_words) __attribute__((weak));
extern int32_t bsp_render_hud_effect_texture_page_count(uint32_t *texture_page_count) __attribute__((weak));
extern int32_t bsp_render_hud_effect_clut_base_words(uint32_t *clut_base_words) __attribute__((weak));
#define HCU_BITMAP_RELEASE_KIND_LEASE 2u   /* = BSP_SRC_BITMAP_LEASE in render/bsp_render.h */

#define HCU_BITMAP_PAGE_WORDS 2048u

/* PINE-writable A/B control: nonzero keeps HUD source reads blocking. Blocking is the default: with the deferral on,
 * the HUD (ammo gauge, radar contents) and the first-person weapon textures stayed undrawn under real-time pacing even
 * though a fast headless run drew them, so deferral is opt-in until it is shown to hold at real speed. */
uint32_t g_hcu_bitmap_prefetch_off = 1u;

/* port: HUD chunk cache. A HUD bitmap that is not in the GS texture cache (a weapon just picked up, a HUD page not yet
 * drawn) is a synchronous disc read of 30-60 KB on the frame path, 125-425 ms per weapon, and that is the pickup lag.
 * The raw chunks are kept in a RAM region the caller hands over (the streaming map-owner arena, which production
 * gameplay never allocates from), filled once per map generation at the first HUD request from the binding table, and
 * on any miss after that. A hit is a memcpy; the bytes were verified when they were read. */
#define HUDC_ENTRIES 640u
static uint8_t *s_hudc_mem;
static uint32_t s_hudc_cap, s_hudc_used, s_hudc_count, s_hudc_gen, s_hudc_hits, s_hudc_stores;
static struct { uint32_t id, size, off, sha4, hits; } s_hudc[HUDC_ENTRIES];

void hcu_bitmap_chunk_cache_bind(void *mem, uint32_t bytes)
{
	s_hudc_mem = (uint8_t *)mem; s_hudc_cap = mem ? bytes : 0u;
	s_hudc_used = s_hudc_count = s_hudc_gen = 0u;
}
static uint32_t hudc_sha4(const uint8_t sha[32]) { uint32_t v; memcpy(&v, sha, 4); return v; }
static int hudc_find(uint32_t id, uint32_t size, const uint8_t sha[32])
{
	uint32_t i, k = hudc_sha4(sha);
	for (i = 0; i < s_hudc_count; i++)
		if (s_hudc[i].id == id && s_hudc[i].size == size && s_hudc[i].sha4 == k) return (int)i;
	return -1;
}
/* Frees room for `need` bytes by dropping entries nothing has read since the prewarm, last stored first, and packs the
 * rest down. Returns 1 when `need` now fits. */
static int hudc_make_room(uint32_t need)
{
	uint32_t i, live = 0u, kept = 0u;
	uint8_t drop[HUDC_ENTRIES];
	for (i = 0; i < s_hudc_count; i++) { drop[i] = 0u; live += (s_hudc[i].size + 15u) & ~15u; }
	for (i = s_hudc_count; i-- > 0 && s_hudc_cap - live < need + 16u;)
		if (!s_hudc[i].hits) { drop[i] = 1u; live -= (s_hudc[i].size + 15u) & ~15u; }
	if (s_hudc_cap - live < need + 16u) return 0;
	for (i = 0, s_hudc_used = 0u; i < s_hudc_count; i++) {
		if (drop[i]) continue;
		if (s_hudc[i].off != s_hudc_used) memmove(s_hudc_mem + s_hudc_used, s_hudc_mem + s_hudc[i].off, s_hudc[i].size);
		s_hudc[kept] = s_hudc[i]; s_hudc[kept].off = s_hudc_used;
		s_hudc_used += (s_hudc[i].size + 15u) & ~15u;
		kept++;
	}
	s_hudc_count = kept;
	return 1;
}
static void hudc_store(uint32_t id, uint32_t size, const uint8_t sha[32], const void *raw)
{
	uint32_t at;
	if (!s_hudc_mem || !size || hudc_find(id, size, sha) >= 0) return;
	if (s_hudc_count >= HUDC_ENTRIES || ((s_hudc_used + 15u) & ~15u) + size > s_hudc_cap)
		if (!hudc_make_room(size)) return;
	at = (s_hudc_used + 15u) & ~15u;
	memcpy(s_hudc_mem + at, raw, size);
	s_hudc[s_hudc_count].id = id; s_hudc[s_hudc_count].size = size; s_hudc[s_hudc_count].off = at;
	s_hudc[s_hudc_count].sha4 = hudc_sha4(sha); s_hudc[s_hudc_count].hits = 0u;
	s_hudc_count++; s_hudc_used = at + size; s_hudc_stores++;
}

/* Fill the cache from the binding table, once per map generation, before the first HUD frame is drawn. The whole set a
 * map can request is several MB, far more than the cache holds, while every weapon's HUD together needs a few dozen
 * small chunks (the 25 a full weapon cycle reads total 216 KB). So the small chunks go in first: those up to 2.5 KB,
 * then up to 9 KB, then up to 70 KB while room remains. A chunk the prewarm kept that nothing then reads is the first
 * to make way for one that is first read later. The chosen chunks are fetched in disc order, neighbours in one request
 * (a chunk costs a disc seek of about 20 ms read on its own, and a segment row read beside it) when the package was
 * accepted by the CRC check, so the payload bytes are the stored bytes. */
#define HUDC_PREWARM_MAX 1024u
#define HUDC_RUN_GAP 24576u
static void hudc_prewarm(const hcu_asset_profile_view *profile, const hcu_bitmap_binding *bindings,
	uint32_t binding_count, uint32_t generation, void *staging, uint32_t staging_bytes, uint32_t stride)
{
	static struct { uint32_t key, id, size, offset; uint8_t single, chosen; uint8_t sha[32]; } order[HUDC_PREWARM_MAX];
	uint32_t i, j, n = 0, skipped = 0, tier_n[4] = {0, 0, 0, 0}, tier_b[4] = {0, 0, 0, 0}, used = 0u, runs = 0u, raw_chunks = 0u;
	int raw_ok;
	if (!s_hudc_mem || s_hudc_gen == generation) return;
	s_hudc_gen = generation; s_hudc_used = s_hudc_count = 0u; s_hudc_hits = s_hudc_stores = 0u;
	for (i = 0; i < binding_count && n < HUDC_PREWARM_MAX; i++) {
		hcu_asset_chunk_view cv;
		int seen = 0;
		uint32_t tier;
		for (j = 0; j < i && !seen; j++) seen = bindings[j].chunk_id == bindings[i].chunk_id;
		if (seen || hcu_asset_profile_lookup(profile, HCU_ASSET_CHUNK_MEDIA, bindings[i].chunk_id, &cv) != HCU_ASSET_PROFILE_OK ||
			cv.size > stride || memcmp(cv.sha256, bindings[i].expected_chunk_sha256, 32)) continue;
		tier = cv.size <= 2560u ? 0u : cv.size <= 9216u ? 1u : cv.size <= 71680u ? 2u : 3u;
		if (tier == 3u) { skipped++; continue; }
		tier_n[tier]++; tier_b[tier] += cv.size;
		order[n].key = (tier << 28) | (cv.offset & 0x0FFFFFFFu);
		order[n].id = bindings[i].chunk_id; order[n].size = cv.size; order[n].offset = cv.offset;
		order[n].single = cv.segment_count == 1u && cv.size <= HCU_ASSET_PROFILE_MAX_MEDIA_CHUNK_BYTES;
		order[n].chosen = 0u;
		memcpy(order[n].sha, cv.sha256, 32);
		n++;
	}
	for (i = 1; i < n; i++) {                       /* by tier, then disc offset */
		__typeof__(order[0]) t = order[i];
		for (j = i; j > 0 && order[j - 1].key > t.key; j--) order[j] = order[j - 1];
		order[j] = t;
	}
	for (i = 0; i < n && used < HUDC_ENTRIES; i++) {   /* what fits, in tier order */
		uint32_t need = (order[i].size + 15u) & ~15u;
		if (s_hudc_used + need > s_hudc_cap) continue;
		order[i].chosen = 1u; s_hudc_used += need; used++;
	}
	s_hudc_used = 0u;
	/* Fetch in disc order: sort the chosen by offset. */
	for (i = 1; i < n; i++) {
		__typeof__(order[0]) t = order[i];
		for (j = i; j > 0 && order[j - 1].offset > t.offset; j--) order[j] = order[j - 1];
		order[j] = t;
	}
	raw_ok = hcu_asset_profile_fast_trusted() > 0 && staging_bytes >= 4096u;
	if (raw_ok) {                                   /* the stored bytes must be the chunk: check one against a staged read */
		for (i = 0; i < n && !(order[i].chosen && order[i].single); i++) {}
		if (i < n) {
			hcu_asset_profile_staged_stats stats;
			raw_ok = hcu_asset_profile_read_raw(profile, order[i].offset, staging, order[i].size) == HCU_ASSET_PROFILE_OK &&
				hcu_asset_profile_read_chunk_staged_profiled(profile, HCU_ASSET_CHUNK_MEDIA, order[i].id, s_hudc_mem,
					s_hudc_cap, &stats) == HCU_ASSET_PROFILE_OK &&
				memcmp(staging, s_hudc_mem, order[i].size) == 0;
			if (!raw_ok) printf("HALO_PS2_LOCAL hud-chunk-cache raw-check-failed chunk=%u\n", (unsigned)order[i].id);
		}
	}
	for (i = 0; i < n;) {
		hcu_asset_profile_staged_stats stats;
		uint32_t first = i, end, last, span;
		if (!order[i].chosen) { i++; continue; }
		if (raw_ok && order[i].single) {
			end = order[i].offset + order[i].size; last = i;
			for (j = i + 1; j < n; j++) {
				if (!order[j].chosen) continue;
				if (!order[j].single || order[j].offset < end || order[j].offset - end > HUDC_RUN_GAP ||
					order[j].offset + order[j].size - order[first].offset > staging_bytes) break;
				end = order[j].offset + order[j].size; last = j;
			}
			span = end - order[first].offset;
			if (hcu_asset_profile_read_raw(profile, order[first].offset, staging, span) == HCU_ASSET_PROFILE_OK) {
				runs++;
				for (j = first; j <= last; j++)
					if (order[j].chosen && order[j].single && order[j].offset >= order[first].offset &&
						order[j].offset + order[j].size <= end) {
						hudc_store(order[j].id, order[j].size, order[j].sha,
							(const uint8_t *)staging + (order[j].offset - order[first].offset));
						raw_chunks++;
					}
				i = last + 1;
				continue;
			}
		}
		if (hcu_asset_profile_read_chunk_staged_profiled(profile, HCU_ASSET_CHUNK_MEDIA, order[i].id, staging, stride,
			&stats) == HCU_ASSET_PROFILE_OK)
			hudc_store(order[i].id, order[i].size, order[i].sha, staging);
		i++;
	}
	printf("HALO_PS2_LOCAL hud-chunk-cache prewarm bindings=%u candidates=%u too-big=%u chunks=%u bytes=%u cap=%u "
		"raw-runs=%u raw-chunks=%u tier0=%u/%u tier1=%u/%u tier2=%u/%u\n",
		(unsigned)binding_count, (unsigned)n, (unsigned)skipped, (unsigned)s_hudc_count, (unsigned)s_hudc_used,
		(unsigned)s_hudc_cap, (unsigned)runs, (unsigned)raw_chunks, (unsigned)tier_n[0], (unsigned)tier_b[0],
		(unsigned)tier_n[1], (unsigned)tier_b[1], (unsigned)tier_n[2], (unsigned)tier_b[2]);
}

int32_t hcu_bitmap_dispatch_capture_screen_effects(hcu_bitmap_dispatch_context *context,
	const halo_ps2_bitmap_request_queue *queue)
{
	uint32_t i;
	if (!context || !queue || !queue->closed || queue->open || !queue->readers ||
		queue->generation != context->expected_generation ||
		queue->count > HALO_PS2_BITMAP_REQUEST_CAPACITY)
		return HCU_BITMAP_DISPATCH_E_ARGUMENT;
	/* The pre-HUD callback and the later bitmap drain both observe this same
	 * sealed queue. Keep the callback's backend result when the drain arrives. */
	if (context->screen_effect_snapshot_valid &&
		context->screen_effect_generation == queue->generation &&
		context->screen_effect_frame_index == queue->frame_index)
		return HCU_BITMAP_DISPATCH_OK;
	memset(context->screen_effects, 0, sizeof(context->screen_effects));
	context->screen_effect_valid_mask = 0;
	memset(context->screen_effect_prepared_request_mask, 0,
		sizeof(context->screen_effect_prepared_request_mask));
	context->screen_effect_prepared_count = 0;
	memset(context->screen_effect_mask_tex0, 0, sizeof(context->screen_effect_mask_tex0));
	memset(context->screen_effect_mask_clamp, 0, sizeof(context->screen_effect_mask_clamp));
	context->screen_effect_mask_texture_valid_mask = 0;
	context->screen_effect_generation = queue->generation;
	context->screen_effect_frame_index = queue->frame_index;
	context->screen_effect_snapshot_valid = 1;
	/* Until a native PS2 compositor is installed, capturing parameters must not
	 * imply that an effect was applied. */
	context->screen_effect_backend_active = 0;
	for (i = 0; i < HALO_PS2_BITMAP_MAX_VIEWS; ++i) {
		if (queue->screen_effects[i].valid) {
			context->screen_effects[i] = queue->screen_effects[i];
			context->screen_effect_valid_mask |= 1u << i;
		}
	}
	return HCU_BITMAP_DISPATCH_OK;
}

void hcu_bitmap_dispatch_screen_effect_reset(hcu_bitmap_dispatch_context *context)
{
	if (!context) return;
	memset(context->screen_effects, 0, sizeof(context->screen_effects));
	context->screen_effect_valid_mask = 0;
	memset(context->screen_effect_prepared_request_mask, 0,
		sizeof(context->screen_effect_prepared_request_mask));
	context->screen_effect_prepared_count = 0;
	memset(context->screen_effect_mask_tex0, 0, sizeof(context->screen_effect_mask_tex0));
	memset(context->screen_effect_mask_clamp, 0, sizeof(context->screen_effect_mask_clamp));
	context->screen_effect_mask_texture_valid_mask = 0;
	context->screen_effect_generation = 0;
	context->screen_effect_frame_index = 0;
	context->screen_effect_snapshot_valid = 0;
	context->screen_effect_backend_active = 0;
}

int32_t hcu_bitmap_dispatch_screen_effect_get(const hcu_bitmap_dispatch_context *context,
	uint32_t generation, uint32_t frame_index, uint16_t view_index,
	halo_ps2_screen_effect_state *state)
{
	if (!context || !state || view_index >= HALO_PS2_BITMAP_MAX_VIEWS)
		return HCU_BITMAP_DISPATCH_E_ARGUMENT;
	if (!context->screen_effect_snapshot_valid || context->screen_effect_generation != generation ||
		context->screen_effect_frame_index != frame_index ||
		generation != context->expected_generation)
		return HCU_BITMAP_DISPATCH_E_VIEW;
	if (!(context->screen_effect_valid_mask & (1u << view_index))) return 0;
	*state = context->screen_effects[view_index];
	return 1;
}

int32_t hcu_bitmap_dispatch_screen_effect_mask_get(const hcu_bitmap_dispatch_context *context,
	uint32_t generation, uint32_t frame_index, uint16_t view_index,
	uint64_t *tex0, uint64_t *clamp)
{
	if (!context || !tex0 || !clamp || view_index >= HALO_PS2_BITMAP_MAX_VIEWS)
		return HCU_BITMAP_DISPATCH_E_ARGUMENT;
	if (!context->screen_effect_snapshot_valid || context->screen_effect_generation != generation ||
		context->screen_effect_frame_index != frame_index || generation != context->expected_generation)
		return HCU_BITMAP_DISPATCH_E_VIEW;
	if (!(context->screen_effect_mask_texture_valid_mask & (1u << view_index))) return 0;
	*tex0 = context->screen_effect_mask_tex0[view_index];
	*clamp = context->screen_effect_mask_clamp[view_index];
	return 1;
}

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

/* Meter (CE hud meter shader, matching the N64 meter_surface the Xbox combiner
 * implements): texel alpha is the fill order. order >= flash alpha (the maximum)
 * is the empty background; order < gradient_min alpha is the solid colour, lerped
 * min->max at that threshold; the band [min, max) is the flash colour (damage and
 * recharge). When CE is not flashing the two alphas are equal, so the band is
 * empty and one threshold partitions the meter. A GS alpha test cannot lerp a
 * different colour per texel, so the solid region is one colour. Each pass is
 * its own GIF packet with TEST set and restored. */
static uint32_t meter_lerp_channel(uint32_t a, uint32_t b, uint32_t t)
{
	return (a * (255u - t) + b * t + 127u) / 255u;
}

/* Texel alpha in the converted textures is on the GS scale (0x80 = 1.0) while CE's meter value is
 * 0..255, so the alpha-test reference is rescaled. The GS tests the alpha after MODULATE, i.e.
 * texel * vertex_alpha / 0x80, so a pass whose vertex alpha is not 1.0 scales its reference too. */
uint8_t hcu_bitmap_meter_alpha_ref(uint32_t value, uint32_t vertex_alpha)
{
	uint32_t ref = (value * 128u + 127u) / 255u;
	uint32_t va = (vertex_alpha * 128u + 127u) / 255u;
	return (uint8_t)((ref * va + 64u) / 128u);
}

static hcu_bitmap_quad_status meter_emit(chain_t *geometry_chain, const tex_info *image,
	hcu_bitmap_quad_state_t *state,
	const hcu_bitmap_vertex_t vertices[4], const halo_ps2_bitmap_request *request)
{
	hcu_bitmap_vertex_t quad[4];
	uint32_t min_a = request->meter_value;
	uint32_t max_a = request->meter_flash_color >> 24;
	uint32_t empty = request->meter_background_color;
	uint32_t mn = request->meter_gradient_min_color, mx = request->meter_gradient_max_color;
	uint32_t solid, flash, i;
	int flashing = (request->has_meter & HALO_PS2_BITMAP_METER_FLASHING) && max_a > min_a;
	hcu_bitmap_blend_t saved = state->blend;
	hcu_bitmap_quad_status status;
	solid = (meter_lerp_channel((mn >> 16) & 255u, (mx >> 16) & 255u, min_a) << 16) |
		(meter_lerp_channel((mn >> 8) & 255u, (mx >> 8) & 255u, min_a) << 8) |
		meter_lerp_channel(mn & 255u, mx & 255u, min_a);
	flash = (request->meter_flash_color & 0x00FFFFFFu) | 0xFF000000u;
	memcpy(quad, vertices, sizeof(quad));
	/* Flash is added for order >= min, then subtracted for order >= max, so
	 * only the band [min, max) remains. An alpha blend cannot punch that hole. */
	if (flashing) {
		for (i = 0; i < 4; i++) quad[i].argb = flash;
		state->blend = HCU_BITMAP_BLEND_RAW_ADD;
		state->alpha_test = HCU_BITMAP_ALPHA_TEST_FILL;
		state->alpha_ref = hcu_bitmap_meter_alpha_ref(min_a, 255u);
		status = hcu_bitmap_quad_emit_validated(geometry_chain, image, state, quad);
		if (status != HCU_BITMAP_QUAD_OK) { state->blend = saved; return status; }
		state->blend = HCU_BITMAP_BLEND_SUBTRACT;
		state->alpha_ref = hcu_bitmap_meter_alpha_ref(max_a, 255u);
		status = hcu_bitmap_quad_emit_validated(geometry_chain, image, state, quad);
		state->blend = saved;
		if (status != HCU_BITMAP_QUAD_OK) return status;
	}
	if (empty >> 24) {
		for (i = 0; i < 4; i++) quad[i].argb = empty;
		state->alpha_test = HCU_BITMAP_ALPHA_TEST_FILL;
		state->alpha_ref = hcu_bitmap_meter_alpha_ref(max_a, empty >> 24);
		status = hcu_bitmap_quad_emit_validated(geometry_chain, image, state, quad);
		if (status != HCU_BITMAP_QUAD_OK) return status;
	}
	if (!min_a) return HCU_BITMAP_QUAD_OK;
	for (i = 0; i < 4; i++) quad[i].argb = solid | 0xFF000000u;
	state->alpha_test = HCU_BITMAP_ALPHA_TEST_EMPTY;
	state->alpha_ref = hcu_bitmap_meter_alpha_ref(min_a, 255u);
	return hcu_bitmap_quad_emit_validated(geometry_chain, image, state, quad);
}

/* The Xbox meter shader (rasterizer_xbox_dynavobgeom.c, its register combiners decoded) works on a
 * texel's Y (the fill order) and alpha (the shape):
 *   alpha 0                    killed.
 *   Y >= flash alpha           the empty colour, kept (1 - empty alpha) of what is behind.
 *   else                       lerp(min colour, max colour, Y), plus the flash colour while Y is at
 *                              or above the fill threshold (the band between the two thresholds),
 *                              kept (1 - opacity) of what is behind.
 *   then colour * shape alpha * tint.rgb is added to the retained backdrop.
 * The GS alpha test sees one channel, so the meter bitmap's index holds both (shape level in the
 * top two bits, Y >> 2 in the rest; see halo2ps2 texconv.convert_meter_rgba) and this builds the
 * palette that turns each into that texel's result. Returns 1 when the entries are premultiplied
 * (draw with Cs + Cd * (1 - As)), 0 when they are ordinary alpha-blend colours. */
static const uint8_t k_meter_shape_level[4] = { 0u, 127u, 191u, 255u };

static float meter_clamp(float v, float lo, float hi)
{
	return v < lo ? lo : v > hi ? hi : v;
}

static float meter_channel(uint32_t color, unsigned shift)
{
	return (float)((color >> shift) & 255u) * (1.0f / 255.0f);
}

int hcu_bitmap_meter_build_clut(const halo_ps2_bitmap_request *request, uint8_t clut[1024])
{
	float pr[256], pg[256], pb[256], pa[256];
	float threshold, flash_alpha, empty_keep, filled_keep;
	float min_c[3], max_c[3], flash_c[3], empty_c[3], tint[3];
	int negative_flash = 0, premultiplied = 0;
	unsigned i, k;
	threshold = (float)request->meter_value * (1.0f / 255.0f);
	flash_alpha = meter_channel(request->meter_flash_color, 24);
	empty_keep = meter_channel(request->meter_background_color, 24);
	filled_keep = meter_channel(request->meter_tint_color, 24);
	for (k = 0; k < 3u; ++k) {
		unsigned shift = 16u - 8u * k;
		min_c[k] = meter_channel(request->meter_gradient_min_color, shift);
		max_c[k] = meter_channel(request->meter_gradient_max_color, shift);
		flash_c[k] = meter_channel(request->meter_flash_color, shift);
		empty_c[k] = meter_channel(request->meter_background_color, shift);
		tint[k] = meter_channel(request->meter_tint_color, shift);
	}
	for (i = 0; i < 256u; ++i) {
		float shape = (float)k_meter_shape_level[i >> 6] * (1.0f / 255.0f);
		/* The bin's low edge, not its centre: the retail thresholds are mult * rounds + bias with the bullets' Y at
		 * mult * k (sniper 60, rocket launcher 120, assault rifle 4), so a bullet is filled only while its Y is
		 * below the threshold; the centre (Y + 2) pushed the top bullet of a full magazine over it. */
		float y = (float)((i & 63u) * 4u) * (1.0f / 255.0f), keep, ramp, band, col[3];
		if (!(i >> 6)) { pr[i] = pg[i] = pb[i] = pa[i] = 0.0f; continue; }
		if (y > 1.0f) y = 1.0f;
		if (y >= flash_alpha) {
			for (k = 0; k < 3u; ++k) col[k] = empty_c[k];
			keep = empty_keep;
		} else {
			/* 4 * (threshold - Y) clamped, then 1 - 2x: 1 at and above the threshold, 0 a
			 * little below it (the flash band's soft lower edge). */
			ramp = meter_clamp(4.0f * (threshold - y), 0.0f, 1.0f);
			band = 1.0f - 2.0f * ramp;
			if (band < 0.0f) band = 0.0f;
			for (k = 0; k < 3u; ++k) {
				float g = (1.0f - y) * min_c[k] + y * max_c[k];
				g += band * (negative_flash ? -flash_c[k] : flash_c[k]);
				col[k] = meter_clamp(g, 0.0f, 1.0f);
			}
			keep = filled_keep;
		}
		pr[i] = col[0] * shape * tint[0];
		pg[i] = col[1] * shape * tint[1];
		pb[i] = col[2] * shape * tint[2];
		pa[i] = 1.0f - keep;
		if ((pr[i] > pa[i] + 0.002f || pg[i] > pa[i] + 0.002f || pb[i] > pa[i] + 0.002f)) premultiplied = 1;
	}
	for (i = 0; i < 256u; ++i) {
		/* CSM1 order: the entries of blocks 8-15 and 16-23 swap. */
		uint32_t pos = (i & 0xE7u) | ((i & 0x08u) << 1) | ((i & 0x10u) >> 1);
		uint8_t *e = clut + pos * 4u;
		float a = pa[i], r = pr[i], g = pg[i], b = pb[i];
		if (!premultiplied && a > 0.0f) { r /= a; g /= a; b /= a; }
		else if (!premultiplied) r = g = b = 0.0f;
		e[0] = (uint8_t)(meter_clamp(r, 0.0f, 1.0f) * 255.0f + 0.5f);
		e[1] = (uint8_t)(meter_clamp(g, 0.0f, 1.0f) * 255.0f + 0.5f);
		e[2] = (uint8_t)(meter_clamp(b, 0.0f, 1.0f) * 255.0f + 0.5f);
		e[3] = (uint8_t)(meter_clamp(a, 0.0f, 1.0f) * 128.0f + 0.5f);
	}
	return premultiplied;
}

/* Draws a meter from a texture built by convert_meter_rgba with a palette made for this draw,
 * uploaded to one of the HUD's scratch CLUT slots and held by the lease until the kick that
 * carries it is done. 1: drawn. 0: not applicable (no scratch slot or another kind of texture),
 * the caller draws the old alpha-test passes. -1: the chains are full. */
static int meter_emit_palette(hcu_bitmap_dispatch_context *ctx, const tex_info *image,
	hcu_bitmap_quad_state_t *state, hcu_bitmap_vertex_t vertices[4],
	const halo_ps2_bitmap_request *request, uint32_t tbp, uint32_t tbw,
	chain_t *upload_chain, chain_t *geometry_chain, hcu_bitmap_lease *lease)
{
	uint8_t clut[1024] __attribute__((aligned(16)));
	uint32_t physical_slot, slot_index, clut_words, cbp, i;
	int premultiplied;
	if (!ctx || !ctx->slots || ctx->slot_count < HCU_BITMAP_COMPOSE_OUTPUT_COUNT || !lease ||
		image->psm != GS_PSMT8 || !(image->flags & TEX_F_METER) ||
		!bsp_render_hud_effect_clut_base_words || bsp_render_hud_effect_clut_base_words(&clut_words) != 0)
		return 0;
	for (physical_slot = 0; physical_slot < HCU_BITMAP_COMPOSE_OUTPUT_COUNT; ++physical_slot) {
		slot_index = ctx->slot_count - HCU_BITMAP_COMPOSE_OUTPUT_COUNT + physical_slot;
		if (!ctx->slots[slot_index].valid && !ctx->slots[slot_index].readers) break;
	}
	if (physical_slot == HCU_BITMAP_COMPOSE_OUTPUT_COUNT) return 0;
	cbp = clut_words / 64u + physical_slot * 4u;
	if (cbp + 3u >= 0x4000u) return 0;
	premultiplied = hcu_bitmap_meter_build_clut(request, clut);
	if (gs_upload_inline(upload_chain, clut, sizeof(clut), cbp, 1u, GS_PSMCT32, 16u, 16u)) return -1;
	state->tex0 = GS_TEX0(tbp, tbw, GS_PSMT8, (uint32_t)log2_exact(image->width),
		(uint32_t)log2_exact(image->height), 1, 0, cbp, GS_PSMCT32, 0, 0, 1);
	state->blend = premultiplied ? HCU_BITMAP_BLEND_PREMULTIPLIED : HCU_BITMAP_BLEND_ALPHA;
	state->alpha_test = HCU_BITMAP_ALPHA_TEST_NONE;
	for (i = 0; i < 4u; ++i) vertices[i].argb = 0xFFFFFFFFu;
	if (hcu_bitmap_quad_emit_validated(geometry_chain, image, state, vertices) != HCU_BITMAP_QUAD_OK) return -1;
	memset(&ctx->slots[slot_index], 0, sizeof(ctx->slots[slot_index]));
	ctx->slots[slot_index].cache_key = UINT16_MAX;
	ctx->slots[slot_index].readers = 1; ctx->slots[slot_index].valid = 1; ctx->slots[slot_index].reserved8 = 1;
	ctx->slots[slot_index].compose_clut_slot = (uint16_t)physical_slot;
	lease->reserved = (uint16_t)(slot_index + 1u);
	return 1;
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

static const hcu_bitmap_binding *binding_find(const hcu_bitmap_binding *bindings,
	uint32_t count, int32_t datum, uint16_t bitmap_index)
{
	uint32_t i;
	if (datum < 0) return NULL;
	for (i = 0; i < count; ++i)
		if (bindings[i].bitmap_output_datum == (uint32_t)datum &&
			bindings[i].bitmap_index == bitmap_index && bindings[i].image_index == 0u)
			return &bindings[i];
	return NULL;
}

/* The scope masks (hcu_profile_bitmap.SCOPE_MASK_BITMAPS) are the only bitmaps allowed above the normal 256px cap: black
 * texels whose alpha is the mask's Y, PSMT4 with 16 levels (PSMT8 with 256 for an older package). The full-view mask is
 * 512x256 and the split-view masks 256x256, so the shape (not a datum) is what admits one on any map. */
static int screen_effect_mask_shape(const halo_ps2_bitmap_request *request,
	const tex_info *image, uint32_t mip_bytes, uint32_t clut_bytes)
{
	uint32_t texels;
	if (!request || !image || !request->screen_effect_mask) return 0;
	if (!((image->width == 512u && image->height == 256u) || (image->width == 256u && image->height == 256u))) return 0;
	texels = (uint32_t)image->width * image->height;
	if (image->psm == GS_PSMT4) return image->clut_entries == 16u && clut_bytes == 64u && mip_bytes == texels / 2u;
	if (image->psm == GS_PSMT8) return image->clut_entries == 256u && clut_bytes == 1024u && mip_bytes == texels;
	return 0;
}

static int compose_source_matches(const hcu_bitmap_compose_source *source,
	const hcu_bitmap_binding *binding, uint32_t generation)
{
	return source->valid && source->generation == generation &&
		source->bitmap_output_datum == binding->bitmap_output_datum &&
		source->bitmap_index == binding->bitmap_index && source->image_index == binding->image_index &&
		source->chunk_id == binding->chunk_id &&
		source->expected_source_datum == binding->expected_source_datum &&
		source->expected_profile_id == binding->expected_profile_id &&
		memcmp(source->chunk_sha256, binding->expected_chunk_sha256, 32) == 0;
}

/* Load and pin only the verified indexed texels and CLUT. At 4 KiB per entry,
 * the four-entry source cache occupies 16 KiB and needs no heap or map I/O on a
 * cache hit. Each map change is checked against its package generation/hash. */
static hcu_bitmap_dispatch_status compose_source_get(hcu_bitmap_dispatch_context *ctx,
	const hcu_bitmap_binding *binding, uint32_t generation,
	hcu_bitmap_compose_source **out)
{
/* A chunk whose bytes were read but whose image the HUD cannot draw stays rejected for the map generation: left alone, the
 * request is re-issued every frame and each one is a disc read (a scope mask the shape check refused cost 90 ms a frame). */
static uint32_t s_hud_reject[16], s_hud_reject_count, s_hud_reject_gen;
static int hud_rejected(uint32_t chunk, uint32_t generation)
{
	uint32_t i;
	if (s_hud_reject_gen != generation) return 0;
	for (i = 0; i < s_hud_reject_count; i++) if (s_hud_reject[i] == chunk) return 1;
	return 0;
}
static void hud_reject(uint32_t chunk, uint32_t generation)
{
	if (s_hud_reject_gen != generation) { s_hud_reject_gen = generation; s_hud_reject_count = 0u; }
	if (hud_rejected(chunk, generation) || s_hud_reject_count >= 16u) return;
	s_hud_reject[s_hud_reject_count++] = chunk;
	printf("HALO_PS2_LOCAL hud-chunk-rejected chunk=%u\n", (unsigned)chunk);
}
#define HUD_REJECT_FORMAT() do { hud_reject(binding->chunk_id, expected_generation); return HCU_BITMAP_DISPATCH_E_FORMAT; } while (0)

#if defined(HALO_PS2_C3_LAG_TRACE) && HALO_PS2_C3_LAG_TRACE
/* A HUD chunk read on the frame path (a cache miss): printed for the first 64 reads of a run, then every 64th. */
static void hud_read_trace(const char *site, uint32_t chunk, uint32_t size)
{
	static uint32_t count;
	if (count < 64u || (count & 63u) == 0u)
		printf("HALO_PS2_LOCAL hud-read site=%s chunk=%u size=%u n=%u\n", site, (unsigned)chunk, (unsigned)size, (unsigned)count);
	count++;
}
#endif

	uint8_t *storage = (uint8_t *)ctx->source_storage;
	hcu_bitmap_compose_source *source = NULL;
	hcu_asset_chunk_view chunk;
	tex_section section;
	tex_info image;
	tex_mip_view mip;
	hcu_asset_profile_staged_stats stats;
	const uint8_t *clut;
	uint32_t i, clut_bytes, offset, read_begin, parse_begin;
	if (!ctx || !binding || !out || !storage || !ctx->profile ||
		ctx->source_storage_bytes < HCU_BITMAP_COMPOSE_RESERVED_BYTES ||
		binding->expected_profile_id != ctx->profile->profile_id)
		return HCU_BITMAP_DISPATCH_E_ARGUMENT;
	for (i = 0; i < HCU_BITMAP_COMPOSE_SOURCE_COUNT; ++i)
		if (compose_source_matches(&ctx->compose_sources[i], binding, generation)) {
			*out = &ctx->compose_sources[i]; ctx->counters.hits++; return HCU_BITMAP_DISPATCH_OK;
		}
	if (ctx->compose_cache_generation != generation) {
		memset(ctx->compose_sources, 0, sizeof(ctx->compose_sources));
		ctx->compose_cache_generation = generation;
		ctx->compose_source_cursor = 0;
	}
	if (hcu_asset_profile_lookup(ctx->profile, HCU_ASSET_CHUNK_MEDIA,
		binding->chunk_id, &chunk) != HCU_ASSET_PROFILE_OK || chunk.size > ctx->slot_stride)
		return HCU_BITMAP_DISPATCH_E_CHUNK;
	if (memcmp(chunk.sha256, binding->expected_chunk_sha256, 32))
		return HCU_BITMAP_DISPATCH_E_IDENTITY;
	read_begin = BITMAP_CYCLES();
	ctx->counters.misses++;
	ctx->counters.source_reads++;
	ctx->counters.source_bytes += chunk.size;
	ctx->counters.hash_checks++;
	if (hcu_asset_profile_read_chunk_staged_profiled(ctx->profile,
		HCU_ASSET_CHUNK_MEDIA, binding->chunk_id, ctx->staging_buffer,
		ctx->slot_stride, &stats) != HCU_ASSET_PROFILE_OK) {
		ctx->counters.source_cycles += BITMAP_CYCLES() - read_begin;
		return HCU_BITMAP_DISPATCH_E_CHUNK;
	}
	ctx->counters.read_calls += stats.payload_read_calls;
#if defined(HALO_PS2_C3_LAG_TRACE) && HALO_PS2_C3_LAG_TRACE
	hud_read_trace("compose-source", binding->chunk_id, chunk.size);
#endif
	ctx->counters.read_bytes += stats.payload_read_bytes;
	ctx->counters.read_cycles += stats.read_cycles;
	ctx->counters.hash_cycles += stats.hash_cycles;
	ctx->counters.source_cycles += BITMAP_CYCLES() - read_begin;
	parse_begin = BITMAP_CYCLES();
	ctx->counters.parses++;
	if (tex_open(&section, (const uint8_t *)ctx->staging_buffer, chunk.size) != TEX_OK ||
		binding->image_index >= section.texture_count) {
		ctx->counters.parse_cycles += BITMAP_CYCLES() - parse_begin;
		return HCU_BITMAP_DISPATCH_E_FORMAT;
	}
	image = tex_get(&section, binding->image_index);
	if (image.source_id != binding->expected_source_datum) {
		ctx->counters.parse_cycles += BITMAP_CYCLES() - parse_begin;
		return HCU_BITMAP_DISPATCH_E_IDENTITY;
	}
	if ((image.psm != GS_PSMT4 && image.psm != GS_PSMT8) ||
		!image.width || !image.height || image.width > 256u || image.height > 512u ||
		(image.height > 256u && image.width != 8u) ||
		!tex_mip(&section, &image, 0, &mip) || !(clut = tex_clut(&section, &image))) {
		ctx->counters.parse_cycles += BITMAP_CYCLES() - parse_begin;
		return HCU_BITMAP_DISPATCH_E_FORMAT;
	}
	clut_bytes = (uint32_t)image.clut_entries * 4u;
	if (!mip.pixels || !mip.bytes || clut_bytes != (uint32_t)image.clut_entries * 4u ||
		mip.bytes > HCU_BITMAP_COMPOSE_SOURCE_BYTES ||
		clut_bytes > HCU_BITMAP_COMPOSE_SOURCE_BYTES - mip.bytes) {
		ctx->counters.parse_cycles += BITMAP_CYCLES() - parse_begin;
		return HCU_BITMAP_DISPATCH_E_CAPACITY;
	}
	ctx->counters.parse_cycles += BITMAP_CYCLES() - parse_begin;
	i = ctx->compose_source_cursor++ % HCU_BITMAP_COMPOSE_SOURCE_COUNT;
	source = &ctx->compose_sources[i];
	memset(source, 0, sizeof(*source));
	offset = ctx->source_storage_bytes - HCU_BITMAP_COMPOSE_SOURCE_COUNT * HCU_BITMAP_COMPOSE_SOURCE_BYTES +
		i * HCU_BITMAP_COMPOSE_SOURCE_BYTES;
	memcpy(storage + offset, mip.pixels, mip.bytes);
	memcpy(storage + offset + mip.bytes, clut, clut_bytes);
	source->generation = generation;
	source->bitmap_output_datum = binding->bitmap_output_datum;
	source->bitmap_index = binding->bitmap_index;
	source->image_index = binding->image_index;
	source->chunk_id = binding->chunk_id;
	source->expected_source_datum = binding->expected_source_datum;
	source->expected_profile_id = binding->expected_profile_id;
	source->storage_offset = offset;
	source->index_bytes = mip.bytes;
	source->clut_bytes = clut_bytes;
	source->width = image.width;
	source->height = image.height;
	source->clut_entries = image.clut_entries;
	source->psm = image.psm;
	memcpy(source->chunk_sha256, binding->expected_chunk_sha256, 32);
	source->valid = 1;
	*out = source;
	return HCU_BITMAP_DISPATCH_OK;
}

static hcu_bitmap_dispatch_status dispatch_multiply_request(hcu_bitmap_dispatch_context *ctx,
	const halo_ps2_bitmap_request *request, hcu_bitmap_rect target, hcu_bitmap_lease *lease)
{
	const hcu_bitmap_binding *base_binding, *multiply_binding;
	hcu_bitmap_compose_source *base_source, *multiply_source;
	hud_effect_indexed_image base, multiply;
	hud_effect_map_transform base_transform, multiply_transform;
	hcu_bitmap_dispatch_status status;
	hcu_bitmap_source_slot *slot;
	tex_info output_image;
	chain_t upload_before, geometry_before;
	hcu_bitmap_quad_state_t state;
	hcu_bitmap_vertex_t vertices[4], placed[4];
	hcu_bitmap_blend_t blend;
	uint8_t *output;
	uint32_t output_offset, output_bytes, output_index_bytes, scratch_words, scratch_pages;
	uint32_t clut_words, tbp, tbw, cbp, i, slot_index, physical_slot, tex_w, tex_h;
	uint32_t pixel_w, pixel_h, transfer_h, tex_pages, page_first, pool_start, pool_end;
	uint32_t candidate, storage_bytes;
	uint8_t used_pages[512];
	uint8_t palette_entries;
	float x[4], y[4], u[4], v[4], min_x, max_x, min_y, max_y;
	float dx1, dy1, dx3, dy3, det, u_x, u_y, v_x, v_y, source_u0, source_v0;
	int32_t pixel_x0, pixel_x1, pixel_y0, pixel_y1;
	if (!ctx || !request || !lease || !request->has_multiply_map || request->has_meter ||
		request->multiply_slot >= HCU_BITMAP_COMPOSE_OUTPUT_REQUESTS || !ctx->bindings ||
		!ctx->profile || !ctx->cache || !ctx->slots || ctx->slot_count < HCU_BITMAP_COMPOSE_OUTPUT_COUNT ||
		!ctx->source_storage || ctx->source_storage_bytes < HCU_BITMAP_COMPOSE_RESERVED_BYTES ||
		!ctx->upload_chain || !ctx->geometry_chain || !ctx->staging_buffer ||
		request->multiply_bitmap_tag_index < 0 || request->multiply_bitmap_index >= 4096u ||
		request->bitmap_tag_index < 0 || request->bitmap_index >= 4096u ||
		request->multiply_scale_u <= 0.0f || request->multiply_scale_v <= 0.0f ||
		request->multiply_scale_u > 16.0f || request->multiply_scale_v > 16.0f ||
		!isfinite(request->multiply_offset_u) || !isfinite(request->multiply_offset_v) ||
		request->multiply_offset_u < -16.0f || request->multiply_offset_u > 16.0f ||
		request->multiply_offset_v < -16.0f || request->multiply_offset_v > 16.0f ||
		!blend_for(request->framebuffer_blend_function, &blend))
		return HCU_BITMAP_DISPATCH_E_UNSUPPORTED;
	if (request->generation != ctx->expected_generation) return HCU_BITMAP_DISPATCH_E_IDENTITY;
	base_binding = binding_find(ctx->bindings, ctx->binding_count,
		request->bitmap_tag_index, request->bitmap_index);
	multiply_binding = binding_find(ctx->bindings, ctx->binding_count,
		request->multiply_bitmap_tag_index, request->multiply_bitmap_index);
	if (!base_binding || !multiply_binding || base_binding->expected_profile_id != ctx->profile->profile_id ||
		multiply_binding->expected_profile_id != ctx->profile->profile_id)
		return HCU_BITMAP_DISPATCH_E_IDENTITY;
	status = compose_source_get(ctx, base_binding, request->generation, &base_source);
	if (status != HCU_BITMAP_DISPATCH_OK) return status;
	status = compose_source_get(ctx, multiply_binding, request->generation, &multiply_source);
	if (status != HCU_BITMAP_DISPATCH_OK) return status;
	base.indices = (const uint8_t *)ctx->source_storage + base_source->storage_offset;
	base.indices_bytes = base_source->index_bytes;
	base.clut_rgba32 = base.indices + base_source->index_bytes;
	base.width = base_source->width; base.height = base_source->height;
	base.clut_entries = base_source->clut_entries; base.psm = base_source->psm;
	multiply.indices = (const uint8_t *)ctx->source_storage + multiply_source->storage_offset;
	multiply.indices_bytes = multiply_source->index_bytes;
	multiply.clut_rgba32 = multiply.indices + multiply_source->index_bytes;
	multiply.width = multiply_source->width; multiply.height = multiply_source->height;
	multiply.clut_entries = multiply_source->clut_entries; multiply.psm = multiply_source->psm;
	memset(&base_transform, 0, sizeof(base_transform));
	base_transform.scale_u = base_transform.scale_v = 1.0f;
	base_transform.wrap_u = base_transform.wrap_v = request->bitmap_wrap ? 1u : 0u;
	base_transform.tint_r = base_transform.tint_g = base_transform.tint_b = base_transform.fade = 255u;
	memset(&multiply_transform, 0, sizeof(multiply_transform));
	multiply_transform.scale_u = request->multiply_scale_u;
	multiply_transform.scale_v = request->multiply_scale_v;
	multiply_transform.offset_u = request->multiply_offset_u;
	multiply_transform.offset_v = request->multiply_offset_v;
	multiply_transform.wrap_u = multiply_transform.wrap_v = request->multiply_wrap ? 1u : 0u;
	multiply_transform.tint_r = request->multiply_tint[0];
	multiply_transform.tint_g = request->multiply_tint[1];
	multiply_transform.tint_b = request->multiply_tint[2];
	multiply_transform.fade = request->multiply_tint[3];
	if (base.width > 256u || base.height > 512u || (base.height > 256u && base.width != 8u) ||
		multiply.width > 256u || multiply.height > 512u || (multiply.height > 256u && multiply.width != 8u) ||
		base_source->psm != GS_PSMT4 || multiply_source->psm != GS_PSMT4)
		return HCU_BITMAP_DISPATCH_E_UNSUPPORTED;
	min_x = min_y = 3.402823466e+38f; max_x = max_y = -3.402823466e+38f;
	for (i = 0; i < 4u; ++i) {
		x[i] = request->vertices[i].x; y[i] = request->vertices[i].y;
		u[i] = request->vertices[i].u; v[i] = request->vertices[i].v;
		if (!isfinite(x[i]) || !isfinite(y[i]) || !isfinite(u[i]) || !isfinite(v[i]) ||
			u[i] < 0.0f || u[i] > 1.0f || v[i] < 0.0f || v[i] > 1.0f)
			return HCU_BITMAP_DISPATCH_E_UNSUPPORTED;
		if (x[i] < min_x) min_x = x[i];
		if (x[i] > max_x) max_x = x[i];
		if (y[i] < min_y) min_y = y[i];
		if (y[i] > max_y) max_y = y[i];
	}
	/* CE's rotated HUD rectangles remain affine parallelograms. Reject other
	 * projective/irregular geometry rather than composing a different mapping. */
	if (fabsf(x[2] - (x[1] + x[3] - x[0])) > 0.02f ||
		fabsf(y[2] - (y[1] + y[3] - y[0])) > 0.02f ||
		fabsf(u[2] - (u[1] + u[3] - u[0])) > 0.002f ||
		fabsf(v[2] - (v[1] + v[3] - v[0])) > 0.002f)
		return HCU_BITMAP_DISPATCH_E_UNSUPPORTED;
	pixel_x0 = (int32_t)ceilf(min_x - 0.5f); pixel_x1 = (int32_t)ceilf(max_x - 0.5f);
	pixel_y0 = (int32_t)ceilf(min_y - 0.5f); pixel_y1 = (int32_t)ceilf(max_y - 0.5f);
	if (pixel_x1 <= pixel_x0 || pixel_y1 <= pixel_y0) return HCU_BITMAP_DISPATCH_E_UNSUPPORTED;
	pixel_w = (uint32_t)(pixel_x1 - pixel_x0); pixel_h = (uint32_t)(pixel_y1 - pixel_y0);
	/* The only admitted multiply-map profile is the retail sniper's 8-pixel-wide
	 * angle-ticks strip. Keep the fixed output arena sized to that measured shape;
	 * other geometries fail closed without consuming the normal bitmap pool. */
	if (pixel_w > 8u || pixel_h > 512u) return HCU_BITMAP_DISPATCH_E_UNSUPPORTED;
	tex_w = tex_h = 8u;
	while (tex_w < pixel_w) tex_w <<= 1;
	while (tex_h < pixel_h) tex_h <<= 1;
	transfer_h = (pixel_h + 3u) & ~3u;
	if (transfer_h > tex_h) return HCU_BITMAP_DISPATCH_E_UNSUPPORTED;
	dx1 = x[1] - x[0]; dy1 = y[1] - y[0]; dx3 = x[3] - x[0]; dy3 = y[3] - y[0];
	det = dx1 * dy3 - dy1 * dx3;
	if (!isfinite(det) || fabsf(det) < 0.0001f) return HCU_BITMAP_DISPATCH_E_UNSUPPORTED;
	u_x = ((u[1] - u[0]) * dy3 - (u[3] - u[0]) * dy1) / det;
	u_y = (-(u[1] - u[0]) * dx3 + (u[3] - u[0]) * dx1) / det;
	v_x = ((v[1] - v[0]) * dy3 - (v[3] - v[0]) * dy1) / det;
	v_y = (-(v[1] - v[0]) * dx3 + (v[3] - v[0]) * dx1) / det;
	source_u0 = u[0] + u_x * ((float)pixel_x0 + 0.5f - x[0]) + u_y * ((float)pixel_y0 + 0.5f - y[0]);
	source_v0 = v[0] + v_x * ((float)pixel_x0 + 0.5f - x[0]) + v_y * ((float)pixel_y0 + 0.5f - y[0]);
	for (physical_slot = 0; physical_slot < HCU_BITMAP_COMPOSE_OUTPUT_COUNT; ++physical_slot) {
		slot_index = ctx->slot_count - HCU_BITMAP_COMPOSE_OUTPUT_COUNT + physical_slot;
		if (!ctx->slots[slot_index].valid && !ctx->slots[slot_index].readers) break;
	}
	if (physical_slot == HCU_BITMAP_COMPOSE_OUTPUT_COUNT) return HCU_BITMAP_DISPATCH_E_BUSY;
	slot = &ctx->slots[slot_index];
	pool_start = ctx->source_storage_bytes - HCU_BITMAP_COMPOSE_RESERVED_BYTES;
	pool_end = pool_start + HCU_BITMAP_COMPOSE_OUTPUT_POOL_BYTES;
	output_index_bytes = tex_w * transfer_h / 2u;
	output_bytes = output_index_bytes + 64u;
	if (output_bytes < output_index_bytes) return HCU_BITMAP_DISPATCH_E_CAPACITY;
	candidate = pool_start;
	for (;;) {
		int overlap = 0;
		for (i = 0; i < HCU_BITMAP_COMPOSE_OUTPUT_COUNT; ++i) {
			hcu_bitmap_source_slot *existing = &ctx->slots[ctx->slot_count - HCU_BITMAP_COMPOSE_OUTPUT_COUNT + i];
			uint32_t existing_end;
			if (!existing->valid || existing->cache_key != UINT16_MAX || !existing->reserved8) continue;
			existing_end = existing->storage_offset + existing->storage_bytes;
			if (candidate < existing_end && candidate + output_bytes > existing->storage_offset) {
				candidate = (existing_end + 15u) & ~15u; overlap = 1; break;
			}
		}
		if (!overlap) break;
	}
	if (candidate > pool_end || output_bytes > pool_end - candidate)
		return HCU_BITMAP_DISPATCH_E_CAPACITY;
	output_offset = candidate; storage_bytes = output_bytes;
	output = (uint8_t *)ctx->source_storage + output_offset;
	if (hud_effect_compose_multiply_indexed_psmt4_affine(&base, &multiply, &base_transform,
		&multiply_transform, request->point_sampled, (uint16_t)tex_w, (uint16_t)transfer_h,
		source_u0, source_v0, u_x, u_y, v_x, v_y,
		output, output_index_bytes, output + output_index_bytes, 64u, &palette_entries) != 0 ||
		!palette_entries || palette_entries > 16u)
		return HCU_BITMAP_DISPATCH_E_UNSUPPORTED;
	if (!bsp_render_hud_effect_texture_base_words || !bsp_render_hud_effect_texture_page_count ||
		!bsp_render_hud_effect_clut_base_words ||
		bsp_render_hud_effect_texture_base_words(&scratch_words) != 0 ||
		bsp_render_hud_effect_texture_page_count(&scratch_pages) != 0 ||
		bsp_render_hud_effect_clut_base_words(&clut_words) != 0)
		return HCU_BITMAP_DISPATCH_E_UNSUPPORTED;
	tex_pages = pages_for(tex_w, tex_h, GS_PSMT4);
	if (!tex_pages || scratch_pages > sizeof(used_pages) || !scratch_pages || tex_pages > scratch_pages)
		return HCU_BITMAP_DISPATCH_E_CAPACITY;
	memset(used_pages, 0, sizeof(used_pages));
	for (i = 0; i < HCU_BITMAP_COMPOSE_OUTPUT_COUNT; ++i) {
		hcu_bitmap_source_slot *existing = &ctx->slots[ctx->slot_count - HCU_BITMAP_COMPOSE_OUTPUT_COUNT + i];
		uint32_t p;
		if (!existing->valid || existing->cache_key != UINT16_MAX || !existing->reserved8) continue;
		if (existing->gs_page_first > scratch_pages || existing->gs_page_count > scratch_pages - existing->gs_page_first)
			return HCU_BITMAP_DISPATCH_E_CAPACITY;
		for (p = 0; p < existing->gs_page_count; ++p) used_pages[existing->gs_page_first + p] = 1u;
	}
	for (page_first = 0; page_first + tex_pages <= scratch_pages; ++page_first) {
		for (i = 0; i < tex_pages && !used_pages[page_first + i]; ++i) {}
		if (i == tex_pages) break;
	}
	if (page_first + tex_pages > scratch_pages) return HCU_BITMAP_DISPATCH_E_CAPACITY;
	tbp = scratch_words / 64u + page_first * 32u;
	tbw = (tex_w + 63u) / 64u;
	cbp = clut_words / 64u + physical_slot * 4u;
	if (tbp >= 0x4000u || tbp + tex_pages * 32u > 0x4000u || cbp + 3u >= 0x4000u)
		return HCU_BITMAP_DISPATCH_E_CAPACITY;
	upload_before = *ctx->upload_chain;
	geometry_before = *ctx->geometry_chain;
	if (gs_upload_pair(ctx->upload_chain, output, output_index_bytes, tbp, tbw,
		GS_PSMT4, tex_w, transfer_h, output + output_index_bytes, 64u, cbp, 8u, 2u))
		goto multiply_rollback;
	memset(&output_image, 0, sizeof(output_image));
	output_image.width = (uint16_t)tex_w; output_image.height = (uint16_t)tex_h; output_image.psm = GS_PSMT4;
	memset(&state, 0, sizeof(state));
	state.tex0 = GS_TEX0(tbp, tbw, GS_PSMT4, (uint32_t)log2_exact(tex_w),
		(uint32_t)log2_exact(tex_h), 1, 0, cbp, GS_PSMCT32, 0, 0, 1);
	state.clamp = GS_CLAMP(1, 1, 0, tex_w - 1u, 0, tex_h - 1u);
	state.screen_w = ctx->screen_w; state.screen_h = ctx->screen_h;
	state.z = 0xFFFFFFu; state.blend = blend; state.texture_layers = 1;
	state.point_sampled = 1; /* the composed texels already match the native destination grid */
	for (i = 0; i < 4; ++i) {
		vertices[i].x = request->vertices[i].x; vertices[i].y = request->vertices[i].y;
		vertices[i].u = (vertices[i].x - min_x) * ((float)pixel_w - 1.0f) /
			((max_x - min_x) * ((float)tex_w - 1.0f));
		vertices[i].v = (vertices[i].y - min_y) * ((float)pixel_h - 1.0f) /
			((max_y - min_y) * ((float)tex_h - 1.0f));
		vertices[i].argb = request->vertices[i].color;
	}
	if (hcu_bitmap_quad_place(&state, &target, vertices, placed) != 0) goto multiply_rollback;
	if (hcu_bitmap_quad_emit_validated(ctx->geometry_chain, &output_image, &state, placed) != HCU_BITMAP_QUAD_OK)
		goto multiply_rollback;
	memset(slot, 0, sizeof(*slot));
	slot->cache_key = UINT16_MAX; slot->storage_offset = output_offset;
	slot->storage_bytes = storage_bytes; slot->readers = 1; slot->valid = 1; slot->reserved8 = 1;
	slot->gs_page_first = (uint16_t)page_first; slot->gs_page_count = (uint16_t)tex_pages;
	slot->compose_clut_slot = (uint16_t)physical_slot;
	lease->slot = (uint16_t)slot_index; lease->cache_key = UINT16_MAX;
	lease->generation = request->generation; lease->active = 1;
	return HCU_BITMAP_DISPATCH_OK;

multiply_rollback:
	*ctx->upload_chain = upload_before;
	*ctx->geometry_chain = geometry_before;
	return HCU_BITMAP_DISPATCH_E_CAPACITY;
}

/* A run of text (halo_ps2_text_glyph records). The characters are the font tag's 8-bit alpha
 * bitmaps; the run is composed into one 8-bit indexed texture on the EE, uploaded to the HUD's
 * scratch pages, and drawn as one quad. Each texel holds two 4-bit coverages: the text (low
 * nibble) and its drop shadow (high nibble). The palette turns every pair into the text colour
 * over a black shadow, so a string costs one texture, one palette and one quad. The output
 * pool, slots and scratch pages are the ones the multiply overlay uses, released by the same
 * fenced leases. */
#define HCU_TEXT_MAX_W 512u
#define HCU_TEXT_MAX_H 64u
#define HCU_TEXT_MAX_TEXELS 16384u

static uint32_t text_pow2_at_least(uint32_t n, uint32_t minimum)
{
	uint32_t p = minimum;
	while (p < n) p <<= 1;
	return p;
}

static hcu_bitmap_dispatch_status dispatch_text_run(hcu_bitmap_dispatch_context *ctx,
	const halo_ps2_bitmap_request_queue *queue, const halo_ps2_bitmap_request *request,
	hcu_bitmap_rect target, hcu_bitmap_lease *lease)
{
	hcu_bitmap_source_slot *slot;
	tex_info output_image;
	chain_t upload_before, geometry_before;
	hcu_bitmap_quad_state_t state;
	hcu_bitmap_vertex_t vertices[4], placed[4];
	hcu_bitmap_blend_t blend;
	uint8_t *output, *clut;
	uint32_t first, count, i, g, row, col, pool_start, pool_end, candidate, output_bytes, index_bytes;
	uint32_t scratch_words, scratch_pages, clut_words, tex_pages, page_first, tbp, tbw, cbp;
	uint32_t slot_index, physical_slot, tex_w, tex_h, text_argb, fade, shadow_on;
	int32_t min_x, min_y, max_x, max_y, run_w, run_h;
	uint8_t used_pages[512];
	float scale, ox, oy, qx0, qy0, qx1, qy1;
	if (!ctx || !queue || !request || !lease || !request->text_run || !ctx->cache || !ctx->slots ||
		ctx->slot_count < HCU_BITMAP_COMPOSE_OUTPUT_COUNT || !ctx->source_storage ||
		ctx->source_storage_bytes < HCU_BITMAP_COMPOSE_RESERVED_BYTES ||
		!ctx->upload_chain || !ctx->geometry_chain || !blend_for(request->framebuffer_blend_function, &blend))
		return HCU_BITMAP_DISPATCH_E_UNSUPPORTED;
	if (request->generation != ctx->expected_generation) return HCU_BITMAP_DISPATCH_E_IDENTITY;
	first = request->text_glyph_first; count = request->text_glyph_count;
	if (!count || first + count > queue->text_glyph_count || first + count > HALO_PS2_TEXT_GLYPH_CAPACITY)
		return HCU_BITMAP_DISPATCH_E_UNSUPPORTED;
	scale = request->text_scale; ox = request->text_origin_x; oy = request->text_origin_y;
	if (!(scale > 0.0f && scale <= 8.0f) || !isfinite(ox) || !isfinite(oy)) return HCU_BITMAP_DISPATCH_E_UNSUPPORTED;
	text_argb = request->vertices[0].color;
	shadow_on = (request->vertices[1].color >> 24) != 0u;
	fade = text_argb >> 24;
	if (!fade) return HCU_BITMAP_DISPATCH_E_UNSUPPORTED;
	min_x = min_y = 0x7FFFFFFF; max_x = max_y = -0x7FFFFFFF;
	for (g = first; g < first + count; ++g) {
		const halo_ps2_text_glyph *gl = &queue->text_glyphs[g];
		if (!gl->pixels || gl->w <= 0 || gl->h <= 0) return HCU_BITMAP_DISPATCH_E_UNSUPPORTED;
		if (gl->x < min_x) min_x = gl->x;
		if (gl->y < min_y) min_y = gl->y;
		if (gl->x + gl->w + 1 > max_x) max_x = gl->x + gl->w + 1;   /* the shadow sits one pixel right and down */
		if (gl->y + gl->h + 1 > max_y) max_y = gl->y + gl->h + 1;
	}
	run_w = max_x - min_x; run_h = max_y - min_y;
	if (run_w <= 0 || run_h <= 0 || run_w > (int32_t)HCU_TEXT_MAX_W || run_h > (int32_t)HCU_TEXT_MAX_H)
		return HCU_BITMAP_DISPATCH_E_UNSUPPORTED;
	tex_w = text_pow2_at_least((uint32_t)run_w, 16u);
	tex_h = text_pow2_at_least((uint32_t)run_h, 8u);
	if (tex_w > HCU_TEXT_MAX_W || tex_w * tex_h > HCU_TEXT_MAX_TEXELS) return HCU_BITMAP_DISPATCH_E_UNSUPPORTED;
	for (physical_slot = 0; physical_slot < HCU_BITMAP_COMPOSE_OUTPUT_COUNT; ++physical_slot) {
		slot_index = ctx->slot_count - HCU_BITMAP_COMPOSE_OUTPUT_COUNT + physical_slot;
		if (!ctx->slots[slot_index].valid && !ctx->slots[slot_index].readers) break;
	}
	if (physical_slot == HCU_BITMAP_COMPOSE_OUTPUT_COUNT) return HCU_BITMAP_DISPATCH_E_BUSY;
	slot = &ctx->slots[slot_index];
	pool_start = ctx->source_storage_bytes - HCU_BITMAP_COMPOSE_RESERVED_BYTES;
	pool_end = pool_start + HCU_BITMAP_COMPOSE_OUTPUT_POOL_BYTES;
	index_bytes = tex_w * tex_h;
	output_bytes = index_bytes + 1024u;
	candidate = pool_start;
	for (;;) {
		int overlap = 0;
		for (i = 0; i < HCU_BITMAP_COMPOSE_OUTPUT_COUNT; ++i) {
			hcu_bitmap_source_slot *existing = &ctx->slots[ctx->slot_count - HCU_BITMAP_COMPOSE_OUTPUT_COUNT + i];
			uint32_t existing_end;
			if (!existing->valid || existing->cache_key != UINT16_MAX || !existing->reserved8) continue;
			existing_end = existing->storage_offset + existing->storage_bytes;
			if (candidate < existing_end && candidate + output_bytes > existing->storage_offset) {
				candidate = (existing_end + 15u) & ~15u; overlap = 1; break;
			}
		}
		if (!overlap) break;
	}
	if (candidate > pool_end || output_bytes > pool_end - candidate) return HCU_BITMAP_DISPATCH_E_CAPACITY;
	if (!bsp_render_hud_effect_texture_base_words || !bsp_render_hud_effect_texture_page_count ||
		!bsp_render_hud_effect_clut_base_words ||
		bsp_render_hud_effect_texture_base_words(&scratch_words) != 0 ||
		bsp_render_hud_effect_texture_page_count(&scratch_pages) != 0 ||
		bsp_render_hud_effect_clut_base_words(&clut_words) != 0)
		return HCU_BITMAP_DISPATCH_E_UNSUPPORTED;
	tex_pages = pages_for(tex_w, tex_h, GS_PSMT8);
	if (!tex_pages || scratch_pages > sizeof(used_pages) || !scratch_pages || tex_pages > scratch_pages)
		return HCU_BITMAP_DISPATCH_E_CAPACITY;
	memset(used_pages, 0, sizeof(used_pages));
	for (i = 0; i < HCU_BITMAP_COMPOSE_OUTPUT_COUNT; ++i) {
		hcu_bitmap_source_slot *existing = &ctx->slots[ctx->slot_count - HCU_BITMAP_COMPOSE_OUTPUT_COUNT + i];
		uint32_t p;
		if (!existing->valid || existing->cache_key != UINT16_MAX || !existing->reserved8) continue;
		if (existing->gs_page_first > scratch_pages || existing->gs_page_count > scratch_pages - existing->gs_page_first)
			return HCU_BITMAP_DISPATCH_E_CAPACITY;
		for (p = 0; p < existing->gs_page_count; ++p) used_pages[existing->gs_page_first + p] = 1u;
	}
	for (page_first = 0; page_first + tex_pages <= scratch_pages; ++page_first) {
		for (i = 0; i < tex_pages && !used_pages[page_first + i]; ++i) {}
		if (i == tex_pages) break;
	}
	if (page_first + tex_pages > scratch_pages) return HCU_BITMAP_DISPATCH_E_CAPACITY;
	tbp = scratch_words / 64u + page_first * 32u;
	tbw = (tex_w + 63u) / 64u;
	cbp = clut_words / 64u + physical_slot * 4u;
	if (tbp >= 0x4000u || tbp + tex_pages * 32u > 0x4000u || cbp + 3u >= 0x4000u)
		return HCU_BITMAP_DISPATCH_E_CAPACITY;
	/* Compose: the text in the low nibble, its shadow (one pixel right and down) in the high one. */
	output = (uint8_t *)ctx->source_storage + candidate;
	clut = output + index_bytes;
	memset(output, 0, index_bytes);
	for (g = first; g < first + count; ++g) {
		const halo_ps2_text_glyph *gl = &queue->text_glyphs[g];
		for (row = 0; row < (uint32_t)gl->h; ++row) {
			const uint8_t *src = gl->pixels + (uint32_t)(gl->src_y + (int32_t)row) * (uint32_t)gl->src_stride + (uint32_t)gl->src_x;
			uint32_t dy = (uint32_t)(gl->y + (int32_t)row - min_y);
			for (col = 0; col < (uint32_t)gl->w; ++col) {
				uint32_t cov = (uint32_t)src[col] >> 4;
				uint32_t dx = (uint32_t)(gl->x + (int32_t)col - min_x);
				uint8_t *t, *sh;
				if (!cov) continue;
				t = output + dy * tex_w + dx;
				if ((*t & 15u) < cov) *t = (uint8_t)((*t & 0xF0u) | cov);
				if (shadow_on) {
					sh = output + (dy + 1u) * tex_w + dx + 1u;
					if ((uint32_t)(*sh >> 4) < cov) *sh = (uint8_t)((*sh & 15u) | (cov << 4));
				}
			}
		}
	}
	/* Palette (CSM1 order: the entries of blocks 8-15 and 16-23 swap). GS alpha 128 is opaque. */
	{
		uint32_t r = (text_argb >> 16) & 255u, gr = (text_argb >> 8) & 255u, b = text_argb & 255u;
		for (i = 0; i < 256u; ++i) {
			float sa = (float)(i >> 4) / 15.0f, ta = (float)(i & 15u) / 15.0f;
			float a = ta + sa * (1.0f - ta);
			uint32_t pos = (i & 0xE7u) | ((i & 0x08u) << 1) | ((i & 0x10u) >> 1);
			uint8_t *e = clut + pos * 4u;
			float k = a > 0.0f ? ta / a : 0.0f;
			e[0] = (uint8_t)((float)r * k + 0.5f); e[1] = (uint8_t)((float)gr * k + 0.5f);
			e[2] = (uint8_t)((float)b * k + 0.5f); e[3] = (uint8_t)(a * 128.0f + 0.5f);
		}
	}
	upload_before = *ctx->upload_chain;
	geometry_before = *ctx->geometry_chain;
	if (gs_upload_pair(ctx->upload_chain, output, index_bytes, tbp, tbw, GS_PSMT8, tex_w, tex_h,
		clut, 1024u, cbp, 16u, 16u))
		goto text_rollback;
	memset(&output_image, 0, sizeof(output_image));
	output_image.width = (uint16_t)tex_w; output_image.height = (uint16_t)tex_h; output_image.psm = GS_PSMT8;
	memset(&state, 0, sizeof(state));
	state.tex0 = GS_TEX0(tbp, tbw, GS_PSMT8, (uint32_t)log2_exact(tex_w), (uint32_t)log2_exact(tex_h),
		1, 0, cbp, GS_PSMCT32, 0, 0, 1);
	state.clamp = GS_CLAMP(1, 1, 0, tex_w - 1u, 0, tex_h - 1u);
	state.screen_w = ctx->screen_w; state.screen_h = ctx->screen_h;
	state.z = 0xFFFFFFu; state.blend = blend; state.texture_layers = 1;
	state.point_sampled = scale == 1.0f ? 1u : 0u;
	qx0 = ox + ((float)min_x - ox) * scale; qy0 = oy + ((float)min_y - oy) * scale;
	qx1 = ox + ((float)(min_x + run_w) - ox) * scale; qy1 = oy + ((float)(min_y + run_h) - oy) * scale;
	vertices[0].x = qx0; vertices[0].y = qy0; vertices[0].u = 0.0f; vertices[0].v = 0.0f;
	vertices[1].x = qx1; vertices[1].y = qy0; vertices[1].u = (float)run_w / (float)tex_w; vertices[1].v = 0.0f;
	vertices[2].x = qx1; vertices[2].y = qy1; vertices[2].u = (float)run_w / (float)tex_w; vertices[2].v = (float)run_h / (float)tex_h;
	vertices[3].x = qx0; vertices[3].y = qy1; vertices[3].u = 0.0f; vertices[3].v = (float)run_h / (float)tex_h;
	for (i = 0; i < 4; ++i) vertices[i].argb = (fade << 24) | 0x00FFFFFFu;
	if (hcu_bitmap_quad_place(&state, &target, vertices, placed) != 0) goto text_rollback;
	if (hcu_bitmap_quad_emit_validated(ctx->geometry_chain, &output_image, &state, placed) != HCU_BITMAP_QUAD_OK)
		goto text_rollback;
	memset(slot, 0, sizeof(*slot));
	slot->cache_key = UINT16_MAX; slot->storage_offset = candidate;
	slot->storage_bytes = output_bytes; slot->readers = 1; slot->valid = 1; slot->reserved8 = 1;
	slot->gs_page_first = (uint16_t)page_first; slot->gs_page_count = (uint16_t)tex_pages;
	slot->compose_clut_slot = (uint16_t)physical_slot;
	lease->slot = (uint16_t)slot_index; lease->cache_key = UINT16_MAX;
	lease->generation = request->generation; lease->active = 1;
	return HCU_BITMAP_DISPATCH_OK;

text_rollback:
	*ctx->upload_chain = upload_before;
	*ctx->geometry_chain = geometry_before;
	return HCU_BITMAP_DISPATCH_E_CAPACITY;
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
	hcu_bitmap_rect target, hcu_bitmap_lease *lease, int prepare_only,
	uint64_t *prepared_tex0, uint64_t *prepared_clamp)
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
	uint32_t retained_bytes = 0;
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
	uint32_t source_storage_limit = source_storage_bytes;
	uint32_t slot_limit = slot_count;

	if (!request || !bindings || !profile || !cache || !journal || !cache_readers || !slots ||
		!binding_count || !slot_count || !source_storage || !slot_stride || !staging_buffer || !upload_chain ||
		!geometry_chain || !lease || lease->active || !screen_w || !screen_h ||
		(prepare_only && (!request->screen_effect_mask || !prepared_tex0 || !prepared_clamp)) ||
		(!prepare_only && (target.x < 0 || target.y < 0 || target.w <= 0 || target.h <= 0 ||
		 target.x + target.w > screen_w || target.y + target.h > screen_h)) ||
		slot_count > UINT16_MAX || cache_reader_count < cache->max_keys ||
		cache_reader_count > TC_MAX_KEYS || !source_storage_bytes ||
		!slot_stride || slot_stride > staging_buffer_bytes ||
		(slot_stride & 15u) ||
		((uintptr_t)source_storage & 15u))
		return HCU_BITMAP_DISPATCH_E_ARGUMENT;
	if (context && source_storage_limit >= HCU_BITMAP_COMPOSE_RESERVED_BYTES)
	{
		source_storage_limit -= HCU_BITMAP_COMPOSE_RESERVED_BYTES;
		if (slot_limit >= HCU_BITMAP_COMPOSE_OUTPUT_COUNT)
			slot_limit -= HCU_BITMAP_COMPOSE_OUTPUT_COUNT;
	}
	if (request->has_multiply_map) return HCU_BITMAP_DISPATCH_E_UNSUPPORTED;
	if (request->generation != expected_generation)
		return HCU_BITMAP_DISPATCH_E_IDENTITY;
	hudc_prewarm(profile, bindings, binding_count, expected_generation, staging_buffer, staging_buffer_bytes, slot_stride);
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
	/* If verified metadata survived a prior TC_DEFER, ask the bounded cache
	 * whether admission is possible before touching the backing package again.
	 * A successful probe is rolled back; the normal path below still performs
	 * the integrity checked read needed to queue an actual upload. */
	if (descriptor && !cache->map[binding->cache_key]) {
		uint32_t probe_pages = pages_for(descriptor->width, descriptor->height, descriptor->psm);
		tc_result probe_result;
		const tc_entry *probe_entry;
		if (!probe_pages || probe_pages > cache->total_pages) return HCU_BITMAP_DISPATCH_E_CAPACITY;
		tc_journal_begin(cache, journal);
#if defined(HALO_PS2_C3_BITMAP_DEFER_PROBE) && HALO_PS2_C3_BITMAP_DEFER_PROBE
		cache->hud_priority = 1;
		probe_result = tc_acquire_j_probe(cache, journal, binding->cache_key, probe_pages,
			descriptor->mip_bytes + descriptor->clut_bytes, &probe_entry,
			HCU_BITMAP_DEFER_PROBE_PTR, HCU_BITMAP_PROBE_HUD);
#else
		cache->hud_priority = 1;
		probe_result = tc_acquire_j(cache, journal, binding->cache_key, probe_pages,
			descriptor->mip_bytes + descriptor->clut_bytes, &probe_entry);
#endif
		cache->hud_priority = 0;
		tc_journal_rollback(cache, journal);
		if (probe_result == TC_DEFER) {
			return HCU_BITMAP_DISPATCH_E_DEFERRED;
		}
		if (probe_result == TC_FULL) return HCU_BITMAP_DISPATCH_E_CAPACITY;
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
		image.flags = descriptor->flags;
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
		if (hud_rejected(binding->chunk_id, expected_generation)) return HCU_BITMAP_DISPATCH_E_FORMAT;
			observed_profile.reader_context = &probe;
			read_profile = &observed_profile;
		}
		if (hcu_asset_profile_lookup(read_profile, HCU_ASSET_CHUNK_MEDIA,
			binding->chunk_id, &chunk_view) != HCU_ASSET_PROFILE_OK || chunk_view.size > slot_stride)
			return HCU_BITMAP_DISPATCH_E_CHUNK;
		if (memcmp(chunk_view.sha256, binding->expected_chunk_sha256, 32))
			return HCU_BITMAP_DISPATCH_E_IDENTITY;
		/* A HUD bitmap that is not in VRAM (first draw after a weapon change, or evicted) would otherwise do a
		 * synchronous optical read here, 40-400 ms on the frame path. Start the read in the background and
		 * defer the request: CE re-issues it next frame and the read becomes a memcpy once the transfer lands. */
		if (context && resident_mode && !g_hcu_bitmap_prefetch_off &&
			hcu_asset_profile_range_ready(profile, HCU_ASSET_CHUNK_MEDIA, binding->chunk_id, 0u,
				chunk_view.size) == 0) {
			/* The background transfer may never land (another read owns the single read-ahead slot), and a HUD
			 * bitmap deferred forever is a missing radar, ammo count and crosshair. Defer a chunk for up to 20
			 * frames, then take the blocking read like before. */
			static uint32_t deferred_chunk[16];
			static uint8_t deferred_count[16];
			uint32_t slot = binding->chunk_id & 15u;
			if (deferred_chunk[slot] != binding->chunk_id) { deferred_chunk[slot] = binding->chunk_id; deferred_count[slot] = 0u; }
			if (deferred_count[slot] < 20u) {
				deferred_count[slot]++;
				context->counters.misses--; /* counted again when the retry reads */
				return HCU_BITMAP_DISPATCH_E_DEFERRED;
			}
			deferred_chunk[slot] = 0xFFFFFFFFu;
		}
		raw = (uint8_t *)staging_buffer;
		{
			const int hit = hudc_find(binding->chunk_id, chunk_view.size, chunk_view.sha256);
			if (hit >= 0) {
				memcpy(raw, s_hudc_mem + s_hudc[hit].off, chunk_view.size);
				s_hudc[hit].hits++;
				s_hudc_hits++;
				goto have_raw;
			}
		}
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
#if defined(HALO_PS2_C3_LAG_TRACE) && HALO_PS2_C3_LAG_TRACE
		hud_read_trace(request->screen_effect_mask ? "dispatch-mask" : "dispatch", binding->chunk_id, chunk_view.size);
#endif
		} else {
			int result = hcu_asset_profile_read_chunk(read_profile, HCU_ASSET_CHUNK_MEDIA,
				binding->chunk_id, raw, slot_stride);
			if (context) context->counters.source_cycles += BITMAP_CYCLES() - source_begin;
			if (result != HCU_ASSET_PROFILE_OK) return HCU_BITMAP_DISPATCH_E_CHUNK;
		}
		printf("HALO_PS2_LOCAL hud-chunk-miss id=%u size=%u cached=%u/%u\n", (unsigned)binding->chunk_id,
			(unsigned)chunk_view.size, (unsigned)s_hudc_used, (unsigned)s_hudc_cap);
		hudc_store(binding->chunk_id, chunk_view.size, chunk_view.sha256, raw);
		{ const int k = hudc_find(binding->chunk_id, chunk_view.size, chunk_view.sha256); if (k >= 0) s_hudc[k].hits = 1u; }
have_raw:
		read_bytes = chunk_view.size;
		parse_begin = BITMAP_CYCLES();
		if (context) context->counters.parses++;
		if (tex_open(&section, raw, read_bytes) != TEX_OK || binding->image_index >= section.texture_count)
			HUD_REJECT_FORMAT();
		image = tex_get(&section, binding->image_index);
		if (image.source_id != binding->expected_source_datum)
			return HCU_BITMAP_DISPATCH_E_IDENTITY;
		if ((image.psm != GS_PSMT8 && image.psm != GS_PSMT4) || !image.width || !image.height ||
			(image.width > 256u && !request->screen_effect_mask) || image.height > 256u ||
			image.width > 512u || log2_exact(image.width) < 0 ||
			log2_exact(image.height) < 0 || !tex_mip(&section, &image, 0, &mip))
			HUD_REJECT_FORMAT();
		clut = tex_clut(&section, &image);
		clut_bytes = (uint32_t)image.clut_entries * 4u;
		if (!clut || !clut_bytes || (mip.bytes & 15u) || (clut_bytes & 15u))
			HUD_REJECT_FORMAT();
		if (image.width > 256u && !screen_effect_mask_shape(request, &image, mip.bytes, clut_bytes))
			HUD_REJECT_FORMAT();
		if (context) context->counters.parse_cycles += BITMAP_CYCLES() - parse_begin;
	}
	if ((image.psm != GS_PSMT8 && image.psm != GS_PSMT4) ||
		!image.width || !image.height || (image.width > 256u && !request->screen_effect_mask) ||
		image.width > 512u || image.height > 256u ||
		log2_exact(image.width) < 0 || log2_exact(image.height) < 0 ||
		!mip.bytes || (mip.bytes & 15u) || !clut_bytes || (clut_bytes & 15u) ||
		clut_bytes != (uint32_t)image.clut_entries * 4u)
		return HCU_BITMAP_DISPATCH_E_FORMAT;
	if (request->screen_effect_mask &&
		!screen_effect_mask_shape(request, &image, mip.bytes, clut_bytes))
		return HCU_BITMAP_DISPATCH_E_FORMAT;
	upload_source = !cache->map[binding->cache_key];
	if (upload_source) {
		for (slot_index = 0; slot_index < slot_limit && slots[slot_index].valid; slot_index++) {}
		if (slot_index == slot_limit) return HCU_BITMAP_DISPATCH_E_CAPACITY;
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
	/* Publish only after chunk hash, TEXS parse, source datum and image shape
	 * have all passed. This descriptor contains no source pointers or pixels.
	 * It is recorded before admission so a TC_DEFER leaves verified metadata
	 * for the next frame's probe, which then skips the package read. */
	if (!resident_hit && resident_mode && (descriptor || empty_descriptor)) {
		hcu_bitmap_resident_descriptor *d = descriptor ? descriptor : empty_descriptor;
		memset(d, 0, sizeof(*d));
		d->bitmap_output_datum = binding->bitmap_output_datum;
		d->bitmap_index = binding->bitmap_index; d->image_index = binding->image_index;
		d->cache_key = binding->cache_key; d->chunk_id = binding->chunk_id;
		d->expected_source_datum = binding->expected_source_datum;
		d->profile_id = binding->expected_profile_id; d->generation = expected_generation;
		d->width = image.width; d->height = image.height; d->psm = image.psm;
		d->clut_entries = image.clut_entries; d->flags = image.flags; d->mip_bytes = mip.bytes; d->clut_bytes = clut_bytes;
		d->source_offset = image.pixel_offset;
		memcpy(d->chunk_sha256, binding->expected_chunk_sha256, 32);
		d->valid = 1;
	}

	/* Protect each outstanding source/GPU lease from tc's LRU eviction policy. */
	/* C3.7/bounded transaction: the journal records only what this request mutates (no whole-table copy).
	 * The reader-batch touch of leased entries runs once per batch before the first request. */
	tc_journal_begin(cache, journal);
	upload_before = *upload_chain;
	geometry_before = *geometry_chain;
#if defined(HALO_PS2_C3_BITMAP_DEFER_PROBE) && HALO_PS2_C3_BITMAP_DEFER_PROBE
	cache->hud_priority = 1;
	acquired = tc_acquire_j_probe(cache, journal, binding->cache_key, pages,
		upload_source ? mip.bytes + clut_bytes : 0u, &entry,
		HCU_BITMAP_DEFER_PROBE_PTR, HCU_BITMAP_PROBE_HUD);
#else
	cache->hud_priority = 1;
	acquired = tc_acquire_j(cache, journal, binding->cache_key, pages,
		upload_source ? mip.bytes + clut_bytes : 0u, &entry);
#endif
	cache->hud_priority = 0;
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
		if (retained_bytes > source_storage_limit) goto rollback;
		/* Each successful tc upload is charged against cache->budget_bytes. The
		 * packed cursor is monotonic until the actual paired-chain fence. */
		{
			uint32_t offset = 0;
			for (i = 0; i < slot_count; ++i) {
				uint32_t end;
				if (!slots[i].valid) continue;
				if (slots[i].storage_offset >= source_storage_limit) continue; /* fixed HUD composition arena */
				if (slots[i].storage_offset > source_storage_limit ||
					slots[i].storage_bytes > source_storage_limit - slots[i].storage_offset)
					goto rollback;
				end = slots[i].storage_offset + slots[i].storage_bytes;
				if (end > offset) offset = end;
			}
			if (offset > source_storage_limit || retained_bytes > source_storage_limit - offset)
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
	state.clamp = request->bitmap_wrap ? GS_CLAMP(0, 0, 0, 0, 0, 0) :
		GS_CLAMP(1, 1, 0, image.width - 1u, 0, image.height - 1u);
	state.screen_w = screen_w; state.screen_h = screen_h;
	state.z = 0xFFFFFFu; state.blend = blend; state.texture_layers = 1;
	state.point_sampled = request->point_sampled;
	for (i = 0; i < 4; i++) {
		vertices[i].x = request->vertices[i].x; vertices[i].y = request->vertices[i].y;
		vertices[i].u = request->vertices[i].u; vertices[i].v = request->vertices[i].v;
		vertices[i].argb = request->vertices[i].color;
		if (vertices[i].u < 0.0f || vertices[i].u > 1.0f ||
			vertices[i].v < 0.0f || vertices[i].v > 1.0f)
			state.uv_extended = 1;
	}
	if (prepare_only) {
		*prepared_tex0 = state.tex0;
		*prepared_clamp = state.clamp;
	} else {
		/* CE vertices are viewport-relative: offset into this view and clip to it. */
		if (hcu_bitmap_quad_place(&state, &target, vertices, placed) != 0) goto rollback;
		memcpy(vertices, placed, sizeof(vertices));
	if (request->screen_effect_mask && !prepare_only) {
		/* Retail's zoom effect darkens the view by the mask's Y: framebuffer * (1 - Y), a black quad with alpha Y (the
		 * CLUT is black with alpha Y). The mask's texels sit 1:1 on the pane, centred, and its edge texel is
		 * extended over the rest (clamp). Corners are given in the HUD's virtual frame, which place() scales back. */
		float sx = (float)target.w / (float)screen_w, sy = (float)target.h / (float)screen_h;
		float scale = sx < sy ? sx : sy;
		float mw = (float)image.width, mh = (float)image.height;
		float ox = ((float)target.w - mw) * 0.5f, oy = ((float)target.h - mh) * 0.5f;
		float tx[2], ty[2];
		unsigned k;
		if (!(scale > 0.0f)) goto rollback;
		tx[0] = -ox; tx[1] = (float)target.w - ox;
		ty[0] = -oy; ty[1] = (float)target.h - oy;
		for (k = 0; k < 4; k++) {
			vertices[k].x = (k == 1 || k == 2) ? (float)target.w / scale : 0.0f;
			vertices[k].y = (k >= 2) ? (float)target.h / scale : 0.0f;
			/* put_vertex maps u to 0.5 + u * (width - 1) texels */
			vertices[k].u = (tx[(k == 1 || k == 2) ? 1 : 0] - 0.5f) / (mw - 1.0f);
			vertices[k].v = (ty[(k >= 2) ? 1 : 0] - 0.5f) / (mh - 1.0f);
			vertices[k].argb = 0xFFFFFFFFu;
		}
		state.blend = HCU_BITMAP_BLEND_ALPHA;
		state.point_sampled = 1;
		state.uv_extended = 1;
		state.clamp = GS_CLAMP(1, 1, 0, image.width - 1u, 0, image.height - 1u);
	}
		if (request->has_meter & HALO_PS2_BITMAP_METER_PRESENT) {
			int palette = meter_emit_palette(context, &image, &state, vertices, request, tbp, tbw,
				upload_chain, geometry_chain, lease);
			if (palette < 0) goto rollback;
			if (!palette && meter_emit(geometry_chain, &image,
				&state, vertices, request) != HCU_BITMAP_QUAD_OK)
				goto rollback;
		} else if (hcu_bitmap_quad_emit_validated(geometry_chain, &image,
			&state, vertices) != HCU_BITMAP_QUAD_OK) {
			goto rollback;
		}
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
#if defined(HALO_PS2_C3_BITMAP_DEFER_PROBE) && HALO_PS2_C3_BITMAP_DEFER_PROBE
	hcu_bitmap_defer_probe_add_hud(HCU_BITMAP_DEFER_PROBE_PTR, !prepare_only,
		acquired == TC_UPLOAD);
#endif
	return HCU_BITMAP_DISPATCH_OK;

rollback:
	*upload_chain = upload_before;
	*geometry_chain = geometry_before;
	tc_journal_rollback(cache, journal);
	if (upload_source && slot) memset(slot, 0, sizeof(*slot));
	return HCU_BITMAP_DISPATCH_E_CAPACITY;
}

int32_t hcu_bitmap_dispatch_prepare_screen_effect_mask(hcu_bitmap_dispatch_context *ctx,
	const halo_ps2_bitmap_request_reader *reader, uint32_t request_index,
	uint64_t *tex0, uint64_t *clamp)
{
	const halo_ps2_bitmap_request *request;
	halo_ps2_screen_effect_state effect;
	hcu_bitmap_lease *lease;
	hcu_bitmap_dispatch_status status;
	uint32_t word, bit;
	if (!ctx || !reader || !reader->held || !reader->queue || !reader->requests ||
		!tex0 || !clamp || request_index >= reader->count ||
		reader->generation != ctx->expected_generation ||
		!ctx->screen_effect_snapshot_valid ||
		ctx->screen_effect_generation != reader->generation ||
		ctx->screen_effect_frame_index != reader->queue->frame_index)
		return HCU_BITMAP_DISPATCH_E_ARGUMENT;
	request = &reader->requests[request_index];
	if (!request->screen_effect_mask || request->generation != reader->generation ||
		request->frame_index != reader->queue->frame_index || request->view_index < 0 ||
		request->view_index >= (int16_t)HALO_PS2_BITMAP_MAX_VIEWS ||
		hcu_bitmap_dispatch_screen_effect_get(ctx, reader->generation,
			reader->queue->frame_index, (uint16_t)request->view_index, &effect) != 1 ||
		effect.mask_request_index != request_index)
		return HCU_BITMAP_DISPATCH_E_IDENTITY;
	word = request_index >> 5;
	bit = 1u << (request_index & 31u);
	if (ctx->screen_effect_prepared_request_mask[word] & bit)
		return HCU_BITMAP_DISPATCH_E_BUSY;
	if (ctx->lease_count >= ctx->lease_capacity || !ctx->leases || !ctx->upload_chain ||
		!ctx->geometry_chain || !ctx->cache)
		return HCU_BITMAP_DISPATCH_E_CAPACITY;
	lease = &ctx->leases[ctx->lease_count];
	memset(lease, 0, sizeof(*lease));
	status = dispatch_request_impl(ctx, request, ctx->bindings, ctx->binding_count,
		ctx->profile, ctx->expected_generation, ctx->cache, ctx->journal,
		ctx->cache_readers, ctx->cache_reader_count, ctx->slots, ctx->slot_count,
		ctx->source_storage, ctx->source_storage_bytes, ctx->slot_stride,
		ctx->staging_buffer, ctx->staging_buffer_bytes, ctx->upload_chain,
		ctx->geometry_chain, ctx->texture_page_base_words, ctx->clut_base_words,
		ctx->screen_w, ctx->screen_h, (hcu_bitmap_rect){ 0, 0, 0, 0 }, lease,
		1, tex0, clamp);
	if (status != HCU_BITMAP_DISPATCH_OK) return status;
	lease->kick_seq = bsp_render_kick_seq ? bsp_render_kick_seq() + 1u : 0u;
	ctx->lease_count++;
	ctx->screen_effect_prepared_request_mask[word] |= bit;
	ctx->screen_effect_prepared_count++;
	ctx->screen_effect_mask_tex0[(uint16_t)request->view_index] = *tex0;
	ctx->screen_effect_mask_clamp[(uint16_t)request->view_index] = *clamp;
	ctx->screen_effect_mask_texture_valid_mask |= 1u << (uint16_t)request->view_index;
	return HCU_BITMAP_DISPATCH_OK;
}

int32_t hcu_bitmap_dispatch_screen_effect_mask_complement_clut(
	hcu_bitmap_dispatch_context *ctx,
	const halo_ps2_bitmap_request_reader *reader, uint32_t request_index,
	uint8_t clut_rgba32[1024])
{
	const halo_ps2_bitmap_request *request;
	const hcu_bitmap_binding *binding;
	hcu_asset_chunk_view chunk;
	hcu_asset_profile_staged_stats stats;
	tex_section section;
	tex_info image;
	tex_mip_view mip;
	const uint8_t *clut;
	uint32_t i, word, bit, clut_bytes;
	if (!ctx || !reader || !reader->held || !reader->queue || !reader->requests || !clut_rgba32 ||
		request_index >= reader->count || reader->generation != ctx->expected_generation ||
		!ctx->screen_effect_snapshot_valid || ctx->screen_effect_generation != reader->generation ||
		ctx->screen_effect_frame_index != reader->queue->frame_index || !ctx->profile ||
		!ctx->staging_buffer || ctx->slot_stride > ctx->staging_buffer_bytes)
		return HCU_BITMAP_DISPATCH_E_ARGUMENT;
	word = request_index >> 5;
	bit = 1u << (request_index & 31u);
	if (!(ctx->screen_effect_prepared_request_mask[word] & bit)) return HCU_BITMAP_DISPATCH_E_BUSY;
	request = &reader->requests[request_index];
	if (!request->screen_effect_mask || request->generation != reader->generation ||
		request->frame_index != reader->queue->frame_index || request->bitmap_tag_index < 0)
		return HCU_BITMAP_DISPATCH_E_IDENTITY;
	binding = binding_find(ctx->bindings, ctx->binding_count,
		request->bitmap_tag_index, request->bitmap_index);
	if (!binding || binding->expected_profile_id != ctx->profile->profile_id ||
		hcu_asset_profile_lookup(ctx->profile, HCU_ASSET_CHUNK_MEDIA,
			binding->chunk_id, &chunk) != HCU_ASSET_PROFILE_OK || chunk.size > ctx->slot_stride ||
		memcmp(chunk.sha256, binding->expected_chunk_sha256, 32) != 0)
		return HCU_BITMAP_DISPATCH_E_IDENTITY;
	if (hcu_asset_profile_read_chunk_staged_profiled(ctx->profile, HCU_ASSET_CHUNK_MEDIA,
		binding->chunk_id, ctx->staging_buffer, ctx->slot_stride, &stats) != HCU_ASSET_PROFILE_OK)
		return HCU_BITMAP_DISPATCH_E_CHUNK;
	ctx->counters.source_reads++;
	ctx->counters.source_bytes += chunk.size;
	ctx->counters.hash_checks++;
	ctx->counters.read_calls += stats.payload_read_calls;
#if defined(HALO_PS2_C3_LAG_TRACE) && HALO_PS2_C3_LAG_TRACE
	hud_read_trace("mask-clut", binding->chunk_id, chunk.size);
#endif
	ctx->counters.read_bytes += stats.payload_read_bytes;
	ctx->counters.read_cycles += stats.read_cycles;
	ctx->counters.hash_cycles += stats.hash_cycles;
	ctx->counters.parses++;
	if (tex_open(&section, (const uint8_t *)ctx->staging_buffer, chunk.size) != TEX_OK ||
		binding->image_index >= section.texture_count)
		return HCU_BITMAP_DISPATCH_E_FORMAT;
	image = tex_get(&section, binding->image_index);
	if (image.source_id != binding->expected_source_datum ||
		!screen_effect_mask_shape(request, &image,
			tex_mip(&section, &image, 0, &mip) ? mip.bytes : 0u,
			(uint32_t)image.clut_entries * 4u) || !(clut = tex_clut(&section, &image)))
		return HCU_BITMAP_DISPATCH_E_IDENTITY;
	clut_bytes = (uint32_t)image.clut_entries * 4u;
	if (clut_bytes != 1024u) return HCU_BITMAP_DISPATCH_E_FORMAT;
	memcpy(clut_rgba32, clut, 1024u);
	for (i = 0; i < 256u; ++i) {
		if (clut_rgba32[i * 4u + 3u] > 128u) return HCU_BITMAP_DISPATCH_E_FORMAT;
		clut_rgba32[i * 4u + 3u] = (uint8_t)(128u - clut_rgba32[i * 4u + 3u]);
	}
	return HCU_BITMAP_DISPATCH_OK;
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
		screen_w, screen_h, target, lease, 0, NULL, NULL);
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
	/* A meter's palette slot, held beside its texture. */
	if (slots && lease->reserved && (uint32_t)lease->reserved - 1u < slot_count &&
		slots[lease->reserved - 1u].readers) {
		slots[lease->reserved - 1u].readers--;
		if (!slots[lease->reserved - 1u].readers)
			memset(&slots[lease->reserved - 1u], 0, sizeof(slots[lease->reserved - 1u]));
	}
	lease->reserved = 0;
	lease->active = 0;
}

int hcu_bitmap_dispatch_reader(const halo_ps2_bitmap_request_reader *reader,
	void *context)
{
	hcu_bitmap_dispatch_context *ctx = (hcu_bitmap_dispatch_context *)context;
	uint32_t i, bitmap_requests = 0;
	if (!reader || !reader->held || !ctx || !reader->requests || !reader->queue ||
		!ctx->leases || ctx->lease_count > ctx->lease_capacity ||
		ctx->screen_effect_prepared_count > reader->count || !ctx->cache ||
		!ctx->cache_readers || ctx->cache_reader_count < ctx->cache->max_keys ||
		reader->generation != ctx->expected_generation)
		return HCU_BITMAP_DISPATCH_E_ARGUMENT;
	for (i = 0; i < reader->count; i++)
		if (!reader->requests[i].screen_effect_mask && !reader->requests[i].screen_flash &&
			!reader->requests[i].motion_marker && !reader->requests[i].button_glyph)
			bitmap_requests++;
	/* Flashes, motion markers and button glyphs are untextured, so they do not take a lease. */
	if (bitmap_requests > ctx->lease_capacity - ctx->lease_count)
		return HCU_BITMAP_DISPATCH_E_ARGUMENT;
	if (hcu_bitmap_dispatch_capture_screen_effects(ctx, reader->queue) != HCU_BITMAP_DISPATCH_OK)
		return HCU_BITMAP_DISPATCH_E_ARGUMENT;
	ctx->first_error = HCU_BITMAP_DISPATCH_OK;
	/* leased entries stay protected for the whole batch; the touch is idempotent within the frame */
	hcu_bitmap_dispatch_touch_cache(ctx->cache, ctx->cache_readers, ctx->cache_reader_count);
	for (i = 0; i < reader->count; i++) {
		hcu_bitmap_lease *lease = &ctx->leases[ctx->lease_count];
		hcu_bitmap_dispatch_status status;
		hcu_bitmap_rect target;
		/* A captured effect mask is consumed by a native pre-HUD backend when one is active. Without one it is
		 * drawn below as the retail scope darkening (a black quad whose alpha is the mask's Y). */
		if (reader->requests[i].screen_effect_mask && ctx->screen_effect_backend_active)
			continue; /* a native backend draws it before the HUD */
		memset(lease, 0, sizeof(*lease));
		if (hcu_bitmap_view_resolve(ctx->views, ctx->view_count, reader->requests[i].view_index,
			ctx->screen_w, ctx->screen_h, &target) != 0) {
			if (ctx->first_error == HCU_BITMAP_DISPATCH_OK) ctx->first_error = HCU_BITMAP_DISPATCH_E_VIEW;
			continue;
		}
		/* Screen flash: untextured, so no binding, texture lease or cache entry. */
		if (reader->requests[i].screen_flash) {
			hcu_bitmap_quad_status flash = hcu_bitmap_quad_emit_flash(ctx->geometry_chain,
				ctx->screen_w, ctx->screen_h, &target, 0xFFFFFFu,
				(int16_t)reader->requests[i].screen_flash_type, reader->requests[i].vertices[0].color,
				reader->requests[i].vertices[1].color & 255u, ctx->flash_frame_base);
			if (flash == HCU_BITMAP_QUAD_OK) ctx->screen_flashes++;
			else if (flash == HCU_BITMAP_QUAD_CAPACITY) ctx->counters.deferred++;
			else if (ctx->first_error == HCU_BITMAP_DISPATCH_OK) ctx->first_error = HCU_BITMAP_DISPATCH_E_ARGUMENT;
			continue;
		}
		/* Controller button glyph of a help prompt: vector shapes, no texture. */
		if (reader->requests[i].button_glyph) {
			hcu_bitmap_quad_status glyph = hcu_bitmap_quad_emit_glyph(ctx->geometry_chain,
				ctx->screen_w, ctx->screen_h, &target, reader->requests[i].button_glyph,
				(reader->requests[i].vertices[0].x + reader->requests[i].vertices[2].x) * 0.5f,
				(reader->requests[i].vertices[0].y + reader->requests[i].vertices[2].y) * 0.5f,
				reader->requests[i].vertices[2].y - reader->requests[i].vertices[0].y,
				reader->requests[i].vertices[0].color);
			if (glyph == HCU_BITMAP_QUAD_CAPACITY) ctx->counters.deferred++;
			continue;
		}
		/* Motion-sensor blip or sweep: untextured, same virtual-frame vertices as the HUD.
		 * A sweep (motion_disc_radius set) is a ring clipped to the radar circle. */
		if (reader->requests[i].motion_marker) {
			hcu_bitmap_vertex_t marker_v[4];
			hcu_bitmap_quad_status marker;
			unsigned k;
			for (k = 0; k < 4; k++) {
				marker_v[k].x = reader->requests[i].vertices[k].x;
				marker_v[k].y = reader->requests[i].vertices[k].y;
				marker_v[k].u = 0.0f; marker_v[k].v = 0.0f;
				marker_v[k].argb = reader->requests[i].vertices[k].color;
			}
			if (reader->requests[i].motion_disc_radius > 0.0f) {
				float hole = 0.0f;
				if (i + 1u < reader->count && reader->requests[i + 1u].motion_marker == 2u)
					hole = (reader->requests[i + 1u].vertices[1].x -
						reader->requests[i + 1u].vertices[0].x) * 0.5f;
				marker = hcu_bitmap_quad_emit_ring(ctx->geometry_chain, ctx->screen_w, ctx->screen_h,
					&target, reader->requests[i].motion_disc_x, reader->requests[i].motion_disc_y,
					reader->requests[i].motion_disc_radius, hole, marker_v[0].argb);
				if (hole > 0.0f) i++; /* the subtractive square is the hole; the ring drew it */
			} else {
				marker = hcu_bitmap_quad_emit_marker(ctx->geometry_chain, ctx->screen_w, ctx->screen_h,
					&target, marker_v, reader->requests[i].motion_marker == 2u);
			}
			if (marker == HCU_BITMAP_QUAD_CAPACITY) ctx->counters.deferred++;
			continue;
		}
		/* A run of text: composed into one texture, so it takes a lease like the multiply overlay. */
		if (reader->requests[i].text_run) {
			status = dispatch_text_run(ctx, reader->queue, &reader->requests[i], target, lease);
			if (status == HCU_BITMAP_DISPATCH_OK) {
				lease->kick_seq = bsp_render_kick_seq ? bsp_render_kick_seq() + 1u : 0u;
				ctx->lease_count++;
			} else if (status == HCU_BITMAP_DISPATCH_E_BUSY || status == HCU_BITMAP_DISPATCH_E_CAPACITY) {
				ctx->counters.deferred++;   /* not drawn this frame; the string is queued again next frame */
			}
			continue;
		}
		status = reader->requests[i].has_multiply_map ?
			dispatch_multiply_request(ctx, &reader->requests[i], target, lease) :
			dispatch_request_impl(ctx, &reader->requests[i], ctx->bindings,
			ctx->binding_count, ctx->profile, ctx->expected_generation,
			ctx->cache, ctx->journal, ctx->cache_readers, ctx->cache_reader_count,
			ctx->slots, ctx->slot_count,
			ctx->source_storage, ctx->source_storage_bytes, ctx->slot_stride,
		/* A multiply overlay faded to nothing (the sniper's angle ticks while unzoomed) draws nothing:
		 * its primary map is only a mask and must never be drawn plain. */
		if (reader->requests[i].has_multiply_map && reader->requests[i].multiply_tint[3] == 0u)
			continue;
			ctx->staging_buffer, ctx->staging_buffer_bytes,
			ctx->upload_chain, ctx->geometry_chain,
			ctx->texture_page_base_words, ctx->clut_base_words,
			ctx->screen_w, ctx->screen_h, target, lease, 0, NULL, NULL);
		/* A multiply overlay that is not the narrow sniper strip still draws its
		 * primary map. Composing the second map would exceed the per-frame budget. */
		if (status == HCU_BITMAP_DISPATCH_E_UNSUPPORTED && reader->requests[i].has_multiply_map) {
			halo_ps2_bitmap_request plain = reader->requests[i];
			plain.has_multiply_map = 0;
			status = dispatch_request_impl(ctx, &plain, ctx->bindings,
				ctx->binding_count, ctx->profile, ctx->expected_generation,
				ctx->cache, ctx->journal, ctx->cache_readers, ctx->cache_reader_count,
				ctx->slots, ctx->slot_count,
				ctx->source_storage, ctx->source_storage_bytes, ctx->slot_stride,
				ctx->staging_buffer, ctx->staging_buffer_bytes,
				ctx->upload_chain, ctx->geometry_chain,
				ctx->texture_page_base_words, ctx->clut_base_words,
				ctx->screen_w, ctx->screen_h, target, lease, 0, NULL, NULL);
		}
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
		if (lease->active &&
			(lease->cache_key == UINT16_MAX || (lease->cache_key < ctx->cache_reader_count &&
			 ctx->cache_readers[lease->cache_key])) &&
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
