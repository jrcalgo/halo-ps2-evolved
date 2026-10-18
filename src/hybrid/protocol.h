#ifndef HALO_HYBRID_PROTOCOL_H
#define HALO_HYBRID_PROTOCOL_H
#include <stdint.h>
/* Synthetic M08 protocol. No platform pointers, DMA state or borrowed storage. */
enum { HYBRID_NONE, HYBRID_CREATE, HYBRID_MOVE, HYBRID_DESTROY };
#define HYBRID_CAPACITY 4
struct hybrid_command {
    uint32_t tick, handle;
    uint16_t action;
    int16_t x, y;
};
struct hybrid_event { uint32_t tick, handle; uint16_t action, accepted; };
struct hybrid_item { uint32_t handle; int16_t x, y; };
struct hybrid_snapshot {
    uint32_t tick, count, created, destroyed, rejected;
    struct hybrid_item items[HYBRID_CAPACITY];
};
void hybrid_reset(void);
int hybrid_step(const struct hybrid_command *, struct hybrid_event *);
void hybrid_capture(struct hybrid_snapshot *);
#endif
