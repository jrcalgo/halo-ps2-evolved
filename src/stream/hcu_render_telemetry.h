#ifndef HALO_STREAM_HCU_RENDER_TELEMETRY_H
#define HALO_STREAM_HCU_RENDER_TELEMETRY_H
/* C2.6/C2.7 renderer owner samplers. Each sampler reads the parent renderer's live DMA and
 * texture counters (render/bsp_render.c) and reports them in the owner-telemetry shape, so the
 * owner registry never copies renderer state. Pure C; the counters come from the EE renderer,
 * and host tests supply them. */
#include "stream/hcu_owner_telemetry.h"

/* The renderer reserves 17 texture-window pages below its texture cache (the CLUT pool and the
 * font page). They are resident for the whole binding, so the render-chunk store counts them. */
#define HCU_RENDER_TEXTURE_RESERVED_BYTES (17u * 8192u)

/* DMA (BACKING, 1,179,648 bytes): sums the geometry and upload pairs. `high` is the sum of the two
 * per-kind peaks, an upper bound on the peak of the sum. `resets` counts geometry rebuilds. */
int hcu_render_telemetry_sample_dma(void *ctx, hcu_owner_sample_t *out);
/* RENDER_CHUNKS (BACKING): the whole texture window, reserved pages plus the texture cache. */
int hcu_render_telemetry_sample_render_chunks(void *ctx, hcu_owner_sample_t *out);
/* RENDER_TEXTURE (NESTED in RENDER_CHUNKS): the texture cache's resident pages only. */
int hcu_render_telemetry_sample_texture(void *ctx, hcu_owner_sample_t *out);

/* Registers the three samplers. Returns 1 when all three were bound. */
int hcu_render_telemetry_bind(hcu_owner_telemetry_t *t);

#endif
