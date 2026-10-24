#include "render/storage.h"

#include <assert.h>
#include <stdint.h>
#include <string.h>

static uint8_t s_dma[BSP_RENDER_DMA_STORAGE_BYTES + 64u] __attribute__((aligned(64)));

int main(void)
{
	bsp_render_chain_storage storage;
	uintptr_t base = (uintptr_t)s_dma;
	assert(BSP_RENDER_DMA_STORAGE_BYTES == 1179648u);
	assert(bsp_render_chain_storage_layout(&storage, s_dma,
		BSP_RENDER_DMA_STORAGE_BYTES, 0, 0) == 0);
	assert((uintptr_t)storage.geometry[0] == base);
	assert((uintptr_t)storage.geometry[1] == base + 32768u * 16u);
	assert((uintptr_t)storage.upload[0] == base + 2u * 32768u * 16u);
	assert((uintptr_t)storage.upload[1] == base + (2u * 32768u + 4096u) * 16u);
	assert((uintptr_t)storage.upload[1] + 4096u * 16u ==
		base + BSP_RENDER_DMA_STORAGE_BYTES);
	assert(bsp_render_chain_storage_layout(&storage, s_dma + 1,
		BSP_RENDER_DMA_STORAGE_BYTES, 0, 0) == -1);
	assert(bsp_render_chain_storage_layout(&storage, s_dma,
		BSP_RENDER_DMA_STORAGE_BYTES - 16u, 0, 0) == -1);
	assert(bsp_render_chain_storage_layout(&storage, s_dma,
		BSP_RENDER_DMA_STORAGE_BYTES + 16u, 0, 0) == -1);
	assert(bsp_render_chain_storage_layout(&storage, s_dma,
		BSP_RENDER_DMA_STORAGE_BYTES, 1, 0) == -1);
	assert(bsp_render_chain_storage_layout(&storage, s_dma,
		BSP_RENDER_DMA_STORAGE_BYTES, 0, 1) == -1);
	assert(bsp_render_chain_storage_layout(&storage,
		(void *)(UINTPTR_MAX - 63u), BSP_RENDER_DMA_STORAGE_BYTES, 0, 0) == -1);

	/* Chain sizes and the four exact spans: two 32768-qw geometry and two 4096-qw upload chains. */
	assert(BSP_RENDER_GEOMETRY_CHAIN_QW == 32768u);
	assert(BSP_RENDER_UPLOAD_CHAIN_QW == 4096u);
	assert(2u * BSP_RENDER_GEOMETRY_CHAIN_QW * 16u == 1048576u);
	assert(2u * BSP_RENDER_UPLOAD_CHAIN_QW * 16u == 131072u);
	assert(BSP_RENDER_DMA_STORAGE_BYTES == 1179648u);
	assert(bsp_render_chain_storage_layout(&storage, s_dma,
		BSP_RENDER_DMA_STORAGE_BYTES, 0, 0) == 0);
	assert((uintptr_t)storage.geometry[1] - (uintptr_t)storage.geometry[0] == 32768u * 16u);
	assert((uintptr_t)storage.upload[0] - (uintptr_t)storage.geometry[1] == 32768u * 16u);
	assert((uintptr_t)storage.upload[1] - (uintptr_t)storage.upload[0] == 4096u * 16u);

	/* Frame-scratch packet workspace: init/environment/font packets have owners in [0,5632). */
	assert(BSP_RENDER_WORKSPACE_BYTES == 5632u);
	assert(BSP_RENDER_VIF_PROGRAM_OFFSET == 0u);
	assert(BSP_RENDER_VIF_PROGRAM_BYTES == 4096u);
	assert(BSP_RENDER_ENV_PACKET_OFFSET == 4096u);
	assert(BSP_RENDER_ENV_PACKET_BYTES == 1024u);     /* 64 qw, the environment packet's max_qwords_count */
	assert(BSP_RENDER_FONT_PACKET_OFFSET == 5120u);
	assert(BSP_RENDER_FONT_PACKET_BYTES == 512u);    /* 32 qw, the font atlas upload packet */
	assert(BSP_RENDER_VIF_PROGRAM_OFFSET + BSP_RENDER_VIF_PROGRAM_BYTES == BSP_RENDER_ENV_PACKET_OFFSET);
	assert(BSP_RENDER_ENV_PACKET_OFFSET + BSP_RENDER_ENV_PACKET_BYTES == BSP_RENDER_FONT_PACKET_OFFSET);
	assert(BSP_RENDER_FONT_PACKET_OFFSET + BSP_RENDER_FONT_PACKET_BYTES == BSP_RENDER_WORKSPACE_BYTES);

	/* Idle-chain rule: with no kick in flight either chain may be built; with a kick in flight the
	 * build must take the other chain. Indices other than 0 and 1 are never idle. */
	assert(bsp_render_chain_is_idle(0, 0, 0));
	assert(bsp_render_chain_is_idle(1, 0, 0));
	assert(bsp_render_chain_is_idle(1, 1, 0));
	assert(bsp_render_chain_is_idle(0, 1, 1));
	assert(!bsp_render_chain_is_idle(0, 1, 0));
	assert(!bsp_render_chain_is_idle(1, 1, 1));
	assert(!bsp_render_chain_is_idle(2, 1, 0));
	assert(!bsp_render_chain_is_idle(0, 1, 2));

	/* A frame loop that alternates build and kick never has its build on the in-flight chain. */
	{
		uint32_t build = 0, kick = 0;
		int inflight = 0;
		unsigned frame;
		for (frame = 0; frame < 64; frame++) {
			build ^= 1u;
			if (!bsp_render_chain_is_idle(build, inflight, kick))
				build ^= 1u;
			assert(bsp_render_chain_is_idle(build, inflight, kick));
			kick = build;
			inflight = 1;
		}
	}
	return 0;
}
