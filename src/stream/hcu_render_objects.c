#include "stream/hcu_render_objects.h"
#include "stream/hcu_render_views.h"
#include "stream/hcu_render_frame.h"

#include <math.h>
#include <string.h>
#if defined(HALO_PS2_C3_MOVEMENT_TRACE)
#include <stdio.h>
#endif
#if defined(HALO_PS2_C3_LAG_TRACE) && HALO_PS2_C3_LAG_TRACE
#include <stdio.h>
static uint32_t s_lag_trace_events;
#define HCU_C3_LAG_TRACE_EVENT_CAP 64u
#endif
#if (defined(HALO_PS2_C3_LAG_TRACE) && HALO_PS2_C3_LAG_TRACE) || \
	(defined(HALO_PS2_C3_PERF_PROBE) && HALO_PS2_C3_PERF_PROBE)
#include "platform/timer.h"
#endif

static hcu_render_objects_frustum s_view_frustums[HALO_PS2_FRAME_MAX_VIEWS];
static const halo_ps2_frame_snapshot *s_frustum_snapshot;
static uint32_t s_frustum_sequence, s_frustum_generation;

#ifndef HCU_C3_OBJECT_PREPARE_CACHE
#define HCU_C3_OBJECT_PREPARE_CACHE 0
#endif

#ifndef HCU_C3_OBJECT_FASTPATH
#define HCU_C3_OBJECT_FASTPATH 0
#endif
#ifndef HCU_C3_OBJECT_VIEW_CACHE
#define HCU_C3_OBJECT_VIEW_CACHE 0
#endif
#ifdef HCU_RENDER_OBJECTS_EE
static hcu_render_objects_model s_meta[HCU_OBJECTS_MAX_MODELS];
static int prepared_lookup(const halo_ps2_frame_snapshot *, uint32_t, uint32_t, uint32_t, int *, uint32_t *);
#endif

/* ---- selection ---------------------------------------------------------------------------------- */

int hcu_render_objects_find_model(const hcu_render_objects_model *models, uint32_t model_count,
	uint32_t resource_id)
{
	uint32_t i;
	if (!models) return -1;
	for (i = 0; i < model_count && i < HCU_OBJECTS_MAX_MODELS; i++)
		if (models[i].loaded && models[i].resource_id == resource_id) return (int)i;
	return -1;
}

/* CE's render_object_list() skips the local first-person biped and, on that
 * branch, does not descend into its child object list. The parent snapshot is
 * flat, so apply the same per-view rule to attached descendants before model
 * selection. Follow only bounded snapshot links so malformed/cyclic input
 * cannot loop. */
static int hcu_render_object_descends_from(const halo_ps2_frame_snapshot *snap,
	uint32_t object_index, uint32_t ancestor_index)
{
	uint32_t depth;
	for (depth = 0; depth < snap->object_count && object_index < snap->object_count; ++depth) {
		const halo_ps2_frame_object *object = &snap->objects[object_index];
		uint32_t first = object->attachment_first;
		uint32_t count = object->attachment_count;
		uint32_t i, parent_index;
		int found = 0;
		if (first > snap->attachment_count || count > snap->attachment_count - first)
			return 0;
		for (i = first; i < first + count; ++i) {
			const halo_ps2_frame_attachment *attachment = &snap->attachments[i];
			if (attachment->kind != HALO_PS2_FRAME_ATTACHMENT_PARENT_LINK ||
				attachment->child_object != object_index)
				continue;
			if (attachment->parent_object >= snap->object_count)
				return 0;
			parent_index = attachment->parent_object;
			found = 1;
			break;
		}
		if (!found)
			return 0;
		if (parent_index == ancestor_index)
			return 1;
		object_index = parent_index;
	}
	return 0;
}

/* A weapon is loose only when the published parent-link inventory confirms it
 * has no parent. Other attachment kinds do not imply object parenting. */
static int hcu_render_object_is_loose_weapon(const halo_ps2_frame_snapshot *snap, uint32_t index)
{
	const halo_ps2_frame_object *o;
	uint32_t i, first, count;
	if (!snap || index >= snap->object_count) return 0;
	o = &snap->objects[index];
	if (o->type != HCU_OBJECTS_TYPE_WEAPON) return 0;
	first = o->attachment_first; count = o->attachment_count;
	if (first > snap->attachment_count || count > snap->attachment_count - first) return 0;
	for (i = first; i < first + count; ++i) {
		const halo_ps2_frame_attachment *a = &snap->attachments[i];
		if (a->kind == HALO_PS2_FRAME_ATTACHMENT_PARENT_LINK && a->child_object == index)
			return 0;
	}
	return 1;
}

static void hcu_render_frustum_set_plane(hcu_render_objects_frustum *frustum, unsigned index,
	const float normal[3], const float position[3], float distance)
{
	frustum->plane[index][0] = normal[0];
	frustum->plane[index][1] = normal[1];
	frustum->plane[index][2] = normal[2];
	frustum->plane[index][3] = -(normal[0] * position[0] + normal[1] * position[1] +
		normal[2] * position[2] + distance);
}

int hcu_render_objects_frustum_build_aspect(const halo_ps2_frame_view *view,
	float aspect, hcu_render_objects_frustum *out)
{
	const halo_ps2_snapshot_camera *camera;
	hcu_view_camera converted;
	float forward[3], right[3], up[3], plane[3], x0, y0, x1, y1;
	float sin_v, cos_v, sin_h, cos_h, sin_yaw, cos_yaw, sin_pitch, cos_pitch;
	float half_v, half_h;
	unsigned i;
	if (!out) return 0;
	memset(out, 0, sizeof *out);
	if (!view) return 0;
	camera = &view->camera;
	if (aspect <= 0.0f) {
		x0 = (float)camera->viewport_bounds[0]; y0 = (float)camera->viewport_bounds[1];
		x1 = (float)camera->viewport_bounds[2]; y1 = (float)camera->viewport_bounds[3];
		if (!(x1 > x0) || !(y1 > y0)) return 0;
		aspect = (x1 - x0) / (y1 - y0);
	}
	if (!hcu_views_camera_from_snapshot(camera->position, camera->forward, camera->up,
		camera->vertical_field_of_view, aspect, camera->z_near, camera->z_far, &converted))
		return 0;
	sin_yaw = sinf(converted.yaw); cos_yaw = cosf(converted.yaw);
	sin_pitch = sinf(converted.pitch); cos_pitch = cosf(converted.pitch);
	forward[0] = cos_pitch * cos_yaw; forward[1] = cos_pitch * sin_yaw; forward[2] = sin_pitch;
	/* Exact basis used by render/camera.c: +Y is Halo-left. */
	right[0] = sin_yaw; right[1] = -cos_yaw; right[2] = 0.0f;
	up[0] = -sin_pitch * cos_yaw; up[1] = -sin_pitch * sin_yaw; up[2] = cos_pitch;
	half_v = camera->vertical_field_of_view * 0.5f;
	half_h = converted.hfov * 0.5f;
	sin_v = sinf(half_v); cos_v = cosf(half_v);
	sin_h = sinf(half_h); cos_h = cosf(half_h);
	/* near/far */
	hcu_render_frustum_set_plane(out, 0u, forward, converted.pos, converted.near_z);
	plane[0] = -forward[0]; plane[1] = -forward[1]; plane[2] = -forward[2];
	hcu_render_frustum_set_plane(out, 1u, plane, converted.pos, -converted.far_z);
	/* left and right */
	for (i = 0; i < 3u; ++i) plane[i] = forward[i] * sin_h - right[i] * cos_h;
	hcu_render_frustum_set_plane(out, 2u, plane, converted.pos, 0.0f);
	for (i = 0; i < 3u; ++i) plane[i] = forward[i] * sin_h + right[i] * cos_h;
	hcu_render_frustum_set_plane(out, 3u, plane, converted.pos, 0.0f);
	/* bottom and top */
	for (i = 0; i < 3u; ++i) plane[i] = forward[i] * sin_v + up[i] * cos_v;
	hcu_render_frustum_set_plane(out, 4u, plane, converted.pos, 0.0f);
	for (i = 0; i < 3u; ++i) plane[i] = forward[i] * sin_v - up[i] * cos_v;
	hcu_render_frustum_set_plane(out, 5u, plane, converted.pos, 0.0f);
	out->valid = 1u;
	return 1;
}

int hcu_render_objects_frustum_build(const halo_ps2_frame_view *view,
	hcu_render_objects_frustum *out)
{
	return hcu_render_objects_frustum_build_aspect(view, 0.0f, out);
}

static void hcu_render_object_frustums_prepare(const halo_ps2_frame_snapshot *snap)
{
	uint32_t view;
	if (!snap) return;
	if (s_frustum_snapshot == snap && s_frustum_sequence == snap->sequence &&
		s_frustum_generation == snap->map_generation) return;
	memset(s_view_frustums, 0, sizeof s_view_frustums);
	for (view = 0; view < snap->view_count && view < HALO_PS2_FRAME_MAX_VIEWS; ++view)
		if (snap->views[view].flags & HALO_PS2_FRAME_VIEW_ACTIVE)
			hcu_render_objects_frustum_build(&snap->views[view], &s_view_frustums[view]);
	s_frustum_snapshot = snap;
	s_frustum_sequence = snap->sequence;
	s_frustum_generation = snap->map_generation;
}

/* Admission uses the exact viewport aspect that the parent will draw for this
 * view. The camera's published bounds describe CE's source window, while C3
 * may render it into a different 1-4 view layout. */
#ifdef HCU_RENDER_OBJECTS_EE
static void hcu_render_object_frustums_prepare_admission(const halo_ps2_frame_snapshot *snap,
	uint32_t layout_view_count, int32_t screen_w, int32_t screen_h)
{
	hcu_render_layout layout;
	uint32_t view;
	if (!snap) return;
	hcu_render_object_frustums_prepare(snap);
	if (hcu_render_layout_compute(layout_view_count, screen_w, screen_h, &layout) != 0) {
		memset(s_view_frustums, 0, sizeof s_view_frustums);
		return;
	}
	/* A snapshot view without a matching output rectangle has unknown target
	 * projection; invalid frusta conservatively retain its objects. */
	memset(s_view_frustums, 0, sizeof s_view_frustums);
	for (view = 0; view < snap->view_count && view < HALO_PS2_FRAME_MAX_VIEWS; ++view)
		if (view < layout.view_count && (snap->views[view].flags & HALO_PS2_FRAME_VIEW_ACTIVE)) {
			float aspect = (float)layout.views[view].w / (float)layout.views[view].h;
			hcu_render_objects_frustum_build_aspect(&snap->views[view], aspect, &s_view_frustums[view]);
		}
}
#endif

#ifndef HCU_RENDER_OBJECTS_EE
static float hcu_render_object_bound_radius(const halo_ps2_frame_snapshot *snap,
	const halo_ps2_frame_object *object)
{
	(void)snap;
	return object ? object->render_radius : 0.0f;
}
#else
static float hcu_render_object_bound_radius(const halo_ps2_frame_snapshot *snap,
	const halo_ps2_frame_object *object);
#endif

int hcu_render_objects_bound_in_frustum(const float position[3], float radius,
	const hcu_render_objects_frustum *frustum)
{
	unsigned i;
	float x, y, z;
	if (!position || !frustum || !frustum->valid || !isfinite(radius) || radius <= 0.0f)
		return 1; /* unknown bound: retain */
	x = position[0]; y = position[1]; z = position[2];
	if (!isfinite(x) || !isfinite(y) || !isfinite(z)) return 1;
	for (i = 0; i < 6u; ++i)
		if (frustum->plane[i][0] * x + frustum->plane[i][1] * y +
			frustum->plane[i][2] * z + frustum->plane[i][3] < -radius) return 0;
	return 1;
}

static int hcu_render_object_in_frustum(const halo_ps2_frame_snapshot *snap,
	const halo_ps2_frame_object *object, const hcu_render_objects_frustum *frustum)
{
	float radius;
	if (!object || !isfinite(object->render_radius) || object->render_radius <= 0.0f) return 1;
	radius = hcu_render_object_bound_radius(snap, object);
	return hcu_render_objects_bound_in_frustum(object->world.position, radius, frustum);
}

int hcu_render_objects_object_visible_with_frustum(const halo_ps2_frame_snapshot *snap,
	const halo_ps2_frame_view *view, uint32_t object_index,
	const hcu_render_objects_frustum *frustum)
{
	const halo_ps2_frame_object *object;
	if (!snap || !view || object_index >= snap->object_count) return 0;
	object = &snap->objects[object_index];
	if (object->flags & HALO_PS2_FRAME_OBJECT_INVISIBLE) return 0;
	if (!hcu_render_object_in_frustum(snap, object, frustum)) return 0;
	if ((view->flags & (HALO_PS2_FRAME_VIEW_FIRST_PERSON_CAMERA | HALO_PS2_FRAME_VIEW_FIRST_PERSON)) &&
		view->unit_object != HALO_PS2_FRAME_NONE_U16 &&
		(object_index == view->unit_object ||
		 hcu_render_object_descends_from(snap, object_index, view->unit_object))) return 0;
	return 1;
}

/* Host callers get the same predicate; hot selection/residency loops use the
 * cached per-view frustum built once for this immutable snapshot. */
int hcu_render_objects_object_visible_in_view(const halo_ps2_frame_snapshot *snap,
	const halo_ps2_frame_view *view, uint32_t object_index)
{
	hcu_render_objects_frustum frustum;
	if (!snap || !view) return 0;
	(void)hcu_render_objects_frustum_build(view, &frustum);
	return hcu_render_objects_object_visible_with_frustum(snap, view, object_index, &frustum);
}

int hcu_render_objects_prepare_key_valid(const hcu_object_prepare_key *key, uint32_t sequence,
	uint32_t map_generation, uint32_t object_generation, uint32_t resource_id, uint32_t slot_epoch)
{
	return key && key->sequence == sequence && key->map_generation == map_generation &&
		key->object_generation == object_generation && key->resource_id == resource_id &&
		key->slot_epoch == slot_epoch;
}

int hcu_render_objects_prepare_select(int enabled, const hcu_object_prepare_key *key,
	uint32_t sequence, uint32_t map_generation, uint32_t object_generation,
	uint32_t resource_id, uint32_t slot_epoch, int prepared_slot, uint32_t prepared_hash,
	int fallback_slot, uint32_t fallback_hash, int *slot, uint32_t *pose_hash)
{
	int used;
	if (!slot || !pose_hash) return 0;
	used = enabled && hcu_render_objects_prepare_key_valid(key, sequence, map_generation,
		object_generation, resource_id, slot_epoch);
	*slot = used ? prepared_slot : fallback_slot;
	*pose_hash = used ? prepared_hash : fallback_hash;
	return used;
}

int hcu_render_objects_prepare_range_valid(uint32_t first, uint32_t count, uint32_t limit)
{
	return first <= limit && count <= limit - first;
}

void hcu_render_objects_prepare_matrix(const halo_ps2_snapshot_matrix4x3 *source, float *out)
{
	unsigned a, c;
	if (!source || !out) return;
	for (a = 0; a < 3; ++a) {
		const float *basis = a == 0 ? source->forward : a == 1 ? source->left : source->up;
		for (c = 0; c < 3; ++c) out[a * 4u + c] = basis[c] * source->scale;
		out[a * 4u + 3u] = 0.0f;
	}
	for (c = 0; c < 3; ++c) out[12u + c] = source->position[c];
	out[15] = 1.0f;
}

int hcu_render_objects_note_submission(hcu_render_objects_counters *counters,
	hcu_render_drawn_identity_set *identities, uint16_t type, uint32_t object_index,
	uint32_t generation)
{
	uint32_t i;
	uint32_t *submitted, *unique;
	if (!counters || !identities) return HCU_RENDER_CONTENT_E_ARGUMENT;
	switch (type) {
	case HCU_OBJECTS_TYPE_BIPED: submitted = &counters->submitted_bipeds; unique = &counters->unique_bipeds; break;
	case HCU_OBJECTS_TYPE_VEHICLE: submitted = &counters->submitted_vehicles; unique = &counters->unique_vehicles; break;
	case HCU_OBJECTS_TYPE_WEAPON: submitted = &counters->submitted_weapons; unique = &counters->unique_weapons; break;
	default: return HCU_RENDER_CONTENT_E_ARGUMENT;
	}
	(*submitted)++;
	for (i = 0; i < identities->count; i++)
		if (identities->entries[i].object_index == object_index &&
			identities->entries[i].generation == generation && identities->entries[i].type == type)
			return HCU_RENDER_CONTENT_OK;
	if (identities->count >= HCU_OBJECTS_DRAWN_IDENTITY_MAX) {
		identities->overflow++;
		counters->drawn_identity_overflow++;
		return HCU_RENDER_CONTENT_OK;
	}
	identities->entries[identities->count].object_index = object_index;
	identities->entries[identities->count].generation = generation;
	identities->entries[identities->count].type = type;
	identities->entries[identities->count].reserved = 0u;
	identities->count++;
	(*unique)++;
	return HCU_RENDER_CONTENT_OK;
}

uint32_t hcu_render_objects_residency_priority(uint16_t type)
{
	/* Keep player/AI bipeds and their weapons resident before optional traffic. */
	if (type == HCU_OBJECTS_TYPE_BIPED || type == HCU_OBJECTS_TYPE_WEAPON) return 0;
	if (type == HCU_OBJECTS_TYPE_VEHICLE) return 1;
	if (type == HCU_OBJECTS_TYPE_EFFECT) return 2;
	return 3;
}

int hcu_render_objects_residency_may_evict(int loaded, int referenced_this_frame,
	int fence_observed)
{
	return loaded && !referenced_this_frame && fence_observed == 1;
}

int hcu_render_objects_residency_victim_ok(int loaded, int referenced_this_frame,
	int fence_observed, uint32_t pins, uint32_t *evict_refused_pinned)
{
	if (!hcu_render_objects_residency_may_evict(loaded, referenced_this_frame, fence_observed))
		return 0;
	if (pins == 0u) return 1;
	if (evict_refused_pinned) (*evict_refused_pinned)++;
	return 0;
}

int hcu_render_objects_residency_rank_victim_ok(int loaded, uint32_t victim_rank, uint32_t requester_rank,
	int fence_observed, uint32_t pins, uint32_t *evict_refused_pinned)
{
	if (!loaded || fence_observed != 1 || victim_rank <= requester_rank) return 0;
	if (pins == 0u) return 1;
	if (evict_refused_pinned) (*evict_refused_pinned)++;
	return 0;
}

int hcu_render_objects_residency_pre_admit_allowed(uint32_t active_readers, int own_reader_pinned,
	int previous_fence_clear, uint32_t latest_sequence, uint32_t latest_generation)
{
	return active_readers == 0u && !own_reader_pinned && previous_fence_clear == 1 &&
		latest_sequence != 0u && latest_generation != 0u;
}

int hcu_render_objects_residency_pre_admit_matches(uint32_t planned_sequence, uint32_t planned_generation,
	uint32_t pinned_sequence, uint32_t pinned_generation)
{
	return planned_sequence != 0u && planned_generation != 0u &&
		planned_sequence == pinned_sequence && planned_generation == pinned_generation;
}

int hcu_render_objects_pool_request_fits(uint32_t need, uint32_t capacity)
{
	return need != 0 && need <= capacity;
}

/* ---- shared texture pages (C3.objects) -------------------------------------------------------------
 * Fixed table, open addressing with linear probes bounded by the table size. Retired and reclaimed slots stay
 * in the probe chain (RETIRED stays findable; TOMB keeps a removed slot from ending a chain early). */
int hcu_render_tex_pages_init(hcu_render_tex_pages *t)
{
	if (!t) return -1;
	memset(t, 0, sizeof *t);
	return 0;
}

static uint32_t tex_page_hash(const uint8_t id[HCU_OBJECTS_TEX_PAGE_ID_BYTES])
{
	return (uint32_t)id[0] | ((uint32_t)id[1] << 8) | ((uint32_t)id[2] << 16) | ((uint32_t)id[3] << 24);
}

uint32_t hcu_render_tex_page_acquire(hcu_render_tex_pages *t, const uint8_t id[HCU_OBJECTS_TEX_PAGE_ID_BYTES],
	uint32_t bytes, int *is_new)
{
	uint32_t k, start, insert = HCU_TEX_PAGE_NONE;
	if (is_new) *is_new = 0;
	if (!t || !id || bytes == 0u) return HCU_TEX_PAGE_NONE;
	t->acquires++;
	start = tex_page_hash(id) & (HCU_OBJECTS_TEX_PAGE_MAX - 1u);
	for (k = 0; k < HCU_OBJECTS_TEX_PAGE_MAX; k++) {
		uint32_t i = (start + k) & (HCU_OBJECTS_TEX_PAGE_MAX - 1u);
		hcu_render_tex_page *p = &t->page[i];
		if (k + 1u > t->probe_max) t->probe_max = k + 1u;
		if (p->state == HCU_TEX_PAGE_FREE) {
			if (insert == HCU_TEX_PAGE_NONE) insert = i;
			break;
		}
		if (p->state == HCU_TEX_PAGE_TOMB) {
			if (insert == HCU_TEX_PAGE_NONE) insert = i;
			continue;
		}
		if (memcmp(p->id, id, HCU_OBJECTS_TEX_PAGE_ID_BYTES) != 0) continue;
		if (p->bytes != bytes) { t->conflicts++; return HCU_TEX_PAGE_NONE; }
		if (p->state == HCU_TEX_PAGE_RETIRED) {
			p->state = HCU_TEX_PAGE_LIVE;
			t->retired--;
			t->live++;
		}
		p->refs++;
		return i;
	}
	if (insert == HCU_TEX_PAGE_NONE) { t->full_refusals++; return HCU_TEX_PAGE_NONE; }
	{
		hcu_render_tex_page *p = &t->page[insert];
		memcpy(p->id, id, HCU_OBJECTS_TEX_PAGE_ID_BYTES);
		p->bytes = bytes;
		p->pool_off = 0;
		p->refs = 1;
		p->kick = 0;
		p->state = HCU_TEX_PAGE_LIVE;
		t->live++;
		t->new_pages++;
		if (is_new) *is_new = 1;
	}
	return insert;
}

int hcu_render_tex_page_release(hcu_render_tex_pages *t, uint32_t index, uint32_t kick)
{
	hcu_render_tex_page *p;
	if (!t || index >= HCU_OBJECTS_TEX_PAGE_MAX) return -1;
	p = &t->page[index];
	if (p->state != HCU_TEX_PAGE_LIVE || p->refs == 0u) return -1;
	t->releases++;
	p->refs--;
	if (p->refs == 0u) {
		/* The kick is the latest one: any chain that could read the page was built before or at this kick. */
		p->kick = kick;
		p->state = HCU_TEX_PAGE_RETIRED;
		t->live--;
		t->retired++;
	}
	return 0;
}

int hcu_render_tex_page_reclaim_next(hcu_render_tex_pages *t, int (*fence_observed)(uint32_t kick),
	uint32_t *pool_off, uint32_t *bytes)
{
	uint32_t i;
	if (!t || !fence_observed || !pool_off || !bytes) return 0;
	for (i = 0; i < HCU_OBJECTS_TEX_PAGE_MAX; i++) {
		hcu_render_tex_page *p = &t->page[i];
		if (p->state != HCU_TEX_PAGE_RETIRED || p->refs != 0u) continue;
		if (p->kick != 0u && fence_observed(p->kick) != 1) continue;
		*pool_off = p->pool_off;
		*bytes = p->bytes;
		p->state = HCU_TEX_PAGE_TOMB;
		t->retired--;
		t->reclaims++;
		return 1;
	}
	return 0;
}

int hcu_render_objects_select(const halo_ps2_frame_snapshot *snap, uint32_t view,
	const hcu_render_objects_model *models, uint32_t model_count,
	hcu_render_object_draw *out, uint32_t capacity, uint32_t *count,
	hcu_render_objects_counters *counters)
{
	const halo_ps2_frame_view *v;
	const hcu_render_objects_frustum *frustum;
	uint32_t ref, first, n, emitted = 0, i;
	if (!snap || !out || !count || !counters) return HCU_RENDER_CONTENT_E_ARGUMENT;
	*count = 0;
	if (snap->version != HALO_PS2_FRAME_SNAPSHOT_VERSION || view >= snap->view_count ||
		view >= HALO_PS2_FRAME_MAX_VIEWS || snap->object_count > HALO_PS2_FRAME_MAX_OBJECTS ||
		snap->view_ref_count > HALO_PS2_FRAME_MAX_VIEW_REFS ||
		snap->attachment_count > HALO_PS2_FRAME_MAX_ATTACHMENTS)
		return HCU_RENDER_CONTENT_E_ARGUMENT;
	counters->views_seen++;
	v = &snap->views[view];
	if (!(v->flags & HALO_PS2_FRAME_VIEW_ACTIVE)) return 0;
	hcu_render_object_frustums_prepare(snap);
	frustum = &s_view_frustums[view];
	first = v->view_ref_first;
	n = v->view_ref_count;
	if (first > snap->view_ref_count || n > snap->view_ref_count - first) {
		counters->failures++;
		return HCU_RENDER_CONTENT_E_ARGUMENT;
	}
	for (ref = first; ref < first + n; ref++) {
		uint32_t oi = snap->view_refs[ref];
		const halo_ps2_frame_object *o;
		const halo_ps2_frame_resource *r;
		int slot;
		if (oi >= snap->object_count) { counters->failures++; continue; }
		o = &snap->objects[oi];
		/* CE publishes the local player's unit and attached inventory with the
		 * rest of the world. In first-person, it skips this biped and therefore
		 * never enters its child list. Filter both the body and its descendants
		 * only from this view; other players' attached weapons and loose world
		 * weapons remain available. Camera mode is carried independently of FP
		 * model-copy success; keep the older flag as a compatibility fallback. */
		if (!hcu_render_objects_object_visible_with_frustum(snap, v, oi, frustum)) continue;
		for (i = 0; i < emitted; i++)
			if (out[i].object_index == oi) break;
		if (i != emitted) { counters->deduped++; continue; }
		if (o->resource_slot >= snap->resource_count) { counters->failures++; continue; }
		r = &snap->resources[o->resource_slot];
		slot = -1;
		{
			uint32_t cached_hash = 0;
#ifdef HCU_RENDER_OBJECTS_EE
			if (HCU_C3_OBJECT_PREPARE_CACHE && models == s_meta)
				(void)prepared_lookup(snap, oi, o->id.generation, r->id, &slot, &cached_hash);
#endif
			if (slot >= 0 && (uint32_t)slot >= model_count) slot = -1;
			if (slot < 0) slot = hcu_render_objects_find_model(models, model_count, r->id);
		if (slot < 0) { counters->model_misses++; counters->failures++; continue; }
		if (o->palette_count > 0 && (uint32_t)o->palette_first + o->palette_count > snap->palette_count) {
			counters->failures++;
			continue;
		}
		if ((o->flags & HCU_OBJECTS_FLAG_SKINNED) && o->palette_count == 0) {
			counters->failures++;
			continue;
		}
		if (emitted >= capacity || emitted >= HCU_OBJECTS_MAX_DRAW) { counters->failures++; continue; }
		out[emitted].view = view;
		out[emitted].object_index = oi;
		out[emitted].generation = o->id.generation;
		out[emitted].definition_index = o->definition_index;
		out[emitted].resource_id = r->id;
		out[emitted].slot = (uint16_t)slot;
		out[emitted].type = (uint16_t)o->type;
		out[emitted].flags = o->flags;
		out[emitted].palette_first = o->palette_first;
		out[emitted].palette_count = o->palette_count;
		out[emitted].ground_weapon_lod = (uint8_t)hcu_render_object_is_loose_weapon(snap, oi);
		out[emitted].reserved_lod = 0;
		out[emitted].pose_hash = cached_hash ? cached_hash : hcu_render_objects_pose_hash(snap->palette, snap->palette_count,
			o->palette_first, o->palette_count);
		out[emitted].world = o->world;
		}
		counters->model_hits++;
		emitted++;
	}
	*count = emitted;
	return 0;
}

