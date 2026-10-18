#include "render/texcache.h"
#include <assert.h>
#include <stdint.h>

static tc_t cache;
static void invariant(void) {
    unsigned pages[8]={0}, clut[8]={0};
    for(unsigned e=0;e<TC_MAX_ENTRIES;e++) if(cache.entry[e].valid) {
        const tc_entry *x=&cache.entry[e];
        assert(x->key<cache.max_keys && cache.map[x->key]==e+1);
        assert(x->pages && x->first_page+x->pages<=cache.total_pages);
        assert(x->clut_slot<cache.clut_slots && cache.clut_used[x->clut_slot]);
        assert(!clut[x->clut_slot]++);
        for(unsigned p=x->first_page;p<x->first_page+x->pages;p++) {
            assert(!pages[p]++ && cache.owner[p]==e+1);
        }
    }
    for(unsigned p=0;p<cache.total_pages;p++) assert((cache.owner[p]!=0)==(pages[p]!=0));
    for(unsigned k=0;k<cache.max_keys;k++) if(cache.map[k]) {
        assert(cache.map[k]<=TC_MAX_ENTRIES);
        assert(cache.entry[cache.map[k]-1].valid && cache.entry[cache.map[k]-1].key==k);
    }
}
int main(void) {
    const tc_entry *e;
    tc_init(&cache,8,8,64,4096);
    uint32_t frame=1, random=0x4d595df4u;
    for(unsigned step=0;step<200000;step++) {
        random=random*1664525u+1013904223u;
        if(step%7==0) { frame+=2; tc_begin_frame(&cache,frame); }
        unsigned key=(random>>8)%64;
        if((random&31)==0) {
            tc_cancel_claim(&cache,key); /* allowed only for a newly returned upload */
        } else {
            tc_result result=tc_acquire(&cache,key,1+((random>>16)%3),64,&e);
            if(result==TC_UPLOAD) {
                assert(e && e->valid && e->key==key && e->pending_upload);
                if((random&3)==0) tc_cancel_claim(&cache,key);
                else tc_commit_claim(&cache,key);
            } else if(result==TC_HIT) { assert(e && e->key==key); tc_cancel_claim(&cache,key); assert(cache.map[key]); }
            else assert(result==TC_FULL || result==TC_DEFER);
        }
        if(step%31==0) invariant();
    }
    invariant();
    for(unsigned k=0;k<64;k++) tc_cancel_claim(&cache,k);
    invariant();
    tc_flush(&cache);
    assert(tc_pages_free(&cache)==8);
    invariant();
    return 0;
}
