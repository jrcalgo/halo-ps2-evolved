/* CE collision_bsp_test_pill / collision_bsp_test_sphere.
 *
 * The square floor is the synthetic technique from
 * tests/m3_ce_collision_synthetic_main.c (surface 0, pill t = 0.375).
 * Blood Gulch is a host view of the raw Xbox collision arrays: indices and
 * plane/vertex bytes are copied unchanged and only the tag-block pointers
 * are host addresses. Expectations come from hcu_swept_oracle.h, which the
 * Python oracle writes from those raw bytes before this binary is linked.
 */
#include "cseries/cseries.h"
#include "physics/collision_bsp.h"
#include "physics/collision_bsp_definitions.h"
#include "hcu_swept_oracle.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>

/* cseries.h renames the libc memory calls. Undo that in this file so the
 * replacements below can call libc without recursing, and so the blob loader
 * uses the real allocator. Other translation units still call csmem*. */
#undef memcmp
#undef memcpy
#undef memset
#undef malloc
#undef free

struct collision_bsp *global_collision_bsp = NULL;
short global_current_collision_user_depth = 1;
short global_current_collision_users[32];

static int swept_error_count = 0;

/* Private CE layouts (collision_bsp.c). Sizes are asserted there as 8. */
struct hcu_swept_leaf {
	word flags;
	short bsp2d_reference_count;
	long first_bsp2d_reference_index;
};

struct hcu_swept_bsp2d_reference {
	long plane_designator;
	long root_index;
};

void error(short priority, const char *format, ...)
{
	(void)priority;
	(void)format;
	swept_error_count++;
	fprintf(stderr, "swept-error priority=%d\n", (int)priority);
}

void display_assert(char *information, char *file, long line, boolean fatal)
{
	fprintf(stderr, "swept-assert %s %s:%ld fatal=%d\n",
		information ? information : "", file ? file : "", line, (int)fatal);
	if (fatal)
		exit(1);
}

void system_exit(long code)
{
	exit((int)code);
}

void halt_and_catch_fire(void)
{
	exit(1);
}

void *csmemset(void *buffer, long value, unsigned long size)
{
	return memset(buffer, (int)value, size);
}

void *csmemcpy(void *destination, const void *source, unsigned long size)
{
	return memcpy(destination, source, size);
}

long csmemcmp(const void *left, const void *right, unsigned long size)
{
	return memcmp(left, right, size);
}

void *debug_malloc(unsigned int size, boolean clear, const char *file, long line)
{
	void *pointer;

	(void)file;
	(void)line;
	pointer = malloc(size);
	if (pointer && clear)
		memset(pointer, 0, size);
	return pointer;
}

void debug_free(void *pointer, const char *file, long line)
{
	(void)file;
	(void)line;
	free(pointer);
}

void *tag_block_get_element_with_size(struct tag_block const *block,
	long index, long element_size)
{
	if (!block || !block->address || index < 0 || index >= block->count)
		return NULL;
	if (block->definition && block->definition->element_size != element_size)
		return NULL;
	return (char *)block->address + index * element_size;
}

void collision_log_usage(short collision_function)
{
	(void)collision_function;
}

void collision_log_start_time(LARGE_INTEGER *start_time)
{
	if (start_time)
		start_time->QuadPart = 0;
}

void collision_log_end_time(short collision_function, long start_time)
{
	(void)collision_function;
	(void)start_time;
}

static float bits_to_float(unsigned bits)
{
	float value;

	memcpy(&value, &bits, sizeof value);
	return value;
}

static int fail(const char *what)
{
	fprintf(stderr, "swept-fail %s\n", what);
	return 0;
}

static int leaf_listed(long const *leaves, long count, long leaf)
{
	long index;

	for (index = 0; index < count && index < 256; ++index) {
		if (leaves[index] == leaf)
			return 1;
	}
	return 0;
}

static void bind_block(struct tag_block *block, long count, void *address)
{
	block->count = count;
	block->address = address;
	block->definition = NULL;
}

static void init_square(struct collision_bsp *bsp,
	struct bsp3d_node *nodes, real_plane3d *planes,
	struct hcu_swept_leaf *leaves, struct hcu_swept_bsp2d_reference *refs,
	struct collision_surface *surfaces, struct collision_edge *edges,
	struct collision_vertex *vertices)
{
	static float const xy[4][2] = {
		{-2.f, -2.f}, {2.f, -2.f}, {2.f, 2.f}, {-2.f, 2.f}
	};
	int index;

