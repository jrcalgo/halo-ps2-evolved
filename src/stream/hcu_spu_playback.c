#include "stream/hcu_spu_playback.h"

#include <math.h>
#include <string.h>

#include "stream/hcu_spu_hw.h"

#define HSB_MAGIC 0x31425348u /* 'HSB1' */
#define HSB_VERSION 2u
#define HSB_HEADER_BYTES 32u
#define HSB_ENTRY_BYTES 32u
#define HCU_SPU_TICKS_PER_SECOND 1000u /* game_time is CE's system_milliseconds */
#define HCU_SPU_TAIL_MS 40u
#define HCU_SPU_VOLUME_MAX 0x3FFFu
#define HCU_SPU_VOLUME_SCALE 0.5f /* mixing headroom: nine overlapping full-gain voices clipped at 0.7 in the Blood Gulch capture */
#define HCU_SPU_PITCH_MAX 0x3FFFu
#define HCU_SPU_ADSR1 0x00FFu
#define HCU_SPU_ADSR2 0x1FC0u
#define SD_VOICE_PARAM_VOLL 0x0000u
#define SD_VOICE_PARAM_VOLR 0x0100u
#define SD_VOICE_PARAM_PITCH 0x0200u
#define SD_VOICE_PARAM_ADSR1 0x0300u
#define SD_VOICE_PARAM_ADSR2 0x0400u
#define SD_VOICE_ADDR_SSA 0x2000u
#define SD_SWITCH_KON_ENTRY 0x1500u
#define SD_SWITCH_KOFF_ENTRY 0x1600u
#define SD_CORE1 1u

typedef struct {
	uint8_t active;
	uint8_t priority;
	uint8_t looping;
	uint32_t hash, owner;
	uint32_t start_tick, end_tick;
	const hcu_spu_sample *sample;
	hcu_sound_request request; /* latest gain/position, used to retrigger a loop and to apply a fade */
} voice_state;

static const hcu_spu_hw *s_hw;
static hcu_spu_sample s_samples[HCU_SPU_MAX_SAMPLES];
static uint32_t s_sample_count;
static uint8_t s_perm_cursor[HCU_SPU_MAX_SAMPLES];
static voice_state s_voice[HCU_SPU_VOICES];
static hcu_spu_stats s_stats;
static float s_listener[3], s_listener_forward[3], s_listener_up[3];
static int s_listener_valid;

/* A page-in reads the sample from the bank and waits for the SPU2 transfer: up to ~12 ms for one sample on the EE.
 * The first of a tick is taken at once; a second new sound in the same tick waits in a short queue for a later tick,
 * so an explosion's burst of new sounds spreads over frames instead of costing one of them (a late sound is
 * 33 ms late; a dropped frame is the same 33 ms for everything on screen). */
#define HCU_SPU_PENDING 16u
#define HCU_SPU_PENDING_MAX_AGE 700u /* ms */
typedef struct {
	hcu_sound_request request;
	uint32_t hash, born;
	uint8_t looping;
} pending_start;
static pending_start s_pending[HCU_SPU_PENDING];
static uint32_t s_pending_head, s_pending_count;
static uint32_t s_page_in_time, s_page_ins_this_tick;
static hcu_spu_sample *s_loading; /* the one sample being paged in over several ticks */
static uint32_t s_draining_born;
static int s_draining;

static uint32_t rd32(const uint8_t *p)
{
	return (uint32_t)p[0] | (uint32_t)p[1] << 8 | (uint32_t)p[2] << 16 | (uint32_t)p[3] << 24;
}

static float rdf(const uint8_t *p)
{
	uint32_t bits = rd32(p);
	float value;
	memcpy(&value, &bits, sizeof(value));
	return value;
}

uint32_t hcu_spu_name_hash(const char *path)
{
	uint32_t value = 0x811C9DC5u;
	if (!path) return value;
	for (; *path; ++path) {
		unsigned char ch = (unsigned char)*path;
		if (ch == '\\' || ch == '/') continue;
		if (ch >= 'A' && ch <= 'Z') ch = (unsigned char)(ch + ('a' - 'A'));
		value = (value ^ ch) * 0x01000193u;
	}
	return value;
}

