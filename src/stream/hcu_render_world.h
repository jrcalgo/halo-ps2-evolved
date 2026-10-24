/* C3.world: production world source for the HCU parent renderer.
 *
 * The map service owns the mounted profile. This module binds one BSPS v2
 * section (world/bsp.h) that lives in a caller-owned span inside that owner,
 * publishes it through hcu_map_service_bind_world, and holds a SOURCE_SPAN
 * reader on the section bytes so CE dispose waits until the renderer releases
 * the world. It never allocates; every byte it touches is in the span it is
 * given. Host-testable: no EE or renderer headers are needed. */
#ifndef HALO_STREAM_HCU_RENDER_WORLD_H
#define HALO_STREAM_HCU_RENDER_WORLD_H

#include <stddef.h>
#include <stdint.h>

#include "world/bsp.h"
#include "stream/hcu_map_service.h"

#ifdef __cplusplus
extern "C" {
#endif

enum {
	HCU_RENDER_WORLD_OK = 0,
	HCU_RENDER_WORLD_E_ARGUMENT = -1,
	HCU_RENDER_WORLD_E_SPAN = -2,      /* bytes are not inside the caller-owned span */
	HCU_RENDER_WORLD_E_FORMAT = -3,    /* bsp_open rejected the section */
	HCU_RENDER_WORLD_E_SERVICE = -4,   /* no owner mounted, or bind refused */
	HCU_RENDER_WORLD_E_READER = -5,    /* reader table full or owner not live */
	HCU_RENDER_WORLD_E_STATE = -6,     /* already bound, or not bound */
	HCU_RENDER_WORLD_E_NO_PRODUCER = -7 /* the profile package carries no BSPS section */
};

typedef struct {
	const uint8_t *base;
	size_t bytes;
} hcu_render_world_span;

typedef struct {
	bsp_section bsp;                 /* valid while bound; points into the bound bytes */
	const uint8_t *bytes;           /* BSPS bytes, inside the owner span */
	size_t bytes_size;
	hcu_map_reader_ref reader;      /* SOURCE_SPAN reader on bytes; blocks CE dispose */
	uint32_t generation;            /* map boundary count at bind time */
	int bound;
} hcu_render_world;

/* Validates the BSPS bytes (bsp_open), registers a SOURCE_SPAN reader, then
 * publishes bsp and tex_source through hcu_map_service_bind_world. The reader
 * is acquired first, so a failure leaves the service unchanged. `tex_source` is
 * the renderer's tex_source_t (an opaque pointer here, so the host build needs
 * no render headers); pass a texture_count of 0 source for a flat world. */
int hcu_render_world_bind(hcu_render_world *w, hcu_map_service *service,
	hcu_render_world_span owner, const uint8_t *bsps, size_t bsps_bytes,
	const void *tex_source);

/* Releases the reader. Call before the renderer stops reading and before the
 * owner's storage is released. The service clears its world pointers when the
 * owner releases; this module does not clear them. */
int hcu_render_world_unbind(hcu_render_world *w, hcu_map_service *service);

/* Nonzero while the bound world is still the service's current world for the
 * same map generation. */
int hcu_render_world_is_current(const hcu_render_world *w, const hcu_map_service *service);

/* Producer seam: the BSPS bytes for the mounted profile. The profile package
 * does not carry a BSPS section today (CBSP and BITM only), so this returns
 * HCU_RENDER_WORLD_E_NO_PRODUCER and writes NULL outputs. See the report for the
 * smallest producer change. */
int hcu_render_world_profile_bsps(const hcu_map_service *service,
	const uint8_t **bsps, size_t *bytes);

#ifdef __cplusplus
}
#endif
#endif
