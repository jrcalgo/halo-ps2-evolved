#include "cseries.h"
#include "tag_schema.h"
#include "ps2_ctag.h"
#include "halo_ps2_cache.h"

#undef malloc
#undef free
#undef memset
#undef memcpy
#undef strcat
#undef strcmp
#undef strlen

#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

typedef char fixture_ilp32[sizeof(void *) == 4 && sizeof(long) == 4 ? 1 : -1];

typedef struct
{
	uint32_t *tag_instances;
	int32_t scenario_tag_index;
	uint32_t checksum;
	int32_t tag_count;
	int32_t vertex_buffer_count;
	uint32_t *vertex_buffers;
	int32_t index_buffer_count;
	uint32_t *index_buffers;
	uint32_t signature;
} hcu_profile_tag_header;

typedef struct
{
	uint32_t group_tag;
	uint32_t parent_group_tags[2];
	int32_t tag_index;
	char *name;
	uint8_t *base_address;
	uint32_t unused[2];
} hcu_profile_tag_instance;

typedef struct
{
	uint8_t *payload;
	size_t payload_size;
} hcu_profile_payload_owner;

static unsigned long s_tag_cache_size = HALO_PORT_TAG_CACHE_SIZE;
static void *s_tag_cache_base;
static void *s_claims_buffer;

unsigned long physical_memory_get_tag_cache_size(void) { return s_tag_cache_size; }
void *physical_memory_get_tag_cache_base_address(void) { return s_tag_cache_base; }
void *physical_memory_get_structure_bsp_cache_base_address(void) { return NULL; }
unsigned long physical_memory_get_structure_bsp_cache_size(void) { return 0; }

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

void *debug_malloc(unsigned int size, boolean clear, const char *file, long line)
{
	void *result = malloc((size_t)size);
	(void)file; (void)line;
	if (clear && result) memset(result, 0, (size_t)size);
	return result;
}
void debug_free(void *buffer, const char *file, long line)
{
	(void)file; (void)line;
	free(buffer);
}

char *csstrcat(char *left, char const *right) { return strcat(left, right); }
unsigned long csstrlen(char const *text) { return (unsigned long)strlen(text); }
long csstrcmp(char const *left, char const *right) { return (long)strcmp(left, right); }

static int load_file(const char *path, uint8_t **out, size_t *size)
{
	FILE *f = fopen(path, "rb");
	long n;
	if (!f || fseek(f, 0, SEEK_END) || (n = ftell(f)) < 0 || fseek(f, 0, SEEK_SET))
	{
		if (f) fclose(f);
		return 0;
	}
	*out = (uint8_t *)malloc((size_t)n);
	if (!*out || fread(*out, 1, (size_t)n, f) != (size_t)n)
	{
		free(*out);
		fclose(f);
		return 0;
	}
	fclose(f);
	*size = (size_t)n;
	return 1;
}

static int points_into(const uint8_t *base, size_t size, const void *p, size_t n)
{
	uintptr_t b = (uintptr_t)base, q = (uintptr_t)p;
	return q >= b && q - b <= size && n <= size - (size_t)(q - b);
}

static int write_validation_deltas(const char *path, const uint8_t *before,
	const uint8_t *after, size_t size)
{
	FILE *out = fopen(path, "w");
	size_t i, spans = 0, changed = 0;
	if (!out) return 0;
	fprintf(out, "{\"format\":\"hcu-validator-byte-deltas-v1\",\"image_size\":%lu,\"spans\":[", (unsigned long)size);
	for (i = 0; i < size; )
	{
		size_t start, end, j;
		if (before[i] == after[i]) { i++; continue; }
		start = i;
		while (i < size && before[i] != after[i]) { i++; changed++; }
		end = i;
		if (spans++) fputc(',', out);
		fprintf(out, "{\"offset\":%lu,\"before_hex\":\"", (unsigned long)start);
		for (j = start; j < end; j++) fprintf(out, "%02x", before[j]);
		fputs("\",\"after_hex\":\"", out);
		for (j = start; j < end; j++) fprintf(out, "%02x", after[j]);
		fputs("\"}", out);
	}
	fprintf(out, "],\"changed_bytes\":%lu,\"span_count\":%lu}\n", (unsigned long)changed, (unsigned long)spans);
	return fclose(out) == 0;
}

