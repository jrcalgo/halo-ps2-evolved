/* C4 synthetic-consumer parity: CE leaf_map consumers driven over decoded synthetic fixtures.
 * Verbatim CE bodies (submodules/halo-ce-universal/source/structures/leaf_map.c) are spliced at the marker:
 *   leaf_map_close_portal        (485-517 region; reads leaves, portals, map_leaf.portal_designators)
 *   leaf_map_leaf_is_closed      (reads map_leaf.portal_designators)
 *   leaf_map_get_leaf_bounds     (reads map_leaf.faces when the leaf has no portal designators)
 * The input is a text case list written by tests/c4_synth_consumer_oracle.py from the walker-validated
 * synthetic fixtures. match_assert is reduced to a printed ASSERT line. Helpers that CE implements
 * elsewhere (projection, distance) are stubs: the faces used here carry no vertices, so they are never
 * reached; a face with vertices aborts the harness rather than guessing. */
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <float.h>
#include <limits.h>
#include <math.h>

typedef int boolean;
typedef float real;
#define TRUE 1
#define FALSE 0
#define REAL_MAX FLT_MAX
#define REAL_MIN (-FLT_MAX)
#define LONG_MAX_MASK 0x7fffffffL
#define LONG_MIN_BIT (-2147483647L - 1L)
#define match_assert(file, line, expr) do { if (!(expr)) printf("ASSERT %d\n", (line)); } while (0)

struct tag_block { long count; void *address; };
#define TAG_BLOCK_GET_ELEMENT(block, index, type) ((type *)((char *)(block)->address + (index) * sizeof(type)))

typedef struct { real x, y, z; } real_point3d;
typedef struct { real x, y; } real_point2d;
typedef struct { real i, j, k; } real_vector3d;
typedef struct { real_vector3d n; real d; } real_plane3d;
typedef struct { real x0, x1, y0, y1, z0, z1; } real_rectangle3d;

struct map_leaf { struct tag_block faces; struct tag_block portal_designators; };
struct map_leaf_face { short node_index; struct tag_block vertices; };
struct leaf_portal { long plane_index; long leaf_indices[2]; struct tag_block vertices; };
struct bsp3d_node { long plane_designator; };
struct bsp_stub { struct tag_block nodes; struct tag_block planes; };
struct leaf_map { struct bsp_stub *bsp; struct tag_block leaves; struct tag_block portals; };

#undef LONG_MAX
#define LONG_MAX LONG_MAX_MASK
#undef LONG_MIN
#define LONG_MIN LONG_MIN_BIT

static real_rectangle3d const private_null_rectangle = { REAL_MAX, REAL_MIN, REAL_MAX, REAL_MIN, REAL_MAX, REAL_MIN };
static real_rectangle3d const *global_null_rectangle3d = &private_null_rectangle;

/* helper stubs (CE implementations live elsewhere; unreachable without face vertices) */
/* projection is evaluated per face and its value is unused when a face has no vertices */
static short projection_from_vector3d(const real_vector3d *v) { (void)v; return 0; }
static boolean projection_sign_from_vector3d(const real_vector3d *v, short p) { (void)v; (void)p; return FALSE; }
static void project_point2d(const real_point2d *p, const real_plane3d *plane, short projection, boolean sign, real_point3d *out)
{ (void)p; (void)plane; (void)projection; (void)sign; (void)out; abort(); }
static real distance3d(const real_point3d *a, const real_point3d *b)
{ real dx = a->x - b->x, dy = a->y - b->y, dz = a->z - b->z; return (real)sqrt((double)dx * dx + (double)dy * dy + (double)dz * dz); }

/* CE_LEAF_MAP_FUNCTIONS */

int main(void) {
    char line[256];
    struct leaf_map map;
    struct bsp_stub bsp;
    struct bsp3d_node node0 = { 0 };
    real_plane3d plane0;
    long leaf_count = 0, portal_count = 0;
    struct map_leaf *leaves = NULL;
    struct leaf_portal *portals = NULL;
    long *designators[64];
    struct map_leaf_face *faces[64];

    memset(&plane0, 0, sizeof(plane0));
    memset(&bsp, 0, sizeof(bsp));
    map.bsp = &bsp;
    /* one node and one plane, so a face's node and plane lookups resolve (these faces have no vertices) */
    bsp.nodes.count = 1; bsp.nodes.address = &node0;
    bsp.planes.count = 1; bsp.planes.address = &plane0;
    while (fgets(line, sizeof(line), stdin)) {
        char tag[16];
        if (sscanf(line, "%15s", tag) != 1) continue;
        if (!strcmp(tag, "LEAVES")) {
            sscanf(line, "%*s %ld", &leaf_count);
            leaves = calloc((size_t)leaf_count, sizeof(*leaves));
            map.leaves.count = leaf_count; map.leaves.address = leaves;
        } else if (!strcmp(tag, "LEAF")) {
            /* LEAF <index> <designator count k> <k designators> <face count f> */
            long index, k, f, i;
            char *p = line;
            p = strchr(p, ' ') + 1; index = strtol(p, &p, 10);
            k = strtol(p, &p, 10);
            designators[index] = calloc((size_t)(k ? k : 1), sizeof(long));
            for (i = 0; i < k; i++) designators[index][i] = strtol(p, &p, 10);
            f = strtol(p, &p, 10);
            faces[index] = calloc((size_t)(f ? f : 1), sizeof(struct map_leaf_face));
            leaves[index].portal_designators.count = k;
            leaves[index].portal_designators.address = designators[index];
            leaves[index].faces.count = f;
            leaves[index].faces.address = faces[index];
        } else if (!strcmp(tag, "PORTALS")) {
            sscanf(line, "%*s %ld", &portal_count);
            portals = calloc((size_t)portal_count, sizeof(*portals));
            map.portals.count = portal_count; map.portals.address = portals;
        } else if (!strcmp(tag, "PORTAL")) {
            long index, l0, l1, vc;
            sscanf(line, "%*s %ld %ld %ld %ld", &index, &l0, &l1, &vc);
            portals[index].leaf_indices[0] = l0;
            portals[index].leaf_indices[1] = l1;
            portals[index].vertices.count = vc;
            portals[index].vertices.address = NULL;
            if (vc) abort();
        } else if (!strcmp(tag, "CLOSE")) {
            long p; sscanf(line, "%*s %ld", &p);
            printf("CLOSE %ld\n", p);
            leaf_map_close_portal(&map, p);
        } else if (!strcmp(tag, "CLOSED")) {
            long l; sscanf(line, "%*s %ld", &l);
            printf("CLOSED %ld %d\n", l, (int)leaf_map_leaf_is_closed(&map, l));
        } else if (!strcmp(tag, "BOUNDS")) {
            long l; real_point3d c; real r;
            sscanf(line, "%*s %ld", &l);
            leaf_map_get_leaf_bounds(&map, l, &c, &r);
            printf("BOUNDS %ld center %a %a %a radius %a\n", l, (double)c.x, (double)c.y, (double)c.z, (double)r);
        }
    }
    return 0;
}
