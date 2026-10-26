/* C4 validator parity driver for the three zero-byte BSP schema check descriptors.
 *
 * The production CE translation unit tag_schema_collision.c is included verbatim, so
 * the static callbacks (structure_bsp_check, structure_detail_object_data_check,
 * structure_collision_bsp_check) and their callees (collision_bsp_graph_check,
 * bsp3d_check, bsp2d_check, collision_leaves_check, collision_surfaces_check) run
 * unmodified. Only the two reporting functions from tag_validate.c are stubbed: they
 * record the message and perform the same side effect (refused flag, or a counted
 * correction) that CE's implementations perform.
 *
 * Each case prints one line:
 *   CASE <name> result=<0|1> corrections=<n> refused=<0|1> message="<text>"
 */
#include "cseries.h"
#include "tag_schema.h"
/* c4_validators_types.inc: enum and structs copied verbatim from tag_validate.c by the
 * Python harness (private to that file in CE). */
#include "c4_validators_types.inc"

#include "../submodules/halo-ce-universal/port/linux/game/tag_schema_collision.c"

#include <stdarg.h>
#include <stdio.h>
#include <string.h>

static long s_corrections;
static char s_message[512];

static void record(const char *format, va_list arguments)
{
	vsnprintf(s_message, sizeof s_message, format, arguments);
}

void tag_validate_refuse(struct tag_validation *validation, char const *format, ...)
{
	va_list arguments;
	validation->refused = TRUE;
	va_start(arguments, format);
	record(format, arguments);
	va_end(arguments);
}

void tag_validate_correct(struct tag_validation *validation, char const *format, ...)
{
	va_list arguments;
	(void)validation;
	s_corrections++;
	va_start(arguments, format);
	record(format, arguments);
	va_end(arguments);
}

/* Data-only accessors. tag_validate_contains answers from the region the context was
 * built over; the schema-table, tag-lookup and buffer accessors report "none", which is
 * the not-found branch the checks take when the owning tag or buffer is absent. */
boolean tag_validate_custom_edition(struct tag_validation *validation)
{
	(void)validation;
	return FALSE;
}
boolean tag_validate_contains(struct tag_validation *validation, void const *address,
	unsigned long size)
{
	const unsigned char *start = (const unsigned char *)validation->region;
	const unsigned char *at = (const unsigned char *)address;
	if (!address || !validation->region) return FALSE;
	return at >= start && size <= validation->region_size &&
		(unsigned long)(at - start) <= validation->region_size - size;
}
void *tag_validate_tag_get(struct tag_validation *validation, long tag_index,
	unsigned long group_tag)
{
	(void)validation; (void)tag_index; (void)group_tag;
	return NULL;
}
/* A material's buffer is the bsp's own buffer: the hardware_format it names is its data
 * (data-only accessor; containment is then checked by tag_validate_contains). */
void *tag_validate_vertex_buffer_data(struct tag_validation *validation, void const *buffer)
{
	(void)validation;
	return (void *)buffer;
}
void *tag_validate_index_buffer_data(struct tag_validation *validation, void const *buffer)
{
	(void)validation;
	return (void *)buffer;
}

/* CE's cseries helpers are macros over memset/memcpy in the headers; provide loops. */
void *csmemset(void *buffer, long c, unsigned long size)
{
	unsigned char *p = (unsigned char *)buffer;
	unsigned long i;
	for (i = 0; i < size; i++) p[i] = (unsigned char)c;
	return buffer;
}
void *csmemcpy(void *destination, const void *source, unsigned long size)
{
	unsigned char *d = (unsigned char *)destination;
	const unsigned char *s2 = (const unsigned char *)source;
	unsigned long i;
	for (i = 0; i < size; i++) d[i] = s2[i];
	return destination;
}
unsigned long csstrlen(const char *s1)
{
	unsigned long n = 0;
	while (s1[n]) n++;
	return n;
}

static void begin(void)
{
	s_corrections = 0;
	s_message[0] = 0;
}

static void report(const char *name, int result, int refused)
{
	printf("CASE %s result=%d corrections=%ld refused=%d message=\"%s\"\n",
		name, result, s_corrections, refused, s_message);
}

/* Storage for fixtures. Every array is a whole-block the checks index by count. */
static struct bsp3d_node s_nodes[4];
static struct real_plane3d s_planes[4];
static struct collision_leaf_fixture { unsigned char bytes[64]; } s_leaves[4];
static struct bsp2d_reference s_bsp2d_refs[4];
static struct structure_leaf s_structure_leaves[4];
static struct structure_surface_reference s_surface_refs[4];
static struct structure_cluster_portal s_portals[4];
static struct detail_object_cell_definition s_cells[4];
static word s_counts[16];
/* A material's uncompressed environment vertices: 0x38 bytes each (type 0). */
static unsigned char s_vertex_bytes[0x38 * 4];

