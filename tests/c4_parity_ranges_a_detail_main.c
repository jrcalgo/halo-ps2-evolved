/* C4 ranges-a member-exact driver for the detail object cell selector.

Owner structs: structure_detail_object_data.cells (struct detail_object_cell_definition,
ledger member detail_object_cell.<unclassified@0x0>) and structure_detail_object_data.counts
(word, ledger member detail_object_count.<unclassified@0x0>).

The functions key_compare_cells_lower_bound, key_compare_cells_upper_bound,
get_lower_bound_cell, get_upper_bound_cell and structure_detail_objects_port_count are
extracted verbatim from submodules/halo-ce-universal/source/structures/structure_detail_objects.c
by tests/test_c4_parity_ranges_a.py (placeholder marker CE_FUNCTIONS). Types, the
tag block accessor and error reporting are the minimal ILP32 stand-ins below.

stdin:
  n_counts c0 ... (word counts)
  n_objects
  n_cells then one line per cell: cell_x cell_y cell_z
  queries: 'q x y z' -> prints 'q lb=<i> ub=<j>'; 'p count_index first' -> prints 'p <value>'
  'end' terminates.
*/
#include <stddef.h>
#include <stdio.h>
#include <stdlib.h>

typedef unsigned char byte;
typedef int boolean;
typedef float real;
typedef unsigned short word;
typedef struct { void *address; long count; } tag_block;

#define TRUE 1
#define FALSE 0
#define _error_silent 0
#define error(level, ...) ((void)0)
#define TAG_BLOCK_GET_ELEMENT(b,i,t) ((t*)((byte*)(b)->address+(i)*sizeof(t)))

struct detail_object_cell_coordinate
{
	short x;
	short y;
	short z;
	boolean initialized;
	byte pad07;
};

struct detail_object_cell_definition
{
	short cell_x;
	short cell_y;
	short cell_z;
	short offset_z;
	unsigned int valid_layers;
	int start_index;
	int count_index;
	int unused14[3];
};
typedef char cell_definition_size_assert[sizeof(struct detail_object_cell_definition) == 0x20 ? 1 : -1];

struct structure_detail_object_data
{
	tag_block counts;
	tag_block detail_objects;
};

#define detail_object_count_get(block, index) \
	TAG_BLOCK_GET_ELEMENT((block), (index), word)

static int warned_about_detail_object_counts;

/*CE_FUNCTIONS*/

static word counts_store[256];
static struct detail_object_cell_definition cells_store[256];
static struct structure_detail_object_data data;

static int read_int(void) { int v; if (scanf("%d", &v) != 1) exit(3); return v; }

int main(void)
{
	long i, n;
	char tag[8];
	struct detail_object_cell_definition *begin, *end;

	data.counts.address = counts_store;
	data.detail_objects.address = NULL;
	n = read_int();
	data.counts.count = n;
	for (i = 0; i < n; i++) counts_store[i] = (word)read_int();
	data.detail_objects.count = read_int();

	n = read_int();
	for (i = 0; i < n; i++) {
		cells_store[i].cell_x = (short)read_int();
		cells_store[i].cell_y = (short)read_int();
		cells_store[i].cell_z = (short)read_int();
	}
	begin = cells_store;
	end = cells_store + n;

	while (scanf("%7s", tag) == 1) {
		if (tag[0] == 'e') break;
		if (tag[0] == 'q') {
			struct detail_object_cell_coordinate key;
			struct detail_object_cell_definition *lb, *ub;
			key.x = (short)read_int();
			key.y = (short)read_int();
			key.z = (short)read_int();
			key.initialized = TRUE;
			key.pad07 = 0;
			lb = get_lower_bound_cell(begin, end, &key);
			ub = get_upper_bound_cell(begin, end, &key);
			printf("q lb=%ld ub=%ld\n", (long)(lb - begin), (long)(ub - begin));
		} else if (tag[0] == 'p') {
			long count_index = read_int();
			long first = read_int();
			printf("p %ld\n", structure_detail_objects_port_count(&data, count_index, first));
		}
	}
	return 0;
}
