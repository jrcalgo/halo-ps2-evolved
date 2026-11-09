#include "stream/hcu_spu_stream.h"

#include <string.h>

#include "stream/hcu_spu_playback.h"

#define HMS_MAGIC 0x31534d48u /* 'HMS1' */
#define HMS_VERSION 1u
#define HMS_HEADER_BYTES 32u
#define HMS_PIECE_BYTES 16u
#define HMS_SLICE 16384u
#define BLOCK 16u
#define SD_CORE1 1u
#define SD_VOICE_PARAM_VOLL 0x0000u
#define SD_VOICE_PARAM_VOLR 0x0100u
#define SD_VOICE_PARAM_PITCH 0x0200u
#define SD_VOICE_PARAM_ADSR1 0x0300u
#define SD_VOICE_PARAM_ADSR2 0x0400u
#define SD_VOICE_ADDR_SSA 0x2000u
#define SD_VOICE_ADDR_LSAX 0x2100u
#define SD_VOICE_ADDR_NAX 0x2200u
#define SD_SWITCH_KON_ENTRY 0x1500u
#define SD_SWITCH_KOFF_ENTRY 0x1600u
#define STREAM_ADSR1 0x00FFu
#define STREAM_ADSR2 0x1FC0u
#define FLAG_LOOP_START 4u
#define FLAG_LOOP_END_REPEAT 3u

typedef struct { uint32_t offset, blocks, samples; } piece_t;
typedef struct { int32_t piece; uint32_t position, bytes, destination; } segment_t;

static const hcu_spu_hw *s_hw;
static hcu_spu_stream_source s_source;
static piece_t s_pieces[HCU_STREAM_MAX_PIECES];
static uint32_t s_piece_count, s_rate;
static int s_open;

static uint32_t s_queue[HCU_STREAM_QUEUE];
static uint32_t s_queue_head, s_queue_count;
static int32_t s_current;            /* piece being read, -1 before the first and after the last */
static uint32_t s_position;          /* bytes of one channel of it already planned */

static int s_playing;
static uint32_t s_last_half;
static int s_pending;                /* half awaiting a refill, -1 none */
static int s_stage;                  /* 0 idle, 1 left channel next, 2 right channel next */
static segment_t s_plan[4];
static uint32_t s_plan_count;
static uint32_t s_plan_half;
static hcu_spu_stream_stats s_stats;
static uint8_t s_buffer[HCU_STREAM_HALF] __attribute__((aligned(64)));

static uint32_t rd32(const uint8_t *p) { return p[0] | (p[1] << 8) | (p[2] << 16) | ((uint32_t)p[3] << 24); }

static uint16_t voice_entry(uint32_t voice, uint16_t param)
{
	return (uint16_t)(SD_CORE1 | (voice << 1) | param);
}

static uint32_t piece_bytes(const piece_t *piece) { return piece->blocks * BLOCK; }

int hcu_spu_stream_open(const hcu_spu_hw *hw, const hcu_spu_stream_source *source)
{
	uint8_t head[HMS_HEADER_BYTES], table[HCU_STREAM_MAX_PIECES * HMS_PIECE_BYTES];
	uint32_t count, table_off, data_off, i;
	s_open = 0;
	if (!hw || !source || !source->read || !hw->get_addr || !hw->upload_raw) return -1;
	if (source->size < HMS_HEADER_BYTES || source->read(source->context, 0, head, HMS_HEADER_BYTES) != 0) return -2;
	count = rd32(head + 16); table_off = rd32(head + 20); data_off = rd32(head + 24);
	s_rate = rd32(head + 8);
	if (rd32(head) != HMS_MAGIC || rd32(head + 4) != HMS_VERSION || rd32(head + 12) != 2u || s_rate < 8000u ||
		s_rate > 48000u || count < 1u || count > HCU_STREAM_MAX_PIECES || table_off != HMS_HEADER_BYTES ||
		data_off < table_off + count * HMS_PIECE_BYTES || rd32(head + 28) != source->size) return -3;
	if (source->read(source->context, table_off, table, count * HMS_PIECE_BYTES) != 0) return -4;
	for (i = 0; i < count; ++i) {
		const uint8_t *e = table + i * HMS_PIECE_BYTES;
		piece_t *p = &s_pieces[i];
		p->offset = rd32(e); p->blocks = rd32(e + 4); p->samples = rd32(e + 8);
		/* at least one half, so a half spans at most two pieces; two channels of blocks inside the file */
		if (p->blocks * BLOCK < HCU_STREAM_HALF || p->blocks > 0x1000000u || p->offset < data_off ||
			(uint64_t)p->offset + 2ull * p->blocks * BLOCK > source->size || p->samples > p->blocks * 28u) return -5;
	}
	s_hw = hw; s_source = *source; s_piece_count = count;
	s_queue_head = s_queue_count = 0; s_current = -1; s_position = 0;
	s_playing = 0; s_pending = -1; s_stage = 0;
	memset(&s_stats, 0, sizeof(s_stats));
	s_open = 1;
	return 0;
}