int hcu_render_objects_select_first_person(const halo_ps2_frame_snapshot *snap,
	uint32_t view, const hcu_render_objects_model *models, uint32_t model_count,
	hcu_render_first_person_draw out[2], uint32_t *count,
	hcu_render_objects_counters *counters)
{
	const halo_ps2_frame_view *v;
	uint16_t resource_slots[2];
	uint16_t palette_first[2];
	uint16_t palette_count[2];
	const uint8_t kinds[2] = { HCU_OBJECTS_FP_WEAPON, HCU_OBJECTS_FP_HANDS };
	uint32_t i, emitted = 0;
	if (!snap || !out || !count || !counters) return HCU_RENDER_CONTENT_E_ARGUMENT;
	*count = 0;
	if (snap->version != HALO_PS2_FRAME_SNAPSHOT_VERSION ||
		view >= snap->view_count || view >= HALO_PS2_FRAME_MAX_VIEWS ||
		snap->resource_count > HALO_PS2_FRAME_MAX_RESOURCES ||
		snap->palette_count > HALO_PS2_FRAME_MAX_PALETTE)
		return HCU_RENDER_CONTENT_E_ARGUMENT;
	if (!(snap->views[view].flags & HALO_PS2_FRAME_VIEW_ACTIVE)) return 0;
	v = &snap->views[view];
	if (!(v->flags & HALO_PS2_FRAME_VIEW_FIRST_PERSON)) return 0;
	resource_slots[0] = v->first_person_weapon_resource_slot;
	resource_slots[1] = v->first_person_hands_resource_slot;
	palette_first[0] = v->first_person_weapon_palette_first;
	palette_first[1] = v->first_person_hands_palette_first;
	palette_count[0] = v->first_person_weapon_palette_count;
	palette_count[1] = v->first_person_hands_palette_count;
	for (i = 0; i < 2u; ++i) {
		uint16_t resource_slot = resource_slots[i];
		uint16_t first = palette_first[i];
		uint16_t nodes = palette_count[i];
		const halo_ps2_frame_resource *resource;
		int slot;
		if (resource_slot == HALO_PS2_FRAME_NONE_U16) continue;
		if (resource_slot >= snap->resource_count ||
			first > snap->palette_count || nodes > snap->palette_count - first ||
			emitted >= 2u) {
			counters->failures++;
			continue;
		}
		resource = &snap->resources[resource_slot];
		if (resource->generation != snap->map_generation) {
			counters->first_person_stale_resources++;
			counters->failures++;
			continue;
		}
		slot = hcu_render_objects_find_model(models, model_count, resource->id);
		if (slot < 0) {
			counters->first_person_model_misses++;
			counters->model_misses++;
			counters->failures++;
			continue;
		}
		if (!models[slot].node_count ||
			models[slot].node_count > HALO_PS2_FRAME_MAX_FIRST_PERSON_NODES ||
			nodes != models[slot].node_count) {
			counters->failures++;
			continue;
		}
		out[emitted].resource_id = resource->id;
		out[emitted].model_slot = (uint16_t)slot;
		out[emitted].palette_first = first;
		out[emitted].palette_count = nodes;
		out[emitted].kind = kinds[i];
		out[emitted].reserved = 0u;
		counters->first_person_model_hits++;
		counters->model_hits++;
		emitted++;
	}
	*count = emitted;
	return 0;
}

/* ---- C3.6 pose hash, pose tracking, effect requests ------------------------------------------- */

static uint32_t fnv_word(uint32_t h, uint32_t w)
{
	uint32_t b;
	for (b = 0; b < 4u; b++) {
		h ^= (w >> (8u * b)) & 0xFFu;
		h *= 16777619u;
	}
	return h;
}

static uint32_t float_bits(float f)
{
	uint32_t u;
	memcpy(&u, &f, sizeof u);
	return u;
}

uint32_t hcu_render_objects_pose_hash(const halo_ps2_snapshot_matrix4x3 *palette, uint32_t palette_count,
	uint32_t first, uint32_t n)
{
	uint32_t h = 2166136261u, i, k;
	if (n == 0u || !palette || first > palette_count || n > palette_count - first) return 0u;
	for (i = 0; i < n; i++) {
		const halo_ps2_snapshot_matrix4x3 *m = &palette[first + i];
		h = fnv_word(h, float_bits(m->scale));
		for (k = 0; k < 3u; k++) h = fnv_word(h, float_bits(m->forward[k]));
		for (k = 0; k < 3u; k++) h = fnv_word(h, float_bits(m->left[k]));
		for (k = 0; k < 3u; k++) h = fnv_word(h, float_bits(m->up[k]));
		for (k = 0; k < 3u; k++) h = fnv_word(h, float_bits(m->position[k]));
	}
	return h == 0u ? 1u : h;
}

int hcu_render_pose_track(hcu_render_pose_tracker *t, uint32_t object_index, uint32_t generation,
	uint32_t hash, hcu_render_objects_counters *counters)
{
	int changed;
	if (!t || object_index >= HCU_OBJECTS_POSE_TRACK) return HCU_RENDER_CONTENT_E_ARGUMENT;
	changed = t->seen[object_index] && t->generation[object_index] == generation &&
		t->hash[object_index] != hash;
	if (counters) {
		if (changed) counters->pose_changes++;
		else if (t->seen[object_index] && t->generation[object_index] == generation) counters->pose_static++;
	}
	t->seen[object_index] = 1;
	t->generation[object_index] = generation;
	t->hash[object_index] = hash;
	return changed;
}

int hcu_render_objects_track_poses(const halo_ps2_frame_snapshot *snap, hcu_render_pose_tracker *t,
	hcu_render_objects_counters *counters)
{
	uint32_t oi;
	if (!snap || !t) return HCU_RENDER_CONTENT_E_ARGUMENT;
	if (snap->version != HALO_PS2_FRAME_SNAPSHOT_VERSION || snap->object_count > HALO_PS2_FRAME_MAX_OBJECTS ||
		snap->palette_count > HALO_PS2_FRAME_MAX_PALETTE)
		return HCU_RENDER_CONTENT_E_ARGUMENT;
	for (oi = 0; oi < snap->object_count; oi++) {
		const halo_ps2_frame_object *o = &snap->objects[oi];
		uint32_t h;
		if (o->palette_count == 0u) continue;
		if ((uint32_t)o->palette_first + o->palette_count > snap->palette_count) {
			if (counters) counters->failures++;
			continue;
		}
		h = 0u;
#ifdef HCU_RENDER_OBJECTS_EE
		if (HCU_C3_OBJECT_PREPARE_CACHE && o->resource_slot < snap->resource_count) {
			int slot = -1;
			if (prepared_lookup(snap, oi, o->id.generation, snap->resources[o->resource_slot].id, &slot, &h)) { /* prepared */ }
		}
#endif
		if (!h) h = hcu_render_objects_pose_hash(snap->palette, snap->palette_count,
			o->palette_first, o->palette_count);
		hcu_render_pose_track(t, oi, o->id.generation, h, counters);
	}
	return HCU_RENDER_CONTENT_OK;
}

int hcu_render_effects_select(const halo_ps2_frame_snapshot *snap, uint32_t view,
	hcu_render_effect_draw *out, uint32_t capacity, uint32_t *count,
	hcu_render_objects_counters *counters)
{
	const halo_ps2_frame_view *v;
	uint32_t e, emitted = 0, budget;
	if (!snap || !out || !count) return HCU_RENDER_CONTENT_E_ARGUMENT;
	*count = 0;
	if (snap->version != HALO_PS2_FRAME_SNAPSHOT_VERSION || view >= snap->view_count ||
		view >= HALO_PS2_FRAME_MAX_VIEWS || snap->fx_request_count > HALO_PS2_FRAME_MAX_FX_REQUESTS)
		return HCU_RENDER_CONTENT_E_ARGUMENT;
	if (capacity > HCU_FX_MAX_PER_VIEW) capacity = HCU_FX_MAX_PER_VIEW;   /* fixed per-view cap */
	v = &snap->views[view];
	if (!(v->flags & HALO_PS2_FRAME_VIEW_ACTIVE)) return 0;
	/* Viewport-share budget: the full view draws up to the cap; a half view a half; quarter views (3-4 active)
	 * a quarter each. Keeps the chain's fx packets inside the per-view geometry budget. */
	{
		uint32_t active = 0, vi;
		for (vi = 0; vi < snap->view_count && vi < HALO_PS2_FRAME_MAX_VIEWS; vi++)
			if (snap->views[vi].flags & HALO_PS2_FRAME_VIEW_ACTIVE) active++;
		budget = active <= 1u ? HCU_FX_MAX_PER_VIEW : active == 2u ? HCU_FX_MAX_PER_VIEW / 2u
			: HCU_FX_MAX_PER_VIEW / 4u;
		if (budget > capacity) budget = capacity;
	}
	for (e = 0; e < snap->fx_request_count; e++) {
		const halo_ps2_frame_fx_request *fx = &snap->fx_requests[e];
		uint32_t ref, owned = 0;
		if (!(fx->view_mask & (1u << view))) continue;
		/* C3.6(c): an unowned request (world decals, owner NONE) is drawn by every view its mask names. An
		 * owned request must belong to an object this view references. Gating NONE owners out dropped every decal. */
		if (fx->owner_object == HALO_PS2_FRAME_NONE_U16) {
			owned = 1;
		} else {
			for (ref = v->view_ref_first; ref < v->view_ref_first + v->view_ref_count && ref < snap->view_ref_count; ref++)
				if (snap->view_refs[ref] == fx->owner_object) { owned = 1; break; }
		}
		if (!owned) continue;
		if (!isfinite(fx->position[0]) || !isfinite(fx->position[1]) || !isfinite(fx->position[2]) ||
			fx->kind == 0u || fx->kind > HALO_PS2_FRAME_FX_PARTICLE) {
			if (counters) counters->effects_refused++;
			continue;
		}
		if (emitted >= budget) {
			/* Per-view fx draw budget (viewport share): excess requests are deferred, not refused. */
			if (counters) counters->fx_budget_deferred++;
			continue;
		}
		if (emitted >= capacity) {
			if (counters) counters->effects_refused++;
			continue;
		}
		out[emitted].view = view;
		out[emitted].owner_object = fx->owner_object;
		out[emitted].source_index = fx->source_index;
		out[emitted].source_generation = fx->source_generation;
		out[emitted].resource_id = fx->resource_id;
		out[emitted].permutation = fx->permutation;
		out[emitted].kind = fx->kind;
		out[emitted].flags = fx->flags;
		out[emitted].position[0] = fx->position[0];
		out[emitted].position[1] = fx->position[1];
		out[emitted].position[2] = fx->position[2];
		out[emitted].forward[0] = fx->forward[0];
		out[emitted].forward[1] = fx->forward[1];
		out[emitted].forward[2] = fx->forward[2];
		out[emitted].scale = fx->scale;
		out[emitted].age_sec = fx->age_sec;
		out[emitted].particle_flags = fx->particle_flags;
		out[emitted].particle_shader_flags = fx->particle_shader_flags;
		out[emitted].bitmap_width = fx->bitmap_width;
		out[emitted].bitmap_height = fx->bitmap_height;
		out[emitted].framebuffer_blend_function = fx->kind == HALO_PS2_FRAME_FX_DECAL ?
			(uint8_t)HALO_PS2_FRAME_FX_DECAL_BLEND(fx->flags) : fx->framebuffer_blend_function;
		out[emitted].framebuffer_fade_mode = fx->kind == HALO_PS2_FRAME_FX_DECAL ?
			(uint8_t)HALO_PS2_FRAME_FX_DECAL_FADE(fx->flags) : fx->framebuffer_fade_mode;
		out[emitted].local_player_index = fx->local_player_index;
		out[emitted].sprite_orientation = fx->sprite_orientation;
		out[emitted].native_geometry = (fx->flags & HALO_PS2_FRAME_FX_NATIVE_GEOMETRY) ?
			fx->decal_geometry : NULL;
		out[emitted].native_surface_id = fx->decal_surface_id;
		out[emitted].sequence_index = fx->sequence_index;
		out[emitted].frame_index = fx->frame_index;
		out[emitted].rotation = fx->rotation;
		out[emitted].lifespan_sec = fx->lifespan_sec;
		out[emitted].fade_in_sec = fx->fade_in_sec;
		out[emitted].fade_out_sec = fx->fade_out_sec;
		out[emitted].minimum_pixels = fx->minimum_pixels;
		out[emitted].lod_cutoff = fx->lod_cutoff;
		out[emitted].runtime_oo_width = fx->runtime_oo_width;
		if (fx->kind == HALO_PS2_FRAME_FX_DECAL)
			memcpy(out[emitted].color_argb, fx->decal_color_argb, sizeof fx->decal_color_argb);
		else memcpy(out[emitted].color_argb, fx->color_argb, sizeof fx->color_argb);
		out[emitted].decal_intensity = fx->decal_intensity;
		memcpy(out[emitted].segment_end_color_argb, fx->segment_end_color_argb,
			sizeof fx->segment_end_color_argb);
		out[emitted].segment_end_width = fx->segment_end_width;
		memcpy(out[emitted].sprite_uv, fx->sprite_uv, sizeof fx->sprite_uv);
		memcpy(out[emitted].registration, fx->registration, sizeof fx->registration);
		if (counters) counters->effects_selected++;
		emitted++;
	}
	*count = emitted;
	return 0;
}

/* ---- C3.6(c) quad generation (pure) -------------------------------------------------------------- */

static void fx_cross(const float a[3], const float b[3], float out[3])
{
	out[0] = a[1] * b[2] - a[2] * b[1];
	out[1] = a[2] * b[0] - a[0] * b[2];
	out[2] = a[0] * b[1] - a[1] * b[0];
}

static float fx_len(const float v[3])
{
	return sqrtf(v[0] * v[0] + v[1] * v[1] + v[2] * v[2]);
}

static int fx_finite3(const float v[3])
{
	return isfinite(v[0]) && isfinite(v[1]) && isfinite(v[2]);
}

int hcu_render_fx_camera_basis(const halo_ps2_snapshot_camera *cam, float right[3], float up[3])
{
	float f[3], u[3], l, r[3], cu[3];
	int k;
	if (!cam || !right || !up) return HCU_RENDER_CONTENT_E_ARGUMENT;
	if (!fx_finite3(cam->forward) || !fx_finite3(cam->up)) return HCU_RENDER_CONTENT_E_ARGUMENT;
	for (k = 0; k < 3; k++) { f[k] = cam->forward[k]; u[k] = cam->up[k]; }
	l = fx_len(f);
	if (!(l > 1e-6f)) return HCU_RENDER_CONTENT_E_ARGUMENT;
	for (k = 0; k < 3; k++) f[k] /= l;
	fx_cross(f, u, r);
	l = fx_len(r);
	if (!(l > 1e-6f)) return HCU_RENDER_CONTENT_E_ARGUMENT;          /* forward parallel to up */
	for (k = 0; k < 3; k++) r[k] /= l;
	fx_cross(r, f, cu);                                                /* unit: r and f are orthonormal */
	for (k = 0; k < 3; k++) { right[k] = r[k]; up[k] = cu[k]; }
	return 0;
}

int hcu_render_first_person_world(const halo_ps2_snapshot_camera *cam, const halo_ps2_snapshot_matrix4x3 *local,
	halo_ps2_snapshot_matrix4x3 *world)
{
	float left[3], ax[3][3], origin[3];
	unsigned a, c;
	if (!cam || !local || !world) return HCU_RENDER_CONTENT_E_ARGUMENT;
	if (!fx_finite3(cam->forward) || !fx_finite3(cam->up) || !fx_finite3(cam->position) ||
		!fx_finite3(local->forward) || !fx_finite3(local->left) || !fx_finite3(local->up) ||
		!fx_finite3(local->position) || !isfinite(local->scale)) return HCU_RENDER_CONTENT_E_ARGUMENT;
	/* CE's left: up x forward (matrix4x3_rotation_from_vectors). The camera axes are F, L, U. */
	fx_cross(cam->up, cam->forward, left);
	for (c = 0; c < 3; c++) { ax[0][c] = cam->forward[c]; ax[1][c] = left[c]; ax[2][c] = cam->up[c]; origin[c] = cam->position[c]; }
	for (a = 0; a < 3; a++) {
		const float *basis = a == 0 ? local->forward : a == 1 ? local->left : local->up;
		float *out = a == 0 ? world->forward : a == 1 ? world->left : world->up;
		for (c = 0; c < 3; c++)
			out[c] = basis[0] * ax[0][c] + basis[1] * ax[1][c] + basis[2] * ax[2][c];
	}
	for (c = 0; c < 3; c++)
		world->position[c] = origin[c] + local->position[0] * ax[0][c] + local->position[1] * ax[1][c] +
			local->position[2] * ax[2][c];
	world->scale = local->scale;
	return 0;
}

int hcu_render_fx_build_quad(const hcu_render_effect_draw *e, const float right[3], const float up[3],
	hcu_render_fx_quad *q)
{
	float a[3], b[3], n[3], ref[3] = { 0.0f, 0.0f, 1.0f }, l, s;
	int decal, k, c;
	static const float sx[4] = { -1.0f, 1.0f, 1.0f, -1.0f };
	static const float sy[4] = { -1.0f, -1.0f, 1.0f, 1.0f };
	if (!e || !q || !right || !up) return HCU_RENDER_CONTENT_E_ARGUMENT;
	s = e->scale;
	if (!(s > 0.0f) || !isfinite(s) || !fx_finite3(e->position)) return HCU_RENDER_CONTENT_E_ARGUMENT;
	if (e->kind != HALO_PS2_FRAME_FX_EFFECT && e->kind != HALO_PS2_FRAME_FX_PARTICLE_SYSTEM &&
		e->kind != HALO_PS2_FRAME_FX_CONTRAIL && e->kind != HALO_PS2_FRAME_FX_DECAL)
		return HCU_RENDER_CONTENT_E_ARGUMENT;
	q->kind = (uint16_t)e->kind;
	q->resource_id = e->resource_id;
	q->pad = 0;
	decal = 0;
	if (e->kind == HALO_PS2_FRAME_FX_DECAL && fx_finite3(e->forward)) {
		for (k = 0; k < 3; k++) n[k] = e->forward[k];
		l = fx_len(n);
		if (l > 1e-6f) {
			for (k = 0; k < 3; k++) n[k] /= l;
			decal = 1;
		}
	}
	if (decal) {
		/* tangent a = ref x n (ref is world up, or world +y when the normal is almost vertical), b = n x a */
		if (fabsf(n[2]) > 0.99f) { ref[0] = 0.0f; ref[1] = 1.0f; ref[2] = 0.0f; }
		fx_cross(ref, n, a);
		l = fx_len(a);
		/* A malformed finite normal can still overflow its length calculation. Refuse it
		 * instead of normalizing a zero/NaN tangent and emitting corrupt geometry. */
		if (!(l > 1e-6f) || !isfinite(l)) return HCU_RENDER_CONTENT_E_ARGUMENT;
		for (k = 0; k < 3; k++) a[k] /= l;
		fx_cross(n, a, b);
	} else {
		for (k = 0; k < 3; k++) { a[k] = right[k]; b[k] = up[k]; }
	}
	for (c = 0; c < 4; c++)
		for (k = 0; k < 3; k++) {
			q->v[c][k] = e->position[k] + s * (sx[c] * a[k] + sy[c] * b[k]);
			if (!isfinite(q->v[c][k])) return HCU_RENDER_CONTENT_E_ARGUMENT;
		}
	return 0;
}

int hcu_render_fx_particle_build_quad(const hcu_render_effect_draw *e,
	const halo_ps2_snapshot_camera *camera, int viewport_h, hcu_render_fx_quad *q)
{
	float axis_x[3], axis_y[3], direction[3], view_ray[3], right[3], up[3], forward[3];
	float radius, scale, depth, diameter, pixel_scale = 1.0f, vfov;
	static const float cx[4] = { 0, 1, 1, 0 };
	static const float cy[4] = { 0, 0, 1, 1 };
	int i, k;
	if (!e || !camera || !q || e->kind != HALO_PS2_FRAME_FX_PARTICLE ||
		(e->bitmap_width == 0 || e->bitmap_height == 0) || viewport_h <= 0 || !isfinite(e->scale) || e->scale <= 0.0f ||
		!isfinite(e->runtime_oo_width) || !fx_finite3(e->position) ||
		!isfinite(e->age_sec) || !isfinite(e->lifespan_sec) || e->age_sec < 0.0f ||
		!isfinite(e->rotation)) return HCU_RENDER_CONTENT_E_ARGUMENT;
	if (e->age_sec >= e->lifespan_sec &&
		!(e->flags & HALO_PS2_FRAME_FX_PARTICLE_FINAL_SEQUENCE)) return 1;
	if (!fx_finite3(camera->position) || !isfinite(camera->vertical_field_of_view) ||
		!(camera->vertical_field_of_view > 0.0f) ||
		hcu_render_fx_camera_basis(camera, right, up) != 0) return HCU_RENDER_CONTENT_E_ARGUMENT;
	memcpy(forward, camera->forward, sizeof forward);
	{
		float len = fx_len(forward);
		if (!(len > 1e-6f) || !isfinite(len)) return HCU_RENDER_CONTENT_E_ARGUMENT;
		for (k = 0; k < 3; k++) forward[k] /= len;
	}
	if (e->sprite_orientation == 0u) {
		memcpy(axis_x, right, sizeof axis_x);
		memcpy(axis_y, up, sizeof axis_y);
	} else {
		float len;
		if (!fx_finite3(e->forward)) return HCU_RENDER_CONTENT_E_ARGUMENT;
		memcpy(direction, e->forward, sizeof direction);
		len = fx_len(direction);
		if (!(len > 1e-6f) || !isfinite(len)) return HCU_RENDER_CONTENT_E_ARGUMENT;
		for (k = 0; k < 3; k++) direction[k] /= len;
		if (e->sprite_orientation == 1u) {
			for (k = 0; k < 3; k++) view_ray[k] = e->position[k] - camera->position[k];
			fx_cross(view_ray, direction, axis_y);
			len = fx_len(axis_y);
			if (!(len > 1e-6f)) memcpy(axis_y, up, sizeof axis_y);
			else for (k = 0; k < 3; k++) axis_y[k] /= len;
			memcpy(axis_x, direction, sizeof axis_x);
		} else if (e->sprite_orientation == 2u) {
			float reference[3] = { 0.0f, 0.0f, 1.0f };
			fx_cross(direction, reference, axis_x);
			len = fx_len(axis_x);
			if (len * len < 1e-2f) {
				/* CE's fallback is viewer-space global-left; in the HCU's
				 * world-space particle basis global-left is +Y. */
				reference[0] = 0.0f; reference[1] = 1.0f; reference[2] = 0.0f;
				fx_cross(direction, reference, axis_x);
				len = fx_len(axis_x);
			}
			if (!(len > 1e-6f)) return HCU_RENDER_CONTENT_E_ARGUMENT;
			for (k = 0; k < 3; k++) axis_x[k] /= len;
			/* CE keeps basis.forward=cross(direction, reference), copies it
			 * to left, then rotates left -90 around direction. Its math helper
			 * computes v - sine*(v cross axis), so left becomes
			 * -cross(direction, axis_x). */
			fx_cross(direction, axis_x, axis_y);
			for (k = 0; k < 3; k++) axis_y[k] = -axis_y[k];
		} else return HCU_RENDER_CONTENT_E_ARGUMENT;
	}
	radius = e->scale;
	depth = (e->position[0] - camera->position[0]) * forward[0] +
		(e->position[1] - camera->position[1]) * forward[1] +
		(e->position[2] - camera->position[2]) * forward[2];
	vfov = camera->vertical_field_of_view;
	if (!(depth > 0.0f)) return 1;
	diameter = (float)viewport_h * radius / (tanf(vfov * 0.5f) * depth);
	if (diameter <= e->lod_cutoff) return 1;
	if (e->minimum_pixels > diameter) pixel_scale = e->minimum_pixels / diameter;
	scale = 2.0f * radius * e->runtime_oo_width * pixel_scale;
	if (!isfinite(scale) || !(scale > 0.0f)) return HCU_RENDER_CONTENT_E_ARGUMENT;
	q->kind = (uint16_t)e->kind; q->resource_id = e->resource_id; q->pad = 0;
	for (i = 0; i < 4; i++) {
		float u = e->sprite_uv[cx[i] ? 1 : 0];
		float v = e->sprite_uv[cy[i] ? 2 : 3];
		float x = (u - (e->sprite_uv[0] + e->registration[0])) * (float)e->bitmap_width;
		/* CE build_sprite_compute_scale multiplies both normalized UV offsets
		 * by bitmap->width before applying the shared sprite scale. */
		float y = ((e->registration[1] + e->sprite_uv[2]) - v) * (float)e->bitmap_width;
		float cs = cosf(e->rotation), sn = sinf(e->rotation);
		float rx = x * cs - y * sn, ry = y * cs + x * sn;
		if (e->particle_flags & 0x0004u) rx = -rx;
		if (e->particle_flags & 0x0008u) ry = -ry;
		for (k = 0; k < 3; k++) {
			q->v[i][k] = e->position[k] + scale * (axis_x[k] * rx + axis_y[k] * ry);
			if (!isfinite(q->v[i][k])) return HCU_RENDER_CONTENT_E_ARGUMENT;
		}
	}
	return 0;
}

