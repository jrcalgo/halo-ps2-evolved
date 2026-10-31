#ifndef HCU_BITMAP_DEFER_PROBE_H
#define HCU_BITMAP_DEFER_PROBE_H

#include <stdint.h>

#define HCU_BITMAP_DEFER_PROBE_MAGIC 0x42445031u /* BDP1 */
#define HCU_BITMAP_DEFER_PROBE_VERSION 1u

enum {
	HCU_BITMAP_PROBE_HUD = 0,
	HCU_BITMAP_PROBE_FX = 1,
	HCU_BITMAP_PROBE_WORLD = 2,
	HCU_BITMAP_PROBE_CLASS_COUNT = 3
};
enum {
	HCU_BITMAP_PROBE_BUDGET = 0,
	HCU_BITMAP_PROBE_NO_VICTIM = 1,
	HCU_BITMAP_PROBE_JOURNAL = 2,
	HCU_BITMAP_PROBE_REASON_COUNT = 3
};

/* Diagnostic-only PINE block. Keep this independent of the existing session trace ABI. */
typedef struct hcu_bitmap_defer_probe {
	uint32_t magic, version, bytes;
	volatile uint32_t seq;
	uint32_t frame, tick;
	uint32_t defer_frame[HCU_BITMAP_PROBE_CLASS_COUNT][HCU_BITMAP_PROBE_REASON_COUNT];
	uint32_t defer_total[HCU_BITMAP_PROBE_CLASS_COUNT][HCU_BITMAP_PROBE_REASON_COUNT];
	uint32_t sampled_failure_mask, sampled_class, sampled_reason, sampled_frame;
	uint32_t sampled_required_pages, sampled_required_bytes;
	uint32_t sampled_free_pages, sampled_free_clut, sampled_largest_run, sampled_budget_remaining;
	uint32_t sampled_fence_safe_victims, sampled_fence_blocked_victims, sampled_journal_remaining;
	uint32_t hud_draws_frame, hud_draws_total, hud_upload_pairs_frame, hud_upload_pairs_total;
	uint32_t fx_textured_draws_frame, fx_textured_draws_total;
	uint32_t fx_upload_pairs_frame, fx_upload_pairs_total;
	uint32_t world_upload_pairs_frame, world_upload_pairs_total;
} hcu_bitmap_defer_probe;
typedef char hcu_bitmap_defer_probe_size_assert[
	sizeof(hcu_bitmap_defer_probe) <= 512u ? 1 : -1];

#if defined(HALO_PS2_C3_BITMAP_DEFER_PROBE) && HALO_PS2_C3_BITMAP_DEFER_PROBE
extern volatile hcu_bitmap_defer_probe g_hcu_bitmap_defer_probe;
#define HCU_BITMAP_DEFER_PROBE_PTR (&g_hcu_bitmap_defer_probe)
#else
#define HCU_BITMAP_DEFER_PROBE_PTR ((volatile hcu_bitmap_defer_probe *)0)
#endif

static inline void hcu_bitmap_defer_probe_begin_frame(volatile hcu_bitmap_defer_probe *p,
	uint32_t frame, uint32_t tick)
{
	uint32_t seq;
	if (!p) return;
	seq = p->seq; p->seq = seq + 1u;
	if (p->magic != HCU_BITMAP_DEFER_PROBE_MAGIC || p->version != HCU_BITMAP_DEFER_PROBE_VERSION) {
		p->magic = HCU_BITMAP_DEFER_PROBE_MAGIC;
		p->version = HCU_BITMAP_DEFER_PROBE_VERSION;
		p->bytes = sizeof(*p);
		p->hud_draws_total = p->hud_upload_pairs_total = 0u;
		p->fx_textured_draws_total = p->fx_upload_pairs_total = p->world_upload_pairs_total = 0u;
		for (unsigned c = 0; c < HCU_BITMAP_PROBE_CLASS_COUNT; ++c)
			for (unsigned r = 0; r < HCU_BITMAP_PROBE_REASON_COUNT; ++r) p->defer_total[c][r] = 0u;
	}
	p->frame = frame; p->tick = tick;
	p->sampled_failure_mask = 0u;
	for (unsigned c = 0; c < HCU_BITMAP_PROBE_CLASS_COUNT; ++c)
		for (unsigned r = 0; r < HCU_BITMAP_PROBE_REASON_COUNT; ++r) p->defer_frame[c][r] = 0u;
	p->hud_draws_frame = p->hud_upload_pairs_frame = 0u;
	p->fx_textured_draws_frame = p->fx_upload_pairs_frame = p->world_upload_pairs_frame = 0u;
	p->seq = seq + 2u;
}

static inline void hcu_bitmap_defer_probe_add_hud(volatile hcu_bitmap_defer_probe *p,
	int draw_queued, int upload_queued)
{
	uint32_t seq;
	if (!p) return;
	seq = p->seq; p->seq = seq + 1u;
	if (draw_queued) { p->hud_draws_frame++; p->hud_draws_total++; }
	if (upload_queued) { p->hud_upload_pairs_frame++; p->hud_upload_pairs_total++; }
	p->seq = seq + 2u;
}

static inline void hcu_bitmap_defer_probe_add_fx_draws(volatile hcu_bitmap_defer_probe *p,
	uint32_t textured_draws)
{
	uint32_t seq;
	if (!p) return;
	seq = p->seq; p->seq = seq + 1u;
	p->fx_textured_draws_frame += textured_draws;
	p->fx_textured_draws_total += textured_draws;
	p->seq = seq + 2u;
}

static inline void hcu_bitmap_defer_probe_add_upload(volatile hcu_bitmap_defer_probe *p, unsigned cls)
{
	uint32_t seq;
	if (!p) return;
	seq = p->seq; p->seq = seq + 1u;
	if (cls == HCU_BITMAP_PROBE_FX) { p->fx_upload_pairs_frame++; p->fx_upload_pairs_total++; }
	else if (cls == HCU_BITMAP_PROBE_WORLD) { p->world_upload_pairs_frame++; p->world_upload_pairs_total++; }
	p->seq = seq + 2u;
}

#endif
