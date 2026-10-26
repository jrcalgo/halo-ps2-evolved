/* C4 ranges-a member-exact driver for structure_runtime_decal.<unclassified@0x0>.

Compiles structure_decals_update, extracted verbatim from
submodules/halo-ce-universal/source/structures/structure_runtime_decals.c by
tests/test_c4_parity_ranges_a.py (placeholder marker CE_FUNCTIONS). The range consumed is
position (0x0), palette_index (0xc), yaw (0xe) and pitch (0xf); unused (0xd) has no access.

The decal manager is a data-only stand-in: decals_delete_permanent_from_cluster and
decal_new record their calls and do nothing else; decal_definition_get is a no-op. The
euler-to-vector conversion is recorded as the angles it is given (the test checks the
angles the range produces against the CE formula), not converted.

stdin:
  n_runtime, per decal: px py pz palette_index unused yaw pitch
  n_palette, per entry: definition index (-1 = none)
  n_clusters, per cluster: first_decal_index decal_count
  old_pvs_bits (n_clusters values 0/1), new_pvs_bits (n_clusters values 0/1)
  reconnect (0/1)
stdout: lines 'del <cluster>', 'new <definition> <px> <py> <pz> <yaw_angle> <pitch_angle>',
        'bad <index>' for each malformed report, one per decal call.
*/
#include <math.h>
#include <stddef.h>
#include <stdio.h>
#include <stdlib.h>

typedef unsigned char byte;
typedef int boolean;
typedef unsigned short word;
typedef float real;
typedef struct { real x, y, z; } real_point3d;
typedef struct { real i, j, k; } real_vector3d;
typedef struct { real yaw, pitch; } real_euler_angles2d; /* CE union: struct { yaw; pitch; } */
struct tag_block { void *address; long count; };
typedef struct tag_block tag_block;
typedef struct { unsigned int group_tag; unsigned int name; int name_length; int index; } tag_reference;

#define TRUE 1
#define FALSE 0
#define NONE (-1)
#define _pi 3.14159265358979f
#define LONG_BITS 32
#define LONG_BITS_BITS 5
#define TEST_FLAG(v, b) ((((unsigned long)(v)) >> (b)) & 1)
#define BIT_VECTOR_TEST_FLAG(bit_vector, bit) (TEST_FLAG((bit_vector)[(bit) >> LONG_BITS_BITS], ((bit) & (LONG_BITS - 1))))
#define TAG_BLOCK_GET_ELEMENT(b,i,t) ((t*)((byte*)(b)->address+(i)*sizeof(t)))
#define match_assert(file, line, condition) \
	do { if (!(condition)) { printf("assert %d\n", (line)); exit(4); } } while (0)
#define error(level, ...) ((void)0)
#define _error_silent 0

struct structure_cluster_runtime_decals
{
	byte unused[0xC];
	short first_decal_index;
	word decal_count;
	byte unused2[0x58];
};
typedef char cluster_decals_size_assert[sizeof(struct structure_cluster_runtime_decals) == 0x68 ? 1 : -1];

struct structure_runtime_decal
{
	real_point3d position;
	byte palette_index;
	byte unused;
	char yaw;
	char pitch;
};
typedef char runtime_decal_size_assert[sizeof(struct structure_runtime_decal) == 0x10 ? 1 : -1];
typedef char runtime_decal_yaw_offset_assert[offsetof(struct structure_runtime_decal, yaw) == 0xe ? 1 : -1];
typedef char runtime_decal_pitch_offset_assert[offsetof(struct structure_runtime_decal, pitch) == 0xf ? 1 : -1];

struct scenario_decal_palette_entry { tag_reference reference; };
struct scenario { tag_block decal_palette; };

struct structure_bsp
{
	tag_block runtime_decals;
	tag_block clusters;
};

struct structure_decals_globals
{
	boolean reconnect_to_structure_bsp;
	byte pad[3];
};

