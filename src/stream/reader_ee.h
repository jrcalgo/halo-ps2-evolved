#ifndef HYBRID_STREAM_READER_EE_H
#define HYBRID_STREAM_READER_EE_H
#include "staging.h"
#define READER_PATH_CAP 160
/* One owner thread calls the public API. One worker owns the active read.
 * Objects, backing storage and stack must outlive successful reader_stop(). */
typedef struct {
    staging_pool pool;
    struct { char path[READER_PATH_CAP]; long offset; } requests[STAGING_SLOTS];
    int wake, done, thread, active, result, running;
    staging_ticket ticket;
    void *destination;
    size_t bytes;
} ee_reader;
int reader_start(ee_reader *, void *storage, size_t, void *stack, size_t, int priority);
int reader_request(ee_reader *, uint32_t map, const char *, long, size_t, staging_ticket *);
void reader_pump(ee_reader *);
void reader_cancel_map(ee_reader *, uint32_t);
/* Nonblocking: fails until every request/consumer is drained. */
int reader_stop(ee_reader *);
#endif
