#ifndef HYBRID_STREAM_STAGING_H
#define HYBRID_STREAM_STAGING_H
#include <stddef.h>
#include <stdint.h>

#define STAGING_SLOTS 4
/* Owner-thread state machine. Workers return completions to the owner; they
 * never mutate this structure. Cancelled READING buffers stay owned by the
 * worker until completion. HELD buffers stay owned by the consumer until release. */
typedef enum { ST_FREE, ST_QUEUED, ST_READING, ST_READY, ST_HELD, ST_DMA,
               ST_CANCEL_READING, ST_CANCEL_HELD, ST_CANCEL_DMA } staging_state;
typedef struct { uint64_t serial; unsigned slot; } staging_ticket;
typedef struct {
    staging_state state;
    uint64_t serial;
    uint32_t map;
    size_t requested;
} staging_slot;
typedef struct {
    unsigned char *storage;
    size_t stride, high_water;
    uint64_t next_serial;
    uint32_t request_failures, reset_count, reset_failures;
    staging_slot slots[STAGING_SLOTS];
} staging_pool;

int staging_init(staging_pool *, void *, size_t);
/* Quiescent reset preserves serials and lifetime telemetry, so stale tickets
 * cannot name a newly reused slot. Refused while a worker or reader owns bytes. */
int staging_reset(staging_pool *);
int staging_request(staging_pool *, uint32_t map, size_t, staging_ticket *);
void *staging_begin(staging_pool *, staging_ticket);
int staging_complete(staging_pool *, staging_ticket, size_t bytes, int ok);
const void *staging_acquire(staging_pool *, staging_ticket);
/* Owner fills a queued slot and publishes it. The worker must not be reading it. */
int staging_commit(staging_pool *, staging_ticket, const void *);
/* HELD -> DMA. Release fails until staging_dma_complete. Cancel keeps the buffer. */
int staging_dma_submit(staging_pool *, staging_ticket);
int staging_dma_complete(staging_pool *, staging_ticket);
int staging_release(staging_pool *, staging_ticket);
void staging_cancel_map(staging_pool *, uint32_t);
int staging_map_drained(const staging_pool *, uint32_t);
#endif