int main(int argc, char **argv)
{
	uint8_t *payload = NULL;
	uint8_t *before_image = NULL;
	size_t payload_size = 0;
	ps2_ctag_view view;
	ps2_ctag_status ctag_status;
	hcu_profile_tag_header *header;
	hcu_profile_tag_instance *instances;
	hcu_profile_tag_instance *held_first;
	char *held_name;
	uint8_t *held_root;
	uint32_t saved_signature;
	int mounted, valid, corrupt_rejected = 0, owner_unpublished = 0;
	int pointers_stable;
	long validation_corrections;
	const char *released_after_unmount;
	long file_length;
	const char *profile;
	if ((argc != 4 && argc != 5 && argc != 6) || !load_file(argv[1], &payload, &payload_size)) return 2;
	profile = argv[2];
	file_length = strtol(argv[3], NULL, 0);
	if (argc >= 5)
	{
		unsigned long requested = strtoul(argv[4], NULL, 0);
		unsigned long claims_size;
		if (!requested || requested > HALO_PORT_TAG_CACHE_SIZE ||
			posix_memalign(&s_tag_cache_base, 16, requested) != 0)
			return 12;
		s_tag_cache_size = requested;
		memset(s_tag_cache_base, 0, requested);
		claims_size = tag_validate_claims_buffer_size();
		if (!claims_size || posix_memalign(&s_claims_buffer, 16, claims_size) != 0 ||
			!tag_validate_bind_claims_buffer(s_claims_buffer, claims_size))
			return 13;
	}
	fprintf(stderr, "ceval-step=load profile=%s\n", profile);
	if (file_length < 0) return 3;
	mounted = ps2_cache_mount_ctag(profile, payload, payload_size);
	fprintf(stderr, "ceval-step=mount result=%d bytes=%lu\n", mounted, (unsigned long)payload_size);
	ctag_status = ps2_ctag_open(&view, payload, payload_size,
		payload_size, (uint32_t)(payload_size / 4u));
	fprintf(stderr, "ceval-step=open status=%d image=%lu relocs=%lu\n", (int)ctag_status,
		ctag_status == PS2_CTAG_OK ? (unsigned long)view.image_size : 0,
		ctag_status == PS2_CTAG_OK ? (unsigned long)view.relocation_count : 0);
	if (ctag_status != PS2_CTAG_OK)
	{
		printf("profile-ce-validation profile=%s ctag=reject status=%d mount=%d image_size=0 capacity=%lu\n",
			profile, (int)ctag_status, mounted, s_tag_cache_size);
		free(payload);
		return 0;
	}
	if (view.image_size < sizeof(*header)) return 4;
	if (s_tag_cache_base)
	{
		if (ps2_ctag_materialize(&view, (uint32_t)(uintptr_t)s_tag_cache_base,
			(uint8_t *)s_tag_cache_base, s_tag_cache_size) != PS2_CTAG_OK)
			return 5;
		fprintf(stderr, "ceval-step=host-materialize base=%p capacity=%lu\n",
			s_tag_cache_base, s_tag_cache_size);
		header = (hcu_profile_tag_header *)s_tag_cache_base;
	}
	else
	{
		if (ps2_ctag_rebase_in_place(&view, (uint32_t)(uintptr_t)view.image,
			(uint8_t *)view.image, view.image_size) != PS2_CTAG_OK)
			return 5;
		fprintf(stderr, "ceval-step=rebase base=%p\n", (void *)view.image);
		header = (hcu_profile_tag_header *)(uintptr_t)view.image;
	}
	if (header->signature != 0x74616773u || header->tag_count <= 0 ||
		!points_into(s_tag_cache_base ? s_tag_cache_base : view.image, view.image_size, header->tag_instances,
			(size_t)header->tag_count * sizeof(*instances)))
		return 6;
	instances = (hcu_profile_tag_instance *)(uintptr_t)header->tag_instances;
	held_first = instances;
	held_name = instances[0].name;
	held_root = instances[0].base_address;
	if (!points_into(s_tag_cache_base ? s_tag_cache_base : view.image, view.image_size, held_name, 1) ||
		!points_into(s_tag_cache_base ? s_tag_cache_base : view.image, view.image_size, held_root, 1))
		return 7;
	fprintf(stderr, "ceval-step=header tags=%ld first-name=%p first-root=%p\n",
		(long)header->tag_count, held_name, held_root);
	if (argc == 6)
	{
		before_image = (uint8_t *)malloc(view.image_size);
		if (!before_image) return 15;
		memcpy(before_image, header, view.image_size);
	}
	valid = tag_validate_tags(header, (long)view.image_size, file_length, profile) ? 1 : 0;
	validation_corrections = tag_validate_corrections();
	if (argc == 6 && !write_validation_deltas(argv[5], before_image,
		(uint8_t *)header, view.image_size)) return 16;
	fprintf(stderr, "ceval-step=validated valid=%d\n", valid);
	if (instances != held_first || instances[0].name != held_name ||
		instances[0].base_address != held_root)
		return 8;
	saved_signature = header->signature;
	header->signature ^= 1u;
	corrupt_rejected = tag_validate_tags(header, (long)view.image_size,
		file_length, profile) ? 0 : 1;
	header->signature = saved_signature;
	if (mounted)
	{
		if (!cache_files_precache_map_loaded(profile)) return 9;
		ps2_cache_unmount_ctag();
		owner_unpublished = !cache_files_precache_map_loaded(profile);
		released_after_unmount = "1";
	}
	else
	{
		owner_unpublished = !cache_files_precache_map_loaded(profile);
		released_after_unmount = "not_applicable";
	}
	/* Drop validator-held tag-header state after the owner has unpublished the
	 * cache, before the caller frees the CTAG bytes holding those pointers. */
	tag_validate_release_claims_buffer();
	free(s_claims_buffer);
	pointers_stable = instances == held_first && instances[0].name == held_name &&
		instances[0].base_address == held_root &&
		points_into(s_tag_cache_base ? s_tag_cache_base : view.image, view.image_size, held_name, 1) &&
		points_into(s_tag_cache_base ? s_tag_cache_base : view.image, view.image_size, held_root, 1);
	/* The caller keeps the original CTAG allocation alive through unmount. Only
	 * after publication is cleared may its owner release these tag references. */
	printf("profile-ce-validation profile=%s ctag=ok image_size=%lu tags=%ld relocations=%lu mount=%d validator=%s corrupt_schema_rejected=%d pointers_stable=%d owner_unpublished=%d released_after_unmount=%s capacity=%lu corrections=%ld\n",
		profile, (unsigned long)view.image_size, (long)header->tag_count,
		(unsigned long)view.relocation_count, mounted,
		valid ? "accepted" : "rejected", corrupt_rejected,
		pointers_stable,
		owner_unpublished, released_after_unmount, s_tag_cache_size,
		validation_corrections);
	if (mounted && !owner_unpublished) return 10;
	if (!corrupt_rejected || !pointers_stable) return 11;
	free(payload);
	free(s_tag_cache_base);
	free(before_image);
	return 0;
}