	memset(bsp, 0, sizeof *bsp);
	memset(nodes, 0, sizeof *nodes);
	memset(planes, 0, sizeof *planes);
	memset(leaves, 0, sizeof *leaves);
	memset(refs, 0, sizeof *refs);
	memset(surfaces, 0, sizeof *surfaces);
	memset(edges, 0, 4 * sizeof *edges);
	memset(vertices, 0, 4 * sizeof *vertices);
	planes[0].n.i = 0.f;
	planes[0].n.j = 0.f;
	planes[0].n.k = 1.f;
	planes[0].d = 0.f;
	nodes[0].plane_designator = 0;
	nodes[0].children[0] = NONE;
	nodes[0].children[1] = (long)0x80000000u;
	leaves[0].flags = 0;
	leaves[0].bsp2d_reference_count = 1;
	leaves[0].first_bsp2d_reference_index = 0;
	refs[0].plane_designator = 0;
	refs[0].root_index = (long)0x80000000u;
	surfaces[0].plane_designator = 0;
	surfaces[0].first_edge_index = 0;
	surfaces[0].flags = 0;
	surfaces[0].material_index = 0;
	for (index = 0; index < 4; ++index) {
		vertices[index].point.x = xy[index][0];
		vertices[index].point.y = xy[index][1];
		vertices[index].point.z = 0.f;
		vertices[index].first_edge_index = index;
		edges[index].vertex_indices[0] = index;
		edges[index].vertex_indices[1] = (index + 1) % 4;
		edges[index].edge_indices[0] = (index + 1) % 4;
		edges[index].edge_indices[1] = (index + 3) % 4;
		edges[index].surface_indices[0] = 0;
		edges[index].surface_indices[1] = NONE;
	}
	bind_block(&bsp->bsp3d.nodes, 1, nodes);
	bind_block(&bsp->bsp3d.planes, 1, planes);
	bind_block(&bsp->leaves, 1, leaves);
	bind_block(&bsp->bsp2d_references, 1, refs);
	bind_block(&bsp->bsp2d.nodes, 0, NULL);
	bind_block(&bsp->surfaces, 1, surfaces);
	bind_block(&bsp->edges, 4, edges);
	bind_block(&bsp->vertices, 4, vertices);
}