int hcu_render_fx_contrail_build_quad(const hcu_render_effect_draw *e,
	const halo_ps2_snapshot_camera *camera, hcu_render_fx_quad *q)
{
	float tangent[3], eye[3], side[3], length, widths[2];
	unsigned end, axis;
	if (!e || !camera || !q || e->kind != HALO_PS2_FRAME_FX_CONTRAIL ||
		!fx_finite3(e->position) || !fx_finite3(e->forward) ||
		!fx_finite3(camera->position) || !isfinite(e->scale) ||
		!isfinite(e->segment_end_width) || e->scale < 0.0f || e->segment_end_width < 0.0f)
		return HCU_RENDER_CONTENT_E_ARGUMENT;
	for (axis = 0; axis < 3; ++axis) {
		tangent[axis] = e->forward[axis] - e->position[axis];
		eye[axis] = camera->position[axis] - e->position[axis];
	}
	length = fx_len(tangent);
	if (!(length > 1e-6f) || !isfinite(length)) return 1;
	for (axis = 0; axis < 3; ++axis) tangent[axis] /= length;
	switch (e->sprite_orientation) {
	case 0u: /* CE vertical ribbon */
		side[0] = side[1] = 0.0f; side[2] = 1.0f;
		break;
	case 1u: /* CE horizontal ribbon */
	case 2u: /* CE media-mapped ribbon: same segment cross-section */
		side[0] = -tangent[1]; side[1] = tangent[0]; side[2] = 0.0f;
		break;
	case 4u: /* CE viewer-facing ribbon */
		fx_cross(tangent, eye, side);
		length = fx_len(side);
		if (!(length > 1e-6f) || !isfinite(length)) return 1;
		for (axis = 0; axis < 3; ++axis) side[axis] /= length;
		break;
	default: /* CE ground-mapped contrails are rendered by the dedicated BSP path. */
		return 1;
	}
	length = fx_len(side);
	if (!(length > 1e-6f) || !isfinite(length)) return 1;
	for (axis = 0; axis < 3; ++axis) side[axis] /= length;
	widths[0] = e->scale * 0.5f;
	widths[1] = e->segment_end_width * 0.5f;
	q->kind = (uint16_t)e->kind; q->resource_id = e->resource_id; q->pad = 0;
	for (end = 0; end < 2u; ++end) {
		const float *center = end ? e->forward : e->position;
		unsigned first = end ? 2u : 0u;
		float sign0 = end ? 1.0f : -1.0f;
		float sign1 = end ? -1.0f : 1.0f;
		for (axis = 0; axis < 3; ++axis) {
			q->v[first][axis] = center[axis] + sign0 * widths[end] * side[axis];
			q->v[first + 1u][axis] = center[axis] + sign1 * widths[end] * side[axis];
		}
	}
	return 0;
}

int hcu_render_fx_flat_colour(uint16_t kind, uint8_t rgba[4])
{
	if (!rgba) return HCU_RENDER_CONTENT_E_ARGUMENT;
	switch (kind) {
	case HALO_PS2_FRAME_FX_EFFECT:          rgba[0] = 255; rgba[1] = 160; rgba[2] = 48;  rgba[3] = 128; return 0;
	case HALO_PS2_FRAME_FX_PARTICLE_SYSTEM: rgba[0] = 200; rgba[1] = 200; rgba[2] = 200; rgba[3] = 96;  return 0;
	case HALO_PS2_FRAME_FX_PARTICLE:       rgba[0] = 255; rgba[1] = 255; rgba[2] = 255; rgba[3] = 255; return 0;
	case HALO_PS2_FRAME_FX_CONTRAIL:        rgba[0] = 176; rgba[1] = 208; rgba[2] = 255; rgba[3] = 80;  return 0;
	case HALO_PS2_FRAME_FX_DECAL:           rgba[0] = 40;  rgba[1] = 32;  rgba[2] = 24;  rgba[3] = 112; return 0;
	default: return HCU_RENDER_CONTENT_E_ARGUMENT;
	}
}

/* ---- pin / unpin -------------------------------------------------------------------------------- */

const halo_ps2_frame_snapshot *hcu_render_objects_pin(hcu_render_objects_pin_t *pin,
	hcu_render_objects_counters *counters)
{
	if (!pin) return NULL;
	memset(pin, 0, sizeof *pin);
	pin->snapshot = hcu_snapshot_bank_begin_read(&pin->reader);
	if (!pin->snapshot) {
		if (counters) counters->pin_refusals++;
		return NULL;
	}
	pin->pinned = 1;
	if (counters) counters->pins++;
	return pin->snapshot;
}

void hcu_render_objects_unpin(hcu_render_objects_pin_t *pin, hcu_render_objects_counters *counters)
{
	if (!pin || !pin->pinned) return;
	hcu_snapshot_bank_end_read(&pin->reader);
	pin->pinned = 0;
	pin->snapshot = NULL;
	if (counters) counters->unpins++;
}

/* ---- parity ------------------------------------------------------------------------------------- */

int hcu_render_objects_parity(hcu_render_parity_log *log, uint32_t frame,
	const hcu_render_object_draw *draw, uint32_t count, hcu_render_objects_counters *counters)
{
	uint32_t i;
	if (!log || (!draw && count)) return HCU_RENDER_CONTENT_E_ARGUMENT;
	for (i = 0; i < count; i++) {
		hcu_render_parity_record rec;
		hcu_render_content_status st;
		rec.frame = frame;
		rec.view = draw[i].view;
		rec.kind = draw[i].type == HCU_OBJECTS_TYPE_VEHICLE ? HCU_RENDER_PARITY_VEHICLE
			: draw[i].type == HCU_OBJECTS_TYPE_WEAPON ? HCU_RENDER_PARITY_WEAPON
			: draw[i].type == HCU_OBJECTS_TYPE_EFFECT ? HCU_RENDER_PARITY_EFFECT
			: HCU_RENDER_PARITY_OBJECT;
		rec.surface_id = (int32_t)draw[i].definition_index;
		rec.material_id = -1;
		rec.resource_id = draw[i].resource_id;
		st = hcu_render_parity_log_append(log, &rec);
		if (st == HCU_RENDER_CONTENT_E_FULL) {
			if (counters) counters->parity_dropped++;
		} else if (st != HCU_RENDER_CONTENT_OK) {
			return st;
		}
	}
	return HCU_RENDER_CONTENT_OK;
}

/* ---- synthetic builder -------------------------------------------------------------------------- */

int hcu_render_synthetic_begin(halo_ps2_frame_snapshot *s, uint32_t map_generation,
	uint32_t frame_index, uint32_t view_count)
{
	if (!s || view_count == 0 || view_count > HALO_PS2_FRAME_MAX_VIEWS) return HCU_RENDER_CONTENT_E_ARGUMENT;
	memset(s, 0, sizeof *s);
	s->version = HALO_PS2_FRAME_SNAPSHOT_VERSION;
	s->map_generation = map_generation;
	s->frame_index = frame_index;
	s->view_count = (uint16_t)view_count;
	return HCU_RENDER_CONTENT_OK;
}

int hcu_render_synthetic_view(halo_ps2_frame_snapshot *s, uint32_t view,
	const halo_ps2_snapshot_camera *camera)
{
	halo_ps2_frame_view *v;
	if (!s || !camera || view >= s->view_count) return HCU_RENDER_CONTENT_E_ARGUMENT;
	if (view > 0 && !(s->views[view - 1].flags & HALO_PS2_FRAME_VIEW_ACTIVE)) return HCU_RENDER_CONTENT_E_STATE;
	v = &s->views[view];
	memset(v, 0, sizeof *v);
	v->flags = HALO_PS2_FRAME_VIEW_ACTIVE;
	v->player_index = (int8_t)view;
	v->camera = *camera;
	v->view_ref_first = s->view_ref_count;
	v->view_ref_count = 0;
	return HCU_RENDER_CONTENT_OK;
}

int hcu_render_synthetic_object_add(halo_ps2_frame_snapshot *s, uint32_t view,
	uint32_t object_index, const hcu_render_synthetic_object *o)
{
	halo_ps2_frame_view *v;
	halo_ps2_frame_object *fo = NULL;
	uint32_t i, res = 0xFFFFFFFFu;
	if (!s || !o || view >= s->view_count || object_index >= HALO_PS2_FRAME_MAX_OBJECTS) return HCU_RENDER_CONTENT_E_ARGUMENT;
	v = &s->views[view];
	if (!(v->flags & HALO_PS2_FRAME_VIEW_ACTIVE) || v->view_ref_first + v->view_ref_count != s->view_ref_count)
		return HCU_RENDER_CONTENT_E_STATE;
	if (o->palette_count && !o->palette) return HCU_RENDER_CONTENT_E_ARGUMENT;
	if (s->view_ref_count >= HALO_PS2_FRAME_MAX_VIEW_REFS) return HCU_RENDER_CONTENT_E_FULL;
	for (i = 0; i < s->resource_count; i++)
		if (s->resources[i].id == o->resource_id) { res = i; break; }
	if (res == 0xFFFFFFFFu) {
		if (s->resource_count >= HALO_PS2_FRAME_MAX_RESOURCES) return HCU_RENDER_CONTENT_E_FULL;
		res = s->resource_count++;
		s->resources[res].id = o->resource_id;
		s->resources[res].generation = s->map_generation;
	}
	/* Interned object: the first view that adds an index creates it; later views only reference it. */
	if (object_index < s->object_count) {
		fo = &s->objects[object_index];
		if (fo->id.index != object_index) return HCU_RENDER_CONTENT_E_STATE;
	} else {
		if (object_index != s->object_count) return HCU_RENDER_CONTENT_E_STATE;
		if (s->object_count >= HALO_PS2_FRAME_MAX_OBJECTS) return HCU_RENDER_CONTENT_E_FULL;
		if (s->palette_count + o->palette_count > HALO_PS2_FRAME_MAX_PALETTE) return HCU_RENDER_CONTENT_E_FULL;
		fo = &s->objects[object_index];
		memset(fo, 0, sizeof *fo);
		fo->id.index = object_index;
		fo->id.generation = 1u + object_index;
		fo->definition_index = o->definition_index;
		fo->type = (int16_t)o->type;
		fo->flags = o->flags;
		fo->resource_slot = (uint16_t)res;
		fo->palette_first = s->palette_count;
		fo->palette_count = o->palette_count;
		fo->world = o->world;
		for (i = 0; i < o->palette_count; i++) s->palette[s->palette_count + i] = o->palette[i];
		s->palette_count = (uint16_t)(s->palette_count + o->palette_count);
		s->object_count++;
	}
	s->view_refs[s->view_ref_count++] = (uint16_t)object_index;
	v->view_ref_count++;
	return HCU_RENDER_CONTENT_OK;
}

/* ==== EE adapter ================================================================================= */
void hcu_render_fx_corner_st(unsigned corner, float st[2])
{
	static const float uv[4][2] = { { 0.0f, 1.0f }, { 1.0f, 1.0f }, { 1.0f, 0.0f }, { 0.0f, 0.0f } };
	st[0] = uv[corner & 3u][0];
	st[1] = uv[corner & 3u][1];
}

uint32_t hcu_render_objects_fp_lod(int32_t view_w, int32_t view_h, int32_t screen_w, int32_t screen_h)
{
	/* A view at most a quarter of the frame (area test in 64-bit, so no overflow) draws the far level. */
	int64_t view_area, screen_area;
	if (view_w <= 0 || view_h <= 0 || screen_w <= 0 || screen_h <= 0) return HCU_OBJECTS_FP_LOD_NEAR;
	view_area = (int64_t)view_w * (int64_t)view_h;
	screen_area = (int64_t)screen_w * (int64_t)screen_h;
	return view_area * 4 <= screen_area ? HCU_OBJECTS_FP_LOD_FAR : HCU_OBJECTS_FP_LOD_NEAR;
}

#ifdef HCU_RENDER_OBJECTS_EE
#include "core/mat.h"
#include "platform/video.h"
#include "render/bsp_render.h"
#include "render/chain.h"
#include "render/clip.h"
#include "render/gs.h"
#include "render/decal_compose.h"
#include "render/upload.h"
#include "render/lodctl.h"
#include "render/obj_render.h"
#include "sim/skeleton.h"
#include "stream/sha256.h"
#include "stream/hcu_fx_bitmap.h"
#include "world/model.h"

/* The large converted palette pool lives in frame_scratch. Compact fixed records keep the cache bounded. */
typedef struct {
	uint32_t generation, resource_id, pose_hash;
	uint16_t slot, palette_first, palette_count;
	uint8_t valid, reserved;
	mat4 root;
} prepared_object;
typedef struct {
	uint32_t epoch;
	model_info info;
	uint16_t perm[OBJ_MAX_REGIONS];
	uint8_t valid, pad[3];
} prepared_slot;
typedef struct {
	uint32_t sequence, map_generation;
	uint8_t ready;
	uint8_t pad[3];
	prepared_object object[HALO_PS2_FRAME_MAX_OBJECTS];
	prepared_slot slot[HCU_OBJECTS_MAX_MODELS];
	mat4 palette[HALO_PS2_FRAME_MAX_PALETTE];
	uint8_t palette_ready[HALO_PS2_FRAME_MAX_PALETTE / 8u];
} prepared_cache;
_Static_assert(sizeof(prepared_cache) <= HCU_OBJECTS_PREPARE_CACHE_BYTES,
	"C3 prepared object cache exceeds its frame_scratch reservation");
static prepared_cache *s_prepared;
static uint32_t s_slot_epoch[HCU_OBJECTS_MAX_MODELS];
static hcu_object_prepare_stats s_prepare_stats;
void hcu_render_objects_prepare_cache_stats(hcu_object_prepare_stats *out) { if (out) *out = s_prepare_stats; }
static void prepared_invalidate_all(void)
{
	uint32_t i;
	if (s_prepared) {
		s_prepared->ready = 0u;
		for (i = 0; i < HCU_OBJECTS_MAX_MODELS; ++i) s_prepared->slot[i].valid = 0u;
	}
	for (i = 0; i < HCU_OBJECTS_MAX_MODELS; ++i)
		if (++s_slot_epoch[i] == 0u) ++s_slot_epoch[i];
}


#include "world/tex.h"
#include <math.h>

#define OBJ_ALIGN 64u
#define OBJ_READ_STEP 262144u
#define OBJ_BUDGET 2048u

typedef struct {
	const hcu_render_objects_table_entry *entry;
	model_section models;
	tex_section tex;
	int has_tex;
	uint32_t tex_base;
	tex_source_t src;
	int loaded;
	int refused;                 /* chunk missing or not matching the table: never loaded */
	uint32_t model_size, tex_size; /* chunk sizes from the profile directory (set at load) */
	uint32_t pool_off, pool_size; /* the entry's pool region while loaded */
	uint32_t last_used;          /* frame + 1 of the last frame that referenced it */
} obj_slot;

static obj_slot s_slots[HCU_OBJECTS_MAX_MODELS];
static hcu_render_objects_model s_meta[HCU_OBJECTS_MAX_MODELS];
static uint32_t s_slot_count;
/* C3.3: per-slot count of pinned-bank references (resource ids matched on the low 16 bits of source_datum,
 * as residency_frame does). Applied +1 when a pin is taken and -1 when it is dropped, against the same
 * immutable snapshot, so the counts balance; refused slots still count so the drop cannot leave a residue. */
static uint16_t s_slot_pins[HCU_OBJECTS_MAX_MODELS];
static uint8_t s_slot_rank[HCU_OBJECTS_MAX_MODELS];   /* C3.objects: this frame's residency rank (HCU_OBJECTS_RANK_UNUSED = not referenced) */
static hcu_render_objects_counters s_totals;
static hcu_render_drawn_identity_set s_drawn_identities;
static hcu_render_objects_pin_t s_pin;

static void slot_pins_apply(const halo_ps2_frame_snapshot *snap, int delta)
{
	uint32_t r, k;
	if (!snap) return;
	for (r = 0; r < snap->resource_count && r < HALO_PS2_FRAME_MAX_RESOURCES; r++)
		for (k = 0; k < s_slot_count; k++)
			if ((s_slots[k].entry->source_datum & 0xFFFFu) == snap->resources[r].id) {
				if (delta > 0) s_slot_pins[k]++;
				else if (s_slot_pins[k] > 0u) s_slot_pins[k]--;
			}
}

static void pin_drop(void)
{
	if (!s_pin.pinned) return;
	slot_pins_apply(s_pin.snapshot, -1);
	hcu_render_objects_unpin(&s_pin, &s_totals);
}

/* Residency pool: the render arena's rest, managed first-fit in 64-byte-aligned segments. Segments are kept
 * in offset order and cover the pool exactly; adjacent free segments merge on free. */
#define OBJ_SEG_MAX 256u
typedef struct { uint32_t off, size; uint8_t used; } obj_seg;
static uint8_t *s_pool;
static uint32_t s_pool_size;
static obj_seg s_segs[OBJ_SEG_MAX];
static uint32_t s_seg_count;
static hcu_render_objects_residency s_res;
static const hcu_asset_profile_view *s_profile;
static uint32_t s_bounds_map_generation;
static uint32_t s_tex_total;
static tex_source_t s_src_total;
static int s_installed;

static float hcu_render_object_bound_radius(const halo_ps2_frame_snapshot *snap,
	const halo_ps2_frame_object *object)
{
#ifdef HCU_RENDER_OBJECTS_EE
	uint32_t i, generation;
	float center[3], model_radius;
	const halo_ps2_frame_resource *resource;
	if (!snap || !object || object->type != HCU_OBJECTS_TYPE_SCENERY ||
		object->resource_slot >= snap->resource_count || object->resource_slot >= HALO_PS2_FRAME_MAX_RESOURCES)
		return object ? object->render_radius : 0.0f;
	resource = &snap->resources[object->resource_slot];
	for (i = 0; i < s_slot_count; ++i) {
		const hcu_render_objects_table_entry *entry = s_slots[i].entry;
		if (s_slots[i].refused || !entry || (entry->source_datum & 0xFFFFu) != resource->id) continue;
		if (!s_bounds_map_generation) s_bounds_map_generation = snap->map_generation;
		generation = resource->generation;
		if (hcu_render_model_bound_resolve(&entry->bounds, s_profile ? s_profile->profile_id : 0u,
			entry->source_datum, entry->model_chunk, entry->model_sha256, entry->tag_datum,
			s_bounds_map_generation, snap->map_generation, generation, center, &model_radius))
			return hcu_render_bounds_root_radius(object->render_radius, object->world.scale, center, model_radius);
		break;
	}
#else
	(void)snap;
#endif
	return object ? object->render_radius : 0.0f;
}

static hcu_render_objects_counters s_view_counters;
static uint32_t s_world_render_cycles, s_fp_render_cycles;
#if (defined(HALO_PS2_C3_LAG_TRACE) && HALO_PS2_C3_LAG_TRACE) || \
	(defined(HALO_PS2_C3_PERF_PROBE) && HALO_PS2_C3_PERF_PROBE)
static hcu_render_objects_timing_probe s_timing_probe;
#endif
static uint32_t s_pending_seq;
static uint32_t s_frame;
static hcu_render_object_draw s_draw[HCU_OBJECTS_MAX_DRAW];
static uint32_t s_draw_count;
static hcu_render_first_person_draw s_fp_draw[2];
static hcu_render_effect_draw s_fx[HCU_FX_MAX_PER_VIEW];
static uint32_t s_fx_count;
static uint32_t s_fp_draw_count;
static hcu_render_parity_record s_parity_store[HCU_OBJECTS_MAX_PARITY];
static hcu_render_parity_log s_parity;
static uint32_t s_view_triangles, s_view_skinned, s_view_drawn;
static const halo_ps2_frame_snapshot *s_snapshot;
static hcu_render_pose_tracker s_poses;
static uint32_t s_cur_view;
/* C3.6 sky: table index of the sky model entry (HCU_RENDER_OBJECTS_SKY_NONE = no sky) and its residency pin. */
static uint32_t s_sky_index = HCU_RENDER_OBJECTS_SKY_NONE;
static uint8_t s_sky_pinned;
static mat4 mat_from_snapshot(const halo_ps2_snapshot_matrix4x3 *w);
size_t hcu_render_objects_prepare_cache_bytes(void) { return HCU_OBJECTS_PREPARE_CACHE_BYTES; }
int hcu_render_objects_prepare_cache_bind(void *memory, size_t bytes)
{
	if (!memory || bytes < sizeof(prepared_cache) || ((uintptr_t)memory & 15u)) {
		s_prepared = NULL;
		return HCU_RENDER_CONTENT_E_ARGUMENT;
	}
	s_prepared = (prepared_cache *)memory;
	s_prepared->sequence = 0u;
	s_prepared->map_generation = 0u;
	s_prepared->ready = 0u;
	{
		uint32_t i;
		for (i = 0; i < HALO_PS2_FRAME_MAX_OBJECTS; ++i) s_prepared->object[i].valid = 0u;
		for (i = 0; i < HCU_OBJECTS_MAX_MODELS; ++i) s_prepared->slot[i].valid = 0u;
	}
	memset(s_prepared->palette_ready, 0, sizeof(s_prepared->palette_ready));
	memset(&s_prepare_stats, 0, sizeof(s_prepare_stats));
	return HCU_RENDER_CONTENT_OK;
}

static void prepare_snapshot(const halo_ps2_frame_snapshot *snap)
{
	uint32_t i;
	if (!HCU_C3_OBJECT_PREPARE_CACHE || !s_prepared || !snap) return;
	if (snap->object_count > HALO_PS2_FRAME_MAX_OBJECTS ||
		snap->resource_count > HALO_PS2_FRAME_MAX_RESOURCES ||
		snap->palette_count > HALO_PS2_FRAME_MAX_PALETTE ||
		snap->version != HALO_PS2_FRAME_SNAPSHOT_VERSION) {
		s_prepared->ready = 0u;
		return;
	}
	if (s_prepared->ready && s_prepared->sequence == snap->sequence && s_prepared->map_generation == snap->map_generation) return;
	{
		uint32_t k;
		for (k = 0; k < HALO_PS2_FRAME_MAX_OBJECTS; ++k) s_prepared->object[k].valid = 0u;
		for (k = 0; k < HCU_OBJECTS_MAX_MODELS; ++k) s_prepared->slot[k].valid = 0u;
	}
	memset(s_prepared->palette_ready, 0, sizeof(s_prepared->palette_ready));
	s_prepared->sequence = snap->sequence;
	s_prepared->map_generation = snap->map_generation;
	/* Model metadata/default permutations are shared by all objects using a resident slot. */
	for (i = 0; i < s_slot_count && i < HCU_OBJECTS_MAX_MODELS; ++i) {
		prepared_slot *p = &s_prepared->slot[i];
		if (!s_slots[i].loaded) continue;
		p->info = model_get(&s_slots[i].models, 0);
		if (p->info.region_count > OBJ_MAX_REGIONS) continue;
		memset(p->perm, 0, sizeof(p->perm));
		model_select_permutations(&s_slots[i].models, &p->info, NULL, p->perm);
		p->epoch = s_slot_epoch[i];
		p->valid = 1;
		s_prepare_stats.prepared_slots++;
	}
	for (i = 0; i < snap->object_count; ++i) {
		const halo_ps2_frame_object *o = &snap->objects[i];
		prepared_object *p = &s_prepared->object[i];
		const halo_ps2_frame_resource *r;
		int slot;
		uint32_t n, j, shared = HALO_PS2_FRAME_MAX_OBJECTS;
		if (o->resource_slot >= snap->resource_count) continue;
		r = &snap->resources[o->resource_slot];
		slot = hcu_render_objects_find_model(s_meta, s_slot_count, r->id);
		if (slot < 0 || !s_prepared->slot[slot].valid) continue;
		p->slot = (uint16_t)slot; p->resource_id = r->id; p->generation = o->id.generation;
		p->root = mat_from_snapshot(&o->world);
		p->pose_hash = 0u;
		p->palette_count = 0u;
		p->palette_first = o->palette_first;
		n = o->palette_count;
		if (n && hcu_render_objects_prepare_range_valid(o->palette_first, n, snap->palette_count)) {
			for (j = 0; j < i; ++j) {
				const halo_ps2_frame_object *prev = &snap->objects[j];
				if (prev->palette_first == o->palette_first && prev->palette_count == n &&
					s_prepared->object[j].valid && s_prepared->object[j].palette_count == n) { shared = j; break; }
			}
			if (shared < HALO_PS2_FRAME_MAX_OBJECTS) {
				p->palette_first = s_prepared->object[shared].palette_first;
				p->palette_count = (uint16_t)n;
				p->pose_hash = s_prepared->object[shared].pose_hash;
			} else {
				for (j = 0; j < n; ++j) {
					uint32_t pi = o->palette_first + j;
					uint8_t mask = (uint8_t)(1u << (pi & 7u));
					if (!(s_prepared->palette_ready[pi >> 3] & mask)) {
						s_prepared->palette[pi] = mat_from_snapshot(&snap->palette[pi]);
						s_prepared->palette_ready[pi >> 3] |= mask;
					}
				}
				p->palette_count = (uint16_t)n;
				p->pose_hash = hcu_render_objects_pose_hash(snap->palette, snap->palette_count,
					o->palette_first, o->palette_count);
			}
		}
		p->valid = 1;
		s_prepare_stats.prepared_objects++;
	}
	s_prepared->ready = 1u;
}

static int prepared_lookup(const halo_ps2_frame_snapshot *snap, uint32_t oi, uint32_t generation,
	uint32_t resource_id, int *slot, uint32_t *pose_hash)
{
	prepared_object *p;
	hcu_object_prepare_key key;
	if (!HCU_C3_OBJECT_PREPARE_CACHE || !s_prepared || !s_prepared->ready || !snap || !slot || !pose_hash ||
		oi >= HALO_PS2_FRAME_MAX_OBJECTS || s_prepared->sequence != snap->sequence ||
		s_prepared->map_generation != snap->map_generation) return 0;
	p = &s_prepared->object[oi];
	if (!p->valid || p->generation != generation || p->resource_id != resource_id ||
		p->slot >= HCU_OBJECTS_MAX_MODELS || !s_prepared->slot[p->slot].valid ||
		!s_slots[p->slot].loaded) return 0;
	key.sequence = s_prepared->sequence; key.map_generation = s_prepared->map_generation;
	key.object_generation = p->generation; key.resource_id = p->resource_id;
	key.slot_epoch = s_prepared->slot[p->slot].epoch;
	return hcu_render_objects_prepare_select(HCU_C3_OBJECT_PREPARE_CACHE, &key,
		snap->sequence, snap->map_generation, generation, resource_id,
		s_slot_epoch[p->slot], (int)p->slot, p->pose_hash, -1, 0u, slot, pose_hash);
}


static int read_verified(const hcu_asset_profile_view *view, uint32_t id, uint32_t size,
	uint8_t *dst, const uint8_t want[32]
#if defined(HALO_PS2_C3_LAG_TRACE) && HALO_PS2_C3_LAG_TRACE
	, uint32_t *read_cycles, uint32_t *hash_cycles
#endif
	)
{
	sha256_context s;
	uint8_t digest[32];
	uint32_t at = 0;
#if defined(HALO_PS2_C3_LAG_TRACE) && HALO_PS2_C3_LAG_TRACE
	uint32_t t = timer_cycles();
#endif
	while (at < size) {
		uint32_t n = size - at < OBJ_READ_STEP ? size - at : OBJ_READ_STEP;
		if (hcu_asset_profile_read_range(view, HCU_ASSET_CHUNK_MEDIA, id, at, dst + at, n) != 0) return -1;
		at += n;
	}
#if defined(HALO_PS2_C3_LAG_TRACE) && HALO_PS2_C3_LAG_TRACE
	if (read_cycles) *read_cycles = timer_cycles() - t;
	t = timer_cycles();
#endif
	sha256_init(&s);
	sha256_update(&s, dst, size);
	sha256_final(&s, digest);
#if defined(HALO_PS2_C3_LAG_TRACE) && HALO_PS2_C3_LAG_TRACE
	if (hash_cycles) *hash_cycles = timer_cycles() - t;
#endif
	return memcmp(digest, want, 32) ? -2 : 0;
}

