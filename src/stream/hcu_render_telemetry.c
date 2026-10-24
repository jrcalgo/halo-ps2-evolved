/* port: C2.6/C2.7 renderer owner samplers (see hcu_render_telemetry.h). */
#include "stream/hcu_render_telemetry.h"
#include "render/storage.h"

static void from_counters(hcu_owner_sample_t *out, const bsp_render_owner_counters *c)
{
    out->capacity = c->capacity;
    out->used = c->used;
    out->high = c->high_water;
    out->failures = c->failures;
    out->resets = c->resets;
}

int hcu_render_telemetry_sample_dma(void *ctx, hcu_owner_sample_t *out)
{
    bsp_render_owner_counters g, u;
    (void)ctx;
    if (!out || bsp_render_dma_counters(&g, &u) != 0)
        return 0;
    out->capacity = (size_t)g.capacity + u.capacity;
    out->used = (size_t)g.used + u.used;
    out->high = (size_t)g.high_water + u.high_water;
    out->failures = g.failures + u.failures;
    out->resets = g.resets;
    return 1;
}

int hcu_render_telemetry_sample_texture(void *ctx, hcu_owner_sample_t *out)
{
    bsp_render_owner_counters t;
    (void)ctx;
    if (!out || bsp_render_texcache_counters(&t) != 0)
        return 0;
    from_counters(out, &t);
    return 1;
}

int hcu_render_telemetry_sample_render_chunks(void *ctx, hcu_owner_sample_t *out)
{
    bsp_render_owner_counters t;
    (void)ctx;
    if (!out || bsp_render_texcache_counters(&t) != 0)
        return 0;
    from_counters(out, &t);
    out->capacity += HCU_RENDER_TEXTURE_RESERVED_BYTES;
    out->used += HCU_RENDER_TEXTURE_RESERVED_BYTES;
    out->high += HCU_RENDER_TEXTURE_RESERVED_BYTES;
    return 1;
}

int hcu_render_telemetry_bind(hcu_owner_telemetry_t *t)
{
    int ok = 1;
    if (!t)
        return 0;
    ok &= hcu_owner_telemetry_bind_sampler(t, HCU_OWNER_DMA, hcu_render_telemetry_sample_dma, NULL) != 0;
    ok &= hcu_owner_telemetry_bind_sampler(t, HCU_OWNER_RENDER_CHUNKS, hcu_render_telemetry_sample_render_chunks, NULL) != 0;
    ok &= hcu_owner_telemetry_bind_sampler(t, HCU_OWNER_RENDER_TEXTURE, hcu_render_telemetry_sample_texture, NULL) != 0;
    return ok;
}