static int synthetic_reference(void)
{
	struct collision_bsp bsp;
	struct bsp3d_node nodes[1];
	real_plane3d planes[1];
	struct hcu_swept_leaf leaves[1];
	struct hcu_swept_bsp2d_reference refs[1];
	struct collision_surface surfaces[1];
	struct collision_edge edges[4];
	struct collision_vertex vertices[4];
	real_point3d start;
	real_point3d outside;
	real_point3d above;
	real_point3d sphere_center;
	real_vector3d movement;
	struct collision_bsp_test_pill_result pill;
	struct collision_bsp_test_sphere_result sphere;
	int hit;
	unsigned plane_bits[4];
	unsigned t_bits;

	init_square(&bsp, nodes, planes, leaves, refs, surfaces, edges, vertices);
	start.x = 0.f;
	start.y = 0.f;
	start.z = 1.f;
	movement.i = 0.f;
	movement.j = 0.f;
	movement.k = -2.f;
	memset(&pill, 0, sizeof pill);
	hit = collision_bsp_test_pill(&bsp, &start, &movement, 0.25f, 1.f, &pill);
	memcpy(&t_bits, &pill.t, sizeof t_bits);
	memcpy(plane_bits, &pill.plane, sizeof plane_bits);
	if (!hit || pill.surface_index != 0 || pill.material_index != 0 ||
		!leaf_listed(pill.leaf_indices, pill.leaf_count, 0) ||
		t_bits != 0x3ec00000u ||
		plane_bits[0] != 0 || plane_bits[1] != 0 ||
		plane_bits[2] != 0x3f800000u || plane_bits[3] != 0) {
		fprintf(stderr,
			"swept-fail synthetic_pill_hit hit=%d surface=%ld material=%d "
			"leaf_count=%ld t_bits=0x%08x plane=%08x %08x %08x %08x\n",
			hit, pill.surface_index, (int)pill.material_index, pill.leaf_count,
			t_bits, plane_bits[0], plane_bits[1], plane_bits[2], plane_bits[3]);
		return 0;
	}
	printf("swept-subtest synthetic_pill_hit surface=0 material=0 leaf=0 "
		"t=0.375000 status=passed\n");

	outside.x = 3.f;
	outside.y = 0.f;
	outside.z = 1.f;
	memset(&pill, 0, sizeof pill);
	hit = collision_bsp_test_pill(&bsp, &outside, &movement, 0.25f, 1.f, &pill);
	if (hit) {
		fprintf(stderr, "swept-fail synthetic_pill_miss surface=%ld t_bits=",
			pill.surface_index);
		memcpy(&t_bits, &pill.t, sizeof t_bits);
		fprintf(stderr, "0x%08x\n", t_bits);
		return 0;
	}
	printf("swept-subtest synthetic_pill_miss hit=0 status=passed\n");

	sphere_center.x = 0.f;
	sphere_center.y = 0.f;
	sphere_center.z = 0.10f;
	memset(&sphere, 0, sizeof sphere);
	hit = collision_bsp_test_sphere(&bsp, 0, NULL, &sphere_center, 0.25f, &sphere);
	if (!hit || sphere.surface_count != 1 || sphere.surface_indices[0] != 0 ||
		sphere.edge_count != 0 || sphere.vertex_count != 0 ||
		!leaf_listed(sphere.leaf_indices, sphere.leaf_count, 0) ||
		surfaces[0].material_index != 0 || surfaces[0].plane_designator != 0) {
		fprintf(stderr,
			"swept-fail synthetic_sphere_hit hit=%d surfaces=%ld edges=%ld "
			"vertices=%ld leaf_count=%ld\n",
			hit, sphere.surface_count, sphere.edge_count, sphere.vertex_count,
			sphere.leaf_count);
		return 0;
	}
	printf("swept-subtest synthetic_sphere_hit surface=0 material=0 leaf=0 "
		"surfaces=1 edges=0 vertices=0 status=passed\n");

	above.x = 0.f;
	above.y = 0.f;
	above.z = 2.f;
	memset(&sphere, 0, sizeof sphere);
	hit = collision_bsp_test_sphere(&bsp, 0, NULL, &above, 0.25f, &sphere);
	if (hit || sphere.surface_count != 0 || sphere.edge_count != 0 ||
		sphere.vertex_count != 0) {
		fprintf(stderr,
			"swept-fail synthetic_sphere_miss hit=%d surfaces=%ld edges=%ld "
			"vertices=%ld\n",
			hit, sphere.surface_count, sphere.edge_count, sphere.vertex_count);
		return 0;
	}
	printf("swept-subtest synthetic_sphere_miss hit=0 surfaces=0 edges=0 "
		"vertices=0 status=passed\n");
	return swept_error_count == 0 || fail("synthetic reported a CE error");
}

struct swept_view {
	struct collision_bsp bsp;
	unsigned char *payload;
	unsigned char *snapshot;
	unsigned long payload_bytes;
	struct collision_surface *surfaces;
	real_plane3d *planes;
};

