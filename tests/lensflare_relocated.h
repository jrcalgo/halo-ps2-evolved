/* Shared ABI for the relocated lens-flare selector harness.
 * The partial structure_bsp matches the layout rasterizer_lights.c uses
 * when it reads lens flares, markers, and clusters. */
#ifndef LENSFLARE_RELOCATED_H
#define LENSFLARE_RELOCATED_H

#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>

#if !defined(HCU_PS2_CACHE_TEST_CSERIES_H)
typedef unsigned char byte;
typedef unsigned char boolean;
#endif

typedef unsigned short word;
typedef float real;
typedef struct { real x, y, z; } real_point3d;
typedef struct { real i, j, k; } real_vector3d;

#ifndef NONE
#define NONE (-1)
#endif
#ifndef MIN
#define MIN(a, b) ((a) < (b) ? (a) : (b))
#endif
#ifndef SHORT_MAX
#define SHORT_MAX 32767
#endif
/* source/render/render.h */
#ifndef MAXIMUM_QUEUED_LENS_FLARES
#define MAXIMUM_QUEUED_LENS_FLARES 8
#endif

#define LENSFLARE_SPRITE_REQUEST_BOUND (SHORT_MAX + 1 - MAXIMUM_QUEUED_LENS_FLARES)

struct tag_block_definition;

struct tag_block {
	long count;
	void *address;
	struct tag_block_definition *definition;
};

struct tag_reference {
	unsigned long group_tag;
	char *name;
	long name_length;
	long index;
};

struct structure_bsp {
	byte reserved000[0x11C];
	struct tag_block lens_flares;
	struct tag_block lens_flare_markers;
	struct tag_block clusters;
};

struct structure_cluster {
	byte reserved00[0x40];
	word first_lens_flare_marker_index;
	word lens_flare_marker_count;
	byte reserved44[0x24];
};

struct structure_lens_flare {
	struct tag_reference lens_flare;
};

struct structure_lens_flare_marker {
	real_point3d position;
	char i_direction;
	char j_direction;
	char k_direction;
	byte lens_flare_index;
};

struct lens_flare_definition {
	int unused;
};

struct rasterizer_lens_flare_submit_parameters {
	struct lens_flare_definition *definition;
	real_point3d position;
	unsigned long compressed_direction;
	unsigned long compressed_up;
	unsigned long compressed_light_color;
	short light_identifier;
	short light_index;
	short lens_flare_index;
	byte compressed_window_index;
	byte compressed_light_scale;
	long internal__occlusion_pixels;
};

struct lensflare_render_state {
	int window_index;
};

typedef char lensflare_assert_cluster_size[
	sizeof(struct structure_cluster) == 0x68 ? 1 : -1];
typedef char lensflare_assert_cluster_count_offset[
	offsetof(struct structure_cluster, lens_flare_marker_count) == 0x42 ? 1 : -1];
typedef char lensflare_assert_marker_size[
	sizeof(struct structure_lens_flare_marker) == 0x10 ? 1 : -1];
typedef char lensflare_assert_marker_index_offset[
	offsetof(struct structure_lens_flare_marker, lens_flare_index) == 15 ? 1 : -1];
typedef char lensflare_assert_flare_size[
	sizeof(struct structure_lens_flare) == 0x10 ? 1 : -1];
typedef char lensflare_assert_block_size[
	sizeof(struct tag_block) == 12 ? 1 : -1];
typedef char lensflare_assert_reference_size[
	sizeof(struct tag_reference) == 16 ? 1 : -1];
typedef char lensflare_assert_reference_index[
	offsetof(struct tag_reference, index) == 12 ? 1 : -1];
typedef char lensflare_assert_bsp_flares[
	offsetof(struct structure_bsp, lens_flares) == 0x11C ? 1 : -1];
typedef char lensflare_assert_sprite_bound[
	LENSFLARE_SPRITE_REQUEST_BOUND == 32760 ? 1 : -1];

extern unsigned char lensflare_bsp_cache[];
extern unsigned long lensflare_bsp_published_bytes;
extern unsigned char lensflare_tag_cache[];
extern unsigned long lensflare_tag_published_bytes;
extern int lensflare_active_cluster;
extern struct lensflare_render_state render;

int lensflare_draw_lens_flares(void);
int screenshot_in_progress(void);
struct structure_bsp *global_structure_bsp_get(void);
void lens_flare_data_error(char const *message);
void set_real_vector3d(real_vector3d *vector, real i, real j, real k);
void perpendicular3d(real_vector3d const *direction, real_vector3d *up);
void normalize3d(real_vector3d *vector);
unsigned long compress_real_vector3d_to_int32_clamp(real_vector3d const *vector);
struct lens_flare_definition *lens_flare_definition_get(long index);
void rasterizer_lens_flare_submit(struct rasterizer_lens_flare_submit_parameters *parameters);
void rasterizer_lens_flare_submit_for_cluster(short cluster_index);

/* Null-definition branch of tag_block_get_element_fast, plus a published-image
 * bound the fixture requires. Retail CBSP leaves these definition pointers null. */
static inline void *lensflare_block_element(struct tag_block const *block,
	long index, long element_size)
{
	unsigned long bytes;
	uintptr_t base, address, end;
	if (!block || index < 0 || index >= block->count || !block->address ||
		block->definition || element_size <= 0 ||
		(unsigned long)block->count >
			(unsigned long)-1 / (unsigned long)element_size) {
		fprintf(stderr, "lensflare block-element rejected\n");
		exit(20);
	}
	bytes = (unsigned long)block->count * (unsigned long)element_size;
	base = (uintptr_t)lensflare_bsp_cache;
	address = (uintptr_t)block->address;
	end = base + lensflare_bsp_published_bytes;
	if (!lensflare_bsp_published_bytes || address < base || address > end ||
		bytes > end - address) {
		fprintf(stderr, "lensflare block leaves published BSP\n");
		exit(21);
	}
	return (byte *)block->address + (unsigned long)index * (unsigned long)element_size;
}

#define TAG_BLOCK_GET_ELEMENT(block_address, index, type) \
	((type *)lensflare_block_element((block_address), (index), sizeof(type)))

#endif
