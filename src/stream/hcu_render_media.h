/* C3.render-media: loads the profile's BSPS/TEXS/LMn render chunks into
 * caller-owned spans and exposes them as a renderer tex_source_t.
 *
 * Reads go through hcu_asset_profile_read_range only and are verified against the
 * chunk's full logical SHA-256 before anything is published. Nothing is
 * allocated: BSPS goes to `bsps` (the BSP span), TEXS and LMn go to `tex`
 * (the render_texture span). Failure leaves the media unloaded and the spans
 * zeroed over the region touched. */
#ifndef HALO_STREAM_HCU_RENDER_MEDIA_H
#define HALO_STREAM_HCU_RENDER_MEDIA_H

#include <stddef.h>
#include <stdint.h>

#include "render/bsp_render.h"
#include "stream/hcu_asset_profile.h"
#include "world/tex.h"

#ifdef __cplusplus
extern "C" {
#endif

enum {
	HCU_RENDER_MEDIA_OK = 0,
	HCU_RENDER_MEDIA_E_ARGUMENT = -1,
	HCU_RENDER_MEDIA_E_ABSENT = -2,   /* no BSPS chunk for this index (package built without --render-media) */
	HCU_RENDER_MEDIA_E_SPAN = -3,     /* chunk does not fit the span it must live in */
	HCU_RENDER_MEDIA_E_READ = -4,     /* read_range failed */
	HCU_RENDER_MEDIA_E_HASH = -5,     /* logical SHA-256 mismatch */
	HCU_RENDER_MEDIA_E_FORMAT = -6,   /* tex_open / lm_open refused the section */
	HCU_RENDER_MEDIA_E_STATE = -7
};

typedef struct { uint8_t *base; size_t bytes; } hcu_render_media_span;

typedef struct {
	int loaded;
	uint32_t bsp_index;
	uint8_t *bsps; size_t bsps_bytes;       /* inside the BSP span, 64-aligned */
	uint8_t *texs; size_t texs_bytes;       /* inside the texture span */
	uint8_t *lm;   size_t lm_bytes;         /* NULL / 0 when the BSP has no lightmap */
	size_t bsps_span_used, tex_span_used;   /* owner bytes charged, alignment included */
	tex_section tex;
	lm_section lightmap;
	int has_tex, has_lm;
	tex_source_t source;                    /* hand to bsp_render_set_world / bind_world */
} hcu_render_media;

/* `flush` (may be NULL) is called on each destination range after the read, for
 * D-cache write-back on the EE before DMA. */
typedef void (*hcu_render_media_flush_fn)(void *base, size_t bytes);

int hcu_render_media_load(hcu_render_media *m, const hcu_asset_profile_view *view,
	uint32_t bsp_index, hcu_render_media_span bsps, hcu_render_media_span tex,
	hcu_render_media_flush_fn flush);
/* C3:pack: sizes from the chunk directory only (no reads). bsps_bytes = BSPS size;
 * tex_bytes = TEXS padded to 64 + LMn (LMn is 0 when absent). */
int hcu_render_media_measure(const hcu_asset_profile_view *view, uint32_t bsp_index,
	size_t *bsps_bytes, size_t *tex_bytes);

/* C3:pack: tight layout inside one owner. BSPS at 0, TEX at align64(bsps_bytes),
 * the level arena at align64(tex_off + tex_bytes) with the rest of the owner.
 * Returns E_SPAN when the spans do not fit. */
typedef struct {
	size_t bsps_off, bsps_bytes;
	size_t tex_off, tex_bytes;
	size_t arena_off, arena_bytes;
} hcu_render_media_pack;
int hcu_render_media_pack_plan(size_t owner_bytes, size_t bsps_bytes, size_t tex_bytes,
	hcu_render_media_pack *out);

/* Forget the media. Call after the renderer and map-service reader have released it. */
void hcu_render_media_clear(hcu_render_media *m);

#ifdef __cplusplus
}
#endif
#endif