static struct structure_bsp bsp_store;
static struct structure_bsp *global_structure_bsp_get(void) { return &bsp_store; }
static struct scenario scenario_store;
static struct scenario *global_scenario_get(void) { return &scenario_store; }
static struct structure_decals_globals globals_store;
static struct structure_decals_globals *structure_decals_globals = &globals_store;
static struct structure_runtime_decal runtime_store[256];
static struct structure_cluster_runtime_decals cluster_store[64];
static struct scenario_decal_palette_entry palette_store[64];
static unsigned long old_pvs[2], new_pvs[2];

static void structure_decals_report_malformed(long decal_index)
{
	printf("bad %ld\n", decal_index);
}

static void decals_delete_permanent_from_cluster(short cluster_index)
{
	printf("del %d\n", (int)cluster_index);
}

static void decal_definition_get(long definition_index)
{
	(void)definition_index;
}

static void vector3d_from_euler_angles2d(real_vector3d *v, real_euler_angles2d const *angles)
{
	/* stand-in: records the angles through the vector (i = yaw, j = pitch, k = 0) */
	v->i = angles->yaw;
	v->j = angles->pitch;
	v->k = 0;
}

static void decal_new(long definition_index, real_point3d const *position, real_vector3d const *normal,
	real scale, long a, long b, boolean c)
{
	(void)scale; (void)a; (void)b; (void)c;
	printf("new %ld %.9g %.9g %.9g %.9g %.9g\n", definition_index,
		position->x, position->y, position->z, normal->i, normal->j);
}

/*CE_FUNCTIONS*/

int main(void)
{
	long n, i;
	short nc;
	int bit;
	int reconnect;

	n = 0;
	if (scanf("%ld", &n) != 1) return 3;
	bsp_store.runtime_decals.address = runtime_store;
	bsp_store.runtime_decals.count = n;
	for (i = 0; i < n; i++) {
		struct structure_runtime_decal *d = &runtime_store[i];
		int pi, unused, yaw, pitch;
		if (scanf("%f %f %f %d %d %d %d", &d->position.x, &d->position.y, &d->position.z,
			&pi, &unused, &yaw, &pitch) != 7) return 3;
		d->palette_index = (byte)pi;
		d->unused = (byte)unused;
		d->yaw = (char)yaw;
		d->pitch = (char)pitch;
	}
	if (scanf("%ld", &n) != 1) return 3;
	scenario_store.decal_palette.address = palette_store;
	scenario_store.decal_palette.count = n;
	for (i = 0; i < n; i++) {
		int index;
		if (scanf("%d", &index) != 1) return 3;
		palette_store[i].reference.index = index;
	}
	if (scanf("%hd", &nc) != 1) return 3;
	bsp_store.clusters.address = cluster_store;
	bsp_store.clusters.count = nc;
	for (i = 0; i < nc; i++) {
		int first, count;
		if (scanf("%d %d", &first, &count) != 2) return 3;
		cluster_store[i].first_decal_index = (short)first;
		cluster_store[i].decal_count = (word)count;
	}
	for (i = 0; i < 2; i++) old_pvs[i] = 0;
	for (i = 0; i < 2; i++) new_pvs[i] = 0;
	for (i = 0; i < nc; i++) {
		if (scanf("%d", &bit) != 1) return 3;
		if (bit) old_pvs[i >> LONG_BITS_BITS] |= 1UL << (i & (LONG_BITS - 1));
	}
	for (i = 0; i < nc; i++) {
		if (scanf("%d", &bit) != 1) return 3;
		if (bit) new_pvs[i >> LONG_BITS_BITS] |= 1UL << (i & (LONG_BITS - 1));
	}
	if (scanf("%d", &reconnect) != 1) return 3;
	structure_decals_globals->reconnect_to_structure_bsp = (boolean)reconnect;

	structure_decals_update(old_pvs, new_pvs, nc);
	return 0;
}
