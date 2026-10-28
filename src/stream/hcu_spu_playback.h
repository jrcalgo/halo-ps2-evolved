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
 * voices are CORE1 voices 0..23. Spatialisation is gain only: the listener is
 * the unit camera, so no pan or distance model is applied. */

#define HCU_SPU_VOICES 24u
#define HCU_SPU_RAM_BASE 0x5010u
#define HCU_SPU_RAM_END 0x200000u

typedef struct {
	uint32_t hash;
	uint16_t perm, perm_count;
	uint32_t rate, samples, bank_offset, bytes;
	float gain;
	uint32_t datum;
	uint32_t spu_addr;
} hcu_spu_sample;

typedef struct {
	uint32_t requests;       /* playback-class records offered */
	uint32_t started;        /* key-on issued */
	uint32_t stopped;        /* key-off issued for a STOP / steal */
	uint32_t no_sample;      /* sound not in the bank */
	uint32_t stolen;         /* voice taken from an equal or lower priority sound (oldest first) */
	uint32_t dropped_busy;   /* every voice busy with a higher-priority sound */
	uint32_t ignored;        /* looping/fade events, not played */
	uint32_t hw_errors;      /* failed libsd remote call */
	uint32_t uploaded_bytes;
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
void hcu_spu_get_stats(hcu_spu_stats *out);
int hcu_spu_ready(void);

/* Host-testable pieces (no libsd): parse/validate a bank image and pick a sample. */
int hcu_spu_bank_parse(const uint8_t *image, uint32_t size, hcu_spu_sample *out,
	uint32_t capacity, uint32_t *count_out, uint32_t *data_off_out, uint32_t *data_end_out);
uint32_t hcu_spu_pitch_for(uint32_t rate, float multiplier);
uint32_t hcu_spu_volume_for(float gain, float sample_gain);

#ifdef __cplusplus
}
#endif

#endif