uint32_t hcu_spu_pitch_for(uint32_t rate, float multiplier)
{
	float scaled;
	if (!rate) return 0;
	if (!(multiplier > 0.0f)) multiplier = 1.0f;
	scaled = (float)0x1000 * (float)rate / 48000.0f * multiplier + 0.5f;
	if (scaled >= (float)HCU_SPU_PITCH_MAX) return HCU_SPU_PITCH_MAX;
	return (uint32_t)scaled;
}

uint32_t hcu_spu_volume_for(float gain, float sample_gain)
{
	float v;
	if (!(gain > 0.0f)) return 0;
	if (!(sample_gain > 0.0f)) sample_gain = 1.0f;
	if (gain > 1.0f) gain = 1.0f;
	if (sample_gain > 1.0f) sample_gain = 1.0f;
	v = gain * sample_gain * (float)HCU_SPU_VOLUME_MAX * HCU_SPU_VOLUME_SCALE;
	return v >= (float)HCU_SPU_VOLUME_MAX ? HCU_SPU_VOLUME_MAX : (uint32_t)v;
}

int hcu_spu_bank_parse(const uint8_t *image, uint32_t size, hcu_spu_sample *out,
	uint32_t capacity, uint32_t *count_out, uint32_t *data_off_out, uint32_t *data_end_out)
{
	uint32_t count, entries_off, data_off, total, i;
	if (!image || size < HSB_HEADER_BYTES + 32u || !out || !count_out) return -1;
	if (rd32(image) != HSB_MAGIC || rd32(image + 4) != HSB_VERSION) return -2;
	count = rd32(image + 8);
	entries_off = rd32(image + 12);
	data_off = rd32(image + 16);
	total = rd32(image + 20);
	if (total != size || count > capacity || entries_off != HSB_HEADER_BYTES ||
		data_off < entries_off + count * HSB_ENTRY_BYTES || (data_off & 15u) || data_off > size - 32u)
		return -3;
	for (i = 0; i < count; ++i) {
		const uint8_t *e = image + entries_off + i * HSB_ENTRY_BYTES;
		hcu_spu_sample *s = &out[i];
		memset(s, 0, sizeof(*s));
		s->hash = rd32(e);
		s->perm = (uint16_t)(e[4] | e[5] << 8);
		s->perm_count = (uint16_t)(e[6] | e[7] << 8);
		s->rate = rd32(e + 8);
		s->samples = rd32(e + 12);
		s->bank_offset = rd32(e + 16);
		s->bytes = rd32(e + 20);
		s->gain = rdf(e + 24);
		s->near_dist = (float)(e[28] | e[29] << 8) / 64.0f;
		s->far_dist = (float)(e[30] | e[31] << 8) / 64.0f;
		if (!s->perm_count || s->perm >= s->perm_count || !s->rate || !s->bytes || (s->bytes & 15u) ||
			(s->bank_offset & 15u) || s->bank_offset < data_off || s->bank_offset > size - 32u ||
			s->bytes > size - 32u - s->bank_offset)
			return -4;
		/* The load uploads the data region from HCU_SPU_RAM_BASE until SPU2 RAM is full: a sample is resident
		 * when it fits entirely, any other is paged in on first use. */
		if (HCU_SPU_RAM_BASE + (s->bank_offset - data_off) + s->bytes <= HCU_SPU_RAM_END) {
			s->spu_addr = HCU_SPU_RAM_BASE + (s->bank_offset - data_off);
			s->resident = 1;
		}
	}
	*count_out = count;
	if (data_off_out) *data_off_out = data_off;
	if (data_end_out) *data_end_out = size - 32u;
	return 0;
}

void hcu_spu_attach(const hcu_spu_hw *hw, const hcu_spu_sample *samples, uint32_t count)
{
	uint32_t i;
	s_hw = hw;
	s_sample_count = count > HCU_SPU_MAX_SAMPLES ? HCU_SPU_MAX_SAMPLES : count;
	s_loading = NULL;
	for (i = 0; i < s_sample_count; ++i) { s_samples[i] = samples[i]; s_samples[i].loading = 0; s_samples[i].loaded = 0; }
	memset(s_perm_cursor, 0, sizeof(s_perm_cursor));
	memset(s_voice, 0, sizeof(s_voice));
	memset(&s_stats, 0, sizeof(s_stats));
	s_stats.samples = s_sample_count;
}