static void collision_valid_one_leaf(struct collision_bsp *bsp)
{
	memset(bsp, 0, sizeof *bsp);
	memset(s_nodes, 0, sizeof s_nodes);
	memset(s_leaves, 0, sizeof s_leaves);
	bsp->bsp3d.planes.count = 1;
	bsp->bsp3d.planes.address = s_planes;
	bsp->bsp3d.nodes.count = 1;
	bsp->bsp3d.nodes.address = s_nodes;
	s_nodes[0].children[0] = LONG_MIN | 0;
	s_nodes[0].children[1] = LONG_MIN | 0;
	bsp->leaves.count = 1;
	bsp->leaves.address = s_leaves;
}

int main(void)
{
	struct tag_validation validation;
	struct collision_bsp collision;
	struct structure_bsp structure;
	struct structure_detail_object_data detail;
	struct structure_material material;
	struct collision_bsp *collision_pointer;
	int ok;

	/* Collision: valid minimal bsp is accepted with no correction. */
	begin();
	memset(&validation, 0, sizeof validation);
	collision_valid_one_leaf(&collision);
	ok = structure_collision_bsp_check(&validation, &collision);
	report("collision_valid_one_leaf", ok, validation.refused);

	/* Collision: nodes with no planes are refused (the designator needs a plane). */
	begin();
	memset(&validation, 0, sizeof validation);
	collision_valid_one_leaf(&collision);
	collision.bsp3d.planes.count = 0;
	ok = structure_collision_bsp_check(&validation, &collision);
	report("collision_nodes_without_planes", ok, validation.refused);

	/* Collision: a child naming a leaf past the leaf count is corrected to NONE. */
	begin();
	memset(&validation, 0, sizeof validation);
	collision_valid_one_leaf(&collision);
	s_nodes[0].children[0] = LONG_MIN | 5;
	ok = structure_collision_bsp_check(&validation, &collision);
	report("collision_child_leaf_out_of_range", ok, validation.refused);
	printf("CHILD_AFTER %ld\n", (long)s_nodes[0].children[0]);

	/* Collision: bsp2d references with no surfaces are dropped by correction. */
	begin();
	memset(&validation, 0, sizeof validation);
	collision_valid_one_leaf(&collision);
	memset(s_bsp2d_refs, 0, sizeof s_bsp2d_refs);
	collision.bsp2d_references.count = 2;
	collision.bsp2d_references.address = s_bsp2d_refs;
	ok = structure_collision_bsp_check(&validation, &collision);
	report("collision_bsp2d_refs_without_surfaces", ok, validation.refused);
	printf("REFS_AFTER %ld\n", collision.bsp2d_references.count);

	/* Detail objects: no cells is accepted and stays valid. */
	begin();
	memset(&validation, 0, sizeof validation);
	memset(&detail, 0, sizeof detail);
	detail.valid = TRUE;
	ok = structure_detail_object_data_check(&validation, &detail);
	printf("DETAIL_VALID_AFTER_EMPTY %d\n", (int)detail.valid);
	report("detail_no_cells", ok, validation.refused);

	/* Detail objects: cells out of (x,y,z) order are corrected and the data is
	 * marked invalid so none is drawn. */
	begin();
	memset(&validation, 0, sizeof validation);
	memset(&detail, 0, sizeof detail);
	memset(s_cells, 0, sizeof s_cells);
	s_cells[0].cell_x = 5;
	s_cells[1].cell_x = 1;
	detail.valid = TRUE;
	detail.cells.count = 2;
	detail.cells.address = s_cells;
	detail.counts.count = 0;
	detail.counts.address = s_counts;
	ok = structure_detail_object_data_check(&validation, &detail);
	printf("DETAIL_VALID_AFTER_ORDER %d\n", (int)detail.valid);
	report("detail_cells_out_of_order", ok, validation.refused);

	/* Detail objects: a negative count index is corrected and invalidates the data. */
	begin();
	memset(&validation, 0, sizeof validation);
	memset(&detail, 0, sizeof detail);
	memset(s_cells, 0, sizeof s_cells);
	s_cells[0].count_index = -1;
	detail.valid = TRUE;
	detail.cells.count = 1;
	detail.cells.address = s_cells;
	detail.counts.count = 0;
	detail.counts.address = s_counts;
	ok = structure_detail_object_data_check(&validation, &detail);
	printf("DETAIL_VALID_AFTER_NEGATIVE %d\n", (int)detail.valid);
	report("detail_negative_count_index", ok, validation.refused);

	/* Structure: a valid bsp with a collision bsp is accepted. */
	begin();
	memset(&validation, 0, sizeof validation);
	memset(&structure, 0, sizeof structure);
	collision_valid_one_leaf(&collision);
	collision_pointer = &collision;
	structure.collision_bsp.count = 1;
	structure.collision_bsp.address = collision_pointer;
	ok = structure_bsp_check(&validation, &structure);
	report("structure_valid_with_collision", ok, validation.refused);

	/* Structure: no collision bsp is refused. */
	begin();
	memset(&validation, 0, sizeof validation);
	memset(&structure, 0, sizeof structure);
	ok = structure_bsp_check(&validation, &structure);
	report("structure_without_collision_bsp", ok, validation.refused);

	/* Structure: a leaf naming surface references past the table is corrected. */
	begin();
	memset(&validation, 0, sizeof validation);
	memset(&structure, 0, sizeof structure);
	collision_valid_one_leaf(&collision);
	collision_pointer = &collision;
	structure.collision_bsp.count = 1;
	structure.collision_bsp.address = collision_pointer;
	memset(s_structure_leaves, 0, sizeof s_structure_leaves);
	s_structure_leaves[0].surface_reference_count = 3;
	s_structure_leaves[0].first_surface_reference_index = 0;
	structure.leaves.count = 1;
	structure.leaves.address = s_structure_leaves;
	structure.surface_references.count = 0;
	ok = structure_bsp_check(&validation, &structure);
	report("structure_leaf_references_out_of_range", ok, validation.refused);
	printf("LEAF_COUNT_AFTER %d\n", (int)s_structure_leaves[0].surface_reference_count);

	/* Structure: a surface reference naming a node past the collision bsp is reset. */
	begin();
	memset(&validation, 0, sizeof validation);
	memset(&structure, 0, sizeof structure);
	collision_valid_one_leaf(&collision);
	collision_pointer = &collision;
	structure.collision_bsp.count = 1;
	structure.collision_bsp.address = collision_pointer;
	memset(s_surface_refs, 0, sizeof s_surface_refs);
	s_surface_refs[0].bsp3d_node_index = 7;
	structure.surface_references.count = 1;
	structure.surface_references.address = s_surface_refs;
	ok = structure_bsp_check(&validation, &structure);
	report("structure_surface_reference_node_out_of_range", ok, validation.refused);
	printf("NODE_REF_AFTER %ld\n", (long)s_surface_refs[0].bsp3d_node_index);

	/* Structure: a negative leaf reference count (a bad count) is corrected to none. */
	begin();
	memset(&validation, 0, sizeof validation);
	memset(&structure, 0, sizeof structure);
	collision_valid_one_leaf(&collision);
	collision_pointer = &collision;
	structure.collision_bsp.count = 1;
	structure.collision_bsp.address = collision_pointer;
	memset(s_structure_leaves, 0, sizeof s_structure_leaves);
	s_structure_leaves[0].surface_reference_count = -1;
	structure.leaves.count = 1;
	structure.leaves.address = s_structure_leaves;
	ok = structure_bsp_check(&validation, &structure);
	report("structure_negative_leaf_reference_count", ok, validation.refused);

	/* Structure: a cluster portal naming a plane past the collision bsp's planes. */
	begin();
	memset(&validation, 0, sizeof validation);
	memset(&structure, 0, sizeof structure);
	collision_valid_one_leaf(&collision);
	collision_pointer = &collision;
	structure.collision_bsp.count = 1;
	structure.collision_bsp.address = collision_pointer;
	memset(s_portals, 0, sizeof s_portals);
	s_portals[0].plane_index = 9;
	structure.cluster_portals.count = 1;
	structure.cluster_portals.address = s_portals;
	ok = structure_bsp_check(&validation, &structure);
	report("structure_portal_plane_out_of_range", ok, validation.refused);
	printf("PORTAL_PLANE_AFTER %ld\n", (long)s_portals[0].plane_index);


	/* Material vertex buffers (structure_material.vertices, the inline vertex_buffer record at
	 * structure_material 0xb0; copious_unused at 0xae is not an input to this check): a buffer the
	 * bsp holds with its count inside it is accepted with no correction. */
	begin();
	memset(&validation, 0, sizeof validation);
	memset(s_vertex_bytes, 0, sizeof s_vertex_bytes);
	validation.region = s_vertex_bytes;
	validation.region_size = sizeof s_vertex_bytes;
	memset(&material, 0, sizeof material);
	material.vertices.type = 0;
	material.vertices.count = 2;
	material.vertices.hardware_format = s_vertex_bytes;
	structure_vertex_buffer_check(&validation, &material.vertices, FALSE, 0, 0);
	printf("MATERIAL_VB_FORMAT_AFTER_CONTAINED %d\n", material.vertices.hardware_format != NULL);
	printf("MATERIAL_VB_COUNT_AFTER_CONTAINED %ld\n", material.vertices.count);
	report("material_vertex_buffer_contained", material.vertices.hardware_format != NULL, validation.refused);

	/* A count past the bsp's buffer is corrected: the buffer is none and is not drawn. */
	begin();
	memset(&validation, 0, sizeof validation);
	validation.region = s_vertex_bytes;
	validation.region_size = 0x38 * 2;
	memset(&material, 0, sizeof material);
	material.vertices.type = 0;
	material.vertices.count = 4;
	material.vertices.hardware_format = s_vertex_bytes;
	structure_vertex_buffer_check(&validation, &material.vertices, FALSE, 0, 0);
	printf("MATERIAL_VB_FORMAT_AFTER_PAST %d\n", material.vertices.hardware_format != NULL);
	report("material_vertex_buffer_past_region", material.vertices.hardware_format != NULL, validation.refused);

	return 0;
}