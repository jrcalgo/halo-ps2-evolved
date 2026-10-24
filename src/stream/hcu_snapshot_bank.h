/* Triple-bank store for halo_ps2_frame_snapshot (wire version 2).
 *
 * Contract for the frame lane (renderer) and the CE publisher:
 *
 *   hcu_snapshot_bank_bind(storage, bytes)   once at boot, storage from frame
 *                                            scratch; 16-byte aligned, at
 *                                            least hcu_snapshot_bank_storage_required().
 *   hcu_snapshot_bank_unbind()               only after every reader has ended
 *                                            and the renderer is drained; refused
 *                                            (returns -1) while any reader is active.
 *
 *   Writer (CE render_frame, via halo_ps2_frame_snapshot_begin/commit):
 *     begin_write   returns a free, unpublished bank slot, or NULL when every
 *                   non-published slot still has readers (refusal is counted).
 *     intern_object returns the object index for {index, generation}, adding it
 *                   once; shared objects across views are deduplicated here.
 *     commit        validates bounds and finiteness, stamps the map generation
 *                   and sequence, then publishes. A rejected commit releases the
 *                   slot without publishing.
 *
 *   Reader (frame lane):
 *     begin_read(&reader)  pins the latest published slot. Returns the snapshot
 *                          or NULL when nothing is published. Each successful
 *                          begin_read must be paired with end_read.
 *     end_read(&reader)    releases the pin. A slot with a pin is never reused
 *                          or overwritten, even after newer publications.
 *     latest()             unpinned view of the newest published snapshot. A
 *                          publication stays unmodified through one further
 *                          commit; after that its bank may be rewritten, so a
 *                          reader that needs it longer must use begin_read.
 *
 * Refusals never overwrite: begin_write returns NULL, and nothing is published
 * until a writer commits. A new map generation is set with
 * hcu_snapshot_bank_set_map_generation(); it is stamped on each commit and does
 * not alter pinned snapshots.
 *
 * Thread model: single EE core. Readers and writers run in the frame lane and
 * never from an interrupt handler. */
#ifndef HCU_SNAPSHOT_BANK_H
#define HCU_SNAPSHOT_BANK_H

#include "halo_ps2_frame_snapshot.h"

#include <stddef.h>
#include <stdint.h>

#define HCU_SNAPSHOT_BANK_SLOTS 3u

typedef struct hcu_snapshot_reader {
	int slot;
	const halo_ps2_frame_snapshot *snapshot;
} hcu_snapshot_reader;

size_t hcu_snapshot_bank_storage_required(void);
int hcu_snapshot_bank_bind(void *storage, size_t storage_bytes);
int hcu_snapshot_bank_unbind(void);
int hcu_snapshot_bank_is_bound(void);

void hcu_snapshot_bank_set_map_generation(uint32_t generation);

halo_ps2_frame_snapshot *hcu_snapshot_bank_begin_write(void);
int hcu_snapshot_bank_intern_object(halo_ps2_frame_snapshot *snapshot,
	halo_ps2_frame_object_id id, int *out_index);
int hcu_snapshot_bank_commit(halo_ps2_frame_snapshot *snapshot);
void hcu_snapshot_bank_abandon(halo_ps2_frame_snapshot *snapshot);

const halo_ps2_frame_snapshot *hcu_snapshot_bank_begin_read(
	hcu_snapshot_reader *reader);
void hcu_snapshot_bank_end_read(hcu_snapshot_reader *reader);
const halo_ps2_frame_snapshot *hcu_snapshot_bank_latest(void);
int hcu_snapshot_bank_published_slot(void);

/* Counters for telemetry and tests. */
typedef struct hcu_snapshot_bank_stats {
	uint32_t commits;
	uint32_t commit_rejects;
	uint32_t write_refusals;
	uint32_t read_pins_active;
	uint32_t read_pins_taken;
	uint32_t object_dedupe_hits;
	uint32_t object_overflows;
} hcu_snapshot_bank_stats;

void hcu_snapshot_bank_get_stats(hcu_snapshot_bank_stats *out);

#endif
