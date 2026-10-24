#include "stream/hcu_render_snapshot.h"

#include <math.h>
#include <stdio.h>
#include <string.h>

_Static_assert(sizeof(float) == 4, "CE render snapshots require 32-bit real");
_Static_assert(sizeof(halo_ps2_snapshot_matrix4x3) == HCU_CE_MATRIX4X3_BYTES,
	"snapshot wire matrix must match CE real_matrix4x3");

static halo_ps2_render_snapshot *s_snapshots[2];
static void *s_snapshot_storage;
static size_t s_snapshot_storage_bytes;
static uint32_t *s_dma_words;
static size_t s_dma_storage_bytes;
static int s_published_snapshot = -1;
static int s_writing_snapshot = -1;
static uint32_t s_dma_qwords;

#define HCU_DMA_MAX_MATRICES 64u
#define HCU_DMA_WORDS ((1u + HCU_DMA_MAX_MATRICES * 4u + 1u) * 4u)

static size_t align16_size(size_t value)
{
	return (value + 15u) & ~(size_t)15u;
}

size_t hcu_render_snapshot_storage_required(void)
{
	return align16_size(sizeof(halo_ps2_render_snapshot)) * 2u;
}

size_t hcu_render_snapshot_dma_storage_required(void)
{
	return HCU_DMA_WORDS * sizeof(uint32_t);
}

int hcu_render_snapshot_bind(void *frame_scratch, size_t frame_scratch_bytes,
	void *dma_commands, size_t dma_commands_bytes)
{
	size_t bank_bytes = align16_size(sizeof(halo_ps2_render_snapshot));
	if (!frame_scratch || !dma_commands ||
		((uintptr_t)frame_scratch & 15u) != 0u ||
		((uintptr_t)dma_commands & 15u) != 0u ||
		frame_scratch_bytes < hcu_render_snapshot_storage_required() ||
		dma_commands_bytes < hcu_render_snapshot_dma_storage_required())
		return -1;

	/* Binding is a boot-time operation. Refuse to invalidate pointers retained
	 * by a renderer; callers must explicitly unbind at a frame/map boundary. */
	if (s_snapshot_storage || s_dma_words)
		return -1;
	s_snapshot_storage = frame_scratch;
	s_snapshot_storage_bytes = frame_scratch_bytes;
	s_snapshots[0] = (halo_ps2_render_snapshot *)frame_scratch;
	s_snapshots[1] = (halo_ps2_render_snapshot *)
		((uint8_t *)frame_scratch + bank_bytes);
	memset(s_snapshots[0], 0, sizeof *s_snapshots[0]);
	memset(s_snapshots[1], 0, sizeof *s_snapshots[1]);
	s_dma_words = (uint32_t *)dma_commands;
	s_dma_storage_bytes = dma_commands_bytes;
	s_published_snapshot = -1;
	s_writing_snapshot = -1;
	s_dma_qwords = 0;
	return 0;
}

void hcu_render_snapshot_unbind(void)
{
	/* The owner must first stop CE and parent consumers. Clearing publication
	 * makes stale data unavailable before the arena can be rewound. */
	s_published_snapshot = -1;
	s_writing_snapshot = -1;
	s_snapshots[0] = NULL;
	s_snapshots[1] = NULL;
	s_snapshot_storage = NULL;
	s_snapshot_storage_bytes = 0;
	s_dma_words = NULL;
	s_dma_storage_bytes = 0;
	s_dma_qwords = 0;
}

halo_ps2_render_snapshot *halo_ps2_render_snapshot_begin(void)
{
	if (!s_snapshot_storage || s_snapshot_storage_bytes <
		hcu_render_snapshot_storage_required())
		return NULL;
	int next = s_published_snapshot == 0 ? 1 : 0;
	halo_ps2_render_snapshot *snapshot = s_snapshots[next];
	s_writing_snapshot = next;
	/* Reset the header/counts, not the large object tail. The producer must
	 * fill every record below object_count before commit. */
	memset(snapshot, 0, offsetof(halo_ps2_render_snapshot, objects));
	return snapshot;
}

static int finite_matrix(const halo_ps2_snapshot_matrix4x3 *matrix)
{
	float values[HCU_CE_MATRIX4X3_BYTES / sizeof(float)];
	memcpy(values, matrix, sizeof values);
	if (!isfinite(values[0]) || values[0] == 0.0f)
		return 0;
	{
		unsigned i;
		for (i = 1; i < HCU_CE_MATRIX4X3_BYTES / sizeof(float); ++i)
			if (!isfinite(values[i]))
				return 0;
	}
	return 1;
}

int halo_ps2_render_snapshot_commit(halo_ps2_render_snapshot *snapshot)
{
	unsigned i;
	uint32_t sequence;
	if (!snapshot || s_writing_snapshot < 0 ||
		snapshot != s_snapshots[s_writing_snapshot] ||
		snapshot->object_count > HALO_PS2_RENDER_MAX_OBJECTS ||
		snapshot->first_person_node_count >
			HALO_PS2_RENDER_MAX_FIRST_PERSON_NODES ||
		!isfinite(snapshot->time_delta_since_tick_sec) ||
		snapshot->time_delta_since_tick_sec < 0.0f)
		return -1;
	if (snapshot->local_player_index != -1)
	{
		const halo_ps2_snapshot_camera *camera = &snapshot->camera;
		if (!isfinite(camera->vertical_field_of_view) ||
			!isfinite(camera->z_near) || !isfinite(camera->z_far) ||
			camera->vertical_field_of_view <= 0.0f ||
			camera->vertical_field_of_view >= 3.1415927f ||
			camera->z_near <= 0.0f || camera->z_far <= camera->z_near)
			return -1;
		for (i = 0; i < 3; ++i)
			if (!isfinite(camera->position[i]) ||
				!isfinite(camera->forward[i]) || !isfinite(camera->up[i]))
				return -1;
	}
	for (i = 0; i < snapshot->first_person_node_count; ++i)
		if (!finite_matrix(&snapshot->first_person_nodes[i]))
			return -1;
	for (i = 0; i < snapshot->object_count; ++i)
		if (!finite_matrix(&snapshot->objects[i].world))
			return -1;
	sequence = s_published_snapshot < 0 ? 1u :
		s_snapshots[s_published_snapshot]->sequence + 1u;
	if (sequence == 0u)
		sequence = 1u;
	snapshot->sequence = sequence;
	s_published_snapshot = s_writing_snapshot;
	s_writing_snapshot = -1;
	return 0;
}

