#include "stream/hcu_snapshot_bank.h"

#include <assert.h>
#include <math.h>
#include <stdio.h>
#include <string.h>

static uint8_t s_storage[(2 * 1024) * 1024] __attribute__((aligned(16)));

static halo_ps2_frame_object_id oid(uint32_t index, uint32_t generation)
{
	halo_ps2_frame_object_id id;
	id.index = index;
	id.generation = generation;
	return id;
}

static void set_identity(halo_ps2_snapshot_matrix4x3 *m)
{
	memset(m, 0, sizeof *m);
	m->scale = 1.0f;
	m->forward[0] = 1.0f;
	m->left[1] = 1.0f;
	m->up[2] = 1.0f;
}

static void set_camera(halo_ps2_snapshot_camera *c)
{
	memset(c, 0, sizeof *c);
	c->forward[0] = 1.0f;
	c->up[2] = 1.0f;
	c->vertical_field_of_view = 1.0f;
	c->z_near = 0.1f;
	c->z_far = 100.0f;
}

/* Adds one object through the bank intern API and gives it a world matrix. */
static int add_object(halo_ps2_frame_snapshot *s, uint32_t index)
{
	int slot = -1;
	assert(hcu_snapshot_bank_intern_object(s, oid(index, 7u), &slot) == 0);
	set_identity(&s->objects[slot].world);
	s->objects[slot].world.position[0] = (float)index;
	return slot;
}

static void add_active_view(halo_ps2_frame_snapshot *s, unsigned view,
	unsigned ref_first, unsigned ref_count)
{
	halo_ps2_frame_view *v = &s->views[view];
	memset(v, 0, sizeof *v);
	v->flags = HALO_PS2_FRAME_VIEW_ACTIVE;
	v->player_index = (int8_t)view;
	set_camera(&v->camera);
	v->view_ref_first = (uint16_t)ref_first;
	v->view_ref_count = (uint16_t)ref_count;
	s->view_count = (uint16_t)(view + 1u);
}

/* Publishes a snapshot that every view shares with a fixed object table. */
static const halo_ps2_frame_snapshot *publish_shared(unsigned objects,
	unsigned views)
{
	halo_ps2_frame_snapshot *s = hcu_snapshot_bank_begin_write();
	unsigned i, v;
	assert(s);
	for (i = 0; i < objects; ++i) {
		add_object(s, i);
		s->view_refs[s->view_ref_count++] = (uint16_t)i;
	}
	for (v = 0; v < views; ++v)
		add_active_view(s, v, 0u, objects);
	assert(hcu_snapshot_bank_commit(s) == 0);
	return hcu_snapshot_bank_latest();
}

static void test_bind_and_version(void)
{
	halo_ps2_frame_snapshot *s;
	size_t need = hcu_snapshot_bank_storage_required();
	assert(hcu_snapshot_bank_bind(NULL, need) == -1);
	assert(hcu_snapshot_bank_bind(s_storage + 4, need) == -1);
	assert(hcu_snapshot_bank_bind(s_storage, need - 1u) == -1);
	assert(!hcu_snapshot_bank_is_bound());
	assert(hcu_snapshot_bank_begin_write() == NULL);
	assert(hcu_snapshot_bank_bind(s_storage, need) == 0);
	assert(hcu_snapshot_bank_is_bound());
	assert(hcu_snapshot_bank_bind(s_storage, need) == -1);
	assert(hcu_snapshot_bank_latest() == NULL);

	s = hcu_snapshot_bank_begin_write();
	assert(s);
	assert(s->version == HALO_PS2_FRAME_SNAPSHOT_VERSION);
	assert(s->version == 3u);
	/* Wrong version must not publish. */
	s->version = 1u;
	assert(hcu_snapshot_bank_commit(s) == -1);
	assert(hcu_snapshot_bank_latest() == NULL);
	/* The rejected commit released the write slot. */
	s = hcu_snapshot_bank_begin_write();
	assert(s && s->version == 3u);
	hcu_snapshot_bank_set_map_generation(41u);
	assert(hcu_snapshot_bank_commit(s) == 0);
	assert(hcu_snapshot_bank_latest()->map_generation == 41u);
	assert(hcu_snapshot_bank_latest()->sequence == 1u);
	printf("version: ok (publish after rejected v1 commit, sequence 1, map 41)\n");
}

