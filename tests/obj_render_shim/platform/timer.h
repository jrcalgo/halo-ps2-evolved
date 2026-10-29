#ifndef TEST_OBJ_RENDER_PLATFORM_TIMER_H
#define TEST_OBJ_RENDER_PLATFORM_TIMER_H
#include <stdint.h>
static uint32_t obj_render_host_ticks;
static inline uint32_t timer_cycles(void) { return ++obj_render_host_ticks; }
static inline float timer_ms(uint32_t start, uint32_t end) { return (float)(end - start); }
#endif
