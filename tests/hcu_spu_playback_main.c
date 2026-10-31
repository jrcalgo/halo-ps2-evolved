#include <stdio.h>
#include <string.h>

#include "stream/hcu_spu_hw.h"
#include "stream/hcu_spu_playback.h"

#define CHECK(x) do { if (!(x)) { printf("FAIL line %d: %s\n", __LINE__, #x); return 1; } } while (0)

typedef struct { int kind; uint16_t entry; uint32_t value; } op_t;
static op_t ops[512];
static unsigned nops;
static void h_param(uint16_t e, uint16_t v) { ops[nops++] = (op_t){ 0, e, v }; }
static void h_addr(uint16_t e, uint32_t v) { ops[nops++] = (op_t){ 1, e, v }; }
static void h_switch(uint16_t e, uint32_t v) { ops[nops++] = (op_t){ 2, e, v }; }
static uint32_t h_get(uint16_t e) { (void)e; return 0; }
static unsigned uploads, upload_fail;
static uint32_t upload_addr[16], upload_min_addr = 0xffffffffu;
static int h_upload(const hcu_spu_sample *sample, uint32_t addr)
{
	(void)sample;
	if (upload_fail) return -1;
	if (uploads < 16) upload_addr[uploads] = addr;
	if (addr < upload_min_addr) upload_min_addr = addr;
	uploads++;
	return 0;
}
static const hcu_spu_hw hw = { h_param, h_addr, h_switch, h_get, h_upload, 0 };
static unsigned part_calls, part_fail;
static uint32_t part_offset[16], part_bytes[16];
static int h_upload_part(const hcu_spu_sample *sample, uint32_t addr, uint32_t offset, uint32_t bytes)
{
	(void)sample; (void)addr;
	if (part_fail) return -1;
	if (part_calls < 16) { part_offset[part_calls] = offset; part_bytes[part_calls] = bytes; }
	part_calls++;
	return 0;
}
static const hcu_spu_hw hw_part = { h_param, h_addr, h_switch, h_get, h_upload, h_upload_part };

static void w32(uint8_t *p, uint32_t v) { p[0] = v; p[1] = v >> 8; p[2] = v >> 16; p[3] = v >> 24; }

static uint8_t image[4u * 1024u * 1024u];
static uint32_t build_image(uint32_t count, const uint32_t *hashes, const uint16_t *perms,
	const uint16_t *perm_counts, uint32_t sample_bytes)
{
	uint32_t data_off = 32 + 32 * count, i, total;
	memset(image, 0, sizeof(image));
	memcpy(image, "HSB1", 4);
	w32(image + 4, 2); w32(image + 8, count); w32(image + 12, 32); w32(image + 16, data_off);
	for (i = 0; i < count; ++i) {
		uint8_t *e = image + 32 + 32 * i;
		float gain = 1.0f;
		w32(e, hashes[i]); e[4] = perms[i]; e[6] = perm_counts[i];
		w32(e + 8, 22050); w32(e + 12, 22050); /* one second */
		w32(e + 16, data_off + i * sample_bytes); w32(e + 20, sample_bytes);
		memcpy(e + 24, &gain, 4);
		if (i == 1) { e[28] = (4 * 64) & 255; e[29] = (4 * 64) >> 8; e[30] = (12 * 64) & 255; e[31] = (12 * 64) >> 8; } /* tag near 4 / far 12 */
	}
	total = data_off + count * sample_bytes + 32;
	w32(image + 20, total);
	return total;
}

/* the tests count in 30 Hz ticks; the player's clock is milliseconds */
#define TEST_MS_PER_TICK 33u

static hcu_sound_request req(uint16_t event, uint32_t owner, uint8_t prio, uint32_t tick, float gain)
{
	hcu_sound_request r;
	memset(&r, 0, sizeof(r));
	r.event = event; r.owner_datum = owner; r.priority = prio; r.game_time = tick * TEST_MS_PER_TICK;
	r.gain = gain; r.pitch = 1.0f;
	return r;
}