static void test_publish_sequence_and_generation(void)
{
	halo_ps2_frame_snapshot const *a, *b;
	a = publish_shared(2u, 1u);
	assert(a->sequence == 2u);
	hcu_snapshot_bank_set_map_generation(42u);
	b = publish_shared(2u, 1u);
	assert(b->sequence == 3u);
	assert(b->map_generation == 42u);
	assert(a->map_generation == 41u);
	printf("sequence: ok (monotonic, map generation stamped per commit)\n");
}

static void test_dedupe(void)
{
	halo_ps2_frame_snapshot *s;
	int first = -1, again = -1, other = -1;
	hcu_snapshot_bank_stats stats;
	uint32_t hits_before;
	hcu_snapshot_bank_get_stats(&stats);
	hits_before = stats.object_dedupe_hits;

	/* Four views, one shared object: the table keeps one record. */
	s = hcu_snapshot_bank_begin_write();
	assert(s);
	assert(hcu_snapshot_bank_intern_object(s, oid(9u, 1u), &first) == 0);
	assert(hcu_snapshot_bank_intern_object(s, oid(9u, 1u), &again) == 0);
	assert(first == again);
	assert(hcu_snapshot_bank_intern_object(s, oid(9u, 2u), &other) == 0);
	assert(other != first);
	assert(s->object_count == 2u);
	hcu_snapshot_bank_get_stats(&stats);
	assert(stats.object_dedupe_hits == hits_before + 1u);
	hcu_snapshot_bank_abandon(s);

	/* A duplicate injected by hand is refused at commit. */
	s = hcu_snapshot_bank_begin_write();
	assert(s);
	add_object(s, 3u);
	s->objects[1].id = oid(3u, 7u);
	s->object_count = 2u;
	assert(hcu_snapshot_bank_commit(s) == -1);
	s = hcu_snapshot_bank_begin_write();
	assert(s != NULL);
	hcu_snapshot_bank_abandon(s);
	printf("dedupe: ok (intern returns existing index, duplicate commit refused)\n");
}

static void test_refusal_when_all_free_slots_are_pinned(void)
{
	hcu_snapshot_reader r1, r2;
	halo_ps2_frame_snapshot const *a, *b;
	halo_ps2_frame_snapshot *w;
	hcu_snapshot_bank_stats stats;
	uint32_t sequence_a;

	assert(hcu_snapshot_bank_unbind() == 0);
	assert(hcu_snapshot_bank_bind(s_storage,
		hcu_snapshot_bank_storage_required()) == 0);

	a = publish_shared(1u, 1u);
	sequence_a = a->sequence;
	assert(hcu_snapshot_bank_begin_read(&r1) == a);
	b = publish_shared(1u, 1u);
	assert(b != a);
	assert(hcu_snapshot_bank_begin_read(&r2) == b);
	/* Publish a third snapshot: the pinned slots are A (r1) and B (r2), so the
	 * only free slot is the third bank. This is still allowed. */
	w = hcu_snapshot_bank_begin_write();
	assert(w != NULL);
	assert(w != a && w != b);
	assert(hcu_snapshot_bank_commit(w) == 0);
	/* Slots are A(pinned), B(pinned), C(published): the writer has no free
	 * slot and must refuse without touching a pinned bank. */
	assert(hcu_snapshot_bank_begin_write() == NULL);
	hcu_snapshot_bank_get_stats(&stats);
	assert(stats.write_refusals >= 1u);
	/* Unbind must refuse while readers still hold the bank. */
	assert(hcu_snapshot_bank_unbind() == -1);
	/* A pinned snapshot is intact after the refused write. */
	assert(a->sequence == sequence_a);
	assert(a->views[0].camera.z_far == 100.0f);
	/* Releasing A allows exactly that slot to be overwritten. */
	hcu_snapshot_bank_end_read(&r1);
	w = hcu_snapshot_bank_begin_write();
	assert(w == (halo_ps2_frame_snapshot *)a);
	hcu_snapshot_bank_abandon(w);
	/* Releasing B and still-published C leaves no unpinned use of B. */
	hcu_snapshot_bank_end_read(&r2);
	assert(hcu_snapshot_bank_unbind() == 0);
	printf("refusal: write refused while all free banks pinned (refusals=%u)\n",
		stats.write_refusals);
}