int hcu_spu_ready(void)
{
	return s_hw != 0 && s_sample_count != 0;
}

void hcu_spu_get_stats(hcu_spu_stats *out)
{
	uint32_t i, active = 0;
	if (!out) return;
	for (i = 0; i < HCU_SPU_VOICES; ++i) active += s_voice[i].active;
	s_stats.voices_active = active;
	*out = s_stats;
}

void hcu_spu_note_uploaded(uint32_t bytes)
{
	s_stats.uploaded_bytes = bytes;
}

static uint16_t voice_entry(uint32_t voice, uint16_t param)
{
	return (uint16_t)(SD_CORE1 | (voice << 1) | param);
}

static void expire(uint32_t now)
{
	uint32_t i;
	for (i = 0; i < HCU_SPU_VOICES; ++i)
		if (s_voice[i].active && !s_voice[i].looping && (int32_t)(now - s_voice[i].end_tick) >= 0) s_voice[i].active = 0;
}

static int pick_voice(uint8_t priority, uint32_t now, int *stolen)
{
	uint32_t i;
	int victim = -1;
	*stolen = 0;
	for (i = 0; i < HCU_SPU_VOICES; ++i)
		if (!s_voice[i].active) return (int)i;
	for (i = 0; i < HCU_SPU_VOICES; ++i) {
		if (s_voice[i].priority > priority) continue;
		if (victim < 0 || s_voice[i].priority < s_voice[victim].priority ||
			(s_voice[i].priority == s_voice[victim].priority &&
			 (int32_t)(s_voice[victim].start_tick - s_voice[i].start_tick) > 0))
			victim = (int)i;
	}
	(void)now;
	if (victim >= 0) *stolen = 1;
	return victim;
}

static const hcu_spu_sample *choose_sample(uint32_t hash)
{
	uint32_t i, first = HCU_SPU_MAX_SAMPLES, perms = 0;
	for (i = 0; i < s_sample_count; ++i)
		if (s_samples[i].hash == hash) { first = i; perms = s_samples[i].perm_count; break; }
	if (first == HCU_SPU_MAX_SAMPLES) return 0;
	{
		uint32_t pick = s_perm_cursor[first] % perms;
		s_perm_cursor[first] = (uint8_t)(s_perm_cursor[first] + 1u);
		for (i = first; i < s_sample_count && s_samples[i].hash == hash; ++i)
			if (s_samples[i].perm == pick) return &s_samples[i];
	}
	return &s_samples[first];
}

static void key_off(uint32_t voice)
{
	s_hw->set_switch((uint16_t)(SD_CORE1 | SD_SWITCH_KOFF_ENTRY), 1u << voice);
	s_stats.stopped++;
	s_voice[voice].active = 0;
}

void hcu_spu_set_listener(const float position[3], const float forward[3], const float up[3])
{
	uint32_t i;
	if (!position || !forward || !up) { s_listener_valid = 0; return; }
	for (i = 0; i < 3; ++i) {
		s_listener[i] = position[i];
		s_listener_forward[i] = forward[i];
		s_listener_up[i] = up[i];
	}
	s_listener_valid = 1;
}