#define OBJ_NONE 0xFFFFFFFFu

static int slot_binding(void *user, uint32_t shader_id, mat_binding_t *out);
static int slot_texture(void *user, int tex, tex_image_t *out);

static uint32_t obj_align(uint32_t n)
{
	return (n + OBJ_ALIGN - 1u) & ~(OBJ_ALIGN - 1u);
}

/* Chunk sizes come from the mounted profile directory. Keep the alignment and combined allocation arithmetic
 * checked before using either size for a pool allocation or a read into the pool. */
static int entry_need(const obj_slot *s, uint32_t *out)
{
	uint32_t model, texture;
	if (!s || !out || s->model_size > UINT32_MAX - (OBJ_ALIGN - 1u) ||
		s->tex_size > UINT32_MAX - (OBJ_ALIGN - 1u)) return -1;
	model = obj_align(s->model_size);
	texture = obj_align(s->tex_size);
	if (model > UINT32_MAX - texture) return -1;
	*out = model + texture;
	return 0;
}

/* Time-sliced verified read. After the opening frames a lazy load reads and hashes at most OBJ_LOAD_SLICE_BYTES per
 * frame into its reserved pool region and finishes once both chunks verify, so a first-use model costs several short
 * frames (the object appears late) instead of one hitch of the whole software SHA-256. One job runs at a time; a job
 * whose entry stops being requested is dropped. Host builds load synchronously. */
#ifdef HCU_RENDER_OBJECTS_EE
#define OBJ_LOAD_SLICE_BYTES 24576u
#else
#define OBJ_LOAD_SLICE_BYTES 0u
#endif
#define OBJ_SLICE_AFTER_FRAME 60u
#define OBJ_JOB_NONE 0xFFFFFFFFu
typedef struct {
	uint32_t entry, off, stage, at, last_frame, pump_frame;
	uint8_t tex_ok;
	sha256_context sha;
} obj_load_job;
static obj_load_job s_job = { OBJ_JOB_NONE, 0u, 0u, 0u, 0u, 0u, 0u };

static void pool_init(uint8_t *base, uint32_t size)
{
	s_job.entry = OBJ_JOB_NONE;
	s_pool = base;
	s_pool_size = size;
	s_segs[0].off = 0;
	s_segs[0].size = size;
	s_segs[0].used = 0;
	s_seg_count = size ? 1u : 0u;
	s_res.pool_bytes = size;
	s_res.pool_used = 0;
}

/* First free segment of at least n bytes, or -1. */
static int pool_find(uint32_t n)
{
	uint32_t i;
	for (i = 0; i < s_seg_count; i++)
		if (!s_segs[i].used && s_segs[i].size >= n) return (int)i;
	return -1;
}

static uint32_t pool_alloc(uint32_t n)
{
	int i = pool_find(n);
	obj_seg *g;
	if (i < 0) return OBJ_NONE;
	g = &s_segs[i];
	if (g->size > n) {
		uint32_t k;
		if (s_seg_count >= OBJ_SEG_MAX) return OBJ_NONE;
		for (k = s_seg_count; k > (uint32_t)i + 1u; k--) s_segs[k] = s_segs[k - 1u];
		s_seg_count++;
		s_segs[i + 1].off = g->off + n;
		s_segs[i + 1].size = g->size - n;
		s_segs[i + 1].used = 0;
		g->size = n;
	}
	g->used = 1;
	s_res.pool_used += n;
	if (s_res.pool_used > s_res.pool_used_peak) s_res.pool_used_peak = s_res.pool_used;
	return g->off;
}

static void pool_free(uint32_t off)
{
	uint32_t i;
	for (i = 0; i < s_seg_count; i++)
		if (s_segs[i].used && s_segs[i].off == off) break;
	if (i == s_seg_count) return;
	s_res.pool_used -= s_segs[i].size;
	s_segs[i].used = 0;
	if (i + 1u < s_seg_count && !s_segs[i + 1].used) {
		uint32_t k;
		s_segs[i].size += s_segs[i + 1].size;
		for (k = i + 1u; k + 1u < s_seg_count; k++) s_segs[k] = s_segs[k + 1u];
		s_seg_count--;
	}
	if (i > 0 && !s_segs[i - 1].used) {
		uint32_t k;
		s_segs[i - 1].size += s_segs[i].size;
		for (k = i; k + 1u < s_seg_count; k++) s_segs[k] = s_segs[k + 1u];
		s_seg_count--;
	}
}

/* Fence: the latest kick is complete (or there is none), so no in-flight chain reads the pool. Anything
 * else (pending, or not yet observed) blocks eviction. */
static int pool_fence_safe(void)
{
	uint32_t k = bsp_render_kick_seq();
	hcu_snapshot_bank_stats bank_stats;
	hcu_snapshot_bank_get_stats(&bank_stats);
	if (bank_stats.read_pins_active != 0u) return 0;
	if (k == 0u) return 1;
	return bsp_render_fence_observed(k) == 1;
}

/* Reads and checks one chunk's directory entry (size and hash) without reading its bytes. */
static int chunk_check(const hcu_asset_profile_view *view, uint32_t id, const uint8_t want[32], uint32_t *size)
{
	hcu_asset_chunk_view c;
	if (hcu_asset_profile_lookup(view, HCU_ASSET_CHUNK_MEDIA, id, &c) != 0) return -1;
	if (memcmp(c.sha256, want, 32)) return -2;
	*size = c.size;
	return 0;
}

/* Advances the sliced job by one frame's budget. Returns 1 when both chunks are read, 0 while more remain, -1 when the
 * model chunk fails to read or verify. A texture chunk that fails only clears tex_ok (the entry is drawn untextured). */
static int job_pump(const hcu_asset_profile_view *view, const obj_slot *s, const hcu_render_objects_table_entry *e,
	uint8_t *bytes, uint32_t model_span, uint32_t frame)
{
	uint32_t budget = OBJ_LOAD_SLICE_BYTES;
	if (s_job.pump_frame == frame + 1u) return 0;   /* one slice per frame, however often residency runs */
	s_job.pump_frame = frame + 1u;
	s_job.last_frame = frame;
	while (s_job.stage < 2u) {
		int tex = s_job.stage == 1u;
		uint32_t chunk = tex ? e->texture_chunk : e->model_chunk;
		uint32_t size = tex ? s->tex_size : s->model_size;
		uint8_t *dst = tex ? bytes + model_span : bytes;
		const uint8_t *want = tex ? e->texture_sha256 : e->model_sha256;
		uint8_t digest[32];
		int bad = 0;
		if (tex && !(e->texture_chunk && size)) { s_job.stage = 2u; break; }
		if (!s_job.at) sha256_init(&s_job.sha);
		while (s_job.at < size) {
			uint32_t n = size - s_job.at;
			if (!budget) return 0;
			if (n > budget) n = budget;
			if (hcu_asset_profile_read_range(view, HCU_ASSET_CHUNK_MEDIA, chunk, s_job.at, dst + s_job.at, n) != 0) {
				bad = 1;
				break;
			}
			sha256_update(&s_job.sha, dst + s_job.at, n);
			s_job.at += n;
			budget -= n;
		}
		if (!bad) {
			sha256_final(&s_job.sha, digest);
			bad = memcmp(digest, want, 32) != 0;
		}
		if (bad && !tex) return -1;
		if (tex) s_job.tex_ok = bad ? 0u : 1u;
		s_job.at = 0u;
		s_job.stage++;
	}
	return 1;
}

/* Loads entry i into a fresh pool region, reading and verifying its bytes. Returns 0, or -1 when the pool
 * has no room (the caller may evict), -2 when the entry itself is refused, or -3 while a sliced load is still
 * reading (its pool region stays reserved) and -4 when another entry's sliced load is running. */
static int entry_load(const hcu_asset_profile_view *view, uint32_t i, uint32_t frame)
{
	obj_slot *s = &s_slots[i];
	const hcu_render_objects_table_entry *e = s->entry;
	uint32_t need, model_span;
	uint32_t off;
	uint8_t *bytes;
	int pre_verified = 0, pre_tex_ok = 0;
#if defined(HALO_PS2_C3_LAG_TRACE) && HALO_PS2_C3_LAG_TRACE
	uint32_t trace_start = timer_cycles(), trace_model_read = 0, trace_model_hash = 0, trace_model_open = 0;
	uint32_t trace_tex_read = 0, trace_tex_hash = 0, trace_tex_open = 0;
#endif
	if (entry_need(s, &need) != 0) { s->refused = 1; s_res.entry_refusals++; return -2; }
	model_span = obj_align(s->model_size);
	if (OBJ_LOAD_SLICE_BYTES && frame > OBJ_SLICE_AFTER_FRAME) {
		int rc;
		if (s_job.entry != OBJ_JOB_NONE && s_job.entry != i) {
			if (frame <= s_job.last_frame + 2u) return -4;
			pool_free(s_job.off);                 /* the job's entry is no longer requested */
			s_job.entry = OBJ_JOB_NONE;
		}
		if (s_job.entry == OBJ_JOB_NONE) {
			off = pool_alloc(need);
			if (off == OBJ_NONE) return -1;
			s_job.entry = i;
			s_job.off = off;
			s_job.stage = 0u;
			s_job.at = 0u;
			s_job.pump_frame = 0u;
			s_job.tex_ok = 0u;
		}
		off = s_job.off;
		bytes = s_pool + off;
		rc = job_pump(view, s, e, bytes, model_span, frame);
		if (rc == 0) return -3;
		s_job.entry = OBJ_JOB_NONE;
		if (rc < 0) {
			pool_free(off);
			s->refused = 1;
			s_res.entry_refusals++;
			return -2;
		}
		pre_verified = 1;
		pre_tex_ok = s_job.tex_ok;
	} else {
		off = pool_alloc(need);
		if (off == OBJ_NONE) return -1;
		bytes = s_pool + off;
	}
#if defined(HALO_PS2_C3_LAG_TRACE) && HALO_PS2_C3_LAG_TRACE
	{
		int read_rc = pre_verified ? 0 : read_verified(view, e->model_chunk, s->model_size, bytes, e->model_sha256,
			&trace_model_read, &trace_model_hash);
		uint32_t t = timer_cycles();
		if (read_rc != 0 || model_open(&s->models, bytes, s->model_size) != MODEL_OK || model_get(&s->models, 0).node_count == 0) {
			trace_model_open = timer_cycles() - t;
			pool_free(off);
			s->refused = 1;
			s_res.entry_refusals++;
			if (s_lag_trace_events < HCU_C3_LAG_TRACE_EVENT_CAP) {
				s_lag_trace_events++;
				printf("HALO_PS2_LOCAL lag-load frame=%u entry=%u datum=%u model=%u texture=%u result=model-refused total-cycles=%u read-cycles=%u hash-cycles=%u open-cycles=%u pool=%u/%u\n",
				(unsigned)frame, (unsigned)i, (unsigned)e->source_datum, (unsigned)s->model_size, (unsigned)s->tex_size,
				(unsigned)(timer_cycles()-trace_start), (unsigned)trace_model_read, (unsigned)trace_model_hash, (unsigned)trace_model_open,
				(unsigned)s_res.pool_used, (unsigned)s_res.pool_bytes);
			}
			return -2;
		}
		trace_model_open = timer_cycles() - t;
	}
#else
	if ((!pre_verified && read_verified(view, e->model_chunk, s->model_size, bytes, e->model_sha256) != 0) ||
		model_open(&s->models, bytes, s->model_size) != MODEL_OK || model_get(&s->models, 0).node_count == 0) {
		pool_free(off);
		s->refused = 1;
		s_res.entry_refusals++;
		return -2;
	}
#endif
	s->has_tex = 0;
#if defined(HALO_PS2_C3_LAG_TRACE) && HALO_PS2_C3_LAG_TRACE
	if (e->texture_chunk && s->tex_size) {
		int read_rc = pre_verified ? (pre_tex_ok ? 0 : -2) : read_verified(view, e->texture_chunk, s->tex_size,
			bytes + model_span, e->texture_sha256, &trace_tex_read, &trace_tex_hash);
		if (read_rc == 0) {
			uint32_t t = timer_cycles();
			if (tex_open(&s->tex, bytes + model_span, s->tex_size) == TEX_OK) {
				trace_tex_open = timer_cycles() - t;
				if (s->tex.texture_count > HCU_OBJECTS_TEX_STRIDE) s_res.keys_refused++;
				else s->has_tex = 1;
			} else trace_tex_open = timer_cycles() - t;
		}
	}
#else
	if (e->texture_chunk && s->tex_size &&
		(pre_verified ? pre_tex_ok :
			read_verified(view, e->texture_chunk, s->tex_size, bytes + model_span, e->texture_sha256) == 0) &&
		tex_open(&s->tex, bytes + model_span, s->tex_size) == TEX_OK) {
		if (s->tex.texture_count > HCU_OBJECTS_TEX_STRIDE) {
			s_res.keys_refused++;      /* more textures than the entry's key stride: drawn flat */
		} else {
			s->has_tex = 1;
		}
	}
#endif
	s->pool_off = off;
	s->pool_size = need;
	s->tex_base = (uint32_t)(s - s_slots) * HCU_OBJECTS_TEX_STRIDE;
	s->src.binding = slot_binding;
	s->src.texture = slot_texture;
	s->src.lightmap = NULL;
	s->src.user = s;
	s->src.texture_count = s->has_tex ? s->tex.texture_count : 0;
	s->loaded = 1;
	if (++s_slot_epoch[i] == 0u) ++s_slot_epoch[i];
	if (s_prepared) { s_prepared->ready = 0u; s_prepared->slot[i].valid = 0u; }
	s->last_used = frame + 1u;
	s_meta[i].resource_id = e->source_datum & 0xFFFFu; /* CE model.index: low 16 bits of the tag datum */
	s_meta[i].source_datum = e->source_datum;
	s_meta[i].model_bytes = s->model_size;
	s_meta[i].texture_count = (uint16_t)(s->has_tex ? s->tex.texture_count : 0);
	s_meta[i].node_count = (uint16_t)model_get(&s->models, 0).node_count;
	s_meta[i].loaded = 1;
#if defined(HALO_PS2_C3_LAG_TRACE) && HALO_PS2_C3_LAG_TRACE
	if (s_lag_trace_events < HCU_C3_LAG_TRACE_EVENT_CAP) {
		s_lag_trace_events++;
		printf("HALO_PS2_LOCAL lag-load frame=%u entry=%u datum=%u model=%u texture=%u result=resident model-read-cycles=%u model-hash-cycles=%u model-open-cycles=%u texture-read-cycles=%u texture-hash-cycles=%u texture-open-cycles=%u total-cycles=%u pool=%u/%u nodes=%u textures=%u\n",
		(unsigned)frame, (unsigned)i, (unsigned)e->source_datum, (unsigned)s->model_size, (unsigned)s->tex_size,
		(unsigned)trace_model_read, (unsigned)trace_model_hash, (unsigned)trace_model_open,
		(unsigned)trace_tex_read, (unsigned)trace_tex_hash, (unsigned)trace_tex_open,
		(unsigned)(timer_cycles()-trace_start), (unsigned)s_res.pool_used, (unsigned)s_res.pool_bytes,
		(unsigned)s_meta[i].node_count, (unsigned)s_meta[i].texture_count);
	}
#endif
	s_res.loads++;
	s_res.resident++;
	if (s->has_tex) s_res.keys_used += s->tex.texture_count;
	return 0;
}

static void entry_evict(uint32_t i)
{
	obj_slot *s = &s_slots[i];
	pool_free(s->pool_off);
	s->loaded = 0;
	if (++s_slot_epoch[i] == 0u) ++s_slot_epoch[i];
	if (s_prepared) { s_prepared->ready = 0u; s_prepared->slot[i].valid = 0u; }
	s->has_tex = 0;
	s_meta[i].loaded = 0;
	s_res.evictions++;
	s_res.resident--;
}

/* Makes entry i resident for this frame: loads it when the pool has room, otherwise evicts the least recently
 * used entries that this frame does not reference, and only while the fence is clear. */
static void entry_request(const hcu_asset_profile_view *view, uint32_t i, uint32_t frame, uint32_t rank)
{
	obj_slot *s = &s_slots[i];
	uint32_t need;
	int safe = -1;
	if (s->loaded) { s->last_used = frame + 1u; s_res.hits++; return; }
	if (s->refused) { s_res.misses++; return; }
	if (entry_need(s, &need) != 0) { s->refused = 1; s_res.entry_refusals++; s_res.misses++; return; }
	if (s_job.entry == i) {                       /* its sliced load already owns a pool region */
		if (entry_load(view, i, frame) != 0) s_res.misses++;
		return;
	}
	if (s_job.entry != OBJ_JOB_NONE && frame <= s_job.last_frame + 2u) { s_res.misses++; return; }   /* one sliced load at a time */
	if (!hcu_render_objects_pool_request_fits(need, s_res.pool_bytes)) {
		s_res.pool_refusals++;
		s_res.misses++;
		return;
	}
	for (;;) {
		if (pool_find(need) >= 0) {
			if (entry_load(view, i, frame) == 0) return;
			break;
		}
		if (safe < 0) safe = pool_fence_safe();
		if (!safe) { s_res.fence_blocked++; break; }
		{
			/* Evict only when the victims can make room: free bytes plus every eligible victim must cover the request,
			 * so a request that cannot fit never costs a resident entry a reload. */
			uint32_t v, reclaim = s_res.pool_bytes - s_res.pool_used, dummy = 0;
			for (v = 0; v < s_slot_count; v++)
				if (hcu_render_objects_residency_rank_victim_ok(s_slots[v].loaded, s_slot_rank[v], rank, safe,
					s_slot_pins[v], &dummy)) reclaim += s_slots[v].pool_size;
			if (reclaim < need) { s_res.pool_refusals++; break; }
		}
		{
			uint32_t v, best = OBJ_NONE;
			for (v = 0; v < s_slot_count; v++)
				if (hcu_render_objects_residency_rank_victim_ok(s_slots[v].loaded, s_slot_rank[v], rank, safe,
					s_slot_pins[v], &s_res.evict_refused_pinned) &&
					(best == OBJ_NONE || s_slot_rank[v] > s_slot_rank[best] ||
					 (s_slot_rank[v] == s_slot_rank[best] && s_slots[v].last_used < s_slots[best].last_used))) best = v;
			if (best == OBJ_NONE) { s_res.pool_refusals++; break; }
			entry_evict(best);
		}
	}
	s_res.misses++;
}

/* Frame begin: every entry the snapshot's visible views reference is made resident before the views draw. */
static void residency_frame(const halo_ps2_frame_snapshot *snap, uint32_t frame,
	uint32_t layout_view_count, int32_t screen_w, int32_t screen_h)
{
	static uint8_t need[HCU_OBJECTS_MAX_MODELS];
	static uint8_t priority[HCU_OBJECTS_MAX_MODELS];
	uint32_t v, ref, i, p;
	if (!snap || !s_pool) return;
	hcu_render_object_frustums_prepare_admission(snap, layout_view_count, screen_w, screen_h);
	memset(need, 0, sizeof need);
	memset(priority, 0xFF, sizeof priority);
	for (v = 0; v < snap->view_count && v < HALO_PS2_FRAME_MAX_VIEWS; v++) {
		const halo_ps2_frame_view *fv = &snap->views[v];
		const hcu_render_objects_frustum *frustum = &s_view_frustums[v];
		uint16_t first_person_slots[2];
		unsigned fp;
		if (!(fv->flags & HALO_PS2_FRAME_VIEW_ACTIVE)) continue;
		first_person_slots[0] = fv->first_person_weapon_resource_slot;
		first_person_slots[1] = fv->first_person_hands_resource_slot;
		if (fv->flags & HALO_PS2_FRAME_VIEW_FIRST_PERSON)
			for (fp = 0; fp < 2u; fp++) {
				uint32_t rid, k;
				if (first_person_slots[fp] >= snap->resource_count) continue;
				rid = snap->resources[first_person_slots[fp]].id;
				for (k = 0; k < s_slot_count; k++)
					if (!s_slots[k].refused &&
						(s_slots[k].entry->source_datum & 0xFFFFu) == rid) {
						need[k] = 1;
						priority[k] = 0u;
						break;
					}
			}
		for (ref = fv->view_ref_first; ref < fv->view_ref_first + fv->view_ref_count && ref < snap->view_ref_count; ref++) {
			uint32_t oi = snap->view_refs[ref];
			uint32_t rid, k, rank;
			if (oi >= snap->object_count) continue;
			if (!hcu_render_objects_object_visible_with_frustum(snap, fv, oi, frustum)) continue;
			if (snap->objects[oi].resource_slot >= snap->resource_count) continue;
			rid = snap->resources[snap->objects[oi].resource_slot].id;
			rank = hcu_render_objects_residency_priority(snap->objects[oi].type);
			for (k = 0; k < s_slot_count; k++)
				if (!s_slots[k].refused && (s_slots[k].entry->source_datum & 0xFFFFu) == rid) {
					need[k] = 1;
					if (rank < priority[k]) priority[k] = (uint8_t)rank;
					break;
				}
		}
	}
	/* Ranks before any eviction: an entry is displaced only by a strictly more important request. */
	for (i = 0; i < s_slot_count; i++)
		s_slot_rank[i] = need[i] ? priority[i] : HCU_OBJECTS_RANK_UNUSED;
	/* Mark what this frame uses before any eviction, so a referenced entry is never the victim. */
	for (i = 0; i < s_slot_count; i++)
		if (need[i] && s_slots[i].loaded) s_slots[i].last_used = frame + 1u;
	/* Resolve shared resources at their most important visible type, then admit by that priority. */
	for (p = 0; p <= 3u; p++)
		for (i = 0; i < s_slot_count; i++)
			if (need[i] && priority[i] == p) entry_request(s_profile, i, frame, p);
}

/* ---- texture binding (same mapping as hcu_render_media.c, global texture index) ---------------- */
static int slot_binding(void *user, uint32_t shader_id, mat_binding_t *out)
{
	obj_slot *s = user;
	tex_binding b;
	if (!s->has_tex || !tex_find_binding(&s->tex, shader_id, &b)) { s_view_counters.texture_misses++; return -1; }
	out->tex = b.texture == TEX_NONE ? (int16_t)-1 : (int16_t)(s->tex_base + b.texture);
	out->flags = 0;
	out->pad = 0;
	if (b.flags & TEX_B_ALPHA_TEST) out->flags |= MAT_ALPHA_TEST;
	if (b.blend >= TEX_BLEND_ALPHA) out->flags |= MAT_BLEND;
	if (b.flags & TEX_B_TWO_SIDED) out->flags |= MAT_TWO_SIDED;
	out->uv_scale[0] = b.uv_scale[0];
	out->uv_scale[1] = b.uv_scale[1];
	if (out->tex < 0) s_view_counters.texture_misses++;
	return out->tex < 0 ? -1 : 0;
}

static int slot_texture(void *user, int tex, tex_image_t *out)
{
	obj_slot *s = user;
	tex_info t;
	tex_mip_view mv;
	int64_t local = (int64_t)tex - (int64_t)s->tex_base;
	if (!s->has_tex || local < 0 || (uint64_t)local >= s->tex.texture_count) { s_view_counters.texture_misses++; return -1; }
	t = tex_get(&s->tex, (uint32_t)local);
	if (!tex_mip(&s->tex, &t, 0, &mv)) { s_view_counters.texture_misses++; return -1; }
	out->pixels = mv.pixels;
	out->pixel_bytes = mv.bytes;
	out->clut = tex_clut(&s->tex, &t);
	out->clut_bytes = (uint32_t)t.clut_entries * 4u;
	out->w = t.width;
	out->h = t.height;
	out->psm = t.psm;
	s_view_counters.texture_hits++;
	return 0;
}

/* ---- matrices ----------------------------------------------------------------------------------- */
/* Same basis mapping as hcu_render_snapshot_matrix_from_ce: forward/left/up scaled, position last. */
static mat4 mat_from_snapshot(const halo_ps2_snapshot_matrix4x3 *w)
{
	mat4 m;
	hcu_render_objects_prepare_matrix(w, &m.m[0][0]);
	return m;
}

/* ---- pose: the CE-published palette (or the placement for unskinned objects); no ANIM sampling ---- */
static const halo_ps2_frame_snapshot *s_pose_snapshot;
/* The view camera of the first-person pass (camera-local palettes map through it). */
static const halo_ps2_snapshot_camera *s_fp_cam;
/* First-person detail of the view being drawn. The FP pass is one object, so its LOD is the engine's bias on
 * the object's pick: level 0 adds no bias (LOD0 slots 0..1), level 4 adds 2 (far slots 2..4). */
static uint32_t s_view_fp_lod = HCU_OBJECTS_FP_LOD_NEAR;
static lodctl_t s_fp_lodctl;

/* Level 2 is the first lodctl setting with a one-step model bias. Compensate
 * its distance scale so this detail change does not shorten weapon visibility. */
static lodctl_t s_ground_weapon_lodctl = { 0.0f, 0.0f, 2, 0, 0, 0, 0u, 0u };

#if defined(HALO_PS2_C3_MOVEMENT_TRACE)
static uint16_t s_fp_pose_diag_first[2];
static unsigned s_fp_pose_diag_count;
static unsigned s_fp_view_diag_done;

static void fp_view_diagnostic(const render_ctx_t *rc)
{
	unsigned i;
	if (s_fp_view_diag_done || !rc || !rc->cam || !rc->clip) return;
	s_fp_view_diag_done = 1u;
	printf("HALO_PS2_FPVIEW view=%u viewport=%d,%d,%d,%d pos=%.9g,%.9g,%.9g yaw=%.9g pitch=%.9g hfov=%.9g aspect=%.9g near=%.9g far=%.9g\n",
		(unsigned)s_cur_view, rc->viewport_x, rc->viewport_y, rc->viewport_w, rc->viewport_h,
		rc->cam->pos[0], rc->cam->pos[1], rc->cam->pos[2], rc->cam->yaw, rc->cam->pitch,
		rc->cam->hfov, rc->cam->aspect, rc->cam->near_z, rc->cam->far_z);
	for (i = 0; i < 4u; ++i)
		printf("HALO_PS2_FPCLIP view=%u row=%u %.9g %.9g %.9g %.9g\n", (unsigned)s_cur_view, i,
		rc->clip[i][0], rc->clip[i][1], rc->clip[i][2], rc->clip[i][3]);
}

