#include "hcu_owner_telemetry.h"
#include <string.h>

typedef struct {
    const char *name;
    hcu_owner_kind_t kind;
    hcu_owner_domain_t domain;
    int parent;
} owner_static_t;

static const owner_static_t k_owners[HCU_OWNER_COUNT] = {
    [HCU_OWNER_GAME_STATE]     = {"game_state",         HCU_OWNER_KIND_BACKING, HCU_OWNER_DOMAIN_EE, -1},
    [HCU_OWNER_OBJECT_POOL]    = {"object_pool",        HCU_OWNER_KIND_NESTED,  HCU_OWNER_DOMAIN_EE, HCU_OWNER_GAME_STATE},
    [HCU_OWNER_ACTOR_POOL]     = {"actor_pool",         HCU_OWNER_KIND_NESTED,  HCU_OWNER_DOMAIN_EE, HCU_OWNER_GAME_STATE},
    [HCU_OWNER_WIDGET_POOL]    = {"widget_pool",        HCU_OWNER_KIND_NESTED,  HCU_OWNER_DOMAIN_EE, HCU_OWNER_DYNAMIC_SIM},
    [HCU_OWNER_DYNAMIC_SIM]    = {"dynamic_simulation", HCU_OWNER_KIND_BACKING, HCU_OWNER_DOMAIN_EE, -1},
    [HCU_OWNER_TAGS]           = {"tags",               HCU_OWNER_KIND_BACKING, HCU_OWNER_DOMAIN_EE, -1},
    [HCU_OWNER_BSP]            = {"bsp",                HCU_OWNER_KIND_BACKING, HCU_OWNER_DOMAIN_EE, -1},
    [HCU_OWNER_RENDER_CHUNKS]  = {"render_chunks",      HCU_OWNER_KIND_BACKING, HCU_OWNER_DOMAIN_EE, -1},
    [HCU_OWNER_RENDER_TEXTURE] = {"render_texture",     HCU_OWNER_KIND_NESTED,  HCU_OWNER_DOMAIN_EE, HCU_OWNER_RENDER_CHUNKS},
    [HCU_OWNER_GS_WINDOW]      = {"gs_window",          HCU_OWNER_KIND_BACKING, HCU_OWNER_DOMAIN_GS, -1},
    [HCU_OWNER_GS_TEXTURE]     = {"gs_texture",         HCU_OWNER_KIND_NESTED,  HCU_OWNER_DOMAIN_GS, HCU_OWNER_GS_WINDOW},
    [HCU_OWNER_STREAMING]      = {"streaming",          HCU_OWNER_KIND_BACKING, HCU_OWNER_DOMAIN_EE, -1},
    [HCU_OWNER_SCRATCH]        = {"scratch",            HCU_OWNER_KIND_BACKING, HCU_OWNER_DOMAIN_EE, -1},
    [HCU_OWNER_DMA]            = {"dma",                HCU_OWNER_KIND_BACKING, HCU_OWNER_DOMAIN_EE, -1},
    [HCU_OWNER_AUDIO_REQUESTS] = {"audio_requests",     HCU_OWNER_KIND_BACKING, HCU_OWNER_DOMAIN_EE, -1},
};

static int valid_id(hcu_owner_id_t id) {
    return (int)id >= 0 && (int)id < (int)HCU_OWNER_COUNT;
}

static void bump_u32(uint32_t *v) {
    if (*v != UINT32_MAX) ++*v;
}

void hcu_owner_telemetry_init(hcu_owner_telemetry_t *t) {
    if (t) memset(t, 0, sizeof *t);
}

int hcu_owner_static_info(hcu_owner_id_t id, int *parent, hcu_owner_kind_t *kind, const char **name) {
    if (!valid_id(id) || !parent || !kind || !name) return 0;
    *parent = k_owners[id].parent;
    *kind = k_owners[id].kind;
    *name = k_owners[id].name;
    return 1;
}

int hcu_owner_static_domain(hcu_owner_id_t id, hcu_owner_domain_t *domain) {
    if (!valid_id(id) || !domain) return 0;
    *domain = k_owners[id].domain;
    return 1;
}