static void test_four_view_capacity(void)
{
	halo_ps2_frame_snapshot const *s;
	unsigned v;
	halo_ps2_frame_snapshot *w;
	size_t need = hcu_snapshot_bank_storage_required();

	assert(hcu_snapshot_bank_unbind() == 0);
	assert(hcu_snapshot_bank_bind(s_storage, need) == 0);

	/* 256 shared objects, 4 views x 256 refs = 1024 refs, full palette. */
	w = hcu_snapshot_bank_begin_write();
	assert(w);
	for (v = 0; v < 256u; ++v) {
		add_object(w, v);
	}
	for (v = 0; v < 4u; ++v) {
		unsigned i;
		unsigned first = w->view_ref_count;
		for (i = 0; i < 256u; ++i)
			w->view_refs[w->view_ref_count++] = (uint16_t)i;
		add_active_view(w, v, first, 256u);
		w->views[v].palette_first = (uint16_t)(v * 160u);
		w->views[v].palette_count = 160u;
		w->views[v].first_person_weapon_palette_first = (uint16_t)(v * 160u + 128u);
		w->views[v].first_person_weapon_palette_count = 32u;
	}
	for (v = 0; v < HALO_PS2_FRAME_MAX_PALETTE; ++v)
		set_identity(&w->palette[v]);
	w->palette_count = HALO_PS2_FRAME_MAX_PALETTE;
	assert(hcu_snapshot_bank_commit(w) == 0);
	s = hcu_snapshot_bank_latest();
	assert(s->view_count == 4u && s->object_count == 256u);
	assert(s->view_ref_count == 1024u);
	assert(s->palette_count == HALO_PS2_FRAME_MAX_PALETTE);
	assert(hcu_snapshot_bank_unbind() == 0);
	printf("four views: ok (256 shared objects, 1024 refs, 640 palette matrices)\n");
}

