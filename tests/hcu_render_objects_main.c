/* Host tests for the C3.objects pure core: synthetic builder, selection, pin/unpin, parity. */
#include <math.h>
#include <stdio.h>
#include <string.h>
#include <stdint.h>

#include "stream/hcu_render_objects.h"

static int fail(const char *what, int line)
{
	printf("FAIL %s line %d\n", what, line);
	return 1;
}

#define CHECK(cond) do { if (!(cond)) return fail(#cond, __LINE__); } while (0)

static halo_ps2_snapshot_matrix4x3 mat_at(float x, float y, float z)
{
	halo_ps2_snapshot_matrix4x3 m;
	memset(&m, 0, sizeof m);
	m.scale = 1.0f;
	m.forward[0] = 1.0f;
	m.left[1] = 1.0f;
	m.up[2] = 1.0f;
	m.position[0] = x; m.position[1] = y; m.position[2] = z;
	return m;
}

static void models_table(hcu_render_objects_model *m)
{
	memset(m, 0, sizeof(hcu_render_objects_model) * 2u);
	m[0].resource_id = 100; m[0].loaded = 1; m[0].node_count = 3;
	m[1].resource_id = 200; m[1].loaded = 1; m[1].node_count = 2;
}

static const halo_ps2_snapshot_camera kcam = {
	.position = {0, 0, 0}, .forward = {1, 0, 0}, .up = {0, 0, 1},
	.vertical_field_of_view = 1.0f, .z_near = 0.1f, .z_far = 100.0f,
};

/* Two views; object 0 (skinned, 3 palette nodes) is shared, view 1 adds object 1 (static, resource 200). */
static int build_two_views(halo_ps2_frame_snapshot *s, halo_ps2_snapshot_matrix4x3 *pal)
{
	hcu_render_synthetic_object o;
	int i;
	for (i = 0; i < 3; i++) pal[i] = mat_at((float)i, 0.0f, 0.0f);
	CHECK(hcu_render_synthetic_begin(s, 7u, 42u, 2u) == 0);
	CHECK(hcu_render_synthetic_view(s, 0, &kcam) == 0);
	memset(&o, 0, sizeof o);
	o.resource_id = 100; o.definition_index = 5; o.type = HCU_OBJECTS_TYPE_BIPED;
	o.flags = HCU_OBJECTS_FLAG_SKINNED; o.palette_count = 3; o.world = mat_at(1, 2, 3); o.palette = pal;
	CHECK(hcu_render_synthetic_object_add(s, 0, 0, &o) == 0);
	CHECK(hcu_render_synthetic_view(s, 1, &kcam) == 0);
	CHECK(hcu_render_synthetic_object_add(s, 1, 0, &o) == 0);   /* shared: same index, same palette */
	memset(&o, 0, sizeof o);
	o.resource_id = 200; o.definition_index = 9; o.type = HCU_OBJECTS_TYPE_WEAPON; o.world = mat_at(4, 5, 6);
	CHECK(hcu_render_synthetic_object_add(s, 1, 1, &o) == 0);
	return 0;
}

static int test_builder(void)
{
	halo_ps2_frame_snapshot s;
	halo_ps2_snapshot_matrix4x3 pal[3];
	CHECK(build_two_views(&s, pal) == 0);
	CHECK(s.version == HALO_PS2_FRAME_SNAPSHOT_VERSION);
	CHECK(s.view_count == 2);
	CHECK(s.object_count == 2);            /* the shared object is interned once */
	CHECK(s.palette_count == 3);           /* one palette range for the shared object */
	CHECK(s.resource_count == 2);
	CHECK(s.view_ref_count == 3);          /* view 0: obj0; view 1: obj0, obj1 */
	CHECK(s.views[0].view_ref_first == 0 && s.views[0].view_ref_count == 1);
	CHECK(s.views[1].view_ref_first == 1 && s.views[1].view_ref_count == 2);
	/* Out-of-order views and index gaps are refused. */
	CHECK(hcu_render_synthetic_object_add(&s, 0, 0, &(hcu_render_synthetic_object){ .resource_id = 100 }) == HCU_RENDER_CONTENT_E_STATE);
	CHECK(hcu_render_synthetic_object_add(&s, 1, 5, &(hcu_render_synthetic_object){ .resource_id = 100 }) == HCU_RENDER_CONTENT_E_STATE);
	CHECK(hcu_render_synthetic_begin(&s, 1u, 0u, 5u) == HCU_RENDER_CONTENT_E_ARGUMENT);
	return 0;
}

