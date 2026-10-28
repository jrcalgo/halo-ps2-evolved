#ifndef HALO_STREAM_HCU_SPU_PLAYBACK_H
#define HALO_STREAM_HCU_SPU_PLAYBACK_H

#include <stdint.h>

#include "stream/hcu_sound_requests.h"

#ifdef __cplusplus
extern "C" {
#endif

/* SPU2 playback backend for the drained C3.8 sound requests (CE sound manager
 * -> bounded request queue -> here). Samples come from an HSB1 bank
 * (tools/hcu_sound_bank.py) uploaded once into SPU2 RAM through libsd/sdrdrv;
 * voices are CORE1 voices 0..23. A bank larger than SPU2 RAM is paged: the leading
 * samples that fit are resident after the load, any other sample is uploaded on its
 * first request through hcu_spu_hw.upload, evicting the least recently used samples
 * no voice is playing. Positioned sounds are attenuated by distance
 * (full volume inside HCU_SPU_NEAR, linear to silence at HCU_SPU_FAR world units)
 * and panned with a constant-power law against the listener's right vector. The
 * bank carries the sound tag's min/max distance where the tag sets one; every
 * other sound (the tag defers to its sound class) uses these fixed approximations
 * of CE's distance model, not retail values. */

#define HCU_SPU_VOICES 24u
#define HCU_SPU_MAX_SAMPLES 1024u
#define HCU_SPU_RAM_BASE 0x5010u
#define HCU_SPU_RAM_END 0x200000u
#define HCU_SPU_NEAR 2.0f
#define HCU_SPU_FAR 60.0f

typedef struct {
	uint32_t hash;
	uint16_t perm, perm_count;
	uint32_t rate, samples, bank_offset, bytes;
	float gain;
	float near_dist, far_dist; /* sound tag min/max distance in world units; 0 = use HCU_SPU_NEAR/FAR */
	uint32_t spu_addr;       /* SPU2 RAM byte address while resident */
	uint8_t resident;        /* uploaded to SPU2 RAM */
	uint32_t last_used;      /* CE tick of the latest start, for eviction */
} hcu_spu_sample;

typedef struct {
	uint32_t requests;       /* playback-class records offered */
	uint32_t started;        /* key-on issued */
	uint32_t stopped;        /* key-off issued for a STOP / steal */
	uint32_t no_sample;      /* sound not in the bank */
	uint32_t stolen;         /* voice taken from an equal or lower priority sound (oldest first) */
	uint32_t dropped_busy;   /* every voice busy with a higher-priority sound */
	uint32_t inaudible;      /* positioned sound beyond HCU_SPU_FAR, not started */
	uint32_t loops_started;  /* looping voices started */
	uint32_t loop_restarts;  /* looping voice retriggered at the end of its sample */
	uint32_t fades;          /* volume updates applied to a playing voice */
	uint32_t hw_errors;      /* failed libsd remote call */
	uint32_t uploaded_bytes;
	uint32_t page_ins;       /* samples uploaded on demand */
	uint32_t evictions;      /* resident samples dropped to make room */
	uint32_t page_fails;     /* no room (every candidate in use) or upload failed */
	uint32_t samples;
	uint32_t voices_active;
	uint32_t active_high;
} hcu_spu_stats;

/* Load libsd/sdrdrv IRX images, bind the remote and initialise CORE1. 0 on success. */
int hcu_spu_init(void);
/* Read, verify (SHA-256 trailer) and upload a bank. 0 on success. */
int hcu_spu_load_bank(const char *path);
/* FNV-1a over the lower-cased path without separators, as the bank tool computes it. */
uint32_t hcu_spu_name_hash(const char *path);
/* Offer a drained record. `name_hash` identifies the sound definition. */
void hcu_spu_request(const hcu_sound_request *request, uint32_t name_hash);
/* Once per game tick with the current CE tick: retriggers looping voices. */
void hcu_spu_tick(uint32_t now);
void hcu_spu_get_stats(hcu_spu_stats *out);
int hcu_spu_ready(void);
/* Listener pose (the first view's camera). Without one, sounds are centred at full distance gain. */
void hcu_spu_set_listener(const float position[3], const float forward[3], const float up[3]);
/* Distance gain and left/right gains (constant power) for a source; returns the distance gain. */
float hcu_spu_spatial_range(const float listener[3], const float forward[3], const float up[3],
	const float source[3], float near_dist, float far_dist, float *left, float *right);
float hcu_spu_spatial(const float listener[3], const float forward[3], const float up[3],
	const float source[3], float *left, float *right);

/* Host-testable pieces (no libsd): parse/validate a bank image and pick a sample. */
int hcu_spu_bank_parse(const uint8_t *image, uint32_t size, hcu_spu_sample *out,
	uint32_t capacity, uint32_t *count_out, uint32_t *data_off_out, uint32_t *data_end_out);
uint32_t hcu_spu_pitch_for(uint32_t rate, float multiplier);
uint32_t hcu_spu_volume_for(float gain, float sample_gain);

#ifdef __cplusplus
}
#endif

#endif
