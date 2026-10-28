/* C3.3 host proof: a bank with a live reader is never overwritten, and its
 * pinned snapshot stays intact. Uses only the public bank API so it does not
 * depend on the fx/effect wire fields that another lane is changing. */
#include "stream/hcu_snapshot_bank.h"

#include <assert.h>
#include <stdio.h>
#include <string.h>

static uint8_t s_storage[HCU_SNAPSHOT_BANK_BYTES] __attribute__((aligned(16)));

/* C3.3 frame_scratch layout: 3 banks + 16-byte guard + 64-byte-aligned renderer workspace (5,632 B,
 * BSP_RENDER_WORKSPACE_BYTES in engine/src/render/storage.h) + guard, worst case with 63 bytes of
 * alignment padding, must fit the 393,216-byte frame_scratch owner (engine/src/core/mem.c). */
_Static_assert(sizeof(halo_ps2_frame_snapshot) == 90592u, "halo_ps2_frame_snapshot v11 size changed");
_Static_assert(HCU_SNAPSHOT_BANK_BYTES == 271776u, "three snapshot banks must be 271,776 B");
_Static_assert(HCU_SNAPSHOT_BANK_BYTES + 16u + 63u + 5632u + 16u <= HCU_C3_FRAME_SCRATCH_BYTES,
	"banks plus renderer workspace exceed frame_scratch");

static halo_ps2_frame_object_id oid(uint32_t index)
{
	halo_ps2_frame_object_id id;
	id.index = index;
	id.generation = 3u;
	return id;
}

/* Publishes one snapshot with `objects` shared objects and one active view. */
static void set_identity_world(halo_ps2_snapshot_matrix4x3 *m)
{
	memset(m, 0, sizeof *m);
	m->scale = 1.0f;
	m->forward[0] = 1.0f;
	m->left[1] = 1.0f;
	m->up[2] = 1.0f;
}

static void set_active_view(halo_ps2_frame_view *v, uint16_t first, uint16_t count)
{
	memset(v, 0, sizeof *v);
	v->flags = HALO_PS2_FRAME_VIEW_ACTIVE;
	v->camera.forward[0] = 1.0f;
	v->camera.up[2] = 1.0f;
	v->camera.vertical_field_of_view = 1.0f;
	v->camera.z_near = 0.1f;
	v->camera.z_far = 100.0f;
	v->view_ref_first = first;
	v->view_ref_count = count;
}

static const halo_ps2_frame_snapshot *publish(unsigned objects, uint32_t marker)
{
	halo_ps2_frame_snapshot *s = hcu_snapshot_bank_begin_write();
	unsigned i;
	int slot;
	assert(s);
	for (i = 0; i < objects; ++i) {
		assert(hcu_snapshot_bank_intern_object(s, oid(marker * 16u + i), &slot) == 0);
		memset(&s->objects[slot].world, 0, sizeof s->objects[slot].world);
		s->objects[slot].world.scale = 1.0f;
		s->objects[slot].world.forward[0] = 1.0f;
		s->objects[slot].world.left[1] = 1.0f;
		s->objects[slot].world.up[2] = 1.0f;
		s->view_refs[s->view_ref_count++] = (uint16_t)slot;
	}
	s->views[0].flags = HALO_PS2_FRAME_VIEW_ACTIVE;
	s->views[0].camera.forward[0] = 1.0f;
	s->views[0].camera.up[2] = 1.0f;
	s->views[0].camera.vertical_field_of_view = 1.0f;
	s->views[0].camera.z_near = 0.1f;
	s->views[0].camera.z_far = (float)marker;
	s->views[0].view_ref_first = 0u;
	s->views[0].view_ref_count = (uint16_t)objects;
	s->view_count = 1u;
	assert(hcu_snapshot_bank_commit(s) == 0);
	return hcu_snapshot_bank_latest();
}

/* Cross-view dedupe: two views reference one object. The second view's intern returns the first index,
 * counts one dedupe hit, and the object is stored once. Both views resolve through view_refs. */
