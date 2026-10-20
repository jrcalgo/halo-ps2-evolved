/* Sample the packed CE shotgun cone for a fixed seed, as play_ee does. */
#include "game/shot.h"
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define MAX_WEAPONS 32
#define DIRECTION_COUNT 1026

/* Direct transcription of the pinned CE seed_random_vector_in_cone3d,
 * seed_random_range, normalize3d, and rotate_vector_about_axis equations.
 * unsigned long is explicitly 32-bit here, as it is in the source target ABI. */
static uint16_t ce_seed_random(uint32_t *seed)
{
    *seed = *seed * 1664525u + 1013904223u;
    return (uint16_t)(*seed >> 16);
}

static uint32_t ce_seed_random_range(uint32_t *seed, uint32_t upper)
{
    return upper * (uint32_t)ce_seed_random(seed) >> 16;
}

static void ce_cone(const float axis[3], const float (*directions)[3],
                    const shot_cone *cone, uint32_t *seed, float result[3])
{
    float random[3], n[3], magnitude, angle, sine, cosine, dot, cross[3];
    unsigned i;
    memcpy(result, axis, 3 * sizeof(float));
    memcpy(random, directions[ce_seed_random_range(seed, DIRECTION_COUNT)], sizeof random);
    n[0] = axis[1] * random[2] - axis[2] * random[1];
    n[1] = axis[2] * random[0] - axis[0] * random[2];
    n[2] = axis[0] * random[1] - axis[1] * random[0];
    magnitude = sqrtf(n[0] * n[0] + n[1] * n[1] + n[2] * n[2]);
    if (fabsf(magnitude) < 0.0001f) return;
    for (i = 0; i < 3; i++) n[i] *= 1.0f / magnitude;
    angle = cone->inner_cone_angle +
        (cone->error_upper_bound - cone->inner_cone_angle) *
        ((float)ce_seed_random(seed) / 65535.0f);
    sine = sinf(angle);
    cosine = cosf(angle);
    dot = n[0] * result[0] + n[1] * result[1] + n[2] * result[2];
    cross[0] = n[2] * result[1] - result[2] * n[1];
    cross[1] = n[0] * result[2] - result[0] * n[2];
    cross[2] = n[1] * result[0] - result[1] * n[0];
    for (i = 0; i < 3; i++)
        result[i] = cosine * result[i] + dot * (1.0f - cosine) * n[i] - sine * cross[i];
}

int main(int argc, char **argv)
{
    FILE *file;
    long length;
    unsigned char *blob;
    unsigned short weapons, directions;
    unsigned char *mark;
    unsigned char *records;
    unsigned char *table;
    shot_cone shotgun;
    float vectors[DIRECTION_COUNT][3];
    float axis[3] = {1.0f, 0.0f, 0.0f};
    uint32_t seed = 1;
    uint32_t ce_seed = 1;
    int i;
    long scan;
    if (argc != 2 || !(file = fopen(argv[1], "rb"))) return 1;
    if (fseek(file, 0, SEEK_END) != 0 || (length = ftell(file)) <= 0 || fseek(file, 0, SEEK_SET) != 0)
        return 2;
    blob = malloc((size_t)length);
    if (!blob || fread(blob, 1, (size_t)length, file) != (size_t)length) return 3;
    fclose(file);
    mark = NULL;
    for (scan = 0; scan + 4 <= length; scan++) {
        if (memcmp(blob + scan, "RND1", 4) == 0) {
            mark = blob + scan;
            break;
        }
    }
    if (!mark || mark + 8 > blob + length) return 4;
    memcpy(&weapons, mark + 4, 2);
    memcpy(&directions, mark + 6, 2);
    if (weapons != 23 || directions != DIRECTION_COUNT) return 5;
    records = mark + 8;
    memcpy(&shotgun, records + 2 * sizeof(shot_cone), sizeof shotgun);
    table = records + weapons * sizeof(shot_cone);
    if ((size_t)(blob + length - table) < sizeof vectors) return 6;
    memcpy(vectors, table, sizeof vectors);
    for (i = 0; i < 15; i++) {
        float forward[3], reference[3];
        shot_random_cone(axis, (const float (*)[3])vectors, directions, &shotgun, 0.0f, &seed, forward);
        ce_cone(axis, (const float (*)[3])vectors, &shotgun, &ce_seed, reference);
        if (seed != ce_seed || fabsf(forward[0] - reference[0]) > 2e-7f ||
            fabsf(forward[1] - reference[1]) > 2e-7f ||
            fabsf(forward[2] - reference[2]) > 2e-7f) return 7;
        printf("%d %.9f %.9f %.9f %08x\n", i, forward[0], forward[1], forward[2], seed);
    }
    free(blob);
    return 0;
}
