/* C3.objects: draws the published CE object snapshot (players, bots, vehicles, weapons, effects, and
 * the exact per-view first-person gun and arms models) through the halo-ps2 object pass, after the BSP pass.
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

#define HCU_OBJECTS_MAX_MODELS 80u      /* table entries (one MODL chunk each); residency is by the pool */
#define HCU_OBJECTS_TEX_STRIDE 32u      /* texture cache keys per entry: entry i owns [i*32, i*32+32) */
#define HCU_OBJECTS_MAX_DRAW 64u        /* draw entries per view */
#define HCU_OBJECTS_MAX_PARITY 64u      /* parity records kept for the first frame only */
#define HCU_FX_MAX_PER_VIEW 64u          /* C3.6(c): fx requests drawn per view (fixed cap, no heap) */

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
	uint16_t node_count;
	uint8_t loaded;
	uint8_t pad;
} hcu_render_objects_model;

#define HCU_OBJECTS_FP_WEAPON 1u
#define HCU_OBJECTS_FP_HANDS 2u
typedef struct {
	uint32_t resource_id;
	uint16_t model_slot;
	uint16_t palette_first;
	uint16_t palette_count;
	uint8_t kind;
	uint8_t reserved;
} hcu_render_first_person_draw;

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
	uint32_t pose_hash;                  /* FNV-1a over the object's palette matrices (0 when unskinned) */
	halo_ps2_snapshot_matrix4x3 world;
} hcu_render_object_draw;

/* C3.6 pose tracker: one entry per snapshot object index. A change in the palette hash between two
 * frames of the same generation is the evidence that a vehicle or weapon node palette moved. */
#define HCU_OBJECTS_POSE_TRACK HALO_PS2_FRAME_MAX_OBJECTS
typedef struct {
	uint32_t generation[HCU_OBJECTS_POSE_TRACK];
	uint32_t hash[HCU_OBJECTS_POSE_TRACK];
	uint8_t seen[HCU_OBJECTS_POSE_TRACK];
} hcu_render_pose_tracker;

/* C3.6 effect and decal requests from the snapshot (v4 fx request table). Draw entries carry the
 * view and the CE source identity {datum index, datum identifier} within the snapshot's map generation. */
typedef struct {
	uint32_t view;
	uint32_t owner_object;
	uint32_t source_index;
	uint32_t source_generation;
	uint32_t resource_id;
	uint32_t permutation;
	uint16_t kind;
	uint16_t flags;
	float position[3];
	float forward[3];
	float scale;
	float age_sec;
} hcu_render_effect_draw;

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
	uint32_t first_person_draws;
	uint32_t first_person_model_hits;
	uint32_t first_person_model_misses;
	uint32_t first_person_stale_resources;
	uint32_t first_person_weapon_draws;  /* C3.6: per-kind first-person draws */
	uint32_t first_person_hands_draws;
	uint32_t pose_changes;               /* palette hash differs from the object's previous frame */
	uint32_t pose_static;                /* palette hash equal to the previous frame */
	uint32_t effects_selected;           /* C3.6: snapshot effect requests accepted for a view */
	uint32_t effects_refused;            /* out of range owner, non-finite or unknown kind */
	uint32_t parts_logged;               /* per-part parity records (surface = part, material = shader) */
	uint32_t fx_drawn;                   /* C3.6(c): fx quads admitted to the view's GS packet */
	uint32_t fx_skipped_space;           /* C3.6(c): fx quads refused by chain_has_space and skipped */
	uint32_t fx_textured;                /* C3.6(c): fx quads drawn with a resident texture */
	uint32_t fx_flat;                    /* C3.6(c): fx quads drawn flat-shaded (no resident texture) */
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
/* Select CE's exact per-view first-person gun and hands resources and their
 * already remapped model-node palettes, without deriving a proxy or sampling. */
int hcu_render_objects_select_first_person(const halo_ps2_frame_snapshot *snap,
	uint32_t view, const hcu_render_objects_model *models, uint32_t model_count,
	hcu_render_first_person_draw out[2], uint32_t *count,
	hcu_render_objects_counters *counters);

/* FNV-1a over the bit patterns of `n` palette matrices starting at `first`. Returns 0 for n == 0. */
uint32_t hcu_render_objects_pose_hash(const halo_ps2_snapshot_matrix4x3 *palette, uint32_t palette_count,
	uint32_t first, uint32_t n);
/* Records one object's pose hash. Returns 1 when it differs from the previous frame of the same
 * generation, 0 when equal or first seen; the counters receive pose_changes / pose_static. */
int hcu_render_pose_track(hcu_render_pose_tracker *t, uint32_t object_index, uint32_t generation,
	uint32_t hash, hcu_render_objects_counters *counters);
/* Effect requests of one view: owner must be a view reference of that view and the position finite.
 * Bounded by capacity; overflow counts as a refusal. */
int hcu_render_effects_select(const halo_ps2_frame_snapshot *snap, uint32_t view,
	hcu_render_effect_draw *out, uint32_t capacity, uint32_t *count,
	hcu_render_objects_counters *counters);