float hcu_spu_spatial_range(const float listener[3], const float forward[3], const float up[3],
	const float source[3], float near_dist, float far_dist, float *left, float *right)
{
	float d[3], rx, ry, rz, dist, att, pan, rlen;
	uint32_t i;
	for (i = 0; i < 3; ++i) d[i] = source[i] - listener[i];
	dist = sqrtf(d[0] * d[0] + d[1] * d[1] + d[2] * d[2]);
	if (!(dist > near_dist)) att = 1.0f;
	else if (dist >= far_dist) att = 0.0f;
	else att = 1.0f - (dist - near_dist) / (far_dist - near_dist);
	/* right = forward x up (CE is right-handed with +z up) */
	rx = forward[1] * up[2] - forward[2] * up[1];
	ry = forward[2] * up[0] - forward[0] * up[2];
	rz = forward[0] * up[1] - forward[1] * up[0];
	rlen = sqrtf(rx * rx + ry * ry + rz * rz);
	pan = 0.0f;
	/* Inside one unit the direction is noise (the listener's own weapon): keep it centred. */
	if (dist > 1.0f && rlen > 1.0e-6f) {
		pan = (d[0] * rx + d[1] * ry + d[2] * rz) / (dist * rlen);
		if (pan > 1.0f) pan = 1.0f;
		if (pan < -1.0f) pan = -1.0f;
	}
	/* Constant power, but never below 0.707 of full on both sides when centred. */
	*left = sqrtf((1.0f - pan) * 0.5f) * 1.41421356f;
	*right = sqrtf((1.0f + pan) * 0.5f) * 1.41421356f;
	if (*left > 1.0f) *left = 1.0f;
	if (*right > 1.0f) *right = 1.0f;
	return att;
}

static int sample_in_use(const hcu_spu_sample *sample)
{
	uint32_t i;
	for (i = 0; i < HCU_SPU_VOICES; ++i)
		if (s_voice[i].active && s_voice[i].sample == sample) return 1;
	return 0;
}

/* Lowest 64-byte aligned address where `padded` bytes fit between the resident samples, or 0 when none does. */
static uint32_t find_gap(uint32_t padded)
{
	uint32_t i, c, best = 0;
	for (c = 0; c <= s_sample_count; ++c) {
		uint32_t start = c == 0 ? HCU_SPU_RAM_BASE : (s_samples[c - 1].resident ? s_samples[c - 1].spu_addr + s_samples[c - 1].bytes : 0);
		int fits = 1;
		if (c && !s_samples[c - 1].resident) continue;
		start = (start + 63u) & ~63u;
		if (start + padded > HCU_SPU_RAM_END) continue;
		for (i = 0; i < s_sample_count && fits; ++i)
			if (s_samples[i].resident && s_samples[i].spu_addr < start + padded &&
				start < s_samples[i].spu_addr + s_samples[i].bytes) fits = 0;
		if (fits && (!best || start < best)) best = start;
	}
	return best;
}

/* A sample about to lose its SPU2 RAM: whatever voice last started it is muted and keyed off first, whatever the
 * bookkeeping says about its lifetime. A voice that reads a region another sample was uploaded over plays that
 * sample's ADPCM blocks out of step: the buzzing and beeping. */
static void silence_voices_of(const hcu_spu_sample *sample)
{
	uint32_t i, mask = 0;
	for (i = 0; i < HCU_SPU_VOICES; ++i) {
		if (s_voice[i].sample != sample) continue;
		s_hw->set_param(voice_entry(i, SD_VOICE_PARAM_VOLL), 0u);
		s_hw->set_param(voice_entry(i, SD_VOICE_PARAM_VOLR), 0u);
		s_voice[i].sample = NULL;
		s_voice[i].active = 0;
		mask |= 1u << i;
	}
	if (mask) {
		s_hw->set_switch((uint16_t)(SD_CORE1 | SD_SWITCH_KOFF_ENTRY), mask);
		s_stats.muted_before_evict++;
	}
}

