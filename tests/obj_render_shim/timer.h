#include <stdint.h>
static uint32_t host_ticks;
static inline uint32_t timer_cycles(void) { return ++host_ticks; }
static inline float timer_ms(uint32_t a, uint32_t b) { return (float)(b - a); }