int hcu_spu_stream_ready(void) { return s_open; }
uint32_t hcu_spu_stream_piece_count(void) { return s_open ? s_piece_count : 0u; }

uint32_t hcu_spu_stream_piece_ms(uint32_t piece)
{
	return s_open && piece < s_piece_count ? (uint32_t)((uint64_t)s_pieces[piece].samples * 1000u / s_rate) : 0u;
}

int hcu_spu_stream_queue(uint32_t piece)
{
	if (!s_open || piece >= s_piece_count || s_queue_count >= HCU_STREAM_QUEUE) return -1;
	s_queue[(s_queue_head + s_queue_count++) % HCU_STREAM_QUEUE] = piece;
	return 0;
}

uint32_t hcu_spu_stream_queued(void) { return s_queue_count; }
int hcu_spu_stream_playing(void) { return s_playing; }
void hcu_spu_stream_get_stats(hcu_spu_stream_stats *out) { if (out) *out = s_stats; }

/* Decides what the next HCU_STREAM_HALF bytes of each channel are: pieces back to back, silence once none is left. */
static void plan_half(uint32_t half)
{
	uint32_t remaining = HCU_STREAM_HALF, destination = 0;
	s_plan_count = 0; s_plan_half = half;
	while (remaining) {
		segment_t *seg = &s_plan[s_plan_count];
		uint32_t take;
		if (s_current < 0 || s_position >= piece_bytes(&s_pieces[s_current])) {
			if (!s_queue_count) {
				seg->piece = -1; seg->position = 0; seg->bytes = remaining; seg->destination = destination;
				s_plan_count++;
				s_stats.silent_halves++;
				return;
			}
			s_current = (int32_t)s_queue[s_queue_head];
			s_queue_head = (s_queue_head + 1u) % HCU_STREAM_QUEUE; s_queue_count--;
			s_position = 0;
			s_stats.pieces_started++;
		}
		take = piece_bytes(&s_pieces[s_current]) - s_position;
		if (take > remaining) take = remaining;
		seg->piece = s_current; seg->position = s_position; seg->bytes = take; seg->destination = destination;
		s_plan_count++;
		s_position += take; destination += take; remaining -= take;
	}
}

/* Reads one channel's bytes of a planned segment into the buffer: per slice of the piece, the channel's part of it. */
static void read_segment(const segment_t *seg, uint32_t channel)
{
	uint32_t position = seg->position, left = seg->bytes;
	uint8_t *destination = s_buffer + seg->destination;
	const piece_t *piece;
	if (seg->piece < 0) { memset(destination, 0, left); return; }
	piece = &s_pieces[seg->piece];
	while (left) {
		uint32_t slice = position / HMS_SLICE, within = position % HMS_SLICE;
		uint32_t slice_bytes = piece_bytes(piece) - slice * HMS_SLICE, take;
		if (slice_bytes > HMS_SLICE) slice_bytes = HMS_SLICE;
		take = slice_bytes - within;
		if (take > left) take = left;
		if (s_source.read(s_source.context, piece->offset + slice * 2u * HMS_SLICE + channel * slice_bytes + within,
			destination, take) != 0) {
			memset(destination, 0, take);
			s_stats.read_fails++;
		}
		position += take; destination += take; left -= take;
	}
}

