/* Host shim for source/memory/memory_pool.c: the CE helpers it calls, with
 * the same contracts, and no game headers. */
#ifndef HCU_C2_ALLOC_A_SHIM_CSERIES_H
#define HCU_C2_ALLOC_A_SHIM_CSERIES_H

#include <stddef.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

typedef unsigned char byte;
typedef int boolean;
#define TRUE 1
#define FALSE 0

#define shim_assert_failed(file, line, text) \
	do { fprintf(stderr, "assert %s:%d: %s\n", file, line, text); abort(); } while (0)
#define match_assert(file, line, expr) \
	do { if (!(expr)) shim_assert_failed(file, line, #expr); } while (0)
/* The message argument is never built on the host. */
#define match_vassert(file, line, expr, message) \
	do { if (!(expr)) shim_assert_failed(file, line, #expr); } while (0)

#define csmemset(buffer, value, size) memset((buffer), (value), (size))
#define csmemcpy(destination, source, size) memcpy((destination), (source), (size))
#define csmemmove(destination, source, size) memmove((destination), (source), (size))
#define csstrncpy(destination, source, size) strncpy((destination), (source), (size))
#define temporary NULL
#define csprintf(buffer, ...) ((void)0)

/* CE's match_malloc/match_free route to the debug heap; the host uses libc. */
#define match_malloc(file, line, size) malloc((size))
#define match_free(file, line, pointer) free((pointer))

#endif
