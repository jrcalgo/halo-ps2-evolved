#ifndef HALO_STREAM_HCU_SOUND_REQUESTS_H
#define HALO_STREAM_HCU_SOUND_REQUESTS_H

#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/* Bounded CE sound-request adapter (C3.8). CE's sound manager submits each
 * request to the platform seam with its event, owner, position, priority and
 * playback parameters. The recorder keeps them in a fixed ring in arrival
 * order. The drainer hands them to the audio side in the same order.
 *
 * SPU2 playback is not implemented here. Every drained request is a record of
 * what CE asked for, and the adapter always reports spu2_playback_qualified=0. */

#define HCU_SOUND_REQUEST_CAPACITY 64u

typedef enum {
	HCU_SOUND_EVENT_NONE = 0,
	HCU_SOUND_EVENT_PERMUTATION = 1,   /* _sound_cache_sound_request seam */
	HCU_SOUND_EVENT_IMPULSE = 2,
	HCU_SOUND_EVENT_LOOPING_START = 3,
	HCU_SOUND_EVENT_LOOPING_STOP = 4,
	HCU_SOUND_EVENT_FADE = 5
} hcu_sound_event_kind;

typedef enum {
	HCU_SOUND_OWNER_NONE = 0,
	HCU_SOUND_OWNER_OBJECT = 1,
	HCU_SOUND_OWNER_UNIT = 2,
	HCU_SOUND_OWNER_SCENARIO = 3,
	HCU_SOUND_OWNER_UNATTACHED = 4
} hcu_sound_owner_kind;

typedef struct {
	uint32_t sequence;          /* assigned at submit, strictly increasing */
	uint16_t event;             /* hcu_sound_event_kind */
	uint16_t owner_kind;        /* hcu_sound_owner_kind */
	uint32_t owner_datum;       /* CE datum handle of the owner, or NONE */
	uint32_t sound_index;       /* sound definition index, or NONE */
	uint32_t permutation;       /* permutation handle or cache block index */
	float position[3];          /* world position; ignored when !has_position */
	uint8_t has_position;
	uint8_t priority;           /* CE sound priority, 0 lowest */
	uint8_t flags;              /* bit 0 block, bit 1 load, bit 2 reference */
	uint8_t reserved;
	float gain;                 /* playback gain, 1.0 nominal */
	float pitch;                /* playback pitch multiplier, 1.0 nominal */
	uint32_t game_time;         /* CE game time in ticks at submit */
} hcu_sound_request;

typedef struct {
	uint32_t submitted;         /* every submit call */
	uint32_t accepted;          /* stored in the ring */
	uint32_t rejected;          /* ring full, or invalid record */
	uint32_t drained;           /* handed to the drainer */
	uint32_t high_water;        /* largest pending count seen */
	uint32_t pending;           /* currently stored */
	uint32_t dropped_while_full;
	uint32_t resets;
} hcu_sound_request_counters;

typedef struct {
	hcu_sound_request ring[HCU_SOUND_REQUEST_CAPACITY];
	uint32_t head;              /* next record to drain */
	uint32_t count;             /* stored records */
	uint32_t next_sequence;
	hcu_sound_request_counters counters;
	int spu2_playback_qualified; /* always 0: see header comment */
} hcu_sound_request_queue;

/* Clears the queue and counters. Not qualified for SPU2 playback. */
void hcu_sound_requests_init(hcu_sound_request_queue *queue);
/* Drops any pending records and counts a reset. Counters are kept. */
void hcu_sound_requests_reset(hcu_sound_request_queue *queue);
/* Validates the record and appends it. Returns 1 when accepted. A full ring
 * rejects the new record (oldest records are never discarded) and counts it. */
int hcu_sound_requests_submit(hcu_sound_request_queue *queue,
	const hcu_sound_request *request);
/* Copies up to max records, oldest first, into out. Returns the number
 * copied. Drained records leave the ring. */
size_t hcu_sound_requests_drain(hcu_sound_request_queue *queue,
	hcu_sound_request *out, size_t max);
/* Reads the counters into out. */
void hcu_sound_requests_counters(const hcu_sound_request_queue *queue,
	hcu_sound_request_counters *out);
/* Prints the counters as one HALO_PS2_LOCAL line. Always reports
 * spu2-playback=not-qualified. */
void hcu_sound_requests_print(const hcu_sound_request_queue *queue,
	const char *phase);

#ifdef __cplusplus
}
#endif

#endif
