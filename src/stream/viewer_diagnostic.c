/* Viewer-only M11 worker diagnostic. Does not replace texture streaming. */
#include "reader_ee.h"
#include "render/bsp_render.h"
#include "world/world.h"
#include "core/mem.h"
#include <string.h>
#include <stdio.h>
#include <kernel.h>
#include <stdlib.h>

static ee_reader reader;
static unsigned char storage[1024 * 1024] __attribute__((aligned(64)));
static unsigned char stack[16384] __attribute__((aligned(16)));
static staging_ticket ticket[STAGING_SLOTS];
static unsigned phase, cycle, started, unloads;
static unsigned cache_limit, cache_route, cache_evictions, cache_failures, cache_deferred;
static arena_t *level;
static world_t *world;
static char pack_path[160], tex_path[160], object_path[160];
static int bsp_index, has_tex, has_objects;
static size_t baseline_used;
static void require(int good, const char *message) {
    if (!good) { printf("[err] streaming diagnostic: %s\n", message); exit(1); }
}
void hybrid_stream_configure(arena_t *a, world_t *w, const char *pack, const char *tex,
                             int bsp, const char *objects, unsigned pages, unsigned route) {
    require(a && w && pack && strlen(pack)<sizeof pack_path,"configure");
    level=a; world=w; strcpy(pack_path,pack); bsp_index=bsp;
    has_tex=tex!=NULL; if(tex) { require(strlen(tex)<sizeof tex_path,"texture path"); strcpy(tex_path,tex); }
    has_objects=objects!=NULL; if(objects) { require(strlen(objects)<sizeof object_path,"object path"); strcpy(object_path,objects); }
    cache_limit=pages;
    cache_route=route;
    baseline_used=a->used;
}
void hybrid_stream_build(unsigned frame, const camera_t *camera, const text_batch_t *text) {
    camera_t swept;
    const camera_t *view=camera;
    if (!started) {
        require(ChangeThreadPriority(GetThreadId(),64) >= 0,"owner priority");
        require(reader_start(&reader,storage,sizeof storage,stack,sizeof stack,30),"start");
        started=1;
        printf("[stream] start storage=%u stack=%u metadata=%u\n",
               (unsigned)sizeof storage,(unsigned)sizeof stack,(unsigned)sizeof reader);
        if (cache_limit) {
            bsp_render_cache_limit(cache_limit);
            printf("[stream] cache_limit=%u physical=%u\n",cache_limit,(unsigned)bsp_render_cache_pages());
        }
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
    if (phase >= 6 && unloads < 3 && frame == 60 + unloads * 60) {
        bsp_render_clear_world();
        arena_reset(level);
        require(level->used == 0,"arena reset");
        require(world_load(world,level,pack_path,has_tex?tex_path:NULL,bsp_index)==0,"reload BSP/TEXS");
        require(bsp_render_set_world(level,&world->bsp,&world->source)==0,"restore renderer");
        if (has_objects) require(world_load_objects(world,level,object_path)==0,"reload object sections");
        require(level->used == baseline_used,"arena high-water/reload drift");
        printf("[stream] unload_reload=%u used=%u baseline=%u cache_pages=%u\n",
               unloads+1,(unsigned)level->used,(unsigned)baseline_used,(unsigned)bsp_render_cache_pages());
        unloads++;
        printf("[stream] reload_ready=%u\n",unloads);
    }
    if (phase >= 6 && unloads == 3 && frame >= 240 && phase == 6) {
        printf("[stream] map_unload_reload=passed cycles=3\n");
        phase=7;
    }
    if (cache_route) {
        static const float route[][4] = {
            {65,-95,9,-70}, {65,-145,32,84}, {110,-155,32,138}, {118,-105,32,-167},
            {100,-65,32,-122}, {25,-75,32,-44}, {18,-115,32,-2}, {30,-155,32,45},
            {65,-175,32,90}, {118,-155,32,160}, {65,-58,32,-90}, {65,-95,9,-70}
        };
        unsigned point=(frame/30u)%(sizeof route/sizeof route[0]);
        swept=*camera;
        swept.pos[0]=route[point][0]; swept.pos[1]=route[point][1]; swept.pos[2]=route[point][2];
        swept.yaw=route[point][3]*0.01745329252f;
        swept.pitch=-5.0f*0.01745329252f;
        view=&swept;
    }
    if (unloads && frame >= 60 && frame <= 62) printf("[stream] frame_build_start=%u\n",frame);
    bsp_render_build(frame,view,text);
    if (cache_limit) {
        const render_stats_t *stats=bsp_render_stats();
        cache_evictions+=stats->tex_evictions;
        cache_failures+=stats->tex_failed;
        cache_deferred+=stats->tex_deferred;
        if (frame==360) printf("[stream] texture_churn evictions=%u failed=%u deferred=%u pages=%u\n",
                               cache_evictions,cache_failures,cache_deferred,(unsigned)bsp_render_cache_pages());
    }
    if (unloads && frame >= 60 && frame <= 62) printf("[stream] frame_build_done=%u\n",frame);
}
