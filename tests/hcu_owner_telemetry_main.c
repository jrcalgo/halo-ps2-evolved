#include "stream/hcu_owner_telemetry.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>

static int fake_render_sampler(void *ctx, hcu_owner_sample_t *out) {
    const hcu_owner_sample_t *src = (const hcu_owner_sample_t *)ctx;
    if (!src) return 0;
    *out = *src;
    return 1;
}

static int fake_unbound(void *ctx, hcu_owner_sample_t *out) {
    (void)ctx;
    (void)out;
    return 0;
}

int main(void) {
    hcu_owner_telemetry_t t;
    hcu_owner_report_t r;
    int parent;
    hcu_owner_kind_t kind;
    const char *name;

    /* Static table: every nested owner names a BACKING parent. */
    for (int i = 0; i < (int)HCU_OWNER_COUNT; ++i) {
        assert(hcu_owner_static_info((hcu_owner_id_t)i, &parent, &kind, &name));
        assert(name && name[0]);
        if (kind == HCU_OWNER_KIND_NESTED) {
            assert(parent >= 0 && parent < (int)HCU_OWNER_COUNT);
            int pparent;
            hcu_owner_kind_t pkind;
            const char *pname;
            assert(hcu_owner_static_info((hcu_owner_id_t)parent, &pparent, &pkind, &pname));
            assert(pkind == HCU_OWNER_KIND_BACKING && pparent == -1);
        } else {
            assert(parent == -1);
        }
    }
    assert(!hcu_owner_static_info(HCU_OWNER_COUNT, &parent, &kind, &name));
    assert(hcu_owner_static_info(HCU_OWNER_WIDGET_POOL, &parent, &kind, &name));
    assert(kind == HCU_OWNER_KIND_NESTED && parent == HCU_OWNER_DYNAMIC_SIM);

    hcu_owner_telemetry_init(&t);

    /* Event-driven backings and nested pools. */
    assert(hcu_owner_telemetry_note_capacity(&t, HCU_OWNER_GAME_STATE, 1000));
    assert(hcu_owner_telemetry_note_used(&t, HCU_OWNER_GAME_STATE, 600));
    assert(hcu_owner_telemetry_note_used(&t, HCU_OWNER_GAME_STATE, 700));
    assert(hcu_owner_telemetry_note_used(&t, HCU_OWNER_GAME_STATE, 650));
    assert(hcu_owner_telemetry_note_failure(&t, HCU_OWNER_GAME_STATE));
    assert(hcu_owner_telemetry_note_failure(&t, HCU_OWNER_GAME_STATE));
    assert(hcu_owner_telemetry_note_reset(&t, HCU_OWNER_GAME_STATE));

    assert(hcu_owner_telemetry_note_capacity(&t, HCU_OWNER_OBJECT_POOL, 400));
    assert(hcu_owner_telemetry_note_used(&t, HCU_OWNER_OBJECT_POOL, 350));
    assert(hcu_owner_telemetry_note_failure(&t, HCU_OWNER_OBJECT_POOL));
    assert(hcu_owner_telemetry_note_capacity(&t, HCU_OWNER_ACTOR_POOL, 200));
    assert(hcu_owner_telemetry_note_used(&t, HCU_OWNER_ACTOR_POOL, 100));

    assert(hcu_owner_telemetry_note_capacity(&t, HCU_OWNER_DYNAMIC_SIM, 300));
    assert(hcu_owner_telemetry_note_used(&t, HCU_OWNER_DYNAMIC_SIM, 120));
    /* The widget pool is allocated from the dynamic-simulation arena; its
       internal use is nested telemetry, not another backing owner. */
    assert(hcu_owner_telemetry_note_capacity(&t, HCU_OWNER_WIDGET_POOL, 256));
    assert(hcu_owner_telemetry_note_used(&t, HCU_OWNER_WIDGET_POOL, 200));
    assert(hcu_owner_telemetry_note_capacity(&t, HCU_OWNER_TAGS, 5000));
    assert(hcu_owner_telemetry_note_used(&t, HCU_OWNER_TAGS, 4000));
    assert(hcu_owner_telemetry_note_capacity(&t, HCU_OWNER_BSP, 2000));
    assert(hcu_owner_telemetry_note_used(&t, HCU_OWNER_BSP, 1800));

    /* Sampler-driven render chunks, with a nested texture owner. */
    hcu_owner_sample_t chunks = {500, 100, 450, 1, 0};
    hcu_owner_sample_t texture = {300, 200, 280, 0, 2};
    assert(hcu_owner_telemetry_bind_sampler(&t, HCU_OWNER_RENDER_CHUNKS, fake_render_sampler, &chunks));
    assert(hcu_owner_telemetry_bind_sampler(&t, HCU_OWNER_RENDER_TEXTURE, fake_render_sampler, &texture));

    assert(hcu_owner_telemetry_note_capacity(&t, HCU_OWNER_SCRATCH, 64));
    assert(hcu_owner_telemetry_note_used(&t, HCU_OWNER_SCRATCH, 64));
    assert(hcu_owner_telemetry_note_capacity(&t, HCU_OWNER_STREAMING, 1024));
    assert(hcu_owner_telemetry_note_used(&t, HCU_OWNER_STREAMING, 512));
    assert(hcu_owner_telemetry_note_capacity(&t, HCU_OWNER_DMA, 1179648));
    assert(hcu_owner_telemetry_note_used(&t, HCU_OWNER_DMA, 1179648));
    assert(hcu_owner_telemetry_note_capacity(&t, HCU_OWNER_AUDIO_REQUESTS, 0));

    assert(hcu_owner_telemetry_snapshot(&t, &r));
    assert(r.nested_within_parent == 1);

    /* Nested rows are present and carry their own counters. */
    assert(r.rows[HCU_OWNER_OBJECT_POOL].sample.high == 350); /* peak from note_used */
    assert(r.rows[HCU_OWNER_OBJECT_POOL].sample.used == 350);
    assert(r.rows[HCU_OWNER_OBJECT_POOL].sample.failures == 1);
    assert(r.rows[HCU_OWNER_ACTOR_POOL].sample.capacity == 200);
    assert(r.rows[HCU_OWNER_WIDGET_POOL].parent == HCU_OWNER_DYNAMIC_SIM);
    assert(r.rows[HCU_OWNER_WIDGET_POOL].sample.used == 200);
    assert(r.rows[HCU_OWNER_RENDER_TEXTURE].kind == HCU_OWNER_KIND_NESTED);
    assert(r.rows[HCU_OWNER_RENDER_TEXTURE].sample.resets == 2);

    /* Backing totals must equal the sum over BACKING rows only. */
    size_t cap = 0, used = 0, high = 0;
    uint64_t fail = 0, reset = 0;
    for (int i = 0; i < (int)HCU_OWNER_COUNT; ++i) {
        if (r.rows[i].kind != HCU_OWNER_KIND_BACKING) continue;
        cap += r.rows[i].sample.capacity;
        used += r.rows[i].sample.used;
        high += r.rows[i].sample.high;
        fail += r.rows[i].sample.failures;
        reset += r.rows[i].sample.resets;
    }
    assert(r.backing_capacity == cap);
    assert(r.backing_used == used);
    assert(r.backing_high == high);
    assert(r.backing_failures == fail);
    assert(r.backing_resets == reset);

    /* Expected literal values: game state 1000 + dyn 300 + tags 5000 + bsp 2000
     * + chunks 500 + streaming 1024 + scratch 64 + dma 1179648 + audio 0. Nested
     * object pool 400, actor pool 200, widget pool 256 and texture 300 are NOT added. */
    assert(r.backing_capacity == 1000u + 300u + 5000u + 2000u + 500u + 1024u + 64u + 1179648u);
    /* Used sum: 650 + 120 + 4000 + 1800 + 100 + 512 + 64 + 1179648 (game-state
     * used is the last note, 650). */
    assert(r.backing_used == 650u + 120u + 4000u + 1800u + 100u + 512u + 64u + 1179648u);
    /* Peak sum counts backing peaks only: game state high 700, chunks 450. */
    assert(r.rows[HCU_OWNER_GAME_STATE].sample.high == 700);
    assert(r.backing_failures == 2u + 1u /* game state, render chunks */);
    assert(r.backing_resets == 1u);

    /* Nested capacity larger than parent makes the report invalid. */
    texture.capacity = 600;
    assert(hcu_owner_telemetry_snapshot(&t, &r));
    assert(r.nested_within_parent == 0);
    texture.capacity = 300;

    /* A sampler that reports not-bound leaves the row unbound and empty. */
    assert(hcu_owner_telemetry_bind_sampler(&t, HCU_OWNER_DMA, fake_unbound, NULL));
    assert(hcu_owner_telemetry_snapshot(&t, &r));
    assert(!r.rows[HCU_OWNER_DMA].bound && r.rows[HCU_OWNER_DMA].sample.capacity == 0);
    assert(r.backing_capacity == 1000u + 300u + 5000u + 2000u + 500u + 1024u + 64u);

    /* Counters saturate instead of wrapping. */
    hcu_owner_telemetry_t s;
    hcu_owner_telemetry_init(&s);
    s.owners[HCU_OWNER_STREAMING].events.failures = UINT32_MAX;
    assert(hcu_owner_telemetry_note_failure(&s, HCU_OWNER_STREAMING));
    assert(s.owners[HCU_OWNER_STREAMING].events.failures == UINT32_MAX);

    /* Bad arguments are rejected without touching state. */
    assert(!hcu_owner_telemetry_note_used(&t, HCU_OWNER_COUNT, 1));
    assert(!hcu_owner_telemetry_bind_sampler(&t, HCU_OWNER_TAGS, NULL, NULL));
    assert(!hcu_owner_telemetry_snapshot(NULL, &r));
    assert(!hcu_owner_telemetry_snapshot(&t, NULL));

    printf("hcu_owner_telemetry: all checks passed\n");
    return 0;
}
