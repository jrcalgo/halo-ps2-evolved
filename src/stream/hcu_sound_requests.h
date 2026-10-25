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

/* Must stay a power of two: indices wrap with & (CAPACITY - 1). */
#define HCU_SOUND_REQUEST_CAPACITY 64u

typedef enum {
	HCU_SOUND_EVENT_NONE = 0,
	HCU_SOUND_EVENT_PERMUTATION_REQUEST = 1, /* cache request, not playback */
	HCU_SOUND_EVENT_IMPULSE = 2,
	HCU_SOUND_EVENT_LOOPING_START = 3,
	HCU_SOUND_EVENT_LOOPING_STOP = 4,
	HCU_SOUND_EVENT_FADE = 5,
	HCU_SOUND_EVENT_STOP = 6
} hcu_sound_event_kind;

typedef enum {
	HCU_SOUND_OWNER_NONE = 0,
	HCU_SOUND_OWNER_OBJECT = 1,
	HCU_SOUND_OWNER_UNIT = 2,
	HCU_SOUND_OWNER_SCENARIO = 3,
	HCU_SOUND_OWNER_UNATTACHED = 4,
	HCU_SOUND_OWNER_LOOPING = 5,
	HCU_SOUND_OWNER_CE_SOURCE = 6
} hcu_sound_owner_kind;

typedef struct {
	uint32_t sequence;          /* assigned at submit, strictly increasing */
	uint16_t event;             /* hcu_sound_event_kind */
	uint16_t owner_kind;        /* hcu_sound_owner_kind */
	uint32_t owner_datum;       /* raw CE source datum in owner_kind namespace */
	uint32_t sound_index;       /* CE sound definition index, or NONE */
	uint32_t permutation;       /* permutation handle or cache block index */
	float position[3];          /* world position; ignored when !has_position */
	uint8_t has_position;
	uint8_t priority;           /* CE sound priority, 0 lowest */
	uint8_t flags;              /* bit 0 block, bit 1 load, bit 2 reference */
	uint8_t accepted;           /* cache seam result; not playback success */
	uint8_t metadata_known;     /* bit 0 owner, 1 position, 2 priority, 3 gain, 4 pitch, 5 time */
	uint8_t repeat;             /* PERMUTATION_REQUEST: submits merged here, 1..255 */
	uint8_t reserved[2];
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
	uint32_t coalesced;         /* PERMUTATION_REQUEST merged into a pending record */
	uint32_t evicted;           /* stored record removed to admit a playback event */
} hcu_sound_request_counters;

/* Field-preservation coverage (C3.8). Updated once per drained record, O(1).
 * Field counts cover playback records (every event except PERMUTATION_REQUEST);
 * kinds[] covers all drained records. Known flags come from metadata_known;
 * position is known only when has_position is set. checksum is the XOR of an
 * FNV-1a hash over (event, owner, position, priority, gain, pitch) per drained
 * record. record_fold is the same XOR at accept time, out_fold the XOR of the
 * records dropped without draining (eviction or reset). After a drain the
 * invariant record_fold ^ out_fold == checksum holds iff no stored bytes
 * changed between submit and drain. */
typedef struct {
	uint32_t kinds[8];          /* drained records by hcu_sound_event_kind */
	uint32_t playback;          /* drained playback records */
	uint32_t owner_known;
	uint32_t position_known;    /* has_position with the position bit */
	uint32_t spatial;           /* playback records with has_position */
	uint32_t priority_known;
	uint32_t gain_known;
	uint32_t pitch_known;
	uint32_t priority_min;      /* over priority_known playback records; 255 when none */
	uint32_t priority_max;      /* 0 when none */
	uint32_t checksum;         /* XOR of drained-record FNV hashes */
	uint32_t record_fold;       /* XOR of accepted-record FNV hashes */
	uint32_t out_fold;          /* XOR of pending records dropped unsent */
} hcu_sound_coverage;

typedef struct {
	hcu_sound_request ring[HCU_SOUND_REQUEST_CAPACITY];
	uint32_t head;              /* next record to drain */
	uint32_t count;             /* stored records */
	uint32_t next_sequence;
	hcu_sound_request_counters counters;
	hcu_sound_coverage coverage;
	int spu2_playback_qualified; /* always 0: see header comment */
} hcu_sound_request_queue;

/* Clears the queue and counters. Not qualified for SPU2 playback. */
void hcu_sound_requests_init(hcu_sound_request_queue *queue);
/* Drops any pending records and counts a reset. Counters are kept. */
void hcu_sound_requests_reset(hcu_sound_request_queue *queue);
/* Validates the record and appends it. Returns 1 when accepted or merged. A
 * PERMUTATION_REQUEST with the same permutation and flags as a pending record
 * in the last few slots merges into it. When full, a playback event evicts the
 * oldest PERMUTATION_REQUEST, else a lower-priority IMPULSE/FADE. A stop with a
 * matching LOOPING_START pending is never refused while any victim exists.
 * Everything else is rejected and counted. Eviction keeps arrival order. */
int hcu_sound_requests_submit(hcu_sound_request_queue *queue,
	const hcu_sound_request *request);
/* Build a playback/fade/stop record from the CE bridge arguments. metadata_known
 * uses bits 0..5 for owner, position-state, priority, gain, pitch and time.
 * Always fills *out. Returns 0 when the record is invalid; the caller must
 * still submit it so the queue counts the rejection. An unknown owner kind is
 * stored as NONE with the owner bit cleared. */
int hcu_sound_request_capture_playback(hcu_sound_request *out,
	uint16_t event, uint32_t permutation, uint32_t sound_index,
	uint16_t owner_kind, uint32_t owner_datum, int has_position,
	const float position[3], uint8_t priority, float gain, float pitch,
	uint32_t game_time, uint8_t metadata_known);
/* Calls fn on up to max records in place, oldest first (fn may be NULL to
 * discard). fn must not submit to the same queue. Returns the number drained. */
typedef void (*hcu_sound_request_fn)(void *context, const hcu_sound_request *request);
size_t hcu_sound_requests_drain_each(hcu_sound_request_queue *queue,
	hcu_sound_request_fn fn, void *context, size_t max);
/* Copies up to max records, oldest first, into out. Returns the number
 * copied. Drained records leave the ring. */
size_t hcu_sound_requests_drain(hcu_sound_request_queue *queue,
	hcu_sound_request *out, size_t max);
/* Reads the counters into out. */
void hcu_sound_requests_counters(const hcu_sound_request_queue *queue,
	hcu_sound_request_counters *out);
/* Reads the field-coverage block into out. */
void hcu_sound_requests_coverage(const hcu_sound_request_queue *queue,
	hcu_sound_coverage *out);
/* Prints the counters and coverage as one HALO_PS2_LOCAL line. Always reports
 * spu2-playback=not-qualified. */
void hcu_sound_requests_print(const hcu_sound_request_queue *queue,
	const char *phase);

#ifdef __cplusplus
}
#endif

#endif