int main(void)
{
	hcu_spu_sample samples[8];
	uint32_t count = 0, data_off = 0, data_end = 0, i;
	const uint32_t hashes[3] = { hcu_spu_name_hash("Sound\\SFX\\Fire"), hcu_spu_name_hash("a"), hcu_spu_name_hash("a") };
	const uint16_t perms[3] = { 0, 0, 1 }, pcs[3] = { 1, 2, 2 };
	uint32_t total = build_image(3, hashes, perms, pcs, 64);
	hcu_spu_stats st;
	hcu_sound_request r;

	CHECK(hcu_spu_name_hash("Sound\\SFX\\Fire") == hcu_spu_name_hash("soundsfxfire"));
	CHECK(hcu_spu_pitch_for(48000, 1.0f) == 0x1000);
	CHECK(hcu_spu_pitch_for(22050, 1.0f) == 1882);
	CHECK(hcu_spu_pitch_for(22050, 2.0f) == 3763);
	CHECK(hcu_spu_pitch_for(44100, 100.0f) == 0x3FFF);
	CHECK(hcu_spu_volume_for(0.0f, 1.0f) == 0);
	CHECK(hcu_spu_volume_for(1.0f, 1.0f) == 8191);
	CHECK(hcu_spu_volume_for(5.0f, 1.0f) == 8191);

	CHECK(hcu_spu_bank_parse(image, total, samples, 8, &count, &data_off, &data_end) == 0);
	CHECK(count == 3 && data_off == 128 && data_end == total - 32);
	CHECK(samples[0].spu_addr == HCU_SPU_RAM_BASE && samples[1].spu_addr == HCU_SPU_RAM_BASE + 64);
	CHECK(hcu_spu_bank_parse(image, total - 16, samples, 8, &count, 0, 0) != 0);
	CHECK(hcu_spu_bank_parse(image, total, samples, 2, &count, 0, 0) != 0);
	image[0] = 'X';
	CHECK(hcu_spu_bank_parse(image, total, samples, 8, &count, 0, 0) == -2);
	image[0] = 'H';

	hcu_spu_attach(&hw, samples, count);
	CHECK(hcu_spu_ready());
	nops = 0;
	r = req(HCU_SOUND_EVENT_IMPULSE, 7, 4, 100, 0.5f);
	hcu_spu_request(&r, hashes[0]);
	CHECK(nops == 8); /* vol L/R, pitch, adsr1/2, ssa, lsax, kon */
	CHECK(ops[5].kind == 1 && ops[5].value == HCU_SPU_RAM_BASE);
	/* the loop address is the sample's terminator block: the SPU2 jumps to it at an end block */
	CHECK(ops[6].kind == 1 && ops[6].entry == (1u | 0x2100u) && ops[6].value == HCU_SPU_RAM_BASE + samples[0].bytes - 16u);
	CHECK(ops[7].kind == 2 && ops[7].value == 1u);
	CHECK(ops[0].value == hcu_spu_volume_for(0.5f, 1.0f));
	hcu_spu_get_stats(&st);
	CHECK(st.requests == 1 && st.started == 1 && st.voices_active == 1);

	r = req(HCU_SOUND_EVENT_IMPULSE, 7, 4, 101, 0.5f);
	hcu_spu_request(&r, 0xDEADBEEFu);
	hcu_spu_get_stats(&st);
	CHECK(st.no_sample == 1);

	/* permutations rotate for the same definition */
	nops = 0;
	r = req(HCU_SOUND_EVENT_IMPULSE, 1, 4, 102, 1.0f);
	hcu_spu_request(&r, hashes[1]);
	CHECK(ops[5].value == samples[1].spu_addr);
	nops = 0;
	hcu_spu_request(&r, hashes[1]);
	CHECK(ops[5].value == samples[2].spu_addr);

	/* STOP releases the matching owner's voice only */
	nops = 0;
	r = req(HCU_SOUND_EVENT_STOP, 7, 4, 103, 0.0f);
	hcu_spu_request(&r, hashes[0]);
	CHECK(nops == 1 && ops[0].kind == 2 && ops[0].value == 1u);
	hcu_spu_get_stats(&st);
	CHECK(st.stopped == 1 && st.voices_active == 2);

	/* fill all 24 voices, then a lower priority is dropped and a higher one steals */
	for (i = 0; i < 30; ++i) {
		r = req(HCU_SOUND_EVENT_IMPULSE, 1000 + i, 3, 200, 1.0f);
		hcu_spu_request(&r, hashes[0]);
	}
	hcu_spu_get_stats(&st);
	CHECK(st.voices_active == HCU_SPU_VOICES && st.stolen == 6 && st.dropped_busy == 0);
	r = req(HCU_SOUND_EVENT_IMPULSE, 4000, 2, 200, 1.0f);
	hcu_spu_request(&r, hashes[0]);
	hcu_spu_get_stats(&st);
	CHECK(st.dropped_busy == 1 && st.stolen == 6);
	r = req(HCU_SOUND_EVENT_IMPULSE, 5000, 9, 200, 1.0f);
	hcu_spu_request(&r, hashes[0]);
	hcu_spu_get_stats(&st);
	CHECK(st.stolen == 7);

	/* voices expire by sample length (1 s = 1002 ms) */
	r = req(HCU_SOUND_EVENT_IMPULSE, 6000, 3, 240, 1.0f);
	hcu_spu_request(&r, hashes[0]);
	hcu_spu_get_stats(&st);
	CHECK(st.voices_active < HCU_SPU_VOICES || st.started > 24);

	/* free every voice: all earlier ones are over by tick 400 */
	hcu_spu_attach(&hw, samples, count);
	{
		const float lp[3] = { 0, 0, 0 }, lf[3] = { 1, 0, 0 }, lu[3] = { 0, 0, 1 };
		float lg, rg, att;
		/* source on the listener's right (-y is right for forward +x, up +z: forward x up = (0,-1,0)) */
		const float right_src[3] = { 0, -10, 0 }, left_src[3] = { 0, 10, 0 }, ahead[3] = { 10, 0, 0 };
		const float near_src[3] = { 1, 0, 0 }, far_src[3] = { 100, 0, 0 };
		att = hcu_spu_spatial(lp, lf, lu, right_src, &lg, &rg);
		CHECK(rg > 0.99f && lg < 0.05f && att > 0.8f && att < 0.9f);
		att = hcu_spu_spatial(lp, lf, lu, left_src, &lg, &rg);
		CHECK(lg > 0.99f && rg < 0.05f);
		att = hcu_spu_spatial(lp, lf, lu, ahead, &lg, &rg);
		CHECK(lg > 0.99f && rg > 0.99f);
		att = hcu_spu_spatial(lp, lf, lu, near_src, &lg, &rg);
		CHECK(att == 1.0f && lg > 0.99f && rg > 0.99f);
		att = hcu_spu_spatial(lp, lf, lu, far_src, &lg, &rg);
		CHECK(att == 0.0f);

		hcu_spu_set_listener(lp, lf, lu);
		nops = 0;
		r = req(HCU_SOUND_EVENT_IMPULSE, 1, 3, 500, 1.0f);
		r.has_position = 1; r.position[1] = -10.0f;
		hcu_spu_request(&r, hashes[0]);
		CHECK(nops == 8 && ops[0].value < ops[1].value && ops[1].value > 0);
		nops = 0;
		r.position[1] = 0.0f; r.position[0] = 100.0f;
		hcu_spu_request(&r, hashes[0]);
		CHECK(nops == 0);
		hcu_spu_get_stats(&st);
		CHECK(st.inaudible == 1);
		/* a sound tag's own distances replace the defaults: hashes[1] carries near 4 / far 12 */
		CHECK(samples[1].near_dist == 4.0f && samples[1].far_dist == 12.0f && samples[0].far_dist == 0.0f);
		nops = 0;
		r.position[0] = 15.0f;
		hcu_spu_request(&r, hashes[1]);
		CHECK(nops == 0);
		hcu_spu_get_stats(&st);
		CHECK(st.inaudible == 2);
		r.position[0] = 8.0f;
		hcu_spu_request(&r, hashes[1]);
		CHECK(nops == 8);
		hcu_spu_set_listener(0, 0, 0);
	}

	/* loops: start once, a repeated start updates instead, restart at the end of the sample, stop releases */
	hcu_spu_attach(&hw, samples, count);
	nops = 0;
	r = req(HCU_SOUND_EVENT_LOOPING_START, 9, 3, 600, 1.0f);
	hcu_spu_request(&r, hashes[0]);
	CHECK(nops == 8);
	nops = 0;
	hcu_spu_request(&r, hashes[0]);
	hcu_spu_get_stats(&st);
	CHECK(st.loops_started == 1 && st.voices_active == 1);
	nops = 0;
	hcu_spu_tick(610 * TEST_MS_PER_TICK);
	CHECK(nops == 0);
	hcu_spu_tick(640 * TEST_MS_PER_TICK);
	CHECK(nops == 9); /* key-off, then the eight key-on operations */
	hcu_spu_get_stats(&st);
	CHECK(st.loop_restarts == 1 && st.voices_active == 1);
	r = req(HCU_SOUND_EVENT_FADE, 9, 3, 641, 0.5f);
	nops = 0;
	hcu_spu_request(&r, hashes[0]);
	CHECK(nops == 2 && ops[0].value == hcu_spu_volume_for(0.5f, 1.0f));
	/* a loop whose pitch moves (an engine's revs) has its voice pitch changed with the volume */
	r = req(HCU_SOUND_EVENT_FADE, 9, 3, 641, 0.5f);
	r.pitch = 1.5f;
	nops = 0;
	hcu_spu_request(&r, hashes[0]);
	CHECK(nops == 3 && ops[0].value == hcu_spu_pitch_for(samples[0].rate, 1.5f));
	r = req(HCU_SOUND_EVENT_FADE, 9, 3, 642, 0.0f);
	nops = 0;
	hcu_spu_request(&r, hashes[0]);
	hcu_spu_get_stats(&st);
	CHECK(st.voices_active == 0);
	r = req(HCU_SOUND_EVENT_LOOPING_START, 9, 3, 650, 1.0f);
	hcu_spu_request(&r, hashes[0]);
	r = req(HCU_SOUND_EVENT_STOP, 9, 3, 651, 0.0f);
	hcu_spu_request(&r, hashes[0]);
	hcu_spu_get_stats(&st);
	CHECK(st.voices_active == 0);

	/* paging: three 900 KB samples; two are resident after the load, the third is uploaded on first use */
	{
		const uint32_t ph[3] = { 0x1001, 0x1002, 0x1003 };
		const uint16_t pp[3] = { 0, 0, 0 }, pc[3] = { 1, 1, 1 };
		uint32_t ptotal = build_image(3, ph, pp, pc, 900000u);
		hcu_spu_sample ps[4];
		uint32_t pcount = 0;
		CHECK(hcu_spu_bank_parse(image, ptotal, ps, 4, &pcount, 0, 0) == 0 && pcount == 3);
		CHECK(ps[0].resident && ps[1].resident && !ps[2].resident);
		hcu_spu_attach(&hw, ps, pcount);
		uploads = 0;
		r = req(HCU_SOUND_EVENT_IMPULSE, 1, 3, 1000, 1.0f);
		hcu_spu_request(&r, ph[0]);
		CHECK(uploads == 0); /* resident */
		/* the third does not fit: sample 1 is the least recently used one no voice plays (0 is playing) */
		r = req(HCU_SOUND_EVENT_IMPULSE, 2, 3, 1001, 1.0f);
		hcu_spu_request(&r, ph[2]);
		hcu_spu_get_stats(&st);
		CHECK(uploads == 1 && st.page_ins == 1 && st.evictions == 1 && st.page_fails == 0);
		CHECK(upload_addr[0] % 64u == 0 && upload_addr[0] >= HCU_SPU_RAM_BASE &&
			upload_addr[0] + 900000u <= HCU_SPU_RAM_END);
		CHECK(upload_addr[0] != ps[0].spu_addr); /* never over the playing sample */
		/* a sample uploaded in a tick starts on the next one, never in the tick that wrote it */
		{
			hcu_spu_stats before;
			hcu_spu_get_stats(&before);
			hcu_spu_tick(1001 * TEST_MS_PER_TICK);
			hcu_spu_get_stats(&st);
			CHECK(st.started == before.started + 1);
		}
		/* requesting the evicted one now evicts again (sample 0 and 2 both play: nothing is evictable) */
		uploads = 0;
		r = req(HCU_SOUND_EVENT_IMPULSE, 3, 3, 1002, 1.0f);
		hcu_spu_request(&r, ph[1]);
		hcu_spu_get_stats(&st);
		CHECK(uploads == 0 && st.page_fails == 1);
		/* after the voices end the evicted sample pages back in; a failing upload is counted */
		upload_fail = 1;
		r = req(HCU_SOUND_EVENT_IMPULSE, 4, 3, 1100, 1.0f);
		hcu_spu_request(&r, ph[1]);
		hcu_spu_get_stats(&st);
		CHECK(st.page_fails == 2 && uploads == 0);
		upload_fail = 0;
		r = req(HCU_SOUND_EVENT_IMPULSE, 4, 3, 1100, 1.0f);
		hcu_spu_request(&r, ph[1]);
		hcu_spu_get_stats(&st);
		CHECK(uploads == 1 && st.page_ins == 2);
		/* the evicted sample's voice had expired in the bookkeeping but not on the hardware: it was muted and keyed off first */
		CHECK(st.muted_before_evict >= 1);
	}
	/* a large page-in is spread over ticks: one 16 KB slice per call, the sound starts when the last slice is up */
	{
		uint32_t bh[64], i, bt;
		uint16_t bp[64], bc[64];
		hcu_spu_sample bs[64];
		uint32_t bcount = 0;
		for (i = 0; i < 64; ++i) { bh[i] = 0x3000 + i; bp[i] = 0; bc[i] = 1; }
		bt = build_image(64, bh, bp, bc, 40000u);
		CHECK(hcu_spu_bank_parse(image, bt, bs, 64, &bcount, 0, 0) == 0 && bcount == 64);
		CHECK(!bs[63].resident);
		hcu_spu_attach(&hw_part, bs, bcount);
		uploads = 0; part_calls = 0;
		r = req(HCU_SOUND_EVENT_IMPULSE, 1, 3, 2000, 1.0f);
		hcu_spu_request(&r, bh[63]);
		hcu_spu_get_stats(&st);
		CHECK(part_calls == 1 && part_offset[0] == 0 && part_bytes[0] == 16384u && uploads == 0);
		CHECK(st.started == 0 && st.page_ins == 0 && st.voices_active == 0);
		hcu_spu_tick(2000 * TEST_MS_PER_TICK + 33u);
		hcu_spu_get_stats(&st);
		CHECK(part_calls == 2 && part_offset[1] == 16384u && part_bytes[1] == 16384u && st.started == 0);
		hcu_spu_tick(2000 * TEST_MS_PER_TICK + 66u);
		hcu_spu_get_stats(&st);
		CHECK(part_calls == 3 && part_offset[2] == 32768u && part_bytes[2] == 40000u - 32768u);
		/* the last slice's transfer settles for one tick before the voice is keyed on */
		CHECK(st.page_ins == 1 && st.started == 0 && st.voices_active == 0 && st.page_fails == 0);
		hcu_spu_tick(2000 * TEST_MS_PER_TICK + 99u);
		hcu_spu_get_stats(&st);
		CHECK(st.started == 1 && st.voices_active == 1);
		/* a finished one-shot is keyed off explicitly (once), not left to the end flag */
		hcu_spu_tick(2000 * TEST_MS_PER_TICK + 66u + 500u);
		hcu_spu_get_stats(&st);
		CHECK(st.expiry_koffs == 0 && st.voices_active == 1);
		nops = 0;
		hcu_spu_tick(2000 * TEST_MS_PER_TICK + 66u + 1200u);
		hcu_spu_get_stats(&st);
		CHECK(st.expiry_koffs == 1 && st.voices_active == 0);
		CHECK(nops == 1 && ops[0].kind == 2 && ops[0].entry == (1u | 0x1600u) && ops[0].value == 1u);
		hcu_spu_tick(2000 * TEST_MS_PER_TICK + 66u + 1300u);
		hcu_spu_get_stats(&st);
		CHECK(st.expiry_koffs == 1);
		/* a failing slice drops the reservation and is counted; the sample pages in again later */
		part_calls = 0;
		r = req(HCU_SOUND_EVENT_IMPULSE, 2, 3, 2100, 1.0f);
		hcu_spu_request(&r, bh[62]);
		part_fail = 1;
		hcu_spu_tick(2100 * TEST_MS_PER_TICK + 33u);
		part_fail = 0;
		hcu_spu_get_stats(&st);
		CHECK(st.page_fails == 2 && st.started == 1); /* the failed slice, then the queued start's own page-in */
		part_calls = 0;
		r = req(HCU_SOUND_EVENT_IMPULSE, 2, 3, 2200, 1.0f);
		hcu_spu_request(&r, bh[62]);
		CHECK(part_calls == 1); /* the sample pages in again */
	}
	/* a bank with a pinned prefix: its samples are resident from the load and never evicted; paging uses the pool above */
	{
		uint32_t qh[64], i, qt, pinned_end;
		uint16_t qp[64], qc[64];
		hcu_spu_sample qs[64];
		uint32_t qcount = 0;
		for (i = 0; i < 64; ++i) { qh[i] = 0x4000 + i; qp[i] = 0; qc[i] = 1; }
		qt = build_image(64, qh, qp, qc, 40000u);
		w32(image + 24, 30u * 40000u); /* header spu_bytes: the first 30 samples are pinned */
		CHECK(hcu_spu_bank_resident_limit(image) == 30u * 40000u);
		CHECK(hcu_spu_bank_parse(image, qt, qs, 64, &qcount, 0, 0) == 0 && qcount == 64);
		for (i = 0; i < 64; ++i) CHECK(qs[i].resident == (i < 30u) && qs[i].pinned == (i < 30u));
		pinned_end = qs[29].spu_addr + qs[29].bytes;
		hcu_spu_attach(&hw, qs, qcount);
		uploads = 0; upload_min_addr = 0xffffffffu;
		/* far more distinct paged samples than the pool holds, each after the last has ended */
		for (i = 30; i < 64; ++i) {
			r = req(HCU_SOUND_EVENT_IMPULSE, 1, 3, 3000 + (i - 30) * 100, 1.0f);
			hcu_spu_request(&r, qh[i]);
		}
		hcu_spu_get_stats(&st);
		CHECK(uploads == 34 && st.page_fails == 0 && st.evictions > 0);
		CHECK(upload_min_addr >= pinned_end); /* nothing ever uploaded over the pinned prefix */
		/* a legacy bank (spu_bytes 0 or beyond the pool limit) pins nothing */
		w32(image + 24, 0);
		CHECK(hcu_spu_bank_parse(image, qt, qs, 64, &qcount, 0, 0) == 0 && !qs[0].pinned && qs[0].resident);
	}
	/* two new sounds in one tick: the first pages in at once, the second waits for the next tick */
	{
		const uint32_t dh[7] = { 0x2001, 0x2002, 0x2003, 0x2004, 0x2005, 0x2006, 0x2007 };
		const uint16_t dp[7] = { 0, 0, 0, 0, 0, 0, 0 }, dc[7] = { 1, 1, 1, 1, 1, 1, 1 };
		uint32_t dtotal = build_image(7, dh, dp, dc, 500000u);
		hcu_spu_sample ds[8];
		uint32_t dcount = 0, first = 0, second = 0, i;
		hcu_sound_request dr;
		CHECK(hcu_spu_bank_parse(image, dtotal, ds, 8, &dcount, 0, 0) == 0 && dcount == 7);
		for (i = 0; i < 7; ++i)
			if (!ds[i].resident) { if (!first) first = i + 1u; else if (!second) second = i + 1u; }
		CHECK(first && second);
		hcu_spu_attach(&hw, ds, dcount);
		uploads = 0;
		dr = req(HCU_SOUND_EVENT_IMPULSE, 1, 3, 2000, 1.0f);
		hcu_spu_request(&dr, dh[first - 1u]);
		dr = req(HCU_SOUND_EVENT_IMPULSE, 2, 3, 2000, 1.0f);
		hcu_spu_request(&dr, dh[second - 1u]);
		hcu_spu_get_stats(&st);
		CHECK(uploads == 1 && st.started == 0); /* the page-in's sound starts on the next tick */
		hcu_spu_tick(2001 * TEST_MS_PER_TICK);
		hcu_spu_get_stats(&st);
		CHECK(uploads == 2 && st.started == 1 && st.page_fails == 0);
		hcu_spu_tick(2002 * TEST_MS_PER_TICK);
		hcu_spu_get_stats(&st);
		CHECK(st.started == 2);
		/* a sound that waits longer than the queue allows is dropped, not started late */
		dr = req(HCU_SOUND_EVENT_IMPULSE, 3, 3, 2010, 1.0f);
		hcu_spu_request(&dr, dh[first - 1u]);
		hcu_spu_tick(2200 * TEST_MS_PER_TICK);
		hcu_spu_get_stats(&st);
		CHECK(st.page_fails == 0);
	}
	/* game_time is milliseconds: a 1 s sound still holds its voice 100 ms in, and is over after 1 s */
	hcu_spu_attach(&hw, samples, count);
	r = req(HCU_SOUND_EVENT_IMPULSE, 1, 3, 0, 1.0f);
	r.game_time = 50000u;
	hcu_spu_request(&r, hashes[0]);
	r.owner_datum = 2; r.game_time = 50100u;
	hcu_spu_request(&r, hashes[0]);
	hcu_spu_get_stats(&st);
	CHECK(st.voices_active == 2);
	r.owner_datum = 3; r.game_time = 51200u;
	hcu_spu_request(&r, hashes[0]);
	hcu_spu_get_stats(&st);
	CHECK(st.voices_active == 1);
	/* a half-pitch sound plays twice as long: it still holds its voice 1.5 s in */
	hcu_spu_attach(&hw, samples, count);
	r = req(HCU_SOUND_EVENT_IMPULSE, 1, 3, 0, 1.0f);
	r.game_time = 60000u; r.pitch = 0.5f;
	hcu_spu_request(&r, hashes[0]);
	r.owner_datum = 2; r.pitch = 1.0f; r.game_time = 61500u;
	hcu_spu_request(&r, hashes[0]);
	hcu_spu_get_stats(&st);
	CHECK(st.voices_active == 2);
	hcu_spu_attach(&hw, samples, count);
	/* a request that names its recording (a pitch range's permutation) gets that one, not the next in turn */
	nops = 0;
	r = req(HCU_SOUND_EVENT_IMPULSE, 1, 4, 102, 1.0f);
	r.permutation_hint = 2; /* flat permutation 1 */
	hcu_spu_request(&r, hashes[1]);
	CHECK(ops[5].value == samples[2].spu_addr);
	nops = 0;
	r.permutation_hint = 1; /* flat permutation 0 */
	hcu_spu_request(&r, hashes[1]);
	CHECK(ops[5].value == samples[1].spu_addr);
	nops = 0;
	r.permutation_hint = 9; /* a permutation that was not kept plays the nearest one below it */
	hcu_spu_request(&r, hashes[1]);
	CHECK(ops[5].value == samples[2].spu_addr);

	/* a kept recording of a pitch range carries the tag's permutation index, which may exceed the kept count */
	{
		const uint16_t big_perms[3] = { 3, 6, 0 }, one[3] = { 1, 1, 1 };
		hcu_spu_sample tmp[8];
		uint32_t n = 0, sz = build_image(3, hashes, big_perms, one, 64);
		CHECK(hcu_spu_bank_parse(image, sz, tmp, 8, &n, 0, 0) == 0 && n == 3 && tmp[0].perm == 3 && tmp[1].perm == 6);
	}
	printf("spu-playback-ok started=%u stopped=%u loops=%u fades=%u\n", st.started, st.stopped, st.loops_started, st.fades);
	return 0;
}