static void fp_pose_diagnostic(const hcu_render_object_draw *draw, const object_nodes_t *nodes,
	unsigned count)
{
	unsigned i;
	if (!draw || !nodes || !(draw->flags & HCU_OBJECTS_FLAG_CAMERA_LOCAL) || s_fp_pose_diag_count >= 2u)
		return;
	for (i = 0; i < s_fp_pose_diag_count; ++i)
		if (s_fp_pose_diag_first[i] == draw->palette_first)
			return;
	s_fp_pose_diag_first[s_fp_pose_diag_count++] = draw->palette_first;
	printf("HALO_PS2_FPPOSE parent model=%u resource=%u palette_first=%u palette_count=%u nodes=%u\n",
		(unsigned)draw->slot, (unsigned)draw->resource_id, (unsigned)draw->palette_first,
		(unsigned)draw->palette_count, count);
	for (i = 0; i < count; ++i) {
		const mat4 *w = &nodes->world[i];
		const mat4 *s = &nodes->skin[i];
		printf("HALO_PS2_FPPOSE parent_node model=%u i=%u worldP %.9g %.9g %.9g skinF %.9g %.9g %.9g L %.9g %.9g %.9g U %.9g %.9g %.9g P %.9g %.9g %.9g\n",
			(unsigned)draw->slot, i, w->m[3][0], w->m[3][1], w->m[3][2],
			s->m[0][0], s->m[0][1], s->m[0][2],
			s->m[1][0], s->m[1][1], s->m[1][2],
			s->m[2][0], s->m[2][1], s->m[2][2],
			s->m[3][0], s->m[3][1], s->m[3][2]);
	}
}
#endif

static int pose_fn(void *user, const object_t *ob, object_nodes_t *out)
{
	const hcu_render_object_draw *d = user;
	const obj_slot *s = &s_slots[d->slot];
	unsigned n, i;
	model_info mi;
	mat4 root = ob->root;
	const prepared_object *prepared = NULL;
	if (!s->loaded || !s_pose_snapshot) return 0;
	if (!(d->flags & HCU_OBJECTS_FLAG_CAMERA_LOCAL) && HCU_C3_OBJECT_PREPARE_CACHE && s_prepared && s_prepared->ready &&
		d->object_index < HALO_PS2_FRAME_MAX_OBJECTS && s_prepared->sequence == s_pose_snapshot->sequence &&
		s_prepared->map_generation == s_pose_snapshot->map_generation &&
		s_prepared->object[d->object_index].valid && s_prepared->object[d->object_index].palette_count == d->palette_count &&
		s_prepared->object[d->object_index].generation == d->generation &&
		s_prepared->object[d->object_index].resource_id == d->resource_id &&
		s_prepared->object[d->object_index].slot == d->slot &&
		s_prepared->slot[d->slot].valid && s_prepared->slot[d->slot].epoch == s_slot_epoch[d->slot]) {
		prepared = &s_prepared->object[d->object_index];
		mi = s_prepared->slot[d->slot].info;
	} else mi = model_get(&s->models, 0);
	n = mi.node_count;
	if (n == 0 || n > SKEL_MAX_NODES) return 0;
	if (d->palette_count) {
		if (d->palette_count < n || !s_pose_snapshot) return 0;
		if (prepared) {
			/* The cache holds converted CE pose matrices. Keep world[] in that
			 * bind-space world form for markers/attachments; skin[] is derived
			 * below with this model's own default inverse bind. */
			memcpy(out->world, &s_prepared->palette[prepared->palette_first], n * sizeof(mat4));
			memcpy(out->skin, &s_prepared->palette[prepared->palette_first], n * sizeof(mat4));
		} else {
			for (i = 0; i < n; i++) {
				const halo_ps2_snapshot_matrix4x3 *src = &s_pose_snapshot->palette[d->palette_first + i];
				if (d->flags & HCU_OBJECTS_FLAG_CAMERA_LOCAL) {
					halo_ps2_snapshot_matrix4x3 w;
					if (!s_fp_cam || hcu_render_first_person_world(s_fp_cam, src, &w) != 0) return 0;
					src = &w;
				}
				out->world[i] = mat_from_snapshot(src);
				out->skin[i] = out->world[i];
			}
		}
		/* CE's render_model applies runtime_default_inverse_matrix to every
		 * posed node. MODL vertices are in bind pose, so do the same for every
		 * object palette, including world vehicles and bipeds. Camera-local
		 * FP needs the same model-specific transform after camera composition.
		 * Preserve world[] for marker and attachment transforms; reuse skin[] as
		 * bind-world scratch to keep the workspace bounded. */
		{
			skel_xform bind[SKEL_MAX_NODES];
			int16_t parent[SKEL_MAX_NODES];
			mat4 identity, inverse;
			for (i = 0; i < n; i++) {
				model_node node = model_get_node(&s->models, &mi, i);
				memcpy(bind[i].rot, node.rotation, sizeof bind[i].rot);
				memcpy(bind[i].trans, node.translation, sizeof bind[i].trans);
				bind[i].scale = node.scale;
				parent[i] = node.parent;
			}
			mat4_identity(&identity);
			if (skel_world(out->skin, bind, parent, n, &identity) != 0) return 0;
			for (i = 0; i < n; i++) {
				mat4_rigid_inverse(&inverse, &out->skin[i]);
				mat4_mul(&out->skin[i], &inverse, &out->world[i]);
			}
#if defined(HALO_PS2_C3_MOVEMENT_TRACE)
			if (d->flags & HCU_OBJECTS_FLAG_CAMERA_LOCAL)
				fp_pose_diagnostic(d, out, n);
#endif
		}
		s_view_skinned += n;
	} else {
		for (i = 0; i < n; i++) { out->skin[i] = root; out->world[i] = root; }
	}
	out->count = n;
	return 1;
}

/* ---- the object pass ----------------------------------------------------------------------------- */
static obj_render_t s_objr;

/* C3.6 parity identities: one record per model part of the permutations this draw uses (LOD 0 of each
 * region's permutation). surface_id = the part's index in the model's part table, material_id = its
 * Xbox shader tag id (the key of the OTEX binding), resource_id = the MODL chunk id. Frame 0 only. */
static void log_part_parity(const obj_slot *s, const model_info *mi, const uint16_t *perm,
	uint32_t resource_id, uint32_t kind)
{
	uint32_t region;
	if (s_frame || !s_parity.records) return;
	for (region = 0; region < mi->region_count && region < OBJ_MAX_REGIONS; region++) {
		model_part_range pr = model_parts(&s->models, mi, perm[region], 0);
		uint32_t p;
		for (p = pr.first_part; p < (uint32_t)pr.first_part + pr.part_count; p++) {
			model_part part = model_get_part(&s->models, p);
			hcu_render_parity_record rec;
			if (s_parity.count >= s_parity.capacity) { s_view_counters.parity_dropped++; return; }
			rec.frame = s_frame;
			rec.view = s_cur_view;
			rec.kind = kind;
			rec.surface_id = (int32_t)p;
			rec.material_id = (int32_t)part.shader_id;
			rec.resource_id = resource_id;
			if (hcu_render_parity_log_append(&s_parity, &rec) == HCU_RENDER_CONTENT_OK) s_view_counters.parts_logged++;
		}
	}
}

/* C3.6 per-frame identity: one fold per drawn item, at its draw point. Frame-scoped (reset in frame begin). */
static hcu_render_parity_frame s_frame_parity;
static void frame_identity_add(uint32_t kind, int32_t surface_id, uint32_t resource_id)
{
	hcu_render_parity_record rec;
	rec.frame = s_frame;
	rec.view = s_cur_view;
	rec.kind = kind;
	rec.surface_id = surface_id;
	rec.material_id = -1;
	rec.resource_id = resource_id;
	(void)hcu_render_parity_frame_add(&s_frame_parity, &rec);
}

/* ---- C3.6(c) effect and decal quads (EE) ----------------------------------------------------------
 * Every admitted quad of a view goes into one GIF packet (PRIM triangle, alpha blend, depth test GEQUAL,
 * no depth write). The packet is preceded by one A+D state chunk. Quads are clipped on the EE with the
 * same planes as the BSP and packed with clip_pack_vertex, like the sky. Admission is decided before any
 * byte is written: a quad that does not fit the chain is counted in fx_skipped_space and skipped. */
#define FX_STATE_QW 5u        /* VIF header + GIF tag (AD) + three A+D pairs */
#define FX_BLEND_STATE_QW 3u  /* VIF header + GIF tag + one A+D pair */
#define FX_BLEND_RESTORE_RESERVE_QW (1u + FX_BLEND_STATE_QW) /* CNT tag + blend-state data */
#define FX_PACKET_HDR_QW 2u   /* VIF header + GIF tag */

static hcu_render_fx_quad s_fxq[HCU_FX_MAX_PER_VIEW];
static uint32_t s_fxn[HCU_FX_MAX_PER_VIEW];        /* clipped vertices of an admitted quad (0 = not admitted) */

/* C3.6(c) textured fx inputs, set once by the parent: bindings, the profile their chunks come from, and the
 * staging buffer one BITM chunk is read into. The bytes are copied into the renderer's ring by the call. */
static const hcu_bitmap_binding *s_fx_bind;
static uint32_t s_fx_bind_count;
static const hcu_asset_profile_view *s_fx_profile;
static void *s_fx_staging;
static uint32_t s_fx_staging_bytes;
static hcu_fx_descriptor_cache *s_fx_descriptors;
static uint32_t s_fx_descriptor_profile_id, s_fx_descriptor_map_generation;
static uint8_t s_fx_descriptor_epoch_valid;

int hcu_render_objects_bind_fx_descriptor_cache(void *storage, uint32_t storage_bytes)
{
	if (!storage || storage_bytes < sizeof(hcu_fx_descriptor_cache)) {
		s_fx_descriptors = NULL;
		return -1;
	}
	s_fx_descriptors = (hcu_fx_descriptor_cache *)storage;
	memset(s_fx_descriptors, 0, sizeof *s_fx_descriptors);
	s_fx_descriptor_epoch_valid = 0u;
	return 0;
}

/* A texture whose source attempt failed (cache refusal or unreadable source) is not read from the package again for a few frames: the source
 * read costs far more than the check it precedes, and it would repeat every frame while the cache stays full. */
#define FX_BACKOFF_SLOTS 32u
#define FX_BACKOFF_FRAMES 8u
static struct { uint32_t bind, until; } s_fx_backoff[FX_BACKOFF_SLOTS];
static unsigned s_fx_backoff_next;

static int fx_backoff_active(uint32_t bind)
{
	unsigned i;
	for (i = 0; i < FX_BACKOFF_SLOTS; i++)
		if (s_fx_backoff[i].bind == bind && s_fx_backoff[i].until > s_frame) return 1;
	return 0;
}

static void fx_backoff_set(uint32_t bind, int on)
{
	unsigned i;
	for (i = 0; i < FX_BACKOFF_SLOTS; i++)
		if (s_fx_backoff[i].bind == bind && s_fx_backoff[i].until) {
			s_fx_backoff[i].until = on ? s_frame + FX_BACKOFF_FRAMES : 0u;
			return;
		}
	if (!on) return;
	s_fx_backoff[s_fx_backoff_next % FX_BACKOFF_SLOTS].bind = bind;
	s_fx_backoff[s_fx_backoff_next % FX_BACKOFF_SLOTS].until = s_frame + FX_BACKOFF_FRAMES;
	s_fx_backoff_next++;
}

void hcu_render_objects_set_fx_bindings(const hcu_bitmap_binding *bindings, uint32_t count,
	const hcu_asset_profile_view *profile, void *staging, uint32_t staging_bytes)
{
	if (s_fx_bind != bindings || s_fx_profile != profile) {
		if (s_fx_descriptors) memset(s_fx_descriptors, 0, sizeof *s_fx_descriptors);
		s_fx_descriptor_epoch_valid = 0u;
	}
	s_fx_bind = bindings; s_fx_bind_count = count; s_fx_profile = profile;
	s_fx_staging = staging; s_fx_staging_bytes = staging_bytes;
}

/* Per-view scratch (fixed, no heap): admitted quad indices and their bindings, the buckets, and per bucket
 * the TEX0 and whether its texture is resident. */
static uint32_t s_fx_cidx[HCU_FX_MAX_PER_VIEW];
static uint32_t s_fx_cbind[HCU_FX_MAX_PER_VIEW];
static uint16_t s_fx_order[HCU_FX_MAX_PER_VIEW];
static hcu_fx_bucket s_fx_bucket[HCU_FX_BUCKET_CAP];
static uint64_t s_fx_tex0[HCU_FX_BUCKET_CAP];
static uint8_t s_fx_bucket_ok[HCU_FX_BUCKET_CAP];
static uint8_t s_fx_blend[HCU_FX_MAX_PER_VIEW], s_fx_fade[HCU_FX_MAX_PER_VIEW];
static uint8_t s_fx_textured[HCU_FX_MAX_PER_VIEW];
/* Inline upload copies this staging palette into the fenced upload chain before returning. */
static uint32_t s_decal_clut_stage[256] __attribute__((aligned(64)));
static void fx_decal_colour(const hcu_render_effect_draw *e, uint8_t rgba[4]);

/* Keep enough room inside the active geometry bound for the final blend-state CNT. CLOSE is deliberately
 * refused: the FX pass is a producer and must not consume the frame's physical-capacity closing scope. */
static int fx_chain_reserve_blend_restore(chain_t *c, uint32_t *saved_limit,
	uint32_t *saved_hud_limit, uint32_t *saved_scope)
{
	uint32_t *active_limit;
	if (!c || !saved_limit || !saved_hud_limit || !saved_scope) return 0;
	*saved_limit = c->limit; *saved_hud_limit = c->hud_limit; *saved_scope = c->scope;
	if (c->scope == CHAIN_SCOPE_GENERAL) active_limit = &c->limit;
	else if (c->scope == CHAIN_SCOPE_HUD) active_limit = &c->hud_limit;
	else return 0;
	if (*active_limit < c->qw || *active_limit - c->qw < FX_BLEND_RESTORE_RESERVE_QW) return 0;
	*active_limit -= FX_BLEND_RESTORE_RESERVE_QW;
	return 1;
}

static void fx_chain_restore_bounds(chain_t *c, uint32_t limit, uint32_t hud_limit, uint32_t scope)
{
	c->limit = limit; c->hud_limit = hud_limit; c->scope = scope;
}

/* Reads one binding's BITM image. The bytes point into the staging buffer and are valid until the next call.
 * Same checks as hcu_bitmap_dispatch_request: identity, chunk digest, format, power-of-two size, mip 0. */
static int fx_source(const hcu_bitmap_binding *b, bsp_fx_tex_src *out)
{
	hcu_asset_chunk_view cv;
	tex_section section;
	tex_info image;
	tex_mip_view mip;
	if (!s_fx_profile || !s_fx_staging || !b || b->image_index != 0u) return -1;
	if (hcu_asset_profile_lookup(s_fx_profile, HCU_ASSET_CHUNK_MEDIA, b->chunk_id, &cv) != HCU_ASSET_PROFILE_OK ||
		cv.size > s_fx_staging_bytes || memcmp(cv.sha256, b->expected_chunk_sha256, 32)) return -1;
	s_view_counters.fx_source_read_bytes += cv.size;
	/* s_fx_staging is disposable, so the single-pass staged read applies (one read and one hash per byte). */
	if (hcu_asset_profile_read_chunk_staged(s_fx_profile, HCU_ASSET_CHUNK_MEDIA, b->chunk_id,
		s_fx_staging, s_fx_staging_bytes) != HCU_ASSET_PROFILE_OK) return -1;
	if (tex_open(&section, (const uint8_t *)s_fx_staging, cv.size) != TEX_OK ||
		b->image_index >= section.texture_count) return -1;
	image = tex_get(&section, b->image_index);
	if (image.source_id != b->expected_source_datum) return -1;
	if ((image.psm != GS_PSMT8 && image.psm != GS_PSMT4) || !image.width || !image.height ||
		image.width > 256u || image.height > 256u) return -1;
	if (!tex_mip(&section, &image, 0, &mip)) return -1;
	out->clut = tex_clut(&section, &image);
	if (!out->clut) return -1;
	out->pixels = mip.pixels; out->pixel_bytes = mip.bytes;
	out->clut_bytes = (uint32_t)image.clut_entries * 4u;
	out->w = image.width; out->h = image.height; out->psm = image.psm;
	return 0;
}

static int fx_resident_query(void *context, uint32_t cache_key, uint16_t width,
	uint16_t height, uint8_t psm, uint64_t *tex0_out)
{
	int st;
	(void)context;
	st = bsp_render_fx_texture_resident(cache_key, width, height, psm, tex0_out);
	if (st == BSP_FX_TEX_OK) s_view_counters.fx_resident_hits++;
	else if (st == BSP_FX_TEX_MISS) s_view_counters.fx_resident_misses++;
	return st == BSP_FX_TEX_MISS ? HCU_FX_RESIDENT_MISS : st;
}

static int fx_source_load(void *context, const hcu_bitmap_binding *binding,
	uint16_t *width, uint16_t *height, uint8_t *psm)
{
	bsp_fx_tex_src *src = (bsp_fx_tex_src *)context;
	if (!src || !width || !height || !psm || fx_source(binding, src) != 0) return BSP_FX_TEX_NO_SOURCE;
	*width = src->w; *height = src->h; *psm = src->psm;
	return 0;
}

static uint8_t s_fx_submit_blend;
static int fx_source_submit(void *context, const hcu_bitmap_binding *binding,
	uint16_t width, uint16_t height, uint8_t psm, uint64_t *tex0_out)
{
	bsp_fx_tex_src *src = (bsp_fx_tex_src *)context;
	if (!src || !binding || !tex0_out || width != src->w || height != src->h || psm != src->psm)
		return BSP_FX_TEX_NO_SOURCE;
	/* The converter keeps an arbitrary colour in the transparent palette entries. Alpha blending hides it, but add
	 * and subtract ignore texel alpha, so every transparent texel would add that colour and show the whole sprite
	 * rectangle. Multiply decals (blend 1, 2) need the colour untouched. */
	if (s_fx_submit_blend != 1u && s_fx_submit_blend != 2u && src->clut) {
		uint32_t *clut = (uint32_t *)(uintptr_t)src->clut;
		uint32_t n = src->clut_bytes / 4u, e;
		if (n > 256u) n = 256u;
		for (e = 0; e < n; e++) if ((clut[e] >> 24) == 0u) clut[e] = 0u;
	}
	return bsp_render_fx_texture(binding->cache_key, src, tex0_out);
}

/* A decal composes three palettes from its source CLUT on every frame it is drawn, and fx_source reads and
 * hash-verifies the whole bitmap chunk. Keep the verified CLUT and size of each decal bitmap so that read happens
 * once per bitmap, not once per decal per frame. Entries are keyed by chunk id and the chunk's expected hash. */
#define FX_DECAL_SRC_SLOTS 16u
typedef struct {
	uint8_t sha[32];
	uint32_t chunk_id, clut_bytes;
	uint16_t w, h;
	uint8_t used;
	uint8_t clut[1024];
} fx_decal_src_slot;
static fx_decal_src_slot s_decal_src[FX_DECAL_SRC_SLOTS];
static unsigned s_decal_src_next;

static const fx_decal_src_slot *fx_decal_source_cached(const hcu_bitmap_binding *b)
{
	bsp_fx_tex_src src;
	fx_decal_src_slot *slot;
	unsigned i;
	for (i = 0; i < FX_DECAL_SRC_SLOTS; i++)
		if (s_decal_src[i].used && s_decal_src[i].chunk_id == b->chunk_id &&
			!memcmp(s_decal_src[i].sha, b->expected_chunk_sha256, 32)) return &s_decal_src[i];
	if (fx_source(b, &src) != 0 || !src.clut || src.clut_bytes > sizeof slot->clut) return NULL;
	slot = &s_decal_src[s_decal_src_next++ % FX_DECAL_SRC_SLOTS];
	memcpy(slot->sha, b->expected_chunk_sha256, 32);
	memcpy(slot->clut, src.clut, src.clut_bytes);
	slot->chunk_id = b->chunk_id;
	slot->clut_bytes = src.clut_bytes;
	slot->w = src.w;
	slot->h = src.h;
	slot->used = 1u;
	return slot;
}

static int fx_decal_channel_textures(render_ctx_t *rc, const hcu_bitmap_binding *binding,
	const hcu_render_effect_draw *effect, uint64_t base_tex0, uint64_t out_tex0[3],
	uint16_t *width, uint16_t *height)
{
	const fx_decal_src_slot *src;
	uint8_t rgba[4];
	uint8_t opacity;
	unsigned channel, entries;
	if (!rc || !rc->chain || !binding || !effect || !base_tex0 || !out_tex0 ||
		!width || !height || !(src = fx_decal_source_cached(binding))) return 0;
	if (!chain_has_space(rc->chain, 3u * 76u)) return 0;
	*width = src->w; *height = src->h;
	entries = src->clut_bytes / 4u;
	if (entries > 256u) entries = 256u;
	fx_decal_colour(effect, rgba);
	{
		float source_intensity = effect->decal_intensity * 255.0f;
		unsigned intensity_byte;
		if (!(source_intensity > 0.0f)) intensity_byte = 0u;
		else if (source_intensity >= 255.0f) intensity_byte = 255u;
		else intensity_byte = (unsigned)(source_intensity + 0.5f);
		opacity = (uint8_t)(((unsigned)rgba[3] * intensity_byte + 127u) >> 8);
	}
	for (channel = 0; channel < 3u; ++channel) {
		uint32_t block = rc->decal_clut_block[channel];
		if (decal_compose_build_palette(s_decal_clut_stage, src->clut, entries, channel,
			rgba[channel], opacity, effect->framebuffer_blend_function == 2u) != 0 ||
			!decal_compose_emit_palette(rc->chain, s_decal_clut_stage, block, 0u)) return 0;
		out_tex0[channel] = (base_tex0 & ~((uint64_t)0x3fffu << 37)) |
			((uint64_t)(block & 0x3fffu) << 37) | (1ull << 61);
	}
	return 1;
}

/* Clips the quad's two triangles and returns the fan vertex count. When `out` is non-NULL the fans are packed
 * there (12 words per vertex) and `out` is not advanced; the caller advances it by 12 * the returned count.
 * `textured` sets the ST of each corner (hcu_render_fx_corner_st); flat quads carry zero ST. */
static uint32_t fx_quad_clip(const render_ctx_t *rc, const hcu_render_fx_quad *q,
	const hcu_render_effect_draw *effect, const uint8_t rgba[4],
	const uint8_t rgba_end[4],
	const clip_gs *g, int textured, int scratch_uv, int tile_x, int tile_y, uint32_t *out)
{
	static const int tri[2][3] = { { 0, 1, 2 }, { 0, 2, 3 } };
	uint32_t total = 0;
	int t, k, j;
	for (t = 0; t < 2; t++) {
		cvert in[3], poly[CLIP_MAX_VERTS];
		int cnt;
		for (k = 0; k < 3; k++) {
			clip_project(rc->clip, q->v[tri[t][k]], &in[k]);
			for (j = 0; j < CLIP_ATTRS; j++) in[k].a[j] = 0.0f;
			if (textured && scratch_uv && effect && effect->kind == HALO_PS2_FRAME_FX_DECAL) {
				float px = (float)rc->viewport_x + (float)rc->viewport_w * 0.5f +
					g->sx * (in[k].c[0] / in[k].c[3]);
				float py = (float)rc->viewport_y + (float)rc->viewport_h * 0.5f +
					g->sy * (in[k].c[1] / in[k].c[3]);
				in[k].a[0] = (px - (float)tile_x) / (float)DECAL_COMPOSE_W;
				in[k].a[1] = (py - (float)tile_y) / (float)DECAL_COMPOSE_H;
			} else if (textured && effect && effect->kind == HALO_PS2_FRAME_FX_DECAL &&
				(effect->flags & HALO_PS2_FRAME_FX_NATIVE_GEOMETRY) && effect->native_geometry) {
				const halo_ps2_frame_fx_geometry_vertex *v = &effect->native_geometry[tri[t][k]];
				in[k].a[0] = v->uv[0];
				in[k].a[1] = v->uv[1];
			} else if (textured && effect && (effect->kind == HALO_PS2_FRAME_FX_PARTICLE ||
				effect->kind == HALO_PS2_FRAME_FX_CONTRAIL)) {
				unsigned corner = (unsigned)tri[t][k];
				float u0 = effect->sprite_uv[0], u1 = effect->sprite_uv[1];
				float v0 = effect->sprite_uv[2], v1 = effect->sprite_uv[3];
				if (effect->kind == HALO_PS2_FRAME_FX_PARTICLE && effect->bitmap_width) {
					/* Atlas sprites sit edge to edge, and the GS filters bilinearly: sampling exactly on the
					 * sprite rectangle pulls in the neighbouring sprite and draws an outline around the quad.
					 * Pull the sampled rectangle in by half a texel of the converted (half-resolution) bitmap. */
					float d = 1.0f / (float)effect->bitmap_width, eu = (u1 - u0) * 0.25f, ev = (v1 - v0) * 0.25f;
					if (d > eu) d = eu;
					u0 += d; u1 -= d;
					if (d > ev) d = ev;
					v0 += d; v1 -= d;
				}
				in[k].a[0] = (corner == 0u || corner == 3u) ? u0 : u1;
				in[k].a[1] = (corner < 2u) ? v1 : v0;
			} else if (textured) hcu_render_fx_corner_st((unsigned)tri[t][k], &in[k].a[0]);
			{
				const uint8_t *vertex_rgba = rgba_end && tri[t][k] >= 2 ? rgba_end : rgba;
				in[k].a[4] = vertex_rgba[0]; in[k].a[5] = vertex_rgba[1];
				in[k].a[6] = vertex_rgba[2]; in[k].a[7] = vertex_rgba[3];
			}
		}
		cnt = clip_polygon(in, rc->cam->near_z, poly);
		if (cnt < 3) continue;
		for (j = 1; j + 1 < cnt; j++) {
			if (out) {
				clip_pack_vertex(&poly[0], 0, g, out); out += 12;
				clip_pack_vertex(&poly[j], 0, g, out); out += 12;
				clip_pack_vertex(&poly[j + 1], 0, g, out); out += 12;
			}
			total += 3;
		}
	}
	return total;
}

