#ifndef HCU_SESSION_TRACE_H
#define HCU_SESSION_TRACE_H
#include <stdint.h>

/* Fixed read-only PINE ABI. Rows are plain 32-bit words; no pointers/heap. */
#define HCU_SESSION_TRACE_MAGIC 0x43545243u
#define HCU_SESSION_TRACE_VERSION 1u
#define HCU_SESSION_TRACE_FRAME_CAP 32u
#define HCU_SESSION_TRACE_INPUT_CAP 128u
#define HCU_SESSION_TRACE_EVENT_CAP 64u

typedef struct hcu_session_trace_frame {
	volatile uint32_t seq; /* 0 while being written; otherwise monotonic sequence */
	uint32_t frame;
	int32_t tick;
	uint32_t perf_probe_frame, object_probe_frame, object_probe_view, video_probe_frame, probe_valid; /* bits: perf, object, video, scope */
	uint32_t frame_cycles, bsp_wait_cycles, previous_kick_wait_cycles;
	uint32_t video_present_cycles;
	uint32_t scheduler_game_ticks, scheduler_dropped_ticks;
	uint32_t object_world_cycles, object_fp_cycles, object_fp_overhead_cycles;
	uint32_t object_drawn, object_triangles, object_skinned_nodes, object_failures;
	uint32_t raw_buttons, effective_buttons, connected, edge_down, edge_up;
	uint32_t state_valid; /* bit0 player transform, bit1 camera transform/FOV, bit2 held weapon identity, bit3 cache/pool, bit4 native zoom */
	float camera_x, camera_y, camera_z, camera_yaw, camera_pitch, camera_hfov;
	uint32_t map_generation, fp_weapon_resource_id, fp_hands_resource_id;
	int32_t native_zoom_level;
	uint32_t scope_probe_frame, scope_valid, scope_requests, scope_views, scope_tiles;
	uint32_t scope_copy_attempts, scope_copy_queued, scope_fence_refusals;
	uint32_t scope_capacity_refusals, scope_copy_refusals, scope_emitted_qw, scope_backend_cycles;
	int32_t scope_backend_status;
	uint32_t bitmap_hits_total, bitmap_misses_total, bitmap_source_reads_total, bitmap_source_bytes_total;
	uint32_t bitmap_hash_checks_total, bitmap_parses_total, bitmap_read_calls_total, bitmap_read_bytes_total;
	uint32_t bitmap_read_cycles_total, bitmap_hash_cycles_total, bitmap_parse_cycles_total, bitmap_source_cycles_total, bitmap_deferred_total;
	uint32_t video_wait_cycles, video_select_cycles;
	uint32_t cache_resident, cache_loads, cache_misses, cache_evictions;
	uint32_t cache_pool_used, cache_pool_capacity, cache_pool_refusals, cache_fence_blocked;
} hcu_session_trace_frame;

typedef struct hcu_session_trace_input {
	volatile uint32_t seq;
	uint32_t frame;
	int32_t tick;
	uint32_t raw_buttons, effective_buttons, edge_down, edge_up, connected;
	uint32_t axes; /* packed lx | ly<<8 | rx<<16 | ry<<24 */
	uint32_t analog_buttons_low; /* A,B,X,Y bytes */
	uint32_t analog_buttons_high; /* BLACK,WHITE,LT,RT bytes; intent only */
	int16_t effective_lx, effective_ly, effective_rx, effective_ry;
} hcu_session_trace_input;

typedef struct hcu_session_trace_event {
	volatile uint32_t seq;
	uint32_t frame, tick, type, entry_index, source_datum, bytes, reason, generation;
} hcu_session_trace_event;

typedef struct hcu_session_trace {
	uint32_t magic, version, bytes;
	volatile uint32_t seq; /* odd while writer updates top-level fields */
	volatile uint32_t frame_write_seq, input_write_seq, event_write_seq;
	volatile uint32_t frame_overwrites, input_overwrites, event_overwrites;
	uint32_t frame, tick;
	uint32_t raw_buttons, effective_buttons, connected;
	uint32_t frame_capacity, input_capacity, event_capacity;
	hcu_session_trace_frame frames[HCU_SESSION_TRACE_FRAME_CAP];
	hcu_session_trace_input inputs[HCU_SESSION_TRACE_INPUT_CAP];
	hcu_session_trace_event events[HCU_SESSION_TRACE_EVENT_CAP];
} hcu_session_trace;

#if defined(HALO_PS2_C3_SESSION_TRACE) && HALO_PS2_C3_SESSION_TRACE
extern volatile hcu_session_trace g_hcu_c3_session_trace;
enum { HCU_SESSION_EVENT_MODEL_LOAD = 1u, HCU_SESSION_EVENT_MODEL_EVICT = 2u,
	HCU_SESSION_EVENT_MODEL_REFUSED = 3u, HCU_SESSION_EVENT_POOL_REFUSED = 4u,
	HCU_SESSION_EVENT_FENCE_REFUSED = 5u };
static inline void hcu_session_trace_record_event(uint32_t type, uint32_t frame,
	uint32_t entry_index, uint32_t source_datum, uint32_t bytes, uint32_t reason, uint32_t generation)
{
	volatile hcu_session_trace *t = &g_hcu_c3_session_trace;
	uint32_t n, old;
	old = t->seq; t->seq = old + 1u; n = t->event_write_seq + 1u;
	{
		volatile hcu_session_trace_event *r = &t->events[(n - 1u) % HCU_SESSION_TRACE_EVENT_CAP];
		r->seq = n * 2u - 1u; r->frame = frame; r->tick = t->tick; r->type = type;
		r->entry_index = entry_index; r->source_datum = source_datum;
		r->bytes = bytes; r->reason = reason; r->generation = generation;
		r->seq = n * 2u;
	}
	t->event_write_seq = n;
	if (n > HCU_SESSION_TRACE_EVENT_CAP) t->event_overwrites++;
	t->seq = old + 2u;
}
static inline void hcu_session_trace_record_input(uint32_t raw, uint32_t effective, uint32_t connected, uint32_t axes, uint32_t analog_low, uint32_t analog_high, int16_t elx, int16_t ely, int16_t erx, int16_t ery)
{
	volatile hcu_session_trace *t = &g_hcu_c3_session_trace;
	uint32_t n, old, prev;
	prev = t->raw_buttons;
	n = t->input_write_seq + 1u;
	old = t->seq; t->seq = old + 1u;
	t->raw_buttons = raw; t->effective_buttons = effective; t->connected = connected;
	t->input_write_seq = n;
	{
		volatile hcu_session_trace_input *r = &t->inputs[(n - 1u) % HCU_SESSION_TRACE_INPUT_CAP];
				r->seq = n * 2u - 1u;
		r->frame = t->frame; r->tick = (int32_t)t->tick;
		r->raw_buttons = raw; r->effective_buttons = effective;
		r->edge_down = raw & ~prev; r->edge_up = prev & ~raw; r->connected = connected; r->axes = axes; r->analog_buttons_low = analog_low; r->analog_buttons_high = analog_high;
		r->effective_lx = elx; r->effective_ly = ely; r->effective_rx = erx; r->effective_ry = ery;
		r->seq = n * 2u;
	}
	if (n > HCU_SESSION_TRACE_INPUT_CAP) t->input_overwrites++;
	t->seq = old + 2u;
}
#endif
#endif
