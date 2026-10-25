#include "stream/hcu_snapshot_bank.h"

#include <math.h>
#include <stddef.h>
#include <string.h>

#define BANK_NONE (-1)

typedef struct bank_slot_state {
	uint32_t readers;
} bank_slot_state;

static halo_ps2_frame_snapshot *s_slots[HCU_SNAPSHOT_BANK_SLOTS];
static bank_slot_state s_state[HCU_SNAPSHOT_BANK_SLOTS];
static void *s_storage;
static size_t s_storage_bytes;
static int s_published = BANK_NONE;
static int s_writing = BANK_NONE;
static uint32_t s_map_generation;
static uint32_t s_next_sequence = 1u;
static hcu_snapshot_bank_stats s_stats;

static size_t align16_size(size_t value)
{
	return (value + 15u) & ~(size_t)15u;
}

size_t hcu_snapshot_bank_storage_required(void)
{
	return align16_size(sizeof(halo_ps2_frame_snapshot)) *
		HCU_SNAPSHOT_BANK_SLOTS;
}

int hcu_snapshot_bank_is_bound(void)
{
	return s_storage != NULL;
}

int hcu_snapshot_bank_bind(void *storage, size_t storage_bytes)
{
	size_t stride = align16_size(sizeof(halo_ps2_frame_snapshot));
	unsigned i;
	if (!storage || ((uintptr_t)storage & 15u) != 0u ||
		storage_bytes < hcu_snapshot_bank_storage_required())
		return -1;
	/* Binding over live readers or an existing bind would invalidate pins. */
	if (s_storage != NULL)
		return -1;
	s_storage = storage;
	s_storage_bytes = storage_bytes;
	for (i = 0; i < HCU_SNAPSHOT_BANK_SLOTS; ++i) {
		s_slots[i] = (halo_ps2_frame_snapshot *)
			((uint8_t *)storage + i * stride);
		s_state[i].readers = 0u;
		memset(s_slots[i], 0, sizeof *s_slots[i]);
	}
	s_published = BANK_NONE;
	s_writing = BANK_NONE;
	s_next_sequence = 1u;
	memset(&s_stats, 0, sizeof s_stats);
	return 0;
}

int hcu_snapshot_bank_unbind(void)
{
	unsigned i;
	if (!s_storage)
		return 0;
	/* Refuse while any reader or writer holds a bank: the caller must end
	 * readers and drain the renderer before the frame arena is rewound. */
	if (s_writing != BANK_NONE)
		return -1;
	for (i = 0; i < HCU_SNAPSHOT_BANK_SLOTS; ++i)
		if (s_state[i].readers != 0u)
			return -1;
	for (i = 0; i < HCU_SNAPSHOT_BANK_SLOTS; ++i)
		s_slots[i] = NULL;
	s_storage = NULL;
	s_storage_bytes = 0u;
	s_published = BANK_NONE;
	return 0;
}

void hcu_snapshot_bank_set_map_generation(uint32_t generation)
{
	/* A new map unpublishes the previous map's bank. Its bytes stay until a slot is reused, and readers that
	 * already pinned it keep their pins, but begin_read returns NULL until this map publishes its first bank. */
	if (generation != s_map_generation)
		s_published = BANK_NONE;
	s_map_generation = generation;
}

/* Header-only reset. The object, palette and effect tails are rewritten by
 * the producer, and commit validates every count it publishes. */
halo_ps2_frame_snapshot *hcu_snapshot_bank_begin_write(void)
{
	unsigned i;
	int slot = BANK_NONE;
	if (!s_storage || s_writing != BANK_NONE)
		return NULL;
	for (i = 0; i < HCU_SNAPSHOT_BANK_SLOTS; ++i) {
		if ((int)i == s_published || s_state[i].readers != 0u)
			continue;
		slot = (int)i;
		break;
	}
	if (slot == BANK_NONE) {
		s_stats.write_refusals++;
		return NULL;
	}
	s_writing = slot;
	memset(s_slots[slot], 0, offsetof(halo_ps2_frame_snapshot, views));
	s_slots[slot]->version = HALO_PS2_FRAME_SNAPSHOT_VERSION;
	s_slots[slot]->map_generation = s_map_generation;
	return s_slots[slot];
}

void hcu_snapshot_bank_abandon(halo_ps2_frame_snapshot *snapshot)
{
	if (s_writing != BANK_NONE && snapshot == s_slots[s_writing])
		s_writing = BANK_NONE;
}

