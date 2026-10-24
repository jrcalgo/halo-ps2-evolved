#include "stream/hcu_load_trace.h"

#ifdef HCU_LOAD_TRACE

#include <stdio.h>
#include <string.h>

#ifdef HCU_LOAD_TRACE_EE
#include <kernel.h>
#include <timer.h>
static uint64_t ee_clock(void) { return (uint64_t)GetTimerSystemTime(); }
static uint64_t (*s_now_us)(void) = ee_clock;
#else
static uint64_t (*s_now_us)(void);
#endif
static hcu_load_trace_state s_state;
static hcu_load_trace_state s_last;

/* EE system time counts BUSCLK (147.456 MHz, ps2sdk kBUSCLK). */
#define TRACE_BUSCLK_HZ 147456000u

enum { TRACE_SITES = 16 };
static struct { const char *name; uint32_t calls; uint64_t bytes; } s_sites[TRACE_SITES];
static int s_site_count;

static void site_clear(void)
{
	memset(s_sites, 0, sizeof(s_sites));
	s_site_count = 0;
}

static void clear_counters(void)
{
	s_state.read_bytes = 0;
	s_state.read_calls = 0;
	s_state.read_max = 0;
	s_state.hash_bytes = 0;
	s_state.hash_passes = 0;
	site_clear();
}

void hcu_load_trace_set_clock(uint64_t (*now_us)(void))
{
	s_now_us = now_us;
}
/* EE builds report GetTimerSystemTime() counts (the EE system timer ticks at
 * the kernel's timer rate; the field is named _us for the host clock). */

void hcu_load_trace_phase_begin(const char *phase)
{
	clear_counters();
	s_state.name = phase;
	s_state.begin_us = s_now_us ? s_now_us() : 0;
	s_state.open = 1;
}

void hcu_load_trace_phase_end(const char *phase)
{
	uint64_t now = s_now_us ? s_now_us() : 0;
	if (!s_state.open || (phase && s_state.name && strcmp(phase, s_state.name) != 0)) return;
	printf("HALO_PS2_LOCAL load-trace phase=%s us=%llu busclk=%llu read-bytes=%llu read-calls=%u read-max=%u "
		"hash-bytes=%llu hash-passes=%u\n",
		s_state.name ? s_state.name : "?",
		(unsigned long long)(((now - s_state.begin_us) * 1000000ull) / TRACE_BUSCLK_HZ),
		(unsigned long long)(now - s_state.begin_us),
		(unsigned long long)s_state.read_bytes, (unsigned)s_state.read_calls,
		(unsigned)s_state.read_max,
		(unsigned long long)s_state.hash_bytes, (unsigned)s_state.hash_passes);
	for (int k = 0; k < s_site_count; ++k)
		printf("HALO_PS2_LOCAL load-trace site phase=%s site=%s calls=%u bytes=%llu\n",
			s_state.name ? s_state.name : "?", s_sites[k].name, (unsigned)s_sites[k].calls,
			(unsigned long long)s_sites[k].bytes);
	s_last = s_state;
	s_state.open = 0;
}

void hcu_load_trace_read(uint32_t bytes)
{
	s_state.read_bytes += bytes;
	s_state.read_calls++;
	if (bytes > s_state.read_max) s_state.read_max = bytes;
}

void hcu_load_trace_read_at(const char *site, uint32_t bytes)
{
	int k;
	hcu_load_trace_read(bytes);
	for (k = 0; k < s_site_count; ++k)
		if (strcmp(s_sites[k].name, site) == 0) break;
	if (k == s_site_count) {
		if (s_site_count == TRACE_SITES) return;
		s_sites[k].name = site;
		s_site_count++;
	}
	s_sites[k].calls++;
	s_sites[k].bytes += bytes;
}

void hcu_load_trace_hash_pass(const char *segment, uint32_t bytes)
{
	(void)segment;
	s_state.hash_bytes += bytes;
	s_state.hash_passes++;
}

void hcu_load_trace_note(const char *key, uint32_t value)
{
	printf("HALO_PS2_LOCAL load-trace note %s=%u\n", key ? key : "?", (unsigned)value);
}

const hcu_load_trace_state *hcu_load_trace_state_get(void)
{
	return &s_last;
}

#endif