static int load_view(struct swept_view *view, char const *path)
{
	static unsigned long const strides[8] = {12, 16, 8, 8, 20, 12, 24, 16};
	FILE *file;
	char magic[4];
	uint32_t counts[8];
	unsigned long bytes;
	int index;
	unsigned char *cursor;

	memset(view, 0, sizeof *view);
	file = fopen(path, "rb");
	if (!file)
		return fail("open collision blob");
	if (fread(magic, 1, 4, file) != 4 || memcmp(magic, "SWP1", 4) != 0) {
		fclose(file);
		return fail("blob magic");
	}
	if (fread(counts, 4, 8, file) != 8) {
		fclose(file);
		return fail("blob counts");
	}
	bytes = 0;
	for (index = 0; index < 8; ++index) {
		if (counts[index] != hcu_swept_counts[index]) {
			fclose(file);
			fprintf(stderr, "swept-fail count %d blob=%u header=%u\n",
				index, counts[index], hcu_swept_counts[index]);
			return 0;
		}
		bytes += (unsigned long)counts[index] * strides[index];
	}
	view->payload = (unsigned char *)malloc(bytes);
	view->snapshot = (unsigned char *)malloc(bytes);
	if (!view->payload || !view->snapshot) {
		fclose(file);
		return fail("blob allocation");
	}
	if (fread(view->payload, 1, bytes, file) != bytes) {
		fclose(file);
		return fail("truncated blob");
	}
	fclose(file);
	memcpy(view->snapshot, view->payload, bytes);
	view->payload_bytes = bytes;
	cursor = view->payload;
	bind_block(&view->bsp.bsp3d.nodes, (long)counts[0], cursor);
	cursor += counts[0] * strides[0];
	bind_block(&view->bsp.bsp3d.planes, (long)counts[1], cursor);
	view->planes = (real_plane3d *)cursor;
	cursor += counts[1] * strides[1];
	bind_block(&view->bsp.leaves, (long)counts[2], cursor);
	cursor += counts[2] * strides[2];
	bind_block(&view->bsp.bsp2d_references, (long)counts[3], cursor);
	cursor += counts[3] * strides[3];
	bind_block(&view->bsp.bsp2d.nodes, (long)counts[4], cursor);
	cursor += counts[4] * strides[4];
	bind_block(&view->bsp.surfaces, (long)counts[5], cursor);
	view->surfaces = (struct collision_surface *)cursor;
	cursor += counts[5] * strides[5];
	bind_block(&view->bsp.edges, (long)counts[6], cursor);
	cursor += counts[6] * strides[6];
	bind_block(&view->bsp.vertices, (long)counts[7], cursor);
	cursor += counts[7] * strides[7];
	if ((unsigned long)(cursor - view->payload) != bytes)
		return fail("blob cursor");
	if (HCU_SWEPT_SURFACE < 0 || HCU_SWEPT_SURFACE >= view->bsp.surfaces.count)
		return fail("oracle surface out of range");
	if (view->surfaces[HCU_SWEPT_SURFACE].material_index != HCU_SWEPT_MATERIAL ||
		view->surfaces[HCU_SWEPT_SURFACE].plane_designator !=
			HCU_SWEPT_PLANE_DESIGNATOR)
		return fail("oracle surface bytes differ from header");
	return 1;
}