static int fx_decal_one_tile(const render_ctx_t *rc, const hcu_render_fx_quad *q,
	const clip_gs *g, int *tile_x0, int *tile_y0, int *tile_x1, int *tile_y1)
{
	static const int tri[2][3] = { { 0, 1, 2 }, { 0, 2, 3 } };
	float minx = 1e30f, miny = 1e30f, maxx = -1e30f, maxy = -1e30f;
	int t, tx0, tx1, ty0, ty1;
	if (!rc || !q || !g || !tile_x0 || !tile_y0 || !tile_x1 || !tile_y1) return 0;
	for (t = 0; t < 2; ++t) {
		cvert in[3], poly[CLIP_MAX_VERTS];
		int k, n, j;
		for (k = 0; k < 3; ++k) clip_project(rc->clip, q->v[tri[t][k]], &in[k]);
		n = clip_polygon(in, rc->cam->near_z, poly);
		for (j = 0; j < n; ++j) {
			float x = (float)rc->viewport_x + (float)rc->viewport_w * 0.5f +
				g->sx * (poly[j].c[0] / poly[j].c[3]);
			float y = (float)rc->viewport_y + (float)rc->viewport_h * 0.5f +
				g->sy * (poly[j].c[1] / poly[j].c[3]);
			if (x < minx) minx = x;
			if (x > maxx) maxx = x;
			if (y < miny) miny = y;
			if (y > maxy) maxy = y;
		}
	}
	if (maxx < (float)rc->viewport_x || maxy < (float)rc->viewport_y ||
		minx >= (float)(rc->viewport_x + rc->viewport_w) ||
		miny >= (float)(rc->viewport_y + rc->viewport_h)) return 0;
	if (minx < (float)rc->viewport_x) minx = (float)rc->viewport_x;
	if (miny < (float)rc->viewport_y) miny = (float)rc->viewport_y;
	if (maxx >= VIDEO_WIDTH) maxx = (float)VIDEO_WIDTH - 1.0f;
	if (maxy >= VIDEO_HEIGHT) maxy = (float)VIDEO_HEIGHT - 1.0f;
	if (maxx >= (float)(rc->viewport_x + rc->viewport_w))
		maxx = (float)(rc->viewport_x + rc->viewport_w - 1);
	if (maxy >= (float)(rc->viewport_y + rc->viewport_h))
		maxy = (float)(rc->viewport_y + rc->viewport_h - 1);
	tx0 = (int)minx / (int)DECAL_COMPOSE_W; tx1 = (int)maxx / (int)DECAL_COMPOSE_W;
	ty0 = (int)miny / (int)DECAL_COMPOSE_H; ty1 = (int)maxy / (int)DECAL_COMPOSE_H;
	*tile_x0 = tx0 * (int)DECAL_COMPOSE_W; *tile_y0 = ty0 * (int)DECAL_COMPOSE_H;
	*tile_x1 = tx1 * (int)DECAL_COMPOSE_W; *tile_y1 = ty1 * (int)DECAL_COMPOSE_H;
	return 1;
}

static int fx_decal_emit_poly(render_ctx_t *rc, const hcu_render_fx_quad *quad,
	const hcu_render_effect_draw *effect, const clip_gs *g, uint64_t tex0,
	uint16_t tex_w, uint16_t tex_h, int scratch_uv, int tile_x, int tile_y, u64 pending)
{
	static const uint8_t white[4] = { 255, 255, 255, 128 };
	uint32_t nv, *w, *pw;
	u64 *q;
	if (!rc || !quad || !effect || !g || !tex0) return 0;
	nv = fx_quad_clip(rc, quad, effect, white, NULL, g, 1, scratch_uv, tile_x, tile_y, NULL);
	if (!nv || !chain_has_space(rc->chain, FX_PACKET_HDR_QW + 3u * nv)) return 0;
	w = chain_cnt(rc->chain, FX_PACKET_HDR_QW + 3u * nv, pending);
	if (!w) return 0;
	w[0] = VIF_CODE(VIF_NOP, 0, 0); w[1] = VIF_CODE(VIF_NOP, 0, 0);
	w[2] = VIF_CODE(VIF_FLUSHA, 0, 0); w[3] = VIF_CODE(VIF_DIRECT, 0, 1u + 3u * nv);
	q = (u64 *)(w + 4);
	q[0] = GIF_TAG(nv, 1, 1, GS_PRIM(GSX_PRIM_TRIANGLE, 1, 1, 0, 0, 0, 0, 0, 0), GIFX_FLG_PACKED, 3);
	q[1] = 0x412u;
	pw = (uint32_t *)(q + 2);
	if (fx_quad_clip(rc, quad, effect, white, NULL, g, 1, scratch_uv, tile_x, tile_y, pw) != nv)
		return 0;
	(void)tex_w; (void)tex_h;
	return 1;
}

static uint64_t fx_decal_frame(uint32_t page, uint32_t fbw, uint32_t psm, uint32_t fbmask)
{
	return (uint64_t)page | (uint64_t)fbw << 16 | (uint64_t)psm << 24 | (uint64_t)fbmask << 32;
}

static uint64_t fx_decal_xyoffset(const render_ctx_t *rc, int tile_local, int tile_x, int tile_y)
{
	int x = (2048 - rc->viewport_x) * 16 - rc->viewport_w * 8;
	int y = (2048 - rc->viewport_y) * 16 - rc->viewport_h * 8;
	if (tile_local) { x += tile_x * 16; y += tile_y * 16; }
	return (uint64_t)(uint16_t)x | (uint64_t)(uint16_t)y << 32;
}

static uint64_t fx_decal_scissor(const render_ctx_t *rc, int tile_local)
{
	if (tile_local) return (63ull << 16) | (31ull << 48);
	return (uint64_t)rc->viewport_x | (uint64_t)(rc->viewport_x + rc->viewport_w - 1) << 16 |
		(uint64_t)rc->viewport_y << 32 | (uint64_t)(rc->viewport_y + rc->viewport_h - 1) << 48;
}

static int fx_decal_state(render_ctx_t *rc, const hcu_render_effect_draw *effect,
	const clip_gs *g, int tile_x, int tile_y, int scratch_target, unsigned channel,
	uint64_t tex0, uint16_t tex_w, uint16_t tex_h)
{
	gs_ad ad[12];
	uint32_t mask = 0;
	uint32_t frame_page, fbw, psm, zpage;
	int tile_local = scratch_target;
	unsigned n = 0;
	(void)g;
	if (scratch_target) {
		frame_page = rc->decal_color_page; fbw = 1; psm = GS_PSMCT32;
		zpage = rc->decal_z_page; mask = 0x00ffffffu;
	} else {
		frame_page = rc->framebuffer_page; fbw = rc->framebuffer_width / 64u; psm = rc->framebuffer_psm;
		zpage = rc->zbuffer_page;
		if (decal_compose_ct16_frame_mask(channel, &mask) != 0) return 0;
	}
	if (!tex0 || !fbw || psm != (scratch_target ? GS_PSMCT32 : GS_PSMCT16S)) return 0;
	ad[n++] = (gs_ad){ fx_decal_frame(frame_page, fbw, psm, mask), DECAL_GS_A_FRAME_1 };
	ad[n++] = (gs_ad){ GS_ZBUF(zpage, GS_PSMZ24, 1u), DECAL_GS_A_ZBUF_1 };
	ad[n++] = (gs_ad){ GS_TEST(0u, 1u, 0u, 0u, 0u, 0u, 1u, 2u), DECAL_GS_A_TEST_1 };
	ad[n++] = (gs_ad){ scratch_target ? GS_ALPHA(0u, 1u, 0u, 1u, 0u) :
		GS_ALPHA(0u, 2u, 0u, 2u, 0u), DECAL_GS_A_ALPHA_1 };
	ad[n++] = (gs_ad){ fx_decal_xyoffset(rc, tile_local, tile_x, tile_y), DECAL_GS_A_XYOFFSET_1 };
	ad[n++] = (gs_ad){ fx_decal_scissor(rc, tile_local), DECAL_GS_A_SCISSOR_1 };
	ad[n++] = (gs_ad){ 0u, DECAL_GS_A_TEXFLUSH };
	ad[n++] = (gs_ad){ tex0, DECAL_GS_A_TEX0_1 };
	ad[n++] = (gs_ad){ GS_TEX1(1u, 0u, 0u, 0u, 0u, 0u, 0u), 0x14u };
	ad[n++] = (gs_ad){ GS_CLAMP(1u, 1u, 0u, tex_w ? tex_w - 1u : 0u, 0u, tex_h ? tex_h - 1u : 0u), DECAL_GS_A_CLAMP_1 };
	ad[n++] = (gs_ad){ 0x80ull | (0x80ull << 32), DECAL_GS_A_TEXA };
	ad[n++] = (gs_ad){ 0u, DECAL_GS_A_FBA_1 };
	return decal_compose_emit_ad(rc->chain, ad, n, 0);
}

static int fx_decal_composite_tile(render_ctx_t *rc, const hcu_render_effect_draw *effect,
	const hcu_render_fx_quad *quad, const clip_gs *g, const uint64_t variants[3],
	uint16_t decal_w, uint16_t decal_h, uint32_t tile_x, uint32_t tile_y, u64 pending)
{
	gs_ad zcopy[5], copy_state[12], restore[11];
	uint64_t copy_sprite[14], sample_tex0;
	uint32_t nv, fbw, tex_tbp;
	unsigned channel;
	if (!rc || !effect || !quad || !g || rc->framebuffer_psm != GS_PSMCT16S ||
		rc->framebuffer_width != VIDEO_WIDTH || rc->framebuffer_height != VIDEO_HEIGHT ||
		!rc->decal_color_page || !rc->decal_z_page) return 0;
	nv = fx_quad_clip(rc, quad, effect, (const uint8_t[4]){255,255,255,128}, NULL,
		g, 1, 0, 0, 0, NULL);
	if (!nv || !chain_has_space(rc->chain, 151u + 18u * nv)) return 0;
	/* Copy the matching 24-bit reverse-Z tile into its one-page scratch target. */
	if (decal_compose_copy_packet(zcopy, rc->zbuffer_page * 32u, rc->decal_z_page * 32u,
		rc->framebuffer_width / 64u, 1u, GS_PSMZ24, GS_PSMZ24,
		tile_x, tile_y, 0u, 0u, DECAL_COMPOSE_W, DECAL_COMPOSE_H) != 0 ||
		decal_compose_copy_frame_state(copy_state, rc->decal_color_page, rc->decal_z_page,
		rc->framebuffer_page, rc->framebuffer_width, tile_x, tile_y) != 0 ||
		decal_compose_sprite_packet(copy_sprite, tile_x << 4, tile_y << 4,
			(tile_x + DECAL_COMPOSE_W) << 4, (tile_y + DECAL_COMPOSE_H) << 4,
			0u, 0u, DECAL_COMPOSE_W << 4, DECAL_COMPOSE_H << 4,
			128u, 128u, 128u, 128u, 0u) != 0) return 0;
	if (!decal_compose_emit_ad(rc->chain, zcopy, 5u, pending) ||
		!decal_compose_emit_ad(rc->chain, copy_state, 12u, 0u) ||
		!decal_compose_emit_sprite(rc->chain, copy_sprite, 0u)) return 0;
	/* Build and execute three alpha-mask/product passes against the saved destination color. */
	tex_tbp = rc->decal_color_page * 32u;
	sample_tex0 = GS_TEX0(tex_tbp, 1u, GS_PSMCT32, 6u, 5u, 1u, 1u, 0u,
		GS_PSMCT32, 0u, 0u, 0u);
	for (channel = 0; channel < 3u; ++channel) {
		if (!fx_decal_state(rc, effect, g, (int)tile_x, (int)tile_y, 1, channel,
			variants[channel], decal_w, decal_h) ||
			!fx_decal_emit_poly(rc, quad, effect, g, variants[channel], decal_w, decal_h,
				0, (int)tile_x, (int)tile_y, 0u)) return 0;
		if (!fx_decal_state(rc, effect, g, (int)tile_x, (int)tile_y, 0, channel,
			sample_tex0, DECAL_COMPOSE_W, DECAL_COMPOSE_H) ||
			!fx_decal_emit_poly(rc, quad, effect, g, sample_tex0, DECAL_COMPOSE_W,
				DECAL_COMPOSE_H, 1, (int)tile_x, (int)tile_y, 0u)) return 0;
	}
	/* Canonical state restore for subsequent FX/overlay draws; texture state has no CPU shadow in BSP. */
	fbw = rc->framebuffer_width / 64u;
	if (decal_compose_restore_state(restore,
		fx_decal_frame(rc->framebuffer_page, fbw, GS_PSMCT16S, 0u), 1u,
		GS_ZBUF(rc->zbuffer_page, GS_PSMZ24, 1u),
		GS_TEST(0u, 6u, 0x40u, 0u, 0u, 0u, 1u, 2u), GS_ALPHA(0u, 1u, 0u, 1u, 0u),
		fx_decal_xyoffset(rc, 0, 0, 0), fx_decal_scissor(rc, 0),
		0x80ull | (0x80ull << 32), GS_CLAMP(1u, 1u, 0u, 0u, 0u, 0u), 0u,
		GS_TEX1(1u, 0u, 0u, 0u, 0u, 0u, 0u)) != 0 ||
		!decal_compose_emit_ad(rc->chain, restore, 11u, 0u)) return 0;
	return 1;
}

static int fx_decal_composite_one(render_ctx_t *rc, const hcu_render_effect_draw *effect,
	const hcu_bitmap_binding *binding, const hcu_render_fx_quad *quad, const clip_gs *g,
	uint64_t base_tex0, u64 pending)
{
	uint64_t variants[3];
	uint16_t decal_w, decal_h;
	uint32_t nv, tiles_x, tiles_y, tile_count, per_tile;
	int x0, y0, x1, y1, x, y;
	if (!rc || !effect || !binding || !quad || !g ||
		!fx_decal_one_tile(rc, quad, g, &x0, &y0, &x1, &y1)) return 0;
	tiles_x = (uint32_t)(x1 - x0) / DECAL_COMPOSE_W + 1u;
	tiles_y = (uint32_t)(y1 - y0) / DECAL_COMPOSE_H + 1u;
	if (tiles_x > 8u || tiles_y > 14u) return 0;
	tile_count = tiles_x * tiles_y;
	nv = fx_quad_clip(rc, quad, effect, (const uint8_t[4]){255,255,255,128}, NULL,
		g, 1, 0, 0, 0, NULL);
	per_tile = 165u + 18u * nv;
	if (!nv || !chain_has_space(rc->chain, 3u * 76u + tile_count * per_tile)) return 0;
	if (!fx_decal_channel_textures(rc, binding, effect, base_tex0, variants, &decal_w, &decal_h)) return 0;
	for (y = y0; y <= y1; y += (int)DECAL_COMPOSE_H)
		for (x = x0; x <= x1; x += (int)DECAL_COMPOSE_W)
			if (!fx_decal_composite_tile(rc, effect, quad, g, variants, decal_w, decal_h,
				(uint32_t)x, (uint32_t)y, pending)) return 0;
	return 1;
}

/* Textured bucket state: TEX0 (the bucket's texture), TEX1 (bilinear, fixed LOD), CLAMP. Five qwords. */
static void fx_tex_state(chain_t *c, uint64_t tex0, u64 pending, int repeat_uv)
{
	u32 *w = chain_cnt(c, FX_STATE_QW, pending);
	u64 *q;
	if (!w) return;
	w[0] = VIF_CODE(VIF_NOP, 0, 0); w[1] = VIF_CODE(VIF_NOP, 0, 0);
	w[2] = VIF_CODE(VIF_FLUSHA, 0, 0); w[3] = VIF_CODE(VIF_DIRECT, 0, 1 + 3);
	q = (u64 *)(w + 4);
	q[0] = GIF_TAG(3, 1, 0, 0, GIFX_FLG_PACKED, 1); q[1] = GIF_REGS_AD;
	q[2] = tex0;                                    q[3] = GS_A_TEX0_1;
	q[4] = GS_TEX1(1, 0, 1, 1, 0, 0, 0);            q[5] = GS_A_TEX1_1;
	q[6] = GS_CLAMP(repeat_uv ? 0 : 1, repeat_uv ? 0 : 1, 0, 0, 0, 0); q[7] = GS_A_CLAMP_1;
}

/* CE transparent shader mode stays separate from framebuffer fade mode.
 * Alpha, add, and alpha-multiply-add have verified GS mappings. Subtract is exact
 * (Cd - Cs*As). The GS has no per-component min/max, so those two are counted
 * approximations: min darkens the destination by source alpha, max adds. Multiply and
 * double-multiply need the decal composite path; elsewhere they stay alpha. */
static int fx_blend_state(chain_t *c, uint8_t ce_blend)
{
	u64 alpha = GS_ALPHA(0, 1, 0, 1, 0);
	u32 *w;
	u64 *q;
	if (ce_blend == 3u) alpha = GS_ALPHA(0, 2, 2, 1, 128);
	else if (ce_blend == 7u) alpha = GS_ALPHA(2, 1, 0, 1, 0);
	else if (ce_blend == 4u) alpha = GS_ALPHA(2, 0, 0, 1, 0);
	else if (ce_blend == 5u) alpha = GS_ALPHA(2, 1, 0, 1, 0);
	else if (ce_blend == 6u) alpha = GS_ALPHA(0, 2, 2, 1, 128);
	w = chain_cnt(c, FX_BLEND_STATE_QW, 0);
	if (!w) return 0;
	w[0] = VIF_CODE(VIF_NOP, 0, 0); w[1] = VIF_CODE(VIF_NOP, 0, 0);
	w[2] = VIF_CODE(VIF_FLUSHA, 0, 0); w[3] = VIF_CODE(VIF_DIRECT, 0, 1 + 1);
	q = (u64 *)(w + 4);
	q[0] = GIF_TAG(1, 1, 0, 0, GIFX_FLG_PACKED, 1); q[1] = GIF_REGS_AD;
	q[2] = alpha; q[3] = GS_A_ALPHA_1;
	return 1;
}

/* Build the live CE particle sprite from its selected atlas rectangle and
 * particle-definition orientation. Return 1 when CE's LOD cutoff rejects it. */
static int fx_particle_quad(const render_ctx_t *rc, const hcu_render_effect_draw *e,
	const float billboard_right[3], const float billboard_up[3], hcu_render_fx_quad *q)
{
	(void)billboard_right; (void)billboard_up;
	if (!rc || !s_snapshot || s_cur_view >= s_snapshot->view_count) return -1;
	return hcu_render_fx_particle_build_quad(e,
		&s_snapshot->views[s_cur_view].camera, rc->viewport_h, q);
}

static int fx_native_decal_quad(const hcu_render_effect_draw *e, hcu_render_fx_quad *q)
{
	unsigned i;
	if (!e || !q || !s_snapshot ||
		!(e->flags & HALO_PS2_FRAME_FX_NATIVE_GEOMETRY) || !e->native_geometry)
		return -1;
	for (i = 0; i < 4u; i++) {
		const halo_ps2_frame_fx_geometry_vertex *v = &e->native_geometry[i];
		memcpy(q->v[i], v->position, sizeof q->v[i]);
	}
	q->resource_id = e->resource_id;
	q->kind = HALO_PS2_FRAME_FX_DECAL;
	return 0;
}

static void fx_particle_colour(const hcu_render_effect_draw *e, uint8_t rgba[4])
{
	float fade = 1.0f, remaining = e->lifespan_sec - e->age_sec;
	float alpha;
	int i;
	if (e->fade_in_sec > 0.0f && e->age_sec < e->fade_in_sec) fade = e->age_sec / e->fade_in_sec;
	if (e->fade_out_sec > 0.0f && remaining < e->fade_out_sec) fade *= remaining / e->fade_out_sec;
	for (i = 0; i < 3; i++) {
		float c = e->color_argb[i + 1] * 255.0f;
		if (!(c > 0.0f)) c = 0.0f;
		if (c > 255.0f) c = 255.0f;
		rgba[i] = (uint8_t)c;
	}
	alpha = (e->framebuffer_blend_function != 0u && !(e->particle_shader_flags & 1u)) ? 255.0f :
		e->color_argb[0] * 255.0f;
	alpha *= fade;
	if (!(alpha > 0.0f)) alpha = 0.0f;
	if (alpha > 255.0f) alpha = 255.0f;
	rgba[3] = (uint8_t)alpha;
}

static void fx_decal_colour(const hcu_render_effect_draw *e, uint8_t rgba[4])
{
	static const unsigned source_channel[4] = { 1u, 2u, 3u, 0u };
	unsigned i;
	for (i = 0; i < 4u; i++) {
		float value = e->color_argb[source_channel[i]] * 255.0f;
		if (!(value > 0.0f)) value = 0.0f;
		if (value > 255.0f) value = 255.0f;
		rgba[i] = (uint8_t)value;
	}
}

static void fx_contrail_colour(const hcu_render_effect_draw *e,
	const halo_ps2_snapshot_camera *camera, uint8_t start[4], uint8_t end[4])
{
	const float *colors[2] = { e->color_argb, e->segment_end_color_argb };
	float tangent[3], eye[3], normal[3], length, fade = 1.0f;
	unsigned endpoint, channel, k;
	for (k = 0; k < 3; ++k) {
		tangent[k] = e->forward[k] - e->position[k];
		eye[k] = camera->position[k] - e->position[k];
	}
	length = fx_len(tangent);
	if (length > 1e-6f) for (k = 0; k < 3; ++k) tangent[k] /= length;
	if (e->framebuffer_fade_mode != 0u) {
		if (e->sprite_orientation == 0u) {
			normal[0] = -tangent[1]; normal[1] = tangent[0]; normal[2] = 0.0f;
		} else if (e->sprite_orientation == 1u || e->sprite_orientation == 2u) {
			normal[0] = 0.0f; normal[1] = 0.0f; normal[2] = 1.0f;
		} else {
			float side[3];
			fx_cross(tangent, eye, side);
			fx_cross(side, tangent, normal);
		}
		length = fx_len(normal);
		if (length > 1e-6f) {
			float eye_length = fx_len(eye);
			for (k = 0; k < 3; ++k) normal[k] /= length;
			if (eye_length > 1e-6f)
				fade = fabsf((normal[0] * eye[0] + normal[1] * eye[1] + normal[2] * eye[2]) / eye_length);
			else fade = 0.0f;
		}
		if (e->framebuffer_fade_mode == 2u) fade = 1.0f - fade;
		if (e->particle_shader_flags & 0x0040u) fade = fade * fade * (3.0f - 2.0f * fade);
	}
	for (endpoint = 0; endpoint < 2u; ++endpoint) {
		uint8_t *rgba = endpoint ? end : start;
		for (channel = 0; channel < 3u; ++channel) {
			float value = colors[endpoint][channel + 1u] * 255.0f;
			if (!(value > 0.0f)) value = 0.0f;
			if (value > 255.0f) value = 255.0f;
			rgba[channel] = (uint8_t)value;
		}
		{
			float alpha = colors[endpoint][0] * 255.0f * fade;
			if ((endpoint == 0u && (e->particle_flags & HALO_PS2_FRAME_CONTRAIL_FADE_START)) ||
				(endpoint == 1u && (e->particle_flags & HALO_PS2_FRAME_CONTRAIL_FADE_END)))
				alpha = 0.0f;
			if (!(alpha > 0.0f)) alpha = 0.0f;
			if (alpha > 255.0f) alpha = 255.0f;
			rgba[3] = (uint8_t)alpha;
		}
	}
}

