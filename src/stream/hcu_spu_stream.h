#ifndef HALO_STREAM_HCU_SPU_STREAM_H
#define HALO_STREAM_HCU_SPU_STREAM_H

#include <stdint.h>

#include "stream/hcu_spu_hw.h"

#ifdef __cplusplus
extern "C" {
#endif

/* Music streamed from disc through two SPU2 voices (left and right channel) at the recording's own rate, for a
 * stream file written by tools/build_hcu_menu_music.py ("HMS1"). Each channel plays a ring of two halves in the last
 * 64 KB of SPU2 RAM: the voice loops the ring (loop flags the player sets on the first and last block), and as it
 * crosses into one half the other, just played, is refilled from the file. A refill is one disc read and one SPU2
 * upload per channel, on separate ticks, so a tick costs one read of HCU_STREAM_HALF bytes at most. A late refill
 * repeats the half (counted as an underrun) rather than playing anything but music.
 * Pieces are queued by index and play back to back with no gap; when none is queued the ring fills with silence. */

#define HCU_STREAM_HALF 16384u               /* bytes of one channel's half-ring: 0.65 s at 44.1 kHz */
#define HCU_STREAM_RING_L 0x1F0000u          /* SPU2 RAM: left ring, then right ring, to the end of SPU2 RAM */
#define HCU_STREAM_RING_R (HCU_STREAM_RING_L + 2u * HCU_STREAM_HALF)
#define HCU_STREAM_RESERVED_BYTES (4u * HCU_STREAM_HALF)
#define HCU_STREAM_VOICE_L 22u
#define HCU_STREAM_VOICE_R 23u
#define HCU_STREAM_VOICE_MASK ((1u << HCU_STREAM_VOICE_L) | (1u << HCU_STREAM_VOICE_R))
#define HCU_STREAM_MAX_PIECES 16u
#define HCU_STREAM_QUEUE 8u

typedef struct {
	/* Reads `bytes` of the stream file at `offset`; 0 on success. */
	int (*read)(void *context, uint32_t offset, void *destination, uint32_t bytes);
	void *context;
	uint32_t size;
} hcu_spu_stream_source;

typedef struct {
	uint32_t ticks;
	uint32_t refills;      /* halves refilled */
	uint32_t underruns;    /* a half was due again before its refill finished */
	uint32_t read_fails;   /* segments that read as silence */
	uint32_t pieces_started;
	uint32_t silent_halves;/* halves filled with silence: nothing was queued */
} hcu_spu_stream_stats;

/* Parses and validates the stream file's header and piece table. 0 on success. Does not touch the hardware. */
int hcu_spu_stream_open(const hcu_spu_hw *hw, const hcu_spu_stream_source *source);
int hcu_spu_stream_ready(void);
uint32_t hcu_spu_stream_piece_count(void);
uint32_t hcu_spu_stream_piece_ms(uint32_t piece);
/* Appends a piece to play after the ones already queued. 0 on success, -1 when the queue is full or `piece` is bad. */
int hcu_spu_stream_queue(uint32_t piece);
/* Pieces queued and not yet begun by the reader. */
uint32_t hcu_spu_stream_queued(void);
/* Fills both halves of both rings from the queue and keys the two voices on together. `volume` is the voice volume
 * (0..0x3FFF); the channels are panned hard left and right. 0 on success. */
int hcu_spu_stream_start(uint32_t volume);
/* Once per frame: refills the half the voices have left. */
void hcu_spu_stream_tick(void);
void hcu_spu_stream_stop(void);
int hcu_spu_stream_playing(void);
void hcu_spu_stream_get_stats(hcu_spu_stream_stats *out);

#if defined(__mips__)
/* Opens the stream file through the file bridge and attaches it. 0 on success. */
int hcu_spu_stream_open_path(const char *path);
#endif

#ifdef __cplusplus
}
#endif

#endif