int hcu_snapshot_bank_intern_object(halo_ps2_frame_snapshot *snapshot,
	halo_ps2_frame_object_id id, int *out_index)
{
	unsigned i;
	if (!snapshot || s_writing == BANK_NONE || snapshot != s_slots[s_writing] ||
		!out_index)
		return -1;
	for (i = 0; i < snapshot->object_count; ++i) {
		const halo_ps2_frame_object_id *known = &snapshot->objects[i].id;
		if (known->index == id.index && known->generation == id.generation) {
			s_stats.object_dedupe_hits++;
			*out_index = (int)i;
			return 0;
		}
	}
	if (snapshot->object_count >= HALO_PS2_FRAME_MAX_OBJECTS) {
		s_stats.object_overflows++;
		return -1;
	}
	i = snapshot->object_count++;
	memset(&snapshot->objects[i], 0, sizeof snapshot->objects[i]);
	snapshot->objects[i].id = id;
	snapshot->objects[i].resource_slot = HALO_PS2_FRAME_NONE_U16;
	*out_index = (int)i;
	return 0;
}

static int finite3(const float *v)
{
	return isfinite(v[0]) && isfinite(v[1]) && isfinite(v[2]);
}

static int finite_matrix(const halo_ps2_snapshot_matrix4x3 *m)
{
	if (!isfinite(m->scale) || m->scale == 0.0f)
		return 0;
	return finite3(m->forward) && finite3(m->left) && finite3(m->up) &&
		finite3(m->position);
}

static int range_ok(unsigned first, unsigned count, unsigned limit)
{
	return first <= limit && count <= limit - first;
}

static int resource_slot_ok(uint16_t slot, unsigned resource_count)
{
	return slot == HALO_PS2_FRAME_NONE_U16 || slot < resource_count;
}

static int validate_camera(const halo_ps2_snapshot_camera *camera)
{
	if (!finite3(camera->position) || !finite3(camera->forward) ||
		!finite3(camera->up) || !isfinite(camera->vertical_field_of_view) ||
		!isfinite(camera->z_near) || !isfinite(camera->z_far))
		return 0;
	if (camera->vertical_field_of_view <= 0.0f ||
		camera->vertical_field_of_view >= 3.1415927f)
		return 0;
	return camera->z_near > 0.0f && camera->z_far > camera->z_near;
}

static int validate_snapshot(const halo_ps2_frame_snapshot *s)
{
	unsigned i;
	if (s->version != HALO_PS2_FRAME_SNAPSHOT_VERSION)
		return 0;
	if (s->view_count > HALO_PS2_FRAME_MAX_VIEWS ||
		s->object_count > HALO_PS2_FRAME_MAX_OBJECTS ||
		s->view_ref_count > HALO_PS2_FRAME_MAX_VIEW_REFS ||
		s->palette_count > HALO_PS2_FRAME_MAX_PALETTE ||
		s->resource_count > HALO_PS2_FRAME_MAX_RESOURCES ||
		s->attachment_count > HALO_PS2_FRAME_MAX_ATTACHMENTS ||
		s->fx_request_count > HALO_PS2_FRAME_MAX_FX_REQUESTS ||
		s->effect_count + s->decal_count != s->fx_request_count)
		return 0;
	if (!isfinite(s->time_delta_since_tick_sec) ||
		s->time_delta_since_tick_sec < 0.0f)
		return 0;
	for (i = 0; i < s->resource_count; ++i)
		if (s->resources[i].generation != s->map_generation)
			return 0;
	for (i = 0; i < s->view_count; ++i) {
		const halo_ps2_frame_view *v = &s->views[i];
		if (!(v->flags & HALO_PS2_FRAME_VIEW_ACTIVE))
			continue;
		if (!validate_camera(&v->camera) ||
			!range_ok(v->palette_first, v->palette_count, s->palette_count) ||
			!range_ok(v->view_ref_first, v->view_ref_count, s->view_ref_count) ||
			!range_ok(v->first_person_weapon_palette_first,
				v->first_person_weapon_palette_count, s->palette_count) ||
			!range_ok(v->first_person_hands_palette_first,
				v->first_person_hands_palette_count, s->palette_count))
			return 0;
		if ((v->flags & HALO_PS2_FRAME_VIEW_FIRST_PERSON) &&
			((v->first_person_weapon_resource_slot == HALO_PS2_FRAME_NONE_U16 &&
			  v->first_person_hands_resource_slot == HALO_PS2_FRAME_NONE_U16) ||
			 !resource_slot_ok(v->first_person_weapon_resource_slot,
				s->resource_count) ||
			 !resource_slot_ok(v->first_person_hands_resource_slot,
				s->resource_count)))
			return 0;
	}
	for (i = 0; i < s->view_ref_count; ++i)
		if (s->view_refs[i] >= s->object_count)
			return 0;
	for (i = 0; i < s->palette_count; ++i)
		if (!finite_matrix(&s->palette[i]))
			return 0;
	for (i = 0; i < s->object_count; ++i) {
		const halo_ps2_frame_object *o = &s->objects[i];
		unsigned j;
		/* One object appears once; views share it through view_refs. */
		for (j = 0; j < i; ++j)
			if (s->objects[j].id.index == o->id.index &&
				s->objects[j].id.generation == o->id.generation)
				return 0;
		if (!range_ok(o->palette_first, o->palette_count, s->palette_count) ||
			!range_ok(o->attachment_first, o->attachment_count,
				s->attachment_count) ||
			!finite_matrix(&o->world))
			return 0;
		if (o->resource_slot != HALO_PS2_FRAME_NONE_U16 &&
			o->resource_slot >= s->resource_count)
			return 0;
	}
	for (i = 0; i < s->attachment_count; ++i) {
		const halo_ps2_frame_attachment *a = &s->attachments[i];
		if (a->parent_object >= s->object_count ||
			a->child_object >= s->object_count)
			return 0;
	}
	for (i = 0; i < s->fx_request_count; ++i) {
		const halo_ps2_frame_fx_request *r = &s->fx_requests[i];
		unsigned kind_ok = r->kind == HALO_PS2_FRAME_FX_EFFECT ||
			r->kind == HALO_PS2_FRAME_FX_PARTICLE_SYSTEM ||
			r->kind == HALO_PS2_FRAME_FX_CONTRAIL ||
			r->kind == HALO_PS2_FRAME_FX_LIGHT ||
			r->kind == HALO_PS2_FRAME_FX_DECAL;
		if (!kind_ok)
			return 0;
		if (r->owner_object != HALO_PS2_FRAME_NONE_U16 &&
			r->owner_object >= s->object_count)
			return 0;
		if ((r->view_mask >> HALO_PS2_FRAME_MAX_VIEWS) != 0u)
			return 0;
		if (!finite3(r->position) || !finite3(r->forward) ||
			!isfinite(r->scale) || r->scale < 0.0f ||
			!isfinite(r->age_sec) || r->age_sec < 0.0f)
			return 0;
	}
	return 1;
}

