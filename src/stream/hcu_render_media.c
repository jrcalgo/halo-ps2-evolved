#include "stream/hcu_render_media.h"

#include <string.h>

#include "stream/hcu_render_world.h"
#include "stream/sha256.h"

#define MEDIA_ALIGN 64u

static size_t align_up(size_t v) { return (v + (MEDIA_ALIGN - 1u)) & ~(size_t)(MEDIA_ALIGN - 1u); }

/* Reads a whole chunk into dst with read_range and proves its logical SHA-256. */
static int read_verified(const hcu_asset_profile_view *view, uint32_t kind, uint32_t id,
	uint8_t *dst, uint32_t size, const uint8_t want[32])
{
	sha256_context s;
	uint8_t digest[32];
	uint32_t at = 0;
	/* Bounded steps: a read_range call never spans more than 256 KiB. */
	while (at < size) {
		uint32_t n = size - at < 262144u ? size - at : 262144u;
		if (hcu_asset_profile_read_range(view, kind, id, at, dst + at, n) != 0)
			return HCU_RENDER_MEDIA_E_READ;
		at += n;
	}
	sha256_init(&s);
	sha256_update(&s, dst, size);
	sha256_final(&s, digest);
	return memcmp(digest, want, 32) ? HCU_RENDER_MEDIA_E_HASH : HCU_RENDER_MEDIA_OK;
}

static int place(const hcu_asset_profile_view *view, uint32_t kind, uint32_t id,
	hcu_render_media_span span, size_t *used, uint8_t **out, size_t *out_bytes)
{
	hcu_asset_chunk_view c;
	size_t at = align_up(*used);
	int rc;
	if (hcu_asset_profile_lookup(view, kind, id, &c) != 0) return HCU_RENDER_MEDIA_E_ABSENT;
	if (at < *used || at > span.bytes || c.size > span.bytes - at) return HCU_RENDER_MEDIA_E_SPAN;
	rc = read_verified(view, kind, id, span.base + at, c.size, c.sha256);
	if (rc != 0) { memset(span.base + at, 0, c.size); return rc; }
	*out = span.base + at;
	*out_bytes = c.size;
	*used = at + c.size;
	return HCU_RENDER_MEDIA_OK;
}

/* ---- tex_source_t adapter (same mapping as engine/src/world/world.c) ---------------------------- */
static int src_binding(void *user, uint32_t shader_id, mat_binding_t *out)
{
	const hcu_render_media *m = user;
	tex_binding b;
	if (!m || !m->has_tex || !tex_find_binding(&m->tex, shader_id, &b)) return -1;
	out->tex = b.texture == TEX_NONE ? (int16_t)-1 : (int16_t)b.texture;
	out->flags = 0;
	out->pad = 0;
	if (b.flags & TEX_B_ALPHA_TEST) out->flags |= MAT_ALPHA_TEST;
	if (b.blend >= TEX_BLEND_ALPHA) out->flags |= MAT_BLEND;
	if (b.flags & TEX_B_TWO_SIDED) out->flags |= MAT_TWO_SIDED;
	out->uv_scale[0] = b.uv_scale[0];
	out->uv_scale[1] = b.uv_scale[1];
	return out->tex < 0 ? -1 : 0;
}

static int src_texture(void *user, int tex, tex_image_t *out)
{
	const hcu_render_media *m = user;
	tex_info t;
	tex_mip_view mv;
	if (!m || !m->has_tex || tex < 0 || (uint32_t)tex >= m->tex.texture_count) return -1;
	t = tex_get(&m->tex, (uint32_t)tex);
	if (!tex_mip(&m->tex, &t, 0, &mv)) return -1;
	out->pixels = mv.pixels;
	out->pixel_bytes = mv.bytes;
	out->clut = tex_clut(&m->tex, &t);
	out->clut_bytes = (uint32_t)t.clut_entries * 4u;
	out->w = t.width;
	out->h = t.height;
	out->psm = t.psm;
	return 0;
}

static int src_lightmap(void *user, unsigned page, tex_image_t *out)
{
	const hcu_render_media *m = user;
	lm_page_info p;
	if (!m || !m->has_lm || !lm_get_page(&m->lightmap, page, &p)) return -1;
	out->pixels = p.pixels;
	out->pixel_bytes = p.pixel_bytes;
	out->clut = m->lightmap.clut;
	out->clut_bytes = LM_CLUT_BYTES;
	out->w = p.width;
	out->h = p.height;
	out->psm = p.psm;
	return 0;
}

int hcu_render_media_load(hcu_render_media *m, const hcu_asset_profile_view *view,
	uint32_t bsp_index, hcu_render_media_span bsps, hcu_render_media_span tex,
	hcu_render_media_flush_fn flush)
{
	size_t bu = 0, tu = 0;
	int rc;
	hcu_asset_chunk_view probe;
	if (!m || !view || !bsps.base || !tex.base) return HCU_RENDER_MEDIA_E_ARGUMENT;
	if (m->loaded) return HCU_RENDER_MEDIA_E_STATE;
	if (((uintptr_t)bsps.base | (uintptr_t)tex.base) & (MEDIA_ALIGN - 1u)) return HCU_RENDER_MEDIA_E_ARGUMENT;
	memset(m, 0, sizeof *m);
	m->bsp_index = bsp_index;
	rc = place(view, HCU_ASSET_CHUNK_BSPS, bsp_index, bsps, &bu, &m->bsps, &m->bsps_bytes);
	if (rc != 0) goto fail;
	rc = place(view, HCU_ASSET_CHUNK_TEXS, bsp_index, tex, &tu, &m->texs, &m->texs_bytes);
	if (rc != 0) goto fail;
	if (tex_open(&m->tex, m->texs, m->texs_bytes) != TEX_OK) { rc = HCU_RENDER_MEDIA_E_FORMAT; goto fail; }
	m->has_tex = 1;
	if (hcu_asset_profile_lookup(view, HCU_ASSET_CHUNK_LIGHTMAP, bsp_index, &probe) == 0) {
		rc = place(view, HCU_ASSET_CHUNK_LIGHTMAP, bsp_index, tex, &tu, &m->lm, &m->lm_bytes);
		if (rc != 0) goto fail;
		if (lm_open(&m->lightmap, m->lm, m->lm_bytes) != TEX_OK) { rc = HCU_RENDER_MEDIA_E_FORMAT; goto fail; }
		m->has_lm = 1;
	}
	if (flush) {
		flush(bsps.base, bu);
		flush(tex.base, tu);
	}
	m->bsps_span_used = bu;
	m->tex_span_used = tu;
	m->source.binding = src_binding;
	m->source.texture = src_texture;
	m->source.lightmap = m->has_lm ? src_lightmap : NULL;
	m->source.user = m;
	m->source.texture_count = m->tex.texture_count;
	m->loaded = 1;
	hcu_render_world_publish_profile_bsps(m->bsps, m->bsps_bytes);
	return HCU_RENDER_MEDIA_OK;
fail:
	if (bu) memset(bsps.base, 0, bu);
	if (tu) memset(tex.base, 0, tu);
	memset(m, 0, sizeof *m);
	return rc;
}

void hcu_render_media_clear(hcu_render_media *m)
{
	if (!m) return;
	if (m->loaded) hcu_render_world_publish_profile_bsps(NULL, 0);
	memset(m, 0, sizeof *m);
}
