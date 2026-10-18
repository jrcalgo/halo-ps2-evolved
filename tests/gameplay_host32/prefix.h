/* Narrow cseries boundary for whole-file integer_math.c host compilation. */
#ifndef HALO_HOST32_PROBE_PREFIX_H
#define HALO_HOST32_PROBE_PREFIX_H
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdarg.h>

_Static_assert(sizeof(long) == 4, "Xbox-width long required");
_Static_assert(sizeof(void *) == 4, "32-bit pointers required");
_Static_assert(sizeof(short) == 2, "16-bit short required");

/* Skip the platform-heavy cseries header, not the original algorithms. */
#define __CSERIES_H
typedef unsigned char byte;
typedef unsigned short word;
typedef byte boolean;
#define TRUE 1
#define FALSE 0
#define MIN(a,b) ((a)>(b)?(b):(a))
#define MAX(a,b) ((a)>(b)?(a):(b))
#define BIT_VECTOR_SIZE_IN_LONGS(count) (((count) + 31) >> 5)
#define SHORT_FIXED_TO_LONG(value) ((value) >> 8)

extern char temporary[1024];
char *probe_csprintf(char *buffer, const char *format, ...);
void probe_assert(const char *file, int line, const char *expression);
void probe_warn(const char *file, int line, const char *message);
#define csprintf probe_csprintf
#define match_assert(file,line,expr) do { if (!(expr)) probe_assert(file,line,#expr); } while (0)
#define match_vwarn(file,line,expr,message) do { if (!(expr)) probe_warn(file,line,message); } while (0)
#endif
