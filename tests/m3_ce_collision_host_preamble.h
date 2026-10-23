/* Keep glibc's declarations under host-only aliases so CE's XDK-shaped
 * long-returning strnlen and word random declarations can be parsed as-is. */
#define strnlen m3_libc_strnlen
#include <string.h>
#undef strnlen
#define random m3_libc_random
#include <stdlib.h>
#undef random

struct collision_bsp;
typedef struct { long QuadPart; } LARGE_INTEGER;