static void fx_pass(render_ctx_t *rc, int first_person_pass)
{
	const halo_ps2_snapshot_camera *cam;
	float right[3], up[3];
	clip_gs g;
	chain_t *c = rc->chain;
	uint32_t i, admitted = 0, verts = 0, n = 0, nbk, b, k;
	uint32_t saved_limit, saved_hud_limit, saved_scope;
	uint32_t *pw;
	u64 *q;
	u32 *w;
	if (!s_fx_count || !s_snapshot || s_cur_view >= s_snapshot->view_count) return;
	if (s_fx_descriptors && s_fx_profile) {
		if (!s_fx_descriptor_epoch_valid || s_fx_descriptor_profile_id != s_fx_profile->profile_id ||
			s_fx_descriptor_map_generation != s_snapshot->map_generation) {
			memset(s_fx_descriptors, 0, sizeof *s_fx_descriptors);
			s_fx_descriptor_profile_id = s_fx_profile->profile_id;
			s_fx_descriptor_map_generation = s_snapshot->map_generation;
			s_fx_descriptor_epoch_valid = 1u;
		}
	}
	cam = &s_snapshot->views[s_cur_view].camera;
	if (hcu_render_fx_camera_basis(cam, right, up) != 0) { s_view_counters.failures++; return; }
	g.near_z = rc->cam->near_z; g.zmax = 16777215.0f;
	g.sx = (float)VIDEO_WIDTH * 0.5f; g.sy = (float)VIDEO_HEIGHT * 0.5f; g.ox = 2048.0f; g.oy = 2048.0f;
	g.fog_k = 0.0f; g.fog_b = 4080.0f;
	if (!fx_chain_reserve_blend_restore(c, &saved_limit, &saved_hud_limit, &saved_scope)) return;

	for (i = 0; i < s_fx_count; i++) {
		uint8_t rgba[4], rgba_end[4];
		uint32_t nv;
		s_fxn[i] = 0;
		/* CE effect datums schedule/own child particles and other live
		 * datums; they have no authored billboard primitive of their own. Keep
		 * them in the snapshot for diagnostics, but never draw the orange
		 * bookkeeping fallback. */
		int qst;
		if (((s_fx[i].flags & HALO_PS2_FRAME_FX_FIRST_PERSON) != 0u) != (first_person_pass != 0))
			continue;
		if (s_fx[i].kind == HALO_PS2_FRAME_FX_EFFECT ||
			s_fx[i].kind == HALO_PS2_FRAME_FX_PARTICLE_SYSTEM) continue;
		if (s_fx[i].kind == HALO_PS2_FRAME_FX_DECAL &&
			(s_fx[i].flags & HALO_PS2_FRAME_FX_NATIVE_GEOMETRY))
			qst = fx_native_decal_quad(&s_fx[i], &s_fxq[i]);
		else if (s_fx[i].kind == HALO_PS2_FRAME_FX_PARTICLE)
			qst = fx_particle_quad(rc, &s_fx[i], right, up, &s_fxq[i]);
		else if (s_fx[i].kind == HALO_PS2_FRAME_FX_CONTRAIL)
			qst = hcu_render_fx_contrail_build_quad(&s_fx[i], cam, &s_fxq[i]);
		else qst = hcu_render_fx_build_quad(&s_fx[i], right, up, &s_fxq[i]);
		if (qst > 0) continue; /* CE-authored particle LOD/lifetime rejection */
		if (qst < 0 || (s_fx[i].kind == HALO_PS2_FRAME_FX_DECAL &&
			!(s_fx[i].flags & HALO_PS2_FRAME_FX_NATIVE_GEOMETRY)) ||
			hcu_render_fx_flat_colour(s_fx[i].kind, rgba) != 0) {
			s_view_counters.effects_refused++;
			continue;
		}
		if (s_fx[i].kind == HALO_PS2_FRAME_FX_PARTICLE) fx_particle_colour(&s_fx[i], rgba);
		if (s_fx[i].kind == HALO_PS2_FRAME_FX_DECAL) fx_decal_colour(&s_fx[i], rgba);
		if (s_fx[i].kind == HALO_PS2_FRAME_FX_CONTRAIL) fx_contrail_colour(&s_fx[i], cam, rgba, rgba_end);
		nv = fx_quad_clip(rc, &s_fxq[i], &s_fx[i], rgba,
			s_fx[i].kind == HALO_PS2_FRAME_FX_CONTRAIL ? rgba_end : NULL, &g, 0, 0, 0, 0, NULL);
		if (!nv) continue;                                /* behind the near plane or off the guard band */
		if (!chain_has_space(c, FX_STATE_QW + FX_PACKET_HDR_QW + 3u * (verts + nv))) {
			s_view_counters.fx_skipped_space++;
			continue;
		}
		s_fxn[i] = nv;
		verts += nv;
		admitted++;
	}
	if (!admitted) {
		fx_chain_restore_bounds(c, saved_limit, saved_hud_limit, saved_scope);
		return;
	}

	/* C3.6(c): resolve each admitted quad's binding (decal: resource_id = bitmap tag, permutation = element),
	 * bucket by binding, and make each bucket's texture resident. A bucket whose texture is refused is drawn flat. */
	for (i = 0; i < s_fx_count; i++) {
		if (!s_fxn[i]) continue;
		s_fx_textured[i] = 0;
		s_fx_cidx[n] = i;
		s_fx_cbind[n] = HCU_FX_BITMAP_NONE;
		s_fx_blend[n] = s_fx[i].framebuffer_blend_function;
		s_fx_fade[n] = s_fx[i].framebuffer_fade_mode;
		if (rc->opt->textures) hcu_fx_bitmap_resolve(s_fx_bind, s_fx_bind_count, s_fx[i].resource_id,
			s_fx[i].permutation, &s_fx_cbind[n]);
		n++;
	}
	nbk = hcu_fx_bucket_quads_state(s_fx_cbind, s_fx_blend, s_fx_fade, n,
		s_fx_order, s_fx_bucket, HCU_FX_BUCKET_CAP);
	if (nbk > HCU_FX_BUCKET_CAP) nbk = 0;                 /* -1 (bad arguments) draws every quad flat */
	for (b = 0; b < nbk; b++) {
		hcu_fx_bucket *bk = &s_fx_bucket[b];
		bsp_fx_tex_src src;
		const hcu_bitmap_binding *binding;
		uint64_t tex0 = 0;
		int st, source_attempted = 0;
		s_fx_bucket_ok[b] = 0;
		if (!rc->opt->textures) break;
		if (bk->binding == HCU_FX_BITMAP_NONE) { s_view_counters.fx_no_binding += bk->count; continue; }
		binding = &s_fx_bind[bk->binding];
		if (fx_backoff_active(bk->binding)) { s_view_counters.fx_budget_deferred += bk->count; continue; }
		s_fx_submit_blend = (uint8_t)bk->blend_function;
		st = hcu_fx_texture_resolve(s_fx_descriptors, binding,
			s_fx_profile ? s_fx_profile->profile_id : 0u,
			s_snapshot ? s_snapshot->map_generation : 0u,
			fx_resident_query, fx_source_load, fx_source_submit, &src, &tex0,
			&source_attempted, NULL);
		if (source_attempted) s_view_counters.fx_source_calls++;
		if (st == BSP_FX_TEX_OK) fx_backoff_set(bk->binding, 0);
		else if (source_attempted) fx_backoff_set(bk->binding, 1);
		if (st == BSP_FX_TEX_OK) {
			s_fx_bucket_ok[b] = 1;
			s_fx_tex0[b] = tex0;
			for (k = 0; k < bk->count; k++) s_fx_textured[s_fx_cidx[s_fx_order[bk->first + k]]] = 1;
		} else if (st == BSP_FX_TEX_BUDGET) {
			s_view_counters.fx_budget_deferred += bk->count;
		} else if (st == BSP_FX_TEX_CACHE_FULL) {
			s_view_counters.fx_cache_full += bk->count;
		} else if (st == BSP_FX_TEX_NO_SOURCE) {
			s_view_counters.fx_no_binding += bk->count;
		} else {
			s_view_counters.failures += bk->count;     /* outside the frame: a renderer ordering fault */
		}
	}

	/* Common depth state; alpha is set per CE shader-state bucket below. */
	if (!chain_has_space(c, FX_STATE_QW + 1u)) {
		s_view_counters.fx_skipped_space += admitted;
		fx_chain_restore_bounds(c, saved_limit, saved_hud_limit, saved_scope);
		return;
	}
	w = chain_cnt(c, FX_STATE_QW, rb_take_pending());
	if (!w) {
		s_view_counters.fx_skipped_space += admitted;
		fx_chain_restore_bounds(c, saved_limit, saved_hud_limit, saved_scope);
		return;
	}
	w[0] = VIF_CODE(VIF_NOP, 0, 0); w[1] = VIF_CODE(VIF_NOP, 0, 0);
	w[2] = VIF_CODE(VIF_FLUSHA, 0, 0); w[3] = VIF_CODE(VIF_DIRECT, 0, 1 + 3);
	q = (u64 *)(w + 4);
	q[0] = GIF_TAG(3, 1, 0, 0, GIFX_FLG_PACKED, 1); q[1] = GIF_REGS_AD;
	q[2] = GS_ALPHA(0, 1, 0, 1, 0);                q[3] = GS_A_ALPHA_1;
	q[4] = GS_TEST(0, 6, 0x40, 0, 0, 0, 1, 2);      q[5] = GS_A_TEST_1;
	q[6] = GS_ZBUF(*rb_zbuf_page_ptr(), GS_PSMZ24, 1); q[7] = GS_A_ZBUF_1;

	/* Each binding+blend+fade bucket gets matching GS alpha state and texture
	 * state, or a flat fallback packet with that same blend state. */
	for (b = 0; b < nbk; b++) {
		hcu_fx_bucket *bk = &s_fx_bucket[b];
		uint32_t bverts = 0;
		int textured = s_fx_bucket_ok[b] != 0;
		/* An effect whose texture is not resident (budget, full cache, no source)
		 * must not be drawn as its flat base colour: that is a solid rectangle
		 * around the projectile or impact. Withhold it until the texture is
		 * resident. Only the textures-off debug mode keeps the flat packets. */
		if (!textured && rc->opt->textures) {
			s_view_counters.fx_flat += bk->count;
			continue;
		}
		if ((bk->blend_function == 1u || bk->blend_function == 2u) && textured) {
			int decal_bucket = 1;
			for (k = 0; k < bk->count; ++k) {
				uint32_t oi = s_fx_order[bk->first + k];
				uint32_t qi = s_fx_cidx[oi];
				if (s_fx[qi].kind != HALO_PS2_FRAME_FX_DECAL ||
					!(s_fx[qi].flags & HALO_PS2_FRAME_FX_NATIVE_GEOMETRY) ||
					s_fx_cbind[oi] == HCU_FX_BITMAP_NONE) { decal_bucket = 0; break; }
			}
			if (decal_bucket) {
				for (k = 0; k < bk->count; ++k) {
					uint32_t oi = s_fx_order[bk->first + k];
					uint32_t qi = s_fx_cidx[oi];
					const hcu_bitmap_binding *binding = &s_fx_bind[s_fx_cbind[oi]];
					if (fx_decal_composite_one(rc, &s_fx[qi], binding, &s_fxq[qi], &g,
						s_fx_tex0[b], 0u)) {
						s_view_counters.fx_drawn++; s_view_counters.fx_textured++;
					} else {
						s_view_counters.effects_refused++;
						s_view_counters.fx_blend_unsupported++;
					}
				}
				continue;
			}
		}
		if (bk->blend_function != 0u && bk->blend_function != 3u && bk->blend_function != 4u &&
			bk->blend_function != 7u)
			s_view_counters.fx_blend_unsupported += bk->count;
		if (!fx_blend_state(c, bk->blend_function)) {
			s_view_counters.fx_skipped_space += bk->count;
			continue;
		}
		for (k = 0; k < bk->count; k++) bverts += s_fxn[s_fx_cidx[s_fx_order[bk->first + k]]];
		if (textured) {
			int repeat_uv = 0;
			for (k = 0; k < bk->count; ++k)
				if (s_fx[s_fx_cidx[s_fx_order[bk->first + k]]].kind == HALO_PS2_FRAME_FX_CONTRAIL)
					repeat_uv = 1;
			if (!chain_has_space(c, FX_STATE_QW)) {
				s_view_counters.fx_skipped_space += bk->count;
				continue;
			}
			fx_tex_state(c, s_fx_tex0[b], 0, repeat_uv);
		}
		w = chain_cnt(c, FX_PACKET_HDR_QW + 3u * bverts, 0);
		if (!w) { s_view_counters.fx_skipped_space += bk->count; continue; }
		w[0] = VIF_CODE(VIF_NOP, 0, 0); w[1] = VIF_CODE(VIF_NOP, 0, 0);
		w[2] = VIF_CODE(VIF_FLUSHA, 0, 0); w[3] = VIF_CODE(VIF_DIRECT, 0, 1 + 3 * bverts);
		q = (u64 *)(w + 4);
		q[0] = GIF_TAG(bverts, 1, 1, GS_PRIM(GSX_PRIM_TRIANGLE, 1, textured, rc->opt->fog, 1, 0, 0, 0, 0), GIFX_FLG_PACKED, 3);
		q[1] = 0x412;
		pw = (uint32_t *)(q + 2);
		for (k = 0; k < bk->count; k++) {
			uint32_t qi = s_fx_cidx[s_fx_order[bk->first + k]];
			uint8_t rgba[4], rgba_end[4];
			hcu_render_fx_flat_colour(s_fx[qi].kind, rgba);
			if (s_fx[qi].kind == HALO_PS2_FRAME_FX_PARTICLE) fx_particle_colour(&s_fx[qi], rgba);
			if (s_fx[qi].kind == HALO_PS2_FRAME_FX_DECAL) fx_decal_colour(&s_fx[qi], rgba);
			if (s_fx[qi].kind == HALO_PS2_FRAME_FX_CONTRAIL) fx_contrail_colour(&s_fx[qi], cam, rgba, rgba_end);
			pw += 12 * fx_quad_clip(rc, &s_fxq[qi], &s_fx[qi], rgba,
				s_fx[qi].kind == HALO_PS2_FRAME_FX_CONTRAIL ? rgba_end : NULL, &g,
				textured, 0, 0, 0, pw);
			s_view_counters.fx_drawn++;
			if (textured) s_view_counters.fx_textured++;
			else s_view_counters.fx_flat++;
		}
	}
	/* Do not leak the last effect blend state into the following pass. */
	fx_chain_restore_bounds(c, saved_limit, saved_hud_limit, saved_scope);
	(void)fx_blend_state(c, 0u);
}

static void object_pass(void *user, render_ctx_t *rc)
{
	uint32_t i;
	(void)user;
#if HCU_C3_OBJECT_VIEW_CACHE
	s_objr.setup_emitted = obj_render_begin_view(rc);
	if (!s_objr.setup_emitted) s_view_counters.failures++;
#endif
	for (i = 0; i < s_draw_count && (!HCU_C3_OBJECT_VIEW_CACHE || s_objr.setup_emitted); i++) {
		const hcu_render_object_draw *d = &s_draw[i];
		obj_slot *s = &s_slots[d->slot];
#if !HCU_C3_OBJECT_FASTPATH
		object_table_t table;
		object_t *ob = &table.obj[0];
#else
		object_t object_storage;
		object_t *ob = &object_storage;
#endif
		model_info mi;
		uint16_t perm[OBJ_MAX_REGIONS];
		mat4 root;
		if (d->type == HCU_OBJECTS_TYPE_BIPED) s_view_counters.attempted_bipeds++;
		else if (d->type == HCU_OBJECTS_TYPE_VEHICLE) s_view_counters.attempted_vehicles++;
		else if (d->type == HCU_OBJECTS_TYPE_WEAPON) s_view_counters.attempted_weapons++;
		if (!s->loaded) {
			if (d->type == HCU_OBJECTS_TYPE_BIPED) s_view_counters.refused_bipeds++;
			else if (d->type == HCU_OBJECTS_TYPE_VEHICLE) s_view_counters.refused_vehicles++;
			else if (d->type == HCU_OBJECTS_TYPE_WEAPON) s_view_counters.refused_weapons++;
			continue;
		}
		if (HCU_C3_OBJECT_PREPARE_CACHE && s_prepared && s_prepared->ready && d->object_index < HALO_PS2_FRAME_MAX_OBJECTS &&
			s_prepared->sequence == s_snapshot->sequence && s_prepared->map_generation == s_snapshot->map_generation &&
			s_prepared->object[d->object_index].valid &&
			s_prepared->object[d->object_index].generation == d->generation &&
			s_prepared->object[d->object_index].resource_id == d->resource_id &&
			s_prepared->object[d->object_index].slot == d->slot &&
			s_prepared->slot[d->slot].valid && s_prepared->slot[d->slot].epoch == s_slot_epoch[d->slot]) {
			mi = s_prepared->slot[d->slot].info;
			memcpy(perm, s_prepared->slot[d->slot].perm, sizeof perm);
			root = s_prepared->object[d->object_index].root;
			s_prepare_stats.reused_objects++;
		} else {
			mi = model_get(&s->models, 0);
			model_select_permutations(&s->models, &mi, NULL, perm);
			root = mat_from_snapshot(&d->world);
			if (HCU_C3_OBJECT_PREPARE_CACHE) s_prepare_stats.cache_fallbacks++;
		}
#if !HCU_C3_OBJECT_FASTPATH
		memset(&table, 0, sizeof table);
#endif
		memset(ob, 0, sizeof *ob);
		ob->def = -1;
		ob->type = (uint8_t)d->type;
		ob->flags = OBJ_F_VISIBLE | ((d->flags & HCU_OBJECTS_FLAG_SKINNED) ? OBJ_F_ANIMATED : 0);
		ob->model = 0;
		ob->graph = -1;
		ob->anim = SCEN_NO_ANIM;
		ob->region_count = mi.region_count < OBJ_MAX_REGIONS ? mi.region_count : OBJ_MAX_REGIONS;
		ob->frame = 0.0f;
		ob->root = root;
		ob->pos[0] = root.m[3][0]; ob->pos[1] = root.m[3][1]; ob->pos[2] = root.m[3][2];
		ob->radius = mi.radius * d->world.scale;
		memcpy(ob->perm, perm, sizeof ob->perm);
#if HCU_C3_OBJECT_FASTPATH
		s_objr.table = NULL;
		s_objr.span = ob;
		s_objr.span_count = 1;
#else
		table.count = 1;
		s_objr.table = &table;
		s_objr.span = NULL;
		s_objr.span_count = 0;
#endif
		s_objr.world.models = &s->models;
		s_objr.world.scen = NULL;
		s_objr.world.anims = NULL;
		s_objr.textures = &s->src;
		s_objr.draw_objects = 1;
		s_objr.viewmodel = 0;
		s_objr.draw_fp = 0;
		s_objr.fp = NULL;
		s_objr.lod = d->ground_weapon_lod ? &s_ground_weapon_lodctl : NULL;
		s_objr.bsp = NULL;
		s_objr.bsp_index = 0;
		s_objr.max_distance = d->ground_weapon_lod ? (4000.0f / lodctl_distance_scale(&s_ground_weapon_lodctl)) : 4000.0f;
		s_objr.max_batches = OBJ_BUDGET;
		s_objr.sky_model = -1;
		s_objr.pose = pose_fn;
		s_objr.pose_user = (void *)d;
		{
		#if (defined(HALO_PS2_C3_LAG_TRACE) && HALO_PS2_C3_LAG_TRACE) || \
			(defined(HALO_PS2_C3_PERF_PROBE) && HALO_PS2_C3_PERF_PROBE)
			uint32_t pass_start = timer_cycles();
#endif
			obj_render_pass(&s_objr, rc);
		#if (defined(HALO_PS2_C3_LAG_TRACE) && HALO_PS2_C3_LAG_TRACE) || \
			(defined(HALO_PS2_C3_PERF_PROBE) && HALO_PS2_C3_PERF_PROBE)
			s_world_render_cycles += timer_cycles() - pass_start;
#endif
		}
		log_part_parity(s, &mi, perm, d->resource_id, d->type == HCU_OBJECTS_TYPE_VEHICLE ? HCU_RENDER_PARITY_VEHICLE
			: d->type == HCU_OBJECTS_TYPE_WEAPON ? HCU_RENDER_PARITY_WEAPON : HCU_RENDER_PARITY_OBJECT);
		if (s_objr.st_visible && s_objr.st_batches > 0u) {
			s_view_drawn++;
			s_view_counters.objects_drawn++;
			frame_identity_add(d->type == HCU_OBJECTS_TYPE_VEHICLE ? HCU_RENDER_PARITY_VEHICLE
				: d->type == HCU_OBJECTS_TYPE_WEAPON ? HCU_RENDER_PARITY_WEAPON : HCU_RENDER_PARITY_OBJECT,
				(int32_t)d->definition_index, d->resource_id);
			if (d->type == HCU_OBJECTS_TYPE_BIPED || d->type == HCU_OBJECTS_TYPE_VEHICLE ||
				d->type == HCU_OBJECTS_TYPE_WEAPON)
				(void)hcu_render_objects_note_submission(&s_view_counters, &s_drawn_identities,
					d->type, s_snapshot->objects[d->object_index].id.index, d->generation);
			s_view_counters.triangles += s_objr.st_triangles;
		} else if (s_objr.st_culled && !s_objr.st_visible) {
			/* Frustum, distance, sub-pixel or pose culling is CE's normal per-view decision, not a draw
			 * failure. Only an object that passed culling and was refused below counts as a failure. */
		} else {
			if (d->type == HCU_OBJECTS_TYPE_BIPED) s_view_counters.refused_bipeds++;
			else if (d->type == HCU_OBJECTS_TYPE_VEHICLE) s_view_counters.refused_vehicles++;
			else if (d->type == HCU_OBJECTS_TYPE_WEAPON) s_view_counters.refused_weapons++;
			s_view_counters.failures++;
		}
		s_view_triangles += s_objr.st_triangles;
	}
	/* World decals/particles use the untouched world Z buffer. CE source pass flags
	 * select camera-local particles for the later viewmodel depth context. */
	fx_pass(rc, 0);
	/* CE has already selected these exact model tags and mapped its animation
	 * graph pose into each model's node order. Draw arms and gun as separate
	 * view-space model submissions, after world objects, using only the
	 * snapshot's resource slots and palette ranges. */
	{
		camera_t viewmodel_cam;
		frustum_t viewmodel_frustum;
		float viewmodel_clip[4][4];
		render_ctx_t viewmodel_rc;
		int viewmodel_ready = 0;
#if (defined(HALO_PS2_C3_LAG_TRACE) && HALO_PS2_C3_LAG_TRACE) || \
	(defined(HALO_PS2_C3_PERF_PROBE) && HALO_PS2_C3_PERF_PROBE)
		uint32_t fp_total_start = timer_cycles();
#endif
		if (s_fp_draw_count > 0u && rc && rc->cam) {
			if (camera_viewmodel_context(rc->cam, rc->viewport_w, rc->viewport_h,
				VIDEO_WIDTH, VIDEO_HEIGHT, &viewmodel_cam, viewmodel_clip, &viewmodel_frustum) == 0) {
				viewmodel_rc = *rc;
				viewmodel_rc.cam = &viewmodel_cam;
				viewmodel_rc.clip = (const float (*)[4])viewmodel_clip;
				viewmodel_rc.frustum = &viewmodel_frustum;
				/* Clear only this view's depth before both models. AFAIL_ZB_ONLY preserves world color and the
				 * model packets still use GEQUAL + writes, so hands/gun occlude each other normally. */
				viewmodel_ready = rb_first_person_depth_begin(rc);
				if (viewmodel_ready && !obj_render_begin_view(&viewmodel_rc))
					viewmodel_ready = 0;
			}
		if (!viewmodel_ready) s_view_counters.failures++;
		}
	for (i = 0; viewmodel_ready && i < s_fp_draw_count; i++) {
		const hcu_render_first_person_draw *fp = &s_fp_draw[i];
		hcu_render_object_draw pose;
#if !HCU_C3_OBJECT_FASTPATH
		object_table_t table;
		object_t *ob = &table.obj[0];
#else
		object_t object_storage;
		object_t *ob = &object_storage;
#endif
		obj_slot *s;
		model_info mi;
		uint16_t perm[OBJ_MAX_REGIONS];
		mat4 root;
		halo_ps2_snapshot_matrix4x3 root_world;
		if (fp->model_slot >= s_slot_count ||
			fp->palette_count == 0u || !s_snapshot ||
			(uint32_t)fp->palette_first + fp->palette_count > s_snapshot->palette_count) {
			s_view_counters.failures++;
			continue;
		}
		s = &s_slots[fp->model_slot];
		if (!s->loaded) {
			s_view_counters.first_person_model_misses++;
			s_view_counters.model_misses++;
			s_view_counters.failures++;
			continue;
		}
		memset(&pose, 0, sizeof pose);
		pose.slot = fp->model_slot;
		pose.type = HCU_OBJECTS_TYPE_WEAPON;
		pose.flags = HCU_OBJECTS_FLAG_SKINNED | HCU_OBJECTS_FLAG_CAMERA_LOCAL;
		pose.resource_id = fp->resource_id;
		pose.palette_first = fp->palette_first;
		pose.palette_count = fp->palette_count;
		if (s_cur_view >= s_snapshot->view_count ||
			hcu_render_first_person_world(&s_snapshot->views[s_cur_view].camera,
				&s_snapshot->palette[fp->palette_first], &root_world) != 0) {
			s_view_counters.failures++;
			continue;
		}
		root = mat_from_snapshot(&root_world);
		mi = model_get(&s->models, 0);
		model_select_permutations(&s->models, &mi, NULL, perm);
		memset(perm + (mi.region_count < OBJ_MAX_REGIONS ? mi.region_count : OBJ_MAX_REGIONS),
			0, (OBJ_MAX_REGIONS - (mi.region_count < OBJ_MAX_REGIONS ? mi.region_count : OBJ_MAX_REGIONS)) * sizeof *perm);
		{
			unsigned region;
			for (region = 0; region < mi.region_count && region < OBJ_MAX_REGIONS; region++)
				if (perm[region] >= mi.permutation_count) perm[region] = 0;
		}
#if !HCU_C3_OBJECT_FASTPATH
		memset(&table, 0, sizeof table);
#endif
		memset(ob, 0, sizeof *ob);
		ob->def = -1;
		ob->type = HCU_OBJECTS_TYPE_WEAPON;
		ob->flags = OBJ_F_VISIBLE | OBJ_F_ANIMATED;
		ob->model = 0;
		ob->graph = -1;
		ob->anim = SCEN_NO_ANIM;
		ob->region_count = mi.region_count < OBJ_MAX_REGIONS ? mi.region_count : OBJ_MAX_REGIONS;
		ob->root = root;
		ob->pos[0] = root.m[3][0]; ob->pos[1] = root.m[3][1]; ob->pos[2] = root.m[3][2];
		ob->radius = mi.radius * s_snapshot->palette[fp->palette_first].scale;
		memcpy(ob->perm, perm, sizeof ob->perm);
#if HCU_C3_OBJECT_FASTPATH
		s_objr.table = NULL;
		s_objr.span = ob;
		s_objr.span_count = 1;
#else
		table.count = 1;
		s_objr.table = &table;
		s_objr.span = NULL;
		s_objr.span_count = 0;
#endif
		s_objr.world.models = &s->models;
		s_objr.world.scen = NULL;
		s_objr.world.anims = NULL;
		s_objr.textures = &s->src;
		s_objr.draw_objects = 1;
		s_objr.viewmodel = 1;
		s_objr.draw_fp = 0;
		s_objr.fp = NULL;
		s_objr.lod = NULL;
		s_objr.bsp = NULL;
		s_objr.bsp_index = 0;
		s_objr.max_distance = 4000.0f;
		s_objr.max_batches = OBJ_BUDGET;
		s_objr.sky_model = -1;
		s_objr.pose = pose_fn;
		s_objr.pose_user = &pose;
		s_fp_lodctl.level = (s_view_fp_lod == HCU_OBJECTS_FP_LOD_FAR) ? 4 : 0;
		s_objr.lod = &s_fp_lodctl;
		s_fp_cam = &s_snapshot->views[s_cur_view].camera;
#if defined(HALO_PS2_C3_MOVEMENT_TRACE)
		if (s_cur_view == 0u) fp_view_diagnostic(&viewmodel_rc);
#endif
		{
		#if (defined(HALO_PS2_C3_LAG_TRACE) && HALO_PS2_C3_LAG_TRACE) || \
			(defined(HALO_PS2_C3_PERF_PROBE) && HALO_PS2_C3_PERF_PROBE)
			uint32_t pass_start = timer_cycles();
#endif
			obj_render_pass(&s_objr, &viewmodel_rc);
		#if (defined(HALO_PS2_C3_LAG_TRACE) && HALO_PS2_C3_LAG_TRACE) || \
			(defined(HALO_PS2_C3_PERF_PROBE) && HALO_PS2_C3_PERF_PROBE)
			s_fp_render_cycles += timer_cycles() - pass_start;
#endif
		}
		s_fp_cam = NULL;
		log_part_parity(s, &mi, perm, fp->resource_id, HCU_RENDER_PARITY_WEAPON);
		s_view_triangles += s_objr.st_triangles;
		s_view_skinned += fp->palette_count;
		if (s_objr.st_visible && s_objr.st_batches > 0u) {
			s_view_drawn++;
			s_view_counters.objects_drawn++;
			s_view_counters.first_person_draws++;
			frame_identity_add(HCU_RENDER_PARITY_WEAPON, -1, fp->resource_id);
			if (fp->kind == HCU_OBJECTS_FP_WEAPON) s_view_counters.first_person_weapon_draws++;
			else if (fp->kind == HCU_OBJECTS_FP_HANDS) s_view_counters.first_person_hands_draws++;
			s_view_counters.triangles += s_objr.st_triangles;
		} else {
			s_view_counters.failures++;
		}
	}
	if (viewmodel_ready) fx_pass(&viewmodel_rc, 1);
	if (viewmodel_ready && !rb_first_person_depth_end(rc)) s_view_counters.failures++;
	#if (defined(HALO_PS2_C3_LAG_TRACE) && HALO_PS2_C3_LAG_TRACE) || \
		(defined(HALO_PS2_C3_PERF_PROBE) && HALO_PS2_C3_PERF_PROBE)
		{
			uint32_t total = timer_cycles() - fp_total_start;
			s_timing_probe.version = 1u;
			s_timing_probe.frame = s_frame;
			s_timing_probe.view = s_cur_view;
			s_timing_probe.world_render_cycles = s_world_render_cycles;
			s_timing_probe.first_person_render_cycles = s_fp_render_cycles;
			s_timing_probe.first_person_overhead_cycles = total > s_fp_render_cycles ? total - s_fp_render_cycles : 0u;
			s_timing_probe.drawn = s_view_drawn;
			s_timing_probe.triangles = s_view_triangles;
			s_timing_probe.skinned_nodes = s_view_skinned;
			s_timing_probe.failures = s_view_counters.failures;
		}
	#endif
	}
	/* s_objr is reused across views/frames; never let FP-only culling policy leak into a world pass. */
	s_objr.viewmodel = 0;
#if HCU_C3_OBJECT_VIEW_CACHE
	s_objr.setup_emitted = 0;
#endif
}

