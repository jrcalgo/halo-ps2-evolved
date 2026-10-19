#include "game/arsenal.h"
#include <stdio.h>
#include <stdlib.h>

int main(int argc, char **argv)
{
    FILE *file;
    int count, i, n;
    if (argc != 2) return 1;
    file = fopen(argv[1], "rb");
    if (!file) return 1;
    if (fread(&count, sizeof count, 1, file) != 1) return 1;
    for (i = 0; i < count; i++) {
        arsenal_spec spec;
        arsenal_result result;
        int tick;
        if (fread(&spec, sizeof spec, 1, file) != 1) return 1;
        arsenal_run(&spec, 90, &result);
        printf("RESULT %s shots %d pellets %d over %d loaded %d melee %.3f ticks",
            spec.name, result.shots, result.pellets, result.overheated,
            result.loaded, result.melee);
        for (tick = 0; tick < result.tick_count; tick++) printf(" %d", result.ticks[tick]);
        printf("\n");
        n = i;
    }
    (void)n;
    fclose(file);
    return 0;
}
