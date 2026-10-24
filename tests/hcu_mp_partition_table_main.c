/* Host check of the versioned profile-v2 partition table.
 * Every row must be 16-byte aligned, fill the 10 MiB map/render backing exactly
 * with its CE, BSP, guards and residency span, and be found by name. */
#include "stream/hcu_memory_profile.h"

#include <stdio.h>
#include <string.h>

/* This host binary links the table only, so the binder's CE and claims hooks are
 * stubbed. They are exercised by hcu_mp_production_bind_capacity_main.c. */
unsigned long tag_validate_claims_buffer_size(void) { return 0; }
int physical_memory_bindings_clean(void) { return 0; }
int physical_memory_bind_game_state(void *p, unsigned long n) { (void)p; (void)n; return 0; }
int physical_memory_bind_tag_cache(void *p, unsigned long n) { (void)p; (void)n; return 0; }
int physical_memory_bind_structure_bsp_cache(void *p, unsigned long n) { (void)p; (void)n; return 0; }
int physical_memory_bind_texture_cache(void *p, unsigned long n) { (void)p; (void)n; return 0; }
int physical_memory_bind_sound_cache(void *p, unsigned long n) { (void)p; (void)n; return 0; }
int physical_memory_bind_malloc_arena(void *p, unsigned long n) { (void)p; (void)n; return 0; }
int physical_memory_bind_tag_validation_scratch(void *p, unsigned long n) { (void)p; (void)n; return 0; }
void physical_memory_free(void) {}

#define MAP_RENDER_BACKING ((size_t)6291456u + (size_t)4194304u)
#define OUTER_GUARD ((size_t)16u)
/* Whole 64 KiB residency slots: 16 slots, the map service's minimum measured fit. */
#define RESIDENCY_BYTES ((size_t)16u * (size_t)65536u)
/* Renderer terms every row must leave room for: BSP_RENDER_WORKSPACE_BYTES and the 17 reserved texture pages. */
#define RENDER_WORKSPACE_MIN ((size_t)5632u + (size_t)139264u)

static int failures;

static void check(int condition, const char *what)
{
	if (!condition) {
		printf("FAIL %s\n", what);
		failures++;
	}
}

int main(void)
{
	unsigned i, count = hcu_memory_partition_count_v2();
	const hcu_memory_partition_entry_t *sidewinder;
	const hcu_memory_profile_t *selected;

	check(count == 27u, "table has 27 rows (26 session rows and ui)");
	for (i = 0; i < count; i++) {
		const hcu_memory_partition_entry_t *entry = hcu_memory_partition_entry_v2(i);
		const hcu_memory_profile_t *p;
		size_t map_parent;

		check(entry != NULL && entry->name != NULL, "row present");
		if (!entry || !entry->name) continue;
		p = &entry->profile;
		check(p->version == HCU_MEMORY_PROFILE_VERSION_1, "row version 1");
		check((p->tag_cache_bytes & 15u) == 0, "tag 16-byte aligned");
		check((p->structure_bsp_bytes & 15u) == 0, "bsp 16-byte aligned");
		check((p->render_texture_bytes & 15u) == 0, "render 16-byte aligned");
		map_parent = p->tag_cache_bytes + OUTER_GUARD + p->structure_bsp_bytes;
		check(p->residency_bytes == RESIDENCY_BYTES, "row carries 16 residency slots");
		check(p->residency_bytes % 65536u == 0, "residency is whole 64 KiB slots");
		check(map_parent + p->render_texture_bytes + OUTER_GUARD + p->residency_bytes ==
			MAP_RENDER_BACKING, "row fills the 10 MiB map/render backing");
		check(p->render_texture_bytes >= RENDER_WORKSPACE_MIN,
			"row leaves the renderer workspace and reserved pages");
		check(hcu_memory_partition_select_v2(entry->name) == p,
			"row found by its own name");
	}
	check(hcu_memory_partition_entry_v2(count) == NULL, "index past the end is NULL");
	check(hcu_memory_partition_select_v2("not-a-profile") == NULL, "unknown name is NULL");
	check(hcu_memory_partition_select_v2(NULL) == NULL, "NULL name is NULL");

	sidewinder = hcu_memory_partition_entry_v2(0);
	selected = hcu_memory_partition_select_v2("sidewinder_marine_shotgun_4p4bot");
	check(selected != NULL, "sidewinder marine shotgun row present");
	check(selected && selected->tag_cache_bytes == 6913936u, "sidewinder CE aligned");
	check(selected && selected->structure_bsp_bytes == 1993744u, "sidewinder BSP aligned");
	check(selected && selected->render_texture_bytes == 529472u, "sidewinder render residual");
	check(selected && selected->residency_bytes == RESIDENCY_BYTES, "sidewinder residency span");
	(void)sidewinder;
	selected = hcu_memory_partition_select_v2("ui");
	check(selected != NULL, "ui row present");
	check(selected && selected->tag_cache_bytes == 789152u, "ui CE aligned");
	check(selected && selected->structure_bsp_bytes == 2288u, "ui BSP aligned");
	check(selected && selected->render_texture_bytes == 8645712u, "ui render residual");

	printf("partition-table-v2 rows=%u failures=%d\n", count, failures);
	return failures ? 1 : 0;
}
