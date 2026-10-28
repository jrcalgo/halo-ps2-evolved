#include "hcu_world_hotset.h"
#include <string.h>

typedef struct {
    uint32_t id, bytes;
    uint8_t kind, mandatory, visible;
} unique_candidate;

static void clear_plan(hcu_wh_plan *p, uint32_t generation) {
    memset(p, 0, sizeof(*p));
    p->generation = generation;
    p->status = HCU_WH_OK;
}

static int find_id(const unique_candidate *u, uint32_t n, uint32_t id) {
    uint32_t i;
    for (i = 0; i < n; ++i) if (u[i].id == id) return (int)i;
    return -1;
}

static uint32_t signature(const unique_candidate *u, uint32_t n) {
    uint32_t h = 2166136261u, i;
    /* u is canonical (ascending ID), making input ordering irrelevant. */
    for (i = 0; i < n; ++i) {
        h = (h ^ u[i].id) * 16777619u;
        h = (h ^ u[i].bytes) * 16777619u;
        h = (h ^ u[i].kind) * 16777619u;
        h = (h ^ u[i].mandatory) * 16777619u;
    }
    return h;
}

static void sort_unique(unique_candidate *u, uint32_t n) {
    uint32_t i, j;
    for (i = 1; i < n; ++i) {
        unique_candidate v = u[i];
        j = i;
        while (j && u[j - 1].id > v.id) { u[j] = u[j - 1]; --j; }
        u[j] = v;
    }
}

static int core_has(const hcu_wh_plan *p, uint32_t id) {
    uint32_t i;
    for (i = 0; i < p->core_count; ++i) if (p->core_ids[i] == id) return 1;
    return 0;
}

static int add_core(const unique_candidate *u, uint32_t index,
                    uint64_t limit, uint64_t *used, hcu_wh_plan *p) {
    if (core_has(p, u[index].id)) return 1;
    if (p->core_count >= HCU_WH_MAX_CORE) return -1;
    if (*used > limit || u[index].bytes > limit - *used) return 0;
    p->core_ids[p->core_count++] = u[index].id;
    *used += u[index].bytes;
    return 1;
}

