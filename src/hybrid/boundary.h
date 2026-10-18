/* Project CRT and allocation boundary for the hybrid proof.
 * Gameplay modules see these names. This header has no GS, DMA, or VU state.
 */
#ifndef HALO_HYBRID_BOUNDARY_H
#define HALO_HYBRID_BOUNDARY_H
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

_Static_assert(sizeof(long) == 4, "Xbox-width long required");
_Static_assert(sizeof(void *) == 4, "32-bit pointers required");
_Static_assert(sizeof(short) == 2, "16-bit short required");

#define __CSERIES_H
typedef unsigned char byte;
typedef unsigned short word;
typedef byte boolean;
#define TRUE 1
#define FALSE 0
#define NONE (-1)
#define MIN(a,b) ((a)>(b)?(b):(a))
#define MAX(a,b) ((a)>(b)?(a):(b))
#define BIT_VECTOR_SIZE_IN_LONGS(count) (((count) + 31) >> 5)
#define SHORT_FIXED_TO_LONG(value) ((value) >> 8)
#define csmemset memset
#define csmemcpy memcpy

extern char temporary[1024];
char *probe_csprintf(char *buffer, const char *format, ...);
char *probe_csstrncpy(char *destination, const char *source, unsigned long size);
void probe_assert(const char *file, int line, const char *expression);
void probe_warn(const char *file, int line, const char *message);
void *probe_malloc(const char *file, int line, unsigned long size);
void probe_free(const char *file, int line, void *pointer);

#define csprintf probe_csprintf
#define csstrncpy probe_csstrncpy
#define match_assert(file,line,expr) do { if (!(expr)) probe_assert(file,line,#expr); } while (0)
#define match_vassert(file,line,expr,message) do { if (!(expr)) probe_assert(file,line,message); } while (0)
#define match_vwarn(file,line,expr,message) do { if (!(expr)) probe_warn(file,line,message); } while (0)
#define match_malloc(file,line,size) probe_malloc(file,line,size)
#define match_free(file,line,pointer) probe_free(file,line,pointer)
#endif