static int test_select(void)
{
	halo_ps2_frame_snapshot s;
	halo_ps2_snapshot_matrix4x3 pal[3];
	hcu_render_objects_model models[HCU_OBJECTS_MAX_MODELS];
	hcu_render_object_draw draw[HCU_OBJECTS_MAX_DRAW];
	hcu_render_objects_counters c;
	uint32_t n = 0;
	CHECK(build_two_views(&s, pal) == 0);
	models_table(models);
	memset(&c, 0, sizeof c);
	CHECK(hcu_render_objects_select(&s, 0, models, 2, draw, HCU_OBJECTS_MAX_DRAW, &n, &c) == 0);
	CHECK(n == 1 && draw[0].resource_id == 100 && draw[0].slot == 0 && draw[0].definition_index == 5);
	CHECK(draw[0].palette_count == 3 && draw[0].type == HCU_OBJECTS_TYPE_BIPED);
	CHECK(hcu_render_objects_select(&s, 1, models, 2, draw, HCU_OBJECTS_MAX_DRAW, &n, &c) == 0);
	CHECK(n == 2 && draw[0].object_index == 0 && draw[1].object_index == 1 && draw[1].slot == 1);
	CHECK(draw[1].world.position[0] == 4.0f && draw[1].resource_id == 200);
	CHECK(c.views_seen == 2 && c.model_hits == 3 && c.failures == 0);
	/* Refusals: view out of range, unknown resource, palette range past the table, bad refs. */
	CHECK(hcu_render_objects_select(&s, 2, models, 2, draw, HCU_OBJECTS_MAX_DRAW, &n, &c) == HCU_RENDER_CONTENT_E_ARGUMENT);
	s.resources[1].id = 999;                                  /* object 1 now unknown */
	CHECK(hcu_render_objects_select(&s, 1, models, 2, draw, HCU_OBJECTS_MAX_DRAW, &n, &c) == 0);
	CHECK(n == 1 && c.model_misses == 1);
	s.objects[0].palette_count = 9;                           /* range runs past the snapshot palette */
	memset(&c, 0, sizeof c);
	CHECK(hcu_render_objects_select(&s, 0, models, 2, draw, HCU_OBJECTS_MAX_DRAW, &n, &c) == 0);
	CHECK(n == 0 && c.failures == 1);
	s.objects[0].palette_count = 3;
	s.view_refs[0] = 200;                                     /* reference past object_count */
	memset(&c, 0, sizeof c);
	CHECK(hcu_render_objects_select(&s, 0, models, 2, draw, HCU_OBJECTS_MAX_DRAW, &n, &c) == 0);
	CHECK(n == 0 && c.failures == 1);
	s.view_refs[0] = 0;
	s.objects[0].flags = HCU_OBJECTS_FLAG_SKINNED;
	s.objects[0].palette_count = 0;                           /* skinned without a palette */
	memset(&c, 0, sizeof c);
	CHECK(hcu_render_objects_select(&s, 0, models, 2, draw, HCU_OBJECTS_MAX_DRAW, &n, &c) == 0);
	CHECK(n == 0 && c.failures == 1);
	s.objects[0].palette_count = 3;
	s.objects[0].flags = HCU_OBJECTS_FLAG_SKINNED;
	/* Same object twice in one view counts as deduplicated, drawn once. */
	s.view_ref_count = 2; s.view_refs[1] = 0;
	s.views[0].view_ref_count = 2;
	memset(&c, 0, sizeof c);
	CHECK(hcu_render_objects_select(&s, 0, models, 2, draw, HCU_OBJECTS_MAX_DRAW, &n, &c) == 0);
	CHECK(n == 1 && c.deduped == 1);
	/* Capacity: refused with a failure, nothing written past capacity. */
	s.views[0].view_ref_count = 1; s.view_ref_count = 2; s.view_refs[1] = 1;
	s.views[1].view_ref_first = 0;
	memset(&c, 0, sizeof c);
	CHECK(hcu_render_objects_select(&s, 0, models, 2, draw, 0, &n, &c) == 0);
	CHECK(n == 0 && c.failures == 1);
	return 0;
}

/* Four views share one biped and one weapon. The bank keeps one object record and one palette range, every
 * view references both, and the unique identity set counts each source identity once across the views. */
static int test_four_view_dedup(void)
{
	halo_ps2_frame_snapshot s;
	halo_ps2_snapshot_matrix4x3 pal[3];
	hcu_render_objects_model models[HCU_OBJECTS_MAX_MODELS];
	hcu_render_object_draw draw[HCU_OBJECTS_MAX_DRAW];
	hcu_render_objects_counters c;
	hcu_render_drawn_identity_set ids;
	hcu_render_synthetic_object o;
	uint32_t n = 0, v;
	int i;
	for (i = 0; i < 3; i++) pal[i] = mat_at((float)i, 0.0f, 0.0f);
	CHECK(hcu_render_synthetic_begin(&s, 7u, 42u, 4u) == 0);
	for (v = 0; v < 4u; v++) {
		/* Views are appended in order; each view references the shared table. */
		CHECK(hcu_render_synthetic_view(&s, v, &kcam) == 0);
		memset(&o, 0, sizeof o);
		o.resource_id = 100; o.definition_index = 5; o.type = HCU_OBJECTS_TYPE_BIPED;
		o.flags = HCU_OBJECTS_FLAG_SKINNED; o.palette_count = 3; o.world = mat_at(1, 2, 3); o.palette = pal;
		CHECK(hcu_render_synthetic_object_add(&s, v, 0, &o) == 0);   /* first view creates, others dedupe */
		memset(&o, 0, sizeof o);
		o.resource_id = 200; o.definition_index = 9; o.type = HCU_OBJECTS_TYPE_WEAPON; o.world = mat_at(4, 5, 6);
		CHECK(hcu_render_synthetic_object_add(&s, v, 1, &o) == 0);
	}

	CHECK(s.view_count == 4 && s.object_count == 2);       /* one record per source identity */
	CHECK(s.palette_count == 3);                            /* the shared palette is stored once */
	CHECK(s.view_ref_count == 8);                           /* 4 views x 2 shared objects */
	for (v = 0; v < 4u; v++)
		CHECK(s.views[v].view_ref_count == 2 && s.views[v].view_ref_first == 2u * v);
	models_table(models);
	memset(&c, 0, sizeof c);
	memset(&ids, 0, sizeof ids);
	for (v = 0; v < 4u; v++) {
		CHECK(hcu_render_objects_select(&s, v, models, 2, draw, HCU_OBJECTS_MAX_DRAW, &n, &c) == 0);
		CHECK(n == 2 && draw[0].object_index == 0 && draw[1].object_index == 1);
		CHECK(draw[0].palette_first == 0 && draw[0].palette_count == 3);
		CHECK(hcu_render_objects_note_submission(&c, &ids, HCU_OBJECTS_TYPE_BIPED,
			draw[0].object_index, draw[0].generation) == 0);
		CHECK(hcu_render_objects_note_submission(&c, &ids, HCU_OBJECTS_TYPE_WEAPON,
			draw[1].object_index, draw[1].generation) == 0);
	}
	CHECK(c.views_seen == 4 && c.failures == 0 && c.deduped == 0);  /* deduped counts repeats inside one view only */
	CHECK(c.submitted_bipeds == 4u && c.submitted_weapons == 4u);   /* per-view submissions */
	CHECK(c.unique_bipeds == 1u && c.unique_weapons == 1u);         /* identities across the 4 views */
	CHECK(ids.count == 2u && ids.overflow == 0u);
	return 0;
}

