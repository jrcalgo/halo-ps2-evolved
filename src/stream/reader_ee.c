#include "reader_ee.h"
#include <kernel.h>
#include <limits.h>
#include <string.h>
#include "stream/file.h"
extern void *_gp;

static void worker(void *arg) {
    ee_reader *r = arg;
    for (;;) {
        WaitSema(r->wake);
        /* Semaphore handoff publishes the immutable mailbox. Only this worker
         * writes result; the owner reads it after acquiring done. */
        r->result = file_read_at(r->requests[r->ticket.slot].path,
                                r->requests[r->ticket.slot].offset,
                                r->destination, r->bytes);
        SignalSema(r->done);
    }
}
int reader_start(ee_reader *r, void *storage, size_t bytes,
                 void *stack, size_t stack_bytes, int priority) {
    ee_sema_t sem = {0};
    ee_thread_t thread = {0};
    staging_pool kept;
    int preserve;
    if (!r || !stack || ((uintptr_t)stack & 15) || stack_bytes < 16384 ||
        stack_bytes > INT_MAX || priority < 1 || priority > 127) return 0;
    /* A restarted worker must keep DMA-leased slots. Their bytes stay put. */
    preserve = !r->running && r->pool.storage == storage;
    if (preserve) {
        for (unsigned i = 0; i < STAGING_SLOTS; ++i) {
            staging_state state = r->pool.slots[i].state;
            if (state != ST_FREE && state != ST_DMA && state != ST_CANCEL_DMA) return 0;
        }
        kept = r->pool;
    }
    memset(r, 0, sizeof *r);
    r->wake = r->done = r->thread = -1;
    if (preserve) r->pool = kept;
    else if (!staging_init(&r->pool, storage, bytes)) return 0;
    sem.init_count = 0; sem.max_count = 1;
    r->wake = CreateSema(&sem);
    if (r->wake < 0) return 0;
    r->done = CreateSema(&sem);
    if (r->done < 0) { DeleteSema(r->wake); return 0; }
    thread.func = worker; thread.stack = stack; thread.stack_size = (int)stack_bytes;
    thread.gp_reg = &_gp; thread.initial_priority = priority;
    r->thread = CreateThread(&thread);
    if (r->thread < 0 || StartThread(r->thread, r) < 0) {
        if (r->thread >= 0) DeleteThread(r->thread);
        DeleteSema(r->done); DeleteSema(r->wake);
        return 0;
    }
    r->running = 1;
    return 1;
}
int reader_request(ee_reader *r, uint32_t map, const char *path, long offset,
                   size_t bytes, staging_ticket *ticket) {
    if (!r->running || !path || strlen(path) >= READER_PATH_CAP ||
        offset < 0 || bytes > LONG_MAX || offset > LONG_MAX - (long)bytes) return 0;
    if (!staging_request(&r->pool, map, bytes, ticket)) return 0;
    strcpy(r->requests[ticket->slot].path, path);
    r->requests[ticket->slot].offset = offset;
    return 1;
}
void reader_pump(ee_reader *r) {
    if (!r->running) return;
    if (r->active) {
        if (PollSema(r->done) < 0) return;
        staging_complete(&r->pool, r->ticket, r->bytes, r->result == 0);
        r->active = 0;
    }
    for (unsigned i = 0; i < STAGING_SLOTS; ++i) {
        staging_slot *s = &r->pool.slots[i];
        if (s->state != ST_QUEUED) continue;
        r->ticket = (staging_ticket){s->serial, i};
        r->bytes = s->requested;
        r->destination = staging_begin(&r->pool, r->ticket);
        r->active = 1;
        SignalSema(r->wake);
        return;
    }
}
void reader_cancel_map(ee_reader *r, uint32_t map) {
    if (r->running) staging_cancel_map(&r->pool, map);
}
int reader_stop(ee_reader *r) {
    if (!r->running) return 0;
    if (r->active) return 0;
    for (unsigned i = 0; i < STAGING_SLOTS; ++i) {
        staging_state state = r->pool.slots[i].state;
        if (state != ST_FREE && state != ST_DMA && state != ST_CANCEL_DMA) return 0;
    }
    /* No outstanding read. The worker has signalled done and can only wait
     * for wake; termination cannot interrupt filesystem or consumer work. */
    if (TerminateThread(r->thread) < 0) return 0;
    DeleteThread(r->thread);
    DeleteSema(r->done); DeleteSema(r->wake);
    r->running = 0;
    return 1;
}
