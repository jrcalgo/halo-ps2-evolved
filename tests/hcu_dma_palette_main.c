#include "core/mat.h"
#include "render/chain.h"
#include "sim/skeleton.h"

#include <assert.h>
#include <stdint.h>
#include <string.h>

/* Mirrors the inline chain layout used by render/obj_render.c:104-106:
 * CNT tag, 4-qword VIF header, five-qword node palette, 4-qword MSCAL tail. */
static uint32_t s_chain_words[64] __attribute__((aligned(16)));

int main(void)
{
	chain_t chain;
	mat4 node, clip;
	float light[3] = { 0.0f, 0.0f, -1.0f };
	float palette[5][4];
	uint32_t *payload;
	float *dma_palette;
	unsigned i;

	mat4_identity(&node);
	mat4_identity(&clip);
	node.m[3][0] = 10.0f;
	node.m[3][1] = -2.0f;
	node.m[3][2] = 4.0f;
	skel_palette_entry(palette, &node, clip.m, light);

	chain_init(&chain, s_chain_words, 64);
	payload = (uint32_t *)chain_cnt(&chain, 1 + 5 + 1, 0);
	assert(payload != NULL);
	/* Production renderer stores header first, then one 80-byte palette. */
	dma_palette = (float *)(payload + 4);
	assert(((uintptr_t)dma_palette & 15u) == 0);
	memcpy(dma_palette, palette, sizeof(palette));
	assert((uintptr_t)&s_chain_words[0] % 16u == 0);
	assert(chain_qwords(&chain) == 8);
	assert(dma_palette[12] == 10.0f && dma_palette[13] == -2.0f &&
		dma_palette[14] == 4.0f);
	for (i = 0; i < 20; ++i)
		assert(dma_palette[i] == ((float *)palette)[i]);
	return 0;
}