static int test_submitted_category_counters(void)
{
	hcu_render_objects_counters c;
	hcu_render_drawn_identity_set ids;
	memset(&c, 0, sizeof c);
	memset(&ids, 0, sizeof ids);
	/* Calls model the post-obj_render_pass success site: repeat view submissions count, but the
	 * source identity remains unique across views/frames. Unknown types do not enter qualification. */
	CHECK(hcu_render_objects_note_submission(&c, &ids, HCU_OBJECTS_TYPE_BIPED, 4u, 2u) == 0);
	CHECK(hcu_render_objects_note_submission(&c, &ids, HCU_OBJECTS_TYPE_BIPED, 4u, 2u) == 0);
	CHECK(hcu_render_objects_note_submission(&c, &ids, HCU_OBJECTS_TYPE_VEHICLE, 5u, 1u) == 0);
	CHECK(hcu_render_objects_note_submission(&c, &ids, HCU_OBJECTS_TYPE_WEAPON, 6u, 3u) == 0);
	CHECK(c.submitted_bipeds == 2u && c.submitted_vehicles == 1u && c.submitted_weapons == 1u);
	CHECK(c.unique_bipeds == 1u && c.unique_vehicles == 1u && c.unique_weapons == 1u);
	CHECK(ids.count == 3u && ids.overflow == 0u);
	CHECK(hcu_render_objects_note_submission(&c, &ids, HCU_OBJECTS_TYPE_EFFECT, 7u, 1u) ==
		HCU_RENDER_CONTENT_E_ARGUMENT);
	CHECK(c.submitted_bipeds == 2u && c.submitted_vehicles == 1u && c.submitted_weapons == 1u);
	return 0;
}

static int test_first_person_select(void)
{
	halo_ps2_frame_snapshot s;
	halo_ps2_snapshot_matrix4x3 pal[3];
	hcu_render_objects_model models[HCU_OBJECTS_MAX_MODELS];
	hcu_render_first_person_draw draw[2];
	hcu_render_objects_counters c;
	uint32_t n;
	CHECK(build_two_views(&s, pal) == 0);
	models_table(models);
	/* CE selected model 200 as the gun and model 100 as the arms; these are
	 * distinct tag resources and use separate model-order pose ranges. */
	s.views[0].flags |= HALO_PS2_FRAME_VIEW_FIRST_PERSON;
	s.views[0].first_person_weapon_resource_slot = 1u;
	s.views[0].first_person_weapon_palette_first = 3u;
	s.views[0].first_person_weapon_palette_count = 2u;
	s.views[0].first_person_hands_resource_slot = 0u;
	s.views[0].first_person_hands_palette_first = 5u;
	s.views[0].first_person_hands_palette_count = 3u;
	s.palette_count = 8u;
	memset(&c, 0, sizeof c);
	CHECK(hcu_render_objects_select_first_person(&s, 0, models, 2, draw, &n, &c) == 0);
	CHECK(n == 2 && draw[0].kind == HCU_OBJECTS_FP_WEAPON &&
		draw[0].resource_id == 200u && draw[0].model_slot == 1u &&
		draw[0].palette_first == 3u && draw[0].palette_count == 2u);
	CHECK(draw[1].kind == HCU_OBJECTS_FP_HANDS && draw[1].resource_id == 100u &&
		draw[1].model_slot == 0u && draw[1].palette_first == 5u &&
		draw[1].palette_count == 3u);
	CHECK(c.first_person_model_hits == 2u && c.first_person_model_misses == 0u && c.failures == 0u);
	s.resources[1].generation++;
	memset(&c, 0, sizeof c);
	CHECK(hcu_render_objects_select_first_person(&s, 0, models, 2, draw, &n, &c) == 0);
	CHECK(n == 1 && draw[0].kind == HCU_OBJECTS_FP_HANDS &&
		c.first_person_stale_resources == 1u && c.failures == 1u);
	s.resources[1].generation--;

	/* A resource miss is explicit and cannot fall back to the world weapon. */
	s.resources[1].id = 999u;
	memset(&c, 0, sizeof c);
	CHECK(hcu_render_objects_select_first_person(&s, 0, models, 2, draw, &n, &c) == 0);
	CHECK(n == 1 && draw[0].kind == HCU_OBJECTS_FP_HANDS &&
		c.first_person_model_misses == 1u && c.first_person_model_hits == 1u &&
		c.failures == 1u);
	s.resources[1].id = 200u;
	s.views[0].first_person_weapon_palette_count = 1u;
	memset(&c, 0, sizeof c);
	CHECK(hcu_render_objects_select_first_person(&s, 0, models, 2, draw, &n, &c) == 0);
	CHECK(n == 1 && draw[0].kind == HCU_OBJECTS_FP_HANDS && c.failures == 1u);
	return 0;
}

