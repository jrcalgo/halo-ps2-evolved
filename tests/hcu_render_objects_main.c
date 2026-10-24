/* Host tests for the C3.objects pure core: synthetic builder, selection, pin/unpin, parity. */
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
	m[0].resource_id = 100; m[0].loaded = 1;
	m[1].resource_id = 200; m[1].loaded = 1;
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

int main(void)
{
	if (test_builder()) return 1;
	if (test_select()) return 2;
	if (test_parity()) return 3;
	if (test_pin()) return 4;
	printf("hcu_render_objects tests passed\n");
	return 0;
}
