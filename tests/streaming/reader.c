#define _POSIX_C_SOURCE 200809L
#include <kernel.h>
#include "stream/reader_ee.h"
#include <assert.h>
#include <pthread.h>
#include <semaphore.h>
#include <string.h>
#include <time.h>
#include <errno.h>
void *_gp;
static sem_t sems[2], entered, proceed;
static int next_sem;
static pthread_t thread;
static void (*entry)(void *);
static void *argument;
int CreateSema(ee_sema_t *s) { int i=next_sem++; assert(i<2); assert(!sem_init(&sems[i],0,s->init_count)); return i; }
int DeleteSema(int i) { return sem_destroy(&sems[i]); }
int WaitSema(int i) { int result; do { result=sem_wait(&sems[i]); } while(result && errno==EINTR); return result; }
int SignalSema(int i) { return sem_post(&sems[i]); }
int PollSema(int i) { return sem_trywait(&sems[i]); }
int CreateThread(ee_thread_t *t) { entry=t->func; return 0; }
static void *trampoline(void *a) { (void)a; entry(argument); return NULL; }
int StartThread(int i,void *arg) { (void)i; argument=arg; return pthread_create(&thread,NULL,trampoline,NULL); }
int TerminateThread(int i) { (void)i; assert(!pthread_cancel(thread)); return pthread_join(thread,NULL); }
int DeleteThread(int i) { (void)i; return 0; }
int file_read_at(const char *path,long offset,void *dst,size_t bytes) {
    assert(!strcmp(path,"fixture")); assert(offset==7);
    sem_post(&entered); /* deterministically hold the actual worker mid-read */
    while(sem_wait(&proceed) && errno==EINTR) {}
    memset(dst,0x63,bytes); return 0;
}
static void pump_until(ee_reader *r, staging_ticket t, staging_state state) {
    struct timespec pause={0,1000000};
    for(int i=0;i<2000;i++) {
        reader_pump(r);
        if(r->pool.slots[t.slot].state==state) return;
        nanosleep(&pause,NULL);
    }
    assert(!"worker timed out");
}
int main(void) {
    static unsigned char stack[16384] __attribute__((aligned(16)));
    unsigned char storage[1024]; ee_reader r; staging_ticket a,b;
    sem_init(&entered,0,0); sem_init(&proceed,0,0);
    assert(reader_start(&r,storage,sizeof storage,stack,sizeof stack,80));
    assert(!reader_request(&r,1,"fixture",-1,256,&a));
    assert(reader_request(&r,1,"fixture",7,256,&a));
    reader_pump(&r); sem_wait(&entered);
    reader_cancel_map(&r,1);
    assert(!reader_stop(&r));
    assert(!staging_map_drained(&r.pool,1));
    assert(reader_request(&r,2,"fixture",7,256,&b));
    assert(a.slot!=b.slot);
    sem_post(&proceed);
    pump_until(&r,a,ST_FREE);
    sem_wait(&entered); sem_post(&proceed);
    pump_until(&r,b,ST_READY);
    const unsigned char *data=staging_acquire(&r.pool,b);
    assert(data && data[0]==0x63 && data[255]==0x63);
    reader_cancel_map(&r,2);
    assert(!reader_stop(&r));
    assert(staging_release(&r.pool,b));
    assert(staging_map_drained(&r.pool,1));
    assert(staging_map_drained(&r.pool,2));
    assert(reader_stop(&r));
    assert(!reader_request(&r,3,"fixture",7,256,&b));
    sem_destroy(&entered); sem_destroy(&proceed);
    return 0;
}
