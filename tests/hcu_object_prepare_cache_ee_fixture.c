/* Compile the EE adapter into this host fixture so the real static cache builder and selector run. */
#define HCU_RENDER_OBJECTS_EE 1
#define HCU_C3_OBJECT_PREPARE_CACHE 1
#include <stdio.h>
#include "stream/hcu_render_objects.c"

#define CHECK(x) do { if (!(x)) { fprintf(stderr, "FAIL %s line %d\n", #x, __LINE__); return 1; } } while (0)

model_info model_get(const model_section *s, uint32_t index)
{
	model_info m;
	(void)s; (void)index;
	memset(&m, 0, sizeof(m));
	m.node_count = 1; m.region_count = 1; m.permutation_count = 1; m.radius = 1.0f;
	return m;
}

void model_select_permutations(const model_section *s, const model_info *m, const char *variant, uint16_t *out)
{
	uint32_t i;
	(void)s; (void)variant;
	for (i = 0; i < m->region_count; ++i) out[i] = 0u;
}

int main(void)
{
	static unsigned char memory[HCU_OBJECT_PREPARE_STORAGE_BYTES] __attribute__((aligned(16)));
	halo_ps2_frame_snapshot snap;
	hcu_render_object_draw draw[HCU_OBJECTS_MAX_DRAW];
	hcu_render_objects_counters counters;
	uint32_t count, hash;
	int slot;
	hcu_render_objects_model alternate[2];
	memset(&snap, 0, sizeof(snap));
	memset(&counters, 0, sizeof(counters));
	CHECK(hcu_render_objects_prepare_cache_bind(memory, sizeof(memory)) == HCU_RENDER_CONTENT_OK);
	s_slot_count = 1u;
	s_slots[0].loaded = 1;
	s_slot_epoch[0] = 5u;
	s_meta[0].loaded = 1;
	s_meta[0].resource_id = 77u;
	snap.version = HALO_PS2_FRAME_SNAPSHOT_VERSION;
	snap.sequence = 11u; snap.map_generation = 3u;
	snap.view_count = 1u; snap.object_count = 1u; snap.resource_count = 1u; snap.palette_count = 1u;
	snap.views[0].flags = HALO_PS2_FRAME_VIEW_ACTIVE;
	snap.views[0].view_ref_count = 1u;
	snap.view_ref_count = 1u; snap.view_refs[0] = 0u;
	snap.resources[0].id = 77u;
	snap.objects[0].id.index = 0u; snap.objects[0].id.generation = 101u;
	snap.objects[0].resource_slot = 0u; snap.objects[0].palette_count = 1u;
	snap.objects[0].flags = HCU_OBJECTS_FLAG_SKINNED;
	snap.objects[0].world.scale = 2.0f;
	snap.objects[0].world.forward[0] = 1.0f;
	snap.objects[0].world.left[1] = 1.0f;
	snap.objects[0].world.up[2] = 1.0f;
	snap.objects[0].world.position[0] = 6.0f;
	snap.palette[0] = snap.objects[0].world;
	prepare_snapshot(&snap);
	CHECK(s_prepared->ready && s_prepared->object[0].valid);
	CHECK(s_prepared->slot[0].valid && s_prepared->object[0].palette_count == 1u);
	CHECK(s_prepared->object[0].root.m[0][0] == 2.0f && s_prepared->object[0].root.m[3][0] == 6.0f);
	CHECK(s_prepared->palette[0].m[0][0] == 2.0f && s_prepared->palette[0].m[3][0] == 6.0f);
	CHECK(prepared_lookup(&snap, 0u, 101u, 77u, &slot, &hash) && slot == 0);
	CHECK(hash == hcu_render_objects_pose_hash(snap.palette, snap.palette_count, 0u, 1u));
	CHECK(hcu_render_objects_select(&snap, 0u, s_meta, 1u, draw, HCU_OBJECTS_MAX_DRAW, &count, &counters) == 0);
	CHECK(count == 1u && draw[0].slot == 0u && draw[0].pose_hash == hash);
	memset(alternate, 0, sizeof(alternate));
	alternate[1].loaded = 1; alternate[1].resource_id = 77u;
	CHECK(hcu_render_objects_select(&snap, 0u, alternate, 2u, draw, HCU_OBJECTS_MAX_DRAW, &count, &counters) == 0);
	CHECK(count == 1u && draw[0].slot == 1u); /* foreign model table bypasses prepared slot */
	snap.sequence++;
	snap.objects[0].world.position[0] = 9.0f;
	prepare_snapshot(&snap);
	CHECK(s_prepared->object[0].root.m[3][0] == 9.0f);
	snap.map_generation++;
	snap.objects[0].id.generation++;
	prepare_snapshot(&snap);
	CHECK(prepared_lookup(&snap, 0u, snap.objects[0].id.generation, 77u, &slot, &hash));
	slot = -1;
	CHECK(!prepared_lookup(&snap, 0u, snap.objects[0].id.generation + 1u, 77u, &slot, &hash));
	s_slot_epoch[0]++;
	CHECK(!prepared_lookup(&snap, 0u, snap.objects[0].id.generation, 77u, &slot, &hash));
	slot = (int)s_prepared->slot[0].epoch;
	prepared_invalidate_all();
	CHECK(!s_prepared->ready && !s_prepared->slot[0].valid && s_slot_epoch[0] != (uint32_t)slot);
	prepare_snapshot(&snap);
	CHECK(s_prepared->ready);
	snap.version++;
	prepare_snapshot(&snap);
	CHECK(!s_prepared->ready);
	snap.version = HALO_PS2_FRAME_SNAPSHOT_VERSION;
	prepare_snapshot(&snap);
	CHECK(s_prepared->ready);
	snap.resource_count = HALO_PS2_FRAME_MAX_RESOURCES + 1u;
	prepare_snapshot(&snap);
	CHECK(!s_prepared->ready);
	snap.resource_count = 1u;
	snap.palette_count = HALO_PS2_FRAME_MAX_PALETTE + 1u;
	prepare_snapshot(&snap);
	CHECK(!s_prepared->ready);
	puts("hcu object prepare EE cache fixture passed");
	return 0;
}
