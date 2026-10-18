#include "hybrid/boundary.h"
#ifdef HALO_PS2
#include <kernel.h>
#endif

char temporary[1024];

char *probe_csprintf(char *buffer, const char *format, ...)
{
    va_list args;
    va_start(args, format);
    vsnprintf(buffer, sizeof temporary, format, args);
    va_end(args);
    return buffer;
}

char *probe_csstrncpy(char *destination, const char *source, unsigned long size)
{
    return strncpy(destination, source, size);
}

void probe_assert(const char *file, int line, const char *expression)
{
#ifdef HALO_PS2
    printf("HALO_PS2_FAIL reason=assertion file=%s line=%d expression=%s\n", file, line, expression);
    for (;;) SleepThread();
#else
    fprintf(stderr, "%s:%d assertion: %s\n", file, line, expression);
    abort();
#endif
}

void probe_warn(const char *file, int line, const char *message)
{
#ifdef HALO_PS2
    printf("%s:%d warning: %s\n", file, line, message);
#else
    fprintf(stderr, "%s:%d warning: %s\n", file, line, message);
#endif
}

void *probe_malloc(const char *file, int line, unsigned long size)
{
    (void)file;
    (void)line;
    return malloc(size);
}

void probe_free(const char *file, int line, void *pointer)
{
    (void)file;
    (void)line;
    free(pointer);
}
