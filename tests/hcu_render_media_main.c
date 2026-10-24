/* Host test for src/stream/hcu_render_media.c and the C3 chunk-kind table.
 * argv: package.hcp bsps.bin texs.bin lm.bin norender.hcp */
#include "stream/hcu_render_media.h"
#include "stream/hcu_render_world.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

/* The map service is not linked: hcu_render_world.c only needs these symbols for bind. */
int hcu_map_service_reader_acquire(hcu_map_service *s, hcu_map_reader_kind k, const void *p, uint32_t n, hcu_map_reader_ref *r)
{ (void)s; (void)k; (void)p; (void)n; (void)r; return 0; }
int hcu_map_service_reader_release(hcu_map_service *s, hcu_map_reader_ref r) { (void)s; (void)r; return 0; }
int hcu_map_service_bind_world(hcu_map_service *s, const struct bsp_section *b, const void *x) { (void)s; (void)b; (void)x; return 0; }
int hcu_map_service_current_world(const hcu_map_service *s, const struct bsp_section **b, const void **x, uint32_t *g)
{ (void)s; (void)b; (void)x; (void)g; return 0; }

#define CHECK(c) do { if (!(c)) { fprintf(stderr, "FAIL line %d: %s\n", __LINE__, #c); return 1; } } while (0)

static uint8_t *slurp(const char *path, size_t *n)
{
	FILE *f = fopen(path, "rb"); long len; uint8_t *p;
	if (!f) return NULL;
	fseek(f, 0, SEEK_END); len = ftell(f); rewind(f);
	p = malloc((size_t)len + 1);
	if (!p || fread(p, 1, (size_t)len, f) != (size_t)len) return NULL;
	fclose(f); *n = (size_t)len; return p;
}

static uint8_t s_bsp_span[1u << 20] __attribute__((aligned(64)));
static uint8_t s_tex_span[1u << 20] __attribute__((aligned(64)));