/* Makes `sample` resident, evicting least recently used samples that no voice plays. 0 on success. */
static int page_in(hcu_spu_sample *sample)
{
	uint32_t padded = (sample->bytes + 63u) & ~63u, addr;
	if (sample->resident) return 0;
	if (!s_hw->upload) return -1;
	for (;;) {
		uint32_t i, victim = HCU_SPU_MAX_SAMPLES;
		addr = find_gap(padded);
		if (addr) break;
		for (i = 0; i < s_sample_count; ++i)
			if (s_samples[i].resident && !s_samples[i].loading && !sample_in_use(&s_samples[i]) &&
				(victim == HCU_SPU_MAX_SAMPLES || (int32_t)(s_samples[victim].last_used - s_samples[i].last_used) > 0))
				victim = i;
		if (victim == HCU_SPU_MAX_SAMPLES) return -2;
		silence_voices_of(&s_samples[victim]);
		s_samples[victim].resident = 0;
		s_stats.evictions++;
	}
	if (s_hw->upload_part && padded > HCU_SPU_UPLOAD_PART) {
		/* the first slice now, the rest one slice per game tick (hcu_spu_tick); starts wait for `loading` to clear */
		if (s_hw->upload_part(sample, addr, 0, HCU_SPU_UPLOAD_PART) != 0) return -3;
		sample->spu_addr = addr;
		sample->resident = 1;
		sample->loading = 1;
		sample->loaded = HCU_SPU_UPLOAD_PART;
		s_loading = sample;
		return 0;
	}
	if (s_hw->upload(sample, addr) != 0) return -3;
	sample->spu_addr = addr;
	sample->resident = 1;
	s_stats.page_ins++;
	return 0;
}

/* One more slice of the sample being paged in; the sample is playable once the last slice is up. */
static void advance_loading(void)
{
	hcu_spu_sample *s = s_loading;
	uint32_t n;
	if (!s) return;
	n = s->bytes - s->loaded < HCU_SPU_UPLOAD_PART ? s->bytes - s->loaded : HCU_SPU_UPLOAD_PART;
	if (s_hw->upload_part(s, s->spu_addr, s->loaded, n) != 0) {
		s->resident = 0;
		s->loading = 0;
		s_loading = NULL;
		s_stats.page_fails++;
		return;
	}
	s->loaded += n;
	if (s->loaded >= s->bytes) {
		s->loading = 0;
		s_loading = NULL;
		s_stats.page_ins++;
	}
}

float hcu_spu_spatial(const float listener[3], const float forward[3], const float up[3],
	const float source[3], float *left, float *right)
{
	return hcu_spu_spatial_range(listener, forward, up, source, HCU_SPU_NEAR, HCU_SPU_FAR, left, right);
}

/* Left/right volumes for a request: sample and request gain, then distance and pan when positioned. */
static int request_volumes(const hcu_sound_request *r, const hcu_spu_sample *sample, uint32_t *vol_l, uint32_t *vol_r)
{
	uint32_t volume = hcu_spu_volume_for(r->gain, sample->gain);
	*vol_l = *vol_r = volume;
	if (r->has_position && s_listener_valid) {
		float l, rt, att;
		float near_d = sample->near_dist, far_d = sample->far_dist;
		/* Tag distances when the sound tag sets a valid pair; otherwise the fixed class-agnostic defaults. */
		if (!(near_d > 0.0f && far_d > near_d)) { near_d = HCU_SPU_NEAR; far_d = HCU_SPU_FAR; }
		att = hcu_spu_spatial_range(s_listener, s_listener_forward, s_listener_up, r->position, near_d, far_d, &l, &rt);
		*vol_l = (uint32_t)((float)volume * att * l);
		*vol_r = (uint32_t)((float)volume * att * rt);
	}
	return *vol_l || *vol_r;
}

static void key_on(uint32_t voice, const hcu_sound_request *r, const hcu_spu_sample *sample, uint32_t vol_l, uint32_t vol_r)
{
	s_hw->set_param(voice_entry(voice, SD_VOICE_PARAM_VOLL), (uint16_t)vol_l);
	s_hw->set_param(voice_entry(voice, SD_VOICE_PARAM_VOLR), (uint16_t)vol_r);
	s_hw->set_param(voice_entry(voice, SD_VOICE_PARAM_PITCH), (uint16_t)hcu_spu_pitch_for(sample->rate, r->pitch));
	s_hw->set_param(voice_entry(voice, SD_VOICE_PARAM_ADSR1), HCU_SPU_ADSR1);
	s_hw->set_param(voice_entry(voice, SD_VOICE_PARAM_ADSR2), HCU_SPU_ADSR2);
	s_hw->set_addr(voice_entry(voice, SD_VOICE_ADDR_SSA), sample->spu_addr);
	s_hw->set_switch((uint16_t)(SD_CORE1 | SD_SWITCH_KON_ENTRY), 1u << voice);
}

