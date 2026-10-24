/* C3.objects: draws the published CE object snapshot (players, bots, vehicles, weapons, one effect model)
 * through the halo-ps2 object pass, after the BSP pass of each view.
 *
 * Parent contract: the parent reads immutable published data only. It never advances animation or
 * gameplay. Node palettes are the CE-computed skin matrices from the snapshot; the parent does not
 * sample ANIM. The snapshot is read-pinned while the frame draws and unpinned once the frame's kick
 * has completed (hcu_render_objects_pin / hcu_render_objects_unpin).
 *
 * This header and the selection/builder half of hcu_render_objects.c are host-testable: they touch no
 * renderer or EE headers. The EE adapter (draw pass, model/texture loading) is compiled only with
 * HCU_RENDER_OBJECTS_EE. */
#ifndef HALO_STREAM_HCU_RENDER_OBJECTS_H
#define HALO_STREAM_HCU_RENDER_OBJECTS_H

#include <stddef.h>
#include <stdint.h>

#include "halo_ps2_frame_snapshot.h"
#include "stream/hcu_render_content.h"
#include "stream/hcu_snapshot_bank.h"

#ifdef __cplusplus
extern "C" {
#endif

#define HCU_OBJECTS_MAX_MODELS 8u       /* resident model slots (one MODL chunk each) */
#define HCU_OBJECTS_MAX_DRAW 64u        /* draw entries per view */
#define HCU_OBJECTS_MAX_PARITY 64u      /* parity records kept for the first frame only */

/* Object types carried in halo_ps2_frame_object.type. */
#define HCU_OBJECTS_TYPE_BIPED 0
#define HCU_OBJECTS_TYPE_VEHICLE 1
#define HCU_OBJECTS_TYPE_WEAPON 2
#define HCU_OBJECTS_TYPE_EFFECT 3

/* Object flags. Bit 0 means the object is skinned: its palette is used, one matrix per model node. */
#define HCU_OBJECTS_FLAG_SKINNED 0x0001u

/* Resident model table. resource_id is the MEDIA chunk id of the MODL chunk (the snapshot resource
 * identity); source_datum keeps the CE tag datum for the parity log. */
typedef struct {
	uint32_t resource_id;
	uint32_t source_datum;
	uint32_t model_bytes;
	uint32_t texture_bytes;
	uint16_t texture_count;
	uint8_t loaded;
	uint8_t pad;
} hcu_render_objects_model;

typedef struct {
	uint32_t view;
	uint32_t object_index;
	uint32_t generation;
	uint32_t definition_index;
	uint32_t resource_id;
	uint16_t slot;
	uint16_t type;
	uint16_t flags;
	uint16_t palette_first;
	uint16_t palette_count;
	halo_ps2_snapshot_matrix4x3 world;
} hcu_render_object_draw;

typedef struct {
	uint32_t views_seen;
	uint32_t objects_drawn;
	uint32_t triangles;
	uint32_t skinned_nodes;
	uint32_t model_hits;        /* resource resolved to a resident model slot */
	uint32_t model_misses;      /* resource not resident: object refused */
	uint32_t texture_hits;      /* texture binding resolved from resident OTEX */
	uint32_t texture_misses;    /* texture binding unresolved: part drawn flat */
	uint32_t failures;          /* invalid object, palette, resource or overflow */
	uint32_t deduped;           /* object referenced twice in one view */
	uint32_t pins;
	uint32_t unpins;
	uint32_t pin_refusals;
	uint32_t parity_dropped;
} hcu_render_objects_counters;

typedef struct {
	const halo_ps2_frame_snapshot *snapshot;
	hcu_snapshot_reader reader;
	int pinned;
} hcu_render_objects_pin_t;

/* ---- selection (pure) ---------------------------------------------------------------------------
 * Collects the draw entries of one view from its view_refs. Objects are validated against the
 * snapshot bounds, the palette range and the resident model table. Failures are counted and the
 * object is skipped; nothing is clamped silently. Returns 0 or a negative status. */
int hcu_render_objects_select(const halo_ps2_frame_snapshot *snap, uint32_t view,
	const hcu_render_objects_model *models, uint32_t model_count,
	hcu_render_object_draw *out, uint32_t capacity, uint32_t *count,
	hcu_render_objects_counters *counters);

/* Resident model lookup by MEDIA chunk id. Returns the slot or -1. */
int hcu_render_objects_find_model(const hcu_render_objects_model *models, uint32_t model_count,
	uint32_t resource_id);

/* ---- pin / unpin ----------------------------------------------------------------------------------
 * pin takes a read pin on the latest published bank slot. unpin releases it; call it only after the
 * frame's kick has completed. Returns NULL when nothing is published (the frame draws no objects). */
const halo_ps2_frame_snapshot *hcu_render_objects_pin(hcu_render_objects_pin_t *pin,
	hcu_render_objects_counters *counters);
void hcu_render_objects_unpin(hcu_render_objects_pin_t *pin, hcu_render_objects_counters *counters);

/* ---- parity ------------------------------------------------------------------------------------- */
/* Appends one parity record per draw entry. surface_id carries the CE object definition index,
 * material_id is -1 (the object's shaders are bound per part), resource_id the MODL chunk id. */
int hcu_render_objects_parity(hcu_render_parity_log *log, uint32_t frame,
	const hcu_render_object_draw *draw, uint32_t count, hcu_render_objects_counters *counters);

/* ---- synthetic snapshot builder ----------------------------------------------------------------
 * Test-only producer used behind HCU_C3_OBJECTS_SYNTHETIC until the CE snapshot publisher fills the
 * bank. It writes a version-2 snapshot with the same layout the CE publisher uses. */
typedef struct {
	uint32_t resource_id;
	uint32_t definition_index;
	uint16_t type;
	uint16_t flags;
	uint16_t palette_count;
	halo_ps2_snapshot_matrix4x3 world;
	const halo_ps2_snapshot_matrix4x3 *palette;   /* palette_count matrices, or NULL when not skinned */
} hcu_render_synthetic_object;

int hcu_render_synthetic_begin(halo_ps2_frame_snapshot *s, uint32_t map_generation,
	uint32_t frame_index, uint32_t view_count);
int hcu_render_synthetic_view(halo_ps2_frame_snapshot *s, uint32_t view,
	const halo_ps2_snapshot_camera *camera);
/* Adds an object to `view`; the same {definition_index, resource_id} within one snapshot is interned
 * once and referenced by every view that adds it. Views must be filled in order. */
int hcu_render_synthetic_object_add(halo_ps2_frame_snapshot *s, uint32_t view,
	uint32_t object_index, const hcu_render_synthetic_object *o);

/* ---- EE adapter (HCU_RENDER_OBJECTS_EE only) ------------------------------------------------------ */
#ifdef HCU_RENDER_OBJECTS_EE
#include "core/mem.h"
#include "stream/hcu_asset_profile.h"

/* One generated entry (tools/hcu_c3_objects_table.py): a MODL chunk and its OTEX chunk, both MEDIA
 * chunks of the mounted profile, with the expected logical SHA-256 of each. texture_chunk 0 = flat. */
typedef struct {
	uint32_t model_chunk;
	uint32_t texture_chunk;
	uint32_t source_datum;
	uint8_t model_sha256[32];
	uint8_t texture_sha256[32];
	const char *path;
} hcu_render_objects_table_entry;

typedef struct {
	uint32_t models_loaded, models_refused, texture_sets, textures;
	uint32_t model_bytes, texture_bytes, arena_before, arena_after;
} hcu_render_objects_load_info;

typedef struct {
	uint32_t drawn, triangles, skinned_nodes, failures, pins_before;
	uint32_t model_hits, model_misses, texture_hits, texture_misses;
	uint32_t parity_records;
} hcu_render_objects_view_stats;

/* Loads the table's MODL/OTEX chunks into `arena` (the render level arena) with read-verify. Refused
 * entries are left out; the arena charge is reported. Resets all previous object state. */
int hcu_render_objects_load(const hcu_asset_profile_view *view, arena_t *arena,
	const hcu_render_objects_table_entry *table, uint32_t count, hcu_render_objects_load_info *info);
/* Installs the object pass after the BSP pass (bsp_render_set_object_pass). Call once per map,
 * after the models are loaded and before the first view. */
int hcu_render_objects_install(void);
/* Frame lifetime: begin unpins the previous frame when its kick has completed, optionally publishes the
 * synthetic snapshot (synthetic_views > 0, HCU_C3_OBJECTS_SYNTHETIC) and pins the latest published
 * snapshot; end records the kick sequence. release drops any pin (GPU already drained). */
const halo_ps2_frame_snapshot *hcu_render_objects_frame_begin(uint32_t frame, uint32_t synthetic_views,
	const halo_ps2_snapshot_camera *synthetic_cameras);
void hcu_render_objects_view_begin(uint32_t view);
void hcu_render_objects_view_end(uint32_t view, hcu_render_objects_view_stats *out);
void hcu_render_objects_frame_end(void);
void hcu_render_objects_release(void);
void hcu_render_objects_totals(hcu_render_objects_counters *out);
#endif

#ifdef __cplusplus
}
#endif
#endif