int hcu_snapshot_bank_commit(halo_ps2_frame_snapshot *snapshot)
{
	if (snapshot && s_writing != BANK_NONE && snapshot == s_slots[s_writing])
		snapshot->map_generation = s_map_generation;
	/* Publication never replaces a bank that still has readers. begin_write
	 * already excludes such slots; this is the same refusal at publish time. */
	if (!snapshot || s_writing == BANK_NONE || snapshot != s_slots[s_writing] ||
		s_state[s_writing].readers != 0u || !validate_snapshot(snapshot)) {
		s_stats.commit_rejects++;
		if (s_writing != BANK_NONE && snapshot == s_slots[s_writing])
			s_writing = BANK_NONE;
		return -1;
	}
	snapshot->sequence = s_next_sequence++;
	if (s_next_sequence == 0u)
		s_next_sequence = 1u;
	/* The previous publication is not freed here. It stays unavailable for
	 * writing only while readers hold it, which begin_write checks. */
	s_published = s_writing;
	s_writing = BANK_NONE;
	s_stats.commits++;
	return 0;
}

const halo_ps2_frame_snapshot *hcu_snapshot_bank_begin_read(
	hcu_snapshot_reader *reader)
{
	if (!reader)
		return NULL;
	/* A reader that still holds a pin keeps it. Re-begin would overwrite the
	 * slot record and leak the pin count, so the slot could never be reused. */
	if (reader->snapshot != NULL)
		return NULL;
	reader->slot = BANK_NONE;
	reader->snapshot = NULL;
	if (s_published == BANK_NONE)
		return NULL;
	s_state[s_published].readers++;
	s_stats.read_pins_active++;
	s_stats.read_pins_taken++;
	reader->slot = s_published;
	reader->snapshot = s_slots[s_published];
	return reader->snapshot;
}

void hcu_snapshot_bank_end_read(hcu_snapshot_reader *reader)
{
	if (!reader || reader->slot == BANK_NONE)
		return;
	if (s_state[reader->slot].readers > 0u) {
		s_state[reader->slot].readers--;
		s_stats.read_pins_active--;
	}
	reader->slot = BANK_NONE;
	reader->snapshot = NULL;
}

const halo_ps2_frame_snapshot *hcu_snapshot_bank_latest(void)
{
	return s_published == BANK_NONE ? NULL : s_slots[s_published];
}

int hcu_snapshot_bank_published_slot(void)
{
	return s_published;
}

void hcu_snapshot_bank_get_stats(hcu_snapshot_bank_stats *out)
{
	if (out)
		*out = s_stats;
}

/* CE weak hooks. The publisher calls begin, fills, then commits or abandons. */
halo_ps2_frame_snapshot *halo_ps2_frame_snapshot_begin(void)
{
	return hcu_snapshot_bank_begin_write();
}

int halo_ps2_frame_snapshot_intern_object(halo_ps2_frame_snapshot *snapshot,
	halo_ps2_frame_object_id id, int *out_index)
{
	return hcu_snapshot_bank_intern_object(snapshot, id, out_index);
}

int halo_ps2_frame_snapshot_commit(halo_ps2_frame_snapshot *snapshot)
{
	return hcu_snapshot_bank_commit(snapshot);
}