int hcu_wh_plan_build(const hcu_wh_candidate *items, uint32_t count,
                      uint32_t generation, uint64_t pool_bytes,
                      uint64_t transient_reserve, hcu_wh_state *state,
                      hcu_wh_plan *out) {
    unique_candidate u[HCU_WH_MAX_CANDIDATES];
    uint32_t n = 0, i, j, sig;
    uint64_t used = 0, available, totals[3] = {0, 0, 0}, goals[3] = {0, 0, 0};
    int partial = 0;

    if (!out || !state || (!items && count) || count > HCU_WH_MAX_CANDIDATES)
        return HCU_WH_INVALID;
    clear_plan(out, generation);
    if (state->valid > 1 || state->count > HCU_WH_MAX_CORE) return out->status = HCU_WH_INVALID;
    if (transient_reserve > pool_bytes) return out->status = HCU_WH_NON_FIT;

    /* Merge exact duplicate references. Conflicting resource facts are invalid. */
    for (i = 0; i < count; ++i) {
        const hcu_wh_candidate *c = &items[i];
        int found = -1;
        if (c->generation != generation) continue;
        if (!c->bytes || c->kind > HCU_WH_GROUND_WEAPON || c->mandatory > 1 ||
            c->current_visible > 1 || c->predicted_visible > 1)
            return out->status = HCU_WH_INVALID;
        for (j = 0; j < n; ++j) if (u[j].id == c->id) { found = (int)j; break; }
        if (found >= 0) {
            unique_candidate *v = &u[found];
            if (v->bytes != c->bytes || v->kind != c->kind)
                return out->status = HCU_WH_INVALID;
            v->mandatory |= c->mandatory;
            v->visible |= (uint8_t)(c->current_visible || c->predicted_visible);
        } else {
            u[n].id = c->id; u[n].bytes = c->bytes; u[n].kind = c->kind;
            u[n].mandatory = c->mandatory;
            u[n].visible = (uint8_t)(c->current_visible || c->predicted_visible);
            ++n;
        }
    }
    sort_unique(u, n);
    sig = signature(u, n);
    for (i = 0; i < n; ++i) if (u[i].kind != HCU_WH_OTHER) {
        uint8_t k = u[i].kind;
        if (UINT64_MAX - totals[k] < u[i].bytes) return out->status = HCU_WH_OVERFLOW;
        totals[k] += u[i].bytes;
    }
    goals[HCU_WH_VEHICLE] = totals[HCU_WH_VEHICLE] / 2 + totals[HCU_WH_VEHICLE] % 2;
    goals[HCU_WH_GROUND_WEAPON] = totals[HCU_WH_GROUND_WEAPON] / 2 + totals[HCU_WH_GROUND_WEAPON] % 2;

    if (state->valid && state->generation == generation && state->signature == sig) {
        if (state->count > HCU_WH_MAX_CORE) return out->status = HCU_WH_INVALID;
        for (i = 0; i < state->count; ++i) {
            if (find_id(u, n, state->ids[i]) < 0 || core_has(out, state->ids[i]))
                return out->status = HCU_WH_INVALID;
            out->core_ids[out->core_count++] = state->ids[i];
        }
    } else {
        const uint64_t limit = pool_bytes - transient_reserve;
        /* Mandatory resources are added first, in canonical ID order. */
        for (i = 0; i < n; ++i) if (u[i].mandatory) {
            int rc = add_core(u, i, limit, &used, out);
            if (rc < 0) return out->status = HCU_WH_OVERFLOW;
            if (!rc) return out->status = HCU_WH_NON_FIT;
        }
        /* Reach half-byte goals where possible, trying smaller fitting IDs too. */
        for (i = 0; i < 2; ++i) {
            uint8_t kind = i ? HCU_WH_GROUND_WEAPON : HCU_WH_VEHICLE;
            uint64_t covered = 0;
            for (j = 0; j < out->core_count; ++j) {
                int ix = find_id(u, n, out->core_ids[j]);
                if (ix >= 0 && u[ix].kind == kind) covered += u[ix].bytes;
            }
            while (covered < goals[kind]) {
                int chosen = -1;
                for (j = 0; j < n; ++j) {
                    if (u[j].kind != kind || core_has(out, u[j].id)) continue;
                    if (used <= limit && u[j].bytes <= limit - used) { chosen = (int)j; break; }
                }
                if (chosen < 0) break;
                if (add_core(u, (uint32_t)chosen, limit, &used, out) < 0)
                    return out->status = HCU_WH_OVERFLOW;
                covered += u[chosen].bytes;
            }
            if (covered < goals[kind]) partial = 1;
        }
        state->generation = generation; state->signature = sig;
        state->count = out->core_count; state->valid = 1;
        for (i = 0; i < out->core_count; ++i) state->ids[i] = out->core_ids[i];
    }

    /* Recompute selected costs from canonical records and validate cached core. */
    used = 0;
    for (i = 0; i < out->core_count; ++i) {
        int ix = find_id(u, n, out->core_ids[i]);
        if (ix < 0) return out->status = HCU_WH_INVALID;
        if (UINT64_MAX - used < u[ix].bytes) return out->status = HCU_WH_OVERFLOW;
        used += u[ix].bytes;
        if (u[ix].mandatory) out->mandatory_bytes += u[ix].bytes;
        if (u[ix].kind == HCU_WH_VEHICLE) out->vehicle_coverage_bytes += u[ix].bytes;
        if (u[ix].kind == HCU_WH_GROUND_WEAPON) out->weapon_coverage_bytes += u[ix].bytes;
    }
    for (i = 0; i < n; ++i) if (u[i].mandatory && !core_has(out, u[i].id))
        return out->status = HCU_WH_INVALID;
    out->core_bytes = used; out->reserve_bytes = transient_reserve;
    if (out->mandatory_bytes > pool_bytes - transient_reserve || used > pool_bytes - transient_reserve)
        return out->status = HCU_WH_NON_FIT;
    available = pool_bytes - transient_reserve - used;
    out->vehicle_coverage_permille = totals[HCU_WH_VEHICLE] ?
        (uint32_t)(out->vehicle_coverage_bytes * 1000 / totals[HCU_WH_VEHICLE]) : 0;
    out->weapon_coverage_permille = totals[HCU_WH_GROUND_WEAPON] ?
        (uint32_t)(out->weapon_coverage_bytes * 1000 / totals[HCU_WH_GROUND_WEAPON]) : 0;
    for (i = 0; i < 2; ++i) {
        uint8_t kind = i ? HCU_WH_GROUND_WEAPON : HCU_WH_VEHICLE;
        uint64_t covered = kind == HCU_WH_VEHICLE ? out->vehicle_coverage_bytes : out->weapon_coverage_bytes;
        if (covered < goals[kind]) partial = 1;
    }

    /* Unique resources only; visibility orders prefetch, never core selection. */
    while (out->prefetch_count < HCU_WH_MAX_PREFETCH) {
        int best = -1;
        for (i = 0; i < n; ++i) {
            if (u[i].mandatory || core_has(out, u[i].id)) continue;
            for (j = 0; j < out->prefetch_count; ++j)
                if (out->prefetch_ids[j] == u[i].id) break;
            if (j < out->prefetch_count) continue;
            if (best < 0 || (u[i].visible > u[best].visible) ||
                (u[i].visible == u[best].visible && u[i].id < u[best].id)) best = (int)i;
        }
        if (best < 0) break;
        /* Skip items that do not fit; keep searching for smaller alternatives. */
        if (u[best].bytes > available) {
            int candidate = -1;
            for (i = 0; i < n; ++i) {
                if (u[i].mandatory || core_has(out, u[i].id) || u[i].bytes > available) continue;
                for (j = 0; j < out->prefetch_count; ++j) if (out->prefetch_ids[j] == u[i].id) break;
                if (j < out->prefetch_count) continue;
                if (candidate < 0 || u[i].visible > u[candidate].visible ||
                    (u[i].visible == u[candidate].visible && u[i].id < u[candidate].id)) candidate = (int)i;
            }
            if (candidate < 0) break;
            best = candidate;
        }
        out->prefetch_ids[out->prefetch_count++] = u[best].id;
        out->prefetch_bytes += u[best].bytes; available -= u[best].bytes;
    }
    if (partial) out->status = HCU_WH_PARTIAL;
    return out->status;
}
