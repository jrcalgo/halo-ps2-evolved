/* Host test for the renderer owner samplers (src/stream/hcu_render_telemetry.c). The EE renderer's
 * counters are replaced by the fixtures below, so the sampler arithmetic and the owner registry are
 * checked without the EE. */
#include "stream/hcu_render_telemetry.h"
#include "render/storage.h"

#include <assert.h>
#include <stdio.h>

static bsp_render_owner_counters s_geom, s_upload, s_tex;
static int s_dma_status, s_tex_status;

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

	/* Texture is nested: its own pages only. */
	assert(hcu_render_telemetry_sample_texture(NULL, &sample) == 1);
	assert(sample.capacity == 1048576u);
	assert(sample.used == 524288u);
	assert(sample.high == 786432u);
	assert(sample.failures == 3u);
	assert(sample.resets == 5u);

	/* Render chunks: the texture window adds the 17 reserved pages. */
	assert(HCU_RENDER_TEXTURE_RESERVED_BYTES == 139264u);
	assert(hcu_render_telemetry_sample_render_chunks(NULL, &sample) == 1);
	assert(sample.capacity == 1048576u + 139264u);
	assert(sample.used == 524288u + 139264u);
	assert(sample.high == 786432u + 139264u);
	assert(sample.failures == 3u);

	/* Unbound renderer: samplers report nothing. */
	s_dma_status = -1;
	s_tex_status = -1;
	assert(hcu_render_telemetry_sample_dma(NULL, &sample) == 0);
	assert(hcu_render_telemetry_sample_texture(NULL, &sample) == 0);
	assert(hcu_render_telemetry_sample_render_chunks(NULL, &sample) == 0);
	assert(hcu_render_telemetry_sample_dma(NULL, NULL) == 0);
	s_dma_status = 0;
	s_tex_status = 0;

	/* Registry: all three owners bind, and the BACKING totals count DMA and render chunks, not the
	 * nested texture owner. */
	hcu_owner_telemetry_init(&telemetry);
	assert(hcu_render_telemetry_bind(&telemetry) == 1);
	assert(hcu_render_telemetry_bind(NULL) == 0);
	assert(hcu_owner_telemetry_snapshot(&telemetry, &report) != 0);
	assert(report.rows[HCU_OWNER_DMA].bound);
	assert(report.rows[HCU_OWNER_RENDER_CHUNKS].bound);
	assert(report.rows[HCU_OWNER_RENDER_TEXTURE].bound);
	assert(report.rows[HCU_OWNER_RENDER_TEXTURE].kind == HCU_OWNER_KIND_NESTED);
	assert(report.rows[HCU_OWNER_RENDER_TEXTURE].parent == HCU_OWNER_RENDER_CHUNKS);
	assert(report.nested_within_parent);
	assert(report.backing_capacity == 1179648u + 1048576u + 139264u);
	printf("render dma telemetry: PASSED\n");
	return 0;
}