/* ---- public ------------------------------------------------------------------------------------- */
int hcu_render_objects_load(const hcu_asset_profile_view *view, arena_t *arena,
	const hcu_render_objects_table_entry *table, uint32_t count, hcu_render_objects_load_info *info)
{
	uint32_t i;
	size_t room;
	uint8_t *base;
	if (!view || !arena || !table || !info) return HCU_RENDER_CONTENT_E_ARGUMENT;
	if (count > HCU_OBJECTS_MAX_MODELS) return HCU_RENDER_CONTENT_E_FULL;
	memset(info, 0, sizeof *info);
	prepared_invalidate_all();
	memset(s_slots, 0, sizeof s_slots);
	s_bounds_map_generation = 0u;
	memset(s_slot_pins, 0, sizeof s_slot_pins);
	s_sky_pinned = 0u;
	memset(s_meta, 0, sizeof s_meta);
	memset(&s_res, 0, sizeof s_res);
	memset(&s_totals, 0, sizeof s_totals);
	memset(&s_drawn_identities, 0, sizeof s_drawn_identities);
	memset(&s_view_counters, 0, sizeof s_view_counters);
	s_profile = view;
	s_slot_count = count;
	s_tex_total = count * HCU_OBJECTS_TEX_STRIDE;
	s_installed = 0;
	s_parity.records = NULL;
	info->arena_before = (uint32_t)arena->used;
	/* The residency pool is the render arena's rest: nothing else is charged to it after this. */
	room = arena->cap > arena->used ? arena->cap - arena->used : 0;
	if (room) {
		uintptr_t current = (uintptr_t)arena->base + arena->used;
		size_t padding = (size_t)((-(uintptr_t)current) & (OBJ_ALIGN - 1u));
		room = room > padding ? room - padding : 0;
		room &= ~(size_t)(OBJ_ALIGN - 1u);
	}
	base = room ? arena_alloc(arena, room, OBJ_ALIGN) : NULL;
	pool_init(base, base ? (uint32_t)room : 0u);
	for (i = 0; i < count; i++) {
		obj_slot *s = &s_slots[i];
		s->entry = &table[i];
		if (chunk_check(view, table[i].model_chunk, table[i].model_sha256, &s->model_size) != 0) {
			s->refused = 1;
			info->models_refused++;
			continue;
		}
		s->tex_size = 0;
		if (table[i].texture_chunk &&
			chunk_check(view, table[i].texture_chunk, table[i].texture_sha256, &s->tex_size) != 0)
			s->tex_size = 0;               /* a bad texture chunk leaves the entry flat, as before */
		s_meta[i].resource_id = table[i].source_datum & 0xFFFFu;
		s_meta[i].source_datum = table[i].source_datum;
		info->entries++;
	}
	info->pool_bytes = s_pool_size;
	info->arena_after = (uint32_t)arena->used;
	return base ? HCU_RENDER_CONTENT_OK : HCU_RENDER_CONTENT_E_FULL;
}

void hcu_render_objects_residency_stats(hcu_render_objects_residency *out)
{
	if (out) *out = s_res;
}

/* C3.6 sky: the scenario sky model, drawn by halo-ps2's obj_render_sky (camera-centred, Z test always, no Z write)
 * before each view's BSP. The sky entry is not a snapshot object, so frame begin requests it on its own. */
void hcu_render_objects_set_sky_entry(uint32_t table_index)
{
	s_sky_index = table_index < HCU_OBJECTS_MAX_MODELS ? table_index : HCU_RENDER_OBJECTS_SKY_NONE;
}

static void sky_pass(void *user, render_ctx_t *rc)
{
	obj_slot *s;
	model_info mi;
	uint16_t perm[OBJ_MAX_REGIONS];
	unsigned region;
	(void)user;
	if (s_sky_index >= s_slot_count) return;
	s = &s_slots[s_sky_index];
	if (!s->loaded) { s_view_counters.sky_misses++; return; }
	s_objr.world.models = &s->models;
	s_objr.world.scen = NULL;
	s_objr.world.anims = NULL;
	s_objr.textures = &s->src;
	s_objr.sky_model = 0;
	obj_render_sky(&s_objr, rc);
	s_view_counters.sky_drawn++;
	/* parity: per-part identities of the sky's LOD-0 permutations, logged at frame 0 like the other models */
	mi = model_get(&s->models, 0);
	model_select_permutations(&s->models, &mi, NULL, perm);
	for (region = 0; region < mi.region_count && region < OBJ_MAX_REGIONS; region++)
		if (perm[region] >= mi.permutation_count) perm[region] = 0;
	log_part_parity(s, &mi, perm, s->entry->source_datum & 0xFFFFu, HCU_RENDER_PARITY_SKY);
	frame_identity_add(HCU_RENDER_PARITY_SKY, -1, s->entry->source_datum & 0xFFFFu);
}

int hcu_render_objects_frame_parity(hcu_render_parity_frame *out)
{
	if (!out) return HCU_RENDER_CONTENT_E_ARGUMENT;
	*out = s_frame_parity;
	return HCU_RENDER_CONTENT_OK;
}

int hcu_render_objects_install(void)
{
	memset(&s_src_total, 0, sizeof s_src_total);
	s_src_total.texture_count = s_tex_total;
	s_src_total.binding = slot_binding;
	s_src_total.texture = slot_texture;
	/* The texture cache keys are fixed per entry (HCU_OBJECTS_TEX_STRIDE), so an evicted entry reloads under the
	 * same keys and its bytes never change. */
	bsp_render_cache_limit(0);
	bsp_render_set_object_pass(object_pass, NULL, &s_src_total);
	bsp_render_set_sky_pass(sky_pass, NULL);
	s_installed = 1;
	return 0;
}

/* Synthetic publisher: one object set per view. Model slots are found by table path, so the plan
 * follows the generated table order rather than fixed indices. */
static int find_entry(const char *path)
{
	uint32_t i;
	for (i = 0; i < s_slot_count; i++)
		if (!s_slots[i].refused && s_slots[i].entry->path && strcmp(s_slots[i].entry->path, path) == 0) {
			/* The synthetic set references the entry through the same residency path as a snapshot does. It runs
			 * before this frame's residency ranks are set, so it may displace only entries that are not needed. */
			entry_request(s_profile, i, s_frame, HCU_OBJECTS_RANK_UNUSED - 1u);
			return s_slots[i].loaded ? (int)i : -1;
		}
	return -1;
}

static int publish_synthetic(uint32_t frame, uint32_t views, const halo_ps2_snapshot_camera *cams)
{
	static const char *const cyborg = "characters\\cyborg\\cyborg";
	static const char *const rifle = "weapons\\assault rifle\\assault rifle";
	static const char *const grenade = "weapons\\plasma grenade\\plasma grenade";
	static const char *const ghost = "vehicles\\ghost\\ghost";
	halo_ps2_frame_snapshot *s;
	halo_ps2_snapshot_matrix4x3 pal[SKEL_MAX_NODES];
	int ic = find_entry(cyborg), ir = find_entry(rifle), ig = find_entry(grenade), ih = find_entry(ghost);
	uint32_t v;
	uint32_t ghost_index = 0xFFFFFFFFu;
	if (!views || views > HALO_PS2_FRAME_MAX_VIEWS || !cams || ic < 0 || ir < 0 || ig < 0 || ih < 0) return -1;
	s = hcu_snapshot_bank_begin_write();
	if (!s) return -2;
	if (hcu_render_synthetic_begin(s, 1u, frame, views) != 0) { hcu_snapshot_bank_abandon(s); return -3; }
	for (v = 0; v < views; v++) {
		const halo_ps2_snapshot_camera *c = &cams[v];
		float hx = c->forward[0], hy = c->forward[1], fl;
		halo_ps2_snapshot_matrix4x3 m;
		halo_ps2_snapshot_matrix4x3 world;
		halo_ps2_snapshot_matrix4x3 grenade_at;
		hcu_render_synthetic_object o;
		unsigned n = 0, k;
		fl = sqrtf(hx * hx + hy * hy);
		if (fl < 1e-4f) { hx = 1.0f; hy = 0.0f; fl = 1.0f; }
		hx /= fl; hy /= fl;
		/* Facing the camera: forward = -H, left = Z x forward, up = Z. */
		memset(&m, 0, sizeof m);
		m.scale = 1.0f;
		m.forward[0] = -hx; m.forward[1] = -hy; m.forward[2] = 0.0f;
		m.left[0] = hy; m.left[1] = -hx; m.left[2] = 0.0f;
		m.up[2] = 1.0f;
		m.position[0] = c->position[0] + hx * 8.0f;
		m.position[1] = c->position[1] + hy * 8.0f;
		m.position[2] = c->position[2] - 5.0f;
		if (hcu_render_synthetic_view(s, v, c) != 0) { hcu_snapshot_bank_abandon(s); return -4; }
		n = s_slots[ic].models.model_count ? model_get(&s_slots[ic].models, 0).node_count : 0;
		if (n == 0 || n > SKEL_MAX_NODES) n = 1;
		for (k = 0; k < n; k++) pal[k] = m;
		memset(&o, 0, sizeof o);
		o.resource_id = s_slots[ic].entry->source_datum & 0xFFFFu; o.definition_index = 0; o.type = HCU_OBJECTS_TYPE_BIPED;
		o.flags = HCU_OBJECTS_FLAG_SKINNED; o.palette_count = (uint16_t)n; o.world = m; o.palette = pal;
		if (hcu_render_synthetic_object_add(s, v, s->object_count, &o) != 0) { hcu_snapshot_bank_abandon(s); return -5; }
		/* Weapon held beside the player, and a plasma grenade effect above it. */
		world = m;
		world.position[0] += m.left[0] * 1.0f; world.position[1] += m.left[1] * 1.0f; world.position[2] += 1.0f;
		memset(&o, 0, sizeof o);
		o.resource_id = s_slots[ir].entry->source_datum & 0xFFFFu; o.definition_index = 1; o.type = HCU_OBJECTS_TYPE_WEAPON;
		o.world = world;
		if (hcu_render_synthetic_object_add(s, v, s->object_count, &o) != 0) { hcu_snapshot_bank_abandon(s); return -6; }
		grenade_at = m;
		grenade_at.position[2] += 2.5f;
		memset(&o, 0, sizeof o);
		o.resource_id = s_slots[ig].entry->source_datum & 0xFFFFu; o.definition_index = 2; o.type = HCU_OBJECTS_TYPE_EFFECT;
		o.world = grenade_at;
		if (hcu_render_synthetic_object_add(s, v, s->object_count, &o) != 0) { hcu_snapshot_bank_abandon(s); return -7; }
		/* Vehicle in front of view 0; the same object is referenced by every view (deduplicated). */
		if (v == 0) {
			halo_ps2_snapshot_matrix4x3 car = m;
			car.position[0] = c->position[0] + hx * 16.0f + m.left[0] * 6.0f;
			car.position[1] = c->position[1] + hy * 16.0f + m.left[1] * 6.0f;
			car.position[2] = c->position[2] - 6.0f;
			memset(&o, 0, sizeof o);
			o.resource_id = s_slots[ih].entry->source_datum & 0xFFFFu; o.definition_index = 3; o.type = HCU_OBJECTS_TYPE_VEHICLE;
			o.world = car;
			ghost_index = s->object_count;
			if (hcu_render_synthetic_object_add(s, v, ghost_index, &o) != 0) { hcu_snapshot_bank_abandon(s); return -8; }
		} else if (ghost_index != 0xFFFFFFFFu) {
			memset(&o, 0, sizeof o);
			o.resource_id = s_slots[ih].entry->source_datum & 0xFFFFu; o.definition_index = 3; o.type = HCU_OBJECTS_TYPE_VEHICLE;
			if (hcu_render_synthetic_object_add(s, v, ghost_index, &o) != 0) { hcu_snapshot_bank_abandon(s); return -9; }
		}
	}
	if (hcu_snapshot_bank_commit(s) != 0) return -10;
	return 0;
}

const halo_ps2_frame_snapshot *hcu_render_objects_frame_begin(uint32_t frame, uint32_t synthetic_views,
	const halo_ps2_snapshot_camera *synthetic_cameras, uint32_t layout_view_count,
	int32_t screen_w, int32_t screen_h)
{
	const halo_ps2_frame_snapshot *pre_admit_snapshot = NULL;
	hcu_snapshot_bank_stats bank_stats;
	uint32_t pre_admit_sequence = 0u, pre_admit_generation = 0u;
	int pre_admitted = 0;
	s_frame = frame;
	memset(&s_view_counters, 0, sizeof s_view_counters);
	if (s_pin.pinned && s_pending_seq && bsp_render_fence_observed(s_pending_seq) == 1 &&
		bsp_render_source_release(BSP_SRC_OBJECT_PIN, s_pending_seq) == 1) {
		pin_drop();
		s_pending_seq = 0;
	}
	if (synthetic_views) {
		if (publish_synthetic(frame, synthetic_views, synthetic_cameras) != 0) s_totals.failures++;
	}
	/* Cache admission may reclaim stale resources only when every snapshot reader
	 * and the prior GS chain are done. Plan from an unpinned latest snapshot, then
	 * verify its identity again after taking our immutable render pin. */
	if (!s_pin.pinned) {
		hcu_snapshot_bank_get_stats(&bank_stats);
		pre_admit_snapshot = hcu_snapshot_bank_latest();
		if (pre_admit_snapshot && hcu_render_objects_residency_pre_admit_allowed(
			bank_stats.read_pins_active, s_pin.pinned, pool_fence_safe(),
			pre_admit_snapshot->sequence, pre_admit_snapshot->map_generation)) {
			pre_admit_sequence = pre_admit_snapshot->sequence;
			pre_admit_generation = pre_admit_snapshot->map_generation;
			residency_frame(pre_admit_snapshot, frame, layout_view_count, screen_w, screen_h);
			if (s_sky_index < s_slot_count && !s_slots[s_sky_index].refused) {
				entry_request(s_profile, s_sky_index, frame, 0u);
				if (s_slots[s_sky_index].loaded && !s_sky_pinned) {
					s_slot_pins[s_sky_index]++;
					s_sky_pinned = 1u;
				}
			}
			pre_admitted = 1;
		}
	}
	if (!s_pin.pinned) {
		hcu_render_objects_pin(&s_pin, &s_totals);
		if (s_pin.pinned) slot_pins_apply(s_pin.snapshot, 1);
	}
	s_snapshot = s_pin.pinned ? s_pin.snapshot : NULL;
	if (s_snapshot && (!pre_admitted || !hcu_render_objects_residency_pre_admit_matches(
		pre_admit_sequence, pre_admit_generation, s_snapshot->sequence, s_snapshot->map_generation)))
		residency_frame(s_snapshot, frame, layout_view_count, screen_w, screen_h);
	hcu_render_parity_frame_reset(&s_frame_parity);
	if (s_sky_index < s_slot_count && !s_slots[s_sky_index].refused) {
		entry_request(s_profile, s_sky_index, frame, 0u);   /* the sky is requested with the top rank (it is pinned once loaded) */
		if (s_slots[s_sky_index].loaded && !s_sky_pinned) {
			s_slot_pins[s_sky_index]++;        /* the sky is never an eviction victim once resident */
			s_sky_pinned = 1;
		}
	}
	s_pose_snapshot = s_snapshot;
	if (s_snapshot) {
		prepare_snapshot(s_snapshot);
		hcu_render_objects_track_poses(s_snapshot, &s_poses, &s_totals);
	}
	return s_snapshot;
}

void hcu_render_objects_view_begin_rect(uint32_t view, int32_t view_w, int32_t view_h,
	int32_t screen_w, int32_t screen_h)
{
	/* Keep selection aligned with the parent view's exact projection. The same
	 * layout aspect was used to admit residency before the snapshot was pinned. */
	if (s_snapshot && view < s_snapshot->view_count && view < HALO_PS2_FRAME_MAX_VIEWS &&
		view_w > 0 && view_h > 0)
		hcu_render_objects_frustum_build_aspect(&s_snapshot->views[view],
			(float)view_w / (float)view_h, &s_view_frustums[view]);
	hcu_render_objects_view_begin(view);
	s_view_fp_lod = hcu_render_objects_fp_lod(view_w, view_h, screen_w, screen_h);
}

void hcu_render_objects_view_begin(uint32_t view)
{
	uint32_t n = 0;
	uint32_t fp_n = 0;
	int st;
	s_draw_count = 0;
	s_view_fp_lod = HCU_OBJECTS_FP_LOD_NEAR;
	s_fp_draw_count = 0;
	s_cur_view = view;
	s_world_render_cycles = s_fp_render_cycles = 0u;
	s_view_triangles = 0;
	s_view_skinned = 0;
	s_view_drawn = 0;
	if (!s_snapshot) return;
	st = hcu_render_objects_select(s_snapshot, view, s_meta, s_slot_count, s_draw, HCU_OBJECTS_MAX_DRAW,
		&n, &s_view_counters);
	if (st != 0) { s_view_counters.failures++; n = 0; }
	s_draw_count = n;
	st = hcu_render_objects_select_first_person(s_snapshot, view, s_meta,
		s_slot_count, s_fp_draw, &fp_n, &s_view_counters);
	if (st != 0) { s_view_counters.failures++; fp_n = 0; }
	s_fp_draw_count = fp_n;
	s_fx_count = 0;
	st = hcu_render_effects_select(s_snapshot, view, s_fx, HCU_FX_MAX_PER_VIEW, &s_fx_count, &s_view_counters);
	if (st != 0) { s_view_counters.failures++; s_fx_count = 0; }
	if (s_frame == 0) {
		if (!s_parity.records) hcu_render_parity_log_init(&s_parity, s_parity_store, HCU_OBJECTS_MAX_PARITY);
		if (hcu_render_objects_parity(&s_parity, s_frame, s_draw, n, &s_view_counters) != HCU_RENDER_CONTENT_OK)
			s_view_counters.failures++;
	}
}

void hcu_render_objects_view_end(uint32_t view, hcu_render_objects_view_stats *out)
{
	(void)view;
	if (out) {
		out->drawn = s_view_drawn;
		out->triangles = s_view_triangles;
		out->skinned_nodes = s_view_skinned;
		out->failures = s_view_counters.failures;
		out->pins_before = s_totals.pins;
		out->model_hits = s_view_counters.model_hits;
		out->model_misses = s_view_counters.model_misses;
		out->texture_hits = s_view_counters.texture_hits;
		out->texture_misses = s_view_counters.texture_misses;
		out->parity_records = s_parity.records ? s_parity.count : 0;
		out->sky_drawn = s_view_counters.sky_drawn;
		out->sky_misses = s_view_counters.sky_misses;
		out->first_person_draws = s_view_counters.first_person_draws;
		out->first_person_model_hits = s_view_counters.first_person_model_hits;
		out->first_person_model_misses = s_view_counters.first_person_model_misses;
		out->first_person_stale_resources = s_view_counters.first_person_stale_resources;
		out->first_person_weapon_draws = s_view_counters.first_person_weapon_draws;
		out->first_person_hands_draws = s_view_counters.first_person_hands_draws;
		out->first_person_lod = s_view_fp_lod;
		out->parts_logged = s_view_counters.parts_logged;
		out->effects_selected = s_view_counters.effects_selected;
		out->effects_refused = s_view_counters.effects_refused;
		out->fx_drawn = s_view_counters.fx_drawn;
		out->fx_skipped_space = s_view_counters.fx_skipped_space;
		out->fx_textured = s_view_counters.fx_textured;
		out->fx_flat = s_view_counters.fx_flat;
		out->fx_no_binding = s_view_counters.fx_no_binding;
		out->fx_budget_deferred = s_view_counters.fx_budget_deferred;
		out->fx_cache_full = s_view_counters.fx_cache_full;
		out->fx_blend_unsupported = s_view_counters.fx_blend_unsupported;
		out->fx_source_calls = s_view_counters.fx_source_calls;
		out->fx_source_read_bytes = s_view_counters.fx_source_read_bytes;
		out->fx_resident_hits = s_view_counters.fx_resident_hits;
		out->fx_resident_misses = s_view_counters.fx_resident_misses;
		out->first_person_weapon_resource_id = 0u;
		out->first_person_hands_resource_id = 0u;
		out->first_person_weapon_resource_slot = HALO_PS2_FRAME_NONE_U16;
		out->first_person_hands_resource_slot = HALO_PS2_FRAME_NONE_U16;
		out->first_person_map_generation = s_snapshot ? s_snapshot->map_generation : 0u;
		if (s_snapshot && view < s_snapshot->view_count) {
			const halo_ps2_frame_view *fv = &s_snapshot->views[view];
			if (fv->first_person_weapon_resource_slot < s_snapshot->resource_count) {
				out->first_person_weapon_resource_slot = fv->first_person_weapon_resource_slot;
				out->first_person_weapon_resource_id = s_snapshot->resources[
					fv->first_person_weapon_resource_slot].id;
			}
			if (fv->first_person_hands_resource_slot < s_snapshot->resource_count) {
				out->first_person_hands_resource_slot = fv->first_person_hands_resource_slot;
				out->first_person_hands_resource_id = s_snapshot->resources[
					fv->first_person_hands_resource_slot].id;
			}
		}
	}
	s_totals.objects_drawn += s_view_drawn;
	s_totals.submitted_bipeds += s_view_counters.submitted_bipeds;
	s_totals.submitted_vehicles += s_view_counters.submitted_vehicles;
	s_totals.submitted_weapons += s_view_counters.submitted_weapons;
	s_totals.attempted_bipeds += s_view_counters.attempted_bipeds;
	s_totals.attempted_vehicles += s_view_counters.attempted_vehicles;
	s_totals.attempted_weapons += s_view_counters.attempted_weapons;
	s_totals.refused_bipeds += s_view_counters.refused_bipeds;
	s_totals.refused_vehicles += s_view_counters.refused_vehicles;
	s_totals.refused_weapons += s_view_counters.refused_weapons;
	s_totals.unique_bipeds += s_view_counters.unique_bipeds;
	s_totals.unique_vehicles += s_view_counters.unique_vehicles;
	s_totals.unique_weapons += s_view_counters.unique_weapons;
	s_totals.drawn_identity_overflow += s_view_counters.drawn_identity_overflow;
	s_totals.triangles += s_view_triangles;
	s_totals.skinned_nodes += s_view_skinned;
	s_totals.failures += s_view_counters.failures;
	s_totals.model_hits += s_view_counters.model_hits;
	s_totals.model_misses += s_view_counters.model_misses;
	s_totals.texture_hits += s_view_counters.texture_hits;
	s_totals.texture_misses += s_view_counters.texture_misses;
	s_totals.first_person_draws += s_view_counters.first_person_draws;
	s_totals.first_person_model_hits += s_view_counters.first_person_model_hits;
	s_totals.first_person_model_misses += s_view_counters.first_person_model_misses;
	s_totals.first_person_stale_resources += s_view_counters.first_person_stale_resources;
	s_totals.first_person_weapon_draws += s_view_counters.first_person_weapon_draws;
	s_totals.first_person_hands_draws += s_view_counters.first_person_hands_draws;
	s_totals.effects_selected += s_view_counters.effects_selected;
	s_totals.effects_refused += s_view_counters.effects_refused;
	s_totals.parts_logged += s_view_counters.parts_logged;
	s_totals.fx_drawn += s_view_counters.fx_drawn;
	s_totals.fx_skipped_space += s_view_counters.fx_skipped_space;
	s_totals.fx_textured += s_view_counters.fx_textured;
	s_totals.fx_flat += s_view_counters.fx_flat;
	s_totals.fx_no_binding += s_view_counters.fx_no_binding;
	s_totals.fx_budget_deferred += s_view_counters.fx_budget_deferred;
	s_totals.fx_cache_full += s_view_counters.fx_cache_full;
	s_totals.fx_blend_unsupported += s_view_counters.fx_blend_unsupported;
	s_totals.fx_source_calls += s_view_counters.fx_source_calls;
	s_totals.fx_source_read_bytes += s_view_counters.fx_source_read_bytes;
	s_totals.fx_resident_hits += s_view_counters.fx_resident_hits;
	s_totals.fx_resident_misses += s_view_counters.fx_resident_misses;
	s_view_counters.fx_drawn = s_view_counters.fx_skipped_space = 0;
	s_view_counters.fx_textured = s_view_counters.fx_flat = s_view_counters.fx_no_binding = 0;
	s_view_counters.fx_budget_deferred = s_view_counters.fx_cache_full = 0;
	s_view_counters.fx_blend_unsupported = 0;
	s_view_counters.fx_source_calls = s_view_counters.fx_source_read_bytes = 0;
	s_view_counters.fx_resident_hits = s_view_counters.fx_resident_misses = 0;
	s_view_counters.parts_logged = 0;
	s_view_counters.first_person_weapon_draws = s_view_counters.first_person_hands_draws = 0;
	s_totals.deduped += s_view_counters.deduped;
	s_view_counters.deduped = 0;
	s_view_counters.failures = 0;
	s_view_counters.submitted_bipeds = s_view_counters.submitted_vehicles = 0;
	s_view_counters.submitted_weapons = 0;
	s_view_counters.attempted_bipeds = s_view_counters.attempted_vehicles = 0;
	s_view_counters.attempted_weapons = 0;
	s_view_counters.refused_bipeds = s_view_counters.refused_vehicles = 0;
	s_view_counters.refused_weapons = 0;
	s_view_counters.unique_bipeds = s_view_counters.unique_vehicles = 0;
	s_view_counters.unique_weapons = s_view_counters.drawn_identity_overflow = 0;
	s_view_counters.model_hits = s_view_counters.model_misses = 0;
	s_view_counters.texture_hits = s_view_counters.texture_misses = 0;
	s_view_counters.first_person_draws = 0;
	s_view_counters.first_person_model_hits = s_view_counters.first_person_model_misses = 0;
	s_view_counters.first_person_stale_resources = 0;
	s_view_counters.effects_selected = s_view_counters.effects_refused = 0;
	s_draw_count = 0;
	s_fp_draw_count = 0;
	s_fx_count = 0;
}

void hcu_render_objects_frame_end(void)
{
	if (s_pin.pinned) s_pending_seq = bsp_render_kick_seq();
}

int hcu_render_objects_release(void)
{
	if (s_pin.pinned) {
		/* A pin without an assigned kick may still be referenced by the chain being built.
		 * Keep both the pin and its cache state until its exact kick is observed complete. */
		if (!s_pending_seq || bsp_render_fence_observed(s_pending_seq) != 1) return 0;
		if (bsp_render_source_release(BSP_SRC_OBJECT_PIN, s_pending_seq) != 1) return 0;
		pin_drop();
	}
	s_pending_seq = 0;
	s_snapshot = NULL;
	s_pose_snapshot = NULL;
	return 1;
}

void hcu_render_objects_totals(hcu_render_objects_counters *out)
{
	if (out) *out = s_totals;
}

int hcu_render_objects_parity_summary(hcu_render_parity_summary *out)
{
	return hcu_render_parity_summarize(&s_parity, out);
}
#endif /* HCU_RENDER_OBJECTS_EE */

const hcu_render_objects_timing_probe *hcu_render_objects_timing_probe_get(void)
{
#if defined(HCU_RENDER_OBJECTS_EE) && \
	((defined(HALO_PS2_C3_LAG_TRACE) && HALO_PS2_C3_LAG_TRACE) || \
	 (defined(HALO_PS2_C3_PERF_PROBE) && HALO_PS2_C3_PERF_PROBE))
	return &s_timing_probe;
#else
	return NULL;
#endif
}
