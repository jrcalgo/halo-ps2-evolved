#include "render/upload.h"
#include "render/texcache.h"
#include <assert.h>
#include <string.h>
int main(void) {
    unsigned char memory[32*16] __attribute__((aligned(16)));
    unsigned char pixels[16] __attribute__((aligned(16)))={0};
    tc_t cache; chain_t c; const tc_entry *entry;
    for(unsigned cap=1;cap<18;cap++) {
        memset(memory,0,sizeof memory);
        chain_init(&c,memory,cap);
        chain_cnt(&c,0,0); /* earlier packet must survive */
        unsigned char prefix[16]; memcpy(prefix,memory,16);
        tc_init(&cache,1,1,2,100);
        tc_begin_frame(&cache,1);
        assert(tc_acquire(&cache,0,1,32,&entry)==TC_UPLOAD);
        int result=gs_upload_pair(&c,pixels,16,0,1,19,4,4,pixels,16,0,4,1);
        if(cap<17) {
            assert(result==-1 && c.qw==1 && !c.overflow);
            tc_cancel_claim(&cache,0);
            assert(cache.map[0]==0 && tc_pages_free(&cache)==1);
            assert(cache.upload_bytes==32 && cache.evictions==0);
            assert(tc_acquire(&cache,0,1,32,&entry)==TC_UPLOAD);
        } else assert(result==0 && c.qw==17);
        assert(!memcmp(prefix,memory,16));
    }
    chain_init(&c,memory,32);
    assert(gs_upload_pair(&c,pixels,16,0,1,19,4,4,pixels,15,0,4,1)==-1);
    assert(c.qw==0 && !c.overflow);
    c.overflow=1;
    assert(gs_upload_pair(&c,pixels,16,0,1,19,4,4,pixels,16,0,4,1)==-1);
    assert(c.qw==0 && c.overflow);
    return 0;
}
