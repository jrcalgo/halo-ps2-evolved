/* Synthetic proof using unchanged Halo datum and integer-point operations.
 * This is not a Halo player, physics implementation or complete object system.
 */
#include "hybrid/protocol.h"
#include "data.h"
#include "integer_math.h"
#include <string.h>
struct synthetic_object { short identifier, reserved; point2d position; };
static unsigned char storage[sizeof(struct data_array) + HYBRID_CAPACITY * sizeof(struct synthetic_object)] __attribute__((aligned(16)));
static struct data_array *pool;
static uint32_t tick, created, destroyed, rejected;

void hybrid_reset(void)
{
    pool = (struct data_array *)storage;
    memset(storage, 0, sizeof storage);
    data_initialize(pool, "hybrid", HYBRID_CAPACITY, sizeof(struct synthetic_object));
    data_make_valid(pool);
    tick = created = destroyed = rejected = 0;
}

int hybrid_step(const struct hybrid_command *command, struct hybrid_event *event)
{
    struct synthetic_object *object;
    long handle = (long)command->handle;
    if (!pool || command->tick != tick) return -1;
    *event = (struct hybrid_event){ tick, command->handle, command->action, 0 };
    switch (command->action) {
    case HYBRID_NONE: event->accepted = 1; break;
    case HYBRID_CREATE:
        handle = datum_new(pool);
        if (handle != NONE) {
            object = datum_get(pool, handle);
            set_point2d(&object->position, command->x, command->y);
            event->handle = (uint32_t)handle;
            event->accepted = 1;
            ++created;
        }
        break;
    case HYBRID_MOVE:
        object = datum_try_and_get(pool, handle);
        if (object) {
            offset_point2d(&object->position, command->x, command->y);
            event->accepted = 1;
        }
        break;
    case HYBRID_DESTROY:
        if (datum_try_and_get(pool, handle)) {
            datum_delete(pool, handle);
            event->accepted = 1;
            ++destroyed;
        }
        break;
    default: return -1;
    }
    if (!event->accepted) ++rejected;
    ++tick;
    return 0;
}

void hybrid_capture(struct hybrid_snapshot *snapshot)
{
    struct data_iterator iterator;
    struct synthetic_object *object;
    memset(snapshot, 0, sizeof *snapshot);
    snapshot->tick = tick; snapshot->created = created;
    snapshot->destroyed = destroyed; snapshot->rejected = rejected;
    data_iterator_new(&iterator, pool);
    while ((object = data_iterator_next(&iterator))) {
        struct hybrid_item *item = &snapshot->items[snapshot->count++];
        item->handle = (uint32_t)iterator.datum_index;
        item->x = object->position.x; item->y = object->position.y;
    }
}
