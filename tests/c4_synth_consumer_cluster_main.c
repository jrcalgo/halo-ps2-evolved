/* C4 synthetic-consumer parity: CE structure_cluster.surface_indices consumer.
 * structure_cluster_check() (submodules/halo-ce-universal/port/linux/game/tag_schema_collision.c:1444-1526,
 * the runtime reader of the cluster surface lists) is spliced in verbatim at the marker. Its other
 * cluster fields are set to the retail-empty state (NONE / 0) because the synthetic surface_indices
 * fixture does not carry them. tag_validate_correct is a stub that prints its formatted message. */
#include <stdint.h>
#include <stdio.h>
#include <stdarg.h>
#include <stdlib.h>
#include <string.h>

typedef int boolean;
typedef unsigned short word;
#define TRUE 1
#define FALSE 0
#define NONE (-1)
#define SHORT_MIN (-32768)
#define SHORT_MAX 32767
#define LONG_MAX_MASK 0x7fffffffL

struct tag_block { long count; void *address; };
struct tag_validation { int unused; };

static void tag_validate_correct(struct tag_validation *validation, const char *format, ...)
{
    va_list args;
    (void)validation;
    printf("CORRECT ");
    va_start(args, format);
    vprintf(format, args);
    va_end(args);
    printf("\n");
}

struct structure_surface { unsigned short vertex_indices[3]; };
struct structure_material { struct tag_block vertices; };
struct structure_lightmap { struct tag_block materials; };
struct structure_bsp {
    struct tag_block fog_planes, fog_regions, runtime_decals, lens_flare_markers;
    struct tag_block lightmaps, surfaces;
};
struct structure_cluster_schema {
    short fog_designator; short first_runtime_decal_index; word runtime_decal_count;
    word first_lens_flare_marker_index; word lens_flare_marker_count;
    struct tag_block surface_indices;
};

/* CE_CLUSTER_FUNCTIONS */

static long lm_storage[1];
static long surface_list_storage[64];

int main(void) {
    struct tag_validation validation;
    struct structure_bsp bsp;
    struct structure_cluster_schema cluster;
    struct structure_lightmap lightmaps[1];
    struct structure_material materials[8];
    struct structure_surface surfaces[16];
    struct tag_block mats;
    char line[512];
    long surface_count = 0, material_count = 0, list_count = 0, i;

    memset(&bsp, 0, sizeof(bsp));
    memset(&cluster, 0, sizeof(cluster));
    cluster.fog_designator = NONE;
    cluster.first_runtime_decal_index = NONE;
    (void)lm_storage;

    while (fgets(line, sizeof(line), stdin)) {
        char tag[16];
        char *p = line;
        if (sscanf(line, "%15s", tag) != 1) continue;
        if (!strcmp(tag, "MATERIALS")) {
            material_count = strtol(line + 9, NULL, 10);
            for (i = 0; i < material_count; i++) {
                fgets(line, sizeof(line), stdin);
                materials[i].vertices.count = strtol(line + 2, NULL, 10);
                materials[i].vertices.address = NULL;
            }
            mats.count = material_count; mats.address = materials;
        } else if (!strcmp(tag, "SURFACES")) {
            surface_count = strtol(line + 8, NULL, 10);
            for (i = 0; i < surface_count; i++) {
                char *q;
                fgets(line, sizeof(line), stdin);
                q = line + 2;
                surfaces[i].vertex_indices[0] = (unsigned short)strtol(q, &q, 10);
                surfaces[i].vertex_indices[1] = (unsigned short)strtol(q, &q, 10);
                surfaces[i].vertex_indices[2] = (unsigned short)strtol(q, &q, 10);
            }
            bsp.surfaces.count = surface_count; bsp.surfaces.address = surfaces;
        } else if (!strcmp(tag, "LIST")) {
            list_count = strtol(line + 4, &p, 10);
            for (i = 0; i < list_count; i++) surface_list_storage[i] = strtol(p, &p, 10);
            lightmaps[0].materials = mats;
            bsp.lightmaps.count = 1; bsp.lightmaps.address = lightmaps;
            cluster.surface_indices.count = list_count;
            cluster.surface_indices.address = surface_list_storage;
            printf("RUN\n");
            structure_cluster_check(&validation, &bsp, &cluster, 0);
            printf("LIST");
            for (i = 0; i < list_count; i++) printf(" %ld", surface_list_storage[i]);
            printf("\n");
        }
    }
    return 0;
}