/* How long the voice plays, in game_time units (ms), at the request's pitch: a lowered pitch plays longer,
 * and a voice must not be reused, nor its sample evicted, before the SPU2 is done with it. */
static uint32_t voice_ticks(const hcu_spu_sample *sample, float pitch, uint32_t tail)
{
	uint32_t pitch_milli = !(pitch > 0.0f) ? 1000u : pitch > 4.0f ? 4000u : (uint32_t)(pitch * 1000.0f);
	if (pitch_milli < 1u) pitch_milli = 1u;
	return (uint32_t)((uint64_t)sample->samples * HCU_SPU_TICKS_PER_SECOND * 1000u / ((uint64_t)sample->rate * pitch_milli)) + tail;
}

/* Queues a start that must wait for a page-in; 0 when the queue is full. */
static int queue_start(const hcu_sound_request *r, uint32_t hash, int looping)
{
	pending_start *p;
	if (s_pending_count >= HCU_SPU_PENDING) return 0;
	p = &s_pending[(s_pending_head + s_pending_count++) % HCU_SPU_PENDING];
	p->request = *r;
	p->hash = hash;
	p->born = s_draining ? s_draining_born : r->game_time;
	p->looping = (uint8_t)looping;
	return 1;
}

static void start_sound(const hcu_sound_request *r, uint32_t hash, int looping)
{
	const hcu_spu_sample *sample = choose_sample(hash);
	int stolen, voice;
	uint8_t priority = r->priority == 255u ? 0u : r->priority;
	uint32_t vol_l, vol_r, ticks;
	if (!sample) { s_stats.no_sample++; return; }
	if (!request_volumes(r, sample, &vol_l, &vol_r) && r->has_position && s_listener_valid) {
		s_stats.inaudible++;
		return;
	}
	{
		hcu_spu_sample *paged = (hcu_spu_sample *)sample;
		paged->last_used = r->game_time;
		/* a sample still being paged in, or a second page-in while one is under way: the start waits for a later tick */
		if (paged->loading || (!paged->resident && s_loading)) {
			if (!queue_start(r, hash, looping)) s_stats.dropped_busy++;
			return;
		}
		if (!paged->resident) {
			if (s_page_in_time != r->game_time) { s_page_in_time = r->game_time; s_page_ins_this_tick = 0; }
			if (s_page_ins_this_tick >= 1u && queue_start(r, hash, looping)) return;
		}
		{
			int was_resident = paged->resident;
			if (page_in(paged) != 0) { s_stats.page_fails++; return; }
			if (!was_resident) s_page_ins_this_tick++;
			if (paged->loading) {
				if (!queue_start(r, hash, looping)) s_stats.dropped_busy++;
				return;
			}
		}
	}
	voice = pick_voice(priority, r->game_time, &stolen);
	if (voice < 0) { s_stats.dropped_busy++; return; }
	if (stolen) { key_off((uint32_t)voice); s_stats.stolen++; }
	key_on((uint32_t)voice, r, sample, vol_l, vol_r);
	/* a one-shot keeps its voice and sample a little past the nominal end: the key-on goes through IOP RPCs */
	ticks = voice_ticks(sample, r->pitch, looping ? 2u : HCU_SPU_TAIL_MS);
	s_voice[voice].active = 1;
	s_voice[voice].looping = (uint8_t)looping;
	s_voice[voice].priority = priority;
	s_voice[voice].hash = hash;
	s_voice[voice].owner = r->owner_datum;
	s_voice[voice].start_tick = r->game_time;
	s_voice[voice].end_tick = r->game_time + ticks;
	s_voice[voice].sample = sample;
	s_voice[voice].request = *r;
	s_stats.started++;
	if (looping) s_stats.loops_started++;
	{
		uint32_t i, active = 0;
		for (i = 0; i < HCU_SPU_VOICES; ++i) active += s_voice[i].active;
		if (active > s_stats.active_high) s_stats.active_high = active;
	}
}

static void stop_sound(const hcu_sound_request *r, uint32_t hash)
{
	uint32_t i;
	for (i = 0; i < HCU_SPU_VOICES; ++i)
		if (s_voice[i].active && s_voice[i].hash == hash && s_voice[i].owner == r->owner_datum)
			key_off(i);
}

