#include "cseries.h"
#include "tag_schema.h"

#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#undef malloc
#undef free
#undef memset
#undef memcpy
#undef strcat
#undef strlen

/* Exercise the dynamic binding contract with a cache larger than the 2 MiB
 * bootstrap, plus a separate BSP span. */
static unsigned long cache_size = 10UL * 1024UL * 1024UL;
static unsigned char structure_bsp_cache[4096] __attribute__((aligned(16)));
static unsigned long structure_bsp_cache_size = sizeof(structure_bsp_cache);
static unsigned char tag_cache[98304] __attribute__((aligned(16)));

static struct tag_schema_field structure_bsp_fields[] = { TAG_SCHEMA_END };
static struct tag_schema_definition structure_bsp_definition = {
	"test_structure_bsp", sizeof(unsigned long), structure_bsp_fields
};
static struct tag_schema_field scenario_fields[] = { TAG_SCHEMA_END };
static struct tag_schema_definition scenario_definition = {
	"test_scenario", sizeof(unsigned long), scenario_fields
};
static struct tag_schema_group test_groups[] = {
	{ 'scnr', { NONE, NONE }, &scenario_definition },
	{ 'sbsp', { NONE, NONE }, &structure_bsp_definition },
	{ 0, { 0, 0 }, NULL }
};
static struct tag_schema_group const empty_groups[] = {{ 0, { 0, 0 }, NULL }};
struct tag_schema_group const *const tag_schema_group_lists[] = { test_groups, empty_groups, NULL };
struct tag_schema_group const tag_schema_custom_edition_groups[] = {{ 0, { 0, 0 }, NULL }};

unsigned long physical_memory_get_tag_cache_size(void) { return cache_size; }
void *physical_memory_get_structure_bsp_cache_base_address(void) { return structure_bsp_cache; }
unsigned long physical_memory_get_structure_bsp_cache_size(void) { return structure_bsp_cache_size; }
void tag_validate_report(char const *message)
{
	fputs(message, stderr);
	fputc('\n', stderr);
}

void *csmemset(void *buffer, long value, unsigned long size)
{
	return memset(buffer, (int)value, (size_t)size);
}

void *csmemcpy(void *destination, const void *source, unsigned long size)
{
	return memcpy(destination, source, (size_t)size);
}

char *csstrcat(char *left, char const *right) { return strcat(left, right); }
unsigned long csstrlen(char const *text) { return (unsigned long)strlen(text); }

int main(void)
{
	unsigned long claims_words = (cache_size + structure_bsp_cache_size + 31) / 32;
	size_t claims_bytes = claims_words * sizeof(unsigned long);
	unsigned char *allocation = malloc(claims_bytes + 32768 + 64);
	uintptr_t aligned;
	unsigned char *claims;
	unsigned char tag_bytes[4] = { 0 };
	struct tag_validate_header_fixture
	{
		void *instances;
		long scenario_tag_index;
		unsigned long checksum;
		long tag_count;
		long vertex_buffer_count;
		void *vertex_buffers;
		long index_buffer_count;
		void *index_buffers;
		unsigned long signature;
	} *header;
	struct tag_validate_instance_fixture
	{
		unsigned long group_tag;
		unsigned long parents[2];
		long tag_index;
		char *name;
		void *base_address;
		unsigned long unused[2];
	} *instances;
	struct tag_validate_structure_bsp_header_fixture
	{
		void *base_address;
		long vertex_buffer_count;
		void *vertex_buffers;
		long index_buffer_count;
		void *index_buffers;
		unsigned long signature;
	} *bsp_header;
	size_t i;

	if (!allocation)
		return 1;
	aligned = ((uintptr_t)allocation + 15) & ~(uintptr_t)15;
	claims = (unsigned char *)aligned;
	if (tag_validate_claims_buffer_size() != claims_bytes)
		return 14;
	if (tag_validate_claims_buffer_ready())
		return 16;
	memset(claims + claims_bytes, 0xA5, 32);
	if (tag_validate_bind_claims_buffer(claims, claims_bytes - sizeof(unsigned long)))
		return 2;
	if (!tag_validate_bind_claims_buffer(claims, claims_bytes))
		return 3;
	if (!tag_validate_claims_buffer_ready())
		return 17;
	/* Invalid minimal input still initializes the exact caller-owned span. */
	if (tag_validate_tags(tag_bytes, sizeof(tag_bytes), sizeof(tag_bytes), "scratch-test"))
		return 4;
	if (!tag_validate_any_claimed((void *)(uintptr_t)1, 1))
		return 7;
	if (!tag_validate_any_claimed(tag_bytes, cache_size + 1))
		return 8;
	for (i = 0; i < 32; ++i)
		if (claims[claims_bytes + i] != 0xA5)
			return 5;
	tag_validate_release_claims_buffer();
	if (tag_validate_claims_buffer_ready())
		return 18;
	cache_size = sizeof(tag_cache);
	claims_words = (cache_size + structure_bsp_cache_size + 31) / 32;
	claims_bytes = claims_words * sizeof(unsigned long);
	if (tag_validate_claims_buffer_size() != claims_bytes)
		return 15;
	if (!tag_validate_bind_claims_buffer(claims, claims_bytes))
		return 6;
	if (!tag_validate_claims_buffer_ready())
		return 19;
	memset(tag_cache, 0, sizeof(tag_cache));
	header = (struct tag_validate_header_fixture *)tag_cache;
	instances = (struct tag_validate_instance_fixture *)(tag_cache + sizeof(*header));
	header->instances = instances;
	header->scenario_tag_index = 0;
	header->tag_count = 2;
	header->signature = 0x74616773;
	instances[0].group_tag = 'scnr';
	instances[0].parents[0] = instances[0].parents[1] = 0xFFFFFFFFUL;
	instances[0].tag_index = 0;
	instances[0].name = (char *)(tag_cache + 128);
	instances[0].base_address = tag_cache + 184;
	instances[1].group_tag = 'sbsp';
	instances[1].parents[0] = instances[1].parents[1] = 0xFFFFFFFFUL;
	instances[1].tag_index = 1;
	instances[1].name = (char *)(tag_cache + 160);
	memcpy(instances[0].name, "levels/test/test", sizeof("levels/test/test"));
	memcpy(instances[1].name, "levels/test/test_bsp0", sizeof("levels/test/test_bsp0"));
	if (!tag_validate_tags(tag_cache, 192, 192, "separate-bsp-test"))
		return 9;
	memset(structure_bsp_cache, 0, sizeof(structure_bsp_cache));
	bsp_header = (struct tag_validate_structure_bsp_header_fixture *)structure_bsp_cache;
	bsp_header->base_address = structure_bsp_cache + sizeof(*bsp_header);
	bsp_header->signature = 'sbsp';
	if (!tag_validate_structure_bsp(1, structure_bsp_cache, sizeof(structure_bsp_cache)))
		return 10;
	if (!tag_validate_claimed(structure_bsp_cache + sizeof(*bsp_header)))
		return 11;
	if (!tag_validate_claimed(tag_cache + sizeof(*header)))
		return 12;
	if (tag_validate_any_claimed((void *)(tag_cache + 128), strlen("levels/test/test") + 1))
		return 13;
	tag_validate_release_claims_buffer();
	free(allocation);
	return 0;
}