int main(int argc, char **argv)
{
	size_t pn, bn, tn, ln, nn;
	uint8_t *pkg, *bsps, *texs, *lm, *norender;
	hcu_asset_profile_view v, v2;
	hcu_asset_chunk_kind k;
	hcu_render_media m;
	hcu_render_media_span bs = { s_bsp_span, sizeof s_bsp_span }, ts = { s_tex_span, sizeof s_tex_span };
	const uint8_t *pb; size_t pbn;
	uint32_t life = 0;
	mat_binding_t mb; tex_image_t img; tex_binding b0; unsigned page;
	if (argc != 6) return 2;
	pkg = slurp(argv[1], &pn); bsps = slurp(argv[2], &bn); texs = slurp(argv[3], &tn);
	lm = slurp(argv[4], &ln); norender = slurp(argv[5], &nn);
	CHECK(pkg && bsps && texs && lm && norender);

	/* kind table */
	CHECK(hcu_asset_chunk_kind_lookup(HCU_ASSET_CHUNK_BSPS, &k) == 0 && k.keyed && strcmp(k.name, "BSPS") == 0);
	CHECK(hcu_asset_chunk_kind_lookup(HCU_ASSET_CHUNK_TEXS, &k) == 0 && strcmp(k.name, "TEXS") == 0);
	CHECK(hcu_asset_chunk_kind_lookup(HCU_ASSET_CHUNK_LIGHTMAP, &k) == 0 && strcmp(k.name, "LMn") == 0);
	CHECK(hcu_asset_chunk_kind_lookup(0, &k) != 0 && hcu_asset_chunk_kind_lookup(7, &k) != 0);
	CHECK(hcu_asset_chunk_id_valid(1, 0) && !hcu_asset_chunk_id_valid(1, 1));
	CHECK(hcu_asset_chunk_id_valid(3, 0) && !hcu_asset_chunk_id_valid(3, 2));
	CHECK(hcu_asset_chunk_id_valid(2, 99) && hcu_asset_chunk_id_valid(4, 3) && hcu_asset_chunk_id_valid(6, 12));
	CHECK(!hcu_asset_chunk_id_valid(7, 0));
	CHECK(hcu_asset_profile_lifetime(4, &life) == 0 && life == HCU_ASSET_LIFETIME_MAP_UNLOAD);
	CHECK(hcu_asset_profile_lifetime(7, &life) != 0);

	/* package without render chunks */
	CHECK(hcu_asset_profile_preflight(norender, nn, 7, &v2) == 0);
	CHECK(hcu_render_media_load(&m, &v2, 0, bs, ts, NULL) == HCU_RENDER_MEDIA_E_ABSENT);
	CHECK(hcu_render_world_profile_bsps(NULL, &pb, &pbn) == HCU_RENDER_WORLD_E_NO_PRODUCER && !pb && !pbn);

	/* real load */
	CHECK(hcu_asset_profile_preflight(pkg, pn, 7, &v) == 0);
	/* index with no chunks */
	CHECK(hcu_render_media_load(&m, &v, 5, bs, ts, NULL) == HCU_RENDER_MEDIA_E_ABSENT);
	/* too small span: nothing is left behind */
	{ hcu_render_media_span small = { s_bsp_span, bn - 16 };
	  CHECK(hcu_render_media_load(&m, &v, 0, small, ts, NULL) == HCU_RENDER_MEDIA_E_SPAN); }
	{ hcu_render_media_span small = { s_tex_span, tn + ln - 16 };
	  CHECK(hcu_render_media_load(&m, &v, 0, bs, small, NULL) == HCU_RENDER_MEDIA_E_SPAN);
	  CHECK(s_bsp_span[0] == 0 && s_bsp_span[bn / 2] == 0); }
	CHECK(hcu_render_media_load(&m, &v, 0, bs, ts, NULL) == 0);
	CHECK(m.loaded && m.bsps_bytes == bn && m.texs_bytes == tn && m.lm_bytes == ln && m.has_lm);
	CHECK(memcmp(m.bsps, bsps, bn) == 0 && memcmp(m.texs, texs, tn) == 0 && memcmp(m.lm, lm, ln) == 0);
	CHECK(m.bsps >= s_bsp_span && m.bsps + bn <= s_bsp_span + sizeof s_bsp_span);
	CHECK(m.texs >= s_tex_span && m.lm + ln <= s_tex_span + sizeof s_tex_span && m.lm >= m.texs + tn);
	CHECK(((uintptr_t)m.bsps & 63u) == 0 && ((uintptr_t)m.texs & 63u) == 0 && ((uintptr_t)m.lm & 63u) == 0);
	CHECK(m.bsps_span_used >= bn && m.tex_span_used >= tn + ln);
	CHECK(hcu_render_media_load(&m, &v, 0, bs, ts, NULL) == HCU_RENDER_MEDIA_E_STATE);
	CHECK(hcu_render_world_profile_bsps(NULL, &pb, &pbn) == 0 && pb == m.bsps && pbn == bn);

	/* tex_source over the packaged TEXS/LMn */
	CHECK(m.source.texture_count == m.tex.texture_count && m.source.texture_count > 0);
	b0 = tex_get_binding(&m.tex, 0);
	{ unsigned i, textured = 0;
	  for (i = 0; i < m.tex.binding_count; ++i) {
		tex_binding b = tex_get_binding(&m.tex, i);
		if (m.source.binding(m.source.user, b.shader_id, &mb) == 0) {
			CHECK(mb.tex >= 0 && (uint32_t)mb.tex < m.tex.texture_count);
			CHECK(m.source.texture(m.source.user, mb.tex, &img) == 0);
			CHECK(img.pixels && img.clut && img.w >= 8 && img.pixel_bytes > 0);
			textured++;
		}
	  }
	  CHECK(textured > 0); }
	CHECK(m.source.binding(m.source.user, 0xdeadbeefu, &mb) != 0);
	CHECK(m.source.texture(m.source.user, -1, &img) != 0);
	(void)b0;
	for (page = 0; page < m.lightmap.page_count; ++page)
		if (m.source.lightmap(m.source.user, page, &img) == 0) break;
	CHECK(page < m.lightmap.page_count && img.clut_bytes == LM_CLUT_BYTES && img.psm == TEX_PSMT8);
	CHECK(m.source.lightmap(m.source.user, 100000u, &img) != 0);

	hcu_render_media_clear(&m);
	CHECK(!m.loaded && hcu_render_world_profile_bsps(NULL, &pb, &pbn) == HCU_RENDER_WORLD_E_NO_PRODUCER);

	/* corruption after preflight must be caught by the logical hash */
	{ hcu_asset_chunk_view e; uint8_t *image = pkg;
	  CHECK(hcu_asset_profile_lookup(&v, HCU_ASSET_CHUNK_BSPS, 0, &e) == 0);
	  image[e.offset + 100] ^= 0x40;   /* first segment payload */
	  CHECK(hcu_render_media_load(&m, &v, 0, bs, ts, NULL) == HCU_RENDER_MEDIA_E_HASH);
	  CHECK(!m.loaded && s_bsp_span[100] == 0);
	  image[e.offset + 100] ^= 0x40; }
	CHECK(hcu_render_media_load(&m, &v, 0, bs, ts, NULL) == 0);
	puts("render media host test OK");
	return 0;
}
