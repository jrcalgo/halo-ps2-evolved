#ifndef HCU_C3_PHASE_PROBE_H
#define HCU_C3_PHASE_PROBE_H

#include <stdint.h>

/* Optional fixed-width PINE diagnostic block. This is independent of the
 * session-trace ring ABI and is published only by phase-probe builds. */
#define HCU_C3_PHASE_PROBE_MAGIC 0x50484333u /* "3CHP" */
#define HCU_C3_PHASE_PROBE_VERSION 2u
#define HCU_C3_FRAME_RING_MAGIC 0x52463343u /* C3FR */
#define HCU_C3_FRAME_RING_VERSION 5u
#define HCU_C3_FRAME_RING_CAPACITY 32u

typedef struct hcu_c3_frame_probe {
	uint32_t sequence;
	uint32_t frame;
	uint32_t tick;
	uint32_t view_count;
	uint32_t view_cycles[4];
	uint32_t build_cycles;
	uint32_t gs_wait_cycles;
	uint32_t video_wait_cycles;
	uint32_t present_cycles;
	uint32_t submit_cycles;
	uint32_t total_cycles;
	uint32_t frame_interval_cycles;
	uint32_t publication_cycles;
	uint32_t cache_evictions;
	uint32_t cache_pool_refusals;
	uint32_t cache_pool_used;
	uint32_t cache_pool_capacity;
	uint32_t cache_pool_high_water;
	uint32_t bitmap_read_calls;
	uint32_t bitmap_read_bytes;
	uint32_t bitmap_source_reads;
	uint32_t bitmap_source_read_bytes;
	uint32_t bitmap_deferred;
	uint32_t bitmap_source_cycles;
	uint32_t bitmap_cache_hits;
	uint32_t bitmap_cache_misses;
	uint32_t bitmap_source_read_cycles;
	uint32_t view_visibility_cycles;
	uint32_t view_clip_gather_cycles;
	uint32_t view_material_sort_cycles;
	uint32_t view_world_emit_cycles;
	uint32_t view_object_hook_cycles;
	uint32_t view_hud_cycles;
	uint32_t view_overlay_cycles;
	uint32_t view_other_cycles;
	uint32_t gif_wait_cycles;
	uint32_t vif_submit_cycles;
	uint32_t upload_submit_cycles;
	uint32_t cache_loads;
	uint32_t cache_pool_misses;
	uint32_t cache_loads_refused;
	uint32_t last_pool_event;
	uint32_t last_pool_event_resource;
	uint32_t last_pool_event_need;
	uint32_t last_pool_event_reclaim;
	uint32_t fx_publish_cycles;
	uint32_t fx_source_calls;
	uint32_t fx_source_bytes;
	uint32_t decal_lock_count;
	uint32_t fx_stream_drops;
	uint32_t tc_defer_count;
	uint32_t first_person_model_misses;
	uint32_t view_skipped;
	uint32_t chain_overflow;
	uint32_t emit_failures;
	uint32_t scheduler_steps;
	uint32_t dropped_delta;
	uint32_t flash_type;
	uint32_t flash_argb;
	/* v5: per-frame deltas (cumulative counters minus the frame start) and governor state. */
	uint32_t snapshot_commit_rejects;
	uint32_t spu_page_ins;
	uint32_t spu_uploaded_bytes;
	uint32_t gov_level;
	uint32_t gov_pressure;
	uint32_t obj_load_bytes;
	uint32_t obj_load_cycles;
} hcu_c3_frame_probe;

typedef struct hcu_c3_frame_probe_ring {
	volatile uint32_t seq;
	uint32_t magic;
	uint32_t version;
	uint32_t capacity;
	uint32_t write_sequence;
	uint32_t overwrites;
	hcu_c3_frame_probe frames[HCU_C3_FRAME_RING_CAPACITY];
} hcu_c3_frame_probe_ring;

typedef struct hcu_c3_phase_probe {
	volatile uint32_t seq; /* odd while writing, even when coherent */
	uint32_t magic;
	uint32_t version;
	uint32_t frame;
	uint32_t hud_emit_cycles;
	uint32_t close_frame_cycles;
	uint32_t setup_packet_cycles;
	uint32_t setup_gif_wait_cycles;
	uint32_t upload_submit_cycles;
	uint32_t upload_gif_wait_cycles;
	uint32_t vif_submit_cycles;
	uint32_t submit_hook_cycles;
	uint32_t upload_qw;
	uint32_t view_camera_setup_cycles;
	uint32_t view_visibility_cycles;
	uint32_t view_clip_gather_group_cycles;
	uint32_t view_clip_gather_cycles;
	uint32_t view_clip_group_cycles;
	uint32_t clip_batches_in;
	uint32_t clip_polys_out;
	uint32_t clip_vertices_out;
	uint32_t view_material_group_sort_cycles;
	uint32_t view_sky_cycles;
	uint32_t view_world_emit_cycles;
	uint32_t view_object_hook_cycles;
	uint32_t view_inline_hud_cycles;
	uint32_t view_overlay_cycles;
	uint32_t view_other_cycles;
	uint32_t view_total_cycles;
	uint32_t view_count;
	uint32_t clear_view_count;
} hcu_c3_phase_probe;

#if defined(HALO_PS2_C3_PHASE_PROBE) && HALO_PS2_C3_PHASE_PROBE
extern volatile hcu_c3_phase_probe g_hcu_c3_phase_probe;
extern volatile hcu_c3_frame_probe_ring g_hcu_c3_frame_probe_ring;
#endif

#endif
