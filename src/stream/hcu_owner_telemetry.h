#ifndef HCU_OWNER_TELEMETRY_H
#define HCU_OWNER_TELEMETRY_H
/* C2.6 owner telemetry: one registry and one snapshot for every named owner.
 *
 * Rules:
 *   - EE BACKING owners contribute to the EE committed-budget total. GS backing
 *     owners are reported in a separate VRAM total and never added to EE RAM.
 *   - A NESTED owner is carved from or accounted inside one same-domain BACKING
 *     owner (its parent). Its used/high/capacity are reported for diagnosis but
 *     are never added to either backing total.
 *   - Counters are per owner: high (peak used bytes since the last reset),
 *     failures (saturating count of refused requests) and resets (saturating count of
 *     quiescent resets). None of these is derived from another owner's counters.
 *
 * Producers either push events (hcu_owner_telemetry_note_*) or register a sampler
 * that reads the owner's own live counters at snapshot time (used by the renderer
 * for the EE render arena, GS texture window/cache, and DMA). */
#include <stddef.h>
#include <stdint.h>

typedef enum {
    HCU_OWNER_GAME_STATE,        /* BACKING: CE game-state CPU backing */
    HCU_OWNER_OBJECT_POOL,       /* NESTED in GAME_STATE: object memory pool */
    HCU_OWNER_ACTOR_POOL,        /* NESTED in GAME_STATE: actor datum array */
    HCU_OWNER_WIDGET_POOL,       /* NESTED in DYNAMIC_SIM: actual widget allocator not yet bound */
    HCU_OWNER_DYNAMIC_SIM,       /* BACKING: dynamic simulation arena */
    HCU_OWNER_TAGS,              /* BACKING: CE tag cache span */
    HCU_OWNER_BSP,               /* BACKING: current BSP / structure span */
    HCU_OWNER_RENDER_CHUNKS,     /* EE BACKING: renderer chunk arena */
    HCU_OWNER_RENDER_TEXTURE,    /* NESTED in EE RENDER_CHUNKS; currently unmeasured */
    HCU_OWNER_GS_WINDOW,          /* GS BACKING: renderer texture window incl. fixed pages */
    HCU_OWNER_GS_TEXTURE,         /* NESTED in GS_WINDOW: texture cache pages */
    HCU_OWNER_STREAMING,         /* BACKING: staging pool bytes */
    HCU_OWNER_SCRATCH,           /* BACKING: frame/decode scratch arena */
    HCU_OWNER_DMA,               /* BACKING: DMA command chains (sampler) */
    HCU_OWNER_AUDIO_REQUESTS,    /* BACKING: audio request queue (sampler) */
    HCU_OWNER_COUNT
} hcu_owner_id_t;

typedef enum {
    HCU_OWNER_KIND_BACKING = 0,
    HCU_OWNER_KIND_NESTED = 1
} hcu_owner_kind_t;

typedef enum {
    HCU_OWNER_DOMAIN_EE = 0,
    HCU_OWNER_DOMAIN_GS = 1
} hcu_owner_domain_t;

/* Sampler contract: fill every field from the owner's own live counters. `high`
 * must be the peak since the owner's last reset; `failures` and `resets` are
 * lifetime-since-bind counts. Return 0 if the owner is not bound yet. */
typedef struct {
    size_t capacity;   /* bytes committed to this owner (for NESTED: inside parent) */
    size_t used;       /* bytes live now */
    size_t high;       /* peak used bytes */
    uint32_t failures; /* refused allocations/requests */
    uint32_t resets;   /* quiescent resets */
} hcu_owner_sample_t;

typedef int (*hcu_owner_sampler_fn)(void *ctx, hcu_owner_sample_t *out);

typedef struct {
    hcu_owner_sampler_fn sampler;
    void *ctx;
    /* Event-driven counters, used when no sampler is registered. */
    hcu_owner_sample_t events;
    int bound;
} hcu_owner_slot_t;

typedef struct {
    hcu_owner_slot_t owners[HCU_OWNER_COUNT];
} hcu_owner_telemetry_t;

typedef struct {
    hcu_owner_id_t id;
    const char *name;
    hcu_owner_kind_t kind;
    hcu_owner_domain_t domain;
    int parent;        /* parent owner id, or -1 for BACKING */
    int bound;
    hcu_owner_sample_t sample;
} hcu_owner_row_t;

typedef struct {
    hcu_owner_row_t rows[HCU_OWNER_COUNT];
    /* Sums over EE BACKING owners only. Nested owners are never added here. */
    size_t backing_capacity;
    size_t backing_used;
    size_t backing_high;
    uint64_t backing_failures;
    uint64_t backing_resets;
    /* GS-space backing totals are separate from EE RAM totals. */
    size_t gs_capacity;
    size_t gs_used;
    size_t gs_high;
    uint64_t gs_failures;
    uint64_t gs_resets;
    /* Nested owners must fit under a same-domain backing parent. */
    int nested_within_parent;
} hcu_owner_report_t;

void hcu_owner_telemetry_init(hcu_owner_telemetry_t *t);
/* Registers a live sampler. Returns 0 for a bad id or null sampler. */
int hcu_owner_telemetry_bind_sampler(hcu_owner_telemetry_t *t, hcu_owner_id_t id,
    hcu_owner_sampler_fn sampler, void *ctx);
/* Event hooks for owners without a sampler. Each returns 0 on bad id. */
int hcu_owner_telemetry_note_capacity(hcu_owner_telemetry_t *t, hcu_owner_id_t id, size_t capacity);
int hcu_owner_telemetry_note_used(hcu_owner_telemetry_t *t, hcu_owner_id_t id, size_t used_now);
int hcu_owner_telemetry_note_failure(hcu_owner_telemetry_t *t, hcu_owner_id_t id);
int hcu_owner_telemetry_note_reset(hcu_owner_telemetry_t *t, hcu_owner_id_t id);

/* Fills one row per owner and the BACKING-only totals. Returns 0 on null args. */
int hcu_owner_telemetry_snapshot(const hcu_owner_telemetry_t *t, hcu_owner_report_t *out);
/* Static parent/kind table: 1 if `id` is a valid owner, writes its parent and kind. */
int hcu_owner_static_info(hcu_owner_id_t id, int *parent, hcu_owner_kind_t *kind, const char **name);
int hcu_owner_parent_is_valid(hcu_owner_id_t child, hcu_owner_id_t proposed_parent);
int hcu_owner_static_domain(hcu_owner_id_t id, hcu_owner_domain_t *domain);
#endif