static void test_bounds(void)
{
	halo_ps2_frame_snapshot *s;
	int slot = -1;
	uint32_t index;
	hcu_snapshot_bank_stats stats;

	assert(hcu_snapshot_bank_bind(s_storage,
		hcu_snapshot_bank_storage_required()) == 0);

	/* Five views is refused by the wire contract. */
	s = hcu_snapshot_bank_begin_write();
	s->view_count = 5u;
	assert(hcu_snapshot_bank_commit(s) == -1);

	/* Object overflow is refused at intern time and at commit. */
	s = hcu_snapshot_bank_begin_write();
	for (index = 0; index < HALO_PS2_FRAME_MAX_OBJECTS; ++index) {
		int out = -1;
		assert(hcu_snapshot_bank_intern_object(s, oid(index, 1u), &out) == 0);
	}
	assert(hcu_snapshot_bank_intern_object(s, oid(9999u, 1u), &slot) == -1);
	hcu_snapshot_bank_get_stats(&stats);
	assert(stats.object_overflows >= 1u);
	hcu_snapshot_bank_abandon(s);

	/* Out-of-range view ref. */
	s = hcu_snapshot_bank_begin_write();
	add_object(s, 1u);
	s->view_ref_count = 1u;
	s->view_refs[0] = 7u;
	add_active_view(s, 0u, 0u, 1u);
	assert(hcu_snapshot_bank_commit(s) == -1);

	/* Palette range outside the palette. */
	s = hcu_snapshot_bank_begin_write();
	add_object(s, 1u);
	s->palette_count = 2u;
	s->objects[0].palette_first = 1u;
	s->objects[0].palette_count = 2u;
	set_identity(&s->palette[0]);
	set_identity(&s->palette[1]);
	assert(hcu_snapshot_bank_commit(s) == -1);

	/* Non-finite camera with an active view. */
	s = hcu_snapshot_bank_begin_write();
	add_active_view(s, 0u, 0u, 0u);
	s->views[0].camera.z_near = NAN;
	assert(hcu_snapshot_bank_commit(s) == -1);

	/* Zero-scale object transform. */
	s = hcu_snapshot_bank_begin_write();
	add_object(s, 2u);
	s->objects[0].world.scale = 0.0f;
	assert(hcu_snapshot_bank_commit(s) == -1);

	/* Attachment, effect, decal and resource references are checked. */
	s = hcu_snapshot_bank_begin_write();
	add_object(s, 3u);
	s->attachment_count = 1u;
	s->attachments[0].parent_object = 0u;
	s->attachments[0].child_object = 9u;
	assert(hcu_snapshot_bank_commit(s) == -1);

	s = hcu_snapshot_bank_begin_write();
	add_object(s, 3u);
	s->effect_count = 1u;
	s->effects[0].owner_object = 5u;
	assert(hcu_snapshot_bank_commit(s) == -1);

	s = hcu_snapshot_bank_begin_write();
	add_object(s, 3u);
	s->decal_count = 1u;
	s->decals[0].owner_object = 0u;
	s->decals[0].resource_slot = HALO_PS2_FRAME_NONE_U16;
	s->decals[0].size = -1.0f;
	assert(hcu_snapshot_bank_commit(s) == -1);

	s = hcu_snapshot_bank_begin_write();
	add_object(s, 3u);
	s->objects[0].resource_slot = 4u;
	s->resource_count = 1u;
	assert(hcu_snapshot_bank_commit(s) == -1);

	/* A valid effect and decal referencing a valid object pass. */
	s = hcu_snapshot_bank_begin_write();
	add_object(s, 3u);
	s->effect_count = 1u;
	s->effects[0].owner_object = 0u;
	s->effects[0].priority = 1u;
	s->decal_count = 1u;
	s->decals[0].owner_object = 0u;
	s->decals[0].resource_slot = HALO_PS2_FRAME_NONE_U16;
	s->decals[0].size = 0.5f;
	s->decals[0].lifetime_sec = 2.0f;
	assert(hcu_snapshot_bank_commit(s) == 0);

	/* v3 first-person resources and model-order palettes accept exact bounded
	 * gun/arms ranges, then reject invalid ranges and resource slots. */
	s = hcu_snapshot_bank_begin_write();
	add_object(s, 3u);
	s->view_ref_count = 1u;
	s->view_refs[0] = 0u;
	add_active_view(s, 0u, 0u, 1u);
	s->resource_count = 2u;
	s->resources[0].id = 17u;
	s->resources[0].generation = s->map_generation;
	s->resources[1].id = 23u;
	s->resources[1].generation = s->map_generation;
	s->palette_count = 2u;
	set_identity(&s->palette[0]);
	set_identity(&s->palette[1]);
	s->views[0].first_person_weapon_resource_slot = 0u;
	s->views[0].first_person_hands_resource_slot = 1u;
	s->views[0].flags |= HALO_PS2_FRAME_VIEW_FIRST_PERSON;
	s->views[0].first_person_weapon_palette_first = 0u;
	s->views[0].first_person_weapon_palette_count = 1u;
	s->views[0].first_person_hands_palette_first = 1u;
	s->views[0].first_person_hands_palette_count = 1u;
	assert(hcu_snapshot_bank_commit(s) == 0);

	s = hcu_snapshot_bank_begin_write();
	add_object(s, 3u);
	s->resource_count = 1u;
	s->resources[0].id = 17u;
	s->resources[0].generation = s->map_generation ^ 1u;
	assert(hcu_snapshot_bank_commit(s) == -1);

	s = hcu_snapshot_bank_begin_write();
	add_object(s, 3u);
	s->view_ref_count = 1u;
	s->view_refs[0] = 0u;
	add_active_view(s, 0u, 0u, 1u);
	s->palette_count = 1u;
	set_identity(&s->palette[0]);
	s->views[0].first_person_weapon_palette_first = 1u;
	s->views[0].first_person_weapon_palette_count = 1u;
	assert(hcu_snapshot_bank_commit(s) == -1);

	s = hcu_snapshot_bank_begin_write();
	add_object(s, 3u);
	s->view_ref_count = 1u;
	s->view_refs[0] = 0u;
	add_active_view(s, 0u, 0u, 1u);
	s->views[0].flags |= HALO_PS2_FRAME_VIEW_FIRST_PERSON;
	s->views[0].first_person_weapon_resource_slot = 0u;
	assert(hcu_snapshot_bank_commit(s) == -1);

	/* Commit with no pending write, and a second begin while writing. */
	assert(hcu_snapshot_bank_commit(s) == -1);
	s = hcu_snapshot_bank_begin_write();
	assert(s);
	assert(hcu_snapshot_bank_begin_write() == NULL);
	hcu_snapshot_bank_abandon(s);

	assert(hcu_snapshot_bank_unbind() == 0);
	printf("bounds: ok (views, palettes, v3 first-person ranges/slots, refs, attachments, effects, decals, resources)\n");
}

static void test_fits_frame_scratch(void)
{
	size_t bank = hcu_snapshot_bank_storage_required();
	size_t frame_scratch = 393216u;
	/* Pinned C2 owner: the v1 double bank must not be bound alongside. */
	printf("bytes: v3 bank=%zu (3 slots, frame_scratch owner=%zu, share=%.1f%%)\n",
		bank, frame_scratch, 100.0 * (double)bank / (double)frame_scratch);
	assert(bank < frame_scratch);
}

int main(void)
{
	test_bind_and_version();
	test_publish_sequence_and_generation();
	test_dedupe();
	test_refusal_when_all_free_slots_are_pinned();
	test_four_view_capacity();
	test_bounds();
	test_fits_frame_scratch();
	printf("hcu_snapshot_bank tests passed\n");
	return 0;
}
