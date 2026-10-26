/* C4 ranges-a member-exact driver for structure_material.<unclassified@0x10>, the span
members first_surface_index (0x14) and surface_count (0x18) that the surface-to-material
search reads. The search structure_bsp_find_material_for_surface is extracted verbatim
from submodules/halo-ce-universal/source/structures/structure_bsp_definitions.c by
tests/test_c4_parity_ranges_a.py (placeholder marker CE_FUNCTIONS). The material layout
below reproduces CE's offsets (asserted), and match_assert is a stand-in that exits
non-zero so a failed Xbox assertion is reported, not hidden.

stdin: n_lightmaps; per lightmap: n_materials then n_materials lines 'first count'.
queries: 's <surface>' lines, terminated by 'e'.
stdout: 's 0' (FALSE) or 's 1 <lightmap> <material>' (TRUE).
*/
#include <stddef.h>
#include <stdio.h>
#include <stdlib.h>

typedef unsigned char byte;
typedef int boolean;
typedef unsigned short word;
typedef struct { void *address; long count; } tag_block;

#define TRUE 1
#define FALSE 0
#define TAG_BLOCK_GET_ELEMENT(b,i,t) ((t*)((byte*)(b)->address+(i)*sizeof(t)))
#define match_assert(file, line, condition) \
	do { if (!(condition)) { printf("assert %d\n", (line)); exit(4); } } while (0)

struct structure_material
{
	byte shader[16];
	short permutation_index;
	word flags;
	int first_surface_index;
	int surface_count;
	byte tail[0x9c - 0x20];
};
typedef char material_first_offset_assert[offsetof(struct structure_material, first_surface_index) == 0x14 ? 1 : -1];
typedef char material_count_offset_assert[offsetof(struct structure_material, surface_count) == 0x18 ? 1 : -1];

struct structure_lightmap
{
	short bitmap_index;
	word pad;
	long unused[4];
	tag_block materials;
};

struct structure_bsp
{
	tag_block lightmaps;
};

/*CE_FUNCTIONS*/

static struct structure_bsp bsp;
static struct structure_lightmap lightmap_store[64];
static struct structure_material material_store[64][64];

static int read_int(void) { int v; if (scanf("%d", &v) != 1) exit(3); return v; }

int main(void)
{
	long li, mi, n, nm;
	char tag[8];

	n = read_int();
	bsp.lightmaps.address = lightmap_store;
	bsp.lightmaps.count = n;
	for (li = 0; li < n; li++) {
		nm = read_int();
		lightmap_store[li].materials.address = material_store[li];
		lightmap_store[li].materials.count = nm;
		for (mi = 0; mi < nm; mi++) {
			material_store[li][mi].first_surface_index = read_int();
			material_store[li][mi].surface_count = read_int();
		}
	}
	while (scanf("%7s", tag) == 1) {
		long surface;
		short lightmap_index, material_index;
		boolean found;
		if (tag[0] == 'e') break;
		surface = read_int();
		found = structure_bsp_find_material_for_surface(&bsp, surface, &lightmap_index, &material_index);
		if (found)
			printf("s 1 %d %d\n", (int)lightmap_index, (int)material_index);
		else
			printf("s 0\n");
	}
	return 0;
}
