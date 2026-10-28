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
static uint32_t upload_addr[16];
static int h_upload(const hcu_spu_sample *sample, uint32_t addr)
{
	(void)sample;
	if (upload_fail) return -1;
	if (uploads < 16) upload_addr[uploads] = addr;
	uploads++;
	return 0;
}
static const hcu_spu_hw hw = { h_param, h_addr, h_switch, h_get, h_upload };

static void w32(uint8_t *p, uint32_t v) { p[0] = v; p[1] = v >> 8; p[2] = v >> 16; p[3] = v >> 24; }

static uint8_t image[4u * 1024u * 1024u];
static uint32_t build_image(uint32_t count, const uint32_t *hashes, const uint16_t *perms,
	const uint16_t *perm_counts, uint32_t sample_bytes)
{
	uint32_t data_off = 32 + 32 * count, i, total;
	memset(image, 0, sizeof(image));
	memcpy(image, "HSB1", 4);
	w32(image + 4, 1); w32(image + 8, count); w32(image + 12, 32); w32(image + 16, data_off);
	for (i = 0; i < count; ++i) {
		uint8_t *e = image + 32 + 32 * i;
		float gain = 1.0f;
		w32(e, hashes[i]); e[4] = perms[i]; e[6] = perm_counts[i];
		w32(e + 8, 22050); w32(e + 12, 22050); /* one second */
		w32(e + 16, data_off + i * sample_bytes); w32(e + 20, sample_bytes);
		memcpy(e + 24, &gain, 4); w32(e + 28, 100 + i);
	}
	total = data_off + count * sample_bytes + 32;
	w32(image + 20, total);
	return total;
}

static hcu_sound_request req(uint16_t event, uint32_t owner, uint8_t prio, uint32_t tick, float gain)
{
	hcu_sound_request r;
	memset(&r, 0, sizeof(r));
	r.event = event; r.owner_datum = owner; r.priority = prio; r.game_time = tick;
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
	CHECK(hcu_spu_volume_for(1.0f, 1.0f) == 11468);
	CHECK(hcu_spu_volume_for(5.0f, 1.0f) == 11468);

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
	CHECK(nops == 7); /* vol L/R, pitch, adsr1/2, ssa, kon */
	CHECK(ops[5].kind == 1 && ops[5].value == HCU_SPU_RAM_BASE);
	CHECK(ops[6].kind == 2 && ops[6].value == 1u);
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

	/* voices expire by sample length (1 s = 30 ticks + 2) */
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
		CHECK(nops == 7 && ops[0].value < ops[1].value && ops[1].value > 0);
		nops = 0;
		r.position[1] = 0.0f; r.position[0] = 100.0f;
		hcu_spu_request(&r, hashes[0]);
		CHECK(nops == 0);
		hcu_spu_get_stats(&st);
		CHECK(st.inaudible == 1);
		hcu_spu_set_listener(0, 0, 0);
	}

	/* loops: start once, a repeated start updates instead, restart at the end of the sample, stop releases */
	hcu_spu_attach(&hw, samples, count);
	nops = 0;
	r = req(HCU_SOUND_EVENT_LOOPING_START, 9, 3, 600, 1.0f);
	hcu_spu_request(&r, hashes[0]);
	CHECK(nops == 7);
	nops = 0;
	hcu_spu_request(&r, hashes[0]);
	hcu_spu_get_stats(&st);
	CHECK(st.loops_started == 1 && st.voices_active == 1);
	nops = 0;
	hcu_spu_tick(610);
	CHECK(nops == 0);
	hcu_spu_tick(640);
	CHECK(nops == 8); /* key-off, then the seven key-on operations */
	hcu_spu_get_stats(&st);
	CHECK(st.loop_restarts == 1 && st.voices_active == 1);
	r = req(HCU_SOUND_EVENT_FADE, 9, 3, 641, 0.5f);
	nops = 0;
	hcu_spu_request(&r, hashes[0]);
	CHECK(nops == 2 && ops[0].value == hcu_spu_volume_for(0.5f, 1.0f));
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
	}
	printf("spu-playback-ok started=%u stopped=%u loops=%u fades=%u\n", st.started, st.stopped, st.loops_started, st.fades);
	return 0;
}
