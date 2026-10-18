/* Narrow CRT/allocation boundary for the unchanged whole data.c module. */
#include "prefix.h"
#define NONE (-1)
#define csmemset memset
#define csmemcpy memcpy
char *probe_csstrncpy(char *destination, const char *source, unsigned long size);
#define csstrncpy probe_csstrncpy
#define match_vassert(file,line,expr,message) do { if (!(expr)) probe_assert(file,line,message); } while (0)
void *probe_malloc(const char *file, int line, unsigned long size);
void probe_free(const char *file, int line, void *pointer);
#define match_malloc(file,line,size) probe_malloc(file,line,size)
#define match_free(file,line,pointer) probe_free(file,line,pointer)
