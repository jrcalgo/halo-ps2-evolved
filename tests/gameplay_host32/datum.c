#include "datum_prefix.h"
#include "data.h"
#include <stddef.h>

_Static_assert(sizeof(struct data_array) == 56, "Xbox datum array layout");
_Static_assert(offsetof(struct data_array, signature) == 40, "datum signature offset");
_Static_assert(offsetof(struct data_array, data) == 52, "datum storage pointer offset");
_Static_assert(sizeof(struct data_iterator) == 16, "Xbox iterator layout");
struct item { short identifier; short reserved; long value; };
_Static_assert(sizeof(struct item) == 8, "fixture slot layout");
char temporary[1024];
static int allocations, fail_allocation;
char *probe_csprintf(char *buffer, const char *format, ...)
{
    va_list args; va_start(args, format); vsnprintf(buffer, sizeof temporary, format, args); va_end(args); return buffer;
}
void probe_assert(const char *file, int line, const char *expression)
{
    fprintf(stderr, "%s:%d assertion: %s\n", file, line, expression); abort();
}
void probe_warn(const char *file, int line, const char *message)
{
    fprintf(stderr, "%s:%d warning: %s\n", file, line, message);
}
char *probe_csstrncpy(char *destination, const char *source, unsigned long size)
{
    return strncpy(destination, source, size);
}
void *probe_malloc(const char *file, int line, unsigned long size)
{
    void *p; (void)file; (void)line;
    if (fail_allocation) return NULL;
    p = malloc(size); if (p) ++allocations; return p;
}
void probe_free(const char *file, int line, void *pointer)
{
    (void)file; (void)line; if (pointer) --allocations; free(pointer);
}
#define CHECK(e) do { if (!(e)) { fprintf(stderr,"datum check failed: %s line=%d\n",#e,__LINE__); return 1; } } while (0)

int main(void)
{
    struct data_array *pool;
    struct data_iterator iterator;
    struct item *item;
    long handles[4], stale, replacement, reset;
    int i, visits = 0;
    fail_allocation = 1;
    CHECK(data_new("fixture", 4, sizeof(struct item)) == NULL && allocations == 0);
    fail_allocation = 0;
    pool = data_new("fixture", 4, sizeof(struct item));
    CHECK(pool && allocations == 1 && !pool->valid);
    CHECK(data_allocation_size(4, sizeof(struct item)) == 88);
    data_make_valid(pool);
    CHECK(pool->valid && pool->count == 0 && pool->actual_count == 0);
    for (i=0; i<4; ++i) {
        handles[i] = datum_new(pool);
        CHECK(handles[i] != NONE && (short)handles[i] == i);
        item = datum_get(pool, handles[i]);
        CHECK(item && item->value == 0 && item->reserved == 0);
        item->value = 100+i;
    }
    CHECK(datum_new(pool) == NONE && pool->actual_count == 4);
    CHECK(datum_try_and_get(pool, NONE) == NULL);
    CHECK(datum_try_and_get(pool, 0x12340005L) == NULL);
    stale = handles[1]; datum_delete(pool, stale);
    CHECK(datum_try_and_get(pool, stale) == NULL && pool->actual_count == 3);
    replacement = datum_new(pool);
    CHECK((short)replacement == 1 && replacement != stale);
    CHECK(datum_try_and_get(pool, stale) == NULL);
    item = datum_get(pool, replacement); CHECK(item && item->value == 0);
    data_iterator_new(&iterator, pool);
    while ((item = data_iterator_next(&iterator))) {
        CHECK(item == datum_get(pool, iterator.datum_index)); ++visits;
    }
    CHECK(visits == 4);
    CHECK(data_next_index(pool, NONE) == handles[0]);
    CHECK(data_prev_index(pool, NONE) == handles[3]);
    datum_delete(pool, handles[3]);
    CHECK(pool->count == 3 && pool->actual_count == 3);
    CHECK(datum_new_at_index(pool, 0x12340003L) == 0x12340003L);
    CHECK(datum_new_at_index(pool, 0x12340003L) == NONE);
    data_delete_all(pool);
    reset = datum_new(pool); CHECK(reset == handles[0]);
    data_delete_all(pool); pool->next_identifier = (short)0xffff;
    CHECK(((unsigned long)datum_new(pool) >> 16) == 0xffffUL);
    CHECK(((unsigned long)datum_new(pool) >> 16) == 0x8000UL);
    data_make_invalid(pool); CHECK(!pool->valid);
    data_make_valid(pool); CHECK(pool->actual_count == 0);
    data_dispose(pool); CHECK(allocations == 0);
    puts("{\"fixture\":\"datum\",\"abi\":\"ILP32\",\"slots\":4,\"status\":\"passed\"}");
    return 0;
}
