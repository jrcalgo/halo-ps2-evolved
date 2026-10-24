#include "core/mat.h"
#include "render/chain.h"
#include "sim/skeleton.h"
#include "stream/hcu_render_snapshot.h"

#include <assert.h>
#include <math.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

/* Compile the test against the actual pinned HCU matrix declaration without
 * pulling in its machine runtime. These type aliases match cseries.h. */
typedef float real;
typedef unsigned char byte;
typedef unsigned char boolean;
typedef unsigned short word;
typedef unsigned long dword;
#define TRUE 1
#define FALSE 0
#define NONE -1
#define _x 0
#define _y 1
#define _z 2
#define __inline static inline
#define match_assert(file, line, condition) ((void)0)
#define PIN(value, low, high) ((value) < (low) ? (low) : \
	((value) > (high) ? (high) : (value)))
#include "math/real_math.h"

_Static_assert(sizeof(real_matrix4x3) == HCU_CE_MATRIX4X3_BYTES,
	"pinned CE real_matrix4x3 wire size changed");
_Static_assert(offsetof(real_matrix4x3, scale) == 0 &&
	offsetof(real_matrix4x3, forward) == 4 &&
	offsetof(real_matrix4x3, left) == 16 &&
	offsetof(real_matrix4x3, up) == 28 &&
	offsetof(real_matrix4x3, position) == 40,
	"pinned CE real_matrix4x3 wire offsets changed");

static uint32_t s_chain_words[64] __attribute__((aligned(16)));
static uint32_t s_emit_words[1u + 64u * 4u][4] __attribute__((aligned(16)));
static uint8_t s_snapshot_storage[
	((sizeof(halo_ps2_render_snapshot) + 15u) & ~(size_t)15u) * 2u]
	__attribute__((aligned(16)));
static halo_ps2_render_snapshot s_snapshot_copy;

static int emit_latest(void)
{
	chain_t chain;
	chain_init(&chain, s_emit_words, 1u + 64u * 4u);
	return hcu_render_snapshot_emit_chain(&chain);
}

static void near(float actual, float expected)
{
	if (!(fabsf(actual - expected) < 0.0001f))
		fprintf(stderr, "near mismatch actual=%f expected=%f\n", actual, expected);
	assert(fabsf(actual - expected) < 0.0001f);
}

