/* C4 synthetic-consumer parity: CE structure_material.uncompressed_vertex_data consumer.
 * structure_material_convert() (submodules/halo-ce-universal/port/linux/game/custom_edition_geometry.c:760-
 * the function end) is spliced in verbatim at the marker. The rasterizer calls are stubs that record their
 * arguments: the destination range the consumer asks for and the bytes of the synthetic data block it
 * would write into. Destination bytes beyond the data block's size are reported as OVERRUN and not written. */
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

typedef int boolean;
typedef unsigned char byte;
#define TRUE 1
#define FALSE 0
#define XBOX_POINTER(type, address) ((type *)(address))
#define XBOX_ADDRESS(address) ((void *)(address))

struct tag_block { long count; void *address; };
struct tag_data { long size; void *address; };
struct structure_material {
    struct tag_block vertices, lightmap_vertices;
    struct tag_data uncompressed_vertex_data, compressed_vertex_data;
};

enum {
    _rasterizer_vertex_type_environment_uncompressed,
    _rasterizer_vertex_type_environment_compressed,
    _rasterizer_vertex_type_environment_lightmap_uncompressed,
    _rasterizer_vertex_type_environment_lightmap_compressed
};

/* stub: vertex sizes as the CE rasterizer defines them for these types */
static long rasterizer_geometry_get_vertex_size(int type)
{
    switch (type) {
    case _rasterizer_vertex_type_environment_uncompressed: return 56;
    case _rasterizer_vertex_type_environment_compressed: return 20;
    case _rasterizer_vertex_type_environment_lightmap_uncompressed: return 20;
    default: return 12;
    }
}

static struct tag_data g_data_block;
static struct tag_data *g_data = &g_data_block;
static byte *g_data_base;

static void rasterizer_geometry_compress_vertices(int type, long count, const void *src, long src_bytes,
    void *dst, long dst_bytes)
{
    long avail = g_data->size, offset = (long)((byte *)dst - g_data_base), i;
    (void)src; (void)src_bytes; (void)type;
    printf("COMPRESS count=%ld dst_offset=%ld dst_bytes=%ld", count, offset, dst_bytes);
    if (offset + dst_bytes > avail) {
        printf(" OVERRUN need=%ld have=%ld\n", offset + dst_bytes, avail);
        return;
    }
    printf(" BYTES");
    for (i = 0; i < dst_bytes; i++) printf(" %02x", (unsigned)((byte *)dst)[i]);
    printf("\n");
}

static boolean rasterizer_vertex_buffer_new(struct tag_block *buffer, int type, long count, const void *data, long bytes)
{
    (void)data;
    printf("VB type=%d count=%ld bytes=%ld\n", type, count, bytes);
    buffer->count = count;
    return TRUE;
}

/* CE_MATERIAL_CONVERT */

int main(void) {
    struct structure_material material;
    byte *vertices;
    char line[1024];
    while (fgets(line, sizeof(line), stdin)) {
        char tag[16];
        if (sscanf(line, "%15s", tag) != 1) continue;
        if (!strcmp(tag, "DATA")) {
            long size = strtol(line + 5, NULL, 10);
            struct tag_data *data = &g_data_block;
            g_data_base = malloc((size_t)size + 1);
            memset(g_data_base, 0, (size_t)size + 1);
            data->size = size;
            data->address = g_data_base;
            /* BYTES line follows */
            fgets(line, sizeof(line), stdin);
            {
                char *p = line + 5; long i;
                for (i = 0; i < size; i++) g_data_base[i] = (byte)strtol(p, &p, 16);
            }
        } else if (!strcmp(tag, "MATERIAL")) {
            long vc, lc; int r;
            vertices = calloc(4096, 1);
            r = sscanf(line, "%*s %ld %ld", &vc, &lc);
            (void)r;
            memset(&material, 0, sizeof(material));
            material.vertices.count = vc;
            material.lightmap_vertices.count = lc;
            material.uncompressed_vertex_data = g_data_block;
            printf("CONVERT vc=%ld lc=%ld\n", vc, lc);
            printf("RESULT %d\n", (int)structure_material_convert(&material, vertices));
        }
    }
    return 0;
}