/* One channel of the planned half: read it, set the ring's loop flags, upload it. */
static int fill_channel(uint32_t channel)
{
	uint32_t i, ring = channel ? HCU_STREAM_RING_R : HCU_STREAM_RING_L;
	for (i = 0; i < s_plan_count; ++i) read_segment(&s_plan[i], channel);
	/* The ring's first block starts the loop, its last block ends it and repeats: the voice runs half 0, half 1, and
	 * on to half 0 again without anything but the refills changing what it reads. */
	if (s_plan_half == 0u) s_buffer[1] = FLAG_LOOP_START;
	else s_buffer[HCU_STREAM_HALF - BLOCK + 1u] = FLAG_LOOP_END_REPEAT;
	return s_hw->upload_raw(s_buffer, HCU_STREAM_HALF, ring + s_plan_half * HCU_STREAM_HALF);
}

int hcu_spu_stream_start(uint32_t volume)
{
	uint32_t half, voice;
	if (!s_open || s_playing || !s_queue_count) return -1;
	s_current = -1; s_position = 0; s_pending = -1; s_stage = 0;
	for (half = 0; half < 2u; ++half) {
		plan_half(half);
		if (fill_channel(0) != 0 || fill_channel(1) != 0) return -2;
	}
	for (voice = HCU_STREAM_VOICE_L; voice <= HCU_STREAM_VOICE_R; ++voice) {
		uint32_t ring = voice == HCU_STREAM_VOICE_L ? HCU_STREAM_RING_L : HCU_STREAM_RING_R;
		s_hw->set_param(voice_entry(voice, SD_VOICE_PARAM_VOLL), (uint16_t)(voice == HCU_STREAM_VOICE_L ? volume : 0u));
		s_hw->set_param(voice_entry(voice, SD_VOICE_PARAM_VOLR), (uint16_t)(voice == HCU_STREAM_VOICE_R ? volume : 0u));
		s_hw->set_param(voice_entry(voice, SD_VOICE_PARAM_PITCH), (uint16_t)hcu_spu_pitch_for(s_rate, 1.0f));
		s_hw->set_param(voice_entry(voice, SD_VOICE_PARAM_ADSR1), STREAM_ADSR1);
		s_hw->set_param(voice_entry(voice, SD_VOICE_PARAM_ADSR2), STREAM_ADSR2);
		s_hw->set_addr(voice_entry(voice, SD_VOICE_ADDR_SSA), ring);
		s_hw->set_addr(voice_entry(voice, SD_VOICE_ADDR_LSAX), ring);
	}
	/* One key-on for both so the channels start on the same sample and stay together. */
	s_hw->set_switch((uint16_t)(SD_CORE1 | SD_SWITCH_KON_ENTRY), HCU_STREAM_VOICE_MASK);
	s_last_half = 0;
	s_playing = 1;
	return 0;
}

void hcu_spu_stream_tick(void)
{
	if (!s_playing) return;
	s_stats.ticks++;
	if (s_stage == 0) {
		uint32_t nax = s_hw->get_addr(voice_entry(HCU_STREAM_VOICE_L, SD_VOICE_ADDR_NAX));
		if (nax >= HCU_STREAM_RING_L && nax < HCU_STREAM_RING_L + 2u * HCU_STREAM_HALF) {
			uint32_t half = (nax - HCU_STREAM_RING_L) / HCU_STREAM_HALF;
			if (half != s_last_half) {
				if (s_pending >= 0) s_stats.underruns++;
				s_pending = (int)s_last_half; /* the half the voices just left */
				s_last_half = half;
			}
		}
		if (s_pending < 0) return;
		plan_half((uint32_t)s_pending);
		s_stage = 1;
	}
	if (s_stage == 1) {
		if (fill_channel(0) != 0) s_stats.read_fails++;
		s_stage = 2;
	} else {
		/* The plan is spent (the left channel's reads were the segments); the right channel reads the same ones. */
		if (fill_channel(1) != 0) s_stats.read_fails++;
		s_stage = 0; s_pending = -1;
		s_stats.refills++;
	}
}

void hcu_spu_stream_stop(void)
{
	uint32_t voice;
	if (!s_open || !s_playing) return;
	for (voice = HCU_STREAM_VOICE_L; voice <= HCU_STREAM_VOICE_R; ++voice) {
		s_hw->set_param(voice_entry(voice, SD_VOICE_PARAM_VOLL), 0u);
		s_hw->set_param(voice_entry(voice, SD_VOICE_PARAM_VOLR), 0u);
	}
	s_hw->set_switch((uint16_t)(SD_CORE1 | SD_SWITCH_KOFF_ENTRY), HCU_STREAM_VOICE_MASK);
	s_playing = 0; s_pending = -1; s_stage = 0;
}
