/* C4 owner-exhaustion fixture for the legacy HP2 preflight in hcu_map_service.c.
 *
 * The production translation unit is compiled unmodified; HCU_C4_FAULT_SEAM is
 * defined on the command line, which enables the two owner-allocation seam sites:
 *   site 1: CTAG relocation vector allocation in feed_ctag_first_pass()
 *   site 2: source-hash scratch allocation in verify_source_hash()
 *
 * Usage: legacy-fixture <asset_root> <map_name> <site: 0 clean|1|2>
 *   site 0 prints the clean preflight state once.
 *   site 1|2 arms that one-shot failure, runs preflight (must fail with a safe
 *   empty state and intact guards), disarms, then retries and prints the state
 *   a clean retry must reproduce. */
#include "stream/hcu_map_service.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

#define MAP_BYTES (16u * 1024u * 1024u)
#define SCRATCH_BYTES (4u * 1024u * 1024u)
#define GUARD_BYTES 256u

/* One streaming region holds the map owner followed by the section scratch, as
 * map_service_init requires; GUARD_BYTES past the region must never be written. */
static uint8_t streaming_memory[MAP_BYTES + SCRATCH_BYTES + GUARD_BYTES] __attribute__((aligned(64)));

/* Host stand-ins for the EE memory and cache services the legacy preflight calls. */
static uint8_t tag_cache[16u * 1024u * 1024u] __attribute__((aligned(16)));
static uint8_t bsp_cache[4u * 1024u * 1024u] __attribute__((aligned(16)));
unsigned long physical_memory_get_tag_cache_size(void) { return sizeof tag_cache; }
void *physical_memory_get_tag_cache_base_address(void) { return tag_cache; }
unsigned long physical_memory_get_structure_bsp_cache_size(void) { return sizeof bsp_cache; }
void *physical_memory_get_structure_bsp_cache_base_address(void) { return bsp_cache; }
void SyncDCache(void *address, void *end) { (void)address; (void)end; }

/* CE's cseries helpers (macros over memset/memcpy/strlen in the headers) are
 * provided here with explicit loops so they cannot recurse into the macros. */
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
/* The fixture links file I/O with --wrap=read; forward to the real libc read. */
extern ssize_t __real_read(int fd, void *buf, size_t count);
ssize_t __wrap_read(int fd, void *buf, size_t count)
{
	return __real_read(fd, buf, count);
}

static int s_armed_site;
static int s_fired_site;

/* Test-only seam hook required by the HCU_C4_FAULT_SEAM hunks. */
int hcu_c4_fault_take_owner_failure(int site)
{
	if (s_armed_site == site) {
		s_armed_site = 0;
		s_fired_site = site;
		return 1;
	}
	return 0;
}

static int guards_intact(const hcu_map_service *service)
{
	unsigned i;
	for (i = 0; i < GUARD_BYTES; i++)
		if (streaming_memory[MAP_BYTES + SCRATCH_BYTES + i] != 0xC4) return 0;
	return service->map_arena->used <= service->map_arena->cap &&
		service->section_scratch->used <= service->section_scratch->cap;
}

static void print_state(const char *label, hcu_map_service *service, int rc)
{
	printf("%s rc=%d preflight_ready=%d staged_map=%s staged_entry=%d map_used=%u "
		"scratch_used=%u source_active=%d mount_active=%d descriptor=%d canaries=%s\n",
		label, rc, service->preflight_ready,
		service->staged_map[0] ? service->staged_map : "-",
		service->staged_entry != NULL,
		(unsigned)service->map_arena->used,
		(unsigned)service->section_scratch->used,
		service->source.active, service->mount.active,
		service->source.reader.descriptor,
		guards_intact(service) ? "ok" : "bad");
}

int main(int argc, char **argv)
{
	mem_layout_v2_t layout;
	arena_t map_owner, section_scratch, streaming;
	hcu_map_service service;
	int site, rc;

	if (argc != 4) return 2;
	setvbuf(stdout, NULL, _IONBF, 0);
	site = atoi(argv[3]);
	memset(streaming_memory, 0xC4, sizeof streaming_memory);
	memset(&layout, 0, sizeof layout);
	arena_init(&map_owner, "c4 legacy map owner", streaming_memory, MAP_BYTES);
	arena_init(&section_scratch, "c4 legacy section scratch",
		streaming_memory + MAP_BYTES, SCRATCH_BYTES);
	arena_init(&streaming, "c4 legacy streaming", streaming_memory, MAP_BYTES + SCRATCH_BYTES);
	layout.regions[MEM_LAYOUT_V2_STREAMING] = streaming;
	layout.regions[MEM_LAYOUT_V2_FRAME_SCRATCH] = section_scratch;
	if (hcu_map_service_init_with_arenas(&service, &layout, argv[1],
		&map_owner, &section_scratch) != 0) {
		printf("init-failed\n");
		return 3;
	}
	print_state("INITIAL", &service, -1);

	if (site == 0) {
		rc = hcu_map_service_preflight(argv[2]);
		print_state("CLEAN", &service, rc);
		return rc == 1 ? 0 : 4;
	}
	s_armed_site = site;
	rc = hcu_map_service_preflight(argv[2]);
	printf("FAULT site=%d fired=%d\n", site, s_fired_site);
	print_state("FAULTED", &service, rc);
	s_armed_site = 0;
	rc = hcu_map_service_preflight(argv[2]);
	print_state("RETRY", &service, rc);
	return rc == 1 ? 0 : 5;
}
