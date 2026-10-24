/* Pointer-free CPU snapshot boundary from CE transform records to halo-ps2.
 * The input is the pinned CE real_matrix4x3 wire layout (13 IEEE-754 floats,
 * 52 bytes); callers pass object_get_node_matrix() data only after the CE tick. */
#ifndef HCU_RENDER_SNAPSHOT_H
#define HCU_RENDER_SNAPSHOT_H

#include "core/mat.h"
#include "halo_ps2_render_snapshot.h"
#include "render/chain.h"

#include <stddef.h>

#define HCU_CE_MATRIX4X3_BYTES 52u

/* Snapshot banks are borrowed from frame_scratch. DMA payloads are appended
 * to the caller's live renderer chain; this module owns no DMA storage. */
size_t hcu_render_snapshot_storage_required(void);
int hcu_render_snapshot_bind(void *frame_scratch, size_t frame_scratch_bytes);
void hcu_render_snapshot_unbind(void);

/* The CE port's begin/commit hooks use the currently bound two-bank store.
 * A begin returns NULL until bind succeeds. */
halo_ps2_render_snapshot *halo_ps2_render_snapshot_begin(void);
int halo_ps2_render_snapshot_commit(halo_ps2_render_snapshot *snapshot);
halo_ps2_render_snapshot const *halo_ps2_render_snapshot_latest(void);

/* Returns 0 and writes an engine mat4; rejects null/non-finite records. The
 * output matrix preserves CE's forward/left/up/position basis and scale. */
int hcu_render_snapshot_matrix_from_ce(const void *ce_matrix4x3,
	mat4 *out_world);

/* Latest immutable parent-owned CE presentation snapshot. The pointer remains
 * stable until two more frames have been published. */
halo_ps2_render_snapshot const *hcu_render_snapshot_latest(void);

/* Append published object/first-person matrices as an inline VIF1 unpack to
 * an idle engine chain. Returns appended qwords, 0 for no matrices, or -1 on
 * invalid input/overflow. The caller controls chain lifetime and submission. */
int hcu_render_snapshot_emit_chain(chain_t *chain);

#endif
