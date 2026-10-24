#include "stream/hcu_render_objects.h"

#include <string.h>

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

int hcu_render_objects_select(const halo_ps2_frame_snapshot *snap, uint32_t view,
	const hcu_render_objects_model *models, uint32_t model_count,
	hcu_render_object_draw *out, uint32_t capacity, uint32_t *count,
	hcu_render_objects_counters *counters)
{
	const halo_ps2_frame_view *v;
	uint32_t ref, first, n, emitted = 0, i;
	if (!snap || !out || !count || !counters) return HCU_RENDER_CONTENT_E_ARGUMENT;
	*count = 0;
	if (snap->version != HALO_PS2_FRAME_SNAPSHOT_VERSION || view >= snap->view_count ||
		view >= HALO_PS2_FRAME_MAX_VIEWS || snap->object_count > HALO_PS2_FRAME_MAX_OBJECTS ||
		snap->view_ref_count > HALO_PS2_FRAME_MAX_VIEW_REFS)
		return HCU_RENDER_CONTENT_E_ARGUMENT;
	counters->views_seen++;
	v = &snap->views[view];
	if (!(v->flags & HALO_PS2_FRAME_VIEW_ACTIVE)) return 0;
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
		for (i = 0; i < emitted; i++)
			if (out[i].object_index == oi) break;
		if (i != emitted) { counters->deduped++; continue; }
		if (o->resource_slot >= snap->resource_count) { counters->failures++; continue; }
		r = &snap->resources[o->resource_slot];
		slot = hcu_render_objects_find_model(models, model_count, r->id);
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
		out[emitted].world = o->world;
		counters->model_hits++;
		emitted++;
	}
	*count = emitted;
	return 0;
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
		s->resources[res].generation = 1u;
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
#ifdef HCU_RENDER_OBJECTS_EE
#include "core/mat.h"
#include "render/bsp_render.h"
#include "render/obj_render.h"
#include "stream/sha256.h"
#include "world/model.h"
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
static uint32_t s_tex_total;
static tex_source_t s_src_total;
static int s_installed;

static hcu_render_objects_counters s_totals;
static hcu_render_objects_counters s_view_counters;
static hcu_render_objects_pin_t s_pin;
static uint32_t s_pending_seq;
static uint32_t s_frame;
static hcu_render_object_draw s_draw[HCU_OBJECTS_MAX_DRAW];
static uint32_t s_draw_count;
static hcu_render_parity_record s_parity_store[HCU_OBJECTS_MAX_PARITY];
static hcu_render_parity_log s_parity;
static uint32_t s_view_triangles, s_view_skinned, s_view_drawn;
static const halo_ps2_frame_snapshot *s_snapshot;