static int test_parity(void)
{
	hcu_render_parity_record store[4];
	hcu_render_parity_log log;
	hcu_render_object_draw d[3];
	hcu_render_objects_counters c;
	memset(d, 0, sizeof d);
	memset(&c, 0, sizeof c);
	d[0].view = 0; d[0].definition_index = 5; d[0].resource_id = 100; d[0].type = HCU_OBJECTS_TYPE_BIPED;
	d[1].view = 0; d[1].definition_index = 9; d[1].resource_id = 200; d[1].type = HCU_OBJECTS_TYPE_WEAPON;
	d[2].view = 1; d[2].definition_index = 7; d[2].resource_id = 300; d[2].type = HCU_OBJECTS_TYPE_VEHICLE;
	CHECK(hcu_render_parity_log_init(&log, store, 4) == 0);
	CHECK(hcu_render_objects_parity(&log, 0, d, 3, &c) == 0);
	CHECK(log.count == 3 && c.parity_dropped == 0);
	CHECK(store[0].kind == HCU_RENDER_PARITY_OBJECT && store[0].surface_id == 5 && store[0].material_id == -1);
	CHECK(store[0].resource_id == 100 && store[1].kind == HCU_RENDER_PARITY_WEAPON);
	CHECK(store[2].kind == HCU_RENDER_PARITY_VEHICLE && store[2].view == 1 && store[2].resource_id == 300);
	CHECK(hcu_render_objects_parity(&log, 0, d, 3, &c) == 0);
	CHECK(log.count == 4 && log.dropped == 2 && c.parity_dropped == 2);
	return 0;
}

static int test_residency_policy(void)
{
	CHECK(hcu_render_objects_residency_priority(HCU_OBJECTS_TYPE_BIPED) == 0);
	CHECK(hcu_render_objects_residency_priority(HCU_OBJECTS_TYPE_WEAPON) == 0);
	CHECK(hcu_render_objects_residency_priority(HCU_OBJECTS_TYPE_VEHICLE) == 1);
	CHECK(hcu_render_objects_residency_priority(HCU_OBJECTS_TYPE_EFFECT) == 2);
	CHECK(hcu_render_objects_residency_priority(99) == 3);
	/* No resource can be evicted before its draw/upload chain fence is observed. */
	CHECK(!hcu_render_objects_residency_may_evict(1, 0, 0));
	CHECK(!hcu_render_objects_residency_may_evict(1, 0, -1));
	CHECK(!hcu_render_objects_residency_may_evict(1, 1, 1));
	CHECK(!hcu_render_objects_residency_may_evict(0, 0, 1));
	CHECK(hcu_render_objects_residency_may_evict(1, 0, 1));
	/* C3.3 pin check: a pinned entry that would otherwise be evictable is refused and counted. */
	{
		uint32_t refused = 0;
		CHECK(hcu_render_objects_residency_victim_ok(1, 0, 1, 0u, &refused) == 1 && refused == 0);
		CHECK(hcu_render_objects_residency_victim_ok(1, 0, 1, 1u, &refused) == 0 && refused == 1);
		CHECK(hcu_render_objects_residency_victim_ok(1, 0, 1, 2u, &refused) == 0 && refused == 2);
		/* Pins do not change the fence or reference rules, and do not count those refusals. */
		CHECK(hcu_render_objects_residency_victim_ok(1, 0, 0, 1u, &refused) == 0 && refused == 2);
		CHECK(hcu_render_objects_residency_victim_ok(1, 1, 1, 1u, &refused) == 0 && refused == 2);
		CHECK(hcu_render_objects_residency_victim_ok(0, 0, 1, 1u, &refused) == 0 && refused == 2);
	}
	/* C3.objects priority displacement: only a strictly less important (larger rank) loaded entry is a victim. */
	{
		uint32_t refused = 0;
		CHECK(HCU_OBJECTS_RANK_UNUSED > 3u);
		CHECK(hcu_render_objects_residency_rank_victim_ok(1, HCU_OBJECTS_RANK_UNUSED, 0u, 1, 0u, &refused) == 1);
		CHECK(hcu_render_objects_residency_rank_victim_ok(1, 2u, 1u, 1, 0u, &refused) == 1);   /* effect displaced by vehicle */
		CHECK(hcu_render_objects_residency_rank_victim_ok(1, 1u, 1u, 1, 0u, &refused) == 0);   /* equal rank keeps its entry */
		CHECK(hcu_render_objects_residency_rank_victim_ok(1, 0u, 1u, 1, 0u, &refused) == 0);   /* biped never displaced by vehicle */
		CHECK(refused == 0);
		CHECK(hcu_render_objects_residency_rank_victim_ok(1, 2u, 1u, 1, 1u, &refused) == 0 && refused == 1);  /* pinned */
		CHECK(hcu_render_objects_residency_rank_victim_ok(1, 2u, 1u, 0, 0u, &refused) == 0 && refused == 1);  /* fence */
		CHECK(hcu_render_objects_residency_rank_victim_ok(0, 2u, 1u, 1, 0u, &refused) == 0 && refused == 1);  /* not loaded */
	}
	/* An individually oversized model is a real pool refusal, not an eviction attempt. */
	CHECK(hcu_render_objects_pool_request_fits(1024, 2048));
	CHECK(!hcu_render_objects_pool_request_fits(2049, 2048));
	CHECK(!hcu_render_objects_pool_request_fits(0, 2048));
	return 0;
}

