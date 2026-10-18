#include "stream/staging.h"
#include <assert.h>
#include <string.h>
int main(void) {
    unsigned char storage[1024];
    staging_pool p;
    staging_ticket t[4], extra, old;
    assert(!staging_init(&p, storage, 3));
    assert(staging_init(&p, storage, sizeof storage));
    assert(!staging_request(&p, 1, 257, &extra));
    for (unsigned i=0;i<4;i++) assert(staging_request(&p, 1, 256, &t[i]));
    assert(p.high_water == sizeof storage);
    assert(!staging_request(&p, 2, 1, &extra));
    memset(staging_begin(&p,t[0]), 0x5a,256);
    assert(!staging_begin(&p,t[0]));
    assert(staging_begin(&p,t[1]));
    assert(staging_complete(&p,t[1],256,1));
    assert(staging_acquire(&p,t[1]));
    assert(staging_begin(&p,t[2]));
    assert(staging_complete(&p,t[2],256,1));
    staging_cancel_map(&p,1); /* reading, held, ready and queued */
    assert(!staging_map_drained(&p,1));
    assert(!staging_acquire(&p,t[2]));
    assert(staging_request(&p,2,256,&extra));
    assert(extra.slot != t[0].slot && extra.slot != t[1].slot);
    assert(!staging_complete(&p,t[0],256,1));
    assert(staging_release(&p,t[1]));
    assert(staging_map_drained(&p,1));
    old=extra;
    assert(staging_begin(&p,extra));
    assert(!staging_complete(&p,extra,255,1)); /* short read */
    assert(staging_request(&p,2,256,&extra));
    assert(!staging_complete(&p,old,256,1)); /* reused slot */
    assert(staging_begin(&p,extra));
    assert(!staging_complete(&p,extra,256,0));
    assert(staging_request(&p,3,256,&extra));
    assert(staging_begin(&p,extra));
    assert(staging_complete(&p,extra,256,1));
    assert(staging_acquire(&p,extra));
    assert(!staging_acquire(&p,extra));
    assert(staging_release(&p,extra));
    assert(!staging_release(&p,extra));
    p.next_serial=UINT64_MAX;
    assert(!staging_request(&p,3,1,&extra));
    return 0;
}