halo_ps2_render_snapshot const *halo_ps2_render_snapshot_latest(void)
{
	return s_published_snapshot >= 0 ?
		s_snapshots[s_published_snapshot] : NULL;
}

halo_ps2_render_snapshot const *hcu_render_snapshot_latest(void)
{
	return halo_ps2_render_snapshot_latest();
}

int hcu_render_snapshot_matrix_from_ce(const void *ce_matrix4x3,
	mat4 *out_world)
{
	float ce[13];
	mat4 converted;
	unsigned i, axis, component;

	if (!ce_matrix4x3 || !out_world)
		return -1;
	memcpy(ce, ce_matrix4x3, sizeof ce);
	for (i = 0; i < 13; ++i)
		if (!isfinite(ce[i]))
			return -1;

	/* CE real_matrix4x3 is { scale, forward[3], left[3], up[3],
	 * position[3] }. halo-ps2 mat4 stores each transformed basis image in a
	 * row and transforms p as x*m[0] + y*m[1] + z*m[2] + m[3]. */
	memset(&converted, 0, sizeof converted);
	for (axis = 0; axis < 3; ++axis)
		for (component = 0; component < 3; ++component) {
			float value = ce[1u + axis * 3u + component] * ce[0];
			if (!isfinite(value))
				return -1;
			converted.m[axis][component] = value;
		}
	for (component = 0; component < 3; ++component)
		converted.m[3][component] = ce[10u + component];
	converted.m[3][3] = 1.0f;
	*out_world = converted;
	return 0;
}

/* VIF unpack of V4-32 words. Same encoding as engine/src/render/gs.h. */
#define HCU_VIF_CODE(cmd, num, imm) \
	((uint32_t)(cmd) << 24 | (uint32_t)((num) & 0xFFu) << 16 | \
		(uint32_t)((imm) & 0xFFFFu))
#define HCU_VIF_NOP 0x00u
#define HCU_VIF_UNPACK_V4_32 0x6Cu

static int append_matrix(uint32_t *cursor, const void *ce_matrix)
{
	mat4 converted;
	if (hcu_render_snapshot_matrix_from_ce(ce_matrix, &converted) != 0)
		return -1;
	memcpy(cursor, &converted, sizeof converted);
	return 0;
}

int hcu_render_snapshot_publish_dma(void)
{
	const halo_ps2_render_snapshot *snapshot = hcu_render_snapshot_latest();
	uint32_t *payload;
	unsigned packed = 0;
	unsigned index;

	s_dma_qwords = 0;
	if (!s_dma_words || s_dma_storage_bytes <
		hcu_render_snapshot_dma_storage_required())
		return -1;
	if (!snapshot || snapshot->first_person_node_count +
		snapshot->object_count == 0) {
		static int logged_empty;
		if (!logged_empty) {
			logged_empty = 1;
			printf("HALO_PS2_LOCAL snapshot-dma qwords=0\n");
		}
		return 0;
	}
	/* The temporary packet currently contains one compact batch. Never emit a
	 * plausible-looking prefix when a view needs more than this batch can hold;
	 * the renderer must split large scenes into explicit batches. */
	if ((unsigned)snapshot->first_person_node_count +
		(unsigned)snapshot->object_count > HCU_DMA_MAX_MATRICES)
		return -1;
	payload = s_dma_words + 4;
	for (index = 0; index < snapshot->first_person_node_count &&
		packed < HCU_DMA_MAX_MATRICES; ++index, ++packed) {
		if (append_matrix(payload, &snapshot->first_person_nodes[index]) != 0)
			return -1;
		payload += 16;
	}
	for (index = 0; index < snapshot->object_count &&
		packed < HCU_DMA_MAX_MATRICES; ++index, ++packed) {
		if (append_matrix(payload, &snapshot->objects[index].world) != 0)
			return -1;
		payload += 16;
	}
	s_dma_words[0] = HCU_VIF_CODE(HCU_VIF_NOP, 0, 0);
	s_dma_words[1] = HCU_VIF_CODE(HCU_VIF_NOP, 0, 0);
	s_dma_words[2] = HCU_VIF_CODE(HCU_VIF_NOP, 0, 0);
	s_dma_words[3] = HCU_VIF_CODE(HCU_VIF_UNPACK_V4_32, packed * 4u, 0);
	s_dma_qwords = 1u + packed * 4u;
	{
		static int logged_packet;
		if (!logged_packet) {
			logged_packet = 1;
			printf("HALO_PS2_LOCAL snapshot-dma qwords=%u\n",
				(unsigned)s_dma_qwords);
		}
	}
	return (int)s_dma_qwords;
}

uint32_t const *hcu_render_snapshot_dma_words(void)
{
	return s_dma_words;
}

uint32_t hcu_render_snapshot_dma_qwords(void)
{
	return s_dma_qwords;
}