static int test_pin(void)
{
	static unsigned char storage[1u << 20] __attribute__((aligned(16)));
	halo_ps2_frame_snapshot s;
	halo_ps2_snapshot_matrix4x3 pal[3];
	hcu_render_objects_pin_t pin;
	hcu_render_objects_counters c;
	const halo_ps2_frame_snapshot *p;
	uint32_t seq;
	memset(&c, 0, sizeof c);
	CHECK(hcu_snapshot_bank_storage_required() <= sizeof storage);
	CHECK(hcu_snapshot_bank_bind(storage, hcu_snapshot_bank_storage_required()) == 0);
	CHECK(hcu_render_objects_pin(&pin, &c) == NULL);          /* nothing published yet */
	CHECK(c.pin_refusals == 1);
	CHECK(build_two_views(&s, pal) == 0);
	hcu_snapshot_bank_set_map_generation(s.map_generation);
	{
		halo_ps2_frame_snapshot *slot = hcu_snapshot_bank_begin_write();
		CHECK(slot != NULL);
		memcpy(slot, &s, sizeof s);
		CHECK(hcu_snapshot_bank_commit(slot) == 0);
	}
	p = hcu_render_objects_pin(&pin, &c);
	CHECK(p != NULL && c.pins == 1);
	seq = p->sequence;
	for (int k = 0; k < 2; k++) {
		halo_ps2_frame_snapshot *slot = hcu_snapshot_bank_begin_write();
		CHECK(slot != NULL);             /* the pinned slot is never handed out */
		CHECK(slot != (halo_ps2_frame_snapshot *)p);
		memcpy(slot, &s, sizeof s);
		slot->frame_index = 1000u + (uint32_t)k;
		CHECK(hcu_snapshot_bank_commit(slot) == 0);
	}
	CHECK(p->sequence == seq && p->frame_index == 42u);       /* pinned data unchanged */
	CHECK(hcu_snapshot_bank_unbind() != 0);                   /* refused while pinned */
	hcu_render_objects_unpin(&pin, &c);
	CHECK(c.unpins == 1);
	hcu_render_objects_unpin(&pin, &c);                       /* second unpin is a no-op */
	CHECK(c.unpins == 1);
	CHECK(hcu_snapshot_bank_unbind() == 0);
	return 0;
}

/* C3.6: pose hash, pose tracking, effect requests and the parity summary identity. */
static int test_c3_6(void)
{
	halo_ps2_frame_snapshot s;
	halo_ps2_snapshot_matrix4x3 pal[3];
	hcu_render_synthetic_object o;
	hcu_render_objects_counters c;
	hcu_render_effect_draw fx[4];
	hcu_render_pose_tracker tr;
	hcu_render_parity_record recs[3];
	hcu_render_parity_log log;
	hcu_render_parity_summary sum, sum2;
	uint32_t h0, h1, count = 0;
	int i;

	for (i = 0; i < 3; i++) pal[i] = mat_at((float)i, 1.0f, 0.0f);
	CHECK(hcu_render_synthetic_begin(&s, 7u, 3u, 1u) == 0);
	CHECK(hcu_render_synthetic_view(&s, 0, &kcam) == 0);
	memset(&o, 0, sizeof o);
	o.resource_id = 100; o.definition_index = 5; o.type = HCU_OBJECTS_TYPE_VEHICLE;
	o.flags = HCU_OBJECTS_FLAG_SKINNED; o.palette_count = 3; o.palette = pal; o.world = mat_at(0, 0, 0);
	CHECK(hcu_render_synthetic_object_add(&s, 0, 0, &o) == 0);

	/* pose hash: deterministic, sensitive to one matrix, zero for an empty palette */
	h0 = hcu_render_objects_pose_hash(pal, 3, 0, 3);
	CHECK(h0 != 0u && h0 == hcu_render_objects_pose_hash(pal, 3, 0, 3));
	CHECK(hcu_render_objects_pose_hash(pal, 3, 0, 0) == 0u);
	CHECK(hcu_render_objects_pose_hash(pal, 3, 2, 2) == 0u);   /* range past the palette: refused */
	pal[2].position[1] += 0.25f;
	h1 = hcu_render_objects_pose_hash(pal, 3, 0, 3);
	CHECK(h1 != h0);

	/* pose tracker: first sight is silent, a changed palette counts as a change, equal counts as static */
	memset(&tr, 0, sizeof tr);
	memset(&c, 0, sizeof c);
	CHECK(hcu_render_pose_track(&tr, 0, 1u, h0, &c) == 0);
	CHECK(hcu_render_pose_track(&tr, 0, 1u, h1, &c) == 1);
	CHECK(hcu_render_pose_track(&tr, 0, 1u, h1, &c) == 0);
	CHECK(c.pose_changes == 1 && c.pose_static == 1);
	CHECK(hcu_render_pose_track(&tr, 0, 2u, h0, &c) == 0);   /* new generation: not a change */
	CHECK(hcu_render_pose_track(&tr, HCU_OBJECTS_POSE_TRACK, 1u, h0, &c) == HCU_RENDER_CONTENT_E_ARGUMENT);
	CHECK(hcu_render_objects_track_poses(&s, &tr, &c) == 0);
	CHECK(c.pose_changes == 1);                              /* generation 1 object 0 now has h1 -> h0 change */

	/* effects (v4 fx table): owner in view 0 and visible to view 0 is selected; a request whose view_mask
	 * excludes view 0, an owner outside the view, or a NaN position is not */
	s.fx_request_count = 3;
	s.fx_requests[0].kind = HALO_PS2_FRAME_FX_PARTICLE_SYSTEM; s.fx_requests[0].owner_object = 0;
	s.fx_requests[0].view_mask = 0x1; s.fx_requests[0].permutation = 4; s.fx_requests[0].scale = 2.0f;
	s.fx_requests[0].position[0] = 1.0f; s.fx_requests[0].position[1] = 2.0f; s.fx_requests[0].position[2] = 3.0f;
	s.fx_requests[1].kind = HALO_PS2_FRAME_FX_DECAL; s.fx_requests[1].owner_object = 0;
	s.fx_requests[1].view_mask = 0x2; s.fx_requests[1].position[0] = 1.0f;
	s.fx_requests[2].kind = HALO_PS2_FRAME_FX_DECAL; s.fx_requests[2].owner_object = 0;
	s.fx_requests[2].view_mask = 0x1; s.fx_requests[2].position[0] = 0.0f / 0.0f;
	memset(&c, 0, sizeof c);
	CHECK(hcu_render_effects_select(&s, 0, fx, 4, &count, &c) == 0);
	CHECK(count == 1 && fx[0].kind == HALO_PS2_FRAME_FX_PARTICLE_SYSTEM && fx[0].permutation == 4);
	CHECK(fx[0].owner_object == 0 && fx[0].scale == 2.0f);
	CHECK(c.effects_selected == 1 && c.effects_refused == 1);
	CHECK(hcu_render_effects_select(&s, 0, fx, 0, &count, &c) == 0 && count == 0);
	CHECK(c.effects_refused == 3);   /* NaN again + no room: refusals are counted, never silent */

	/* parity summary: per-kind counts, known materials, and a hash that moves with the identity */
	memset(recs, 0, sizeof recs);
	recs[0].kind = HCU_RENDER_PARITY_OBJECT; recs[0].surface_id = 4; recs[0].material_id = 11; recs[0].resource_id = 100;
	recs[1].kind = HCU_RENDER_PARITY_WEAPON; recs[1].surface_id = 1; recs[1].material_id = -1; recs[1].resource_id = 200;
	recs[2].kind = HCU_RENDER_PARITY_OBJECT; recs[2].surface_id = 4; recs[2].material_id = 12; recs[2].resource_id = 100;
	CHECK(hcu_render_parity_log_init(&log, recs, 3) == HCU_RENDER_CONTENT_OK);
	log.count = 3;
	CHECK(hcu_render_parity_summarize(&log, &sum) == HCU_RENDER_CONTENT_OK);
	CHECK(sum.records == 3 && sum.per_kind[HCU_RENDER_PARITY_OBJECT] == 2 && sum.per_kind[HCU_RENDER_PARITY_WEAPON] == 1);
	CHECK(sum.materials_known == 2 && sum.dropped == 0);
	recs[2].material_id = 13;
	CHECK(hcu_render_parity_summarize(&log, &sum2) == HCU_RENDER_CONTENT_OK);
	CHECK(sum2.hash != sum.hash);
	recs[2].material_id = 12;
	CHECK(hcu_render_parity_summarize(&log, &sum2) == HCU_RENDER_CONTENT_OK);
	CHECK(sum2.hash == sum.hash);
	return 0;
}

