#include "stream/hcu_render_world.h"

#include <string.h>

static int span_contains(hcu_render_world_span owner, const uint8_t *p, size_t bytes)
{
	uintptr_t lo, at;
	if (!owner.base || !p || bytes == 0 || owner.bytes == 0) return 0;
	lo = (uintptr_t)owner.base;
	at = (uintptr_t)p;
	if (at < lo) return 0;
	if (at - lo > owner.bytes) return 0;
	return bytes <= owner.bytes - (size_t)(at - lo);
}

int hcu_render_world_bind(hcu_render_world *w, hcu_map_service *service,
	hcu_render_world_span owner, const uint8_t *bsps, size_t bsps_bytes,
	const void *tex_source)
{
	const struct bsp_section *current_bsp = NULL;
	const void *current_source = NULL;
	uint32_t generation = 0;
	bsp_section section;

	if (!w || !service || !bsps || bsps_bytes == 0 || !tex_source)
		return HCU_RENDER_WORLD_E_ARGUMENT;
	if (w->bound) return HCU_RENDER_WORLD_E_STATE;
	if (((uintptr_t)bsps & 15u) != 0) return HCU_RENDER_WORLD_E_ARGUMENT;
	if (!span_contains(owner, bsps, bsps_bytes)) return HCU_RENDER_WORLD_E_SPAN;
	if (bsp_open(&section, bsps, bsps_bytes) != BSP_OK) return HCU_RENDER_WORLD_E_FORMAT;

	memset(w, 0, sizeof *w);
	/* Reader first: a refused reader (no owner, full table) leaves the service untouched. */
	if (!hcu_map_service_reader_acquire(service, HCU_MAP_READER_SOURCE_SPAN,
		bsps, (uint32_t)bsps_bytes, &w->reader))
		return HCU_RENDER_WORLD_E_READER;

	w->bsp = section;
	if (!hcu_map_service_bind_world(service, &w->bsp, tex_source)) {
		(void)hcu_map_service_reader_release(service, w->reader);
		memset(w, 0, sizeof *w);
		return HCU_RENDER_WORLD_E_SERVICE;
	}
	if (!hcu_map_service_current_world(service, &current_bsp, &current_source, &generation) ||
		current_bsp != &w->bsp || current_source != tex_source) {
		/* Cannot happen on a live service; the stored pointers are not trusted. */
		(void)hcu_map_service_reader_release(service, w->reader);
		memset(w, 0, sizeof *w);
		return HCU_RENDER_WORLD_E_SERVICE;
	}
	w->bytes = bsps;
	w->bytes_size = bsps_bytes;
	w->generation = generation;
	w->bound = 1;
	return HCU_RENDER_WORLD_OK;
}

int hcu_render_world_unbind(hcu_render_world *w, hcu_map_service *service)
{
	if (!w || !service) return HCU_RENDER_WORLD_E_ARGUMENT;
	if (!w->bound) return HCU_RENDER_WORLD_E_STATE;
	if (!hcu_map_service_reader_release(service, w->reader))
		return HCU_RENDER_WORLD_E_READER;
	memset(w, 0, sizeof *w);
	return HCU_RENDER_WORLD_OK;
}

int hcu_render_world_is_current(const hcu_render_world *w, const hcu_map_service *service)
{
	const struct bsp_section *bsp = NULL;
	const void *source = NULL;
	uint32_t generation = 0;
	if (!w || !service || !w->bound) return 0;
	if (!hcu_map_service_current_world(service, &bsp, &source, &generation)) return 0;
	return bsp == &w->bsp && generation == w->generation;
}

static const uint8_t *s_profile_bsps;
static size_t s_profile_bsps_bytes;

void hcu_render_world_publish_profile_bsps(const uint8_t *bsps, size_t bytes)
{
	s_profile_bsps = bytes ? bsps : NULL;
	s_profile_bsps_bytes = s_profile_bsps ? bytes : 0;
}

int hcu_render_world_profile_bsps(const hcu_map_service *service,
	const uint8_t **bsps, size_t *bytes)
{
	/* Returns the verified BSPS bytes that hcu_render_media_load placed in the
	 * caller-owned BSP span. Nothing is synthesized: a package built without
	 * --render-media leaves nothing published and this stays NO_PRODUCER. */
	(void)service;
	if (bsps) *bsps = s_profile_bsps;
	if (bytes) *bytes = s_profile_bsps_bytes;
	return s_profile_bsps ? HCU_RENDER_WORLD_OK : HCU_RENDER_WORLD_E_NO_PRODUCER;
}