/* C3.6(c) quad generation (pure, host-tested). A billboard faces the camera: right and up come from the
 * view's camera basis (hcu_render_fx_camera_basis). A decal lies in the plane perpendicular to its forward
 * (its normal). `scale` is the half extent in world units. Corners are counter-clockwise in (right, up) order:
 * v[0] = (-,-), v[1] = (+,-), v[2] = (+,+), v[3] = (-,+). */
typedef struct {
	float v[4][3];
	uint32_t resource_id;
	uint16_t kind;
	uint16_t pad;
} hcu_render_fx_quad;

/* Unit right and up of the snapshot camera. Returns 0, or E_ARGUMENT when forward or up is degenerate. */
int hcu_render_fx_camera_basis(const halo_ps2_snapshot_camera *cam, float right[3], float up[3]);
/* Builds one quad. Returns 0, or E_ARGUMENT for a non-finite or non-positive scale or a kind with no quad
 * (HALO_PS2_FRAME_FX_LIGHT). A decal with a zero or non-finite forward falls back to a billboard. */
int hcu_render_fx_build_quad(const hcu_render_effect_draw *e, const float right[3], const float up[3],
	hcu_render_fx_quad *q);
/* Flat colour per kind as RGBA, with alpha on the GS scale (0x80 = opaque). Returns 0, or E_ARGUMENT. */
int hcu_render_fx_flat_colour(uint16_t kind, uint8_t rgba[4]);

/* C3.6: pose-track every interned object of the pinned snapshot once per frame. */
int hcu_render_objects_track_poses(const halo_ps2_frame_snapshot *snap, hcu_render_pose_tracker *t,
	hcu_render_objects_counters *counters);

/* Resident model lookup by MEDIA chunk id. Returns the slot or -1. */
int hcu_render_objects_find_model(const hcu_render_objects_model *models, uint32_t model_count,
	uint32_t resource_id);

/* Residency policy helpers shared with host tests. Lower priority values are admitted first. */
uint32_t hcu_render_objects_residency_priority(uint16_t type);
int hcu_render_objects_residency_may_evict(int loaded, int referenced_this_frame,
	int fence_observed);
/* C3.3 pin check: an entry that a pinned snapshot bank references (pins > 0) is never a victim. Each
 * refusal of an otherwise-evictable entry increments *evict_refused_pinned. Returns 1 when evictable. */
int hcu_render_objects_residency_victim_ok(int loaded, int referenced_this_frame, int fence_observed,
	uint32_t pins, uint32_t *evict_refused_pinned);
int hcu_render_objects_pool_request_fits(uint32_t need, uint32_t capacity);

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
 * bank. It writes a current-version snapshot with the same layout the CE publisher uses. */
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
	uint32_t entries, models_refused, texture_sets, textures;
	uint32_t model_bytes, texture_bytes, arena_before, arena_after;
	uint32_t pool_bytes;
} hcu_render_objects_load_info;

/* Residency of the table's models in the pool (C3.objects). hits and misses count the frame's referenced
 * entries: a hit is resident when the frame begins, a miss is still not resident after the frame's loads
 * and evictions. A miss on an entry the pool cannot hold, or that the fence keeps from evicting, is
 * counted in pool_refusals or fence_blocked. */
typedef struct {
	uint32_t resident, loads, hits, misses, evictions, pool_refusals, fence_blocked;
	uint32_t entry_refusals, pool_bytes, pool_used, pool_used_peak;
	uint32_t keys_used, keys_refused;
	uint32_t evict_refused_pinned;  /* C3.3: evictable-by-fence entries kept because a pinned bank holds them */
} hcu_render_objects_residency;

typedef struct {
	uint32_t drawn, triangles, skinned_nodes, failures, pins_before;
	uint32_t model_hits, model_misses, texture_hits, texture_misses;
	uint32_t parity_records;
	uint32_t first_person_draws, first_person_model_hits, first_person_model_misses;
	uint32_t first_person_stale_resources;
	uint32_t first_person_weapon_draws, first_person_hands_draws;
	uint32_t parts_logged, effects_selected, effects_refused;
	uint32_t fx_drawn, fx_skipped_space, fx_textured, fx_flat;
	uint32_t first_person_map_generation;
	uint16_t first_person_weapon_resource_slot, first_person_hands_resource_slot;
	uint32_t first_person_weapon_resource_id, first_person_hands_resource_id;
} hcu_render_objects_view_stats;

/* Takes the rest of `arena` as the residency pool and checks the table's chunk sizes against the mounted
 * profile. No chunk is read here: entries load when a frame's snapshot references them (see frame_begin).
 * Entries whose chunks do not match the table are refused. Resets all previous object state. */
int hcu_render_objects_load(const hcu_asset_profile_view *view, arena_t *arena,
	const hcu_render_objects_table_entry *table, uint32_t count, hcu_render_objects_load_info *info);
/* Installs the object pass after the BSP pass (bsp_render_set_object_pass). Call once per map,
 * after the models are loaded and before the first view. */
int hcu_render_objects_install(void);
/* C3.6: summary (counts per kind and identity hash) of this run's first-frame parity log. */
int hcu_render_objects_parity_summary(hcu_render_parity_summary *out);
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
void hcu_render_objects_residency_stats(hcu_render_objects_residency *out);
#endif

#ifdef __cplusplus
}
#endif
#endif