int hcu_owner_parent_is_valid(hcu_owner_id_t child, hcu_owner_id_t proposed_parent) {
    if (!valid_id(child) || !valid_id(proposed_parent) ||
        k_owners[child].kind != HCU_OWNER_KIND_NESTED ||
        k_owners[child].parent != (int)proposed_parent ||
        k_owners[proposed_parent].kind != HCU_OWNER_KIND_BACKING ||
        k_owners[child].domain != k_owners[proposed_parent].domain)
        return 0;
    return 1;
}

int hcu_owner_telemetry_bind_sampler(hcu_owner_telemetry_t *t, hcu_owner_id_t id,
    hcu_owner_sampler_fn sampler, void *ctx) {
    if (!t || !valid_id(id) || !sampler) return 0;
    t->owners[id].sampler = sampler;
    t->owners[id].ctx = ctx;
    t->owners[id].bound = 1;
    return 1;
}

int hcu_owner_telemetry_note_capacity(hcu_owner_telemetry_t *t, hcu_owner_id_t id, size_t capacity) {
    if (!t || !valid_id(id)) return 0;
    t->owners[id].events.capacity = capacity;
    t->owners[id].bound = 1;
    return 1;
}

int hcu_owner_telemetry_note_used(hcu_owner_telemetry_t *t, hcu_owner_id_t id, size_t used_now) {
    if (!t || !valid_id(id)) return 0;
    hcu_owner_sample_t *e = &t->owners[id].events;
    e->used = used_now;
    if (used_now > e->high) e->high = used_now;
    t->owners[id].bound = 1;
    return 1;
}

int hcu_owner_telemetry_note_failure(hcu_owner_telemetry_t *t, hcu_owner_id_t id) {
    if (!t || !valid_id(id)) return 0;
    bump_u32(&t->owners[id].events.failures);
    t->owners[id].bound = 1;
    return 1;
}

int hcu_owner_telemetry_note_reset(hcu_owner_telemetry_t *t, hcu_owner_id_t id) {
    if (!t || !valid_id(id)) return 0;
    bump_u32(&t->owners[id].events.resets);
    t->owners[id].bound = 1;
    return 1;
}

int hcu_owner_telemetry_snapshot(const hcu_owner_telemetry_t *t, hcu_owner_report_t *out) {
    if (!t || !out) return 0;
    memset(out, 0, sizeof *out);
    out->nested_within_parent = 1;
    for (int i = 0; i < (int)HCU_OWNER_COUNT; ++i) {
        const hcu_owner_slot_t *s = &t->owners[i];
        hcu_owner_row_t *row = &out->rows[i];
        row->id = (hcu_owner_id_t)i;
        row->name = k_owners[i].name;
        row->kind = k_owners[i].kind;
        row->domain = k_owners[i].domain;
        row->parent = k_owners[i].parent;
        row->bound = s->bound;
        if (s->sampler) {
            /* A sampler that reports not-bound leaves the row empty. */
            if (!s->sampler(s->ctx, &row->sample)) {
                memset(&row->sample, 0, sizeof row->sample);
                row->bound = 0;
            } else {
                row->bound = 1;
            }
        } else {
            row->sample = s->events;
        }
    }
    for (int i = 0; i < (int)HCU_OWNER_COUNT; ++i) {
        const hcu_owner_row_t *row = &out->rows[i];
        if (row->kind == HCU_OWNER_KIND_BACKING) {
            if (row->domain == HCU_OWNER_DOMAIN_EE) {
                out->backing_capacity += row->sample.capacity;
                out->backing_used += row->sample.used;
                out->backing_high += row->sample.high;
                out->backing_failures += row->sample.failures;
                out->backing_resets += row->sample.resets;
            } else {
                out->gs_capacity += row->sample.capacity;
                out->gs_used += row->sample.used;
                out->gs_high += row->sample.high;
                out->gs_failures += row->sample.failures;
                out->gs_resets += row->sample.resets;
            }
        } else {
            const hcu_owner_row_t *parent;
            if (!hcu_owner_parent_is_valid(row->id, (hcu_owner_id_t)row->parent)) {
                out->nested_within_parent = 0;
                continue;
            }
            parent = &out->rows[row->parent];
            if (row->bound && parent->bound &&
                (row->domain != parent->domain || row->sample.capacity > parent->sample.capacity))
                out->nested_within_parent = 0;
        }
    }
    return 1;
}