int main(void)
{
	real_matrix4x3 ce = { 0 };
	halo_ps2_render_snapshot *snapshot;
	halo_ps2_render_snapshot const *published;
	mat4 node, clip;
	float point[3] = { 3.0f, 4.0f, 5.0f }, transformed[3];
	float light[3] = { 0.0f, 0.0f, -1.0f }, palette[5][4];
	uint32_t *payload;
	float *dma_palette;
	chain_t chain;
	unsigned char simulation_state[128];
	unsigned char simulation_before[sizeof simulation_state];
	unsigned player;

	assert(hcu_render_snapshot_storage_required() == sizeof s_snapshot_storage);
	assert(hcu_render_snapshot_storage_required() <= 393216u);
	assert(halo_ps2_render_snapshot_begin() == NULL);
	assert(hcu_render_snapshot_bind((uint8_t *)s_snapshot_storage + 1,
		sizeof s_snapshot_storage - 1) == -1);
	assert(hcu_render_snapshot_bind(s_snapshot_storage,
		sizeof s_snapshot_storage - 1) == -1);
	assert(hcu_render_snapshot_bind(s_snapshot_storage,
		sizeof s_snapshot_storage) == 0);
	assert(hcu_render_snapshot_bind(s_snapshot_storage,
		sizeof s_snapshot_storage) == -1);

	ce.scale = 2.0f;
	ce.forward.i = 0.0f; ce.forward.j = 1.0f; ce.forward.k = 0.0f;
	ce.left.i = -1.0f; ce.left.j = 0.0f; ce.left.k = 0.0f;
	ce.up.i = 0.0f; ce.up.j = 0.0f; ce.up.k = 1.0f;
	ce.position.x = 10.0f; ce.position.y = -2.0f; ce.position.z = 4.0f;
	assert(hcu_render_snapshot_matrix_from_ce(&ce, &node) == 0);
	mat4_transform_point(&node, point, transformed);
	/* CE matrix4x3_transform_point() semantics, including matrix scale. */
	near(transformed[0], 2.0f);
	near(transformed[1], 4.0f);
	near(transformed[2], 14.0f);
	near(node.m[3][0], ce.position.x);
	near(node.m[3][1], ce.position.y);
	near(node.m[3][2], ce.position.z);

	mat4_identity(&clip);
	skel_palette_entry(palette, &node, clip.m, light);
	chain_init(&chain, s_chain_words, 64);
	payload = (uint32_t *)chain_cnt(&chain, 1 + 5 + 1, 0);
	assert(payload != NULL);
	dma_palette = (float *)(payload + 4);
	assert(((uintptr_t)dma_palette & 15u) == 0);
	memcpy(dma_palette, palette, sizeof palette);
	assert(chain_qwords(&chain) == 8);
	near(dma_palette[12], 10.0f);
	near(dma_palette[13], -2.0f);
	near(dma_palette[14], 4.0f);

	ce.scale = NAN;
	assert(hcu_render_snapshot_matrix_from_ce(&ce, &node) == -1);
	assert(hcu_render_snapshot_matrix_from_ce(NULL, &node) == -1);
	assert(hcu_render_snapshot_matrix_from_ce(&ce, NULL) == -1);

	/* Exercise the same two-bank pointer-free publication API the CE PS2
	 * render adapter calls, including immutability of the previous frame. */
	snapshot = halo_ps2_render_snapshot_begin();
	assert(snapshot != NULL);
	snapshot->frame_index = 10;
	snapshot->time_delta_since_tick_sec = 1.0f / 30.0f;
	snapshot->window_index = 0;
	snapshot->local_player_index = 0;
	snapshot->camera.forward[0] = 1.0f;
	snapshot->camera.up[2] = 1.0f;
	snapshot->camera.vertical_field_of_view = 1.2f;
	snapshot->camera.z_near = 0.1f;
	snapshot->camera.z_far = 1000.0f;
	snapshot->object_count = 1;
	snapshot->objects[0].datum_index = 0x10001u;
	snapshot->objects[0].definition_index = 12;
	snapshot->objects[0].type = 5;
	snapshot->objects[0].world.scale = 1.0f;
	snapshot->objects[0].world.forward[0] = 1.0f;
	snapshot->objects[0].world.left[1] = 1.0f;
	snapshot->objects[0].world.up[2] = 1.0f;
	assert(halo_ps2_render_snapshot_commit(snapshot) == 0);
	published = hcu_render_snapshot_latest();
	assert(published != NULL && published->sequence == 1);
	assert(published->frame_index == 10 && published->object_count == 1);
	assert(published->objects[0].datum_index == 0x10001u);

	snapshot = halo_ps2_render_snapshot_begin();
	assert(snapshot != NULL && snapshot != published);
	snapshot->frame_index = 11;
	snapshot->time_delta_since_tick_sec = 1.0f / 60.0f;
	snapshot->local_player_index = -1;
	assert(halo_ps2_render_snapshot_commit(snapshot) == 0);
	assert(published->sequence == 1 && published->frame_index == 10);
	assert(hcu_render_snapshot_latest()->sequence == 2);

	snapshot = halo_ps2_render_snapshot_begin();
	snapshot->object_count = HALO_PS2_RENDER_MAX_OBJECTS + 1u;
	assert(halo_ps2_render_snapshot_commit(snapshot) == -1);
	assert(hcu_render_snapshot_latest()->sequence == 2);
	/* A single bounded pair of banks is reused for all local views. The latest
	 * view is immutable until the second subsequent publication; no per-view
	 * heap allocation or map-arena pointer is retained. */
	memset(simulation_state, 0x5a, sizeof simulation_state);
	memcpy(simulation_before, simulation_state, sizeof simulation_state);
	for (player = 0; player < 4; ++player) {
		snapshot = halo_ps2_render_snapshot_begin();
		assert(snapshot != NULL);
		snapshot->frame_index = 40;
		snapshot->time_delta_since_tick_sec = 1.0f / 30.0f;
		snapshot->window_index = (int16_t)player;
		snapshot->local_player_index = (int16_t)player;
		snapshot->camera.forward[0] = 1.0f;
		snapshot->camera.up[2] = 1.0f;
		snapshot->camera.vertical_field_of_view = 1.2f;
		snapshot->camera.z_near = 0.1f;
		snapshot->camera.z_far = 1000.0f;
		snapshot->object_count = 1;
		snapshot->objects[0].datum_index = 0x10001u;
		snapshot->objects[0].world.scale = 1.0f;
		snapshot->objects[0].world.forward[0] = 1.0f;
		snapshot->objects[0].world.left[1] = 1.0f;
		snapshot->objects[0].world.up[2] = 1.0f;
		assert(halo_ps2_render_snapshot_commit(snapshot) == 0);
		published = hcu_render_snapshot_latest();
		assert(published->local_player_index == (int16_t)player);
		assert((const uint8_t *)published >= s_snapshot_storage &&
			(const uint8_t *)(published + 1) <=
			(const uint8_t *)s_snapshot_storage + sizeof s_snapshot_storage);
		assert(memcmp(simulation_state, simulation_before,
			sizeof simulation_state) == 0);
	}
	/* Parent-side packet packing may be skipped, performed once, or repeated;
	 * it is a read-only consumer and must not change either the published bytes
	 * or the stand-in authoritative state. This is not a linked CE tick test. */
	published = hcu_render_snapshot_latest();
	memcpy(&s_snapshot_copy, published, sizeof s_snapshot_copy);
	for (player = 0; player <= 2; ++player) {
		unsigned presentation;
		for (presentation = 0; presentation < player; ++presentation)
			assert(emit_latest() == 5);
		assert(memcmp(published, &s_snapshot_copy,
			sizeof s_snapshot_copy) == 0);
		assert(memcmp(simulation_state, simulation_before,
			sizeof simulation_state) == 0);
	}
	assert(emit_latest() == 5);
	snapshot = halo_ps2_render_snapshot_begin();
	snapshot->time_delta_since_tick_sec = 0.0f;
	snapshot->local_player_index = -1;
	snapshot->object_count = 1;
	snapshot->objects[0].world.scale = 2.0f;
	snapshot->objects[0].world.forward[0] = 0.0f;
	snapshot->objects[0].world.forward[1] = 1.0f;
	snapshot->objects[0].world.left[0] = -1.0f;
	snapshot->objects[0].world.up[2] = 1.0f;
	snapshot->objects[0].world.position[0] = 10.0f;
	snapshot->objects[0].world.position[1] = -2.0f;
	snapshot->objects[0].world.position[2] = 4.0f;
	assert(halo_ps2_render_snapshot_commit(snapshot) == 0);
	assert(emit_latest() == 5);
	assert(((uintptr_t)s_emit_words & 15u) == 0);
	assert(((uint64_t *)s_emit_words)[0] ==
		((uint64_t)4u | (uint64_t)DMA_ID_CNT << 28));
	assert((uint32_t)((uint64_t *)s_emit_words)[1] == 0u); /* VIF0 NOP */
	assert((uint32_t)(((uint64_t *)s_emit_words)[1] >> 32) ==
		((uint32_t)0x6Cu << 24 | 4u << 16)); /* VIF1 UNPACK V4-32 */
	dma_palette = (float *)(s_emit_words[1]);
	/* The first payload word follows both TTE VIF codes; it is matrix data,
	 * proving UNPACK did not consume a low-word NOP as the first float. */
	near(dma_palette[0], 0.0f);
	near(dma_palette[1], 2.0f);
	near(dma_palette[12], 10.0f);
	near(dma_palette[13], -2.0f);
	near(dma_palette[14], 4.0f);
	chain_init(&chain, s_chain_words, 4);
	assert(hcu_render_snapshot_emit_chain(&chain) == -1);
	assert(chain.qw == 0 && chain.overflow == 1);
	/* Reject a valid full object snapshot when the one-batch diagnostic DMA
	 * packet cannot represent it; do not silently publish a truncated prefix. */
	snapshot = halo_ps2_render_snapshot_begin();
	assert(snapshot != NULL);
	snapshot->local_player_index = -1;
	snapshot->time_delta_since_tick_sec = 0.0f;
	snapshot->object_count = 65;
	for (player = 0; player < snapshot->object_count; ++player) {
		snapshot->objects[player].world.scale = 1.0f;
		snapshot->objects[player].world.forward[0] = 1.0f;
		snapshot->objects[player].world.left[1] = 1.0f;
		snapshot->objects[player].world.up[2] = 1.0f;
	}
	assert(halo_ps2_render_snapshot_commit(snapshot) == 0);
	assert(emit_latest() == -1);
	hcu_render_snapshot_unbind();
	assert(hcu_render_snapshot_latest() == NULL);
	assert(emit_latest() == -1);
	return 0;
}
