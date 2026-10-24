/* Host fixture with verbatim CE detail-object selection functions injected by
 * test_hcu_mp_detail_object_consumer.py. This checks CPU view selection only;
 * it does not implement a PS2 detail-object renderer. */
#include <assert.h>
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

typedef uint8_t byte;
typedef uint16_t word;
typedef int boolean;
typedef float real;
typedef struct { real i, j, k, l; } real_vector4d;
typedef struct { real x, y, z; } real_point3d;
struct tag_block { void *address; int32_t count; };
struct detail_object_cell_coordinate { short x, y, z; boolean initialized; byte pad07; };
struct detail_object_cell_definition {
	short cell_x, cell_y, cell_z, offset_z;
	uint32_t valid_layers;
	int32_t start_index, count_index, unused14[3];
};
struct detail_object_cell_data {
	int32_t first_detail_object_index, detail_object_count;
	short cell_x, cell_y;
	real cell_z;
	int32_t first_vertex_index;
	real_vector4d *z_reference_vector;
};
struct detail_object_layer_data {
	struct detail_object_cell_data *cells;
	short cell_count, collection_definition_index;
};
struct detail_object_view_data {
	struct detail_object_layer_data *layers;
	short layer_count;
	word pad06;
};
struct detail_object_runtime_data {
	struct detail_object_cell_data cells[32][27];
	struct detail_object_layer_data layers[32];
	struct detail_object_view_data view_data;
	struct detail_object_cell_coordinate cell_coordinate;
};
struct detail_object_global_runtime_data {
	struct detail_object_runtime_data local_player_data[2];
	real_vector4d default_z_reference_vector;
};
struct structure_detail_object_data {
	struct tag_block cells, detail_objects, counts, z_reference_vectors;
	byte valid, pad31[3];
	int32_t unused34[3];
};
struct structure_bsp { struct tag_block detail_object_data; };
struct scenario { struct tag_block detail_object_collection_palette; };
struct { short local_player_index; struct { real_point3d position; } camera; } render;

#define TRUE 1
#define FALSE 0
#define NONE (-1)
#define _error_silent 0
#define NUMBEROF(a) ((int32_t)(sizeof(a) / sizeof((a)[0])))
#define TEST_FLAG(value, bit) (((value) & (1u << (bit))) != 0)
#define TAG_BLOCK_GET_ELEMENT(block, index, type) \
	((type *)((byte *)(block)->address + (index) * (int32_t)sizeof(type)))
#define structure_detail_object_data_get(block, index) \
	TAG_BLOCK_GET_ELEMENT((block), (index), struct structure_detail_object_data)
#define detail_object_cell_definition_get(block, index) \
	TAG_BLOCK_GET_ELEMENT((block), (index), struct detail_object_cell_definition)
#define detail_object_count_get(block, index) \
	TAG_BLOCK_GET_ELEMENT((block), (index), word)
#define detail_object_z_reference_vector_get(block, index) \
	TAG_BLOCK_GET_ELEMENT((block), (index), real_vector4d)
#define match_assert(file, line, expression) assert(expression)

static struct detail_object_global_runtime_data runtime_storage;
static struct detail_object_global_runtime_data *detail_object_global_runtime_data;
static struct structure_bsp bsp_storage;
static struct structure_bsp *global_structure_bsp;
static struct scenario scenario_storage;
static int current_local_player_count = 1;
static int begin_calls, rebuild_calls, draw_calls, end_calls;
static int expected_mode;
static boolean warned_about_detail_object_counts;

static real fast_ftol(real value) { return (real)lrintf(value); }
static short local_player_count(void) { return (short)current_local_player_count; }
static struct structure_bsp *global_structure_bsp_get(void) { return global_structure_bsp; }
static struct scenario *global_scenario_get(void) { return &scenario_storage; }
static void error(short priority, const char *format, ...) { (void)priority; (void)format; }
static void rasterizer_detail_objects_begin(void) { ++begin_calls; }
static void rasterizer_detail_objects_end(void) { ++end_calls; }

static void rasterizer_detail_objects_rebuild_vertices(struct detail_object_view_data *view)
{
	++rebuild_calls;
	if (expected_mode == 1)
	{
		assert(view->layer_count == 2);
		assert(view->layers != NULL);
		assert(view->layers[0].collection_definition_index == 0);
		assert(view->layers[0].cell_count == 3);
		assert(view->layers[0].cells[0].cell_z == -1.0f);
		assert(view->layers[0].cells[0].first_detail_object_index == 3);
		assert(view->layers[0].cells[1].first_detail_object_index == 4);
		assert(view->layers[0].cells[2].cell_x == -1);
		assert(view->layers[0].cells[2].first_detail_object_index == 1);
		assert(view->layers[1].collection_definition_index == 1);
		assert(view->layers[1].cell_count == 2);
		assert(view->layers[1].cells[0].first_detail_object_index == 8);
		assert(view->layers[1].cells[1].first_detail_object_index == 5);
	}
	else
	{
		assert(view->layer_count == 0);
	}
}

static void rasterizer_detail_objects_draw(struct detail_object_view_data const *view)
{
	++draw_calls;
	assert(view->layer_count == (expected_mode == 1 ? 2 : 0));
}

/* CE_DETAIL_OBJECT_FUNCTIONS */

