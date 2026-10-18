/* M11 hard upload cap and frame-wrap lifetime regressions. No GS/EE claim. */
#include "render/texcache.h"
#include <stdint.h>
#include <stdio.h>
static tc_t t;
#define CHECK(x) do { if(!(x)){fprintf(stderr,"failed: %s line %d\n",#x,__LINE__);return 1;} }while(0)
int main(void)
{
    const tc_entry *e=NULL;
    tc_init(&t,2,2,8,100);
    tc_begin_frame(&t,1);
    CHECK(tc_acquire(&t,0,1,101,&e)==TC_FULL);
    CHECK(tc_pages_free(&t)==2 && t.upload_bytes==0 && t.map[0]==0);
    CHECK(tc_acquire(&t,0,1,100,&e)==TC_UPLOAD);
    CHECK(tc_acquire(&t,1,1,1,&e)==TC_DEFER);
    CHECK(t.upload_bytes==100 && t.map[1]==0);
    tc_init(&t,2,2,8,UINT32_MAX);
    tc_begin_frame(&t,1);
    CHECK(tc_acquire(&t,0,1,UINT32_MAX-1,&e)==TC_UPLOAD);
    CHECK(tc_acquire(&t,1,1,10,&e)==TC_DEFER);
    CHECK(t.upload_bytes==UINT32_MAX-1);
    tc_init(&t,1,1,8,100);
    tc_begin_frame(&t,UINT32_MAX-1);
    CHECK(tc_acquire(&t,0,1,1,&e)==TC_UPLOAD);
    tc_begin_frame(&t,UINT32_MAX);
    CHECK(tc_acquire(&t,1,1,1,&e)==TC_DEFER);
    tc_begin_frame(&t,0);
    CHECK(tc_acquire(&t,1,1,1,&e)==TC_UPLOAD && t.map[0]==0);
    /* Wrapped LRU: UINT32_MAX-2 is older than frame 0. */
    tc_init(&t,2,2,8,100);
    tc_begin_frame(&t,UINT32_MAX-2);
    CHECK(tc_acquire(&t,0,1,1,&e)==TC_UPLOAD);
    tc_begin_frame(&t,0);
    CHECK(tc_acquire(&t,1,1,1,&e)==TC_UPLOAD);
    tc_begin_frame(&t,2);
    CHECK(tc_acquire(&t,2,1,1,&e)==TC_UPLOAD);
    CHECK(t.map[0]==0 && t.map[1]!=0);
    tc_flush(&t);
    CHECK(tc_pages_free(&t)==2);
    for(unsigned k=0;k<t.max_keys;k++) CHECK(!t.map[k]);
    puts("M11 texture hard-cap/frame-wrap regressions passed");return 0;
}
