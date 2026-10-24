/* Host test for the renderer owner samplers (src/stream/hcu_render_telemetry.c). The EE renderer's
 * counters are replaced by the fixtures below, so the sampler arithmetic and the owner registry are
 * checked without the EE. */
#include "stream/hcu_render_telemetry.h"
#include "render/storage.h"

#include <assert.h>
#include <stdio.h>

static bsp_render_owner_counters s_geom, s_upload, s_tex;
static int s_dma_status, s_tex_status;
static unsigned char s_ee_render_storage[65536];

int bsp_render_dma_counters(bsp_render_owner_counters *g, bsp_render_owner_counters *u)
{
	if (!g || !u) return -1;
	*g = s_geom;
	*u = s_upload;
	return s_dma_status;
}

int bsp_render_texcache_counters(bsp_render_owner_counters *out)
{
	if (!out) return -1;
	*out = s_tex;
	return s_tex_status;
}

int main(void)
{
	hcu_owner_telemetry_t telemetry;
	hcu_owner_sample_t sample;
	hcu_owner_report_t report;
	arena_t ee_render = {0};

	/* Fixture: both geometry chains full-capacity, one upload chain half used. */
	s_geom.capacity = 1048576u; s_geom.used = 65536u; s_geom.high_water = 524288u;
	s_geom.failures = 2u; s_geom.resets = 40u;
	s_upload.capacity = 131072u; s_upload.used = 4096u; s_upload.high_water = 65536u;
	s_upload.failures = 0u; s_upload.resets = 40u;
	s_tex.capacity = 1048576u; s_tex.used = 524288u; s_tex.high_water = 786432u;
	s_tex.failures = 3u; s_tex.resets = 5u;
	s_dma_status = 0;
	s_tex_status = 0;

	/* DMA: the two kinds sum to the 1,179,648-byte owner. */
	assert(hcu_render_telemetry_sample_dma(NULL, &sample) == 1);
	assert(sample.capacity == 1179648u);
	assert(sample.used == 69632u);
	assert(sample.high == 589824u);
	assert(sample.failures == 2u);
	assert(sample.resets == 40u);

	/* EE render arena samples its own allocator counters. */
	ee_render.base = s_ee_render_storage;
	ee_render.cap = sizeof s_ee_render_storage;
	ee_render.used = 16384u;
	ee_render.high = 32768u;
	ee_render.failed_allocations = 2u;
	ee_render.reset_count = 3u;
	assert(hcu_render_telemetry_sample_render_chunks(&ee_render, &sample) == 1);
	assert(sample.capacity == sizeof s_ee_render_storage);
	assert(sample.used == 16384u && sample.high == 32768u);
	assert(sample.failures == 2u && sample.resets == 3u);
	assert(hcu_render_telemetry_sample_render_chunks(NULL, &sample) == 0);

	/* GS texture cache is separate; the whole GS window includes reserved pages. */
	assert(hcu_render_telemetry_sample_gs_texture(NULL, &sample) == 1);
	assert(sample.capacity == 1048576u);
	assert(sample.used == 524288u);
	assert(sample.high == 786432u);
	assert(sample.failures == 3u);
	assert(sample.resets == 5u);

	assert(HCU_GS_TEXTURE_RESERVED_BYTES == 139264u);
	assert(hcu_render_telemetry_sample_gs_window(NULL, &sample) == 1);
	assert(sample.capacity == 1048576u + 139264u);
	assert(sample.used == 524288u + 139264u);
	assert(sample.high == 786432u + 139264u);
	assert(sample.failures == 3u);

	/* Unbound renderer: samplers report nothing. */
	s_dma_status = -1;
	s_tex_status = -1;
	assert(hcu_render_telemetry_sample_dma(NULL, &sample) == 0);
	assert(hcu_render_telemetry_sample_gs_texture(NULL, &sample) == 0);
	assert(hcu_render_telemetry_sample_gs_window(NULL, &sample) == 0);
	assert(hcu_render_telemetry_sample_dma(NULL, NULL) == 0);
	s_dma_status = 0;
	s_tex_status = 0;

	/* Registry: EE backing totals count DMA and the actual EE arena; GS totals stay separate. */
	hcu_owner_telemetry_init(&telemetry);
	assert(hcu_render_telemetry_bind(&telemetry, &ee_render) == 1);
	assert(hcu_render_telemetry_bind(NULL, &ee_render) == 0);
	assert(hcu_render_telemetry_bind(&telemetry, NULL) == 0);
	assert(hcu_owner_telemetry_snapshot(&telemetry, &report) != 0);
	assert(report.rows[HCU_OWNER_DMA].bound);
	assert(report.rows[HCU_OWNER_RENDER_CHUNKS].bound);
	assert(!report.rows[HCU_OWNER_RENDER_TEXTURE].bound);
	assert(report.rows[HCU_OWNER_RENDER_CHUNKS].domain == HCU_OWNER_DOMAIN_EE);
	assert(report.rows[HCU_OWNER_GS_WINDOW].bound);
	assert(report.rows[HCU_OWNER_GS_WINDOW].domain == HCU_OWNER_DOMAIN_GS);
	assert(report.rows[HCU_OWNER_GS_TEXTURE].bound);
	assert(report.rows[HCU_OWNER_GS_TEXTURE].kind == HCU_OWNER_KIND_NESTED);
	assert(report.rows[HCU_OWNER_GS_TEXTURE].parent == HCU_OWNER_GS_WINDOW);
	assert(report.nested_within_parent);
	assert(report.backing_capacity == 1179648u + sizeof s_ee_render_storage);
	assert(report.gs_capacity == 1048576u + HCU_GS_TEXTURE_RESERVED_BYTES);
	assert(report.backing_used == 69632u + 16384u);
	assert(report.gs_used == 524288u + HCU_GS_TEXTURE_RESERVED_BYTES);

	/* A GS occupancy change cannot alter the EE sum or the render_chunks row. */
	s_tex.used = 4096u;
	s_tex.high_water = 8192u;
	assert(hcu_owner_telemetry_snapshot(&telemetry, &report));
	assert(report.backing_capacity == 1179648u + sizeof s_ee_render_storage);
	assert(report.backing_used == 69632u + 16384u);
	assert(report.rows[HCU_OWNER_RENDER_CHUNKS].sample.used == 16384u);
	assert(report.gs_used == 4096u + HCU_GS_TEXTURE_RESERVED_BYTES);
	printf("render dma telemetry: PASSED\n");
	return 0;
}
