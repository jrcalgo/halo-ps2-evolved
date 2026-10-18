#include "hybrid/protocol.h"
#include <stdio.h>
#include <string.h>
#define CHECK(e) do { if (!(e)) { fprintf(stderr,"hybrid check failed: %s line=%d\n",#e,__LINE__); return 1; } } while (0)

static unsigned hash_word(unsigned hash, unsigned word)
{
    unsigned i;
    for (i=0;i<4;++i) { hash ^= (word>>(i*8))&255; hash *= 16777619u; }
    return hash;
}
static int replay(unsigned cadence, unsigned *hash_out, struct hybrid_snapshot *final)
{
    struct hybrid_command command;
    struct hybrid_event event;
    struct hybrid_snapshot snapshot, saved;
    int expected_x=0;
    unsigned tick, handle=0xffffffffu, stale=0xffffffffu, hash=2166136261u;
    hybrid_reset();
    for (tick=0;tick<18000;++tick) {
        command=(struct hybrid_command){tick,handle,HYBRID_MOVE,(tick%120<60)?1:-1,0};
        if (tick%600==0) { command.action=HYBRID_CREATE;command.x=-30;command.y=0; }
        if (tick%600==598) { command.action=HYBRID_DESTROY;stale=handle; }
        if (tick%600==599) { command.action=HYBRID_MOVE;command.handle=stale; }
        CHECK(hybrid_step(&command,&event)==0);
        if (command.action==HYBRID_CREATE) { CHECK(event.accepted);handle=event.handle;expected_x=command.x; }
        if (tick%600==599) CHECK(!event.accepted);
        if (command.action==HYBRID_MOVE && event.accepted) expected_x+=command.x;
        hybrid_capture(&snapshot);
        hash=hash_word(hash,snapshot.count);
        if (snapshot.count) {
            CHECK(snapshot.count==1 && snapshot.items[0].x==expected_x && snapshot.items[0].y==0);
            hash=hash_word(hash,snapshot.items[0].handle);
            hash=hash_word(hash,(unsigned)(unsigned short)snapshot.items[0].x);
            hash=hash_word(hash,(unsigned)(unsigned short)snapshot.items[0].y);
        }
        hash=hash_word(hash,event.tick);hash=hash_word(hash,event.handle);
        hash=hash_word(hash,event.action);hash=hash_word(hash,event.accepted);
        if (cadence && tick%cadence==0) {
            hybrid_capture(&snapshot); saved=snapshot;
            /* A presentation consumer mutates its copy, never simulation storage. */
            snapshot.items[0].x=32000;
            hybrid_capture(&snapshot);CHECK(!memcmp(&snapshot,&saved,sizeof snapshot));
        }
    }
    hybrid_capture(final);
    CHECK(final->tick==18000 && final->count==0 && final->created==30 && final->destroyed==30 && final->rejected==30);
    *hash_out=hash;
    return 0;
}

int main(void)
{
    unsigned normal,suppressed,delayed;
    struct hybrid_snapshot a,b,c;
    CHECK(!replay(1,&normal,&a));
    CHECK(!replay(0,&suppressed,&b));
    CHECK(!replay(7,&delayed,&c));
    CHECK(normal==suppressed && normal==delayed);
    CHECK(!memcmp(&a,&b,sizeof a) && !memcmp(&a,&c,sizeof a));
    printf("{\"fixture\":\"hybrid-host\",\"ticks\":18000,\"created\":30,\"destroyed\":30,\"stale_rejected\":30,\"event_hash\":%u,\"presentation_independent\":true,\"status\":\"passed\"}\n",normal);
    return 0;
}