static int retail_queries(struct swept_view *view)
{
	real_point3d hit_point;
	real_point3d miss_point;
	real_vector3d hit_vector;
	real_vector3d miss_vector;
	real radius;
	struct collision_bsp_test_sphere_result sphere;
	struct collision_bsp_test_pill_result pill;
	struct collision_surface const *surface;
	unsigned plane_bits[4];
	unsigned t_bits;
	int hit;

	hit_point.x = bits_to_float(hcu_swept_hit_point[0]);
	hit_point.y = bits_to_float(hcu_swept_hit_point[1]);
	hit_point.z = bits_to_float(hcu_swept_hit_point[2]);
	hit_vector.i = bits_to_float(hcu_swept_hit_vector[0]);
	hit_vector.j = bits_to_float(hcu_swept_hit_vector[1]);
	hit_vector.k = bits_to_float(hcu_swept_hit_vector[2]);
	miss_point.x = bits_to_float(hcu_swept_miss_point[0]);
	miss_point.y = bits_to_float(hcu_swept_miss_point[1]);
	miss_point.z = bits_to_float(hcu_swept_miss_point[2]);
	miss_vector.i = bits_to_float(hcu_swept_miss_vector[0]);
	miss_vector.j = bits_to_float(hcu_swept_miss_vector[1]);
	miss_vector.k = bits_to_float(hcu_swept_miss_vector[2]);
	radius = bits_to_float(HCU_SWEPT_RADIUS_BITS);

	memset(&sphere, 0, sizeof sphere);
	hit = collision_bsp_test_sphere(&view->bsp, 0, NULL, &hit_point, radius,
		&sphere);
	surface = &view->surfaces[HCU_SWEPT_SURFACE];
	if (!hit || sphere.surface_count != 1 ||
		sphere.surface_indices[0] != HCU_SWEPT_SURFACE ||
		sphere.edge_count != 0 || sphere.vertex_count != 0 ||
		!leaf_listed(sphere.leaf_indices, sphere.leaf_count, HCU_SWEPT_LEAF) ||
		surface->material_index != HCU_SWEPT_MATERIAL ||
		surface->plane_designator != HCU_SWEPT_PLANE_DESIGNATOR) {
		fprintf(stderr,
			"swept-fail bloodgulch_sphere_hit hit=%d surfaces=%ld first=%ld "
			"edges=%ld vertices=%ld leaf_count=%ld material=%d designator=%ld\n",
			hit, sphere.surface_count,
			sphere.surface_count > 0 ? sphere.surface_indices[0] : -1L,
			sphere.edge_count, sphere.vertex_count, sphere.leaf_count,
			(int)surface->material_index, surface->plane_designator);
		return 0;
	}
	printf("swept-subtest bloodgulch_sphere_hit surface=%ld material=%d "
		"leaf=%ld surfaces=%ld edges=%ld vertices=%ld status=passed\n",
		sphere.surface_indices[0], (int)surface->material_index,
		(long)HCU_SWEPT_LEAF, sphere.surface_count, sphere.edge_count,
		sphere.vertex_count);

	memset(&sphere, 0, sizeof sphere);
	hit = collision_bsp_test_sphere(&view->bsp, 0, NULL, &miss_point, radius,
		&sphere);
	if (hit || sphere.surface_count != 0 || sphere.edge_count != 0 ||
		sphere.vertex_count != 0) {
		fprintf(stderr,
			"swept-fail bloodgulch_sphere_miss hit=%d surfaces=%ld edges=%ld "
			"vertices=%ld\n",
			hit, sphere.surface_count, sphere.edge_count, sphere.vertex_count);
		return 0;
	}
	printf("swept-subtest bloodgulch_sphere_miss hit=0 surfaces=0 edges=0 "
		"vertices=0 leaves=%ld status=passed\n", sphere.leaf_count);

	memset(&pill, 0, sizeof pill);
	hit = collision_bsp_test_pill(&view->bsp, &hit_point, &hit_vector, radius,
		1.f, &pill);
	memcpy(&t_bits, &pill.t, sizeof t_bits);
	memcpy(plane_bits, &pill.plane, sizeof plane_bits);
	if (!hit || pill.surface_index != HCU_SWEPT_SURFACE ||
		pill.material_index != HCU_SWEPT_MATERIAL ||
		!leaf_listed(pill.leaf_indices, pill.leaf_count, HCU_SWEPT_LEAF) ||
		t_bits != 0 ||
		memcmp(plane_bits, hcu_swept_plane, sizeof plane_bits) != 0) {
		fprintf(stderr,
			"swept-fail bloodgulch_pill_hit hit=%d surface=%ld material=%d "
			"leaf_count=%ld t_bits=0x%08x plane=%08x %08x %08x %08x\n",
			hit, pill.surface_index, (int)pill.material_index, pill.leaf_count,
			t_bits, plane_bits[0], plane_bits[1], plane_bits[2], plane_bits[3]);
		return 0;
	}
	printf("swept-subtest bloodgulch_pill_hit surface=%ld material=%d leaf=%ld "
		"t=0.000000 status=passed\n",
		pill.surface_index, (int)pill.material_index, (long)HCU_SWEPT_LEAF);

	memset(&pill, 0, sizeof pill);
	hit = collision_bsp_test_pill(&view->bsp, &miss_point, &miss_vector, radius,
		1.f, &pill);
	if (hit) {
		memcpy(&t_bits, &pill.t, sizeof t_bits);
		fprintf(stderr,
			"swept-fail bloodgulch_pill_miss surface=%ld material=%d t_bits=0x%08x\n",
			pill.surface_index, (int)pill.material_index, t_bits);
		return 0;
	}
	printf("swept-subtest bloodgulch_pill_miss hit=0 leaves=%ld status=passed\n",
		pill.leaf_count);
	return 1;
}

int main(int argc, char **argv)
{
	struct swept_view view;
	short depth_before;
	short user_before;

	if (argc != 2) {
		fprintf(stderr, "usage: hcu-swept-collision <blob>\n");
		return 2;
	}
	global_current_collision_user_depth = 1;
	global_current_collision_users[0] = (short)0x5EE7;
	depth_before = global_current_collision_user_depth;
	user_before = global_current_collision_users[0];
	if (!load_view(&view, argv[1]))
		return 1;
	if (!synthetic_reference())
		return 1;
	if (swept_error_count != 0)
		return fail("CE error during synthetic reference");
	if (!retail_queries(&view))
		return 1;
	if (swept_error_count != 0)
		return fail("CE error during bloodgulch queries");
	if (memcmp(view.payload, view.snapshot, view.payload_bytes) != 0)
		return fail("published collision bytes changed");
	if (global_current_collision_user_depth != depth_before ||
		global_current_collision_users[0] != user_before)
		return fail("collision-user depth changed");
	printf("swept-subtest bsp_bytes bytes=%lu status=unchanged\n",
		view.payload_bytes);
	printf("swept-subtest collision_user depth=%d user0=0x%04x status=unchanged\n",
		(int)global_current_collision_user_depth,
		(unsigned)(global_current_collision_users[0] & 0xffff));
	free(view.payload);
	free(view.snapshot);
	return 0;
}