static void test_synthetic_selection(void)
{
	struct detail_object_cell_definition cells[8] = {
		{ -2, 0, 0, 0, 1u << 0, 0, 0, { 0, 0, 0 } },
		{ -1, 0, 0, 0, (1u << 0) | (1u << 2), 1, 1, { 0, 0, 0 } },
		{ 0, 0, -1, 0, 1u << 0, 3, 3, { 0, 0, 0 } },
		{ 0, 0, 0, 0, (1u << 0) | (1u << 1), 4, 4, { 0, 0, 0 } },
		{ 0, 1, 1, 0, 1u << 2, 6, 6, { 0, 0, 0 } },
		{ 0, 2, 0, 0, 1u << 0, 7, 7, { 0, 0, 0 } },
		{ 1, 0, 0, 0, 1u << 1, 8, 8, { 0, 0, 0 } },
		{ 2, 0, 0, 0, 1u << 2, 9, 9, { 0, 0, 0 } },
	};
	word counts[10] = { 1, 1, 1, 1, 1, 1, 1, 1, 1, 1 };
	struct detail_object_cell_definition *cell_ptr = cells;
	struct structure_detail_object_data detail;
	memset(&runtime_storage, 0, sizeof(runtime_storage));
	memset(&detail, 0, sizeof(detail));
	runtime_storage.default_z_reference_vector.k = 1.0f;
	detail_object_global_runtime_data = &runtime_storage;
	detail.cells.address = cell_ptr;
	detail.cells.count = NUMBEROF(cells);
	detail.counts.address = counts;
	detail.counts.count = NUMBEROF(counts);
	detail.detail_objects.count = 10;
	detail.valid = TRUE;
	bsp_storage.detail_object_data.address = &detail;
	bsp_storage.detail_object_data.count = 1;
	global_structure_bsp = &bsp_storage;
	scenario_storage.detail_object_collection_palette.count = 2;
	render.local_player_index = 0;
	render.camera.position.x = 4.0f;
	render.camera.position.y = 4.0f;
	render.camera.position.z = 4.0f;
	current_local_player_count = 1;
	expected_mode = 1;
	begin_calls = rebuild_calls = draw_calls = end_calls = 0;
	structure_render_detail_objects();
	assert(begin_calls == 1 && rebuild_calls == 1 && draw_calls == 1 && end_calls == 1);
	/* Same camera cell: CE reuses the cached layer/cell selection. */
	structure_render_detail_objects();
	assert(begin_calls == 2 && rebuild_calls == 1 && draw_calls == 2 && end_calls == 2);
	/* The CE path is explicitly disabled unless there is exactly one local player. */
	current_local_player_count = 2;
	structure_render_detail_objects();
	assert(begin_calls == 2 && rebuild_calls == 1 && draw_calls == 2 && end_calls == 2);
	printf("synthetic camera-cell selection passed layers=2 cells=5 cached=1 split_screen_gate=1\n");
}

static void test_empty_valid_data(void)
{
	struct structure_detail_object_data detail;
	memset(&runtime_storage, 0, sizeof(runtime_storage));
	memset(&detail, 0, sizeof(detail));
	detail_object_global_runtime_data = &runtime_storage;
	detail.valid = TRUE;
	bsp_storage.detail_object_data.address = &detail;
	bsp_storage.detail_object_data.count = 1;
	global_structure_bsp = &bsp_storage;
	scenario_storage.detail_object_collection_palette.count = 0;
	render.local_player_index = 0;
	render.camera.position.x = render.camera.position.y = render.camera.position.z = 4.0f;
	current_local_player_count = 1;
	expected_mode = 0;
	begin_calls = rebuild_calls = draw_calls = end_calls = 0;
	structure_render_detail_objects();
	assert(begin_calls == 1 && rebuild_calls == 1 && draw_calls == 1 && end_calls == 1);
	assert(runtime_storage.local_player_data[0].view_data.layer_count == 0);
	printf("empty valid detail data passed empty_view=1\n");
}

static void test_retail_empty_data(int32_t map_id, byte valid)
{
	struct structure_detail_object_data detail;
	memset(&runtime_storage, 0, sizeof(runtime_storage));
	memset(&detail, 0, sizeof(detail));
	detail_object_global_runtime_data = &runtime_storage;
	detail.valid = valid;
	bsp_storage.detail_object_data.address = &detail;
	bsp_storage.detail_object_data.count = 1;
	global_structure_bsp = &bsp_storage;
	scenario_storage.detail_object_collection_palette.count = 0;
	render.local_player_index = 0;
	render.camera.position.x = render.camera.position.y = render.camera.position.z = 4.0f;
	current_local_player_count = 1;
	expected_mode = 0;
	begin_calls = rebuild_calls = draw_calls = end_calls = 0;
	structure_render_detail_objects();
	assert(begin_calls == 0 && rebuild_calls == 0 && draw_calls == 0 && end_calls == 0);
	assert(runtime_storage.local_player_data[0].view_data.layer_count == 0);
	printf("retail map=%d detail_valid=%u cells=0 counts=0 objects=0 zrefs=0 draw_calls=0\n",
		map_id, (unsigned)valid);
}

int main(int argc, char **argv)
{
	assert(sizeof(struct detail_object_cell_definition) == 0x20);
	/* Pointer-bearing runtime records are intentionally host-width here; this
	 * is semantic fixture execution, not an HCU target ABI qualification. */
	if (argc == 2 && strcmp(argv[1], "synthetic") == 0)
	{
		test_synthetic_selection();
		test_empty_valid_data();
		return 0;
	}
	if (argc == 4 && strcmp(argv[1], "retail") == 0)
	{
		test_retail_empty_data((int32_t)strtol(argv[2], NULL, 10),
			(byte)strtoul(argv[3], NULL, 10));
		return 0;
	}
	return 2;
}
