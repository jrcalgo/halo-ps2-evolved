#include "stream/hcu_spu_playback.h"

#include <math.h>
#include <string.h>

#include "stream/hcu_spu_hw.h"

#define HSB_MAGIC 0x31425348u /* 'HSB1' */
#define HSB_VERSION 1u
#define HSB_HEADER_BYTES 32u
#define HSB_ENTRY_BYTES 32u
#define HCU_SPU_MAX_SAMPLES 160u
#define HCU_SPU_TICKS_PER_SECOND 30u
#define HCU_SPU_VOLUME_MAX 0x3FFFu
#define HCU_SPU_VOLUME_SCALE 0.7f /* headroom for the eight overlapping weapon voices */
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
		s->datum = rd32(e + 28);
		if (!s->perm_count || s->perm >= s->perm_count || !s->rate || !s->bytes || (s->bytes & 15u) ||
			(s->bank_offset & 15u) || s->bank_offset < data_off || s->bank_offset > size - 32u ||
			s->bytes > size - 32u - s->bank_offset)
			return -4;
		/* SPU2 RAM mirrors the data region, shifted to HCU_SPU_RAM_BASE. */
		s->spu_addr = HCU_SPU_RAM_BASE + (s->bank_offset - data_off);
		if (s->spu_addr + s->bytes > HCU_SPU_RAM_END) return -5;
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
	for (i = 0; i < s_sample_count; ++i) s_samples[i] = samples[i];
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

float hcu_spu_spatial(const float listener[3], const float forward[3], const float up[3],
	const float source[3], float *left, float *right)
{
	float d[3], rx, ry, rz, dist, att, pan, rlen;
	uint32_t i;
	for (i = 0; i < 3; ++i) d[i] = source[i] - listener[i];
	dist = sqrtf(d[0] * d[0] + d[1] * d[1] + d[2] * d[2]);
	if (!(dist > HCU_SPU_NEAR)) att = 1.0f;
	else if (dist >= HCU_SPU_FAR) att = 0.0f;
	else att = 1.0f - (dist - HCU_SPU_NEAR) / (HCU_SPU_FAR - HCU_SPU_NEAR);
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

/* Left/right volumes for a request: sample and request gain, then distance and pan when positioned. */
static int request_volumes(const hcu_sound_request *r, const hcu_spu_sample *sample, uint32_t *vol_l, uint32_t *vol_r)
{
	uint32_t volume = hcu_spu_volume_for(r->gain, sample->gain);
	*vol_l = *vol_r = volume;
	if (r->has_position && s_listener_valid) {
		float l, rt, att = hcu_spu_spatial(s_listener, s_listener_forward, s_listener_up, r->position, &l, &rt);
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
	voice = pick_voice(priority, r->game_time, &stolen);
	if (voice < 0) { s_stats.dropped_busy++; return; }
	if (stolen) { key_off((uint32_t)voice); s_stats.stolen++; }
	key_on((uint32_t)voice, r, sample, vol_l, vol_r);
	ticks = (uint32_t)((uint64_t)sample->samples * HCU_SPU_TICKS_PER_SECOND / sample->rate) + 2u;
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
	uint32_t i, vol_l, vol_r, ticks;
	if (!s_hw) return;
	for (i = 0; i < HCU_SPU_VOICES; ++i) {
		voice_state *v = &s_voice[i];
		if (!v->active || !v->looping || (int32_t)(now - v->end_tick) < 0) continue;
		s_hw->set_switch((uint16_t)(SD_CORE1 | SD_SWITCH_KOFF_ENTRY), 1u << i);
		(void)request_volumes(&v->request, v->sample, &vol_l, &vol_r);
		key_on(i, &v->request, v->sample, vol_l, vol_r);
		ticks = (uint32_t)((uint64_t)v->sample->samples * HCU_SPU_TICKS_PER_SECOND / v->sample->rate) + 2u;
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
