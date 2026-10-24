#include "staging.h"
#include <string.h>

static void increment(uint32_t *value) {
    if (*value != UINT32_MAX) ++*value;
}
static staging_slot *lookup(staging_pool *p, staging_ticket t) {
    if (!p || t.slot >= STAGING_SLOTS || !t.serial) return NULL;
    staging_slot *s = &p->slots[t.slot];
    return s->state != ST_FREE && s->serial == t.serial ? s : NULL;
}
int staging_init(staging_pool *p, void *storage, size_t bytes) {
    if (!p || !storage || bytes < STAGING_SLOTS) return 0;
    memset(p, 0, sizeof(*p));
    p->storage = storage;
    p->stride = bytes / STAGING_SLOTS;
    return 1;
}
int staging_reset(staging_pool *p) {
    if (!p || !p->storage || !p->stride) return 0;
    for (unsigned i = 0; i < STAGING_SLOTS; ++i) {
        if (p->slots[i].state != ST_FREE) {
            increment(&p->reset_failures);
            return 0;
        }
    }
    memset(p->slots, 0, sizeof(p->slots));
    increment(&p->reset_count);
    return 1;
}
int staging_request(staging_pool *p, uint32_t map, size_t bytes, staging_ticket *t) {
    if (!p) return 0;
    if (!p->storage || !t || !bytes || bytes > p->stride || p->next_serial == UINT64_MAX) {
        increment(&p->request_failures);
        return 0;
    }
    for (unsigned i = 0; i < STAGING_SLOTS; ++i) {
        staging_slot *s = &p->slots[i];
        if (s->state != ST_FREE) continue;
        *s = (staging_slot){ST_QUEUED, ++p->next_serial, map, bytes};
        *t = (staging_ticket){s->serial, i};
        size_t used = 0;
        for (unsigned j = 0; j < STAGING_SLOTS; ++j)
            if (p->slots[j].state != ST_FREE) used += p->stride;
        if (used > p->high_water) p->high_water = used;
        return 1;
    }
    increment(&p->request_failures);
    return 0;
}
void *staging_begin(staging_pool *p, staging_ticket t) {
    staging_slot *s = lookup(p, t);
    if (!s || s->state != ST_QUEUED) return NULL;
    s->state = ST_READING;
    return p->storage + t.slot * p->stride;
}
int staging_complete(staging_pool *p, staging_ticket t, size_t bytes, int ok) {
    staging_slot *s = lookup(p, t);
    if (!s || (s->state != ST_READING && s->state != ST_CANCEL_READING)) return 0;
    if (s->state == ST_CANCEL_READING || !ok || bytes != s->requested) {
        s->state = ST_FREE;
        return 0;
    }
    s->state = ST_READY;
    return 1;
}
const void *staging_acquire(staging_pool *p, staging_ticket t) {
    staging_slot *s = lookup(p, t);
    if (!s || s->state != ST_READY) return NULL;
    s->state = ST_HELD;
    return p->storage + t.slot * p->stride;
}
int staging_commit(staging_pool *p, staging_ticket t, const void *src) {
    staging_slot *s = lookup(p, t);
    if (!s || s->state != ST_QUEUED || !src) return 0;
    memcpy(p->storage + t.slot * p->stride, src, s->requested);
    s->state = ST_READY;
    return 1;
}
int staging_dma_submit(staging_pool *p, staging_ticket t) {
    staging_slot *s = lookup(p, t);
    if (!s || s->state != ST_HELD) return 0;
    s->state = ST_DMA;
    return 1;
}
int staging_dma_complete(staging_pool *p, staging_ticket t) {
    staging_slot *s = lookup(p, t);
    if (!s || (s->state != ST_DMA && s->state != ST_CANCEL_DMA)) return 0;
    s->state = s->state == ST_DMA ? ST_HELD : ST_CANCEL_HELD;
    return 1;
}
int staging_release(staging_pool *p, staging_ticket t) {
    staging_slot *s = lookup(p, t);
    if (!s || (s->state != ST_HELD && s->state != ST_CANCEL_HELD)) return 0;
    s->state = ST_FREE;
    return 1;
}
void staging_cancel_map(staging_pool *p, uint32_t map) {
    for (unsigned i = 0; i < STAGING_SLOTS; ++i) {
        staging_slot *s = &p->slots[i];
        if (s->map != map) continue;
        switch (s->state) {
        case ST_READING: s->state = ST_CANCEL_READING; break;
        case ST_HELD: s->state = ST_CANCEL_HELD; break;
        case ST_DMA: s->state = ST_CANCEL_DMA; break;
        case ST_QUEUED: case ST_READY: s->state = ST_FREE; break;
        default: break;
        }
    }
}
int staging_map_drained(const staging_pool *p, uint32_t map) {
    for (unsigned i = 0; i < STAGING_SLOTS; ++i)
        if (p->slots[i].state != ST_FREE && p->slots[i].map == map) return 0;
    return 1;
}