static float dist3(const float a[3], const float b[3])
{
	float d[3] = { a[0] - b[0], a[1] - b[1], a[2] - b[2] };
	return sqrtf(d[0] * d[0] + d[1] * d[1] + d[2] * d[2]);
}

/* C3.6(c): quad generation (billboard and decal orientation, flat colours), the view-mask filter and the
 * per-view cap. The EE clip and packet path is checked by the EE syntax build, not here. */
static int test_fx_quads(void)
{
	halo_ps2_frame_snapshot s;
	hcu_render_synthetic_object o;
	hcu_render_effect_draw e;
	hcu_render_effect_draw out[HCU_FX_MAX_PER_VIEW];
	hcu_render_objects_counters c;
	hcu_render_fx_quad q;
	halo_ps2_snapshot_camera cam_bad;
	float right[3], up[3], centre[3] = { 5.0f, 1.0f, 2.0f };
	uint8_t rgba_a[4], rgba_b[4];
	uint32_t count = 0, k, i;

	/* camera basis from kcam (forward +x, up +z): right = -y, up = +z */
	CHECK(hcu_render_fx_camera_basis(&kcam, right, up) == 0);
	CHECK(fabsf(right[0]) < 1e-6f && fabsf(right[1] + 1.0f) < 1e-6f && fabsf(right[2]) < 1e-6f);
	CHECK(fabsf(up[0]) < 1e-6f && fabsf(up[1]) < 1e-6f && fabsf(up[2] - 1.0f) < 1e-6f);
	cam_bad = kcam;
	cam_bad.forward[0] = 0.0f; cam_bad.forward[2] = 1.0f;   /* forward parallel to up */
	CHECK(hcu_render_fx_camera_basis(&cam_bad, right, up) == HCU_RENDER_CONTENT_E_ARGUMENT);

	/* billboard: every corner lies in the plane through the centre perpendicular to the forward axis, and
	 * sits at scale * sqrt(2) from the centre; v[0] is (-right, -up) and v[2] is (+right, +up) */
	memset(&e, 0, sizeof e);
	e.kind = HALO_PS2_FRAME_FX_EFFECT; e.position[0] = 5.0f; e.position[1] = 1.0f; e.position[2] = 2.0f;
	e.scale = 0.5f;
	CHECK(hcu_render_fx_build_quad(&e, right, up, &q) == 0);
	for (k = 0; k < 4; k++) {
		CHECK(fabsf(q.v[k][0] - 5.0f) < 1e-5f);                       /* dot(forward, corner - centre) = 0 */
		CHECK(fabsf(dist3(q.v[k], centre) - 0.5f * sqrtf(2.0f)) < 1e-5f);
	}
	CHECK(fabsf(q.v[0][1] - 1.5f) < 1e-5f && fabsf(q.v[0][2] - 1.5f) < 1e-5f);   /* -right -up */
	CHECK(fabsf(q.v[2][1] - 0.5f) < 1e-5f && fabsf(q.v[2][2] - 2.5f) < 1e-5f);   /* +right +up */
	CHECK(q.kind == HALO_PS2_FRAME_FX_EFFECT);

	/* the billboard follows the camera: a camera rolled 90 degrees about its forward axis turns the corners */
	{
		float r2[3], u2[3];
		halo_ps2_snapshot_camera rolled = kcam;
		rolled.up[0] = 0.0f; rolled.up[1] = 1.0f; rolled.up[2] = 0.0f;   /* up = +y: right = +z */
		CHECK(hcu_render_fx_camera_basis(&rolled, r2, u2) == 0);
		CHECK(fabsf(r2[2] - 1.0f) < 1e-6f && fabsf(u2[1] - 1.0f) < 1e-6f);
		CHECK(hcu_render_fx_build_quad(&e, r2, u2, &q) == 0);
		CHECK(fabsf(q.v[2][2] - 2.5f) < 1e-5f && fabsf(q.v[2][1] - 1.0f - 0.5f) < 1e-5f);
	}

	/* decal: the normal is forward. A +z normal keeps every corner at the decal's height; a -z normal
	 * (almost-vertical, so the fallback tangent is used) does too; a +x normal keeps the corners at its x */
	memset(&e, 0, sizeof e);
	e.kind = HALO_PS2_FRAME_FX_DECAL; e.position[0] = 1.0f; e.position[1] = 2.0f; e.position[2] = 3.0f;
	e.scale = 1.0f; e.forward[2] = 1.0f;
	CHECK(hcu_render_fx_build_quad(&e, right, up, &q) == 0);
	for (k = 0; k < 4; k++) {
		CHECK(fabsf(q.v[k][2] - 3.0f) < 1e-5f);
		CHECK(fabsf(dist3(q.v[k], e.position) - sqrtf(2.0f)) < 1e-5f);
	}
	e.forward[2] = -2.0f;
	CHECK(hcu_render_fx_build_quad(&e, right, up, &q) == 0);
	for (k = 0; k < 4; k++) CHECK(fabsf(q.v[k][2] - 3.0f) < 1e-5f);
	e.forward[0] = 1.0f; e.forward[2] = 0.0f;
	CHECK(hcu_render_fx_build_quad(&e, right, up, &q) == 0);
	for (k = 0; k < 4; k++) CHECK(fabsf(q.v[k][0] - 1.0f) < 1e-5f);
	/* zero forward: a decal falls back to a billboard facing the camera (all corners at x = centre x) */
	e.forward[0] = 0.0f;
	CHECK(hcu_render_fx_build_quad(&e, right, up, &q) == 0);
	for (k = 0; k < 4; k++) CHECK(fabsf(q.v[k][0] - 1.0f) < 1e-5f);

	/* refusals: LIGHT has no quad; scale must be finite and positive */
	e.kind = HALO_PS2_FRAME_FX_LIGHT; e.scale = 1.0f;
	CHECK(hcu_render_fx_build_quad(&e, right, up, &q) == HCU_RENDER_CONTENT_E_ARGUMENT);
	e.kind = HALO_PS2_FRAME_FX_EFFECT; e.scale = 0.0f;
	CHECK(hcu_render_fx_build_quad(&e, right, up, &q) == HCU_RENDER_CONTENT_E_ARGUMENT);
	e.scale = 0.0f / 0.0f;
	CHECK(hcu_render_fx_build_quad(&e, right, up, &q) == HCU_RENDER_CONTENT_E_ARGUMENT);

	/* flat colour per kind: the four drawn kinds differ, LIGHT is refused */
	CHECK(hcu_render_fx_flat_colour(HALO_PS2_FRAME_FX_EFFECT, rgba_a) == 0);
	CHECK(hcu_render_fx_flat_colour(HALO_PS2_FRAME_FX_PARTICLE_SYSTEM, rgba_b) == 0);
	CHECK(memcmp(rgba_a, rgba_b, 4) != 0);
	CHECK(hcu_render_fx_flat_colour(HALO_PS2_FRAME_FX_CONTRAIL, rgba_a) == 0);
	CHECK(hcu_render_fx_flat_colour(HALO_PS2_FRAME_FX_DECAL, rgba_b) == 0);
	CHECK(memcmp(rgba_a, rgba_b, 4) != 0);
	CHECK(hcu_render_fx_flat_colour(HALO_PS2_FRAME_FX_LIGHT, rgba_a) == HCU_RENDER_CONTENT_E_ARGUMENT);

	/* view mask and cap: 64 requests owned by object 0 (in both views), even ones visible to view 0 only,
	 * odd ones to view 1 only */
	CHECK(hcu_render_synthetic_begin(&s, 11u, 0u, 2u) == 0);
	CHECK(hcu_render_synthetic_view(&s, 0, &kcam) == 0);
	memset(&o, 0, sizeof o);
	o.resource_id = 100; o.definition_index = 5; o.type = HCU_OBJECTS_TYPE_BIPED; o.world = mat_at(0, 0, 0);
	CHECK(hcu_render_synthetic_object_add(&s, 0, 0, &o) == 0);
	CHECK(hcu_render_synthetic_view(&s, 1, &kcam) == 0);
	CHECK(hcu_render_synthetic_object_add(&s, 1, 0, &o) == 0);
	s.fx_request_count = HALO_PS2_FRAME_MAX_FX_REQUESTS;
	for (i = 0; i < s.fx_request_count; i++) {
		s.fx_requests[i].kind = HALO_PS2_FRAME_FX_PARTICLE_SYSTEM;
		s.fx_requests[i].owner_object = 0;
		s.fx_requests[i].view_mask = (i & 1u) ? 0x2u : 0x1u;
		s.fx_requests[i].scale = 1.0f;
		s.fx_requests[i].position[0] = (float)i;
	}
	memset(&c, 0, sizeof c);
	CHECK(hcu_render_effects_select(&s, 0, out, HCU_FX_MAX_PER_VIEW, &count, &c) == 0);
	CHECK(count == 32 && c.effects_selected == 32 && c.effects_refused == 0);
	for (i = 0; i < count; i++) CHECK((out[i].position[0] - (float)(2 * i)) == 0.0f);   /* even ones only */
	CHECK(hcu_render_effects_select(&s, 1, out, HCU_FX_MAX_PER_VIEW, &count, &c) == 0);
	CHECK(count == 32 && out[0].position[0] == 1.0f);
	/* all visible to view 0: the fixed cap holds even when the caller offers more room */
	for (i = 0; i < s.fx_request_count; i++) s.fx_requests[i].view_mask = 0x1u;
	memset(&c, 0, sizeof c);
	CHECK(hcu_render_effects_select(&s, 0, out, 1000u, &count, &c) == 0);
	CHECK(count == HCU_FX_MAX_PER_VIEW && c.effects_selected == HCU_FX_MAX_PER_VIEW && c.effects_refused == 0);
	CHECK(hcu_render_effects_select(&s, 0, out, 10u, &count, &c) == 0);
	CHECK(count == 10 && c.effects_refused == HALO_PS2_FRAME_MAX_FX_REQUESTS - 10u);
	return 0;
}

