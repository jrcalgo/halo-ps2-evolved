/* Host ILP32 harness for the extracted CE lightmap/material search.
   The Python audit splices the verbatim function over CE_FUNCTION.
   Layout offsets match structure_bsp / structure_lightmap / structure_material
   on Xbox (lightmaps +0x104, material surface range +0x14/+0x18, 256-byte
   materials, 32-byte lightmaps). This process does not link CE collision. */
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

typedef unsigned char byte;
typedef unsigned char boolean;
typedef unsigned short word;
typedef int long_is_32bit_assert[sizeof(long) == 4 ? 1 : -1];

#define TRUE 1
#define FALSE 0
#define TAG_BLOCK_GET_ELEMENT(block_address, index, type) \
	((type *)tag_block_get_element_fast((block_address), (index), sizeof(type)))
#define match_assert(file, line, expr) \
	do { \
		if (!(expr)) { \
			fprintf(stderr, "ce assert %s:%d %s query=%d\n", file, line, #expr, current_query); \
			exit(11); \
		} \
	} while (0)

struct tag_block_definition {
	char *name;
	unsigned long flags;
	long maximum_element_count;
	long element_size;
};

struct tag_block {
	long count;
	void *address;
	struct tag_block_definition *definition;
};

struct structure_material {
	byte shader[16];
	short permutation_index;
	word flags;
	long first_surface_index;
	long surface_count;
	byte rest[228];
};

struct structure_lightmap {
	short bitmap_index;
	word pad;
	long unused[4];
	struct tag_block materials;
};

struct structure_bsp {
	byte prefix[0x104];
	struct tag_block lightmaps;
};

typedef int material_size_assert[sizeof(struct structure_material) == 256 ? 1 : -1];
typedef int lightmap_size_assert[sizeof(struct structure_lightmap) == 32 ? 1 : -1];
typedef int tag_block_size_assert[sizeof(struct tag_block) == 12 ? 1 : -1];
typedef int material_first_assert[offsetof(struct structure_material, first_surface_index) == 0x14 ? 1 : -1];
typedef int material_count_assert[offsetof(struct structure_material, surface_count) == 0x18 ? 1 : -1];
typedef int lightmap_materials_assert[offsetof(struct structure_lightmap, materials) == 0x14 ? 1 : -1];
typedef int bsp_lightmaps_assert[offsetof(struct structure_bsp, lightmaps) == 0x104 ? 1 : -1];

static int slow_path_calls;
static volatile int collision_user_depth;
static int32_t current_query;

static void *tag_block_get_element_with_size(
	struct tag_block const *block,
	long index,
	long element_size)
{
	(void)block;
	(void)index;
	(void)element_size;
	slow_path_calls += 1;
	return NULL;
}

/* Copied from tag_groups.h so the extracted CE call uses the real fast path. */
static void *tag_block_get_element_fast(
	struct tag_block const *block,
	long index,
	long element_size)
{
	if (block && index >= 0 && index < block->count && block->address &&
		(!block->definition || block->definition->element_size == element_size))
	{
		return (char *)block->address + index * element_size;
	}
	return tag_block_get_element_with_size(block, index, element_size);
}

/* CE_FUNCTION */

static uint32_t fnv1a(unsigned char const *data, uint32_t size)
{
	uint32_t hash = 2166136261u;
	uint32_t i;

	for (i = 0; i < size; i++)
	{
		hash ^= data[i];
		hash *= 16777619u;
	}
	return hash;
}

static int read_full(FILE *stream, void *dst, size_t size)
{
	return fread(dst, 1, size, stream) == size;
}

static int write_full(FILE *stream, void const *src, size_t size)
{
	return fwrite(src, 1, size, stream) == size;
}

static int reloc_add(
	unsigned char *image,
	uint32_t image_size,
	uint32_t field,
	uint32_t addend,
	int keep_zero)
{
	uint32_t value;

	if (field > image_size - 4)
	{
		fprintf(stderr, "relocation field %u leaves image\n", field);
		return 0;
	}
	memcpy(&value, image + field, 4);
	if (value == 0 && keep_zero)
		return 1;
	if (value > 0xffffffffu - addend)
	{
		fprintf(stderr, "relocation at %u overflows\n", field);
		return 0;
	}
	value += addend;
	memcpy(image + field, &value, 4);
	return 1;
}

static int run_empty(void)
{
	struct structure_bsp structure;
	short lightmap_index;
	short material_index;
	boolean found;

	memset(&structure, 0, sizeof structure);
	lightmap_index = 7;
	material_index = 7;
	collision_user_depth = 0;
	found = structure_bsp_find_material_for_surface(&structure, 0, &lightmap_index, &material_index);
	printf("empty found=%d lightmap=%d material=%d depth=%d\n",
		found ? 1 : 0, lightmap_index, material_index, collision_user_depth);
	return (found == FALSE && collision_user_depth == 0) ? 0 : 1;
}

static int run_fixture(char const *fixture_path, char const *result_path)
{
	FILE *fixture;
	FILE *results;
	unsigned char magic[8];
	uint32_t image_size = 0;
	uint32_t reloc_count = 0;
	uint32_t tag_reloc_count = 0;
	uint32_t query_count = 0;
	int32_t expected_lightmaps = 0;
	int32_t expected_mat0_first = 0;
	int32_t expected_mat0_count = 0;
	uint32_t tag_base = 0;
	unsigned char *slab = NULL;
	unsigned char *image;
	unsigned char *saved = NULL;
	uint32_t *relocs = NULL;
	uint32_t *tag_relocs = NULL;
	int32_t *queries = NULL;
	int32_t *rows = NULL;
	uint32_t base;
	uint32_t root_value;
	uint32_t i;
	uint32_t fnv_before;
	uint32_t fnv_after;
	int32_t seen_lightmaps;
	int32_t mat0_first = -1;
	int32_t mat0_count = -1;
	int32_t depth_before;
	int32_t depth_after;
	uint32_t bytes_unchanged = 0;
	struct structure_bsp *structure;
	int status = 0;
	unsigned char header[44];

	if (sizeof(void *) != 4)
	{
		fprintf(stderr, "harness is not ILP32\n");
		return 9;
	}
	fixture = fopen(fixture_path, "rb");
	if (!fixture)
	{
		fprintf(stderr, "open fixture failed\n");
		return 8;
	}
	if (!read_full(fixture, magic, 8) || memcmp(magic, "LMFIX01", 8) != 0)
	{
		fprintf(stderr, "bad fixture magic\n");
		fclose(fixture);
		return 8;
	}
	if (!read_full(fixture, &image_size, 4) || !read_full(fixture, &reloc_count, 4) ||
		!read_full(fixture, &tag_reloc_count, 4) || !read_full(fixture, &query_count, 4) ||
		!read_full(fixture, &expected_lightmaps, 4) || !read_full(fixture, &expected_mat0_first, 4) ||
		!read_full(fixture, &expected_mat0_count, 4) || !read_full(fixture, &tag_base, 4))
	{
		fprintf(stderr, "truncated fixture header\n");
		fclose(fixture);
		return 8;
	}
	if (image_size < 0x110 || image_size > 32u * 1024u * 1024u || reloc_count > 1000000u ||
		tag_reloc_count > 1000000u || query_count > 200000u || expected_lightmaps < 0 ||
		expected_lightmaps > 4096)
	{
		fprintf(stderr, "fixture bounds rejected\n");
		fclose(fixture);
		return 8;
	}
	if (posix_memalign((void **)&slab, 16, image_size + 128) != 0)
	{
		fclose(fixture);
		return 8;
	}
	memset(slab, 0x5a, image_size + 128);
	image = slab + 64;
	saved = malloc(image_size);
	relocs = malloc(sizeof(uint32_t) * (reloc_count ? reloc_count : 1));
	tag_relocs = malloc(sizeof(uint32_t) * (tag_reloc_count ? tag_reloc_count : 1));
	queries = malloc(sizeof(int32_t) * (query_count ? query_count : 1));
	rows = malloc(sizeof(int32_t) * (query_count ? query_count : 1) * 3);
	if (!saved || !relocs || !tag_relocs || !queries || !rows ||
		!read_full(fixture, image, image_size) ||
		(reloc_count && !read_full(fixture, relocs, sizeof(uint32_t) * reloc_count)) ||
		(tag_reloc_count && !read_full(fixture, tag_relocs, sizeof(uint32_t) * tag_reloc_count)) ||
		(query_count && !read_full(fixture, queries, sizeof(int32_t) * query_count)))
	{
		fprintf(stderr, "truncated fixture body\n");
		status = 8;
		goto done;
	}
	fclose(fixture);
	fixture = NULL;
	memcpy(saved, image, image_size);
	fnv_before = fnv1a(saved, image_size);
	base = (uint32_t)(uintptr_t)image;
	if (base > 0xffffffffu - image_size)
	{
		fprintf(stderr, "image base overflows\n");
		status = 9;
		goto done;
	}
	for (i = 0; i < reloc_count; i++)
	{
		if (!reloc_add(image, image_size, relocs[i], base, 1))
		{
			status = 9;
			goto done;
		}
	}
	for (i = 0; i < tag_reloc_count; i++)
	{
		if (!reloc_add(image, image_size, tag_relocs[i], tag_base, 0))
		{
			status = 9;
			goto done;
		}
	}
	memcpy(&root_value, image, 4);
	if (root_value < base || root_value > base + image_size - sizeof(struct structure_bsp))
	{
		fprintf(stderr, "relocated root %u outside image\n", root_value);
		status = 4;
		goto done;
	}
	structure = (struct structure_bsp *)(uintptr_t)root_value;
	slow_path_calls = 0;
	seen_lightmaps = structure->lightmaps.count;
	if (seen_lightmaps != expected_lightmaps || structure->lightmaps.definition != NULL)
	{
		fprintf(stderr, "lightmap block count/definition %ld expected %ld def %p\n",
			(long)structure->lightmaps.count, (long)expected_lightmaps,
			(void *)structure->lightmaps.definition);
		status = 4;
		goto done;
	}
	for (i = 0; i < (uint32_t)seen_lightmaps; i++)
	{
		struct structure_lightmap *lightmap = TAG_BLOCK_GET_ELEMENT(
			&structure->lightmaps, (long)i, struct structure_lightmap);
		if (!lightmap || lightmap->materials.definition != NULL || lightmap->materials.count < 0)
		{
			fprintf(stderr, "lightmap %u materials unavailable\n", i);
			status = 4;
			goto done;
		}
	}
	if (seen_lightmaps > 0 && expected_mat0_count >= 0)
	{
		struct structure_lightmap *lightmap = TAG_BLOCK_GET_ELEMENT(
			&structure->lightmaps, 0, struct structure_lightmap);
		struct structure_material *material;
		if (lightmap->materials.count <= 0)
		{
			fprintf(stderr, "first lightmap has no materials\n");
			status = 4;
			goto done;
		}
		material = TAG_BLOCK_GET_ELEMENT(&lightmap->materials, 0, struct structure_material);
		mat0_first = material->first_surface_index;
		mat0_count = material->surface_count;
		if (mat0_first != expected_mat0_first || mat0_count != expected_mat0_count)
		{
			fprintf(stderr, "mat0 range %d+%d expected %d+%d\n",
				mat0_first, mat0_count, expected_mat0_first, expected_mat0_count);
			status = 4;
			goto done;
		}
	}
	if (slow_path_calls != 0)
	{
		fprintf(stderr, "tag block slow path during layout %u\n", slow_path_calls);
		status = 7;
		goto done;
	}
	collision_user_depth = 0;
	depth_before = collision_user_depth;
	slow_path_calls = 0;
	for (i = 0; i < query_count; i++)
	{
		short lightmap_index = 0x7fff;
		short material_index = 0x7fff;
		current_query = queries[i];
		boolean found = structure_bsp_find_material_for_surface(
			structure, queries[i], &lightmap_index, &material_index);
		rows[i * 3] = found ? 1 : 0;
		rows[i * 3 + 1] = lightmap_index;
		rows[i * 3 + 2] = material_index;
	}
	depth_after = collision_user_depth;
	if (depth_before != 0 || depth_after != 0)
	{
		fprintf(stderr, "collision user depth %d -> %d\n", depth_before, depth_after);
		status = 6;
	}
	if (slow_path_calls != 0)
	{
		fprintf(stderr, "tag block slow path calls %u\n", slow_path_calls);
		status = 7;
	}
	for (i = 0; i < 64; i++)
	{
		if (slab[i] != 0x5a || slab[64 + image_size + i] != 0x5a)
		{
			fprintf(stderr, "image canary changed\n");
			status = 5;
			break;
		}
	}
	memcpy(image, saved, image_size);
	fnv_after = fnv1a(image, image_size);
	bytes_unchanged = (fnv_after == fnv_before && memcmp(image, saved, image_size) == 0) ? 1u : 0u;
	if (!bytes_unchanged)
	{
		fprintf(stderr, "published image bytes changed\n");
		status = 5;
	}
	results = fopen(result_path, "wb");
	if (!results)
	{
		status = 8;
		goto done;
	}
	memcpy(header, "LMOK", 4);
	memcpy(header + 4, &bytes_unchanged, 4);
	memcpy(header + 8, &depth_before, 4);
	memcpy(header + 12, &depth_after, 4);
	memcpy(header + 16, &slow_path_calls, 4);
	memcpy(header + 20, &seen_lightmaps, 4);
	memcpy(header + 24, &mat0_first, 4);
	memcpy(header + 28, &mat0_count, 4);
	memcpy(header + 32, &fnv_before, 4);
	memcpy(header + 36, &fnv_after, 4);
	memcpy(header + 40, &query_count, 4);
	if (!write_full(results, header, 44) ||
		(query_count && !write_full(results, rows, sizeof(int32_t) * query_count * 3)))
	{
		status = 8;
	}
	fclose(results);
	printf("queries=%u lightmaps=%d mat0=%d+%d depth=%d/%d bytes_unchanged=%u slow=%u\n",
		query_count, seen_lightmaps, mat0_first, mat0_count, depth_before, depth_after,
		bytes_unchanged, slow_path_calls);
done:
	if (fixture)
		fclose(fixture);
	free(saved);
	free(relocs);
	free(tag_relocs);
	free(queries);
	free(rows);
	free(slab);
	return status;
}

int main(int argc, char **argv)
{
	if (argc == 2 && strcmp(argv[1], "empty") == 0)
		return run_empty();
	if (argc == 4 && strcmp(argv[1], "fixture") == 0)
		return run_fixture(argv[2], argv[3]);
	fprintf(stderr, "usage: %s empty | fixture <in> <out>\n", argv[0]);
	return 8;
}
