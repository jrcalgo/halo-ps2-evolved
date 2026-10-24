#ifndef HALO_STREAM_HCU_RENDER_TELEMETRY_H
#define HALO_STREAM_HCU_RENDER_TELEMETRY_H
/* Renderer owner samplers keep EE arenas separate from GS VRAM. The EE arena is sampled
 * directly; DMA and GS texture counters come from the renderer. Host tests supply those counters. */
#include "stream/hcu_owner_telemetry.h"
#include "core/mem.h"

/* The renderer reserves 17 texture-window pages below its texture cache (the CLUT pool and the
 * font page). They are resident for the whole binding, so the render-chunk store counts them. */
#define HCU_GS_TEXTURE_RESERVED_BYTES (17u * 8192u)

/* DMA (BACKING, 1,179,648 bytes): sums the geometry and upload pairs. `high` is the sum of the two
 * per-kind peaks, an upper bound on the peak of the sum. `resets` counts geometry rebuilds. */
int hcu_render_telemetry_sample_dma(void *ctx, hcu_owner_sample_t *out);
/* RENDER_CHUNKS (EE BACKING): the selected render arena's own counters. */
int hcu_render_telemetry_sample_render_chunks(void *ctx, hcu_owner_sample_t *out);
/* GS_WINDOW (GS BACKING) and GS_TEXTURE (nested in GS_WINDOW) are VRAM-space owners. */
int hcu_render_telemetry_sample_gs_window(void *ctx, hcu_owner_sample_t *out);
int hcu_render_telemetry_sample_gs_texture(void *ctx, hcu_owner_sample_t *out);

/* Registers DMA, the EE render arena, and GS-space samplers. The separate
 * RENDER_TEXTURE EE row intentionally remains unbound until it has a real EE owner. */
int hcu_render_telemetry_bind(hcu_owner_telemetry_t *t, const arena_t *ee_render_chunks);

#endif
