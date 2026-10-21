/* Pointer-free CPU snapshot boundary from CE transform records to halo-ps2.
 * The input is the pinned CE real_matrix4x3 wire layout (13 IEEE-754 floats,
 * 52 bytes); callers pass object_get_node_matrix() data only after the CE tick. */
#ifndef HCU_RENDER_SNAPSHOT_H
#define HCU_RENDER_SNAPSHOT_H

#include "core/mat.h"
#include "halo_ps2_render_snapshot.h"

#include <stddef.h>

#define HCU_CE_MATRIX4X3_BYTES 52u

/* Returns 0 and writes an engine mat4; rejects null/non-finite records. The
 * output matrix preserves CE's forward/left/up/position basis and scale. */
int hcu_render_snapshot_matrix_from_ce(const void *ce_matrix4x3,
	mat4 *out_world);

/* Latest immutable parent-owned CE presentation snapshot. The pointer remains
 * stable until two more frames have been published. */
halo_ps2_render_snapshot const *hcu_render_snapshot_latest(void);

/* Pack the published CE object and first-person matrices into a 16-byte
 * aligned VIF unpack. Returns the qword count, 0 when nothing is published,
 * or -1 when a matrix is rejected. This is the DMA payload, not a scene. */
int hcu_render_snapshot_publish_dma(void);
uint32_t const *hcu_render_snapshot_dma_words(void);
uint32_t hcu_render_snapshot_dma_qwords(void);

#endif