/* C3.6(c): textured quad ST per corner, normalized, in the order of hcu_render_fx_quad.v. */
static int test_fx_corner_st(void)
{
	float st[2];
	hcu_render_fx_corner_st(0, st); CHECK(st[0] == 0.0f && st[1] == 1.0f);   /* (-,-) bottom-left */
	hcu_render_fx_corner_st(1, st); CHECK(st[0] == 1.0f && st[1] == 1.0f);   /* (+,-) bottom-right */
	hcu_render_fx_corner_st(2, st); CHECK(st[0] == 1.0f && st[1] == 0.0f);   /* (+,+) top-right */
	hcu_render_fx_corner_st(3, st); CHECK(st[0] == 0.0f && st[1] == 0.0f);   /* (-,+) top-left */
	hcu_render_fx_corner_st(6, st); CHECK(st[0] == 1.0f && st[1] == 0.0f);   /* corners wrap mod 4 */
	return 0;
}

/* C3.6 review fixes: world decals (owner NONE) are drawn by every view their mask names, owned effects still need a
 * view reference; the per-frame identity accumulator agrees with the summary hash over the same records. */
static int test_c3_6_unowned_fx_and_frame_identity(void)
{
	halo_ps2_frame_snapshot s;
	halo_ps2_snapshot_matrix4x3 pal[3];
	hcu_render_effect_draw out[HCU_FX_MAX_PER_VIEW];
	hcu_render_objects_counters c;
	hcu_render_parity_frame pf;
	hcu_render_parity_record store[4], rec;
	hcu_render_parity_log log;
	hcu_render_parity_summary sum;
	uint32_t count = 0, i;
	CHECK(build_two_views(&s, pal) == 0);
	s.fx_request_count = 3;
	s.fx_requests[0].kind = HALO_PS2_FRAME_FX_DECAL; s.fx_requests[0].owner_object = HALO_PS2_FRAME_NONE_U16;
	s.fx_requests[0].view_mask = 0x1; s.fx_requests[0].position[0] = 1.0f;
	s.fx_requests[1].kind = HALO_PS2_FRAME_FX_DECAL; s.fx_requests[1].owner_object = HALO_PS2_FRAME_NONE_U16;
	s.fx_requests[1].view_mask = 0x2; s.fx_requests[1].position[0] = 2.0f;
	s.fx_requests[2].kind = HALO_PS2_FRAME_FX_PARTICLE_SYSTEM; s.fx_requests[2].owner_object = 0;
	s.fx_requests[2].view_mask = 0x1; s.fx_requests[2].position[0] = 3.0f;
	memset(&c, 0, sizeof c);
	CHECK(hcu_render_effects_select(&s, 0, out, HCU_FX_MAX_PER_VIEW, &count, &c) == 0);
	CHECK(count == 2 && c.effects_selected == 2 && c.effects_refused == 0);   /* unowned decal + owned effect */
	CHECK(out[0].kind == HALO_PS2_FRAME_FX_DECAL && out[0].position[0] == 1.0f);
	CHECK(out[1].position[0] == 3.0f);
	CHECK(hcu_render_effects_select(&s, 1, out, HCU_FX_MAX_PER_VIEW, &count, &c) == 0);
	CHECK(count == 1 && out[0].position[0] == 2.0f);                           /* view 1 sees only its decal */

	/* per-frame accumulator: same words as the summary, so the hashes agree record for record */
	hcu_render_parity_frame_reset(&pf);
	CHECK(pf.records == 0 && pf.hash == 2166136261u);
	CHECK(hcu_render_parity_log_init(&log, store, 4) == 0);
	for (i = 0; i < 3; i++) {
		memset(&rec, 0, sizeof rec);
		rec.kind = i == 1 ? HCU_RENDER_PARITY_SKY : HCU_RENDER_PARITY_OBJECT;
		rec.surface_id = (int32_t)(5 + i); rec.material_id = -1; rec.resource_id = 100u + i;
		CHECK(hcu_render_parity_frame_add(&pf, &rec) == HCU_RENDER_CONTENT_OK);
		CHECK(hcu_render_parity_log_append(&log, &rec) == HCU_RENDER_CONTENT_OK);
	}
	CHECK(pf.records == 3 && pf.per_kind[HCU_RENDER_PARITY_OBJECT] == 2 && pf.per_kind[HCU_RENDER_PARITY_SKY] == 1);
	CHECK(hcu_render_parity_summarize(&log, &sum) == HCU_RENDER_CONTENT_OK);
	CHECK(sum.hash == pf.hash && sum.records == pf.records);
	memset(&rec, 0, sizeof rec);
	rec.kind = 0;
	CHECK(hcu_render_parity_frame_add(&pf, &rec) == HCU_RENDER_CONTENT_E_ARGUMENT);   /* invalid kind refused */
	CHECK(pf.records == 3);
	return 0;
}

int main(void)
{
	if (test_builder()) return 1;
	if (test_select()) return 2;
	if (test_submitted_category_counters()) return 9;
	if (test_four_view_dedup()) return 10;
	if (test_first_person_select()) return 3;
	if (test_parity()) return 4;
	if (test_residency_policy()) return 5;
	if (test_pin()) return 6;
	if (test_c3_6()) return 7;
	if (test_fx_quads()) return 8;
	if (test_fx_corner_st()) return 9;
	if (test_c3_6_unowned_fx_and_frame_identity()) return 11;
	printf("hcu_render_objects tests passed\n");
	return 0;
}
