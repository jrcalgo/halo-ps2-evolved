#ifndef HALO_STREAM_HCU_LOAD_TRACE_H
#define HALO_STREAM_HCU_LOAD_TRACE_H

/* Opt-in load tracing (HCU_LOAD_TRACE). With the flag undefined every macro
 * below is a no-op, so the default build's code and behaviour do not change.
 *
 * Counters are per phase: a phase begins by clearing them and ends by printing
 * one `HALO_PS2_LOCAL load-trace phase=... ` line. Phases are flat (no nesting).
 * The clock is supplied by the EE build through hcu_load_trace_set_clock; with
 * no clock the elapsed time prints as 0. */

#include <stdint.h>

#ifdef HCU_LOAD_TRACE

typedef struct {
	uint64_t read_bytes;
	uint32_t read_calls;
	uint32_t read_max;
	uint64_t hash_bytes;
	uint32_t hash_passes;
	uint64_t begin_us;
	const char *name;
	int open;
} hcu_load_trace_state;

void hcu_load_trace_set_clock(uint64_t (*now_us)(void));
void hcu_load_trace_phase_begin(const char *phase);
void hcu_load_trace_phase_end(const char *phase);
void hcu_load_trace_read(uint32_t bytes);
void hcu_load_trace_read_at(const char *site, uint32_t bytes);
void hcu_load_trace_hash_pass(const char *segment, uint32_t bytes);
void hcu_load_trace_note(const char *key, uint32_t value);
const hcu_load_trace_state *hcu_load_trace_state_get(void);

#define HCU_LOAD_TRACE_BEGIN(p) hcu_load_trace_phase_begin(p)
#define HCU_LOAD_TRACE_END(p) hcu_load_trace_phase_end(p)
#define HCU_LOAD_TRACE_READ(n) hcu_load_trace_read((uint32_t)(n))
#define HCU_LOAD_TRACE_READ_AT(s, n) hcu_load_trace_read_at((s), (uint32_t)(n))
#define HCU_LOAD_TRACE_HASH(s, n) hcu_load_trace_hash_pass((s), (uint32_t)(n))
#define HCU_LOAD_TRACE_NOTE(k, v) hcu_load_trace_note((k), (uint32_t)(v))

#else

#define HCU_LOAD_TRACE_BEGIN(p) ((void)0)
#define HCU_LOAD_TRACE_END(p) ((void)0)
#define HCU_LOAD_TRACE_READ(n) ((void)0)
#define HCU_LOAD_TRACE_READ_AT(s, n) ((void)0)
#define HCU_LOAD_TRACE_HASH(s, n) ((void)0)
#define HCU_LOAD_TRACE_NOTE(k, v) ((void)0)

#endif

#endif
