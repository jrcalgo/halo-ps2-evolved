/* Viewer-only M11 worker diagnostic. Does not replace texture streaming. */
#include "reader_ee.h"
#include "render/bsp_render.h"
#include <stdio.h>
#include <kernel.h>
#include <stdlib.h>

static ee_reader reader;
static unsigned char storage[1024 * 1024] __attribute__((aligned(64)));
static unsigned char stack[16384] __attribute__((aligned(16)));
static staging_ticket ticket[STAGING_SLOTS];
static unsigned phase, cycle, started;
static void require(int good, const char *message) {
    if (!good) { printf("[err] streaming diagnostic: %s\n", message); exit(1); }
}
void hybrid_stream_build(unsigned frame, const camera_t *camera, const text_batch_t *text) {
    if (!started) {
        require(ChangeThreadPriority(GetThreadId(),64) >= 0,"owner priority");
        require(reader_start(&reader,storage,sizeof storage,stack,sizeof stack,30),"start");
        started=1;
        printf("[stream] start storage=%u stack=%u metadata=%u\n",
               (unsigned)sizeof storage,(unsigned)sizeof stack,(unsigned)sizeof reader);
    }
    if (phase < 6) {
        require(frame < 120,"timeout");
        reader_pump(&reader);
        switch(phase) {
        case 0:
            for (unsigned i=0;i<STAGING_SLOTS;i++)
                require(reader_request(&reader,cycle+1,"stream-fixture.bin",0,256,&ticket[i]),"queue");
            { staging_ticket extra;
              require(!reader_request(&reader,99,"stream-fixture.bin",0,256,&extra),"exhaustion"); }
            reader_pump(&reader);
            /* Cancellation before owner completion polling must retain the
             * active buffer even if the worker has already finished the I/O. */
            reader_cancel_map(&reader,cycle+1);
            require(!staging_map_drained(&reader.pool,cycle+1),"premature drain");
            require(!reader_stop(&reader),"premature shutdown");
            phase=1; break;
        case 1:
            if (!staging_map_drained(&reader.pool,cycle+1)) break;
            require(reader_request(&reader,100+cycle,"stream-fixture.bin",0,256,&ticket[0]),"reload");
            phase=2; break;
        case 2: {
            const unsigned char *p=staging_acquire(&reader.pool,ticket[0]);
            if (!p) break;
            for(unsigned i=0;i<256;i++) require(p[i]==(unsigned char)(i^0xa5),"contents");
            reader_cancel_map(&reader,100+cycle);
            require(!staging_map_drained(&reader.pool,100+cycle),"held drain");
            require(staging_release(&reader.pool,ticket[0]),"release");
            require(staging_map_drained(&reader.pool,100+cycle),"released drain");
            printf("[stream] cycle=%u cancel/reload/contents/drain=ok\n",cycle);
            if (++cycle < 3) phase=0;
            else phase=3;
            break;
        }
        case 3:
            require(reader_request(&reader,999,"stream-fixture.bin",255,256,&ticket[0]),"short queue");
            phase=4; break;
        case 4:
            if (reader.pool.slots[ticket[0].slot].state!=ST_FREE) break;
            require(!staging_acquire(&reader.pool,ticket[0]),"short exposed");
            require(reader_stop(&reader),"stop");
            printf("[stream] passed cycles=3 short-read=discarded high=%u reserved=%u\n",
                   (unsigned)reader.pool.high_water,
                   (unsigned)(sizeof storage+sizeof stack+sizeof reader));
            phase=6; break;
        }
    }
    bsp_render_build(frame,camera,text);
}