/* A fade carries the channel's current gain: re-apply it (and the position) to the voices of that sound. */
static void fade_sound(const hcu_sound_request *r, uint32_t hash)
{
	uint32_t i, vol_l, vol_r;
	for (i = 0; i < HCU_SPU_VOICES; ++i) {
		voice_state *v = &s_voice[i];
		if (!v->active || v->hash != hash || v->owner != r->owner_datum) continue;
		v->request.gain = r->gain;
		if (r->has_position) {
			v->request.has_position = 1;
			v->request.position[0] = r->position[0];
			v->request.position[1] = r->position[1];
			v->request.position[2] = r->position[2];
		}
		if (!request_volumes(&v->request, v->sample, &vol_l, &vol_r)) {
			key_off(i);
			continue;
		}
		s_hw->set_param(voice_entry(i, SD_VOICE_PARAM_VOLL), (uint16_t)vol_l);
		s_hw->set_param(voice_entry(i, SD_VOICE_PARAM_VOLR), (uint16_t)vol_r);
		s_stats.fades++;
	}
}

/* Once per game tick: restart looping voices whose sample ended (the bank's VAG data has no loop flag). */
void hcu_spu_tick(uint32_t now)
{
	uint32_t i, vol_l, vol_r, ticks, queued;
	if (!s_hw) return;
	advance_loading();
	/* Sounds that waited for a page-in: one new sample per tick; one that waited too long is dropped. A start
	 * that must wait again is queued behind the rest (only the entries queued before this tick are visited). */
	for (queued = s_pending_count; queued; --queued) {
		pending_start p = s_pending[s_pending_head];
		s_pending_head = (s_pending_head + 1u) % HCU_SPU_PENDING;
		s_pending_count--;
		if ((int32_t)(now - p.born) > (int32_t)HCU_SPU_PENDING_MAX_AGE) { s_stats.dropped_busy++; continue; }
		p.request.game_time = now;
		s_draining = 1;
		s_draining_born = p.born;
		start_sound(&p.request, p.hash, p.looping);
		s_draining = 0;
	}
	for (i = 0; i < HCU_SPU_VOICES; ++i) {
		voice_state *v = &s_voice[i];
		if (!v->active || !v->looping || (int32_t)(now - v->end_tick) < 0) continue;
		s_hw->set_switch((uint16_t)(SD_CORE1 | SD_SWITCH_KOFF_ENTRY), 1u << i);
		(void)request_volumes(&v->request, v->sample, &vol_l, &vol_r);
		key_on(i, &v->request, v->sample, vol_l, vol_r);
		ticks = voice_ticks(v->sample, v->request.pitch, 2u);
		v->start_tick = now;
		v->end_tick = now + ticks;
		s_stats.loop_restarts++;
	}
}

void hcu_spu_request(const hcu_sound_request *r, uint32_t name_hash)
{
	if (!r || !s_hw || !s_sample_count) return;
	switch (r->event) {
	case HCU_SOUND_EVENT_IMPULSE:
		s_stats.requests++;
		expire(r->game_time);
		start_sound(r, name_hash, 0);
		break;
	case HCU_SOUND_EVENT_LOOPING_START: {
		uint32_t i;
		s_stats.requests++;
		expire(r->game_time);
		/* CE re-announces a running loop while it is being updated: one voice per owner and sound. */
		for (i = 0; i < HCU_SPU_VOICES; ++i)
			if (s_voice[i].active && s_voice[i].looping && s_voice[i].hash == name_hash &&
				s_voice[i].owner == r->owner_datum) {
				fade_sound(r, name_hash);
				return;
			}
		start_sound(r, name_hash, 1);
		break;
	}
	case HCU_SOUND_EVENT_STOP:
	case HCU_SOUND_EVENT_LOOPING_STOP:
		stop_sound(r, name_hash);
		break;
	case HCU_SOUND_EVENT_FADE:
		s_stats.requests++;
		fade_sound(r, name_hash);
		break;
	default:
		break;
	}
}