static void test_cross_view_dedupe(void)
{
	halo_ps2_frame_snapshot *s = hcu_snapshot_bank_begin_write();
	hcu_snapshot_bank_stats before, after;
	int shared, shared_again, other;
	assert(s);
	hcu_snapshot_bank_get_stats(&before);
	assert(hcu_snapshot_bank_intern_object(s, oid(900u), &shared) == 0);
	assert(hcu_snapshot_bank_intern_object(s, oid(900u), &shared_again) == 0);
	assert(hcu_snapshot_bank_intern_object(s, oid(901u), &other) == 0);
	assert(shared == shared_again && other != shared);
	assert(s->object_count == 2u);
	hcu_snapshot_bank_get_stats(&after);
	assert(after.object_dedupe_hits - before.object_dedupe_hits == 1u);
	set_identity_world(&s->objects[shared].world);
	set_identity_world(&s->objects[other].world);
	/* view 0 references {shared, other}; view 1 references {shared} only. */
	s->view_refs[0] = (uint16_t)shared;
	s->view_refs[1] = (uint16_t)other;
	s->view_refs[2] = (uint16_t)shared_again;
	set_active_view(&s->views[0], 0u, 2u);
	set_active_view(&s->views[1], 2u, 1u);
	s->view_count = 2u;
	s->view_ref_count = 3u;
	assert(hcu_snapshot_bank_commit(s) == 0);
	assert(hcu_snapshot_bank_latest()->object_count == 2u);
	assert(hcu_snapshot_bank_latest()->view_refs[2] == shared);
	printf("cross-view-dedupe: ok (shared object interned once, dedupe-hits+%u, views 2, objects 2)\n",
		(unsigned)(after.object_dedupe_hits - before.object_dedupe_hits));
}

int main(void)
{
	hcu_snapshot_reader r1, r2;
	hcu_snapshot_bank_stats st;
	const halo_ps2_frame_snapshot *a, *b, *c;
	halo_ps2_frame_snapshot *w;
	uint32_t seq_a, refusals_before, refusals_after, eviction_refusals = 0u;
	unsigned trial;

	assert(hcu_snapshot_bank_bind(s_storage, sizeof s_storage) == 0);
	test_cross_view_dedupe();
	a = publish(2u, 11u);
	seq_a = a->sequence;
	assert(hcu_snapshot_bank_begin_read(&r1) == a);
	b = publish(2u, 12u);
	assert(hcu_snapshot_bank_begin_read(&r2) == b);
	c = publish(2u, 13u);
	assert(c != a && c != b);

	hcu_snapshot_bank_get_stats(&st);
	assert(st.read_pins_active == 2u);
	refusals_before = st.write_refusals;

	/* Writer wants a bank while A and B have live readers and C is published:
	 * every trial must be refused and must never hand back a pinned bank. */
	for (trial = 0; trial < 8u; ++trial) {
		w = hcu_snapshot_bank_begin_write();
		assert(w == NULL);
		/* Eviction attempt on a bank with readers: unbind is refused. */
		if (hcu_snapshot_bank_unbind() == -1)
			eviction_refusals++;
	}
	hcu_snapshot_bank_get_stats(&st);
	refusals_after = st.write_refusals;
	assert(refusals_after - refusals_before == 8u);
	assert(eviction_refusals == 8u);
	assert(st.read_pins_active == 2u);

	/* Pinned snapshots are byte-stable across the refused writes. */
	assert(a->sequence == seq_a && a->views[0].camera.z_far == 11.0f);
	assert(b->views[0].camera.z_far == 12.0f);
	assert(a->object_count == 2u && a->objects[0].id.index == 11u * 16u);

	/* Releasing A makes exactly A writable; B stays protected. */
	hcu_snapshot_bank_end_read(&r1);
	w = hcu_snapshot_bank_begin_write();
	assert(w == (halo_ps2_frame_snapshot *)a);
	hcu_snapshot_bank_abandon(w);
	w = hcu_snapshot_bank_begin_write();
	assert(w == (halo_ps2_frame_snapshot *)a);
	hcu_snapshot_bank_abandon(w);
	assert(b->views[0].camera.z_far == 12.0f);
	assert(hcu_snapshot_bank_unbind() == -1);

	hcu_snapshot_bank_end_read(&r2);
	hcu_snapshot_bank_get_stats(&st);
	assert(st.read_pins_active == 0u);
	assert(st.read_pins_taken >= 2u);
	assert(hcu_snapshot_bank_unbind() == 0);

	printf("pinned-writer: ok (refused-writes=%u eviction-refusals=%u reader-pins-taken=%u reader-pins-active=0)\n",
		(unsigned)(refusals_after - refusals_before), (unsigned)eviction_refusals,
		(unsigned)st.read_pins_taken);
	printf("pinned-bytes: ok (sequence, camera and object identity unchanged while pinned)\n");
	printf("hcu_scenes_bank tests passed\n");
	return 0;
}