static int read_verified(const hcu_asset_profile_view *view, uint32_t id, uint32_t size,
	uint8_t *dst, const uint8_t want[32])
{
	sha256_context s;
	uint8_t digest[32];
	uint32_t at = 0;
	while (at < size) {
		uint32_t n = size - at < OBJ_READ_STEP ? size - at : OBJ_READ_STEP;
		if (hcu_asset_profile_read_range(view, HCU_ASSET_CHUNK_MEDIA, id, at, dst + at, n) != 0) return -1;
		at += n;
	}
	sha256_init(&s);
	sha256_update(&s, dst, size);
	sha256_final(&s, digest);
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

static void pool_init(uint8_t *base, uint32_t size)
{
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

/* Loads entry i into a fresh pool region, reading and verifying its bytes. Returns 0, or -1 when the pool
 * has no room (the caller may evict) or -2 when the entry itself is refused. */
static int entry_load(const hcu_asset_profile_view *view, uint32_t i, uint32_t frame)
{
	obj_slot *s = &s_slots[i];
	const hcu_render_objects_table_entry *e = s->entry;
	uint32_t need, model_span;
	uint32_t off;
	uint8_t *bytes;
	if (entry_need(s, &need) != 0) { s->refused = 1; s_res.entry_refusals++; return -2; }
	model_span = obj_align(s->model_size);
	off = pool_alloc(need);
	if (off == OBJ_NONE) return -1;
	bytes = s_pool + off;
	if (read_verified(view, e->model_chunk, s->model_size, bytes, e->model_sha256) != 0 ||
		model_open(&s->models, bytes, s->model_size) != MODEL_OK || model_get(&s->models, 0).node_count == 0) {
		pool_free(off);
		s->refused = 1;
		s_res.entry_refusals++;
		return -2;
	}
	s->has_tex = 0;
	if (e->texture_chunk && s->tex_size &&
		read_verified(view, e->texture_chunk, s->tex_size, bytes + model_span, e->texture_sha256) == 0 &&
		tex_open(&s->tex, bytes + model_span, s->tex_size) == TEX_OK) {
		if (s->tex.texture_count > HCU_OBJECTS_TEX_STRIDE) {
			s_res.keys_refused++;      /* more textures than the entry's key stride: drawn flat */
		} else {
			s->has_tex = 1;
		}
	}
	s->pool_off = off;
	s->pool_size = need;
	s->tex_base = (uint32_t)(s - s_slots) * HCU_OBJECTS_TEX_STRIDE;
	s->src.binding = slot_binding;
	s->src.texture = slot_texture;
	s->src.lightmap = NULL;
	s->src.user = s;
	s->src.texture_count = s->has_tex ? s->tex.texture_count : 0;
	s->loaded = 1;
	s->last_used = frame + 1u;
	s_meta[i].resource_id = e->source_datum & 0xFFFFu; /* CE model.index: low 16 bits of the tag datum */
	s_meta[i].source_datum = e->source_datum;
	s_meta[i].model_bytes = s->model_size;
	s_meta[i].texture_count = (uint16_t)(s->has_tex ? s->tex.texture_count : 0);
	s_meta[i].loaded = 1;
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
	s->has_tex = 0;
	s_meta[i].loaded = 0;
	s_res.evictions++;
	s_res.resident--;
}

/* Makes entry i resident for this frame: loads it when the pool has room, otherwise evicts the least recently
 * used entries that this frame does not reference, and only while the fence is clear. */
static void entry_request(const hcu_asset_profile_view *view, uint32_t i, uint32_t frame)
{
	obj_slot *s = &s_slots[i];
	uint32_t need;
	int safe = -1;
	if (s->loaded) { s->last_used = frame + 1u; s_res.hits++; return; }
	if (s->refused) { s_res.misses++; return; }
	if (entry_need(s, &need) != 0) { s->refused = 1; s_res.entry_refusals++; s_res.misses++; return; }
	for (;;) {
		if (pool_find(need) >= 0) {
			if (entry_load(view, i, frame) == 0) return;
			break;
		}
		if (safe < 0) safe = pool_fence_safe();
		if (!safe) { s_res.fence_blocked++; break; }
		{
			uint32_t v, best = OBJ_NONE;
			for (v = 0; v < s_slot_count; v++)
				if (s_slots[v].loaded && s_slots[v].last_used <= frame &&
					(best == OBJ_NONE || s_slots[v].last_used < s_slots[best].last_used)) best = v;
			if (best == OBJ_NONE) { s_res.pool_refusals++; break; }
			entry_evict(best);
		}
	}
	s_res.misses++;
}

/* Frame begin: every entry the snapshot's visible views reference is made resident before the views draw. */
static void residency_frame(const halo_ps2_frame_snapshot *snap, uint32_t frame)
{
	static uint8_t need[HCU_OBJECTS_MAX_MODELS];
	uint32_t v, ref, i;
	if (!snap || !s_pool) return;
	memset(need, 0, sizeof need);
	for (v = 0; v < snap->view_count && v < HALO_PS2_FRAME_MAX_VIEWS; v++) {
		const halo_ps2_frame_view *fv = &snap->views[v];
		if (!(fv->flags & HALO_PS2_FRAME_VIEW_ACTIVE)) continue;
		for (ref = fv->view_ref_first; ref < fv->view_ref_first + fv->view_ref_count && ref < snap->view_ref_count; ref++) {
			uint32_t oi = snap->view_refs[ref];
			uint32_t rid, k;
			if (oi >= snap->object_count) continue;
			if (snap->objects[oi].resource_slot >= snap->resource_count) continue;
			rid = snap->resources[snap->objects[oi].resource_slot].id;
			for (k = 0; k < s_slot_count; k++)
				if (!s_slots[k].refused && (s_slots[k].entry->source_datum & 0xFFFFu) == rid) { need[k] = 1; break; }
		}
	}
	/* Mark what this frame uses before any eviction, so a referenced entry is never the victim. */
	for (i = 0; i < s_slot_count; i++)
		if (need[i] && s_slots[i].loaded) s_slots[i].last_used = frame + 1u;
	for (i = 0; i < s_slot_count; i++)
		if (need[i]) entry_request(s_profile, i, frame);
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
	unsigned a, c;
	for (a = 0; a < 3; a++) {
		const float *basis = a == 0 ? w->forward : a == 1 ? w->left : w->up;
		for (c = 0; c < 3; c++) m.m[a][c] = basis[c] * w->scale;
	}
	for (c = 0; c < 3; c++) m.m[3][c] = w->position[c];
	m.m[0][3] = m.m[1][3] = m.m[2][3] = 0.0f;
	m.m[3][3] = 1.0f;
	return m;
}

/* ---- pose: the CE-published palette (or the placement for unskinned objects); no ANIM sampling ---- */
static const halo_ps2_frame_snapshot *s_pose_snapshot;

static int pose_fn(void *user, const object_t *ob, object_nodes_t *out)
{
	const hcu_render_object_draw *d = user;
	const obj_slot *s = &s_slots[d->slot];
	unsigned n, i;
	model_info mi;
	mat4 root = ob->root;
	if (!s->loaded) return 0;
	mi = model_get(&s->models, 0);
	n = mi.node_count;
	if (n == 0 || n > SKEL_MAX_NODES) return 0;
	if (d->palette_count) {
		if (d->palette_count < n || !s_pose_snapshot) return 0;
		for (i = 0; i < n; i++) {
			out->skin[i] = mat_from_snapshot(&s_pose_snapshot->palette[d->palette_first + i]);
			out->world[i] = out->skin[i];
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

static void object_pass(void *user, render_ctx_t *rc)
{
	uint32_t i;
	(void)user;
	for (i = 0; i < s_draw_count; i++) {
		const hcu_render_object_draw *d = &s_draw[i];
		obj_slot *s = &s_slots[d->slot];
		object_table_t table;
		object_t *ob = &table.obj[0];
		model_info mi;
		uint16_t perm[OBJ_MAX_REGIONS];
		mat4 root;
		if (!s->loaded) continue;
		mi = model_get(&s->models, 0);
		model_select_permutations(&s->models, &mi, NULL, perm);
		root = mat_from_snapshot(&d->world);
		memset(&table, 0, sizeof table);
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
		table.count = 1;
		s_objr.table = &table;
		s_objr.world.models = &s->models;
		s_objr.world.scen = NULL;
		s_objr.world.anims = NULL;
		s_objr.textures = &s->src;
		s_objr.draw_objects = 1;
		s_objr.draw_fp = 0;
		s_objr.fp = NULL;
		s_objr.lod = NULL;
		s_objr.bsp = NULL;
		s_objr.bsp_index = 0;
		s_objr.max_distance = 4000.0f;
		s_objr.max_batches = OBJ_BUDGET;
		s_objr.sky_model = -1;
		s_objr.pose = pose_fn;
		s_objr.pose_user = (void *)d;
		obj_render_pass(&s_objr, rc);
		if (s_objr.st_visible) {
			s_view_drawn++;
			s_view_counters.objects_drawn++;
			s_view_counters.triangles += s_objr.st_triangles;
		} else {
			s_view_counters.failures++;
		}
		s_view_triangles += s_objr.st_triangles;
	}
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
	memset(s_slots, 0, sizeof s_slots);
	memset(s_meta, 0, sizeof s_meta);
	memset(&s_res, 0, sizeof s_res);
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
			/* The synthetic set references the entry through the same residency path as a snapshot does. */
			entry_request(s_profile, i, s_frame);
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
	const halo_ps2_snapshot_camera *synthetic_cameras)
{
	s_frame = frame;
	memset(&s_view_counters, 0, sizeof s_view_counters);
	if (s_pin.pinned && s_pending_seq && bsp_render_fence_observed(s_pending_seq) == 1) {
		hcu_render_objects_unpin(&s_pin, &s_totals);
		s_pending_seq = 0;
	}
	if (synthetic_views) {
		if (publish_synthetic(frame, synthetic_views, synthetic_cameras) != 0) s_totals.failures++;
	}
	if (!s_pin.pinned) hcu_render_objects_pin(&s_pin, &s_totals);
	s_snapshot = s_pin.pinned ? s_pin.snapshot : NULL;
	residency_frame(s_snapshot, frame);
	s_pose_snapshot = s_snapshot;
	return s_snapshot;
}

void hcu_render_objects_view_begin(uint32_t view)
{
	uint32_t n = 0;
	int st;
	s_draw_count = 0;
	s_view_triangles = 0;
	s_view_skinned = 0;
	s_view_drawn = 0;
	if (!s_snapshot) return;
	st = hcu_render_objects_select(s_snapshot, view, s_meta, s_slot_count, s_draw, HCU_OBJECTS_MAX_DRAW,
		&n, &s_view_counters);
	if (st != 0) { s_view_counters.failures++; n = 0; }
	s_draw_count = n;
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
	}
	s_totals.objects_drawn += s_view_drawn;
	s_totals.triangles += s_view_triangles;
	s_totals.skinned_nodes += s_view_skinned;
	s_totals.failures += s_view_counters.failures;
	s_totals.model_hits += s_view_counters.model_hits;
	s_totals.model_misses += s_view_counters.model_misses;
	s_totals.texture_hits += s_view_counters.texture_hits;
	s_totals.texture_misses += s_view_counters.texture_misses;
	s_totals.deduped += s_view_counters.deduped;
	s_view_counters.deduped = 0;
	s_view_counters.failures = 0;
	s_view_counters.model_hits = s_view_counters.model_misses = 0;
	s_view_counters.texture_hits = s_view_counters.texture_misses = 0;
	s_draw_count = 0;
}

void hcu_render_objects_frame_end(void)
{
	if (s_pin.pinned) s_pending_seq = bsp_render_kick_seq();
}

void hcu_render_objects_release(void)
{
	if (s_pin.pinned) hcu_render_objects_unpin(&s_pin, &s_totals);
	s_pending_seq = 0;
	s_snapshot = NULL;
	s_pose_snapshot = NULL;
}

void hcu_render_objects_totals(hcu_render_objects_counters *out)
{
	if (out) *out = s_totals;
}
#endif /* HCU_RENDER_OBJECTS_EE */
