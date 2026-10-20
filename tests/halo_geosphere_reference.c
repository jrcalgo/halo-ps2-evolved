/* Emit the table from the unchanged pinned Halo CE geosphere implementation. */
#define BUILDING_CSERIES 1
#include "cseries.h"
#include "math/real_math.h"
#include "math/geometry.h"
#include <stdio.h>
#include <stdlib.h>

void *debug_malloc(unsigned int size, boolean clear, const char *file, long line)
{
    (void)file;
    (void)line;
    return clear ? calloc(1, size) : malloc(size);
}

void debug_free(void *pointer, const char *file, long line)
{
    (void)file;
    (void)line;
    free(pointer);
}

void display_assert(char *expression, char *file, long line, boolean fatal)
{
    (void)expression;
    (void)file;
    (void)line;
    (void)fatal;
    abort();
}

void system_exit(long code)
{
    exit((int)code);
}

int main(void)
{
    struct geosphere *sphere = geosphere_new(16);
    if (!sphere || sphere->vertex_count != 1026) return 1;
    if (fwrite(sphere->vertices, sizeof(*sphere->vertices), sphere->vertex_count, stdout) !=
        sphere->vertex_count) return 2;
    geosphere_dispose(sphere);
    return 0;
}
